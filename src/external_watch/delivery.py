"""Default-off Telegram delivery gate for UTD watch candidates.

Delivery is deliberately separate from collection. A caller must opt in explicitly,
provide the owner chat/token, and keep the kill switch clear. Receipts live only in
the derived sidecar DB.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

DELIVERY_SCHEMA = """
CREATE TABLE IF NOT EXISTS delivery_receipts(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 delivery_key TEXT NOT NULL UNIQUE,
 source TEXT NOT NULL,
 item_key TEXT NOT NULL,
 change_type TEXT NOT NULL,
 delivered_at TEXT NOT NULL,
 telegram_message_id INTEGER,
 payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watch_feedback(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 delivery_key TEXT NOT NULL,
 action TEXT NOT NULL,
 recorded_at TEXT NOT NULL,
 UNIQUE(delivery_key, action)
);
"""

FEEDBACK_PREFIX = "utdw"
_ALLOWED_FEEDBACK = {"useful", "noise", "more", "less", "mute", "pause"}
_UTD_TIMEZONE = ZoneInfo("America/Chicago")


def default_sidecar_db(env: Mapping[str, str] | None = None) -> str:
    """Return the one sidecar path shared by collection, delivery and callbacks."""
    env = env or os.environ
    return (
        env.get("UTD_WATCH_SIDECAR_DB", "").strip()
        or env.get("UTD_SHADOW_DB", "").strip()
        or "data/utd_shadow.db"
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def delivery_enabled(*, explicit: bool = False, env: Mapping[str, str] | None = None) -> bool:
    env = env or os.environ
    return bool(explicit) and env.get("UTD_WATCH_DELIVERY_ENABLED", "").strip() == "1" and env.get("UTD_WATCH_KILL_SWITCH", "").strip() != "1"


def delivery_key(candidate: Mapping[str, Any]) -> str:
    material = "|".join(
        [
            str(candidate.get("source") or ""),
            str(candidate.get("item_key") or ""),
            str(candidate.get("change_type") or ""),
            json.dumps(candidate.get("payload") or {}, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def build_feedback_markup(key: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "👍 Полезно", "callback_data": f"{FEEDBACK_PREFIX}:{key}:useful"},
                {"text": "👎 Шум", "callback_data": f"{FEEDBACK_PREFIX}:{key}:noise"},
            ],
            [
                {"text": "Больше такого", "callback_data": f"{FEEDBACK_PREFIX}:{key}:more"},
                {"text": "Меньше такого", "callback_data": f"{FEEDBACK_PREFIX}:{key}:less"},
            ],
            [
                {"text": "Mute source", "callback_data": f"{FEEDBACK_PREFIX}:{key}:mute"},
                {"text": "Пауза", "callback_data": f"{FEEDBACK_PREFIX}:{key}:pause"},
            ],
        ]
    }


def render_candidate(candidate: Mapping[str, Any]) -> str:
    payload = candidate.get("payload") if isinstance(candidate.get("payload"), Mapping) else {}
    rel = candidate.get("relevance") if isinstance(candidate.get("relevance"), Mapping) else {}
    title = str(payload.get("title") or payload.get("name") or "UTD update").strip()
    url = str(payload.get("url") or payload.get("canonical_url") or "").strip()
    change = str(candidate.get("change_type") or "updated")
    category_values = [str(x) for x in rel.get("categories") or [] if str(x)]
    categories = ", ".join(category_values)
    reason = str(rel.get("reason") or "").strip()
    urgency = "Срочно. " if rel.get("urgent") else ""
    digest_items = candidate.get("digest_items")
    if isinstance(digest_items, Sequence) and not isinstance(digest_items, (str, bytes)):
        lines = [title]
        for index, item in enumerate(digest_items, start=1):
            item_payload = item.get("payload") if isinstance(item, Mapping) else {}
            item_title = str((item_payload or {}).get("title") or "UTD update").strip()
            item_url = str((item_payload or {}).get("url") or "").strip()
            item_when = _candidate_time(item_payload or {})
            when_suffix = f" · {item_when}" if item_when else ""
            lines.append(f"{index}. {item_title}{when_suffix}{f' — {item_url}' if item_url else ''}")
        lines.append("Почему тебе: это дневной digest по подтверждённому UTD scope, не лента всех новостей.")
        return "\n".join(lines)
    lines = [f"{urgency}{title}", f"Что изменилось: {_human_change(change)}."]
    when = _candidate_time(payload)
    if when:
        lines.append(f"Когда: {when}")
    human_reason = _human_reason(reason, categories=categories)
    if human_reason:
        lines.append(f"Почему тебе: {human_reason}")
    elif categories:
        lines.append(f"Почему тебе: совпадает с подтверждённым scope: {categories}.")
    next_step = _candidate_next_step(category_values, change=change, urgent=bool(rel.get("urgent")))
    if next_step:
        lines.append(f"Что сделать: {next_step}")
    checked_at = _format_timestamp(payload.get("updated_at"))
    if checked_at:
        lines.append(f"Источник проверен: {checked_at}")
    if url:
        lines.append(f"Источник: {url}")
    return "\n".join(lines)


def _human_change(change: str) -> str:
    return {
        "new": "новое релевантное событие или ресурс",
        "updated": "официальная страница изменилась",
        "cancelled": "событие отменено или статус стал inactive",
        "reinstated": "событие снова активно",
        "daily_digest": "подборка релевантных изменений за день",
    }.get(str(change or "").casefold(), str(change or "updated"))


def _candidate_time(payload: Mapping[str, Any]) -> str:
    instance = payload.get("instance") if isinstance(payload.get("instance"), Mapping) else {}
    start = str(instance.get("start") or payload.get("start") or payload.get("start_at") or payload.get("date") or "").strip()
    end = str(instance.get("end") or payload.get("end") or payload.get("end_at") or "").strip()
    start_dt = _parse_timestamp(start)
    end_dt = _parse_timestamp(end)
    if start_dt and end_dt:
        if start_dt.date() == end_dt.date():
            return f"{start_dt:%Y-%m-%d}, {start_dt:%H:%M}–{end_dt:%H:%M} CT"
        return f"{_format_local_dt(start_dt)} — {_format_local_dt(end_dt)}"
    if start_dt:
        return _format_local_dt(start_dt)
    if start and end:
        return f"{start} — {end}"
    return start


def _human_reason(reason: str, *, categories: str) -> str:
    clean = " ".join(str(reason or "").replace("_", " ").split())
    if not clean:
        return ""
    lowered = clean.casefold()
    if lowered.startswith("synthetic ") or "confirmed scope" in lowered:
        return f"совпадает с твоим подтверждённым UTD scope: {categories or 'UTD'}."
    return clean


def _candidate_next_step(categories: Sequence[str], *, change: str, urgent: bool) -> str:
    lowered = {item.casefold() for item in categories}
    prefix = "сегодня " if urgent or str(change).casefold() in {"cancelled", "reinstated"} else ""
    if "program" in lowered:
        return f"{prefix}открой источник и проверь, касается ли срок твоей программы."
    if "career" in lowered:
        return f"{prefix}проверь регистрацию и добавь событие в календарь, если оно подходит под internship search."
    if "ai" in lowered:
        return f"{prefix}открой страницу события и реши, стоит ли идти по теме AI/research."
    if "isso" in lowered:
        return f"{prefix}сверься с ISSO page; не принимай immigration-решение по уведомлению."
    if "benefits" in lowered:
        return f"{prefix}проверь eligibility на странице ресурса перед действием."
    if "spouse_family" in lowered:
        return f"{prefix}проверь, явно ли указана spouse/family eligibility."
    return f"{prefix}открой источник и реши, нужно ли действие."


def _format_timestamp(value: object) -> str:
    parsed = _parse_timestamp(value)
    return _format_local_dt(parsed) if parsed is not None else ""


def _parse_timestamp(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(_UTD_TIMEZONE)


def _format_local_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d, %H:%M CT")


class DeliveryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript(DELIVERY_SCHEMA)

    def already_delivered(self, key: str) -> bool:
        with sqlite3.connect(self.path) as db:
            return db.execute("SELECT 1 FROM delivery_receipts WHERE delivery_key=? LIMIT 1", (key,)).fetchone() is not None

    def record_delivery(self, key: str, candidate: Mapping[str, Any], message_id: int | None) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT OR IGNORE INTO delivery_receipts(delivery_key,source,item_key,change_type,delivered_at,telegram_message_id,payload_json) VALUES(?,?,?,?,?,?,?)",
                (
                    key,
                    str(candidate.get("source") or ""),
                    str(candidate.get("item_key") or ""),
                    str(candidate.get("change_type") or ""),
                    _now(),
                    message_id,
                    json.dumps(dict(candidate), ensure_ascii=False, sort_keys=True),
                ),
            )
            db.commit()

    def record_digest(
        self,
        key: str,
        digest: Mapping[str, Any],
        items: Sequence[tuple[str, Mapping[str, Any]]],
        message_id: int | None,
    ) -> None:
        """Record the visible digest and each contained item for idempotency.

        Component records are deliberately not feedback targets and do not count
        as separate Telegram deliveries; they only prevent an item from being
        reintroduced if a later digest has a different mix of candidates.
        """
        self.record_delivery(key, digest, message_id)
        for item_key, item in items:
            component = {**dict(item), "digest_component": True, "digest_key": key}
            self.record_delivery(item_key, component, message_id)

    def delivered_item_count_today(self, *, now: datetime | None = None) -> int:
        """Count delivered candidate items in the profile timezone, not poll runs."""
        local_day = (now or datetime.now(timezone.utc)).astimezone(_UTD_TIMEZONE).date()
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT delivered_at,payload_json FROM delivery_receipts").fetchall()
        count = 0
        for delivered_at, raw_payload in rows:
            try:
                delivered_day = datetime.fromisoformat(str(delivered_at).replace("Z", "+00:00")).astimezone(_UTD_TIMEZONE).date()
            except ValueError:
                continue
            if delivered_day != local_day:
                continue
            try:
                payload = json.loads(str(raw_payload))
            except (TypeError, json.JSONDecodeError):
                payload = {}
            if isinstance(payload, dict) and payload.get("digest_component"):
                continue
            items = payload.get("digest_items") if isinstance(payload, dict) else None
            count += len(items) if isinstance(items, list) else 1
        return count

    def record_feedback(self, key: str, action: str) -> str:
        if action not in _ALLOWED_FEEDBACK:
            raise ValueError("Unsupported watch feedback")
        with sqlite3.connect(self.path) as db:
            if db.execute("SELECT 1 FROM delivery_receipts WHERE delivery_key=?", (key,)).fetchone() is None:
                raise ValueError("Unknown delivery receipt")
            db.execute("INSERT OR IGNORE INTO watch_feedback(delivery_key,action,recorded_at) VALUES(?,?,?)", (key, action, _now()))
            db.commit()
        return action

    def feedback_summary(self) -> dict[str, Any]:
        with sqlite3.connect(self.path) as db:
            raw_deliveries = [row[0] for row in db.execute("SELECT payload_json FROM delivery_receipts")]
            counts = {str(a): int(c) for a, c in db.execute("SELECT action,COUNT(*) FROM watch_feedback GROUP BY action")}
        delivered = 0
        for raw_payload in raw_deliveries:
            try:
                payload = json.loads(str(raw_payload))
            except (TypeError, json.JSONDecodeError):
                payload = {}
            if not (isinstance(payload, dict) and payload.get("digest_component")):
                delivered += 1
        rated = counts.get("useful", 0) + counts.get("noise", 0)
        return {
            "delivered": delivered,
            "feedback": counts,
            "rated": rated,
            "observed_precision": (counts.get("useful", 0) / rated) if rated else None,
        }


def deliver_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    sidecar_db: str | Path,
    token: str,
    chat_id: str,
    explicit_enable: bool = False,
    env: Mapping[str, str] | None = None,
    sender: Callable[..., int | None] | None = None,
) -> dict[str, Any]:
    if not delivery_enabled(explicit=explicit_enable, env=env):
        return {"enabled": False, "sent": 0, "duplicates_blocked": 0, "daily_cap_blocked": 0}
    if not token or not chat_id:
        raise ValueError("Telegram token and owner chat id are required")
    if sender is None:
        from bot.telegram_delivery import send_text
        sender = send_text
    store = DeliveryStore(sidecar_db)
    sent = 0
    duplicates = 0
    daily_cap = 5
    remaining = max(0, daily_cap - store.delivered_item_count_today())
    eligible: list[tuple[str, Mapping[str, Any]]] = []
    for candidate in candidates:
        key = delivery_key(candidate)
        if store.already_delivered(key):
            duplicates += 1
            continue
        eligible.append((key, candidate))
    daily_cap_blocked = max(0, len(eligible) - remaining)

    # A source-supported urgent change can alert immediately. Everything else is
    # one bounded daily digest, so a frequent collector cannot become a news feed.
    urgent = [(key, candidate) for key, candidate in eligible if bool((candidate.get("relevance") or {}).get("urgent"))]
    ordinary = [(key, candidate) for key, candidate in eligible if not bool((candidate.get("relevance") or {}).get("urgent"))]
    for key, candidate in urgent[:remaining]:
        message_id = sender(
            chat_id=chat_id,
            text=render_candidate(candidate),
            token=token,
            parse_mode=None,
            reply_markup=build_feedback_markup(key),
        )
        store.record_delivery(key, candidate, message_id)
        sent += 1
    remaining -= min(len(urgent), remaining)
    if remaining and ordinary:
        digest_items = [dict(candidate) for _, candidate in ordinary[:remaining]]
        digest = _build_daily_digest(digest_items)
        key = delivery_key(digest)
        if store.already_delivered(key):
            duplicates += len(digest_items)
        else:
            message_id = sender(
                chat_id=chat_id,
                text=render_candidate(digest),
                token=token,
                parse_mode=None,
                reply_markup=build_feedback_markup(key),
            )
            store.record_digest(key, digest, ordinary[:remaining], message_id)
            sent += 1
    return {
        "enabled": True,
        "sent": sent,
        "duplicates_blocked": duplicates,
        "daily_cap_blocked": daily_cap_blocked,
    }


def _build_daily_digest(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    categories = list(
        dict.fromkeys(
            str(category)
            for item in items
            for category in ((item.get("relevance") or {}).get("categories") or [])
        )
    )
    return {
        "source": "utd_daily_digest",
        "item_key": "|".join(str(item.get("item_key") or "") for item in items),
        "change_type": "daily_digest",
        "digest_items": [dict(item) for item in items],
        "payload": {
            "title": "UTD: важное на сегодня",
            "items": [
                {
                    "title": str((item.get("payload") or {}).get("title") or "UTD update"),
                    "url": str((item.get("payload") or {}).get("url") or ""),
                }
                for item in items
            ],
        },
        "relevance": {
            "relevant": True,
            "urgent": False,
            "categories": categories,
            "reason": "daily_digest_of_confirmed_matches",
        },
    }


def handle_feedback_callback(sidecar_db: str | Path, callback_data: str) -> dict[str, Any]:
    parts = callback_data.split(":")
    if len(parts) != 3 or parts[0] != FEEDBACK_PREFIX:
        raise ValueError("Unsupported watch callback")
    key, action = parts[1], parts[2]
    store = DeliveryStore(sidecar_db)
    recorded = store.record_feedback(key, action)
    messages = {
        "useful": "Записал: полезно.",
        "noise": "Записал: это шум.",
        "more": "Записал: больше такого.",
        "less": "Записал: меньше такого.",
        "mute": "Записал feedback mute; источник не будет молча отключён без подтверждения профиля.",
        "pause": "Записал feedback pause; постоянная пауза требует подтверждения профиля.",
    }
    return {"message": messages[recorded], "action": recorded}
