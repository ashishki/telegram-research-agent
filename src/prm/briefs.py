"""Immutable local-archive briefs and their bounded conversational views.

PA-07 deliberately keeps a brief in process memory.  A ``BriefDocument`` is
the one source object for its compact Telegram rendering and every supported
follow-up; a follow-up never asks the archive retriever to find new material.
There is no database, job, delivery, export, provider call, or restart
recovery in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import re
from threading import RLock
from typing import Any, Literal, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


BRIEF_DOCUMENT_SCHEMA_VERSION = "assistant.brief_document.v1"
BRIEF_INSPECTION_SCHEMA_VERSION = "prm_brief_inspection.v1"
BRIEF_RETENTION = "ephemeral_current_visible_response_only"
_MAX_BRIEFS = 64
_MAX_ITEMS = 20
_MAX_TELEGRAM_CHARS = 2_400
_BRIEF_ID = re.compile(r"^brief_[a-z0-9_-]{3,120}$")
_OWNER_REF = re.compile(r"^owner_[a-z0-9_-]{3,120}$")
_EVIDENCE_REF = re.compile(r"^evidence_[a-z0-9_-]{3,120}$")
_ITEM_ID = re.compile(r"^brief_item_[a-z0-9_-]{3,120}$")
_RESPONSE_REF = re.compile(r"^response_[a-f0-9]{24}$")
_HTTPS_REF = re.compile(r"^https://[^\s]{1,500}$", re.IGNORECASE)
_SAFE_REASON = re.compile(r"^[a-z][a-z0-9_.-]{2,120}$")
_SAFE_TOPIC = re.compile(r"^[a-z0-9][a-z0-9 _./-]{0,63}$")
_COVERAGE_STATES = frozenset({"checked", "excluded", "unavailable", "stale", "partial"})
_IMPORTANCE = frozenset({"critical", "high", "medium", "low", "unknown"})
_URGENCY = frozenset({"urgent", "soon", "not_marked", "unknown"})


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
    title: str
    summary: str
    observed_at: datetime
    time_kind: Literal["published", "event", "updated"]
    topics: tuple[str, ...]
    importance: Literal["critical", "high", "medium", "low", "unknown"]
    urgency: Literal["urgent", "soon", "not_marked", "unknown"]
    selection_reasons: tuple[str, ...]
    conflict_group: str | None = None
    conflict_value: str | None = None

    def __post_init__(self) -> None:
        if not _EVIDENCE_REF.fullmatch(self.evidence_ref) or not _HTTPS_REF.fullmatch(self.source_ref):
            raise ValueError("brief evidence identity is invalid")
        if _clean(self.title, 240, required=True) is None or _clean(self.summary, 400, required=True) is None:
            raise ValueError("brief evidence text is invalid")
        if self.observed_at.tzinfo is None or self.time_kind not in {"published", "event", "updated"}:
            raise ValueError("brief evidence time is invalid")
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

    def __post_init__(self) -> None:
        if not _ITEM_ID.fullmatch(self.item_id):
            raise ValueError("brief item id is invalid")
        if _clean(self.title, 240, required=True) is None or _clean(self.summary, 400, required=True) is None:
            raise ValueError("brief item text is invalid")
        if not self.evidence_refs or len(self.evidence_refs) > 20 or len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("brief item evidence is invalid")
        if any(not _EVIDENCE_REF.fullmatch(item) for item in self.evidence_refs):
            raise ValueError("brief item evidence is invalid")
        if not self.selection_reasons or any(not _SAFE_REASON.fullmatch(item) for item in self.selection_reasons):
            raise ValueError("brief item reasons are invalid")
        if self.importance not in _IMPORTANCE or self.urgency not in _URGENCY:
            raise ValueError("brief item priority is invalid")

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


@dataclass(frozen=True, slots=True)
class BriefDocument:
    """Immutable report object; ``to_dict`` remains PA-01 schema compatible."""

    brief_id: str
    version: int
    owner_ref: str
    window: BriefWindow
    status: Literal["complete", "partial", "empty"]
    sections: tuple[BriefSection, ...]
    evidence: tuple[BriefEvidence, ...]
    selection_reasons: tuple[str, ...]
    previous_version: BriefVersionRef | None
    coverage_manifest: CoverageManifest
    deduplication: tuple[DeduplicationRecord, ...] = ()
    conflicts: tuple[ConflictRecord, ...] = ()
    comparison_ref: BriefVersionRef | None = None

    def __post_init__(self) -> None:
        if not _BRIEF_ID.fullmatch(self.brief_id) or self.version < 1 or not _OWNER_REF.fullmatch(self.owner_ref):
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
        }

    def inspect(self) -> dict[str, object]:
        """Expose how this exact immutable document was selected and bounded."""

        return {
            "schema_version": BRIEF_INSPECTION_SCHEMA_VERSION,
            "brief_ref": {**self.version_ref.to_dict(), "retention": BRIEF_RETENTION},
            "period": {**self.window.to_dict(), "interval": "[start_at,end_at)"},
            "coverage": {**self.coverage_manifest.to_dict(), "complete": self.coverage_manifest.complete},
            "deduplication": [item.to_dict() for item in self.deduplication],
            "conflicts": [item.to_dict() for item in self.conflicts],
            "importance_vs_urgency": [
                {
                    "item_id": item.item_id,
                    "importance": item.importance,
                    "urgency": item.urgency,
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


@dataclass(frozen=True, slots=True)
class BriefFollowup:
    kind: Literal["explain_item", "shorten", "filter_topics", "compare_weeks"]
    item_number: int | None = None
    topics: tuple[str, ...] = ()


def build_brief_document(request: BriefBuildRequest) -> BriefDocument:
    """Build a deterministic BriefDocument only from local selected evidence."""

    topic = _clean(request.topic, 160, required=True)
    assert topic is not None  # checked by the request type
    brief_id = "brief_" + _digest(
        "prm.brief.logical.v1",
        request.owner_ref,
        topic.casefold(),
        request.window.timezone,
        _iso(request.window.start_at),
        _iso(request.window.end_at),
    )
    previous = request.previous_document
    if previous is not None and previous.brief_id == brief_id:
        version = previous.version + 1
        previous_ref: BriefVersionRef | None = previous.version_ref
    else:
        version = 1
        previous_ref = None

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
    return BriefDocument(
        brief_id=brief_id,
        version=version,
        owner_ref=request.owner_ref,
        window=request.window,
        status=status,
        sections=sections,
        evidence=kept,
        selection_reasons=tuple(reasons),
        previous_version=previous_ref,
        coverage_manifest=coverage,
        deduplication=deduplication,
        conflicts=conflicts,
        comparison_ref=request.comparison_document.version_ref if request.comparison_document is not None else None,
    )


def classify_brief_followup(text: str) -> BriefFollowup | None:
    clean = " ".join(str(text or "").split())
    lowered = clean.casefold()
    item = re.fullmatch(r"(?:объясни|поясни|расскажи про|explain)\s+(?:пункт|item)\s*(\d{1,2})", lowered)
    if item is not None:
        return BriefFollowup("explain_item", item_number=int(item.group(1)))
    if lowered in {"сделай короче", "сократи", "shorten it", "make it shorter"}:
        return BriefFollowup("shorten")
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
    view: Literal["telegram", "short", "item", "topics", "comparison"] = "telegram",
    item_number: int | None = None,
    topics: Sequence[str] = (),
    comparison_document: BriefDocument | None = None,
) -> str:
    """Render a local view of a document; it neither fetches nor regenerates."""

    if type(document) is not BriefDocument:
        raise ValueError("brief document is required")
    if view == "item":
        return _render_item(document, item_number)
    if view == "comparison":
        return _render_comparison(document, comparison_document)
    selected_topics = tuple(_topic(item) for item in topics if _topic(item))
    items = tuple(item for item in document.items if not selected_topics or set(selected_topics) & set(item.topics))
    return _render_telegram(document, items, short=view == "short", topics=selected_topics)


class BriefDocumentStore:
    """Small process-local store reachable only through a visible response."""

    def __init__(self) -> None:
        self._documents: dict[tuple[str, str, int], BriefDocument] = {}
        self._bindings: dict[str, tuple[str, tuple[str, str, int], tuple[str, str, int] | None]] = {}
        self._lock = RLock()

    def clear(self) -> None:
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
    ) -> None:
        if not conversation_id.startswith("conversation_") or not _RESPONSE_REF.fullmatch(response_ref) or type(document) is not BriefDocument:
            raise ValueError("brief visibility binding is invalid")
        if comparison_document is not None and type(comparison_document) is not BriefDocument:
            raise ValueError("brief comparison binding is invalid")
        with self._lock:
            key = (conversation_id, document.brief_id, document.version)
            comparison_key = (
                (conversation_id, comparison_document.brief_id, comparison_document.version)
                if comparison_document is not None
                else None
            )
            incoming = {key, comparison_key} - {None}
            while len(set(self._documents) | incoming) > _MAX_BRIEFS:
                oldest = next(iter(self._documents))
                self._documents.pop(oldest, None)
                self._bindings = {
                    key: value for key, value in self._bindings.items()
                    if value[1] != oldest and value[2] != oldest
                }
            self._documents[key] = document
            if comparison_document is not None:
                assert comparison_key is not None
                self._documents[comparison_key] = comparison_document
            self._bindings[conversation_id] = (response_ref, key, comparison_key)

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
        with self._lock:
            binding = self._bindings.pop(conversation_id, None)
            if binding is None:
                return
            for key in (binding[1], binding[2]):
                if key is not None:
                    self._documents.pop(key, None)

    def render_brief(self, brief_id: str, version: int, view: str, **kwargs: object) -> str | None:
        with self._lock:
            visible_keys = {
                key
                for binding in self._bindings.values()
                for key in (binding[1], binding[2])
                if key is not None
            }
            matches = [
                document
                for key, document in self._documents.items()
                if key in visible_keys and key[1] == brief_id and key[2] == version
            ]
        # An exact version reference still cannot cross an ephemeral private
        # conversation boundary.  Ambiguity fails closed rather than selecting
        # a most-recent report from another visible conversation.
        if len(matches) != 1:
            return None
        document = matches[0]
        if view not in {"telegram", "short", "item", "topics", "comparison"}:
            raise ValueError("brief view is invalid")
        return render_brief_document(document, view=view, **kwargs)  # type: ignore[arg-type]


GLOBAL_BRIEFS = BriefDocumentStore()


def render_brief(brief_id: str, version: int, view: str, *, store: BriefDocumentStore = GLOBAL_BRIEFS, **kwargs: object) -> str | None:
    """Read one exact ephemeral report version; no fallback/latest lookup exists."""

    return store.render_brief(brief_id, version, view, **kwargs)


def _local_archive_evidence(
    raw_items: Sequence[Mapping[str, Any]],
    window: BriefWindow,
) -> tuple[tuple[BriefEvidence, ...], int, int, int]:
    selected: list[BriefEvidence] = []
    invalid = undated = outside = 0
    for raw in raw_items:
        try:
            evidence = _evidence_from_mapping(raw, timezone_name=window.timezone)
        except ValueError:
            invalid += 1
            continue
        if evidence.observed_at is None:  # pragma: no cover - construction is guarded
            undated += 1
            continue
        if not window.contains(evidence.observed_at):
            outside += 1
            continue
        selected.append(evidence)
    return tuple(selected), invalid, undated, outside


def _evidence_from_mapping(raw: Mapping[str, Any], *, timezone_name: str) -> BriefEvidence:
    if raw.get("local_archive_provenance") is not True:
        raise ValueError("brief source lacks local archive provenance")
    identity = _clean(
        raw.get("evidence_id") or raw.get("archive_document_id") or raw.get("post_archive_document_id") or raw.get("post_id"),
        120,
        required=True,
    )
    source_ref = _clean(raw.get("canonical_url") or raw.get("source_url") or raw.get("telegram_url"), 512, required=True)
    summary = _clean(raw.get("support_span") or raw.get("snippet") or raw.get("summary"), 400, required=True)
    title = _clean(raw.get("title"), 240) or _clean(raw.get("channel_username"), 160) or "Архивный материал"
    if identity is None or source_ref is None or summary is None or not _HTTPS_REF.fullmatch(source_ref):
        raise ValueError("brief local archive source is invalid")
    timestamp, time_kind = _source_time(raw, timezone_name=timezone_name)
    if timestamp is None:
        raise ValueError("brief local archive source has no usable event time")
    topics = _topics(raw)
    importance = _importance(raw)
    urgency = _urgency(raw)
    reasons = ["local_archive_source", f"importance_{importance}", f"urgency_{urgency}"]
    if bool(raw.get("personal_relevance") or _mapping(raw.get("relevance")).get("relevant")):
        reasons.append("personal_relevance_marked")
    change = _clean(raw.get("change_type"), 48)
    if change and _SAFE_REASON.fullmatch(f"change_{change.casefold().replace('-', '_')}"):
        reasons.append(f"change_{change.casefold().replace('-', '_')}")
    return BriefEvidence(
        evidence_ref="evidence_" + _slug(identity, fallback=source_ref),
        source_ref=source_ref,
        title=title,
        summary=summary,
        observed_at=timestamp,
        time_kind=time_kind,
        topics=topics,
        importance=importance,
        urgency=urgency,
        selection_reasons=tuple(dict.fromkeys(reasons)),
        conflict_group=_clean(raw.get("conflict_group"), 120, required=True),
        conflict_value=_clean(raw.get("conflict_value"), 240, required=True),
    )


def _source_time(raw: Mapping[str, Any], *, timezone_name: str) -> tuple[datetime | None, Literal["published", "event", "updated"]]:
    for key, kind in (("event_at", "event"), ("published_at", "published"), ("posted_at", "published"), ("updated_at", "updated")):
        parsed = _parse_timestamp(raw.get(key), timezone_name=timezone_name)
        if parsed is not None:
            return parsed, kind
    return None, "published"


def _topics(raw: Mapping[str, Any]) -> tuple[str, ...]:
    relevance = _mapping(raw.get("relevance"))
    values = raw.get("topics") or raw.get("categories") or relevance.get("categories") or ()
    if isinstance(values, str):
        values = (values,)
    if not isinstance(values, (tuple, list)):
        values = ()
    normalized = tuple(dict.fromkeys(value for value in (_topic(item) for item in values) if value))
    return normalized[:8] or ("unclassified",)


def _topic(value: object) -> str:
    clean = " ".join(str(value or "").casefold().split())[:64]
    return clean if _SAFE_TOPIC.fullmatch(clean) else ""


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
        families.setdefault(item.source_ref, []).append(item)
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
    important = [item for item in evidence if item.importance in {"critical", "high"}]
    attention = [item for item in evidence if item.urgency in {"urgent", "soon"} and item not in important]
    remainder = [item for item in evidence if item not in important and item not in attention]
    sections: list[BriefSection] = []
    for section_id, title, items in (
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


def _render_telegram(document: BriefDocument, items: Sequence[BriefItem], *, short: bool, topics: Sequence[str]) -> str:
    period = _period_label(document.window)
    lines = [f"Бриф · {period}", f"Часовой пояс: {document.window.timezone}"]
    if topics:
        lines.append("Темы: " + ", ".join(topics))
    if not items:
        if document.status == "empty" and document.coverage_manifest.complete:
            lines.extend(("", "В проверенной области важных изменений не найдено."))
        else:
            lines.extend(("", "В предоставленной локальной выборке нет пунктов для этого вида; это не вывод за весь период."))
        return _bounded(lines)
    evidence = document.evidence_by_ref()
    index = 0
    for section in document.sections:
        contained = [item for item in section.items if item in items]
        if not contained:
            continue
        lines.extend(("", section.title))
        for item in contained:
            index += 1
            priority = _priority_label(item)
            summary = _short(item.summary, 170 if short else 280)
            lines.append(f"{index}. {item.title} — {summary} [{priority}]")
            if not short:
                source = evidence[item.evidence_refs[0]]
                lines.append(f"   Источник: {source.source_ref}")
            if item.conflict_groups:
                lines.append("   ⚠ В источниках есть неразрешённое расхождение.")
            if short and index >= 3:
                break
        if short and index >= 3:
            break
    lines.extend(("", _coverage_line(document)))
    lines.append(f"Версия: {document.brief_id} v{document.version}")
    return _bounded(lines)


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
        f"Версия BriefDocument: {document.brief_id} v{document.version}",
    ]
    if item.conflict_groups:
        lines.append("Есть неразрешённый конфликт источников; вывод не выравнивался автоматически.")
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
        if key in prior_by_source and item.summary != prior_by_source[key].summary
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


def _priority_label(item: BriefItem) -> str:
    urgency = "срочно" if item.urgency == "urgent" else "скоро" if item.urgency == "soon" else "не отмечена"
    return f"важность: {item.importance}; срочность: {urgency}"


def _coverage_line(document: BriefDocument) -> str:
    states = ", ".join(f"{item.source_ref}: {item.state}" for item in document.coverage_manifest.sources[:3])
    if document.coverage_manifest.complete:
        return f"Покрытие: проверено ({states})."
    return f"Покрытие частичное ({states}); «ничего важного» не утверждается за весь период."


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
