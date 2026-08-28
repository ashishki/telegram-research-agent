"""Shadow-only candidate selection for future digest UX."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

CHANGE_WEIGHT = {"cancelled": 50, "reinstated": 45, "updated": 35, "new": 20, "disappeared": 0}


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
        if key not in best or rank > best[key][0]:
            best[key] = (rank, candidate)
    ordered = sorted(best.values(), key=lambda pair: pair[0], reverse=True)
    return [candidate for _, candidate in ordered[:cap]]
