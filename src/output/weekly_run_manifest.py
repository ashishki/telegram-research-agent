"""Typed, atomic run identity and stage state for IRX-2 weekly packages.

The manifest is deliberately independent from the report renderers.  It gives
the IRX-2 orchestrator one immutable run identity, a frozen stage policy, and a
small state machine whose JSON representation can be inspected without Python.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePath
from typing import Any, Iterable, Mapping, Sequence

from output.reporting_period import PARTIAL_ISO_WEEK, ReportingPeriod, ReportingPeriodError


MANIFEST_SCHEMA_VERSION = "weekly_run_manifest.v1"
PIPELINE_PROFILE = "irx2_orchestration.v1"
RADAR_BINDING_SCHEMA_VERSION = "radar_run_binding.v1"
REACTION_SNAPSHOT_SCHEMA_VERSION = "reaction_visibility_snapshot.v1"
REACTION_SNAPSHOT_PATH = "reaction_sync/reaction-snapshot.json"
REACTION_EFFECT_SCHEMA_VERSION = "reaction_personalization.v1"

PENDING = "pending"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
DISABLED = "disabled"
SKIPPED_DEPENDENCY = "skipped_dependency"
CANCELLED = "cancelled"

STAGE_STATUSES = frozenset(
    {PENDING, RUNNING, SUCCEEDED, FAILED, DISABLED, SKIPPED_DEPENDENCY, CANCELLED}
)
RUN_STATUSES = frozenset({RUNNING, "complete", "partial", FAILED, CANCELLED})
TERMINAL_RUN_STATUSES = frozenset({"complete", "partial", FAILED, CANCELLED})
FAILURE_STAGE_STATUSES = frozenset({FAILED, SKIPPED_DEPENDENCY, CANCELLED})

IRX2_STAGE_ORDER = (
    "knowledge_refresh",
    "reaction_sync",
    "feedback_snapshot",
    "canonical_thread_curation",
    "frontier_analysis",
    "radar",
    "editorial_intelligence",
    "weekly_brief",
    "knowledge_atlas",
    "knowledge_audit_explorer",
    "reader_value_gates",
)

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ISO_WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization|cookie)"
    r"\s*[:=]\s*([^\s,;]+)"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+=*")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")
_MAX_ERROR_MESSAGE = 500
_MAX_WARNING = 500
_MAX_WARNINGS = 50


class WeeklyRunManifestError(ValueError):
    """Raised when a manifest or state transition violates the V1 contract."""


class ManifestExistsError(WeeklyRunManifestError):
    """Raised when exclusive run creation would replace an existing run."""


class TerminalManifestError(WeeklyRunManifestError):
    """Raised when a caller attempts to mutate a finalized manifest."""


class RadarBindingError(WeeklyRunManifestError):
    """Raised when a Radar identity envelope is invalid or mismatched."""


@dataclass(frozen=True, slots=True)
class StagePolicy:
    """Frozen policy bits copied into both ``stage_policy`` and stage state."""

    enabled: bool
    required: bool
    fatal: bool
    degrades_on_failure: bool

    def to_dict(self) -> dict[str, bool]:
        return {
            "enabled": self.enabled,
            "required": self.required,
            "fatal": self.fatal,
            "degrades_on_failure": self.degrades_on_failure,
        }


# A Brief failure is fatal because there is no deliverable package.  Knowledge
# refresh is also foundational.  Other enabled failures are visible partials.
_BASE_STAGE_POLICY: dict[str, StagePolicy] = {
    "knowledge_refresh": StagePolicy(True, True, True, False),
    "reaction_sync": StagePolicy(True, True, False, True),
    "feedback_snapshot": StagePolicy(True, True, False, True),
    "canonical_thread_curation": StagePolicy(False, False, False, False),
    "frontier_analysis": StagePolicy(True, True, False, True),
    "radar": StagePolicy(True, True, False, True),
    "editorial_intelligence": StagePolicy(False, False, False, False),
    "weekly_brief": StagePolicy(True, True, True, False),
    "knowledge_atlas": StagePolicy(True, True, False, True),
    "knowledge_audit_explorer": StagePolicy(False, False, False, False),
    "reader_value_gates": StagePolicy(False, False, False, False),
}

_COMMON_STAGE_DEFAULTS: dict[str, Any] = {
    "attempt": 0,
    "started_at": None,
    "finished_at": None,
    "degraded": False,
    "error": None,
    "record_counts": {},
    "dependency_refs": {},
    "artifact_refs": {},
    "checksums": {},
}

_STAGE_SPECIFIC_DEFAULTS: dict[str, dict[str, Any]] = {
    "knowledge_refresh": {"artifact_path": None},
    "reaction_sync": {"snapshot_ref": None, "observed_through": None},
    "feedback_snapshot": {
        "snapshot_id": None,
        "cutoff": None,
        "confirmed_event_count": 0,
        "pending_event_count": 0,
    },
    "canonical_thread_curation": {"artifact_path": None},
    "frontier_analysis": {"analysis_id": None, "artifact_path": None},
    "radar": {
        "radar_run_id": None,
        "artifact_path": None,
        "artifact_sha256": None,
        "binding_path": None,
        "binding_sha256": None,
        "seed_export_path": None,
        "seed_export_sha256": None,
        "reporting_week": None,
        "market_lens_path": None,
    },
    "editorial_intelligence": {"artifact_path": None},
    "weekly_brief": {"html_path": None, "json_path": None},
    "knowledge_atlas": {"html_path": None, "json_path": None},
    "knowledge_audit_explorer": {"html_path": None, "json_path": None},
    "reader_value_gates": {"artifact_path": None},
}

_IMMUTABLE_MANIFEST_FIELDS = (
    "schema_version",
    "pipeline_profile",
    "run_id",
    "supersedes_run_id",
    "run_date",
    "generated_at",
    "reporting_week",
    "week_label",
    "period_mode",
    "analysis_period_start",
    "analysis_period_end",
    "required_stages",
    "stage_policy",
    "created_by",
)


def irx2_stage_policy(*, radar_enabled: bool = True) -> dict[str, dict[str, bool]]:
    """Return a fresh, deterministic policy mapping for the IRX-2 profile."""

    policy = dict(_BASE_STAGE_POLICY)
    if not radar_enabled:
        policy["radar"] = StagePolicy(False, False, False, False)
    return {name: policy[name].to_dict() for name in IRX2_STAGE_ORDER}


def generate_run_id(period: ReportingPeriod, *, entropy: str | None = None) -> str:
    """Generate a filesystem-safe run ID; persistence still enforces exclusivity."""

    if not isinstance(period, ReportingPeriod):
        raise WeeklyRunManifestError("period must be a ReportingPeriod")
    token = entropy if entropy is not None else uuid.uuid4().hex[:12]
    token = str(token).strip().lower()
    if not re.fullmatch(r"[a-z0-9]{6,32}", token):
        raise WeeklyRunManifestError("run ID entropy must contain 6-32 lowercase letters/digits")
    stamp = period.generated_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"tra-weekly-{period.reporting_week}-{stamp}-{token}"
    _validate_run_id(run_id)
    return run_id


def build_initial_manifest(
    period: ReportingPeriod,
    *,
    run_id: str | None = None,
    entropy: str | None = None,
    radar_enabled: bool = True,
    supersedes_run_id: str | None = None,
    created_by: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build and validate the immutable initial ``running`` manifest."""

    if not isinstance(period, ReportingPeriod):
        raise WeeklyRunManifestError("period must be a ReportingPeriod")
    resolved_run_id = str(run_id or generate_run_id(period, entropy=entropy))
    _validate_run_id(resolved_run_id)
    if supersedes_run_id is not None:
        _validate_run_id(str(supersedes_run_id))
        if str(supersedes_run_id) == resolved_run_id:
            raise WeeklyRunManifestError("supersedes_run_id must differ from run_id")

    policy = irx2_stage_policy(radar_enabled=radar_enabled)
    stages = {
        name: _new_stage_record(name, policy[name])
        for name in IRX2_STAGE_ORDER
    }
    required_stages = [name for name in IRX2_STAGE_ORDER if policy[name]["required"]]
    period_fields = period.to_dict()
    warnings: list[str] = []
    if not radar_enabled:
        warnings.append(
            "MVP Radar disabled by the run request; no build decision was produced "
            "and the IRX-14 dogfood gate is blocked."
        )
    if period.period_mode == PARTIAL_ISO_WEEK:
        warnings.append("Diagnostic partial ISO week; reader output must display a partial banner.")

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "pipeline_profile": PIPELINE_PROFILE,
        "run_id": resolved_run_id,
        "supersedes_run_id": str(supersedes_run_id) if supersedes_run_id else None,
        **period_fields,
        "run_status": RUNNING,
        "partial": period.period_mode == PARTIAL_ISO_WEEK,
        "cancellation_requested": False,
        "finalized_at": None,
        "knowledge_refresh_status": PENDING,
        "reaction_sync_status": PENDING,
        "frontier_analysis_id": None,
        "frontier_analysis_path": None,
        "market_lens_path": None,
        "radar_status": DISABLED if not radar_enabled else PENDING,
        "radar_json_path": None,
        "weekly_brief_html_path": None,
        "weekly_brief_json_path": None,
        "atlas_html_path": None,
        "atlas_json_path": None,
        "audit_explorer_path": None,
        "feedback_snapshot": None,
        "report_generation_status": PENDING,
        "required_stages": required_stages,
        "stage_policy": policy,
        "stages": stages,
        "frontier_analysis_ref": {"id": None, "path": None},
        "radar_json_ref": {
            "path": None,
            "sha256": None,
            "binding_path": None,
            "binding_sha256": None,
            "run_id": None,
            "reporting_week": period.reporting_week,
        },
        "feedback_snapshot_ref": {
            "snapshot_id": None,
            "cutoff": period_fields["analysis_period_end"],
            "confirmed_event_count": 0,
            "pending_event_count": 0,
        },
        "artifacts": {
            "weekly_brief_html_path": None,
            "weekly_brief_json_path": None,
            "atlas_html_path": None,
            "atlas_json_path": None,
            "audit_explorer_html_path": None,
            "audit_explorer_json_path": None,
            "editorial_json_path": None,
        },
        "warnings": warnings,
        "failed_stages": [],
        "created_by": _sanitize_created_by(created_by),
    }
    _project_summary(manifest)
    validate_manifest(manifest)
    return manifest


def create_manifest(
    output_root: str | os.PathLike[str],
    period: ReportingPeriod,
    **manifest_options: Any,
) -> tuple[Path, dict[str, Any]]:
    """Exclusively create ``<output_root>/<run_id>/manifest.json``.

    The run directory itself is the uniqueness lock.  Regeneration therefore
    cannot replace an earlier identity even if a caller supplies the same ID.
    """

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    manifest = build_initial_manifest(period, **manifest_options)
    run_dir = root / manifest["run_id"]
    try:
        run_dir.mkdir(mode=0o750)
    except FileExistsError as exc:
        raise ManifestExistsError(f"run already exists: {manifest['run_id']}") from exc
    path = run_dir / "manifest.json"
    try:
        _atomic_create_json(path, manifest)
    except Exception:
        try:
            run_dir.rmdir()
        except OSError:
            pass
        raise
    return path, manifest


