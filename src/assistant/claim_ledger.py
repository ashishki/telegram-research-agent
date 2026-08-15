"""Claim ledger and deterministic grounding metrics for PRM answers."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping, Sequence


CLAIM_LEDGER_SCHEMA_VERSION = "prm_claim_ledger.v1"
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_+-]{2,}")
_URL_RE = re.compile(r"https://[^\s)\]]+")


def build_claim_ledger(
    claims: Sequence[Mapping[str, Any] | str],
    evidence_items: Sequence[Mapping[str, Any]],
    *,
    current_fact_required: bool = False,
    project_name: str = "",
) -> dict[str, Any]:
    ledger_claims = [
        _claim_entry(index, claim, evidence_items, current_fact_required=current_fact_required, project_name=project_name)
        for index, claim in enumerate(claims, start=1)
        if _claim_text(claim)
    ]
    return {
        "schema_version": CLAIM_LEDGER_SCHEMA_VERSION,
        "claim_count": len(ledger_claims),
        "claims": ledger_claims,
        "metrics": evaluate_claim_grounding(ledger_claims),
    }


def build_claim_ledger_from_payload(payload: Mapping[str, Any], evidence_items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    professional = payload.get("professional_answer") if isinstance(payload.get("professional_answer"), Mapping) else {}
    answer_gate = payload.get("answer_gate") if isinstance(payload.get("answer_gate"), Mapping) else {}
    claims: list[Mapping[str, Any] | str] = []
    for item in professional.get("key_findings") or []:
        if isinstance(item, Mapping):
            claims.append(
                {
                    "claim_text": item.get("claim"),
                    "claim_type": "source_fact",
                    "citation": item.get("citation") or item.get("source_url"),
                }
            )
    recommendation = str(professional.get("recommended_action") or "").strip()
    if recommendation:
        claims.append({"claim_text": recommendation, "claim_type": "recommendation"})
    if not claims:
        direct = str(payload.get("direct_answer") or "").strip()
        if direct:
            claims.append({"claim_text": direct, "claim_type": "summary"})
    return build_claim_ledger(
        claims,
        evidence_items,
        current_fact_required=bool(answer_gate.get("external_verification_required")) and not bool(answer_gate.get("current_claim_allowed", True)),
        project_name=str(payload.get("project_name") or ""),
    )


def evaluate_claim_grounding(claims: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(claims)
    supported = sum(1 for claim in claims if claim.get("support_status") == "supported")
    partial = sum(1 for claim in claims if claim.get("support_status") == "partially_supported")
    unsupported = sum(1 for claim in claims if claim.get("support_status") == "unsupported")
    cited = sum(1 for claim in claims if claim.get("evidence_refs"))
    citation_urls = sum(
        1
        for claim in claims
        if claim.get("evidence_refs") and all(str(ref).startswith("https://") for ref in claim.get("evidence_refs") or [])
    )
    current_violations = sum(1 for claim in claims if claim.get("freshness") == "current_fact_blocked" and claim.get("support_status") == "supported")
    technical_leaks = sum(1 for claim in claims if _has_technical_leak(str(claim.get("claim_text") or "")))
    return {
        "schema_version": "prm_claim_grounding_metrics.v1",
        "claim_count": total,
        "supported_claim_rate": round(supported / total, 4) if total else 1.0,
        "partial_claim_rate": round(partial / total, 4) if total else 0.0,
        "unsupported_claim_rate": round(unsupported / total, 4) if total else 0.0,
        "citation_completeness": round(cited / total, 4) if total else 1.0,
        "citation_precision": round(citation_urls / max(1, cited), 4),
        "current_fact_violations": current_violations,
        "technical_leaks": technical_leaks,
    }


def claim_ledger_public_summary(ledger: Mapping[str, Any]) -> dict[str, Any]:
    metrics = ledger.get("metrics") if isinstance(ledger.get("metrics"), Mapping) else {}
    return {
        "schema_version": "prm_claim_ledger_public_summary.v1",
        "claim_count": int(ledger.get("claim_count") or 0),
        "supported_claim_rate": float(metrics.get("supported_claim_rate") or 0.0),
        "unsupported_claim_rate": float(metrics.get("unsupported_claim_rate") or 0.0),
        "citation_completeness": float(metrics.get("citation_completeness") or 0.0),
        "citation_precision": float(metrics.get("citation_precision") or 0.0),
        "current_fact_violations": int(metrics.get("current_fact_violations") or 0),
        "technical_leaks": int(metrics.get("technical_leaks") or 0),
    }


def _claim_entry(
    index: int,
    claim: Mapping[str, Any] | str,
    evidence_items: Sequence[Mapping[str, Any]],
    *,
    current_fact_required: bool,
    project_name: str,
) -> dict[str, Any]:
    text = _claim_text(claim)
    claim_type = str(claim.get("claim_type") or "source_fact") if isinstance(claim, Mapping) else "source_fact"
    evidence = _matching_evidence(text, claim, evidence_items)
    support_status = _support_status(text, evidence, current_fact_required=current_fact_required, claim_type=claim_type)
    groups = sorted({str(item.get("source_group_id") or "") for item in evidence if str(item.get("source_group_id") or "")})
    refs = _evidence_refs(claim, evidence)
    return {
        "claim_id": "claim:" + hashlib.sha256(f"{index}:{text}".encode()).hexdigest()[:12],
        "claim_text": text,
        "claim_type": claim_type,
        "freshness": "current_fact_blocked" if current_fact_required else _freshness(evidence),
        "support_status": support_status,
        "evidence_refs": refs,
        "independent_source_groups": groups,
        "confidence": _confidence(support_status, evidence),
        "project_relevance": "direct" if project_name and project_name.casefold() in text.casefold() else "unknown",
        "operator_action_relevance": "recommendation" if claim_type == "recommendation" else "evidence",
    }


def _claim_text(claim: Mapping[str, Any] | str) -> str:
    if isinstance(claim, Mapping):
        return " ".join(str(claim.get("claim_text") or claim.get("claim") or "").split())[:420]
    return " ".join(str(claim or "").split())[:420]


def _matching_evidence(
    text: str,
    claim: Mapping[str, Any] | str,
    evidence_items: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    explicit_refs = set()
    if isinstance(claim, Mapping):
        explicit_refs.update(_URL_RE.findall(str(claim.get("citation") or "")))
        explicit_refs.update(_URL_RE.findall(str(claim.get("source_url") or "")))
    text_refs = set(_URL_RE.findall(text))
    explicit_refs.update(text_refs)
    if explicit_refs:
        matched = [item for item in evidence_items if str(item.get("source_url") or "") in explicit_refs]
        if matched:
            return matched
    claim_tokens = set(_tokens(text))
    ranked: list[tuple[int, Mapping[str, Any]]] = []
    for item in evidence_items:
        span = str(item.get("support_span") or item.get("snippet") or "")
        score = len(claim_tokens & set(_tokens(span)))
        if score:
            ranked.append((score, item))
    ranked.sort(key=lambda value: value[0], reverse=True)
    return [item for _score, item in ranked[:3]]


def _support_status(text: str, evidence: Sequence[Mapping[str, Any]], *, current_fact_required: bool, claim_type: str) -> str:
    if current_fact_required and claim_type != "boundary":
        return "unsupported"
    if not evidence:
        return "unsupported"
    score = max(_overlap(text, item) for item in evidence)
    if claim_type == "recommendation":
        return "supported" if score >= 0.12 else "partially_supported"
    if score >= 0.25:
        return "supported"
    if score >= 0.08:
        return "partially_supported"
    return "unsupported"


def _overlap(text: str, item: Mapping[str, Any]) -> float:
    claim_tokens = set(_tokens(text))
    if not claim_tokens:
        return 0.0
    evidence_tokens = set(_tokens(str(item.get("support_span") or item.get("snippet") or "")))
    return len(claim_tokens & evidence_tokens) / max(1, min(len(claim_tokens), 14))


def _evidence_refs(claim: Mapping[str, Any] | str, evidence: Sequence[Mapping[str, Any]]) -> list[str]:
    refs = []
    if isinstance(claim, Mapping):
        refs.extend(_URL_RE.findall(str(claim.get("citation") or "")))
        refs.extend(_URL_RE.findall(str(claim.get("source_url") or "")))
    for item in evidence:
        url = str(item.get("source_url") or "").strip()
        if url.startswith("https://") and url not in refs:
            refs.append(url)
    return refs[:5]


def _freshness(evidence: Sequence[Mapping[str, Any]]) -> str:
    statuses = [str(item.get("freshness_status") or "") for item in evidence]
    if "fresh" in statuses:
        return "fresh"
    if "recent_context" in statuses:
        return "recent_context"
    if "stale" in statuses:
        return "stale"
    return "unknown"


def _confidence(support_status: str, evidence: Sequence[Mapping[str, Any]]) -> str:
    if support_status == "supported" and len({str(item.get("source_group_id") or "") for item in evidence}) >= 2:
        return "medium"
    if support_status == "supported":
        return "low"
    if support_status == "partially_supported":
        return "low"
    return "none"


def _tokens(value: object) -> list[str]:
    return [token.casefold() for token in _TOKEN_RE.findall(str(value or ""))]


def _has_technical_leak(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in ("tool_calls", "estimated_cost", "vector_index_path", "sqlite row", "archive_document_id"))
