from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping, Sequence
from uuid import uuid4

from assistant.linked_sources import (
    FakeLinkedSourceFetcher,
    LinkedSourceApprovals,
    LinkedSourceFetcher,
    resolve_linked_sources,
)
from assistant.claim_ledger import (
    approve_claim_ledger,
    build_candidate_claims_from_evidence,
    build_claim_ledger,
    claim_ledger_public_summary,
    verify_answer_against_evidence,
)
from assistant.evidence_quality import build_evidence_quality_items, evidence_quality_summary
from assistant.pi_facade import PersonalIntelligenceFacade
from assistant.pi_memory import build_memory_proposal, query_saved_knowledge
from assistant.professional_workflows import (
    build_professional_answer,
    build_ai_systems_project_application_workflow,
    build_career_portfolio_gap_workflow,
    build_enterprise_ai_adoption_workflow,
    build_learning_experiment_workflow,
    build_writer_editor_brief_workflow,
)
from assistant.professional_personalization import infer_professional_lens, rerank_for_professional_lens
from assistant.rag_context_pack import build_rag_context_pack, render_rag_context_pack
from assistant.archive_relevance import rank_archive_items
from assistant.retrieval_policy import build_query_rewrites, select_retrieval_policy
from config.settings import Settings
from prm.research_planner import assess_research_gaps


MEMORY_RESEARCH_SCHEMA_VERSION = "memory_research_answer.v1"
MEMORY_RESEARCH_RECEIPT_SCHEMA_VERSION = "memory_research_receipt.v1"

PROJECT_LABELS = {
    "direct_implication",
    "weak_watch",
    "learning_relevance",
    "no_match",
    "ambiguous_project",
}

_HARD_MAX_TOOL_CALLS = 8
_HARD_MAX_ARCHIVE_SOURCES = 10
_HARD_MAX_ARCHIVE_CANDIDATES = 32
_HARD_MAX_LINKED_SOURCES = 5
_HARD_MAX_RETRIES = 1
_HARD_MAX_TIMEOUT_SECONDS = 60
_HARD_MAX_PROMPT_CHARS = 12_000
_OPEN_BROWSING_TERMS = (
    "browse web",
    "open web",
    "search web",
    "search internet",
    "live web",
    "google it",
    "look it up online",
    "посмотри в интернете",
    "поищи в интернете",
    "загугли",
    "брауз",
    "живой веб",
)
_MAX_ARCHIVE_QUERY_VARIANTS = 4
_QUERY_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё][0-9A-Za-zА-Яа-яЁё_+-]{1,}")
_QUERY_STOPWORDS = {
    "a",
    "about",
    "after",
    "again",
    "all",
    "already",
    "and",
    "any",
    "apply",
    "are",
    "around",
    "as",
    "at",
    "answer",
    "answers",
    "be",
    "by",
    "can",
    "could",
    "does",
    "for",
    "from",
    "give",
    "had",
    "has",
    "have",
    "how",
    "interesting",
    "into",
    "is",
    "it",
    "last",
    "me",
    "month",
    "months",
    "my",
    "need",
    "needs",
    "of",
    "on",
    "or",
    "our",
    "recent",
    "should",
    "show",
    "so",
    "tell",
    "that",
    "the",
    "there",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "which",
    "why",
    "with",
    "day",
    "days",
    "week",
    "weeks",
    "а",
    "без",
    "было",
    "бы",
    "в",
    "вот",
    "все",
    "всю",
    "где",
    "два",
    "две",
    "дней",
    "дня",
    "день",
    "для",
    "до",
    "его",
    "если",
    "есть",
    "еще",
    "же",
    "за",
    "и",
    "из",
    "или",
    "как",
    "какие",
    "какой",
    "когда",
    "ли",
    "месяц",
    "месяца",
    "месяцев",
    "мне",
    "мой",
    "моего",
    "мои",
    "можно",
    "на",
    "надо",
    "нам",
    "не",
    "неделю",
    "недели",
    "недель",
    "него",
    "них",
    "но",
    "о",
    "ок",
    "он",
    "она",
    "они",
    "от",
    "последние",
    "последних",
    "последнюю",
    "по",
    "под",
    "почему",
    "про",
    "с",
    "сам",
    "сразу",
    "так",
    "там",
    "тогда",
    "только",
    "у",
    "уже",
    "что",
    "чтобы",
    "интересного",
    "это",
    "этого",
    "этим",
    "архива",
    "архиве",
    "делать",
    "моем",
    "моём",
}
_PROJECT_QUERY_HINTS = {
    "ai rollout training os": ("AI rollout training SOP guardrails",),
    "lead response sla agent": ("lead response SLA no answer",),
    "demand to mvp radar": ("MVP repeated questions competitor traction",),
    "workflow to agent studio": ("workflow automation SOP transcript",),
    "dream motif interpreter": ("dream motif pgvector retrieval",),
    "entropy protocol": ("trader risk audit rule violation",),
    "gdev agent": ("game support triage eval pipeline",),
    "telegram research agent": ("telegram research memory RAG", "personal research memory"),
}
_AI_TRANSFORMATION_BASE_VARIANTS = (
    "внедрение ИИ компании успешным",
    "AI transformation companies ROI productivity",
    "ИИ бизнес процессы финансовая выгода",
)
_AI_TRANSFORMATION_FAILURE_VARIANTS = (
    "1% компаний внедрение ИИ успешным",
    "AI complexity productivity неуспешно",
)
_AI_TRANSFORMATION_HIRING_VARIANTS = (
    "AI layoffs hiring companies",
    "ИИ увольнения найм компании",
)
_AI_MODEL_VARIANTS = (
    "AI models LLM",
    "LLM GPT Claude Gemini",
    "модели ИИ LLM",
)

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "один": 1,
    "одну": 1,
    "одна": 1,
    "два": 2,
    "две": 2,
    "пару": 2,
    "три": 3,
    "трех": 3,
    "трёх": 3,
    "четыре": 4,
    "четырех": 4,
    "четырёх": 4,
    "пять": 5,
    "пяти": 5,
    "шесть": 6,
    "шести": 6,
    "семь": 7,
    "семи": 7,
}
_RELATIVE_WINDOW_RE = re.compile(
    r"(?:за\s+)?(?:последн\w*|last|recent)\s+"
    r"(?P<count>\d+|one|two|three|four|five|six|seven|один|одну|одна|два|две|пару|три|трех|трёх|четыре|четырех|четырёх|пять|пяти|шесть|шести|семь|семи)?\s*"
    r"(?P<unit>дн(?:я|ей|ь)?|недел(?:я|ю|и|ь)?|месяц(?:а|ев|ы)?|days?|weeks?|months?)",
    re.IGNORECASE,
)
_TODAY_WINDOW_RE = re.compile(r"\b(today|сегодня)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ResearchTimeWindow:
    requested: bool = False
    strict: bool = False
    date_from: str = ""
    date_to: str = ""
    label: str = ""
    days: int = 0
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested": bool(self.requested),
            "strict": bool(self.strict),
            "date_from": self.date_from,
            "date_to": self.date_to,
            "label": self.label,
            "days": int(self.days or 0),
            "source": self.source,
        }


@dataclass(frozen=True)
class MemoryResearchBudget:
    max_tool_calls: int = 4
    max_archive_sources: int = 5
    max_archive_candidates: int = 16
    max_linked_sources: int = 3
    max_retries: int = 0
    timeout_seconds: int = 30
    max_prompt_chars: int = 8_000
    max_model_calls: int = 0
    max_cost_usd: float = 0.0
    allow_open_browsing: bool = False
    allow_provider_egress: bool = False
    allow_vector_retrieval: bool = False
    vector_index_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_tool_calls": int(self.max_tool_calls),
            "max_archive_sources": int(self.max_archive_sources),
            "max_archive_candidates": int(self.max_archive_candidates),
            "max_linked_sources": int(self.max_linked_sources),
            "max_retries": int(self.max_retries),
            "timeout_seconds": int(self.timeout_seconds),
            "max_prompt_chars": int(self.max_prompt_chars),
            "max_model_calls": int(self.max_model_calls),
            "max_cost_usd": round(float(self.max_cost_usd or 0.0), 8),
            "allow_open_browsing": bool(self.allow_open_browsing),
            "allow_provider_egress": bool(self.allow_provider_egress),
            "allow_vector_retrieval": bool(self.allow_vector_retrieval),
            "vector_index_path_configured": bool(self.vector_index_path),
        }


