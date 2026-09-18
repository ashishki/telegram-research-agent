"""Default-deny, revision-bound capability grants for the PA request boundary.

This module deliberately contains no credential lookup, network call, database
write, or environment-based authorization.  A configured key can make an
adapter technically available, but only an active matching ``CapabilityGrant``
can authorize a request to use it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import re
from threading import RLock
from typing import Any, Literal, Mapping, Sequence


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
_GRANT_REF = re.compile(r"^grant_[a-z0-9_-]{3,120}$")
_OWNER_REF = re.compile(r"^owner_[a-z0-9_-]{3,120}$")
_CONNECTION_REF = re.compile(r"^connection_[a-z0-9_-]{3,120}$")


class CapabilityDenied(RuntimeError):
    """Raised only by an adapter after a policy decision has denied egress."""


class CapabilityGrantDocumentError(ValueError):
    """A versioned grant document is malformed or unsafe to interpret."""


@dataclass(frozen=True, slots=True)
class ProviderPolicy:
    permitted_provider_refs: tuple[str, ...]
    fallback_allowed: bool = False
    maximum_request_count: int = 1
    egress_allowed: bool = True

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
        if not isinstance(self.egress_allowed, bool):
            raise ValueError("egress_allowed must be boolean")
        if not self.egress_allowed and self.permitted_provider_refs:
            raise ValueError("denied egress cannot permit providers")


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


def decode_capability_grant_document(
    document: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> CapabilityGrant:
    """Decode the PA-01 ``assistant.capability_grant.v1`` contract fail-closed.

    This is the sole bridge from the versioned public contract into PA-02's
    runtime type.  It accepts only the complete v1 shape and verifies that the
    declared status agrees with its validity/revocation timestamps at ``now``.
    It never reads credentials, a database or an account.
    """

    if not isinstance(document, Mapping) or set(document) != {
        "schema_version",
        "grant_id",
        "owner_ref",
        "connection_ref",
        "capability",
        "provider_policy",
        "validity",
        "status",
    }:
        raise CapabilityGrantDocumentError("grant document has an invalid shape")
    if document.get("schema_version") != "assistant.capability_grant.v1":
        raise CapabilityGrantDocumentError("unsupported grant schema version")

    grant_id = _document_string(document.get("grant_id"), pattern=_GRANT_REF)
    owner_ref = _document_string(document.get("owner_ref"), pattern=_OWNER_REF)
    connection_value = document.get("connection_ref")
    connection_ref = (
        None
        if connection_value is None
        else _document_string(connection_value, pattern=_CONNECTION_REF)
    )
    capability = _document_mapping(document.get("capability"), required={
        "name", "resource_refs", "operations", "data_classes", "purpose"
    })
    provider_policy = _document_mapping(document.get("provider_policy"), required={
        "egress", "permitted_provider_refs", "fallback_allowed", "maximum_request_count"
    })
    validity = _document_mapping(document.get("validity"), required={
        "issued_at", "expires_at", "revision", "revoked_at"
    })

    capability_name = _document_string(capability.get("name"), pattern=_CAPABILITY)
    resource_refs = _document_string_list(capability.get("resource_refs"), maximum=32)
    operations = _document_string_list(capability.get("operations"), maximum=8, allowed=_OPERATIONS)
    data_classes = _document_string_list(capability.get("data_classes"), maximum=8, allowed=_DATA_CLASSES)
    purpose = _document_string(capability.get("purpose"), pattern=_CAPABILITY)

    egress = provider_policy.get("egress")
    if egress not in {"allow", "deny"}:
        raise CapabilityGrantDocumentError("grant egress policy is invalid")
    providers = _document_string_list(
        provider_policy.get("permitted_provider_refs"),
        maximum=16,
        pattern=re.compile(r"^provider_[a-z0-9_.-]{3,120}$"),
        allow_empty=egress == "deny",
    )
    if (egress == "allow" and not providers) or (egress == "deny" and providers):
        raise CapabilityGrantDocumentError("grant egress/provider policy is inconsistent")
    fallback_allowed = provider_policy.get("fallback_allowed")
    maximum_request_count = provider_policy.get("maximum_request_count")
    if not isinstance(fallback_allowed, bool):
        raise CapabilityGrantDocumentError("grant fallback policy is invalid")
    if (
        not isinstance(maximum_request_count, int)
        or isinstance(maximum_request_count, bool)
        or not 0 <= maximum_request_count <= 100000
    ):
        raise CapabilityGrantDocumentError("grant request budget is invalid")

    issued_at = _document_timestamp(validity.get("issued_at"))
    expires_value = validity.get("expires_at")
    expires_at = None if expires_value is None else _document_timestamp(expires_value)
    revoked_value = validity.get("revoked_at")
    revoked_at = None if revoked_value is None else _document_timestamp(revoked_value)
    revision = validity.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise CapabilityGrantDocumentError("grant revision is invalid")

    status = document.get("status")
    if status not in {"active", "revoked", "expired"}:
        raise CapabilityGrantDocumentError("grant status is invalid")
    grant = CapabilityGrant(
        grant_id=grant_id,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        capability=capability_name,
        resource_refs=tuple(resource_refs),
        operations=tuple(operations),
        data_classes=tuple(data_classes),
        purpose=purpose,
        provider_policy=ProviderPolicy(
            tuple(providers),
            fallback_allowed=fallback_allowed,
            maximum_request_count=maximum_request_count,
            egress_allowed=egress == "allow",
        ),
        issued_at=issued_at,
        expires_at=expires_at,
        revision=revision,
        revoked_at=revoked_at,
    )
    if grant.state_at(_utc(now or datetime.now(timezone.utc))) != status:
        raise CapabilityGrantDocumentError("grant status does not match validity state")
    return grant


def _document_mapping(value: object, *, required: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != required:
        raise CapabilityGrantDocumentError("grant nested object has an invalid shape")
    return value


def _document_string(value: object, *, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise CapabilityGrantDocumentError("grant string field is invalid")
    if pattern is not None and not pattern.fullmatch(value):
        raise CapabilityGrantDocumentError("grant string field has an invalid format")
    return value


def _document_string_list(
    value: object,
    *,
    maximum: int,
    allowed: set[str] | None = None,
    pattern: re.Pattern[str] | None = None,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty) or len(value) > maximum:
        raise CapabilityGrantDocumentError("grant list field is invalid")
    values = [_document_string(item, pattern=pattern) for item in value]
    if len(set(values)) != len(values) or (allowed is not None and not set(values) <= allowed):
        raise CapabilityGrantDocumentError("grant list values are invalid")
    return values


def _document_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise CapabilityGrantDocumentError("grant timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CapabilityGrantDocumentError("grant timestamp is invalid") from exc
    return _utc(parsed)


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
    connection_ref: str | None = None
    expected_grant_revision: int | None = None
    grant_ref: str | None = None
    is_fallback: bool = False

    def __post_init__(self) -> None:
        for name, value in (("owner_ref", self.owner_ref), ("resource_ref", self.resource_ref), ("purpose", self.purpose)):
            if not _is_opaque_ref(value):
                raise ValueError(f"invalid {name}")
        if self.connection_ref is not None and not _is_opaque_ref(self.connection_ref):
            raise ValueError("invalid connection_ref")
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
    owner_ref: str
    connection_ref: str | None
    resource_ref: str
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
    """One registry-bound egress slot, revalidated exactly at consumption."""

    __slots__ = ("grant_ref", "grant_revision", "_registry", "_request", "_consumed", "_lock")

    def __init__(
        self,
        *,
        registry: "CapabilityRegistry",
        request: AuthorizationRequest,
        grant_ref: str,
        grant_revision: int,
    ) -> None:
        self._registry = registry
        self._request = replace(
            request,
            grant_ref=grant_ref,
            expected_grant_revision=grant_revision,
        )
        self.grant_ref = grant_ref
        self.grant_revision = grant_revision
        self._consumed = False
        self._lock = RLock()

    def consume(self) -> bool:
        with self._lock:
            if self._consumed or not self._registry._reservation_is_current(self):
                return False
            self._consumed = True
            return True

    @property
    def available(self) -> bool:
        with self._lock:
            return not self._consumed

    @property
    def current(self) -> bool:
        with self._lock:
            return not self._consumed and self._registry._reservation_is_current(self)


class CapabilityRegistry:
    """Current grant lookup. No grant is equivalent to a denied request.

    PA-02 stores grants in memory only, but a reserved decision is never a
    durable grant snapshot: an adapter rechecks current revoke, expiry and
    revision state immediately before its transport call.
    """

    def __init__(self, grants: Sequence[CapabilityGrant]) -> None:
        self._grants_by_id = {grant.grant_id: grant for grant in grants}
        self._reserved_counts: dict[tuple[str, int], int] = {}
        self._lock = RLock()
        grant_ids = [grant.grant_id for grant in grants]
        if len(set(grant_ids)) != len(grant_ids):
            raise ValueError("grant IDs must be unique")

    def replace_grant(self, grant: CapabilityGrant) -> None:
        """Atomically publish a strictly newer revision of an existing grant."""

        with self._lock:
            current = self._grants_by_id.get(grant.grant_id)
            if current is None:
                raise KeyError("cannot replace an unknown grant")
            if grant.revision <= current.revision:
                raise ValueError("replacement grant revision must increase")
            self._grants_by_id[grant.grant_id] = grant

    def revoke_grant(self, grant_ref: str, *, revoked_at: datetime | None = None) -> None:
        """Atomically revoke an existing grant without exposing its contents."""

        with self._lock:
            current = self._grants_by_id.get(grant_ref)
            if current is None:
                raise KeyError("cannot revoke an unknown grant")
            self._grants_by_id[grant_ref] = replace(
                current,
                revoked_at=_utc(revoked_at or datetime.now(timezone.utc)),
            )

    def expire_grant(self, grant_ref: str, *, expires_at: datetime | None = None) -> None:
        """Atomically expire an existing grant for deterministic local revocation tests."""

        with self._lock:
            current = self._grants_by_id.get(grant_ref)
            if current is None:
                raise KeyError("cannot expire an unknown grant")
            self._grants_by_id[grant_ref] = replace(
                current,
                expires_at=_utc(expires_at or datetime.now(timezone.utc)),
            )

    def authorize_and_reserve(
        self,
        request: AuthorizationRequest,
        *,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        """Authorize and reserve one provider-operation slot without a network call.

        Reservations are intentionally spent after a real attempt, including an
        unknown outcome. Automatic retries are not authorized by this method.
        """

        with self._lock:
            decision = self._authorize_unlocked(request, moment=_utc(now or datetime.now(timezone.utc)))
            if not decision.allowed or decision.grant_ref is None or decision.grant_revision is None:
                return decision
            grant = self._grants_by_id[decision.grant_ref]
            key = (grant.grant_id, grant.revision)
            used = self._reserved_counts.get(key, 0)
            if used >= grant.provider_policy.maximum_request_count:
                return _deny(request, "grant_budget_exhausted", grant)
            self._reserved_counts[key] = used + 1
        return AuthorizationDecision(
            allowed=True,
            reason="allowed",
            grant_ref=decision.grant_ref,
            grant_revision=decision.grant_revision,
            owner_ref=decision.owner_ref,
            connection_ref=decision.connection_ref,
            resource_ref=decision.resource_ref,
            capability=decision.capability,
            operation=decision.operation,
            data_class=decision.data_class,
            provider_ref=decision.provider_ref,
            purpose=decision.purpose,
            reservation=BudgetReservation(
                registry=self,
                request=request,
                grant_ref=grant.grant_id,
                grant_revision=grant.revision,
            ),
        )

    def authorize(self, request: AuthorizationRequest, *, now: datetime | None = None) -> AuthorizationDecision:
        with self._lock:
            return self._authorize_unlocked(request, moment=_utc(now or datetime.now(timezone.utc)))

    def _reservation_is_current(self, reservation: BudgetReservation) -> bool:
        with self._lock:
            decision = self._authorize_unlocked(reservation._request, moment=datetime.now(timezone.utc))
            return bool(
                decision.allowed
                and decision.grant_ref == reservation.grant_ref
                and decision.grant_revision == reservation.grant_revision
            )

    def _authorize_unlocked(self, request: AuthorizationRequest, *, moment: datetime) -> AuthorizationDecision:
        candidates = [grant for grant in self._grants_by_id.values() if grant.owner_ref == request.owner_ref]
        if request.grant_ref is not None:
            candidates = [grant for grant in candidates if grant.grant_id == request.grant_ref]
        if not candidates:
            return _deny(request, "no_matching_grant")

        capability_matches = [grant for grant in candidates if grant.capability == request.capability]
        if not capability_matches:
            return _deny(request, "capability_not_granted")
        connection_matches = [grant for grant in capability_matches if grant.connection_ref == request.connection_ref]
        if not connection_matches:
            return _deny(request, "connection_not_granted", capability_matches[0])
        resource_matches = [grant for grant in connection_matches if request.resource_ref in grant.resource_refs]
        if not resource_matches:
            return _deny(request, "resource_not_granted", connection_matches[0])
        operation_matches = [grant for grant in resource_matches if request.operation in grant.operations]
        if not operation_matches:
            return _deny(request, "operation_not_granted", resource_matches[0])
        data_matches = [grant for grant in operation_matches if request.data_class in grant.data_classes]
        if not data_matches:
            return _deny(request, "data_class_not_granted", operation_matches[0])
        purpose_matches = [grant for grant in data_matches if request.purpose == grant.purpose]
        if not purpose_matches:
            return _deny(request, "purpose_not_granted", data_matches[0])
        fallback_matches = [
            grant for grant in purpose_matches if not request.is_fallback or grant.provider_policy.fallback_allowed
        ]
        if not fallback_matches:
            return _deny(request, "fallback_not_granted", purpose_matches[0])
        if request.operation == "model_egress" and request.provider_ref is None:
            return _deny(request, "provider_required", fallback_matches[0])
        egress_matches = [
            grant
            for grant in fallback_matches
            if request.operation != "model_egress" or grant.provider_policy.egress_allowed
        ]
        if not egress_matches:
            return _deny(request, "egress_denied", fallback_matches[0])
        provider_matches = [
            grant
            for grant in egress_matches
            if request.provider_ref is None or request.provider_ref in grant.provider_policy.permitted_provider_refs
        ]
        if not provider_matches:
            return _deny(request, "provider_not_permitted", egress_matches[0])

        state_denial: AuthorizationDecision | None = None
        for grant in provider_matches:
            state = grant.state_at(moment)
            if state != "active":
                state_denial = _deny(request, f"grant_{state}", grant)
                continue
            if request.expected_grant_revision is not None and request.expected_grant_revision != grant.revision:
                state_denial = _deny(request, "grant_revision_mismatch", grant)
                continue
            return AuthorizationDecision(
                allowed=True,
                reason="allowed",
                grant_ref=grant.grant_id,
                grant_revision=grant.revision,
                owner_ref=request.owner_ref,
                connection_ref=request.connection_ref,
                resource_ref=request.resource_ref,
                capability=request.capability,
                operation=request.operation,
                data_class=request.data_class,
                provider_ref=request.provider_ref,
                purpose=request.purpose,
            )
        return state_denial or _deny(request, "no_matching_grant")


def is_authorized_egress(
    decision: AuthorizationDecision | None,
    *,
    capability: str,
    provider_ref: str,
    data_class: str,
    owner_ref: str,
    connection_ref: str | None,
    resource_ref: str,
) -> bool:
    """Check a prior decision immediately before an external request."""

    return is_authorized_operation(
        decision,
        capability=capability,
        operation="model_egress",
        provider_ref=provider_ref,
        data_class=data_class,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=resource_ref,
    )


def is_authorized_operation(
    decision: AuthorizationDecision | None,
    *,
    capability: str,
    operation: str,
    provider_ref: str,
    data_class: str,
    owner_ref: str,
    connection_ref: str | None,
    resource_ref: str,
) -> bool:
    """Check an authorization immediately before an adapter operation."""

    return bool(
        decision is not None
        and decision.allowed
        and decision.owner_ref == owner_ref
        and decision.connection_ref == connection_ref
        and decision.resource_ref == resource_ref
        and decision.capability == capability
        and decision.operation == operation
        and decision.provider_ref == provider_ref
        and decision.data_class == data_class
        and decision.reservation is not None
        and decision.reservation.current
    )


def require_authorized_egress(
    decision: AuthorizationDecision | None,
    *,
    capability: str,
    provider_ref: str,
    data_class: str,
    owner_ref: str,
    connection_ref: str | None,
    resource_ref: str,
) -> None:
    if not is_authorized_egress(
        decision,
        capability=capability,
        provider_ref=provider_ref,
        data_class=data_class,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=resource_ref,
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
    owner_ref: str,
    connection_ref: str | None,
    resource_ref: str,
) -> None:
    if not is_authorized_operation(
        decision,
        capability=capability,
        operation=operation,
        provider_ref=provider_ref,
        data_class=data_class,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=resource_ref,
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


def describe_current_capability_scope(
    grants: Sequence[CapabilityGrant],
    *,
    now: datetime | None = None,
) -> str:
    """Render the currently enforceable scope without inventing a grant source."""

    moment = _utc(now or datetime.now(timezone.utc))
    active = [grant for grant in grants if grant.state_at(moment) == "active"]
    if not active:
        return (
            "Права и приватность\n"
            "Сейчас нет активных разрешений: внешние модели, голосовая загрузка и "
            "передача материалов провайдерам заблокированы.\n"
            "Ключ провайдера сам по себе не является согласием.\n"
            "Подключение, выдача и отзыв разрешений появятся только после отдельного "
            "подтверждённого источника grants; этот бот его пока не создаёт."
        )
    return "\n\n".join(describe_grant_scope(grant) for grant in active)


def _deny(request: AuthorizationRequest, reason: str, grant: CapabilityGrant | None = None) -> AuthorizationDecision:
    return AuthorizationDecision(
        allowed=False,
        reason=reason,
        grant_ref=grant.grant_id if grant else None,
        grant_revision=grant.revision if grant else None,
        owner_ref=request.owner_ref,
        connection_ref=request.connection_ref,
        resource_ref=request.resource_ref,
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
