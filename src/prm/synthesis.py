"""Optional bounded synthesis over already approved claims."""

from __future__ import annotations

import json
import os
from typing import Any, Mapping, Sequence

from assistant.claim_ledger import verify_answer_against_evidence
from llm.client import LLMClient
from prm.archive_contract import ARCHIVE_RESPONSE_CONTRACTS

_FORBIDDEN_USER_MARKERS = (
    "The local research path found grounded evidence",
    "Archive signal:",
    "Linked-source signal:",
    "Project routing",
)
_ARCHIVE_FORBIDDEN_SECTIONS = (
    "Главный риск",
    "Критерий успеха",
    "Что изменило бы решение",
    "влияние на backlog",
    "влияния на backlog",
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
    primary_intent: str = "",
    response_contract_id: str = "",
) -> str | None:
    if not synthesis_allowed():
        return None
    gate = _mapping(payload.get("answer_gate"))
    if bool(gate.get("external_verification_required")) and not bool(gate.get("current_claim_allowed", True)):
        return None

    if response_contract_id in ARCHIVE_RESPONSE_CONTRACTS:
        return _synthesize_archive_answer(
            payload,
            deterministic_fallback=deterministic_fallback,
            evidence_items=evidence_items,
            primary_intent=primary_intent,
        )

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
    return _call_and_verify(
        prompt,
        evidence_items=evidence_items,
        project_name=str(_mapping(payload.get("project_fit")).get("project_name") or ""),
    )


def _synthesize_archive_answer(
    payload: Mapping[str, Any],
    *,
    deterministic_fallback: str,
    evidence_items: Sequence[Mapping[str, Any]],
    primary_intent: str,
) -> str | None:
    contract = _mapping(payload.get("archive_contract"))
    summary = _mapping(contract.get("result_summary"))
    if primary_intent == "archive_to_action" and int(summary.get("actionable_count") or 0) == 0:
        return None
    findings = [
        {
            "relevance": item.get("relevance_label"),
            "source_role": item.get("source_role"),
            "supports_action": item.get("supports_action"),
            "summary": item.get("summary"),
            "source": item.get("source_url"),
            "reason": item.get("relevance_reason"),
        }
        for field in ("direct_findings", "partial_findings", "adjacent_findings")
        for item in _mappings(contract.get(field))
    ][:8]
    if not findings:
        return None
    prompt = (
        "Write a compact Russian Telegram answer for a private archive assistant. "
        "Start with the direct answer in the first sentence. Keep direct, partial and adjacent findings explicitly separate. "
        "Never turn an archive lookup into a project decision. Do not mention backlog, project blockers, acceptance criteria, "
        "watch-signal policy, claim ledgers or internal evidence terminology. Do not invent source content. "
        "Applicability is allowed only as a clearly marked analytical inference. Keep the answer under 1800 characters.\n\n"
        f"intent: {primary_intent}\n"
        f"result_summary: {json.dumps(summary, ensure_ascii=False)}\n"
        f"findings: {json.dumps(findings, ensure_ascii=False)}\n"
        f"applicability: {json.dumps(contract.get('applicability') or [], ensure_ascii=False)}\n"
        f"limitations: {json.dumps(contract.get('limitations') or [], ensure_ascii=False)}\n"
        f"fallback_contract: {deterministic_fallback[:2600]}"
    )
    answer = _call_and_verify(prompt, evidence_items=evidence_items, project_name="")
    if not answer:
        return None
    if any(marker.casefold() in answer.casefold() for marker in _ARCHIVE_FORBIDDEN_SECTIONS):
        return None
    if int(summary.get("direct_count") or 0) == 0 and "прям" not in answer.casefold():
        return None
    return answer


def _call_and_verify(
    prompt: str,
    *,
    evidence_items: Sequence[Mapping[str, Any]],
    project_name: str,
) -> str | None:
    try:
        answer = LLMClient.complete(
            prompt=prompt,
            system="You are a grounded synthesis layer. Unsupported facts and intent substitution are forbidden.",
            category="bot_ask",
            max_tokens=900,
            max_attempts=1,
        ).strip()
    except Exception:
        return None
    if not answer or any(marker in answer for marker in _FORBIDDEN_USER_MARKERS):
        return None
    verification = verify_answer_against_evidence(
        answer,
        evidence_items,
        current_fact_required=False,
        project_name=project_name,
    )
    metrics = _mapping(verification.get("metrics"))
    if int(metrics.get("current_fact_violations") or 0) or float(metrics.get("unsupported_claim_rate") or 0.0) > 0.6:
        return None
    return answer


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, Mapping)]
