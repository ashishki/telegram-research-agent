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
from db.frontier_analysis import upsert_frontier_analysis  # noqa: E402
from db.knowledge_atoms import record_knowledge_atom  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
from output.ai_intelligence_report import (  # noqa: E402
    AiIntelligenceReportQualityError,
    REQUIRED_SECTIONS,
    _learning_actions,
    _read_queue_atoms,
    generate_ai_intelligence_report,
    validate_ai_intelligence_html,
)
from output.idea_threads import refresh_idea_threads  # noqa: E402
import main  # noqa: E402


class TestAiIntelligenceReport(unittest.TestCase):
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

    def _seed_atoms(self, db_path: str) -> None:
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
                atom_type="tutorial_resource",
                claim="A tutorial shows how to wire coding-agent eval checks into CI.",
                summary="The post is a useful read queue item for eval-gated release setup.",
                evidence_quote="wire coding-agent eval checks into CI",
                source_post_ids=[202],
                source_urls=["https://t.me/ml_ops/202"],
                entities=["AI agents", "eval gates"],
                tools=["Codex"],
                models=["Claude"],
                practices=["eval-gated release"],
                confidence=0.78,
                novelty_score=0.72,
                practical_utility_score=0.88,
                why_it_matters="It can be read and tried this week.",
                first_seen_at="2026-07-07T09:00:00Z",
                last_seen_at="2026-07-07T09:00:00Z",
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

    def _seed_marked_post(self, db_path: str) -> None:
        with sqlite3.connect(db_path) as connection:
            posted_at = "2026-07-07T11:00:00Z"
            connection.execute(
                """
                INSERT INTO raw_posts (
                    id, channel_username, channel_id, message_id, posted_at, text,
                    media_type, media_caption, forward_from, view_count, message_url,
                    raw_json, ingested_at, image_description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    701,
                    "@ai_lab",
                    10,
                    701,
                    posted_at,
                    "Operator-marked source post about eval-gated agent workflows.",
                    None,
                    None,
                    None,
                    100,
                    "https://t.me/ai_lab/701",
                    "{}",
                    posted_at,
                    None,
                ),
            )
            connection.execute(
                """
                INSERT INTO posts (
                    id, raw_post_id, channel_username, posted_at, content,
                    url_count, has_code, language_detected, word_count, normalized_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    701,
                    701,
                    "@ai_lab",
                    posted_at,
                    "Operator-marked source post about eval-gated agent workflows.",
                    0,
                    0,
                    "en",
                    8,
                    posted_at,
                ),
            )
            connection.commit()
            connection.execute(
                """
                INSERT INTO signal_feedback (post_id, feedback, recorded_at)
                VALUES (?, ?, ?)
                """,
                (701, "operator_marked_interesting", "2026-07-07T12:00:00Z"),
            )
            connection.commit()

    def test_generates_standalone_html_with_required_sections_sources_and_actions(self):
        db_path = self._make_db()
        self._seed_atoms(db_path)
        self._seed_marked_post(db_path)
        with tempfile.TemporaryDirectory() as output_dir:
            try:
                settings = self._settings(db_path)
                refresh_idea_threads(
                    settings,
                    weeks=12,
                    now=datetime(2026, 7, 8, tzinfo=timezone.utc),
                )
                with sqlite3.connect(db_path) as connection:
                    upsert_frontier_analysis(
                        connection,
                        week_label="2026-W28",
                        generated_at="2026-07-08T00:00:00Z",
                        model="claude-opus-4-6",
                        prompt_version="frontier-analysis-v1",
                        lookback_weeks=12,
                        threads_analyzed=1,
                        atoms_analyzed=3,
                        executive_brief="Top-model synthesis says eval-gated agent workflows are becoming practical.",
                        what_changed=[
                            {
                                "title": "Eval gates moved into practice",
                                "summary": "The thread now combines implementation and risk signals.",
                                "why_it_matters": "It changes what to verify before using agent output.",
                            }
                        ],
                        trend_narratives=[
                            {
                                "title": "Eval-gated agent workflows",
                                "narrative": "The idea moved from isolated demos toward release discipline.",
                            }
                        ],
                        study_now=[
                            {
                                "topic": "Coding-agent eval design",
                                "reason": "It is the bridge from useful demos to repeatable engineering.",
                            }
                        ],
                        actions=[
                            {
                                "title": "Build one tiny eval gate",
                                "next_step": "Catch a bad agent edit before merge.",
                            }
                        ],
                        caveats=["Evidence is still bounded to the current thread set."],
                        analysis={},
                    )
                summary = generate_ai_intelligence_report(
                    settings,
                    week_label="2026-W28",
                    output_root=output_dir,
                    now=datetime(2026, 7, 8, tzinfo=timezone.utc),
                )
                html_text = Path(summary.html_path).read_text(encoding="utf-8")
                metadata = json.loads(Path(summary.json_path).read_text(encoding="utf-8"))
            finally:
                os.unlink(db_path)

        self.assertEqual(summary.week_label, "2026-W28")
        self.assertEqual(summary.thread_count, 1)
        self.assertEqual(summary.source_atom_count, 3)
        self.assertEqual(summary.action_count, 1)
        self.assertEqual(summary.quality_finding_count, 0)
        for section_id, title in REQUIRED_SECTIONS:
            self.assertIn(f'id="{section_id}"', html_text)
            self.assertIn(title, html_text)
        self.assertIn("<!doctype html>", html_text)
        self.assertIn("AI Intelligence Report - 2026-W28", html_text)
        self.assertIn("Frontier Analysis", html_text)
        self.assertIn("Top-model synthesis says eval-gated agent workflows are becoming practical.", html_text)
        self.assertIn("Coding-agent eval design", html_text)
        self.assertIn("https://t.me/ai_lab/101", html_text)
        self.assertIn("Source Map", html_text)
        self.assertIn("Appendix: grouped source posts", html_text)
        self.assertIn("action-card", html_text)
        self.assertIn("Personal Learning Loop", html_text)
        self.assertIn("What Feedback Changed This Week", html_text)
        self.assertIn("personalization confidence is low", html_text)
        self.assertIn("Posts you marked this week", html_text)
        self.assertIn("https://t.me/ai_lab/701", html_text)
        self.assertEqual(metadata["marked_posts"][0]["feedback"], "operator_marked_interesting")
        self.assertEqual(html_text.count('class="learning-read-item"'), 5)
        self.assertEqual(html_text.count('class="learning-try-item"'), 2)
        self.assertIn("Small Experiment", html_text)
        self.assertIn("Skill Gap", html_text)
        self.assertIn("Reflection Question", html_text)
        self.assertNotIn("Matches:", html_text)
        self.assertEqual(metadata["thread_count"], 1)
        self.assertEqual(metadata["frontier_analysis"]["model"], "claude-opus-4-6")
        self.assertTrue(metadata["compressed_context"])
        self.assertTrue(metadata["actions"])
        self.assertEqual(len(metadata["personal_learning_loop"]["read_items"]), 5)
        self.assertEqual(len(metadata["personal_learning_loop"]["try_items"]), 2)
        self.assertIn("reflection_question", metadata["personal_learning_loop"])
        self.assertIn("AI Intelligence Report 2026-W28 is ready", summary.notification_text)

    def test_quality_gate_blocks_internal_match_traces(self):
        all_sections = "".join(
            f'<section id="{section_id}"><h2>{title}</h2></section>'
            for section_id, title in REQUIRED_SECTIONS
        )
        html_text = f"<html><body>{all_sections}<article class=\"action-card\">x</article><p>Matches: repo keyword</p></body></html>"
        findings = validate_ai_intelligence_html(html_text)
        self.assertTrue(any("Internal matching trace" in finding.message for finding in findings))

    def test_generation_raises_when_quality_gate_finds_trace(self):
        db_path = self._make_db()
        with tempfile.TemporaryDirectory() as output_dir:
            try:
                settings = self._settings(db_path)
                trace_html = "".join(
                    f'<section id="{section_id}"><h2>{title}</h2></section>'
                    for section_id, title in REQUIRED_SECTIONS
                )
                trace_html = f"<html><body>{trace_html}<article class=\"action-card\">x</article><p>Matches: leaked trace</p></body></html>"
                with patch("output.ai_intelligence_report.render_ai_intelligence_html", return_value=(trace_html, [])):
                    with self.assertRaises(AiIntelligenceReportQualityError):
                        generate_ai_intelligence_report(
                            settings,
                            week_label="2026-W28",
                            output_root=output_dir,
                            now=datetime(2026, 7, 8, tzinfo=timezone.utc),
                        )
            finally:
                os.unlink(db_path)

    def test_ai_intelligence_report_cli_writes_report_and_notification(self):
        db_path = self._make_db()
        self._seed_atoms(db_path)
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as output_dir:
            try:
                settings = self._settings(db_path)
                refresh_idea_threads(
                    settings,
                    weeks=12,
                    now=datetime(2026, 7, 8, tzinfo=timezone.utc),
                )
                with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                    with patch.object(
                        sys,
                        "argv",
                        [
                            "main.py",
                            "ai-intelligence-report",
                            "--week",
                            "2026-W28",
                            "--skip-refresh",
                            "--output-root",
                            output_dir,
                        ],
                    ):
                        with redirect_stdout(stdout):
                            exit_code = main.main()
                html_path = Path(output_dir) / "2026-W28.html"
                json_path = Path(output_dir) / "2026-W28.json"
                html_exists = html_path.exists()
                json_exists = json_path.exists()
            finally:
                os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertTrue(html_exists)
        self.assertTrue(json_exists)
        self.assertIn(str(html_path), output)
        self.assertIn("notification=AI Intelligence Report 2026-W28 is ready.", output)
        self.assertIn("threads=1", output)
        self.assertIn("source_atoms=3", output)

    def test_feedback_promotes_related_read_queue_atoms(self):
        threads = [
            {
                "slug": "generic-agent-news",
                "title": "Generic agent news",
                "atoms": [
                    {
                        "id": 1,
                        "atom_type": "tutorial_resource",
                        "claim": "A broad agent tutorial.",
                        "summary": "Broad but high-scoring.",
                        "practical_utility_score": 0.99,
                        "novelty_score": 0.9,
                        "confidence": 0.9,
                    }
                ],
            },
            {
                "slug": "eval-gates",
                "title": "Eval gates",
                "atoms": [
                    {
                        "id": 2,
                        "atom_type": "tutorial_resource",
                        "claim": "A specific eval-gate setup.",
                        "summary": "Lower raw score but promoted by feedback.",
                        "practical_utility_score": 0.2,
                        "novelty_score": 0.2,
                        "confidence": 0.8,
                    }
                ],
            },
        ]

        atoms = _read_queue_atoms(
            threads,
            {
                "promoted_target_refs": ["knowledge_atom:2"],
                "downranked_target_refs": [],
                "downranked_thread_slugs": [],
                "downranked_atom_refs": [],
            },
        )

        self.assertEqual(atoms[0]["id"], 2)

    def test_feedback_downranks_related_learning_actions(self):
        threads = [
            {
                "slug": "agent-frameworks",
                "title": "Agent Frameworks",
                "status": "active",
                "momentum_30d": 0.95,
                "source_channel_count": 5,
                "current_claims": ["Framework churn is noisy."],
                "atoms": [],
            },
            {
                "slug": "eval-gates",
                "title": "Eval Gates",
                "status": "active",
                "momentum_30d": 0.2,
                "source_channel_count": 1,
                "current_claims": ["Eval gates are useful."],
                "atoms": [],
            },
        ]

        actions = _learning_actions(
            threads,
            {
                "downranked_target_refs": ["action:agent-frameworks"],
                "promoted_target_refs": ["experiment:eval-gates"],
                "downranked_thread_slugs": [],
                "counts_by_feedback": {"wrong_priority": 1, "useful": 1},
                "missed_post_eval_examples": [],
            },
        )

        self.assertIn("Eval Gates", actions[0]["title"])


if __name__ == "__main__":
    unittest.main()
