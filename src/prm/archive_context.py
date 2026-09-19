"""Immutable, source-bound archive excerpts eligible for PA-04 synthesis.

This is intentionally narrower than a generic ``list[dict]``.  A provider
transport may receive this type only after every excerpt has been selected by
the local archive contract and bound back to an evidence-quality support span.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping, Sequence


_MAX_ITEMS = 8
_MAX_QUESTION_CHARS = 2_000
_MAX_TITLE_CHARS = 300
_MAX_TEXT_CHARS = 1_200
_MAX_SOURCE_REF_CHARS = 500
_MAX_RENDERED_CHARS = 12_000
_HTTPS_SOURCE_REF = re.compile(r"^https://[^\s]{1,492}$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ArchiveContextItem:
    evidence_id: str
    title: str
    text: str
    source_ref: str
    relevance_label: str

    def to_transport_dict(self) -> dict[str, str]:
        return {
            "evidence_id": self.evidence_id,
            "title": self.title,
            "text": self.text,
            "source_ref": self.source_ref,
            "relevance_label": self.relevance_label,
        }


@dataclass(frozen=True, slots=True)
class ArchiveEvidenceContext:
    """A bounded context selected by the local retrieval/result contract."""

    question: str
    items: tuple[ArchiveContextItem, ...]
    binding_digest: str

    @classmethod
    def from_payload(
        cls,
        *,
        question: str,
        archive_contract: Mapping[str, Any],
        evidence_items: Sequence[Mapping[str, Any]],
    ) -> "ArchiveEvidenceContext | None":
        clean_question = _clean(question, _MAX_QUESTION_CHARS, required=True)
        if clean_question is None or not isinstance(archive_contract, Mapping):
            return None
        selected = _selected_findings(archive_contract)
        if not selected or len(selected) > _MAX_ITEMS:
            return None
        support_by_identity = _support_by_identity(evidence_items)
        if not support_by_identity:
            return None

        items: list[ArchiveContextItem] = []
        seen_sources: set[str] = set()
        for finding in selected:
            source_ref = _clean(finding.get("source_url"), _MAX_SOURCE_REF_CHARS, required=True)
            title = _clean(finding.get("title"), _MAX_TITLE_CHARS) or "Архивный материал"
            evidence_id = _clean(finding.get("evidence_id"), 220, required=True)
            label = _clean(finding.get("relevance_label"), 32, required=True)
            if (
                source_ref is None
                or evidence_id is None
                or label not in {"direct", "partial", "adjacent"}
                or not _HTTPS_SOURCE_REF.fullmatch(source_ref)
                or source_ref in seen_sources
            ):
                return None
            supports = support_by_identity.get((evidence_id, source_ref))
            # The evidence item has already been selected by local retrieval.
            # A source URL alone is only a locator: require its exact archive
            # identity and explicit local provenance, and use its canonical
            # bounded support span rather than a separately truncated display
            # summary.  More than one span for the same source identity is
            # ambiguous and must not be silently selected.
            if supports is None or len(supports) != 1:
                return None
            support = supports[0]
            seen_sources.add(source_ref)
            items.append(ArchiveContextItem(
                evidence_id=evidence_id,
                title=title,
                text=support,
                source_ref=source_ref,
                relevance_label=label,
            ))

        rendered = _render(items)
        if len(rendered) > _MAX_RENDERED_CHARS:
            return None
        digest_payload = {
            "schema_version": "prm_archive_evidence_context.v1",
            "question": clean_question,
            "items": [item.to_transport_dict() for item in items],
        }
        binding_digest = hashlib.sha256(
            json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return cls(question=clean_question, items=tuple(items), binding_digest=binding_digest)

    def to_transport_context(self) -> tuple[dict[str, str], ...]:
        """Return a copy-safe form for the dedicated private-context transport."""

        return tuple(item.to_transport_dict() for item in self.items)

    def public_measurement(self) -> dict[str, object]:
        """Safe metadata only; do not log archive excerpts or user question."""

        return {
            "schema_version": "prm_archive_evidence_context_measurement.v1",
            "binding_digest": self.binding_digest,
            "selected_source_count": len(self.items),
            "source_refs": [item.source_ref for item in self.items],
            "relevance_labels": [item.relevance_label for item in self.items],
        }


def archive_evidence_context_is_intact(value: object) -> bool:
    """Detect a forged or mutated context before private text can egress."""

    if type(value) is not ArchiveEvidenceContext or not value.items or len(value.items) > _MAX_ITEMS:
        return False
    if _clean(value.question, _MAX_QUESTION_CHARS, required=True) != value.question:
        return False
    items: list[ArchiveContextItem] = []
    seen_sources: set[str] = set()
    for item in value.items:
        if type(item) is not ArchiveContextItem:
            return False
        if (
            _clean(item.evidence_id, 220, required=True) != item.evidence_id
            or _clean(item.title, _MAX_TITLE_CHARS, required=True) != item.title
            or _clean(item.text, _MAX_TEXT_CHARS, required=True) != item.text
            or _clean(item.source_ref, _MAX_SOURCE_REF_CHARS, required=True) != item.source_ref
            or item.relevance_label not in {"direct", "partial", "adjacent"}
            or not _HTTPS_SOURCE_REF.fullmatch(item.source_ref)
            or item.source_ref in seen_sources
        ):
            return False
        seen_sources.add(item.source_ref)
        items.append(item)
    if len(_render(items)) > _MAX_RENDERED_CHARS:
        return False
    digest_payload = {
        "schema_version": "prm_archive_evidence_context.v1",
        "question": value.question,
        "items": [item.to_transport_dict() for item in items],
    }
    digest = hashlib.sha256(
        json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return digest == value.binding_digest


def _selected_findings(contract: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    items: list[Mapping[str, Any]] = []
    for field in ("direct_findings", "partial_findings", "adjacent_findings"):
        value = contract.get(field)
        if not isinstance(value, (list, tuple)):
            return []
        items.extend(item for item in value if isinstance(item, Mapping))
    return items


def _support_by_identity(evidence_items: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], list[str]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for item in evidence_items:
        if not isinstance(item, Mapping):
            continue
        evidence_id = _clean(item.get("evidence_id"), 220, required=True)
        source_ref = _clean(item.get("source_url"), _MAX_SOURCE_REF_CHARS, required=True)
        support = _clean(item.get("support_span") or item.get("snippet"), _MAX_TEXT_CHARS, required=True)
        if (
            evidence_id is None
            or source_ref is None
            or support is None
            or item.get("local_archive_provenance") is not True
            or not _HTTPS_SOURCE_REF.fullmatch(source_ref)
        ):
            continue
        grouped.setdefault((evidence_id, source_ref), []).append(support)
    return grouped


def _render(items: Sequence[ArchiveContextItem]) -> str:
    return "\n\n---\n\n".join(
        f"evidence_id={item.evidence_id}\nrelevance={item.relevance_label}\ntitle={item.title}\ntext={item.text}\nsource_ref={item.source_ref}"
        for item in items
    )


def _clean(value: object, limit: int, *, required: bool = False) -> str | None:
    if not isinstance(value, str):
        return None if required else ""
    clean = " ".join(value.split())
    if len(clean) > limit or (required and not clean):
        return None
    return clean
