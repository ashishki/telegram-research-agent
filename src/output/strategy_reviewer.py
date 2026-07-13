from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from config.settings import PROJECT_ROOT
from db.ai_report_feedback import summarize_ai_report_feedback
from output.reaction_personalization import (
    ReactionPersonalizationError,
    build_reaction_pattern_proposals,
    validate_reaction_effect,
)
from output.weekly_run_manifest import (
    TERMINAL_RUN_STATUSES,
    WeeklyRunManifestError,
    load_manifest,
    validate_manifest,
    verify_file_checksum,
)


DEFAULT_WEEKLY_RUN_ROOT = PROJECT_ROOT / "data" / "output" / "weekly_intelligence_runs"
_COMPLETED_PERIOD_MODES = frozenset({"completed_iso_week", "explicit_iso_week"})
_READABLE_TERMINAL_RUN_STATUSES = frozenset({"complete", "partial"})
_ISO_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")
_ISO_WEEK_IN_TEXT_RE = re.compile(r"(?<!\d)(\d{4}-W\d{2})(?!\d)")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _task(
    *,
    title: str,
    files: list[str],
    acceptance_criteria: list[str],
    verification_commands: list[str],
    rationale: str,
) -> dict[str, Any]:
    return {
        "title": title,
        "rationale": rationale,
        "files": files,
        "acceptance_criteria": acceptance_criteria,
        "verification_commands": verification_commands,
        "requires_approval": True,
        "mutation_policy": "suggestion_only_no_auto_edit",
    }


def load_reaction_pattern_observations(
    weekly_run_root: str | Path,
) -> list[dict[str, object]]:
    """Load immutable completed-week reaction observations for Strategy Reviewer.

    One authoritative terminal run is selected per ISO week.  The newest
    candidate is never replaced by an older run when its manifest, checksum,
    identity, or receipt is invalid; that week simply contributes no signal.
    """

    try:
        root = Path(weekly_run_root).expanduser().resolve()
        manifest_paths: list[tuple[Path, bool]] = []
        if root.is_dir():
            for candidate in root.glob("*/manifest.json"):
                try:
                    resolved = candidate.resolve()
                except (OSError, RuntimeError):
                    resolved = candidate.absolute()
                contained = resolved.parent.parent == root
                manifest_paths.append(
                    (resolved if contained else candidate.absolute(), not contained)
                )
            manifest_paths.sort(key=lambda item: str(item[0]))
    except (OSError, RuntimeError, TypeError, ValueError):
        return []
    selected: dict[str, tuple[tuple[int, str, str], Path, bool]] = {}
    for manifest_path, uncontained in manifest_paths:
        payload = None if uncontained else _read_json_object(manifest_path)
        # Select authority from the raw week identity before trusting status or
        # period-mode fields.  A newer malformed candidate for the same week
        # must block older receipts instead of disappearing from selection.
        payload_week = (
            _candidate_reporting_week(payload) if payload is not None else None
        )
        directory_week = _run_dir_reporting_week(manifest_path.parent.name)
        fully_valid = False
        if payload is not None and not uncontained:
            run_dir = manifest_path.parent.resolve()
            try:
                load_manifest(
                    manifest_path,
                    path_base=run_dir,
                    allowed_roots=(run_dir,),
                    check_artifact_existence=True,
                )
            except (
                OSError,
                UnicodeError,
                TypeError,
                ValueError,
                WeeklyRunManifestError,
            ):
                pass
            else:
                fully_valid = True
        reporting_weeks = (
            {payload_week}
            if fully_valid and payload_week is not None
            else {week for week in (payload_week, directory_week) if week is not None}
        )
        if not reporting_weeks:
            continue
        key = (
            (2**63 - 1, manifest_path.parent.name, str(manifest_path.absolute()))
            if uncontained
            else
            _manifest_authority_key(payload, manifest_path)
            if payload is not None
            else (
                _filesystem_freshness_ns(manifest_path),
                manifest_path.parent.name,
                str(manifest_path.resolve()),
            )
        )
        for reporting_week in reporting_weeks:
            previous = selected.get(reporting_week)
            if previous is None or key > previous[0]:
                selected[reporting_week] = (
                    key,
                    manifest_path.absolute() if uncontained else manifest_path.resolve(),
                    uncontained,
                )

    observations: list[dict[str, object]] = []
    for reporting_week in sorted(selected):
        _key, manifest_path, uncontained = selected[reporting_week]
        if uncontained:
            continue
        loaded = _load_manifest_week_observations(
            manifest_path,
            expected_week=reporting_week,
        )
        if loaded is not None:
            observations.extend(loaded)
    return sorted(
        observations,
        key=lambda item: (
            str(item.get("reporting_week") or ""),
            str(item.get("canonical_thread_ref") or ""),
            str(item.get("compatibility_thread_ref") or ""),
            tuple(str(value) for value in item.get("reacted_post_refs") or ()),
        ),
    )


