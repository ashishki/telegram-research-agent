import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pytest

from assistant.prm_post_answer_actions import (
    PRM_ACTION_PREFIX,
    PRM_CONFIRM_PREFIX,
    _CONTEXTS,
    _claim_context_for_confirmation,
    _clear_confirmation_lock,
    UnavailablePrmAction,
    apply_validated_prm_action,
    build_post_answer_actions as _build_post_answer_actions,
    handle_post_answer_callback as _handle_post_answer_callback,
    read_prm_rollback_drain,
    validate_prm_post_answer_callback,
)
from assistant.utd_profile import start_utd_profile_onboarding
from db.migrate import run_migrations


@pytest.fixture(autouse=True)
def _isolated_private_trace_root(tmp_path, monkeypatch):
    monkeypatch.setattr("assistant.prm_private_traces._TRACE_ROOT", tmp_path / "private_traces")


def _answer(*, project_name: str = "") -> dict:
    return {
        "question": "как улучшить eval gates?",
        "direct_answer": "Добавить один regression case.",
        "source_refs": ["https://t.me/example/1"],
        "project_name": project_name,
    }


def test_post_answer_controls_require_private_owner_actor_binding(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()

        missing = _build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")
        group = _build_post_answer_actions(
            _answer(), db_path=db_path, chat_id="-10042", actor_id="42", owner_chat_id="42"
        )
        bound = _build_post_answer_actions(
            _answer(), db_path=db_path, chat_id="42", actor_id="42", owner_chat_id="42"
        )
        rejected = _handle_post_answer_callback(
            db_path, f"{PRM_ACTION_PREFIX}:{bound['context_id']}:n", chat_id="42", actor_id="42"
        )

    assert missing["reply_markup"] is None
    assert group["reply_markup"] is None
    assert bound["reply_markup"] is not None
    assert rejected["status"] == "action_unavailable"


def test_post_answer_snapshot_rejects_invalid_counts_and_tampering(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()

        invalid = _build_post_answer_actions(
            {**_answer(), "direct_count": True}, db_path=db_path, chat_id="42", actor_id="42", owner_chat_id="42"
        )
        bound = _build_post_answer_actions(
            _answer(), db_path=db_path, chat_id="42", actor_id="42", owner_chat_id="42"
        )
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE prm_post_answer_proposals SET summary_json = json_set(summary_json, '$.project_name', 'tampered') WHERE context_id = ?",
                (bound["context_id"],),
            )
        rejected = _handle_post_answer_callback(
            db_path, f"{PRM_ACTION_PREFIX}:{bound['context_id']}:n", chat_id="42", actor_id="42", owner_chat_id="42"
        )

    assert invalid["reply_markup"] is None
    assert rejected["status"] == "action_unavailable"


def test_post_answer_context_binds_canonical_snapshot_and_project_ref(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        bound = _build_post_answer_actions(
            {
                **_answer(project_name="telegram-research-agent"),
                "title": "  Result\n title  ",
                "query": "  evidence   binding ",
                "keyboard_action_ids": ["n", "n", "unknown", "u"],
            },
            db_path=db_path,
            chat_id="42",
            actor_id="42",
            owner_chat_id="42",
        )
        with sqlite3.connect(db_path) as connection:
            summary = json.loads(connection.execute(
                "SELECT summary_json FROM prm_post_answer_proposals WHERE context_id = ?", (bound["context_id"],)
            ).fetchone()[0])

    snapshot = summary["prm_post_answer_action_binding"]["source_snapshot"]
    assert set(snapshot) == {
        "title", "query", "body", "source_refs", "evidence_items", "project_name",
        "primary_intent", "response_contract_id", "direct_count", "partial_count", "offered_action_codes",
    }
    assert snapshot["title"] == "Result title"
    assert snapshot["query"] == "evidence binding"
    assert snapshot["offered_action_codes"] == bound["action_codes"]
    assert summary["prm_post_answer_action_binding"]["source_project_ref"] == {
        "origin": "telegram-research-agent", "value": "telegram-research-agent",
    }


def test_invalid_prm_action_context_is_read_only_before_rejection(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        bound = _build_post_answer_actions(
            _answer(), db_path=db_path, chat_id="42", actor_id="42", owner_chat_id="42"
        )
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE prm_post_answer_proposals SET summary_json = '{}' WHERE context_id = ?",
                (bound["context_id"],),
            )
            before = connection.execute(
                "SELECT summary_json, proposals_json, status FROM prm_post_answer_proposals WHERE context_id = ?",
                (bound["context_id"],),
            ).fetchone()
            memory_before = connection.execute("SELECT count(*) FROM personal_memory_events").fetchone()[0]
            receipts_before = connection.execute("SELECT count(*) FROM prm_interaction_ledger").fetchone()[0]

        result = _handle_post_answer_callback(
            db_path, f"{PRM_ACTION_PREFIX}:{bound['context_id']}:n", chat_id="42", actor_id="42", owner_chat_id="42"
        )
        with sqlite3.connect(db_path) as connection:
            after = connection.execute(
                "SELECT summary_json, proposals_json, status FROM prm_post_answer_proposals WHERE context_id = ?",
                (bound["context_id"],),
            ).fetchone()
            memory_after = connection.execute("SELECT count(*) FROM personal_memory_events").fetchone()[0]
            receipts_after = connection.execute("SELECT count(*) FROM prm_interaction_ledger").fetchone()[0]

    assert result["status"] == "action_unavailable"
    assert after == before
    assert memory_after == memory_before
    assert receipts_after == receipts_before


def test_post_answer_context_rejects_expired_wrong_chat_actor_or_tampered_binding(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        bound = _build_post_answer_actions(
            _answer(), db_path=db_path, chat_id="42", actor_id="42", owner_chat_id="42"
        )
        callback = f"{PRM_ACTION_PREFIX}:{bound['context_id']}:n"
        wrong_chat = _handle_post_answer_callback(
            db_path, callback, chat_id="43", actor_id="43", owner_chat_id="43"
        )
        wrong_actor = _handle_post_answer_callback(
            db_path, callback, chat_id="42", actor_id="43", owner_chat_id="42"
        )
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE prm_post_answer_proposals SET expires_at = '2000-01-01T00:00:00Z' WHERE context_id = ?",
                (bound["context_id"],),
            )
        expired = _handle_post_answer_callback(
            db_path, callback, chat_id="42", actor_id="42", owner_chat_id="42"
        )
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE prm_post_answer_proposals SET expires_at = '2999-01-01T00:00:00Z', "
                "summary_json = json_set(summary_json, '$.prm_post_answer_action_binding.source_result_version', 'tampered') "
                "WHERE context_id = ?",
                (bound["context_id"],),
            )
        tampered = _handle_post_answer_callback(
            db_path, callback, chat_id="42", actor_id="42", owner_chat_id="42"
        )

    assert {result["status"] for result in (wrong_chat, wrong_actor, expired, tampered)} == {"action_unavailable"}


def test_validated_prm_action_cas_rejects_stale_row(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        bound = _build_post_answer_actions(
            _answer(), db_path=db_path, chat_id="42", actor_id="42", owner_chat_id="42"
        )
        validated = validate_prm_post_answer_callback(
            db_path, f"{PRM_ACTION_PREFIX}:{bound['context_id']}:n", chat_id="42", actor_id="42", owner_chat_id="42"
        )
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE prm_post_answer_proposals SET proposals_json = json_set(proposals_json, '$.__other_transition__', 1) WHERE context_id = ?",
                (bound["context_id"],),
            )
            before = connection.execute(
                "SELECT proposals_json, status FROM prm_post_answer_proposals WHERE context_id = ?", (bound["context_id"],)
            ).fetchone()
        result = apply_validated_prm_action(db_path, validated)
        with sqlite3.connect(db_path) as connection:
            after = connection.execute(
                "SELECT proposals_json, status FROM prm_post_answer_proposals WHERE context_id = ?", (bound["context_id"],)
            ).fetchone()

    assert not isinstance(validated, UnavailablePrmAction)
    assert result["status"] == "action_unavailable"
    assert after == before


def test_dynamic_post_answer_codes_require_issued_bound_transition(monkeypatch):
    answer = {
        **_answer(),
        "archive_evidence": {"items": [
            {"source_url": "https://t.me/example/1", "snippet": "Первый пункт."},
            {"source_url": "https://t.me/example/2", "snippet": "Второй пункт."},
        ]},
    }
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(answer, db_path=db_path, chat_id="42")["context_id"]
        forged_selection = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n2", chat_id="42")
        forged_cancel = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:c", chat_id="42")
        forged_reason = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:ws", chat_id="42")
        chooser = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")
        preview = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n2", chat_id="42")
        confirmed = handle_post_answer_callback(db_path, f"{PRM_CONFIRM_PREFIX}:{context_id}:n2", chat_id="42")

    assert {result["status"] for result in (forged_selection, forged_cancel, forged_reason)} == {"action_unavailable"}
    assert chooser["status"] == "select_item"
    assert preview["status"] == "needs_confirmation"
    assert confirmed["write_performed"] is True


def test_prm_rollback_drain_is_owner_restricted_and_never_mutates_utd_rows(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        bound = _build_post_answer_actions(
            _answer(), db_path=db_path, chat_id="42", actor_id="42", owner_chat_id="42"
        )
        utd = start_utd_profile_onboarding(db_path, chat_id="42", now=datetime.now(timezone.utc))
        with sqlite3.connect(db_path) as connection:
            before = connection.execute(
                "SELECT context_id, summary_json, proposals_json, status FROM prm_post_answer_proposals ORDER BY context_id"
            ).fetchall()

        statements: list[str] = []
        real_connect = sqlite3.connect

        def traced_connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection

        monkeypatch.setattr("assistant.prm_post_answer_actions.sqlite3.connect", traced_connect)
        report = read_prm_rollback_drain(db_path, owner_chat_id="42", now=datetime.now(timezone.utc))
        wrong_owner = read_prm_rollback_drain(db_path, owner_chat_id="43", now=datetime.now(timezone.utc))
        with real_connect(db_path) as connection:
            after = connection.execute(
                "SELECT context_id, summary_json, proposals_json, status FROM prm_post_answer_proposals ORDER BY context_id"
            ).fetchall()

    assert bound["context_id"] and utd["context_id"]
    assert report["status"] == "blocked"
    assert report["blocker_count"] == 2
    assert report["classifications"] == {
        "prm_binding_v1": 1,
        "legacy_prm_candidate": 0,
        "utd_profile": 1,
        "utd_subscription": 0,
        "unknown": 0,
    }
    assert wrong_owner["status"] == "clear"
    assert after == before
    assert statements and all(statement.lstrip().upper().startswith("SELECT") for statement in statements)


def build_post_answer_actions(answer, *, db_path, chat_id):
    """Use the exact synthetic private tuple required by PA-00."""
    return _build_post_answer_actions(
        answer, db_path=db_path, chat_id=chat_id, actor_id=chat_id, owner_chat_id=chat_id
    )


def handle_post_answer_callback(db_path, callback_data, *, chat_id, actor_id=None):
    return _handle_post_answer_callback(
        db_path, callback_data, chat_id=chat_id,
        actor_id=actor_id if actor_id is not None else chat_id, owner_chat_id=chat_id,
    )


def test_action_markup_relevant_and_bounded(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        markup = build_post_answer_actions(_answer(project_name="telegram-research-agent"), db_path=db_path, chat_id="42")["reply_markup"]
        buttons = [button for row in markup["inline_keyboard"] for button in row]

    assert {button["text"] for button in buttons}.issuperset({"Полезно", "Частично", "Мимо", "Сохранить заметку", "Следить"})
    assert {button["text"] for button in buttons}.issuperset({"Связать с проектом", "Создать действие", "Создать эксперимент"})
    assert all(button["callback_data"].startswith(f"{PRM_ACTION_PREFIX}:") for button in buttons)
    assert all(len(button["callback_data"]) <= 64 for button in buttons)


def test_proposal_before_write(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]

        result = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")

        assert result["status"] == "needs_confirmation"
        assert result["write_performed"] is False
        assert os.path.exists(db_path)
        confirm_button = result["reply_markup"]["inline_keyboard"][0][0]
        assert confirm_button["callback_data"] == f"{PRM_CONFIRM_PREFIX}:{context_id}:n"


def test_save_second_item_uses_exact_answer_version_and_full_preview(monkeypatch):
    answer = {
        **_answer(),
        "archive_evidence": {"items": [
            {"source_url": "https://t.me/example/1", "snippet": "Первый пункт."},
            {"source_url": "https://t.me/example/2", "snippet": "Второй точный пункт."},
        ]},
    }
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(answer, db_path=db_path, chat_id="42")["context_id"]
        chooser = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")
        preview = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n2", chat_id="42")
        forged = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n5", chat_id="42")
        confirmed = handle_post_answer_callback(db_path, f"{PRM_CONFIRM_PREFIX}:{context_id}:n2", chat_id="42")

        assert chooser["status"] == "select_item"
        assert chooser["write_performed"] is False
        assert preview["status"] == "needs_confirmation"
        assert preview["proposal"]["body"] == "Второй точный пункт."
        assert preview["proposal"]["source_refs"] == ["https://t.me/example/2"]
        assert "Текст: Второй точный пункт." in preview["message"]
        assert forged["status"] == "action_unavailable"
        assert forged["write_performed"] is False
        assert confirmed["write_performed"] is True


def test_single_evidence_item_is_the_exact_saved_item(monkeypatch):
    answer = {
        **_answer(),
        "direct_answer": "Сводка ответа отличается от источника.",
        "archive_evidence": {"items": [
            {"source_url": "https://t.me/example/only", "snippet": "Единственный точный пункт."},
        ]},
    }
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(answer, db_path=db_path, chat_id="42")["context_id"]
        preview = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")

        assert preview["proposal"]["body"] == "Единственный точный пункт."
        assert preview["proposal"]["source_refs"] == ["https://t.me/example/only"]
        assert preview["proposal"]["metadata"]["selected_item_index"] == 1


def test_forged_or_unselected_item_callback_cannot_draft(monkeypatch):
    answer = {
        **_answer(),
        "primary_intent": "archive_lookup",
        "direct_count": 1,
        "archive_evidence": {"items": [
            {"source_url": "https://t.me/example/1", "snippet": "Первый пункт."},
            {"source_url": "https://t.me/example/2", "snippet": "Второй пункт."},
        ]},
    }
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(answer, db_path=db_path, chat_id="42")["context_id"]
        direct_item = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n2", chat_id="42")
        forged_action = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:p", chat_id="42")

        assert direct_item["status"] == "action_unavailable"
        assert forged_action["status"] == "action_unavailable"
        assert direct_item["write_performed"] is False
        assert forged_action["write_performed"] is False


def test_confirmed_action_receipt(monkeypatch):
    _CONTEXTS.clear()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]
        handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")

        result = handle_post_answer_callback(db_path, f"{PRM_CONFIRM_PREFIX}:{context_id}:n", chat_id="42")

        assert result["status"] == "ok"
        assert result["write_performed"] is True
        assert "Сохранено" in result["message"]
        assert "memory_id=" not in result["message"]


def test_restart_and_chat_isolation(monkeypatch):
    _CONTEXTS.clear()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]
        _CONTEXTS.clear()  # simulates process restart; durable state must remain usable

        wrong_chat = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="43")
        drafted = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")
        repeated = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")

        assert wrong_chat["status"] == "action_unavailable"
        assert drafted["status"] == "needs_confirmation"
        assert repeated["proposal"] == drafted["proposal"]


