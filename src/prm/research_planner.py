"""Bounded source selection for archive-to-action research."""

from __future__ import annotations

import json
import os
from typing import Any, Mapping, Sequence

from llm.client import LLMClient


_MAX_PROMPT_CANDIDATES = 12
_MAX_SELECTED = 8


def plan_archive_evidence(candidates: Sequence[Mapping[str, Any]], *, question: str) -> dict[str, Any]:
    """Select a cited, bounded evidence set; provider use is opt-in and best-effort."""

    ranked = _ranked(candidates)
    fallback = ranked[:_MAX_SELECTED]
    result = {
        "schema_version": "prm_archive_research_plan.v1",
        "candidate_count": len(ranked),
        "selected_count": len(fallback),
        "selected_evidence_ids": [_identity(item) for item in fallback],
        "selection_mode": "deterministic_role_rank",
        "provider_egress": False,
        "items": fallback,
    }
    if not _llm_enabled() or not ranked:
        return result

    prompt_candidates = [
        {
            "id": _identity(item),
            "role": item.get("source_role"),
            "relevance": item.get("relevance_label"),
            "actionable": bool(item.get("supports_action")),
            "excerpt": _excerpt(item),
            "source": item.get("source_url"),
        }
        for item in ranked[:_MAX_PROMPT_CANDIDATES]
        if _identity(item)
    ]
    try:
        raw = LLMClient.complete(
            prompt=(
                "Select the archive sources that best answer the user's research question. "
                "Prefer concrete, replayable practice. Treat announcements, promotions and model comparisons as context only. "
                "Return JSON only: {\"selected_ids\":[...]}; select at most 8 ids and use only ids provided.\n\n"
                f"question: {question[:600]}\n"
                f"candidates: {json.dumps(prompt_candidates, ensure_ascii=False)}"
            ),
            system="You are a bounded evidence selector. Never invent sources or facts.",
            category="bot_ask",
            max_tokens=220,
            max_attempts=1,
        ).strip()
        selected_ids = _selected_ids(raw, allowed={item["id"] for item in prompt_candidates})
    except Exception:
        selected_ids = []
    if not selected_ids:
        return result
    selected = [item for item in ranked if _identity(item) in selected_ids][: _MAX_SELECTED]
    if not selected:
        return result
    return {
        **result,
        "selected_count": len(selected),
        "selected_evidence_ids": [_identity(item) for item in selected],
        "selection_mode": "llm_bounded_rerank",
        "provider_egress": True,
        "items": selected,
    }


def assess_research_gaps(candidates: Sequence[Mapping[str, Any]], *, question: str) -> dict[str, Any]:
    """Identify missing evidence types and bounded local follow-up queries."""

    rows = _ranked(candidates)
    direct = [item for item in rows if item.get("relevance_label") == "direct"]
    actionable = [item for item in rows if bool(item.get("supports_action"))]
    missing: list[str] = []
    queries: list[str] = []
    if not direct:
        missing.append("direct_topic_evidence")
    if not actionable:
        missing.append("replayable_practice")
        if _is_agent_eval_question(question):
            queries.extend((
                "agent evals harness regression fixture",
                "agent evals tool-call correctness task success",
                "agent evals failure analysis gold labels",
            ))
        else:
            topic = " ".join(str(question or "").split())[:180]
            queries.extend((f"{topic} case study implementation", f"{topic} failure mode checklist"))
    return {
        "schema_version": "prm_research_gap_check.v1",
        "status": "needs_gap_search" if queries else "sufficient",
        "candidate_count": len(rows),
        "direct_count": len(direct),
        "actionable_count": len(actionable),
        "missing_evidence": missing,
        "query_variants": _unique(queries)[:3],
    }


def _ranked(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        identity = _identity(candidate)
        if identity and identity not in unique:
            unique[identity] = dict(candidate)
    return sorted(
        unique.values(),
        key=lambda item: (
            bool(item.get("supports_action")),
            {"direct": 3, "partial": 2, "adjacent": 1}.get(str(item.get("relevance_label") or ""), 0),
            float(item.get("fusion_score") or 0.0),
            float(item.get("directness_score") or 0.0),
        ),
        reverse=True,
    )


def _selected_ids(raw: str, *, allowed: set[str]) -> list[str]:
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return []
    values = payload.get("selected_ids") if isinstance(payload, Mapping) else []
    result: list[str] = []
    for value in values if isinstance(values, list) else []:
        clean = str(value or "").strip()
        if clean in allowed and clean not in result:
            result.append(clean)
    return result[:_MAX_SELECTED]


def _identity(item: Mapping[str, Any]) -> str:
    for key in ("archive_document_id", "post_archive_document_id", "source_url", "telegram_url", "post_id"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def _excerpt(item: Mapping[str, Any]) -> str:
    return " ".join(str(item.get("snippet") or item.get("summary") or "").split())[:320]


def _llm_enabled() -> bool:
    accepted = {"1", "true", "yes", "approved"}
    return (
        os.environ.get("PRM_TELEGRAM_RAG_LLM_SYNTHESIS", "").strip().casefold() in accepted
        and os.environ.get("PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS", "").strip().casefold() in accepted
    )


def _is_agent_eval_question(question: str) -> bool:
    lowered = str(question or "").casefold()
    return ("agent" in lowered or "агент" in lowered) and ("eval" in lowered or "оцен" in lowered)


def _unique(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        clean = " ".join(str(value or "").split())
        if clean and clean not in result:
            result.append(clean)
    return result
