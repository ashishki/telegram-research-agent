import json
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
    "no_missed_posts",
    "wrong_priority",
    "not_interested",
    "noise",
    "trust_too_high",
    "trust_too_low",
    "verify_first",
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
    "missed_post",
    "trust_correction",
}
INTAKE_INPUT_KINDS = {"text", "voice_transcript"}
INTAKE_STATUSES = {"pending", "confirmed", "discarded"}


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


def _json_array(value: object | None) -> str:
    if value is None:
        return "[]"
    if not isinstance(value, list):
        raise ValueError("JSON array value is required")
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _load_json_array(value: str | None) -> list[dict]:
    if not value:
        return []
    decoded = json.loads(value)
    if not isinstance(decoded, list):
        return []
    return [item for item in decoded if isinstance(item, dict)]


def _row_to_intake(columns: list[str], row: sqlite3.Row | tuple) -> dict:
    values = dict(zip(columns, row))
    return {
        "id": int(values["id"]),
        "week_label": values["week_label"],
        "report_path": values["report_path"],
        "input_kind": values["input_kind"],
        "raw_text": values["raw_text"],
        "transcript_text": values["transcript_text"],
        "proposals": _load_json_array(values["proposals_json"]),
        "suggestions": _load_json_array(values["suggestions_json"]),
        "confirmation_summary": values["confirmation_summary"],
        "status": values["status"],
        "created_at": values["created_at"],
        "confirmed_at": values["confirmed_at"],
        "recorded_by": values["recorded_by"],
    }


def _cursor_to_intakes(cursor: sqlite3.Cursor) -> list[dict]:
    columns = [description[0] for description in cursor.description or []]
    return [_row_to_intake(columns, row) for row in cursor.fetchall()]


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
    commit: bool = True,
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
    if commit:
        connection.commit()
    rows = fetch_ai_report_feedback(connection, feedback_id=int(cursor.lastrowid), limit=1)
    if not rows:
        raise RuntimeError("AI report feedback insert could not be read back")
    return rows[0]


def record_ai_report_feedback_intake(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    input_kind: str,
    raw_text: str,
    transcript_text: str | None = None,
    proposals: list[dict] | None = None,
    suggestions: list[dict] | None = None,
    confirmation_summary: str | None = None,
    report_path: str | None = None,
    created_at: str | None = None,
    recorded_by: str = "operator",
    commit: bool = True,
) -> dict:
    clean_week = _clean_required(week_label, "week_label")
    clean_input = _normalize_choice(input_kind, INTAKE_INPUT_KINDS, "input_kind")
    clean_raw_text = _clean_required(raw_text, "raw_text")
    timestamp = created_at or _now_iso()
    cursor = connection.execute(
        """
        INSERT INTO ai_report_feedback_intakes (
            week_label,
            report_path,
            input_kind,
            raw_text,
            transcript_text,
            proposals_json,
            suggestions_json,
            confirmation_summary,
            status,
            created_at,
            confirmed_at,
            recorded_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, NULL, ?)
        """,
        (
            clean_week,
            _clean_optional(report_path),
            clean_input,
            clean_raw_text,
            _clean_optional(transcript_text),
            _json_array(proposals),
            _json_array(suggestions),
            _clean_optional(confirmation_summary) or "",
            timestamp,
            _clean_optional(recorded_by) or "operator",
        ),
    )
    if commit:
        connection.commit()
    rows = fetch_ai_report_feedback_intake(connection, intake_id=int(cursor.lastrowid), limit=1)
    if not rows:
        raise RuntimeError("AI report feedback intake insert could not be read back")
    return rows[0]


def update_ai_report_feedback_intake_summary(
    connection: sqlite3.Connection,
    *,
    intake_id: int,
    confirmation_summary: str,
    commit: bool = True,
) -> dict:
    connection.execute(
        """
        UPDATE ai_report_feedback_intakes
        SET confirmation_summary = ?
        WHERE id = ?
        """,
        (_clean_optional(confirmation_summary) or "", int(intake_id)),
    )
    if commit:
        connection.commit()
    rows = fetch_ai_report_feedback_intake(connection, intake_id=int(intake_id), limit=1)
    if not rows:
        raise ValueError(f"AI report feedback intake not found: {intake_id}")
    return rows[0]


