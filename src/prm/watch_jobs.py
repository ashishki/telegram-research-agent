"""Local, fail-closed contracts for PA-09 watches, jobs and reconciliation.

This module deliberately does *not* run a scheduler, collect a source, read
credentials, send a Telegram message, or select a default database.  A caller
must explicitly provide a local SQLite path and a freshly reserved PA-02
capability decision at the collection/send boundary.  The durable tables are a
small derived job sidecar, not a production migration or an application
startup hook.

The boundary is intentionally narrower than a worker implementation: it makes
the state that a future authorized worker must preserve explicit, while keeping
unknown delivery outcomes closed until reconciliation establishes what happened.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Callable, Literal, Mapping
from zoneinfo import ZoneInfo

from prm.capabilities import (
    AuthorizationDecision,
    CapabilityDenied,
    is_authorized_operation,
    require_authorized_operation,
    transport_purpose,
)
from prm.briefs import brief_owner_ref_from_authenticated_private_tuple


WATCH_SUBSCRIPTION_SCHEMA_VERSION = "assistant.watch_subscription.v1"
WATCH_JOB_SCHEMA_VERSION = "assistant.watch_job.v1"
WATCH_DELIVERY_CAPABILITY = "assistant.watch_delivery"
WATCH_DELIVERY_PROVIDER = "provider_telegram"
WATCH_DELIVERY_PURPOSE = "watch.delivery"
WATCH_COLLECTION_CAPABILITY = "assistant.watch_collection"
WATCH_COLLECTION_PROVIDER = "provider_watch_source"
WATCH_COLLECTION_PURPOSE = "watch.collection"
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,511}$")
_SUBSCRIPTION = re.compile(r"^watch_[a-z0-9_-]{3,120}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,191}$")
_STAGE = re.compile(r"^[a-z][a-z0-9_.:-]{2,95}$")
_DIGEST_STAGE = re.compile(r"^digest:[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_TIME = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
_SAFE_URL = re.compile(r"^https://[^\s<>]{1,2048}$", re.IGNORECASE)
_LIFECYCLES = frozenset({"active", "paused", "cancelled", "completed"})
_SUBJECT_STATES = frozenset({"active", "completed", "cancelled", "not_relevant"})
_JOB_STATES = frozenset({"queued", "leased", "deferred", "unknown", "sent", "cancelled"})
_TRIGGERS = frozenset({"meaningful_change", "deadline_reminder", "digest"})
_FREQUENCIES = frozenset({"immediate", "daily", "weekly"})
_DATA_CLASSES = frozenset({
    "public", "user_provided", "private_archive", "private_connector_metadata",
    "private_connector_content", "model_generated",
})
_FEEDBACK_ACTIONS = frozenset({"pause", "unsubscribe", "done", "not_relevant", "less"})
_DEADLINE_STAGES = frozenset({"deadline:14d", "deadline:7d", "deadline:1d", "deadline:due"})


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("stored timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("stored timestamp is invalid") from exc
    return _utc(parsed)


def _bounded_text(value: object, *, field: str, maximum: int, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} is invalid")
    text = " ".join(value.split())
    if (required and not text) or len(text) > maximum:
        raise ValueError(f"{field} is invalid")
    return text


def _ref(value: object, *, field: str, pattern: re.Pattern[str] = _REF) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{field} is invalid")
    return value


def watch_owner_ref_from_authenticated_private_tuple(
    chat_id: str | None,
    actor_id: str | None,
    owner_chat_id: str | None,
) -> str | None:
    """Use PA-07's canonical private-owner binding for every watch mutation."""
    return brief_owner_ref_from_authenticated_private_tuple(chat_id, actor_id, owner_chat_id)


@dataclass(frozen=True, slots=True)
class WatchSubscription:
    """An exact confirmed watch intent; it does not claim a worker is running."""

    subscription_id: str
    owner_ref: str
    consent_revision: int
    source_refs: tuple[str, ...]
    destination_ref: str
    trigger: Literal["meaningful_change", "deadline_reminder", "digest"]
    timezone_name: str
    expires_at: datetime
    daily_cap: int
    frequency: Literal["immediate", "daily", "weekly"] = "immediate"
    delivery_time: str | None = None
    delivery_weekday: int | None = None
    quiet_start: str | None = None
    quiet_end: str | None = None
    lifecycle: Literal["active", "paused", "cancelled", "completed"] = "active"
    paused_until: datetime | None = None
    allow_urgent_during_quiet_hours: bool = False
    schema_version: str = WATCH_SUBSCRIPTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _ref(self.subscription_id, field="subscription_id", pattern=_SUBSCRIPTION)
        _ref(self.owner_ref, field="owner_ref")
        _ref(self.destination_ref, field="destination_ref")
        if (
            not isinstance(self.consent_revision, int)
            or isinstance(self.consent_revision, bool)
            or self.consent_revision < 1
        ):
            raise ValueError("consent_revision is invalid")
        if (
            not isinstance(self.source_refs, tuple)
            or not self.source_refs
            or len(self.source_refs) > 16
            or len(set(self.source_refs)) != len(self.source_refs)
        ):
            raise ValueError("source_refs are invalid")
        for source_ref in self.source_refs:
            _ref(source_ref, field="source_ref")
        if self.trigger not in _TRIGGERS:
            raise ValueError("trigger is invalid")
        try:
            ZoneInfo(self.timezone_name)
        except Exception as exc:
            raise ValueError("timezone_name is invalid") from exc
        _utc(self.expires_at)
        if self.paused_until is not None:
            _utc(self.paused_until)
        if not isinstance(self.daily_cap, int) or isinstance(self.daily_cap, bool) or not 1 <= self.daily_cap <= 24:
            raise ValueError("daily_cap is invalid")
        if self.frequency not in _FREQUENCIES:
            raise ValueError("frequency is invalid")
        if self.delivery_time is not None and not _TIME.fullmatch(self.delivery_time):
            raise ValueError("delivery_time is invalid")
        if self.frequency == "immediate":
            if self.delivery_time is not None or self.delivery_weekday is not None:
                raise ValueError("immediate watches have no schedule")
        elif self.delivery_time is None:
            raise ValueError("scheduled watches require delivery_time")
        if self.frequency == "weekly":
            if not isinstance(self.delivery_weekday, int) or isinstance(self.delivery_weekday, bool) or not 0 <= self.delivery_weekday <= 6:
                raise ValueError("weekly delivery_weekday is invalid")
        elif self.delivery_weekday is not None:
            raise ValueError("delivery_weekday is only valid for weekly watches")
        if self.trigger == "digest" and self.frequency == "immediate":
            raise ValueError("digest watches require a delivery schedule")
        if (self.quiet_start is None) != (self.quiet_end is None):
            raise ValueError("quiet hours are incomplete")
        if self.quiet_start is not None and (not _TIME.fullmatch(self.quiet_start) or not _TIME.fullmatch(self.quiet_end or "")):
            raise ValueError("quiet hours are invalid")
        if self.lifecycle not in _LIFECYCLES:
            raise ValueError("lifecycle is invalid")
        if not isinstance(self.allow_urgent_during_quiet_hours, bool):
            raise ValueError("allow_urgent_during_quiet_hours is invalid")
        if self.schema_version != WATCH_SUBSCRIPTION_SCHEMA_VERSION:
            raise ValueError("subscription schema is invalid")


@dataclass(frozen=True, slots=True)
class WatchNotification:
    """A source-bound notification explanation, never a bare activity ping."""

    subscription_id: str
    owner_ref: str
    subject_ref: str
    change_version: str
    delivery_stage: str
    title: str
    change_summary: str
    relevance_reason: str
    source_ref: str
    due_at: datetime
    data_class: str = "model_generated"
    source_url: str | None = None
    urgent: bool = False

    def __post_init__(self) -> None:
        _ref(self.subscription_id, field="subscription_id", pattern=_SUBSCRIPTION)
        _ref(self.owner_ref, field="owner_ref")
        _ref(self.subject_ref, field="subject_ref")
        _ref(self.change_version, field="change_version", pattern=_VERSION)
        _ref(self.delivery_stage, field="delivery_stage", pattern=_STAGE)
        if self.delivery_stage != "change" and self.delivery_stage not in _DEADLINE_STAGES and not _valid_digest_stage(self.delivery_stage):
            raise ValueError("delivery_stage is invalid")
        _bounded_text(self.title, field="title", maximum=240)
        # These two fields are a materiality gate.  A timestamp-only or
        # relevance-free candidate cannot create a watch alert.
        _bounded_text(self.change_summary, field="change_summary", maximum=800)
        _bounded_text(self.relevance_reason, field="relevance_reason", maximum=800)
        _ref(self.source_ref, field="source_ref")
        _utc(self.due_at)
        if self.data_class not in _DATA_CLASSES:
            raise ValueError("data_class is invalid")
        if self.source_url is not None and (not isinstance(self.source_url, str) or not _SAFE_URL.fullmatch(self.source_url)):
            raise ValueError("source_url is invalid")
        if not isinstance(self.urgent, bool):
            raise ValueError("urgent is invalid")

    @property
    def idempotency_key(self) -> str:
        material = "\x1f".join((
            self.subscription_id, self.owner_ref, self.subject_ref,
            self.change_version, self.delivery_stage,
        ))
        return "watchjob_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:40]


