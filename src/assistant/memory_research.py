from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from assistant.linked_sources import (
    FakeLinkedSourceFetcher,
    LinkedSourceApprovals,
    LinkedSourceFetcher,
    resolve_linked_sources,
)
from assistant.pi_facade import PersonalIntelligenceFacade
from assistant.pi_memory import build_memory_proposal
from assistant.rag_context_pack import build_rag_context_pack, render_rag_context_pack
from config.settings import Settings


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
    "agent",
    "agents",
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
    "into",
    "is",
    "it",
    "me",
    "my",
    "need",
    "needs",
    "of",
    "on",
    "or",
    "our",
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
    "а",
    "без",
    "было",
    "бы",
    "в",
    "вот",
    "все",
    "всю",
    "где",
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
    "мне",
    "мой",
    "моего",
    "мои",
    "можно",
    "на",
    "надо",
    "нам",
    "не",
    "него",
    "них",
    "но",
    "о",
    "ок",
    "он",
    "она",
    "они",
    "от",
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
    "это",
    "этого",
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


@dataclass(frozen=True)
class MemoryResearchBudget:
    max_tool_calls: int = 4
    max_archive_sources: int = 5
    max_linked_sources: int = 3
    max_retries: int = 0
    timeout_seconds: int = 30
    max_prompt_chars: int = 8_000
    max_model_calls: int = 0
    max_cost_usd: float = 0.0
    allow_open_browsing: bool = False
    allow_provider_egress: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_tool_calls": int(self.max_tool_calls),
            "max_archive_sources": int(self.max_archive_sources),
            "max_linked_sources": int(self.max_linked_sources),
            "max_retries": int(self.max_retries),
            "timeout_seconds": int(self.timeout_seconds),
            "max_prompt_chars": int(self.max_prompt_chars),
            "max_model_calls": int(self.max_model_calls),
            "max_cost_usd": round(float(self.max_cost_usd or 0.0), 8),
            "allow_open_browsing": bool(self.allow_open_browsing),
            "allow_provider_egress": bool(self.allow_provider_egress),
        }


