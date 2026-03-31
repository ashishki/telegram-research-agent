import io
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
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

from db.migrate import run_migrations  # noqa: E402
import main  # noqa: E402


class TestReportPreviewCli(unittest.TestCase):
    def test_report_preview_with_empty_db_prints_no_posts(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        stdout = io.StringIO()

        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                run_migrations()

            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(sys, "argv", ["main.py", "report-preview"]):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
        finally:
            os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("No scored posts found", output)

    def test_report_preview_with_strong_post_prints_strong_signals(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        stdout = io.StringIO()

        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                run_migrations()

            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO raw_posts (
                        id, channel_username, channel_id, message_id, posted_at, text, media_type,
                        media_caption, forward_from, view_count, message_url, raw_json, ingested_at, image_description
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (1, "@preview", 3001, 4001, now_iso, "body", None, None, None, 0, None, "{}", now_iso, None),
                )
                connection.execute(
                    """
                    INSERT INTO posts (
                        id, raw_post_id, channel_username, posted_at, content, url_count, has_code,
                        language_detected, word_count, normalized_at, signal_score, bucket,
                        routed_model, score_breakdown, scored_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        1,
                        "@preview",
                        now_iso,
                        "A strong post about agent workflows and signal filtering",
                        0,
                        0,
                        "en",
                        9,
                        now_iso,
                        0.91,
                        "strong",
                        "claude-opus-4-6",
                        "{}",
                        now_iso,
                    ),
                )
                connection.commit()

            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(sys, "argv", ["main.py", "report-preview"]):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
        finally:
            os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("## Strong Signals", output)


if __name__ == "__main__":
    unittest.main()