@dataclass(frozen=True, slots=True)
class WatchJob:
    job_key: str
    notification: WatchNotification
    subscription_revision: int
    state: str
    attempts: int
    lease_token: str | None = None
    lease_until: datetime | None = None

    def __post_init__(self) -> None:
        _ref(self.job_key, field="job_key")
        if type(self.notification) is not WatchNotification:
            raise ValueError("notification is invalid")
        if not isinstance(self.subscription_revision, int) or isinstance(self.subscription_revision, bool) or self.subscription_revision < 1:
            raise ValueError("subscription_revision is invalid")
        if self.state not in _JOB_STATES:
            raise ValueError("job state is invalid")
        if not isinstance(self.attempts, int) or isinstance(self.attempts, bool) or self.attempts < 0:
            raise ValueError("attempts are invalid")
        if self.lease_token is not None:
            _ref(self.lease_token, field="lease_token")
        if self.lease_until is not None:
            _utc(self.lease_until)


@dataclass(frozen=True, slots=True)
class WatchQueueResult:
    status: Literal["queued", "duplicate", "blocked"]
    reason: str
    job: WatchJob | None = None


@dataclass(frozen=True, slots=True)
class WatchSubscriptionPreview:
    """One expiring exact subscription preview, before durable confirmation."""

    confirmation_ref: str
    subscription: WatchSubscription
    expires_at: datetime
    content_digest: str


@dataclass(frozen=True, slots=True)
class WatchReconciliationEvidence:
    """A typed observation bound to one owner and PA-02 delivery operation."""

    job_key: str
    owner_ref: str
    operation_ref: str
    outcome: Literal["delivered", "not_delivered"]
    evidence_ref: str
    observed_at: datetime

    def __post_init__(self) -> None:
        _ref(self.job_key, field="job_key")
        _ref(self.owner_ref, field="owner_ref")
        _ref(self.operation_ref, field="operation_ref")
        if self.outcome not in {"delivered", "not_delivered"}:
            raise ValueError("reconciliation outcome is invalid")
        _ref(self.evidence_ref, field="evidence_ref")
        _utc(self.observed_at)


@dataclass(frozen=True, slots=True)
class WatchReconciliationRequirement:
    """The persisted PA-02 operation that a future adapter must reconcile."""

    job_key: str
    owner_ref: str
    destination_ref: str
    operation_ref: str
    unknown_at: datetime

    def __post_init__(self) -> None:
        _ref(self.job_key, field="job_key")
        _ref(self.owner_ref, field="owner_ref")
        _ref(self.destination_ref, field="destination_ref")
        _ref(self.operation_ref, field="operation_ref")
        _utc(self.unknown_at)


@dataclass(frozen=True, slots=True)
class WatchDeliveryAccess:
    """One freshly reserved PA-02 Telegram watch-delivery decision."""

    authorization: AuthorizationDecision
    owner_ref: str
    destination_ref: str
    data_class: str

    def __post_init__(self) -> None:
        if type(self.authorization) is not AuthorizationDecision:
            raise ValueError("watch delivery requires a typed authorization")
        _ref(self.owner_ref, field="owner_ref")
        _ref(self.destination_ref, field="destination_ref")
        if self.data_class not in _DATA_CLASSES:
            raise ValueError("data_class is invalid")
        if transport_purpose(
            provider_ref=WATCH_DELIVERY_PROVIDER,
            capability=WATCH_DELIVERY_CAPABILITY,
            operation="deliver",
        ) != WATCH_DELIVERY_PURPOSE:
            raise ValueError("watch delivery transport purpose is unavailable")
        decision = self.authorization
        if (
            not decision.allowed
            or decision.reservation is None
            or not decision.operation_ref
            or decision.reservation.operation_ref != decision.operation_ref
            or decision.owner_ref != self.owner_ref
            or decision.resource_ref != self.destination_ref
            or decision.provider_ref != WATCH_DELIVERY_PROVIDER
            or decision.capability != WATCH_DELIVERY_CAPABILITY
            or decision.operation != "deliver"
            or decision.data_class != self.data_class
            or decision.purpose != WATCH_DELIVERY_PURPOSE
        ):
            raise ValueError("watch delivery authorization is out of scope")


@dataclass(frozen=True, slots=True)
class WatchCollectionAccess:
    """A typed PA-02 read reservation checked before a watch source is read."""

    authorization: AuthorizationDecision
    owner_ref: str
    source_ref: str

    def __post_init__(self) -> None:
        if type(self.authorization) is not AuthorizationDecision:
            raise ValueError("watch collection requires a typed authorization")
        _ref(self.owner_ref, field="owner_ref")
        _ref(self.source_ref, field="source_ref")
        decision = self.authorization
        if (
            not decision.allowed
            or decision.reservation is None
            or decision.owner_ref != self.owner_ref
            or decision.resource_ref != self.source_ref
            or decision.provider_ref != WATCH_COLLECTION_PROVIDER
            or decision.capability != WATCH_COLLECTION_CAPABILITY
            or decision.operation != "read"
            or decision.purpose != WATCH_COLLECTION_PURPOSE
        ):
            raise ValueError("watch collection authorization is out of scope")


class KnownWatchDeliveryFailure(Exception):
    """A synthetic/adapter failure known to have made no external send."""


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    """The exact preflight record an authorized transport must finish honestly."""

    job: WatchJob
    text: str
    authorization: AuthorizationDecision


@dataclass(frozen=True, slots=True)
class WatchRunResult:
    """A local one-shot runner receipt; it does not imply a service exists."""

    claimed: int
    sent: int
    deferred: int
    unknown: int
    blocked: int


WATCH_JOB_SCHEMA = """
CREATE TABLE IF NOT EXISTS pa_watch_subscriptions(
 subscription_id TEXT PRIMARY KEY,
 owner_ref TEXT NOT NULL,
 consent_revision INTEGER NOT NULL,
 lifecycle TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 document_json TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pa_watch_subscription_confirmations(
 confirmation_ref TEXT PRIMARY KEY,
 owner_ref TEXT NOT NULL,
 subscription_json TEXT NOT NULL,
 content_digest TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('previewed','confirmed','cancelled','expired')),
 created_at TEXT NOT NULL,
 confirmed_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS pa_watch_subjects(
 subscription_id TEXT NOT NULL,
 subject_ref TEXT NOT NULL,
 current_version TEXT NOT NULL,
 lifecycle TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 PRIMARY KEY(subscription_id, subject_ref)
);
CREATE TABLE IF NOT EXISTS pa_watch_jobs(
 job_key TEXT PRIMARY KEY,
 subscription_id TEXT NOT NULL,
 owner_ref TEXT NOT NULL,
 subscription_revision INTEGER NOT NULL,
 subject_ref TEXT NOT NULL,
 change_version TEXT NOT NULL,
 delivery_stage TEXT NOT NULL,
 notification_json TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('queued','leased','deferred','unknown','sent','cancelled')),
 due_at TEXT NOT NULL,
 lease_token TEXT NOT NULL DEFAULT '',
 lease_until TEXT NOT NULL DEFAULT '',
 attempts INTEGER NOT NULL DEFAULT 0,
 retry_after TEXT NOT NULL DEFAULT '',
 last_reason TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pa_watch_receipts(
 job_key TEXT PRIMARY KEY,
 outcome TEXT NOT NULL CHECK(outcome IN ('sent','reconciled_delivered')),
 delivered_at TEXT NOT NULL,
 transport_receipt_ref TEXT,
 detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pa_watch_quota_reservations(
 job_key TEXT PRIMARY KEY,
 subscription_id TEXT NOT NULL,
 local_day TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pa_watch_unknown_attempts(
 job_key TEXT PRIMARY KEY,
 owner_ref TEXT NOT NULL,
 destination_ref TEXT NOT NULL,
 operation_ref TEXT NOT NULL,
 grant_ref TEXT NOT NULL,
 grant_revision INTEGER NOT NULL,
 unknown_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pa_watch_feedback(
 job_key TEXT NOT NULL,
 action TEXT NOT NULL,
 recorded_at TEXT NOT NULL,
 UNIQUE(job_key, action)
);
"""


