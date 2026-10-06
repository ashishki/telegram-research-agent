from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import opencode_role_review as review
import mimo_code_review


def response():
    return {
        "model": "mimo-v2.6-pro",
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
            "verdict": "ADVISORY", "findings": [], "not_verified": ["live I/O"],
            "summary": "No P0/P1 found in the provided synthetic design.",
        })}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 30},
    }


@pytest.mark.parametrize("change", ["model", "truncated", "critical", "missing_summary"])
def test_invalid_identity_or_verdict_cannot_be_published(change):
    payload = response()
    verdict = json.loads(payload["choices"][0]["message"]["content"])
    if change == "model":
        payload["model"] = "other-model"
    elif change == "truncated":
        payload["choices"][0]["finish_reason"] = "length"
    elif change == "critical":
        verdict["findings"] = [{"severity": "P1", "title": "Replay", "issue": "Unsafe retry", "fix": "Fence it"}]
    else:
        verdict["summary"] = ""
    payload["choices"][0]["message"]["content"] = json.dumps(verdict)
    with pytest.raises(ValueError):
        review.parse_response(payload, "mimo-v2.6-pro")


def setup_run(tmp_path, monkeypatch, *, planning_block=False):
    doc = tmp_path / "design.md"
    doc.write_text("synthetic review input")
    design = {"feature_id": "F"}
    manifest = [{"path": "design.md", "sha256": review.digest(doc.read_bytes()), "bytes": len(doc.read_bytes())}]
    monkeypatch.setattr(review, "prepare_packet", lambda *args: ("synthetic packet", manifest, design))
    calls, records = [], []
    def preflight(*args, **kwargs):
        if planning_block:
            raise SystemExit("planning decision needs_input")
    workflow = SimpleNamespace(validate_task_feature_slice_binding=preflight, git_commit=lambda root: "a" * 40)
    lib = SimpleNamespace(design_hashes=lambda root, design: {"markdown_sha256": "b" * 64, "registry_payload_sha256": "c" * 64})
    approval = SimpleNamespace(write_design_review_record=lambda **kwargs: records.append(kwargs))
    monkeypatch.setattr(review, "pinned_modules", lambda root: (lib, workflow, approval))
    monkeypatch.setattr(mimo_code_review, "_api_key", lambda path: calls.append("key") or "synthetic-key")
    def fake_provider(**kwargs):
        calls.append(kwargs)
        return response()
    monkeypatch.setattr(mimo_code_review, "_call_model", fake_provider)
    args = SimpleNamespace(root=tmp_path, task="T1", feature_id="F", role="program_design_review",
                           model="mimo-v2.6-pro", key_file="", timeout_seconds=30,
                           call_cap=1, allow_provider_egress=True, prepare_only=False)
    return args, calls, records


@pytest.mark.parametrize("gate", ["planning", "egress", "budget", "prepare_only"])
def test_real_gates_precede_credential_lookup_and_provider_call(tmp_path, monkeypatch, gate):
    args, calls, records = setup_run(tmp_path, monkeypatch, planning_block=gate == "planning")
    if gate == "egress": args.allow_provider_egress = False
    if gate == "budget": args.call_cap = 0
    if gate == "prepare_only": args.prepare_only = True
    if gate == "prepare_only":
        assert review.execute(args) == 0
    else:
        with pytest.raises(ValueError):
            review.execute(args)
    assert calls == [] and records == []


def test_one_fake_provider_call_emits_distinct_hash_bound_non_codex_evidence(tmp_path, monkeypatch):
    args, calls, records = setup_run(tmp_path, monkeypatch)
    assert review.execute(args) == 0
    assert len(calls) == 2 and calls[0] == "key"
    assert calls[1]["max_output_tokens"] == 8000
    assert calls[1]["base_url"] == "https://opencode.ai/zen/go/v1"
    results = list((tmp_path / ".playbook-artifacts/opencode-runs").glob("*/result.json"))
    assert len(results) == 1
    result = json.loads(results[0].read_text())
    assert result["schema_version"] == "assistant.opencode_design_review.v1"
    assert result["requested_model"] == result["observed_model"] == "mimo-v2.6-pro"
    assert result["observed_effort"] == "unknown"
    assert "synthetic-key" not in results[0].read_text()
    assert results[0].with_suffix(".json.sha256").read_text().strip() == review.digest(results[0].read_bytes())
    assert len(records) == 1 and records[0]["reviewer_binding"].startswith("opencode_go:")
    assert records[0]["read_only"] is True


def test_input_drift_during_provider_call_never_creates_a_review_record(tmp_path, monkeypatch):
    args, calls, records = setup_run(tmp_path, monkeypatch)
    def changing_provider(**kwargs):
        (tmp_path / "design.md").write_text("changed after request")
        return response()
    monkeypatch.setattr(mimo_code_review, "_call_model", changing_provider)
    with pytest.raises(ValueError, match="document changed"):
        review.execute(args)
    assert records == []
    assert not list((tmp_path / ".playbook-artifacts/opencode-runs").glob("*/result.json"))


