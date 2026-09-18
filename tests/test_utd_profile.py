from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from assistant.utd_profile import UTD_CONFIRM_PREFIX, UTD_DRAFT_PREFIX, build_utd_subscription_cancel_proposal, confirm_utd_subscription_cancel, handle_utd_profile_callback, handle_utd_subscription_callback, load_confirmed_utd_profile, start_utd_profile_onboarding, start_utd_subscription_cancel, start_utd_subscription_pause
from assistant.utd_profile_schema import render_utd_watch_preview
from external_watch.subscription import subscription_effect
from external_watch.profile import load_confirmed_utd_profile as load_runtime_utd_profile


def _init_db(path: Path) -> None:
    with sqlite3.connect(path) as c:
        c.executescript("""
        CREATE TABLE prm_post_answer_proposals (context_id TEXT PRIMARY KEY, chat_id_hash TEXT NOT NULL, summary_json TEXT NOT NULL, proposals_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, expires_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft');
        CREATE TABLE personal_memory_events (id INTEGER PRIMARY KEY AUTOINCREMENT, memory_id TEXT NOT NULL, object_type TEXT NOT NULL, event_type TEXT NOT NULL, title TEXT NOT NULL, body TEXT, rationale TEXT, source_refs_json TEXT NOT NULL, metadata_json TEXT NOT NULL, proposal_id TEXT NOT NULL, rollback_of_event_id INTEGER, created_at TEXT NOT NULL, created_by TEXT NOT NULL, confirmation_token_hash TEXT NOT NULL, confirmation_receipt_json TEXT NOT NULL);
        CREATE UNIQUE INDEX uq_personal_memory_confirmation ON personal_memory_events(proposal_id, confirmation_token_hash);
        """)


def test_preview_confirm_pause_mute_and_expiry(tmp_path: Path) -> None:
    db = tmp_path / "m.db"; _init_db(db); now = datetime(2026,8,28,12,tzinfo=timezone.utc)
    started = start_utd_profile_onboarding(db, chat_id="42", seed_text="программа=Graduate analytics; карьера=internships; AI=agent systems; exclude=football, parking; schedule=10:30; quiet=21:00-07:00", now=now)
    assert started["profile_persisted"] is False
    cid = started["context_id"]
    for action in ("ps", "mf"):
        handle_utd_profile_callback(db, f"{UTD_DRAFT_PREFIX}:{cid}:{action}", chat_id="42", now=now)
    preview = handle_utd_profile_callback(db, f"{UTD_DRAFT_PREFIX}:{cid}:pv", chat_id="42", now=now)
    meta = preview["proposal"]["metadata"]
    assert meta["timezone"] == "America/Chicago" and meta["daily_cap"] == 5
    assert meta["paused"] is True and meta["muted_sources"] == ["spouse_family"]
    assert meta["exclusions"] == ["football", "parking"] and meta["schedule"] == "10:30"
    assert meta["monitoring_authorized"] is False and meta["delivery_authorized"] is False
    saved = handle_utd_profile_callback(db, f"{UTD_CONFIRM_PREFIX}:{cid}:save", chat_id="42", now=now)
    replay = handle_utd_profile_callback(db, f"{UTD_CONFIRM_PREFIX}:{cid}:save", chat_id="42", now=now)
    assert saved["status"] == "ok" and replay["status"] == "already_confirmed"
    assert load_confirmed_utd_profile(db, now=now) is not None
    assert load_confirmed_utd_profile(db, now=now + timedelta(days=121)) is None


def test_confirmation_copy_truthfully_describes_existing_runtime_effect(tmp_path: Path) -> None:
    db = tmp_path / "m.db"; _init_db(db); now = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
    preview_text = render_utd_watch_preview({"expires_at": "2026-12-01T00:00:00Z"})
    assert "уже отдельно включённым runtime" in preview_text
    cid = start_utd_profile_onboarding(db, chat_id="42", now=now)["context_id"]
    handle_utd_profile_callback(db, f"{UTD_DRAFT_PREFIX}:{cid}:pv", chat_id="42", now=now)
    saved = handle_utd_profile_callback(db, f"{UTD_CONFIRM_PREFIX}:{cid}:save", chat_id="42", now=now)
    assert "не запускает runtime" in saved["message"] and "может быть прочитан" in saved["message"]
    profile = load_runtime_utd_profile(db, now=now)
    assert subscription_effect(profile, now=now, runtime_enabled=False)["reason"] == "runtime_disabled"
    assert subscription_effect(profile, now=now, runtime_enabled=True)["collect"] is True


def test_international_student_question_does_not_match_career_internship_marker() -> None:
    from assistant.utd_profile_schema import classify_utd_question

    assert classify_utd_question("что мне нельзя пропустить как international student?") == "isso"


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


def test_confirmed_unsubscribe_appends_tombstone_and_blocks_profile(tmp_path: Path) -> None:
    db = tmp_path / "m.db"; _init_db(db); now = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
    cid = start_utd_profile_onboarding(db, chat_id="42", now=now)["context_id"]
    handle_utd_profile_callback(db, f"{UTD_DRAFT_PREFIX}:{cid}:pv", chat_id="42", now=now)
    handle_utd_profile_callback(db, f"{UTD_CONFIRM_PREFIX}:{cid}:save", chat_id="42", now=now)
    cancel = build_utd_subscription_cancel_proposal(db)
    assert cancel["status"] == "needs_confirmation" and cancel["persisted"] is False
    result = confirm_utd_subscription_cancel(db, cancel, now=now)
    assert result["event_type"] == "deleted"
    assert load_confirmed_utd_profile(db, now=now) is None


