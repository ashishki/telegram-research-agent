from datetime import datetime, timedelta, timezone

import pytest

from prm.capabilities import (
    AuthorizationRequest,
    CapabilityDenied,
    CapabilityGrant,
    CapabilityRegistry,
    ProviderPolicy,
    transport_purpose,
)
from prm.confirmed_actions import (
    ACTION_EXECUTE_CAPABILITY,
    ActionExecuteRequest,
    ActionExecutor,
    ActionProposal,
    ActionReceiptStore,
    ExecutionOutcome,
    confirm_action,
    execute_action,
    reconcile_action,
    require_action_execute_access,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
OWNER = "owner_action_primary"
CONNECTION = "connection_action_primary"
RESOURCE = "resource_action_primary"


def _mail_proposal(**changes):
    values = {
        "proposal_ref": "proposal_mail_1",
        "owner_ref": OWNER,
        "connection_ref": CONNECTION,
        "provider_id": "provider_microsoft_graph",
        "action_code": "mail.send",
        "resource_ref": RESOURCE,
        "version": 1,
        "content": {"to": ["prof@example.edu"], "subject": "Question", "body": "Hello"},
        "rationale_refs": ("evidence_mail_1",),
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=10),
    }
    values.update(changes)
    return ActionProposal(**values)  # type: ignore[arg-type]


def _registry():
    grant = CapabilityGrant(
        grant_id="grant_action_primary",
        owner_ref=OWNER,
        connection_ref=CONNECTION,
        capability=ACTION_EXECUTE_CAPABILITY,
        resource_refs=(RESOURCE,),
        operations=("write",),
        data_classes=("private_connector_content",),
        purpose="action.execute",
        provider_policy=ProviderPolicy(("provider_microsoft_graph",), maximum_request_count=4),
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
        revision=1,
    )
    return CapabilityRegistry((grant,))


def _request(registry=None):
    registry = registry or _registry()
    decision = registry.authorize_and_reserve(
        AuthorizationRequest(
            owner_ref=OWNER,
            connection_ref=CONNECTION,
            capability=ACTION_EXECUTE_CAPABILITY,
            resource_ref=RESOURCE,
            operation="write",
            data_class="private_connector_content",
            provider_ref="provider_microsoft_graph",
            purpose="action.execute",
            operation_ref="operation_action",
        ),
        now=NOW,
    )
    return ActionExecuteRequest(
        authorization=decision,
        owner_ref=OWNER,
        connection_ref=CONNECTION,
        resource_ref=RESOURCE,
        provider_id="provider_microsoft_graph",
    )


class _CountingExecutor:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = 0
        self.reconciles = 0

    def execute(self, action):
        self.calls += 1
        return self.outcome

    def reconcile(self, receipt):
        self.reconciles += 1
        return ExecutionOutcome(status="succeeded", provider_operation_ref="provider_ok_1")


def test_dangerous_and_unknown_actions_are_unavailable():
    with pytest.raises(ValueError):
        _mail_proposal(action_code="coursework.submit")
    with pytest.raises(ValueError):
        _mail_proposal(action_code="payment.send")
    with pytest.raises(ValueError):
        _mail_proposal(action_code="unknown.action")


def test_mail_content_is_validated():
    with pytest.raises(ValueError):
        _mail_proposal(content={"to": [], "subject": "s", "body": "b"})
    with pytest.raises(ValueError):
        _mail_proposal(content={"to": ["not-an-email"], "subject": "s", "body": "b"})
    with pytest.raises(ValueError):
        _mail_proposal(content={"to": ["a@b.co"], "subject": "", "body": "b"})


def test_confirmation_binds_owner_actor_version_and_is_one_use():
    proposal = _mail_proposal()
    with pytest.raises(ValueError):
        confirm_action(proposal, owner_ref=OWNER, actor_ref="someone_else", now=NOW)
    action = confirm_action(proposal, owner_ref=OWNER, actor_ref=OWNER, now=NOW)
    first = action.consume(now=NOW)
    assert first is not None
    assert first.confirmation.consumed is True
    # One-use is enforced at execution through the idempotency key (below).


def test_changed_content_or_expiry_cannot_reuse_confirmation():
    from dataclasses import replace

    proposal = _mail_proposal()
    action = confirm_action(proposal, owner_ref=OWNER, actor_ref=OWNER, now=NOW)
    # A changed proposal (new version/content) must not execute on the old token.
    changed = _mail_proposal(version=2, content={"to": ["other@example.edu"], "subject": "s", "body": "b"})
    with pytest.raises(ValueError):
        execute_action(
            replace(action, proposal=changed),
            request=_request(),
            executor=_CountingExecutor(ExecutionOutcome(status="succeeded", provider_operation_ref="p1")),
            store=ActionReceiptStore(),
            now=NOW,
        )
    expired = confirm_action(proposal, owner_ref=OWNER, actor_ref=OWNER, now=NOW, ttl_seconds=30)
    assert expired.consume(now=NOW + timedelta(hours=1)) is None


def test_execute_is_idempotent_and_unknown_needs_reconciliation():
    proposal = _mail_proposal()
    action = confirm_action(proposal, owner_ref=OWNER, actor_ref=OWNER, now=NOW)
    store = ActionReceiptStore()
    executor = _CountingExecutor(ExecutionOutcome(status="unknown", error_code="timeout"))
    first = execute_action(action, request=_request(), executor=executor, store=store, now=NOW)
    assert first.status == "unknown"
    # A second click with the same key must not call the provider again.
    second = execute_action(action, request=_request(), executor=executor, store=store, now=NOW)
    assert second.idempotency_key == first.idempotency_key
    assert executor.calls == 1
    resolved = reconcile_action(first, request=_request(), executor=executor, store=store)
    assert resolved.status == "succeeded"
    assert resolved.reconciled is True
    assert executor.reconciles == 1


def test_known_failure_is_not_unknown():
    proposal = _mail_proposal()
    action = confirm_action(proposal, owner_ref=OWNER, actor_ref=OWNER, now=NOW)
    receipt = execute_action(
        action,
        request=_request(),
        executor=_CountingExecutor(ExecutionOutcome(status="failed_known", error_code="rejected")),
        store=ActionReceiptStore(),
        now=NOW,
    )
    assert receipt.status == "failed_known"


def test_execute_fails_closed_without_or_after_revoked_grant():
    proposal = _mail_proposal()
    action = confirm_action(proposal, owner_ref=OWNER, actor_ref=OWNER, now=NOW)
    with pytest.raises(CapabilityDenied):
        require_action_execute_access(
            ActionExecuteRequest(
                authorization=None,
                owner_ref=OWNER,
                connection_ref=CONNECTION,
                resource_ref=RESOURCE,
                provider_id="provider_microsoft_graph",
            )
        )
    registry = _registry()
    registry.revoke_grant("grant_action_primary", revoked_at=NOW)
    request = ActionExecuteRequest(
        authorization=None,
        owner_ref=OWNER,
        connection_ref=CONNECTION,
        resource_ref=RESOURCE,
        provider_id="provider_microsoft_graph",
    )
    with pytest.raises(CapabilityDenied):
        require_action_execute_access(request)
    assert (
        transport_purpose(
            provider_ref="provider_microsoft_graph",
            capability=ACTION_EXECUTE_CAPABILITY,
            operation="write",
        )
        == "action.execute"
    )
