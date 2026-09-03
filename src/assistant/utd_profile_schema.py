"""Pure UTD-1 profile contract, rendering, and draft transformations."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping


UTD_DRAFT_PREFIX = "utdp"
UTD_CONFIRM_PREFIX = "utdc"
UTD_PROFILE_SCHEMA_VERSION = "utd_profile.v1"
UTD_WATCH_SCHEMA_VERSION = "utd_watch_preview.v1"
UTD_TIMEZONE = "America/Chicago"
UTD_DRAFT_TTL = timedelta(minutes=30)
DEFAULT_EXPIRY_DAYS = 120
DEFAULT_DAILY_CAP = 5

_CATEGORY_LABELS = {
    "program": "программа и академические сроки",
    "career": "карьера",
    "ai": "AI / engineering",
    "isso": "ISSO и статус",
    "benefits": "benefits / basic needs",
    "spouse_family": "супруга / семья",
}
_CATEGORY_CODES = {
    "pg": "program",
    "ca": "career",
    "ai": "ai",
    "is": "isso",
    "be": "benefits",
    "sf": "spouse_family",
}
_SHORT_LABELS = {
    "program": "Программа",
    "career": "Карьера",
    "ai": "AI",
    "isso": "ISSO",
    "benefits": "Benefits",
    "spouse_family": "Семья",
}
_SOURCE_FAMILIES = {
    "program": "публичные academic/program pages UTD",
    "career": "публичные события и материалы UTD Career Center",
    "ai": "публичные AI/engineering/research события UTD",
    "isso": "публичные страницы и объявления ISSO",
    "benefits": "публичные Basic Needs и benefit-ресурсы UTD",
    "spouse_family": "публичные события с явно указанной spouse/family eligibility",
}
_FREQUENCIES = ("daily_digest", "weekly_digest", "urgent_only")
_FREQUENCY_LABELS = {
    "daily_digest": "один дневной digest",
    "weekly_digest": "один недельный digest",
    "urgent_only": "только подтверждённо срочное",
}
_CAP_VALUES = (5, 3, 1)
_EXPIRY_VALUES = (120, 90, 30, 180)



def is_utd_profile_intent(text: str) -> bool:
    normalized = " ".join(str(text or "").casefold().split())
    return normalized.startswith("/utd") or any(
        phrase in normalized
        for phrase in (
            "настроить мой utd-профиль",
            "настроить utd-профиль",
            "настроить профиль utd",
            "set up my utd profile",
        )
    )


def is_utd_question(text: str) -> bool:
    normalized = " ".join(str(text or "").casefold().split())
    if is_utd_profile_intent(normalized):
        return False
    return any(marker in normalized for marker in ("utd", "ut dallas", "isso", "comet calendar"))


def render_utd_onboarding(draft: Mapping[str, Any]) -> str:
    normalized = _normalize_draft(draft)
    selected = ", ".join(_CATEGORY_LABELS[item] for item in normalized["categories"])
    return (
        "Что тебе важно в UTD: программа, карьера, AI, ISSO, benefits или spouse/family?\n\n"
        f"Сейчас выбрано: {selected or 'ничего'}.\n"
        f"Программа: {normalized['program']}\n"
        f"Карьера: {normalized['career_goals']}\n"
        f"AI: {normalized['ai_interests']}\n\n"
        "Это только локальный черновик на 30 минут. Кнопки меняют preview, но не профиль. "
        "Постоянная запись появится только после отдельной кнопки подтверждения."
    )


def render_utd_watch_preview(draft: Mapping[str, Any]) -> str:
    normalized = _normalize_draft(draft)
    sources = _selected_sources(normalized)
    source_lines = [
        f"• {source}{' — muted' if category in normalized['muted_sources'] else ''}"
        for category, source in sources.items()
    ]
    categories = ", ".join(_CATEGORY_LABELS[item] for item in normalized["categories"])
    positives = ", ".join(_positive_terms(normalized))
    negatives = ", ".join(_negative_terms())
    state = (
        "scope сохранён в паузе; мониторинг выключен"
        if normalized["paused"]
        else "scope готов к сохранению; мониторинг выключен"
    )
    return (
        "UTD WATCH — preview перед сохранением\n\n"
        f"Что важно: {categories or 'ничего не выбрано'}\n"
        f"Программа: {normalized['program']}\n"
        f"Карьерный фокус: {normalized['career_goals']}\n"
        f"AI-фокус: {normalized['ai_interests']}\n"
        f"Аудитория: {normalized['audience_context']}\n\n"
        "Источники (только названия будущих source families; сейчас не подключены):\n"
        f"{chr(10).join(source_lines) if source_lines else '• нет выбранных источников'}\n\n"
        f"Позитивные фильтры: {positives}\n"
        f"Негативные фильтры: {negatives}\n"
        "Spouse/family: подходит только событие с явно указанной eligibility; "
        "догадки запрещены.\n\n"
        f"Timezone: {UTD_TIMEZONE}\n"
        f"Частота: {_FREQUENCY_LABELS[normalized['frequency']]}\n"
        f"Лимит: не более {normalized['daily_cap']} элементов в день\n"
        f"Expiry/review: {normalized['expires_at']}\n"
        f"Состояние: {state}\n"
        f"Muted source families: {', '.join(normalized['muted_sources']) or 'нет'}\n\n"
        "Граница: этот profile preview сам не делает live fetch, не запускает timer, "
        "не отправляет Telegram delivery и не включает provider egress. Runtime watch "
        "управляется отдельным deployment gate и kill switch. Подтверждение сохраняет "
        "только персональный UTD scope."
    )


def classify_utd_question(text: str) -> str:
    normalized = " ".join(str(text or "").casefold().split())
    rules = (
        ("spouse_family", ("spouse", "супруг", "семь", "f-2", "f2")),
        ("benefits", ("benefit", "льгот", "скидк", "basic needs", "помощ")),
        ("career", ("career", "карьер", "intern", "стажиров", "on-campus", "job fair")),
        ("ai", (" ai ", "искусственн", "agent", "rag", "research", "исследован")),
        ("isso", ("isso", "i-20", "sevis", "immigration", "status")),
        ("program", ("deadline", "дедлайн", "срок", "registration", "регистрац", "program")),
    )
    padded = f" {normalized} "
    for category, markers in rules:
        if any(marker in padded for marker in markers):
            return category
    return "program"


def _default_draft(now: datetime) -> dict[str, Any]:
    return {
        "schema_version": UTD_PROFILE_SCHEMA_VERSION,
        "program": os.environ.get("UTD_PROGRAM_NAME", "моя программа UTD").strip()
        or "моя программа UTD",
        "career_goals": os.environ.get(
            "UTD_CAREER_INTERESTS",
            "internships, on-campus opportunities и AI/engineering career events",
        ).strip(),
        "ai_interests": os.environ.get(
            "UTD_AI_INTERESTS",
            "applied AI, agentic systems, RAG, evals и engineering research",
        ).strip(),
        "audience_context": os.environ.get(
            "UTD_AUDIENCE_CONTEXT",
            "student; spouse/family only when eligibility is explicit",
        ).strip(),
        "categories": list(_CATEGORY_LABELS),
        "frequency": "daily_digest",
        "daily_cap": DEFAULT_DAILY_CAP,
        "review_after_days": DEFAULT_EXPIRY_DAYS,
        "expires_at": _iso(now + timedelta(days=DEFAULT_EXPIRY_DAYS)),
        "paused": False,
        "muted_sources": [],
    }


def _parse_seed(seed_text: str) -> dict[str, str]:
    text = str(seed_text or "").strip()
    if text.casefold().startswith("/utd"):
        text = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) == 2 else ""
    if ":" in text and "=" not in text.split(":", 1)[0]:
        text = text.split(":", 1)[1]
    aliases = {
        "программа": "program",
        "program": "program",
        "карьера": "career_goals",
        "career": "career_goals",
        "ai": "ai_interests",
        "ии": "ai_interests",
        "аудитория": "audience_context",
        "audience": "audience_context",
        "семья": "audience_context",
    }
    parsed: dict[str, str] = {}
    for part in text.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        field = aliases.get(key.strip().casefold())
        clean_value = " ".join(value.split())[:240]
        if field and clean_value:
            parsed[field] = clean_value
    return parsed


def _apply_draft_action(draft: dict[str, Any], action: str, now: datetime) -> None:
    if action in _CATEGORY_CODES:
        category = _CATEGORY_CODES[action]
        categories = list(draft.get("categories") or [])
        if category in categories:
            categories.remove(category)
        else:
            categories.append(category)
        draft["categories"] = [item for item in _CATEGORY_LABELS if item in categories]
        return
    if action == "fr":
        draft["frequency"] = _cycle(_FREQUENCIES, str(draft.get("frequency")))
        return
    if action == "cp":
        draft["daily_cap"] = _cycle(_CAP_VALUES, int(draft.get("daily_cap") or 5))
        return
    if action == "ex":
        days = _cycle(_EXPIRY_VALUES, int(draft.get("review_after_days") or 120))
        draft["review_after_days"] = days
        draft["expires_at"] = _iso(now + timedelta(days=days))
        return
    if action == "ps":
        draft["paused"] = not bool(draft.get("paused"))
        return
    if action in {"mi", "mf"}:
        source = "isso" if action == "mi" else "spouse_family"
        muted = list(draft.get("muted_sources") or [])
        if source in muted:
            muted.remove(source)
        else:
            muted.append(source)
        draft["muted_sources"] = [item for item in _CATEGORY_LABELS if item in muted]
        return
    raise ValueError("Unsupported UTD draft action")


def _onboarding_markup(context_id: str, draft: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize_draft(draft)
    rows: list[list[dict[str, str]]] = []
    category_buttons = []
    for code, category in _CATEGORY_CODES.items():
        selected = category in normalized["categories"]
        category_buttons.append(
            {
                "text": f"{'✅' if selected else '○'} {_SHORT_LABELS[category]}",
                "callback_data": f"{UTD_DRAFT_PREFIX}:{context_id}:{code}",
            }
        )
    for index in range(0, len(category_buttons), 2):
        rows.append(category_buttons[index : index + 2])
    rows.extend(
        [
            [
                {
                    "text": f"Частота: {_frequency_short(normalized['frequency'])}",
                    "callback_data": f"{UTD_DRAFT_PREFIX}:{context_id}:fr",
                },
                {
                    "text": f"Лимит: {normalized['daily_cap']}",
                    "callback_data": f"{UTD_DRAFT_PREFIX}:{context_id}:cp",
                },
            ],
            [
                {
                    "text": f"Expiry: {normalized['review_after_days']} дн.",
                    "callback_data": f"{UTD_DRAFT_PREFIX}:{context_id}:ex",
                },
                {
                    "text": f"Пауза: {'да' if normalized['paused'] else 'нет'}",
                    "callback_data": f"{UTD_DRAFT_PREFIX}:{context_id}:ps",
                },
            ],
            [
                {
                    "text": (
                        "Mute ISSO: да"
                        if "isso" in normalized["muted_sources"]
                        else "Mute ISSO: нет"
                    ),
                    "callback_data": f"{UTD_DRAFT_PREFIX}:{context_id}:mi",
                },
                {
                    "text": (
                        "Mute family: да"
                        if "spouse_family" in normalized["muted_sources"]
                        else "Mute family: нет"
                    ),
                    "callback_data": f"{UTD_DRAFT_PREFIX}:{context_id}:mf",
                },
            ],
            [
                {
                    "text": "Показать preview",
                    "callback_data": f"{UTD_DRAFT_PREFIX}:{context_id}:pv",
                },
                {
                    "text": "Отмена",
                    "callback_data": f"{UTD_DRAFT_PREFIX}:{context_id}:cx",
                },
            ],
        ]
    )
    return {"inline_keyboard": rows}


def _normalize_draft(raw: Mapping[str, Any]) -> dict[str, Any]:
    selected_categories = {str(value) for value in raw.get("categories") or []}
    categories = [item for item in _CATEGORY_LABELS if item in selected_categories]
    muted = [
        item
        for item in _CATEGORY_LABELS
        if item in {str(value) for value in raw.get("muted_sources") or []}
    ]
    frequency = str(raw.get("frequency") or "daily_digest")
    if frequency not in _FREQUENCIES:
        frequency = "daily_digest"
    daily_cap = int(raw.get("daily_cap") or DEFAULT_DAILY_CAP)
    if daily_cap not in _CAP_VALUES:
        daily_cap = DEFAULT_DAILY_CAP
    review_after_days = int(raw.get("review_after_days") or DEFAULT_EXPIRY_DAYS)
    if review_after_days not in _EXPIRY_VALUES:
        review_after_days = DEFAULT_EXPIRY_DAYS
    return {
        "schema_version": UTD_PROFILE_SCHEMA_VERSION,
        "program": _bounded(raw.get("program"), "моя программа UTD"),
        "career_goals": _bounded(raw.get("career_goals"), "карьерные события UTD"),
        "ai_interests": _bounded(raw.get("ai_interests"), "AI / engineering"),
        "audience_context": _bounded(
            raw.get("audience_context"),
            "student; spouse/family only when eligibility is explicit",
        ),
        "categories": categories,
        "frequency": frequency,
        "daily_cap": daily_cap,
        "review_after_days": review_after_days,
        "expires_at": _canonical_timestamp(raw.get("expires_at")),
        "paused": bool(raw.get("paused")),
        "muted_sources": muted,
    }


def _selected_sources(draft: Mapping[str, Any]) -> dict[str, str]:
    return {
        category: _SOURCE_FAMILIES[category]
        for category in draft.get("categories") or []
        if category in _SOURCE_FAMILIES
    }


def _positive_terms(draft: Mapping[str, Any]) -> list[str]:
    terms: list[str] = []
    mapping = {
        "program": ["deadline", "registration", "degree requirement", "academic calendar"],
        "career": ["internship", "on-campus", "career fair", "workshop"],
        "ai": ["AI", "machine learning", "agent", "RAG", "research seminar"],
        "isso": ["ISSO", "I-20", "SEVIS", "international student"],
        "benefits": ["basic needs", "benefit", "student resource"],
        "spouse_family": ["spouse eligible", "family welcome", "guest allowed"],
    }
    for category in draft.get("categories") or []:
        terms.extend(mapping.get(str(category), []))
    return list(dict.fromkeys(terms))[:24]


def _negative_terms() -> list[str]:
    return [
        "past event",
        "duplicate",
        "alumni-only",
        "faculty-only",
        "unsupported benefit claim",
        "spouse/family eligibility not stated",
    ]


def _cycle(values: tuple[Any, ...], current: Any) -> Any:
    try:
        index = values.index(current)
    except ValueError:
        return values[0]
    return values[(index + 1) % len(values)]


def _frequency_short(value: str) -> str:
    return {"daily_digest": "день", "weekly_digest": "неделя", "urgent_only": "urgent"}[value]


def _canonical_timestamp(value: object) -> str:
    if isinstance(value, datetime):
        return _iso(_as_utc(value))
    text = str(value or "").strip()
    if not text:
        raise ValueError("expires_at is required")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return _iso(_as_utc(parsed))


def _as_utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _bounded(value: object, fallback: str, limit: int = 240) -> str:
    clean = " ".join(str(value or "").split())[:limit]
    return clean or fallback
