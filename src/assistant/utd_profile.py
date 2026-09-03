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
            _set_draft_status(db_path, context_id, "confirmed")
            return {
                **result,
                "profile_persisted": True,
                "message": (
                    "UTD-профиль сохранён как подтверждённое намерение. "
                    "Само сохранение профиля не включает live-сбор, таймеры, модель или "
                    "Telegram-уведомления; это отдельный deployment gate с kill switch."
                ),
            }
        return {**result, "profile_persisted": False}

    if action == "cx":
        _set_draft_status(db_path, context_id, "cancelled")
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
