import sys
import types
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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

from output.generate_study_plan import generate_study_plan  # noqa: E402


class TestGenerateStudyPlan(unittest.TestCase):
    def test_generate_study_plan_uses_real_db_without_nested_transaction_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "study_plan.sqlite"
            settings = SimpleNamespace(db_path=str(db_path))
            week_label = "2026-W17"

            with sqlite3.connect(db_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS study_plans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        week_label TEXT NOT NULL UNIQUE,
                        generated_at TEXT NOT NULL,
                        content_md TEXT NOT NULL,
                        topics_covered TEXT,
                        reminder_sent_at TEXT,
                        completed_at TEXT,
                        completion_notes TEXT
                    );
                    CREATE TABLE IF NOT EXISTS posts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        raw_post_id INTEGER,
                        channel_username TEXT,
                        content TEXT,
                        posted_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS raw_posts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_url TEXT,
                        view_count INTEGER
                    );
                    CREATE TABLE IF NOT EXISTS post_topics (
                        post_id INTEGER,
                        topic_id INTEGER
                    );
                    CREATE TABLE IF NOT EXISTS topics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        label TEXT,
                        description TEXT
                    );
                    CREATE TABLE IF NOT EXISTS user_post_tags (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        post_id INTEGER NOT NULL,
                        tag TEXT NOT NULL,
                        note TEXT,
                        recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS project_context_snapshots (
                        project_id INTEGER PRIMARY KEY,
                        project_name TEXT NOT NULL,
                        github_repo TEXT,
                        source_commit_at TEXT,
                        summary TEXT NOT NULL DEFAULT '',
                        open_questions TEXT NOT NULL DEFAULT '',
                        recent_changes TEXT NOT NULL DEFAULT '',
                        context_json TEXT NOT NULL DEFAULT '{}',
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS llm_usage (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        called_at TEXT,
                        model TEXT,
                        task_type TEXT,
                        input_tokens INTEGER,
                        output_tokens INTEGER,
                        est_cost_usd REAL,
                        category TEXT,
                        cost_usd REAL,
                        duration_ms INTEGER
                    );
                    CREATE TABLE IF NOT EXISTS signal_evidence_items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        post_id INTEGER NOT NULL,
                        raw_post_id INTEGER NOT NULL,
                        week_label TEXT NOT NULL,
                        evidence_kind TEXT NOT NULL,
                        excerpt_text TEXT NOT NULL,
                        source_channel TEXT NOT NULL,
                        message_url TEXT,
                        posted_at TEXT NOT NULL,
                        topic_labels_json TEXT NOT NULL DEFAULT '[]',
                        project_names_json TEXT NOT NULL DEFAULT '[]',
                        selection_reason TEXT NOT NULL,
                        last_used_at TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS decision_journal (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        decision_scope TEXT NOT NULL,
                        subject_ref_type TEXT NOT NULL,
                        subject_ref_id TEXT NOT NULL,
                        project_name TEXT,
                        status TEXT NOT NULL,
                        reason TEXT,
                        evidence_item_ids_json TEXT NOT NULL DEFAULT '[]',
                        recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        recorded_by TEXT NOT NULL DEFAULT 'pipeline'
                    );
                    """
                )
                connection.commit()

            with patch("output.generate_study_plan._compute_week_label", return_value=week_label), \
                 patch("output.generate_study_plan._load_prompt_sections", return_value=("system", "{week_label} {topics_json}")), \
                 patch("output.generate_study_plan._fetch_books_catalog", return_value=[]), \
                 patch("output.generate_study_plan._fetch_project_context_snapshots", return_value=[]), \
                 patch("output.generate_study_plan.LLMClient.complete", return_value="study plan"), \
                 patch("output.generate_study_plan.refresh_all_project_context_snapshots"), \
                 patch("output.generate_study_plan.send_text"):
                content = generate_study_plan(settings)

            self.assertEqual("study plan", content)
            with sqlite3.connect(db_path) as connection:
                stored = connection.execute(
                    "SELECT content_md FROM study_plans WHERE week_label = ?",
                    (week_label,),
                ).fetchone()
            self.assertIsNotNone(stored)


if __name__ == "__main__":
    unittest.main()