def test_expired_context_cannot_draft_or_confirm(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]
        with sqlite3.connect(db_path) as connection:
            connection.execute("UPDATE prm_post_answer_proposals SET expires_at = '2000-01-01T00:00:00Z' WHERE context_id = ?", (context_id,))

        result = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")
        confirm = handle_post_answer_callback(db_path, f"{PRM_CONFIRM_PREFIX}:{context_id}:n", chat_id="42")
        with sqlite3.connect(db_path) as connection:
            remaining = connection.execute(
                "SELECT count(*) FROM prm_post_answer_proposals WHERE context_id = ?", (context_id,)
            ).fetchone()[0]

        assert result["status"] == "action_unavailable"
        assert result["write_performed"] is False
        assert confirm["status"] == "action_unavailable"
        assert confirm["write_performed"] is False
        assert remaining == 1


def test_cancelled_context_cannot_be_confirmed(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]
        preview = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")
        cancelled = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:c", chat_id="42")
        confirm = handle_post_answer_callback(db_path, f"{PRM_CONFIRM_PREFIX}:{context_id}:n", chat_id="42")

        assert preview["status"] == "needs_confirmation"
        assert cancelled["status"] == "cancelled"
        assert cancelled["write_performed"] is False
        assert confirm["status"] == "action_unavailable"


