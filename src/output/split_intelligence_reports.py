from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from config.settings import PROJECT_ROOT, Settings
from output.ai_intelligence_report import _current_week_label, load_ai_intelligence_context
from output.knowledge_atlas_report import (
    KnowledgeAtlasSummary,
    build_knowledge_atlas_artifact,
)
from output.weekly_intelligence_brief import (
    WeeklyIntelligenceBriefSummary,
    build_weekly_intelligence_brief_artifact,
    load_mvp_radar_summary,
)


OUTPUT_ROOT = PROJECT_ROOT / "data" / "output"


@dataclass(frozen=True)
class SplitIntelligenceReportsSummary:
    week_label: str
    generated_at: str
    knowledge_atlas: KnowledgeAtlasSummary
    weekly_brief: WeeklyIntelligenceBriefSummary
    notification_text: str


def generate_split_intelligence_reports(
    settings: Settings,
    *,
    week_label: str | None = None,
    threads_limit: int = 24,
    atoms_limit: int = 8,
    output_root: str | Path | None = None,
    mvp_radar_json_path: str | Path | None = None,
    now: datetime | None = None,
) -> SplitIntelligenceReportsSummary:
    clean_week = str(week_label or _current_week_label(now)).strip()
    generated_at = (now or _utc_now()).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    root = Path(output_root) if output_root is not None else OUTPUT_ROOT
    atlas_root = root / "knowledge_atlas"
    brief_root = root / "weekly_intelligence_briefs"
    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        context = load_ai_intelligence_context(
            connection,
            week_label=clean_week,
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
        generated_at=generated_at,
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
    return (
        f"Split AI intelligence reports {summary.week_label} are ready.\n"
        f"Weekly Brief: {summary.weekly_brief.html_path}\n"
        f"Knowledge Atlas: {summary.knowledge_atlas.html_path}"
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
