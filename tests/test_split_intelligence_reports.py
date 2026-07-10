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
from output.idea_threads import refresh_idea_threads
from output.split_intelligence_reports import deliver_split_intelligence_reports, generate_split_intelligence_reports


class TestSplitIntelligenceReports(unittest.TestCase):
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
                week_label="2026-W28",
                threads_limit=8,
                atoms_limit=4,
                output_root=root,
                mvp_radar_json_path=mvp_path,
                now=datetime(2026, 7, 8, tzinfo=timezone.utc),
            )

            atlas_html = Path(summary.knowledge_atlas.html_path).read_text(encoding="utf-8")
            brief_html = Path(summary.weekly_brief.html_path).read_text(encoding="utf-8")
            atlas_json = json.loads(Path(summary.knowledge_atlas.json_path).read_text(encoding="utf-8"))
            brief_json = json.loads(Path(summary.weekly_brief.json_path).read_text(encoding="utf-8"))

            self.assertTrue(summary.knowledge_atlas.html_path.endswith(".knowledge-atlas.html"))
            self.assertTrue(summary.weekly_brief.html_path.endswith(".weekly-brief.html"))
            self.assertIn("<title>Knowledge Atlas 2026-W28</title>", atlas_html)
            self.assertIn("<title>Weekly Intelligence Brief 2026-W28</title>", brief_html)
            self.assertIn(f'content="{INTELLIGENCE_CONTRACT_VERSION}"', atlas_html)
            self.assertIn(f'content="{INTELLIGENCE_CONTRACT_VERSION}"', brief_html)
            self.assertIn(f'content="{RADAR_INTELLIGENCE_CONTRACT_VERSION}"', brief_html)
            self.assertIn('id="trend-board"', atlas_html)
            self.assertIn('id="brief-actions"', brief_html)
            self.assertIn("Why selected:", brief_html)
            self.assertLess(brief_html.find('id="brief-actions"'), brief_html.find('id="brief-mvp-radar"'))
            self.assertEqual(atlas_json["artifact_type"], "knowledge_atlas")
            self.assertEqual(brief_json["artifact_type"], "weekly_intelligence_brief")
            self.assertEqual(atlas_json["contract_version"], INTELLIGENCE_CONTRACT_VERSION)
            self.assertEqual(brief_json["contract_version"], INTELLIGENCE_CONTRACT_VERSION)
            self.assertEqual(brief_json["radar_contract_version"], RADAR_INTELLIGENCE_CONTRACT_VERSION)
            self.assertTrue(brief_json["actions"][0]["ranking_factors"])
            self.assertTrue(brief_json["actions"][0]["why_selected"])
            self.assertTrue(brief_json["personal_learning_loop"]["read_items"][0]["ranking_factors"])
            self.assertTrue(brief_json["personal_learning_loop"]["read_items"][0]["why_selected"])
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
            self.assertIn("Top Personal Changes", brief_html)
            self.assertIn("Evidence / Trust", brief_html)
            self.assertIn("What To Do", brief_html)
            self.assertIn("Ignore / Defer", brief_html)
            self.assertIn("Project Impact", brief_html)
            self.assertIn("Exact Feedback Targets", brief_html)
            self.assertIn("Do not build yet.", brief_html)
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
                now=datetime(2026, 7, 8, tzinfo=timezone.utc),
            )

            brief_html = Path(summary.weekly_brief.html_path).read_text(encoding="utf-8")
            brief_json = json.loads(Path(summary.weekly_brief.json_path).read_text(encoding="utf-8"))
            atlas_exists = Path(summary.knowledge_atlas.html_path).exists()

        self.assertTrue(atlas_exists)
        self.assertEqual(brief_json["mvp_radar"]["status"], "not_available")
        self.assertEqual(brief_json["mvp_radar_gate"]["radar_artifact_status"], "missing")
        self.assertEqual(brief_json["mvp_radar_gate"]["decision"], "do_not_build")
        self.assertIn("MVP Radar artifact is missing", brief_html)
        self.assertIn("No candidate selected", brief_html)


if __name__ == "__main__":
    unittest.main()
