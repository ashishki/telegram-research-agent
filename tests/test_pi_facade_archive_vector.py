from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from assistant.pi_facade import PersonalIntelligenceFacade
from config.settings import Settings
from db.archive_vector import build_archive_vector_index


def _seed_archive_db(db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(
            """
            CREATE TABLE raw_posts (
                id INTEGER PRIMARY KEY,
                channel_username TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                posted_at TEXT NOT NULL,
                raw_json TEXT NOT NULL DEFAULT '',
                ingested_at TEXT NOT NULL DEFAULT '2026-08-01T10:00:00Z',
                message_url TEXT,
                forward_from TEXT
            );
            CREATE TABLE posts (
                id INTEGER PRIMARY KEY,
                raw_post_id INTEGER NOT NULL UNIQUE,
                channel_username TEXT NOT NULL,
                posted_at TEXT NOT NULL,
                content TEXT NOT NULL,
                url_count INTEGER NOT NULL DEFAULT 0,
                has_code INTEGER NOT NULL DEFAULT 0,
                language_detected TEXT,
                word_count INTEGER NOT NULL DEFAULT 0,
                normalized_at TEXT NOT NULL DEFAULT '2026-08-01T10:00:00Z'
            );
            CREATE VIRTUAL TABLE posts_fts USING fts5(
                content,
                content='posts',
                content_rowid='id'
            );
            """
        )
        content = "AI transformation ROI improves when companies redesign workflows."
        connection.execute(
            """
            INSERT INTO raw_posts (
                id, channel_username, channel_id, message_id, posted_at, message_url
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (101, "@ai_lab", -1001, 1001, "2026-08-01T10:00:00Z", "https://t.me/ai_lab/1001"),
        )
        connection.execute(
            """
            INSERT INTO posts (
                id, raw_post_id, channel_username, posted_at, content,
                language_detected, word_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (1, 101, "@ai_lab", "2026-08-01T10:00:00Z", content, "en", len(content.split())),
        )
        connection.execute("INSERT INTO posts_fts(rowid, content) VALUES (?, ?)", (1, content))
        connection.commit()
    finally:
        connection.close()


class TestPiFacadeArchiveVector(unittest.TestCase):
    def test_hybrid_archive_search_redacts_vector_path_and_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "agent.db"
            index_path = root / "archive-vector.sqlite"
            _seed_archive_db(db_path)
            connection = sqlite3.connect(db_path)
            connection.row_factory = sqlite3.Row
            try:
                build_archive_vector_index(connection, index_path=index_path)
            finally:
                connection.close()
            facade = PersonalIntelligenceFacade(
                settings=Settings(
                    db_path=str(db_path),
                    llm_api_key="",
                    model_provider="",
                    telegram_session_path="",
                ),
                output_root=root,
            )

            result = facade.search_telegram_archive(
                "AI transformation ROI",
                filters={"retrieval_mode": "hybrid", "vector_index_path": str(index_path)},
                limit=3,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["retrieval_mode"], "hybrid_local_vector_archive")
        self.assertNotIn("vector_index_path", result["filters"])
        self.assertTrue(result["filters"]["vector_index_path_configured"])
        self.assertEqual(result["items"][0]["retrieval_mode"], "hybrid_fts_only")
        self.assertIn("FTS-first hybrid", result["message"])


if __name__ == "__main__":
    unittest.main()
