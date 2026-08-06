from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


LINKED_SOURCE_RECEIPT_SCHEMA_VERSION = "linked_source_research_receipt.v1"
LINKED_SOURCE_CACHE_RECORD_SCHEMA_VERSION = "linked_source_cache_record.v1"
CONTENT_HASH_ALGORITHM = "sha256:normalized_text"

SOURCE_TYPES = frozenset({"article", "docs", "github", "paper", "video", "product", "unknown"})
EXTRACTION_STATUSES = frozenset({"extracted", "failed", "refused", "not_fetched"})

_URL_PATTERN = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
_TRAILING_URL_PUNCTUATION = ".,!?;:)]}'\""
_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_NAMES = {"fbclid", "gclid", "mc_cid", "mc_eid"}
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|token|password|secret)=([^\s&]+)"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
)


class LinkedSourceFetcher(Protocol):
    requires_live_http: bool
    requires_external_skill: bool
    requires_provider_summarization: bool

    def fetch(self, source_url: str) -> "FetchedLinkedSource":
        ...


@dataclass(frozen=True)
class FetchedLinkedSource:
    source_url: str
    title: str = ""
    text: str = ""
    fetched_at: str | None = None
    status: str = "ok"
    failure_reason: str | None = None
    raw_payload: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class LinkedSourceApprovals:
    allow_live_http_fetch: bool = False
    allow_external_skills: bool = False
    allow_provider_summarization: bool = False
    approved_budget_usd: float = 0.0
    max_live_fetches: int = 0
    max_provider_calls: int = 0
    approved_external_skill_trust_record: bool = False
    approval_ref: str | None = None

    def to_receipt(self) -> dict[str, Any]:
        return {
            "allow_live_http_fetch": self.allow_live_http_fetch,
            "allow_external_skills": self.allow_external_skills,
            "allow_provider_summarization": self.allow_provider_summarization,
            "approved_budget_usd": round(float(self.approved_budget_usd or 0.0), 8),
            "max_live_fetches": max(0, int(self.max_live_fetches or 0)),
            "max_provider_calls": max(0, int(self.max_provider_calls or 0)),
            "approved_external_skill_trust_record": self.approved_external_skill_trust_record,
            "approval_ref_present": bool(str(self.approval_ref or "").strip()),
        }


@dataclass(frozen=True)
class LinkedSourceCandidate:
    source_url: str
    normalized_url: str
    source_type: str
    source_post_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "normalized_url": self.normalized_url,
            "source_type": self.source_type,
            "source_post_refs": list(self.source_post_refs),
        }


@dataclass(frozen=True)
class LinkedSourceCacheRecord:
    source_url: str
    normalized_url: str
    source_type: str
    fetched_at: str
    normalized_title: str
    content_hash: str
    extraction_status: str
    redacted_failure_reason: str | None = None
    text_excerpt: str = ""
    source_post_refs: tuple[str, ...] = ()
    content_hash_algorithm: str = CONTENT_HASH_ALGORITHM

    def to_dict(self) -> dict[str, Any]:
        status = self.extraction_status if self.extraction_status in EXTRACTION_STATUSES else "failed"
        return {
            "schema_version": LINKED_SOURCE_CACHE_RECORD_SCHEMA_VERSION,
            "source_url": self.source_url,
            "normalized_url": self.normalized_url,
            "source_type": self.source_type if self.source_type in SOURCE_TYPES else "unknown",
            "fetched_at": self.fetched_at,
            "normalized_title": self.normalized_title,
            "content_hash": self.content_hash,
            "content_hash_algorithm": self.content_hash_algorithm,
            "extraction_status": status,
            "redacted_failure_reason": self.redacted_failure_reason,
            "text_excerpt": self.text_excerpt,
            "source_post_refs": list(self.source_post_refs),
        }


@dataclass
class LinkedSourceCache:
    durable: bool = False
    _records: dict[str, LinkedSourceCacheRecord] = field(default_factory=dict)

    def get(self, normalized_url: str) -> LinkedSourceCacheRecord | None:
        return self._records.get(normalized_url)

    def put(self, record: LinkedSourceCacheRecord) -> LinkedSourceCacheRecord:
        self._records[record.normalized_url] = record
        return record

    def to_records(self) -> list[LinkedSourceCacheRecord]:
        return list(self._records.values())

    def to_dicts(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in self.to_records()]