def fetch_ai_report_feedback_intake(
    connection: sqlite3.Connection,
    *,
    intake_id: int | None = None,
    week_label: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []
    if intake_id is not None:
        clauses.append("id = ?")
        params.append(int(intake_id))
    if week_label:
        clauses.append("week_label = ?")
        params.append(str(week_label).strip())
    if status:
        clauses.append("status = ?")
        params.append(_normalize_choice(status, INTAKE_STATUSES, "status"))
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor = connection.execute(
        f"""
        SELECT *
        FROM ai_report_feedback_intakes
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (*params, max(1, int(limit or 20))),
    )
    return _cursor_to_intakes(cursor)


def _set_ai_report_feedback_intake_status(
    connection: sqlite3.Connection,
    intake_id: int,
    status: str,
    *,
    commit: bool = True,
) -> dict:
    clean_status = _normalize_choice(status, INTAKE_STATUSES, "status")
    rows = fetch_ai_report_feedback_intake(connection, intake_id=int(intake_id), limit=1)
    if not rows:
        raise ValueError(f"AI report feedback intake not found: {intake_id}")
    current = rows[0]
    if current["status"] != "pending":
        raise ValueError(f"AI report feedback intake is {current['status']}, not pending")
    confirmed_at = _now_iso() if clean_status == "confirmed" else None
    connection.execute(
        """
        UPDATE ai_report_feedback_intakes
        SET status = ?,
            confirmed_at = ?
        WHERE id = ?
        """,
        (clean_status, confirmed_at, int(intake_id)),
    )
    if commit:
        connection.commit()
    updated = fetch_ai_report_feedback_intake(connection, intake_id=int(intake_id), limit=1)
    if not updated:
        raise RuntimeError("AI report feedback intake update could not be read back")
    return updated[0]


def confirm_ai_report_feedback_intake(
    connection: sqlite3.Connection,
    intake_id: int,
    *,
    commit: bool = True,
) -> dict:
    return _set_ai_report_feedback_intake_status(connection, intake_id, "confirmed", commit=commit)


def discard_ai_report_feedback_intake(
    connection: sqlite3.Connection,
    intake_id: int,
    *,
    commit: bool = True,
) -> dict:
    return _set_ai_report_feedback_intake_status(connection, intake_id, "discarded", commit=commit)


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
    positive_feedback = {"useful", "tried", "applied_to_project", "read"}
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
    downranked_targets = sorted(
        {
            f"{event.get('target_type')}:{event.get('target_ref')}"
            for event in events
            if event.get("feedback_type") in downrank_feedback and event.get("target_ref")
        }
    )
    promoted_targets = sorted(
        {
            f"{event.get('target_type')}:{event.get('target_ref')}"
            for event in events
            if event.get("feedback_type") in positive_feedback and event.get("target_ref")
        }
    )
    missed_examples = [
        {
            "example_type": "missed_post",
            "week_label": event["week_label"],
            "source_url": event.get("source_url"),
            "notes": event.get("notes"),
            "target_ref": event.get("target_ref"),
            "created_at": event.get("created_at"),
        }
        for event in events
        if event.get("feedback_type") == "missed_important_post"
    ]
    priority_examples = [
        {
            "example_type": "priority_calibration",
            "week_label": event["week_label"],
            "feedback_type": event.get("feedback_type"),
            "target_type": event.get("target_type"),
            "target_ref": event.get("target_ref"),
            "source_url": event.get("source_url"),
            "notes": event.get("notes"),
            "created_at": event.get("created_at"),
        }
        for event in events
        if event.get("feedback_type") in {"wrong_priority", "not_interested"}
    ]
    completion = _minimum_feedback_completion(events)
    guidance = _frontier_prompt_guidance(
        counts=counts,
        downranked_threads=downranked_threads,
        downranked_atoms=downranked_atoms,
        promoted_targets=promoted_targets,
        eval_examples=[*missed_examples, *priority_examples],
    )
    feedback_changes = _feedback_changes_summary(
        event_count=len(events),
        counts=counts,
        downranked_targets=downranked_targets,
        promoted_targets=promoted_targets,
        missed_examples=missed_examples,
        priority_examples=priority_examples,
    )
    return {
        "event_count": len(events),
        "counts_by_feedback": dict(sorted(counts.items())),
        "downranked_thread_slugs": downranked_threads,
        "downranked_atom_refs": downranked_atoms,
        "downranked_target_refs": downranked_targets,
        "promoted_target_refs": promoted_targets,
        "missed_post_eval_examples": missed_examples[:10],
        "priority_eval_examples": priority_examples[:10],
        "feedback_eval_examples": [*missed_examples, *priority_examples][:12],
        "feedback_completion": completion,
        "feedback_changes": feedback_changes,
        "frontier_prompt_guidance": guidance,
        "recent_events": events[:10],
    }


def _feedback_changes_summary(
    *,
    event_count: int,
    counts: Counter,
    downranked_targets: list[str],
    promoted_targets: list[str],
    missed_examples: list[dict],
    priority_examples: list[dict],
) -> dict:
    if event_count <= 0:
        return {
            "status": "low_confidence",
            "summary": "No prior feedback is available; personalization confidence is low.",
            "items": ["No confirmed feedback has changed ranking yet."],
            "downranked": [],
            "promoted": [],
            "eval_example_count": 0,
        }

    items: list[str] = []
    if downranked_targets:
        items.append(f"Downranked {len(downranked_targets)} target(s) related to wrong-priority or not-interested feedback.")
    if promoted_targets:
        items.append(f"Promoted {len(promoted_targets)} target(s) marked useful, tried, read, or applied-to-project.")
    if missed_examples:
        items.append(f"Added {len(missed_examples)} missed-post eval example(s) for next report coverage.")
    if priority_examples:
        items.append(f"Added {len(priority_examples)} priority-calibration example(s) for ranking.")
    trust_count = sum(int(counts.get(name) or 0) for name in ("trust_too_high", "trust_too_low", "verify_first"))
    if trust_count:
        items.append(f"Applied {trust_count} source-trust correction(s) to future verification prompts.")
    if not items:
        items.append("Recorded prior feedback as a general personalization signal.")
    return {
        "status": "feedback_used",
        "summary": " ".join(items),
        "items": items,
        "downranked": downranked_targets,
        "promoted": promoted_targets,
        "eval_example_count": len(missed_examples) + len(priority_examples),
    }


def _minimum_feedback_completion(events: list[dict]) -> dict:
    read_refs = {
        str(event.get("target_ref") or event.get("source_url") or event.get("id"))
        for event in events
        if event.get("feedback_type") == "read"
        and event.get("target_type") in {"read_queue", "knowledge_atom", "report"}
    }
    action_refs = {
        str(event.get("target_ref") or event.get("id"))
        for event in events
        if event.get("target_type") in {"action", "experiment"}
        and event.get("feedback_type") in {
            "tried",
            "useful",
            "applied_to_project",
            "wrong_priority",
            "too_shallow",
            "not_interested",
        }
    }
    missed_or_clear = any(
        event.get("feedback_type") in {"missed_important_post", "no_missed_posts"}
        for event in events
    )
    trust_refs = {
        str(event.get("target_ref") or event.get("id"))
        for event in events
        if event.get("feedback_type") in {"trust_too_high", "trust_too_low", "verify_first"}
    }
    required = {
        "read_items": len(read_refs) >= 2,
        "action_outcome": bool(action_refs),
        "missed_or_no_missed": missed_or_clear,
        "trust_correction": bool(trust_refs),
    }
    completed = sum(1 for value in required.values() if value)
    missing = [name for name, ok in required.items() if not ok]
    return {
        "completed": completed == len(required),
        "completed_count": completed,
        "required_count": len(required),
        "missing": missing,
        "read_event_count": len(read_refs),
        "action_event_count": len(action_refs),
        "has_missed_or_no_missed": missed_or_clear,
        "trust_correction_count": len(trust_refs),
    }


def _frontier_prompt_guidance(
    *,
    counts: Counter,
    downranked_threads: list[str],
    downranked_atoms: list[str],
    promoted_targets: list[str],
    eval_examples: list[dict],
) -> list[str]:
    guidance: list[str] = []
    if downranked_threads or downranked_atoms or counts.get("wrong_priority") or counts.get("not_interested"):
        guidance.append(
            "Downrank similar items when prior feedback marked them wrong_priority, not_interested, or noise."
        )
    if promoted_targets or counts.get("useful") or counts.get("tried"):
        guidance.append(
            "Promote similar items when prior feedback marked them read, tried, useful, or applied_to_project."
        )
    if eval_examples:
        guidance.append(
            "Treat missed-post and priority-calibration feedback as eval examples for coverage and ranking."
        )
    if not guidance:
        guidance.append("No prior feedback is available; state low personalization confidence.")
    return guidance


def fetch_ai_report_eval_examples(
    connection: sqlite3.Connection,
    *,
    week_label: str | None = None,
    limit: int = 20,
) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []
    if week_label:
        clauses.append("week_label = ?")
        params.append(str(week_label).strip())
    clauses.append("feedback_type IN ('missed_important_post', 'wrong_priority', 'not_interested')")
    where_sql = f"WHERE {' AND '.join(clauses)}"
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
    return [
        {
            "example_type": (
                "missed_post"
                if row["feedback_type"] == "missed_important_post"
                else "priority_calibration"
            ),
            "week_label": row["week_label"],
            "feedback_type": row.get("feedback_type"),
            "target_type": row.get("target_type"),
            "source_url": row.get("source_url"),
            "notes": row.get("notes"),
            "target_ref": row.get("target_ref"),
            "created_at": row.get("created_at"),
        }
        for row in _cursor_to_feedback(cursor)
    ]


def fetch_missed_post_eval_examples(
    connection: sqlite3.Connection,
    *,
    week_label: str | None = None,
    limit: int = 20,
) -> list[dict]:
    return [
        example
        for example in fetch_ai_report_eval_examples(connection, week_label=week_label, limit=limit)
        if example.get("example_type") == "missed_post"
    ]


def format_ai_report_feedback_summary(summary: dict) -> str:
    counts = summary.get("counts_by_feedback") or {}
    if counts:
        counts_text = ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
    else:
        counts_text = "none"
    missed_count = len(summary.get("missed_post_eval_examples") or [])
    eval_count = len(summary.get("feedback_eval_examples") or [])
    downranked = summary.get("downranked_thread_slugs") or []
    downranked_atoms = summary.get("downranked_atom_refs") or []
    completion = summary.get("feedback_completion") or {}
    return (
        f"events={int(summary.get('event_count') or 0)} "
        f"counts={counts_text} missed_eval_examples={missed_count} eval_examples={eval_count} "
        f"completion={completion.get('completed_count', 0)}/{completion.get('required_count', 4)} "
        f"downranked_threads={','.join(downranked) if downranked else 'none'} "
        f"downranked_atoms={','.join(downranked_atoms) if downranked_atoms else 'none'}"
    )
