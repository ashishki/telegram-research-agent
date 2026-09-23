import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from assistant.prm_post_answer_actions import PRM_ACTION_PREFIX, build_post_answer_actions
from bot import bot as bot_runtime
from bot import callbacks, handlers, legacy_handlers, prm_handlers
from bot.runtime import BOT_RUNTIME_LEGACY, BOT_RUNTIME_PRM_ASSISTANT, normalize_bot_runtime_mode
from bot.prm_handlers import PRM_SAFE_COMMANDS
from db.migrate import run_migrations
from prm.capabilities import AuthorizationRequest, CapabilityGrant, CapabilityRegistry, ProviderPolicy
from prm.archive_synthesis_transport import ArchiveSynthesisReceipt, ArchiveSynthesisTransportResult
from prm.contracts import ArchiveSynthesisAccess, AssistantResult, ModelEgressAccess


def _model_access() -> ModelEgressAccess:
    now = datetime.now(timezone.utc)
    grant = CapabilityGrant(
        grant_id="grant_synthetic_chat",
        owner_ref="owner_synthetic_primary",
        connection_ref="connection_synthetic_model",
        capability="model.generate",
        resource_refs=("resource_conversation",),
        operations=("model_egress",),
        data_classes=("user_provided",),
        purpose="answer.request",
        provider_policy=ProviderPolicy(("provider_anthropic",)),
        issued_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=5),
        revision=1,
    )
    registry = CapabilityRegistry((grant,))
    decision = registry.authorize_and_reserve(AuthorizationRequest(
        owner_ref=grant.owner_ref,
        connection_ref=grant.connection_ref,
        capability=grant.capability,
        resource_ref="resource_conversation",
        operation="model_egress",
        data_class="user_provided",
        provider_ref="provider_anthropic",
        purpose="answer.request",
        expected_grant_revision=1,
        operation_ref="operation_synthetic_chat",
    ))
    return ModelEgressAccess(
        authorization=decision,
        owner_ref=grant.owner_ref,
        connection_ref=grant.connection_ref or "",
        resource_ref="resource_conversation",
    )


def _archive_synthesis_access() -> ArchiveSynthesisAccess:
    now = datetime.now(timezone.utc)
    connection_ref = "connection_synthetic_archive"
    text = CapabilityGrant(
        grant_id="grant_synthetic_archive_text",
        owner_ref="owner_synthetic_primary",
        connection_ref=connection_ref,
        capability="model.generate",
        resource_refs=("resource_conversation",),
        operations=("model_egress",),
        data_classes=("user_provided",),
        purpose="answer.request",
        provider_policy=ProviderPolicy(("provider_openai",), maximum_request_count=2),
        issued_at=now - timedelta(minutes=1), expires_at=now + timedelta(minutes=5), revision=1,
    )
    context = CapabilityGrant(
        grant_id="grant_synthetic_archive_context",
        owner_ref=text.owner_ref,
        connection_ref=connection_ref,
        capability="model.context_egress",
        resource_refs=("resource_archive",),
        operations=("model_egress",),
        data_classes=("private_archive",),
        purpose="answer.context",
        provider_policy=ProviderPolicy(("provider_openai",), maximum_request_count=2),
        issued_at=now - timedelta(minutes=1), expires_at=now + timedelta(minutes=5), revision=1,
    )
    registry = CapabilityRegistry((text, context))
    operation_ref = "operation_synthetic_archive_ingress"
    query = registry.authorize_and_reserve(AuthorizationRequest(
        owner_ref=text.owner_ref, connection_ref=connection_ref, capability="model.generate",
        resource_ref="resource_conversation", operation="model_egress", data_class="user_provided",
        provider_ref="provider_openai", purpose="answer.request", expected_grant_revision=1, operation_ref=operation_ref,
    ))
    archive = registry.authorize_and_reserve(AuthorizationRequest(
        owner_ref=text.owner_ref, connection_ref=connection_ref, capability="model.context_egress",
        resource_ref="resource_archive", operation="model_egress", data_class="private_archive",
        provider_ref="provider_openai", purpose="answer.context", expected_grant_revision=1, operation_ref=operation_ref,
    ))
    return ArchiveSynthesisAccess(
        query_authorization=query, context_authorization=archive, owner_ref=text.owner_ref, connection_ref=connection_ref,
        query_resource_ref="resource_conversation", context_resource_ref="resource_archive",
    )


def test_runtime_mode_is_explicit():
    assert normalize_bot_runtime_mode("prm") == BOT_RUNTIME_PRM_ASSISTANT
    assert normalize_bot_runtime_mode("legacy") == BOT_RUNTIME_LEGACY
    assert bot_runtime.run_bot.__kwdefaults__["runtime_mode"] == BOT_RUNTIME_PRM_ASSISTANT
    assert bot_runtime.run_bot.__kwdefaults__["model_access_provider"] is None
    assert bot_runtime.run_bot.__kwdefaults__["archive_synthesis_access_provider"] is None


