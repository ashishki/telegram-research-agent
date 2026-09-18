"""PA-02 text and voice egress boundaries, using fake clients and synthetic grants."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bot.voice import VoiceTranscriptionUnavailable, transcribe_audio_file, transcribe_telegram_voice
import llm.client as anthropic_client
from llm.openai_provider import ProviderEgressDenied, complete_with_provider
from tests.test_assistant_permissions import NOW, make_grant, make_request
from prm.capabilities import CapabilityRegistry


class _FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text="synthetic provider answer")


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


def _decision(*, capability="model.generate", resource_ref="resource_conversation", data_class="user_provided"):
    grant = make_grant(capability=capability, resource_ref=resource_ref, data_class=data_class)
    request = make_request(capability=capability, resource_ref=resource_ref, data_class=data_class)
    return CapabilityRegistry((grant,)).authorize_and_reserve(request, now=NOW)


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
        assert anthropic_client.complete(prompt="Synthetic question", authorization=decision) == "synthetic answer"


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
        local_context=[{"title": "synthetic", "text": "private synthetic context"}],
        client=client,
    )

    assert result.receipt.context_egress_performed is False
    assert "private synthetic context" not in repr(client.responses.calls[0]["input"])

    context_decision = _decision(
        capability="model.context_egress",
        resource_ref="resource_archive",
        data_class="private_archive",
    )
    client_with_context = _FakeClient()
    result_with_context = complete_with_provider(
        "Synthetic question",
        provider="openai",
        allow_provider_egress=True,
        allow_context_egress=True,
        authorization=_decision(),
        context_authorization=context_decision,
        local_context=[{"title": "synthetic", "text": "private synthetic context"}],
        client=client_with_context,
    )

    assert result_with_context.receipt.context_egress_performed is True
    assert "private synthetic context" in repr(client_with_context.responses.calls[0]["input"])


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
