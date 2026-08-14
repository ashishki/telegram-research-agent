import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace


def test_live_ux_eval_generates_a_private_100_case_contract():
    path = Path(__file__).parents[1] / "tools" / "prm_live_ux_eval.py"
    spec = importlib.util.spec_from_file_location("prm_live_ux_eval", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    cases = module.build_cases()

    assert len(cases) == 100
    assert {case["kind"] for case in cases} == {"research", "brief", "decision", "current_fact"}
    assert len({module._case_id(case) for case in cases}) == 100
    assert all("expected" in case and "question" in case for case in cases)


def test_live_ux_eval_receipts_are_restricted_to_private_events_dir():
    path = Path(__file__).parents[1] / "tools" / "prm_live_ux_eval.py"
    spec = importlib.util.spec_from_file_location("prm_live_ux_eval_path", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    allowed = module.PRIVATE_RECEIPT_ROOT / "prm-live-ux-eval.json"
    assert module._private_receipt_path(allowed) == allowed
    try:
        module._private_receipt_path(Path("/tmp/prm-live-ux-eval.json"))
    except ValueError:
        pass
    else:
        raise AssertionError("non-private receipt path was accepted")


def test_live_ux_eval_requires_egress_and_suppresses_usage_with_budget(monkeypatch):
    path = Path(__file__).parents[1] / "tools" / "prm_live_ux_eval.py"
    spec = importlib.util.spec_from_file_location("prm_live_ux_eval_live", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    from llm.client import LLMClient
    import llm.client as llm_client

    observed_suppression = []

    def complete_json(**_kwargs):
        observed_suppression.append(llm_client._usage_recording_suppressed)
        return {"mode": "research", "confidence": 0.9, "reason": "test", "retrieval_query": "eval"}

    def complete_with_receipt(**_kwargs):
        observed_suppression.append(llm_client._usage_recording_suppressed)
        return SimpleNamespace(text='{"score": 5, "clear": true, "action_oriented": true, "grounded": true, "technical_leak": false, "reason": "private text must not persist"}')

    monkeypatch.setenv("PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS", "1")
    monkeypatch.setenv("PRM_TELEGRAM_AUTO_LLM_ROUTER", "1")
    monkeypatch.setattr(LLMClient, "complete_json", staticmethod(complete_json))
    monkeypatch.setattr(LLMClient, "complete_with_receipt", staticmethod(complete_with_receipt))

    receipt = module.run(live=True, case_limit=1, case_offset=0, max_provider_calls=1)

    assert receipt["provider_calls"] == 1
    assert receipt["failure_counts"] == {"judge_error": 1}
    assert observed_suppression == [1]
    assert "private text" not in str(receipt)
    assert LLMClient.complete_json(prompt="", system="", category="", max_tokens=1)["mode"] == "research"


def test_live_ux_eval_main_refuses_live_without_runtime_egress(monkeypatch):
    path = Path(__file__).parents[1] / "tools" / "prm_live_ux_eval.py"
    spec = importlib.util.spec_from_file_location("prm_live_ux_eval_cli", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    monkeypatch.delenv("PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS", raising=False)
    monkeypatch.setattr("sys.argv", ["prm_live_ux_eval.py", "--live", "--confirm-live-eval"])

    try:
        module.main()
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("live eval ran without runtime egress approval")
