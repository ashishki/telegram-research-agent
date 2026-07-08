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
from bot.callbacks import (
    build_artifact_feedback_markup,
    build_idea_feedback_markup,
    record_artifact_callback,
    record_idea_callback,
)
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

    def test_artifact_feedback_markup_uses_compact_callback_payloads(self):
        markup = build_artifact_feedback_markup("2026-W18", "research_brief")
        callbacks = [
            button["callback_data"]
            for row in markup["inline_keyboard"]
            for button in row
        ]

        self.assertIn("art:2026-W18:rb:u", callbacks)
        self.assertIn("art:2026-W18:rb:d", callbacks)
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

    def test_record_artifact_callback_writes_artifact_feedback(self):
        settings = self._settings_with_idea()
        answer = record_artifact_callback(settings, "art:2026-W18:rb:a")

        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT week_label, artifact_type, feedback, recorded_by
                FROM artifact_feedback_logs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        self.assertEqual(answer, "Записал: decision_impacting")
        self.assertEqual(row["week_label"], "2026-W18")
        self.assertEqual(row["artifact_type"], "research_brief")
        self.assertEqual(row["feedback"], "decision_impacting")
        self.assertEqual(row["recorded_by"], "telegram_button")

    def test_record_artifact_defer_button_records_note(self):
        settings = self._settings_with_idea()
        record_artifact_callback(settings, "art:2026-W18:ii:d")

        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT artifact_type, feedback, notes
                FROM artifact_feedback_logs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        self.assertEqual(row["artifact_type"], "implementation_ideas")
        self.assertEqual(row["feedback"], "weak")
        self.assertEqual(row["notes"], "deferred_from_button")

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
            "record_callback",
            return_value="Записал: acted_on",
        ) as record_mock, patch.object(
            bot_runtime,
            "_telegram_answer_callback",
        ) as answer_mock:
            bot_runtime.run_bot(settings)

        get_updates_mock.assert_called_once_with(token="token", offset=None)
        record_mock.assert_called_once_with(settings, "idea:7:done")
        answer_mock.assert_called_once_with("token", "callback-1", "Записал: acted_on")

    def test_run_bot_dispatches_transcribed_voice_feedback(self):
        settings = self._settings_with_idea()
        update = {
            "update_id": 101,
            "message": {
                "chat": {"id": 12345},
                "from": {"id": 12345},
                "voice": {"file_id": "voice-1"},
                "caption": "Too shallow target=eval-gates.",
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
        ), patch.object(
            bot_runtime,
            "dispatch_command",
        ) as dispatch_mock:
            bot_runtime.run_bot(settings)

        dispatch_mock.assert_called_once_with(
            chat_id="12345",
            text="/feedback_voice Too shallow target=eval-gates.",
            settings=settings,
        )

    def test_run_bot_dispatches_plain_text_to_hermes_chat(self):
        settings = self._settings_with_idea()
        update = {
            "update_id": 104,
            "message": {
                "chat": {"id": 12345},
                "from": {"id": 12345},
                "text": "Что мне делать с weekly workbook?",
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
        ), patch.object(
            bot_runtime,
            "dispatch_command",
        ) as dispatch_mock:
            bot_runtime.run_bot(settings)

        dispatch_mock.assert_called_once_with(
            chat_id="12345",
            text="/chat Что мне делать с weekly workbook?",
            settings=settings,
        )

    def test_run_bot_voice_without_transcript_runs_transcription(self):
        settings = self._settings_with_idea()
        update = {
            "update_id": 102,
            "message": {
                "chat": {"id": 12345},
                "from": {"id": 12345},
                "voice": {"file_id": "voice-1"},
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
        ), patch.object(
            bot_runtime,
            "dispatch_command",
        ) as dispatch_mock, patch.object(
            bot_runtime,
            "send_message",
        ) as send_message_mock, patch.object(
            bot_runtime,
            "transcribe_telegram_voice",
            return_value="Useful workbook. target=claim-cards.",
        ) as transcribe_mock:
            bot_runtime.run_bot(settings)

        send_message_mock.assert_called_once()
        self.assertIn("Распознаю", send_message_mock.call_args.args[2])
        transcribe_mock.assert_called_once_with(token="token", file_id="voice-1")
        dispatch_mock.assert_called_once_with(
            chat_id="12345",
            text="/feedback_voice Useful workbook. target=claim-cards.",
            settings=settings,
        )

    def test_run_bot_voice_without_openai_key_returns_text_fallback(self):
        settings = self._settings_with_idea()
        update = {
            "update_id": 103,
            "message": {
                "chat": {"id": 12345},
                "from": {"id": 12345},
                "voice": {"file_id": "voice-1"},
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
        ), patch.object(
            bot_runtime,
            "dispatch_command",
        ) as dispatch_mock, patch.object(
            bot_runtime,
            "send_message",
        ) as send_message_mock, patch.object(
            bot_runtime,
            "transcribe_telegram_voice",
            side_effect=bot_runtime.VoiceTranscriptionUnavailable("OPENAI_API_KEY is not set"),
        ):
            bot_runtime.run_bot(settings)

        dispatch_mock.assert_not_called()
        self.assertEqual(send_message_mock.call_count, 2)
        fallback_message = send_message_mock.call_args_list[-1].args[2]
        self.assertIn("OPENAI_API_KEY", fallback_message)
        self.assertIn("/feedback_voice <твой фидбек>", fallback_message)


if __name__ == "__main__":
    unittest.main()
