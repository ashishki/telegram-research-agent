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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from bot.telegram_delivery import TelegramKnownRejection
from .subscription import in_quiet_hours, scheduled_delivery_due, subscription_effect

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
CREATE TABLE IF NOT EXISTS delivery_outbox(
 delivery_key TEXT PRIMARY KEY,
 candidate_json TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('pending','leased','deferred','unknown','sent','cancelled')),
 attempts INTEGER NOT NULL DEFAULT 0,
 lease_until TEXT NOT NULL DEFAULT '',
 retry_after TEXT NOT NULL DEFAULT '',
 last_error TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS delivery_quota_reservations(
 reservation_key TEXT PRIMARY KEY,
 local_day TEXT NOT NULL,
 units INTEGER NOT NULL,
 state TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ordinary_digest_reservations(
 local_day TEXT PRIMARY KEY,
 delivery_key TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_delivery_candidates(
 delivery_key TEXT PRIMARY KEY,
 candidate_json TEXT NOT NULL,
 created_at TEXT NOT NULL
);
"""

FEEDBACK_PREFIX = "utdw"
TELEGRAM_TEXT_LIMIT = 4096
_ALLOWED_FEEDBACK = {"useful", "noise", "more", "less", "mute", "pause"}
_UTD_TIMEZONE = ZoneInfo("America/Chicago")
_FEEDBACK_PAUSE_WINDOW = timedelta(hours=24)


class KnownDeliveryFailure(Exception):
    """A pre-send/provider rejection known not to have reached Telegram."""


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


def build_feedback_markup(key: str, *, language: str = "ru") -> dict[str, Any]:
    english = language == "en"
    suffix = ":en" if english else ""
    return {
        "inline_keyboard": [
            [
                {"text": "👍 Useful" if english else "👍 Полезно", "callback_data": f"{FEEDBACK_PREFIX}:{key}:useful{suffix}"},
                {"text": "👎 Noise" if english else "👎 Шум", "callback_data": f"{FEEDBACK_PREFIX}:{key}:noise{suffix}"},
            ],
            [
                {"text": "Adjust notifications" if english else "Настроить уведомления", "callback_data": f"{FEEDBACK_PREFIX}:{key}:settings{suffix}"},
            ],
        ]
    }


def build_feedback_settings_markup(key: str, *, language: str = "ru") -> dict[str, Any]:
    """Expose secondary controls only after the user explicitly asks for them."""
    english = language == "en"
    suffix = ":en" if english else ""
    return {
        "inline_keyboard": [
            [
                {"text": "More like this" if english else "Больше похожего", "callback_data": f"{FEEDBACK_PREFIX}:{key}:more{suffix}"},
                {"text": "Less like this" if english else "Меньше похожего", "callback_data": f"{FEEDBACK_PREFIX}:{key}:less{suffix}"},
            ],
            [
                {"text": "Mute source" if english else "Источник неинтересен", "callback_data": f"{FEEDBACK_PREFIX}:{key}:mute{suffix}"},
                {"text": "Pause 24h" if english else "Пауза на 24 ч", "callback_data": f"{FEEDBACK_PREFIX}:{key}:pause{suffix}"},
            ],
        ]
    }


def render_candidate(candidate: Mapping[str, Any], *, language: str = "ru", depth: str = "brief") -> str:
    payload = candidate.get("payload") if isinstance(candidate.get("payload"), Mapping) else {}
    rel = candidate.get("relevance") if isinstance(candidate.get("relevance"), Mapping) else {}
    title = _bounded_text(str(payload.get("title") or payload.get("name") or "UTD update").strip(), 700)
    url = _source_url(payload)
    change = str(candidate.get("change_type") or "updated")
    category_values = [str(x) for x in rel.get("categories") or [] if str(x)]
    categories = _display_categories(category_values)
    reason = str(rel.get("reason") or "").strip()
    urgency = "Срочно. " if rel.get("urgent") else ""
    digest_items = candidate.get("digest_items")
    if isinstance(digest_items, Sequence) and not isinstance(digest_items, (str, bytes)):
        english = language == "en"
        lines = ["UTD: important today" if english else title]
        for index, item in enumerate(digest_items, start=1):
            item_payload = item.get("payload") if isinstance(item, Mapping) else {}
            item_title = _bounded_text(str((item_payload or {}).get("title") or "UTD update").strip(), 450)
            item_url = _source_url(item_payload or {})
            if not item_url or len(item_url) > 2048:
                continue
            item_when = _candidate_time(item_payload or {})
            when_suffix = f" · {item_when}" if item_when else ""
            item_rel = item.get("relevance") if isinstance(item, Mapping) and isinstance(item.get("relevance"), Mapping) else {}
            item_category_values = [str(value) for value in item_rel.get("categories") or [] if str(value)]
            item_categories = _display_categories(item_category_values)
            item_change = _meaningful_change_summary(
                item_payload or {}, str(item.get("change_type") or "updated"), english=english
            )
            if not item_change:
                # A source timestamp alone is not a user-relevant change.
                continue
            relevance_line = (f"Relevant to your confirmed topics: {item_categories or 'UTD'}." if english else f"Почему тебе: совпадает с твоими подтверждёнными темами: {item_categories or 'UTD'}.")
            label = "What changed" if english else "Что изменилось"
            lines.append(f"{index}. {item_title}{when_suffix}\n{label}: {item_change}. {relevance_line}{f' Source: {item_url}' if english else f' Источник: {item_url}'}")
        lines.append("Why you received this: daily digest for your confirmed UTD scope, not a general news feed." if english else "Почему тебе: это дневная подборка по твоим подтверждённым темам UTD, не лента всех новостей.")
        return _bounded_text("\n".join(lines), TELEGRAM_TEXT_LIMIT)
    if not url or len(url) > 2048:
        return ""
    change_summary = _meaningful_change_summary(payload, change, english=language == "en")
    if not change_summary:
        # Do not turn an opaque source refresh into a notification.  A producer
        # must provide a bounded, human-readable change summary for updates.
        return ""
    if language == "en":
        lines = [f"{'Urgent. ' if rel.get('urgent') else ''}{title}", f"What changed: {change_summary}."]
        if reason or categories:
            lines.append(f"Why it matters to you: {_human_reason_en(reason, categories=categories)}")
        next_step = _candidate_next_step_en(category_values, change=change, urgent=bool(rel.get("urgent")))
        if next_step:
            lines.append(f"What to do: {next_step}")
        if depth in {"standard", "deep"} and str(payload.get("material_text") or "").strip():
            lines.append("Details: " + _bounded_text(str(payload.get("material_text") or "").strip(), 700 if depth == "deep" else 300))
        lines.append(f"Source: {url}")
        return _bounded_text("\n".join(lines), TELEGRAM_TEXT_LIMIT)
    lines = [f"{urgency}{title}", f"Что изменилось: {change_summary}."]
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
    if depth in {"standard", "deep"} and str(payload.get("material_text") or "").strip():
        lines.append("Деталь: " + _bounded_text(str(payload.get("material_text") or "").strip(), 700 if depth == "deep" else 300))
    lines.append(f"Источник: {url}")
    return _bounded_text("\n".join(lines), TELEGRAM_TEXT_LIMIT)


def render_on_demand_edition(events: Sequence[Mapping[str, Any]], *, source_health: Mapping[str, str] | None = None, detail_event_id: str = "") -> str:
    """Pure, non-delivery edition renderer for explicit user requests only."""
    health = source_health
    if not health:
        return "Покрытие источников не указано; нельзя честно сказать, есть ли новости."
    seen: set[str] = set()
    selected: list[Mapping[str, Any]] = []
    withheld_without_source = 0
    for event in events:
        if detail_event_id and str(event.get("event_id") or "") != detail_event_id:
            continue
        key = str(event.get("repost_family_id") or event.get("event_id") or "")
        if isinstance(event.get("payload"), Mapping) and isinstance(event["payload"].get("instance"), Mapping):
            key = str(event.get("event_id") or key)
        if not key or key in seen:
            continue
        seen.add(key)
        payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else event
        relevance = payload.get("relevance") if isinstance(payload.get("relevance"), Mapping) else {}
        if relevance.get("relevant") is False:
            continue
        if not _source_url({"canonical_url": event.get("canonical_url"), "url": payload.get("url")}):
            withheld_without_source += 1
            continue
        selected.append(event)
    if not selected:
        values = {str(value).casefold() for value in health.values()}
        if values <= {"healthy", "ok"}:
            status = "Новых релевантных событий в этом окне нет."
        elif values & {"healthy", "ok"}:
            status = "Покрытие частичное: часть источников недоступна; выпуск не является полным."
        elif "unknown" in values:
            status = "Покрытие источников неизвестно; нельзя честно сказать, есть ли новости."
        else:
            status = "Источники недоступны: " + _bounded_text(", ".join(sorted(health)), 300)
        if withheld_without_source:
            status += " События без ссылки на первоисточник не показаны."
        return status
    lines = ["Детали события" if detail_event_id else "Новости по теме (по запросу)"]
    unhealthy = sorted(key for key, value in health.items() if value not in {"healthy", "ok"})
    if unhealthy:
        _append_bounded(lines, "Не все источники доступны: " + _bounded_text(", ".join(unhealthy), 300) + ".")
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for event in selected:
        payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else event
        groups.setdefault(_edition_category(payload), []).append(event)
    grouped = [(category, event) for category, group in groups.items() for event in group]
    omitted = max(0, len(grouped) - 12) + withheld_without_source
    notice = f"… Не показано событий: {omitted}; запроси детали по одному." if omitted else ""
    reserve = len(notice) + 1 if notice else 0
    section = ""
    for index, (category, event) in enumerate(grouped[:12], 1):
        payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else event
        title = str(event.get("title") or payload.get("title") or "Событие")
        update = _format_timestamp(event.get("update_at")) or str(event.get("update_at") or "")
        url = _source_url({"canonical_url": event.get("canonical_url"), "url": payload.get("url")})
        publication = _format_timestamp(event.get("publication_at"))
        change = str(event.get("change_type") or "new")
        event_lines = [f"{index}. {title}" + (f" — обновлено {update}" if update else ""), f"   Изменение: {_edition_change(change)}."]
        if publication and publication != update:
            event_lines.append(f"   Опубликовано: {publication}; это не новая публикация только из-за обновления/репоста.")
        relevance = payload.get("relevance") if isinstance(payload.get("relevance"), Mapping) else {}
        category_values = [str(value) for value in relevance.get("categories") or [] if str(value)]
        categories = _display_categories(category_values)
        reason = _human_reason(str(relevance.get("reason") or "").strip(), categories=categories)
        event_lines.append(f"   Почему это может быть полезно: {reason or 'совпадает с выбранной темой.'}")
        if detail_event_id:
            detail = str(payload.get("change_summary") or payload.get("material_text") or "").strip()
            if detail:
                event_lines.append(f"   Деталь: {_bounded_text(detail, 500)}")
        if url:
            event_lines.append(f"   Источник: {url}")
        block = ((category + "\n") if category != section else "") + "\n".join(event_lines)
        if len("\n".join([*lines, block])) + reserve > TELEGRAM_TEXT_LIMIT:
            omitted = (len(grouped) - index + 1) + withheld_without_source
            break
        if category != section:
            section = category
        lines.append(block)
    if omitted:
        _append_bounded(lines, f"… Не показано событий: {omitted}; запроси детали по одному.")
    return "\n".join(lines)


def _append_bounded(lines: list[str], block: str) -> bool:
    if len("\n".join([*lines, block])) > TELEGRAM_TEXT_LIMIT:
        return False
    lines.append(block)
    return True


def _bounded_text(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: max(0, limit - 1)] + "…"


def _edition_category(payload: Mapping[str, Any]) -> str:
    relevance = payload.get("relevance") if isinstance(payload.get("relevance"), Mapping) else {}
    categories = relevance.get("categories") or payload.get("categories") or []
    values = [str(value) for value in categories] if isinstance(categories, Sequence) and not isinstance(categories, (str, bytes)) else []
    return "\n" + (_display_categories(values[:1]) or "Другие изменения")


def _edition_change(change: str) -> str:
    return {"new": "новое событие", "cosmetic_or_unchanged": "косметическое изменение", "material_update": "существенное исправление", "cancelled": "отмена", "disappeared": "исчезло из текущего окна"}.get(change, "обновление")


def _human_change(change: str) -> str:
    return {
        "new": "новое релевантное событие или ресурс",
        "updated": "официальная страница изменилась",
        "cancelled": "событие отменено или статус стал inactive",
        "reinstated": "событие снова активно",
        "daily_digest": "подборка релевантных изменений за день",
    }.get(str(change or "").casefold(), str(change or "updated"))


def _human_change_en(change: str) -> str:
    return {
        "new": "a new relevant event or resource was published",
        "updated": "the official page changed",
        "cancelled": "the event was cancelled or became inactive",
        "reinstated": "the event is active again",
        "daily_digest": "a daily set of relevant changes",
    }.get(str(change or "").casefold(), str(change or "updated"))


_DISPLAY_CATEGORY_LABELS = {
    "program": "программа",
    "career": "карьера",
    "ai": "AI и исследования",
    "isso": "ISSO",
    "benefits": "льготы и поддержка",
    "spouse_family": "семья",
}


def _display_categories(categories: Sequence[str]) -> str:
    return ", ".join(_DISPLAY_CATEGORY_LABELS.get(str(item), str(item)) for item in categories if str(item))


def _meaningful_change_summary(payload: Mapping[str, Any], change: str, *, english: bool) -> str:
    """Return an explicit change diff; never claim a generic page refresh is useful."""

    normalized = str(change or "").casefold()
    if normalized in {"cancelled", "reinstated"}:
        return _human_change_en(normalized) if english else _human_change(normalized)
    explicit = " ".join(str(payload.get("change_summary") or "").split()).strip(" .")
    if explicit:
        return _bounded_text(explicit, 500)
    if normalized == "new":
        return _human_change_en(normalized) if english else _human_change(normalized)
    return ""


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
    if lowered.startswith("synthetic ") or "confirmed scope" in lowered or lowered.endswith(" match") or clean.isascii():
        return f"совпадает с твоими подтверждёнными темами: {categories or 'UTD'}."
    return clean


def _human_reason_en(reason: str, *, categories: str) -> str:
    clean = " ".join(str(reason or "").replace("_", " ").split())
    if not clean or clean.casefold().startswith("synthetic ") or "confirmed scope" in clean.casefold():
        return f"it matches your confirmed UTD scope: {categories or 'UTD'}."
    return clean


def _candidate_next_step(categories: Sequence[str], *, change: str, urgent: bool) -> str:
    lowered = {item.casefold() for item in categories}
    prefix = "сегодня " if urgent or str(change).casefold() in {"cancelled", "reinstated"} else ""
    if "program" in lowered:
        return f"{prefix}открой источник и проверь, касается ли срок твоей программы."
    if "career" in lowered:
        return f"{prefix}проверь регистрацию и добавь событие в календарь, если оно подходит для поиска стажировки."
    if "ai" in lowered:
        return f"{prefix}открой страницу события и реши, стоит ли участвовать по теме AI или исследований."
    if "isso" in lowered:
        return f"{prefix}сверься с официальной страницей ISSO; не принимай иммиграционное решение только по уведомлению."
    if "benefits" in lowered:
        return f"{prefix}проверь условия доступности на странице ресурса перед действием."
    if "spouse_family" in lowered:
        return f"{prefix}проверь, явно ли указана доступность для семьи."
    return f"{prefix}открой источник и реши, нужно ли действие."


def _candidate_next_step_en(categories: Sequence[str], *, change: str, urgent: bool) -> str:
    lowered = {item.casefold() for item in categories}
    prefix = "today, " if urgent or str(change).casefold() in {"cancelled", "reinstated"} else ""
    if "program" in lowered:
        return f"{prefix}open the source and check whether the deadline applies to your program."
    if "career" in lowered:
        return f"{prefix}check registration and add the event if it fits your internship search."
    if "ai" in lowered:
        return f"{prefix}open the event page and decide whether it is useful for AI or research."
    if "isso" in lowered:
        return f"{prefix}check the ISSO page; do not make an immigration decision from this alert alone."
    if "benefits" in lowered or "spouse_family" in lowered:
        return f"{prefix}check eligibility on the source page before acting."
    return f"{prefix}open the source and decide whether action is needed."


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
            try:
                db.execute("ALTER TABLE delivery_outbox ADD COLUMN retry_after TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError:
                pass

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

    def enqueue_outbox(self, key: str, candidate: Mapping[str, Any]) -> bool:
        """Durably create one pending send; duplicate enqueue is harmless."""
        now = _now()
        with sqlite3.connect(self.path) as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO delivery_outbox(delivery_key,candidate_json,state,created_at,updated_at) VALUES(?,?, 'pending',?,?)",
                (key, json.dumps(dict(candidate), ensure_ascii=False, sort_keys=True), now, now),
            )
            db.commit()
        return bool(cursor.rowcount)

    def acknowledge_pending_candidate(self, candidate: Mapping[str, Any]) -> None:
        """Remove source-handoff work only after durable outbox acceptance."""
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM pending_delivery_candidates WHERE delivery_key=?", (delivery_key(candidate),))
            db.commit()

    def lease_outbox(self, key: str, *, now: datetime | None = None, lease_seconds: int = 60, max_attempts: int = 3) -> Mapping[str, Any] | None:
        """Atomically reserve a retryable item; unknown outcomes are never leased."""
        current = now or datetime.now(timezone.utc)
        expires = (current + timedelta(seconds=lease_seconds)).isoformat()
        now_text = current.isoformat()
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT candidate_json,state,lease_until,attempts,retry_after FROM delivery_outbox WHERE delivery_key=?", (key,)).fetchone()
            if row is None:
                db.rollback()
                return None
            candidate_json, state, lease_until, attempts, retry_after = row
            # A lost worker may have sent after Telegram accepted but before a
            # receipt commit. Expiry therefore becomes reconciliation-needed,
            # never an automatic resend.
            if state == "leased":
                if lease_until and str(lease_until) <= now_text:
                    db.execute("UPDATE delivery_outbox SET state='unknown',lease_until='',last_error='lease_expired_ambiguous',updated_at=? WHERE delivery_key=?", (now_text, key))
                    db.commit()
                else:
                    db.rollback()
                return None
            if state not in {"pending", "deferred"}:
                db.rollback()
                return None
            if state == "deferred" and retry_after and str(retry_after) > now_text:
                db.rollback()
                return None
            if int(attempts) >= max_attempts:
                db.execute("UPDATE delivery_outbox SET state='unknown',last_error='retry_budget_exhausted',updated_at=? WHERE delivery_key=?", (now_text, key))
                db.commit()
                return None
            updated = db.execute(
                "UPDATE delivery_outbox SET state='leased',attempts=attempts+1,lease_until=?,updated_at=? WHERE delivery_key=? AND state IN ('pending','deferred','leased')",
                (expires, now_text, key),
            )
            if updated.rowcount != 1:
                db.rollback()
                return None
            db.commit()
        return json.loads(str(candidate_json))

    def resolve_outbox(self, key: str, *, outcome: str, error: str = "") -> None:
        if outcome not in {"sent", "deferred", "unknown", "cancelled"}:
            raise ValueError("unsupported outbox outcome")
        with sqlite3.connect(self.path) as db:
            retry_after = ""
            if outcome == "deferred":
                row = db.execute("SELECT attempts FROM delivery_outbox WHERE delivery_key=?", (key,)).fetchone()
                delay = min(300, 30 * (2 ** max(0, int(row[0] if row else 1) - 1)))
                retry_after = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
            updated = db.execute(
                "UPDATE delivery_outbox SET state=?,lease_until='',retry_after=?,last_error=?,updated_at=? WHERE delivery_key=? AND state='leased'",
                (outcome, retry_after, error[:500], _now(), key),
            )
            if updated.rowcount != 1:
                raise ValueError("outbox item is not leased")
            db.commit()

    def outbox_state(self, key: str) -> str:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT state FROM delivery_outbox WHERE delivery_key=?", (key,)).fetchone()
        return str(row[0]) if row else ""

    def reserve_quota(self, key: str, *, units: int, cap: int = 5, now: datetime | None = None) -> bool:
        """Atomically reserve conservative daily capacity before a send attempt."""
        current = now or datetime.now(timezone.utc)
        day = current.astimezone(_UTD_TIMEZONE).date().isoformat()
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT 1 FROM delivery_quota_reservations WHERE reservation_key=?", (key,)).fetchone()
            if existing:
                db.rollback()
                return True
            reserved = int(db.execute("SELECT COALESCE(SUM(r.units),0) FROM delivery_quota_reservations r WHERE r.local_day=? AND NOT EXISTS (SELECT 1 FROM delivery_receipts d WHERE d.delivery_key=r.reservation_key OR r.reservation_key LIKE d.delivery_key || ':%')", (day,)).fetchone()[0])
            receipt_rows = db.execute("SELECT delivered_at,payload_json FROM delivery_receipts").fetchall()
            receipts = 0
            for delivered_at, raw in receipt_rows:
                try:
                    delivered = datetime.fromisoformat(str(delivered_at).replace("Z", "+00:00")).astimezone(_UTD_TIMEZONE).date().isoformat()
                    payload = json.loads(str(raw))
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
                if delivered == day and not payload.get("digest_component"):
                    receipts += len(payload.get("digest_items") or []) or 1
            used = reserved + receipts
            if used + units > cap:
                db.rollback()
                return False
            db.execute("INSERT INTO delivery_quota_reservations(reservation_key,local_day,units,state,created_at) VALUES(?,?,?,'reserved',?)", (key, day, units, current.isoformat()))
            db.commit()
        return True

    def reserve_ordinary_digest(self, key: str, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        day = current.astimezone(_UTD_TIMEZONE).date().isoformat()
        with sqlite3.connect(self.path) as db:
            try:
                db.execute("INSERT INTO ordinary_digest_reservations(local_day,delivery_key,created_at) VALUES(?,?,?)", (day, key, current.isoformat()))
            except sqlite3.IntegrityError:
                return False
            db.commit()
        return True

    def prepare_ordinary_outbox(self, key: str, candidate: Mapping[str, Any], *, units: int, cap: int = 5, now: datetime | None = None) -> bool:
        """Atomically reserve the daily digest slot, quota and durable work."""
        current = now or datetime.now(timezone.utc)
        day = current.astimezone(_UTD_TIMEZONE).date().isoformat()
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM ordinary_digest_reservations WHERE local_day=?", (day,)).fetchone():
                db.rollback(); return False
            reserved = int(db.execute("SELECT COALESCE(SUM(r.units),0) FROM delivery_quota_reservations r WHERE r.local_day=? AND NOT EXISTS (SELECT 1 FROM delivery_receipts d WHERE d.delivery_key=r.reservation_key OR r.reservation_key LIKE d.delivery_key || ':%')", (day,)).fetchone()[0])
            receipts = 0
            for delivered_at, raw in db.execute("SELECT delivered_at,payload_json FROM delivery_receipts"):
                try:
                    delivered = datetime.fromisoformat(str(delivered_at).replace("Z", "+00:00")).astimezone(_UTD_TIMEZONE).date().isoformat()
                    payload = json.loads(str(raw))
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
                if delivered == day and not payload.get("digest_component"):
                    receipts += len(payload.get("digest_items") or []) or 1
            if reserved + receipts + units > cap:
                db.rollback(); return False
            db.execute("INSERT INTO ordinary_digest_reservations(local_day,delivery_key,created_at) VALUES(?,?,?)", (day, key, current.isoformat()))
            db.execute("INSERT INTO delivery_quota_reservations(reservation_key,local_day,units,state,created_at) VALUES(?,?,?,'reserved',?)", (key, day, units, current.isoformat()))
            db.execute("INSERT INTO delivery_outbox(delivery_key,candidate_json,state,created_at,updated_at) VALUES(?,?, 'pending',?,?)", (key, json.dumps(dict(candidate), ensure_ascii=False, sort_keys=True), current.isoformat(), current.isoformat()))
            db.commit()
        return True

    def pending_ordinary_outbox(self, *, now: datetime | None = None) -> tuple[str, dict[str, Any]] | None:
        current = now or datetime.now(timezone.utc)
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT r.delivery_key,o.candidate_json FROM ordinary_digest_reservations r "
                "JOIN delivery_outbox o ON o.delivery_key=r.delivery_key "
                "WHERE o.state IN ('pending','deferred') ORDER BY r.created_at ASC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return str(row[0]), json.loads(str(row[1]))

    def ordinary_reservation_day(self, key: str) -> str:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT local_day FROM ordinary_digest_reservations WHERE delivery_key=?", (key,)).fetchone()
        return str(row[0]) if row else ""

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
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            rows = [(key, digest)] + [(item_key, {**dict(item), "digest_component": True, "digest_key": key}) for item_key, item in items]
            for delivery_key_value, candidate in rows:
                db.execute(
                    "INSERT OR IGNORE INTO delivery_receipts(delivery_key,source,item_key,change_type,delivered_at,telegram_message_id,payload_json) VALUES(?,?,?,?,?,?,?)",
                    (delivery_key_value, str(candidate.get("source") or ""), str(candidate.get("item_key") or ""), str(candidate.get("change_type") or ""), _now(), message_id, json.dumps(candidate, ensure_ascii=False, sort_keys=True)),
                )
            db.commit()

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

    def ordinary_digest_delivered_today(self, *, now: datetime | None = None) -> bool:
        """Return whether a non-urgent digest has already been sent today.

        Frequent polling should not turn ordinary UTD matches into multiple
        newsletter-like messages. Urgent candidates still use their own
        candidate-level idempotency and daily cap.
        """
        local_day = (now or datetime.now(timezone.utc)).astimezone(_UTD_TIMEZONE).date()
        with sqlite3.connect(self.path) as db:
            rows = db.execute(
                "SELECT delivered_at,payload_json FROM delivery_receipts WHERE change_type='daily_digest'"
            ).fetchall()
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
            if isinstance(payload, dict) and not payload.get("digest_component"):
                return True
        return False

    def record_feedback(self, key: str, action: str) -> str:
        if action not in _ALLOWED_FEEDBACK:
            raise ValueError("Unsupported watch feedback")
        with sqlite3.connect(self.path) as db:
            if db.execute("SELECT 1 FROM delivery_receipts WHERE delivery_key=?", (key,)).fetchone() is None:
                raise ValueError("Unknown delivery receipt")
            db.execute("INSERT OR IGNORE INTO watch_feedback(delivery_key,action,recorded_at) VALUES(?,?,?)", (key, action, _now()))
            db.commit()
        return action

    def has_delivery_receipt(self, key: str) -> bool:
        with sqlite3.connect(self.path) as db:
            return db.execute(
                "SELECT 1 FROM delivery_receipts WHERE delivery_key=?", (key,)
            ).fetchone() is not None

    def paused_until(self, *, now: datetime | None = None) -> str:
        """Return a sidecar-only temporary delivery pause timestamp, if active."""
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT recorded_at FROM watch_feedback WHERE action='pause' ORDER BY recorded_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return ""
        try:
            recorded_at = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
        except ValueError:
            return ""
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=timezone.utc)
        until = recorded_at.astimezone(timezone.utc) + _FEEDBACK_PAUSE_WINDOW
        if until <= current:
            return ""
        return until.isoformat().replace("+00:00", "Z")

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
            "paused_until": self.paused_until(),
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
    subscription: Mapping[str, Any] | None = None,
    profile_db: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not delivery_enabled(explicit=explicit_enable, env=env):
        return {"enabled": False, "sent": 0, "duplicates_blocked": 0, "daily_cap_blocked": 0}
    if not token or not chat_id:
        raise ValueError("Telegram token and owner chat id are required")
    # The caller's snapshot is enough for fixture-only/direct use.  The live
    # runner supplies profile_db so a cancellation between selection and send
    # is observed at this boundary too.
    if profile_db is not None:
        from .profile import load_confirmed_utd_profile
        subscription = load_confirmed_utd_profile(profile_db, now=now)
    effect = subscription_effect(subscription, runtime_enabled=True)
    if not effect["deliver"]:
        return {"enabled": True, "sent": 0, "duplicates_blocked": 0, "daily_cap_blocked": 0, "suppressed_by_subscription": effect["reason"]}
    if str(subscription.get("frequency") or "daily_digest") == "urgent_only":
        candidates = [item for item in candidates if bool((item.get("relevance") or {}).get("urgent"))]
        if not candidates:
            return {"enabled": True, "sent": 0, "duplicates_blocked": 0, "daily_cap_blocked": 0, "suppressed_by_subscription": "urgent_only"}
    if subscription is not None:
        current_subscription_time = now or datetime.now(timezone.utc)
        if in_quiet_hours(subscription, now=current_subscription_time):
            return {"enabled": True, "sent": 0, "duplicates_blocked": 0, "daily_cap_blocked": 0, "suppressed_by_subscription": "quiet_hours"}
        ordinary_due = scheduled_delivery_due(subscription, now=current_subscription_time)
        if not ordinary_due:
            # Urgent, source-supported changes are explicitly allowed outside
            # the ordinary digest schedule; ordinary candidates remain queued
            # only on a later scheduled run.
            candidates = [item for item in candidates if bool((item.get("relevance") or {}).get("urgent"))]
            if not candidates:
                return {"enabled": True, "sent": 0, "duplicates_blocked": 0, "daily_cap_blocked": 0, "suppressed_by_subscription": "schedule"}
    else:
        ordinary_due = True
    if sender is None:
        from bot.telegram_delivery import send_text
        sender = send_text
    store = DeliveryStore(sidecar_db)
    paused_until = store.paused_until()
    if paused_until:
        return {
            "enabled": True,
            "sent": 0,
            "duplicates_blocked": 0,
            "daily_cap_blocked": 0,
            "ordinary_digest_blocked": 0,
            "suppressed_by_pause": len(candidates),
            "paused_until": paused_until,
        }
    current = now or datetime.now(timezone.utc)
    current_day = current.astimezone(_UTD_TIMEZONE).date().isoformat()
    recovered = store.pending_ordinary_outbox(now=current)
    if recovered is not None and ordinary_due:
        recovered_key, recovered_digest = recovered
        recovered_items = [(delivery_key(item), item) for item in recovered_digest.get("digest_items") or [] if isinstance(item, Mapping)]
        recovered_units = max(1, len(recovered_items))
        prepared_day = store.ordinary_reservation_day(recovered_key)
        recovery_quota_key = f"{recovered_key}:recovery:{current_day}"
        recovery_cap = int(subscription.get("daily_cap") or 5) if subscription is not None else 5
        recovery_allowed = (prepared_day == current_day and store.delivered_item_count_today(now=current) + recovered_units <= recovery_cap) or store.reserve_quota(recovery_quota_key, units=recovered_units, cap=recovery_cap, now=current)
        recovered_result = "daily_cap_blocked"
        if recovery_allowed:
            recovered_result = deliver_outbox_item(sidecar_db=sidecar_db, key=recovered_key, token=token, chat_id=chat_id, sender=sender, digest_components=recovered_items, explicit_enable=explicit_enable, env=env, subscription=subscription, profile_db=profile_db, now=current)
        if recovered_result == "sent":
            return {"enabled": True, "sent": 1, "duplicates_blocked": 0, "daily_cap_blocked": 0, "ordinary_digest_blocked": 0, "suppressed_by_pause": 0, "paused_until": "", "recovered_pending_digest": True}
    sent = 0
    duplicates = 0
    daily_cap = int(subscription.get("daily_cap") or 5) if subscription is not None else 5
    daily_cap = daily_cap if daily_cap in {1, 3, 5} else 1
    remaining = max(0, daily_cap - store.delivered_item_count_today(now=current))
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
        if not store.reserve_quota(key, units=1, cap=daily_cap):
            daily_cap_blocked += 1
            continue
        store.enqueue_outbox(key, _bound_candidate(candidate, subscription))
        store.acknowledge_pending_candidate(candidate)
        if deliver_outbox_item(sidecar_db=sidecar_db, key=key, token=token, chat_id=chat_id, sender=sender, explicit_enable=explicit_enable, env=env, subscription=subscription, profile_db=profile_db, now=current, allow_outside_schedule=True) == "sent":
            sent += 1
    remaining -= min(len(urgent), remaining)
    ordinary_digest_blocked = 0
    if remaining and ordinary:
        if store.ordinary_digest_delivered_today():
            ordinary_digest_blocked = len(ordinary)
            ordinary = []
        else:
            ordinary_digest_blocked = max(0, len(ordinary) - remaining)
            ordinary = ordinary[:remaining]
    if remaining and ordinary:
        ordinary = _bounded_digest_components(ordinary)
        if not ordinary:
            return {"enabled": True, "sent": sent, "duplicates_blocked": duplicates, "daily_cap_blocked": daily_cap_blocked, "ordinary_digest_blocked": ordinary_digest_blocked, "suppressed_by_pause": 0, "paused_until": ""}
        digest_items = [dict(candidate) for _, candidate in ordinary]
        digest = _build_daily_digest(digest_items)
        digest = _bound_candidate(digest, subscription)
        key = delivery_key(digest)
        if store.already_delivered(key):
            duplicates += len(digest_items)
        else:
            if not store.prepare_ordinary_outbox(key, digest, units=len(digest_items), cap=daily_cap):
                ordinary_digest_blocked = len(digest_items)
            else:
                for _, component in ordinary:
                    store.acknowledge_pending_candidate(component)
            if store.outbox_state(key) in {"pending", "deferred"} and deliver_outbox_item(sidecar_db=sidecar_db, key=key, token=token, chat_id=chat_id, sender=sender, digest_components=ordinary, explicit_enable=explicit_enable, env=env, subscription=subscription, profile_db=profile_db, now=current) == "sent":
                sent += 1
    return {
        "enabled": True,
        "sent": sent,
        "duplicates_blocked": duplicates,
        "daily_cap_blocked": daily_cap_blocked,
        "ordinary_digest_blocked": ordinary_digest_blocked,
        "suppressed_by_pause": 0,
        "paused_until": "",
    }


def deliver_outbox_item(
    *,
    sidecar_db: str | Path,
    key: str,
    token: str,
    chat_id: str,
    sender: Callable[..., int | None],
    digest_components: Sequence[tuple[str, Mapping[str, Any]]] = (),
    explicit_enable: bool = False,
    env: Mapping[str, str] | None = None,
    subscription: Mapping[str, Any] | None = None,
    profile_db: str | Path | None = None,
    now: datetime | None = None,
    allow_outside_schedule: bool = False,
) -> str:
    """Attempt one leased outbox item; ambiguity is retained as `unknown`.

    This function is deliberately not a scheduler. A future confirmed
    subscription runner must call it only after its own scope/kill checks.
    """
    if not delivery_enabled(explicit=explicit_enable, env=env):
        return "disabled"
    if profile_db is not None:
        from .profile import load_confirmed_utd_profile
        subscription = load_confirmed_utd_profile(profile_db, now=now)
    effect = subscription_effect(subscription, runtime_enabled=True)
    if not effect["deliver"]:
        return "subscription_blocked"
    if subscription is not None and (in_quiet_hours(subscription, now=now) or (not allow_outside_schedule and not scheduled_delivery_due(subscription, now=now))):
        return "subscription_blocked"
    store = DeliveryStore(sidecar_db)
    candidate = store.lease_outbox(key)
    if candidate is None:
        return "not_leased"
    if not _candidate_bound_to_current_subscription(candidate, subscription, require_binding=profile_db is not None):
        store.resolve_outbox(key, outcome="cancelled", error="subscription_revision_changed")
        return "subscription_blocked"
    relevance = candidate.get("relevance") if isinstance(candidate.get("relevance"), Mapping) else {}
    candidate_categories = set(relevance.get("categories") or [])
    active_categories = set(subscription.get("categories") or []) - set(subscription.get("muted_sources") or [])
    if (candidate_categories & set(subscription.get("muted_sources") or [])) or (candidate_categories and not (candidate_categories & active_categories)):
        store.resolve_outbox(key, outcome="cancelled", error="subscription_muted")
        return "subscription_blocked"
    payload = candidate.get("payload") if isinstance(candidate.get("payload"), Mapping) else {}
    candidate_text = " ".join(str(payload.get(field) or "").casefold() for field in ("title", "material_text", "url"))
    if any(str(exclusion).casefold().strip() in candidate_text for exclusion in subscription.get("exclusions") or [] if str(exclusion).strip()):
        store.resolve_outbox(key, outcome="cancelled", error="subscription_exclusion")
        return "subscription_blocked"
    if digest_components:
        digest_components = _bounded_digest_components(digest_components)
        if not digest_components:
            store.resolve_outbox(key, outcome="cancelled", error="missing_primary_source")
            return "subscription_blocked"
        if profile_db is not None and any(not _candidate_bound_to_current_subscription(component, subscription, require_binding=True) for _, component in digest_components):
            store.resolve_outbox(key, outcome="cancelled", error="subscription_revision_changed")
            return "subscription_blocked"
        candidate = {**candidate, "digest_items": [dict(item) for _, item in digest_components]}
    try:
        text = render_candidate(candidate, language=str(subscription.get("language") or "ru"), depth=str(subscription.get("depth") or "brief"))
        if not text:
            store.resolve_outbox(key, outcome="cancelled", error="missing_primary_source")
            return "subscription_blocked"
        # Terminal delivery decision: a lifecycle edit/cancellation that wins
        # before this guard must stop a leased item. A later lifecycle event is
        # ordered after the transport decision; no exactly-once claim follows.
        if profile_db is not None:
            from .profile import load_confirmed_utd_profile
            subscription = load_confirmed_utd_profile(profile_db, now=now)
            terminal_effect = subscription_effect(subscription, runtime_enabled=True)
            if not delivery_enabled(explicit=explicit_enable, env=env) or not terminal_effect["deliver"] or not _candidate_bound_to_current_subscription(candidate, subscription, require_binding=True):
                store.resolve_outbox(key, outcome="cancelled", error="terminal_subscription_or_kill_block")
                return "subscription_blocked"
        message_id = sender(chat_id=chat_id, text=text, token=token, parse_mode=None, reply_markup=build_feedback_markup(key, language=str(subscription.get("language") or "ru")))
    except KnownDeliveryFailure as exc:
        store.resolve_outbox(key, outcome="deferred", error=type(exc).__name__)
        return "deferred"
    except TelegramKnownRejection as exc:
        store.resolve_outbox(key, outcome="deferred", error=type(exc).__name__)
        return "deferred"
    except Exception as exc:
        # A transport failure may be before or after Telegram acceptance. Do
        # not blind-retry it; an operator/receipt reconciliation decides next.
        store.resolve_outbox(key, outcome="unknown", error=type(exc).__name__)
        return "unknown"
    if message_id is None:
        store.resolve_outbox(key, outcome="unknown", error="missing_message_id")
        return "unknown"
    if digest_components:
        store.record_digest(key, candidate, digest_components, int(message_id))
    else:
        store.record_delivery(key, candidate, int(message_id))
    store.resolve_outbox(key, outcome="sent")
    return "sent"


def _bound_candidate(candidate: Mapping[str, Any], subscription: Mapping[str, Any]) -> dict[str, Any]:
    """Carry canonical profile revision with durable work when one is available."""
    bound = dict(candidate)
    if candidate.get("subscription_memory_id") and candidate.get("subscription_event_id") is not None:
        return bound
    memory_id = str(subscription.get("subscription_memory_id") or "")
    event_id = subscription.get("subscription_event_id")
    if memory_id and isinstance(event_id, int):
        bound["subscription_memory_id"] = memory_id
        bound["subscription_event_id"] = event_id
    return bound


def _candidate_bound_to_current_subscription(candidate: Mapping[str, Any], subscription: Mapping[str, Any], *, require_binding: bool = False) -> bool:
    memory_id = str(candidate.get("subscription_memory_id") or "")
    event_id = candidate.get("subscription_event_id")
    if not memory_id and event_id is None:
        if require_binding:
            return False
        return True  # direct/synthetic caller has no canonical profile reference
    return memory_id == str(subscription.get("subscription_memory_id") or "") and event_id == subscription.get("subscription_event_id")


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
                    "url": _source_url(item.get("payload") if isinstance(item.get("payload"), Mapping) else {}),
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


def _bounded_digest_components(items: Sequence[tuple[str, Mapping[str, Any]]]) -> list[tuple[str, Mapping[str, Any]]]:
    """Keep only components whose complete source link fits in final Telegram text."""
    lines = ["UTD: важное на сегодня"]
    footer = "Почему тебе: это дневной digest по подтверждённому UTD scope, не лента всех новостей."
    kept: list[tuple[str, Mapping[str, Any]]] = []
    for key, candidate in items:
        payload = candidate.get("payload") if isinstance(candidate.get("payload"), Mapping) else {}
        url = _source_url(payload)
        if not url or len(url) > 2048:
            continue
        title = _bounded_text(str(payload.get("title") or "UTD update").strip(), 450)
        when = _candidate_time(payload)
        line = f"{len(kept) + 1}. {title}{f' · {when}' if when else ''} — {url}"
        if len("\n".join([*lines, line, footer])) > TELEGRAM_TEXT_LIMIT:
            break
        lines.append(line)
        kept.append((key, candidate))
    return kept


def _source_url(payload: Mapping[str, Any]) -> str:
    # Fetch allowlisting is not enough: event payloads can carry arbitrary
    # links. Only display a direct, policy-valid primary source URL.
    from .fetch import FetchError, validate_url
    for raw in (payload.get("canonical_url"), payload.get("url")):
        value = str(raw or "").strip()
        if not value:
            continue
        try:
            validate_url(value)
        except FetchError:
            continue
        return value
    return ""


def handle_feedback_callback(sidecar_db: str | Path, callback_data: str) -> dict[str, Any]:
    parts = callback_data.split(":")
    if len(parts) not in {3, 4} or parts[0] != FEEDBACK_PREFIX or (len(parts) == 4 and parts[3] != "en"):
        raise ValueError("Unsupported watch callback")
    key, action = parts[1], parts[2]
    store = DeliveryStore(sidecar_db)
    if action == "settings":
        if not store.has_delivery_receipt(key):
            raise ValueError("Unknown delivery receipt")
        english = len(parts) == 4
        return {
            "message": "Notification settings for this update:" if english else "Настройки для этого уведомления:",
            "action": action,
            "settings_opened": True,
            "reply_markup": build_feedback_settings_markup(key, language="en" if english else "ru"),
        }
    recorded = store.record_feedback(key, action)
    messages = {
        "useful": "Записал: полезно.",
        "noise": "Записал: это шум.",
        "more": "Записал: больше такого.",
        "less": "Записал: меньше такого.",
        "mute": "Записал: источник неинтересен. Он не будет отключён автоматически без подтверждения профиля.",
        "pause": "Приостановил UTD-уведомления на 24 часа. Подтверждённый профиль не изменён.",
    }
    if len(parts) == 4:
        messages = {"useful": "Recorded: useful.", "noise": "Recorded: noise.", "more": "Recorded: more like this.", "less": "Recorded: less like this.", "mute": "Recorded: this source is not useful. It is not disabled without profile confirmation.", "pause": "UTD notifications paused for 24 hours; the confirmed profile was not changed."}
    return {"message": messages[recorded], "action": recorded}
