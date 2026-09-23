"""PA-10 local, fail-closed contracts for selected read-only mail.

This module deliberately does *not* run an OAuth flow, read or store a token,
open a network connection, select a default database, poll on a timer, or send
a Telegram message. A caller must inject a provider adapter and a freshly
reserved PA-02 authorization at the read boundary. The implemented surface is a
small, explicit-path derived sidecar for normalized thread summaries only; raw
mail bodies and attachments are never retained here.

The provider is selected explicitly (never guessed from an email address), the
scope selection is documented honestly (an application folder/domain filter is
not a provider-enforced token restriction), and unknown outcomes stay closed.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Literal, Mapping, Protocol, Sequence

from assistant.prm_post_answer_actions import canonical_private_owner_id
from prm.capabilities import (
    AuthorizationDecision,
    CapabilityDenied,
    require_authorized_operation,
)


MAIL_CONNECTOR_SCHEMA_VERSION = "assistant.mail_connector.v1"
MAIL_SUMMARY_SCHEMA_VERSION = "assistant.mail_thread_summary.v1"
MAIL_READ_CAPABILITY = "assistant.mail_read"
MAIL_READ_PROVIDER = "provider_microsoft_graph"
MAIL_READ_OPERATION = "read"
MAIL_READ_PURPOSE = "mail.read"
MAIL_DATA_CLASS = "private_connector_content"

_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,511}$")
_THREAD = re.compile(r"^thread_[a-z0-9_-]{3,120}$")
_CURSOR = re.compile(r"^cursor_[A-Za-z0-9_-]{4,400}$")
_DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")
_PROVIDER = re.compile(r"^provider_[a-z0-9_]{3,60}$")
_SAFE_URL = re.compile(r"^https://[^\s<>]{1,2048}$", re.IGNORECASE)

CATEGORIES = ("obligation", "opportunity", "reading", "administrative", "uncertain")
VERIFICATION_AUTHORITIES = ("canvas", "official_message", "aggregator")
DeadlineAuthority = Literal["canvas", "official_message", "aggregator"]
MAX_SCOPE_FOLDERS = 24
MAX_SCOPE_DOMAINS = 24
MAX_ITEMS_LIMIT = 500


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty string")
    return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _bounded_text(value: object, *, field: str, maximum: int, required: bool = True) -> str:
    if value is None:
        value = ""
    text = " ".join(str(value).split())
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > maximum:
        raise ValueError(f"{field} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in text):
        raise ValueError(f"{field} contains control characters")
    return text


def _ref(value: object, *, field: str, pattern: re.Pattern[str] = _REF) -> str:
    text = str(value or "")
    if not pattern.fullmatch(text):
        raise ValueError(f"invalid {field}")
    return text


def mail_owner_ref_from_authenticated_private_tuple(
    chat_id: str | None,
    actor_id: str | None,
    owner_chat_id: str | None,
) -> str | None:
    """Derive durable mail ownership only from the canonical private tuple."""

    values = tuple(canonical_private_owner_id(value) for value in (chat_id, actor_id, owner_chat_id))
    if any(value is None for value in values) or len(set(values)) != 1:
        return None
    canonical = "\x1f".join(value for value in values if value is not None)
    digest = hashlib.sha256(f"pa10.mail.owner.v1:{canonical}".encode("utf-8")).hexdigest()
    return "owner_mail_" + digest[:24]


@dataclass(frozen=True, slots=True)
class MailProviderProfile:
    """Documented, non-secret provider capabilities used to explain scope."""

    provider_id: str
    display_name: str
    auth_kind: Literal["oauth2_delegated", "oauth2_authorization_code"]
    api_base: str
    docs_url: str
    default_read_scopes: tuple[str, ...]
    token_scope_is_mailbox_wide: bool
    supports_folder_filter: bool
    supports_incremental_sync: bool
    notes: str

    def __post_init__(self) -> None:
        _ref(self.provider_id, field="provider_id", pattern=_PROVIDER)
        _bounded_text(self.display_name, field="display_name", maximum=80)
        if self.auth_kind not in ("oauth2_delegated", "oauth2_authorization_code"):
            raise ValueError("invalid auth_kind")
        if not _SAFE_URL.fullmatch(self.api_base):
            raise ValueError("api_base must be an https URL")
        if not _SAFE_URL.fullmatch(self.docs_url):
            raise ValueError("docs_url must be an https URL")
        if not self.default_read_scopes or len(self.default_read_scopes) > 16:
            raise ValueError("read scopes must be a bounded non-empty tuple")
        for scope in self.default_read_scopes:
            _bounded_text(scope, field="scope", maximum=120)
        _bounded_text(self.notes, field="notes", maximum=400)


MAIL_PROVIDER_PROFILES: dict[str, MailProviderProfile] = {
    "provider_microsoft_graph": MailProviderProfile(
        provider_id="provider_microsoft_graph",
        display_name="Microsoft 365 (Exchange Online)",
        auth_kind="oauth2_delegated",
        api_base="https://graph.microsoft.com/v1.0",
        docs_url="https://learn.microsoft.com/en-us/graph/permissions-reference",
        default_read_scopes=("Mail.ReadBasic", "Calendars.Read", "Contacts.Read"),
        token_scope_is_mailbox_wide=True,
        supports_folder_filter=True,
        supports_incremental_sync=True,
        notes=(
            "Делегированный доступ; Mail.ReadBasic покрывает весь ящик. Отдельная "
            "папка/домен — прикладной фильтр, не ограничение токена."
        ),
    ),
    "provider_gmail": MailProviderProfile(
        provider_id="provider_gmail",
        display_name="Gmail",
        auth_kind="oauth2_authorization_code",
        api_base="https://gmail.googleapis.com/gmail/v1",
        docs_url="https://developers.google.com/workspace/gmail/api/auth/scopes",
        default_read_scopes=("https://www.googleapis.com/auth/gmail.readonly",),
        token_scope_is_mailbox_wide=True,
        supports_folder_filter=True,
        supports_incremental_sync=True,
        notes=(
            "gmail.readonly покрывает весь ящик; label-фильтр — прикладной. "
            "Провайдер выбирается явно, не угадывается по адресу."
        ),
    ),
}


def resolve_mail_provider(provider_id: str) -> MailProviderProfile:
    try:
        return MAIL_PROVIDER_PROFILES[provider_id]
    except KeyError as exc:
        raise ValueError("unknown mail provider profile") from exc


@dataclass(frozen=True, slots=True)
class MailScopeSelection:
    """A bounded, read-only selection; v1 forbids bodies and attachments."""

    provider_id: str
    resource_ref: str
    folders: tuple[str, ...] = ()
    sender_domains: tuple[str, ...] = ()
    since: datetime | None = None
    until: datetime | None = None
    max_items: int = 50
    fetch_body: bool = False
    include_attachments: bool = False
    schema_version: str = MAIL_CONNECTOR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MAIL_CONNECTOR_SCHEMA_VERSION:
            raise ValueError("unsupported mail connector schema version")
        resolve_mail_provider(self.provider_id)
        if not _REF.fullmatch(self.resource_ref):
            raise ValueError("invalid resource_ref")
        if len(self.folders) > MAX_SCOPE_FOLDERS or len(set(self.folders)) != len(self.folders):
            raise ValueError("folders must be a unique bounded tuple")
        for folder in self.folders:
            _bounded_text(folder, field="folder", maximum=80)
        if len(self.sender_domains) > MAX_SCOPE_DOMAINS or len(set(self.sender_domains)) != len(self.sender_domains):
            raise ValueError("sender_domains must be a unique bounded tuple")
        for domain in self.sender_domains:
            if not _DOMAIN.fullmatch(domain):
                raise ValueError("invalid sender domain")
        if self.fetch_body:
            raise ValueError("v1 mail read must never fetch message bodies")
        if self.include_attachments:
            raise ValueError("v1 mail read must never fetch attachments")
        if not isinstance(self.max_items, int) or isinstance(self.max_items, bool):
            raise ValueError("max_items must be an integer")
        if not 1 <= self.max_items <= MAX_ITEMS_LIMIT:
            raise ValueError("max_items is out of range")
        if self.since is not None:
            _utc(self.since)
        if self.until is not None:
            _utc(self.until)
        if self.since is not None and self.until is not None and _utc(self.since) > _utc(self.until):
            raise ValueError("since must not be after until")

    def to_payload(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "resource_ref": self.resource_ref,
            "folders": list(self.folders),
            "sender_domains": list(self.sender_domains),
            "since": _iso(self.since) if self.since else None,
            "until": _iso(self.until) if self.until else None,
            "max_items": self.max_items,
            "fetch_body": self.fetch_body,
            "include_attachments": self.include_attachments,
            "schema_version": self.schema_version,
        }

    @property
    def scope_digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def describe_mail_scope(selection: MailScopeSelection) -> str:
    """Render the honest read boundary; never imply a narrower token scope."""

    profile = resolve_mail_provider(selection.provider_id)
    parts = [f"Провайдер: {profile.display_name} (выбран явно)."]
    parts.append(f"Читаем максимум {selection.max_items} писем.")
    if selection.folders:
        parts.append("Папки/метки: " + ", ".join(selection.folders) + ".")
    if selection.sender_domains:
        parts.append("Отправители: " + ", ".join(selection.sender_domains) + ".")
    if selection.since or selection.until:
        window = f"с {_iso(selection.since)}" if selection.since else "с начала"
        window += f" по {_iso(selection.until)}" if selection.until else ""
        parts.append(f"Окно: {window}.")
    if profile.token_scope_is_mailbox_wide:
        parts.append(
            "Важно: запрошенный OAuth-скоуп покрывает весь ящик; папка/домен — "
            "только прикладной фильтр. Вложения не читаются, тела писем не сохраняются."
        )
    parts.append("Только чтение: без отправки, отметок «прочитано» и правил почты.")
    return " ".join(parts)


@dataclass(frozen=True, slots=True)
class MailConsentPreview:
    preview_ref: str
    owner_ref: str
    connection_ref: str
    provider_id: str
    scope_digest: str
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _ref(self.preview_ref, field="preview_ref")
        _ref(self.owner_ref, field="owner_ref")
        _ref(self.connection_ref, field="connection_ref")
        resolve_mail_provider(self.provider_id)
        if not re.fullmatch(r"[0-9a-f]{64}", self.scope_digest):
            raise ValueError("invalid scope digest")
        if _utc(self.expires_at) <= _utc(self.created_at):
            raise ValueError("preview must expire after creation")

    def state_at(self, now: datetime) -> Literal["active", "expired"]:
        return "active" if _utc(now) < _utc(self.expires_at) else "expired"


@dataclass(frozen=True, slots=True)
class MailConsentConfirmation:
    owner_ref: str
    connection_ref: str
    scope_digest: str
    confirmed_at: datetime

    def __post_init__(self) -> None:
        _ref(self.owner_ref, field="owner_ref")
        _ref(self.connection_ref, field="connection_ref")
        if not re.fullmatch(r"[0-9a-f]{64}", self.scope_digest):
            raise ValueError("invalid scope digest")
        _utc(self.confirmed_at)


def build_mail_consent_preview(
    selection: MailScopeSelection,
    *,
    owner_ref: str,
    connection_ref: str,
    now: datetime,
    ttl_seconds: int = 600,
) -> MailConsentPreview:
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool) or not 30 <= ttl_seconds <= 3600:
        raise ValueError("ttl_seconds is out of range")
    moment = _utc(now)
    nonce = hashlib.sha256(
        f"{owner_ref}\x1f{connection_ref}\x1f{selection.scope_digest}\x1f{_iso(moment)}".encode("utf-8")
    ).hexdigest()[:24]
    return MailConsentPreview(
        preview_ref=f"mailpreview_{nonce}",
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        provider_id=selection.provider_id,
        scope_digest=selection.scope_digest,
        created_at=moment,
        expires_at=moment + timedelta(seconds=ttl_seconds),
    )


def confirm_mail_scope(
    preview: MailConsentPreview,
    confirmation: MailConsentConfirmation,
    *,
    selection: MailScopeSelection,
    now: datetime,
) -> None:
    """Validate an exact identity/scope/expiry binding for a preview.

    This helper is stateless: single-use consumption is enforced by the
    authorization/transport layer that owns the preview, not here.
    """

    moment = _utc(now)
    if preview.state_at(moment) != "active":
        raise ValueError("mail consent preview has expired")
    if confirmation.owner_ref != preview.owner_ref or confirmation.connection_ref != preview.connection_ref:
        raise ValueError("mail consent identity mismatch")
    if confirmation.scope_digest != preview.scope_digest:
        raise ValueError("mail consent scope changed")
    if selection.provider_id != preview.provider_id or selection.scope_digest != preview.scope_digest:
        raise ValueError("mail scope does not match the confirmed preview")


@dataclass(frozen=True, slots=True)
class MailFetchRequest:
    """One paged, read-only fetch bound to a reserved authorization."""

    authorization: AuthorizationDecision
    owner_ref: str
    connection_ref: str
    selection: MailScopeSelection
    cursor: str | None = None
    page_size: int = 50

    def __post_init__(self) -> None:
        _ref(self.owner_ref, field="owner_ref")
        _ref(self.connection_ref, field="connection_ref")
        if self.authorization is not None and type(self.authorization) is not AuthorizationDecision:
            raise ValueError("authorization must be an AuthorizationDecision or None")
        if self.cursor is not None and not _CURSOR.fullmatch(self.cursor):
            raise ValueError("invalid cursor")
        if not isinstance(self.page_size, int) or isinstance(self.page_size, bool):
            raise ValueError("page_size must be an integer")
        if not 1 <= self.page_size <= self.selection.max_items:
            raise ValueError("page_size must not exceed the confirmed max_items")


@dataclass(frozen=True, slots=True)
class MailMessage:
    message_ref: str
    thread_ref: str
    received_at: datetime
    sender_domain: str
    subject: str
    snippet: str

    def __post_init__(self) -> None:
        _ref(self.message_ref, field="message_ref")
        _ref(self.thread_ref, field="thread_ref", pattern=_THREAD)
        _utc(self.received_at)
        if not _DOMAIN.fullmatch(self.sender_domain):
            raise ValueError("invalid sender domain")
        _bounded_text(self.subject, field="subject", maximum=240, required=False)
        _bounded_text(self.snippet, field="snippet", maximum=400, required=False)


@dataclass(frozen=True, slots=True)
class MailFetchPage:
    messages: tuple[MailMessage, ...]
    next_cursor: str | None
    has_more: bool

    def __post_init__(self) -> None:
        if len(self.messages) > MAX_ITEMS_LIMIT:
            raise ValueError("page exceeds the maximum item count")
        if len({message.message_ref for message in self.messages}) != len(self.messages):
            raise ValueError("page message refs must be unique")
        if self.next_cursor is not None and not _CURSOR.fullmatch(self.next_cursor):
            raise ValueError("invalid next_cursor")
        if self.has_more and self.next_cursor is None:
            raise ValueError("a page that has more must provide a cursor")


class MailReadAdapter(Protocol):
    """Injected by an authorized caller; this module ships no live adapter."""

    def fetch_page(self, request: MailFetchRequest) -> MailFetchPage: ...

    def revoke(self, connection_ref: str) -> None: ...


def require_mail_read_access(request: MailFetchRequest) -> None:
    """Fail closed unless a matching PA-02 mail-read reservation is present."""

    if request.selection.provider_id != MAIL_READ_PROVIDER:
        raise CapabilityDenied("mail read provider is not enabled for this adapter")
    require_authorized_operation(
        request.authorization,
        capability=MAIL_READ_CAPABILITY,
        operation=MAIL_READ_OPERATION,
        provider_ref=MAIL_READ_PROVIDER,
        data_class=MAIL_DATA_CLASS,
        owner_ref=request.owner_ref,
        connection_ref=request.connection_ref,
        resource_ref=request.selection.resource_ref,
        purpose=MAIL_READ_PURPOSE,
    )


@dataclass(frozen=True, slots=True)
class MailDeadline:
    text: str
    due_at: datetime | None
    timezone: str
    authority: DeadlineAuthority
    source_ref: str

    def __post_init__(self) -> None:
        _bounded_text(self.text, field="deadline text", maximum=240)
        _bounded_text(self.timezone, field="timezone", maximum=64)
        if self.authority not in VERIFICATION_AUTHORITIES:
            raise ValueError("invalid deadline authority")
        _ref(self.source_ref, field="source_ref")
        if self.due_at is not None:
            _utc(self.due_at)

    def to_payload(self) -> dict[str, object]:
        return {
            "text": self.text,
            "due_at": _iso(self.due_at) if self.due_at else None,
            "timezone": self.timezone,
            "authority": self.authority,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class MailThreadSummary:
    """Normalized, bounded summary; never a raw message dump."""

    summary_ref: str
    owner_ref: str
    provider_id: str
    thread_ref: str
    subject: str
    category: Literal["obligation", "opportunity", "reading", "administrative", "uncertain"]
    takeaways: tuple[str, ...]
    decisions: tuple[str, ...]
    deadlines: tuple[MailDeadline, ...]
    opportunities: tuple[str, ...]
    excerpt: str
    source_refs: tuple[str, ...]
    retrieved_at: datetime
    freshness: Literal["fresh", "stale", "unknown"]
    schema_version: str = MAIL_SUMMARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MAIL_SUMMARY_SCHEMA_VERSION:
            raise ValueError("unsupported mail summary schema version")
        _ref(self.summary_ref, field="summary_ref")
        _ref(self.owner_ref, field="owner_ref")
        resolve_mail_provider(self.provider_id)
        _ref(self.thread_ref, field="thread_ref", pattern=_THREAD)
        _bounded_text(self.subject, field="subject", maximum=240, required=False)
        if self.category not in CATEGORIES:
            raise ValueError("invalid category")
        for name, values, limit in (
            ("takeaways", self.takeaways, 8),
            ("decisions", self.decisions, 8),
            ("opportunities", self.opportunities, 8),
            ("source_refs", self.source_refs, 16),
        ):
            if len(values) > limit or len(set(values)) != len(values):
                raise ValueError(f"{name} must be a unique bounded tuple")
            for value in values:
                _bounded_text(value, field=name, maximum=300)
        if len(self.deadlines) > 8:
            raise ValueError("deadlines must be a bounded tuple")
        _bounded_text(self.excerpt, field="excerpt", maximum=400, required=False)
        _utc(self.retrieved_at)
        if self.freshness not in ("fresh", "stale", "unknown"):
            raise ValueError("invalid freshness")

    @property
    def has_conflicting_deadlines(self) -> bool:
        instants = {_utc(deadline.due_at) for deadline in self.deadlines if deadline.due_at is not None}
        return len(instants) > 1

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "summary_ref": self.summary_ref,
            "owner_ref": self.owner_ref,
            "provider_id": self.provider_id,
            "thread_ref": self.thread_ref,
            "subject": self.subject,
            "category": self.category,
            "takeaways": list(self.takeaways),
            "decisions": list(self.decisions),
            "deadlines": [deadline.to_payload() for deadline in self.deadlines],
            "opportunities": list(self.opportunities),
            "excerpt": self.excerpt,
            "source_refs": list(self.source_refs),
            "retrieved_at": _iso(self.retrieved_at),
            "freshness": self.freshness,
        }

    @property
    def content_digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @classmethod
    def from_payload(cls, payload: object) -> "MailThreadSummary":
        if not isinstance(payload, Mapping):
            raise ValueError("mail summary payload must be a mapping")
        if payload.get("schema_version") != MAIL_SUMMARY_SCHEMA_VERSION:
            raise ValueError("unsupported mail summary schema version")
        deadlines = tuple(
            MailDeadline(
                text=str(item.get("text") or ""),
                due_at=_parse_utc(item["due_at"]) if item.get("due_at") else None,
                timezone=str(item.get("timezone") or ""),
                authority=str(item.get("authority") or ""),  # type: ignore[arg-type]
                source_ref=str(item.get("source_ref") or ""),
            )
            for item in payload.get("deadlines") or []  # type: ignore[union-attr]
            if isinstance(item, Mapping)
        )
        return cls(
            summary_ref=str(payload.get("summary_ref") or ""),
            owner_ref=str(payload.get("owner_ref") or ""),
            provider_id=str(payload.get("provider_id") or ""),
            thread_ref=str(payload.get("thread_ref") or ""),
            subject=str(payload.get("subject") or ""),
            category=str(payload.get("category") or ""),  # type: ignore[arg-type]
            takeaways=tuple(str(item) for item in payload.get("takeaways") or []),  # type: ignore[union-attr]
            decisions=tuple(str(item) for item in payload.get("decisions") or []),  # type: ignore[union-attr]
            deadlines=deadlines,
            opportunities=tuple(str(item) for item in payload.get("opportunities") or []),  # type: ignore[union-attr]
            excerpt=str(payload.get("excerpt") or ""),
            source_refs=tuple(str(item) for item in payload.get("source_refs") or []),  # type: ignore[union-attr]
            retrieved_at=_parse_utc(payload.get("retrieved_at")),
            freshness=str(payload.get("freshness") or ""),  # type: ignore[arg-type]
        )


MAIL_DERIVED_SCHEMA = """
CREATE TABLE IF NOT EXISTS pa_mail_derived_summaries(
    owner_ref TEXT NOT NULL,
    connection_ref TEXT NOT NULL,
    thread_ref TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY(owner_ref, thread_ref)
);
"""


class MailDerivedStore:
    """Explicit-path sidecar for normalized summaries only; never raw mail."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(MAIL_DERIVED_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def write_summary(self, summary: MailThreadSummary, *, connection_ref: str) -> None:
        _ref(connection_ref, field="connection_ref")
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO pa_mail_derived_summaries"
                "(owner_ref, connection_ref, thread_ref, summary_json, content_digest, retrieved_at)"
                " VALUES(?,?,?,?,?,?)"
                " ON CONFLICT(owner_ref, thread_ref) DO UPDATE SET"
                " connection_ref=excluded.connection_ref,"
                " summary_json=excluded.summary_json,"
                " content_digest=excluded.content_digest,"
                " retrieved_at=excluded.retrieved_at",
                (
                    summary.owner_ref,
                    connection_ref,
                    summary.thread_ref,
                    json.dumps(summary.to_payload(), ensure_ascii=False, sort_keys=True),
                    summary.content_digest,
                    _iso(summary.retrieved_at),
                ),
            )

    def list_summaries(self, owner_ref: str, *, limit: int = 50) -> tuple[MailThreadSummary, ...]:
        _ref(owner_ref, field="owner_ref")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
            raise ValueError("limit is out of range")
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT summary_json FROM pa_mail_derived_summaries"
                " WHERE owner_ref=? ORDER BY retrieved_at DESC LIMIT ?",
                (owner_ref, limit),
            ).fetchall()
        return tuple(MailThreadSummary.from_payload(json.loads(row[0])) for row in rows)

    def delete_owner(self, owner_ref: str) -> int:
        _ref(owner_ref, field="owner_ref")
        with closing(self._connect()) as conn:
            cursor = conn.execute("DELETE FROM pa_mail_derived_summaries WHERE owner_ref=?", (owner_ref,))
        return int(cursor.rowcount or 0)

    def delete_connection(self, owner_ref: str, connection_ref: str) -> int:
        _ref(owner_ref, field="owner_ref")
        _ref(connection_ref, field="connection_ref")
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                "DELETE FROM pa_mail_derived_summaries WHERE owner_ref=? AND connection_ref=?",
                (owner_ref, connection_ref),
            )
        return int(cursor.rowcount or 0)

    def count(self, owner_ref: str) -> int:
        _ref(owner_ref, field="owner_ref")
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM pa_mail_derived_summaries WHERE owner_ref=?", (owner_ref,)
            ).fetchone()
        return int(row[0]) if row else 0
