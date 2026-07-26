from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from db.archive_documents import archive_documents_for_row


SELECTIVE_ENRICHMENT_SCHEMA_VERSION = "selective_enrichment_batch.v1"
DEFAULT_MAX_COST_USD = 5.0
DEFAULT_MAX_MODEL_CALLS = 100
DEFAULT_MAX_RETRIES = 1
DEFAULT_COST_PER_ATTEMPT_USD = 0.05

PRIORITY_SOURCES: tuple[str, ...] = (
    "reaction",
    "repeated_search_return",
    "cited_answer",
    "watch_topic",
    "active_project",
    "repeated_signal",
    "manual_save",
)

SOURCE_ALIASES = {
    "reactions": "reaction",
    "search_return": "repeated_search_return",
    "repeated_search_returns": "repeated_search_return",
    "answer_citation": "cited_answer",
    "cited_answers": "cited_answer",
    "watch_topics": "watch_topic",
    "project": "active_project",
    "active_projects": "active_project",
    "repeated_signals": "repeated_signal",
    "manual_saved_post": "manual_save",
    "manual_saves": "manual_save",
}


class SelectiveEnrichmentError(ValueError):
    """Raised when a selective enrichment queue or receipt is invalid."""


@dataclass(frozen=True)
class EnrichmentSignal:
    post_id: int
    source: str
    weight: float = 1.0


@dataclass(frozen=True)
class EnrichmentQueueItem:
    post_id: int
    primary_source: str
    priority_rank: int
    priority_sources: tuple[str, ...]
    signal_count: int
    source_count: int
    priority_score: float

    def as_dict(self) -> dict[str, object]:
        return {
            "post_id": self.post_id,
            "primary_source": self.primary_source,
            "priority_rank": self.priority_rank,
            "priority_sources": list(self.priority_sources),
            "signal_count": self.signal_count,
            "source_count": self.source_count,
            "priority_score": self.priority_score,
        }


@dataclass(frozen=True)
class EnrichmentBudget:
    max_cost_usd: float = DEFAULT_MAX_COST_USD
    max_model_calls: int = DEFAULT_MAX_MODEL_CALLS
    max_retries: int = DEFAULT_MAX_RETRIES
    estimated_cost_per_attempt_usd: float = DEFAULT_COST_PER_ATTEMPT_USD

    def normalized(self) -> "EnrichmentBudget":
        max_cost = float(self.max_cost_usd)
        cost_per_attempt = float(self.estimated_cost_per_attempt_usd)
        max_calls = int(self.max_model_calls)
        max_retries = int(self.max_retries)
        if not math.isfinite(max_cost) or max_cost < 0:
            raise SelectiveEnrichmentError("max_cost_usd must be a non-negative finite number")
        if not math.isfinite(cost_per_attempt) or cost_per_attempt < 0:
            raise SelectiveEnrichmentError(
                "estimated_cost_per_attempt_usd must be a non-negative finite number"
            )
        if max_calls < 0:
            raise SelectiveEnrichmentError("max_model_calls must be non-negative")
        if max_retries < 0:
            raise SelectiveEnrichmentError("max_retries must be non-negative")
        return EnrichmentBudget(
            max_cost_usd=max_cost,
            max_model_calls=max_calls,
            max_retries=max_retries,
            estimated_cost_per_attempt_usd=cost_per_attempt,
        )


Extractor = Callable[[EnrichmentQueueItem], Mapping[str, object]]


def build_enrichment_queue(
    signals: Sequence[EnrichmentSignal | Mapping[str, object]],
    *,
    limit: int | None = None,
) -> tuple[EnrichmentQueueItem, ...]:
    """Build a deterministic selective-enrichment queue from priority signals."""

    grouped: dict[int, list[EnrichmentSignal]] = defaultdict(list)
    for raw_signal in signals:
        signal = _coerce_signal(raw_signal)
        grouped[signal.post_id].append(signal)

    items: list[EnrichmentQueueItem] = []
    for post_id, post_signals in grouped.items():
        sources = tuple(
            sorted(
                {signal.source for signal in post_signals},
                key=lambda source: _source_rank(source),
            )
        )
        primary = sources[0]
        items.append(
            EnrichmentQueueItem(
                post_id=post_id,
                primary_source=primary,
                priority_rank=_source_rank(primary),
                priority_sources=sources,
                signal_count=len(post_signals),
                source_count=len(sources),
                priority_score=round(sum(signal.weight for signal in post_signals), 6),
            )
        )

    ordered = tuple(
        sorted(
            items,
            key=lambda item: (
                item.priority_rank,
                -item.source_count,
                -item.signal_count,
                -item.priority_score,
                item.post_id,
            ),
        )
    )
    if limit is None:
        return ordered
    return ordered[: max(0, int(limit))]