class FakeLinkedSourceFetcher:
    requires_live_http = False
    requires_external_skill = False
    requires_provider_summarization = False

    def __init__(self, fixtures: Mapping[str, Mapping[str, Any] | FetchedLinkedSource]):
        self._fixtures = {
            normalize_source_url(source_url): payload
            for source_url, payload in fixtures.items()
        }

    def fetch(self, source_url: str) -> FetchedLinkedSource:
        normalized_url = normalize_source_url(source_url)
        payload = self._fixtures.get(normalized_url)
        if payload is None:
            return FetchedLinkedSource(
                source_url=source_url,
                status="failed",
                failure_reason="fixture_not_found",
            )
        if isinstance(payload, FetchedLinkedSource):
            return payload
        return FetchedLinkedSource(
            source_url=str(payload.get("source_url") or source_url),
            title=str(payload.get("title") or ""),
            text=str(payload.get("text") or ""),
            fetched_at=_optional_text(payload.get("fetched_at")),
            status=str(payload.get("status") or "ok"),
            failure_reason=_optional_text(payload.get("failure_reason")),
            raw_payload=payload.get("raw_payload") if isinstance(payload.get("raw_payload"), Mapping) else None,
        )


@dataclass
class LinkedSourceResolver:
    fetcher: LinkedSourceFetcher | None = None
    cache: LinkedSourceCache = field(default_factory=LinkedSourceCache)
    approvals: LinkedSourceApprovals = field(default_factory=LinkedSourceApprovals)
    max_sources: int = 10

    def resolve(self, posts: Sequence[Mapping[str, Any]], *, fetched_at: str | None = None) -> dict[str, Any]:
        timestamp = normalize_timestamp(fetched_at)
        candidates = extract_linked_source_candidates(posts, limit=self.max_sources)
        cache_events: list[dict[str, Any]] = []
        for candidate in candidates:
            cached = self.cache.get(candidate.normalized_url)
            if cached is not None:
                cache_events.append(
                    {
                        "normalized_url": candidate.normalized_url,
                        "cache_status": "hit",
                        "extraction_status": cached.extraction_status,
                    }
                )
                continue

            refusal_reason = _approval_refusal_reason(self.fetcher, self.approvals)
            if refusal_reason:
                record = _record_from_failure(candidate, timestamp, "refused", refusal_reason)
                self.cache.put(record)
                cache_events.append(
                    {
                        "normalized_url": candidate.normalized_url,
                        "cache_status": "stored",
                        "extraction_status": "refused",
                    }
                )
                continue

            if self.fetcher is None:
                record = _record_from_failure(candidate, timestamp, "not_fetched", "no_fixture_fetcher_configured")
                self.cache.put(record)
                cache_events.append(
                    {
                        "normalized_url": candidate.normalized_url,
                        "cache_status": "stored",
                        "extraction_status": "not_fetched",
                    }
                )
                continue

            record = self._fetch_record(candidate, timestamp)
            self.cache.put(record)
            cache_events.append(
                {
                    "normalized_url": candidate.normalized_url,
                    "cache_status": "stored",
                    "extraction_status": record.extraction_status,
                }
            )

        cache_records = self.cache.to_records()
        receipt = build_linked_source_receipt(
            candidates=candidates,
            cache_records=cache_records,
            cache_events=cache_events,
            cache_durable=self.cache.durable,
            approvals=self.approvals,
            fetcher=self.fetcher,
        )
        return {
            "schema_version": LINKED_SOURCE_RECEIPT_SCHEMA_VERSION,
            "status": receipt["status"],
            "mode": receipt["mode"],
            "candidates": [candidate.to_dict() for candidate in candidates],
            "cache_records": [record.to_dict() for record in cache_records],
            "cache_events": cache_events,
            "receipt": receipt,
        }

    def _fetch_record(self, candidate: LinkedSourceCandidate, fetched_at: str) -> LinkedSourceCacheRecord:
        assert self.fetcher is not None
        try:
            fetched = self.fetcher.fetch(candidate.source_url)
        except Exception as exc:  # pragma: no cover - exercised through public failure status
            return _record_from_failure(candidate, fetched_at, "failed", f"{type(exc).__name__}: {exc}")

        status = str(fetched.status or "ok").strip().lower()
        if status not in {"ok", "extracted"}:
            return _record_from_failure(
                candidate,
                normalize_timestamp(fetched.fetched_at or fetched_at),
                "failed",
                fetched.failure_reason or status,
            )

        normalized_text = normalize_text(fetched.text)
        if not normalized_text:
            return _record_from_failure(
                candidate,
                normalize_timestamp(fetched.fetched_at or fetched_at),
                "failed",
                fetched.failure_reason or "empty_extracted_text",
            )
        return LinkedSourceCacheRecord(
            source_url=candidate.source_url,
            normalized_url=candidate.normalized_url,
            source_type=candidate.source_type,
            fetched_at=normalize_timestamp(fetched.fetched_at or fetched_at),
            normalized_title=normalize_title(fetched.title),
            content_hash=content_hash(normalized_text),
            extraction_status="extracted",
            redacted_failure_reason=None,
            text_excerpt=bounded_excerpt(normalized_text),
            source_post_refs=candidate.source_post_refs,
        )


