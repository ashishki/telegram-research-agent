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
                "SELECT event_type, metadata_json FROM personal_memory_events WHERE object_type='watch_topic' ORDER BY id DESC"
            ).fetchall()
    except sqlite3.Error:
        return None
    for event_type, metadata_json in rows:
        try:
            metadata = json.loads(str(metadata_json))
        except (TypeError, json.JSONDecodeError):
            continue
        if metadata.get("capability") != "utd_profile_preview_watch":
            continue
        if str(event_type) in {"deleted", "rolled_back"}:
            return None
        try:
            expires_at = datetime.fromisoformat(str(metadata.get("expires_at") or "").replace("Z", "+00:00"))
        except ValueError:
            return None
        if _utc(expires_at) <= _utc(now):
            return None
        return metadata
    return None
