"""Volatile, confirmation-gated Telegram actions for PRM research answers."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from dataclasses import dataclass
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
    "q": ("followup_refine", "Уточнить: термин, канал, период"),
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
_CANONICAL_PRIVATE_OWNER_ID = re.compile(r"[1-9][0-9]{0,18}\Z")
_MAX_PRIVATE_OWNER_ID = 9_223_372_036_854_775_807
_CONTEXT_ID = re.compile(r"[0-9a-f]{10}\Z")


@dataclass(frozen=True)
class UnavailablePrmAction:
    """A deliberately detail-free result for a rejected PRM control."""


@dataclass(frozen=True)
class ValidatedPrmAction:
    """Immutable, read-only validation output consumed by one CAS application."""

    prefix: str
    context_id: str
    action: str
    chat_id: str
    actor_id: str
    owner_chat_id: str
    status: str
    expires_at: str
    summary_json: str
    proposals_json: str
    summary_fingerprint: str
    proposals_fingerprint: str
    source_snapshot_json: str

_SHORT_LABELS = {
    "u": "👍 Полезно",
    "m": "≈ Частично",
    "x": "👎 Мимо",
    "n": "Сохранить",
    "p": "К проекту",
    "a": "Сохранить действие",
    "e": "Сохранить эксперимент",
    "o": "Показать ещё",
    "q": "Уточнить: термин, канал, период",
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


def build_post_answer_actions(
    answer: Mapping[str, Any], *, db_path: str | Path | None = None, chat_id: str = "",
    actor_id: str | None = None, owner_chat_id: str | None = None,
) -> dict[str, Any]:
    """Register a bounded answer context and return only relevant safe actions."""

    private_tuple = _private_owner_tuple(chat_id, actor_id, owner_chat_id)
    if private_tuple is None:
        return {"context_id": None, "reply_markup": None, "action_codes": []}
    action_codes = select_post_answer_action_codes(answer)
    traced_answer = {**dict(answer), "keyboard_action_ids": action_codes}
    context_id = _register_context(
        traced_answer,
        db_path=db_path,
        chat_id=private_tuple[0],
        actor_id=private_tuple[1],
        owner_chat_id=private_tuple[2],
    )
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


def handle_post_answer_callback(
    db_path: str,
    callback_data: str,
    *,
    chat_id: str,
    actor_id: str | None = None,
    owner_chat_id: str | None = None,
) -> dict[str, Any]:
    """Validate once without writes, then apply that exact bound transition."""

    validated = validate_prm_post_answer_callback(
        db_path,
        callback_data,
        chat_id=chat_id,
        actor_id=actor_id,
        owner_chat_id=owner_chat_id,
    )
    if isinstance(validated, UnavailablePrmAction):
        return _unavailable_action()
    return apply_validated_prm_action(db_path, validated)


def validate_prm_post_answer_callback(
    db_path: str | Path,
    callback_data: str,
    *,
    chat_id: str,
    actor_id: str | None = None,
    owner_chat_id: str | None = None,
) -> ValidatedPrmAction | UnavailablePrmAction:
    """Purely validate a PRM callback against one immutable persisted context."""

    private_tuple = _private_owner_tuple(chat_id, actor_id, owner_chat_id)
    if private_tuple is None:
        return UnavailablePrmAction()
    try:
        prefix, context_id, action = _parse_callback(callback_data)
    except (TypeError, ValueError):
        return UnavailablePrmAction()
    if not _CONTEXT_ID.fullmatch(context_id):
        return UnavailablePrmAction()
    row = _read_prm_validation_row(db_path, context_id)
    if row is None:
        return UnavailablePrmAction()
    stored_chat_hash, summary_json, proposals_json, expires_at, status = row
    if stored_chat_hash != _chat_hash(private_tuple[0]) or status not in {"ready", "pending", "confirmed"}:
        return UnavailablePrmAction()
    try:
        context = json.loads(summary_json)
        proposals = json.loads(proposals_json)
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return UnavailablePrmAction()
    if not isinstance(context, dict) or not isinstance(proposals, dict) or expiry.tzinfo is None:
        return UnavailablePrmAction()
    if expiry <= datetime.now(timezone.utc) and _confirmation_lock_value(proposals) is None:
        return UnavailablePrmAction()
    if not _valid_prm_binding(context, context_id):
        return UnavailablePrmAction()
    if (
        context.get("actor_hash") != _chat_hash(private_tuple[1])
        or context.get("owner_chat_id_hash") != _chat_hash(private_tuple[2])
    ):
        return UnavailablePrmAction()
    snapshot = context["prm_post_answer_action_binding"]["source_snapshot"]
    if not isinstance(snapshot, Mapping) or not _validated_transition_allowed(prefix, action, snapshot, proposals, status):
        return UnavailablePrmAction()
    try:
        snapshot_json = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return UnavailablePrmAction()
    return ValidatedPrmAction(
        prefix=prefix,
        context_id=context_id,
        action=action,
        chat_id=private_tuple[0],
        actor_id=private_tuple[1],
        owner_chat_id=private_tuple[2],
        status=status,
        expires_at=expires_at,
        summary_json=summary_json,
        proposals_json=proposals_json,
        summary_fingerprint=_fingerprint(summary_json),
        proposals_fingerprint=_fingerprint(proposals_json),
        source_snapshot_json=snapshot_json,
    )


def apply_validated_prm_action(
    db_path: str | Path, validated: ValidatedPrmAction,
) -> dict[str, Any]:
    """Consume one validated transition with a status/expiry/fingerprint CAS."""

    if not isinstance(validated, ValidatedPrmAction):
        return _unavailable_action()
    if validated.prefix == PRM_CONFIRM_PREFIX:
        return _apply_validated_confirmation(db_path, validated)
    try:
        context, proposals = _validated_context_and_proposals(validated)
        with sqlite3.connect(db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not _validated_row_is_current(connection, validated):
                connection.rollback()
                return _unavailable_action()
            if validated.status == "confirmed":
                connection.rollback()
                return _unavailable_action()
            action = validated.action
            if action in {"o", "q"}:
                connection.rollback()
                return _followup_result(context, action)
            if action == "c":
                if not _cas_prm_context(
                    connection, validated, proposals=proposals, next_status="cancelled",
                ):
                    connection.rollback()
                    return _unavailable_action()
                connection.commit()
                return {"status": "cancelled", "write_performed": False, "message": "Черновик отменён. Запись не создана."}
            if action == "n" and len(context["evidence_items"]) > 1:
                issued = [f"n{index}" for index in range(1, len(context["evidence_items"]) + 1)]
                proposals["__selection__"] = {"parent": "n", "issued_codes": issued}
                proposals["__cancel_issued_for__"] = {"kind": "selection", "parent": "n"}
                if not _cas_prm_context(connection, validated, proposals=proposals, next_status="pending"):
                    connection.rollback()
                    return _unavailable_action()
                connection.commit()
                return _select_item_result(validated.context_id, context)
            proposal_type, label = _ACTION_TYPES["n" if _selected_item_index(action) else action]
            if proposal_type == "feedback_reason_prompt":
                proposals["__feedback_reason__"] = {
                    "parent": action,
                    "issued_codes": ["ws", "og", "wp", "na", "lg", "we"],
                }
                if not _cas_prm_context(connection, validated, proposals=proposals, next_status="pending"):
                    connection.rollback()
                    return _unavailable_action()
                connection.commit()
                _record_validated_feedback(db_path, validated.context_id, action, label)
                return _reason_prompt_result(validated.context_id)
            if proposal_type == "feedback_reason":
                proposals["__feedback_recorded__"] = action
                if not _cas_prm_context(connection, validated, proposals=proposals, next_status="pending"):
                    connection.rollback()
                    return _unavailable_action()
                connection.commit()
                _record_validated_feedback(db_path, validated.context_id, action, label)
                return {"status": "recorded", "write_performed": False, "message": "Записал причину обратной связи."}
            if proposal_type == "feedback" and context["primary_intent"]:
                proposals["__feedback_recorded__"] = action
                if not _cas_prm_context(connection, validated, proposals=proposals, next_status="pending"):
                    connection.rollback()
                    return _unavailable_action()
                connection.commit()
                _record_validated_feedback(db_path, validated.context_id, action, label)
                return {"status": "recorded", "write_performed": False, "message": "Оценку записал."}
            proposal_result = proposals.get(action)
            if not isinstance(proposal_result, Mapping):
                proposal_result = build_memory_proposal(proposal_type, _proposal_args(context, action))
                proposal_result["confirmation"]["token"] = f"{PRM_CONFIRM_PREFIX}-{secrets.token_urlsafe(24)}"
                proposals[action] = proposal_result
            proposals["__cancel_issued_for__"] = {"kind": "preview", "parent": action}
            if not _cas_prm_context(connection, validated, proposals=proposals, next_status="pending"):
                connection.rollback()
                return _unavailable_action()
            connection.commit()
    except (KeyError, TypeError, ValueError, sqlite3.Error):
        return _unavailable_action()
    if proposal_type == "feedback":
        _record_validated_feedback(db_path, validated.context_id, action, label)
    proposal = proposal_result.get("proposal") if isinstance(proposal_result, Mapping) else None
    if not isinstance(proposal, Mapping):
        return _unavailable_action()
    return {
        "status": "needs_confirmation",
        "write_performed": False,
        "proposal": proposal,
        "message": _render_proposal_preview(label, proposal),
        "reply_markup": {"inline_keyboard": [[
            {"text": "Подтвердить", "callback_data": f"{PRM_CONFIRM_PREFIX}:{validated.context_id}:{action}"},
            {"text": "Отменить", "callback_data": f"{PRM_ACTION_PREFIX}:{validated.context_id}:c"},
        ]]},
    }


def _read_prm_validation_row(
    db_path: str | Path, context_id: str,
) -> tuple[str, str, str, str, str] | None:
    """Read exactly one context through SQLite's read-only connection mode."""

    try:
        database_uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
        with sqlite3.connect(database_uri, uri=True) as connection:
            row = connection.execute(
                "SELECT chat_id_hash, summary_json, proposals_json, expires_at, status "
                "FROM prm_post_answer_proposals WHERE context_id = ?",
                (context_id,),
            ).fetchone()
    except (OSError, sqlite3.Error):
        return None
    if row is None or len(row) != 5 or any(not isinstance(value, str) for value in row):
        return None
    return row


