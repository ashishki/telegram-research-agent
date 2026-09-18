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
from assistant.prm_private_traces import update_private_interaction_feedback, write_private_interaction_receipt
from db.prm19_dogfood_receipts import record_feedback_transition, record_interaction_receipt

PRM_ACTION_PREFIX = "prma"
PRM_CONFIRM_PREFIX = "prmc"
_ACTION_TYPES = {
    "n": ("knowledge_note", "Сохранить заметку"),
    "w": ("watch_topic", "Следить"),
    "p": ("project_link", "Связать с проектом"),
    "a": ("action", "Создать действие"),
    "e": ("experiment", "Создать эксперимент"),
    "o": ("followup_more", "Показать ещё"),
    "q": ("followup_refine", "Уточнить поиск"),
    "u": ("feedback", "Полезно"),
    "m": ("feedback_reason_prompt", "Частично"),
    "x": ("feedback_reason_prompt", "Мимо"),
    "ws": ("feedback_reason", "Не те источники"),
    "og": ("feedback_reason", "Слишком общий ответ"),
    "wp": ("feedback_reason", "Не тот проект"),
    "na": ("feedback_reason", "Нет полезного действия"),
    "lg": ("feedback_reason", "Слишком длинно"),
    "we": ("feedback_reason", "Слабые доказательства"),
    "r": ("feedback", "Не тот приоритет"),
    "s": ("feedback", "Слишком поверхностно"),
    "d": ("feedback", "Применил"),
    "c": ("cancel", "Отменить"),
}
_CONTEXTS: dict[str, dict[str, Any]] = {}
_PROPOSAL_TTL = timedelta(minutes=30)
_CONFIRMATION_LOCK_TTL = timedelta(minutes=2)
_CONFIRMATION_LOCK_KEY = "__confirmation_lock__"

_SHORT_LABELS = {
    "u": "👍 Полезно",
    "m": "≈ Частично",
    "x": "👎 Мимо",
    "n": "Сохранить",
    "p": "К проекту",
    "a": "Сохранить действие",
    "e": "Сохранить эксперимент",
    "o": "Показать ещё",
    "q": "Уточнить поиск",
    "w": "Следить",
}


def select_post_answer_action_codes(answer: Mapping[str, Any]) -> list[str]:
    """Return context-aware actions without registering state or writing."""

    intent = str(answer.get("primary_intent") or "").strip()
    if not intent:
        codes = ["u", "m", "x", "n", "w"]
        if str(answer.get("project_name") or "").strip():
            codes.extend(["p", "a", "e"])
        return codes

    feedback = ["u", "m", "x"]
    summary = answer.get("result_summary") if isinstance(answer.get("result_summary"), Mapping) else {}
    direct_count = max(0, int(answer.get("direct_count") or summary.get("direct_count") or 0))
    partial_count = max(0, int(answer.get("partial_count") or summary.get("partial_count") or 0))
    adjacent_count = max(0, int(answer.get("adjacent_count") or summary.get("adjacent_count") or 0))
    relevance_established = bool(answer.get("relevance_established")) or direct_count + partial_count + adjacent_count > 0
    project_name = str(answer.get("project_name") or "").strip()

    if intent in {"archive_lookup", "archive_synthesis", "archive_to_action"}:
        if not relevance_established:
            return [*feedback, "q"]
        codes = [*feedback, "n", "o", "q"]
        if intent == "archive_to_action":
            codes.append("w")
        if project_name:
            codes.append("p")
        return codes
    if intent == "project_mapping":
        if not relevance_established:
            return [*feedback, "q"]
        codes = [*feedback, "n", "p"]
        if relevance_established:
            codes.append("a")
        return codes
    if intent == "decision_support":
        # A decision-support response is an explicit request to turn a
        # conclusion into a bounded next action. Confirmation still gates the
        # durable write; evidence gates elsewhere decide whether the response
        # itself can be shown.
        codes = [*feedback, "a"]
        if bool(answer.get("experiment_recommended")):
            codes.append("e")
        return codes
    if intent == "current_fact_verification":
        return [*feedback, "q"]
    if intent == "writer_brief":
        return [*feedback, "n"] if relevance_established else [*feedback, "q"]
    if intent == "memory_action":
        return [*feedback, "n"]
    return [*feedback, "n"] if relevance_established else [*feedback, "q"]


