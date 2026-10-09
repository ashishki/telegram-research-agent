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
    budget=tmp_path/'docs/verification/PAI-next-review-packets.json';budget.parent.mkdir(parents=True,exist_ok=True)
    budget.write_text(json.dumps({'ongoing_review_budget_authority':{'owner_message':'synthetic authorized scope'},'provider':'opencode_go','model':'mimo-v2.6-pro',
        'per_call_timeout_seconds_maximum':900,'per_call_output_tokens_maximum':16000}))
    design = {"feature_id": "F", "slices": []}
    manifest = [{"path": "design.md", "sha256": review.digest(doc.read_bytes()), "bytes": len(doc.read_bytes())}]
    monkeypatch.setattr(review, "prepare_packet", lambda *args: ("synthetic packet", manifest, design))
    def synthetic_snapshot(root,head,entries):
        for entry in entries:
            if review.digest((root/entry['path']).read_bytes())!=entry['sha256']:
                raise review.ReviewBlocked('review inputs must match captured committed HEAD')
    monkeypatch.setattr(review,'verify_packet_snapshot',synthetic_snapshot)
    calls, records = [], []
    def preflight(*args, **kwargs):
        if planning_block:
            raise SystemExit("planning decision needs_input")
    workflow = SimpleNamespace(validate_task_feature_slice_binding=preflight, git_commit=lambda root: "a" * 40)
    lib = SimpleNamespace(design_hashes=lambda root, design: {"markdown_sha256": "b" * 64, "registry_payload_sha256": "c" * 64},
                          safe_repo_path=lambda root, ref: root / ref)
    approval = SimpleNamespace(write_design_review_record=lambda **kwargs: records.append(kwargs))
    monkeypatch.setattr(review, "pinned_modules", lambda root: (lib, workflow, approval))
    monkeypatch.setattr(review, "require_tooling_audit", lambda root: "synthetic-independent-audit")
    monkeypatch.setattr(mimo_code_review, "_api_key", lambda path: calls.append("key") or "synthetic-key")
    def fake_provider(**kwargs):
        calls.append(kwargs)
        return response()
    monkeypatch.setattr(mimo_code_review, "_call_model", fake_provider)
    args = SimpleNamespace(root=tmp_path, task="T1", feature_id="F", role="program_design_review",
                           model="mimo-v2.6-pro", key_file="", timeout_seconds=30,
                           call_cap=1, allow_provider_egress=True, prepare_only=False)
    return args, calls, records


def select_glm_fixture(root, args=None):
    budget=root/'docs/verification/PAI-next-review-packets.json'
    record=json.loads(budget.read_text());record['model']='glm-5.3'
    record['reviewer_model_authority']={'model':'glm-5.3','provider':'opencode_go',
        'owner_message':'synthetic approved selection','decision_ref':'docs/verification/PAI-reviewer-change-proposal.md'}
    budget.write_text(json.dumps(record))
    if args is not None:args.model='glm-5.3'


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


@pytest.mark.parametrize('reasoning,observed',[(0,'thinking_disabled'),(None,'unknown'),(5,'unknown'),(False,'unknown')])
def test_explicit_review_thinking_mode_requires_actual_telemetry_for_observation(tmp_path,monkeypatch,reasoning,observed):
    args,calls,records=setup_run(tmp_path,monkeypatch);args.thinking_disabled=True
    def provider(**kwargs):
        calls.append(kwargs);payload=response()
        payload['usage']={'prompt_tokens':1,'completion_tokens':1,'total_tokens':2,
            'completion_tokens_details':{'reasoning_tokens':reasoning}}
        return payload
    monkeypatch.setattr(mimo_code_review,'_call_model',provider)
    assert review.execute(args)==0 and calls[1]['thinking_disabled'] is True
    path=next((tmp_path/'.playbook-artifacts/opencode-runs').glob('*/result.json'))
    result=json.loads(path.read_text())
    assert result['requested_effort']=='thinking_disabled' and result['observed_effort']==observed


def test_explicit_thinking_mode_is_sent_once_and_invalid_mode_cannot_call_provider(monkeypatch):
    requests=[]
    class FakeHTTP:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,limit):return json.dumps(response()).encode()
    def fake_open(request,timeout):requests.append(json.loads(request.data));return FakeHTTP()
    monkeypatch.setattr(mimo_code_review,'urlopen',fake_open)
    kwargs={'api_key':'synthetic-key','base_url':'https://opencode.ai/zen/go/v1','model':'mimo-v2.6-pro',
        'prompt':'Synthetic review packet','timeout':30}
    mimo_code_review._call_model(**kwargs,thinking_disabled=True)
    assert requests[0]['thinking']=={'type':'disabled'}
    with pytest.raises(ValueError,match='invalid_review_thinking_mode'):
        mimo_code_review._call_model(**kwargs,thinking_disabled='disabled')
    assert len(requests)==1


@pytest.mark.parametrize('change',['too_many_findings','long_title','long_summary','unknown_field'])
def test_parser_enforces_the_exact_same_provider_json_schema(change):
    payload=response();value=json.loads(payload['choices'][0]['message']['content'])
    finding={'severity':'P2','title':'Synthetic','issue':'Synthetic issue','fix':'Synthetic fix'}
    if change=='too_many_findings':value['findings']=[finding]*13
    elif change=='long_title':value['findings']=[{**finding,'title':'x'*141}]
    elif change=='long_summary':value['summary']='x'*1601
    else:value['extra']='not declared'
    payload['choices'][0]['message']['content']=json.dumps(value)
    with pytest.raises(review.ReviewBlocked,match='invalid verdict schema'):
        review.parse_response(payload,'mimo-v2.6-pro')


def test_real_tooling_packet_manifest_hashes_exact_rendered_sections():
    packet,manifest,_=review.prepare_packet(Path(__file__).resolve().parents[1],'PAI-00','PAI','program_design_review',True,None)
    for entry in manifest:
        section=packet.split('\n--- DOCUMENT: '+entry['path']+' ---\n',1)[1].split('\n--- DOCUMENT:',1)[0]
        assert review.digest(section.encode())==entry['rendered_sha256']
        assert len(section.encode())==entry['rendered_bytes']


