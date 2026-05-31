import os
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def _install_stub(module_name: str, **attributes: object) -> None:
    module = sys.modules.get(module_name)
    if module is None:
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module
    for name, value in attributes.items():
        setattr(module, name, value)


_install_stub(
    "anthropic",
    APIConnectionError=Exception,
    APIStatusError=Exception,
    APITimeoutError=Exception,
    Anthropic=object,
    RateLimitError=Exception,
)
_install_stub("telethon", TelegramClient=object)
_install_stub("telethon.errors", FloodWaitError=Exception)
_install_stub("weasyprint")
_install_stub("jinja2")

from bot import bot as bot_runtime
from bot.callbacks import build_idea_feedback_markup, record_idea_callback
from config.settings import Settings


class TestIdeaCallbacks(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "test.db")
        os.environ["AGENT_DB_PATH"] = self.db_path

    def tearDown(self):
        del os.environ["AGENT_DB_PATH"]
        self.tmpdir.cleanup()

    def _settings_with_idea(self) -> Settings:
        from db.migrate import run_migrations

        run_migrations()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO insight_triage_records (
                    id, week_label, title, idea_type, timing, implementation_mode,
                    confidence, evidence_strength, main_risk, recommendation,
                    reason, source_url, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    7,
                    "2026-W18",
                    "[Implement] telegram-research-agent — Add reaction feedback",
                    "implement",
                    "now",
                    "extend",
                    "high",
                    "strong",
                    "low",
                    "do_now",
                    "useful",
                    "https://t.me/source/1",
                    "2026-05-01T00:00:00Z",
                ),
            )
            connection.commit()
        return Settings(db_path=self.db_path, llm_api_key="", model_provider="anthropic", telegram_session_path="")

    def test_markup_uses_compact_callback_payloads(self):
        markup = build_idea_feedback_markup(7)
        callbacks = [
            button["callback_data"]
            for row in markup["inline_keyboard"]
            for button in row
        ]

        self.assertIn("idea:7:done", callbacks)
        self.assertIn("idea:7:later", callbacks)
        self.assertIn("idea:7:reject", callbacks)
        self.assertTrue(all(len(value) <= 64 for value in callbacks))

    def test_record_idea_callback_writes_user_decision(self):
        settings = self._settings_with_idea()
        answer = record_idea_callback(settings, "idea:7:reject")

        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT decision_scope, subject_ref_type, subject_ref_id, project_name, status, recorded_by
                FROM decision_journal
                WHERE subject_ref_id = '7'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        self.assertEqual(answer, "Записал: rejected")
        self.assertEqual(row["decision_scope"], "insight")
        self.assertEqual(row["subject_ref_type"], "insight_triage_id")
        self.assertEqual(row["project_name"], "telegram-research-agent")
        self.assertEqual(row["status"], "rejected")
        self.assertEqual(row["recorded_by"], "telegram_button")

    def test_run_bot_dispatches_authorized_callback_update(self):
        settings = self._settings_with_idea()
        update = {
            "update_id": 100,
            "callback_query": {
                "id": "callback-1",
                "from": {"id": 12345},
                "message": {"chat": {"id": 12345}},
                "data": "idea:7:done",
            },
        }

        def stop_after_first_poll(state):
            state.stop_requested = True

        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_OWNER_CHAT_ID": "12345"},
            clear=False,
        ), patch.object(bot_runtime, "_install_signal_handlers", side_effect=stop_after_first_poll), patch.object(
            bot_runtime,
            "_telegram_get_updates",
            return_value=[update],
        ) as get_updates_mock, patch.object(
            bot_runtime,
            "record_idea_callback",
            return_value="Записал: acted_on",
        ) as record_mock, patch.object(
            bot_runtime,
            "_telegram_answer_callback",
        ) as answer_mock:
            bot_runtime.run_bot(settings)

        get_updates_mock.assert_called_once_with(token="token", offset=None)
        record_mock.assert_called_once_with(settings, "idea:7:done")
        answer_mock.assert_called_once_with("token", "callback-1", "Записал: acted_on")


if __name__ == "__main__":
    unittest.main()
