import sqlite3
import tempfile
import unittest
from pathlib import Path


class TestSignalFeedbackMigration(unittest.TestCase):
    def setUp(self):
        import os
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "test.db")
        os.environ["AGENT_DB_PATH"] = self.db_path

    def tearDown(self):
        del __import__("os").environ["AGENT_DB_PATH"]
        self.tmpdir.cleanup()

    def _run_migrations(self):
        from db.migrate import run_migrations
        run_migrations()
        return sqlite3.connect(self.db_path)

    def test_signal_feedback_table_created(self):
        conn = self._run_migrations()
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='signal_feedback'"
        ).fetchone()
        self.assertIsNotNone(row, "signal_feedback table should exist after migrations")

    def test_record_feedback_inserts_row(self):
        from db.migrate import record_feedback

        conn = self._run_migrations()
        conn.row_factory = sqlite3.Row
        record_feedback(conn, post_id=42, feedback="acted_on")

        row = conn.execute(
            "SELECT post_id, feedback, recorded_at FROM signal_feedback WHERE post_id = 42"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["post_id"], 42)
        self.assertEqual(row["feedback"], "acted_on")
        self.assertTrue(row["recorded_at"])

    def test_record_feedback_rejects_invalid_value(self):
        from db.migrate import record_feedback

        conn = self._run_migrations()
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO signal_feedback (post_id, feedback, recorded_at) VALUES (?, ?, ?)",
                (1, "invalid_value", "2026-01-01T00:00:00"),
            )
            conn.commit()


if __name__ == "__main__":
    unittest.main()
