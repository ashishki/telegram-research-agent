"""On-demand, capability-gated public web search and primary-source reads.

The module has no default provider instance.  Callers must supply both a
typed PA-02 ``PublicWebAccess`` and a concrete provider adapter; absent either,
the result is a truthful non-execution record.  It accepts no archive/profile
context and never turns search snippets into fetched primary-source evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
import hmac
import http.client
import ipaddress
import json
import re
import socket
from typing import Any, Mapping, Protocol, Sequence
from urllib import error, parse, request

from prm.capabilities import CapabilityDenied, require_authorized_operation
from prm.contracts import PublicWebAccess


PUBLIC_WEB_SCHEMA_VERSION = "prm_public_web_research.v1"
PUBLIC_WEB_PROVIDER_REF = "provider_public_web"
_MAX_QUERY_CHARS = 300
_MAX_TITLE_CHARS = 240
_MAX_SNIPPET_CHARS = 500
_MAX_EXCERPT_CHARS = 900
_ALLOWED_CONTENT_TYPES = frozenset({
    "text/html",
    "text/plain",
    "application/json",
    "application/xml",
})
# These are possession/context patterns, rather than generic subject words. A
# public current-fact question may legitimately be *about* Telegram or an
# archive product; rejecting it solely for that topic would encourage callers
# to work around the boundary. The application never derives this field from
# the operator's original text, and this check rejects the obvious private
# context forms that must never reach a public provider.
_PRIVATE_QUERY_MARKERS = (
    "my archive", "my profile", "my telegram", "my messages", "private archive",
    "telegram archive", "saved messages", "мой архив", "моем архиве", "моём архиве",
    "мой профиль", "мои сообщения", "телеграм-архив", "telegram-архив",
)
_INSTRUCTION_MARKERS = (
    "ignore previous", "ignore all", "system message", "developer message", "assistant instruction",
    "игнорируй предыдущ", "системное сообщение", "инструкция для ассистента",
)
_TAG_RE = re.compile(r"<[^>]{0,1000}>")
_SPACE_RE = re.compile(r"\s+")


class PublicWebTransportError(RuntimeError):
    """A public web provider failed without exposing transport details."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PublicWebProvider(Protocol):
    """A provider adapter with separate discovery and source-read operations."""

    def search_public(self, query: str, *, bounds: "PublicWebBounds") -> Sequence[Mapping[str, Any]]: ...

    def fetch_public(self, source_ref: str, *, bounds: "PublicWebBounds") -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class PublicWebBounds:
    """Fixed ceilings and exact trusted primary-source hosts for one request."""

    trusted_source_hosts: tuple[str, ...]
    max_search_results: int = 8
    max_fetches: int = 3
    timeout_seconds: float = 15.0
    max_response_bytes: int = 512_000
    max_source_age_days: int = 30

    def __post_init__(self) -> None:
        if not self.trusted_source_hosts or len(self.trusted_source_hosts) > 16:
            raise ValueError("public web bounds require bounded trusted hosts")
        normalized = tuple(_normalize_host(host) for host in self.trusted_source_hosts)
        if any(host is None for host in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("public web bounds require canonical unique hosts")
        object.__setattr__(self, "trusted_source_hosts", tuple(str(host) for host in normalized))
        if not 1 <= self.max_search_results <= 20 or not 1 <= self.max_fetches <= 4:
            raise ValueError("public web bounds exceed fixed request limits")
        if not 1.0 <= float(self.timeout_seconds) <= 30.0:
            raise ValueError("public web timeout is out of range")
        if not 4_096 <= self.max_response_bytes <= 1_000_000:
            raise ValueError("public web response limit is out of range")
        if not 1 <= self.max_source_age_days <= 365:
            raise ValueError("public web freshness bound is out of range")


class HttpPublicWebProvider:
    """A small JSON-search/HTTPS-fetch adapter for an explicitly wired runtime.

    It is inert until an application injects an instance and supplies an active
    ``PublicWebAccess``.  The endpoint is configuration owned by that runtime,
    never taken from a user request.  This adapter intentionally follows no
    redirects and performs DNS checks before every socket-opening operation.
    """

    def __init__(self, *, search_endpoint: str) -> None:
        _validate_https_url(search_endpoint)
        self._search_endpoint = search_endpoint

    def search_public(self, query: str, *, bounds: PublicWebBounds) -> Sequence[Mapping[str, Any]]:
        endpoint = _append_query(self._search_endpoint, query)
        response = _https_get(endpoint, timeout_seconds=bounds.timeout_seconds, max_bytes=bounds.max_response_bytes)
        if response["content_type"] != "application/json":
            raise PublicWebTransportError("search_content_type")
        try:
            decoded = json.loads(response["body"].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PublicWebTransportError("search_payload") from exc
        rows = decoded.get("results") if isinstance(decoded, Mapping) else None
        if not isinstance(rows, list):
            raise PublicWebTransportError("search_payload")
        return [dict(row) for row in rows if isinstance(row, Mapping)][:bounds.max_search_results]

    def fetch_public(self, source_ref: str, *, bounds: PublicWebBounds) -> Mapping[str, Any]:
        response = _https_get(source_ref, timeout_seconds=bounds.timeout_seconds, max_bytes=bounds.max_response_bytes)
        return {
            "status": response["status"],
            "final_url": response["final_url"],
            "headers": response["headers"],
            "body": response["body"],
            # Only a source's explicit modification/publication metadata may
            # establish freshness. The HTTP response Date is transport timing,
            # not evidence that the document itself is current.
            "published_at": response["headers"].get("last-modified"),
        }


def execute_public_web_research(
    *,
    public_query: str,
    original_query: str,
    access: PublicWebAccess | None,
    provider: PublicWebProvider | None,
    bounds: PublicWebBounds | None,
) -> dict[str, Any]:
    """Search and read only explicitly scoped public primary sources.

    ``original_query`` is used solely to reject a private query being mirrored
    into the public-query field; it is never sent to a provider or returned.
    Returned excerpts are untrusted evidence data, not executable instructions.
    """

    query_status = _validate_public_query(public_query, original_query=original_query)
    if query_status != "accepted":
        _abandon_access(access)
        return _result(status=query_status, access=access, bounds=bounds, provider_supplied=provider is not None)
    if type(access) is not PublicWebAccess:
        return _result(status="authorization_required", access=access, bounds=bounds, provider_supplied=provider is not None)
    if not hmac.compare_digest(_public_query_digest(public_query), access.public_query_digest):
        _abandon_access(access)
        return _result(status="public_query_scope_mismatch", access=access, bounds=bounds, provider_supplied=provider is not None)
    if provider is None or bounds is None:
        _abandon_access(access)
        return _result(status="provider_unavailable", access=access, bounds=bounds, provider_supplied=provider is not None)

    try:
        _consume_search(access)
        raw_hits = provider.search_public(public_query, bounds=bounds)
    except (CapabilityDenied, PublicWebTransportError):
        _abandon_access(access)
        return _result(status="search_unavailable", access=access, bounds=bounds, provider_supplied=True)
    except Exception:
        _abandon_access(access)
        return _result(status="search_failed", access=access, bounds=bounds, provider_supplied=True)

    search_hits = _normalize_search_hits(raw_hits, bounds=bounds)
    fetch_limit = min(bounds.max_fetches, len(access.fetch_authorizations))
    candidates = [item for item in search_hits if item["primary_source_candidate"]][:fetch_limit]
    fetched: list[dict[str, Any]] = []
    gaps: list[str] = []
    for index, candidate in enumerate(candidates):
        try:
            _consume_fetch(access, index=index)
            fetched.append(_fetch_candidate(provider, candidate, bounds=bounds))
        except (CapabilityDenied, PublicWebTransportError) as exc:
            fetched.append({"source_url": candidate["source_url"], "status": "fetch_unavailable", "error": type(exc).__name__})
            gaps.append("primary_source_fetch_unavailable")
        except Exception as exc:
            fetched.append({"source_url": candidate["source_url"], "status": "fetch_failed", "error": type(exc).__name__})
            gaps.append("primary_source_fetch_failed")
    _abandon_unused_fetches(access, used=len(candidates))

    accepted = [item for item in fetched if item.get("status") == "fetched"]
    fresh = [item for item in accepted if item.get("freshness") == "fresh"]
    conflicts = _conflicts(fresh)
    if conflicts:
        status = "conflicting_primary_evidence"
        gaps.append("conflicting_primary_sources")
    elif fresh and not gaps and len(accepted) == len(candidates):
        status = "verified_current_evidence"
    elif fresh or accepted:
        status = "partial_primary_evidence"
        gaps.append("incomplete_or_stale_primary_coverage")
    else:
        status = "insufficient_primary_evidence"
        gaps.append("no_fresh_primary_evidence")
    return {
        **_result(status=status, access=access, bounds=bounds, provider_supplied=True),
        "search": {
            "performed": True,
            "result_count": len(search_hits),
            "primary_candidate_count": len(candidates),
            "query_logged": False,
        },
        "search_hits": search_hits,
        "fetched_sources": fetched,
        "evidence_items": fresh if status == "verified_current_evidence" else [],
        "coverage": {
            "status": status,
            "fresh_primary_source_count": len(fresh),
            "fetched_primary_source_count": len(accepted),
            "conflict_count": len(conflicts),
            "gaps": list(dict.fromkeys(gaps)),
        },
        "conflicts": conflicts,
    }


def render_public_web_answer(result: Mapping[str, Any]) -> str:
    """Render evidence/gaps without treating a search snippet as a document."""

    status = str(result.get("status") or "public_web_unavailable")
    evidence = [item for item in result.get("evidence_items") or [] if isinstance(item, Mapping)]
    if status == "verified_current_evidence" and evidence:
        first = evidence[0]
        return "\n".join((
            # Keep the sole factual sentence byte-for-byte within the fetched
            # source span. Presentation metadata on a separate line binds its
            # visible URL without becoming an unsupported factual claim.
            str(first.get("support_span") or ""),
            "Источник: " + str(first.get("source_url") or ""),
        ))
    if status == "conflicting_primary_evidence":
        refs = [str(item.get("source_url") or "") for item in result.get("fetched_sources") or [] if isinstance(item, Mapping)]
        return "Я не могу подтвердить актуальный внешний факт: первоисточники расходятся. Источники: " + ", ".join(refs[:4])
    coverage = result.get("coverage") if isinstance(result.get("coverage"), Mapping) else {}
    gaps = ", ".join(str(item) for item in coverage.get("gaps") or [] if str(item)) or "public_verification_not_completed"
    return "Я не могу подтвердить актуальный внешний факт: " + gaps


def _result(
    *,
    status: str,
    access: object,
    bounds: PublicWebBounds | None,
    provider_supplied: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": PUBLIC_WEB_SCHEMA_VERSION,
        "status": status,
        "search": {"performed": False, "query_logged": False},
        "search_hits": [],
        "fetched_sources": [],
        "evidence_items": [],
        "coverage": {"status": status, "fresh_primary_source_count": 0, "fetched_primary_source_count": 0, "conflict_count": 0, "gaps": [status]},
        "conflicts": [],
        "privacy": {
            "original_query_sent": False,
            "private_archive_sent": False,
            "provider_payload_logged": False,
            # A typed grant is not evidence that an adapter, credential or
            # live account is configured. This is deliberately only a
            # per-call dependency fact (and remains false for the default
            # application instance).
            "provider_adapter_supplied": provider_supplied,
            "bounds_configured": bounds is not None,
        },
        "write_performed": False,
    }


def _validate_public_query(public_query: str, *, original_query: str) -> str:
    clean = _compact(public_query)
    if len(clean) < 3 or len(clean) > _MAX_QUERY_CHARS:
        return "public_query_required"
    lowered = clean.casefold()
    if any(marker in lowered for marker in _PRIVATE_QUERY_MARKERS):
        return "private_public_query_rejected"
    original = _compact(original_query).casefold()
    if any(marker in original for marker in _PRIVATE_QUERY_MARKERS) and clean.casefold() == original:
        return "private_public_query_rejected"
    return "accepted"


def _consume_search(access: PublicWebAccess) -> None:
    require_authorized_operation(
        access.search_authorization,
        capability="web.search",
        operation="read",
        provider_ref=PUBLIC_WEB_PROVIDER_REF,
        data_class="public",
        owner_ref=access.owner_ref,
        connection_ref=access.connection_ref,
        resource_ref=access.search_resource_ref,
        purpose="public.search",
    )


def _consume_fetch(access: PublicWebAccess, *, index: int) -> None:
    require_authorized_operation(
        access.fetch_authorizations[index],
        capability="web.fetch",
        operation="read",
        provider_ref=PUBLIC_WEB_PROVIDER_REF,
        data_class="public",
        owner_ref=access.owner_ref,
        connection_ref=access.connection_ref,
        resource_ref=access.fetch_resource_ref,
        purpose="public.fetch",
    )


def _abandon_access(access: object) -> None:
    if type(access) is not PublicWebAccess:
        return
    for decision in (access.search_authorization, *access.fetch_authorizations):
        if decision.reservation is not None:
            decision.reservation.abandon_before_transport()


def _abandon_unused_fetches(access: PublicWebAccess, *, used: int) -> None:
    for decision in access.fetch_authorizations[used:]:
        if decision.reservation is not None:
            decision.reservation.abandon_before_transport()


def _normalize_search_hits(value: object, *, bounds: PublicWebBounds) -> list[dict[str, Any]]:
    rows = value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        source_url = str(row.get("source_url") or row.get("url") or "").strip()
        try:
            parsed = _validate_https_url(source_url)
        except PublicWebTransportError:
            continue
        normalized = parsed.geturl()
        if normalized in seen:
            continue
        seen.add(normalized)
        host = str(parsed.hostname or "").casefold()
        result.append({
            "source_url": normalized,
            "title": _bounded(row.get("title"), _MAX_TITLE_CHARS),
            "snippet": _bounded(row.get("snippet") or row.get("summary"), _MAX_SNIPPET_CHARS),
            "coverage": "search_snippet_only",
            # The caller's bounded allowlist is the only discovery-to-fetch
            # bridge. A plausible public host is not a primary source for this
            # question unless the caller explicitly scoped it.
            "primary_source_candidate": host in bounds.trusted_source_hosts,
            "untrusted_content": True,
        })
        if len(result) >= bounds.max_search_results:
            break
    return result


def _fetch_candidate(provider: PublicWebProvider, candidate: Mapping[str, Any], *, bounds: PublicWebBounds) -> dict[str, Any]:
    source_url = str(candidate.get("source_url") or "")
    source = _validate_https_url(source_url)
    if str(source.hostname or "").casefold() not in bounds.trusted_source_hosts:
        raise PublicWebTransportError("source_not_allowlisted")
    _reject_private_resolution(str(source.hostname or ""))
    raw = provider.fetch_public(source_url, bounds=bounds)
    if not isinstance(raw, Mapping):
        raise PublicWebTransportError("fetch_payload")
    status = int(raw.get("status") or 0)
    final_url = str(raw.get("final_url") or source_url)
    final = _validate_https_url(final_url)
    _reject_private_resolution(str(final.hostname or ""))
    if final.geturl() != source.geturl() or final.hostname != source.hostname or final.port != source.port:
        raise PublicWebTransportError("redirect_rejected")
    headers = {str(key).casefold(): str(value) for key, value in dict(raw.get("headers") or {}).items()}
    body = raw.get("body")
    if not isinstance(body, bytes):
        raise PublicWebTransportError("fetch_body")
    content_type = str(headers.get("content-type") or "").split(";", 1)[0].strip().casefold()
    if status < 200 or status >= 400:
        raise PublicWebTransportError("http_status")
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise PublicWebTransportError("content_type")
    if len(body) > bounds.max_response_bytes:
        raise PublicWebTransportError("response_too_large")
    excerpt = _safe_excerpt(body, content_type=content_type)
    if _looks_like_instruction(excerpt):
        return {
            "source_url": source_url,
            "final_url": final_url,
            "status": "untrusted_source_instruction",
            "coverage": "source_excluded",
            "content_hash": "sha256:" + hashlib.sha256(body).hexdigest(),
        }
    published_at = raw.get("published_at") or headers.get("last-modified")
    freshness = _freshness(published_at, max_age_days=bounds.max_source_age_days)
    return {
        "evidence_id": "public:" + hashlib.sha256((source_url + "\x1f" + hashlib.sha256(body).hexdigest()).encode("utf-8")).hexdigest()[:24],
        "source_url": source_url,
        "final_url": final_url,
        "source_kind": "public_web",
        "source_group_id": str(source.hostname or "").casefold(),
        "status": "fetched",
        "coverage": "fetched_primary_source",
        "support_span": excerpt,
        "content_hash": "sha256:" + hashlib.sha256(body).hexdigest(),
        "content_type": content_type,
        "content_bytes": len(body),
        "published_at": _timestamp(published_at),
        "fetched_at": _now(),
        "freshness": freshness,
        "freshness_status": freshness,
        "access_scope": "public_primary_source",
    }


def _conflicts(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    fingerprints = {
        hashlib.sha256(_compact(str(item.get("support_span") or "")).casefold().encode("utf-8")).hexdigest(): str(item.get("source_url") or "")
        for item in items
        if str(item.get("support_span") or "")
    }
    if len(fingerprints) <= 1:
        return []
    return [{"status": "conflicting_primary_source_content", "source_refs": sorted(fingerprints.values())[:4]}]


def _freshness(value: object, *, max_age_days: int) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return "unknown"
    age = datetime.now(timezone.utc) - parsed
    if age < timedelta(days=0) or age > timedelta(days=max_age_days):
        return "stale"
    return "fresh"


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


def _timestamp(value: object) -> str | None:
    parsed = _parse_timestamp(value)
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z") if parsed is not None else None


def _safe_excerpt(body: bytes, *, content_type: str) -> str:
    text = body[:80_000].decode("utf-8", errors="ignore")
    if content_type == "text/html":
        text = _TAG_RE.sub(" ", text)
    return _bounded(html.unescape(text), _MAX_EXCERPT_CHARS)


def _looks_like_instruction(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in _INSTRUCTION_MARKERS)


def _validate_https_url(value: str) -> parse.ParseResult:
    try:
        parsed = parse.urlparse(value)
        port = parsed.port
    except ValueError as exc:
        raise PublicWebTransportError("invalid_url") from exc
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or port not in {None, 443}:
        raise PublicWebTransportError("invalid_url")
    raw_host = _normalize_host(parsed.hostname)
    if raw_host is None or raw_host != parsed.hostname.casefold():
        raise PublicWebTransportError("noncanonical_host")
    return parsed


def _normalize_host(value: object) -> str | None:
    if not isinstance(value, str) or not value or not value.isascii():
        return None
    host = value.casefold()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return None
    labels = host.split(".")
    if len(labels) < 2 or any(
        not label or len(label) > 63 or not label[0].isalnum() or not label[-1].isalnum()
        or any(not (character.isalnum() or character == "-") for character in label)
        for label in labels
    ):
        return None
    return host


def _reject_private_resolution(host: str) -> None:
    _resolve_public_addresses(host)


def _resolve_public_addresses(host: str) -> tuple[tuple[int, tuple[Any, ...]], ...]:
    """Resolve once, reject unsafe addresses, and retain the exact dial set.

    ``urllib`` would otherwise resolve a hostname again while opening the TLS
    socket. Returning the approved address tuple lets ``_https_get`` bind the
    actual TCP dial to the checked resolution instead of making DNS validation
    merely advisory.
    """
    try:
        results = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise PublicWebTransportError("dns") from exc
    if not results:
        raise PublicWebTransportError("dns")
    accepted: list[tuple[int, tuple[Any, ...]]] = []
    for result in results:
        address = ipaddress.ip_address(result[4][0])
        if not address.is_global:
            raise PublicWebTransportError("unsafe_dns")
        candidate = (int(result[0]), tuple(result[4]))
        if candidate not in accepted:
            accepted.append(candidate)
    return tuple(accepted)


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PublicWebTransportError("redirect_rejected")


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """TLS connection whose TCP peer is an already-validated DNS address."""

    def __init__(self, host: str, *, approved_addresses: tuple[tuple[int, tuple[Any, ...]], ...], **kwargs: Any) -> None:
        self._approved_addresses = approved_addresses
        super().__init__(host, **kwargs)

    def connect(self) -> None:
        last_error: OSError | None = None
        raw_socket: socket.socket | None = None
        for family, sockaddr in self._approved_addresses:
            candidate: socket.socket | None = None
            try:
                candidate = socket.socket(family, socket.SOCK_STREAM)
                candidate.settimeout(self.timeout)
                candidate.connect(sockaddr)
                raw_socket = candidate
                break
            except OSError as exc:
                last_error = exc
                if candidate is not None:
                    candidate.close()
        if raw_socket is None:
            raise PublicWebTransportError("transport") from last_error
        try:
            # ``self.host`` remains the canonical hostname for SNI and
            # certificate validation; only the TCP peer is pinned.
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except OSError:
            raw_socket.close()
            raise


class _PinnedHTTPSHandler(request.HTTPSHandler):
    """Use a no-proxy HTTPS connection that cannot re-resolve a hostname."""

    handler_order = 400

    def __init__(self, *, approved_addresses: tuple[tuple[int, tuple[Any, ...]], ...]) -> None:
        super().__init__()
        self._approved_addresses = approved_addresses

    def https_open(self, req: request.Request):
        return self.do_open(
            lambda host, **kwargs: _PinnedHTTPSConnection(host, approved_addresses=self._approved_addresses, **kwargs),
            req,
            context=self._context,
            check_hostname=self._check_hostname,
        )


def _https_get(url: str, *, timeout_seconds: float, max_bytes: int) -> dict[str, Any]:
    parsed = _validate_https_url(url)
    addresses = _resolve_public_addresses(str(parsed.hostname or ""))
    # Ambient proxy configuration can point a request at a local endpoint.
    # This transport never inherits it: public egress uses the validated TLS
    # destination directly.
    opener = request.build_opener(
        request.ProxyHandler({}),
        _NoRedirect(),
        _PinnedHTTPSHandler(approved_addresses=addresses),
    )
    req = request.Request(url, headers={"User-Agent": "telegram-research-agent-public-web/1", "Accept": "application/json,text/html,text/plain,application/xml"})
    try:
        response = opener.open(req, timeout=timeout_seconds)
    except PublicWebTransportError:
        raise
    except error.HTTPError as exc:
        raise PublicWebTransportError("rate_limited" if exc.code == 429 else "http_status") from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise PublicWebTransportError("transport") from exc
    with response:
        final_url = str(response.geturl() or url)
        final = _validate_https_url(final_url)
        if final.geturl() != parsed.geturl() or final.hostname != parsed.hostname or final.port != parsed.port:
            raise PublicWebTransportError("redirect_rejected")
        content_type = str(response.headers.get_content_type() or "").casefold()
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise PublicWebTransportError("response_too_large")
        headers = {key.lower(): value for key, value in response.headers.items() if key.lower() in {"content-type", "last-modified", "date", "etag"}}
        return {"status": int(getattr(response, "status", 200)), "final_url": final_url, "content_type": content_type, "headers": headers, "body": body}


def _append_query(endpoint: str, query: str) -> str:
    parsed = parse.urlparse(endpoint)
    params = parse.parse_qsl(parsed.query, keep_blank_values=True)
    params.append(("q", query))
    return parse.urlunparse(parsed._replace(query=parse.urlencode(params)))


def _compact(value: object) -> str:
    return _SPACE_RE.sub(" ", str(value or "")).strip()


def _public_query_digest(query: str) -> str:
    """Return a scope-binding digest without retaining/logging the query."""

    return "sha256:" + hashlib.sha256(_compact(query).encode("utf-8")).hexdigest()


def _bounded(value: object, limit: int) -> str:
    return _compact(value)[:limit]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
