"""Bounded primary-source verification planning and gated fetching."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urljoin, urlparse


PRIMARY_SOURCE_VERIFICATION_SCHEMA_VERSION = "prm_primary_source_verification.v1"
PRIMARY_SOURCE_FETCH_SCHEMA_VERSION = "prm_primary_source_fetch.v1"
_DEFAULT_CACHE_DIR = Path("data/evals/private/prm_qa/verification_cache")
_CACHE_TTL = timedelta(hours=24)
_MAX_RESPONSE_BYTES = 512_000
_TIMEOUT_SECONDS = 8.0
_REDIRECT_LIMIT = 3
_CONTENT_TYPE_ALLOWLIST = (
    "text/html",
    "text/plain",
    "application/json",
    "application/pdf",
    "application/xml",
)


def build_primary_source_verification_plan(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Create an operator-visible plan; this function never performs a fetch."""

    approvals = _mapping(payload.get("approvals"))
    telegram_sources = _source_refs(payload.get("telegram_source_refs"))
    candidates = _prioritize_primary_sources(payload.get("candidate_source_urls") or [])
    approved = bool(approvals.get("live_fetch_approved")) and bool(approvals.get("trust_record_approved"))
    return {
        "schema_version": PRIMARY_SOURCE_VERIFICATION_SCHEMA_VERSION,
        "status": "verification_planned" if approved else "verification_required_not_run",
        "telegram_signal": {"evidence_class": "discovery_context", "source_refs": telegram_sources},
        "primary_source_plan": candidates,
        "independent_confirmation": {"status": "not_run", "source_refs": []},
        "live_fetch": {
            "performed": False,
            "approval_required": True,
            "trust_record_required": True,
            "approved": approved,
        },
        "next_approval_step": (
            "Заполнить и утвердить trust record, затем отдельно утвердить ограниченный live fetch."
            if not approved
            else "Выполнить отдельно утвержденную ограниченную проверку первоисточников."
        ),
        "write_performed": False,
    }


def execute_primary_source_verification(
    payload: Mapping[str, Any],
    *,
    transport: Any | None = None,
    cache_dir: str | Path | None = None,
    allow_live_fetch: bool = False,
) -> dict[str, Any]:
    """Run a bounded primary-source verification only after explicit approval.

    Tests should pass a fake transport.  Live network fetch remains disabled
    unless both payload approvals and allow_live_fetch are true.
    """

    plan = build_primary_source_verification_plan(payload)
    if not bool(plan["live_fetch"]["approved"]) or (transport is None and not allow_live_fetch):
        return {**plan, "fetch_results": [], "status": "verification_required_not_run"}
    cache_root = Path(cache_dir or _DEFAULT_CACHE_DIR)
    results = []
    for candidate in plan["primary_source_plan"][:4]:
        source_url = candidate["source_url"]
        classification = classify_trusted_source(source_url, official_relation=candidate.get("evidence_class") == "official_or_github")
        if classification["safety_status"] != "accepted":
            results.append({**classification, "source_url": source_url, "status": "rejected"})
            continue
        cached = _read_cache(cache_root, source_url)
        if cached is not None:
            results.append(cached)
            continue
        try:
            fetched = _fetch_with_transport(source_url, transport=transport) if transport is not None else _fetch_live(source_url)
        except Exception as exc:
            results.append(
                {
                    "schema_version": PRIMARY_SOURCE_FETCH_SCHEMA_VERSION,
                    "source_url": source_url,
                    "status": "fetch_failed",
                    "error_type": type(exc).__name__,
                    "evidence_class": classification["evidence_class"],
                    "fetched_at": _now(),
                    "write_performed": False,
                }
            )
            continue
        result = {
            "schema_version": PRIMARY_SOURCE_FETCH_SCHEMA_VERSION,
            "source_url": source_url,
            "final_url": fetched["final_url"],
            "status": "fetched",
            "http_status": int(fetched["status"]),
            "content_type": fetched["content_type"],
            "content_bytes": len(fetched["body"]),
            "content_hash": "sha256:" + hashlib.sha256(fetched["body"]).hexdigest(),
            "fetched_at": _now(),
            "cache_ttl_seconds": int(_CACHE_TTL.total_seconds()),
            "evidence_class": classification["evidence_class"],
            "primary_source_status": classification["primary_source_status"],
            "github_repository": _github_repository_summary(source_url, fetched["body"]) if classification["evidence_class"] == "github_repository" else {},
            "privacy": {"provider_egress": False, "third_party_code_executed": False, "cache_gitignored": True},
            "write_performed": False,
        }
        _write_cache(cache_root, source_url, result)
        results.append(result)
    return {
        **plan,
        "status": "verification_fetched" if results else "verification_required_not_run",
        "fetch_results": results,
        "live_fetch": {**plan["live_fetch"], "performed": bool(results), "allow_live_fetch_runtime": bool(allow_live_fetch), "response_size_cap_bytes": _MAX_RESPONSE_BYTES},
        "write_performed": False,
    }


