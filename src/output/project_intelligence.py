"""Deterministic, evidence-bound Project Intelligence V2 projection.

This module deliberately contains no model, database, clock, environment, or
network access.  Project action authority comes only from versioned project
descriptors and the bounded IRX-5 editorial input package.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

import yaml


PROJECT_INTELLIGENCE_SCHEMA_VERSION = "project_intelligence.v2"
PROJECT_ACTION_PERMISSIONS_SCHEMA_VERSION = "project_action_permissions.v1"
PROJECT_INTELLIGENCE_ARTIFACT_FILENAME = "project-intelligence.v2.json"
PROJECTS_YAML_PATH = Path(__file__).resolve().parents[1] / "config" / "projects.yaml"
EDITORIAL_INPUT_SCHEMA_VERSION = "editorial_intelligence_input.v1"
MAX_CONFIRMED_ACTIONS = 2
MAX_AUDIT_RECORDS = 32
MAX_DIAGNOSTIC_RECORDS = MAX_AUDIT_RECORDS
MAX_INPUT_PACKAGE_BYTES = 80_000
MAX_DESCRIPTOR_BYTES = 512_000
MAX_ARTIFACT_BYTES = 1_000_000

_ROOT_FIELDS = {
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
_PERIOD_FIELDS = {
    "reporting_week",
    "analysis_period_start",
    "analysis_period_end",
}
_PERMISSION_FIELDS = {
    "permission_id",
    "canonical_thread_refs",
    "why_this_project",
    "affected_component",
    "suggested_change",
    "likely_files",
    "effort",
    "acceptance_criteria",
    "risk",
    "priority",
}
_DESCRIPTOR_FIELDS = {
    "schema_version",
    "project_name",
    "project_repo",
    *_PERMISSION_FIELDS,
}
_DIAGNOSTIC_FIELDS = {
    "project_name",
    "permission_id",
    "signal_id",
    "canonical_thread_ref",
    "status",
    "reason_ru",
    "evidence_refs",
}
_ACTION_FIELDS = {
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
_AUDIT_FIELDS = {
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
_EDITORIAL_PERMISSION_FIELDS = {
    "project_action_ref",
    "signal_id",
    "project",
    "permission",
    "evidence_refs",
}
_DIAGNOSTIC_STATUSES = {
    "confirmed",
    "watch",
    "rejected_overlap",
    "learning_only",
    "existing_project_context",
}
_AUDIT_STATUSES = _DIAGNOSTIC_STATUSES | {"no_confirmed_implication"}
_SOURCE_POLICY = (
    "configured_exact_project_permission_thread_and_decision_grade_evidence_only"
)
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{5,199}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_CANONICAL_REF_RE = re.compile(r"^canonical_thread:[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_SIGNAL_ID_RE = re.compile(r"^signal:[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_ISO_WEEK_RE = re.compile(r"^(\d{4})-W(0[1-9]|[1-4]\d|5[0-3])$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EVIDENCE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,299}$")
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LETTER_RE = re.compile(r"[A-Za-zА-Яа-яЁё]")
_REPOSITORY_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,199})$"
)
_SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9_@+./-]+$")
_MARKUP_RE = re.compile(
    r"(?:<\s*(?:!|/?\s*[A-Za-z])|\bon[a-z]{2,}\s*=|javascript\s*:)",
    re.IGNORECASE,
)
_BIDI_CONTROLS = {
    "\u061c",
    "\u200e",
    "\u200f",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
    "\u2066",
    "\u2067",
    "\u2068",
    "\u2069",
}
_EFFORTS = {"XS", "S", "M"}


class ProjectIntelligenceError(ValueError):
    """Base error for the deterministic projection boundary."""


class ProjectDescriptorError(ProjectIntelligenceError):
    """A project action descriptor is malformed or unsafe."""


class ProjectIntelligenceValidationError(ProjectIntelligenceError):
    """A projection, input package, or diagnostic record is invalid."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(str(error) for error in errors if str(error).strip())
        super().__init__(
            "; ".join(self.errors) or "project intelligence validation failed"
        )


class ProjectIntelligenceArtifactError(ProjectIntelligenceError):
    """An immutable artifact cannot be safely loaded or written."""


