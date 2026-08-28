from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot import callbacks
from bot.bot import _PRM_CALLBACK_PREFIXES


def test_utd_callback_namespace_routes_to_utd_handler(monkeypatch) -> None:
    calls = []
    def fake_utd(db_path, callback_data, *, chat_id):
        calls.append((db_path, callback_data, chat_id)); return {"status": "draft_updated"}
    monkeypatch.setattr(callbacks, "handle_utd_profile_callback", fake_utd)
    settings = SimpleNamespace(db_path="local.db")
    result = callbacks.handle_prm_post_answer_callback(settings, "utdp:u123:pv", chat_id="42")
    assert result == {"status": "draft_updated"}
    assert calls == [("local.db", "utdp:u123:pv", "42")]


def test_existing_prm_callback_namespace_is_unchanged(monkeypatch) -> None:
    calls = []
    def fake_prm(db_path, callback_data, *, chat_id):
        calls.append((db_path, callback_data, chat_id)); return {"status": "needs_confirmation"}
    monkeypatch.setattr(callbacks, "handle_post_answer_callback", fake_prm)
    settings = SimpleNamespace(db_path="local.db")
    result = callbacks.handle_prm_post_answer_callback(settings, "prma:c123:n", chat_id="42")
    assert result == {"status": "needs_confirmation"}
    assert calls == [("local.db", "prma:c123:n", "42")]


def test_active_bot_accepts_only_prm_and_utd_safe_callback_namespaces() -> None:
    assert _PRM_CALLBACK_PREFIXES == ("prma:", "prmc:", "utdp:", "utdc:")
    with pytest.raises(ValueError):
        callbacks.handle_prm_post_answer_callback(SimpleNamespace(db_path="local.db"), "idea:1:done", chat_id="42")