class WatchJobStore:
    """An explicit-path local durable sidecar for watch state and receipts."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript(WATCH_JOB_SCHEMA)

    def preview_subscription(
        self,
        subscription: WatchSubscription,
        *,
        authenticated_chat_id: str | None,
        authenticated_actor_id: str | None,
        authenticated_owner_chat_id: str | None,
        now: datetime | None = None,
    ) -> WatchSubscriptionPreview | None:
        """Store one owner-bound expiring preview; it creates no active watch."""
        self._validate_subscription(subscription)
        current = _utc(now or datetime.now(timezone.utc))
        if watch_owner_ref_from_authenticated_private_tuple(
            authenticated_chat_id, authenticated_actor_id, authenticated_owner_chat_id,
        ) != subscription.owner_ref:
            return None
        payload = _subscription_payload(subscription)
        digest = _digest_payload(payload)
        preview = WatchSubscriptionPreview(
            "watchconfirm_" + secrets.token_hex(16), subscription,
            current + timedelta(minutes=10), digest,
        )
        with sqlite3.connect(self.path) as db:
            existing = db.execute(
                "SELECT owner_ref,consent_revision FROM pa_watch_subscriptions WHERE subscription_id=?",
                (subscription.subscription_id,),
            ).fetchone()
            if existing is not None and (
                str(existing[0]) != subscription.owner_ref
                or subscription.consent_revision != int(existing[1]) + 1
            ):
                return None
            db.execute(
                "INSERT INTO pa_watch_subscription_confirmations(confirmation_ref,owner_ref,subscription_json,content_digest,expires_at,state,created_at) VALUES(?,?,?,?,?,'previewed',?)",
                (
                    preview.confirmation_ref, subscription.owner_ref, json.dumps(payload, sort_keys=True),
                    preview.content_digest, _iso(preview.expires_at), _iso(current),
                ),
            )
            db.commit()
        return preview

    def confirm_subscription(
        self,
        confirmation_ref: str,
        *,
        authenticated_chat_id: str | None,
        authenticated_actor_id: str | None,
        authenticated_owner_chat_id: str | None,
        now: datetime | None = None,
    ) -> WatchSubscription | None:
        """Consume one exact unexpired preview; no caller-built subscription is accepted."""
        _ref(confirmation_ref, field="confirmation_ref")
        current = _utc(now or datetime.now(timezone.utc))
        owner_ref = watch_owner_ref_from_authenticated_private_tuple(
            authenticated_chat_id, authenticated_actor_id, authenticated_owner_chat_id,
        )
        if owner_ref is None:
            return None
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT owner_ref,subscription_json,content_digest,expires_at,state FROM pa_watch_subscription_confirmations WHERE confirmation_ref=?",
                (confirmation_ref,),
            ).fetchone()
            if row is None or str(row[0]) != owner_ref or str(row[4]) != "previewed":
                db.rollback()
                return None
            if _parse_utc(row[3]) <= current:
                db.execute("UPDATE pa_watch_subscription_confirmations SET state='expired' WHERE confirmation_ref=? AND state='previewed'", (confirmation_ref,))
                db.commit()
                return None
            try:
                payload = json.loads(str(row[1]))
                subscription = _subscription_from_payload(payload)
            except (TypeError, json.JSONDecodeError, ValueError):
                db.execute("UPDATE pa_watch_subscription_confirmations SET state='cancelled' WHERE confirmation_ref=?", (confirmation_ref,))
                db.commit()
                return None
            if subscription.owner_ref != owner_ref or _digest_payload(_subscription_payload(subscription)) != str(row[2]):
                db.execute("UPDATE pa_watch_subscription_confirmations SET state='cancelled' WHERE confirmation_ref=?", (confirmation_ref,))
                db.commit()
                return None
            existing = db.execute("SELECT document_json FROM pa_watch_subscriptions WHERE subscription_id=?", (subscription.subscription_id,)).fetchone()
            if existing is not None:
                try:
                    prior = _subscription_from_payload(json.loads(str(existing[0])))
                except (TypeError, json.JSONDecodeError, ValueError):
                    prior = None
                if prior is None or prior.owner_ref != subscription.owner_ref or subscription.consent_revision != prior.consent_revision + 1:
                    db.rollback()
                    return None
                updated_subscription = db.execute(
                    "UPDATE pa_watch_subscriptions SET consent_revision=?,lifecycle=?,expires_at=?,document_json=?,updated_at=? WHERE subscription_id=? AND consent_revision=?",
                    (subscription.consent_revision, subscription.lifecycle, _iso(subscription.expires_at), json.dumps(_subscription_payload(subscription), sort_keys=True), _iso(current), subscription.subscription_id, prior.consent_revision),
                )
                if updated_subscription.rowcount != 1:
                    db.rollback()
                    return None
                db.execute(
                    "UPDATE pa_watch_jobs SET state='cancelled',last_reason='subscription_revised',updated_at=? WHERE subscription_id=? AND state IN ('queued','deferred')",
                    (_iso(current), subscription.subscription_id),
                )
            else:
                db.execute(
                    "INSERT INTO pa_watch_subscriptions(subscription_id,owner_ref,consent_revision,lifecycle,expires_at,document_json,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (subscription.subscription_id, subscription.owner_ref, subscription.consent_revision, subscription.lifecycle, _iso(subscription.expires_at), json.dumps(_subscription_payload(subscription), sort_keys=True), _iso(current)),
                )
            updated = db.execute(
                "UPDATE pa_watch_subscription_confirmations SET state='confirmed',confirmed_at=? WHERE confirmation_ref=? AND state='previewed'",
                (_iso(current), confirmation_ref),
            )
            if updated.rowcount != 1:
                db.rollback()
                return None
            db.commit()
        return subscription

    def subscription(self, subscription_id: str) -> WatchSubscription | None:
        _ref(subscription_id, field="subscription_id", pattern=_SUBSCRIPTION)
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT document_json FROM pa_watch_subscriptions WHERE subscription_id=?", (subscription_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            return _subscription_from_payload(json.loads(str(row[0])))
        except (TypeError, json.JSONDecodeError, ValueError):
            return None

    def collection_allowed(
        self,
        subscription_id: str,
        access: WatchCollectionAccess,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Consume a current source-read reservation only for an active watch."""
        subscription = self.subscription(subscription_id)
        current = _utc(now or datetime.now(timezone.utc))
        if (
            subscription is None
            or access.owner_ref != subscription.owner_ref
            or access.source_ref not in subscription.source_refs
            or _subscription_effect(subscription, now=current) != "active"
        ):
            return False
        decision = access.authorization
        if not is_authorized_operation(
            decision,
            capability=WATCH_COLLECTION_CAPABILITY,
            operation="read",
            provider_ref=WATCH_COLLECTION_PROVIDER,
            data_class=decision.data_class,
            owner_ref=subscription.owner_ref,
            connection_ref=decision.connection_ref,
            resource_ref=access.source_ref,
            purpose=WATCH_COLLECTION_PURPOSE,
        ):
            return False
        try:
            require_authorized_operation(
                decision,
                capability=WATCH_COLLECTION_CAPABILITY,
                operation="read",
                provider_ref=WATCH_COLLECTION_PROVIDER,
                data_class=decision.data_class,
                owner_ref=subscription.owner_ref,
                connection_ref=decision.connection_ref,
                resource_ref=access.source_ref,
                purpose=WATCH_COLLECTION_PURPOSE,
            )
        except CapabilityDenied:
            return False
        return True

    def queue_notification(
        self,
        notification: WatchNotification,
        *,
        expected_subscription_revision: int,
        now: datetime | None = None,
    ) -> WatchQueueResult:
        """Durably queue one meaningful version; repeat evidence is a duplicate."""
        self._validate_notification(notification)
        if not isinstance(expected_subscription_revision, int) or isinstance(expected_subscription_revision, bool):
            raise ValueError("expected_subscription_revision is invalid")
        current = _utc(now or datetime.now(timezone.utc))
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            subscription = self._load_subscription_in(db, notification.subscription_id)
            if subscription is None or subscription.owner_ref != notification.owner_ref:
                db.rollback()
                return WatchQueueResult("blocked", "subscription_unavailable")
            if subscription.consent_revision != expected_subscription_revision:
                db.rollback()
                return WatchQueueResult("blocked", "subscription_revision_mismatch")
            effect = _subscription_effect(subscription, now=current)
            if effect != "active":
                db.rollback()
                return WatchQueueResult("blocked", effect)
            if notification.source_ref not in subscription.source_refs:
                db.rollback()
                return WatchQueueResult("blocked", "source_not_confirmed")
            if not _stage_matches_trigger(notification.delivery_stage, subscription.trigger):
                db.rollback()
                return WatchQueueResult("blocked", "trigger_mismatch")
            subject = db.execute(
                "SELECT current_version,lifecycle FROM pa_watch_subjects WHERE subscription_id=? AND subject_ref=?",
                (notification.subscription_id, notification.subject_ref),
            ).fetchone()
            if subject is not None and str(subject[1]) in {"completed", "cancelled", "not_relevant"}:
                db.rollback()
                return WatchQueueResult("blocked", "subject_" + str(subject[1]))
            if subject is None:
                db.execute(
                    "INSERT INTO pa_watch_subjects(subscription_id,subject_ref,current_version,lifecycle,updated_at) VALUES(?,?,?,'active',?)",
                    (notification.subscription_id, notification.subject_ref, notification.change_version, _iso(current)),
                )
            elif str(subject[0]) != notification.change_version:
                # Changed deadline/fact: old waiting versions must not alert;
                # a leased old version is checked again at terminal preflight.
                db.execute(
                    "UPDATE pa_watch_subjects SET current_version=?,updated_at=? WHERE subscription_id=? AND subject_ref=?",
                    (notification.change_version, _iso(current), notification.subscription_id, notification.subject_ref),
                )
                db.execute(
                    "UPDATE pa_watch_jobs SET state='cancelled',last_reason='superseded_change_version',updated_at=? WHERE subscription_id=? AND subject_ref=? AND change_version<>? AND state IN ('queued','deferred')",
                    (_iso(current), notification.subscription_id, notification.subject_ref, notification.change_version),
                )
            key = notification.idempotency_key
            existing = db.execute("SELECT state FROM pa_watch_jobs WHERE job_key=?", (key,)).fetchone()
            if existing is not None:
                db.rollback()
                return WatchQueueResult("duplicate", "same_subject_version_stage")
            db.execute(
                "INSERT INTO pa_watch_jobs(job_key,subscription_id,owner_ref,subscription_revision,subject_ref,change_version,delivery_stage,notification_json,state,due_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?, 'queued',?,?,?)",
                (
                    key, notification.subscription_id, notification.owner_ref, subscription.consent_revision,
                    notification.subject_ref, notification.change_version, notification.delivery_stage,
                    json.dumps(_notification_payload(notification), sort_keys=True), _iso(notification.due_at), _iso(current), _iso(current),
                ),
            )
            db.commit()
        job = WatchJob(key, notification, subscription.consent_revision, "queued", 0)
        return WatchQueueResult("queued", "meaningful_change", job)

    def claim_due_jobs(
        self,
        *,
        now: datetime | None = None,
        limit: int = 8,
        lease_seconds: int = 60,
        max_attempts: int = 3,
    ) -> tuple[WatchJob, ...]:
        """Atomically lease bounded due work; expired leases become unknown."""
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 32:
            raise ValueError("limit is invalid")
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds is invalid")
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts is invalid")
        current = _utc(now or datetime.now(timezone.utc))
        current_text = _iso(current)
        claimed: list[WatchJob] = []
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE pa_watch_jobs SET state='unknown',lease_token='',lease_until='',last_reason='lease_expired_reconciliation_required',updated_at=? WHERE state='leased' AND lease_until<>'' AND lease_until<=?",
                (current_text, current_text),
            )
            rows = db.execute(
                "SELECT job_key,notification_json,subscription_revision,state,attempts FROM pa_watch_jobs WHERE state IN ('queued','deferred') AND due_at<=? AND (retry_after='' OR retry_after<=?) ORDER BY due_at,created_at LIMIT ?",
                (current_text, current_text, limit * 3),
            ).fetchall()
            for job_key, raw, revision, state, attempts in rows:
                if len(claimed) >= limit:
                    break
                try:
                    notification = _notification_from_payload(json.loads(str(raw)))
                except (TypeError, json.JSONDecodeError, ValueError):
                    db.execute(
                        "UPDATE pa_watch_jobs SET state='cancelled',last_reason='invalid_notification',updated_at=? WHERE job_key=?",
                        (current_text, job_key),
                    )
                    continue
                subscription = self._load_subscription_in(db, notification.subscription_id)
                policy = _job_policy(subscription, notification, now=current)
                if policy in {"quiet_hours", "schedule_wait"}:
                    continue
                if policy != "active":
                    db.execute(
                        "UPDATE pa_watch_jobs SET state='cancelled',last_reason=?,updated_at=? WHERE job_key=? AND state IN ('queued','deferred')",
                        (policy, current_text, job_key),
                    )
                    continue
                subject = db.execute(
                    "SELECT current_version,lifecycle FROM pa_watch_subjects WHERE subscription_id=? AND subject_ref=?",
                    (notification.subscription_id, notification.subject_ref),
                ).fetchone()
                if subject is None or str(subject[0]) != notification.change_version or str(subject[1]) != "active":
                    db.execute(
                        "UPDATE pa_watch_jobs SET state='cancelled',last_reason='subject_not_current',updated_at=? WHERE job_key=?",
                        (current_text, job_key),
                    )
                    continue
                if int(attempts) >= max_attempts:
                    db.execute(
                        "UPDATE pa_watch_jobs SET state='unknown',last_reason='retry_budget_exhausted',updated_at=? WHERE job_key=?",
                        (current_text, job_key),
                    )
                    continue
                lease_token = "lease_" + secrets.token_hex(16)
                lease_until = _iso(current + timedelta(seconds=lease_seconds))
                updated = db.execute(
                    "UPDATE pa_watch_jobs SET state='leased',attempts=attempts+1,lease_token=?,lease_until=?,updated_at=? WHERE job_key=? AND state IN ('queued','deferred')",
                    (lease_token, lease_until, current_text, job_key),
                )
                if updated.rowcount == 1:
                    claimed.append(WatchJob(str(job_key), notification, int(revision), "leased", int(attempts) + 1, lease_token, _parse_utc(lease_until)))
            db.commit()
        return tuple(claimed)

    def prepare_delivery(
        self,
        job: WatchJob,
        access: WatchDeliveryAccess,
        *,
        now: datetime | None = None,
    ) -> DeliveryAttempt | None:
        """Run the final policy/grant/quota check immediately before transport.

        This is intentionally not a sender.  An authorized adapter must call
        ``finish_delivery`` with the honest transport outcome; no code here can
        make a network request or infer that a message was received.
        """
        if type(job) is not WatchJob or job.state != "leased" or not job.lease_token:
            return None
        current = _utc(now or datetime.now(timezone.utc))
        current_text = _iso(current)
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT notification_json,subscription_revision,state,lease_until FROM pa_watch_jobs WHERE job_key=? AND lease_token=?",
                (job.job_key, job.lease_token),
            ).fetchone()
            if row is None or str(row[2]) != "leased" or (str(row[3]) and str(row[3]) <= current_text):
                db.rollback()
                return None
            try:
                notification = _notification_from_payload(json.loads(str(row[0])))
            except (TypeError, json.JSONDecodeError, ValueError):
                self._cancel_leased_in(db, job.job_key, job.lease_token, "invalid_notification", current)
                db.commit()
                return None
            subscription = self._load_subscription_in(db, notification.subscription_id)
            policy = _job_policy(subscription, notification, now=current)
            subject = db.execute(
                "SELECT current_version,lifecycle FROM pa_watch_subjects WHERE subscription_id=? AND subject_ref=?",
                (notification.subscription_id, notification.subject_ref),
            ).fetchone()
            if (
                subscription is None
                or int(row[1]) != subscription.consent_revision
                or policy != "active"
                or subject is None
                or str(subject[0]) != notification.change_version
                or str(subject[1]) != "active"
            ):
                self._cancel_leased_in(db, job.job_key, job.lease_token, policy if policy != "active" else "subscription_or_subject_changed", current)
                db.commit()
                return None
            if (
                access.owner_ref != subscription.owner_ref
                or access.destination_ref != subscription.destination_ref
                or access.data_class != notification.data_class
            ):
                self._cancel_leased_in(db, job.job_key, job.lease_token, "delivery_scope_mismatch", current)
                db.commit()
                return None
            db.commit()
        decision = access.authorization
        if not is_authorized_operation(
            decision,
            capability=WATCH_DELIVERY_CAPABILITY,
            operation="deliver",
            provider_ref=WATCH_DELIVERY_PROVIDER,
            data_class=notification.data_class,
            owner_ref=notification.owner_ref,
            connection_ref=decision.connection_ref,
            resource_ref=access.destination_ref,
            purpose=WATCH_DELIVERY_PURPOSE,
        ):
            with sqlite3.connect(self.path) as db:
                db.execute("BEGIN IMMEDIATE")
                self._cancel_leased_in(db, job.job_key, job.lease_token, "delivery_grant_unavailable", current)
                db.commit()
            return None
        refreshed = WatchJob(job.job_key, notification, job.subscription_revision, "leased", job.attempts, job.lease_token, job.lease_until)
        return DeliveryAttempt(refreshed, render_watch_notification(notification), decision)

    def finish_delivery(
        self,
        attempt: DeliveryAttempt,
        *,
        outcome: Literal["sent", "unknown", "known_not_delivered"],
        transport_receipt_ref: str | None = None,
        detail: str = "",
        now: datetime | None = None,
        max_attempts: int = 3,
    ) -> bool:
        """Separate a truthful transport result from the durable job receipt."""
        if type(attempt) is not DeliveryAttempt or outcome not in {"sent", "unknown", "known_not_delivered"}:
            raise ValueError("delivery outcome is invalid")
        if transport_receipt_ref is not None:
            _ref(transport_receipt_ref, field="transport_receipt_ref")
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts is invalid")
        current = _utc(now or datetime.now(timezone.utc))
        job = attempt.job
        if not job.lease_token:
            return False
        recorded_outcome: Literal["accepted", "unknown"] | None = None
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            result = self._finish_delivery_in(
                db, attempt, outcome=outcome,
                transport_receipt_ref=transport_receipt_ref, detail=detail,
                current=current, max_attempts=max_attempts,
            )
            if result is None:
                db.rollback()
                return False
            db.commit()
        if outcome == "sent":
            recorded_outcome = "accepted"
        elif outcome == "unknown":
            recorded_outcome = "unknown"
        if recorded_outcome is not None:
            assert attempt.authorization.reservation is not None
            attempt.authorization.reservation.record_delivery_outcome(recorded_outcome)
        return True

    def deliver_claimed_job(
        self,
        job: WatchJob,
        access: WatchDeliveryAccess,
        *,
        sender: Callable[[str], str | None],
        now: datetime | None = None,
    ) -> Literal["sent", "deferred", "unknown", "blocked"]:
        """Own the last local guard and truthful outcome around one transport.

        ``sender`` is injected: this module has no Telegram client, token,
        account or default delivery path. A future authorized adapter calls
        this method rather than using ``prepare_delivery`` as a detached,
        stale preflight. The lifecycle is reloaded immediately before the
        callback and every callback outcome reaches durable state.
        """
        if not callable(sender):
            raise ValueError("sender is invalid")
        current = _utc(now or datetime.now(timezone.utc))
        attempt = self.prepare_delivery(job, access, now=current)
        if attempt is None:
            return "blocked"
        # Keep the SQLite write transaction through the injected callback. It
        # linearizes the exact final policy decision, quota reservation and
        # one transport attempt: a concurrent pause/revision waits until this
        # callback has an honest outcome, and a second holder of the same
        # lease sees the terminal state instead of double-sending. A process
        # crash during the callback rolls the transaction back; the expired
        # lease is then deliberately unknown rather than eligible for retry.
        result: Literal["sent", "deferred", "unknown", "blocked"]
        recorded_outcome: Literal["accepted", "unknown"] | None = None
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT notification_json,subscription_revision,state,lease_until FROM pa_watch_jobs WHERE job_key=? AND lease_token=?",
                (attempt.job.job_key, attempt.job.lease_token),
            ).fetchone()
            if row is None or str(row[2]) != "leased" or (str(row[3]) and str(row[3]) <= _iso(current)):
                db.rollback()
                return "blocked"
            try:
                notification = _notification_from_payload(json.loads(str(row[0])))
            except (TypeError, json.JSONDecodeError, ValueError):
                self._cancel_leased_in(db, attempt.job.job_key, attempt.job.lease_token or "", "invalid_notification", current)
                db.commit()
                return "blocked"
            subscription = self._load_subscription_in(db, notification.subscription_id)
            subject = db.execute(
                "SELECT current_version,lifecycle FROM pa_watch_subjects WHERE subscription_id=? AND subject_ref=?",
                (notification.subscription_id, notification.subject_ref),
            ).fetchone()
            if (
                subscription is None
                or int(row[1]) != subscription.consent_revision
                or _job_policy(subscription, notification, now=current) != "active"
                or subject is None
                or str(subject[0]) != notification.change_version
                or str(subject[1]) != "active"
                or access.owner_ref != subscription.owner_ref
                or access.destination_ref != subscription.destination_ref
                or access.data_class != notification.data_class
            ):
                self._cancel_leased_in(db, attempt.job.job_key, attempt.job.lease_token or "", "terminal_policy_or_scope_changed", current)
                db.commit()
                return "blocked"
            decision = attempt.authorization
            try:
                # This consumes the current PA-02 reservation while the local
                # policy state is locked, immediately before ``sender``.
                require_authorized_operation(
                    decision,
                    capability=WATCH_DELIVERY_CAPABILITY,
                    operation="deliver",
                    provider_ref=WATCH_DELIVERY_PROVIDER,
                    data_class=notification.data_class,
                    owner_ref=notification.owner_ref,
                    connection_ref=decision.connection_ref,
                    resource_ref=access.destination_ref,
                    purpose=WATCH_DELIVERY_PURPOSE,
                )
            except CapabilityDenied:
                self._cancel_leased_in(db, attempt.job.job_key, attempt.job.lease_token or "", "delivery_grant_unavailable", current)
                db.commit()
                return "blocked"
            if not self._reserve_quota_in(db, attempt.job.job_key, subscription, current):
                self._cancel_leased_in(db, attempt.job.job_key, attempt.job.lease_token or "", "daily_cap_reached", current)
                db.commit()
                return "blocked"
            try:
                receipt_ref = sender(attempt.text)
            except KnownWatchDeliveryFailure as exc:
                final_state = self._finish_delivery_in(
                    db, attempt, outcome="known_not_delivered", detail=type(exc).__name__,
                    current=current, max_attempts=3,
                )
                assert final_state is not None
                result = "deferred" if final_state == "deferred" else "unknown"
            except Exception as exc:
                final_state = self._finish_delivery_in(
                    db, attempt, outcome="unknown", detail=type(exc).__name__,
                    current=current, max_attempts=3,
                )
                assert final_state == "unknown"
                recorded_outcome, result = "unknown", "unknown"
            else:
                if receipt_ref is not None and (not isinstance(receipt_ref, str) or not _REF.fullmatch(receipt_ref)):
                    final_state = self._finish_delivery_in(
                        db, attempt, outcome="unknown", detail="invalid_transport_receipt",
                        current=current, max_attempts=3,
                    )
                    assert final_state == "unknown"
                    recorded_outcome, result = "unknown", "unknown"
                else:
                    final_state = self._finish_delivery_in(
                        db, attempt, outcome="sent", transport_receipt_ref=receipt_ref,
                        current=current, max_attempts=3,
                    )
                    assert final_state == "sent"
                    recorded_outcome, result = "accepted", "sent"
            db.commit()
        if recorded_outcome is not None:
            assert attempt.authorization.reservation is not None
            attempt.authorization.reservation.record_delivery_outcome(recorded_outcome)
        return result

    def run_once(
        self,
        *,
        access_for_job: Callable[[WatchJob], WatchDeliveryAccess | None],
        sender: Callable[[str], str | None],
        now: datetime | None = None,
        limit: int = 8,
    ) -> WatchRunResult:
        """Run at most one bounded local batch; it never installs a timer."""
        if not callable(access_for_job) or not callable(sender):
            raise ValueError("runner callbacks are invalid")
        current = _utc(now or datetime.now(timezone.utc))
        claimed = self.claim_due_jobs(now=current, limit=limit)
        outcomes = {"sent": 0, "deferred": 0, "unknown": 0, "blocked": 0}
        for job in claimed:
            try:
                access = access_for_job(job)
            except Exception:
                access = None
            if access is None:
                # No reservation means no transport attempt occurred. Do not
                # convert a known no-send into an ambiguous lease expiry.
                self._cancel_known_not_sent(job, reason="delivery_access_unavailable", now=current)
                outcomes["blocked"] += 1
                continue
            try:
                outcomes[self.deliver_claimed_job(job, access, sender=sender, now=current)] += 1
            except (ValueError, TypeError):
                outcomes["blocked"] += 1
        return WatchRunResult(len(claimed), outcomes["sent"], outcomes["deferred"], outcomes["unknown"], outcomes["blocked"])

    def reconciliation_requirement(
        self,
        job_key: str,
        *,
        authenticated_chat_id: str | None,
        authenticated_actor_id: str | None,
        authenticated_owner_chat_id: str | None,
    ) -> WatchReconciliationRequirement | None:
        """Return the sealed past operation only to its exact private owner."""
        _ref(job_key, field="job_key")
        owner_ref = watch_owner_ref_from_authenticated_private_tuple(
            authenticated_chat_id, authenticated_actor_id, authenticated_owner_chat_id,
        )
        if owner_ref is None:
            return None
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT a.owner_ref,a.destination_ref,a.operation_ref,a.unknown_at "
                "FROM pa_watch_unknown_attempts a JOIN pa_watch_jobs j ON j.job_key=a.job_key "
                "WHERE a.job_key=? AND j.state='unknown'",
                (job_key,),
            ).fetchone()
        if row is None or str(row[0]) != owner_ref:
            return None
        return WatchReconciliationRequirement(
            job_key, str(row[0]), str(row[1]), str(row[2]), _parse_utc(row[3]),
        )

    def reconcile_unknown(
        self,
        evidence: WatchReconciliationEvidence,
        *,
        access: WatchDeliveryAccess,
        authenticated_chat_id: str | None,
        authenticated_actor_id: str | None,
        authenticated_owner_chat_id: str | None,
    ) -> bool:
        """Reconcile a known PA-02 unknown, never a caller assertion alone."""
        if type(evidence) is not WatchReconciliationEvidence:
            raise ValueError("reconciliation evidence is invalid")
        evidence.__post_init__()
        owner_ref = watch_owner_ref_from_authenticated_private_tuple(
            authenticated_chat_id, authenticated_actor_id, authenticated_owner_chat_id,
        )
        if owner_ref is None or owner_ref != evidence.owner_ref:
            return False
        decision = access.authorization
        if (
            access.owner_ref != evidence.owner_ref
            or decision.owner_ref != evidence.owner_ref
            or decision.operation_ref != evidence.operation_ref
            or decision.reservation is None
            or decision.reservation.operation_ref != evidence.operation_ref
        ):
            return False
        job_key, outcome, current = evidence.job_key, evidence.outcome, _utc(evidence.observed_at)
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT a.owner_ref,a.destination_ref,a.operation_ref,a.grant_ref,a.grant_revision,a.unknown_at,j.state "
                "FROM pa_watch_unknown_attempts a JOIN pa_watch_jobs j ON j.job_key=a.job_key WHERE a.job_key=?",
                (job_key,),
            ).fetchone()
            if (
                row is None
                or str(row[6]) != "unknown"
                or str(row[0]) != evidence.owner_ref
                or str(row[1]) != access.destination_ref
                or str(row[2]) != evidence.operation_ref
                or str(row[3]) != decision.grant_ref
                or int(row[4]) != decision.grant_revision
                or current < _parse_utc(row[5])
            ):
                db.rollback()
                return False
            # The sealed original PA-02 reservation must itself still be in
            # the unknown state. This is the local linkage a future authorized
            # provider adapter supplies alongside its provider evidence.
            if not decision.reservation.registry.reconcile_unknown_operation(
                evidence.operation_ref, delivery_outcome=outcome,
            ):
                db.rollback()
                return False
            if outcome == "delivered":
                db.execute(
                    "UPDATE pa_watch_jobs SET state='sent',last_reason='reconciled_delivered',updated_at=? WHERE job_key=? AND state='unknown'",
                    (_iso(current), job_key),
                )
                db.execute(
                    "INSERT OR IGNORE INTO pa_watch_receipts(job_key,outcome,delivered_at,transport_receipt_ref,detail) VALUES(?,?,?,?,?)",
                    (job_key, "reconciled_delivered", _iso(current), evidence.evidence_ref, "reconciliation established delivery"),
                )
                self._release_quota_in(db, job_key)
            else:
                db.execute(
                    "UPDATE pa_watch_jobs SET state='queued',retry_after='',last_reason='reconciled_not_delivered',updated_at=? WHERE job_key=? AND state='unknown'",
                    (_iso(current), job_key),
                )
                self._release_quota_in(db, job_key)
            db.execute("DELETE FROM pa_watch_unknown_attempts WHERE job_key=?", (job_key,))
            db.commit()
        return True

    def complete_subject(
        self,
        subscription_id: str,
        subject_ref: str,
        *,
        expected_subscription_revision: int,
        state: Literal["completed", "cancelled", "not_relevant"] = "completed",
        authenticated_chat_id: str | None,
        authenticated_actor_id: str | None,
        authenticated_owner_chat_id: str | None,
        now: datetime | None = None,
    ) -> bool:
        """Stop waiting work when an event is done, cancelled or irrelevant."""
        _ref(subscription_id, field="subscription_id", pattern=_SUBSCRIPTION)
        _ref(subject_ref, field="subject_ref")
        if state not in {"completed", "cancelled", "not_relevant"}:
            raise ValueError("subject state is invalid")
        current = _utc(now or datetime.now(timezone.utc))
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT owner_ref,consent_revision FROM pa_watch_subscriptions WHERE subscription_id=?", (subscription_id,)
            ).fetchone()
            if (
                row is None
                or watch_owner_ref_from_authenticated_private_tuple(
                    authenticated_chat_id, authenticated_actor_id, authenticated_owner_chat_id,
                ) != str(row[0])
                or int(row[1]) != expected_subscription_revision
            ):
                db.rollback()
                return False
            subject = db.execute(
                "SELECT current_version FROM pa_watch_subjects WHERE subscription_id=? AND subject_ref=?",
                (subscription_id, subject_ref),
            ).fetchone()
            if subject is None:
                db.rollback()
                return False
            db.execute(
                "UPDATE pa_watch_subjects SET lifecycle=?,updated_at=? WHERE subscription_id=? AND subject_ref=?",
                (state, _iso(current), subscription_id, subject_ref),
            )
            db.execute(
                "UPDATE pa_watch_jobs SET state='cancelled',last_reason='subject_'+?,updated_at=? WHERE subscription_id=? AND subject_ref=? AND state IN ('queued','deferred')",
                (state, _iso(current), subscription_id, subject_ref),
            )
            db.commit()
        return True

    def record_feedback(
        self,
        job_key: str,
        *,
        action: str,
        authenticated_chat_id: str | None,
        authenticated_actor_id: str | None,
        authenticated_owner_chat_id: str | None,
        now: datetime | None = None,
    ) -> bool:
        """Record explicit post-delivery feedback without inventing a preference."""
        _ref(job_key, field="job_key")
        if action not in _FEEDBACK_ACTIONS:
            raise ValueError("feedback action is invalid")
        current = _utc(now or datetime.now(timezone.utc))
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT j.subscription_id,j.subject_ref,j.owner_ref FROM pa_watch_jobs j JOIN pa_watch_receipts r ON r.job_key=j.job_key WHERE j.job_key=?",
                (job_key,),
            ).fetchone()
            if (
                row is None
                or watch_owner_ref_from_authenticated_private_tuple(
                    authenticated_chat_id, authenticated_actor_id, authenticated_owner_chat_id,
                ) != str(row[2])
            ):
                db.rollback()
                return False
            db.execute(
                "INSERT OR IGNORE INTO pa_watch_feedback(job_key,action,recorded_at) VALUES(?,?,?)",
                (job_key, action, _iso(current)),
            )
            if action in {"pause", "unsubscribe"}:
                subscription = self._load_subscription_in(db, str(row[0]))
                if subscription is None:
                    db.rollback()
                    return False
                lifecycle = "paused" if action == "pause" else "cancelled"
                revised = replace(
                    subscription,
                    consent_revision=subscription.consent_revision + 1,
                    lifecycle=lifecycle,
                )
                db.execute(
                    "UPDATE pa_watch_subscriptions SET consent_revision=?,lifecycle=?,document_json=?,updated_at=? WHERE subscription_id=? AND consent_revision=?",
                    (
                        revised.consent_revision, revised.lifecycle, json.dumps(_subscription_payload(revised), sort_keys=True),
                        _iso(current), revised.subscription_id, subscription.consent_revision,
                    ),
                )
                db.execute(
                    "UPDATE pa_watch_jobs SET state='cancelled',last_reason='feedback_'+?,updated_at=? WHERE subscription_id=? AND state IN ('queued','deferred')",
                    (action, _iso(current), str(row[0])),
                )
            elif action in {"done", "not_relevant"}:
                db.execute(
                    "UPDATE pa_watch_subjects SET lifecycle=?,updated_at=? WHERE subscription_id=? AND subject_ref=?",
                    ("completed" if action == "done" else "not_relevant", _iso(current), str(row[0]), str(row[1])),
                )
                db.execute(
                    "UPDATE pa_watch_jobs SET state='cancelled',last_reason='feedback_'+?,updated_at=? WHERE subscription_id=? AND subject_ref=? AND state IN ('queued','deferred')",
                    (action, _iso(current), str(row[0]), str(row[1])),
                )
            # "less" is intentionally audit-only here. It cannot mutate
            # source selection or a durable preference without PA-14 policy.
            db.commit()
        return True

    def job_state(self, job_key: str) -> str:
        _ref(job_key, field="job_key")
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT state FROM pa_watch_jobs WHERE job_key=?", (job_key,)).fetchone()
        return str(row[0]) if row else ""

    def receipt(self, job_key: str) -> Mapping[str, str] | None:
        _ref(job_key, field="job_key")
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT outcome,delivered_at,transport_receipt_ref,detail FROM pa_watch_receipts WHERE job_key=?", (job_key,)
            ).fetchone()
        if row is None:
            return None
        return {"outcome": str(row[0]), "delivered_at": str(row[1]), "transport_receipt_ref": str(row[2] or ""), "detail": str(row[3])}

    def _finish_delivery_in(
        self,
        db: sqlite3.Connection,
        attempt: DeliveryAttempt,
        *,
        outcome: Literal["sent", "unknown", "known_not_delivered"],
        transport_receipt_ref: str | None = None,
        detail: str = "",
        current: datetime,
        max_attempts: int,
    ) -> Literal["sent", "unknown", "deferred"] | None:
        """Persist one outcome inside the caller's already-exclusive transaction."""
        job = attempt.job
        if not job.lease_token:
            return None
        row = db.execute(
            "SELECT state,attempts FROM pa_watch_jobs WHERE job_key=? AND lease_token=?",
            (job.job_key, job.lease_token),
        ).fetchone()
        if row is None or str(row[0]) != "leased":
            return None
        if outcome == "sent":
            db.execute(
                "UPDATE pa_watch_jobs SET state='sent',lease_token='',lease_until='',last_reason='',updated_at=? WHERE job_key=? AND lease_token=?",
                (_iso(current), job.job_key, job.lease_token),
            )
            db.execute(
                "INSERT OR IGNORE INTO pa_watch_receipts(job_key,outcome,delivered_at,transport_receipt_ref,detail) VALUES(?,?,?,?,?)",
                (job.job_key, "sent", _iso(current), transport_receipt_ref, _bounded_text(detail or "sent", field="detail", maximum=500)),
            )
            db.execute("DELETE FROM pa_watch_unknown_attempts WHERE job_key=?", (job.job_key,))
            self._release_quota_in(db, job.job_key)
            return "sent"
        if outcome == "unknown":
            decision = attempt.authorization
            if (
                decision.grant_ref is None
                or decision.grant_revision is None
                or decision.operation_ref is None
                or decision.reservation is None
                or decision.reservation.operation_ref != decision.operation_ref
            ):
                return None
            db.execute(
                "UPDATE pa_watch_jobs SET state='unknown',lease_token='',lease_until='',last_reason='transport_outcome_unknown',updated_at=? WHERE job_key=? AND lease_token=?",
                (_iso(current), job.job_key, job.lease_token),
            )
            db.execute(
                "INSERT INTO pa_watch_unknown_attempts(job_key,owner_ref,destination_ref,operation_ref,grant_ref,grant_revision,unknown_at) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(job_key) DO UPDATE SET owner_ref=excluded.owner_ref,destination_ref=excluded.destination_ref,operation_ref=excluded.operation_ref,grant_ref=excluded.grant_ref,grant_revision=excluded.grant_revision,unknown_at=excluded.unknown_at",
                (
                    job.job_key, decision.owner_ref, decision.resource_ref,
                    decision.operation_ref, decision.grant_ref, decision.grant_revision, _iso(current),
                ),
            )
            return "unknown"
        attempts = int(row[1])
        if attempts >= max_attempts:
            state, retry_after, reason = "unknown", "", "known_failure_retry_budget_exhausted"
        else:
            delay = min(300, 30 * (2 ** max(0, attempts - 1)))
            state, retry_after, reason = "deferred", _iso(current + timedelta(seconds=delay)), "known_not_delivered"
        db.execute(
            "UPDATE pa_watch_jobs SET state=?,lease_token='',lease_until='',retry_after=?,last_reason=?,updated_at=? WHERE job_key=? AND lease_token=?",
            (state, retry_after, reason, _iso(current), job.job_key, job.lease_token),
        )
        self._release_quota_in(db, job.job_key)
        return state

    def _cancel_known_not_sent(self, job: WatchJob, *, reason: str, now: datetime) -> None:
        if not job.lease_token:
            return
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            self._cancel_leased_in(db, job.job_key, job.lease_token, reason, now)
            db.commit()

    def _load_subscription_in(self, db: sqlite3.Connection, subscription_id: str) -> WatchSubscription | None:
        row = db.execute(
            "SELECT document_json FROM pa_watch_subscriptions WHERE subscription_id=?", (subscription_id,)
        ).fetchone()
        if row is None:
            return None
        try:
            return _subscription_from_payload(json.loads(str(row[0])))
        except (TypeError, json.JSONDecodeError, ValueError):
            return None

    def _reserve_quota_in(self, db: sqlite3.Connection, job_key: str, subscription: WatchSubscription, current: datetime) -> bool:
        existing = db.execute("SELECT 1 FROM pa_watch_quota_reservations WHERE job_key=?", (job_key,)).fetchone()
        if existing is not None:
            return True
        day = current.astimezone(ZoneInfo(subscription.timezone_name)).date().isoformat()
        receipts = db.execute(
            "SELECT r.delivered_at FROM pa_watch_receipts r JOIN pa_watch_jobs j ON j.job_key=r.job_key WHERE j.subscription_id=?",
            (subscription.subscription_id,),
        ).fetchall()
        used = 0
        for (delivered_at,) in receipts:
            try:
                if _parse_utc(delivered_at).astimezone(ZoneInfo(subscription.timezone_name)).date().isoformat() == day:
                    used += 1
            except ValueError:
                # Corrupt receipts remain conservatively counted, rather than
                # becoming a quota bypass after a restart.
                used += 1
        reserved = int(db.execute(
            "SELECT COUNT(*) FROM pa_watch_quota_reservations WHERE subscription_id=? AND local_day=?",
            (subscription.subscription_id, day),
        ).fetchone()[0])
        if used + reserved >= subscription.daily_cap:
            return False
        db.execute(
            "INSERT INTO pa_watch_quota_reservations(job_key,subscription_id,local_day,created_at) VALUES(?,?,?,?)",
            (job_key, subscription.subscription_id, day, _iso(current)),
        )
        return True

    @staticmethod
    def _release_quota_in(db: sqlite3.Connection, job_key: str) -> None:
        db.execute("DELETE FROM pa_watch_quota_reservations WHERE job_key=?", (job_key,))

    @staticmethod
    def _cancel_leased_in(db: sqlite3.Connection, job_key: str, lease_token: str, reason: str, current: datetime) -> None:
        db.execute(
            "UPDATE pa_watch_jobs SET state='cancelled',lease_token='',lease_until='',last_reason=?,updated_at=? WHERE job_key=? AND lease_token=? AND state='leased'",
            (reason[:500], _iso(current), job_key, lease_token),
        )
        db.execute("DELETE FROM pa_watch_quota_reservations WHERE job_key=?", (job_key,))

    @staticmethod
    def _validate_subscription(subscription: WatchSubscription) -> None:
        if type(subscription) is not WatchSubscription:
            raise ValueError("subscription is invalid")
        subscription.__post_init__()

    @staticmethod
    def _validate_notification(notification: WatchNotification) -> None:
        if type(notification) is not WatchNotification:
            raise ValueError("notification is invalid")
        notification.__post_init__()


