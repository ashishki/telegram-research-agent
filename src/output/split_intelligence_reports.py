from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Mapping, Sequence

from config.settings import PROJECT_ROOT, Settings
from output.ai_intelligence_report import load_ai_intelligence_context
from output.knowledge_atlas_report import (
    KnowledgeAtlasSummary,
    build_knowledge_atlas_artifact,
)
from output.reporting_period import (
    ReportingPeriod,
    format_period_display_label,
    resolve_reporting_period,
)
from output.weekly_intelligence_brief import (
    WeeklyIntelligenceBriefSummary,
    build_weekly_intelligence_brief_artifact,
    load_mvp_radar_summary,
)

if TYPE_CHECKING:
    from llm.client import LLMCompletionReceipt
    from output.editorial_intelligence import EditorialIntelligenceSummary
    from output.project_intelligence import ProjectIntelligenceSummary


OUTPUT_ROOT = PROJECT_ROOT / "data" / "output"
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SplitIntelligenceReportsSummary:
    week_label: str
    generated_at: str
    knowledge_atlas: KnowledgeAtlasSummary
    weekly_brief: WeeklyIntelligenceBriefSummary
    notification_text: str
    delivered_message_ids: tuple[int | None, ...] = ()
    reporting_week: str = ""
    run_date: str = ""
    analysis_period_start: str = ""
    analysis_period_end: str = ""
    period_mode: str = ""
    run_id: str = ""
    manifest_path: str = ""
    run_status: str = ""
    partial: bool = False
    pipeline_profile: str = ""
    project_intelligence: ProjectIntelligenceSummary | None = None
    project_intelligence_error: str = ""
    editorial_intelligence: EditorialIntelligenceSummary | None = None
    editorial_intelligence_error: str = ""


