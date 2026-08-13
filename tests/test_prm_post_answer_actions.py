import os
import tempfile

from assistant.prm_post_answer_actions import (
    PRM_ACTION_PREFIX,
    PRM_CONFIRM_PREFIX,
    _CONTEXTS,
    build_post_answer_actions,
    handle_post_answer_callback,
)
from db.migrate import run_migrations


def _answer(*, project_name: str = "") -> dict:
    return {
        "question": "как улучшить eval gates?",
        "direct_answer": "Добавить один regression case.",
        "source_refs": ["https://t.me/example/1"],
        "project_name": project_name,
    }


def test_action_markup_relevant_and_bounded():
    _CONTEXTS.clear()
    markup = build_post_answer_actions(_answer(project_name="telegram-research-agent"))["reply_markup"]
    buttons = [button for row in markup["inline_keyboard"] for button in row]

    assert {button["text"] for button in buttons}.issuperset({"Сохранить заметку", "Следить", "Отметить полезным"})
    assert {button["text"] for button in buttons}.issuperset({"Связать с проектом", "Создать действие", "Создать эксперимент"})
    assert all(button["callback_data"].startswith(f"{PRM_ACTION_PREFIX}:") for button in buttons)
    assert all(len(button["callback_data"]) <= 64 for button in buttons)


def test_proposal_before_write():
    _CONTEXTS.clear()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        context_id = build_post_answer_actions(_answer())["context_id"]

        result = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n")

        assert result["status"] == "needs_confirmation"
        assert result["write_performed"] is False
        assert not os.path.exists(db_path)
        confirm_button = result["reply_markup"]["inline_keyboard"][0][0]
        assert confirm_button["callback_data"] == f"{PRM_CONFIRM_PREFIX}:{context_id}:n"


def test_confirmed_action_receipt(monkeypatch):
    _CONTEXTS.clear()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer())["context_id"]
        handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n")

        result = handle_post_answer_callback(db_path, f"{PRM_CONFIRM_PREFIX}:{context_id}:n")

        assert result["status"] == "ok"
        assert result["write_performed"] is True
        assert "memory_id=" in result["message"]
        assert "event_id=" in result["message"]


def test_feedback_action_no_config_or_external_mutation():
    _CONTEXTS.clear()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        context_id = build_post_answer_actions(_answer())["context_id"]

        result = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:u")

        assert result["proposal"]["object_type"] == "feedback"
        assert result["write_performed"] is False
        assert not os.path.exists(db_path)
