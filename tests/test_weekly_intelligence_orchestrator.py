import json
import sqlite3
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import output.weekly_intelligence_orchestrator as orchestrator_module
from output.mvp_weekly_pipeline import MvpWeeklyPipelineResult
from output.frontier_analysis import frontier_analysis_fingerprint
from output.reporting_period import resolve_reporting_period
from output.weekly_intelligence_brief import RADAR_DISABLED_DISCLOSURE_RU
from output.weekly_intelligence_orchestrator import (
    _deliver_from_manifest,
    _frontier_stage,
    run_weekly_intelligence_v2,
)
from output.weekly_run_manifest import PIPELINE_PROFILE, load_manifest, sha256_file


RUN_AT = datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)


class TestWeeklyIntelligenceOrchestrator(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.db_path = self.root / "agent.sqlite3"
        sqlite3.connect(self.db_path).close()
        self.settings = types.SimpleNamespace(db_path=str(self.db_path))
        self.period = resolve_reporting_period(RUN_AT)

    def tearDown(self):
        self.temporary.cleanup()

    def _frontier(self, _settings, period, run_dir, *_args, **_kwargs):
        manifest_path, run_id = _args[:2]
        relative = Path("frontier") / "frontier-analysis.json"
        path = run_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        analysis = {
            "id": 7,
            "analysis": {
                "source_context": {
                    **period.to_dict(),
                    "feedback_snapshot_at": period.to_dict()["analysis_period_end"],
                }
            },
        }
        path.write_text(
            json.dumps(
                {
                    "schema_version": "frontier_analysis_run_snapshot.v1",
                    **period.to_dict(),
                    "run_id": run_id,
                    "manifest_path": str(Path(manifest_path).resolve()),
                    "pipeline_profile": PIPELINE_PROFILE,
                    "frontier_analysis": analysis,
                }
            ),
            encoding="utf-8",
        )
        return {
            "analysis_id": 7,
            "artifact_path": relative.as_posix(),
            "checksums": {"artifact_path": sha256_file(path)},
            "record_counts": {"threads": 0, "atoms": 0, "actions": 0},
        }

    def _radar(self, **overrides):
        def invoke(_settings, **kwargs):
            period = kwargs["reporting_period"]
            seed_path = Path(kwargs["seed_output_path"])
            seed_path.parent.mkdir(parents=True, exist_ok=True)
            seed_path.write_text(
                json.dumps(
                    [
                        {
                            "title": "Bound candidate seed",
                            **period.to_dict(),
                        }
                    ]
                ),
                encoding="utf-8",
            )
            source_path = self.root / f"{kwargs['radar_run_id']}.json"
            source_path.write_text(
                json.dumps(
                    {
                        "result": {
                            "run_id": kwargs["radar_run_id"],
                            "status": "selected",
                            "selected_title": "Same-run Candidate",
                            "dossier_status": "investigate",
                            "recommendation": "revisit_with_evidence_gap",
                            "score": 61,
                            "selected_source_mix": {
                                "decision_grade_external": False,
                            },
                        },
                        "selected": {
                            "title": "Same-run Candidate",
                            "dossier_status": "investigate",
                            "recommendation": "revisit_with_evidence_gap",
                            "missing_evidence": ["matched external demand"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            values = {
                "week_label": period.reporting_week,
                "seed_path": str(seed_path),
                "seed_count": 1,
                "radar_status": "selected",
                "report_path": None,
                "json_path": str(source_path),
                "selected_title": "Same-run Candidate",
                "dossier_status": "investigate",
                "recommendation": "revisit_with_evidence_gap",
                "score": 61,
                "radar_run_id": kwargs["radar_run_id"],
                "live_intelligence_path": (
                    str(kwargs["live_intelligence_path"])
                    if kwargs.get("live_intelligence_path") is not None
                    else None
                ),
                "knowledge_thread_count": 0,
                **period.to_dict(),
            }
            values.update(overrides)
            return MvpWeeklyPipelineResult(**values)

        return invoke

    def _run(self, **kwargs):
        context_error = kwargs.pop("_context_error", None)
        context_override = kwargs.pop("_context", None)
        knowledge = types.SimpleNamespace(
            atoms_seen=0,
            threads_refreshed=0,
            links_refreshed=0,
        )
        context = context_override or {
            **self.period.to_dict(),
            "threads": [],
            "source_channels": [],
            "marked_posts": [],
            "frontier_analysis": None,
            "feedback_context": {},
        }
        context_patch = patch(
            "output.weekly_intelligence_orchestrator.load_ai_intelligence_context",
            side_effect=context_error,
        ) if context_error is not None else patch(
            "output.weekly_intelligence_orchestrator.load_ai_intelligence_context",
            return_value=context,
        )
        with patch(
            "output.weekly_intelligence_orchestrator.refresh_idea_threads",
            return_value=knowledge,
        ), patch(
            "output.weekly_intelligence_orchestrator._sync_reactions",
            return_value={"posts_checked": 0, "errors": 0},
        ), patch(
            "output.weekly_intelligence_orchestrator._feedback_snapshot",
            return_value={
                "snapshot_id": "feedback-snapshot:test",
                "cutoff": self.period.to_dict()["analysis_period_end"],
                "confirmed_event_count": 0,
                "pending_event_count": 0,
                "record_counts": {"confirmed_events": 0, "pending_intakes": 0},
            },
        ), patch(
            "output.weekly_intelligence_orchestrator._frontier_stage",
            side_effect=self._frontier,
        ), patch(
            "output.weekly_intelligence_orchestrator.run_mvp_weekly_pipeline",
            side_effect=self._radar(),
        ), context_patch:
            return run_weekly_intelligence_v2(
                self.settings,
                reporting_period=self.period,
                output_root=self.root / "runs",
                run_id=kwargs.pop("run_id", "irx2-test-run"),
                **kwargs,
            )

    def test_success_binds_one_run_period_radar_and_reader_sidecars(self):
        result = self._run()

        self.assertEqual(result.run_status, "complete")
        manifest = load_manifest(
            result.manifest_path,
            path_base=Path(result.manifest_path).parent,
            allowed_roots=(Path(result.manifest_path).parent,),
            check_artifact_existence=True,
        )
        self.assertEqual(manifest["run_id"], "irx2-test-run")
        self.assertEqual(manifest["reporting_week"], "2026-W28")
        self.assertEqual(manifest["stages"]["radar"]["radar_run_id"], "irx2-test-run-radar")
        self.assertEqual(manifest["run_status"], "complete")
        brief = json.loads(Path(result.weekly_brief_json_path).read_text(encoding="utf-8"))
        atlas = json.loads(Path(result.atlas_json_path).read_text(encoding="utf-8"))
        for payload in (brief, atlas):
            self.assertEqual(payload["run_id"], result.run_id)
            self.assertEqual(payload["manifest_path"], result.manifest_path)
            self.assertEqual(payload["run_status"], "complete")
            self.assertEqual(payload["analysis_period_end"], "2026-07-13T00:00:00Z")
        self.assertEqual(brief["mvp_radar"]["selected_candidate"], "Same-run Candidate")
        self.assertEqual(brief["mvp_radar"]["status"], "selected")
        binding_path = Path(result.manifest_path).parent / manifest["stages"]["radar"]["binding_path"]
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        self.assertEqual(binding["manifest_run_id"], result.run_id)
        self.assertEqual(binding["radar_run_id"], "irx2-test-run-radar")

    def test_reaction_failure_is_partial_and_uses_pre_run_snapshot(self):
        with patch(
            "output.weekly_intelligence_orchestrator._sync_reactions",
            side_effect=RuntimeError("reaction API unavailable"),
        ):
            # Keep the common patches while overriding the nested reaction patch.
            knowledge = types.SimpleNamespace(atoms_seen=0, threads_refreshed=0, links_refreshed=0)
            context = {**self.period.to_dict(), "threads": [], "feedback_context": {}}
            with patch(
                "output.weekly_intelligence_orchestrator.refresh_idea_threads",
                return_value=knowledge,
            ), patch(
                "output.weekly_intelligence_orchestrator._feedback_snapshot",
                return_value={
                    "snapshot_id": "feedback-snapshot:test",
                    "cutoff": self.period.to_dict()["analysis_period_end"],
                    "confirmed_event_count": 0,
                    "pending_event_count": 0,
                },
            ), patch(
                "output.weekly_intelligence_orchestrator._frontier_stage",
                side_effect=self._frontier,
            ), patch(
                "output.weekly_intelligence_orchestrator.run_mvp_weekly_pipeline",
                side_effect=self._radar(),
            ), patch(
                "output.weekly_intelligence_orchestrator.load_ai_intelligence_context",
                return_value=context,
            ):
                result = run_weekly_intelligence_v2(
                    self.settings,
                    reporting_period=self.period,
                    output_root=self.root / "runs",
                    run_id="irx2-reaction-failure",
                )

        self.assertEqual(result.run_status, "partial")
        manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
        self.assertEqual(manifest["stages"]["reaction_sync"]["status"], "failed")
        brief = json.loads(Path(result.weekly_brief_json_path).read_text(encoding="utf-8"))
        self.assertEqual(brief["reaction_snapshot_at"], self.period.to_dict()["generated_at"])
        self.assertEqual(brief["run_status"], "partial")

    def test_wrong_period_radar_is_rejected_and_package_is_partial(self):
        wrong = self._radar(reporting_week="2026-W27", week_label="2026-W27")
        with patch(
            "output.weekly_intelligence_orchestrator.run_mvp_weekly_pipeline",
            side_effect=wrong,
        ):
            # _run installs its own Radar patch, so exercise a dedicated full setup.
            knowledge = types.SimpleNamespace(atoms_seen=0, threads_refreshed=0, links_refreshed=0)
            context = {**self.period.to_dict(), "threads": [], "feedback_context": {}}
            with patch(
                "output.weekly_intelligence_orchestrator.refresh_idea_threads",
                return_value=knowledge,
            ), patch(
                "output.weekly_intelligence_orchestrator._sync_reactions",
                return_value={"errors": 0},
            ), patch(
                "output.weekly_intelligence_orchestrator._feedback_snapshot",
                return_value={
                    "snapshot_id": "feedback-snapshot:test",
                    "cutoff": self.period.to_dict()["analysis_period_end"],
                    "confirmed_event_count": 0,
                    "pending_event_count": 0,
                },
            ), patch(
                "output.weekly_intelligence_orchestrator._frontier_stage",
                side_effect=self._frontier,
            ), patch(
                "output.weekly_intelligence_orchestrator.load_ai_intelligence_context",
                return_value=context,
            ):
                result = run_weekly_intelligence_v2(
                    self.settings,
                    reporting_period=self.period,
                    output_root=self.root / "runs",
                    run_id="irx2-wrong-radar-period",
                )

        manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
        self.assertEqual(result.run_status, "partial")
        self.assertEqual(manifest["stages"]["radar"]["status"], "failed")
        self.assertIn("period mismatch", manifest["stages"]["radar"]["error"]["message"])
        brief = json.loads(Path(result.weekly_brief_json_path).read_text(encoding="utf-8"))
        self.assertFalse(brief["mvp_radar"]["selected_candidate"])
        self.assertEqual(brief["mvp_radar"]["status"], "not_available")
        self.assertFalse(brief["mvp_radar"]["source_path"])

    def test_intentional_radar_disable_is_complete_but_reader_visible(self):
        with patch(
            "output.weekly_intelligence_orchestrator.run_mvp_weekly_pipeline"
        ) as radar:
            result = self._run(
                radar_enabled=False,
                run_id="irx2-radar-disabled",
            )

        radar.assert_not_called()
        self.assertEqual(result.run_status, "complete")
        manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
        self.assertEqual(manifest["stages"]["radar"]["status"], "disabled")
        brief_json = json.loads(Path(result.weekly_brief_json_path).read_text(encoding="utf-8"))
        brief_html = Path(result.weekly_brief_html_path).read_text(encoding="utf-8")
        self.assertTrue(brief_json["mvp_radar"]["disabled"])
        self.assertEqual(brief_json["mvp_radar_gate"]["radar_artifact_status"], "disabled")
        self.assertEqual(brief_json["mvp_radar_gate"]["warning"], RADAR_DISABLED_DISCLOSURE_RU)
        self.assertIn(RADAR_DISABLED_DISCLOSURE_RU, brief_html)

    def test_atlas_failure_leaves_a_partial_brief(self):
        with patch(
            "output.weekly_intelligence_orchestrator.build_knowledge_atlas_artifact",
            side_effect=RuntimeError("atlas render failed"),
        ):
            result = self._run(run_id="irx2-atlas-failure")

        self.assertEqual(result.run_status, "partial")
        self.assertIsNone(result.atlas_json_path)
        brief = json.loads(Path(result.weekly_brief_json_path).read_text(encoding="utf-8"))
        self.assertEqual(brief["run_status"], "partial")

    def test_brief_failure_is_fatal_and_never_delivers(self):
        with patch(
            "output.weekly_intelligence_orchestrator.build_weekly_intelligence_brief_artifact",
            side_effect=RuntimeError("brief render failed"),
        ), patch(
            "output.weekly_intelligence_orchestrator._deliver_from_manifest"
        ) as deliver:
            result = self._run(
                run_id="irx2-brief-failure",
                deliver=True,
            )

        self.assertEqual(result.run_status, "failed")
        self.assertIsNone(result.weekly_brief_json_path)
        deliver.assert_not_called()

    def test_reader_context_failure_is_terminal_and_never_delivers(self):
        with patch(
            "output.weekly_intelligence_orchestrator._deliver_from_manifest"
        ) as deliver:
            result = self._run(
                run_id="irx2-context-failure",
                deliver=True,
                _context_error=RuntimeError("context query failed"),
            )

        self.assertEqual(result.run_status, "failed")
        manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
        self.assertEqual(manifest["stages"]["weekly_brief"]["status"], "failed")
        self.assertEqual(
            manifest["stages"]["knowledge_atlas"]["status"],
            "skipped_dependency",
        )
        deliver.assert_not_called()

    def test_reader_uses_run_scoped_frontier_snapshot_not_mutable_context(self):
        seen_frontier_ids = []
        original = orchestrator_module.build_weekly_intelligence_brief_artifact

        def capture(context, **kwargs):
            seen_frontier_ids.append((context.get("frontier_analysis") or {}).get("id"))
            return original(context, **kwargs)

        stale_context = {
            **self.period.to_dict(),
            "threads": [],
            "source_channels": [],
            "marked_posts": [],
            "frontier_analysis": {"id": 999, "analysis": {}},
            "feedback_context": {},
        }
        with patch(
            "output.weekly_intelligence_orchestrator.build_weekly_intelligence_brief_artifact",
            side_effect=capture,
        ):
            result = self._run(
                run_id="irx2-frontier-snapshot",
                _context=stale_context,
            )

        self.assertEqual(result.run_status, "complete")
        self.assertTrue(seen_frontier_ids)
        self.assertEqual(set(seen_frontier_ids), {7})

    def test_delivery_revalidates_bound_artifacts_before_sending(self):
        result = self._run(run_id="irx2-delivery-validation")
        manifest_path = Path(result.manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        brief_path = Path(result.weekly_brief_json_path)
        brief_path.write_text(
            brief_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )

        with patch("bot.telegram_delivery.send_text") as send_text, patch(
            "bot.telegram_delivery.send_document"
        ) as send_document, self.assertRaisesRegex(Exception, "checksum"):
            _deliver_from_manifest(
                manifest_path,
                manifest,
                chat_id="1",
                token="token",
            )

        send_text.assert_not_called()
        send_document.assert_not_called()

    def test_live_intelligence_input_is_copied_and_checksum_bound(self):
        source = self.root / "external-live-intelligence.json"
        source.write_text(
            json.dumps(
                {
                    "schema_version": "live_source_intelligence.v1",
                    **self.period.to_dict(),
                }
            ),
            encoding="utf-8",
        )

        result = self._run(
            run_id="irx2-live-input",
            live_intelligence_path=source,
        )
        manifest_path = Path(result.manifest_path)
        manifest = load_manifest(
            manifest_path,
            path_base=manifest_path.parent,
            allowed_roots=(manifest_path.parent,),
            check_artifact_existence=True,
        )
        radar = manifest["stages"]["radar"]
        relative = radar["dependency_refs"]["live_intelligence_path"]
        bound = manifest_path.parent / relative

        self.assertNotEqual(bound.resolve(), source.resolve())
        self.assertEqual(bound.read_bytes(), source.read_bytes())
        self.assertEqual(
            radar["checksums"]["live_intelligence_path"],
            sha256_file(bound),
        )

    def test_frontier_stage_rejects_a_concurrently_replaced_week_row(self):
        source_context = {
            **self.period.to_dict(),
            "feedback_snapshot_at": self.period.to_dict()["analysis_period_end"],
        }
        row = {
            "id": 7,
            "week_label": self.period.reporting_week,
            "generated_at": self.period.to_dict()["generated_at"],
            "model": "model-a",
            "prompt_version": "frontier-analysis-v1",
            "lookback_weeks": 12,
            "threads_analyzed": 1,
            "atoms_analyzed": 1,
            "executive_brief": "original",
            "what_changed": [],
            "trend_narratives": [],
            "study_now": [],
            "actions": [],
            "caveats": [],
            "analysis": {"source_context": source_context},
        }
        summary = types.SimpleNamespace(
            analysis_sha256=frontier_analysis_fingerprint(row),
            threads_analyzed=1,
            atoms_analyzed=1,
            action_count=0,
        )
        replaced = {**row, "executive_brief": "concurrent replacement"}
        run_dir = self.root / "frontier-race"
        run_dir.mkdir()

        with patch(
            "output.weekly_intelligence_orchestrator.run_frontier_analysis",
            return_value=summary,
        ), patch(
            "output.weekly_intelligence_orchestrator.fetch_frontier_analysis",
            return_value=replaced,
        ), self.assertRaisesRegex(RuntimeError, "changed before"):
            _frontier_stage(
                self.settings,
                self.period,
                run_dir,
                run_dir / "manifest.json",
                "frontier-race-run",
                lookback_weeks=12,
                model="strong",
                threads_limit=24,
                atoms_limit=8,
                force=False,
            )


if __name__ == "__main__":
    unittest.main()
