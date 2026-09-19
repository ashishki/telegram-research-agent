from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from bot.prm_handlers import _brief_navigation_markup
from bot import prm_handlers
from prm.application import PersonalResearchAssistant
from prm.briefs import BriefBuildRequest, BriefDocumentStore, BriefWindow, CoverageSource, build_brief_document, render_brief
from prm.contracts import OperatorRequest
from prm.conversation import ConversationStore


def _window(start: str, end: str) -> BriefWindow:
    return BriefWindow.from_iso(
        timezone_name="Europe/Berlin",
        start_at=start,
        end_at=end,
        generated_at=end,
    )


def _source(identifier: str, url: str, title: str, summary: str, posted_at: str, topic: str) -> dict[str, object]:
    return {
        "local_archive_provenance": True,
        "evidence_id": identifier,
        "source_url": url,
        "title": title,
        "support_span": summary,
        "posted_at": posted_at,
        "topics": [topic],
        "importance": "high" if topic == "AI" else "medium",
        "urgent": topic == "career",
    }


def _request(*, comparison_document=None) -> BriefBuildRequest:
    return BriefBuildRequest(
        topic="weekly signals",
        window=_window("2026-09-14T00:00:00+02:00", "2026-09-21T00:00:00+02:00"),
        coverage=(CoverageSource("telegram:archive", "checked"),),
        evidence=(
            _source("ai", "https://t.me/example/ai", "AI item", "AI evidence detail.", "2026-09-16T10:00:00+02:00", "AI"),
            _source("career", "https://t.me/example/career", "Career item", "Career evidence detail.", "2026-09-17T10:00:00+02:00", "career"),
        ),
        comparison_document=comparison_document,
    )


def _assistant() -> tuple[PersonalResearchAssistant, BriefDocumentStore]:
    briefs = BriefDocumentStore()
    return (
        PersonalResearchAssistant(
            settings=SimpleNamespace(db_path=":memory:"),
            conversations=ConversationStore(),
            briefs=briefs,
        ),
        briefs,
    )