def _completed_terminal_week(manifest: Mapping[str, object]) -> str | None:
    reporting_week = _candidate_reporting_week(manifest)
    if reporting_week is None:
        return None
    if manifest.get("period_mode") not in _COMPLETED_PERIOD_MODES:
        return None
    if manifest.get("run_status") not in TERMINAL_RUN_STATUSES:
        return None
    return reporting_week


def _candidate_reporting_week(manifest: Mapping[str, object]) -> str | None:
    reporting_week = str(manifest.get("reporting_week") or "").strip()
    match = _ISO_WEEK_RE.fullmatch(reporting_week)
    if match is None:
        return None
    try:
        datetime.fromisocalendar(int(match.group(1)), int(match.group(2)), 1)
    except ValueError:
        return None
    return reporting_week


def _run_dir_reporting_week(value: str) -> str | None:
    match = _ISO_WEEK_IN_TEXT_RE.search(str(value or ""))
    if match is None:
        return None
    week_label = match.group(1)
    year_text, week_text = week_label.split("-W", 1)
    try:
        datetime.fromisocalendar(int(year_text), int(week_text), 1)
    except ValueError:
        return None
    return week_label


def _previous_iso_week_label(value: str | None) -> str | None:
    if value is None:
        return None
    match = _ISO_WEEK_RE.fullmatch(str(value).strip())
    if match is None:
        return str(value).strip()
    try:
        week_start = datetime.fromisocalendar(
            int(match.group(1)),
            int(match.group(2)),
            1,
        )
    except ValueError:
        return str(value).strip()
    prior = week_start - timedelta(weeks=1)
    year, week, _weekday = prior.isocalendar()
    return f"{year}-W{week:02d}"


def _manifest_authority_key(
    manifest: Mapping[str, object],
    manifest_path: Path,
) -> tuple[int, str, str]:
    try:
        validate_manifest(manifest)
        freshness = _timestamp_ns(manifest.get("generated_at"))
    except (TypeError, ValueError, WeeklyRunManifestError):
        freshness = _filesystem_freshness_ns(manifest_path)
    return (
        freshness,
        str(manifest.get("run_id") or manifest_path.parent.name),
        str(manifest_path.resolve()),
    )