def _subscription_effect(subscription: WatchSubscription, *, now: datetime) -> str:
    if subscription.lifecycle != "active":
        return subscription.lifecycle
    if _utc(subscription.expires_at) <= now:
        return "expired"
    if subscription.paused_until is not None and _utc(subscription.paused_until) > now:
        return "paused"
    return "active"


def _job_policy(subscription: WatchSubscription | None, notification: WatchNotification, *, now: datetime) -> str:
    if subscription is None:
        return "subscription_unavailable"
    effect = _subscription_effect(subscription, now=now)
    if effect != "active":
        return effect
    try:
        local = now.astimezone(ZoneInfo(subscription.timezone_name))
    except Exception:
        return "invalid_timezone"
    if _in_quiet_hours(subscription, local=local) and not (notification.urgent and subscription.allow_urgent_during_quiet_hours):
        return "quiet_hours"
    if subscription.frequency != "immediate" and not _scheduled_digest_due(subscription, local=local):
        return "schedule_wait"
    return "active"


def _is_digest_stage(stage: str) -> bool:
    return _valid_digest_stage(stage)


def _valid_digest_stage(stage: str) -> bool:
    if not _DIGEST_STAGE.fullmatch(stage):
        return False
    try:
        datetime.fromisoformat(stage.removeprefix("digest:"))
    except ValueError:
        return False
    return True


