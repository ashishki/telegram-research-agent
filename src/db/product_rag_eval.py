from __future__ import annotations

from typing import Any, Mapping, Sequence


PRODUCT_RAG_EVAL_SCHEMA_VERSION = "product_rag_eval_manifest.v1"
PRODUCT_RAG_THRESHOLDS_SCHEMA_VERSION = "product_rag_thresholds.v1"
PRODUCT_RAG_SIMULATION_SCHEMA_VERSION = "product_rag_simulation_receipt.v1"

REQUIRED_PRODUCT_RAG_CATEGORIES: tuple[str, ...] = (
    "archive_recall",
    "semantic_phrasing",
    "project_fit",
    "linked_source_freshness",
    "no_answer",
    "decision_support",
)

REQUIRED_LOWER_BOUND_THRESHOLDS: tuple[str, ...] = (
    "recall_at_5",
    "recall_at_10",
    "citation_precision",
    "no_answer_accuracy",
    "stale_rejection",
)

REQUIRED_UPPER_BOUND_THRESHOLDS: tuple[str, ...] = (
    "duplicate_top10_rate",
    "latency_ms_p95",
)

_CANDIDATE_EXPECTED_LABEL_FIELDS = {
    "expected_archive_document_ids",
    "expected_post_ids",
    "expected_source_urls",
    "expected_no_answer",
    "stale_archive_document_ids",
    "stale_post_ids",
    "stale_source_urls",
    "forbidden_archive_document_ids",
    "forbidden_post_ids",
    "forbidden_source_urls",
}

_RAW_TEXT_FIELDS = {
    "content",
    "copied_evidence_text",
    "evidence_text",
    "full_post_text",
    "message_text",
    "post_text",
    "private_report_text",
    "raw_json",
    "raw_post_text",
    "raw_text",
    "snippet",
    "telegram_text",
}


class ProductRagEvalError(ValueError):
    """Raised when product RAG eval metadata is malformed."""