def build_post_answer_actions(answer: Mapping[str, Any], *, db_path: str | Path | None = None, chat_id: str = "") -> dict[str, Any]:
    """Register a bounded answer context and return only relevant safe actions."""

    action_codes = select_post_answer_action_codes(answer)
    traced_answer = {**dict(answer), "keyboard_action_ids": action_codes}
    context_id = _register_context(traced_answer, db_path=db_path, chat_id=chat_id)
    if context_id is None:
        return {"context_id": None, "reply_markup": None}
    intent = str(answer.get("primary_intent") or "").strip()
    row_size = 2 if intent else 3
    rows: list[list[dict[str, str]]] = []
    for index in range(0, len(action_codes), row_size):
        row = []
        for code in action_codes[index : index + row_size]:
            callback_data = f"{PRM_ACTION_PREFIX}:{context_id}:{code}"
            row.append({"text": _button_label(code, intent=intent), "callback_data": callback_data})
        rows.append(row)
    return {
        "context_id": context_id,
        "action_codes": action_codes,
        "reply_markup": {"inline_keyboard": rows},
    }


def handle_post_answer_callback(db_path: str, callback_data: str, *, chat_id: str, actor_id: str = "") -> dict[str, Any]:
    """Draft or confirm a proposal. No callback is a write unless it is `prmc`."""

    prefix, context_id, action = _parse_callback(callback_data)
    context = _load_context(db_path, context_id, chat_id, actor_id)
    if context is None:
        return {"status": "expired", "write_performed": False, "message": "Действие устарело. Запроси ответ заново."}
    if str(context.get("_status") or "") == "confirmed":
        return {"status": "already_confirmed", "write_performed": False, "message": "Этот черновик уже подтверждён; новая запись не создаётся."}
    if _confirmation_locked(context):
        if prefix != PRM_CONFIRM_PREFIX:
            return {"status": "confirmation_in_progress", "write_performed": False, "message": "Подтверждение уже выполняется; повтори проверку статуса."}
    if prefix == PRM_ACTION_PREFIX:
        if action == "c":
            if not _delete_context(db_path, context_id):
                return {"status": "confirmation_in_progress", "write_performed": False, "message": "Подтверждение уже началось; повтори запрос статуса."}
            return {"status": "cancelled", "write_performed": False, "message": "Черновик отменён. Запись не создана."}
        if not _action_allowed(context, action):
            return {"status": "action_not_available", "write_performed": False, "message": "Это действие не предлагалось для текущей версии ответа."}
        if action == "n" and len(context.get("evidence_items") or []) > 1:
            context["proposals"]["__selection_open__"] = True
            _save_proposals(db_path, context_id, context["proposals"])
            return _select_item_result(context_id, context)
        selected_index = _selected_item_index(action)
        if selected_index and selected_index > len(context.get("evidence_items") or []):
            return {"status": "invalid_selection", "write_performed": False, "message": "Этот пункт не относится к текущей версии ответа."}
        if selected_index and not context["proposals"].get("__selection_open__"):
            return {"status": "selection_required", "write_performed": False, "message": "Сначала выбери пункт через preview."}
        proposal_type, label = _ACTION_TYPES["n" if _selected_item_index(action) else action]
        if proposal_type in {"followup_more", "followup_refine"}:
            return _followup_result(context, action)
        if proposal_type == "feedback_reason_prompt":
            context["proposals"]["__reason_parent__"] = action
            _save_proposals(db_path, context_id, context["proposals"])
            try:
                record_feedback_transition(db_path, interaction_id=context_id, action_code=action)
            except sqlite3.Error:
                pass
            update_private_interaction_feedback(context_id, feedback="partial" if action == "m" else "miss")
            reason_rows = [
                [
                    {"text": _ACTION_TYPES["ws"][1], "callback_data": f"{PRM_ACTION_PREFIX}:{context_id}:ws"},
                    {"text": _ACTION_TYPES["og"][1], "callback_data": f"{PRM_ACTION_PREFIX}:{context_id}:og"},
                ],
                [
                    {"text": _ACTION_TYPES["wp"][1], "callback_data": f"{PRM_ACTION_PREFIX}:{context_id}:wp"},
                    {"text": _ACTION_TYPES["na"][1], "callback_data": f"{PRM_ACTION_PREFIX}:{context_id}:na"},
                ],
                [
                    {"text": _ACTION_TYPES["lg"][1], "callback_data": f"{PRM_ACTION_PREFIX}:{context_id}:lg"},
                    {"text": _ACTION_TYPES["we"][1], "callback_data": f"{PRM_ACTION_PREFIX}:{context_id}:we"},
                ],
            ]
            return {
                "status": "needs_reason",
                "write_performed": False,
                "message": "Уточни причину, чтобы следующая итерация была полезнее.",
                "reply_markup": {"inline_keyboard": reason_rows},
            }
        if proposal_type in {"feedback", "feedback_reason"}:
            try:
                record_feedback_transition(db_path, interaction_id=context_id, action_code=action)
            except sqlite3.Error:
                pass
            update_private_interaction_feedback(
                context_id,
                feedback=_feedback_label(action),
                reason=label if proposal_type == "feedback_reason" else "",
            )
        if proposal_type == "feedback_reason":
            return {
                "status": "recorded",
                "write_performed": False,
                "message": "Записал причину обратной связи.",
            }
        if proposal_type == "feedback" and str(context.get("primary_intent") or ""):
            return {
                "status": "recorded",
                "write_performed": False,
                "message": "Оценку записал.",
            }
        proposal_result = context["proposals"].get(action)
        if not isinstance(proposal_result, Mapping):
            proposal_result = build_memory_proposal(proposal_type, _proposal_args(context, action))
            proposal_result["confirmation"]["token"] = f"{PRM_CONFIRM_PREFIX}-{secrets.token_urlsafe(24)}"
            context["proposals"][action] = proposal_result
            _save_proposals(db_path, context_id, context["proposals"])
        confirm_data = f"{PRM_CONFIRM_PREFIX}:{context_id}:{action}"
        return {
            "status": "needs_confirmation",
            "write_performed": False,
            "proposal": proposal_result["proposal"],
            "message": _render_proposal_preview(label, proposal_result["proposal"]),
            "reply_markup": {"inline_keyboard": [[
                {"text": "Подтвердить", "callback_data": confirm_data},
                {"text": "Отменить", "callback_data": f"{PRM_ACTION_PREFIX}:{context_id}:c"},
            ]]},
        }
    proposal_result = context["proposals"].get(action)
    if not isinstance(proposal_result, Mapping):
        return {"status": "missing_proposal", "write_performed": False, "message": "Сначала выбери действие ещё раз."}
    claim_id = _claim_context_for_confirmation(db_path, context_id, chat_id)
    if claim_id is None:
        return {"status": "confirmation_in_progress", "write_performed": False, "message": "Подтверждение уже выполняется; повтори проверку статуса."}
    try:
        result = confirm_memory_proposal(
            db_path,
            {
                "proposal": proposal_result["proposal"],
                "confirmation_token": proposal_result["confirmation"]["token"],
                "expected_confirmation_token": proposal_result["confirmation"]["token"],
                "confirmed_by": "telegram_operator",
            },
        )
    except Exception:
        _clear_confirmation_lock(db_path, context_id, claim_id)
        raise
    if result.get("persisted"):
        _mark_confirmed(db_path, context_id, claim_id)
        return {**result, "message": "Сохранено. Запись можно использовать в следующих исследованиях."}
    _clear_confirmation_lock(db_path, context_id, claim_id)
    return result


