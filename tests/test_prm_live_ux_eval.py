import importlib.util
from pathlib import Path


def _module(name="prm_live_ux_eval"):
    path = Path(__file__).parents[1] / "tools" / "prm_live_ux_eval.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_live_ux_eval_generates_100_intent_specific_cases():
    module = _module()
    cases = module.build_cases()
    assert len(cases) == 100
    assert {case["kind"] for case in cases} == {"research", "brief", "decision", "current_fact"}
    assert len({module._case_id(case) for case in cases}) == 100
    first = cases[0]
    assert first["question"] == "Что в моём архиве есть про agent evals и что из этого реально применимо сейчас?"
    assert first["expected_intent"] == "archive_to_action"


def test_live_ux_eval_receipts_are_restricted_to_private_events_dir():
    module = _module("prm_live_ux_eval_path")
    allowed = module.PRIVATE_RECEIPT_ROOT / "prm-live-ux-eval.json"
    assert module._private_receipt_path(allowed) == allowed
    try:
        module._private_receipt_path(Path("/tmp/prm-live-ux-eval.json"))
    except ValueError:
        pass
    else:
        raise AssertionError("non-private receipt path was accepted")


def test_live_ux_eval_detects_irrelevant_decision_template():
    module = _module("prm_live_ux_eval_template")
    assert module._forbidden_template("Главный риск\nКритерий успеха", kind="research") is True
    assert module._forbidden_template("Решение", kind="decision") is False
