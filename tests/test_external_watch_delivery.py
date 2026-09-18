from pathlib import Path
from datetime import datetime, timedelta, timezone
from threading import Barrier, Thread
from urllib.error import HTTPError
from zoneinfo import ZoneInfo
import pytest
import sys

from bot.telegram_delivery import TelegramAmbiguousDelivery, TelegramKnownRejection, _send_text_internal, _telegram_request
from external_watch.delivery import DeliveryStore, KnownDeliveryFailure, build_feedback_markup, deliver_candidates, deliver_outbox_item, delivery_enabled, delivery_key, handle_feedback_callback, render_candidate, render_on_demand_edition
from external_watch.selection import select_candidates
from external_watch.store import ShadowStore
from external_watch.adapters import canonical_hash


def test_on_demand_edition_is_deduplicated_bounded_and_distinguishes_health():
    events = [{"event_id":"a","repost_family_id":"same","title":"One","canonical_url":"https://calendar.utdallas.edu/a"}, {"event_id":"b","repost_family_id":"same","title":"Repost"}]
    assert render_on_demand_edition(events, source_health={"calendar":"healthy"}).count("Почему это может быть полезно:") == 1
    assert "Новых релевантных" in render_on_demand_edition([], source_health={"calendar":"healthy"})
    assert "недоступны" in render_on_demand_edition([], source_health={"calendar":"error"})
    assert "Покрытие источников не указано" in render_on_demand_edition([])


def test_on_demand_edition_is_stable_detail_cap_safe_and_keeps_partial_health_visible():
    events = [
        {"event_id": "b", "repost_family_id": "family", "title": "Repost", "canonical_url": "https://calendar.utdallas.edu/b"},
        {"event_id": "a", "repost_family_id": "family", "title": "Original", "canonical_url": "https://calendar.utdallas.edu/a", "update_at": "2026-09-17T09:30:00Z", "payload": {"material_text": "A material correction."}},
    ]
    text = render_on_demand_edition(list(reversed(events)), source_health={"calendar": "healthy", "isso": "error"}, detail_event_id="a")
    assert text.startswith("Детали события") and "Original" in text
    assert "A material correction." in text and "2026-09-17, 04:30 CT" in text
    assert "Не все источники доступны: isso." in text
    huge = [{"event_id": str(i), "title": "x" * 1000, "canonical_url": f"https://calendar.utdallas.edu/{i}"} for i in range(12)]
    bounded = render_on_demand_edition(huge)
    assert len(bounded) <= 4096
    assert not bounded.endswith("x")


def test_on_demand_edition_labels_old_repost_change_and_all_omissions():
    events = [{
        "event_id":"old", "repost_family_id":"origin", "title":"Old origin", "canonical_url":"https://calendar.utdallas.edu/old",
        "publication_at":"2026-01-01T10:00:00Z", "update_at":"2026-09-17T10:00:00Z", "change_type":"material_update",
        "payload":{"relevance":{"categories":["career"], "reason":"deadline changed"}},
    }]
    text = render_on_demand_edition(events, source_health={"calendar":"healthy"})
    assert "существенное исправление" in text and "Опубликовано:" in text
    many = [{"event_id":str(i), "title":"Event", "canonical_url":f"https://calendar.utdallas.edu/{i}"} for i in range(13)]
    assert "Не показано событий: 1" in render_on_demand_edition(many, source_health={"x":"healthy"})
    huge_health = {"x" * 1000: "error" for _ in range(1)}
    assert len(render_on_demand_edition([], source_health=huge_health)) <= 4096
    oversized = [{"event_id":str(i), "title":"x" * 5000 if i == 0 else "Event", "canonical_url":f"https://calendar.utdallas.edu/{i}"} for i in range(13)]
    output = render_on_demand_edition(oversized, source_health={"x":"healthy"})
    assert "Не показано событий: 13" in output and len(output) <= 4096
from external_watch.live import build_parser


