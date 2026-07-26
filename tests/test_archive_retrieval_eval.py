import sqlite3
import unittest

from db.archive_retrieval_eval import (
    METRIC_FIELDS,
    evaluate_archive_retrieval,
    validate_archive_retrieval_eval_report,
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
            ingested_at TEXT NOT NULL DEFAULT '2026-07-20T10:00:00Z',
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
            normalized_at TEXT NOT NULL DEFAULT '2026-07-20T10:00:00Z'
        );
        CREATE VIRTUAL TABLE posts_fts USING fts5(
            content,
            content='posts',
            content_rowid='id'
        );
        CREATE TABLE reaction_sync_state (
            source TEXT NOT NULL,
            channel_username TEXT NOT NULL,
            message_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            action_key TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            PRIMARY KEY(source, channel_username, message_id, emoji, action_key)
        );
        """
    )
    return connection


def _seed_post(
    connection: sqlite3.Connection,
    *,
    post_id: int,
    content: str,
    channel_id: int = -1001,
    message_id: int | None = None,
) -> None:
    raw_post_id = 10_000 + post_id
    resolved_message_id = message_id if message_id is not None else 9000 + post_id
    connection.execute(
        """
        INSERT INTO raw_posts (
            id, channel_username, channel_id, message_id, posted_at,
            message_url, forward_from
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            raw_post_id,
            "@source",
            channel_id,
            resolved_message_id,
            "2026-07-20T10:00:00Z",
            f"https://t.me/source/{resolved_message_id}",
            "",
        ),
    )
    connection.execute(
        """
        INSERT INTO posts (
            id, raw_post_id, channel_username, posted_at, content,
            language_detected, word_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            post_id,
            raw_post_id,
            "@source",
            "2026-07-20T10:00:00Z",
            content,
            "en",
            len(content.split()),
        ),
    )
    connection.execute(
        "INSERT INTO posts_fts(rowid, content) VALUES (?, ?)",
        (post_id, content),
    )


class TestArchiveRetrievalEval(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = _make_connection()

    def tearDown(self) -> None:
        self.connection.close()

    def test_eval_separates_gold_and_candidate_rows(self):
        _seed_post(self.connection, post_id=1, content="Alpha retrieval baseline source.")
        _seed_post(self.connection, post_id=2, content="Beta retrieval baseline source.")

        report = evaluate_archive_retrieval(
            self.connection,
            [
                {
                    "case_id": "GOLD-001",
                    "category": "exact_known_item",
                    "language": "en",
                    "query": "alpha retrieval",
                    "human_approved": True,
                    "expected_post_ids": [1],
                },
                {
                    "case_id": "CAND-001",
                    "category": "semantic_topic",
                    "language": "en",
                    "query": "beta retrieval",
                    "human_approved": False,
                },
            ],
        )
        validate_archive_retrieval_eval_report(report)

        self.assertEqual(report["dataset"]["gold_row_count"], 1)
        self.assertEqual(report["dataset"]["candidate_row_count"], 1)
        self.assertEqual(report["gold"]["metrics"]["hit_at_10"], 1.0)
        self.assertEqual(report["gold"]["metrics"]["mrr"], 1.0)
        self.assertEqual(
            report["dataset"]["candidate_unapproved_case_ids"],
            ["CAND-001"],
        )
        self.assertNotIn("query", report["gold"]["rows"][0])
        self.assertNotIn("query", report["candidates"]["rows"][0])
        self.assertFalse(report["vector_backend_gate"]["vector_backend_adopted"])

    def test_metrics_are_present_when_no_gold_exists(self):
        _seed_post(self.connection, post_id=1, content="Gamma retrieval baseline source.")
        self.connection.execute(
            """
            INSERT INTO reaction_sync_state (
                source, channel_username, message_id, emoji, action_key, applied_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "telegram_reaction",
                "@source",
                9001,
                "+",
                "tag:interesting|feedback:operator_marked_interesting",
                "2026-07-20T11:00:00Z",
            ),
        )

        report = evaluate_archive_retrieval(
            self.connection,
            [
                {
                    "case_id": "CAND-001",
                    "category": "reaction",
                    "language": "en",
                    "query": "gamma retrieval",
                    "human_approved": False,
                }
            ],
        )

        metrics = report["gold"]["metrics"]
        self.assertEqual(metrics["status"], "not_scored_no_human_approved_gold")
        for field in METRIC_FIELDS:
            self.assertIn(field, metrics)
        self.assertEqual(report["candidates"]["diagnostics"]["reacted_post_searchability"], 1.0)
        self.assertEqual(
            report["vector_backend_gate"]["status"],
            "blocked_no_human_approved_gold",
        )

    def test_no_answer_and_stale_rejection_metrics_are_scored_for_gold(self):
        _seed_post(self.connection, post_id=1, content="Delta retrieval baseline source.")

        report = evaluate_archive_retrieval(
            self.connection,
            [
                {
                    "case_id": "GOLD-NOANSWER",
                    "category": "no_answer",
                    "language": "en",
                    "query": "unmatchedterm",
                    "human_approved": True,
                    "expected_no_answer": True,
                },
                {
                    "case_id": "GOLD-STALE",
                    "category": "freshness_news",
                    "language": "en",
                    "query": "delta retrieval",
                    "human_approved": True,
                    "expected_post_ids": [1],
                    "stale_post_ids": [99],
                },
            ],
        )

        self.assertEqual(report["gold"]["metrics"]["no_answer_accuracy"], 1.0)
        self.assertEqual(report["gold"]["metrics"]["stale_rejection"], 1.0)
        self.assertEqual(report["privacy"]["raw_telegram_text_printed"], False)


if __name__ == "__main__":
    unittest.main()
