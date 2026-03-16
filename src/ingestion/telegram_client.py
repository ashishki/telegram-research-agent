import logging
import os

from telethon import TelegramClient

from config.settings import Settings


LOGGER = logging.getLogger(__name__)


async def make_client(settings: Settings) -> TelegramClient:
    api_id_raw = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")

    if not api_id_raw or not api_hash:
        raise RuntimeError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set")

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise RuntimeError("TELEGRAM_API_ID must be an integer") from exc

    client = TelegramClient(settings.telegram_session_path, api_id, api_hash)
    LOGGER.info("Connecting Telethon client with session %s", settings.telegram_session_path)
    await client.connect()

    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError("Telegram session is not authorized; run interactive setup first")

    LOGGER.info("Telethon client connected")
    return client