def resolve_linked_sources(
    posts: Sequence[Mapping[str, Any]],
    *,
    fetcher: LinkedSourceFetcher | None = None,
    cache: LinkedSourceCache | None = None,
    approvals: LinkedSourceApprovals | None = None,
    max_sources: int = 10,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    resolver = LinkedSourceResolver(
        fetcher=fetcher,
        cache=cache or LinkedSourceCache(),
        approvals=approvals or LinkedSourceApprovals(),
        max_sources=max_sources,
    )
    return resolver.resolve(posts, fetched_at=fetched_at)


def extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in _URL_PATTERN.finditer(str(text or "")):
        url = _strip_url(match.group(0))
        if url:
            urls.append(url)
    return _unique(urls)


def extract_linked_source_candidates(posts: Sequence[Mapping[str, Any]], *, limit: int = 10) -> list[LinkedSourceCandidate]:
    refs_by_url: dict[str, list[str]] = {}
    originals_by_url: dict[str, str] = {}
    for post in posts:
        post_ref = _post_ref(post)
        for url in _post_urls(post):
            normalized_url = normalize_source_url(url)
            if not normalized_url or is_telegram_url(normalized_url):
                continue
            originals_by_url.setdefault(normalized_url, url)
            if post_ref:
                refs_by_url.setdefault(normalized_url, [])
                if post_ref not in refs_by_url[normalized_url]:
                    refs_by_url[normalized_url].append(post_ref)

    bounded_limit = max(1, min(50, int(limit or 10)))
    candidates: list[LinkedSourceCandidate] = []
    for normalized_url, source_url in list(originals_by_url.items())[:bounded_limit]:
        candidates.append(
            LinkedSourceCandidate(
                source_url=source_url,
                normalized_url=normalized_url,
                source_type=classify_source_url(normalized_url),
                source_post_refs=tuple(refs_by_url.get(normalized_url) or ()),
            )
        )
    return candidates


def normalize_source_url(url: str) -> str:
    stripped = _strip_url(url)
    if not stripped:
        return ""
    try:
        parts = urlsplit(stripped)
    except ValueError:
        return stripped
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if scheme not in {"http", "https"} or not host:
        return stripped

    port = parts.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    query = _normalize_query(parts.query)
    path = parts.path or ""
    if path == "/":
        path = ""
    elif path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, query, ""))


def classify_source_url(url: str) -> str:
    normalized_url = normalize_source_url(url)
    try:
        parts = urlsplit(normalized_url)
    except ValueError:
        return "unknown"
    host = (parts.hostname or "").lower()
    path = (parts.path or "").lower()
    if not host:
        return "unknown"
    if host == "github.com" or host.endswith(".github.com") or host == "gist.github.com":
        return "github"
    if _is_video(host, path):
        return "video"
    if _is_paper(host, path):
        return "paper"
    if _is_docs(host, path):
        return "docs"
    if _is_product(host, path):
        return "product"
    if _is_article(host, path):
        return "article"
    return "unknown"


