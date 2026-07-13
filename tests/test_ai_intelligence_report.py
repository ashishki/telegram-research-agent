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
from db.ai_report_feedback import record_ai_report_feedback  # noqa: E402
from db.frontier_analysis import upsert_frontier_analysis  # noqa: E402
from db.knowledge_atoms import record_knowledge_atom  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
from output.ai_intelligence_report import (  # noqa: E402
    AiIntelligenceReportQualityError,
    REQUIRED_SECTIONS,
    _learning_actions,
    _reaction_ranked_threads_for_navigation,
    _read_queue_atoms,
    generate_ai_intelligence_report,
    load_ai_intelligence_context,
    validate_ai_intelligence_html,
)
from output.ai_report_contract import _thread_deltas  # noqa: E402
from output.idea_threads import refresh_idea_threads  # noqa: E402
from output.reporting_period import resolve_reporting_period  # noqa: E402
import main  # noqa: E402


class TestAiIntelligenceReport(unittest.TestCase):
    def test_thread_deltas_do_not_relabel_old_atoms_as_current_period_evidence(self):
        context = {
            "week_start": "2026-07-06T00:00:00Z",
            "week_end": "2026-07-13T00:00:00Z",
        }
        threads = [
            {
                "id": 1,
                "slug": "historical-only",
                "title": "Historical only",
                "changed_this_week": False,
                "atoms": [
                    {
                        "id": 10,
                        "claim": "Evidence from before the reporting period.",
                        "last_seen_at": "2026-07-05T23:59:59Z",
                        "confidence": 0.8,
                    }
                ],
            }
        ]

        self.assertEqual(_thread_deltas(context, threads), [])

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
        self._insert_marked_post(
            db_path,
            post_id=701,
            posted_at="2026-07-07T11:00:00Z",
            recorded_at="2026-07-07T12:00:00Z",
        )

    def _insert_marked_post(
        self,
        db_path: str,
        *,
        post_id: int,
        posted_at: str,
        recorded_at: str,
    ) -> None:
        with sqlite3.connect(db_path) as connection:
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
                    post_id,
                    "@ai_lab",
                    10,
                    post_id,
                    posted_at,
                    "Operator-marked source post about eval-gated agent workflows.",
                    None,
                    None,
                    None,
                    100,
                    f"https://t.me/ai_lab/{post_id}",
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
                    post_id,
                    post_id,
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
                (post_id, "operator_marked_interesting", recorded_at),
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
                        analysis={
                            "source_context": {
                                "run_date": "2026-07-13",
                                "generated_at": "2026-07-13T07:02:52Z",
                                "reporting_week": "2026-W28",
                                "week_label": "2026-W28",
                                "period_mode": "completed_iso_week",
                                "analysis_period_start": "2026-07-06T00:00:00Z",
                                "analysis_period_end": "2026-07-13T00:00:00Z",
                            }
                        },
                    )
                summary = generate_ai_intelligence_report(
                    settings,
                    output_root=output_dir,
                    now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
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
        self.assertIn("AI Intelligence Report - 6-12 июля 2026 (2026-W28)", html_text)
        self.assertIn("Generated 2026-07-13T07:02:52Z", html_text)
        self.assertIn("Frontier Analysis", html_text)
        self.assertIn("Top-model synthesis says eval-gated agent workflows are becoming practical.", html_text)
        self.assertIn("Coding-agent eval design", html_text)
        self.assertIn("https://t.me/ai_lab/101", html_text)
        self.assertIn("Source Map", html_text)
        self.assertIn("Appendix: grouped source posts", html_text)
        self.assertIn("action-card", html_text)
        self.assertIn("Personal Learning Loop", html_text)
        self.assertIn("What Feedback Changed This Week", html_text)
        self.assertIn("personalization state is unknown", html_text)
        self.assertIn("no-feedback is not a negative signal", html_text)
        self.assertIn("Why selected:", html_text)
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
        self.assertEqual(metadata["run_date"], "2026-07-13")
        self.assertEqual(metadata["reporting_week"], "2026-W28")
        self.assertEqual(metadata["week_label"], "2026-W28")
        self.assertEqual(metadata["period_mode"], "completed_iso_week")
        self.assertEqual(metadata["analysis_period_start"], "2026-07-06T00:00:00Z")
        self.assertEqual(metadata["analysis_period_end"], "2026-07-13T00:00:00Z")
        self.assertEqual(metadata["frontier_analysis"]["model"], "claude-opus-4-6")
        self.assertTrue(metadata["compressed_context"])
        self.assertTrue(metadata["actions"])
        self.assertTrue(metadata["actions"][0]["ranking_factors"])
        self.assertTrue(metadata["actions"][0]["why_selected"])
        self.assertEqual(len(metadata["personal_learning_loop"]["read_items"]), 5)
        self.assertEqual(len(metadata["personal_learning_loop"]["try_items"]), 2)
        self.assertTrue(metadata["personal_learning_loop"]["read_items"][0]["ranking_factors"])
        self.assertTrue(metadata["personal_learning_loop"]["read_items"][0]["why_selected"])
        self.assertTrue(metadata["personal_learning_loop"]["try_items"][0]["ranking_factors"])
        self.assertTrue(metadata["personal_learning_loop"]["try_items"][0]["why_selected"])
        self.assertIn("reflection_question", metadata["personal_learning_loop"])
        self.assertIn("AI Intelligence Report 2026-W28 is ready", summary.notification_text)

    def test_historical_context_excludes_future_atom_and_rebuilds_thread_as_of_period_end(self):
        db_path = self._make_db()
        settings = self._settings(db_path)
        try:
            with sqlite3.connect(db_path) as connection:
                record_knowledge_atom(
                    connection,
                    week_label="2026-W28",
                    atom_type="engineering_practice",
                    claim="Historical eval gates protect agent releases.",
                    summary="The completed-week state.",
                    evidence_quote="historical eval gate",
                    source_post_ids=[901],
                    source_urls=["https://t.me/ai_lab/901"],
                    entities=["shared eval gates"],
                    practices=["bounded releases"],
                    first_seen_at="2026-07-06T00:00:00Z",
                    last_seen_at="2026-07-12T23:59:59Z",
                )
                record_knowledge_atom(
                    connection,
                    week_label="2026-W29",
                    atom_type="risk_warning",
                    claim="Future claim must not leak into W28.",
                    summary="State learned after the historical boundary.",
                    evidence_quote="future state",
                    source_post_ids=[902],
                    source_urls=["https://t.me/ai_lab/902"],
                    entities=["shared eval gates"],
                    practices=["bounded releases"],
                    first_seen_at="2026-07-13T00:00:00Z",
                    last_seen_at="2026-07-13T00:00:00Z",
                )
            refresh_idea_threads(
                settings,
                weeks=12,
                now=datetime(2026, 7, 15, tzinfo=timezone.utc),
            )
            period = resolve_reporting_period(
                datetime(2026, 7, 20, 8, tzinfo=timezone.utc),
                week_label="2026-W28",
            )
            with sqlite3.connect(db_path) as connection:
                context = load_ai_intelligence_context(
                    connection,
                    week_label=period.week_label,
                    reporting_period=period,
                    threads_limit=8,
                    atoms_limit=8,
                )
        finally:
            os.unlink(db_path)

        self.assertEqual(len(context["threads"]), 1)
        thread = context["threads"][0]
        self.assertEqual([atom["claim"] for atom in thread["atoms"]], ["Historical eval gates protect agent releases."])
        self.assertEqual(thread["current_claims"], ["Historical eval gates protect agent releases."])
        self.assertEqual(thread["last_seen_at"], "2026-07-12T23:59:59Z")
        self.assertTrue(thread["changed_this_week"])
        self.assertNotIn("Future claim", json.dumps(context, ensure_ascii=False))

    def test_as_of_thread_projection_uses_all_eligible_atoms_before_display_limit(self):
        db_path = self._make_db()
        settings = self._settings(db_path)
        try:
            with sqlite3.connect(db_path) as connection:
                for index in range(10):
                    channel = "bounded_a" if index % 2 == 0 else "bounded_b"
                    record_knowledge_atom(
                        connection,
                        week_label="2026-W28",
                        atom_type="engineering_practice",
                        claim=f"Bounded aggregation evidence {index}.",
                        summary=f"Eligible historical evidence {index}.",
                        evidence_quote=f"bounded evidence {index}",
                        source_post_ids=[1000 + index],
                        source_urls=[f"https://t.me/{channel}/{1000 + index}"],
                        entities=["bounded aggregation"],
                        practical_utility_score=0.9,
                        first_seen_at=f"2026-07-{6 + index // 3:02d}T00:00:00Z",
                        last_seen_at=f"2026-07-{6 + index // 3:02d}T00:00:00Z",
                    )
            refresh_idea_threads(
                settings,
                weeks=12,
                now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
            )
            period = resolve_reporting_period(
                datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
            )
            with sqlite3.connect(db_path) as connection:
                context = load_ai_intelligence_context(
                    connection,
                    week_label=period.week_label,
                    reporting_period=period,
                    threads_limit=8,
                    atoms_limit=2,
                )
        finally:
            os.unlink(db_path)

        self.assertEqual(len(context["threads"]), 1)
        thread = context["threads"][0]
        self.assertEqual(thread["atom_count"], 10)
        self.assertEqual(thread["source_channel_count"], 2)
        self.assertEqual(thread["status"], "production_pattern")
        self.assertAlmostEqual(thread["momentum_30d"], 10 / 12)
        self.assertEqual(len(thread["atoms"]), 2)

    def test_display_atom_limit_does_not_truncate_period_delta_history(self):
        db_path = self._make_db()
        settings = self._settings(db_path)
        try:
            with sqlite3.connect(db_path) as connection:
                for index, (claim, observed_at, confidence) in enumerate(
                    (
                        ("Prior bounded-delta state.", "2026-07-05T12:00:00Z", 0.4),
                        ("First completed-week delta.", "2026-07-07T12:00:00Z", 0.8),
                        ("Second completed-week delta.", "2026-07-08T12:00:00Z", 0.9),
                    ),
                    start=1,
                ):
                    record_knowledge_atom(
                        connection,
                        week_label="2026-W28",
                        atom_type="engineering_practice",
                        claim=claim,
                        summary=claim,
                        evidence_quote=f"bounded delta evidence {index}",
                        source_post_ids=[1100 + index],
                        source_urls=[f"https://t.me/bounded_delta/{1100 + index}"],
                        entities=["bounded delta"],
                        confidence=confidence,
                        first_seen_at=observed_at,
                        last_seen_at=observed_at,
                    )
            refresh_idea_threads(
                settings,
                weeks=12,
                now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
            )
            period = resolve_reporting_period(
                datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
            )
            with sqlite3.connect(db_path) as connection:
                context = load_ai_intelligence_context(
                    connection,
                    week_label=period.week_label,
                    reporting_period=period,
                    atoms_limit=2,
                )
            deltas = _thread_deltas(context, context["threads"])
        finally:
            os.unlink(db_path)

        self.assertEqual(len(context["threads"][0]["atoms"]), 2)
        self.assertEqual(len(deltas), 1)
        self.assertEqual(deltas[0]["previous_state"], "Prior bounded-delta state.")
        self.assertEqual(deltas[0]["confidence_change"], "up")
        self.assertEqual(len(deltas[0]["new_evidence_atom_ids"]), 2)

    def test_context_ignores_frontier_analysis_from_a_different_period(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                upsert_frontier_analysis(
                    connection,
                    week_label="2026-W28",
                    generated_at="2026-07-10T00:00:00Z",
                    model="test-model",
                    prompt_version="frontier-analysis-v1",
                    lookback_weeks=12,
                    threads_analyzed=0,
                    atoms_analyzed=0,
                    executive_brief="Partial analysis must not leak.",
                    what_changed=[],
                    trend_narratives=[],
                    study_now=[],
                    actions=[],
                    caveats=[],
                    analysis={
                        "source_context": {
                            "reporting_week": "2026-W28",
                            "week_label": "2026-W28",
                            "period_mode": "partial_iso_week",
                            "analysis_period_start": "2026-07-06T00:00:00Z",
                            "analysis_period_end": "2026-07-10T00:00:00Z",
                        }
                    },
                )
                period = resolve_reporting_period(
                    datetime(2026, 7, 20, 8, tzinfo=timezone.utc),
                    week_label="2026-W28",
                )
                context = load_ai_intelligence_context(
                    connection,
                    week_label=period.week_label,
                    reporting_period=period,
                )
        finally:
            os.unlink(db_path)

        self.assertIsNone(context["frontier_analysis"])

    def test_marked_post_eligibility_uses_source_period_and_run_snapshot(self):
        db_path = self._make_db()
        try:
            self._insert_marked_post(
                db_path,
                post_id=801,
                posted_at="2026-07-12T23:59:59Z",
                recorded_at="2026-07-13T07:00:00Z",
            )
            self._insert_marked_post(
                db_path,
                post_id=802,
                posted_at="2026-07-13T00:00:00Z",
                recorded_at="2026-07-13T07:00:00Z",
            )
            self._insert_marked_post(
                db_path,
                post_id=803,
                posted_at="2026-07-12T10:00:00Z",
                recorded_at="2026-07-13T08:00:00Z",
            )
            self._insert_marked_post(
                db_path,
                post_id=804,
                posted_at="2026-07-12T12:00:00Z",
                recorded_at="2026-07-13T07:02:52Z",
            )
            self._insert_marked_post(
                db_path,
                post_id=805,
                posted_at="2026-07-12T23:59:59.999999Z",
                recorded_at="2026-07-13T07:02:52.987600Z",
            )
            self._insert_marked_post(
                db_path,
                post_id=806,
                posted_at="2026-07-12T12:00:00Z",
                recorded_at="2026-07-13T07:02:52.987655Z",
            )
            period = resolve_reporting_period(
                datetime(2026, 7, 13, 7, 2, 52, 987654, tzinfo=timezone.utc)
            )
            with sqlite3.connect(db_path) as connection:
                context = load_ai_intelligence_context(
                    connection,
                    week_label=period.week_label,
                    reporting_period=period,
                )
        finally:
            os.unlink(db_path)

        self.assertEqual([post["post_id"] for post in context["marked_posts"]], [805, 804, 801])
        self.assertEqual(context["analysis_period_start"], "2026-07-06T00:00:00Z")
        self.assertEqual(context["analysis_period_end"], "2026-07-13T00:00:00Z")
        self.assertEqual(context["reaction_snapshot_at"], "2026-07-13T07:02:52.987654Z")

    def test_explicit_reaction_snapshot_includes_same_run_sync_and_excludes_later_reactions(self):
        db_path = self._make_db()
        try:
            self._insert_marked_post(
                db_path,
                post_id=811,
                posted_at="2026-07-12T18:00:00Z",
                recorded_at="2026-07-13T07:45:00Z",
            )
            self._insert_marked_post(
                db_path,
                post_id=812,
                posted_at="2026-07-12T19:00:00Z",
                recorded_at="2026-07-13T08:00:00.000001Z",
            )
            period = resolve_reporting_period(
                datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
            )
            with sqlite3.connect(db_path) as connection:
                context = load_ai_intelligence_context(
                    connection,
                    week_label=period.week_label,
                    reporting_period=period,
                    reaction_snapshot_at="2026-07-13T08:00:00Z",
                )
        finally:
            os.unlink(db_path)

        self.assertEqual([post["post_id"] for post in context["marked_posts"]], [811])
        self.assertEqual(context["reaction_snapshot_at"], "2026-07-13T08:00:00Z")

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
                            now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
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
                    with patch(
                        "output.ai_intelligence_report.resolve_reporting_period",
                        side_effect=lambda _now=None, **kwargs: resolve_reporting_period(
                            datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
                            **kwargs,
                        ),
                    ):
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
        self.assertTrue(atoms[0]["_ranking_factors"])
        self.assertIn("confirmed feedback promoted", atoms[0]["_why_selected"])

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
        self.assertTrue(actions[0]["ranking_factors"])
        self.assertIn("confirmed feedback promoted", actions[0]["why_selected"])

    def test_reaction_interest_promotes_exactly_one_visible_action_after_filtering(self):
        def thread(slug, position, *, status="active", reacted=False):
            return {
                "id": position + 1,
                "slug": slug,
                "title": slug,
                "status": status,
                "momentum_30d": 0.5,
                "source_channel_count": 2,
                "changed_this_week": False,
                "last_seen_at": "2026-07-12T00:00:00Z",
                "atom_count": 2,
                "current_claims": [slug],
                "atoms": [],
                "_reaction_baseline_position": position,
                **({"_reaction_interest": True} if reacted else {}),
            }

        # The reacted item arrives in raw personalized order ahead of one row,
        # while a filtered hype row also separates it from visible actions.
        # Baseline positions prevent stacking that raw move with the one Brief move.
        threads = [
            thread("one", 0),
            thread("reacted", 3, reacted=True),
            thread("two", 1),
            thread("hidden", 2, status="hype_only"),
        ]

        actions = _learning_actions(threads, {})

        self.assertEqual(
            [action["thread_slug"] for action in actions[:3]],
            ["one", "reacted", "two"],
        )

    def test_reaction_interest_cannot_cross_stronger_close_order_tiebreaks(self):
        base = {
            "status": "active",
            "momentum_30d": 0.5,
            "source_channel_count": 2,
            "current_claims": ["claim"],
            "atoms": [],
        }
        stronger_cases = (
            ("changed_this_week", {"changed_this_week": True}),
            ("last_seen_at", {"last_seen_at": "2026-07-12T00:00:01Z"}),
            ("atom_count", {"atom_count": 3}),
        )
        for label, stronger_field in stronger_cases:
            with self.subTest(label=label):
                first = {
                    **base,
                    "id": 1,
                    "slug": "stronger",
                    "title": "Stronger",
                    "changed_this_week": False,
                    "last_seen_at": "2026-07-12T00:00:00Z",
                    "atom_count": 2,
                    "_reaction_baseline_position": 0,
                    **stronger_field,
                }
                reacted = {
                    **base,
                    "id": 2,
                    "slug": "reacted",
                    "title": "Reacted",
                    "changed_this_week": False,
                    "last_seen_at": "2026-07-12T00:00:00Z",
                    "atom_count": 2,
                    "_reaction_baseline_position": 1,
                    "_reaction_interest": True,
                }

                actions = _learning_actions([first, reacted], {})

                self.assertEqual(
                    [action["thread_slug"] for action in actions[:2]],
                    ["stronger", "reacted"],
                )

    def test_adjacent_reacted_items_each_gain_one_step_on_brief_and_atlas(self):
        threads = [
            {
                "id": index,
                "slug": f"thread-{index}",
                "title": f"Thread {index}",
                "status": "active",
                "momentum_30d": 0.5,
                "source_channel_count": 2,
                "changed_this_week": False,
                "last_seen_at": "2026-07-12T00:00:00Z",
                "atom_count": 2,
                "current_claims": [f"claim {index}"],
                "atoms": [],
                "_reaction_baseline_position": index - 1,
                **({"_reaction_interest": True} if index in {2, 3} else {}),
            }
            for index in (1, 2, 3)
        ]

        actions = _learning_actions(threads, {})
        navigation = _reaction_ranked_threads_for_navigation(threads, {}, limit=3)

        self.assertEqual(
            [action["thread_slug"] for action in actions[:3]],
            ["thread-2", "thread-3", "thread-1"],
        )
        self.assertEqual(
            [thread["slug"] for thread in navigation],
            ["thread-2", "thread-3", "thread-1"],
        )


if __name__ == "__main__":
    unittest.main()