def run_selective_enrichment_batch(
    connection: sqlite3.Connection,
    queue: Sequence[EnrichmentQueueItem | Mapping[str, object]],
    *,
    extractor: Extractor,
    budget: EnrichmentBudget | None = None,
) -> dict[str, object]:
    """Run a bounded selective-enrichment batch with an injected extractor.

    The function owns cost/retry accounting and search-availability receipts.
    The extractor is deliberately injected so tests and future runners can use
    this contract without this module invoking an LLM provider directly.
    """

    clean_budget = (budget or EnrichmentBudget()).normalized()
    items = tuple(_coerce_queue_item(item) for item in queue)
    attempts_used = 0
    estimated_cost = 0.0
    item_receipts: list[dict[str, object]] = []
    stopped_reason: str | None = None

    for item in items:
        post_attempts = 0
        last_failure_reason: str | None = None
        while post_attempts <= clean_budget.max_retries:
            cap_reason = _budget_cap_reason(
                attempts_used=attempts_used,
                estimated_cost=estimated_cost,
                budget=clean_budget,
            )
            if cap_reason is not None:
                stopped_reason = cap_reason
                item_receipts.append(
                    _item_receipt(
                        item,
                        status="stopped_budget",
                        attempts=post_attempts,
                        failure_reason=cap_reason,
                        archive_search_available=_archive_search_available(connection, item.post_id),
                    )
                )
                break

            attempts_used += 1
            post_attempts += 1
            estimated_cost = round(
                estimated_cost + clean_budget.estimated_cost_per_attempt_usd,
                8,
            )
            try:
                payload = extractor(item)
            except Exception:
                last_failure_reason = "extractor_failed"
                if post_attempts <= clean_budget.max_retries:
                    continue
                item_receipts.append(
                    _item_receipt(
                        item,
                        status="failed",
                        attempts=post_attempts,
                        failure_reason=last_failure_reason,
                        archive_search_available=_archive_search_available(connection, item.post_id),
                    )
                )
                break

            item_receipts.append(
                _item_receipt(
                    item,
                    status="succeeded",
                    attempts=post_attempts,
                    failure_reason=None,
                    archive_search_available=_archive_search_available(connection, item.post_id),
                    extracted_kinds=_extracted_kinds(payload),
                )
            )
            break

        if stopped_reason is not None:
            break

    counts = _receipt_counts(
        queued_count=len(items),
        attempts_used=attempts_used,
        estimated_cost=estimated_cost,
        item_receipts=item_receipts,
    )
    receipt = {
        "schema_version": SELECTIVE_ENRICHMENT_SCHEMA_VERSION,
        "status": _batch_status(item_receipts, queued_count=len(items), stopped_reason=stopped_reason),
        "budget": {
            "max_cost_usd": clean_budget.max_cost_usd,
            "max_model_calls": clean_budget.max_model_calls,
            "max_retries": clean_budget.max_retries,
            "estimated_cost_per_attempt_usd": clean_budget.estimated_cost_per_attempt_usd,
            "cost_cap_exceeded": estimated_cost > clean_budget.max_cost_usd,
        },
        "counts": counts,
        "items": item_receipts,
        "stopped_reason": stopped_reason,
        "privacy": {
            "raw_text_included": False,
            "source_urls_included": False,
            "provider_payload_included": False,
        },
    }
    validate_selective_enrichment_receipt(receipt)
    return receipt