def load_manifest(
    path: str | os.PathLike[str],
    *,
    path_base: str | os.PathLike[str] | None = None,
    allowed_roots: Sequence[str | os.PathLike[str]] = (),
    check_artifact_existence: bool = False,
) -> dict[str, Any]:
    """Load JSON and apply the complete deterministic manifest validator."""

    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WeeklyRunManifestError(f"cannot load manifest: {target}") from exc
    validate_manifest(
        payload,
        path_base=path_base,
        allowed_roots=allowed_roots,
        check_artifact_existence=check_artifact_existence,
    )
    return payload


def write_manifest(
    path: str | os.PathLike[str],
    manifest: Mapping[str, Any],
    *,
    path_base: str | os.PathLike[str] | None = None,
    allowed_roots: Sequence[str | os.PathLike[str]] = (),
    check_artifact_existence: bool = True,
) -> None:
    """Validate an update and atomically replace a non-terminal manifest."""

    target = Path(path)
    previous = load_manifest(target, path_base=path_base, allowed_roots=allowed_roots)
    candidate = copy.deepcopy(dict(manifest))
    validate_manifest(
        candidate,
        path_base=path_base,
        allowed_roots=allowed_roots,
        check_artifact_existence=check_artifact_existence,
    )
    validate_manifest_update(previous, candidate)
    _atomic_replace_json(target, candidate)


def transition_stage(
    manifest: Mapping[str, Any],
    stage_name: str,
    new_status: str,
    *,
    at: datetime | str | None = None,
    updates: Mapping[str, Any] | None = None,
    error: BaseException | Mapping[str, Any] | str | None = None,
    degraded: bool = False,
) -> dict[str, Any]:
    """Return a validated copy with one legal stage transition applied."""

    current = copy.deepcopy(dict(manifest))
    validate_manifest(current)
    if current["run_status"] != RUNNING:
        raise TerminalManifestError("terminal manifests are immutable")
    if stage_name not in IRX2_STAGE_ORDER:
        raise WeeklyRunManifestError(f"unknown stage: {stage_name}")
    if new_status not in STAGE_STATUSES:
        raise WeeklyRunManifestError(f"unsupported stage status: {new_status}")

    old_record = current["stages"][stage_name]
    old_status = old_record["status"]
    policy = current["stage_policy"][stage_name]
    _validate_requested_transition(old_status, new_status, policy)
    timestamp = _canonical_timestamp(at or datetime.now(timezone.utc), field="transition time")

    if new_status == RUNNING:
        record = _new_stage_record(stage_name, policy)
        record["status"] = RUNNING
        record["attempt"] = int(old_record["attempt"]) + 1
        record["started_at"] = timestamp
    else:
        record = copy.deepcopy(old_record)
        if new_status in {SKIPPED_DEPENDENCY, CANCELLED} and old_status == PENDING:
            record["started_at"] = timestamp
            record["attempt"] = max(1, int(record["attempt"]))
        record["status"] = new_status
        record["finished_at"] = timestamp
        record["degraded"] = bool(degraded)

    _apply_stage_updates(stage_name, record, updates or {})
    if new_status == FAILED:
        record["error"] = sanitize_error(error or "stage failed")
    elif new_status in {SKIPPED_DEPENDENCY, CANCELLED}:
        record["error"] = sanitize_error(error) if error is not None else None
    elif new_status == SUCCEEDED:
        record["error"] = None
    elif error is not None:
        raise WeeklyRunManifestError("errors may be recorded only for failed/skipped/cancelled stages")
    if degraded and new_status != SUCCEEDED:
        raise WeeklyRunManifestError("degraded=true requires a validated succeeded fallback")

    current["stages"][stage_name] = record
    _project_summary(current)
    _recompute_running_state(current)
    validate_manifest(current)
    return current


