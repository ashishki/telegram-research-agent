from datetime import datetime, timezone

from external_watch.subscription import in_quiet_hours, scheduled_delivery_due, subscription_effect


def _profile(**extra):
    return {"expires_at": "2026-12-01T00:00:00Z", "timezone": "America/Chicago", "quiet_hours": {"start": "22:00", "end": "08:00"}, "subscription_confirmed": True, **extra}


def test_subscription_is_fail_closed_until_runtime_and_blocks_lifecycle_states():
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)
    assert subscription_effect(None, now=now)["reason"] == "unconfirmed"
    assert subscription_effect(_profile(), now=now)["reason"] == "runtime_disabled"
    assert subscription_effect(_profile(subscription_status="cancelled"), now=now, runtime_enabled=True)["collect"] is False
    assert subscription_effect(_profile(paused=True), now=now, runtime_enabled=True)["deliver"] is False
    assert subscription_effect(_profile(), now=now, runtime_enabled=True, kill_switch=True)["reason"] == "kill_switch"


def test_quiet_window_handles_dst_zone_and_overnight_window():
    assert in_quiet_hours(_profile(), now=datetime(2026, 11, 1, 7, 30, tzinfo=timezone.utc))
    assert not in_quiet_hours(_profile(), now=datetime(2026, 11, 1, 16, 0, tzinfo=timezone.utc))


def test_schedule_is_timezone_and_weekday_aware():
    profile = _profile(schedule="09:00", frequency="weekly_digest")
    assert scheduled_delivery_due(profile, now=datetime(2026, 9, 14, 14, 0, tzinfo=timezone.utc))
    assert not scheduled_delivery_due(profile, now=datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc))
    assert scheduled_delivery_due(_profile(frequency="urgent_only"), now=datetime(2026, 9, 15, 14, 7, tzinfo=timezone.utc))
    assert not scheduled_delivery_due(_profile(schedule="09:00", period="weekly"), now=datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc))
    assert scheduled_delivery_due(_profile(schedule="09:00", period="weekly"), now=datetime(2026, 9, 14, 14, 30, tzinfo=timezone.utc))


def test_spring_forward_uses_first_post_gap_window_without_normal_late_catchup():
    profile = _profile(schedule="02:00", frequency="daily_digest")
    # 2026-03-08 08:00Z is 03:00 Chicago: the local 02:00 never existed.
    assert scheduled_delivery_due(profile, now=datetime(2026, 3, 8, 8, 0, tzinfo=timezone.utc))
    assert not scheduled_delivery_due(profile, now=datetime(2026, 3, 9, 8, 0, tzinfo=timezone.utc))


def test_schedule_never_wraps_into_the_next_local_day():
    assert not scheduled_delivery_due(_profile(schedule="23:30", frequency="daily_digest"), now=datetime(2026, 9, 18, 5, 0, tzinfo=timezone.utc))


def test_malformed_persisted_time_fails_closed():
    assert in_quiet_hours(_profile(quiet_hours={"start": "nope", "end": "08:00"}))
    assert not scheduled_delivery_due(_profile(schedule="99:99"), now=datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc))
