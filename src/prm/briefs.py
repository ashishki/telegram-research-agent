"""Immutable local-archive briefs and their bounded conversational views.

``BriefDocument`` is the one source object for its compact Telegram rendering
and every supported follow-up; a follow-up never asks the archive retriever to
find new material.  The current visible-response binding is deliberately
ephemeral.  Its immutable versions may also be retained in the local database
under an exact owner/id/version key for a future authorized report reader.
There is no job, delivery, export, provider call, or restart follow-up
recovery in this module.
"""

from __future__ import annotations

from assistant.prm_post_answer_actions import canonical_private_owner_id
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape as _html_escape
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any, Literal, Mapping, Sequence
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from prm.brief_editorial import BriefEditorial


BRIEF_DOCUMENT_SCHEMA_VERSION = "assistant.brief_document.v1"
BRIEF_INSPECTION_SCHEMA_VERSION = "prm_brief_inspection.v1"
BRIEF_RETENTION = "owner_scoped_durable_version_history_with_ephemeral_visible_binding"
BRIEF_FULL_VIEW_BUTTON_TEXT = "Показать полный бриф"
_MAX_BRIEFS = 64
_MAX_HISTORY_REFS = 8
_MAX_PERSISTED_HISTORY_REFS = 64
_MAX_PERSISTED_DOCUMENTS_PER_OWNER = 64
_MAX_ITEMS = 20
_MAX_TELEGRAM_CHARS = 2_400
_BRIEF_STORAGE_SCHEMA_VERSION = "prm_brief_document_storage.v1"
_BRIEF_ID = re.compile(r"^brief_[a-z0-9_-]{3,120}$")
_OWNER_REF = re.compile(r"^owner_[a-z0-9_-]{3,120}$")
_EVIDENCE_REF = re.compile(r"^evidence_[a-z0-9_-]{3,120}$")
_ITEM_ID = re.compile(r"^brief_item_[a-z0-9_-]{3,120}$")
_RESPONSE_REF = re.compile(r"^response_[a-f0-9]{24}$")
_HTTPS_REF = re.compile(r"^https://[^\s]{1,500}$", re.IGNORECASE)
_SAFE_REASON = re.compile(r"^[a-z][a-z0-9_.-]{2,120}$")
_SAFE_TOPIC = re.compile(r"^[a-z0-9][a-z0-9 _./-]{0,63}$")
_PROJECT_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-/]{0,79}$")
_CONTENT_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_COVERAGE_STATES = frozenset({"checked", "excluded", "unavailable", "stale", "partial"})
_IMPORTANCE = frozenset({"critical", "high", "medium", "low", "unknown"})
_URGENCY = frozenset({"urgent", "soon", "not_marked", "unknown"})
_SOURCE_STATES = frozenset({"active", "stale", "deleted", "reissued", "unknown"})
_PERIOD_RELATIONS = frozenset({
    "event_in_window", "published_in_window", "first_discovered_in_window",
    "updated_in_window", "deleted_in_window", "reissued_in_window",
})


def _clean(value: object, limit: int, *, required: bool = False) -> str | None:
    if not isinstance(value, str):
        return None if required else ""
    result = " ".join(value.split())
    if len(result) > limit or (required and not result):
        return None
    return result


def _digest(*parts: str, length: int = 24) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:length]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("brief time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object, *, timezone_name: str) -> datetime | None:
    clean = _clean(value, 64, required=True)
    if clean is None:
        return None
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError:
            return None
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class BriefWindow:
    """A half-open interval expressed in one selected operator timezone."""

    timezone: str
    start_at: datetime
    end_at: datetime
    generated_at: datetime

    def __post_init__(self) -> None:
        try:
            zone = ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("brief timezone is invalid") from exc
        if _utc(self.start_at) >= _utc(self.end_at):
            raise ValueError("brief window must be half-open and non-empty")
        if any(value.tzinfo is None for value in (self.start_at, self.end_at, self.generated_at)):
            raise ValueError("brief window times must be timezone-aware")
        # Access the zone once so a platform without the requested IANA entry
        # fails at construction, not after it has selected evidence.
        del zone

    @classmethod
    def from_iso(
        cls,
        *,
        timezone_name: str,
        start_at: str,
        end_at: str,
        generated_at: str | None = None,
    ) -> "BriefWindow":
        generated = _parse_timestamp(generated_at, timezone_name=timezone_name) if generated_at else datetime.now(timezone.utc)
        start = _parse_timestamp(start_at, timezone_name=timezone_name)
        end = _parse_timestamp(end_at, timezone_name=timezone_name)
        if start is None or end is None or generated is None:
            raise ValueError("brief window timestamps are invalid")
        return cls(timezone_name, start, end, generated)

    def contains(self, observed_at: datetime) -> bool:
        """Use [start, end), including a DST-safe UTC comparison."""

        moment = _utc(observed_at)
        return _utc(self.start_at) <= moment < _utc(self.end_at)

    def to_dict(self) -> dict[str, str]:
        return {
            "timezone": self.timezone,
            "start_at": _iso(self.start_at),
            "end_at": _iso(self.end_at),
            "generated_at": _iso(self.generated_at),
        }


@dataclass(frozen=True, slots=True)
class CoverageSource:
    source_ref: str
    state: Literal["checked", "excluded", "unavailable", "stale", "partial"]
    reason: str | None = None

    def __post_init__(self) -> None:
        if not _clean(self.source_ref, 512, required=True) or self.state not in _COVERAGE_STATES:
            raise ValueError("coverage source is invalid")
        if self.reason is not None and _clean(self.reason, 240, required=True) is None:
            raise ValueError("coverage reason is invalid")

    def to_dict(self) -> dict[str, str | None]:
        return {"source_ref": self.source_ref, "state": self.state, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class CoverageManifest:
    sources: tuple[CoverageSource, ...]
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.sources or len(self.sources) > 100 or len({item.source_ref for item in self.sources}) != len(self.sources):
            raise ValueError("coverage sources are invalid")
        if (
            len(self.limitations) > 32
            or len(set(self.limitations)) != len(self.limitations)
            or any(not _SAFE_REASON.fullmatch(item) for item in self.limitations)
        ):
            raise ValueError("coverage limitations are invalid")

    @property
    def complete(self) -> bool:
        return bool(self.sources) and all(item.state == "checked" for item in self.sources)

    def to_dict(self) -> dict[str, object]:
        return {"sources": [item.to_dict() for item in self.sources], "limitations": list(self.limitations)}


@dataclass(frozen=True, slots=True)
class BriefEvidence:
    """A bounded selected local-archive source, never a search instruction."""

    evidence_ref: str
    source_ref: str
    source_family_ref: str
    title: str
    summary: str
    observed_at: datetime
    time_kind: Literal["published", "event", "discovered", "updated", "deleted", "reissued"]
    topics: tuple[str, ...]
    importance: Literal["critical", "high", "medium", "low", "unknown"]
    urgency: Literal["urgent", "soon", "not_marked", "unknown"]
    selection_reasons: tuple[str, ...]
    factual_snapshot_digest: str
    project_refs: tuple[str, ...] = ()
    conflict_group: str | None = None
    conflict_value: str | None = None
    published_at: datetime | None = None
    event_at: datetime | None = None
    first_discovered_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    reissued_at: datetime | None = None
    source_state: str = "unknown"
    period_relation: str = "published_in_window"
    source_version: str = ""

    def __post_init__(self) -> None:
        if (
            not _EVIDENCE_REF.fullmatch(self.evidence_ref)
            or not _HTTPS_REF.fullmatch(self.source_ref)
            or _clean(self.source_family_ref, 512, required=True) is None
        ):
            raise ValueError("brief evidence identity is invalid")
        if _clean(self.title, 240, required=True) is None or _clean(self.summary, 1200, required=True) is None:
            raise ValueError("brief evidence text is invalid")
        if self.observed_at.tzinfo is None or self.time_kind not in {"published", "event", "discovered", "updated", "deleted", "reissued"}:
            raise ValueError("brief evidence time is invalid")
        if any(
            item is not None and item.tzinfo is None
            for item in (
                self.published_at,
                self.event_at,
                self.first_discovered_at,
                self.updated_at,
                self.deleted_at,
                self.reissued_at,
            )
        ):
            raise ValueError("brief evidence provenance time is invalid")
        if self.source_state not in _SOURCE_STATES or self.period_relation not in _PERIOD_RELATIONS:
            raise ValueError("brief evidence source state is invalid")
        if _clean(self.source_version, 120) is None or not _CONTENT_DIGEST.fullmatch(self.factual_snapshot_digest):
            raise ValueError("brief evidence factual identity is invalid")
        if (
            not self.topics
            or len(self.topics) > 8
            or len(set(self.topics)) != len(self.topics)
            or any(not _SAFE_TOPIC.fullmatch(item) for item in self.topics)
        ):
            raise ValueError("brief evidence topics are invalid")
        if self.importance not in _IMPORTANCE or self.urgency not in _URGENCY:
            raise ValueError("brief evidence priority is invalid")
        if (
            len(self.project_refs) > 8
            or len(set(self.project_refs)) != len(self.project_refs)
            or any(not _PROJECT_REF.fullmatch(item) for item in self.project_refs)
        ):
            raise ValueError("brief evidence project bindings are invalid")
        if (
            not self.selection_reasons
            or len(self.selection_reasons) > 10
            or len(set(self.selection_reasons)) != len(self.selection_reasons)
            or any(not _SAFE_REASON.fullmatch(item) for item in self.selection_reasons)
        ):
            raise ValueError("brief evidence reasons are invalid")
        if self.conflict_group is not None and _clean(self.conflict_group, 120, required=True) is None:
            raise ValueError("brief conflict group is invalid")
        if self.conflict_value is not None and _clean(self.conflict_value, 240, required=True) is None:
            raise ValueError("brief conflict value is invalid")


@dataclass(frozen=True, slots=True)
class BriefItem:
    item_id: str
    title: str
    summary: str
    evidence_refs: tuple[str, ...]
    selection_reasons: tuple[str, ...]
    topics: tuple[str, ...]
    importance: Literal["critical", "high", "medium", "low", "unknown"]
    urgency: Literal["urgent", "soon", "not_marked", "unknown"]
    conflict_groups: tuple[str, ...] = ()
    project_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _ITEM_ID.fullmatch(self.item_id):
            raise ValueError("brief item id is invalid")
        if _clean(self.title, 240, required=True) is None or _clean(self.summary, 1200, required=True) is None:
            raise ValueError("brief item text is invalid")
        if not self.evidence_refs or len(self.evidence_refs) > 20 or len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("brief item evidence is invalid")
        if any(not _EVIDENCE_REF.fullmatch(item) for item in self.evidence_refs):
            raise ValueError("brief item evidence is invalid")
        if not self.selection_reasons or any(not _SAFE_REASON.fullmatch(item) for item in self.selection_reasons):
            raise ValueError("brief item reasons are invalid")
        if self.importance not in _IMPORTANCE or self.urgency not in _URGENCY:
            raise ValueError("brief item priority is invalid")
        if len(self.project_refs) > 8 or any(not _PROJECT_REF.fullmatch(item) for item in self.project_refs):
            raise ValueError("brief item project bindings are invalid")

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "summary": self.summary,
            "evidence_refs": list(self.evidence_refs),
            "selection_reasons": list(self.selection_reasons),
        }


@dataclass(frozen=True, slots=True)
class BriefSection:
    section_id: str
    title: str
    items: tuple[BriefItem, ...]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"^[a-z][a-z0-9_-]{2,80}$", self.section_id) or _clean(self.title, 200, required=True) is None:
            raise ValueError("brief section is invalid")
        if not self.items or len(self.items) > 100:
            raise ValueError("brief section needs items")

    def to_contract_dict(self) -> dict[str, object]:
        return {"section_id": self.section_id, "title": self.title, "items": [item.to_contract_dict() for item in self.items]}


@dataclass(frozen=True, slots=True)
class DeduplicationRecord:
    kept_evidence_ref: str
    dropped_evidence_refs: tuple[str, ...]
    key: str
    reason: str = "canonical_source_family"

    def to_dict(self) -> dict[str, object]:
        return {
            "kept_evidence_ref": self.kept_evidence_ref,
            "dropped_evidence_refs": list(self.dropped_evidence_refs),
            "key": self.key,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ConflictRecord:
    group: str
    evidence_refs: tuple[str, ...]
    values: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"group": self.group, "evidence_refs": list(self.evidence_refs), "values": list(self.values)}


