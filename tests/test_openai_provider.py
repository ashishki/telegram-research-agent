from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pytest

import llm.openai_provider as openai_provider
from llm.openai_provider import CONTEXT_EGRESS_ENABLE_ENV, OPENAI_TERRA_MODEL, PROVIDER_ENABLE_ENV, ProviderEgressDenied, ProviderEgressOutcomeUnknown, complete_with_provider
from prm.capabilities import AuthorizationRequest, CapabilityGrant, CapabilityRegistry, ProviderPolicy


class _FakeResponses:
    def __init__(self): self.calls = []
    def create(self, **kwargs): self.calls.append(kwargs); return SimpleNamespace(output_text="provider answer")
class _FakeClient:
    def __init__(self): self.responses = _FakeResponses()


SYNTHETIC_OPENAI_KEY = "synthetic-openai-key"
SYNTHETIC_OPENAI_CONNECTION = openai_provider._openai_connection_ref(SYNTHETIC_OPENAI_KEY)
assert SYNTHETIC_OPENAI_CONNECTION is not None


def _authorization(
    *,
    capability="model.generate",
    resource_ref="resource_conversation",
    data_class="user_provided",
    purpose="answer.request",
    connection_ref=SYNTHETIC_OPENAI_CONNECTION,
):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    grant = CapabilityGrant(
        grant_id=f"grant_synthetic_{capability.replace('.', '_')}",
        owner_ref="owner_synthetic_primary",
        connection_ref=connection_ref,
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
        connection_ref=connection_ref,
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


def test_provider_transport_rejects_a_grant_for_another_active_credential_before_fake_call(monkeypatch) -> None:
    granted_connection_ref = openai_provider._openai_connection_ref("synthetic-openai-grant-a")
    assert granted_connection_ref is not None
    client = _FakeClient()
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-openai-credential-b")

    with pytest.raises(ProviderEgressDenied):
        complete_with_provider(
            "Question",
            provider="openai",
            allow_provider_egress=True,
            authorization=_authorization(connection_ref=granted_connection_ref),
            owner_ref="owner_synthetic_primary",
            connection_ref=granted_connection_ref,
            resource_ref="resource_conversation",
            client=client,
        )

    assert client.responses.calls == []


def test_provider_transport_rejects_a_null_connection_ref_before_fake_call(monkeypatch) -> None:
    client = _FakeClient()
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", SYNTHETIC_OPENAI_KEY)

    with pytest.raises(ProviderEgressDenied):
        complete_with_provider(
            "Question",
            provider="openai",
            allow_provider_egress=True,
            authorization=_authorization(connection_ref=None),
            owner_ref="owner_synthetic_primary",
            connection_ref=None,
            resource_ref="resource_conversation",
            client=client,
        )

    assert client.responses.calls == []


def test_context_egress_requires_second_explicit_gate(monkeypatch) -> None:
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true"); monkeypatch.setenv("OPENAI_API_KEY", SYNTHETIC_OPENAI_KEY); monkeypatch.delenv(CONTEXT_EGRESS_ENABLE_ENV, raising=False); client = _FakeClient()
    result = complete_with_provider(
        "Question",
        provider="openai",
        allow_provider_egress=True,
        allow_context_egress=True,
        authorization=_authorization(),
        owner_ref="owner_synthetic_primary",
        connection_ref=SYNTHETIC_OPENAI_CONNECTION,
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
        local_context=[{
            "title": "approved",
            "summary": "approved context",
            "source_ref": "archive:synthetic-approved-1",
        }],
        client=client2,
        owner_ref="owner_synthetic_primary",
        connection_ref=SYNTHETIC_OPENAI_CONNECTION,
        resource_ref="resource_conversation",
        context_resource_ref="resource_archive",
    )
    assert "approved context" in repr(client2.responses.calls[0]["input"])
    assert "archive:synthetic-approved-1" in repr(client2.responses.calls[0]["input"])
    assert result2.receipt.context_egress_performed is True


def test_context_transport_rejects_a_reservation_for_the_query_purpose(monkeypatch) -> None:
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    monkeypatch.setenv(CONTEXT_EGRESS_ENABLE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", SYNTHETIC_OPENAI_KEY)
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
        local_context=[{
            "title": "private",
            "text": "must-not-egress",
            "source_ref": "archive:synthetic-private-1",
        }],
        client=client,
        owner_ref="owner_synthetic_primary",
        connection_ref=SYNTHETIC_OPENAI_CONNECTION,
        resource_ref="resource_conversation",
        context_resource_ref="resource_archive",
    )

    assert result.receipt.context_egress_performed is False
    assert len(client.responses.calls) == 1
    assert "must-not-egress" not in repr(client.responses.calls[0]["input"])


@pytest.mark.parametrize(
    ("local_context", "private_marker"),
    [
        ("raw-context-sentinel", "raw-context-sentinel"),
        ([{"title": "uncited-sentinel", "text": "uncited context"}], "uncited-sentinel"),
        ([{
            "title": "malformed-sentinel",
            "text": {"not": "text"},
            "source_ref": "archive:malformed-1",
        }], "malformed-sentinel"),
        ([
            {
                "title": "aggregate-context-sentinel" if index == 0 else "approved",
                "text": "x" * 1_200,
                "source_ref": f"archive:{index}-" + "r" * 485,
            }
            for index in range(8)
        ], "aggregate-context-sentinel"),
    ],
)
def test_context_transport_omits_raw_uncited_malformed_or_oversized_context(monkeypatch, local_context, private_marker) -> None:
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    monkeypatch.setenv(CONTEXT_EGRESS_ENABLE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", SYNTHETIC_OPENAI_KEY)
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
            purpose="answer.context",
        ),
        local_context=local_context,
        client=client,
        owner_ref="owner_synthetic_primary",
        connection_ref=SYNTHETIC_OPENAI_CONNECTION,
        resource_ref="resource_conversation",
        context_resource_ref="resource_archive",
    )

    assert result.receipt.context_egress_performed is False
    assert len(client.responses.calls) == 1
    assert private_marker not in repr(client.responses.calls[0]["input"])


