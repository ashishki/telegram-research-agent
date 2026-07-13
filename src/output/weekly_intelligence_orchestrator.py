"""IRX-2 run-scoped orchestration for one weekly intelligence package.

The legacy report and Radar commands remain available.  This module is the
explicit additive path which resolves one :class:`ReportingPeriod`, creates one
immutable run identity, and binds every successful output through the manifest.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from config.settings import PROJECT_ROOT, Settings
from db.frontier_analysis import fetch_frontier_analysis
from output.ai_intelligence_report import load_ai_intelligence_context
from output.ai_report_contract import RADAR_INTELLIGENCE_CONTRACT_VERSION
from output.frontier_analysis import frontier_analysis_fingerprint, run_frontier_analysis
from output.idea_threads import refresh_idea_threads
from output.knowledge_atlas_report import build_knowledge_atlas_artifact
from output.mvp_weekly_pipeline import MvpWeeklyPipelineResult, run_mvp_weekly_pipeline
from output.reporting_period import ReportingPeriod, resolve_reporting_period
from output.reporting_period import register_reporting_period_sqlite
from output.weekly_intelligence_brief import (
    RADAR_DISABLED_DISCLOSURE_RU,
    build_weekly_intelligence_brief_artifact,
    load_mvp_radar_summary,
)
from output.weekly_run_manifest import (
    CANCELLED,
    FAILED,
    PIPELINE_PROFILE,
    SKIPPED_DEPENDENCY,
    SUCCEEDED,
    append_warning,
    build_radar_run_binding,
    create_manifest,
    fail_stage,
    finalize_manifest,
    load_manifest,
    sha256_file,
    start_stage,
    succeed_stage,
    transition_stage,
    write_manifest,
    write_radar_run_binding,
)


DEFAULT_WEEKLY_RUN_ROOT = PROJECT_ROOT / "data" / "output" / "weekly_intelligence_runs"
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class WeeklyIntelligenceRunResult:
    run_id: str
    manifest_path: str
    run_status: str
    partial: bool
    reporting_week: str
    analysis_period_start: str
    analysis_period_end: str
    weekly_brief_html_path: str | None
    weekly_brief_json_path: str | None
    atlas_html_path: str | None
    atlas_json_path: str | None
    radar_json_path: str | None
    warnings: tuple[str, ...]
    delivered_message_ids: tuple[int | None, ...] = ()


@dataclass(frozen=True)
class _RadarStageResult:
    manifest_updates: dict[str, Any]
    brief_json_path: Path


def run_weekly_intelligence_v2(
    settings: Settings,
    *,
    reporting_period: ReportingPeriod | None = None,
    week_label: str | None = None,
    period_mode: str | None = None,
    now: datetime | None = None,
    run_id: str | None = None,
    supersedes_run_id: str | None = None,
    output_root: str | Path | None = None,
    radar_enabled: bool = True,
    refresh_weeks: int = 12,
    refresh_limit: int | None = None,
    reaction_limit: int = 300,
    frontier_lookback_weeks: int = 12,
    frontier_model: str = "strong",
    threads_limit: int = 24,
    atoms_limit: int = 8,
    force_frontier: bool = False,
    radar_limit: int = 80,
    include_channels: tuple[str, ...] = (),
    market_context_days: int = 84,
    force_market_baseline: bool = False,
    with_live_source_index: bool = False,
    live_intelligence_path: str | Path | None = None,
    deliver: bool = False,
    chat_id: str | None = None,
    token: str | None = None,
) -> WeeklyIntelligenceRunResult:
    """Run the IRX-2 profile and return the finalized manifest projection.

    Stage failures are represented in the returned terminal manifest.  Only a
    failure to create or persist the manifest itself escapes to the caller.
    """

    period = _resolve_period(
        reporting_period=reporting_period,
        week_label=week_label,
        period_mode=period_mode,
        now=now,
    )
    runs_root = Path(output_root) if output_root is not None else DEFAULT_WEEKLY_RUN_ROOT
    manifest_path, manifest = create_manifest(
        runs_root,
        period,
        run_id=run_id,
        radar_enabled=radar_enabled,
        supersedes_run_id=supersedes_run_id,
        created_by={"command": "weekly-intelligence-v2", "host": "redacted"},
    )
    run_dir = manifest_path.parent
    allowed_roots = (run_dir,)

    def persist(candidate: Mapping[str, Any], *, check_outputs: bool = True) -> dict[str, Any]:
        value = dict(candidate)
        write_manifest(
            manifest_path,
            value,
            path_base=run_dir,
            allowed_roots=allowed_roots,
            check_artifact_existence=check_outputs,
        )
        return value

    reaction_snapshot_at: str = manifest["generated_at"]
    radar_brief_path: Path | None = None

    # Knowledge refresh is foundational.  A failure stops downstream work and
    # produces a failed manifest rather than a stale reader artifact.
    manifest = persist(start_stage(manifest, "knowledge_refresh"))
    try:
        knowledge = refresh_idea_threads(
            settings,
            weeks=max(1, int(refresh_weeks or 1)),
            limit=refresh_limit if refresh_limit and refresh_limit > 0 else None,
            now=period.analysis_period_end,
            analysis_period_end=period.analysis_period_end,
        )
        manifest = persist(
            succeed_stage(
                manifest,
                "knowledge_refresh",
                updates={
                    "record_counts": {
                        "atoms": knowledge.atoms_seen,
                        "threads": knowledge.threads_refreshed,
                        "links": knowledge.links_refreshed,
                    }
                },
            )
        )
    except Exception as exc:
        manifest = persist(fail_stage(manifest, "knowledge_refresh", exc), check_outputs=False)
        manifest = _skip_pending_stages(manifest, "knowledge_refresh failed")
        manifest = persist(manifest, check_outputs=False)
        manifest = persist(finalize_manifest(manifest), check_outputs=False)
        return _result_from_manifest(manifest_path, manifest)

    manifest = persist(start_stage(manifest, "reaction_sync"))
    try:
        reaction_summary = _sync_reactions(settings, period, max(1, int(reaction_limit or 1)))
        reaction_counts = _integer_counts(reaction_summary)
        if reaction_counts.get("errors", 0):
            raise RuntimeError(
                f"reaction sync completed with {reaction_counts['errors']} error(s)"
            )
        observed = _utc_now_iso()
        reaction_snapshot_at = observed
        manifest = persist(
            succeed_stage(
                manifest,
                "reaction_sync",
                updates={
                    "snapshot_ref": f"reaction-snapshot:{manifest['run_id']}",
                    "observed_through": observed,
                    "record_counts": reaction_counts,
                },
            )
        )
    except Exception as exc:
        counts = _integer_counts(locals().get("reaction_summary", {}))
        manifest = persist(
            fail_stage(
                manifest,
                "reaction_sync",
                exc,
                updates={
                    "snapshot_ref": f"reaction-snapshot:{manifest['run_id']}:pre-run",
                    "observed_through": manifest["generated_at"],
                    "record_counts": counts,
                },
            ),
            check_outputs=False,
        )
        manifest = persist(
            append_warning(
                manifest,
                "Reaction sync failed; reader context is limited to the pre-run reaction cutoff.",
            ),
            check_outputs=False,
        )

    manifest = persist(start_stage(manifest, "feedback_snapshot"))
    try:
        feedback = _feedback_snapshot(settings, period, manifest["run_id"])
        manifest = persist(
            succeed_stage(manifest, "feedback_snapshot", updates=feedback)
        )
    except Exception as exc:
        manifest = persist(
            fail_stage(manifest, "feedback_snapshot", exc),
            check_outputs=False,
        )
        manifest = persist(
            append_warning(manifest, "Feedback snapshot failed; personalization context may be incomplete."),
            check_outputs=False,
        )

    manifest = persist(start_stage(manifest, "frontier_analysis"))
    try:
        frontier_updates = _frontier_stage(
            settings,
            period,
            run_dir,
            manifest_path,
            manifest["run_id"],
            lookback_weeks=max(1, int(frontier_lookback_weeks or 1)),
            model=frontier_model,
            threads_limit=max(1, int(threads_limit or 1)),
            atoms_limit=max(1, int(atoms_limit or 1)),
            force=force_frontier,
        )
        manifest = persist(
            succeed_stage(manifest, "frontier_analysis", updates=frontier_updates)
        )
    except Exception as exc:
        manifest = persist(
            fail_stage(manifest, "frontier_analysis", exc),
            check_outputs=False,
        )
        manifest = persist(
            append_warning(manifest, "Exact-period Frontier Analysis is unavailable for this run."),
            check_outputs=False,
        )

    if radar_enabled:
        manifest = persist(start_stage(manifest, "radar"))
        try:
            radar = _radar_stage(
                settings,
                period,
                manifest,
                run_dir,
                manifest_path,
                limit=max(1, int(radar_limit or 1)),
                include_channels=include_channels,
                market_context_days=max(1, int(market_context_days or 1)),
                force_market_baseline=force_market_baseline,
                with_live_source_index=with_live_source_index,
                live_intelligence_path=live_intelligence_path,
            )
            radar_brief_path = radar.brief_json_path
            manifest = persist(
                succeed_stage(manifest, "radar", updates=radar.manifest_updates)
            )
        except Exception as exc:
            manifest = persist(fail_stage(manifest, "radar", exc), check_outputs=False)
            manifest = persist(
                append_warning(
                    manifest,
                    "Required MVP Radar failed or did not match this run and reporting period.",
                ),
                check_outputs=False,
            )

    try:
        manifest = _render_reader_stages(
            settings=settings,
            period=period,
            manifest_path=manifest_path,
            manifest=manifest,
            persist=persist,
            run_dir=run_dir,
            reaction_snapshot_at=reaction_snapshot_at,
            radar_brief_path=radar_brief_path,
            radar_enabled=radar_enabled,
            threads_limit=max(1, int(threads_limit or 1)),
            atoms_limit=max(1, int(atoms_limit or 1)),
        )
        manifest = persist(finalize_manifest(manifest))
    except Exception as exc:
        current = load_manifest(
            manifest_path,
            path_base=run_dir,
            allowed_roots=allowed_roots,
        )
        if current["run_status"] != "running":
            raise
        _remove_unbound_reader_artifacts(
            current,
            run_dir=run_dir,
            reporting_week=period.reporting_week,
        )
        if current["stages"]["weekly_brief"]["status"] == "pending":
            current = persist(
                start_stage(current, "weekly_brief"),
                check_outputs=False,
            )
        manifest = _recover_reader_failure(current, exc)
        manifest = persist(manifest, check_outputs=False)
        manifest = persist(finalize_manifest(manifest))

    delivered: tuple[int | None, ...] = ()
    if deliver and manifest["run_status"] in {"complete", "partial"}:
        try:
            delivered = _deliver_from_manifest(
                manifest_path,
                manifest,
                chat_id=chat_id,
                token=token,
            )
        except Exception:
            LOGGER.exception(
                "Finalized weekly run delivery failed run_id=%s",
                manifest["run_id"],
            )
    return _result_from_manifest(manifest_path, manifest, delivered=delivered)


def _resolve_period(
    *,
    reporting_period: ReportingPeriod | None,
    week_label: str | None,
    period_mode: str | None,
    now: datetime | None,
) -> ReportingPeriod:
    if reporting_period is not None:
        if week_label is not None or period_mode is not None or now is not None:
            raise ValueError(
                "reporting_period cannot be combined with week_label, period_mode, or now"
            )
        return reporting_period
    return resolve_reporting_period(now=now, week_label=week_label, period_mode=period_mode)


def _sync_reactions(
    settings: Settings,
    period: ReportingPeriod,
    limit: int,
) -> dict[str, int]:
    from ingestion.reaction_sync import sync_reactions

    return asyncio.run(
        sync_reactions(settings, reporting_period=period, limit=limit)
    )


def _feedback_snapshot(
    settings: Settings,
    period: ReportingPeriod,
    run_id: str,
) -> dict[str, Any]:
    cutoff = period.to_dict()["analysis_period_end"]
    confirmed = 0
    pending = 0
    with sqlite3.connect(settings.db_path) as connection:
        register_reporting_period_sqlite(connection)
        if _table_exists(connection, "ai_report_feedback_events"):
            confirmed = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM ai_report_feedback_events
                    WHERE week_label < ?
                      AND reporting_utc_micros(created_at) < reporting_utc_micros(?)
                    """,
                    (period.reporting_week, cutoff),
                ).fetchone()[0]
            )
        if _table_exists(connection, "ai_report_feedback_intakes"):
            pending = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM ai_report_feedback_intakes
                    WHERE status = 'pending'
                      AND week_label < ?
                      AND reporting_utc_micros(created_at) < reporting_utc_micros(?)
                    """,
                    (period.reporting_week, cutoff),
                ).fetchone()[0]
            )
    return {
        "snapshot_id": f"feedback-snapshot:{run_id}",
        "cutoff": cutoff,
        "confirmed_event_count": confirmed,
        "pending_event_count": pending,
        "record_counts": {"confirmed_events": confirmed, "pending_intakes": pending},
    }


def _frontier_stage(
    settings: Settings,
    period: ReportingPeriod,
    run_dir: Path,
    manifest_path: Path,
    run_id: str,
    *,
    lookback_weeks: int,
    model: str,
    threads_limit: int,
    atoms_limit: int,
    force: bool,
) -> dict[str, Any]:
    summary = run_frontier_analysis(
        settings,
        reporting_period=period,
        feedback_snapshot_at=period.analysis_period_end,
        lookback_weeks=lookback_weeks,
        model=model,
        threads_limit=threads_limit,
        atoms_limit=atoms_limit,
        force=force,
    )
    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = fetch_frontier_analysis(connection, week_label=period.reporting_week)
    if not row or int(row.get("id") or 0) < 1:
        raise RuntimeError("exact-period Frontier Analysis could not be read back")
    if not summary.analysis_sha256 or frontier_analysis_fingerprint(row) != summary.analysis_sha256:
        raise RuntimeError(
            "Frontier Analysis changed before this run could bind its immutable snapshot"
        )
    source_context = (row.get("analysis") or {}).get("source_context") or {}
    for field in (
        "reporting_week",
        "period_mode",
        "analysis_period_start",
        "analysis_period_end",
    ):
        if str(source_context.get(field) or "") != period.to_dict()[field]:
            raise RuntimeError(f"Frontier Analysis period mismatch: {field}")
    if str(source_context.get("feedback_snapshot_at") or "") != period.to_dict()[
        "analysis_period_end"
    ]:
        raise RuntimeError("Frontier Analysis feedback snapshot mismatch")
    relative = Path("frontier") / "frontier-analysis.json"
    payload = {
        "schema_version": "frontier_analysis_run_snapshot.v1",
        **period.to_dict(),
        "run_id": run_id,
        "manifest_path": str(manifest_path.resolve()),
        "pipeline_profile": PIPELINE_PROFILE,
        "frontier_analysis": row,
    }
    artifact_path = run_dir / relative
    _atomic_write_json(artifact_path, payload, exclusive=True)
    return {
        "analysis_id": int(row["id"]),
        "artifact_path": relative.as_posix(),
        "checksums": {"artifact_path": sha256_file(artifact_path)},
        "record_counts": {
            "threads": int(summary.threads_analyzed),
            "atoms": int(summary.atoms_analyzed),
            "actions": int(summary.action_count),
        },
    }


def _radar_stage(
    settings: Settings,
    period: ReportingPeriod,
    manifest: Mapping[str, Any],
    run_dir: Path,
    manifest_path: Path,
    *,
    limit: int,
    include_channels: tuple[str, ...],
    market_context_days: int,
    force_market_baseline: bool,
    with_live_source_index: bool,
    live_intelligence_path: str | Path | None,
) -> _RadarStageResult:
    radar_dir = run_dir / "radar"
    seed_path = radar_dir / "opportunity-seeds.json"
    radar_run_id = _radar_run_id(str(manifest["run_id"]))
    bound_live_intelligence = _bound_live_intelligence_input(
        period,
        radar_dir=radar_dir,
        enabled=with_live_source_index,
        source_path=live_intelligence_path,
    )
    result = run_mvp_weekly_pipeline(
        settings,
        reporting_period=period,
        limit=limit,
        include_channels=include_channels,
        market_context_days=market_context_days,
        force_market_baseline=force_market_baseline,
        seed_output_path=seed_path,
        radar_run_id=radar_run_id,
        deliver=False,
        emit_operator_outputs=False,
        # The orchestrator owns the immutable copy; the legacy pipeline only
        # validates and passes that exact file to Radar.
        with_live_source_index=False,
        live_intelligence_path=bound_live_intelligence,
    )
    _validate_pipeline_period(result, period, radar_run_id)
    if Path(result.seed_path).resolve() != seed_path.resolve() or not seed_path.is_file():
        raise RuntimeError("Radar seed output is not the declared run-scoped artifact")
    _validate_seed_period(seed_path, period)
    if not result.json_path:
        raise RuntimeError("Radar returned no JSON artifact")
    source_json = Path(result.json_path)
    if not source_json.is_file():
        raise RuntimeError("Radar JSON artifact is missing")
    raw_payload = _load_json_object(source_json, label="Radar JSON")
    raw_result = raw_payload.get("result")
    if not isinstance(raw_result, Mapping) or raw_result.get("run_id") != radar_run_id:
        raise RuntimeError("Radar JSON result.run_id does not match this invocation")

    raw_relative = Path("radar") / "radar-result.json"
    raw_path = run_dir / raw_relative
    _atomic_copy(source_json, raw_path, exclusive=True)
    copied_payload = _load_json_object(raw_path, label="copied Radar JSON")
    if copied_payload != raw_payload:
        raise RuntimeError("copied Radar JSON payload changed during binding")

    seed_relative = _relative_run_path(seed_path, run_dir)
    binding_relative = Path("radar") / "radar-run-binding.json"
    binding_path = run_dir / binding_relative
    selected = raw_payload.get("selected")
    status_projection = {
        key: raw_result.get(key)
        for key in (
            "status",
            "selected_title",
            "dossier_status",
            "recommendation",
            "score",
            "selected_source_mix",
        )
        if key in raw_result
    }
    if not status_projection:
        status_projection = {"status": result.radar_status}
    binding = build_radar_run_binding(
        manifest,
        radar_run_id=radar_run_id,
        radar_contract_version=RADAR_INTELLIGENCE_CONTRACT_VERSION,
        radar_schema_version=str(
            raw_payload.get("schema_version")
            or raw_payload.get("contract_version")
            or "demand_mvp_radar.mvp_of_week.v1"
        ),
        seed_export_path=seed_relative.as_posix(),
        radar_json_path=raw_relative.as_posix(),
        selected_candidate=selected if isinstance(selected, Mapping) else None,
        status_projection=status_projection,
        path_base=run_dir,
        allowed_roots=(run_dir,),
    )
    write_radar_run_binding(
        binding_path,
        binding,
        manifest=manifest,
        path_base=run_dir,
        allowed_roots=(run_dir,),
    )

    dependency_refs: dict[str, str] = {}
    checksums: dict[str, str] = {}
    for name, value in (
        ("market_lens_path", result.market_lens_path),
        ("market_pack_path", result.market_pack_path),
        ("market_baseline_path", result.market_baseline_path),
        ("market_delta_path", result.market_delta_path),
        ("live_intelligence_path", result.live_intelligence_path),
    ):
        if not value:
            continue
        path = Path(value)
        relative = _relative_run_path(path, run_dir)
        if not path.is_file():
            raise RuntimeError(f"Radar dependency is missing: {name}")
        dependency_refs[name] = relative.as_posix()
        checksums[name] = sha256_file(path)

    return _RadarStageResult(
        manifest_updates={
            "radar_run_id": radar_run_id,
            "artifact_path": raw_relative.as_posix(),
            "artifact_sha256": sha256_file(raw_path),
            "binding_path": binding_relative.as_posix(),
            "binding_sha256": sha256_file(binding_path),
            "seed_export_path": seed_relative.as_posix(),
            "seed_export_sha256": sha256_file(seed_path),
            "reporting_week": period.reporting_week,
            "market_lens_path": dependency_refs.get("market_lens_path"),
            "record_counts": {
                "seeds": max(0, int(result.seed_count)),
                "knowledge_threads": max(0, int(result.knowledge_thread_count)),
            },
            "dependency_refs": dependency_refs,
            "artifact_refs": {"binding_path": binding_relative.as_posix()},
            "checksums": checksums,
        },
        brief_json_path=raw_path,
    )


def _bound_live_intelligence_input(
    period: ReportingPeriod,
    *,
    radar_dir: Path,
    enabled: bool,
    source_path: str | Path | None,
) -> Path | None:
    """Create the immutable run-scoped live-intelligence input, when requested."""

    if source_path is None and not enabled:
        return None
    radar_dir.mkdir(parents=True, exist_ok=True)
    destination = radar_dir / "live-intelligence.json"
    if source_path is not None:
        source = Path(source_path)
        if not source.is_file():
            raise FileNotFoundError(f"Live intelligence snapshot not found: {source}")
        _atomic_copy(source, destination, exclusive=True)
        return destination

    from output.live_source_intelligence import build_live_source_intelligence_snapshot

    build_live_source_intelligence_snapshot(
        reporting_period=period,
        output_path=destination,
    )
    if not destination.is_file():
        raise RuntimeError("run-scoped live intelligence snapshot was not created")
    return destination


def _frontier_context_from_manifest(
    manifest: Mapping[str, Any],
    *,
    run_dir: Path,
    manifest_path: Path,
    period: ReportingPeriod,
) -> dict[str, Any] | None:
    """Return only the Frontier snapshot bound to this manifest run."""

    stage = manifest["stages"]["frontier_analysis"]
    if stage["status"] != SUCCEEDED:
        return None
    artifact_path = _bound_file(run_dir, stage.get("artifact_path"))
    if artifact_path is None:
        raise RuntimeError("run-scoped Frontier snapshot is missing")
    payload = _load_json_object(artifact_path, label="Frontier run snapshot")
    if payload.get("schema_version") != "frontier_analysis_run_snapshot.v1":
        raise RuntimeError("Frontier run snapshot schema mismatch")
    expected = period.to_dict()
    for field in (
        "run_date",
        "generated_at",
        "reporting_week",
        "week_label",
        "period_mode",
        "analysis_period_start",
        "analysis_period_end",
    ):
        if str(payload.get(field) or "") != str(expected[field]):
            raise RuntimeError(f"Frontier run snapshot period mismatch: {field}")
    if payload.get("run_id") != manifest["run_id"]:
        raise RuntimeError("Frontier run snapshot run ID mismatch")
    if str(payload.get("manifest_path") or "") != str(manifest_path.resolve()):
        raise RuntimeError("Frontier run snapshot manifest path mismatch")
    if payload.get("pipeline_profile") != manifest["pipeline_profile"]:
        raise RuntimeError("Frontier run snapshot pipeline profile mismatch")
    analysis = payload.get("frontier_analysis")
    if not isinstance(analysis, Mapping):
        raise RuntimeError("Frontier run snapshot has no analysis object")
    if int(analysis.get("id") or 0) != int(stage.get("analysis_id") or 0):
        raise RuntimeError("Frontier run snapshot analysis ID mismatch")
    return dict(analysis)


def _render_reader_stages(
    *,
    settings: Settings,
    period: ReportingPeriod,
    manifest_path: Path,
    manifest: dict[str, Any],
    persist,
    run_dir: Path,
    reaction_snapshot_at: str,
    radar_brief_path: Path | None,
    radar_enabled: bool,
    threads_limit: int,
    atoms_limit: int,
) -> dict[str, Any]:
    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        context = load_ai_intelligence_context(
            connection,
            week_label=period.reporting_week,
            reporting_period=period,
            reaction_snapshot_at=reaction_snapshot_at,
            feedback_snapshot_at=period.analysis_period_end,
            threads_limit=threads_limit,
            atoms_limit=atoms_limit,
        )
    context = {
        **context,
        "reaction_snapshot_at": reaction_snapshot_at,
        # The mutable week-keyed DB row is not authoritative for an IRX-2 run.
        # Bind the reader to this run's immutable Frontier snapshot, or suppress
        # Frontier content when that stage failed.
        "frontier_analysis": _frontier_context_from_manifest(
            manifest,
            run_dir=run_dir,
            manifest_path=manifest_path,
            period=period,
        ),
    }
    if radar_enabled and radar_brief_path is not None:
        mvp_radar = load_mvp_radar_summary(period.reporting_week, radar_brief_path)
    elif radar_enabled:
        # Never allow the orchestrated path to rediscover an older week-named
        # V1 or sibling artifact after this run's required Radar stage failed.
        mvp_radar = {
            "status": "not_available",
            "selected_candidate": None,
            "dossier_status": None,
            "recommendation": "needs_more_evidence",
            "source_mix": {},
            "missing_evidence": ["Same-run MVP Radar JSON is unavailable."],
            "next_validation": ["Retry MVP Radar in a new weekly run."],
            "source_path": None,
        }
    else:
        mvp_radar = {
            "status": "intentionally_disabled",
            "disabled": True,
            "selected_candidate": None,
            "dossier_status": None,
            "recommendation": "needs_more_evidence",
            "source_mix": {},
            "missing_evidence": [RADAR_DISABLED_DISCLOSURE_RU],
            "next_validation": [],
            "source_path": None,
        }

    brief_root = run_dir / "weekly_brief"
    atlas_root = run_dir / "knowledge_atlas"
    brief_html = brief_root / f"{period.reporting_week}.weekly-brief.html"
    brief_json = brief_root / f"{period.reporting_week}.weekly-brief.json"
    atlas_html = atlas_root / f"{period.reporting_week}.knowledge-atlas.html"
    atlas_json = atlas_root / f"{period.reporting_week}.knowledge-atlas.json"
    brief_updates = {
        "html_path": _relative_run_path(brief_html, run_dir).as_posix(),
        "json_path": _relative_run_path(brief_json, run_dir).as_posix(),
        "checksums": {
            "html_path": "0" * 64,
            "json_path": "0" * 64,
        },
    }
    atlas_updates = {
        "html_path": _relative_run_path(atlas_html, run_dir).as_posix(),
        "json_path": _relative_run_path(atlas_json, run_dir).as_posix(),
        "checksums": {
            "html_path": "0" * 64,
            "json_path": "0" * 64,
        },
    }

    manifest = persist(start_stage(manifest, "weekly_brief"))
    try:
        preliminary_identity = _run_identity(manifest_path, manifest, run_status="running")
        build_weekly_intelligence_brief_artifact(
            context,
            generated_at=manifest["generated_at"],
            output_root=brief_root,
            mvp_radar=mvp_radar,
            related_artifacts={},
            run_identity=preliminary_identity,
        )
    except Exception as exc:
        _remove_reader_artifacts(brief_html, brief_json)
        manifest = persist(fail_stage(manifest, "weekly_brief", exc), check_outputs=False)
        manifest = persist(
            transition_stage(
                manifest,
                "knowledge_atlas",
                SKIPPED_DEPENDENCY,
                error="Weekly Brief render failed",
            ),
            check_outputs=False,
        )
        return manifest

    manifest = persist(start_stage(manifest, "knowledge_atlas"))
    atlas_rendered = False
    predicted = _predicted_reader_identity(
        manifest_path,
        manifest,
        brief_updates=brief_updates,
        atlas_updates=atlas_updates,
        atlas_succeeds=True,
    )
    try:
        build_knowledge_atlas_artifact(
            context,
            generated_at=manifest["generated_at"],
            output_root=atlas_root,
            related_artifacts={
                "weekly_brief_html_path": str(brief_html),
                "weekly_brief_json_path": str(brief_json),
            },
            run_identity=predicted,
        )
        atlas_rendered = True
    except Exception as exc:
        _remove_reader_artifacts(atlas_html, atlas_json)
        manifest = persist(fail_stage(manifest, "knowledge_atlas", exc), check_outputs=False)
        manifest = persist(
            append_warning(manifest, "Knowledge Atlas render failed; the Brief remains available."),
            check_outputs=False,
        )

    final_identity = _predicted_reader_identity(
        manifest_path,
        manifest,
        brief_updates=brief_updates,
        atlas_updates=atlas_updates,
        atlas_succeeds=atlas_rendered,
    )
    try:
        build_weekly_intelligence_brief_artifact(
            context,
            generated_at=manifest["generated_at"],
            output_root=brief_root,
            mvp_radar=mvp_radar,
            related_artifacts=(
                {
                    "knowledge_atlas_html_path": str(atlas_html),
                    "knowledge_atlas_json_path": str(atlas_json),
                }
                if atlas_rendered
                else {}
            ),
            run_identity=final_identity,
        )
    except Exception as exc:
        _remove_reader_artifacts(brief_html, brief_json)
        manifest = persist(fail_stage(manifest, "weekly_brief", exc), check_outputs=False)
        if atlas_rendered:
            manifest = persist(
                transition_stage(
                    manifest,
                    "knowledge_atlas",
                    CANCELLED,
                    error="Weekly Brief finalization failed",
                ),
                check_outputs=False,
            )
            _remove_reader_artifacts(atlas_html, atlas_json)
        return manifest

    final_brief_updates = _reader_artifact_updates(
        brief_html,
        brief_json,
        run_dir=run_dir,
    )
    candidate = manifest
    if atlas_rendered:
        final_atlas_updates = _reader_artifact_updates(
            atlas_html,
            atlas_json,
            run_dir=run_dir,
        )
        candidate = succeed_stage(
            candidate,
            "knowledge_atlas",
            updates=final_atlas_updates,
        )
    candidate = succeed_stage(
        candidate,
        "weekly_brief",
        updates=final_brief_updates,
    )
    # Persist the mutually-referencing reader package as one state transition.
    # The manifest validator can now verify both final sidecars together.
    return persist(candidate)


def _reader_artifact_updates(
    html_path: Path,
    json_path: Path,
    *,
    run_dir: Path,
) -> dict[str, Any]:
    if not html_path.is_file() or not json_path.is_file():
        raise RuntimeError("reader artifact pair is incomplete")
    return {
        "html_path": _relative_run_path(html_path, run_dir).as_posix(),
        "json_path": _relative_run_path(json_path, run_dir).as_posix(),
        "checksums": {
            "html_path": sha256_file(html_path),
            "json_path": sha256_file(json_path),
        },
    }


def _predicted_reader_identity(
    manifest_path: Path,
    manifest: Mapping[str, Any],
    *,
    brief_updates: Mapping[str, Any],
    atlas_updates: Mapping[str, Any],
    atlas_succeeds: bool,
) -> dict[str, Any]:
    candidate = dict(manifest)
    if candidate["stages"]["weekly_brief"]["status"] != SUCCEEDED:
        candidate = succeed_stage(candidate, "weekly_brief", updates=brief_updates)
    atlas_status = candidate["stages"]["knowledge_atlas"]["status"]
    if atlas_succeeds and atlas_status != SUCCEEDED:
        if atlas_status == "pending":
            candidate = start_stage(candidate, "knowledge_atlas")
        candidate = succeed_stage(candidate, "knowledge_atlas", updates=atlas_updates)
    terminal = finalize_manifest(candidate)
    return _run_identity(manifest_path, terminal)


def _run_identity(
    manifest_path: Path,
    manifest: Mapping[str, Any],
    *,
    run_status: str | None = None,
) -> dict[str, Any]:
    status = run_status or str(manifest["run_status"])
    failed_stages = [
        name
        for name, stage in manifest["stages"].items()
        if stage.get("enabled")
        and stage.get("status") in {FAILED, SKIPPED_DEPENDENCY, CANCELLED}
    ]
    return {
        "run_id": manifest["run_id"],
        "manifest_path": str(manifest_path.resolve()),
        "run_status": status,
        "partial": status == "partial" or bool(manifest.get("partial")),
        "pipeline_profile": manifest["pipeline_profile"],
        "failed_stages": failed_stages,
        "warnings": [str(item) for item in manifest.get("warnings") or ()],
    }


def _skip_pending_stages(manifest: Mapping[str, Any], reason: str) -> dict[str, Any]:
    result = dict(manifest)
    for name, stage in list(result["stages"].items()):
        if stage["enabled"] and stage["status"] == "pending":
            result = transition_stage(
                result,
                name,
                SKIPPED_DEPENDENCY,
                error=reason,
            )
    return result


def _recover_reader_failure(
    manifest: Mapping[str, Any],
    error: BaseException,
) -> dict[str, Any]:
    """Turn an unexpected reader/orchestration exception into terminal state."""

    result = dict(manifest)
    brief_status = result["stages"]["weekly_brief"]["status"]
    if brief_status == "pending":
        result = start_stage(result, "weekly_brief")
        brief_status = "running"
    if brief_status == "running":
        result = fail_stage(result, "weekly_brief", error)
    atlas_status = result["stages"]["knowledge_atlas"]["status"]
    if atlas_status == "pending":
        result = transition_stage(
            result,
            "knowledge_atlas",
            SKIPPED_DEPENDENCY,
            error="Weekly Brief did not finalize",
        )
    elif atlas_status == "running":
        if result["stages"]["weekly_brief"]["status"] == FAILED:
            result = transition_stage(
                result,
                "knowledge_atlas",
                CANCELLED,
                error="Weekly Brief did not finalize",
            )
        else:
            result = fail_stage(result, "knowledge_atlas", error)
    return result


def _radar_run_id(manifest_run_id: str) -> str:
    candidate = f"{manifest_run_id}-radar"
    if len(candidate) <= 128:
        return candidate
    digest = hashlib.sha256(manifest_run_id.encode("utf-8")).hexdigest()
    return f"radar-{digest}"


def _validate_pipeline_period(
    result: MvpWeeklyPipelineResult,
    period: ReportingPeriod,
    radar_run_id: str,
) -> None:
    expected = period.to_dict()
    actual = asdict(result)
    for field in (
        "reporting_week",
        "week_label",
        "period_mode",
        "analysis_period_start",
        "analysis_period_end",
    ):
        expected_value = expected["week_label" if field == "week_label" else field]
        if str(actual.get(field) or "") != str(expected_value):
            raise RuntimeError(f"Radar pipeline period mismatch: {field}")
    if result.radar_run_id != radar_run_id:
        raise RuntimeError("Radar pipeline run ID mismatch")


def _validate_seed_period(path: Path, period: ReportingPeriod) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Radar seed export is malformed") from exc
    if not isinstance(payload, list):
        raise RuntimeError("Radar seed export must be a JSON array")
    expected = period.to_dict()
    for index, item in enumerate(payload):
        if not isinstance(item, Mapping):
            raise RuntimeError(f"Radar seed {index} must be an object")
        for field in (
            "reporting_week",
            "week_label",
            "period_mode",
            "analysis_period_start",
            "analysis_period_end",
        ):
            if item.get(field) != expected[field]:
                raise RuntimeError(f"Radar seed {index} period mismatch: {field}")


def _deliver_from_manifest(
    manifest_path: Path,
    manifest: Mapping[str, Any],
    *,
    chat_id: str | None,
    token: str | None,
) -> tuple[int | None, ...]:
    """Deliver only paths bound by this finalized manifest."""

    from bot.telegram_delivery import send_document, send_text

    clean_chat_id = str(chat_id or os.environ.get("TELEGRAM_OWNER_CHAT_ID", "")).strip()
    clean_token = str(token or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
    if not clean_chat_id or not clean_token:
        return ()
    run_dir = manifest_path.parent
    validated = load_manifest(
        manifest_path,
        path_base=run_dir,
        allowed_roots=(run_dir,),
        check_artifact_existence=True,
    )
    if validated["run_id"] != manifest.get("run_id"):
        raise RuntimeError("delivery manifest run ID changed after finalization")
    manifest = validated
    if manifest["run_status"] not in {"complete", "partial"}:
        return ()
    brief_path = _bound_file(run_dir, manifest.get("weekly_brief_html_path"))
    if brief_path is None:
        return ()
    ids: list[int | None] = [
        send_text(
            chat_id=clean_chat_id,
            text=(
                f"Weekly Intelligence run {manifest['run_id']} finalized "
                f"as {manifest['run_status']}."
            ),
            token=clean_token,
            parse_mode=None,
        ),
        send_document(
            chat_id=clean_chat_id,
            file_path=str(brief_path),
            caption=f"Weekly Intelligence Brief {manifest['reporting_week']}",
            token=clean_token,
        ),
    ]
    atlas_path = _bound_file(run_dir, manifest.get("atlas_html_path"))
    if atlas_path is not None:
        ids.append(
            send_document(
                chat_id=clean_chat_id,
                file_path=str(atlas_path),
                caption=f"Knowledge Atlas {manifest['reporting_week']}",
                token=clean_token,
            )
        )
    return tuple(ids)


def _bound_file(run_dir: Path, relative: object) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    candidate = (run_dir / relative).resolve()
    try:
        candidate.relative_to(run_dir.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _result_from_manifest(
    manifest_path: Path,
    manifest: Mapping[str, Any],
    *,
    delivered: tuple[int | None, ...] = (),
) -> WeeklyIntelligenceRunResult:
    return WeeklyIntelligenceRunResult(
        run_id=str(manifest["run_id"]),
        manifest_path=str(manifest_path.resolve()),
        run_status=str(manifest["run_status"]),
        partial=bool(manifest["partial"]),
        reporting_week=str(manifest["reporting_week"]),
        analysis_period_start=str(manifest["analysis_period_start"]),
        analysis_period_end=str(manifest["analysis_period_end"]),
        weekly_brief_html_path=_resolved_manifest_path(
            manifest_path.parent, manifest.get("weekly_brief_html_path")
        ),
        weekly_brief_json_path=_resolved_manifest_path(
            manifest_path.parent, manifest.get("weekly_brief_json_path")
        ),
        atlas_html_path=_resolved_manifest_path(
            manifest_path.parent, manifest.get("atlas_html_path")
        ),
        atlas_json_path=_resolved_manifest_path(
            manifest_path.parent, manifest.get("atlas_json_path")
        ),
        radar_json_path=_resolved_manifest_path(
            manifest_path.parent, manifest.get("radar_json_path")
        ),
        warnings=tuple(str(item) for item in manifest.get("warnings") or ()),
        delivered_message_ids=delivered,
    )


def _resolved_manifest_path(run_dir: Path, value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return str((run_dir / value).resolve())


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} is malformed") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} must be an object")
    return payload


def _relative_run_path(path: Path, run_dir: Path) -> Path:
    try:
        return path.resolve().relative_to(run_dir.resolve())
    except ValueError as exc:
        raise RuntimeError(f"artifact escapes the weekly run root: {path}") from exc


def _integer_counts(values: Mapping[str, Any] | object) -> dict[str, int]:
    if not isinstance(values, Mapping):
        return {}
    return {
        str(key): max(0, int(value))
        for key, value in values.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write_json(path: Path, payload: object, *, exclusive: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and path.exists():
        raise FileExistsError(f"immutable run artifact already exists: {path}")
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive:
            try:
                os.link(temporary, path)
            except FileExistsError:
                raise FileExistsError(f"immutable run artifact already exists: {path}")
        else:
            os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_copy(source: Path, target: Path, *, exclusive: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and target.exists():
        raise FileExistsError(f"immutable run artifact already exists: {target}")
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with source.open("rb") as input_handle, os.fdopen(fd, "wb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        if exclusive:
            try:
                os.link(temporary, target)
            except FileExistsError:
                raise FileExistsError(f"immutable run artifact already exists: {target}")
        else:
            os.replace(temporary, target)
        _fsync_directory(target.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_reader_artifacts(*paths: Path) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def _remove_unbound_reader_artifacts(
    manifest: Mapping[str, Any],
    *,
    run_dir: Path,
    reporting_week: str,
) -> None:
    readers = (
        (
            "weekly_brief",
            run_dir / "weekly_brief" / f"{reporting_week}.weekly-brief.html",
            run_dir / "weekly_brief" / f"{reporting_week}.weekly-brief.json",
        ),
        (
            "knowledge_atlas",
            run_dir / "knowledge_atlas" / f"{reporting_week}.knowledge-atlas.html",
            run_dir / "knowledge_atlas" / f"{reporting_week}.knowledge-atlas.json",
        ),
    )
    for stage_name, html_path, json_path in readers:
        if manifest["stages"][stage_name]["status"] in {"pending", "running"}:
            _remove_reader_artifacts(html_path, json_path)
