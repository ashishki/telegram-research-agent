from assistant.claim_ledger import build_claim_ledger, claim_ledger_public_summary


def test_claim_ledger_marks_supported_claim_with_citation():
    evidence = [
        {
            "source_url": "https://t.me/source/1",
            "source_group_id": "content_hash:abc",
            "support_span": "RAG evaluation needs claim citations and private failure traces.",
            "freshness_status": "fresh",
        }
    ]

    ledger = build_claim_ledger(
        [{"claim_text": "RAG evaluation needs claim citations.", "source_url": "https://t.me/source/1"}],
        evidence,
    )

    assert ledger["claims"][0]["support_status"] == "supported"
    assert ledger["metrics"]["citation_completeness"] == 1.0
    assert claim_ledger_public_summary(ledger)["supported_claim_rate"] == 1.0


def test_claim_ledger_blocks_current_fact_claims_without_verification():
    ledger = build_claim_ledger(
        [{"claim_text": "Latest price is confirmed.", "claim_type": "source_fact"}],
        [{"source_url": "https://t.me/source/1", "support_span": "old price discussion"}],
        current_fact_required=True,
    )

    assert ledger["claims"][0]["support_status"] == "unsupported"
    assert ledger["metrics"]["current_fact_violations"] == 0
