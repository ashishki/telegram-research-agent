import json
import sqlite3
from datetime import datetime, timezone

from external_watch.profile import load_confirmed_utd_profile


def _db(path, metadata, event_type="created"):
    db=sqlite3.connect(path)
    db.execute("CREATE TABLE personal_memory_events(id INTEGER PRIMARY KEY, memory_id TEXT, event_type TEXT, object_type TEXT, metadata_json TEXT, confirmation_token_hash TEXT, confirmation_receipt_json TEXT)")
    db.execute("INSERT INTO personal_memory_events(memory_id,event_type,object_type,metadata_json,confirmation_token_hash,confirmation_receipt_json) VALUES(?,?,?,?,?,?)", ("fixture-profile",event_type,"watch_topic",json.dumps({**metadata, "profile_schema_version":"utd_profile.v1"}),"fixture",json.dumps({"confirmation_token_hash":"fixture"})))
    db.commit(); db.close()


def test_profile_reader_is_read_only_and_honors_expiry(tmp_path):
    path=tmp_path/"prm.db"
    meta={"capability":"utd_profile_preview_watch","expires_at":"2026-12-01T00:00:00+00:00","categories":["program"]}
    _db(path, meta)
    loaded=load_confirmed_utd_profile(path, now=datetime(2026,8,28,tzinfo=timezone.utc))
    assert loaded["categories"] == ["program"]
    assert load_confirmed_utd_profile(path, now=datetime(2027,1,1,tzinfo=timezone.utc)) is None


def test_profile_reader_honors_delete_tombstone(tmp_path):
    path=tmp_path/"prm.db"
    meta={"capability":"utd_profile_preview_watch","expires_at":"2026-12-01T00:00:00+00:00"}
    _db(path, meta, event_type="deleted")
    assert load_confirmed_utd_profile(path, now=datetime(2026,8,28,tzinfo=timezone.utc)) is None


def test_profile_reader_does_not_fall_back_past_a_tombstone(tmp_path):
    path = tmp_path / "prm.db"
    meta = {"capability": "utd_profile_preview_watch", "expires_at": "2026-12-01T00:00:00+00:00"}
    _db(path, meta)
    db = sqlite3.connect(path)
    db.execute("INSERT INTO personal_memory_events(memory_id,event_type,object_type,metadata_json,confirmation_token_hash,confirmation_receipt_json) VALUES(?,?,?,?,?,?)", ("fixture-profile", "deleted", "watch_topic", json.dumps(meta), "fixture", json.dumps({"confirmation_token_hash":"fixture"})))
    db.commit(); db.close()
    assert load_confirmed_utd_profile(path, now=datetime(2026, 8, 28, tzinfo=timezone.utc)) is None


def test_profile_reader_rejects_a_receipt_not_linked_to_event_token(tmp_path):
    path = tmp_path / "prm.db"
    _db(path, {"capability": "utd_profile_preview_watch", "expires_at": "2026-12-01T00:00:00+00:00"})
    db = sqlite3.connect(path)
    db.execute("UPDATE personal_memory_events SET confirmation_receipt_json=?", (json.dumps({"confirmation_token_hash": "forged"}),))
    db.commit(); db.close()
    assert load_confirmed_utd_profile(path, now=datetime(2026, 8, 28, tzinfo=timezone.utc)) is None


def test_newer_invalid_profile_never_falls_back_to_older_active_profile(tmp_path):
    path = tmp_path / "prm.db"
    meta = {"capability": "utd_profile_preview_watch", "expires_at": "2026-12-01T00:00:00+00:00"}
    _db(path, meta)
    db = sqlite3.connect(path)
    db.execute("INSERT INTO personal_memory_events(memory_id,event_type,object_type,metadata_json,confirmation_token_hash,confirmation_receipt_json) VALUES(?,?,?,?,?,?)", ("newer-profile", "created", "watch_topic", json.dumps({**meta, "profile_schema_version": "utd_profile.v1"}), "real", json.dumps({"confirmation_token_hash": "forged"})))
    db.commit(); db.close()
    assert load_confirmed_utd_profile(path, now=datetime(2026, 8, 28, tzinfo=timezone.utc)) is None


def test_newer_malformed_receipt_never_falls_back_to_older_active_profile(tmp_path):
    path = tmp_path / "prm.db"; meta = {"capability": "utd_profile_preview_watch", "expires_at": "2026-12-01T00:00:00+00:00"}
    _db(path, meta)
    db = sqlite3.connect(path)
    db.execute("INSERT INTO personal_memory_events(memory_id,event_type,object_type,metadata_json,confirmation_token_hash,confirmation_receipt_json) VALUES(?,?,?,?,?,?)", ("newer-profile", "created", "watch_topic", json.dumps({**meta, "profile_schema_version": "utd_profile.v1"}), "real", "not-json"))
    db.commit(); db.close()
    assert load_confirmed_utd_profile(path, now=datetime(2026, 8, 28, tzinfo=timezone.utc)) is None
