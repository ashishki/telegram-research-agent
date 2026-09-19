from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from assistant.claim_ledger import verify_answer_against_evidence
from prm.application import (
    PersonalResearchAssistant,
    _final_answer_publication_allowed,
    _render_terminal_empty_answer,
    _render_verified_evidence_fallback,
)
from prm.archive_synthesis_transport import (
    ArchiveSynthesisReceipt,
    ArchiveSynthesisTransportResult,
    _openai_connection_ref,
)
from prm.capabilities import AuthorizationRequest, CapabilityGrant, CapabilityRegistry, ProviderPolicy
from prm.contracts import ArchiveSynthesisAccess, AssistantResult, OperatorRequest
from prm.presentation import render_payload
from prm.synthesis import ArchiveSynthesisOutcome


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
            "evidence_id": "tg:1", "support_span": "Agent evals use task success and groundedness.",
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


class _ArchiveHoldoutFacade:
    """Representative offline archive corpus; the production retriever ranks it."""

    def __init__(self, items):
        self.items = list(items)
        self.archive_queries = []

    def search_telegram_archive(self, query, filters=None, limit=5):
        self.archive_queries.append((query, dict(filters or {}), limit))
        return {
            "status": "ok" if self.items else "insufficient_evidence",
            "query": query,
            "retrieval_mode": "sqlite_fts_archive",
            "items": self.items[:limit],
        }

    def search_intelligence_items(self, query, filters=None, limit=5):
        return {"status": "empty", "query": query, "items": []}

    def analyze_project_context(self, query, project_name=None, week_label=None, limit=5):
        return {
            "status": "empty",
            "query": query,
            "project_name": project_name or "",
            "relevance_label": "no_match",
            "source_refs": [],
            "unknowns": [],
            "decision_support": {},
        }


def _archive_synthesis_access() -> ArchiveSynthesisAccess:
    now = datetime.now(timezone.utc)
    connection_ref = _openai_connection_ref("synthetic-pa04-holdout-key")
    assert connection_ref is not None
    text = CapabilityGrant(
        grant_id="grant_pa04_holdout_text",
        owner_ref="owner_pa04_holdout",
        connection_ref=connection_ref,
        capability="model.generate",
        resource_refs=("resource_conversation",),
        operations=("model_egress",),
        data_classes=("user_provided",),
        purpose="answer.request",
        provider_policy=ProviderPolicy(("provider_openai",), maximum_request_count=2),
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=5),
        revision=1,
    )
    context = CapabilityGrant(
        grant_id="grant_pa04_holdout_context",
        owner_ref=text.owner_ref,
        connection_ref=connection_ref,
        capability="model.context_egress",
        resource_refs=("resource_archive",),
        operations=("model_egress",),
        data_classes=("private_archive",),
        purpose="answer.context",
        provider_policy=ProviderPolicy(("provider_openai",), maximum_request_count=2),
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=5),
        revision=1,
    )
    registry = CapabilityRegistry((text, context))
    operation_ref = "operation_pa04_holdout"
    query = registry.authorize_and_reserve(AuthorizationRequest(
        owner_ref=text.owner_ref,
        connection_ref=connection_ref,
        capability="model.generate",
        resource_ref="resource_conversation",
        operation="model_egress",
        data_class="user_provided",
        provider_ref="provider_openai",
        purpose="answer.request",
        expected_grant_revision=1,
        operation_ref=operation_ref,
    ))
    archive = registry.authorize_and_reserve(AuthorizationRequest(
        owner_ref=text.owner_ref,
        connection_ref=connection_ref,
        capability="model.context_egress",
        resource_ref="resource_archive",
        operation="model_egress",
        data_class="private_archive",
        provider_ref="provider_openai",
        purpose="answer.context",
        expected_grant_revision=1,
        operation_ref=operation_ref,
    ))
    return ArchiveSynthesisAccess(
        query_authorization=query,
        context_authorization=archive,
        owner_ref=text.owner_ref,
        connection_ref=connection_ref,
        query_resource_ref="resource_conversation",
        context_resource_ref="resource_archive",
    )


def _synthetic_archive_receipt() -> ArchiveSynthesisReceipt:
    return ArchiveSynthesisReceipt(
        provider="openai",
        model="synthetic-pa04-holdout",
        external_call_attempted=True,
        external_call_performed=True,
        context_egress_attempted=True,
        context_egress_performed=True,
        delivery_outcome="accepted",
        context_binding_digest="synthetic-pa04-holdout",
    )


