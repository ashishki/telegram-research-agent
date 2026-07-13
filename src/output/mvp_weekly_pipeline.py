import json
import logging
import os
import subprocess
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from delivery.telegraph import publish_article
from bot.callbacks import build_artifact_feedback_markup
from bot.telegram_delivery import send_document, send_text
from config.settings import PROJECT_ROOT, Settings
from output.opportunity_seed_export import export_opportunity_seeds
from output.market_context_lens import summarize_market_context_lens
from output.market_pain_intelligence import summarize_market_pain_pack
from output.render_report import render_report_html
from output.reporting_period import (
    PARTIAL_ISO_WEEK,
    TRAILING_SEVEN_DAYS,
    ReportingPeriod,
    format_period_display_label,
    resolve_reporting_period,
)
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
    validation_adapter_status: dict[str, object] | None = None
    matched_external_evidence: list[dict[str, object]] | None = None
    missing_evidence_by_category: dict[str, object] | None = None
    decision_change_action: dict[str, object] | None = None
    telegraph_url: str | None = None
    source_counts: dict[str, object] | None = None
    source_errors: dict[str, str] | None = None
    live_intelligence_path: str | None = None
    knowledge_thread_count: int = 0
    knowledge_threads: list[dict] | None = None
    market_pack_path: str | None = None
    market_pain_pack: dict | None = None
    market_lens_path: str | None = None
    market_baseline_path: str | None = None
    market_delta_path: str | None = None
    market_context_lens: dict | None = None
    run_date: str = ""
    generated_at: str = ""
    reporting_week: str = ""
    period_mode: str = ""
    analysis_period_start: str = ""
    analysis_period_end: str = ""
    radar_run_id: str = ""