_CONFIRMED_SUBSCRIPTION = {"subscription_confirmed": True, "subscription_status": "active", "expires_at": "2026-12-01T00:00:00Z", "timezone": "America/Chicago", "quiet_hours": {}, "frequency": "daily_digest", "schedule": datetime.now(ZoneInfo("America/Chicago")).strftime("%H:%M"), "daily_cap": 5, "categories": ["career", "ai", "program", "isso", "benefits", "spouse_family"]}


@pytest.fixture(autouse=True)
def _confirmed_subscription_for_delivery_fixtures(monkeypatch):
    """Every positive delivery test must model the confirmed runtime contract."""
    original_candidates = deliver_candidates
    original_item = deliver_outbox_item
    monkeypatch.setattr(sys.modules[__name__], "deliver_candidates", lambda *args, **kwargs: original_candidates(*args, subscription=kwargs.pop("subscription", _CONFIRMED_SUBSCRIPTION), **kwargs))
    monkeypatch.setattr(sys.modules[__name__], "deliver_outbox_item", lambda *args, **kwargs: original_item(*args, subscription=kwargs.pop("subscription", _CONFIRMED_SUBSCRIPTION), **kwargs))


def _candidate():
    return {"source":"calendar","item_key":"42:7","change_type":"updated","payload":{"title":"AI Career Fair","change_summary":"открыта регистрация на ярмарку вакансий","url":"https://calendar.utdallas.edu/event/x"},"relevance":{"relevant":True,"urgent":False,"score":9,"categories":["career","ai"],"reason":"AI career match"}}


def _candidate_payload(**updates):
    return {**_candidate()["payload"], **updates}


def test_delivery_is_triple_gated(tmp_path):
    env={"UTD_WATCH_DELIVERY_ENABLED":"1","UTD_WATCH_KILL_SWITCH":"1"}
    assert not delivery_enabled(explicit=True, env=env)
    assert not delivery_enabled(explicit=False, env={"UTD_WATCH_DELIVERY_ENABLED":"1"})


def test_final_send_reloads_profile_and_blocks_a_cancelled_queued_item(tmp_path, monkeypatch):
    """A stale caller snapshot must not send after canonical cancellation."""
    from external_watch import profile as profile_module
    monkeypatch.setattr(profile_module, "load_confirmed_utd_profile", lambda *_args, **_kwargs: None)
    db = tmp_path / "shadow.db"
    key = delivery_key(_candidate())
    DeliveryStore(db).enqueue_outbox(key, _candidate())
    sent = []
    result = deliver_outbox_item(
        sidecar_db=db, key=key, token="t", chat_id="1", sender=lambda **kwargs: sent.append(kwargs) or 1,
        explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED": "1"}, profile_db=tmp_path / "canonical.db",
    )
    assert result == "subscription_blocked"
    assert sent == [] and DeliveryStore(db).outbox_state(key) == "pending"


