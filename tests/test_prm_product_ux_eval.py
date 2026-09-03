import importlib.util
from pathlib import Path


def _module(name="prm_product_ux_eval"):
    path = Path(__file__).parents[1] / "tools" / "prm_product_ux_eval.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_product_ux_corpus_is_large_and_covers_unified_bot_surfaces():
    module = _module()
    corpus = module.build_corpus()
    metrics = corpus["metrics"]
    assert metrics["one_turn_cases"] >= 250
    assert metrics["dialogues"] >= 100
    assert metrics["dialogue_turns"] >= 900
    one_turn_surfaces = {case["surface"] for case in corpus["one_turn_cases"]}
    dialogue_surfaces = {
        turn["surface"] for dialogue in corpus["dialogues"] for turn in dialogue["turns"]
    }
    assert {
        "prm_application",
        "utd_ask",
        "utd_onboarding",
        "utd_profile_action",
        "utd_notification",
        "utd_feedback",
    } <= one_turn_surfaces | dialogue_surfaces


def test_product_ux_case_index_windows_dialogues_and_single_turns():
    module = _module("prm_product_ux_eval_index")
    corpus = module.build_corpus()
    with_single = module.build_case_index(
        corpus, include_one_turn_cases=True, dialogue_window_turns=4
    )
    without_single = module.build_case_index(
        corpus, include_one_turn_cases=False, dialogue_window_turns=4
    )
    assert len(with_single) > len(without_single)
    assert len({case["case_id"] for case in with_single}) == len(with_single)
    assert any(case["case_type"] == "dialogue_window" for case in with_single)
    assert any(case["case_type"] == "single_turn" for case in with_single)
    assert any(case.get("setup_turns") for case in without_single)


def test_product_ux_codex_exec_command_is_read_only_ephemeral_and_terra_medium():
    module = _module("prm_product_ux_eval_command")
    command = module.codex_exec_command(
        codex_bin="/usr/bin/codex",
        model="gpt-5.6-terra",
        reasoning_effort="medium",
        schema_path=Path("/tmp/schema.json"),
        output_path=Path("/tmp/result.json"),
        workdir=Path("/tmp/work"),
    )
    assert command[:2] == ["/usr/bin/codex", "exec"]
    assert ["--model", "gpt-5.6-terra"] == command[2:4]
    assert 'model_reasoning_effort="medium"' in command
    assert "--ephemeral" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--output-schema" in command
    assert command[-1] == "-"


def test_product_ux_redacts_provider_payload_surfaces():
    module = _module("prm_product_ux_eval_redact")
    redacted = module.redact_case_for_judge(
        {
            "chat_id": "123456789",
            "text": (
                "token sk-testsecret1234567890 and bot 123456:ABCdefGhijklmnopQRST "
                "https://t.me/private_channel/123 /srv/openclaw-you/workspace/telegram-research-agent/data"
            ),
        }
    )
    rendered = str(redacted)
    assert "123456789" not in rendered
    assert "sk-testsecret" not in rendered
    assert "123456:ABC" not in rendered
    assert "t.me/private_channel" not in rendered
    assert "/srv/openclaw-you" not in rendered


def test_product_ux_simulates_utd_notification_with_feedback_controls():
    module = _module("prm_product_ux_eval_utd_notification")
    turn = {
        "case_id": "notification",
        "surface": "utd_notification",
        "message": "simulated",
        "utd_category": "ai",
        "change_type": "updated",
        "expected": {
            "surface": "utd_notification",
            "utd_category": "ai",
            "notification_has_reason": True,
            "notification_has_source": True,
            "feedback_controls": True,
        },
    }
    result = module.simulate_judge_case(
        {"case_id": "judge:notification", "case_type": "single_turn", "turns": [turn]}
    )
    visible = result["turns"][0]["assistant_visible_message"]
    assert "Почему тебе:" in visible
    assert "Полезно" in visible
    assert "Шум" in visible
    assert result["deterministic_summary"]["failed_turns"] == 0


def test_product_ux_fake_judge_report_records_advisory_metrics(tmp_path):
    module = _module("prm_product_ux_eval_fake_judge")
    case = {
        "case_id": "judge:fake",
        "case_type": "single_turn",
        "deterministic_summary": {"turn_count": 1, "failure_counts": {}},
        "turns": [],
    }

    def fake_judge(case, model, timeout, max_output_tokens, reasoning_effort):
        return {
            "case_id": case["case_id"],
            "status": "judged",
            "verdict": "pass",
            "scores": {field: 5 for field in module.JUDGE_SCORE_FIELDS},
            "would_user_know_next_step": True,
            "lost_context": False,
            "over_answering": False,
            "missing_clarification": False,
            "confusing_controls": False,
            "notification_noise": False,
            "one_bot_fragmentation": False,
            "privacy_boundary_violation": False,
            "unsafe_or_overconfident": False,
            "human_review_required": False,
            "risk_tags": [],
            "summary": "ok",
            "suggested_fix": "",
        }

    report = module.run_judge_sync(
        [case],
        output_path=tmp_path / "report.json",
        dataset_output_path=tmp_path / "dataset.ndjson",
        md_report_path=tmp_path / "report.md",
        provider="codex-exec",
        model="gpt-5.6-terra",
        provider_reasoning_effort="medium",
        allow_provider_egress=True,
        provider_timeout=1,
        max_output_tokens=100,
        quality_floor=4.0,
        case_delay_seconds=0.0,
        progress_every=0,
        partial_every=0,
        abort_provider_failures=1,
        case_selection={"selected_count": 1, "total_built_count": 1},
        corpus_metrics={"one_turn_cases": 1, "dialogues": 0, "dialogue_turns": 0},
        judge_caller=fake_judge,
    )
    assert report["status"] == "pass"
    assert report["provider"] == "codex-exec"
    assert report["model"] == "gpt-5.6-terra"
    assert report["provider_reasoning_effort"] == "medium"
    assert report["metrics"]["judged_count"] == 1