def generate_split_intelligence_reports(
    settings: Settings,
    *,
    week_label: str | None = None,
    period_mode: str | None = None,
    reporting_period: ReportingPeriod | None = None,
    threads_limit: int = 24,
    atoms_limit: int = 8,
    output_root: str | Path | None = None,
    mvp_radar_json_path: str | Path | None = None,
    now: datetime | None = None,
    reaction_snapshot_at: datetime | str | None = None,
    reaction_snapshot_binding: Mapping[str, object] | None = None,
    reaction_snapshot: Mapping[str, object] | None = None,
    feedback_snapshot_at: datetime | str | None = None,
    feedback_snapshot_usable: bool = True,
    run_identity: Mapping[str, object] | None = None,
    project_intelligence_output_root: str | Path | None = None,
    project_intelligence_projects_path: str | Path | None = None,
    project_intelligence_diagnostics: Sequence[Mapping[str, object]] | None = None,
    editorial_output_root: str | Path | None = None,
    editorial_radar_binding: Mapping[str, object] | None = None,
    editorial_completion: Callable[..., LLMCompletionReceipt] | None = None,
    editorial_model: str | None = None,
    editorial_generated_at: datetime | str | None = None,
) -> SplitIntelligenceReportsSummary:
    resolved_period = _resolve_split_reporting_period(
        reporting_period=reporting_period,
        now=now,
        week_label=week_label,
        period_mode=period_mode,
    )
    period_metadata = resolved_period.to_dict()
    clean_week = resolved_period.week_label
    generated_at = period_metadata["generated_at"]
    root = Path(output_root) if output_root is not None else OUTPUT_ROOT
    atlas_root = root / "knowledge_atlas"
    brief_root = root / "weekly_intelligence_briefs"
    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        context = load_ai_intelligence_context(
            connection,
            week_label=clean_week,
            reporting_period=resolved_period,
            reaction_snapshot_at=reaction_snapshot_at,
            feedback_snapshot_at=feedback_snapshot_at,
            reaction_snapshot_binding=(
                dict(reaction_snapshot_binding)
                if reaction_snapshot_binding is not None
                else None
            ),
            reaction_snapshot=(
                dict(reaction_snapshot) if reaction_snapshot is not None else None
            ),
            feedback_snapshot_usable=feedback_snapshot_usable,
            threads_limit=max(1, int(threads_limit or 24)),
            atoms_limit=max(1, int(atoms_limit or 8)),
        )
    mvp_radar = load_mvp_radar_summary(clean_week, mvp_radar_json_path)
    weekly_brief = build_weekly_intelligence_brief_artifact(
        context,
        generated_at=generated_at,
        output_root=brief_root,
        mvp_radar=mvp_radar,
        related_artifacts={},
        run_identity=run_identity,
    )
    knowledge_atlas = build_knowledge_atlas_artifact(
        context,
        generated_at=generated_at,
        output_root=atlas_root,
        related_artifacts={
            "weekly_brief_html_path": weekly_brief.html_path,
            "weekly_brief_json_path": weekly_brief.json_path,
        },
        run_identity=run_identity,
    )
    # Rewrite the weekly brief sidecar once the Atlas path is known so both
    # surfaces are cross-linked without reloading the DB context.
    weekly_brief = build_weekly_intelligence_brief_artifact(
        context,
        generated_at=generated_at,
        output_root=brief_root,
        mvp_radar=mvp_radar,
        related_artifacts={
            "knowledge_atlas_html_path": knowledge_atlas.html_path,
            "knowledge_atlas_json_path": knowledge_atlas.json_path,
        },
        run_identity=run_identity,
    )
    project_intelligence = None
    project_intelligence_error = ""
    project_permissions: Sequence[Mapping[str, object]] = ()
    editorial_intelligence = None
    editorial_intelligence_error = ""

    shadow_requested = (
        project_intelligence_output_root is not None
        or editorial_output_root is not None
    )
    shadow_context = context
    shadow_context_error: Exception | None = None
    feedback_count = 0
    if shadow_requested:
        try:
            # A shadow-only reload binds mutable feedback reads to the run
            # cutoff without changing the already-built V1 reader surfaces.
            if feedback_snapshot_at is None:
                with sqlite3.connect(settings.db_path) as connection:
                    connection.row_factory = sqlite3.Row
                    connection.execute("PRAGMA foreign_keys = ON;")
                    shadow_context = load_ai_intelligence_context(
                        connection,
                        week_label=clean_week,
                        reporting_period=resolved_period,
                        reaction_snapshot_at=reaction_snapshot_at,
                        feedback_snapshot_at=resolved_period.analysis_period_end,
                        reaction_snapshot_binding=(
                            dict(reaction_snapshot_binding)
                            if reaction_snapshot_binding is not None
                            else None
                        ),
                        reaction_snapshot=(
                            dict(reaction_snapshot)
                            if reaction_snapshot is not None
                            else None
                        ),
                        feedback_snapshot_usable=feedback_snapshot_usable,
                        threads_limit=max(1, int(threads_limit or 24)),
                        atoms_limit=max(1, int(atoms_limit or 8)),
                    )
            feedback_context = shadow_context.get("feedback_context")
            feedback_count = (
                int(feedback_context.get("confirmed_event_count") or 0)
                if isinstance(feedback_context, Mapping)
                else 0
            )
        except Exception as exc:  # Shadow context must never block V1 delivery.
            shadow_context_error = exc

    shadow_identity = {
        **period_metadata,
        **(dict(run_identity) if isinstance(run_identity, Mapping) else {}),
    }

    if project_intelligence_output_root is not None:
        try:
            if shadow_context_error is not None:
                raise shadow_context_error
            from output.editorial_intelligence import build_editorial_input_package
            from output.project_intelligence import (
                PROJECTS_YAML_PATH,
                generate_project_intelligence_artifact,
                load_project_action_descriptors,
                load_project_intelligence_artifact,
                project_editorial_permissions,
            )

            preliminary_package = build_editorial_input_package(
                shadow_context,
                run_identity=shadow_identity,
                radar_binding=editorial_radar_binding,
                project_permissions=(),
                feedback_snapshot_count=feedback_count,
            )
            diagnostic_options = (
                {"diagnostic_records": tuple(project_intelligence_diagnostics)}
                if project_intelligence_diagnostics is not None
                else {}
            )
            if project_intelligence_projects_path is None:
                project_summary = generate_project_intelligence_artifact(
                    preliminary_package,
                    output_root=project_intelligence_output_root,
                    **diagnostic_options,
                )
            else:
                project_summary = generate_project_intelligence_artifact(
                    preliminary_package,
                    output_root=project_intelligence_output_root,
                    projects_yaml_path=Path(project_intelligence_projects_path),
                    **diagnostic_options,
                )
            project_artifact = load_project_intelligence_artifact(project_summary.path)
            projects_path = (
                Path(project_intelligence_projects_path)
                if project_intelligence_projects_path is not None
                else PROJECTS_YAML_PATH
            )
            project_descriptors = load_project_action_descriptors(projects_path)
            project_permissions = project_editorial_permissions(
                project_artifact,
                input_package=preliminary_package,
                projects=project_descriptors,
            )
            project_intelligence = project_summary
        except Exception as exc:  # Project shadow must never block V1 or editorial.
            project_intelligence_error = exc.__class__.__name__
            project_permissions = ()
            LOGGER.warning(
                "Project intelligence shadow failed without blocking V1 reports: %s",
                project_intelligence_error,
            )

    if editorial_output_root is not None:
        try:
            if shadow_context_error is not None:
                raise shadow_context_error
            from output.editorial_intelligence import (
                generate_editorial_intelligence_artifact,
            )

            editorial_intelligence = generate_editorial_intelligence_artifact(
                shadow_context,
                run_identity=shadow_identity,
                output_root=editorial_output_root,
                radar_binding=editorial_radar_binding,
                project_permissions=project_permissions,
                feedback_snapshot_count=feedback_count,
                completion=editorial_completion,
                model=editorial_model,
                generated_at=editorial_generated_at,
            )
        except Exception as exc:  # Editorial shadow must never block V1 delivery.
            editorial_intelligence_error = exc.__class__.__name__
            LOGGER.warning(
                "Editorial intelligence shadow failed without blocking V1 reports: %s",
                editorial_intelligence_error,
            )
    summary = SplitIntelligenceReportsSummary(
        week_label=clean_week,
        reporting_week=resolved_period.reporting_week,
        run_date=period_metadata["run_date"],
        generated_at=generated_at,
        analysis_period_start=period_metadata["analysis_period_start"],
        analysis_period_end=period_metadata["analysis_period_end"],
        period_mode=resolved_period.period_mode,
        run_id=str((run_identity or {}).get("run_id") or ""),
        manifest_path=str((run_identity or {}).get("manifest_path") or ""),
        run_status=str((run_identity or {}).get("run_status") or ""),
        partial=bool((run_identity or {}).get("partial", False)),
        pipeline_profile=str((run_identity or {}).get("pipeline_profile") or ""),
        knowledge_atlas=knowledge_atlas,
        weekly_brief=weekly_brief,
        project_intelligence=project_intelligence,
        project_intelligence_error=project_intelligence_error,
        editorial_intelligence=editorial_intelligence,
        editorial_intelligence_error=editorial_intelligence_error,
        notification_text="",
    )
    return SplitIntelligenceReportsSummary(
        **{
            **asdict(summary),
            "knowledge_atlas": knowledge_atlas,
            "weekly_brief": weekly_brief,
            "project_intelligence": project_intelligence,
            "project_intelligence_error": project_intelligence_error,
            "editorial_intelligence": editorial_intelligence,
            "editorial_intelligence_error": editorial_intelligence_error,
            "notification_text": build_split_reports_notification(summary),
        }
    )


