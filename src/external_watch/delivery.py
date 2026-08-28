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
    categories = ", ".join(str(x) for x in rel.get("categories") or [])
    reason = str(rel.get("reason") or "").strip()
    urgency = "Срочно. " if rel.get("urgent") else ""
    digest_items = candidate.get("digest_items")
    if isinstance(digest_items, Sequence) and not isinstance(digest_items, (str, bytes)):
        lines = [title]
        for index, item in enumerate(digest_items, start=1):
            item_payload = item.get("payload") if isinstance(item, Mapping) else {}
            item_title = str((item_payload or {}).get("title") or "UTD update").strip()
            item_url = str((item_payload or {}).get("url") or "").strip()
            lines.append(f"{index}. {item_title}{f' — {item_url}' if item_url else ''}")
        lines.append("Почему тебе: совпадает с подтверждённым UTD scope.")
        return "\n".join(lines)
    lines = [f"{urgency}{title}", f"Изменение: {change}."]
    if reason:
        lines.append(f"Почему тебе: {reason}")
    elif categories:
        lines.append(f"Почему тебе: {categories}.")
    if url:
        lines.append(f"Источник: {url}")
    return "\n".join(lines)


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