def start_stage(
    manifest: Mapping[str, Any],
    stage_name: str,
    *,
    at: datetime | str | None = None,
    updates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return transition_stage(manifest, stage_name, RUNNING, at=at, updates=updates)


def succeed_stage(
    manifest: Mapping[str, Any],
    stage_name: str,
    *,
    at: datetime | str | None = None,
    updates: Mapping[str, Any] | None = None,
    degraded: bool = False,
) -> dict[str, Any]:
    return transition_stage(
        manifest,
        stage_name,
        SUCCEEDED,
        at=at,
        updates=updates,
        degraded=degraded,
    )


def fail_stage(
    manifest: Mapping[str, Any],
    stage_name: str,
    error: BaseException | Mapping[str, Any] | str,
    *,
    at: datetime | str | None = None,
    updates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return transition_stage(
        manifest,
        stage_name,
        FAILED,
        at=at,
        updates=updates,
        error=error,
    )


def finalize_manifest(
    manifest: Mapping[str, Any],
    *,
    at: datetime | str | None = None,
    cancelled: bool = False,
) -> dict[str, Any]:
    """Derive and freeze the one terminal run state."""

    result = copy.deepcopy(dict(manifest))
    validate_manifest(result)
    if result["run_status"] != RUNNING:
        raise TerminalManifestError("terminal manifests are immutable")
    active = [
        name
        for name in IRX2_STAGE_ORDER
        if result["stage_policy"][name]["enabled"]
        and result["stages"][name]["status"] in {PENDING, RUNNING}
    ]
    if active and not cancelled:
        raise WeeklyRunManifestError(
            "cannot finalize while enabled stages are pending/running: " + ", ".join(active)
        )

    final_timestamp = _canonical_timestamp(
        at or datetime.now(timezone.utc), field="finalized_at"
    )
    if cancelled:
        for name in active:
            result = transition_stage(
                result,
                name,
                CANCELLED,
                at=final_timestamp,
                error="run cancelled",
            )

    result["finalized_at"] = final_timestamp
    result["cancellation_requested"] = bool(cancelled)
    _project_summary(result)
    result["failed_stages"] = _failed_stages(result)
    result["partial"] = _derived_partial(result)
    if cancelled:
        result["run_status"] = CANCELLED
    elif _has_fatal_failure(result):
        result["run_status"] = FAILED
    elif result["partial"] or not _all_required_succeeded(result):
        result["run_status"] = "partial"
        result["partial"] = True
    else:
        result["run_status"] = "complete"
        result["partial"] = False
    validate_manifest(result)
    return result


def append_warning(manifest: Mapping[str, Any], warning: str) -> dict[str, Any]:
    """Add one bounded operator-visible warning to a running manifest."""

    result = copy.deepcopy(dict(manifest))
    validate_manifest(result)
    if result["run_status"] != RUNNING:
        raise TerminalManifestError("terminal manifests are immutable")
    clean = _bounded_text(warning, _MAX_WARNING)
    if not clean:
        raise WeeklyRunManifestError("warning must not be empty")
    if clean not in result["warnings"]:
        if len(result["warnings"]) >= _MAX_WARNINGS:
            raise WeeklyRunManifestError("manifest warning limit exceeded")
        result["warnings"].append(clean)
    validate_manifest(result)
    return result


def sanitize_error(
    error: BaseException | Mapping[str, Any] | str,
    *,
    max_message: int = _MAX_ERROR_MESSAGE,
) -> dict[str, Any]:
    """Return a bounded, traceback-free error record with common secrets redacted."""

    if not isinstance(max_message, int) or isinstance(max_message, bool) or max_message < 32:
        raise WeeklyRunManifestError("max_message must be an integer >= 32")
    if isinstance(error, Mapping):
        type_name = _bounded_text(error.get("type") or "StageError", 100)
        message = _bounded_text(error.get("message") or "stage failed", max_message)
        code = _bounded_text(error.get("code"), 80) or None
        retryable = bool(error.get("retryable", False))
    elif isinstance(error, BaseException):
        type_name = _bounded_text(type(error).__name__, 100)
        message = _bounded_text(str(error) or type_name, max_message)
        code = None
        retryable = False
    else:
        type_name = "StageError"
        message = _bounded_text(str(error), max_message)
        code = None
        retryable = False
    message = _redact_secrets(message)
    return {
        "type": type_name or "StageError",
        "code": code,
        "message": message or "stage failed",
        "retryable": retryable,
    }


def validate_manifest(
    manifest: Mapping[str, Any],
    *,
    path_base: str | os.PathLike[str] | None = None,
    allowed_roots: Sequence[str | os.PathLike[str]] = (),
    check_artifact_existence: bool = False,
) -> None:
    """Validate schema, period, policy, projections, paths, and aggregation."""

    if not isinstance(manifest, Mapping):
        raise WeeklyRunManifestError("manifest must be an object")
    _require_equal(manifest, "schema_version", MANIFEST_SCHEMA_VERSION)
    _require_equal(manifest, "pipeline_profile", PIPELINE_PROFILE)
    run_id = _require_string(manifest, "run_id")
    _validate_run_id(run_id)
    supersedes = manifest.get("supersedes_run_id")
    if supersedes is not None:
        _validate_run_id(_require_string(manifest, "supersedes_run_id"))
        if supersedes == run_id:
            raise WeeklyRunManifestError("supersedes_run_id must differ from run_id")

    period = _period_from_manifest(manifest)
    if manifest.get("week_label") != manifest.get("reporting_week"):
        raise WeeklyRunManifestError("week_label must equal reporting_week")
    run_status = _require_string(manifest, "run_status")
    if run_status not in RUN_STATUSES:
        raise WeeklyRunManifestError(f"invalid run_status: {run_status}")
    _require_bool(manifest, "partial")
    _require_bool(manifest, "cancellation_requested")
    finalized_at = manifest.get("finalized_at")
    if run_status == RUNNING:
        if finalized_at is not None:
            raise WeeklyRunManifestError("running manifest cannot have finalized_at")
        if manifest.get("cancellation_requested"):
            raise WeeklyRunManifestError("running manifest cannot be cancellation-requested")
    else:
        _canonical_timestamp(finalized_at, field="finalized_at")
    if run_status == CANCELLED and not manifest.get("cancellation_requested"):
        raise WeeklyRunManifestError("cancelled run requires cancellation_requested=true")
    if run_status != CANCELLED and manifest.get("cancellation_requested"):
        raise WeeklyRunManifestError("cancellation_requested requires run_status=cancelled")

    policy = manifest.get("stage_policy")
    stages = manifest.get("stages")
    if not isinstance(policy, Mapping) or not isinstance(stages, Mapping):
        raise WeeklyRunManifestError("stage_policy and stages must be objects")
    if tuple(policy.keys()) != IRX2_STAGE_ORDER or tuple(stages.keys()) != IRX2_STAGE_ORDER:
        raise WeeklyRunManifestError("stage policy/state membership and order must match IRX-2")
    _validate_profile_policy(policy)
    required = manifest.get("required_stages")
    expected_required = [name for name in IRX2_STAGE_ORDER if policy[name]["required"]]
    if required != expected_required:
        raise WeeklyRunManifestError("required_stages must exactly match required=true policy entries")
    for name in IRX2_STAGE_ORDER:
        _validate_stage_record(name, stages[name], policy[name], period)
    active_stages = [
        name
        for name in IRX2_STAGE_ORDER
        if policy[name]["enabled"] and stages[name]["status"] in {PENDING, RUNNING}
    ]
    if run_status != RUNNING and active_stages:
        raise WeeklyRunManifestError(
            "terminal manifest cannot retain enabled pending/running stages: "
            + ", ".join(active_stages)
        )

    warnings = manifest.get("warnings")
    if not isinstance(warnings, list) or len(warnings) > _MAX_WARNINGS:
        raise WeeklyRunManifestError("warnings must be a bounded list")
    for warning in warnings:
        if not isinstance(warning, str) or warning != _bounded_text(warning, _MAX_WARNING):
            raise WeeklyRunManifestError("warning is invalid or exceeds the size limit")
    failed_stages = manifest.get("failed_stages")
    if failed_stages != _failed_stages(manifest):
        raise WeeklyRunManifestError("failed_stages projection does not match stage state")
    if bool(manifest.get("partial")) != _derived_partial(manifest):
        raise WeeklyRunManifestError("partial projection does not match period/stage state")

    _validate_summary_projection(manifest)
    _validate_created_by(manifest.get("created_by"))
    _validate_paths(manifest, path_base=path_base, allowed_roots=allowed_roots)
    if check_artifact_existence:
        _validate_succeeded_stage_outputs(
            manifest, path_base=path_base, allowed_roots=allowed_roots
        )

    if run_status == "complete":
        if not _all_required_succeeded(manifest) or _derived_partial(manifest):
            raise WeeklyRunManifestError("complete run requires every required stage at full quality")
    elif run_status == "partial":
        if not manifest.get("partial") or _has_fatal_failure(manifest):
            raise WeeklyRunManifestError("partial run cannot hide a fatal failure")
    elif run_status == FAILED and not _has_fatal_failure(manifest):
        raise WeeklyRunManifestError("failed run requires a fatal stage failure")


def validate_manifest_update(previous: Mapping[str, Any], current: Mapping[str, Any]) -> None:
    """Validate immutability plus persisted stage transitions between two snapshots."""

    validate_manifest(previous)
    validate_manifest(current)
    if previous["run_status"] != RUNNING:
        raise TerminalManifestError("terminal manifests are immutable")
    for field in _IMMUTABLE_MANIFEST_FIELDS:
        if previous.get(field) != current.get(field):
            raise WeeklyRunManifestError(f"immutable manifest field changed: {field}")
    for name in IRX2_STAGE_ORDER:
        before = previous["stages"][name]
        after = current["stages"][name]
        if before == after:
            continue
        _validate_persisted_stage_update(before, after, name)
    if current["run_status"] not in RUN_STATUSES:
        raise WeeklyRunManifestError("invalid resulting run status")


def sha256_file(path: str | os.PathLike[str], *, chunk_size: int = 1024 * 1024) -> str:
    """Hash immutable artifact bytes without loading a large file into memory."""

    if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) or chunk_size <= 0:
        raise WeeklyRunManifestError("chunk_size must be a positive integer")
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise WeeklyRunManifestError(f"cannot hash artifact: {path}") from exc
    return digest.hexdigest()


def verify_file_checksum(path: str | os.PathLike[str], expected_sha256: str) -> None:
    """Raise when a file's bytes do not match an expected lowercase SHA-256."""

    if not isinstance(expected_sha256, str) or not _SHA256_RE.fullmatch(expected_sha256):
        raise WeeklyRunManifestError("expected_sha256 must be 64 lowercase hex characters")
    actual = sha256_file(path)
    if not hmac.compare_digest(actual, expected_sha256):
        raise WeeklyRunManifestError(
            f"artifact checksum mismatch: expected {expected_sha256}, got {actual}"
        )


def load_bound_reaction_snapshot(
    manifest: Mapping[str, Any],
    *,
    path_base: str | os.PathLike[str] | None = None,
    allowed_roots: Sequence[str | os.PathLike[str]] = (),
    verify_file: bool = True,
) -> dict[str, Any] | None:
    """Load a validated run-scoped reaction snapshot when one is bound.

    IRX-2 manifests predate this optional artifact.  A successful legacy
    ``reaction_sync`` stage with no ``artifact_refs.snapshot_path`` therefore
    remains valid and returns ``None``; callers must not promote that legacy
    count-only result into fresh personalization evidence.
    """

    validate_manifest(
        manifest,
        path_base=path_base,
        allowed_roots=allowed_roots,
        check_artifact_existence=False,
    )
    stage = manifest["stages"]["reaction_sync"]
    binding = _optional_reaction_snapshot_binding(stage)
    if stage["status"] != SUCCEEDED or binding is None:
        return None
    return _validate_reaction_snapshot_output(
        manifest,
        path_base=path_base,
        allowed_roots=allowed_roots,
        verify_file=verify_file,
    )


def build_radar_run_binding(
    manifest: Mapping[str, Any],
    *,
    radar_run_id: str,
    radar_contract_version: str,
    radar_schema_version: str,
    seed_export_path: str | os.PathLike[str],
    radar_json_path: str | os.PathLike[str],
    selected_candidate: Mapping[str, Any] | None,
    status_projection: Mapping[str, Any],
    created_at: datetime | str | None = None,
    path_base: str | os.PathLike[str] | None = None,
    allowed_roots: Sequence[str | os.PathLike[str]] = (),
) -> dict[str, Any]:
    """Build the additive same-run Radar envelope around immutable raw bytes."""

    validate_manifest(manifest)
    if manifest["run_status"] != RUNNING:
        raise RadarBindingError("Radar binding may be created only for a running manifest")
    radar_policy = manifest["stage_policy"]["radar"]
    if not radar_policy["enabled"]:
        raise RadarBindingError("Radar was predeclared disabled for this run")
    _validate_run_id(str(radar_run_id), field="radar_run_id")
    seed_path_text = os.fspath(seed_export_path)
    radar_path_text = os.fspath(radar_json_path)
    _validate_one_path(seed_path_text, path_base=path_base, allowed_roots=allowed_roots)
    _validate_one_path(radar_path_text, path_base=path_base, allowed_roots=allowed_roots)
    seed_resolved = _resolve_artifact_path(seed_path_text, path_base)
    radar_resolved = _resolve_artifact_path(radar_path_text, path_base)
    binding = {
        "schema_version": RADAR_BINDING_SCHEMA_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_run_id": manifest["run_id"],
        "radar_run_id": str(radar_run_id),
        "run_date": manifest["run_date"],
        "generated_at": manifest["generated_at"],
        "reporting_week": manifest["reporting_week"],
        "week_label": manifest["week_label"],
        "period_mode": manifest["period_mode"],
        "analysis_period_start": manifest["analysis_period_start"],
        "analysis_period_end": manifest["analysis_period_end"],
        "radar_contract_version": _nonempty_bounded(radar_contract_version, 120),
        "radar_schema_version": _nonempty_bounded(radar_schema_version, 120),
        "seed_export_ref": {
            "path": seed_path_text,
            "sha256": sha256_file(seed_resolved),
        },
        "radar_json_ref": {
            "path": radar_path_text,
            "sha256": sha256_file(radar_resolved),
        },
        "selected_candidate": copy.deepcopy(dict(selected_candidate))
        if selected_candidate is not None
        else None,
        "status_projection": copy.deepcopy(dict(status_projection)),
        "created_at": _canonical_timestamp(
            created_at or datetime.now(timezone.utc), field="created_at"
        ),
    }
    validate_radar_run_binding(
        binding,
        manifest=manifest,
        path_base=path_base,
        allowed_roots=allowed_roots,
        verify_files=True,
    )
    return binding


def validate_radar_run_binding(
    binding: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any] | None = None,
    path_base: str | os.PathLike[str] | None = None,
    allowed_roots: Sequence[str | os.PathLike[str]] = (),
    verify_files: bool = False,
) -> None:
    """Validate binding schema, period/run parity, containment, and checksums."""

    if not isinstance(binding, Mapping):
        raise RadarBindingError("Radar binding must be an object")
    try:
        _require_equal(binding, "schema_version", RADAR_BINDING_SCHEMA_VERSION)
        _require_equal(binding, "manifest_schema_version", MANIFEST_SCHEMA_VERSION)
        _validate_run_id(_require_string(binding, "manifest_run_id"), field="manifest_run_id")
        _validate_run_id(_require_string(binding, "radar_run_id"), field="radar_run_id")
        if not _ISO_WEEK_RE.fullmatch(_require_string(binding, "reporting_week")):
            raise WeeklyRunManifestError("invalid binding reporting_week")
        if binding.get("week_label") != binding.get("reporting_week"):
            raise WeeklyRunManifestError("binding week_label/reporting_week mismatch")
        _period_from_manifest(binding)
        _nonempty_bounded(binding.get("radar_contract_version"), 120)
        _nonempty_bounded(binding.get("radar_schema_version"), 120)
        _canonical_timestamp(binding.get("created_at"), field="created_at")
        for ref_name in ("seed_export_ref", "radar_json_ref"):
            ref = binding.get(ref_name)
            if not isinstance(ref, Mapping):
                raise WeeklyRunManifestError(f"{ref_name} must be an object")
            path = _require_string(ref, "path")
            checksum = _require_string(ref, "sha256")
            if not _SHA256_RE.fullmatch(checksum):
                raise WeeklyRunManifestError(f"{ref_name}.sha256 must be lowercase SHA-256")
            _validate_one_path(path, path_base=path_base, allowed_roots=allowed_roots)
            if verify_files:
                verify_file_checksum(_resolve_artifact_path(path, path_base), checksum)
        candidate = binding.get("selected_candidate")
        if candidate is not None and not isinstance(candidate, Mapping):
            raise WeeklyRunManifestError("selected_candidate must be an object or null")
        projection = binding.get("status_projection")
        if not isinstance(projection, Mapping) or not projection:
            raise WeeklyRunManifestError("status_projection must be a non-empty object")
        _ensure_json_value(candidate, field="selected_candidate")
        _ensure_json_value(projection, field="status_projection")

        if manifest is not None:
            validate_manifest(manifest)
            parity = {
                "manifest_run_id": "run_id",
                "run_date": "run_date",
                "generated_at": "generated_at",
                "reporting_week": "reporting_week",
                "week_label": "week_label",
                "period_mode": "period_mode",
                "analysis_period_start": "analysis_period_start",
                "analysis_period_end": "analysis_period_end",
            }
            for binding_field, manifest_field in parity.items():
                if binding.get(binding_field) != manifest.get(manifest_field):
                    raise WeeklyRunManifestError(
                        f"Radar binding mismatch for {binding_field}"
                    )
            stage_run_id = manifest["stages"]["radar"].get("radar_run_id")
            if stage_run_id is not None and binding.get("radar_run_id") != stage_run_id:
                raise WeeklyRunManifestError("Radar binding/stage radar_run_id mismatch")
    except WeeklyRunManifestError as exc:
        if isinstance(exc, RadarBindingError):
            raise
        raise RadarBindingError(str(exc)) from exc


def write_radar_run_binding(
    path: str | os.PathLike[str],
    binding: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any] | None = None,
    path_base: str | os.PathLike[str] | None = None,
    allowed_roots: Sequence[str | os.PathLike[str]] = (),
    verify_files: bool = True,
) -> None:
    """Exclusively and atomically persist one immutable Radar binding."""

    validate_radar_run_binding(
        binding,
        manifest=manifest,
        path_base=path_base,
        allowed_roots=allowed_roots,
        verify_files=verify_files,
    )
    _atomic_create_json(Path(path), dict(binding))