def _load_manifest_week_observations(
    manifest_path: Path,
    *,
    expected_week: str,
) -> list[dict[str, object]] | None:
    run_dir = manifest_path.parent.resolve()
    try:
        manifest = load_manifest(
            manifest_path,
            path_base=run_dir,
            allowed_roots=(run_dir,),
            check_artifact_existence=True,
        )
    except (OSError, UnicodeError, TypeError, ValueError, WeeklyRunManifestError):
        return None
    if _completed_terminal_week(manifest) != expected_week:
        return None
    if manifest.get("run_status") not in _READABLE_TERMINAL_RUN_STATUSES:
        return None
    stage = _mapping(manifest.get("stages"), "weekly_brief")
    if stage is None or stage.get("status") != "succeeded":
        return None
    json_path = _contained_run_path(run_dir, stage.get("json_path"))
    checksums = stage.get("checksums")
    if json_path is None or not isinstance(checksums, Mapping):
        return None
    try:
        verify_file_checksum(json_path, str(checksums.get("json_path") or ""))
    except (OSError, TypeError, ValueError, WeeklyRunManifestError):
        return None
    sidecar = _read_json_object(json_path)
    if sidecar is None or sidecar.get("artifact_type") != "weekly_intelligence_brief":
        return None
    if not _reader_identity_matches(sidecar, manifest, manifest_path, json_path):
        return None
    raw_effect = sidecar.get("reaction_effect")
    if not isinstance(raw_effect, Mapping):
        return None
    try:
        effect = validate_reaction_effect(raw_effect)
    except (TypeError, ValueError, ReactionPersonalizationError):
        return None
    if not _effect_identity_matches(effect, manifest):
        return None
    return _effect_observations(effect, manifest)


def _effect_observations(
    effect: Mapping[str, object],
    manifest: Mapping[str, object],
) -> list[dict[str, object]] | None:
    result: list[dict[str, object]] = []
    values = effect.get("eligible_thread_audit")
    if not isinstance(values, list):
        return None
    for raw_item in values:
        if not isinstance(raw_item, Mapping):
            return None
        canonical_ref = _optional_text(raw_item.get("canonical_thread_ref"))
        compatibility_ref = _optional_text(
            raw_item.get("compatibility_thread_ref")
            or raw_item.get("current_thread_ref")
        )
        reacted_post_refs = _strict_string_list(raw_item.get("reacted_post_refs"))
        source_refs = _strict_string_list(raw_item.get("source_refs"))
        if (
            not (canonical_ref or compatibility_ref)
            or not reacted_post_refs
            or not source_refs
        ):
            return None
        result.append(
            {
                "reporting_week": str(manifest["reporting_week"]),
                "period_mode": str(manifest["period_mode"]),
                "completed": True,
                "canonical_thread_ref": canonical_ref,
                "compatibility_thread_ref": compatibility_ref,
                "reacted_post_refs": reacted_post_refs,
                "source_refs": source_refs,
            }
        )
    return result


def _attach_exact_confirmed_feedback(
    observations: Iterable[Mapping[str, object]],
    summary: Mapping[str, object],
) -> list[dict[str, object]]:
    """Attach only exact confirmed target identities from the feedback summary.

    Reaction lineage and explicit feedback are deliberately joined by the
    already-normalized target reference (for example
    ``idea_thread:eval-gates``).  Titles, slugs embedded in prose, sources, and
    other adjacent target types are not similarity evidence.
    """

    if summary.get("confirmation_state") != "confirmed_only":
        supporting_targets: set[str] = set()
        contradicting_targets: set[str] = set()
    else:
        supporting_targets = set(
            _strict_string_list(summary.get("promoted_target_refs")) or []
        )
        contradicting_targets = set(
            _strict_string_list(summary.get("downranked_target_refs")) or []
        )

    result: list[dict[str, object]] = []
    for raw_observation in observations:
        observation = dict(raw_observation)
        target_refs = {
            ref
            for ref in (
                _optional_text(observation.get("canonical_thread_ref")),
                _optional_text(observation.get("compatibility_thread_ref")),
                _optional_text(observation.get("current_thread_ref")),
            )
            if ref
        }
        observation["supporting_confirmed_feedback"] = sorted(
            target_refs & supporting_targets
        )
        observation["contradicting_confirmed_feedback"] = sorted(
            target_refs & contradicting_targets
        )
        result.append(observation)
    return result


