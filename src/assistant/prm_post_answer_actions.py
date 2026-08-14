"""Volatile, confirmation-gated Telegram actions for PRM research answers."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from assistant.pi_memory import build_memory_proposal, confirm_memory_proposal
from db.prm19_dogfood_receipts import record_feedback_transition, record_interaction_receipt


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
_PROPOSAL_TTL = timedelta(minutes=30)


def build_post_answer_actions(answer: Mapping[str, Any], *, db_path: str | Path | None = None, chat_id: str = "") -> dict[str, Any]:
    """Register a bounded answer context and return only relevant safe actions."""

    context_id = _register_context(answer, db_path=db_path, chat_id=chat_id)
    if context_id is None:
        return {"context_id": None, "reply_markup": None}
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


def handle_post_answer_callback(db_path: str, callback_data: str, *, chat_id: str) -> dict[str, Any]:
    """Draft or confirm a proposal. No callback is a write unless it is `prmc`."""

    prefix, context_id, action = _parse_callback(callback_data)
    context = _load_context(db_path, context_id, chat_id)
    if context is None:
        return {"status": "expired", "write_performed": False, "message": "Действие устарело. Запроси ответ заново."}
    if prefix == PRM_ACTION_PREFIX:
        proposal_type, label = _ACTION_TYPES[action]
        if proposal_type == "feedback":
            try:
                record_feedback_transition(db_path, interaction_id=context_id, action_code=action)
            except sqlite3.Error:
                # Feedback receipt failure must not discard the answer/action path.
                pass
        proposal_result = context["proposals"].get(action)
        if not isinstance(proposal_result, Mapping):
            proposal_result = build_memory_proposal(proposal_type, _proposal_args(context, action))
            context["proposals"][action] = proposal_result
            _save_proposals(db_path, context_id, context["proposals"])
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
        _mark_confirmed(db_path, context_id)
        return {
            **result,
            "message": "Сохранено. Запись можно использовать в следующих исследованиях.",
        }
    return result


def _register_context(answer: Mapping[str, Any], *, db_path: str | Path | None, chat_id: str) -> str | None:
    if db_path is None or not chat_id or not Path(db_path).exists():
        return None
    context_id = secrets.token_hex(5)
    context = {
        "title": _bounded_text(answer.get("title") or "PRM research"),
        "body": _bounded_text(answer.get("body") or answer.get("direct_answer") or ""),
        "source_refs": [str(ref) for ref in answer.get("source_refs") or [] if str(ref).startswith("https://")][:5],
        "project_name": _bounded_text(answer.get("project_name") or ""),
        "proposals": {},
    }
    now = datetime.now(timezone.utc)
    try:
        with sqlite3.connect(db_path) as connection:
            connection.execute("INSERT INTO prm_post_answer_proposals(context_id, chat_id_hash, summary_json, created_at, expires_at) VALUES (?, ?, ?, ?, ?)", (context_id, _chat_hash(chat_id), json.dumps({k: v for k, v in context.items() if k != "proposals"}, ensure_ascii=False), _iso(now), _iso(now + _PROPOSAL_TTL)))
    except sqlite3.Error:
        return None
    try:
        record_interaction_receipt(
            db_path,
            interaction_id=context_id,
            chat_id_hash=_chat_hash(chat_id),
            answer=_receipt_metadata(answer),
        )
    except (sqlite3.Error, ValueError):
        _mark_receipt_status(db_path, context_id, "failed")
    else:
        _mark_receipt_status(db_path, context_id, "recorded")
    return context_id


def _load_context(db_path: str | Path, context_id: str, chat_id: str) -> dict[str, Any] | None:
    if not chat_id:
        return None
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute("SELECT chat_id_hash, summary_json, proposals_json, expires_at, status FROM prm_post_answer_proposals WHERE context_id = ?", (context_id,)).fetchone()
    except sqlite3.Error:
        return None
    if row is None or row[0] != _chat_hash(chat_id) or row[4] == "cancelled" or datetime.fromisoformat(str(row[3]).replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        return None
    context = json.loads(str(row[1])); context["proposals"] = json.loads(str(row[2])); return context


def _save_proposals(db_path: str | Path, context_id: str, proposals: Mapping[str, Any]) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE prm_post_answer_proposals SET proposals_json = ?, status = 'pending' WHERE context_id = ?", (json.dumps(proposals, ensure_ascii=False, sort_keys=True), context_id))


def _mark_confirmed(db_path: str | Path, context_id: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE prm_post_answer_proposals SET status = 'confirmed' WHERE context_id = ?", (context_id,))


def _chat_hash(chat_id: str) -> str:
    return hashlib.sha256(f"prm.post-answer.v1:{chat_id}".encode()).hexdigest()


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


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


def _receipt_metadata(answer: Mapping[str, Any]) -> dict[str, Any]:
    """Select non-content answer metadata for the private interaction ledger."""

    professional = answer.get("professional_answer") if isinstance(answer.get("professional_answer"), Mapping) else {}
    return {
        "input_kind": answer.get("input_kind"),
        "answer_status": answer.get("answer_status"),
        "source_count": answer.get("source_count", 0),
        "evidence_classes": answer.get("evidence_classes", []),
        "external_verification_status": answer.get("external_verification_status"),
        "selected_professional_lens": answer.get("selected_professional_lens"),
        "selected_project": answer.get("project_name"),
        "primary_workflow": answer.get("primary_workflow"),
        "professional_answer": professional,
    }


def _mark_receipt_status(db_path: str | Path, context_id: str, status: str) -> None:
    """Keep MAT-6 proposal callbacks usable before the approved MAT-7 migration."""

    try:
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE prm_post_answer_proposals SET receipt_status = ? WHERE context_id = ?",
                (status, context_id),
            )
    except sqlite3.Error:
        pass
