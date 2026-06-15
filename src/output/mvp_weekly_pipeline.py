import json
import logging
import os
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from delivery.telegraph import publish_article
from bot.callbacks import build_artifact_feedback_markup
from bot.telegram_delivery import send_document, send_text
from config.settings import PROJECT_ROOT, Settings
from output.opportunity_seed_export import export_opportunity_seeds
from output.render_report import render_report_html
from output.weekly_messages import build_mvp_message, write_weekly_message


LOGGER = logging.getLogger(__name__)
DEFAULT_RADAR_REPO = PROJECT_ROOT.parent / "Demand-to-MVP-Radar"
DEFAULT_MVP_MODEL = "claude-opus-4-7"
BUILD_READY_STATUSES = {"build", "focused_experiment"}
NON_BUILD_READY_RECOMMENDATIONS = {
    "revisit_with_evidence_gap",
    "needs_more_evidence",
    "needs_more_specific_scope",
    "existing_project_context",
    "reject",
}


@dataclass(frozen=True)
class MvpWeeklyPipelineResult:
    week_label: str
    seed_path: str
    seed_count: int
    radar_status: str
    report_path: str | None
    json_path: str | None
    selected_title: str | None
    dossier_status: str | None
    recommendation: str | None
    score: int | None
    selected_source_mix: dict[str, object] | None = None
    telegraph_url: str | None = None
    source_counts: dict[str, object] | None = None
    source_errors: dict[str, str] | None = None
    live_intelligence_path: str | None = None


def run_mvp_weekly_pipeline(
    settings: Settings,
    *,
    days: int = 7,
    limit: int = 80,
    include_channels: tuple[str, ...] = (),
    run_id: str | None = None,
    deliver: bool = True,
    with_live_source_index: bool = False,
    live_intelligence_path: Path | str | None = None,
    live_index_days: int | None = None,
    backfill_live_source_events: bool = False,
) -> MvpWeeklyPipelineResult:
    seed_export = export_opportunity_seeds(
        settings,
        days=days,
        limit=limit,
        include_channels=include_channels,
    )
    effective_run_id = run_id or f"mvp-weekly-{seed_export.week_label}"
    live_path = _prepare_live_intelligence_path(
        settings,
        explicit_path=live_intelligence_path,
        enabled=with_live_source_index,
        days=live_index_days or days,
        backfill=backfill_live_source_events,
    )
    radar_payload = _run_radar(
        seed_path=Path(seed_export.output_path),
        run_id=effective_run_id,
        live_intelligence_path=live_path,
    )
    result = MvpWeeklyPipelineResult(
        week_label=seed_export.week_label,
        seed_path=seed_export.output_path,
        seed_count=seed_export.seed_count,
        radar_status=str(radar_payload.get("status") or "unknown"),
        report_path=_optional_str(radar_payload.get("report_path")),
        json_path=_optional_str(radar_payload.get("json_path")),
        selected_title=_optional_str(radar_payload.get("selected_title")),
        dossier_status=_optional_str(radar_payload.get("dossier_status")),
        recommendation=_optional_str(radar_payload.get("recommendation")),
        score=_optional_int(radar_payload.get("score")),
        selected_source_mix=_optional_dict(radar_payload.get("selected_source_mix")),
        source_counts=_optional_dict(radar_payload.get("source_counts")),
        source_errors=_optional_str_dict(radar_payload.get("source_errors")),
        live_intelligence_path=str(live_path) if live_path is not None else None,
    )
    _write_mvp_operator_message(result)
    if deliver:
        telegraph_url = _deliver_result(result)
        result = replace(result, telegraph_url=telegraph_url)
    return result


def _prepare_live_intelligence_path(
    settings: Settings,
    *,
    explicit_path: Path | str | None,
    enabled: bool,
    days: int,
    backfill: bool,
) -> Path | None:
    if explicit_path is not None:
        path = Path(explicit_path)
        if not path.exists():
            raise FileNotFoundError(f"Live intelligence snapshot not found: {path}")
        return path
    if not enabled:
        return None
    from output.live_source_intelligence import build_live_source_intelligence_snapshot
    from output.source_events import backfill_recent_source_events

    if backfill:
        import sqlite3

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            backfill_recent_source_events(connection, days=max(1, int(days or 7)))
    result = build_live_source_intelligence_snapshot(days=max(1, int(days or 7)))
    return result.output_path