def test_unsubscribe_callback_is_chat_bound_and_revision_bound(tmp_path: Path) -> None:
    db = tmp_path / "m.db"; _init_db(db); now = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
    cid = start_utd_profile_onboarding(db, chat_id="42", now=now)["context_id"]
    handle_utd_profile_callback(db, f"{UTD_DRAFT_PREFIX}:{cid}:pv", chat_id="42", now=now)
    handle_utd_profile_callback(db, f"{UTD_CONFIRM_PREFIX}:{cid}:save", chat_id="42", now=now)
    preview = start_utd_subscription_cancel(db, chat_id="42", now=now)
    callback = preview["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert handle_utd_subscription_callback(db, callback, chat_id="other", now=now)["status"] == "expired"
    result = handle_utd_subscription_callback(db, callback, chat_id="42", now=now)
    assert result["event_type"] == "deleted"
    assert load_confirmed_utd_profile(db, now=now) is None


def test_unsubscribe_rejects_a_stale_profile_revision(tmp_path: Path) -> None:
    db = tmp_path / "m.db"; _init_db(db); now = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
    cid = start_utd_profile_onboarding(db, chat_id="42", now=now)["context_id"]
    preview_profile = handle_utd_profile_callback(db, f"{UTD_DRAFT_PREFIX}:{cid}:pv", chat_id="42", now=now)
    saved = handle_utd_profile_callback(db, f"{UTD_CONFIRM_PREFIX}:{cid}:save", chat_id="42", now=now)
    cancel = build_utd_subscription_cancel_proposal(db)
    # Append an edit to the same object after preview: the old delete must not win.
    proposal = dict(preview_profile["proposal"])
    proposal["operation"] = "edit"; proposal["target_memory_id"] = saved["memory_id"]
    from assistant.pi_memory import build_memory_proposal, confirm_memory_proposal
    edited = build_memory_proposal("watch_topic", proposal)
    assert confirm_memory_proposal(db, {"proposal": edited["proposal"], "confirmation_token": edited["confirmation"]["token"]})["event_type"] == "edited"
    assert confirm_utd_subscription_cancel(db, cancel, now=now)["status"] == "stale_subscription"
    # The final append independently rechecks the exact revision under its
    # write transaction. This models an edit arriving after the preview check.
    direct = confirm_memory_proposal(db, {"proposal": cancel["proposal"], "confirmation_token": cancel["confirmation"]["token"]})
    assert direct["status"] == "invalid_target" and "revision changed" in direct["message"]


def test_confirmed_pause_is_visible_lifecycle_action_and_blocks_profile(tmp_path: Path) -> None:
    db = tmp_path / "m.db"; _init_db(db); now = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
    cid = start_utd_profile_onboarding(db, chat_id="42", now=now)["context_id"]
    handle_utd_profile_callback(db, f"{UTD_DRAFT_PREFIX}:{cid}:pv", chat_id="42", now=now)
    saved = handle_utd_profile_callback(db, f"{UTD_CONFIRM_PREFIX}:{cid}:save", chat_id="42", now=now)
    assert saved["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "utds:pause:preview"
    preview = handle_utd_subscription_callback(db, "utds:pause:preview", chat_id="42", now=now)
    callback = preview["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert handle_utd_subscription_callback(db, callback, chat_id="42", now=now)["event_type"] == "edited"
    assert load_confirmed_utd_profile(db, now=now)["paused"] is True


def test_confirmation_claim_prevents_cancel_race_for_profile_pause_and_unsubscribe(tmp_path: Path) -> None:
    """A cancel arriving after the atomic claim cannot erase the exact preview."""
    import assistant.utd_profile as utd
    db = tmp_path / "m.db"; _init_db(db); now = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
    profile_context = start_utd_profile_onboarding(db, chat_id="42", now=now)["context_id"]
    handle_utd_profile_callback(db, f"{UTD_DRAFT_PREFIX}:{profile_context}:pv", chat_id="42", now=now)
    assert utd._claim_utd_preview(db, context_id=profile_context, chat_id="42", now=now)
    assert handle_utd_profile_callback(db, f"{UTD_DRAFT_PREFIX}:{profile_context}:cx", chat_id="42", now=now)["status"] == "expired"
    assert utd._finish_utd_preview_claim(db, context_id=profile_context, status="previewed") is None
    handle_utd_profile_callback(db, f"{UTD_CONFIRM_PREFIX}:{profile_context}:save", chat_id="42", now=now)
    for action in ("pause", "cancel"):
        preview = (start_utd_subscription_pause if action == "pause" else start_utd_subscription_cancel)(db, chat_id="42", now=now)
        context_id = preview["context_id"]
        assert utd._claim_utd_preview(db, context_id=context_id, chat_id="42", now=now)
        assert handle_utd_subscription_callback(db, f"utds:{context_id}:cancel", chat_id="42", now=now)["status"] == "expired"
        with sqlite3.connect(db) as c:
            assert c.execute("SELECT status FROM prm_post_answer_proposals WHERE context_id=?", (context_id,)).fetchone()[0] == "confirming"
        utd._finish_utd_preview_claim(db, context_id=context_id, status="previewed")
