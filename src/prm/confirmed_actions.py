"""PA-13 local, fail-closed confirmed external actions.

An external write (send mail, create/update/cancel a calendar event) happens
only after a one-use, version-bound, owner-bound confirmation of the exact
content, and only when a freshly reserved PA-02 write grant is present. The
default is deny: no OAuth, network call, token storage, default database,
scheduler or delivery lives here. Dangerous out-of-scope actions are refused by
construction, an unknown provider outcome is never retried until reconciled,
and a receipt always reflects what actually happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Literal, Mapping, Protocol

from prm.capabilities import (
    AuthorizationDecision,
    CapabilityDenied,
    require_authorized_operation,
)


ACTION_SCHEMA_VERSION = "assistant.action_proposal.v1"
ACTION_EXECUTE_CAPABILITY = "assistant.action_execute"
ACTION_EXECUTE_OPERATION = "write"
ACTION_EXECUTE_PURPOSE = "action.execute"
DATA_CLASS = "private_connector_content"

ALLOWED_ACTIONS = frozenset({"mail.send", "calendar.create", "calendar.update", "calendar.cancel"})
# Never executable by the product, whatever a caller passes.
DANGEROUS_ACTIONS = frozenset(
    {"coursework.submit", "payment.send", "course.register", "grades.write", "mail.delete_all", "profile.write"}
)
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,511}$")
_PROPOSAL = re.compile(r"^proposal_[a-z0-9_-]{3,120}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_RECIPIENTS = 20
_MAX_BODY = 20000


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


def canonical_content(action_code: str, content: Mapping[str, Any]) -> str:
    return json.dumps(
        {"action_code": action_code, "content": dict(content)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_digest(action_code: str, content: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_content(action_code, content).encode("utf-8")).hexdigest()


def _validate_content(action_code: str, content: Mapping[str, Any]) -> None:
    if action_code not in ALLOWED_ACTIONS:
        raise ValueError("action code is not allowed")
    if not isinstance(content, Mapping):
        raise ValueError("content must be a mapping")
    if action_code == "mail.send":
        recipients = content.get("to")
        if not isinstance(recipients, (list, tuple)) or not recipients or len(recipients) > _MAX_RECIPIENTS:
            raise ValueError("mail.send needs 1..20 recipients")
        for recipient in recipients:
            if not _EMAIL.fullmatch(str(recipient)) or len(str(recipient)) > 254:
                raise ValueError("invalid recipient address")
        _text(content.get("subject"), field="subject", maximum=240)
        _text(content.get("body"), field="body", maximum=_MAX_BODY)
    else:  # calendar.*
        _text(content.get("title"), field="title", maximum=240)
        if action_code != "calendar.cancel":
            for name in ("start_at", "end_at"):
                value = content.get(name)
                if not isinstance(value, str):
                    raise ValueError(f"{name} must be an ISO string")
                try:
                    _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
                except Exception as exc:
                    raise ValueError(f"{name} must be timezone-aware") from exc
        _ref(content.get("calendar_ref"), field="calendar_ref")


@dataclass(frozen=True, slots=True)
class ActionProposal:
    proposal_ref: str
    owner_ref: str
    connection_ref: str
    provider_id: str
    action_code: str
    resource_ref: str
    version: int
    content: Mapping[str, Any]
    rationale_refs: tuple[str, ...]
    created_at: datetime
    expires_at: datetime
    status: Literal["prepared", "confirmed", "consumed", "cancelled"] = "prepared"
    schema_version: str = ACTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTION_SCHEMA_VERSION:
            raise ValueError("unsupported action schema version")
        if not _PROPOSAL.fullmatch(self.proposal_ref):
            raise ValueError("invalid proposal_ref")
        _ref(self.owner_ref, field="owner_ref")
        _ref(self.connection_ref, field="connection_ref")
        _ref(self.provider_id, field="provider_id")
        if self.action_code in DANGEROUS_ACTIONS:
            raise ValueError("this action is never available")
        _validate_content(self.action_code, self.content)
        _ref(self.resource_ref, field="resource_ref")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("proposal version must be a positive integer")
        if not self.rationale_refs:
            raise ValueError("proposal requires at least one rationale ref")
        for value in self.rationale_refs:
            _ref(value, field="rationale_ref")
        if self.status not in ("prepared", "confirmed", "consumed", "cancelled"):
            raise ValueError("invalid proposal status")
        if _utc(self.expires_at) <= _utc(self.created_at):
            raise ValueError("proposal must expire after creation")

    @property
    def digest(self) -> str:
        return content_digest(self.action_code, self.content)

    def state_at(self, now: datetime) -> str:
        if self.status in ("consumed", "cancelled"):
            return self.status
        return "expired" if _utc(now) >= _utc(self.expires_at) else self.status

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "proposal_ref": self.proposal_ref,
            "owner_ref": self.owner_ref,
            "connection_ref": self.connection_ref,
            "provider_id": self.provider_id,
            "action_code": self.action_code,
            "resource_ref": self.resource_ref,
            "version": self.version,
            "content": dict(self.content),
            "content_digest": self.digest,
            "rationale_refs": list(self.rationale_refs),
            "created_at": _iso(self.created_at),
            "expires_at": _iso(self.expires_at),
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ActionConfirmation:
    proposal_ref: str
    proposal_version: int
    content_digest: str
    owner_ref: str
    actor_ref: str
    confirmed_at: datetime
    expires_at: datetime
    consumed: bool = False

    def __post_init__(self) -> None:
        if not _PROPOSAL.fullmatch(self.proposal_ref):
            raise ValueError("invalid proposal_ref")
        if not isinstance(self.proposal_version, int) or isinstance(self.proposal_version, bool) or self.proposal_version < 1:
            raise ValueError("invalid proposal_version")
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_digest):
            raise ValueError("invalid content digest")
        _ref(self.owner_ref, field="owner_ref")
        _ref(self.actor_ref, field="actor_ref")
        if _utc(self.expires_at) <= _utc(self.confirmed_at):
            raise ValueError("confirmation must expire after it is confirmed")


@dataclass(frozen=True, slots=True)
class ConfirmedAction:
    """A single-use token; ``consume`` returns a used copy exactly once."""

    proposal: ActionProposal
    confirmation: ActionConfirmation
    idempotency_key: str

    def consume(self, *, now: datetime) -> "ConfirmedAction | None":
        if self.confirmation.consumed:
            return None
        if _utc(now) >= _utc(self.confirmation.expires_at):
            return None
        if self.proposal.state_at(now) != "prepared":
            return None
        return replace(self, confirmation=replace(self.confirmation, consumed=True))


def confirm_action(
    proposal: ActionProposal,
    *,
    owner_ref: str,
    actor_ref: str,
    now: datetime,
    ttl_seconds: int = 300,
) -> ConfirmedAction:
    """Bind a one-use confirmation to the exact proposal version and content."""

    if not 30 <= ttl_seconds <= 3600:
        raise ValueError("ttl_seconds is out of range")
    moment = _utc(now)
    if proposal.state_at(moment) != "prepared":
        raise ValueError("proposal is not confirmable")
    if proposal.owner_ref != owner_ref or owner_ref != actor_ref:
        raise ValueError("confirmation requires the exact private owner and actor")
    confirmation = ActionConfirmation(
        proposal_ref=proposal.proposal_ref,
        proposal_version=proposal.version,
        content_digest=proposal.digest,
        owner_ref=owner_ref,
        actor_ref=actor_ref,
        confirmed_at=moment,
        expires_at=moment + timedelta(seconds=ttl_seconds),
    )
    key = hashlib.sha256(
        f"{proposal.proposal_ref}\x1f{proposal.version}\x1f{proposal.digest}".encode("utf-8")
    ).hexdigest()
    return ConfirmedAction(proposal=proposal, confirmation=confirmation, idempotency_key="action_" + key[:40])


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    status: Literal["succeeded", "failed_known", "unknown"]
    provider_operation_ref: str = ""
    error_code: str = ""

    def __post_init__(self) -> None:
        if self.status not in ("succeeded", "failed_known", "unknown"):
            raise ValueError("invalid execution status")
        if self.status == "succeeded" and not self.provider_operation_ref:
            raise ValueError("a success needs a provider operation reference")
        if self.status == "unknown" and not self.error_code:
            raise ValueError("an unknown outcome needs an error code")


@dataclass(frozen=True, slots=True)
class ActionReceipt:
    idempotency_key: str
    proposal_ref: str
    proposal_version: int
    content_digest: str
    status: Literal["succeeded", "failed_known", "unknown"]
    provider_operation_ref: str = ""
    error_code: str = ""
    reconciled: bool = False
    created_at: datetime | None = None


class ActionExecutor(Protocol):
    def execute(self, action: ConfirmedAction) -> ExecutionOutcome: ...

    def reconcile(self, receipt: ActionReceipt) -> ExecutionOutcome: ...


class ActionReceiptStore:
    """Explicit in-memory receipt store; the product would use a sidecar path."""

    def __init__(self) -> None:
        self._receipts: dict[str, ActionReceipt] = {}

    def get(self, idempotency_key: str) -> ActionReceipt | None:
        return self._receipts.get(idempotency_key)

    def put(self, receipt: ActionReceipt) -> None:
        self._receipts[receipt.idempotency_key] = receipt

    def all(self) -> tuple[ActionReceipt, ...]:
        return tuple(self._receipts.values())


@dataclass(frozen=True, slots=True)
class ActionExecuteRequest:
    authorization: AuthorizationDecision | None
    owner_ref: str
    connection_ref: str
    resource_ref: str
    provider_id: str


def require_action_execute_access(request: ActionExecuteRequest) -> None:
    if request.provider_id not in ("provider_microsoft_graph", "provider_google"):
        raise CapabilityDenied("action provider is not enabled for this adapter")
    require_authorized_operation(
        request.authorization,
        capability=ACTION_EXECUTE_CAPABILITY,
        operation=ACTION_EXECUTE_OPERATION,
        provider_ref=request.provider_id,
        data_class=DATA_CLASS,
        owner_ref=request.owner_ref,
        connection_ref=request.connection_ref,
        resource_ref=request.resource_ref,
        purpose=ACTION_EXECUTE_PURPOSE,
    )


def execute_action(
    action: ConfirmedAction,
    *,
    request: ActionExecuteRequest,
    executor: ActionExecutor,
    store: ActionReceiptStore,
    now: datetime,
) -> ActionReceipt:
    """Execute exactly once; unknown outcomes are recorded, never retried here."""

    proposal = action.proposal
    if (
        action.confirmation.proposal_version != proposal.version
        or action.confirmation.content_digest != proposal.digest
    ):
        raise ValueError("confirmation does not match the proposal version/content")
    if (request.owner_ref, request.connection_ref, request.resource_ref, request.provider_id) != (
        proposal.owner_ref,
        proposal.connection_ref,
        proposal.resource_ref,
        proposal.provider_id,
    ):
        raise ValueError("execute request does not match the confirmed proposal")
    require_action_execute_access(request)
    existing = store.get(action.idempotency_key)
    if existing is not None:
        return existing
    consumed = action.consume(now=now)
    if consumed is None:
        raise ValueError("confirmation is expired, already used or the proposal changed")
    outcome = executor.execute(consumed)
    receipt = ActionReceipt(
        idempotency_key=action.idempotency_key,
        proposal_ref=proposal.proposal_ref,
        proposal_version=proposal.version,
        content_digest=proposal.digest,
        status=outcome.status,
        provider_operation_ref=outcome.provider_operation_ref,
        error_code=outcome.error_code,
        created_at=_utc(now),
    )
    store.put(receipt)
    return receipt


def reconcile_action(
    receipt: ActionReceipt,
    *,
    request: ActionExecuteRequest,
    executor: ActionExecutor,
    store: ActionReceiptStore,
) -> ActionReceipt:
    """Resolve an unknown outcome; only then is a retry meaningful."""

    if receipt.status != "unknown":
        return receipt
    require_action_execute_access(request)
    outcome = executor.reconcile(receipt)
    resolved = replace(
        receipt,
        status=outcome.status,
        provider_operation_ref=outcome.provider_operation_ref or receipt.provider_operation_ref,
        error_code=outcome.error_code or receipt.error_code,
        reconciled=True,
    )
    store.put(resolved)
    return resolved
