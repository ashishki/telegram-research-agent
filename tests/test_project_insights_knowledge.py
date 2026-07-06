import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
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

from config.settings import Settings  # noqa: E402
from db.knowledge_atoms import record_knowledge_atom  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
from output.idea_threads import refresh_idea_threads  # noqa: E402
from output.map_project_insights import run_project_mapping  # noqa: E402


class TestProjectInsightsKnowledgeContext(unittest.TestCase):
    def test_project_insights_use_knowledge_threads_without_raw_keyword_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "agent.db")
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                run_migrations()

            settings = Settings(
                db_path=db_path,
                llm_api_key="",
                model_provider="anthropic",
                telegram_session_path="",
            )
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO projects (name, description, keywords, github_repo, active)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        "telegram-research-agent",
                        "AI research report pipeline",
                        json.dumps(["eval gates", "agent release"]),
                        "ashishki/telegram-research-agent",
                        1,
                    ),
                )
                record_knowledge_atom(
                    connection,
                    week_label="2026-W28",
                    atom_type="engineering_practice",
                    claim="Eval gates should block shallow agent release recommendations.",
                    summary="The thread is directly relevant to agent release quality gates.",
                    evidence_quote="eval gates for agent releases",
                    source_post_ids=[701],
                    source_urls=["https://t.me/ai_lab/701"],
                    entities=["eval gates", "agent release"],
                    practices=["eval-gated release"],
                    confidence=0.86,
                    novelty_score=0.66,
                    practical_utility_score=0.94,
                    first_seen_at="2026-07-06T08:00:00Z",
                    last_seen_at="2026-07-06T08:00:00Z",
                )

            refresh_idea_threads(settings, weeks=12, now=datetime(2026, 7, 8, tzinfo=timezone.utc))
            output_dir = Path(tmpdir) / "project_insights"
            with patch("output.map_project_insights._compute_week_label", return_value="2026-W28"), \
                 patch(
                     "output.map_project_insights._start_of_current_iso_week",
                     return_value=datetime(2026, 7, 6, tzinfo=timezone.utc),
                 ), \
                 patch("output.map_project_insights.PROJECT_INSIGHTS_OUTPUT_DIR", output_dir), \
                 patch("output.map_project_insights._project_is_curated", return_value=True), \
                 patch("output.map_project_insights._search_project_posts", return_value=[]), \
                 patch("output.map_project_insights.complete_json") as complete_mock, \
                 patch("output.map_project_insights._log_project_insights_quality_findings"):
                result = run_project_mapping(settings)

            complete_mock.assert_not_called()
            self.assertEqual(result["knowledge_thread_links"], 1)
            report = (output_dir / "2026-W28.md").read_text(encoding="utf-8")
            self.assertIn("Knowledge Thread", report)
            self.assertIn("Source atoms:", report)
            self.assertIn("https://t.me/ai_lab/701", report)
            self.assertNotIn("No project insights were identified", report)


if __name__ == "__main__":
    unittest.main()
