from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


PROJECT_CONTEXT_SCHEMA_VERSION = "project_context_decision_support.v1"
MAX_PROJECT_DESCRIPTOR_BYTES = 512_000
PROJECT_RELEVANCE_LABELS = {
    "direct_implication",
    "weak_watch",
    "learning_relevance",
    "no_match",
}

_TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_+-]{1,}")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}
_GENERIC_PROJECT_TERMS = {
    "agent",
    "agents",
    "automation",
    "codex",
    "data",
    "eval",
    "evaluation",
    "evidence",
    "governance",
    "memory",
    "mvp",
    "pipeline",
    "project",
    "quality",
    "rag",
    "research",
    "system",
    "tool",
    "tools",
    "workflow",
}
_LEARNING_TERMS = {
    "architecture",
    "background",
    "calibration",
    "concept",
    "explainer",
    "framework",
    "learn",
    "learning",
    "pattern",
    "reference",
    "study",
    "tutorial",
}


def load_project_descriptors(path: str | Path) -> list[dict[str, Any]]:
    """Load active project descriptors without syncing external project state."""

    source = Path(path)
    if not source.exists():
        return []
    try:
        if source.stat().st_size > MAX_PROJECT_DESCRIPTOR_BYTES:
            raise ValueError("project descriptor file exceeds size limit")
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot load project descriptors: {type(exc).__name__}") from exc
    if payload is None:
        return []
    if not isinstance(payload, Mapping):
        raise ValueError("project descriptor root must be an object")
    projects = payload.get("projects")
    if not isinstance(projects, list):
        raise ValueError("project descriptor root must contain a projects list")
    return [_normalize_project_descriptor(item) for item in projects if isinstance(item, Mapping)]


