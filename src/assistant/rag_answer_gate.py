from __future__ import annotations

import re
from typing import Any


RAG_ANSWER_GATE_VERSION = "rag_answer_gate.v1"

_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё][0-9A-Za-zА-Яа-яЁё_+-]{1,}")

_CURRENT_MARKERS = (
    "today",
    "current",
    "currently",
    "latest",
    "right now",
    "pricing",
    "prices",
    "hiring",
    "layoffs",
    "сегодня",
    "сейчас",
    "текущ",
    "актуальн",
    "последн",
    "свеж",
    "цены",
    "стоим",
    "купить",
    "нанимает",
    "увольняет",
)

_EXTERNAL_VERIFICATION_MARKERS = (
    "external verification",
    "live web",
    "web verification",
    "linked source",
    "linked-source",
    "github",
    "docs",
    "source cache",
    "source verification",
    "внешн",
    "вериф",
    "провер",
    "первоисточник",
    "ссылк",
    "линк",
    "кэш",
    "док",
)

_PROJECT_STATE_MARKERS = (
    "approved",
    "deployed",
    "finished",
    "implemented",
    "production",
    "started",
    "vector database backend",
    "vector index",
    "embedding provider",
    "dogfood",
    "service",
    "утвержден",
    "одобрен",
    "внедрил",
    "внедрен",
    "завершен",
    "запущен",
    "создала",
    "создан",
    "прочитал все",
    "production db",
)

_PROOF_DEMAND_MARKERS = (
    "prove",
    "proof",
    "show documents proving",
    "докажи",
    "доказывают",
    "документы доказывают",
    "какие документы",
)


def assess_rag_answer_gate(
    question: str,
    *,
    source_count: int,
    external_verification_hint: bool = False,
) -> dict[str, Any]:
    """Decide whether retrieved context is sufficient for a product RAG answer.

    This is a deterministic answer-level gate. It deliberately does not run
    retrieval, embeddings, provider calls, live web checks, or writes.
    """
    clean_question = " ".join(str(question or "").split())
    source_total = max(0, int(source_count or 0))
    proof_required = _requires_project_state_proof(clean_question)
    live_required = bool(external_verification_hint) or _requires_external_verification(clean_question)
    current_answer_required = _requires_current_answer(clean_question)

    if source_total <= 0:
        status = "needs_external_verification" if live_required or current_answer_required else "insufficient_evidence"
        return _gate(
            status=status,
            source_count=source_total,
            allow_answer=False,
            current_claim_allowed=False,
            no_answer_required=True,
            external_verification_required=live_required or current_answer_required,
            reason="no_cited_context",
        )

    if proof_required:
        return _gate(
            status="insufficient_evidence",
            source_count=source_total,
            allow_answer=False,
            current_claim_allowed=False,
            no_answer_required=True,
            external_verification_required=live_required or current_answer_required,
            reason="unsupported_project_state_claim",
        )

    if current_answer_required:
        return _gate(
            status="needs_external_verification",
            source_count=source_total,
            allow_answer=False,
            current_claim_allowed=False,
            no_answer_required=True,
            external_verification_required=True,
            reason="current_external_fact_required",
        )

    if live_required:
        return _gate(
            status="answerable_with_freshness_boundary",
            source_count=source_total,
            allow_answer=True,
            current_claim_allowed=False,
            no_answer_required=False,
            external_verification_required=True,
            reason="archive_context_requires_external_freshness_boundary",
        )

    return _gate(
        status="answerable",
        source_count=source_total,
        allow_answer=True,
        current_claim_allowed=True,
        no_answer_required=False,
        external_verification_required=False,
        reason="cited_context_sufficient_for_archive_answer",
    )


def _gate(
    *,
    status: str,
    source_count: int,
    allow_answer: bool,
    current_claim_allowed: bool,
    no_answer_required: bool,
    external_verification_required: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": RAG_ANSWER_GATE_VERSION,
        "status": status,
        "reason": reason,
        "source_count": int(source_count),
        "allow_answer": bool(allow_answer),
        "current_claim_allowed": bool(current_claim_allowed),
        "no_answer_required": bool(no_answer_required),
        "external_verification_required": bool(external_verification_required),
        "vector_backend_required": False,
        "embeddings_run": False,
    }


def _requires_project_state_proof(question: str) -> bool:
    lowered = question.casefold()
    if _contains_any(lowered, _PROOF_DEMAND_MARKERS) and _contains_any(lowered, _PROJECT_STATE_MARKERS):
        return True
    if _contains_any(lowered, ("уже", "already")) and _contains_any(lowered, _PROJECT_STATE_MARKERS):
        return True
    if _contains_any(lowered, ("сейчас", "current", "currently")) and _contains_any(lowered, _PROJECT_STATE_MARKERS):
        return True
    return False


def _requires_current_answer(question: str) -> bool:
    lowered = question.casefold()
    if _contains_any(lowered, ("точные текущие цены", "current prices", "pricing today")):
        return True
    if _contains_any(lowered, ("сегодня", "today")) and _contains_any(lowered, ("цены", "стоим", "купить", "price", "pricing", "buy")):
        return True
    return False


def _requires_external_verification(question: str) -> bool:
    lowered = question.casefold()
    if _requires_current_answer(question):
        return True
    return _contains_any(lowered, _CURRENT_MARKERS) or _contains_any(lowered, _EXTERNAL_VERIFICATION_MARKERS)


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    tokens = _tokens(value)
    for needle in needles:
        clean = needle.casefold().strip()
        if not clean:
            continue
        if " " in clean or "-" in clean:
            if clean in value:
                return True
            continue
        if clean in tokens or any(token.startswith(clean) for token in tokens):
            return True
    return False


def _tokens(value: str) -> set[str]:
    result: set[str] = set()
    for match in _TOKEN_RE.finditer(value):
        token = match.group(0).casefold().strip("_-+")
        if token:
            result.add(token)
    return result
