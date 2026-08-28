from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from assistant.utd_profile import UTD_CONFIRM_PREFIX, UTD_DRAFT_PREFIX, handle_utd_profile_callback, load_confirmed_utd_profile, start_utd_profile_onboarding


def _init_db(path: Path) -> None:
    with sqlite3.connect(path) as c:
        c.executescript("""
        CREATE TABLE prm_post_answer_proposals (context_id TEXT PRIMARY KEY, chat_id_hash TEXT NOT NULL, summary_json TEXT NOT NULL, proposals_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, expires_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft');
        CREATE TABLE personal_memory_events (id INTEGER PRIMARY KEY AUTOINCREMENT, memory_id TEXT NOT NULL, object_type TEXT NOT NULL, event_type TEXT NOT NULL, title TEXT NOT NULL, body TEXT, rationale TEXT, source_refs_json TEXT NOT NULL, metadata_json TEXT NOT NULL, proposal_id TEXT NOT NULL, rollback_of_event_id INTEGER, created_at TEXT NOT NULL, created_by TEXT NOT NULL, confirmation_token_hash TEXT NOT NULL, confirmation_receipt_json TEXT NOT NULL);
        CREATE UNIQUE INDEX uq_personal_memory_confirmation ON personal_memory_events(proposal_id, confirmation_token_hash);
        """)


def test_preview_confirm_pause_mute_and_expiry(tmp_path: Path) -> None:
    db = tmp_path / "m.db"; _init_db(db); now = datetime(2026,8,28,12,tzinfo=timezone.utc)
    started = start_utd_profile_onboarding(db, chat_id="42", seed_text="программа=Graduate analytics; карьера=internships; AI=agent systems", now=now)
    assert started["profile_persisted"] is False
    cid = started["context_id"]
    for action in ("ps", "mf"):
        handle_utd_profile_callback(db, f"{UTD_DRAFT_PREFIX}:{cid}:{action}", chat_id="42", now=now)
    preview = handle_utd_profile_callback(db, f"{UTD_DRAFT_PREFIX}:{cid}:pv", chat_id="42", now=now)
    meta = preview["proposal"]["metadata"]
    assert meta["timezone"] == "America/Chicago" and meta["daily_cap"] == 5
    assert meta["paused"] is True and meta["muted_sources"] == ["spouse_family"]
    assert meta["monitoring_authorized"] is False and meta["delivery_authorized"] is False
    saved = handle_utd_profile_callback(db, f"{UTD_CONFIRM_PREFIX}:{cid}:save", chat_id="42", now=now)
    replay = handle_utd_profile_callback(db, f"{UTD_CONFIRM_PREFIX}:{cid}:save", chat_id="42", now=now)
    assert saved["status"] == "ok" and replay["status"] == "already_confirmed"
    assert load_confirmed_utd_profile(db, now=now) is not None
    assert load_confirmed_utd_profile(db, now=now + timedelta(days=121)) is None


def test_cancel_and_expiry_scrub_draft_payload(tmp_path: Path) -> None:
    db = tmp_path / "m.db"; _init_db(db); now = datetime(2026,8,28,12,tzinfo=timezone.utc)
    cid = start_utd_profile_onboarding(db, chat_id="42", now=now)["context_id"]
    handle_utd_profile_callback(db, f"{UTD_DRAFT_PREFIX}:{cid}:cx", chat_id="42", now=now)
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT summary_json, proposals_json, status FROM prm_post_answer_proposals WHERE context_id=?", (cid,)).fetchone() == ("{}", "{}", "cancelled")
    cid2 = start_utd_profile_onboarding(db, chat_id="42", now=now)["context_id"]
    result = handle_utd_profile_callback(db, f"{UTD_DRAFT_PREFIX}:{cid2}:pv", chat_id="42", now=now+timedelta(minutes=31))
    assert result["status"] == "expired"
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT summary_json, proposals_json, status FROM prm_post_answer_proposals WHERE context_id=?", (cid2,)).fetchone() == ("{}", "{}", "expired")
