"""PA-02 grant registry tests.  These fixtures contain no account or provider data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from prm.capabilities import (
    AuthorizationRequest,
    CapabilityGrant,
    CapabilityRegistry,
    CapabilityDenied,
    ProviderPolicy,
    describe_grant_scope,
    require_authorized_egress,
)


NOW = datetime(2026, 9, 18, tzinfo=timezone.utc)


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
) -> CapabilityGrant:
    return CapabilityGrant(
        grant_id="grant_synthetic_001",
        owner_ref="owner_synthetic_primary",
        connection_ref=None,
        capability=capability,
        resource_refs=(resource_ref,),
        operations=(operation,),
        data_classes=(data_class,),
        purpose="answer.request",
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
) -> AuthorizationRequest:
    return AuthorizationRequest(
        owner_ref="owner_synthetic_primary",
        capability=capability,
        resource_ref=resource_ref,
        operation=operation,
        data_class=data_class,
        provider_ref=provider_ref,
        purpose="answer.request",
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
    )
    with pytest.raises(CapabilityDenied):
        require_authorized_egress(
            first,
            capability="model.generate",
            provider_ref="provider_openai",
            data_class="user_provided",
        )


def test_permission_description_states_real_scope_and_never_calls_a_key_consent():
    description = describe_grant_scope(make_grant())

    assert "model.generate" in description
    assert "resource_conversation" in description
    assert "provider_openai" in description
    assert "Ключ провайдера сам по себе не является согласием." in description
