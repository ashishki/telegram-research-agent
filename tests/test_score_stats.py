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


class TestScoreStatsCli(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}):
            run_migrations()
        return tmp.name

    def _insert_post(
        self,
        connection: sqlite3.Connection,
        *,
        post_id: int,
        bucket: str,
        signal_score: float,
        topic_label: str,
        posted_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO raw_posts (
                id, channel_username, channel_id, message_id, posted_at, text, media_type,
                media_caption, forward_from, view_count, message_url, raw_json, ingested_at, image_description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (post_id, "@stats", 2000 + post_id, 3000 + post_id, posted_at, "body", None, None, None, 50, None, "{}", posted_at, None),
        )
        connection.execute(
            """
            INSERT INTO posts (
                id, raw_post_id, channel_username, posted_at, content, url_count, has_code,
                language_detected, word_count, normalized_at, signal_score, bucket
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (post_id, post_id, "@stats", posted_at, f"{topic_label} content", 0, 0, "en", 20, posted_at, signal_score, bucket),
        )
        connection.execute(
            "INSERT INTO topics (id, label, description, first_seen, last_seen, post_count) VALUES (?, ?, ?, ?, ?, ?)",
            (post_id, topic_label, topic_label, posted_at, posted_at, 1),
        )
        connection.execute(
            "INSERT INTO post_topics (post_id, topic_id, confidence) VALUES (?, ?, ?)",
            (post_id, post_id, 0.9),
        )

    def test_score_stats_runs_on_empty_db(self):
        db_path = self._make_db()
        stdout = io.StringIO()

        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(sys, "argv", ["main.py", "score-stats"]):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
        finally:
            os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("strong: count=0", output)
        self.assertIn("noise: count=0", output)
        self.assertIn("top_topics: none", output)

    def test_score_stats_reports_bucket_counts(self):
        db_path = self._make_db()
        stdout = io.StringIO()
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        try:
            with sqlite3.connect(db_path) as connection:
                self._insert_post(connection, post_id=1, bucket="strong", signal_score=0.9, topic_label="llm", posted_at=now_iso)
                self._insert_post(connection, post_id=2, bucket="strong", signal_score=0.8, topic_label="agents", posted_at=now_iso)
                self._insert_post(connection, post_id=3, bucket="noise", signal_score=0.1, topic_label="memes", posted_at=now_iso)
                connection.commit()

            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(sys, "argv", ["main.py", "score-stats"]):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
        finally:
            os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("strong: count=2 avg_signal_score=0.8500", output)
        self.assertIn("watch: count=0 avg_signal_score=0.0000", output)
        self.assertIn("noise: count=1 avg_signal_score=0.1000", output)
        self.assertIn("top_topics: agents (1), llm (1), memes (1)", output)


if __name__ == "__main__":
    unittest.main()