def test_provider_output_limit_is_real_and_rejects_invalid_bounds(monkeypatch):
    captured = []
    class FakeHTTP:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit): return json.dumps(response()).encode()
    def open_fake(request, timeout):
        captured.append(json.loads(request.data))
        return FakeHTTP()
    monkeypatch.setattr(mimo_code_review, "urlopen", open_fake)
    mimo_code_review._call_model(api_key="synthetic-key", base_url="https://opencode.ai/zen/go/v1",
                                model="mimo-v2.6-pro", prompt="synthetic", timeout=30, max_output_tokens=8000)
    assert captured[0]["max_tokens"] == 8000
    with pytest.raises(ValueError):
        mimo_code_review._call_model(api_key="synthetic-key", base_url="https://opencode.ai/zen/go/v1",
                                    model="mimo-v2.6-pro", prompt="synthetic", timeout=30, max_output_tokens=True)
    assert len(captured) == 1


def test_real_pinned_design_record_accepts_non_codex_binding_and_rejects_drift(tmp_path, monkeypatch):
    args, calls, _ = setup_run(tmp_path, monkeypatch)
    from playbook import verified_upstream, ROOT
    sys.path.insert(0, str(verified_upstream(ROOT) / "tools"))
    import feature_design_lib
    import approve_feature_design
    workflow = SimpleNamespace(validate_task_feature_slice_binding=lambda *a, **kw: None,
                               git_commit=lambda root: "a" * 40)
    design = {"schema_version": "playbook.feature_design.v1", "feature_id": "F",
              "status": "draft", "planning_depth": "compact_design", "risk_level": "high",
              "brief_ref": "docs/PROJECT_BRIEF.md", "architecture_refs": [],
              "approval_policy": "human_required", "slices": []}
    folder = tmp_path / "docs/design"
    folder.mkdir(parents=True)
    (folder / "F.md").write_text("# Synthetic design\n")
    registry = folder / "F.design.json"
    registry.write_text(json.dumps(design))
    manifest = [{"path": p.relative_to(tmp_path).as_posix(), "sha256": review.digest(p.read_bytes()),
                 "bytes": len(p.read_bytes())} for p in [folder / "F.md", registry]]
    monkeypatch.setattr(review, "prepare_packet", lambda *args: ("synthetic", manifest, design))
    monkeypatch.setattr(review, "pinned_modules", lambda root: (feature_design_lib, workflow, approve_feature_design))
    assert review.execute(args) == 0
    parsed = approve_feature_design.parse_design_review_record(
        root=tmp_path, feature_id="F", role=args.role, current_design=design, required=True,
    )
    assert parsed["verdict"] == "ADVISORY"
    record = json.loads(approve_feature_design.design_review_record_path(tmp_path, "F", args.role).read_text())
    assert record["reviewer_binding"].startswith("opencode_go:")
    assert "approved_by" not in record
    (folder / "F.md").write_text("# Changed synthetic design\n")
    with pytest.raises(approve_feature_design.ApprovalError, match="Markdown changed"):
        approve_feature_design.parse_design_review_record(
            root=tmp_path, feature_id="F", role=args.role, current_design=design, required=True,
        )


def test_redirect_and_oversized_provider_response_are_denied(monkeypatch):
    with pytest.raises(ValueError, match="redirect_denied"):
        mimo_code_review._NoReviewRedirects().redirect_request(
            None, None, 302, "redirect", {}, "https://foreign.invalid/",
        )
    class Oversized:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit): return b"x" * limit
    monkeypatch.setattr(mimo_code_review, "urlopen", lambda *a, **kw: Oversized())
    with pytest.raises(ValueError, match="response_too_large"):
        mimo_code_review._call_model(api_key="synthetic-key", base_url="https://opencode.ai/zen/go/v1",
                                    model="mimo-v2.6-pro", prompt="synthetic", timeout=30)


def test_provider_failure_diagnostic_never_echoes_exception_content(monkeypatch, capsys):
    def failing(args):
        raise ValueError("synthetic-secret-value-from-provider")
    monkeypatch.setattr(review, "execute", failing)
    assert review.main(["run", "--task", "PAI-01", "--feature-id", "PAI",
                        "--role", "program_design_review"]) == 2
    assert "synthetic-secret-value" not in capsys.readouterr().err


def test_runner_has_no_silent_codex_fallback(monkeypatch):
    # The pinned workflow imports its own same-named module. Load the local
    # entrypoint explicitly so module caching cannot test the wrong runner.
    spec = importlib.util.spec_from_file_location(
        "local_pa_role_runner", Path(__file__).resolve().parents[1] / "tools/run_codex_role.py",
    )
    run_codex_role = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_codex_role)
    calls = []
    monkeypatch.setattr(run_codex_role, "pinned_main", lambda args: calls.append(args) or 0)
    assert run_codex_role.main(["run", "--task", "PAI-01", "--role", "program_design_review"]) == 2
    assert calls == []
    assert run_codex_role.main(["verify", "--result", "historical.json"]) == 0
    assert calls == [["run_codex_role", "verify", "--result", "historical.json"]]


