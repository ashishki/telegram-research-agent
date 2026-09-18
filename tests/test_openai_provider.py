from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pytest

from llm.openai_provider import CONTEXT_EGRESS_ENABLE_ENV, OPENAI_TERRA_MODEL, PROVIDER_ENABLE_ENV, ProviderEgressDenied, complete_with_provider
from prm.capabilities import AuthorizationRequest, CapabilityGrant, CapabilityRegistry, ProviderPolicy


class _FakeResponses:
    def __init__(self): self.calls = []
    def create(self, **kwargs): self.calls.append(kwargs); return SimpleNamespace(output_text="provider answer")
class _FakeClient:
    def __init__(self): self.responses = _FakeResponses()


def _authorization(
    *,
    capability="model.generate",
    resource_ref="resource_conversation",
    data_class="user_provided",
    purpose="answer.request",
):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    grant = CapabilityGrant(
        grant_id=f"grant_synthetic_{capability.replace('.', '_')}",
        owner_ref="owner_synthetic_primary",
        connection_ref=None,
        capability=capability,
        resource_refs=(resource_ref,),
        operations=("model_egress",),
        data_classes=(data_class,),
        purpose=purpose,
        provider_policy=ProviderPolicy(("provider_openai",)),
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        revision=1,
    )
    request = AuthorizationRequest(
        owner_ref="owner_synthetic_primary",
        capability=capability,
        resource_ref=resource_ref,
        operation="model_egress",
        data_class=data_class,
        provider_ref="provider_openai",
        purpose=purpose,
        expected_grant_revision=1,
    )
    return CapabilityRegistry((grant,)).authorize_and_reserve(request, now=now)


def test_local_search_is_default_and_performs_no_provider_call() -> None:
    client = _FakeClient(); result = complete_with_provider("Find archive notes", local_context=[{"title":"private","text":"context"}], client=client)
    assert result.status == "local_required" and not result.receipt.external_call_performed
    assert client.responses.calls == []


def test_provider_call_requires_environment_and_per_call_gate(monkeypatch) -> None:
    monkeypatch.delenv(PROVIDER_ENABLE_ENV, raising=False)
    with pytest.raises(ProviderEgressDenied): complete_with_provider("Use provider", provider="openai", allow_provider_egress=True, client=_FakeClient())
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    with pytest.raises(ProviderEgressDenied): complete_with_provider("Use provider", provider="openai", allow_provider_egress=False, client=_FakeClient())


def test_context_egress_requires_second_explicit_gate(monkeypatch) -> None:
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true"); monkeypatch.delenv(CONTEXT_EGRESS_ENABLE_ENV, raising=False); client = _FakeClient()
    result = complete_with_provider(
        "Question",
        provider="openai",
        allow_provider_egress=True,
        allow_context_egress=True,
        authorization=_authorization(),
        owner_ref="owner_synthetic_primary",
        connection_ref=None,
        resource_ref="resource_conversation",
        local_context=[{"title":"private title","text":"private context"}],
        client=client,
    )
    request = client.responses.calls[0]
    assert request["model"] == OPENAI_TERRA_MODEL and "private context" not in repr(request["input"])
    assert result.receipt.context_egress_performed is False
    monkeypatch.setenv(CONTEXT_EGRESS_ENABLE_ENV, "true"); client2 = _FakeClient()
    result2 = complete_with_provider(
        "Question",
        provider="openai",
        allow_provider_egress=True,
        allow_context_egress=True,
        authorization=_authorization(),
        context_authorization=_authorization(
            capability="model.context_egress",
            resource_ref="resource_archive",
            data_class="private_archive",
            purpose="answer.context",
        ),
        local_context=[{"title":"approved","summary":"approved context"}],
        client=client2,
        owner_ref="owner_synthetic_primary",
        connection_ref=None,
        resource_ref="resource_conversation",
        context_resource_ref="resource_archive",
    )
    assert "approved context" in repr(client2.responses.calls[0]["input"])
    assert result2.receipt.context_egress_performed is True


def test_context_transport_rejects_a_reservation_for_the_query_purpose(monkeypatch) -> None:
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    monkeypatch.setenv(CONTEXT_EGRESS_ENABLE_ENV, "true")
    client = _FakeClient()

    result = complete_with_provider(
        "Question",
        provider="openai",
        allow_provider_egress=True,
        allow_context_egress=True,
        authorization=_authorization(),
        context_authorization=_authorization(
            capability="model.context_egress",
            resource_ref="resource_archive",
            data_class="private_archive",
            purpose="answer.request",
        ),
        local_context=[{"title": "private", "text": "must-not-egress"}],
        client=client,
        owner_ref="owner_synthetic_primary",
        connection_ref=None,
        resource_ref="resource_conversation",
        context_resource_ref="resource_archive",
    )

    assert result.receipt.context_egress_performed is False
    assert len(client.responses.calls) == 1
    assert "must-not-egress" not in repr(client.responses.calls[0]["input"])
