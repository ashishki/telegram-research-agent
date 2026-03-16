#!/usr/bin/env bash
# Run this script ONCE interactively in an SSH terminal to authorize Telethon.
# It will prompt for your phone number and the code Telegram sends you.
set -euo pipefail

set -a
source /srv/openclaw-you/.env
set +a

mkdir -p /srv/openclaw-you/secrets

/srv/openclaw-you/venv/bin/python3 - << 'PYEOF'
import asyncio, os
from telethon import TelegramClient

api_id   = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
session  = os.environ.get("TELEGRAM_SESSION_PATH", "/srv/openclaw-you/secrets/telegram.session")

async def main():
    client = TelegramClient(session, api_id, api_hash)
    await client.start()          # prompts phone + code interactively
    me = await client.get_me()
    print(f"✓ Authorized as: {me.first_name} (@{me.username}), id={me.id}")
    print(f"✓ Session saved to: {session}")
    await client.disconnect()

asyncio.run(main())
PYEOF
