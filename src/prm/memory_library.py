"""PA-14 local, inspectable memory and knowledge library.

Explicit preferences, saved items and reused reports are stored in an
explicit-path SQLite sidecar and are fully inspectable, correctable, forgettable
and exportable. Feedback never silently mutates a preference: it becomes a
proposal that the owner must confirm. Engagement states (indexed, opened, read,
applied) are tracked separately and never conflated. Forgetting returns an
explicit propagation plan for derived indexes/caches/jobs instead of mutating
unrelated archive data.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Literal, Mapping

from prm.capabilities import (
    AuthorizationDecision,
    CapabilityDenied,
    require_authorized_operation,
)


MEMORY_SCHEMA_VERSION = "assistant.memory_library.v1"
MEMORY_CAPABILITY = "assistant.memory"
MEMORY_PROVIDER = "provider_local"
MEMORY_PURPOSE = "memory.manage"
MEMORY_DATA_CLASS = "private_connector_metadata"

_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,511}$")
_ITEM = re.compile(r"^memory_[a-z0-9_-]{3,120}$")
_PREF = re.compile(r"^pref_[a-z0-9_-]{3,120}$")

PREFERENCE_KINDS = ("interest", "project", "depth", "length", "source", "topic")
PREFERENCE_SOURCES = ("explicit", "feedback")
ENGAGEMENTS = ("none", "indexed", "opened", "read", "applied")
ITEM_STATES = ("active", "forgotten")
ITEM_KINDS = ("note", "report", "material", "project", "preference_link")
DERIVED_TARGETS = ("index", "cache", "jobs")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_utc(value: object) -> datetime:
    return _utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


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


@dataclass(frozen=True, slots=True)
class MemoryPreference:
    preference_ref: str
    owner_ref: str
    kind: Literal["interest", "project", "depth", "length", "source", "topic"]
    value: str
    source: Literal["explicit", "feedback"]
    revision: int
    active: bool
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not _PREF.fullmatch(self.preference_ref):
            raise ValueError("invalid preference_ref")
        _ref(self.owner_ref, field="owner_ref")
        if self.kind not in PREFERENCE_KINDS:
            raise ValueError("invalid preference kind")
        _text(self.value, field="value", maximum=300)
        if self.source not in PREFERENCE_SOURCES:
            raise ValueError("invalid preference source")
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("preference revision must be positive")

    def to_payload(self) -> dict[str, object]:
        return {
            "preference_ref": self.preference_ref,
            "owner_ref": self.owner_ref,
            "kind": self.kind,
            "value": self.value,
            "source": self.source,
            "revision": self.revision,
            "active": self.active,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }


@dataclass(frozen=True, slots=True)
class PreferenceChangeProposal:
    """Feedback is a proposal until the owner confirms it; then it is reversible."""

    proposal_ref: str
    owner_ref: str
    kind: str
    value: str
    source: Literal["explicit", "feedback"]
    evidence_refs: tuple[str, ...]
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        _ref(self.proposal_ref, field="proposal_ref")
        _ref(self.owner_ref, field="owner_ref")
        if self.kind not in PREFERENCE_KINDS:
            raise ValueError("invalid preference kind")
        _text(self.value, field="value", maximum=300)
        if self.source not in PREFERENCE_SOURCES:
            raise ValueError("invalid preference source")
        if not self.evidence_refs:
            raise ValueError("a preference change needs evidence")
        for value in self.evidence_refs:
            _ref(value, field="evidence_ref")
        if _utc(self.expires_at) <= _utc(self.created_at):
            raise ValueError("proposal must expire after creation")

    def state_at(self, now: datetime) -> Literal["active", "expired"]:
        return "active" if _utc(now) < _utc(self.expires_at) else "expired"


@dataclass(frozen=True, slots=True)
class MemoryItem:
    item_ref: str
    owner_ref: str
    kind: Literal["note", "report", "material", "project", "preference_link"]
    title: str
    content_ref: str
    source_ref: str
    state: Literal["active", "forgotten"]
    engagement: Literal["none", "indexed", "opened", "read", "applied"]
    version: int
    content_digest: str
    saved_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not _ITEM.fullmatch(self.item_ref):
            raise ValueError("invalid item_ref")
        _ref(self.owner_ref, field="owner_ref")
        if self.kind not in ITEM_KINDS:
            raise ValueError("invalid item kind")
        _text(self.title, field="title", maximum=240)
        _ref(self.content_ref, field="content_ref")
        _ref(self.source_ref, field="source_ref")
        if self.state not in ITEM_STATES:
            raise ValueError("invalid item state")
        if self.engagement not in ENGAGEMENTS:
            raise ValueError("invalid engagement")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("item version must be positive")
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_digest):
            raise ValueError("invalid content digest")

    def to_payload(self) -> dict[str, object]:
        return {
            "item_ref": self.item_ref,
            "owner_ref": self.owner_ref,
            "kind": self.kind,
            "title": self.title,
            "content_ref": self.content_ref,
            "source_ref": self.source_ref,
            "state": self.state,
            "engagement": self.engagement,
            "version": self.version,
            "content_digest": self.content_digest,
            "saved_at": _iso(self.saved_at),
            "updated_at": _iso(self.updated_at),
        }


@dataclass(frozen=True, slots=True)
class DerivedPropagationPlan:
    """Explicit derived-artifact cleanup for one item; unrelated data is untouched."""

    item_ref: str
    targets: tuple[tuple[str, str], ...]  # (target, reason)

    def __post_init__(self) -> None:
        if not _ITEM.fullmatch(self.item_ref):
            raise ValueError("invalid item_ref")
        for target, _reason in self.targets:
            if target not in DERIVED_TARGETS:
                raise ValueError("unknown derived target")


def plan_forget(item: MemoryItem) -> DerivedPropagationPlan:
    targets = [
        ("index", "remove the item's derived index rows"),
        ("cache", "drop cached retrievals that cite the item"),
        ("jobs", "cancel or re-scope scheduled work that references the item"),
    ]
    return DerivedPropagationPlan(item_ref=item.item_ref, targets=tuple(targets))


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS pa_memory_items(
    owner_ref TEXT NOT NULL, item_ref TEXT NOT NULL, version INTEGER NOT NULL,
    payload TEXT NOT NULL, state TEXT NOT NULL, engagement TEXT NOT NULL,
    updated_at TEXT NOT NULL, PRIMARY KEY(owner_ref, item_ref, version));
CREATE TABLE IF NOT EXISTS pa_memory_preferences(
    owner_ref TEXT NOT NULL, preference_ref TEXT NOT NULL, revision INTEGER NOT NULL,
    payload TEXT NOT NULL, active INTEGER NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY(owner_ref, preference_ref, revision));
CREATE TABLE IF NOT EXISTS pa_memory_proposals(
    owner_ref TEXT NOT NULL, proposal_ref TEXT NOT NULL, payload TEXT NOT NULL,
    consumed INTEGER NOT NULL, PRIMARY KEY(owner_ref, proposal_ref));
"""