def test_confirmation_idempotent(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]
        handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")

        first = handle_post_answer_callback(db_path, f"{PRM_CONFIRM_PREFIX}:{context_id}:n", chat_id="42")
        replay = handle_post_answer_callback(db_path, f"{PRM_CONFIRM_PREFIX}:{context_id}:n", chat_id="42")
        with sqlite3.connect(db_path) as connection:
            event_count = connection.execute("SELECT count(*) FROM personal_memory_events").fetchone()[0]

        assert first["write_performed"] is True
        assert replay["status"] == "already_confirmed"
        assert replay["write_performed"] is False
        assert event_count == 1


def test_stalled_confirmation_is_recovered_without_claiming_a_write(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]
        handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE prm_post_answer_proposals SET proposals_json = json_set(proposals_json, '$.__confirmation_lock__', ?) WHERE context_id = ?",
                ("2000-01-01T00:00:00Z", context_id),
            )

        recovered = handle_post_answer_callback(db_path, f"{PRM_CONFIRM_PREFIX}:{context_id}:n", chat_id="42")
        replay = handle_post_answer_callback(db_path, f"{PRM_CONFIRM_PREFIX}:{context_id}:n", chat_id="42")

        assert recovered["persisted"] is True
        assert recovered["write_performed"] is True
        assert replay["status"] == "already_confirmed"
        assert replay["write_performed"] is False