@pytest.mark.parametrize("timeout,expected", [(300, 0), (900, 0), (901, 2), (29, 2)])
def test_design_review_deadline_bounds_reach_actual_transport(tmp_path, monkeypatch, timeout, expected):
    _, calls, records = setup_run(tmp_path, monkeypatch)
    assert review.main(["run", "--root", str(tmp_path), "--task", "T1", "--feature-id", "F",
                        "--role", "program_design_review", "--model", "mimo-v2.6-pro", "--allow-provider-egress", "--call-cap", "1",
                        "--timeout-seconds", str(timeout)]) == expected
    if expected == 0:
        assert calls[1]["timeout"] == timeout
        assert len(records) == 1
    else:
        assert calls == [] and records == []


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
    record_path=approve_feature_design.design_review_record_path(tmp_path,'F',args.role)
    original_record=record_path.read_text()
    record_path.write_text(json.dumps({**record,'verdict':'STOP_SHIP'}))
    with pytest.raises(approve_feature_design.ApprovalError,match='STOP_SHIP review blocks approval'):
        approve_feature_design.parse_design_review_record(root=tmp_path,feature_id='F',role=args.role,current_design=design,required=True)
    record_path.write_text(original_record)
    record_path.write_text(json.dumps({**record,'role':'product_design_review'}))
    with pytest.raises(approve_feature_design.ApprovalError):
        approve_feature_design.parse_design_review_record(root=tmp_path,feature_id='F',role=args.role,current_design=design,required=True)
    record_path.write_text(original_record)
    (folder / "F.md").write_text("# Changed synthetic design\n")
    with pytest.raises(approve_feature_design.ApprovalError, match="Markdown changed"):
        approve_feature_design.parse_design_review_record(
            root=tmp_path, feature_id="F", role=args.role, current_design=design, required=True,
        )


def test_cached_gate_module_from_another_path_is_rejected(tmp_path,monkeypatch):
    monkeypatch.setattr(review,'verified_upstream',lambda root:tmp_path)
    with pytest.raises(review.ReviewBlocked,match='pinned gate module import path differs'):
        review.pinned_modules(tmp_path)


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
    ], "literal": "$0", "flags": [False, None, 600],
        "numeric_keys":{"0":"$2","2":{"$0":"$99"}},
        "mixed":[{"a":"$99"},{"b":["$0","$2",{"nested":"$99"}]}]}
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


def test_explicit_design_recheck_output_cap_reaches_provider_and_receipt(tmp_path, monkeypatch):
    args, calls, records = setup_run(tmp_path, monkeypatch)
    args.output_token_cap = 16000
    assert review.execute(args) == 0
    assert calls[1]["max_output_tokens"] == 16000
    result = json.loads(next((tmp_path / ".playbook-artifacts/opencode-runs").glob("*/result.json")).read_text())
    assert result["output_token_cap"] == 16000
    assert records


def test_independent_phase_partition_covers_every_slice_and_spec_section():
    assert {n for group in review.REVIEW_GROUPS.values() for n in group} == set(range(32))
    assert sum(len(group) for group in review.REVIEW_GROUPS.values()) == 32
    assert set().union(*review.SPEC_GROUPS.values()) == set(range(16))


def test_phase_result_never_becomes_full_design_approval(tmp_path, monkeypatch):
    args, calls, records = setup_run(tmp_path, monkeypatch)
    args.slice_group = "foundation"
    assert review.execute(args) == 0
    assert records == []
    result=json.loads(next((tmp_path/".playbook-artifacts/opencode-runs").glob("*/result.json")).read_text())
    assert result["slice_group"] == "foundation"
    assert set(result["reviewed_slice_ids"]) == {f"PAI-{n:02}" for n in range(7)}
    assert result["reviewed_spec_sections"] == sorted(review.SPEC_GROUPS["foundation"])


def test_complete_review_rejects_missing_phases_without_approval(tmp_path, monkeypatch):
    import finalize_opencode_design_reviews as complete
    args, calls, records=setup_run(tmp_path,monkeypatch)
    args.slice_group="foundation"
    assert review.execute(args)==0
    result=next((tmp_path/".playbook-artifacts/opencode-runs").glob("*/result.json"))
    (tmp_path/"docs/design").mkdir(parents=True)
    (tmp_path/"docs/design/F.design.json").write_text(json.dumps({"slices":[{"slice_id":f"PAI-{n:02}"} for n in range(32)]}))
    monkeypatch.setattr(complete,"pinned_modules",review.pinned_modules)
    with pytest.raises(ValueError,match="all four"):
        complete.finalize(tmp_path,"F",args.role,[result])
    assert records==[]


def test_complete_review_requires_all_phases_and_keeps_one_marker(tmp_path, monkeypatch):
    import finalize_opencode_design_reviews as complete
    args, calls, records=setup_run(tmp_path,monkeypatch)
    (tmp_path/"docs/design").mkdir(parents=True)
    (tmp_path/"docs/design/F.design.json").write_text(json.dumps({"slices":[{"slice_id":f"PAI-{n:02}"} for n in range(32)]}))
    results=[]
    for group in review.REVIEW_GROUPS:
        args.slice_group=group
        assert review.execute(args)==0
        results=sorted((tmp_path/".playbook-artifacts/opencode-runs").glob("*/result.json"))
        assert records==[]
    monkeypatch.setattr(complete,"pinned_modules",review.pinned_modules)
    assert complete.finalize(tmp_path,"F",args.role,results)==0
    assert len(records)==1
    assert records[0]["reviewer_binding"].startswith("opencode_go_complete:")
    report=(tmp_path/records[0]["report_path"]).read_text()
    assert report.count("PROGRAM_DESIGN_REVIEW:")==1
    assert len(results)==4


def test_complete_review_rejects_scope_or_head_drift(tmp_path, monkeypatch):
    import finalize_opencode_design_reviews as complete
    args,calls,records=setup_run(tmp_path,monkeypatch)
    args.slice_group="foundation"
    review.execute(args)
    result=next((tmp_path/".playbook-artifacts/opencode-runs").glob("*/result.json"))
    payload=json.loads(result.read_text());payload["reviewed_head"]="f"*40
    result.write_text(json.dumps(payload))
    result.with_suffix(".json.sha256").write_text(review.digest(result.read_bytes()))
    (tmp_path/"docs/design").mkdir(parents=True)
    (tmp_path/"docs/design/F.design.json").write_text(json.dumps({"slices":[{"slice_id":f"PAI-{n:02}"} for n in range(32)]}))
    monkeypatch.setattr(complete,"pinned_modules",review.pinned_modules)
    with pytest.raises(ValueError,match="different HEAD"):
        complete.finalize(tmp_path,"F",args.role,[result])
    assert records==[]


def stream_response(events):
    import io
    class StreamHTTP:
        def __init__(self):
            self.data = io.BytesIO(b''.join(
                b'data: ' + (event.encode() if isinstance(event, str) else json.dumps(event).encode()) + b'\n\n'
                for event in events))
            self.timeouts = []
            self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=SimpleNamespace(settimeout=self.timeouts.append)))
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def readline(self, limit): return self.data.readline(limit)
    return StreamHTTP()


def stream_event(delta=None, finish=None, *, model='mimo-v2.6-pro'):
    return {'model': model, 'choices': [{'index': 0, 'delta': delta or {}, 'finish_reason': finish}]}


