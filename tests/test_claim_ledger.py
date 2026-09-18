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


def test_final_verification_does_not_replace_a_wrong_visible_citation():
    evidence = [{
        "evidence_id": "right", "source_url": "https://example.invalid/right",
        "support_span": "Orion service does not retain private messages and costs 20 dollars per month.",
    }]
    verification = verify_answer_against_evidence(
        "Orion service does not retain private messages and costs 20 dollars per month.\nИсточник: https://example.invalid/wrong",
        evidence,
    )
    claim = verification["claims"][0]
    assert claim["support_status"] == "unsupported"
    assert claim["evidence_refs"] == ["https://example.invalid/wrong"]
    assert verification["metrics"]["citation_integrity"] == 0.0


def test_final_verification_covers_the_eleventh_claim_and_marks_tail_when_bounded():
    evidence = [{"source_url": "https://example.invalid/a", "support_span": "Fact one is fully supported."}]
    answer = " ".join(["Fact one is fully supported."] * 10 + ["Fact eleven is fully invented."])
    verification = verify_answer_against_evidence(answer, evidence, max_claims=10)
    assert verification["candidate_claim_count"] == 2  # identical claims are deduplicated

    labels = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda".split())
    unique_answer = " ".join([f"Fact {label} is fully supported." for label in labels])
    verification = verify_answer_against_evidence(unique_answer, evidence, max_claims=10)
    assert verification["verification_complete"] is False
    assert verification["metrics"]["unverified_tail_claim_count"] == 1


def test_critical_number_negation_and_actor_mutations_are_not_supported():
    evidence = [{"source_url": "https://example.invalid/a", "support_span": "Orion service does not retain private messages and costs 20 dollars per month."}]
    for mutated in (
        "Orion service does not retain private messages and costs 900 dollars per month.",
        "Orion service retains private messages and costs 20 dollars per month.",
        "Nova service does not retain private messages and costs 20 dollars per month.",
    ):
        claim = build_claim_ledger([mutated], evidence)["claims"][0]
        assert claim["support_status"] == "unsupported"


def test_cyrillic_actor_mutation_and_existing_irrelevant_citation_do_not_pass():
    evidence = [
        {"source_url": "https://example.invalid/right", "support_span": "Сервис Альфа не хранит личные сообщения."},
        {"source_url": "https://example.invalid/other", "support_span": "Сервис Гамма публикует еженедельный дайджест."},
    ]
    mutated = build_claim_ledger(["Сервис Бета не хранит личные сообщения."], evidence)["claims"][0]
    assert mutated["support_status"] == "unsupported"
    lowercase_mutated = build_claim_ledger(["Сервис бета не хранит личные сообщения."], evidence)["claims"][0]
    assert lowercase_mutated["support_status"] == "unsupported"
    verification = verify_answer_against_evidence(
        "Сервис Альфа не хранит личные сообщения. Источник: https://example.invalid/right https://example.invalid/other",
        evidence,
    )
    assert verification["claims"][0]["support_status"] == "unsupported"
    assert verification["metrics"]["citation_integrity"] == 0.0


def test_supported_final_claim_without_displayed_source_has_no_citation_integrity_pass():
    evidence = [{"source_url": "https://example.invalid/right", "support_span": "Orion service costs 20 dollars."}]
    verification = verify_answer_against_evidence("Orion service costs 20 dollars.", evidence)
    assert verification["claims"][0]["support_status"] == "supported"
    assert verification["claims"][0]["evidence_refs"] == []
    assert verification["metrics"]["citation_integrity"] == 0.0


def test_detached_source_inventory_does_not_bind_to_previous_claim():
    evidence = [{"source_url": "https://example.invalid/right", "support_span": "Orion service costs 20 dollars."}]
    verification = verify_answer_against_evidence(
        "Orion service costs 20 dollars.\nИсточники\n- 2026-09-17 @channel: https://example.invalid/right", evidence
    )
    assert verification["claims"][0]["evidence_refs"] == []


def test_boundary_keywords_do_not_reclassify_a_current_value_as_safe():
    for unsafe in (
        "Внешняя проверка показала, что текущая цена Nvidia — 900.",
        "Что известно сейчас: текущая цена Nvidia — 900.",
        "Следующий шаг: текущая цена Nvidia — 900.",
    ):
        verification = verify_answer_against_evidence(unsafe, [], current_fact_required=True)
        assert verification["claims"][0]["claim_type"] == "source_fact"
        assert verification["claims"][0]["support_status"] == "unsupported"
