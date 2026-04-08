import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock


def _run_migrations_for_test(db_path: str) -> sqlite3.Connection:
    os.environ["AGENT_DB_PATH"] = db_path
    from db.migrate import run_migrations
    run_migrations()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn


class TestRecordDecisionForFeedback(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "test.db")
        self.conn = _run_migrations_for_test(self.db_path)

    def tearDown(self):
        self.conn.close()
        del os.environ["AGENT_DB_PATH"]
        self.tmpdir.cleanup()

    def _count_decisions(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM decision_journal").fetchone()[0]

    def _get_decision(self, subject_ref_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM decision_journal WHERE subject_ref_id = ?",
            (subject_ref_id,),
        ).fetchone()

    def test_acted_on_writes_acted_on_status(self):
        from db.evidence import record_decision_for_feedback
        record_decision_for_feedback(self.conn, post_id=10, feedback="acted_on")

        row = self._get_decision("10")
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "acted_on")
        self.assertEqual(row["decision_scope"], "signal")
        self.assertEqual(row["subject_ref_type"], "post_id")

    def test_skipped_writes_ignored_status(self):
        from db.evidence import record_decision_for_feedback
        record_decision_for_feedback(self.conn, post_id=11, feedback="skipped")

        row = self._get_decision("11")
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "ignored")

    def test_marked_important_writes_acted_on_status(self):
        from db.evidence import record_decision_for_feedback
        record_decision_for_feedback(self.conn, post_id=12, feedback="marked_important")

        row = self._get_decision("12")
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "acted_on")

    def test_unknown_feedback_writes_no_row(self):
        from db.evidence import record_decision_for_feedback
        record_decision_for_feedback(self.conn, post_id=13, feedback="totally_unknown")

        self.assertEqual(self._count_decisions(), 0)

    def test_reason_contains_feedback_value(self):
        from db.evidence import record_decision_for_feedback
        record_decision_for_feedback(self.conn, post_id=14, feedback="acted_on")

        row = self._get_decision("14")
        self.assertIsNotNone(row)
        self.assertIn("acted_on", str(row["reason"] or ""))


class TestRecordDecisionsForTriage(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "test.db")
        self.conn = _run_migrations_for_test(self.db_path)

    def tearDown(self):
        self.conn.close()
        del os.environ["AGENT_DB_PATH"]
        self.tmpdir.cleanup()

    def _make_insight(self, recommendation: str, title: str = "Test Idea") -> object:
        insight = MagicMock()
        insight.recommendation = recommendation
        insight.title = title
        insight.reason = f"reason for {recommendation}"
        return insight

    def _get_decisions_by_scope(self, scope: str) -> list:
        rows = self.conn.execute(
            "SELECT * FROM decision_journal WHERE decision_scope = ?",
            (scope,),
        ).fetchall()
        return [dict(row) for row in rows]

    def test_do_now_writes_acted_on_status(self):
        from db.evidence import record_decisions_for_triage
        insights = [self._make_insight("do_now", title="Fast impl")]
        record_decisions_for_triage(self.conn, "2026-W14", insights)

        rows = self._get_decisions_by_scope("insight")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "acted_on")

    def test_backlog_writes_deferred_status(self):
        from db.evidence import record_decisions_for_triage
        insights = [self._make_insight("backlog", title="Future idea")]
        record_decisions_for_triage(self.conn, "2026-W14", insights)

        rows = self._get_decisions_by_scope("insight")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "deferred")

    def test_reject_or_defer_writes_rejected_status(self):
        from db.evidence import record_decisions_for_triage
        insights = [self._make_insight("reject_or_defer", title="Weak idea")]
        record_decisions_for_triage(self.conn, "2026-W14", insights)

        rows = self._get_decisions_by_scope("insight")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "rejected")

    def test_unknown_recommendation_writes_no_row(self):
        from db.evidence import record_decisions_for_triage
        insights = [self._make_insight("unknown_status", title="Unknown")]
        record_decisions_for_triage(self.conn, "2026-W14", insights)

        rows = self._get_decisions_by_scope("insight")
        self.assertEqual(len(rows), 0)

    def test_multiple_insights_write_multiple_rows(self):
        from db.evidence import record_decisions_for_triage
        insights = [
            self._make_insight("do_now", title="Idea 1"),
            self._make_insight("backlog", title="Idea 2"),
            self._make_insight("reject_or_defer", title="Idea 3"),
        ]
        record_decisions_for_triage(self.conn, "2026-W14", insights)

        rows = self._get_decisions_by_scope("insight")
        self.assertEqual(len(rows), 3)
        statuses = {row["status"] for row in rows}
        self.assertEqual(statuses, {"acted_on", "deferred", "rejected"})

    def test_decision_scope_is_insight(self):
        from db.evidence import record_decisions_for_triage
        insights = [self._make_insight("do_now", title="Scoped idea")]
        record_decisions_for_triage(self.conn, "2026-W14", insights)

        row = self.conn.execute(
            "SELECT decision_scope FROM decision_journal LIMIT 1"
        ).fetchone()
        self.assertEqual(row["decision_scope"], "insight")