def classify_trusted_source(url: str, *, official_relation: bool = False) -> dict[str, str]:
    validation = _validate_candidate_url(url)
    parsed = urlparse(url)
    host = str(parsed.hostname or "").casefold()
    if validation != "accepted":
        return {"source_url": url, "safety_status": validation, "evidence_class": "unknown", "primary_source_status": "rejected"}
    if host == "github.com" or host.endswith(".github.com"):
        return {"source_url": url, "safety_status": "accepted", "evidence_class": "github_repository", "primary_source_status": "primary_or_official"}
    if host == "arxiv.org" or host.endswith(".arxiv.org"):
        return {"source_url": url, "safety_status": "accepted", "evidence_class": "research_paper", "primary_source_status": "primary_or_official"}
    if official_relation and ("docs." in host or "/docs" in parsed.path.casefold()):
        return {"source_url": url, "safety_status": "accepted", "evidence_class": "official_documentation", "primary_source_status": "primary_or_official"}
    if official_relation:
        return {"source_url": url, "safety_status": "accepted", "evidence_class": "official_vendor_announcement", "primary_source_status": "primary_or_official"}
    return {"source_url": url, "safety_status": "accepted", "evidence_class": "unknown", "primary_source_status": "unverified_relation"}


def render_primary_source_verification_answer(payload: Mapping[str, Any]) -> str:
    """Render the required evidence classes without claiming a verification result."""

    plan = build_primary_source_verification_plan(payload)
    primary = plan["primary_source_plan"]
    lines = [
        "Telegram-сигнал: " + _render_refs(plan["telegram_signal"]["source_refs"]),
        "Первоисточник: " + _render_urls(primary),
        "Независимое подтверждение: не выполнено.",
        "Изменившиеся факты: не установлены.",
        "Неизвестно: актуальные факты и независимое подтверждение.",
        "Пересмотренная рекомендация: " + plan["next_approval_step"],
    ]
    return "\n".join(lines)


def _prioritize_primary_sources(urls: Sequence[object]) -> list[dict[str, str]]:
    candidates = []
    for value in urls:
        raw = _mapping(value)
        url = str(raw.get("source_url") or raw.get("url") or value or "").strip()
        validation = _validate_candidate_url(url)
        if validation != "accepted":
            continue
        host = str(urlparse(url).hostname or "").casefold()
        official_relation = bool(raw.get("official_relation"))
        github_host = host == "github.com" or host.endswith(".github.com")
        research_host = host == "arxiv.org" or host.endswith(".arxiv.org")
        source_class = "official_or_github" if github_host or research_host or official_relation else "other"
        candidates.append({"source_url": url, "evidence_class": source_class})
    return sorted(candidates, key=lambda item: (item["evidence_class"] != "official_or_github", item["source_url"]))


