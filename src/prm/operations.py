"""PA-17 local, fail-closed operations, recovery and security contracts.

This module makes failure and recovery behavior explicit and testable without
touching any live system: no service start, timer, network call, database
migration, restore or deployment. Unknown states stay unknown, a duplicate
execution reuses its receipt instead of acting twice, recovery never blindly
retries, migration rehearsals refuse the live path, and deployment requires an
explicit approval.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import re
from typing import Literal, Sequence


OPS_SCHEMA_VERSION = "assistant.operations.v1"
HEALTH_STATES = ("healthy", "degraded", "down", "unknown")
FAILURE_KINDS = (
    "rate_limited", "provider_outage", "disk_full", "revoked_token",
    "duplicate_execution", "timeout", "unknown",
)

_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,511}$")
_COMPONENT = re.compile(r"^[a-z][a-z0-9_.:-]{2,63}$")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _component(value: object) -> str:
    text = str(value or "")
    if not _COMPONENT.fullmatch(text):
        raise ValueError("invalid component name")
    return text


@dataclass(frozen=True, slots=True)
class ComponentSignal:
    component: str
    state: Literal["healthy", "degraded", "down", "unknown"]
    detail_ref: str = ""

    def __post_init__(self) -> None:
        _component(self.component)
        if self.state not in HEALTH_STATES:
            raise ValueError("invalid health state")
        if self.detail_ref:
            if not _REF.fullmatch(self.detail_ref):
                raise ValueError("invalid detail_ref")


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    components: tuple[ComponentSignal, ...]
    generated_at: datetime
    schema_version: str = OPS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != OPS_SCHEMA_VERSION:
            raise ValueError("unsupported ops schema version")
        _utc(self.generated_at)
        if not self.components:
            raise ValueError("a health snapshot needs components")

    @property
    def overall(self) -> Literal["healthy", "degraded", "down", "unknown"]:
        states = {signal.state for signal in self.components}
        if states == {"healthy"}:
            return "healthy"
        if "down" in states:
            return "down"
        if "degraded" in states or "unknown" in states:
            return "degraded" if "degraded" in states else "unknown"
        return "unknown"

    def to_payload(self) -> dict[str, object]:
        # Only component names, states and opaque refs are exposed.
        return {
            "schema_version": self.schema_version,
            "generated_at": _utc(self.generated_at).isoformat().replace("+00:00", "Z"),
            "overall": self.overall,
            "components": [
                {"component": signal.component, "state": signal.state, "detail_ref": signal.detail_ref}
                for signal in self.components
            ],
        }


@dataclass(frozen=True, slots=True)
class FailurePolicy:
    kind: str
    retryable: bool
    backoff_seconds: int
    requires_reconciliation: bool
    blocks_send: bool
    requires_human: bool

    def __post_init__(self) -> None:
        if self.kind not in FAILURE_KINDS:
            raise ValueError("invalid failure kind")
        if not isinstance(self.backoff_seconds, int) or isinstance(self.backoff_seconds, bool) or self.backoff_seconds < 0:
            raise ValueError("backoff_seconds must be a non-negative integer")


_POLICIES: dict[str, FailurePolicy] = {
    # 429: retry with backoff, no reconciliation, sending not blocked.
    "rate_limited": FailurePolicy("rate_limited", True, 30, False, False, False),
    # Outage: retry later, but any in-flight attempt is reconciled first.
    "provider_outage": FailurePolicy("provider_outage", True, 120, True, False, False),
    # Disk full: no blind retry, sending blocked, a human must act.
    "disk_full": FailurePolicy("disk_full", False, 0, True, True, True),
    # Revoked token: never retry; re-consent required (human).
    "revoked_token": FailurePolicy("revoked_token", False, 0, False, True, True),
    # Duplicate: reuse the existing receipt, never act again.
    "duplicate_execution": FailurePolicy("duplicate_execution", False, 0, False, False, False),
    # Timeout: unknown outcome -> reconcile before any retry.
    "timeout": FailurePolicy("timeout", False, 0, True, False, False),
    # Unknown: fail closed, reconcile, human review.
    "unknown": FailurePolicy("unknown", False, 0, True, True, True),
}


def policy_for(kind: str) -> FailurePolicy:
    try:
        return _POLICIES[kind]
    except KeyError as exc:
        raise ValueError("unknown failure kind") from exc


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    component: str
    action: Literal["resume", "abandon", "reconcile", "none"]
    reason: str

    def __post_init__(self) -> None:
        _component(self.component)
        if self.action not in ("resume", "abandon", "reconcile", "none"):
            raise ValueError("invalid recovery action")
        if not self.reason:
            raise ValueError("recovery decision needs a reason")


def plan_recovery(component: str, state: str, *, failure_kind: str | None = None) -> RecoveryDecision:
    """Recovery never blindly retries: unknown outcomes reconcile first."""

    if state == "healthy":
        return RecoveryDecision(component, "none", "component is healthy")
    if state == "down":
        return RecoveryDecision(component, "abandon", "component is down; no blind retry")
    if failure_kind is not None:
        policy = policy_for(failure_kind)
        if policy.requires_human:
            return RecoveryDecision(component, "abandon", f"{failure_kind} needs a human before any retry")
        if policy.requires_reconciliation:
            return RecoveryDecision(component, "reconcile", f"{failure_kind} requires reconciliation")
        if policy.retryable:
            return RecoveryDecision(component, "resume", f"{failure_kind} is retryable after backoff")
        return RecoveryDecision(component, "abandon", f"{failure_kind} is not retryable")
    return RecoveryDecision(component, "reconcile", "degraded state needs reconciliation")


def duplicate_outcome(existing_receipt_ref: str) -> RecoveryDecision:
    """A duplicate execution returns the original outcome; it never acts twice."""

    if not _REF.fullmatch(receipt_ref := str(existing_receipt_ref or "")):
        raise ValueError("invalid receipt ref")
    return RecoveryDecision("jobs", "none", f"duplicate execution reused receipt {receipt_ref}")


@dataclass(frozen=True, slots=True)
class BackupManifest:
    backup_ref: str
    source_copy_ref: str
    sha256: str
    created_at: datetime
    schema_version: str = OPS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != OPS_SCHEMA_VERSION:
            raise ValueError("unsupported ops schema version")
        if not _REF.fullmatch(self.backup_ref) or not _REF.fullmatch(self.source_copy_ref):
            raise ValueError("invalid backup refs")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("invalid sha256")
        _utc(self.created_at)


@dataclass(frozen=True, slots=True)
class RehearsalPlan:
    steps: tuple[tuple[str, str], ...]
    swap_requires_approval: bool

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("a rehearsal needs steps")
        for name, _detail in self.steps:
            if not _COMPONENT.fullmatch(name):
                raise ValueError("invalid rehearsal step name")


def build_migration_rehearsal(live_path: str | Path, copy_path: str | Path) -> RehearsalPlan:
    """Refuse to rehearse against the live path; only a real copy is allowed."""

    live = Path(live_path).resolve()
    copy = Path(copy_path).resolve()
    if copy == live:
        raise ValueError("rehearsal must not use the live path")
    try:
        copy.relative_to(live)
    except ValueError:
        pass
    else:
        raise ValueError("rehearsal copy must live outside the live path")
    return RehearsalPlan(
        steps=(
            ("backup", "snapshot the live data to a separate copy first"),
            ("copy", "materialize the rehearsal copy"),
            ("migrate", "apply the migration to the copy only"),
            ("verify", "verify counts, integrity and rollback on the copy"),
            ("swap", "swap only after explicit approval and a fresh backup"),
        ),
        swap_requires_approval=True,
    )


@dataclass(frozen=True, slots=True)
class DeploymentRequest:
    component: str
    version: str
    approval_ref: str = ""

    def __post_init__(self) -> None:
        _component(self.component)
        if not re.fullmatch(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,191}$", self.version):
            raise ValueError("invalid version")
        if self.approval_ref and not _REF.fullmatch(self.approval_ref):
            raise ValueError("invalid approval_ref")


def require_deployment_approval(request: DeploymentRequest, *, approved_refs: Sequence[str]) -> None:
    """Production deployment is denied unless the exact approval is present."""

    if not request.approval_ref or request.approval_ref not in set(approved_refs):
        raise PermissionError("production deployment requires an explicit approval")


def secret_ref(plaintext: str) -> str:
    """Store only an opaque, non-reversible reference to a secret."""

    if not plaintext or len(plaintext) > 4096:
        raise ValueError("invalid secret value")
    digest = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    return f"secret_ref_{digest[:32]}"


def redact_text(value: str) -> str:
    """Best-effort redaction for logs/snapshots; never a substitute for policy."""

    text = str(value)
    text = re.sub(r"\bsk-[A-Za-z0-9_\-]{16,}\b", "[REDACTED_KEY]", text)
    text = re.sub(r"\b\d{6,}:[A-Za-z0-9_\-]{20,}\b", "[REDACTED_BOT_TOKEN]", text)
    return text
