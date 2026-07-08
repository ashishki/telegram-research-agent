import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
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

from db.ai_report_feedback import record_ai_report_feedback  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
from output.strategy_reviewer import build_strategy_review  # noqa: E402
import main  # noqa: E402


class TestStrategyReviewer(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def test_review_outputs_advisory_categories_and_codex_tasks(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                record_ai_report_feedback(
                    connection,
                    week_label="2026-W28",
                    feedback_type="too_shallow",
                    target_type="report_section",
                    target_ref="deep-explain",
                )
                record_ai_report_feedback(
                    connection,
                    week_label="2026-W28",
                    feedback_type="wrong_priority",
                    target_type="idea_thread",
                    target_ref="agent-frameworks",
                )
                record_ai_report_feedback(
                    connection,
                    week_label="2026-W28",
                    feedback_type="missed_important_post",
                    target_type="missed_post",
                    source_url="https://t.me/ai_lab/999",
                )
                review = build_strategy_review(connection, week_label="2026-W28")
        finally:
            os.unlink(db_path)

        self.assertTrue(review["suggestions"]["change"])
        self.assertTrue(review["suggestions"]["demote"])
        self.assertTrue(review["suggestions"]["test_next_week"])
        self.assertTrue(review["memory_only_updates"])
        self.assertTrue(review["approval_required"])
        self.assertTrue(review["codex_tasks"])
        self.assertTrue(review["risks"])
        self.assertTrue(all(task["requires_approval"] for task in review["codex_tasks"]))
        self.assertTrue(all(task["rationale"] for task in review["codex_tasks"]))
        self.assertTrue(all(task["files"] for task in review["codex_tasks"]))
        self.assertTrue(all(task["acceptance_criteria"] for task in review["codex_tasks"]))
        self.assertTrue(all(task["verification_commands"] for task in review["codex_tasks"]))
        self.assertEqual(review["mutation_policy"]["source_code"], "do_not_modify")
        self.assertEqual(review["mutation_policy"]["profile"], "do_not_modify")

    def test_strategy_reviewer_cli_writes_json_without_mutating_config(self):
        db_path = self._make_db()
        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir) / "strategy-review.json"
            try:
                with sqlite3.connect(db_path) as connection:
                    record_ai_report_feedback(
                        connection,
                        week_label="2026-W28",
                        feedback_type="useful",
                        target_type="action",
                        target_ref="eval-gates",
                    )
                with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                    with patch.object(
                        sys,
                        "argv",
                        [
                            "main.py",
                            "strategy-reviewer",
                            "--week",
                            "2026-W28",
                            "--output-path",
                            str(output_path),
                        ],
                    ):
                        exit_code = main.main()
                payload = json.loads(output_path.read_text(encoding="utf-8"))
            finally:
                os.unlink(db_path)

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["suggestions"]["keep"])
        self.assertEqual(payload["mutation_policy"]["projects"], "do_not_modify")


if __name__ == "__main__":
    unittest.main()
