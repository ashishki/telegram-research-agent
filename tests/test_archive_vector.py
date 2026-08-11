from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from db.archive_search import ArchiveSearchFilters
from db.archive_vector import (
    LOCAL_EMBEDDING_MODEL,
    build_archive_vector_index,
    search_archive_vector_index,
    search_telegram_archive_hybrid,
)


def _make_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
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
        CREATE TABLE signal_feedback (
            id INTEGER PRIMARY KEY,
            post_id INTEGER NOT NULL,
            feedback TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE user_post_tags (
            id INTEGER PRIMARY KEY,
            post_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            note TEXT,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            keywords TEXT,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE post_project_links (
            post_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            relevance_score REAL NOT NULL,
            note TEXT,
            PRIMARY KEY(post_id, project_id)
        );
        """
    )
    return connection


def _insert_post(
    connection: sqlite3.Connection,
    *,
    post_id: int,
    channel_username: str,
    channel_id: int,
    message_id: int,
    posted_at: str,
    content: str,
    language: str = "ru",
) -> None:
    raw_post_id = post_id + 100
    source_url = f"https://t.me/{channel_username.lstrip('@')}/{message_id}"
    connection.execute(
        """
        INSERT INTO raw_posts (
            id, channel_username, channel_id, message_id, posted_at, message_url
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (raw_post_id, channel_username, channel_id, message_id, posted_at, source_url),
    )
    connection.execute(
        """
        INSERT INTO posts (
            id, raw_post_id, channel_username, posted_at, content,
            language_detected, word_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (post_id, raw_post_id, channel_username, posted_at, content, language, len(content.split())),
    )
    connection.execute(
        "INSERT INTO posts_fts(rowid, content) VALUES (?, ?)",
        (post_id, content),
    )


class TestArchiveVector(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = _make_connection()
        _insert_post(
            self.connection,
            post_id=1,
            channel_username="@ai_lab",
            channel_id=-1001,
            message_id=1001,
            posted_at="2026-08-01T10:00:00Z",
            content=(
                "AI transformation programs show ROI when companies redesign workflows, "
                "measure productivity, and move beyond pilots."
            ),
        )
        _insert_post(
            self.connection,
            post_id=2,
            channel_username="@hr_lab",
            channel_id=-1002,
            message_id=2002,
            posted_at="2026-08-02T10:00:00Z",
            content=(
                "Some companies announce layoffs while others keep hiring AI platform "
                "engineers for internal transformation."
            ),
        )
        self.connection.execute(
            "INSERT INTO signal_feedback (post_id, feedback, recorded_at) VALUES (?, ?, ?)",
            (1, "operator_liked", "2026-08-01T11:00:00Z"),
        )
        self.connection.execute(
            "INSERT INTO user_post_tags (post_id, tag, note, recorded_at) VALUES (?, ?, ?, ?)",
            (1, "roi", "fixture note", "2026-08-01T11:01:00Z"),
        )
        self.connection.execute(
            "INSERT INTO projects (id, name, description, keywords) VALUES (?, ?, ?, ?)",
            (10, "PRM-27", "local vector sidecar", "RAG vector retrieval"),
        )
        self.connection.execute(
            "INSERT INTO post_project_links (post_id, project_id, relevance_score, note) VALUES (?, ?, ?, ?)",
            (1, 10, 0.9, "fixture link"),
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_build_and_search_local_sidecar_without_canonical_mutation_or_egress(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "archive_vector.sqlite"
            before_count = self.connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0]

            payload = build_archive_vector_index(self.connection, index_path=index_path)
            results = search_archive_vector_index(
                index_path=index_path,
                query="AI transformation ROI productivity",
                limit=3,
            )

        after_count = self.connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        self.assertEqual(before_count, after_count)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["embedding_model"], LOCAL_EMBEDDING_MODEL)
        self.assertEqual(payload["source_rows_scanned"], 2)
        self.assertEqual(payload["inserted"], 2)
        self.assertFalse(payload["privacy"]["provider_egress"])
        self.assertFalse(payload["privacy"]["canonical_db_mutated"])
        self.assertTrue(payload["privacy"]["sidecar_write"])
        self.assertEqual(results[0].post_id, 1)
        result = results[0].as_dict()
        self.assertEqual(result["retrieval_mode"], "local_vector_archive")
        self.assertIn("semantic_score", result)

    def test_full_rebuild_deletes_stale_sidecar_documents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "archive_vector.sqlite"
            first = build_archive_vector_index(self.connection, index_path=index_path)
            self.assertEqual(first["inserted"], 2)

            self.connection.execute("DELETE FROM posts_fts WHERE rowid = ?", (2,))
            self.connection.execute("DELETE FROM posts WHERE id = ?", (2,))
            self.connection.execute("DELETE FROM raw_posts WHERE id = ?", (102,))
            second = build_archive_vector_index(self.connection, index_path=index_path)
            results = search_archive_vector_index(
                index_path=index_path,
                query="layoffs hiring",
                filters=ArchiveSearchFilters(channel_usernames=("@hr_lab",)),
                limit=3,
            )

        self.assertEqual(second["source_rows_scanned"], 1)
        self.assertGreaterEqual(second["deleted"], 1)
        self.assertEqual(results, [])

    def test_bounded_incremental_build_does_not_prune_outside_scan_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "archive_vector.sqlite"
            build_archive_vector_index(self.connection, index_path=index_path)
            limited = build_archive_vector_index(self.connection, index_path=index_path, limit=1)
            results = search_archive_vector_index(index_path=index_path, query="layoffs hiring", limit=3)

        self.assertEqual(limited["source_rows_scanned"], 1)
        self.assertEqual(limited["deleted"], 0)
        self.assertEqual(results[0].post_id, 2)

    def test_vector_filters_include_reaction_tags_and_project_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "archive_vector.sqlite"
            build_archive_vector_index(self.connection, index_path=index_path)
            results = search_archive_vector_index(
                index_path=index_path,
                query="AI transformation productivity",
                filters=ArchiveSearchFilters(
                    channel_usernames=("@ai_lab",),
                    reacted_only=True,
                    tags=("roi",),
                    project_names=("PRM-27",),
                ),
                limit=3,
            )

        self.assertEqual([result.post_id for result in results], [1])
        self.assertEqual(results[0].reaction_count, 1)
        self.assertEqual(results[0].tag_count, 1)
        self.assertEqual(results[0].project_names, ("PRM-27",))

    def test_hybrid_default_preserves_fts_precision_when_fts_has_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "archive_vector.sqlite"
            build_archive_vector_index(self.connection, index_path=index_path)
            results = search_telegram_archive_hybrid(
                self.connection,
                "AI transformation productivity",
                vector_index_path=index_path,
                limit=3,
            )

        self.assertEqual(results[0].post_id, 1)
        self.assertEqual(results[0].retrieval_mode, "hybrid_fts_only")
        self.assertEqual(results[0].fts_rank, 1)
        self.assertIsNone(results[0].vector_rank)
        self.assertGreater(results[0].fusion_score or 0.0, 0.0)

    def test_hybrid_always_policy_marks_fts_vector_provenance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "archive_vector.sqlite"
            build_archive_vector_index(self.connection, index_path=index_path)
            results = search_telegram_archive_hybrid(
                self.connection,
                "AI transformation productivity",
                vector_index_path=index_path,
                limit=3,
                vector_policy="always",
            )

        self.assertEqual(results[0].post_id, 1)
        self.assertEqual(results[0].retrieval_mode, "hybrid_fts_vector")
        self.assertEqual(results[0].fts_rank, 1)
        self.assertEqual(results[0].vector_rank, 1)
        self.assertGreater(results[0].fusion_score or 0.0, 0.0)


if __name__ == "__main__":
    unittest.main()
