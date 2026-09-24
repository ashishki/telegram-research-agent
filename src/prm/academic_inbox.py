"""PA-12 local, fail-closed Academic Inbox contracts.

Normalizes permitted Canvas/mail/UTD evidence into actionable academic
candidates. It does not run OAuth, fetch a network resource, read grades,
submissions, rosters or attachments, pick a default database, schedule a job or
send anything. Primary-source authority, conflicting deadlines, eligibility
uncertainty, local-done versus source-completion and reminder revisions all
remain explicit and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Literal, Mapping
from zoneinfo import ZoneInfo

from prm.capabilities import (
    AuthorizationDecision,
    CapabilityDenied,
    require_authorized_operation,
)


ACADEMIC_SCHEMA_VERSION = "assistant.academic_candidate.v1"
ACADEMIC_READ_CAPABILITY = "assistant.academic_read"
ACADEMIC_READ_PROVIDER = "provider_canvas"
ACADEMIC_READ_OPERATION = "read"
ACADEMIC_PURPOSE = "academic.read"
DATA_CLASS = "private_connector_content"

_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,511}$")
_CANDIDATE = re.compile(r"^academic_[a-z0-9_-]{3,120}$")
_COURSE = re.compile(r"^course_[A-Za-z0-9_-]{2,120}$")
_SAFE_URL = re.compile(r"^https://[^\s<>]{1,2048}$", re.IGNORECASE)
MAX_ITEMS_LIMIT = 500
MAX_DEADLINES = 8

CATEGORIES = ("obligation", "opportunity", "reading", "administrative", "uncertain")
SOURCE_KINDS = ("canvas_assignment", "canvas_announcement", "canvas_calendar", "mail", "utd_public")
AUTHORITIES = ("canvas", "official_message", "aggregator")
COMPLETIONS = ("not_done", "local_done", "source_completed", "unknown")
_AUTHORITY_RANK = {"canvas": 3, "official_message": 2, "aggregator": 1}

_OPPORTUNITY_HINTS = ("scholarship", "стипенд", "grant", "грант", "mentor", "ментор", "internship", "стажиров", "job", "ваканс", "research opportunity", "конкурс")
_READING_HINTS = ("reading", "chapter", "глава", "article", "статья", "лекц", "учебник", "read ")
_ADMIN_HINTS = ("registration", "регистрац", "housing", "жиль", "insurance", "страхов", "isso", "visa", "виз", "payment", "оплат", "tuition", "иммиграц")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _text(value: object, *, field: str, maximum: int, required: bool = True) -> str:
    text = " ".join(str(value or "").split())
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > maximum:
        raise ValueError(f"{field} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in text):
        raise ValueError(f"{field} contains control characters")
    return text


def _ref(value: object, *, field: str) -> str:
    text = str(value or "")
    if not _REF.fullmatch(text):
        raise ValueError(f"invalid {field}")
    return text


def _tz(value: object) -> str:
    name = _text(value, field="timezone", maximum=64)
    try:
        ZoneInfo(name)
    except Exception as exc:
        raise ValueError("unknown timezone") from exc
    return name


@dataclass(frozen=True, slots=True)
class CanvasScopeSelection:
    """Minimal, read-only Canvas selection; grades/submissions/files are refused."""

    provider_id: str
    account_ref: str
    course_refs: tuple[str, ...]
    window_start: datetime
    window_end: datetime
    local_timezone: str
    max_items: int = 100
    include_assignments: bool = True
    include_announcements: bool = True
    include_calendar: bool = True
    fetch_submissions: bool = False
    fetch_grades: bool = False
    fetch_attachments: bool = False
    schema_version: str = ACADEMIC_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACADEMIC_SCHEMA_VERSION:
            raise ValueError("unsupported academic schema version")
        if self.provider_id != ACADEMIC_READ_PROVIDER:
            raise ValueError("unknown academic provider")
        _ref(self.account_ref, field="account_ref")
        if not self.course_refs or len(self.course_refs) > 32 or len(set(self.course_refs)) != len(self.course_refs):
            raise ValueError("course_refs must be a unique bounded non-empty tuple")
        for course in self.course_refs:
            if not _COURSE.fullmatch(str(course)):
                raise ValueError("invalid course_ref")
        start, end = _utc(self.window_start), _utc(self.window_end)
        if end <= start or (end - start) > timedelta(days=400):
            raise ValueError("invalid academic window")
        _tz(self.local_timezone)
        if not isinstance(self.max_items, int) or isinstance(self.max_items, bool) or not 1 <= self.max_items <= MAX_ITEMS_LIMIT:
            raise ValueError("max_items is out of range")
        if any((self.fetch_submissions, self.fetch_grades, self.fetch_attachments)):
            raise ValueError("academic inbox must not read submissions, grades or attachments")
        if not any((self.include_assignments, self.include_announcements, self.include_calendar)):
            raise ValueError("at least one read surface must be selected")


def describe_canvas_scope(selection: CanvasScopeSelection) -> str:
    surfaces = [
        name
        for name, enabled in (
            ("задания", selection.include_assignments),
            ("объявления", selection.include_announcements),
            ("календарь", selection.include_calendar),
        )
        if enabled
    ]
    return (
        "Canvas: выбран явно. Читаем только " + ", ".join(surfaces) + ". "
        "Оценки, сдачи, ростеры, файлы и вложения не читаются. Только чтение."
    )


@dataclass(frozen=True, slots=True)
class AcademicDeadline:
    label: str
    due_at: datetime
    timezone: str
    authority: Literal["canvas", "official_message", "aggregator"]
    source_ref: str

    def __post_init__(self) -> None:
        _text(self.label, field="deadline label", maximum=160)
        _utc(self.due_at)
        _tz(self.timezone)
        if self.authority not in AUTHORITIES:
            raise ValueError("invalid deadline authority")
        _ref(self.source_ref, field="source_ref")

    def to_payload(self) -> dict[str, object]:
        return {
            "label": self.label,
            "due_at": _iso(self.due_at),
            "timezone": self.timezone,
            "authority": self.authority,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class AcademicCandidate:
    candidate_ref: str
    owner_ref: str
    source_kind: Literal["canvas_assignment", "canvas_announcement", "canvas_calendar", "mail", "utd_public"]
    title: str
    summary: str
    category: Literal["obligation", "opportunity", "reading", "administrative", "uncertain"]
    authority: Literal["canvas", "official_message", "aggregator"]
    deadlines: tuple[AcademicDeadline, ...] = ()
    eligibility_note: str = ""
    eligibility_uncertain: bool = False
    completion: Literal["not_done", "local_done", "source_completed", "unknown"] = "not_done"
    source_refs: tuple[str, ...] = ()
    source_version: str = ""
    schema_version: str = ACADEMIC_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACADEMIC_SCHEMA_VERSION:
            raise ValueError("unsupported academic schema version")
        if not _CANDIDATE.fullmatch(self.candidate_ref):
            raise ValueError("invalid candidate_ref")
        _ref(self.owner_ref, field="owner_ref")
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError("invalid source kind")
        _text(self.title, field="title", maximum=240)
        _text(self.summary, field="summary", maximum=2000, required=False)
        if self.category not in CATEGORIES:
            raise ValueError("invalid category")
        if self.authority not in AUTHORITIES:
            raise ValueError("invalid authority")
        if len(self.deadlines) > MAX_DEADLINES:
            raise ValueError("too many deadlines")
        if self.completion not in COMPLETIONS:
            raise ValueError("invalid completion")
        if not self.source_refs:
            raise ValueError("candidate requires at least one source ref")
        for value in self.source_refs:
            _ref(value, field="source_ref")
        _text(self.eligibility_note, field="eligibility_note", maximum=400, required=False)
        if len(self.source_version) > 200:
            raise ValueError("source_version is too long")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "candidate_ref": self.candidate_ref,
            "owner_ref": self.owner_ref,
            "source_kind": self.source_kind,
            "title": self.title,
            "summary": self.summary,
            "category": self.category,
            "authority": self.authority,
            "deadlines": [deadline.to_payload() for deadline in self.deadlines],
            "eligibility_note": self.eligibility_note,
            "eligibility_uncertain": self.eligibility_uncertain,
            "completion": self.completion,
            "source_refs": list(self.source_refs),
            "source_version": self.source_version,
        }

    @property
    def identity_digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def categorize(source_kind: str, text: str) -> str:
    """Deterministic, stage-agnostic category from the visible text."""

    low = text.casefold()
    if source_kind == "canvas_assignment":
        if any(hint in low for hint in _OPPORTUNITY_HINTS):
            return "opportunity"
        if any(hint in low for hint in _READING_HINTS):
            return "reading"
        return "obligation"
    if any(hint in low for hint in _OPPORTUNITY_HINTS):
        return "opportunity"
    if any(hint in low for hint in _ADMIN_HINTS):
        return "administrative"
    if any(hint in low for hint in _READING_HINTS):
        return "reading"
    return "uncertain"


def authoritative_deadline(candidate: AcademicCandidate) -> AcademicDeadline | None:
    """Highest-authority deadline; canvas outranks mail, mail outranks aggregators."""

    if not candidate.deadlines:
        return None
    return max(candidate.deadlines, key=lambda item: (_AUTHORITY_RANK[item.authority], _utc(item.due_at)))


def conflicting_deadlines(candidate: AcademicCandidate) -> tuple[AcademicDeadline, ...]:
    """Distinct instants that must be surfaced, never merged."""

    instants = {_utc(deadline.due_at) for deadline in candidate.deadlines}
    if len(instants) <= 1:
        return ()
    return candidate.deadlines


def derive_stage(candidate: AcademicCandidate, *, now: datetime) -> str:
    if candidate.completion in {"local_done", "source_completed"}:
        return "completed"
    deadline = authoritative_deadline(candidate)
    if deadline is None:
        return "unknown"
    moment = _utc(now)
    due = _utc(deadline.due_at)
    if due < moment:
        return "overdue"
    if due - moment <= timedelta(days=3):
        return "due_soon"
    return "upcoming"


def deduplicate_candidates(candidates: tuple[AcademicCandidate, ...]) -> tuple[AcademicCandidate, ...]:
    """Merge the same underlying item seen through several sources.

    Identity is (source_kind family, title casefold, earliest deadline day).
    The strongest authority wins; sources and deadlines are unioned so nothing
    is silently dropped.
    """

    groups: dict[tuple[str, str, str], list[AcademicCandidate]] = {}
    order: list[tuple[str, str, str]] = []
    for candidate in candidates:
        deadline = authoritative_deadline(candidate)
        key = (
            candidate.source_kind,
            candidate.title.casefold(),
            deadline.due_at.date().isoformat() if deadline else "",
        )
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(candidate)
    merged: list[AcademicCandidate] = []
    for key in order:
        group = groups[key]
        winner = max(group, key=lambda item: _AUTHORITY_RANK[item.authority])
        from dataclasses import replace

        deadlines: list[AcademicDeadline] = []
        seen_instants: set[tuple[str, datetime]] = set()
        for item in group:
            for deadline in item.deadlines:
                token = (deadline.label, _utc(deadline.due_at))
                if token not in seen_instants:
                    seen_instants.add(token)
                    deadlines.append(deadline)
        sources = tuple(dict.fromkeys(ref for item in group for ref in item.source_refs))
        merged.append(
            replace(
                winner,
                deadlines=tuple(deadlines[:MAX_DEADLINES]),
                source_refs=sources,
                eligibility_uncertain=any(item.eligibility_uncertain for item in group),
            )
        )
    return tuple(merged)


@dataclass(frozen=True, slots=True)
class ReminderPreview:
    reminder_ref: str
    owner_ref: str
    candidate_ref: str
    source_version: str
    lead_minutes: int
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _ref(self.reminder_ref, field="reminder_ref")
        _ref(self.owner_ref, field="owner_ref")
        if not _CANDIDATE.fullmatch(self.candidate_ref):
            raise ValueError("invalid candidate_ref")
        if not isinstance(self.lead_minutes, int) or isinstance(self.lead_minutes, bool) or not 15 <= self.lead_minutes <= 20160:
            raise ValueError("lead_minutes is out of range")
        if _utc(self.expires_at) <= _utc(self.created_at):
            raise ValueError("reminder preview must expire after creation")

    def state_at(self, now: datetime) -> Literal["active", "expired"]:
        return "active" if _utc(now) < _utc(self.expires_at) else "expired"


def build_reminder_preview(
    candidate: AcademicCandidate,
    *,
    owner_ref: str,
    lead_minutes: int,
    now: datetime,
    ttl_seconds: int = 600,
) -> ReminderPreview:
    if not 30 <= ttl_seconds <= 3600:
        raise ValueError("ttl_seconds is out of range")
    moment = _utc(now)
    nonce = hashlib.sha256(
        f"{owner_ref}\x1f{candidate.candidate_ref}\x1f{candidate.source_version}\x1f{lead_minutes}\x1f{_iso(moment)}".encode("utf-8")
    ).hexdigest()[:24]
    return ReminderPreview(
        reminder_ref=f"reminder_{nonce}",
        owner_ref=owner_ref,
        candidate_ref=candidate.candidate_ref,
        source_version=candidate.source_version,
        lead_minutes=lead_minutes,
        created_at=moment,
        expires_at=moment + timedelta(seconds=ttl_seconds),
    )


def confirm_reminder(
    preview: ReminderPreview,
    *,
    candidate: AcademicCandidate,
    owner_ref: str,
    now: datetime,
) -> None:
    """A revision to the source item invalidates the previous reminder basis."""

    if preview.state_at(now) != "active":
        raise ValueError("reminder preview has expired")
    if preview.owner_ref != owner_ref:
        raise ValueError("reminder identity mismatch")
    if preview.candidate_ref != candidate.candidate_ref or preview.source_version != candidate.source_version:
        raise ValueError("reminder basis changed: rebuild the preview from the new source version")


@dataclass(frozen=True, slots=True)
class AcademicFetchRequest:
    authorization: AuthorizationDecision | None
    owner_ref: str
    connection_ref: str
    selection: CanvasScopeSelection
    cursor: str | None = None
    page_size: int | None = None

    def __post_init__(self) -> None:
        _ref(self.owner_ref, field="owner_ref")
        _ref(self.connection_ref, field="connection_ref")
        if self.authorization is not None and type(self.authorization) is not AuthorizationDecision:
            raise ValueError("authorization must be an AuthorizationDecision or None")
        if self.cursor is not None and not re.fullmatch(r"^cursor_[A-Za-z0-9_-]{4,400}$", self.cursor):
            raise ValueError("invalid cursor")
        if self.page_size is not None and (
            not isinstance(self.page_size, int)
            or isinstance(self.page_size, bool)
            or not 1 <= self.page_size <= self.selection.max_items
        ):
            raise ValueError("page_size must not exceed max_items")


def require_academic_read_access(request: AcademicFetchRequest) -> None:
    if request.selection.provider_id != ACADEMIC_READ_PROVIDER:
        raise CapabilityDenied("academic read provider is not enabled for this adapter")
    require_authorized_operation(
        request.authorization,
        capability=ACADEMIC_READ_CAPABILITY,
        operation=ACADEMIC_READ_OPERATION,
        provider_ref=ACADEMIC_READ_PROVIDER,
        data_class=DATA_CLASS,
        owner_ref=request.owner_ref,
        connection_ref=request.connection_ref,
        resource_ref=request.selection.account_ref,
        purpose=ACADEMIC_PURPOSE,
    )
