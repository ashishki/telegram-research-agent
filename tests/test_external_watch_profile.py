import json
import sqlite3
from datetime import datetime, timezone

from external_watch.profile import load_confirmed_utd_profile


def _db(path, metadata, event_type="saved"):
    db=sqlite3.connect(path)
    db.execute("CREATE TABLE personal_memory_events(id INTEGER PRIMARY KEY, event_type TEXT, object_type TEXT, metadata_json TEXT)")
    db.execute("INSERT INTO personal_memory_events(event_type,object_type,metadata_json) VALUES(?,?,?)", (event_type,"watch_topic",json.dumps(metadata)))
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
