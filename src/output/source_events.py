from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config.settings import PROJECT_ROOT


EVENT_SCHEMA_VERSION = "source_event.v1"
DEFAULT_SOURCE_EVENT_ROOT = PROJECT_ROOT / "data" / "events" / "source_events"


def telegram_source_event_from_row(row: dict[str, Any] | sqlite3.Row) -> dict[str, Any]:
    channel = _text(_value(row, "channel_username"))
    message_id = _int(_value(row, "message_id"))
    text = _text(_value(row, "text"))
    media_caption = _optional_text(_value(row, "media_caption"))
    content = text or media_caption or ""
    posted_at = _text(_value(row, "posted_at"))
    captured_at = _text(_value(row, "ingested_at")) or _now_iso()
    source_url = _optional_text(_value(row, "message_url")) or _message_url(channel, message_id)
    upstream_id = f"telegram:{channel}:{message_id}"
    payload = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_type": "telegram_post",
        "source_type": "telegram",
        "upstream_id": upstream_id,
        "source_url": source_url,
        "channel_username": channel,
        "channel_id": _optional_text(_value(row, "channel_id")),
        "message_id": message_id,
        "posted_at": posted_at,
        "captured_at": captured_at,
        "text": content,
        "media_type": _text(_value(row, "media_type")) or "none",
        "view_count": _int(_value(row, "view_count")),
        "content_hash": _content_hash(channel=channel, message_id=message_id, text=content),
    }
    if media_caption and media_caption != text:
        payload["media_caption"] = media_caption
    image_description = _optional_text(_value(row, "image_description"))
    if image_description:
        payload["image_description"] = image_description
    return payload


def append_source_events(
    events: list[dict[str, Any]],
    *,
    event_root: Path | str | None = None,
) -> list[Path]:
    if not events:
        return []
    root = Path(event_root) if event_root is not None else DEFAULT_SOURCE_EVENT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[_event_date(event)].append(event)

    written_paths: list[Path] = []
    for date_label, date_events in sorted(grouped.items()):
        path = root / f"{date_label}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            for event in date_events:
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        written_paths.append(path)
    return written_paths


def backfill_recent_source_events(
    connection: sqlite3.Connection,
    *,
    days: int = 14,
    event_root: Path | str | None = None,
    limit: int = 5000,
) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, int(days or 14)))).isoformat()
    rows = connection.execute(
        """
        SELECT channel_username, channel_id, message_id, posted_at, text, media_type,
               media_caption, view_count, message_url, image_description, ingested_at
        FROM raw_posts
        WHERE posted_at >= ?
        ORDER BY posted_at ASC, id ASC
        LIMIT ?
        """,
        (cutoff, max(1, int(limit or 5000))),
    ).fetchall()
    events = [telegram_source_event_from_row(row) for row in rows]
    append_source_events(_dedupe_events(events), event_root=event_root)
    return len(events)


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for event in events:
        upstream_id = _text(event.get("upstream_id"))
        if not upstream_id or upstream_id in seen:
            continue
        seen.add(upstream_id)
        deduped.append(event)
    return deduped


def _event_date(event: dict[str, Any]) -> str:
    value = _text(event.get("captured_at")) or _text(event.get("posted_at"))
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return datetime.now(timezone.utc).date().isoformat()


def _value(row: dict[str, Any] | sqlite3.Row, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return row[key]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _optional_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _message_url(channel_username: str, message_id: int) -> str | None:
    normalized = channel_username.strip().lstrip("@")
    if not normalized or normalized.startswith("+") or normalized.isdigit() or message_id <= 0:
        return None
    return f"https://t.me/{normalized}/{message_id}"


def _content_hash(*, channel: str, message_id: int, text: str) -> str:
    payload = f"{channel}\n{message_id}\n{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
