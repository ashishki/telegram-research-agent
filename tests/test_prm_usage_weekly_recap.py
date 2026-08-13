import pytest

from output.prm_usage_weekly_recap import PRMUsageWeeklyRecapError, build_prm_usage_weekly_recap


def test_recap_uses_usage_receipts_not_report_v2():
    result = build_prm_usage_weekly_recap(
        {
            "usage_receipts": [{"useful": "yes", "selected_project": "PRM"}],
            "confirmed_memory_events": [{"proposal_type": "action", "title": "Проверить eval fixture"}],
        }
    )

    assert result["status"] == "usage_evidence"
    assert result["usage_receipt_count"] == 1
    assert result["legacy_report_inputs_used"] is False
    assert result["write_performed"] is False


def test_recap_contract():
    result = build_prm_usage_weekly_recap(
        {
            "usage_receipts": [{"useful": "partial", "selected_project": "PRM"}],
            "reaction_summary": [{"count": 3}],
        }
    )

    assert result["main_change"]
    assert result["action_study_watch_ignore"]
    assert result["reaction_processing_summary"] == "Обработано реакций: 3."
    assert result["project_connection"] == "PRM"
    assert result["feedback_request"]


def test_recap_requires_usage_evidence():
    with pytest.raises(PRMUsageWeeklyRecapError, match="usage evidence"):
        build_prm_usage_weekly_recap({})

    preview = build_prm_usage_weekly_recap({"fixture_preview_approved": True})
    assert preview["status"] == "fixture_preview"
