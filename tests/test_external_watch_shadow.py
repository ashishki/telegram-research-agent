import json
import sqlite3
from pathlib import Path

from external_watch.adapters import canonical_hash, parse_localist
from external_watch.relevance import classify
from external_watch.store import ShadowStore

ROOT = Path(__file__).parents[1]


def _profile(**updates):
    profile = {
        "categories": ["program", "career", "ai", "isso", "benefits", "spouse_family"],
        "paused": False,
        "muted_sources": [],
    }
    profile.update(updates)
    return profile


def test_real_calendar_fixture_preserves_event_instance_identity_and_offset():
    fixture = json.loads((ROOT / "tests/fixtures/external_watch/calendar.real.20260828.json").read_text())
    raw = json.dumps(fixture["content"]).encode()
    items = parse_localist(raw)
    registrar = next(item for item in items if item["event_id"] == "49277395432862")
    assert registrar["item_key"] == "event:49277395432862:instance:49277395446182"
    assert registrar["instance"]["start"] == "2026-08-28T00:00:00-05:00"
    assert registrar["status"] == "live"
    assert "Academic Calendar" in registrar["topics"]


def test_localist_preserves_dst_source_offsets():
    payload = {"events": [
        {"event": {"id": 1, "title": "before DST", "status": "live", "event_instances": [{"event_instance": {"id": 10, "start": "2026-10-31T10:00:00-05:00", "end": None, "all_day": False}}]}},
        {"event": {"id": 2, "title": "after DST", "status": "live", "event_instances": [{"event_instance": {"id": 20, "start": "2026-11-02T10:00:00-06:00", "end": None, "all_day": False}}]}},
    ]}
    items = parse_localist(json.dumps(payload).encode())
    assert items[0]["instance"]["start"].endswith("-05:00")
    assert items[1]["instance"]["start"].endswith("-06:00")


def test_sidecar_is_idempotent_and_cancel_reinstate_safe(tmp_path):
    store = ShadowStore(tmp_path / "shadow.db")
    active = {"item_key": "event:1:instance:10", "event_id": "1", "title": "Deadline", "status": "live"}
    relevant = {active["item_key"]: {"relevant": True, "categories": ["program"]}}
    first = store.apply_success("calendar", [active], {active["item_key"]: canonical_hash(active)}, relevant)
    second = store.apply_success("calendar", [active], {active["item_key"]: canonical_hash(active)}, relevant)
    assert [x["change_type"] for x in first] == ["new"]
    assert second == []

    cancelled = {**active, "status": "cancelled"}
    third = store.apply_success("calendar", [cancelled], {active["item_key"]: canonical_hash(cancelled)}, relevant)
    fourth = store.apply_success("calendar", [active], {active["item_key"]: canonical_hash(active)}, relevant)
    assert [x["change_type"] for x in third] == ["cancelled"]
    assert [x["change_type"] for x in fourth] == ["reinstated"]


def test_source_error_health_does_not_turn_existing_item_into_disappearance(tmp_path):
    store = ShadowStore(tmp_path / "shadow.db")
    item = {"item_key": "event:1", "event_id": "1", "title": "Event", "status": "live"}
    store.apply_success("calendar", [item], {"event:1": canonical_hash(item)}, {"event:1": {"relevant": True}})
    store.health("calendar", "error", error_code="rate_limited", detail="HTTP 429")
    with sqlite3.connect(tmp_path / "shadow.db") as db:
        state = db.execute("SELECT state FROM items WHERE source='calendar' AND item_key='event:1'").fetchone()[0]
        disappearances = db.execute("SELECT COUNT(*) FROM changes WHERE change_type='disappeared'").fetchone()[0]
    assert state == "active"
    assert disappearances == 0


def test_spouse_family_requires_explicit_eligibility_wording():
    profile = _profile(categories=["spouse_family"])
    generic = {"title": "International student social event", "audiences": ["International Students"]}
    explicit = {"title": "International student spouse and family welcome", "audiences": ["International Students"]}
    assert classify(generic, profile)["relevant"] is False
    assert classify(explicit, profile)["relevant"] is True