def run_mvp_weekly_pipeline(
    settings: Settings,
    *,
    days: int | None = None,
    week_label: str | None = None,
    period_mode: str | None = None,
    reporting_period: ReportingPeriod | None = None,
    now: datetime | None = None,
    limit: int = 80,
    include_channels: tuple[str, ...] = (),
    market_context_days: int = 84,
    force_market_baseline: bool = False,
    seed_output_path: Path | None = None,
    run_id: str | None = None,
    radar_run_id: str | None = None,
    deliver: bool = True,
    emit_operator_outputs: bool = True,
    with_live_source_index: bool = False,
    live_intelligence_path: Path | str | None = None,
    live_index_days: int | None = None,
    backfill_live_source_events: bool = False,
) -> MvpWeeklyPipelineResult:
    require_live_period_identity = reporting_period is not None
    if reporting_period is not None:
        if (
            days is not None
            or week_label is not None
            or period_mode is not None
            or now is not None
        ):
            raise ValueError(
                "reporting_period cannot be combined with days, week_label, period_mode, or now"
            )
        period = reporting_period
    else:
        if days is not None and int(days) != 7:
            raise ValueError("rolling MVP weekly mode supports exactly seven days")
        if days is not None and period_mode is not None:
            raise ValueError("rolling --days cannot be combined with another period mode")
        if week_label is not None and days is not None:
            raise ValueError("--week cannot be combined with rolling --days")
        resolved_mode = period_mode
        if days is not None and resolved_mode is None and week_label is None:
            resolved_mode = TRAILING_SEVEN_DAYS
        period = resolve_reporting_period(
            now,
            week_label=week_label,
            period_mode=resolved_mode,
        )
    period_fields = period.to_dict()
    if run_id is not None and radar_run_id is not None and run_id != radar_run_id:
        raise ValueError("run_id and radar_run_id must match when both are provided")
    seed_export = export_opportunity_seeds(
        settings,
        reporting_period=period,
        limit=limit,
        output_path=seed_output_path,
        include_channels=include_channels,
        market_context_days=market_context_days,
        force_market_baseline=force_market_baseline,
    )
    effective_run_id = radar_run_id or run_id or f"mvp-weekly-{seed_export.week_label}"
    live_path = _prepare_live_intelligence_path(
        settings,
        explicit_path=live_intelligence_path,
        enabled=with_live_source_index,
        reporting_period=period,
        requested_days=live_index_days,
        backfill=backfill_live_source_events,
        require_period_identity=require_live_period_identity,
    )
    radar_payload = _run_radar(
        seed_path=Path(seed_export.output_path),
        run_id=effective_run_id,
        live_intelligence_path=live_path,
    )
    result_run_id = radar_payload.get("run_id")
    if not isinstance(result_run_id, str) or result_run_id != effective_run_id:
        raise RuntimeError(
            "Demand-to-MVP Radar result run_id does not match the requested radar_run_id"
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
        radar_run_id=result_run_id,
        selected_source_mix=_optional_dict(radar_payload.get("selected_source_mix")),
        validation_adapter_status=_optional_dict(radar_payload.get("validation_adapter_status")),
        matched_external_evidence=_optional_dict_list(radar_payload.get("matched_external_evidence")),
        missing_evidence_by_category=_optional_dict(radar_payload.get("missing_evidence_by_category")),
        decision_change_action=_optional_dict(radar_payload.get("decision_change_action")),
        source_counts=_optional_dict(radar_payload.get("source_counts")),
        source_errors=_optional_str_dict(radar_payload.get("source_errors")),
        live_intelligence_path=str(live_path) if live_path is not None else None,
        knowledge_thread_count=seed_export.knowledge_thread_count,
        knowledge_threads=seed_export.knowledge_threads or [],
        market_pack_path=seed_export.market_pack_path,
        market_pain_pack=seed_export.market_pain_pack or {},
        market_lens_path=seed_export.market_lens_path,
        market_baseline_path=seed_export.market_baseline_path,
        market_delta_path=seed_export.market_delta_path,
        market_context_lens=seed_export.market_context_lens or {},
        run_date=period_fields["run_date"],
        generated_at=period_fields["generated_at"],
        reporting_week=period_fields["reporting_week"],
        period_mode=period_fields["period_mode"],
        analysis_period_start=period_fields["analysis_period_start"],
        analysis_period_end=period_fields["analysis_period_end"],
    )
    if emit_operator_outputs:
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
    reporting_period: ReportingPeriod,
    requested_days: int | None,
    backfill: bool,
    require_period_identity: bool = False,
) -> Path | None:
    from output.live_source_intelligence import (
        build_live_source_intelligence_snapshot,
        load_live_source_intelligence,
    )

    if explicit_path is not None:
        path = Path(explicit_path)
        if not path.exists():
            raise FileNotFoundError(f"Live intelligence snapshot not found: {path}")
        payload = load_live_source_intelligence(path)
        window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
        start = payload.get("analysis_period_start") or window.get("start")
        end = payload.get("analysis_period_end") or window.get("end")
        if (
            _utc_timestamp(start) != reporting_period.analysis_period_start
            or _utc_timestamp(end) != reporting_period.analysis_period_end
        ):
            raise ValueError("live intelligence snapshot does not match the resolved reporting period")
        if require_period_identity:
            expected = reporting_period.to_dict()
            for field in ("reporting_week", "week_label", "period_mode"):
                if str(payload.get(field) or "") != expected[field]:
                    raise ValueError(
                        "live intelligence snapshot does not match the resolved "
                        f"reporting period: {field}"
                    )
        return path
    if not enabled:
        return None
    period_seconds = (
        reporting_period.analysis_period_end - reporting_period.analysis_period_start
    ).total_seconds()
    if requested_days is not None and period_seconds != max(1, int(requested_days)) * 86_400:
        raise ValueError("--live-index-days must match the resolved reporting period")
    from output.source_events import backfill_recent_source_events

    if backfill:
        import sqlite3

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            backfill_recent_source_events(
                connection,
                analysis_period_start=reporting_period.analysis_period_start,
                analysis_period_end=reporting_period.analysis_period_end,
            )
    result = build_live_source_intelligence_snapshot(reporting_period=reporting_period)
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
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Demand-to-MVP Radar returned malformed JSON output") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Demand-to-MVP Radar output must be a JSON object")
    if payload.get("run_id") != run_id:
        raise RuntimeError(
            "Demand-to-MVP Radar result run_id does not match the requested run_id"
        )

    json_path_value = payload.get("json_path")
    if not isinstance(json_path_value, str) or not json_path_value.strip():
        raise RuntimeError("Demand-to-MVP Radar result is missing json_path")
    json_path = Path(json_path_value.strip())
    if not json_path.is_absolute():
        json_path = radar_repo / json_path
    if not json_path.is_file():
        raise RuntimeError(f"Demand-to-MVP Radar JSON result not found: {json_path}")
    try:
        result_payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Demand-to-MVP Radar JSON result is malformed: {json_path}") from exc
    if not isinstance(result_payload, dict):
        raise RuntimeError("Demand-to-MVP Radar JSON result must be an object")
    result_record = result_payload.get("result")
    if not isinstance(result_record, dict) or result_record.get("run_id") != run_id:
        raise RuntimeError(
            "Demand-to-MVP Radar JSON result.run_id does not match the requested run_id"
        )
    return payload


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
            caption=_mvp_artifact_title(result),
            token=token,
        )
    return telegraph_url