@dataclass(frozen=True, slots=True)
class BriefVersionRef:
    brief_id: str
    version: int

    def __post_init__(self) -> None:
        if not _BRIEF_ID.fullmatch(self.brief_id) or self.version < 1:
            raise ValueError("brief version reference is invalid")

    def to_dict(self) -> dict[str, object]:
        return {"brief_id": self.brief_id, "version": self.version}


def brief_owner_ref_from_authenticated_private_tuple(
    chat_id: str | None,
    actor_id: str | None,
    owner_chat_id: str | None,
) -> str | None:
    """Derive durable ownership only from the canonical private Telegram tuple."""

    values = tuple(canonical_private_owner_id(value) for value in (chat_id, actor_id, owner_chat_id))
    if any(value is None for value in values) or len(set(values)) != 1:
        return None
    canonical = "\x1f".join(value for value in values if value is not None)
    digest = hashlib.sha256(f"pa07.brief.owner.v1:{canonical}".encode("utf-8")).hexdigest()
    return "owner_brief_" + digest[:24]


@dataclass(frozen=True, slots=True)
class BriefDocument:
    """Immutable report object; ``to_dict`` remains PA-01 schema compatible."""

    brief_id: str
    version: int
    owner_ref: str
    topic: str
    window: BriefWindow
    status: Literal["complete", "partial", "empty"]
    sections: tuple[BriefSection, ...]
    evidence: tuple[BriefEvidence, ...]
    selection_reasons: tuple[str, ...]
    previous_version: BriefVersionRef | None
    coverage_manifest: CoverageManifest
    content_digest: str
    deduplication: tuple[DeduplicationRecord, ...] = ()
    conflicts: tuple[ConflictRecord, ...] = ()
    comparison_ref: BriefVersionRef | None = None
    period_basis: str = "explicit_requested_range"
    editorial: BriefEditorial | None = None

    def __post_init__(self) -> None:
        if (
            not _BRIEF_ID.fullmatch(self.brief_id)
            or self.version < 1
            or not _OWNER_REF.fullmatch(self.owner_ref)
            or _clean(self.topic, 160, required=True) is None
        ):
            raise ValueError("brief identity is invalid")
        if self.status not in {"complete", "partial", "empty"}:
            raise ValueError("brief status is invalid")
        if len(self.sections) > 20 or len(self.evidence) > _MAX_ITEMS:
            raise ValueError("brief is too large")
        if self.status == "empty" and self.sections:
            raise ValueError("empty brief cannot contain sections")
        # A partial selection may truthfully contain no in-window usable item:
        # that is distinct from a fully checked empty report.
        if self.status == "complete" and not self.sections:
            raise ValueError("complete brief needs sections")
        if len({item.evidence_ref for item in self.evidence}) != len(self.evidence):
            raise ValueError("brief evidence references are not unique")
        referenced = {ref for section in self.sections for item in section.items for ref in item.evidence_refs}
        if referenced != {item.evidence_ref for item in self.evidence}:
            raise ValueError("brief items must exactly bind selected evidence")
        if (
            not self.selection_reasons
            or len(self.selection_reasons) > 32
            or len(set(self.selection_reasons)) != len(self.selection_reasons)
            or any(not _SAFE_REASON.fullmatch(item) for item in self.selection_reasons)
        ):
            raise ValueError("brief selection reasons are invalid")
        if self.previous_version is not None and self.previous_version.brief_id != self.brief_id:
            raise ValueError("previous version must preserve the brief identity")
        if not _CONTENT_DIGEST.fullmatch(self.content_digest):
            raise ValueError("brief content identity is invalid")
        if not _SAFE_REASON.fullmatch(self.period_basis):
            raise ValueError("brief period basis is invalid")
        if self.editorial is not None:
            if type(self.editorial) is not BriefEditorial:
                raise ValueError("brief editorial is invalid")
            BriefEditorial.from_dict(self.editorial.to_dict(), self.evidence)

    @property
    def version_ref(self) -> BriefVersionRef:
        return BriefVersionRef(self.brief_id, self.version)

    @property
    def items(self) -> tuple[BriefItem, ...]:
        return tuple(item for section in self.sections for item in section.items)

    def evidence_by_ref(self) -> dict[str, BriefEvidence]:
        return {item.evidence_ref: item for item in self.evidence}

    def to_dict(self) -> dict[str, object]:
        """The stable shared DTO, intentionally with no renderer-specific keys."""

        return {
            "schema_version": BRIEF_DOCUMENT_SCHEMA_VERSION,
            "brief_id": self.brief_id,
            "version": self.version,
            "owner_ref": self.owner_ref,
            "window": self.window.to_dict(),
            "status": self.status,
            "sections": [section.to_contract_dict() for section in self.sections],
            "evidence_refs": [item.evidence_ref for item in self.evidence],
            "selection_reasons": list(self.selection_reasons),
            "previous_version": self.previous_version.to_dict() if self.previous_version is not None else None,
            "coverage_manifest": self.coverage_manifest.to_dict(),
            **({"editorial": self.editorial.to_dict()} if self.editorial is not None else {}),
        }

    def inspect(self) -> dict[str, object]:
        """Expose how this exact immutable document was selected and bounded."""

        return {
            "schema_version": BRIEF_INSPECTION_SCHEMA_VERSION,
            "brief_ref": {
                **self.version_ref.to_dict(),
                "content_digest": self.content_digest,
                "retention": BRIEF_RETENTION,
            },
            "period": {
                **self.window.to_dict(),
                "interval": "[start_at,end_at)",
                "basis": self.period_basis,
            },
            "topic": self.topic,
            "coverage": {**self.coverage_manifest.to_dict(), "complete": self.coverage_manifest.complete},
            "deduplication": [item.to_dict() for item in self.deduplication],
            "conflicts": [item.to_dict() for item in self.conflicts],
            "importance_vs_urgency": [
                {
                    "item_id": item.item_id,
                    "importance": item.importance,
                    "urgency": item.urgency,
                    "project_refs": list(item.project_refs),
                    "selection_reasons": list(item.selection_reasons),
                }
                for item in self.items
            ],
            "history": {
                "previous_version": self.previous_version.to_dict() if self.previous_version is not None else None,
                "comparison_ref": self.comparison_ref.to_dict() if self.comparison_ref is not None else None,
            },
            "evidence": [
                {
                    "evidence_ref": item.evidence_ref,
                    "source_ref": item.source_ref,
                    "observed_at": _iso(item.observed_at),
                    "time_kind": item.time_kind,
                    "period_relation": item.period_relation,
                    "published_at": _iso(item.published_at) if item.published_at is not None else None,
                    "event_at": _iso(item.event_at) if item.event_at is not None else None,
                    "first_discovered_at": _iso(item.first_discovered_at) if item.first_discovered_at is not None else None,
                    "updated_at": _iso(item.updated_at) if item.updated_at is not None else None,
                    "deleted_at": _iso(item.deleted_at) if item.deleted_at is not None else None,
                    "reissued_at": _iso(item.reissued_at) if item.reissued_at is not None else None,
                    "source_state": item.source_state,
                    "source_version": item.source_version or None,
                    "factual_snapshot_digest": item.factual_snapshot_digest,
                    "topics": list(item.topics),
                }
                for item in self.evidence
            ],
        }


@dataclass(frozen=True, slots=True)
class BriefBuildRequest:
    """Caller-supplied evidence already selected from the local archive."""

    topic: str
    window: BriefWindow
    evidence: tuple[Mapping[str, Any], ...]
    owner_ref: str = "owner_local_brief"
    coverage: tuple[CoverageSource, ...] = ()
    limitations: tuple[str, ...] = ()
    previous_document: BriefDocument | None = None
    comparison_document: BriefDocument | None = None
    period_basis: str = "explicit_requested_range"
    editorial: BriefEditorial | None = None

    def __post_init__(self) -> None:
        if _clean(self.topic, 160, required=True) is None or not _OWNER_REF.fullmatch(self.owner_ref):
            raise ValueError("brief request identity is invalid")
        if not isinstance(self.evidence, tuple) or len(self.evidence) > _MAX_ITEMS:
            raise ValueError("brief request evidence is invalid")
        if any(not isinstance(item, Mapping) for item in self.evidence):
            raise ValueError("brief request evidence is invalid")
        if self.previous_document is not None and type(self.previous_document) is not BriefDocument:
            raise ValueError("brief previous document is invalid")
        if self.comparison_document is not None and type(self.comparison_document) is not BriefDocument:
            raise ValueError("brief comparison document is invalid")
        if any(
            document is not None and document.owner_ref != self.owner_ref
            for document in (self.previous_document, self.comparison_document)
        ):
            raise ValueError("brief history must remain within one owner scope")
        if not _SAFE_REASON.fullmatch(self.period_basis):
            raise ValueError("brief request period basis is invalid")


@dataclass(frozen=True, slots=True)
class BriefFollowup:
    kind: Literal["explain_item", "shorten", "filter_topics", "compare_weeks", "less_technical", "apply", "full"]
    item_number: int | None = None
    topics: tuple[str, ...] = ()


def build_brief_document(request: BriefBuildRequest) -> BriefDocument:
    """Build a deterministic BriefDocument only from local selected evidence."""

    topic = _clean(request.topic, 160, required=True)
    assert topic is not None  # checked by the request type
    evidence, invalid_count, undated_count, outside_count = _local_archive_evidence(request.evidence, request.window)
    kept, deduplication = _deduplicate(evidence)
    conflicts = _conflicts(kept)
    conflict_refs = {ref for conflict in conflicts for ref in conflict.evidence_refs}
    sections = _sections(kept, conflict_refs)
    coverage = _coverage(
        request.coverage,
        request.limitations,
        invalid_count=invalid_count,
        undated_count=undated_count,
        outside_count=outside_count,
    )
    if not kept:
        status: Literal["complete", "partial", "empty"] = "empty" if coverage.complete else "partial"
    else:
        status = "complete" if coverage.complete else "partial"
    reasons = ["local_archive_selected", "source_bound_items", "importance_urgency_separate"]
    if deduplication:
        reasons.append("canonical_source_deduplication")
    if conflicts:
        reasons.append("conflicts_preserved")
    if status != "complete":
        reasons.append("coverage_not_complete")
    previous = request.previous_document
    if previous is not None and _same_logical_report(previous, owner_ref=request.owner_ref, topic=topic, window=request.window):
        # A visible prior version is the only authority to increment the same
        # report identity. It remains conversation-bound in BriefDocumentStore.
        brief_id = previous.brief_id
        version = previous.version + 1
        previous_ref: BriefVersionRef | None = previous.version_ref
    else:
        # After a reset/restart no history is retained. Binding a fresh v1 to
        # its canonical selected content avoids reusing an identity for a
        # different evidence set while still being deterministic for the same
        # exact selection.
        previous_ref = None
        base_content_digest = _content_digest(
            topic=topic,
            window=request.window,
            evidence=kept,
            coverage=coverage,
            deduplication=deduplication,
            conflicts=conflicts,
            selection_reasons=tuple(reasons),
            previous_version=None,
            comparison_ref=request.comparison_document.version_ref if request.comparison_document is not None else None,
            period_basis=request.period_basis,
            editorial=request.editorial,
        )
        brief_id = "brief_" + _digest(
            "prm.brief.content.v1",
            request.owner_ref,
            topic.casefold(),
            request.window.timezone,
            _iso(request.window.start_at),
            _iso(request.window.end_at),
            base_content_digest,
        )
        version = 1
    comparison_ref = request.comparison_document.version_ref if request.comparison_document is not None else None
    content_digest = _content_digest(
        topic=topic,
        window=request.window,
        evidence=kept,
        coverage=coverage,
        deduplication=deduplication,
        conflicts=conflicts,
        selection_reasons=tuple(reasons),
        previous_version=previous_ref,
        comparison_ref=comparison_ref,
        period_basis=request.period_basis,
        editorial=request.editorial,
    )
    return BriefDocument(
        brief_id=brief_id,
        version=version,
        owner_ref=request.owner_ref,
        topic=topic,
        window=request.window,
        status=status,
        sections=sections,
        evidence=kept,
        selection_reasons=tuple(reasons),
        previous_version=previous_ref,
        coverage_manifest=coverage,
        content_digest=content_digest,
        deduplication=deduplication,
        conflicts=conflicts,
        comparison_ref=comparison_ref,
        period_basis=request.period_basis,
        editorial=request.editorial,
    )


