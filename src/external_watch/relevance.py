"""Deterministic profile-aware UTD shadow relevance policy."""
from __future__ import annotations

from typing import Any, Mapping

CATEGORY_TERMS = {
    "program": ("academic calendar", "registrar", "registration", "deadline", "census", "withdraw", "full term", "8-week"),
    "career": ("career", "intern", "job", "employer", "networking", "professional development"),
    "ai": ("artificial intelligence", " ai ", "machine learning", "agent", "rag", "research", "engineering", "data science"),
    "isso": ("isso", "international", "f-1", "f1", "j-1", "j1", "immigration", "sevis", "cpt", "opt", "orientation"),
    "benefits": ("basic needs", "resource", "financial", "food", "housing", "clothing", "emergency fund"),
    "spouse_family": ("spouse", "family", "dependent", "f-2", "f2", "parenting"),
}


def classify(item: Mapping[str, Any], profile: Mapping[str, Any]) -> dict[str, Any]:
    if profile.get("paused"):
        return {"relevant": False, "categories": [], "reason": "profile_paused", "urgent": False}
    selected = set(profile.get("categories") or [])
    muted = set(profile.get("muted_sources") or [])
    text = " ".join(str(item.get(k) or "") for k in ("title", "material_text", "status", "url"))
    text += " " + " ".join(str(x) for key in ("audiences", "topics", "departments", "event_types") for x in (item.get(key) or []))
    padded = f" {text.casefold()} "
    matched = []
    for category, terms in CATEGORY_TERMS.items():
        if category not in selected or category in muted:
            continue
        if any(term in padded for term in terms):
            matched.append(category)
    if "spouse_family" in matched:
        explicit = any(term in padded for term in (" spouse ", " family ", " dependent ", " f-2 ", " f2 "))
        if not explicit:
            matched.remove("spouse_family")
    urgent = any(term in padded for term in (" deadline ", " cancelled ", " canceled ", " census ", " immigration ", " sevis "))
    return {"relevant": bool(matched), "categories": matched, "reason": "term_match" if matched else "no_profile_match", "urgent": urgent}