def _followup_result(context: Mapping[str, Any], action: str) -> dict[str, Any]:
    query = _bounded_text(context.get("query") or context.get("title") or "тема", 180)
    if action == "o":
        suggested = f"Покажи ещё материалы по запросу: {query}"
        message = "Готов продолжить поиск. Отправь предложенный уточняющий запрос."
    else:
        suggested = f"Уточни поиск по теме: {query}"
        message = "Сузь формулировку или добавь точный термин, автора, канал либо период."
    return {
        "status": "followup_suggested",
        "write_performed": False,
        "message": message,
        "suggested_query": suggested,
    }


def _register_context(answer: Mapping[str, Any], *, db_path: str | Path | None, chat_id: str) -> str | None:
    # Telegram group IDs are negative.  A group callback does not identify a
    # single proposal owner on this legacy surface, so durable PRM actions are
    # deliberately unavailable there until the actor identity is carried from
    # the original message through registration and confirmation.
    if db_path is None or not chat_id or str(chat_id).startswith("-") or not Path(db_path).exists():
        return None
    context_id = secrets.token_hex(5)
    context = {
        "title": _bounded_text(answer.get("title") or "PRM research"),
        "query": _bounded_text(answer.get("query") or "", 220),
        "body": _bounded_text(answer.get("body") or answer.get("direct_answer") or ""),
        "source_refs": [str(ref) for ref in answer.get("source_refs") or [] if str(ref).startswith("https://")][:5],
        "evidence_items": _bounded_evidence_items(answer.get("archive_evidence")),
        "project_name": _bounded_text(answer.get("project_name") or ""),
        "primary_intent": _bounded_text(answer.get("primary_intent") or "", 64),
        "response_contract_id": _bounded_text(answer.get("response_contract_id") or "", 64),
        "direct_count": max(0, int(answer.get("direct_count") or 0)),
        "partial_count": max(0, int(answer.get("partial_count") or 0)),
        "allowed_actions": [str(code) for code in answer.get("keyboard_action_ids") or [] if str(code) in _ACTION_TYPES],
        "actor_hash": _chat_hash(chat_id),
        "proposals": {},
    }
    now = datetime.now(timezone.utc)
    try:
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "INSERT INTO prm_post_answer_proposals(context_id, chat_id_hash, summary_json, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (
                    context_id,
                    _chat_hash(chat_id),
                    json.dumps({key: value for key, value in context.items() if key != "proposals"}, ensure_ascii=False),
                    _iso(now),
                    _iso(now + _PROPOSAL_TTL),
                ),
            )
    except sqlite3.Error:
        return None
    try:
        record_interaction_receipt(
            db_path,
            interaction_id=context_id,
            chat_id_hash=_chat_hash(chat_id),
            answer=_receipt_metadata(answer),
        )
        write_private_interaction_receipt(answer, interaction_id=context_id)
    except (sqlite3.Error, ValueError, OSError):
        _mark_receipt_status(db_path, context_id, "failed")
    else:
        _mark_receipt_status(db_path, context_id, "recorded")
    return context_id


