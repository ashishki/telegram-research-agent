import subprocess
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable


DIGEST_TIMER_NAME = "telegram-digest.timer"
DIGEST_OUTPUT_RELATIVE_PATH = Path("data") / "output"
DIGEST_SCHEDULE_DESCRIPTION = "Mon 05:00 UTC / 09:00 Asia/Tbilisi + 2h grace"
DIGEST_SCHEDULE_WEEKDAY = 0
DIGEST_SCHEDULE_HOUR_UTC = 5
DIGEST_SCHEDULE_MINUTE_UTC = 0
DIGEST_SCHEDULE_GRACE_HOURS = 2
ROOT_OWNED_REPORT_LIMIT = 20


@dataclass(frozen=True)
class TimerHealth:
    name: str
    state: str
    checked: bool
    detail: str = ""

    @property
    def is_active(self) -> bool:
        return self.checked and self.state == "active"

    @property
    def is_failure(self) -> bool:
        return self.checked and not self.is_active


@dataclass(frozen=True)
class WeeklyDeliveryHealth:
    week_label: str
    deadline_utc: datetime
    digest_due: bool
    db_digest_present: bool | None
    artifact_present: bool
    artifact_path: Path
    last_digest_week: str | None
    timer: TimerHealth
    output_root: Path
    root_owned_paths: tuple[str, ...]
    root_owned_total: int
    root_owned_scan_errors: tuple[str, ...] = ()

    @property
    def failure_reasons(self) -> tuple[str, ...]:
        failures: list[str] = []
        if self.timer.is_failure:
            failures.append("digest_timer_inactive")
        if self.digest_due and self.db_digest_present is False and not self.artifact_present:
            failures.append("current_week_digest_missing")
        if self.root_owned_total > 0:
            failures.append("root_owned_output_paths")
        return tuple(failures)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _week_label_for(value: datetime) -> str:
    year, week, _ = value.isocalendar()
    return f"{year}-W{week:02d}"


def _deadline_for_week(week_label: str) -> datetime:
    year_str, week_str = week_label.split("-W", maxsplit=1)
    scheduled_date = date.fromisocalendar(int(year_str), int(week_str), DIGEST_SCHEDULE_WEEKDAY + 1)
    scheduled_at = datetime.combine(
        scheduled_date,
        time(DIGEST_SCHEDULE_HOUR_UTC, DIGEST_SCHEDULE_MINUTE_UTC),
        tzinfo=timezone.utc,
    )
    return scheduled_at + timedelta(hours=DIGEST_SCHEDULE_GRACE_HOURS)


