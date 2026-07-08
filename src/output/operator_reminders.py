from __future__ import annotations

import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bot.callbacks import build_reminder_digest_markup
from bot.telegram_delivery import send_text
from config.settings import Settings


LOGGER = logging.getLogger(__name__)
DEFAULT_REMINDER_HOUR = 10
DEFAULT_TIMEZONE = "Asia/Tbilisi"
RELATIVE_RE = re.compile(
    r"(?:через|in)\s+(\d+)\s*(минут[уы]?|мин|m|час(?:а|ов)?|ч|h|д(?:ень|ня|ней)?|дн|d)",
    re.IGNORECASE,
)
ABSOLUTE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{1,2}:\d{2}))?")
TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")


@dataclass(frozen=True)
class ParsedReminder:
    due_at: str
    text: str
    reminder_type: str
    timezone_name: str


def create_reminder(
    connection: sqlite3.Connection,
    *,
    due_at: str,
    text: str,
    reminder_type: str = "general",
    source_text: str | None = None,
    recorded_by: str = "operator",
) -> dict:
    clean_text = " ".join(str(text or "").split())
    if not clean_text:
        raise ValueError("Reminder text is required")
    reminder_type = _normalize_reminder_type(reminder_type, clean_text)
    created_at = _utc_now()
    cursor = connection.execute(
        """
        INSERT INTO operator_reminders (
            due_at, text, reminder_type, source_text, status, created_at, recorded_by
        ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
        """,
        (due_at, clean_text, reminder_type, source_text, created_at, recorded_by),
    )
    connection.commit()
    return {
        "id": int(cursor.lastrowid),
        "due_at": due_at,
        "text": clean_text,
        "reminder_type": reminder_type,
        "status": "pending",
        "created_at": created_at,
    }


def parse_reminder_request(raw_text: str, *, now: datetime | None = None) -> ParsedReminder:
    text = " ".join(str(raw_text or "").split())
    if not text:
        raise ValueError("Reminder request is empty")
    timezone_name = get_reminder_timezone_name()
    tz = _load_timezone(timezone_name)
    local_now = (now or datetime.now(timezone.utc)).astimezone(tz)
    due_local, remaining = _parse_due_time(text, local_now)
    reminder_text = _clean_reminder_text(remaining or text)
    if not reminder_text:
        reminder_text = text
    return ParsedReminder(
        due_at=due_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        text=reminder_text,
        reminder_type=_normalize_reminder_type("general", reminder_text),
        timezone_name=timezone_name,
    )


