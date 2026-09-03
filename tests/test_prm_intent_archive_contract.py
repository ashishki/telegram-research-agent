from assistant.archive_relevance import rank_archive_items
from assistant.prm_post_answer_actions import select_post_answer_action_codes
from prm.archive_contract import build_archive_response_contract
from prm.presentation import render_payload
from prm.routing import decide_route

QUERY = "Что в моём архиве есть про agent evals и что из этого реально применимо сейчас?"


def _items():
    return [
        {"archive_document_id": "direct", "posted_at": "2026-08-10", "channel_username": "eval",
         "source_url": "https://t.me/eval/1",
         "snippet": "Agent evaluation measures task success, groundedness, tool-call correctness and regression against gold labels.",
         "matched_query_variant": "agent evals"},
        {"archive_document_id": "adjacent", "posted_at": "2026-08-09", "channel_username": "ops",
         "source_url": "https://t.me/ops/1",
         "snippet": "Agent Operations covers access control and audit trails.",
         "matched_query_variant": "agent operations"},
    ]


def test_archive_query_does_not_route_to_project_decision():
    route = decide_route(QUERY)
    assert route.primary_intent == "archive_to_action"
    assert route.response_contract_id == "archive_research.v2"
    assert route.project_context_required is False
    assert route.decision_requested is False
    assert route.project_name == ""


def test_word_now_alone_does_not_require_external_verification():
    route = decide_route(QUERY)
    assert route.external_verification_required is False
    assert route.reason == "archive_to_action"


def test_archive_practices_question_routes_to_action_research():
    route = decide_route("Что в моём архиве есть про RAG retrieval и какие практики стоит применить?")

    assert route.primary_intent == "archive_to_action"


def test_project_followup_with_unconfigured_project_still_routes_to_project_mapping():
    route = decide_route(
        "В архиве по теме AI adoption. Сопоставь с проектом: "
        "а применимо это к проекту Workflow-to-Agent-Studio?"
    )

    assert route.primary_intent == "project_mapping"
    assert route.project_context_required is True
    assert route.project_name == "Workflow-to-Agent-Studio"


def test_ai_adoption_query_does_not_treat_pet_adoption_as_relevant():
    ranked = rank_archive_items(
        "Что в моём архиве было про AI adoption?",
        [
            {
                "archive_document_id": "pet",
                "snippet": "Vetland Adoption Center helps pets, dogs and cats find families.",
                "matched_query_variant": "AI adoption",
            },
            {
                "archive_document_id": "ai",
                "snippet": "Enterprise AI adoption needs rollout metrics, workflow owners and automation guardrails.",
                "matched_query_variant": "AI adoption",
            },
        ],
    )

    by_id = {item["archive_document_id"]: item for item in ranked}
    assert by_id["pet"]["relevance_label"] == "unrelated"
    assert by_id["pet"]["relevance_reason"] == "non_ai_adoption_context"
    assert by_id["ai"]["relevance_label"] in {"direct", "partial", "adjacent"}


def test_explicit_external_benchmark_routes_to_current_fact():
    route = decide_route("Что сейчас известно про новый внешний benchmark?")
    assert route.primary_intent == "current_fact_verification"
    assert route.external_verification_required is True


def test_mixed_language_agent_evals_query_preserves_english_terms():
    assert decide_route(QUERY).retrieval_query == "agent evals"


def test_direct_eval_match_ranks_above_adjacent_agent_operations():
    ranked = rank_archive_items(QUERY, list(reversed(_items())))
    assert ranked[0]["archive_document_id"] == "direct"
    assert ranked[0]["relevance_label"] == "direct"
    assert ranked[1]["relevance_label"] == "adjacent"


def test_weak_retrieval_reports_no_direct_matches():
    contract = build_archive_response_contract(
        question=QUERY, archive_items=rank_archive_items(QUERY, [_items()[1]]),
        primary_intent="archive_to_action", response_contract_id="archive_research.v2",
    )
    assert contract["result_summary"]["direct_count"] == 0
    assert "Прямых материалов" in contract["direct_answer"]
    assert contract["adjacent_findings"]
    assert all("оценки агентов" not in item for item in contract["limitations"])


def test_archive_answer_does_not_render_decision_risk_template():
    contract = build_archive_response_contract(
        question=QUERY, archive_items=rank_archive_items(QUERY, _items()),
        primary_intent="archive_to_action", response_contract_id="archive_research.v2",
    )
    text = render_payload({"response_contract_id": "archive_research.v2", "archive_contract": contract}, mode="research")
    assert text.startswith("В архиве найдено")
    for forbidden in ("Решение\n", "Контекст проекта", "Главный риск", "Критерий успеха", "backlog"):
        assert forbidden not in text
    assert "Прямые находки" in text
    assert "Смежные материалы" in text
    assert "Что применимо сейчас" in text


