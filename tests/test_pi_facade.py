import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from assistant.pi_facade import PersonalIntelligenceFacade
from config.settings import Settings
from output.reporting_period import resolve_reporting_period
from output.weekly_intelligence_brief import RADAR_DISABLED_DISCLOSURE_RU
from output.weekly_run_manifest import (
    build_initial_manifest,
    build_radar_run_binding,
    fail_stage,
    finalize_manifest,
    sha256_file,
    start_stage,
    succeed_stage,
    transition_stage,
)


class TestPersonalIntelligenceFacade(unittest.TestCase):
    def _unavailable_reaction_effect(self, run_id: str) -> dict:
        return {
            "schema_version": "reaction_personalization.v1",
            "run_id": run_id,
            "surface": "weekly_brief",
            "reporting_week": "2026-W28",
            "analysis_period_start": "2026-07-06T00:00:00Z",
            "analysis_period_end": "2026-07-13T00:00:00Z",
            "snapshot_ref": f"reaction-snapshot:{run_id}",
            "snapshot_status": "unavailable",
            "status": "unavailable",
            "reader_summary_ru": (
                "Синхронизация реакций не завершена. Персонализация по реакциям "
                "для этого запуска не применялась."
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

    def _settings(self, root: Path) -> Settings:
        return Settings(
            db_path=str(root / "agent.db"),
            llm_api_key="",
            model_provider="",
            telegram_session_path="",
        )

    def _write_workbook(self, root: Path, *, marked_posts: list[dict] | None = None) -> None:
        output_dir = root / "ai_visual_intelligence"
        output_dir.mkdir(parents=True)
        html_path = output_dir / "2026-W28.visual.html"
        json_path = output_dir / "2026-W28.visual.json"
        html_path.write_text("<!doctype html><title>workbook</title>", encoding="utf-8")
        json_path.write_text(
            json.dumps(
                {
                    "week_label": "2026-W28",
                    "generated_at": "2026-07-08T00:00:00Z",
                    "html_path": str(html_path),
                    "workbook_sections": [
                        {"id": "decision-brief", "title": "Операторский вердикт", "title_en": "Decision Brief", "kind": "decision_brief"},
                        {"id": "strong-signals", "title": "Сильные сигналы", "title_en": "Strong Signals", "kind": "strong_signals"},
                    ],
                    "decision_cards": [
                        {
                            "id": "decision-1",
                            "verdict": "study",
                            "title": "Study eval gates",
                            "why_for_operator": "Eval gates matter this week.",
                            "next_action": "Read one source.",
                            "confidence": "medium",
                            "evidence_atom_ids": [101],
                        }
                    ],
                    "claim_cards": [
                        {
                            "id": "claim-1",
                            "claim": "Eval gates are becoming release infrastructure for coding agents.",
                            "caveat": "Evidence is still source-limited.",
                            "source_urls": ["https://t.me/ai_lab/101"],
                            "evidence_atom_ids": [101],
                            "evidence_tier": "primary_source",
                            "verification_status": "verified",
                            "confidence": 0.8,
                        }
                    ],
                    "action_cards": [
                        {
                            "id": "action-1",
                            "title": "Try a tiny eval gate",
                            "next_step": "Add one regression guard.",
                            "success_criterion": "Bad agent edit fails before merge.",
                            "effort": "30 min",
                            "scope": "verification",
                            "why_selected": "Selected for source-backed utility with confirmed feedback.",
                            "ranking_factors": [
                                {
                                    "label": "feedback_score",
                                    "value": 1,
                                    "weight": "high",
                                    "evidence": {"event_count": 1, "confirmation_state": "confirmed_only"},
                                }
                            ],
                        }
                    ],
                    "project_diagnostic": {
                        "implementation_suggestions": [
                            {
                                "project": "telegram-research-agent",
                                "title": "Add eval gate backlog item",
                                "next_step": "Draft one scoped issue.",
                                "effort": "30 min",
                                "risk_caveat": "Do not overbuild.",
                                "acceptance_criteria": ["Issue has owner and test command."],
                                "source_atom_ids": [101],
                                "source_urls": ["https://t.me/ai_lab/101"],
                            }
                        ]
                    },
                    "mvp_radar": {
                        "status": "loaded",
                        "selected_candidate": "LLM Guardrail Watchdog",
                        "dossier_status": "investigate",
                        "recommendation": "revisit_with_evidence_gap",
                        "source_mix": {"readiness": "telegram_only"},
                        "missing_evidence": ["Need external demand."],
                        "next_validation": ["Interview operators."],
                    },
                    "feedback_targets": [],
                    "marked_posts": marked_posts or [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_split_artifacts(self, root: Path) -> None:
        brief_dir = root / "weekly_intelligence_briefs"
        atlas_dir = root / "knowledge_atlas"
        brief_dir.mkdir(parents=True)
        atlas_dir.mkdir(parents=True)
        (brief_dir / "2026-W28.weekly-brief.html").write_text("<!doctype html><title>Brief</title>", encoding="utf-8")
        (atlas_dir / "2026-W28.knowledge-atlas.html").write_text("<!doctype html><title>Atlas</title>", encoding="utf-8")
        (brief_dir / "2026-W28.weekly-brief.json").write_text(
            json.dumps(
                {
                    "artifact_type": "weekly_intelligence_brief",
                    "week_label": "2026-W28",
                    "generated_at": "2026-07-08T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        (atlas_dir / "2026-W28.knowledge-atlas.json").write_text(
            json.dumps(
                {
                    "artifact_type": "knowledge_atlas",
                    "week_label": "2026-W28",
                    "generated_at": "2026-07-08T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )

    def _write_manifest_run(
        self,
        root: Path,
        *,
        run_id: str,
        generated_at: datetime,
        radar_enabled: bool = False,
        failed: bool = False,
        leave_running: bool = False,
        marked_posts: list[dict] | None = None,
        reaction_effect: dict | None = None,
    ) -> tuple[Path, dict]:
        period = resolve_reporting_period(generated_at, week_label="2026-W28")
        manifest = build_initial_manifest(
            period,
            run_id=run_id,
            radar_enabled=radar_enabled,
        )
        run_dir = root / "weekly_intelligence_runs" / run_id
        run_dir.mkdir(parents=True)
        manifest_path = run_dir / "manifest.json"
        if leave_running:
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            return manifest_path, manifest
        manifest = start_stage(manifest, "knowledge_refresh")
        if failed:
            manifest = fail_stage(manifest, "knowledge_refresh", "knowledge refresh failed")
            for name, stage in list(manifest["stages"].items()):
                if stage["enabled"] and stage["status"] == "pending":
                    manifest = transition_stage(
                        manifest,
                        name,
                        "skipped_dependency",
                        error="knowledge refresh failed",
                    )
            manifest = finalize_manifest(manifest)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            return manifest_path, manifest
        manifest = succeed_stage(manifest, "knowledge_refresh")
        manifest = start_stage(manifest, "reaction_sync")
        manifest = succeed_stage(
            manifest,
            "reaction_sync",
            updates={
                "snapshot_ref": f"reaction-snapshot:{run_id}",
                "observed_through": generated_at.isoformat().replace("+00:00", "Z"),
            },
        )
        manifest = start_stage(manifest, "feedback_snapshot")
        manifest = succeed_stage(
            manifest,
            "feedback_snapshot",
            updates={
                "snapshot_id": f"feedback-snapshot:{run_id}",
                "cutoff": manifest["analysis_period_end"],
            },
        )
        frontier_path = run_dir / "bound" / "frontier.json"
        frontier_path.parent.mkdir(parents=True)
        frontier_path.write_text("{}", encoding="utf-8")
        manifest = start_stage(manifest, "frontier_analysis")
        manifest = succeed_stage(
            manifest,
            "frontier_analysis",
            updates={
                "analysis_id": 1,
                "artifact_path": "bound/frontier.json",
                "checksums": {"artifact_path": sha256_file(frontier_path)},
            },
        )
        if radar_enabled:
            seed_path = run_dir / "bound" / "seed.json"
            radar_path = run_dir / "bound" / "radar.json"
            binding_path = run_dir / "bound" / "binding.json"
            seed_path.write_text("[]", encoding="utf-8")
            radar_path.write_text(
                json.dumps(
                    {
                        "result": {
                            "run_id": f"{run_id}-radar",
                            "selected_title": "Manifest candidate",
                            "dossier_status": "investigate",
                            "recommendation": "revisit_with_evidence_gap",
                        }
                    }
                ),
                encoding="utf-8",
            )
            manifest = start_stage(manifest, "radar")
            binding = build_radar_run_binding(
                manifest,
                radar_run_id=f"{run_id}-radar",
                radar_contract_version="mvp_radar.v1",
                radar_schema_version="mvp_of_week.v1",
                seed_export_path="bound/seed.json",
                radar_json_path="bound/radar.json",
                selected_candidate={"title": "Manifest candidate"},
                status_projection={"status": "loaded"},
                created_at=generated_at,
                path_base=run_dir,
                allowed_roots=(run_dir,),
            )
            binding_path.write_text(json.dumps(binding), encoding="utf-8")
            manifest = succeed_stage(
                manifest,
                "radar",
                updates={
                    "radar_run_id": f"{run_id}-radar",
                    "artifact_path": "bound/radar.json",
                    "artifact_sha256": sha256_file(radar_path),
                    "binding_path": "bound/binding.json",
                    "binding_sha256": sha256_file(binding_path),
                    "seed_export_path": "bound/seed.json",
                    "seed_export_sha256": sha256_file(seed_path),
                    "reporting_week": "2026-W28",
                },
            )
        brief_html = run_dir / "bound" / "reader-brief.html"
        brief_json = run_dir / "bound" / "reader-brief.json"
        atlas_html = run_dir / "bound" / "reader-atlas.html"
        atlas_json = run_dir / "bound" / "reader-atlas.json"
        brief_html.write_text("<!doctype html><title>Manifest Brief</title>", encoding="utf-8")
        atlas_html.write_text("<!doctype html><title>Manifest Atlas</title>", encoding="utf-8")
        period_fields = period.to_dict()
        run_identity = {
            "run_id": run_id,
            "manifest_path": str(manifest_path.resolve()),
            "run_status": "complete",
            "partial": False,
            "pipeline_profile": manifest["pipeline_profile"],
            "failed_stages": list(manifest["failed_stages"]),
            "warnings": list(manifest["warnings"]),
        }
        brief_json.write_text(
            json.dumps(
                {
                    "artifact_type": "weekly_intelligence_brief",
                    **period_fields,
                    **run_identity,
                    "html_path": str(brief_html.resolve()),
                    "json_path": str(brief_json.resolve()),
                    "artifact_paths": {
                        "html": str(brief_html.resolve()),
                        "json": str(brief_json.resolve()),
                    },
                    "marked_posts": list(marked_posts or []),
                    **(
                        {"reaction_effect": {**reaction_effect, "surface": "weekly_brief"}}
                        if reaction_effect is not None
                        else {}
                    ),
                    "action_cards": [
                        {
                            "id": "manifest-action",
                            "title": "Manifest scoped action",
                            "next_step": "Use only the bound Brief and Atlas.",
                        }
                    ],
                    "mvp_radar": (
                        {
                            "status": "loaded",
                            "selected_candidate": "Embedded stale candidate",
                            "dossier_status": "investigate",
                            "recommendation": "revisit_with_evidence_gap",
                        }
                        if radar_enabled
                        else {
                            "status": "intentionally_disabled",
                            "disabled": True,
                        }
                    ),
                }
            ),
            encoding="utf-8",
        )
        atlas_json.write_text(
            json.dumps(
                {
                    "artifact_type": "knowledge_atlas",
                    **period_fields,
                    **run_identity,
                    "html_path": str(atlas_html.resolve()),
                    "json_path": str(atlas_json.resolve()),
                    "artifact_paths": {
                        "html": str(atlas_html.resolve()),
                        "json": str(atlas_json.resolve()),
                    },
                    "thread_navigation": {
                        "threads": [
                            {
                                "slug": "manifest-thread",
                                "title": "Manifest bounded thread",
                                "current_understanding": "Historical state frozen in the run Atlas.",
                                "claims": ["Bound evidence only"],
                                "atom_ids": [101],
                                "source_urls": ["https://t.me/ai_lab/101"],
                            }
                        ]
                    },
                    **(
                        {"reaction_effect": {**reaction_effect, "surface": "knowledge_atlas"}}
                        if reaction_effect is not None
                        else {}
                    ),
                }
            ),
            encoding="utf-8",
        )
        manifest = start_stage(manifest, "weekly_brief")
        manifest = succeed_stage(
            manifest,
            "weekly_brief",
            updates={
                "html_path": "bound/reader-brief.html",
                "json_path": "bound/reader-brief.json",
                "checksums": {
                    "html_path": sha256_file(brief_html),
                    "json_path": sha256_file(brief_json),
                },
            },
        )
        manifest = start_stage(manifest, "knowledge_atlas")
        manifest = succeed_stage(
            manifest,
            "knowledge_atlas",
            updates={
                "html_path": "bound/reader-atlas.html",
                "json_path": "bound/reader-atlas.json",
                "checksums": {
                    "html_path": sha256_file(atlas_html),
                    "json_path": sha256_file(atlas_json),
                },
            },
        )
        manifest = finalize_manifest(manifest)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path, manifest

    def test_facade_instantiates_without_external_api_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facade = PersonalIntelligenceFacade(
                settings=self._settings(root),
                output_root=root,
                now=datetime(2026, 7, 8, tzinfo=timezone.utc),
            )
            current = facade.get_current_week_label()

        self.assertEqual(current["status"], "ok")
        self.assertEqual(current["week_label"], "2026-W28")
        self.assertEqual(current["source"], "date")

    def test_missing_workbook_returns_missing_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            result = facade.get_workbook_summary("2026-W28")

        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["week_label"], "2026-W28")
        self.assertEqual(result["artifact_paths"], {"html": None, "json": None})

    def test_missing_mvp_radar_returns_missing_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            result = facade.get_mvp_radar_status("2026-W28")

        self.assertEqual(result["status"], "missing")
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["missing_evidence"], [])

    def test_missing_feedback_table_returns_missing_or_empty_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Path(root / "agent.db").touch()
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            result = facade.get_feedback_summary("2026-W28")

        self.assertIn(result["status"], {"missing", "empty"})
        self.assertEqual(result["counts"], {})

    def test_no_mutation_methods_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)

        for method_name in [
            "edit_code",
            "run_codex",
            "edit_config",
            "mutate_profile",
            "mutate_projects",
        ]:
            self.assertFalse(hasattr(facade, method_name), method_name)

    def test_list_marked_posts_does_not_treat_no_reaction_as_negative(self):
        marked_posts = [
            {
                "post_id": 101,
                "channel_username": "ai_lab",
                "content": "Interesting source that has no visible reaction value in the sidecar.",
                "source_url": "https://t.me/ai_lab/101",
                "reaction": None,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root, marked_posts=marked_posts)
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            result = facade.list_marked_posts("2026-W28")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["items"][0]["reaction"], None)
        self.assertEqual(result["items"][0]["marked_reason_guess"], None)
        self.assertNotEqual(result["items"][0]["marked_reason_guess"], "negative")

    def test_get_workbook_summary_returns_stable_keys(self):
        expected_keys = {
            "status",
            "week_label",
            "title",
            "artifact_type",
            "generated_at",
            "decision_brief",
            "strong_signals",
            "actions",
            "project_actions",
            "mvp_status",
            "mvp_radar_gate",
            "artifact_paths",
            "artifact_status",
            "message",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            result = facade.get_workbook_summary("2026-W28")

        self.assertEqual(set(result.keys()), expected_keys)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["strong_signals"])
        self.assertEqual(result["actions"][0]["why_selected"], "Selected for source-backed utility with confirmed feedback.")
        self.assertEqual(result["actions"][0]["ranking_factors"][0]["label"], "feedback_score")
        self.assertEqual(result["mvp_radar_gate"]["decision"], "do_not_build")
        self.assertIn(result["artifact_status"]["status"], {"partial", "missing"})

    def test_get_artifact_status_names_stale_split_artifacts_and_missing_radar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_split_artifacts(root)
            facade = PersonalIntelligenceFacade(
                settings=self._settings(root),
                output_root=root,
                now=datetime(2026, 7, 15, tzinfo=timezone.utc),
            )
            result = facade.get_artifact_status("2026-W28")

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["current_week_label"], "2026-W29")
        self.assertEqual(result["weekly_brief"]["status"], "stale")
        self.assertEqual(result["knowledge_atlas"]["status"], "stale")
        self.assertEqual(result["mvp_radar"]["status"], "missing")
        self.assertEqual(result["mvp_radar_gate"]["decision"], "do_not_build")
        self.assertEqual(result["evidence_boundaries"]["market_context"], "context_only")
        self.assertIn("Weekly Brief", result["message"])
        self.assertIn("Knowledge Atlas", result["message"])
        self.assertIn("MVP Radar", result["message"])
        self.assertIn("weekly_intelligence_brief_json", result["artifact_paths"])

    def test_finalized_manifest_is_freshness_authority_for_completed_week(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path, _manifest = self._write_manifest_run(
                root,
                run_id="pi-completed-run",
                generated_at=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
            )
            facade = PersonalIntelligenceFacade(
                settings=self._settings(root),
                output_root=root,
                now=datetime(2026, 7, 15, tzinfo=timezone.utc),
            )
            result = facade.get_artifact_status("2026-W28")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["run_status"], "complete")
        self.assertEqual(result["run_id"], "pi-completed-run")
        self.assertEqual(result["manifest_path"], str(manifest_path.resolve()))
        self.assertEqual(result["current_week_label"], "2026-W29")
        self.assertEqual(result["weekly_brief"]["status"], "current")
        self.assertEqual(result["knowledge_atlas"]["status"], "current")
        self.assertEqual(result["mvp_radar"]["status"], "disabled")
        self.assertEqual(result["mvp_radar_gate"]["radar_artifact_status"], "disabled")
        self.assertIn(RADAR_DISABLED_DISCLOSURE_RU, result["message"])

    def test_manifest_paths_are_authoritative_not_week_filename_adjacency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path, _manifest = self._write_manifest_run(
                root,
                run_id="pi-bound-path-run",
                generated_at=datetime(2026, 7, 13, 7, 3, tzinfo=timezone.utc),
                radar_enabled=True,
            )
            self._write_split_artifacts(root)
            facade = PersonalIntelligenceFacade(
                settings=self._settings(root),
                output_root=root,
                now=datetime(2026, 7, 15, tzinfo=timezone.utc),
            )
            result = facade.get_artifact_status("2026-W28")
            radar = facade.get_mvp_radar_status("2026-W28")

        run_dir = manifest_path.parent
        self.assertEqual(
            result["weekly_brief"]["json_path"],
            str(run_dir / "bound" / "reader-brief.json"),
        )
        self.assertEqual(
            result["mvp_radar"]["json_path"],
            str(run_dir / "bound" / "radar.json"),
        )
        self.assertEqual(radar["candidate"], "Manifest candidate")
        self.assertEqual(radar["run_id"], "pi-bound-path-run")

    def test_manifest_reader_sidecar_requires_full_identity_and_bound_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path, _manifest = self._write_manifest_run(
                root,
                run_id="pi-reader-identity",
                generated_at=datetime(2026, 7, 13, 7, 4, tzinfo=timezone.utc),
            )
            run_dir = manifest_path.parent
            brief_json = run_dir / "bound" / "reader-brief.json"
            payload = json.loads(brief_json.read_text(encoding="utf-8"))
            payload["pipeline_profile"] = "tampered-profile"
            brief_json.write_text(json.dumps(payload), encoding="utf-8")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["stages"]["weekly_brief"]["checksums"]["json_path"] = sha256_file(
                brief_json
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            tampered = facade.get_workbook_summary("2026-W28")

            payload["pipeline_profile"] = manifest["pipeline_profile"]
            brief_json.write_text(json.dumps(payload), encoding="utf-8")
            manifest["stages"]["weekly_brief"]["checksums"]["json_path"] = sha256_file(
                brief_json
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            (run_dir / "bound" / "reader-brief.html").unlink()
            missing_html = facade.get_workbook_summary("2026-W28")

        self.assertEqual(tampered["status"], "missing")
        self.assertEqual(missing_html["status"], "missing")

    def test_manifest_atlas_identity_tamper_blocks_historical_thread_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path, _manifest = self._write_manifest_run(
                root,
                run_id="pi-atlas-identity",
                generated_at=datetime(2026, 7, 13, 7, 4, 30, tzinfo=timezone.utc),
            )
            atlas_json = manifest_path.parent / "bound" / "reader-atlas.json"
            payload = json.loads(atlas_json.read_text(encoding="utf-8"))
            payload["analysis_period_end"] = "2026-07-20T00:00:00Z"
            atlas_json.write_text(json.dumps(payload), encoding="utf-8")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["stages"]["knowledge_atlas"]["checksums"]["json_path"] = sha256_file(
                atlas_json
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            with patch.object(
                facade,
                "_idea_threads_from_db",
                side_effect=AssertionError("live thread fallback must not run"),
            ):
                result = facade.search_idea_threads("Historical state", week_label="2026-W28")

        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["items"], [])

    def test_manifest_radar_rejects_raw_run_id_tamper_without_embedded_or_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path, _manifest = self._write_manifest_run(
                root,
                run_id="pi-radar-tamper",
                generated_at=datetime(2026, 7, 13, 7, 5, tzinfo=timezone.utc),
                radar_enabled=True,
            )
            self._write_workbook(root)
            run_dir = manifest_path.parent
            raw_path = run_dir / "bound" / "radar.json"
            binding_path = run_dir / "bound" / "binding.json"
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            raw["result"]["run_id"] = "different-radar-run"
            raw["result"]["selected_title"] = "Tampered candidate"
            raw_path.write_text(json.dumps(raw), encoding="utf-8")
            binding = json.loads(binding_path.read_text(encoding="utf-8"))
            binding["radar_json_ref"]["sha256"] = sha256_file(raw_path)
            binding_path.write_text(json.dumps(binding), encoding="utf-8")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            radar_stage = manifest["stages"]["radar"]
            radar_stage["artifact_sha256"] = sha256_file(raw_path)
            radar_stage["binding_sha256"] = sha256_file(binding_path)
            manifest["radar_json_ref"]["sha256"] = radar_stage["artifact_sha256"]
            manifest["radar_json_ref"]["binding_sha256"] = radar_stage["binding_sha256"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            result = facade.get_mvp_radar_status("2026-W28")

        self.assertEqual(result["status"], "missing")
        self.assertIsNone(result["candidate"])
        self.assertNotEqual(result["candidate"], "Embedded stale candidate")
        self.assertNotEqual(result["candidate"], "LLM Guardrail Watchdog")

    def test_manifest_empty_marked_posts_are_authoritative_over_live_or_legacy_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_manifest_run(
                root,
                run_id="pi-empty-marked-posts",
                generated_at=datetime(2026, 7, 13, 7, 6, tzinfo=timezone.utc),
                marked_posts=[],
            )
            self._write_workbook(
                root,
                marked_posts=[
                    {
                        "post_id": 999,
                        "content": "Legacy marked post must not leak into the manifest week.",
                    }
                ],
            )
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            with patch.object(
                facade,
                "_marked_post_rows",
                side_effect=AssertionError("live DB fallback must not run"),
            ):
                result = facade.list_marked_posts("2026-W28")

        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["items"], [])

    def test_manifest_historical_thread_search_and_detail_never_fall_back_to_live_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_manifest_run(
                root,
                run_id="pi-historical-threads",
                generated_at=datetime(2026, 7, 13, 7, 7, tzinfo=timezone.utc),
            )
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            with patch.object(
                facade,
                "_idea_threads_from_db",
                side_effect=AssertionError("live thread search must not run"),
            ), patch.object(
                facade,
                "_idea_thread_detail_from_db",
                side_effect=AssertionError("live thread detail must not run"),
            ):
                search = facade.search_idea_threads("Historical state", week_label="2026-W28")
                detail = facade.get_idea_thread("manifest-thread", week_label="2026-W28")

        self.assertEqual(search["status"], "ok")
        self.assertEqual(search["items"][0]["slug"], "manifest-thread")
        self.assertEqual(detail["status"], "ok")
        self.assertEqual(detail["title"], "Manifest bounded thread")

    def test_manifest_item_search_uses_only_bound_brief_and_atlas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_manifest_run(
                root,
                run_id="pi-historical-items",
                generated_at=datetime(2026, 7, 13, 7, 8, tzinfo=timezone.utc),
            )
            self._write_workbook(root)
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            with patch(
                "assistant.pi_facade.build_retrieval_items",
                side_effect=AssertionError("legacy and DB retrieval must not run"),
            ):
                bounded = facade.search_intelligence_items(
                    "Manifest scoped action",
                    filters={"week_label": "2026-W28"},
                    limit=5,
                )
                legacy = facade.search_intelligence_items(
                    "LLM Guardrail Watchdog",
                    filters={"week_label": "2026-W28"},
                    limit=5,
                )

        self.assertEqual(bounded["status"], "ok")
        self.assertTrue(any(item["item_type"] == "action_card" for item in bounded["items"]))
        self.assertEqual(legacy["status"], "empty")
        self.assertEqual(legacy["items"], [])

    def test_manifest_reaction_receipt_is_available_through_bound_retrieval_only(self):
        run_id = "pi-reaction-receipt"
        receipt = {
            "schema_version": "reaction_personalization.v1",
            "run_id": run_id,
            "surface": "weekly_brief",
            "reporting_week": "2026-W28",
            "analysis_period_start": "2026-07-06T00:00:00Z",
            "analysis_period_end": "2026-07-13T00:00:00Z",
            "snapshot_ref": f"reaction-snapshot:{run_id}",
            "snapshot_status": "unavailable",
            "status": "unavailable",
            "reader_summary_ru": (
                "Синхронизация реакций не завершена. Персонализация по реакциям "
                "для этого запуска не применялась."
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
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_manifest_run(
                root,
                run_id=run_id,
                generated_at=datetime(2026, 7, 13, 7, 8, tzinfo=timezone.utc),
                reaction_effect=receipt,
            )
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            with patch(
                "assistant.pi_facade.build_retrieval_items",
                side_effect=AssertionError("legacy and DB retrieval must not run"),
            ):
                result = facade.search_intelligence_items(
                    "reaction personalization receipt",
                    filters={"week_label": "2026-W28"},
                    limit=5,
                )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(any(item["item_type"] == "reaction_effect" for item in result["items"]))

    def test_foreign_nested_reaction_receipt_invalidates_bound_reader_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path, manifest = self._write_manifest_run(
                root,
                run_id="pi-local-receipt-run",
                generated_at=datetime(2026, 7, 13, 7, 8, tzinfo=timezone.utc),
                reaction_effect=self._unavailable_reaction_effect("foreign-run"),
            )
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)

            status = facade.get_artifact_status("2026-W28")
            workbook = facade.get_workbook_summary("2026-W28")
            retrieval = facade.search_intelligence_items(
                "reaction personalization receipt",
                filters={"week_label": "2026-W28"},
                limit=5,
            )

        self.assertEqual(status["status"], "ok")
        self.assertEqual(status["run_id"], manifest["run_id"])
        self.assertEqual(status["manifest_path"], str(manifest_path.resolve()))
        self.assertEqual(workbook["status"], "missing")
        self.assertEqual(retrieval["status"], "empty")
        self.assertFalse(
            any(item.get("item_type") == "reaction_effect" for item in retrieval["items"])
        )

    def test_uncontained_manifest_symlink_is_invalid_and_blocks_fallback(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as external:
            root = Path(tmp)
            self._write_manifest_run(
                root,
                run_id="pi-old-2026-W28",
                generated_at=datetime(2026, 7, 13, 7, 0, tzinfo=timezone.utc),
            )
            external_root = Path(external)
            external_manifest, _external = self._write_manifest_run(
                external_root,
                run_id="external-run",
                generated_at=datetime(2026, 7, 13, 8, 0, tzinfo=timezone.utc),
            )
            lexical_dir = root / "weekly_intelligence_runs" / "newer-2026-W28"
            lexical_dir.mkdir()
            lexical_manifest = lexical_dir / "manifest.json"
            lexical_manifest.symlink_to(external_manifest)
            self._write_split_artifacts(root)
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)

            status = facade.get_artifact_status("2026-W28")
            workbook = facade.get_workbook_summary("2026-W28")

        self.assertEqual(status["status"], "invalid")
        self.assertEqual(status["manifest_path"], str(lexical_manifest.absolute()))
        self.assertEqual(workbook["status"], "missing")

    def test_newest_failed_manifest_blocks_older_success_and_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_path, _old = self._write_manifest_run(
                root,
                run_id="pi-old-complete",
                generated_at=datetime(2026, 7, 13, 7, 0, tzinfo=timezone.utc),
            )
            failed_path, _failed = self._write_manifest_run(
                root,
                run_id="pi-new-failed",
                generated_at=datetime(2026, 7, 13, 8, 0, tzinfo=timezone.utc),
                failed=True,
            )
            self._write_split_artifacts(root)
            facade = PersonalIntelligenceFacade(
                settings=self._settings(root),
                output_root=root,
            )
            status = facade.get_artifact_status("2026-W28")
            workbook = facade.get_workbook_summary("2026-W28")

        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["run_id"], "pi-new-failed")
        self.assertEqual(status["manifest_path"], str(failed_path.resolve()))
        self.assertNotEqual(status["manifest_path"], str(old_path.resolve()))
        self.assertEqual(status["weekly_brief"]["status"], "failed")
        self.assertIsNone(status["weekly_brief"]["json_path"])
        self.assertEqual(workbook["status"], "missing")

    def test_running_manifest_blocks_v1_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_manifest_run(
                root,
                run_id="pi-running",
                generated_at=datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc),
                leave_running=True,
            )
            self._write_split_artifacts(root)
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            status = facade.get_artifact_status("2026-W28")

        self.assertEqual(status["status"], "running")
        self.assertEqual(status["weekly_brief"]["status"], "pending")
        self.assertIsNone(status["weekly_brief"]["json_path"])

    def test_newer_valid_generation_wins_if_older_manifest_is_touched_later(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_path, _old = self._write_manifest_run(
                root,
                run_id="pi-old-late-finish",
                generated_at=datetime(2026, 7, 13, 7, 0, tzinfo=timezone.utc),
            )
            new_path, _new = self._write_manifest_run(
                root,
                run_id="pi-new-generation",
                generated_at=datetime(2026, 7, 13, 8, 0, tzinfo=timezone.utc),
            )
            old_path.touch()
            facade = PersonalIntelligenceFacade(
                settings=self._settings(root),
                output_root=root,
            )

            current = facade.get_current_week_label()
            status = facade.get_artifact_status("2026-W28")

        self.assertEqual(current["status"], "ok")
        self.assertEqual(current["run_id"], "pi-new-generation")
        self.assertEqual(status["status"], "ok")
        self.assertEqual(status["run_id"], "pi-new-generation")
        self.assertEqual(status["manifest_path"], str(new_path.resolve()))
        self.assertNotEqual(status["manifest_path"], str(old_path.resolve()))

    def test_invalid_newest_manifest_blocks_older_success_and_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_path, _old = self._write_manifest_run(
                root,
                run_id="pi-old-valid",
                generated_at=datetime(2026, 7, 13, 7, 0, tzinfo=timezone.utc),
            )
            invalid_path, _new = self._write_manifest_run(
                root,
                run_id="pi-new-invalid",
                generated_at=datetime(2026, 7, 13, 8, 0, tzinfo=timezone.utc),
            )
            invalid = json.loads(invalid_path.read_text(encoding="utf-8"))
            invalid["pipeline_profile"] = "corrupt-profile"
            invalid["generated_at"] = "0000"
            invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
            self._write_split_artifacts(root)
            facade = PersonalIntelligenceFacade(
                settings=self._settings(root),
                output_root=root,
            )

            current = facade.get_current_week_label()
            status = facade.get_artifact_status("2026-W28")
            workbook = facade.get_workbook_summary("2026-W28")

        self.assertEqual(current["status"], "invalid")
        self.assertEqual(current["run_id"], "pi-new-invalid")
        self.assertEqual(status["status"], "invalid")
        self.assertEqual(status["run_id"], "pi-new-invalid")
        self.assertEqual(status["manifest_path"], str(invalid_path.resolve()))
        self.assertNotEqual(status["manifest_path"], str(old_path.resolve()))
        self.assertEqual(status["weekly_brief"]["status"], "invalid")
        self.assertIsNone(status["weekly_brief"]["json_path"])
        self.assertEqual(workbook["status"], "missing")

    def test_invalid_conflicting_week_identity_blocks_old_explicit_week_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_path, _old = self._write_manifest_run(
                root,
                run_id="pi-old-week-identity",
                generated_at=datetime(2026, 7, 13, 7, 0, tzinfo=timezone.utc),
            )
            invalid_path, _new = self._write_manifest_run(
                root,
                run_id="pi-new-week-conflict",
                generated_at=datetime(2026, 7, 13, 8, 0, tzinfo=timezone.utc),
            )
            invalid = json.loads(invalid_path.read_text(encoding="utf-8"))
            invalid["reporting_week"] = "2026-W29"
            invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
            facade = PersonalIntelligenceFacade(
                settings=self._settings(root),
                output_root=root,
            )

            status = facade.get_artifact_status("2026-W28")

        self.assertEqual(status["status"], "invalid")
        self.assertEqual(status["week_label"], "2026-W28")
        self.assertEqual(status["run_id"], "pi-new-week-conflict")
        self.assertEqual(status["manifest_path"], str(invalid_path.resolve()))
        self.assertNotEqual(status["manifest_path"], str(old_path.resolve()))
        self.assertEqual(status["weekly_brief"]["status"], "invalid")

    def test_invalid_only_manifest_blocks_v1_brief_and_radar_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            invalid_path, _manifest = self._write_manifest_run(
                root,
                run_id="pi-only-invalid",
                generated_at=datetime(2026, 7, 13, 8, 0, tzinfo=timezone.utc),
            )
            invalid_path.write_text("{malformed", encoding="utf-8")
            self._write_split_artifacts(root)
            facade = PersonalIntelligenceFacade(
                settings=self._settings(root),
                output_root=root,
            )

            status = facade.get_artifact_status("2026-W28")
            radar = facade.get_mvp_radar_status("2026-W28")
            sections = facade.get_workbook_sections("2026-W28")
            default_status = facade.get_artifact_status()
            default_radar = facade.get_mvp_radar_status()
            default_marked = facade.list_marked_posts()

        self.assertEqual(status["status"], "invalid")
        self.assertEqual(status["run_id"], "pi-only-invalid")
        self.assertEqual(status["knowledge_atlas"]["status"], "invalid")
        self.assertEqual(status["artifact_paths"], {})
        self.assertEqual(radar["status"], "invalid")
        self.assertIsNone(radar["candidate"])
        self.assertEqual(radar["run_id"], "pi-only-invalid")
        self.assertEqual(sections["status"], "missing")
        self.assertEqual(sections["sections"], [])
        self.assertEqual(default_status["status"], "invalid")
        self.assertEqual(default_status["run_id"], "pi-only-invalid")
        self.assertEqual(default_radar["status"], "invalid")
        self.assertEqual(default_radar["run_id"], "pi-only-invalid")
        self.assertEqual(default_marked["status"], "missing")
        self.assertIn("authoritative", default_marked["message"])

    def test_get_action_statuses_keeps_missing_feedback_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            Path(root / "agent.db").touch()
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            result = facade.get_action_statuses("2026-W28")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["items"][0]["status"], "unknown")
        self.assertEqual(result["counts"]["unknown"], 1)
        self.assertEqual(result["counts"]["not_interested"], 0)

    def test_search_intelligence_items_reports_curated_fts_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            result = facade.search_intelligence_items("радар рынка", limit=5)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["retrieval_decision"]["mode"], "curated_deterministic_plus_sqlite_fts")
        self.assertEqual(result["retrieval_decision"]["raw_telegram_status"], "disabled")
        self.assertTrue(any(item["item_type"] == "mvp_dossier" for item in result["items"]))

    def test_strategy_reviewer_uses_bound_weekly_run_root_and_exposes_proposals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            weekly_run_root = root / "custom-weekly-runs"
            weekly_run_root.mkdir()
            with sqlite3.connect(root / "agent.db") as connection:
                connection.execute("CREATE TABLE ai_report_feedback_events (id INTEGER)")
            proposal = {
                "proposal_id": "reaction-pattern:test",
                "status": "unapproved",
                "applied": False,
            }
            review = {
                "generated_at": "2026-07-13T08:00:00Z",
                "suggestions": {
                    "keep": [],
                    "change": [],
                    "demote": [],
                    "test_next_week": [],
                },
                "memory_only_updates": [],
                "approval_required": [],
                "codex_tasks": [],
                "reaction_pattern_proposals": [proposal],
                "risks": [],
                "mutation_policy": {"profile": "do_not_modify"},
                "feedback_summary": {},
            }
            facade = PersonalIntelligenceFacade(
                settings=self._settings(root),
                weekly_run_root=weekly_run_root,
            )
            with patch(
                "assistant.pi_facade.build_strategy_review",
                return_value=review,
            ) as build_review:
                result = facade.get_strategy_reviewer_notes("2026-W28")

        self.assertEqual(result["reaction_pattern_proposals"], [proposal])
        self.assertEqual(
            build_review.call_args.kwargs["weekly_run_root"],
            weekly_run_root,
        )


if __name__ == "__main__":
    unittest.main()
