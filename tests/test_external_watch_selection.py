from external_watch.selection import select_candidates
from external_watch.editions import classify_event_change, project_edition


def test_edition_keeps_times_and_collapses_repost_family_without_writing():
    edition = project_edition([{"source":"calendar","event_id":"1","url":"https://x/e","title":"Deadline","published_at":"2026-09-01","updated_at":"2026-09-02","fetched_at":"2026-09-03"}, {"source":"calendar","event_id":"1","url":"https://x/e","title":"Deadline","updated_at":"2026-09-01"}], topic_id="t", window_start="2026-09-01", window_end="2026-09-08", checked_at="2026-09-03T12:00:00Z")
    assert len(edition["events"]) == 1 and edition["events"][0]["publication_at"] == "2026-09-01"
    assert edition["events"][0]["fetch_at"] == "2026-09-03" and edition["write_performed"] is False
    assert classify_event_change(edition["events"][0], None) == "disappeared"


def test_edition_preserves_instances_collapses_reposts_and_classifies_material_changes():
    items = [
        {"source":"calendar","event_id":"1","instance":{"id":"a"},"url":"https://x/a","title":"A","material_text":"v1","updated_at":"2026-01-01"},
        {"source":"calendar","event_id":"1","instance":{"id":"b"},"url":"https://x/b","title":"B","material_text":"v1","updated_at":"2026-01-01"},
        {"source":"calendar","event_id":"2","url":"https://x/c","title":"C","material_text":"v1","updated_at":"2026-01-01"},
        {"source":"other","event_id":"3","url":"https://x/c","title":"C repost","material_text":"v2","updated_at":"2026-01-02"},
    ]
    edition = project_edition(items, topic_id="t", window_start="2026-01-01T00:00:00Z", window_end="2026-01-03T00:00:00Z", checked_at="c")
    assert len(edition["events"]) == 3 and edition["edition_id"]
    old, changed = edition["events"][0], {**edition["events"][0], "fingerprint": "changed"}
    assert classify_event_change(old, changed) == "material_update"
    assert classify_event_change(old, {**old, "payload": {"status": "canceled"}}) == "cancelled"


def test_edition_is_bounded_and_carries_prior_change_states_without_writing():
    prior = project_edition(
        [{"source":"calendar", "event_id":"one", "url":"https://x/one", "title":"Old", "published_at":"2026-09-01T09:00:00Z", "updated_at":"2026-09-01T09:00:00Z", "material_text":"v1"}],
        topic_id="t", window_start="2026-09-01T00:00:00Z", window_end="2026-09-01T23:00:00Z", checked_at="2026-09-01T10:00:00Z",
    )
    current = project_edition(
        [
            {"source":"calendar", "event_id":"one", "url":"https://x/one", "title":"Old", "published_at":"2026-09-01T09:00:00Z", "updated_at":"2026-09-02T09:00:00Z", "material_text":"v2"},
            {"source":"calendar", "event_id":"bad", "url":"https://x/bad", "title":"Bad", "updated_at":"not-a-time"},
        ],
        topic_id="t", window_start="2026-09-02T00:00:00Z", window_end="2026-09-02T23:00:00Z", checked_at="2026-09-02T10:00:00Z", prior_events=prior["events"],
    )
    assert current["rejected_invalid_time_count"] == 1
    assert current["events"][0]["change_type"] == "material_update"
    disappeared = project_edition([], topic_id="t", window_start="2026-09-03T00:00:00Z", window_end="2026-09-03T23:00:00Z", checked_at="2026-09-03T10:00:00Z", prior_events=current["events"])
    assert disappeared["events"][0]["change_type"] == "disappeared"
    assert disappeared["write_performed"] is False


def _change(key, score, *, urgent=False, change_type="new"):
    return {"source":"calendar","item_key":key,"change_type":change_type,"payload":{"title":key},"relevance":{"relevant":True,"score":score,"urgent":urgent,"categories":["program"]}}


def test_selection_respects_cap_and_prioritizes_urgent_material_changes():
    changes=[_change(str(i), i) for i in range(10)] + [_change("urgent", 60, urgent=True, change_type="cancelled")]
    selected=select_candidates(changes,{"daily_cap":5,"frequency":"daily_digest","paused":False})
    assert len(selected)==5
    assert selected[0]["item_key"] == "urgent"


def test_selection_suppresses_disappearance_and_urgent_only_nonurgent():
    changes=[_change("a",90), _change("b",90,change_type="disappeared"), _change("c",70,urgent=True)]
    selected=select_candidates(changes,{"daily_cap":5,"frequency":"urgent_only","paused":False})
    assert [x["item_key"] for x in selected] == ["c"]
