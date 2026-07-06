import sqlite3
from collections import Counter
from datetime import datetime, timezone


FEEDBACK_TYPES = {
    "read",
    "useful",
    "tried",
    "applied_to_project",
    "too_shallow",
    "missed_important_post",
    "wrong_priority",
    "not_interested",
    "noise",
}
TARGET_TYPES = {
    "report",
    "report_section",
    "idea_thread",
    "knowledge_atom",
    "source_channel",
    "read_queue",
    "experiment",
    "action",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_required(value: str, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_choice(value: str, allowed: set[str], field_name: str) -> str:
    normalized = _clean_required(value, field_name).replace("-", "_")
    if normalized not in allowed:
        expected = ", ".join(sorted(allowed))
        raise ValueError(f"unsupported {field_name}: {value!r}; expected one of {expected}")
    return normalized


def _row_to_feedback(columns: list[str], row: sqlite3.Row | tuple) -> dict:
    values = dict(zip(columns, row))
    return {
        "id": int(values["id"]),
        "week_label": values["week_label"],
        "report_path": values["report_path"],
        "feedback_type": values["feedback_type"],
        "target_type": values["target_type"],
        "target_ref": values["target_ref"],
        "source_url": values["source_url"],
        "notes": values["notes"],
        "created_at": values["created_at"],
        "recorded_by": values["recorded_by"],
    }


def _cursor_to_feedback(cursor: sqlite3.Cursor) -> list[dict]:
    columns = [description[0] for description in cursor.description or []]
    return [_row_to_feedback(columns, row) for row in cursor.fetchall()]


def record_ai_report_feedback(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    feedback_type: str,
    target_type: str = "report",
    target_ref: str | None = None,
    report_path: str | None = None,
    source_url: str | None = None,
    notes: str | None = None,
    created_at: str | None = None,
    recorded_by: str = "operator",
) -> dict:
    clean_week = _clean_required(week_label, "week_label")
    clean_feedback = _normalize_choice(feedback_type, FEEDBACK_TYPES, "feedback_type")
    clean_target = _normalize_choice(target_type, TARGET_TYPES, "target_type")
    timestamp = created_at or _now_iso()
    cursor = connection.execute(
        """
        INSERT INTO ai_report_feedback_events (
            week_label,
            report_path,
            feedback_type,
            target_type,
            target_ref,
            source_url,
            notes,
            created_at,
            recorded_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            clean_week,
            _clean_optional(report_path),
            clean_feedback,
            clean_target,
            _clean_optional(target_ref),
            _clean_optional(source_url),
            _clean_optional(notes),
            timestamp,
            _clean_optional(recorded_by) or "operator",
        ),
    )
    connection.commit()
    rows = fetch_ai_report_feedback(connection, feedback_id=int(cursor.lastrowid), limit=1)
    if not rows:
        raise RuntimeError("AI report feedback insert could not be read back")
    return rows[0]


def fetch_ai_report_feedback(
    connection: sqlite3.Connection,
    *,
    feedback_id: int | None = None,
    week_label: str | None = None,
    feedback_type: str | None = None,
    target_type: str | None = None,
    target_ref: str | None = None,
    limit: int = 20,
) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []
    if feedback_id is not None:
        clauses.append("id = ?")
        params.append(int(feedback_id))
    if week_label:
        clauses.append("week_label = ?")
        params.append(str(week_label).strip())
    if feedback_type:
        clauses.append("feedback_type = ?")
        params.append(_normalize_choice(feedback_type, FEEDBACK_TYPES, "feedback_type"))
    if target_type:
        clauses.append("target_type = ?")
        params.append(_normalize_choice(target_type, TARGET_TYPES, "target_type"))
    if target_ref:
        clauses.append("target_ref = ?")
        params.append(str(target_ref).strip())
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor = connection.execute(
        f"""
        SELECT *
        FROM ai_report_feedback_events
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (*params, max(1, int(limit or 20))),
    )
    return _cursor_to_feedback(cursor)


def summarize_ai_report_feedback(
    connection: sqlite3.Connection,
    *,
    before_week_label: str | None = None,
    week_label: str | None = None,
    limit: int = 100,
) -> dict:
    clauses: list[str] = []
    params: list[object] = []
    if week_label:
        clauses.append("week_label = ?")
        params.append(str(week_label).strip())
    if before_week_label:
        clauses.append("week_label < ?")
        params.append(str(before_week_label).strip())
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor = connection.execute(
        f"""
        SELECT *
        FROM ai_report_feedback_events
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (*params, max(1, int(limit or 100))),
    )
    events = _cursor_to_feedback(cursor)
    return _summarize_events(events)


def _summarize_events(events: list[dict]) -> dict:
    counts = Counter(event["feedback_type"] for event in events)
    downrank_feedback = {"not_interested", "noise", "wrong_priority"}
    downranked_threads = sorted(
        {
            str(event.get("target_ref") or "")
            for event in events
            if event.get("target_type") == "idea_thread"
            and event.get("feedback_type") in downrank_feedback
            and event.get("target_ref")
        }
    )
    downranked_atoms = sorted(
        {
            str(event.get("target_ref") or "")
            for event in events
            if event.get("target_type") == "knowledge_atom"
            and event.get("feedback_type") in downrank_feedback
            and event.get("target_ref")
        }
    )
    missed_examples = [
        {
            "week_label": event["week_label"],
            "source_url": event.get("source_url"),
            "notes": event.get("notes"),
            "target_ref": event.get("target_ref"),
            "created_at": event.get("created_at"),
        }
        for event in events
        if event.get("feedback_type") == "missed_important_post"
    ]
    return {
        "event_count": len(events),
        "counts_by_feedback": dict(sorted(counts.items())),
        "downranked_thread_slugs": downranked_threads,
        "downranked_atom_refs": downranked_atoms,
        "missed_post_eval_examples": missed_examples[:10],
        "recent_events": events[:10],
    }


def fetch_missed_post_eval_examples(
    connection: sqlite3.Connection,
    *,
    week_label: str | None = None,
    limit: int = 20,
) -> list[dict]:
    rows = fetch_ai_report_feedback(
        connection,
        week_label=week_label,
        feedback_type="missed_important_post",
        limit=limit,
    )
    return [
        {
            "week_label": row["week_label"],
            "source_url": row.get("source_url"),
            "notes": row.get("notes"),
            "target_ref": row.get("target_ref"),
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]


def format_ai_report_feedback_summary(summary: dict) -> str:
    counts = summary.get("counts_by_feedback") or {}
    if counts:
        counts_text = ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
    else:
        counts_text = "none"
    missed_count = len(summary.get("missed_post_eval_examples") or [])
    downranked = summary.get("downranked_thread_slugs") or []
    downranked_atoms = summary.get("downranked_atom_refs") or []
    return (
        f"events={int(summary.get('event_count') or 0)} "
        f"counts={counts_text} missed_eval_examples={missed_count} "
        f"downranked_threads={','.join(downranked) if downranked else 'none'} "
        f"downranked_atoms={','.join(downranked_atoms) if downranked_atoms else 'none'}"
    )
