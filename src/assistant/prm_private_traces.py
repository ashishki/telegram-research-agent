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
        "selected_route": _safe_mapping(trace.get("selected_route")),
        "query_rewrite": _safe_list(trace.get("query_rewrite")),
        "retrieval_candidates": _safe_list(trace.get("retrieval_candidates")),
        "selected_context": _safe_list(trace.get("selected_context")),
        "source_groups": _safe_list(trace.get("source_groups")),
        "evidence_quality": _safe_mapping(trace.get("evidence_quality")),
        "claim_ledger": _safe_mapping(trace.get("claim_ledger")),
        "claim_verification": _safe_mapping(trace.get("claim_verification")),
        "failure_codes": _safe_list(trace.get("failure_codes")),
        "privacy": {
            "gitignored": True,
            "raw_provider_payload_recorded": False,
            "public_artifact": False,
        },
    }
    directory = Path(trace_root or _TRACE_ROOT / "failed_cases")
    _write_json(directory / f"{trace_id}.json", payload)
    _prune(directory, limit=_MAX_TRACE_FILES)
    return payload


def build_private_interaction_receipt(answer: Mapping[str, Any], *, interaction_id: str) -> dict[str, Any]:
    receipt = answer.get("receipt") if isinstance(answer.get("receipt"), Mapping) else {}
    policy = answer.get("retrieval_policy") if isinstance(answer.get("retrieval_policy"), Mapping) else receipt.get("retrieval_policy", {})
    evidence = answer.get("evidence_quality") if isinstance(answer.get("evidence_quality"), Mapping) else {}
    evidence_summary = evidence.get("summary") if isinstance(evidence.get("summary"), Mapping) else receipt.get("evidence_quality_summary", {})
    ledger = answer.get("claim_ledger") if isinstance(answer.get("claim_ledger"), Mapping) else {}
    grounding = ledger.get("metrics") if isinstance(ledger.get("metrics"), Mapping) else receipt.get("claim_grounding", {})
    archive = answer.get("archive_evidence") if isinstance(answer.get("archive_evidence"), Mapping) else {}
    source_groups = [
        str(item.get("source_group_id") or "")
        for item in (evidence.get("items") or [])
        if isinstance(item, Mapping) and str(item.get("source_group_id") or "")
    ]
    body = _clean(answer.get("answer") or answer.get("direct_answer") or "")
    return {
        "schema_version": PRIVATE_TRACE_SCHEMA_VERSION,
        "interaction_id": _clean(interaction_id),
        "timestamp": _now(),
        "job_type": str(policy.get("job_type") or "unknown"),
        "workflow": str(answer.get("primary_workflow") or _safe_mapping(answer.get("operator_context")).get("primary_workflow") or "unknown"),
        "project": str(_safe_mapping(answer.get("project_fit")).get("project_name") or answer.get("project_name") or ""),
        "retrieval_policy": str(policy.get("policy_id") or "unknown"),
        "retrieval_latency": _latency_from_attempts(archive.get("attempted_queries")),
        "source_count": max(0, int(answer.get("source_count") or len(archive.get("items") or []))),
        "source_groups": sorted(set(source_groups)),
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
            "raw_archive_body_recorded": False,
            "provider_payload_recorded": False,
            "commit_allowed": False,
        },
    }


def _latency_from_attempts(value: object) -> float:
    if not isinstance(value, list):
        return 0.0
    return 0.0


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
