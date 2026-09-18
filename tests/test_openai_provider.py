from __future__ import annotations

from dataclasses import replace
from threading import Barrier, Event, Thread
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pytest

import llm.openai_provider as openai_provider
from llm.openai_provider import CONTEXT_EGRESS_ENABLE_ENV, OPENAI_TERRA_MODEL, PROVIDER_ENABLE_ENV, ProviderEgressDenied, ProviderEgressOutcomeUnknown, complete_with_provider
from prm.capabilities import (
    AuthorizationRequest,
    CapabilityGrant,
    CapabilityRegistry,
    ProviderPolicy,
    commit_transport_reservations,
)


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
    operation_ref="operation_synthetic_openai_001",
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
        operation_ref=operation_ref,
    )
    return CapabilityRegistry((grant,)).authorize_and_reserve(request, now=now)


def _registry_and_request(
    *,
    capability="model.generate",
    resource_ref="resource_conversation",
    data_class="user_provided",
    purpose="answer.request",
    operation_ref="operation_synthetic_openai_001",
):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    grant = CapabilityGrant(
        grant_id=f"grant_synthetic_retry_{capability.replace('.', '_')}",
        owner_ref="owner_synthetic_primary",
        connection_ref=SYNTHETIC_OPENAI_CONNECTION,
        capability=capability,
        resource_refs=(resource_ref,),
        operations=("model_egress",),
        data_classes=(data_class,),
        purpose=purpose,
        provider_policy=ProviderPolicy(("provider_openai",), maximum_request_count=2),
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
        connection_ref=SYNTHETIC_OPENAI_CONNECTION,
        expected_grant_revision=1,
        operation_ref=operation_ref,
    )
    return CapabilityRegistry((grant,)), request


def _compound_registry_and_requests(*, operation_ref: str):
    """Build the one PA-02 text/context operation group in one registry."""

    now = datetime.now(timezone.utc).replace(microsecond=0)
    text_grant = CapabilityGrant(
        grant_id="grant_synthetic_compound_text",
        owner_ref="owner_synthetic_primary",
        connection_ref=SYNTHETIC_OPENAI_CONNECTION,
        capability="model.generate",
        resource_refs=("resource_conversation",),
        operations=("model_egress",),
        data_classes=("user_provided",),
        purpose="answer.request",
        provider_policy=ProviderPolicy(("provider_openai",), maximum_request_count=2),
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        revision=1,
    )
    context_grant = CapabilityGrant(
        grant_id="grant_synthetic_compound_context",
        owner_ref="owner_synthetic_primary",
        connection_ref=SYNTHETIC_OPENAI_CONNECTION,
        capability="model.context_egress",
        resource_refs=("resource_archive",),
        operations=("model_egress",),
        data_classes=("private_archive",),
        purpose="answer.context",
        provider_policy=ProviderPolicy(("provider_openai",), maximum_request_count=2),
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        revision=1,
    )
    registry = CapabilityRegistry((text_grant, context_grant))
    text_request = AuthorizationRequest(
        owner_ref="owner_synthetic_primary",
        capability="model.generate",
        resource_ref="resource_conversation",
        operation="model_egress",
        data_class="user_provided",
        provider_ref="provider_openai",
        purpose="answer.request",
        connection_ref=SYNTHETIC_OPENAI_CONNECTION,
        expected_grant_revision=1,
        operation_ref=operation_ref,
    )
    context_request = AuthorizationRequest(
        owner_ref="owner_synthetic_primary",
        capability="model.context_egress",
        resource_ref="resource_archive",
        operation="model_egress",
        data_class="private_archive",
        provider_ref="provider_openai",
        purpose="answer.context",
        connection_ref=SYNTHETIC_OPENAI_CONNECTION,
        expected_grant_revision=1,
        operation_ref=operation_ref,
    )
    return registry, text_request, context_request


def test_one_registry_reserves_and_commits_only_the_exact_openai_operation_group() -> None:
    registry, text_request, context_request = _compound_registry_and_requests(
        operation_ref="operation_synthetic_group_registry_001"
    )
    text = registry.authorize_and_reserve(text_request)
    context = registry.authorize_and_reserve(context_request)

    assert text.allowed is True
    assert context.allowed is True
    assert registry.authorize_and_reserve(text_request).reason == "operation_in_progress"
    assert text.reservation is not None
    assert context.reservation is not None
    assert commit_transport_reservations((text.reservation,)) is False
    assert text.reservation.current is True
    assert context.reservation.current is True
    assert commit_transport_reservations((text.reservation, context.reservation)) is True


