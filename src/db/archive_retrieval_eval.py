from __future__ import annotations

import sqlite3
import time
from typing import Mapping, Sequence

from db.archive_search import ArchiveSearchError, ArchiveSearchResult, search_telegram_archive
from db.reaction_fast_lane import build_reaction_fast_lane_receipt


ARCHIVE_RETRIEVAL_EVAL_SCHEMA_VERSION = "archive_retrieval_eval.v1"

METRIC_FIELDS: tuple[str, ...] = (
    "hit_at_10",
    "mrr",
    "citation_precision",
    "stale_rejection",
    "no_answer_accuracy",
    "duplicate_top10_rate",
    "latency_ms_p95",
    "reacted_post_searchability",
)


class ArchiveRetrievalEvalError(ValueError):
    """Raised when retrieval evaluation input is malformed."""


def evaluate_archive_retrieval(
    connection: sqlite3.Connection,
    cases: Sequence[Mapping[str, object]],
    *,
    limit: int = 10,
) -> dict[str, object]:
    clean_limit = max(1, int(limit or 10))
    gold_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    gold_scores: list[dict[str, float | None]] = []
    candidate_duplicate_rates: list[float] = []
    gold_latencies: list[float] = []
    candidate_latencies: list[float] = []

    for case in cases:
        case_id = _required_string(case, "case_id")
        category = str(case.get("category") or "unknown").strip() or "unknown"
        query = _required_string(case, "query")
        is_human_approved = case.get("human_approved") is True
        is_gold = is_human_approved and _is_scoreable_gold_case(case)
        if is_human_approved and not is_gold:
            raise ArchiveRetrievalEvalError(
                f"{case_id} is human_approved but has no expected relevance, stale/forbidden, or no-answer labels"
            )
        started = time.perf_counter()
        error_type: str | None = None
        results: list[ArchiveSearchResult] = []
        try:
            results = search_telegram_archive(connection, query, limit=clean_limit)
        except (ArchiveSearchError, sqlite3.Error) as exc:
            error_type = type(exc).__name__
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        duplicate_rate = _duplicate_top10_rate(results)

        row = {
            "case_id": case_id,
            "category": category,
            "approval_status": "gold" if is_gold else "candidate_unapproved",
            "result_count": len(results),
            "latency_ms": latency_ms,
            "duplicate_top10_rate": duplicate_rate,
            "error_type": error_type,
        }
        if is_gold:
            gold_latencies.append(latency_ms)
            scores = _score_gold_case(case, results, search_error=error_type is not None)
            gold_scores.append(scores)
            gold_rows.append({**row, "scores": scores})
        else:
            candidate_latencies.append(latency_ms)
            candidate_duplicate_rates.append(duplicate_rate)
            candidate_rows.append(row)

    gold_metrics = _aggregate_gold_metrics(gold_scores, gold_latencies, connection)
    candidate_diagnostics = {
        "status": "diagnostic_only_not_gold",
        "latency_ms_p95": _p95(candidate_latencies),
        "duplicate_top10_rate": _mean(candidate_duplicate_rates),
        "reacted_post_searchability": _reacted_post_searchability(connection),
    }
    if not gold_rows:
        gold_metrics["status"] = "not_scored_no_human_approved_gold"

    return {
        "schema_version": ARCHIVE_RETRIEVAL_EVAL_SCHEMA_VERSION,
        "dataset": {
            "row_count": len(cases),
            "gold_row_count": len(gold_rows),
            "candidate_row_count": len(candidate_rows),
            "candidate_unapproved_case_ids": [row["case_id"] for row in candidate_rows],
        },
        "gold": {
            "row_count": len(gold_rows),
            "metrics": gold_metrics,
            "rows": gold_rows,
        },
        "candidates": {
            "row_count": len(candidate_rows),
            "diagnostics": candidate_diagnostics,
            "rows": candidate_rows,
        },
        "vector_backend_gate": {
            "status": (
                "blocked_no_human_approved_gold"
                if not gold_rows
                else "requires_human_approved_adr_before_vector_adoption"
            ),
            "vector_backend_adopted": False,
            "embeddings_run": False,
        },
        "privacy": {
            "raw_telegram_text_printed": False,
            "snippets_included": False,
            "source_urls_included": False,
            "queries_included": False,
        },
    }


