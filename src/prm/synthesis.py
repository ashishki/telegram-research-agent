"""Optional bounded synthesis over already approved claims."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from assistant.claim_ledger import verify_answer_against_evidence
from llm.client import LLMClient
from prm.archive_contract import ARCHIVE_RESPONSE_CONTRACTS
from prm.archive_context import ArchiveEvidenceContext
from prm.archive_synthesis_transport import (
    ArchiveSynthesisTransportOutcomeUnknown,
    ArchiveSynthesisTransportUnavailable,
    complete_archive_synthesis,
)
from prm.capabilities import AuthorizationDecision
from prm.contracts import ArchiveSynthesisAccess

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


@dataclass(frozen=True, slots=True)
class ArchiveSynthesisOutcome:
    """A verified generation result or a truthful reason to keep local output."""

    text: str | None
    status: str
    measurement: Mapping[str, object]


def synthesis_allowed(authorization: AuthorizationDecision | None = None) -> bool:
    """Keep the legacy generic synthesis entrypoint local-only.

    PA-04 uses ``synthesize_archive_response`` instead: it creates an immutable
    selected-evidence packet and consumes the paired OpenAI text/context
    reservations. This legacy Anthropic-shaped function still has no archive
    provenance carrier, so it must never be enabled by a grant alone.
    """

    del authorization
    return False


def synthesize_answer(
    payload: Mapping[str, Any],
    *,
    deterministic_fallback: str,
    mode: str,
    evidence_items: Sequence[Mapping[str, Any]],
    primary_intent: str = "",
    response_contract_id: str = "",
    authorization: AuthorizationDecision | None = None,
) -> str | None:
    if not synthesis_allowed(authorization):
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
            authorization=authorization,
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
        authorization=authorization,
    )


def synthesize_archive_response(
    payload: Mapping[str, Any],
    *,
    question: str,
    evidence_items: Sequence[Mapping[str, Any]],
    access: ArchiveSynthesisAccess | None,
) -> ArchiveSynthesisOutcome:
    """Generate only from a locally selected, immutable archive evidence set.

    No access, malformed provenance, a denied transport, an unknown provider
    outcome, a wrong citation, or a false no-evidence answer all preserve the
    deterministic local archive renderer.  The returned measurement carries no
    excerpts or user question.
    """

    contract = _mapping(payload.get("archive_contract"))
    context = ArchiveEvidenceContext.from_payload(
        question=question,
        archive_contract=contract,
        evidence_items=evidence_items,
    )
    if context is None:
        _abandon_archive_access(access)
        return ArchiveSynthesisOutcome(
            text=None,
            status="context_unavailable",
            measurement={"provider_egress_attempted": False, "context_egress_attempted": False},
        )
    base_measurement: dict[str, object] = {**context.public_measurement()}
    if type(access) is not ArchiveSynthesisAccess:
        return ArchiveSynthesisOutcome(
            text=None,
            status="authorization_required",
            measurement={**base_measurement, "provider_egress_attempted": False, "context_egress_attempted": False},
        )
    try:
        result = complete_archive_synthesis(context=context, access=access)
    except ArchiveSynthesisTransportOutcomeUnknown:
        return ArchiveSynthesisOutcome(
            text=None,
            status="provider_outcome_unknown",
            measurement={**base_measurement, "provider_egress_attempted": True, "context_egress_attempted": True},
        )
    except ArchiveSynthesisTransportUnavailable:
        return ArchiveSynthesisOutcome(
            text=None,
            status="provider_unavailable_or_denied",
            measurement={**base_measurement, "provider_egress_attempted": False, "context_egress_attempted": False},
        )

    answer = " ".join(str(result.text or "").split())
    if not _verified_archive_answer(answer, contract=contract, evidence_items=evidence_items):
        return ArchiveSynthesisOutcome(
            text=None,
            status="generated_answer_rejected",
            measurement={**base_measurement, **result.receipt.public_measurement()},
        )
    return ArchiveSynthesisOutcome(
        text=answer,
        status="generated_verified",
        measurement={**base_measurement, **result.receipt.public_measurement()},
    )


def _abandon_archive_access(access: object) -> None:
    if type(access) is not ArchiveSynthesisAccess:
        return
    for decision in (access.query_authorization, access.context_authorization):
        if decision.reservation is not None:
            decision.reservation.abandon_before_transport()


def _synthesize_archive_answer(
    payload: Mapping[str, Any],
    *,
    deterministic_fallback: str,
    evidence_items: Sequence[Mapping[str, Any]],
    primary_intent: str,
    authorization: AuthorizationDecision | None,
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
    answer = _call_and_verify(
        prompt,
        evidence_items=evidence_items,
        project_name="",
        authorization=authorization,
    )
    if not answer:
        return None
    if any(marker.casefold() in answer.casefold() for marker in _ARCHIVE_FORBIDDEN_SECTIONS):
        return None
    if int(summary.get("direct_count") or 0) == 0 and "прям" not in answer.casefold():
        return None
    return answer


def _verified_archive_answer(
    answer: str,
    *,
    contract: Mapping[str, Any],
    evidence_items: Sequence[Mapping[str, Any]],
) -> bool:
    if not answer or len(answer) > 1_800:
        return False
    lowered = answer.casefold()
    if any(marker.casefold() in lowered for marker in _ARCHIVE_FORBIDDEN_SECTIONS):
        return False
    summary = _mapping(contract.get("result_summary"))
    direct = _mappings(contract.get("direct_findings"))
    direct_count = int(summary.get("direct_count") or 0)
    if direct_count and any(marker in lowered for marker in (
        "недостаточно данных", "прямых материалов не найден", "ничего не найдено", "not enough evidence", "no direct evidence",
    )):
        return False
    if not direct_count and not any(marker in lowered for marker in ("прям", "direct")):
        return False
    # A direct finding that contributes to the answer cannot silently lose its
    # source identity on the way through generation.
    direct_sources = {str(item.get("source_url") or "").strip() for item in direct}
    if any(source and source not in answer for source in direct_sources):
        return False
    verification = verify_answer_against_evidence(
        answer,
        evidence_items,
        current_fact_required=False,
        project_name="",
    )
    metrics = _mapping(verification.get("metrics"))
    return bool(
        verification.get("verification_complete")
        and int(metrics.get("current_fact_violations") or 0) == 0
        and int(metrics.get("technical_leaks") or 0) == 0
        and float(metrics.get("unsupported_claim_rate") or 0.0) == 0.0
        and (
            int(metrics.get("claim_count") or 0) == 0
            or float(metrics.get("citation_integrity") or 0.0) == 1.0
        )
    )


def _call_and_verify(
    prompt: str,
    *,
    evidence_items: Sequence[Mapping[str, Any]],
    project_name: str,
    authorization: AuthorizationDecision | None,
) -> str | None:
    try:
        answer = LLMClient.complete(
            prompt=prompt,
            system="You are a grounded synthesis layer. Unsupported facts and intent substitution are forbidden.",
            category="bot_ask",
            max_tokens=900,
            max_attempts=1,
            authorization=authorization,
            data_class="private_archive",
            owner_ref=authorization.owner_ref if authorization is not None else None,
            connection_ref=authorization.connection_ref if authorization is not None else None,
            resource_ref=authorization.resource_ref if authorization is not None else None,
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
    # Publication is an allow decision, not a diagnostic.  A generated answer
    # with any unsupported factual clause, an unverified tail, or a citation
    # that does not bind to its selected span falls back to deterministic text.
    if (
        int(metrics.get("current_fact_violations") or 0)
        or not bool(verification.get("verification_complete"))
        or float(metrics.get("unsupported_claim_rate") or 0.0) > 0.0
        or (int(metrics.get("claim_count") or 0) > 0 and float(metrics.get("citation_integrity") or 0.0) < 1.0)
    ):
        return None
    return answer


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, Mapping)]
