"""Privacy-safe direct/partial/adjacent relevance classification.

This module is deterministic and intentionally small.  It does not call a
provider or a vector service; it adds an explicit directness feature on top of
retrieval so broad Agent Operations material cannot masquerade as an exact
``agent evals`` result.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё][0-9A-Za-zА-Яа-яЁё_+-]{1,}")

_AGENT_EVAL_ALIASES = (
    "agent evals",
    "agent eval",
    "agent evaluation",
    "agent evaluations",
    "evaluation of agents",
    "evaluation of llm agents",
    "llm agent evaluation",
    "evals агентов",
    "оценка агентов",
    "оценивание агентов",
)
_AGENT_TERMS = ("agent", "agents", "agentic", "агент", "агентов", "агента", "агентных")
_EVAL_TERMS = (
    "eval",
    "evals",
    "evaluation",
    "evaluations",
    "benchmark",
    "benchmarks",
    "regression",
    "groundedness",
    "task success",
    "tool-call correctness",
    "tool call correctness",
    "judge calibration",
    "gold label",
    "gold labels",
    "оценка",
    "оценивание",
    "бенчмарк",
    "регресс",
)
_ADJACENT_AGENT_TERMS = (
    "agent operations",
    "agentops",
    "agent ops",
    "agent reliability",
    "agent runtime",
    "access control",
    "audit trail",
    "операции агентов",
    "доступ агента",
    "аудит агента",
)
_QUERY_STOPWORDS = {
    "что", "есть", "было", "моем", "моём", "архиве", "архива", "про", "какие", "материалы",
    "из", "этого", "реально", "применимо", "сейчас", "найди", "покажи", "мне", "мой", "для",
    "what", "in", "my", "archive", "about", "from", "this", "now", "apply", "applicable", "find",
}
_LABEL_WEIGHT = {"direct": 4, "partial": 3, "adjacent": 2, "unrelated": 1}
_PROMOTION_MARKERS = (
    "промокод", "скидк", "регистрац", "вебинар", "эфир", "спикер", "ведущие", "курс",
    "promo code", "discount", "register", "webinar", "speakers",
)
_MODEL_COMPARISON_MARKERS = (
    "vs gemini", "vs gpt", "vs claude", "vs kimi", "сравнени", "model comparison",
)
_PRACTICE_MARKERS = (
    "harness", "fixture", "gold label", "tool-call correctness", "tool call correctness",
    "task success", "groundedness", "judge calibration", "quality gate", "regression",
    "тестовый набор", "регресс", "корректность вызова", "успешност задачи", "калибров",
)
_BENCHMARK_MARKERS = ("benchmark", "бенчмарк", "качество", "стоимост", "скорост", "error analysis", "анализ ошибок")


@dataclass(frozen=True, slots=True)
class RelevanceDecision:
    label: str
    score: float
    reason: str
    matched_terms: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "relevance_label": self.label,
            "directness_score": round(self.score, 4),
            "relevance_reason": self.reason,
            "matched_relevance_terms": list(self.matched_terms),
        }


@dataclass(frozen=True, slots=True)
class SourceRoleDecision:
    role: str
    supports_action: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_role": self.role,
            "supports_action": self.supports_action,
            "source_role_reason": self.reason,
        }


def canonical_query_variants(question: str, *, max_variants: int = 8) -> list[str]:
    """Return bounded phrase-preserving aliases for the detected topic."""

    lowered = _clean(question).casefold()
    if _is_agent_eval_query(lowered):
        variants = [
            "agent evals",
            "agent evaluation",
            "evaluation of agents",
            "LLM agent evaluation",
            "agent benchmark",
            "agent task success",
            "agent tool-call correctness",
            "agent groundedness",
        ]
        return variants[: max(1, min(int(max_variants or 8), len(variants)))]
    topic = " ".join(_significant_tokens(question)[:8])
    return [topic] if topic else []


def classify_archive_relevance(question: str, item: Mapping[str, Any]) -> RelevanceDecision:
    text = _evidence_text(item)
    lowered = text.casefold()
    question_lowered = _clean(question).casefold()
    variant = _clean(item.get("matched_query_variant")).casefold()

    if _is_agent_eval_query(question_lowered):
        exact = [alias for alias in _AGENT_EVAL_ALIASES if alias in lowered]
        agent_hits = _matching_markers(lowered, _AGENT_TERMS)
        eval_hits = _matching_markers(lowered, _EVAL_TERMS)
        adjacent_hits = _matching_markers(lowered, _ADJACENT_AGENT_TERMS)
        variant_exact = any(alias in variant for alias in _AGENT_EVAL_ALIASES)
        if exact:
            return RelevanceDecision("direct", 0.98, "exact_agent_eval_phrase", tuple(exact[:4]))
        if agent_hits and eval_hits:
            score = 0.86 + (0.04 if variant_exact else 0.0)
            return RelevanceDecision(
                "direct",
                min(0.94, score),
                "agent_and_evaluation_concepts_present",
                tuple([*agent_hits[:2], *eval_hits[:3]]),
            )
        if eval_hits:
            return RelevanceDecision(
                "partial",
                0.62 if variant_exact else 0.56,
                "evaluation_concept_without_explicit_agent_scope",
                tuple(eval_hits[:4]),
            )
        if adjacent_hits or agent_hits:
            return RelevanceDecision(
                "adjacent",
                0.34,
                "agent_context_without_evaluation_practice",
                tuple([*adjacent_hits[:3], *agent_hits[:2]]),
            )
        return RelevanceDecision("unrelated", 0.05, "no_agent_eval_support", ())

    query_terms = _significant_tokens(question)
    evidence_terms = set(_tokens(lowered))
    if not query_terms:
        return RelevanceDecision("unrelated", 0.0, "empty_topic", ())
    matched = [term for term in query_terms if term in evidence_terms or (len(term) > 4 and term in lowered)]
    coverage = len(matched) / max(1, len(set(query_terms)))
    exact_phrase = " ".join(query_terms[:4])
    if len(query_terms) >= 2 and exact_phrase and exact_phrase in lowered:
        return RelevanceDecision("direct", 0.92, "exact_topic_phrase", tuple(matched))
    if coverage >= 0.65:
        return RelevanceDecision("direct", min(0.9, 0.55 + coverage * 0.4), "high_topic_coverage", tuple(matched))
    if coverage >= 0.35:
        return RelevanceDecision("partial", 0.35 + coverage * 0.35, "partial_topic_coverage", tuple(matched))
    if matched:
        return RelevanceDecision("adjacent", 0.18 + coverage * 0.25, "weak_topic_overlap", tuple(matched))
    return RelevanceDecision("unrelated", 0.02, "no_topic_overlap", ())


def rank_archive_items(question: str, items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[tuple[int, dict[str, Any]]] = []
    for index, item in enumerate(items):
        decision = classify_archive_relevance(question, item)
        role = classify_archive_source_role(item)
        label = _effective_relevance_label(decision.label, role)
        row = {
            **dict(item),
            **decision.to_dict(),
            **role.to_dict(),
            "relevance_label": label,
            "original_candidate_position": index + 1,
        }
        enriched.append((index, row))
    enriched.sort(key=lambda pair: _sort_key(pair[1], original_index=pair[0]), reverse=True)
    return [{**row, "display_rank": rank} for rank, (_index, row) in enumerate(enriched, start=1)]


def classify_archive_source_role(item: Mapping[str, Any]) -> SourceRoleDecision:
    """Classify whether a post can support an actionable archive conclusion."""

    text = _evidence_text(item).casefold()
    if _contains_any(text, _PROMOTION_MARKERS):
        return SourceRoleDecision("announcement_or_promotion", False, "promotional_or_event_announcement")
    if _contains_any(text, _MODEL_COMPARISON_MARKERS):
        return SourceRoleDecision("model_comparison", False, "model_comparison_is_not_agent_eval_practice")
    if _contains_any(text, _PRACTICE_MARKERS):
        return SourceRoleDecision("practical_evidence", True, "concrete_evaluation_practice")
    if _contains_any(text, _BENCHMARK_MARKERS):
        return SourceRoleDecision("benchmark_context", False, "benchmark_context_without_replayable_practice")
    return SourceRoleDecision("commentary", False, "topic_mention_without_actionable_practice")


def _effective_relevance_label(label: str, role: SourceRoleDecision) -> str:
    if label != "direct":
        return label
    if role.role == "practical_evidence":
        return "direct"
    if role.role == "benchmark_context":
        return "partial"
    return "adjacent"


def _sort_key(item: Mapping[str, Any], *, original_index: int) -> tuple[float, ...]:
    label = str(item.get("relevance_label") or "unrelated")
    directness = float(item.get("directness_score") or 0.0)
    semantic = float(item.get("semantic_score") or 0.0)
    fusion = float(item.get("fusion_score") or 0.0)
    try:
        lexical = -float(item.get("rank") or 0.0)
    except (TypeError, ValueError):
        lexical = 0.0
    return (
        float(_LABEL_WEIGHT.get(label, 0)),
        directness,
        fusion,
        semantic,
        lexical,
        -float(original_index),
    )


def _is_agent_eval_query(lowered: str) -> bool:
    if any(alias in lowered for alias in _AGENT_EVAL_ALIASES):
        return True
    has_agent = bool(_matching_markers(lowered, _AGENT_TERMS))
    has_eval = bool(_matching_markers(lowered, _EVAL_TERMS))
    return has_agent and has_eval


def _evidence_text(item: Mapping[str, Any]) -> str:
    return _clean(
        " ".join(
            str(item.get(key) or "")
            for key in (
                "title",
                "snippet",
                "summary",
                "content",
                "text",
                "support_span",
                "channel_username",
            )
        )
    )


def _matching_markers(value: str, markers: Sequence[str]) -> list[str]:
    tokens = set(_tokens(value))
    result: list[str] = []
    for marker in markers:
        clean = marker.casefold()
        if " " in clean or "-" in clean:
            if clean in value:
                result.append(marker)
        elif clean in tokens or any(token.startswith(clean) for token in tokens):
            result.append(marker)
    return _unique(result)


def _contains_any(value: str, markers: Sequence[str]) -> bool:
    return any(marker in value for marker in markers)


def _significant_tokens(value: object) -> list[str]:
    return [token for token in _tokens(value) if token not in _QUERY_STOPWORDS][:12]


def _tokens(value: object) -> list[str]:
    return [match.group(0).casefold().strip("_-+") for match in _TOKEN_RE.finditer(str(value or ""))]


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _unique(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