def validate_selective_enrichment_receipt(receipt: Mapping[str, object]) -> dict[str, object]:
    if receipt.get("schema_version") != SELECTIVE_ENRICHMENT_SCHEMA_VERSION:
        raise SelectiveEnrichmentError("selective enrichment receipt schema_version is invalid")
    if receipt.get("status") not in {"complete", "partial", "stopped_budget", "empty"}:
        raise SelectiveEnrichmentError("selective enrichment receipt status is invalid")
    counts = receipt.get("counts")
    if not isinstance(counts, Mapping):
        raise SelectiveEnrichmentError("selective enrichment counts must be an object")
    for field in (
        "queued_posts",
        "attempted_posts",
        "model_calls",
        "succeeded_posts",
        "failed_posts",
        "stopped_budget_posts",
        "archive_search_available_after_failure",
    ):
        _nonnegative_int(counts.get(field), f"counts.{field}")
    estimated_cost = counts.get("estimated_cost_usd")
    if not isinstance(estimated_cost, (int, float)) or isinstance(estimated_cost, bool) or estimated_cost < 0:
        raise SelectiveEnrichmentError("counts.estimated_cost_usd must be non-negative")
    budget = receipt.get("budget")
    if not isinstance(budget, Mapping):
        raise SelectiveEnrichmentError("selective enrichment budget must be an object")
    items = receipt.get("items")
    if not isinstance(items, list):
        raise SelectiveEnrichmentError("selective enrichment items must be a list")
    privacy = receipt.get("privacy")
    if not isinstance(privacy, Mapping) or privacy.get("raw_text_included") is not False:
        raise SelectiveEnrichmentError("selective enrichment receipt must exclude raw text")
    return dict(receipt)


def _coerce_signal(raw_signal: EnrichmentSignal | Mapping[str, object]) -> EnrichmentSignal:
    if isinstance(raw_signal, EnrichmentSignal):
        signal = raw_signal
    elif isinstance(raw_signal, Mapping):
        signal = EnrichmentSignal(
            post_id=int(raw_signal.get("post_id") or 0),
            source=str(raw_signal.get("source") or ""),
            weight=float(raw_signal.get("weight") or 1.0),
        )
    else:
        raise SelectiveEnrichmentError("enrichment signal must be a mapping or EnrichmentSignal")
    if signal.post_id <= 0:
        raise SelectiveEnrichmentError("post_id must be positive")
    source = _normalize_source(signal.source)
    if not math.isfinite(signal.weight) or signal.weight <= 0:
        raise SelectiveEnrichmentError("signal weight must be positive")
    return EnrichmentSignal(post_id=signal.post_id, source=source, weight=signal.weight)


def _coerce_queue_item(raw_item: EnrichmentQueueItem | Mapping[str, object]) -> EnrichmentQueueItem:
    if isinstance(raw_item, EnrichmentQueueItem):
        return raw_item
    if not isinstance(raw_item, Mapping):
        raise SelectiveEnrichmentError("queue item must be a mapping or EnrichmentQueueItem")
    post_id = int(raw_item.get("post_id") or 0)
    sources = tuple(
        _normalize_source(source)
        for source in _string_list(raw_item.get("priority_sources") or raw_item.get("primary_source"))
    )
    if post_id <= 0 or not sources:
        raise SelectiveEnrichmentError("queue item requires post_id and priority source")
    primary = sources[0]
    return EnrichmentQueueItem(
        post_id=post_id,
        primary_source=primary,
        priority_rank=_source_rank(primary),
        priority_sources=sources,
        signal_count=max(1, int(raw_item.get("signal_count") or 1)),
        source_count=len(set(sources)),
        priority_score=float(raw_item.get("priority_score") or 1.0),
    )


def _normalize_source(source: str) -> str:
    normalized = str(source or "").strip().lower().replace("-", "_")
    normalized = SOURCE_ALIASES.get(normalized, normalized)
    if normalized not in PRIORITY_SOURCES:
        raise SelectiveEnrichmentError(f"unsupported enrichment signal source: {source!r}")
    return normalized


def _source_rank(source: str) -> int:
    return PRIORITY_SOURCES.index(source)


def _budget_cap_reason(
    *,
    attempts_used: int,
    estimated_cost: float,
    budget: EnrichmentBudget,
) -> str | None:
    if attempts_used + 1 > budget.max_model_calls:
        return "model_call_cap_exceeded"
    next_cost = round(estimated_cost + budget.estimated_cost_per_attempt_usd, 8)
    if next_cost > budget.max_cost_usd:
        return "cost_cap_exceeded"
    return None


