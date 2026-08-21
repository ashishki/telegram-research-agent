import os
import sqlite3
import tempfile

import pytest

from assistant.prm_post_answer_actions import (
    PRM_ACTION_PREFIX,
    build_post_answer_actions,
    handle_post_answer_callback,
)
from db.migrate import run_migrations
from db.prm19_dogfood_receipts import (
    PRM19DogfoodReceiptValidationError,
    export_interaction_aggregate,
    list_interaction_receipts,
    record_feedback_transition,
    record_interaction_receipt,
)


@pytest.fixture(autouse=True)
def _isolated_private_trace_root(tmp_path, monkeypatch):
    monkeypatch.setattr("assistant.prm_private_traces._TRACE_ROOT", tmp_path / "private_traces")


def _answer() -> dict:
    return {
        "direct_answer": "Use one regression case.",
        "source_refs": ["https://t.me/example/1"],
        "answer_status": "supported",
        "source_count": 1,
        "evidence_classes": ["telegram_archive"],
        "primary_workflow": "research",
    }


def test_one_receipt_per_answer_and_no_raw_question(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()

        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]
        assert context_id
        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                "SELECT chat_id_hash, source_count, evidence_classes_json, useful_label, receipt_status "
                "FROM prm_interaction_ledger WHERE interaction_id = ?", (context_id,)
            ).fetchone()
            raw_columns = {item[1] for item in connection.execute("PRAGMA table_info(prm_interaction_ledger)")}

    assert row[0] != "42"
    assert row[1:] == (1, '["telegram_archive"]', "unknown", "recorded")
    assert not {"question", "raw_post_text", "provider_payload", "source_refs_json"} & raw_columns


def test_feedback_transition_updates_same_interaction_once(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]

        first = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:u", chat_id="42")
        replay = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:r", chat_id="42")
        with sqlite3.connect(db_path) as connection:
            transition_count = connection.execute("SELECT count(*) FROM prm_interaction_feedback_transitions").fetchone()[0]
            useful_label = connection.execute(
                "SELECT useful_label FROM prm_interaction_ledger WHERE interaction_id = ?", (context_id,)
            ).fetchone()[0]

    assert first["status"] == "needs_confirmation"
    assert replay["status"] == "needs_confirmation"
    assert transition_count == 1
    assert useful_label == "yes"


def test_feedback_transition_reports_legacy_check_drift_without_migration():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        with sqlite3.connect(db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE prm_interaction_ledger (
                    interaction_id TEXT PRIMARY KEY,
                    chat_id_hash TEXT NOT NULL,
                    surface TEXT NOT NULL,
                    input_kind TEXT NOT NULL,
                    answer_status TEXT NOT NULL,
                    source_count INTEGER NOT NULL,
                    evidence_classes_json TEXT NOT NULL,
                    external_verification_status TEXT NOT NULL,
                    selected_professional_lens TEXT NOT NULL DEFAULT 'unknown',
                    selected_project TEXT NOT NULL DEFAULT 'unknown',
                    primary_workflow TEXT NOT NULL DEFAULT 'unknown',
                    useful_label TEXT NOT NULL DEFAULT 'unknown',
                    feedback_transitioned_at TEXT,
                    receipt_status TEXT NOT NULL DEFAULT 'recorded',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE prm_interaction_feedback_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    interaction_id TEXT NOT NULL UNIQUE,
                    feedback_action TEXT NOT NULL CHECK(feedback_action IN ('useful', 'wrong_priority', 'too_shallow', 'applied')),
                    useful_label TEXT NOT NULL CHECK(useful_label IN ('yes', 'partial', 'no')),
                    recorded_at TEXT NOT NULL
                );
                INSERT INTO prm_interaction_ledger (
                    interaction_id, chat_id_hash, surface, input_kind, answer_status,
                    source_count, evidence_classes_json, external_verification_status,
                    created_at, expires_at
                ) VALUES (
                    'ctx12345', 'a', 'telegram', 'text', 'supported',
                    1, '[]', 'unknown', '2026-08-17T00:00:00Z', '2999-01-01T00:00:00Z'
                );
                """
            )

        result = record_feedback_transition(db_path, interaction_id="ctx12345", action_code="ws")
        with sqlite3.connect(db_path) as connection:
            transition_count = connection.execute("SELECT count(*) FROM prm_interaction_feedback_transitions").fetchone()[0]
            useful_label = connection.execute(
                "SELECT useful_label FROM prm_interaction_ledger WHERE interaction_id = 'ctx12345'"
            ).fetchone()[0]

    assert result == {"status": "schema_incompatible", "write_performed": False}
    assert transition_count == 0
    assert useful_label == "unknown"


def test_migration_rebuilds_prm_feedback_transition_reason_actions(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                CREATE TABLE prm_interaction_feedback_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    interaction_id TEXT NOT NULL UNIQUE,
                    feedback_action TEXT NOT NULL CHECK(feedback_action IN ('useful', 'wrong_priority', 'too_shallow', 'applied')),
                    useful_label TEXT NOT NULL CHECK(useful_label IN ('yes', 'partial', 'no')),
                    recorded_at TEXT NOT NULL
                )
                """
            )
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]

        result = handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:m", chat_id="42")
        with sqlite3.connect(db_path) as connection:
            table_sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'prm_interaction_feedback_transitions'"
            ).fetchone()[0]
            transition = connection.execute(
                "SELECT feedback_action, useful_label FROM prm_interaction_feedback_transitions WHERE interaction_id = ?",
                (context_id,),
            ).fetchone()
            ledger_label = connection.execute(
                "SELECT useful_label FROM prm_interaction_ledger WHERE interaction_id = ?",
                (context_id,),
            ).fetchone()[0]

    assert result["status"] == "needs_reason"
    assert "'wrong_sources'" in table_sql
    assert transition == ("partial", "partial")
    assert ledger_label == "partial"


