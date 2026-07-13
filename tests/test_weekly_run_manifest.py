import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from output.reporting_period import PARTIAL_ISO_WEEK, resolve_reporting_period
from output.weekly_run_manifest import (
    FAILED,
    REACTION_SNAPSHOT_PATH,
    REACTION_SNAPSHOT_SCHEMA_VERSION,
    ManifestExistsError,
    RadarBindingError,
    TerminalManifestError,
    WeeklyRunManifestError,
    append_warning,
    build_initial_manifest,
    build_radar_run_binding,
    create_manifest,
    fail_stage,
    finalize_manifest,
    load_bound_reaction_snapshot,
    load_manifest,
    sanitize_error,
    sha256_file,
    start_stage,
    succeed_stage,
    transition_stage,
    validate_manifest,
    validate_radar_run_binding,
    verify_file_checksum,
    write_manifest,
    write_radar_run_binding,
)


RUN_AT = datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)


class TestWeeklyRunManifest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.period = resolve_reporting_period(RUN_AT)

    def tearDown(self):
        self.temporary.cleanup()

    def _file(self, run_dir: Path, relative: str, content: str = "{}") -> str:
        path = run_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return relative

    def _reader_sidecar(
        self,
        manifest,
        run_dir: Path,
        *,
        html_path: str,
        json_path: str,
        run_status: str,
    ) -> str:
        failed_stages = list(manifest["failed_stages"])
        if (
            run_status == "partial"
            and manifest["stage_policy"]["radar"]["enabled"]
            and manifest["stages"]["radar"]["status"] == "pending"
        ):
            failed_stages = [*failed_stages, "radar"]
        payload = {
            field: manifest[field]
            for field in (
                "run_id",
                "run_date",
                "generated_at",
                "reporting_week",
                "week_label",
                "period_mode",
                "analysis_period_start",
                "analysis_period_end",
                "pipeline_profile",
            )
        }
        payload.update(
            {
                "manifest_path": str((run_dir / "manifest.json").resolve()),
                "run_status": run_status,
                "partial": run_status == "partial",
                "failed_stages": failed_stages,
                "warnings": list(manifest["warnings"]),
                "html_path": str((run_dir / html_path).resolve()),
                "json_path": str((run_dir / json_path).resolve()),
                "artifact_paths": {
                    "html": str((run_dir / html_path).resolve()),
                    "json": str((run_dir / json_path).resolve()),
                },
            }
        )
        return json.dumps(payload, ensure_ascii=False)

    def _finish_successfully(
        self,
        manifest,
        run_dir: Path,
        *,
        radar_enabled=True,
        atlas_succeeds=True,
        feedback_succeeds=True,
    ):
        manifest = start_stage(manifest, "knowledge_refresh")
        manifest = succeed_stage(
            manifest,
            "knowledge_refresh",
            updates={"record_counts": {"atoms": 0, "threads": 0}},
        )
        manifest = start_stage(manifest, "reaction_sync")
        manifest = succeed_stage(
            manifest,
            "reaction_sync",
            updates={
                "snapshot_ref": f"reaction-snapshot:{manifest['run_id']}",
                "observed_through": "2026-07-13T07:03:00Z",
                "record_counts": {"posts_checked": 0},
            },
        )
        manifest = start_stage(manifest, "feedback_snapshot")
        if feedback_succeeds:
            manifest = succeed_stage(
                manifest,
                "feedback_snapshot",
                updates={
                    "snapshot_id": f"feedback-snapshot:{manifest['run_id']}",
                    "cutoff": manifest["analysis_period_end"],
                    "confirmed_event_count": 0,
                    "pending_event_count": 0,
                },
            )
        else:
            manifest = fail_stage(
                manifest,
                "feedback_snapshot",
                RuntimeError("feedback snapshot unavailable"),
            )
        frontier = self._file(run_dir, "frontier/frontier.json")
        manifest = start_stage(manifest, "frontier_analysis")
        manifest = succeed_stage(
            manifest,
            "frontier_analysis",
            updates={
                "analysis_id": 9,
                "artifact_path": frontier,
                "checksums": {"artifact_path": sha256_file(run_dir / frontier)},
            },
        )
        if radar_enabled:
            seed = self._file(run_dir, "radar/seeds.json", "[]")
            raw = self._file(
                run_dir,
                "radar/raw.json",
                json.dumps({"result": {"run_id": "radar-test-run"}}),
            )
            market_lens = self._file(run_dir, "radar/market-lens.json")
            manifest = start_stage(manifest, "radar")
            binding = build_radar_run_binding(
                manifest,
                radar_run_id="radar-test-run",
                radar_contract_version="tra-radar-intelligence-contract.v1",
                radar_schema_version="mvp_of_week.v1",
                seed_export_path=seed,
                radar_json_path=raw,
                selected_candidate=None,
                status_projection={"status": "no_candidate"},
                path_base=run_dir,
                allowed_roots=(run_dir,),
            )
            binding_path = run_dir / "radar" / "binding.json"
            write_radar_run_binding(
                binding_path,
                binding,
                manifest=manifest,
                path_base=run_dir,
                allowed_roots=(run_dir,),
            )
            manifest = succeed_stage(
                manifest,
                "radar",
                updates={
                    "radar_run_id": "radar-test-run",
                    "artifact_path": raw,
                    "artifact_sha256": sha256_file(run_dir / raw),
                    "binding_path": "radar/binding.json",
                    "binding_sha256": sha256_file(binding_path),
                    "seed_export_path": seed,
                    "seed_export_sha256": sha256_file(run_dir / seed),
                    "reporting_week": manifest["reporting_week"],
                    "market_lens_path": market_lens,
                    "dependency_refs": {"market_lens_path": market_lens},
                    "artifact_refs": {"binding_path": "radar/binding.json"},
                    "checksums": {
                        "market_lens_path": sha256_file(run_dir / market_lens)
                    },
                },
            )
        brief_html = self._file(run_dir, "brief/brief.html", "brief")
        brief_json = "brief/brief.json"
        will_be_partial = bool(manifest["partial"]) or (
            manifest["stage_policy"]["radar"]["enabled"] and not radar_enabled
        ) or not atlas_succeeds
        expected_status = "partial" if will_be_partial else "complete"
        self._file(
            run_dir,
            brief_json,
            self._reader_sidecar(
                manifest,
                run_dir,
                html_path=brief_html,
                json_path=brief_json,
                run_status=expected_status,
            ),
        )
        manifest = start_stage(manifest, "weekly_brief")
        manifest = succeed_stage(
            manifest,
            "weekly_brief",
            updates={
                "html_path": brief_html,
                "json_path": brief_json,
                "checksums": {
                    "html_path": sha256_file(run_dir / brief_html),
                    "json_path": sha256_file(run_dir / brief_json),
                },
            },
        )
        atlas_html = self._file(run_dir, "atlas/atlas.html", "atlas")
        atlas_json = "atlas/atlas.json"
        self._file(
            run_dir,
            atlas_json,
            self._reader_sidecar(
                manifest,
                run_dir,
                html_path=atlas_html,
                json_path=atlas_json,
                run_status=expected_status,
            ),
        )
        manifest = start_stage(manifest, "knowledge_atlas")
        if not atlas_succeeds:
            manifest = fail_stage(
                manifest,
                "knowledge_atlas",
                "renderer unavailable",
            )
            brief_sidecar_path = run_dir / brief_json
            brief_sidecar = json.loads(
                brief_sidecar_path.read_text(encoding="utf-8")
            )
            brief_sidecar["failed_stages"] = list(manifest["failed_stages"])
            brief_sidecar_path.write_text(
                json.dumps(brief_sidecar),
                encoding="utf-8",
            )
            manifest["stages"]["weekly_brief"]["checksums"][
                "json_path"
            ] = sha256_file(brief_sidecar_path)
            return manifest
        return succeed_stage(
            manifest,
            "knowledge_atlas",
            updates={
                "html_path": atlas_html,
                "json_path": atlas_json,
                "checksums": {
                    "html_path": sha256_file(run_dir / atlas_html),
                    "json_path": sha256_file(run_dir / atlas_json),
                },
            },
        )

    def _bind_empty_verified_reaction_snapshot(self, manifest, run_dir: Path):
        changed = copy.deepcopy(manifest)
        reaction_stage = changed["stages"]["reaction_sync"]
        observed_through = reaction_stage["started_at"]
        payload = {
            "schema_version": REACTION_SNAPSHOT_SCHEMA_VERSION,
            **{
                field: changed[field]
                for field in (
                    "run_date",
                    "generated_at",
                    "reporting_week",
                    "week_label",
                    "period_mode",
                    "analysis_period_start",
                    "analysis_period_end",
                )
            },
            "run_id": changed["run_id"],
            "snapshot_ref": reaction_stage["snapshot_ref"],
            "observed_through": observed_through,
            "coverage": {
                "candidate_count": 0,
                "checked_count": 0,
                "coverage_complete": True,
                "visibility_verified": True,
            },
            "observed_personal_posts": [],
        }
        snapshot_path = run_dir / REACTION_SNAPSHOT_PATH
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(payload), encoding="utf-8")
        reaction_stage["observed_through"] = observed_through
        reaction_stage["record_counts"] = {
            "candidate_count": 0,
            "checked_count": 0,
            "posts_checked": 0,
            "observed_personal_posts": 0,
            "posts_with_reactions": 0,
            "personal_reaction_events_detected": 0,
            "errors": 0,
        }
        reaction_stage["artifact_refs"] = {
            "snapshot_path": REACTION_SNAPSHOT_PATH,
        }
        reaction_stage["checksums"] = {
            "snapshot_path": sha256_file(snapshot_path),
        }
        return changed

    def _bind_verified_reaction_posts(self, manifest, run_dir: Path, posts):
        changed = self._bind_empty_verified_reaction_snapshot(manifest, run_dir)
        snapshot_path = run_dir / REACTION_SNAPSHOT_PATH
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        payload["coverage"] = {
            "candidate_count": len(posts),
            "checked_count": len(posts),
            "coverage_complete": True,
            "visibility_verified": True,
        }
        payload["observed_personal_posts"] = posts
        snapshot_path.write_text(json.dumps(payload), encoding="utf-8")
        event_count = sum(len(post["raw_emojis"]) for post in posts)
        changed["stages"]["reaction_sync"]["record_counts"] = {
            "candidate_count": len(posts),
            "checked_count": len(posts),
            "posts_checked": len(posts),
            "observed_personal_posts": len(posts),
            "posts_with_reactions": len(posts),
            "personal_reaction_events_detected": event_count,
            "errors": 0,
        }
        changed["stages"]["reaction_sync"]["checksums"][
            "snapshot_path"
        ] = sha256_file(snapshot_path)
        return changed

    def _bound_reaction_manifest(self, *, run_id="bound-reaction-run"):
        manifest = build_initial_manifest(
            self.period,
            run_id=run_id,
            radar_enabled=False,
        )
        run_dir = self.root / run_id
        run_dir.mkdir()
        manifest = start_stage(
            manifest,
            "reaction_sync",
            at="2026-07-13T07:02:53Z",
        )
        snapshot_ref = f"reaction-snapshot:{run_id}"
        observed_through = "2026-07-13T07:02:54Z"
        payload = {
            "schema_version": REACTION_SNAPSHOT_SCHEMA_VERSION,
            **self.period.to_dict(),
            "run_id": run_id,
            "snapshot_ref": snapshot_ref,
            "observed_through": observed_through,
            "coverage": {
                "candidate_count": 2,
                "checked_count": 2,
                "coverage_complete": True,
                "visibility_verified": True,
            },
            "observed_personal_posts": [
                {
                    "post_id": 41,
                    "channel_username": "@source",
                    "message_id": 77,
                    "posted_at": "2026-07-12T23:59:59Z",
                    "raw_emojis": ["🔥"],
                }
            ],
        }
        snapshot_path = run_dir / REACTION_SNAPSHOT_PATH
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(payload), encoding="utf-8")
        manifest = succeed_stage(
            manifest,
            "reaction_sync",
            at="2026-07-13T07:02:55Z",
            updates={
                "snapshot_ref": snapshot_ref,
                "observed_through": observed_through,
                "record_counts": {
                    "candidate_count": 2,
                    "checked_count": 2,
                    "posts_checked": 2,
                    "observed_personal_posts": 1,
                    "posts_with_reactions": 1,
                    "personal_reaction_events_detected": 1,
                    "errors": 0,
                },
                "artifact_refs": {"snapshot_path": REACTION_SNAPSHOT_PATH},
                "checksums": {"snapshot_path": sha256_file(snapshot_path)},
            },
        )
        return manifest, run_dir, snapshot_path, payload

    def _with_reader_reaction_effects(
        self,
        manifest,
        run_dir: Path,
        *,
        include_brief=True,
        include_atlas=True,
        brief_updates=None,
        atlas_updates=None,
    ):
        changed = copy.deepcopy(manifest)
        base_effect = {
            "schema_version": "reaction_personalization.v1",
            "run_id": manifest["run_id"],
            "reporting_week": manifest["reporting_week"],
            "analysis_period_start": manifest["analysis_period_start"],
            "analysis_period_end": manifest["analysis_period_end"],
            "snapshot_ref": manifest["stages"]["reaction_sync"]["snapshot_ref"],
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
        variants = (
            ("weekly_brief", "weekly_brief", include_brief, brief_updates or {}),
            ("knowledge_atlas", "knowledge_atlas", include_atlas, atlas_updates or {}),
        )
        for stage_name, surface, include, updates in variants:
            if manifest["stages"][stage_name]["status"] != "succeeded":
                continue
            sidecar_path = run_dir / manifest["stages"][stage_name]["json_path"]
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            sidecar.pop("reaction_effect", None)
            if include:
                effect = {
                    **base_effect,
                    "surface": surface,
                    **updates,
                }
                if (
                    "reader_summary_ru" not in updates
                    and effect["status"] == "no_eligible_reactions"
                    and effect["snapshot_status"] == "complete"
                ):
                    effect["reader_summary_ru"] = (
                        "Для источников этого периода личные реакции не найдены. "
                        "Это не снижало оценки тем и не трактовалось как отсутствие интереса."
                    )
                sidecar["reaction_effect"] = effect
            sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
            changed["stages"][stage_name]["checksums"]["json_path"] = sha256_file(
                sidecar_path
            )
        return changed

    def test_initial_manifest_has_frozen_irx2_policy_and_period(self):
        manifest = build_initial_manifest(self.period, run_id="manifest-test-run")

        self.assertEqual(manifest["schema_version"], "weekly_run_manifest.v1")
        self.assertEqual(manifest["pipeline_profile"], "irx2_orchestration.v1")
        self.assertEqual(manifest["reporting_week"], "2026-W28")
        self.assertEqual(manifest["analysis_period_start"], "2026-07-06T00:00:00Z")
        self.assertEqual(manifest["analysis_period_end"], "2026-07-13T00:00:00Z")
        self.assertEqual(
            manifest["required_stages"],
            [
                "knowledge_refresh",
                "reaction_sync",
                "feedback_snapshot",
                "frontier_analysis",
                "radar",
                "weekly_brief",
                "knowledge_atlas",
            ],
        )
        self.assertEqual(manifest["stages"]["editorial_intelligence"]["status"], "disabled")
        validate_manifest(manifest)

    def test_legacy_reaction_success_without_optional_binding_remains_valid(self):
        manifest = build_initial_manifest(
            self.period,
            run_id="legacy-reaction-manifest",
            radar_enabled=False,
        )
        manifest = start_stage(manifest, "reaction_sync")
        manifest = succeed_stage(
            manifest,
            "reaction_sync",
            updates={
                "snapshot_ref": "reaction-snapshot:legacy-reaction-manifest",
                "observed_through": "2026-07-13T07:03:00Z",
                "record_counts": {"posts_checked": 0},
            },
        )

        validate_manifest(
            manifest,
            path_base=self.root,
            allowed_roots=(self.root,),
            check_artifact_existence=True,
        )
        self.assertIsNone(
            load_bound_reaction_snapshot(
                manifest,
                path_base=self.root,
                allowed_roots=(self.root,),
            )
        )

    def test_bound_reaction_snapshot_validates_checksum_and_full_identity(self):
        manifest, run_dir, snapshot_path, payload = self._bound_reaction_manifest()

        validate_manifest(
            manifest,
            path_base=run_dir,
            allowed_roots=(run_dir,),
            check_artifact_existence=True,
        )
        self.assertEqual(
            load_bound_reaction_snapshot(
                manifest,
                path_base=run_dir,
                allowed_roots=(run_dir,),
            ),
            payload,
        )

        snapshot_path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(WeeklyRunManifestError, "checksum mismatch"):
            load_bound_reaction_snapshot(
                manifest,
                path_base=run_dir,
                allowed_roots=(run_dir,),
            )

    def test_reaction_snapshot_half_binding_is_rejected_but_absence_is_optional(self):
        manifest, _run_dir, _snapshot_path, _payload = self._bound_reaction_manifest(
            run_id="reaction-half-binding"
        )
        missing_checksum = copy.deepcopy(manifest)
        missing_checksum["stages"]["reaction_sync"]["checksums"] = {}
        with self.assertRaisesRegex(WeeklyRunManifestError, "bound together"):
            validate_manifest(missing_checksum)

        missing_path = copy.deepcopy(manifest)
        missing_path["stages"]["reaction_sync"]["artifact_refs"] = {}
        with self.assertRaisesRegex(WeeklyRunManifestError, "bound together"):
            validate_manifest(missing_path)

    def test_reaction_snapshot_rejects_payload_or_attempt_identity_tampering(self):
        manifest, run_dir, snapshot_path, payload = self._bound_reaction_manifest(
            run_id="reaction-identity-tamper"
        )
        cases = {
            "run_id": ({**payload, "run_id": "different-run"}, None),
            "reporting_week": (
                {**payload, "reporting_week": "2026-W27", "week_label": "2026-W27"},
                None,
            ),
            "snapshot_ref": (
                {**payload, "snapshot_ref": "reaction-snapshot:different"},
                None,
            ),
            "coverage": (
                {
                    **payload,
                    "coverage": {
                        **payload["coverage"],
                        "checked_count": 1,
                        "coverage_complete": False,
                    },
                },
                None,
            ),
            "post-period": (
                {
                    **payload,
                    "observed_personal_posts": [
                        {
                            **payload["observed_personal_posts"][0],
                            "posted_at": payload["analysis_period_end"],
                        }
                    ],
                },
                None,
            ),
            "attempt": (
                {**payload, "observed_through": "2026-07-13T07:03:00Z"},
                "2026-07-13T07:03:00Z",
            ),
        }
        for field, (changed_payload, stage_observed) in cases.items():
            with self.subTest(field=field):
                snapshot_path.write_text(json.dumps(changed_payload), encoding="utf-8")
                changed = copy.deepcopy(manifest)
                changed["stages"]["reaction_sync"]["checksums"][
                    "snapshot_path"
                ] = sha256_file(snapshot_path)
                if stage_observed is not None:
                    changed["stages"]["reaction_sync"][
                        "observed_through"
                    ] = stage_observed
                with self.assertRaises(WeeklyRunManifestError):
                    validate_manifest(
                        changed,
                        path_base=run_dir,
                        allowed_roots=(run_dir,),
                        check_artifact_existence=True,
                    )

        snapshot_path.write_text(json.dumps(payload), encoding="utf-8")
        count_mismatch = copy.deepcopy(manifest)
        count_mismatch["stages"]["reaction_sync"]["checksums"][
            "snapshot_path"
        ] = sha256_file(snapshot_path)
        count_mismatch["stages"]["reaction_sync"]["record_counts"][
            "posts_with_reactions"
        ] = 0
        with self.assertRaisesRegex(
            WeeklyRunManifestError,
            "snapshot/stage record_counts mismatch",
        ):
            validate_manifest(
                count_mismatch,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )

        event_mismatch = copy.deepcopy(manifest)
        event_mismatch["stages"]["reaction_sync"]["record_counts"][
            "personal_reaction_events_detected"
        ] = 0
        with self.assertRaisesRegex(
            WeeklyRunManifestError,
            "personal_reaction_events_detected",
        ):
            validate_manifest(
                event_mismatch,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )

    def test_exclusive_creation_never_reuses_a_run_identity(self):
        path, first = create_manifest(self.root, self.period, run_id="exclusive-run")

        with self.assertRaises(ManifestExistsError):
            create_manifest(self.root, self.period, run_id="exclusive-run")
        self.assertEqual(load_manifest(path), first)

    def test_atomic_replace_failure_preserves_previous_valid_json(self):
        path, initial = create_manifest(self.root, self.period, run_id="atomic-run")
        candidate = start_stage(initial, "knowledge_refresh")

        with patch(
            "output.weekly_run_manifest.os.replace",
            side_effect=OSError("simulated replace failure"),
        ):
            with self.assertRaises(OSError):
                write_manifest(path, candidate, check_artifact_existence=False)

        self.assertEqual(load_manifest(path), initial)
        self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_persisted_identity_and_stage_policy_are_immutable(self):
        path, initial = create_manifest(self.root, self.period, run_id="immutable-run")
        changed = copy.deepcopy(initial)
        changed["run_id"] = "different-run"

        with self.assertRaisesRegex(WeeklyRunManifestError, "immutable manifest field"):
            write_manifest(path, changed, check_artifact_existence=False)

    def test_full_success_finalizes_complete_and_terminal_is_immutable(self):
        path, manifest = create_manifest(self.root, self.period, run_id="complete-run")
        manifest = self._finish_successfully(manifest, path.parent)
        # The helper exercises every legal in-memory transition.  Persist its
        # last running snapshot to model the orchestrator's per-stage writes,
        # then verify the final running -> terminal atomic update.
        path.write_text(json.dumps(manifest), encoding="utf-8")
        terminal = finalize_manifest(manifest, at="2026-07-13T07:10:00Z")
        write_manifest(
            path,
            terminal,
            path_base=path.parent,
            allowed_roots=(path.parent,),
        )

        loaded = load_manifest(
            path,
            path_base=path.parent,
            allowed_roots=(path.parent,),
            check_artifact_existence=True,
        )
        self.assertEqual(loaded["run_status"], "complete")
        self.assertFalse(loaded["partial"])
        with self.assertRaises(TerminalManifestError):
            append_warning(loaded, "too late")
        with self.assertRaises(TerminalManifestError):
            write_manifest(path, loaded, check_artifact_existence=False)

    def test_terminal_manifest_rejects_active_stages_and_cancellation_quiesces_them(self):
        manifest = build_initial_manifest(
            self.period,
            run_id="terminal-quiescence-run",
            radar_enabled=False,
        )
        invalid = copy.deepcopy(manifest)
        invalid["run_status"] = "cancelled"
        invalid["cancellation_requested"] = True
        invalid["finalized_at"] = "2026-07-13T07:05:00Z"
        with self.assertRaisesRegex(WeeklyRunManifestError, "cannot retain enabled"):
            validate_manifest(invalid)

        terminal = finalize_manifest(
            manifest,
            at="2026-07-13T07:06:00Z",
            cancelled=True,
        )
        enabled = [
            name
            for name, policy in terminal["stage_policy"].items()
            if policy["enabled"]
        ]
        self.assertEqual(terminal["run_status"], "cancelled")
        self.assertEqual(terminal["failed_stages"], enabled)
        for name in enabled:
            stage = terminal["stages"][name]
            self.assertEqual(stage["status"], "cancelled")
            self.assertEqual(stage["attempt"], 1)
            self.assertEqual(stage["started_at"], "2026-07-13T07:06:00Z")
            self.assertEqual(stage["finished_at"], "2026-07-13T07:06:00Z")
        validate_manifest(terminal)

    def test_frontier_and_reader_checksums_are_verified(self):
        manifest = build_initial_manifest(
            self.period,
            run_id="reader-checksum-run",
            radar_enabled=False,
        )
        run_dir = self.root / manifest["run_id"]
        run_dir.mkdir()
        terminal = finalize_manifest(
            self._finish_successfully(manifest, run_dir, radar_enabled=False)
        )
        validate_manifest(
            terminal,
            path_base=run_dir,
            allowed_roots=(run_dir,),
            check_artifact_existence=True,
        )

        (run_dir / "frontier/frontier.json").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(WeeklyRunManifestError, "checksum mismatch"):
            validate_manifest(
                terminal,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )
        (run_dir / "frontier/frontier.json").write_text("{}", encoding="utf-8")
        (run_dir / "brief/brief.html").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(WeeklyRunManifestError, "checksum mismatch"):
            validate_manifest(
                terminal,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )

    def test_reader_sidecar_identity_is_verified_after_all_stages_finish(self):
        manifest = build_initial_manifest(
            self.period,
            run_id="reader-identity-run",
            radar_enabled=False,
        )
        run_dir = self.root / manifest["run_id"]
        run_dir.mkdir()
        terminal = finalize_manifest(
            self._finish_successfully(manifest, run_dir, radar_enabled=False)
        )
        sidecar_path = run_dir / terminal["stages"]["weekly_brief"]["json_path"]
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        sidecar["reporting_week"] = "2026-W27"
        sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
        tampered = copy.deepcopy(terminal)
        tampered["stages"]["weekly_brief"]["checksums"]["json_path"] = sha256_file(
            sidecar_path
        )

        with self.assertRaisesRegex(
            WeeklyRunManifestError,
            "weekly_brief sidecar identity mismatch: reporting_week",
        ):
            validate_manifest(
                tampered,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )

    def test_bound_reaction_snapshot_requires_effect_on_each_succeeded_reader(self):
        manifest = build_initial_manifest(
            self.period,
            run_id="bound-reader-receipts",
            radar_enabled=False,
        )
        run_dir = self.root / manifest["run_id"]
        run_dir.mkdir()
        legacy_terminal = finalize_manifest(
            self._finish_successfully(manifest, run_dir, radar_enabled=False)
        )

        # The pre-IRX-3 sidecar shape remains valid when reaction_sync has no
        # immutable, verified snapshot binding.
        validate_manifest(
            legacy_terminal,
            path_base=run_dir,
            allowed_roots=(run_dir,),
            check_artifact_existence=True,
        )

        bound_terminal = self._bind_empty_verified_reaction_snapshot(
            legacy_terminal,
            run_dir,
        )
        with self.assertRaisesRegex(
            WeeklyRunManifestError,
            "weekly_brief sidecar reaction_effect is required",
        ):
            validate_manifest(
                bound_terminal,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )

        complete_receipt = {
            "snapshot_status": "complete",
            "status": "no_eligible_reactions",
        }
        with_effects = self._with_reader_reaction_effects(
            bound_terminal,
            run_dir,
            brief_updates=complete_receipt,
            atlas_updates=complete_receipt,
        )
        validate_manifest(
            with_effects,
            path_base=run_dir,
            allowed_roots=(run_dir,),
            check_artifact_existence=True,
        )

    def test_bound_reaction_snapshot_requires_effect_when_only_brief_succeeds(self):
        manifest = build_initial_manifest(
            self.period,
            run_id="bound-single-reader-receipt",
            radar_enabled=False,
        )
        run_dir = self.root / manifest["run_id"]
        run_dir.mkdir()
        terminal = finalize_manifest(
            self._finish_successfully(
                manifest,
                run_dir,
                radar_enabled=False,
                atlas_succeeds=False,
            )
        )
        bound_terminal = self._bind_empty_verified_reaction_snapshot(
            terminal,
            run_dir,
        )

        with self.assertRaisesRegex(
            WeeklyRunManifestError,
            "weekly_brief sidecar reaction_effect is required",
        ):
            validate_manifest(
                bound_terminal,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )

        with_effect = self._with_reader_reaction_effects(
            bound_terminal,
            run_dir,
            brief_updates={
                "snapshot_status": "complete",
                "status": "no_eligible_reactions",
            },
        )
        validate_manifest(
            with_effect,
            path_base=run_dir,
            allowed_roots=(run_dir,),
            check_artifact_existence=True,
        )

    def test_bound_reaction_effect_status_tracks_feedback_snapshot_availability(self):
        manifest = build_initial_manifest(
            self.period,
            run_id="bound-feedback-receipt",
            radar_enabled=False,
        )
        run_dir = self.root / manifest["run_id"]
        run_dir.mkdir()
        terminal = finalize_manifest(
            self._finish_successfully(
                manifest,
                run_dir,
                radar_enabled=False,
                feedback_succeeds=False,
            )
        )
        bound_terminal = self._bind_empty_verified_reaction_snapshot(
            terminal,
            run_dir,
        )
        partial_summary = (
            "Снимок личных реакций за период подтверждён, но контекст явной "
            "обратной связи не удалось полностью проверить. Поэтому "
            "персонализация по реакциям не применялась."
        )
        valid_partial = self._with_reader_reaction_effects(
            bound_terminal,
            run_dir,
            brief_updates={
                "snapshot_status": "complete",
                "status": "partial",
                "reader_summary_ru": partial_summary,
            },
            atlas_updates={
                "snapshot_status": "complete",
                "status": "partial",
                "reader_summary_ru": partial_summary,
            },
        )
        validate_manifest(
            valid_partial,
            path_base=run_dir,
            allowed_roots=(run_dir,),
            check_artifact_existence=True,
        )

        false_complete = self._with_reader_reaction_effects(
            bound_terminal,
            run_dir,
            brief_updates={
                "snapshot_status": "complete",
                "status": "no_eligible_reactions",
            },
            atlas_updates={
                "snapshot_status": "complete",
                "status": "no_eligible_reactions",
            },
        )
        with self.assertRaisesRegex(
            WeeklyRunManifestError,
            "must be partial when the confirmed-feedback snapshot is unavailable",
        ):
            validate_manifest(
                false_complete,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )

        succeeded_manifest = build_initial_manifest(
            self.period,
            run_id="bound-complete-feedback-receipt",
            radar_enabled=False,
        )
        succeeded_dir = self.root / succeeded_manifest["run_id"]
        succeeded_dir.mkdir()
        succeeded_terminal = self._bind_empty_verified_reaction_snapshot(
            finalize_manifest(
                self._finish_successfully(
                    succeeded_manifest,
                    succeeded_dir,
                    radar_enabled=False,
                )
            ),
            succeeded_dir,
        )
        false_partial = self._with_reader_reaction_effects(
            succeeded_terminal,
            succeeded_dir,
            brief_updates={
                "snapshot_status": "complete",
                "status": "partial",
                "reader_summary_ru": partial_summary,
            },
            atlas_updates={
                "snapshot_status": "complete",
                "status": "partial",
                "reader_summary_ru": partial_summary,
            },
        )
        with self.assertRaisesRegex(
            WeeklyRunManifestError,
            "cannot be partial when both reaction and confirmed-feedback snapshots succeeded",
        ):
            validate_manifest(
                false_partial,
                path_base=succeeded_dir,
                allowed_roots=(succeeded_dir,),
                check_artifact_existence=True,
            )

    def test_nonempty_snapshot_binds_selected_unconsumed_and_rendered_lineage(self):
        manifest = build_initial_manifest(
            self.period,
            run_id="bound-nonempty-reaction-lineage",
            radar_enabled=False,
        )
        run_dir = self.root / manifest["run_id"]
        run_dir.mkdir()
        terminal = finalize_manifest(
            self._finish_successfully(manifest, run_dir, radar_enabled=False)
        )
        posts = [
            {
                "post_id": 41,
                "channel_username": "@source",
                "message_id": 77,
                "posted_at": "2026-07-12T23:59:58Z",
                "raw_emojis": ["a"],
            },
            {
                "post_id": 42,
                "channel_username": "@other",
                "message_id": 78,
                "posted_at": "2026-07-12T23:59:59Z",
                "raw_emojis": ["b"],
            },
        ]
        bound = self._bind_verified_reaction_posts(terminal, run_dir, posts)

        def opaque(prefix, value):
            return prefix + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]

        selected_post_ref = opaque("reaction-post:", "source:77:41")
        unselected_reaction_ref = opaque("reaction:", "other:78:b")
        selected_reaction_ref = opaque("reaction:", "source:77:a")
        attribution = {
            "surface_item_ref": "thread:chosen",
            "reacted_post_count": 1,
            "compatibility_thread_ref": "idea_thread:chosen",
            "current_thread_ref": "idea_thread:chosen",
            "canonical_thread_ref": None,
            "thread_resolution_status": "compatibility_current_thread_only",
            "boost_role": "weak_implicit_interest",
            "reader_reason_ru": "Вы отметили один связанный пост за отчётный период.",
            "reacted_post_refs": [selected_post_ref],
            "source_refs": ["telegram:@source"],
            "evidence_refs": ["atom:1"],
            "boost_applied": True,
        }
        base_effect = {
            "schema_version": "reaction_personalization.v1",
            "run_id": bound["run_id"],
            "reporting_week": bound["reporting_week"],
            "analysis_period_start": bound["analysis_period_start"],
            "analysis_period_end": bound["analysis_period_end"],
            "snapshot_ref": bound["stages"]["reaction_sync"]["snapshot_ref"],
            "snapshot_status": "complete",
            "status": "linked_no_selection_effect",
            "reader_summary_ru": (
                "Ваши отметки связаны с темами выпуска, но не изменили их место: "
                "они уже прошли по силе доказательств."
            ),
            "counts": {
                "personal_reaction_events_detected": 2,
                "unique_reacted_posts": 2,
                "posts_resolved": 2,
                "eligible_period_posts": 2,
                "unique_atoms_linked": 1,
                "unique_canonical_threads_linked": 0,
                "canonical_threads_boosted": 0,
                "unique_compatibility_threads_linked": 1,
                "compatibility_threads_boosted": 1,
                "selected_items_linked": 1,
                "selected_signals_influenced": 0,
                "unconsumed_reaction_events": 1,
            },
            "influenced_items": [],
            "linked_only_items": [
                {
                    **attribution,
                    "effect": "linked_only",
                    "rank_changed": False,
                    "selection_changed": False,
                    "linked_only": True,
                }
            ],
            "eligible_thread_audit": [
                {
                    **attribution,
                    "selected": True,
                    "counterfactual_effect": "linked_only",
                }
            ],
            "unconsumed_by_reason": {"knowledge_atom_not_extracted": 1},
            "unconsumed": [
                {
                    "reaction_ref": unselected_reaction_ref,
                    "reason": "knowledge_atom_not_extracted",
                    "reasons": ["knowledge_atom_not_extracted"],
                    "audit_detail": "no bounded atom cites the normalized post identity",
                }
            ],
            "ranking_policy": {
                "policy_version": "reaction-ranking.v1",
                "strength": "weak",
                "below_confirmed_feedback": True,
                "can_change_evidence_gate": False,
            },
        }

        def write_effects(effect, *, atlas_effect=None):
            for stage_name, surface in (
                ("weekly_brief", "weekly_brief"),
                ("knowledge_atlas", "knowledge_atlas"),
            ):
                sidecar_path = run_dir / bound["stages"][stage_name]["json_path"]
                sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
                selected_effect = (
                    atlas_effect
                    if stage_name == "knowledge_atlas" and atlas_effect is not None
                    else effect
                )
                sidecar["reaction_effect"] = {
                    **copy.deepcopy(selected_effect),
                    "surface": surface,
                }
                if stage_name == "weekly_brief":
                    sidecar["actions"] = [{"surface_item_ref": "thread:chosen"}]
                else:
                    sidecar["thread_navigation"] = {"threads": [{"slug": "chosen"}]}
                sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
                bound["stages"][stage_name]["checksums"]["json_path"] = sha256_file(
                    sidecar_path
                )

        write_effects(base_effect)
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(json.dumps(bound), encoding="utf-8")
        load_manifest(
            manifest_path,
            path_base=run_dir,
            allowed_roots=(run_dir,),
            check_artifact_existence=True,
        )

        atlas_unselected = copy.deepcopy(base_effect)
        atlas_unselected["reader_summary_ru"] = (
            "Личные реакции связаны с темами, прошедшими условия, но эти "
            "темы остались за пределом краткой выборки и не изменили выпуск. "
            "Это не снижало оценки тем."
        )
        atlas_unselected["counts"]["selected_items_linked"] = 0
        atlas_unselected["counts"]["unconsumed_reaction_events"] = 2
        atlas_unselected["linked_only_items"] = []
        atlas_unselected["eligible_thread_audit"][0]["selected"] = False
        atlas_unselected["eligible_thread_audit"][0][
            "counterfactual_effect"
        ] = "report_limit_reached"
        atlas_unselected["unconsumed_by_reason"] = {
            "knowledge_atom_not_extracted": 1,
            "report_limit_reached": 1,
        }
        atlas_unselected["unconsumed"] = [
            {
                "reaction_ref": selected_reaction_ref,
                "reason": "report_limit_reached",
                "reasons": ["report_limit_reached"],
                "audit_detail": "eligible compatibility thread remained below the report limit",
            },
            *copy.deepcopy(base_effect["unconsumed"]),
        ]
        write_effects(base_effect, atlas_effect=atlas_unselected)
        validate_manifest(
            bound,
            path_base=run_dir,
            allowed_roots=(run_dir,),
            check_artifact_existence=True,
        )

        ghost = copy.deepcopy(base_effect)
        ghost["linked_only_items"][0]["surface_item_ref"] = "thread:ghost"
        ghost["eligible_thread_audit"][0]["surface_item_ref"] = "thread:ghost"
        write_effects(ghost)
        with self.assertRaisesRegex(WeeklyRunManifestError, "absent from the rendered surface"):
            validate_manifest(
                bound,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )

        double_consumed = copy.deepcopy(base_effect)
        double_consumed["unconsumed"][0]["reaction_ref"] = selected_reaction_ref
        write_effects(double_consumed)
        with self.assertRaisesRegex(WeeklyRunManifestError, "unconsumed lineage"):
            validate_manifest(
                bound,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )

    def test_optional_reader_reaction_effect_requires_identity_and_cross_surface_parity(self):
        manifest = build_initial_manifest(
            self.period,
            run_id="reader-reaction-effect",
            radar_enabled=False,
        )
        run_dir = self.root / manifest["run_id"]
        run_dir.mkdir()
        terminal = finalize_manifest(
            self._finish_successfully(manifest, run_dir, radar_enabled=False)
        )
        with_effects = self._with_reader_reaction_effects(terminal, run_dir)
        validate_manifest(
            with_effects,
            path_base=run_dir,
            allowed_roots=(run_dir,),
            check_artifact_existence=True,
        )

        cases = (
            (
                "presence",
                lambda: self._with_reader_reaction_effects(
                    terminal, run_dir, include_atlas=False
                ),
                "present on both",
            ),
            (
                "surface",
                lambda: self._with_reader_reaction_effects(
                    terminal, run_dir,
                    brief_updates={"surface": "knowledge_atlas"},
                ),
                "surface mismatch",
            ),
            (
                "run",
                lambda: self._with_reader_reaction_effects(
                    terminal, run_dir,
                    brief_updates={"run_id": "different-run"},
                ),
                "run_id mismatch",
            ),
            (
                "snapshot-status",
                lambda: self._with_reader_reaction_effects(
                    terminal, run_dir,
                    brief_updates={"snapshot_status": "complete"},
                ),
                "snapshot_status mismatch",
            ),
            (
                "payload-parity",
                lambda: self._with_reader_reaction_effects(
                    terminal, run_dir,
                    atlas_updates={
                        "ranking_policy": {
                            "policy_version": "reaction-ranking.v1",
                            "strength": "weak",
                            "below_confirmed_feedback": True,
                            "can_change_evidence_gate": False,
                            "audit_note": "different",
                        }
                    },
                ),
                "common identity differs",
            ),
            (
                "logical-effect",
                lambda: self._with_reader_reaction_effects(
                    terminal,
                    run_dir,
                    brief_updates={"status": "effects_applied"},
                ),
                "reaction_effect is invalid",
            ),
        )
        for label, build_changed, message in cases:
            with self.subTest(label=label), self.assertRaisesRegex(
                WeeklyRunManifestError, message
            ):
                changed = build_changed()
                validate_manifest(
                    changed,
                    path_base=run_dir,
                    allowed_roots=(run_dir,),
                    check_artifact_existence=True,
                )

    def test_required_radar_failure_aggregates_partial(self):
        manifest = build_initial_manifest(self.period, run_id="radar-failed-run")
        run_dir = self.root / manifest["run_id"]
        run_dir.mkdir()
        manifest = self._finish_successfully(
            manifest,
            run_dir,
            radar_enabled=False,
        )
        manifest = start_stage(manifest, "radar")
        manifest = fail_stage(manifest, "radar", "wrong reporting period")
        terminal = finalize_manifest(manifest)

        self.assertEqual(terminal["run_status"], "partial")
        self.assertTrue(terminal["partial"])
        self.assertEqual(terminal["failed_stages"], ["radar"])

    def test_brief_failure_is_fatal(self):
        manifest = build_initial_manifest(
            self.period,
            run_id="brief-failed-run",
            radar_enabled=False,
        )
        run_dir = self.root / manifest["run_id"]
        run_dir.mkdir()
        # Complete all enabled non-reader stages, then make Brief fatal and
        # explicitly skip Atlas as its dependent reader surface.
        for stage in ("knowledge_refresh",):
            manifest = start_stage(manifest, stage)
            manifest = succeed_stage(manifest, stage)
        manifest = start_stage(manifest, "reaction_sync")
        manifest = succeed_stage(
            manifest,
            "reaction_sync",
            updates={
                "snapshot_ref": "reaction-snapshot:brief-failed-run",
                "observed_through": "2026-07-13T07:03:00Z",
            },
        )
        manifest = start_stage(manifest, "feedback_snapshot")
        manifest = succeed_stage(
            manifest,
            "feedback_snapshot",
            updates={
                "snapshot_id": "feedback-snapshot:brief-failed-run",
                "cutoff": manifest["analysis_period_end"],
            },
        )
        frontier = self._file(run_dir, "frontier.json")
        manifest = start_stage(manifest, "frontier_analysis")
        manifest = succeed_stage(
            manifest,
            "frontier_analysis",
            updates={
                "analysis_id": 1,
                "artifact_path": frontier,
                "checksums": {"artifact_path": sha256_file(run_dir / frontier)},
            },
        )
        manifest = start_stage(manifest, "weekly_brief")
        manifest = fail_stage(manifest, "weekly_brief", "renderer unavailable")
        manifest = transition_stage(
            manifest,
            "knowledge_atlas",
            "skipped_dependency",
            error="Brief failed",
        )
        terminal = finalize_manifest(manifest)

        self.assertEqual(terminal["run_status"], FAILED)
        self.assertIn("weekly_brief", terminal["failed_stages"])

    def test_predeclared_radar_disable_can_complete_but_is_visible(self):
        manifest = build_initial_manifest(
            self.period,
            run_id="radar-disabled-run",
            radar_enabled=False,
        )
        run_dir = self.root / manifest["run_id"]
        run_dir.mkdir()
        manifest = self._finish_successfully(manifest, run_dir, radar_enabled=False)
        terminal = finalize_manifest(manifest)

        self.assertEqual(terminal["run_status"], "complete")
        self.assertEqual(terminal["stages"]["radar"]["status"], "disabled")
        self.assertNotIn("radar", terminal["required_stages"])
        self.assertTrue(any("dogfood gate" in warning for warning in terminal["warnings"]))

    def test_partial_iso_week_forces_partial_even_when_stages_succeed(self):
        partial_period = resolve_reporting_period(RUN_AT, period_mode=PARTIAL_ISO_WEEK)
        manifest = build_initial_manifest(
            partial_period,
            run_id="partial-period-run",
            radar_enabled=False,
        )
        run_dir = self.root / manifest["run_id"]
        run_dir.mkdir()
        manifest = self._finish_successfully(manifest, run_dir, radar_enabled=False)
        terminal = finalize_manifest(manifest)

        self.assertEqual(terminal["run_status"], "partial")
        self.assertTrue(terminal["partial"])

    def test_skip_transition_counts_as_an_attempt_and_can_resume(self):
        manifest = build_initial_manifest(
            self.period,
            run_id="resume-run",
            radar_enabled=False,
        )
        skipped = transition_stage(
            manifest,
            "knowledge_atlas",
            "skipped_dependency",
            error="dependency failed",
        )
        self.assertEqual(skipped["stages"]["knowledge_atlas"]["attempt"], 1)
        resumed = start_stage(skipped, "knowledge_atlas")
        self.assertEqual(resumed["stages"]["knowledge_atlas"]["attempt"], 2)

    def test_radar_binding_rejects_period_or_checksum_tampering(self):
        manifest = build_initial_manifest(self.period, run_id="binding-run")
        run_dir = self.root / manifest["run_id"]
        run_dir.mkdir()
        self._file(run_dir, "seed.json", "[]")
        self._file(run_dir, "radar.json", '{"result":{"run_id":"radar-binding"}}')
        manifest = start_stage(manifest, "radar")
        binding = build_radar_run_binding(
            manifest,
            radar_run_id="radar-binding",
            radar_contract_version="tra-radar-intelligence-contract.v1",
            radar_schema_version="mvp_of_week.v1",
            seed_export_path="seed.json",
            radar_json_path="radar.json",
            selected_candidate=None,
            status_projection={"status": "no_candidate"},
            path_base=run_dir,
            allowed_roots=(run_dir,),
        )

        wrong_period = copy.deepcopy(binding)
        wrong_period["reporting_week"] = "2026-W27"
        wrong_period["week_label"] = "2026-W27"
        with self.assertRaises(RadarBindingError):
            validate_radar_run_binding(wrong_period, manifest=manifest)
        (run_dir / "radar.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(RadarBindingError, "checksum mismatch"):
            validate_radar_run_binding(
                binding,
                manifest=manifest,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                verify_files=True,
            )

    def test_successful_radar_requires_binding_raw_and_dependency_parity(self):
        manifest = build_initial_manifest(self.period, run_id="radar-integrity-run")
        run_dir = self.root / manifest["run_id"]
        run_dir.mkdir()
        terminal = finalize_manifest(self._finish_successfully(manifest, run_dir))
        validate_manifest(
            terminal,
            path_base=run_dir,
            allowed_roots=(run_dir,),
            check_artifact_existence=True,
        )

        market_path = run_dir / terminal["stages"]["radar"]["market_lens_path"]
        market_path.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(WeeklyRunManifestError, "checksum mismatch"):
            validate_manifest(
                terminal,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )
        market_path.write_text("{}", encoding="utf-8")

        binding_path = run_dir / terminal["stages"]["radar"]["binding_path"]
        original_binding_text = binding_path.read_text(encoding="utf-8")
        wrong_binding = json.loads(original_binding_text)
        wrong_binding["radar_run_id"] = "different-binding-run"
        binding_path.write_text(json.dumps(wrong_binding), encoding="utf-8")
        binding_id_mismatch = copy.deepcopy(terminal)
        changed_binding_checksum = sha256_file(binding_path)
        binding_id_mismatch["stages"]["radar"][
            "binding_sha256"
        ] = changed_binding_checksum
        binding_id_mismatch["radar_json_ref"][
            "binding_sha256"
        ] = changed_binding_checksum
        with self.assertRaisesRegex(
            RadarBindingError,
            "binding/stage radar_run_id mismatch",
        ):
            validate_manifest(
                binding_id_mismatch,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )
        binding_path.write_text(original_binding_text, encoding="utf-8")

        alternate_seed = run_dir / "radar" / "alternate-seeds.json"
        alternate_seed.write_text("[]", encoding="utf-8")
        wrong_path = copy.deepcopy(terminal)
        wrong_path["stages"]["radar"]["seed_export_path"] = (
            "radar/alternate-seeds.json"
        )
        with self.assertRaisesRegex(
            WeeklyRunManifestError,
            "binding/stage mismatch for seed_export_path",
        ):
            validate_manifest(
                wrong_path,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )

        raw_path = run_dir / terminal["stages"]["radar"]["artifact_path"]
        raw_path.write_text(
            json.dumps({"result": {"run_id": "different-radar-run"}}),
            encoding="utf-8",
        )
        raw_mismatch = copy.deepcopy(terminal)
        raw_checksum = sha256_file(raw_path)
        raw_mismatch["stages"]["radar"]["artifact_sha256"] = raw_checksum
        raw_mismatch["radar_json_ref"]["sha256"] = raw_checksum
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        binding["radar_json_ref"]["sha256"] = raw_checksum
        binding_path.write_text(json.dumps(binding), encoding="utf-8")
        binding_checksum = sha256_file(binding_path)
        raw_mismatch["stages"]["radar"]["binding_sha256"] = binding_checksum
        raw_mismatch["radar_json_ref"]["binding_sha256"] = binding_checksum
        with self.assertRaisesRegex(
            WeeklyRunManifestError,
            "raw/stage radar_run_id mismatch",
        ):
            validate_manifest(
                raw_mismatch,
                path_base=run_dir,
                allowed_roots=(run_dir,),
                check_artifact_existence=True,
            )

    def test_path_traversal_and_wrong_checksum_are_rejected(self):
        manifest = build_initial_manifest(
            self.period,
            run_id="unsafe-path-run",
            radar_enabled=False,
        )
        changed = copy.deepcopy(manifest)
        changed["stages"]["frontier_analysis"]["artifact_path"] = "../escape.json"
        changed["frontier_analysis_path"] = "../escape.json"
        changed["frontier_analysis_ref"]["path"] = "../escape.json"
        with self.assertRaisesRegex(WeeklyRunManifestError, "escapes"):
            validate_manifest(changed)

        artifact = self.root / "artifact.json"
        artifact.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(WeeklyRunManifestError, "checksum mismatch"):
            verify_file_checksum(artifact, "0" * 64)

    def test_error_records_are_bounded_and_redact_secrets(self):
        error = sanitize_error(
            RuntimeError("token=super-secret password:hunter2 Bearer abc.def.ghi")
        )

        self.assertNotIn("super-secret", error["message"])
        self.assertNotIn("hunter2", error["message"])
        self.assertNotIn("abc.def.ghi", error["message"])
        self.assertLessEqual(len(error["message"]), 500)


if __name__ == "__main__":
    unittest.main()