def test_local_search_is_default_and_performs_no_provider_call() -> None:
    client = _FakeClient(); result = complete_with_provider("Find archive notes", local_context=[{"title":"private","text":"context"}], client=client)
    assert result.status == "local_required" and not result.receipt.external_call_performed
    assert client.responses.calls == []


def test_provider_call_requires_environment_and_per_call_gate(monkeypatch) -> None:
    monkeypatch.delenv(PROVIDER_ENABLE_ENV, raising=False)
    with pytest.raises(ProviderEgressDenied): complete_with_provider("Use provider", provider="openai", allow_provider_egress=True, client=_FakeClient())
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    with pytest.raises(ProviderEgressDenied): complete_with_provider("Use provider", provider="openai", allow_provider_egress=False, client=_FakeClient())


def test_provider_requires_matching_opaque_operation_references_before_fake_call(monkeypatch) -> None:
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    monkeypatch.setenv(CONTEXT_EGRESS_ENABLE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", SYNTHETIC_OPENAI_KEY)

    missing_ref_client = _FakeClient()
    with pytest.raises(ProviderEgressDenied):
        complete_with_provider(
            "Question",
            provider="openai",
            allow_provider_egress=True,
            authorization=_authorization(operation_ref=None),
            owner_ref="owner_synthetic_primary",
            connection_ref=SYNTHETIC_OPENAI_CONNECTION,
            resource_ref="resource_conversation",
            client=missing_ref_client,
        )

    mismatched_ref_client = _FakeClient()
    with pytest.raises(ProviderEgressDenied):
        complete_with_provider(
            "Question",
            provider="openai",
            allow_provider_egress=True,
            allow_context_egress=True,
            authorization=_authorization(operation_ref="operation_synthetic_openai_001"),
            context_authorization=_authorization(
                capability="model.context_egress",
                resource_ref="resource_archive",
                data_class="private_archive",
                purpose="answer.context",
                operation_ref="operation_synthetic_openai_002",
            ),
            local_context=[{
                "title": "approved",
                "text": "private-context-sentinel",
                "source_ref": "archive:synthetic-approved-1",
            }],
            owner_ref="owner_synthetic_primary",
            connection_ref=SYNTHETIC_OPENAI_CONNECTION,
            resource_ref="resource_conversation",
            context_resource_ref="resource_archive",
            client=mismatched_ref_client,
        )

    assert missing_ref_client.responses.calls == []
    assert mismatched_ref_client.responses.calls == []

    forged_ref_client = _FakeClient()
    with pytest.raises(ProviderEgressDenied):
        complete_with_provider(
            "Question",
            provider="openai",
            allow_provider_egress=True,
            authorization=replace(
                _authorization(operation_ref="operation_synthetic_openai_001"),
                operation_ref="operation_synthetic_openai_002",
            ),
            owner_ref="owner_synthetic_primary",
            connection_ref=SYNTHETIC_OPENAI_CONNECTION,
            resource_ref="resource_conversation",
            client=forged_ref_client,
        )

    assert forged_ref_client.responses.calls == []


def test_context_transport_uses_sealed_reservation_scope_not_copied_decision_fields(monkeypatch) -> None:
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    monkeypatch.setenv(CONTEXT_EGRESS_ENABLE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", SYNTHETIC_OPENAI_KEY)
    client = _FakeClient()
    context_authorization = _authorization(
        capability="model.context_egress",
        resource_ref="resource_archive_authorized",
        data_class="private_archive",
        purpose="answer.context",
    )

    result = complete_with_provider(
        "Question",
        provider="openai",
        allow_provider_egress=True,
        allow_context_egress=True,
        authorization=_authorization(),
        context_authorization=replace(
            context_authorization,
            resource_ref="resource_archive_ungranted",
        ),
        local_context=[{
            "title": "approved",
            "text": "private-archive-forgery-sentinel",
            "source_ref": "archive:synthetic-approved-1",
        }],
        owner_ref="owner_synthetic_primary",
        connection_ref=SYNTHETIC_OPENAI_CONNECTION,
        resource_ref="resource_conversation",
        context_resource_ref="resource_archive_ungranted",
        client=client,
    )

    assert result.receipt.context_egress_performed is False
    assert len(client.responses.calls) == 1
    assert "private-archive-forgery-sentinel" not in repr(client.responses.calls[0]["input"])

    forged_text_client = _FakeClient()
    with pytest.raises(ProviderEgressDenied):
        complete_with_provider(
            "Question",
            provider="openai",
            allow_provider_egress=True,
            authorization=replace(
                _authorization(),
                resource_ref="resource_conversation_ungranted",
            ),
            owner_ref="owner_synthetic_primary",
            connection_ref=SYNTHETIC_OPENAI_CONNECTION,
            resource_ref="resource_conversation_ungranted",
            client=forged_text_client,
        )

    assert forged_text_client.responses.calls == []


def test_provider_releases_operation_key_after_pretransport_ref_denial(monkeypatch) -> None:
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", SYNTHETIC_OPENAI_KEY)
    registry, request = _registry_and_request(operation_ref="operation_synthetic_release_001")
    authorization = registry.authorize_and_reserve(request)
    client = _FakeClient()

    with pytest.raises(ProviderEgressDenied):
        complete_with_provider(
            "Question",
            provider="openai",
            allow_provider_egress=True,
            authorization=replace(
                authorization,
                operation_ref="operation_synthetic_release_forged",
            ),
            owner_ref="owner_synthetic_primary",
            connection_ref=SYNTHETIC_OPENAI_CONNECTION,
            resource_ref="resource_conversation",
            client=client,
        )

    retry_authorization = registry.authorize_and_reserve(request)
    assert client.responses.calls == []
    assert retry_authorization.allowed is True

    stale_client = _FakeClient()
    with pytest.raises(ProviderEgressDenied):
        complete_with_provider(
            "Question",
            provider="openai",
            allow_provider_egress=True,
            authorization=authorization,
            owner_ref="owner_synthetic_primary",
            connection_ref=SYNTHETIC_OPENAI_CONNECTION,
            resource_ref="resource_conversation",
            client=stale_client,
        )

    retry_client = _FakeClient()
    result = complete_with_provider(
        "Question",
        provider="openai",
        allow_provider_egress=True,
        authorization=retry_authorization,
        owner_ref="owner_synthetic_primary",
        connection_ref=SYNTHETIC_OPENAI_CONNECTION,
        resource_ref="resource_conversation",
        client=retry_client,
    )

    assert stale_client.responses.calls == []
    assert result.status == "ok"
    assert len(retry_client.responses.calls) == 1


def test_abandoned_text_and_context_decisions_cannot_transport_after_rereservation(monkeypatch) -> None:
    monkeypatch.delenv(PROVIDER_ENABLE_ENV, raising=False)
    monkeypatch.setenv(CONTEXT_EGRESS_ENABLE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", SYNTHETIC_OPENAI_KEY)
    operation_ref = "operation_synthetic_context_release_001"
    registry, text_request, context_request = _compound_registry_and_requests(operation_ref=operation_ref)
    first_text = registry.authorize_and_reserve(text_request)
    first_context = registry.authorize_and_reserve(context_request)
    scope = {
        "owner_ref": "owner_synthetic_primary",
        "connection_ref": SYNTHETIC_OPENAI_CONNECTION,
        "resource_ref": "resource_conversation",
        "context_resource_ref": "resource_archive",
    }

    with pytest.raises(ProviderEgressDenied):
        complete_with_provider(
            "Question",
            provider="openai",
            allow_provider_egress=True,
            allow_context_egress=True,
            authorization=first_text,
            context_authorization=first_context,
            local_context=[{
                "title": "approved",
                "text": "private-context-sentinel",
                "source_ref": "archive:synthetic-approved-1",
            }],
            client=_FakeClient(),
            **scope,
        )

    retry_text = registry.authorize_and_reserve(text_request)
    retry_context = registry.authorize_and_reserve(context_request)
    assert retry_text.allowed is True
    assert retry_context.allowed is True
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")

    stale_client = _FakeClient()
    with pytest.raises(ProviderEgressDenied):
        complete_with_provider(
            "Question",
            provider="openai",
            allow_provider_egress=True,
            allow_context_egress=True,
            authorization=first_text,
            context_authorization=first_context,
            local_context=[{
                "title": "approved",
                "text": "private-context-sentinel",
                "source_ref": "archive:synthetic-approved-1",
            }],
            client=stale_client,
            **scope,
        )

    retry_client = _FakeClient()
    result = complete_with_provider(
        "Question",
        provider="openai",
        allow_provider_egress=True,
        allow_context_egress=True,
        authorization=retry_text,
        context_authorization=retry_context,
        local_context=[{
            "title": "approved",
            "text": "private-context-sentinel",
            "source_ref": "archive:synthetic-approved-1",
        }],
        client=retry_client,
        **scope,
    )

    assert stale_client.responses.calls == []
    assert result.receipt.context_egress_performed is True
    assert len(retry_client.responses.calls) == 1
    assert "private-context-sentinel" in repr(retry_client.responses.calls[0]["input"])


def test_abandoned_decision_cannot_race_a_fresh_reservation_to_transport(monkeypatch) -> None:
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", SYNTHETIC_OPENAI_KEY)
    registry, request = _registry_and_request(operation_ref="operation_synthetic_race_001")
    stale_authorization = registry.authorize_and_reserve(request)
    assert stale_authorization.reservation is not None
    stale_authorization.reservation.abandon_before_transport()
    fresh_authorization = registry.authorize_and_reserve(request)
    barrier = Barrier(3)
    outcomes: dict[str, str] = {}
    clients = {"stale": _FakeClient(), "fresh": _FakeClient()}

    def attempt(label, authorization):
        barrier.wait()
        try:
            complete_with_provider(
                "Question",
                provider="openai",
                allow_provider_egress=True,
                authorization=authorization,
                owner_ref="owner_synthetic_primary",
                connection_ref=SYNTHETIC_OPENAI_CONNECTION,
                resource_ref="resource_conversation",
                client=clients[label],
            )
        except ProviderEgressDenied:
            outcomes[label] = "denied"
        else:
            outcomes[label] = "ok"

    stale_thread = Thread(target=attempt, args=("stale", stale_authorization))
    fresh_thread = Thread(target=attempt, args=("fresh", fresh_authorization))
    stale_thread.start()
    fresh_thread.start()
    barrier.wait()
    stale_thread.join()
    fresh_thread.join()

    assert outcomes == {"stale": "denied", "fresh": "ok"}
    assert clients["stale"].responses.calls == []
    assert len(clients["fresh"].responses.calls) == 1


def test_committed_text_reservation_cannot_reopen_before_transport(monkeypatch) -> None:
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", SYNTHETIC_OPENAI_KEY)
    registry, request = _registry_and_request(operation_ref="operation_synthetic_committed_text_001")
    authorization = registry.authorize_and_reserve(request)
    committed = Barrier(2)
    release_transport = Event()
    original_commit = openai_provider._commit_transport_authorizations
    client = _FakeClient()
    errors: list[BaseException] = []

    def pause_after_commit(authorizations):
        result = original_commit(authorizations)
        committed.wait()
        assert release_transport.wait(timeout=5)
        return result

    def transport() -> None:
        try:
            complete_with_provider(
                "Question",
                provider="openai",
                allow_provider_egress=True,
                authorization=authorization,
                owner_ref="owner_synthetic_primary",
                connection_ref=SYNTHETIC_OPENAI_CONNECTION,
                resource_ref="resource_conversation",
                client=client,
            )
        except BaseException as error:
            errors.append(error)

    monkeypatch.setattr(openai_provider, "_commit_transport_authorizations", pause_after_commit)
    thread = Thread(target=transport)
    thread.start()
    committed.wait()
    assert authorization.reservation is not None
    authorization.reservation.abandon_before_transport()
    assert registry.authorize_and_reserve(request).reason == "operation_in_progress"
    release_transport.set()
    thread.join(timeout=5)

    assert thread.is_alive() is False
    assert errors == []
    assert len(client.responses.calls) == 1


def test_committed_text_and_context_reservations_cannot_reopen_before_transport(monkeypatch) -> None:
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    monkeypatch.setenv(CONTEXT_EGRESS_ENABLE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", SYNTHETIC_OPENAI_KEY)
    operation_ref = "operation_synthetic_committed_context_001"
    registry, text_request, context_request = _compound_registry_and_requests(operation_ref=operation_ref)
    authorization = registry.authorize_and_reserve(text_request)
    context_authorization = registry.authorize_and_reserve(context_request)
    committed = Barrier(2)
    release_transport = Event()
    original_commit = openai_provider._commit_transport_authorizations
    client = _FakeClient()
    errors: list[BaseException] = []
    scope = {
        "owner_ref": "owner_synthetic_primary",
        "connection_ref": SYNTHETIC_OPENAI_CONNECTION,
        "resource_ref": "resource_conversation",
        "context_resource_ref": "resource_archive",
    }

    def pause_after_commit(authorizations):
        result = original_commit(authorizations)
        committed.wait()
        assert release_transport.wait(timeout=5)
        return result

    def transport() -> None:
        try:
            complete_with_provider(
                "Question",
                provider="openai",
                allow_provider_egress=True,
                allow_context_egress=True,
                authorization=authorization,
                context_authorization=context_authorization,
                local_context=[{
                    "title": "approved",
                    "text": "private-context-commit-sentinel",
                    "source_ref": "archive:synthetic-approved-1",
                }],
                client=client,
                **scope,
            )
        except BaseException as error:
            errors.append(error)

    monkeypatch.setattr(openai_provider, "_commit_transport_authorizations", pause_after_commit)
    thread = Thread(target=transport)
    thread.start()
    committed.wait()
    assert authorization.reservation is not None
    assert context_authorization.reservation is not None
    authorization.reservation.abandon_before_transport()
    context_authorization.reservation.abandon_before_transport()
    assert registry.authorize_and_reserve(text_request).reason == "operation_in_progress"
    assert registry.authorize_and_reserve(context_request).reason == "operation_in_progress"
    release_transport.set()
    thread.join(timeout=5)

    assert thread.is_alive() is False
    assert errors == []
    assert len(client.responses.calls) == 1
    assert "private-context-commit-sentinel" in repr(client.responses.calls[0]["input"])


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
    registry, text_request, context_request = _compound_registry_and_requests(
        operation_ref="operation_synthetic_context_positive_001"
    )
    result2 = complete_with_provider(
        "Question",
        provider="openai",
        allow_provider_egress=True,
        allow_context_egress=True,
        authorization=registry.authorize_and_reserve(text_request),
        context_authorization=registry.authorize_and_reserve(context_request),
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


def test_context_egress_rejects_same_ref_from_independent_registry_domains(monkeypatch) -> None:
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    monkeypatch.setenv(CONTEXT_EGRESS_ENABLE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", SYNTHETIC_OPENAI_KEY)
    client = _FakeClient()

    with pytest.raises(ProviderEgressDenied):
        complete_with_provider(
            "Question",
            provider="openai",
            allow_provider_egress=True,
            allow_context_egress=True,
            authorization=_authorization(operation_ref="operation_synthetic_cross_registry_001"),
            context_authorization=_authorization(
                capability="model.context_egress",
                resource_ref="resource_archive",
                data_class="private_archive",
                purpose="answer.context",
                operation_ref="operation_synthetic_cross_registry_001",
            ),
            local_context=[{
                "title": "approved",
                "text": "must-not-cross-registry-egress",
                "source_ref": "archive:synthetic-cross-registry-1",
            }],
            client=client,
            owner_ref="owner_synthetic_primary",
            connection_ref=SYNTHETIC_OPENAI_CONNECTION,
            resource_ref="resource_conversation",
            context_resource_ref="resource_archive",
        )

    assert client.responses.calls == []


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
    registry, text_request, context_request = _compound_registry_and_requests(
        operation_ref="operation_synthetic_invalid_context_001"
    )

    result = complete_with_provider(
        "Question",
        provider="openai",
        allow_provider_egress=True,
        allow_context_egress=True,
        authorization=registry.authorize_and_reserve(text_request),
        context_authorization=registry.authorize_and_reserve(context_request),
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


def test_context_transport_blocks_unknown_outcome_retry_until_explicit_reconciliation(monkeypatch) -> None:
    monkeypatch.setenv(PROVIDER_ENABLE_ENV, "true")
    monkeypatch.setenv(CONTEXT_EGRESS_ENABLE_ENV, "true")
    monkeypatch.setenv("OPENAI_API_KEY", SYNTHETIC_OPENAI_KEY)
    captured_calls: list[dict] = []

    def raise_after_capture(**kwargs):
        captured_calls.append(kwargs)
        raise TimeoutError("synthetic unknown outcome")

    client = SimpleNamespace(responses=SimpleNamespace(create=raise_after_capture))
    operation_ref = "operation_synthetic_unknown_001"
    registry, text_request, context_request = _compound_registry_and_requests(operation_ref=operation_ref)
    authorization = registry.authorize_and_reserve(text_request)
    context_authorization = registry.authorize_and_reserve(context_request)
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

    retry_authorization = registry.authorize_and_reserve(text_request)
    retry_context_authorization = registry.authorize_and_reserve(context_request)
    assert retry_authorization.reason == "operation_outcome_unknown"
    assert retry_context_authorization.reason == "operation_outcome_unknown"

    assert registry.reconcile_unknown_operation(operation_ref, delivery_outcome="not_delivered")
    assert registry.authorize_and_reserve(text_request).allowed is True
    assert registry.authorize_and_reserve(context_request).allowed is True
