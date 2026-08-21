"""Telegram polling adapter for active PRM and explicit legacy runtimes."""

from __future__ import annotations

from importlib import import_module
import json
import logging
import os
import signal
from typing import Any
from urllib import parse, request

from config.settings import Settings
from .callbacks import handle_prm_post_answer_callback, record_callback
from .prm_handlers import dispatch_prm_command, send_message
from .runtime import BOT_RUNTIME_LEGACY, BOT_RUNTIME_PRM_ASSISTANT, normalize_bot_runtime_mode
from .voice import VoiceTranscriptionUnavailable, transcribe_telegram_voice

LOGGER = logging.getLogger(__name__)
BOT_API_BASE = "https://api.telegram.org"


class _BotState:
    def __init__(self) -> None:
        self.stop_requested = False


def _load_bot_env() -> tuple[str, str]:
    return (
        os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip(),
    )


def _install_signal_handlers(state: _BotState) -> None:
    def stop(signame: str) -> None:
        LOGGER.info("%s received; stopping after current poll cycle", signame)
        state.stop_requested = True

    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop("SIGTERM"))
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop("SIGINT"))


def _telegram_get_updates(token: str, offset: int | None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {
        "timeout": 30,
        "allowed_updates": json.dumps(["message", "edited_message", "callback_query"]),
    }
    if offset is not None:
        query["offset"] = offset
    url = f"{BOT_API_BASE}/bot{token}/getUpdates?{parse.urlencode(query)}"
    with request.urlopen(url, timeout=35) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not decoded.get("ok"):
        raise RuntimeError(f"Telegram API returned error: {decoded!r}")
    return list(decoded.get("result") or [])


def _telegram_answer_callback(token: str, callback_query_id: str, text: str) -> None:
    payload = parse.urlencode(
        {"callback_query_id": callback_query_id, "text": text[:200], "show_alert": "false"}
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
    return update.get("message") or update.get("edited_message")


def _is_authorized_message(message: dict[str, Any], owner_chat_id: str) -> bool:
    chat_id = str((message.get("chat") or {}).get("id", ""))
    from_id = str((message.get("from") or {}).get("id", ""))
    return owner_chat_id in {chat_id, from_id}


def _is_authorized_callback(callback_query: dict[str, Any], owner_chat_id: str) -> bool:
    from_id = str((callback_query.get("from") or {}).get("id", ""))
    chat_id = str((((callback_query.get("message") or {}).get("chat") or {}).get("id", "")))
    return owner_chat_id in {from_id, chat_id}


def dispatch_command(
    chat_id: str,
    text: str,
    settings: Settings,
    *,
    runtime_mode: str = BOT_RUNTIME_LEGACY,
) -> None:
    """Stable patch point and explicit compatibility dispatcher."""

    mode = normalize_bot_runtime_mode(runtime_mode)
    if mode == BOT_RUNTIME_PRM_ASSISTANT:
        dispatch_prm_command(chat_id, text, settings)
        return
    legacy = import_module("bot.legacy_handlers")
    legacy.dispatch_command(chat_id=chat_id, text=text, settings=settings, runtime_mode=BOT_RUNTIME_LEGACY)


def _operator_text_command(text: str, *, runtime_mode: str) -> str:
    return f"/auto {text}" if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT else f"/message {text}"


def _voice_text_command(text: str, *, runtime_mode: str) -> str:
    return f"/auto_voice {text}" if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT else f"/voice {text}"


def _voice_received_message(runtime_mode: str) -> str:
    if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT:
        return "Принял голосовое. Распознаю и передам как вопрос в PRM assistant."
    return "Принял голосовое. Распознаю и определю тип сообщения."


def _voice_unavailable_message(runtime_mode: str) -> str:
    if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT:
        return (
            "Голосовое распознавание недоступно: OPENAI_API_KEY не настроен. "
            "Отправь обычное текстовое сообщение."
        )
    return (
        "Голосовое распознавание недоступно: OPENAI_API_KEY не настроен. "
        "Отправь сообщение текстом или используй /feedback <фидбек>."
    )


def _voice_failed_message(runtime_mode: str) -> str:
    if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT:
        return "Не смог распознать голосовое. Отправь обычное текстовое сообщение."
    return "Не смог распознать голосовое. Отправь сообщение текстом."


def run_bot(settings: Settings, *, runtime_mode: str = BOT_RUNTIME_LEGACY) -> None:
    runtime_mode = normalize_bot_runtime_mode(runtime_mode)
    token, owner_chat_id = _load_bot_env()
    if not token or not owner_chat_id:
        LOGGER.error("Bot startup failed: TELEGRAM_BOT_TOKEN or TELEGRAM_OWNER_CHAT_ID is missing")
        return

    state = _BotState()
    _install_signal_handlers(state)
    offset: int | None = None
    LOGGER.info("Telegram polling started owner_chat_id=%s runtime_mode=%s", owner_chat_id, runtime_mode)

    while True:
        try:
            updates = _telegram_get_updates(token=token, offset=offset)
        except Exception:
            LOGGER.warning("Telegram getUpdates failed", exc_info=True)
            if state.stop_requested:
                break
            continue

        for update in updates:
            offset = int(update.get("update_id", 0)) + 1
            callback = update.get("callback_query")
            if callback is not None:
                _handle_callback(callback, token=token, owner_chat_id=owner_chat_id, settings=settings, runtime_mode=runtime_mode)
                continue

            message = _extract_message(update)
            if message is None or not _is_authorized_message(message, owner_chat_id):
                continue
            chat_id = str((message.get("chat") or {}).get("id", owner_chat_id))
            text = str(message.get("text") or "").strip()
            if text:
                command = text if text.startswith("/") else _operator_text_command(text, runtime_mode=runtime_mode)
                if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT:
                    dispatch_command(chat_id=chat_id, text=command, settings=settings, runtime_mode=runtime_mode)
                else:
                    dispatch_command(chat_id=chat_id, text=command, settings=settings)
                continue

            transcript = _embedded_voice_transcript(message)
            if transcript:
                command = _voice_text_command(transcript, runtime_mode=runtime_mode)
                if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT:
                    dispatch_command(chat_id=chat_id, text=command, settings=settings, runtime_mode=runtime_mode)
                else:
                    dispatch_command(chat_id=chat_id, text=command, settings=settings)
                continue
            if not message.get("voice"):
                continue

            send_message(token, chat_id, _voice_received_message(runtime_mode))
            try:
                transcript = transcribe_telegram_voice(
                    token=token,
                    file_id=str((message.get("voice") or {}).get("file_id") or ""),
                )
            except VoiceTranscriptionUnavailable:
                send_message(token, chat_id, _voice_unavailable_message(runtime_mode))
                continue
            except Exception:
                LOGGER.warning("Voice transcription failed chat_id=%s", chat_id, exc_info=True)
                send_message(token, chat_id, _voice_failed_message(runtime_mode))
                continue
            command = _voice_text_command(transcript, runtime_mode=runtime_mode)
            if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT:
                dispatch_command(chat_id=chat_id, text=command, settings=settings, runtime_mode=runtime_mode)
            else:
                dispatch_command(chat_id=chat_id, text=command, settings=settings)

        if state.stop_requested:
            break

    LOGGER.info("Telegram polling stopped runtime_mode=%s", runtime_mode)


def _handle_callback(callback: dict[str, Any], *, token: str, owner_chat_id: str, settings: Settings, runtime_mode: str) -> None:
    callback_id = str(callback.get("id") or "")
    if not _is_authorized_callback(callback, owner_chat_id):
        if callback_id:
            _telegram_answer_callback(token, callback_id, "Not authorized")
        return
    data = str(callback.get("data") or "")
    answer = "Готово"
    callback_acknowledged = False
    if callback_id and runtime_mode == BOT_RUNTIME_PRM_ASSISTANT:
        try:
            _telegram_answer_callback(token, callback_id, "Принято")
            callback_acknowledged = True
        except Exception:
            LOGGER.warning("Failed to answer callback query id=%s", callback_id, exc_info=True)
    try:
        if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT:
            if not data.startswith(("prma:", "prmc:")):
                answer = "PRM safe mode: legacy callbacks are disabled."
            else:
                chat_id = str((((callback.get("message") or {}).get("chat") or {}).get("id") or owner_chat_id))
                result = handle_prm_post_answer_callback(settings, data, chat_id=chat_id)
                message = str(result.get("message") or "")
                if message:
                    send_message(token, chat_id, message, parse_mode=None, reply_markup=result.get("reply_markup"))
        else:
            answer = record_callback(settings, data)
    except Exception:
        LOGGER.warning("Callback handling failed data=%s", data, exc_info=True)
        answer = "Не смог обработать действие"
    if callback_id and not callback_acknowledged:
        try:
            _telegram_answer_callback(token, callback_id, answer)
        except Exception:
            LOGGER.warning("Failed to answer callback query id=%s", callback_id, exc_info=True)


def _embedded_voice_transcript(message: dict[str, Any]) -> str:
    voice = message.get("voice") or {}
    for value in (
        message.get("caption"),
        message.get("transcript"),
        message.get("voice_transcript"),
        voice.get("transcript"),
        voice.get("transcription"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""
