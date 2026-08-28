"""SQLite persistence helpers for the confirmation-gated UTD-1 profile."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from assistant.utd_profile_schema import _as_utc, _normalize_draft


def load_confirmed_utd_profile(
    db_path: str | Path | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    if db_path is None or not Path(db_path).exists():
        return None
    try:
        with sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True) as connection:
            rows = connection.execute(
                """
                SELECT event_type, metadata_json
                FROM personal_memory_events
                WHERE object_type = 'watch_topic'
                ORDER BY id DESC
                """
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
            expires_at = datetime.fromisoformat(
                str(metadata.get("expires_at") or "").replace("Z", "+00:00")
            )
        except ValueError:
            return None
        if _as_utc(expires_at) <= _as_utc(now):
            return None
        return metadata
    return None


def _load_draft(
    db_path: str | Path,
    *,
    context_id: str,
    chat_id: str,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any], str] | None:
    if not chat_id or not Path(db_path).exists():
        return None
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                """
                SELECT chat_id_hash, summary_json, proposals_json, expires_at, status
                FROM prm_post_answer_proposals
                WHERE context_id = ?
                """,
                (context_id,),
            ).fetchone()
            if row is None or row[0] != _chat_hash(chat_id):
                return None
            expires_at = datetime.fromisoformat(str(row[3]).replace("Z", "+00:00"))
            if str(row[4]) == "cancelled" or expires_at <= now:
                _discard_draft_in_connection(
                    connection,
                    context_id,
                    "expired" if expires_at <= now else "cancelled",
                )
                return None
    except (sqlite3.Error, ValueError):
        return None
    try:
        summary = json.loads(str(row[1]))
        proposals = json.loads(str(row[2] or "{}"))
    except json.JSONDecodeError:
        return None
    if summary.get("kind") != "utd_profile_draft" or not isinstance(summary.get("draft"), Mapping):
        return None
    return _normalize_draft(summary["draft"]), dict(proposals), str(row[4])


def _save_draft(
    db_path: str | Path,
    context_id: str,
    *,
    draft: Mapping[str, Any],
    proposals: Mapping[str, Any],
    status: str,
) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE prm_post_answer_proposals
            SET summary_json = ?, proposals_json = ?, status = ?
            WHERE context_id = ?
            """,
            (
                json.dumps(
                    {"kind": "utd_profile_draft", "draft": _normalize_draft(draft)},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                json.dumps(proposals, ensure_ascii=False, sort_keys=True),
                status,
                context_id,
            ),
        )
        connection.commit()


def _discard_draft(db_path: str | Path, context_id: str, status: str) -> None:
    with sqlite3.connect(db_path) as connection:
        _discard_draft_in_connection(connection, context_id, status)


def _discard_draft_in_connection(
    connection: sqlite3.Connection,
    context_id: str,
    status: str,
) -> None:
    connection.execute(
        """
        UPDATE prm_post_answer_proposals
        SET summary_json = '{}', proposals_json = '{}', status = ?
        WHERE context_id = ?
        """,
        (status, context_id),
    )
    connection.commit()


def _set_draft_status(db_path: str | Path, context_id: str, status: str) -> None:
    if status in {"cancelled", "expired"}:
        _discard_draft(db_path, context_id, status)
        return
    # Confirmed proposal state is retained only until the existing 30-minute
    # proposal expiry so an exact callback replay can remain idempotent.
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE prm_post_answer_proposals SET status = ? WHERE context_id = ?",
            (status, context_id),
        )
        connection.commit()


def _draft_schema_ready(connection: sqlite3.Connection) -> bool:
    required = {
        "context_id",
        "chat_id_hash",
        "summary_json",
        "proposals_json",
        "created_at",
        "expires_at",
        "status",
    }
    columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(prm_post_answer_proposals)").fetchall()
    }
    return required.issubset(columns)


def _chat_hash(chat_id: str) -> str:
    secret = os.environ.get("PI_SAVE_CONFIRMATION_SECRET", "local-prm12-confirmation-v1")
    return hashlib.sha256(f"{secret}:utd-draft:{chat_id}".encode("utf-8")).hexdigest()
