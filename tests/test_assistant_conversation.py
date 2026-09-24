from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from llm.client import LLMOutcomeUnknown
from prm.application import PersonalResearchAssistant
from prm.capabilities import AuthorizationRequest, CapabilityGrant, CapabilityRegistry, ProviderPolicy
from prm.conversation import (
    ConfirmationRef,
    ConversationStore,
    classify_turn,
    identity_hash,
)
from prm.contracts import ModelEgressAccess, OperatorRequest


NOW = datetime(2026, 9, 19, 10, tzinfo=timezone.utc)


def _confirmation(state, *, proposal_ref="proposal_note_001", version="version-1") -> ConfirmationRef:
    return ConfirmationRef(
        proposal_ref=proposal_ref,
        proposal_version=version,
        response_ref=state.object_refs[0].response_ref,
        chat_id_hash=identity_hash("42"),
        actor_id_hash=identity_hash("42"),
        owner_id_hash=identity_hash("42"),
        expires_at=NOW + timedelta(minutes=5),
    )


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


def test_plain_yes_resolves_only_one_current_exact_visible_proposal() -> None:
    store = ConversationStore()
    state = store.record_response("42", text="Preview A", now=NOW)
    confirmation = _confirmation(state)
    store.offer_confirmation("42", confirmation, now=NOW)

    resolved = store.resolve_plain_yes(
        "42",
        actor_id="42",
        owner_chat_id="42",
        proposal_versions={confirmation.proposal_ref: confirmation.proposal_version},
        now=NOW,
    )

    assert resolved.status == "resolved"
    assert resolved.confirmation_ref == confirmation


def test_plain_yes_fails_closed_for_ambiguous_stale_expired_or_identity_mismatch() -> None:
    store = ConversationStore()
    state = store.record_response("42", text="Preview A", now=NOW)
    first = _confirmation(state, proposal_ref="proposal_note_001")
    second = _confirmation(state, proposal_ref="proposal_note_002")
    state = store.offer_confirmation("42", first, now=NOW)

    # A malformed/recovered state with two visible previews must not choose one
    # by keyword, insertion order, topic, or proposal name.
    store._states[state.conversation_id] = replace(  # noqa: SLF001 - adversarial store fixture
        state,
        visible_confirmation_refs=(first, second),
        current_confirmation_ref=first,
    )
    assert store.resolve_plain_yes(
        "42", actor_id="42", owner_chat_id="42",
        proposal_versions={first.proposal_ref: first.proposal_version, second.proposal_ref: second.proposal_version},
        now=NOW,
    ).status == "ambiguous_or_unavailable"

    store._states[state.conversation_id] = state  # noqa: SLF001
    assert store.resolve_plain_yes(
        "42", actor_id="43", owner_chat_id="42",
        proposal_versions={first.proposal_ref: first.proposal_version}, now=NOW,
    ).status == "unavailable"
    assert store.resolve_plain_yes(
        "42", actor_id=None, owner_chat_id="42",
        proposal_versions={first.proposal_ref: first.proposal_version}, now=NOW,
    ).status == "unavailable"
    assert store.resolve_plain_yes(
        "42", actor_id="42", owner_chat_id="42",
        proposal_versions={first.proposal_ref: "changed-version"}, now=NOW,
    ).status == "stale_or_unavailable"
    assert store.resolve_plain_yes(
        "42", actor_id="42", owner_chat_id="42",
        proposal_versions={first.proposal_ref: first.proposal_version}, now=NOW + timedelta(minutes=6),
    ).status == "unavailable"


def test_confirmation_rejects_group_or_mismatched_private_tuple_at_construction() -> None:
    store = ConversationStore()
    state = store.record_response("42", text="Preview A", now=NOW)

    with pytest.raises(ValueError, match="one private owner tuple"):
        ConfirmationRef(
            proposal_ref="proposal_note_001",
            proposal_version="version-1",
            response_ref=state.object_refs[0].response_ref,
            chat_id_hash=identity_hash("-10042"),
            actor_id_hash=identity_hash("42"),
            owner_id_hash=identity_hash("42"),
            expires_at=NOW + timedelta(minutes=5),
        )


