import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


def _run_migrations_for_test(db_path: str) -> sqlite3.Connection:
    os.environ["AGENT_DB_PATH"] = db_path
    from db.migrate import run_migrations

    run_migrations()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn


class TestProjectContextRefresh(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "test.db")
        self.conn = _run_migrations_for_test(self.db_path)

        self.conn.execute(
            """
            INSERT INTO projects (
                id, name, description, keywords, active, github_repo, last_commit_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "ashishki/gdev-agent",
                "repo description",
                json.dumps(["fastapi", "redis"]),
                1,
                "ashishki/gdev-agent",
                "2026-04-13T08:00:00Z",
            ),
        )
        self.conn.execute(
            """
            INSERT INTO raw_posts (
                id, channel_username, channel_id, message_id, posted_at, text, raw_json, ingested_at, message_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "@signal_chan",
                100,
                500,
                "2026-04-13T07:00:00Z",
                "Interesting signal about cost-aware routing.",
                "{}",
                "2026-04-13T07:05:00Z",
                "https://t.me/signal_chan/500",
            ),
        )
        self.conn.execute(
            """
            INSERT INTO posts (
                id, raw_post_id, channel_username, posted_at, content, normalized_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                1,
                "@signal_chan",
                "2026-04-13T07:00:00Z",
                "Interesting signal about cost-aware routing and eval gates.",
                "2026-04-13T07:06:00Z",
            ),
        )
        self.conn.execute(
            """
            INSERT INTO post_project_links (post_id, project_id, relevance_score, note)
            VALUES (?, ?, ?, ?)
            """,
            (1, 1, 0.92, "linked by test"),
        )
        self.conn.execute(
            """
            INSERT INTO decision_journal (
                decision_scope, subject_ref_type, subject_ref_id, project_name, status, reason, recorded_by, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "insight",
                "insight_triage_id",
                "1",
                "gdev-agent",
                "acted_on",
                "Implemented cost-aware routing gate",
                "pipeline",
                "2026-04-13T09:00:00Z",
            ),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        del os.environ["AGENT_DB_PATH"]
        self.tmpdir.cleanup()

    def test_refresh_all_project_context_snapshots_includes_recent_decisions_and_signals(self):
        from output.context_memory import refresh_all_project_context_snapshots

        refresh_all_project_context_snapshots(self.conn)
        self.conn.commit()

        row = self.conn.execute(
            """
            SELECT summary, open_questions, context_json, linked_signal_count, snapshot_week_label
            FROM project_context_snapshots
            WHERE project_id = 1
            """
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["linked_signal_count"], 1)
        self.assertTrue(str(row["snapshot_week_label"]).startswith("2026-W"))
        self.assertIn("acted_on=1", row["summary"])

        context = json.loads(row["context_json"])
        self.assertEqual(context["decision_counts"]["acted_on"], 1)
        self.assertEqual(len(context["recent_decisions"]), 1)
        self.assertEqual(len(context["recent_linked_signals"]), 1)
        self.assertIn("Implemented cost-aware routing gate", context["recent_decisions"][0])


if __name__ == "__main__":
    unittest.main()