@dataclass(frozen=True, slots=True)
class ProjectIntelligenceSummary:
    artifact_path: str
    run_id: str
    reporting_week: str
    reader_state: str
    confirmed_action_count: int
    audit_record_count: int
    input_hash: str
    cache_hit: bool = False

    @property
    def path(self) -> str:
        """Compatibility alias used by other artifact summaries."""

        return self.artifact_path


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: yaml.SafeLoader, node: yaml.Node, deep: bool = False
) -> dict:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ProjectDescriptorError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def load_project_action_descriptors(path: str | Path) -> list[dict[str, object]]:
    """Load and normalize only explicitly configured project action permissions."""

    source = Path(path)
    try:
        if source.stat().st_size > MAX_DESCRIPTOR_BYTES:
            raise ProjectDescriptorError("project descriptor file exceeds size limit")
        data = yaml.load(source.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except ProjectDescriptorError:
        raise
    except (OSError, TypeError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        raise ProjectDescriptorError(f"cannot load project descriptors: {exc}") from exc
    if not isinstance(data, Mapping):
        raise ProjectDescriptorError("projects descriptor root must be an object")
    raw_projects = data.get("projects")
    if not isinstance(raw_projects, list):
        raise ProjectDescriptorError("projects must be a list")

    result: list[dict[str, object]] = []
    seen_projects: set[str] = set()
    seen_permissions: set[tuple[str, str]] = set()
    for project_index, raw_project in enumerate(raw_projects):
        path_prefix = f"projects[{project_index}]"
        if not isinstance(raw_project, Mapping):
            raise ProjectDescriptorError(f"{path_prefix} must be an object")
        intelligence = raw_project.get("project_intelligence")
        # Legacy project records are outside this descriptor authority.  They
        # must not become newly invalid merely because this opt-in slice is
        # enabled for a different project.
        if intelligence is None:
            continue
        project_name = _strict_text(
            raw_project.get("name"), f"{path_prefix}.name", 160, ProjectDescriptorError
        )
        project_repo = _strict_text(
            raw_project.get("repo"), f"{path_prefix}.repo", 300, ProjectDescriptorError
        )
        if not _IDENTIFIER_RE.fullmatch(project_name):
            raise ProjectDescriptorError(f"{path_prefix}.name is not a safe identifier")
        if not _REPOSITORY_RE.fullmatch(project_repo):
            raise ProjectDescriptorError(f"{path_prefix}.repo is not a safe repository")
        if project_name in seen_projects:
            raise ProjectDescriptorError("project names must be unique")
        seen_projects.add(project_name)
        if not isinstance(intelligence, Mapping):
            raise ProjectDescriptorError(
                f"{path_prefix}.project_intelligence must be an object"
            )
        _require_exact_keys(
            intelligence,
            {"schema_version", "action_permissions"},
            f"{path_prefix}.project_intelligence",
            ProjectDescriptorError,
        )
        if (
            intelligence.get("schema_version")
            != PROJECT_ACTION_PERMISSIONS_SCHEMA_VERSION
        ):
            raise ProjectDescriptorError(
                f"{path_prefix}.project_intelligence.schema_version mismatch"
            )
        raw_permissions = intelligence.get("action_permissions")
        if not isinstance(raw_permissions, list):
            raise ProjectDescriptorError(
                f"{path_prefix}.project_intelligence.action_permissions must be a list"
            )
        if len(raw_permissions) > 64:
            raise ProjectDescriptorError(
                f"{path_prefix}.project_intelligence.action_permissions exceeds limit"
            )
        for permission_index, raw_permission in enumerate(raw_permissions):
            permission_path = f"{path_prefix}.project_intelligence.action_permissions[{permission_index}]"
            if not isinstance(raw_permission, Mapping):
                raise ProjectDescriptorError(f"{permission_path} must be an object")
            _require_exact_keys(
                raw_permission,
                _PERMISSION_FIELDS,
                permission_path,
                ProjectDescriptorError,
            )
            permission_id = _strict_identifier(
                raw_permission.get("permission_id"),
                f"{permission_path}.permission_id",
                ProjectDescriptorError,
            )
            permission_key = (project_name, permission_id)
            if permission_key in seen_permissions:
                raise ProjectDescriptorError(
                    "permission IDs must be unique per project"
                )
            seen_permissions.add(permission_key)
            canonical_refs = _strict_string_list(
                raw_permission.get("canonical_thread_refs"),
                f"{permission_path}.canonical_thread_refs",
                minimum=1,
                maximum=8,
                error_type=ProjectDescriptorError,
            )
            if any(not _CANONICAL_REF_RE.fullmatch(ref) for ref in canonical_refs):
                raise ProjectDescriptorError(
                    f"{permission_path}.canonical_thread_refs contains an invalid ref"
                )
            likely_files = _strict_string_list(
                raw_permission.get("likely_files"),
                f"{permission_path}.likely_files",
                minimum=1,
                maximum=8,
                error_type=ProjectDescriptorError,
            )
            for likely_file in likely_files:
                _validate_repo_relative_path(likely_file, permission_path)
            acceptance = _strict_string_list(
                raw_permission.get("acceptance_criteria"),
                f"{permission_path}.acceptance_criteria",
                minimum=1,
                maximum=6,
                error_type=ProjectDescriptorError,
            )
            for index, criterion in enumerate(acceptance):
                _require_russian(
                    criterion,
                    f"{permission_path}.acceptance_criteria[{index}]",
                    ProjectDescriptorError,
                )
            effort = _strict_text(
                raw_permission.get("effort"),
                f"{permission_path}.effort",
                8,
                ProjectDescriptorError,
            ).upper()
            if effort not in _EFFORTS:
                raise ProjectDescriptorError(
                    f"{permission_path}.effort must be XS, S, or M"
                )
            priority = raw_permission.get("priority")
            if (
                not isinstance(priority, int)
                or isinstance(priority, bool)
                or not 1 <= priority <= 10_000
            ):
                raise ProjectDescriptorError(
                    f"{permission_path}.priority must be a bounded integer"
                )
            descriptor: dict[str, object] = {
                "schema_version": PROJECT_ACTION_PERMISSIONS_SCHEMA_VERSION,
                "project_name": project_name,
                "project_repo": project_repo,
                "permission_id": permission_id,
                "canonical_thread_refs": sorted(canonical_refs),
                "why_this_project": _russian_text(
                    raw_permission.get("why_this_project"),
                    f"{permission_path}.why_this_project",
                    1_000,
                    ProjectDescriptorError,
                ),
                "affected_component": _strict_text(
                    raw_permission.get("affected_component"),
                    f"{permission_path}.affected_component",
                    300,
                    ProjectDescriptorError,
                ),
                "suggested_change": _russian_text(
                    raw_permission.get("suggested_change"),
                    f"{permission_path}.suggested_change",
                    1_200,
                    ProjectDescriptorError,
                ),
                "likely_files": sorted(likely_files),
                "effort": effort,
                "acceptance_criteria": sorted(acceptance),
                "risk": _russian_text(
                    raw_permission.get("risk"),
                    f"{permission_path}.risk",
                    800,
                    ProjectDescriptorError,
                ),
                "priority": priority,
            }
            result.append(descriptor)
    result.sort(key=_descriptor_sort_key)
    return result


def build_project_intelligence_projection(
    input_package: Mapping[str, object],
    *,
    projects: Sequence[Mapping[str, object]],
    diagnostic_records: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Build one pure, deterministic Project Intelligence V2 projection."""

    package = _validate_input_package(input_package)
    descriptors = _normalize_descriptors(projects)
    diagnostics_omitted = diagnostic_records is None
    records = _normalize_diagnostics(diagnostic_records or ())
    candidates = {item["signal_id"]: item for item in package["signal_candidates"]}
    evidence = {item["evidence_ref"]: item for item in package["evidence_catalog"]}
    descriptor_by_key = {
        (item["project_name"], item["permission_id"]): item for item in descriptors
    }

    if diagnostics_omitted:
        records = _automatic_diagnostics(descriptors, candidates, evidence)
    for index, record in enumerate(records):
        if record["status"] == "confirmed" or not record["evidence_refs"]:
            continue
        candidate = candidates.get(str(record["signal_id"]))
        if candidate is None or not set(record["evidence_refs"]).issubset(
            candidate["evidence_refs"]
        ):
            raise ProjectIntelligenceValidationError(
                (
                    f"diagnostic_records[{index}].evidence_refs are not owned "
                    "by its signal",
                )
            )
        if not set(record["evidence_refs"]).issubset(evidence):
            raise ProjectIntelligenceValidationError(
                (
                    f"diagnostic_records[{index}].evidence_refs are not in "
                    "the input catalog",
                )
            )

    evaluated: list[dict[str, object]] = []
    action_by_audit_id: dict[str, dict[str, object]] = {}
    for record in records:
        descriptor = descriptor_by_key.get(
            (record["project_name"], record["permission_id"])
        )
        audit, action = _evaluate_record(
            record,
            descriptor=descriptor,
            candidates=candidates,
            evidence=evidence,
        )
        evaluated.append(audit)
        if action is not None:
            action_by_audit_id[str(audit["audit_id"])] = action

    evaluated.sort(key=lambda item: _audit_sort_key(item, descriptor_by_key))
    selected_actions: list[dict[str, object]] = []
    selected_authorities: set[tuple[str, str, str]] = set()
    for audit in evaluated:
        action = action_by_audit_id.get(str(audit["audit_id"]))
        if action is None:
            continue
        authority = (
            str(action["project_name"]),
            str(action["permission_id"]),
            str(action["signal_id"]),
        )
        if authority in selected_authorities:
            audit["reason_ru"] = (
                "Действие прошло проверки, но то же разрешение проекта и сигнал уже "
                "представлены одним выбранным действием; дубликат оставлен в аудите."
            )
            continue
        if len(selected_actions) < MAX_CONFIRMED_ACTIONS:
            audit["selected"] = True
            selected_actions.append(action)
            selected_authorities.add(authority)
        else:
            audit["reason_ru"] = (
                "Действие прошло детерминированные проверки, но не выбрано из-за "
                "лимита не более двух подтверждённых проектных действий."
            )

    if not evaluated:
        evaluated = [_no_implication_audit()]
    editorial_permissions = [
        _editorial_permission(action) for action in selected_actions
    ]
    reader_state = (
        "confirmed_actions" if selected_actions else "no_confirmed_implication"
    )
    reader_summary = _reader_summary(len(selected_actions))
    input_hash = _projection_input_hash(package, descriptors, records)
    result: dict[str, object] = {
        "schema_version": PROJECT_INTELLIGENCE_SCHEMA_VERSION,
        "descriptor_schema_version": PROJECT_ACTION_PERMISSIONS_SCHEMA_VERSION,
        "run_id": package["run_id"],
        "reporting_period": dict(package["reporting_period"]),
        "reader_state": reader_state,
        "reader_summary_ru": reader_summary,
        "confirmed_actions": selected_actions,
        "audit_records": evaluated,
        "editorial_permissions": editorial_permissions,
        "source_policy": _SOURCE_POLICY,
        "input_hash": input_hash,
    }
    return validate_project_intelligence_projection(
        result,
        input_package=input_package,
        projects=projects,
    )


def validate_project_intelligence_projection(
    payload: Mapping[str, object],
    *,
    input_package: Mapping[str, object] | None = None,
    projects: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Validate a closed projection and return a detached normalized copy."""

    errors: list[str] = []
    if not isinstance(payload, Mapping):
        raise ProjectIntelligenceValidationError(("projection must be an object",))
    value = _json_copy(payload, "projection")
    _collect_exact_keys(value, _ROOT_FIELDS, "root", errors)
    if value.get("schema_version") != PROJECT_INTELLIGENCE_SCHEMA_VERSION:
        errors.append("schema_version mismatch")
    if (
        value.get("descriptor_schema_version")
        != PROJECT_ACTION_PERMISSIONS_SCHEMA_VERSION
    ):
        errors.append("descriptor_schema_version mismatch")
    run_id = value.get("run_id")
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        errors.append("run_id is invalid")
    period = _validate_period_value(value.get("reporting_period"), errors)
    state = value.get("reader_state")
    if not isinstance(state, str) or state not in {
        "confirmed_actions",
        "no_confirmed_implication",
    }:
        errors.append("reader_state is invalid")
    _collect_russian_text(
        value.get("reader_summary_ru"), "reader_summary_ru", errors, 800
    )
    if value.get("source_policy") != _SOURCE_POLICY:
        errors.append("source_policy mismatch")
    if not isinstance(value.get("input_hash"), str) or not _HASH_RE.fullmatch(
        str(value.get("input_hash") or "")
    ):
        errors.append("input_hash is invalid")

    package: dict[str, object] | None = None
    input_context_supplied = input_package is not None
    candidate_by_id: dict[str, dict[str, object]] = {}
    evidence_by_id: dict[str, dict[str, object]] = {}
    if input_package is not None:
        try:
            package = _validate_input_package(input_package)
        except ProjectIntelligenceValidationError as exc:
            errors.extend(f"input_package: {item}" for item in exc.errors)
        if package is not None:
            if value.get("run_id") != package.get("run_id"):
                errors.append("run_id does not match input package")
            if period != package.get("reporting_period"):
                errors.append("reporting_period does not match input package")
            candidate_by_id = {
                item["signal_id"]: item for item in package["signal_candidates"]
            }
            evidence_by_id = {
                item["evidence_ref"]: item for item in package["evidence_catalog"]
            }

    descriptor_by_key: dict[tuple[object, object], dict[str, object]] = {}
    project_context_supplied = projects is not None
    if projects is not None:
        try:
            normalized_projects = _normalize_descriptors(projects)
            descriptor_by_key = {
                (item["project_name"], item["permission_id"]): item
                for item in normalized_projects
            }
        except ProjectIntelligenceError as exc:
            errors.append(f"projects: {exc}")

    raw_actions = value.get("confirmed_actions")
    actions = raw_actions if isinstance(raw_actions, list) else []
    if not isinstance(raw_actions, list):
        errors.append("confirmed_actions must be a list")
    if len(actions) > MAX_CONFIRMED_ACTIONS:
        errors.append("confirmed_actions exceeds limit 2")
    action_refs: set[str] = set()
    action_keys: set[tuple[str, str, str, str]] = set()
    action_identity_order: list[tuple[str, str, str, str]] = []
    action_authorities: set[tuple[str, str, str]] = set()
    action_by_identity: dict[tuple[str, str, str, str], Mapping[str, object]] = {}
    for index, raw_action in enumerate(actions):
        path = f"confirmed_actions[{index}]"
        if not isinstance(raw_action, Mapping):
            errors.append(f"{path} must be an object")
            continue
        action = dict(raw_action)
        _collect_exact_keys(action, _ACTION_FIELDS, path, errors)
        _validate_action(
            action,
            path,
            errors,
            descriptor_by_key=descriptor_by_key,
            candidate_by_id=candidate_by_id,
            evidence_by_id=evidence_by_id,
            project_context_supplied=project_context_supplied,
            input_context_supplied=input_context_supplied,
        )
        action_ref = str(action.get("project_action_ref") or "")
        if action_ref in action_refs:
            errors.append(f"{path}.project_action_ref is duplicated")
        action_refs.add(action_ref)
        identity = _action_identity(action)
        if identity in action_keys:
            errors.append(f"{path} duplicates a confirmed action identity")
        action_keys.add(identity)
        action_identity_order.append(identity)
        action_by_identity[identity] = action
        authority = identity[:3]
        if authority in action_authorities:
            errors.append(f"{path} duplicates a project permission/signal action")
        action_authorities.add(authority)
    if all(
        isinstance(item, Mapping)
        and isinstance(item.get("priority"), int)
        and not isinstance(item.get("priority"), bool)
        for item in actions
    ):
        expected_action_order = [
            _action_identity(item)
            for item in sorted(
                actions,
                key=lambda item: (
                    int(item["priority"]),
                    str(item.get("project_name") or ""),
                    str(item.get("permission_id") or ""),
                    str(item.get("signal_id") or ""),
                    str(item.get("canonical_thread_ref") or ""),
                ),
            )
        ]
        if action_identity_order != expected_action_order:
            errors.append("confirmed_actions order is not deterministic")

    raw_audits = value.get("audit_records")
    audits = raw_audits if isinstance(raw_audits, list) else []
    if not isinstance(raw_audits, list):
        errors.append("audit_records must be a list")
    if not audits:
        errors.append("audit_records must not be empty")
    if len(audits) > MAX_AUDIT_RECORDS:
        errors.append("audit_records exceeds limit")
    audit_ids: set[str] = set()
    selected_keys: set[tuple[str, str, str, str]] = set()
    selected_audits: dict[tuple[str, str, str, str], Mapping[str, object]] = {}
    sentinel_count = 0
    for index, raw_audit in enumerate(audits):
        path = f"audit_records[{index}]"
        if not isinstance(raw_audit, Mapping):
            errors.append(f"{path} must be an object")
            continue
        audit = dict(raw_audit)
        _collect_exact_keys(audit, _AUDIT_FIELDS, path, errors)
        audit_id = audit.get("audit_id")
        if (
            not isinstance(audit_id, str)
            or not audit_id
            or audit_id != audit_id.strip()
        ):
            errors.append(f"{path}.audit_id is invalid")
        elif audit_id in audit_ids:
            errors.append(f"{path}.audit_id is duplicated")
        else:
            audit_ids.add(audit_id)
        status = audit.get("status")
        if not isinstance(status, str) or status not in _AUDIT_STATUSES:
            errors.append(f"{path}.status is invalid")
        _collect_russian_text(
            audit.get("reason_ru"), f"{path}.reason_ru", errors, 1_200
        )
        refs = _collect_string_list(
            audit.get("evidence_refs"), f"{path}.evidence_refs", errors, 0, 12
        )
        if any(not _EVIDENCE_REF_RE.fullmatch(ref) for ref in refs):
            errors.append(f"{path}.evidence_refs contains an unsafe ref")
        if not isinstance(audit.get("selected"), bool):
            errors.append(f"{path}.selected must be a boolean")
        if status == "no_confirmed_implication":
            sentinel_count += 1
            if audit.get("audit_id") != "audit:no-confirmed-implication":
                errors.append(f"{path}.audit_id is not the canonical sentinel ref")
            if (
                any(
                    audit.get(field)
                    for field in (
                        "project_name",
                        "permission_id",
                        "signal_id",
                        "canonical_thread_ref",
                    )
                )
                or refs
                or audit.get("selected") is not False
            ):
                errors.append(f"{path} sentinel must not claim an action or evidence")
        else:
            for field in (
                "project_name",
                "permission_id",
                "signal_id",
                "canonical_thread_ref",
            ):
                if not isinstance(audit.get(field), str) or not str(audit.get(field)):
                    errors.append(f"{path}.{field} is invalid")
            if not _IDENTIFIER_RE.fullmatch(str(audit.get("project_name") or "")):
                errors.append(f"{path}.project_name is unsafe")
            if not _IDENTIFIER_RE.fullmatch(str(audit.get("permission_id") or "")):
                errors.append(f"{path}.permission_id is unsafe")
            if not _SIGNAL_ID_RE.fullmatch(str(audit.get("signal_id") or "")):
                errors.append(f"{path}.signal_id is unsafe")
            if not _CANONICAL_REF_RE.fullmatch(
                str(audit.get("canonical_thread_ref") or "")
            ):
                errors.append(f"{path}.canonical_thread_ref is unsafe")
            if audit.get("selected") is True:
                if status != "confirmed":
                    errors.append(f"{path} selected audit must be confirmed")
                identity = _audit_identity(audit)
                if identity in selected_keys:
                    errors.append(f"{path} duplicates a selected audit identity")
                selected_keys.add(identity)
                selected_audits[identity] = audit
            expected_audit_id = _stable_ref("audit", *_audit_identity(audit))
            if audit.get("audit_id") != expected_audit_id:
                errors.append(f"{path}.audit_id is not the deterministic audit ref")
            audit_candidate = candidate_by_id.get(str(audit.get("signal_id") or ""))
            if audit_candidate is not None:
                owned_refs = set(audit_candidate["evidence_refs"])
                if not set(refs).issubset(owned_refs):
                    errors.append(f"{path}.evidence_refs are not owned by its signal")
            elif input_context_supplied and refs:
                errors.append(
                    f"{path}.evidence_refs cannot cite evidence without a bound signal"
                )
            if input_context_supplied and not set(refs).issubset(evidence_by_id):
                errors.append(f"{path}.evidence_refs are not in the input catalog")
            if status == "confirmed":
                audit_descriptor = descriptor_by_key.get(
                    (
                        _mapping_key_text(audit.get("project_name")),
                        _mapping_key_text(audit.get("permission_id")),
                    )
                )
                if project_context_supplied and audit_descriptor is None:
                    errors.append(f"{path} confirmed audit has no descriptor")
                elif (
                    audit_descriptor is not None
                    and audit.get("canonical_thread_ref")
                    not in audit_descriptor["canonical_thread_refs"]
                ):
                    errors.append(f"{path} confirmed audit thread is not permitted")
                if audit_candidate is None:
                    if input_context_supplied:
                        errors.append(f"{path} confirmed audit has no signal")
                else:
                    if (
                        audit.get("canonical_thread_ref")
                        not in audit_candidate["canonical_thread_refs"]
                    ):
                        errors.append(
                            f"{path} confirmed audit thread is not signal-owned"
                        )
                    eligible_refs = set(
                        _eligible_evidence_refs(audit_candidate, evidence_by_id)
                    )
                    if not refs or not set(refs).issubset(eligible_refs):
                        errors.append(f"{path} confirmed audit fails evidence closure")
    if selected_keys != action_keys:
        errors.append("selected audit records must exactly match confirmed_actions")
    for identity in selected_keys & action_keys:
        if selected_audits[identity].get("evidence_refs") != action_by_identity[
            identity
        ].get("evidence_refs"):
            errors.append("selected audit evidence must exactly match its action")
    if input_context_supplied and project_context_supplied:
        actionable_audits = sorted(
            (
                dict(item)
                for item in audits
                if isinstance(item, Mapping)
                and _confirmed_audit_is_actionable(
                    item,
                    descriptor_by_key=descriptor_by_key,
                    candidate_by_id=candidate_by_id,
                    evidence_by_id=evidence_by_id,
                )
            ),
            key=lambda item: _audit_sort_key(item, descriptor_by_key),
        )
        expected_selected_order: list[tuple[str, str, str, str]] = []
        expected_authorities: set[tuple[str, str, str]] = set()
        for audit in actionable_audits:
            identity = _audit_identity(audit)
            authority = identity[:3]
            if authority in expected_authorities:
                continue
            if len(expected_selected_order) >= MAX_CONFIRMED_ACTIONS:
                break
            expected_authorities.add(authority)
            expected_selected_order.append(identity)
        if action_identity_order != expected_selected_order:
            errors.append(
                "confirmed actions must preserve the deterministic first-two "
                "distinct authority order"
            )
        if selected_keys != set(expected_selected_order):
            errors.append(
                "selected audits must be the deterministic first two distinct "
                "confirmed authorities"
            )
    if actions and sentinel_count:
        errors.append("confirmed actions cannot coexist with no-implication sentinel")
    if sentinel_count > 1:
        errors.append("no-implication sentinel must be unique")
    if not actions and not sentinel_count and not audits:
        errors.append("empty projection requires no-implication sentinel")
    expected_state = "confirmed_actions" if actions else "no_confirmed_implication"
    if state != expected_state:
        errors.append("reader_state does not match confirmed actions")
    if value.get("reader_summary_ru") != _reader_summary(len(actions)):
        errors.append("reader_summary_ru does not match confirmed action count")

    raw_permissions = value.get("editorial_permissions")
    permissions = raw_permissions if isinstance(raw_permissions, list) else []
    if not isinstance(raw_permissions, list):
        errors.append("editorial_permissions must be a list")
    if len(permissions) != len(actions):
        errors.append("editorial_permissions must exactly cover confirmed actions")
    for index, raw_permission in enumerate(permissions):
        path = f"editorial_permissions[{index}]"
        if not isinstance(raw_permission, Mapping):
            errors.append(f"{path} must be an object")
            continue
        permission = dict(raw_permission)
        _collect_exact_keys(permission, _EDITORIAL_PERMISSION_FIELDS, path, errors)
        if index < len(actions) and permission != _editorial_permission(actions[index]):
            errors.append(f"{path} does not match its confirmed action")
    if errors:
        raise ProjectIntelligenceValidationError(errors)
    return value


def project_editorial_permissions(
    payload: Mapping[str, object],
    *,
    input_package: Mapping[str, object] | None = None,
    projects: Sequence[Mapping[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Return detached IRX-5-shaped permissions for confirmed actions only."""

    preliminary = validate_project_intelligence_projection(payload)
    if preliminary["confirmed_actions"] and (input_package is None or projects is None):
        raise ProjectIntelligenceValidationError(
            (
                "non-empty editorial permissions require the exact input package "
                "and project descriptors",
            )
        )
    validated = validate_project_intelligence_projection(
        preliminary,
        input_package=input_package,
        projects=projects,
    )
    return [dict(item) for item in validated["editorial_permissions"]]


def load_project_intelligence_artifact(path: str | Path) -> dict[str, object]:
    """Strictly load one Project Intelligence V2 JSON artifact."""

    source = Path(path)
    try:
        if source.stat().st_size > MAX_ARTIFACT_BYTES:
            raise ProjectIntelligenceArtifactError(
                "project artifact exceeds size limit"
            )
        raw = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProjectIntelligenceArtifactError(
            f"cannot read project artifact: {exc}"
        ) from exc
    try:
        payload = _strict_json_loads(raw)
    except (json.JSONDecodeError, ProjectIntelligenceValidationError) as exc:
        raise ProjectIntelligenceArtifactError(
            f"invalid project artifact JSON: {exc}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ProjectIntelligenceArtifactError(
            "project artifact root must be an object"
        )
    return validate_project_intelligence_projection(payload)


def generate_project_intelligence_artifact(
    input_package: Mapping[str, object],
    *,
    output_root: str | Path,
    projects_yaml_path: str | Path = PROJECTS_YAML_PATH,
    diagnostic_records: Sequence[Mapping[str, object]] | None = None,
) -> ProjectIntelligenceSummary:
    """Generate or exactly reuse one immutable run-scoped artifact."""

    descriptors = load_project_action_descriptors(projects_yaml_path)
    projection = build_project_intelligence_projection(
        input_package,
        projects=descriptors,
        diagnostic_records=diagnostic_records,
    )
    run_id = str(projection["run_id"])
    if not _RUN_ID_RE.fullmatch(run_id):
        raise ProjectIntelligenceArtifactError("unsafe run_id")
    artifact_path = (
        Path(output_root) / run_id / "project" / PROJECT_INTELLIGENCE_ARTIFACT_FILENAME
    )
    encoded = _canonical_json_bytes(projection) + b"\n"
    cache_hit = False
    if artifact_path.exists():
        existing = load_project_intelligence_artifact(artifact_path)
        if existing != projection or artifact_path.read_bytes() != encoded:
            raise ProjectIntelligenceArtifactError(
                "immutable project artifact differs; create a new run_id"
            )
        cache_hit = True
    else:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_create_once(artifact_path, encoded)
        if artifact_path.read_bytes() != encoded:
            raise ProjectIntelligenceArtifactError(
                "project artifact write verification failed"
            )
    return _summary(projection, artifact_path, cache_hit=cache_hit)


def _validate_input_package(value: Mapping[str, object]) -> dict[str, object]:
    errors: list[str] = []
    if not isinstance(value, Mapping):
        raise ProjectIntelligenceValidationError(("input_package must be an object",))
    package = _json_copy(value, "input_package")
    if len(_canonical_json_bytes(package).decode("utf-8")) > MAX_INPUT_PACKAGE_BYTES:
        errors.append("input_package exceeds bounded size limit")
    if package.get("schema_version") != EDITORIAL_INPUT_SCHEMA_VERSION:
        errors.append("input_package.schema_version mismatch")
    run_id = package.get("run_id")
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        errors.append("input_package.run_id is invalid")
    period = _validate_period_value(
        package.get("reporting_period"), errors, prefix="input_package."
    )

    raw_candidates = package.get("signal_candidates")
    candidates: list[dict[str, object]] = []
    seen_signals: set[str] = set()
    if not isinstance(raw_candidates, list):
        errors.append("input_package.signal_candidates must be a list")
    else:
        if len(raw_candidates) > 8:
            errors.append("input_package.signal_candidates exceeds IRX-5 bound")
        for index, raw_candidate in enumerate(raw_candidates):
            path = f"input_package.signal_candidates[{index}]"
            if not isinstance(raw_candidate, Mapping):
                errors.append(f"{path} must be an object")
                continue
            signal_id = raw_candidate.get("signal_id")
            if not isinstance(signal_id, str) or not _SIGNAL_ID_RE.fullmatch(signal_id):
                errors.append(f"{path}.signal_id is invalid")
                continue
            if signal_id in seen_signals:
                errors.append(f"{path}.signal_id is duplicated")
            seen_signals.add(signal_id)
            canonical_refs = _collect_string_list(
                raw_candidate.get("canonical_thread_refs"),
                f"{path}.canonical_thread_refs",
                errors,
                1,
                8,
            )
            if any(not _CANONICAL_REF_RE.fullmatch(ref) for ref in canonical_refs):
                errors.append(f"{path}.canonical_thread_refs contains an invalid ref")
            evidence_refs = _collect_string_list(
                raw_candidate.get("evidence_refs"),
                f"{path}.evidence_refs",
                errors,
                0,
                12,
            )
            if any(not _EVIDENCE_REF_RE.fullmatch(ref) for ref in evidence_refs):
                errors.append(f"{path}.evidence_refs contains an unsafe ref")
            confidence = raw_candidate.get("confidence_ceiling")
            if not isinstance(confidence, str) or confidence not in {
                "low",
                "medium",
                "high",
            }:
                errors.append(f"{path}.confidence_ceiling is invalid")
            fingerprint_source = _json_copy(raw_candidate, path)
            for unordered_field in (
                "allowed_decisions",
                "canonical_thread_refs",
                "evidence_refs",
                "source_thread_refs",
            ):
                unordered_value = fingerprint_source.get(unordered_field)
                if isinstance(unordered_value, list):
                    try:
                        fingerprint_source[unordered_field] = sorted(unordered_value)
                    except TypeError:
                        # The strict authority fields above report malformed
                        # values; the fingerprint remains deterministic JSON.
                        pass
            candidates.append(
                {
                    "signal_id": signal_id,
                    "canonical_thread_refs": sorted(canonical_refs),
                    "confidence_ceiling": confidence,
                    "evidence_refs": sorted(evidence_refs),
                    "fingerprint": _canonical_value(fingerprint_source),
                }
            )

    raw_evidence = package.get("evidence_catalog")
    catalog: list[dict[str, object]] = []
    seen_evidence: set[str] = set()
    if not isinstance(raw_evidence, list):
        errors.append("input_package.evidence_catalog must be a list")
    else:
        if len(raw_evidence) > 24:
            errors.append("input_package.evidence_catalog exceeds IRX-5 bound")
        for index, raw_item in enumerate(raw_evidence):
            path = f"input_package.evidence_catalog[{index}]"
            if not isinstance(raw_item, Mapping):
                errors.append(f"{path} must be an object")
                continue
            evidence_ref = raw_item.get("evidence_ref")
            if not isinstance(evidence_ref, str) or not _EVIDENCE_REF_RE.fullmatch(
                evidence_ref
            ):
                errors.append(f"{path}.evidence_ref is invalid")
                continue
            if evidence_ref in seen_evidence:
                errors.append(f"{path}.evidence_ref is duplicated")
            seen_evidence.add(evidence_ref)
            for field in ("decision_grade", "context_only"):
                if not isinstance(raw_item.get(field), bool):
                    errors.append(f"{path}.{field} must be a boolean")
            catalog.append(
                {
                    "evidence_ref": evidence_ref,
                    "decision_grade": raw_item.get("decision_grade") is True,
                    "context_only": raw_item.get("context_only") is True,
                    "fingerprint": _canonical_value(raw_item),
                }
            )
    evidence_ids = {item["evidence_ref"] for item in catalog}
    for candidate in candidates:
        if not set(candidate["evidence_refs"]).issubset(evidence_ids):
            errors.append(
                f"input_package signal {candidate['signal_id']} contains unknown evidence_refs"
            )
    if errors:
        raise ProjectIntelligenceValidationError(errors)
    candidates.sort(key=lambda item: str(item["signal_id"]))
    catalog.sort(key=lambda item: str(item["evidence_ref"]))
    return {
        "schema_version": EDITORIAL_INPUT_SCHEMA_VERSION,
        "run_id": run_id,
        "reporting_period": period,
        "signal_candidates": candidates,
        "evidence_catalog": catalog,
    }


def _normalize_descriptors(
    projects: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    if isinstance(projects, (str, bytes)) or not isinstance(projects, Sequence):
        raise ProjectDescriptorError("projects must be a descriptor sequence")
    result: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(projects):
        path = f"projects[{index}]"
        if not isinstance(raw, Mapping):
            raise ProjectDescriptorError(f"{path} must be an object")
        _require_exact_keys(raw, _DESCRIPTOR_FIELDS, path, ProjectDescriptorError)
        item = _json_copy(raw, path)
        if item.get("schema_version") != PROJECT_ACTION_PERMISSIONS_SCHEMA_VERSION:
            raise ProjectDescriptorError(f"{path}.schema_version mismatch")
        key = (
            str(item.get("project_name") or ""),
            str(item.get("permission_id") or ""),
        )
        if key in seen:
            raise ProjectDescriptorError(
                "descriptor project/permission keys must be unique"
            )
        seen.add(key)
        # Reuse the strict field checks by validating the normalized values.
        _strict_text(
            item.get("project_name"),
            f"{path}.project_name",
            160,
            ProjectDescriptorError,
        )
        _strict_text(
            item.get("project_repo"),
            f"{path}.project_repo",
            300,
            ProjectDescriptorError,
        )
        if not _IDENTIFIER_RE.fullmatch(str(item.get("project_name"))):
            raise ProjectDescriptorError(
                f"{path}.project_name is not a safe identifier"
            )
        if not _REPOSITORY_RE.fullmatch(str(item.get("project_repo"))):
            raise ProjectDescriptorError(
                f"{path}.project_repo is not a safe repository"
            )
        _strict_identifier(
            item.get("permission_id"), f"{path}.permission_id", ProjectDescriptorError
        )
        refs = _strict_string_list(
            item.get("canonical_thread_refs"),
            f"{path}.canonical_thread_refs",
            minimum=1,
            maximum=8,
            error_type=ProjectDescriptorError,
        )
        if any(not _CANONICAL_REF_RE.fullmatch(ref) for ref in refs):
            raise ProjectDescriptorError(f"{path}.canonical_thread_refs is invalid")
        files = _strict_string_list(
            item.get("likely_files"),
            f"{path}.likely_files",
            minimum=1,
            maximum=8,
            error_type=ProjectDescriptorError,
        )
        for file_path in files:
            _validate_repo_relative_path(file_path, path)
        acceptance = _strict_string_list(
            item.get("acceptance_criteria"),
            f"{path}.acceptance_criteria",
            minimum=1,
            maximum=6,
            error_type=ProjectDescriptorError,
        )
        for criterion in acceptance:
            _require_russian(
                criterion, f"{path}.acceptance_criteria", ProjectDescriptorError
            )
        for field, maximum in (
            ("why_this_project", 1_000),
            ("suggested_change", 1_200),
            ("risk", 800),
        ):
            _russian_text(
                item.get(field), f"{path}.{field}", maximum, ProjectDescriptorError
            )
        _strict_text(
            item.get("affected_component"),
            f"{path}.affected_component",
            300,
            ProjectDescriptorError,
        )
        if (
            not isinstance(item.get("effort"), str)
            or item.get("effort") not in _EFFORTS
        ):
            raise ProjectDescriptorError(f"{path}.effort is invalid")
        priority = item.get("priority")
        if (
            not isinstance(priority, int)
            or isinstance(priority, bool)
            or not 1 <= priority <= 10_000
        ):
            raise ProjectDescriptorError(f"{path}.priority is invalid")
        item["canonical_thread_refs"] = sorted(refs)
        item["likely_files"] = sorted(files)
        item["acceptance_criteria"] = sorted(acceptance)
        result.append(item)
    result.sort(key=_descriptor_sort_key)
    return result


def _normalize_diagnostics(
    records: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise ProjectIntelligenceValidationError(
            ("diagnostic_records must be a sequence",)
        )
    if len(records) > MAX_DIAGNOSTIC_RECORDS:
        raise ProjectIntelligenceValidationError(
            (f"diagnostic_records exceeds limit {MAX_DIAGNOSTIC_RECORDS}",)
        )
    result: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for index, raw in enumerate(records):
        path = f"diagnostic_records[{index}]"
        if not isinstance(raw, Mapping):
            raise ProjectIntelligenceValidationError((f"{path} must be an object",))
        _require_exact_keys(
            raw, _DIAGNOSTIC_FIELDS, path, ProjectIntelligenceValidationError
        )
        item = _json_copy(raw, path)
        for field, maximum in (
            ("project_name", 160),
            ("permission_id", 200),
            ("signal_id", 220),
            ("canonical_thread_ref", 220),
        ):
            _strict_text(
                item.get(field),
                f"{path}.{field}",
                maximum,
                ProjectIntelligenceValidationError,
            )
        if not _IDENTIFIER_RE.fullmatch(str(item["project_name"])):
            raise ProjectIntelligenceValidationError(
                (f"{path}.project_name is not a safe identifier",)
            )
        if not _IDENTIFIER_RE.fullmatch(str(item["permission_id"])):
            raise ProjectIntelligenceValidationError(
                (f"{path}.permission_id is not a safe identifier",)
            )
        if not _SIGNAL_ID_RE.fullmatch(str(item["signal_id"])):
            raise ProjectIntelligenceValidationError((f"{path}.signal_id is invalid",))
        if not _CANONICAL_REF_RE.fullmatch(str(item["canonical_thread_ref"])):
            raise ProjectIntelligenceValidationError(
                (f"{path}.canonical_thread_ref is invalid",)
            )
        if (
            not isinstance(item.get("status"), str)
            or item.get("status") not in _DIAGNOSTIC_STATUSES
        ):
            raise ProjectIntelligenceValidationError((f"{path}.status is invalid",))
        _russian_text(
            item.get("reason_ru"),
            f"{path}.reason_ru",
            1_200,
            ProjectIntelligenceValidationError,
        )
        refs = _strict_string_list(
            item.get("evidence_refs"),
            f"{path}.evidence_refs",
            minimum=0,
            maximum=12,
            error_type=ProjectIntelligenceValidationError,
        )
        if any(not _EVIDENCE_REF_RE.fullmatch(ref) for ref in refs):
            raise ProjectIntelligenceValidationError(
                (f"{path}.evidence_refs contains an unsafe ref",)
            )
        item["evidence_refs"] = sorted(refs)
        identity = _audit_identity(item)
        if identity in seen:
            raise ProjectIntelligenceValidationError(
                (f"{path} duplicates a diagnostic identity",)
            )
        seen.add(identity)
        result.append(item)
    result.sort(
        key=lambda item: (
            *_audit_identity(item),
            str(item["status"]),
            str(item["reason_ru"]),
        )
    )
    return result


def _automatic_diagnostics(
    descriptors: Sequence[Mapping[str, object]],
    candidates: Mapping[str, Mapping[str, object]],
    evidence: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for descriptor in descriptors:
        allowed_refs = set(descriptor["canonical_thread_refs"])
        for candidate in candidates.values():
            matches = sorted(allowed_refs & set(candidate["canonical_thread_refs"]))
            for canonical_ref in matches:
                eligible = _eligible_evidence_refs(candidate, evidence)
                confidence_allowed = candidate["confidence_ceiling"] in {
                    "medium",
                    "high",
                }
                status = "confirmed" if confidence_allowed and eligible else "watch"
                if status == "confirmed":
                    reason = (
                        "Точное настроенное разрешение совпало с канонической темой "
                        "и допустимыми доказательствами сигнала."
                    )
                    record_refs = eligible
                else:
                    reasons: list[str] = []
                    if not confidence_allowed:
                        reasons.append("уверенность сигнала ниже допустимой границы")
                    if not eligible:
                        reasons.append(
                            "decision-grade non-context доказательства отсутствуют"
                        )
                    reason = (
                        "Точная каноническая тема совпала с разрешением, но "
                        + " и ".join(reasons)
                        + "; запись оставлена только для наблюдения."
                    )
                    record_refs = sorted(
                        ref for ref in candidate["evidence_refs"] if ref in evidence
                    )
                records.append(
                    {
                        "project_name": descriptor["project_name"],
                        "permission_id": descriptor["permission_id"],
                        "signal_id": candidate["signal_id"],
                        "canonical_thread_ref": canonical_ref,
                        "status": status,
                        "reason_ru": reason,
                        "evidence_refs": record_refs,
                    }
                )
    return _normalize_diagnostics(records)


def _evaluate_record(
    record: Mapping[str, object],
    *,
    descriptor: Mapping[str, object] | None,
    candidates: Mapping[str, Mapping[str, object]],
    evidence: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, object], dict[str, object] | None]:
    status = str(record["status"])
    reason = str(record["reason_ru"])
    candidate = candidates.get(str(record["signal_id"]))
    requested_refs = list(record["evidence_refs"])
    failure: str | None = None
    # Non-actionable diagnostic classifications are already deterministic host
    # decisions. Preserve them verbatim in audit instead of reinterpreting a
    # weak/rejected/learning/context record as an attempted confirmation.
    if status != "confirmed":
        pass
    elif descriptor is None:
        failure = "Проект или разрешение не настроены; широкое совпадение отклонено."
        status = "rejected_overlap"
    elif candidate is None:
        failure = "Сигнал отсутствует в ограниченном редакционном входе этого запуска."
        status = "rejected_overlap"
    elif record["canonical_thread_ref"] not in descriptor["canonical_thread_refs"]:
        failure = (
            "Каноническая тема не совпадает с точным настроенным разрешением проекта."
        )
        status = "rejected_overlap"
    elif record["canonical_thread_ref"] not in candidate["canonical_thread_refs"]:
        failure = "Каноническая тема не принадлежит указанному сигналу."
        status = "rejected_overlap"

    eligible = _eligible_evidence_refs(candidate, evidence) if candidate else []
    if failure is None and status == "confirmed":
        if candidate["confidence_ceiling"] not in {"medium", "high"}:
            failure = (
                "Уверенность сигнала ниже допустимой границы для проектного действия."
            )
            status = "watch"
        elif not requested_refs:
            failure = "Подтверждённое действие требует хотя бы одно допустимое доказательство."
            status = "watch"
        elif not set(requested_refs).issubset(set(eligible)):
            failure = "Доказательства не замкнуты на decision-grade non-context записи указанного сигнала."
            status = "watch"
    if failure is not None:
        reason = failure

    audit_id = _stable_ref(
        "audit",
        str(record["project_name"]),
        str(record["permission_id"]),
        str(record["signal_id"]),
        str(record["canonical_thread_ref"]),
    )
    audit_refs = sorted(
        ref
        for ref in requested_refs
        if candidate is not None
        and ref in set(candidate["evidence_refs"])
        and ref in evidence
    )
    audit: dict[str, object] = {
        "audit_id": audit_id,
        "project_name": record["project_name"],
        "permission_id": record["permission_id"],
        "signal_id": record["signal_id"],
        "canonical_thread_ref": record["canonical_thread_ref"],
        "status": status,
        "reason_ru": reason,
        "evidence_refs": audit_refs,
        "selected": False,
    }
    if status != "confirmed" or descriptor is None or candidate is None:
        return audit, None
    action_ref = _stable_ref(
        "project_action",
        str(descriptor["project_name"]),
        str(descriptor["permission_id"]),
        str(record["signal_id"]),
        str(record["canonical_thread_ref"]),
    )
    action: dict[str, object] = {
        "project_action_ref": action_ref,
        "project_name": descriptor["project_name"],
        "project_repo": descriptor["project_repo"],
        "permission_id": descriptor["permission_id"],
        "signal_id": record["signal_id"],
        "canonical_thread_ref": record["canonical_thread_ref"],
        "why_this_project": descriptor["why_this_project"],
        "affected_component": descriptor["affected_component"],
        "suggested_change": descriptor["suggested_change"],
        "likely_files": list(descriptor["likely_files"]),
        "effort": descriptor["effort"],
        "acceptance_criteria": list(descriptor["acceptance_criteria"]),
        "risk": descriptor["risk"],
        "priority": descriptor["priority"],
        "confidence": candidate["confidence_ceiling"],
        "evidence_refs": sorted(requested_refs),
        "status": "confirmed",
    }
    return audit, action


def _eligible_evidence_refs(
    candidate: Mapping[str, object] | None,
    evidence: Mapping[str, Mapping[str, object]],
) -> list[str]:
    if candidate is None:
        return []
    return sorted(
        ref
        for ref in candidate["evidence_refs"]
        if ref in evidence
        and evidence[ref].get("decision_grade") is True
        and evidence[ref].get("context_only") is False
    )


def _confirmed_audit_is_actionable(
    audit: Mapping[str, object],
    *,
    descriptor_by_key: Mapping[tuple[object, object], Mapping[str, object]],
    candidate_by_id: Mapping[str, Mapping[str, object]],
    evidence_by_id: Mapping[str, Mapping[str, object]],
) -> bool:
    if audit.get("status") != "confirmed":
        return False
    project_name = _mapping_key_text(audit.get("project_name"))
    permission_id = _mapping_key_text(audit.get("permission_id"))
    signal_id = _mapping_key_text(audit.get("signal_id"))
    canonical_ref = _mapping_key_text(audit.get("canonical_thread_ref"))
    descriptor = descriptor_by_key.get((project_name, permission_id))
    candidate = candidate_by_id.get(signal_id)
    refs = audit.get("evidence_refs")
    if descriptor is None or candidate is None or not isinstance(refs, list):
        return False
    if canonical_ref not in descriptor["canonical_thread_refs"]:
        return False
    if canonical_ref not in candidate["canonical_thread_refs"]:
        return False
    if candidate.get("confidence_ceiling") not in {"medium", "high"}:
        return False
    if not refs or not all(isinstance(ref, str) for ref in refs):
        return False
    return set(refs).issubset(_eligible_evidence_refs(candidate, evidence_by_id))


def _validate_action(
    action: Mapping[str, object],
    path: str,
    errors: list[str],
    *,
    descriptor_by_key: Mapping[tuple[object, object], Mapping[str, object]],
    candidate_by_id: Mapping[str, Mapping[str, object]],
    evidence_by_id: Mapping[str, Mapping[str, object]],
    project_context_supplied: bool,
    input_context_supplied: bool,
) -> None:
    if action.get("status") != "confirmed":
        errors.append(f"{path}.status must be confirmed")
    for field in (
        "project_action_ref",
        "project_name",
        "project_repo",
        "permission_id",
        "signal_id",
        "canonical_thread_ref",
        "why_this_project",
        "affected_component",
        "suggested_change",
        "effort",
        "risk",
    ):
        if not isinstance(action.get(field), str) or not str(action.get(field)):
            errors.append(f"{path}.{field} is invalid")
    if not _IDENTIFIER_RE.fullmatch(str(action.get("project_name") or "")):
        errors.append(f"{path}.project_name is unsafe")
    if not _REPOSITORY_RE.fullmatch(str(action.get("project_repo") or "")):
        errors.append(f"{path}.project_repo is unsafe")
    if not _IDENTIFIER_RE.fullmatch(str(action.get("permission_id") or "")):
        errors.append(f"{path}.permission_id is unsafe")
    if not _SIGNAL_ID_RE.fullmatch(str(action.get("signal_id") or "")):
        errors.append(f"{path}.signal_id is unsafe")
    if not _CANONICAL_REF_RE.fullmatch(str(action.get("canonical_thread_ref") or "")):
        errors.append(f"{path}.canonical_thread_ref is unsafe")
    _collect_safe_text(
        action.get("affected_component"), f"{path}.affected_component", errors, 300
    )
    for field in ("why_this_project", "suggested_change", "risk"):
        _collect_russian_text(action.get(field), f"{path}.{field}", errors, 1_200)
    files = _collect_string_list(
        action.get("likely_files"), f"{path}.likely_files", errors, 1, 8
    )
    for file_path in files:
        try:
            _validate_repo_relative_path(file_path, path)
        except ProjectDescriptorError as exc:
            errors.append(str(exc))
    criteria = _collect_string_list(
        action.get("acceptance_criteria"), f"{path}.acceptance_criteria", errors, 1, 6
    )
    for index, criterion in enumerate(criteria):
        _collect_russian_text(
            criterion, f"{path}.acceptance_criteria[{index}]", errors, 500
        )
    priority = action.get("priority")
    if (
        not isinstance(priority, int)
        or isinstance(priority, bool)
        or not 1 <= priority <= 10_000
    ):
        errors.append(f"{path}.priority must be a bounded positive integer")
    if not isinstance(action.get("confidence"), str) or action.get(
        "confidence"
    ) not in {"medium", "high"}:
        errors.append(f"{path}.confidence exceeds project action gate")
    refs = _collect_string_list(
        action.get("evidence_refs"), f"{path}.evidence_refs", errors, 1, 12
    )
    if any(not _EVIDENCE_REF_RE.fullmatch(ref) for ref in refs):
        errors.append(f"{path}.evidence_refs contains an unsafe ref")
    expected_action_ref = _stable_ref(
        "project_action",
        str(action.get("project_name") or ""),
        str(action.get("permission_id") or ""),
        str(action.get("signal_id") or ""),
        str(action.get("canonical_thread_ref") or ""),
    )
    if action.get("project_action_ref") != expected_action_ref:
        errors.append(f"{path}.project_action_ref is not deterministic")

    descriptor = descriptor_by_key.get(
        (
            _mapping_key_text(action.get("project_name")),
            _mapping_key_text(action.get("permission_id")),
        )
    )
    if project_context_supplied and descriptor is None:
        errors.append(f"{path} has no configured descriptor")
    elif descriptor is not None:
        for field in (
            "project_name",
            "project_repo",
            "permission_id",
            "why_this_project",
            "affected_component",
            "suggested_change",
            "likely_files",
            "effort",
            "acceptance_criteria",
            "risk",
            "priority",
        ):
            if action.get(field) != descriptor.get(field):
                errors.append(f"{path}.{field} does not match configured descriptor")
        if (
            action.get("canonical_thread_ref")
            not in descriptor["canonical_thread_refs"]
        ):
            errors.append(f"{path}.canonical_thread_ref is not permitted")
    candidate = candidate_by_id.get(str(action.get("signal_id") or ""))
    if input_context_supplied and candidate is None:
        errors.append(f"{path}.signal_id is not in input package")
    elif candidate is not None:
        if action.get("canonical_thread_ref") not in candidate["canonical_thread_refs"]:
            errors.append(f"{path}.canonical_thread_ref is not owned by signal")
        allowed = set(_eligible_evidence_refs(candidate, evidence_by_id))
        if not refs or not set(refs).issubset(allowed):
            errors.append(f"{path}.evidence_refs fail evidence closure")
        if action.get("confidence") != candidate.get("confidence_ceiling"):
            errors.append(f"{path}.confidence does not match signal ceiling")


def _validate_period_value(
    value: object,
    errors: list[str],
    *,
    prefix: str = "",
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        errors.append(f"{prefix}reporting_period must be an object")
        return {field: "" for field in _PERIOD_FIELDS}
    period = dict(value)
    _collect_exact_keys(period, _PERIOD_FIELDS, f"{prefix}reporting_period", errors)
    result: dict[str, str] = {}
    for field in _PERIOD_FIELDS:
        raw = period.get(field)
        if not isinstance(raw, str) or not raw or raw != raw.strip():
            errors.append(f"{prefix}reporting_period.{field} is invalid")
            result[field] = ""
        else:
            result[field] = raw
    match = _ISO_WEEK_RE.fullmatch(result["reporting_week"])
    expected_start: date | None = None
    if match is None:
        errors.append(f"{prefix}reporting_period.reporting_week is invalid")
    else:
        try:
            expected_start = date.fromisocalendar(
                int(match.group(1)), int(match.group(2)), 1
            )
        except ValueError:
            errors.append(f"{prefix}reporting_period.reporting_week is impossible")
    try:
        start = _parse_utc(result["analysis_period_start"])
        end = _parse_utc(result["analysis_period_end"])
        if end - start != timedelta(days=7):
            errors.append(f"{prefix}reporting_period must span exactly seven days")
        if expected_start is not None and (
            start.date() != expected_start or start.time().isoformat() != "00:00:00"
        ):
            errors.append(f"{prefix}reporting_period does not match reporting_week")
    except (TypeError, ValueError):
        errors.append(f"{prefix}reporting_period timestamps are invalid")
    return result


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must use Z")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if (
        parsed.tzinfo != timezone.utc
        or parsed.isoformat().replace("+00:00", "Z") != value
    ):
        raise ValueError("timestamp is not canonical UTC")
    return parsed


def _projection_input_hash(
    package: Mapping[str, object],
    descriptors: Sequence[Mapping[str, object]],
    diagnostics: Sequence[Mapping[str, object]],
) -> str:
    envelope = {
        "schema_version": PROJECT_INTELLIGENCE_SCHEMA_VERSION,
        "descriptor_schema_version": PROJECT_ACTION_PERMISSIONS_SCHEMA_VERSION,
        "input_package": package,
        "projects": list(descriptors),
        "diagnostic_records": list(diagnostics),
    }
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(envelope)).hexdigest()


def _editorial_permission(action: Mapping[str, object]) -> dict[str, object]:
    return {
        "project_action_ref": action["project_action_ref"],
        "signal_id": action["signal_id"],
        "project": action["project_name"],
        "permission": "allowed",
        "evidence_refs": list(action["evidence_refs"]),
    }


def _reader_summary(action_count: int) -> str:
    if action_count:
        return (
            f"Подтверждено проектных действий: {action_count}; каждое ограничено "
            "настроенным разрешением и доказательствами сигнала."
        )
    return (
        "Подтверждённых проектных действий не найдено; неподтверждённые "
        "совпадения, если они были, доступны только в аудите."
    )


def _no_implication_audit() -> dict[str, object]:
    return {
        "audit_id": "audit:no-confirmed-implication",
        "project_name": "",
        "permission_id": "",
        "signal_id": "",
        "canonical_thread_ref": "",
        "status": "no_confirmed_implication",
        "reason_ru": "Подтверждённых проектных действий не найдено в ограниченном входе этого запуска.",
        "evidence_refs": [],
        "selected": False,
    }


def _summary(
    projection: Mapping[str, object],
    path: Path,
    *,
    cache_hit: bool,
) -> ProjectIntelligenceSummary:
    period = projection["reporting_period"]
    return ProjectIntelligenceSummary(
        artifact_path=str(path),
        run_id=str(projection["run_id"]),
        reporting_week=str(period["reporting_week"]),
        reader_state=str(projection["reader_state"]),
        confirmed_action_count=len(projection["confirmed_actions"]),
        audit_record_count=len(projection["audit_records"]),
        input_hash=str(projection["input_hash"]),
        cache_hit=cache_hit,
    )


def _atomic_create_once(path: Path, data: bytes) -> None:
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ProjectIntelligenceArtifactError(
                    "immutable project artifact appeared with different bytes"
                )
    finally:
        temporary.unlink(missing_ok=True)


def _strict_json_loads(text: str) -> object:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise ProjectIntelligenceValidationError(
                    (f"duplicate JSON key: {key}",)
                )
            result[key] = value
        return result

    def constant(value: str) -> object:
        raise ProjectIntelligenceValidationError((f"non-finite JSON value: {value}",))

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _json_copy(value: object, field: str) -> dict[str, object]:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ProjectIntelligenceValidationError(
            (f"{field} must be finite JSON: {exc}",)
        ) from exc
    if not isinstance(decoded, dict):
        raise ProjectIntelligenceValidationError((f"{field} must be an object",))
    return decoded


def _canonical_value(value: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_exact_keys(
    value: Mapping[object, object],
    expected: set[str],
    path: str,
    error_type: type[ProjectIntelligenceError],
) -> None:
    actual = set(value)
    unknown = sorted(str(key) for key in actual - expected)
    missing = sorted(expected - actual)
    if unknown or missing:
        details = []
        if missing:
            details.append(f"missing {missing}")
        if unknown:
            details.append(f"unknown {unknown}")
        if error_type is ProjectIntelligenceValidationError:
            raise error_type((f"{path}: {', '.join(details)}",))
        raise error_type(f"{path}: {', '.join(details)}")


def _collect_exact_keys(
    value: Mapping[object, object], expected: set[str], path: str, errors: list[str]
) -> None:
    actual = set(value)
    if actual != expected:
        errors.append(
            f"{path} fields mismatch: missing={sorted(expected - actual)} "
            f"unknown={sorted(str(item) for item in actual - expected)}"
        )


def _strict_text(
    value: object,
    field: str,
    maximum: int,
    error_type: type[ProjectIntelligenceError],
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or _has_unsafe_text(value)
    ):
        message = f"{field} must be an exact non-empty string up to {maximum} chars"
        if error_type is ProjectIntelligenceValidationError:
            raise error_type((message,))
        raise error_type(message)
    return value


def _strict_identifier(
    value: object,
    field: str,
    error_type: type[ProjectIntelligenceError],
) -> str:
    text = _strict_text(value, field, 200, error_type)
    if not _IDENTIFIER_RE.fullmatch(text):
        message = f"{field} is not a safe identifier"
        if error_type is ProjectIntelligenceValidationError:
            raise error_type((message,))
        raise error_type(message)
    return text


def _russian_text(
    value: object,
    field: str,
    maximum: int,
    error_type: type[ProjectIntelligenceError],
) -> str:
    text = _strict_text(value, field, maximum, error_type)
    _require_russian(text, field, error_type)
    return text


def _require_russian(
    value: str,
    field: str,
    error_type: type[ProjectIntelligenceError],
) -> None:
    cyrillic_count = len(_CYRILLIC_RE.findall(value))
    letter_count = len(_LETTER_RE.findall(value))
    if cyrillic_count < 3 or (letter_count and cyrillic_count / letter_count < 0.2):
        message = f"{field} must contain Russian reader copy"
        if error_type is ProjectIntelligenceValidationError:
            raise error_type((message,))
        raise error_type(message)


def _strict_string_list(
    value: object,
    field: str,
    *,
    minimum: int,
    maximum: int,
    error_type: type[ProjectIntelligenceError],
) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        message = f"{field} must be a list with {minimum}..{maximum} items"
        if error_type is ProjectIntelligenceValidationError:
            raise error_type((message,))
        raise error_type(message)
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_strict_text(item, f"{field}[{index}]", 2_000, error_type))
    if len(result) != len(set(result)):
        message = f"{field} must not contain duplicates"
        if error_type is ProjectIntelligenceValidationError:
            raise error_type((message,))
        raise error_type(message)
    return result


def _collect_string_list(
    value: object,
    field: str,
    errors: list[str],
    minimum: int,
    maximum: int,
) -> list[str]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        errors.append(f"{field} must be a list with {minimum}..{maximum} items")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item or item != item.strip():
            errors.append(f"{field}[{index}] is invalid")
        else:
            result.append(item)
    if len(result) != len(set(result)):
        errors.append(f"{field} contains duplicates")
    return result


def _collect_russian_text(
    value: object, field: str, errors: list[str], maximum: int
) -> None:
    cyrillic_count = len(_CYRILLIC_RE.findall(value)) if isinstance(value, str) else 0
    letter_count = len(_LETTER_RE.findall(value)) if isinstance(value, str) else 0
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or _has_unsafe_text(value)
        or cyrillic_count < 3
        or (letter_count and cyrillic_count / letter_count < 0.2)
    ):
        errors.append(f"{field} must be bounded Russian reader copy")


def _collect_safe_text(
    value: object, field: str, errors: list[str], maximum: int
) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or _has_unsafe_text(value)
    ):
        errors.append(f"{field} must be bounded safe text")


def _validate_repo_relative_path(value: str, field: str) -> None:
    if (
        not _SAFE_PATH_RE.fullmatch(value)
        or "\\" in value
        or "://" in value
        or value.startswith(("/", "~"))
        or value.endswith("/")
    ):
        raise ProjectDescriptorError(f"{field}.likely_files contains an unsafe path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ProjectDescriptorError(f"{field}.likely_files contains an unsafe path")
    if str(path) != value:
        raise ProjectDescriptorError(f"{field}.likely_files path is not normalized")


def _has_unsafe_text(value: str) -> bool:
    return bool(_MARKUP_RE.search(value)) or any(
        ord(character) < 32
        or 127 <= ord(character) <= 159
        or character in _BIDI_CONTROLS
        for character in value
    )


def _descriptor_sort_key(item: Mapping[str, object]) -> tuple[int, str, str, str]:
    return (
        int(item["priority"]),
        str(item["project_name"]),
        str(item["permission_id"]),
        str(item["project_repo"]),
    )


def _audit_sort_key(
    item: Mapping[str, object],
    descriptor_by_key: Mapping[tuple[object, object], Mapping[str, object]],
) -> tuple[int, int, str, str, str, str]:
    descriptor = descriptor_by_key.get((item["project_name"], item["permission_id"]))
    priority = int(descriptor["priority"]) if descriptor is not None else 1_000_000
    status_rank = {
        "confirmed": 0,
        "watch": 1,
        "rejected_overlap": 2,
        "learning_only": 3,
        "existing_project_context": 4,
        "no_confirmed_implication": 5,
    }
    return (
        status_rank.get(str(item["status"]), 9),
        priority,
        str(item["project_name"]),
        str(item["permission_id"]),
        str(item["signal_id"]),
        str(item["canonical_thread_ref"]),
    )


def _stable_ref(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}:{digest}"


def _mapping_key_text(value: object) -> str:
    """Return only a genuine string for safe dictionary authority lookup."""

    return value if isinstance(value, str) else ""


def _audit_identity(item: Mapping[str, object]) -> tuple[str, str, str, str]:
    return (
        str(item.get("project_name") or ""),
        str(item.get("permission_id") or ""),
        str(item.get("signal_id") or ""),
        str(item.get("canonical_thread_ref") or ""),
    )


def _action_identity(item: Mapping[str, object]) -> tuple[str, str, str, str]:
    return _audit_identity(item)


__all__ = [
    "PROJECT_ACTION_PERMISSIONS_SCHEMA_VERSION",
    "PROJECT_INTELLIGENCE_ARTIFACT_FILENAME",
    "PROJECT_INTELLIGENCE_SCHEMA_VERSION",
    "PROJECTS_YAML_PATH",
    "ProjectDescriptorError",
    "ProjectIntelligenceArtifactError",
    "ProjectIntelligenceError",
    "ProjectIntelligenceSummary",
    "ProjectIntelligenceValidationError",
    "build_project_intelligence_projection",
    "generate_project_intelligence_artifact",
    "load_project_action_descriptors",
    "load_project_intelligence_artifact",
    "project_editorial_permissions",
    "validate_project_intelligence_projection",
]
