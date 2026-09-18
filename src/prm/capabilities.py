"""Default-deny, revision-bound capability grants for the PA request boundary.

This module deliberately contains no credential lookup, network call, database
write, or environment-based authorization.  A configured key can make an
adapter technically available, but only an active matching ``CapabilityGrant``
can authorize a request to use it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from threading import Lock
from typing import Literal, Sequence


GrantOperation = Literal["read", "prepare", "deliver", "write", "delete", "model_egress"]
DataClass = Literal[
    "public",
    "user_provided",
    "private_archive",
    "private_connector_metadata",
    "private_connector_content",
    "model_generated",
]
_OPERATIONS = {"read", "prepare", "deliver", "write", "delete", "model_egress"}
_DATA_CLASSES = {
    "public",
    "user_provided",
    "private_archive",
    "private_connector_metadata",
    "private_connector_content",
    "model_generated",
}
_OPAQUE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,511}$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9_.-]{2,80}$")


class CapabilityDenied(RuntimeError):
    """Raised only by an adapter after a policy decision has denied egress."""


@dataclass(frozen=True, slots=True)
class ProviderPolicy:
    permitted_provider_refs: tuple[str, ...]
    fallback_allowed: bool = False
    maximum_request_count: int = 1

    def __post_init__(self) -> None:
        if len(self.permitted_provider_refs) > 16:
            raise ValueError("too many permitted providers")
        if len(set(self.permitted_provider_refs)) != len(self.permitted_provider_refs):
            raise ValueError("permitted providers must be unique")
        if any(not _is_opaque_ref(value) for value in self.permitted_provider_refs):
            raise ValueError("invalid provider reference")
        if not isinstance(self.maximum_request_count, int) or isinstance(self.maximum_request_count, bool):
            raise ValueError("maximum request count must be an integer")
        if not 0 <= self.maximum_request_count <= 100000:
            raise ValueError("maximum request count is out of range")


@dataclass(frozen=True, slots=True)
class CapabilityGrant:
    """An in-memory representation of ``assistant.capability_grant.v1``."""

    grant_id: str
    owner_ref: str
    connection_ref: str | None
    capability: str
    resource_refs: tuple[str, ...]
    operations: tuple[GrantOperation, ...]
    data_classes: tuple[DataClass, ...]
    purpose: str
    provider_policy: ProviderPolicy
    issued_at: datetime
    expires_at: datetime | None
    revision: int
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        for name, value in (("grant_id", self.grant_id), ("owner_ref", self.owner_ref), ("purpose", self.purpose)):
            if not _is_opaque_ref(value):
                raise ValueError(f"invalid {name}")
        if self.connection_ref is not None and not _is_opaque_ref(self.connection_ref):
            raise ValueError("invalid connection_ref")
        if not _CAPABILITY.fullmatch(self.capability):
            raise ValueError("invalid capability")
        if not self.resource_refs or len(self.resource_refs) > 32 or len(set(self.resource_refs)) != len(self.resource_refs):
            raise ValueError("resource refs must be non-empty and unique")
        if any(not _is_opaque_ref(value) for value in self.resource_refs):
            raise ValueError("invalid resource reference")
        if not self.operations or len(set(self.operations)) != len(self.operations) or not set(self.operations) <= _OPERATIONS:
            raise ValueError("invalid grant operations")
        if not self.data_classes or len(set(self.data_classes)) != len(self.data_classes) or not set(self.data_classes) <= _DATA_CLASSES:
            raise ValueError("invalid grant data classes")
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("grant revision must be positive")
        if self.issued_at.tzinfo is None or (self.expires_at is not None and self.expires_at.tzinfo is None):
            raise ValueError("grant timestamps must be timezone-aware")

    def state_at(self, now: datetime) -> str:
        moment = _utc(now)
        if self.revoked_at is not None and _utc(self.revoked_at) <= moment:
            return "revoked"
        if self.expires_at is not None and _utc(self.expires_at) <= moment:
            return "expired"
        if _utc(self.issued_at) > moment:
            return "not_yet_valid"
        return "active"


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    """Metadata-only authorization input; it never carries a prompt or payload."""

    owner_ref: str
    capability: str
    resource_ref: str
    operation: GrantOperation
    data_class: DataClass
    provider_ref: str | None
    purpose: str
    expected_grant_revision: int | None = None
    grant_ref: str | None = None
    is_fallback: bool = False

    def __post_init__(self) -> None:
        for name, value in (("owner_ref", self.owner_ref), ("resource_ref", self.resource_ref), ("purpose", self.purpose)):
            if not _is_opaque_ref(value):
                raise ValueError(f"invalid {name}")
        if self.provider_ref is not None and not _is_opaque_ref(self.provider_ref):
            raise ValueError("invalid provider_ref")
        if self.grant_ref is not None and not _is_opaque_ref(self.grant_ref):
            raise ValueError("invalid grant_ref")
        if not _CAPABILITY.fullmatch(self.capability):
            raise ValueError("invalid capability")
        if self.operation not in _OPERATIONS or self.data_class not in _DATA_CLASSES:
            raise ValueError("invalid authorization scope")
        if self.expected_grant_revision is not None and self.expected_grant_revision < 1:
            raise ValueError("invalid expected grant revision")


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    grant_ref: str | None
    grant_revision: int | None
    capability: str
    operation: str
    data_class: str
    provider_ref: str | None
    purpose: str
    reservation: "BudgetReservation | None" = None

    def to_public_dict(self) -> dict[str, object]:
        """Return diagnostics safe for a user-visible permission explanation."""

        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "grant_ref": self.grant_ref,
            "grant_revision": self.grant_revision,
            "capability": self.capability,
            "operation": self.operation,
            "data_class": self.data_class,
            "provider_ref": self.provider_ref,
            "purpose": self.purpose,
            "budget_reserved": self.reservation is not None,
        }


class BudgetReservation:
    """One egress slot reserved by a registry and consumable exactly once."""

    __slots__ = ("grant_ref", "grant_revision", "_consumed", "_lock")

    def __init__(self, *, grant_ref: str, grant_revision: int) -> None:
        self.grant_ref = grant_ref
        self.grant_revision = grant_revision
        self._consumed = False
        self._lock = Lock()

    def consume(self) -> bool:
        with self._lock:
            if self._consumed:
                return False
            self._consumed = True
            return True

    @property
    def available(self) -> bool:
        with self._lock:
            return not self._consumed


class CapabilityRegistry:
    """Immutable grant lookup. No grant is equivalent to a denied request."""

    def __init__(self, grants: Sequence[CapabilityGrant]) -> None:
        self._grants = tuple(grants)
        self._grants_by_id = {grant.grant_id: grant for grant in self._grants}
        self._reserved_counts: dict[tuple[str, int], int] = {}
        self._budget_lock = Lock()
        grant_ids = [grant.grant_id for grant in self._grants]
        if len(set(grant_ids)) != len(grant_ids):
            raise ValueError("grant IDs must be unique")

    def authorize_and_reserve(
        self,
        request: AuthorizationRequest,
        *,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        """Authorize and reserve one provider-operation slot without a network call.

        Reservations are intentionally consumed even when an adapter later
        reports an unknown outcome.  That conservative accounting prevents an
        automatic retry from silently exceeding the confirmed grant budget.
        """

        decision = self.authorize(request, now=now)
        if not decision.allowed or decision.grant_ref is None or decision.grant_revision is None:
            return decision
        grant = self._grants_by_id[decision.grant_ref]
        key = (grant.grant_id, grant.revision)
        with self._budget_lock:
            used = self._reserved_counts.get(key, 0)
            if used >= grant.provider_policy.maximum_request_count:
                return _deny(request, "grant_budget_exhausted", grant)
            self._reserved_counts[key] = used + 1
        return AuthorizationDecision(
            allowed=True,
            reason="allowed",
            grant_ref=decision.grant_ref,
            grant_revision=decision.grant_revision,
            capability=decision.capability,
            operation=decision.operation,
            data_class=decision.data_class,
            provider_ref=decision.provider_ref,
            purpose=decision.purpose,
            reservation=BudgetReservation(grant_ref=grant.grant_id, grant_revision=grant.revision),
        )

    def authorize(self, request: AuthorizationRequest, *, now: datetime | None = None) -> AuthorizationDecision:
        moment = _utc(now or datetime.now(timezone.utc))
        candidates = [grant for grant in self._grants if grant.owner_ref == request.owner_ref]
        if request.grant_ref is not None:
            candidates = [grant for grant in candidates if grant.grant_id == request.grant_ref]
        if not candidates:
            return _deny(request, "no_matching_grant")

        # A deterministic reason is more useful than a generic denial, but it
        # never includes request content, credentials, or provider responses.
        for grant in candidates:
            state = grant.state_at(moment)
            if state == "revoked":
                return _deny(request, "grant_revoked", grant)
            if state == "expired":
                return _deny(request, "grant_expired", grant)
            if state == "not_yet_valid":
                return _deny(request, "grant_not_yet_valid", grant)
            if request.expected_grant_revision is not None and request.expected_grant_revision != grant.revision:
                return _deny(request, "grant_revision_mismatch", grant)
            if request.capability != grant.capability:
                continue
            if request.resource_ref not in grant.resource_refs:
                return _deny(request, "resource_not_granted", grant)
            if request.operation not in grant.operations:
                return _deny(request, "operation_not_granted", grant)
            if request.data_class not in grant.data_classes:
                return _deny(request, "data_class_not_granted", grant)
            if request.purpose != grant.purpose:
                return _deny(request, "purpose_not_granted", grant)
            if request.is_fallback and not grant.provider_policy.fallback_allowed:
                return _deny(request, "fallback_not_granted", grant)
            if request.provider_ref is not None and request.provider_ref not in grant.provider_policy.permitted_provider_refs:
                return _deny(request, "provider_not_permitted", grant)
            if request.operation == "model_egress" and request.provider_ref is None:
                return _deny(request, "provider_required", grant)
            return AuthorizationDecision(
                allowed=True,
                reason="allowed",
                grant_ref=grant.grant_id,
                grant_revision=grant.revision,
                capability=request.capability,
                operation=request.operation,
                data_class=request.data_class,
                provider_ref=request.provider_ref,
                purpose=request.purpose,
            )
        return _deny(request, "capability_not_granted")


def is_authorized_egress(
    decision: AuthorizationDecision | None,
    *,
    capability: str,
    provider_ref: str,
    data_class: str,
) -> bool:
    """Check a prior decision immediately before an external request."""

    return is_authorized_operation(
        decision,
        capability=capability,
        operation="model_egress",
        provider_ref=provider_ref,
        data_class=data_class,
    )


def is_authorized_operation(
    decision: AuthorizationDecision | None,
    *,
    capability: str,
    operation: str,
    provider_ref: str,
    data_class: str,
) -> bool:
    """Check an authorization immediately before an adapter operation."""

    return bool(
        decision is not None
        and decision.allowed
        and decision.capability == capability
        and decision.operation == operation
        and decision.provider_ref == provider_ref
        and decision.data_class == data_class
        and decision.reservation is not None
        and decision.reservation.available
    )


def require_authorized_egress(
    decision: AuthorizationDecision | None,
    *,
    capability: str,
    provider_ref: str,
    data_class: str,
) -> None:
    if not is_authorized_egress(
        decision,
        capability=capability,
        provider_ref=provider_ref,
        data_class=data_class,
    ):
        raise CapabilityDenied("An active capability grant is required before provider egress")
    assert decision is not None and decision.reservation is not None
    if not decision.reservation.consume():
        raise CapabilityDenied("The capability budget reservation was already consumed")


def require_authorized_operation(
    decision: AuthorizationDecision | None,
    *,
    capability: str,
    operation: str,
    provider_ref: str,
    data_class: str,
) -> None:
    if not is_authorized_operation(
        decision,
        capability=capability,
        operation=operation,
        provider_ref=provider_ref,
        data_class=data_class,
    ):
        raise CapabilityDenied("An active capability grant is required before provider operation")
    assert decision is not None and decision.reservation is not None
    if not decision.reservation.consume():
        raise CapabilityDenied("The capability budget reservation was already consumed")


def describe_grant_scope(grant: CapabilityGrant) -> str:
    """Render the actual grant boundary without exposing identifiers or secrets."""

    providers = ", ".join(grant.provider_policy.permitted_provider_refs) or "none"
    resources = ", ".join(grant.resource_refs)
    operations = ", ".join(grant.operations)
    data_classes = ", ".join(grant.data_classes)
    return (
        f"Capability: {grant.capability}\n"
        f"Allowed resources: {resources}\n"
        f"Allowed operations: {operations}\n"
        f"Allowed data classes: {data_classes}\n"
        f"Permitted providers: {providers}\n"
        "Ключ провайдера сам по себе не является согласием."
    )


def _deny(request: AuthorizationRequest, reason: str, grant: CapabilityGrant | None = None) -> AuthorizationDecision:
    return AuthorizationDecision(
        allowed=False,
        reason=reason,
        grant_ref=grant.grant_id if grant else None,
        grant_revision=grant.revision if grant else None,
        capability=request.capability,
        operation=request.operation,
        data_class=request.data_class,
        provider_ref=request.provider_ref,
        purpose=request.purpose,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _is_opaque_ref(value: object) -> bool:
    return isinstance(value, str) and bool(_OPAQUE_REF.fullmatch(value))