def _stage_matches_trigger(stage: str, trigger: str) -> bool:
    return bool(
        (trigger == "meaningful_change" and stage == "change")
        or (trigger == "deadline_reminder" and stage in _DEADLINE_STAGES)
        or (trigger == "digest" and _is_digest_stage(stage))
    )


def _in_quiet_hours(subscription: WatchSubscription, *, local: datetime) -> bool:
    if subscription.quiet_start is None or subscription.quiet_end is None or subscription.quiet_start == subscription.quiet_end:
        return False
    time = local.strftime("%H:%M")
    if subscription.quiet_start < subscription.quiet_end:
        return subscription.quiet_start <= time < subscription.quiet_end
    return time >= subscription.quiet_start or time < subscription.quiet_end


def _scheduled_digest_due(subscription: WatchSubscription, *, local: datetime) -> bool:
    # A bounded post-schedule window supports a one-shot worker without turning
    # late daily runs into next-day catch-up. Fall-back duplicate wall minutes
    # are harmless because the durable stage/version key has one receipt.
    if subscription.delivery_time is None:
        return False
    if subscription.frequency == "weekly" and local.weekday() != subscription.delivery_weekday:
        return False
    hour, minute = (int(part) for part in subscription.delivery_time.split(":"))
    delta = (local.hour * 60 + local.minute) - (hour * 60 + minute)
    if 0 <= delta <= 45:
        return True
    scheduled = datetime(local.year, local.month, local.day, hour, minute, tzinfo=local.tzinfo)
    return bool(0 < delta <= 120 and local.hour >= 3 and local.utcoffset() != scheduled.utcoffset())


