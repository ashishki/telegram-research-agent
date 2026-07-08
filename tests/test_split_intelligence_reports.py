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
from output.idea_threads import refresh_idea_threads
from output.split_intelligence_reports import generate_split_intelligence_reports


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
            self.assertIn('id="trend-board"', atlas_html)
            self.assertIn('id="brief-actions"', brief_html)
            self.assertLess(brief_html.find('id="brief-actions"'), brief_html.find('id="brief-mvp-radar"'))
            self.assertEqual(atlas_json["artifact_type"], "knowledge_atlas")
            self.assertEqual(brief_json["artifact_type"], "weekly_intelligence_brief")
            self.assertEqual(
                atlas_json["related_artifacts"]["weekly_brief_json_path"],
                summary.weekly_brief.json_path,
            )
            self.assertEqual(
                brief_json["related_artifacts"]["knowledge_atlas_json_path"],
                summary.knowledge_atlas.json_path,
            )
            self.assertEqual(brief_json["mvp_radar"]["selected_candidate"], "Agent Eval Gate Scanner")


if __name__ == "__main__":
    unittest.main()