def test_report_followups_use_only_the_current_visible_brief_document(monkeypatch) -> None:
    assistant, _ = _assistant()

    def forbidden_retrieval(*args, **kwargs):
        raise AssertionError("a report follow-up must not search archive evidence again")

    monkeypatch.setattr("prm.application.answer_memory_research", forbidden_retrieval)
    initial = assistant.answer(OperatorRequest(query="weekly signals", mode="brief", chat_id="42", brief_request=_request()))
    explained = assistant.answer(OperatorRequest(query="объясни пункт 2", chat_id="42"))
    shortened = assistant.answer(OperatorRequest(query="сделай короче", chat_id="42"))
    filtered = assistant.answer(OperatorRequest(query="только AI", chat_id="42"))
    less_technical = assistant.answer(OperatorRequest(query="сделай менее техническим", chat_id="42"))
    apply = assistant.answer(OperatorRequest(query="что из этого применить?", chat_id="42"))
    navigation = initial.payload["telegram_navigation"]
    full = assistant.answer(OperatorRequest(query=navigation["button_text"], chat_id="42"))

    assert initial.payload["brief_document_created"] is True
    assert navigation == {
        "kind": "reply_keyboard",
        "button_text": "Показать полный бриф",
        "current_visible_brief_only": True,
        "brief_version": initial.payload["brief_document"]["previous_version"] or {
            "brief_id": initial.payload["brief_document"]["brief_id"], "version": 1,
        },
    }
    assert _brief_navigation_markup(initial.payload) == {
        "keyboard": [[{"text": "Показать полный бриф"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }
    assert explained.payload["brief_followup"]["kind"] == "explain_item"
    assert "Пункт 2: Career item" in explained.text
    assert "https://t.me/example/career" in explained.text
    assert shortened.payload["brief_view"] == "short"
    assert filtered.payload["brief_view"] == "topics"
    assert "AI item" in filtered.text
    assert "Career item" not in filtered.text
    assert less_technical.payload["brief_view"] == "less_technical"
    assert "новых фактов и поиска нет" in less_technical.text
    assert apply.payload["brief_view"] == "apply"
    assert "не выполненные действия" in apply.text
    assert full.payload["brief_view"] == "full"
    assert full.payload["telegram_parse_mode"] == "HTML"
    assert full.text.startswith("🗞 <b>Материалы по теме</b>")
    assert "Редакторский обзор пока не подготовлен" in full.text
    assert all(
        result.payload["retrieval_performed"] is False
        for result in (initial, explained, shortened, filtered, less_technical, apply, full)
    )


def test_current_editorial_item_reference_is_ephemeral_and_exact() -> None:
    document = build_brief_document(_request())
    store = BriefDocumentStore()
    conversation_id = "conversation_" + "a" * 24
    response_ref = "response_" + "b" * 24
    store.bind_visible(
        conversation_id=conversation_id,
        response_ref=response_ref,
        document=document,
        active_item_number=1,
    )
    # The store returns only the item bound to this exact visible response;
    # the application additionally limits rich continuations to editorial reports.
    assert store.visible_item_number(conversation_id=conversation_id, response_ref=response_ref) == 1
    assert store.visible_item_number(conversation_id=conversation_id, response_ref="response_" + "c" * 24) is None
    store.forget_conversation(conversation_id)
    assert store.visible_item_number(conversation_id=conversation_id, response_ref=response_ref) is None


def test_compare_weeks_uses_an_actual_bound_prior_brief_not_a_new_search(monkeypatch) -> None:
    prior = build_brief_document(
        BriefBuildRequest(
            topic="weekly signals",
            window=_window("2026-09-07T00:00:00+02:00", "2026-09-14T00:00:00+02:00"),
            coverage=(CoverageSource("telegram:archive", "checked"),),
            evidence=(_source("prior", "https://t.me/example/prior", "Prior item", "Prior evidence.", "2026-09-09T10:00:00+02:00", "AI"),),
        )
    )
    assistant, _ = _assistant()
    monkeypatch.setattr(
        "prm.application.answer_memory_research",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("comparison must not search")),
    )
    current = assistant.answer(
        OperatorRequest(query="weekly signals", mode="brief", chat_id="42", brief_request=_request(comparison_document=prior))
    )
    comparison = assistant.answer(OperatorRequest(query="сравни с прошлой неделей", chat_id="42"))

    assert current.payload["brief_inspection"]["history"]["comparison_ref"] == prior.version_ref.to_dict()
    assert comparison.payload["brief_followup"]["kind"] == "compare_weeks"
    assert "Prior item" in comparison.text
    assert "поиск не запускался" in comparison.text
    assert comparison.payload["retrieval_performed"] is False


def test_new_topic_and_restart_make_report_state_unavailable() -> None:
    assistant, briefs = _assistant()
    initial = assistant.answer(OperatorRequest(query="weekly signals", mode="brief", chat_id="42", brief_request=_request()))
    refreshed = assistant.answer(OperatorRequest(query="обнови бриф", chat_id="42"))
    conversation_id = initial.payload["conversation"]["conversation_id"]
    response_ref = initial.payload["conversation"]["response_refs"][0]
    brief_id = initial.payload["brief_document"]["brief_id"]
    assert render_brief(brief_id, 1, "short", conversation_id=conversation_id, store=briefs) is not None
    assert render_brief(brief_id, 2, "short", conversation_id=conversation_id, store=briefs) is not None
    refreshed_ref = refreshed.payload["conversation"]["response_refs"][0]
    assert briefs.resolve_visible(conversation_id=conversation_id, response_ref=refreshed_ref) is not None

    reset = assistant.answer(OperatorRequest(query="/new", mode="chat", chat_id="42"))
    assert reset.status == "topic_reset"
    assert briefs.resolve_visible(conversation_id=conversation_id, response_ref=response_ref) is None
    assert render_brief(brief_id, 1, "short", conversation_id=conversation_id, store=briefs) is None
    assert render_brief(brief_id, 2, "short", conversation_id=conversation_id, store=briefs) is None

    # A fresh process owns fresh ConversationStore and BriefDocumentStore;
    # no report reference is reconstructed from a topic or response string.
    restarted, restarted_briefs = _assistant()
    assert restarted_briefs.resolve_visible(conversation_id=conversation_id, response_ref=response_ref) is None
    assert restarted.briefs is restarted_briefs


def test_active_brief_refresh_versions_and_two_active_weeks_bind_real_history(monkeypatch) -> None:
    assistant, _ = _assistant()
    initial = assistant.answer(OperatorRequest(query="weekly signals", mode="brief", chat_id="42", brief_request=_request()))
    refreshed = assistant.answer(OperatorRequest(query="обнови бриф", chat_id="42"))

    assert refreshed.payload["brief_document"]["version"] == 2
    assert refreshed.payload["brief_document"]["previous_version"] == {
        "brief_id": initial.payload["brief_document"]["brief_id"], "version": 1,
    }
    assert refreshed.payload["brief_inspection"]["period"]["basis"] == "revised_existing_evidence"
    assert refreshed.payload["brief_refresh"] == {
        "performed": True,
        "new_source_search": False,
        "material_changes": [],
    }
    assert "Существенных изменений фактов не обнаружено" in refreshed.text
    third = assistant.answer(OperatorRequest(query="обнови бриф", chat_id="42"))
    brief_id = initial.payload["brief_document"]["brief_id"]
    conversation_id = initial.payload["conversation"]["conversation_id"]
    assert third.payload["brief_document"]["version"] == 3
    assert all(
        render_brief(brief_id, version, "short", conversation_id=conversation_id, store=assistant.briefs) is not None
        for version in (1, 2, 3)
    )
    calls = []
    empty_payload = {
        "status": "ok", "direct_answer": "", "answer_gate": {"allow_answer": True},
        "archive_evidence": {"items": []}, "evidence_quality": {"items": []},
        "professional_answer": {}, "project_fit": {}, "project_decision": {}, "claim_ledger": {},
        "unknowns": [], "next_steps": {}, "receipt": {}, "privacy": {},
    }
    monkeypatch.setattr(
        "prm.application.answer_memory_research",
        lambda *args, **kwargs: calls.append(args) or empty_payload,
    )
    first_week = assistant.answer(
        OperatorRequest(query="бриф AI за прошлую неделю timezone Europe/Berlin", mode="brief", chat_id="42")
    )
    second_week = assistant.answer(
        OperatorRequest(query="бриф AI последние 7 дней timezone Europe/Berlin", mode="brief", chat_id="42")
    )
    compared = assistant.answer(OperatorRequest(query="сравни с прошлой неделей", chat_id="42"))

    assert len(calls) == 2
    assert first_week.payload["brief_inspection"]["period"]["basis"] == "previous_calendar_week"
    assert second_week.payload["brief_inspection"]["history"]["comparison_ref"] == {
        "brief_id": first_week.payload["brief_document"]["brief_id"],
        "version": first_week.payload["brief_document"]["version"],
    }
    assert compared.payload["brief_followup"]["kind"] == "compare_weeks"
    assert len(calls) == 2


def test_telegram_dispatch_reuses_visible_brief_store_across_turns_and_denies_after_restart(monkeypatch) -> None:
    chat_id = "987654321"
    settings = SimpleNamespace(db_path=":memory:")
    created = []
    sent: list[tuple[str, dict[str, object]]] = []

    class DispatchAssistant(PersonalResearchAssistant):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            created.append(self)

        def answer(self, request):
            if request.query == "weekly signals":
                return super().answer(replace(request, mode="brief", brief_request=_request()))
            return super().answer(request)

    fallback_payload = {
        "status": "ok", "direct_answer": "No visible brief remains.", "answer_gate": {"allow_answer": True},
        "archive_evidence": {"items": []}, "evidence_quality": {"items": []},
        "professional_answer": {}, "project_fit": {}, "project_decision": {}, "claim_ledger": {},
        "unknowns": [], "next_steps": {}, "receipt": {}, "privacy": {},
    }
    monkeypatch.setattr(prm_handlers, "PersonalResearchAssistant", DispatchAssistant)
    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: fallback_payload)
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(prm_handlers, "_send_chunks", lambda _chat, text, **kwargs: sent.append((text, kwargs)))
    prm_handlers._PRM_BRIEF_STORES.clear()

    prm_handlers.dispatch_prm_command(
        chat_id, "/brief weekly signals", settings, actor_id=chat_id, owner_chat_id=chat_id,
    )
    prm_handlers.dispatch_prm_command(
        chat_id, "/auto объясни пункт 2", settings, actor_id=chat_id, owner_chat_id=chat_id,
    )

    assert len(created) == 2
    assert created[0].briefs is created[1].briefs
    assert sent[0][1]["parse_mode"] == "HTML"
    assert "<b>Короткий бриф</b>" in sent[0][0]
    assert "Пункт 2: Career item" in sent[-1][0]

    visible_store = created[-1].briefs
    # A process restart loses only the bounded visible store. Conversation
    # metadata alone cannot reconstruct a natural-language report follow-up.
    prm_handlers._PRM_BRIEF_STORES.clear()
    prm_handlers.dispatch_prm_command(
        chat_id, "/auto объясни пункт 2", settings, actor_id=chat_id, owner_chat_id=chat_id,
    )

    assert created[-1].briefs is not visible_store
    assert "Пункт 2: Career item" not in sent[-1][0]
    prm_handlers._PRM_BRIEF_STORES.clear()
