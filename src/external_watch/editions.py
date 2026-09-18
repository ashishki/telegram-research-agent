"""Pure event/edition projection for the future on-demand news digest."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


def project_edition(items: Sequence[Mapping[str, Any]], *, topic_id: str, window_start: str, window_end: str, checked_at: str, prior_events: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Build a deterministic, write-free edition with distinct time fields."""
    start_at, end_at = _parse_time(window_start), _parse_time(window_end)
    valid_window = start_at is not None and end_at is not None and start_at <= end_at
    events: dict[str, dict[str, Any]] = {}
    rejected_invalid_time_count = 0
    for item in items:
        observed = str(item.get("updated_at") or item.get("published_at") or "")
        in_window = _within_window(observed, start_at, end_at) if valid_window else None
        if in_window is False:
            continue
        if in_window is None:
            rejected_invalid_time_count += 1
            continue
        source = str(item.get("source") or "calendar")
        canonical = str(item.get("canonical_url") or item.get("url") or "")
        title = " ".join(str(item.get("title") or "").casefold().split())
        # A canonical origin identifies a repost family.  A title alone does
        # not: two unrelated items can have the same generic title.
        family = _digest(canonical) if canonical else ""
        event_id = _digest(source, str(item.get("event_id") or family), str((item.get("instance") or {}).get("id") or item.get("item_key") or ""))
        fingerprint = _digest(title, str(item.get("status") or ""), str(item.get("material_hash") or item.get("material_text") or ""))
        record = {"event_id": event_id, "repost_family_id": family, "source": source, "canonical_url": canonical, "title": str(item.get("title") or ""), "publication_at": str(item.get("published_at") or ""), "update_at": str(item.get("updated_at") or ""), "fetch_at": str(item.get("fetched_at") or ""), "check_at": checked_at, "fingerprint": fingerprint, "payload": dict(item)}
        event_key = event_id if str((item.get("instance") or {}).get("id") or "") else (family or event_id)
        prior = events.get(event_key)
        if prior is None or (_timestamp_sort_key(record["update_at"]), record["event_id"]) > (_timestamp_sort_key(prior["update_at"]), prior["event_id"]):
            events[event_key] = {**record, **{k: record[k] or (prior or {}).get(k, "") for k in ("publication_at", "fetch_at")}}
    prior = {_prior_key(item): dict(item) for item in prior_events if _prior_key(item)}
    current = {_prior_key(item): item for item in events.values()}
    annotated: list[dict[str, Any]] = []
    for key, record in current.items():
        annotated.append({**record, "change_type": classify_event_change(prior.get(key), record)})
    # A disappearance is information, not a cancellation. It is caller-supplied
    # prior state projected into this ephemeral edition; no state is written.
    for key, record in prior.items():
        if key not in current:
            annotated.append({**record, "change_type": "disappeared"})
    ordered = sorted(annotated, key=lambda x: (_timestamp_sort_key(str(x.get("update_at") or x.get("publication_at") or "")), str(x["event_id"])), reverse=True)
    return {"schema_version": "prm_news_edition.v1", "edition_id": _digest(topic_id, window_start, window_end), "topic_id": topic_id, "window": {"start": window_start, "end": window_end, "valid": valid_window}, "checked_at": checked_at, "events": ordered, "rejected_invalid_time_count": rejected_invalid_time_count, "write_performed": False}


def classify_event_change(previous: Mapping[str, Any] | None, current: Mapping[str, Any] | None) -> str:
    if previous is None and current is not None: return "new"
    if previous is not None and current is None: return "disappeared"
    if previous is None: return "unchanged"
    if str(current.get("payload", {}).get("status") or "").casefold() in {"cancelled", "canceled"}: return "cancelled"
    if previous.get("fingerprint") == current.get("fingerprint"): return "cosmetic_or_unchanged"
    return "material_update"


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:20]


def _within_window(observed: str, start_at: datetime | None, end_at: datetime | None) -> bool | None:
    """Return None for invalid required time, never silently classify it fresh."""
    # Short non-date values occur only in legacy unit fixtures; a production
    # caller must provide bounded ISO times, which are validated below.
    if not observed:
        return None
    observed_at = _parse_time(observed)
    if observed_at is None or start_at is None or end_at is None:
        return None
    return start_at <= observed_at <= end_at


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp_sort_key(value: str) -> str:
    parsed = _parse_time(value)
    return parsed.isoformat() if parsed is not None else ""


def _prior_key(item: Mapping[str, Any]) -> str:
    payload = item.get("payload") if isinstance(item.get("payload"), Mapping) else {}
    if isinstance(payload.get("instance"), Mapping):
        return str(item.get("event_id") or "")
    return str(item.get("repost_family_id") or item.get("event_id") or "")
