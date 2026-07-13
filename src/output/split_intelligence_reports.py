from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from config.settings import PROJECT_ROOT, Settings
from output.ai_intelligence_report import load_ai_intelligence_context
from output.knowledge_atlas_report import (
    KnowledgeAtlasSummary,
    build_knowledge_atlas_artifact,
)
from output.reporting_period import format_period_display_label, resolve_reporting_period
from output.weekly_intelligence_brief import (
    WeeklyIntelligenceBriefSummary,
    build_weekly_intelligence_brief_artifact,
    load_mvp_radar_summary,
)


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


def generate_split_intelligence_reports(
    settings: Settings,
    *,
    week_label: str | None = None,
    period_mode: str | None = None,
    threads_limit: int = 24,
    atoms_limit: int = 8,
    output_root: str | Path | None = None,
    mvp_radar_json_path: str | Path | None = None,
    now: datetime | None = None,
) -> SplitIntelligenceReportsSummary:
    reporting_period = resolve_reporting_period(
        now=now,
        week_label=week_label,
        period_mode=period_mode,
    )
    period_metadata = reporting_period.to_dict()
    clean_week = reporting_period.week_label
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
            reporting_period=reporting_period,
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
    )
    knowledge_atlas = build_knowledge_atlas_artifact(
        context,
        generated_at=generated_at,
        output_root=atlas_root,
        related_artifacts={
            "weekly_brief_html_path": weekly_brief.html_path,
            "weekly_brief_json_path": weekly_brief.json_path,
        },
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
    )
    summary = SplitIntelligenceReportsSummary(
        week_label=clean_week,
        reporting_week=reporting_period.reporting_week,
        run_date=period_metadata["run_date"],
        generated_at=generated_at,
        analysis_period_start=period_metadata["analysis_period_start"],
        analysis_period_end=period_metadata["analysis_period_end"],
        period_mode=reporting_period.period_mode,
        knowledge_atlas=knowledge_atlas,
        weekly_brief=weekly_brief,
        notification_text="",
    )
    return SplitIntelligenceReportsSummary(
        **{
            **asdict(summary),
            "knowledge_atlas": knowledge_atlas,
            "weekly_brief": weekly_brief,
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
        LOGGER.info("Split AI report delivery skipped because Telegram credentials are missing")
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
    )


def _period_display_label(summary: SplitIntelligenceReportsSummary) -> str:
    return format_period_display_label(
        period_mode=summary.period_mode,
        reporting_week=summary.reporting_week or summary.week_label,
        analysis_period_start=summary.analysis_period_start,
        analysis_period_end=summary.analysis_period_end,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
