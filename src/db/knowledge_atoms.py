import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterable


ATOM_TYPES = {
    "tool_release",
    "model_update",
    "workflow_pattern",
    "engineering_practice",
    "benchmark_claim",
    "market_signal",
    "risk_warning",
    "case_study",
    "tutorial_resource",
    "opinion_shift",
    "research_claim",
    "pricing_or_limit_change",
    "regulatory_or_access_change",
}
BATCH_STATUSES = {"running", "completed", "failed", "partial"}
STALENESS_STATUSES = {
    "fresh",
    "active",
    "watch",
    "stale",
    "superseded",
    "resolved",
    "hype_only",
    "unknown",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_required(value: str, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _normalize_choice(value: str, allowed: set[str], field_name: str) -> str:
    normalized = _clean_required(value, field_name)
    if normalized not in allowed:
        expected = ", ".join(sorted(allowed))
        raise ValueError(f"unsupported {field_name}: {value!r}; expected one of {expected}")
    return normalized


def _score(value: float | int | None, field_name: str) -> float:
    score = float(value or 0.0)
    if score < 0.0 or score > 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return score


def _normalize_string_list(values: Iterable[str] | str | None) -> list[str]:
    if isinstance(values, str):
        values = (values,)
    result: list[str] = []
    for value in values or ():
        text = str(value).strip()
        if text:
            result.append(text)
    return result


def _normalize_int_list(values: Iterable[int | str] | None) -> list[int]:
    result: list[int] = []
    for value in values or ():
        result.append(int(value))
    return result


def _json_string_array(values: Iterable[str] | str | None) -> str:
    return json.dumps(_normalize_string_list(values), ensure_ascii=False)


def _parse_array(value: str | None) -> list:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _row_to_batch(columns: list[str], row: sqlite3.Row | tuple) -> dict:
    values = dict(zip(columns, row))
    return {
        "id": int(values["id"]),
        "batch_key": values["batch_key"],
        "started_at": values["started_at"],
        "completed_at": values["completed_at"],
        "week_label": values["week_label"],
        "channel_username": values["channel_username"],
        "post_count": int(values["post_count"] or 0),
        "model": values["model"],
        "prompt_version": values["prompt_version"],
        "status": values["status"],
        "error": values["error"],
        "created_at": values["created_at"],
        "updated_at": values["updated_at"],
    }


def _row_to_atom(columns: list[str], row: sqlite3.Row | tuple) -> dict:
    values = dict(zip(columns, row))
    return {
        "id": int(values["id"]),
        "atom_key": values["atom_key"],
        "extraction_batch_id": values["extraction_batch_id"],
        "week_label": values["week_label"],
        "atom_type": values["atom_type"],
        "claim": values["claim"],
        "summary": values["summary"],
        "evidence_quote": values["evidence_quote"],
        "source_post_ids": _parse_array(values["source_post_ids_json"]),
        "source_urls": _parse_array(values["source_urls_json"]),
        "entities": _parse_array(values["entities_json"]),
        "tools": _parse_array(values["tools_json"]),
        "models": _parse_array(values["models_json"]),
        "practices": _parse_array(values["practices_json"]),
        "confidence": float(values["confidence"] or 0.0),
        "novelty_score": float(values["novelty_score"] or 0.0),
        "practical_utility_score": float(values["practical_utility_score"] or 0.0),
        "frontier_relevance_score": float(values["frontier_relevance_score"] or 0.0),
        "operator_relevance_score": float(values["operator_relevance_score"] or 0.0),
        "staleness_status": values["staleness_status"],
        "why_it_matters": values["why_it_matters"],
        "expiry_hint": values["expiry_hint"],
        "first_seen_at": values["first_seen_at"],
        "last_seen_at": values["last_seen_at"],
        "created_at": values["created_at"],
        "updated_at": values["updated_at"],
    }


def _cursor_to_batches(cursor: sqlite3.Cursor) -> list[dict]:
    columns = [description[0] for description in cursor.description or []]
    return [_row_to_batch(columns, row) for row in cursor.fetchall()]


def _cursor_to_atoms(cursor: sqlite3.Cursor) -> list[dict]:
    columns = [description[0] for description in cursor.description or []]
    return [_row_to_atom(columns, row) for row in cursor.fetchall()]


def build_batch_key(
    *,
    week_label: str,
    channel_username: str | None,
    model: str,
    prompt_version: str,
) -> str:
    payload = {
        "week_label": _clean_required(week_label, "week_label"),
        "channel_username": _clean_optional(channel_username) or "*",
        "model": _clean_required(model, "model"),
        "prompt_version": _clean_required(prompt_version, "prompt_version"),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return f"knowledge-batch:{digest}"


def build_atom_key(
    *,
    atom_type: str,
    claim: str,
    source_post_ids: Iterable[int | str],
) -> str:
    payload = {
        "atom_type": _normalize_choice(atom_type, ATOM_TYPES, "atom_type"),
        "claim": " ".join(_clean_required(claim, "claim").lower().split()),
        "source_post_ids": sorted(_normalize_int_list(source_post_ids)),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return f"knowledge-atom:{digest}"


def record_knowledge_extraction_batch(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    model: str,
    channel_username: str | None = None,
    post_count: int = 0,
    prompt_version: str = "unversioned",
    status: str = "running",
    started_at: str | None = None,
    completed_at: str | None = None,
    error: str | None = None,
    batch_key: str | None = None,
) -> dict:
    clean_week = _clean_required(week_label, "week_label")
    clean_model = _clean_required(model, "model")
    clean_prompt_version = _clean_required(prompt_version, "prompt_version")
    clean_status = _normalize_choice(status, BATCH_STATUSES, "status")
    clean_channel = _clean_optional(channel_username)
    clean_post_count = int(post_count or 0)
    if clean_post_count < 0:
        raise ValueError("post_count must be non-negative")
    now = _now_iso()
    clean_batch_key = batch_key or build_batch_key(
        week_label=clean_week,
        channel_username=clean_channel,
        model=clean_model,
        prompt_version=clean_prompt_version,
    )
    connection.execute(
        """
        INSERT INTO knowledge_extraction_batches (
            batch_key,
            started_at,
            completed_at,
            week_label,
            channel_username,
            post_count,
            model,
            prompt_version,
            status,
            error,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(batch_key) DO UPDATE SET
            started_at = excluded.started_at,
            completed_at = excluded.completed_at,
            week_label = excluded.week_label,
            channel_username = excluded.channel_username,
            post_count = excluded.post_count,
            model = excluded.model,
            prompt_version = excluded.prompt_version,
            status = excluded.status,
            error = excluded.error,
            updated_at = excluded.updated_at
        """,
        (
            clean_batch_key,
            started_at or now,
            completed_at,
            clean_week,
            clean_channel,
            clean_post_count,
            clean_model,
            clean_prompt_version,
            clean_status,
            _clean_optional(error),
            now,
            now,
        ),
    )
    connection.commit()
    rows = fetch_knowledge_extraction_batches(connection, batch_key=clean_batch_key, limit=1)
    if not rows:
        raise RuntimeError("knowledge extraction batch could not be read back")
    return rows[0]


def complete_knowledge_extraction_batch(
    connection: sqlite3.Connection,
    *,
    batch_id: int,
    status: str = "completed",
    error: str | None = None,
    completed_at: str | None = None,
) -> dict:
    clean_status = _normalize_choice(status, BATCH_STATUSES, "status")
    timestamp = completed_at or _now_iso()
    connection.execute(
        """
        UPDATE knowledge_extraction_batches
        SET status = ?, error = ?, completed_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (clean_status, _clean_optional(error), timestamp, timestamp, int(batch_id)),
    )
    connection.commit()
    rows = fetch_knowledge_extraction_batches(connection, batch_id=batch_id, limit=1)
    if not rows:
        raise RuntimeError("knowledge extraction batch could not be read back")
    return rows[0]


def fetch_knowledge_extraction_batches(
    connection: sqlite3.Connection,
    *,
    batch_id: int | None = None,
    batch_key: str | None = None,
    week_label: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []
    if batch_id is not None:
        clauses.append("id = ?")
        params.append(int(batch_id))
    if batch_key:
        clauses.append("batch_key = ?")
        params.append(str(batch_key).strip())
    if week_label:
        clauses.append("week_label = ?")
        params.append(str(week_label).strip())
    if status:
        clauses.append("status = ?")
        params.append(_normalize_choice(status, BATCH_STATUSES, "status"))
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor = connection.execute(
        f"""
        SELECT *
        FROM knowledge_extraction_batches
        {where_sql}
        ORDER BY started_at DESC, id DESC
        LIMIT ?
        """,
        (*params, max(1, int(limit or 20))),
    )
    return _cursor_to_batches(cursor)


def record_knowledge_atom(
    connection: sqlite3.Connection,
    *,
    atom_type: str,
    claim: str,
    evidence_quote: str,
    source_post_ids: Iterable[int | str],
    source_urls: Iterable[str] | str,
    extraction_batch_id: int | None = None,
    week_label: str | None = None,
    summary: str | None = None,
    entities: Iterable[str] | str | None = None,
    tools: Iterable[str] | str | None = None,
    models: Iterable[str] | str | None = None,
    practices: Iterable[str] | str | None = None,
    confidence: float | int | None = 0.0,
    novelty_score: float | int | None = 0.0,
    practical_utility_score: float | int | None = 0.0,
    frontier_relevance_score: float | int | None = 0.0,
    operator_relevance_score: float | int | None = 0.0,
    staleness_status: str = "active",
    why_it_matters: str | None = None,
    expiry_hint: str | None = None,
    first_seen_at: str | None = None,
    last_seen_at: str | None = None,
    atom_key: str | None = None,
) -> dict:
    clean_atom_type = _normalize_choice(atom_type, ATOM_TYPES, "atom_type")
    clean_claim = _clean_required(claim, "claim")
    clean_evidence_quote = _clean_required(evidence_quote, "evidence_quote")
    clean_source_post_ids = _normalize_int_list(source_post_ids)
    clean_source_urls = _normalize_string_list(source_urls)
    if not clean_source_post_ids:
        raise ValueError("source_post_ids must include at least one id")
    if not clean_source_urls:
        raise ValueError("source_urls must include at least one URL")
    clean_staleness = _normalize_choice(staleness_status, STALENESS_STATUSES, "staleness_status")
    now = _now_iso()
    first_seen = first_seen_at or now
    last_seen = last_seen_at or first_seen
    clean_atom_key = atom_key or build_atom_key(
        atom_type=clean_atom_type,
        claim=clean_claim,
        source_post_ids=clean_source_post_ids,
    )
    connection.execute(
        """
        INSERT INTO knowledge_atoms (
            atom_key,
            extraction_batch_id,
            week_label,
            atom_type,
            claim,
            summary,
            evidence_quote,
            source_post_ids_json,
            source_urls_json,
            entities_json,
            tools_json,
            models_json,
            practices_json,
            confidence,
            novelty_score,
            practical_utility_score,
            frontier_relevance_score,
            operator_relevance_score,
            staleness_status,
            why_it_matters,
            expiry_hint,
            first_seen_at,
            last_seen_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(atom_key) DO UPDATE SET
            extraction_batch_id = excluded.extraction_batch_id,
            week_label = COALESCE(excluded.week_label, knowledge_atoms.week_label),
            atom_type = excluded.atom_type,
            claim = excluded.claim,
            summary = excluded.summary,
            evidence_quote = excluded.evidence_quote,
            source_post_ids_json = excluded.source_post_ids_json,
            source_urls_json = excluded.source_urls_json,
            entities_json = excluded.entities_json,
            tools_json = excluded.tools_json,
            models_json = excluded.models_json,
            practices_json = excluded.practices_json,
            confidence = excluded.confidence,
            novelty_score = excluded.novelty_score,
            practical_utility_score = excluded.practical_utility_score,
            frontier_relevance_score = excluded.frontier_relevance_score,
            operator_relevance_score = excluded.operator_relevance_score,
            staleness_status = excluded.staleness_status,
            why_it_matters = excluded.why_it_matters,
            expiry_hint = excluded.expiry_hint,
            first_seen_at = CASE
                WHEN knowledge_atoms.first_seen_at <= excluded.first_seen_at
                THEN knowledge_atoms.first_seen_at
                ELSE excluded.first_seen_at
            END,
            last_seen_at = CASE
                WHEN knowledge_atoms.last_seen_at >= excluded.last_seen_at
                THEN knowledge_atoms.last_seen_at
                ELSE excluded.last_seen_at
            END,
            updated_at = excluded.updated_at
        """,
        (
            clean_atom_key,
            extraction_batch_id,
            _clean_optional(week_label),
            clean_atom_type,
            clean_claim,
            _clean_optional(summary) or "",
            clean_evidence_quote,
            json.dumps(clean_source_post_ids, ensure_ascii=False),
            json.dumps(clean_source_urls, ensure_ascii=False),
            _json_string_array(entities),
            _json_string_array(tools),
            _json_string_array(models),
            _json_string_array(practices),
            _score(confidence, "confidence"),
            _score(novelty_score, "novelty_score"),
            _score(practical_utility_score, "practical_utility_score"),
            _score(frontier_relevance_score, "frontier_relevance_score"),
            _score(operator_relevance_score, "operator_relevance_score"),
            clean_staleness,
            _clean_optional(why_it_matters) or "",
            _clean_optional(expiry_hint),
            first_seen,
            last_seen,
            now,
            now,
        ),
    )
    connection.commit()
    rows = fetch_knowledge_atoms(connection, atom_key=clean_atom_key, limit=1)
    if not rows:
        raise RuntimeError("knowledge atom could not be read back")
    return rows[0]


def fetch_knowledge_atoms(
    connection: sqlite3.Connection,
    *,
    atom_id: int | None = None,
    atom_key: str | None = None,
    week_label: str | None = None,
    atom_type: str | None = None,
    staleness_status: str | None = None,
    extraction_batch_id: int | None = None,
    limit: int = 20,
) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []
    if atom_id is not None:
        clauses.append("id = ?")
        params.append(int(atom_id))
    if atom_key:
        clauses.append("atom_key = ?")
        params.append(str(atom_key).strip())
    if week_label:
        clauses.append("week_label = ?")
        params.append(str(week_label).strip())
    if atom_type:
        clauses.append("atom_type = ?")
        params.append(_normalize_choice(atom_type, ATOM_TYPES, "atom_type"))
    if staleness_status:
        clauses.append("staleness_status = ?")
        params.append(_normalize_choice(staleness_status, STALENESS_STATUSES, "staleness_status"))
    if extraction_batch_id is not None:
        clauses.append("extraction_batch_id = ?")
        params.append(int(extraction_batch_id))
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor = connection.execute(
        f"""
        SELECT *
        FROM knowledge_atoms
        {where_sql}
        ORDER BY last_seen_at DESC, id DESC
        LIMIT ?
        """,
        (*params, max(1, int(limit or 20))),
    )
    return _cursor_to_atoms(cursor)
