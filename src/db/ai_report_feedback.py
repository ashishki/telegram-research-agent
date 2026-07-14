import json
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone


FEEDBACK_TYPES = {
    "read",
    "useful",
    "tried",
    "applied_to_project",
    "too_shallow",
    "too_long",
    "confusing_visual",
    "missing_visual",
    "duplicate_content",
    "action_completed",
    "radar_decision_useful",
    "reaction_effect_missing",
    "source_trust_correction",
    "desired_report_change",
    "missed_important_post",
    "no_missed_posts",
    "wrong_priority",
    "not_interested",
    "noise",
    "trust_too_high",
    "trust_too_low",
    "verify_first",
    "correction",
    "retraction",
    "accidental_feedback",
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
    "feedback_event",
    "operator_context",
}
REPORT_SURFACES = {
    "weekly_brief",
    "knowledge_atlas",
    "mvp_radar",
    "reaction_personalization",
    "project_action",
    "visual",
    "audit_explorer",
    "report_package",
}
REPORT_SURFACE_ALIASES = {
    "brief": "weekly_brief",
    "weekly": "weekly_brief",
    "weekly_report": "weekly_brief",
    "weekly_intelligence_brief": "weekly_brief",
    "atlas": "knowledge_atlas",
    "knowledge": "knowledge_atlas",
    "knowledge_atlas_v2": "knowledge_atlas",
    "radar": "mvp_radar",
    "mvp": "mvp_radar",
    "mvp_weekly": "mvp_radar",
    "reaction": "reaction_personalization",
    "reactions": "reaction_personalization",
    "personalization": "reaction_personalization",
    "project": "project_action",
    "projects": "project_action",
    "action": "project_action",
    "actions": "project_action",
    "visuals": "visual",
    "chart": "visual",
    "graph": "visual",
    "audit": "audit_explorer",
    "audit_explorer": "audit_explorer",
    "package": "report_package",
}
FEEDBACK_CLASSIFICATIONS = {
    "useful",
    "wrong_priority",
    "too_shallow",
    "too_long",
    "confusing_visual",
    "missing_visual",
    "duplicate_content",
    "action_completed",
    "applied_to_project",
    "radar_decision_useful",
    "reaction_effect_missing",
    "source_trust_correction",
    "desired_report_change",
}
APPLICATION_STATUSES = {
    "applied",
    "unchanged",
    "code_config_required",
    "rejected",
    "pending",
}
INTAKE_INPUT_KINDS = {"text", "voice_transcript"}
INTAKE_STATUSES = {"pending", "confirmed", "discarded"}
CONFIRMATION_STATES = {"pending", "confirmed", "discarded"}
APPLICATION_RECEIPT_SCHEMA_VERSION = "ai_report_feedback_application_receipt.v1"


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


def _clean_identifier(value: object | None, *, default: str, max_length: int = 160) -> str:
    text = str(value or "").strip().replace(" ", "_").replace("-", "_")
    return (text[:max_length] if text else default)


def _feedback_classification(feedback_type: str, explicit: str | None = None) -> str:
    if explicit:
        return _normalize_choice(explicit, FEEDBACK_CLASSIFICATIONS, "feedback_classification")
    normalized = _normalize_choice(feedback_type, FEEDBACK_TYPES, "feedback_type")
    if normalized in FEEDBACK_CLASSIFICATIONS:
        return normalized
    if normalized in {"not_interested", "noise"}:
        return "wrong_priority"
    if normalized in {"tried"}:
        return "action_completed"
    if normalized in {"trust_too_high", "trust_too_low", "verify_first"}:
        return "source_trust_correction"
    if normalized in {"read", "no_missed_posts", "correction", "retraction", "accidental_feedback"}:
        return "desired_report_change"
    if normalized == "missed_important_post":
        return "desired_report_change"
    return "desired_report_change"


def _report_surface(
    *,
    report_surface: str | None,
    target_type: str,
    target_ref: str | None,
    report_path: str | None,
    feedback_classification: str,
) -> str:
    if report_surface:
        normalized = str(report_surface).strip().replace("-", "_").lower()
        normalized = REPORT_SURFACE_ALIASES.get(normalized, normalized)
        return _normalize_choice(normalized, REPORT_SURFACES, "report_surface")

    path_text = str(report_path or "").lower()
    target_text = f"{target_type} {target_ref or ''} {feedback_classification}".lower()
    combined = f"{path_text} {target_text}"
    if "atlas" in combined:
        return "knowledge_atlas"
    if "audit" in combined:
        return "audit_explorer"
    if "radar" in combined or "mvp" in combined:
        return "mvp_radar"
    if "reaction" in combined or "personalization" in combined:
        return "reaction_personalization"
    if target_type in {"action", "experiment"} or "project" in combined:
        return "project_action"
    if "visual" in combined or "chart" in combined or "graph" in combined:
        return "visual"
    return "weekly_brief"