def test_active_registry_contains_only_prm_commands():
    assert "/weekly" not in PRM_SAFE_COMMANDS
    assert "/run_digest" not in PRM_SAFE_COMMANDS
    assert {"/auto", "/research", "/brief", "/chat"}.issubset(PRM_SAFE_COMMANDS)


def test_compatibility_dispatch_facades_default_to_gated_prm_assistant():
    assert bot_runtime.dispatch_command.__kwdefaults__["runtime_mode"] == BOT_RUNTIME_PRM_ASSISTANT
    assert handlers.dispatch_command.__kwdefaults__["runtime_mode"] == BOT_RUNTIME_PRM_ASSISTANT


def test_active_bot_ingress_forwards_only_typed_reserved_model_access(monkeypatch, tmp_path):
    access = _model_access()
    forwarded = []
    monkeypatch.setattr(bot_runtime, "dispatch_prm_command", lambda *args, **kwargs: forwarded.append((args, kwargs)))

    bot_runtime.dispatch_command(
        "42", "/chat rewrite this", SimpleNamespace(db_path=str(tmp_path / "memory.db")),
        runtime_mode=BOT_RUNTIME_PRM_ASSISTANT, actor_id="42", owner_chat_id="42", model_access=access,
    )

    assert forwarded[0][1]["model_access"] is access
    assert bot_runtime._model_access_for_private_turn(lambda *_args: access, chat_id="42", actor_id="42", owner_chat_id="42") is access
    assert bot_runtime._model_access_for_private_turn(
        lambda *_args: SimpleNamespace(allowed=True), chat_id="42", actor_id="42", owner_chat_id="42",
    ) is None
    provider_calls = []
    provider = lambda *_args: (provider_calls.append(True) or access)
    assert bot_runtime._model_access_for_command(
        provider, command="/research в архиве про evals", chat_id="42", actor_id="42", owner_chat_id="42",
    ) is None
    assert provider_calls == []
    assert bot_runtime._model_access_for_command(
        provider, command="/chat rewrite this", chat_id="42", actor_id="42", owner_chat_id="42",
    ) is access
    assert provider_calls == [True]


def test_active_bot_ingress_forwards_only_typed_paired_archive_access(monkeypatch, tmp_path):
    access = _archive_synthesis_access()
    forwarded = []
    monkeypatch.setattr(bot_runtime, "dispatch_prm_command", lambda *args, **kwargs: forwarded.append((args, kwargs)))

    bot_runtime.dispatch_command(
        "42", "/research в архиве про agent evals", SimpleNamespace(db_path=str(tmp_path / "memory.db")),
        runtime_mode=BOT_RUNTIME_PRM_ASSISTANT, actor_id="42", owner_chat_id="42", archive_synthesis_access=access,
    )

    assert forwarded[0][1]["archive_synthesis_access"] is access
    assert bot_runtime._archive_synthesis_access_for_private_turn(
        lambda *_args: access, chat_id="42", actor_id="42", owner_chat_id="42",
    ) is access
    calls = []
    provider = lambda *_args: (calls.append(True) or access)
    assert bot_runtime._archive_synthesis_access_for_command(
        provider, command="/chat rewrite this", chat_id="42", actor_id="42", owner_chat_id="42",
    ) is None
    assert bot_runtime._archive_synthesis_access_for_command(
        provider, command="/research какая текущая цена Nvidia сегодня?", chat_id="42", actor_id="42", owner_chat_id="42",
    ) is None
    assert bot_runtime._archive_synthesis_access_for_command(
        provider, command="/research в архиве про agent evals", chat_id="42", actor_id="42", owner_chat_id="42",
    ) is access
    assert calls == [True]


