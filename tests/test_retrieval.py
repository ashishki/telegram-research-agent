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


def _insert_evidence_row(
    conn: sqlite3.Connection,
    *,
    post_id: int = 1,
    raw_post_id: int = 1,
    week_label: str = "2026-W14",
    evidence_kind: str = "strong_signal",
    excerpt_text: str = "test excerpt",
    source_channel: str = "test_channel",
    message_url: str = "https://t.me/test/1",
    posted_at: str = "2026-04-07T10:00:00Z",
    project_names_json: str = '[]',
    selection_reason: str = "bucket=strong (auto-scored)",
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO signal_evidence_items (
            post_id, raw_post_id, week_label, evidence_kind,
            excerpt_text, source_channel, message_url, posted_at,
            topic_labels_json, project_names_json, selection_reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            post_id, raw_post_id, week_label, evidence_kind,
            excerpt_text, source_channel, message_url, posted_at,
            "[]", project_names_json, selection_reason,
            "2026-04-07T10:00:00Z",
        ),
    )
    conn.commit()


def _insert_decision_row(
    conn: sqlite3.Connection,
    *,
    decision_scope: str = "signal",
    subject_ref_type: str = "post_id",
    subject_ref_id: str = "1",
    project_name: str | None = None,
    status: str = "acted_on",
    reason: str | None = None,
    recorded_by: str = "user",
    recorded_at: str = "2026-04-07T10:00:00Z",
) -> None:
    conn.execute(
        """
        INSERT INTO decision_journal (
            decision_scope, subject_ref_type, subject_ref_id,
            project_name, status, reason, recorded_by, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision_scope, subject_ref_type, subject_ref_id,
            project_name, status, reason, recorded_by, recorded_at,
        ),
    )
    conn.commit()


class TestFetchEvidenceItemsScoping(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "test.db")
        self.conn = _run_migrations_for_test(self.db_path)

    def tearDown(self):
        self.conn.close()
        del os.environ["AGENT_DB_PATH"]
        self.tmpdir.cleanup()

    def test_project_name_scope_returns_matching_rows_only(self):
        from db.retrieval import fetch_evidence_items
        _insert_evidence_row(self.conn, post_id=1, raw_post_id=1,
                             project_names_json='["alpha-project"]', week_label="2026-W14")
        _insert_evidence_row(self.conn, post_id=2, raw_post_id=2,
                             project_names_json='["beta-project"]', week_label="2026-W14")

        results = fetch_evidence_items(self.conn, project_name="alpha-project")

        self.assertEqual(len(results), 1)
        self.assertIn("alpha-project", results[0]["project_names_json"])

    def test_week_label_scope_returns_matching_week_only(self):
        from db.retrieval import fetch_evidence_items
        _insert_evidence_row(self.conn, post_id=1, raw_post_id=1, week_label="2026-W14")
        _insert_evidence_row(self.conn, post_id=2, raw_post_id=2, week_label="2026-W10")

        results = fetch_evidence_items(self.conn, week_label="2026-W14")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["week_label"], "2026-W14")

    def test_week_range_scope_returns_rows_in_range(self):
        from db.retrieval import fetch_evidence_items
        _insert_evidence_row(self.conn, post_id=1, raw_post_id=1, week_label="2026-W12")
        _insert_evidence_row(self.conn, post_id=2, raw_post_id=2, week_label="2026-W14")
        _insert_evidence_row(self.conn, post_id=3, raw_post_id=3, week_label="2026-W16")

        results = fetch_evidence_items(self.conn, week_range=["2026-W12", "2026-W14"])

        week_labels = {row["week_label"] for row in results}
        self.assertIn("2026-W12", week_labels)
        self.assertIn("2026-W14", week_labels)
        self.assertNotIn("2026-W16", week_labels)

    def test_source_channel_scope_returns_matching_channel_only(self):
        from db.retrieval import fetch_evidence_items
        _insert_evidence_row(self.conn, post_id=1, raw_post_id=1, source_channel="chan_a")
        _insert_evidence_row(self.conn, post_id=2, raw_post_id=2, source_channel="chan_b")

        results = fetch_evidence_items(self.conn, source_channel="chan_a")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source_channel"], "chan_a")

    def test_evidence_kind_scope_returns_matching_kind_only(self):
        from db.retrieval import fetch_evidence_items
        _insert_evidence_row(self.conn, post_id=1, raw_post_id=1, evidence_kind="strong_signal")
        _insert_evidence_row(self.conn, post_id=2, raw_post_id=2, evidence_kind="manual_tag")

        results = fetch_evidence_items(self.conn, evidence_kind="manual_tag")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["evidence_kind"], "manual_tag")

    def test_exclude_statuses_filters_out_acted_on_items(self):
        from db.retrieval import fetch_evidence_items
        _insert_evidence_row(self.conn, post_id=1, raw_post_id=1)
        _insert_evidence_row(self.conn, post_id=2, raw_post_id=2)
        _insert_decision_row(self.conn, subject_ref_id="1", status="acted_on",
                             decision_scope="signal")

        results = fetch_evidence_items(self.conn, exclude_statuses=["acted_on"])

        post_ids = [row["post_id"] for row in results]
        self.assertNotIn(1, post_ids)
        self.assertIn(2, post_ids)

    def test_no_filters_returns_all_rows(self):
        from db.retrieval import fetch_evidence_items
        _insert_evidence_row(self.conn, post_id=1, raw_post_id=1)
        _insert_evidence_row(self.conn, post_id=2, raw_post_id=2)
        _insert_evidence_row(self.conn, post_id=3, raw_post_id=3)

        results = fetch_evidence_items(self.conn)

        self.assertEqual(len(results), 3)

    def test_returned_rows_have_required_provenance_fields(self):
        from db.retrieval import fetch_evidence_items
        _insert_evidence_row(
            self.conn, post_id=1, raw_post_id=1,
            week_label="2026-W14", evidence_kind="strong_signal",
            excerpt_text="some excerpt", source_channel="mychan",
            message_url="https://t.me/mychan/1", posted_at="2026-04-07T10:00:00Z",
            project_names_json='["my-project"]',
            selection_reason="bucket=strong (auto-scored)",
        )

        results = fetch_evidence_items(self.conn)

        self.assertEqual(len(results), 1)
        row = results[0]
        for field in ("id", "post_id", "week_label", "evidence_kind",
                      "excerpt_text", "source_channel", "posted_at",
                      "project_names_json", "selection_reason"):
            self.assertIn(field, row, f"Required field '{field}' missing from result")

    def test_last_used_at_is_updated_after_fetch(self):
        from db.retrieval import fetch_evidence_items
        _insert_evidence_row(self.conn, post_id=1, raw_post_id=1)

        before_row = self.conn.execute(
            "SELECT last_used_at FROM signal_evidence_items WHERE post_id = 1"
        ).fetchone()
        self.assertIsNone(before_row["last_used_at"])

        fetch_evidence_items(self.conn)

        after_row = self.conn.execute(
            "SELECT last_used_at FROM signal_evidence_items WHERE post_id = 1"
        ).fetchone()
        self.assertIsNotNone(after_row["last_used_at"])

    def test_limit_is_respected(self):
        from db.retrieval import fetch_evidence_items
        for i in range(1, 6):
            _insert_evidence_row(self.conn, post_id=i, raw_post_id=i)

        results = fetch_evidence_items(self.conn, limit=3)

        self.assertLessEqual(len(results), 3)


class TestFetchDecisions(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "test.db")
        self.conn = _run_migrations_for_test(self.db_path)

    def tearDown(self):
        self.conn.close()
        del os.environ["AGENT_DB_PATH"]
        self.tmpdir.cleanup()

    def test_decision_scope_filter(self):
        from db.retrieval import fetch_decisions
        _insert_decision_row(self.conn, decision_scope="signal", subject_ref_id="1", status="acted_on")
        _insert_decision_row(self.conn, decision_scope="insight", subject_ref_id="2", status="rejected")

        results = fetch_decisions(self.conn, decision_scope="signal")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["decision_scope"], "signal")

    def test_status_filter(self):
        from db.retrieval import fetch_decisions
        _insert_decision_row(self.conn, status="acted_on", subject_ref_id="1")
        _insert_decision_row(self.conn, status="rejected", subject_ref_id="2")

        results = fetch_decisions(self.conn, status="acted_on")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "acted_on")

    def test_limit_respected(self):
        from db.retrieval import fetch_decisions
        for i in range(1, 6):
            _insert_decision_row(self.conn, subject_ref_id=str(i))

        results = fetch_decisions(self.conn, limit=2)

        self.assertLessEqual(len(results), 2)

    def test_no_filters_returns_all_rows(self):
        from db.retrieval import fetch_decisions
        _insert_decision_row(self.conn, decision_scope="signal", subject_ref_id="1", status="acted_on")
        _insert_decision_row(self.conn, decision_scope="insight", subject_ref_id="2", status="rejected")

        results = fetch_decisions(self.conn)

        self.assertGreaterEqual(len(results), 2)


class TestFetchProjectSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "test.db")
        self.conn = _run_migrations_for_test(self.db_path)

    def tearDown(self):
        self.conn.close()
        del os.environ["AGENT_DB_PATH"]
        self.tmpdir.cleanup()

    def _insert_snapshot(self, project_name: str, summary: str = "test summary") -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO project_context_snapshots
                (project_id, project_name, summary, open_questions, recent_changes, context_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (1, project_name, summary, "", "", "{}", "2026-04-07T10:00:00Z"),
        )
        self.conn.commit()

    def test_returns_dict_for_known_project(self):
        from db.retrieval import fetch_project_snapshot
        self._insert_snapshot("my-project", summary="Working on memory layer")

        result = fetch_project_snapshot(self.conn, "my-project")

        self.assertIsNotNone(result)
        self.assertEqual(result["project_name"], "my-project")
        self.assertEqual(result["summary"], "Working on memory layer")

    def test_returns_none_for_unknown_project(self):
        from db.retrieval import fetch_project_snapshot

        result = fetch_project_snapshot(self.conn, "nonexistent-project")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
