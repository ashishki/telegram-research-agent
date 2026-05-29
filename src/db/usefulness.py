import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterable


LIST_FIELDS = {
    "useful_sections": "useful_sections_json",
    "not_useful_sections": "not_useful_sections_json",
    "decisions_influenced": "decisions_influenced_json",
    "weak_evidence_notes": "weak_evidence_notes_json",
    "channels_gaining_trust": "channels_gaining_trust_json",
    "channels_losing_trust": "channels_losing_trust_json",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_list(values: Iterable[str] | None) -> list[str]:
    if isinstance(values, str):
        values = (values,)
    normalized: list[str] = []
    for value in values or ():
        text = str(value).strip()
        if text:
            normalized.append(text)
    return normalized


def _json_array(values: Iterable[str] | None) -> str:
    return json.dumps(_normalize_list(values), ensure_ascii=False)


def _parse_json_array(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if item is not None]


def _row_to_log(columns: list[str], row: sqlite3.Row | tuple) -> dict:
    values = dict(zip(columns, row))
    result = {
        "id": int(values["id"]),
        "week_label": values["week_label"],
        "notes": values["notes"],
        "recorded_at": values["recorded_at"],
        "recorded_by": values["recorded_by"],
    }
    for public_name, column_name in LIST_FIELDS.items():
        result[public_name] = _parse_json_array(values[column_name])
    return result


def _cursor_rows_to_logs(cursor: sqlite3.Cursor) -> list[dict]:
    columns = [description[0] for description in cursor.description or []]
    return [_row_to_log(columns, row) for row in cursor.fetchall()]


def record_weekly_usefulness_log(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    useful_sections: Iterable[str] | None = None,
    not_useful_sections: Iterable[str] | None = None,
    decisions_influenced: Iterable[str] | None = None,
    weak_evidence_notes: Iterable[str] | None = None,
    channels_gaining_trust: Iterable[str] | None = None,
    channels_losing_trust: Iterable[str] | None = None,
    notes: str | None = None,
    recorded_at: str | None = None,
) -> dict:
    clean_week_label = str(week_label).strip()
    if not clean_week_label:
        raise ValueError("week_label is required")

    clean_notes = notes.strip() if isinstance(notes, str) and notes.strip() else None
    timestamp = recorded_at or _now_iso()
    cursor = connection.execute(
        """
        INSERT INTO weekly_usefulness_logs (
            week_label,
            useful_sections_json,
            not_useful_sections_json,
            decisions_influenced_json,
            weak_evidence_notes_json,
            channels_gaining_trust_json,
            channels_losing_trust_json,
            notes,
            recorded_at,
            recorded_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            clean_week_label,
            _json_array(useful_sections),
            _json_array(not_useful_sections),
            _json_array(decisions_influenced),
            _json_array(weak_evidence_notes),
            _json_array(channels_gaining_trust),
            _json_array(channels_losing_trust),
            clean_notes,
            timestamp,
            "operator",
        ),
    )
    connection.commit()

    read_cursor = connection.execute(
        """
        SELECT *
        FROM weekly_usefulness_logs
        WHERE id = ?
        """,
        (cursor.lastrowid,),
    )
    rows = _cursor_rows_to_logs(read_cursor)
    if not rows:
        raise RuntimeError("weekly usefulness log insert could not be read back")
    return rows[0]


def fetch_weekly_usefulness_logs(
    connection: sqlite3.Connection,
    *,
    week_label: str | None = None,
    limit: int = 10,
) -> list[dict]:
    clean_limit = max(1, int(limit or 10))
    if week_label:
        cursor = connection.execute(
            """
            SELECT *
            FROM weekly_usefulness_logs
            WHERE week_label = ?
            ORDER BY recorded_at DESC, id DESC
            LIMIT ?
            """,
            (week_label, clean_limit),
        )
    else:
        cursor = connection.execute(
            """
            SELECT *
            FROM weekly_usefulness_logs
            ORDER BY recorded_at DESC, id DESC
            LIMIT ?
            """,
            (clean_limit,),
        )
    return _cursor_rows_to_logs(cursor)