def build_linked_source_receipt(
    *,
    candidates: Sequence[LinkedSourceCandidate],
    cache_records: Sequence[LinkedSourceCacheRecord],
    cache_events: Sequence[Mapping[str, Any]],
    cache_durable: bool,
    approvals: LinkedSourceApprovals,
    fetcher: LinkedSourceFetcher | None,
) -> dict[str, Any]:
    status_counts: dict[str, int] = {status: 0 for status in sorted(EXTRACTION_STATUSES)}
    type_counts: dict[str, int] = {source_type: 0 for source_type in sorted(SOURCE_TYPES)}
    for candidate in candidates:
        type_counts[candidate.source_type if candidate.source_type in SOURCE_TYPES else "unknown"] += 1
    for record in cache_records:
        status = record.extraction_status if record.extraction_status in EXTRACTION_STATUSES else "failed"
        status_counts[status] += 1

    status = _overall_status(candidates, cache_records)
    mode = "fixture_fetch" if fetcher is not None and not _fetcher_requires_external_boundary(fetcher) else "classification_only"
    if fetcher is not None and _fetcher_requires_external_boundary(fetcher):
        mode = "approval_gated"
    return {
        "schema_version": LINKED_SOURCE_RECEIPT_SCHEMA_VERSION,
        "status": status,
        "mode": mode,
        "candidate_count": len(candidates),
        "cache_record_count": len(cache_records),
        "source_type_counts": {key: value for key, value in type_counts.items() if value},
        "extraction_status_counts": {key: value for key, value in status_counts.items() if value},
        "cache_events": [dict(event) for event in cache_events],
        "cache_records": [record.to_dict() for record in cache_records],
        "approvals": approvals.to_receipt(),
        "privacy": {
            "model_calls": 0,
            "estimated_cost_usd": 0.0,
            "external_skill_used": False,
            "live_http_fetch_used": bool(fetcher and getattr(fetcher, "requires_live_http", False) and approvals.allow_live_http_fetch),
            "provider_summarization_used": False,
            "provider_payload_logged": False,
            "raw_telegram_corpus_egress": False,
            "telegram_post_text_logged": False,
            "durable_cache_write": bool(cache_durable),
        },
    }


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def normalize_text(value: object) -> str:
    return " ".join(str(value or "").split())


def normalize_title(value: object, *, limit: int = 180) -> str:
    return bounded_excerpt(normalize_text(value), limit=limit)


def bounded_excerpt(value: object, *, limit: int = 500) -> str:
    compact = normalize_text(value)
    if len(compact) <= limit:
        return compact
    if limit <= 3:
        return compact[:limit]
    return compact[: limit - 3].rstrip() + "..."


def normalize_timestamp(value: str | None = None) -> str:
    if value:
        return normalize_text(value)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_telegram_url(url: str) -> bool:
    try:
        host = (urlsplit(normalize_source_url(url)).hostname or "").lower()
    except ValueError:
        return False
    return host in {"t.me", "telegram.me"} or host.endswith(".t.me")


def _record_from_failure(
    candidate: LinkedSourceCandidate,
    fetched_at: str,
    extraction_status: str,
    failure_reason: str,
) -> LinkedSourceCacheRecord:
    status = extraction_status if extraction_status in EXTRACTION_STATUSES else "failed"
    return LinkedSourceCacheRecord(
        source_url=candidate.source_url,
        normalized_url=candidate.normalized_url,
        source_type=candidate.source_type,
        fetched_at=normalize_timestamp(fetched_at),
        normalized_title="",
        content_hash="",
        extraction_status=status,
        redacted_failure_reason=redact_failure_reason(failure_reason),
        text_excerpt="",
        source_post_refs=candidate.source_post_refs,
    )


def redact_failure_reason(reason: object) -> str:
    redacted = normalize_text(reason)
    for pattern in _SECRET_PATTERNS:
        if pattern.pattern.startswith("(?i)\\bBearer"):
            redacted = pattern.sub("Bearer <redacted>", redacted)
        else:
            redacted = pattern.sub(r"\1=<redacted>", redacted)
    redacted = re.sub(r"<[^>]*>", "<redacted>", redacted)
    redacted = re.sub(r"https?://[^\s]+", "<url>", redacted)
    return bounded_excerpt(redacted or "unknown_failure", limit=360)


def _approval_refusal_reason(fetcher: LinkedSourceFetcher | None, approvals: LinkedSourceApprovals) -> str | None:
    if fetcher is None:
        return None
    reasons: list[str] = []
    if getattr(fetcher, "requires_live_http", False) and (
        not approvals.allow_live_http_fetch
        or approvals.max_live_fetches <= 0
        or not str(approvals.approval_ref or "").strip()
    ):
        reasons.append("live_http_fetch requires allow_live_http_fetch, max_live_fetches, and approval_ref")
    if getattr(fetcher, "requires_external_skill", False) and (
        not approvals.allow_external_skills or not approvals.approved_external_skill_trust_record
    ):
        reasons.append("external_skill requires allow_external_skills and approved trust record")
    if getattr(fetcher, "requires_provider_summarization", False) and (
        not approvals.allow_provider_summarization
        or approvals.max_provider_calls <= 0
        or approvals.approved_budget_usd <= 0
        or not str(approvals.approval_ref or "").strip()
    ):
        reasons.append(
            "provider_summarization requires allow_provider_summarization, max_provider_calls, approved_budget_usd, and approval_ref"
        )
    if reasons:
        return "approval_required: " + "; ".join(reasons)
    return None


