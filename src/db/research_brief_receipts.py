import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_PROJECT = "telegram-research-agent"
RECEIPT_TYPE = "research_brief_receipt"
VERIFICATION_STATUSES = {"pending", "verified", "needs_review", "failed", "waived"}
OPERATOR_REVIEW_STATUSES = {"verified", "needs_review", "failed", "waived"}
TELEGRAM_POST_URL_RE = re.compile(r"^https://t\.me/[A-Za-z0-9_]+/\d+$")

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


def _merge_health_flags(existing: list[Any], new_flags: list[Any] | tuple[Any, ...] | None) -> list[Any]:
    merged: list[Any] = []
    for flag in [*existing, *(list(new_flags) if new_flags is not None else [])]:
        if flag not in merged:
            merged.append(flag)
    return merged


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _count_existing_ids(connection: sqlite3.Connection, table_name: str, ids: list[int]) -> int:
    if not ids or not _table_exists(connection, table_name):
        return 0
    placeholders = ",".join("?" for _ in ids)
    row = connection.execute(
        f"SELECT COUNT(*) FROM {table_name} WHERE id IN ({placeholders})",
        ids,
    ).fetchone()
    return int(row[0] if row else 0)


def _is_existing_path(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return Path(text).exists()


def _coerce_int_list(values: Any) -> tuple[list[int], int]:
    if not isinstance(values, list):
        return [], 0
    coerced: list[int] = []
    invalid_count = 0
    for value in values:
        try:
            coerced.append(int(value))
        except (TypeError, ValueError):
            invalid_count += 1
    return coerced, invalid_count


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
    artifact_path: str | None = None,
    telegraph_url: str | None = None,
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
    if artifact_path:
        clauses.append("(markdown_path = ? OR json_path = ? OR html_path = ?)")
        params.extend([artifact_path, artifact_path, artifact_path])
    if telegraph_url:
        clauses.append("telegraph_url = ?")
        params.append(telegraph_url)

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


def update_research_brief_receipt_delivery_refs(
    connection: sqlite3.Connection,
    *,
    receipt_id: str | None = None,
    week_label: str | None = None,
    digest_id: int | None = None,
    telegraph_url: str | None = None,
    telegram_delivery_timestamp: str | None = None,
    telegram_message_id: int | None = None,
    fallback_delivery: str | None = None,
    fallback_delivery_used: bool | None = None,
    health_flags: list[Any] | tuple[Any, ...] | None = None,
) -> dict | None:
    if not any([receipt_id, week_label, digest_id is not None]):
        raise ValueError("receipt_id, week_label, or digest_id is required")

    rows = fetch_research_brief_receipts(
        connection,
        receipt_id=receipt_id,
        week_label=week_label,
        digest_id=digest_id,
        limit=1,
    )
    if not rows:
        return None

    receipt = rows[0]
    fields: list[str] = ["updated_at = ?"]
    params: list[Any] = [_now_iso()]

    if telegraph_url is not None:
        fields.append("telegraph_url = ?")
        params.append(_clean_text(telegraph_url))
    if telegram_delivery_timestamp is not None:
        fields.append("telegram_delivery_timestamp = ?")
        params.append(_clean_text(telegram_delivery_timestamp))
    if telegram_message_id is not None:
        fields.append("telegram_message_id = ?")
        params.append(telegram_message_id)
    if fallback_delivery is not None:
        fields.append("fallback_delivery = ?")
        params.append(_clean_text(fallback_delivery))
    if fallback_delivery_used is not None:
        fields.append("fallback_delivery_used = ?")
        params.append(1 if fallback_delivery_used else 0)
    if health_flags is not None:
        fields.append("health_flags_json = ?")
        params.append(_json_list(_merge_health_flags(receipt["health_flags"], health_flags)))

    params.append(receipt["id"])
    connection.execute(
        f"""
        UPDATE research_brief_receipts
        SET {', '.join(fields)}
        WHERE id = ?
        """,
        params,
    )
    connection.commit()

    updated = fetch_research_brief_receipts(connection, receipt_id=receipt["receipt_id"], limit=1)
    return updated[0] if updated else None


def verify_research_brief_receipt(
    connection: sqlite3.Connection,
    *,
    receipt_id: str | None = None,
    week_label: str | None = None,
    digest_id: int | None = None,
) -> dict | None:
    if not any([receipt_id, week_label, digest_id is not None]):
        raise ValueError("receipt_id, week_label, or digest_id is required")

    rows = fetch_research_brief_receipts(
        connection,
        receipt_id=receipt_id,
        week_label=week_label,
        digest_id=digest_id,
        limit=1,
    )
    if not rows:
        return None

    receipt = rows[0]
    failures: list[str] = []
    review: list[str] = []

    if receipt.get("type") != RECEIPT_TYPE:
        failures.append("receipt type is not research_brief_receipt")
    if not receipt.get("week_label"):
        failures.append("week_label is missing")
    if not receipt.get("window_start") or not receipt.get("window_end"):
        failures.append("evidence window is incomplete")
    if receipt.get("digest_id") is None:
        failures.append("digest_id is missing")
    elif _count_existing_ids(connection, "digests", [int(receipt["digest_id"])]) != 1:
        failures.append("digest_id does not resolve")

    source_set = receipt.get("source_set") or {}
    source_links = [
        str(url).strip()
        for url in source_set.get("telegram_source_links", [])
        if str(url).strip()
    ]
    invalid_links = [url for url in source_links if not TELEGRAM_POST_URL_RE.match(url)]
    if invalid_links:
        failures.append(f"invalid Telegram source links: {len(invalid_links)}")
    if source_set.get("source_post_ids") and not source_links:
        review.append("source_post_ids are present but telegram_source_links are missing")

    evidence_ids, invalid_evidence_id_count = _coerce_int_list(source_set.get("source_evidence_item_ids", []))
    if invalid_evidence_id_count:
        failures.append("one or more source_evidence_item_ids are invalid")
    if evidence_ids:
        existing_evidence_count = _count_existing_ids(connection, "signal_evidence_items", evidence_ids)
        if existing_evidence_count != len(set(evidence_ids)):
            failures.append("one or more source_evidence_item_ids do not resolve")

    markdown_path = receipt.get("markdown_path")
    json_path = receipt.get("json_path")
    html_path = receipt.get("html_path")
    if not _is_existing_path(markdown_path):
        failures.append("markdown artifact is missing")
    total_posts = int((receipt.get("post_counts") or {}).get("total_posts") or 0)
    if total_posts > 0 and not _is_existing_path(json_path):
        failures.append("json artifact is missing")
    if not receipt.get("telegraph_url") and not receipt.get("fallback_delivery_used"):
        review.append("delivery route is missing telegraph_url or fallback_delivery")
    if receipt.get("fallback_delivery_used") and not receipt.get("fallback_delivery"):
        failures.append("fallback delivery is flagged but fallback_delivery is missing")
    if receipt.get("fallback_delivery_used") and not _is_existing_path(html_path) and receipt.get("fallback_delivery") != "text":
        failures.append("fallback artifact is missing")

    config_fingerprints = receipt.get("config_fingerprints") or {}
    for key in ("scoring_config", "profile_config", "projects_config", "channels_config", "prompt_template"):
        value = config_fingerprints.get(key)
        if not isinstance(value, dict) or not (value.get("sha256") or value.get("status") == "missing"):
            review.append(f"{key} fingerprint is missing")

    llm_model = receipt.get("llm_model")
    llm_usage_ids = source_set.get("llm_usage_ids") or config_fingerprints.get("llm_usage_ids") or []
    if llm_model and not llm_usage_ids:
        review.append("llm_usage_ids are missing for model-generated brief")
    if llm_usage_ids:
        usage_ids, invalid_usage_id_count = _coerce_int_list(llm_usage_ids)
        if invalid_usage_id_count:
            failures.append("one or more llm_usage_ids are invalid")
        existing_usage_count = _count_existing_ids(connection, "llm_usage", usage_ids)
        if existing_usage_count != len(set(usage_ids)):
            failures.append("one or more llm_usage_ids do not resolve")

    health_flags = receipt.get("health_flags") or []
    strong_count = int((receipt.get("post_counts") or {}).get("strong_count") or 0)
    watch_count = int((receipt.get("post_counts") or {}).get("watch_count") or 0)
    if total_posts <= 0 and "empty_week_alert" not in health_flags:
        review.append("empty week is missing empty_week_alert")
    if total_posts > 0 and strong_count + watch_count <= 0 and "low_signal_alert" not in health_flags:
        review.append("low-signal week is missing low_signal_alert")
    if source_set.get("broad_fallback_used") and not source_set.get("broad_fallback_reason"):
        review.append("broad fallback usage lacks broad_fallback_reason")

    if failures:
        status = "failed"
        notes = failures + review
    elif review:
        status = "needs_review"
        notes = review
    else:
        status = "verified"
        notes = ["deterministic checks passed"]

    connection.execute(
        """
        UPDATE research_brief_receipts
        SET verification_status = ?,
            verifier_method = ?,
            verifier_notes = ?,
            checked_at = ?,
            checked_by = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            status,
            "deterministic_checks",
            "; ".join(notes),
            _now_iso(),
            "system",
            _now_iso(),
            receipt["id"],
        ),
    )
    connection.commit()

    updated = fetch_research_brief_receipts(connection, receipt_id=receipt["receipt_id"], limit=1)
    return updated[0] if updated else None


def review_research_brief_receipt(
    connection: sqlite3.Connection,
    *,
    verification_status: str,
    verifier_notes: str | None = None,
    checked_by: str = "operator",
    receipt_id: str | None = None,
    week_label: str | None = None,
    digest_id: int | None = None,
) -> dict | None:
    if verification_status not in OPERATOR_REVIEW_STATUSES:
        allowed = ", ".join(sorted(OPERATOR_REVIEW_STATUSES))
        raise ValueError(f"unsupported operator verification_status: {verification_status!r}; expected one of {allowed}")
    if not any([receipt_id, week_label, digest_id is not None]):
        raise ValueError("receipt_id, week_label, or digest_id is required")

    rows = fetch_research_brief_receipts(
        connection,
        receipt_id=receipt_id,
        week_label=week_label,
        digest_id=digest_id,
        limit=1,
    )
    if not rows:
        return None

    receipt = rows[0]
    timestamp = _now_iso()
    connection.execute(
        """
        UPDATE research_brief_receipts
        SET verification_status = ?,
            verifier_method = ?,
            verifier_notes = ?,
            checked_at = ?,
            checked_by = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            verification_status,
            "operator_review",
            _clean_text(verifier_notes),
            timestamp,
            _clean_text(checked_by) or "operator",
            timestamp,
            receipt["id"],
        ),
    )
    connection.commit()

    updated = fetch_research_brief_receipts(connection, receipt_id=receipt["receipt_id"], limit=1)
    return updated[0] if updated else None
