from assistant.evidence_quality import build_evidence_quality_items, evidence_quality_summary


def test_evidence_quality_separates_relevance_and_independence():
    items = build_evidence_quality_items(
        [
            {
                "source_url": "https://t.me/channel/10",
                "snippet": "Agent reliability eval harness needs citations and failure traces.",
                "content_hash": "abc123",
                "reaction_count": 1,
            },
            {
                "source_url": "https://github.com/owner/repo",
                "snippet": "README with tests and CI for agent reliability.",
            },
        ],
        question="agent reliability citations",
    )

    assert items[0]["source_class"] == "telegram_commentary"
    assert items[0]["independence"] == "unknown"
    assert items[0]["operator_interest"] == "confirmed_interest"
    assert items[1]["source_class"] == "github_repository"
    assert items[1]["independence"] == "independent"
    assert items[0]["relevance_score"] > 0


def test_evidence_quality_summary_counts_source_groups():
    items = build_evidence_quality_items(
        [
            {"source_url": "https://t.me/channel/10", "snippet": "same", "content_hash": "h1"},
            {"source_url": "https://t.me/channel/11", "snippet": "same copy", "content_hash": "h1"},
        ],
        question="same",
    )

    summary = evidence_quality_summary(items)

    assert summary["evidence_count"] == 2
    assert summary["source_group_count"] == 1
