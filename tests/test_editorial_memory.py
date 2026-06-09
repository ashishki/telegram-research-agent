import io
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
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
from output.editorial_memory import build_weekly_editorial_memory  # noqa: E402
from output.operator_report import build_monthly_operator_report  # noqa: E402
import main  # noqa: E402


class TestEditorialMemory(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def _seed_editorial_rows(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT INTO artifact_feedback_logs (
                week_label, artifact_type, feedback, section, item_ref,
                source_evidence_item_ids_json, notes, recorded_at, recorded_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-W24",
                "research_brief",
                "useful",
                "Decision Brief",
                "top",
                "[]",
                "Keep concise decision block",
                "2026-06-01T10:00:00Z",
                "operator",
            ),
        )
        connection.execute(
            """
            INSERT INTO artifact_feedback_logs (
                week_label, artifact_type, feedback, section,
                source_evidence_item_ids_json, notes, recorded_at, recorded_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-W24",
                "study_plan",
                "weak",
                "Resources",
                "[]",
                "Too generic",
                "2026-06-01T11:00:00Z",
                "operator",
            ),
        )
        connection.execute(
            """
            INSERT INTO weekly_usefulness_logs (
                week_label,
                useful_sections_json,
                not_useful_sections_json,
                decisions_influenced_json,
                weak_evidence_notes_json,
                channels_gaining_trust_json,
                channels_losing_trust_json,
                notes,
                recorded_at,
                recorded_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-W24",
                json.dumps(["Evidence & Source Mix"]),
                json.dumps(["Study Plan"]),
                json.dumps(["Deferred weak MVP"]),
                json.dumps(["Need external proof"]),
                json.dumps(["source_a"]),
                json.dumps(["source_b"]),
                "Study contradicted digest",
                "2026-06-02T10:00:00Z",
                "operator",
            ),
        )
        connection.execute(
            """
            INSERT INTO research_brief_receipts (
                receipt_id,
                week_label,
                generated_at,
                post_counts_json,
                source_set_json,
                fallback_delivery_used,
                verification_status,
                health_flags_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "receipt-2026-W24",
                "2026-W24",
                "2026-06-02T12:00:00Z",
                "{}",
                "{}",
                1,
                "needs_review",
                json.dumps(["low_signal_alert"]),
                "2026-06-02T12:00:00Z",
                "2026-06-02T12:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO source_observations (
                channel_username, week_label, low_signal_count, rejected_count,
                skipped_count, counters_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "source_b",
                "2026-W24",
                3,
                1,
                1,
                "{}",
                "2026-06-02T12:00:00Z",
                "2026-06-02T12:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO quality_metrics (
                week_label, computed_at, total_posts, strong_count, watch_count,
                cultural_count, noise_count, project_match_count, output_word_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-W24", "2026-06-02T12:00:00Z", 10, 0, 2, 0, 8, 1, 80),
        )
        connection.commit()

    def _make_output_root(self, tmpdir: str) -> Path:
        output_root = Path(tmpdir)
        (output_root / "digests").mkdir()
        (output_root / "study_plans").mkdir()
        (output_root / "project_insights").mkdir()
        (output_root / "digests" / "2026-W24.md").write_text(
            "## Decision Brief\n- Evaluated: 10 posts.\n\n"
            "## Project Insights\n**project**\n- Source-backed insight\n\n"
            "## What Changed\n- watch: 2\n",
            encoding="utf-8",
        )
        (output_root / "study_plans" / "2026-W24.md").write_text(
            "No Telegram signals this week.",
            encoding="utf-8",
        )
        (output_root / "project_insights" / "2026-W24.md").write_text(
            "## Project Insights - 2026-W24\n\nNo project insights were identified this week.\n",
            encoding="utf-8",
        )
        return output_root

    def test_weekly_editorial_memory_renders_local_signals_and_sidecar(self):
        db_path = self._make_db()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_root = self._make_output_root(tmpdir)
                with sqlite3.connect(db_path) as connection:
                    connection.row_factory = sqlite3.Row
                    self._seed_editorial_rows(connection)
                    memory = build_weekly_editorial_memory(
                        connection,
                        week_label="2026-W24",
                        output_root=output_root,
                    )
                self.assertIsNotNone(memory.sidecar_path)
                self.assertTrue(memory.sidecar_path.exists())
                rendered = memory.markdown
        finally:
            os.unlink(db_path)

        self.assertIn("# Weekly Editorial Memory 2026-W24", rendered)
        self.assertIn("No model-generated judgments", rendered)
        self.assertIn("research_brief / Decision Brief / top: useful", rendered)
        self.assertIn("study_plan / Resources: weak", rendered)
        self.assertIn("Study Plan says no Telegram signals", rendered)
        self.assertIn("Receipt verification status: needs_review", rendered)
        self.assertIn("source_b", rendered)
        self.assertIn("## Test Next Week", rendered)

    def test_editorial_memory_cli_writes_sidecar(self):
        db_path = self._make_db()
        stdout = io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_root = self._make_output_root(tmpdir)
                with sqlite3.connect(db_path) as connection:
                    connection.row_factory = sqlite3.Row
                    self._seed_editorial_rows(connection)
                with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                    with patch.object(
                        sys,
                        "argv",
                        [
                            "main.py",
                            "memory",
                            "inspect-editorial-memory",
                            "--week",
                            "2026-W24",
                            "--output-root",
                            str(output_root),
                        ],
                    ):
                        with redirect_stdout(stdout):
                            exit_code = main.main()
                sidecar_exists = (output_root / "editorial_memory" / "2026-W24.md").exists()
        finally:
            os.unlink(db_path)

        rendered = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("sidecar=", rendered)
        self.assertIn("Weekly Editorial Memory 2026-W24", rendered)
        self.assertTrue(sidecar_exists)

    def test_operator_report_includes_editorial_memory_section(self):
        db_path = self._make_db()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_root = self._make_output_root(tmpdir)
                with sqlite3.connect(db_path) as connection:
                    connection.row_factory = sqlite3.Row
                    self._seed_editorial_rows(connection)
                    report = build_monthly_operator_report(
                        connection,
                        month="2026-06",
                        report_output_root=output_root,
                    )
        finally:
            os.unlink(db_path)

        self.assertIn("## Editorial Memory", report)
        self.assertIn("Editorial memory: 1 week(s) with local signals", report)
        self.assertIn("2026-W24: keep=", report)

    def test_editorial_memory_handles_default_sqlite_rows_and_verified_receipts(self):
        db_path = self._make_db()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_root = self._make_output_root(tmpdir)
                with sqlite3.connect(db_path) as connection:
                    self._seed_editorial_rows(connection)
                    connection.execute(
                        """
                        UPDATE research_brief_receipts
                        SET verification_status = ?, fallback_delivery_used = ?, health_flags_json = ?
                        WHERE week_label = ?
                        """,
                        ("verified", 0, "[]", "2026-W24"),
                    )
                    connection.commit()
                    memory = build_weekly_editorial_memory(
                        connection,
                        week_label="2026-W24",
                        output_root=output_root,
                        write_sidecar=False,
                    )
        finally:
            os.unlink(db_path)

        self.assertIn("Weekly Editorial Memory 2026-W24", memory.markdown)
        self.assertNotIn("Receipt verification status: verified", memory.markdown)


if __name__ == "__main__":
    unittest.main()
