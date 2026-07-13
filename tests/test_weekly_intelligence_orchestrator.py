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
        run_id = kwargs.pop("run_id", "irx2-test-run")
        real_context_loader = orchestrator_module.load_ai_intelligence_context
        context_error = kwargs.pop("_context_error", None)
        context_override = kwargs.pop("_context", None)
        context_calls = kwargs.pop("_context_calls", None)
        feedback_error = kwargs.pop("_feedback_error", None)
        real_context = kwargs.pop("_real_context", context_override is None)
        reaction_outcome = kwargs.pop(
            "_reaction_outcome", self._empty_verified_reaction_outcome()
        )
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
        if (
            context_override is not None
            and not context.get("reaction_effect")
            and isinstance(reaction_outcome, dict)
            and reaction_outcome.get("observed_personal_posts") == []
        ):
            context["reaction_effect"] = self._empty_complete_reaction_effect(run_id)

        def load_context(*_args, **call_kwargs):
            if context_calls is not None:
                context_calls.append(call_kwargs)
            return context

        def load_real_context(*args, **call_kwargs):
            if context_calls is not None:
                context_calls.append(call_kwargs)
            return real_context_loader(*args, **call_kwargs)

        context_patch = (
            patch(
                "output.weekly_intelligence_orchestrator.load_ai_intelligence_context",
                side_effect=context_error,
            )
            if context_error is not None
            else patch(
                "output.weekly_intelligence_orchestrator.load_ai_intelligence_context",
                side_effect=load_real_context,
            )
            if real_context
            else patch(
                "output.weekly_intelligence_orchestrator.load_ai_intelligence_context",
                side_effect=load_context,
            )
        )
        with patch(
            "output.weekly_intelligence_orchestrator.refresh_idea_threads",
            return_value=knowledge,
        ), patch(
            "output.weekly_intelligence_orchestrator._sync_reactions",
            return_value=reaction_outcome,
        ), patch(
            "output.weekly_intelligence_orchestrator._feedback_snapshot",
            side_effect=(
                feedback_error
                if feedback_error is not None
                else lambda *_args, **_kwargs: {
                    "snapshot_id": "feedback-snapshot:test",
                    "cutoff": self.period.to_dict()["analysis_period_end"],
                    "confirmed_event_count": 0,
                    "pending_event_count": 0,
                    "record_counts": {
                        "confirmed_events": 0,
                        "pending_intakes": 0,
                    },
                }
            ),
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
                run_id=run_id,
                **kwargs,
            )

    def _empty_verified_reaction_outcome(self):
        return {
            "summary": {
                "posts_checked": 0,
                "posts_with_reactions": 0,
                "matched_reactions": 0,
                "applied_tags": 0,
                "applied_feedback": 0,
                "skipped_unknown": 0,
                "skipped_existing": 0,
                "errors": 0,
            },
            "observed_personal_posts": [],
            "candidate_count": 0,
            "checked_count": 0,
            "coverage_complete": True,
            "visibility_verified": True,
        }

    def _empty_complete_reaction_effect(self, run_id):
        return {
            "schema_version": "reaction_personalization.v1",
            "run_id": run_id,
            "surface": "weekly_brief",
            "reporting_week": self.period.reporting_week,
            "analysis_period_start": "2026-07-06T00:00:00Z",
            "analysis_period_end": "2026-07-13T00:00:00Z",
            "snapshot_ref": f"reaction-snapshot:{run_id}",
            "snapshot_status": "complete",
            "status": "no_eligible_reactions",
            "reader_summary_ru": (
                "Для источников этого периода личные реакции не найдены. Это не снижало "
                "оценки тем и не трактовалось как отсутствие интереса."
            ),
            "counts": {
                "personal_reaction_events_detected": 0,
                "unique_reacted_posts": 0,
                "posts_resolved": 0,
                "eligible_period_posts": 0,
                "unique_atoms_linked": 0,
                "unique_canonical_threads_linked": 0,
                "canonical_threads_boosted": 0,
                "unique_compatibility_threads_linked": 0,
                "compatibility_threads_boosted": 0,
                "selected_items_linked": 0,
                "selected_signals_influenced": 0,
                "unconsumed_reaction_events": 0,
            },
            "influenced_items": [],
            "linked_only_items": [],
            "eligible_thread_audit": [],
            "unconsumed_by_reason": {},
            "unconsumed": [],
            "ranking_policy": {
                "policy_version": "reaction-ranking.v1",
                "strength": "weak",
                "below_confirmed_feedback": True,
                "can_change_evidence_gate": False,
            },
        }

    def _verified_reaction_outcome(self):
        return {
            "summary": {
                "posts_checked": 2,
                "posts_with_reactions": 1,
                "matched_reactions": 2,
                "applied_tags": 2,
                "applied_feedback": 2,
                "skipped_unknown": 0,
                "skipped_existing": 0,
                "errors": 0,
            },
            "observed_personal_posts": [
                {
                    "post_id": 41,
                    "channel_username": "@source",
                    "message_id": 77,
                    "posted_at": "2026-07-12T23:59:59Z",
                    "raw_emojis": ["custom_emoji:123", "🔥"],
                }
            ],
            "candidate_count": 2,
            "checked_count": 2,
            "coverage_complete": True,
            "visibility_verified": True,
        }

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

    def test_verified_reaction_outcome_is_immutable_bound_and_passed_to_context(self):
        seen = []
        context_calls = []
        original = orchestrator_module.build_weekly_intelligence_brief_artifact

        def capture(context, **kwargs):
            seen.append(
                (
                    context.get("reaction_snapshot_binding"),
                    context.get("reaction_snapshot"),
                )
            )
            return original(context, **kwargs)

        with patch(
            "output.weekly_intelligence_orchestrator.build_weekly_intelligence_brief_artifact",
            side_effect=capture,
        ):
            result = self._run(
                run_id="irx3-reaction-snapshot",
                _reaction_outcome=self._verified_reaction_outcome(),
                _context_calls=context_calls,
            )

        manifest_path = Path(result.manifest_path)
        manifest = load_manifest(
            manifest_path,
            path_base=manifest_path.parent,
            allowed_roots=(manifest_path.parent,),
            check_artifact_existence=True,
        )
        stage = manifest["stages"]["reaction_sync"]
        self.assertEqual(stage["status"], "succeeded")
        self.assertEqual(
            stage["artifact_refs"],
            {"snapshot_path": "reaction_sync/reaction-snapshot.json"},
        )
        snapshot_path = manifest_path.parent / stage["artifact_refs"]["snapshot_path"]
        self.assertEqual(
            stage["checksums"]["snapshot_path"], sha256_file(snapshot_path)
        )
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertEqual(snapshot["schema_version"], "reaction_visibility_snapshot.v1")
        self.assertEqual(snapshot["run_id"], result.run_id)
        self.assertEqual(snapshot["snapshot_ref"], stage["snapshot_ref"])
        self.assertEqual(snapshot["observed_through"], stage["observed_through"])
        for field, expected in self.period.to_dict().items():
            self.assertEqual(snapshot[field], expected)
        self.assertEqual(
            snapshot["coverage"],
            {
                "candidate_count": 2,
                "checked_count": 2,
                "coverage_complete": True,
                "visibility_verified": True,
            },
        )
        self.assertEqual(snapshot["observed_personal_posts"][0]["post_id"], 41)
        self.assertTrue(seen)
        for binding, context_snapshot in seen:
            self.assertEqual(context_snapshot, snapshot)
            self.assertEqual(binding["snapshot_ref"], stage["snapshot_ref"])
            self.assertEqual(
                binding["snapshot_path"], "reaction_sync/reaction-snapshot.json"
            )
            self.assertEqual(
                binding["snapshot_sha256"], stage["checksums"]["snapshot_path"]
            )
            self.assertEqual(binding["snapshot_status"], "complete")
            self.assertTrue(binding["usable"])
        self.assertEqual(len(context_calls), 1)
        self.assertEqual(context_calls[0]["reaction_snapshot"], snapshot)
        self.assertEqual(
            context_calls[0]["reaction_snapshot_binding"]["snapshot_status"],
            "complete",
        )
        self.assertTrue(context_calls[0]["feedback_snapshot_usable"])

    def test_legacy_count_only_reaction_success_remains_unbound(self):
        seen = []
        context_calls = []
        original = orchestrator_module.build_weekly_intelligence_brief_artifact

        def capture(context, **kwargs):
            seen.append(
                (
                    context.get("reaction_snapshot_binding"),
                    context.get("reaction_snapshot"),
                )
            )
            return original(context, **kwargs)

        with patch(
            "output.weekly_intelligence_orchestrator.build_weekly_intelligence_brief_artifact",
            side_effect=capture,
        ):
            result = self._run(
                run_id="irx3-legacy-reaction-outcome",
                _reaction_outcome={"posts_checked": 0, "errors": 0},
                _context_calls=context_calls,
            )

        manifest_path = Path(result.manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        stage = manifest["stages"]["reaction_sync"]
        self.assertEqual(result.run_status, "partial")
        self.assertEqual(stage["status"], "failed")
        self.assertEqual(stage["artifact_refs"], {})
        self.assertEqual(stage["checksums"], {})
        self.assertFalse(
            (manifest_path.parent / "reaction_sync/reaction-snapshot.json").exists()
        )
        self.assertTrue(seen)
        for binding, context_snapshot in seen:
            self.assertIsNone(context_snapshot)
            self.assertEqual(binding["run_id"], result.run_id)
            self.assertEqual(binding["stage_status"], "failed")
            self.assertEqual(binding["snapshot_status"], "partial")
            self.assertFalse(binding["usable"])
            self.assertNotIn("snapshot_path", binding)
        self.assertEqual(len(context_calls), 1)
        self.assertIsNone(context_calls[0]["reaction_snapshot"])
        self.assertEqual(
            context_calls[0]["reaction_snapshot_binding"]["snapshot_status"],
            "partial",
        )

    def test_failed_feedback_snapshot_disables_reaction_personalization_input(self):
        context_calls = []

        result = self._run(
            run_id="irx3-feedback-unusable",
            _reaction_outcome=self._verified_reaction_outcome(),
            _feedback_error=RuntimeError("feedback snapshot failed"),
            _context_calls=context_calls,
            _real_context=True,
        )

        self.assertEqual(result.run_status, "partial")
        self.assertEqual(len(context_calls), 1)
        self.assertTrue(
            context_calls[0]["reaction_snapshot_binding"]["usable"]
        )
        self.assertIsNotNone(context_calls[0]["reaction_snapshot"])
        self.assertFalse(context_calls[0]["feedback_snapshot_usable"])

    def test_real_reader_context_emits_unavailable_legacy_receipt_on_both_surfaces(self):
        result = self._run(
            run_id="irx3-real-context-legacy",
            _real_context=True,
            _reaction_outcome={"posts_checked": 0, "errors": 0},
        )

        brief = json.loads(Path(result.weekly_brief_json_path).read_text(encoding="utf-8"))
        atlas = json.loads(Path(result.atlas_json_path).read_text(encoding="utf-8"))
        brief_effect = brief["reaction_effect"]
        atlas_effect = atlas["reaction_effect"]
        self.assertEqual(result.run_status, "partial")
        self.assertEqual(brief_effect["status"], "partial")
        self.assertEqual(brief_effect["snapshot_status"], "partial")
        self.assertEqual(brief_effect["surface"], "weekly_brief")
        self.assertEqual(atlas_effect["surface"], "knowledge_atlas")
        brief_effect.pop("surface")
        atlas_effect.pop("surface")
        self.assertEqual(brief_effect, atlas_effect)
        for path in (result.weekly_brief_html_path, result.atlas_html_path):
            self.assertIn(
                "Как реакции повлияли на выпуск",
                Path(path).read_text(encoding="utf-8"),
            )

    def test_real_reader_context_consumes_only_the_bound_verified_snapshot(self):
        result = self._run(
            run_id="irx3-real-context-verified",
            _real_context=True,
            _reaction_outcome=self._verified_reaction_outcome(),
        )

        manifest_path = Path(result.manifest_path)
        manifest = load_manifest(
            manifest_path,
            path_base=manifest_path.parent,
            allowed_roots=(manifest_path.parent,),
            check_artifact_existence=True,
        )
        brief = json.loads(Path(result.weekly_brief_json_path).read_text(encoding="utf-8"))
        effect = brief["reaction_effect"]
        self.assertEqual(effect["snapshot_status"], "complete")
        self.assertEqual(
            effect["snapshot_ref"], manifest["stages"]["reaction_sync"]["snapshot_ref"]
        )
        self.assertEqual(effect["status"], "no_eligible_reactions")
        self.assertEqual(effect["counts"]["unique_reacted_posts"], 1)
        self.assertEqual(
            effect["counts"]["personal_reaction_events_detected"], 2
        )

    def test_real_reader_context_keeps_complete_snapshot_identity_when_feedback_fails(self):
        result = self._run(
            run_id="irx3-real-context-feedback-partial",
            _real_context=True,
            _reaction_outcome=self._verified_reaction_outcome(),
            _feedback_error=RuntimeError("feedback snapshot failed"),
        )

        self.assertEqual(result.run_status, "partial")
        brief = json.loads(Path(result.weekly_brief_json_path).read_text(encoding="utf-8"))
        effect = brief["reaction_effect"]
        self.assertEqual(effect["status"], "partial")
        self.assertEqual(effect["snapshot_status"], "complete")
        brief_html = Path(result.weekly_brief_html_path).read_text(encoding="utf-8")
        self.assertIn("контекст явной обратной связи", brief_html)
        self.assertNotIn("Синхронизация реакций не завершена", brief_html)
        self.assertNotIn("найдено постов — 0", brief_html)
        self.assertIn("постов с подтверждёнными реакциями — 1", brief_html)
        manifest_path = Path(result.manifest_path)
        load_manifest(
            manifest_path,
            path_base=manifest_path.parent,
            allowed_roots=(manifest_path.parent,),
            check_artifact_existence=True,
        )

    def test_real_reader_context_marks_unverified_reaction_stage_partial_without_payload(self):
        outcome = {
            **self._verified_reaction_outcome(),
            "visibility_verified": False,
        }
        result = self._run(
            run_id="irx3-real-context-reaction-partial",
            _real_context=True,
            _reaction_outcome=outcome,
        )

        self.assertEqual(result.run_status, "partial")
        manifest_path = Path(result.manifest_path)
        manifest = load_manifest(
            manifest_path,
            path_base=manifest_path.parent,
            allowed_roots=(manifest_path.parent,),
            check_artifact_existence=True,
        )
        self.assertEqual(manifest["stages"]["reaction_sync"]["status"], "failed")
        self.assertEqual(manifest["stages"]["reaction_sync"]["artifact_refs"], {})
        brief = json.loads(Path(result.weekly_brief_json_path).read_text(encoding="utf-8"))
        self.assertEqual(brief["reaction_effect"]["status"], "partial")
        self.assertEqual(brief["reaction_effect"]["snapshot_status"], "partial")

    def test_unverified_incomplete_or_error_outcome_fails_without_a_usable_snapshot(self):
        valid = self._verified_reaction_outcome()
        cases = {
            "unverified": {**valid, "visibility_verified": False},
            "truncated": {
                **valid,
                "candidate_count": 3,
                "coverage_complete": False,
            },
            "errors": {
                **valid,
                "summary": {**valid["summary"], "errors": 1},
            },
            "summary-checked-mismatch": {
                **valid,
                "summary": {**valid["summary"], "posts_checked": 0},
            },
            "summary-observed-mismatch": {
                **valid,
                "summary": {**valid["summary"], "posts_with_reactions": 0},
            },
            "summary-event-mismatch": {
                **valid,
                "summary": {
                    **valid["summary"],
                    "matched_reactions": 0,
                    "skipped_existing": 0,
                },
            },
            "missing-coverage": {
                key: value
                for key, value in valid.items()
                if key != "coverage_complete"
            },
        }
        for suffix, outcome in cases.items():
            with self.subTest(suffix=suffix):
                context_calls = []
                result = self._run(
                    run_id=f"irx3-reaction-{suffix}",
                    _reaction_outcome=outcome,
                    _context_calls=context_calls,
                )
                manifest_path = Path(result.manifest_path)
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                stage = manifest["stages"]["reaction_sync"]
                self.assertEqual(result.run_status, "partial")
                self.assertEqual(stage["status"], "failed")
                self.assertEqual(stage["artifact_refs"], {})
                self.assertEqual(stage["checksums"], {})
                self.assertFalse(
                    (
                        manifest_path.parent
                        / "reaction_sync/reaction-snapshot.json"
                    ).exists()
                )
                self.assertEqual(len(context_calls), 1)
                self.assertIsNone(context_calls[0]["reaction_snapshot"])
                descriptor = context_calls[0]["reaction_snapshot_binding"]
                self.assertEqual(descriptor["stage_status"], "failed")
                self.assertEqual(descriptor["snapshot_status"], "partial")
                self.assertFalse(descriptor["usable"])

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