def _fetcher_requires_external_boundary(fetcher: LinkedSourceFetcher) -> bool:
    return any(
        bool(getattr(fetcher, attr, False))
        for attr in ("requires_live_http", "requires_external_skill", "requires_provider_summarization")
    )


def _overall_status(
    candidates: Sequence[LinkedSourceCandidate],
    cache_records: Sequence[LinkedSourceCacheRecord],
) -> str:
    if not candidates:
        return "empty"
    statuses = {record.extraction_status for record in cache_records}
    if statuses == {"extracted"} and len(cache_records) >= len(candidates):
        return "ok"
    if "refused" in statuses:
        return "refused"
    if statuses.intersection({"failed", "not_fetched"}):
        return "partial"
    return "empty"


def _post_urls(post: Mapping[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("text", "content", "snippet", "message_text"):
        value = post.get(key)
        if isinstance(value, str):
            urls.extend(extract_urls(value))
    for key in ("linked_urls", "urls", "outbound_urls"):
        value = post.get(key)
        if isinstance(value, str):
            urls.extend(extract_urls(value))
        elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
            urls.extend(str(item) for item in value if str(item).strip())
    return _unique(_strip_url(url) for url in urls if _strip_url(url))


def _post_ref(post: Mapping[str, Any]) -> str:
    for key in ("archive_document_id", "source_url", "telegram_url", "message_url", "post_ref", "id"):
        value = post.get(key)
        if value is None:
            continue
        text = normalize_text(value)
        if text:
            return text
    return ""


def _strip_url(url: object) -> str:
    clean = str(url or "").strip()
    while clean and clean[-1] in _TRAILING_URL_PUNCTUATION:
        clean = clean[:-1]
    return clean


def _normalize_query(query: str) -> str:
    if not query:
        return ""
    kept = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        lower_key = key.lower()
        if lower_key in _TRACKING_QUERY_NAMES or lower_key.startswith(_TRACKING_QUERY_PREFIXES):
            continue
        kept.append((key, value))
    return urlencode(kept, doseq=True)


def _is_video(host: str, path: str) -> bool:
    return host in {"youtu.be", "youtube.com", "www.youtube.com", "vimeo.com", "www.vimeo.com", "loom.com", "www.loom.com"} or path.endswith(
        (".mp4", ".mov", ".webm")
    )


def _is_paper(host: str, path: str) -> bool:
    paper_hosts = {
        "arxiv.org",
        "www.arxiv.org",
        "doi.org",
        "www.doi.org",
        "openreview.net",
        "papers.ssrn.com",
        "aclanthology.org",
        "www.aclanthology.org",
        "semanticscholar.org",
        "www.semanticscholar.org",
    }
    return host in paper_hosts or path.endswith(".pdf") or "/paper/" in path or "/papers/" in path


def _is_docs(host: str, path: str) -> bool:
    return (
        host.startswith("docs.")
        or host.startswith("developer.")
        or host.endswith(".readthedocs.io")
        or host in {"readthedocs.io", "docs.python.org", "developer.mozilla.org"}
        or "/docs/" in path
        or path.startswith("/docs")
        or "/documentation/" in path
        or "/reference/" in path
        or path.startswith("/api/")
    )


def _is_product(host: str, path: str) -> bool:
    product_hosts = {
        "producthunt.com",
        "www.producthunt.com",
        "apps.apple.com",
        "play.google.com",
        "chromewebstore.google.com",
        "linear.app",
        "www.notion.so",
    }
    product_paths = ("/pricing", "/product", "/products", "/features", "/customers", "/enterprise", "/download")
    return host in product_hosts or path.startswith(product_paths) or any(marker in path for marker in ("/pricing/", "/features/"))


def _is_article(host: str, path: str) -> bool:
    article_hosts = {
        "medium.com",
        "www.medium.com",
        "substack.com",
        "dev.to",
        "hackernoon.com",
        "towardsdatascience.com",
    }
    article_markers = ("/blog/", "/posts/", "/post/", "/article/", "/articles/", "/news/", "/newsletter/")
    return (
        host in article_hosts
        or host.startswith("blog.")
        or host.endswith(".substack.com")
        or any(marker in path for marker in article_markers)
        or bool(re.search(r"/20\d{2}/", path))
    )


def _unique(values: Sequence[Any]) -> list[Any]:
    seen: set[str] = set()
    unique: list[Any] = []
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique


def _optional_text(value: object) -> str | None:
    text = normalize_text(value)
    return text or None
