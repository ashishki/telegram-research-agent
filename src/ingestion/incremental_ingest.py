import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.settings import PROJECT_ROOT, Settings
from ingestion.bootstrap_ingest import (
    MAX_FLOOD_WAIT_SECONDS,
    _extract_message_row,
    _insert_message,
    _load_active_channels,
)
from ingestion.telegram_client import make_client
from telethon.errors import FloodWaitError


LOGGER = logging.getLogger(__name__)
CHANNELS_PATH = PROJECT_ROOT / "src" / "config" / "channels.yaml"
DEFAULT_LOOKBACK_DAYS = 7


def _parse_posted_at(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _get_channel_cutoff(connection: sqlite3.Connection, channel_username: str) -> datetime:
    row = connection.execute(
        "SELECT MAX(posted_at) FROM raw_posts WHERE channel_username = ?",
        (channel_username,),
    ).fetchone()
    latest_posted_at = _parse_posted_at(row[0] if row else None)
    if latest_posted_at is not None:
        return latest_posted_at
    return datetime.now(timezone.utc) - timedelta(days=DEFAULT_LOOKBACK_DAYS)


async def _ingest_channel(client, connection: sqlite3.Connection, channel: dict) -> dict:
    channel_username = channel["username"]

    while True:
        channel_inserted = 0
        channel_skipped = 0
        cutoff_date = _get_channel_cutoff(connection, channel_username)

        try:
            entity = await client.get_entity(channel_username)
            cursor = connection.cursor()
            cursor.execute("BEGIN")
            ingested_at = datetime.now(timezone.utc).isoformat()

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
                "Incremental channel=%s since=%s inserted=%d skipped=%d",
                channel_username,
                cutoff_date.isoformat(),
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
            LOGGER.exception("Incremental ingest failed for channel %s", channel_username)
            return {"inserted": 0, "skipped": 0, "errors": 1}


async def run_incremental(settings: Settings) -> dict:
    channels = _load_active_channels()
    totals = {"inserted": 0, "skipped": 0, "errors": 0}

    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    client = await make_client(settings)
    try:
        with sqlite3.connect(settings.db_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON;")
            connection.execute("PRAGMA journal_mode = WAL;")

            for channel in channels:
                result = await _ingest_channel(client, connection, channel)
                totals["inserted"] += result["inserted"]
                totals["skipped"] += result["skipped"]
                totals["errors"] += result["errors"]
    finally:
        await client.disconnect()

    LOGGER.info(
        "Incremental summary inserted=%d skipped=%d errors=%d channels=%s",
        totals["inserted"],
        totals["skipped"],
        totals["errors"],
        CHANNELS_PATH,
    )
    return totals
