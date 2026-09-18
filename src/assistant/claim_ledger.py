"""Claim ledger and deterministic grounding metrics for PRM answers."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping, Sequence


CLAIM_LEDGER_SCHEMA_VERSION = "prm_claim_ledger.v1"
ANSWER_CLAIM_VERIFICATION_SCHEMA_VERSION = "prm_answer_claim_verification.v1"
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_+-]{2,}")
_URL_RE = re.compile(r"https://[^\s)\]]+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|[\n\r]+")
_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")
_SECTION_HEADINGS = {
    "answer",
    "boundaries",
    "context",
    "direct answer",
    "evidence",
    "limits",
    "next steps",
    "project fit",
    "question",
    "short answer",
    "sources",
    "unknowns",
    "вопрос",
    "где доказательства слабые",
    "границы",
    "источники",
    "контекст проекта",
    "короткий вывод",
    "короткий ответ",
    "ограничения",
    "почему это важно тебе",
    "рекомендация",
    "что делать",
    "что найдено",
    "что известно сейчас",
    "следующий шаг",
}


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
    approved = payload.get("approved_claim_ledger") if isinstance(payload.get("approved_claim_ledger"), Mapping) else {}
    claims: list[Mapping[str, Any] | str] = []
    for item in approved.get("claims") or []:
        if isinstance(item, Mapping) and str(item.get("support_status") or "") == "supported":
            claims.append(
                {
                    "claim_text": item.get("claim_text"),
                    "claim_type": item.get("claim_type") or "source_fact",
                    "citation": next(iter(item.get("evidence_refs") or []), ""),
                }
            )
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


def build_candidate_claims_from_evidence(
    evidence_items: Sequence[Mapping[str, Any]],
    *,
    max_claims: int = 6,
) -> list[dict[str, Any]]:
    """Convert bounded evidence spans into pre-synthesis candidate claims.

    This runs before any answer synthesis.  It is intentionally allowed to use
    evidence spans because these are candidate claims for the ledger, not the
    final-answer verifier.
    """

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in evidence_items:
        span = " ".join(str(item.get("support_span") or item.get("snippet") or "").split())
        if not span:
            continue
        normalized = _normalized_text(span)
        if normalized in seen:
            continue
        seen.add(normalized)
        candidates.append(
            {
                "claim_text": span[:280],
                "claim_type": "source_fact",
                "source_url": item.get("source_url") or "",
                "evidence_id": item.get("evidence_id") or "",
            }
        )
        if len(candidates) >= max(1, min(12, int(max_claims or 1))):
            break
    return candidates


def approve_claim_ledger(ledger: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only claims that passed deterministic support checks."""

    approved = [
        dict(claim)
        for claim in ledger.get("claims") or []
        if isinstance(claim, Mapping) and str(claim.get("support_status") or "") == "supported"
    ]
    return {
        "schema_version": CLAIM_LEDGER_SCHEMA_VERSION,
        "approval_stage": "pre_synthesis",
        "claim_count": len(approved),
        "claims": approved,
        "metrics": evaluate_claim_grounding(approved),
        "candidate_claim_count": int(ledger.get("claim_count") or 0),
    }


def extract_atomic_claims_from_answer(answer: str, *, max_claims: int = 20) -> list[str]:
    """Extract scoreable atomic claims from the rendered final answer text."""

    claims: list[str] = []
    seen: set[str] = set()
    for raw_part in _SENTENCE_SPLIT_RE.split(str(answer or "")):
        clean = _clean_answer_sentence(raw_part)
        if not clean:
            continue
        normalized = _normalized_text(clean)
        if normalized in seen:
            continue
        seen.add(normalized)
        claims.append(clean[:420])
        if len(claims) >= max(1, min(50, int(max_claims or 1))):
            break
    return claims


