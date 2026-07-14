from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from assistant.pi_facade import PersonalIntelligenceFacade
from output.intelligence_retrieval_items import (
    DEFAULT_OUTPUT_ROOT,
    IntelligenceRetrievalItem,
    build_retrieval_items,
)
from output.knowledge_atlas_report_v2 import (
    ATLAS_V2_DIRECTORY,
    ATLAS_V2_JSON_FILENAME,
    ATLAS_V2_SURFACE,
    find_manifest_bound_knowledge_atlas_v2,
)
from output.report_v2_regression_fixtures import (
    REQUIRED_VIEWPORTS,
    load_report_v2_regression_manifest,
)
from output.weekly_intelligence_brief_v2 import (
    BRIEF_V2_DIRECTORY,
    BRIEF_V2_JSON_FILENAME,
    BRIEF_V2_SCHEMA_VERSION,
    BRIEF_V2_SURFACE,
    find_manifest_bound_weekly_intelligence_brief_v2,
)
from output.weekly_run_manifest import (
    MANIFEST_SCHEMA_VERSION,
    PIPELINE_PROFILE,
    WeeklyRunManifestError,
    load_manifest,
)


REPORT_V2_ROLLOUT_RECEIPT_VERSION = "report_v2_rollout_receipt.v1"
REPORT_V2_OPERATOR_COMMAND = "weekly-intelligence-v2"
REPORT_V2_START_GATE_COMMAND = "report-v2-rollout-gate"
PUBLISHED_ROLLOUT_CONTRACTS = {
    "intelligence_contract": "tra-intelligence-contract.v2",
    "split_report": BRIEF_V2_SCHEMA_VERSION,
    "weekly_brief_surface": BRIEF_V2_SURFACE,
    "knowledge_atlas_surface": ATLAS_V2_SURFACE,
    "editorial": "editorial_intelligence.v1",
    "weekly_run_manifest": MANIFEST_SCHEMA_VERSION,
    "pipeline_profile": PIPELINE_PROFILE,
}
V1_COMPATIBILITY_ALIASES = {
    "weekly_brief": "weekly_intelligence_briefs/<week>.json",
    "knowledge_atlas": "knowledge_atlas/<week>.json",
    "workbook": "ai_intelligence/<week>.json",
}
V2_OUTPUT_PATHS = {
    "manifest": "weekly_intelligence_runs/<run_id>/manifest.json",
    "run_weekly_brief": "weekly_intelligence_runs/<run_id>/weekly_brief/<week>.weekly-brief.json",
    "run_knowledge_atlas": "weekly_intelligence_runs/<run_id>/knowledge_atlas/<week>.knowledge-atlas.json",
    "brief_v2": f"{BRIEF_V2_DIRECTORY}/<run_id>/{BRIEF_V2_JSON_FILENAME}",
    "atlas_v2": f"{ATLAS_V2_DIRECTORY}/<run_id>/{ATLAS_V2_JSON_FILENAME}",
}
@dataclass(frozen=True)
class RolloutGate:
    name: str
    status: str
    summary: str
    evidence: dict[str, Any]
    blocks_dogfood: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_report_v2_rollout_receipt(
    settings: Any,
    *,
    week_label: str | None = None,
    output_root: str | Path | None = None,
    weekly_run_root: str | Path | None = None,
    vault_path: str | Path | None = None,
    namespace: str | None = None,
    generated_at: datetime | None = None,
    max_weekly_cost_usd: float = 5.0,
) -> dict[str, Any]:
    """Build a read-only IRX-14 migration/start-gate receipt.

    The receipt never starts dogfood and never mutates delivery configuration.
    It only states whether the current evidence is sufficient to do so.
    """

    output_base = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    run_root = (
        Path(weekly_run_root)
        if weekly_run_root is not None
        else output_base / "weekly_intelligence_runs"
    )
    facade = PersonalIntelligenceFacade(
        settings=settings,
        output_root=output_base,
        weekly_run_root=run_root,
        v2_source_roots=(output_base,),
        now=generated_at,
    )
    requested_week = str(week_label or "").strip() or None
    artifact_status = facade.get_artifact_status(requested_week)
    clean_week = str(artifact_status.get("week_label") or requested_week or "")
    manifest_path = _select_manifest_path(clean_week, run_root)
    manifest = _load_manifest_for_gate(manifest_path) if manifest_path else None
    run_id = str((manifest or {}).get("run_id") or artifact_status.get("run_id") or "")
    brief_v2 = _find_brief_v2(output_base, run_id, manifest_path)
    atlas_v2 = _find_atlas_v2(output_base, run_id, manifest_path)
    retrieval_items = build_retrieval_items(
        settings,
        clean_week or None,
        output_root=output_base,
        weekly_run_root=run_root,
        v2_source_roots=(output_base,),
    )
    feedback_summary = facade.get_feedback_summary(clean_week or None)
    fixture_manifest = load_report_v2_regression_manifest()
    cost_summary = _load_cost_summary(
        getattr(settings, "db_path", None),
        generated_at=generated_at,
        max_weekly_cost_usd=max_weekly_cost_usd,
    )

    return build_report_v2_rollout_receipt_from_evidence(
        week_label=clean_week,
        artifact_status=artifact_status,
        manifest=manifest,
        manifest_path=manifest_path,
        retrieval_items=retrieval_items,
        brief_v2=brief_v2,
        atlas_v2=atlas_v2,
        feedback_summary=feedback_summary,
        cost_summary=cost_summary,
        fixture_manifest=fixture_manifest,
        output_root=output_base,
        vault_path=vault_path,
        namespace=namespace,
        generated_at=generated_at,
    )


