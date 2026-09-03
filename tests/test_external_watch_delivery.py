from pathlib import Path

from external_watch.delivery import DeliveryStore, deliver_candidates, delivery_enabled, handle_feedback_callback, render_candidate
from external_watch.live import build_parser


def _candidate():
    return {"source":"calendar","item_key":"42:7","change_type":"updated","payload":{"title":"AI Career Fair","url":"https://calendar.utdallas.edu/event/x"},"relevance":{"relevant":True,"urgent":False,"score":9,"categories":["career","ai"],"reason":"AI career match"}}


def test_delivery_is_triple_gated(tmp_path):
    env={"UTD_WATCH_DELIVERY_ENABLED":"1","UTD_WATCH_KILL_SWITCH":"1"}
    assert not delivery_enabled(explicit=True, env=env)
    assert not delivery_enabled(explicit=False, env={"UTD_WATCH_DELIVERY_ENABLED":"1"})


def test_notification_copy_is_human_readable_and_actionable():
    text = render_candidate(
        {
            "source": "calendar",
            "item_key": "program:deadline",
            "change_type": "updated",
            "payload": {
                "title": "Late Registration deadline",
                "url": "https://calendar.utdallas.edu/event/deadline",
                "instance": {"start": "2026-09-08T15:00:00-05:00"},
            },
            "relevance": {
                "relevant": True,
                "urgent": False,
                "categories": ["program"],
                "reason": "synthetic_program_match_for_confirmed_scope",
            },
        }
    )
    assert "Что изменилось: официальная страница изменилась." in text
    assert "Когда: 2026-09-08, 15:00 CT" in text
    assert "Почему тебе: совпадает с твоим подтверждённым UTD scope: program." in text
    assert "Что сделать: открой источник и проверь, касается ли срок твоей программы." in text
    assert "synthetic" not in text


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


def test_ordinary_candidates_are_one_digest_and_each_item_is_idempotent(tmp_path):
    sent=[]
    def sender(**kwargs):
        sent.append(kwargs); return 101
    env={"UTD_WATCH_DELIVERY_ENABLED":"1"}
    db=tmp_path/"shadow.db"
    first = deliver_candidates(
        [_candidate(), {**_candidate(), "item_key":"43:8", "payload":{"title":"Career workshop"}}],
        sidecar_db=db, token="t", chat_id="1", explicit_enable=True, env=env, sender=sender,
    )
    follow_up = deliver_candidates(
        [{**_candidate(), "item_key":"43:8", "payload":{"title":"Career workshop"}}],
        sidecar_db=db, token="t", chat_id="1", explicit_enable=True, env=env, sender=sender,
    )
    assert first["sent"] == 1
    assert "1. AI Career Fair" in sent[0]["text"]
    assert "2. Career workshop" in sent[0]["text"]
    assert follow_up["duplicates_blocked"] == 1
    assert len(sent) == 1
    assert DeliveryStore(db).feedback_summary()["delivered"] == 1


def test_daily_cap_is_enforced_across_delivery_runs(tmp_path):
    sent=[]
    def sender(**kwargs):
        sent.append(kwargs); return 101
    env={"UTD_WATCH_DELIVERY_ENABLED":"1"}
    db=tmp_path/"shadow.db"
    candidates=[{**_candidate(), "item_key":str(i)} for i in range(6)]
    result=deliver_candidates(candidates, sidecar_db=db, token="t", chat_id="1", explicit_enable=True, env=env, sender=sender)
    assert result["sent"] == 1 and result["daily_cap_blocked"] == 1
    later=deliver_candidates([{**_candidate(), "item_key":"later"}], sidecar_db=db, token="t", chat_id="1", explicit_enable=True, env=env, sender=sender)
    assert later["sent"] == 0 and later["daily_cap_blocked"] == 1


def test_pause_feedback_suppresses_delivery_for_24h_without_profile_mutation(tmp_path):
    sent=[]
    def sender(**kwargs):
        sent.append(kwargs); return 101
    env={"UTD_WATCH_DELIVERY_ENABLED":"1"}
    db=tmp_path/"shadow.db"
    key = "pause-key"
    store = DeliveryStore(db)
    store.record_delivery(key, _candidate(), None)

    result = handle_feedback_callback(db, f"utdw:{key}:pause")
    delivery = deliver_candidates(
        [{**_candidate(), "item_key":"later"}],
        sidecar_db=db, token="t", chat_id="1", explicit_enable=True, env=env, sender=sender,
    )

    assert result["action"] == "pause"
    assert "24 часа" in result["message"]
    assert delivery["sent"] == 0
    assert delivery["suppressed_by_pause"] == 1
    assert delivery["paused_until"]
    assert sent == []
    assert DeliveryStore(db).feedback_summary()["paused_until"]


def test_ordinary_digest_is_sent_at_most_once_per_day(tmp_path):
    sent=[]
    def sender(**kwargs):
        sent.append(kwargs); return 101
    env={"UTD_WATCH_DELIVERY_ENABLED":"1"}
    db=tmp_path/"shadow.db"

    first=deliver_candidates([_candidate()], sidecar_db=db, token="t", chat_id="1", explicit_enable=True, env=env, sender=sender)
    second=deliver_candidates([{**_candidate(), "item_key":"later"}], sidecar_db=db, token="t", chat_id="1", explicit_enable=True, env=env, sender=sender)

    assert first["sent"] == 1
    assert second["sent"] == 0
    assert second["ordinary_digest_blocked"] == 1
    assert len(sent) == 1


def test_live_cli_defaults_to_env_prm_db_and_shared_sidecar(monkeypatch):
    monkeypatch.setenv("AGENT_DB_PATH", "/tmp/agent.db")
    monkeypatch.setenv("UTD_WATCH_SIDECAR_DB", "/tmp/utd-shadow.db")

    args = build_parser().parse_args([])

    assert args.prm_db == "/tmp/agent.db"
    assert args.sidecar_db == "/tmp/utd-shadow.db"


def test_live_watch_systemd_template_is_separate_gated_timer():
    root = Path(__file__).resolve().parents[1]
    service = (root / "systemd" / "telegram-utd-watch.service").read_text()
    timer = (root / "systemd" / "telegram-utd-watch.timer").read_text()

    assert "Type=oneshot" in service
    assert "EnvironmentFile=/srv/openclaw-you/.env" in service
    assert "UTD_WATCH_DELIVERY_ENABLED=1" in service
    assert "UTD_WATCH_KILL_SWITCH=0" in service
    assert "-m external_watch.live --enable-shadow --enable-delivery" in service
    assert "src/main.py ingest" not in service
    assert "weekly-intelligence" not in service
    assert "OnUnitActiveSec=45m" in timer
    assert "Persistent=false" in timer
    assert "Unit=telegram-utd-watch.service" in timer
