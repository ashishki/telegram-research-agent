from types import SimpleNamespace

from assistant.prm_post_answer_actions import PRM_ACTION_PREFIX, build_post_answer_actions
from bot import bot as bot_runtime
from bot import callbacks, handlers, legacy_handlers, prm_handlers
from bot.runtime import BOT_RUNTIME_LEGACY, BOT_RUNTIME_PRM_ASSISTANT, normalize_bot_runtime_mode
from bot.prm_handlers import PRM_SAFE_COMMANDS
from db.migrate import run_migrations


def test_runtime_mode_is_explicit():
    assert normalize_bot_runtime_mode("prm") == BOT_RUNTIME_PRM_ASSISTANT
    assert normalize_bot_runtime_mode("legacy") == BOT_RUNTIME_LEGACY


def test_active_registry_contains_only_prm_commands():
    assert "/weekly" not in PRM_SAFE_COMMANDS
    assert "/run_digest" not in PRM_SAFE_COMMANDS
    assert {"/auto", "/research", "/brief", "/chat"}.issubset(PRM_SAFE_COMMANDS)


def test_prm_entrypoints_propagate_private_owner_identity_or_render_no_controls(monkeypatch, tmp_path):
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

    assert valid["reply_markup"] is not None
    assert absent["reply_markup"] is None
    assert malformed["reply_markup"] is None
    assert group["reply_markup"] is None
    assert legacy is None
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
