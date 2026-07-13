import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from output.reporting_period import PARTIAL_ISO_WEEK, resolve_reporting_period
from output.weekly_run_manifest import (
    FAILED,
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

    def _finish_successfully(self, manifest, run_dir: Path, *, radar_enabled=True):
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
        )
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