def _run_radar(
    *,
    seed_path: Path,
    run_id: str,
    live_intelligence_path: Path | None = None,
) -> dict[str, object]:
    radar_repo = Path(os.environ.get("RADAR_REPO_PATH", str(DEFAULT_RADAR_REPO))).resolve()
    if not radar_repo.exists():
        raise FileNotFoundError(f"Demand-to-MVP-Radar repository not found: {radar_repo}")

    data_dir = Path(os.environ.get("DMR_DATA_DIR", str(radar_repo / "data"))).resolve()
    report_dir = Path(os.environ.get("DMR_REPORT_DIR", str(radar_repo / "reports"))).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        f"{radar_repo}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else str(radar_repo)
    )
    env.setdefault("DMR_LLM_PROVIDER", "anthropic")
    env.setdefault("DMR_LLM_API_KEY", env.get("LLM_API_KEY", ""))
    env.setdefault(
        "DMR_LLM_MODEL_MVP_WEEKLY",
        env.get("LLM_MODEL_MVP_WEEKLY") or env.get("STRONG_MODEL") or DEFAULT_MVP_MODEL,
    )
    env.setdefault("DMR_LLM_FALLBACK_MODEL_MVP_WEEKLY", "claude-opus-4-1-20250805")
    source_config = Path(
        os.environ.get(
            "DMR_MVP_SOURCE_CONFIG",
            str(radar_repo / "config" / "mvp_weekly_sources.json"),
        )
    ).resolve()
    command = [
        *_radar_python_command(radar_repo),
        "-m",
        "demand_mvp_radar.cli",
        "mvp-of-week",
        "--telegram-export",
        str(seed_path),
        "--run-id",
        run_id,
        "--data-dir",
        str(data_dir),
        "--report-dir",
        str(report_dir),
    ]
    if source_config.exists():
        command.extend(["--source-config", str(source_config)])
    if live_intelligence_path is not None and live_intelligence_path.exists():
        command.extend(["--live-intelligence", str(live_intelligence_path)])
    completed = subprocess.run(
        command,
        cwd=str(radar_repo),
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    stdout = completed.stdout.strip()
    if not stdout:
        raise RuntimeError("Demand-to-MVP Radar returned empty output")
    return json.loads(stdout)


def _radar_python_command(radar_repo: Path) -> list[str]:
    python_bin = os.environ.get("RADAR_PYTHON", "").strip()
    if python_bin:
        return [python_bin]
    repo_venv_python = radar_repo / ".venv" / "bin" / "python"
    if repo_venv_python.exists():
        return [str(repo_venv_python)]
    raise FileNotFoundError(f"Demand-to-MVP Radar local venv not found: {repo_venv_python}")


def _deliver_result(result: MvpWeeklyPipelineResult) -> str | None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
    if not token or not chat_id:
        LOGGER.info("MVP weekly delivery skipped because Telegram owner credentials are missing")
        return None

    telegraph_url = _publish_mvp_telegraph(result)
    notification = _write_mvp_operator_message(result)
    if telegraph_url:
        notification = f"{notification}\n\nПолный audit-отчет: {telegraph_url}"
    send_text(
        chat_id=chat_id,
        text=notification[:4096],
        token=token,
        parse_mode=None,
        reply_markup=build_artifact_feedback_markup(result.week_label, "mvp_weekly"),
    )
    if result.report_path:
        send_document(
            chat_id=chat_id,
            file_path=result.report_path,
            caption=f"MVP of the Week {result.week_label}",
            token=token,
        )
    return telegraph_url


def _write_mvp_operator_message(result: MvpWeeklyPipelineResult) -> str:
    live = (result.source_counts or {}).get("live_intelligence")
    notification = build_mvp_message(
        week_label=result.week_label,
        title=result.selected_title or "No candidate selected",
        status=_notification_status(result),
        recommendation=result.recommendation or result.radar_status,
        score=result.score,
        source_mix=result.selected_source_mix or {},
        live_intelligence=live if isinstance(live, dict) else {},
    )
    write_weekly_message(result.week_label, "mvp", notification)
    return notification


def _notification_status(result: MvpWeeklyPipelineResult) -> str:
    status = result.dossier_status or result.recommendation or result.radar_status
    recommendation = (result.recommendation or "").strip().lower()
    normalized_status = status.strip().lower()
    if (
        recommendation in NON_BUILD_READY_RECOMMENDATIONS
        and normalized_status in BUILD_READY_STATUSES
    ):
        return "reject" if recommendation == "reject" else "investigate"
    return status


def _publish_mvp_telegraph(result: MvpWeeklyPipelineResult) -> str | None:
    if not result.report_path:
        return None
    report_path = Path(result.report_path)
    if not report_path.exists():
        LOGGER.warning("MVP weekly Telegraph publish skipped; report missing: %s", report_path)
        return None
    try:
        markdown = report_path.read_text(encoding="utf-8")
        html = render_report_html(markdown)
        title = f"MVP of the Week {result.week_label}"
        return publish_article(title=title, html_content=html)
    except Exception:
        LOGGER.warning("MVP weekly Telegraph publish failed", exc_info=True)
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_dict(value: object) -> dict[str, object] | None:
    return value if isinstance(value, dict) else None


def _optional_str_dict(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): str(item) for key, item in value.items()}


