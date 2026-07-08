import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from config.settings import Settings
from db.migrate import run_migrations
from output.operator_reminders import (
    create_reminder,
    format_daily_reminder_digest,
    list_pending_reminders,
    parse_reminder_request,
    send_daily_reminder_digest,
)


class TestOperatorReminders(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "test.db")
        os.environ["AGENT_DB_PATH"] = self.db_path
        run_migrations()
        self.settings = Settings(
            db_path=self.db_path,
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

    def tearDown(self):
        del os.environ["AGENT_DB_PATH"]
        self.tmpdir.cleanup()

    def test_parse_reminder_request_extracts_tomorrow_task(self):
        now = datetime(2026, 7, 8, 8, 0, tzinfo=timezone.utc)
        with patch.dict(os.environ, {"REMINDER_TIMEZONE": ""}, clear=False):
            parsed = parse_reminder_request("напомни завтра 18:00 дать feedback по Workbook", now=now)

        self.assertEqual(parsed.text, "дать feedback по Workbook")
        self.assertEqual(parsed.reminder_type, "feedback")
        self.assertEqual(parsed.timezone_name, "Asia/Tbilisi")
        self.assertEqual(parsed.due_at, "2026-07-09T14:00:00Z")

    def test_create_and_list_pending_reminders(self):
        with sqlite3.connect(self.db_path) as connection:
            reminder = create_reminder(
                connection,
                due_at="2026-07-08T10:00:00Z",
                text="почитать Workbook",
                source_text="напомни почитать Workbook",
            )
            rows = list_pending_reminders(connection)

        self.assertEqual(reminder["status"], "pending")
        self.assertEqual(rows[0]["id"], reminder["id"])
        self.assertEqual(rows[0]["reminder_type"], "read_watch")
        self.assertIn("last_prompted_at", rows[0])

    def test_send_daily_digest_sends_once_and_keeps_pending_until_button(self):
        with sqlite3.connect(self.db_path) as connection:
            reminder = create_reminder(
                connection,
                due_at="2026-07-08T10:00:00Z",
                text="дать feedback по Workbook",
                reminder_type="feedback",
            )

        captured = {}

        def fake_send_text(**kwargs):
            captured.update(kwargs)
            return 55

        now = datetime(2026, 7, 8, 16, 30, tzinfo=timezone.utc)
        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_OWNER_CHAT_ID": "42", "REMINDER_TIMEZONE": "Asia/Tbilisi"},
            clear=False,
        ), patch("output.operator_reminders.send_text", side_effect=fake_send_text):
            result = send_daily_reminder_digest(self.settings, now=now)
            second = send_daily_reminder_digest(self.settings, now=now)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["prompted"], 1)
        self.assertEqual(second["status"], "empty")
        self.assertIn("дневной чек-ин", captured["text"])
        self.assertIn("2026-07-08 Asia/Tbilisi", captured["text"])
        self.assertIn("Когда: 2026-07-08 14:00 Asia/Tbilisi", captured["text"])
        self.assertIn("дать feedback по Workbook", captured["text"])
        callbacks = [
            button["callback_data"]
            for row in captured["reply_markup"]["inline_keyboard"]
            for button in row
        ]
        self.assertIn(f"rem:{reminder['id']}:done", callbacks)
        self.assertIn(f"rem:{reminder['id']}:not", callbacks)

        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT status, last_prompted_at FROM operator_reminders WHERE id = ?",
                (reminder["id"],),
            ).fetchone()

        self.assertEqual(row["status"], "pending")
        self.assertIsNotNone(row["last_prompted_at"])

    def test_send_daily_digest_missing_credentials_is_explicit(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_OWNER_CHAT_ID": ""}, clear=False):
            result = send_daily_reminder_digest(self.settings)

        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["prompted"], 0)

    def test_format_daily_digest_is_compact(self):
        text = format_daily_reminder_digest(
            [
                {
                    "id": 1,
                    "due_at": "2026-07-08T10:00:00Z",
                    "text": "посмотреть источник",
                    "reminder_type": "read_watch",
                }
            ],
            now=datetime(2026, 7, 8, 18, 30, tzinfo=timezone.utc),
            timezone_name="Asia/Tbilisi",
        )

        self.assertIn("Hermes: дневной чек-ин", text)
        self.assertIn("2026-07-08 Asia/Tbilisi", text)
        self.assertIn("1. [read/watch] посмотреть источник", text)
        self.assertIn("Когда: 2026-07-08 14:00 Asia/Tbilisi", text)
        self.assertIn("сделал / не сделал", text)


if __name__ == "__main__":
    unittest.main()
