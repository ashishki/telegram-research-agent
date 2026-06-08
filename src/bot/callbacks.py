import logging
import sqlite3
from datetime import datetime, timezone

from config.settings import Settings
from db.artifact_feedback import record_artifact_feedback


LOGGER = logging.getLogger(__name__)

IDEA_CALLBACK_PREFIX = "idea"
ARTIFACT_CALLBACK_PREFIX = "art"
_IDEA_ACTIONS: dict[str, tuple[str, str]] = {
    "done": ("acted_on", "Marked done from Telegram button"),
    "later": ("deferred", "Deferred from Telegram button"),
    "reject": ("rejected", "Rejected from Telegram button"),
    "interesting": ("deferred", "Marked interesting from Telegram button"),
}
_ARTIFACT_TYPE_CODES = {
    "rb": "research_brief",
    "ii": "implementation_ideas",
    "mvp": "mvp_weekly",
    "sp": "study_plan",
    "ci": "channel_intelligence",
}
_ARTIFACT_TYPE_TO_CODE = {value: key for key, value in _ARTIFACT_TYPE_CODES.items()}
_ARTIFACT_ACTIONS: dict[str, tuple[str, str | None]] = {
    "u": ("useful", None),
    "w": ("weak", None),
    "n": ("noisy", None),
    "a": ("decision_impacting", None),
    "d": ("weak", "deferred_from_button"),
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


def build_artifact_feedback_markup(week_label: str, artifact_type: str) -> dict:
    clean_week = str(week_label).strip()
    type_code = _ARTIFACT_TYPE_TO_CODE.get(str(artifact_type).strip())
    if not clean_week or not type_code:
        raise ValueError("Unsupported artifact feedback target")

    def _button(text: str, action_code: str) -> dict:
        return {
            "text": text,
            "callback_data": f"{ARTIFACT_CALLBACK_PREFIX}:{clean_week}:{type_code}:{action_code}",
        }

    return {
        "inline_keyboard": [
            [
                _button("Useful", "u"),
                _button("Unclear", "w"),
                _button("Noise", "n"),
            ],
            [
                _button("Apply", "a"),
                _button("Defer", "d"),
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


def record_artifact_callback(settings: Settings, callback_data: str) -> str:
    parts = callback_data.split(":")
    if len(parts) != 4 or parts[0] != ARTIFACT_CALLBACK_PREFIX:
        raise ValueError("Unsupported callback")

    week_label = parts[1].strip()
    artifact_type = _ARTIFACT_TYPE_CODES.get(parts[2])
    feedback_note = _ARTIFACT_ACTIONS.get(parts[3])
    if not week_label:
        raise ValueError("Invalid artifact week")
    if artifact_type is None:
        raise ValueError("Unsupported artifact type")
    if feedback_note is None:
        raise ValueError("Unsupported artifact feedback")
    feedback, note = feedback_note

    with sqlite3.connect(settings.db_path) as connection:
        record_artifact_feedback(
            connection,
            week_label=week_label,
            artifact_type=artifact_type,
            feedback=feedback,
            notes=note,
            recorded_by="telegram_button",
        )

    return f"Записал: {feedback}"


def record_callback(settings: Settings, callback_data: str) -> str:
    if callback_data.startswith(f"{IDEA_CALLBACK_PREFIX}:"):
        return record_idea_callback(settings, callback_data)
    if callback_data.startswith(f"{ARTIFACT_CALLBACK_PREFIX}:"):
        return record_artifact_callback(settings, callback_data)
    raise ValueError("Unsupported callback")