def _load_context(db_path: str | Path, context_id: str, chat_id: str, actor_id: str = "") -> dict[str, Any] | None:
    if not chat_id:
        return None
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                "SELECT chat_id_hash, summary_json, proposals_json, expires_at, status FROM prm_post_answer_proposals WHERE context_id = ?",
                (context_id,),
            ).fetchone()
    except sqlite3.Error:
        return None
    proposals = json.loads(str(row[2])) if row is not None else {}
    # A process may stop after claiming confirmation and before recording the
    # append-only event.  Retain that exact proposal for confirmation recovery;
    # ordinary expired drafts are still deleted below.
    locked = _confirmation_lock_value(proposals) is not None
    expired = row is not None and not locked and datetime.fromisoformat(str(row[3]).replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    if (
        row is None
        or row[0] != _chat_hash(chat_id)
        or row[4] == "cancelled"
        or expired
    ):
        if expired:
            _delete_context(db_path, context_id)
        return None
    context = json.loads(str(row[1]))
    if actor_id and str(context.get("actor_hash") or "") != _chat_hash(actor_id):
        return None
    context["proposals"] = proposals
    context["_status"] = str(row[4])
    return context


def _save_proposals(db_path: str | Path, context_id: str, proposals: Mapping[str, Any]) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE prm_post_answer_proposals SET proposals_json = ?, status = 'pending' "
            "WHERE context_id = ? AND status IN ('ready', 'pending') "
            "AND json_extract(proposals_json, '$.__confirmation_lock__') IS NULL",
            (json.dumps(proposals, ensure_ascii=False, sort_keys=True), context_id),
        )


