from __future__ import annotations

import sqlite3
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from output.intelligence_retrieval_items import (
    IntelligenceRetrievalItem,
    search_retrieval_items,
)


TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё][0-9A-Za-zА-Яа-яЁё_-]{1,}")
RAW_ITEM_TYPES = {"raw_post", "telegram_post", "raw_telegram_post"}
RRF_K = 60
FTS_CANDIDATE_MULTIPLIER = 4
TERM_EXPANSIONS = (
    (("rag", "ретрив", "поиск", "контекст"), ("retrieval", "grounding", "context", "semantic", "vector")),
    (("eval", "evaluation", "оценк", "эваль", "эвал"), ("eval", "evaluation", "gate", "guardrail", "benchmark", "regression")),
    (("agent", "агент"), ("agent", "agentic", "coding", "workflow")),
    (("mvp", "радар", "продукт", "рынок", "маркет"), ("mvp", "radar", "opportunity", "market", "demand", "validation")),
    (("действ", "задач", "делать", "next"), ("action", "next", "step", "project", "implementation")),
    (("feedback", "фидбек", "обратн"), ("feedback", "useful", "wrong_priority", "applied", "tried")),
)


@dataclass(frozen=True)
class CuratedSearchDecision:
    mode: str
    vector_status: str
    raw_telegram_status: str
    reason: str

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "vector_status": self.vector_status,
            "raw_telegram_status": self.raw_telegram_status,
            "reason": self.reason,
        }


DEFAULT_SEARCH_DECISION = CuratedSearchDecision(
    mode="curated_deterministic_plus_sqlite_fts",
    vector_status="deferred_until_curated_search_misses_are_proven",
    raw_telegram_status="disabled",
    reason=(
        "HPI-9-lite keeps SQLite/JSON curated objects as source of truth. "
        "The prototype adds transient SQLite FTS over filtered curated items; "
        "it does not index raw Telegram posts or create a vector store."
    ),
)


