from tools.prm_qa_usage_recap import summarize_receipts


def test_usage_recap_summary_is_aggregate_only():
    summary = summarize_receipts(
        [
            {"job_type": "semantic_topic", "workflow": "archive_research", "feedback": {"label": "useful"}},
            {"job_type": "comparison", "workflow": "archive_research", "feedback": {"label": "miss"}},
        ]
    )

    assert summary["receipt_count"] == 2
    assert summary["useful_rate"] == 0.5
    assert summary["privacy"]["public_summary_contains_questions"] is False
    assert "question" not in summary
