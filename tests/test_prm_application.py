from types import SimpleNamespace

from prm.application import PersonalResearchAssistant, _final_answer_publication_allowed, _render_verified_evidence_fallback
from assistant.claim_ledger import verify_answer_against_evidence
from prm.contracts import AssistantResult, OperatorRequest
from prm.presentation import render_payload


def _payload():
    return {
        "status": "ok",
        "direct_answer": "В архиве есть подтверждённый сигнал.",
        "answer_gate": {"allow_answer": True, "external_verification_required": False, "current_claim_allowed": True},
        "archive_evidence": {"items": [{
            "archive_document_id": "tg:1", "snippet": "Agent evals use task success and groundedness.",
            "source_url": "https://t.me/example/1", "channel_username": "example", "posted_at": "2026-08-01",
            "matched_query_variant": "agent evals",
        }]},
        "evidence_quality": {"items": [{
            "evidence_id": "e1", "support_span": "Agent evals use task success and groundedness.",
            "source_url": "https://t.me/example/1", "source_group_id": "g1", "freshness_status": "fresh",
            "relevance_label": "direct",
        }]},
        "professional_answer": {"short_answer": "В архиве есть подтверждённый сигнал.", "key_findings": [],
                                "recommended_action": None, "uncertainty": [], "workflow_section": {},
                                "answer_status": "supported", "professional_lens": "neutral",
                                "primary_workflow": "archive_research"},
        "project_fit": {}, "project_decision": {}, "claim_ledger": {"claims": []},
        "unknowns": [], "next_steps": {}, "receipt": {}, "privacy": {},
    }


def test_application_returns_intent_specific_archive_contract(monkeypatch):
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: _payload())
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr("prm.application.synthesize_answer", lambda *args, **kwargs: None)
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"))
    result = assistant.answer(OperatorRequest(
        query="Что в моём архиве есть про agent evals и что из этого реально применимо сейчас?",
        mode="auto",
    ))
    assert isinstance(result, AssistantResult)
    assert result.mode == "research"
    assert result.route["primary_intent"] == "archive_to_action"
    assert result.route["project_context_required"] is False
    assert result.payload["response_contract_id"] == "archive_research.v2"
    assert result.text.startswith("Я не публикую свободный пересказ")
    assert "Agent evals use task success and groundedness." in result.text
    assert "https://t.me/example/1" in result.text
    assert result.payload["final_answer_publication"]["fallback_used"] is True


def test_explicit_topic_edition_is_application_path_without_fetch_send_or_write():
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"))
    result = assistant.render_topic_edition(
        OperatorRequest(query="что нового по AI events", mode="brief"),
        topic_id="ai-events",
        items=[{
            "source": "calendar", "event_id": "42", "url": "https://calendar.utdallas.edu/event/42",
            "title": "AI Career Fair", "updated_at": "2026-09-17T09:30:00Z",
            "material_text": "Registration deadline was moved.",
        }],
        window_start="2026-09-17T00:00:00Z", window_end="2026-09-17T23:59:59Z",
        checked_at="2026-09-17T10:00:00Z", source_health={"calendar": "healthy"},
    )
    assert result.mode == "brief" and "AI Career Fair" in result.text
    assert "Значимость (анализ):" in result.text
    assert result.payload["write_performed"] is False
    assert result.payload["automatic_job_created"] is False
    assert result.payload["notification_sent"] is False
    repeat = assistant.render_topic_edition(
        OperatorRequest(query="что нового по AI events", mode="brief"), topic_id="ai-events",
        items=[{"source":"calendar", "event_id":"42", "url":"https://calendar.utdallas.edu/event/42", "title":"AI Career Fair", "updated_at":"2026-09-17T09:30:00Z"}],
        window_start="2026-09-17T00:00:00Z", window_end="2026-09-17T23:59:59Z", checked_at="2026-09-17T10:00:00Z", source_health={"calendar":"healthy"},
    )
    assert repeat.interaction_id == result.interaction_id


