from datetime import datetime, timezone

from assistant.operator_context import build_operator_context, validate_operator_context


def test_selects_one_workflow():
    context = build_operator_context(
        chat_id="42",
        query="Собери редакторский бриф про AI transformation",
        requested_mode="brief",
        now=datetime(2026, 8, 14, tzinfo=timezone.utc),
    )

    validate_operator_context(context)
    assert context.primary_workflow == "writer_editor_brief"
    assert context.interaction_id
    assert context.chat_id_hash != "42"
    assert context.durable_write_allowed is False
    assert context.created_at == "2026-08-14T00:00:00Z"


def test_current_fact_gate_wins():
    context = build_operator_context(
        chat_id="42",
        query="Какая текущая цена NVIDIA сегодня?",
        requested_mode="chat",
    )

    assert context.primary_workflow == "current_fact_verification"
    assert context.external_verification_requirement is True
    assert context.primary_workflow != "generic_chat"


def test_voice_context_is_ephemeral_and_validated():
    context = build_operator_context(
        chat_id="42",
        query="Что было в архиве про evals?",
        requested_mode="research",
        input_kind="voice_transcript",
    )

    validate_operator_context(context)
    assert context.input_kind == "voice_transcript"
    assert context.privacy_mode == "ephemeral_local_only"