def select_project_descriptor(
    project_name: str | None,
    query: str,
    descriptors: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    clean_name = _clean_text(project_name).casefold()
    if clean_name:
        for descriptor in descriptors:
            if _clean_text(descriptor.get("name")).casefold() == clean_name:
                return dict(descriptor)
    query_text = _normalize_text(query)
    best_score = 0
    best_descriptor: Mapping[str, Any] | None = None
    for descriptor in descriptors:
        name = _clean_text(descriptor.get("name"))
        score = 0
        if name and _normalize_text(name) in query_text:
            score += 8
        repo = _clean_text(descriptor.get("repo"))
        if repo and _normalize_text(repo) in query_text:
            score += 5
        score += len(_matched_terms(_string_values(descriptor.get("keywords")), query_text, _tokens(query_text)))
        if score > best_score:
            best_score = score
            best_descriptor = descriptor
    return dict(best_descriptor) if best_descriptor is not None and best_score > 0 else None


def build_project_context_decision_support(
    *,
    query: str,
    project_descriptor: Mapping[str, Any],
    archive_result: Mapping[str, Any] | None = None,
    curated_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    descriptor = _normalize_project_descriptor(project_descriptor)
    archive_items = _items_from_result(archive_result)
    curated_items = _items_from_result(curated_result)
    archive_source_refs = _source_refs_from_items(archive_items)
    curated_source_refs = _source_refs_from_items(curated_items)
    source_refs = _unique([*archive_source_refs, *curated_source_refs])

    query_text = _normalize_text(query)
    raw_evidence_text = _items_text(archive_items) + " " + _items_text(curated_items)
    evidence_text = _normalize_text(raw_evidence_text)
    combined_text = _normalize_text(f"{query} {raw_evidence_text}")
    evidence_tokens = _tokens(evidence_text)
    field_matches = _descriptor_field_matches(
        descriptor,
        query_text,
        evidence_text,
        evidence_tokens,
        combined_text=combined_text,
        combined_tokens=_tokens(combined_text),
    )
    exclude_matches = field_matches.get("exclude_keywords", [])
    keyword_matches = field_matches.get("keywords", [])
    strong_keyword_matches = [term for term in keyword_matches if _is_strong_project_term(term)]
    learning_matches = _learning_matches(descriptor, query_text, evidence_text, evidence_tokens)
    direct_project_link = _has_direct_project_link(descriptor, archive_items, curated_items)

    label = _classify_project_relevance(
        source_refs=source_refs,
        archive_source_refs=archive_source_refs,
        exclude_matches=exclude_matches,
        direct_project_link=direct_project_link,
        strong_keyword_matches=strong_keyword_matches,
        keyword_matches=keyword_matches,
        field_matches=field_matches,
        learning_matches=learning_matches,
    )
    descriptor_fields_used = [
        field
        for field in ("name", "repo", "description", "focus", "keywords", "learning_keywords")
        if field_matches.get(field)
    ]
    suggestions = _project_suggestions(
        label=label,
        descriptor=descriptor,
        strong_keyword_matches=strong_keyword_matches,
        keyword_matches=keyword_matches,
        source_refs=source_refs,
        descriptor_fields_used=descriptor_fields_used,
    )

    status = "insufficient_evidence" if label == "no_match" and not source_refs else "ok"
    return {
        "schema_version": PROJECT_CONTEXT_SCHEMA_VERSION,
        "status": status,
        "query": _clean_text(query),
        "project_name": descriptor["name"],
        "project_repo": descriptor.get("repo") or None,
        "relevance_label": label,
        "descriptor_fields_used": descriptor_fields_used,
        "field_matches": {key: value for key, value in field_matches.items() if value},
        "matched_terms": _unique([term for terms in field_matches.values() for term in terms]),
        "archive_evidence": {
            "status": _status_from_result(archive_result, archive_items),
            "source_refs": archive_source_refs,
            "items": _bounded_items(archive_items),
        },
        "curated_knowledge": {
            "status": _status_from_result(curated_result, curated_items),
            "source_refs": curated_source_refs,
            "items": _bounded_items(curated_items),
        },
        "project_suggestions": suggestions,
        "watch_or_learning": _watch_or_learning_payload(
            label=label,
            learning_matches=learning_matches,
            keyword_matches=keyword_matches,
            source_refs=source_refs,
        ),
        "decision_support": {
            "automatic_mvp_build_approval": False,
            "code_mutation_exposed": False,
            "project_mutation_exposed": False,
            "write_performed": False,
            "requires_human_confirmation_for_saves": True,
        },
        "unknowns": _project_unknowns(label=label, source_refs=source_refs, archive_source_refs=archive_source_refs),
        "source_refs": source_refs,
        "message": _project_context_message(label),
    }


def project_context_search_query(query: str, descriptor: Mapping[str, Any], *, max_terms: int = 6) -> str:
    clean_query = _clean_text(query)
    keywords = [
        term
        for term in _string_values(descriptor.get("keywords"))
        if _is_strong_project_term(term)
    ][:max_terms]
    if keywords:
        return " ".join([clean_query, *keywords]).strip()
    return clean_query


def render_project_context_answer(payload: Mapping[str, Any]) -> str:
    project_name = _clean_text(payload.get("project_name")) or "unknown project"
    label = _clean_text(payload.get("relevance_label")) or "no_match"
    fields = _string_values(payload.get("descriptor_fields_used"))
    source_refs = _string_values(payload.get("source_refs"))
    suggestions = [item for item in payload.get("project_suggestions") or [] if isinstance(item, Mapping)]
    watch = payload.get("watch_or_learning") if isinstance(payload.get("watch_or_learning"), Mapping) else {}
    unknowns = _string_values(payload.get("unknowns"))
    lines = [f"Project context: {project_name} -> {label}."]
    lines.append("Descriptor fields used: " + (", ".join(fields) if fields else "none matched."))
    if source_refs:
        lines.append("Archive/source evidence: " + ", ".join(source_refs[:5]))
    else:
        lines.append("Archive/source evidence: insufficient_evidence.")
    if suggestions:
        first = suggestions[0]
        lines.append("Suggestion: " + _clean_text(first.get("suggested_next_step")))
    elif watch:
        lines.append("Suggestion: " + _clean_text(watch.get("reader_guidance")))
    else:
        lines.append("Suggestion: no project action recommendation.")
    if unknowns:
        lines.append("Unknowns: " + "; ".join(unknowns))
    lines.append("Boundary: no MVP build approval, code mutation, or project mutation was exposed.")
    return "\n".join(lines)


def _normalize_project_descriptor(raw: Mapping[str, Any]) -> dict[str, Any]:
    name = _clean_text(raw.get("name"))
    if not name:
        raise ValueError("project descriptor name is required")
    return {
        "name": name,
        "repo": _clean_text(raw.get("repo")),
        "description": _clean_text(raw.get("description")),
        "focus": _clean_text(raw.get("focus")),
        "keywords": _string_values(raw.get("keywords")),
        "exclude_keywords": _string_values(raw.get("exclude_keywords")),
        "learning_keywords": _string_values(raw.get("learning_keywords")),
    }


def _descriptor_field_matches(
    descriptor: Mapping[str, Any],
    query_text: str,
    evidence_text: str,
    evidence_tokens: set[str],
    *,
    combined_text: str,
    combined_tokens: set[str],
) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {}
    name = _clean_text(descriptor.get("name"))
    if name and (_normalize_text(name) in query_text or _normalize_text(name) in evidence_text):
        matches["name"] = [name]
    repo = _clean_text(descriptor.get("repo"))
    if repo and (_normalize_text(repo) in query_text or _normalize_text(repo) in evidence_text):
        matches["repo"] = [repo]
    for field in ("description", "focus"):
        terms = _field_terms(descriptor.get(field))
        matched = _matched_terms(terms, evidence_text, evidence_tokens)
        if matched:
            matches[field] = matched
    matched_excludes = _matched_terms(
        _string_values(descriptor.get("exclude_keywords")),
        combined_text,
        combined_tokens,
    )
    if matched_excludes:
        matches["exclude_keywords"] = matched_excludes
    for field in ("keywords", "learning_keywords"):
        matched = _matched_terms(_string_values(descriptor.get(field)), evidence_text, evidence_tokens)
        if matched:
            matches[field] = matched
    return matches


def _field_terms(value: Any) -> list[str]:
    text = _clean_text(value)
    tokens = [token for token in _tokens(text) if token not in _GENERIC_PROJECT_TERMS]
    return tokens[:16]


def _matched_terms(terms: Sequence[str], text: str, tokens: set[str]) -> list[str]:
    matched: list[str] = []
    for term in terms:
        clean = _clean_text(term)
        if not clean:
            continue
        normalized = _normalize_text(clean)
        term_tokens = _tokens(normalized)
        if not term_tokens:
            continue
        if normalized in text:
            matched.append(clean)
            continue
        overlap = sorted(term_tokens.intersection(tokens))
        if len(term_tokens) == 1 and overlap:
            matched.append(clean)
        elif len(term_tokens) > 1 and len(overlap) >= min(2, len(term_tokens)):
            matched.append(clean)
    return _unique(matched)


def _learning_matches(
    descriptor: Mapping[str, Any],
    query_text: str,
    evidence_text: str,
    evidence_tokens: set[str],
) -> list[str]:
    configured = _matched_terms(
        _string_values(descriptor.get("learning_keywords")),
        evidence_text,
        evidence_tokens,
    )
    ambient = sorted((set(_tokens(query_text)) | evidence_tokens).intersection(_LEARNING_TERMS))
    return _unique([*configured, *ambient])


def _classify_project_relevance(
    *,
    source_refs: Sequence[str],
    archive_source_refs: Sequence[str],
    exclude_matches: Sequence[str],
    direct_project_link: bool,
    strong_keyword_matches: Sequence[str],
    keyword_matches: Sequence[str],
    field_matches: Mapping[str, Sequence[str]],
    learning_matches: Sequence[str],
) -> str:
    if exclude_matches:
        return "no_match"
    if not source_refs:
        return "no_match"
    non_name_fields = {
        field
        for field, matches in field_matches.items()
        if field not in {"name", "repo", "exclude_keywords", "learning_keywords"} and matches
    }
    if direct_project_link or (
        archive_source_refs
        and len(strong_keyword_matches) >= 2
        and len(non_name_fields) >= 2
    ):
        return "direct_implication"
    if learning_matches and (keyword_matches or field_matches.get("learning_keywords")):
        return "learning_relevance"
    if keyword_matches or non_name_fields:
        return "weak_watch"
    return "no_match"


def _project_suggestions(
    *,
    label: str,
    descriptor: Mapping[str, Any],
    strong_keyword_matches: Sequence[str],
    keyword_matches: Sequence[str],
    source_refs: Sequence[str],
    descriptor_fields_used: Sequence[str],
) -> list[dict[str, Any]]:
    if label != "direct_implication":
        return []
    terms = _unique([*strong_keyword_matches, *keyword_matches])[:4]
    focus = ", ".join(terms) if terms else "the cited project-relevant evidence"
    project_name = _clean_text(descriptor.get("name"))
    return [
        {
            "suggestion_type": "candidate_next_step",
            "project_name": project_name,
            "suggested_next_step": (
                f"Use the cited evidence on {focus} to scope a human-approved "
                f"{project_name} experiment or backlog item."
            ),
            "evidence_basis": list(source_refs[:5]),
            "descriptor_fields_used": list(descriptor_fields_used),
            "confidence": "medium",
            "mutation_performed": False,
        }
    ]


def _watch_or_learning_payload(
    *,
    label: str,
    learning_matches: Sequence[str],
    keyword_matches: Sequence[str],
    source_refs: Sequence[str],
) -> dict[str, Any] | None:
    if label == "weak_watch":
        return {
            "kind": "weak_watch",
            "reader_guidance": "Watch the signal; do not turn it into an action recommendation yet.",
            "matched_terms": list(keyword_matches),
            "source_refs": list(source_refs[:5]),
        }
    if label == "learning_relevance":
        return {
            "kind": "learning_relevance",
            "reader_guidance": "Treat this as study context until project-specific evidence appears.",
            "matched_terms": list(learning_matches),
            "source_refs": list(source_refs[:5]),
        }
    if label == "no_match":
        return {
            "kind": "no_match",
            "reader_guidance": "No project action recommendation.",
            "matched_terms": [],
            "source_refs": list(source_refs[:5]),
        }
    return None


def _project_unknowns(*, label: str, source_refs: Sequence[str], archive_source_refs: Sequence[str]) -> list[str]:
    unknowns: list[str] = []
    if not source_refs:
        unknowns.append("archive or curated source support")
    if not archive_source_refs:
        unknowns.append("Telegram archive citation")
    if label in {"weak_watch", "learning_relevance", "no_match"}:
        unknowns.append("direct project implication")
    return unknowns


def _project_context_message(label: str) -> str:
    if label == "direct_implication":
        return "Project context matched direct evidence; suggestion is read-only and human-gated."
    if label == "weak_watch":
        return "Project context is a weak watch match; no action recommendation was produced."
    if label == "learning_relevance":
        return "Project context is learning-relevant; no action recommendation was produced."
    return "No project context match was supported by the supplied evidence."


def _items_from_result(result: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(result, Mapping):
        return []
    raw_items = result.get("items") or result.get("results") or []
    if not isinstance(raw_items, list):
        return []
    return [dict(item) for item in raw_items if isinstance(item, Mapping)]


def _bounded_items(items: Sequence[Mapping[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    bounded: list[dict[str, Any]] = []
    for item in items[:limit]:
        result = {
            key: item.get(key)
            for key in (
                "archive_document_id",
                "id",
                "item_type",
                "title",
                "summary",
                "channel_username",
                "posted_at",
                "source_url",
                "source_refs",
                "source_urls",
                "atom_ids",
                "project_name",
                "project_names",
                "snippet",
            )
            if key in item
        }
        bounded.append(result)
    return bounded


def _status_from_result(result: Mapping[str, Any] | None, items: Sequence[Mapping[str, Any]]) -> str:
    if isinstance(result, Mapping) and result.get("status"):
        return _clean_text(result.get("status"))
    return "ok" if items else "empty"


def _items_text(items: Sequence[Mapping[str, Any]]) -> str:
    values: list[str] = []
    for item in items:
        for key in (
            "title",
            "summary",
            "claim",
            "body",
            "snippet",
            "content",
            "why_this_matters",
            "next_action",
        ):
            value = item.get(key)
            if isinstance(value, str):
                values.append(value)
    return " ".join(values)


def _source_refs_from_items(items: Sequence[Mapping[str, Any]]) -> list[str]:
    refs: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key in {"source_url", "url"}:
                    refs.extend(_string_values(child))
                    continue
                if key in {"source_refs", "source_urls"}:
                    refs.extend(_string_values(child))
                    continue
                visit(child)
            return
        if isinstance(value, list):
            for child in value:
                visit(child)

    visit(list(items))
    return _unique(refs)


def _has_direct_project_link(
    descriptor: Mapping[str, Any],
    archive_items: Sequence[Mapping[str, Any]],
    curated_items: Sequence[Mapping[str, Any]],
) -> bool:
    name = _clean_text(descriptor.get("name")).casefold()
    if not name:
        return False
    for item in [*archive_items, *curated_items]:
        names = _string_values(item.get("project_names"))
        single = _clean_text(item.get("project_name"))
        if single:
            names.append(single)
        if any(candidate.casefold() == name for candidate in names):
            return True
    return False


def _is_strong_project_term(term: str) -> bool:
    tokens = _tokens(term)
    if not tokens:
        return False
    if len(tokens) >= 2:
        return any(token not in _GENERIC_PROJECT_TERMS for token in tokens)
    token = next(iter(tokens))
    return token not in _GENERIC_PROJECT_TERMS and len(token) >= 4


def _tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in _TOKEN_RE.findall(str(value or ""))
        if len(token) >= 2 and token.casefold() not in _STOPWORDS
    }


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("-", " ").replace("_", " ").split())


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _string_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        clean = _clean_text(value)
        return [clean] if clean else []
    if isinstance(value, list | tuple | set):
        return [_clean_text(item) for item in value if _clean_text(item)]
    clean = _clean_text(value)
    return [clean] if clean else []


def _unique(values: Sequence[Any]) -> list:
    result = []
    seen = set()
    for value in values:
        key = str(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
