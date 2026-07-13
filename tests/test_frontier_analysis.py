import io
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
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
from db.frontier_analysis import fetch_frontier_analysis  # noqa: E402
from db.knowledge_atoms import record_knowledge_atom  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
from output.frontier_analysis import run_frontier_analysis  # noqa: E402
from output.idea_threads import refresh_idea_threads  # noqa: E402
from output.reporting_period import resolve_reporting_period  # noqa: E402
import main  # noqa: E402


class TestFrontierAnalysis(unittest.TestCase):
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

    def _seed_threads(self, db_path: str) -> Settings:
        settings = self._settings(db_path)
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
                models=["Claude"],
                practices=["eval-gated release"],
                confidence=0.84,
                novelty_score=0.6,
                practical_utility_score=0.92,
                why_it_matters="This is actionable for AI engineering release discipline.",
                first_seen_at="2026-07-06T08:00:00Z",
                last_seen_at="2026-07-06T08:00:00Z",
            )
            record_knowledge_atom(
                connection,
                week_label="2026-W28",
                atom_type="risk_warning",
                claim="Teams can over-trust coding-agent changes when eval suites are shallow.",
                summary="The source warns that superficial checks can hide release risk.",
                evidence_quote="eval suites are shallow",
                source_post_ids=[303],
                source_urls=["https://t.me/research/303"],
                entities=["AI agents", "eval gates"],
                tools=["Codex"],
                models=["Claude"],
                practices=["eval-gated release"],
                confidence=0.74,
                novelty_score=0.65,
                practical_utility_score=0.82,
                first_seen_at="2026-07-07T10:00:00Z",
                last_seen_at="2026-07-07T10:00:00Z",
            )
        refresh_idea_threads(settings, weeks=12, now=datetime(2026, 7, 8, tzinfo=timezone.utc))
        return settings

    def _payload(self) -> str:
        return json.dumps(
            {
                "executive_brief": "Agent coding is moving from demos toward eval-gated release discipline.",
                "what_changed": [
                    {
                        "title": "Eval gates moved into the release path",
                        "summary": "The thread now has both practice and risk evidence.",
                        "why_it_matters": "It changes what should be tested before trusting agent output.",
                    }
                ],
                "trend_narratives": [
                    {
                        "thread_slug": "codex-claude-ai-agents",
                        "title": "Eval-gated agent workflows",
                        "narrative": "The idea evolved from isolated coding-agent use to release discipline.",
                        "status": "active",
                    }
                ],
                "study_now": [
                    {
                        "topic": "Eval design for coding agents",
                        "reason": "It is the bottleneck between useful demos and reliable workflows.",
                        "priority": "high",
                    }
                ],
                "actions": [
                    {
                        "title": "Build a tiny eval gate",
                        "next_step": "Create one regression check around an agent-written change.",
                        "success_criterion": "A failing agent edit is caught before merge.",
                    }
                ],
                "caveats": ["Evidence is source-grounded but still limited to the exported thread set."],
            }
        )

    def test_frontier_analysis_records_top_model_synthesis(self):
        db_path = self._make_db()
        try:
            settings = self._seed_threads(db_path)
            with patch("output.frontier_analysis.complete", return_value=self._payload()) as complete:
                summary = run_frontier_analysis(
                    settings,
                    week_label="2026-W28",
                    now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
                    lookback_weeks=12,
                    model="strong",
                    force=True,
                )
            with sqlite3.connect(db_path) as connection:
                row = fetch_frontier_analysis(connection, week_label="2026-W28")
        finally:
            os.unlink(db_path)

        self.assertEqual(complete.call_count, 1)
        self.assertEqual(summary.week_label, "2026-W28")
        self.assertEqual(summary.what_changed_count, 1)
        self.assertEqual(summary.study_now_count, 1)
        self.assertEqual(summary.action_count, 1)
        self.assertIsNotNone(row)
        self.assertIn("eval-gated release discipline", row["executive_brief"])
        self.assertEqual(row["study_now"][0]["topic"], "Eval design for coding agents")
        source_context = row["analysis"]["source_context"]
        self.assertEqual(source_context["run_date"], "2026-07-13")
        self.assertEqual(source_context["reporting_week"], "2026-W28")
        self.assertEqual(source_context["week_label"], "2026-W28")
        self.assertEqual(source_context["period_mode"], "explicit_iso_week")
        self.assertEqual(source_context["analysis_period_start"], "2026-07-06T00:00:00Z")
        self.assertEqual(source_context["analysis_period_end"], "2026-07-13T00:00:00Z")
        self.assertEqual(summary.generated_at, "2026-07-13T07:02:52Z")

    def test_frontier_analysis_cli_skips_existing_without_force(self):
        db_path = self._make_db()
        stdout = io.StringIO()
        try:
            settings = self._seed_threads(db_path)
            with patch("output.frontier_analysis.complete", return_value=self._payload()):
                run_frontier_analysis(
                    settings,
                    week_label="2026-W28",
                    now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
                    force=True,
                )
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch("output.frontier_analysis.complete", side_effect=AssertionError("should skip")):
                    with patch(
                        "output.frontier_analysis.resolve_reporting_period",
                        side_effect=lambda _now=None, **kwargs: resolve_reporting_period(
                            datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
                            **kwargs,
                        ),
                    ):
                        with patch.object(
                            sys,
                            "argv",
                            ["main.py", "frontier-analysis", "--week", "2026-W28"],
                        ):
                            with redirect_stdout(stdout):
                                exit_code = main.main()
        finally:
            os.unlink(db_path)

        self.assertEqual(exit_code, 0)
        self.assertIn("skipped_existing=true", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