def _validated_transition_allowed(
    prefix: str,
    action: str,
    snapshot: Mapping[str, Any],
    proposals: Mapping[str, Any],
    status: str,
) -> bool:
    """Accept only the initial offer or an exact server-issued child state."""

    if prefix == PRM_CONFIRM_PREFIX:
        proposal = proposals.get(action)
        confirmation = proposal.get("confirmation") if isinstance(proposal, Mapping) else None
        return (
            status in {"ready", "pending", "confirmed"}
            and action != "c"
            and isinstance(proposal, Mapping)
            and isinstance(proposal.get("proposal"), Mapping)
            and isinstance(confirmation, Mapping)
            and isinstance(confirmation.get("token"), str)
            and bool(confirmation.get("token"))
        )
    if prefix != PRM_ACTION_PREFIX or status == "confirmed":
        return False
    if action == "c":
        issued = proposals.get("__cancel_issued_for__")
        return (
            status in {"ready", "pending"}
            and isinstance(issued, Mapping)
            and issued.get("kind") in {"selection", "preview"}
            and isinstance(issued.get("parent"), str)
            and _confirmation_lock_value(proposals) is None
        )
    selected_index = _selected_item_index(action)
    if selected_index:
        selection = proposals.get("__selection__")
        issued_codes = selection.get("issued_codes") if isinstance(selection, Mapping) else None
        return (
            isinstance(selection, Mapping)
            and selection.get("parent") == "n"
            and isinstance(issued_codes, list)
            and action in issued_codes
            and selected_index <= len(snapshot.get("evidence_items") or [])
        )
    if _ACTION_TYPES.get(action, ("", ""))[0] == "feedback_reason":
        reason = proposals.get("__feedback_reason__")
        issued_codes = reason.get("issued_codes") if isinstance(reason, Mapping) else None
        return (
            isinstance(reason, Mapping)
            and reason.get("parent") in {"m", "x"}
            and isinstance(issued_codes, list)
            and action in issued_codes
        )
    offered = snapshot.get("offered_action_codes")
    return isinstance(offered, list) and action in offered


