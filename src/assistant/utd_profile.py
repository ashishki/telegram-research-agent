"""Confirmation-gated UTD profile and preview-watch UX.

UTD-1 deliberately stops at a local draft and a confirmed PRM memory event.
It never fetches UTD sources, starts timers, calls a model, or sends alerts.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from assistant.pi_memory import build_memory_proposal, confirm_memory_proposal
from assistant.utd_profile_schema import (
    UTD_CONFIRM_PREFIX,
    UTD_DRAFT_PREFIX,
    UTD_DRAFT_TTL,
    UTD_PROFILE_SCHEMA_VERSION,
    UTD_TIMEZONE,
    UTD_WATCH_SCHEMA_VERSION,
    _apply_draft_action,
    _as_utc,
    _CATEGORY_LABELS,
    _default_draft,
    _FREQUENCY_LABELS,
    _iso,
    _negative_terms,
    _normalize_draft,
    _onboarding_markup,
    _parse_seed,
    _positive_terms,
    _selected_sources,
    classify_utd_question,
    is_utd_profile_intent,
    is_utd_question,
    render_utd_onboarding,
    render_utd_watch_preview,
)
from assistant.utd_profile_store import (
    _chat_hash,
    _draft_schema_ready,
    _load_draft,
    _save_draft,
    _set_draft_status,
    load_confirmed_utd_profile,
)

UTD_SUBSCRIPTION_PREFIX = "utds"


def start_utd_profile_onboarding(
    db_path: str | Path,
    *,
    chat_id: str,
    seed_text: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create an expiring local draft; no PRM preference is persisted yet."""

    current = _as_utc(now)
    db_file = Path(db_path)
    if not chat_id or not db_file.exists():
        return _unavailable("Локальная PRM-база недоступна; UTD-черновик не создан.")

    draft = _default_draft(current)
    draft.update(_parse_seed(seed_text))
    context_id = f"u{secrets.token_hex(5)}"
    try:
        with sqlite3.connect(db_file) as connection:
            if not _draft_schema_ready(connection):
                return _unavailable(
                    "Таблица безопасных PRM-черновиков недоступна; профиль не сохранён."
                )
            connection.execute(
                """
                INSERT INTO prm_post_answer_proposals (
                    context_id, chat_id_hash, summary_json, proposals_json,
                    created_at, expires_at, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    context_id,
                    _chat_hash(chat_id),
                    json.dumps(
                        {"kind": "utd_profile_draft", "draft": draft},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "{}",
                    _iso(current),
                    _iso(current + UTD_DRAFT_TTL),
                    "draft",
                ),
            )
            connection.commit()
    except sqlite3.Error:
        return _unavailable("Не смог создать локальный UTD-черновик; профиль не сохранён.")

    return {
        "status": "draft_started",
        "context_id": context_id,
        "profile_persisted": False,
        "write_performed": False,
        "draft_state_written": True,
        "message": render_utd_onboarding(draft),
        "reply_markup": _onboarding_markup(context_id, draft),
    }


def handle_utd_profile_callback(
    db_path: str | Path,
    callback_data: str,
    *,
    chat_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Mutate only an expiring draft unless the exact `utdc:*:save` callback is used."""

    current = _as_utc(now)
    prefix, context_id, action = _parse_callback(callback_data)
    loaded = _load_draft(db_path, context_id=context_id, chat_id=chat_id, now=current)
    if loaded is None:
        return {
            "status": "expired",
            "profile_persisted": False,
            "write_performed": False,
            "message": "UTD-черновик истёк или принадлежит другому чату. Начни настройку заново.",
        }
    draft, proposals, status = loaded

    if prefix == UTD_CONFIRM_PREFIX:
        if action != "save":
            raise ValueError("Unsupported UTD confirmation action")
        proposal_result = proposals.get("utd_profile")
        if not isinstance(proposal_result, Mapping):
            return {
                "status": "missing_preview",
                "profile_persisted": False,
                "write_performed": False,
                "message": "Сначала открой preview, затем подтверждай сохранение.",
            }
        proposal = proposal_result.get("proposal")
        confirmation = proposal_result.get("confirmation")
        if not isinstance(proposal, Mapping) or not isinstance(confirmation, Mapping):
            raise ValueError("Invalid UTD proposal state")
        _assert_non_executable_proposal(proposal)
        # A crash after the durable claim is safely resumable with the exact
        # proposal/token; the append-only confirmation remains idempotent.
        if status in {"confirmed", "confirming"}:
            recovered = confirm_memory_proposal(db_path, {"proposal": proposal, "confirmation_token": confirmation.get("token"), "confirmed_by": "telegram_operator", "confirmed_at": _iso(current)})
            if recovered.get("persisted"):
                _finish_utd_preview_claim(db_path, context_id=context_id, status="confirmed")
            return {**recovered, "profile_persisted": bool(recovered.get("persisted"))}
        if not _claim_utd_preview(db_path, context_id=context_id, chat_id=chat_id, now=current):
            return {"status": "expired", "profile_persisted": False, "write_performed": False, "message": "Preview уже отменён или подтверждается; открой новый."}
        result = confirm_memory_proposal(
            db_path,
            {
                "proposal": proposal,
                "confirmation_token": confirmation.get("token"),
                "confirmed_by": "telegram_operator",
                "confirmed_at": _iso(current),
            },
        )
        if result.get("persisted"):
            _finish_utd_preview_claim(db_path, context_id=context_id, status="confirmed")
            return {
                **result,
                "profile_persisted": True,
                "message": (
                    "UTD-профиль сохранён как подтверждённый scope. Само это действие "
                    "не запускает runtime, таймеры, модель или Telegram-уведомления. Но если "
                    "отдельно включённый runtime уже существует, активный scope может быть "
                    "прочитан на его следующем запуске; kill switch и остальные delivery-gates "
                    "всё равно проверяются."
                ),
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "Поставить UTD-подписку на паузу", "callback_data": f"{UTD_SUBSCRIPTION_PREFIX}:pause:preview"}],
                        [{"text": "Отменить UTD-подписку", "callback_data": f"{UTD_SUBSCRIPTION_PREFIX}:cancel:preview"}],
                    ]
                },
            }
        _finish_utd_preview_claim(db_path, context_id=context_id, status="previewed")
        return {**result, "profile_persisted": False}

    if action == "cx":
        if not _cancel_utd_preview(db_path, context_id=context_id, chat_id=chat_id):
            return {"status": "expired", "profile_persisted": False, "write_performed": False, "message": "Preview уже подтверждается; отмена не изменила профиль."}
        return {
            "status": "cancelled",
            "profile_persisted": False,
            "write_performed": False,
            "message": "UTD-черновик отменён. Постоянный профиль не изменён.",
        }
    if action == "pv":
        proposal_result = build_utd_watch_proposal(draft)
        proposals = {"utd_profile": proposal_result}
        _save_draft(db_path, context_id, draft=draft, proposals=proposals, status="previewed")
        return {
            "status": "needs_confirmation",
            "profile_persisted": False,
            "write_performed": False,
            "message": render_utd_watch_preview(draft),
            "proposal": proposal_result["proposal"],
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {
                            "text": "Подтвердить профиль",
                            "callback_data": f"{UTD_CONFIRM_PREFIX}:{context_id}:save",
                        }
                    ],
                    [
                        {
                            "text": "Вернуться к настройкам",
                            "callback_data": f"{UTD_DRAFT_PREFIX}:{context_id}:back",
                        },
                        {
                            "text": "Отмена",
                            "callback_data": f"{UTD_DRAFT_PREFIX}:{context_id}:cx",
                        },
                    ],
                ]
            },
        }
    if action == "back":
        return {
            "status": "draft_updated",
            "profile_persisted": status == "confirmed",
            "write_performed": False,
            "message": render_utd_onboarding(draft),
            "reply_markup": _onboarding_markup(context_id, draft),
        }

    _apply_draft_action(draft, action, current)
    _save_draft(db_path, context_id, draft=draft, proposals={}, status="draft")
    return {
        "status": "draft_updated",
        "profile_persisted": False,
        "write_performed": False,
        "message": render_utd_onboarding(draft),
        "reply_markup": _onboarding_markup(context_id, draft),
    }