def _section_id(value: object | None, *, target_type: str, report_surface: str) -> str:
    if value is not None and str(value).strip():
        return _clean_identifier(value, default="report_section")
    if target_type == "report":
        return "report"
    if report_surface == "visual":
        return "visual"
    if report_surface == "project_action":
        return "project_actions"
    if report_surface == "mvp_radar":
        return "mvp_radar"
    if report_surface == "reaction_personalization":
        return "reaction_personalization"
    if report_surface == "knowledge_atlas":
        return "knowledge_atlas"
    if report_surface == "audit_explorer":
        return "audit_explorer"
    return target_type


def _item_ref(
    value: object | None,
    *,
    target_ref: str | None,
    source_url: str | None,
    section_id: str,
) -> str:
    if value is not None and str(value).strip():
        return str(value).strip()[:200]
    if target_ref:
        return str(target_ref).strip()[:200]
    if source_url:
        return str(source_url).strip()[:200]
    return section_id or "report"


def _originating_report_item_ref(
    value: object | None,
    *,
    target_type: str,
    item_ref: str,
    feedback_classification: str,
) -> str | None:
    clean = _clean_optional(str(value)) if value is not None else None
    if clean:
        return clean[:200]
    if target_type in {"action", "experiment"} or feedback_classification in {
        "action_completed",
        "applied_to_project",
    }:
        return item_ref
    return None


def _application_status(
    *,
    feedback_type: str,
    feedback_classification: str,
    explicit: str | None,
) -> str:
    if explicit:
        return _normalize_choice(explicit, APPLICATION_STATUSES, "application_status")
    normalized_type = _normalize_choice(feedback_type, FEEDBACK_TYPES, "feedback_type")
    if normalized_type in {"retraction", "accidental_feedback"}:
        return "rejected"
    if feedback_classification in {
        "too_shallow",
        "too_long",
        "confusing_visual",
        "missing_visual",
        "duplicate_content",
        "reaction_effect_missing",
        "source_trust_correction",
    }:
        return "code_config_required"
    if feedback_classification in {
        "useful",
        "wrong_priority",
        "action_completed",
        "applied_to_project",
        "radar_decision_useful",
    }:
        return "applied"
    if normalized_type in {"missed_important_post"}:
        return "pending"
    return "unchanged"


def _application_reason(
    *,
    feedback_classification: str,
    application_status: str,
    explicit: str | None,
) -> str:
    clean = _clean_optional(explicit)
    if clean:
        return clean[:500]
    if application_status == "applied":
        return f"Confirmed {feedback_classification} feedback is available to future report ranking/editorial context."
    if application_status == "code_config_required":
        return f"Confirmed {feedback_classification} feedback requires explicit code, prompt, config, or profile approval."
    if application_status == "rejected":
        return f"Confirmed {feedback_classification} feedback was recorded but not applied because it rejects or retracts a prior signal."
    if application_status == "pending":
        return f"Confirmed {feedback_classification} feedback is pending a later artifact or manual review."
    return f"Confirmed {feedback_classification} feedback was preserved without changing this report."


def _application_reader_summary_ru(feedback: dict) -> str:
    classification = str(feedback.get("feedback_classification") or "desired_report_change")
    status = str(feedback.get("application_status") or "unchanged")
    surface = str(feedback.get("report_surface") or "weekly_brief")
    section = str(feedback.get("section_id") or "report")
    item = str(feedback.get("item_ref") or feedback.get("target_ref") or "report")
    if status == "applied":
        prefix = "Учтено"
    elif status == "code_config_required":
        prefix = "Нужна отдельная задача"
    elif status == "rejected":
        prefix = "Не применено"
    elif status == "pending":
        prefix = "Ожидает применения"
    else:
        prefix = "Оставлено без изменения"
    return f"{prefix}: {surface}/{section}/{item} — {classification}."


