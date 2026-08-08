"""Bounded, citation-safe context packs for local PRM research answers."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


RAG_CONTEXT_PACK_SCHEMA_VERSION = "rag_context_pack.v1"
_RAW_FIELDS = frozenset({"content", "raw_text", "raw_post_text", "telegram_text", "full_post_text", "provider_payload"})
_SOURCE_CLASSES = frozenset({"telegram_archive", "curated_memory", "linked_source", "semantic_candidate"})


class RagContextPackError(ValueError):
    """Raised when a context pack would violate the citation/privacy contract."""


def build_rag_context_pack(
    *,
    archive_evidence: Mapping[str, Any],
    curated_memory: Mapping[str, Any],
    linked_source_evidence: Mapping[str, Any],
    project_fit: Mapping[str, Any],
    semantic_candidates: Sequence[Mapping[str, Any]] = (),
    max_sources: int = 12,
    max_excerpt_chars: int = 240,
    no_answer_threshold: float = 0.60,
) -> dict[str, Any]:
    """Assemble only bounded excerpts that have a stable citation reference.

    This deliberately accepts synthetic semantic candidates for contract tests,
    but does not run semantic retrieval, embeddings, or external fetches.
    """
    clean_max_sources = max(1, min(20, int(max_sources or 1)))
    clean_excerpt_limit = max(40, min(500, int(max_excerpt_chars or 40)))
    threshold = float(no_answer_threshold)
    if not 0.0 <= threshold <= 1.0:
        raise RagContextPackError("no_answer_threshold must be between 0 and 1")

    project_label = str(project_fit.get("relevance_label") or "no_match")
    sources: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_candidates(source_class: str, candidates: Sequence[Mapping[str, Any]], *, query_variant: str = "", freshness: str = "unknown") -> None:
        for candidate in candidates:
            if len(sources) >= clean_max_sources:
                excluded.append({"source_class": source_class, "reason": "source_limit"})
                continue
            if not isinstance(candidate, Mapping):
                excluded.append({"source_class": source_class, "reason": "invalid_candidate"})
                continue
            if _RAW_FIELDS.intersection(candidate):
                excluded.append({"source_class": source_class, "reason": "raw_corpus_field_refused"})
                continue
            source_ref = _source_ref(candidate)
            if not source_ref:
                excluded.append({"source_class": source_class, "reason": "missing_citation"})
                continue
            if source_ref in seen:
                excluded.append({"source_class": source_class, "reason": "duplicate_citation"})
                continue
            excerpt = _bounded_text(candidate.get("snippet") or candidate.get("text_excerpt") or candidate.get("summary"), clean_excerpt_limit)
            if not excerpt:
                excluded.append({"source_class": source_class, "reason": "missing_bounded_excerpt"})
                continue
            seen.add(source_ref)
            sources.append({
                "source_ref": source_ref,
                "source_class": source_class,
                "excerpt": excerpt,
                "excerpt_chars": len(excerpt),
                "retrieval_query_variant": str(candidate.get("matched_query_variant") or query_variant or ""),
                "freshness_status": str(candidate.get("freshness_status") or freshness),
                "project_label": project_label,
            })

    add_candidates("telegram_archive", _mappings(archive_evidence.get("items")), query_variant=_first_string(archive_evidence.get("query_variants")), freshness="archive_date_known")
    add_candidates("curated_memory", _mappings(curated_memory.get("items")), freshness="curated_memory")
    add_candidates("linked_source", _mappings(linked_source_evidence.get("items")), freshness="cached_fixture_or_unknown")
    add_candidates("semantic_candidate", _mappings(semantic_candidates), freshness="synthetic_not_executed")

    status = "ready" if sources else "insufficient_evidence"
    return validate_rag_context_pack({
        "schema_version": RAG_CONTEXT_PACK_SCHEMA_VERSION,
        "status": status,
        "sources": sources,
        "excluded_candidates": excluded,
        "limits": {"max_sources": clean_max_sources, "max_excerpt_chars": clean_excerpt_limit},
        "no_answer": {"threshold": threshold, "required": not sources, "reason": "no_cited_context" if not sources else "not_triggered"},
        "privacy": {"raw_corpus_included": False, "provider_payload_included": False, "provider_egress": False, "embeddings_run": False},
    })


def validate_rag_context_pack(pack: Mapping[str, Any]) -> dict[str, Any]:
    if pack.get("schema_version") != RAG_CONTEXT_PACK_SCHEMA_VERSION:
        raise RagContextPackError("context pack schema_version is invalid")
    if pack.get("status") not in {"ready", "insufficient_evidence"}:
        raise RagContextPackError("context pack status is invalid")
    limits = pack.get("limits")
    if not isinstance(limits, Mapping) or int(limits.get("max_sources") or 0) < 1 or int(limits.get("max_excerpt_chars") or 0) < 1:
        raise RagContextPackError("context pack limits are invalid")
    sources = _mappings(pack.get("sources"))
    seen: set[str] = set()
    for source in sources:
        if _RAW_FIELDS.intersection(source):
            raise RagContextPackError("context pack contains a raw corpus field")
        ref = _source_ref(source)
        if not ref:
            raise RagContextPackError("context source is missing citation")
        if ref in seen:
            raise RagContextPackError("context pack contains duplicate citation")
        seen.add(ref)
        if source.get("source_class") not in _SOURCE_CLASSES:
            raise RagContextPackError("context source_class is invalid")
        excerpt = str(source.get("excerpt") or "")
        if not excerpt or len(excerpt) > int(limits["max_excerpt_chars"]):
            raise RagContextPackError("context excerpt violates its budget")
    privacy = pack.get("privacy")
    if not isinstance(privacy, Mapping) or any(privacy.get(field) is not False for field in ("raw_corpus_included", "provider_payload_included", "provider_egress", "embeddings_run")):
        raise RagContextPackError("context pack privacy boundary is invalid")
    if pack["status"] == "ready" and not sources:
        raise RagContextPackError("ready context pack requires cited sources")
    return dict(pack)


def render_rag_context_pack(pack: Mapping[str, Any]) -> str:
    validated = validate_rag_context_pack(pack)
    lines = ["Citation-Safe Context Pack", f"status={validated['status']}"]
    for source in _mappings(validated.get("sources")):
        lines.append(f"- [{source['source_class']}] {source['source_ref']}: {source['excerpt']}")
    if not validated["sources"]:
        lines.append("- no cited context; answer must use no-answer handling")
    return "\n".join(lines)


def _source_ref(candidate: Mapping[str, Any]) -> str:
    for key in ("source_ref", "source_url", "normalized_url", "archive_document_id", "memory_id", "id"):
        value = str(candidate.get(key) or "").strip()
        if value:
            return value
    return ""


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in (value or []) if isinstance(item, Mapping)]


def _first_string(value: Any) -> str:
    return next((str(item).strip() for item in (value or []) if str(item).strip()), "")


def _bounded_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit].strip()
