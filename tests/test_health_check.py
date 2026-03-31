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


class TestHealthCheckCli(unittest.TestCase):
    def test_health_check_with_real_db_prints_counts(self):
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
                    (1, "@health", 1001, 2001, now_iso, "body", None, None, None, 0, None, "{}", now_iso, None),
                )
                connection.execute(
                    """
                    INSERT INTO posts (
                        id, raw_post_id, channel_username, posted_at, content, url_count, has_code,
                        language_detected, word_count, normalized_at, signal_score, bucket, scored_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (1, 1, "@health", now_iso, "strong signal", 0, 0, "en", 2, now_iso, 0.9, "strong", now_iso),
                )
                connection.execute(
                    """
                    INSERT INTO llm_usage (
                        model, task_type, input_tokens, output_tokens, est_cost_usd,
                        called_at, category, cost_usd, duration_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("claude-haiku-4-5", "test", 10, 5, 0.01, now_iso, "test", 0.01, 5),
                )
                connection.commit()

            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(sys, "argv", ["main.py", "health-check"]):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
        finally:
            os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("posts:", output)
        self.assertIn("llm_usage:", output)

    def test_health_check_without_db_path_prints_not_configured(self):
        stdout = io.StringIO()

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(sys, "argv", ["main.py", "health-check"]):
                with redirect_stdout(stdout):
                    exit_code = main.main()

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("DB_PATH not configured", output)


if __name__ == "__main__":
    unittest.main()
