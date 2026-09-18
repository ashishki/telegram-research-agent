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
from assistant.prm_post_answer_actions import UnavailablePrmAction
from .callbacks import (
    apply_validated_prm_post_answer_callback,
    handle_prm_post_answer_callback,
    record_callback,
    validate_prm_post_answer_callback,
)
from .prm_handlers import (
    consume_private_reply_authorization,
    dispatch_prm_command,
    issue_private_reply_authorizations,
    send_message,
)
from prm.capabilities import AuthorizationDecision
from .runtime import (
    BOT_RUNTIME_LEGACY,
    BOT_RUNTIME_PRM_ASSISTANT,
    normalize_bot_runtime_mode,
)
from .voice import VoiceTranscriptionUnavailable, transcribe_telegram_voice

LOGGER = logging.getLogger(__name__)
BOT_API_BASE = "https://api.telegram.org"
_PRM_CALLBACK_PREFIXES = ("prma:", "prmc:", "utdp:", "utdc:", "utdw:", "utds:")


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


def _answer_prm_callback(
    token: str,
    callback_query_id: str,
    text: str,
    *,
    delivery_authorization: AuthorizationDecision | None,
    chat_id: str,
    actor_id: str | None,
    owner_chat_id: str | None,
) -> bool:
    """Acknowledge a PA callback only through its inbound reply envelope."""

    if not consume_private_reply_authorization(
        token=token,
        chat_id=chat_id,
        authorization=delivery_authorization,
        actor_id=actor_id,
        owner_chat_id=owner_chat_id,
    ):
        return False
    try:
        _telegram_answer_callback(token, callback_query_id, text)
    except Exception:
        LOGGER.warning("Failed to acknowledge PRM callback")
        return False
    return True


def _extract_message(update: dict[str, Any]) -> dict[str, Any] | None:
    return update.get("message") or update.get("edited_message")


def _is_authorized_message(message: dict[str, Any], owner_chat_id: str) -> bool:
    chat_id = str((message.get("chat") or {}).get("id", ""))
    from_id = str((message.get("from") or {}).get("id", ""))
    return owner_chat_id in {chat_id, from_id}


def _is_authorized_callback(callback_query: dict[str, Any], owner_chat_id: str) -> bool:
    from_id = str((callback_query.get("from") or {}).get("id", ""))
    chat_id = str(
        (((callback_query.get("message") or {}).get("chat") or {}).get("id", ""))
    )
    return owner_chat_id in {from_id, chat_id}


def dispatch_command(
    chat_id: str,
    text: str,
    settings: Settings,
    *,
    runtime_mode: str = BOT_RUNTIME_LEGACY,
    actor_id: str | None = None,
    owner_chat_id: str | None = None,
    delivery_authorizations: tuple[AuthorizationDecision, ...] = (),
    utd_draft_authorization: AuthorizationDecision | None = None,
) -> None:
    """Stable patch point and explicit compatibility dispatcher."""

    mode = normalize_bot_runtime_mode(runtime_mode)
    if mode == BOT_RUNTIME_PRM_ASSISTANT:
        prm_kwargs: dict[str, object] = {
            "actor_id": actor_id,
            "owner_chat_id": owner_chat_id,
        }
        if delivery_authorizations:
            prm_kwargs["delivery_authorizations"] = delivery_authorizations
        if utd_draft_authorization is not None:
            prm_kwargs["utd_draft_authorization"] = utd_draft_authorization
        dispatch_prm_command(chat_id, text, settings, **prm_kwargs)
        return
    legacy = import_module("bot.legacy_handlers")
    legacy.dispatch_command(
        chat_id=chat_id,
        text=text,
        settings=settings,
        runtime_mode=BOT_RUNTIME_LEGACY,
    )


def _operator_text_command(text: str, *, runtime_mode: str) -> str:
    return (
        f"/auto {text}"
        if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT
        else f"/message {text}"
    )


def _voice_text_command(text: str, *, runtime_mode: str) -> str:
    return (
        f"/auto_voice {text}"
        if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT
        else f"/voice {text}"
    )


def _voice_received_message(runtime_mode: str) -> str:
    if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT:
        return "Принял голосовое. Распознаю и передам как вопрос в PRM assistant."
    return "Принял голосовое. Распознаю и определю тип сообщения."