def validate_archive_retrieval_eval_report(report: Mapping[str, object]) -> dict[str, object]:
    if report.get("schema_version") != ARCHIVE_RETRIEVAL_EVAL_SCHEMA_VERSION:
        raise ArchiveRetrievalEvalError("archive retrieval eval schema_version is invalid")
    dataset = report.get("dataset")
    if not isinstance(dataset, Mapping):
        raise ArchiveRetrievalEvalError("dataset must be an object")
    for field in ("row_count", "gold_row_count", "candidate_row_count"):
        _nonnegative_int(dataset.get(field), f"dataset.{field}")
    gold = report.get("gold")
    if not isinstance(gold, Mapping) or not isinstance(gold.get("metrics"), Mapping):
        raise ArchiveRetrievalEvalError("gold metrics must be present")
    metrics = gold["metrics"]
    for field in METRIC_FIELDS:
        if field not in metrics:
            raise ArchiveRetrievalEvalError(f"missing metric: {field}")
    gate = report.get("vector_backend_gate")
    if not isinstance(gate, Mapping) or gate.get("vector_backend_adopted") is not False:
        raise ArchiveRetrievalEvalError("vector backend must not be adopted by eval report")
    privacy = report.get("privacy")
    if not isinstance(privacy, Mapping) or privacy.get("raw_telegram_text_printed") is not False:
        raise ArchiveRetrievalEvalError("retrieval eval report must exclude raw text")
    return dict(report)


def _score_gold_case(
    case: Mapping[str, object],
    results: Sequence[ArchiveSearchResult],
    *,
    search_error: bool = False,
) -> dict[str, float | None]:
    expected_no_answer = case.get("expected_no_answer") is True
    first_rank = _first_relevant_rank(case, results)
    labeled_relevance = _has_expected_relevance(case)
    return {
        "hit_at_10": None if expected_no_answer or not labeled_relevance else (1.0 if first_rank is not None else 0.0),
        "mrr": None if expected_no_answer or not labeled_relevance else (1.0 / first_rank if first_rank else 0.0),
        "citation_precision": None if expected_no_answer or not labeled_relevance else _citation_precision(case, results),
        "stale_rejection": _stale_rejection(case, results, search_error=search_error),
        "no_answer_accuracy": (
            0.0
            if expected_no_answer and search_error
            else 1.0
            if expected_no_answer and not results
            else 0.0
            if expected_no_answer
            else None
        ),
        "duplicate_top10_rate": _duplicate_top10_rate(results),
    }


def _aggregate_gold_metrics(
    gold_scores: Sequence[Mapping[str, float | None]],
    latencies_ms: Sequence[float],
    connection: sqlite3.Connection,
) -> dict[str, float | str | None]:
    metrics: dict[str, float | str | None] = {"status": "scored"}
    for field in (
        "hit_at_10",
        "mrr",
        "citation_precision",
        "stale_rejection",
        "no_answer_accuracy",
        "duplicate_top10_rate",
    ):
        values = [
            float(score[field])
            for score in gold_scores
            if score.get(field) is not None
        ]
        metrics[field] = _mean(values)
    metrics["latency_ms_p95"] = _p95(latencies_ms)
    metrics["reacted_post_searchability"] = _reacted_post_searchability(connection)
    return metrics


def _first_relevant_rank(
    case: Mapping[str, object],
    results: Sequence[ArchiveSearchResult],
) -> int | None:
    for index, result in enumerate(results[:10], start=1):
        if _is_relevant(case, result):
            return index
    return None


def _citation_precision(
    case: Mapping[str, object],
    results: Sequence[ArchiveSearchResult],
) -> float | None:
    if not results:
        return 0.0
    relevant_count = sum(1 for result in results[:10] if _is_relevant(case, result))
    return relevant_count / len(results[:10])


