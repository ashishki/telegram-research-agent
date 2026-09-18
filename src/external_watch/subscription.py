"""Pure, fail-closed subscription lifecycle contract for Personal Search & News.

This is intentionally independent of timers and transports.  A caller must pass
the confirmed metadata on every collection and send attempt; this module never
enables a runtime or persists an operator choice by itself.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo


def _time(value: object) -> str | None:
    text = str(value or "")
    if len(text) != 5 or text[2] != ":":
        return None
    try:
        hour, minute = (int(part) for part in text.split(":"))
    except ValueError:
        return None
    return text if 0 <= hour <= 23 and 0 <= minute <= 59 else None


def _utc(value: object, now: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def subscription_effect(
    profile: Mapping[str, Any] | None,
    *,
    now: datetime | None = None,
    runtime_enabled: bool = False,
    kill_switch: bool = False,
) -> dict[str, Any]:
    """Return the exact effect, failing closed for unconfirmed/bad metadata."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not isinstance(profile, Mapping):
        return {"collect": False, "deliver": False, "reason": "unconfirmed"}
    if not bool(profile.get("subscription_confirmed")):
        return {"collect": False, "deliver": False, "reason": "unconfirmed"}
    status = str(profile.get("subscription_status") or "active")
    if status != "active":
        return {"collect": False, "deliver": False, "reason": status if status in {"paused", "cancelled", "expired", "unconfirmed"} else "invalid_status"}
    try:
        if _utc(profile.get("expires_at")) <= current:
            return {"collect": False, "deliver": False, "reason": "expired"}
    except (ValueError, TypeError):
        return {"collect": False, "deliver": False, "reason": "invalid_expiry"}
    if kill_switch:
        return {"collect": False, "deliver": False, "reason": "kill_switch"}
    if bool(profile.get("paused")):
        return {"collect": False, "deliver": False, "reason": "paused"}
    if not runtime_enabled:
        return {"collect": False, "deliver": False, "reason": "runtime_disabled"}
    return {"collect": True, "deliver": True, "reason": "active"}


def in_quiet_hours(profile: Mapping[str, Any], *, now: datetime | None = None) -> bool:
    """Inclusive-start/exclusive-end local quiet window, including DST zones."""
    quiet = profile.get("quiet_hours") if isinstance(profile.get("quiet_hours"), Mapping) else {}
    start, end = _time(quiet.get("start")), _time(quiet.get("end"))
    if start is None or end is None:
        return bool(quiet)
    if start == end:
        return False
    try:
        zone = ZoneInfo(str(profile.get("timezone") or "UTC"))
        local = (now or datetime.now(timezone.utc)).astimezone(zone).strftime("%H:%M")
    except Exception:
        return True
    return start <= local < end if start < end else local >= start or local < end


def scheduled_delivery_due(profile: Mapping[str, Any], *, now: datetime | None = None) -> bool:
    """Whether an ordinary digest may be delivered in this local minute."""
    if str(profile.get("frequency") or "daily_digest") == "urgent_only":
        return True
    try:
        local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(str(profile.get("timezone") or "UTC")))
    except Exception:
        return False
    schedule = _time(profile.get("schedule") or "09:00")
    if schedule is None:
        return False
    hour, minute = (int(part) for part in schedule.split(":"))
    scheduled_minute = hour * 60 + minute
    local_minute = local.hour * 60 + local.minute
    # The one-shot service runs every 45 minutes.  This bounded window avoids
    # silently dropping a digest when the timer is offset or a DST wall-clock
    # minute does not exist; receipt/idempotency still permits one digest/day.
    # A daily schedule never wraps into the following local day: 23:30 must
    # not be due at 00:00 merely because modulo arithmetic made it +30 min.
    delta = local_minute - scheduled_minute
    if not 0 <= delta <= 45:
        # Spring-forward can erase a configured 02:xx local wall-clock time.
        # Deliver at the first bounded post-gap invocation (up to two hours),
        # but never use this for ordinary late/day-wrap catch-up.
        scheduled_wall = datetime(local.year, local.month, local.day, hour, minute, tzinfo=local.tzinfo)
        if not (0 < delta <= 120 and local.hour >= 3 and local.utcoffset() != scheduled_wall.utcoffset()):
            return False
    return (str(profile.get("frequency") or "daily_digest") != "weekly_digest" and str(profile.get("period") or "daily") != "weekly") or local.weekday() == 0


def render_subscription_effect(profile: Mapping[str, Any], *, runtime_enabled: bool = False) -> str:
    effect = subscription_effect(profile, runtime_enabled=runtime_enabled)
    if effect["reason"] == "runtime_disabled":
        return "Подтверждённый scope сохранён; runtime выключен, поэтому сбор и доставка ожидают отдельного включения."
    return f"Состояние подписки: {effect['reason']}."