def _validated_context_and_proposals(
    validated: ValidatedPrmAction,
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = json.loads(validated.source_snapshot_json)
    proposals = json.loads(validated.proposals_json)
    if not isinstance(snapshot, dict) or not isinstance(proposals, dict):
        raise ValueError("validated PRM payload is malformed")
    return {
        **snapshot,
        "allowed_actions": snapshot["offered_action_codes"],
        "proposals": proposals,
    }, proposals


def _validated_row_is_current(
    connection: sqlite3.Connection, validated: ValidatedPrmAction,
) -> bool:
    row = connection.execute(
        "SELECT chat_id_hash, summary_json, proposals_json, expires_at, status "
        "FROM prm_post_answer_proposals WHERE context_id = ?",
        (validated.context_id,),
    ).fetchone()
    if row is None or len(row) != 5:
        return False
    chat_hash, summary_json, proposals_json, expires_at, status = row
    if not all(isinstance(value, str) for value in row):
        return False
    return (
        chat_hash == _chat_hash(validated.chat_id)
        and status == validated.status
        and expires_at == validated.expires_at
        and _fingerprint(summary_json) == validated.summary_fingerprint
        and _fingerprint(proposals_json) == validated.proposals_fingerprint
    )


def _cas_prm_context(
    connection: sqlite3.Connection,
    validated: ValidatedPrmAction,
    *,
    proposals: Mapping[str, Any],
    next_status: str,
) -> bool:
    payload = json.dumps(proposals, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    cursor = connection.execute(
        "UPDATE prm_post_answer_proposals SET proposals_json = ?, status = ? "
        "WHERE context_id = ? AND chat_id_hash = ? AND summary_json = ? "
        "AND proposals_json = ? AND status = ? AND expires_at = ?",
        (
            payload,
            next_status,
            validated.context_id,
            _chat_hash(validated.chat_id),
            validated.summary_json,
            validated.proposals_json,
            validated.status,
            validated.expires_at,
        ),
    )
    return bool(cursor.rowcount)


def _apply_validated_confirmation(
    db_path: str | Path, validated: ValidatedPrmAction,
) -> dict[str, Any]:
    """Claim the exact preview by CAS before the confirmation-gated memory write."""

    try:
        _context, proposals = _validated_context_and_proposals(validated)
        proposal_result = proposals.get(validated.action)
        proposal = proposal_result.get("proposal") if isinstance(proposal_result, Mapping) else None
        confirmation = proposal_result.get("confirmation") if isinstance(proposal_result, Mapping) else None
        token = confirmation.get("token") if isinstance(confirmation, Mapping) else None
        if not isinstance(proposal, Mapping) or not isinstance(token, str) or not token:
            return _unavailable_action()
        with sqlite3.connect(db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not _validated_row_is_current(connection, validated):
                connection.rollback()
                return _unavailable_action()
            if validated.status == "confirmed":
                connection.rollback()
                return {"status": "already_confirmed", "write_performed": False, "message": "Этот черновик уже подтверждён; новая запись не создаётся."}
            existing_lock = _confirmation_lock_value(proposals)
            if existing_lock is not None and not _stale_confirmation_lock(existing_lock):
                connection.rollback()
                return {"status": "confirmation_in_progress", "write_performed": False, "message": "Подтверждение уже выполняется; повтори проверку статуса."}
            claim_id = f"{_iso(datetime.now(timezone.utc))}:{secrets.token_hex(12)}"
            proposals[_CONFIRMATION_LOCK_KEY] = claim_id
            if not _cas_prm_context(connection, validated, proposals=proposals, next_status="pending"):
                connection.rollback()
                return _unavailable_action()
            connection.commit()
    except (KeyError, TypeError, ValueError, sqlite3.Error):
        return _unavailable_action()
    try:
        result = confirm_memory_proposal(
            db_path,
            {
                "proposal": proposal,
                "confirmation_token": token,
                "expected_confirmation_token": token,
                "confirmed_by": "telegram_operator",
            },
        )
    except Exception:
        _clear_confirmation_lock(db_path, validated.context_id, claim_id)
        return _unavailable_action()
    if result.get("persisted"):
        _mark_confirmed(db_path, validated.context_id, claim_id)
        return {**result, "message": "Сохранено. Запись можно использовать в следующих исследованиях."}
    _clear_confirmation_lock(db_path, validated.context_id, claim_id)
    return result


def _stale_confirmation_lock(value: str) -> bool:
    marker = value.split("Z", 1)[0]
    if "Z" not in value:
        return False
    try:
        claimed_at = datetime.fromisoformat(f"{marker}+00:00")
    except ValueError:
        return False
    return claimed_at <= datetime.now(timezone.utc) - _CONFIRMATION_LOCK_TTL


def _record_validated_feedback(
    db_path: str | Path, context_id: str, action: str, label: str,
) -> None:
    try:
        record_feedback_transition(str(db_path), interaction_id=context_id, action_code=action)
    except sqlite3.Error:
        pass
    update_private_interaction_feedback(
        context_id,
        feedback=_feedback_label(action),
        reason=label if _ACTION_TYPES.get(action, ("", ""))[0] == "feedback_reason" else "",
    )


def _reason_prompt_result(context_id: str) -> dict[str, Any]:
    codes = (("ws", "og"), ("wp", "na"), ("lg", "we"))
    return {
        "status": "needs_reason",
        "write_performed": False,
        "message": "Уточни причину, чтобы следующая итерация была полезнее.",
        "reply_markup": {"inline_keyboard": [
            [
                {"text": _ACTION_TYPES[left][1], "callback_data": f"{PRM_ACTION_PREFIX}:{context_id}:{left}"},
                {"text": _ACTION_TYPES[right][1], "callback_data": f"{PRM_ACTION_PREFIX}:{context_id}:{right}"},
            ]
            for left, right in codes
        ]},
    }


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def _register_context(
    answer: Mapping[str, Any], *, db_path: str | Path | None, chat_id: str,
    actor_id: str, owner_chat_id: str,
) -> str | None:
    # Telegram group IDs are negative.  A group callback does not identify a
    # single proposal owner on this legacy surface, so durable PRM actions are
    # deliberately unavailable there until the actor identity is carried from
    # the original message through registration and confirmation.
    if db_path is None or not chat_id or str(chat_id).startswith("-") or not Path(db_path).exists():
        return None
    context_id = secrets.token_hex(5)
    snapshot = canonicalize_prm_action_snapshot(answer)
    if snapshot is None:
        return None
    encoded_snapshot = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    context = {
        **snapshot,
        "allowed_actions": snapshot["offered_action_codes"],
        "context_kind": "prm",
        "prm_post_answer_action_binding": {
            "version": "prm_post_answer_action_binding.v1",
            "source_result_id": context_id,
            "source_snapshot": snapshot,
            "source_result_version": hashlib.sha256(encoded_snapshot.encode("utf-8")).hexdigest(),
            **({"source_project_ref": {"origin": snapshot["project_name"], "value": snapshot["project_name"]}} if snapshot["project_name"] else {}),
        },
        "actor_hash": _chat_hash(actor_id),
        "owner_chat_id_hash": _chat_hash(owner_chat_id),
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


def _load_context(
    db_path: str | Path, context_id: str, chat_id: str, actor_id: str, owner_chat_id: str,
) -> dict[str, Any] | None:
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
    if row is None:
        return None
    try:
        proposals = json.loads(str(row[2]))
        expires_at = datetime.fromisoformat(str(row[3]).replace("Z", "+00:00"))
        context = json.loads(str(row[1]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(proposals, dict) or not isinstance(context, dict):
        return None
    # A process may stop after claiming confirmation and before recording the
    # append-only event.  Retain that exact proposal for confirmation recovery;
    # ordinary expired drafts are still deleted below.
    locked = _confirmation_lock_value(proposals) is not None
    expired = not locked and expires_at <= datetime.now(timezone.utc)
    if (
        row[0] != _chat_hash(chat_id)
        or row[4] == "cancelled"
        or expired
    ):
        return None
    if not _valid_prm_binding(context, context_id):
        return None
    if (
        str(context.get("actor_hash") or "") != _chat_hash(actor_id)
        or str(context.get("owner_chat_id_hash") or "") != _chat_hash(owner_chat_id)
    ):
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


def canonical_private_owner_id(value: object) -> str | None:
    """Return one safe Telegram private-owner ID spelling or None."""

    if not isinstance(value, str) or not _CANONICAL_PRIVATE_OWNER_ID.fullmatch(value):
        return None
    return value if int(value) <= _MAX_PRIVATE_OWNER_ID else None


def _private_owner_tuple(
    chat_id: object, actor_id: object, owner_chat_id: object,
) -> tuple[str, str, str] | None:
    values = tuple(canonical_private_owner_id(value) for value in (chat_id, actor_id, owner_chat_id))
    if None in values or len(set(values)) != 1:
        return None
    return values  # type: ignore[return-value]


def _unavailable_action() -> dict[str, Any]:
    return {"status": "action_unavailable", "write_performed": False, "message": "Действие недоступно. Запроси ответ заново."}


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


def canonicalize_prm_action_snapshot(answer: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build the only bounded immutable answer representation for an action."""

    if not isinstance(answer, Mapping):
        return None
    try:
        def scalar(key: str, limit: int, *, fallback: str | None = None) -> str | None:
            value = answer.get(key) if key in answer else (answer.get(fallback) if fallback else None)
            if value is None:
                return ""
            return _bounded_text(value, limit) if isinstance(value, str) else None

        title = scalar("title", 240)
        query = scalar("query", 220)
        body = scalar("body", 240, fallback="direct_answer")
        project_name = scalar("project_name", 240)
        intent = scalar("primary_intent", 64)
        contract = scalar("response_contract_id", 64)
        if None in {title, query, body, project_name, intent, contract}:
            return None
        counts: dict[str, int] = {}
        for key in ("direct_count", "partial_count"):
            value = answer.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
                return None
            counts[key] = value
        raw_refs = answer.get("source_refs", [])
        if not isinstance(raw_refs, (list, tuple)):
            return None
        refs: list[str] = []
        for raw in raw_refs:
            if not isinstance(raw, str):
                return None
            if raw.startswith("https://") and len(raw) <= 512 and raw not in refs:
                refs.append(raw)
            if len(refs) == 5:
                break
        if "evidence_items" in answer:
            evidence = answer["evidence_items"]
        else:
            evidence = _bounded_evidence_items(answer.get("archive_evidence"))
        if not isinstance(evidence, (list, tuple)) or any(not isinstance(item, Mapping) for item in evidence):
            return None
        normalized_evidence: list[dict[str, str]] = []
        for item in evidence:
            url = item.get("source_url")
            snippet = item.get("snippet")
            if not isinstance(url, str) or not url.startswith("https://") or len(url) > 512 or not isinstance(snippet, str):
                return None
            pair = {"source_url": url, "snippet": _bounded_text(snippet, 400)}
            if pair["snippet"] and pair not in normalized_evidence:
                normalized_evidence.append(pair)
            if len(normalized_evidence) == 5:
                break
        raw_codes = answer.get("offered_action_codes", answer.get("keyboard_action_ids", []))
        if not isinstance(raw_codes, (list, tuple)):
            return None
        action_codes: list[str] = []
        for code in raw_codes:
            if not isinstance(code, str):
                return None
            if code in _ACTION_TYPES and code not in action_codes:
                action_codes.append(code)
            if len(action_codes) == 20:
                break
        return {
            "title": title or "PRM research", "query": query or "", "body": body or "",
            "source_refs": refs, "evidence_items": normalized_evidence,
            "project_name": project_name or "", "primary_intent": intent or "",
            "response_contract_id": contract or "", **counts,
            "offered_action_codes": action_codes,
        }
    except (TypeError, ValueError, UnicodeError):
        return None


def _valid_prm_binding(context: Mapping[str, Any], context_id: str) -> bool:
    binding = context.get("prm_post_answer_action_binding")
    if not isinstance(binding, Mapping) or context.get("context_kind") != "prm":
        return False
    snapshot = binding.get("source_snapshot")
    if not isinstance(snapshot, Mapping) or binding.get("source_result_id") != context_id:
        return False
    canonical = canonicalize_prm_action_snapshot(snapshot)
    if canonical is None:
        return False
    if dict(snapshot) != canonical:
        return False
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    expected_binding: dict[str, Any] = {
        "version": "prm_post_answer_action_binding.v1",
        "source_result_id": context_id,
        "source_snapshot": canonical,
        "source_result_version": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }
    if canonical["project_name"]:
        expected_binding["source_project_ref"] = {
            "origin": canonical["project_name"], "value": canonical["project_name"],
        }
    if dict(binding) != expected_binding:
        return False
    if context.get("allowed_actions") != canonical["offered_action_codes"]:
        return False
    return all(context.get(key) == value for key, value in canonical.items())


def _select_item_result(context_id: str, context: Mapping[str, Any]) -> dict[str, Any]:
    rows = [
        [{"text": f"Сохранить пункт {index}", "callback_data": f"{PRM_ACTION_PREFIX}:{context_id}:n{index}"}]
        for index, _item in enumerate(context.get("evidence_items") or [], start=1)
    ]
    rows.append([{"text": "Отменить", "callback_data": f"{PRM_ACTION_PREFIX}:{context_id}:c"}])
    return {
        "status": "select_item",
        "write_performed": False,
        "message": "Выбери точный пункт из этой версии ответа перед предпросмотром.",
        "reply_markup": {"inline_keyboard": rows},
    }


def _render_proposal_preview(label: str, proposal: Mapping[str, Any]) -> str:
    refs = ", ".join(str(ref) for ref in proposal.get("source_refs") or []) or "нет"
    return "\n".join((
        f"{label}: предпросмотр, запись не создана.",
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