class MemoryLibraryStore:
    """Explicit-path sidecar; no default database and no hidden learning."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path, isolation_level=None)) as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, isolation_level=None)

    # --- items -------------------------------------------------------------
    def save_item(self, item: MemoryItem) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pa_memory_items(owner_ref,item_ref,version,payload,state,engagement,updated_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (item.owner_ref, item.item_ref, item.version,
                 json.dumps(item.to_payload(), ensure_ascii=False, sort_keys=True),
                 item.state, item.engagement, _iso(item.updated_at)),
            )

    def _latest_item(self, owner_ref: str, item_ref: str) -> MemoryItem | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT payload FROM pa_memory_items WHERE owner_ref=? AND item_ref=? ORDER BY version DESC LIMIT 1",
                (owner_ref, item_ref),
            ).fetchone()
        if not row:
            return None
        return _item_from_payload(json.loads(row[0]))

    def get_item(self, owner_ref: str, item_ref: str) -> MemoryItem | None:
        _ref(owner_ref, field="owner_ref")
        _ref(item_ref, field="item_ref")
        return self._latest_item(owner_ref, item_ref)

    def list_items(self, owner_ref: str, *, include_forgotten: bool = False) -> tuple[MemoryItem, ...]:
        _ref(owner_ref, field="owner_ref")
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT payload, version FROM pa_memory_items WHERE owner_ref=? ORDER BY item_ref, version DESC",
                (owner_ref,),
            ).fetchall()
        latest: dict[str, MemoryItem] = {}
        for payload, _version in rows:
            item = _item_from_payload(json.loads(payload))
            latest.setdefault(item.item_ref, item)
        items = [item for item in latest.values() if include_forgotten or item.state == "active"]
        return tuple(sorted(items, key=lambda item: item.item_ref))

    def item_history(self, owner_ref: str, item_ref: str) -> tuple[MemoryItem, ...]:
        _ref(owner_ref, field="owner_ref")
        _ref(item_ref, field="item_ref")
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT payload FROM pa_memory_items WHERE owner_ref=? AND item_ref=? ORDER BY version",
                (owner_ref, item_ref),
            ).fetchall()
        return tuple(_item_from_payload(json.loads(row[0])) for row in rows)

    def set_engagement(self, owner_ref: str, item_ref: str, engagement: str, *, now: datetime) -> MemoryItem:
        if engagement not in ENGAGEMENTS:
            raise ValueError("invalid engagement")
        item = self.get_item(owner_ref, item_ref)
        if item is None:
            raise ValueError("unknown item")
        updated = replace(item, engagement=engagement, updated_at=_utc(now))
        self.save_item(updated)
        return updated

    def revise_item(self, owner_ref: str, item_ref: str, *, title: str, content_ref: str, now: datetime) -> MemoryItem:
        item = self.get_item(owner_ref, item_ref)
        if item is None:
            raise ValueError("unknown item")
        version = item.version + 1
        payload = {
            "owner_ref": owner_ref, "item_ref": item_ref, "kind": item.kind,
            "title": _text(title, field="title", maximum=240), "content_ref": _ref(content_ref, field="content_ref"),
            "version": version,
        }
        revised = replace(
            item,
            title=payload["title"],
            content_ref=payload["content_ref"],
            version=version,
            content_digest=_digest(payload),
            updated_at=_utc(now),
        )
        self.save_item(revised)
        return revised

    def forget_item(self, owner_ref: str, item_ref: str, *, now: datetime) -> DerivedPropagationPlan:
        item = self.get_item(owner_ref, item_ref)
        if item is None:
            raise ValueError("unknown item")
        self.save_item(replace(item, state="forgotten", updated_at=_utc(now)))
        return plan_forget(item)

    def export_items(self, owner_ref: str, *, include_forgotten: bool = False) -> tuple[dict[str, object], ...]:
        return tuple(item.to_payload() for item in self.list_items(owner_ref, include_forgotten=include_forgotten))

    # --- preferences -------------------------------------------------------
    def active_preferences(self, owner_ref: str) -> tuple[MemoryPreference, ...]:
        _ref(owner_ref, field="owner_ref")
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT payload, active FROM pa_memory_preferences WHERE owner_ref=? ORDER BY preference_ref, revision DESC",
                (owner_ref,),
            ).fetchall()
        latest: dict[str, MemoryPreference] = {}
        for payload, active in rows:
            pref = _preference_from_payload(json.loads(payload))
            latest.setdefault(pref.preference_ref, pref)
        return tuple(pref for pref in latest.values() if pref.active)

    def history_preferences(self, owner_ref: str) -> tuple[MemoryPreference, ...]:
        _ref(owner_ref, field="owner_ref")
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT payload FROM pa_memory_preferences WHERE owner_ref=? ORDER BY preference_ref, revision",
                (owner_ref,),
            ).fetchall()
        return tuple(_preference_from_payload(json.loads(row[0])) for row in rows)

    def propose_preference(
        self,
        owner_ref: str,
        *,
        kind: str,
        value: str,
        source: str,
        evidence_refs: tuple[str, ...],
        now: datetime,
        ttl_seconds: int = 600,
    ) -> PreferenceChangeProposal:
        if source == "feedback":
            # Feedback never mutates memory on its own; it needs confirmation.
            pass
        moment = _utc(now)
        nonce = hashlib.sha256(
            f"{owner_ref}\x1f{kind}\x1f{value}\x1f{source}\x1f{_iso(moment)}".encode("utf-8")
        ).hexdigest()[:24]
        proposal = PreferenceChangeProposal(
            proposal_ref=f"pref_prop_{nonce}",
            owner_ref=owner_ref,
            kind=kind,
            value=value,
            source=source,  # type: ignore[arg-type]
            evidence_refs=evidence_refs,
            created_at=moment,
            expires_at=moment + timedelta(seconds=max(30, ttl_seconds)),
        )
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pa_memory_proposals(owner_ref,proposal_ref,payload,consumed) VALUES(?,?,?,0)",
                (owner_ref, proposal.proposal_ref, json.dumps(_proposal_payload(proposal), ensure_ascii=False, sort_keys=True)),
            )
        return proposal

    def confirm_preference(
        self,
        proposal: PreferenceChangeProposal,
        *,
        owner_ref: str,
        now: datetime,
    ) -> MemoryPreference:
        if proposal.owner_ref != owner_ref:
            raise ValueError("preference identity mismatch")
        if proposal.state_at(now) != "active":
            raise ValueError("preference proposal has expired")
        conn = self._connect()
        try:
            # One atomic transaction: the conditional update is the one-use gate.
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT consumed FROM pa_memory_proposals WHERE owner_ref=? AND proposal_ref=?",
                (owner_ref, proposal.proposal_ref),
            ).fetchone()
            if row is None:
                raise ValueError("unknown preference proposal")
            cursor = conn.execute(
                "UPDATE pa_memory_proposals SET consumed=1 WHERE owner_ref=? AND proposal_ref=? AND consumed=0",
                (owner_ref, proposal.proposal_ref),
            )
            if cursor.rowcount != 1:
                raise ValueError("preference proposal was already applied")
            prior = conn.execute(
                "SELECT revision FROM pa_memory_preferences WHERE owner_ref=? AND preference_ref=? ORDER BY revision DESC LIMIT 1",
                (owner_ref, proposal.proposal_ref),
            ).fetchone()
            revision = (prior[0] + 1) if prior else 1
            moment = _utc(now)
            pref = MemoryPreference(
                preference_ref=proposal.proposal_ref,
                owner_ref=owner_ref,
                kind=proposal.kind,  # type: ignore[arg-type]
                value=proposal.value,
                source=proposal.source,
                revision=revision,
                active=True,
                created_at=moment,
                updated_at=moment,
            )
            conn.execute(
                "INSERT OR REPLACE INTO pa_memory_preferences(owner_ref,preference_ref,revision,payload,active,updated_at)"
                " VALUES(?,?,?,?,?,?)",
                (pref.owner_ref, pref.preference_ref, pref.revision,
                 json.dumps(pref.to_payload(), ensure_ascii=False, sort_keys=True), 1, _iso(pref.updated_at)),
            )
            conn.execute("COMMIT")
            return pref
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def deactivate_preference(self, owner_ref: str, preference_ref: str, *, now: datetime) -> MemoryPreference:
        current = next(
            (pref for pref in self.active_preferences(owner_ref) if pref.preference_ref == preference_ref), None
        )
        if current is None:
            raise ValueError("unknown or inactive preference")
        updated = replace(current, revision=current.revision + 1, active=False, updated_at=_utc(now))
        self._write_preference(updated)
        return updated

    def _write_preference(self, pref: MemoryPreference) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pa_memory_preferences(owner_ref,preference_ref,revision,payload,active,updated_at)"
                " VALUES(?,?,?,?,?,?)",
                (pref.owner_ref, pref.preference_ref, pref.revision,
                 json.dumps(pref.to_payload(), ensure_ascii=False, sort_keys=True),
                 1 if pref.active else 0, _iso(pref.updated_at)),
            )


def _item_from_payload(payload: Mapping[str, Any]) -> MemoryItem:
    return MemoryItem(
        item_ref=str(payload["item_ref"]),
        owner_ref=str(payload["owner_ref"]),
        kind=str(payload["kind"]),  # type: ignore[arg-type]
        title=str(payload["title"]),
        content_ref=str(payload["content_ref"]),
        source_ref=str(payload["source_ref"]),
        state=str(payload["state"]),  # type: ignore[arg-type]
        engagement=str(payload["engagement"]),  # type: ignore[arg-type]
        version=int(payload["version"]),
        content_digest=str(payload["content_digest"]),
        saved_at=_parse_utc(payload["saved_at"]),
        updated_at=_parse_utc(payload["updated_at"]),
    )


def _preference_from_payload(payload: Mapping[str, Any]) -> MemoryPreference:
    return MemoryPreference(
        preference_ref=str(payload["preference_ref"]),
        owner_ref=str(payload["owner_ref"]),
        kind=str(payload["kind"]),  # type: ignore[arg-type]
        value=str(payload["value"]),
        source=str(payload["source"]),  # type: ignore[arg-type]
        revision=int(payload["revision"]),
        active=bool(payload["active"]),
        created_at=_parse_utc(payload["created_at"]),
        updated_at=_parse_utc(payload["updated_at"]),
    )


def _proposal_payload(proposal: PreferenceChangeProposal) -> dict[str, object]:
    return {
        "proposal_ref": proposal.proposal_ref,
        "owner_ref": proposal.owner_ref,
        "kind": proposal.kind,
        "value": proposal.value,
        "source": proposal.source,
        "evidence_refs": list(proposal.evidence_refs),
        "created_at": _iso(proposal.created_at),
        "expires_at": _iso(proposal.expires_at),
    }


def require_memory_access(
    authorization: AuthorizationDecision | None,
    *,
    owner_ref: str,
    connection_ref: str,
    resource_ref: str,
    operation: Literal["read", "write", "delete"],
) -> None:
    if operation not in ("read", "write", "delete"):
        raise CapabilityDenied("unsupported memory operation")
    require_authorized_operation(
        authorization,
        capability=MEMORY_CAPABILITY,
        operation=operation,
        provider_ref=MEMORY_PROVIDER,
        data_class=MEMORY_DATA_CLASS,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=resource_ref,
        purpose=MEMORY_PURPOSE,
    )
