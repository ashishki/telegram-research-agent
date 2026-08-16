"""Focused active Telegram command surface for the PRM assistant."""

from __future__ import annotations

import logging
import os
from typing import Any, Mapping

from assistant.prm_post_answer_actions import build_post_answer_actions
from bot.telegram_delivery import _send_text_internal
from config.settings import Settings
from prm.application import PersonalResearchAssistant
from prm.contracts import OperatorRequest

LOGGER = logging.getLogger(__name__)
PRM_SAFE_COMMANDS = frozenset({"/start", "/help", "/auto", "/auto_voice", "/research", "/brief", "/chat", "/status", "/refresh", "/reactions"})


def send_message(token: str, chat_id: str, text: str, parse_mode: str | None = None, escape_markdown: bool = False, reply_markup: dict | None = None) -> None:
    del escape_markdown
    try:
        kwargs: dict[str, object] = {"chat_id": chat_id, "text": text, "token": token, "parse_mode": parse_mode}
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        _send_text_internal(**kwargs)
    except Exception:
        LOGGER.warning("Failed to send PRM Telegram message chat_id=%s", chat_id, exc_info=True)


def dispatch_prm_command(chat_id: str, text: str, settings: Settings) -> None:
    command, args = _split_command(text)
    if command not in PRM_SAFE_COMMANDS:
        send_message(_token(), chat_id, "Эта команда не входит в активный PRM-интерфейс. Используй обычный вопрос или /help.")
        return
    if command in {"/start", "/help"}:
        send_message(_token(), chat_id, _help_text())
        return
    if command in {"/status", "/refresh", "/reactions"}:
        _delegate_safe_ops(command, chat_id, args, settings)
        return
    mode = {"/research": "research", "/brief": "brief", "/chat": "chat"}.get(command, "auto")
    input_kind = "voice_transcript" if command == "/auto_voice" else "text"
    if not args:
        send_message(_token(), chat_id, "Напиши вопрос после команды или просто отправь обычное сообщение.")
        return
    assistant = PersonalResearchAssistant(settings=settings)
    try:
        result = assistant.answer(OperatorRequest(query=args, mode=mode, chat_id=chat_id, input_kind=input_kind))  # type: ignore[arg-type]
    except Exception as exc:
        LOGGER.warning("PRM request failed command=%s", command, exc_info=True)
        send_message(_token(), chat_id, f"Не смог обработать запрос: {type(exc).__name__}")
        return
    markup = _post_answer_markup(result.payload, settings=settings, chat_id=chat_id)
    _send_chunks(chat_id, result.text, reply_markup=markup)


def _delegate_safe_ops(command: str, chat_id: str, args: str, settings: Settings) -> None:
    from bot import legacy_handlers

    handler_name = {"/status": "handle_status", "/refresh": "handle_refresh", "/reactions": "handle_reactions"}[command]
    handler = getattr(legacy_handlers, handler_name, None)
    if handler is None:
        send_message(_token(), chat_id, "Операционная команда пока недоступна в текущей сборке.")
        return
    handler(chat_id, args, settings)


def _post_answer_markup(payload: Mapping[str, Any], *, settings: Settings, chat_id: str) -> dict | None:
    gate = _mapping(payload.get("answer_gate"))
    if not bool(gate.get("allow_answer", True)):
        return None
    archive = _mapping(payload.get("archive_evidence"))
    source_refs = [
        str(item.get("source_url") or item.get("telegram_url") or "")
        for item in archive.get("items") or []
        if isinstance(item, Mapping)
    ]
    professional = _mapping(payload.get("professional_answer"))
    project = _mapping(payload.get("project_fit"))
    bundle = build_post_answer_actions(
        {
            "direct_answer": payload.get("direct_answer"),
            "source_refs": source_refs,
            "project_name": project.get("project_name"),
            "answer_status": professional.get("answer_status"),
            "source_count": len(source_refs),
            "selected_professional_lens": professional.get("professional_lens"),
            "primary_workflow": professional.get("primary_workflow"),
            "professional_answer": professional,
            "archive_evidence": archive,
            "retrieval_policy": _mapping(payload.get("retrieval_policy")),
            "evidence_quality": _mapping(payload.get("evidence_quality")),
            "claim_ledger": _mapping(payload.get("claim_ledger")),
            "receipt": _mapping(payload.get("receipt")),
            "privacy": _mapping(payload.get("privacy")),
        },
        db_path=settings.db_path,
        chat_id=chat_id,
    )
    return bundle.get("reply_markup") if isinstance(bundle, Mapping) else None


def _send_chunks(chat_id: str, text: str, *, reply_markup: dict | None, limit: int = 3900) -> None:
    chunks = []
    current = ""
    for paragraph in str(text or "").split("\n\n"):
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = paragraph
    if current or not chunks:
        chunks.append(current)
    for index, chunk in enumerate(chunks):
        send_message(_token(), chat_id, chunk, reply_markup=reply_markup if index == len(chunks) - 1 else None)


def _split_command(text: str) -> tuple[str, str]:
    clean = str(text or "").strip()
    if not clean.startswith("/"):
        return "/auto", clean
    parts = clean.split(maxsplit=1)
    command = parts[0].split("@", 1)[0].casefold()
    return command, parts[1].strip() if len(parts) > 1 else ""


def _token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _help_text() -> str:
    return (
        "Я ищу по твоему Telegram-архиву и отвечаю со ссылками.\n\n"
        "Просто напиши вопрос или отправь голосовое.\n\n"
        "Примеры:\n"
        "• Что писали про agent evals?\n"
        "• Что применить к telegram-research-agent?\n"
        "• Собери бриф для поста.\n"
        "• Что я отмечал реакциями?\n\n"
        "После ответа можно сохранить заметку, следить за темой или оценить полезность."
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
