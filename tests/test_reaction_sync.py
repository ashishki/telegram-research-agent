import os
import sqlite3
import tempfile
import unittest
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

    def test_apply_reaction_feedback_records_tag_feedback_and_state(self):
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
        state = connection.execute("SELECT action_key FROM reaction_sync_state WHERE message_id = 77").fetchone()

        self.assertEqual(tag["tag"], "strong")
        self.assertEqual(feedback["feedback"], "marked_important")
        self.assertEqual(state["action_key"], "tag:strong|feedback:marked_important")

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

    def test_unknown_reaction_is_ignored(self):
        from ingestion.reaction_sync import apply_reaction_feedback

        connection, post_id = self._connection_with_post()
        summary = apply_reaction_feedback(
            connection,
            post_id=post_id,
            channel_username="@source",
            message_id=77,
            emojis={"🐢"},
        )

        self.assertEqual(summary["skipped_unknown"], 1)
        self.assertIsNone(connection.execute("SELECT 1 FROM user_post_tags WHERE post_id = ?", (post_id,)).fetchone())
        self.assertIsNone(connection.execute("SELECT 1 FROM signal_feedback WHERE post_id = ?", (post_id,)).fetchone())


if __name__ == "__main__":
    unittest.main()
