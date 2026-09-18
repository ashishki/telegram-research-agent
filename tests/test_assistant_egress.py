"""PA-02 text and voice egress boundaries, using fake clients and synthetic grants."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bot import prm_handlers
from bot.voice import VoiceTranscriptionUnavailable, transcribe_audio_file, transcribe_telegram_voice
import llm.client as anthropic_client
from llm.openai_provider import OpenAIProviderError, ProviderEgressDenied, complete_with_provider
from tests.test_assistant_permissions import NOW, make_grant, make_request
from prm.capabilities import CapabilityRegistry

OWNER_SCOPE = {
    "owner_ref": "owner_synthetic_primary",
    "connection_ref": None,
    "resource_ref": "resource_conversation",
}
SYNTHETIC_TELEGRAM_TOKEN = "synthetic-telegram-token"


class _FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text="synthetic provider answer")


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


def _decision(
    *,
    capability="model.generate",
    resource_ref="resource_conversation",
    data_class="user_provided",
    purpose="answer.request",
):
    grant = make_grant(
        capability=capability,
        resource_ref=resource_ref,
        data_class=data_class,
        purpose=purpose,
    )
    request = make_request(
        capability=capability,
        resource_ref=resource_ref,
        data_class=data_class,
        purpose=purpose,
    )
    return CapabilityRegistry((grant,)).authorize_and_reserve(request, now=NOW)


def _reserved_decision_with_registry(*, capability="model.generate", resource_ref="resource_conversation"):
    grant = make_grant(capability=capability, resource_ref=resource_ref)
    registry = CapabilityRegistry((grant,))
    return registry, grant, registry.authorize_and_reserve(
        make_request(capability=capability, resource_ref=resource_ref), now=NOW
    )


def _delivery_decision(
    *,
    registry: CapabilityRegistry | None = None,
    purpose: str = "answer.delivery",
    connection_ref: str | None = None,
):
    active_connection_ref = connection_ref or prm_handlers._telegram_connection_ref(SYNTHETIC_TELEGRAM_TOKEN)
    assert active_connection_ref is not None
    grant = make_grant(
        grant_id="grant_synthetic_delivery",
        owner_ref="owner_telegram_42",
        capability="assistant.result_delivery",
        resource_ref="42",
        operation="deliver",
        data_class="private_archive",
        providers=("provider_telegram",),
        purpose=purpose,
        connection_ref=active_connection_ref,
    )
    active_registry = registry or CapabilityRegistry((grant,))
    return active_registry, grant, active_registry.authorize_and_reserve(
        make_request(
            owner_ref="owner_telegram_42",
            capability="assistant.result_delivery",
            resource_ref="42",
            operation="deliver",
            data_class="private_archive",
            provider_ref="provider_telegram",
            purpose=purpose,
            connection_ref=active_connection_ref,
        ),
        now=NOW,
    )


def test_configured_provider_switch_without_grant_makes_no_text_egress(monkeypatch):
    client = _FakeClient()
    monkeypatch.setenv("PRM_OPENAI_PROVIDER_ENABLED", "true")

    with pytest.raises(ProviderEgressDenied):
        complete_with_provider(
            "Synthetic question",
            provider="openai",
            allow_provider_egress=True,
            authorization=None,
            client=client,
        )

    assert client.responses.calls == []


def test_anthropic_text_client_denies_before_client_creation_without_a_grant():
    fake_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_kwargs: pytest.fail("must not call provider")))

    with patch.object(anthropic_client, "_get_client", return_value=fake_client):
        with pytest.raises(anthropic_client.LLMError):
            anthropic_client.complete(prompt="Synthetic question", authorization=None)


def test_anthropic_text_client_uses_only_a_matching_provider_grant():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="synthetic answer")],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    fake_client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_kwargs: response))
    grant = make_grant(providers=("provider_anthropic",))
    request = make_request(provider_ref="provider_anthropic")
    decision = CapabilityRegistry((grant,)).authorize_and_reserve(request, now=NOW)

    with patch.object(anthropic_client, "_get_client", return_value=fake_client):
        assert anthropic_client.complete(
            prompt="Synthetic question", authorization=decision, **OWNER_SCOPE
        ) == "synthetic answer"


def test_prm_result_delivery_requires_a_fresh_private_owner_grant_before_fake_telegram_send(monkeypatch):
    sent: list[str] = []
    _registry, _grant, decision = _delivery_decision()
    monkeypatch.setattr(prm_handlers, "send_message", lambda _token, _chat, text, **_kwargs: sent.append(text))
    monkeypatch.setattr(prm_handlers, "_token", lambda: SYNTHETIC_TELEGRAM_TOKEN)

    prm_handlers._send_chunks(
        "42",
        "private synthetic archive result",
        reply_markup=None,
        actor_id="42",
        owner_chat_id="42",
        delivery_authorizations=(decision,),
    )

    assert sent == ["private synthetic archive result"]


def test_prm_result_delivery_rechecks_revocation_before_fake_telegram_send(monkeypatch):
    sent: list[str] = []
    registry, grant, decision = _delivery_decision()
    registry.revoke_grant(grant.grant_id)
    monkeypatch.setattr(prm_handlers, "send_message", lambda _token, _chat, text, **_kwargs: sent.append(text))
    monkeypatch.setattr(prm_handlers, "_token", lambda: SYNTHETIC_TELEGRAM_TOKEN)

    prm_handlers._send_chunks(
        "42",
        "private synthetic archive result",
        reply_markup=None,
        actor_id="42",
        owner_chat_id="42",
        delivery_authorizations=(decision,),
    )

    assert sent == []


def test_prm_result_delivery_rejects_another_purpose_before_fake_telegram_send(monkeypatch):
    sent: list[str] = []
    _registry, _grant, decision = _delivery_decision(purpose="answer.request")
    monkeypatch.setattr(prm_handlers, "send_message", lambda _token, _chat, text, **_kwargs: sent.append(text))
    monkeypatch.setattr(prm_handlers, "_token", lambda: SYNTHETIC_TELEGRAM_TOKEN)

    prm_handlers._send_chunks(
        "42",
        "private synthetic archive result",
        reply_markup=None,
        actor_id="42",
        owner_chat_id="42",
        delivery_authorizations=(decision,),
    )

    assert sent == []


def test_prm_result_delivery_rejects_another_telegram_connection_before_fake_sender(monkeypatch):
    sent: list[str] = []
    _registry, _grant, decision = _delivery_decision(connection_ref="connection_telegram_other")
    monkeypatch.setattr(prm_handlers, "send_message", lambda _token, _chat, text, **_kwargs: sent.append(text))
    monkeypatch.setattr(prm_handlers, "_token", lambda: SYNTHETIC_TELEGRAM_TOKEN)

    prm_handlers._send_chunks(
        "42",
        "private synthetic archive result",
        reply_markup=None,
        actor_id="42",
        owner_chat_id="42",
        delivery_authorizations=(decision,),
    )

    assert sent == []


def test_prm_result_delivery_default_denies_before_fake_telegram_send(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(prm_handlers, "send_message", lambda _token, _chat, text, **_kwargs: sent.append(text))
    monkeypatch.setattr(prm_handlers, "_token", lambda: SYNTHETIC_TELEGRAM_TOKEN)

    prm_handlers._send_chunks(
        "42",
        "private synthetic archive result",
        reply_markup=None,
        actor_id="42",
        owner_chat_id="42",
    )

    assert sent == []


def test_private_context_needs_its_own_data_class_grant(monkeypatch):
    client = _FakeClient()
    monkeypatch.setenv("PRM_OPENAI_PROVIDER_ENABLED", "true")
    monkeypatch.setenv("PRM_OPENAI_CONTEXT_EGRESS_ENABLED", "true")

    result = complete_with_provider(
        "Synthetic question",
        provider="openai",
        allow_provider_egress=True,
        allow_context_egress=True,
        authorization=_decision(),
        context_authorization=None,
        **OWNER_SCOPE,
        local_context=[{"title": "synthetic", "text": "private synthetic context"}],
        client=client,
    )

    assert result.receipt.context_egress_performed is False
    assert "private synthetic context" not in repr(client.responses.calls[0]["input"])

    context_decision = _decision(
        capability="model.context_egress",
        resource_ref="resource_archive",
        data_class="private_archive",
        purpose="answer.context",
    )
    client_with_context = _FakeClient()
    result_with_context = complete_with_provider(
        "Synthetic question",
        provider="openai",
        allow_provider_egress=True,
        allow_context_egress=True,
        authorization=_decision(),
        context_authorization=context_decision,
        context_resource_ref="resource_archive",
        local_context=[{"title": "synthetic", "text": "private synthetic context"}],
        client=client_with_context,
        **OWNER_SCOPE,
    )

    assert result_with_context.receipt.context_egress_performed is True
    assert "private synthetic context" in repr(client_with_context.responses.calls[0]["input"])


@pytest.mark.parametrize("change", ["revoke", "expire", "revision"])
def test_openai_adapter_rechecks_current_grant_state_before_transport(monkeypatch, change):
    registry, grant, decision = _reserved_decision_with_registry()
    if change == "revoke":
        registry.revoke_grant(grant.grant_id)
    elif change == "expire":
        registry.expire_grant(grant.grant_id)
    else:
        registry.replace_grant(replace(grant, revision=grant.revision + 1))
    client = _FakeClient()
    monkeypatch.setenv("PRM_OPENAI_PROVIDER_ENABLED", "true")

    with pytest.raises(ProviderEgressDenied):
        complete_with_provider(
            "Synthetic question",
            provider="openai",
            allow_provider_egress=True,
            authorization=decision,
            client=client,
            **OWNER_SCOPE,
        )

    assert client.responses.calls == []


def test_openai_adapter_rejects_cross_owner_or_resource_substitution(monkeypatch):
    monkeypatch.setenv("PRM_OPENAI_PROVIDER_ENABLED", "true")
    for substituted_scope in (
        {**OWNER_SCOPE, "owner_ref": "owner_synthetic_other"},
        {**OWNER_SCOPE, "connection_ref": "connection_synthetic_other"},
        {**OWNER_SCOPE, "resource_ref": "resource_other"},
    ):
        client = _FakeClient()
        with pytest.raises(ProviderEgressDenied):
            complete_with_provider(
                "Synthetic question",
                provider="openai",
                allow_provider_egress=True,
                authorization=_decision(),
                client=client,
                **substituted_scope,
            )
        assert client.responses.calls == []


def test_openai_adapter_redacts_provider_exception_chain(monkeypatch):
    def raise_provider_error(**_kwargs):
        raise RuntimeError("provider-payload-sentinel")

    client = SimpleNamespace(responses=SimpleNamespace(create=raise_provider_error))
    monkeypatch.setenv("PRM_OPENAI_PROVIDER_ENABLED", "true")

    with pytest.raises(OpenAIProviderError) as error:
        complete_with_provider(
            "private-prompt-sentinel",
            provider="openai",
            allow_provider_egress=True,
            authorization=_decision(),
            client=client,
            **OWNER_SCOPE,
        )

    assert "provider-payload-sentinel" not in str(error.value)
    assert error.value.__cause__ is None


def test_voice_adapter_binds_download_and_transcription_to_actual_file_resource():
    download_grant = make_grant(
        capability="media.voice_download",
        resource_ref="resource_alpha",
        operation="read",
        providers=("provider_telegram",),
        purpose="voice.transcription",
    )
    transcription_grant = make_grant(
        grant_id="grant_synthetic_transcription",
        capability="media.transcribe",
        resource_ref="resource_alpha",
        operation="model_egress",
        providers=("provider_openai",),
        purpose="voice.transcription",
    )
    download_authorization = CapabilityRegistry((download_grant,)).authorize_and_reserve(
        make_request(
            capability="media.voice_download",
            resource_ref="resource_alpha",
            operation="read",
            provider_ref="provider_telegram",
            purpose="voice.transcription",
        ),
        now=NOW,
    )
    transcription_authorization = CapabilityRegistry((transcription_grant,)).authorize_and_reserve(
        make_request(
            capability="media.transcribe",
            resource_ref="resource_alpha",
            operation="model_egress",
            provider_ref="provider_openai",
            purpose="voice.transcription",
        ),
        now=NOW,
    )

    with patch("bot.voice.request.urlopen") as urlopen:
        with pytest.raises(VoiceTranscriptionUnavailable):
            transcribe_telegram_voice(
                token="synthetic-bot-token",
                file_id="resource_beta",
                download_authorization=download_authorization,
                transcription_authorization=transcription_authorization,
                owner_ref="owner_synthetic_primary",
            )

    urlopen.assert_not_called()


def test_voice_download_and_transcription_fail_before_network_without_separate_grants(tmp_path):
    audio_path = tmp_path / "synthetic.ogg"
    audio_path.write_bytes(b"synthetic audio")

    with patch("bot.voice.request.urlopen") as urlopen:
        with pytest.raises(VoiceTranscriptionUnavailable):
            transcribe_audio_file(str(audio_path), transcription_authorization=None)
        with pytest.raises(VoiceTranscriptionUnavailable):
            transcribe_telegram_voice(
                token="synthetic-bot-token",
                file_id="synthetic-file",
                download_authorization=None,
                transcription_authorization=None,
            )

    urlopen.assert_not_called()