def test_context_transport_reports_unknown_outcome_without_automatic_retry(monkeypatch) -> None:
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    monkeypatch.setenv(CONTEXT_EGRESS_ENABLE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", SYNTHETIC_OPENAI_KEY)
    captured_calls: list[dict] = []

    def raise_after_capture(**kwargs):
        captured_calls.append(kwargs)
        raise TimeoutError("synthetic unknown outcome")

    client = SimpleNamespace(responses=SimpleNamespace(create=raise_after_capture))
    authorization = _authorization()
    context_authorization = _authorization(
        capability="model.context_egress",
        resource_ref="resource_archive",
        data_class="private_archive",
        purpose="answer.context",
    )
    scope = {
        "owner_ref": "owner_synthetic_primary",
        "connection_ref": SYNTHETIC_OPENAI_CONNECTION,
        "resource_ref": "resource_conversation",
        "context_resource_ref": "resource_archive",
    }

    with pytest.raises(ProviderEgressOutcomeUnknown) as error:
        complete_with_provider(
            "Question",
            provider="openai",
            allow_provider_egress=True,
            allow_context_egress=True,
            authorization=authorization,
            context_authorization=context_authorization,
            local_context=[{
                "title": "approved",
                "text": "private-context-sentinel",
                "source_ref": "archive:synthetic-approved-1",
            }],
            client=client,
            **scope,
        )

    receipt = error.value.receipt
    assert len(captured_calls) == 1
    assert "private-context-sentinel" in repr(captured_calls[0]["input"])
    assert receipt.external_call_attempted is True
    assert receipt.context_egress_attempted is True
    assert receipt.external_call_performed is False
    assert receipt.context_egress_performed is False
    assert receipt.delivery_outcome == "unknown"

    retry_client = _FakeClient()
    with pytest.raises(ProviderEgressDenied):
        complete_with_provider(
            "Question",
            provider="openai",
            allow_provider_egress=True,
            allow_context_egress=True,
            authorization=authorization,
            context_authorization=context_authorization,
            local_context=[{
                "title": "approved",
                "text": "private-context-sentinel",
                "source_ref": "archive:synthetic-approved-1",
            }],
            client=retry_client,
            **scope,
        )

    assert retry_client.responses.calls == []