def test_stream_preserves_only_final_verdict_and_usage_and_real_wire_bounds(monkeypatch):
    import time
    verdict = response()['choices'][0]['message']['content']
    events = [stream_event({'reasoning_content': 'synthetic hidden reasoning'}),
              stream_event({'content': verdict[:40]}), stream_event({'content': verdict[40:]}),
              stream_event(finish='stop'), {'model': 'mimo-v2.6-pro', 'choices': [],
                                          'usage': {'prompt_tokens': 100, 'completion_tokens': 70}}, '[DONE]']
    wire = stream_response(events)
    captured = []
    def open_fake(request, timeout):
        captured.append(json.loads(request.data))
        return wire
    monkeypatch.setattr(mimo_code_review, 'urlopen', open_fake)
    payload = mimo_code_review._call_model(api_key='synthetic-key', base_url='https://opencode.ai/zen/go/v1',
        model='mimo-v2.6-pro', prompt='synthetic', timeout=900, max_output_tokens=16000, stream=True)
    assert captured[0]['stream'] is True and captured[0]['stream_options'] == {'include_usage': True}
    assert captured[0]['max_tokens'] == 16000
    assert review.parse_response(payload, 'mimo-v2.6-pro')['verdict'] == 'ADVISORY'
    assert payload['usage']['completion_tokens'] == 70
    assert 'hidden reasoning' not in json.dumps(payload)
    assert all(0 < timeout <= 900 for timeout in wire.timeouts)


@pytest.mark.parametrize('events', [
    [stream_event({'content': '{}'}), '[DONE]'],
    [stream_event(finish='stop')],
    [stream_event(model='other-model'), '[DONE]'],
    [stream_event(finish='stop'), stream_event({'content': '{}'}), '[DONE]'],
    [{'error': {'message': 'synthetic-secret'}}],
    [stream_event({'content': 'x' * 70000})],
])
def test_incomplete_or_untrusted_stream_never_becomes_a_verdict(events):
    import time
    with pytest.raises(ValueError):
        mimo_code_review._read_review_stream(stream_response(events), 'mimo-v2.6-pro', time.monotonic() + 900)


def test_stream_total_deadline_expires_even_with_arriving_tokens(monkeypatch):
    wire = stream_response([stream_event({'content': '{}'}), stream_event(finish='stop'), '[DONE]'])
    ticks = iter([0, 5, 31])
    monkeypatch.setattr(mimo_code_review.time, 'monotonic', lambda: next(ticks))
    with pytest.raises(TimeoutError):
        mimo_code_review._read_review_stream(wire, 'mimo-v2.6-pro', 30)
    assert wire.timeouts == [30]


def test_stream_bounds_final_text_separately_from_chunk_envelope():
    import time
    # Legitimate token chunks can exceed the old one-JSON wire envelope.
    event = stream_event({'reasoning_content': 'discarded ' * 3000})
    wire = stream_response([event] * 40 + [stream_event({'content': '{}'}), stream_event(finish='stop'), '[DONE]'])
    assert mimo_code_review._read_review_stream(wire, 'mimo-v2.6-pro', time.monotonic() + 900)['choices'][0]['message']['content'] == '{}'
    for delta, count in [({'content': 'x' * 60000}, 18), ({'reasoning_content': 'x' * 60000}, 140)]:
        with pytest.raises(ValueError, match='review_response_too_large'):
            mimo_code_review._read_review_stream(stream_response([stream_event(delta)] * count), 'mimo-v2.6-pro', time.monotonic() + 900)


def test_stream_failure_preserves_fixed_diagnostic_without_provider_text(tmp_path, monkeypatch):
    args, calls, records = setup_run(tmp_path, monkeypatch)
    def failed_provider(**kwargs): raise ValueError('review_response_too_large')
    monkeypatch.setattr(mimo_code_review, '_call_model', failed_provider)
    with pytest.raises(ValueError): review.execute(args)
    failure = json.loads(next((tmp_path / '.playbook-artifacts/opencode-runs').glob('*/failure.json')).read_text())
    assert failure['error_code'] == 'review_response_too_large'
    assert records == []


def test_stream_terminal_diagnostic_cannot_leak_provider_content(tmp_path, monkeypatch):
    args, calls, records = setup_run(tmp_path, monkeypatch)
    def failed_provider(**kwargs):
        error = ValueError('review_stream_incomplete')
        error.review_stream_state = {'wire_bytes': 1234, 'final_text_bytes': 0,
            'finish_reason': None, 'terminal_event': 'eof',
            'observed_model': 'synthetic-secret', 'reasoning': 'synthetic-secret'}
        raise error
    monkeypatch.setattr(mimo_code_review, '_call_model', failed_provider)
    with pytest.raises(ValueError): review.execute(args)
    raw = next((tmp_path / '.playbook-artifacts/opencode-runs').glob('*/failure.json')).read_text()
    assert 'synthetic-secret' not in raw
    assert json.loads(raw)['stream_state'] == {'wire_bytes': 1234, 'final_text_bytes': 0,
                                               'finish_reason': None, 'terminal_event': 'eof'}
    assert records == []


def test_missing_independent_tooling_audit_denies_before_provider(tmp_path, monkeypatch):
    args, calls, records = setup_run(tmp_path, monkeypatch)
    # Recover the actual function; the common fake-provider fixture represents
    # an already-audited synthetic toolchain for its unrelated contract tests.
    import importlib.util
    spec = importlib.util.spec_from_file_location("fresh_review_gate", review.__file__)
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    monkeypatch.setattr(review, "require_tooling_audit", fresh.require_tooling_audit)
    with pytest.raises(ValueError, match='independent current tooling audit'):
        review.execute(args)
    assert calls == [] and records == []


