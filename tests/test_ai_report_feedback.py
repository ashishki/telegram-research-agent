import io
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
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

from config.settings import Settings  # noqa: E402
from db.ai_report_feedback import (  # noqa: E402
    fetch_ai_report_feedback,
    fetch_missed_post_eval_examples,
    record_ai_report_feedback,
    summarize_ai_report_feedback,
)
from db.knowledge_atoms import record_knowledge_atom  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
from output.ai_intelligence_report import generate_ai_intelligence_report  # noqa: E402
from output.idea_threads import refresh_idea_threads  # noqa: E402
import main  # noqa: E402


class TestAiReportFeedback(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name
        with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
            run_migrations()
        return db_path

    def _settings(self, db_path: str) -> Settings:
        return Settings(
            db_path=db_path,
            llm_api_key="",
            model_provider="",
            telegram_session_path="",
        )

    def _seed_atom(self, db_path: str) -> None:
        with sqlite3.connect(db_path) as connection:
            record_knowledge_atom(
                connection,
                week_label="2026-W28",
                atom_type="engineering_practice",
                claim="Eval gates are becoming the release path for coding agents.",
                summary="A source describes eval gates before agent-written releases.",
                evidence_quote="eval gates before release",
                source_post_ids=[101],
                source_urls=["https://t.me/ai_lab/101"],
                entities=["AI agents", "eval gates"],
                tools=["Codex"],
                practices=["eval-gated release"],
                confidence=0.84,
                novelty_score=0.6,
                practical_utility_score=0.92,
                first_seen_at="2026-07-06T08:00:00Z",
                last_seen_at="2026-07-06T08:00:00Z",
            )

    def test_migration_creates_ai_report_feedback_table_and_indexes(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                table = connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name = 'ai_report_feedback_events'
                    """
                ).fetchone()
                columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(ai_report_feedback_events)").fetchall()
                }
                indexes = {
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type = 'index' AND tbl_name = 'ai_report_feedback_events'
                        """
                    ).fetchall()
                }
        finally:
            os.unlink(db_path)

        self.assertIsNotNone(table)
        for column in ["week_label", "feedback_type", "target_type", "target_ref", "source_url", "notes"]:
            self.assertIn(column, columns)
        self.assertIn("idx_ai_report_feedback_week", indexes)
        self.assertIn("idx_ai_report_feedback_type", indexes)
        self.assertIn("idx_ai_report_feedback_target", indexes)

    def test_record_fetch_summary_and_missed_eval_examples(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                for feedback_type in [
                    "read",
                    "useful",
                    "tried",
                    "too-shallow",
                    "missed-important-post",
                    "wrong-priority",
                ]:
                    target_type = {
                        "too-shallow": "idea-thread",
                        "wrong-priority": "knowledge-atom",
                    }.get(feedback_type, "report-section")
                    record_ai_report_feedback(
                        connection,
                        week_label="2026-W27",
                        report_path="data/output/ai_intelligence/2026-W27.html",
                        feedback_type=feedback_type,
                        target_type=target_type,
                        target_ref="42" if feedback_type == "wrong-priority" else "eval-gates",
                        source_url="https://t.me/ai_lab/999" if feedback_type == "missed-important-post" else None,
                        notes=f"note for {feedback_type}",
                    )
                fetched = fetch_ai_report_feedback(connection, week_label="2026-W27", limit=10)
                summary = summarize_ai_report_feedback(connection, before_week_label="2026-W28")
                examples = fetch_missed_post_eval_examples(connection, week_label="2026-W27")
        finally:
            os.unlink(db_path)

        self.assertEqual(len(fetched), 6)
        self.assertEqual(summary["event_count"], 6)
        self.assertEqual(summary["counts_by_feedback"]["read"], 1)
        self.assertEqual(summary["counts_by_feedback"]["too_shallow"], 1)
        self.assertEqual(summary["downranked_atom_refs"], ["42"])
        self.assertEqual(len(summary["missed_post_eval_examples"]), 1)
        self.assertEqual(examples[0]["source_url"], "https://t.me/ai_lab/999")

    def test_feedback_context_appears_in_next_ai_report(self):
        db_path = self._make_db()
        try:
            self._seed_atom(db_path)
            with tempfile.TemporaryDirectory() as output_dir:
                settings = self._settings(db_path)
                with sqlite3.connect(db_path) as connection:
                    connection.row_factory = sqlite3.Row
                    record_ai_report_feedback(
                        connection,
                        week_label="2026-W27",
                        feedback_type="too_shallow",
                        target_type="idea_thread",
                        target_ref="eval-gates",
                        notes="Needed deeper source checks.",
                    )
                    record_ai_report_feedback(
                        connection,
                        week_label="2026-W27",
                        feedback_type="missed_important_post",
                        target_type="report_section",
                        target_ref="read-queue",
                        source_url="https://t.me/ai_lab/999",
                        notes="Missed a practical eval guide.",
                    )
                refresh_idea_threads(
                    settings,
                    weeks=12,
                    now=datetime(2026, 7, 8, tzinfo=timezone.utc),
                )
                summary = generate_ai_intelligence_report(
                    settings,
                    week_label="2026-W28",
                    output_root=output_dir,
                    now=datetime(2026, 7, 8, tzinfo=timezone.utc),
                )
                html_text = Path(summary.html_path).read_text(encoding="utf-8")
        finally:
            os.unlink(db_path)

        self.assertIn("Personalization Context", html_text)
        self.assertIn("too shallow=1", html_text)
        self.assertIn("Missed-post eval examples available", html_text)
        self.assertIn("Convert missed-post feedback into an eval example", html_text)

    def test_log_and_inspect_ai_report_feedback_cli(self):
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
                        "log-ai-report-feedback",
                        "--week",
                        "2026-W28",
                        "--feedback",
                        "missed-important-post",
                        "--target-type",
                        "report-section",
                        "--target-ref",
                        "read-queue",
                        "--source-url",
                        "https://t.me/ai_lab/999",
                        "--notes",
                        "Missed a practical eval guide.",
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
                        "inspect-ai-report-feedback",
                        "--week",
                        "2026-W28",
                        "--eval-examples",
                    ],
                ):
                    with redirect_stdout(inspect_stdout):
                        inspect_exit = main.main()
        finally:
            os.unlink(db_path)

        self.assertEqual(record_exit, 0)
        self.assertEqual(inspect_exit, 0)
        self.assertIn("Recorded AI report feedback", record_stdout.getvalue())
        inspect_output = inspect_stdout.getvalue()
        self.assertIn("AI Report Feedback inspection", inspect_output)
        self.assertIn("missed_important_post", inspect_output)
        self.assertIn("missed_post_eval_examples (1):", inspect_output)
        self.assertIn("https://t.me/ai_lab/999", inspect_output)


if __name__ == "__main__":
    unittest.main()