def test_old_confirmation_claim_cannot_clear_a_stale_takeover_lock(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]
        handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42")
        first_claim = _claim_context_for_confirmation(db_path, context_id, "42")
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE prm_post_answer_proposals SET proposals_json = json_set(proposals_json, '$.__confirmation_lock__', ?) WHERE context_id = ?",
                ("2000-01-01T00:00:00Z:stalled", context_id),
            )
        second_claim = _claim_context_for_confirmation(db_path, context_id, "42")
        _clear_confirmation_lock(db_path, context_id, str(first_claim))
        with sqlite3.connect(db_path) as connection:
            lock = connection.execute(
                "SELECT json_extract(proposals_json, '$.__confirmation_lock__') FROM prm_post_answer_proposals WHERE context_id = ?",
                (context_id,),
            ).fetchone()[0]

        assert first_claim
        assert second_claim
        assert lock == second_claim


def test_group_context_and_other_actor_are_fail_closed(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()

        group = build_post_answer_actions(_answer(), db_path=db_path, chat_id="-100123")
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]
        denied = handle_post_answer_callback(
            db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42", actor_id="43"
        )
        allowed = handle_post_answer_callback(
            db_path, f"{PRM_ACTION_PREFIX}:{context_id}:n", chat_id="42", actor_id="42"
        )

        assert group == {"context_id": None, "reply_markup": None, "action_codes": []}
        assert denied["status"] == "action_unavailable"
        assert allowed["status"] == "needs_confirmation"


