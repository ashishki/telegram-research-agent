import os
import sqlite3
import tempfile

import pytest

from assistant.pi_memory import build_memory_proposal, confirm_memory_proposal, query_saved_knowledge
from db.migrate import run_migrations


def _confirm(db_path: str, *, object_type: str, title: str, metadata: dict | None = None, operation: str = "create", target_memory_id: str | None = None) -> dict:
    draft = build_memory_proposal(object_type, {
        "operation": operation, "target_memory_id": target_memory_id,
        "title": title, "body": "Bounded confirmed summary.",
        "source_refs": ["https://t.me/example/1"], "metadata": metadata or {},
    })
    return confirm_memory_proposal(db_path, {"proposal": draft["proposal"], "confirmation_token": draft["confirmation"]["token"]})


def test_query_filters(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        _confirm(db_path, object_type="watch_topic", title="RAG evaluation", metadata={"project_name": "prm"})
        _confirm(db_path, object_type="knowledge_note", title="Other note")

        result = query_saved_knowledge(db_path, filters={"topic": "rag", "project": "prm", "from_at": "2026-01-01T00:00:00Z", "state": "active"})

    assert result["secondary_evidence"] is True
    assert result["write_performed"] is False
    assert len(result["items"]) == 1
    assert result["items"][0]["citation"].startswith("memory:mem_")
    assert result["items"][0]["source_refs"] == ["https://t.me/example/1"]


def test_state_history_preserved_when_action_is_closed(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        created = _confirm(db_path, object_type="action", title="Run one eval")
        closed = _confirm(db_path, object_type="action", title="Run one eval", operation="delete", target_memory_id=created["memory_id"])

        closed_items = query_saved_knowledge(db_path, filters={"state": "closed"})["items"]
        active_items = query_saved_knowledge(db_path, filters={"state": "active", "object_type": "action"})["items"]

    assert closed["persisted"] is True
    assert len(closed_items) == 1
    assert closed_items[0]["memory_id"] == created["memory_id"]
    assert [event["event_type"] for event in closed_items[0]["history"]] == ["created", "deleted"]
    assert active_items == []


def test_source_card_and_canonical_timestamp(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        result = _confirm(db_path, object_type="source_card", title="Official source")
        draft = build_memory_proposal("source_card", {"title": "Bad time"})
        with pytest.raises(ValueError, match="ISO-8601"):
            confirm_memory_proposal(db_path, {"proposal": draft["proposal"], "confirmation_token": draft["confirmation"]["token"], "confirmed_at": "not-a-date"})

    assert result["object_type"] == "source_card"


def test_legacy_offset_timestamp_uses_utc_date_filter(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "memory.db")
        monkeypatch.setenv("AGENT_DB_PATH", db_path)
        run_migrations()
        created = _confirm(db_path, object_type="knowledge_note", title="Legacy time")
        with sqlite3.connect(db_path) as connection:
            connection.execute("UPDATE personal_memory_events SET created_at = '2026-01-01T00:30:00+02:00' WHERE memory_id = ?", (created["memory_id"],))
        result = query_saved_knowledge(db_path, filters={"to_at": "2025-12-31T23:00:00Z"})

    assert result["items"][0]["created_at"] == "2025-12-31T22:30:00Z"