def test_final_send_cancels_work_bound_to_a_superseded_profile(tmp_path, monkeypatch):
    from external_watch import profile as profile_module
    profile_b = {**_CONFIRMED_SUBSCRIPTION, "subscription_memory_id": "B", "subscription_event_id": 9}
    monkeypatch.setattr(profile_module, "load_confirmed_utd_profile", lambda *_args, **_kwargs: profile_b)
    db = tmp_path / "shadow.db"; candidate = {**_candidate(), "subscription_memory_id": "A", "subscription_event_id": 4}
    key = delivery_key(candidate); DeliveryStore(db).enqueue_outbox(key, candidate)
    assert deliver_outbox_item(sidecar_db=db, key=key, token="t", chat_id="1", sender=lambda **_kwargs: pytest.fail("must not send"), explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED": "1"}, profile_db=tmp_path / "canonical.db") == "subscription_blocked"
    assert DeliveryStore(db).outbox_state(key) == "cancelled"


def test_terminal_guard_blocks_lifecycle_change_after_lease_and_render(tmp_path, monkeypatch):
    """The send decision is revalidated after rendering, immediately before transport."""
    from external_watch import profile as profile_module
    db = tmp_path / "shadow.db"
    profile_a = {**_CONFIRMED_SUBSCRIPTION, "subscription_memory_id": "A", "subscription_event_id": 4}
    candidate = {**_candidate(), "subscription_memory_id": "A", "subscription_event_id": 4}
    key = delivery_key(candidate); DeliveryStore(db).enqueue_outbox(key, candidate)
    lifecycle_changed = {"value": False}
    monkeypatch.setattr(profile_module, "load_confirmed_utd_profile", lambda *_args, **_kwargs: None if lifecycle_changed["value"] else profile_a)
    import external_watch.delivery as delivery_module
    original_render = delivery_module.render_candidate
    def render_then_cancel(*args, **kwargs):
        lifecycle_changed["value"] = True
        return original_render(*args, **kwargs)
    monkeypatch.setattr(delivery_module, "render_candidate", render_then_cancel)
    sent = []
    result = deliver_outbox_item(sidecar_db=db, key=key, token="t", chat_id="1", sender=lambda **kwargs: sent.append(kwargs) or 1, explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED": "1"}, profile_db=tmp_path / "canonical.db")
    assert result == "subscription_blocked" and sent == []
    assert DeliveryStore(db).outbox_state(key) == "cancelled"


def test_terminal_guard_rechecks_a_mutated_kill_control_and_unit_does_not_override_it(tmp_path, monkeypatch):
    """A later oneshot invocation can read the operator's EnvironmentFile value."""
    from external_watch import profile as profile_module
    db = tmp_path / "shadow.db"; profile_a = {**_CONFIRMED_SUBSCRIPTION, "subscription_memory_id": "A", "subscription_event_id": 4}
    candidate = {**_candidate(), "subscription_memory_id": "A", "subscription_event_id": 4}; key = delivery_key(candidate)
    DeliveryStore(db).enqueue_outbox(key, candidate)
    monkeypatch.setattr(profile_module, "load_confirmed_utd_profile", lambda *_args, **_kwargs: profile_a)
    env = {"UTD_WATCH_DELIVERY_ENABLED": "1", "UTD_WATCH_KILL_SWITCH": "0"}
    import external_watch.delivery as delivery_module
    original_render = delivery_module.render_candidate
    monkeypatch.setattr(delivery_module, "render_candidate", lambda *args, **kwargs: (env.__setitem__("UTD_WATCH_KILL_SWITCH", "1") or original_render(*args, **kwargs)))
    assert deliver_outbox_item(sidecar_db=db, key=key, token="t", chat_id="1", sender=lambda **_: pytest.fail("must not send"), explicit_enable=True, env=env, profile_db=tmp_path / "canonical.db") == "subscription_blocked"
    unit = (Path(__file__).parents[1] / "systemd/telegram-utd-watch.service").read_text()
    assert "Environment=UTD_WATCH_KILL_SWITCH=0" not in unit and "EnvironmentFile=" in unit


def test_source_selection_and_outbox_keep_revision_binding_until_final_send(tmp_path, monkeypatch):
    """A source record selected under A cannot be relabelled as later profile B."""
    source = ShadowStore(tmp_path / "shadow.db")
    item = {"item_key": "event:1", "event_id": "1", "title": "Career deadline", "url": "https://calendar.utdallas.edu/1", "status": "live"}
    profile_a = {**_CONFIRMED_SUBSCRIPTION, "subscription_memory_id": "A", "subscription_event_id": 4}
    pending = source.apply_success("calendar", [item], {"event:1": canonical_hash(item)}, {"event:1": {"relevant": True, "urgent": True, "categories": ["career"], "score": 9}}, profile_binding=profile_a)
    selected = select_candidates(pending, profile_a)
    assert selected[0]["subscription_memory_id"] == "A" and selected[0]["subscription_event_id"] == 4
    from external_watch import profile as profile_module
    monkeypatch.setattr(profile_module, "load_confirmed_utd_profile", lambda *_args, **_kwargs: {**profile_a, "subscription_memory_id": "B", "subscription_event_id": 5})
    sent = []
    result = deliver_candidates(selected, sidecar_db=tmp_path / "shadow.db", token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED": "1"}, sender=lambda **kwargs: sent.append(kwargs) or 1, profile_db=tmp_path / "canonical.db")
    assert result["sent"] == 0 and sent == []
    key = delivery_key(selected[0])
    assert DeliveryStore(tmp_path / "shadow.db").outbox_state(key) == "cancelled"


def test_urgent_candidate_can_send_outside_ordinary_schedule(tmp_path):
    candidate = {**_candidate(), "relevance": {**_candidate()["relevance"], "urgent": True}}
    sent = []
    result = deliver_candidates(
        [candidate], sidecar_db=tmp_path / "shadow.db", token="t", chat_id="1", explicit_enable=True,
        env={"UTD_WATCH_DELIVERY_ENABLED": "1"}, sender=lambda **kwargs: sent.append(kwargs) or 1,
        subscription={**_CONFIRMED_SUBSCRIPTION, "frequency": "daily_digest", "schedule": "09:00", "quiet_hours": {}},
        now=datetime(2026, 9, 15, 20, tzinfo=timezone.utc),
    )
    assert result["sent"] == 1 and len(sent) == 1


def test_urgent_only_never_sends_an_ordinary_candidate(tmp_path):
    result = deliver_candidates([_candidate()], sidecar_db=tmp_path / "shadow.db", token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED": "1"}, sender=lambda **_kwargs: pytest.fail("must not send"), subscription={**_CONFIRMED_SUBSCRIPTION, "frequency": "urgent_only"})
    assert result["sent"] == 0 and result["suppressed_by_subscription"] == "urgent_only"


def test_notification_copy_is_human_readable_and_actionable():
    text = render_candidate(
        {
            "source": "calendar",
            "item_key": "program:deadline",
            "change_type": "updated",
            "payload": {
                "title": "Late Registration deadline",
                "change_summary": "срок поздней регистрации перенесён на 8 сентября",
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
    assert "Что изменилось: срок поздней регистрации перенесён на 8 сентября." in text
    assert "Когда: 2026-09-08, 15:00 CT" in text
    assert "Почему тебе: совпадает с твоими подтверждёнными темами: программа." in text
    assert "Что сделать: открой источник и проверь, касается ли срок твоей программы." in text
    assert "synthetic" not in text


def test_updated_notification_without_a_change_summary_is_withheld():
    candidate = _candidate()
    candidate["payload"] = {key: value for key, value in candidate["payload"].items() if key != "change_summary"}

    assert render_candidate(candidate) == ""


def test_notification_keeps_primary_feedback_compact_and_reveals_settings_on_request(tmp_path):
    key = "compact-feedback"
    labels = [button["text"] for row in build_feedback_markup(key)["inline_keyboard"] for button in row]
    assert labels == ["👍 Полезно", "👎 Шум", "Настроить уведомления"]

    store = DeliveryStore(tmp_path / "shadow.db")
    store.record_delivery(key, _candidate(), None)
    result = handle_feedback_callback(tmp_path / "shadow.db", f"utdw:{key}:settings")
    settings_labels = [button["text"] for row in result["reply_markup"]["inline_keyboard"] for button in row]
    assert result["action"] == "settings"
    assert settings_labels == ["Больше похожего", "Меньше похожего", "Источник неинтересен", "Пауза на 24 ч"]
    assert store.feedback_summary()["feedback"] == {}


def test_final_renderer_requires_primary_source_and_is_telegram_bounded():
    assert render_candidate({**_candidate(), "payload": _candidate_payload(title="missing source", url="")}) == ""
    huge = {**_candidate(), "payload": _candidate_payload(title="x" * 10000, url="https://calendar.utdallas.edu/event/x")}
    text = render_candidate(huge, depth="deep")
    assert text and len(text) <= 4096 and "https://calendar.utdallas.edu/event/x" in text
    assert "Source:" in render_candidate(_candidate(), language="en", depth="standard")


def test_final_renderer_withholds_off_policy_links_for_alerts_and_digests():
    off_policy = {**_candidate(), "payload": _candidate_payload(title="Off policy", url="https://tracker.example/redirect")}
    assert render_candidate(off_policy) == ""
    assert render_candidate({"payload": {"title": "digest"}, "digest_items": [off_policy]})
    # No allowed component remains, so delivery cannot create a digest outbox.
    assert render_candidate({"payload": {"title": "digest"}, "digest_items": [off_policy]}).count("https://") == 0
    isso = {**_candidate(), "payload": _candidate_payload(title="ISSO", url="https://isso.utdallas.edu/advising")}
    assert "https://isso.utdallas.edu/advising" in render_candidate(isso)


def test_on_demand_edition_withholds_off_policy_event_links():
    event = {"event_id": "off", "title": "Off policy", "canonical_url": "https://tracker.example/redirect"}
    text = render_on_demand_edition([event], source_health={"calendar": "healthy"})
    assert "tracker.example" not in text and "без ссылки" in text


def test_english_alert_and_digest_explain_relevance_change_and_action_without_russian_ui():
    urgent = {**_candidate(), "change_type": "cancelled", "relevance": {**_candidate()["relevance"], "urgent": True}}
    alert = render_candidate(urgent, language="en")
    assert "What changed: the event was cancelled" in alert
    assert "Why it matters to you:" in alert and "What to do:" in alert and "Source: https://" in alert
    digest = render_candidate({"payload": {"title": "ignored"}, "digest_items": [urgent]}, language="en")
    assert "What changed: the event was cancelled" in digest
    assert "Relevant to your confirmed topics:" in digest and "Source: https://" in digest
    assert not any(word in digest for word in ("Почему", "Источник", "Что изменилось")) and len(digest) <= 4096


def test_english_delivery_sender_payload_and_feedback_acknowledgement_are_english(tmp_path):
    candidate = {**_candidate(), "relevance": {**_candidate()["relevance"], "urgent": True}}
    sent = []
    result = deliver_candidates([candidate], sidecar_db=tmp_path / "shadow.db", token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED": "1"}, sender=lambda **kwargs: sent.append(kwargs) or 7, subscription={**_CONFIRMED_SUBSCRIPTION, "language": "en"})
    assert result["sent"] == 1
    labels = [button["text"] for row in sent[0]["reply_markup"]["inline_keyboard"] for button in row]
    assert all(not any(word in label for word in ("Полезно", "Шум", "Больше", "Меньше", "Пауза")) for label in labels)
    callback = sent[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert callback.endswith(":en") and handle_feedback_callback(tmp_path / "shadow.db", callback)["message"].startswith("Recorded:")


def test_digest_uses_canonical_url_for_text_and_component_receipt(tmp_path):
    item = {**_candidate(), "payload": _candidate_payload(title="Canonical", url="https://tracking.example/redirect", canonical_url="https://calendar.utdallas.edu/event/canonical")}
    sent = []
    result = deliver_candidates([item], sidecar_db=tmp_path / "shadow.db", token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED": "1"}, sender=lambda **kwargs: sent.append(kwargs) or 1)
    assert result["sent"] == 1 and "https://calendar.utdallas.edu/event/canonical" in sent[0]["text"] and "tracking.example" not in sent[0]["text"]
    assert DeliveryStore(tmp_path / "shadow.db").feedback_summary()["delivered"] == 1
    import sqlite3, json
    with sqlite3.connect(tmp_path / "shadow.db") as db:
        payload = json.loads(db.execute("SELECT payload_json FROM delivery_receipts").fetchone()[0])
    assert payload["digest_items"][0]["payload"]["canonical_url"] == "https://calendar.utdallas.edu/event/canonical"


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


def test_outbox_lease_is_atomic_and_ambiguous_send_is_never_blindly_retried(tmp_path):
    db = tmp_path / "outbox.db"
    candidate = _candidate()
    key = delivery_key(candidate)
    store = DeliveryStore(db)
    assert store.enqueue_outbox(key, candidate)
    assert store.lease_outbox(key) is not None
    assert DeliveryStore(db).lease_outbox(key) is None
    store.resolve_outbox(key, outcome="unknown", error="timeout after acceptance unknown")
    assert store.outbox_state(key) == "unknown"
    assert deliver_outbox_item(sidecar_db=db, key=key, token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED":"1"}, sender=lambda **_: 12) == "not_leased"


def test_two_workers_lease_only_one_sender_and_expired_lease_becomes_unknown(tmp_path):
    db = tmp_path / "outbox.db"
    key = delivery_key(_candidate())
    store = DeliveryStore(db)
    assert store.enqueue_outbox(key, _candidate())
    barrier = Barrier(2)
    results = []
    sends = []

    def worker():
        barrier.wait()
        results.append(deliver_outbox_item(sidecar_db=db, key=key, token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED":"1"}, sender=lambda **_: sends.append(1) or 1))

    first, second = Thread(target=worker), Thread(target=worker)
    first.start(); second.start(); first.join(); second.join()
    assert sorted(results) == ["not_leased", "sent"] and sends == [1]
    expiry_key = key + "expiry"
    assert store.enqueue_outbox(expiry_key, _candidate())
    assert store.lease_outbox(expiry_key) is not None
    later = datetime.now(timezone.utc).replace(microsecond=0)
    assert store.lease_outbox(expiry_key, now=later) is None
    assert store.outbox_state(expiry_key) == "leased"
    assert store.lease_outbox(expiry_key, now=later + timedelta(seconds=1), lease_seconds=0) is None
    # Explicitly advance beyond the original one-minute lease: no automatic resend.
    assert store.lease_outbox(expiry_key, now=later + timedelta(minutes=2)) is None
    assert store.outbox_state(expiry_key) == "unknown"


def test_transport_timeout_is_unknown_and_known_retries_are_bounded(tmp_path):
    db = tmp_path / "outbox.db"
    key = delivery_key(_candidate())
    store = DeliveryStore(db)
    assert store.enqueue_outbox(key, _candidate())
    assert deliver_outbox_item(sidecar_db=db, key=key, token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED":"1"}, sender=lambda **_: (_ for _ in ()).throw(TimeoutError())) == "unknown"
    assert store.outbox_state(key) == "unknown"

    retry_key = key + "retry"
    assert store.enqueue_outbox(retry_key, _candidate())
    for attempt in range(3):
        assert store.lease_outbox(retry_key, now=datetime(2030, 1, 1, 0, attempt, tzinfo=timezone.utc)) is not None
        store.resolve_outbox(retry_key, outcome="deferred", error="known")
    assert store.lease_outbox(retry_key, now=datetime(2030, 1, 1, 1, 0, tzinfo=timezone.utc)) is None
    assert store.outbox_state(retry_key) == "unknown"


def test_outbox_success_records_receipt_once_and_disabled_never_leases(tmp_path):
    db = tmp_path / "outbox.db"
    candidate = _candidate()
    key = delivery_key(candidate)
    store = DeliveryStore(db)
    store.enqueue_outbox(key, candidate)
    assert deliver_outbox_item(sidecar_db=db, key=key, token="t", chat_id="1", explicit_enable=False, env={"UTD_WATCH_DELIVERY_ENABLED":"1"}, sender=lambda **_: 7) == "disabled"
    assert store.outbox_state(key) == "pending"
    assert deliver_outbox_item(sidecar_db=db, key=key, token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED":"1"}, sender=lambda **_: 7) == "sent"
    assert store.outbox_state(key) == "sent" and store.already_delivered(key)


def test_cancelled_subscription_blocks_a_queued_send_before_lease(tmp_path):
    db = tmp_path / "outbox.db"
    key = delivery_key(_candidate())
    store = DeliveryStore(db)
    assert store.enqueue_outbox(key, _candidate())
    subscription = {"expires_at": "2026-12-01T00:00:00Z", "timezone": "America/Chicago", "quiet_hours": {}, "subscription_status": "cancelled"}
    assert deliver_outbox_item(sidecar_db=db, key=key, token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED":"1"}, sender=lambda **_: 1, subscription=subscription) == "subscription_blocked"
    assert store.outbox_state(key) == "pending"


def test_subscription_schedule_blocks_delivery_outside_its_local_minute(tmp_path):
    db = tmp_path / "outbox.db"
    profile = {"expires_at": "2026-12-01T00:00:00Z", "timezone": "America/Chicago", "quiet_hours": {}, "schedule": "09:00", "frequency": "daily_digest", "subscription_confirmed": True}
    result = deliver_candidates([_candidate()], sidecar_db=db, token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED":"1"}, sender=lambda **_: 1, subscription=profile, now=datetime(2026, 9, 17, 15, 1, tzinfo=timezone.utc))
    assert result["sent"] == 0 and result["suppressed_by_subscription"] == "schedule"


def test_known_failure_is_bounded_deferred_retry_not_unknown(tmp_path):
    db = tmp_path / "outbox.db"
    key = delivery_key(_candidate())
    store = DeliveryStore(db)
    store.enqueue_outbox(key, _candidate())
    def rejected(**_):
        raise KnownDeliveryFailure("pre-send policy rejection")
    assert deliver_outbox_item(sidecar_db=db, key=key, token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED":"1"}, sender=rejected) == "deferred"
    # Durable retry_after prevents a hot loop; repeated deferred attempts are
    # bounded in lease_outbox once their scheduled retries occur.
    assert deliver_outbox_item(sidecar_db=db, key=key, token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED":"1"}, sender=rejected) == "not_leased"
    assert store.outbox_state(key) == "deferred"


def test_actual_telegram_rejection_is_a_bounded_deferred_retry(tmp_path):
    db = tmp_path / "outbox.db"
    key = delivery_key(_candidate())
    store = DeliveryStore(db)
    assert store.enqueue_outbox(key, _candidate())

    def rejected(**_):
        raise TelegramKnownRejection("400 chat not found")

    assert deliver_outbox_item(sidecar_db=db, key=key, token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED":"1"}, sender=rejected) == "deferred"
    assert store.outbox_state(key) == "deferred"


def test_only_real_telegram_rejections_are_retryable(monkeypatch, tmp_path):
    def rejected_400(*_args, **_kwargs):
        raise HTTPError("https://api.telegram.org", 400, "bad request", {}, None)

    monkeypatch.setattr("bot.telegram_delivery.request.urlopen", rejected_400)
    try:
        _telegram_request("https://api.telegram.org", b"", {})
    except TelegramKnownRejection:
        pass
    else:
        raise AssertionError("a definite 4xx rejection must be typed")

    db = tmp_path / "outbox.db"
    key = delivery_key(_candidate())
    store = DeliveryStore(db)
    assert store.enqueue_outbox(key, _candidate())
    unrelated = type("TelegramKnownRejection", (Exception,), {})
    assert deliver_outbox_item(sidecar_db=db, key=key, token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED":"1"}, sender=lambda **_: (_ for _ in ()).throw(unrelated())) == "unknown"
    assert store.outbox_state(key) == "unknown"


def test_partial_chunk_rejection_is_ambiguous_and_never_replayed(monkeypatch, tmp_path):
    calls = []

    def chunk_transport(**_kwargs):
        calls.append(1)
        if len(calls) == 1:
            return {"ok": True, "result": {"message_id": 1}}
        raise TelegramKnownRejection("second chunk rejected")

    monkeypatch.setattr("bot.telegram_delivery._telegram_request", chunk_transport)
    try:
        _send_text_internal("1", "x" * 4100, "token", parse_mode=None)
    except TelegramAmbiguousDelivery:
        pass
    else:
        raise AssertionError("a failure after the first accepted chunk must be ambiguous")

    db = tmp_path / "outbox.db"
    candidate = {**_candidate(), "payload": _candidate_payload(title="x" * 4100, url="https://calendar.utdallas.edu/event/x")}
    key = delivery_key(candidate)
    store = DeliveryStore(db)
    assert store.enqueue_outbox(key, candidate)
    calls.clear()
    assert deliver_outbox_item(sidecar_db=db, key=key, token="token", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED":"1"}, sender=lambda **kwargs: _send_text_internal(**kwargs)) == "sent"
    assert len(calls) == 1 and store.outbox_state(key) == "sent"


def test_pending_ordinary_digest_is_recovered_before_a_new_digest(tmp_path):
    db = tmp_path / "outbox.db"
    item = _candidate()
    digest = {"source":"utd_daily_digest", "item_key":"pending", "change_type":"daily_digest", "digest_items":[item], "payload":{"title":"pending"}, "relevance":{}}
    key = delivery_key(digest)
    store = DeliveryStore(db)
    assert store.prepare_ordinary_outbox(key, digest, units=1)
    sent = []
    result = deliver_candidates([], sidecar_db=db, token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED":"1"}, sender=lambda **kwargs: sent.append(kwargs) or 77)
    assert result["sent"] == 1 and result["recovered_pending_digest"] is True
    assert store.outbox_state(key) == "sent" and len(sent) == 1


def test_pending_ordinary_digest_survives_the_local_day_boundary(tmp_path):
    db = tmp_path / "outbox.db"
    digest = {"source":"utd_daily_digest", "item_key":"yesterday", "change_type":"daily_digest", "digest_items":[_candidate()], "payload":{"title":"pending"}, "relevance":{}}
    key = delivery_key(digest)
    store = DeliveryStore(db)
    yesterday = datetime(2026, 9, 16, 23, 30, tzinfo=timezone.utc)
    today = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    assert store.prepare_ordinary_outbox(key, digest, units=1, now=yesterday)
    assert store.pending_ordinary_outbox(now=today) == (key, digest)


def test_prior_day_digest_recovery_reserves_the_actual_delivery_day_cap(tmp_path):
    db = tmp_path / "outbox.db"
    store = DeliveryStore(db)
    local_now = datetime.now(ZoneInfo("America/Chicago"))
    yesterday = (local_now.replace(hour=1, minute=0, second=0, microsecond=0) - timedelta(days=1)).astimezone(timezone.utc)
    digest = {"source":"utd_daily_digest", "item_key":"yesterday", "change_type":"daily_digest", "digest_items":[_candidate()], "payload":{"title":"pending"}, "relevance":{}}
    key = delivery_key(digest)
    assert store.prepare_ordinary_outbox(key, digest, units=1, now=yesterday)
    for index in range(5):
        store.record_delivery(f"today-{index}", {**_candidate(), "item_key": f"today-{index}"}, 100 + index)
    sent = []
    result = deliver_candidates([], sidecar_db=db, token="t", chat_id="1", explicit_enable=True, env={"UTD_WATCH_DELIVERY_ENABLED":"1"}, sender=lambda **kwargs: sent.append(kwargs) or 7)
    assert result["sent"] == 0 and sent == []
    assert store.outbox_state(key) == "pending"


def test_ordinary_candidates_are_one_digest_and_each_item_is_idempotent(tmp_path):
    sent=[]
    def sender(**kwargs):
        sent.append(kwargs); return 101
    env={"UTD_WATCH_DELIVERY_ENABLED":"1"}
    db=tmp_path/"shadow.db"
    first = deliver_candidates(
        [_candidate(), {**_candidate(), "item_key":"43:8", "payload":_candidate_payload(title="Career workshop", url="https://calendar.utdallas.edu/event/workshop")}],
        sidecar_db=db, token="t", chat_id="1", explicit_enable=True, env=env, sender=sender,
    )
    follow_up = deliver_candidates(
        [{**_candidate(), "item_key":"43:8", "payload":_candidate_payload(title="Career workshop", url="https://calendar.utdallas.edu/event/workshop")}],
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
    assert "UTD_WATCH_DELIVERY_ENABLED=1" not in service
    assert "UTD_WATCH_KILL_SWITCH=0" not in service
    assert "EnvironmentFile" in service and "next timer run" in service
    assert "-m external_watch.live --enable-shadow --enable-delivery" in service
    assert "src/main.py ingest" not in service
    assert "weekly-intelligence" not in service
    assert "OnUnitActiveSec=45m" in timer
    assert "Persistent=false" in timer
    assert "Unit=telegram-utd-watch.service" in timer