def test_feedback_action_no_config_or_external_mutation(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]

        result = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:u", chat_id="42")

        assert result["proposal"]["object_type"] == "feedback"
        assert result["write_performed"] is False
        assert os.path.exists(db_path)


def test_partial_feedback_prompts_for_reason_and_updates_private_receipt(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]

        prompt = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:m", chat_id="42")
        reason = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:ws", chat_id="42")

        assert prompt["status"] == "needs_reason"
        buttons = [button for row in prompt["reply_markup"]["inline_keyboard"] for button in row]
        assert "Не те источники" in {button["text"] for button in buttons}
        assert reason["status"] == "recorded"
        assert reason["write_performed"] is False


def test_private_receipt_write_failure_does_not_drop_answer(monkeypatch):
    def fail_receipt(*args, **kwargs):
        raise PermissionError("private trace directory is not writable")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        monkeypatch.setattr("assistant.prm_post_answer_actions.write_private_interaction_receipt", fail_receipt)
        run_migrations()

        result = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")

        assert result["context_id"]
        assert result["reply_markup"]
        with sqlite3.connect(db_path) as connection:
            status = connection.execute(
                "SELECT receipt_status FROM prm_post_answer_proposals WHERE context_id = ?",
                (result["context_id"],),
            ).fetchone()[0]

        assert status == "failed"