def _new_stage_record(name: str, policy: Mapping[str, Any]) -> dict[str, Any]:
    record = {key: bool(policy[key]) for key in StagePolicy.__dataclass_fields__}
    record["status"] = PENDING if record["enabled"] else DISABLED
    record.update(copy.deepcopy(_COMMON_STAGE_DEFAULTS))
    record.update(copy.deepcopy(_STAGE_SPECIFIC_DEFAULTS[name]))
    return record


def _apply_stage_updates(name: str, record: dict[str, Any], updates: Mapping[str, Any]) -> None:
    if not isinstance(updates, Mapping):
        raise WeeklyRunManifestError("stage updates must be an object")
    reserved = {
        "enabled",
        "required",
        "fatal",
        "degrades_on_failure",
        "status",
        "attempt",
        "started_at",
        "finished_at",
        "degraded",
        "error",
    }
    for key, value in updates.items():
        if key in reserved or key not in record:
            raise WeeklyRunManifestError(f"unsupported {name} stage update: {key}")
        _ensure_json_value(value, field=f"stages.{name}.{key}")
        record[key] = copy.deepcopy(value)


def _validate_requested_transition(
    old_status: str, new_status: str, policy: Mapping[str, Any]
) -> None:
    if old_status in {SUCCEEDED, DISABLED}:
        raise WeeklyRunManifestError(f"{old_status} stage is terminal")
    if not policy["enabled"]:
        raise WeeklyRunManifestError("predeclared disabled stage cannot be started")
    allowed = {
        PENDING: {RUNNING, SKIPPED_DEPENDENCY, CANCELLED},
        RUNNING: {SUCCEEDED, FAILED, CANCELLED},
        FAILED: {RUNNING},
        SKIPPED_DEPENDENCY: {RUNNING},
        CANCELLED: {RUNNING},
    }
    if new_status not in allowed.get(old_status, set()):
        raise WeeklyRunManifestError(f"illegal stage transition: {old_status} -> {new_status}")


def _validate_persisted_stage_update(
    before: Mapping[str, Any], after: Mapping[str, Any], name: str
) -> None:
    for field in ("enabled", "required", "fatal", "degrades_on_failure"):
        if before.get(field) != after.get(field):
            raise WeeklyRunManifestError(f"immutable stage policy changed: {name}.{field}")
    old_status = before["status"]
    new_status = after["status"]
    if old_status == new_status:
        raise WeeklyRunManifestError(f"stage record changed without a transition: {name}")
    _validate_requested_transition(old_status, new_status, before)
    starts_without_running = old_status == PENDING and new_status in {
        SKIPPED_DEPENDENCY,
        CANCELLED,
    }
    expected_attempt = int(before["attempt"]) + (
        1 if new_status == RUNNING or starts_without_running else 0
    )
    if int(after["attempt"]) != expected_attempt:
        raise WeeklyRunManifestError(f"invalid attempt counter for stage: {name}")


def _recompute_running_state(manifest: dict[str, Any]) -> None:
    manifest["run_status"] = RUNNING
    manifest["finalized_at"] = None
    manifest["cancellation_requested"] = False
    manifest["failed_stages"] = _failed_stages(manifest)
    manifest["partial"] = _derived_partial(manifest)


def _project_summary(manifest: dict[str, Any]) -> None:
    stages = manifest["stages"]
    manifest["knowledge_refresh_status"] = stages["knowledge_refresh"]["status"]
    manifest["reaction_sync_status"] = stages["reaction_sync"]["status"]
    frontier = stages["frontier_analysis"]
    manifest["frontier_analysis_id"] = frontier["analysis_id"]
    manifest["frontier_analysis_path"] = frontier["artifact_path"]
    manifest["frontier_analysis_ref"] = {
        "id": frontier["analysis_id"],
        "path": frontier["artifact_path"],
    }
    radar = stages["radar"]
    manifest["radar_status"] = radar["status"]
    manifest["radar_json_path"] = radar["artifact_path"]
    manifest["market_lens_path"] = radar["market_lens_path"]
    manifest["radar_json_ref"] = {
        "path": radar["artifact_path"],
        "sha256": radar["artifact_sha256"],
        "binding_path": radar["binding_path"],
        "binding_sha256": radar["binding_sha256"],
        "run_id": radar["radar_run_id"],
        "reporting_week": manifest["reporting_week"],
    }
    feedback = stages["feedback_snapshot"]
    manifest["feedback_snapshot"] = feedback["snapshot_id"]
    manifest["feedback_snapshot_ref"] = {
        "snapshot_id": feedback["snapshot_id"],
        "cutoff": feedback["cutoff"] or manifest["analysis_period_end"],
        "confirmed_event_count": feedback["confirmed_event_count"],
        "pending_event_count": feedback["pending_event_count"],
    }
    brief = stages["weekly_brief"]
    atlas = stages["knowledge_atlas"]
    audit = stages["knowledge_audit_explorer"]
    editorial = stages["editorial_intelligence"]
    manifest["weekly_brief_html_path"] = brief["html_path"]
    manifest["weekly_brief_json_path"] = brief["json_path"]
    manifest["atlas_html_path"] = atlas["html_path"]
    manifest["atlas_json_path"] = atlas["json_path"]
    manifest["audit_explorer_path"] = audit["html_path"]
    manifest["artifacts"] = {
        "weekly_brief_html_path": brief["html_path"],
        "weekly_brief_json_path": brief["json_path"],
        "atlas_html_path": atlas["html_path"],
        "atlas_json_path": atlas["json_path"],
        "audit_explorer_html_path": audit["html_path"],
        "audit_explorer_json_path": audit["json_path"],
        "editorial_json_path": editorial["artifact_path"],
    }
    reader_statuses = {brief["status"], atlas["status"]}
    if reader_statuses & FAILURE_STAGE_STATUSES:
        manifest["report_generation_status"] = FAILED
    elif RUNNING in reader_statuses:
        manifest["report_generation_status"] = RUNNING
    elif PENDING in reader_statuses:
        manifest["report_generation_status"] = PENDING
    elif reader_statuses == {SUCCEEDED}:
        manifest["report_generation_status"] = SUCCEEDED
    else:
        manifest["report_generation_status"] = PENDING


def _validate_summary_projection(manifest: Mapping[str, Any]) -> None:
    projected = copy.deepcopy(dict(manifest))
    _project_summary(projected)
    fields = (
        "knowledge_refresh_status",
        "reaction_sync_status",
        "frontier_analysis_id",
        "frontier_analysis_path",
        "market_lens_path",
        "radar_status",
        "radar_json_path",
        "weekly_brief_html_path",
        "weekly_brief_json_path",
        "atlas_html_path",
        "atlas_json_path",
        "audit_explorer_path",
        "feedback_snapshot",
        "report_generation_status",
        "frontier_analysis_ref",
        "radar_json_ref",
        "feedback_snapshot_ref",
        "artifacts",
    )
    for field in fields:
        if manifest.get(field) != projected.get(field):
            raise WeeklyRunManifestError(f"flat/nested projection mismatch: {field}")


def _failed_stages(manifest: Mapping[str, Any]) -> list[str]:
    return [
        name
        for name in IRX2_STAGE_ORDER
        if manifest["stage_policy"][name]["enabled"]
        and manifest["stages"][name]["status"] in FAILURE_STAGE_STATUSES
    ]


def _derived_partial(manifest: Mapping[str, Any]) -> bool:
    if manifest.get("period_mode") == PARTIAL_ISO_WEEK:
        return True
    for name in IRX2_STAGE_ORDER:
        if not manifest["stage_policy"][name]["enabled"]:
            continue
        stage = manifest["stages"][name]
        if stage["status"] in FAILURE_STAGE_STATUSES or stage.get("degraded"):
            return True
    return False


def _has_fatal_failure(manifest: Mapping[str, Any]) -> bool:
    return any(
        manifest["stage_policy"][name]["enabled"]
        and manifest["stage_policy"][name]["fatal"]
        and manifest["stages"][name]["status"] in FAILURE_STAGE_STATUSES
        for name in IRX2_STAGE_ORDER
    )


def _all_required_succeeded(manifest: Mapping[str, Any]) -> bool:
    return all(manifest["stages"][name]["status"] == SUCCEEDED for name in manifest["required_stages"])


def _validate_profile_policy(policy: Mapping[str, Any]) -> None:
    radar = policy.get("radar")
    if not isinstance(radar, Mapping):
        raise WeeklyRunManifestError("Radar policy is missing")
    radar_enabled = radar.get("enabled") is True
    expected = irx2_stage_policy(radar_enabled=radar_enabled)
    if dict(policy) != expected:
        raise WeeklyRunManifestError("stage_policy does not match irx2_orchestration.v1")