def _voice_unavailable_message(runtime_mode: str) -> str:
    if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT:
        return (
            "Голосовое распознавание недоступно по текущей политике доступа. "
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
        LOGGER.error(
            "Bot startup failed: TELEGRAM_BOT_TOKEN or TELEGRAM_OWNER_CHAT_ID is missing"
        )
        return

    state = _BotState()
    _install_signal_handlers(state)
    offset: int | None = None
    LOGGER.info(
        "Telegram polling started owner_chat_id=%s runtime_mode=%s",
        owner_chat_id,
        runtime_mode,
    )

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
                _handle_callback(
                    callback,
                    token=token,
                    owner_chat_id=owner_chat_id,
                    settings=settings,
                    runtime_mode=runtime_mode,
                )
                continue

            message = _extract_message(update)
            if message is None or not _is_authorized_message(message, owner_chat_id):
                continue
            chat_id = str((message.get("chat") or {}).get("id", owner_chat_id))
            actor_id = str((message.get("from") or {}).get("id") or "")
            # PRM answers can contain private archive excerpts.  Sender-based
            # owner authorization is retained for legacy operations, but the
            # PRM surface is deliberately private-chat-only.
            if (
                runtime_mode == BOT_RUNTIME_PRM_ASSISTANT
                and (chat_id != owner_chat_id or actor_id != owner_chat_id)
            ):
                continue
            delivery_authorizations = (
                issue_private_reply_authorizations(
                    token=token,
                    chat_id=chat_id,
                    actor_id=actor_id,
                    owner_chat_id=owner_chat_id,
                )
                if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT
                else ()
            )
            text = str(message.get("text") or "").strip()
            if text:
                command = (
                    text
                    if text.startswith("/")
                    else _operator_text_command(text, runtime_mode=runtime_mode)
                )
                if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT:
                    dispatch_command(
                        chat_id=chat_id,
                        text=command,
                        settings=settings,
                        runtime_mode=runtime_mode,
                        actor_id=actor_id,
                        owner_chat_id=owner_chat_id,
                        delivery_authorizations=delivery_authorizations,
                    )
                else:
                    dispatch_command(chat_id=chat_id, text=command, settings=settings)
                continue

            transcript = _embedded_voice_transcript(message)
            if transcript:
                command = _voice_text_command(transcript, runtime_mode=runtime_mode)
                if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT:
                    dispatch_command(
                        chat_id=chat_id,
                        text=command,
                        settings=settings,
                        runtime_mode=runtime_mode,
                        actor_id=actor_id,
                        owner_chat_id=owner_chat_id,
                        delivery_authorizations=delivery_authorizations,
                    )
                else:
                    dispatch_command(chat_id=chat_id, text=command, settings=settings)
                continue
            if not message.get("voice"):
                continue

            send_message(
                token,
                chat_id,
                _voice_received_message(runtime_mode),
                delivery_authorization=delivery_authorizations[0] if delivery_authorizations else None,
                actor_id=actor_id,
                owner_chat_id=owner_chat_id,
            )
            try:
                transcript = transcribe_telegram_voice(
                    token=token,
                    file_id=str((message.get("voice") or {}).get("file_id") or ""),
                )
            except VoiceTranscriptionUnavailable:
                send_message(
                    token,
                    chat_id,
                    _voice_unavailable_message(runtime_mode),
                    delivery_authorization=delivery_authorizations[1] if len(delivery_authorizations) > 1 else None,
                    actor_id=actor_id,
                    owner_chat_id=owner_chat_id,
                )
                continue
            except Exception:
                LOGGER.warning("Voice transcription failed chat_id=%s", chat_id, exc_info=True)
                send_message(
                    token,
                    chat_id,
                    _voice_failed_message(runtime_mode),
                    delivery_authorization=delivery_authorizations[1] if len(delivery_authorizations) > 1 else None,
                    actor_id=actor_id,
                    owner_chat_id=owner_chat_id,
                )
                continue
            command = _voice_text_command(transcript, runtime_mode=runtime_mode)
            if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT:
                dispatch_command(
                    chat_id=chat_id,
                    text=command,
                    settings=settings,
                    runtime_mode=runtime_mode,
                    actor_id=actor_id,
                    owner_chat_id=owner_chat_id,
                    delivery_authorizations=delivery_authorizations[1:],
                )
            else:
                dispatch_command(chat_id=chat_id, text=command, settings=settings)

        if state.stop_requested:
            break

    LOGGER.info("Telegram polling stopped runtime_mode=%s", runtime_mode)


def _handle_callback(
    callback: dict[str, Any],
    *,
    token: str,
    owner_chat_id: str,
    settings: Settings,
    runtime_mode: str,
) -> None:
    callback_id = str(callback.get("id") or "")
    data = str(callback.get("data") or "")
    callback_chat_id = str((((callback.get("message") or {}).get("chat") or {}).get("id")) or "")
    callback_actor_id = str((callback.get("from") or {}).get("id") or "")
    callback_delivery_authorizations = (
        issue_private_reply_authorizations(
            token=token,
            chat_id=callback_chat_id,
            actor_id=callback_actor_id,
            owner_chat_id=owner_chat_id,
        )
        if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT
        else ()
    )

    callback_decisions = iter(callback_delivery_authorizations)

    def next_callback_decision() -> AuthorizationDecision | None:
        return next(callback_decisions, None)

    def acknowledge_callback(text: str) -> bool:
        if not callback_id:
            return False
        if runtime_mode != BOT_RUNTIME_PRM_ASSISTANT:
            _telegram_answer_callback(token, callback_id, text)
            return True
        return _answer_prm_callback(
            token,
            callback_id,
            text,
            delivery_authorization=next_callback_decision(),
            chat_id=callback_chat_id,
            actor_id=callback_actor_id,
            owner_chat_id=owner_chat_id,
        )

    if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT and data.startswith(("prma:", "prmc:")):
        validated = validate_prm_post_answer_callback(
            settings,
            data,
            chat_id=callback_chat_id,
            actor_id=str((callback.get("from") or {}).get("id") or ""),
            owner_chat_id=owner_chat_id,
        )
        if isinstance(validated, UnavailablePrmAction):
            acknowledge_callback("Action unavailable")
            return
        result = apply_validated_prm_post_answer_callback(settings, validated)
        unavailable = str(result.get("status") or "") in {
            "action_unavailable", "expired", "action_not_available", "missing_proposal",
            "invalid_selection", "selection_required",
        }
        acknowledge_callback("Action unavailable" if unavailable else "Принято")
        if not unavailable:
            message = str(result.get("message") or "")
            if message:
                send_message(
                    token,
                    callback_chat_id,
                    message,
                    parse_mode=None,
                    reply_markup=result.get("reply_markup"),
                    delivery_authorization=next_callback_decision(),
                    actor_id=callback_actor_id,
                    owner_chat_id=owner_chat_id,
                )
        return
    if not _is_authorized_callback(callback, owner_chat_id):
        acknowledge_callback("Not authorized")
        return
    if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT and callback_chat_id != owner_chat_id:
        acknowledge_callback("PRM доступен только в личном чате владельца")
        return
    if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT and data.startswith(
        ("utdp:", "utdc:", "utdw:", "utds:")
    ):
        # UTD callback namespaces mutate durable draft/profile/watch state.
        # PA-02 deliberately has no callback-specific local-write authority,
        # so do not hand the action to their legacy mutation facade.
        acknowledge_callback("Action unavailable")
        return
    english_feedback = data.startswith("utdw:") and data.endswith(":en")
    answer = "Готово"
    callback_acknowledged = False
    if (
        callback_id
        and runtime_mode == BOT_RUNTIME_PRM_ASSISTANT
        and data.startswith(_PRM_CALLBACK_PREFIXES)
        and not english_feedback
    ):
        try:
            callback_acknowledged = acknowledge_callback("Принято")
        except Exception:
            LOGGER.warning(
                "Failed to answer callback query id=%s", callback_id, exc_info=True
            )
    try:
        if runtime_mode == BOT_RUNTIME_PRM_ASSISTANT:
            if not data.startswith(_PRM_CALLBACK_PREFIXES):
                answer = "PRM safe mode: legacy callbacks are disabled."
            else:
                chat_id = callback_chat_id
                result = handle_prm_post_answer_callback(
                    settings,
                    data,
                    chat_id=chat_id,
                    actor_id=callback_actor_id,
                    owner_chat_id=owner_chat_id,
                )
                message = str(result.get("message") or "")
                if message:
                    send_message(
                        token,
                        chat_id,
                        message,
                        parse_mode=None,
                        reply_markup=result.get("reply_markup"),
                        delivery_authorization=next_callback_decision(),
                        actor_id=callback_actor_id,
                        owner_chat_id=owner_chat_id,
                    )
                if english_feedback:
                    answer = "Recorded"
        else:
            answer = record_callback(settings, data)
    except Exception:
        LOGGER.warning("Callback handling failed data=%s", data, exc_info=True)
        answer = "Could not record feedback" if english_feedback else "Не смог обработать действие"
    if callback_id and not callback_acknowledged:
        try:
            acknowledge_callback(answer)
        except Exception:
            LOGGER.warning(
                "Failed to answer callback query id=%s", callback_id, exc_info=True
            )


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