@pytest.mark.parametrize("error_type", ["http", "timeout"])
def test_failed_actual_attempt_keeps_safe_evidence_and_never_publishes_verdict(tmp_path, monkeypatch, error_type):
    from urllib.error import HTTPError
    args, calls, records = setup_run(tmp_path, monkeypatch)
    error = HTTPError("https://opencode.ai/zen/go/v1/chat/completions", 503,
                      "synthetic-secret-value", {}, None) if error_type == "http" else TimeoutError("synthetic-secret-value")
    def failed_provider(**kwargs):
        raise error
    monkeypatch.setattr(mimo_code_review, "_call_model", failed_provider)
    with pytest.raises(type(error)):
        review.execute(args)
    attempt_dirs = list((tmp_path / ".playbook-artifacts/opencode-runs").iterdir())
    assert len(attempt_dirs) == 1
    failure = json.loads((attempt_dirs[0] / "failure.json").read_text())
    assert failure["status"] == "no_valid_verdict"
    assert failure["provider_outcome"] == "unknown"
    assert failure["http_status"] == (503 if error_type == "http" else None)
    assert failure["call_cap"] == 1
    assert "synthetic-secret-value" not in (attempt_dirs[0] / "failure.json").read_text()
    assert records == []
    assert not (attempt_dirs[0] / "result.json").exists()


def test_transport_matches_navigator_two_messages_strict_schema_and_fresh_session(monkeypatch):
    captures = []
    class FakeHTTP:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, limit): return json.dumps(response()).encode()
    def fake_open(request, timeout):
        captures.append((json.loads(request.data), dict(request.header_items()), timeout))
        return FakeHTTP()
    monkeypatch.setattr(mimo_code_review, "urlopen", fake_open)
    for _ in range(2):
        mimo_code_review._call_model(
            api_key="synthetic-key", base_url="https://opencode.ai/zen/go/v1",
            model="mimo-v2.6-pro", prompt="synthetic document", timeout=300,
            max_output_tokens=8000, response_schema=review.VERDICT_SCHEMA,
        )
    body, headers, timeout = captures[0]
    assert [message["role"] for message in body["messages"]] == ["system", "user"]
    assert body["messages"][1]["content"] == "synthetic document"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"] == review.VERDICT_SCHEMA
    assert body["max_tokens"] == 8000 and timeout == 300
    assert "temperature" not in body
    sessions = [next(value for key, value in record[1].items() if key.lower() == "x-opencode-session") for record in captures]
    assert len(set(sessions)) == 2 and all(len(value) == 32 for value in sessions)


def test_json_factoring_preserves_complete_registry_and_literal_references():
    import re
    document = {"rows": [
        {"id": 1, "scope": "a long repeated scope with every requirement", "path": "src/prm/runtime/worker.py"},
        {"id": 2, "scope": "a long repeated scope with every requirement", "path": "src/prm/runtime/worker.py"},
    ], "literal": "$0", "flags": [False, None, 600]}
    packed = review.factor_json(document)
    def decode(node):
        if isinstance(node, str) and re.fullmatch(r"[$][0-9]+", node): return packed["symbols"][node[1:]]
        if isinstance(node, list): return [decode(item) for item in node]
        if isinstance(node, dict) and set(node) == {"$table"}:
            table = node["$table"]
            return [dict(zip(table["columns"], [decode(v) for v in row])) for row in table["rows"]]
        if isinstance(node, dict): return {k: decode(v) for k, v in node.items()}
        return node
    assert decode(packed["document"]) == document


def test_tooling_audit_cannot_create_a_full_design_record(tmp_path, monkeypatch):
    args, calls, records = setup_run(tmp_path, monkeypatch)
    args.tooling_review = True
    assert review.execute(args) == 0
    assert calls[1]["response_schema"] == review.VERDICT_SCHEMA
    assert records == []
    result = json.loads(next((tmp_path / ".playbook-artifacts/opencode-runs").glob("*/result.json")).read_text())
    assert result["review_scope"] == "tooling"


def test_truncated_response_preserves_known_telemetry_without_approval(tmp_path, monkeypatch):
    args, calls, records = setup_run(tmp_path, monkeypatch)
    payload = response()
    payload["choices"][0]["finish_reason"] = "length"
    monkeypatch.setattr(mimo_code_review, "_call_model", lambda **kw: payload)
    with pytest.raises(ValueError, match="incomplete"):
        review.execute(args)
    failure = json.loads(next((tmp_path / ".playbook-artifacts/opencode-runs").glob("*/failure.json")).read_text())
    assert failure["observed_model"] == "mimo-v2.6-pro"
    assert failure["finish_reason"] == "length"
    assert failure["usage"] == payload["usage"]
    assert records == []
