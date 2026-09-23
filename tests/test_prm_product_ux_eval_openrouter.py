import importlib.util
from pathlib import Path


def _module(name="prm_product_ux_eval_opencode"):
    path = Path(__file__).parents[1] / "tools" / "prm_product_ux_eval.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _case():
    return {
        "case_id": "case-1",
        "surface": "prm_application",
        "deterministic_summary": {"turn_count": 1, "failure_codes": []},
    }


def test_opencode_api_key_prefers_explicit_file_over_env(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setenv("OPENCODE_API_KEY", "env-key")
    monkeypatch.delenv("OPENCODE_API_KEY_FILE", raising=False)
    assert module._opencode_api_key() == "env-key"

    key_file = tmp_path / "opencode.key"
    key_file.write_text("file-key\n", encoding="utf-8")
    monkeypatch.setenv("OPENCODE_API_KEY_FILE", str(key_file))
    assert module._opencode_api_key() == "file-key"

    monkeypatch.setenv("OPENCODE_API_KEY_FILE", str(tmp_path / "missing.key"))
    assert module._opencode_api_key() == "env-key"

    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.setenv("OPENCODE_API_KEY_FILE", str(tmp_path / "missing.key"))
    assert module._opencode_api_key() == ""


def test_opencode_api_key_never_uses_openrouter_env(monkeypatch):
    module = _module("prm_product_ux_eval_or_wronghost")
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.delenv("OPENCODE_API_KEY_FILE", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-wrong-host")
    monkeypatch.setenv("OPENROUTER_API_KEY_FILE", "/tmp/opencode/does-not-exist")
    assert module._opencode_api_key() == ""


def test_call_openai_compatible_json_fails_closed_without_key(monkeypatch):
    module = _module("prm_product_ux_eval_or_nokey")
    for name in (
        "OPENCODE_API_KEY",
        "OPENCODE_API_KEY_FILE",
        "OPENROUTER_API_KEY",
        "OPENROUTER_API_KEY_FILE",
    ):
        monkeypatch.delenv(name, raising=False)
    result = module.call_openai_compatible_json(
        prompt="judge",
        payload={"case": {}},
        model="mimo-v2.6-pro",
        timeout=5,
        max_output_tokens=300,
    )
    assert result == {"status": "provider_error", "error": "missing_api_key"}


def test_chat_completion_text_accepts_string_and_block_content():
    module = _module("prm_product_ux_eval_or_text")
    assert module._chat_completion_text(
        {"choices": [{"message": {"content": "{}"}}]}
    ) == "{}"
    assert (
        module._chat_completion_text(
            {"choices": [{"message": {"content": [{"text": "{"}, {"text": "}"}]}}]}
        )
        == "{}"
    )
    assert module._chat_completion_text({"choices": []}) is None


def test_judge_one_case_opencode_normalizes_provider_json(monkeypatch):
    module = _module("prm_product_ux_eval_or_normalize")
    verdict = {
        "verdict": "pass",
        "scores": {field: 5 for field in module.JUDGE_SCORE_FIELDS},
        "would_user_know_next_step": True,
        "privacy_boundary_violation": False,
        "unsafe_or_overconfident": False,
        "human_review_required": False,
        "risk_tags": [],
        "summary": "ok",
        "suggested_fix": "",
    }
    monkeypatch.setattr(
        module,
        "call_openai_compatible_json",
        lambda **_: {"status": "ok", "json": verdict},
    )
    result = module.judge_one_case_opencode(_case(), "mimo-v2.6-pro", 5, 300, "medium")
    assert result["status"] == "judged"
    assert result["verdict"] == "pass"
    assert result["case_id"] == "case-1"


def test_run_judge_sync_opencode_defaults_model_and_fails_closed(tmp_path, monkeypatch):
    module = _module("prm_product_ux_eval_or_run")
    common = dict(
        output_path=tmp_path / "report.json",
        dataset_output_path=tmp_path / "dataset.ndjson",
        md_report_path=tmp_path / "report.md",
        provider="opencode-go",
        model="",
        provider_reasoning_effort="medium",
        provider_timeout=5,
        max_output_tokens=300,
        quality_floor=4.0,
        case_delay_seconds=0.0,
        progress_every=0,
        partial_every=0,
        abort_provider_failures=1,
        case_selection={"selected_count": 1, "total_built_count": 1},
        corpus_metrics={"one_turn_cases": 1, "dialogues": 0, "dialogue_turns": 0},
    )

    for name in (
        "OPENCODE_API_KEY",
        "OPENCODE_API_KEY_FILE",
        "OPENROUTER_API_KEY",
        "OPENROUTER_API_KEY_FILE",
    ):
        monkeypatch.delenv(name, raising=False)
    skipped = module.run_judge_sync(
        [_case()], allow_provider_egress=True, judge_caller=lambda *a: {}, **common
    )
    assert skipped["status"] == "skipped_fail_closed"
    assert skipped["judge_status"] == "no_provider_credentials"

    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    seen = {}

    def fake_judge(case, model, timeout, max_output_tokens, reasoning_effort):
        seen["model"] = model
        return module.normalize_judgment(case["case_id"], {"verdict": "warn", "scores": {}})

    report = module.run_judge_sync(
        [_case()], allow_provider_egress=True, judge_caller=fake_judge, **common
    )
    assert seen["model"] == module.DEFAULT_OPENCODE_MODEL
    assert report["provider"] == "opencode-go"
    assert report["model"] == module.DEFAULT_OPENCODE_MODEL
    assert report["provider_egress_allowed"] is True


def test_default_caller_dispatch_reaches_opencode_transport(tmp_path, monkeypatch):
    module = _module("prm_product_ux_eval_or_dispatch")
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    seen = {}

    def fake_call(**kwargs):
        seen["model"] = kwargs["model"]
        return {
            "status": "ok",
            "json": {
                "verdict": "warn",
                "scores": {field: 3 for field in module.JUDGE_SCORE_FIELDS},
                "summary": "ok",
            },
        }

    monkeypatch.setattr(module, "call_openai_compatible_json", fake_call)
    report = module.run_judge_sync(
        [_case()],
        output_path=tmp_path / "r.json",
        dataset_output_path=tmp_path / "d.ndjson",
        md_report_path=tmp_path / "r.md",
        provider="opencode-go",
        model="",
        provider_reasoning_effort="medium",
        allow_provider_egress=True,
        provider_timeout=5,
        max_output_tokens=300,
        quality_floor=4.0,
        case_delay_seconds=0.0,
        progress_every=0,
        partial_every=0,
        abort_provider_failures=1,
        case_selection={"selected_count": 1, "total_built_count": 1},
        corpus_metrics={"one_turn_cases": 1, "dialogues": 0, "dialogue_turns": 0},
    )
    assert seen["model"] == module.DEFAULT_OPENCODE_MODEL
    assert report["metrics"]["judged_count"] == 1


def test_openrouter_alias_uses_opencode_defaults(tmp_path, monkeypatch):
    module = _module("prm_product_ux_eval_or_alias")
    assert "openrouter" in module.OPENCODE_JUDGE_PROVIDERS
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    seen = {}

    def fake_judge(case, model, timeout, max_output_tokens, reasoning_effort):
        seen["model"] = model
        return module.normalize_judgment(case["case_id"], {"verdict": "warn", "scores": {}})

    report = module.run_judge_sync(
        [_case()],
        output_path=tmp_path / "r.json",
        dataset_output_path=tmp_path / "d.ndjson",
        md_report_path=tmp_path / "r.md",
        provider="openrouter",
        model="",
        provider_reasoning_effort="medium",
        allow_provider_egress=True,
        provider_timeout=5,
        max_output_tokens=300,
        quality_floor=4.0,
        case_delay_seconds=0.0,
        progress_every=0,
        partial_every=0,
        abort_provider_failures=1,
        case_selection={"selected_count": 1, "total_built_count": 1},
        corpus_metrics={"one_turn_cases": 1, "dialogues": 0, "dialogue_turns": 0},
        judge_caller=fake_judge,
    )
    assert seen["model"] == module.DEFAULT_OPENCODE_MODEL
    assert report["provider"] == "openrouter"
