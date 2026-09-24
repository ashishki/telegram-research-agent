from __future__ import annotations

from types import SimpleNamespace

from bot import prm_handlers
from prm.conversation import GLOBAL_CONVERSATIONS


def _settings(tmp_path):
    return SimpleNamespace(db_path=str(tmp_path / "memory.db"))


def test_help_describes_one_archive_and_utd_assistant() -> None:
    text = prm_handlers._help_text()
    assert "один помощник" in text
    assert "AI-архив" in text
    assert "UTD / Dallas" in text
    assert "Настроить мой UTD-профиль" in text
    assert "Свежие UTD-источники" in text


def test_natural_language_denies_utd_draft_before_local_write_without_grant(monkeypatch, tmp_path) -> None:
    sent = []; started = []
    def fake_start(db_path, *, chat_id, seed_text):
        started.append(seed_text); return {"message": "draft only", "reply_markup": {"inline_keyboard": []}}
    monkeypatch.setattr(prm_handlers, "start_utd_profile_onboarding", fake_start)
    monkeypatch.setattr(prm_handlers, "send_message", lambda _token, _chat, text, **kwargs: sent.append((text, kwargs.get("reply_markup"))))
    prm_handlers.dispatch_prm_command("42", "/auto Настроить мой UTD-профиль", _settings(tmp_path))
    assert started == []
    assert sent == []


def test_utd_question_fails_closed_without_entering_prm_research(monkeypatch, tmp_path) -> None:
    sent = []
    class ForbiddenAssistant:
        def __init__(self, *args, **kwargs): raise AssertionError("UTD-1 must not enter live/external PRM research")
    monkeypatch.setattr(prm_handlers, "PersonalResearchAssistant", ForbiddenAssistant)
    monkeypatch.setattr(prm_handlers, "send_message", lambda _token, _chat, text, **_kwargs: sent.append(text))
    prm_handlers.dispatch_prm_command("42", "/research Когда следующий UTD career fair?", _settings(tmp_path))
    assert len(sent) == 1
    assert "UTD — безопасный предпросмотр" in sent[0]
    assert "Свежие UTD-источники" in sent[0]


def test_explicit_archive_utd_question_keeps_route_but_denies_result_delivery_without_grant(monkeypatch, tmp_path) -> None:
    sent = []; requests = []
    class FakeAssistant:
        def __init__(self, *, settings): self.settings = settings
        def answer(self, request):
            requests.append(request); return SimpleNamespace(text="archive result", payload={"answer_gate": {"allow_answer": False}})
    monkeypatch.setattr(prm_handlers, "PersonalResearchAssistant", FakeAssistant)
    monkeypatch.setattr(prm_handlers, "send_message", lambda _token, _chat, text, **_kwargs: sent.append(text))
    prm_handlers.dispatch_prm_command(
        "42",
        "/auto Что в архиве есть про UTD и AI research?",
        _settings(tmp_path),
        actor_id="42",
        owner_chat_id="42",
    )
    assert len(requests) == 1
    assert sent == []


def test_prm_active_handler_resolves_short_followups_from_volatile_context() -> None:
    prm_handlers._PRM_DIALOG_STATE.clear()
    prm_handlers._remember_prm_dialog(
        "42",
        "Что в моём архиве было про agent evals и что мне с этим делать?",
        mode="research",
        topic="agent evals",
    )

    resolved = prm_handlers._resolve_prm_dialog_query(
        "42",
        "покажи только прямые находки",
        mode="auto",
    )

    assert resolved["used"] is True
    assert resolved["effective_query"].startswith("В архиве по теме agent evals.")
    assert "Уточнение: покажи только прямые находки" in resolved["effective_query"]

    project_followup = prm_handlers._resolve_prm_dialog_query(
        "42",
        "а применимо это к проекту telegram-research-agent?",
        mode="auto",
    )

    assert project_followup["used"] is True
    assert "agent evals" in project_followup["effective_query"]
    assert "telegram-research-agent" in project_followup["effective_query"]
    assert "Проверь" not in project_followup["effective_query"]


def test_new_topic_replaces_volatile_topic_and_last_week_followup_keeps_it() -> None:
    prm_handlers._PRM_DIALOG_STATE.clear()
    prm_handlers._remember_prm_dialog("42", "В архиве по теме Topic A", mode="research", topic="Topic A")
    new_topic = prm_handlers._resolve_prm_dialog_query("42", "В архиве по теме Topic B", mode="auto")
    assert new_topic["used"] is False
    assert new_topic["effective_query"] == "В архиве по теме Topic B"

    prm_handlers._remember_prm_dialog("42", new_topic["effective_query"], mode="research", topic="Topic B")
    followup = prm_handlers._resolve_prm_dialog_query("42", "за прошлую неделю", mode="auto")
    assert followup["used"] is True
    assert "Topic B" in followup["effective_query"]
    assert "за прошлую неделю" in followup["effective_query"]


