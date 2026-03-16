import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from telethon.errors import FloodWaitError

from config.settings import PROJECT_ROOT, Settings
from ingestion.telegram_client import make_client


LOGGER = logging.getLogger(__name__)
CHANNELS_PATH = PROJECT_ROOT / "src" / "config" / "channels.yaml"
MAX_FLOOD_WAIT_SECONDS = 600


def _load_active_channels() -> list[dict]:
    payload = yaml.safe_load(CHANNELS_PATH.read_text(encoding="utf-8")) or {}
    channels = payload.get("channels", [])
    return [channel for channel in channels if channel.get("active")]


def _to_utc_iso(value: datetime | None) -> str:
    if value is None:
        value = datetime.now(timezone.utc)
    elif value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _detect_media_type(message) -> str:
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.document:
        return "document"
    return "none"


def _extract_message_row(message, channel_username: str, ingested_at: str) -> dict:
    text = message.message or ""
    media_type = _detect_media_type(message)
    media_caption = text if media_type != "none" else None
    forward_from = str(message.fwd_from.from_id) if message.fwd_from else None

    payload = {
        "channel_username": channel_username,
        "channel_id": message.peer_id.channel_id,
        "message_id": message.id,
        "posted_at": _to_utc_iso(message.date),
        "text": text,
        "media_type": media_type,
        "media_caption": media_caption,
        "forward_from": forward_from,
        "view_count": message.views or 0,
    }
    payload["raw_json"] = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    payload["ingested_at"] = ingested_at
    return payload


def _insert_message(cursor: sqlite3.Cursor, row: dict) -> None:
    cursor.execute(
        """
        INSERT INTO raw_posts (
            channel_username,
            channel_id,
            message_id,
            posted_at,
            text,
            media_type,
            media_caption,
            forward_from,
            view_count,
            raw_json,
            ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["channel_username"],
            row["channel_id"],
            row["message_id"],
            row["posted_at"],
            row["text"],
            row["media_type"],
            row["media_caption"],
            row["forward_from"],
            row["view_count"],
            row["raw_json"],
            row["ingested_at"],
        ),
    )


async def _ingest_channel(client, connection: sqlite3.Connection, channel: dict, cutoff_date: datetime) -> dict:
    channel_username = channel["username"]

    while True:
        channel_inserted = 0
        channel_skipped = 0
        try:
            entity = await client.get_entity(channel_username)
            cursor = connection.cursor()
            cursor.execute("BEGIN")
            ingested_at = _to_utc_iso(datetime.now(timezone.utc))

            # Telethon treats offset_date as a lower bound when iterating in reverse order.
            async for message in client.iter_messages(entity, offset_date=cutoff_date, reverse=True):
                if message is None or message.id is None or message.peer_id is None:
                    continue
                if message.date and message.date < cutoff_date:
                    continue

                row = _extract_message_row(message, channel_username, ingested_at)
                try:
                    _insert_message(cursor, row)
                except sqlite3.IntegrityError:
                    channel_skipped += 1
                    continue
                channel_inserted += 1

            connection.commit()
            LOGGER.info(
                "Bootstrap channel=%s inserted=%d skipped=%d",
                channel_username,
                channel_inserted,
                channel_skipped,
            )
            return {"inserted": channel_inserted, "skipped": channel_skipped, "errors": 0}
        except FloodWaitError as exc:
            connection.rollback()
            wait_seconds = int(exc.seconds)
            if wait_seconds > MAX_FLOOD_WAIT_SECONDS:
                LOGGER.error(
                    "FloodWait: sleeping %ss for channel %s exceeds ceiling; skipping channel",
                    wait_seconds,
                    channel_username,
                )
                return {"inserted": 0, "skipped": 0, "errors": 1}
            LOGGER.warning("FloodWait: sleeping %ss for channel %s", wait_seconds, channel_username)
            await asyncio.sleep(wait_seconds)
        except Exception:
            connection.rollback()
            LOGGER.exception("Bootstrap failed for channel %s", channel_username)
            return {"inserted": 0, "skipped": 0, "errors": 1}


async def run_bootstrap(settings: Settings) -> dict:
    channels = _load_active_channels()
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=90)
    totals = {"inserted": 0, "skipped": 0, "errors": 0}

    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    client = await make_client(settings)
    try:
        with sqlite3.connect(settings.db_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON;")
            connection.execute("PRAGMA journal_mode = WAL;")

            for channel in channels:
                result = await _ingest_channel(client, connection, channel, cutoff_date)
                totals["inserted"] += result["inserted"]
                totals["skipped"] += result["skipped"]
                totals["errors"] += result["errors"]
    finally:
        await client.disconnect()

    LOGGER.info(
        "Bootstrap summary inserted=%d skipped=%d errors=%d",
        totals["inserted"],
        totals["skipped"],
        totals["errors"],
    )
    return totals