def test_new_topic_cancellation_and_restart_clear_plain_language_confirmation() -> None:
    store = ConversationStore()
    state = store.record_response("42", text="Preview A", now=NOW)
    confirmation = _confirmation(state)
    store.offer_confirmation("42", confirmation, now=NOW)

    state = store.begin_new_topic("42", now=NOW)
    assert state.current_confirmation_ref is None
    assert store.resolve_plain_yes(
        "42", actor_id="42", owner_chat_id="42",
        proposal_versions={confirmation.proposal_ref: confirmation.proposal_version}, now=NOW,
    ).status == "unavailable"

    state = store.record_response("42", text="Preview B", now=NOW)
    confirmation = _confirmation(state, proposal_ref="proposal_note_002")
    store.offer_confirmation("42", confirmation, now=NOW)
    state = store.cancel("42", now=NOW)
    assert state is not None and state.current_confirmation_ref is None

    # Retention is intentionally process-local: a restart never silently
    # restores a text-confirmation capability from a topic summary.
    restarted = ConversationStore()
    assert restarted.resolve_plain_yes(
        "42", actor_id="42", owner_chat_id="42",
        proposal_versions={confirmation.proposal_ref: confirmation.proposal_version}, now=NOW,
    ).status == "unavailable"


def test_explicit_new_topic_is_a_local_reset_not_a_model_or_archive_request(monkeypatch) -> None:
    def forbidden_archive(*args, **kwargs):
        raise AssertionError("new topic must not search")

    monkeypatch.setattr("prm.application.answer_memory_research", forbidden_archive)
    store = ConversationStore()
    store.record_response("42", text="Old result", now=NOW)
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"), conversations=store)

    result = assistant.answer(OperatorRequest(query="/new", mode="chat", chat_id="42"))

    assert result.status == "topic_reset"
    assert result.payload["model_call_attempted"] is False
    state = store.load("42")
    assert state is not None and state.object_refs == () and state.current_confirmation_ref is None


def test_object_controls_need_a_visible_object_not_keywords_alone() -> None:
    store = ConversationStore()
    assert classify_turn("сделай короче", None).kind == "new_topic"
    state = store.record_response(
        "42", text="Первое. Второе.", item_texts=("Первый пункт", "Второй пункт"), now=NOW,
    )
    assert classify_turn("сделай короче", state).kind == "shorten"
    selected = classify_turn("а второе", state)
    assert selected.kind == "select_item"
    assert selected.item_ref == state.object_refs[0].item_refs[1]


def test_request_cancel_marks_only_the_selected_ephemeral_request() -> None:
    store = ConversationStore()
    store.start_request("42", "request-1", now=NOW)
    store.start_request("42", "request-2", now=NOW)

    state = store.cancel("42", "request-1", now=NOW)

    assert state is not None
    assert store.is_cancelled("42", "request-1", now=NOW) is True
    assert store.is_cancelled("42", "request-2", now=NOW) is False
    assert state.pending_request_ids == ("request-2",)

    assert store.cancel_request("request-2", now=NOW) is not None
    assert store.is_cancelled("42", "request-2", now=NOW) is True


def test_general_chat_does_not_fall_into_archive_and_denies_without_model_grant(monkeypatch) -> None:
    def forbidden_archive(*args, **kwargs):
        raise AssertionError("greeting must not start archive retrieval")

    monkeypatch.setattr("prm.application.answer_memory_research", forbidden_archive)
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"), conversations=ConversationStore())

    result = assistant.answer(OperatorRequest(query="Привет, помоги отредактировать этот абзац", mode="auto", chat_id="42"))

    assert result.mode == "chat"
    assert result.status == "provider_egress_required"
    assert result.payload["model_call_attempted"] is False
    assert result.payload["conversation"]["retention"] == "ephemeral_clear_on_restart"