def _validate_stage_record(
    name: str,
    record: Any,
    policy: Mapping[str, Any],
    period: ReportingPeriod,
) -> None:
    if not isinstance(record, Mapping):
        raise WeeklyRunManifestError(f"stage record must be an object: {name}")
    expected_keys = set(_new_stage_record(name, policy))
    if set(record) != expected_keys:
        raise WeeklyRunManifestError(f"stage record fields do not match contract: {name}")
    for bit in StagePolicy.__dataclass_fields__:
        if record.get(bit) is not policy.get(bit):
            raise WeeklyRunManifestError(f"stage policy projection mismatch: {name}.{bit}")
    status = record.get("status")
    if status not in STAGE_STATUSES:
        raise WeeklyRunManifestError(f"invalid stage status: {name}.{status}")
    if policy["enabled"]:
        if status == DISABLED:
            raise WeeklyRunManifestError(f"enabled stage cannot be disabled: {name}")
    elif status != DISABLED:
        raise WeeklyRunManifestError(f"predeclared disabled stage must remain disabled: {name}")
    attempt = record.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 0:
        raise WeeklyRunManifestError(f"invalid stage attempt: {name}")
    if status == PENDING and attempt != 0:
        raise WeeklyRunManifestError(f"pending stage attempt must be zero: {name}")
    if status == DISABLED and attempt != 0:
        raise WeeklyRunManifestError(f"disabled stage attempt must be zero: {name}")
    if status in {RUNNING, SUCCEEDED, FAILED, SKIPPED_DEPENDENCY, CANCELLED} and attempt < 1:
        raise WeeklyRunManifestError(f"active/finished stage requires an attempt: {name}")
    started = record.get("started_at")
    finished = record.get("finished_at")
    if status in {PENDING, DISABLED}:
        if started is not None or finished is not None:
            raise WeeklyRunManifestError(f"inactive stage cannot have timestamps: {name}")
    elif status == RUNNING:
        _canonical_timestamp(started, field=f"stages.{name}.started_at")
        if finished is not None:
            raise WeeklyRunManifestError(f"running stage cannot have finished_at: {name}")
    else:
        start_dt = _parse_timestamp(started, field=f"stages.{name}.started_at")
        end_dt = _parse_timestamp(finished, field=f"stages.{name}.finished_at")
        if end_dt < start_dt:
            raise WeeklyRunManifestError(f"stage finish precedes start: {name}")
    if not isinstance(record.get("degraded"), bool):
        raise WeeklyRunManifestError(f"degraded must be boolean: {name}")
    if record.get("degraded") and status != SUCCEEDED:
        raise WeeklyRunManifestError(f"degraded marker requires succeeded status: {name}")
    error = record.get("error")
    if status == FAILED and not isinstance(error, Mapping):
        raise WeeklyRunManifestError(f"failed stage requires a sanitized error: {name}")
    if error is not None:
        _validate_error(error, name)
    if status == SUCCEEDED and error is not None:
        raise WeeklyRunManifestError(f"succeeded stage cannot retain error: {name}")
    _validate_record_counts(record.get("record_counts"), name)
    for key in ("dependency_refs", "artifact_refs", "checksums"):
        if not isinstance(record.get(key), Mapping):
            raise WeeklyRunManifestError(f"{name}.{key} must be an object")
        _ensure_json_value(record[key], field=f"stages.{name}.{key}")

    if name == "reaction_sync":
        binding = _optional_reaction_snapshot_binding(record)
        if binding is not None and status != SUCCEEDED:
            raise WeeklyRunManifestError(
                "reaction snapshot binding requires a succeeded stage"
            )
        if status == SUCCEEDED:
            _nonempty_bounded(record.get("snapshot_ref"), 300)
            _canonical_timestamp(
                record.get("observed_through"), field="reaction observed_through"
            )
    if name == "feedback_snapshot":
        cutoff = record.get("cutoff")
        if cutoff is not None and cutoff != _canonical_timestamp(
            period.analysis_period_end, field="analysis_period_end"
        ):
            raise WeeklyRunManifestError("feedback snapshot cutoff must equal analysis_period_end")
        for key in ("confirmed_event_count", "pending_event_count"):
            _nonnegative_int(record.get(key), field=f"feedback_snapshot.{key}")
        if status == SUCCEEDED:
            _nonempty_bounded(record.get("snapshot_id"), 300)
            if cutoff is None:
                raise WeeklyRunManifestError("successful feedback snapshot requires cutoff")
    if name == "frontier_analysis" and status == SUCCEEDED:
        _nonnegative_int(record.get("analysis_id"), field="frontier analysis_id", positive=True)
        _nonempty_bounded(record.get("artifact_path"), 2000)
        _required_checksum(record["checksums"], "artifact_path", stage=name)
    if name == "radar":
        reporting_week = record.get("reporting_week")
        if reporting_week is not None and reporting_week != period.reporting_week:
            raise WeeklyRunManifestError("Radar stage reporting_week mismatch")
        for key in ("artifact_sha256", "binding_sha256", "seed_export_sha256"):
            value = record.get(key)
            if value is not None and (not isinstance(value, str) or not _SHA256_RE.fullmatch(value)):
                raise WeeklyRunManifestError(f"Radar {key} must be lowercase SHA-256")
        if status == SUCCEEDED:
            for key in (
                "radar_run_id",
                "artifact_path",
                "artifact_sha256",
                "binding_path",
                "binding_sha256",
                "seed_export_path",
                "seed_export_sha256",
                "reporting_week",
            ):
                _nonempty_bounded(record.get(key), 2000)
            _validate_run_id(str(record["radar_run_id"]), field="radar_run_id")
            if set(record["dependency_refs"]) != set(record["checksums"]):
                raise WeeklyRunManifestError(
                    "Radar dependency_refs/checksums keys must match exactly"
                )
            for key in record["dependency_refs"]:
                _required_checksum(record["checksums"], key, stage=name)
            market_lens_path = record.get("market_lens_path")
            if (
                market_lens_path is not None
                and record["dependency_refs"].get("market_lens_path")
                != market_lens_path
            ):
                raise WeeklyRunManifestError(
                    "Radar market_lens_path/dependency_refs mismatch"
                )
            if record["artifact_refs"] and (
                record["artifact_refs"].get("binding_path") != record["binding_path"]
            ):
                raise WeeklyRunManifestError(
                    "Radar artifact_refs.binding_path mismatch"
                )
    if name in {"weekly_brief", "knowledge_atlas"} and status == SUCCEEDED:
        _nonempty_bounded(record.get("html_path"), 2000)
        _nonempty_bounded(record.get("json_path"), 2000)
        _required_checksum(record["checksums"], "html_path", stage=name)
        _required_checksum(record["checksums"], "json_path", stage=name)


def _validate_succeeded_stage_outputs(
    manifest: Mapping[str, Any],
    *,
    path_base: str | os.PathLike[str] | None,
    allowed_roots: Sequence[str | os.PathLike[str]],
) -> None:
    paths: list[tuple[str, str, str | None]] = []
    for name in IRX2_STAGE_ORDER:
        stage = manifest["stages"][name]
        if stage["status"] != SUCCEEDED:
            continue
        if name == "frontier_analysis":
            paths.append((name, stage["artifact_path"], stage["checksums"]["artifact_path"]))
        elif name == "radar":
            paths.extend(
                [
                    (name, stage["artifact_path"], stage["artifact_sha256"]),
                    (name, stage["binding_path"], stage["binding_sha256"]),
                    (name, stage["seed_export_path"], stage["seed_export_sha256"]),
                ]
            )
        elif name in {"weekly_brief", "knowledge_atlas"}:
            paths.extend(
                [
                    (name, stage["html_path"], stage["checksums"]["html_path"]),
                    (name, stage["json_path"], stage["checksums"]["json_path"]),
                ]
            )
        elif stage.get("artifact_path"):
            paths.append((name, stage["artifact_path"], None))
    for stage_name, path, checksum in paths:
        _validate_one_path(path, path_base=path_base, allowed_roots=allowed_roots)
        resolved = _resolve_artifact_path(path, path_base)
        if not resolved.is_file():
            raise WeeklyRunManifestError(
                f"successful stage artifact does not exist: {stage_name}: {path}"
            )
        if checksum is not None:
            verify_file_checksum(resolved, checksum)

    radar_stage = manifest["stages"]["radar"]
    if radar_stage["status"] == SUCCEEDED:
        _validate_radar_stage_outputs(
            manifest,
            path_base=path_base,
            allowed_roots=allowed_roots,
        )

    reaction_stage = manifest["stages"]["reaction_sync"]
    reaction_snapshot_payload: dict[str, Any] | None = None
    if (
        reaction_stage["status"] == SUCCEEDED
        and _optional_reaction_snapshot_binding(reaction_stage) is not None
    ):
        reaction_snapshot_payload = _validate_reaction_snapshot_output(
            manifest,
            path_base=path_base,
            allowed_roots=allowed_roots,
            verify_file=True,
        )

    if _all_enabled_stages_terminal(manifest):
        _validate_reader_sidecar_identities(
            manifest,
            path_base=path_base,
            reaction_snapshot_payload=reaction_snapshot_payload,
        )


def _optional_reaction_snapshot_binding(
    stage: Mapping[str, Any],
) -> tuple[str, str] | None:
    artifact_refs = stage.get("artifact_refs")
    checksums = stage.get("checksums")
    if not isinstance(artifact_refs, Mapping) or not isinstance(checksums, Mapping):
        return None
    has_path = "snapshot_path" in artifact_refs
    has_checksum = "snapshot_path" in checksums
    if has_path != has_checksum:
        raise WeeklyRunManifestError(
            "reaction snapshot path and checksum must be bound together"
        )
    if not has_path:
        return None
    path = artifact_refs.get("snapshot_path")
    if path != REACTION_SNAPSHOT_PATH:
        raise WeeklyRunManifestError(
            f"reaction snapshot path must equal {REACTION_SNAPSHOT_PATH!r}"
        )
    checksum = _required_checksum(checksums, "snapshot_path", stage="reaction_sync")
    return str(path), checksum


def _validate_reaction_snapshot_output(
    manifest: Mapping[str, Any],
    *,
    path_base: str | os.PathLike[str] | None,
    allowed_roots: Sequence[str | os.PathLike[str]],
    verify_file: bool,
) -> dict[str, Any]:
    stage = manifest["stages"]["reaction_sync"]
    binding = _optional_reaction_snapshot_binding(stage)
    if stage.get("status") != SUCCEEDED or binding is None:
        raise WeeklyRunManifestError("reaction snapshot is not bound to a succeeded stage")
    path, checksum = binding
    _validate_one_path(path, path_base=path_base, allowed_roots=allowed_roots)
    resolved = _resolve_artifact_path(path, path_base)
    if not resolved.is_file():
        raise WeeklyRunManifestError(
            f"successful stage artifact does not exist: reaction_sync: {path}"
        )
    if verify_file:
        verify_file_checksum(resolved, checksum)
    payload = dict(_load_json_object(resolved, label="reaction snapshot"))
    if payload.get("schema_version") != REACTION_SNAPSHOT_SCHEMA_VERSION:
        raise WeeklyRunManifestError("reaction snapshot schema_version mismatch")
    for field in (
        "run_id",
        "run_date",
        "generated_at",
        "reporting_week",
        "week_label",
        "period_mode",
        "analysis_period_start",
        "analysis_period_end",
    ):
        if payload.get(field) != manifest.get(field):
            raise WeeklyRunManifestError(
                f"reaction snapshot identity mismatch: {field}"
            )
    if payload.get("snapshot_ref") != stage.get("snapshot_ref"):
        raise WeeklyRunManifestError(
            "reaction snapshot identity mismatch: snapshot_ref"
        )
    expected_snapshot_ref = f"reaction-snapshot:{manifest['run_id']}"
    if stage.get("snapshot_ref") != expected_snapshot_ref:
        raise WeeklyRunManifestError(
            "bound reaction snapshot_ref does not match the manifest run_id"
        )
    if payload.get("observed_through") != stage.get("observed_through"):
        raise WeeklyRunManifestError(
            "reaction snapshot identity mismatch: observed_through"
        )
    observed_at = _parse_timestamp(
        payload.get("observed_through"), field="reaction snapshot observed_through"
    )
    started_at = _parse_timestamp(
        stage.get("started_at"), field="reaction_sync started_at"
    )
    finished_at = _parse_timestamp(
        stage.get("finished_at"), field="reaction_sync finished_at"
    )
    if observed_at < started_at or observed_at > finished_at:
        raise WeeklyRunManifestError(
            "reaction snapshot observed_through must fall within the stage attempt"
        )
    generated_at = _parse_timestamp(
        manifest.get("generated_at"), field="manifest generated_at"
    )
    if observed_at < generated_at:
        raise WeeklyRunManifestError(
            "reaction snapshot observed_through precedes manifest generation"
        )

    coverage = payload.get("coverage")
    if not isinstance(coverage, Mapping):
        raise WeeklyRunManifestError("reaction snapshot coverage must be an object")
    candidate_count = _nonnegative_int(
        coverage.get("candidate_count"),
        field="reaction snapshot coverage.candidate_count",
    )
    checked_count = _nonnegative_int(
        coverage.get("checked_count"),
        field="reaction snapshot coverage.checked_count",
    )
    for field in ("coverage_complete", "visibility_verified"):
        if not isinstance(coverage.get(field), bool):
            raise WeeklyRunManifestError(
                f"reaction snapshot coverage.{field} must be boolean"
            )
    if checked_count > candidate_count:
        raise WeeklyRunManifestError(
            "reaction snapshot checked_count cannot exceed candidate_count"
        )
    if not coverage.get("coverage_complete") or checked_count != candidate_count:
        raise WeeklyRunManifestError("reaction snapshot coverage is incomplete")
    if not coverage.get("visibility_verified"):
        raise WeeklyRunManifestError("reaction snapshot visibility is unverified")

    posts = payload.get("observed_personal_posts")
    if not isinstance(posts, list):
        raise WeeklyRunManifestError(
            "reaction snapshot observed_personal_posts must be a list"
        )
    if len(posts) > checked_count:
        raise WeeklyRunManifestError(
            "reaction snapshot observed post count exceeds checked_count"
        )
    record_counts = stage.get("record_counts")
    if not isinstance(record_counts, Mapping):
        raise WeeklyRunManifestError(
            "bound reaction snapshot requires stage record_counts"
        )
    event_count = 0
    expected_record_counts = {
        "candidate_count": candidate_count,
        "checked_count": checked_count,
        "posts_checked": checked_count,
        "observed_personal_posts": len(posts),
        "posts_with_reactions": len(posts),
        "errors": 0,
    }
    for field, expected in expected_record_counts.items():
        if record_counts.get(field) != expected:
            raise WeeklyRunManifestError(
                f"reaction snapshot/stage record_counts mismatch: {field}"
            )
    manifest_period_start = _parse_timestamp(
        manifest.get("analysis_period_start"), field="analysis_period_start"
    )
    manifest_period_end = _parse_timestamp(
        manifest.get("analysis_period_end"), field="analysis_period_end"
    )
    identities: set[tuple[str, int]] = set()
    post_ids: set[int] = set()
    for index, post in enumerate(posts):
        if not isinstance(post, Mapping):
            raise WeeklyRunManifestError(
                f"reaction snapshot post {index} must be an object"
            )
        post_id = _nonnegative_int(
            post.get("post_id"), field=f"reaction snapshot post {index}.post_id", positive=True
        )
        if post_id in post_ids:
            raise WeeklyRunManifestError(
                "reaction snapshot repeats one normalized post identity"
            )
        post_ids.add(post_id)
        channel = _nonempty_bounded(post.get("channel_username"), 300)
        message_id = _nonnegative_int(
            post.get("message_id"),
            field=f"reaction snapshot post {index}.message_id",
            positive=True,
        )
        identity = (channel.strip().lstrip("@").casefold(), message_id)
        if identity in identities:
            raise WeeklyRunManifestError("reaction snapshot contains duplicate posts")
        identities.add(identity)
        posted_at = _parse_timestamp(
            post.get("posted_at"), field=f"reaction snapshot post {index}.posted_at"
        )
        if not (
            manifest_period_start <= posted_at < manifest_period_end
        ):
            raise WeeklyRunManifestError(
                f"reaction snapshot post {index} falls outside the reporting period"
            )
        raw_emojis = post.get("raw_emojis")
        if (
            not isinstance(raw_emojis, list)
            or not raw_emojis
            or any(not isinstance(item, str) or not item.strip() for item in raw_emojis)
            or raw_emojis != sorted(set(raw_emojis))
        ):
            raise WeeklyRunManifestError(
                f"reaction snapshot post {index}.raw_emojis must be sorted unique strings"
            )
        event_count += len(raw_emojis)
    if record_counts.get("personal_reaction_events_detected") != event_count:
        raise WeeklyRunManifestError(
            "reaction snapshot/stage record_counts mismatch: "
            "personal_reaction_events_detected"
        )
    _ensure_json_value(payload, field="reaction snapshot")
    return payload
    return payload


