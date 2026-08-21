import os
import sqlite3
import tempfile

import pytest

from assistant.prm_post_answer_actions import (
    PRM_ACTION_PREFIX,
    PRM_CONFIRM_PREFIX,
    _CONTEXTS,
    build_post_answer_actions,
    handle_post_answer_callback,
)
from db.migrate import run_migrations


@pytest.fixture(autouse=True)
def _isolated_private_trace_root(tmp_path, monkeypatch):
    monkeypatch.setattr("assistant.prm_private_traces._TRACE_ROOT", tmp_path / "private_traces")


def _answer(*, project_name: str = "") -> dict:
    return {
        "question": "как улучшить eval gates?",
        "direct_answer": "Добавить один regression case.",
        "source_refs": ["https://t.me/example/1"],
        "project_name": project_name,
    }


def test_action_markup_relevant_and_bounded(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        markup = build_post_answer_actions(_answer(project_name="telegram-research-agent"), db_path=db_path, chat_id="42")["reply_markup"]
        buttons = [button for row in markup["inline_keyboard"] for button in row]

    assert {button["text"] for button in buttons}.issuperset({"Полезно", "Частично", "Мимо", "Сохранить заметку", "Следить"})
    assert {button["text"] for button in buttons}.issuperset({"Связать с проектом", "Создать действие", "Создать эксперимент"})
    assert all(button["callback_data"].startswith(f"{PRM_ACTION_PREFIX}:") for button in buttons)
    assert all(len(button["callback_data"]) <= 64 for button in buttons)


def test_proposal_before_write(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]

        result = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")

        assert result["status"] == "needs_confirmation"
        assert result["write_performed"] is False
        assert os.path.exists(db_path)
        confirm_button = result["reply_markup"]["inline_keyboard"][0][0]
        assert confirm_button["callback_data"] == f"{PRM_CONFIRM_PREFIX}:{context_id}:n"


def test_confirmed_action_receipt(monkeypatch):
    _CONTEXTS.clear()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]
        handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")

        result = handle_post_answer_callback(db_path, f"{PRM_CONFIRM_PREFIX}:{context_id}:n", chat_id="42")

        assert result["status"] == "ok"
        assert result["write_performed"] is True
        assert "Сохранено" in result["message"]
        assert "memory_id=" not in result["message"]


def test_restart_and_chat_isolation(monkeypatch):
    _CONTEXTS.clear()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]
        _CONTEXTS.clear()  # simulates process restart; durable state must remain usable

        wrong_chat = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="43")
        drafted = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")
        repeated = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")

        assert wrong_chat["status"] == "expired"
        assert drafted["status"] == "needs_confirmation"
        assert repeated["proposal"] == drafted["proposal"]


def test_expired_context_cannot_draft_or_confirm(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]
        with sqlite3.connect(db_path) as connection:
            connection.execute("UPDATE prm_post_answer_proposals SET expires_at = '2000-01-01T00:00:00Z' WHERE context_id = ?", (context_id,))

        result = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")
        confirm = handle_post_answer_callback(db_path, f"{PRM_CONFIRM_PREFIX}:{context_id}:n", chat_id="42")

        assert result["status"] == "expired"
        assert result["write_performed"] is False
        assert confirm["status"] == "expired"
        assert confirm["write_performed"] is False


def test_confirmation_idempotent(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]
        handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")

        first = handle_post_answer_callback(db_path, f"{PRM_CONFIRM_PREFIX}:{context_id}:n", chat_id="42")
        replay = handle_post_answer_callback(db_path, f"{PRM_CONFIRM_PREFIX}:{context_id}:n", chat_id="42")
        with sqlite3.connect(db_path) as connection:
            event_count = connection.execute("SELECT count(*) FROM personal_memory_events").fetchone()[0]

        assert first["write_performed"] is True
        assert replay["status"] == "already_confirmed"
        assert replay["write_performed"] is False
        assert event_count == 1


def test_feedback_action_no_config_or_external_mutation(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]

        result = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:u", chat_id="42")

        assert result["proposal"]["object_type"] == "feedback"
        assert result["write_performed"] is False
        assert os.path.exists(db_path)


def test_partial_feedback_prompts_for_reason_and_updates_private_receipt(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]

        prompt = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:m", chat_id="42")
        reason = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:ws", chat_id="42")

        assert prompt["status"] == "needs_reason"
        buttons = [button for row in prompt["reply_markup"]["inline_keyboard"] for button in row]
        assert "Не те источники" in {button["text"] for button in buttons}
        assert reason["status"] == "recorded"
        assert reason["write_performed"] is False


def test_private_receipt_write_failure_does_not_drop_answer(monkeypatch):
    def fail_receipt(*args, **kwargs):
        raise PermissionError("private trace directory is not writable")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        monkeypatch.setattr("assistant.prm_post_answer_actions.write_private_interaction_receipt", fail_receipt)
        run_migrations()

        result = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")

        assert result["context_id"]
        assert result["reply_markup"]
        with sqlite3.connect(db_path) as connection:
            status = connection.execute(
                "SELECT receipt_status FROM prm_post_answer_proposals WHERE context_id = ?",
                (result["context_id"],),
            ).fetchone()[0]

        assert status == "failed"