def test_topic_edition_rejects_invalid_window_and_ranks_relevant_events():
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"))
    invalid = assistant.render_topic_edition(OperatorRequest(query="x", mode="brief"), topic_id="x", items=[], window_start="bad", window_end="also-bad", checked_at="2026-09-17T10:00:00Z", source_health={"calendar":"healthy"})
    assert invalid.status == "invalid_edition_window" and "некорректно" in invalid.text and "нет" not in invalid.text
    items = [
        {"source":"calendar", "event_id":"low", "url":"https://calendar.utdallas.edu/low", "title":"Low", "updated_at":"2026-09-17T09:00:00Z", "relevance":{"relevant":True,"score":1,"categories":["career"],"reason":"low"}},
        {"source":"calendar", "event_id":"high", "url":"https://calendar.utdallas.edu/high", "title":"High", "updated_at":"2026-09-17T09:00:00Z", "relevance":{"relevant":True,"score":9,"categories":["ai"],"reason":"high"}},
    ]
    ranked = assistant.render_topic_edition(OperatorRequest(query="x", mode="brief"), topic_id="x", items=items, window_start="2026-09-17T00:00:00Z", window_end="2026-09-17T23:00:00Z", checked_at="2026-09-17T10:00:00Z", source_health={"calendar":"healthy"})
    assert ranked.text.index("High") < ranked.text.index("Low")
    assert "Ai" in ranked.text and "Career" in ranked.text and "https://calendar.utdallas.edu/high" in ranked.text


def test_archive_to_action_uses_bounded_research_plan(monkeypatch):
    payload = _payload()
    payload["archive_candidate_pool"] = [
        {**payload["archive_evidence"]["items"][0], "source_role": "practical_evidence", "supports_action": True,
         "retrieval_mode": "hybrid_fts_vector"},
        {"archive_document_id": "promo", "snippet": "Agent evals webinar registration", "source_url": "https://t.me/example/2", "source_role": "announcement_or_promotion", "supports_action": False},
    ]
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: payload)
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr("prm.application.synthesize_answer", lambda *args, **kwargs: None)
    monkeypatch.setattr("prm.application.plan_archive_evidence", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider-capable planner must remain disabled")))

    result = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:")).answer(OperatorRequest(
        query="Что в моём архиве есть про agent evals и что из этого реально применимо сейчас?",
        mode="auto",
    ))

    assert result.payload["research_plan"]["status"] == "local_planner_disabled"
    assert result.payload["research_plan"]["provider_egress"] is False
    assert result.payload["research_plan"]["gap_check"] == {}


def test_ambiguous_project_clarifies(monkeypatch):
    called = False

    def fail(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("retrieval must not run")

    monkeypatch.setattr("prm.application.answer_memory_research", fail)
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"))
    result = assistant.answer(OperatorRequest(query="Стоит ли добавить это в backlog моего проекта?"))
    assert result.mode == "project_clarify"
    assert "К какому проекту" in result.text
    assert called is False


def test_free_text_memory_action_does_not_run_archive_search_or_write(monkeypatch):
    called = False

    def fail(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("free-text memory action must not run archive search")

    monkeypatch.setattr("prm.application.answer_memory_research", fail)
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"))
    result = assistant.answer(
        OperatorRequest(query="сохрани заметку, но сначала покажи что именно сохранишь")
    )

    assert result.status == "needs_confirmation"
    assert result.route["primary_intent"] == "memory_action"
    assert result.payload["write_performed"] is False
    assert result.payload["answer_gate"]["allow_answer"] is False
    assert "Черновик заметки" in result.text
    assert "запись не создана" in result.text
    assert "Durable запись появится только после отдельного подтверждения" in result.text
    assert called is False


def test_free_text_memory_action_preview_cleans_synthetic_dialog_prefix(monkeypatch):
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not search")))
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"))
    result = assistant.answer(
        OperatorRequest(query="В архиве по теме RAG retrieval. Уточнение: следи за этой темой")
    )

    assert result.status == "needs_confirmation"
    assert "- Тема: RAG retrieval" in result.text
    assert "Уточнение" not in result.text


def test_current_fact_boundary_suppresses_archive_snippets_and_sources(monkeypatch):
    payload = _payload()
    payload["archive_evidence"] = {
        "items": [
            {
                "archive_document_id": "tg:old",
                "snippet": "Old market price from the private archive.",
                "source_url": "https://t.me/archive/old",
                "channel_username": "archive",
                "posted_at": "2026-08-01",
            }
        ]
    }
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: payload)
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr("prm.application.synthesize_answer", lambda *args, **kwargs: None)

    result = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:")).answer(
        OperatorRequest(query="какая текущая цена акций Nvidia сегодня?", mode="auto")
    )

    assert result.route["primary_intent"] == "current_fact_verification"
    assert "Внешняя проверка не запускалась" in result.text
    assert "Следующий шаг" in result.text
    assert "Old market price" not in result.text
    assert "https://t.me/archive/old" not in result.text