def _validate_radar_stage_outputs(
    manifest: Mapping[str, Any],
    *,
    path_base: str | os.PathLike[str] | None,
    allowed_roots: Sequence[str | os.PathLike[str]],
) -> None:
    stage = manifest["stages"]["radar"]
    binding_path = _resolve_artifact_path(stage["binding_path"], path_base)
    binding = _load_json_object(binding_path, label="Radar binding")
    validate_radar_run_binding(
        binding,
        manifest=manifest,
        path_base=path_base,
        allowed_roots=allowed_roots,
        verify_files=True,
    )

    binding_parity = (
        ("seed_export_ref", "path", "seed_export_path"),
        ("seed_export_ref", "sha256", "seed_export_sha256"),
        ("radar_json_ref", "path", "artifact_path"),
        ("radar_json_ref", "sha256", "artifact_sha256"),
    )
    for ref_name, ref_field, stage_field in binding_parity:
        ref = binding[ref_name]
        if ref.get(ref_field) != stage.get(stage_field):
            raise WeeklyRunManifestError(
                f"Radar binding/stage mismatch for {stage_field}"
            )

    artifact_refs = stage["artifact_refs"]
    if artifact_refs:
        if artifact_refs.get("binding_path") != stage["binding_path"]:
            raise WeeklyRunManifestError("Radar artifact_refs.binding_path mismatch")

    raw_path = _resolve_artifact_path(stage["artifact_path"], path_base)
    raw = _load_json_object(raw_path, label="Radar JSON")
    raw_result = raw.get("result")
    if not isinstance(raw_result, Mapping):
        raise WeeklyRunManifestError("Radar JSON result must be an object")
    if raw_result.get("run_id") != stage["radar_run_id"]:
        raise WeeklyRunManifestError("Radar raw/stage radar_run_id mismatch")

    dependency_refs = stage["dependency_refs"]
    dependency_checksums = stage["checksums"]
    if set(dependency_refs) != set(dependency_checksums):
        raise WeeklyRunManifestError(
            "Radar dependency_refs/checksums keys must match exactly"
        )
    for key, value in dependency_refs.items():
        if not isinstance(value, str) or not value.strip():
            raise WeeklyRunManifestError(f"Radar dependency path is invalid: {key}")
        checksum = _required_checksum(dependency_checksums, key, stage="radar")
        _validate_one_path(value, path_base=path_base, allowed_roots=allowed_roots)
        resolved = _resolve_artifact_path(value, path_base)
        if not resolved.is_file():
            raise WeeklyRunManifestError(f"Radar dependency does not exist: {key}: {value}")
        verify_file_checksum(resolved, checksum)
    market_lens_path = stage.get("market_lens_path")
    if market_lens_path is not None and dependency_refs.get("market_lens_path") != market_lens_path:
        raise WeeklyRunManifestError("Radar market_lens_path/dependency_refs mismatch")


