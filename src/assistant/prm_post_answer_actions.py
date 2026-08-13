"""Volatile, confirmation-gated Telegram actions for PRM research answers."""

from __future__ import annotations

import secrets
from typing import Any, Mapping

from assistant.pi_memory import build_memory_proposal, confirm_memory_proposal


PRM_ACTION_PREFIX = "prma"
PRM_CONFIRM_PREFIX = "prmc"
_ACTION_TYPES = {
    "n": ("knowledge_note", "Сохранить заметку"),
    "w": ("watch_topic", "Следить"),
    "p": ("project_link", "Связать с проектом"),
    "a": ("action", "Создать действие"),
    "e": ("experiment", "Создать эксперимент"),
    "u": ("feedback", "Отметить полезным"),
    "r": ("feedback", "Не тот приоритет"),
    "s": ("feedback", "Слишком поверхностно"),
    "d": ("feedback", "Применил"),
}
_CONTEXTS: dict[str, dict[str, Any]] = {}
_MAX_CONTEXTS = 100


def build_post_answer_actions(answer: Mapping[str, Any]) -> dict[str, Any]:
    """Register a bounded answer context and return only relevant safe actions."""

    context_id = _register_context(answer)
    action_codes = ["n", "w", "u", "r", "s"]
    if str(answer.get("project_name") or "").strip():
        action_codes.extend(["p", "a", "e"])
    rows: list[list[dict[str, str]]] = []
    for index in range(0, len(action_codes), 3):
        row = []
        for code in action_codes[index : index + 3]:
            _proposal_type, label = _ACTION_TYPES[code]
            callback_data = f"{PRM_ACTION_PREFIX}:{context_id}:{code}"
            row.append({"text": label, "callback_data": callback_data})
        rows.append(row)
    return {"context_id": context_id, "reply_markup": {"inline_keyboard": rows}}


def handle_post_answer_callback(db_path: str, callback_data: str) -> dict[str, Any]:
    """Draft or confirm a proposal. No callback is a write unless it is `prmc`."""

    prefix, context_id, action = _parse_callback(callback_data)
    context = _CONTEXTS.get(context_id)
    if context is None:
        return {"status": "expired", "write_performed": False, "message": "Действие устарело. Запроси ответ заново."}
    if prefix == PRM_ACTION_PREFIX:
        proposal_type, label = _ACTION_TYPES[action]
        proposal_result = build_memory_proposal(proposal_type, _proposal_args(context, action))
        context["proposals"][action] = proposal_result
        confirm_data = f"{PRM_CONFIRM_PREFIX}:{context_id}:{action}"
        return {
            "status": "needs_confirmation",
            "write_performed": False,
            "proposal": proposal_result["proposal"],
            "message": f"{label}: черновик подготовлен. Подтверди сохранение.",
            "reply_markup": {"inline_keyboard": [[{"text": "Подтвердить", "callback_data": confirm_data}]]},
        }
    proposal_result = context["proposals"].get(action)
    if not isinstance(proposal_result, Mapping):
        return {"status": "missing_proposal", "write_performed": False, "message": "Сначала выбери действие ещё раз."}
    result = confirm_memory_proposal(
        db_path,
        {
            "proposal": proposal_result["proposal"],
            "confirmation_token": proposal_result["confirmation"]["token"],
            "confirmed_by": "telegram_operator",
        },
    )
    if result.get("persisted"):
        _CONTEXTS.pop(context_id, None)
        return {
            **result,
            "message": f"Сохранено. Найти запись: memory_id={result.get('memory_id')}; event_id={result.get('event_id')}.",
        }
    return result


def _register_context(answer: Mapping[str, Any]) -> str:
    if len(_CONTEXTS) >= _MAX_CONTEXTS:
        _CONTEXTS.pop(next(iter(_CONTEXTS)))
    context_id = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:10]
    _CONTEXTS[context_id] = {
        "title": _bounded_text(answer.get("title") or answer.get("question") or "PRM research"),
        "body": _bounded_text(answer.get("body") or answer.get("direct_answer") or ""),
        "source_refs": [str(ref) for ref in answer.get("source_refs") or [] if str(ref).startswith("https://")][:5],
        "project_name": _bounded_text(answer.get("project_name") or ""),
        "proposals": {},
    }
    return context_id


def _proposal_args(context: Mapping[str, Any], action: str) -> dict[str, Any]:
    title = str(context["title"])
    feedback_titles = {"u": "Полезно", "r": "Не тот приоритет", "s": "Слишком поверхностно", "d": "Применил"}
    if action in feedback_titles:
        return {
            "title": feedback_titles[action],
            "body": title,
            "rationale": "Операторская оценка PRM-ответа.",
            "source_refs": context["source_refs"],
            "metadata": {"feedback_type": action},
        }
    names = {"n": "Заметка", "w": "Наблюдать", "p": "Связь с проектом", "a": "Действие", "e": "Эксперимент"}
    return {
        "title": f"{names[action]}: {title}",
        "body": str(context["body"]),
        "rationale": "Черновик из локального PRM-ответа; сохранение требует подтверждения.",
        "source_refs": context["source_refs"],
        "metadata": {"project_name": context["project_name"]} if context["project_name"] else {},
    }


def _parse_callback(callback_data: str) -> tuple[str, str, str]:
    parts = str(callback_data or "").split(":")
    if len(parts) != 3 or parts[0] not in {PRM_ACTION_PREFIX, PRM_CONFIRM_PREFIX} or parts[2] not in _ACTION_TYPES:
        raise ValueError("Unsupported PRM post-answer callback")
    if not parts[1] or len(callback_data) > 64:
        raise ValueError("Invalid PRM post-answer callback")
    return parts[0], parts[1], parts[2]


def _bounded_text(value: object, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]
