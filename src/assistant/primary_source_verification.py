"""Bounded primary-source verification planning and gated fetching."""

from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from assistant.claim_ledger import build_claim_ledger, claim_ledger_public_summary
from assistant.evidence_quality import build_evidence_quality_items


PRIMARY_SOURCE_VERIFICATION_SCHEMA_VERSION = "prm_primary_source_verification.v1"
PRIMARY_SOURCE_FETCH_SCHEMA_VERSION = "prm_primary_source_fetch.v1"
_CACHE_TTL = timedelta(hours=24)
_MAX_RESPONSE_BYTES = 512_000
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
    trusted_hosts = _trusted_hosts(approvals.get("trusted_hosts"))
    candidates = _prioritize_primary_sources(payload.get("candidate_source_urls") or [], trusted_hosts=trusted_hosts)
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
    fixture_responses: Mapping[str, Mapping[str, Any]] | None = None,
    cache_dir: str | Path | None = None,
    allow_live_fetch: bool = False,
) -> dict[str, Any]:
    """Run a bounded primary-source verification only after explicit approval.

    Tests must pass declarative fixture responses. Live network fetching is
    deliberately absent; ``allow_live_fetch`` is retained only for compatible
    callers and cannot enable any I/O.
    """

    plan = build_primary_source_verification_plan(payload)
    if not bool(plan["live_fetch"]["approved"]) or fixture_responses is None:
        return {**plan, "fetch_results": [], "status": "verification_required_not_run"}
    # A cache is a caller-supplied fixture artifact only.  In particular, do
    # not create a default data/ cache as a side effect of this local plan.
    cache_root = Path(cache_dir) if cache_dir is not None else None
    results = []
    for candidate in plan["primary_source_plan"][:4]:
        source_url = candidate["source_url"]
        if candidate.get("evidence_class") != "official_or_github":
            results.append({"source_url": source_url, "status": "untrusted_candidate"})
            continue
        classification = classify_trusted_source(source_url, official_relation=candidate.get("evidence_class") == "official_or_github")
        if classification["safety_status"] != "accepted" or classification["primary_source_status"] != "primary_or_official":
            results.append({**classification, "source_url": source_url, "status": "rejected"})
            continue
        cached = _read_cache(cache_root, source_url) if cache_root is not None else None
        if cached is not None and not _valid_cached_fetch(cached, source_url=source_url, classification=classification):
            cached = None
        if cached is not None:
            results.append({**cached, "status": "cached_fixture", "cache_hit": True})
            continue
        try:
            fetched = _fetch_fixture(source_url, fixture_responses=fixture_responses)
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
        final_classification = classify_trusted_source(
            fetched["final_url"], official_relation=candidate.get("evidence_class") == "official_or_github"
        )
        source_host = str(urlparse(source_url).hostname or "").casefold()
        final_host = str(urlparse(fetched["final_url"]).hostname or "").casefold()
        if (
            final_classification["safety_status"] != "accepted"
            or final_classification["evidence_class"] != classification["evidence_class"]
            or final_host != source_host
            or _explicit_https_port(fetched["final_url"]) != _explicit_https_port(source_url)
        ):
            results.append({**final_classification, "source_url": source_url, "final_url": fetched["final_url"], "status": "rejected_redirect"})
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
            "text_excerpt": _text_excerpt(fetched["body"]),
            "fetched_at": _now(),
            "cache_ttl_seconds": int(_CACHE_TTL.total_seconds()),
            "evidence_class": classification["evidence_class"],
            "primary_source_status": classification["primary_source_status"],
            "github_repository": _github_repository_summary(source_url, fetched["body"]) if classification["evidence_class"] == "github_repository" else {},
            "privacy": {
                "provider_egress": False,
                "third_party_code_executed": False,
                "cache_gitignored": False,
                "cache_location": "caller_supplied_fixture" if cache_root is not None else "not_written",
            },
            "write_performed": cache_root is not None,
        }
        if cache_root is not None:
            _write_cache(cache_root, source_url, result)
        results.append(result)
    # Fixture content is test evidence only, never an independently fetched
    # primary source. It must not upgrade a user-visible claim or status.
    fresh_fixture_results = [item for item in results if item.get("status") == "fetched"]
    for item in fresh_fixture_results:
        item["status"] = "fixture_checked_not_verified"
        item["fixture_origin"] = True
    claim_update = _empty_claim_update()
    return {
        **plan,
        "status": "verification_required_not_run",
        "fetch_results": results,
        "claim_ledger": claim_update["claim_ledger"],
        "claim_ledger_summary": claim_update["claim_ledger_summary"],
        "support_comparison": claim_update["support_comparison"],
        "revised_recommendation": claim_update["revised_recommendation"],
        "live_fetch": {**plan["live_fetch"], "performed": False, "allow_live_fetch_runtime": False, "response_size_cap_bytes": _MAX_RESPONSE_BYTES},
        "write_performed": cache_root is not None and bool(fresh_fixture_results),
    }