def _effect_identity_matches(
    effect: Mapping[str, object],
    manifest: Mapping[str, object],
) -> bool:
    if effect.get("surface") != "weekly_brief" or effect.get("snapshot_status") != "complete":
        return False
    for field in (
        "run_id",
        "reporting_week",
        "analysis_period_start",
        "analysis_period_end",
    ):
        if effect.get(field) != manifest.get(field):
            return False
    reaction_stage = _mapping(manifest.get("stages"), "reaction_sync")
    return (
        reaction_stage is not None
        and reaction_stage.get("status") == "succeeded"
        and effect.get("snapshot_ref") == reaction_stage.get("snapshot_ref")
    )


def _reader_identity_matches(
    sidecar: Mapping[str, object],
    manifest: Mapping[str, object],
    manifest_path: Path,
    json_path: Path,
) -> bool:
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
        "run_status",
        "partial",
    ):
        if sidecar.get(field) != manifest.get(field):
            return False
    if _contained_identity_path(sidecar.get("manifest_path"), manifest_path) is False:
        return False
    if _contained_identity_path(sidecar.get("json_path"), json_path) is False:
        return False
    artifact_paths = sidecar.get("artifact_paths")
    return isinstance(artifact_paths, Mapping) and _contained_identity_path(
        artifact_paths.get("json"), json_path
    )


def _mapping(value: object, key: str) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    nested = value.get(key)
    return nested if isinstance(nested, Mapping) else None


