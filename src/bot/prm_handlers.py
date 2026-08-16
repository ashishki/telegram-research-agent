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
    contract = _mapping(payload.get("archive_contract"))
    summary = _mapping(contract.get("result_summary"))
    direct_count = int(summary.get("direct_count") or 0)
    partial_count = int(summary.get("partial_count") or 0)
    bundle = build_post_answer_actions(
        {
            "query": payload.get("question"),
            "direct_answer": payload.get("direct_answer"),
            "source_refs": source_refs,
            "project_name": project.get("project_name"),
            "answer_status": professional.get("answer_status") or contract.get("answer_status"),
            "source_count": len(source_refs),
            "direct_count": direct_count,
            "partial_count": partial_count,
            "relevance_established": direct_count + partial_count > 0,
            "primary_intent": payload.get("primary_intent"),
            "response_contract_id": payload.get("response_contract_id"),
            "selected_professional_lens": professional.get("professional_lens"),
            "primary_workflow": professional.get("primary_workflow"),
            "professional_answer": professional,
            "archive_evidence": archive,
            "retrieval_policy": _mapping(payload.get("retrieval_policy")),
            "evidence_quality": _mapping(payload.get("evidence_quality")),
            "claim_ledger": _mapping(payload.get("claim_ledger")),
            "receipt": _mapping(payload.get("receipt")),
            "privacy": _mapping(payload.get("privacy")),
            "route_decision": _mapping(payload.get("route_decision")),
            "archive_contract": contract,
            "render_mode": "telegram_archive_contract_v2" if contract else "telegram_legacy",
        },
        db_path=settings.db_path,
        chat_id=chat_id,
    )
    return bundle.get("reply_markup") if isinstance(bundle, Mapping) else None


def _send_chunks(chat_id: str, text: str, *, reply_markup: dict | None, limit: int = 3400) -> None:
    chunks = _split_telegram_text(text, limit=limit)
    for index, chunk in enumerate(chunks):
        send_message(_token(), chat_id, chunk, reply_markup=reply_markup if index == len(chunks) - 1 else None)


def _split_telegram_text(text: str, *, limit: int = 3400) -> list[str]:
    clean = str(text or "").strip()
    if not clean:
        return [""]
    chunks: list[str] = []
    current = ""
    for paragraph in clean.split("\n\n"):
        pieces = _bounded_pieces(paragraph, limit=limit)
        for piece in pieces:
            candidate = piece if not current else f"{current}\n\n{piece}"
            if len(candidate) <= limit:
                current = candidate
                continue
            if current:
                chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks or [clean[:limit]]


def _bounded_pieces(paragraph: str, *, limit: int) -> list[str]:
    if len(paragraph) <= limit:
        return [paragraph]
    lines = paragraph.splitlines() or [paragraph]
    result: list[str] = []
    current = ""
    for line in lines:
        if len(line) > limit:
            if current:
                result.append(current)
                current = ""
            result.extend(line[index : index + limit] for index in range(0, len(line), limit))
            continue
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= limit:
            current = candidate
        else:
            result.append(current)
            current = line
    if current:
        result.append(current)
    return result


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
        "Я ищу по твоему Telegram-архиву и сначала отвечаю на сам вопрос.\n\n"
        "Прямые совпадения, частичные и смежные материалы показываются отдельно. "
        "Проектная привязка и внешняя проверка включаются только когда ты их явно просишь.\n\n"
        "Примеры:\n"
        "• Что в архиве есть про agent evals?\n"
        "• Что из найденного применимо сейчас?\n"
        "• Как это связано с Eval-Ground-Truth-Lab?\n"
        "• Что сейчас известно про внешний benchmark?\n\n"
        "После релевантного ответа можно показать ещё, уточнить поиск или сохранить заметку."
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