def classify_brief_followup(text: str) -> BriefFollowup | None:
    clean = " ".join(str(text or "").split())
    lowered = clean.casefold()
    item = re.fullmatch(r"(?:объясни|поясни|расскажи про|подробнее про|explain)\s+(?:пункт\s*|item\s*)?(\d{1,2})[?.!]?", lowered)
    if item is not None:
        return BriefFollowup("explain_item", item_number=int(item.group(1)))
    if lowered in {"а второе?", "а второе", "объясни второе", "подробнее про второе"}:
        return BriefFollowup("explain_item", item_number=2)
    if lowered in {"сделай короче", "сократи", "shorten it", "make it shorter"}:
        return BriefFollowup("shorten")
    if lowered in {
        "покажи полный бриф", "показать полный бриф", "полный бриф", "подробный бриф", "show full brief",
    }:
        return BriefFollowup("full")
    if (
        "менее техничес" in lowered
        or "проще" in lowered
        or "less technical" in lowered
        or "less tech" in lowered
    ):
        return BriefFollowup("less_technical")
    if lowered in {
        "что из этого применить?", "что из этого применить", "что применить?", "что применить",
        "what from this should i apply?", "what from this should i apply",
        "а мне это зачем?", "а мне это зачем", "что попробовать?", "что попробовать",
    }:
        return BriefFollowup("apply")
    if ("сравни" in lowered or "compare" in lowered) and ("прошл" in lowered or "week" in lowered or "недел" in lowered):
        return BriefFollowup("compare_weeks")
    topic = re.fullmatch(r"(?:только|покажи только|filter)\s+(.{1,120})", lowered)
    if topic is not None:
        values = tuple(_topic(value) for value in re.split(r"[,;/]", topic.group(1)) if _topic(value))
        if values:
            return BriefFollowup("filter_topics", topics=values[:4])
    return None


def render_brief_document(
    document: BriefDocument,
    *,
    view: Literal["telegram", "short", "item", "topics", "comparison", "less_technical", "apply", "full"] = "telegram",
    item_number: int | None = None,
    topics: Sequence[str] = (),
    comparison_document: BriefDocument | None = None,
) -> str:
    """Render a local view of a document; it neither fetches nor regenerates."""

    if type(document) is not BriefDocument:
        raise ValueError("brief document is required")
    if document.editorial is not None and view != "comparison":
        return _render_editorial(document, view=view, item_number=item_number, topics=topics)
    if view == "item":
        return _render_item(document, item_number)
    if view == "comparison":
        return _render_comparison(document, comparison_document)
    if view == "less_technical":
        return _render_less_technical(document)
    if view == "apply":
        return _render_apply(document)
    if view == "full":
        return _render_telegram_full_card(document)
    selected_topics = tuple(_topic(item) for item in topics if _topic(item))
    items = tuple(item for item in document.items if not selected_topics or set(selected_topics) & set(item.topics))
    if view == "telegram":
        return _render_telegram_card(document, items)
    return _render_telegram(document, items, short=view == "short", topics=selected_topics)


_BRIEF_DOCUMENT_TABLE = "assistant_brief_documents"


def _storage_document(document: BriefDocument) -> dict[str, object]:
    """Encode every rendering-relevant field without serializing a corpus."""

    def timestamp(value: datetime | None) -> str | None:
        return _iso(value) if value is not None else None

    return {
        "schema_version": _BRIEF_STORAGE_SCHEMA_VERSION,
        "brief_id": document.brief_id,
        "version": document.version,
        "owner_ref": document.owner_ref,
        "topic": document.topic,
        "window": document.window.to_dict(),
        "status": document.status,
        "sections": [
            {
                "section_id": section.section_id,
                "title": section.title,
                "items": [
                    {
                        "item_id": item.item_id,
                        "title": item.title,
                        "summary": item.summary,
                        "evidence_refs": list(item.evidence_refs),
                        "selection_reasons": list(item.selection_reasons),
                        "topics": list(item.topics),
                        "importance": item.importance,
                        "urgency": item.urgency,
                        "conflict_groups": list(item.conflict_groups),
                        "project_refs": list(item.project_refs),
                    }
                    for item in section.items
                ],
            }
            for section in document.sections
        ],
        "evidence": [
            {
                "evidence_ref": item.evidence_ref,
                "source_ref": item.source_ref,
                "source_family_ref": item.source_family_ref,
                "title": item.title,
                "summary": item.summary,
                "observed_at": _iso(item.observed_at),
                "time_kind": item.time_kind,
                "topics": list(item.topics),
                "importance": item.importance,
                "urgency": item.urgency,
                "selection_reasons": list(item.selection_reasons),
                "factual_snapshot_digest": item.factual_snapshot_digest,
                "project_refs": list(item.project_refs),
                "conflict_group": item.conflict_group,
                "conflict_value": item.conflict_value,
                "published_at": timestamp(item.published_at),
                "event_at": timestamp(item.event_at),
                "first_discovered_at": timestamp(item.first_discovered_at),
                "updated_at": timestamp(item.updated_at),
                "deleted_at": timestamp(item.deleted_at),
                "reissued_at": timestamp(item.reissued_at),
                "source_state": item.source_state,
                "period_relation": item.period_relation,
                "source_version": item.source_version,
            }
            for item in document.evidence
        ],
        "selection_reasons": list(document.selection_reasons),
        "previous_version": _storage_version_ref(document.previous_version),
        "comparison_ref": _storage_version_ref(document.comparison_ref),
        "coverage_manifest": document.coverage_manifest.to_dict(),
        "content_digest": document.content_digest,
        "deduplication": [item.to_dict() for item in document.deduplication],
        "conflicts": [item.to_dict() for item in document.conflicts],
        "period_basis": document.period_basis,
        **({"editorial": document.editorial.to_dict()} if document.editorial is not None else {}),
    }


def _storage_version_ref(value: BriefVersionRef | None) -> dict[str, object] | None:
    return value.to_dict() if value is not None else None


def _stored_mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"stored brief {field} is invalid")
    return value