def build_utd_watch_proposal(draft: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize_draft(draft)
    metadata = {
        "capability": "utd_profile_preview_watch",
        "profile_schema_version": UTD_PROFILE_SCHEMA_VERSION,
        "watch_schema_version": UTD_WATCH_SCHEMA_VERSION,
        "program": normalized["program"],
        "career_goals": normalized["career_goals"],
        "ai_interests": normalized["ai_interests"],
        "audience_context": normalized["audience_context"],
        "categories": normalized["categories"],
        "sources": _selected_sources(normalized),
        "positive_terms": _positive_terms(normalized),
        "negative_terms": _negative_terms(),
        "timezone": UTD_TIMEZONE,
        "frequency": normalized["frequency"],
        "daily_cap": normalized["daily_cap"],
        "expires_at": normalized["expires_at"],
        "paused": normalized["paused"],
        "muted_sources": normalized["muted_sources"],
        "exclusions": normalized["exclusions"],
        "language": normalized["language"],
        "depth": normalized["depth"],
        "period": normalized["period"],
        "schedule": normalized["schedule"],
        "quiet_hours": normalized["quiet_hours"],
        "subscription_status": normalized["subscription_status"],
        "monitoring_authorized": False,
        "delivery_authorized": False,
        "provider_egress_authorized": False,
        "source_status": "preview_only",
    }
    return build_memory_proposal(
        "watch_topic",
        {
            "title": "UTD profile and preview watch",
            "body": render_utd_watch_preview(normalized),
            "rationale": (
                "Operator-confirmed UTD relevance scope only; this event is not permission "
                "to poll sources, run timers, call a provider, or deliver notifications."
            ),
            "source_refs": [],
            "metadata": metadata,
        },
    )


def build_utd_subscription_cancel_proposal(db_path: str | Path) -> dict[str, Any]:
    """Prepare, but never persist, an exact revision-bound unsubscribe tombstone."""
    path = Path(db_path)
    if not path.exists():
        return {"status": "unavailable", "persisted": False, "message": "Подписка не найдена."}
    try:
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
            rows = connection.execute(
                "SELECT id,memory_id,event_type,title,metadata_json FROM personal_memory_events "
                "WHERE object_type='watch_topic' ORDER BY id DESC"
            ).fetchall()
    except sqlite3.Error:
        return {"status": "unavailable", "persisted": False, "message": "Подписка не найдена."}
    seen_memory_ids: set[str] = set()
    for event_id, memory_id, event_type, title, raw_metadata in rows:
        memory_id = str(memory_id)
        if memory_id in seen_memory_ids:
            continue
        seen_memory_ids.add(memory_id)
        try:
            metadata = json.loads(str(raw_metadata))
        except (TypeError, json.JSONDecodeError):
            continue
        if metadata.get("capability") != "utd_profile_preview_watch":
            continue
        if str(event_type) not in {"created", "edited"}:
            return {"status": "not_found", "persisted": False, "message": "Активная UTD-подписка не найдена."}
        metadata = {**metadata, "subscription_status": "cancelled", "cancellation_reason": "operator_confirmed_unsubscribe", "subscription_target_event_id": int(event_id), "subscription_target_memory_id": memory_id}
        return build_memory_proposal("watch_topic", {
            "operation": "delete", "target_memory_id": memory_id, "title": str(title),
            "body": "UTD subscription cancelled; queued sends must remain blocked.",
            "rationale": "Explicit unsubscribe; no collection or delivery may continue.",
            "source_refs": [], "metadata": metadata,
        })
    return {"status": "not_found", "persisted": False, "message": "Активная UTD-подписка не найдена."}


def confirm_utd_subscription_cancel(db_path: str | Path, proposal_result: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Persist only a caller-confirmed, still-current unsubscribe proposal."""
    proposal = proposal_result.get("proposal") if isinstance(proposal_result, Mapping) else None
    confirmation = proposal_result.get("confirmation") if isinstance(proposal_result, Mapping) else None
    if not isinstance(proposal, Mapping) or not isinstance(confirmation, Mapping):
        return {"status": "confirmation_required", "persisted": False, "message": "Сначала открой точный preview отмены."}
    if not _subscription_target_is_current(db_path, proposal):
        return {"status": "stale_subscription", "persisted": False, "write_performed": False, "message": "Профиль уже изменён. Открой новый preview перед подтверждением."}
    return confirm_memory_proposal(db_path, {
        "proposal": proposal, "confirmation_token": confirmation.get("token"),
        "confirmed_by": "telegram_operator", "confirmed_at": _iso(_as_utc(now)),
    })


def build_utd_subscription_pause_proposal(db_path: str | Path) -> dict[str, Any]:
    """Prepare an exact revision-bound pause edit, without persisting it."""
    cancel = build_utd_subscription_cancel_proposal(db_path)
    source = cancel.get("proposal") if isinstance(cancel, Mapping) else None
    if not isinstance(source, Mapping):
        return cancel
    metadata = source.get("metadata") if isinstance(source.get("metadata"), Mapping) else {}
    return build_memory_proposal("watch_topic", {
        "operation": "edit", "target_memory_id": source.get("target_memory_id"), "title": source.get("title"),
        "body": "UTD subscription paused; collection and queued delivery remain blocked until a newly confirmed active profile.",
        "rationale": "Explicit pause; no collection or delivery may continue.", "source_refs": [],
        "metadata": {**metadata, "subscription_status": "paused", "paused": True, "pause_reason": "operator_confirmed_pause"},
    })


def confirm_utd_subscription_pause(db_path: str | Path, proposal_result: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    proposal = proposal_result.get("proposal") if isinstance(proposal_result, Mapping) else None
    confirmation = proposal_result.get("confirmation") if isinstance(proposal_result, Mapping) else None
    if not isinstance(proposal, Mapping) or not isinstance(confirmation, Mapping):
        return {"status": "confirmation_required", "persisted": False, "message": "Сначала открой точный preview паузы."}
    if not _subscription_target_is_current(db_path, proposal):
        return {"status": "stale_subscription", "persisted": False, "write_performed": False, "message": "Профиль уже изменён. Открой новый preview перед подтверждением."}
    return confirm_memory_proposal(db_path, {"proposal": proposal, "confirmation_token": confirmation.get("token"), "confirmed_by": "telegram_operator", "confirmed_at": _iso(_as_utc(now))})


def start_utd_subscription_cancel(db_path: str | Path, *, chat_id: str, now: datetime | None = None) -> dict[str, Any]:
    """Persist an expiring, chat-bound preview; it is not the unsubscribe itself."""
    return _start_utd_subscription_preview(db_path, chat_id=chat_id, action="unsubscribe", now=now)


def start_utd_subscription_pause(db_path: str | Path, *, chat_id: str, now: datetime | None = None) -> dict[str, Any]:
    return _start_utd_subscription_preview(db_path, chat_id=chat_id, action="pause", now=now)


def _start_utd_subscription_preview(db_path: str | Path, *, chat_id: str, action: str, now: datetime | None = None) -> dict[str, Any]:
    current = _as_utc(now)
    proposal = build_utd_subscription_cancel_proposal(db_path) if action == "unsubscribe" else build_utd_subscription_pause_proposal(db_path)
    if proposal.get("status") != "needs_confirmation" or not chat_id:
        return proposal
    context_id = f"s{secrets.token_hex(5)}"
    try:
        with sqlite3.connect(db_path) as connection:
            if not _draft_schema_ready(connection):
                return _unavailable("Таблица безопасных confirmation preview недоступна.")
            connection.execute("""INSERT INTO prm_post_answer_proposals (context_id, chat_id_hash, summary_json, proposals_json, created_at, expires_at, status) VALUES (?, ?, ?, ?, ?, ?, ?)""", (context_id, _chat_hash(chat_id), json.dumps({"kind": "utd_subscription_lifecycle", "action": action, "target_event_id": proposal["proposal"]["metadata"]["subscription_target_event_id"]}, sort_keys=True), json.dumps({action: proposal}, sort_keys=True), _iso(current), _iso(current + UTD_DRAFT_TTL), "previewed"))
            connection.commit()
    except sqlite3.Error:
        return _unavailable("Не смог сохранить безопасный preview отмены.")
    label = "паузу" if action == "pause" else "отмену"
    return {**proposal, "context_id": context_id, "message": f"Preview {label} готов. Подтвердите именно это действие; оно не затронет более новую ревизию профиля.", "reply_markup": {"inline_keyboard": [[{"text": f"Подтвердить {label}", "callback_data": f"{UTD_SUBSCRIPTION_PREFIX}:{context_id}:confirm"}, {"text": "Не выполнять", "callback_data": f"{UTD_SUBSCRIPTION_PREFIX}:{context_id}:cancel"}]]}}


def handle_utd_subscription_callback(db_path: str | Path, callback_data: str, *, chat_id: str, now: datetime | None = None) -> dict[str, Any]:
    """Confirm/cancel only the exact persisted unsubscribe preview for its chat."""
    parts = str(callback_data or "").split(":")
    if len(parts) == 3 and parts[0] == UTD_SUBSCRIPTION_PREFIX and parts[2] == "preview" and parts[1] in {"pause", "cancel"}:
        return (start_utd_subscription_pause if parts[1] == "pause" else start_utd_subscription_cancel)(db_path, chat_id=chat_id, now=now)
    if len(parts) != 3 or parts[0] != UTD_SUBSCRIPTION_PREFIX or not parts[1] or parts[2] not in {"confirm", "cancel"} or len(callback_data) > 64:
        raise ValueError("Unsupported UTD subscription callback")
    current = _as_utc(now)
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute("SELECT chat_id_hash, summary_json, proposals_json, expires_at, status FROM prm_post_answer_proposals WHERE context_id = ?", (parts[1],)).fetchone()
            if row is None or row[0] != _chat_hash(chat_id):
                return {"status": "expired", "persisted": False, "message": "Preview истёк или принадлежит другому чату."}
            if datetime.fromisoformat(str(row[3]).replace("Z", "+00:00")) <= current or row[4] not in {"previewed", "confirming"}:
                return {"status": "expired", "persisted": False, "message": "Preview уже не действителен; открой новый."}
            if parts[2] == "cancel":
                cursor = connection.execute("UPDATE prm_post_answer_proposals SET summary_json='{}', proposals_json='{}', status='cancelled' WHERE context_id=? AND status='previewed'", (parts[1],))
                connection.commit()
                return {"status": "cancelled", "persisted": False, "write_performed": False, "message": "Отмена подписки не подтверждена; профиль не изменён."} if cursor.rowcount else {"status": "expired", "persisted": False, "message": "Preview уже подтверждается; отмена не изменила профиль."}
            action = ""
            try:
                summary = json.loads(str(row[1]))
                action = summary.get("action") if summary.get("kind") == "utd_subscription_lifecycle" else ""
                proposal = json.loads(str(row[2])).get(action)
            except json.JSONDecodeError:
                proposal = None
        if row[4] == "previewed" and not _claim_utd_preview(db_path, context_id=parts[1], chat_id=chat_id, now=current):
            return {"status": "expired", "persisted": False, "message": "Preview уже отменён или подтверждается; открой новый."}
        result = (confirm_utd_subscription_pause if action == "pause" else confirm_utd_subscription_cancel)(db_path, proposal if isinstance(proposal, Mapping) else {}, now=current)
        if result.get("persisted"):
            _finish_utd_preview_claim(db_path, context_id=parts[1], status="confirmed")
        else:
            _finish_utd_preview_claim(db_path, context_id=parts[1], status="previewed")
        return result
    except (sqlite3.Error, ValueError):
        return {"status": "expired", "persisted": False, "message": "Preview отмены недоступен; открой новый."}


def _claim_utd_preview(db_path: str | Path, *, context_id: str, chat_id: str, now: datetime) -> bool:
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute("UPDATE prm_post_answer_proposals SET status='confirming' WHERE context_id=? AND chat_id_hash=? AND status='previewed' AND expires_at > ?", (context_id, _chat_hash(chat_id), _iso(now)))
        return bool(cursor.rowcount)


def _finish_utd_preview_claim(db_path: str | Path, *, context_id: str, status: str) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE prm_post_answer_proposals SET status=? WHERE context_id=? AND status='confirming'", (status, context_id))


def _cancel_utd_preview(db_path: str | Path, *, context_id: str, chat_id: str) -> bool:
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute("UPDATE prm_post_answer_proposals SET summary_json='{}', proposals_json='{}', status='cancelled' WHERE context_id=? AND chat_id_hash=? AND status IN ('draft', 'previewed')", (context_id, _chat_hash(chat_id)))
        return bool(cursor.rowcount)


def _subscription_target_is_current(db_path: str | Path, proposal: Mapping[str, Any]) -> bool:
    metadata = proposal.get("metadata")
    if not isinstance(metadata, Mapping):
        return False
    target_memory_id = str(metadata.get("subscription_target_memory_id") or "")
    target_event_id = metadata.get("subscription_target_event_id")
    if not target_memory_id or not isinstance(target_event_id, int) or proposal.get("target_memory_id") != target_memory_id:
        return False
    try:
        with sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True) as connection:
            row = connection.execute("SELECT id,event_type,metadata_json FROM personal_memory_events WHERE memory_id=? ORDER BY id DESC LIMIT 1", (target_memory_id,)).fetchone()
    except sqlite3.Error:
        return False
    if row is None or int(row[0]) != target_event_id or str(row[1]) not in {"created", "edited"}:
        return False
    try:
        current_metadata = json.loads(str(row[2]))
    except (TypeError, json.JSONDecodeError):
        return False
    return current_metadata.get("capability") == "utd_profile_preview_watch"


def render_utd_question_preview(text: str, *, db_path: str | Path | None = None) -> str:
    category = classify_utd_question(text)
    profile = load_confirmed_utd_profile(db_path) if db_path is not None else None
    selected = bool(profile and category in profile.get("categories", []))
    if selected and bool(profile.get("paused")):
        profile_line = "Этот тип есть в подтверждённом профиле, но весь scope на паузе."
    elif selected and category in profile.get("muted_sources", []):
        profile_line = "Этот тип есть в профиле, но соответствующая source family muted."
    elif selected:
        profile_line = "Этот тип включён в подтверждённый scope; мониторинг всё равно выключен."
    else:
        profile_line = "Этот тип пока не включён в подтверждённый профиль."
    category_label = _CATEGORY_LABELS[category]
    caution = {
        "program": "Актуальный deadline требует свежей primary-source страницы.",
        "benefits": "Benefit или экономию нельзя обещать без актуальных eligibility и условий.",
        "spouse_family": "Событие нельзя считать доступным супруге/семье без явной eligibility.",
        "career": "Карьерное событие требует свежей даты, аудитории и registration status.",
        "ai": "AI/research событие требует свежей даты и официальной страницы организатора.",
        "isso": "ISSO-информация требует свежей официальной страницы и даты обновления.",
    }[category]
    return (
        "UTD ASK — безопасный preview\n\n"
        f"Распознано: {category_label}. {profile_line}\n"
        f"{caution}\n\n"
        "Этот ASK preview сам не запускает live fetch и не делает eligibility-выводы. "
        "Live UTD-источники/watch работают отдельно: только confirmed profile, allowlisted official "
        "sources, delivery gate, receipts и kill switch. Обычные вопросы по твоему "
        "AI-архиву продолжают работать как раньше."
    )


def _assert_non_executable_proposal(proposal: Mapping[str, Any]) -> None:
    metadata = proposal.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("UTD proposal metadata is required")
    if any(
        bool(metadata.get(field))
        for field in (
            "monitoring_authorized",
            "delivery_authorized",
            "provider_egress_authorized",
        )
    ):
        raise ValueError("UTD-1 proposal must remain non-executable")
    if metadata.get("source_status") != "preview_only":
        raise ValueError("UTD-1 source status must be preview_only")


def _parse_callback(callback_data: str) -> tuple[str, str, str]:
    parts = str(callback_data or "").split(":")
    if len(parts) != 3 or parts[0] not in {UTD_DRAFT_PREFIX, UTD_CONFIRM_PREFIX}:
        raise ValueError("Unsupported UTD callback")
    if not parts[1] or not parts[2] or len(callback_data) > 64:
        raise ValueError("Invalid UTD callback")
    return parts[0], parts[1], parts[2]


def _unavailable(message: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "profile_persisted": False,
        "write_performed": False,
        "draft_state_written": False,
        "message": message,
    }
