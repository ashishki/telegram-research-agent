import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


class TestReactionSync(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "test.db")
        os.environ["AGENT_DB_PATH"] = self.db_path

    def tearDown(self):
        del os.environ["AGENT_DB_PATH"]
        self.tmpdir.cleanup()

    def _connection_with_post(self) -> tuple[sqlite3.Connection, int]:
        from db.migrate import run_migrations

        run_migrations()
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute(
            """
            INSERT INTO raw_posts (
                channel_username, channel_id, message_id, posted_at,
                text, raw_json, ingested_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("@source", 100, 77, "2026-04-28T00:00:00Z", "Interesting post", "{}", "2026-04-28T00:01:00Z"),
        )
        raw_post_id = int(connection.execute("SELECT id FROM raw_posts").fetchone()["id"])
        connection.execute(
            """
            INSERT INTO posts (raw_post_id, channel_username, posted_at, content, normalized_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (raw_post_id, "@source", "2026-04-28T00:00:00Z", "Interesting post", "2026-04-28T00:02:00Z"),
        )
        post_id = int(connection.execute("SELECT id FROM posts").fetchone()["id"])
        connection.commit()
        return connection, post_id

    def test_reaction_sync_state_table_created(self):
        connection, _post_id = self._connection_with_post()
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='reaction_sync_state'"
        ).fetchone()
        self.assertIsNotNone(row)

    def test_apply_reaction_feedback_records_operator_interest_and_raw_emoji(self):
        from ingestion.reaction_sync import apply_reaction_feedback

        connection, post_id = self._connection_with_post()
        summary = apply_reaction_feedback(
            connection,
            post_id=post_id,
            channel_username="@source",
            message_id=77,
            emojis={"🔥"},
        )

        self.assertEqual(summary["matched_reactions"], 1)
        self.assertEqual(summary["applied_tags"], 1)
        self.assertEqual(summary["applied_feedback"], 1)

        tag = connection.execute("SELECT tag FROM user_post_tags WHERE post_id = ?", (post_id,)).fetchone()
        feedback = connection.execute("SELECT feedback FROM signal_feedback WHERE post_id = ?", (post_id,)).fetchone()
        state = connection.execute(
            "SELECT emoji, action_key FROM reaction_sync_state WHERE message_id = 77"
        ).fetchone()

        self.assertEqual(tag["tag"], "interesting")
        self.assertEqual(feedback["feedback"], "operator_marked_interesting")
        self.assertEqual(state["emoji"], "🔥")
        self.assertEqual(state["action_key"], "tag:interesting|feedback:operator_marked_interesting")

    def test_apply_reaction_feedback_is_idempotent(self):
        from ingestion.reaction_sync import apply_reaction_feedback

        connection, post_id = self._connection_with_post()
        apply_reaction_feedback(
            connection,
            post_id=post_id,
            channel_username="@source",
            message_id=77,
            emojis={"✅"},
        )
        second = apply_reaction_feedback(
            connection,
            post_id=post_id,
            channel_username="@source",
            message_id=77,
            emojis={"✅"},
        )

        self.assertEqual(second["skipped_existing"], 1)
        tag_count = connection.execute("SELECT COUNT(*) FROM user_post_tags WHERE post_id = ?", (post_id,)).fetchone()[0]
        feedback_count = connection.execute("SELECT COUNT(*) FROM signal_feedback WHERE post_id = ?", (post_id,)).fetchone()[0]
        self.assertEqual(tag_count, 1)
        self.assertEqual(feedback_count, 1)

    def test_old_reaction_state_prevents_reapplying_same_raw_emoji(self):
        from ingestion.reaction_sync import apply_reaction_feedback

        connection, post_id = self._connection_with_post()
        connection.execute(
            """
            INSERT INTO reaction_sync_state (
                source, channel_username, message_id, emoji, action_key, applied_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "telegram_reaction",
                "@source",
                77,
                "🔥",
                "tag:strong|feedback:marked_important",
                "2026-07-07T12:00:00Z",
            ),
        )
        connection.commit()

        summary = apply_reaction_feedback(
            connection,
            post_id=post_id,
            channel_username="@source",
            message_id=77,
            emojis={"🔥"},
        )

        self.assertEqual(summary["skipped_existing"], 1)
        feedback_count = connection.execute(
            "SELECT COUNT(*) FROM signal_feedback WHERE post_id = ?",
            (post_id,),
        ).fetchone()[0]
        self.assertEqual(feedback_count, 0)

    def test_any_visible_personal_reaction_counts_as_operator_interest(self):
        from ingestion.reaction_sync import apply_reaction_feedback

        connection, post_id = self._connection_with_post()
        summary = apply_reaction_feedback(
            connection,
            post_id=post_id,
            channel_username="@source",
            message_id=77,
            emojis={"🐢"},
        )

        self.assertEqual(summary["matched_reactions"], 1)
        self.assertEqual(summary["skipped_unknown"], 0)
        tag = connection.execute("SELECT tag FROM user_post_tags WHERE post_id = ?", (post_id,)).fetchone()
        feedback = connection.execute("SELECT feedback FROM signal_feedback WHERE post_id = ?", (post_id,)).fetchone()
        state = connection.execute("SELECT emoji FROM reaction_sync_state WHERE message_id = 77").fetchone()
        self.assertEqual(tag["tag"], "interesting")
        self.assertEqual(feedback["feedback"], "operator_marked_interesting")
        self.assertEqual(state["emoji"], "🐢")

    def test_aggregate_only_reaction_counts_are_not_personal_feedback(self):
        from ingestion.reaction_sync import _extract_self_reactions_from_message

        message = _Object(
            reactions=_Object(
                results=[
                    _Object(reaction=_Object(emoticon="🔥"), count=42),
                ],
                recent_reactions=[],
            )
        )

        self.assertEqual(_extract_self_reactions_from_message(message, self_user_id=123), set())

    def test_recent_self_reaction_is_personal_feedback(self):
        from ingestion.reaction_sync import _extract_self_reactions_from_message

        message = _Object(
            reactions=_Object(
                recent_reactions=[
                    _Object(
                        peer_id=_Object(user_id=123),
                        reaction=_Object(emoticon="🔥"),
                    ),
                ],
            )
        )

        self.assertEqual(_extract_self_reactions_from_message(message, self_user_id=123), {"🔥"})

    def test_candidate_selection_uses_exact_reporting_period_when_supplied(self):
        from ingestion.reaction_sync import _load_candidate_posts
        from output.reporting_period import resolve_reporting_period

        connection, _post_id = self._connection_with_post()
        connection.execute(
            "UPDATE posts SET posted_at = ?",
            ("2026-07-12T23:59:59.999999Z",),
        )
        connection.execute(
            """
            INSERT INTO raw_posts (
                channel_username, channel_id, message_id, posted_at,
                text, raw_json, ingested_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("@future", 101, 78, "2026-07-13T00:00:00Z", "Future", "{}", "2026-07-13T00:01:00Z"),
        )
        future_raw_id = int(connection.execute("SELECT max(id) FROM raw_posts").fetchone()[0])
        connection.execute(
            """
            INSERT INTO posts (raw_post_id, channel_username, posted_at, content, normalized_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (future_raw_id, "@future", "2026-07-13T00:00:00Z", "Future", "2026-07-13T00:02:00Z"),
        )
        connection.commit()
        period = resolve_reporting_period(
            datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
        )

        rows = _load_candidate_posts(
            connection,
            days=14,
            limit=20,
            reporting_period=period,
        )

        self.assertEqual([row["message_id"] for row in rows], [77])


class _Object:
    def __init__(self, **values):
        for key, value in values.items():
            setattr(self, key, value)


if __name__ == "__main__":
    unittest.main()
