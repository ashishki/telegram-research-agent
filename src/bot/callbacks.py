import logging
import sqlite3
from datetime import datetime, timezone

from config.settings import Settings


LOGGER = logging.getLogger(__name__)

IDEA_CALLBACK_PREFIX = "idea"
_IDEA_ACTIONS: dict[str, tuple[str, str]] = {
    "done": ("acted_on", "Marked done from Telegram button"),
    "later": ("deferred", "Deferred from Telegram button"),
    "reject": ("rejected", "Rejected from Telegram button"),
    "interesting": ("deferred", "Marked interesting from Telegram button"),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_idea_feedback_markup(triage_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ сделал", "callback_data": f"{IDEA_CALLBACK_PREFIX}:{triage_id}:done"},
                {"text": "🕒 позже", "callback_data": f"{IDEA_CALLBACK_PREFIX}:{triage_id}:later"},
            ],
            [
                {"text": "⛔ отказал", "callback_data": f"{IDEA_CALLBACK_PREFIX}:{triage_id}:reject"},
                {"text": "🧠 интересно", "callback_data": f"{IDEA_CALLBACK_PREFIX}:{triage_id}:interesting"},
            ],
        ]
    }


def _project_name_from_title(title: str | None) -> str | None:
    if not title:
        return None
    import re

    match = re.match(r"\[(?:Implement|Build)\]\s+(.+?)\s+[—–-]\s+", str(title).strip(), re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def record_idea_callback(settings: Settings, callback_data: str) -> str:
    parts = callback_data.split(":")
    if len(parts) != 3 or parts[0] != IDEA_CALLBACK_PREFIX:
        raise ValueError("Unsupported callback")

    try:
        triage_id = int(parts[1])
    except ValueError as exc:
        raise ValueError("Invalid idea id") from exc

    action = parts[2]
    status_reason = _IDEA_ACTIONS.get(action)
    if status_reason is None:
        raise ValueError("Unsupported idea action")
    status, reason = status_reason

    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT id, week_label, title
            FROM insight_triage_records
            WHERE id = ?
            LIMIT 1
            """,
            (triage_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Idea not found: {triage_id}")

        connection.execute(
            """
            INSERT INTO decision_journal (
                decision_scope,
                subject_ref_type,
                subject_ref_id,
                project_name,
                status,
                reason,
                recorded_by,
                recorded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "insight",
                "insight_triage_id",
                str(triage_id),
                _project_name_from_title(row["title"]),
                status,
                reason,
                "telegram_button",
                _now_iso(),
            ),
        )
        connection.commit()

    return f"Записал: {status}"
