import json
import logging
import os
import signal
from typing import Any
from urllib import parse, request

from config.settings import Settings

from .callbacks import record_idea_callback
from .handlers import dispatch_command


LOGGER = logging.getLogger(__name__)
BOT_API_BASE = "https://api.telegram.org"


class _StopPolling(Exception):
    pass


class _BotState:
    def __init__(self) -> None:
        self.stop_requested = False


def _load_bot_env() -> tuple[str, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    owner_chat_id = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
    return token, owner_chat_id


def _handle_shutdown_signal(state: _BotState, signame: str) -> None:
    LOGGER.info("%s received, bot will stop after the current poll cycle", signame)
    state.stop_requested = True


def _install_signal_handlers(state: _BotState) -> None:
    signal.signal(signal.SIGTERM, lambda _signum, _frame: _handle_shutdown_signal(state, "SIGTERM"))
    signal.signal(signal.SIGINT, lambda _signum, _frame: _handle_shutdown_signal(state, "SIGINT"))


def _telegram_get_updates(token: str, offset: int | None) -> list[dict[str, Any]]:
    query = {
        "timeout": 30,
        "allowed_updates": json.dumps(["message", "edited_message", "callback_query"]),
    }
    if offset is not None:
        query["offset"] = offset
    url = f"{BOT_API_BASE}/bot{token}/getUpdates?{parse.urlencode(query)}"
    with request.urlopen(url, timeout=35) as response:
        payload = response.read().decode("utf-8")
    decoded = json.loads(payload)
    if not decoded.get("ok"):
        raise RuntimeError(f"Telegram API returned error: {decoded!r}")
    return decoded.get("result", [])


def _telegram_answer_callback(token: str, callback_query_id: str, text: str) -> None:
    payload = parse.urlencode(
        {
            "callback_query_id": callback_query_id,
            "text": text[:200],
            "show_alert": "false",
        }
    ).encode("utf-8")
    req = request.Request(
        f"{BOT_API_BASE}/bot{token}/answerCallbackQuery",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with request.urlopen(req, timeout=15) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not decoded.get("ok"):
        raise RuntimeError(f"Telegram API returned error: {decoded!r}")


def _extract_message(update: dict[str, Any]) -> dict[str, Any] | None:
    if "message" in update:
        return update["message"]
    if "edited_message" in update:
        return update["edited_message"]
    return None


def _is_authorized_message(message: dict[str, Any], owner_chat_id: str) -> bool:
    chat = message.get("chat") or {}
    from_user = message.get("from") or {}
    chat_id = str(chat.get("id", ""))
    from_id = str(from_user.get("id", ""))
    return owner_chat_id in {chat_id, from_id}


def _is_authorized_callback(callback_query: dict[str, Any], owner_chat_id: str) -> bool:
    from_user = callback_query.get("from") or {}
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}
    from_id = str(from_user.get("id", ""))
    chat_id = str(chat.get("id", ""))
    return owner_chat_id in {from_id, chat_id}


def run_bot(settings: Settings) -> None:
    token, owner_chat_id = _load_bot_env()
    if not token or not owner_chat_id:
        LOGGER.error("Bot startup failed because TELEGRAM_BOT_TOKEN or TELEGRAM_OWNER_CHAT_ID is not set")
        return

    state = _BotState()
    _install_signal_handlers(state)

    offset: int | None = None
    LOGGER.info("Telegram bot polling started owner_chat_id=%s", owner_chat_id)

    while True:
        try:
            updates = _telegram_get_updates(token=token, offset=offset)
        except Exception:
            LOGGER.warning("Telegram getUpdates failed", exc_info=True)
            if state.stop_requested:
                break
            continue

        for update in updates:
            update_id = int(update.get("update_id", 0))
            offset = update_id + 1

            callback_query = update.get("callback_query")
            if callback_query is not None:
                callback_query_id = str(callback_query.get("id", ""))
                if not _is_authorized_callback(callback_query, owner_chat_id):
                    if callback_query_id:
                        try:
                            _telegram_answer_callback(token, callback_query_id, "Not authorized")
                        except Exception:
                            LOGGER.warning("Failed to answer unauthorized callback", exc_info=True)
                    continue
                data = str(callback_query.get("data") or "")
                try:
                    answer = record_idea_callback(settings, data)
                except Exception:
                    LOGGER.warning("Callback handling failed data=%s", data, exc_info=True)
                    answer = "Не смог записать решение"
                if callback_query_id:
                    try:
                        _telegram_answer_callback(token, callback_query_id, answer)
                    except Exception:
                        LOGGER.warning("Failed to answer callback query id=%s", callback_query_id, exc_info=True)
                continue

            message = _extract_message(update)
            if message is None:
                continue
            if not _is_authorized_message(message, owner_chat_id):
                continue

            text = (message.get("text") or "").strip()
            if not text.startswith("/"):
                continue

            chat_id = str((message.get("chat") or {}).get("id", owner_chat_id))
            LOGGER.info("Dispatching bot command chat_id=%s text=%s", chat_id, text.splitlines()[0][:200])
            dispatch_command(chat_id=chat_id, text=text, settings=settings)

        if state.stop_requested:
            break

    LOGGER.info("Telegram bot polling stopped cleanly")