def _read_json_object(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def _contained_run_path(run_dir: Path, value: object) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    resolved = path.resolve() if path.is_absolute() else (run_dir / path).resolve()
    try:
        resolved.relative_to(run_dir)
    except ValueError:
        return None
    return resolved if resolved.is_file() else None


def _contained_identity_path(value: object, expected: Path) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        return Path(text).expanduser().resolve() == expected.resolve()
    except OSError:
        return False


def _strict_string_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    cleaned = [str(item).strip() for item in value if isinstance(item, str) and item.strip()]
    if len(cleaned) != len(value):
        return None
    return sorted(set(cleaned))


def _optional_text(value: object) -> str | None:
    return str(value).strip() if isinstance(value, str) and value.strip() else None


def _timestamp_ns(value: object) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("generated_at must be canonical UTC")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    return int(parsed.timestamp() * 1_000_000_000)


def _filesystem_freshness_ns(path: Path) -> int:
    try:
        return max(path.stat().st_mtime_ns, path.parent.stat().st_mtime_ns)
    except OSError:
        return 0


def build_strategy_review(
    connection: sqlite3.Connection,
    *,
    week_label: str | None = None,
    before_week_label: str | None = None,
    reaction_pattern_observations: Iterable[Mapping[str, object]] | None = None,
    weekly_run_root: str | Path | None = None,
) -> dict[str, Any]:
    summary = summarize_ai_report_feedback(
        connection,
        week_label=week_label,
        before_week_label=before_week_label,
    )
    counts = summary.get("counts_by_feedback") or {}
    has_feedback = int(summary.get("event_count") or 0) > 0
    observations = (
        list(reaction_pattern_observations)
        if reaction_pattern_observations is not None
        else load_reaction_pattern_observations(weekly_run_root)
        if weekly_run_root is not None
        else []
    )
    proposal_as_of_week = week_label or _previous_iso_week_label(before_week_label)
    reaction_pattern_proposals = build_reaction_pattern_proposals(
        _attach_exact_confirmed_feedback(observations, summary),
        as_of_week_label=proposal_as_of_week,
    )

    keep: list[str] = []
    change: list[str] = []
    demote: list[str] = []
    test_next_week: list[str] = []
    approval_required: list[dict[str, str]] = []
    memory_only: list[str] = []
    tasks: list[dict[str, Any]] = []
    risks: list[str] = [
        "Strategy Reviewer is advisory; Hermes must not apply code/config/profile/project changes automatically."
    ]

    if not has_feedback:
        keep.append("Keep the feedback prompt visible; personalization state is unknown until confirmed feedback exists.")
        change.append("Ask for at least one read/try/missed/trust feedback item after the workbook.")
        test_next_week.append("Run the workbook with explicit feedback targets and inspect completion.")
        risks.append("No confirmed feedback is an unknown state, not a negative signal.")
    else:
        memory_only.append("Confirmed feedback is already stored in ai_report_feedback_events; no profile/config edit is required.")
        if counts.get("useful") or counts.get("tried") or counts.get("applied_to_project"):
            keep.append("Keep promoting try/build items that received useful, tried, or applied-to-project feedback.")
        if counts.get("too_shallow"):
            change.append("Increase source-depth checks for sections marked too_shallow.")
            approval_required.append(
                {
                    "change_type": "code_or_prompt",
                    "reason": "Depth behavior requires an approved renderer/prompt/eval change, not an automatic memory write.",
                }
            )
            risks.append("Source-depth changes can weaken evidence gates if they are applied without a regression test.")
            tasks.append(
                _task(
                    title="Add workbook source-depth regression for too_shallow feedback",
                    files=["src/output/ai_visual_report.py", "tests/test_ai_visual_report.py"],
                    acceptance_criteria=[
                        "Workbook shows deeper source/caveat requirements after too_shallow feedback.",
                        "No claim is upgraded without source URLs and caveats.",
                    ],
                    verification_commands=[
                        "PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_ai_visual_report"
                    ],
                    rationale="Operator feedback marked prior analysis too shallow.",
                )
            )
        if counts.get("wrong_priority") or counts.get("not_interested") or counts.get("noise"):
            demote.append("Demote similar threads/actions that match wrong_priority, not_interested, or noise feedback.")
            tasks.append(
                _task(
                    title="Add ranking regression for demoted workbook topics",
                    files=["src/output/ai_intelligence_report.py", "tests/test_ai_intelligence_report.py"],
                    acceptance_criteria=[
                        "wrong_priority/not_interested feedback lowers related read/try/build ranking.",
                        "Useful/tried feedback can still promote explicitly related targets.",
                    ],
                    verification_commands=[
                        "PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_ai_intelligence_report"
                    ],
                    rationale="Operator feedback found priority drift or irrelevant topics.",
                )
            )
        if counts.get("missed_important_post"):
            test_next_week.append("Turn missed important posts into eval examples and verify they appear in next workbook coverage.")
            memory_only.append("Missed-post feedback can remain memory-only until a human approves new eval/code changes.")
        if counts.get("trust_too_high") or counts.get("trust_too_low") or counts.get("verify_first"):
            change.append("Review source-trust calibration before changing trust thresholds.")
            approval_required.append(
                {
                    "change_type": "config",
                    "reason": "Trust threshold/profile changes require explicit operator approval.",
                }
            )
            risks.append("Trust calibration changes require explicit approval because they affect future ranking behavior.")

    if not tasks:
        tasks.append(
            _task(
                title="Review feedback completion after next workbook",
                files=["src/output/ai_report_feedback_intake.py", "tests/test_ai_report_feedback.py"],
                acceptance_criteria=[
                    "Feedback confirmation still writes only confirmed events.",
                    "Strategy review keeps code/config changes suggestion-only.",
                ],
                verification_commands=[
                    "PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_ai_report_feedback"
                ],
                rationale="No targeted code task is justified until more feedback exists.",
            )
        )

    return {
        "generated_at": _now_iso(),
        "week_label": week_label,
        "before_week_label": before_week_label,
        "feedback_summary": summary,
        "suggestions": {
            "keep": keep,
            "change": change,
            "demote": demote,
            "test_next_week": test_next_week,
        },
        "memory_only_updates": memory_only,
        "approval_required": approval_required,
        "codex_tasks": tasks,
        "reaction_pattern_proposals": reaction_pattern_proposals,
        "risks": risks,
        "mutation_policy": {
            "source_code": "do_not_modify",
            "prompts": "do_not_modify",
            "thresholds": "do_not_modify",
            "profile": "do_not_modify",
            "projects": "do_not_modify",
        },
    }


def write_strategy_review(review: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
