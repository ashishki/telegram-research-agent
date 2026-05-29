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

from db.migrate import run_migrations  # noqa: E402
from db.usefulness import fetch_weekly_usefulness_logs, record_weekly_usefulness_log  # noqa: E402
import main  # noqa: E402


class TestOperatorUsefulness(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def test_migration_creates_weekly_usefulness_log_table_and_indexes(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                table_row = connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name = ?
                    """,
                    ("weekly_usefulness_logs",),
                ).fetchone()
                index_rows = connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'index'
                      AND tbl_name = ?
                    ORDER BY name ASC
                    """,
                    ("weekly_usefulness_logs",),
                ).fetchall()
        finally:
            os.unlink(db_path)

        self.assertIsNotNone(table_row)
        index_names = {row[0] for row in index_rows}
        self.assertIn("idx_weekly_usefulness_logs_week_label", index_names)
        self.assertIn("idx_weekly_usefulness_logs_recorded_at", index_names)

    def test_record_and_fetch_weekly_usefulness_log_preserves_lists(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                log = record_weekly_usefulness_log(
                    connection,
                    week_label="2026-W22",
                    useful_sections=["Project Relevance", "Implementation Ideas"],
                    not_useful_sections=["Study Plan"],
                    decisions_influenced=["Prioritized callback validation"],
                    weak_evidence_notes=["Recommendation lacked source links"],
                    channels_gaining_trust=["@source_a"],
                    channels_losing_trust=["@source_b"],
                    notes="Brief was useful but evidence citations need work",
                    recorded_at="2026-05-29T10:00:00Z",
                )
                stored = connection.execute(
                    """
                    SELECT useful_sections_json, channels_gaining_trust_json
                    FROM weekly_usefulness_logs
                    WHERE id = ?
                    """,
                    (log["id"],),
                ).fetchone()
                fetched = fetch_weekly_usefulness_logs(connection, week_label="2026-W22", limit=5)
        finally:
            os.unlink(db_path)

        self.assertEqual(log["useful_sections"], ["Project Relevance", "Implementation Ideas"])
        self.assertEqual(log["not_useful_sections"], ["Study Plan"])
        self.assertEqual(log["decisions_influenced"], ["Prioritized callback validation"])
        self.assertEqual(log["weak_evidence_notes"], ["Recommendation lacked source links"])
        self.assertEqual(log["channels_gaining_trust"], ["@source_a"])
        self.assertEqual(log["channels_losing_trust"], ["@source_b"])
        self.assertEqual(log["notes"], "Brief was useful but evidence citations need work")
        self.assertEqual(json.loads(stored[0]), ["Project Relevance", "Implementation Ideas"])
        self.assertEqual(json.loads(stored[1]), ["@source_a"])
        self.assertEqual(len(fetched), 1)
        self.assertEqual(fetched[0]["id"], log["id"])

    def test_log_usefulness_cli_records_summary(self):
        db_path = self._make_db()
        stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(
                    sys,
                    "argv",
                    [
                        "main.py",
                        "log-usefulness",
                        "--week",
                        "2026-W22",
                        "--useful-section",
                        "Project Relevance",
                        "--useful-section",
                        "Implementation Ideas",
                        "--not-useful-section",
                        "Study Plan",
                        "--decision",
                        "Prioritized callback validation",
                        "--weak-evidence",
                        "Recommendation lacked source links",
                        "--trust-up",
                        "@source_a",
                        "--trust-down",
                        "@source_b",
                        "--notes",
                        "Brief was useful but evidence citations need work",
                    ],
                ):
                    with redirect_stdout(stdout):
                        exit_code = main.main()

            with sqlite3.connect(db_path) as connection:
                row = connection.execute(
                    """
                    SELECT useful_sections_json, not_useful_sections_json,
                           decisions_influenced_json, weak_evidence_notes_json,
                           channels_gaining_trust_json, channels_losing_trust_json, notes
                    FROM weekly_usefulness_logs
                    WHERE week_label = ?
                    """,
                    ("2026-W22",),
                ).fetchone()
        finally:
            os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Recorded weekly usefulness log", output)
        self.assertIn("week=2026-W22", output)
        self.assertIn("useful_sections=2", output)
        self.assertEqual(json.loads(row[0]), ["Project Relevance", "Implementation Ideas"])
        self.assertEqual(json.loads(row[1]), ["Study Plan"])
        self.assertEqual(json.loads(row[2]), ["Prioritized callback validation"])
        self.assertEqual(json.loads(row[3]), ["Recommendation lacked source links"])
        self.assertEqual(json.loads(row[4]), ["@source_a"])
        self.assertEqual(json.loads(row[5]), ["@source_b"])
        self.assertEqual(row[6], "Brief was useful but evidence citations need work")


if __name__ == "__main__":
    unittest.main()