def test_prm_telegram_ingress_drives_actual_source_bound_synthesis(monkeypatch, tmp_path):
    from prm.application import PersonalResearchAssistant

    payload = {
        "status": "ok", "direct_answer": "В архиве есть подтверждённый сигнал.",
        "answer_gate": {"allow_answer": True, "external_verification_required": False, "current_claim_allowed": True},
        "archive_evidence": {"items": [{
            "archive_document_id": "tg:1", "snippet": "Agent evals use task success and groundedness.",
            "source_url": "https://t.me/example/1", "channel_username": "example", "posted_at": "2026-08-01",
        }]},
        "evidence_quality": {"items": [{
            "evidence_id": "tg:1", "support_span": "Agent evals use task success and groundedness.",
            "source_url": "https://t.me/example/1", "source_group_id": "g1", "freshness_status": "fresh",
            "relevance_label": "direct",
        }]},
        "professional_answer": {}, "project_fit": {}, "project_decision": {}, "claim_ledger": {"claims": []},
        "unknowns": [], "next_steps": {}, "receipt": {}, "privacy": {},
    }
    receipt = ArchiveSynthesisReceipt(
        provider="openai", model="gpt-5.6-terra", external_call_attempted=True, external_call_performed=True,
        context_egress_attempted=True, context_egress_performed=True, delivery_outcome="accepted", context_binding_digest="synthetic",
    )
    captured = []

    class CapturingAssistant(PersonalResearchAssistant):
        def answer(self, request):
            result = super().answer(request)
            captured.append((request, result))
            return result

    monkeypatch.setattr("prm.application.answer_memory_research", lambda *args, **kwargs: payload)
    monkeypatch.setattr("prm.application.build_research_facade", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(
        "prm.synthesis.complete_archive_synthesis",
        lambda **_kwargs: ArchiveSynthesisTransportResult(
            text="Agent evals use task success and groundedness (https://t.me/example/1).", receipt=receipt,
        ),
    )
    sent = []
    monkeypatch.setattr(prm_handlers, "PersonalResearchAssistant", CapturingAssistant)
    monkeypatch.setattr(prm_handlers, "_send_chunks", lambda _chat, text, **_kwargs: sent.append(text))
    monkeypatch.setattr(prm_handlers, "_post_answer_action_bundle", lambda *_args, **_kwargs: {"reply_markup": None})

    access = _archive_synthesis_access()
    prm_handlers.dispatch_prm_command(
        "42", "/research в архиве про agent evals", SimpleNamespace(db_path=str(tmp_path / "memory.db")),
        actor_id="42", owner_chat_id="42", archive_synthesis_access=access,
    )

    assert captured[0][0].archive_synthesis_access is access
    assert captured[0][1].payload["retrieval_generation_measurement"]["generation"]["status"] == "generated_verified"
    assert captured[0][1].payload["final_answer_publication"]["fallback_used"] is False
    assert sent == ["Agent evals use task success and groundedness (https://t.me/example/1)."]


def test_prm_entrypoints_do_not_register_post_answer_state_during_pa02(monkeypatch, tmp_path):
    db_path = str(tmp_path / "memory.db")
    monkeypatch.setenv("AGENT_DB_PATH", db_path)
    run_migrations()
    settings = SimpleNamespace(db_path=db_path)
    payload = {
        "answer_gate": {"allow_answer": True}, "question": "agent evals", "direct_answer": "one exact item",
        "archive_evidence": {"items": []}, "archive_contract": {"result_summary": {"direct_count": 1, "partial_count": 0}},
        "primary_intent": "archive_lookup", "response_contract_id": "archive_research.v2",
    }
    valid = prm_handlers._post_answer_action_bundle(
        payload, settings=settings, chat_id="42", actor_id="42", owner_chat_id="42",
    )
    absent = prm_handlers._post_answer_action_bundle(
        payload, settings=settings, chat_id="42",
    )
    malformed = prm_handlers._post_answer_action_bundle(
        payload, settings=settings, chat_id="42", actor_id="042", owner_chat_id="42",
    )
    group = prm_handlers._post_answer_action_bundle(
        payload, settings=settings, chat_id="-10042", actor_id="42", owner_chat_id="42",
    )
    legacy = legacy_handlers._prm_post_answer_markup(payload, settings=settings, chat_id="42")
    forwarded = []
    monkeypatch.setattr(handlers, "dispatch_prm_command", lambda *args, **kwargs: forwarded.append((args, kwargs)))
    handlers.dispatch_command("42", "/research agent evals", settings, runtime_mode=BOT_RUNTIME_PRM_ASSISTANT, actor_id="42", owner_chat_id="42")
    monkeypatch.setattr(bot_runtime, "dispatch_prm_command", lambda *args, **kwargs: forwarded.append((args, kwargs)))
    bot_runtime.dispatch_command("42", "/research agent evals", settings, runtime_mode=BOT_RUNTIME_PRM_ASSISTANT, actor_id="42", owner_chat_id="42")

    # A private tuple identifies a recipient; it is not PA-02 authority to
    # persist an answer-derived action context or receipt.
    assert valid["reply_markup"] is None
    assert absent["reply_markup"] is None
    assert malformed["reply_markup"] is None
    assert group["reply_markup"] is None
    assert legacy is None
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT count(*) FROM prm_post_answer_proposals").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM prm_interaction_ledger").fetchone()[0] == 0
    assert [kwargs for _args, kwargs in forwarded] == [
        {"actor_id": "42", "owner_chat_id": "42"},
        {"actor_id": "42", "owner_chat_id": "42"},
    ]


def test_post_answer_callback_preserves_bound_source_without_reroute(monkeypatch, tmp_path):
    db_path = str(tmp_path / "memory.db")
    monkeypatch.setenv("AGENT_DB_PATH", db_path)
    run_migrations()
    bound = build_post_answer_actions(
        {
            "title": "Agent evals", "direct_answer": "Summary differs from source.",
            "source_refs": ["https://t.me/example/only"],
            "archive_evidence": {"items": [{"source_url": "https://t.me/example/only", "snippet": "Exact bound source."}]},
        },
        db_path=db_path, chat_id="42", actor_id="42", owner_chat_id="42",
    )
    settings = SimpleNamespace(db_path=db_path)
    result = callbacks.handle_prm_post_answer_callback(
        settings, f"{PRM_ACTION_PREFIX}:{bound['context_id']}:n", chat_id="42", actor_id="42", owner_chat_id="42",
    )

    assert result["status"] == "needs_confirmation"
    assert result["proposal"]["body"] == "Exact bound source."
    assert result["proposal"]["source_refs"] == ["https://t.me/example/only"]
