"""Owner-local PRM-QA interaction receipts and failed-case traces."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PRIVATE_TRACE_SCHEMA_VERSION = "prm_qa_private_interaction_receipt.v1"
PRIVATE_FAILURE_TRACE_SCHEMA_VERSION = "prm_qa_private_failure_trace.v1"
_TRACE_ROOT = Path("data/evals/private/prm_qa")
_MAX_TRACE_FILES = 300


def write_private_interaction_receipt(
    answer: Mapping[str, Any],
    *,
    interaction_id: str,
    trace_root: str | Path | None = None,
) -> dict[str, Any]:
    """Write a metadata-only local receipt. Raw user/archive text is excluded."""

    receipt = build_private_interaction_receipt(answer, interaction_id=interaction_id)
    directory = Path(trace_root or _TRACE_ROOT / "interactions")
    _write_json(directory / f"{interaction_id}.json", receipt)
    _prune(directory, limit=_MAX_TRACE_FILES)
    return receipt


def update_private_interaction_feedback(
    interaction_id: str,
    *,
    feedback: str,
    reason: str = "",
    trace_root: str | Path | None = None,
) -> dict[str, Any]:
    directory = Path(trace_root or _TRACE_ROOT / "interactions")
    path = directory / f"{interaction_id}.json"
    if not path.exists():
        return {"status": "missing", "write_performed": False}
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["feedback"] = {"label": _clean(feedback), "reason": _clean(reason), "updated_at": _now()}
    _write_json(path, payload)
    return {"status": "updated", "write_performed": True}


def write_private_failure_trace(
    trace: Mapping[str, Any],
    *,
    trace_id: str,
    trace_root: str | Path | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": PRIVATE_FAILURE_TRACE_SCHEMA_VERSION,
        "trace_id": _clean(trace_id)[:64],
        "recorded_at": _now(),
        "selected_route": _safe_route(trace.get("selected_route")),
        "query_rewrite_hashes": [_hash(_clean(value)) for value in _safe_list(trace.get("query_rewrite")) if _clean(value)],
        "retrieval_candidates": _safe_candidate_trace(trace.get("retrieval_candidates")),
        "selected_context": _safe_candidate_trace(trace.get("selected_context")),
        "source_groups": [_hash(_clean(value)) for value in _safe_list(trace.get("source_groups")) if _clean(value)],
        "evidence_quality": _safe_evidence_summary(trace.get("evidence_quality")),
        "claim_verification": _safe_claim_summary(trace.get("claim_verification")),
        "failure_codes": [_clean(value)[:64] for value in _safe_list(trace.get("failure_codes")) if _clean(value)],
        "privacy": {
            "gitignored": True,
            "raw_question_recorded": False,
            "raw_archive_body_recorded": False,
            "raw_provider_payload_recorded": False,
            "source_urls_recorded": False,
            "public_artifact": False,
        },
    }
    directory = Path(trace_root or _TRACE_ROOT / "failed_cases")
    _write_json(directory / f"{trace_id}.json", payload)
    _prune(directory, limit=_MAX_TRACE_FILES)
    return payload


def build_private_interaction_receipt(answer: Mapping[str, Any], *, interaction_id: str) -> dict[str, Any]:
    receipt = _safe_mapping(answer.get("receipt"))
    policy = _safe_mapping(answer.get("retrieval_policy")) or _safe_mapping(receipt.get("retrieval_policy"))
    evidence = _safe_mapping(answer.get("evidence_quality"))
    evidence_summary = _safe_mapping(evidence.get("summary")) or _safe_mapping(receipt.get("evidence_quality_summary"))
    ledger = _safe_mapping(answer.get("claim_ledger"))
    grounding = _safe_mapping(ledger.get("metrics")) or _safe_mapping(receipt.get("claim_grounding"))
    archive = _safe_mapping(answer.get("archive_evidence"))
    route = _safe_mapping(answer.get("route_decision"))
    contract = _safe_mapping(answer.get("archive_contract"))
    result_summary = _safe_mapping(contract.get("result_summary"))
    body = _clean(answer.get("answer") or answer.get("direct_answer") or "")
    candidate_trace = _archive_candidate_trace(archive.get("items"))
    source_groups = [
        str(item.get("source_group_id") or "")
        for item in evidence.get("items") or []
        if isinstance(item, Mapping) and str(item.get("source_group_id") or "")
    ]
    return {
        "schema_version": PRIVATE_TRACE_SCHEMA_VERSION,
        "interaction_id": _clean(interaction_id),
        "timestamp": _now(),
        "primary_intent": _clean(answer.get("primary_intent") or route.get("primary_intent")) or "unknown",
        "response_contract_id": _clean(answer.get("response_contract_id") or route.get("response_contract_id")) or "unknown",
        "route": _safe_route(route),
        "job_type": str(policy.get("job_type") or "unknown"),
        "workflow": str(answer.get("primary_workflow") or _safe_mapping(answer.get("operator_context")).get("primary_workflow") or "unknown"),
        "project": str(_safe_mapping(answer.get("project_fit")).get("project_name") or answer.get("project_name") or ""),
        "retrieval_policy": str(policy.get("policy_id") or "unknown"),
        "retrieval_latency": _latency_from_attempts(archive.get("attempted_queries")),
        "source_count": max(0, int(answer.get("source_count") or len(archive.get("items") or []))),
        "source_group_hashes": sorted({_hash(value) for value in source_groups if value}),
        "candidate_trace": candidate_trace,
        "selected_evidence_hashes": [item["candidate_hash"] for item in candidate_trace if item.get("selected")],
        "relevance": {
            "direct_count": int(result_summary.get("direct_count") or _label_count(candidate_trace, "direct")),
            "partial_count": int(result_summary.get("partial_count") or _label_count(candidate_trace, "partial")),
            "adjacent_count": int(result_summary.get("adjacent_count") or _label_count(candidate_trace, "adjacent")),
            "unrelated_count": int(result_summary.get("unrelated_count") or _label_count(candidate_trace, "unrelated")),
            "adjacent_contamination_rate": float(evidence_summary.get("adjacent_contamination_rate") or 0.0),
        },
        "claim_count": max(0, int(ledger.get("claim_count") or grounding.get("claim_count") or 0)),
        "supported_claim_rate": float(grounding.get("supported_claim_rate") or 0.0),
        "citation_metrics": {
            "citation_completeness": float(grounding.get("citation_completeness") or 0.0),
            "citation_precision": float(grounding.get("citation_precision") or 0.0),
        },
        "evidence_quality": {
            "source_group_count": int(evidence_summary.get("source_group_count") or 0),
            "direct_rate": float(evidence_summary.get("direct_rate") or 0.0),
            "relevant_rate": float(evidence_summary.get("relevant_rate") or 0.0),
        },
        "render": {
            "mode": _clean(answer.get("render_mode")) or "telegram_answer",
            "answer_chars": len(body),
            "first_useful_information_position": 0 if body else None,
            "keyboard_action_ids": [
                _clean(value)[:32]
                for value in answer.get("keyboard_action_ids") or []
                if _clean(value)
            ][:8],
        },
        "answer_latency": 0.0,
        "model_calls": int(_safe_mapping(answer.get("privacy")).get("model_calls") or 0),
        "estimated_cost": float(_safe_mapping(answer.get("privacy")).get("estimated_cost_usd") or 0.0),
        "answer_hash": hashlib.sha256(body.encode()).hexdigest() if body else "",
        "feedback": {"label": "unknown", "reason": "", "updated_at": ""},
        "save_state": "not_requested",
        "watch_state": "not_requested",
        "action_state": "not_requested",
        "decision_state": "not_requested",
        "privacy": {
            "gitignored": True,
            "raw_question_recorded": False,
            "raw_answer_recorded": False,
            "raw_archive_body_recorded": False,
            "source_urls_recorded": False,
            "provider_payload_recorded": False,
            "commit_allowed": False,
        },
    }


def _archive_candidate_trace(value: object) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(rows[:20], start=1):
        if not isinstance(item, Mapping):
            continue
        identity = _candidate_identity(item)
        label = _clean(item.get("relevance_label")) or "unknown"
        result.append(
            {
                "candidate_hash": _hash(identity or f"candidate:{index}"),
                "source_group_hash": _hash(_clean(item.get("source_group_id"))) if _clean(item.get("source_group_id")) else "",
                "matched_variant_hash": _hash(_clean(item.get("matched_query_variant"))) if _clean(item.get("matched_query_variant")) else "",
                "retrieval_mode": _clean(item.get("retrieval_mode"))[:64],
                "lexical_rank": _number(item.get("rank")),
                "semantic_score": _number(item.get("semantic_score")),
                "fusion_score": _number(item.get("fusion_score")),
                "relevance_label": label,
                "directness_score": _number(item.get("directness_score")),
                "relevance_reason": _clean(item.get("relevance_reason"))[:64],
                "selected": label in {"direct", "partial", "adjacent"},
            }
        )
    return result


def _safe_candidate_trace(value: object) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    result = []
    for index, item in enumerate(rows[:20], start=1):
        if not isinstance(item, Mapping):
            continue
        identity = _candidate_identity(item) or f"candidate:{index}"
        result.append(
            {
                "candidate_hash": _hash(identity),
                "relevance_label": _clean(item.get("relevance_label"))[:32],
                "directness_score": _number(item.get("directness_score")),
                "selected": bool(item.get("selected")),
                "rejection_reason": _clean(item.get("rejection_reason"))[:64],
            }
        )
    return result


def _safe_route(value: object) -> dict[str, Any]:
    route = _safe_mapping(value)
    return {
        "primary_intent": _clean(route.get("primary_intent"))[:64],
        "response_contract_id": _clean(route.get("response_contract_id"))[:64],
        "reason": _clean(route.get("reason"))[:64],
        "reason_codes": [_clean(item)[:64] for item in route.get("reason_codes") or [] if _clean(item)][:8],
        "archive_scope": bool(route.get("archive_scope")),
        "project_context_required": bool(route.get("project_context_required")),
        "external_verification_required": bool(route.get("external_verification_required")),
        "decision_requested": bool(route.get("decision_requested")),
    }


def _safe_evidence_summary(value: object) -> dict[str, Any]:
    summary = _safe_mapping(value)
    return {
        "source_group_count": int(summary.get("source_group_count") or 0),
        "direct_rate": float(summary.get("direct_rate") or 0.0),
        "relevant_rate": float(summary.get("relevant_rate") or 0.0),
        "adjacent_contamination_rate": float(summary.get("adjacent_contamination_rate") or 0.0),
    }


def _safe_claim_summary(value: object) -> dict[str, Any]:
    summary = _safe_mapping(value)
    metrics = _safe_mapping(summary.get("metrics"))
    return {
        "claim_count": int(summary.get("claim_count") or 0),
        "supported_claim_rate": float(metrics.get("supported_claim_rate") or 0.0),
        "unsupported_claim_rate": float(metrics.get("unsupported_claim_rate") or 0.0),
        "current_fact_violations": int(metrics.get("current_fact_violations") or 0),
    }


def _candidate_identity(item: Mapping[str, Any]) -> str:
    for key in ("archive_document_id", "post_archive_document_id", "candidate_id", "evidence_id", "post_id"):
        value = _clean(item.get(key))
        if value:
            return f"{key}:{value}"
    return ""


def _label_count(rows: list[Mapping[str, Any]], label: str) -> int:
    return sum(1 for item in rows if item.get("relevance_label") == label)


def _latency_from_attempts(value: object) -> float:
    if not isinstance(value, list):
        return 0.0
    return 0.0


def _number(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _prune(directory: Path, *, limit: int) -> None:
    files = sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in files[max(1, limit) :]:
        path.unlink(missing_ok=True)


def _safe_mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_list(value: object) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value[:20]


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
