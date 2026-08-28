from external_watch.selection import select_candidates


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