def _validate_reader_sidecar_identities(
    manifest: Mapping[str, Any],
    *,
    path_base: str | os.PathLike[str] | None,
    reaction_snapshot_payload: Mapping[str, Any] | None,
) -> None:
    expected_status = _expected_terminal_status(manifest)
    expected_identity = {
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
    expected_identity["run_status"] = expected_status
    expected_identity["partial"] = bool(manifest["partial"])
    expected_identity["failed_stages"] = list(manifest["failed_stages"])
    expected_identity["warnings"] = list(manifest["warnings"])
    expected_manifest_path = (
        (Path(path_base).resolve() / "manifest.json") if path_base is not None else None
    )
    reaction_effects: dict[str, dict[str, Any]] = {}
    reaction_stage = manifest["stages"]["reaction_sync"]
    rich_reaction_snapshot_bound = (
        reaction_stage["status"] == SUCCEEDED
        and _optional_reaction_snapshot_binding(reaction_stage) is not None
    )

    for stage_name in ("weekly_brief", "knowledge_atlas"):
        stage = manifest["stages"][stage_name]
        if stage["status"] != SUCCEEDED:
            continue
        json_path = _resolve_artifact_path(stage["json_path"], path_base)
        sidecar = _load_json_object(json_path, label=f"{stage_name} sidecar")
        if not isinstance(sidecar.get("partial"), bool):
            raise WeeklyRunManifestError(
                f"{stage_name} sidecar identity mismatch: partial"
            )
        for field, expected in expected_identity.items():
            if sidecar.get(field) != expected:
                raise WeeklyRunManifestError(
                    f"{stage_name} sidecar identity mismatch: {field}"
                )

        manifest_path_value = sidecar.get("manifest_path")
        if not isinstance(manifest_path_value, str) or not manifest_path_value.strip():
            raise WeeklyRunManifestError(
                f"{stage_name} sidecar identity mismatch: manifest_path"
            )
        manifest_path_resolved = _resolve_artifact_path(manifest_path_value, path_base)
        if expected_manifest_path is not None and manifest_path_resolved != expected_manifest_path:
            raise WeeklyRunManifestError(
                f"{stage_name} sidecar identity mismatch: manifest_path"
            )

        expected_paths = {
            "html_path": _resolve_artifact_path(stage["html_path"], path_base),
            "json_path": json_path,
        }
        for field, expected_path in expected_paths.items():
            value = sidecar.get(field)
            if not isinstance(value, str) or not value.strip():
                raise WeeklyRunManifestError(
                    f"{stage_name} sidecar identity mismatch: {field}"
                )
            if _resolve_artifact_path(value, path_base) != expected_path:
                raise WeeklyRunManifestError(
                    f"{stage_name} sidecar identity mismatch: {field}"
                )
        artifact_paths = sidecar.get("artifact_paths")
        if not isinstance(artifact_paths, Mapping):
            raise WeeklyRunManifestError(f"{stage_name} sidecar artifact_paths must be an object")
        for key, field in (("html", "html_path"), ("json", "json_path")):
            value = artifact_paths.get(key)
            if not isinstance(value, str) or not value.strip():
                raise WeeklyRunManifestError(
                    f"{stage_name} sidecar artifact_paths.{key} is invalid"
                )
            if _resolve_artifact_path(value, path_base) != expected_paths[field]:
                raise WeeklyRunManifestError(
                    f"{stage_name} sidecar artifact_paths.{key} mismatch"
                )

        reaction_effect = sidecar.get("reaction_effect")
        if reaction_effect is None and rich_reaction_snapshot_bound:
            raise WeeklyRunManifestError(
                f"{stage_name} sidecar reaction_effect is required when a verified "
                "reaction snapshot is bound"
            )
        if reaction_effect is not None:
            reaction_effects[stage_name] = _validate_reader_reaction_effect(
                reaction_effect,
                manifest=manifest,
                stage_name=stage_name,
                reaction_snapshot_payload=reaction_snapshot_payload,
            )
            _validate_reaction_effect_surface_refs(
                reaction_effects[stage_name],
                sidecar=sidecar,
                stage_name=stage_name,
            )

    brief_succeeded = manifest["stages"]["weekly_brief"]["status"] == SUCCEEDED
    atlas_succeeded = manifest["stages"]["knowledge_atlas"]["status"] == SUCCEEDED
    if brief_succeeded and atlas_succeeded:
        if bool(reaction_effects.get("weekly_brief")) != bool(
            reaction_effects.get("knowledge_atlas")
        ):
            raise WeeklyRunManifestError(
                "reader reaction_effect must be present on both succeeded surfaces"
            )
        if reaction_effects:
            _validate_cross_surface_reaction_effects(
                reaction_effects["weekly_brief"],
                reaction_effects["knowledge_atlas"],
            )


def _validate_cross_surface_reaction_effects(
    brief_effect: Mapping[str, Any],
    atlas_effect: Mapping[str, Any],
) -> None:
    common_identity_fields = (
        "schema_version",
        "run_id",
        "reporting_week",
        "analysis_period_start",
        "analysis_period_end",
        "snapshot_ref",
        "snapshot_status",
        "ranking_policy",
    )
    if any(
        brief_effect.get(field) != atlas_effect.get(field)
        for field in common_identity_fields
    ):
        raise WeeklyRunManifestError(
            "reader reaction_effect common identity differs across surfaces"
        )
    common_count_fields = (
        "personal_reaction_events_detected",
        "unique_reacted_posts",
        "posts_resolved",
        "eligible_period_posts",
        "unique_atoms_linked",
        "unique_canonical_threads_linked",
        "canonical_threads_boosted",
        "unique_compatibility_threads_linked",
        "compatibility_threads_boosted",
    )
    brief_counts = brief_effect.get("counts")
    atlas_counts = atlas_effect.get("counts")
    if not isinstance(brief_counts, Mapping) or not isinstance(atlas_counts, Mapping) or any(
        brief_counts.get(field) != atlas_counts.get(field)
        for field in common_count_fields
    ):
        raise WeeklyRunManifestError(
            "reader reaction_effect common funnel differs across surfaces"
        )

    def shared_audit(effect: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for item in effect.get("eligible_thread_audit") or []:
            if not isinstance(item, Mapping):
                continue
            compatibility_ref = str(item.get("compatibility_thread_ref") or "")
            result[compatibility_ref] = {
                key: value
                for key, value in item.items()
                if key not in {"selected", "counterfactual_effect"}
            }
        return result

    if shared_audit(brief_effect) != shared_audit(atlas_effect):
        raise WeeklyRunManifestError(
            "reader reaction_effect attribution differs across surfaces"
        )


def _validate_reader_reaction_effect(
    value: Any,
    *,
    manifest: Mapping[str, Any],
    stage_name: str,
    reaction_snapshot_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise WeeklyRunManifestError(
            f"{stage_name} sidecar reaction_effect must be an object"
        )
    effect = dict(value)
    if effect.get("schema_version") != REACTION_EFFECT_SCHEMA_VERSION:
        raise WeeklyRunManifestError(
            f"{stage_name} sidecar reaction_effect schema mismatch"
        )
    expected_surface = (
        "weekly_brief" if stage_name == "weekly_brief" else "knowledge_atlas"
    )
    if effect.get("surface") != expected_surface:
        raise WeeklyRunManifestError(
            f"{stage_name} sidecar reaction_effect surface mismatch"
        )
    if effect.get("run_id") != manifest.get("run_id"):
        raise WeeklyRunManifestError(
            f"{stage_name} sidecar reaction_effect run_id mismatch"
        )
    for field in (
        "reporting_week",
        "analysis_period_start",
        "analysis_period_end",
    ):
        if effect.get(field) != manifest.get(field):
            raise WeeklyRunManifestError(
                f"{stage_name} sidecar reaction_effect period mismatch: {field}"
            )
    for optional_field in ("run_date", "generated_at", "week_label", "period_mode"):
        if optional_field in effect and effect.get(optional_field) != manifest.get(
            optional_field
        ):
            raise WeeklyRunManifestError(
                f"{stage_name} sidecar reaction_effect period mismatch: {optional_field}"
            )
    reaction_stage = manifest["stages"]["reaction_sync"]
    if effect.get("snapshot_ref") != reaction_stage.get("snapshot_ref"):
        raise WeeklyRunManifestError(
            f"{stage_name} sidecar reaction_effect snapshot_ref mismatch"
        )
    expected_snapshot_status = (
        "complete"
        if (
            reaction_stage["status"] == SUCCEEDED
            and _optional_reaction_snapshot_binding(reaction_stage) is not None
        )
        else "unavailable"
        if reaction_stage["status"] == SUCCEEDED
        else "partial"
    )
    if effect.get("snapshot_status") != expected_snapshot_status:
        raise WeeklyRunManifestError(
            f"{stage_name} sidecar reaction_effect snapshot_status mismatch"
        )
    counts = effect.get("counts")
    if not isinstance(counts, Mapping):
        raise WeeklyRunManifestError(
            f"{stage_name} sidecar reaction_effect counts must be an object"
        )
    for key, count in counts.items():
        if not isinstance(key, str) or not key:
            raise WeeklyRunManifestError(
                f"{stage_name} sidecar reaction_effect count key is invalid"
            )
        _nonnegative_int(
            count,
            field=f"{stage_name} sidecar reaction_effect counts.{key}",
        )
    # Keep the manifest quality gate in lockstep with the deterministic
    # ranking receipt: identity parity alone must not bless a logically
    # contradictory effect claim.
    from output.reaction_personalization import (
        ReactionPersonalizationError,
        validate_reaction_effect,
    )

    try:
        validate_reaction_effect(effect)
    except ReactionPersonalizationError as exc:
        raise WeeklyRunManifestError(
            f"{stage_name} sidecar reaction_effect is invalid: {exc}"
        ) from exc
    rich_reaction_snapshot_bound = (
        reaction_stage["status"] == SUCCEEDED
        and _optional_reaction_snapshot_binding(reaction_stage) is not None
    )
    if rich_reaction_snapshot_bound:
        if reaction_snapshot_payload is None:
            raise WeeklyRunManifestError(
                f"{stage_name} sidecar reaction_effect has no validated reaction snapshot"
            )
        _validate_reaction_effect_snapshot_lineage(
            effect,
            snapshot_payload=reaction_snapshot_payload,
            stage_name=stage_name,
        )
    feedback_succeeded = manifest["stages"]["feedback_snapshot"]["status"] == SUCCEEDED
    if rich_reaction_snapshot_bound and not feedback_succeeded:
        if effect.get("status") != "partial":
            raise WeeklyRunManifestError(
                f"{stage_name} sidecar reaction_effect must be partial when the "
                "confirmed-feedback snapshot is unavailable"
            )
        event_count = int(effect["counts"]["personal_reaction_events_detected"])
        expected_reasons = (
            {"confirmed_feedback_snapshot_unverified": event_count}
            if event_count
            else {}
        )
        if effect.get("unconsumed_by_reason") != expected_reasons:
            raise WeeklyRunManifestError(
                f"{stage_name} sidecar reaction_effect must attribute unavailable "
                "personalization to the confirmed-feedback snapshot"
            )
    elif rich_reaction_snapshot_bound and effect.get("status") in {
        "partial",
        "unavailable",
    }:
        raise WeeklyRunManifestError(
            f"{stage_name} sidecar reaction_effect cannot be partial when both "
            "reaction and confirmed-feedback snapshots succeeded"
        )
    _ensure_json_value(effect, field=f"{stage_name} sidecar reaction_effect")
    return effect


def _validate_reaction_effect_snapshot_lineage(
    effect: Mapping[str, Any],
    *,
    snapshot_payload: Mapping[str, Any],
    stage_name: str,
) -> None:
    posts = snapshot_payload.get("observed_personal_posts")
    if not isinstance(posts, list):
        raise WeeklyRunManifestError("validated reaction snapshot lost its post list")

    post_sources: dict[str, str] = {}
    reaction_to_post: dict[str, str] = {}
    ordered_reaction_refs: list[str] = []
    event_count = 0
    for post in posts:
        if not isinstance(post, Mapping):
            raise WeeklyRunManifestError("validated reaction snapshot contains an invalid post")
        normalized_channel = str(post.get("channel_username") or "").strip().lstrip("@").casefold()
        message_id = str(post.get("message_id") or "")
        post_id = str(post.get("post_id") or "")
        post_value = ":".join((normalized_channel, message_id, post_id))
        post_ref = "reaction-post:" + hashlib.sha256(
            post_value.encode("utf-8")
        ).hexdigest()[:24]
        post_sources[post_ref] = f"telegram:@{normalized_channel}"
        raw_emojis = post.get("raw_emojis")
        if not isinstance(raw_emojis, list):
            raise WeeklyRunManifestError("validated reaction snapshot lost reaction events")
        for raw_emoji in raw_emojis:
            reaction_value = ":".join(
                (normalized_channel, message_id, str(raw_emoji))
            )
            reaction_ref = (
                "reaction:"
                + hashlib.sha256(reaction_value.encode("utf-8")).hexdigest()[:24]
            )
            reaction_to_post[reaction_ref] = post_ref
            ordered_reaction_refs.append(reaction_ref)
            event_count += 1

    counts = effect["counts"]
    expected_counts = {
        "personal_reaction_events_detected": event_count,
        "unique_reacted_posts": len(posts),
    }
    for field, expected in expected_counts.items():
        if counts.get(field) != expected:
            raise WeeklyRunManifestError(
                f"{stage_name} sidecar reaction_effect/snapshot mismatch: {field}"
            )

    for collection_name in (
        "influenced_items",
        "linked_only_items",
        "eligible_thread_audit",
    ):
        items = effect.get(collection_name)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, Mapping):
                continue
            item_post_refs = item.get("reacted_post_refs")
            item_source_refs = item.get("source_refs")
            if not isinstance(item_post_refs, list) or any(
                post_ref not in post_sources for post_ref in item_post_refs
            ):
                raise WeeklyRunManifestError(
                    f"{stage_name} sidecar reaction_effect contains a post outside "
                    "the bound reaction snapshot"
                )
            expected_sources = sorted({post_sources[post_ref] for post_ref in item_post_refs})
            if item_source_refs != expected_sources:
                raise WeeklyRunManifestError(
                    f"{stage_name} sidecar reaction_effect source lineage contradicts "
                    "the bound reaction snapshot"
                )

    audit = effect.get("eligible_thread_audit")
    consumed_post_refs = {
        post_ref
        for item in audit or []
        if isinstance(item, Mapping) and item.get("selected") is True
        for post_ref in item.get("reacted_post_refs") or []
    }
    expected_unconsumed_refs = [
        reaction_ref
        for reaction_ref in ordered_reaction_refs
        if reaction_to_post[reaction_ref] not in consumed_post_refs
    ]
    if counts.get("unconsumed_reaction_events") != len(expected_unconsumed_refs):
        raise WeeklyRunManifestError(
            f"{stage_name} sidecar reaction_effect loses or double-consumes "
            "snapshot reaction events"
        )
    unconsumed = effect.get("unconsumed")
    actual_unconsumed_refs = [
        item.get("reaction_ref")
        for item in unconsumed or []
        if isinstance(item, Mapping)
    ]
    expected_sample = expected_unconsumed_refs[:25]
    if (
        not isinstance(unconsumed, list)
        or len(actual_unconsumed_refs) != len(unconsumed)
        or actual_unconsumed_refs != expected_sample
    ):
        raise WeeklyRunManifestError(
            f"{stage_name} sidecar reaction_effect unconsumed lineage does not "
            "match the bound reaction snapshot"
        )


def _validate_reaction_effect_surface_refs(
    effect: Mapping[str, Any],
    *,
    sidecar: Mapping[str, Any],
    stage_name: str,
) -> None:
    selected_refs = {
        str(item.get("surface_item_ref") or "").strip()
        for collection_name in ("influenced_items", "linked_only_items")
        for item in effect.get(collection_name) or []
        if isinstance(item, Mapping)
    }
    if not selected_refs:
        return
    if stage_name == "weekly_brief":
        available_refs = {
            str(item.get("surface_item_ref") or "").strip()
            for item in sidecar.get("actions") or []
            if isinstance(item, Mapping)
        }
    else:
        navigation = sidecar.get("thread_navigation")
        navigation_threads = (
            navigation.get("threads")
            if isinstance(navigation, Mapping)
            else []
        )
        available_refs = {
            f"thread:{str(item.get('slug') or '').strip()}"
            for item in navigation_threads or []
            if isinstance(item, Mapping) and str(item.get("slug") or "").strip()
        }
    missing = sorted(selected_refs.difference(available_refs))
    if missing:
        raise WeeklyRunManifestError(
            f"{stage_name} sidecar reaction_effect references items absent from "
            f"the rendered surface: {', '.join(missing)}"
        )


def _load_json_object(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WeeklyRunManifestError(f"cannot load {label}: {path}") from exc
    if not isinstance(payload, Mapping):
        raise WeeklyRunManifestError(f"{label} must be an object")
    return payload


def _required_checksum(
    checksums: Mapping[str, Any], key: str, *, stage: str
) -> str:
    value = checksums.get(key)
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise WeeklyRunManifestError(
            f"{stage}.checksums.{key} must be lowercase SHA-256"
        )
    return value


def _all_enabled_stages_terminal(manifest: Mapping[str, Any]) -> bool:
    return all(
        not manifest["stage_policy"][name]["enabled"]
        or manifest["stages"][name]["status"] not in {PENDING, RUNNING}
        for name in IRX2_STAGE_ORDER
    )


def _expected_terminal_status(manifest: Mapping[str, Any]) -> str:
    status = str(manifest["run_status"])
    if status != RUNNING:
        return status
    if not _all_enabled_stages_terminal(manifest):
        raise WeeklyRunManifestError("cannot derive reader identity while stages are active")
    if _has_fatal_failure(manifest):
        return FAILED
    if _derived_partial(manifest) or not _all_required_succeeded(manifest):
        return "partial"
    return "complete"


def _validate_paths(
    manifest: Mapping[str, Any],
    *,
    path_base: str | os.PathLike[str] | None,
    allowed_roots: Sequence[str | os.PathLike[str]],
) -> None:
    for field, value in _iter_path_values(manifest):
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise WeeklyRunManifestError(f"{field} must be a non-empty path or null")
        _validate_one_path(value, path_base=path_base, allowed_roots=allowed_roots)


def _iter_path_values(manifest: Mapping[str, Any]) -> Iterable[tuple[str, Any]]:
    top = (
        "frontier_analysis_path",
        "market_lens_path",
        "radar_json_path",
        "weekly_brief_html_path",
        "weekly_brief_json_path",
        "atlas_html_path",
        "atlas_json_path",
        "audit_explorer_path",
    )
    for field in top:
        yield field, manifest.get(field)
    refs = ("frontier_analysis_ref", "radar_json_ref")
    for ref_name in refs:
        ref = manifest.get(ref_name)
        if isinstance(ref, Mapping):
            for key, value in ref.items():
                if key == "path" or key.endswith("_path"):
                    yield f"{ref_name}.{key}", value
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, Mapping):
        for key, value in artifacts.items():
            if key.endswith("_path"):
                yield f"artifacts.{key}", value
    stages = manifest.get("stages")
    if isinstance(stages, Mapping):
        for name, stage in stages.items():
            if not isinstance(stage, Mapping):
                continue
            for key, value in stage.items():
                if key.endswith("_path"):
                    yield f"stages.{name}.{key}", value
            for container in ("dependency_refs", "artifact_refs"):
                nested = stage.get(container)
                if isinstance(nested, Mapping):
                    for key, value in nested.items():
                        if key == "path" or key.endswith("_path"):
                            yield f"stages.{name}.{container}.{key}", value


def _validate_one_path(
    value: str,
    *,
    path_base: str | os.PathLike[str] | None,
    allowed_roots: Sequence[str | os.PathLike[str]],
) -> None:
    if "\x00" in value:
        raise WeeklyRunManifestError("artifact path contains a NUL byte")
    candidate = Path(value)
    if path_base is None and not allowed_roots:
        if candidate.is_absolute() or ".." in PurePath(value).parts:
            raise WeeklyRunManifestError(f"artifact path escapes the implicit root: {value}")
        return
    base = Path(path_base).resolve() if path_base is not None else Path.cwd().resolve()
    resolved = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
    roots = [Path(root).resolve() for root in allowed_roots]
    if not roots:
        roots = [base]
    if not any(_is_relative_to(resolved, root) for root in roots):
        raise WeeklyRunManifestError(f"artifact path escapes declared roots: {value}")


def _resolve_artifact_path(
    value: str | os.PathLike[str], path_base: str | os.PathLike[str] | None
) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    base = Path(path_base).resolve() if path_base is not None else Path.cwd().resolve()
    return (base / candidate).resolve()


def _period_from_manifest(manifest: Mapping[str, Any]) -> ReportingPeriod:
    try:
        generated_at = _require_string(manifest, "generated_at")
        run_date_text = _require_string(manifest, "run_date")
        period = ReportingPeriod(
            run_date=datetime.fromisoformat(run_date_text).date(),
            generated_at=generated_at,
            analysis_period_start=_require_string(manifest, "analysis_period_start"),
            analysis_period_end=_require_string(manifest, "analysis_period_end"),
            reporting_week=_require_string(manifest, "reporting_week"),
            period_mode=_require_string(manifest, "period_mode"),  # type: ignore[arg-type]
        )
    except (ReportingPeriodError, ValueError) as exc:
        raise WeeklyRunManifestError(f"invalid reporting period: {exc}") from exc
    canonical = period.to_dict()
    for field in (
        "run_date",
        "generated_at",
        "analysis_period_start",
        "analysis_period_end",
        "reporting_week",
        "week_label",
        "period_mode",
    ):
        if manifest.get(field) != canonical[field]:
            raise WeeklyRunManifestError(f"non-canonical period field: {field}")
    return period


def _sanitize_created_by(value: Mapping[str, Any] | None) -> dict[str, Any]:
    source = value or {}
    if not isinstance(source, Mapping):
        raise WeeklyRunManifestError("created_by must be an object")
    return {
        "command": _bounded_text(source.get("command") or "weekly-intelligence-v2", 200),
        "host": _bounded_text(source.get("host") or "redacted", 200),
        "git_commit": _bounded_text(source.get("git_commit"), 100) or None,
    }


def _validate_created_by(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {"command", "host", "git_commit"}:
        raise WeeklyRunManifestError("created_by fields do not match contract")
    if not value.get("command") or value["command"] != _bounded_text(value["command"], 200):
        raise WeeklyRunManifestError("created_by.command is invalid")
    if not value.get("host") or value["host"] != _bounded_text(value["host"], 200):
        raise WeeklyRunManifestError("created_by.host is invalid")
    commit = value.get("git_commit")
    if commit is not None and commit != _bounded_text(commit, 100):
        raise WeeklyRunManifestError("created_by.git_commit is invalid")


def _validate_error(value: Mapping[str, Any], stage_name: str) -> None:
    if set(value) != {"type", "code", "message", "retryable"}:
        raise WeeklyRunManifestError(f"error fields do not match contract: {stage_name}")
    if value.get("type") != _bounded_text(value.get("type"), 100) or not value.get("type"):
        raise WeeklyRunManifestError(f"invalid error type: {stage_name}")
    code = value.get("code")
    if code is not None and code != _bounded_text(code, 80):
        raise WeeklyRunManifestError(f"invalid error code: {stage_name}")
    message = value.get("message")
    if not message or message != _redact_secrets(_bounded_text(message, _MAX_ERROR_MESSAGE)):
        raise WeeklyRunManifestError(f"error message is unbounded or contains a secret: {stage_name}")
    if not isinstance(value.get("retryable"), bool):
        raise WeeklyRunManifestError(f"error.retryable must be boolean: {stage_name}")


def _validate_record_counts(value: Any, stage_name: str) -> None:
    if not isinstance(value, Mapping):
        raise WeeklyRunManifestError(f"record_counts must be an object: {stage_name}")
    for key, count in value.items():
        if not isinstance(key, str) or not key or len(key) > 100:
            raise WeeklyRunManifestError(f"invalid record count key: {stage_name}")
        _nonnegative_int(count, field=f"stages.{stage_name}.record_counts.{key}")


def _atomic_create_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ManifestExistsError(f"immutable artifact already exists: {path}")
    temp_path = _write_temp_json(path.parent, payload)
    try:
        try:
            os.link(temp_path, path)
        except FileExistsError as exc:
            raise ManifestExistsError(f"immutable artifact already exists: {path}") from exc
        _fsync_directory(path.parent)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _atomic_replace_json(path: Path, payload: Mapping[str, Any]) -> None:
    temp_path = _write_temp_json(path.parent, payload)
    try:
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _write_temp_json(directory: Path, payload: Mapping[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n").encode("utf-8")
    fd, name = tempfile.mkstemp(prefix=".manifest-", suffix=".tmp", dir=directory)
    path = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise
    return path


def _fsync_directory(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _parse_timestamp(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise WeeklyRunManifestError(f"{field} must be a canonical UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise WeeklyRunManifestError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WeeklyRunManifestError(f"{field} must include UTC timezone")
    return parsed.astimezone(timezone.utc)


def _canonical_timestamp(value: Any, *, field: str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise WeeklyRunManifestError(f"{field} must include an explicit timezone")
        parsed = value.astimezone(timezone.utc)
    else:
        parsed = _parse_timestamp(value, field=field)
    return parsed.isoformat().replace("+00:00", "Z")


def _bounded_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    text = _CONTROL_RE.sub(" ", str(value)).strip()
    text = " ".join(text.split())
    return text[:limit]


def _redact_secrets(value: str) -> str:
    value = _BEARER_RE.sub("Bearer [REDACTED]", value)
    return _SENSITIVE_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)


def _nonempty_bounded(value: Any, limit: int) -> str:
    clean = _bounded_text(value, limit)
    if not clean or clean != value:
        raise WeeklyRunManifestError("required string is empty or exceeds its bound")
    return clean


def _require_string(mapping: Mapping[str, Any], field: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value:
        raise WeeklyRunManifestError(f"{field} must be a non-empty string")
    return value


def _require_bool(mapping: Mapping[str, Any], field: str) -> bool:
    value = mapping.get(field)
    if not isinstance(value, bool):
        raise WeeklyRunManifestError(f"{field} must be boolean")
    return value


def _require_equal(mapping: Mapping[str, Any], field: str, expected: Any) -> None:
    if mapping.get(field) != expected:
        raise WeeklyRunManifestError(f"{field} must equal {expected!r}")


def _nonnegative_int(value: Any, *, field: str, positive: bool = False) -> int:
    minimum = 1 if positive else 0
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise WeeklyRunManifestError(f"{field} must be an integer >= {minimum}")
    return value


def _validate_run_id(value: str, *, field: str = "run_id") -> None:
    if not isinstance(value, str) or not _RUN_ID_RE.fullmatch(value):
        raise WeeklyRunManifestError(f"{field} is not filesystem-safe")


def _ensure_json_value(value: Any, *, field: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WeeklyRunManifestError(f"{field} is not deterministic JSON data") from exc


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
