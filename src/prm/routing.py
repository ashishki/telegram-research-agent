"""Intent-first deterministic router for the active PRM interface.

The router deliberately separates a user's primary job from modifiers such as
project mapping and external freshness.  In particular, archive-scoped
questions are not promoted to current-fact verification merely because they
contain the word ``сейчас``/``now``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Iterable

from assistant.project_context import load_project_descriptors
from config.settings import PROJECT_ROOT
from prm.contracts import PrimaryIntent, RequestMode, ResponseContractId

_ARCHIVE_SCOPE_MARKERS = (
    "в архиве",
    "мой архив",
    "моем архиве",
    "моём архиве",
    "из архива",
    "по архиву",
    "telegram-архив",
    "telegram архив",
    "сохранённых материалов",
    "сохраненных материалов",
    "сохранённые материалы",
    "сохраненные материалы",
    "что у меня было",
    "my archive",
    "in my archive",
    "from my archive",
    "saved materials",
    "telegram archive",
)
_ARCHIVE_LOOKUP_MARKERS = (
    "что есть",
    "что было",
    "найди",
    "покажи",
    "материал",
    "пост",
    "source",
    "find",
    "show",
)
_SYNTHESIS_MARKERS = (
    "что говорит",
    "что известно из",
    "суммир",
    "обобщ",
    "разбери",
    "synthesi",
    "summar",
)
_APPLICABILITY_MARKERS = (
    "применим",
    "подходит",
    "использовать сейчас",
    "что из этого реально",
    "что мне с этим делать",
    "что с этим делать",
    "что делать",
    "практичес",
    "какие практики",
    "какую практику",
    "стоит применить",
    "что применить",
    "как внедрить",
    "внедрить",
    "применить",
    "apply",
    "applicable",
    "use now",
    "what can i use",
)
_DECISION_MARKERS = (
    "стоит ли",
    "выбери",
    "выбор",
    "приоритиз",
    "добавить в backlog",
    "добавить в бэклог",
    "изменить backlog",
    "принять решение",
    "какое решение",
    "recommend a decision",
    "should i",
    "prioritize",
    "add to backlog",
)
_CURRENT_MARKERS = (
    "что сейчас известно",
    "самое новое",
    "последняя версия",
    "текущая цена",
    "актуально сегодня",
    "на сегодня",
    "latest",
    "current fact",
    "current price",
    "today",
)
_EXPLICIT_EXTERNAL_MARKERS = (
    "в интернете",
    "во внешних источниках",
    "внешний benchmark",
    "внешний бенчмарк",
    "официальный источник",
    "проверь актуальность",
    "проверь сейчас",
    "live web",
    "external source",
    "official source",
    "verify online",
    "new external benchmark",
)
_BRIEF_MARKERS = (
    "бриф",
    "редактор",
    "для поста",
    "для статьи",
    "собери материал",
    "editor brief",
    "source packet",
    "draft outline",
)
_CHAT_MARKERS = (
    "перепиши",
    "придумай",
    "отредактируй",
    "поговори",
    "без источников",
    "rewrite",
    "brainstorm",
    "freeform",
)
_MEMORY_ACTION_MARKERS = (
    "сохрани",
    "запомни",
    "свяжи с проектом",
    "создай действие",
    "создай эксперимент",
    "следи за",
    "save this",
    "remember this",
    "create action",
    "create experiment",
)
_PROJECT_MARKERS = (
    "мой проект",
    "моему проекту",
    "моего проекта",
    "к моему проекту",
    "к проекту",
    "для проекта",
    "применить к",
    "backlog проекта",
    "бэклог проекта",
    "репозитор",
    "project",
    "repo",
)

_TOPIC_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_+.-]{1,}")
_TOPIC_STOPWORDS = {
    "а", "архив", "архива", "архиве", "без", "было", "бы", "в", "вам", "ваш", "где",
    "для", "есть", "из", "или", "как", "какие", "какой", "материал", "материалы", "мне",
    "мой", "моего", "моем", "моём", "моему", "на", "найди", "не", "покажи", "по", "про",
    "реально", "сейчас", "сохраненных", "сохранённых", "сохраненные", "сохранённые", "тогда",
    "у", "что", "этого", "этом", "этих", "это", "применимо", "применить", "подходит",
    "about", "and", "archive", "current", "find", "for", "from", "in", "latest", "materials",
    "my", "now", "of", "project", "repo", "saved", "show", "the", "this", "today", "use", "what",
    "which", "with",
}


@dataclass(frozen=True, slots=True)
class RouteDecision:
    mode: str
    reason: str
    confidence: float
    project_name: str = ""
    retrieval_query: str = ""
    clarification_required: bool = False
    primary_intent: PrimaryIntent = "archive_synthesis"
    response_contract_id: ResponseContractId = "archive_research.v2"
    archive_scope: bool = False
    project_context_required: bool = False
    external_verification_required: bool = False
    decision_requested: bool = False
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def decide_route(query: str, *, requested_mode: RequestMode = "auto", explicit_project: str = "") -> RouteDecision:
    clean = " ".join(str(query or "").split())
    lowered = clean.casefold()
    project = explicit_project.strip() or find_named_project(clean)
    archive_scope = _contains_any(lowered, _ARCHIVE_SCOPE_MARKERS)
    applicability = _contains_any(lowered, _APPLICABILITY_MARKERS)
    decision_requested = _contains_any(lowered, _DECISION_MARKERS)
    project_requested = bool(project) or _contains_any(lowered, _PROJECT_MARKERS)
    current_required = _requires_current_fact_verification(lowered, archive_scope=archive_scope)

    if not clean:
        return RouteDecision(
            "clarify",
            "empty_query",
            1.0,
            clarification_required=True,
            primary_intent="archive_lookup",
            response_contract_id="archive_lookup.v2",
            reason_codes=("empty_query",),
        )

    if requested_mode == "chat":
        return _decision(
            mode="chat",
            reason="explicit_mode",
            confidence=1.0,
            project=project,
            retrieval_query="",
            intent="freeform_chat",
            contract="chat.v1",
            archive_scope=archive_scope,
            project_context_required=False,
            current_required=False,
            decision_requested=False,
            reason_codes=("explicit_chat_mode",),
        )
    if requested_mode == "brief":
        return _decision(
            mode="brief",
            reason="explicit_mode",
            confidence=1.0,
            project=project,
            retrieval_query=_retrieval_query(clean),
            intent="writer_brief",
            contract="brief.v1",
            archive_scope=archive_scope,
            project_context_required=bool(project),
            current_required=current_required,
            decision_requested=False,
            reason_codes=("explicit_brief_mode",),
        )

    if decision_requested and project_requested and not project:
        return RouteDecision(
            "project_clarify",
            "project_identity_required",
            0.99,
            retrieval_query=_retrieval_query(clean),
            clarification_required=True,
            primary_intent="decision_support",
            response_contract_id="decision_support.v2",
            archive_scope=archive_scope,
            project_context_required=True,
            external_verification_required=current_required,
            decision_requested=True,
            reason_codes=("decision_requested", "project_identity_missing"),
        )

    if requested_mode == "research":
        intent, contract = _research_intent(
            lowered,
            archive_scope=archive_scope,
            applicability=applicability,
            decision_requested=decision_requested,
            project=project,
            current_required=current_required,
        )
        return _decision(
            mode="research",
            reason="explicit_mode",
            confidence=1.0,
            project=project,
            retrieval_query=_retrieval_query(clean),
            intent=intent,
            contract=contract,
            archive_scope=archive_scope,
            project_context_required=intent in {"project_mapping", "decision_support"},
            current_required=current_required,
            decision_requested=decision_requested,
            reason_codes=("explicit_research_mode", intent),
        )

    if _contains_any(lowered, _MEMORY_ACTION_MARKERS):
        return _decision(
            mode="research",
            reason="memory_action_request",
            confidence=0.98,
            project=project,
            retrieval_query=_retrieval_query(clean),
            intent="memory_action",
            contract="archive_research.v2",
            archive_scope=archive_scope,
            project_context_required=bool(project),
            current_required=False,
            decision_requested=False,
            reason_codes=("explicit_memory_action",),
        )
    if _contains_any(lowered, _BRIEF_MARKERS):
        return _decision(
            mode="brief",
            reason="editorial_request",
            confidence=0.94,
            project=project,
            retrieval_query=_retrieval_query(clean),
            intent="writer_brief",
            contract="brief.v1",
            archive_scope=archive_scope,
            project_context_required=bool(project),
            current_required=current_required,
            decision_requested=False,
            reason_codes=("writer_marker",),
        )
    if _contains_any(lowered, _CHAT_MARKERS):
        return _decision(
            mode="chat",
            reason="freeform_request",
            confidence=0.82,
            project=project,
            retrieval_query="",
            intent="freeform_chat",
            contract="chat.v1",
            archive_scope=archive_scope,
            project_context_required=False,
            current_required=False,
            decision_requested=False,
            reason_codes=("freeform_marker",),
        )
    if decision_requested and project:
        return _decision(
            mode="research",
            reason="explicit_project_decision",
            confidence=0.98,
            project=project,
            retrieval_query=_retrieval_query(clean),
            intent="decision_support",
            contract="decision_support.v2",
            archive_scope=archive_scope,
            project_context_required=True,
            current_required=current_required,
            decision_requested=True,
            reason_codes=("decision_requested", "named_project"),
        )
    if project and applicability:
        return _decision(
            mode="research",
            reason="explicit_project_mapping",
            confidence=0.96,
            project=project,
            retrieval_query=_retrieval_query(clean),
            intent="project_mapping",
            contract="project_mapping.v2",
            archive_scope=archive_scope,
            project_context_required=True,
            current_required=current_required,
            decision_requested=False,
            reason_codes=("applicability_requested", "named_project"),
        )
    if current_required:
        return _decision(
            mode="research",
            reason="current_fact_verification",
            confidence=0.97,
            project=project,
            retrieval_query=_retrieval_query(clean),
            intent="current_fact_verification",
            contract="current_fact.v2",
            archive_scope=archive_scope,
            project_context_required=bool(project),
            current_required=True,
            decision_requested=False,
            reason_codes=("current_external_fact",),
        )
    if archive_scope and applicability:
        return _decision(
            mode="research",
            reason="archive_to_action",
            confidence=0.97,
            project="",
            retrieval_query=_retrieval_query(clean),
            intent="archive_to_action",
            contract="archive_research.v2",
            archive_scope=True,
            project_context_required=False,
            current_required=False,
            decision_requested=False,
            reason_codes=("archive_scope", "applicability_requested", "no_implicit_project"),
        )
    if archive_scope and _contains_any(lowered, _SYNTHESIS_MARKERS):
        return _decision(
            mode="research",
            reason="archive_synthesis",
            confidence=0.94,
            project="",
            retrieval_query=_retrieval_query(clean),
            intent="archive_synthesis",
            contract="archive_research.v2",
            archive_scope=True,
            project_context_required=False,
            current_required=False,
            decision_requested=False,
            reason_codes=("archive_scope", "synthesis_requested", "no_implicit_project"),
        )
    if archive_scope:
        return _decision(
            mode="research",
            reason="archive_lookup",
            confidence=0.96,
            project="",
            retrieval_query=_retrieval_query(clean),
            intent="archive_lookup",
            contract="archive_lookup.v2",
            archive_scope=True,
            project_context_required=False,
            current_required=False,
            decision_requested=False,
            reason_codes=("archive_scope", "no_implicit_project"),
        )
    return _decision(
        mode="research",
        reason="safe_archive_default",
        confidence=0.76,
        project=project,
        retrieval_query=_retrieval_query(clean),
        intent="archive_synthesis",
        contract="archive_research.v2",
        archive_scope=False,
        project_context_required=False,
        current_required=False,
        decision_requested=False,
        reason_codes=("safe_archive_default",),
    )


def find_named_project(query: str) -> str:
    lowered = str(query or "").casefold()
    for name, aliases in _project_names():
        candidates = (name, *aliases)
        if any(candidate and candidate.casefold() in lowered for candidate in candidates):
            return name
    return ""


def _project_names() -> Iterable[tuple[str, tuple[str, ...]]]:
    path = Path(PROJECT_ROOT) / "src" / "config" / "projects.yaml"
    try:
        descriptors = load_project_descriptors(path)
    except (OSError, ValueError):
        descriptors = []
    for item in descriptors:
        name = str(item.get("name") or "").strip()
        aliases = tuple(str(value).strip() for value in item.get("aliases") or [] if str(value).strip())
        if name:
            yield name, aliases


def _research_intent(
    lowered: str,
    *,
    archive_scope: bool,
    applicability: bool,
    decision_requested: bool,
    project: str,
    current_required: bool,
) -> tuple[PrimaryIntent, ResponseContractId]:
    if decision_requested and project:
        return "decision_support", "decision_support.v2"
    if project and applicability:
        return "project_mapping", "project_mapping.v2"
    if current_required:
        return "current_fact_verification", "current_fact.v2"
    if archive_scope and applicability:
        return "archive_to_action", "archive_research.v2"
    if archive_scope and _contains_any(lowered, _SYNTHESIS_MARKERS):
        return "archive_synthesis", "archive_research.v2"
    if archive_scope:
        return "archive_lookup", "archive_lookup.v2"
    return "archive_synthesis", "archive_research.v2"


def _requires_current_fact_verification(lowered: str, *, archive_scope: bool) -> bool:
    explicit_external = _contains_any(lowered, _EXPLICIT_EXTERNAL_MARKERS)
    if archive_scope:
        return explicit_external
    if explicit_external:
        return True
    if _contains_any(lowered, _CURRENT_MARKERS):
        return True
    # Outside an archive scope, a standalone freshness word is meaningful, but
    # it is deliberately ignored inside archive lookup/applicability questions.
    return bool(re.search(r"\b(сейчас|актуальн\w*|today|currently|now)\b", lowered))


def _retrieval_query(query: str) -> str:
    clean = " ".join(str(query or "").split())
    lowered = clean.casefold()
    canonical = _canonical_topic_phrase(lowered)
    if canonical:
        return canonical

    selected: list[str] = []
    seen: set[str] = set()
    for raw in _TOPIC_TOKEN_RE.findall(clean):
        token = raw.casefold().strip("._-+")
        if not token or token in _TOPIC_STOPWORDS or token in seen:
            continue
        if token.startswith("применим") or token.startswith("актуальн"):
            continue
        seen.add(token)
        selected.append(_normalize_topic_token(token))
        if len(selected) >= 8:
            break
    return " ".join(selected) or clean[:240]


def _canonical_topic_phrase(lowered: str) -> str:
    if re.search(r"\bagent[\s_-]+evals?\b", lowered):
        return "agent evals"
    if re.search(r"\bagent[\s_-]+evaluations?\b", lowered):
        return "agent evaluation"
    if re.search(r"\bevaluation\s+of\s+(?:llm\s+)?agents?\b", lowered):
        return "agent evaluation"
    if re.search(r"\bevals?\s+агент\w*\b", lowered) or re.search(r"\bоцен\w*\s+агент\w*\b", lowered):
        return "agent evals"
    return ""


def _normalize_topic_token(token: str) -> str:
    return {
        "раг": "RAG",
        "rag": "RAG",
        "fts": "FTS",
        "sqlite": "SQLite",
        "llm": "LLM",
        "ai": "AI",
    }.get(token, token)


def _decision(
    *,
    mode: str,
    reason: str,
    confidence: float,
    project: str,
    retrieval_query: str,
    intent: PrimaryIntent,
    contract: ResponseContractId,
    archive_scope: bool,
    project_context_required: bool,
    current_required: bool,
    decision_requested: bool,
    reason_codes: tuple[str, ...],
) -> RouteDecision:
    return RouteDecision(
        mode=mode,
        reason=reason,
        confidence=confidence,
        project_name=project,
        retrieval_query=retrieval_query,
        primary_intent=intent,
        response_contract_id=contract,
        archive_scope=archive_scope,
        project_context_required=project_context_required,
        external_verification_required=current_required,
        decision_requested=decision_requested,
        reason_codes=reason_codes,
    )


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)
