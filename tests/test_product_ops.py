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
from output.ops_validation import validate_ops  # noqa: E402
from output.product_split import evaluate_product_split_gate  # noqa: E402
import main  # noqa: E402


class TestProductOps(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def _seed_product_gate_rows(self, connection: sqlite3.Connection) -> None:
        for week in ("2026-W18", "2026-W19", "2026-W20", "2026-W21"):
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
                    recorded_at,
                    recorded_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (week, json.dumps(["Signals"]), "[]", "[]", "[]", "[]", "[]", "2026-05-20T10:00:00Z", "operator"),
            )
        for decision_id in ("1", "2"):
            connection.execute(
                """
                INSERT INTO decision_journal (
                    decision_scope, subject_ref_type, subject_ref_id, status, reason, recorded_by, recorded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("insight", "insight_triage_id", decision_id, "acted_on", "used report", "telegram_button", "2026-05-21T10:00:00Z"),
            )
        connection.execute(
            """
            INSERT INTO source_observations (
                channel_username,
                week_label,
                repeated_claim_count,
                counters_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("source_a", "2026-W21", 1, "{}", "2026-05-22T10:00:00Z", "2026-05-22T10:00:00Z"),
        )
        connection.execute(
            """
            INSERT INTO research_brief_receipts (
                receipt_id,
                week_label,
                generated_at,
                post_counts_json,
                source_set_json,
                verification_status,
                health_flags_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "rbr_gate",
                "2026-W21",
                "2026-05-22T10:00:00Z",
                "{}",
                "{}",
                "verified",
                "[]",
                "2026-05-22T10:00:00Z",
                "2026-05-22T10:00:00Z",
            ),
        )
        connection.commit()

    def _seed_ops_rows(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT INTO reaction_sync_state (
                source, channel_username, message_id, emoji, action_key, applied_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("telegram_reaction", "source_a", 101, "🔥", "tag:strong", "2026-07-08T10:00:00Z"),
        )
        connection.execute(
            """
            INSERT INTO decision_journal (
                decision_scope, subject_ref_type, subject_ref_id, status, reason, recorded_by, recorded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("insight", "insight_triage_id", "7", "acted_on", "button", "telegram_button", "2026-07-08T10:00:00Z"),
        )
        connection.commit()

    def test_product_split_gate_can_return_go_when_thresholds_are_met(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                self._seed_product_gate_rows(connection)
                evaluation = evaluate_product_split_gate(connection)
        finally:
            os.unlink(db_path)

        self.assertEqual(evaluation["decision"], "go")
        self.assertTrue(all(check["passed"] for check in evaluation["checks"].values()))

    def test_product_split_gate_cli_prints_decision(self):
        db_path = self._make_db()
        stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(sys, "argv", ["main.py", "product-split-gate"]):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
        finally:
            os.unlink(db_path)

        self.assertEqual(exit_code, 0)
        self.assertIn("Product Split Gate", stdout.getvalue())
        self.assertIn("decision=no_go", stdout.getvalue())

    def test_ops_validation_passes_when_live_evidence_rows_exist(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                self._seed_ops_rows(connection)
                results = validate_ops(connection, kind="all", days=14)
        finally:
            os.unlink(db_path)

        self.assertEqual([result["status"] for result in results], ["passed", "passed"])

    def test_ops_validation_cli_reports_needs_live_event_without_rows(self):
        db_path = self._make_db()
        stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(sys, "argv", ["main.py", "ops-validate", "all"]):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
        finally:
            os.unlink(db_path)

        self.assertEqual(exit_code, 0)
        self.assertIn("reaction_sync: needs_live_event", stdout.getvalue())
        self.assertIn("callback_dispatch: needs_live_event", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
