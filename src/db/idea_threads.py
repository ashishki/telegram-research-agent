import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterable


THREAD_STATUSES = {
    "active",
    "stale",
    "superseded",
    "resolved",
    "hype_only",
    "production_pattern",
}
THREAD_ATOM_RELATIONS = {"supports", "contradicts", "supersedes", "related"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _normalize_strings(values: Iterable[str] | str | None) -> list[str]:
    if isinstance(values, str):
        values = (values,)
    result: list[str] = []
    for value in values or ():
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


def _json_array(values: Iterable[str] | str | None) -> str:
    return json.dumps(_normalize_strings(values), ensure_ascii=False)


def _parse_array(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if item is not None]


def _score(value: float | int | None, field_name: str) -> float:
    score = float(value or 0.0)
    if score < 0.0 or score > 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return score


def _row_to_thread(columns: list[str], row: sqlite3.Row | tuple) -> dict:
    values = dict(zip(columns, row))
    return {
        "id": int(values["id"]),
        "title": values["title"],
        "slug": values["slug"],
        "summary": values["summary"],
        "status": values["status"],
        "first_seen_at": values["first_seen_at"],
        "last_seen_at": values["last_seen_at"],
        "momentum_7d": float(values["momentum_7d"] or 0.0),
        "momentum_30d": float(values["momentum_30d"] or 0.0),
        "momentum_90d": float(values["momentum_90d"] or 0.0),
        "atom_count": int(values["atom_count"] or 0),
        "source_channel_count": int(values["source_channel_count"] or 0),
        "source_channels": _parse_array(values["source_channels_json"]),
        "key_entities": _parse_array(values["key_entities_json"]),
        "current_claims": _parse_array(values["current_claims_json"]),
        "superseded_claims": _parse_array(values["superseded_claims_json"]),
        "contradictions": _parse_array(values["contradictions_json"]),
        "created_at": values["created_at"],
        "updated_at": values["updated_at"],
    }


def _cursor_to_threads(cursor: sqlite3.Cursor) -> list[dict]:
    columns = [description[0] for description in cursor.description or []]
    return [_row_to_thread(columns, row) for row in cursor.fetchall()]


def upsert_idea_thread(
    connection: sqlite3.Connection,
    *,
    slug: str,
    title: str,
    summary: str,
    status: str,
    first_seen_at: str,
    last_seen_at: str,
    momentum_7d: float,
    momentum_30d: float,
    momentum_90d: float,
    atom_count: int,
    source_channels: Iterable[str] | str | None,
    key_entities: Iterable[str] | str | None,
    current_claims: Iterable[str] | str | None,
    superseded_claims: Iterable[str] | str | None = None,
    contradictions: Iterable[str] | str | None = None,
    updated_at: str | None = None,
) -> dict:
    clean_slug = _clean_required(slug, "slug")
    clean_title = _clean_required(title, "title")
    clean_status = _normalize_choice(status, THREAD_STATUSES, "status")
    channels = _normalize_strings(source_channels)
    timestamp = updated_at or _now_iso()
    connection.execute(
        """
        INSERT INTO idea_threads (
            title,
            slug,
            summary,
            status,
            first_seen_at,
            last_seen_at,
            momentum_7d,
            momentum_30d,
            momentum_90d,
            atom_count,
            source_channel_count,
            source_channels_json,
            key_entities_json,
            current_claims_json,
            superseded_claims_json,
            contradictions_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            title = excluded.title,
            summary = excluded.summary,
            status = excluded.status,
            first_seen_at = excluded.first_seen_at,
            last_seen_at = excluded.last_seen_at,
            momentum_7d = excluded.momentum_7d,
            momentum_30d = excluded.momentum_30d,
            momentum_90d = excluded.momentum_90d,
            atom_count = excluded.atom_count,
            source_channel_count = excluded.source_channel_count,
            source_channels_json = excluded.source_channels_json,
            key_entities_json = excluded.key_entities_json,
            current_claims_json = excluded.current_claims_json,
            superseded_claims_json = excluded.superseded_claims_json,
            contradictions_json = excluded.contradictions_json,
            updated_at = excluded.updated_at
        """,
        (
            clean_title,
            clean_slug,
            str(summary or "").strip(),
            clean_status,
            _clean_required(first_seen_at, "first_seen_at"),
            _clean_required(last_seen_at, "last_seen_at"),
            _score(momentum_7d, "momentum_7d"),
            _score(momentum_30d, "momentum_30d"),
            _score(momentum_90d, "momentum_90d"),
            max(0, int(atom_count or 0)),
            len(channels),
            _json_array(channels),
            _json_array(key_entities),
            _json_array(current_claims),
            _json_array(superseded_claims),
            _json_array(contradictions),
            timestamp,
            timestamp,
        ),
    )
    connection.commit()
    rows = fetch_idea_threads(connection, slug=clean_slug, limit=1)
    if not rows:
        raise RuntimeError("idea thread could not be read back")
    return rows[0]


def link_idea_thread_atom(
    connection: sqlite3.Connection,
    *,
    thread_id: int,
    atom_id: int,
    relation: str = "supports",
    created_at: str | None = None,
) -> None:
    clean_relation = _normalize_choice(relation, THREAD_ATOM_RELATIONS, "relation")
    connection.execute(
        """
        DELETE FROM idea_thread_atoms
        WHERE atom_id = ? AND thread_id != ?
        """,
        (int(atom_id), int(thread_id)),
    )
    connection.execute(
        """
        INSERT INTO idea_thread_atoms (thread_id, atom_id, relation, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(thread_id, atom_id) DO UPDATE SET
            relation = excluded.relation
        """,
        (int(thread_id), int(atom_id), clean_relation, created_at or _now_iso()),
    )
    connection.commit()


def fetch_idea_threads(
    connection: sqlite3.Connection,
    *,
    slug: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []
    if slug:
        clauses.append("slug = ?")
        params.append(str(slug).strip())
    if status:
        clauses.append("status = ?")
        params.append(_normalize_choice(status, THREAD_STATUSES, "status"))
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cursor = connection.execute(
        f"""
        SELECT *
        FROM idea_threads
        {where_sql}
        ORDER BY momentum_30d DESC, last_seen_at DESC, atom_count DESC, title ASC
        LIMIT ?
        """,
        (*params, max(1, int(limit or 20))),
    )
    return _cursor_to_threads(cursor)


def fetch_idea_thread_atoms(
    connection: sqlite3.Connection,
    *,
    thread_id: int,
    limit: int = 50,
) -> list[dict]:
    cursor = connection.execute(
        """
        SELECT
            idea_thread_atoms.relation,
            knowledge_atoms.*
        FROM idea_thread_atoms
        JOIN knowledge_atoms ON knowledge_atoms.id = idea_thread_atoms.atom_id
        WHERE idea_thread_atoms.thread_id = ?
        ORDER BY knowledge_atoms.last_seen_at DESC, knowledge_atoms.id DESC
        LIMIT ?
        """,
        (int(thread_id), max(1, int(limit or 50))),
    )
    columns = [description[0] for description in cursor.description or []]
    rows = []
    for row in cursor.fetchall():
        values = dict(zip(columns, row))
        rows.append(
            {
                "id": int(values["id"]),
                "relation": values["relation"],
                "atom_type": values["atom_type"],
                "claim": values["claim"],
                "evidence_quote": values["evidence_quote"],
                "source_urls": _parse_array(values["source_urls_json"]),
                "source_post_ids": _parse_array(values["source_post_ids_json"]),
                "entities": _parse_array(values["entities_json"]),
                "staleness_status": values["staleness_status"],
                "confidence": float(values["confidence"] or 0.0),
                "practical_utility_score": float(values["practical_utility_score"] or 0.0),
                "first_seen_at": values["first_seen_at"],
                "last_seen_at": values["last_seen_at"],
            }
        )
    return rows
