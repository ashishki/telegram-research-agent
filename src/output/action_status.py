from __future__ import annotations

from typing import Any, Iterable, Mapping


ACTION_STATUS_VALUES = {
    "read",
    "tried",
    "applied_to_project",
    "deferred",
    "wrong_priority",
    "not_interested",
    "unknown",
}

def build_action_status_projection(
    workbook: Mapping[str, Any] | None,
    feedback_events: Iterable[Mapping[str, Any]] | None = None,
) -> list[dict]:
    """Project workbook action cards into stable action-status DTOs."""
    action_cards = [
        card
        for card in (workbook or {}).get("action_cards") or []
        if isinstance(card, Mapping)
    ]
    events = [event for event in feedback_events or [] if isinstance(event, Mapping)]
    items: list[dict] = []
    for index, card in enumerate(action_cards, start=1):
        action_id = _clean_text(card.get("id")) or f"action-{index}"
        target_ref = _clean_text(card.get("target_ref")) or action_id
        feedback_target_id = _clean_text(card.get("feedback_target_id"))
        matched_events = _matching_events(events, action_id, target_ref, feedback_target_id)
        feedback_types = _unique(
            _clean_text(event.get("feedback_type"))
            for event in matched_events
            if _clean_text(event.get("feedback_type"))
        )
        items.append(
            {
                "action_id": action_id,
                "target_ref": target_ref,
                "feedback_target_id": feedback_target_id,
                "title": _clean_text(card.get("title")) or action_id,
                "action_kind": _clean_text(card.get("action_kind")) or _clean_text(card.get("scope")) or None,
                "status": _status_from_feedback_types(feedback_types),
                "feedback_types": feedback_types,
                "latest_feedback_at": _latest_value(event.get("created_at") for event in matched_events),
                "source_refs": _unique(
                    _clean_text(event.get("source_url"))
                    for event in matched_events
                    if _clean_text(event.get("source_url"))
                ),
                "outcome_policy": _clean_text(card.get("outcome_policy")),
                "follow_up_hint": _clean_text(card.get("follow_up_hint")),
            }
        )
    return items


def summarize_action_statuses(items: Iterable[Mapping[str, Any]]) -> dict:
    counts = {status: 0 for status in sorted(ACTION_STATUS_VALUES)}
    for item in items:
        status = _clean_text(item.get("status")) or "unknown"
        counts[status if status in ACTION_STATUS_VALUES else "unknown"] += 1
    return counts


def _matching_events(
    events: list[Mapping[str, Any]],
    action_id: str,
    target_ref: str,
    feedback_target_id: str | None,
) -> list[Mapping[str, Any]]:
    refs = {action_id, target_ref}
    if feedback_target_id:
        refs.add(feedback_target_id)
    result = []
    for event in events:
        event_ref = _clean_text(event.get("target_ref"))
        event_type = _clean_text(event.get("target_type"))
        if event_ref in refs:
            result.append(event)
            continue
        if event_type == "action" and event_ref is None and action_id == "action-1":
            result.append(event)
    return result


def _status_from_feedback_types(feedback_types: list[str]) -> str:
    if "applied_to_project" in feedback_types:
        return "applied_to_project"
    if "tried" in feedback_types:
        return "tried"
    if "read" in feedback_types:
        return "read"
    if "wrong_priority" in feedback_types:
        return "wrong_priority"
    if "not_interested" in feedback_types or "noise" in feedback_types:
        return "not_interested"
    if "deferred" in feedback_types:
        return "deferred"
    return "unknown"


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _latest_value(values: Iterable[Any]) -> str | None:
    clean_values = sorted(str(value).strip() for value in values if str(value or "").strip())
    return clean_values[-1] if clean_values else None


def _unique(values: Iterable[Any]) -> list:
    result = []
    seen = set()
    for value in values:
        if value is None:
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
