import sqlite3
import unittest

from db.archive_search import search_telegram_archive
from db.reaction_fast_lane import (
    build_reaction_fast_lane_receipt,
    classify_reaction_semantics,
    validate_reaction_fast_lane_receipt,
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
        CREATE TABLE signal_feedback (
            id INTEGER PRIMARY KEY,
            post_id INTEGER NOT NULL,
            feedback TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE knowledge_atoms (
            id INTEGER PRIMARY KEY,
            source_post_ids_json TEXT NOT NULL,
            source_urls_json TEXT NOT NULL
        );
        CREATE TABLE post_topics (
            post_id INTEGER NOT NULL,
            topic_id INTEGER NOT NULL,
            confidence REAL NOT NULL,
            PRIMARY KEY(post_id, topic_id)
        );
        """
    )
    return connection


def _seed_reacted_archive_post(
    connection: sqlite3.Connection,
    *,
    post_id: int,
    channel_username: str = "@source",
    channel_id: int = -1001,
    message_id: int | None = None,
    emoji: str = "+",
) -> None:
    resolved_message_id = message_id if message_id is not None else 7000 + post_id
    raw_post_id = 10_000 + post_id
    content = (
        f"Reaction fastlane searchable archive fixture {post_id} "
        "with retained post context."
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
            channel_username,
            channel_id,
            resolved_message_id,
            "2026-07-20T10:00:00Z",
            f"https://t.me/{channel_username.lstrip('@')}/{resolved_message_id}",
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
            channel_username,
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
    connection.execute(
        """
        INSERT INTO reaction_sync_state (
            source, channel_username, message_id, emoji, action_key, applied_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "telegram_reaction",
            channel_username,
            resolved_message_id,
            emoji,
            "tag:interesting|feedback:operator_marked_interesting",
            "2026-07-20T11:00:00Z",
        ),
    )
    connection.execute(
        "INSERT INTO signal_feedback (post_id, feedback, recorded_at) VALUES (?, ?, ?)",
        (post_id, "operator_marked_interesting", "2026-07-20T11:00:00Z"),
    )


class TestReactionFastLane(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = _make_connection()

    def tearDown(self) -> None:
        self.connection.close()

    def test_seven_reactions_are_searchable_with_zero_atoms(self):
        for post_id in range(1, 8):
            _seed_reacted_archive_post(self.connection, post_id=post_id)

        receipt = build_reaction_fast_lane_receipt(self.connection)
        validate_reaction_fast_lane_receipt(receipt)

        counts = receipt["counts"]
        self.assertEqual(counts["personal_reaction_events_detected"], 7)
        self.assertEqual(counts["unique_reacted_posts"], 7)
        self.assertEqual(counts["posts_resolved"], 7)
        self.assertEqual(counts["archive_documents_indexed"], 7)
        self.assertEqual(counts["searchable_archive_documents"], 7)
        self.assertEqual(counts["enrichment_attempts"], 7)
        self.assertEqual(counts["enrichment_successes"], 0)
        self.assertEqual(counts["enrichment_failures"], 7)
        self.assertEqual(counts["unique_atoms_linked"], 0)
        self.assertEqual(counts["topic_link_attempts"], 7)
        self.assertEqual(counts["topic_link_successes"], 0)
        self.assertEqual(counts["topic_link_failures"], 7)
        self.assertEqual(counts["ranking_effects"], 0)
        self.assertTrue(
            receipt["search_availability"]["assistant_archive_search_available"]
        )
        self.assertEqual(
            receipt["incomplete_stage_reasons"],
            {
                "knowledge_atom_not_extracted": 7,
                "ranking_not_evaluated": 7,
                "topic_not_linked": 7,
            },
        )

        results = search_telegram_archive(
            self.connection,
            "fastlane",
            filters={"reacted_only": True},
            limit=10,
        )
        self.assertEqual(len(results), 7)
        self.assertTrue(all(result.reaction_count == 1 for result in results))

    def test_receipt_schema_records_all_prm5_fields(self):
        _seed_reacted_archive_post(self.connection, post_id=1)

        receipt = build_reaction_fast_lane_receipt(self.connection)
        counts = receipt["counts"]

        for field in (
            "personal_reaction_events_detected",
            "unique_reacted_posts",
            "archive_documents_indexed",
            "indexed_documents",
            "searchable_archive_documents",
            "enrichment_attempts",
            "enrichment_successes",
            "enrichment_failures",
            "topic_link_attempts",
            "topic_link_successes",
            "topic_link_failures",
            "topic_links",
            "ranking_effects",
        ):
            self.assertIn(field, counts)
        for stage in (
            "reaction_detection",
            "source_resolution",
            "archive_index",
            "enrichment",
            "topic_linkage",
            "assistant_search",
            "ranking",
        ):
            self.assertIn(stage, receipt["stage_statuses"])
        self.assertFalse(receipt["privacy"]["raw_text_included"])
        self.assertFalse(receipt["privacy"]["emoji_values_included"])

    def test_absent_and_multiple_emoji_semantics_are_bounded(self):
        absent = classify_reaction_semantics(()).as_dict()
        self.assertEqual(absent["interest_state"], "unknown")
        self.assertFalse(absent["positive_implicit_interest"])
        self.assertFalse(absent["negative_interest"])
        self.assertEqual(absent["post_level_interest_signals"], 0)

        multiple = classify_reaction_semantics(["+", "-", "+"]).as_dict()
        self.assertEqual(multiple["interest_state"], "positive_implicit_interest")
        self.assertTrue(multiple["positive_implicit_interest"])
        self.assertFalse(multiple["negative_interest"])
        self.assertEqual(multiple["post_level_interest_signals"], 1)
        self.assertEqual(multiple["emoji_count"], 2)
        self.assertEqual(multiple["emoji_interpretation"], "audit_metadata_only")
        self.assertEqual(multiple["interest_strength"], "weak")


if __name__ == "__main__":
    unittest.main()
