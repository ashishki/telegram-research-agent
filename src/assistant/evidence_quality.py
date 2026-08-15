"""Versioned evidence-quality metadata for local PRM answers."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


EVIDENCE_QUALITY_SCHEMA_VERSION = "prm_evidence_quality.v1"
SOURCE_CLASSES = {
    "telegram_commentary",
    "telegram_forward",
    "telegram_firsthand_case",
    "official_documentation",
    "official_vendor_announcement",
    "github_repository",
    "research_paper",
    "company_case",
    "independent_case",
    "unknown",
}

_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_+-]{2,}")


def build_evidence_quality_items(
    evidence: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    question: str = "",
    project_name: str = "",
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Annotate evidence dimensions without turning them into one opaque score."""

    items = _evidence_items(evidence)
    group_counts = Counter(_source_group_id(item) for item in items)
    result = []
    for index, item in enumerate(items, start=1):
        group_id = _source_group_id(item)
        result.append(
            {
                "schema_version": EVIDENCE_QUALITY_SCHEMA_VERSION,
                "evidence_id": str(item.get("evidence_id") or item.get("archive_document_id") or item.get("id") or f"e{index}"),
                "source_url": _source_url(item),
                "source_class": _source_class(item),
                "source_group_id": group_id,
                "posted_at": str(item.get("posted_at") or item.get("fetched_at") or ""),
                "freshness_status": _freshness_status(item, now=now),
                "relevance_score": _relevance_score(question, item),
                "directness": _directness(question, item),
                "independence": _independence(item),
                "corroboration_count": max(0, int(group_counts[group_id]) - 1),
                "primary_source_status": _primary_source_status(item),
                "operator_interest": _operator_interest(item),
                "project_fit": _project_fit(project_name, item),
                "support_span": _support_span(item),
                "content_hash": _content_hash(item),
            }
        )
    return result


def evidence_quality_summary(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(items)
    classes = Counter(str(item.get("source_class") or "unknown") for item in items)
    groups = {str(item.get("source_group_id") or "") for item in items if str(item.get("source_group_id") or "")}
    direct = sum(1 for item in items if item.get("directness") == "direct")
    relevant = sum(1 for item in items if float(item.get("relevance_score") or 0.0) >= 0.35)
    independent = sum(1 for item in items if item.get("independence") == "independent")
    return {
        "schema_version": "prm_evidence_quality_summary.v1",
        "evidence_count": total,
        "source_classes": dict(sorted(classes.items())),
        "source_group_count": len(groups),
        "direct_rate": round(direct / total, 4) if total else 0.0,
        "relevant_rate": round(relevant / total, 4) if total else 0.0,
        "independent_rate": round(independent / total, 4) if total else 0.0,
    }


def _evidence_items(evidence: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if isinstance(evidence, Mapping):
        values = evidence.get("items") or []
    else:
        values = evidence
    return [item for item in values if isinstance(item, Mapping)]


def _source_url(item: Mapping[str, Any]) -> str:
    return " ".join(str(item.get("source_url") or item.get("telegram_url") or item.get("message_url") or item.get("normalized_url") or "").split())


def _source_class(item: Mapping[str, Any]) -> str:
    explicit = str(item.get("source_class") or item.get("evidence_class") or "").strip()
    if explicit in SOURCE_CLASSES:
        return explicit
    url = _source_url(item)
    host = urlparse(url).netloc.casefold()
    text = f"{item.get('snippet') or ''} {item.get('text_excerpt') or ''}".casefold()
    if "github.com" == host or host.endswith(".github.com"):
        return "github_repository"
    if "arxiv.org" == host or host.endswith(".arxiv.org"):
        return "research_paper"
    if "docs." in host or "/docs" in urlparse(url).path.casefold():
        return "official_documentation" if bool(item.get("official_relation")) else "unknown"
    if "t.me" == host or host.endswith(".t.me"):
        if item.get("forward_from") or item.get("repost_cluster_id"):
            return "telegram_forward"
        if any(marker in text for marker in ("we built", "мы сделали", "наш кейс", "case study", "firsthand")):
            return "telegram_firsthand_case"
        return "telegram_commentary"
    if any(marker in text for marker in ("case study", "customer story", "наш кейс", "implemented")):
        return "company_case"
    return "unknown"


def _source_group_id(item: Mapping[str, Any]) -> str:
    for key in ("source_group_id", "repost_cluster_id", "duplicate_cluster_id", "content_hash"):
        value = str(item.get(key) or "").strip()
        if value:
            return f"{key}:{value[:24]}"
    url = _source_url(item)
    if url:
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = path.split("/")
        group = "/".join(parts[:2]) if parts else parsed.netloc
        return f"url:{parsed.netloc.casefold()}:{group}"
    span = _support_span(item)
    return "hash:" + hashlib.sha256(span.encode()).hexdigest()[:16]


def _freshness_status(item: Mapping[str, Any], *, now: datetime | None) -> str:
    raw = str(item.get("posted_at") or item.get("fetched_at") or "").strip()
    if not raw:
        return "unknown"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    reference = now or datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    days = (reference - parsed).days
    if days <= 45:
        return "fresh"
    if days <= 180:
        return "recent_context"
    return "stale"


def _relevance_score(question: str, item: Mapping[str, Any]) -> float:
    query = set(_tokens(question))
    if not query:
        return 0.0
    haystack = set(_tokens(_support_span(item)))
    overlap = len(query & haystack)
    return round(min(1.0, overlap / max(1, min(len(query), 8))), 4)


def _directness(question: str, item: Mapping[str, Any]) -> str:
    score = _relevance_score(question, item)
    if score >= 0.45:
        return "direct"
    if score >= 0.18:
        return "indirect"
    return "background"


def _independence(item: Mapping[str, Any]) -> str:
    source_class = _source_class(item)
    if source_class.startswith("telegram"):
        return "unknown"
    if source_class in {"github_repository", "official_documentation", "official_vendor_announcement", "research_paper", "independent_case"}:
        return "independent"
    return "unknown"


def _primary_source_status(item: Mapping[str, Any]) -> str:
    source_class = _source_class(item)
    if source_class in {"github_repository", "official_documentation", "official_vendor_announcement", "research_paper"}:
        return "primary_or_official"
    if source_class in {"telegram_commentary", "telegram_forward", "unknown"}:
        return "not_primary"
    return "secondary"


def _operator_interest(item: Mapping[str, Any]) -> str:
    if int(item.get("reaction_count") or 0) > 0 or int(item.get("tag_count") or 0) > 0:
        return "confirmed_interest"
    if item.get("reactions") or item.get("tags"):
        return "confirmed_interest"
    return "unknown"


def _project_fit(project_name: str, item: Mapping[str, Any]) -> str:
    clean = str(project_name or "").casefold().strip()
    if not clean:
        return "not_requested"
    projects = [str(value).casefold() for value in item.get("project_names") or [] if str(value).strip()]
    haystack = f"{item.get('snippet') or ''} {item.get('content') or ''}".casefold()
    if clean in projects or clean in haystack:
        return "direct"
    return "unknown"


def _support_span(item: Mapping[str, Any]) -> str:
    value = str(item.get("support_span") or item.get("snippet") or item.get("text_excerpt") or item.get("content") or "")
    return " ".join(value.split())[:260]


def _content_hash(item: Mapping[str, Any]) -> str:
    value = str(item.get("content_hash") or "").strip()
    if value:
        return value
    return "sha256:" + hashlib.sha256(_support_span(item).encode()).hexdigest()


def _tokens(value: object) -> list[str]:
    return [token.casefold() for token in _TOKEN_RE.findall(str(value or ""))]
