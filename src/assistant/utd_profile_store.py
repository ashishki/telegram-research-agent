"""SQLite persistence helpers for the confirmation-gated UTD-1 profile."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from assistant.utd_profile_schema import _as_utc, _normalize_draft


_UTD_STATE_STATUS = {
    "draft": "ready",
    "previewed": "pending",
    "confirming": "pending",
    "confirmed": "confirmed",
    "cancelled": "cancelled",
    "expired": "cancelled",
}
_UTD_ALLOWED_TRANSITIONS = {
    "draft": {"draft", "previewed", "cancelled"},
    "previewed": {"draft", "confirming", "cancelled", "expired"},
    "confirming": {"previewed", "confirmed", "cancelled", "expired"},
    "confirmed": set(),
    "cancelled": set(),
    "expired": set(),
}
_UTD_KINDS = {"utd_profile_draft", "utd_subscription_lifecycle"}


@dataclass(frozen=True)
class UtdTransitionResult:
    """The only state-mutating UTD store outcome."""

    status: str
    logical_state: str | None = None

    @property
    def applied(self) -> bool:
        return self.status == "applied"


@dataclass(frozen=True)
class UtdStoredProposal:
    context_id: str
    logical_state: str
    summary: dict[str, Any]
    proposals: dict[str, Any]
    expires_at: datetime


def encode_utd_proposal_state(summary: Mapping[str, Any], state: str) -> tuple[str, str]:
    """Encode the sole logical UTD state and its canonical shared-table status."""

    if state not in _UTD_STATE_STATUS or not isinstance(summary, Mapping):
        raise ValueError("Unsupported UTD proposal state")
    payload = dict(summary)
    if payload.get("kind") not in _UTD_KINDS:
        raise ValueError("Unsupported UTD proposal kind")
    payload["utd_state"] = state
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False), _UTD_STATE_STATUS[state]


def decode_utd_proposal_state(summary_json: str, table_status: str) -> tuple[dict[str, Any], str] | None:
    """Fail closed unless JSON and the shared-table status describe one UTD state."""

    try:
        summary = json.loads(summary_json)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(summary, dict) or summary.get("kind") not in _UTD_KINDS:
        return None
    state = summary.get("utd_state")
    if not isinstance(state, str) or _UTD_STATE_STATUS.get(state) != table_status:
        return None
    return summary, state


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
                SELECT memory_id, event_type, metadata_json, confirmation_token_hash,
                       confirmation_receipt_json
                FROM personal_memory_events
                WHERE object_type = 'watch_topic'
                ORDER BY id DESC
                """
            ).fetchall()
    except sqlite3.Error:
        return None
    seen_memory_ids: set[str] = set()
    for memory_id, event_type, metadata_json, event_token_hash, raw_receipt in rows:
        if str(memory_id) in seen_memory_ids:
            continue
        seen_memory_ids.add(str(memory_id))
        try:
            metadata = json.loads(str(metadata_json))
        except (TypeError, json.JSONDecodeError):
            continue
        if metadata.get("capability") != "utd_profile_preview_watch":
            continue
        if str(event_type) not in {"created", "edited"}:
            return None
        try:
            receipt = json.loads(str(raw_receipt))
        except (TypeError, json.JSONDecodeError):
            return None
        if receipt.get("confirmation_token_hash") != event_token_hash:
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


def create_utd_proposal(
    db_path: str | Path,
    *,
    context_id: str,
    chat_id: str,
    summary: Mapping[str, Any],
    proposals: Mapping[str, Any],
    created_at: str,
    expires_at: str,
    state: str,
) -> UtdTransitionResult:
    """Create a UTD proposal using only clean-schema shared-table statuses."""

    if not chat_id or not Path(db_path).exists():
        return UtdTransitionResult("unavailable")
    try:
        encoded_summary, table_status = encode_utd_proposal_state(summary, state)
        encoded_proposals = json.dumps(proposals, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with sqlite3.connect(db_path) as connection:
            if not _draft_schema_ready(connection):
                return UtdTransitionResult("unavailable")
            connection.execute(
                "INSERT INTO prm_post_answer_proposals "
                "(context_id, chat_id_hash, summary_json, proposals_json, created_at, expires_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (context_id, _chat_hash(chat_id), encoded_summary, encoded_proposals, created_at, expires_at, table_status),
            )
            connection.commit()
    except (sqlite3.Error, TypeError, ValueError):
        return UtdTransitionResult("unavailable")
    return UtdTransitionResult("applied", state)


def load_utd_proposal(
    db_path: str | Path,
    *,
    context_id: str,
    chat_id: str,
    now: datetime,
) -> UtdStoredProposal | None:
    """Load only a canonical, chat-bound UTD row; expire it through the codec."""

    if not chat_id or not Path(db_path).exists():
        return None
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                "SELECT chat_id_hash, summary_json, proposals_json, expires_at, status "
                "FROM prm_post_answer_proposals WHERE context_id = ?",
                (context_id,),
            ).fetchone()
    except sqlite3.Error:
        return None
    if row is None or row[0] != _chat_hash(chat_id):
        return None
    decoded = decode_utd_proposal_state(str(row[1]), str(row[4]))
    if decoded is None:
        return None
    summary, state = decoded
    try:
        proposals = json.loads(str(row[2]))
        expires_at = _as_utc(datetime.fromisoformat(str(row[3]).replace("Z", "+00:00")))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(proposals, dict):
        return None
    if expires_at <= _as_utc(now) and state not in {"confirmed", "cancelled", "expired", "confirming"}:
        # Draft expiry is terminal/cancelled because the state graph does not
        # allow draft -> expired; a preview can represent explicit expiry.
        terminal = "expired" if state == "previewed" else "cancelled"
        transition_utd_context(
            db_path,
            context_id=context_id,
            chat_id=chat_id,
            expected=state,
            next_state=terminal,
            summary={"kind": summary["kind"]},
            proposals={},
        )
        return None
    if state in {"cancelled", "expired"}:
        return None
    return UtdStoredProposal(context_id, state, summary, proposals, expires_at)