def render_watch_notification(notification: WatchNotification) -> str:
    """Render the stored explanation without new generation or source reads."""
    notification.__post_init__()
    lines = [
        notification.title,
        "Что изменилось: " + notification.change_summary,
        "Почему это важно: " + notification.relevance_reason,
        "Источник: " + (notification.source_url or notification.source_ref),
    ]
    rendered = "\n".join(lines)
    return rendered[:4096]


def _subscription_payload(subscription: WatchSubscription) -> dict[str, object]:
    return {
        "schema_version": subscription.schema_version,
        "subscription_id": subscription.subscription_id,
        "owner_ref": subscription.owner_ref,
        "consent_revision": subscription.consent_revision,
        "source_refs": list(subscription.source_refs),
        "destination_ref": subscription.destination_ref,
        "trigger": subscription.trigger,
        "timezone_name": subscription.timezone_name,
        "expires_at": _iso(subscription.expires_at),
        "daily_cap": subscription.daily_cap,
        "frequency": subscription.frequency,
        "delivery_time": subscription.delivery_time,
        "delivery_weekday": subscription.delivery_weekday,
        "quiet_start": subscription.quiet_start,
        "quiet_end": subscription.quiet_end,
        "lifecycle": subscription.lifecycle,
        "paused_until": _iso(subscription.paused_until) if subscription.paused_until else None,
        "allow_urgent_during_quiet_hours": subscription.allow_urgent_during_quiet_hours,
    }


