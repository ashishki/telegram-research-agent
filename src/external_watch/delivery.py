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
            delivered = int(db.execute("SELECT COUNT(*) FROM delivery_receipts").fetchone()[0])
            counts = {str(a): int(c) for a, c in db.execute("SELECT action,COUNT(*) FROM watch_feedback GROUP BY action")}
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
        return {"enabled": False, "sent": 0, "duplicates_blocked": 0}
    if not token or not chat_id:
        raise ValueError("Telegram token and owner chat id are required")
    if sender is None:
        from bot.telegram_delivery import send_text
        sender = send_text
    store = DeliveryStore(sidecar_db)
    sent = 0
    duplicates = 0
    for candidate in candidates[:5]:
        key = delivery_key(candidate)
        if store.already_delivered(key):
            duplicates += 1
            continue
        message_id = sender(
            chat_id=chat_id,
            text=render_candidate(candidate),
            token=token,
            parse_mode=None,
            reply_markup=build_feedback_markup(key),
        )
        store.record_delivery(key, candidate, message_id)
        sent += 1
    return {"enabled": True, "sent": sent, "duplicates_blocked": duplicates}


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