def _is_relevant(case: Mapping[str, object], result: ArchiveSearchResult) -> bool:
    expected_document_ids = set(_string_list(case.get("expected_archive_document_ids")))
    expected_post_ids = {int(value) for value in _string_list(case.get("expected_post_ids")) if str(value).isdigit()}
    expected_urls = set(_string_list(case.get("expected_source_urls")))
    if expected_document_ids and result.archive_document_id in expected_document_ids:
        return True
    if expected_post_ids and result.post_id in expected_post_ids:
        return True
    if expected_urls and result.source_url in expected_urls:
        return True
    return False


def _has_expected_relevance(case: Mapping[str, object]) -> bool:
    return any(
        _string_list(case.get(field))
        for field in (
            "expected_archive_document_ids",
            "expected_post_ids",
            "expected_source_urls",
        )
    )


def _has_stale_or_forbidden_labels(case: Mapping[str, object]) -> bool:
    return any(
        _string_list(case.get(field))
        for field in (
            "forbidden_archive_document_ids",
            "stale_archive_document_ids",
            "forbidden_post_ids",
            "stale_post_ids",
            "forbidden_source_urls",
            "stale_source_urls",
        )
    )


def _is_scoreable_gold_case(case: Mapping[str, object]) -> bool:
    return (
        case.get("expected_no_answer") is True
        or _has_expected_relevance(case)
        or _has_stale_or_forbidden_labels(case)
    )


def _stale_rejection(
    case: Mapping[str, object],
    results: Sequence[ArchiveSearchResult],
    *,
    search_error: bool = False,
) -> float | None:
    forbidden_document_ids = set(
        _string_list(case.get("forbidden_archive_document_ids") or case.get("stale_archive_document_ids"))
    )
    forbidden_post_ids = {
        int(value)
        for value in _string_list(case.get("forbidden_post_ids") or case.get("stale_post_ids"))
        if str(value).isdigit()
    }
    forbidden_urls = set(_string_list(case.get("forbidden_source_urls") or case.get("stale_source_urls")))
    if not forbidden_document_ids and not forbidden_post_ids and not forbidden_urls:
        return None
    if search_error:
        return 0.0
    for result in results[:10]:
        if result.archive_document_id in forbidden_document_ids:
            return 0.0
        if result.post_id in forbidden_post_ids:
            return 0.0
        if result.source_url in forbidden_urls:
            return 0.0
    return 1.0


def _duplicate_top10_rate(results: Sequence[ArchiveSearchResult]) -> float:
    top = list(results[:10])
    if not top:
        return 0.0
    hashes = [result.content_hash for result in top if result.content_hash]
    duplicate_count = len(hashes) - len(set(hashes))
    return round(duplicate_count / len(top), 6)


def _reacted_post_searchability(connection: sqlite3.Connection) -> float | None:
    try:
        receipt = build_reaction_fast_lane_receipt(connection)
    except sqlite3.Error:
        return None
    counts = receipt.get("counts", {})
    if not isinstance(counts, Mapping):
        return None
    total = int(counts.get("unique_reacted_posts") or 0)
    if total <= 0:
        return None
    searchable = int(counts.get("searchable_archive_posts") or 0)
    return round(searchable / total, 6)


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
    if len(ordered) == 1:
        return ordered[0]
    return round(ordered[index], 3)


def _required_string(row: Mapping[str, object], field: str) -> str:
    value = str(row.get(field) or "").strip()
    if not value:
        raise ArchiveRetrievalEvalError(f"{field} is required")
    return value


def _string_list(value: object) -> list[str]:
    if value in (None, "", [], ()):
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [str(item).strip() for item in value if str(item).strip()]  # type: ignore[arg-type]
    except TypeError:
        return [str(value).strip()]


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise ArchiveRetrievalEvalError(f"{field} must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ArchiveRetrievalEvalError(f"{field} must be a non-negative integer") from exc
    if result < 0:
        raise ArchiveRetrievalEvalError(f"{field} must be a non-negative integer")
    return result
