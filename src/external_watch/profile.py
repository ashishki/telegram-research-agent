"""Minimal read-only loader for a confirmed UTD watch profile.

This module deliberately avoids importing the assistant package so the shadow
sidecar does not pull in LLM/report-era dependencies.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def load_confirmed_utd_profile(db_path: str | Path | None, *, now: datetime | None = None) -> dict[str, Any] | None:
    if db_path is None:
        return None
    path = Path(db_path)
    if not path.exists():
        return None
    try:
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as db:
            rows = db.execute(
                "SELECT id, memory_id, event_type, metadata_json, confirmation_token_hash, confirmation_receipt_json FROM personal_memory_events WHERE object_type='watch_topic' ORDER BY id DESC"
            ).fetchall()
    except sqlite3.Error:
        return None
    seen_memory_ids: set[str] = set()
    for event_id, memory_id, event_type, metadata_json, event_token_hash, confirmation_receipt_json in rows:
        if str(memory_id) in seen_memory_ids:
            continue
        seen_memory_ids.add(str(memory_id))
        try:
            metadata = json.loads(str(metadata_json))
        except (TypeError, json.JSONDecodeError):
            continue
        if metadata.get("capability") != "utd_profile_preview_watch":
            continue
        # A delete is the latest revision for this exact profile object.  Never
        # fall through to an older active row and accidentally re-enable it.
        if str(event_type) not in {"created", "edited"}:
            return None
        try:
            receipt = json.loads(str(confirmation_receipt_json))
        except (TypeError, json.JSONDecodeError):
            return None
        if (not receipt.get("confirmation_token_hash") or receipt.get("confirmation_token_hash") != event_token_hash or not str(metadata.get("profile_schema_version") or "").startswith("utd_profile.")):
            # This is the newest UTD-shaped object. Falling back to an older
            # active profile would silently revive a superseded subscription.
            return None
        try:
            expires_at = datetime.fromisoformat(str(metadata.get("expires_at") or "").replace("Z", "+00:00"))
        except ValueError:
            return None
        if _utc(expires_at) <= _utc(now):
            return None
        return {**metadata, "subscription_confirmed": True, "subscription_memory_id": str(memory_id), "subscription_event_id": int(event_id)}
    return None