def _mark_confirmed(db_path: str | Path, context_id: str, claim_id: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE prm_post_answer_proposals SET status = 'confirmed' WHERE context_id = ? "
            "AND status IN ('ready', 'pending') AND json_extract(proposals_json, '$.__confirmation_lock__') = ?",
            (context_id, claim_id),
        )


def _delete_context(db_path: str | Path, context_id: str) -> bool:
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            "DELETE FROM prm_post_answer_proposals WHERE context_id = ? AND status != 'confirmed' "
            "AND json_extract(proposals_json, '$.__confirmation_lock__') IS NULL",
            (context_id,),
        )
        return bool(cursor.rowcount)


def _claim_context_for_confirmation(db_path: str | Path, context_id: str, chat_id: str) -> str | None:
    now = datetime.now(timezone.utc)
    stale_before = _iso(now - _CONFIRMATION_LOCK_TTL)
    claim_id = f"{_iso(now)}:{secrets.token_hex(12)}"
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            "UPDATE prm_post_answer_proposals SET proposals_json = json_set(proposals_json, '$.__confirmation_lock__', ?) "
            "WHERE context_id = ? AND chat_id_hash = ? AND status IN ('ready', 'pending') "
            "AND (expires_at > ? OR json_extract(proposals_json, '$.__confirmation_lock__') IS NOT NULL) "
            "AND (json_extract(proposals_json, '$.__confirmation_lock__') IS NULL "
            "OR json_extract(proposals_json, '$.__confirmation_lock__') < ?)",
            (claim_id, context_id, _chat_hash(chat_id), _iso(now), stale_before),
        )
        return claim_id if cursor.rowcount else None


def _clear_confirmation_lock(db_path: str | Path, context_id: str, claim_id: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE prm_post_answer_proposals SET proposals_json = json_remove(proposals_json, '$.__confirmation_lock__'), status = 'pending' "
            "WHERE context_id = ? AND status IN ('ready', 'pending') "
            "AND json_extract(proposals_json, '$.__confirmation_lock__') = ?",
            (context_id, claim_id),
        )


def _mark_receipt_status(db_path: str | Path, context_id: str, status: str) -> None:
    try:
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE prm_post_answer_proposals SET receipt_status = ? WHERE context_id = ?",
                (status, context_id),
            )
    except sqlite3.Error:
        return


def _chat_hash(chat_id: str) -> str:
    return hashlib.sha256(f"prm.post-answer.v1:{chat_id}".encode()).hexdigest()


def _confirmation_lock_value(proposals: Mapping[str, Any]) -> str | None:
    value = proposals.get(_CONFIRMATION_LOCK_KEY)
    return str(value) if isinstance(value, str) and value else None


def _confirmation_locked(context: Mapping[str, Any]) -> bool:
    proposals = context.get("proposals")
    return isinstance(proposals, Mapping) and _confirmation_lock_value(proposals) is not None


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _proposal_args(context: Mapping[str, Any], action: str) -> dict[str, Any]:
    title = str(context["title"])
    item_index = _selected_item_index(action)
    if action == "n" and len(context.get("evidence_items") or []) == 1:
        item_index = 1
    selected_item = (context.get("evidence_items") or [])[item_index - 1] if item_index else {}
    body = str(selected_item.get("snippet") or context["body"])
    source_refs = [str(selected_item["source_url"])] if selected_item else context["source_refs"]
    feedback_titles = {
        "u": "Полезно",
        "m": "Частично",
        "x": "Мимо",
        "r": "Не тот приоритет",
        "s": "Слишком поверхностно",
        "d": "Применил",
    }
    if action in feedback_titles:
        return {
            "title": feedback_titles[action],
            "body": title,
            "rationale": "Операторская оценка PRM-ответа.",
            "source_refs": context["source_refs"],
            "metadata": {"feedback_type": action},
        }
    names = {
        "n": "Заметка",
        "w": "Наблюдать",
        "p": "Связь с проектом",
        "a": "Действие",
        "e": "Эксперимент",
    }
    proposal_label = names["n" if item_index else action]
    return {
        "title": f"{proposal_label}: {title}" + (f" — пункт {item_index}" if item_index else ""),
        "body": body,
        "rationale": "Черновик из локального PRM-ответа; сохранение требует подтверждения.",
        "source_refs": source_refs,
        "metadata": {
            **({"project_name": context["project_name"]} if context["project_name"] else {}),
            **({"selected_item_index": item_index} if item_index else {}),
        },
    }


