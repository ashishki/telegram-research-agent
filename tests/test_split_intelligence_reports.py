import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from config.settings import Settings
from db.frontier_analysis import upsert_frontier_analysis
from db.knowledge_atoms import record_knowledge_atom
from db.migrate import run_migrations
from output.ai_report_contract import INTELLIGENCE_CONTRACT_VERSION, RADAR_INTELLIGENCE_CONTRACT_VERSION
from output.ai_intelligence_report import load_ai_intelligence_context
from output.idea_threads import refresh_idea_threads
from output.knowledge_atlas_report import (
    _atlas_project_learning_projection,
    _thread_navigation_model,
    build_knowledge_atlas_artifact,
    render_knowledge_atlas_html,
)
from output.reporting_period import resolve_reporting_period
from output.split_intelligence_reports import (
    deliver_split_intelligence_reports,
    generate_split_intelligence_reports,
    generate_split_weekly_brief_v2_preview,
)
from output.weekly_intelligence_brief import (
    build_weekly_intelligence_brief_artifact,
    load_mvp_radar_summary,
    render_weekly_intelligence_brief_html,
)


class TestSplitIntelligenceReports(unittest.TestCase):
    def test_v2_preview_is_explicit_and_does_not_change_default_delivery(self):
        sentinel = object()
        with patch(
            "output.weekly_intelligence_brief_v2.generate_weekly_intelligence_brief_v2_artifact",
            return_value=sentinel,
        ) as generate:
            result = generate_split_weekly_brief_v2_preview(
                manifest_path="/tmp/run/manifest.json",
                editorial_artifact_path="/tmp/editorial.json",
                editorial_input_package={"schema_version": "fixture"},
                project_intelligence_path="/tmp/project.json",
                project_descriptors=(),
                output_root="/tmp/output",
                allowed_source_roots=("/tmp",),
            )

        self.assertIs(result, sentinel)
        generate.assert_called_once()
        self.assertNotIn(
            "weekly_brief_v2",
            generate_split_intelligence_reports.__code__.co_varnames,
        )

    def test_atlas_secondary_learning_projection_is_reaction_neutral(self):
        baseline_threads = [
            {
                "id": index,
                "slug": slug,
                "title": slug,
                "status": "active",
                "momentum_30d": 0.5,
                "source_channel_count": 2,
                "current_claims": [slug],
                "atoms": [],
            }
            for index, slug in enumerate(("one", "two", "reacted"), start=1)
        ]
        personalized_threads = [
            {**baseline_threads[0], "_reaction_baseline_position": 0},
            {
                **baseline_threads[2],
                "_reaction_baseline_position": 2,
                "_reaction_interest": True,
            },
            {**baseline_threads[1], "_reaction_baseline_position": 1},
        ]

        def capture(context, *, actions, **_kwargs):
            return {
                "thread_slugs": [thread["slug"] for thread in context["threads"]],
                "action_slugs": [action.get("thread_slug") for action in actions],
                "has_reaction_markers": any(
                    any(str(key).startswith("_reaction_") for key in thread)
                    for thread in context["threads"]
                ),
            }

        with patch(
            "output.knowledge_atlas_report.build_project_learning_projection",
            side_effect=capture,
        ):
            baseline = _atlas_project_learning_projection(
                {"threads": baseline_threads, "feedback_context": {}}
            )
            personalized = _atlas_project_learning_projection(
                {"threads": personalized_threads, "feedback_context": {}}
            )

        self.assertEqual(personalized, baseline)
        self.assertFalse(personalized["has_reaction_markers"])

    def test_atlas_navigation_uses_the_same_reaction_feedback_tie_context(self):
        threads = [
            {
                "id": 1,
                "slug": "stronger-feedback",
                "title": "Stronger feedback",
                "status": "active",
                "momentum_30d": 0.5,
                "source_channel_count": 2,
                "changed_this_week": False,
                "last_seen_at": "2026-07-12T00:00:00Z",
                "atom_count": 2,
                "atoms": [],
                "_reaction_baseline_position": 0,
            },
            {
                "id": 2,
                "slug": "reacted",
                "title": "Reacted",
                "status": "active",
                "momentum_30d": 0.5,
                "source_channel_count": 2,
                "changed_this_week": False,
                "last_seen_at": "2026-07-12T00:00:00Z",
                "atom_count": 2,
                "atoms": [],
                "_reaction_baseline_position": 1,
                "_reaction_interest": True,
            },
        ]

        navigation = _thread_navigation_model(
            {
                "threads": threads,
                "feedback_context": {
                    "promoted_target_refs": ["topic:stronger-feedback"],
                },
                "reaction_ranking_context": {
                    "promoted_target_refs": ["topic:stronger-feedback"],
                },
            }
        )

        self.assertEqual(
            [thread["slug"] for thread in navigation["threads"]],
            ["stronger-feedback", "reacted"],
        )

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

    def _seed(self, db_path: str) -> Settings:
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
                atom_type="market_signal",
                claim="AI rollout teams ask for measurable adoption evidence before expanding usage.",
                summary="The source describes adoption metrics for working teams.",
                evidence_quote="measurable adoption evidence",
                source_post_ids=[202],
                source_urls=["https://t.me/rollout/202"],
                entities=["AI adoption", "training"],
                tools=["RAG"],
                models=["Claude"],
                practices=["adoption metrics", "manager approval"],
                confidence=0.8,
                novelty_score=0.68,
                practical_utility_score=0.9,
                why_it_matters="This is tied to AI rollout project workflows.",
                first_seen_at="2026-07-07T09:00:00Z",
                last_seen_at="2026-07-07T09:00:00Z",
            )
            upsert_frontier_analysis(
                connection,
                week_label="2026-W28",
                generated_at="2026-07-08T00:00:00Z",
                model="claude-opus-4-8",
                prompt_version="frontier-analysis-v1",
                lookback_weeks=12,
                threads_analyzed=2,
                atoms_analyzed=2,
                executive_brief="Eval-gated agent workflows and adoption metrics are the operational theme.",
                what_changed=[
                    {
                        "title": "Agent release discipline hardened",
                        "summary": "Eval gates moved from nice-to-have to release path.",
                    }
                ],
                trend_narratives=[],
                study_now=[],
                actions=[
                    {
                        "title": "Try one eval guard",
                        "next_step": "Add one regression guard before agent-written edits merge.",
                    }
                ],
                caveats=[],
                analysis={"source_atom_ids": [1, 2]},
            )
        refresh_idea_threads(
            settings,
            weeks=12,
            now=datetime(2026, 7, 8, tzinfo=timezone.utc),
        )
        return settings

    def test_default_split_path_does_not_invoke_editorial_shadow(self):
        db_path = self._make_db()
        settings = self._seed(db_path)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                with patch(
                    "output.editorial_intelligence.generate_editorial_intelligence_artifact"
                ) as generate_editorial, patch(
                    "output.weekly_intelligence_brief_v2.generate_weekly_intelligence_brief_v2_artifact"
                ) as generate_v2:
                    summary = generate_split_intelligence_reports(
                        settings,
                        week_label="2026-W28",
                        output_root=Path(tmpdir),
                        now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
                    )

            generate_editorial.assert_not_called()
            generate_v2.assert_not_called()
            self.assertIsNone(summary.editorial_intelligence)
            self.assertEqual(summary.editorial_intelligence_error, "")
            self.assertEqual(len(summary.reader_quality_reports), 2)
            self.assertTrue(
                all(
                    report["policy_mode"] == "warn_only_v1"
                    and report["summary"]["delivery_decision"]
                    == "allow_with_warnings"
                    for report in summary.reader_quality_reports
                )
            )
            self.assertIn("Доставка V1 не заблокирована", summary.notification_text)
            self.assertIn("недельный бриф", summary.notification_text)
            self.assertIn("карта знаний", summary.notification_text)
            quality_warning = summary.notification_text.rsplit("\n", 1)[-1]
            self.assertNotIn("weekly_brief", quality_warning)
            self.assertNotIn("knowledge_atlas", quality_warning)
        finally:
            os.unlink(db_path)

    def test_opt_in_editorial_shadow_is_persisted_but_never_enters_v1_renderers(self):
        db_path = self._make_db()
        settings = self._seed(db_path)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                shadow_root = root / "editorial-shadow"
                mvp_path = root / "mvp-weekly-2026-W28.json"
                mvp_path.write_text(
                    json.dumps(
                        {
                            "result": {
                                "selected_title": "Week Named Candidate",
                                "dossier_status": "investigate",
                                "recommendation": "revisit_with_evidence_gap",
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                run_identity = {
                    "run_id": "tra-weekly-shadow-valid",
                    "run_status": "complete",
                    "partial": False,
                    "pipeline_profile": "irx2_orchestration.v1",
                }
                summary = generate_split_intelligence_reports(
                    settings,
                    week_label="2026-W28",
                    output_root=root / "v1",
                    mvp_radar_json_path=mvp_path,
                    now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
                    run_identity=run_identity,
                    editorial_output_root=shadow_root,
                    editorial_generated_at="2026-07-13T07:03:00Z",
                )
                editorial = summary.editorial_intelligence
                self.assertIsNotNone(editorial)
                assert editorial is not None
                editorial_path = Path(editorial.path)
                editorial_payload = json.loads(editorial_path.read_text(encoding="utf-8"))
                brief_json_text = Path(summary.weekly_brief.json_path).read_text(encoding="utf-8")
                atlas_json_text = Path(summary.knowledge_atlas.json_path).read_text(encoding="utf-8")
                brief_html = Path(summary.weekly_brief.html_path).read_text(encoding="utf-8")
                atlas_html = Path(summary.knowledge_atlas.html_path).read_text(encoding="utf-8")

                self.assertTrue(editorial_path.is_file())
                self.assertEqual(editorial.generation_status, "partial")
                self.assertTrue(editorial.partial)
                self.assertEqual(editorial_payload["generation_status"], "partial")
                self.assertEqual(
                    editorial_payload["fallback_reason"],
                    "deterministic_input_partial",
                )
                self.assertNotIn(
                    "feedback_snapshot_cutoff_unbound",
                    editorial_payload["generation_receipt"]["validation_errors"],
                )
                self.assertNotIn(
                    "feedback_snapshot_cutoff_mismatch",
                    editorial_payload["generation_receipt"]["validation_errors"],
                )
                self.assertEqual(summary.editorial_intelligence_error, "")
                self.assertEqual(
                    editorial_payload["mvp_summary"]["reader_decision"],
                    "unavailable",
                )
                self.assertEqual(editorial_payload["mvp_summary"]["radar_ref"], "")
                for reader_text in (
                    brief_json_text,
                    atlas_json_text,
                    brief_html,
                    atlas_html,
                ):
                    self.assertNotIn("Частичный редакционный выпуск", reader_text)
                    self.assertNotIn(str(editorial_path), reader_text)
                    self.assertNotIn("editorial-intelligence.v1.json", reader_text)

                brief_sidecar = json.loads(brief_json_text)
                self.assertEqual(
                    brief_sidecar["mvp_radar"]["selected_candidate"],
                    "Week Named Candidate",
                )

                with patch.dict(
                    os.environ,
                    {"TELEGRAM_OWNER_CHAT_ID": "12345", "TELEGRAM_BOT_TOKEN": "token"},
                    clear=False,
                ):
                    with (
                        patch("bot.telegram_delivery.send_text", return_value=10),
                        patch(
                            "bot.telegram_delivery.send_document",
                            side_effect=[11, 12],
                        ),
                    ):
                        delivered = deliver_split_intelligence_reports(summary)
                self.assertIs(delivered.editorial_intelligence, editorial)
        finally:
            os.unlink(db_path)

    def test_editorial_input_mismatch_does_not_block_v1_split(self):
        db_path = self._make_db()
        settings = self._seed(db_path)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                summary = generate_split_intelligence_reports(
                    settings,
                    week_label="2026-W28",
                    output_root=root / "v1",
                    now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
                    run_identity={
                        "run_id": "tra-weekly-shadow-input-mismatch",
                        "analysis_period_end": "2026-07-01T00:00:00Z",
                    },
                    editorial_output_root=root / "shadow",
                    editorial_generated_at="2026-07-13T07:03:00Z",
                )

                self.assertIsNone(summary.editorial_intelligence)
                self.assertEqual(
                    summary.editorial_intelligence_error,
                    "EditorialInputError",
                )
                self.assertTrue(Path(summary.weekly_brief.html_path).is_file())
                self.assertTrue(Path(summary.knowledge_atlas.html_path).is_file())
        finally:
            os.unlink(db_path)

    def test_editorial_identity_failure_does_not_block_v1_split(self):
        db_path = self._make_db()
        settings = self._seed(db_path)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                summary = generate_split_intelligence_reports(
                    settings,
                    week_label="2026-W28",
                    output_root=Path(tmpdir) / "v1",
                    now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
                    editorial_output_root=Path(tmpdir) / "shadow",
                    run_identity={},
                )

                self.assertIsNone(summary.editorial_intelligence)
                self.assertEqual(
                    summary.editorial_intelligence_error,
                    "EditorialInputError",
                )
                self.assertTrue(Path(summary.weekly_brief.html_path).is_file())
                self.assertTrue(Path(summary.knowledge_atlas.html_path).is_file())
        finally:
            os.unlink(db_path)

    def test_editorial_persistence_failure_does_not_block_v1_split(self):
        db_path = self._make_db()
        settings = self._seed(db_path)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                shadow_root = root / "shadow-is-a-file"
                shadow_root.write_text("occupied", encoding="utf-8")
                summary = generate_split_intelligence_reports(
                    settings,
                    week_label="2026-W28",
                    output_root=root / "v1",
                    now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
                    editorial_output_root=shadow_root,
                    run_identity={"run_id": "tra-weekly-shadow-persistence-fail"},
                    editorial_generated_at="2026-07-13T07:03:00Z",
                )

                self.assertIsNone(summary.editorial_intelligence)
                self.assertEqual(
                    summary.editorial_intelligence_error,
                    "NotADirectoryError",
                )
                self.assertTrue(Path(summary.weekly_brief.html_path).is_file())
                self.assertTrue(Path(summary.knowledge_atlas.html_path).is_file())
        finally:
            os.unlink(db_path)

    def test_unexpected_editorial_runtime_failure_does_not_block_v1_split(self):
        db_path = self._make_db()
        settings = self._seed(db_path)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                with patch(
                    "output.editorial_intelligence.generate_editorial_intelligence_artifact",
                    side_effect=RuntimeError("unexpected shadow failure"),
                ):
                    summary = generate_split_intelligence_reports(
                        settings,
                        week_label="2026-W28",
                        output_root=root / "v1",
                        now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
                        editorial_output_root=root / "shadow",
                        run_identity={"run_id": "tra-weekly-shadow-runtime-fail"},
                    )

                self.assertIsNone(summary.editorial_intelligence)
                self.assertEqual(summary.editorial_intelligence_error, "RuntimeError")
                self.assertTrue(Path(summary.weekly_brief.html_path).is_file())
                self.assertTrue(Path(summary.weekly_brief.json_path).is_file())
                self.assertTrue(Path(summary.knowledge_atlas.html_path).is_file())
                self.assertTrue(Path(summary.knowledge_atlas.json_path).is_file())
        finally:
            os.unlink(db_path)

    def test_generates_distinct_atlas_and_brief_surfaces_from_shared_context(self):
        db_path = self._make_db()
        settings = self._seed(db_path)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            mvp_path = root / "mvp-weekly-2026-W28.json"
            mvp_path.write_text(
                json.dumps(
                    {
                        "result": {
                            "selected_title": "Agent Eval Gate Scanner",
                            "dossier_status": "investigate",
                            "recommendation": "revisit_with_evidence_gap",
                            "score": 61,
                        },
                        "selected": {
                            "missing_evidence": ["Need external demand."],
                            "next_validation": ["Interview five operators."],
                        },
                        "validation_queries": {
                            "schema_version": "radar_validation_evidence.v1",
                            "next_query": {
                                "query": '"agent eval gate scanner" problem',
                                "intent": "search_demand",
                            },
                            "queries_by_intent": {
                                "search_demand": [
                                    {
                                        "query": '"agent eval gate scanner" problem',
                                        "intent": "search_demand",
                                        "source_types": ["serp"],
                                    }
                                ],
                                "manual_workarounds": [
                                    {
                                        "query": '"agent eval gate scanner" workaround',
                                        "intent": "manual_workarounds",
                                        "source_types": ["serp", "reddit"],
                                    }
                                ],
                            },
                        },
                        "matched_external_evidence": [],
                        "missing_evidence_by_category": {
                            "external_corroboration": {
                                "evidence_kind": "search_demand",
                                "missing_evidence": ["Need external demand."],
                                "next_intent": "search_demand",
                                "next_query": '"agent eval gate scanner" problem',
                            }
                        },
                        "validation_adapter_status": {
                            "search_demand": {"status": "cache_only"},
                            "reddit_forum_complaints": {"status": "credential_limited"},
                        },
                        "decision_change_action": {
                            "current_gate": "investigate",
                            "matched_external_evidence_count": 0,
                            "matched_external_source_types": [],
                            "next_query": '"agent eval gate scanner" problem',
                            "next_intent": "search_demand",
                            "next_validation_action": (
                                'Run `"agent eval gate scanner" problem` and attach only candidate-matched evidence.'
                            ),
                            "required_gate_change": "two independent matched external source types",
                            "context_only_results_rule": "unmatched external research remains context only",
                        },
                        "decision_context": {
                            "market_context": {
                                "status": "context_only",
                                "record_count": 2,
                                "source_gate_satisfied": False,
                            },
                            "external_research_context": {
                                "status": "context_only",
                                "record_count": 1,
                                "source_gate_satisfied": False,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            summary = generate_split_intelligence_reports(
                settings,
                threads_limit=8,
                atoms_limit=4,
                output_root=root,
                mvp_radar_json_path=mvp_path,
                now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
            )

            atlas_html = Path(summary.knowledge_atlas.html_path).read_text(encoding="utf-8")
            brief_html = Path(summary.weekly_brief.html_path).read_text(encoding="utf-8")
            atlas_json = json.loads(Path(summary.knowledge_atlas.json_path).read_text(encoding="utf-8"))
            brief_json = json.loads(Path(summary.weekly_brief.json_path).read_text(encoding="utf-8"))

            self.assertTrue(summary.knowledge_atlas.html_path.endswith(".knowledge-atlas.html"))
            self.assertTrue(summary.weekly_brief.html_path.endswith(".weekly-brief.html"))
            self.assertIn("<title>Knowledge Atlas 6-12 июля 2026</title>", atlas_html)
            self.assertIn("<title>Weekly Intelligence Brief 6-12 июля 2026</title>", brief_html)
            self.assertIn("Generated 2026-07-13T07:02:52Z", atlas_html)
            self.assertIn("Generated 2026-07-13T07:02:52Z", brief_html)
            self.assertIn(f'content="{INTELLIGENCE_CONTRACT_VERSION}"', atlas_html)
            self.assertIn(f'content="{INTELLIGENCE_CONTRACT_VERSION}"', brief_html)
            self.assertIn(f'content="{RADAR_INTELLIGENCE_CONTRACT_VERSION}"', brief_html)
            self.assertIn('id="trend-board"', atlas_html)
            self.assertIn('id="thread-navigation"', atlas_html)
            self.assertIn("Thread Navigation", atlas_html)
            self.assertIn("Thread Timeline", atlas_html)
            self.assertIn("Evidence Pane", atlas_html)
            self.assertIn("Momentum Vs Evidence", atlas_html)
            self.assertIn("Source Diversity", atlas_html)
            self.assertIn("Project Connections", atlas_html)
            self.assertIn('id="project-learning"', atlas_html)
            self.assertIn("Project And Learning Intelligence", atlas_html)
            self.assertIn("Learning Stages", atlas_html)
            self.assertIn("Passive reading is not mastery", atlas_html)
            self.assertIn("Open Questions", atlas_html)
            self.assertIn("Original Source Links", atlas_html)
            self.assertIn('id="brief-actions"', brief_html)
            self.assertIn('id="brief-project-learning"', brief_html)
            self.assertIn("External Signals", brief_html)
            self.assertIn("Rejected Overlaps", brief_html)
            self.assertIn("Stale Decisions", brief_html)
            self.assertIn("Repeated Themes Without Action", brief_html)
            self.assertIn("Why selected:", brief_html)
            self.assertLess(brief_html.find('id="brief-actions"'), brief_html.find('id="brief-mvp-radar"'))
            self.assertEqual(atlas_json["artifact_type"], "knowledge_atlas")
            self.assertEqual(brief_json["artifact_type"], "weekly_intelligence_brief")
            self.assertEqual(atlas_json["contract_version"], INTELLIGENCE_CONTRACT_VERSION)
            self.assertEqual(brief_json["contract_version"], INTELLIGENCE_CONTRACT_VERSION)
            self.assertEqual(brief_json["radar_contract_version"], RADAR_INTELLIGENCE_CONTRACT_VERSION)
            period_fields = {
                "run_date",
                "generated_at",
                "reporting_week",
                "week_label",
                "period_mode",
                "analysis_period_start",
                "analysis_period_end",
            }
            self.assertEqual(
                {key: atlas_json[key] for key in period_fields},
                {key: brief_json[key] for key in period_fields},
            )
            self.assertEqual(brief_json["reporting_week"], "2026-W28")
            self.assertEqual(brief_json["period_mode"], "completed_iso_week")
            self.assertEqual(brief_json["analysis_period_start"], "2026-07-06T00:00:00Z")
            self.assertEqual(brief_json["analysis_period_end"], "2026-07-13T00:00:00Z")
            self.assertEqual(summary.reporting_week, "2026-W28")
            self.assertEqual(summary.period_mode, "completed_iso_week")
            self.assertIn("thread_navigation", atlas_json)
            self.assertEqual(
                atlas_json["thread_navigation"]["schema_version"],
                "knowledge_atlas_thread_navigation.v1",
            )
            self.assertTrue(atlas_json["thread_navigation"]["threads"])
            first_thread = atlas_json["thread_navigation"]["threads"][0]
            self.assertTrue(first_thread["evidence_items"])
            self.assertIn("current_understanding", first_thread)
            self.assertIn("change_since_previous_period", first_thread)
            self.assertTrue(first_thread["timeline"])
            self.assertIn("source_diversity", first_thread)
            self.assertIn("project_connections", first_thread)
            self.assertIn("decisions", first_thread)
            self.assertIn("open_questions", first_thread)
            self.assertIn("study_next", first_thread)
            self.assertTrue(brief_json["actions"][0]["ranking_factors"])
            self.assertTrue(brief_json["actions"][0]["why_selected"])
            self.assertTrue(brief_json["personal_learning_loop"]["read_items"][0]["ranking_factors"])
            self.assertTrue(brief_json["personal_learning_loop"]["read_items"][0]["why_selected"])
            self.assertIn("project_learning_projection", atlas_json)
            self.assertIn("project_learning_projection", brief_json)
            self.assertEqual(
                set(brief_json["project_learning_projection"]["learning_intelligence"]["allowed_stages"]),
                {
                    "read",
                    "understood",
                    "explained",
                    "reproduced",
                    "implemented",
                    "tested",
                    "project-applied",
                    "measured",
                    "stale",
                    "prerequisite_gap",
                },
            )
            self.assertEqual(
                brief_json["project_learning_projection"]["source_policy"]["no_feedback_semantics"],
                "unknown",
            )
            self.assertEqual(
                atlas_json["project_learning_projection"]["source_policy"]["market_business_context"],
                "context_only",
            )
            self.assertIn("decision_cockpit", brief_json)
            self.assertEqual(brief_json["decision_cockpit"]["mvp_radar_gate"]["decision"], "do_not_build")
            self.assertEqual(brief_json["mvp_radar_gate"]["matched_gate_evidence_count"], 0)
            self.assertFalse(brief_json["mvp_radar_gate"]["context_only_can_satisfy_gate"])
            self.assertTrue(brief_json["decision_cockpit"]["exact_feedback_targets"])
            self.assertEqual(
                atlas_json["intelligence_contract"]["contract_version"],
                INTELLIGENCE_CONTRACT_VERSION,
            )
            self.assertEqual(
                brief_json["intelligence_contract"]["contract_version"],
                INTELLIGENCE_CONTRACT_VERSION,
            )
            self.assertEqual(
                brief_json["intelligence_contract"]["radar_exchange"]["contract_version"],
                RADAR_INTELLIGENCE_CONTRACT_VERSION,
            )
            self.assertTrue(brief_json["intelligence_contract"]["source_observations"])
            self.assertTrue(brief_json["intelligence_contract"]["evidence_items"])
            self.assertTrue(brief_json["intelligence_contract"]["claims"])
            self.assertFalse(
                brief_json["intelligence_contract"]["radar_exchange"]["context_only_can_satisfy_gate"]
            )
            self.assertEqual(
                atlas_json["related_artifacts"]["weekly_brief_json_path"],
                summary.weekly_brief.json_path,
            )
            self.assertEqual(
                brief_json["related_artifacts"]["knowledge_atlas_json_path"],
                summary.knowledge_atlas.json_path,
            )
            self.assertEqual(brief_json["mvp_radar"]["selected_candidate"], "Agent Eval Gate Scanner")
            self.assertEqual(brief_json["mvp_radar_reader"], brief_json["mvp_radar"])
            self.assertEqual(
                brief_json["mvp_radar"]["reader_state"],
                "unbound_legacy",
            )
            self.assertEqual(
                brief_json["mvp_radar"]["reader_decision"],
                "unavailable",
            )
            self.assertTrue(brief_json["mvp_radar"]["partial"])
            self.assertEqual(brief_json["mvp_radar"]["matched_external_proof"], [])
            self.assertEqual(brief_json["mvp_radar"]["unmatched_context"], [])
            self.assertFalse(
                brief_json["mvp_radar"]["evidence_policy"][
                    "unbound_legacy_can_authorize"
                ]
            )
            self.assertIn("Top Personal Changes", brief_html)
            self.assertIn("Evidence / Trust", brief_html)
            self.assertIn("What To Do", brief_html)
            self.assertIn("Ignore / Defer", brief_html)
            self.assertIn("Project Impact", brief_html)
            self.assertIn("Exact Feedback Targets", brief_html)
            self.assertIn("Сборка не разрешена.", brief_html)
            self.assertIn("MVP Radar Gate Card", brief_html)
            self.assertIn("Validation Query Pack", brief_html)
            self.assertIn("Matched Evidence By Source/Kind", brief_html)
            self.assertIn("Missing Evidence Checklist", brief_html)
            self.assertIn("What Would Change The Decision", brief_html)
            self.assertIn("No matched external validation evidence found", brief_html)
            self.assertIn("Market context: context only, not proof.", brief_html)
            self.assertIn("agent eval gate scanner", brief_html)
            self.assertEqual(
                brief_json["mvp_radar"]["decision_change_action"]["next_query"],
                '"agent eval gate scanner" problem',
            )

            with patch.dict(
                os.environ,
                {"TELEGRAM_OWNER_CHAT_ID": "12345", "TELEGRAM_BOT_TOKEN": "token"},
                clear=False,
            ):
                with patch("bot.telegram_delivery.send_text", return_value=10) as send_text:
                    with patch("bot.telegram_delivery.send_document", side_effect=[11, 12]) as send_document:
                        delivered = deliver_split_intelligence_reports(summary)

            self.assertEqual(delivered.delivered_message_ids, (10, 11, 12))
            self.assertIs(delivered.weekly_brief, summary.weekly_brief)
            self.assertIs(delivered.knowledge_atlas, summary.knowledge_atlas)
            self.assertEqual(
                delivered.reader_quality_reports,
                summary.reader_quality_reports,
            )
            send_text.assert_called_once_with(
                chat_id="12345",
                text=summary.notification_text,
                token="token",
                parse_mode=None,
            )
            self.assertEqual(send_document.call_count, 2)
            self.assertEqual(send_document.call_args_list[0].kwargs["file_path"], str(summary.weekly_brief.html_path))
            self.assertEqual(send_document.call_args_list[1].kwargs["file_path"], str(summary.knowledge_atlas.html_path))

    def test_missing_mvp_radar_does_not_break_brief_or_atlas(self):
        db_path = self._make_db()
        settings = self._seed(db_path)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary = generate_split_intelligence_reports(
                settings,
                week_label="2026-W28",
                threads_limit=8,
                atoms_limit=4,
                output_root=root,
                mvp_radar_json_path=root / "missing-mvp-weekly-2026-W28.json",
                now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
            )

            brief_html = Path(summary.weekly_brief.html_path).read_text(encoding="utf-8")
            brief_json = json.loads(Path(summary.weekly_brief.json_path).read_text(encoding="utf-8"))
            atlas_exists = Path(summary.knowledge_atlas.html_path).exists()

        self.assertTrue(atlas_exists)
        self.assertEqual(brief_json["mvp_radar"]["status"], "not_available")
        self.assertEqual(brief_json["mvp_radar_gate"]["radar_artifact_status"], "missing")
        self.assertEqual(brief_json["mvp_radar_gate"]["decision"], "do_not_build")
        self.assertEqual(brief_json["mvp_radar"]["reader_state"], "missing")
        self.assertEqual(
            brief_json["mvp_radar"]["candidate_state"],
            "unknown_due_to_unavailable_radar",
        )
        self.assertEqual(brief_json["mvp_radar"]["reader_decision"], "unavailable")
        self.assertTrue(brief_json["mvp_radar"]["partial"])
        self.assertIsNone(brief_json["mvp_radar"]["candidate"])
        self.assertNotEqual(brief_json["mvp_radar"]["candidate_state"], "no_candidate")
        self.assertIn(
            "MVP Radar JSON для запрошенного периода недоступен",
            brief_html,
        )
        self.assertIn("MVP Radar недоступен для этого запуска", brief_html)
        self.assertNotIn("run_id", brief_json)
        self.assertTrue(summary.weekly_brief.html_path.endswith("2026-W28.weekly-brief.html"))
        self.assertTrue(summary.knowledge_atlas.html_path.endswith("2026-W28.knowledge-atlas.html"))

    def test_orchestrated_sidecars_share_identity_snapshot_partial_banner_and_unbound_radar(self):
        db_path = self._make_db()
        settings = self._seed(db_path)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            radar_path = root / "radar-disabled.json"
            radar_path.write_text(
                json.dumps({"status": "disabled", "recommendation": "needs_more_evidence"}),
                encoding="utf-8",
            )
            period = resolve_reporting_period(
                datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
            )
            run_identity = {
                "run_id": "tra-weekly-2026-W28-20260713T070252Z",
                "manifest_path": str(root / "weekly-run-manifest.json"),
                "run_status": "partial",
                "partial": True,
                "pipeline_profile": "irx2_orchestration.v1",
                "failed_stages": ["reaction_sync", "radar"],
                "warnings": ["Reaction snapshot is incomplete."],
            }
            summary = generate_split_intelligence_reports(
                settings,
                reporting_period=period,
                reaction_snapshot_at="2026-07-13T08:04:10Z",
                run_identity=run_identity,
                threads_limit=8,
                atoms_limit=4,
                output_root=root,
                mvp_radar_json_path=radar_path,
            )
            atlas_html = Path(summary.knowledge_atlas.html_path).read_text(encoding="utf-8")
            brief_html = Path(summary.weekly_brief.html_path).read_text(encoding="utf-8")
            atlas_json = json.loads(Path(summary.knowledge_atlas.json_path).read_text(encoding="utf-8"))
            brief_json = json.loads(Path(summary.weekly_brief.json_path).read_text(encoding="utf-8"))
            leftovers = list(root.rglob("*.tmp"))

        identity_fields = {
            "run_id",
            "manifest_path",
            "run_status",
            "partial",
            "pipeline_profile",
            "failed_stages",
            "warnings",
        }
        self.assertEqual(
            {key: brief_json[key] for key in identity_fields},
            run_identity,
        )
        self.assertEqual(
            {key: atlas_json[key] for key in identity_fields},
            run_identity,
        )
        self.assertEqual(brief_json["schema_version"], "split_ai_report.v1")
        self.assertEqual(atlas_json["schema_version"], "split_ai_report.v1")
        self.assertEqual(brief_json["reaction_snapshot_at"], "2026-07-13T08:04:10Z")
        self.assertEqual(atlas_json["reaction_snapshot_at"], "2026-07-13T08:04:10Z")
        self.assertEqual(summary.run_id, run_identity["run_id"])
        self.assertTrue(summary.partial)
        self.assertIn('data-run-status="partial"', brief_html)
        self.assertIn('data-run-status="partial"', atlas_html)
        self.assertIn("Частичный выпуск.", brief_html)
        self.assertIn("Частичный выпуск.", atlas_html)
        self.assertIn("синхронизация реакций", brief_html)
        self.assertIn("синхронизация реакций", atlas_html)
        self.assertIn("MVP Radar", brief_html)
        self.assertIn("MVP Radar", atlas_html)
        self.assertIn(
            f'<meta name="weekly-run-id" content="{run_identity["run_id"]}">',
            brief_html,
        )
        self.assertIn(
            f'<meta name="weekly-run-id" content="{run_identity["run_id"]}">',
            atlas_html,
        )
        self.assertIn(
            "Несвязанный legacy-артефакт не даёт права на эксперимент или сборку.",
            brief_html,
        )
        self.assertEqual(
            brief_json["mvp_radar_gate"]["radar_artifact_status"],
            "unbound_legacy",
        )
        self.assertEqual(
            brief_json["mvp_radar_gate"]["warning"],
            "Несвязанный legacy-артефакт не даёт права на эксперимент или сборку.",
        )
        self.assertEqual(brief_json["mvp_radar"]["reader_state"], "unbound_legacy")
        self.assertEqual(brief_json["mvp_radar"]["reader_decision"], "unavailable")
        self.assertTrue(brief_json["mvp_radar"]["partial"])
        self.assertEqual(leftovers, [])

    def test_wrong_week_legacy_radar_is_explicitly_invalid_without_a_fictional_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            radar_path = Path(tmpdir) / "mvp-weekly-2026-W27.json"
            radar_path.write_text(
                json.dumps(
                    {
                        "reporting_week": "2026-W27",
                        "result": {
                            "status": "selected",
                            "selected_title": "Stale Candidate",
                            "dossier_status": "build",
                            "recommendation": "build",
                        },
                    }
                ),
                encoding="utf-8",
            )

            projection = load_mvp_radar_summary("2026-W28", radar_path)

        self.assertEqual(projection["reader_state"], "invalid")
        self.assertEqual(
            projection["candidate_state"],
            "unknown_due_to_unavailable_radar",
        )
        self.assertEqual(projection["reader_decision"], "unavailable")
        self.assertEqual(projection["status"], "not_available")
        self.assertTrue(projection["partial"])
        self.assertIsNone(projection["candidate"])
        self.assertIsNone(projection["selected_candidate"])
        self.assertEqual(projection["matched_external_proof"], [])
        self.assertIn("2026-W27", projection["partial_reasons"][0])
        self.assertIn("2026-W28", projection["partial_reasons"][0])

    def test_resolved_period_rejects_conflicting_legacy_arguments(self):
        period = resolve_reporting_period(
            datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
        )
        with self.assertRaisesRegex(ValueError, "week_label conflicts"):
            generate_split_intelligence_reports(
                self._settings("/tmp/not-opened.db"),
                reporting_period=period,
                week_label="2026-W27",
            )

    def test_reader_headers_show_complete_partial_and_failed_run_statuses(self):
        base_context = {
            "week_label": "2026-W28",
            "reporting_week": "2026-W28",
            "period_mode": "explicit_iso_week",
            "analysis_period_start": "2026-07-06T00:00:00Z",
            "analysis_period_end": "2026-07-13T00:00:00Z",
            "threads": [],
            "source_channels": [],
            "feedback_context": {},
        }
        for status in ("complete", "partial", "failed"):
            with self.subTest(status=status):
                context = {
                    **base_context,
                    "run_status": status,
                    "partial": status == "partial",
                }
                brief_html, _actions = render_weekly_intelligence_brief_html(
                    context,
                    generated_at="2026-07-13T07:02:52Z",
                )
                atlas_html = render_knowledge_atlas_html(
                    context,
                    generated_at="2026-07-13T07:02:52Z",
                )
                self.assertIn(f'data-run-status="{status}"', brief_html)
                self.assertIn(f'data-run-status="{status}"', atlas_html)

    def test_weekly_brief_sidecar_preserves_bounded_marked_posts_snapshot(self):
        db_path = self._make_db()
        self._seed(db_path)
        marked_posts = [
            {
                "post_id": 901,
                "channel_username": "ai_lab",
                "posted_at": "2026-07-12T23:59:59Z",
                "feedback": "operator_marked_interesting",
            }
        ]
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                period = resolve_reporting_period(
                    datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
                )
                with sqlite3.connect(db_path) as connection:
                    connection.row_factory = sqlite3.Row
                    context = load_ai_intelligence_context(
                        connection,
                        reporting_period=period,
                        week_label=period.week_label,
                    )
                context["marked_posts"] = marked_posts
                summary = build_weekly_intelligence_brief_artifact(
                    context,
                    generated_at=period.to_dict()["generated_at"],
                    output_root=root,
                )
                sidecar = json.loads(Path(summary.json_path).read_text(encoding="utf-8"))
        finally:
            os.unlink(db_path)

        self.assertEqual(sidecar["marked_posts"], marked_posts)

    def test_reaction_receipt_is_additive_reader_safe_and_equal_across_surfaces(self):
        context = {
            "week_label": "2026-W28",
            "reporting_week": "2026-W28",
            "run_date": "2026-07-13",
            "generated_at": "2026-07-13T07:02:52Z",
            "period_mode": "completed_iso_week",
            "analysis_period_start": "2026-07-06T00:00:00Z",
            "analysis_period_end": "2026-07-13T00:00:00Z",
            "threads": [
                {
                    "id": 7,
                    "slug": "evaluation-discipline",
                    "title": "Evaluation discipline",
                    "status": "active",
                    "momentum_30d": 0.5,
                    "source_channel_count": 1,
                    "atom_count": 0,
                    "changed_this_week": False,
                    "current_claims": ["Verify evaluation claims."],
                    "superseded_claims": [],
                    "contradictions": [],
                    "atoms": [],
                }
            ],
            "source_channels": [],
            "feedback_context": {},
            "reaction_effect": {
                "schema_version": "reaction_personalization.v1",
                "run_id": "tra-weekly-2026-W28-secret",
                "surface": "weekly_brief",
                "reporting_week": "2026-W28",
                "analysis_period_start": "2026-07-06T00:00:00Z",
                "analysis_period_end": "2026-07-13T00:00:00Z",
                "snapshot_ref": "reaction-snapshot:secret",
                "snapshot_status": "complete",
                "status": "effects_applied",
                "counts": {
                    "personal_reaction_events_detected": 2,
                    "unique_reacted_posts": 2,
                    "posts_resolved": 1,
                    "eligible_period_posts": 1,
                    "unique_atoms_linked": 1,
                    "unique_canonical_threads_linked": 0,
                    "canonical_threads_boosted": 0,
                    "unique_compatibility_threads_linked": 1,
                    "compatibility_threads_boosted": 1,
                    "selected_items_linked": 1,
                    "selected_signals_influenced": 1,
                    "unconsumed_reaction_events": 1,
                },
                "influenced_items": [
                    {
                        "surface_item_ref": "thread:evaluation-discipline",
                        "effect": "rank_changed",
                        "boost_applied": True,
                        "rank_changed": True,
                        "selection_changed": False,
                        "linked_only": False,
                        "compatibility_thread_ref": "idea_thread:evaluation-discipline",
                        "current_thread_ref": "idea_thread:evaluation-discipline",
                        "canonical_thread_ref": None,
                        "thread_resolution_status": "compatibility_current_thread_only",
                        "boost_role": "weak_implicit_interest",
                        "reacted_post_count": 1,
                        "reader_reason_ru": "Вы отметили один связанный пост за отчётный период.",
                        "reacted_post_refs": ["reaction-post:222222222222222222222222"],
                        "source_refs": ["telegram:@source"],
                        "evidence_refs": ["atom:999"],
                    }
                ],
                "linked_only_items": [],
                "eligible_thread_audit": [
                    {
                        "surface_item_ref": "thread:evaluation-discipline",
                        "selected": True,
                        "counterfactual_effect": "rank_changed",
                        "boost_applied": True,
                        "compatibility_thread_ref": "idea_thread:evaluation-discipline",
                        "current_thread_ref": "idea_thread:evaluation-discipline",
                        "canonical_thread_ref": None,
                        "thread_resolution_status": "compatibility_current_thread_only",
                        "boost_role": "weak_implicit_interest",
                        "reacted_post_count": 1,
                        "reader_reason_ru": "Вы отметили один связанный пост за отчётный период.",
                        "reacted_post_refs": ["reaction-post:222222222222222222222222"],
                        "source_refs": ["telegram:@source"],
                        "evidence_refs": ["atom:999"],
                    }
                ],
                "unconsumed_by_reason": {"report_limit_reached": 1},
                "unconsumed": [
                    {
                        "reaction_ref": "reaction:333333333333333333333333",
                        "reason": "report_limit_reached",
                        "reasons": ["report_limit_reached"],
                        "audit_detail": "eligible compatibility thread remained below the report limit",
                    }
                ],
                "ranking_policy": {
                    "policy_version": "reaction-ranking.v1",
                    "strength": "weak",
                    "below_confirmed_feedback": True,
                    "can_change_evidence_gate": False,
                },
                "reader_summary_ru": (
                    "2 личных реакций → 1 постов найдено → 1 атомов знаний → "
                    "1 тем → 1 сигналов изменили позицию."
                ),
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            brief = build_weekly_intelligence_brief_artifact(
                context,
                generated_at=context["generated_at"],
                output_root=root / "brief",
                mvp_radar={},
            )
            atlas = build_knowledge_atlas_artifact(
                context,
                generated_at=context["generated_at"],
                output_root=root / "atlas",
            )
            brief_json = json.loads(Path(brief.json_path).read_text(encoding="utf-8"))
            atlas_json = json.loads(Path(atlas.json_path).read_text(encoding="utf-8"))
            brief_html = Path(brief.html_path).read_text(encoding="utf-8")
            atlas_html = Path(atlas.html_path).read_text(encoding="utf-8")

        self.assertEqual(brief_json["schema_version"], "split_ai_report.v1")
        self.assertEqual(atlas_json["schema_version"], "split_ai_report.v1")
        self.assertEqual(brief_json["reaction_effect"]["surface"], "weekly_brief")
        self.assertEqual(atlas_json["reaction_effect"]["surface"], "knowledge_atlas")
        self.assertEqual(
            brief_json["reaction_effect"]["counts"],
            atlas_json["reaction_effect"]["counts"],
        )
        for reader_html in (brief_html, atlas_html):
            self.assertIn("Как реакции повлияли на выпуск", reader_html)
            self.assertIn("2 личных реакций", reader_html)
            self.assertIn("найдено постов — 1", reader_html)
            self.assertIn("Почему сигнал изменил место", reader_html)
            self.assertIn("Evaluation discipline", reader_html)
            self.assertIn("Почему этот сигнал здесь", reader_html)
            self.assertIn("сигнал остался за пределом краткой выборки", reader_html)
            self.assertNotIn("reaction-snapshot:secret", reader_html)
            self.assertNotIn("idea_thread:secret", reader_html)
            self.assertNotIn("rank_changed", reader_html)
            self.assertNotIn("🔥", reader_html)


if __name__ == "__main__":
    unittest.main()