def build_split_reports_notification(summary: SplitIntelligenceReportsSummary) -> str:
    period_label = _period_display_label(summary)
    return (
        f"Split AI intelligence reports {period_label} are ready.\n"
        f"Weekly Brief: {summary.weekly_brief.html_path}\n"
        f"Knowledge Atlas: {summary.knowledge_atlas.html_path}"
    )


def deliver_split_intelligence_reports(
    summary: SplitIntelligenceReportsSummary,
    *,
    chat_id: str | None = None,
    token: str | None = None,
) -> SplitIntelligenceReportsSummary:
    from bot.telegram_delivery import send_document, send_text

    clean_chat_id = str(chat_id or os.environ.get("TELEGRAM_OWNER_CHAT_ID", "")).strip()
    clean_token = str(token or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
    if not clean_chat_id or not clean_token:
        LOGGER.info(
            "Split AI report delivery skipped because Telegram credentials are missing"
        )
        return summary
    period_label = _period_display_label(summary)
    message_ids = [
        send_text(
            chat_id=clean_chat_id,
            text=summary.notification_text,
            token=clean_token,
            parse_mode=None,
        ),
        send_document(
            chat_id=clean_chat_id,
            file_path=str(summary.weekly_brief.html_path),
            caption=f"Weekly Intelligence Brief {period_label}",
            token=clean_token,
        ),
        send_document(
            chat_id=clean_chat_id,
            file_path=str(summary.knowledge_atlas.html_path),
            caption=f"Knowledge Atlas {period_label}",
            token=clean_token,
        ),
    ]
    return SplitIntelligenceReportsSummary(
        week_label=summary.week_label,
        reporting_week=summary.reporting_week,
        run_date=summary.run_date,
        generated_at=summary.generated_at,
        analysis_period_start=summary.analysis_period_start,
        analysis_period_end=summary.analysis_period_end,
        period_mode=summary.period_mode,
        knowledge_atlas=summary.knowledge_atlas,
        weekly_brief=summary.weekly_brief,
        notification_text=summary.notification_text,
        delivered_message_ids=tuple(message_ids),
        run_id=summary.run_id,
        manifest_path=summary.manifest_path,
        run_status=summary.run_status,
        partial=summary.partial,
        pipeline_profile=summary.pipeline_profile,
        project_intelligence=summary.project_intelligence,
        project_intelligence_error=summary.project_intelligence_error,
        editorial_intelligence=summary.editorial_intelligence,
        editorial_intelligence_error=summary.editorial_intelligence_error,
    )


def _period_display_label(summary: SplitIntelligenceReportsSummary) -> str:
    return format_period_display_label(
        period_mode=summary.period_mode,
        reporting_week=summary.reporting_week or summary.week_label,
        analysis_period_start=summary.analysis_period_start,
        analysis_period_end=summary.analysis_period_end,
    )


def _resolve_split_reporting_period(
    *,
    reporting_period: ReportingPeriod | None,
    now: datetime | None,
    week_label: str | None,
    period_mode: str | None,
) -> ReportingPeriod:
    if reporting_period is None:
        return resolve_reporting_period(
            now=now,
            week_label=week_label,
            period_mode=period_mode,
        )
    if not isinstance(reporting_period, ReportingPeriod):
        raise TypeError("reporting_period must be a ReportingPeriod")
    if (
        week_label is not None
        and str(week_label).strip() != reporting_period.week_label
    ):
        raise ValueError("week_label conflicts with reporting_period")
    if (
        period_mode is not None
        and str(period_mode).strip() != reporting_period.period_mode
    ):
        raise ValueError("period_mode conflicts with reporting_period")
    if now is not None:
        supplied_now = resolve_reporting_period(
            now=now,
            week_label=reporting_period.week_label
            if reporting_period.period_mode == "explicit_iso_week"
            else None,
            period_mode=reporting_period.period_mode,
        )
        if supplied_now != reporting_period:
            raise ValueError("now conflicts with reporting_period")
    return reporting_period


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
