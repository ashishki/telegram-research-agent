"""Shadow-only candidate selection for future digest UX."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

CHANGE_WEIGHT = {"cancelled": 50, "reinstated": 45, "updated": 35, "new": 20, "disappeared": 0}


def rank_edition_events(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Editorial ordering for an explicit edition; no cap, write or delivery."""
    eligible = []
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
        relevance = payload.get("relevance") if isinstance(payload.get("relevance"), Mapping) else {}
        if relevance.get("relevant") is False:
            continue
        eligible.append(dict(event))
    return sorted(
        eligible,
        key=lambda event: (
            bool(((event.get("payload") or {}).get("relevance") or {}).get("urgent")),
            int((((event.get("payload") or {}).get("relevance") or {}).get("score") or 0) + CHANGE_WEIGHT.get(str(event.get("change_type") or ""), 0)),
            str(event.get("update_at") or ""), str(event.get("event_id") or ""),
        ),
        reverse=True,
    )


def select_candidates(changes: Sequence[Mapping[str, Any]], profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return at most the confirmed daily cap; performs no delivery."""
    if profile.get("paused"):
        return []
    cap = max(1, min(int(profile.get("daily_cap") or 5), 5))
    urgent_only = str(profile.get("frequency") or "") == "urgent_only"
    best: dict[str, tuple[tuple[int, int, str], dict[str, Any]]] = {}
    for raw in changes:
        rel = raw.get("relevance") if isinstance(raw.get("relevance"), Mapping) else {}
        if not rel.get("relevant"):
            continue
        if urgent_only and not rel.get("urgent"):
            continue
        change_type = str(raw.get("change_type") or "")
        if change_type == "disappeared":
            continue
        key = str(raw.get("item_key") or "")
        rank = (
            1 if rel.get("urgent") else 0,
            int(rel.get("score") or 0) + CHANGE_WEIGHT.get(change_type, 0),
            key,
        )
        candidate = {
            "source": raw.get("source"),
            "item_key": key,
            "change_type": change_type,
            "relevance": dict(rel),
            "payload": dict(raw.get("payload") or {}),
        }
        # A durable source change is classified against one exact confirmed
        # profile revision.  Never let selection erase that provenance: the
        # final outbox boundary must be able to fail closed after an edit.
        if raw.get("subscription_memory_id"):
            candidate["subscription_memory_id"] = str(raw["subscription_memory_id"])
        if raw.get("subscription_event_id") is not None:
            candidate["subscription_event_id"] = raw["subscription_event_id"]
        if key not in best or rank > best[key][0]:
            best[key] = (rank, candidate)
    ordered = sorted(best.values(), key=lambda pair: pair[0], reverse=True)
    return [candidate for _, candidate in ordered[:cap]]