def _item_receipt(
    item: EnrichmentQueueItem,
    *,
    status: str,
    attempts: int,
    failure_reason: str | None,
    archive_search_available: bool,
    extracted_kinds: Mapping[str, int] | None = None,
) -> dict[str, object]:
    return {
        "post_id": item.post_id,
        "primary_source": item.primary_source,
        "priority_sources": list(item.priority_sources),
        "status": status,
        "attempts": attempts,
        "failure_reason": failure_reason,
        "archive_search_available": archive_search_available,
        "extracted_kinds": dict(extracted_kinds or {}),
    }


def _receipt_counts(
    *,
    queued_count: int,
    attempts_used: int,
    estimated_cost: float,
    item_receipts: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    failed_or_stopped = [
        item
        for item in item_receipts
        if item.get("status") in {"failed", "stopped_budget"}
    ]
    return {
        "queued_posts": queued_count,
        "attempted_posts": sum(1 for item in item_receipts if int(item.get("attempts") or 0) > 0),
        "model_calls": attempts_used,
        "estimated_cost_usd": round(estimated_cost, 8),
        "succeeded_posts": sum(1 for item in item_receipts if item.get("status") == "succeeded"),
        "failed_posts": sum(1 for item in item_receipts if item.get("status") == "failed"),
        "stopped_budget_posts": sum(1 for item in item_receipts if item.get("status") == "stopped_budget"),
        "archive_search_available_after_failure": sum(
            1
            for item in failed_or_stopped
            if item.get("archive_search_available") is True
        ),
    }


def _batch_status(
    item_receipts: Sequence[Mapping[str, object]],
    *,
    queued_count: int,
    stopped_reason: str | None,
) -> str:
    if queued_count == 0:
        return "empty"
    if stopped_reason is not None:
        return "stopped_budget"
    if any(item.get("status") == "failed" for item in item_receipts):
        return "partial"
    return "complete"


def _archive_search_available(connection: sqlite3.Connection, post_id: int) -> bool:
    if (
        not _table_exists(connection, "posts")
        or not _table_exists(connection, "raw_posts")
        or not _table_exists(connection, "posts_fts")
    ):
        return False
    rows = _fetch_mappings(
        connection,
        """
        SELECT
            p.id AS post_id,
            p.raw_post_id,
            p.channel_username,
            p.posted_at,
            p.content,
            p.language_detected,
            r.channel_id,
            r.message_id,
            r.message_url,
            r.forward_from
        FROM posts p
        JOIN raw_posts r ON r.id = p.raw_post_id
        WHERE p.id = ?
        LIMIT 1
        """,
        (post_id,),
    )
    if not rows:
        return False
    documents, exclusion = archive_documents_for_row(rows[0])
    if exclusion is not None or not documents:
        return False
    row = connection.execute(
        "SELECT 1 FROM posts_fts WHERE rowid = ? LIMIT 1",
        (post_id,),
    ).fetchone()
    return row is not None


def _extracted_kinds(payload: Mapping[str, object]) -> dict[str, int]:
    result: dict[str, int] = {}
    for key in (
        "claims",
        "cases",
        "tools",
        "practices",
        "warnings",
        "entities",
        "topic_candidates",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            result[key] = len(value)
    return result


def _fetch_mappings(
    connection: sqlite3.Connection,
    sql: str,
    params: Sequence[object] = (),
) -> list[dict[str, object]]:
    cursor = connection.execute(sql, tuple(params))
    columns = [description[0] for description in cursor.description or ()]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type IN ('table', 'view')
          AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _string_list(value: object) -> list[str]:
    if value in (None, "", [], ()):
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [str(item) for item in value]  # type: ignore[arg-type]
    except TypeError:
        return [str(value)]


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise SelectiveEnrichmentError(f"{field} must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise SelectiveEnrichmentError(f"{field} must be a non-negative integer") from exc
    if result < 0:
        raise SelectiveEnrichmentError(f"{field} must be a non-negative integer")
    return result