def build_product_rag_simulation_receipt(drafts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize operator-review drafts without treating them as gold labels."""
    allowed_outcomes = {"expected_no_answer", "external_verification_required"}
    counts = {outcome: 0 for outcome in sorted(allowed_outcomes)}
    case_ids: list[str] = []
    seen: set[str] = set()
    for index, draft in enumerate(drafts, start=1):
        if not isinstance(draft, Mapping):
            raise ProductRagEvalError(f"simulation draft {index} must be an object")
        case_id = _required_string(draft, "case_id")
        if case_id in seen:
            raise ProductRagEvalError(f"duplicate simulation draft case_id: {case_id}")
        seen.add(case_id)
        if draft.get("human_approved") is not False:
            raise ProductRagEvalError(f"{case_id} simulation draft must have human_approved=false")
        if "human_approval_ref" in draft:
            raise ProductRagEvalError(f"{case_id} simulation draft must not include human_approval_ref")
        if str(draft.get("draft_status") or "") != "needs_operator_confirmation":
            raise ProductRagEvalError(f"{case_id} simulation draft status is invalid")
        outcome = _required_string(draft, "suggested_outcome")
        if outcome not in allowed_outcomes:
            raise ProductRagEvalError(f"{case_id} simulation draft outcome is invalid")
        raw_keys = sorted(_RAW_TEXT_FIELDS.intersection(draft.keys()))
        if raw_keys:
            raise ProductRagEvalError(f"{case_id} simulation draft contains raw text fields: {', '.join(raw_keys)}")
        counts[outcome] += 1
        case_ids.append(case_id)
    return {
        "schema_version": PRODUCT_RAG_SIMULATION_SCHEMA_VERSION,
        "status": "non_gating_simulation_operator_confirmation_required",
        "drafts": {"count": len(case_ids), "case_ids": case_ids, "outcome_counts": counts},
        "gold_labels": {"count": 0, "status": "not_used_by_simulation"},
        "vector_backend_gate": {"status": "blocked_non_gating_simulation", "vector_backend_adopted": False, "embeddings_run": False},
        "privacy": {"raw_telegram_text_included": False, "queries_included": False, "source_urls_included": False, "provider_payloads_included": False},
    }


def build_product_rag_eval_manifest(
    cases: Sequence[Mapping[str, Any]],
    *,
    labels: Sequence[Mapping[str, Any]] | None = None,
    thresholds: Mapping[str, Any] | None = None,
    min_rows: int = 50,
) -> dict[str, Any]:
    normalized_cases = _validate_cases(cases, min_rows=max(1, int(min_rows or 50)))
    labels = labels or []
    normalized_labels = _validate_labels(labels, case_ids={case["case_id"] for case in normalized_cases})
    normalized_thresholds = validate_product_rag_thresholds(thresholds or {})
    category_counts = _category_counts(normalized_cases)
    missing_categories = [
        category
        for category in REQUIRED_PRODUCT_RAG_CATEGORIES
        if category_counts.get(category, 0) <= 0
    ]
    if missing_categories:
        raise ProductRagEvalError("missing required product RAG categories: " + ", ".join(missing_categories))

    return validate_product_rag_eval_manifest(
        {
            "schema_version": PRODUCT_RAG_EVAL_SCHEMA_VERSION,
            "dataset": {
                "case_count": len(normalized_cases),
                "candidate_case_count": len(normalized_cases),
                "gold_label_count": len(normalized_labels),
                "category_counts": category_counts,
                "required_categories": list(REQUIRED_PRODUCT_RAG_CATEGORIES),
                "missing_required_categories": missing_categories,
            },
            "gold_labels": {
                "status": (
                    "blocked_no_human_approved_gold"
                    if not normalized_labels
                    else "human_approved_gold_labels_present"
                ),
                "count": len(normalized_labels),
                "case_ids": [label["case_id"] for label in normalized_labels],
            },
            "thresholds": normalized_thresholds,
            "vector_backend_gate": {
                "status": (
                    "blocked_no_human_approved_gold"
                    if not normalized_labels
                    else "requires_human_approved_adr_before_vector_adoption"
                ),
                "vector_backend_adopted": False,
                "embeddings_run": False,
            },
            "privacy": {
                "raw_telegram_text_included": False,
                "source_urls_included": False,
                "queries_included": False,
                "provider_payloads_included": False,
            },
        }
    )


def validate_product_rag_eval_manifest(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("schema_version") != PRODUCT_RAG_EVAL_SCHEMA_VERSION:
        raise ProductRagEvalError("product RAG eval manifest schema_version is invalid")
    dataset = _mapping(report.get("dataset"), "dataset")
    case_count = _nonnegative_int(dataset.get("case_count"), "dataset.case_count")
    candidate_count = _nonnegative_int(dataset.get("candidate_case_count"), "dataset.candidate_case_count")
    if case_count != candidate_count:
        raise ProductRagEvalError("dataset case_count must match candidate_case_count")
    category_counts = _mapping(dataset.get("category_counts"), "dataset.category_counts")
    for category in REQUIRED_PRODUCT_RAG_CATEGORIES:
        if _nonnegative_int(category_counts.get(category), f"dataset.category_counts.{category}") <= 0:
            raise ProductRagEvalError(f"missing required category count: {category}")
    gold_labels = _mapping(report.get("gold_labels"), "gold_labels")
    _nonnegative_int(gold_labels.get("count"), "gold_labels.count")
    thresholds = validate_product_rag_thresholds(_mapping(report.get("thresholds"), "thresholds"))
    gate = _mapping(report.get("vector_backend_gate"), "vector_backend_gate")
    if gate.get("vector_backend_adopted") is not False or gate.get("embeddings_run") is not False:
        raise ProductRagEvalError("product RAG eval must not adopt vector backend or run embeddings")
    privacy = _mapping(report.get("privacy"), "privacy")
    for field in ("raw_telegram_text_included", "source_urls_included", "queries_included", "provider_payloads_included"):
        if privacy.get(field) is not False:
            raise ProductRagEvalError(f"privacy.{field} must be false")
    return {**dict(report), "thresholds": thresholds}


def validate_product_rag_thresholds(thresholds: Mapping[str, Any]) -> dict[str, Any]:
    if thresholds.get("schema_version") != PRODUCT_RAG_THRESHOLDS_SCHEMA_VERSION:
        raise ProductRagEvalError("product RAG thresholds schema_version is invalid")
    lower_bounds = _mapping(thresholds.get("lower_bounds"), "thresholds.lower_bounds")
    upper_bounds = _mapping(thresholds.get("upper_bounds"), "thresholds.upper_bounds")
    for field in REQUIRED_LOWER_BOUND_THRESHOLDS:
        _bounded_ratio(lower_bounds.get(field), f"thresholds.lower_bounds.{field}")
    for field in REQUIRED_UPPER_BOUND_THRESHOLDS:
        value = _number(upper_bounds.get(field), f"thresholds.upper_bounds.{field}")
        if field == "duplicate_top10_rate" and not 0.0 <= value <= 1.0:
            raise ProductRagEvalError(f"thresholds.upper_bounds.{field} must be between 0 and 1")
        if field == "latency_ms_p95" and value <= 0:
            raise ProductRagEvalError("thresholds.upper_bounds.latency_ms_p95 must be > 0")
    if float(lower_bounds["recall_at_10"]) < float(lower_bounds["recall_at_5"]):
        raise ProductRagEvalError("thresholds.lower_bounds.recall_at_10 must be >= recall_at_5")
    return {
        "schema_version": PRODUCT_RAG_THRESHOLDS_SCHEMA_VERSION,
        "status": str(thresholds.get("status") or "proposed_pending_human_approval"),
        "lower_bounds": {field: float(lower_bounds[field]) for field in REQUIRED_LOWER_BOUND_THRESHOLDS},
        "upper_bounds": {field: float(upper_bounds[field]) for field in REQUIRED_UPPER_BOUND_THRESHOLDS},
    }


def _validate_cases(cases: Sequence[Mapping[str, Any]], *, min_rows: int) -> list[dict[str, Any]]:
    if len(cases) < min_rows:
        raise ProductRagEvalError(f"product RAG eval requires at least {min_rows} candidate rows")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, Mapping):
            raise ProductRagEvalError(f"case {index} must be an object")
        case_id = _required_string(case, "case_id")
        if case_id in seen:
            raise ProductRagEvalError(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        category = _required_string(case, "category")
        if category not in REQUIRED_PRODUCT_RAG_CATEGORIES:
            raise ProductRagEvalError(f"{case_id} has unsupported category: {category}")
        _required_string(case, "language")
        _required_string(case, "query")
        if case.get("human_approved") is not False:
            raise ProductRagEvalError(f"{case_id} candidate row must have human_approved=false")
        if str(case.get("validation_status") or "") != "candidate_unapproved":
            raise ProductRagEvalError(f"{case_id} validation_status must be candidate_unapproved")
        forbidden_keys = sorted((_RAW_TEXT_FIELDS | _CANDIDATE_EXPECTED_LABEL_FIELDS).intersection(case.keys()))
        if forbidden_keys:
            raise ProductRagEvalError(f"{case_id} contains forbidden candidate fields: {', '.join(forbidden_keys)}")
        normalized.append(
            {
                "case_id": case_id,
                "category": category,
                "language": _required_string(case, "language"),
                "validation_status": "candidate_unapproved",
            }
        )
    return normalized


def _validate_labels(labels: Sequence[Mapping[str, Any]], *, case_ids: set[str]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, label in enumerate(labels, start=1):
        if not isinstance(label, Mapping):
            raise ProductRagEvalError(f"label {index} must be an object")
        case_id = _required_string(label, "case_id")
        if case_id not in case_ids:
            raise ProductRagEvalError(f"gold label references unknown case_id: {case_id}")
        if case_id in seen:
            raise ProductRagEvalError(f"duplicate gold label case_id: {case_id}")
        seen.add(case_id)
        if label.get("human_approved") is not True:
            raise ProductRagEvalError(f"{case_id} gold label must have human_approved=true")
        if not _required_string(label, "human_approval_ref"):
            raise ProductRagEvalError(f"{case_id} gold label must include human_approval_ref")
        raw_keys = sorted(_RAW_TEXT_FIELDS.intersection(label.keys()))
        if raw_keys:
            raise ProductRagEvalError(f"{case_id} gold label contains raw text fields: {', '.join(raw_keys)}")
        if not _has_scoreable_gold_label(label):
            raise ProductRagEvalError(f"{case_id} gold label must include expected source IDs/URLs or expected_no_answer=true")
        normalized.append({"case_id": case_id, "human_approval_ref": _required_string(label, "human_approval_ref")})
    return normalized


def _has_scoreable_gold_label(label: Mapping[str, Any]) -> bool:
    if label.get("expected_no_answer") is True:
        return True
    return any(_string_list(label.get(field)) for field in (
        "expected_archive_document_ids",
        "expected_post_ids",
        "expected_source_urls",
    ))


def _category_counts(cases: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {category: 0 for category in REQUIRED_PRODUCT_RAG_CATEGORIES}
    for case in cases:
        category = str(case.get("category") or "")
        counts[category] = counts.get(category, 0) + 1
    return counts


def _required_string(row: Mapping[str, Any], field: str) -> str:
    value = str(row.get(field) or "").strip()
    if not value:
        raise ProductRagEvalError(f"{field} is required")
    return value


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProductRagEvalError(f"{field} must be an object")
    return dict(value)


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ProductRagEvalError(f"{field} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ProductRagEvalError(f"{field} must be a non-negative integer") from exc
    if parsed < 0:
        raise ProductRagEvalError(f"{field} must be a non-negative integer")
    return parsed


def _bounded_ratio(value: Any, field: str) -> float:
    parsed = _number(value, field)
    if not 0.0 <= parsed <= 1.0:
        raise ProductRagEvalError(f"{field} must be between 0 and 1")
    return parsed


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ProductRagEvalError(f"{field} must be numeric")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ProductRagEvalError(f"{field} must be numeric") from exc


def _string_list(value: Any) -> list[str]:
    if value in (None, "", [], ()):
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    try:
        return [str(item).strip() for item in value if str(item).strip()]
    except TypeError:
        clean = str(value).strip()
        return [clean] if clean else []