def verify_answer_against_evidence(
    answer: str,
    evidence_items: Sequence[Mapping[str, Any]],
    *,
    current_fact_required: bool = False,
    project_name: str = "",
    max_claims: int = 20,
) -> dict[str, Any]:
    """Verify the rendered answer, claim by claim, against exact snippets.

    Unlike ``build_candidate_claims_from_evidence``, this function never creates
    claims from support spans.  It first extracts atomic claims from the final
    answer, then attaches the closest exact evidence snippets and deterministic
    entailment verdicts.
    """

    # Keep the URL which the user actually sees attached to its sentence.  The
    # older verifier stripped it while cleaning a sentence and then attached a
    # lexically similar source, turning a wrong displayed URL into a pass.
    raw_parts = _SENTENCE_SPLIT_RE.split(str(answer or ""))
    extracted_records: list[dict[str, str]] = []
    seen: set[str] = set()
    limit = max(1, min(50, int(max_claims or 1)))
    candidate_count = 0
    for raw_part in raw_parts:
        clean = _clean_answer_sentence(raw_part)
        if not clean:
            # Renderers often put a nearby source on its own line.  It still
            # binds to the preceding claim rather than authorizing a lexical
            # replacement with another evidence item.
            urls = _URL_RE.findall(raw_part)
            if urls and extracted_records and _is_nearby_source_line(raw_part):
                extracted_records[-1]["citation"] = " ".join(urls)
            continue
        normalized = _normalized_text(clean)
        if normalized in seen:
            continue
        seen.add(normalized)
        candidate_count += 1
        if len(extracted_records) < limit:
            extracted_records.append({"claim_text": clean, "citation": " ".join(_URL_RE.findall(raw_part))})
    ledger = build_claim_ledger(
        [
            {
                "claim_text": item["claim_text"],
                "citation": item["citation"],
                "claim_type": "boundary" if _is_boundary_claim(item["claim_text"]) else "source_fact",
            }
            for item in extracted_records
        ],
        evidence_items,
        current_fact_required=current_fact_required,
        project_name=project_name,
    )
    verified_claims = []
    for claim in ledger.get("claims") or []:
        if not isinstance(claim, Mapping):
            continue
        matched = _matching_evidence(str(claim.get("claim_text") or ""), claim, evidence_items)
        verified_claims.append(
            {
                **dict(claim),
                "entailment_verdict": _entailment_verdict(str(claim.get("support_status") or "")),
                "exact_evidence_snippets": [
                    {
                        "evidence_id": str(item.get("evidence_id") or ""),
                        "source_url": str(item.get("source_url") or ""),
                        "support_span": str(item.get("support_span") or item.get("snippet") or "")[:280],
                    }
                    for item in matched[:3]
                    if str(item.get("support_span") or item.get("snippet") or "").strip()
                ],
            }
        )
    metrics = evaluate_claim_grounding(verified_claims)
    metrics["verification_complete"] = candidate_count <= limit
    metrics["unverified_tail_claim_count"] = max(0, candidate_count - len(verified_claims))
    return {
        "schema_version": ANSWER_CLAIM_VERIFICATION_SCHEMA_VERSION,
        "claim_extraction_source": "rendered_final_answer",
        "claim_count": len(verified_claims),
        "candidate_claim_count": candidate_count,
        "verification_complete": candidate_count <= limit,
        "claims": verified_claims,
        "metrics": metrics,
    }


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
    current_violations = sum(
        1
        for claim in claims
        if claim.get("freshness") == "current_fact_blocked"
        and claim.get("support_status") == "supported"
        and claim.get("claim_type") != "boundary"
    )
    technical_leaks = sum(1 for claim in claims if _has_technical_leak(str(claim.get("claim_text") or "")))
    citation_integrity = sum(
        1
        for claim in claims
        if claim.get("evidence_refs")
        and claim.get("support_status") == "supported"
        and all(
            str(status) == "supported"
            for status in (claim.get("citation_support") if isinstance(claim.get("citation_support"), Mapping) else {}).values()
        )
    )
    return {
        "schema_version": "prm_claim_grounding_metrics.v1",
        "claim_count": total,
        "supported_claim_rate": round(supported / total, 4) if total else 1.0,
        "partial_claim_rate": round(partial / total, 4) if total else 0.0,
        "unsupported_claim_rate": round(unsupported / total, 4) if total else 0.0,
        "citation_completeness": round(cited / total, 4) if total else 1.0,
        "citation_precision": round(citation_urls / max(1, cited), 4),
        "citation_integrity": round(citation_integrity / max(1, cited), 4),
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
        "citation_integrity": float(metrics.get("citation_integrity") or 0.0),
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
    citation_support = {
        ref: _support_status(
            text,
            [item for item in evidence if str(item.get("source_url") or "") == ref],
            current_fact_required=current_fact_required,
            claim_type=claim_type,
        )
        for ref in refs
    }
    if refs and any(status != "supported" for status in citation_support.values()):
        support_status = "unsupported"
    return {
        "claim_id": "claim:" + hashlib.sha256(f"{index}:{text}".encode()).hexdigest()[:12],
        "claim_text": text,
        "claim_type": claim_type,
        "freshness": "current_fact_blocked" if current_fact_required else _freshness(evidence),
        "support_status": support_status,
        "evidence_refs": refs,
        "matched_evidence": [str(item.get("source_url") or "") for item in evidence],
        "citation_support": citation_support,
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
        # An explicit visible citation is a binding, not a search hint.  Do not
        # silently replace it with a different lexically similar source.
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
    if claim_type == "boundary":
        return "supported"
    if current_fact_required and claim_type == "boundary":
        return "supported"
    if current_fact_required and claim_type != "boundary":
        return "unsupported"
    if not evidence:
        return "unsupported"
    score = max(_overlap(text, item) for item in evidence)
    if claim_type == "source_fact" and not any(_critical_facts_match(text, item) for item in evidence):
        return "unsupported"
    if claim_type == "recommendation":
        return "supported" if score >= 0.12 else "partially_supported"
    if score >= 0.25:
        return "supported"
    if score >= 0.08:
        return "partially_supported"
    return "unsupported"


def _critical_facts_match(text: str, item: Mapping[str, Any]) -> bool:
    """Reject deterministic number/negation/actor mutations without claiming NLI.

    This deliberately does not try to validate free paraphrase semantically.
    It only catches the high-impact factual slots that lexical overlap misses.
    """
    support = str(item.get("support_span") or item.get("snippet") or "")
    claim_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", text))
    support_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", support))
    if claim_numbers and not claim_numbers.issubset(support_numbers):
        return False
    negatives = (" not ", " no ", " never ", "не ", "нет ", "без ")
    if any(marker in f" {text.casefold()} " for marker in negatives) != any(marker in f" {support.casefold()} " for marker in negatives):
        return False
    # Capitalized identifiers after the opening word are stable enough to catch
    # the audited "different subject" mutation while leaving ordinary prose
    # and Russian sentence capitalization alone.
    entity_text = text.split(":", 1)[-1] if ":" in text else text
    claim_names = set(re.findall(r"\b[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9_-]{2,}\b", entity_text))
    support_names = set(re.findall(r"\b[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9_-]{2,}\b", support))
    # A sentence-initial English product/actor is also a critical slot when
    # the support span starts with a different capitalized identifier.
    claim_first = re.match(r"\s*([A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9_-]{2,})\b", text)
    support_first = re.match(r"\s*([A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9_-]{2,})\b", support)
    if ":" not in text and claim_first and support_first and claim_first.group(1) != support_first.group(1):
        return False
    # Russian answers often lowercase the second token in a named actor (for
    # example, "Сервис бета").  Treat the token following a small set of
    # explicit actor labels as a factual slot even when it is lowercase; this
    # is deliberately narrower than treating arbitrary prose as an entity.
    actor_prefix = r"(?:service|сервис|проект|компания|продукт|модель)"
    claim_actor_values = {
        value.casefold()
        for value in re.findall(rf"\b{actor_prefix}\s+([A-Za-zА-Яа-яЁё0-9_-]{{2,}})\b", text, flags=re.IGNORECASE)
    }
    support_actor_values = {
        value.casefold()
        for value in re.findall(rf"\b{actor_prefix}\s+([A-Za-zА-Яа-яЁё0-9_-]{{2,}})\b", support, flags=re.IGNORECASE)
    }
    if claim_actor_values and not claim_actor_values.issubset(support_actor_values):
        return False
    return not claim_names or claim_names.issubset(support_names)


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
    # Evidence matching can help assess a claim, but never manufactures the
    # claim→source edge the operator sees.  Final publication requires an
    # explicit displayed citation for source-dependent factual text.
    return list(dict.fromkeys(refs))[:5]


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


def _clean_answer_sentence(value: str) -> str:
    clean = _BULLET_PREFIX_RE.sub("", str(value or "")).strip()
    clean = re.sub(r"\s+", " ", clean)
    if not clean:
        return ""
    lowered = clean.strip(":").casefold()
    if lowered in _SECTION_HEADINGS:
        return ""
    if lowered.startswith(("http://", "https://")):
        return ""
    if _URL_RE.search(clean) and "@" in clean and re.search(r"\b\d{4}-\d{2}-\d{2}\b", clean):
        # A renderer source inventory is navigational metadata, not another
        # claim. Its URL must not be rebound to the previous factual sentence.
        return ""
    if _is_meta_or_uncertainty_line(lowered):
        return ""
    if clean.endswith(":") and len(_tokens(clean)) <= 6:
        return ""
    # A short factual sentence (for example, "Цена 900 долларов") is exactly
    # the kind of answer that must not evade final verification.
    if len(_tokens(clean)) < 2:
        return ""
    clean = _URL_RE.sub("", clean).strip(" -;,.")
    if len(_tokens(clean)) < 2:
        return ""
    return clean


def _normalized_text(value: str) -> str:
    return " ".join(_tokens(value))


def _is_boundary_claim(value: str) -> bool:
    lowered = value.casefold()
    # This is an allow-list for the deterministic current-fact boundary, not
    # a generic keyword classifier.  In particular, "external verification"
    # must not turn “external verification showed price 900” into a boundary.
    if lowered.startswith((
        "external verification was not run",
        "live web verification was not run",
        "no live web verification",
        "я не могу подтвердить актуальный",
        "я не могу подтвердить текущий факт",
        "внешняя проверка не запускалась",
        "релевантного локального исторического контекста нет",
        "разрешить отдельную проверку официальных источников",
        "или спросить «что было в архиве",
    )):
        return True
    return (
        lowered.startswith("в локальном архиве есть")
        and "историческ" in lowered
        and "не актуальн" in lowered
    )


def _is_meta_or_uncertainty_line(lowered: str) -> bool:
    return any(
        marker in lowered
        for marker in (
            "в архиве найдено",
            "в локальном архиве найдено",
            "found ",
            "local source",
            "релевантных источн",
            "локальных источников",
            "явных противоречий",
            "противоречий в выбранных",
            "недостаточно данных",
            "остаётся неизвестным",
            "остается неизвестным",
            "не проверялись отдельно",
            "not evaluated separately",
            "я не публикую свободный пересказ",
            "подходящего проверяемого фрагмента",
            "не удалось собрать проверяемый источник-атрибутированный ответ",
            "уточни запрос или источник",
            "текущий внешний факт не подтверждён",
        )
    )


def _is_nearby_source_line(value: str) -> bool:
    """Only a labelled source line may bind to the immediately prior claim."""
    clean = str(value or "").strip().casefold()
    return clean.startswith(("источник:", "source:"))


def _entailment_verdict(support_status: str) -> str:
    if support_status == "supported":
        return "entailed"
    if support_status == "partially_supported":
        return "partially_entailed"
    return "not_entailed"