def inspect_digest_timer(
    timer_name: str = DIGEST_TIMER_NAME,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> TimerHealth:
    try:
        result = runner(
            ["systemctl", "is-active", timer_name],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except FileNotFoundError:
        return TimerHealth(name=timer_name, state="unavailable", checked=False, detail="systemctl not found")
    except Exception as exc:
        return TimerHealth(name=timer_name, state="unavailable", checked=False, detail=str(exc))

    stdout = (result.stdout or "").strip()
    stderr = " ".join((result.stderr or "").split())
    if "System has not been booted with systemd" in stderr or "Failed to connect to bus" in stderr:
        return TimerHealth(name=timer_name, state="unavailable", checked=False, detail=stderr[:220])

    state = stdout.splitlines()[0].strip() if stdout else "active" if result.returncode == 0 else "unknown"
    detail = stderr[:220] if result.returncode != 0 and stderr else ""
    return TimerHealth(name=timer_name, state=state, checked=True, detail=detail)


def _path_uid(path: Path) -> int:
    return path.lstat().st_uid


def _display_path(path: Path, *, relative_to: Path | None = None) -> str:
    if relative_to is not None:
        try:
            return str(path.relative_to(relative_to))
        except ValueError:
            pass
    return str(path)


def find_root_owned_output_paths(
    output_root: Path,
    *,
    relative_to: Path | None = None,
    limit: int = ROOT_OWNED_REPORT_LIMIT,
) -> tuple[tuple[str, ...], int, tuple[str, ...]]:
    if not output_root.exists():
        return (), 0, ()

    found: list[str] = []
    errors: list[str] = []
    total = 0
    try:
        paths = output_root.rglob("*")
        for path in paths:
            if not path.is_file():
                continue
            try:
                is_root_owned = _path_uid(path) == 0
            except OSError as exc:
                errors.append(f"{_display_path(path, relative_to=relative_to)}: {exc}")
                continue
            if not is_root_owned:
                continue
            total += 1
            if len(found) < limit:
                found.append(_display_path(path, relative_to=relative_to))
    except OSError as exc:
        errors.append(f"{_display_path(output_root, relative_to=relative_to)}: {exc}")
    return tuple(found), total, tuple(errors)


def _fetch_digest_presence(connection, week_label: str) -> tuple[bool, str | None]:
    row = connection.execute(
        "SELECT week_label FROM digests WHERE week_label = ? LIMIT 1",
        (week_label,),
    ).fetchone()
    last_row = connection.execute(
        "SELECT week_label FROM digests ORDER BY week_label DESC LIMIT 1",
    ).fetchone()
    last_week = str(last_row[0]) if last_row else None
    return row is not None, last_week


def build_weekly_delivery_health(
    *,
    connection=None,
    project_root: Path,
    now: datetime | None = None,
    timer_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> WeeklyDeliveryHealth:
    current = now or _utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    week_label = _week_label_for(current)
    deadline = _deadline_for_week(week_label)
    output_root = project_root / DIGEST_OUTPUT_RELATIVE_PATH
    artifact_path = output_root / "digests" / f"{week_label}.md"
    db_digest_present: bool | None = None
    last_digest_week: str | None = None
    if connection is not None:
        db_digest_present, last_digest_week = _fetch_digest_presence(connection, week_label)

    root_owned_paths, root_owned_total, root_owned_errors = find_root_owned_output_paths(
        output_root,
        relative_to=project_root,
    )
    return WeeklyDeliveryHealth(
        week_label=week_label,
        deadline_utc=deadline,
        digest_due=current >= deadline,
        db_digest_present=db_digest_present,
        artifact_present=artifact_path.exists(),
        artifact_path=artifact_path,
        last_digest_week=last_digest_week,
        timer=inspect_digest_timer(runner=timer_runner),
        output_root=output_root,
        root_owned_paths=root_owned_paths,
        root_owned_total=root_owned_total,
        root_owned_scan_errors=root_owned_errors,
    )


def _state(value: bool | None) -> str:
    if value is None:
        return "not_checked"
    return "present" if value else "missing"


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def format_weekly_delivery_health(
    health: WeeklyDeliveryHealth,
    *,
    relative_to: Path | None = None,
) -> list[str]:
    artifact_path = _display_path(health.artifact_path, relative_to=relative_to)
    output_root = _display_path(health.output_root, relative_to=relative_to)
    lines = [
        (
            "weekly_delivery: "
            f"week={health.week_label} due={'yes' if health.digest_due else 'no'} "
            f"deadline_utc={_format_utc(health.deadline_utc)} "
            f"schedule={DIGEST_SCHEDULE_DESCRIPTION}"
        ),
        (
            "weekly_delivery_digest: "
            f"db={_state(health.db_digest_present)} "
            f"artifact={'present' if health.artifact_present else 'missing'} "
            f"artifact_path={artifact_path} "
            f"last_digest={health.last_digest_week or 'none'}"
        ),
        (
            "weekly_delivery_timer: "
            f"timer={health.timer.name} state={health.timer.state} "
            f"checked={'yes' if health.timer.checked else 'no'}"
        ),
        f"root_owned_output_paths: count={health.root_owned_total} checked={output_root}",
    ]
    if health.timer.detail:
        lines.append(f"weekly_delivery_timer_detail: {health.timer.detail}")
    if health.timer.is_failure:
        lines.append(f"WARNING: {health.timer.name} is {health.timer.state}; weekly reports may not run")
    if health.digest_due and health.db_digest_present is False and not health.artifact_present:
        lines.append(
            f"WARNING: current-week digest missing after scheduled window week={health.week_label}"
        )
    elif health.db_digest_present is False and health.artifact_present:
        lines.append(f"WARNING: current-week digest artifact exists but DB row is missing week={health.week_label}")
    elif health.db_digest_present is True and not health.artifact_present:
        lines.append(f"WARNING: current-week digest DB row exists but Markdown artifact is missing week={health.week_label}")
    if health.root_owned_total > 0:
        sample = ", ".join(health.root_owned_paths) if health.root_owned_paths else "sample unavailable"
        lines.append(f"WARNING: root-owned output files found count={health.root_owned_total} sample={sample}")
    for error in health.root_owned_scan_errors:
        lines.append(f"WARNING: output ownership scan error {error}")
    if health.failure_reasons:
        lines.append(f"weekly_delivery_failures: {', '.join(health.failure_reasons)}")
    return lines
