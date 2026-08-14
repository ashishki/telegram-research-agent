"""Deterministic secondary weekly recap from supplied PRM usage evidence."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


PRM_USAGE_WEEKLY_RECAP_SCHEMA_VERSION = "prm_usage_weekly_recap.v1"


class PRMUsageWeeklyRecapError(ValueError):
    pass


def build_prm_usage_weekly_recap(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a recap from explicit usage inputs; never query legacy reports or persist."""

    receipts = _mappings(payload.get("usage_receipts"))
    fixture_preview = bool(payload.get("fixture_preview_approved"))
    if not receipts and not fixture_preview:
        return _empty_recap()
    events = _mappings(payload.get("confirmed_memory_events"))
    reactions = _mappings(payload.get("reaction_summary"))
    useful = [item for item in receipts if item.get("useful") in {"yes", "partial"}]
    projects = [str(item.get("selected_project") or "").strip() for item in receipts if str(item.get("selected_project") or "").strip() not in {"", "unknown"}]
    return {
        "schema_version": PRM_USAGE_WEEKLY_RECAP_SCHEMA_VERSION,
        "status": "fixture_preview" if not receipts else "usage_evidence",
        "main_change": _main_change(receipts, useful),
        "action_study_watch_ignore": _action_item(events),
        "reaction_processing_summary": _reaction_summary(reactions),
        "project_connection": projects[0] if projects else "Нет подтвержденной связи с проектом.",
        "feedback_request": "Отметь: полезно, частично или мимо; это уточнит следующий recap.",
        "verification_summary": _verification_summary(receipts),
        "saved_knowledge_summary": f"Подтвержденных объектов: {len(events)}.",
        "evidence_boundary": "Это приватная агрегированная проекция usage evidence; не claim о ценности или dogfood.",
        "next_recap_boundary": "Нет автоматической доставки или schedule; следующий recap требует новых локальных evidence.",
        "usage_receipt_count": len(receipts),
        "confirmed_event_count": len(events),
        "legacy_report_inputs_used": False,
        "write_performed": False,
    }


def _empty_recap() -> dict[str, Any]:
    return {
        "schema_version": PRM_USAGE_WEEKLY_RECAP_SCHEMA_VERSION,
        "status": "no_usage_evidence",
        "main_change": "Нет usage evidence за период; изменения и полезность не заявляются.",
        "action_study_watch_ignore": _action_item([]), "reaction_processing_summary": _reaction_summary([]),
        "project_connection": "Нет подтвержденной связи с проектом.", "feedback_request": "Сначала появится подтвержденный operator feedback.",
        "verification_summary": "Нет данных о verification use.", "saved_knowledge_summary": "Подтвержденных объектов: 0.",
        "evidence_boundary": "Приватная агрегированная проекция без claims.", "next_recap_boundary": "Нет schedule или delivery.",
        "usage_receipt_count": 0, "confirmed_event_count": 0, "legacy_report_inputs_used": False, "write_performed": False,
    }


def _verification_summary(receipts: Sequence[Mapping[str, Any]]) -> str:
    required = sum(1 for item in receipts if item.get("external_verification_status") in {"required_not_run", "unavailable"})
    return "Verification gaps: " + str(required) + "."


def _main_change(receipts: Sequence[Mapping[str, Any]], useful: Sequence[Mapping[str, Any]]) -> str:
    if not receipts:
        return "Fixture preview: реальных операторских вопросов пока нет."
    return f"За неделю: {len(useful)} из {len(receipts)} ответов отмечены полезными или частично полезными."


def _action_item(events: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    if not events:
        return {"mode": "watch", "text": "Нет подтвержденных действий; оставить один вопрос на наблюдении."}
    event = events[0]
    return {
        "mode": str(event.get("proposal_type") or "action"),
        "text": str(event.get("title") or "Подтвержденное действие из операторского контекста."),
    }


def _reaction_summary(reactions: Sequence[Mapping[str, Any]]) -> str:
    if not reactions:
        return "Реакции за период не обработаны или не переданы в recap."
    count = sum(max(0, int(item.get("count") or 0)) for item in reactions)
    return f"Обработано реакций: {count}."


def _mappings(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [item for item in value if isinstance(item, Mapping)]
