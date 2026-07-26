import sqlite3
import unittest

from db.archive_search import search_telegram_archive
from output.selective_enrichment import (
    EnrichmentBudget,
    build_enrichment_queue,
    run_selective_enrichment_batch,
    validate_selective_enrichment_receipt,
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
        """
    )
    return connection


def _seed_archive_post(connection: sqlite3.Connection, *, post_id: int) -> None:
    raw_post_id = 10_000 + post_id
    message_id = 8000 + post_id
    content = (
        f"Selective enrichment fixture {post_id} remains searchable "
        "after extraction failure."
    )
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
            -1001,
            message_id,
            "2026-07-20T10:00:00Z",
            f"https://t.me/source/{message_id}",
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


class TestSelectiveEnrichment(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = _make_connection()

    def tearDown(self) -> None:
        self.connection.close()

    def test_priority_order_covers_all_signal_sources(self):
        queue = build_enrichment_queue(
            [
                {"post_id": 7, "source": "manual_save"},
                {"post_id": 6, "source": "repeated_signal"},
                {"post_id": 5, "source": "active_project"},
                {"post_id": 4, "source": "watch_topic"},
                {"post_id": 3, "source": "cited_answer"},
                {"post_id": 2, "source": "repeated_search_return"},
                {"post_id": 1, "source": "reaction"},
            ]
        )

        self.assertEqual([item.post_id for item in queue], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(
            [item.primary_source for item in queue],
            [
                "reaction",
                "repeated_search_return",
                "cited_answer",
                "watch_topic",
                "active_project",
                "repeated_signal",
                "manual_save",
            ],
        )

    def test_extraction_failure_keeps_archive_search_available(self):
        _seed_archive_post(self.connection, post_id=1)
        queue = build_enrichment_queue([{"post_id": 1, "source": "reaction"}])

        def failing_extractor(_item):
            raise RuntimeError("provider unavailable")

        receipt = run_selective_enrichment_batch(
            self.connection,
            queue,
            extractor=failing_extractor,
            budget=EnrichmentBudget(max_cost_usd=5.0, max_model_calls=10, max_retries=0),
        )
        validate_selective_enrichment_receipt(receipt)

        self.assertEqual(receipt["status"], "partial")
        self.assertEqual(receipt["counts"]["failed_posts"], 1)
        self.assertEqual(receipt["counts"]["archive_search_available_after_failure"], 1)
        self.assertEqual(receipt["items"][0]["failure_reason"], "extractor_failed")
        self.assertTrue(receipt["items"][0]["archive_search_available"])
        self.assertFalse(receipt["privacy"]["raw_text_included"])

        results = search_telegram_archive(self.connection, "selective failure", limit=5)
        self.assertEqual([result.post_id for result in results], [1])

    def test_cost_cap_stops_before_retry_exceeds_budget(self):
        _seed_archive_post(self.connection, post_id=1)
        queue = build_enrichment_queue([{"post_id": 1, "source": "reaction"}])
        calls: list[int] = []

        def failing_extractor(_item):
            calls.append(1)
            raise RuntimeError("provider unavailable")

        receipt = run_selective_enrichment_batch(
            self.connection,
            queue,
            extractor=failing_extractor,
            budget=EnrichmentBudget(
                max_cost_usd=3.0,
                max_model_calls=100,
                max_retries=3,
                estimated_cost_per_attempt_usd=2.0,
            ),
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(receipt["status"], "stopped_budget")
        self.assertEqual(receipt["stopped_reason"], "cost_cap_exceeded")
        self.assertEqual(receipt["counts"]["model_calls"], 1)
        self.assertEqual(receipt["counts"]["estimated_cost_usd"], 2.0)
        self.assertEqual(receipt["counts"]["stopped_budget_posts"], 1)
        self.assertFalse(receipt["budget"]["cost_cap_exceeded"])
        self.assertEqual(receipt["items"][0]["failure_reason"], "cost_cap_exceeded")


if __name__ == "__main__":
    unittest.main()
