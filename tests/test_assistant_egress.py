"""PA-02 text and voice egress boundaries, using fake clients and synthetic grants."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bot import bot as bot_runtime
from bot import legacy_handlers
from bot import prm_handlers
from bot.voice import VoiceTranscriptionUnavailable, transcribe_audio_file, transcribe_telegram_voice
import llm.client as anthropic_client
import llm.openai_provider as openai_provider
from llm.openai_provider import OpenAIProviderError, ProviderEgressDenied, complete_with_provider
from tests.test_assistant_permissions import NOW, make_grant, make_request
from prm.capabilities import CapabilityRegistry

OWNER_SCOPE = {
    "owner_ref": "owner_synthetic_primary",
    "connection_ref": None,
    "resource_ref": "resource_conversation",
}
SYNTHETIC_TELEGRAM_TOKEN = "synthetic-telegram-token"
SYNTHETIC_OPENAI_KEY = "synthetic-openai-key"
SYNTHETIC_OPENAI_CONNECTION = openai_provider._openai_connection_ref(SYNTHETIC_OPENAI_KEY)
assert SYNTHETIC_OPENAI_CONNECTION is not None

OWNER_SCOPE["connection_ref"] = SYNTHETIC_OPENAI_CONNECTION


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
        connection_ref=OWNER_SCOPE["connection_ref"],
    )
    request = make_request(
        capability=capability,
        resource_ref=resource_ref,
        data_class=data_class,
        purpose=purpose,
        connection_ref=OWNER_SCOPE["connection_ref"],
    )
    return CapabilityRegistry((grant,)).authorize_and_reserve(request, now=NOW)


def _reserved_decision_with_registry(*, capability="model.generate", resource_ref="resource_conversation"):
    grant = make_grant(
        capability=capability,
        resource_ref=resource_ref,
        connection_ref=OWNER_SCOPE["connection_ref"],
    )
    registry = CapabilityRegistry((grant,))
    return registry, grant, registry.authorize_and_reserve(
        make_request(
            capability=capability,
            resource_ref=resource_ref,
            connection_ref=OWNER_SCOPE["connection_ref"],
        ),
        now=NOW,
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


def _utd_draft_decision_with_registry():
    grant = make_grant(
        grant_id="grant_synthetic_utd_draft",
        owner_ref="owner_telegram_42",
        capability="assistant.utd_draft",
        resource_ref="42",
        operation="write",
        data_class="user_provided",
        providers=("provider_local",),
        purpose="utd.draft",
    )
    request = make_request(
        owner_ref="owner_telegram_42",
        capability="assistant.utd_draft",
        resource_ref="42",
        operation="write",
        data_class="user_provided",
        provider_ref="provider_local",
        purpose="utd.draft",
    )
    registry = CapabilityRegistry((grant,))
    return registry, grant, registry.authorize_and_reserve(request, now=NOW)


def _utd_draft_decision():
    return _utd_draft_decision_with_registry()[2]


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
    synthetic_key = "synthetic-anthropic-key"
    connection_ref = anthropic_client._anthropic_connection_ref(synthetic_key)
    assert connection_ref is not None
    grant = make_grant(providers=("provider_anthropic",), connection_ref=connection_ref)
    request = make_request(provider_ref="provider_anthropic", connection_ref=connection_ref)
    decision = CapabilityRegistry((grant,)).authorize_and_reserve(request, now=NOW)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("ANTHROPIC_API_KEY", synthetic_key)
        with patch.object(anthropic_client, "_get_client", return_value=fake_client):
            assert anthropic_client.complete(
                prompt="Synthetic question",
                authorization=decision,
                owner_ref=OWNER_SCOPE["owner_ref"],
                connection_ref=connection_ref,
                resource_ref=OWNER_SCOPE["resource_ref"],
            ) == "synthetic answer"


def test_prm_result_delivery_requires_a_fresh_private_owner_grant_before_fake_telegram_send(monkeypatch):
    sent: list[str] = []
    _registry, _grant, decision = _delivery_decision()
    monkeypatch.setattr(
        prm_handlers,
        "_send_text_internal",
        lambda **kwargs: sent.append(str(kwargs["text"])),
    )
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
    monkeypatch.setattr(
        prm_handlers,
        "_send_text_internal",
        lambda **kwargs: sent.append(str(kwargs["text"])),
    )
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
    monkeypatch.setattr(
        prm_handlers,
        "_send_text_internal",
        lambda **kwargs: sent.append(str(kwargs["text"])),
    )
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
    monkeypatch.setattr(
        prm_handlers,
        "_send_text_internal",
        lambda **kwargs: sent.append(str(kwargs["text"])),
    )
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
    monkeypatch.setattr(
        prm_handlers,
        "_send_text_internal",
        lambda **kwargs: sent.append(str(kwargs["text"])),
    )
    monkeypatch.setattr(prm_handlers, "_token", lambda: SYNTHETIC_TELEGRAM_TOKEN)

    prm_handlers._send_chunks(
        "42",
        "private synthetic archive result",
        reply_markup=None,
        actor_id="42",
        owner_chat_id="42",
    )

    assert sent == []


def test_shared_prm_sender_default_denies_voice_or_utd_text_before_fake_telegram_send(monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(
        prm_handlers,
        "_send_text_internal",
        lambda **kwargs: sent.append(str(kwargs["text"])),
    )

    prm_handlers.send_message(
        SYNTHETIC_TELEGRAM_TOKEN,
        "42",
        "voice-or-utd status",
        actor_id="42",
        owner_chat_id="42",
    )

    assert sent == []


def test_private_privacy_route_delivers_actual_default_deny_scope_only_with_a_delivery_grant(monkeypatch, tmp_path):
    sent: list[str] = []
    _registry, _grant, decision = _delivery_decision()
    monkeypatch.setattr(prm_handlers, "_token", lambda: SYNTHETIC_TELEGRAM_TOKEN)
    monkeypatch.setattr(
        prm_handlers,
        "_send_text_internal",
        lambda **kwargs: sent.append(str(kwargs["text"])),
    )

    prm_handlers.dispatch_prm_command(
        "42",
        "/privacy",
        SimpleNamespace(db_path=str(tmp_path / "synthetic.db")),
        actor_id="42",
        owner_chat_id="42",
        delivery_authorizations=(decision,),
    )

    assert len(sent) == 1
    assert "нет активных разрешений" in sent[0]


def test_utd_draft_requires_local_write_reservation_before_onboarding(monkeypatch, tmp_path):
    started: list[str] = []
    monkeypatch.setattr(
        prm_handlers,
        "start_utd_profile_onboarding",
        lambda _db_path, *, chat_id, seed_text: started.append(f"{chat_id}:{seed_text}") or {"message": "draft"},
    )
    monkeypatch.setattr(prm_handlers, "_token", lambda: SYNTHETIC_TELEGRAM_TOKEN)

    prm_handlers.dispatch_prm_command(
        "42",
        "/utd Настроить мой UTD-профиль",
        SimpleNamespace(db_path=str(tmp_path / "synthetic.db")),
        actor_id="42",
        owner_chat_id="42",
        utd_draft_authorization=_utd_draft_decision(),
    )

    assert started == ["42:Настроить мой UTD-профиль"]


@pytest.mark.parametrize("change", ["revoke", "expire", "revision", "wrong_owner"])
def test_utd_draft_rechecks_current_authorization_before_any_local_write(
    monkeypatch,
    tmp_path,
    change,
):
    started: list[str] = []
    registry, grant, decision = _utd_draft_decision_with_registry()
    if change == "revoke":
        registry.revoke_grant(grant.grant_id)
    elif change == "expire":
        registry.expire_grant(grant.grant_id)
    elif change == "revision":
        registry.replace_grant(replace(grant, revision=grant.revision + 1))
    monkeypatch.setattr(
        prm_handlers,
        "start_utd_profile_onboarding",
        lambda *_args, **_kwargs: started.append("must-not-write"),
    )
    chat_id = "43" if change == "wrong_owner" else "42"

    prm_handlers.dispatch_prm_command(
        chat_id,
        "/utd Настроить мой UTD-профиль",
        SimpleNamespace(db_path=str(tmp_path / "synthetic.db")),
        actor_id=chat_id,
        owner_chat_id=chat_id,
        utd_draft_authorization=decision,
    )

    assert started == []


def test_pa_safe_ops_deny_before_ungated_legacy_handler_dispatch(monkeypatch, tmp_path):
    legacy_call = []
    monkeypatch.setattr(legacy_handlers, "handle_status", lambda *_args: legacy_call.append("status"))

    prm_handlers.dispatch_prm_command(
        "42",
        "/status",
        SimpleNamespace(db_path=str(tmp_path / "synthetic.db")),
        actor_id="42",
        owner_chat_id="42",
    )

    assert legacy_call == []


def test_prm_private_voice_ingress_uses_its_bounded_return_envelope_at_the_final_sender(
    monkeypatch,
):
    sent: list[str] = []
    update = {
        "update_id": 1,
        "message": {"chat": {"id": 42}, "from": {"id": 42}, "voice": {"file_id": "voice-1"}},
    }
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", SYNTHETIC_TELEGRAM_TOKEN)
    monkeypatch.setenv("TELEGRAM_OWNER_CHAT_ID", "42")
    monkeypatch.setattr(bot_runtime, "_install_signal_handlers", lambda state: setattr(state, "stop_requested", True))
    monkeypatch.setattr(bot_runtime, "_telegram_get_updates", lambda **_kwargs: [update])
    monkeypatch.setattr(
        bot_runtime,
        "transcribe_telegram_voice",
        lambda **_kwargs: (_ for _ in ()).throw(VoiceTranscriptionUnavailable("synthetic unavailable")),
    )
    monkeypatch.setattr(
        prm_handlers,
        "_send_text_internal",
        lambda **kwargs: sent.append(str(kwargs["text"])),
    )

    bot_runtime.run_bot(SimpleNamespace(), runtime_mode=bot_runtime.BOT_RUNTIME_PRM_ASSISTANT)

    assert len(sent) == 2
    assert "Распознаю" in sent[0]
    assert "обычное текстовое сообщение" in sent[1]


def test_private_return_envelope_is_exactly_bound_and_not_issued_for_another_actor():
    decisions = prm_handlers.issue_private_reply_authorizations(
        token=SYNTHETIC_TELEGRAM_TOKEN,
        chat_id="42",
        actor_id="42",
        owner_chat_id="42",
        maximum_send_count=2,
    )

    assert len(decisions) == 2
    assert all(decision.allowed for decision in decisions)
    assert all(decision.owner_ref == "owner_telegram_42" for decision in decisions)
    assert all(decision.resource_ref == "42" for decision in decisions)
    assert all(decision.capability == "assistant.result_delivery" for decision in decisions)
    assert all(decision.purpose == "answer.delivery" for decision in decisions)
    assert prm_handlers.issue_private_reply_authorizations(
        token=SYNTHETIC_TELEGRAM_TOKEN,
        chat_id="42",
        actor_id="43",
        owner_chat_id="42",
    ) == ()


def test_prm_private_text_ingress_renders_default_deny_privacy_without_a_durable_grant(
    monkeypatch,
    tmp_path,
):
    sent: list[str] = []
    update = {
        "update_id": 2,
        "message": {"chat": {"id": 42}, "from": {"id": 42}, "text": "/privacy"},
    }
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", SYNTHETIC_TELEGRAM_TOKEN)
    monkeypatch.setenv("TELEGRAM_OWNER_CHAT_ID", "42")
    monkeypatch.setattr(bot_runtime, "_install_signal_handlers", lambda state: setattr(state, "stop_requested", True))
    monkeypatch.setattr(bot_runtime, "_telegram_get_updates", lambda **_kwargs: [update])
    monkeypatch.setattr(
        prm_handlers,
        "_send_text_internal",
        lambda **kwargs: sent.append(str(kwargs["text"])),
    )

    bot_runtime.run_bot(
        SimpleNamespace(db_path=str(tmp_path / "synthetic.db")),
        runtime_mode=bot_runtime.BOT_RUNTIME_PRM_ASSISTANT,
    )

    assert len(sent) == 1
    assert "нет активных разрешений" in sent[0]


def test_prm_private_utd_command_denies_without_a_runtime_local_write_authorization(
    monkeypatch,
    tmp_path,
):
    started: list[str] = []
    update = {
        "update_id": 21,
        "message": {"chat": {"id": 42}, "from": {"id": 42}, "text": "/utd Мой профиль"},
    }
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", SYNTHETIC_TELEGRAM_TOKEN)
    monkeypatch.setenv("TELEGRAM_OWNER_CHAT_ID", "42")
    monkeypatch.setattr(bot_runtime, "_install_signal_handlers", lambda state: setattr(state, "stop_requested", True))
    monkeypatch.setattr(bot_runtime, "_telegram_get_updates", lambda **_kwargs: [update])
    monkeypatch.setattr(
        prm_handlers,
        "start_utd_profile_onboarding",
        lambda _db_path, *, chat_id, seed_text: started.append(f"{chat_id}:{seed_text}"),
    )

    bot_runtime.run_bot(
        SimpleNamespace(db_path=str(tmp_path / "synthetic.db")),
        runtime_mode=bot_runtime.BOT_RUNTIME_PRM_ASSISTANT,
    )

    assert started == []


@pytest.mark.parametrize("callback_data", [
    "utdp:synthetic:preview",
    "utdc:synthetic:confirm",
    "utds:cancel:confirm",
    "utdw:synthetic:useful",
])
def test_prm_runtime_denies_all_utd_callback_mutations_before_the_legacy_facade(
    monkeypatch,
    tmp_path,
    callback_data,
):
    mutations: list[str] = []
    acknowledgements: list[str] = []
    monkeypatch.setattr(
        bot_runtime,
        "handle_prm_post_answer_callback",
        lambda _settings, data, **_kwargs: mutations.append(data),
    )
    monkeypatch.setattr(
        bot_runtime,
        "_telegram_answer_callback",
        lambda _token, _callback_id, text: acknowledgements.append(text),
    )

    bot_runtime._handle_callback(
        {
            "id": "callback-utd",
            "from": {"id": 42},
            "message": {"chat": {"id": 42}},
            "data": callback_data,
        },
        token=SYNTHETIC_TELEGRAM_TOKEN,
        owner_chat_id="42",
        settings=SimpleNamespace(db_path=str(tmp_path / "synthetic.db")),
        runtime_mode=bot_runtime.BOT_RUNTIME_PRM_ASSISTANT,
    )

    assert mutations == []
    assert acknowledgements == ["Action unavailable"]


def test_prm_callback_followup_uses_the_same_private_return_envelope(monkeypatch, tmp_path):
    sent: list[str] = []
    monkeypatch.setattr(prm_handlers, "_send_text_internal", lambda **kwargs: sent.append(str(kwargs["text"])))
    monkeypatch.setattr(bot_runtime, "validate_prm_post_answer_callback", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        bot_runtime,
        "apply_validated_prm_post_answer_callback",
        lambda *_args, **_kwargs: {"status": "ok", "message": "Synthetic callback follow-up."},
    )
    monkeypatch.setattr(bot_runtime, "_telegram_answer_callback", lambda *_args, **_kwargs: None)

    bot_runtime._handle_callback(
        {
            "id": "callback-1",
            "from": {"id": 42},
            "message": {"chat": {"id": 42}},
            "data": "prma:opaque:n",
        },
        token=SYNTHETIC_TELEGRAM_TOKEN,
        owner_chat_id="42",
        settings=SimpleNamespace(db_path=str(tmp_path / "synthetic.db")),
        runtime_mode=bot_runtime.BOT_RUNTIME_PRM_ASSISTANT,
    )

    assert sent == ["Synthetic callback follow-up."]


def test_prm_callback_acknowledgement_needs_an_exact_private_reply_envelope(monkeypatch, tmp_path):
    acknowledgements: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        bot_runtime,
        "validate_prm_post_answer_callback",
        lambda *_args, **_kwargs: bot_runtime.UnavailablePrmAction(),
    )
    monkeypatch.setattr(
        bot_runtime,
        "_telegram_answer_callback",
        lambda token, callback_id, text: acknowledgements.append((token, callback_id, text)),
    )

    bot_runtime._handle_callback(
        {
            "id": "callback-mismatched",
            "from": {"id": 43},
            "message": {"chat": {"id": 42}},
            "data": "prma:opaque:n",
        },
        token=SYNTHETIC_TELEGRAM_TOKEN,
        owner_chat_id="42",
        settings=SimpleNamespace(db_path=str(tmp_path / "synthetic.db")),
        runtime_mode=bot_runtime.BOT_RUNTIME_PRM_ASSISTANT,
    )

    assert acknowledgements == []


def test_prm_callback_acknowledgement_uses_an_exact_private_reply_envelope(monkeypatch, tmp_path):
    acknowledgements: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        bot_runtime,
        "validate_prm_post_answer_callback",
        lambda *_args, **_kwargs: bot_runtime.UnavailablePrmAction(),
    )
    monkeypatch.setattr(
        bot_runtime,
        "_telegram_answer_callback",
        lambda token, callback_id, text: acknowledgements.append((token, callback_id, text)),
    )

    bot_runtime._handle_callback(
        {
            "id": "callback-private",
            "from": {"id": 42},
            "message": {"chat": {"id": 42}},
            "data": "prma:opaque:n",
        },
        token=SYNTHETIC_TELEGRAM_TOKEN,
        owner_chat_id="42",
        settings=SimpleNamespace(db_path=str(tmp_path / "synthetic.db")),
        runtime_mode=bot_runtime.BOT_RUNTIME_PRM_ASSISTANT,
    )

    assert acknowledgements == [
        (SYNTHETIC_TELEGRAM_TOKEN, "callback-private", "Action unavailable")
    ]


def test_prm_rejects_private_chat_with_a_mismatched_sender_before_dispatch(monkeypatch, tmp_path):
    dispatched: list[str] = []
    update = {
        "update_id": 3,
        "message": {"chat": {"id": 42}, "from": {"id": 43}, "text": "/privacy"},
    }
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", SYNTHETIC_TELEGRAM_TOKEN)
    monkeypatch.setenv("TELEGRAM_OWNER_CHAT_ID", "42")
    monkeypatch.setattr(bot_runtime, "_install_signal_handlers", lambda state: setattr(state, "stop_requested", True))
    monkeypatch.setattr(bot_runtime, "_telegram_get_updates", lambda **_kwargs: [update])
    monkeypatch.setattr(bot_runtime, "dispatch_command", lambda **kwargs: dispatched.append(str(kwargs["text"])))

    bot_runtime.run_bot(
        SimpleNamespace(db_path=str(tmp_path / "synthetic.db")),
        runtime_mode=bot_runtime.BOT_RUNTIME_PRM_ASSISTANT,
    )

    assert dispatched == []


def test_private_context_needs_its_own_data_class_grant(monkeypatch):
    client = _FakeClient()
    monkeypatch.setenv("PRM_OPENAI_PROVIDER_ENABLED", "true")
    monkeypatch.setenv("PRM_OPENAI_CONTEXT_EGRESS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", SYNTHETIC_OPENAI_KEY)

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
