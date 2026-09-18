"""PA-02 grant registry tests.  These fixtures contain no account or provider data."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from prm.capabilities import (
    AuthorizationRequest,
    CapabilityGrant,
    CapabilityRegistry,
    CapabilityDenied,
    ProviderPolicy,
    describe_current_capability_scope,
    describe_grant_scope,
    require_authorized_egress,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)


def make_grant(
    *,
    capability: str = "model.generate",
    resource_ref: str = "resource_conversation",
    operation: str = "model_egress",
    data_class: str = "user_provided",
    providers: tuple[str, ...] = ("provider_openai",),
    revision: int = 3,
    revoked_at: datetime | None = None,
    expires_at: datetime | None = None,
    fallback_allowed: bool = False,
    maximum_request_count: int = 1,
    grant_id: str = "grant_synthetic_001",
    owner_ref: str = "owner_synthetic_primary",
    connection_ref: str | None = None,
    purpose: str = "answer.request",
) -> CapabilityGrant:
    return CapabilityGrant(
        grant_id=grant_id,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        capability=capability,
        resource_refs=(resource_ref,),
        operations=(operation,),
        data_classes=(data_class,),
        purpose=purpose,
        provider_policy=ProviderPolicy(
            providers,
            fallback_allowed=fallback_allowed,
            maximum_request_count=maximum_request_count,
        ),
        issued_at=NOW - timedelta(minutes=5),
        expires_at=expires_at or NOW + timedelta(hours=1),
        revision=revision,
        revoked_at=revoked_at,
    )


def make_request(
    *,
    capability: str = "model.generate",
    resource_ref: str = "resource_conversation",
    operation: str = "model_egress",
    data_class: str = "user_provided",
    provider_ref: str = "provider_openai",
    expected_revision: int | None = 3,
    is_fallback: bool = False,
    owner_ref: str = "owner_synthetic_primary",
    connection_ref: str | None = None,
    purpose: str = "answer.request",
) -> AuthorizationRequest:
    return AuthorizationRequest(
        owner_ref=owner_ref,
        capability=capability,
        resource_ref=resource_ref,
        operation=operation,
        data_class=data_class,
        provider_ref=provider_ref,
        purpose=purpose,
        connection_ref=connection_ref,
        expected_grant_revision=expected_revision,
        is_fallback=is_fallback,
    )


def test_no_consent_or_configured_key_proxy_never_authorizes_egress():
    decision = CapabilityRegistry(()).authorize(make_request(), now=NOW)

    assert decision.allowed is False
    assert decision.reason == "no_matching_grant"
    assert "key" not in decision.to_public_dict()


def test_grant_is_bound_to_owner_resource_operation_data_and_provider():
    registry = CapabilityRegistry((make_grant(),))

    allowed = registry.authorize(make_request(), now=NOW)
    wrong_resource = registry.authorize(make_request(resource_ref="resource_other"), now=NOW)
    wrong_data_class = registry.authorize(make_request(data_class="private_archive"), now=NOW)
    wrong_provider = registry.authorize(make_request(provider_ref="provider_anthropic"), now=NOW)

    assert allowed.allowed is True
    assert allowed.grant_ref == "grant_synthetic_001"
    assert wrong_resource.reason == "resource_not_granted"
    assert wrong_data_class.reason == "data_class_not_granted"
    assert wrong_provider.reason == "provider_not_permitted"


def test_revocation_expiry_and_changed_revision_fail_closed():
    request = make_request()
    revoked = CapabilityRegistry((make_grant(revoked_at=NOW - timedelta(seconds=1)),)).authorize(request, now=NOW)
    expired = CapabilityRegistry((make_grant(expires_at=NOW - timedelta(seconds=1)),)).authorize(request, now=NOW)
    stale = CapabilityRegistry((make_grant(revision=4),)).authorize(request, now=NOW)

    assert revoked.reason == "grant_revoked"
    assert expired.reason == "grant_expired"
    assert stale.reason == "grant_revision_mismatch"
    assert not revoked.allowed and not expired.allowed and not stale.allowed


def test_fallback_requires_an_explicit_grant_policy():
    request = make_request(is_fallback=True)
    denied = CapabilityRegistry((make_grant(fallback_allowed=False),)).authorize(request, now=NOW)
    allowed = CapabilityRegistry((make_grant(fallback_allowed=True),)).authorize(request, now=NOW)

    assert denied.reason == "fallback_not_granted"
    assert allowed.allowed is True


def test_budget_reservation_is_conservative_and_single_use_at_egress():
    registry = CapabilityRegistry((make_grant(maximum_request_count=1),))
    first = registry.authorize_and_reserve(make_request(), now=NOW)
    second = registry.authorize_and_reserve(make_request(), now=NOW)

    assert first.allowed is True
    assert second.reason == "grant_budget_exhausted"
    require_authorized_egress(
        first,
        capability="model.generate",
        provider_ref="provider_openai",
        data_class="user_provided",
        owner_ref="owner_synthetic_primary",
        connection_ref=None,
        resource_ref="resource_conversation",
    )
    with pytest.raises(CapabilityDenied):
        require_authorized_egress(
            first,
            capability="model.generate",
            provider_ref="provider_openai",
            data_class="user_provided",
            owner_ref="owner_synthetic_primary",
            connection_ref=None,
            resource_ref="resource_conversation",
        )


@pytest.mark.parametrize("change", ["revoke", "expire", "revision"])
def test_reserved_decision_rechecks_current_grant_state_before_consumption(change):
    grant = make_grant()
    registry = CapabilityRegistry((grant,))
    decision = registry.authorize_and_reserve(make_request(), now=NOW)

    if change == "revoke":
        registry.revoke_grant(grant.grant_id)
    elif change == "expire":
        registry.expire_grant(grant.grant_id)
    else:
        registry.replace_grant(replace(grant, revision=grant.revision + 1))

    with pytest.raises(CapabilityDenied):
        require_authorized_egress(
            decision,
            capability="model.generate",
            provider_ref="provider_openai",
            data_class="user_provided",
            owner_ref="owner_synthetic_primary",
            connection_ref=None,
            resource_ref="resource_conversation",
        )


def test_matching_active_grant_is_not_masked_by_unrelated_revoked_grant_order():
    unrelated_revoked = make_grant(
        grant_id="grant_synthetic_unrelated",
        capability="model.vision",
        revoked_at=NOW - timedelta(seconds=1),
    )
    decision = CapabilityRegistry((unrelated_revoked, make_grant())).authorize(make_request(), now=NOW)

    assert decision.allowed is True


def test_permission_description_states_real_scope_and_never_calls_a_key_consent():
    description = describe_grant_scope(make_grant())

    assert "model.generate" in description
    assert "resource_conversation" in description
    assert "provider_openai" in description
    assert "Ключ провайдера сам по себе не является согласием." in description


def test_empty_permission_description_is_an_explicit_default_deny_boundary():
    description = describe_current_capability_scope(())

    assert "нет активных разрешений" in description
    assert "заблокированы" in description
    assert "Ключ провайдера сам по себе не является согласием." in description
