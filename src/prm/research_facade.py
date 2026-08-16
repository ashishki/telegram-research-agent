"""Intent-scoped facade adapters for the PRM application boundary."""

from __future__ import annotations

from typing import Any, Mapping

from assistant.archive_relevance import canonical_query_variants, rank_archive_items
from assistant.pi_facade import PersonalIntelligenceFacade
from config.settings import Settings


class ArchiveScopedResearchFacade:
    """Expose archive/curated reads without implicit project selection.

    ``assistant.memory_research`` checks for ``analyze_project_context`` before
    invoking project routing. This intentionally narrow adapter does not expose
    that method, so an archive lookup cannot silently become a project decision.

    Phrase-rich technical queries are resolved through a bounded candidate pool
    across aliases before the legacy planner applies its display limit. This
    keeps a broad Agent Operations hit from occupying the whole result set before
    an ``agent evaluation`` alias is tried.
    """

    def __init__(self, delegate: PersonalIntelligenceFacade, *, question: str) -> None:
        self._delegate = delegate
        self._settings = delegate._settings  # compatibility with saved-memory reads
        self._question = " ".join(str(question or "").split())

    def search_telegram_archive(
        self,
        query: str,
        filters: Mapping[str, Any] | None = None,
        limit: int = 5,
    ) -> dict:
        variants = canonical_query_variants(self._question, max_variants=6)
        if len(variants) <= 1:
            return self._delegate.search_telegram_archive(query, filters=filters, limit=limit)

        bounded_limit = max(1, min(int(limit or 5), 10))
        per_variant_limit = max(12, min(24, bounded_limit * 4))
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        attempts: list[dict[str, Any]] = []
        for variant in variants:
            try:
                result = dict(
                    self._delegate.search_telegram_archive(
                        variant,
                        filters=filters,
                        limit=per_variant_limit,
                    )
                )
            except Exception as exc:
                attempts.append({"query": variant, "status": "invalid", "error_type": type(exc).__name__})
                continue
            rows = [dict(item) for item in result.get("items") or [] if isinstance(item, Mapping)]
            attempts.append({"query": variant, "status": str(result.get("status") or "unknown"), "item_count": len(rows)})
            for item in rows:
                identity = _archive_identity(item)
                if not identity or identity in seen:
                    continue
                seen.add(identity)
                item.setdefault("matched_query_variant", variant)
                candidates.append(item)

        ranked = rank_archive_items(self._question, candidates)
        selected = [item for item in ranked if item.get("relevance_label") != "unrelated"][:bounded_limit]
        return {
            "status": "ok" if selected else "insufficient_evidence",
            "query": query,
            "query_variants": variants,
            "attempted_queries": attempts,
            "items": selected,
            "retrieval_mode": "intent_phrase_candidate_pool",
            "message": (
                "Archive candidates were pooled across phrase-preserving aliases and reranked by directness."
                if selected
                else "No direct, partial or adjacent archive evidence matched the phrase-preserving aliases."
            ),
        }

    def search_intelligence_items(
        self,
        query: str,
        filters: Mapping[str, Any] | None = None,
        limit: int = 5,
    ) -> dict:
        return self._delegate.search_intelligence_items(query, filters=filters, limit=limit)


def build_research_facade(
    *,
    settings: Settings,
    question: str,
    project_context_required: bool,
) -> PersonalIntelligenceFacade | ArchiveScopedResearchFacade:
    delegate = PersonalIntelligenceFacade(settings=settings)
    if project_context_required:
        return delegate
    return ArchiveScopedResearchFacade(delegate, question=question)


def _archive_identity(item: Mapping[str, Any]) -> str:
    for key in (
        "archive_document_id",
        "post_archive_document_id",
        "source_url",
        "telegram_url",
        "message_url",
        "content_hash",
        "post_id",
    ):
        value = str(item.get(key) or "").strip()
        if value:
            return f"{key}:{value}"
    return ""
