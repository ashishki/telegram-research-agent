import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from shutil import which

from bot.telegram_delivery import send_document, send_text
from config.settings import PROJECT_ROOT, Settings
from output.opportunity_seed_export import export_opportunity_seeds


LOGGER = logging.getLogger(__name__)
DEFAULT_RADAR_REPO = PROJECT_ROOT.parent / "Demand-to-MVP-Radar"
DEFAULT_RADAR_PYTHON = Path("/srv/openclaw-you/venv/bin/python3")


@dataclass(frozen=True)
class MvpWeeklyPipelineResult:
    week_label: str
    seed_path: str
    seed_count: int
    radar_status: str
    report_path: str | None
    json_path: str | None
    selected_title: str | None
    recommendation: str | None
    score: int | None


def run_mvp_weekly_pipeline(
    settings: Settings,
    *,
    days: int = 7,
    limit: int = 80,
    include_channels: tuple[str, ...] = (),
    run_id: str | None = None,
    deliver: bool = True,
) -> MvpWeeklyPipelineResult:
    seed_export = export_opportunity_seeds(
        settings,
        days=days,
        limit=limit,
        include_channels=include_channels,
    )
    effective_run_id = run_id or f"mvp-weekly-{seed_export.week_label}"
    radar_payload = _run_radar(
        seed_path=Path(seed_export.output_path),
        run_id=effective_run_id,
    )
    result = MvpWeeklyPipelineResult(
        week_label=seed_export.week_label,
        seed_path=seed_export.output_path,
        seed_count=seed_export.seed_count,
        radar_status=str(radar_payload.get("status") or "unknown"),
        report_path=_optional_str(radar_payload.get("report_path")),
        json_path=_optional_str(radar_payload.get("json_path")),
        selected_title=_optional_str(radar_payload.get("selected_title")),
        recommendation=_optional_str(radar_payload.get("recommendation")),
        score=_optional_int(radar_payload.get("score")),
    )
    if deliver:
        _deliver_result(result)
    return result


def _run_radar(*, seed_path: Path, run_id: str) -> dict[str, object]:
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
    env.setdefault("UV_CACHE_DIR", str(data_dir / "uv-cache"))
    command = [
        *_radar_python_command(),
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


def _radar_python_command() -> list[str]:
    python_bin = os.environ.get("RADAR_PYTHON", "").strip()
    if python_bin:
        return [python_bin]
    uv_bin = os.environ.get("RADAR_UV_BIN", "").strip() or which("uv")
    if uv_bin:
        return [
            uv_bin,
            "run",
            "--no-project",
            "--python",
            os.environ.get("RADAR_PYTHON_VERSION", "3.12"),
            "--with",
            "pydantic>=2,<3",
            "python",
        ]
    return [str(DEFAULT_RADAR_PYTHON if DEFAULT_RADAR_PYTHON.exists() else Path(sys.executable))]


def _deliver_result(result: MvpWeeklyPipelineResult) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
    if not token or not chat_id:
        LOGGER.info("MVP weekly delivery skipped because Telegram owner credentials are missing")
        return

    title = result.selected_title or "No candidate selected"
    score_suffix = f", score {result.score}/100" if result.score is not None else ""
    notification = (
        f"MVP of the Week {result.week_label} is ready.\n"
        f"{title}\n"
        f"Recommendation: {result.recommendation or result.radar_status}{score_suffix}.\n"
        f"Seeds exported: {result.seed_count}."
    )
    send_text(chat_id=chat_id, text=notification, token=token, parse_mode=None)
    if result.report_path:
        send_document(
            chat_id=chat_id,
            file_path=result.report_path,
            caption=f"MVP of the Week {result.week_label}",
            token=token,
        )


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
