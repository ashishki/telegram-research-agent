from __future__ import annotations

from typing import Any, Mapping, Sequence

from assistant.rag_answer_gate import assess_rag_answer_gate


PRODUCT_RAG_ANSWER_GATE_SCHEMA_VERSION = "product_rag_answer_gate_eval.v1"


class ProductRagAnswerGateEvalError(ValueError):
    """Raised when product RAG answer-gate eval input or output is malformed."""


def evaluate_product_rag_answer_gate(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    no_answer_scores: list[float] = []
    external_scores: list[float] = []
    answerable_scores: list[float] = []
    current_claim_rejection_scores: list[float] = []

    for index, case in enumerate(cases, start=1):
        if not isinstance(case, Mapping):
            raise ProductRagAnswerGateEvalError(f"case {index} must be an object")
        case_id = _required_string(case, "case_id")
        query = _required_string(case, "query")
        if case.get("human_approved") is not True:
            raise ProductRagAnswerGateEvalError(f"{case_id} must be human_approved=true")

        expected_no_answer = case.get("expected_no_answer") is True
        expected_external = case.get("external_verification_required") is True
        expected_sources = _expected_source_count(case)
        source_count = max(1, expected_sources)
        gate = assess_rag_answer_gate(
            query,
            source_count=source_count,
            external_verification_hint=expected_external or str(case.get("category") or "") == "linked_source_freshness",
        )

        if expected_no_answer:
            no_answer_scores.append(1.0 if gate["no_answer_required"] is True and gate["allow_answer"] is False else 0.0)
        if expected_external:
            external_scores.append(
                1.0
                if gate["external_verification_required"] is True and gate["current_claim_allowed"] is False
                else 0.0
            )
            current_claim_rejection_scores.append(1.0 if gate["current_claim_allowed"] is False else 0.0)
        if not expected_no_answer and not expected_external and expected_sources > 0:
            answerable_scores.append(1.0 if gate["allow_answer"] is True else 0.0)

        rows.append(
            {
                "case_id": case_id,
                "category": str(case.get("category") or "unknown"),
                "expected_no_answer": expected_no_answer,
                "external_verification_required": expected_external,
                "expected_source_count": expected_sources,
                "gate_status": gate["status"],
                "gate_reason": gate["reason"],
                "allow_answer": gate["allow_answer"],
                "current_claim_allowed": gate["current_claim_allowed"],
                "no_answer_required": gate["no_answer_required"],
                "vector_backend_required": gate["vector_backend_required"],
                "embeddings_run": gate["embeddings_run"],
            }
        )

    return validate_product_rag_answer_gate_report(
        {
            "schema_version": PRODUCT_RAG_ANSWER_GATE_SCHEMA_VERSION,
            "dataset": {
                "row_count": len(rows),
                "gold_row_count": len(rows),
                "candidate_row_count": 0,
            },
            "metrics": {
                "no_answer_accuracy": _mean(no_answer_scores),
                "external_verification_boundary_accuracy": _mean(external_scores),
                "current_claim_rejection": _mean(current_claim_rejection_scores),
                "answerable_source_label_accuracy": _mean(answerable_scores),
                "vector_backend_required_rate": _mean([1.0 if row["vector_backend_required"] else 0.0 for row in rows]),
                "embeddings_run_rate": _mean([1.0 if row["embeddings_run"] else 0.0 for row in rows]),
            },
            "rows": rows,
            "vector_backend_gate": {
                "status": "no_vector_path_accepted_prm26",
                "vector_backend_adopted": False,
                "embeddings_run": False,
            },
            "privacy": {
                "queries_included": False,
                "raw_telegram_text_included": False,
                "snippets_included": False,
                "source_urls_included": False,
                "provider_payloads_included": False,
            },
        }
    )


def validate_product_rag_answer_gate_report(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("schema_version") != PRODUCT_RAG_ANSWER_GATE_SCHEMA_VERSION:
        raise ProductRagAnswerGateEvalError("answer-gate eval schema_version is invalid")
    dataset = _mapping(report.get("dataset"), "dataset")
    for field in ("row_count", "gold_row_count", "candidate_row_count"):
        _nonnegative_int(dataset.get(field), f"dataset.{field}")
    metrics = _mapping(report.get("metrics"), "metrics")
    for field in (
        "no_answer_accuracy",
        "external_verification_boundary_accuracy",
        "current_claim_rejection",
        "answerable_source_label_accuracy",
        "vector_backend_required_rate",
        "embeddings_run_rate",
    ):
        value = metrics.get(field)
        if value is not None:
            _bounded_ratio(value, f"metrics.{field}")
    gate = _mapping(report.get("vector_backend_gate"), "vector_backend_gate")
    if gate.get("vector_backend_adopted") is not False or gate.get("embeddings_run") is not False:
        raise ProductRagAnswerGateEvalError("answer-gate eval must not adopt vector backend or run embeddings")
    privacy = _mapping(report.get("privacy"), "privacy")
    for field in ("queries_included", "raw_telegram_text_included", "snippets_included", "source_urls_included", "provider_payloads_included"):
        if privacy.get(field) is not False:
            raise ProductRagAnswerGateEvalError(f"privacy.{field} must be false")
    return dict(report)


def _expected_source_count(case: Mapping[str, Any]) -> int:
    return sum(
        len(_string_list(case.get(field)))
        for field in (
            "expected_archive_document_ids",
            "expected_post_ids",
            "expected_source_urls",
        )
    )


def _required_string(row: Mapping[str, Any], field: str) -> str:
    value = str(row.get(field) or "").strip()
    if not value:
        raise ProductRagAnswerGateEvalError(f"{field} is required")
    return value


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProductRagAnswerGateEvalError(f"{field} must be an object")
    return dict(value)


def _string_list(value: Any) -> list[str]:
    if value in (None, "", [], ()):
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    try:
        return [str(item).strip() for item in value if str(item).strip()]
    except TypeError:
        clean = str(value).strip()
        return [clean] if clean else []


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _bounded_ratio(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ProductRagAnswerGateEvalError(f"{field} must be numeric")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ProductRagAnswerGateEvalError(f"{field} must be numeric") from exc
    if not 0.0 <= parsed <= 1.0:
        raise ProductRagAnswerGateEvalError(f"{field} must be between 0 and 1")
    return parsed


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ProductRagAnswerGateEvalError(f"{field} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ProductRagAnswerGateEvalError(f"{field} must be a non-negative integer") from exc
    if parsed < 0:
        raise ProductRagAnswerGateEvalError(f"{field} must be a non-negative integer")
    return parsed