def test_active_dispatch_does_not_mutate_legacy_topic_state(monkeypatch, tmp_path) -> None:
    prm_handlers._PRM_DIALOG_STATE.clear()
    prm_handlers._remember_prm_dialog("42", "В архиве по теме Topic A", mode="research", topic="Topic A")

    class FakeAssistant:
        def __init__(self, *, settings): pass
        def answer(self, request):
            return SimpleNamespace(
                text="Topic B result",
                payload={"answer_gate": {"allow_answer": False}},
                status="ok",
                mode="research",
                route={"retrieval_query": "Topic B"},
            )

    monkeypatch.setattr(prm_handlers, "PersonalResearchAssistant", FakeAssistant)
    monkeypatch.setattr(prm_handlers, "send_message", lambda *_args, **_kwargs: None)
    prm_handlers.dispatch_prm_command("42", "/research В архиве по теме Topic B", _settings(tmp_path))
    followup = prm_handlers._resolve_prm_dialog_query("42", "за прошлую неделю", mode="auto")

    assert "Topic A" in followup["effective_query"]
    assert "Topic B" not in followup["effective_query"]


def test_active_dispatch_uses_visible_conversation_object_not_legacy_last_topic(monkeypatch, tmp_path) -> None:
    prm_handlers._PRM_DIALOG_STATE.clear()
    GLOBAL_CONVERSATIONS.clear()
    prm_handlers._remember_prm_dialog("42", "В архиве по теме Topic A", mode="research", topic="Topic A")
    GLOBAL_CONVERSATIONS.record_response("42", text="Topic B result", topic="Topic B")
    requests = []

    class FakeAssistant:
        def __init__(self, *, settings):
            pass

        def answer(self, request):
            requests.append(request)
            return SimpleNamespace(text="result", payload={}, status="ok", mode="research", route={})

    monkeypatch.setattr(prm_handlers, "PersonalResearchAssistant", FakeAssistant)
    monkeypatch.setattr(prm_handlers, "send_message", lambda *_args, **_kwargs: None)

    prm_handlers.dispatch_prm_command("42", "/auto за прошлую неделю", _settings(tmp_path))

    assert len(requests) == 1
    assert "Topic B" in requests[0].query
    assert "Topic A" not in requests[0].query
    GLOBAL_CONVERSATIONS.clear()


def test_active_dispatch_does_not_recover_keyword_followup_from_legacy_state(monkeypatch, tmp_path) -> None:
    prm_handlers._PRM_DIALOG_STATE.clear()
    GLOBAL_CONVERSATIONS.clear()
    prm_handlers._remember_prm_dialog("42", "В архиве по теме Topic A", mode="research", topic="Topic A")
    requests = []

    class FakeAssistant:
        def __init__(self, *, settings):
            pass

        def answer(self, request):
            requests.append(request)
            return SimpleNamespace(text="result", payload={}, status="ok", mode="research", route={})

    monkeypatch.setattr(prm_handlers, "PersonalResearchAssistant", FakeAssistant)
    monkeypatch.setattr(prm_handlers, "send_message", lambda *_args, **_kwargs: None)

    prm_handlers.dispatch_prm_command("42", "/auto за прошлую неделю", _settings(tmp_path))

    assert len(requests) == 1
    assert requests[0].query == "за прошлую неделю"


def test_plain_language_action_selection_rejects_stale_or_cross_topic_context(monkeypatch, tmp_path) -> None:
    prm_handlers._PRM_DIALOG_STATE.clear()
    prm_handlers._remember_prm_dialog(
        "42",
        "Что в моём архиве было про agent evals и что мне с этим делать?",
        mode="research",
        topic="agent evals",
        action_context_id="ctx123",
        action_codes=["n", "w"],
        last_answer="В архиве найдено 1 прямое совпадение.",
        direct_count=1,
    )
    sent = []
    class ForbiddenAssistant:
        def __init__(self, *args, **kwargs): raise AssertionError("free-text save follow-up must not rerun archive search")

    monkeypatch.setattr(prm_handlers, "PersonalResearchAssistant", ForbiddenAssistant)
    monkeypatch.setattr(prm_handlers, "send_message", lambda _token, _chat, text, **kwargs: sent.append((text, kwargs.get("reply_markup"))))

    prm_handlers.dispatch_prm_command("42", "/auto сохрани заметку, но сначала покажи что именно сохранишь", _settings(tmp_path))

    assert sent == [("Это действие недоступно. Отправь запрос заново, чтобы получить новую кнопку действия.", None)]


