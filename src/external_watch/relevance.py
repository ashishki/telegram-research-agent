"""Deterministic, source-aware UTD shadow relevance policy."""
from __future__ import annotations

import re
from typing import Any, Mapping

STRONG_TERMS = {
    "career": ("career", "internship", "internships", "job fair", "employer", "recruiting", "networking", "resume", "interview"),
    "ai": ("artificial intelligence", "generative ai", "machine learning", "deep learning", "large language model", "llm", "agentic", "data science", "fintech", "financial technology"),
    "isso": ("isso", "f-1", " f1 ", "j-1", " j1 ", "sevis", "cpt", "opt", "immigration", "maintain status", "international student orientation"),
    "benefits": ("basic needs", "comet cupboard", "food pantry", "emergency fund", "housing assistance", "financial assistance"),
    "spouse_family": ("spouse", "family", "dependent", "f-2", " f2 ", "parenting"),
}


def _haystack(item: Mapping[str, Any]) -> str:
    text = " ".join(str(item.get(k) or "") for k in ("title", "material_text", "status", "url", "source"))
    text += " " + " ".join(str(x) for key in ("audiences", "topics", "departments", "event_types") for x in (item.get(key) or []))
    return f" {text.casefold()} "


def _profile_phrases(profile: Mapping[str, Any], field: str) -> list[str]:
    raw = str(profile.get(field) or "").casefold()
    phrases=[]
    for part in re.split(r"[,;/|]", raw):
        phrase=" ".join(part.split()).strip()
        if len(phrase) >= 4 and phrase not in {"research", "engineering", "internships", "career events"}:
            phrases.append(phrase)
    return phrases


def classify(item: Mapping[str, Any], profile: Mapping[str, Any]) -> dict[str, Any]:
    if profile.get("paused"):
        return {"relevant": False, "categories": [], "reason": "profile_paused", "urgent": False, "score": 0}
    selected = set(profile.get("categories") or [])
    muted = set(profile.get("muted_sources") or [])
    text = _haystack(item)
    matched: list[str] = []
    score = 0
    reasons: list[str] = []

    source = str(item.get("source") or "")
    topics = {str(x).casefold() for x in (item.get("topics") or [])}
    departments = {str(x).casefold() for x in (item.get("departments") or [])}

    if "program" in selected and "program" not in muted:
        if "academic calendar" in topics or "office of the registrar" in departments:
            matched.append("program"); score += 90; reasons.append("registrar_or_academic_calendar")
        else:
            program_phrases = _profile_phrases(profile, "program")
            if any(p in text for p in program_phrases):
                matched.append("program"); score += 75; reasons.append("program_phrase")

    for category in ("career", "ai", "isso", "benefits", "spouse_family"):
        if category not in selected or category in muted:
            continue
        terms = STRONG_TERMS[category]
        if any(term in text for term in terms):
            matched.append(category); score += 70; reasons.append(f"strong_{category}_term")

    if "ai" in selected and "ai" not in muted and "ai" not in matched:
        if any(p in text for p in _profile_phrases(profile, "ai_interests")):
            matched.append("ai"); score += 65; reasons.append("ai_profile_phrase")
    if "career" in selected and "career" not in muted and "career" not in matched:
        if any(p in text for p in _profile_phrases(profile, "career_goals")):
            matched.append("career"); score += 65; reasons.append("career_profile_phrase")

    # Stable source documents are relevant only to their explicitly selected category.
    if source == "isso" and "isso" in selected and "isso" not in muted:
        if "isso" not in matched: matched.append("isso")
        score = max(score, 90); reasons.append("isso_primary_document")
    if source == "basic_needs" and "benefits" in selected and "benefits" not in muted:
        if "benefits" not in matched: matched.append("benefits")
        score = max(score, 85); reasons.append("basic_needs_primary_document")

    # Family alerts remain explicit-only even if another category matches.
    if "spouse_family" in matched and not any(term in text for term in STRONG_TERMS["spouse_family"]):
        matched.remove("spouse_family")

    relevant = bool(matched) and score >= 60
    urgent = relevant and any(term in text for term in (" deadline ", " cancelled ", " canceled ", " census ", " sevis ", " immigration "))
    return {"relevant": relevant, "categories": matched, "reason": ",".join(dict.fromkeys(reasons)) if reasons else "no_specific_profile_match", "urgent": urgent, "score": min(score, 100)}