def _holdout_item(*, document_id: str, source_url: str, snippet: str) -> dict:
    return {
        "archive_document_id": document_id,
        "posted_at": "2026-09-01T10:00:00Z",
        "channel_username": "eval_holdout",
        "source_url": source_url,
        "snippet": snippet,
    }


def test_application_returns_intent_specific_archive_contract(monkeypatch):
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: _payload())
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: SimpleNamespace())
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


def test_application_uses_verified_pa04_synthesis_and_records_retrieval_generation(monkeypatch):
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: _payload())
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: SimpleNamespace())
    seen = []

    def synthesize(*_args, **kwargs):
        seen.append(kwargs["access"])
        return ArchiveSynthesisOutcome(
            text="Agent evals use task success and groundedness (https://t.me/example/1).",
            status="generated_verified",
            measurement={
                "selected_source_count": 1,
                "provider_egress_attempted": True,
                "context_egress_attempted": True,
                "context_egress_performed": True,
            },
        )

    marker = object()
    monkeypatch.setattr("prm.application.synthesize_archive_response", synthesize)
    result = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:")).answer(OperatorRequest(
        query="Что в моём архиве есть про agent evals?",
        mode="auto",
        archive_synthesis_access=marker,  # the transport independently requires the concrete typed carrier
    ))

    assert seen == [marker]
    assert result.text == "Agent evals use task success and groundedness (https://t.me/example/1)."
    assert result.payload["final_answer_publication"]["fallback_used"] is False
    measurement = result.payload["retrieval_generation_measurement"]
    assert measurement["retrieval"]["selected_source_count"] == 1
    assert measurement["generation"]["status"] == "generated_verified"
    assert measurement["generation"]["context_egress_performed"] is True


@pytest.mark.parametrize(
    ("question", "source_url", "support_span"),
    [
        (
            "What does my archive say about agent evals?",
            "https://t.me/eval_holdout/english",
            "Agent evals use task success and groundedness.",
        ),
        (
            "Что в моём архиве есть про agent evals?",
            "https://t.me/eval_holdout/russian",
            "В архиве есть практика: измерять task success и groundedness для agent evals.",
        ),
    ],
)
def test_pa04_bilingual_holdout_uses_actual_retriever_ranking_and_publication(
    monkeypatch, question, source_url, support_span,
):
    direct = _holdout_item(
        document_id=f"tg:holdout:{source_url.rsplit('/', 1)[-1]}",
        source_url=source_url,
        snippet=support_span,
    )
    facade = _ArchiveHoldoutFacade([
        _holdout_item(
            document_id="tg:holdout:partial",
            source_url="https://t.me/eval_holdout/partial",
            snippet="Evaluation notes mention gold labels.",
        ),
        _holdout_item(
            document_id="tg:holdout:unrelated",
            source_url="https://t.me/eval_holdout/unrelated",
            snippet="Travel planning notes have no evaluation practice.",
        ),
        direct,
    ])
    monkeypatch.setattr("prm.application.build_research_facade", lambda **_kwargs: facade)

    def complete(*, context, access):
        del access
        selected = context.items[0]
        return ArchiveSynthesisTransportResult(
            text=f"{selected.text.rstrip('.!?…')} ({selected.source_ref}).",
            receipt=_synthetic_archive_receipt(),
        )

    monkeypatch.setattr("prm.synthesis.complete_archive_synthesis", complete)
    result = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:")).answer(
        OperatorRequest(
            query=question,
            mode="research",
            chat_id=f"holdout-{source_url.rsplit('/', 1)[-1]}",
            archive_synthesis_access=_archive_synthesis_access(),
        )
    )

    contract = result.payload["archive_contract"]
    selected = result.payload["archive_evidence"]["items"]
    measurement = result.payload["retrieval_generation_measurement"]
    assert facade.archive_queries
    assert selected[0]["source_url"] == source_url
    assert selected[0]["relevance_label"] == "direct"
    assert contract["result_summary"]["direct_count"] == 1
    assert source_url in result.text
    assert result.payload["final_answer_publication"]["allowed"] is True
    assert measurement["retrieval"]["candidate_count"] >= 3
    assert measurement["retrieval"]["selected_source_count"] >= 1
    assert measurement["retrieval"]["attempted_query_count"] >= 1
    assert measurement["generation"]["status"] == "generated_verified"
    assert result.payload["final_answer_publication"]["fallback_used"] is False


