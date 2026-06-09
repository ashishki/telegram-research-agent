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
from output.operator_report import build_monthly_operator_report  # noqa: E402
import main  # noqa: E402


class TestOperatorReport(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def _seed_report_rows(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT INTO reaction_sync_state (
                source, channel_username, message_id, emoji, action_key, applied_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("telegram_reaction", "source_a", 101, "🔥", "tag:strong|feedback:marked_important", "2026-05-10T10:00:00Z"),
        )
        connection.execute(
            """
            INSERT INTO decision_journal (
                decision_scope, subject_ref_type, subject_ref_id, status, reason, recorded_by, recorded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("insight", "insight_triage_id", "7", "acted_on", "button", "telegram_button", "2026-05-11T10:00:00Z"),
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
                "2026-W19",
                json.dumps(["Signals"]),
                json.dumps(["Study"]),
                json.dumps(["Built feature"]),
                json.dumps(["Weak source"]),
                json.dumps(["source_a"]),
                json.dumps(["source_b"]),
                "useful",
                "2026-05-12T10:00:00Z",
                "operator",
            ),
        )
        connection.execute(
            """
            INSERT INTO llm_usage (
                model, input_tokens, output_tokens, est_cost_usd, cost_usd, called_at, category, duration_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("claude-test", 100, 50, 0.02, 0.03, "2026-05-13T10:00:00Z", "digest", 1000),
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
                "rbr_report",
                "2026-W19",
                "2026-05-14T10:00:00Z",
                "{}",
                "{}",
                1,
                "needs_review",
                json.dumps(["low_signal_alert"]),
                "2026-05-14T10:00:00Z",
                "2026-05-14T10:00:00Z",
            ),
        )
        connection.execute(
            """
            INSERT INTO artifact_feedback_logs (
                week_label, artifact_type, feedback, source_evidence_item_ids_json, recorded_at, recorded_by
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("2026-W19", "research_brief", "weak", "[]", "2026-05-15T10:00:00Z", "operator"),
        )
        connection.commit()

    def test_monthly_operator_report_summarizes_local_quality_signals(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                self._seed_report_rows(connection)
                report = build_monthly_operator_report(connection, month="2026-05")
        finally:
            os.unlink(db_path)

        self.assertIn("# Operator Report 2026-05", report)
        self.assertIn("Reaction sync: 1 applied actions", report)
        self.assertIn("Inline decisions: 1", report)
        self.assertIn("Weekly usefulness logs: 1", report)
        self.assertIn("LLM usage: calls=1 input_tokens=100 output_tokens=50", report)
        self.assertIn("empty_or_low_signal=1 fallback_delivery=1", report)
        self.assertIn("Artifact feedback: 1", report)

    def test_operator_report_cli_renders_month(self):
        db_path = self._make_db()
        stdout = io.StringIO()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                self._seed_report_rows(connection)
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(
                    sys,
                    "argv",
                    ["main.py", "operator-report", "--month", "2026-05"],
                ):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
        finally:
            os.unlink(db_path)

        self.assertEqual(exit_code, 0)
        self.assertIn("# Operator Report 2026-05", stdout.getvalue())
        self.assertIn("LLM usage: calls=1", stdout.getvalue())

    def test_monthly_operator_report_includes_report_quality_findings(self):
        db_path = self._make_db()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_root = Path(tmpdir)
                (output_root / "digests").mkdir()
                (output_root / "study_plans").mkdir()
                (output_root / "project_insights").mkdir()
                (output_root / "digests" / "2026-W19.md").write_text(
                    "## Decision Brief\n- Evaluated: 10 posts.\n\n"
                    "## Project Insights\n**project**\n- Source-backed insight\n\n"
                    "## What Changed\n- watch: 2\n",
                    encoding="utf-8",
                )
                (output_root / "study_plans" / "2026-W19.md").write_text(
                    "No Telegram signals this week.",
                    encoding="utf-8",
                )
                (output_root / "project_insights" / "2026-W19.md").write_text(
                    "## Project Insights - 2026-W19\n\nNo project insights were identified this week.\n",
                    encoding="utf-8",
                )

                with sqlite3.connect(db_path) as connection:
                    connection.row_factory = sqlite3.Row
                    connection.execute(
                        """
                        INSERT INTO quality_metrics (
                            week_label, computed_at, total_posts, strong_count, watch_count,
                            cultural_count, noise_count, project_match_count, output_word_count
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        ("2026-W19", "2026-05-14T10:00:00Z", 10, 0, 2, 0, 8, 1, 80),
                    )
                    connection.commit()
                    report = build_monthly_operator_report(
                        connection,
                        month="2026-05",
                        report_output_root=output_root,
                    )
        finally:
            os.unlink(db_path)

        self.assertIn("## Report Quality", report)
        self.assertIn("Report quality / artifact consistency", report)
        self.assertIn("critical=2", report)
        self.assertIn("Study Plan says no Telegram signals", report)
        self.assertIn("Project Insights artifact says no insights", report)

    def test_monthly_operator_report_includes_cost_guardrail_warnings(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                self._seed_report_rows(connection)
                connection.executemany(
                    """
                    INSERT INTO llm_usage (
                        model, input_tokens, output_tokens, est_cost_usd,
                        cost_usd, called_at, category, duration_ms
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            "claude-test",
                            50,
                            20,
                            0.01,
                            0.02,
                            "2026-05-06T10:00:00Z",
                            "topic_detection",
                            500,
                        ),
                        (
                            "claude-test",
                            300,
                            120,
                            0.10,
                            0.12,
                            "2026-05-20T10:00:00Z",
                            "preference_judge",
                            1500,
                        ),
                    ],
                )
                connection.commit()
                with patch.dict(
                    os.environ,
                    {
                        "LLM_WEEKLY_COST_BUDGET_USD": "0.05",
                        "LLM_WEEKLY_COST_SPIKE_RATIO": "2.0",
                    },
                ):
                    report = build_monthly_operator_report(connection, month="2026-05")
        finally:
            os.unlink(db_path)

        self.assertIn("LLM cost guardrail: status=warning", report)
        self.assertIn("weekly budget exceeded", report)
        self.assertIn("weekly cost spike", report)
        self.assertIn("highest_cost_category=preference_judge", report)
        self.assertIn("suggested_action: reduce candidate count before synthesis", report)


if __name__ == "__main__":
    unittest.main()
