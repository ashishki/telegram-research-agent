"""Bounded primary-source verification planning with live access disabled by default."""

from __future__ import annotations

from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


PRIMARY_SOURCE_VERIFICATION_SCHEMA_VERSION = "prm_primary_source_verification.v1"


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
        url = str(value or "").strip()
        if not url.startswith(("https://", "http://")):
            continue
        host = urlparse(url).netloc.casefold()
        source_class = "official_or_github" if host.endswith("github.com") or "docs" in host or host.startswith("www.") else "other"
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


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