def build_report_v2_rollout_receipt_from_evidence(
    *,
    week_label: str,
    artifact_status: Mapping[str, Any],
    manifest: Mapping[str, Any] | None,
    manifest_path: str | Path | None,
    retrieval_items: Iterable[IntelligenceRetrievalItem | Mapping[str, Any]],
    brief_v2: Mapping[str, Any] | None,
    atlas_v2: Mapping[str, Any] | None,
    feedback_summary: Mapping[str, Any] | None,
    cost_summary: Mapping[str, Any] | None,
    fixture_manifest: Mapping[str, Any] | None,
    output_root: str | Path | None = None,
    vault_path: str | Path | None = None,
    namespace: str | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    normalized_items = tuple(retrieval_items)
    gates = [
        _period_gate(artifact_status, manifest),
        _v1_compatibility_gate(artifact_status),
        _v2_paths_gate(manifest, manifest_path, brief_v2, atlas_v2, output_root),
        _retrieval_pi_gate(normalized_items),
        _obsidian_gate(atlas_v2, vault_path=vault_path, namespace=namespace),
        _radar_gate(artifact_status),
        _reaction_gate(manifest, normalized_items),
        _editorial_gate(manifest),
        _project_gate(normalized_items, brief_v2),
        _visual_gate(brief_v2, atlas_v2, fixture_manifest),
        _cost_gate(cost_summary),
        _quality_gate(brief_v2, atlas_v2),
        _feedback_gate(feedback_summary, normalized_items),
        _fixture_gate(fixture_manifest),
    ]
    blocking = [
        gate
        for gate in gates
        if gate.blocks_dogfood and gate.status != "passed"
    ]
    dogfood_status = "eligible" if not blocking else "blocked"
    manifest_run_id = str((manifest or {}).get("run_id") or artifact_status.get("run_id") or "")
    return {
        "schema_version": REPORT_V2_ROLLOUT_RECEIPT_VERSION,
        "generated_at": generated.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "week_label": str(week_label or artifact_status.get("week_label") or ""),
        "run_id": manifest_run_id,
        "manifest_path": str(manifest_path or artifact_status.get("manifest_path") or ""),
        "operator_commands": {
            "v1_compatibility_command": "ai-split-report",
            "v2_candidate_command": REPORT_V2_OPERATOR_COMMAND,
            "start_gate_command": REPORT_V2_START_GATE_COMMAND,
        },
        "published_contracts": dict(PUBLISHED_ROLLOUT_CONTRACTS),
        "v1_compatibility_aliases": dict(V1_COMPATIBILITY_ALIASES),
        "v2_output_paths": dict(V2_OUTPUT_PATHS),
        "migration_status": "ready_for_dogfood_start" if dogfood_status == "eligible" else "blocked_before_dogfood",
        "dogfood_start_status": dogfood_status,
        "dogfood_week_1": {
            "status": "not_started",
            "evidence_policy": "real_current_operator_run_required",
            "blocked_evidence": [gate.summary for gate in blocking],
        },
        "dogfood_policy": {
            "feature_freeze_after_start": "only blockers and friction fixes",
            "no_fabricated_evidence": True,
            "generated_private_artifacts_committed": False,
        },
        "gates": [gate.to_dict() for gate in gates],
        "blocking_gates": [gate.name for gate in blocking],
        "summary": (
            "Report V2 dogfood start gate passed; dogfood still requires a real operator start action."
            if dogfood_status == "eligible"
            else "Report V2 dogfood start is blocked until all gate evidence is current and real."
        ),
    }


def write_report_v2_rollout_receipt(receipt: Mapping[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(dict(receipt), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def format_report_v2_rollout_receipt(receipt: Mapping[str, Any]) -> str:
    lines = [
        f"schema={receipt.get('schema_version')}",
        f"week={receipt.get('week_label')} run_id={receipt.get('run_id') or 'none'}",
        f"dogfood_start_status={receipt.get('dogfood_start_status')}",
        f"operator_command={receipt.get('operator_commands', {}).get('v2_candidate_command')}",
        f"start_gate_command={receipt.get('operator_commands', {}).get('start_gate_command')}",
    ]
    for gate in receipt.get("gates") or []:
        if not isinstance(gate, Mapping):
            continue
        marker = "BLOCK" if gate.get("status") != "passed" and gate.get("blocks_dogfood") else "OK"
        lines.append(f"{marker} {gate.get('name')}: {gate.get('status')} — {gate.get('summary')}")
    blocked = receipt.get("dogfood_week_1", {}).get("blocked_evidence") if isinstance(receipt.get("dogfood_week_1"), Mapping) else []
    if blocked:
        lines.append("blocked_evidence:")
        lines.extend(f"- {item}" for item in blocked)
    return "\n".join(lines) + "\n"


def _period_gate(artifact_status: Mapping[str, Any], manifest: Mapping[str, Any] | None) -> RolloutGate:
    run_status = str((manifest or {}).get("run_status") or artifact_status.get("run_status") or artifact_status.get("status") or "")
    period_mode = str((manifest or {}).get("period_mode") or "")
    passed = artifact_status.get("status") == "ok" and run_status == "complete" and period_mode != "partial_iso_week"
    return RolloutGate(
        "period",
        "passed" if passed else "blocked",
        "completed manifest-bound week is current" if passed else "missing, partial, or non-current weekly run",
        {
            "artifact_status": artifact_status.get("status"),
            "run_status": run_status,
            "period_mode": period_mode,
            "week_label": artifact_status.get("week_label"),
        },
    )


def _v1_compatibility_gate(artifact_status: Mapping[str, Any]) -> RolloutGate:
    brief = _mapping(artifact_status.get("weekly_brief"))
    atlas = _mapping(artifact_status.get("knowledge_atlas"))
    passed = brief.get("status") == "current" and atlas.get("status") == "current"
    return RolloutGate(
        "v1_compatibility",
        "passed" if passed else "blocked",
        "V1 Brief and Atlas remain inspectable" if passed else "V1 Brief/Atlas compatibility artifacts are not current",
        {
            "weekly_brief": brief.get("status"),
            "knowledge_atlas": atlas.get("status"),
            "weekly_brief_json": brief.get("json_path"),
            "knowledge_atlas_json": atlas.get("json_path"),
        },
    )


def _v2_paths_gate(
    manifest: Mapping[str, Any] | None,
    manifest_path: str | Path | None,
    brief_v2: Mapping[str, Any] | None,
    atlas_v2: Mapping[str, Any] | None,
    output_root: str | Path | None,
) -> RolloutGate:
    run_id = str((manifest or {}).get("run_id") or "")
    base = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    expected = {
        "brief_v2": str(base / BRIEF_V2_DIRECTORY / run_id / BRIEF_V2_JSON_FILENAME) if run_id else "",
        "atlas_v2": str(base / ATLAS_V2_DIRECTORY / run_id / ATLAS_V2_JSON_FILENAME) if run_id else "",
    }
    passed = bool(manifest_path and brief_v2 and atlas_v2)
    return RolloutGate(
        "v2_paths",
        "passed" if passed else "blocked",
        "manifest-bound Brief V2 and Atlas V2 package paths are explicit" if passed else "Brief V2 or Atlas V2 package is missing",
        {
            "manifest_path": str(manifest_path or ""),
            "run_id": run_id,
            "expected": expected,
            "brief_v2_loaded": bool(brief_v2),
            "atlas_v2_loaded": bool(atlas_v2),
        },
    )


def _retrieval_pi_gate(items: Iterable[IntelligenceRetrievalItem | Mapping[str, Any]]) -> RolloutGate:
    surfaces = {
        str(_item_value(item, "surface") or "")
        for item in items
        if str(_item_value(item, "schema_version") or "") == BRIEF_V2_SCHEMA_VERSION
    }
    has_brief = BRIEF_V2_SURFACE in surfaces
    has_atlas = ATLAS_V2_SURFACE in surfaces
    passed = has_brief and has_atlas
    return RolloutGate(
        "retrieval_pi",
        "passed" if passed else "blocked",
        "retrieval/PI exposes both V2 reader surfaces" if passed else "retrieval/PI V2 descriptors are incomplete",
        {"surfaces": sorted(surface for surface in surfaces if surface)},
    )


def _obsidian_gate(
    atlas_v2: Mapping[str, Any] | None,
    *,
    vault_path: str | Path | None,
    namespace: str | None,
) -> RolloutGate:
    passed = atlas_v2 is not None
    return RolloutGate(
        "obsidian",
        "passed" if passed else "blocked",
        "Atlas V2 Obsidian adapter has a manifest-bound source" if passed else "Obsidian V2 adapter source package is missing",
        {
            "adapter": "export_knowledge_atlas_v2_obsidian_projection",
            "vault_path": str(vault_path or ""),
            "namespace": str(namespace or ""),
            "atlas_v2_loaded": bool(atlas_v2),
        },
    )


def _radar_gate(artifact_status: Mapping[str, Any]) -> RolloutGate:
    radar = _mapping(artifact_status.get("mvp_radar"))
    gate = _mapping(artifact_status.get("mvp_radar_gate"))
    radar_status = str(radar.get("status") or gate.get("radar_artifact_status") or "")
    decision = str(gate.get("decision") or "")
    context_only = gate.get("context_only_can_satisfy_gate")
    passed = radar_status not in {"", "missing", "failed", "disabled", "invalid", "pending"} and context_only is False
    return RolloutGate(
        "radar",
        "passed" if passed else "blocked",
        "Radar reader is available and context-only evidence cannot satisfy gates" if passed else "Radar is missing, disabled, invalid, or context-only unsafe",
        {
            "radar_status": radar_status,
            "decision": decision,
            "context_only_can_satisfy_gate": context_only,
        },
    )


def _reaction_gate(
    manifest: Mapping[str, Any] | None,
    items: Iterable[IntelligenceRetrievalItem | Mapping[str, Any]],
) -> RolloutGate:
    stage_status = _stage_status(manifest, "reaction_sync")
    has_retrieval_receipt = any(_item_value(item, "item_type") == "reaction_effect" for item in items)
    passed = stage_status == "succeeded" and has_retrieval_receipt
    return RolloutGate(
        "reaction",
        "passed" if passed else "blocked",
        "reaction snapshot/effect is bound and retrievable" if passed else "reaction snapshot/effect evidence is incomplete",
        {"stage_status": stage_status, "retrieval_receipt": has_retrieval_receipt},
    )


def _editorial_gate(manifest: Mapping[str, Any] | None) -> RolloutGate:
    stage_status = _stage_status(manifest, "editorial_intelligence")
    passed = stage_status == "succeeded"
    return RolloutGate(
        "editorial",
        "passed" if passed else "blocked",
        "editorial intelligence stage succeeded" if passed else "editorial intelligence stage has not succeeded",
        {"stage_status": stage_status},
    )


def _project_gate(
    items: Iterable[IntelligenceRetrievalItem | Mapping[str, Any]],
    brief_v2: Mapping[str, Any] | None,
) -> RolloutGate:
    has_project_item = any(
        str(_item_value(item, "item_type") or "") in {"project_action", "project_intelligence", "project_diagnostic"}
        for item in items
    )
    project_actions = _mapping_list((brief_v2 or {}).get("project_actions"))
    passed = has_project_item or bool(project_actions)
    return RolloutGate(
        "project",
        "passed" if passed else "blocked",
        "project implication surface is present or explicitly represented" if passed else "project implication evidence is absent",
        {"retrieval_project_item": has_project_item, "brief_v2_project_actions": len(project_actions)},
    )


def _visual_gate(
    brief_v2: Mapping[str, Any] | None,
    atlas_v2: Mapping[str, Any] | None,
    fixture_manifest: Mapping[str, Any] | None,
) -> RolloutGate:
    brief_visuals = _mapping_list((brief_v2 or {}).get("visual_specs"))
    atlas_visuals = _mapping_list((atlas_v2 or {}).get("visual_specs"))
    visual = _mapping((fixture_manifest or {}).get("visual_regression"))
    approved = _mapping(visual.get("approved_snapshot_hashes"))
    baseline_recorded = visual.get("baseline_status") == "recorded"
    hashes_ready = REQUIRED_VIEWPORTS.issubset(set(approved))
    passed = bool(brief_visuals and atlas_visuals and baseline_recorded and hashes_ready)
    return RolloutGate(
        "visual",
        "passed" if passed else "blocked",
        "semantic visuals and approved desktop/mobile snapshots are available" if passed else "visual semantics or reviewed desktop/mobile snapshots are incomplete",
        {
            "brief_visual_count": len(brief_visuals),
            "atlas_visual_count": len(atlas_visuals),
            "baseline_status": visual.get("baseline_status"),
            "approved_viewports": sorted(approved),
        },
    )


def _cost_gate(cost_summary: Mapping[str, Any] | None) -> RolloutGate:
    summary = dict(cost_summary or {})
    passed = summary.get("status") == "passed"
    return RolloutGate(
        "cost",
        "passed" if passed else "blocked",
        "recent LLM cost is measured and within rollout budget" if passed else "cost/latency receipt is missing or over budget",
        summary,
    )


def _quality_gate(
    brief_v2: Mapping[str, Any] | None,
    atlas_v2: Mapping[str, Any] | None,
) -> RolloutGate:
    brief_partial = bool((brief_v2 or {}).get("partial"))
    atlas_partial = bool((atlas_v2 or {}).get("partial"))
    brief_status = str((brief_v2 or {}).get("run_status") or "")
    atlas_status = str((atlas_v2 or {}).get("run_status") or "")
    passed = brief_v2 is not None and atlas_v2 is not None and not brief_partial and not atlas_partial and brief_status == "complete" and atlas_status == "complete"
    return RolloutGate(
        "quality",
        "passed" if passed else "blocked",
        "Brief V2 and Atlas V2 are complete quality-gated packages" if passed else "Brief V2 or Atlas V2 quality-gated package is missing or partial",
        {
            "brief_run_status": brief_status,
            "brief_partial": brief_partial,
            "atlas_run_status": atlas_status,
            "atlas_partial": atlas_partial,
        },
    )


def _feedback_gate(
    feedback_summary: Mapping[str, Any] | None,
    items: Iterable[IntelligenceRetrievalItem | Mapping[str, Any]],
) -> RolloutGate:
    status = str((feedback_summary or {}).get("status") or "")
    has_receipt_item = any(_item_value(item, "item_type") == "confirmed_feedback_effect" for item in items)
    recent_events = _mapping_list((feedback_summary or {}).get("recent_events"))
    passed = status not in {"", "missing"} and (has_receipt_item or not recent_events)
    return RolloutGate(
        "feedback_readiness",
        "passed" if passed else "blocked",
        "feedback table and report feedback receipt are readable" if passed else "feedback readiness or application receipt is incomplete",
        {
            "feedback_summary_status": status,
            "confirmed_feedback_retrieval_item": has_receipt_item,
            "recent_event_count": len(recent_events),
        },
    )


def _fixture_gate(fixture_manifest: Mapping[str, Any] | None) -> RolloutGate:
    scenarios = _mapping_list((fixture_manifest or {}).get("scenarios"))
    visual = _mapping((fixture_manifest or {}).get("visual_regression"))
    passed = bool(scenarios) and visual.get("baseline_status") in {"recorded", "prerequisite_required"}
    return RolloutGate(
        "fixtures",
        "passed" if passed else "blocked",
        "IRX-13 release-candidate fixture registry is loadable" if passed else "IRX-13 fixture registry is missing or invalid",
        {"scenario_count": len(scenarios), "visual_baseline_status": visual.get("baseline_status")},
    )


def _select_manifest_path(week_label: str, weekly_run_root: str | Path) -> Path | None:
    clean_week = str(week_label or "").strip()
    root = Path(weekly_run_root)
    if not clean_week or not root.exists() or not root.is_dir() or root.is_symlink():
        return None
    candidates: list[tuple[str, str, Path]] = []
    for path in sorted(root.glob("*/manifest.json")):
        if path.is_symlink():
            continue
        try:
            manifest = load_manifest(
                path,
                path_base=path.parent,
                allowed_roots=(path.parent,),
                check_artifact_existence=False,
            )
        except (OSError, ValueError, WeeklyRunManifestError):
            continue
        if manifest.get("reporting_week") != clean_week:
            continue
        candidates.append((str(manifest.get("generated_at") or ""), str(manifest.get("run_id") or ""), path))
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1][2]


def _load_manifest_for_gate(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        return load_manifest(
            path,
            path_base=path.parent,
            allowed_roots=(path.parent,),
            check_artifact_existence=False,
        )
    except (OSError, ValueError, WeeklyRunManifestError):
        return None


def _find_brief_v2(
    output_root: Path,
    run_id: str,
    manifest_path: Path | None,
) -> dict[str, Any] | None:
    if not run_id or manifest_path is None:
        return None
    try:
        value = find_manifest_bound_weekly_intelligence_brief_v2(
            output_root=output_root.resolve(),
            run_id=run_id,
            expected_manifest_path=manifest_path,
            allowed_source_roots=(output_root.resolve(), manifest_path.parent),
        )
        return dict(value) if isinstance(value, Mapping) else None
    except Exception:
        return None


def _find_atlas_v2(
    output_root: Path,
    run_id: str,
    manifest_path: Path | None,
) -> dict[str, Any] | None:
    if not run_id or manifest_path is None:
        return None
    try:
        value = find_manifest_bound_knowledge_atlas_v2(
            output_root=output_root.resolve(),
            run_id=run_id,
            expected_manifest_path=manifest_path,
            allowed_source_roots=(output_root.resolve(), manifest_path.parent),
        )
        return dict(value) if isinstance(value, Mapping) else None
    except Exception:
        return None


def _load_cost_summary(
    db_path: str | Path | None,
    *,
    generated_at: datetime | None,
    max_weekly_cost_usd: float,
) -> dict[str, Any]:
    if not db_path:
        return {"status": "blocked", "reason": "db_path_missing", "max_weekly_cost_usd": max_weekly_cost_usd}
    cutoff = (generated_at or datetime.now(timezone.utc)) - timedelta(days=7)
    try:
        with sqlite3.connect(str(db_path)) as connection:
            row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='llm_usage'"
            ).fetchone()
            if row is None:
                return {
                    "status": "blocked",
                    "reason": "llm_usage_table_missing",
                    "max_weekly_cost_usd": max_weekly_cost_usd,
                }
            total = connection.execute(
                """
                SELECT
                    COUNT(*) AS call_count,
                    COALESCE(SUM(cost_usd), 0.0) AS total_cost_usd,
                    COALESCE(SUM(est_cost_usd), 0.0) AS total_est_cost_usd
                FROM llm_usage
                WHERE called_at >= ?
                """,
                (cutoff.replace(microsecond=0).isoformat().replace("+00:00", "Z"),),
            ).fetchone()
    except sqlite3.Error as exc:
        return {"status": "blocked", "reason": f"llm_usage_query_failed:{exc}", "max_weekly_cost_usd": max_weekly_cost_usd}
    cost = float((total or [0, 0.0, 0.0])[1] or 0.0)
    est_cost = float((total or [0, 0.0, 0.0])[2] or 0.0)
    call_count = int((total or [0, 0.0, 0.0])[0] or 0)
    if call_count <= 0:
        return {
            "status": "blocked",
            "reason": "no_recent_llm_usage_receipt",
            "call_count": 0,
            "total_cost_usd": 0.0,
            "total_est_cost_usd": 0.0,
            "max_weekly_cost_usd": max_weekly_cost_usd,
        }
    measured = max(cost, est_cost)
    return {
        "status": "passed" if measured <= max_weekly_cost_usd else "blocked",
        "reason": "within_budget" if measured <= max_weekly_cost_usd else "over_budget",
        "call_count": call_count,
        "total_cost_usd": cost,
        "total_est_cost_usd": est_cost,
        "max_weekly_cost_usd": max_weekly_cost_usd,
    }


def _stage_status(manifest: Mapping[str, Any] | None, stage: str) -> str:
    stages = _mapping((manifest or {}).get("stages"))
    return str(_mapping(stages.get(stage)).get("status") or "")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _item_value(item: IntelligenceRetrievalItem | Mapping[str, Any], field: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(field)
    return getattr(item, field, None)
