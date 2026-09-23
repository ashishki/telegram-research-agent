import importlib.util
from pathlib import Path

import pytest


def _module(name="assistant_answer_judge_test"):
    path = Path(__file__).parents[1] / "tools" / "assistant_answer_judge.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _raw(**changes):
    values = {
        "case_id": "archive:agent-evals:1",
        "mode": "archive",
        "user_request": "Что обсуждали про agent evals?",
        "assistant_answer": "Обсуждали метрики и holdout. Источник: https://example.org/post",
        "evidence_refs": ["https://example.org/post"],
    }
    values.update(changes)
    return values


def test_build_case_validates_and_redacts():
    module = _module()
    case = module.build_case(_raw(user_request="напиши на user@example.com"))
    assert case["mode"] == "archive"
    assert "user@example.com" not in case["user_request"]
    assert case["schema_version"] == module.CASE_SCHEMA_VERSION
    with pytest.raises(ValueError):
        module.build_case(_raw(mode="nope"))
    with pytest.raises(ValueError):
        module.build_case(_raw(assistant_answer="  "))


def test_normalize_rescales_and_flags():
    module = _module("assistant_answer_judge_norm")
    ten = module.normalize_answer_judgment(
        "c1", {"verdict": "pass", "scores": {field: 8 for field in module.ANSWER_SCORE_FIELDS}}
    )
    assert all(value == 4 for value in ten["scores"].values())
    assert ten["verdict"] == "pass"

    bad = module.normalize_answer_judgment(
        "c2",
        {
            "verdict": "fail",
            "scores": {field: 5 for field in module.ANSWER_SCORE_FIELDS},
            "invented_deadline": True,
            "risk_tags": ["deadline", "deadline"],
        },
    )
    assert bad["invented_deadline"] is True
    assert bad["risk_tags"] == ["deadline"]
    assert bad["human_review_required"] is True


def test_status_escalates_critical_and_privacy_findings():
    module = _module("assistant_answer_judge_status")
    base = {field: 5 for field in module.ANSWER_SCORE_FIELDS}
    critical = [module.normalize_answer_judgment("c1", {"verdict": "warn", "scores": base, "unsupported_claim": True})]
    status, _, reason = module._status(critical, [], 4.0)
    assert status == "failed_closed"
    assert "unsupported" in reason

    privacy = [
        module.normalize_answer_judgment("c2", {"verdict": "warn", "scores": base, "privacy_boundary_violation": True})
    ]
    status, _, reason = module._status(privacy, [], 4.0)
    assert status == "failed_closed"
    assert "privacy" in reason


def test_run_answer_judge_fails_closed(tmp_path, monkeypatch):
    module = _module("assistant_answer_judge_run")
    case = module.build_case(_raw())
    common = dict(
        model="",
        timeout=5,
        max_output_tokens=200,
        quality_floor=4.0,
        output_path=tmp_path / "r.json",
        dataset_output_path=tmp_path / "d.ndjson",
        md_report_path=tmp_path / "r.md",
        judge_caller=lambda *a: {"case_id": "c", "status": "judged", "verdict": "pass"},
    )
    skipped = module.run_answer_judge([case], provider_egress=False, **common)
    assert skipped["status"] == "skipped_fail_closed"

    for name in ("OPENCODE_API_KEY", "OPENCODE_API_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)
    no_creds = module.run_answer_judge([case], provider_egress=True, **common)
    assert no_creds["judge_status"] == "no_provider_credentials"

    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    judged = module.run_answer_judge([case], provider_egress=True, **common)
    assert judged["metrics"]["judged_count"] == 1
