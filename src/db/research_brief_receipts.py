import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


SOURCE_PROJECT = "telegram-research-agent"
RECEIPT_TYPE = "research_brief_receipt"
VERIFICATION_STATUSES = {"pending", "verified", "needs_review", "failed", "waived"}

LIST_JSON_FIELDS = {
    "included_channels": "included_channels_json",
    "project_scopes": "project_scopes_json",
    "topic_scopes": "topic_scopes_json",
    "health_flags": "health_flags_json",
}
DICT_JSON_FIELDS = {
    "post_counts": "post_counts_json",
    "source_set": "source_set_json",
    "config_fingerprints": "config_fingerprints_json",
}
JSON_FIELDS = {**LIST_JSON_FIELDS, **DICT_JSON_FIELDS}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_week_label(week_label: str) -> str:
    clean_week_label = str(week_label).strip()
    if not clean_week_label:
        raise ValueError("week_label is required")
    return clean_week_label


def _require_verification_status(verification_status: str) -> str:
    if verification_status not in VERIFICATION_STATUSES:
        allowed = ", ".join(sorted(VERIFICATION_STATUSES))
        raise ValueError(f"unsupported verification_status: {verification_status!r}; expected one of {allowed}")
    return verification_status


def _json_list(values: list[Any] | tuple[Any, ...] | None) -> str:
    if values is None:
        values = []
    if not isinstance(values, (list, tuple)):
        raise ValueError("expected JSON list value")
    return json.dumps(list(values), ensure_ascii=False, sort_keys=True)


def _json_dict(values: dict[str, Any] | None) -> str:
    if values is None:
        values = {}
    if not isinstance(values, dict):
        raise ValueError("expected JSON object value")
    return json.dumps(values, ensure_ascii=False, sort_keys=True)


def _parse_json_list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _parse_json_dict(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _row_to_receipt(columns: list[str], row: sqlite3.Row | tuple) -> dict:
    values = dict(zip(columns, row))
    receipt = dict(values)
    for public_name, column_name in LIST_JSON_FIELDS.items():
        receipt[public_name] = _parse_json_list(values.get(column_name))
        receipt.pop(column_name, None)
    for public_name, column_name in DICT_JSON_FIELDS.items():
        receipt[public_name] = _parse_json_dict(values.get(column_name))
        receipt.pop(column_name, None)
    receipt["fallback_delivery_used"] = bool(receipt["fallback_delivery_used"])
    return receipt


def _cursor_rows_to_receipts(cursor: sqlite3.Cursor) -> list[dict]:
    columns = [description[0] for description in cursor.description or []]
    return [_row_to_receipt(columns, row) for row in cursor.fetchall()]


def record_research_brief_receipt(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    generated_at: str | None = None,
    receipt_id: str | None = None,
    source_version: str | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
    included_channels: list[Any] | tuple[Any, ...] | None = None,
    post_counts: dict[str, Any] | None = None,
    source_set: dict[str, Any] | None = None,
    project_scopes: list[Any] | tuple[Any, ...] | None = None,
    topic_scopes: list[Any] | tuple[Any, ...] | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    llm_category: str | None = None,
    prompt_template_path: str | None = None,
    prompt_template_version: str | None = None,
    config_fingerprints: dict[str, Any] | None = None,
    generation_params_fingerprint: str | None = None,
    digest_id: int | None = None,
    markdown_path: str | None = None,
    json_path: str | None = None,
    html_path: str | None = None,
    telegraph_url: str | None = None,
    telegram_delivery_timestamp: str | None = None,
    telegram_message_id: int | None = None,
    fallback_delivery: str | None = None,
    fallback_delivery_used: bool = False,
    verification_status: str = "pending",
    verifier_method: str | None = None,
    verifier_notes: str | None = None,
    checked_at: str | None = None,
    checked_by: str | None = None,
    health_flags: list[Any] | tuple[Any, ...] | None = None,
) -> dict:
    clean_week_label = _require_week_label(week_label)
    clean_status = _require_verification_status(verification_status)
    timestamp = generated_at or _now_iso()
    created_at = _now_iso()
    clean_receipt_id = _clean_text(receipt_id) or f"rbr_{uuid.uuid4().hex}"

    cursor = connection.execute(
        """
        INSERT INTO research_brief_receipts (
            receipt_id,
            week_label,
            generated_at,
            source_version,
            window_start,
            window_end,
            included_channels_json,
            post_counts_json,
            source_set_json,
            project_scopes_json,
            topic_scopes_json,
            llm_provider,
            llm_model,
            llm_category,
            prompt_template_path,
            prompt_template_version,
            config_fingerprints_json,
            generation_params_fingerprint,
            digest_id,
            markdown_path,
            json_path,
            html_path,
            telegraph_url,
            telegram_delivery_timestamp,
            telegram_message_id,
            fallback_delivery,
            fallback_delivery_used,
            verification_status,
            verifier_method,
            verifier_notes,
            checked_at,
            checked_by,
            health_flags_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            clean_receipt_id,
            clean_week_label,
            timestamp,
            _clean_text(source_version),
            _clean_text(window_start),
            _clean_text(window_end),
            _json_list(included_channels),
            _json_dict(post_counts),
            _json_dict(source_set),
            _json_list(project_scopes),
            _json_list(topic_scopes),
            _clean_text(llm_provider),
            _clean_text(llm_model),
            _clean_text(llm_category),
            _clean_text(prompt_template_path),
            _clean_text(prompt_template_version),
            _json_dict(config_fingerprints),
            _clean_text(generation_params_fingerprint),
            digest_id,
            _clean_text(markdown_path),
            _clean_text(json_path),
            _clean_text(html_path),
            _clean_text(telegraph_url),
            _clean_text(telegram_delivery_timestamp),
            telegram_message_id,
            _clean_text(fallback_delivery),
            1 if fallback_delivery_used else 0,
            clean_status,
            _clean_text(verifier_method),
            _clean_text(verifier_notes),
            _clean_text(checked_at),
            _clean_text(checked_by),
            _json_list(health_flags),
            created_at,
            created_at,
        ),
    )
    connection.commit()

    rows = fetch_research_brief_receipts(connection, receipt_id=clean_receipt_id, limit=1)
    if not rows:
        raise RuntimeError("research brief receipt insert could not be read back")
    rows[0]["id"] = int(cursor.lastrowid)
    return rows[0]


def fetch_research_brief_receipts(
    connection: sqlite3.Connection,
    *,
    receipt_id: str | None = None,
    week_label: str | None = None,
    digest_id: int | None = None,
    verification_status: str | None = None,
    limit: int = 10,
) -> list[dict]:
    clauses = []
    params: list[Any] = []
    clean_limit = max(1, int(limit or 10))

    if receipt_id:
        clauses.append("receipt_id = ?")
        params.append(receipt_id)
    if week_label:
        clauses.append("week_label = ?")
        params.append(week_label)
    if digest_id is not None:
        clauses.append("digest_id = ?")
        params.append(digest_id)
    if verification_status is not None:
        clauses.append("verification_status = ?")
        params.append(_require_verification_status(verification_status))

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor = connection.execute(
        f"""
        SELECT *
        FROM research_brief_receipts
        {where_sql}
        ORDER BY generated_at DESC, id DESC
        LIMIT ?
        """,
        (*params, clean_limit),
    )
    return _cursor_rows_to_receipts(cursor)
