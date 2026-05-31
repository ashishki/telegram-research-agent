import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterable


ARTIFACT_TYPES = {
    "research_brief",
    "implementation_ideas",
    "study_plan",
    "channel_intelligence",
    "other",
}
FEEDBACK_VALUES = {"useful", "weak", "noisy", "decision_impacting"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_required(value: str, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _normalize_feedback(value: str) -> str:
    normalized = str(value).strip().replace("-", "_")
    if normalized not in FEEDBACK_VALUES:
        allowed = ", ".join(sorted(FEEDBACK_VALUES))
        raise ValueError(f"unsupported artifact feedback: {value!r}; expected one of {allowed}")
    return normalized


def _normalize_artifact_type(value: str | None) -> str:
    normalized = str(value or "research_brief").strip()
    if normalized not in ARTIFACT_TYPES:
        allowed = ", ".join(sorted(ARTIFACT_TYPES))
        raise ValueError(f"unsupported artifact_type: {value!r}; expected one of {allowed}")
    return normalized


def _coerce_int_list(values: Iterable[int | str] | None) -> list[int]:
    result: list[int] = []
    for value in values or ():
        result.append(int(value))
    return result


def _json_int_array(values: Iterable[int | str] | None) -> str:
    return json.dumps(_coerce_int_list(values), ensure_ascii=False)


def _parse_int_array(value: str | None) -> list[int]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    result: list[int] = []
    for item in parsed:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _row_to_feedback(columns: list[str], row: sqlite3.Row | tuple) -> dict:
    values = dict(zip(columns, row))
    return {
        "id": int(values["id"]),
        "week_label": values["week_label"],
        "artifact_type": values["artifact_type"],
        "artifact_path": values["artifact_path"],
        "digest_id": values["digest_id"],
        "section": values["section"],
        "item_ref": values["item_ref"],
        "feedback": values["feedback"],
        "source_evidence_item_ids": _parse_int_array(values["source_evidence_item_ids_json"]),
        "notes": values["notes"],
        "recorded_at": values["recorded_at"],
        "recorded_by": values["recorded_by"],
    }


def _cursor_to_feedback(cursor: sqlite3.Cursor) -> list[dict]:
    columns = [description[0] for description in cursor.description or []]
    return [_row_to_feedback(columns, row) for row in cursor.fetchall()]


def record_artifact_feedback(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    feedback: str,
    artifact_type: str | None = None,
    artifact_path: str | None = None,
    digest_id: int | None = None,
    section: str | None = None,
    item_ref: str | None = None,
    source_evidence_item_ids: Iterable[int | str] | None = None,
    notes: str | None = None,
    recorded_at: str | None = None,
    recorded_by: str = "operator",
) -> dict:
    clean_week_label = _clean_required(week_label, "week_label")
    clean_feedback = _normalize_feedback(feedback)
    clean_artifact_type = _normalize_artifact_type(artifact_type)
    clean_recorded_by = _clean_text(recorded_by) or "operator"
    timestamp = recorded_at or _now_iso()
    cursor = connection.execute(
        """
        INSERT INTO artifact_feedback_logs (
            week_label,
            artifact_type,
            artifact_path,
            digest_id,
            section,
            item_ref,
            feedback,
            source_evidence_item_ids_json,
            notes,
            recorded_at,
            recorded_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            clean_week_label,
            clean_artifact_type,
            _clean_text(artifact_path),
            digest_id,
            _clean_text(section),
            _clean_text(item_ref),
            clean_feedback,
            _json_int_array(source_evidence_item_ids),
            _clean_text(notes),
            timestamp,
            clean_recorded_by,
        ),
    )
    connection.commit()

    rows = fetch_artifact_feedback(connection, feedback_id=int(cursor.lastrowid), limit=1)
    if not rows:
        raise RuntimeError("artifact feedback insert could not be read back")
    return rows[0]


def fetch_artifact_feedback(
    connection: sqlite3.Connection,
    *,
    feedback_id: int | None = None,
    week_label: str | None = None,
    artifact_type: str | None = None,
    artifact_path: str | None = None,
    digest_id: int | None = None,
    feedback: str | None = None,
    limit: int = 20,
) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []
    clean_limit = max(1, int(limit or 20))
    if feedback_id is not None:
        clauses.append("id = ?")
        params.append(int(feedback_id))
    if week_label:
        clauses.append("week_label = ?")
        params.append(str(week_label).strip())
    if artifact_type:
        clauses.append("artifact_type = ?")
        params.append(_normalize_artifact_type(artifact_type))
    if artifact_path:
        clauses.append("artifact_path = ?")
        params.append(artifact_path)
    if digest_id is not None:
        clauses.append("digest_id = ?")
        params.append(int(digest_id))
    if feedback:
        clauses.append("feedback = ?")
        params.append(_normalize_feedback(feedback))

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor = connection.execute(
        f"""
        SELECT *
        FROM artifact_feedback_logs
        {where_sql}
        ORDER BY recorded_at DESC, id DESC
        LIMIT ?
        """,
        (*params, clean_limit),
    )
    return _cursor_to_feedback(cursor)
