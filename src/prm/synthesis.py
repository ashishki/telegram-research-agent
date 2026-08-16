"""Optional bounded synthesis over already approved claims."""

from __future__ import annotations

import json
import os
from typing import Any, Mapping, Sequence

from assistant.claim_ledger import verify_answer_against_evidence
from llm.client import LLMClient

_FORBIDDEN_USER_MARKERS = (
    "The local research path found grounded evidence",
    "Archive signal:",
    "Linked-source signal:",
    "Project routing",
)


def synthesis_allowed() -> bool:
    enabled = os.environ.get("PRM_TELEGRAM_RAG_LLM_SYNTHESIS", "").strip().casefold()
    egress = os.environ.get("PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS", "").strip().casefold()
    accepted = {"1", "true", "yes", "approved"}
    return enabled in accepted and egress in accepted


def synthesize_answer(
    payload: Mapping[str, Any],
    *,
    deterministic_fallback: str,
    mode: str,
    evidence_items: Sequence[Mapping[str, Any]],
) -> str | None:
    if not synthesis_allowed():
        return None
    gate = _mapping(payload.get("answer_gate"))
    if bool(gate.get("external_verification_required")) and not bool(gate.get("current_claim_allowed", True)):
        return None
    ledger = _mapping(payload.get("claim_ledger"))
    claims = [
        {
            "claim": str(item.get("claim_text") or "")[:320],
            "sources": [str(ref) for ref in item.get("evidence_refs") or []][:3],
        }
        for item in ledger.get("claims") or []
        if isinstance(item, Mapping) and str(item.get("support_status") or "") == "supported"
    ][:6]
    if not claims:
        return None
    project = _mapping(payload.get("project_decision"))
    prompt = (
        "Write a concise Russian answer for a private research assistant. Use only the approved claims below. "
        "Do not add facts, current claims, project state or causal conclusions. Keep source URLs beside supported claims. "
        "Use the requested answer mode and at most one recommendation. Return plain text, no JSON.\n\n"
        f"mode: {mode}\n"
        f"approved_claims: {json.dumps(claims, ensure_ascii=False)}\n"
        f"project_decision: {json.dumps(project, ensure_ascii=False)}\n"
        f"fallback_contract: {deterministic_fallback[:2500]}"
    )
    try:
        answer = LLMClient.complete(
            prompt=prompt,
            system="You are a grounded synthesis layer. Unsupported facts are forbidden.",
            category="bot_ask",
            max_tokens=900,
            max_attempts=1,
        ).strip()
    except Exception:
        return None
    if not answer:
        return None
    if any(marker in answer for marker in _FORBIDDEN_USER_MARKERS):
        return None
    verification = verify_answer_against_evidence(
        answer,
        evidence_items,
        current_fact_required=False,
        project_name=str(_mapping(payload.get("project_fit")).get("project_name") or ""),
    )
    metrics = _mapping(verification.get("metrics"))
    if int(metrics.get("current_fact_violations") or 0) or float(metrics.get("unsupported_claim_rate") or 0.0) > 0.6:
        return None
    return answer


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
