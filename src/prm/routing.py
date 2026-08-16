"""Small deterministic router for the active PRM interface."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Iterable

from assistant.project_context import load_project_descriptors
from config.settings import PROJECT_ROOT
from prm.contracts import RequestMode

_CURRENT_MARKERS = (
    "сейчас", "актуальн", "сегодня", "последняя версия", "текущая цена",
    "current", "today", "latest version", "current price",
)
_BRIEF_MARKERS = (
    "бриф", "редактор", "для поста", "для статьи", "собери материал",
    "editor brief", "source packet", "draft outline",
)
_CHAT_MARKERS = (
    "перепиши", "придумай", "отредактируй", "поговори", "без источников",
    "rewrite", "brainstorm", "freeform",
)
_PROJECT_MARKERS = (
    "мой проект", "к проекту", "для проекта", "применить к", "репозитор",
    "project", "repo",
)


@dataclass(frozen=True, slots=True)
class RouteDecision:
    mode: str
    reason: str
    confidence: float
    project_name: str = ""
    retrieval_query: str = ""
    clarification_required: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def decide_route(query: str, *, requested_mode: RequestMode = "auto", explicit_project: str = "") -> RouteDecision:
    clean = " ".join(str(query or "").split())
    lowered = clean.casefold()
    project = explicit_project.strip() or find_named_project(clean)

    if requested_mode != "auto":
        return RouteDecision(
            mode=requested_mode,
            reason="explicit_mode",
            confidence=1.0,
            project_name=project,
            retrieval_query=_retrieval_query(clean),
        )
    if not clean:
        return RouteDecision("clarify", "empty_query", 1.0, clarification_required=True)
    if any(marker in lowered for marker in _CURRENT_MARKERS):
        return RouteDecision("research", "current_fact_boundary", 0.98, project, _retrieval_query(clean))
    if _looks_like_project_decision(lowered) and not project:
        return RouteDecision("project_clarify", "project_identity_required", 0.98, clarification_required=True)
    if any(marker in lowered for marker in _BRIEF_MARKERS):
        return RouteDecision("brief", "editorial_request", 0.9, project, _retrieval_query(clean))
    if any(marker in lowered for marker in _CHAT_MARKERS):
        return RouteDecision("chat", "freeform_request", 0.75, project)
    return RouteDecision("research", "safe_archive_default", 0.7, project, _retrieval_query(clean))


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


def _looks_like_project_decision(lowered: str) -> bool:
    return any(marker in lowered for marker in _PROJECT_MARKERS) and any(
        marker in lowered for marker in ("примен", "измен", "улучш", "решен", "что сделать", "apply", "improve", "decision")
    )


def _retrieval_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_+.-]{2,}", query)
    stop = {"какие", "какой", "который", "моего", "моему", "проект", "project", "what", "which", "about", "для", "что", "как", "это", "the"}
    selected = []
    for token in tokens:
        if token.casefold() in stop or token in selected:
            continue
        selected.append(token)
        if len(selected) >= 8:
            break
    return " ".join(selected) or query[:240]
