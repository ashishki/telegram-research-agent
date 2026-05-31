import io
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch


def _install_stub(module_name: str, **attributes: object) -> None:
    module = sys.modules.get(module_name)
    if module is None:
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module
    for name, value in attributes.items():
        setattr(module, name, value)


_install_stub(
    "anthropic",
    APIConnectionError=Exception,
    APIStatusError=Exception,
    APITimeoutError=Exception,
    Anthropic=object,
    RateLimitError=Exception,
)
_install_stub("telethon", TelegramClient=object)
_install_stub("telethon.errors", FloodWaitError=Exception)
_install_stub("weasyprint")
_install_stub("jinja2")
_install_stub("numpy", asarray=lambda value: value)
_install_stub("sklearn")
_install_stub("sklearn.cluster", KMeans=object)
_install_stub("sklearn.feature_extraction")
_install_stub("sklearn.feature_extraction.text", ENGLISH_STOP_WORDS=set(), TfidfVectorizer=object)
_install_stub("sklearn.metrics", silhouette_score=lambda *_args, **_kwargs: 0.0)

from db.artifact_feedback import fetch_artifact_feedback, record_artifact_feedback  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
import main  # noqa: E402


class TestArtifactFeedback(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def test_migration_creates_artifact_feedback_table_and_indexes(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                table_row = connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name = ?
                    """,
                    ("artifact_feedback_logs",),
                ).fetchone()
                index_names = {
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type = 'index'
                          AND tbl_name = ?
                        """,
                        ("artifact_feedback_logs",),
                    ).fetchall()
                }
        finally:
            os.unlink(db_path)

        self.assertIsNotNone(table_row)
        self.assertIn("idx_artifact_feedback_week_label", index_names)
        self.assertIn("idx_artifact_feedback_feedback", index_names)
        self.assertIn("idx_artifact_feedback_recorded_at", index_names)

    def test_record_and_fetch_artifact_feedback_round_trips_target(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                feedback = record_artifact_feedback(
                    connection,
                    week_label="2026-W22",
                    artifact_type="research_brief",
                    artifact_path="data/output/digests/2026-W22.md",
                    section="Source Quality",
                    item_ref="claim-7",
                    feedback="decision-impacting",
                    source_evidence_item_ids=[101, "102"],
                    notes="Changed what I read next",
                    recorded_at="2026-05-31T10:00:00Z",
                )
                stored = connection.execute(
                    """
                    SELECT source_evidence_item_ids_json
                    FROM artifact_feedback_logs
                    WHERE id = ?
                    """,
                    (feedback["id"],),
                ).fetchone()
                fetched = fetch_artifact_feedback(connection, week_label="2026-W22", limit=5)
        finally:
            os.unlink(db_path)

        self.assertEqual(feedback["feedback"], "decision_impacting")
        self.assertEqual(feedback["section"], "Source Quality")
        self.assertEqual(feedback["item_ref"], "claim-7")
        self.assertEqual(feedback["source_evidence_item_ids"], [101, 102])
        self.assertEqual(json.loads(stored[0]), [101, 102])
        self.assertEqual([row["id"] for row in fetched], [feedback["id"]])

    def test_log_and_inspect_artifact_feedback_cli(self):
        db_path = self._make_db()
        record_stdout = io.StringIO()
        inspect_stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(
                    sys,
                    "argv",
                    [
                        "main.py",
                        "log-artifact-feedback",
                        "--week",
                        "2026-W22",
                        "--artifact-type",
                        "research_brief",
                        "--artifact-path",
                        "data/output/digests/2026-W22.md",
                        "--section",
                        "Evidence",
                        "--item-ref",
                        "claim-7",
                        "--feedback",
                        "weak",
                        "--evidence-id",
                        "101",
                        "--notes",
                        "Source was too thin",
                    ],
                ):
                    with redirect_stdout(record_stdout):
                        record_exit = main.main()

                with patch.object(
                    sys,
                    "argv",
                    [
                        "main.py",
                        "memory",
                        "inspect-artifact-feedback",
                        "--week",
                        "2026-W22",
                    ],
                ):
                    with redirect_stdout(inspect_stdout):
                        inspect_exit = main.main()
        finally:
            os.unlink(db_path)

        self.assertEqual(record_exit, 0)
        self.assertIn("Recorded artifact feedback", record_stdout.getvalue())
        self.assertEqual(inspect_exit, 0)
        self.assertIn("ArtifactFeedback", inspect_stdout.getvalue())
        self.assertIn("feedback=weak", inspect_stdout.getvalue())
        self.assertIn("section=Evidence", inspect_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
