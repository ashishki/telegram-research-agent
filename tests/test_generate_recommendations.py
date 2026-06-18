import sys
import types
import unittest
import sqlite3
import subprocess
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

from output.generate_recommendations import (  # noqa: E402
    MAX_FEEDBACK_CARD_TEXT_CHARS,
    _build_feedback_card_text,
    _html_to_copyable_text,
    _normalize_insights_delivery_text,
    _render_insights_fragment,
    _rewrite_insight_source_urls,
    _send_recommendations_to_telegram_owner,
    run_recommendations,
)
from output.project_memory_pack import build_project_memory_pack  # noqa: E402


class TestGenerateRecommendationsHtml(unittest.TestCase):
    def test_build_project_memory_pack_reads_vault_tasks_and_git_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            repo_path = workspace / "sample-repo"
            repo_path.mkdir()
            vault_path = workspace / "engineering-cognition-vault"
            (vault_path / "10-projects").mkdir(parents=True)
            (vault_path / "_generated" / "summaries").mkdir(parents=True)
            (vault_path / "40-findings").mkdir()
            (vault_path / "50-patterns").mkdir()
            projects_yaml = Path(tmpdir) / "projects.yaml"
            projects_yaml.write_text(
                """
projects:
  - name: sample-project
    repo: owner/sample-repo
    focus: current focus area
""",
                encoding="utf-8",
            )
            (repo_path / "docs").mkdir()
            (vault_path / "10-projects" / "sample-project.md").write_text(
                """
## Active Capability Profiles
Report quality and project-aware recommendations.

## Open Findings
- Needs source freshness diagnostics.

## Context Packet Scopes
- implementation recommendation quality
""",
                encoding="utf-8",
            )
            (vault_path / "_generated" / "summaries" / "sample-project.catalog.md").write_text(
                """
## Canonical Artifacts

| Path | Kind | Title |
|------|------|-------|
| `docs/tasks.md` | task_graph | Current Backlog |
""",
                encoding="utf-8",
            )
            (vault_path / "40-findings" / "open-findings-map.md").write_text(
                "| Project | Gap |\n|---|---|\n| [[sample-project]] | Needs decision log |\n",
                encoding="utf-8",
            )
            (vault_path / "50-patterns" / "deterministic-before-llm.md").write_text(
                "# Deterministic Before LLM\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "init"], cwd=vault_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=vault_path, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=vault_path, check=True)
            subprocess.run(["git", "add", "."], cwd=vault_path, check=True)
            subprocess.run(["git", "commit", "-m", "Seed vault"], cwd=vault_path, check=True, capture_output=True)
            (repo_path / "docs" / "tasks.md").write_text(
                """
- [ ] Add source freshness gate
- [x] Ship weekly message formatter
""",
                encoding="utf-8",
            )
            (repo_path / "README.md").write_text("Sample repo\n", encoding="utf-8")
            subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            subprocess.run(["git", "commit", "-m", "Ship weekly formatter"], cwd=repo_path, check=True, capture_output=True)

            pack = build_project_memory_pack(
                projects_yaml_path=projects_yaml,
                workspace_root=workspace,
                vault_root=vault_path,
            )

        self.assertIn("sample-project", pack)
        self.assertIn("Vault freshness: no upstream; pull skipped", pack)
        self.assertIn("Report quality and project-aware recommendations", pack)
        self.assertIn("Needs source freshness diagnostics", pack)
        self.assertIn("Current Backlog", pack)
        self.assertIn("Add source freshness gate", pack)
        self.assertIn("Ship weekly message formatter", pack)
        self.assertIn("Ship weekly formatter", pack)

    def test_feedback_card_text_is_compact_without_losing_decision_context(self):
        with sqlite3.connect(":memory:") as connection:
            connection.row_factory = sqlite3.Row
            connection.execute(
                """
                CREATE TABLE insight_triage_records (
                    id INTEGER,
                    title TEXT,
                    reason TEXT,
                    recommendation TEXT
                )
                """
            )
            connection.execute(
                """
                INSERT INTO insight_triage_records (id, title, reason, recommendation)
                VALUES (?, ?, ?, ?)
                """,
                (
                    7,
                    "<b>[Implement] telegram-research-agent - Add a very long implementation card title that should not dominate Telegram</b>",
                    "This reason is intentionally verbose. " * 20,
                    "do_now",
                ),
            )
            row = connection.execute("SELECT * FROM insight_triage_records").fetchone()

        text = _build_feedback_card_text(row, "2026-W22")

        self.assertLessEqual(len(text), MAX_FEEDBACK_CARD_TEXT_CHARS)
        self.assertIn("Implementation idea #7 | 2026-W22", text)
        self.assertIn("Do now:", text)
        self.assertIn("Why:", text)
        self.assertIn("Choose:", text)

    def test_recommendations_notification_includes_artifact_feedback_markup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            html_path = Path(tmpdir) / "ideas.html"
            html_path.write_text("<html><body>ideas</body></html>", encoding="utf-8")
            with sqlite3.connect(":memory:") as connection:
                connection.row_factory = sqlite3.Row
                connection.execute(
                    """
                    CREATE TABLE recommendations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        week_label TEXT NOT NULL UNIQUE,
                        generated_at TEXT,
                        content_md TEXT,
                        telegraph_url TEXT,
                        telegram_sent_at TEXT
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO recommendations (week_label, generated_at, content_md) VALUES (?, ?, ?)",
                    ("2026-W22", "2026-05-26T00:00:00Z", "ideas"),
                )
                connection.execute(
                    """
                    CREATE TABLE insight_triage_records (
                        id INTEGER,
                        week_label TEXT,
                        title TEXT,
                        reason TEXT,
                        recommendation TEXT
                    )
                    """
                )
                connection.commit()

                with patch.dict(
                    "os.environ",
                    {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_OWNER_CHAT_ID": "42"},
                ), patch(
                    "output.generate_recommendations.publish_article",
                    return_value="https://telegra.ph/ideas",
                ), patch(
                    "output.generate_recommendations.send_text",
                ) as mock_text, patch(
                    "output.generate_recommendations._send_copyable_insights_document",
                ):
                    _send_recommendations_to_telegram_owner(
                        connection,
                        week_label="2026-W22",
                        content_md="ideas",
                        html_path=html_path,
                        force_delivery=True,
                    )

        self.assertEqual(
            mock_text.call_args.kwargs["reply_markup"]["inline_keyboard"][0][0]["callback_data"],
            "art:2026-W22:ii:u",
        )

    def test_render_insights_fragment_wraps_paragraphs_and_links(self):
        content = (
            "<b>💡 Инсайты недели</b>\n\n"
            "<b>[Implement] Project</b>\n"
            "Полезный абзац с объяснением.\n"
            "https://t.me/source_chan/123"
        )

        html = _render_insights_fragment(content)

        self.assertIn("<h2><b>💡 Инсайты недели</b></h2>", html)
        self.assertIn("<h4><b>[Implement] Project</b></h4>", html)
        self.assertIn("<p>Полезный абзац с объяснением. <a href=\"https://t.me/source_chan/123\">https://t.me/source_chan/123</a></p>", html)

    def test_html_to_copyable_text_preserves_anchor_url(self):
        text = _html_to_copyable_text('<b>[Implement] Project</b>\n<a href="https://t.me/source_chan/123">источник</a>')

        self.assertIn("[Implement] Project", text)
        self.assertIn("источник: https://t.me/source_chan/123", text)

    def test_normalize_insights_delivery_text_removes_stale_duplicate_section_heading(self):
        content = (
            "<b>🧱 Собранные идеи</b>\n\n"
            "<b>[Implement] Project A</b>\n"
            "Body.\n"
            "<b>🆕 Отдельные сигналы</b>\n"
            "<i>(✅ Сделать сейчас — Direct improvement to existing project with cited evidence)</i>\n\n"
            "<b>🆕 Отдельные сигналы</b>\n\n"
            "<b>[Implement] Project B</b>\n"
            "Body."
        )

        normalized = _normalize_insights_delivery_text(content)
        html = _render_insights_fragment(content)
        copy_text = _html_to_copyable_text(content)

        self.assertEqual(normalized.count("🆕 Отдельные сигналы"), 1)
        self.assertEqual(html.count("🆕 Отдельные сигналы"), 1)
        self.assertEqual(copy_text.count("🆕 Отдельные сигналы"), 1)

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

    def test_rewrite_insight_source_urls_keeps_one_source_anchor_per_idea(self):
        content = (
            "<b>💡 Инсайты недели</b>\n\n"
            "<b>[Implement] project — Eval layer</b>\n"
            "Body mentions eval quality.\n"
            "<a href=\"https://t.me/source_a/123\">источник</a>\n"
            "<a href=\"https://t.me/source_b/1\">источник (extra benchmark)</a>"
        )
        candidates = [
            {
                "url": "https://t.me/source_a/123",
                "project_name": "project",
                "channel": "@source_a",
                "match_text": "project eval quality",
            }
        ]

        rewritten = _rewrite_insight_source_urls(content, candidates)

        self.assertIn("https://t.me/source_a/123", rewritten)
        self.assertNotIn("https://t.me/source_b/1", rewritten)
        self.assertEqual(rewritten.count("источник"), 1)


class TestRunRecommendations(unittest.TestCase):
    def test_run_recommendations_continues_when_project_context_snapshots_fail(self):
        settings = SimpleNamespace(db_path=":memory:")

        with patch("output.generate_recommendations._load_digest_summary", return_value=("digest", "summary", [])), \
             patch("output.generate_recommendations._load_projects_context", return_value="projects"), \
             patch("output.generate_recommendations.build_project_memory_pack", return_value="memory-pack"), \
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

    def test_run_recommendations_passes_project_memory_pack_to_prompt(self):
        settings = SimpleNamespace(db_path=":memory:")

        with patch("output.generate_recommendations._load_digest_summary", return_value=("digest", "summary", [])), \
             patch("output.generate_recommendations._load_projects_context", return_value="projects"), \
             patch("output.generate_recommendations.build_project_memory_pack", return_value="CURRENT PROJECT INTENT"), \
             patch("output.generate_recommendations._load_project_context_snapshots", return_value="snapshot"), \
             patch("output.generate_recommendations._load_completed_study_history", return_value="study"), \
             patch("output.generate_recommendations._load_recent_decisions", return_value="decisions"), \
             patch("output.generate_recommendations._load_recent_project_evidence", return_value=("evidence", [])), \
             patch("output.generate_recommendations._load_prompt_sections", return_value=("system", "{project_memory_pack}")), \
             patch("output.generate_recommendations.complete", return_value="insights") as complete_mock, \
             patch("output.generate_recommendations._rewrite_insight_source_urls", return_value="insights"), \
             patch("output.generate_recommendations.triage_insights", return_value=[]), \
             patch("output.generate_recommendations.render_triaged_insights_html", return_value="rendered"), \
             patch("output.generate_recommendations._write_insights_file"), \
             patch("output.generate_recommendations._write_insights_html_file"), \
             patch("output.generate_recommendations._store_recommendations"), \
             patch("output.generate_recommendations._send_recommendations_to_telegram_owner"):
            run_recommendations(settings)

        self.assertEqual("CURRENT PROJECT INTENT", complete_mock.call_args.kwargs["prompt"])

    def test_run_recommendations_stores_insufficient_evidence_note_for_unsupported_ideas(self):
        settings = SimpleNamespace(db_path=":memory:")
        unsupported_html = (
            "<b>💡 Инсайты недели</b>\n\n"
            "<b>[Implement] Project — Unsupported idea</b>\n"
            "Ship this with a generic source link.\n"
            '<a href="https://example.com/source">источник</a>'
        )

        with patch("output.generate_recommendations._load_digest_summary", return_value=("digest", "summary", [])), \
             patch("output.generate_recommendations._load_projects_context", return_value="projects"), \
             patch("output.generate_recommendations.build_project_memory_pack", return_value="memory-pack"), \
             patch("output.generate_recommendations._load_project_context_snapshots", return_value="snapshot"), \
             patch("output.generate_recommendations._load_completed_study_history", return_value="study"), \
             patch("output.generate_recommendations._load_recent_decisions", return_value="decisions"), \
             patch("output.generate_recommendations._load_recent_project_evidence", return_value=("evidence", [])), \
             patch("output.generate_recommendations._load_prompt_sections", return_value=("system", "{recent_evidence}")), \
             patch("output.generate_recommendations.complete", return_value=unsupported_html), \
             patch("output.generate_recommendations.triage_insights", return_value=[]), \
             patch("output.generate_recommendations._write_insights_file"), \
             patch("output.generate_recommendations._write_insights_html_file"), \
             patch("output.generate_recommendations._store_recommendations") as store_mock, \
             patch("output.generate_recommendations._send_recommendations_to_telegram_owner"):
            result = run_recommendations(settings)

        self.assertIn("Недостаточно доказательств", result["text"])
        self.assertIn("No source-backed implementation ideas this week", result["text"])
        self.assertNotIn("[Implement] Project", result["text"])
        stored_text = store_mock.call_args.args[2]
        self.assertEqual(result["text"], stored_text)

    def test_run_recommendations_blocks_llm_when_project_context_is_stale(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "recommendations.sqlite"
            settings = SimpleNamespace(db_path=str(db_path))
            week_label = "2026-W25"

            with sqlite3.connect(db_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE digests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        week_label TEXT NOT NULL UNIQUE,
                        generated_at TEXT NOT NULL,
                        content_md TEXT NOT NULL
                    );
                    CREATE TABLE recommendations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        week_label TEXT NOT NULL UNIQUE,
                        generated_at TEXT NOT NULL,
                        content_md TEXT NOT NULL
                    );
                    CREATE TABLE projects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        keywords TEXT,
                        github_repo TEXT,
                        last_commit_at TEXT,
                        github_synced_at TEXT,
                        active INTEGER DEFAULT 1
                    );
                    CREATE TABLE project_context_snapshots (
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
                    """
                )
                connection.execute(
                    "INSERT INTO digests (week_label, generated_at, content_md) VALUES (?, ?, ?)",
                    (week_label, "2026-06-15T00:00:00Z", "digest"),
                )
                connection.execute(
                    """
                    INSERT INTO projects (id, name, github_repo, last_commit_at, github_synced_at, active)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        "owner/repo",
                        "owner/repo",
                        "2026-05-29T00:00:00Z",
                        "2026-06-08T00:00:00Z",
                        1,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO project_context_snapshots (
                        project_id, project_name, github_repo, source_commit_at, summary, recent_changes, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        "owner/repo",
                        "owner/repo",
                        "2026-05-29T00:00:00Z",
                        "Old summary",
                        "",
                        "2026-06-18T00:00:00Z",
                    ),
                )
                connection.commit()

            with patch("output.generate_recommendations._compute_week_label", return_value=week_label), \
                 patch("output.generate_recommendations._load_digest_summary", return_value=("digest", "summary", [])), \
                 patch("output.generate_recommendations._load_project_repos", return_value=["owner/repo"]), \
                 patch(
                     "output.generate_recommendations._maybe_sync_project_context",
                     return_value={"attempted": True, "repos_synced": 0, "error": "", "reason": ""},
                 ), \
                 patch("output.generate_recommendations._load_projects_context", return_value="projects"), \
                 patch("output.generate_recommendations._load_project_context_snapshots", return_value="snapshot"), \
                 patch("output.generate_recommendations.complete") as complete_mock, \
                 patch("output.generate_recommendations._write_insights_file", return_value=Path(tmpdir) / "out.md"), \
                 patch("output.generate_recommendations._write_insights_html_file", return_value=Path(tmpdir) / "out.html"), \
                 patch("output.generate_recommendations._send_recommendations_to_telegram_owner"):
                result = run_recommendations(settings)

            complete_mock.assert_not_called()
            self.assertIn("контекст проектов устарел", result["text"])
            self.assertFalse(result["project_freshness"]["gate_passed"])
            with sqlite3.connect(db_path) as connection:
                stored = connection.execute(
                    "SELECT content_md FROM recommendations WHERE week_label = ?",
                    (week_label,),
                ).fetchone()
            self.assertIsNotNone(stored)
            self.assertIn("Implementation-рекомендации заблокированы", stored[0])

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
                 patch("output.generate_recommendations.complete", return_value="<b>[Implement] Project — Idea</b>\nBody\n<a href=\"https://t.me/source_chan/123\">источник</a>"), \
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