def source_mix_summary(result: MvpWeeklyPipelineResult) -> str:
    counts = result.source_counts or {}
    selected_mix = result.selected_source_mix or {}
    readiness = _optional_str(selected_mix.get("readiness"))
    telegram_count = _optional_int(counts.get("telegram_seed_evidence_count"))
    if telegram_count is None:
        telegram_count = _optional_int(counts.get("telegram_research_agent"))
    external_count = _optional_int(counts.get("external_evidence_count"))
    external_types = counts.get("external_source_types") or ()
    if isinstance(external_types, str):
        external_text = external_types
    elif isinstance(external_types, (list, tuple)):
        external_text = ", ".join(str(item) for item in external_types)
    else:
        external_text = ""
    skipped = counts.get("skipped_sources") or ()
    if isinstance(skipped, str):
        skipped_text = skipped
    elif isinstance(skipped, (list, tuple)):
        skipped_text = ", ".join(str(item) for item in skipped)
    else:
        skipped_text = ""
    parts = [
        f"readiness={readiness or 'unknown'}",
        f"telegram={telegram_count if telegram_count is not None else 'unknown'}",
        f"external={external_count if external_count is not None else 'unknown'}",
        f"external_types={external_text or 'none'}",
    ]
    reddit_status = _optional_str(selected_mix.get("reddit_api_status"))
    if reddit_status:
        parts.append(f"reddit={reddit_status}")
    missing_credentials = selected_mix.get("missing_credentials") or ()
    if isinstance(missing_credentials, str):
        missing_text = missing_credentials
    elif isinstance(missing_credentials, (list, tuple)):
        missing_text = ", ".join(str(item) for item in missing_credentials)
    else:
        missing_text = ""
    if missing_text:
        parts.append(f"missing_credentials={missing_text}")
    if skipped_text:
        parts.append(f"skipped={skipped_text}")
    source_errors = result.source_errors or {}
    if source_errors:
        parts.append("source_errors=" + ", ".join(sorted(source_errors)))
    return "Source mix: " + "; ".join(parts) + "."


def live_intelligence_summary(result: MvpWeeklyPipelineResult) -> str:
    live = (result.source_counts or {}).get("live_intelligence")
    if not isinstance(live, dict):
        return "Live intelligence: not supplied."
    events = _optional_int(live.get("events_scanned"))
    repeated = _optional_int(live.get("repeated_claim_count"))
    pathway = live.get("pathway")
    pathway_status = ""
    if isinstance(pathway, dict):
        pathway_status = str(pathway.get("status") or "")
    parts = [
        f"events={events if events is not None else 0}",
        f"repeated_claims={repeated if repeated is not None else 0}",
        "context_only=true",
    ]
    if pathway_status:
        parts.append(f"pathway={pathway_status}")
    return "Live intelligence: " + "; ".join(parts) + "."