def _row_to_feedback(columns: list[str], row: sqlite3.Row | tuple) -> dict:
    values = dict(zip(columns, row))
    feedback_type = values["feedback_type"]
    target_type = values["target_type"]
    target_ref = _clean_optional(values.get("target_ref"))
    source_url = _clean_optional(values.get("source_url"))
    feedback_classification = _feedback_classification(
        feedback_type,
        _clean_optional(values.get("feedback_classification")),
    )
    report_surface = _report_surface(
        report_surface=_clean_optional(values.get("report_surface")),
        target_type=target_type,
        target_ref=target_ref,
        report_path=_clean_optional(values.get("report_path")),
        feedback_classification=feedback_classification,
    )
    section_id = _section_id(
        values.get("section_id"),
        target_type=target_type,
        report_surface=report_surface,
    )
    item_ref = _item_ref(
        values.get("item_ref"),
        target_ref=target_ref,
        source_url=source_url,
        section_id=section_id,
    )
    application_status = _application_status(
        feedback_type=feedback_type,
        feedback_classification=feedback_classification,
        explicit=_clean_optional(values.get("application_status")),
    )
    feedback = {
        "id": int(values["id"]),
        "week_label": values["week_label"],
        "report_path": values["report_path"],
        "report_run_id": values.get("report_run_id"),
        "report_surface": report_surface,
        "section_id": section_id,
        "item_ref": item_ref,
        "feedback_type": feedback_type,
        "feedback_classification": feedback_classification,
        "target_type": target_type,
        "target_ref": target_ref,
        "source_url": source_url,
        "notes": values["notes"],
        "confirmation_state": _normalize_choice(
            values.get("confirmation_state") or "confirmed",
            CONFIRMATION_STATES,
            "confirmation_state",
        ),
        "application_status": application_status,
        "application_reason": _application_reason(
            feedback_classification=feedback_classification,
            application_status=application_status,
            explicit=_clean_optional(values.get("application_reason")),
        ),
        "originating_report_item_ref": _originating_report_item_ref(
            values.get("originating_report_item_ref"),
            target_type=target_type,
            item_ref=item_ref,
            feedback_classification=feedback_classification,
        ),
        "created_at": values["created_at"],
        "recorded_by": values["recorded_by"],
    }
    feedback["signal_strength"] = _feedback_signal_strength(feedback["feedback_type"])
    feedback["feedback_provenance"] = _feedback_provenance(feedback)
    feedback["effect_window"] = _feedback_effect_window(feedback)
    feedback["correction"] = _feedback_correction_info(feedback)
    return feedback


def _feedback_signal_strength(feedback_type: str) -> str:
    if feedback_type in {"useful", "applied_to_project", "radar_decision_useful"}:
        return "strong_positive"
    if feedback_type in {"wrong_priority", "not_interested", "noise", "duplicate_content"}:
        return "strong_negative"
    if feedback_type in {
        "trust_too_high",
        "trust_too_low",
        "verify_first",
        "source_trust_correction",
    }:
        return "trust_calibration"
    if feedback_type in {"correction", "retraction", "accidental_feedback"}:
        return "correction"
    if feedback_type in {
        "tried",
        "action_completed",
        "too_shallow",
        "too_long",
        "confusing_visual",
        "missing_visual",
        "reaction_effect_missing",
        "missed_important_post",
    }:
        return "medium"
    if feedback_type in {"read", "no_missed_posts"}:
        return "weak_observation"
    return "unknown"


def _feedback_provenance(feedback: dict) -> dict:
    return {
        "source": "operator_feedback_event",
        "event_id": int(feedback["id"]),
        "recorded_by": feedback.get("recorded_by") or "operator",
        "created_at": feedback.get("created_at"),
        "report_path": feedback.get("report_path"),
        "report_run_id": feedback.get("report_run_id"),
        "report_surface": feedback.get("report_surface"),
        "section_id": feedback.get("section_id"),
        "item_ref": feedback.get("item_ref"),
        "source_url": feedback.get("source_url"),
        "confirmation_state": feedback.get("confirmation_state") or "confirmed",
    }


def _feedback_effect_window(feedback: dict) -> dict:
    return {
        "feedback_week_label": feedback.get("week_label"),
        "applies_from_week_label": _next_week_label(feedback.get("week_label")),
        "applies_to_future_artifacts_only": True,
        "does_not_rewrite_report_path": feedback.get("report_path"),
        "application_status": feedback.get("application_status"),
        "created_at": feedback.get("created_at"),
    }


def _feedback_correction_info(feedback: dict) -> dict:
    feedback_type = str(feedback.get("feedback_type") or "")
    is_correction = feedback_type in {"correction", "retraction", "accidental_feedback"}
    return {
        "is_correction": is_correction,
        "corrects_feedback_id": _feedback_event_ref_id(feedback.get("target_ref")) if is_correction else None,
        "append_only": True,
        "rewrites_prior_event": False,
    }


