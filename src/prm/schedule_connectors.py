"""PA-11 local, fail-closed calendar and contacts read contracts.

No OAuth, network call, token storage, default database, scheduler or delivery.
A caller must inject an adapter and a freshly reserved PA-02 authorization at
the read boundary. Calendar and contacts are distinct capabilities: a calendar
grant never authorizes reading a directory, and a contact is never turned into
an email address by guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Literal, Mapping, Protocol
from zoneinfo import ZoneInfo

from prm.capabilities import (
    AuthorizationDecision,
    CapabilityDenied,
    require_authorized_operation,
)


SCHEDULE_SCHEMA_VERSION = "assistant.schedule_connector.v1"
CALENDAR_READ_CAPABILITY = "assistant.calendar_read"
CONTACTS_READ_CAPABILITY = "assistant.contacts_read"
CALENDAR_READ_OPERATION = "read"
CONTACTS_READ_OPERATION = "read"
DATA_CLASS = "private_connector_content"

_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,511}$")
_PROVIDER = re.compile(r"^provider_[a-z0-9_]{3,60}$")
_SAFE_URL = re.compile(r"^https://[^\s<>]{1,2048}$", re.IGNORECASE)
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CURSOR = re.compile(r"^cursor_[A-Za-z0-9_-]{4,400}$")
MAX_CALENDARS = 16
MAX_ITEMS_LIMIT = 500
FREQS = ("daily", "weekly", "monthly")
EVENT_STATUSES = ("confirmed", "tentative", "cancelled")


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
class ScheduleProviderProfile:
    provider_id: str
    display_name: str
    api_base: str
    docs_url: str
    calendar_scopes: tuple[str, ...]
    contacts_scopes: tuple[str, ...]
    read_only: bool = True

    def __post_init__(self) -> None:
        if not _PROVIDER.fullmatch(self.provider_id):
            raise ValueError("invalid provider_id")
        _text(self.display_name, field="display_name", maximum=80)
        if not _SAFE_URL.fullmatch(self.api_base) or not _SAFE_URL.fullmatch(self.docs_url):
            raise ValueError("provider urls must be https")
        for scopes in (self.calendar_scopes, self.contacts_scopes):
            if not scopes or len(scopes) > 16 or any(len(scope) > 120 for scope in scopes):
                raise ValueError("scopes must be a bounded non-empty tuple")


SCHEDULE_PROVIDERS: dict[str, ScheduleProviderProfile] = {
    "provider_microsoft_graph": ScheduleProviderProfile(
        provider_id="provider_microsoft_graph",
        display_name="Microsoft 365",
        api_base="https://graph.microsoft.com/v1.0",
        docs_url="https://learn.microsoft.com/en-us/graph/permissions-reference",
        calendar_scopes=("Calendars.Read", "Calendars.ReadBasic"),
        contacts_scopes=("Contacts.Read",),
    ),
    "provider_google": ScheduleProviderProfile(
        provider_id="provider_google",
        display_name="Google Workspace",
        api_base="https://www.googleapis.com/calendar/v3",
        docs_url="https://developers.google.com/calendar/api/guides/auth",
        calendar_scopes=("https://www.googleapis.com/auth/calendar.readonly",),
        contacts_scopes=("https://www.googleapis.com/auth/contacts.readonly",),
    ),
}


def resolve_schedule_provider(provider_id: str) -> ScheduleProviderProfile:
    try:
        return SCHEDULE_PROVIDERS[provider_id]
    except KeyError as exc:
        raise ValueError("unknown schedule provider") from exc


@dataclass(frozen=True, slots=True)
class CalendarScopeSelection:
    provider_id: str
    account_ref: str
    calendar_refs: tuple[str, ...]
    window_start: datetime
    window_end: datetime
    local_timezone: str
    max_items: int = 100
    include_recurring: bool = True
    include_all_day: bool = True
    schema_version: str = SCHEDULE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEDULE_SCHEMA_VERSION:
            raise ValueError("unsupported schedule schema version")
        resolve_schedule_provider(self.provider_id)
        _ref(self.account_ref, field="account_ref")
        if not self.calendar_refs or len(self.calendar_refs) > MAX_CALENDARS:
            raise ValueError("calendar_refs must be a bounded non-empty tuple")
        if len(set(self.calendar_refs)) != len(self.calendar_refs):
            raise ValueError("calendar_refs must be unique")
        for value in self.calendar_refs:
            _ref(value, field="calendar_ref")
        start, end = _utc(self.window_start), _utc(self.window_end)
        if end <= start:
            raise ValueError("window_end must be after window_start")
        if (end - start) > timedelta(days=370):
            raise ValueError("calendar window is too large")
        _tz(self.local_timezone)
        if not isinstance(self.max_items, int) or isinstance(self.max_items, bool):
            raise ValueError("max_items must be an integer")
        if not 1 <= self.max_items <= MAX_ITEMS_LIMIT:
            raise ValueError("max_items is out of range")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "provider_id": self.provider_id,
            "account_ref": self.account_ref,
            "calendar_refs": list(self.calendar_refs),
            "window_start": _iso(self.window_start),
            "window_end": _iso(self.window_end),
            "local_timezone": self.local_timezone,
            "max_items": self.max_items,
            "include_recurring": self.include_recurring,
            "include_all_day": self.include_all_day,
        }

    @property
    def scope_digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def describe_calendar_scope(selection: CalendarScopeSelection) -> str:
    profile = resolve_schedule_provider(selection.provider_id)
    window = f"{_iso(selection.window_start)} — {_iso(selection.window_end)}"
    return (
        f"Провайдер: {profile.display_name} (выбран явно). Календари: {len(selection.calendar_refs)}. "
        f"Окно: {window}. Локальная зона: {selection.local_timezone}. Только чтение: без создания, "
        "изменения, приглашений и удаления событий."
    )


@dataclass(frozen=True, slots=True)
class CalendarConsentPreview:
    preview_ref: str
    owner_ref: str
    connection_ref: str
    account_ref: str
    provider_id: str
    scope_digest: str
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for name, value in (("preview_ref", self.preview_ref), ("owner_ref", self.owner_ref), ("connection_ref", self.connection_ref), ("account_ref", self.account_ref)):
            _ref(value, field=name)
        resolve_schedule_provider(self.provider_id)
        if not re.fullmatch(r"[0-9a-f]{64}", self.scope_digest):
            raise ValueError("invalid scope digest")
        if _utc(self.expires_at) <= _utc(self.created_at):
            raise ValueError("preview must expire after creation")

    def state_at(self, now: datetime) -> Literal["active", "expired"]:
        return "active" if _utc(now) < _utc(self.expires_at) else "expired"


def build_calendar_consent_preview(
    selection: CalendarScopeSelection,
    *,
    owner_ref: str,
    connection_ref: str,
    now: datetime,
    ttl_seconds: int = 600,
) -> CalendarConsentPreview:
    if not 30 <= ttl_seconds <= 3600:
        raise ValueError("ttl_seconds is out of range")
    moment = _utc(now)
    nonce = hashlib.sha256(
        f"{owner_ref}\x1f{connection_ref}\x1f{selection.scope_digest}\x1f{_iso(moment)}".encode("utf-8")
    ).hexdigest()[:24]
    return CalendarConsentPreview(
        preview_ref=f"calpreview_{nonce}",
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        account_ref=selection.account_ref,
        provider_id=selection.provider_id,
        scope_digest=selection.scope_digest,
        created_at=moment,
        expires_at=moment + timedelta(seconds=ttl_seconds),
    )


def confirm_calendar_scope(
    preview: CalendarConsentPreview,
    *,
    selection: CalendarScopeSelection,
    owner_ref: str,
    connection_ref: str,
    now: datetime,
) -> None:
    if preview.state_at(now) != "active":
        raise ValueError("calendar consent preview has expired")
    if preview.owner_ref != owner_ref or preview.connection_ref != connection_ref:
        raise ValueError("calendar consent identity mismatch")
    if (
        selection.provider_id != preview.provider_id
        or selection.account_ref != preview.account_ref
        or selection.scope_digest != preview.scope_digest
    ):
        raise ValueError("calendar scope does not match the confirmed preview")


@dataclass(frozen=True, slots=True)
class RecurrenceRule:
    """A bounded recurrence rule; no server-side expansion is assumed."""

    dtstart: datetime
    freq: Literal["daily", "weekly", "monthly"]
    interval: int = 1
    count: int | None = None
    until: datetime | None = None

    def __post_init__(self) -> None:
        _utc(self.dtstart)
        if self.freq not in FREQS:
            raise ValueError("invalid recurrence frequency")
        if not isinstance(self.interval, int) or isinstance(self.interval, bool) or not 1 <= self.interval <= 366:
            raise ValueError("invalid recurrence interval")
        if self.count is not None and (not isinstance(self.count, int) or isinstance(self.count, bool) or not 1 <= self.count <= 1000):
            raise ValueError("invalid recurrence count")
        if self.count is not None and self.until is not None:
            raise ValueError("recurrence cannot set both count and until")
        if self.until is not None and _utc(self.until) < _utc(self.dtstart):
            raise ValueError("recurrence until precedes dtstart")

    def occurs_on(self, day: date) -> bool:
        target = _utc(datetime(day.year, day.month, day.day, tzinfo=timezone.utc))
        start = _utc(self.dtstart)
        if self.freq == "daily":
            step_days = self.interval
            delta = (target.date() - start.date()).days
            if delta < 0 or delta % step_days != 0:
                return False
        elif self.freq == "weekly":
            delta = (target.date() - start.date()).days
            if delta < 0 or delta % (7 * self.interval) != 0:
                return False
        else:  # monthly
            months = (target.year - start.year) * 12 + (target.month - start.month)
            if months < 0 or months % self.interval != 0 or target.day != start.day:
                return False
        if self.count is not None:
            return self._index_of(day) < self.count
        if self.until is not None:
            return _utc(datetime(day.year, day.month, day.day, tzinfo=timezone.utc)) <= _utc(self.until)
        return True

    def _index_of(self, day: date) -> int:
        start = _utc(self.dtstart).date()
        if self.freq == "daily":
            return (day - start).days // self.interval
        if self.freq == "weekly":
            return (day - start).days // (7 * self.interval)
        months = (day.year - start.year) * 12 + (day.month - start.month)
        return months // self.interval


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    event_ref: str
    calendar_ref: str
    account_ref: str
    title: str
    start_at: datetime
    end_at: datetime
    source_timezone: str
    status: Literal["confirmed", "tentative", "cancelled"] = "confirmed"
    all_day: bool = False
    is_recurring: bool = False
    recurrence_id: str | None = None
    version: str = ""
    source_ref: str = ""

    def __post_init__(self) -> None:
        _ref(self.event_ref, field="event_ref")
        _ref(self.calendar_ref, field="calendar_ref")
        _ref(self.account_ref, field="account_ref")
        _text(self.title, field="title", maximum=240, required=False)
        start, end = _utc(self.start_at), _utc(self.end_at)
        if end < start:
            raise ValueError("event end precedes start")
        _tz(self.source_timezone)
        if self.status not in EVENT_STATUSES:
            raise ValueError("invalid event status")
        if self.is_recurring:
            _text(self.recurrence_id or "", field="recurrence_id", maximum=200)
        if any(ord(char) < 32 for char in self.version):
            raise ValueError("invalid version")
        if len(self.version) > 200:
            raise ValueError("version is too long")
        if self.source_ref:
            _ref(self.source_ref, field="source_ref")

    def local_span(self, local_timezone: str) -> tuple[datetime, datetime]:
        zone = ZoneInfo(_tz(local_timezone))
        return self.start_at.astimezone(zone), self.end_at.astimezone(zone)


def detect_conflicts(events: tuple[CalendarEvent, ...]) -> tuple[tuple[str, str], ...]:
    """Return overlapping pairs (cancelled events excluded); order-preserving."""

    active = [event for event in events if event.status != "cancelled"]
    pairs: list[tuple[str, str]] = []
    for index, first in enumerate(active):
        for second in active[index + 1:]:
            if _utc(first.start_at) < _utc(second.end_at) and _utc(second.start_at) < _utc(first.end_at):
                pairs.append((first.event_ref, second.event_ref))
    return tuple(pairs)


@dataclass(frozen=True, slots=True)
class BusyInterval:
    calendar_ref: str
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        _ref(self.calendar_ref, field="calendar_ref")
        if _utc(self.end_at) <= _utc(self.start_at):
            raise ValueError("busy interval must have positive length")


def free_busy(events: tuple[CalendarEvent, ...], *, local_timezone: str) -> tuple[BusyInterval, ...]:
    """Derive busy intervals from confirmed/tentative events in source order."""

    intervals = [
        BusyInterval(event.calendar_ref, event.start_at, event.end_at)
        for event in events
        if event.status != "cancelled"
    ]
    return tuple(intervals)


@dataclass(frozen=True, slots=True)
class CalendarFetchRequest:
    authorization: AuthorizationDecision | None
    owner_ref: str
    connection_ref: str
    selection: CalendarScopeSelection
    cursor: str | None = None
    page_size: int | None = None  # None means "use the confirmed max_items"

    def __post_init__(self) -> None:
        _ref(self.owner_ref, field="owner_ref")
        _ref(self.connection_ref, field="connection_ref")
        if self.authorization is not None and type(self.authorization) is not AuthorizationDecision:
            raise ValueError("authorization must be an AuthorizationDecision or None")
        if self.cursor is not None and not _CURSOR.fullmatch(self.cursor):
            raise ValueError("invalid cursor")
        if self.page_size is not None and (
            not isinstance(self.page_size, int)
            or isinstance(self.page_size, bool)
            or not 1 <= self.page_size <= self.selection.max_items
        ):
            raise ValueError("page_size must not exceed the confirmed max_items")


def require_calendar_read_access(request: CalendarFetchRequest) -> None:
    if request.selection.provider_id not in ("provider_microsoft_graph", "provider_google"):
        raise CapabilityDenied("calendar read provider is not enabled for this adapter")
    require_authorized_operation(
        request.authorization,
        capability=CALENDAR_READ_CAPABILITY,
        operation=CALENDAR_READ_OPERATION,
        provider_ref=request.selection.provider_id,
        data_class=DATA_CLASS,
        owner_ref=request.owner_ref,
        connection_ref=request.connection_ref,
        resource_ref=request.selection.account_ref,
        purpose="calendar.read",
    )


# --- Contacts (directory resolution; never guess an address) ---------------


@dataclass(frozen=True, slots=True)
class Contact:
    contact_ref: str
    account_ref: str
    display_name: str
    emails: tuple[str, ...]
    source_ref: str = ""

    def __post_init__(self) -> None:
        _ref(self.contact_ref, field="contact_ref")
        _ref(self.account_ref, field="account_ref")
        _text(self.display_name, field="display_name", maximum=160)
        if not self.emails or len(self.emails) > 8:
            raise ValueError("contact emails must be a bounded non-empty tuple")
        if len(set(self.emails)) != len(self.emails):
            raise ValueError("contact emails must be unique")
        for email in self.emails:
            if not _EMAIL.fullmatch(email) or len(email) > 254:
                raise ValueError("invalid contact email")
        if self.source_ref:
            _ref(self.source_ref, field="source_ref")


@dataclass(frozen=True, slots=True)
class RecipientResolution:
    query: str
    status: Literal["resolved", "ambiguous", "not_found"]
    contact_ref: str | None
    candidates: tuple[str, ...]


def resolve_recipient(
    query: str,
    contacts: tuple[Contact, ...],
    *,
    accounts: tuple[str, ...] = (),
) -> RecipientResolution:
    """Resolve a recipient only when exactly one contact matches; else ambiguous."""

    clean = _text(query, field="query", maximum=160)
    if accounts:
        contacts = tuple(contact for contact in contacts if contact.account_ref in accounts)
    needle = clean.casefold()
    matches: list[str] = []
    for contact in contacts:
        haystacks = [contact.display_name.casefold(), *(email.casefold() for email in contact.emails)]
        if any(needle == value or needle in value for value in haystacks):
            matches.append(contact.contact_ref)
    unique = tuple(dict.fromkeys(matches))
    if len(unique) == 1:
        return RecipientResolution(clean, "resolved", unique[0], unique)
    if unique:
        return RecipientResolution(clean, "ambiguous", None, unique[:8])
    return RecipientResolution(clean, "not_found", None, ())


@dataclass(frozen=True, slots=True)
class ContactsFetchRequest:
    authorization: AuthorizationDecision | None
    owner_ref: str
    connection_ref: str
    provider_id: str
    account_ref: str
    query: str = ""
    cursor: str | None = None
    page_size: int = 50

    def __post_init__(self) -> None:
        _ref(self.owner_ref, field="owner_ref")
        _ref(self.connection_ref, field="connection_ref")
        resolve_schedule_provider(self.provider_id)
        _ref(self.account_ref, field="account_ref")
        _text(self.query, field="query", maximum=160, required=False)
        if self.authorization is not None and type(self.authorization) is not AuthorizationDecision:
            raise ValueError("authorization must be an AuthorizationDecision or None")
        if self.cursor is not None and not _CURSOR.fullmatch(self.cursor):
            raise ValueError("invalid cursor")
        if not isinstance(self.page_size, int) or isinstance(self.page_size, bool) or not 1 <= self.page_size <= MAX_ITEMS_LIMIT:
            raise ValueError("page_size is out of range")


def require_contacts_read_access(request: ContactsFetchRequest) -> None:
    require_authorized_operation(
        request.authorization,
        capability=CONTACTS_READ_CAPABILITY,
        operation=CONTACTS_READ_OPERATION,
        provider_ref=request.provider_id,
        data_class=DATA_CLASS,
        owner_ref=request.owner_ref,
        connection_ref=request.connection_ref,
        resource_ref=request.account_ref,
        purpose="contacts.read",
    )


class CalendarReadAdapter(Protocol):
    def fetch_page(self, request: CalendarFetchRequest) -> tuple[CalendarEvent, ...]: ...

    def revoke(self, account_ref: str) -> None: ...


class ContactsReadAdapter(Protocol):
    def fetch_page(self, request: ContactsFetchRequest) -> tuple[Contact, ...]: ...

    def revoke(self, account_ref: str) -> None: ...