def answer_memory_research(
    question: str,
    *,
    archive_query: str | None = None,
    settings: Settings | None = None,
    facade: PersonalIntelligenceFacade | Any | None = None,
    week_label: str | None = None,
    project_name: str | None = None,
    limit: int = 5,
    budget: MemoryResearchBudget | None = None,
    linked_source_fetcher: LinkedSourceFetcher | FakeLinkedSourceFetcher | None = None,
    linked_source_fixtures: Mapping[str, Mapping[str, Any]] | None = None,
    project_context_fixtures: Sequence[Mapping[str, Any]] | None = None,
    operator_context: Mapping[str, Any] | None = None,
    research_intent: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    clean_question = _clean_text(question)
    active_budget = budget or MemoryResearchBudget()
    budget_refusal = _budget_refusal(clean_question, active_budget)
    if not clean_question:
        return _refusal_payload("", active_budget, "invalid_question", "Question is empty.")
    if budget_refusal:
        return _refusal_payload(clean_question, active_budget, budget_refusal[0], budget_refusal[1])

    clean_archive_query = _clean_text(archive_query) or clean_question
    time_window = _resolve_time_window(clean_question, now=now)
    bounded_limit = max(1, min(active_budget.max_archive_sources, int(limit or active_budget.max_archive_sources)))
    active_facade = facade or PersonalIntelligenceFacade(settings=settings)
    tool_calls: list[dict[str, Any]] = []

    archive_result = _call_archive_search(
        active_facade,
        clean_archive_query,
        week_label=week_label,
        project_name=project_name,
        limit=bounded_limit,
        candidate_limit=max(bounded_limit, min(_HARD_MAX_ARCHIVE_CANDIDATES, int(active_budget.max_archive_candidates or bounded_limit))),
        tool_calls=tool_calls,
        budget=active_budget,
        time_window=time_window,
    )
    gap_check = {"status": "not_requested", "missing_evidence": [], "query_variants": []}
    if str(research_intent or "") == "archive_to_action":
        gap_check = assess_research_gaps(
            [item for item in archive_result.get("items") or [] if isinstance(item, Mapping)],
            question=clean_question,
        )
        gap_variants = [str(item) for item in gap_check.get("query_variants") or [] if str(item).strip()]
        if gap_variants and len(tool_calls) < active_budget.max_tool_calls:
            gap_result = _call_archive_search(
                active_facade,
                clean_archive_query,
                week_label=week_label,
                project_name=project_name,
                limit=bounded_limit,
                candidate_limit=max(bounded_limit, min(_HARD_MAX_ARCHIVE_CANDIDATES, int(active_budget.max_archive_candidates or bounded_limit))),
                tool_calls=tool_calls,
                budget=active_budget,
                time_window=time_window,
                extra_query_variants=gap_variants,
            )
            archive_result = _merge_archive_results(archive_result, gap_result, query=clean_archive_query)
            gap_check = {
                **gap_check,
                "gap_search_performed": True,
                "post_search": assess_research_gaps(
                    [item for item in archive_result.get("items") or [] if isinstance(item, Mapping)],
                    question=clean_question,
                ),
            }
    curated_result = _call_curated_search(
        active_facade,
        clean_question,
        week_label=week_label,
        limit=bounded_limit,
        tool_calls=tool_calls,
        budget=active_budget,
        time_window=time_window,
    )
    saved_result = _call_saved_knowledge(active_facade, clean_question, project_name=project_name, limit=bounded_limit)
    curated_result = {
        **curated_result,
        "items": [*saved_result.get("items", []), *list(curated_result.get("items") or [])],
        "saved_memory_secondary": True,
    }
    project_context = _route_project_context(
        active_facade,
        clean_question,
        project_name=project_name,
        week_label=week_label,
        limit=bounded_limit,
        archive_result=archive_result,
        curated_result=curated_result,
        fixtures=project_context_fixtures,
        tool_calls=tool_calls,
        budget=active_budget,
    )
    linked_fetcher = linked_source_fetcher
    if linked_fetcher is None and linked_source_fixtures is not None:
        linked_fetcher = FakeLinkedSourceFetcher(linked_source_fixtures)
    linked_result = _call_linked_sources(
        archive_result,
        fetcher=linked_fetcher,
        tool_calls=tool_calls,
        budget=active_budget,
    )

    archive_evidence = _archive_evidence(archive_result, question=clean_question, max_items=bounded_limit, time_window=time_window)
    linked_evidence = _linked_evidence(linked_result, max_items=active_budget.max_linked_sources)
    curated_evidence = _curated_evidence(curated_result, max_items=bounded_limit)
    professional_lens = infer_professional_lens(clean_question)
    archive_evidence["items"] = rerank_for_professional_lens(archive_evidence["items"], lens_id=professional_lens)
    project_fit = _project_fit(project_context)
    context_pack = build_rag_context_pack(
        question=clean_question,
        archive_evidence=archive_evidence,
        curated_memory=curated_evidence,
        linked_source_evidence=linked_evidence,
        project_fit=project_fit,
        vector_backend_used=active_budget.allow_vector_retrieval,
        max_sources=active_budget.max_archive_sources + active_budget.max_linked_sources,
    )
    answer_gate = _mapping(context_pack.get("answer_gate"))
    comparison = _approach_comparison(archive_evidence, linked_evidence, curated_evidence)
    next_steps = _next_steps(project_fit, archive_evidence, linked_evidence, answer_gate)
    deeper_reading = _deeper_reading(linked_evidence, archive_evidence, curated_evidence)
    unknowns = _unknowns(archive_evidence, linked_evidence, project_fit, linked_result, time_window=time_window)
    unknowns = _unique([*unknowns, *_answer_gate_unknowns(answer_gate)])
    repo_project_context = _repo_project_context(clean_question, project_name=project_name)
    direct_answer = _direct_answer(
        question=clean_question,
        archive_evidence=archive_evidence,
        linked_evidence=linked_evidence,
        project_fit=project_fit,
        unknowns=unknowns,
        answer_gate=answer_gate,
        time_window=time_window,
    )
    source_refs = _unique(
        [
            *archive_evidence["source_refs"],
            *linked_evidence["source_refs"],
            *curated_evidence["source_refs"],
            *project_fit.get("source_refs", []),
            *_strings(repo_project_context.get("source_refs")),
        ]
    )
    drafts = (
        _draft_proposals(
            question=clean_question,
            direct_answer=direct_answer,
            project_fit=project_fit,
            source_refs=source_refs,
            unknowns=unknowns,
        )
        if _drafts_allowed(answer_gate)
        else []
    )
    status = _answer_status(answer_gate, archive_evidence=archive_evidence, linked_evidence=linked_evidence, curated_evidence=curated_evidence)
    receipt = _receipt(
        status=status,
        budget=active_budget,
        tool_calls=tool_calls,
        source_refs=source_refs,
        linked_result=linked_result,
        draft_count=len(drafts),
        answer_gate=answer_gate,
    )
    professional_workflows = {}
    if _is_ai_systems_question(clean_question):
        professional_workflows["ai_systems"] = build_ai_systems_project_application_workflow(
            {
                "archive_evidence": archive_evidence,
                "project_fit": project_fit,
                "answer_gate": answer_gate,
            }
        )
    if _is_writer_editor_question(clean_question):
        professional_workflows["writer_editor"] = build_writer_editor_brief_workflow(
            {
                "archive_evidence": archive_evidence,
                "answer_gate": answer_gate,
                "direct_answer": direct_answer,
                "next_steps": next_steps,
            }
        )
    if _is_enterprise_ai_adoption_question(clean_question):
        professional_workflows["enterprise_ai_adoption"] = build_enterprise_ai_adoption_workflow(
            {
                "archive_evidence": archive_evidence,
                "project_fit": project_fit,
            }
        )
    if _is_learning_question(clean_question):
        professional_workflows["learning_experiment"] = build_learning_experiment_workflow(
            {
                "archive_evidence": archive_evidence,
                "project_fit": project_fit,
                "concept": _learning_concept(clean_question),
            }
        )
    if _is_career_question(clean_question):
        professional_workflows["career_portfolio"] = build_career_portfolio_gap_workflow(
            {
                "archive_evidence": archive_evidence,
                "project_fit": project_fit,
                "answer_gate": answer_gate,
            }
        )
    selected_evidence_items = [
        *[item for item in archive_evidence.get("items") or [] if isinstance(item, Mapping)],
        *[item for item in linked_evidence.get("items") or [] if isinstance(item, Mapping)],
    ]
    evidence_quality_items = build_evidence_quality_items(
        selected_evidence_items,
        question=clean_question,
        project_name=str(project_fit.get("project_name") or ""),
    )
    evidence_quality = {
        "schema_version": "prm_evidence_quality_bundle.v1",
        "items": evidence_quality_items,
        "summary": evidence_quality_summary(evidence_quality_items),
    }
    current_fact_required = bool(answer_gate.get("external_verification_required")) and not bool(
        answer_gate.get("current_claim_allowed", True)
    )
    candidate_claim_ledger = build_claim_ledger(
        build_candidate_claims_from_evidence(evidence_quality_items),
        evidence_quality_items,
        current_fact_required=current_fact_required,
        project_name=str(project_fit.get("project_name") or ""),
    )
    claim_ledger = approve_claim_ledger(candidate_claim_ledger)
    project_decision = _project_decision_synthesis(
        question=clean_question,
        project_fit=project_fit,
        curated_evidence=curated_evidence,
        approved_claim_ledger=claim_ledger,
        next_steps=next_steps,
        unknowns=unknowns,
        answer_gate=answer_gate,
    )
    context = _mapping(operator_context)
    interaction_id = str(context.get("interaction_id") or f"local-{uuid4()}")
    primary_workflow = str(context.get("primary_workflow") or "archive_research")
    workflow_section_key = _professional_workflow_section_key(primary_workflow, professional_workflows)
    professional_answer = build_professional_answer(
        {
            "interaction_id": interaction_id,
            "direct_answer": direct_answer,
            "archive_evidence": archive_evidence,
            "project_fit": project_fit,
            "answer_gate": answer_gate,
            "professional_lens": {"selected": professional_lens or "neutral"},
            "next_steps": next_steps,
            "unknowns": unknowns,
            "workflow_section": professional_workflows.get(workflow_section_key, {}),
            "approved_claim_ledger": claim_ledger,
            "project_decision": project_decision,
        },
        workflow=primary_workflow,
    )
    answer_body = render_memory_research_answer_body(
        direct_answer=direct_answer,
        archive_evidence=archive_evidence,
        linked_evidence=linked_evidence,
        comparison=comparison,
        project_fit=project_fit,
        context_pack=context_pack,
        next_steps=next_steps,
        deeper_reading=deeper_reading,
        unknowns=unknowns,
        drafts=drafts,
    )
    final_answer_verification = verify_answer_against_evidence(
        answer_body,
        evidence_quality_items,
        current_fact_required=current_fact_required,
        project_name=str(project_fit.get("project_name") or ""),
    )
    receipt["retrieval_policy"] = _mapping(archive_result.get("retrieval_policy"))
    receipt["evidence_quality_summary"] = evidence_quality["summary"]
    receipt["claim_grounding"] = claim_ledger_public_summary(claim_ledger)
    receipt["final_answer_verification"] = {
        "claim_count": int(final_answer_verification.get("claim_count") or 0),
        "metrics": final_answer_verification.get("metrics") or {},
    }
    return {
        "schema_version": MEMORY_RESEARCH_SCHEMA_VERSION,
        "status": receipt["status"],
        "mode": "local_research_fixture",
        "question": clean_question,
        "time_window": time_window.to_dict(),
        "direct_answer": direct_answer,
        "archive_evidence": archive_evidence,
        "archive_candidate_pool": _archive_candidate_pool(archive_result),
        "research_gap_check": gap_check,
        "curated_memory": curated_evidence,
        "linked_source_evidence": linked_evidence,
        "approach_comparison": comparison,
        "project_fit": project_fit,
        "repo_project_context": repo_project_context,
        "context_pack": context_pack,
        "retrieval_policy": _mapping(archive_result.get("retrieval_policy")),
        "evidence_quality": evidence_quality,
        "candidate_claim_ledger": candidate_claim_ledger,
        "claim_ledger": claim_ledger,
        "project_decision": project_decision,
        "final_answer_verification": final_answer_verification,
        "answer_gate": answer_gate,
        "next_steps": next_steps,
        "deeper_reading_path": deeper_reading,
        "unknowns": unknowns,
        "professional_workflows": professional_workflows,
        "professional_answer": professional_answer,
        "interaction_id": interaction_id,
        "operator_context": dict(context),
        "professional_lens": {
            "selected": professional_lens or "neutral",
            "selection_source": "turn_local_inference" if professional_lens else "neutral",
            "recall_filtered": False,
        },
        "draft_proposals": drafts,
        "receipt": receipt,
        "privacy": receipt["privacy"],
        "answer": answer_body,
    }


def _professional_workflow_section_key(primary_workflow: str, sections: Mapping[str, object]) -> str:
    """Choose the one derived professional view allowed by the operator workflow.

    The reader DTO has one operator workflow, while the local research helpers
    may derive several domain-specific sections.  This selection remains
    deterministic and does not invent a section when no predicate matched.
    """

    preferences = {
        "archive_research": (
            "ai_systems",
            "enterprise_ai_adoption",
            "learning_experiment",
            "career_portfolio",
            "writer_editor",
        ),
        "writer_editor_brief": ("writer_editor",),
    }
    for key in preferences.get(primary_workflow, ()):
        if isinstance(sections.get(key), Mapping):
            return key
    return ""


def _is_ai_systems_question(question: str) -> bool:
    return _contains_any(
        question.casefold(),
        ("agent", "eval", "evaluation", "rag", "retrieval", "context engineering", "tool", "safety", "runtime"),
    )


def _is_writer_editor_question(question: str) -> bool:
    return _contains_any(
        question.casefold(),
        ("brief", "editor", "writer", "article", "post", "статья", "пост", "бриф", "редактор"),
    )


def _is_enterprise_ai_adoption_question(question: str) -> bool:
    return _contains_any(
        question.casefold(),
        ("enterprise", "adoption", "buyer", "product", "компани", "внедрен", "покупател", "продукт"),
    )


def _is_learning_question(question: str) -> bool:
    return _contains_any(
        question.casefold(),
        ("learn", "explain", "experiment", "объясни", "изучи", "эксперимент", "контекст-инжинир"),
    )


def _is_career_question(question: str) -> bool:
    return _contains_any(
        question.casefold(),
        ("career", "portfolio", "job", "vacancy", "карьер", "портфолио", "ваканси"),
    )


def _learning_concept(question: str) -> str:
    lowered = question.casefold()
    if "rag" in lowered or "retrieval" in lowered:
        return "retrieval"
    if "eval" in lowered or "оцен" in lowered:
        return "evaluation"
    return "контекст-инжиниринг"


def render_memory_research_answer(payload: Mapping[str, Any], *, debug: bool = False) -> str:
    if payload.get("status") == "invalid":
        return str(payload.get("message") or "Question is empty.")
    if payload.get("status") == "refused":
        receipt = _mapping(payload.get("receipt"))
        privacy = _mapping(receipt.get("privacy"))
        question = str(payload.get("question") or "")
        if _is_russian(question):
            return "\n".join(
                [
                    "PRM Research",
                    f"Вопрос: {question}",
                    "Статус: отказано",
                    str(payload.get("message") or "Research request refused by policy."),
                    _privacy_line(privacy),
                ]
            ).rstrip()
        return "\n".join(
            [
                "PRM Research",
                f"Question: {payload.get('question') or ''}",
                "Status: refused",
                str(payload.get("message") or "Research request refused by policy."),
                _privacy_line(privacy),
            ]
        ).rstrip()

    if not debug:
        return _render_memory_research_compact(payload)

    body = str(payload.get("answer") or "").strip()
    privacy = _mapping(payload.get("privacy"))
    receipt = _mapping(payload.get("receipt"))
    budget = _mapping(receipt.get("budget"))
    lines = [
        "PRM Research",
        f"Question: {payload.get('question') or ''}",
        "Mode: local-research; no LLM, no live web, no writes.",
        "",
        body or "No local evidence matched. I will not guess beyond available data.",
        "",
        (
            "Planner limits: "
            f"tool_calls={receipt.get('tool_calls_used', 0)}/{budget.get('max_tool_calls', 0)}; "
            f"archive_sources<={budget.get('max_archive_sources', 0)}; "
            f"linked_sources<={budget.get('max_linked_sources', 0)}; "
            f"retries<={budget.get('max_retries', 0)}; "
            f"timeout_seconds<={budget.get('timeout_seconds', 0)}"
        ),
        _privacy_line(privacy),
    ]
    return "\n".join(lines).rstrip()


def render_memory_research_brief(payload: Mapping[str, Any]) -> str:
    """Render a compact local-only source brief for editor/social-post drafting."""
    if payload.get("status") in {"invalid", "refused"}:
        return render_memory_research_answer(payload)
    question = str(payload.get("question") or "")
    ru = _is_russian(question)
    privacy = _mapping(payload.get("privacy"))
    receipt = _mapping(payload.get("receipt"))
    budget = _mapping(receipt.get("budget"))
    archive_evidence = _mapping(payload.get("archive_evidence"))
    linked_evidence = _mapping(payload.get("linked_source_evidence"))
    unknowns = [str(item) for item in payload.get("unknowns") or [] if str(item).strip()]
    archive_items = [item for item in archive_evidence.get("items") or [] if isinstance(item, Mapping)]
    linked_items = [item for item in linked_evidence.get("items") or [] if isinstance(item, Mapping)]
    has_source_evidence = bool(archive_items or linked_items)
    title = "PRM Editor Brief" if not ru else "PRM редакторский бриф"
    lines = [
        title,
        f"{'Вопрос' if ru else 'Question'}: {question}",
        (
            "Режим: local-only source brief; без LLM, live web и записей."
            if ru
            else "Mode: local-only source brief; no LLM, no live web, no writes."
        ),
    ]
    dialog_context = _mapping(payload.get("dialog_context"))
    if dialog_context.get("used"):
        previous = _short(dialog_context.get("previous_question"), 180)
        if previous:
            previous_label = "предыдущий вопрос" if ru else "previous"
            lines.extend(["", "Контекст диалога" if ru else "Dialog context", f"- {previous_label}: {previous}"])

    lines.extend(["", "Позиция" if ru else "Position"])
    lines.append(_compact_answer(payload, ru=ru))

    lines.extend(["", "Опорные тезисы" if ru else "Source-backed points"])
    if archive_items:
        for index, item in enumerate(archive_items[:5], start=1):
            date = str(item.get("posted_at") or "")[:10] or ("дата неизвестна" if ru else "date unknown")
            channel = item.get("channel_username") or ("источник" if ru else "source")
            snippet = _short(item.get("snippet") or item.get("content") or "", 180)
            lines.append(f"{index}. {date} {channel}: {snippet}")
    else:
        lines.append("- локальных источников нет; не превращай это в тезис без нового запроса." if ru else "- no local sources; do not turn this into a thesis without another query.")

    if not has_source_evidence:
        lines.extend(
            [
                "",
                "Как продолжим" if ru else "How to continue",
                (
                    "- Сформулируй тему шире или другими словами — я ещё раз проверю архив."
                    if ru
                    else "- Rephrase or broaden the topic and I will check the archive again."
                ),
                (
                    "- Пришли ссылку или материал, если хочешь собрать бриф именно по нему."
                    if ru
                    else "- Send a link or source material if you want a brief about it."
                ),
            ]
        )

    angle_lines = _brief_angle_lines(payload, ru=ru)
    if angle_lines:
        lines.extend(["", "Углы для поста" if ru else "Editorial angles", *angle_lines])

    source_lines = _compact_source_lines(archive_evidence, linked_evidence, ru=ru, max_items=5)
    if source_lines:
        lines.extend(["", "Ссылки" if ru else "Links", *source_lines])

    if unknowns:
        lines.extend(["", "Ограничения" if ru else "Limits"])
        lines.extend(f"- {_short(_localize_unknown(item) if ru else item, 140)}" for item in unknowns[:5])

    lines.extend(
        [
            "",
            (
                f"{'Лимиты' if ru else 'Limits'}: "
                f"tool_calls={receipt.get('tool_calls_used', 0)}/{budget.get('max_tool_calls', 0)}; "
                f"sources<={budget.get('max_archive_sources', 0)}"
            ),
            _privacy_line(privacy),
        ]
    )
    return "\n".join(line.rstrip() for line in lines if line is not None).rstrip()


def _render_memory_research_compact(payload: Mapping[str, Any]) -> str:
    question = str(payload.get("question") or "")
    ru = _is_russian(question)
    labels = _compact_labels(ru)
    privacy = _mapping(payload.get("privacy"))
    receipt = _mapping(payload.get("receipt"))
    budget = _mapping(receipt.get("budget"))
    answer_gate = _mapping(payload.get("answer_gate"))
    archive_evidence = _mapping(payload.get("archive_evidence"))
    linked_evidence = _mapping(payload.get("linked_source_evidence"))
    project_fit = _mapping(payload.get("project_fit"))
    repo_context = _mapping(payload.get("repo_project_context"))
    dialog_context = _mapping(payload.get("dialog_context"))
    next_steps = _mapping(payload.get("next_steps"))
    unknowns = [str(item) for item in payload.get("unknowns") or [] if str(item).strip()]
    drafts = [item for item in payload.get("draft_proposals") or [] if isinstance(item, Mapping)]

    lines = [
        "PRM Research",
        f"{labels['question']}: {question}",
        labels["mode"],
        "",
        labels["answer"],
        _compact_answer(payload, ru=ru),
    ]

    if dialog_context.get("used"):
        previous = _short(dialog_context.get("previous_question"), 180)
        if previous:
            lines.extend(["", labels["dialog_context"], f"- {labels['dialog_previous']}: {previous}"])

    if repo_context.get("status") == "matched":
        lines.extend(["", labels["repo_context"]])
        summary = repo_context.get("summary_ru") if ru else repo_context.get("summary")
        lines.append(_short(str(summary or repo_context.get("summary") or ""), 260))
        refs = _strings(repo_context.get("source_refs"))
        if refs:
            lines.append(f"{labels['repo_refs']}: " + ", ".join(refs[:4]))

    source_lines = _compact_source_lines(archive_evidence, linked_evidence, ru=ru, max_items=3)
    if source_lines:
        lines.extend(["", labels["sources"], *source_lines])

    action_lines = _compact_action_lines(next_steps, ru=ru)
    if action_lines:
        lines.extend(["", labels["next"], *action_lines])

    if unknowns:
        lines.extend(["", labels["unknowns"]])
        lines.extend(f"- {_short(_localize_unknown(item) if ru else item, 140)}" for item in unknowns[:5])

    if drafts:
        lines.extend(["", labels["drafts"]])
        lines.append(
            labels["draft_summary"].format(
                count=len(drafts),
                persisted=str(any(bool(item.get("persisted")) for item in drafts)).lower(),
            )
        )

    lines.extend(
        [
            "",
            (
                f"{labels['limits']}: "
                f"tool_calls={receipt.get('tool_calls_used', 0)}/{budget.get('max_tool_calls', 0)}; "
                f"sources<={budget.get('max_archive_sources', 0)}; "
                f"debug={'false'}"
            ),
            labels["debug_hint"],
            _privacy_line(privacy),
        ]
    )
    return "\n".join(line.rstrip() for line in lines if line is not None).rstrip()


def _brief_angle_lines(payload: Mapping[str, Any], *, ru: bool) -> list[str]:
    question = str(payload.get("question") or "")
    dialog_context = _mapping(payload.get("dialog_context"))
    intent_question = str(dialog_context.get("effective_question") or question)
    archive_evidence = _mapping(payload.get("archive_evidence"))
    archive_items = [item for item in archive_evidence.get("items") or [] if isinstance(item, Mapping)]
    haystack = _clean_text(
        " ".join(str(item.get("snippet") or item.get("content") or "") for item in archive_items)
    ).casefold()
    if not _is_ai_transformation_question(intent_question.casefold()):
        return []
    asks_hiring = _contains_any(intent_question.casefold(), ("увольн", "наним", "hiring", "layoff", "layoffs", "jobs", "найм"))
    lines: list[str] = []
    if ru:
        lines.append("- пилоты vs результат: отделить факт внедрения AI от доказанного прироста/ROI")
        if _contains_any(haystack, ("1%", "неуспеш", "пилот", "сложность")):
            lines.append("- почему не получилось: сложность процессов и разрыв между демо/пилотом и операционным эффектом")
        if _contains_any(haystack, ("эффект", "финансов", "выгод", "успеш")):
            lines.append("- где есть прирост: искать конкретный процесс, метрику и контекст рынка, а не общий AI-лейбл")
        if asks_hiring:
            lines.append("- найм/увольнения: не писать как текущий список компаний без отдельной внешней проверки")
        return lines
    lines.append("- pilots vs results: separate AI adoption from proven ROI/productivity")
    if _contains_any(haystack, ("1%", "unsuccess", "pilot", "complexity")):
        lines.append("- why it fails: process complexity and the gap between demo/pilot and operating effect")
    if _contains_any(haystack, ("effect", "financial", "benefit", "successful")):
        lines.append("- where growth exists: look for a concrete process, metric, and market context")
    if asks_hiring:
        lines.append("- hiring/layoffs: do not present a current company list without separate verification")
    return lines


def _compact_labels(ru: bool) -> dict[str, str]:
    if ru:
        return {
            "question": "Вопрос",
            "mode": "Режим: local-research; без LLM, live web и записей.",
            "answer": "Короткий ответ",
            "dialog_context": "Контекст диалога",
            "dialog_previous": "предыдущий вопрос",
            "repo_context": "Контекст проекта",
            "repo_refs": "Опорные документы",
            "sources": "Источники",
            "next": "Что делать дальше",
            "unknowns": "Ограничения",
            "drafts": "Черновики",
            "draft_summary": "- подготовлено черновиков: {count}; сохранено={persisted}; запись только через подтверждение",
            "limits": "Лимиты",
            "debug_hint": "Подробности: добавь --debug, чтобы увидеть context pack, approach comparison и draft details.",
        }
    return {
        "question": "Question",
        "mode": "Mode: local-research; no LLM, no live web, no writes.",
        "answer": "Short answer",
        "dialog_context": "Dialog context",
        "dialog_previous": "previous question",
        "repo_context": "Project context",
        "repo_refs": "Evidence docs",
        "sources": "Sources",
        "next": "Next steps",
        "unknowns": "Limits / unknowns",
        "drafts": "Drafts",
        "draft_summary": "- draft proposals: {count}; persisted={persisted}; writes require confirmation",
        "limits": "Limits",
        "debug_hint": "Details: add --debug to show context pack, approach comparison, and draft details.",
    }


def _compact_answer(payload: Mapping[str, Any], *, ru: bool) -> str:
    question = str(payload.get("question") or "")
    dialog_context = _mapping(payload.get("dialog_context"))
    intent_question = str(dialog_context.get("effective_question") or question)
    answer_gate = _mapping(payload.get("answer_gate"))
    archive_evidence = _mapping(payload.get("archive_evidence"))
    linked_evidence = _mapping(payload.get("linked_source_evidence"))
    project_fit = _mapping(payload.get("project_fit"))
    repo_context = _mapping(payload.get("repo_project_context"))
    time_window = _mapping(payload.get("time_window"))
    archive_items = [item for item in archive_evidence.get("items") or [] if isinstance(item, Mapping)]
    linked_items = [item for item in linked_evidence.get("items") or [] if isinstance(item, Mapping)]
    source_count = len(archive_items) + len(linked_items)
    project_label = str(project_fit.get("relevance_label") or "no_match")
    gate_reason = str(answer_gate.get("reason") or "")
    if gate_reason == "current_external_fact_required" or _is_current_external_fact_question(intent_question):
        return (
            "Сначала ограничение: текущий факт нельзя подтвердить локально. Архив ниже — только контекст; внешняя проверка не запускалась."
            if ru
            else "First constraint: this current fact cannot be verified locally. Archive evidence below is context only; no external verification was run."
        )
    if _time_window_requested(time_window) and not source_count:
        label = _time_window_label(time_window, ru=ru)
        return (
            f"В локальном архиве за {label} не нашёл релевантных постов. Старые похожие посты не использую как ответ на свежий вопрос; live web не запускался."
            if ru
            else f"No relevant retained posts were found for {label}. Older related posts were not used as evidence for this freshness-scoped question; no live web verification was run."
        )
    if (
        bool(answer_gate.get("external_verification_required"))
        and not bool(answer_gate.get("current_claim_allowed", True))
        and not bool(answer_gate.get("allow_answer", True))
    ):
        return (
            "Сначала ограничение: текущий факт нельзя подтвердить локально. Архив ниже — только контекст; внешняя проверка не запускалась."
            if ru
            else "First constraint: this current fact cannot be verified locally. Archive evidence below is context only; no external verification was run."
        )
    if not bool(answer_gate.get("allow_answer", True)):
        return (
            "Недостаточно локальных цитируемых доказательств. Я не буду превращать похожие посты в утверждение."
            if ru
            else "Insufficient cited local evidence. I will not turn related posts into a claim."
        )
    if repo_context.get("status") == "matched":
        return (
            "Это вопрос о самом проекте. Сначала смотри документы репозитория и gate receipts; Telegram-архив ниже — только фон."
            if ru
            else "This is a question about the repository itself. Use repo/gate evidence first; Telegram archive evidence below is background."
        )
    if _is_ai_transformation_question(intent_question.casefold()) and source_count:
        return _ai_transformation_compact_answer(
            question=intent_question,
            archive_items=archive_items,
            linked_items=linked_items,
            source_count=source_count,
            project_label=project_label,
            ru=ru,
        )
    if source_count:
        first = archive_items[0] if archive_items else linked_items[0]
        snippet = _short(first.get("snippet") or first.get("content") or first.get("text_excerpt") or "", 150)
        window_prefix_ru = f"за {_time_window_label(time_window, ru=True)} " if _time_window_requested(time_window) else ""
        window_prefix_en = f"for {_time_window_label(time_window, ru=False)} " if _time_window_requested(time_window) else ""
        if ru:
            return (
                f"Нашёл {window_prefix_ru}локальные источники: {source_count}. Главный первый сигнал: {snippet} "
                f"Маршрут проекта: {_localized_project_label(project_label)}."
            )
        return f"Found {source_count} local source(s) {window_prefix_en}. First strong signal: {snippet} Project routing: {project_label}."
    return (
        "Локальных источников не найдено. Я не буду додумывать ответ."
        if ru
        else "No local sources matched. I will not guess beyond available data."
    )


def _ai_transformation_compact_answer(
    *,
    question: str,
    archive_items: Sequence[Mapping[str, Any]],
    linked_items: Sequence[Mapping[str, Any]],
    source_count: int,
    project_label: str,
    ru: bool,
) -> str:
    haystack = _clean_text(
        " ".join(
            str(item.get("snippet") or item.get("content") or item.get("text_excerpt") or "")
            for item in [*archive_items, *linked_items]
        )
    ).casefold()
    asks_hiring = _contains_any(question.casefold(), ("увольн", "наним", "hiring", "layoff", "layoffs", "jobs", "найм"))
    failure_signal = _contains_any(
        haystack,
        ("1%", "неуспеш", "сложность", "пилот", "не дала", "нет прироста", "roi", "productivity"),
    )
    effect_signal = _contains_any(haystack, ("успеш", "эффект", "финансов", "выгод", "бизнес-процесс", "productivity"))
    hiring_signal = _contains_any(haystack, ("увольн", "наним", "hiring", "layoff", "jobs", "рабоч"))
    if ru:
        parts = [f"По локальному архиву найдено {source_count} источн."]
        if failure_signal:
            parts.append("Сильный угол: разрыв между AI-пилотами и реальным масштабируемым успехом.")
        if effect_signal:
            parts.append("Отдельно есть линия про эффект/финансовую выгоду, но её нужно отделять от хайпа внедрения.")
        if asks_hiring and not hiring_signal:
            parts.append("Про найм/увольнения локальная поддержка слабая: нужен отдельный запрос или внешняя проверка.")
        elif hiring_signal:
            parts.append("Есть локальные сигналы про рынок труда, но это архивный контекст, не текущий список компаний.")
        parts.append(f"Маршрут проекта: {_localized_project_label(project_label)}.")
        return " ".join(parts)
    parts = [f"Found {source_count} local source(s)."]
    if failure_signal:
        parts.append("Strong angle: the gap between AI pilots and scalable business success.")
    if effect_signal:
        parts.append("There are effect/financial-benefit signals, but separate them from adoption hype.")
    if asks_hiring and not hiring_signal:
        parts.append("Hiring/layoff support is weak locally; use a sharper query or approved external verification.")
    elif hiring_signal:
        parts.append("Labor-market signals are archive context, not a current company list.")
    parts.append(f"Project routing: {project_label}.")
    return " ".join(parts)


def _compact_source_lines(
    archive_evidence: Mapping[str, Any],
    linked_evidence: Mapping[str, Any],
    *,
    ru: bool,
    max_items: int,
) -> list[str]:
    lines: list[str] = []
    archive_items = [item for item in archive_evidence.get("items") or [] if isinstance(item, Mapping)]
    linked_items = [item for item in linked_evidence.get("items") or [] if isinstance(item, Mapping)]
    for item in archive_items[:max_items]:
        date = str(item.get("posted_at") or "")[:10] or ("дата неизвестна" if ru else "date unknown")
        channel = item.get("channel_username") or ("источник" if ru else "source")
        snippet = _short(item.get("snippet") or item.get("content") or "", 120)
        lines.append(f"- {date} {channel}: {snippet}")
        if item.get("source_url"):
            lines.append(f"  ↳ {item['source_url']}")
    remaining = max_items - len(archive_items[:max_items])
    if remaining > 0:
        for item in linked_items[:remaining]:
            title = item.get("normalized_title") or item.get("source_type") or ("linked source" if not ru else "связанный источник")
            url = item.get("source_url") or item.get("normalized_url") or ""
            lines.append(f"- {title}: {url}")
    if not lines:
        lines.append("- локальных источников нет" if ru else "- no local sources")
    return lines


def _compact_action_lines(next_steps: Mapping[str, Any], *, ru: bool) -> list[str]:
    names = (
        (("apply", "применить"), ("watch", "наблюдать"), ("study", "изучить"), ("ignore", "игнорировать"))
        if ru
        else (("apply", "apply"), ("watch", "watch"), ("study", "study"), ("ignore", "ignore"))
    )
    lines: list[str] = []
    for key, label in names:
        values = [str(item) for item in next_steps.get(key) or [] if str(item).strip()]
        if values:
            value = _localize_next_step(values[0]) if ru else values[0]
            lines.append(f"- {label}: {_short(value, 170)}")
    return lines


def _localized_project_label(label: str) -> str:
    return {
        "direct_implication": "прямое применение",
        "weak_watch": "наблюдать",
        "learning_relevance": "фон для изучения",
        "no_match": "нет привязки",
        "ambiguous_project": "нужно выбрать проект",
    }.get(label, label or "нет привязки")


def _localize_next_step(value: str) -> str:
    translations = {
        "Fetch or approve linked-source reading later if live freshness matters.": (
            "если нужна актуальность, отдельно разрешить linked-source/live-проверку."
        ),
        "Do not apply this to active project work from the current evidence.": (
            "не применять к активному проекту из текущих доказательств."
        ),
        "Read the linked source or archive thread as background before creating a project action.": (
            "Читать как фон; не превращать в проектное действие без проверки и подтверждения."
        ),
        "Draft one bounded project action from the cited evidence; require confirmation before saving.": (
            "Сформулировать одно ограниченное действие из цитируемых источников; сохранить только после подтверждения."
        ),
        "Run an explicitly approved external verification step before making current claims.": (
            "Перед текущими утверждениями отдельно разрешить внешнюю проверку."
        ),
        "Do not answer or save a memory from related-but-insufficient evidence.": (
            "Не отвечать и не сохранять память из похожих, но недостаточных доказательств."
        ),
        "Resolve the target project before applying the research.": "Сначала выбрать целевой проект.",
        "Keep this as a watch signal until repeated archive or linked-source evidence appears.": (
            "оставить как watch-сигнал до повторных архивных или linked-source доказательств."
        ),
        "Add a sharper archive query or approved gold retrieval label.": (
            "сформулировать более точный архивный запрос или добавить approved retrieval label."
        ),
    }
    return translations.get(value, value)


def _localize_unknown(value: str) -> str:
    translations = {
        "approved linked-source text": "утверждённый текст связанных источников",
        "live external freshness": "живая внешняя проверка актуальности",
        "matching project descriptor": "подходящее описание проекта",
        "external verification before current claims": "внешняя проверка перед текущими утверждениями",
        "current-claim freshness": "актуальность текущего утверждения",
        "direct project implication": "прямое влияние на проект",
        "fresh local Telegram archive support for requested time window": (
            "релевантные свежие посты в заданном окне локального Telegram-архива"
        ),
        "local Telegram archive support": "поддержка в локальном Telegram-архиве",
        "sufficient cited proof for the requested claim": "достаточное цитируемое доказательство для запрошенного утверждения",
        "active project context": "контекст активного проекта",
        "target project selection": "выбор целевого проекта",
    }
    return translations.get(value, value)


def render_memory_research_answer_body(
    *,
    direct_answer: str,
    archive_evidence: Mapping[str, Any],
    linked_evidence: Mapping[str, Any],
    comparison: Sequence[Mapping[str, Any]],
    project_fit: Mapping[str, Any],
    context_pack: Mapping[str, Any],
    next_steps: Mapping[str, Sequence[str]],
    deeper_reading: Sequence[Mapping[str, Any]],
    unknowns: Sequence[str],
    drafts: Sequence[Mapping[str, Any]],
) -> str:
    lines = ["Direct Answer", direct_answer]
    lines.extend(["", "Telegram Archive Evidence"])
    archive_items = [item for item in archive_evidence.get("items") or [] if isinstance(item, Mapping)]
    if archive_items:
        for item in archive_items[:5]:
            lines.append(
                "- {date} {channel}: {snippet}".format(
                    date=str(item.get("posted_at") or "")[:10] or "date unknown",
                    channel=item.get("channel_username") or "source",
                    snippet=_short(item.get("snippet") or item.get("content") or "", 220),
                )
            )
            if item.get("source_url"):
                lines.append(f"  source: {item['source_url']}")
    else:
        lines.append("- insufficient evidence")

    lines.extend(["", "Linked Source Evidence"])
    linked_items = [item for item in linked_evidence.get("items") or [] if isinstance(item, Mapping)]
    if linked_items:
        for item in linked_items[:5]:
            title = item.get("normalized_title") or item.get("source_type") or "linked source"
            lines.append(
                f"- {title}: {item.get('source_url') or item.get('normalized_url')}"
            )
            if item.get("text_excerpt"):
                lines.append(f"  adds: {_short(item['text_excerpt'], 220)}")
            elif item.get("extraction_status"):
                lines.append(f"  status: {item['extraction_status']}")
    else:
        lines.append("- no approved linked-source text available")

    lines.extend(["", "Approach Comparison"])
    for item in comparison[:4]:
        lines.append(
            "- {approach}: {summary} Tradeoff: {tradeoff}".format(
                approach=item.get("approach") or "approach",
                summary=_short(item.get("summary"), 180),
                tradeoff=_short(item.get("tradeoff"), 180),
            )
        )
        contradictions = item.get("contradictions")
        if contradictions:
            lines.append(f"  contradictions: {_short('; '.join(str(x) for x in contradictions), 180)}")

    lines.extend(["", "Project Fit"])
    lines.append(
        "{project}: {label}; confidence={confidence}".format(
            project=project_fit.get("project_name") or "project unknown",
            label=project_fit.get("relevance_label") or "no_match",
            confidence=project_fit.get("confidence") or "low",
        )
    )
    if project_fit.get("guidance"):
        lines.append(f"Guidance: {_short(project_fit['guidance'], 260)}")

    lines.extend(["", render_rag_context_pack(context_pack)])

    lines.extend(["", "Apply / Watch / Ignore / Study Next"])
    for key in ("apply", "watch", "ignore", "study"):
        values = [str(item) for item in next_steps.get(key) or [] if str(item).strip()]
        lines.append(f"{key}: " + ("; ".join(values[:3]) if values else "none"))

    lines.extend(["", "Deeper Reading"])
    if deeper_reading:
        for item in deeper_reading[:6]:
            lines.append(f"- {item.get('title') or item.get('kind')}: {item.get('url') or item.get('ref')}")
    else:
        lines.append("- none from approved local evidence")

    lines.extend(["", "Unknowns"])
    if unknowns:
        lines.extend(f"- {_short(item, 220)}" for item in unknowns[:8])
    else:
        lines.append("- none")

    lines.extend(["", "Draft Proposals"])
    if drafts:
        for draft in drafts[:4]:
            confirmation = _mapping(draft.get("confirmation"))
            lines.append(
                "- {proposal_type}: {title}; persisted={persisted}; confirmation_required={required}".format(
                    proposal_type=draft.get("proposal_type") or "proposal",
                    title=_mapping(draft.get("proposal")).get("title") or "untitled",
                    persisted=str(bool(draft.get("persisted"))).lower(),
                    required=str(bool(confirmation.get("required"))).lower(),
                )
            )
    else:
        lines.append("- none")
    return "\n".join(lines).rstrip()


def _resolve_time_window(question: str, *, now: datetime | None = None) -> ResearchTimeWindow:
    clean = _clean_text(question)
    lowered = clean.casefold()
    now_dt = _coerce_now(now)
    today = now_dt.date()

    relative = _RELATIVE_WINDOW_RE.search(lowered)
    if relative:
        raw_count = relative.group("count")
        unit = str(relative.group("unit") or "").casefold()
        count = _window_count(raw_count)
        if not raw_count and unit in {"месяцы", "months"}:
            count = 3
        days = _window_days(count=count, unit=unit)
        return _time_window_from_dates(
            date_from=today - timedelta(days=days),
            date_to_exclusive=today + timedelta(days=1),
            days=days,
            source=_clean_text(relative.group(0)),
        )

    if _TODAY_WINDOW_RE.search(lowered):
        return _time_window_from_dates(
            date_from=today,
            date_to_exclusive=today + timedelta(days=1),
            days=1,
            source="today",
        )

    return ResearchTimeWindow()


def _coerce_now(now: datetime | None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _window_count(value: str | None) -> int:
    clean = str(value or "").strip().casefold()
    if not clean:
        return 1
    if clean.isdigit():
        return max(1, min(24, int(clean)))
    return max(1, min(24, int(_NUMBER_WORDS.get(clean, 1))))


def _window_days(*, count: int, unit: str) -> int:
    if unit.startswith("д") or unit.startswith("day"):
        return max(1, count)
    if unit.startswith("нед") or unit.startswith("week"):
        return max(1, count * 7)
    if unit.startswith("мес") or unit.startswith("month"):
        return max(1, count * 30)
    return max(1, count)


def _time_window_from_dates(
    *,
    date_from: date,
    date_to_exclusive: date,
    days: int,
    source: str,
) -> ResearchTimeWindow:
    inclusive_to = date_to_exclusive - timedelta(days=1)
    label = f"{date_from.isoformat()}–{inclusive_to.isoformat()}"
    return ResearchTimeWindow(
        requested=True,
        strict=True,
        date_from=f"{date_from.isoformat()}T00:00:00Z",
        date_to=f"{date_to_exclusive.isoformat()}T00:00:00Z",
        label=label,
        days=max(1, int(days or 1)),
        source=source,
    )


def _archive_item_matches_time_window(item: Mapping[str, Any], time_window: ResearchTimeWindow) -> bool:
    if not time_window.requested or not time_window.strict:
        return True
    posted_at = _parse_archive_datetime(item.get("posted_at"))
    date_from = _parse_archive_datetime(time_window.date_from)
    date_to = _parse_archive_datetime(time_window.date_to)
    if posted_at is None or date_from is None or date_to is None:
        return False
    return date_from <= posted_at < date_to


def _is_current_external_fact_question(question: str) -> bool:
    lowered = _clean_text(question).casefold()
    if _contains_any(lowered, ("точные текущие цены", "текущая цена", "current prices", "current price", "pricing today")):
        return True
    if _contains_any(lowered, ("сегодня", "today")) and _contains_any(
        lowered,
        ("цены", "цена", "стоим", "акций", "акции", "price", "pricing", "stock", "buy", "купить"),
    ):
        return True
    return False


def _parse_archive_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(text[:10])
        except ValueError:
            return None
        parsed = datetime.combine(parsed_date, datetime.min.time(), tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _time_window_requested(time_window: Mapping[str, Any] | ResearchTimeWindow) -> bool:
    if isinstance(time_window, ResearchTimeWindow):
        return bool(time_window.requested)
    return bool(time_window.get("requested"))


def _time_window_label(time_window: Mapping[str, Any] | ResearchTimeWindow, *, ru: bool) -> str:
    if isinstance(time_window, ResearchTimeWindow):
        label = time_window.label
        days = time_window.days
    else:
        label = str(time_window.get("label") or "")
        days = int(time_window.get("days") or 0)
    if label:
        return label
    if days:
        return f"последние {days} дн." if ru else f"last {days} day(s)"
    return "заданный период" if ru else "the requested period"


def _call_archive_search(
    facade: Any,
    query: str,
    *,
    week_label: str | None,
    project_name: str | None,
    limit: int,
    candidate_limit: int,
    tool_calls: list[dict[str, Any]],
    budget: MemoryResearchBudget,
    time_window: ResearchTimeWindow,
    extra_query_variants: Sequence[str] = (),
) -> dict[str, Any]:
    if len(tool_calls) >= budget.max_tool_calls or not hasattr(facade, "search_telegram_archive"):
        return {"status": "skipped", "query": query, "items": [], "message": "Archive search skipped by planner limit."}
    filters: dict[str, Any] = {}
    if week_label:
        filters["week_label"] = week_label
    if time_window.requested and time_window.strict:
        filters["date_from"] = time_window.date_from
        filters["date_to"] = time_window.date_to
    retrieval_policy = select_retrieval_policy(
        query,
        project_name=str(project_name or ""),
        requested_mode="research",
    )
    if budget.allow_vector_retrieval:
        filters["retrieval_mode"] = "hybrid"
        filters["vector_policy"] = retrieval_policy.vector_policy
        if budget.vector_index_path:
            filters["vector_index_path"] = budget.vector_index_path
    legacy_variants = _archive_query_variants(query, project_name=project_name, max_variants=_MAX_ARCHIVE_QUERY_VARIANTS)
    policy_variants = build_query_rewrites(
        query,
        job_type=retrieval_policy.job_type,
        max_variants=_MAX_ARCHIVE_QUERY_VARIANTS,
    )
    query_variants = _unique([*extra_query_variants, *policy_variants, *legacy_variants])[:_MAX_ARCHIVE_QUERY_VARIANTS]
    logged_filters = {key: value for key, value in filters.items() if key != "vector_index_path"}
    if "vector_index_path" in filters:
        logged_filters["vector_index_path_configured"] = True
    tool_calls.append(
        {
            "name": "search_telegram_archive",
            "arguments": {
                "query": query,
                "query_variants": query_variants,
                "filters": logged_filters,
                "project_name_hint": project_name,
                "retrieval_policy": retrieval_policy.to_dict(),
                "limit": limit,
                "candidate_limit": candidate_limit,
                "time_window": time_window.to_dict(),
            },
        }
    )

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    attempts: list[dict[str, Any]] = []
    failures: list[str] = []
    per_variant_limit = max(1, min(16, (candidate_limit + max(1, len(query_variants)) - 1) // max(1, len(query_variants))))
    for variant in query_variants:
        remaining = max(0, int(candidate_limit or 0) - len(items))
        if remaining <= 0:
            break
        try:
            result = dict(facade.search_telegram_archive(variant, filters=filters, limit=min(remaining, per_variant_limit)))
        except Exception as exc:
            attempts.append({"query": variant, "status": "invalid", "item_count": 0})
            failures.append(type(exc).__name__)
            continue
        result_items = [dict(item) for item in result.get("items") or [] if isinstance(item, Mapping)]
        query_matched_items = [
            item for item in result_items if _archive_item_matches_query_variant(item, variant)
        ]
        accepted_items = [item for item in query_matched_items if _archive_item_matches_time_window(item, time_window)]
        attempts.append(
            {
                "query": variant,
                "status": str(result.get("status") or ("ok" if result_items else "insufficient_evidence")),
                "item_count": len(result_items),
                "accepted_count": len(accepted_items),
                "rejected_by_time_window": max(0, len(query_matched_items) - len(accepted_items)),
            }
        )
        for item in accepted_items:
            key = _archive_item_identity(item)
            if key in seen:
                continue
            seen.add(key)
            item.setdefault("matched_query_variant", variant)
            items.append(item)
            if len(items) >= candidate_limit:
                break

    items = rank_archive_items(query, items)

    if items:
        status = "ok"
        message = "Telegram archive posts matched deterministic query variants."
    elif failures and len(failures) == len(attempts):
        status = "invalid"
        message = f"Archive search failed for all query variants: {', '.join(_unique(failures)[:3])}."
    else:
        status = "insufficient_evidence"
        message = (
            "No retained Telegram archive evidence matched deterministic query variants inside the requested time window."
            if time_window.requested and time_window.strict
            else "No retained Telegram archive evidence matched deterministic query variants."
        )
    return {
        "status": status,
        "query": query,
        "query_variants": query_variants,
        "attempted_queries": attempts,
        "filters": logged_filters,
        "retrieval_policy": retrieval_policy.to_dict(),
        "time_window": time_window.to_dict(),
        "project_name_hint": project_name,
        "items": items[:candidate_limit],
        "retrieval_mode": (
            "hybrid_local_vector_archive_query_planner"
            if budget.allow_vector_retrieval
            else "sqlite_fts_archive_query_planner"
        ),
        "message": message,
    }


def _merge_archive_results(first: Mapping[str, Any], second: Mapping[str, Any], *, query: str) -> dict[str, Any]:
    combined = [
        *[dict(item) for item in first.get("items") or [] if isinstance(item, Mapping)],
        *[dict(item) for item in second.get("items") or [] if isinstance(item, Mapping)],
    ]
    deduplicated: dict[str, dict[str, Any]] = {}
    for item in combined:
        deduplicated.setdefault(_archive_item_identity(item), item)
    items = rank_archive_items(query, list(deduplicated.values()))[:_HARD_MAX_ARCHIVE_CANDIDATES]
    return {
        **dict(first),
        "status": "ok" if items else str(second.get("status") or first.get("status") or "insufficient_evidence"),
        "items": items,
        "query_variants": _unique([*_strings(first.get("query_variants")), *_strings(second.get("query_variants"))]),
        "attempted_queries": [
            *[dict(item) for item in first.get("attempted_queries") or [] if isinstance(item, Mapping)],
            *[dict(item) for item in second.get("attempted_queries") or [] if isinstance(item, Mapping)],
        ],
        "gap_search_performed": True,
    }


def _archive_query_variants(
    query: str,
    *,
    project_name: str | None,
    max_variants: int,
) -> list[str]:
    clean_query = _clean_text(query)
    lowered = clean_query.casefold()
    candidates: list[str] = []
    domain_specific = False

    candidates.extend(_ai_transformation_query_variants(lowered))
    candidates.extend(_ai_model_query_variants(lowered))
    if _contains_any(lowered, ("lead response", "sla", "лид", "заявк")):
        candidates.append("lead response SLA no answer")
        domain_specific = True
    if _contains_any(lowered, ("mvp", "radar", "demand", "спрос")):
        candidates.append("MVP repeated questions competitor traction")
        domain_specific = True
    if _contains_any(lowered, ("workflow", "studio", "sop", "воркфлоу", "сценар")):
        candidates.append("workflow automation SOP transcript")
        domain_specific = True
    if _contains_any(lowered, ("gdev", "game", "support", "игр", "саппорт")):
        candidates.append("game support triage eval pipeline")
        domain_specific = True
    if _contains_any(lowered, ("dream", "motif", "сон", "сновид")):
        candidates.append("dream motif pgvector retrieval")
        domain_specific = True
    if _contains_any(lowered, ("rag", "раг", "ретрив")):
        candidates.extend(("RAG retrieval", "archive retrieval"))
    if _contains_any(lowered, ("fts", "фтс", "sqlite", "sqlite")):
        candidates.append("SQLite FTS")
    if _contains_any(lowered, ("pgvector", "vector", "вектор", "hybrid", "гибрид")):
        candidates.append("pgvector retrieval")
    if _contains_any(lowered, ("harness", "харнес")):
        # SQLite FTS does not lemmatize Russian transliterations such as "харнесса".
        candidates.append("harness")
    if not domain_specific and _contains_any(lowered, ("gold", "eval", "оцен", "провер", "цитат", "grounded", "галлюцин")):
        candidates.extend(("gold labels citation precision", "eval gates grounded claims"))
    if not domain_specific and _contains_any(lowered, ("insufficient", "unsupported", "no answer", "no-answer", "недостат", "не хват", "не гад", "честно")):
        candidates.extend(("insufficient evidence no answer", "unsupported claims"))
    if _contains_any(lowered, ("linked source", "linked-source", "source cache", "источник", "ссылк", "линк")):
        candidates.append("linked sources source cache")
    if _contains_any(lowered, ("external verification", "freshness", "fresh", "свеж", "внешн", "вериф")):
        candidates.append("external verification freshness")
    if _contains_any(lowered, ("reaction", "feedback", "реакц", "фидбек", "лайк")):
        candidates.append("reaction feedback operator")
    if _contains_any(lowered, ("weekly", "brief", "report", "недель", "отчет", "бриф")):
        candidates.append("weekly report personal research memory")
    if _contains_any(lowered, ("assistant", "project-aware", "project aware", "ассистент", "проектн")):
        candidates.append("project aware research assistant")
    if not domain_specific and _contains_any(lowered, ("decision", "action", "confirm", "решени", "действ", "подтверж")):
        candidates.append("decision action confirmation gated")
    if _contains_any(lowered, ("provider egress", "privacy", "приват", "egress")):
        candidates.append("provider egress privacy")

    keyword_variant = _keyword_query_variant(clean_query)
    if keyword_variant:
        candidates.append(keyword_variant)
    bounded_original = _bounded_original_query(clean_query)
    if bounded_original:
        candidates.append(bounded_original)
    if not candidates:
        candidates.extend(_project_query_variants(project_name))
    variants = _unique_strings(candidates)
    if not variants and clean_query:
        variants = [clean_query]
    return variants[: max(1, min(_MAX_ARCHIVE_QUERY_VARIANTS, int(max_variants or _MAX_ARCHIVE_QUERY_VARIANTS)))]


def _ai_transformation_query_variants(lowered_query: str) -> list[str]:
    if not _is_ai_transformation_question(lowered_query):
        return []
    variants = list(_AI_TRANSFORMATION_BASE_VARIANTS)
    if _contains_any(
        lowered_query,
        (
            "не получилось",
            "не дала",
            "не дало",
            "нет прироста",
            "провал",
            "почему нет",
            "roi",
            "productivity",
            "прирост",
            "успешн",
            "неуспешн",
        ),
    ):
        variants = [*_AI_TRANSFORMATION_FAILURE_VARIANTS, *variants]
    if _contains_any(
        lowered_query,
        (
            "увольн",
            "наним",
            "hiring",
            "layoff",
            "layoffs",
            "найм",
            "рабоч",
            "jobs",
        ),
    ):
        variants = [*_AI_TRANSFORMATION_HIRING_VARIANTS, *variants]
    return _unique_strings(variants)


def _ai_model_query_variants(lowered_query: str) -> list[str]:
    if not _is_ai_model_question(lowered_query):
        return []
    return list(_AI_MODEL_VARIANTS)


def _is_ai_model_question(lowered_query: str) -> bool:
    return _contains_any(
        lowered_query,
        (
            "модел",
            "models",
            "llm",
            "gpt",
            "claude",
            "gemini",
            "openai",
            "anthropic",
            "mistral",
            "qwen",
            "llama",
        ),
    )


def _is_ai_transformation_question(lowered_query: str) -> bool:
    has_ai = _contains_any(lowered_query, ("ai", "ии", "artificial intelligence"))
    has_company_scope = _contains_any(
        lowered_query,
        (
            "transformation",
            "трансформац",
            "внедрен",
            "компан",
            "бизнес",
            "roi",
            "productivity",
            "эффект",
            "прирост",
        ),
    )
    return has_ai and has_company_scope


def _project_query_variants(project_name: str | None) -> list[str]:
    clean_project = _clean_text(str(project_name or "").replace("-", " ").replace("_", " "))
    if not clean_project:
        return []
    lowered_project = clean_project.casefold()
    variants = list(_PROJECT_QUERY_HINTS.get(lowered_project, ()))
    if not variants:
        tokens = [token for token in _query_tokens(clean_project) if token not in _QUERY_STOPWORDS]
        if tokens:
            variants.append(" ".join(tokens[:4]))
    return variants


def _keyword_query_variant(query: str) -> str:
    tokens = []
    for token in _query_tokens(query.replace("-", " ")):
        normalized = _normalize_query_token(token)
        if not normalized or normalized.casefold() in _QUERY_STOPWORDS:
            continue
        if len(normalized) < 3 and normalized.upper() not in {"AI", "OS"}:
            continue
        tokens.append(normalized)
    preferred = [token for token in tokens if _is_preferred_query_token(token)]
    selected = _unique_strings([*preferred, *tokens])[:5]
    return " ".join(selected)


def _bounded_original_query(query: str) -> str:
    tokens = [
        _normalize_query_token(token)
        for token in _query_tokens(query.replace("-", " "))
        if token.casefold() not in _QUERY_STOPWORDS
    ]
    if 1 <= len(tokens) <= 5:
        return " ".join(tokens)
    return ""


def _query_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for match in _QUERY_TOKEN_RE.finditer(value):
        token = match.group(0).strip("_-+").casefold()
        if token:
            tokens.append(token)
    return tokens


def _normalize_query_token(token: str) -> str:
    lowered = token.casefold().strip("_-+")
    if lowered in {"rag", "рага", "рагом", "рагу", "раг"}:
        return "RAG"
    if lowered in {"fts", "фтс"}:
        return "FTS"
    if lowered in {"sqlite"}:
        return "SQLite"
    if lowered in {"ai"}:
        return "AI"
    if lowered in {"mvp"}:
        return "MVP"
    if lowered in {"sla"}:
        return "SLA"
    return lowered.replace("_", " ")


def _is_preferred_query_token(token: str) -> bool:
    lowered = token.casefold()
    return (
        token.isupper()
        or any(char.isdigit() for char in token)
        or lowered
        in {
            "agent",
            "archive",
            "assistant",
            "citation",
            "evidence",
            "eval",
            "feedback",
            "freshness",
            "gold",
            "grounded",
            "memory",
            "pgvector",
            "project",
            "retrieval",
            "source",
            "telegram",
            "workflow",
        }
    )


def _contains_any(value: str, needles: Sequence[str]) -> bool:
    tokens = _query_token_segments(value)
    for needle in needles:
        clean = needle.casefold().strip()
        if not clean:
            continue
        if " " in clean or "-" in clean:
            if clean in value:
                return True
            continue
        if clean.isascii() and len(clean) <= 4:
            if clean in tokens or any(token.startswith(clean) for token in tokens):
                return True
            continue
        if clean in value:
            return True
    return False


def _query_token_segments(value: str) -> set[str]:
    segments: set[str] = set()
    for token in _query_tokens(value):
        segments.add(token)
        for part in re.split(r"[-_+]", token):
            if part:
                segments.add(part)
    return segments


def _unique_strings(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = _clean_text(value)
        if not clean:
            continue
        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(clean)
    return result


def _archive_item_identity(item: Mapping[str, Any]) -> str:
    for key in (
        "archive_document_id",
        "post_archive_document_id",
        "source_url",
        "telegram_url",
        "message_url",
        "content_hash",
    ):
        value = str(item.get(key) or "").strip()
        if value:
            return f"{key}:{value}"
    return json.dumps(dict(item), ensure_ascii=False, sort_keys=True)


def _archive_item_matches_query_variant(item: Mapping[str, Any], query_variant: str) -> bool:
    terms = _significant_query_terms(query_variant)
    if len(terms) <= 1:
        return True
    haystack = _clean_text(
        " ".join(
            str(item.get(key) or "")
            for key in (
                "snippet",
                "content",
                "title",
                "summary",
                "channel_username",
                "source_url",
                "telegram_url",
                "message_url",
            )
        )
    ).casefold()
    if not haystack:
        return False
    segments = _query_token_segments(haystack)
    matched = 0
    for term in terms:
        if term in segments or (len(term) > 4 and term in haystack):
            matched += 1
    required = 1 if len(terms) == 2 else 2
    return matched >= required


def _significant_query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for token in _query_tokens(query.replace("-", " ")):
        normalized = _normalize_query_token(token).casefold()
        if normalized in _QUERY_STOPWORDS or len(normalized) < 3:
            continue
        terms.append(normalized)
    return _unique_strings(terms)


def _call_curated_search(
    facade: Any,
    query: str,
    *,
    week_label: str | None,
    limit: int,
    tool_calls: list[dict[str, Any]],
    budget: MemoryResearchBudget,
    time_window: ResearchTimeWindow,
) -> dict[str, Any]:
    if len(tool_calls) >= budget.max_tool_calls or not hasattr(facade, "search_intelligence_items"):
        return {"status": "skipped", "query": query, "items": [], "message": "Curated search skipped by planner limit."}
    filters = {"week_label": week_label} if week_label else {}
    if time_window.requested and time_window.strict and not week_label:
        tool_calls.append(
            {
                "name": "search_intelligence_items",
                "arguments": {
                    "query": query,
                    "filters": {"time_window_enforced": False},
                    "limit": limit,
                    "skipped_reason": "strict_time_window_not_supported_for_curated_memory",
                    "time_window": time_window.to_dict(),
                },
            }
        )
        return {
            "status": "skipped",
            "query": query,
            "items": [],
            "message": "Curated search skipped because the requested recency window can only be enforced on dated archive posts.",
        }
    tool_calls.append({"name": "search_intelligence_items", "arguments": {"query": query, "filters": filters, "limit": limit}})
    try:
        return dict(facade.search_intelligence_items(query, filters=filters, limit=limit))
    except Exception as exc:
        return {"status": "invalid", "query": query, "items": [], "message": f"Curated search failed: {type(exc).__name__}."}


def _call_saved_knowledge(facade: Any, query: str, *, project_name: str | None, limit: int) -> dict[str, Any]:
    settings = getattr(facade, "_settings", None)
    db_path = getattr(settings, "db_path", None)
    if not db_path:
        return {"items": []}
    try:
        return query_saved_knowledge(db_path, filters={"topic": query, **({"project": project_name} if project_name else {})}, limit=limit)
    except (OSError, sqlite3.Error, ValueError):
        return {"items": []}


def _route_project_context(
    facade: Any,
    query: str,
    *,
    project_name: str | None,
    week_label: str | None,
    limit: int,
    archive_result: Mapping[str, Any],
    curated_result: Mapping[str, Any],
    fixtures: Sequence[Mapping[str, Any]] | None,
    tool_calls: list[dict[str, Any]],
    budget: MemoryResearchBudget,
) -> dict[str, Any]:
    if fixtures:
        contexts = [dict(item) for item in fixtures]
        active = [
            item
            for item in contexts
            if str(item.get("relevance_label") or "no_match") in PROJECT_LABELS
            and str(item.get("relevance_label") or "no_match") != "no_match"
        ]
        if len(active) > 1:
            return {
                "schema_version": "project_context_decision_support.v1",
                "status": "ambiguous",
                "query": query,
                "project_name": None,
                "candidate_projects": [
                    {
                        "project_name": item.get("project_name"),
                        "relevance_label": item.get("relevance_label"),
                        "source_refs": _strings(item.get("source_refs")),
                    }
                    for item in active
                ],
                "relevance_label": "ambiguous_project",
                "descriptor_fields_used": [],
                "source_refs": _unique([ref for item in active for ref in _strings(item.get("source_refs"))]),
                "unknowns": ["which active project should receive this research"],
                "decision_support": _readonly_decision_support(),
            }
        return contexts[0] if contexts else _empty_project_context(query, project_name)

    if len(tool_calls) >= budget.max_tool_calls or not hasattr(facade, "analyze_project_context"):
        return _empty_project_context(query, project_name)
    tool_calls.append(
        {
            "name": "analyze_project_context",
            "arguments": {"query": query, "project_name": project_name, "week_label": week_label, "limit": limit},
        }
    )
    try:
        result = dict(facade.analyze_project_context(query, project_name=project_name, week_label=week_label, limit=limit))
    except Exception:
        return _empty_project_context(query, project_name)
    if result.get("relevance_label") not in PROJECT_LABELS:
        result["relevance_label"] = "no_match"
    result.setdefault("decision_support", _readonly_decision_support())
    result.setdefault("archive_evidence", _mapping(archive_result))
    result.setdefault("curated_knowledge", _mapping(curated_result))
    return result


def _call_linked_sources(
    archive_result: Mapping[str, Any],
    *,
    fetcher: LinkedSourceFetcher | None,
    tool_calls: list[dict[str, Any]],
    budget: MemoryResearchBudget,
) -> dict[str, Any]:
    if len(tool_calls) >= budget.max_tool_calls:
        return {"status": "skipped", "cache_records": [], "receipt": {"status": "skipped"}}
    posts = [item for item in archive_result.get("items") or [] if isinstance(item, Mapping)]
    tool_calls.append(
        {
            "name": "resolve_linked_sources",
            "arguments": {"post_count": len(posts), "max_sources": budget.max_linked_sources, "fixture_fetcher": fetcher is not None},
        }
    )
    return resolve_linked_sources(
        posts,
        fetcher=fetcher,
        approvals=LinkedSourceApprovals(),
        max_sources=budget.max_linked_sources,
    )


def _archive_evidence(result: Mapping[str, Any], *, question: str, max_items: int, time_window: ResearchTimeWindow) -> dict[str, Any]:
    items = rank_archive_items(question, [dict(item) for item in result.get("items") or [] if isinstance(item, Mapping)])[:max_items]
    source_refs = _unique(
        [
            str(item.get("source_url") or item.get("telegram_url") or item.get("message_url") or item.get("archive_document_id") or "")
            for item in items
            if str(item.get("source_url") or item.get("telegram_url") or item.get("message_url") or item.get("archive_document_id") or "").strip()
        ]
    )
    return {
        "status": str(result.get("status") or ("ok" if items else "insufficient_evidence")),
        "retrieval_mode": result.get("retrieval_mode") or "sqlite_fts_archive",
        "time_window": time_window.to_dict(),
        "query_variants": _strings(result.get("query_variants")),
        "attempted_queries": [dict(item) for item in result.get("attempted_queries") or [] if isinstance(item, Mapping)],
        "source_refs": source_refs,
        "items": items,
    }


def _archive_candidate_pool(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Keep a bounded local candidate pool for the application-level reranker."""

    fields = (
        "archive_document_id", "post_archive_document_id", "post_id", "posted_at", "channel_username", "source_url",
        "snippet", "summary", "matched_query_variant", "relevance_label", "directness_score", "source_role",
        "supports_action", "source_role_reason", "fusion_score", "semantic_score", "retrieval_mode",
    )
    return [
        {key: item[key] for key in fields if key in item}
        for item in result.get("items") or []
        if isinstance(item, Mapping)
    ][:_HARD_MAX_ARCHIVE_CANDIDATES]


def _curated_evidence(result: Mapping[str, Any], *, max_items: int) -> dict[str, Any]:
    items = [dict(item) for item in result.get("items") or [] if isinstance(item, Mapping)][:max_items]
    source_refs = _unique([ref for item in items for ref in _source_refs(item)])
    return {
        "status": str(result.get("status") or ("ok" if items else "empty")),
        "source_refs": source_refs,
        "items": items,
    }


def _linked_evidence(result: Mapping[str, Any], *, max_items: int) -> dict[str, Any]:
    records = [dict(item) for item in result.get("cache_records") or [] if isinstance(item, Mapping)]
    extracted = [item for item in records if item.get("extraction_status") == "extracted"]
    visible = (extracted or records)[: max(1, min(_HARD_MAX_LINKED_SOURCES, int(max_items or 1)))]
    return {
        "status": str(result.get("status") or ("ok" if extracted else "empty")),
        "source_refs": _unique(
            [
                str(item.get("source_url") or item.get("normalized_url") or "")
                for item in visible
                if str(item.get("source_url") or item.get("normalized_url") or "").strip()
            ]
        ),
        "items": visible,
        "extracted_count": len(extracted),
        "candidate_count": len(result.get("candidates") or []),
    }


def _project_fit(context: Mapping[str, Any]) -> dict[str, Any]:
    label = str(context.get("relevance_label") or "no_match")
    if label not in PROJECT_LABELS:
        label = "no_match"
    guidance_by_label = {
        "direct_implication": "Можно применить к проекту только через маленькое проверяемое действие из цитируемого источника.",
        "weak_watch": "Оставить как сигнал для наблюдения; пока не превращать в проектную работу.",
        "learning_relevance": "Использовать как материал для изучения; прямое проектное действие не доказано.",
        "no_match": "Проект не совпал; считать это общим инженерным сигналом, а не проектным действием.",
        "ambiguous_project": "Сначала выбрать целевой проект, потом превращать исследование в действие.",
    }
    return {
        "status": str(context.get("status") or "ok"),
        "project_name": context.get("project_name"),
        "project_repo": context.get("project_repo"),
        "project_focus": context.get("project_focus"),
        "candidate_projects": list(context.get("candidate_projects") or []),
        "relevance_label": label,
        "confidence": _confidence(label),
        "descriptor_fields_used": _strings(context.get("descriptor_fields_used")),
        "matched_terms": _strings(context.get("matched_terms")),
        "source_refs": _strings(context.get("source_refs")),
        "unknowns": _strings(context.get("unknowns")),
        "guidance": guidance_by_label[label],
        "decision_support": {
            **_readonly_decision_support(),
            **_mapping(context.get("decision_support")),
            "write_performed": False,
            "project_mutation_exposed": False,
        },
    }


def _project_decision_synthesis(
    *,
    question: str,
    project_fit: Mapping[str, Any],
    curated_evidence: Mapping[str, Any],
    approved_claim_ledger: Mapping[str, Any],
    next_steps: Mapping[str, Sequence[str]],
    unknowns: Sequence[str],
    answer_gate: Mapping[str, Any],
) -> dict[str, Any]:
    project_name = _clean_text(project_fit.get("project_name")) or "проект"
    label = str(project_fit.get("relevance_label") or "no_match")
    approved_claims = [item for item in approved_claim_ledger.get("claims") or [] if isinstance(item, Mapping)]
    source_refs = _unique(
        [
            ref
            for claim in approved_claims
            for ref in _strings(claim.get("evidence_refs"))
        ]
    )
    saved_decisions = _saved_project_decisions(curated_evidence, project_name=project_name)
    current_blocker = _project_decision_blocker(
        project_fit=project_fit,
        approved_claims=approved_claims,
        unknowns=unknowns,
        answer_gate=answer_gate,
    )
    next_proof = _project_decision_next_proof(
        project_fit=project_fit,
        approved_claims=approved_claims,
        unknowns=unknowns,
        answer_gate=answer_gate,
    )
    grounded_recommendation = _project_decision_recommendation(
        project_fit=project_fit,
        approved_claims=approved_claims,
        next_steps=next_steps,
        answer_gate=answer_gate,
    )
    return {
        "schema_version": "prm_project_decision_synthesis.v1",
        "status": "ready" if approved_claims and label in {"direct_implication", "weak_watch", "learning_relevance"} else "insufficient_evidence",
        "question_intent": _clean_text(question)[:220],
        "project_name": project_name,
        "project_goal": _clean_text(project_fit.get("project_focus"))
        or "Связать локальный исследовательский сигнал с одним проверяемым действием проекта.",
        "current_blocker": current_blocker,
        "next_proof": next_proof,
        "saved_project_decisions": saved_decisions,
        "approved_claim_refs": [str(claim.get("claim_id") or "") for claim in approved_claims if str(claim.get("claim_id") or "")],
        "source_refs": source_refs[:5],
        "grounded_recommendation": grounded_recommendation,
        "next_action": grounded_recommendation,
        "acceptance_criterion": _project_decision_acceptance_criterion(
            project_fit=project_fit,
            approved_claims=approved_claims,
            recommendation=grounded_recommendation,
        ),
        "write_performed": False,
    }


def _saved_project_decisions(curated_evidence: Mapping[str, Any], *, project_name: str) -> list[str]:
    result: list[str] = []
    needle = project_name.casefold()
    for item in curated_evidence.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        text = _clean_text(
            item.get("title")
            or item.get("summary")
            or item.get("text")
            or item.get("body")
            or item.get("id")
        )
        haystack = f"{text} {item.get('item_type') or ''}".casefold()
        if "decision" not in haystack and "решени" not in haystack and needle not in haystack:
            continue
        if text and text not in result:
            result.append(text[:220])
        if len(result) >= 3:
            break
    return result


def _project_decision_blocker(
    *,
    project_fit: Mapping[str, Any],
    approved_claims: Sequence[Mapping[str, Any]],
    unknowns: Sequence[str],
    answer_gate: Mapping[str, Any],
) -> str:
    if bool(answer_gate.get("external_verification_required")):
        return "Нужна отдельная первоисточниковая проверка: текущий факт нельзя подтвердить локальным архивом."
    if not approved_claims:
        return "Нет approved claim ledger: нельзя делать проектную рекомендацию без поддержанного claims."
    label = str(project_fit.get("relevance_label") or "no_match")
    if label == "direct_implication":
        return "Главный риск сейчас — превратить архивный сигнал в изменение без маленького проверяемого подтверждения."
    if label == "weak_watch":
        return "Связь с проектом пока слабая: нужен повторяемый сигнал или первичный источник."
    if label == "learning_relevance":
        return "Материал полезен для обучения, но прямое product/code действие не доказано."
    if unknowns:
        return "Не закрыто: " + "; ".join(str(item) for item in unknowns[:2]) + "."
    return "Прямая связь с проектом не подтверждена."


def _project_decision_next_proof(
    *,
    project_fit: Mapping[str, Any],
    approved_claims: Sequence[Mapping[str, Any]],
    unknowns: Sequence[str],
    answer_gate: Mapping[str, Any],
) -> str:
    if bool(answer_gate.get("external_verification_required")):
        return "Получить approved primary-source verification и сравнить её с Telegram claim."
    if not approved_claims:
        return "Найти один релевантный локальный или первичный источник и провести claim-ledger проверку."
    label = str(project_fit.get("relevance_label") or "no_match")
    if label == "direct_implication":
        return "Сделать один маленький проверочный кейс в проекте и связать результат с цитируемым источником."
    if label == "weak_watch":
        return "Дождаться второго независимого источника или ручного подтверждения, что это влияет на backlog."
    if label == "learning_relevance":
        return "Провести маленький learning experiment и записать результат только после подтверждения."
    if unknowns:
        return "Закрыть первый неизвестный пункт: " + str(unknowns[0]) + "."
    return "Сначала выбрать более точный проектный критерий."


def _project_decision_recommendation(
    *,
    project_fit: Mapping[str, Any],
    approved_claims: Sequence[Mapping[str, Any]],
    next_steps: Mapping[str, Sequence[str]],
    answer_gate: Mapping[str, Any],
) -> str:
    if bool(answer_gate.get("external_verification_required")):
        return "Не принимать проектное решение до первоисточниковой проверки."
    if not approved_claims:
        return "Не менять проект: подтверждённых claims недостаточно."
    label = str(project_fit.get("relevance_label") or "no_match")
    if label == "direct_implication":
        concrete = _project_decision_concrete_action(project_fit=project_fit, approved_claims=approved_claims)
        if concrete:
            return concrete
        values = [str(item) for item in next_steps.get("apply") or [] if str(item).strip()]
        return _localize_next_step(values[0]) if values else "Сформулировать одно маленькое проверяемое действие из поддержанных источниками утверждений."
    if label == "weak_watch":
        values = [str(item) for item in next_steps.get("watch") or [] if str(item).strip()]
        return _localize_next_step(values[0]) if values else "Оставить как watch-сигнал, не заводя изменение."
    if label == "learning_relevance":
        values = [str(item) for item in next_steps.get("study") or [] if str(item).strip()]
        return _localize_next_step(values[0]) if values else "Использовать как learning input, не как проектное решение."
    return "Не применять к проекту из текущих доказательств."


def _project_decision_concrete_action(
    *,
    project_fit: Mapping[str, Any],
    approved_claims: Sequence[Mapping[str, Any]],
) -> str:
    project_name = _clean_text(project_fit.get("project_name")) or "проекта"
    haystack = _clean_text(
        " ".join(
            [
                str(project_fit.get("project_focus") or ""),
                *[str(claim.get("claim_text") or "") for claim in approved_claims],
            ]
        )
    ).casefold()
    if _contains_any(haystack, ("agent operations", "agentops", "доступ", "аудит", "audit", "access")):
        return (
            f"Для {project_name}: сделать одну проверку по agent operations: "
            "какой агент имеет доступ, кто подтверждает этот доступ и где остаётся журнал аудита."
        )
    if _contains_any(haystack, ("eval", "evaluation", "regression", "регресс", "оценк")):
        return f"Для {project_name}: добавить один проверочный кейс, который ловит описанный сбой на цитируемом примере."
    if _contains_any(haystack, ("retrieval", "rag", "citation", "цит", "источник")):
        return f"Для {project_name}: проверить один сценарий поиска и цитирования на этом источнике и зафиксировать, где ответ теряет опору на доказательства."
    return ""


def _project_decision_acceptance_criterion(
    *,
    project_fit: Mapping[str, Any],
    approved_claims: Sequence[Mapping[str, Any]],
    recommendation: str,
) -> str:
    if not approved_claims:
        return "Найдено хотя бы одно поддержанное источником утверждение с явной связью с проектом."
    if "agent operations" in recommendation.casefold() or "журнал аудита" in recommendation.casefold():
        return "Есть короткая проверка с агентом, уровнем доступа, подтверждающим человеком и местом аудита; без этого изменение не принимается."
    label = str(project_fit.get("relevance_label") or "no_match")
    if label == "direct_implication":
        return "Один маленький эксперимент воспроизводимо проходит, а его результат связан с цитируемым источником."
    if label == "weak_watch":
        return "Появляется второй независимый источник или ручное подтверждение влияния на backlog."
    if label == "learning_relevance":
        return "Сформулирована учебная заметка с источником и без изменения проекта."
    if recommendation:
        return "Рекомендация остаётся отказом от изменения, пока нет прямого проектного доказательства."
    return "Решение не принимается без нового цитируемого доказательства."


def _approach_comparison(
    archive_evidence: Mapping[str, Any],
    linked_evidence: Mapping[str, Any],
    curated_evidence: Mapping[str, Any],
) -> list[dict[str, Any]]:
    comparison: list[dict[str, Any]] = []
    archive_items = [item for item in archive_evidence.get("items") or [] if isinstance(item, Mapping)]
    linked_items = [item for item in linked_evidence.get("items") or [] if isinstance(item, Mapping)]
    curated_items = [item for item in curated_evidence.get("items") or [] if isinstance(item, Mapping)]
    comparison.append(
        {
            "approach": "Telegram archive first",
            "summary": (
                f"Use {len(archive_items)} retained Telegram post(s) as discovery and operator-memory context."
                if archive_items
                else "No retained Telegram post matched the question."
            ),
            "tradeoff": "High provenance for what appeared in your feed; may be stale, summarized, or second-hand.",
            "contradictions": [] if archive_items else ["archive retrieval did not provide support"],
        }
    )
    comparison.append(
        {
            "approach": "Linked source verification",
            "summary": (
                f"Use {int(linked_evidence.get('extracted_count') or 0)} extracted linked source(s) from cited Telegram posts."
                if linked_items
                else "No linked source text is approved or available in cache."
            ),
            "tradeoff": "Better grounding for source claims; fixture-first mode cannot prove live freshness.",
            "contradictions": _linked_contradictions(linked_items),
        }
    )
    comparison.append(
        {
            "approach": "Curated/project memory",
            "summary": (
                f"Use {len(curated_items)} curated memory item(s) to connect the evidence to prior decisions."
                if curated_items
                else "No curated memory item matched the question."
            ),
            "tradeoff": "Useful for continuity; curated memory can lag behind the raw archive.",
            "contradictions": [] if curated_items else ["curated memory did not add support"],
        }
    )
    return comparison


def _next_steps(
    project_fit: Mapping[str, Any],
    archive_evidence: Mapping[str, Any],
    linked_evidence: Mapping[str, Any],
    answer_gate: Mapping[str, Any],
) -> dict[str, list[str]]:
    label = str(project_fit.get("relevance_label") or "no_match")
    apply: list[str] = []
    watch: list[str] = []
    ignore: list[str] = []
    study: list[str] = []
    if not bool(answer_gate.get("allow_answer", True)):
        study.append("Do not answer or save a memory from related-but-insufficient evidence.")
        if bool(answer_gate.get("external_verification_required")):
            watch.append("Run an explicitly approved external verification step before making current claims.")
    elif label == "direct_implication":
        apply.append("Draft one bounded project action from the cited evidence; require confirmation before saving.")
    elif label == "weak_watch":
        watch.append("Keep this as a watch signal until repeated archive or linked-source evidence appears.")
    elif label == "learning_relevance":
        study.append("Read the linked source or archive thread as background before creating a project action.")
    elif label == "ambiguous_project":
        watch.append("Resolve the target project before applying the research.")
    else:
        study.append("Treat this as a cross-project engineering signal, not a project-specific action.")
    if not linked_evidence.get("extracted_count"):
        watch.append("Fetch or approve linked-source reading later if live freshness matters.")
    if not archive_evidence.get("items"):
        study.append("Add a sharper archive query or approved gold retrieval label.")
    return {"apply": apply, "watch": watch, "ignore": ignore, "study": study}


def _deeper_reading(
    linked_evidence: Mapping[str, Any],
    archive_evidence: Mapping[str, Any],
    curated_evidence: Mapping[str, Any],
) -> list[dict[str, Any]]:
    path: list[dict[str, Any]] = []
    for item in linked_evidence.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        url = str(item.get("source_url") or item.get("normalized_url") or "").strip()
        if not url:
            continue
        path.append(
            {
                "kind": "linked_source",
                "title": item.get("normalized_title") or item.get("source_type") or "linked source",
                "url": url,
                "status": item.get("extraction_status"),
            }
        )
    for item in archive_evidence.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        ref = str(item.get("source_url") or item.get("archive_document_id") or "").strip()
        if ref:
            path.append({"kind": "telegram_archive", "title": item.get("channel_username") or "Telegram archive", "ref": ref})
    for item in curated_evidence.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        ref = str(item.get("id") or item.get("title") or "").strip()
        if ref:
            path.append({"kind": "curated_memory", "title": item.get("title") or item.get("item_type") or "curated memory", "ref": ref})
    return path[:8]


def _unknowns(
    archive_evidence: Mapping[str, Any],
    linked_evidence: Mapping[str, Any],
    project_fit: Mapping[str, Any],
    linked_result: Mapping[str, Any],
    *,
    time_window: ResearchTimeWindow,
) -> list[str]:
    unknowns: list[str] = []
    if not archive_evidence.get("items"):
        if time_window.requested:
            unknowns.append("fresh local Telegram archive support for requested time window")
        else:
            unknowns.append("local Telegram archive support")
    if not linked_evidence.get("extracted_count"):
        unknowns.append("approved linked-source text")
    linked_receipt = _mapping(linked_result.get("receipt"))
    privacy = _mapping(linked_receipt.get("privacy"))
    if not privacy.get("live_http_fetch_used"):
        unknowns.append("live external freshness")
    unknowns.extend(_strings(project_fit.get("unknowns")))
    if project_fit.get("relevance_label") == "ambiguous_project":
        unknowns.append("target project selection")
    return _unique(unknowns)[:8]


def _repo_project_context(question: str, *, project_name: str | None) -> dict[str, Any]:
    lowered = _clean_text(" ".join([question, project_name or ""])).casefold()
    if not _contains_any(
        lowered,
        (
            "telegram research agent",
            "telegram-research-agent",
            "этот проект",
            "этого проекта",
            "репозитор",
            "repo",
            "repository",
            "дальше по проекту",
        ),
    ):
        return {"status": "not_applicable", "source_refs": []}
    return {
        "status": "matched",
        "project_name": "telegram-research-agent",
        "summary": (
            "Current repo gate: PRM-28 no-vector RAG evidence is recorded; PRM-19 dogfood must not start "
            "without explicit dogfood-start approval. For project-next-step questions, repo docs and gate receipts "
            "should take precedence over Telegram archive background."
        ),
        "summary_ru": (
            "Текущий gate проекта: PRM-28 no-vector RAG evidence записан; PRM-19 dogfood нельзя начинать "
            "без явного dogfood-start approval. Для вопросов о следующих шагах сначала используй repo docs "
            "и gate receipts, а Telegram-архив считай только фоном."
        ),
        "source_refs": [
            "docs/tasks.md",
            "docs/CODEX_PROMPT.md",
            "evals/prm18_release_gate_receipt_2026-08-11_post_prm28.json",
            "docs/audit/PRM_LOCAL_UX_TRIAL_2026-08-11.md",
        ],
    }


def _direct_answer(
    *,
    question: str,
    archive_evidence: Mapping[str, Any],
    linked_evidence: Mapping[str, Any],
    project_fit: Mapping[str, Any],
    unknowns: Sequence[str],
    answer_gate: Mapping[str, Any],
    time_window: ResearchTimeWindow,
) -> str:
    archive_items = [item for item in archive_evidence.get("items") or [] if isinstance(item, Mapping)]
    linked_items = [item for item in linked_evidence.get("items") or [] if isinstance(item, Mapping)]
    label = str(project_fit.get("relevance_label") or "no_match")
    gate_status = str(answer_gate.get("status") or "")
    gate_reason = str(answer_gate.get("reason") or "")
    ru = _is_russian(question)
    if gate_reason == "current_external_fact_required" or _is_current_external_fact_question(question):
        if ru:
            return "Нужна внешняя проверка перед текущим выводом. Локальный Telegram-архив ниже можно использовать только как discovery-контекст."
        return "External verification is required before a current claim. The local Telegram archive below is discovery context only."
    if time_window.requested and not archive_items and not linked_items:
        label_text = time_window.label or ("заданное окно" if ru else "the requested time window")
        if ru:
            return f"За {label_text} релевантных сохранённых Telegram-постов не найдено. Старые похожие посты не использую как ответ на свежий вопрос."
        return f"No relevant retained Telegram posts were found for {label_text}. Older related posts were not used as evidence for this freshness-scoped question."
    if gate_status == "needs_external_verification":
        if ru:
            return "Для этого вывода нужна внешняя проверка. Локальный архив даёт только направление, не финальное подтверждение."
        return "External verification is required for this answer. The local archive is directional context, not final proof."
    if not bool(answer_gate.get("allow_answer", True)):
        if gate_reason == "unsupported_project_state_claim":
            if ru:
                return "Нашёл только близкий локальный материал, но не цитируемое доказательство текущего/завершённого состояния проекта. Не буду утверждать, что это произошло."
            return "I found only related local material, not cited proof for the requested current/completed project state. I will not claim it happened."
        return "Недостаточно цитируемых локальных доказательств для надёжного ответа." if ru else "I do not have enough cited local evidence to answer reliably."
    if not archive_items and not linked_items:
        return "Локальных архивных или утверждённых linked-source доказательств недостаточно для ответа." if ru else "I do not have enough local archive or approved linked-source evidence to answer reliably."
    first_archive = _short(archive_items[0].get("snippet") or archive_items[0].get("content") or "", 220) if archive_items else ""
    first_linked = _short(linked_items[0].get("text_excerpt") or linked_items[0].get("redacted_failure_reason") or "", 220) if linked_items else ""
    source_count = len(archive_items) + len(linked_items)
    if ru:
        pieces = [f"Нашёл локальные источники: {source_count}."]
        first_signal = first_archive or first_linked
        if first_signal:
            pieces.append(f"Первый полезный сигнал: {first_signal}")
        guidance = str(project_fit.get("guidance") or "").strip()
        project_name = str(project_fit.get("project_name") or "").strip()
        if guidance:
            pieces.append(f"Для {project_name or 'проекта'}: {guidance}")
        else:
            pieces.append(f"Связь с проектом: {_localized_project_label(label)}.")
        if unknowns:
            gaps = "; ".join(_localize_unknown(str(item)) for item in unknowns[:3])
            pieces.append(f"Ограничение: {gaps}.")
        return " ".join(pieces)
    pieces = [f"Found {source_count} local source(s)."]
    first_signal = first_archive or first_linked
    if first_signal:
        pieces.append(f"First useful signal: {first_signal}")
    pieces.append(f"Project relation: {label}.")
    if unknowns:
        pieces.append("Limit: " + "; ".join(str(item) for item in unknowns[:3]) + ".")
    return " ".join(pieces)


def _answer_status(
    answer_gate: Mapping[str, Any],
    *,
    archive_evidence: Mapping[str, Any],
    linked_evidence: Mapping[str, Any],
    curated_evidence: Mapping[str, Any],
) -> str:
    gate_status = str(answer_gate.get("status") or "")
    if gate_status == "needs_external_verification":
        return "needs_external_verification"
    if not bool(answer_gate.get("allow_answer", True)):
        return "insufficient_evidence"
    if archive_evidence.get("items") or linked_evidence.get("items") or curated_evidence.get("items"):
        return "ok"
    return "insufficient_evidence"


def _answer_gate_unknowns(answer_gate: Mapping[str, Any]) -> list[str]:
    unknowns: list[str] = []
    if bool(answer_gate.get("external_verification_required")):
        unknowns.append("external verification before current claims")
    if bool(answer_gate.get("no_answer_required")):
        unknowns.append("sufficient cited proof for the requested claim")
    if not bool(answer_gate.get("current_claim_allowed", True)):
        unknowns.append("current-claim freshness")
    return unknowns


def _drafts_allowed(answer_gate: Mapping[str, Any]) -> bool:
    if not bool(answer_gate.get("allow_answer")):
        return False
    if bool(answer_gate.get("external_verification_required")) and not bool(answer_gate.get("current_claim_allowed", True)):
        return False
    return True


def _draft_proposals(
    *,
    question: str,
    direct_answer: str,
    project_fit: Mapping[str, Any],
    source_refs: Sequence[str],
    unknowns: Sequence[str],
) -> list[dict[str, Any]]:
    if not source_refs:
        return []
    drafts: list[dict[str, Any]] = [
        build_memory_proposal(
            "knowledge_note",
            {
                "title": _short(f"Research note: {question}", 120),
                "body": direct_answer,
                "rationale": "Drafted from bounded local research evidence; not persisted until confirmation.",
                "source_refs": list(source_refs[:8]),
                "metadata": {"schema_version": MEMORY_RESEARCH_SCHEMA_VERSION, "unknowns": list(unknowns[:5])},
            },
        )
    ]
    label = str(project_fit.get("relevance_label") or "no_match")
    if label == "direct_implication":
        drafts.append(
            build_memory_proposal(
                "action",
                {
                    "title": _short(f"Apply research: {question}", 120),
                    "body": "Convert this direct implication into one bounded project action after human review.",
                    "rationale": "Project routing reported direct_implication.",
                    "source_refs": list(source_refs[:8]),
                    "metadata": {"project_name": project_fit.get("project_name")},
                },
            )
        )
    elif label in {"weak_watch", "ambiguous_project"}:
        drafts.append(
            build_memory_proposal(
                "watch_topic",
                {
                    "title": _short(f"Watch research signal: {question}", 120),
                    "body": "Track this until stronger or less ambiguous evidence appears.",
                    "rationale": f"Project routing reported {label}.",
                    "source_refs": list(source_refs[:8]),
                    "metadata": {"project_name": project_fit.get("project_name")},
                },
            )
        )
    elif label == "learning_relevance":
        drafts.append(
            build_memory_proposal(
                "knowledge_note",
                {
                    "title": _short(f"Study path: {question}", 120),
                    "body": "Treat this as learning context rather than a direct project action.",
                    "rationale": "Project routing reported learning_relevance.",
                    "source_refs": list(source_refs[:8]),
                    "metadata": {"project_name": project_fit.get("project_name")},
                },
            )
        )
    return drafts[:3]


def _receipt(
    *,
    status: str,
    budget: MemoryResearchBudget,
    tool_calls: Sequence[Mapping[str, Any]],
    source_refs: Sequence[str],
    linked_result: Mapping[str, Any],
    draft_count: int,
    answer_gate: Mapping[str, Any],
) -> dict[str, Any]:
    linked_receipt = _mapping(linked_result.get("receipt"))
    linked_privacy = _mapping(linked_receipt.get("privacy"))
    return {
        "schema_version": MEMORY_RESEARCH_RECEIPT_SCHEMA_VERSION,
        "status": status,
        "mode": "local_research_fixture",
        "budget": budget.to_dict(),
        "tool_calls_used": len(tool_calls),
        "tool_calls": [dict(item) for item in tool_calls],
        "source_ref_count": len(source_refs),
        "draft_proposal_count": int(draft_count),
        "answer_gate": dict(answer_gate),
        "linked_source_receipt": linked_receipt,
        "privacy": {
            "mode": "local-research",
            "model_calls": 0,
            "estimated_cost_usd": 0.0,
            "bounded_telegram_snippet_provider_egress": False,
            "raw_telegram_corpus_egress": False,
            "provider_egress": False,
            "external_skill_used": False,
            "linked_source_live_fetch": bool(linked_privacy.get("live_http_fetch_used")),
            "provider_summarization_used": False,
            "vector_backend_used": bool(budget.allow_vector_retrieval),
            "local_embedding_backend": "local_hashing_text_vector.v1" if budget.allow_vector_retrieval else "",
            "external_embedding_provider_egress": False,
            "durable_writes": False,
            "drafts_only": True,
        },
    }


def _budget_refusal(question: str, budget: MemoryResearchBudget) -> tuple[str, str] | None:
    if budget.allow_open_browsing or _asks_for_open_browsing(question):
        return (
            "open_ended_browsing_refused",
            "Open-ended browsing is not approved for PRM-23 fixture-first research.",
        )
    if budget.allow_provider_egress or budget.max_model_calls > 0 or float(budget.max_cost_usd or 0.0) > 0.0:
        return (
            "provider_egress_refused",
            "Provider synthesis is not approved for PRM-23 implementation/tests.",
        )
    if budget.max_tool_calls < 1 or budget.max_tool_calls > _HARD_MAX_TOOL_CALLS:
        return ("tool_budget_refused", f"max_tool_calls must be between 1 and {_HARD_MAX_TOOL_CALLS}.")
    if budget.max_archive_sources < 1 or budget.max_archive_sources > _HARD_MAX_ARCHIVE_SOURCES:
        return ("source_budget_refused", f"max_archive_sources must be between 1 and {_HARD_MAX_ARCHIVE_SOURCES}.")
    if budget.max_archive_candidates < 1 or budget.max_archive_candidates > _HARD_MAX_ARCHIVE_CANDIDATES:
        return ("candidate_budget_refused", f"max_archive_candidates must be between 1 and {_HARD_MAX_ARCHIVE_CANDIDATES}.")
    if budget.max_linked_sources < 1 or budget.max_linked_sources > _HARD_MAX_LINKED_SOURCES:
        return ("linked_source_budget_refused", f"max_linked_sources must be between 1 and {_HARD_MAX_LINKED_SOURCES}.")
    if budget.max_retries < 0 or budget.max_retries > _HARD_MAX_RETRIES:
        return ("retry_budget_refused", f"max_retries must be between 0 and {_HARD_MAX_RETRIES}.")
    if budget.timeout_seconds < 1 or budget.timeout_seconds > _HARD_MAX_TIMEOUT_SECONDS:
        return ("timeout_budget_refused", f"timeout_seconds must be between 1 and {_HARD_MAX_TIMEOUT_SECONDS}.")
    if budget.max_prompt_chars < 100 or budget.max_prompt_chars > _HARD_MAX_PROMPT_CHARS:
        return ("prompt_budget_refused", f"max_prompt_chars must be between 100 and {_HARD_MAX_PROMPT_CHARS}.")
    return None


def _refusal_payload(question: str, budget: MemoryResearchBudget, reason: str, message: str) -> dict[str, Any]:
    status = "invalid" if reason == "invalid_question" else "refused"
    receipt = {
        "schema_version": MEMORY_RESEARCH_RECEIPT_SCHEMA_VERSION,
        "status": status,
        "mode": "local_research_fixture",
        "refusal_reason": reason,
        "budget": budget.to_dict(),
        "tool_calls_used": 0,
        "tool_calls": [],
        "privacy": {
            "mode": "local-research",
            "model_calls": 0,
            "estimated_cost_usd": 0.0,
            "bounded_telegram_snippet_provider_egress": False,
            "raw_telegram_corpus_egress": False,
            "provider_egress": False,
            "external_skill_used": False,
            "linked_source_live_fetch": False,
            "provider_summarization_used": False,
            "durable_writes": False,
            "drafts_only": True,
        },
    }
    return {
        "schema_version": MEMORY_RESEARCH_SCHEMA_VERSION,
        "status": status,
        "mode": "local_research_fixture",
        "question": question,
        "direct_answer": "",
        "archive_evidence": {"status": "skipped", "source_refs": [], "items": []},
        "curated_memory": {"status": "skipped", "source_refs": [], "items": []},
        "linked_source_evidence": {"status": "skipped", "source_refs": [], "items": [], "extracted_count": 0},
        "approach_comparison": [],
        "project_fit": _project_fit(_empty_project_context(question, None)),
        "next_steps": {"apply": [], "watch": [], "ignore": [], "study": []},
        "deeper_reading_path": [],
        "unknowns": [message],
        "draft_proposals": [],
        "receipt": receipt,
        "privacy": receipt["privacy"],
        "answer": "",
        "message": message,
    }


def _empty_project_context(query: str, project_name: str | None) -> dict[str, Any]:
    return {
        "schema_version": "project_context_decision_support.v1",
        "status": "insufficient_evidence",
        "query": query,
        "project_name": project_name,
        "relevance_label": "no_match",
        "descriptor_fields_used": [],
        "source_refs": [],
        "unknowns": ["active project context"],
        "decision_support": _readonly_decision_support(),
    }


def _readonly_decision_support() -> dict[str, bool]:
    return {
        "automatic_mvp_build_approval": False,
        "code_mutation_exposed": False,
        "project_mutation_exposed": False,
        "write_performed": False,
        "requires_human_confirmation_for_saves": True,
    }


def _linked_contradictions(items: Sequence[Mapping[str, Any]]) -> list[str]:
    contradictions: list[str] = []
    if not items:
        contradictions.append("linked source text was not available")
    for item in items:
        status = str(item.get("extraction_status") or "")
        if status and status != "extracted":
            contradictions.append(f"linked source extraction status is {status}")
    return _unique(contradictions)


def _confidence(label: str) -> str:
    return {
        "direct_implication": "high",
        "learning_relevance": "medium",
        "weak_watch": "low-medium",
        "ambiguous_project": "low",
        "no_match": "low",
    }.get(label, "low")


def _asks_for_open_browsing(question: str) -> bool:
    lowered = question.casefold()
    return any(term in lowered for term in _OPEN_BROWSING_TERMS)


def _source_refs(item: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("source_refs", "source_urls"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            refs.append(value.strip())
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            refs.extend(str(ref).strip() for ref in value if str(ref).strip())
    if isinstance(item.get("source_url"), str) and item["source_url"].strip():
        refs.append(item["source_url"].strip())
    return _unique(refs)


def _privacy_line(privacy: Mapping[str, Any]) -> str:
    return (
        "Privacy: "
        f"mode={privacy.get('mode') or 'local-research'}; "
        f"model_calls={int(privacy.get('model_calls') or 0)}; "
        f"estimated_cost_usd={_format_cost(privacy.get('estimated_cost_usd'))}; "
        "bounded_telegram_snippet_provider_egress="
        f"{_bool_text(privacy.get('bounded_telegram_snippet_provider_egress'))}; "
        f"raw_telegram_corpus_egress={_bool_text(privacy.get('raw_telegram_corpus_egress'))}; "
        f"linked_source_live_fetch={_bool_text(privacy.get('linked_source_live_fetch'))}; "
        f"vector_backend_used={_bool_text(privacy.get('vector_backend_used'))}; "
        f"external_skill_used={_bool_text(privacy.get('external_skill_used'))}; "
        f"durable_writes={_bool_text(privacy.get('durable_writes'))}"
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _is_russian(value: str) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", value or ""))


def _short(value: Any, limit: int = 220) -> str:
    compact = _clean_text(value)
    if len(compact) <= limit:
        return compact or "n/a"
    if limit <= 3:
        return compact[:limit]
    return compact[: limit - 3].rstrip() + "..."


def _unique(values: Sequence[Any]) -> list[Any]:
    seen: set[str] = set()
    unique: list[Any] = []
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique


def _bool_text(value: Any) -> str:
    return "true" if bool(value) else "false"


def _format_cost(value: Any) -> str:
    try:
        cost = float(value or 0.0)
    except (TypeError, ValueError):
        return "0"
    if cost == 0.0:
        return "0"
    return f"{cost:.8f}"