class TestRecordStudyCompletionDecision(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "test.db")
        self.conn = _run_migrations_for_test(self.db_path)

    def tearDown(self):
        self.conn.close()
        del os.environ["AGENT_DB_PATH"]
        self.tmpdir.cleanup()

    def test_writes_study_scope_completed_status(self):
        from db.evidence import record_study_completion_decision
        record_study_completion_decision(self.conn, "2026-W14")

        row = self.conn.execute(
            "SELECT * FROM decision_journal WHERE decision_scope = 'study' LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["subject_ref_id"], "2026-W14")
        self.assertEqual(row["subject_ref_type"], "study_plan_week")

    def test_reason_contains_week_label(self):
        from db.evidence import record_study_completion_decision
        record_study_completion_decision(self.conn, "2026-W14")

        row = self.conn.execute(
            "SELECT reason FROM decision_journal WHERE decision_scope = 'study' LIMIT 1"
        ).fetchone()
        self.assertIn("2026-W14", str(row["reason"] or ""))


class TestRecordSignalEvidenceForManualTag(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "test.db")
        self.conn = _run_migrations_for_test(self.db_path)
        # Insert minimal raw_posts and posts rows needed by evidence function
        self.conn.execute(
            "INSERT INTO raw_posts (id, channel_username, channel_id, message_id, posted_at, raw_json, ingested_at, message_url)"
            " VALUES (1, 'testchan', 1, 100, '2026-04-07T10:00:00Z', '{}', '2026-04-07T10:00:00Z', 'https://t.me/testchan/100')"
        )
        self.conn.execute(
            "INSERT INTO posts (id, raw_post_id, channel_username, content, posted_at, normalized_at, bucket)"
            " VALUES (1, 1, 'testchan', 'test content', '2026-04-07T10:00:00Z', '2026-04-07T10:00:00Z', 'strong')"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        del os.environ["AGENT_DB_PATH"]
        self.tmpdir.cleanup()

    def test_qualifying_tag_inserts_evidence_row(self):
        from db.evidence import record_signal_evidence_for_manual_tag
        record_signal_evidence_for_manual_tag(self.conn, post_id=1, tag="strong")

        row = self.conn.execute(
            "SELECT * FROM signal_evidence_items WHERE post_id = 1"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["evidence_kind"], "manual_tag")
        self.assertIn("strong", str(row["selection_reason"] or ""))

    def test_non_qualifying_tag_inserts_no_evidence_row(self):
        from db.evidence import record_signal_evidence_for_manual_tag
        record_signal_evidence_for_manual_tag(self.conn, post_id=1, tag="low_signal")

        count = self.conn.execute(
            "SELECT COUNT(*) FROM signal_evidence_items"
        ).fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