def _digest_payload(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _subscription_from_payload(payload: object) -> WatchSubscription:
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema_version", "subscription_id", "owner_ref", "consent_revision", "source_refs", "destination_ref",
        "trigger", "timezone_name", "expires_at", "daily_cap", "frequency", "delivery_time", "delivery_weekday", "quiet_start", "quiet_end",
        "lifecycle", "paused_until", "allow_urgent_during_quiet_hours",
    } or not isinstance(payload.get("source_refs"), list):
        raise ValueError("stored subscription is invalid")
    return WatchSubscription(
        subscription_id=payload["subscription_id"], owner_ref=payload["owner_ref"], consent_revision=payload["consent_revision"],
        source_refs=tuple(payload["source_refs"]), destination_ref=payload["destination_ref"], trigger=payload["trigger"],
        timezone_name=payload["timezone_name"], expires_at=_parse_utc(payload["expires_at"]), daily_cap=payload["daily_cap"],
        frequency=payload["frequency"], delivery_time=payload["delivery_time"], delivery_weekday=payload["delivery_weekday"], quiet_start=payload["quiet_start"], quiet_end=payload["quiet_end"],
        lifecycle=payload["lifecycle"], paused_until=None if payload["paused_until"] is None else _parse_utc(payload["paused_until"]),
        allow_urgent_during_quiet_hours=payload["allow_urgent_during_quiet_hours"], schema_version=payload["schema_version"],
    )


