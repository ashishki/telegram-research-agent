from __future__ import annotations

import copy
import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from output.project_intelligence import (
    ProjectDescriptorError,
    ProjectIntelligenceArtifactError,
    ProjectIntelligenceValidationError,
    build_project_intelligence_projection,
    generate_project_intelligence_artifact,
    load_project_action_descriptors,
    load_project_intelligence_artifact,
    project_editorial_permissions,
    validate_project_intelligence_projection,
)


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "report_v2"
    / "project_intelligence_v2_cases.v1.json"
)
EXPECTED_ROOT_FIELDS = {
    "schema_version",
    "descriptor_schema_version",
    "run_id",
    "reporting_period",
    "reader_state",
    "reader_summary_ru",
    "confirmed_actions",
    "audit_records",
    "editorial_permissions",
    "source_policy",
    "input_hash",
}
EXPECTED_ACTION_FIELDS = {
    "project_action_ref",
    "project_name",
    "project_repo",
    "permission_id",
    "signal_id",
    "canonical_thread_ref",
    "why_this_project",
    "affected_component",
    "suggested_change",
    "likely_files",
    "effort",
    "acceptance_criteria",
    "risk",
    "priority",
    "confidence",
    "evidence_refs",
    "status",
}
EXPECTED_AUDIT_FIELDS = {
    "audit_id",
    "project_name",
    "permission_id",
    "signal_id",
    "canonical_thread_ref",
    "status",
    "reason_ru",
    "evidence_refs",
    "selected",
}
EXPECTED_EDITORIAL_PERMISSION_FIELDS = {
    "project_action_ref",
    "signal_id",
    "project",
    "permission",
    "evidence_refs",
}


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class ProjectIntelligenceV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def setUp(self) -> None:
        self.input_package = copy.deepcopy(self.fixture["input_package"])
        self.records = copy.deepcopy(self.fixture["diagnostic_records"])
        self.project_descriptor = copy.deepcopy(self.fixture["project_descriptor"])
        self.projects = self._load_descriptors(self.project_descriptor)

    def _write_projects(
        self,
        directory: Path,
        descriptor: dict[str, object] | None = None,
    ) -> Path:
        path = directory / "projects.yaml"
        path.write_text(
            json.dumps(
                {"projects": [descriptor or self.project_descriptor]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def _load_descriptors(
        self,
        descriptor: dict[str, object],
    ) -> list[dict[str, object]]:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_projects(Path(tmp), descriptor)
            return list(load_project_action_descriptors(path))

    def _build(
        self,
        records: list[dict[str, object]],
        *,
        input_package: dict[str, object] | None = None,
        projects: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return build_project_intelligence_projection(
            input_package or self.input_package,
            projects=self.projects if projects is None else projects,
            diagnostic_records=records,
        )

    def _assert_zero_projection(self, payload: dict[str, object]) -> None:
        self.assertEqual(payload["reader_state"], "no_confirmed_implication")
        self.assertEqual(payload["confirmed_actions"], [])
        self.assertEqual(payload["editorial_permissions"], [])
        summary = str(payload["reader_summary_ru"])
        self.assertRegex(summary, r"[А-Яа-яЁё]")
        self.assertRegex(summary.lower(), r"нет|не найден|не подтвержд")

    def test_fixture_is_sanitized_and_loader_normalizes_one_project_descriptor(
        self,
    ) -> None:
        serialized = FIXTURE_PATH.read_text(encoding="utf-8")
        self.assertEqual(
            self.fixture["schema_version"],
            "project_intelligence_v2_cases.v1",
        )
        self.assertNotIn("RAW ARCHIVE", serialized)
        self.assertNotIn("/srv/", serialized)
        self.assertNotIn("../", serialized)
        self.assertEqual(len(self.projects), 3)
        self.assertEqual(
            [item["permission_id"] for item in self.projects],
            [
                "brief-evidence-receipt",
                "atlas-audit-link",
                "confidence-boundary-copy",
            ],
        )
        for item in self.projects:
            self.assertEqual(item["schema_version"], "project_action_permissions.v1")
            self.assertEqual(item["project_name"], "telegram-research-agent")
            self.assertEqual(
                item["project_repo"],
                "ashishki/telegram-research-agent",
            )

    def test_confirmed_action_is_exact_concrete_and_owned_by_host_descriptor(
        self,
    ) -> None:
        projection = self._build(self.records["concrete"][:1])
        validate_project_intelligence_projection(
            projection,
            input_package=self.input_package,
            projects=self.projects,
        )

        self.assertEqual(set(projection), EXPECTED_ROOT_FIELDS)
        self.assertEqual(projection["reader_state"], "confirmed_actions")
        self.assertEqual(len(projection["confirmed_actions"]), 1)
        action = projection["confirmed_actions"][0]
        descriptor = self.projects[0]
        self.assertEqual(set(action), EXPECTED_ACTION_FIELDS)
        self.assertEqual(action["status"], "confirmed")
        self.assertEqual(action["project_name"], descriptor["project_name"])
        self.assertEqual(action["project_repo"], descriptor["project_repo"])
        self.assertEqual(action["permission_id"], descriptor["permission_id"])
        self.assertEqual(action["signal_id"], "signal:evidence-bound-brief")
        self.assertEqual(
            action["canonical_thread_ref"],
            "canonical_thread:evidence-bound-brief",
        )
        for field in (
            "why_this_project",
            "affected_component",
            "suggested_change",
            "likely_files",
            "effort",
            "acceptance_criteria",
            "risk",
            "priority",
        ):
            self.assertEqual(action[field], descriptor[field])
        self.assertEqual(action["confidence"], "medium")
        self.assertEqual(
            action["evidence_refs"],
            ["evidence:brief-primary", "evidence:brief-secondary"],
        )
        serialized = json.dumps(action, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("safe-but-undeclared-project", serialized)
        self.assertNotIn("safe/but/undeclared.py", serialized)
        self.assertNotIn("Скопировать общий редакционный совет", serialized)

    def test_max_two_cap_is_priority_stable_and_third_remains_unselected_audit(
        self,
    ) -> None:
        projection = self._build(self.records["concrete"])

        self.assertEqual(
            [item["permission_id"] for item in projection["confirmed_actions"]],
            ["brief-evidence-receipt", "atlas-audit-link"],
        )
        self.assertEqual(len(projection["confirmed_actions"]), 2)
        audits = {item["permission_id"]: item for item in projection["audit_records"]}
        self.assertEqual(set(audits["brief-evidence-receipt"]), EXPECTED_AUDIT_FIELDS)
        self.assertTrue(audits["brief-evidence-receipt"]["selected"])
        self.assertTrue(audits["atlas-audit-link"]["selected"])
        self.assertFalse(audits["confidence-boundary-copy"]["selected"])
        self.assertEqual(audits["confidence-boundary-copy"]["status"], "confirmed")
        self.assertIn("лимит", audits["confidence-boundary-copy"]["reason_ru"].lower())

    def test_watch_rejected_learning_and_existing_states_are_nonactionable(
        self,
    ) -> None:
        cases = {
            "weak": "watch",
            "rejected": "rejected_overlap",
            "learning": "learning_only",
            "existing": "existing_project_context",
        }
        for fixture_name, expected_status in cases.items():
            with self.subTest(status=expected_status):
                projection = self._build(self.records[fixture_name])
                self._assert_zero_projection(projection)
                self.assertEqual(len(projection["audit_records"]), 1)
                audit = projection["audit_records"][0]
                self.assertEqual(audit["status"], expected_status)
                self.assertFalse(audit["selected"])
                self.assertTrue(audit["reason_ru"])

    def test_empty_result_has_explicit_russian_no_implication_audit_state(self) -> None:
        empty_input = copy.deepcopy(self.input_package)
        empty_input["signal_candidates"] = []
        empty_input["evidence_catalog"] = []
        projection = self._build(self.records["empty"], input_package=empty_input)

        self._assert_zero_projection(projection)
        self.assertEqual(len(projection["audit_records"]), 1)
        sentinel = projection["audit_records"][0]
        self.assertEqual(set(sentinel), EXPECTED_AUDIT_FIELDS)
        self.assertEqual(sentinel["status"], "no_confirmed_implication")
        self.assertFalse(sentinel["selected"])
        self.assertRegex(sentinel["reason_ru"], r"[А-Яа-яЁё]")
        self.assertIn("если они были", projection["reader_summary_ru"])
        validate_project_intelligence_projection(
            projection,
            input_package=empty_input,
            projects=self.projects,
        )

    def test_keyword_only_or_wrong_canonical_ref_cannot_be_confirmed(self) -> None:
        keyword_only = copy.deepcopy(self.records["rejected"][0])
        keyword_only["status"] = "confirmed"
        projection = self._build([keyword_only])
        self._assert_zero_projection(projection)
        self.assertFalse(projection["audit_records"][0]["selected"])
        self.assertNotEqual(projection["audit_records"][0]["status"], "confirmed")

        wrong_ref = copy.deepcopy(self.records["concrete"][0])
        wrong_ref["canonical_thread_ref"] = "canonical_thread:generic-evidence"
        projection = self._build([wrong_ref])
        self._assert_zero_projection(projection)
        self.assertFalse(projection["audit_records"][0]["selected"])

    def test_missing_cross_signal_context_only_and_non_decision_evidence_fail_closed(
        self,
    ) -> None:
        base = copy.deepcopy(self.records["concrete"][0])
        cases: dict[str, tuple[str, str]] = {
            "missing": ("signal:evidence-bound-brief", "evidence:missing"),
            "cross_signal": ("signal:evidence-bound-brief", "evidence:atlas-primary"),
            "context_only": ("signal:context-only", "evidence:context-only"),
            "non_decision": ("signal:non-decision", "evidence:non-decision"),
        }
        for name, (signal_id, evidence_ref) in cases.items():
            with self.subTest(gate=name):
                record = copy.deepcopy(base)
                record["signal_id"] = signal_id
                record["evidence_refs"] = [evidence_ref]
                projection = self._build([record])
                self._assert_zero_projection(projection)
                self.assertFalse(projection["audit_records"][0]["selected"])

        foreign_watch = copy.deepcopy(self.records["weak"][0])
        foreign_watch["evidence_refs"] = ["evidence:atlas-primary"]
        with self.assertRaisesRegex(
            ProjectIntelligenceValidationError,
            "evidence_refs are not owned by its signal",
        ):
            self._build([foreign_watch])

    def test_omitted_diagnostics_preserve_exact_ineligible_matches_as_watch(
        self,
    ) -> None:
        cases = {
            "signal:context-only": "evidence:context-only",
            "signal:non-decision": "evidence:non-decision",
        }
        for signal_id, evidence_ref in cases.items():
            with self.subTest(signal_id=signal_id):
                input_package = copy.deepcopy(self.input_package)
                input_package["signal_candidates"] = [
                    item
                    for item in input_package["signal_candidates"]
                    if item["signal_id"] == signal_id
                ]
                input_package["evidence_catalog"] = [
                    item
                    for item in input_package["evidence_catalog"]
                    if item["evidence_ref"] == evidence_ref
                ]

                projection = build_project_intelligence_projection(
                    input_package,
                    projects=self.projects,
                )

                self._assert_zero_projection(projection)
                self.assertEqual(len(projection["audit_records"]), 1)
                audit = projection["audit_records"][0]
                self.assertEqual(audit["signal_id"], signal_id)
                self.assertEqual(audit["status"], "watch")
                self.assertFalse(audit["selected"])
                self.assertNotEqual(
                    audit["audit_id"],
                    "audit:no-confirmed-implication",
                )

    def test_validation_rejects_zero_state_hiding_actionable_confirmed_audit(
        self,
    ) -> None:
        projection = self._build(self.records["concrete"][:1])
        zero_projection = self._build([])
        projection["confirmed_actions"] = []
        projection["editorial_permissions"] = []
        projection["reader_state"] = "no_confirmed_implication"
        projection["reader_summary_ru"] = zero_projection["reader_summary_ru"]
        projection["audit_records"][0]["selected"] = False

        with self.assertRaisesRegex(
            ProjectIntelligenceValidationError,
            "selected audits must be the deterministic first two",
        ):
            validate_project_intelligence_projection(
                projection,
                input_package=self.input_package,
                projects=self.projects,
            )

    def test_unknown_project_or_permission_never_yields_reader_action(self) -> None:
        for field, value in (
            ("project_name", "unknown-project"),
            ("permission_id", "unknown-permission"),
        ):
            with self.subTest(field=field):
                record = copy.deepcopy(self.records["concrete"][0])
                record[field] = value
                projection = self._build([record])
                self._assert_zero_projection(projection)
                self.assertFalse(projection["audit_records"][0]["selected"])

    def test_projection_validation_rejects_unknown_fields_and_broken_closure(
        self,
    ) -> None:
        projection = self._build(self.records["concrete"][:1])
        mutations: list[tuple[str, dict[str, object]]] = []

        root_unknown = copy.deepcopy(projection)
        root_unknown["safe_but_unknown"] = "ignored-looking"
        mutations.append(("root_unknown", root_unknown))

        action_unknown = copy.deepcopy(projection)
        action_unknown["confirmed_actions"][0]["safe_but_unknown"] = "ignored-looking"
        mutations.append(("action_unknown", action_unknown))

        audit_unknown = copy.deepcopy(projection)
        audit_unknown["audit_records"][0]["safe_but_unknown"] = "ignored-looking"
        mutations.append(("audit_unknown", audit_unknown))

        cross_signal = copy.deepcopy(projection)
        cross_signal["confirmed_actions"][0]["evidence_refs"] = [
            "evidence:atlas-primary"
        ]
        mutations.append(("cross_signal", cross_signal))

        generic_copy = copy.deepcopy(projection)
        generic_copy["confirmed_actions"][0]["suggested_change"] = (
            "Скопировать общий редакционный совет."
        )
        mutations.append(("descriptor_mismatch", generic_copy))

        contradictory_summary = copy.deepcopy(projection)
        contradictory_summary["reader_summary_ru"] = (
            "Подтверждённых проектных действий не найдено."
        )
        mutations.append(("reader_summary_mismatch", contradictory_summary))

        audit_evidence_mismatch = copy.deepcopy(projection)
        audit_evidence_mismatch["audit_records"][0]["evidence_refs"] = [
            "evidence:atlas-primary"
        ]
        mutations.append(("selected_audit_evidence_mismatch", audit_evidence_mismatch))

        unstable_action_ref = copy.deepcopy(projection)
        unstable_action_ref["confirmed_actions"][0]["project_action_ref"] = (
            "project_action:forged"
        )
        unstable_action_ref["editorial_permissions"][0]["project_action_ref"] = (
            "project_action:forged"
        )
        mutations.append(("unstable_action_ref", unstable_action_ref))

        unstable_audit_ref = copy.deepcopy(projection)
        unstable_audit_ref["audit_records"][0]["audit_id"] = "audit:forged"
        mutations.append(("unstable_audit_ref", unstable_audit_ref))

        reversed_actions = self._build(self.records["concrete"])
        reversed_actions["confirmed_actions"].reverse()
        reversed_actions["editorial_permissions"].reverse()
        mutations.append(("reversed_confirmed_action_order", reversed_actions))

        for name, payload in mutations:
            with self.subTest(mutation=name):
                with self.assertRaises(ProjectIntelligenceValidationError):
                    validate_project_intelligence_projection(
                        payload,
                        input_package=self.input_package,
                        projects=self.projects,
                    )

    def test_descriptor_rejects_unsafe_paths_missing_fields_and_unknown_keys(
        self,
    ) -> None:
        cases: dict[str, dict[str, object]] = {}

        unsafe = copy.deepcopy(self.project_descriptor)
        unsafe["project_intelligence"]["action_permissions"][0]["likely_files"] = [
            "../private/secret.py"
        ]
        cases["unsafe_path"] = unsafe

        absolute = copy.deepcopy(self.project_descriptor)
        absolute["project_intelligence"]["action_permissions"][0]["likely_files"] = [
            "/etc/passwd"
        ]
        cases["absolute_path"] = absolute

        html_like = copy.deepcopy(self.project_descriptor)
        html_like["project_intelligence"]["action_permissions"][0]["likely_files"] = [
            "src/output/<script>.py"
        ]
        cases["html_like_path"] = html_like

        control_character = copy.deepcopy(self.project_descriptor)
        control_character["project_intelligence"]["action_permissions"][0][
            "likely_files"
        ] = ["src/output/unsafe\nname.py"]
        cases["control_character_path"] = control_character

        missing = copy.deepcopy(self.project_descriptor)
        del missing["project_intelligence"]["action_permissions"][0]["risk"]
        cases["missing_required"] = missing

        unknown = copy.deepcopy(self.project_descriptor)
        unknown["project_intelligence"]["action_permissions"][0]["safe_but_unknown"] = (
            "must not expand authority"
        )
        cases["unknown_key"] = unknown

        zero_priority = copy.deepcopy(self.project_descriptor)
        zero_priority["project_intelligence"]["action_permissions"][0]["priority"] = 0
        cases["non_positive_priority"] = zero_priority

        unsafe_repo = copy.deepcopy(self.project_descriptor)
        unsafe_repo["repo"] = "../../private-repository"
        cases["unsafe_repository"] = unsafe_repo

        markup = copy.deepcopy(self.project_descriptor)
        markup["project_intelligence"]["action_permissions"][0]["suggested_change"] = (
            "<script>alert(1)</script> Добавить проверяемую секцию."
        )
        cases["markup_in_reader_copy"] = markup

        control = copy.deepcopy(self.project_descriptor)
        control["project_intelligence"]["action_permissions"][0]["risk"] = (
            "Риск содержит управляющий символ \u001b и не должен попасть в отчёт."
        )
        cases["control_in_reader_copy"] = control

        for name, descriptor in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ProjectDescriptorError):
                    self._load_descriptors(descriptor)

        unsafe_diagnostic = copy.deepcopy(self.records["weak"][0])
        unsafe_diagnostic["reason_ru"] = (
            "<script>alert(1)</script> Слабый сигнал остаётся в аудите."
        )
        with self.assertRaises(ProjectIntelligenceValidationError):
            self._build([unsafe_diagnostic])

    def test_audit_cap_and_duplicate_diagnostics_are_deterministic(self) -> None:
        records: list[dict[str, object]] = []
        for index in range(32):
            records.append(
                {
                    "project_name": f"unknown-project-{index:02d}",
                    "permission_id": f"unknown-permission-{index:02d}",
                    "signal_id": f"signal:unknown-{index:02d}",
                    "canonical_thread_ref": f"canonical_thread:unknown-{index:02d}",
                    "status": "watch",
                    "reason_ru": (
                        f"Запись {index + 1} остаётся только в ограниченном аудите."
                    ),
                    "evidence_refs": [],
                }
            )
        before = copy.deepcopy(records)

        forward = self._build(records)
        reverse = self._build(list(reversed(copy.deepcopy(records))))

        self._assert_zero_projection(forward)
        self.assertEqual(len(forward["audit_records"]), 32)
        self.assertEqual(
            len({item["audit_id"] for item in forward["audit_records"]}), 32
        )
        self.assertTrue(
            all(item["selected"] is False for item in forward["audit_records"])
        )
        self.assertEqual(_canonical_bytes(forward), _canonical_bytes(reverse))
        self.assertEqual(records, before)

        overflow = copy.deepcopy(records)
        overflow.append(
            {
                "project_name": "unknown-project-32",
                "permission_id": "unknown-permission-32",
                "signal_id": "signal:unknown-32",
                "canonical_thread_ref": "canonical_thread:unknown-32",
                "status": "watch",
                "reason_ru": "Тридцать третья запись должна явно закрыть переполненный аудит.",
                "evidence_refs": [],
            }
        )
        with self.assertRaisesRegex(
            ProjectIntelligenceValidationError,
            "diagnostic_records exceeds limit 32",
        ):
            self._build(overflow)

        duplicate = copy.deepcopy(self.records["concrete"][0])
        with self.assertRaises(ProjectIntelligenceValidationError):
            self._build([duplicate, copy.deepcopy(duplicate)])

    def test_permutations_are_byte_stable_and_inputs_are_not_mutated(self) -> None:
        input_package = copy.deepcopy(self.input_package)
        projects = copy.deepcopy(self.projects)
        records = copy.deepcopy(self.records["concrete"])
        originals = copy.deepcopy((input_package, projects, records))

        expected = self._build(
            records,
            input_package=input_package,
            projects=projects,
        )
        self.assertEqual((input_package, projects, records), originals)

        permuted_input = copy.deepcopy(self.input_package)
        permuted_input["signal_candidates"].reverse()
        permuted_input["evidence_catalog"].reverse()
        for candidate in permuted_input["signal_candidates"]:
            candidate["canonical_thread_refs"].reverse()
            candidate["evidence_refs"].reverse()
        permuted_projects = list(reversed(copy.deepcopy(self.projects)))
        permuted_records = list(reversed(copy.deepcopy(self.records["concrete"])))
        for record in permuted_records:
            record["evidence_refs"].reverse()
        permuted_originals = copy.deepcopy(
            (permuted_input, permuted_projects, permuted_records)
        )

        actual = self._build(
            permuted_records,
            input_package=permuted_input,
            projects=permuted_projects,
        )

        self.assertEqual(_canonical_bytes(actual), _canonical_bytes(expected))
        self.assertEqual(
            (permuted_input, permuted_projects, permuted_records),
            permuted_originals,
        )

    def test_irx5_editorial_permission_shape_and_evidence_closure_are_exact(
        self,
    ) -> None:
        projection = self._build(self.records["concrete"][:1])
        permissions = project_editorial_permissions(
            projection,
            input_package=self.input_package,
            projects=self.projects,
        )

        self.assertEqual(permissions, projection["editorial_permissions"])
        self.assertEqual(len(permissions), 1)
        permission = permissions[0]
        action = projection["confirmed_actions"][0]
        self.assertEqual(set(permission), EXPECTED_EDITORIAL_PERMISSION_FIELDS)
        self.assertEqual(permission["project_action_ref"], action["project_action_ref"])
        self.assertEqual(permission["signal_id"], action["signal_id"])
        self.assertEqual(permission["project"], action["project_name"])
        self.assertEqual(permission["permission"], "allowed")
        self.assertEqual(permission["evidence_refs"], action["evidence_refs"])
        candidate = next(
            item
            for item in self.input_package["signal_candidates"]
            if item["signal_id"] == permission["signal_id"]
        )
        self.assertTrue(
            set(permission["evidence_refs"]).issubset(candidate["evidence_refs"])
        )

        tampered = copy.deepcopy(projection)
        tampered["editorial_permissions"][0]["evidence_refs"] = [
            "evidence:atlas-primary"
        ]
        with self.assertRaises(ProjectIntelligenceValidationError):
            validate_project_intelligence_projection(
                tampered,
                input_package=self.input_package,
                projects=self.projects,
            )

    def test_public_editorial_permission_extractor_requires_authority_context(
        self,
    ) -> None:
        projection = self._build(self.records["concrete"][:1])
        with self.assertRaises(ProjectIntelligenceValidationError):
            project_editorial_permissions(projection)

        forged = copy.deepcopy(projection)
        for collection in (
            forged["confirmed_actions"],
            forged["audit_records"],
            forged["editorial_permissions"],
        ):
            collection[0]["evidence_refs"] = ["evidence:context-only"]
        with self.assertRaises(ProjectIntelligenceValidationError):
            project_editorial_permissions(forged)
        with self.assertRaises(ProjectIntelligenceValidationError):
            project_editorial_permissions(
                forged,
                input_package=self.input_package,
                projects=self.projects,
            )

        empty_input = copy.deepcopy(self.input_package)
        empty_input["signal_candidates"] = []
        empty_input["evidence_catalog"] = []
        empty = self._build([], input_package=empty_input)
        self.assertEqual(project_editorial_permissions(empty), [])

    def test_generate_load_cache_is_immutable_and_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects_path = self._write_projects(root)
            output_root = root / "runs"

            first = generate_project_intelligence_artifact(
                self.input_package,
                output_root=output_root,
                projects_yaml_path=projects_path,
                diagnostic_records=self.records["concrete"],
            )
            artifact_path = Path(first.artifact_path)
            first_bytes = artifact_path.read_bytes()
            loaded = load_project_intelligence_artifact(artifact_path)
            self.assertEqual(
                loaded,
                self._build(self.records["concrete"]),
            )

            second = generate_project_intelligence_artifact(
                self.input_package,
                output_root=output_root,
                projects_yaml_path=projects_path,
                diagnostic_records=self.records["concrete"],
            )
            self.assertEqual(Path(second.artifact_path), artifact_path)
            self.assertEqual(artifact_path.read_bytes(), first_bytes)
            self.assertTrue(second.cache_hit)
            self.assertTrue(dataclasses.is_dataclass(second))
            with self.assertRaises(dataclasses.FrozenInstanceError):
                second.cache_hit = False

            changed = copy.deepcopy(self.input_package)
            changed["evidence_catalog"][0]["verified_excerpt"] = (
                "Changed evidence bytes for the same immutable run."
            )
            with self.assertRaises(ProjectIntelligenceArtifactError):
                generate_project_intelligence_artifact(
                    changed,
                    output_root=output_root,
                    projects_yaml_path=projects_path,
                    diagnostic_records=self.records["concrete"],
                )

            self.assertEqual(artifact_path.read_bytes(), first_bytes)


if __name__ == "__main__":
    unittest.main()