def test_direct_only_followup_hides_partial_and_adjacent_materials():
    contract = build_archive_response_contract(
        question="В архиве по теме agent evals. Уточнение: покажи только прямые находки",
        archive_items=rank_archive_items(QUERY, [_items()[1]]),
        primary_intent="archive_lookup",
        response_contract_id="archive_lookup.v2",
    )
    direct_only = __import__("prm.archive_contract", fromlist=["_direct_only_contract"])._direct_only_contract(
        contract,
        question="В архиве по теме agent evals. Уточнение: покажи только прямые находки",
    )
    text = render_payload(
        {"response_contract_id": "archive_lookup.v2", "archive_contract": direct_only},
        mode="research",
    )
    assert "Частичные совпадения" not in text
    assert "Смежные материалы" not in text
    assert "Фильтр direct-only включён" in text


def test_compact_archive_followup_returns_next_step_without_full_source_dump():
    contract = build_archive_response_contract(
        question="В архиве по теме agent evals. Уточнение: коротко: какой следующий шаг?",
        archive_items=rank_archive_items(QUERY, [_items()[1]]),
        primary_intent="archive_lookup",
        response_contract_id="archive_lookup.v2",
    )
    compact = {**contract, "view": {"compact": True}}
    text = render_payload(
        {"response_contract_id": "archive_lookup.v2", "archive_contract": compact},
        mode="research",
    )
    assert text.startswith("Коротко:")
    assert "Следующий шаг:" in text
    assert "Источники" not in text


def test_single_archive_source_is_enough_to_report_archive_presence():
    contract = build_archive_response_contract(
        question=QUERY, archive_items=rank_archive_items(QUERY, [_items()[0]]),
        primary_intent="archive_lookup", response_contract_id="archive_lookup.v2",
    )
    assert contract["answer_status"] == "supported"
    assert contract["result_summary"]["direct_count"] == 1


def test_promotions_and_model_comparisons_do_not_become_actionable_agent_eval_evidence():
    ranked = rank_archive_items(QUERY, [
        {"archive_document_id": "promo", "snippet": "Agent evals, quality gates and tool calling. Промокод AGENT25, регистрация на вебинар.", "matched_query_variant": "agent evals"},
        {"archive_document_id": "event", "snippet": "Переносимый evals harness для агентов в проде. Ведущие эфира расскажут подробнее.", "matched_query_variant": "agent evals"},
        {"archive_document_id": "benchmark", "snippet": "Agentic LLM Benchmark измеряет качество, стоимость и скорость по анализу ошибок агентных архитектур.", "matched_query_variant": "agent evals"},
        {"archive_document_id": "comparison", "snippet": "Сравнение Kimi Agent vs Gemini по метрике дизайна.", "matched_query_variant": "agent evals"},
    ])

    contract = build_archive_response_contract(
        question=QUERY, archive_items=ranked, primary_intent="archive_to_action", response_contract_id="archive_research.v2",
    )

    assert contract["result_summary"]["direct_count"] == 0
    assert contract["result_summary"]["actionable_count"] == 0
    assert contract["applicability"] == []
    assert {item["source_role"] for item in ranked} == {
        "announcement_or_promotion", "benchmark_context", "model_comparison",
    }


def test_telegram_keyboard_depends_on_intent():
    archive_codes = select_post_answer_action_codes({
        "primary_intent": "archive_lookup", "result_summary": {"direct_count": 0, "partial_count": 0, "adjacent_count": 1}
    })
    action_codes = select_post_answer_action_codes({
        "primary_intent": "archive_to_action", "result_summary": {"direct_count": 1, "partial_count": 0, "adjacent_count": 0}
    })
    decision_codes = select_post_answer_action_codes({"primary_intent": "decision_support"})
    assert "e" not in archive_codes and "a" not in archive_codes and "w" not in archive_codes
    assert "q" in archive_codes and "o" in archive_codes
    assert "w" in action_codes
    assert "a" in decision_codes


def test_feedback_actions_are_not_shown_before_relevance_is_established():
    codes = select_post_answer_action_codes({
        "primary_intent": "archive_lookup", "result_summary": {"direct_count": 0, "partial_count": 0, "adjacent_count": 0}
    })
    assert codes == ["u", "m", "x", "q"]


def test_brief_without_relevance_offers_refine_not_save():
    codes = select_post_answer_action_codes({
        "primary_intent": "writer_brief",
        "direct_count": 0,
        "partial_count": 0,
        "adjacent_count": 0,
    })

    assert codes == ["u", "m", "x", "q"]


def test_project_mapping_without_relevance_offers_refine_not_project_save():
    codes = select_post_answer_action_codes({
        "primary_intent": "project_mapping",
        "direct_count": 0,
        "partial_count": 0,
        "adjacent_count": 0,
    })

    assert codes == ["u", "m", "x", "q"]
