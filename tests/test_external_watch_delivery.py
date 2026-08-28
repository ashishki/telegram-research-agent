from external_watch.delivery import DeliveryStore, deliver_candidates, delivery_enabled, handle_feedback_callback


def _candidate():
    return {"source":"calendar","item_key":"42:7","change_type":"updated","payload":{"title":"AI Career Fair","url":"https://calendar.utdallas.edu/event/x"},"relevance":{"relevant":True,"urgent":False,"score":9,"categories":["career","ai"],"reason":"AI career match"}}


def test_delivery_is_triple_gated(tmp_path):
    env={"UTD_WATCH_DELIVERY_ENABLED":"1","UTD_WATCH_KILL_SWITCH":"1"}
    assert not delivery_enabled(explicit=True, env=env)
    assert not delivery_enabled(explicit=False, env={"UTD_WATCH_DELIVERY_ENABLED":"1"})


def test_delivery_receipt_blocks_duplicate_and_feedback(tmp_path):
    sent=[]
    def sender(**kwargs):
        sent.append(kwargs); return 101
    env={"UTD_WATCH_DELIVERY_ENABLED":"1"}
    db=tmp_path/"shadow.db"
    first=deliver_candidates([_candidate()], sidecar_db=db, token="t", chat_id="1", explicit_enable=True, env=env, sender=sender)
    second=deliver_candidates([_candidate()], sidecar_db=db, token="t", chat_id="1", explicit_enable=True, env=env, sender=sender)
    assert first["sent"] == 1 and second["duplicates_blocked"] == 1 and len(sent) == 1
    data=sent[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    result=handle_feedback_callback(db, data)
    assert result["action"] == "useful"
    assert DeliveryStore(db).feedback_summary()["observed_precision"] == 1.0
