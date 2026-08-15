"""Intent-specific local archive retrieval policy for PRM-QA."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Mapping


RETRIEVAL_POLICY_SCHEMA_VERSION = "prm_retrieval_policy.v1"

_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_+-]{2,}")
_STOPWORDS = {
    "что",
    "как",
    "где",
    "когда",
    "какие",
    "какой",
    "какая",
    "можно",
    "нужно",
    "мне",
    "мой",
    "моего",
    "моему",
    "про",
    "для",
    "после",
    "этих",
    "материалов",
    "найди",
    "сделать",
    "from",
    "with",
    "what",
    "which",
    "about",
    "after",
    "find",
    "project",
}


@dataclass(frozen=True)
class RetrievalPolicy:
    schema_version: str
    policy_id: str
    job_type: str
    vector_policy: str
    query_strategy: str
    candidate_limit: int
    collapse_duplicates: bool
    require_project_name: bool
    freshness_first: bool
    explanation: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def infer_job_type(question: str, *, project_name: str = "", requested_mode: str = "") -> str:
    lowered = str(question or "").casefold()
    mode = str(requested_mode or "").casefold()
    if _has_current_fact_marker(lowered):
        return "current_fact"
    if _has_reaction_marker(lowered):
        return "reacted_post_recall"
    if _has_saved_memory_marker(lowered):
        return "saved_knowledge_recall"
    if mode == "brief" or _has_writer_marker(lowered):
        return "writer_editor"
    if _has_learning_marker(lowered):
        return "learning_experiment"
    if _has_project_decision_marker(lowered) or (str(project_name or "").strip() and _has_decision_marker(lowered)):
        return "named_project_decision" if str(project_name or "").strip() else "ambiguous_project"
    if _has_timeline_marker(lowered):
        return "timeline_freshness"
    if _has_comparison_marker(lowered):
        return "comparison"
    if _has_case_marker(lowered):
        return "case_study"
    if _has_exact_marker(lowered):
        return "exact_known_item"
    return "semantic_topic"


def select_retrieval_policy(
    question: str,
    *,
    job_type: str | None = None,
    project_name: str = "",
    requested_mode: str = "",
) -> RetrievalPolicy:
    clean_job = str(job_type or infer_job_type(question, project_name=project_name, requested_mode=requested_mode)).strip()
    if clean_job == "exact_known_item":
        return _policy(clean_job, "strict_phrase_then_fts", "fallback_on_fts_miss", 8, False, False, False)
    if clean_job == "timeline_freshness":
        return _policy(clean_job, "date_constrained_chronological", "fallback_on_fts_miss", 12, True, False, True)
    if clean_job == "reacted_post_recall":
        return _policy(clean_job, "reaction_filter_first", "fallback_on_fts_miss", 10, True, False, False)
    if clean_job == "saved_knowledge_recall":
        return _policy(clean_job, "saved_object_first", "fallback_on_fts_miss", 10, True, False, False)
    if clean_job == "comparison":
        return _policy(clean_job, "subtopic_decomposition", "fallback_on_fts_miss", 16, True, False, False)
    if clean_job == "case_study":
        return _policy(clean_job, "case_pool_diversity", "fallback_on_fts_miss", 16, True, False, False)
    if clean_job == "named_project_decision":
        return _policy(clean_job, "project_snapshot_plus_archive", "fallback_on_fts_miss", 14, True, True, False)
    if clean_job == "ambiguous_project":
        return _policy(clean_job, "clarify_project_before_retrieval", "fallback_on_fts_miss", 0, False, True, False)
    if clean_job == "current_fact":
        return _policy(clean_job, "archive_context_then_verification_boundary", "fallback_on_fts_miss", 8, True, False, True)
    if clean_job in {"writer_editor", "learning_experiment", "semantic_topic"}:
        return _policy(clean_job, "bounded_query_rewrite", "fallback_on_fts_miss", 12, True, False, False)
    if clean_job in {"no_answer", "distractor_hard_negative"}:
        return _policy(clean_job, "strict_fts_then_fail_closed", "fallback_on_fts_miss", 8, True, False, False)
    return _policy("semantic_topic", "fts_dense_fusion", "always", 12, True, False, False)


def build_query_rewrites(question: str, *, job_type: str = "semantic_topic", max_variants: int = 4) -> list[str]:
    """Create bounded generic rewrites without hand-authored domain dictionaries."""

    original = _single_line(question)
    if not original:
        return []
    tokens = _keywords(original)
    variants = [original]
    if tokens:
        variants.append(" ".join(tokens[:8]))
    if job_type == "comparison":
        for part in re.split(r"\bvs\.?\b|\bversus\b|\bили\b|\bпротив\b", original, flags=re.IGNORECASE):
            clean = " ".join(_keywords(part)[:6])
            if clean:
                variants.append(clean)
    if job_type == "timeline_freshness":
        variants.append(" ".join([*tokens[:6], "изменилось", "динамика"]).strip())
    if job_type == "case_study":
        variants.append(" ".join([*tokens[:6], "case", "пример", "практика"]).strip())
    return _unique([variant for variant in variants if variant])[: max(1, min(int(max_variants or 4), 6))]


def _policy(
    job_type: str,
    strategy: str,
    vector_policy: str,
    candidate_limit: int,
    collapse_duplicates: bool,
    require_project_name: bool,
    freshness_first: bool,
) -> RetrievalPolicy:
    return RetrievalPolicy(
        schema_version=RETRIEVAL_POLICY_SCHEMA_VERSION,
        policy_id=f"{job_type}.{strategy}",
        job_type=job_type,
        vector_policy=vector_policy,
        query_strategy=strategy,
        candidate_limit=max(0, int(candidate_limit)),
        collapse_duplicates=bool(collapse_duplicates),
        require_project_name=bool(require_project_name),
        freshness_first=bool(freshness_first),
        explanation="Selected from deterministic PRM-QA job-type policy.",
    )


def _keywords(value: str) -> list[str]:
    tokens = []
    for token in _TOKEN_RE.findall(value):
        lowered = token.casefold()
        if lowered in _STOPWORDS:
            continue
        if lowered not in tokens:
            tokens.append(lowered)
    return tokens


def _single_line(value: object) -> str:
    return " ".join(str(value or "").split())


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        clean = _single_line(value)
        if clean and clean not in result:
            result.append(clean)
    return result


def _has_current_fact_marker(lowered: str) -> bool:
    return any(marker in lowered for marker in ("сейчас", "сегодня", "актуаль", "latest", "current", "now", "today"))


def _has_reaction_marker(lowered: str) -> bool:
    return any(marker in lowered for marker in ("реакц", "лайк", "liked", "reaction", "отмечал"))


def _has_saved_memory_marker(lowered: str) -> bool:
    return any(marker in lowered for marker in ("сохран", "saved", "заметк", "watchlist", "наблюд"))


def _has_writer_marker(lowered: str) -> bool:
    return any(marker in lowered for marker in ("бриф", "редактор", "тезис", "пост", "стать", "writer", "editor"))


def _has_learning_marker(lowered: str) -> bool:
    return any(marker in lowered for marker in ("объясни", "разобраться", "научи", "эксперимент", "experiment", "learn"))


def _has_project_decision_marker(lowered: str) -> bool:
    project_markers = ("моего проекта", "моему проекту", "мой проект", "для проекта", "с проектом", "project")
    return any(marker in lowered for marker in project_markers) and _has_decision_marker(lowered)


def _has_decision_marker(lowered: str) -> bool:
    decision_markers = ("что делать", "примен", "вывод", "реш", "recommend", "next action", "action")
    return any(marker in lowered for marker in decision_markers)


def _has_timeline_marker(lowered: str) -> bool:
    return any(marker in lowered for marker in ("изменилось", "динамик", "раньше", "позже", "timeline", "over time"))


def _has_comparison_marker(lowered: str) -> bool:
    return any(marker in lowered for marker in ("сравни", "compare", "vs", "versus", "подход"))


def _has_case_marker(lowered: str) -> bool:
    return any(marker in lowered for marker in ("кейс", "пример", "case", "practice", "практик"))


def _has_exact_marker(lowered: str) -> bool:
    return any(marker in lowered for marker in ("найди пост", "найди материал", "find the post", "source", "ссылк"))


def policy_trace(policy: RetrievalPolicy, *, extra: Mapping[str, object] | None = None) -> dict[str, object]:
    payload = policy.to_dict()
    if extra:
        payload["extra"] = {str(key): value for key, value in extra.items()}
    return payload