def test_authorized_chat_sends_only_current_direct_text_not_prior_response_or_topic() -> None:
    calls = []

    class FakeLLM:
        @staticmethod
        def complete_with_receipt(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text="Готовый ответ")

    store = ConversationStore()
    store.record_response("42", text="PRIVATE PRIOR RESPONSE SENTINEL", topic="PRIVATE TOPIC SENTINEL", now=NOW)
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"), conversations=store, llm_client=FakeLLM)

    result = assistant.answer(OperatorRequest(
        query="Перепиши это дружелюбнее",
        mode="chat",
        chat_id="42",
        model_access=_model_access(),
    ))

    assert result.status == "ok"
    assert len(calls) == 1
    assert calls[0]["prompt"] == "Перепиши это дружелюбнее"
    assert "PRIVATE PRIOR RESPONSE SENTINEL" not in calls[0]["prompt"]
    assert "PRIVATE TOPIC SENTINEL" not in calls[0]["system"]
    assert result.payload["safe_context"]["omitted_state"] == [
        "prior_messages", "response_objects", "topic_summary", "confirmations",
    ]


def test_authorized_chat_reports_unknown_provider_outcome_without_retry() -> None:
    calls = []

    class UnknownLLM:
        @staticmethod
        def complete_with_receipt(**kwargs):
            calls.append(kwargs)
            raise LLMOutcomeUnknown(SimpleNamespace())

    assistant = PersonalResearchAssistant(
        settings=SimpleNamespace(db_path=":memory:"), conversations=ConversationStore(), llm_client=UnknownLLM,
    )
    result = assistant.answer(OperatorRequest(
        query="Объясни идею", mode="chat", chat_id="42",
        model_access=_model_access(),
    ))

    assert len(calls) == 1
    assert result.status == "provider_outcome_unknown"
    assert result.payload["provider_outcome"] == "unknown"
    assert "не буду автоматически повторять" in result.text


def test_cancel_request_discards_a_model_result_after_the_model_boundary(monkeypatch) -> None:
    started = []
    store = ConversationStore()
    original_start = store.start_request

    def capture_start(chat_id, request_id, **kwargs):
        started.append(request_id)
        return original_start(chat_id, request_id, **kwargs)

    monkeypatch.setattr(store, "start_request", capture_start)

    class CancellableLLM:
        @staticmethod
        def complete_with_receipt(**kwargs):
            assert assistant.cancel(started[-1]) is True
            return SimpleNamespace(text="This model result must not be rendered")

    assistant = PersonalResearchAssistant(
        settings=SimpleNamespace(db_path=":memory:"), conversations=store, llm_client=CancellableLLM,
    )
    result = assistant.answer(OperatorRequest(
        query="Сделай черновик", mode="chat", chat_id="42",
        model_access=_model_access(),
    ))

    assert result.status == "cancelled_after_model_boundary"
    assert "must not be rendered" not in result.text
    assert result.payload["cancelled"] is True
    state = store.load("42")
    assert state is not None and state.pending_request_ids == ()


def test_application_plain_yes_does_not_reroute_or_execute_without_pa13_version_loader(monkeypatch) -> None:
    def forbidden_archive(*args, **kwargs):
        raise AssertionError("plain yes must not reroute")

    monkeypatch.setattr("prm.application.answer_memory_research", forbidden_archive)
    store = ConversationStore()
    state = store.record_response("42", text="Preview A", now=NOW)
    confirmation = _confirmation(state)
    store.offer_confirmation("42", confirmation, now=NOW)
    assistant = PersonalResearchAssistant(settings=SimpleNamespace(db_path=":memory:"), conversations=store)

    result = assistant.answer(OperatorRequest(query="да", mode="auto", chat_id="42", actor_id="42", owner_chat_id="42"))

    assert result.status == "confirmation_unavailable"
    assert result.payload["confirmation_status"] == "stale_or_unavailable"
    assert "прошлой теме" in result.text