def _source_refs(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _render_refs(refs: Sequence[str]) -> str:
    return ", ".join(refs) if refs else "нет локальных ссылок"


def _render_urls(sources: Sequence[Mapping[str, str]]) -> str:
    return ", ".join(item["source_url"] for item in sources) if sources else "не выбран"


def _validate_candidate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return "invalid_url"
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return "accepted"
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
        return "private_address"
    return "accepted"


def _fetch_with_transport(url: str, *, transport: Any) -> dict[str, Any]:
    fetched = transport(url)
    status = int(fetched.get("status") or 0)
    headers = {str(key).casefold(): str(value) for key, value in dict(fetched.get("headers") or {}).items()}
    body = bytes(fetched.get("body") or b"")
    final_url = str(fetched.get("final_url") or url)
    _validate_fetch_response(final_url, status=status, headers=headers, body=body)
    return {"status": status, "headers": headers, "body": body, "final_url": final_url, "content_type": _content_type(headers)}


def _fetch_live(url: str) -> dict[str, Any]:
    current = url
    context = ssl.create_default_context()
    for _ in range(_REDIRECT_LIMIT + 1):
        _validate_network_destination(current)
        request = urllib.request.Request(current, headers={"User-Agent": "PRMPrimarySourceVerifier/1.0"})
        opener = urllib.request.build_opener(_NoRedirectHandler(), urllib.request.HTTPSHandler(context=context))
        try:
            with opener.open(request, timeout=_TIMEOUT_SECONDS) as response:
                headers = {str(key).casefold(): str(value) for key, value in response.headers.items()}
                body = response.read(_MAX_RESPONSE_BYTES + 1)
                status = int(getattr(response, "status", 200))
        except urllib.error.HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                location = exc.headers.get("Location")
                if not location:
                    raise
                current = urljoin(current, location)
                continue
            headers = {str(key).casefold(): str(value) for key, value in exc.headers.items()}
            body = exc.read(_MAX_RESPONSE_BYTES + 1)
            status = int(exc.code)
        _validate_fetch_response(current, status=status, headers=headers, body=body)
        return {"status": status, "headers": headers, "body": bytes(body), "final_url": current, "content_type": _content_type(headers)}
    raise ValueError("redirect_limit_exceeded")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _validate_network_destination(url: str) -> None:
    validation = _validate_candidate_url(url)
    if validation != "accepted":
        raise ValueError(validation)
    host = str(urlparse(url).hostname or "")
    for family, _type, _proto, _canon, sockaddr in socket.getaddrinfo(host, 443):
        address = ipaddress.ip_address(sockaddr[0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise ValueError("unsafe_dns_result")


def _validate_fetch_response(url: str, *, status: int, headers: Mapping[str, str], body: bytes) -> None:
    if _validate_candidate_url(url) != "accepted":
        raise ValueError("unsafe_final_url")
    if len(body) > _MAX_RESPONSE_BYTES:
        raise ValueError("response_too_large")
    content_type = _content_type(headers)
    if content_type and not any(content_type.startswith(allowed) for allowed in _CONTENT_TYPE_ALLOWLIST):
        raise ValueError("unsupported_content_type")
    if status < 200 or status >= 400:
        raise ValueError("http_status_not_ok")


def _content_type(headers: Mapping[str, str]) -> str:
    return str(headers.get("content-type") or "").split(";")[0].strip().casefold()


def _github_repository_summary(url: str, body: bytes) -> dict[str, Any]:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return {}
    text = body[:80_000].decode("utf-8", errors="ignore").casefold()
    return {
        "repository": f"{parts[0]}/{parts[1]}",
        "readme_present": "readme" in text,
        "license_mentioned": "license" in text or "licence" in text,
        "ci_present": ".github/workflows" in text or "github actions" in text,
        "tests_mentioned": "pytest" in text or "npm test" in text or "tests/" in text,
        "third_party_code_executed": False,
    }


def _read_cache(cache_root: Path, url: str) -> dict[str, Any] | None:
    path = _cache_path(cache_root, url)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    fetched_at = str(payload.get("fetched_at") or "")
    try:
        parsed = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if datetime.now(timezone.utc) - parsed > _CACHE_TTL:
        return None
    payload["cache_hit"] = True
    return payload


def _write_cache(cache_root: Path, url: str, payload: Mapping[str, Any]) -> None:
    cache_root.mkdir(parents=True, exist_ok=True)
    _cache_path(cache_root, url).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _cache_path(cache_root: Path, url: str) -> Path:
    return cache_root / (hashlib.sha256(url.encode()).hexdigest() + ".json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
