import io
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
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
_install_stub("numpy", asarray=lambda value: value)
_install_stub("sklearn")
_install_stub("sklearn.cluster", KMeans=object)
_install_stub("sklearn.feature_extraction")
_install_stub("sklearn.feature_extraction.text", ENGLISH_STOP_WORDS=set(), TfidfVectorizer=object)
_install_stub("sklearn.metrics", silhouette_score=lambda *_args, **_kwargs: 0.0)

from db.migrate import run_migrations  # noqa: E402
from output.source_trust import explain_source_downrank, format_source_downrank_explanations  # noqa: E402
import main  # noqa: E402


class TestSourceTrust(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def _seed_source_rows(self, connection: sqlite3.Connection) -> None:
        connection.executemany(
            """
            INSERT INTO raw_posts (
                id, channel_username, channel_id, message_id, posted_at, text, raw_json, ingested_at, message_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "noisy_source", 1, 101, "2026-05-20T10:00:00Z", "noise", "{}", "2026-05-20T10:01:00Z", ""),
                (2, "noisy_source", 1, 102, "2026-05-21T10:00:00Z", "noise", "{}", "2026-05-21T10:01:00Z", "https://t.me/noisy_source/102"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO posts (
                id, raw_post_id, channel_username, content, posted_at, normalized_at, bucket, project_relevance_score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 1, "noisy_source", "noise", "2026-05-20T10:00:00Z", "2026-05-20T10:01:00Z", "noise", 0.0),
                (2, 2, "noisy_source", "noise", "2026-05-21T10:00:00Z", "2026-05-21T10:01:00Z", "noise", 0.0),
            ],
        )
        connection.execute(
            """
            INSERT INTO user_post_tags (post_id, tag, note, recorded_at)
            VALUES (?, ?, ?, ?)
            """,
            (1, "low_signal", "bad", "2026-05-22T10:00:00Z"),
        )
        connection.execute(
            """
            INSERT INTO signal_feedback (post_id, feedback, recorded_at)
            VALUES (?, ?, ?)
            """,
            (1, "skipped", "2026-05-23T10:00:00Z"),
        )
        connection.execute(
            """
            INSERT INTO source_observations (
                channel_username,
                week_label,
                low_signal_count,
                rejected_count,
                skipped_count,
                counters_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("noisy_source", "2026-W21", 2, 1, 1, "{}", "2026-05-24T10:00:00Z", "2026-05-24T10:00:00Z"),
        )
        connection.commit()

    def test_source_downrank_explanations_use_observed_local_signals(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                self._seed_source_rows(connection)
                explanations = explain_source_downrank(connection, channel="noisy_source", days=30)
        finally:
            os.unlink(db_path)

        self.assertEqual(len(explanations), 1)
        reasons = explanations[0]["reason_counts"]
        self.assertEqual(reasons["many_posts_scored_noise"], 2)
        self.assertEqual(reasons["missing_source_links"], 1)
        self.assertEqual(reasons["operator_low_signal_tags"], 1)
        self.assertEqual(reasons["operator_skipped_feedback"], 1)
        self.assertEqual(reasons["source_observation_rejected"], 1)
        self.assertIn("noisy_source", format_source_downrank_explanations(explanations))

    def test_source_downrank_cli_prints_reason_counts(self):
        db_path = self._make_db()
        stdout = io.StringIO()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                self._seed_source_rows(connection)
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(
                    sys,
                    "argv",
                    [
                        "main.py",
                        "memory",
                        "explain-source-downrank",
                        "--channel",
                        "noisy_source",
                        "--days",
                        "30",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
        finally:
            os.unlink(db_path)

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("Source noisy_source", output)
        self.assertIn("many_posts_scored_noise: 2", output)
        self.assertIn("missing_source_links: 1", output)


if __name__ == "__main__":
    unittest.main()