def test_pa04_partial_result_publishes_useful_cited_support_and_rejects_false_refusal(monkeypatch):
    partial = _holdout_item(
        document_id="tg:holdout:partial-only",
        source_url="https://t.me/eval_holdout/partial-only",
        snippet="Evaluation gates measure task success with gold labels.",
    )

    def run_with(provider_text):
        facade = _ArchiveHoldoutFacade([partial])
        monkeypatch.setattr("prm.application.build_research_facade", lambda **_kwargs: facade)
        monkeypatch.setattr(
            "prm.synthesis.complete_archive_synthesis",
            lambda **_kwargs: ArchiveSynthesisTransportResult(text=provider_text, receipt=_synthetic_archive_receipt()),
        )
        return PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:")).answer(OperatorRequest(
            query="What does my archive say about agent evals?",
            mode="research",
            chat_id=f"partial-{len(provider_text)}",
            archive_synthesis_access=_archive_synthesis_access(),
        ))

    positive = run_with(
        "Partial: Evaluation gates measure task success with gold labels "
        "(https://t.me/eval_holdout/partial-only)."
    )
    assert positive.payload["archive_contract"]["result_summary"] == {
        "direct_count": 0,
        "partial_count": 1,
        "adjacent_count": 0,
        "unrelated_count": 0,
        "selected_count": 1,
        "actionable_count": 0,
    }
    assert positive.payload["retrieval_generation_measurement"]["generation"]["status"] == "generated_verified"
    assert positive.payload["final_answer_publication"]["fallback_used"] is False
    assert "https://t.me/eval_holdout/partial-only" in positive.text

    false_refusal = run_with("No direct evidence.")
    assert false_refusal.payload["retrieval_generation_measurement"]["generation"]["status"] == "generated_answer_rejected"
    assert false_refusal.payload["final_answer_publication"]["fallback_used"] is True
    assert "Evaluation gates measure task success with gold labels." in false_refusal.text
    assert "https://t.me/eval_holdout/partial-only" in false_refusal.text


def test_pa04_truthful_empty_archive_result_publishes_without_generation_or_citation(monkeypatch):
    facade = _ArchiveHoldoutFacade([])
    monkeypatch.setattr("prm.application.build_research_facade", lambda **_kwargs: facade)
    result = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:")).answer(OperatorRequest(
        query="What does my archive say about agent evals?",
        mode="research",
        chat_id="empty-archive-holdout",
    ))

    assert facade.archive_queries
    assert result.payload["archive_contract"]["result_summary"]["selected_count"] == 0
    assert result.payload["retrieval_generation_measurement"]["generation"]["status"] == "context_unavailable"
    assert result.payload["final_answer_publication"]["allowed"] is True
    assert result.payload["final_answer_publication"]["fallback_used"] is True
    assert "не удалось собрать проверяемый ответ" in result.text.casefold()
    assert "https://" not in result.text


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
    assert "Почему это может быть полезно:" in result.text
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
    assert "AI и исследования" in ranked.text and "карьера" in ranked.text and "https://calendar.utdallas.edu/high" in ranked.text


def test_archive_to_action_uses_bounded_research_plan(monkeypatch):
    payload = _payload()
    payload["archive_candidate_pool"] = [
        {**payload["archive_evidence"]["items"][0], "source_role": "practical_evidence", "supports_action": True,
         "retrieval_mode": "hybrid_fts_vector"},
        {"archive_document_id": "promo", "snippet": "Agent evals webinar registration", "source_url": "https://t.me/example/2", "source_role": "announcement_or_promotion", "supports_action": False},
    ]
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: payload)
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: SimpleNamespace())
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
    assert "Постоянная запись появится только после отдельного подтверждения" in result.text
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
        "Не удалось собрать проверяемый ответ. Уточни запрос или источник.",
        [],
    )
    assert verification["claim_count"] == 0


def test_terminal_empty_answer_keeps_a_contextual_next_step_without_factual_claims():
    rendered = _render_terminal_empty_answer("назови один термин, канал или период.")
    verification = verify_answer_against_evidence(rendered, [])

    assert "назови один термин" in rendered
    assert verification["claim_count"] == 0
    assert _final_answer_publication_allowed(verification, {}) is True


def test_mixed_archive_and_current_question_keeps_archive_part_without_claiming_current_fact(monkeypatch):
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: _payload())
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: SimpleNamespace())
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