def _feedback_event_ref_id(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if ":" in text:
        text = text.rsplit(":", maxsplit=1)[-1]
    try:
        clean = int(text)
    except (TypeError, ValueError):
        return None
    return clean if clean > 0 else None


def _next_week_label(week_label: object) -> str | None:
    text = str(week_label or "").strip()
    if "-W" not in text:
        return None
    try:
        year_text, week_text = text.split("-W", maxsplit=1)
        current = datetime.fromisocalendar(int(year_text), int(week_text), 1).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    next_week = current + timedelta(days=7)
    year, week, _ = next_week.isocalendar()
    return f"{year}-W{week:02d}"


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
    report_run_id: str | None = None,
    report_surface: str | None = None,
    section_id: str | None = None,
    item_ref: str | None = None,
    feedback_classification: str | None = None,
    confirmation_state: str = "confirmed",
    application_status: str | None = None,
    application_reason: str | None = None,
    originating_report_item_ref: str | None = None,
    source_url: str | None = None,
    notes: str | None = None,
    created_at: str | None = None,
    recorded_by: str = "operator",
    commit: bool = True,
) -> dict:
    clean_week = _clean_required(week_label, "week_label")
    clean_feedback = _normalize_choice(feedback_type, FEEDBACK_TYPES, "feedback_type")
    clean_target = _normalize_choice(target_type, TARGET_TYPES, "target_type")
    clean_target_ref = _clean_optional(target_ref)
    clean_source_url = _clean_optional(source_url)
    clean_classification = _feedback_classification(clean_feedback, feedback_classification)
    clean_surface = _report_surface(
        report_surface=report_surface,
        target_type=clean_target,
        target_ref=clean_target_ref,
        report_path=report_path,
        feedback_classification=clean_classification,
    )
    clean_section = _section_id(
        section_id,
        target_type=clean_target,
        report_surface=clean_surface,
    )
    clean_item_ref = _item_ref(
        item_ref,
        target_ref=clean_target_ref,
        source_url=clean_source_url,
        section_id=clean_section,
    )
    clean_confirmation = _normalize_choice(
        confirmation_state,
        CONFIRMATION_STATES,
        "confirmation_state",
    )
    clean_application = _application_status(
        feedback_type=clean_feedback,
        feedback_classification=clean_classification,
        explicit=application_status,
    )
    clean_application_reason = _application_reason(
        feedback_classification=clean_classification,
        application_status=clean_application,
        explicit=application_reason,
    )
    clean_originating_ref = _originating_report_item_ref(
        originating_report_item_ref,
        target_type=clean_target,
        item_ref=clean_item_ref,
        feedback_classification=clean_classification,
    )
    timestamp = created_at or _now_iso()
    cursor = connection.execute(
        """
        INSERT INTO ai_report_feedback_events (
            week_label,
            report_path,
            report_run_id,
            report_surface,
            section_id,
            item_ref,
            feedback_type,
            feedback_classification,
            target_type,
            target_ref,
            source_url,
            notes,
            confirmation_state,
            application_status,
            application_reason,
            originating_report_item_ref,
            created_at,
            recorded_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            clean_week,
            _clean_optional(report_path),
            _clean_optional(report_run_id),
            clean_surface,
            clean_section,
            clean_item_ref,
            clean_feedback,
            clean_classification,
            clean_target,
            clean_target_ref,
            clean_source_url,
            _clean_optional(notes),
            clean_confirmation,
            clean_application,
            clean_application_reason,
            clean_originating_ref,
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


def record_ai_report_feedback_correction(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    corrected_feedback_id: int,
    correction_type: str = "correction",
    notes: str | None = None,
    report_path: str | None = None,
    source_url: str | None = None,
    created_at: str | None = None,
    recorded_by: str = "operator",
    commit: bool = True,
) -> dict:
    clean_type = _normalize_choice(correction_type, {"correction", "retraction", "accidental_feedback"}, "correction_type")
    prior_rows = fetch_ai_report_feedback(connection, feedback_id=int(corrected_feedback_id), limit=1)
    if not prior_rows:
        raise ValueError(f"AI report feedback event not found: {corrected_feedback_id}")
    return record_ai_report_feedback(
        connection,
        week_label=week_label,
        feedback_type=clean_type,
        target_type="feedback_event",
        target_ref=f"feedback_event:{int(corrected_feedback_id)}",
        report_path=report_path,
        source_url=source_url,
        notes=notes,
        created_at=created_at,
        recorded_by=recorded_by,
        commit=commit,
    )


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
    report_surface: str | None = None,
    feedback_classification: str | None = None,
    application_status: str | None = None,
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
    if report_surface:
        clauses.append("report_surface = ?")
        normalized_surface = str(report_surface).strip().replace("-", "_").lower()
        params.append(
            _normalize_choice(
                REPORT_SURFACE_ALIASES.get(normalized_surface, normalized_surface),
                REPORT_SURFACES,
                "report_surface",
            )
        )
    if feedback_classification:
        clauses.append("feedback_classification = ?")
        params.append(
            _normalize_choice(
                feedback_classification,
                FEEDBACK_CLASSIFICATIONS,
                "feedback_classification",
            )
        )
    if application_status:
        clauses.append("application_status = ?")
        params.append(_normalize_choice(application_status, APPLICATION_STATUSES, "application_status"))
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


def empty_ai_report_feedback_summary() -> dict:
    return _summarize_events([])


def summarize_ai_report_feedback(
    connection: sqlite3.Connection,
    *,
    before_week_label: str | None = None,
    week_label: str | None = None,
    created_before: datetime | str | None = None,
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
    if created_before is not None:
        from output.reporting_period import register_reporting_period_sqlite

        register_reporting_period_sqlite(connection)
        clauses.append(
            "reporting_utc_micros(created_at) < reporting_utc_micros(?)"
        )
        params.append(_explicit_utc_iso(created_before, field_name="created_before"))
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


def _explicit_utc_iso(value: datetime | str, *, field_name: str) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include an explicit timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _summarize_events(events: list[dict]) -> dict:
    events = [event for event in events if event.get("confirmation_state") == "confirmed"]
    counts = Counter(event["feedback_type"] for event in events)
    classification_counts = Counter(event["feedback_classification"] for event in events)
    surface_counts = Counter(event["report_surface"] for event in events)
    downrank_feedback = {"not_interested", "noise", "wrong_priority"}
    positive_feedback = {
        "useful",
        "tried",
        "applied_to_project",
        "action_completed",
        "radar_decision_useful",
    }
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
    corrections = _feedback_corrections(events)
    effect_traces = _feedback_effect_traces(events)
    application_receipt = _feedback_application_receipt(events)
    targeted_feedback = _targeted_feedback_summary(events)
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
        "counts_by_classification": dict(sorted(classification_counts.items())),
        "counts_by_surface": dict(sorted(surface_counts.items())),
        "downranked_thread_slugs": downranked_threads,
        "downranked_atom_refs": downranked_atoms,
        "downranked_target_refs": downranked_targets,
        "promoted_target_refs": promoted_targets,
        "missed_post_eval_examples": missed_examples[:10],
        "priority_eval_examples": priority_examples[:10],
        "feedback_eval_examples": [*missed_examples, *priority_examples][:12],
        "feedback_completion": completion,
        "feedback_changes": feedback_changes,
        "feedback_corrections": corrections,
        "feedback_effect_traces": effect_traces,
        "feedback_application_receipt": application_receipt,
        "targeted_feedback": targeted_feedback,
        "confirmed_event_count": len(events),
        "pending_draft_count": 0,
        "confirmation_state": "confirmed_only",
        "frontier_prompt_guidance": guidance,
        "recent_events": events[:10],
    }


def _targeted_feedback_summary(events: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], dict] = {}
    for event in events:
        key = (
            str(event.get("report_surface") or "weekly_brief"),
            str(event.get("section_id") or "report"),
            str(event.get("item_ref") or "report"),
        )
        item = grouped.setdefault(
            key,
            {
                "report_surface": key[0],
                "section_id": key[1],
                "item_ref": key[2],
                "event_count": 0,
                "classifications": [],
                "application_statuses": [],
                "feedback_refs": [],
            },
        )
        item["event_count"] += 1
        for field, value in (
            ("classifications", event.get("feedback_classification")),
            ("application_statuses", event.get("application_status")),
            ("feedback_refs", f"feedback:{event.get('id')}"),
        ):
            if value and value not in item[field]:
                item[field].append(value)
    return sorted(
        grouped.values(),
        key=lambda item: (
            item["report_surface"],
            item["section_id"],
            item["item_ref"],
        ),
    )[:20]


def _feedback_application_receipt(events: list[dict]) -> dict:
    buckets: dict[str, list[dict]] = {status: [] for status in sorted(APPLICATION_STATUSES)}
    for event in events:
        status = str(event.get("application_status") or "unchanged")
        if status not in buckets:
            status = "unchanged"
        item = {
            "feedback_ref": f"feedback:{event.get('id')}",
            "event_id": int(event.get("id") or 0),
            "week_label": event.get("week_label"),
            "report_run_id": event.get("report_run_id"),
            "report_surface": event.get("report_surface"),
            "section_id": event.get("section_id"),
            "item_ref": event.get("item_ref"),
            "legacy_target": {
                "target_type": event.get("target_type"),
                "target_ref": event.get("target_ref"),
            },
            "feedback_type": event.get("feedback_type"),
            "feedback_classification": event.get("feedback_classification"),
            "application_status": status,
            "application_reason": event.get("application_reason"),
            "originating_report_item_ref": event.get("originating_report_item_ref"),
            "reader_summary_ru": _application_reader_summary_ru(event),
        }
        buckets[status].append(item)
    return {
        "schema_version": APPLICATION_RECEIPT_SCHEMA_VERSION,
        "confirmation_state": "confirmed_only",
        "confirmed_events_considered": len(events),
        "counts_by_status": {status: len(items) for status, items in sorted(buckets.items())},
        "applied": buckets["applied"][:20],
        "unchanged": buckets["unchanged"][:20],
        "code_config_required": buckets["code_config_required"][:20],
        "rejected": buckets["rejected"][:20],
        "pending": buckets["pending"][:20],
    }


def _feedback_corrections(events: list[dict]) -> list[dict]:
    corrections = []
    for event in events:
        info = event.get("correction") or {}
        if not info.get("is_correction"):
            continue
        corrections.append(
            {
                "event_id": event.get("id"),
                "feedback_type": event.get("feedback_type"),
                "corrects_feedback_id": info.get("corrects_feedback_id"),
                "target_ref": event.get("target_ref"),
                "notes": event.get("notes"),
                "append_only": True,
                "rewrites_prior_event": False,
            }
        )
    return corrections[:20]


def _feedback_effect_traces(events: list[dict]) -> list[dict]:
    traces = []
    for event in events:
        traces.append(
            {
                "event_id": event.get("id"),
                "feedback_type": event.get("feedback_type"),
                "feedback_classification": event.get("feedback_classification"),
                "target_type": event.get("target_type"),
                "target_ref": event.get("target_ref"),
                "report_run_id": event.get("report_run_id"),
                "report_surface": event.get("report_surface"),
                "section_id": event.get("section_id"),
                "item_ref": event.get("item_ref"),
                "signal_strength": event.get("signal_strength"),
                "application_status": event.get("application_status"),
                "application_reason": event.get("application_reason"),
                "originating_report_item_ref": event.get("originating_report_item_ref"),
                "reader_summary_ru": _application_reader_summary_ru(event),
                "applied": event.get("application_status") == "applied",
                "provenance": event.get("feedback_provenance") or {},
                "effect_window": event.get("effect_window") or {},
            }
        )
    return traces[:20]


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
            "status": "unknown",
            "summary": "No prior feedback is available; personalization state is unknown.",
            "items": ["No confirmed feedback has changed ranking yet; no-feedback is not a negative signal."],
            "downranked": [],
            "promoted": [],
            "eval_example_count": 0,
        }

    items: list[str] = []
    if downranked_targets:
        items.append(f"Downranked {len(downranked_targets)} target(s) related to wrong-priority or not-interested feedback.")
    if promoted_targets:
        items.append(f"Promoted {len(promoted_targets)} target(s) marked useful, tried, or applied-to-project.")
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
            "action_completed",
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
            "Promote similar items when prior feedback marked them tried, useful, or applied_to_project; treat read as weak observation."
        )
    if eval_examples:
        guidance.append(
            "Treat missed-post and priority-calibration feedback as eval examples for coverage and ranking."
        )
    if not guidance:
        guidance.append("No prior feedback is available; state unknown personalization confidence.")
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
        f"application_statuses={_format_application_status_counts(summary)} "
        f"downranked_threads={','.join(downranked) if downranked else 'none'} "
        f"downranked_atoms={','.join(downranked_atoms) if downranked_atoms else 'none'}"
    )


def _format_application_status_counts(summary: dict) -> str:
    receipt = summary.get("feedback_application_receipt") or {}
    counts = receipt.get("counts_by_status") or {}
    if not counts:
        return "none"
    return ",".join(f"{status}={count}" for status, count in sorted(counts.items()))
