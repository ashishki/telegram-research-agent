import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Iterable


MVP_KNOWLEDGE_ATOM_TYPES = {
    "market_signal",
    "workflow_pattern",
    "case_study",
    "opinion_shift",
}
IMPLEMENTATION_KNOWLEDGE_ATOM_TYPES = {
    "engineering_practice",
    "workflow_pattern",
}
PROJECT_KNOWLEDGE_ATOM_TYPES = {
    "engineering_practice",
    "workflow_pattern",
    "tool_release",
    "model_update",
    "case_study",
    "tutorial_resource",
    "risk_warning",
}
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


def _parse_array(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _week_start(week_label: str) -> datetime:
    year_str, week_str = str(week_label).split("-W", maxsplit=1)
    week_date = date.fromisocalendar(int(year_str), int(week_str), 1)
    return datetime.combine(week_date, datetime.min.time(), tzinfo=timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_atom_types(atom_types: Iterable[str] | None) -> list[str]:
    normalized = sorted({str(atom_type).strip() for atom_type in atom_types or () if str(atom_type).strip()})
    return normalized


def _keywords_match(corpus: str, keywords: Iterable[str] | None) -> bool:
    normalized = [str(keyword).strip().lower() for keyword in keywords or () if str(keyword).strip()]
    if not normalized:
        return True
    lowered = corpus.lower()
    return any(keyword in lowered for keyword in normalized)


def load_downstream_knowledge_threads(
    connection: sqlite3.Connection,
    *,
    atom_types: Iterable[str] | None = None,
    keywords: Iterable[str] | None = None,
    min_last_seen_at: str | None = None,
    limit: int = 8,
) -> list[dict]:
    if not _table_exists(connection, "idea_threads") or not _table_exists(connection, "idea_thread_atoms"):
        return []
    if not _table_exists(connection, "knowledge_atoms"):
        return []

    clauses = ["idea_threads.status NOT IN ('hype_only', 'resolved')"]
    params: list[object] = []
    normalized_types = _normalize_atom_types(atom_types)
    if normalized_types:
        placeholders = ",".join("?" for _ in normalized_types)
        clauses.append(f"knowledge_atoms.atom_type IN ({placeholders})")
        params.extend(normalized_types)
    if min_last_seen_at:
        clauses.append("idea_threads.last_seen_at >= ?")
        params.append(str(min_last_seen_at))
    where_sql = " AND ".join(clauses)
    rows = connection.execute(
        f"""
        SELECT
            idea_threads.id AS thread_id,
            idea_threads.title AS thread_title,
            idea_threads.slug AS thread_slug,
            idea_threads.summary AS thread_summary,
            idea_threads.status AS thread_status,
            idea_threads.first_seen_at AS thread_first_seen_at,
            idea_threads.last_seen_at AS thread_last_seen_at,
            idea_threads.momentum_30d AS thread_momentum_30d,
            idea_threads.source_channels_json AS thread_source_channels_json,
            idea_threads.key_entities_json AS thread_key_entities_json,
            idea_threads.current_claims_json AS thread_current_claims_json,
            idea_thread_atoms.relation AS atom_relation,
            knowledge_atoms.id AS atom_id,
            knowledge_atoms.atom_type AS atom_type,
            knowledge_atoms.claim AS atom_claim,
            knowledge_atoms.summary AS atom_summary,
            knowledge_atoms.evidence_quote AS atom_evidence_quote,
            knowledge_atoms.source_urls_json AS atom_source_urls_json,
            knowledge_atoms.source_post_ids_json AS atom_source_post_ids_json,
            knowledge_atoms.entities_json AS atom_entities_json,
            knowledge_atoms.tools_json AS atom_tools_json,
            knowledge_atoms.practices_json AS atom_practices_json,
            knowledge_atoms.confidence AS atom_confidence,
            knowledge_atoms.novelty_score AS atom_novelty_score,
            knowledge_atoms.practical_utility_score AS atom_practical_utility_score,
            knowledge_atoms.last_seen_at AS atom_last_seen_at
        FROM idea_threads
        JOIN idea_thread_atoms ON idea_thread_atoms.thread_id = idea_threads.id
        JOIN knowledge_atoms ON knowledge_atoms.id = idea_thread_atoms.atom_id
        WHERE {where_sql}
        ORDER BY
            idea_threads.momentum_30d DESC,
            idea_threads.last_seen_at DESC,
            knowledge_atoms.practical_utility_score DESC,
            knowledge_atoms.last_seen_at DESC,
            knowledge_atoms.id DESC
        """,
        params,
    ).fetchall()

    threads_by_slug: dict[str, dict] = {}
    for row in rows:
        slug = str(row["thread_slug"] or "")
        if not slug:
            continue
        thread = threads_by_slug.setdefault(
            slug,
            {
                "id": int(row["thread_id"]),
                "title": str(row["thread_title"] or ""),
                "slug": slug,
                "summary": str(row["thread_summary"] or ""),
                "status": str(row["thread_status"] or "active"),
                "first_seen_at": str(row["thread_first_seen_at"] or ""),
                "last_seen_at": str(row["thread_last_seen_at"] or ""),
                "momentum_30d": float(row["thread_momentum_30d"] or 0.0),
                "source_channels": _parse_array(row["thread_source_channels_json"]),
                "key_entities": _parse_array(row["thread_key_entities_json"]),
                "current_claims": _parse_array(row["thread_current_claims_json"]),
                "atoms": [],
            },
        )
        atom = {
            "id": int(row["atom_id"]),
            "relation": str(row["atom_relation"] or "supports"),
            "atom_type": str(row["atom_type"] or ""),
            "claim": str(row["atom_claim"] or ""),
            "summary": str(row["atom_summary"] or ""),
            "evidence_quote": str(row["atom_evidence_quote"] or ""),
            "source_urls": _parse_array(row["atom_source_urls_json"]),
            "source_post_ids": _parse_array(row["atom_source_post_ids_json"]),
            "entities": _parse_array(row["atom_entities_json"]),
            "tools": _parse_array(row["atom_tools_json"]),
            "practices": _parse_array(row["atom_practices_json"]),
            "confidence": float(row["atom_confidence"] or 0.0),
            "novelty_score": float(row["atom_novelty_score"] or 0.0),
            "practical_utility_score": float(row["atom_practical_utility_score"] or 0.0),
            "last_seen_at": str(row["atom_last_seen_at"] or ""),
        }
        thread["atoms"].append(atom)

    threads = []
    for thread in threads_by_slug.values():
        corpus = " ".join(
            [
                thread.get("title", ""),
                thread.get("summary", ""),
                " ".join(thread.get("key_entities") or []),
                " ".join(thread.get("current_claims") or []),
                " ".join(atom.get("claim", "") for atom in thread.get("atoms") or []),
                " ".join(term for atom in thread.get("atoms") or [] for term in atom.get("tools") or []),
                " ".join(term for atom in thread.get("atoms") or [] for term in atom.get("practices") or []),
                " ".join(term for atom in thread.get("atoms") or [] for term in atom.get("entities") or []),
            ]
        )
        if not _keywords_match(corpus, keywords):
            continue
        atom_types_seen = sorted({atom["atom_type"] for atom in thread["atoms"] if atom.get("atom_type")})
        source_urls = []
        for atom in thread["atoms"]:
            for url in atom.get("source_urls") or []:
                if url and url not in source_urls:
                    source_urls.append(url)
        thread["atom_types"] = atom_types_seen
        thread["source_atom_ids"] = [atom["id"] for atom in thread["atoms"]]
        thread["source_urls"] = source_urls
        threads.append(thread)

    threads.sort(
        key=lambda thread: (
            float(thread.get("momentum_30d") or 0.0),
            str(thread.get("last_seen_at") or ""),
            len(thread.get("source_atom_ids") or []),
        ),
        reverse=True,
    )
    return threads[: max(1, int(limit or 8))]


def evaluate_knowledge_freshness(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    atom_types: Iterable[str],
    max_age_days: int = 14,
) -> dict:
    if not _table_exists(connection, "idea_threads") or not _table_exists(connection, "knowledge_atoms"):
        return {
            "available": False,
            "gate_passed": True,
            "blocking_reasons": [],
            "latest_last_seen_at": "",
            "thread_count": 0,
            "prompt_context": "Knowledge Thread context unavailable; database tables are missing.",
        }
    week_start = _week_start(week_label)
    min_seen = (week_start - timedelta(days=max(1, int(max_age_days or 14)))).isoformat().replace("+00:00", "Z")
    threads = load_downstream_knowledge_threads(
        connection,
        atom_types=atom_types,
        min_last_seen_at=min_seen,
        limit=12,
    )
    latest_seen = ""
    for thread in threads:
        seen = str(thread.get("last_seen_at") or "")
        if seen > latest_seen:
            latest_seen = seen
    blocking_reasons = []
    if not threads:
        blocking_reasons.append(
            f"no fresh Knowledge Threads for atom types {', '.join(_normalize_atom_types(atom_types))}"
        )
    elif _parse_iso(latest_seen) is None:
        blocking_reasons.append("fresh Knowledge Threads have invalid last_seen_at values")
    return {
        "available": True,
        "gate_passed": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "latest_last_seen_at": latest_seen,
        "thread_count": len(threads),
        "prompt_context": format_knowledge_threads_for_prompt(threads),
    }


def format_knowledge_threads_for_prompt(threads: list[dict], *, limit: int = 8) -> str:
    if not threads:
        return "No downstream Knowledge Threads available."
    lines = []
    for thread in threads[: max(1, int(limit or 8))]:
        atoms = thread.get("atoms") or []
        first_atom = atoms[0] if atoms else {}
        claim = first_atom.get("claim") or (thread.get("current_claims") or [""])[0]
        source_urls = thread.get("source_urls") or []
        source_text = ", ".join(source_urls[:3]) if source_urls else "no source URLs"
        atom_ids = ", ".join(str(atom_id) for atom_id in (thread.get("source_atom_ids") or [])[:6])
        lines.append(
            f"- thread:{thread.get('slug')} | {thread.get('title')} | "
            f"status={thread.get('status')} | atom_types={','.join(thread.get('atom_types') or [])} | "
            f"atom_ids={atom_ids or 'none'} | claim={claim} | sources={source_text}"
        )
    return "\n".join(lines)