def test_short_next_step_followup_does_not_rerun_archive_search(monkeypatch, tmp_path) -> None:
    prm_handlers._PRM_DIALOG_STATE.clear()
    GLOBAL_CONVERSATIONS.clear()
    prm_handlers._remember_prm_dialog(
        "42",
        "Что в моём архиве было про agent evals и что мне с этим делать?",
        mode="research",
        topic="agent evals",
        direct_count=0,
        adjacent_count=1,
    )
    sent = []

    GLOBAL_CONVERSATIONS.record_response("42", text="Visible agent evals result", topic="agent evals")
    monkeypatch.setattr(
        "prm.application.answer_memory_research",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("short next step must not rerun archive search")),
    )
    monkeypatch.setattr(prm_handlers, "_send_chunks", lambda _chat, text, **_kwargs: sent.append(text))

    prm_handlers.dispatch_prm_command("42", "/auto коротко: какой следующий шаг?", _settings(tmp_path))

    assert len(sent) == 1
    assert sent[0].startswith("Следующий шаг:")
    assert "agent evals" in sent[0]
    GLOBAL_CONVERSATIONS.clear()


def test_short_next_step_after_watch_preview_points_to_confirmation() -> None:
    prm_handlers._PRM_DIALOG_STATE.clear()
    prm_handlers._remember_prm_dialog(
        "42",
        "что сейчас самое новое во внешних источниках про agent evals?",
        mode="research",
        topic="agent evals",
        current_fact_boundary=True,
    )
    prm_handlers._remember_pending_prm_action("42", action="w", message="Следить: черновик подготовлен.")

    resolved = prm_handlers._resolve_prm_dialog_query(
        "42",
        "коротко: какой следующий шаг?",
        mode="auto",
    )

    assert resolved["kind"] == "short_next_step"
    assert "подтвердить черновик темы наблюдения" in resolved["message"]
    assert "agent evals" in resolved["message"]
    assert "сохранит только подтверждённую тему" in resolved["message"]
    assert "буду следить" not in resolved["message"]


def test_utd_command_is_part_of_active_prm_surface() -> None:
    assert "/utd" in prm_handlers.PRM_SAFE_COMMANDS


def test_privacy_command_builds_only_the_actual_default_deny_scope(monkeypatch, tmp_path) -> None:
    sent = []

    class ForbiddenAssistant:
        def __init__(self, *args, **kwargs):
            raise AssertionError("permission explanation must not enter PRM research")

    monkeypatch.setattr(prm_handlers, "PersonalResearchAssistant", ForbiddenAssistant)
    monkeypatch.setattr(
        prm_handlers,
        "send_message",
        lambda _token, _chat, text, **_kwargs: sent.append(text),
    )

    prm_handlers.dispatch_prm_command(
        "42",
        "/privacy",
        _settings(tmp_path),
        actor_id="42",
        owner_chat_id="42",
    )

    # The fake sender isolates rendering only. Delivery itself has an explicit
    # grant-backed assertion in the PA-02 egress suite.
    assert len(sent) == 1
    assert "нет активных разрешений" in sent[0]
    assert "заблокированы" in sent[0]
    assert "Ключ провайдера сам по себе не является согласием." in sent[0]


def test_privacy_command_does_not_disclose_scope_across_actor_or_owner_boundary(monkeypatch, tmp_path) -> None:
    sent = []
    monkeypatch.setattr(
        prm_handlers,
        "send_message",
        lambda _token, _chat, text, **_kwargs: sent.append(text),
    )

    prm_handlers.dispatch_prm_command(
        "42",
        "/privacy",
        _settings(tmp_path),
        actor_id="43",
        owner_chat_id="42",
    )

    assert sent == ["Сведения о правах недоступны для этого чата."]
    assert "нет активных разрешений" not in sent[0]


def test_help_does_not_promise_watch_monitoring_or_delivery() -> None:
    rendered = prm_handlers._help_text()

    assert "сохранение темы само по себе не включает мониторинг, уведомления или доставку" in rendered
    assert "watch-уведомления работают" not in rendered
