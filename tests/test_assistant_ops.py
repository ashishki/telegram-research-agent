from datetime import datetime, timezone
from pathlib import Path

import pytest

from prm.operations import (
    ComponentSignal,
    DeploymentRequest,
    HealthSnapshot,
    build_migration_rehearsal,
    duplicate_outcome,
    plan_recovery,
    policy_for,
    redact_text,
    require_deployment_approval,
    secret_ref,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)


def test_health_snapshot_reports_honest_overall_state():
    healthy = HealthSnapshot(components=(ComponentSignal("storage", "healthy"),), generated_at=NOW)
    assert healthy.overall == "healthy"
    degraded = HealthSnapshot(components=(ComponentSignal("jobs", "degraded"), ComponentSignal("storage", "healthy")), generated_at=NOW)
    assert degraded.overall == "degraded"
    down = HealthSnapshot(components=(ComponentSignal("jobs", "down"), ComponentSignal("storage", "healthy")), generated_at=NOW)
    assert down.overall == "down"
    unknown = HealthSnapshot(components=(ComponentSignal("connectors", "unknown"),), generated_at=NOW)
    assert unknown.overall == "unknown"
    # Snapshot exposes only names/states/opaque refs.
    assert "secret" not in str(unknown.to_payload()).lower()


def test_failure_policies_are_explicit():
    rate = policy_for("rate_limited")
    assert rate.retryable and not rate.requires_reconciliation and not rate.blocks_send
    disk = policy_for("disk_full")
    assert not disk.retryable and disk.blocks_send and disk.requires_human
    revoked = policy_for("revoked_token")
    assert not revoked.retryable and revoked.requires_human
    timeout = policy_for("timeout")
    assert not timeout.retryable and timeout.requires_reconciliation
    duplicate = policy_for("duplicate_execution")
    assert not duplicate.retryable and not duplicate.requires_reconciliation
    with pytest.raises(ValueError):
        policy_for("made_up")


def test_recovery_never_blindly_retries():
    assert plan_recovery("storage", "healthy").action == "none"
    assert plan_recovery("jobs", "down").action == "abandon"
    assert plan_recovery("jobs", "degraded", failure_kind="timeout").action == "reconcile"
    assert plan_recovery("jobs", "degraded", failure_kind="rate_limited").action == "resume"
    assert plan_recovery("jobs", "degraded", failure_kind="disk_full").action == "abandon"


def test_duplicate_execution_reuses_receipt():
    decision = duplicate_outcome("receipt_action_1")
    assert decision.action == "none"
    assert "receipt_action_1" in decision.reason


def test_migration_rehearsal_refuses_the_live_path(tmp_path):
    live = tmp_path / "agent.db"
    live.write_text("data")
    with pytest.raises(ValueError):
        build_migration_rehearsal(live, live)
    with pytest.raises(ValueError):
        build_migration_rehearsal(tmp_path, tmp_path / "nested" / "copy.db")
    plan = build_migration_rehearsal(live, tmp_path / "rehearsal" / "copy.db")
    assert plan.swap_requires_approval is True
    assert {name for name, _ in plan.steps} >= {"backup", "copy", "migrate", "verify", "swap"}


def test_deployment_requires_explicit_approval():
    request = DeploymentRequest(component="assistant", version="2026.09.24")
    with pytest.raises(PermissionError):
        require_deployment_approval(request, approved_refs=())
    approved = DeploymentRequest(component="assistant", version="2026.09.24", approval_ref="approval_1")
    with pytest.raises(PermissionError):
        require_deployment_approval(approved, approved_refs=("approval_2",))
    require_deployment_approval(approved, approved_refs=("approval_1",))


def test_secret_ref_is_opaque_and_redaction_masks_tokens():
    ref = secret_ref("super-secret-value")
    assert ref.startswith("secret_ref_")
    assert "super-secret-value" not in ref
    masked = redact_text("key sk-abcdefghijklmnop1234 and bot 123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    assert "sk-abcdefghijklmnop1234" not in masked
    assert "[REDACTED_KEY]" in masked
    assert "[REDACTED_BOT_TOKEN]" in masked