def _parse_callback(callback_data: str) -> tuple[str, str, str]:
    parts = str(callback_data or "").split(":")
    action = parts[2] if len(parts) == 3 else ""
    valid_action = action in _ACTION_TYPES or _selected_item_index(action) is not None
    if len(parts) != 3 or parts[0] not in {PRM_ACTION_PREFIX, PRM_CONFIRM_PREFIX} or not valid_action:
        raise ValueError("Unsupported PRM post-answer callback")
    if not parts[1] or len(callback_data) > 64:
        raise ValueError("Invalid PRM post-answer callback")
    return parts[0], parts[1], parts[2]


def _selected_item_index(action: str) -> int | None:
    return int(action[1]) if len(action) == 2 and action.startswith("n") and action[1] in "12345" else None


def _action_allowed(context: Mapping[str, Any], action: str) -> bool:
    allowed = {str(code) for code in context.get("allowed_actions") or []}
    if _ACTION_TYPES.get(action, ("", ""))[0] == "feedback_reason":
        return str(context.get("proposals", {}).get("__reason_parent__") or "") in {"m", "x"}
    return ("n" if _selected_item_index(action) else action) in allowed


def _bounded_evidence_items(value: object) -> list[dict[str, str]]:
    items = value.get("items") if isinstance(value, Mapping) else []
    result: list[dict[str, str]] = []
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        url = str(item.get("source_url") or item.get("telegram_url") or "")
        snippet = _bounded_text(item.get("support_span") or item.get("snippet") or item.get("summary") or "", 400)
        if url.startswith("https://") and snippet:
            result.append({"source_url": url, "snippet": snippet})
        if len(result) >= 5:
            break
    return result


def _select_item_result(context_id: str, context: Mapping[str, Any]) -> dict[str, Any]:
    rows = [
        [{"text": f"Сохранить пункт {index}", "callback_data": f"{PRM_ACTION_PREFIX}:{context_id}:n{index}"}]
        for index, _item in enumerate(context.get("evidence_items") or [], start=1)
    ]
    rows.append([{"text": "Отменить", "callback_data": f"{PRM_ACTION_PREFIX}:{context_id}:c"}])
    return {
        "status": "select_item",
        "write_performed": False,
        "message": "Выбери точный пункт из этой версии ответа перед preview.",
        "reply_markup": {"inline_keyboard": rows},
    }


def _render_proposal_preview(label: str, proposal: Mapping[str, Any]) -> str:
    refs = ", ".join(str(ref) for ref in proposal.get("source_refs") or []) or "нет"
    return "\n".join((
        f"{label}: preview, запись не создана.",
        f"Тип: {proposal.get('object_type')}",
        f"Заголовок: {proposal.get('title')}",
        f"Текст: {proposal.get('body')}",
        f"Источники: {refs}",
        "Подтверди сохранение только если объект точный.",
    ))


def _button_label(code: str, *, intent: str) -> str:
    if intent:
        return _SHORT_LABELS.get(code, _ACTION_TYPES[code][1])
    return _ACTION_TYPES[code][1]


def _feedback_label(action: str) -> str:
    return {
        "u": "useful",
        "m": "partial",
        "x": "miss",
        "ws": "miss",
        "og": "partial",
        "wp": "miss",
        "na": "partial",
        "lg": "partial",
        "we": "partial",
        "r": "miss",
        "s": "partial",
        "d": "useful",
    }.get(action, "unknown")


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
        "primary_intent": answer.get("primary_intent"),
        "response_contract_id": answer.get("response_contract_id"),
        "professional_answer": professional,
    }