def search_curated_semantic_items(
    items: Iterable[IntelligenceRetrievalItem],
    query: str,
    *,
    filters: Mapping[str, Any] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search curated retrieval items with deterministic scoring plus transient FTS.

    This is intentionally not a raw-post or vector RAG layer. The caller passes
    the curated projection, filters are applied before indexing, and the FTS
    table is in-memory for the current request only.
    """
    clean_query = " ".join(str(query or "").split())
    clean_limit = max(1, int(limit or 10))
    filtered_items = [
        item for item in items
        if _is_curated_item(item) and _matches_filters(item, filters or {})
    ]
    deterministic = search_retrieval_items(filtered_items, clean_query, filters={}, limit=clean_limit * FTS_CANDIDATE_MULTIPLIER)
    fts_ranked = _fts_search(filtered_items, clean_query, limit=clean_limit * FTS_CANDIDATE_MULTIPLIER)
    if not fts_ranked:
        return [
            {**result, "retrieval_mode": "curated_deterministic_fallback"}
            for result in deterministic[:clean_limit]
        ]

    item_by_id = {item.id: item for item in filtered_items}
    ranked: dict[str, dict] = {}
    for rank, result in enumerate(deterministic, start=1):
        item_id = str(result.get("id") or "")
        if not item_id:
            continue
        ranked[item_id] = {
            "item": item_by_id.get(item_id),
            "deterministic_rank": rank,
            "fts_rank": None,
            "deterministic_score": float(result.get("score") or 0.0),
            "fts_score": 0.0,
        }
    for rank, row in enumerate(fts_ranked, start=1):
        item = row["item"]
        entry = ranked.setdefault(
            item.id,
            {
                "item": item,
                "deterministic_rank": None,
                "fts_rank": rank,
                "deterministic_score": 0.0,
                "fts_score": float(row.get("score") or 0.0),
            },
        )
        entry["fts_rank"] = rank
        entry["fts_score"] = float(row.get("score") or 0.0)

    merged = sorted(
        ranked.values(),
        key=lambda entry: (
            _rrf_score(entry.get("deterministic_rank")) + _rrf_score(entry.get("fts_rank")),
            float(entry.get("deterministic_score") or 0.0),
            float(entry.get("fts_score") or 0.0),
            str(entry["item"].updated_at or entry["item"].created_at or "") if entry.get("item") else "",
            str(entry["item"].id) if entry.get("item") else "",
        ),
        reverse=True,
    )
    results = []
    for entry in merged[:clean_limit]:
        item = entry.get("item")
        if not isinstance(item, IntelligenceRetrievalItem):
            continue
        mode = "curated_deterministic_fts" if entry.get("deterministic_rank") and entry.get("fts_rank") else (
            "curated_fts" if entry.get("fts_rank") else "curated_deterministic"
        )
        results.append(
            {
                **_public_item_dict(
                    item,
                    score=round(
                        _rrf_score(entry.get("deterministic_rank")) + _rrf_score(entry.get("fts_rank")),
                        6,
                    ),
                ),
                "retrieval_mode": mode,
            }
        )
    return results


def retrieval_decision_note() -> dict:
    return DEFAULT_SEARCH_DECISION.as_dict()


def _fts_search(items: list[IntelligenceRetrievalItem], query: str, *, limit: int) -> list[dict]:
    terms = _expanded_query_terms(query)
    if not items or not terms:
        return []
    match_query = " OR ".join(f"{term}*" for term in terms)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(":memory:")
        connection.execute(
            """
            CREATE VIRTUAL TABLE curated_items_fts
            USING fts5(item_id UNINDEXED, title, summary, text, tokenize='unicode61');
            """
        )
        connection.executemany(
            """
            INSERT INTO curated_items_fts(rowid, item_id, title, summary, text)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    index,
                    item.id,
                    item.title or "",
                    item.summary or "",
                    item.text or "",
                )
                for index, item in enumerate(items, start=1)
            ],
        )
        rows = connection.execute(
            """
            SELECT rowid, item_id, bm25(curated_items_fts, 0.0, 8.0, 4.0, 1.0) AS rank
            FROM curated_items_fts
            WHERE curated_items_fts MATCH ?
            ORDER BY rank ASC
            LIMIT ?
            """,
            (match_query, max(1, int(limit or 10))),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        if connection is not None:
            connection.close()

    by_rowid = {index: item for index, item in enumerate(items, start=1)}
    results = []
    for position, row in enumerate(rows, start=1):
        item = by_rowid.get(int(row[0]))
        if item is None:
            continue
        results.append(
            {
                "item": item,
                "score": 1.0 / (position + abs(float(row[2] or 0.0))),
            }
        )
    return results


def _expanded_query_terms(query: str) -> list[str]:
    terms = _query_terms(query)
    haystack = " ".join(terms).casefold()
    expanded = list(terms)
    for markers, additions in TERM_EXPANSIONS:
        if any(marker in haystack for marker in markers):
            expanded.extend(additions)
    return _dedupe_terms(expanded)


def _query_terms(query: str) -> list[str]:
    return _dedupe_terms(match.group(0).casefold() for match in TOKEN_RE.finditer(str(query or "")))


def _dedupe_terms(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = re.sub(r"[^0-9A-Za-zА-Яа-яЁё]+", "", str(value or "").casefold())
        if len(clean) < 2 or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result[:24]


def _is_curated_item(item: IntelligenceRetrievalItem) -> bool:
    return str(item.item_type or "").strip().lower() not in RAW_ITEM_TYPES


def _matches_filters(item: IntelligenceRetrievalItem, filters: Mapping[str, Any]) -> bool:
    for key in ("week_label", "item_type", "project_name", "thread_slug", "status"):
        value = filters.get(key)
        if value in (None, "", [], ()):
            continue
        accepted = {_normalize_filter_value(candidate) for candidate in _as_list(value)}
        if _normalize_filter_value(getattr(item, key)) not in accepted:
            return False
    return True


def _public_item_dict(item: IntelligenceRetrievalItem, *, score: float | None) -> dict:
    return {
        "id": item.id,
        "item_type": item.item_type,
        "week_label": item.week_label,
        "title": item.title,
        "summary": item.summary,
        "text": item.text,
        "source_refs": list(item.source_refs or []),
        "atom_ids": list(item.atom_ids or []),
        "thread_slug": item.thread_slug,
        "project_name": item.project_name,
        "score": score,
        "evidence_tier": item.evidence_tier,
        "verification_status": item.verification_status,
    }


def _rrf_score(rank: object) -> float:
    if not rank:
        return 0.0
    return 1.0 / (RRF_K + int(rank))


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _normalize_filter_value(value: object) -> str:
    return " ".join(str(value or "").split()).lower()