def transition_utd_context(
    db_path: str | Path,
    *,
    context_id: str,
    chat_id: str,
    expected: str,
    next_state: str,
    summary: Mapping[str, Any] | None = None,
    proposals: Mapping[str, Any] | None = None,
) -> UtdTransitionResult:
    """Open the one UTD state transaction; callers never own shared SQL."""

    try:
        with sqlite3.connect(db_path) as connection:
            return transition_utd_proposal(
                connection,
                context_id,
                chat_id_hash=_chat_hash(chat_id),
                expected=expected,
                next_state=next_state,
                summary=summary,
                proposals=proposals,
            )
    except sqlite3.Error:
        return UtdTransitionResult("unavailable")


def transition_utd_proposal(
    connection: sqlite3.Connection,
    context_id: str,
    *,
    chat_id_hash: str,
    expected: str,
    next_state: str,
    summary: Mapping[str, Any] | None = None,
    proposals: Mapping[str, Any] | None = None,
) -> UtdTransitionResult:
    """Guard one UTD logical transition with summary/status/proposal CAS."""

    if next_state not in _UTD_ALLOWED_TRANSITIONS.get(expected, set()):
        return UtdTransitionResult("unavailable")
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT summary_json, proposals_json, status, expires_at FROM prm_post_answer_proposals "
            "WHERE context_id = ? AND chat_id_hash = ?",
            (context_id, chat_id_hash),
        ).fetchone()
        if row is None:
            connection.rollback()
            return UtdTransitionResult("unavailable")
        decoded = decode_utd_proposal_state(str(row[0]), str(row[2]))
        if decoded is None or decoded[1] != expected:
            connection.rollback()
            return UtdTransitionResult("unavailable")
        current_summary, _current_state = decoded
        current_proposals = json.loads(str(row[1]))
        if not isinstance(current_proposals, dict):
            connection.rollback()
            return UtdTransitionResult("unavailable")
        next_summary = dict(summary) if summary is not None else current_summary
        next_proposals = dict(proposals) if proposals is not None else current_proposals
        encoded_summary, table_status = encode_utd_proposal_state(next_summary, next_state)
        encoded_proposals = json.dumps(next_proposals, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        cursor = connection.execute(
            "UPDATE prm_post_answer_proposals SET summary_json = ?, proposals_json = ?, status = ? "
            "WHERE context_id = ? AND chat_id_hash = ? AND summary_json = ? AND proposals_json = ? AND status = ? AND expires_at = ?",
            (encoded_summary, encoded_proposals, table_status, context_id, chat_id_hash, row[0], row[1], row[2], row[3]),
        )
        if not cursor.rowcount:
            connection.rollback()
            return UtdTransitionResult("unavailable")
        connection.commit()
    except (sqlite3.Error, TypeError, ValueError, json.JSONDecodeError):
        connection.rollback()
        return UtdTransitionResult("unavailable")
    return UtdTransitionResult("applied", next_state)


def _load_draft(
    db_path: str | Path,
    *,
    context_id: str,
    chat_id: str,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any], str] | None:
    """Compatibility view used by the profile controller, backed by the codec."""

    stored = load_utd_proposal(db_path, context_id=context_id, chat_id=chat_id, now=now)
    if (
        stored is None
        or stored.summary.get("kind") != "utd_profile_draft"
        or not isinstance(stored.summary.get("draft"), Mapping)
    ):
        return None
    return _normalize_draft(stored.summary["draft"]), stored.proposals, stored.logical_state


def _save_draft(
    db_path: str | Path,
    context_id: str,
    *,
    chat_id: str,
    expected: str,
    draft: Mapping[str, Any],
    proposals: Mapping[str, Any],
    state: str,
) -> UtdTransitionResult:
    return transition_utd_context(
        db_path,
        context_id=context_id,
        chat_id=chat_id,
        expected=expected,
        next_state=state,
        summary={"kind": "utd_profile_draft", "draft": _normalize_draft(draft)},
        proposals=proposals,
    )


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