def list_pending_reminders(connection: sqlite3.Connection, *, limit: int = 10) -> list[dict]:
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT id, due_at, text, reminder_type, status, created_at, last_prompted_at
        FROM operator_reminders
        WHERE status = 'pending'
        ORDER BY due_at ASC, id ASC
        LIMIT ?
        """,
        (max(1, min(50, int(limit))),),
    ).fetchall()
    return [dict(row) for row in rows]


def cancel_reminder(connection: sqlite3.Connection, *, reminder_id: int) -> dict | None:
    now = _utc_now()
    row = connection.execute(
        """
        SELECT id, due_at, text, reminder_type, status
        FROM operator_reminders
        WHERE id = ?
        """,
        (reminder_id,),
    ).fetchone()
    if row is None:
        return None
    connection.execute(
        """
        UPDATE operator_reminders
        SET status = 'canceled', canceled_at = ?
        WHERE id = ? AND status = 'pending'
        """,
        (now, reminder_id),
    )
    connection.commit()
    return dict(row)


def send_daily_reminder_digest(
    settings: Settings,
    *,
    now: datetime | None = None,
    limit: int = 10,
    force: bool = False,
) -> dict:
    timezone_name = get_reminder_timezone_name()
    tz = _load_timezone(timezone_name)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    local_now = current.astimezone(tz)
    cutoff_local = local_now.replace(hour=23, minute=59, second=59, microsecond=999999)
    cutoff = cutoff_local.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {
            "status": "missing",
            "prompted": 0,
            "message": "Telegram bot credentials are missing.",
        }

    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, due_at, text, reminder_type, last_prompted_at
            FROM operator_reminders
            WHERE status = 'pending' AND due_at <= ?
            ORDER BY due_at ASC, id ASC
            LIMIT ?
            """,
            (cutoff, max(1, min(20, int(limit)))),
        ).fetchall()
        due_rows = [
            dict(row)
            for row in rows
            if force or _local_date(row["last_prompted_at"], tz) != local_now.date().isoformat()
        ]
        if not due_rows:
            return {
                "status": "empty",
                "prompted": 0,
                "message": "No pending reminders are due for today's digest.",
            }

        message = format_daily_reminder_digest(due_rows, now=local_now, timezone_name=timezone_name)
        send_text(
            chat_id=chat_id,
            text=message,
            token=token,
            parse_mode=None,
            reply_markup=build_reminder_digest_markup(due_rows),
        )
        prompted_at = current.isoformat().replace("+00:00", "Z")
        for row in due_rows:
            connection.execute(
                """
                UPDATE operator_reminders
                SET last_prompted_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (prompted_at, row["id"]),
            )
        connection.commit()
    return {
        "status": "ok",
        "prompted": len(due_rows),
        "message": f"Sent daily reminder digest with {len(due_rows)} item(s).",
    }


def format_daily_reminder_digest(
    rows: Sequence[dict],
    *,
    now: datetime | None = None,
    timezone_name: str | None = None,
) -> str:
    timezone_name = _valid_timezone_name(timezone_name or get_reminder_timezone_name())
    tz = _load_timezone(timezone_name)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_current = current.astimezone(tz)
    date_label = f"{local_current.strftime('%Y-%m-%d')} {timezone_name}"
    lines = [
        "Hermes: дневной чек-ин",
        date_label,
        "",
    ]
    for index, row in enumerate(rows, start=1):
        reminder_type = _human_reminder_type(str(row.get("reminder_type") or "general"))
        text = " ".join(str(row.get("text") or "").split())
        lines.append(f"{index}. [{reminder_type}] {text}")
        if row.get("due_at"):
            lines.append(f"   Когда: {format_reminder_due_at(str(row['due_at']), timezone_name=timezone_name)}")
    lines.extend(
        [
            "",
            "Отметь по каждому пункту: сделал / не сделал.",
        ]
    )
    return "\n".join(lines)


def _parse_due_time(text: str, local_now: datetime) -> tuple[datetime, str]:
    relative = RELATIVE_RE.search(text)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2).casefold()
        if unit.startswith(("мин", "m")):
            due = local_now + timedelta(minutes=amount)
        elif unit.startswith(("час", "ч", "h")):
            due = local_now + timedelta(hours=amount)
        else:
            due = local_now + timedelta(days=amount)
        return due, _remove_match(text, relative)

    absolute = ABSOLUTE_RE.search(text)
    if absolute:
        date_part = absolute.group(1)
        time_part = absolute.group(2) or f"{DEFAULT_REMINDER_HOUR:02d}:00"
        hour, minute = _parse_time_parts(time_part)
        year, month, day = [int(part) for part in date_part.split("-")]
        due = datetime(year, month, day, hour, minute, tzinfo=local_now.tzinfo)
        return due, _remove_match(text, absolute)

    lowered = text.casefold()
    if "завтра" in lowered or "tomorrow" in lowered:
        base = local_now + timedelta(days=1)
        hour, minute = _find_time(text) or (DEFAULT_REMINDER_HOUR, 0)
        due = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return due, _strip_words(text, ("завтра", "tomorrow"))

    if "сегодня" in lowered or "today" in lowered:
        hour, minute = _find_time(text) or (local_now.hour + 1, local_now.minute)
        due = local_now.replace(hour=min(hour, 23), minute=minute, second=0, microsecond=0)
        if due <= local_now:
            due += timedelta(days=1)
        return due, _strip_words(text, ("сегодня", "today"))

    due = (local_now + timedelta(days=1)).replace(
        hour=DEFAULT_REMINDER_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )
    return due, text


def _clean_reminder_text(text: str) -> str:
    clean = text.strip(" .,:;-")
    for prefix in ("напомни", "напомнить", "remind me", "remind"):
        if clean.casefold().startswith(prefix):
            clean = clean[len(prefix):].strip(" .,:;-")
    return clean


def _normalize_reminder_type(raw_type: str, text: str) -> str:
    clean = str(raw_type or "").strip().lower()
    if clean in {"feedback", "action", "read_watch", "project", "mvp"}:
        return clean
    lowered = text.casefold()
    if any(term in lowered for term in ("фидбек", "feedback")):
        return "feedback"
    if any(term in lowered for term in ("почитать", "прочитать", "посмотреть", "watch", "read")):
        return "read_watch"
    if any(term in lowered for term in ("mvp", "радар")):
        return "mvp"
    if any(term in lowered for term in ("проект", "project")):
        return "project"
    if any(term in lowered for term in ("сделать", "action", "задач")):
        return "action"
    return "general"


def _human_reminder_type(reminder_type: str) -> str:
    return {
        "feedback": "feedback",
        "action": "action",
        "read_watch": "read/watch",
        "project": "project",
        "mvp": "MVP",
        "general": "task",
    }.get(reminder_type, "task")


def _local_date(value: str | None, tz: ZoneInfo) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(tz).date().isoformat()


def get_reminder_timezone_name() -> str:
    configured = os.environ.get("REMINDER_TIMEZONE", "").strip() or DEFAULT_TIMEZONE
    return _valid_timezone_name(configured)


def _valid_timezone_name(name: str | None) -> str:
    configured = str(name or "").strip() or DEFAULT_TIMEZONE
    try:
        ZoneInfo(configured)
    except (ZoneInfoNotFoundError, ValueError):
        return DEFAULT_TIMEZONE
    return configured


def format_reminder_due_at(iso_value: str, *, timezone_name: str | None = None) -> str:
    timezone_name = _valid_timezone_name(timezone_name or get_reminder_timezone_name())
    tz = _load_timezone(timezone_name)
    try:
        parsed = datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
    except ValueError:
        return str(iso_value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return f"{parsed.astimezone(tz).strftime('%Y-%m-%d %H:%M')} {timezone_name}"


def _load_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def _find_time(text: str) -> tuple[int, int] | None:
    match = TIME_RE.search(text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _parse_time_parts(value: str) -> tuple[int, int]:
    hour_raw, minute_raw = value.split(":", maxsplit=1)
    return max(0, min(23, int(hour_raw))), max(0, min(59, int(minute_raw)))


def _remove_match(text: str, match: re.Match[str]) -> str:
    return (text[: match.start()] + text[match.end() :]).strip()


def _strip_words(text: str, words: tuple[str, ...]) -> str:
    result = text
    for word in words:
        result = re.sub(rf"\b{re.escape(word)}\b", " ", result, flags=re.IGNORECASE)
    result = TIME_RE.sub(" ", result)
    return " ".join(result.split())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
