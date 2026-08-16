from assistant.claim_ledger import (
    build_claim_ledger,
    build_candidate_claims_from_evidence,
    claim_ledger_public_summary,
    verify_answer_against_evidence,
)


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


def test_final_answer_verification_extracts_claims_from_answer_not_support_span():
    evidence = [
        {
            "evidence_id": "e1",
            "source_url": "https://t.me/source/1",
            "source_group_id": "content_hash:abc",
            "support_span": "RAG evaluation needs claim citations and private failure traces.",
            "freshness_status": "fresh",
        }
    ]

    verification = verify_answer_against_evidence(
        "Короткий вывод: RAG evaluation needs claim citations. Источник: https://t.me/source/1",
        evidence,
    )

    assert verification["claim_extraction_source"] == "rendered_final_answer"
    assert verification["claims"][0]["claim_text"] != evidence[0]["support_span"]
    assert verification["claims"][0]["exact_evidence_snippets"][0]["support_span"] == evidence[0]["support_span"]
    assert verification["claims"][0]["entailment_verdict"] == "entailed"


def test_candidate_claim_ledger_is_pre_synthesis_evidence_derived():
    evidence = [
        {
            "evidence_id": "e1",
            "source_url": "https://t.me/source/1",
            "support_span": "Evaluation quality improves when answer claims are checked.",
        }
    ]

    candidates = build_candidate_claims_from_evidence(evidence)

    assert candidates == [
        {
            "claim_text": "Evaluation quality improves when answer claims are checked.",
            "claim_type": "source_fact",
            "source_url": "https://t.me/source/1",
            "evidence_id": "e1",
        }
    ]