def _notification_payload(notification: WatchNotification) -> dict[str, object]:
    return {
        "subscription_id": notification.subscription_id, "owner_ref": notification.owner_ref, "subject_ref": notification.subject_ref,
        "change_version": notification.change_version, "delivery_stage": notification.delivery_stage, "title": notification.title,
        "change_summary": notification.change_summary, "relevance_reason": notification.relevance_reason, "source_ref": notification.source_ref,
        "due_at": _iso(notification.due_at), "data_class": notification.data_class, "source_url": notification.source_url,
        "urgent": notification.urgent,
    }


def _notification_from_payload(payload: object) -> WatchNotification:
    fields = {
        "subscription_id", "owner_ref", "subject_ref", "change_version", "delivery_stage", "title", "change_summary",
        "relevance_reason", "source_ref", "due_at", "data_class", "source_url", "urgent",
    }
    if not isinstance(payload, Mapping) or set(payload) != fields:
        raise ValueError("stored notification is invalid")
    return WatchNotification(
        subscription_id=payload["subscription_id"], owner_ref=payload["owner_ref"], subject_ref=payload["subject_ref"],
        change_version=payload["change_version"], delivery_stage=payload["delivery_stage"], title=payload["title"],
        change_summary=payload["change_summary"], relevance_reason=payload["relevance_reason"], source_ref=payload["source_ref"],
        due_at=_parse_utc(payload["due_at"]), data_class=payload["data_class"], source_url=payload["source_url"], urgent=payload["urgent"],
    )