def test_owner_review_and_aggregate_are_private_and_scoped(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]
        build_post_answer_actions(_answer(), db_path=db_path, chat_id="43")
        handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:s", chat_id="42")

        rows = list_interaction_receipts(db_path, chat_id_hash=_chat_hash(db_path, "42"))
        aggregate = export_interaction_aggregate(db_path)

    assert len(rows) == 1
    assert rows[0]["useful_label"] == "partial"
    assert "chat_id_hash" not in rows[0]
    assert aggregate == {
        "schema_version": "prm_interaction_aggregate.v1",
        "receipt_count": 2,
        "useful_labels": {"yes": 0, "partial": 1, "no": 0, "unknown": 1},
        "public_export": False,
        "dogfood_started": False,
    }


def test_ledger_rejects_raw_answer_payload(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()

        with pytest.raises(PRM19DogfoodReceiptValidationError, match="raw answer payload"):
            record_interaction_receipt(
                db_path,
                interaction_id="0123456789",
                chat_id_hash="a" * 64,
                answer={"question": "private question"},
            )


def test_expired_receipts_and_transitions_are_pruned_before_review(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        context_id = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")["context_id"]
        handle_post_answer_callback(db_path, f"{PRM_ACTION_PREFIX}:{context_id}:u", chat_id="42")
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE prm_interaction_ledger SET expires_at = '2000-01-01T00:00:00Z' WHERE interaction_id = ?",
                (context_id,),
            )

        rows = list_interaction_receipts(db_path, chat_id_hash=_chat_hash(db_path, "42"))
        aggregate = export_interaction_aggregate(db_path)
        with sqlite3.connect(db_path) as connection:
            transition_count = connection.execute("SELECT count(*) FROM prm_interaction_feedback_transitions").fetchone()[0]

    assert rows == []
    assert aggregate["receipt_count"] == 0
    assert transition_count == 0


def test_pre_mat7_proposal_schema_keeps_actions_when_receipt_is_unavailable():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "CREATE TABLE prm_post_answer_proposals (context_id TEXT PRIMARY KEY, chat_id_hash TEXT NOT NULL, "
                "summary_json TEXT NOT NULL, proposals_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, "
                "expires_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ready')"
            )

        result = build_post_answer_actions(_answer(), db_path=db_path, chat_id="42")

    assert result["context_id"]
    assert result["reply_markup"] is not None


def _chat_hash(db_path: str, chat_id: str) -> str:
    # The public review API deliberately takes only the already-hashed identity.
    import hashlib

    return hashlib.sha256(f"prm.post-answer.v1:{chat_id}".encode()).hexdigest()