def _write_mvp_operator_message(result: MvpWeeklyPipelineResult) -> str:
    live = (result.source_counts or {}).get("live_intelligence")
    notification = build_mvp_message(
        week_label=_period_display_label(result),
        title=result.selected_title or "No candidate selected",
        status=_notification_status(result),
        recommendation=result.recommendation or result.radar_status,
        score=result.score,
        source_mix=result.selected_source_mix or {},
        live_intelligence=live if isinstance(live, dict) else {},
    )
    if result.knowledge_thread_count:
        labels = ", ".join(
            str(item.get("title") or item.get("slug") or "untitled")
            for item in (result.knowledge_threads or [])[:3]
        )
        notification = f"{notification}\nKnowledge Threads в seed-контексте: {labels}"
    if result.market_pain_pack is not None:
        notification = f"{notification}\n{summarize_market_pain_pack(result.market_pain_pack)}"
    if result.market_context_lens is not None:
        notification = f"{notification}\n{summarize_market_context_lens(result.market_context_lens)}"
    validation_line = _validation_gate_notification(result)
    if validation_line:
        notification = f"{notification}\n{validation_line}"
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
        title = _mvp_artifact_title(result)
        return publish_article(title=title, html_content=html)
    except Exception:
        LOGGER.warning("MVP weekly Telegraph publish failed", exc_info=True)
        return None


def _period_display_label(result: MvpWeeklyPipelineResult) -> str:
    return format_period_display_label(
        period_mode=result.period_mode,
        reporting_week=result.reporting_week or result.week_label,
        analysis_period_start=result.analysis_period_start,
        analysis_period_end=result.analysis_period_end,
    )


def _mvp_artifact_title(result: MvpWeeklyPipelineResult) -> str:
    if result.period_mode in {TRAILING_SEVEN_DAYS, PARTIAL_ISO_WEEK}:
        return f"MVP — {_period_display_label(result)}"
    return f"MVP of the Week {result.week_label}"


def _utc_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


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


def _optional_dict_list(value: object) -> list[dict[str, object]] | None:
    if not isinstance(value, list):
        return None
    return [item for item in value if isinstance(item, dict)]


def _optional_str_dict(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): str(item) for key, item in value.items()}


def _validation_gate_notification(result: MvpWeeklyPipelineResult) -> str:
    action = result.decision_change_action or {}
    matched_count = action.get("matched_external_evidence_count")
    if matched_count is None:
        matched_count = sum(
            1
            for item in (result.matched_external_evidence or [])
            if bool(item.get("supports_gate")) and bool(item.get("decision_grade", True))
        )
    source_types = action.get("matched_external_source_types")
    if isinstance(source_types, list):
        source_type_text = ", ".join(str(item) for item in source_types if str(item).strip())
    else:
        source_type_text = ""
    next_query = str(action.get("next_query") or "").strip()
    next_action = str(action.get("next_validation_action") or "").strip()
    if next_query:
        return (
            "Валидация: "
            f"{matched_count} matched external evidence; types={source_type_text or 'none'}; "
            f"next query: {next_query}"
        )
    if next_action:
        return f"Валидация: {matched_count} matched external evidence; next action: {next_action}"
    if result.validation_adapter_status:
        statuses = ", ".join(
            f"{key}={value.get('status') if isinstance(value, dict) else 'unknown'}"
            for key, value in list(result.validation_adapter_status.items())[:4]
        )
        return f"Валидация: adapter status {statuses}"
    return ""


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
