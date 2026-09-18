"""Confirmation-gated UTD profile and preview-watch UX.

UTD-1 deliberately stops at a local draft and a confirmed PRM memory event.
It never fetches UTD sources, starts timers, calls a model, or sends alerts.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone
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
    _load_draft,
    _save_draft,
    create_utd_proposal,
    load_confirmed_utd_profile,
    load_utd_proposal,
    transition_utd_context,
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
    seed = _parse_seed(seed_text)
    draft.update(seed)
    # A field supplied in the start message is an explicit selection; defaults
    # are not.  This keeps the blank onboarding safe without discarding a
    # concise operator-provided setup request.
    selected_from_seed = [
        category
        for field, category in (("program", "program"), ("career_goals", "career"), ("ai_interests", "ai"))
        if field in seed
    ]
    if selected_from_seed:
        draft["categories"] = selected_from_seed
    context_id = f"u{secrets.token_hex(5)}"
    created = create_utd_proposal(
        db_file,
        context_id=context_id,
        chat_id=chat_id,
        summary={"kind": "utd_profile_draft", "draft": draft},
        proposals={},
        created_at=_iso(current),
        expires_at=_iso(current + UTD_DRAFT_TTL),
        state="draft",
    )
    if not created.applied:
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
                "message": "Сначала открой предпросмотр, затем подтверждай сохранение.",
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
                _finish_utd_preview_claim(db_path, context_id=context_id, chat_id=chat_id, status="confirmed")
            return {**recovered, "profile_persisted": bool(recovered.get("persisted"))}
        if not _claim_utd_preview(db_path, context_id=context_id, chat_id=chat_id, now=current):
            return {"status": "expired", "profile_persisted": False, "write_performed": False, "message": "Предпросмотр уже отменён или подтверждается; открой новый."}
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
            _finish_utd_preview_claim(db_path, context_id=context_id, chat_id=chat_id, status="confirmed")
            return {
                **result,
                "profile_persisted": True,
                "message": (
                    "Профиль UTD сохранён. Уведомления сейчас выключены. "
                    "Сохранение профиля само по себе не запускает поиск, расписание или отправку. "
                    "Когда уведомления будут отдельно включены, они будут использовать эти подтверждённые настройки."
                ),
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "Поставить UTD-подписку на паузу", "callback_data": f"{UTD_SUBSCRIPTION_PREFIX}:pause:preview"}],
                        [{"text": "Отменить UTD-подписку", "callback_data": f"{UTD_SUBSCRIPTION_PREFIX}:cancel:preview"}],
                    ]
                },
            }
        _finish_utd_preview_claim(db_path, context_id=context_id, chat_id=chat_id, status="previewed")
        return {**result, "profile_persisted": False}

    if action == "cx":
        if status not in {"draft", "previewed"} or not _cancel_utd_preview(
            db_path, context_id=context_id, chat_id=chat_id, expected=status,
        ):
            return {"status": "expired", "profile_persisted": False, "write_performed": False, "message": "Предпросмотр уже подтверждается; отмена не изменила профиль."}
        return {
            "status": "cancelled",
            "profile_persisted": False,
            "write_performed": False,
            "message": "UTD-черновик отменён. Постоянный профиль не изменён.",
        }
    if action == "pv":
        if not _normalize_draft(draft)["categories"]:
            return {
                "status": "needs_category_selection",
                "profile_persisted": False,
                "write_performed": False,
                "message": "Сначала выбери хотя бы одну тему. ISSO и семья включаются только по явному выбору.",
                "reply_markup": _onboarding_markup(context_id, draft),
            }
        proposal_result = build_utd_watch_proposal(draft)
        proposals = {"utd_profile": proposal_result}
        transition = _save_draft(
            db_path, context_id, chat_id=chat_id, expected=status,
            draft=draft, proposals=proposals, state="previewed",
        )
        if not transition.applied:
            return {"status": "expired", "profile_persisted": False, "write_performed": False, "message": "Предпросмотр уже изменён; открой новый."}
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
        if status == "previewed":
            transition = _save_draft(
                db_path, context_id, chat_id=chat_id, expected="previewed",
                draft=draft, proposals={}, state="draft",
            )
            if not transition.applied:
                return {"status": "expired", "profile_persisted": False, "write_performed": False, "message": "Предпросмотр уже изменён; открой новый."}
        elif status != "draft":
            return {"status": "expired", "profile_persisted": False, "write_performed": False, "message": "Предпросмотр уже подтверждается; открой новый."}
        return {
            "status": "draft_updated",
            "profile_persisted": status == "confirmed",
            "write_performed": False,
            "message": render_utd_onboarding(draft),
            "reply_markup": _onboarding_markup(context_id, draft),
        }

    _apply_draft_action(draft, action, current)
    transition = _save_draft(
        db_path, context_id, chat_id=chat_id, expected=status,
        draft=draft, proposals={}, state="draft",
    )
    if not transition.applied:
        return {"status": "expired", "profile_persisted": False, "write_performed": False, "message": "Черновик уже изменён; начни настройку заново."}
    return {
        "status": "draft_updated",
        "profile_persisted": False,
        "write_performed": False,
        "message": render_utd_onboarding(draft),
        "reply_markup": _onboarding_markup(context_id, draft),
    }


def build_utd_watch_proposal(draft: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize_draft(draft)
    if not normalized["categories"]:
        raise ValueError("UTD profile requires at least one explicitly selected category")
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
            "title": "Профиль UTD и предпросмотр уведомлений",
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
        return {"status": "confirmation_required", "persisted": False, "message": "Сначала открой точный предпросмотр отмены."}
    if not _subscription_target_is_current(db_path, proposal):
        return {"status": "stale_subscription", "persisted": False, "write_performed": False, "message": "Профиль уже изменён. Открой новый предпросмотр перед подтверждением."}
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
        return {"status": "confirmation_required", "persisted": False, "message": "Сначала открой точный предпросмотр паузы."}
    if not _subscription_target_is_current(db_path, proposal):
        return {"status": "stale_subscription", "persisted": False, "write_performed": False, "message": "Профиль уже изменён. Открой новый предпросмотр перед подтверждением."}
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
    created = create_utd_proposal(
        db_path,
        context_id=context_id,
        chat_id=chat_id,
        summary={
            "kind": "utd_subscription_lifecycle",
            "action": action,
            "target_event_id": proposal["proposal"]["metadata"]["subscription_target_event_id"],
        },
        proposals={action: proposal},
        created_at=_iso(current),
        expires_at=_iso(current + UTD_DRAFT_TTL),
        state="previewed",
    )
    if not created.applied:
        return _unavailable("Не смог сохранить безопасный предпросмотр отмены.")
    label = "паузу" if action == "pause" else "отмену подписки"
    message = (
        "Нужно подтверждение паузы. Уведомления остановятся; подтверждённый профиль останется сохранённым."
        if action == "pause"
        else "Нужно подтверждение отмены подписки. Подтверждённый профиль и будущие уведомления будут отключены."
    )
    return {
        **proposal,
        "context_id": context_id,
        "message": message + " Это действие не затронет более новую версию профиля.",
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": f"Подтвердить {label}", "callback_data": f"{UTD_SUBSCRIPTION_PREFIX}:{context_id}:confirm"},
                    {"text": "Не выполнять", "callback_data": f"{UTD_SUBSCRIPTION_PREFIX}:{context_id}:cancel"},
                ]
            ]
        },
    }


def handle_utd_subscription_callback(db_path: str | Path, callback_data: str, *, chat_id: str, now: datetime | None = None) -> dict[str, Any]:
    """Confirm/cancel only the exact persisted unsubscribe preview for its chat."""
    parts = str(callback_data or "").split(":")
    if len(parts) == 3 and parts[0] == UTD_SUBSCRIPTION_PREFIX and parts[2] == "preview" and parts[1] in {"pause", "cancel"}:
        return (start_utd_subscription_pause if parts[1] == "pause" else start_utd_subscription_cancel)(db_path, chat_id=chat_id, now=now)
    if len(parts) != 3 or parts[0] != UTD_SUBSCRIPTION_PREFIX or not parts[1] or parts[2] not in {"confirm", "cancel"} or len(callback_data) > 64:
        raise ValueError("Unsupported UTD subscription callback")
    current = _as_utc(now)
    stored = load_utd_proposal(db_path, context_id=parts[1], chat_id=chat_id, now=current)
    if stored is None or stored.summary.get("kind") != "utd_subscription_lifecycle":
        return {"status": "expired", "persisted": False, "message": "Предпросмотр истёк или принадлежит другому чату."}
    if stored.logical_state not in {"previewed", "confirming"}:
        return {"status": "expired", "persisted": False, "message": "Предпросмотр уже не действителен; открой новый."}
    if parts[2] == "cancel":
        if stored.logical_state != "previewed" or not _cancel_utd_preview(
            db_path, context_id=parts[1], chat_id=chat_id, expected="previewed",
        ):
            return {"status": "expired", "persisted": False, "message": "Предпросмотр уже подтверждается; отмена не изменила профиль."}
        return {"status": "cancelled", "persisted": False, "write_performed": False, "message": "Отмена подписки не подтверждена; профиль не изменён."}
    action = str(stored.summary.get("action") or "")
    proposal = stored.proposals.get(action)
    if stored.logical_state == "previewed" and not _claim_utd_preview(db_path, context_id=parts[1], chat_id=chat_id, now=current):
        return {"status": "expired", "persisted": False, "message": "Предпросмотр уже отменён или подтверждается; открой новый."}
    try:
        result = (confirm_utd_subscription_pause if action == "pause" else confirm_utd_subscription_cancel)(db_path, proposal if isinstance(proposal, Mapping) else {}, now=current)
        if result.get("persisted"):
            _finish_utd_preview_claim(db_path, context_id=parts[1], chat_id=chat_id, status="confirmed")
        else:
            _finish_utd_preview_claim(db_path, context_id=parts[1], chat_id=chat_id, status="previewed")
        return result
    except (sqlite3.Error, ValueError):
        _finish_utd_preview_claim(db_path, context_id=parts[1], chat_id=chat_id, status="previewed")
        return {"status": "expired", "persisted": False, "message": "Предпросмотр отмены недоступен; открой новый."}


def _claim_utd_preview(db_path: str | Path, *, context_id: str, chat_id: str, now: datetime) -> bool:
    stored = load_utd_proposal(db_path, context_id=context_id, chat_id=chat_id, now=now)
    if stored is None or stored.logical_state != "previewed" or stored.expires_at <= now:
        return False
    return transition_utd_context(
        db_path, context_id=context_id, chat_id=chat_id, expected="previewed", next_state="confirming",
    ).applied


def _finish_utd_preview_claim(
    db_path: str | Path, *, context_id: str, chat_id: str, status: str,
) -> None:
    transition_utd_context(
        db_path, context_id=context_id, chat_id=chat_id, expected="confirming", next_state=status,
    )


def _cancel_utd_preview(
    db_path: str | Path, *, context_id: str, chat_id: str, expected: str,
) -> bool:
    stored = load_utd_proposal(db_path, context_id=context_id, chat_id=chat_id, now=datetime.min.replace(tzinfo=timezone.utc))
    if stored is None or stored.logical_state != expected:
        return False
    return transition_utd_context(
        db_path,
        context_id=context_id,
        chat_id=chat_id,
        expected=expected,
        next_state="cancelled",
        summary={"kind": stored.summary["kind"]},
        proposals={},
    ).applied


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
        profile_line = "Этот тип есть в подтверждённом профиле, но уведомления поставлены на паузу."
    elif selected and category in profile.get("muted_sources", []):
        profile_line = "Этот тип есть в профиле, но его источник скрыт."
    elif selected:
        profile_line = "Этот тип включён в подтверждённый профиль; уведомления сейчас выключены."
    else:
        profile_line = "Этот тип пока не включён в подтверждённый профиль."
    category_label = _CATEGORY_LABELS[category]
    caution = {
        "program": "Для актуального срока нужна свежая официальная страница.",
        "benefits": "Нельзя обещать льготу или экономию без актуальных условий доступности.",
        "spouse_family": "Нельзя считать событие доступным семье без явного указания условий.",
        "career": "Для карьерного события нужны свежие дата, аудитория и условия регистрации.",
        "ai": "Для AI/исследовательского события нужны свежая дата и официальная страница организатора.",
        "isso": "ISSO-информация требует свежей официальной страницы и даты обновления.",
    }[category]
    return (
        "UTD — безопасный предпросмотр\n\n"
        f"Распознано: {category_label}. {profile_line}\n"
        f"{caution}\n\n"
        "Свежие UTD-источники сейчас не проверялись, поэтому я не называю дату, доступность или "
        "условия как факт. Этот вопрос не меняет профиль и не включает уведомления. Обычные вопросы "
        "по твоему AI-архиву продолжают работать как раньше."
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
