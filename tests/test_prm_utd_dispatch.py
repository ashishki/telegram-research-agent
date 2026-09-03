from __future__ import annotations

from types import SimpleNamespace

from bot import prm_handlers


def _settings(tmp_path):
    return SimpleNamespace(db_path=str(tmp_path / "memory.db"))


def test_help_describes_one_archive_and_utd_assistant() -> None:
    text = prm_handlers._help_text()
    assert "один помощник" in text
    assert "AI-архив" in text
    assert "UTD / Dallas" in text
    assert "Настроить мой UTD-профиль" in text
    assert "live-источники" in text


def test_natural_language_starts_confirmation_gated_utd_draft(monkeypatch, tmp_path) -> None:
    sent = []; started = []
    def fake_start(db_path, *, chat_id, seed_text):
        started.append(seed_text); return {"message": "draft only", "reply_markup": {"inline_keyboard": []}}
    monkeypatch.setattr(prm_handlers, "start_utd_profile_onboarding", fake_start)
    monkeypatch.setattr(prm_handlers, "send_message", lambda _token, _chat, text, **kwargs: sent.append((text, kwargs.get("reply_markup"))))
    prm_handlers.dispatch_prm_command("42", "/auto Настроить мой UTD-профиль", _settings(tmp_path))
    assert started == ["Настроить мой UTD-профиль"]
    assert sent == [("draft only", {"inline_keyboard": []})]


def test_utd_question_fails_closed_without_entering_prm_research(monkeypatch, tmp_path) -> None:
    sent = []
    class ForbiddenAssistant:
        def __init__(self, *args, **kwargs): raise AssertionError("UTD-1 must not enter live/external PRM research")
    monkeypatch.setattr(prm_handlers, "PersonalResearchAssistant", ForbiddenAssistant)
    monkeypatch.setattr(prm_handlers, "send_message", lambda _token, _chat, text, **_kwargs: sent.append(text))
    prm_handlers.dispatch_prm_command("42", "/research Когда следующий UTD career fair?", _settings(tmp_path))
    assert len(sent) == 1
    assert "UTD ASK — безопасный preview" in sent[0]
    assert "Live UTD-источники" in sent[0]


def test_explicit_archive_utd_question_keeps_existing_archive_route(monkeypatch, tmp_path) -> None:
    sent = []; requests = []
    class FakeAssistant:
        def __init__(self, *, settings): self.settings = settings
        def answer(self, request):
            requests.append(request); return SimpleNamespace(text="archive result", payload={"answer_gate": {"allow_answer": False}})
    monkeypatch.setattr(prm_handlers, "PersonalResearchAssistant", FakeAssistant)
    monkeypatch.setattr(prm_handlers, "send_message", lambda _token, _chat, text, **_kwargs: sent.append(text))
    prm_handlers.dispatch_prm_command("42", "/auto Что в архиве есть про UTD и AI research?", _settings(tmp_path))
    assert len(requests) == 1
    assert sent == ["archive result"]


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


def test_utd_command_is_part_of_active_prm_surface() -> None:
    assert "/utd" in prm_handlers.PRM_SAFE_COMMANDS
