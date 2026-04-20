import sys
import types
import unittest
import sqlite3
import tempfile
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

from output.generate_recommendations import _render_insights_fragment, _rewrite_insight_source_urls, run_recommendations  # noqa: E402


class TestGenerateRecommendationsHtml(unittest.TestCase):
    def test_render_insights_fragment_wraps_paragraphs_and_links(self):
        content = (
            "<b>💡 Инсайты недели</b>\n\n"
            "<b>[Implement] Project</b>\n"
            "Полезный абзац с объяснением.\n"
            "https://example.com/source"
        )

        html = _render_insights_fragment(content)

        self.assertIn("<h2><b>💡 Инсайты недели</b></h2>", html)
        self.assertIn("<p><b>[Implement] Project</b></p>", html)
        self.assertIn("<p>Полезный абзац с объяснением. <a href=\"https://example.com/source\">https://example.com/source</a></p>", html)

    def test_rewrite_insight_source_urls_rebinds_to_best_matching_candidates(self):
        content = (
            "<b>💡 Инсайты недели</b>\n\n"
            "<b>[Implement] telegram-research-agent — Cross-channel clusters</b>\n"
            "Нужно отслеживать cluster spread по нескольким каналам и выделять это в дайджесте.\n"
            "<a href=\"https://t.me/NeuralShit/7342\">источник</a>\n\n"
            "<b>[Implement] gdev-agent — Cost-aware routing</b>\n"
            "В multi-tenant сервисе нужен дешёвый первый проход и дорогой только для неоднозначных кейсов.\n"
            "<a href=\"https://t.me/NeuralShit/7342\">источник</a>"
        )
        candidates = [
            {
                "url": "https://t.me/channelA/100",
                "project_name": "telegram-research-agent",
                "channel": "@signal_a",
                "match_text": "telegram-research-agent cross channel clusters spread digest theme week",
            },
            {
                "url": "https://t.me/channelB/200",
                "project_name": "gdev-agent",
                "channel": "@signal_b",
                "match_text": "gdev-agent cost aware routing cheap first pass multi tenant service classification",
            },
        ]

        rewritten = _rewrite_insight_source_urls(content, candidates)

        self.assertIn("https://t.me/channelA/100", rewritten)
        self.assertIn("https://t.me/channelB/200", rewritten)
        self.assertNotIn("https://t.me/NeuralShit/7342", rewritten)


class TestRunRecommendations(unittest.TestCase):
    def test_run_recommendations_continues_when_project_context_snapshots_fail(self):
        settings = SimpleNamespace(db_path=":memory:")

        with patch("output.generate_recommendations._load_digest_summary", return_value=("digest", "summary", [])), \
             patch("output.generate_recommendations._load_projects_context", return_value="projects"), \
             patch("output.generate_recommendations._load_project_context_snapshots", side_effect=RuntimeError("boom")), \
             patch("output.generate_recommendations._load_completed_study_history", return_value="study"), \
             patch("output.generate_recommendations._load_recent_decisions", return_value="decisions"), \
             patch("output.generate_recommendations._load_recent_project_evidence", return_value=("evidence", [])), \
             patch("output.generate_recommendations._load_prompt_sections", return_value=("system", "{project_context_snapshots}")), \
             patch("output.generate_recommendations.complete", return_value="insights") as complete_mock, \
             patch("output.generate_recommendations._rewrite_insight_source_urls", return_value="insights"), \
             patch("output.generate_recommendations.triage_insights", return_value=[]), \
             patch("output.generate_recommendations.render_triaged_insights_html", return_value="rendered"), \
             patch("output.generate_recommendations._write_insights_file"), \
             patch("output.generate_recommendations._write_insights_html_file"), \
             patch("output.generate_recommendations._store_recommendations"), \
             patch("output.generate_recommendations._send_recommendations_to_telegram_owner"):
            result = run_recommendations(settings)

        complete_mock.assert_called_once()
        self.assertEqual("rendered", result["text"])

    def test_run_recommendations_uses_real_db_without_nested_transaction_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "recommendations.sqlite"
            settings = SimpleNamespace(db_path=str(db_path))
            week_label = "2026-W17"

            with sqlite3.connect(db_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS digests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        week_label TEXT NOT NULL UNIQUE,
                        generated_at TEXT NOT NULL,
                        content_md TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS recommendations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        week_label TEXT NOT NULL UNIQUE,
                        generated_at TEXT NOT NULL,
                        content_md TEXT NOT NULL
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
                    CREATE TABLE IF NOT EXISTS post_topics (
                        post_id INTEGER,
                        topic_id INTEGER
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
                    CREATE TABLE IF NOT EXISTS topics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        label TEXT,
                        description TEXT
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
                    CREATE TABLE IF NOT EXISTS insight_triage_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        week_label TEXT NOT NULL,
                        title TEXT NOT NULL,
                        idea_type TEXT NOT NULL,
                        timing TEXT NOT NULL,
                        implementation_mode TEXT NOT NULL,
                        confidence TEXT NOT NULL,
                        evidence_strength TEXT NOT NULL,
                        main_risk TEXT NOT NULL,
                        recommendation TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        source_url TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS insight_rejection_memory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title_fingerprint TEXT NOT NULL UNIQUE,
                        title TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        rejected_at TEXT NOT NULL,
                        suppressed_until TEXT
                    );
                    """
                )
                connection.execute(
                    "INSERT INTO digests (week_label, generated_at, content_md) VALUES (?, ?, ?)",
                    (week_label, "2026-04-20T00:00:00Z", "digest"),
                )
                connection.commit()

            with patch("output.generate_recommendations._compute_week_label", return_value=week_label), \
                 patch("output.generate_recommendations.complete", return_value="<b>[Implement] Project — Idea</b>\nBody\n<a href=\"https://example.com/source\">источник</a>"), \
                 patch("output.generate_recommendations._load_project_context_snapshots", return_value="snapshot"), \
                 patch("output.generate_recommendations._send_recommendations_to_telegram_owner"), \
                 patch("output.generate_recommendations._write_insights_file"), \
                 patch("output.generate_recommendations._write_insights_html_file"):
                result = run_recommendations(settings)

            self.assertIn("Project", result["text"])
            with sqlite3.connect(db_path) as connection:
                stored = connection.execute(
                    "SELECT content_md FROM recommendations WHERE week_label = ?",
                    (week_label,),
                ).fetchone()
            self.assertIsNotNone(stored)


if __name__ == "__main__":
    unittest.main()