def build_primary_source_claim_ledger(
    payload: Mapping[str, Any],
    fetch_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Project fetched official evidence into the same claim-ledger contract."""

    telegram_claims = _telegram_claims(payload)
    # No independently attested runtime source adapter is authorized in this
    # goal. Never turn caller-provided mappings into answer evidence.
    evidence_items = build_evidence_quality_items([], question=" ".join(telegram_claims))
    ledger = build_claim_ledger(
        [{"claim_text": claim, "claim_type": "source_fact"} for claim in telegram_claims],
        evidence_items,
    )
    comparisons = []
    for claim in ledger.get("claims") or []:
        if not isinstance(claim, Mapping):
            continue
        matched_refs = {
            str(ref)
            for ref in [*(claim.get("evidence_refs") or []), *(claim.get("matched_evidence") or [])]
            if str(ref)
        }
        snippets = [
            item
            for item in evidence_items
            if str(item.get("source_url") or "") in matched_refs
        ]
        comparisons.append(
            {
                "telegram_claim": claim.get("claim_text") or "",
                "official_source_refs": sorted(matched_refs),
                "support_status": claim.get("support_status") or "unsupported",
                "support_snippets": [
                    {
                        "source_url": item.get("source_url") or "",
                        "support_span": item.get("support_span") or "",
                    }
                    for item in snippets[:3]
                ],
            }
        )
    return {
        "claim_ledger": ledger,
        "claim_ledger_summary": claim_ledger_public_summary(ledger),
        "support_comparison": comparisons,
        "revised_recommendation": _revised_recommendation(comparisons),
    }


def classify_trusted_source(url: str, *, official_relation: bool = False) -> dict[str, str]:
    validation = _validate_candidate_url(url)
    parsed = urlparse(url)
    host = str(parsed.hostname or "").casefold()
    if validation != "accepted":
        return {"source_url": url, "safety_status": validation, "evidence_class": "unknown", "primary_source_status": "rejected"}
    if host == "github.com":
        return {"source_url": url, "safety_status": "accepted", "evidence_class": "github_repository", "primary_source_status": "primary_or_official"}
    if host == "arxiv.org":
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


def _prioritize_primary_sources(urls: Sequence[object], *, trusted_hosts: set[str]) -> list[dict[str, str]]:
    candidates = []
    for value in urls:
        raw = _mapping(value)
        url = str(raw.get("source_url") or raw.get("url") or value or "").strip()
        validation = _validate_candidate_url(url)
        if validation != "accepted":
            continue
        host = str(urlparse(url).hostname or "").casefold()
        official_relation = host in trusted_hosts
        github_host = host == "github.com"
        research_host = host == "arxiv.org"
        source_class = "official_or_github" if github_host or research_host or official_relation else "other"
        candidates.append({"source_url": url, "evidence_class": source_class})
    return sorted(candidates, key=lambda item: (item["evidence_class"] != "official_or_github", item["source_url"]))


def _source_refs(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _trusted_hosts(value: object) -> set[str]:
    """Accept only an explicit, well-formed collection of exact host names."""

    if not isinstance(value, Sequence) or isinstance(value, str):
        return set()
    hosts = set()
    for item in value:
        raw_host = str(item).strip()
        if not raw_host.isascii():
            continue
        host = raw_host.casefold()
        if not host or "://" in host or "/" in host or "@" in host:
            continue
        # A hostname must parse as a hostname, rather than an arbitrary label
        # which could be supplied by malformed fixture input.
        parsed = urlparse("https://" + host)
        if parsed.hostname == host and parsed.port is None and _is_dns_hostname(host):
            hosts.add(host)
    return hosts


def _is_dns_hostname(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return False
    labels = host.split(".")
    return len(labels) >= 2 and all(
        1 <= len(label) <= 63
        and label[0].isascii() and label[0].isalnum()
        and label[-1].isascii() and label[-1].isalnum()
        and all(character.isascii() and (character.isalnum() or character == "-") for character in label)
        for label in labels
    )


def _render_refs(refs: Sequence[str]) -> str:
    return ", ".join(refs) if refs else "нет локальных ссылок"


def _render_urls(sources: Sequence[Mapping[str, str]]) -> str:
    return ", ".join(item["source_url"] for item in sources) if sources else "не выбран"


def _validate_candidate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return "invalid_url"
    raw_host = _raw_host(url)
    if not raw_host or not raw_host.isascii() or raw_host != str(parsed.hostname):
        return "noncanonical_host"
    try:
        if parsed.port not in {None, 443}:
            return "nonstandard_port"
    except ValueError:
        return "invalid_url"
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return "accepted" if _is_dns_hostname(raw_host) else "noncanonical_host"
    return "ip_literal"


def _fetch_fixture(url: str, *, fixture_responses: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    fetched = fixture_responses.get(url)
    if not isinstance(fetched, Mapping):
        raise ValueError("fixture_response_missing")
    status = int(fetched.get("status") or 0)
    headers = {str(key).casefold(): str(value) for key, value in dict(fetched.get("headers") or {}).items()}
    body = bytes(fetched.get("body") or b"")
    final_url = str(fetched.get("final_url") or url)
    _validate_fetch_response(final_url, status=status, headers=headers, body=body)
    return {"status": status, "headers": headers, "body": body, "final_url": final_url, "content_type": _content_type(headers)}


def _validate_fetch_response(url: str, *, status: int, headers: Mapping[str, str], body: bytes) -> None:
    if _validate_candidate_url(url) != "accepted":
        raise ValueError("unsafe_final_url")
    if len(body) > _MAX_RESPONSE_BYTES:
        raise ValueError("response_too_large")
    content_type = _content_type(headers)
    if content_type not in _CONTENT_TYPE_ALLOWLIST:
        raise ValueError("unsupported_content_type")
    if status < 200 or status >= 400:
        raise ValueError("http_status_not_ok")


def _content_type(headers: Mapping[str, str]) -> str:
    return str(headers.get("content-type") or "")


def _text_excerpt(body: bytes, *, limit: int = 700) -> str:
    text = body[:80_000].decode("utf-8", errors="ignore")
    text = " ".join(text.split())
    return text[: max(120, min(1200, int(limit or 700)))]


def _telegram_claims(payload: Mapping[str, Any]) -> list[str]:
    raw = payload.get("telegram_claims")
    if isinstance(raw, Sequence) and not isinstance(raw, str):
        claims = [str(item).strip() for item in raw if str(item).strip()]
    else:
        claims = [str(payload.get("telegram_claim") or "").strip()]
    return [claim for claim in claims if claim][:6]


def _revised_recommendation(comparisons: Sequence[Mapping[str, Any]]) -> str:
    if not comparisons:
        return "No Telegram claim was supplied for primary-source comparison."
    statuses = [str(item.get("support_status") or "") for item in comparisons]
    if statuses and all(status == "supported" for status in statuses):
        return "Primary-source fetch supports the Telegram claim; recommendation may cite the official source."
    if any(status == "partially_supported" for status in statuses):
        return "Primary source only partially supports the Telegram claim; revise the recommendation to the narrower supported claim."
    return "Primary source does not support the Telegram claim; keep Telegram as discovery context and do not recommend from it."


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
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    fetched_at = str(payload.get("fetched_at") or "")
    try:
        parsed = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    age = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    if age < timedelta(0) or age > _CACHE_TTL:
        return None
    payload["cache_hit"] = True
    return payload


def _valid_cached_fetch(
    cached: Mapping[str, Any],
    *,
    source_url: str,
    classification: Mapping[str, str],
) -> bool:
    """Fail closed: caller-controlled cache content is not trusted evidence."""

    if (
        cached.get("status") != "fetched"
        or cached.get("source_url") != source_url
        or cached.get("evidence_class") != classification.get("evidence_class")
        or cached.get("primary_source_status") != "primary_or_official"
        or not isinstance(cached.get("text_excerpt"), str)
        or not isinstance(cached.get("content_bytes"), int)
        or not _is_sha256(cached.get("content_hash"))
    ):
        return False
    final_url = str(cached.get("final_url") or "")
    if not final_url:
        return False
    source_host = str(urlparse(source_url).hostname or "").casefold()
    final_host = str(urlparse(final_url).hostname or "").casefold()
    final_classification = classify_trusted_source(
        final_url,
        official_relation=classification.get("evidence_class") in {"github_repository", "research_paper", "official_documentation", "official_vendor_announcement"},
    )
    return (
        source_host == final_host
        and _explicit_https_port(source_url) == _explicit_https_port(final_url)
        and final_classification.get("safety_status") == "accepted"
        and final_classification.get("evidence_class") == classification.get("evidence_class")
        and final_classification.get("primary_source_status") == "primary_or_official"
    )


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 71 and text.startswith("sha256:") and all(character in "0123456789abcdef" for character in text[7:])


def _explicit_https_port(url: str) -> int | None:
    return urlparse(url).port


def _raw_host(url: str) -> str:
    authority = urlparse(url).netloc
    return authority.rsplit("@", 1)[-1].split(":", 1)[0]


def _empty_claim_update() -> dict[str, Any]:
    ledger = build_claim_ledger([], [])
    return {
        "claim_ledger": ledger,
        "claim_ledger_summary": claim_ledger_public_summary(ledger),
        "support_comparison": [],
        "revised_recommendation": "No independently verified primary-source fixture was fetched; keep Telegram as discovery context.",
    }


def _write_cache(cache_root: Path, url: str, payload: Mapping[str, Any]) -> None:
    cache_root.mkdir(parents=True, exist_ok=True)
    _cache_path(cache_root, url).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _cache_path(cache_root: Path, url: str) -> Path:
    return cache_root / (hashlib.sha256(url.encode()).hexdigest() + ".json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