def test_current_fact_boundary_precedes_archive_contract_renderer():
    rendered = render_payload(
        {
            "response_contract_id": "archive_research.v2",
            "answer_gate": {"external_verification_required": True, "current_claim_allowed": False},
            "archive_contract": {
                "view": {},
                "direct_answer": "Archive contract would otherwise answer.",
                "result_summary": {"direct_count": 1, "partial_count": 0, "adjacent_count": 0},
                "direct_findings": [{"summary": "Do not show this historical snippet."}],
                "sources": [{"source_url": "https://t.me/archive/1"}],
            },
            "archive_evidence": {"items": [{"snippet": "Do not show this historical snippet."}]},
        },
        mode="research",
    )

    assert rendered.startswith("Я не могу подтвердить актуальный внешний факт")
    assert "Archive contract would otherwise answer" not in rendered
    assert "Do not show this historical snippet" not in rendered
    assert "https://t.me/archive/1" not in rendered


def test_current_fact_publication_predicate_does_not_bypass_an_unsupported_value():
    verification = verify_answer_against_evidence(
        "Текущая цена Nvidia равна 900.",
        [],
        current_fact_required=True,
    )
    assert _final_answer_publication_allowed(
        verification,
        {"external_verification_required": True, "current_claim_allowed": False, "allow_answer": False},
    ) is False


def test_fallback_normalizes_unicode_sentence_boundaries_before_reverification():
    evidence = [{
        "source_url": "https://example.invalid/right",
        "support_span": "Первый факт подтвержден。 Второй факт подтвержден！",
    }]
    fallback = _render_verified_evidence_fallback(evidence)
    verification = verify_answer_against_evidence(fallback, evidence)
    assert "；" not in fallback  # the renderer uses an ASCII separator consistently
    assert "。 " not in fallback
    assert verification["claim_count"] == 1


def test_mixed_fallback_rejects_external_telegram_url_without_archive_provenance():
    rendered = _render_verified_evidence_fallback(
        [{"source_url": "https://t.me/external/7", "support_span": "External Telegram claim."}],
        boundary="Текущий факт требует проверки.",
        local_only=True,
    )

    assert "External Telegram claim" not in rendered


def test_terminal_refusal_is_recognized_as_nonfactual_after_fallback_failure():
    verification = verify_answer_against_evidence(
        "Не удалось собрать проверяемый источник-атрибутированный ответ. Уточни запрос или источник.",
        [],
    )
    assert verification["claim_count"] == 0
    assert _final_answer_publication_allowed(verification, {}) is True


def test_mixed_archive_and_current_question_keeps_archive_part_without_claiming_current_fact(monkeypatch):
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: _payload())
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr("prm.application.synthesize_answer", lambda *args, **kwargs: None)
    result = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:")).answer(
        OperatorRequest(query="Что в моём архиве про agent evals и какая сейчас текущая цена Nvidia?", mode="auto")
    )
    assert result.route["primary_intent"] == "current_fact_verification"
    assert result.payload["answer_gate"]["allow_answer"] is True
    assert result.status == "partial_needs_external_verification"
    assert result.text.startswith("Я не публикую свободный пересказ")
    assert "Agent evals use task success and groundedness." in result.text


def test_explicit_brief_current_fact_is_fail_closed(monkeypatch):
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: _payload())
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: SimpleNamespace())
    result = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:")).answer(
        OperatorRequest(query="какая текущая цена Nvidia сегодня?", mode="brief")
    )
    assert result.status == "needs_external_verification"
    assert "Внешняя проверка не запускалась" in result.text
    assert "Agent evals" not in result.text


def test_explicit_project_name_is_not_replaced_by_downstream_project_fit(monkeypatch):
    payload = _payload()
    payload["project_fit"] = {
        "project_name": "AI_workflow_playbook",
        "relevance_label": "weak_watch",
        "guidance": "Wrong inferred project.",
    }
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: payload)
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr("prm.application.synthesize_answer", lambda *args, **kwargs: None)

    result = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:")).answer(
        OperatorRequest(
            query="В архиве по теме AI adoption. Сопоставь с проектом: а применимо это к проекту Workflow-to-Agent-Studio?",
            mode="auto",
        )
    )

    assert result.route["project_name"] == "Workflow-to-Agent-Studio"
    assert result.payload["project_fit"]["project_name"] == "Workflow-to-Agent-Studio"
    assert "AI_workflow_playbook" in result.payload["project_fit"]["inferred_project_name"]
    assert result.payload["final_answer_publication"]["fallback_used"] is True