def _stored_text(value: object, *, field: str, limit: int, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ValueError(f"stored brief {field} is invalid")
    result = _clean(value, limit, required=required)
    if result is None:
        raise ValueError(f"stored brief {field} is invalid")
    return result


def _stored_string_tuple(value: object, *, field: str, limit: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > limit or any(not isinstance(item, str) for item in value):
        raise ValueError(f"stored brief {field} is invalid")
    return tuple(value)


def _stored_int(value: object, *, field: str, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"stored brief {field} is invalid")
    return value


def _stored_timestamp(
    value: object,
    *,
    field: str,
    timezone_name: str,
    required: bool = True,
) -> datetime | None:
    if value is None and not required:
        return None
    result = _parse_timestamp(value, timezone_name=timezone_name)
    if result is None:
        raise ValueError(f"stored brief {field} is invalid")
    return result


def _stored_version_ref(value: object, *, field: str) -> BriefVersionRef | None:
    if value is None:
        return None
    payload = _stored_mapping(value, field=field)
    return BriefVersionRef(
        str(_stored_text(payload.get("brief_id"), field=f"{field}.brief_id", limit=128)),
        _stored_int(payload.get("version"), field=f"{field}.version"),
    )


def _stored_document(payload: object) -> BriefDocument:
    """Decode one stored version and fail closed on malformed or altered data."""

    data = _stored_mapping(payload, field="document")
    if data.get("schema_version") != _BRIEF_STORAGE_SCHEMA_VERSION:
        raise ValueError("stored brief schema is unsupported")
    window_data = _stored_mapping(data.get("window"), field="window")
    timezone_name = str(_stored_text(window_data.get("timezone"), field="window.timezone", limit=80))
    window = BriefWindow.from_iso(
        timezone_name=timezone_name,
        start_at=str(_stored_text(window_data.get("start_at"), field="window.start_at", limit=64)),
        end_at=str(_stored_text(window_data.get("end_at"), field="window.end_at", limit=64)),
        generated_at=str(_stored_text(window_data.get("generated_at"), field="window.generated_at", limit=64)),
    )

    evidence_rows = data.get("evidence")
    if not isinstance(evidence_rows, list) or len(evidence_rows) > _MAX_ITEMS:
        raise ValueError("stored brief evidence is invalid")
    evidence: list[BriefEvidence] = []
    for index, row in enumerate(evidence_rows):
        item = _stored_mapping(row, field=f"evidence[{index}]")
        evidence.append(
            BriefEvidence(
                evidence_ref=str(_stored_text(item.get("evidence_ref"), field="evidence_ref", limit=128)),
                source_ref=str(_stored_text(item.get("source_ref"), field="source_ref", limit=512)),
                source_family_ref=str(_stored_text(item.get("source_family_ref"), field="source_family_ref", limit=512)),
                title=str(_stored_text(item.get("title"), field="evidence.title", limit=240)),
                summary=str(_stored_text(item.get("summary"), field="evidence.summary", limit=1200)),
                observed_at=_stored_timestamp(item.get("observed_at"), field="observed_at", timezone_name=timezone_name),
                time_kind=str(_stored_text(item.get("time_kind"), field="time_kind", limit=16)),  # type: ignore[arg-type]
                topics=_stored_string_tuple(item.get("topics"), field="evidence.topics", limit=8),
                importance=str(_stored_text(item.get("importance"), field="importance", limit=16)),  # type: ignore[arg-type]
                urgency=str(_stored_text(item.get("urgency"), field="urgency", limit=16)),  # type: ignore[arg-type]
                selection_reasons=_stored_string_tuple(item.get("selection_reasons"), field="evidence.reasons", limit=10),
                factual_snapshot_digest=str(_stored_text(item.get("factual_snapshot_digest"), field="factual_snapshot_digest", limit=80)),
                project_refs=_stored_string_tuple(item.get("project_refs"), field="project_refs", limit=8),
                conflict_group=_stored_text(item.get("conflict_group"), field="conflict_group", limit=120, required=False),
                conflict_value=_stored_text(item.get("conflict_value"), field="conflict_value", limit=240, required=False),
                published_at=_stored_timestamp(item.get("published_at"), field="published_at", timezone_name=timezone_name, required=False),
                event_at=_stored_timestamp(item.get("event_at"), field="event_at", timezone_name=timezone_name, required=False),
                first_discovered_at=_stored_timestamp(item.get("first_discovered_at"), field="first_discovered_at", timezone_name=timezone_name, required=False),
                updated_at=_stored_timestamp(item.get("updated_at"), field="updated_at", timezone_name=timezone_name, required=False),
                deleted_at=_stored_timestamp(item.get("deleted_at"), field="deleted_at", timezone_name=timezone_name, required=False),
                reissued_at=_stored_timestamp(item.get("reissued_at"), field="reissued_at", timezone_name=timezone_name, required=False),
                source_state=str(_stored_text(item.get("source_state"), field="source_state", limit=16)),
                period_relation=str(_stored_text(item.get("period_relation"), field="period_relation", limit=40)),
                source_version=str(_stored_text(item.get("source_version"), field="source_version", limit=120, required=False)),
            )
        )

    section_rows = data.get("sections")
    if not isinstance(section_rows, list) or len(section_rows) > 20:
        raise ValueError("stored brief sections are invalid")
    sections: list[BriefSection] = []
    for section_index, row in enumerate(section_rows):
        section = _stored_mapping(row, field=f"sections[{section_index}]")
        item_rows = section.get("items")
        if not isinstance(item_rows, list) or len(item_rows) > 100:
            raise ValueError("stored brief section items are invalid")
        items: list[BriefItem] = []
        for item_index, item_row in enumerate(item_rows):
            item = _stored_mapping(item_row, field=f"sections[{section_index}].items[{item_index}]")
            topics = _stored_string_tuple(item.get("topics"), field="item.topics", limit=8)
            conflict_groups = _stored_string_tuple(item.get("conflict_groups"), field="item.conflict_groups", limit=8)
            if any(_clean(value, 120, required=True) is None for value in conflict_groups) or any(
                not _SAFE_TOPIC.fullmatch(value) for value in topics
            ):
                raise ValueError("stored brief item metadata is invalid")
            items.append(
                BriefItem(
                    item_id=str(_stored_text(item.get("item_id"), field="item_id", limit=128)),
                    title=str(_stored_text(item.get("title"), field="item.title", limit=240)),
                    summary=str(_stored_text(item.get("summary"), field="item.summary", limit=1200)),
                    evidence_refs=_stored_string_tuple(item.get("evidence_refs"), field="item.evidence_refs", limit=20),
                    selection_reasons=_stored_string_tuple(item.get("selection_reasons"), field="item.reasons", limit=10),
                    topics=topics,
                    importance=str(_stored_text(item.get("importance"), field="item.importance", limit=16)),  # type: ignore[arg-type]
                    urgency=str(_stored_text(item.get("urgency"), field="item.urgency", limit=16)),  # type: ignore[arg-type]
                    conflict_groups=conflict_groups,
                    project_refs=_stored_string_tuple(item.get("project_refs"), field="item.project_refs", limit=8),
                )
            )
        sections.append(
            BriefSection(
                section_id=str(_stored_text(section.get("section_id"), field="section_id", limit=80)),
                title=str(_stored_text(section.get("title"), field="section.title", limit=200)),
                items=tuple(items),
            )
        )

    coverage_data = _stored_mapping(data.get("coverage_manifest"), field="coverage_manifest")
    source_rows = coverage_data.get("sources")
    if not isinstance(source_rows, list):
        raise ValueError("stored brief coverage sources are invalid")
    coverage = CoverageManifest(
        tuple(
            CoverageSource(
                source_ref=str(_stored_text(_stored_mapping(row, field="coverage.source").get("source_ref"), field="coverage.source_ref", limit=512)),
                state=str(_stored_text(_stored_mapping(row, field="coverage.source").get("state"), field="coverage.state", limit=16)),  # type: ignore[arg-type]
                reason=_stored_text(_stored_mapping(row, field="coverage.source").get("reason"), field="coverage.reason", limit=240, required=False),
            )
            for row in source_rows
        ),
        _stored_string_tuple(coverage_data.get("limitations"), field="coverage.limitations", limit=32),
    )

    deduplication_rows = data.get("deduplication")
    conflict_rows = data.get("conflicts")
    if not isinstance(deduplication_rows, list) or not isinstance(conflict_rows, list):
        raise ValueError("stored brief inspection records are invalid")
    deduplication = tuple(
        _stored_deduplication(row, index=index) for index, row in enumerate(deduplication_rows)
    )
    conflicts = tuple(_stored_conflict(row, index=index) for index, row in enumerate(conflict_rows))
    document = BriefDocument(
        brief_id=str(_stored_text(data.get("brief_id"), field="brief_id", limit=128)),
        version=_stored_int(data.get("version"), field="version"),
        owner_ref=str(_stored_text(data.get("owner_ref"), field="owner_ref", limit=128)),
        topic=str(_stored_text(data.get("topic"), field="topic", limit=160)),
        window=window,
        status=str(_stored_text(data.get("status"), field="status", limit=16)),  # type: ignore[arg-type]
        sections=tuple(sections),
        evidence=tuple(evidence),
        selection_reasons=_stored_string_tuple(data.get("selection_reasons"), field="selection_reasons", limit=32),
        previous_version=_stored_version_ref(data.get("previous_version"), field="previous_version"),
        coverage_manifest=coverage,
        content_digest=str(_stored_text(data.get("content_digest"), field="content_digest", limit=80)),
        deduplication=deduplication,
        conflicts=conflicts,
        comparison_ref=_stored_version_ref(data.get("comparison_ref"), field="comparison_ref"),
        period_basis=str(_stored_text(data.get("period_basis"), field="period_basis", limit=120)),
        editorial=BriefEditorial.from_dict(data["editorial"], evidence) if "editorial" in data else None,
    )
    expected_digest = _content_digest(
        topic=document.topic,
        window=document.window,
        evidence=document.evidence,
        coverage=document.coverage_manifest,
        deduplication=document.deduplication,
        conflicts=document.conflicts,
        selection_reasons=document.selection_reasons,
        previous_version=document.previous_version,
        comparison_ref=document.comparison_ref,
        period_basis=document.period_basis,
        editorial=document.editorial,
    )
    expected_sections = _sections(
        document.evidence,
        {reference for conflict in document.conflicts for reference in conflict.evidence_refs},
    )
    if document.content_digest != expected_digest or document.sections != expected_sections:
        raise ValueError("stored brief content identity is invalid")
    return document


def _stored_deduplication(value: object, *, index: int) -> DeduplicationRecord:
    item = _stored_mapping(value, field=f"deduplication[{index}]")
    kept = str(_stored_text(item.get("kept_evidence_ref"), field="deduplication.kept", limit=128))
    dropped = _stored_string_tuple(item.get("dropped_evidence_refs"), field="deduplication.dropped", limit=_MAX_ITEMS)
    key = str(_stored_text(item.get("key"), field="deduplication.key", limit=512))
    reason = str(_stored_text(item.get("reason"), field="deduplication.reason", limit=120))
    if not _EVIDENCE_REF.fullmatch(kept) or not dropped or any(not _EVIDENCE_REF.fullmatch(ref) for ref in dropped):
        raise ValueError("stored brief deduplication is invalid")
    return DeduplicationRecord(kept, dropped, key, reason)


def _stored_conflict(value: object, *, index: int) -> ConflictRecord:
    item = _stored_mapping(value, field=f"conflicts[{index}]")
    group = str(_stored_text(item.get("group"), field="conflict.group", limit=120))
    refs = _stored_string_tuple(item.get("evidence_refs"), field="conflict.refs", limit=_MAX_ITEMS)
    values = _stored_string_tuple(item.get("values"), field="conflict.values", limit=_MAX_ITEMS)
    if not refs or not values or any(not _EVIDENCE_REF.fullmatch(ref) for ref in refs):
        raise ValueError("stored brief conflict is invalid")
    return ConflictRecord(group, refs, values)


class BriefDocumentStore:
    """Ephemeral visible bindings plus bounded immutable local report history."""

    def __init__(self, *, db_path: str | None = None) -> None:
        self._documents: dict[tuple[str, str, int], BriefDocument] = {}
        # response_ref, current document, optional comparison baseline, and a
        # bounded exact-version history. The history is scoped to one active
        # conversation; it is not a cross-chat catalogue.
        self._bindings: dict[
            str,
            tuple[
                str,
                tuple[str, str, int],
                tuple[str, str, int] | None,
                tuple[tuple[str, str, int], ...],
            ],
        ] = {}
        self._db_path = None if not db_path or str(db_path) == ":memory:" else Path(str(db_path)).resolve()
        self._lock = RLock()

    def clear(self) -> None:
        """Clear only ephemeral visible bindings; retained history is unchanged."""

        with self._lock:
            self._documents.clear()
            self._bindings.clear()

    def bind_visible(
        self,
        *,
        conversation_id: str,
        response_ref: str,
        document: BriefDocument,
        comparison_document: BriefDocument | None = None,
        authenticated_chat_id: str | None = None,
        authenticated_actor_id: str | None = None,
        authenticated_owner_chat_id: str | None = None,
    ) -> None:
        if not conversation_id.startswith("conversation_") or not _RESPONSE_REF.fullmatch(response_ref) or type(document) is not BriefDocument:
            raise ValueError("brief visibility binding is invalid")
        if comparison_document is not None and type(comparison_document) is not BriefDocument:
            raise ValueError("brief comparison binding is invalid")
        if comparison_document is not None and comparison_document.owner_ref != document.owner_ref:
            raise ValueError("brief comparison binding crosses owner scope")
        durable_owner_ref = brief_owner_ref_from_authenticated_private_tuple(
            authenticated_chat_id,
            authenticated_actor_id,
            authenticated_owner_chat_id,
        )
        if durable_owner_ref is not None:
            if document.owner_ref != durable_owner_ref:
                raise ValueError("brief durable ownership binding is invalid")
            self._persist_document(document, durable_owner_ref=durable_owner_ref)
            if comparison_document is not None:
                self._persist_document(comparison_document, durable_owner_ref=durable_owner_ref)
        with self._lock:
            key = (conversation_id, document.brief_id, document.version)
            comparison_key = (
                (conversation_id, comparison_document.brief_id, comparison_document.version)
                if comparison_document is not None
                else None
            )
            prior = self._bindings.get(conversation_id)
            history = tuple(
                dict.fromkeys(
                    history_key
                    for history_key in (
                        key,
                        comparison_key,
                        *(prior[3] if prior is not None else ()),
                    )
                    if history_key is not None
                )
            )[:_MAX_HISTORY_REFS]
            incoming = set(history)
            while len(set(self._documents) | incoming) > _MAX_BRIEFS:
                oldest = next(iter(self._documents))
                self._documents.pop(oldest, None)
                self._drop_history_key(oldest)
            self._documents[key] = document
            if comparison_document is not None:
                assert comparison_key is not None
                self._documents[comparison_key] = comparison_document
            self._bindings[conversation_id] = (response_ref, key, comparison_key, history)

    def resolve_visible(
        self,
        *,
        conversation_id: str,
        response_ref: str | None,
    ) -> tuple[BriefDocument, BriefDocument | None] | None:
        if not response_ref:
            return None
        with self._lock:
            binding = self._bindings.get(conversation_id)
            if binding is None or binding[0] != response_ref:
                return None
            document = self._documents.get(binding[1])
            if document is None:
                self._bindings.pop(conversation_id, None)
                return None
            return document, self._documents.get(binding[2]) if binding[2] is not None else None

    def forget_conversation(self, conversation_id: str) -> None:
        """Remove only the current dialogue binding, never immutable history."""

        with self._lock:
            binding = self._bindings.pop(conversation_id, None)
            if binding is None:
                return
            for key in binding[3]:
                self._documents.pop(key, None)

    def get_persisted_document(
        self,
        *,
        authenticated_chat_id: str | None,
        authenticated_actor_id: str | None,
        authenticated_owner_chat_id: str | None,
        brief_id: str,
        version: int,
    ) -> BriefDocument | None:
        """Load one owner-scoped immutable version; no topic/latest fallback."""

        owner_ref = brief_owner_ref_from_authenticated_private_tuple(
            authenticated_chat_id,
            authenticated_actor_id,
            authenticated_owner_chat_id,
        )
        if owner_ref is None or not _BRIEF_ID.fullmatch(brief_id) or type(version) is not int or version < 1:
            return None
        connection = self._storage_connection()
        if connection is None:
            return None
        try:
            row = connection.execute(
                """
                SELECT content_digest, document_json
                FROM assistant_brief_documents
                WHERE owner_ref = ? AND brief_id = ? AND version = ?
                """,
                (owner_ref, brief_id, version),
            ).fetchone()
        except sqlite3.Error:
            return None
        finally:
            connection.close()
        if row is None:
            return None
        try:
            stored_digest, document_json = row
            payload = json.loads(str(document_json))
            document = _stored_document(payload)
            if (
                document.owner_ref != owner_ref
                or document.brief_id != brief_id
                or document.version != version
                or document.content_digest != stored_digest
            ):
                return None
            return document
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def list_persisted_versions(
        self,
        *,
        authenticated_chat_id: str | None,
        authenticated_actor_id: str | None,
        authenticated_owner_chat_id: str | None,
        brief_id: str,
    ) -> tuple[BriefVersionRef, ...]:
        """List at most the owner-scoped retained versions in chronological order."""

        owner_ref = brief_owner_ref_from_authenticated_private_tuple(
            authenticated_chat_id,
            authenticated_actor_id,
            authenticated_owner_chat_id,
        )
        if owner_ref is None or not _BRIEF_ID.fullmatch(brief_id):
            return ()
        connection = self._storage_connection()
        if connection is None:
            return ()
        try:
            rows = connection.execute(
                """
                SELECT version
                FROM assistant_brief_documents
                WHERE owner_ref = ? AND brief_id = ?
                ORDER BY version DESC
                LIMIT ?
                """,
                (owner_ref, brief_id, _MAX_PERSISTED_HISTORY_REFS),
            ).fetchall()
        except sqlite3.Error:
            return ()
        finally:
            connection.close()
        return tuple(BriefVersionRef(brief_id, int(row[0])) for row in reversed(rows) if type(row[0]) is int and row[0] >= 1)

    def forget_owner(
        self,
        *,
        authenticated_chat_id: str | None,
        authenticated_actor_id: str | None,
        authenticated_owner_chat_id: str | None,
    ) -> None:
        """Delete one owner's retained documents and their ephemeral projections."""

        owner_ref = brief_owner_ref_from_authenticated_private_tuple(
            authenticated_chat_id,
            authenticated_actor_id,
            authenticated_owner_chat_id,
        )
        if owner_ref is None:
            return
        connection = self._storage_connection()
        if connection is not None:
            try:
                connection.execute("DELETE FROM assistant_brief_documents WHERE owner_ref = ?", (owner_ref,))
                connection.commit()
            finally:
                connection.close()
        with self._lock:
            for key, document in tuple(self._documents.items()):
                if document.owner_ref == owner_ref:
                    self._documents.pop(key, None)
                    self._drop_history_key(key)

    def render_brief(
        self,
        brief_id: str,
        version: int,
        view: str,
        *,
        conversation_id: str | None = None,
        authenticated_chat_id: str | None = None,
        authenticated_actor_id: str | None = None,
        authenticated_owner_chat_id: str | None = None,
        **kwargs: object,
    ) -> str | None:
        document: BriefDocument | None
        if conversation_id:
            with self._lock:
                binding = self._bindings.get(conversation_id)
                if binding is None:
                    return None
                key = (conversation_id, brief_id, version)
                if key not in binding[3]:
                    return None
                document = self._documents.get(key)
        else:
            document = self.get_persisted_document(
                authenticated_chat_id=authenticated_chat_id,
                authenticated_actor_id=authenticated_actor_id,
                authenticated_owner_chat_id=authenticated_owner_chat_id,
                brief_id=brief_id,
                version=version,
            )
        # Either an exact current visible version or an exact authenticated
        # owner/history key is required. There is no global/latest lookup.
        if document is None:
            return None
        if view not in {"telegram", "short", "item", "topics", "comparison", "less_technical", "apply", "full"}:
            raise ValueError("brief view is invalid")
        return render_brief_document(document, view=view, **kwargs)  # type: ignore[arg-type]

    def _storage_connection(self) -> sqlite3.Connection | None:
        """Open an existing local schema only; this method never migrates it."""

        if self._db_path is None or not self._db_path.is_file():
            return None
        try:
            connection = sqlite3.connect(f"{self._db_path.as_uri()}?mode=rw", uri=True)
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (_BRIEF_DOCUMENT_TABLE,),
            ).fetchone()
            if exists is None:
                connection.close()
                return None
            return connection
        except sqlite3.Error:
            return None

    def _persist_document(self, document: BriefDocument, *, durable_owner_ref: str) -> None:
        """Insert one immutable version if the authorized local schema exists."""

        if document.owner_ref != durable_owner_ref:
            raise ValueError("brief durable ownership binding is invalid")
        connection = self._storage_connection()
        if connection is None:
            return
        payload = json.dumps(
            _storage_document(document),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        try:
            row = connection.execute(
                """
                SELECT content_digest FROM assistant_brief_documents
                WHERE owner_ref = ? AND brief_id = ? AND version = ?
                """,
                (document.owner_ref, document.brief_id, document.version),
            ).fetchone()
            if row is not None:
                if str(row[0]) != document.content_digest:
                    raise ValueError("brief version already exists with a different content identity")
                return
            connection.execute(
                """
                INSERT INTO assistant_brief_documents (
                    owner_ref, brief_id, version, content_digest, document_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    document.owner_ref,
                    document.brief_id,
                    document.version,
                    document.content_digest,
                    payload,
                    _iso(document.window.generated_at),
                ),
            )
            connection.execute(
                """
                DELETE FROM assistant_brief_documents
                WHERE owner_ref = ? AND rowid NOT IN (
                    SELECT rowid FROM assistant_brief_documents
                    WHERE owner_ref = ?
                    ORDER BY created_at DESC, rowid DESC
                    LIMIT ?
                )
                """,
                (
                    document.owner_ref,
                    document.owner_ref,
                    _MAX_PERSISTED_DOCUMENTS_PER_OWNER,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def _drop_history_key(self, key: tuple[str, str, int]) -> None:
        """Evict a version without leaving a binding that points at it."""

        updated: dict[
            str,
            tuple[
                str,
                tuple[str, str, int],
                tuple[str, str, int] | None,
                tuple[tuple[str, str, int], ...],
            ],
        ] = {}
        for conversation_id, binding in self._bindings.items():
            response_ref, current, comparison, history = binding
            if current == key:
                # The response no longer has its actual source document, so
                # resolving it must fail rather than showing a stale sibling.
                continue
            reduced = tuple(item for item in history if item != key)
            updated[conversation_id] = (
                response_ref,
                current,
                None if comparison == key else comparison,
                reduced,
            )
        self._bindings = updated


GLOBAL_BRIEFS = BriefDocumentStore()


def render_brief(
    brief_id: str,
    version: int,
    view: str,
    *,
    conversation_id: str | None = None,
    authenticated_chat_id: str | None = None,
    authenticated_actor_id: str | None = None,
    authenticated_owner_chat_id: str | None = None,
    store: BriefDocumentStore = GLOBAL_BRIEFS,
    **kwargs: object,
) -> str | None:
    """Read one exact current or authenticated retained report version."""

    return store.render_brief(
        brief_id,
        version,
        view,
        conversation_id=conversation_id,
        authenticated_chat_id=authenticated_chat_id,
        authenticated_actor_id=authenticated_actor_id,
        authenticated_owner_chat_id=authenticated_owner_chat_id,
        **kwargs,
    )


def parse_requested_brief_window(text: str, *, now: datetime | None = None) -> tuple[BriefWindow, str]:
    """Parse the narrow active Telegram period/timezone syntax without search.

    Supported explicit form is ``с 2026-09-14 по 2026-09-21`` (ISO timestamps
    are accepted too), optionally followed by an IANA zone such as
    ``Europe/Berlin``. ``за прошлую неделю`` means the preceding calendar week
    in that zone; ``последние 7 дней`` is a rolling interval. Ambiguous prose
    remains an inspectable rolling default instead of a guessed calendar week.
    """

    clean = " ".join(str(text or "").split())
    timezone_name = _requested_timezone(clean) or "UTC"
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
        timezone_name = "UTC"
    moment = (now or datetime.now(timezone.utc)).astimezone(zone)
    explicit = re.search(
        r"(?:с\s*)?(\d{4}-\d{2}-\d{2}(?:[T ][0-2]\d:[0-5]\d(?::[0-5]\d)?(?:Z|[+-][0-2]\d:[0-5]\d)?)?)\s*"
        r"(?:по|to|…|\.\.)\s*"
        r"(\d{4}-\d{2}-\d{2}(?:[T ][0-2]\d:[0-5]\d(?::[0-5]\d)?(?:Z|[+-][0-2]\d:[0-5]\d)?)?)",
        clean,
        flags=re.IGNORECASE,
    )
    if explicit is not None:
        start = _date_edge(explicit.group(1))
        end = _date_edge(explicit.group(2))
        return BriefWindow.from_iso(
            timezone_name=timezone_name,
            start_at=start,
            end_at=end,
            generated_at=moment.isoformat(),
        ), "explicit_requested_range"
    lowered = clean.casefold()
    if ("прошл" in lowered and "недел" in lowered) or "previous week" in lowered:
        end = (moment.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=moment.weekday()))
        start = end - timedelta(days=7)
        basis = "previous_calendar_week"
    else:
        end = moment
        start = end - timedelta(days=7)
        basis = "rolling_last_7_days" if ("последн" in lowered and "7" in lowered) or "last 7" in lowered else "rolling_default_7_days"
    return BriefWindow(timezone_name, start, end, moment), basis


def rebuild_brief_request(document: BriefDocument) -> BriefBuildRequest:
    """Create a new version from the same immutable evidence, without search."""

    raw_items: list[dict[str, object]] = []
    for item in document.evidence:
        raw_items.append(
            {
                "local_archive_provenance": True,
                "evidence_id": item.evidence_ref,
                "source_url": item.source_ref,
                "repost_family_id": item.source_family_ref,
                "title": item.title,
                "support_span": item.summary,
                "published_at": _iso(item.published_at) if item.published_at is not None else None,
                "event_at": _iso(item.event_at) if item.event_at is not None else None,
                "first_discovered_at": _iso(item.first_discovered_at) if item.first_discovered_at is not None else None,
                "updated_at": _iso(item.updated_at) if item.updated_at is not None else None,
                "deleted_at": _iso(item.deleted_at) if item.deleted_at is not None else None,
                "reissued_at": _iso(item.reissued_at) if item.reissued_at is not None else None,
                "source_state": item.source_state,
                "source_version": item.source_version,
                "topics": item.topics,
                "importance": item.importance,
                "urgency": item.urgency,
                "project_refs": item.project_refs,
                "project_binding_provenance": "source" if item.project_refs else "",
                "conflict_group": item.conflict_group,
                "conflict_value": item.conflict_value,
            }
        )
    return BriefBuildRequest(
        topic=document.topic,
        window=BriefWindow(
            document.window.timezone,
            document.window.start_at,
            document.window.end_at,
            datetime.now(timezone.utc),
        ),
        evidence=tuple(raw_items),
        owner_ref=document.owner_ref,
        coverage=document.coverage_manifest.sources,
        limitations=document.coverage_manifest.limitations,
        previous_document=document,
        period_basis="revised_existing_evidence",
        editorial=document.editorial,
    )


def _local_archive_evidence(
    raw_items: Sequence[Mapping[str, Any]],
    window: BriefWindow,
) -> tuple[tuple[BriefEvidence, ...], int, int, int]:
    selected: list[BriefEvidence] = []
    invalid = undated = outside = 0
    for raw in raw_items:
        try:
            evidence = _evidence_from_mapping(raw, window=window)
        except _UndatedLocalEvidence:
            undated += 1
            continue
        except _OutsideBriefWindow:
            outside += 1
            continue
        except ValueError:
            invalid += 1
            continue
        selected.append(evidence)
    return tuple(selected), invalid, undated, outside


class _UndatedLocalEvidence(ValueError):
    pass


class _OutsideBriefWindow(ValueError):
    pass


def _evidence_from_mapping(raw: Mapping[str, Any], *, window: BriefWindow) -> BriefEvidence:
    if raw.get("local_archive_provenance") is not True:
        raise ValueError("brief source lacks local archive provenance")
    identity = _clean(
        raw.get("evidence_id") or raw.get("archive_document_id") or raw.get("post_archive_document_id") or raw.get("post_id"),
        120,
        required=True,
    )
    source_ref = _clean(raw.get("canonical_url") or raw.get("source_url") or raw.get("telegram_url"), 512, required=True)
    summary = _clean(raw.get("support_span") or raw.get("snippet") or raw.get("summary"), 1200, required=True)
    title = _clean(raw.get("title"), 240) or _clean(raw.get("channel_username"), 160) or "Архивный материал"
    if identity is None or source_ref is None or summary is None or not _HTTPS_REF.fullmatch(source_ref):
        raise ValueError("brief local archive source is invalid")
    family_ref = _clean(
        raw.get("repost_family_id") or raw.get("canonical_url") or source_ref,
        512,
        required=True,
    )
    if family_ref is None:
        raise ValueError("brief local archive source family is invalid")
    provenance = _source_provenance(raw, window=window)
    topics = _topics(raw)
    project_refs = _projects(raw)
    importance = _importance(raw)
    urgency = _urgency(raw)
    reasons = ["local_archive_source", f"importance_{importance}", f"urgency_{urgency}"]
    if bool(raw.get("personal_relevance") or _mapping(raw.get("relevance")).get("relevant")):
        reasons.append("personal_relevance_marked")
    change = _clean(raw.get("change_type"), 48)
    if change and _SAFE_REASON.fullmatch(f"change_{change.casefold().replace('-', '_')}"):
        reasons.append(f"change_{change.casefold().replace('-', '_')}")
    if project_refs:
        reasons.append("project_source_binding")
    reasons.extend((provenance[2], f"source_{provenance[9]}"))
    snapshot = _factual_snapshot_digest(
        source_ref=source_ref,
        title=title,
        summary=summary,
        observed_at=provenance[0],
        time_kind=provenance[1],
        published_at=provenance[3],
        event_at=provenance[4],
        first_discovered_at=provenance[5],
        updated_at=provenance[6],
        deleted_at=provenance[7],
        reissued_at=provenance[8],
        source_state=provenance[9],
        source_version=provenance[10],
        importance=importance,
        urgency=urgency,
        conflict_group=_clean(raw.get("conflict_group"), 120, required=True),
        conflict_value=_clean(raw.get("conflict_value"), 240, required=True),
    )
    return BriefEvidence(
        evidence_ref=identity if _EVIDENCE_REF.fullmatch(identity) else "evidence_" + _slug(identity, fallback=source_ref),
        source_ref=source_ref,
        source_family_ref=family_ref,
        title=title,
        summary=summary,
        observed_at=provenance[0],
        time_kind=provenance[1],
        topics=topics,
        importance=importance,
        urgency=urgency,
        selection_reasons=tuple(dict.fromkeys(reasons)),
        factual_snapshot_digest=snapshot,
        project_refs=project_refs,
        conflict_group=_clean(raw.get("conflict_group"), 120, required=True),
        conflict_value=_clean(raw.get("conflict_value"), 240, required=True),
        published_at=provenance[3],
        event_at=provenance[4],
        first_discovered_at=provenance[5],
        updated_at=provenance[6],
        deleted_at=provenance[7],
        reissued_at=provenance[8],
        source_state=provenance[9],
        period_relation=provenance[2],
        source_version=provenance[10],
    )


def _source_provenance(
    raw: Mapping[str, Any],
    *,
    window: BriefWindow,
) -> tuple[
    datetime,
    Literal["published", "event", "discovered", "updated", "deleted", "reissued"],
    str,
    datetime | None,
    datetime | None,
    datetime | None,
    datetime | None,
    datetime | None,
    datetime | None,
    str,
    str,
]:
    """Keep all source clocks rather than relabelling late discovery as news."""

    zone = window.timezone
    published = _parse_timestamp(raw.get("published_at") or raw.get("posted_at"), timezone_name=zone)
    event = _parse_timestamp(raw.get("event_at"), timezone_name=zone)
    discovered = _parse_timestamp(raw.get("first_discovered_at") or raw.get("first_seen_at"), timezone_name=zone)
    updated = _parse_timestamp(raw.get("updated_at"), timezone_name=zone)
    deleted = _parse_timestamp(raw.get("deleted_at"), timezone_name=zone)
    reissued = _parse_timestamp(raw.get("reissued_at"), timezone_name=zone)
    state = _source_state(raw, deleted_at=deleted, reissued_at=reissued)
    candidates: tuple[tuple[str, datetime | None, str], ...] = (
        ("deleted", deleted, "deleted_in_window"),
        ("reissued", reissued or updated, "reissued_in_window"),
        ("event", event, "event_in_window"),
        ("published", published, "published_in_window"),
        ("discovered", discovered, "first_discovered_in_window"),
        ("updated", updated, "updated_in_window"),
    )
    if not any(value is not None for _kind, value, _relation in candidates):
        raise _UndatedLocalEvidence("brief local archive source has no usable temporal provenance")
    for kind, moment, relation in candidates:
        if moment is not None and window.contains(moment):
            return moment, kind, relation, published, event, discovered, updated, deleted, reissued, state, _source_version(raw)
    raise _OutsideBriefWindow("brief local archive source is outside the requested half-open window")


def _source_state(raw: Mapping[str, Any], *, deleted_at: datetime | None, reissued_at: datetime | None) -> str:
    explicit = str(raw.get("source_state") or raw.get("status") or "").casefold()
    freshness = str(raw.get("freshness_status") or "").casefold()
    change = str(raw.get("change_type") or "").casefold()
    if deleted_at is not None or explicit in {"deleted", "removed"} or raw.get("deleted") is True:
        return "deleted"
    if reissued_at is not None or explicit == "reissued" or change == "reissued" or raw.get("reissued") is True:
        return "reissued"
    if explicit == "stale" or freshness == "stale":
        return "stale"
    return "active" if explicit or freshness or change or raw.get("local_archive_provenance") is True else "unknown"


def _source_version(raw: Mapping[str, Any]) -> str:
    return _clean(
        raw.get("source_version") or raw.get("material_hash") or raw.get("fingerprint") or raw.get("content_hash"),
        120,
    ) or ""


def _factual_snapshot_digest(
    *,
    source_ref: str,
    title: str,
    summary: str,
    observed_at: datetime,
    time_kind: str,
    published_at: datetime | None,
    event_at: datetime | None,
    first_discovered_at: datetime | None,
    updated_at: datetime | None,
    deleted_at: datetime | None,
    reissued_at: datetime | None,
    source_state: str,
    source_version: str,
    importance: str,
    urgency: str,
    conflict_group: str | None,
    conflict_value: str | None,
) -> str:
    payload = {
        "source_ref": source_ref,
        "title": title,
        "summary": summary,
        "observed_at": _iso(observed_at),
        "time_kind": time_kind,
        "published_at": _iso(published_at) if published_at is not None else None,
        "event_at": _iso(event_at) if event_at is not None else None,
        "first_discovered_at": _iso(first_discovered_at) if first_discovered_at is not None else None,
        "updated_at": _iso(updated_at) if updated_at is not None else None,
        "deleted_at": _iso(deleted_at) if deleted_at is not None else None,
        "reissued_at": _iso(reissued_at) if reissued_at is not None else None,
        "source_state": source_state,
        "source_version": source_version,
        "importance": importance,
        "urgency": urgency,
        "conflict_group": conflict_group,
        "conflict_value": conflict_value,
    }
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _topics(raw: Mapping[str, Any]) -> tuple[str, ...]:
    relevance = _mapping(raw.get("relevance"))
    values = raw.get("topics") or raw.get("categories") or relevance.get("categories") or ()
    if isinstance(values, str):
        values = (values,)
    if not isinstance(values, (tuple, list)):
        values = ()
    normalized = tuple(dict.fromkeys(value for value in (_topic(item) for item in values) if value))
    return normalized[:8] or ("unclassified",)


def _projects(raw: Mapping[str, Any]) -> tuple[str, ...]:
    """Accept a project section only when the selected source bound it."""

    values: object = ()
    if raw.get("project_binding_provenance") == "source":
        values = raw.get("project_refs") or ()
    source_binding = raw.get("source_project_ref")
    if isinstance(source_binding, Mapping) and source_binding.get("origin") == "source":
        values = tuple(values) + (source_binding.get("value"),)
    if isinstance(values, str):
        values = (values,)
    if not isinstance(values, (tuple, list)):
        return ()
    normalized = tuple(
        dict.fromkeys(
            clean
            for clean in (_clean(value, 80, required=True) for value in values)
            if clean is not None and _PROJECT_REF.fullmatch(clean)
        )
    )
    return normalized[:8]


def _topic(value: object) -> str:
    clean = " ".join(str(value or "").casefold().split())[:64]
    return clean if _SAFE_TOPIC.fullmatch(clean) else ""


def _requested_timezone(value: str) -> str | None:
    # Keep the active Telegram parser narrow: accept only an explicit IANA
    # zone token (or UTC), never infer it from a source timestamp or host.
    match = re.search(r"\b(?:timezone|tz|часовой\s+пояс)\s*[:=]?\s*([A-Za-z_]+/[A-Za-z_]+|UTC)\b", value, re.IGNORECASE)
    if match is None:
        match = re.search(r"\b([A-Za-z_]+/[A-Za-z_]+|UTC)\b", value)
    if match is None:
        return None
    candidate = match.group(1)
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return None
    return candidate


def _date_edge(value: str) -> str:
    clean = " ".join(value.split()).replace(" ", "T", 1)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", clean):
        return clean + "T00:00:00"
    return clean


def _importance(raw: Mapping[str, Any]) -> Literal["critical", "high", "medium", "low", "unknown"]:
    relevance = _mapping(raw.get("relevance"))
    value = str(raw.get("importance") or relevance.get("importance") or "").casefold()
    if value in _IMPORTANCE:
        return value  # type: ignore[return-value]
    score = raw.get("importance_score") if raw.get("importance_score") is not None else relevance.get("score")
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        if score >= 9:
            return "critical"
        if score >= 6:
            return "high"
        if score >= 3:
            return "medium"
        return "low"
    return "unknown"


def _urgency(raw: Mapping[str, Any]) -> Literal["urgent", "soon", "not_marked", "unknown"]:
    relevance = _mapping(raw.get("relevance"))
    value = str(raw.get("urgency") or relevance.get("urgency") or "").casefold()
    if value in _URGENCY:
        return value  # type: ignore[return-value]
    if raw.get("urgent") is True or relevance.get("urgent") is True:
        return "urgent"
    if raw.get("urgent") is False or relevance.get("urgent") is False:
        return "not_marked"
    return "unknown"


def _deduplicate(evidence: Sequence[BriefEvidence]) -> tuple[tuple[BriefEvidence, ...], tuple[DeduplicationRecord, ...]]:
    families: dict[str, list[BriefEvidence]] = {}
    for item in evidence:
        families.setdefault(item.source_family_ref, []).append(item)
    kept: list[BriefEvidence] = []
    records: list[DeduplicationRecord] = []
    for key, family in families.items():
        ordered = sorted(family, key=_evidence_rank, reverse=True)
        kept.append(ordered[0])
        if len(ordered) > 1:
            records.append(DeduplicationRecord(ordered[0].evidence_ref, tuple(item.evidence_ref for item in ordered[1:]), key))
    return tuple(sorted(kept, key=_evidence_rank, reverse=True)), tuple(records)


def _evidence_rank(item: BriefEvidence) -> tuple[int, int, str]:
    importance = {"critical": 4, "high": 3, "medium": 2, "low": 1, "unknown": 0}[item.importance]
    urgency = {"urgent": 3, "soon": 2, "not_marked": 1, "unknown": 0}[item.urgency]
    return importance, urgency, _iso(item.observed_at)


def _content_digest(
    *,
    topic: str,
    window: BriefWindow,
    evidence: Sequence[BriefEvidence],
    coverage: CoverageManifest,
    deduplication: Sequence[DeduplicationRecord],
    conflicts: Sequence[ConflictRecord],
    selection_reasons: Sequence[str],
    previous_version: BriefVersionRef | None,
    comparison_ref: BriefVersionRef | None,
    period_basis: str,
    editorial: BriefEditorial | None = None,
) -> str:
    """Canonical identity for the selected facts and their inspection basis."""

    payload = {
        "schema_version": "prm_brief_content_identity.v1",
        "topic": topic,
        "window": window.to_dict(),
        "period_basis": period_basis,
        "selection_reasons": list(selection_reasons),
        "previous_version": previous_version.to_dict() if previous_version is not None else None,
        "comparison_ref": comparison_ref.to_dict() if comparison_ref is not None else None,
        "evidence": [
            {
                "evidence_ref": item.evidence_ref,
                "source_ref": item.source_ref,
                "source_family_ref": item.source_family_ref,
                "title": item.title,
                "summary": item.summary,
                "observed_at": _iso(item.observed_at),
                "time_kind": item.time_kind,
                "published_at": _iso(item.published_at) if item.published_at is not None else None,
                "event_at": _iso(item.event_at) if item.event_at is not None else None,
                "first_discovered_at": _iso(item.first_discovered_at) if item.first_discovered_at is not None else None,
                "updated_at": _iso(item.updated_at) if item.updated_at is not None else None,
                "deleted_at": _iso(item.deleted_at) if item.deleted_at is not None else None,
                "reissued_at": _iso(item.reissued_at) if item.reissued_at is not None else None,
                "source_state": item.source_state,
                "period_relation": item.period_relation,
                "source_version": item.source_version,
                "factual_snapshot_digest": item.factual_snapshot_digest,
                "topics": item.topics,
                "importance": item.importance,
                "urgency": item.urgency,
                "selection_reasons": item.selection_reasons,
                "project_refs": item.project_refs,
                "conflict_group": item.conflict_group,
                "conflict_value": item.conflict_value,
            }
            for item in evidence
        ],
        "coverage": coverage.to_dict(),
        "deduplication": [item.to_dict() for item in deduplication],
        "conflicts": [item.to_dict() for item in conflicts],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if editorial is not None:
        payload["editorial"] = editorial.to_dict()
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _same_logical_report(
    document: BriefDocument,
    *,
    owner_ref: str,
    topic: str,
    window: BriefWindow,
) -> bool:
    """Only a refresh of the same selected period may increment its version."""

    return bool(
        document.owner_ref == owner_ref
        and document.topic.casefold() == topic.casefold()
        and document.window.timezone == window.timezone
        and _utc(document.window.start_at) == _utc(window.start_at)
        and _utc(document.window.end_at) == _utc(window.end_at)
    )


def _conflicts(evidence: Sequence[BriefEvidence]) -> tuple[ConflictRecord, ...]:
    groups: dict[str, list[BriefEvidence]] = {}
    for item in evidence:
        if item.conflict_group and item.conflict_value:
            groups.setdefault(item.conflict_group, []).append(item)
    result = []
    for group, items in groups.items():
        values = tuple(dict.fromkeys(item.conflict_value or "" for item in items))
        if len(values) > 1:
            result.append(ConflictRecord(group, tuple(item.evidence_ref for item in items), values))
    return tuple(result)


def _sections(evidence: Sequence[BriefEvidence], conflict_refs: set[str]) -> tuple[BriefSection, ...]:
    projects = [item for item in evidence if item.project_refs]
    unassigned = [item for item in evidence if item not in projects]
    important = [item for item in unassigned if item.importance in {"critical", "high"}]
    attention = [item for item in unassigned if item.urgency in {"urgent", "soon"} and item not in important]
    remainder = [item for item in unassigned if item not in important and item not in attention]
    sections: list[BriefSection] = []
    for section_id, title, items in (
        ("for_projects", "Для моих проектов", projects),
        ("main_changes", "Главное", important),
        ("needs_attention", "Требует внимания", attention),
        ("other_signals", "По темам", remainder),
    ):
        if not items:
            continue
        rows = tuple(_item(item, conflict_refs) for item in items)
        sections.append(BriefSection(section_id, title, rows))
    return tuple(sections)


def _item(evidence: BriefEvidence, conflict_refs: set[str]) -> BriefItem:
    reasons = list(evidence.selection_reasons)
    conflict_groups = (evidence.conflict_group,) if evidence.evidence_ref in conflict_refs and evidence.conflict_group else ()
    if conflict_groups:
        reasons.append("conflict_not_resolved")
    return BriefItem(
        item_id="brief_item_" + _slug(evidence.evidence_ref, fallback=evidence.source_ref),
        title=evidence.title,
        summary=evidence.summary,
        evidence_refs=(evidence.evidence_ref,),
        selection_reasons=tuple(dict.fromkeys(reasons)),
        topics=evidence.topics,
        importance=evidence.importance,
        urgency=evidence.urgency,
        conflict_groups=conflict_groups,
        project_refs=evidence.project_refs,
    )


def _coverage(
    sources: Sequence[CoverageSource],
    limitations: Sequence[str],
    *,
    invalid_count: int,
    undated_count: int,
    outside_count: int,
) -> CoverageManifest:
    base = tuple(sources) or (CoverageSource("local_archive_selected_evidence", "partial", "bounded caller-supplied selection"),)
    values = list(limitations) or ["bounded_local_archive_selection"]
    if invalid_count:
        values.append("invalid_local_evidence_excluded")
    if undated_count:
        values.append("undated_evidence_excluded")
    if outside_count:
        values.append("outside_window_evidence_excluded")
    normalized = tuple(dict.fromkeys(value for value in values if _SAFE_REASON.fullmatch(str(value))))
    return CoverageManifest(base, normalized)


def _render_telegram(
    document: BriefDocument,
    items: Sequence[BriefItem],
    *,
    short: bool,
    topics: Sequence[str],
    maximum_items: int | None = 2,
    full: bool = False,
) -> str:
    """Render either a bounded mobile card or an explicitly requested full view."""

    period = _period_label(document.window)
    lines = [f"{'Полный бриф' if full else 'Бриф'} · {period}", f"Часовой пояс: {document.window.timezone}"]
    if topics:
        lines.append("Темы: " + ", ".join(topics))
    if not items:
        if document.status == "empty" and document.coverage_manifest.complete:
            lines.extend(("", "В проверенной области важных изменений не найдено."))
        else:
            lines.extend(("", "В предоставленной локальной выборке нет пунктов для этого вида; это не вывод за весь период."))
        return "\n".join(lines).strip() if full else _bounded(lines)
    evidence = document.evidence_by_ref()
    index = shown = 0
    stop = False
    for section in document.sections:
        contained = [item for item in section.items if item in items]
        if not contained:
            continue
        section_lines = ["", section.title]
        for item in contained:
            if maximum_items is not None and shown >= maximum_items:
                stop = True
                break
            index += 1
            shown += 1
            priority = _priority_label(item)
            summary = _short(item.summary, 170 if short else 400 if full else 140)
            section_lines.append(f"{index}. {item.title} — {summary} [{priority}]")
            if not short:
                source = evidence[item.evidence_refs[0]]
                source_ref = source.source_ref if full else _telegram_source_label(source.source_ref, item.evidence_refs[0])
                section_lines.append(f"   Источник: {source_ref}")
                section_lines.append(f"   В периоде: {_temporal_label(source)}")
            if item.conflict_groups:
                section_lines.append("   ⚠ В источниках есть неразрешённое расхождение.")
            if short and index >= 3:
                stop = True
                break
        if len(section_lines) > 2:
            lines.extend(section_lines)
        if stop:
            break
    lines.extend(("", _coverage_line(document)))
    omitted = len(items) - shown
    if omitted and not full:
        lines.append(f"Ещё {omitted} пункт(а): кнопка «{BRIEF_FULL_VIEW_BUTTON_TEXT}» откроет полный вид.")
    elif not full:
        lines.append(f"Навигация: «поясни пункт 2», «сделай короче» или кнопка «{BRIEF_FULL_VIEW_BUTTON_TEXT}».")
    lines.append(f"Версия: {document.brief_id} v{document.version}")
    return "\n".join(lines).strip() if full else _bounded(lines)


def _render_telegram_card(document: BriefDocument, items: Sequence[BriefItem]) -> str:
    """Render PA-07's small, safe Telegram-native HTML card.

    This is Telegram parse-mode markup, not a PA-08 HTML document.  The first
    card deliberately shows only the decision-relevant layer; the immutable
    full view remains the inspectable place for exact source/version details.
    All archive-derived text is escaped before it reaches Telegram HTML.
    """

    lines = [
        "🗞 <b>Короткий бриф</b>",
        f"<b>{_telegram_html(document.topic, 88)}</b>",
        f"<i>{_telegram_html(_period_label(document.window), 72)} · {_telegram_html(document.window.timezone, 64)}</i>",
    ]
    if not items:
        lines.append("")
        if document.status == "empty" and document.coverage_manifest.complete:
            lines.append("В проверенной области важных изменений не найдено.")
        else:
            lines.append("В доступной локальной выборке нет пунктов; это не вывод за весь период.")
        lines.extend(("", _telegram_card_coverage_line(document), "Открой полный бриф: там период, покрытие и основания отбора."))
        return "\n".join(lines)

    featured = tuple(item for item in items if _telegram_featured_item(item))
    if not featured:
        lines.extend(
            (
                "",
                "⚪ <b>Среди найденных материалов нет оценённых приоритетов.</b>",
                "Не называю случайные архивные материалы «главным».",
                _telegram_card_coverage_line(document),
                f"<i>Открой «{BRIEF_FULL_VIEW_BUTTON_TEXT}», чтобы посмотреть тематическую подборку и источники.</i>",
            )
        )
        return "\n".join(lines)

    evidence = document.evidence_by_ref()
    shown = 0
    for section in document.sections:
        contained = [item for item in section.items if item in featured]
        if not contained:
            continue
        section_added = False
        for item in contained:
            if shown >= 2:
                break
            if not section_added:
                lines.extend(("", f"<b>{_telegram_html(section.title, 80)}</b>"))
                section_added = True
            shown += 1
            source = evidence[item.evidence_refs[0]]
            lines.extend(
                (
                    f"{_telegram_number(shown)} <b>{_telegram_html(item.title, 96)}</b>",
                    _telegram_html(_short(item.summary, 220), 220),
                    f"{_telegram_card_priority(item)} · {_telegram_card_source_link(source.source_ref)}",
                )
            )
            if item.conflict_groups:
                lines.append("⚠️ В источниках есть расхождение — сверить в полном брифе.")
        if shown >= 2:
            break

    lines.extend(("", _telegram_card_coverage_line(document)))
    omitted = len(items) - shown
    if omitted:
        lines.append(f"Ещё {_telegram_item_count(omitted)} — в полном брифе.")
    lines.append(
        f"<i>Открой «{BRIEF_FULL_VIEW_BUTTON_TEXT}»: остальные материалы и источники.</i>"
    )
    return "\n".join(lines)


def _telegram_featured_item(item: BriefItem) -> bool:
    """Reserve the two mobile slots for a real priority or source-bound project link."""

    return item.importance != "unknown" or item.urgency != "unknown" or bool(item.project_refs)


def _render_telegram_full_card(document: BriefDocument) -> str:
    """Render the expanded Telegram view without exposing an audit dump.

    Exact identifiers, snapshot hashes and the canonical inspection structure
    remain in ``BriefDocument`` for the inspectable application/API boundary.
    They do not help a person decide what to read in a Telegram conversation.
    """

    lines = [
        "🗞 <b>Материалы по теме</b>",
        f"<b>{_telegram_html(document.topic, 88)}</b>",
        f"<i>{_telegram_html(_period_label(document.window), 72)} · {_telegram_html(document.window.timezone, 64)}</i>",
    ]
    if not document.items:
        lines.extend(("", "В этой выборке нет пунктов для подробного разбора.", _telegram_card_coverage_line(document)))
        return "\n".join(lines)

    lines.extend(("", "Редакторский обзор пока не подготовлен. Ниже — найденные фрагменты и источники."))

    evidence = document.evidence_by_ref()
    index = 0
    for section in document.sections:
        if not section.items:
            continue
        lines.extend(("", f"<b>{_telegram_full_section_title(section.section_id, section.title)}</b>"))
        for item in section.items:
            index += 1
            source = evidence[item.evidence_refs[0]]
            item_lines = [
                f"{index}. <b>{_telegram_html(item.title, 112)}</b>",
                _telegram_html(item.summary, 1200),
                *_telegram_why_it_matters(item),
                " · ".join(value for value in (_telegram_card_priority(item), _telegram_card_source_link(source.source_ref)) if value),
            ]
            temporal_note = _telegram_human_time_label(source)
            if temporal_note:
                item_lines.append(f"<i>{temporal_note}</i>")
            lines.extend(item_lines)
            if item.conflict_groups:
                lines.append("⚠️ В источниках есть расхождение — вывод не объединён автоматически.")

    lines.extend(("", _telegram_card_coverage_line(document)))
    if document.deduplication:
        lines.append(f"Повторы: исключено {len(document.deduplication)} по совпадающему источнику.")
    lines.append("<i>Спроси «объясни пункт 2», «сделай короче» или «только &lt;тема&gt;».</i>")
    return "\n".join(lines)


def _telegram_html(value: str, limit: int) -> str:
    """Escape an archive-derived value for Telegram's constrained HTML mode."""

    return _html_escape(_short(value, limit), quote=True)


def _telegram_number(number: int) -> str:
    return {1: "①", 2: "②"}.get(number, f"{number}.")


def _telegram_card_priority(item: BriefItem) -> str:
    importance = {
        "critical": "Важность: критично",
        "high": "Важность: важно",
        "medium": "Важность: полезно",
        "low": "Важность: контекст",
        "unknown": "",
    }[item.importance]
    urgency = {
        "urgent": "срочно",
        "soon": "скоро",
        "not_marked": "",
        "unknown": "",
    }[item.urgency]
    return " · ".join(value for value in (importance, f"Срочность: {urgency}" if urgency else "") if value)


def _human_brief_period(window: BriefWindow) -> str:
    zone = ZoneInfo(window.timezone)
    start = window.start_at.astimezone(zone)
    end = window.end_at.astimezone(zone)
    return f"{start:%d.%m %H:%M} — {end:%d.%m %H:%M} · {window.timezone}"


def _render_editorial(
    document: BriefDocument, *, view: str, item_number: int | None, topics: Sequence[str],
) -> str:
    editorial = document.editorial
    assert editorial is not None
    if not editorial.stories:
        message = (
            "В проверенной области важных изменений по теме не найдено."
            if document.coverage_manifest.complete else
            "В найденной подборке содержательных событий по теме не выделено. Это не вывод за весь период."
        )
        return "\n".join((
            f"🗞 <b>{_telegram_html(document.topic, 160)}</b>",
            f"<i>{_telegram_html(_human_brief_period(document.window), 120)}</i>", "", message,
            "", _telegram_card_coverage_line(document), "Можно выбрать другую тему или период.",
        ))
    sources = document.evidence_by_ref()
    indexed = list(enumerate(editorial.stories, start=1))
    if view == "item":
        indexed = [(i, story) for i, story in indexed if i == item_number]
    if topics:
        selected_topics = {_topic(topic) for topic in topics}
        indexed = [(i, story) for i, story in indexed if any(
            selected_topics & set(sources[anchor.evidence_ref].topics) for anchor in story.anchors
        )]
    if not indexed:
        return "В этом обзоре нет такого пункта или темы. Можно вернуться к полному брифу."
    compact = view in {"telegram", "short", "less_technical", "topics"}
    lines = [f"🗞 <b>{_telegram_html(document.topic, 160)}</b>",
             f"<i>{_telegram_html(_human_brief_period(document.window), 120)}</i>"]
    for index, story in indexed:
        block = ["", f"<b>{index}. {_telegram_html(story.title, 140)}</b>"]
        if view == "apply":
            block.append(_telegram_html(story.why_selected, 300))
            block.append(_telegram_html(story.next_step, 300) if story.next_step else
                         "Конкретный следующий шаг из этих материалов пока не следует.")
        else:
            block.append(_telegram_html(story.summary, 300))
            if not compact:
                block.extend(("", _telegram_html(story.explanation, 900),
                              f"<b>Почему выделил:</b> {_telegram_html(story.why_selected, 300)}"))
                if story.next_step:
                    block.append(f"<b>Можно попробовать:</b> {_telegram_html(story.next_step, 300)}")
        if story.caveat and not compact:
            block.append(f"<b>Ограничение:</b> {_telegram_html(story.caveat, 300)}")
        refs = tuple(dict.fromkeys(anchor.evidence_ref for anchor in story.anchors))
        for ref in refs[:1] if compact else refs:
            source = sources[ref]
            block.append(_telegram_card_source_link(source.source_ref))
            if not compact:
                note = _telegram_human_time_label(source)
                if note:
                    block.append(_telegram_html(note, 300))
        if any(ref in conflict.evidence_refs for ref in refs for conflict in document.conflicts):
            block.append("⚠️ Источники расходятся; это расхождение пока не разрешено.")
        if compact and len("\n".join(lines + block)) > 2000:
            break
        lines.extend(block)
        if compact and sum(line.startswith("<b>") for line in lines) >= 3:
            break
    lines.extend(("", _telegram_card_coverage_line(document)))
    if compact:
        lines.append(f"Подробнее — «{BRIEF_FULL_VIEW_BUTTON_TEXT}». Можно попросить объяснить любой пункт.")
    else:
        example_number = 2 if len(editorial.stories) > 1 else 1
        lines.append(f"Спроси «объясни пункт {example_number}», «сделай короче» или «что попробовать?».")
    return "\n".join(lines)


def _telegram_card_source_link(source_ref: str) -> str:
    """Keep the card compact while preserving a safe direct source link."""

    if len(source_ref) > 240:
        return "Источник — в полном брифе"
    label = _telegram_source_identity(source_ref)
    return f'Источник: <a href="{_html_escape(source_ref, quote=True)}">{_html_escape(label, quote=True)}</a>'


def _telegram_source_identity(source_ref: str) -> str:
    """Give a person a source name without rendering an opaque long URL."""

    parsed = urlsplit(source_ref)
    host = (parsed.hostname or "").casefold()
    segments = [part for part in parsed.path.split("/") if part]
    if host in {"t.me", "telegram.me", "www.t.me"}:
        if segments[:1] == ["s"]:
            segments = segments[1:]
        if segments and re.fullmatch(r"[A-Za-z0-9_]{3,64}", segments[0]):
            return "@" + segments[0]
    return host or "источник"


def _telegram_full_section_title(section_id: str, title: str) -> str:
    if section_id == "other_signals":
        return "Подборка по теме"
    return _telegram_html(title, 80)


def _telegram_human_time_label(source: BriefEvidence) -> str | None:
    if source.period_relation == "published_in_window" and source.source_state == "active":
        return None
    relation = {
        "event_in_window": "Событие относится к выбранному периоду",
        "published_in_window": "Опубликовано в выбранный период",
        "first_discovered_in_window": "впервые обнаружен в периоде; публикация могла быть раньше",
        "updated_in_window": "Источник обновлён в выбранный период",
        "deleted_in_window": "Источник удалён в выбранный период",
        "reissued_in_window": "Источник переиздан в выбранный период",
    }[source.period_relation]
    if source.source_state == "active":
        return f"{relation}."
    state = {
        "active": "актуальное состояние источника",
        "stale": "источник помечен как устаревший",
        "deleted": "источник удалён",
        "reissued": "источник переиздан",
        "unknown": "состояние источника не указано",
    }[source.source_state]
    return f"{relation}; {state}."


def _telegram_why_it_matters(item: BriefItem) -> tuple[str, ...]:
    """Show personal relevance only when the selected source bound it."""

    if item.project_refs:
        projects = ", ".join(f"«{_telegram_html(project, 80)}»" for project in item.project_refs[:2])
        return (f"<i>Зачем вам: связано с проектом {projects}.</i>",)
    if "personal_relevance_marked" in item.selection_reasons:
        return ("<i>Зачем вам: источник помечен в локальной выборке как лично релевантный.</i>",)
    return ()


def _telegram_card_coverage_line(document: BriefDocument) -> str:
    checked = sum(source.state == "checked" for source in document.coverage_manifest.sources)
    total = len(document.coverage_manifest.sources)
    if document.coverage_manifest.complete:
        return f"✓ Проверено {checked} из {total} источников."
    return "◌ Это не полный обзор недели: показаны только найденные материалы."


def _telegram_item_count(count: int) -> str:
    """Use a readable Russian noun form instead of UI-style parentheses."""

    if count % 10 == 1 and count % 100 != 11:
        suffix = "пункт"
    elif count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14}:
        suffix = "пункта"
    else:
        suffix = "пунктов"
    return f"{count} {suffix}"


def _render_item(document: BriefDocument, item_number: int | None) -> str:
    if item_number is None or item_number < 1 or item_number > len(document.items):
        return "В текущем BriefDocument нет такого пункта; поиск источников заново не запускался."
    item = document.items[item_number - 1]
    evidence = document.evidence_by_ref()
    source = evidence[item.evidence_refs[0]]
    lines = [
        f"Пункт {item_number}: {item.title}",
        item.summary,
        "",
        f"Важность: {item.importance}; срочность: {item.urgency}.",
        "Основания отбора: " + ", ".join(item.selection_reasons),
        f"Источник: {source.source_ref}",
        f"Временная связь с периодом: {_temporal_label(source)}.",
        f"Версия BriefDocument: {document.brief_id} v{document.version}",
    ]
    if item.conflict_groups:
        lines.append("Есть неразрешённый конфликт источников; вывод не выравнивался автоматически.")
    return _bounded(lines)


def _render_less_technical(document: BriefDocument) -> str:
    """A deterministic plain-language view, not a second model generation."""

    if not document.items:
        return _render_telegram(document, (), short=True, topics=())
    evidence = document.evidence_by_ref()
    lines = ["Коротко и менее технически"]
    for index, item in enumerate(document.items[:4], start=1):
        source = evidence[item.evidence_refs[0]]
        lines.append(f"{index}. {item.title}: {_short(item.summary, 180)}")
        lines.append(f"   Основание: {source.source_ref}")
    lines.extend(("", "Формулировки упрощены локальным отображением; новых фактов и поиска нет.", f"Версия: {document.brief_id} v{document.version}"))
    return _bounded(lines)


def _render_apply(document: BriefDocument) -> str:
    """Offer source-bounded consideration prompts without inventing actions."""

    if not document.items:
        return "В текущем BriefDocument нет источников, из которых можно осторожно вывести следующий шаг; поиск не запускался."
    evidence = document.evidence_by_ref()
    lines = ["Что из этого можно рассмотреть"]
    for item in document.items[:4]:
        source = evidence[item.evidence_refs[0]]
        urgency = "сначала проверить срок" if item.urgency in {"urgent", "soon"} else "оценить применимость"
        lines.append(f"- {item.title}: {urgency}; основание — {source.source_ref}")
    lines.extend((
        "",
        "Это не выполненные действия и не новые обязательства: BriefDocument хранит сигналы и источники, не подтверждённый план.",
        f"Версия: {document.brief_id} v{document.version}; поиск не запускался.",
    ))
    return _bounded(lines)


def _render_comparison(current: BriefDocument, previous: BriefDocument | None) -> str:
    if previous is None or current.comparison_ref != previous.version_ref:
        return "Сравнение недоступно: текущий BriefDocument не содержит доступной ссылки на отчёт другой недели; новый поиск не запускался."
    current_by_source = {item.source_ref: item for item in current.evidence}
    prior_by_source = {item.source_ref: item for item in previous.evidence}
    added = [item for key, item in current_by_source.items() if key not in prior_by_source]
    removed = [item for key, item in prior_by_source.items() if key not in current_by_source]
    changed = [
        item for key, item in current_by_source.items()
        if key in prior_by_source and item.factual_snapshot_digest != prior_by_source[key].factual_snapshot_digest
    ]
    lines = [
        f"Сравнение: { _period_label(current.window) } ↔ { _period_label(previous.window) }",
        f"Текущая версия: {current.brief_id} v{current.version}; база: {previous.brief_id} v{previous.version}.",
        "",
        "Появилось",
        *(_comparison_lines(added) or ["- Нет новых источников в двух сохранённых выборках."]),
        "",
        "Изменилось",
        *(_comparison_lines(changed) or ["- Нет зафиксированных изменений по общим источникам."]),
        "",
        "Не вошло в текущую выборку",
        *(_comparison_lines(removed) or ["- Нет."]),
        "",
        "Сравнение использует только две сохранённые версии BriefDocument; поиск не запускался.",
    ]
    return _bounded(lines)


def _comparison_lines(items: Sequence[BriefEvidence]) -> list[str]:
    return [f"- {item.title}: {item.source_ref}" for item in items[:5]]


def _period_label(window: BriefWindow) -> str:
    zone = ZoneInfo(window.timezone)
    start = window.start_at.astimezone(zone).strftime("%d.%m %H:%M")
    end = window.end_at.astimezone(zone).strftime("%d.%m %H:%M")
    return f"[{start}, {end})"


def _temporal_label(item: BriefEvidence) -> str:
    relation = {
        "event_in_window": "событие в периоде",
        "published_in_window": "публикация в периоде",
        "first_discovered_in_window": "впервые обнаружен в периоде (публикация могла быть раньше)",
        "updated_in_window": "обновлён в периоде",
        "deleted_in_window": "удалён в периоде",
        "reissued_in_window": "переиздан в периоде",
    }[item.period_relation]
    state = {
        "active": "актуальное состояние источника",
        "stale": "источник помечен как устаревший",
        "deleted": "источник удалён",
        "reissued": "источник переиздан",
        "unknown": "состояние источника не указано",
    }[item.source_state]
    version = f"; снимок {item.source_version}" if item.source_version else ""
    return f"{relation}; {state}{version}"


def _priority_label(item: BriefItem) -> str:
    urgency = "срочно" if item.urgency == "urgent" else "скоро" if item.urgency == "soon" else "не отмечена"
    return f"важность: {item.importance}; срочность: {urgency}"


def _coverage_line(document: BriefDocument) -> str:
    states = ", ".join(f"{item.source_ref}: {item.state}" for item in document.coverage_manifest.sources[:3])
    if document.coverage_manifest.complete:
        return f"Покрытие: проверено ({states})."
    return f"Покрытие частичное ({states}); «ничего важного» не утверждается за весь период."


def _telegram_source_label(source_ref: str, evidence_ref: str) -> str:
    """Keep the first mobile card bounded without silently losing navigation."""

    if len(source_ref) <= 160:
        return source_ref
    return f"{evidence_ref}; полная ссылка — в «покажи полный бриф»"


def _bounded(lines: Sequence[str]) -> str:
    text = "\n".join(line for line in lines if line is not None).strip()
    if len(text) <= _MAX_TELEGRAM_CHARS:
        return text
    return text[: _MAX_TELEGRAM_CHARS - 1].rsplit("\n", 1)[0].rstrip() + "…"


def _short(value: str, limit: int) -> str:
    clean = " ".join(value.split())
    if len(clean) <= limit:
        return clean
    cut = clean[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return (cut or clean[: limit - 1]).rstrip() + "…"


def _slug(value: str, *, fallback: str) -> str:
    clean = re.sub(r"[^a-z0-9_-]+", "_", str(value).casefold()).strip("_")
    if len(clean) < 3:
        clean = _digest(fallback, length=16)
    return clean[:120]


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