def answer_memory_research(
    question: str,
    *,
    settings: Settings | None = None,
    facade: PersonalIntelligenceFacade | Any | None = None,
    week_label: str | None = None,
    project_name: str | None = None,
    limit: int = 5,
    budget: MemoryResearchBudget | None = None,
    linked_source_fetcher: LinkedSourceFetcher | FakeLinkedSourceFetcher | None = None,
    linked_source_fixtures: Mapping[str, Mapping[str, Any]] | None = None,
    project_context_fixtures: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    clean_question = _clean_text(question)
    active_budget = budget or MemoryResearchBudget()
    budget_refusal = _budget_refusal(clean_question, active_budget)
    if not clean_question:
        return _refusal_payload("", active_budget, "invalid_question", "Question is empty.")
    if budget_refusal:
        return _refusal_payload(clean_question, active_budget, budget_refusal[0], budget_refusal[1])

    bounded_limit = max(1, min(active_budget.max_archive_sources, int(limit or active_budget.max_archive_sources)))
    active_facade = facade or PersonalIntelligenceFacade(settings=settings)
    tool_calls: list[dict[str, Any]] = []

    archive_result = _call_archive_search(
        active_facade,
        clean_question,
        week_label=week_label,
        project_name=project_name,
        limit=bounded_limit,
        tool_calls=tool_calls,
        budget=active_budget,
    )
    curated_result = _call_curated_search(
        active_facade,
        clean_question,
        week_label=week_label,
        limit=bounded_limit,
        tool_calls=tool_calls,
        budget=active_budget,
    )
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

    archive_evidence = _archive_evidence(archive_result, max_items=bounded_limit)
    linked_evidence = _linked_evidence(linked_result, max_items=active_budget.max_linked_sources)
    curated_evidence = _curated_evidence(curated_result, max_items=bounded_limit)
    project_fit = _project_fit(project_context)
    context_pack = build_rag_context_pack(
        question=clean_question,
        archive_evidence=archive_evidence,
        curated_memory=curated_evidence,
        linked_source_evidence=linked_evidence,
        project_fit=project_fit,
        max_sources=active_budget.max_archive_sources + active_budget.max_linked_sources,
    )
    answer_gate = _mapping(context_pack.get("answer_gate"))
    comparison = _approach_comparison(archive_evidence, linked_evidence, curated_evidence)
    next_steps = _next_steps(project_fit, archive_evidence, linked_evidence, answer_gate)
    deeper_reading = _deeper_reading(linked_evidence, archive_evidence, curated_evidence)
    unknowns = _unknowns(archive_evidence, linked_evidence, project_fit, linked_result)
    unknowns = _unique([*unknowns, *_answer_gate_unknowns(answer_gate)])
    repo_project_context = _repo_project_context(clean_question, project_name=project_name)
    direct_answer = _direct_answer(
        question=clean_question,
        archive_evidence=archive_evidence,
        linked_evidence=linked_evidence,
        project_fit=project_fit,
        unknowns=unknowns,
        answer_gate=answer_gate,
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
    return {
        "schema_version": MEMORY_RESEARCH_SCHEMA_VERSION,
        "status": receipt["status"],
        "mode": "local_research_fixture",
        "question": clean_question,
        "direct_answer": direct_answer,
        "archive_evidence": archive_evidence,
        "curated_memory": curated_evidence,
        "linked_source_evidence": linked_evidence,
        "approach_comparison": comparison,
        "project_fit": project_fit,
        "repo_project_context": repo_project_context,
        "context_pack": context_pack,
        "answer_gate": answer_gate,
        "next_steps": next_steps,
        "deeper_reading_path": deeper_reading,
        "unknowns": unknowns,
        "draft_proposals": drafts,
        "receipt": receipt,
        "privacy": receipt["privacy"],
        "answer": render_memory_research_answer_body(
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
        ),
    }


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


def _compact_labels(ru: bool) -> dict[str, str]:
    if ru:
        return {
            "question": "Вопрос",
            "mode": "Режим: local-research; без LLM, live web и записей.",
            "answer": "Короткий ответ",
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
    answer_gate = _mapping(payload.get("answer_gate"))
    archive_evidence = _mapping(payload.get("archive_evidence"))
    linked_evidence = _mapping(payload.get("linked_source_evidence"))
    project_fit = _mapping(payload.get("project_fit"))
    repo_context = _mapping(payload.get("repo_project_context"))
    archive_items = [item for item in archive_evidence.get("items") or [] if isinstance(item, Mapping)]
    linked_items = [item for item in linked_evidence.get("items") or [] if isinstance(item, Mapping)]
    source_count = len(archive_items) + len(linked_items)
    project_label = str(project_fit.get("relevance_label") or "no_match")
    if bool(answer_gate.get("external_verification_required")) and not bool(answer_gate.get("current_claim_allowed", True)):
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
    if source_count:
        first = archive_items[0] if archive_items else linked_items[0]
        snippet = _short(first.get("snippet") or first.get("content") or first.get("text_excerpt") or "", 150)
        if ru:
            return (
                f"Нашёл локальные источники: {source_count}. Главный первый сигнал: {snippet} "
                f"Маршрут проекта: {_localized_project_label(project_label)}."
            )
        return f"Found {source_count} local source(s). First strong signal: {snippet} Project routing: {project_label}."
    return (
        "Локальных источников не найдено. Я не буду додумывать ответ."
        if ru
        else "No local sources matched. I will not guess beyond available data."
    )


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
            "читать как фон; не превращать в проектное действие без проверки и подтверждения."
        ),
        "Draft one bounded project action from the cited evidence; require confirmation before saving.": (
            "сформулировать одно ограниченное действие из цитируемых источников; сохранить только после подтверждения."
        ),
        "Run an explicitly approved external verification step before making current claims.": (
            "перед текущими утверждениями отдельно разрешить внешнюю проверку."
        ),
        "Do not answer or save a memory from related-but-insufficient evidence.": (
            "не отвечать и не сохранять память из похожих, но недостаточных доказательств."
        ),
        "Resolve the target project before applying the research.": "сначала выбрать целевой проект.",
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


def _call_archive_search(
    facade: Any,
    query: str,
    *,
    week_label: str | None,
    project_name: str | None,
    limit: int,
    tool_calls: list[dict[str, Any]],
    budget: MemoryResearchBudget,
) -> dict[str, Any]:
    if len(tool_calls) >= budget.max_tool_calls or not hasattr(facade, "search_telegram_archive"):
        return {"status": "skipped", "query": query, "items": [], "message": "Archive search skipped by planner limit."}
    filters: dict[str, Any] = {}
    if week_label:
        filters["week_label"] = week_label
    query_variants = _archive_query_variants(query, project_name=project_name, max_variants=_MAX_ARCHIVE_QUERY_VARIANTS)
    tool_calls.append(
        {
            "name": "search_telegram_archive",
            "arguments": {
                "query": query,
                "query_variants": query_variants,
                "filters": filters,
                "project_name_hint": project_name,
                "limit": limit,
            },
        }
    )

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    attempts: list[dict[str, Any]] = []
    failures: list[str] = []
    for variant in query_variants:
        remaining = max(0, int(limit or 0) - len(items))
        if remaining <= 0:
            break
        try:
            result = dict(facade.search_telegram_archive(variant, filters=filters, limit=remaining))
        except Exception as exc:
            attempts.append({"query": variant, "status": "invalid", "item_count": 0})
            failures.append(type(exc).__name__)
            continue
        result_items = [dict(item) for item in result.get("items") or [] if isinstance(item, Mapping)]
        accepted_items = [
            item for item in result_items if _archive_item_matches_query_variant(item, variant)
        ]
        attempts.append(
            {
                "query": variant,
                "status": str(result.get("status") or ("ok" if result_items else "insufficient_evidence")),
                "item_count": len(result_items),
                "accepted_count": len(accepted_items),
            }
        )
        for item in accepted_items:
            key = _archive_item_identity(item)
            if key in seen:
                continue
            seen.add(key)
            item.setdefault("matched_query_variant", variant)
            items.append(item)
            if len(items) >= limit:
                break

    if items:
        status = "ok"
        message = "Telegram archive posts matched deterministic query variants."
    elif failures and len(failures) == len(attempts):
        status = "invalid"
        message = f"Archive search failed for all query variants: {', '.join(_unique(failures)[:3])}."
    else:
        status = "insufficient_evidence"
        message = "No retained Telegram archive evidence matched deterministic query variants."
    return {
        "status": status,
        "query": query,
        "query_variants": query_variants,
        "attempted_queries": attempts,
        "filters": filters,
        "project_name_hint": project_name,
        "items": items[:limit],
        "retrieval_mode": "sqlite_fts_archive_query_planner",
        "message": message,
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
) -> dict[str, Any]:
    if len(tool_calls) >= budget.max_tool_calls or not hasattr(facade, "search_intelligence_items"):
        return {"status": "skipped", "query": query, "items": [], "message": "Curated search skipped by planner limit."}
    filters = {"week_label": week_label} if week_label else {}
    tool_calls.append({"name": "search_intelligence_items", "arguments": {"query": query, "filters": filters, "limit": limit}})
    try:
        return dict(facade.search_intelligence_items(query, filters=filters, limit=limit))
    except Exception as exc:
        return {"status": "invalid", "query": query, "items": [], "message": f"Curated search failed: {type(exc).__name__}."}


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


def _archive_evidence(result: Mapping[str, Any], *, max_items: int) -> dict[str, Any]:
    items = [dict(item) for item in result.get("items") or [] if isinstance(item, Mapping)][:max_items]
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
        "query_variants": _strings(result.get("query_variants")),
        "attempted_queries": [dict(item) for item in result.get("attempted_queries") or [] if isinstance(item, Mapping)],
        "source_refs": source_refs,
        "items": items,
    }


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
        "direct_implication": "Apply this to the named project after checking the cited evidence and drafting an explicit action.",
        "weak_watch": "Watch the signal, but do not turn it into project work yet.",
        "learning_relevance": "Study the source as background; direct project implication is not established.",
        "no_match": "Ignore for project planning unless new evidence appears.",
        "ambiguous_project": "Choose the target project before converting this research into an action.",
    }
    return {
        "status": str(context.get("status") or "ok"),
        "project_name": context.get("project_name"),
        "candidate_projects": list(context.get("candidate_projects") or []),
        "relevance_label": label,
        "confidence": _confidence(label),
        "descriptor_fields_used": _strings(context.get("descriptor_fields_used")),
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
        ignore.append("Do not apply this to active project work from the current evidence.")
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
) -> list[str]:
    unknowns: list[str] = []
    if not archive_evidence.get("items"):
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
) -> str:
    archive_items = [item for item in archive_evidence.get("items") or [] if isinstance(item, Mapping)]
    linked_items = [item for item in linked_evidence.get("items") or [] if isinstance(item, Mapping)]
    label = str(project_fit.get("relevance_label") or "no_match")
    gate_status = str(answer_gate.get("status") or "")
    gate_reason = str(answer_gate.get("reason") or "")
    if gate_status == "needs_external_verification":
        return (
            "This question requires external verification before a current claim or recommendation. "
            "The local Telegram archive can be used only as discovery context; live/current verification was not approved or run."
        )
    if not bool(answer_gate.get("allow_answer", True)):
        if gate_reason == "unsupported_project_state_claim":
            return (
                "I found at most related local material, but not sufficient cited proof for the requested completed/current project state. "
                "This is insufficient_evidence, so I will not claim it happened."
            )
        return "I do not have enough cited local evidence to answer this reliably."
    if not archive_items and not linked_items:
        return "I do not have enough local archive or approved linked-source evidence to answer this reliably."
    first_archive = _short(archive_items[0].get("snippet") or archive_items[0].get("content") or "", 220) if archive_items else ""
    first_linked = _short(linked_items[0].get("text_excerpt") or linked_items[0].get("redacted_failure_reason") or "", 220) if linked_items else ""
    pieces = ["The local research path found grounded evidence."]
    if first_archive:
        pieces.append(f"Archive signal: {first_archive}")
    if first_linked:
        pieces.append(f"Linked-source signal: {first_linked}")
    pieces.append(f"Project routing is `{label}`.")
    if unknowns:
        pieces.append("Do not treat this as fully current until these gaps are cleared: " + "; ".join(unknowns[:3]) + ".")
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