@pytest.mark.parametrize('model',['mimo-v2.6-pro','glm-5.3'])
def test_real_tooling_gate_rejects_changed_source_and_verdict_disagreement(tmp_path,monkeypatch,model):
    setup_run(tmp_path,monkeypatch)
    if model=='glm-5.3':select_glm_fixture(tmp_path)
    import importlib.util
    spec = importlib.util.spec_from_file_location('fresh_review_gate', review.__file__)
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    module_file=tmp_path/'pinned_gate.py';module_file.write_text('synthetic immutable gate fixture')
    monkeypatch.setattr(fresh,'pinned_modules',lambda root:(SimpleNamespace(__file__=str(module_file)),))
    run = tmp_path / '.playbook-artifacts/opencode-runs/opencode-synthetic'
    run.mkdir(parents=True)
    manifest = []
    for ref in (*fresh.TOOLING_REFS,'docs/ASSISTANT_BOUNDARIES.md','docs/IMPLEMENTATION_CONTRACT.md'):
        path = tmp_path / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('synthetic public toolchain fixture')
        manifest.append({'path': ref, 'sha256': fresh.digest(path.read_bytes())})
    report = run / 'report.md'
    report.write_text('# Independent synthetic audit\n\nPROGRAM_DESIGN_REVIEW: ADVISORY\n\n' + response()['choices'][0]['message']['content'])
    payload = {'review_scope': 'tooling', 'role': 'program_design_review', 'provider': 'opencode_go',
               'read_only': True, 'requested_model': model, 'observed_model': model,
               'verdict': 'ADVISORY', 'documents': manifest, 'report_sha256': fresh.digest(report.read_bytes())}
    payload['pinned_gate_modules']=[{'path':str(module_file),'sha256':fresh.digest(module_file.read_bytes())}]
    payload['runtime_dependencies']=fresh.runtime_dependencies()
    payload.update(task='T1',feature_id='F',generated_at='2026-10-08T12:00:00+00:00',input_sha256=fresh.digest(b'synthetic audit packet'))
    (run/'input_packet.txt').write_text('synthetic audit packet')
    (run/'input_manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(fresh,'prepare_packet',lambda *args:('synthetic audit packet',manifest,{}))
    result = run / 'result.json'
    def write():
        result.write_text(json.dumps(payload))
        result.with_suffix('.json.sha256').write_text(fresh.digest(result.read_bytes()))
    write()
    assert fresh.require_tooling_audit(tmp_path) == result.relative_to(tmp_path).as_posix()
    import shutil
    conflicting=run.parent/'opencode-aaa-newer-stop';shutil.copytree(run,conflicting)
    stopped={**payload,'verdict':'STOP_SHIP','generated_at':'2026-10-08T13:00:00+00:00'}
    stop_report=conflicting/'report.md';stop_body=json.loads(response()['choices'][0]['message']['content']);stop_body['verdict']='STOP_SHIP'
    stop_report.write_text('# Synthetic STOP\n\nPROGRAM_DESIGN_REVIEW: STOP_SHIP\n\n'+json.dumps(stop_body))
    stopped['report_sha256']=fresh.digest(stop_report.read_bytes());stop_result=conflicting/'result.json';stop_result.write_text(json.dumps(stopped));stop_result.with_suffix('.json.sha256').write_text(fresh.digest(stop_result.read_bytes()))
    with pytest.raises(ValueError,match='STOP_SHIP tooling audit'):fresh.require_tooling_audit(tmp_path)
    shutil.rmtree(conflicting)
    module_file.write_text('changed pinned gate')
    with pytest.raises(ValueError):fresh.require_tooling_audit(tmp_path)
    module_file.write_text('synthetic immutable gate fixture')
    target = tmp_path / fresh.TOOLING_REFS[0]
    target.write_text('changed public source')
    with pytest.raises(ValueError): fresh.require_tooling_audit(tmp_path)
    target.write_text('synthetic public toolchain fixture')
    payload['verdict'] = 'PASS'
    write()
    with pytest.raises(ValueError): fresh.require_tooling_audit(tmp_path)


def test_all_phase_packets_keep_complete_canonical_registries():
    for group in review.REVIEW_GROUPS:
        packet, manifest, design = review.prepare_packet(review.ROOT, 'PAI-01', 'PAI', 'program_design_review', slice_group=group)
        assert 'COMPLETE canonical 32-slice registry' in packet
        assert len(design['slices']) == 32
        assert len(packet.encode()) <= review.MAX_INPUT_BYTES
        assert 'test_requirement_academic_01' in packet
        assert 'test_requirement_search_04' in packet


@pytest.mark.parametrize('change', ['scope', 'oversized', 'model', 'truncated', 'critical', 'valid'])
def test_legacy_deep_review_stays_bounded_and_records_observed_identity(tmp_path, monkeypatch, change):
    calls = []
    def git(*args):
        if args[0] == 'rev-parse': return 'a' * 40
        if args[0] == 'diff': return 'x' * 200001 if change == 'oversized' else 'synthetic public diff'
        return 'synthetic commit'
    monkeypatch.setattr(mimo_code_review, '_git', git)
    monkeypatch.setattr(mimo_code_review, '_api_key', lambda path: calls.append('key') or 'synthetic-key')
    verdict = {'verdict': 'SHIP_OK', 'findings': [], 'summary': 'No P0/P1 in the synthetic diff.', 'not_verified': ['live I/O']}
    if change == 'critical': verdict['findings'] = [{'severity': 'P1', 'title': 'Replay'}]
    payload = {'model': 'other-model' if change == 'model' else 'glm-5.3',
        'choices': [{'finish_reason': 'length' if change == 'truncated' else 'stop', 'message': {'content': json.dumps(verdict)}}]}
    monkeypatch.setattr(mimo_code_review, '_call_model', lambda **kwargs: calls.append(kwargs) or payload)
    output = tmp_path / 'deep-review.json'
    args = ['mimo_code_review.py', '--base', 'base', '--out', str(output), '--allow-provider-egress']
    if change != 'scope': args += ['--call-cap', '1']
    monkeypatch.setattr(sys, 'argv', args)
    result = mimo_code_review.main()
    assert result == (0 if change == 'valid' else 1)
    if change in {'scope', 'oversized'}:
        assert calls == []
    else:
        assert calls[1]['max_output_tokens'] == 8000 and calls[1]['stream'] is True
    if change == 'valid':
        report = json.loads(output.read_text())
        assert report['observed_model'] == report['requested_model'] == 'glm-5.3'
        assert report['read_only'] is True and report['cost'] == 'unknown'
    else:
        assert not output.exists() or json.loads(output.read_text()).get('status') != 'reviewed'


def test_phase_receipts_cannot_be_promoted_after_tooling_audit_changes(tmp_path, monkeypatch):
    import finalize_opencode_design_reviews as complete
    args, calls, records = setup_run(tmp_path, monkeypatch)
    (tmp_path / 'docs/design').mkdir(parents=True)
    (tmp_path / 'docs/design/F.design.json').write_text(json.dumps({'slices': [{'slice_id': f'PAI-{n:02}'} for n in range(32)]}))
    for group in review.REVIEW_GROUPS:
        args.slice_group = group
        review.execute(args)
    results = sorted((tmp_path / '.playbook-artifacts/opencode-runs').glob('*/result.json'))
    monkeypatch.setattr(complete, 'pinned_modules', review.pinned_modules)
    monkeypatch.setattr(review, 'require_tooling_audit', lambda root: 'new-independent-audit')
    with pytest.raises(ValueError, match='phase receipts require'):
        complete.finalize(tmp_path, 'F', args.role, results)
    assert records == []


def test_real_committed_snapshot_rejects_dirty_provider_inputs(tmp_path):
    import subprocess
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    doc=tmp_path/'public.md';doc.write_text('public committed source')
    subprocess.run(['git','-C',str(tmp_path),'add','public.md'],check=True)
    subprocess.run(['git','-C',str(tmp_path),'-c','user.name=Synthetic','-c','user.email=synthetic@example.test','commit','-qm','synthetic'],check=True)
    head=subprocess.check_output(['git','-C',str(tmp_path),'rev-parse','HEAD'],text=True).strip()
    manifest=[{'path':'public.md','sha256':review.digest(doc.read_bytes())}]
    review.verify_packet_snapshot(tmp_path,head,manifest)
    doc.write_text('uncommitted replacement')
    with pytest.raises(review.ReviewBlocked,match='captured committed HEAD'):
        review.verify_packet_snapshot(tmp_path,head,[{'path':'public.md','sha256':review.digest(doc.read_bytes())}])


def test_dirty_input_is_denied_before_key_or_provider_lookup(tmp_path,monkeypatch):
    args,calls,records=setup_run(tmp_path,monkeypatch)
    original=review.prepare_packet
    def changing(*params):
        value=original(*params);(tmp_path/'design.md').write_text('changed during packet preparation');return value
    monkeypatch.setattr(review,'prepare_packet',changing)
    with pytest.raises(review.ReviewBlocked,match='captured committed HEAD'):review.execute(args)
    assert calls==[] and records==[]


@pytest.mark.parametrize('content',[('sk-'+'x'*32).encode(),b'Privacy-class: private\nsynthetic restricted fixture'])
def test_restricted_content_source_denied_without_echoing_values(tmp_path,content):
    source=tmp_path/'review.md';source.write_bytes(content)
    with pytest.raises(review.ReviewBlocked,match='restricted review source') as failure:review.read_review_source(source)
    assert content.decode() not in str(failure.value)


def test_hardlinked_review_source_is_denied_before_content_read(tmp_path):
    import os
    source=tmp_path/'source.md';source.write_text('synthetic external source')
    alias=tmp_path/'alias.md';os.link(source,alias)
    with pytest.raises(review.ReviewBlocked,match='linked review source'):review.read_review_source(alias)


def test_complete_review_rejects_rehashed_contradictory_phase_report(tmp_path,monkeypatch):
    import finalize_opencode_design_reviews as complete
    args,calls,records=setup_run(tmp_path,monkeypatch)
    (tmp_path/'docs/design').mkdir(parents=True)
    (tmp_path/'docs/design/F.design.json').write_text(json.dumps({'slices':[{'slice_id':f'PAI-{n:02}'} for n in range(32)]}))
    for group in review.REVIEW_GROUPS:
        args.slice_group=group;assert review.execute(args)==0
    results=sorted((tmp_path/'.playbook-artifacts/opencode-runs').glob('*/result.json'))
    bad=results[0];data=json.loads(bad.read_text());report=bad.parent/'report.md'
    body=json.loads('{'+report.read_text().split('\n{',1)[1])
    body['findings']=[{'severity':'P1','title':'Synthetic blocker','issue':'Synthetic unresolved boundary','fix':'Fix and recheck'}]
    report.write_text('# Synthetic\n\nPROGRAM_DESIGN_REVIEW: ADVISORY\n\n'+json.dumps(body)+'\n')
    data['report_sha256']=review.digest(report.read_bytes());bad.write_text(json.dumps(data));bad.with_suffix('.json.sha256').write_text(review.digest(bad.read_bytes()))
    monkeypatch.setattr(complete,'pinned_modules',review.pinned_modules)
    with pytest.raises(review.ReviewBlocked,match='critical findings'):complete.finalize(tmp_path,'F',args.role,results)
    assert records==[]


def test_legacy_wrapper_only_allows_read_only_help_and_verification(monkeypatch):
    spec=importlib.util.spec_from_file_location('local_role_wrapper',review.ROOT/'tools/run_codex_role.py')
    wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
    calls=[];monkeypatch.setattr(wrapper,'pinned_main',lambda argv:calls.append(argv) or 0)
    for argv in (['run'],['--root','.','run'],['unknown'],[]):assert wrapper.main(argv)==2
    assert calls==[]
    assert wrapper.main(['--help'])==0 and wrapper.main(['verify','--result','synthetic.json'])==0


def test_shared_review_transport_rejects_other_provider_or_model_before_http(monkeypatch):
    calls=[];monkeypatch.setattr(mimo_code_review,'urlopen',lambda *args,**kwargs:calls.append(args))
    for url,model in [('https://other.invalid','mimo-v2.6-pro'),('https://opencode.ai/zen/go/v1','other-model')]:
        with pytest.raises(ValueError,match='authorized_review_provider'):
            mimo_code_review._call_model(api_key='synthetic',base_url=url,model=model,prompt='synthetic',timeout=30)
    assert calls==[]


def test_tooling_scope_cannot_be_promoted_to_complete_design(tmp_path,monkeypatch):
    import finalize_opencode_design_reviews as complete
    args,calls,records=setup_run(tmp_path,monkeypatch)
    (tmp_path/'docs/design').mkdir(parents=True)
    (tmp_path/'docs/design/F.design.json').write_text(json.dumps({'slices':[{'slice_id':f'PAI-{n:02}'} for n in range(32)]}))
    for group in review.REVIEW_GROUPS:
        args.slice_group=group;assert review.execute(args)==0
    results=sorted((tmp_path/'.playbook-artifacts/opencode-runs').glob('*/result.json'))
    bad=results[0];data=json.loads(bad.read_text());data['review_scope']='tooling';bad.write_text(json.dumps(data));bad.with_suffix('.json.sha256').write_text(review.digest(bad.read_bytes()))
    monkeypatch.setattr(complete,'pinned_modules',review.pinned_modules)
    with pytest.raises(review.ReviewBlocked,match='identity/scope'):complete.finalize(tmp_path,'F',args.role,results)
    assert records==[]


def test_extended_review_limits_require_record_before_key_or_http(tmp_path,monkeypatch):
    args,calls,records=setup_run(tmp_path,monkeypatch);args.timeout_seconds=900
    budget=tmp_path/'docs/verification/PAI-next-review-packets.json'
    data=json.loads(budget.read_text());del data['ongoing_review_budget_authority'];budget.write_text(json.dumps(data))
    with pytest.raises(review.ReviewBlocked,match='extended review authority'):review.execute(args)
    assert calls==[] and records==[]


def test_rehashed_packet_cannot_claim_the_original_source_projection(tmp_path,monkeypatch):
    args,calls,records=setup_run(tmp_path,monkeypatch);args.slice_group='foundation';assert review.execute(args)==0
    run=next((tmp_path/'.playbook-artifacts/opencode-runs').glob('*/result.json')).parent
    data=json.loads((run/'result.json').read_text());(run/'input_packet.txt').write_text('different omitted source')
    data['input_sha256']=review.digest((run/'input_packet.txt').read_bytes())
    with pytest.raises(review.ReviewBlocked,match='source projection'):review.verify_stored_packet(tmp_path,data,run)


@pytest.mark.parametrize('change',['absent','renamed','symlink','hardlink'])
def test_snapshot_rejects_untracked_or_linked_equal_content(tmp_path,change):
    import os
    import subprocess
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    doc=tmp_path/'public.md';doc.write_text('synthetic public source')
    subprocess.run(['git','-C',str(tmp_path),'add','public.md'],check=True)
    subprocess.run(['git','-C',str(tmp_path),'-c','user.name=Synthetic','-c','user.email=synthetic@example.test','commit','-qm','synthetic'],check=True)
    head=subprocess.check_output(['git','-C',str(tmp_path),'rev-parse','HEAD'],text=True).strip()
    expected=review.digest(doc.read_bytes())
    if change=='absent':
        doc=tmp_path/'absent.md';doc.write_text('synthetic public source')
    elif change=='renamed':doc=doc.rename(tmp_path/'renamed.md')
    else:
        alias=tmp_path/'alias.md';doc.rename(alias)
        if change=='symlink':doc.symlink_to(alias)
        else:os.link(alias,doc)
    with pytest.raises((review.ReviewBlocked,OSError)):
        review.verify_packet_snapshot(tmp_path,head,[{'path':doc.name,'sha256':expected}])


def test_pai_single_full_run_denied_before_credentials(tmp_path,monkeypatch):
    args,calls,records=setup_run(tmp_path,monkeypatch);args.feature_id='PAI'
    with pytest.raises(review.ReviewBlocked,match='four phase reviews'):
        review.execute(args)
    assert calls==[] and records==[]


@pytest.mark.parametrize('failure',['http','network','timeout'])
def test_deep_review_failure_receipt_is_unknown_and_contains_no_exception_text(tmp_path,monkeypatch,capsys,failure):
    from urllib.error import HTTPError,URLError
    private='synthetic-private-error-body-never-record'
    monkeypatch.setattr(mimo_code_review,'_git',lambda *args:'a'*40 if args[0]=='rev-parse' else 'synthetic public diff')
    monkeypatch.setattr(mimo_code_review,'_api_key',lambda path:'synthetic-key')
    def broken(**kwargs):
        if failure=='http':raise HTTPError('https://example.test',502,private,{},None)
        if failure=='network':raise URLError(private)
        raise TimeoutError(private)
    monkeypatch.setattr(mimo_code_review,'_call_model',broken)
    out=tmp_path/'failure.json'
    monkeypatch.setattr(sys,'argv',['mimo_code_review.py','--base','base','--out',str(out),'--allow-provider-egress','--call-cap','1'])
    assert mimo_code_review.main()==1
    evidence=json.loads(out.read_text())
    assert evidence['provider_outcome']=='unknown' and evidence['usage'] is None
    assert evidence['observed_model'] is None and evidence['provider_call_attempted'] is True
    assert evidence['governed_role_receipt'] is False and evidence['human_authority'] is False
    assert private not in out.read_text()+capsys.readouterr().out


@pytest.mark.parametrize('finish',['none','stop','empty'])
def test_exact_eof_after_complete_json_cannot_publish_native_review(tmp_path,monkeypatch,finish):
    real_model=mimo_code_review._call_model
    args,calls,records=setup_run(tmp_path,monkeypatch)
    monkeypatch.setattr(mimo_code_review,'_call_model',real_model)
    verdict=response()['choices'][0]['message']['content']
    events=[] if finish=='empty' else [stream_event({'content':verdict})]
    if finish=='stop':events.append(stream_event(finish='stop'))
    wire=stream_response(events)
    expected_bytes=len(wire.data.getvalue())
    monkeypatch.setattr(mimo_code_review,'urlopen',lambda request,timeout:wire)
    with pytest.raises(ValueError,match='review_stream_incomplete') as error:
        review.execute(args)
    state=error.value.review_stream_state
    assert state['terminal_event']=='eof' and state['wire_bytes']==expected_bytes
    assert state['finish_reason']==('stop' if finish=='stop' else None)
    assert not list((tmp_path/'.playbook-artifacts/opencode-runs').glob('*/result.json'))
    failure=json.loads(next((tmp_path/'.playbook-artifacts/opencode-runs').glob('*/failure.json')).read_text())
    assert failure['status']=='no_valid_verdict' and failure['provider_outcome']=='unknown'
    assert failure['stream_state']['terminal_event']=='eof' and records==[]


@pytest.mark.parametrize('altered',[False,True])
@pytest.mark.parametrize('model',['mimo-v2.6-pro','glm-5.3'])
def test_four_phase_finalizer_publishes_through_real_pinned_consumer(tmp_path,monkeypatch,altered,model):
    import finalize_opencode_design_reviews as complete
    args,calls,_=setup_run(tmp_path,monkeypatch)
    if model=='glm-5.3':
        select_glm_fixture(tmp_path,args)
        def provider(**kwargs):
            calls.append(kwargs);result=response();result['model']=model;return result
        monkeypatch.setattr(mimo_code_review,'_call_model',provider)
    from playbook import verified_upstream,ROOT
    sys.path.insert(0,str(verified_upstream(ROOT)/'tools'))
    import feature_design_lib
    import approve_feature_design
    workflow=SimpleNamespace(validate_task_feature_slice_binding=lambda *a,**kw:None,git_commit=lambda root:'a'*40)
    design={'schema_version':'playbook.feature_design.v1','feature_id':'F','status':'draft',
        'planning_depth':'compact_design','risk_level':'high','brief_ref':'docs/PROJECT_BRIEF.md',
        'architecture_refs':[],'approval_policy':'human_required','slices':[{'slice_id':f'PAI-{n:02}'} for n in range(32)]}
    folder=tmp_path/'docs/design';folder.mkdir(parents=True)
    (folder/'F.md').write_text('# Synthetic complete-phase design\n')
    (folder/'F.design.json').write_text(json.dumps(design))
    manifest=[{'path':p.relative_to(tmp_path).as_posix(),'sha256':review.digest(p.read_bytes()),'bytes':len(p.read_bytes())} for p in (folder/'F.md',folder/'F.design.json')]
    monkeypatch.setattr(review,'prepare_packet',lambda *args:('synthetic complete packet',manifest,design))
    modules=lambda root:(feature_design_lib,workflow,approve_feature_design)
    monkeypatch.setattr(review,'pinned_modules',modules);monkeypatch.setattr(complete,'pinned_modules',modules)
    for group in review.REVIEW_GROUPS:
        args.slice_group=group;assert review.execute(args)==0
    results=sorted((tmp_path/'.playbook-artifacts/opencode-runs').glob('*/result.json'))
    record_path=approve_feature_design.design_review_record_path(tmp_path,'F',args.role)
    assert len(results)==4 and not record_path.exists()
    if altered:
        results[0].parent.joinpath('report.md').write_text('altered phase report')
        with pytest.raises(review.ReviewBlocked,match='phase report hash changed'):
            complete.finalize(tmp_path,'F',args.role,results)
        assert not record_path.exists() and not (tmp_path/'.playbook-artifacts/opencode-complete').exists()
    else:
        assert complete.finalize(tmp_path,'F',args.role,results)==0
        parsed=approve_feature_design.parse_design_review_record(root=tmp_path,feature_id='F',role=args.role,current_design=design,required=True)
        assert parsed['verdict']=='ADVISORY'
        record=json.loads(record_path.read_text())
        assert record['reviewer_binding'].startswith('opencode_go_complete:') and 'approved_by' not in record
        aggregate=json.loads((tmp_path/record['reviewer_binding'].split(':',1)[1]).read_text())
        assert len(aggregate['parts'])==4 and len(aggregate['coverage']['slices'])==32


@pytest.mark.parametrize('change',['missing_amendment','wrong_provider','wrong_requested','wrong_selection','wrong_observed','thinking_disabled','valid'])
def test_glm_selection_guards_precede_keys_and_exact_identity_controls_publication(tmp_path,monkeypatch,change):
    args,calls,records=setup_run(tmp_path,monkeypatch);select_glm_fixture(tmp_path,args)
    budget=tmp_path/'docs/verification/PAI-next-review-packets.json';data=json.loads(budget.read_text())
    if change=='missing_amendment':del data['reviewer_model_authority']
    if change=='wrong_provider':data['reviewer_model_authority']['provider']='other'
    if change=='wrong_selection':data['model']='mimo-v2.6-pro';args.model='mimo-v2.6-pro'
    budget.write_text(json.dumps(data))
    if change=='wrong_requested':args.model='mimo-v2.6-pro'
    if change=='thinking_disabled':args.thinking_disabled=True
    def provider(**kwargs):
        calls.append(kwargs);result=response();result['model']='mimo-v2.6-pro' if change=='wrong_observed' else 'glm-5.3';return result
    monkeypatch.setattr(mimo_code_review,'_call_model',provider)
    if change=='valid':
        assert review.execute(args)==0
        evidence=json.loads(next((tmp_path/'.playbook-artifacts/opencode-runs').glob('*/result.json')).read_text())
        assert evidence['requested_model']==evidence['observed_model']=='glm-5.3'
        assert evidence['reviewer_model_authority']['authority']['model']=='glm-5.3'
        assert evidence['requested_effort']=='not_requested' and evidence['observed_effort']=='unknown'
        assert calls[1]['thinking_disabled'] is False and len(records)==1
    else:
        with pytest.raises(review.ReviewBlocked):review.execute(args)
        assert records==[] and not list((tmp_path/'.playbook-artifacts/opencode-runs').glob('*/result.json'))
        if change!='wrong_observed':assert calls==[]


def test_glm_transport_keeps_native_metadata_and_omits_mimo_thinking_parameter(monkeypatch):
    captured=[]
    def open_fake(request,timeout):
        captured.append(json.loads(request.data))
        return stream_response([stream_event({'content':response()['choices'][0]['message']['content']},model='glm-5.3'),stream_event(finish='stop',model='glm-5.3'),'[DONE]'])
    monkeypatch.setattr(mimo_code_review,'urlopen',open_fake)
    kwargs={'api_key':'synthetic','base_url':'https://opencode.ai/zen/go/v1','model':'glm-5.3','prompt':'synthetic','timeout':300,'stream':True}
    result=mimo_code_review._call_model(**kwargs)
    assert result['model']=='glm-5.3' and captured[0]['model']=='glm-5.3' and 'thinking' not in captured[0]
    with pytest.raises(ValueError,match='invalid_review_thinking_mode'):
        mimo_code_review._call_model(**kwargs,thinking_disabled=True)
    assert len(captured)==1


@pytest.mark.parametrize('finish', ['stop', 'length'])
def test_glm_max_effort_reaches_wire_and_never_fabricates_observed_effort(tmp_path, monkeypatch, finish):
    real_transport = mimo_code_review._call_model
    args, calls, records = setup_run(tmp_path, monkeypatch)
    select_glm_fixture(tmp_path, args)
    args.reasoning_effort = 'max'
    captured = []
    def open_fake(request, timeout):
        captured.append(json.loads(request.data))
        return stream_response([
            stream_event({'reasoning_content': 'synthetic hidden reasoning'}, model='glm-5.3'),
            stream_event({'content': response()['choices'][0]['message']['content']}, model='glm-5.3'),
            stream_event(finish=finish, model='glm-5.3'), '[DONE]'])
    monkeypatch.setattr(mimo_code_review, 'urlopen', open_fake)
    monkeypatch.setattr(mimo_code_review, '_call_model', real_transport)
    if finish == 'length':
        with pytest.raises(review.ReviewBlocked, match='incomplete reviewer response'):
            review.execute(args)
        evidence = json.loads(next((tmp_path/'.playbook-artifacts/opencode-runs').glob('*/failure.json')).read_text())
        assert records == [] and evidence['finish_reason'] == 'length'
        assert not list((tmp_path/'.playbook-artifacts/opencode-runs').glob('*/result.json'))
    else:
        assert review.execute(args) == 0
        evidence = json.loads(next((tmp_path/'.playbook-artifacts/opencode-runs').glob('*/result.json')).read_text())
        assert evidence['observed_effort'] == 'unknown'
        assert len(records) == 1
    assert evidence['requested_effort'] == 'max'
    assert evidence['observed_model'] == 'glm-5.3'
    assert len(captured) == 1 and captured[0]['reasoning_effort'] == 'max'
    assert 'thinking' not in captured[0]
    assert all('synthetic hidden reasoning' not in p.read_text() for p in (tmp_path/'.playbook-artifacts').rglob('*') if p.is_file())


@pytest.mark.parametrize('effort,model', [('low','glm-5.3'), ('high','glm-5.3'), ('max','mimo-v2.6-pro')])
def test_unrequested_effort_modes_are_denied_before_keys_and_transport(tmp_path, monkeypatch, effort, model):
    real_transport = mimo_code_review._call_model
    args, calls, records = setup_run(tmp_path, monkeypatch)
    if model == 'glm-5.3': select_glm_fixture(tmp_path, args)
    args.reasoning_effort = effort
    with pytest.raises(review.ReviewBlocked, match='reasoning effort outside'):
        review.execute(args)
    assert calls == [] and records == []
    with pytest.raises(ValueError, match='invalid_review_reasoning_effort'):
        real_transport(api_key='synthetic', base_url='https://opencode.ai/zen/go/v1',
            model=model, prompt='synthetic', timeout=30, reasoning_effort=effort)
    assert calls == []


@pytest.mark.parametrize('cap', [64000, 128000, 131072])
@pytest.mark.parametrize('authority', ['old_cap', 'missing_output_authority', 'approved'])
def test_larger_glm_output_needs_separate_authority_before_credentials(tmp_path, monkeypatch, cap, authority):
    args, calls, records = setup_run(tmp_path, monkeypatch)
    select_glm_fixture(tmp_path, args)
    args.output_token_cap = cap
    args.reasoning_effort = 'max'
    budget = tmp_path/'docs/verification/PAI-next-review-packets.json'
    data = json.loads(budget.read_text())
    if authority != 'old_cap': data['per_call_output_tokens_maximum'] = cap
    if authority == 'approved':
        data['per_call_output_authority'] = {'owner_message': 'synthetic explicit cap decision',
            'provider': 'opencode_go', 'model': 'glm-5.3', 'maximum_tokens': cap}
    budget.write_text(json.dumps(data))
    def provider(**kwargs):
        calls.append(kwargs)
        result = response(); result['model'] = 'glm-5.3'; return result
    monkeypatch.setattr(mimo_code_review, '_call_model', provider)
    if authority != 'approved':
        with pytest.raises(review.ReviewBlocked): review.execute(args)
        assert calls == [] and records == []
    else:
        assert review.execute(args) == 0
        assert calls[1]['max_output_tokens'] == cap and calls[1]['reasoning_effort'] == 'max'


@pytest.mark.parametrize('cap', [64000, 131072])
def test_extended_glm_transport_keeps_final_text_and_legacy_bounds(monkeypatch, cap):
    import time
    captured = []
    events = [stream_event({'reasoning_content': 'x' * 60000}, model='glm-5.3')] * 140
    events += [stream_event({'content': '{}'}, model='glm-5.3'), stream_event(finish='stop', model='glm-5.3'), '[DONE]']
    def open_fake(request, timeout):
        captured.append(json.loads(request.data)); return stream_response(events)
    monkeypatch.setattr(mimo_code_review, 'urlopen', open_fake)
    result = mimo_code_review._call_model(api_key='synthetic', base_url='https://opencode.ai/zen/go/v1',
        model='glm-5.3', prompt='synthetic', timeout=900, max_output_tokens=cap, reasoning_effort='max', stream=True)
    assert result['choices'][0]['message']['content'] == '{}'
    assert captured[0]['max_tokens'] == cap and len(captured) == 1
    with pytest.raises(ValueError, match='invalid_review_output_bound'):
        mimo_code_review._call_model(api_key='synthetic', base_url='https://opencode.ai/zen/go/v1',
            model='mimo-v2.6-pro', prompt='synthetic', timeout=900, max_output_tokens=64000)
    with pytest.raises(ValueError, match='review_response_too_large'):
        mimo_code_review._read_review_stream(stream_response(events), 'glm-5.3', time.monotonic() + 900)
    with pytest.raises(ValueError, match='review_response_too_large'):
        mimo_code_review._read_review_stream(stream_response([stream_event({'content': 'x' * 60000}, model='glm-5.3')] * 18),
            'glm-5.3', time.monotonic() + 900, max_wire_bytes=67_108_864)


def test_native_glm_cli_defaults_to_owner_requested_max(tmp_path, monkeypatch):
    _, calls, _ = setup_run(tmp_path, monkeypatch)
    select_glm_fixture(tmp_path)
    def provider(**kwargs):
        calls.append(kwargs); result = response(); result['model'] = 'glm-5.3'; return result
    monkeypatch.setattr(mimo_code_review, '_call_model', provider)
    assert review.main(['run', '--root', str(tmp_path), '--task', 'T1', '--feature-id', 'F',
        '--role', 'program_design_review', '--model', 'glm-5.3', '--allow-provider-egress', '--call-cap', '1']) == 0
    assert calls[1]['reasoning_effort'] == 'max'


@pytest.mark.parametrize('authorized', [False, True])
def test_glm_full_output_deadline_requires_owner_scope(tmp_path, monkeypatch, authorized):
    _, calls, _ = setup_run(tmp_path, monkeypatch); select_glm_fixture(tmp_path)
    path = tmp_path/'docs/verification/PAI-next-review-packets.json'
    data = json.loads(path.read_text())
    if authorized: data['per_call_timeout_seconds_maximum'] = 7200
    path.write_text(json.dumps(data))
    def provider(**kwargs):
        calls.append(kwargs); result = response(); result['model'] = 'glm-5.3'; return result
    monkeypatch.setattr(mimo_code_review, '_call_model', provider)
    assert review.main(['run', '--root', str(tmp_path), '--task', 'T1', '--feature-id', 'F',
        '--role', 'program_design_review', '--model', 'glm-5.3', '--timeout-seconds', '7200',
        '--allow-provider-egress', '--call-cap', '1']) == (0 if authorized else 2)
    if authorized: assert calls[1]['timeout'] == 7200 and calls[1]['reasoning_effort'] == 'max'
    else: assert calls == []


@pytest.mark.parametrize('scope', ['missing', 'mimo', 'approved'])
def test_large_complete_packet_needs_owner_scope_before_keys(tmp_path, monkeypatch, scope):
    args,calls,records=setup_run(tmp_path,monkeypatch)
    if scope != 'mimo':select_glm_fixture(tmp_path,args)
    original=review.prepare_packet
    def packet(*arguments):
        _,manifest,design=original(*arguments);return 'synthetic ' * 21000,manifest,design
    monkeypatch.setattr(review,'prepare_packet',packet)
    path=tmp_path/'docs/verification/PAI-next-review-packets.json';data=json.loads(path.read_text())
    if scope != 'missing':data['per_call_input_authority']={'owner_message':'synthetic maximum instruction','provider':'opencode_go','model':args.model,'maximum_bytes':1000000}
    path.write_text(json.dumps(data))
    def provider(**kwargs):
        calls.append(kwargs);payload=response();payload['model']=args.model;return payload
    monkeypatch.setattr(mimo_code_review,'_call_model',provider)
    if scope == 'approved':
        assert review.execute(args)==0 and len(calls[1]['prompt'].encode())>200000
        evidence=json.loads(next((tmp_path/'.playbook-artifacts/opencode-runs').glob('*/attempt.json')).read_text())
        assert evidence['input_authority']['authority']['maximum_bytes']==1000000
    else:
        with pytest.raises(review.ReviewBlocked,match='larger input'):review.execute(args)
        assert calls==[] and records==[]


@pytest.mark.parametrize('mixed',[False,True])
def test_glm_complete_record_requires_four_same_model_parts(tmp_path,monkeypatch,mixed):
    import finalize_opencode_design_reviews as complete
    args,calls,records=setup_run(tmp_path,monkeypatch);select_glm_fixture(tmp_path,args)
    def provider(**kwargs):
        calls.append(kwargs);result=response();result['model']='glm-5.3';return result
    monkeypatch.setattr(mimo_code_review,'_call_model',provider)
    (tmp_path/'docs/design').mkdir(parents=True)
    (tmp_path/'docs/design/F.design.json').write_text(json.dumps({'slices':[{'slice_id':f'PAI-{n:02}'} for n in range(32)]}))
    for group in review.REVIEW_GROUPS:
        args.slice_group=group;assert review.execute(args)==0
    results=sorted((tmp_path/'.playbook-artifacts/opencode-runs').glob('*/result.json'))
    monkeypatch.setattr(complete,'pinned_modules',review.pinned_modules)
    if mixed:
        bad=results[0];data=json.loads(bad.read_text());data.update(requested_model='mimo-v2.6-pro',observed_model='mimo-v2.6-pro');bad.write_text(json.dumps(data));bad.with_suffix('.json.sha256').write_text(review.digest(bad.read_bytes()))
        with pytest.raises(review.ReviewBlocked,match='identity/scope'):
            complete.finalize(tmp_path,'F',args.role,results)
        assert records==[] and not (tmp_path/'.playbook-artifacts/opencode-complete').exists()
    else:
        assert complete.finalize(tmp_path,'F',args.role,results)==0
        aggregate=json.loads(next((tmp_path/'.playbook-artifacts/opencode-complete').glob('*/result.json')).read_text())
        assert aggregate['requested_model']==aggregate['observed_model']=='glm-5.3'
        assert len(aggregate['parts'])==4 and len(records)==1
