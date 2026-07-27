from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


MEMORY_PROPOSAL_SCHEMA_VERSION = "pi_memory_proposal.v1"
MEMORY_EVENT_SCHEMA_VERSION = "pi_memory_event.v1"
CONFIRMATION_TOKEN_PREFIX = "confirm-"

MEMORY_OBJECT_TYPES = {
    "knowledge_note",
    "watch_topic",
    "project_link",
    "decision",
    "action",
    "experiment",
    "feedback",
}

MEMORY_OPERATIONS = {
    "create": "created",
    "edit": "edited",
    "delete": "deleted",
    "rollback": "rolled_back",
}


def build_memory_proposal(proposal_type: str, args: Mapping[str, Any]) -> dict:
    proposal = normalize_memory_proposal(
        {
            "schema_version": MEMORY_PROPOSAL_SCHEMA_VERSION,
            "object_type": proposal_type,
            "operation": args.get("operation") or "create",
            "target_memory_id": args.get("target_memory_id"),
            "target_event_id": args.get("target_event_id"),
            "title": args.get("title"),
            "body": args.get("body"),
            "rationale": args.get("rationale"),
            "source_refs": args.get("source_refs"),
            "metadata": args.get("metadata"),
        }
    )
    proposal_id = _proposal_id(proposal)
    confirmation_token = confirmation_token_for_proposal(proposal)
    return {
        "status": "needs_confirmation",
        "proposal_id": proposal_id,
        "proposal_type": proposal_type,
        "operation": proposal["operation"],
        "proposal": proposal,
        "confirmation": {
            "required": True,
            "token": confirmation_token,
            "confirm_tool": "confirm_save_proposal",
            "message": "Pass this exact proposal and token to confirm_save_proposal to persist it.",
        },
        "persisted": False,
        "write_performed": False,
        "message": "Proposal drafted only; human confirmation is required before persistence.",
    }


def confirm_memory_proposal(db_path: str | Path, args: Mapping[str, Any]) -> dict:
    raw_proposal = args.get("proposal")
    if not isinstance(raw_proposal, Mapping):
        raise ValueError("proposal is required")
    proposal = normalize_memory_proposal(raw_proposal)
    supplied_token = _clean_required(args.get("confirmation_token"), "confirmation_token")
    expected_token = confirmation_token_for_proposal(proposal)
    if supplied_token != expected_token:
        return {
            "status": "confirmation_required",
            "persisted": False,
            "write_performed": False,
            "message": "Valid confirmation_token is required before persistence.",
        }

    timestamp = _optional_string(args.get("confirmed_at")) or _now_iso()
    confirmed_by = _optional_string(args.get("confirmed_by")) or "operator"
    memory_id = proposal.get("target_memory_id") or _memory_id(proposal)
    event_type = MEMORY_OPERATIONS[str(proposal["operation"])]
    token_hash = _token_hash(supplied_token)
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_file) as connection:
        _ensure_schema(connection)
        cursor = connection.execute(
            """
            INSERT INTO personal_memory_events (
                memory_id,
                object_type,
                event_type,
                title,
                body,
                rationale,
                source_refs_json,
                metadata_json,
                proposal_id,
                rollback_of_event_id,
                created_at,
                created_by,
                confirmation_token_hash,
                confirmation_receipt_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                proposal["object_type"],
                event_type,
                proposal["title"],
                proposal.get("body"),
                proposal.get("rationale"),
                json.dumps(proposal["source_refs"], ensure_ascii=False),
                json.dumps(proposal["metadata"], ensure_ascii=False, sort_keys=True),
                _proposal_id(proposal),
                proposal.get("target_event_id") if event_type == "rolled_back" else None,
                timestamp,
                confirmed_by,
                token_hash,
                json.dumps(
                    {
                        "schema_version": MEMORY_EVENT_SCHEMA_VERSION,
                        "proposal_id": _proposal_id(proposal),
                        "operation": proposal["operation"],
                        "confirmed_at": timestamp,
                        "confirmed_by": confirmed_by,
                        "confirmation_token_hash": token_hash,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        )
        connection.commit()
        event_id = int(cursor.lastrowid)

    return {
        "status": "ok",
        "persisted": True,
        "write_performed": True,
        "memory_id": memory_id,
        "event_id": event_id,
        "event_type": event_type,
        "object_type": proposal["object_type"],
        "operation": proposal["operation"],
        "append_only": True,
        "rollback_of_event_id": proposal.get("target_event_id") if event_type == "rolled_back" else None,
        "confirmation_receipt": {
            "schema_version": MEMORY_EVENT_SCHEMA_VERSION,
            "proposal_id": _proposal_id(proposal),
            "confirmed_at": timestamp,
            "confirmed_by": confirmed_by,
            "confirmation_token_hash": token_hash,
        },
        "message": "Confirmed memory proposal persisted as an append-only event.",
    }


def normalize_memory_proposal(raw: Mapping[str, Any]) -> dict:
    object_type = _normalize_choice(raw.get("object_type"), MEMORY_OBJECT_TYPES, "object_type")
    operation = _normalize_choice(raw.get("operation") or "create", set(MEMORY_OPERATIONS), "operation")
    target_memory_id = _optional_string(raw.get("target_memory_id"))
    target_event_id = _optional_int(raw.get("target_event_id"))
    if operation in {"edit", "delete", "rollback"} and not target_memory_id:
        raise ValueError("target_memory_id is required for edit, delete, and rollback proposals")
    if operation == "rollback" and target_event_id is None:
        raise ValueError("target_event_id is required for rollback proposals")
    title = _clean_required(raw.get("title"), "title")
    return {
        "schema_version": MEMORY_PROPOSAL_SCHEMA_VERSION,
        "object_type": object_type,
        "operation": operation,
        "target_memory_id": target_memory_id,
        "target_event_id": target_event_id,
        "title": title,
        "body": _optional_string(raw.get("body")),
        "rationale": _optional_string(raw.get("rationale")),
        "source_refs": _string_list(raw.get("source_refs")),
        "metadata": _metadata(raw.get("metadata")),
    }


def confirmation_token_for_proposal(proposal: Mapping[str, Any]) -> str:
    normalized = normalize_memory_proposal(proposal)
    secret = os.environ.get("PI_SAVE_CONFIRMATION_SECRET", "local-prm12-confirmation-v1")
    digest = hashlib.sha256(f"{secret}:{_canonical_json(normalized)}".encode("utf-8")).hexdigest()
    return f"{CONFIRMATION_TOKEN_PREFIX}{digest[:20]}"


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS personal_memory_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id TEXT NOT NULL CHECK(length(trim(memory_id)) > 0),
            object_type TEXT NOT NULL CHECK(object_type IN (
                'knowledge_note',
                'watch_topic',
                'project_link',
                'decision',
                'action',
                'experiment',
                'feedback'
            )),
            event_type TEXT NOT NULL CHECK(event_type IN (
                'created',
                'edited',
                'deleted',
                'rolled_back'
            )),
            title TEXT NOT NULL CHECK(length(trim(title)) > 0),
            body TEXT,
            rationale TEXT,
            source_refs_json TEXT NOT NULL
                CHECK(json_valid(source_refs_json) AND json_type(source_refs_json) = 'array'),
            metadata_json TEXT NOT NULL
                CHECK(json_valid(metadata_json) AND json_type(metadata_json) = 'object'),
            proposal_id TEXT NOT NULL CHECK(length(trim(proposal_id)) > 0),
            rollback_of_event_id INTEGER,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            confirmation_token_hash TEXT NOT NULL CHECK(length(trim(confirmation_token_hash)) > 0),
            confirmation_receipt_json TEXT NOT NULL
                CHECK(json_valid(confirmation_receipt_json)
                      AND json_type(confirmation_receipt_json) = 'object')
        );

        CREATE INDEX IF NOT EXISTS idx_personal_memory_events_memory
        ON personal_memory_events(memory_id, id);

        CREATE INDEX IF NOT EXISTS idx_personal_memory_events_type_created
        ON personal_memory_events(object_type, created_at);
        """
    )


def _proposal_id(proposal: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(proposal).encode("utf-8")).hexdigest()
    return f"prm12prop_{digest[:20]}"


def _memory_id(proposal: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(
        f"{proposal.get('object_type')}:{proposal.get('title')}:{_proposal_id(proposal)}".encode("utf-8")
    ).hexdigest()
    return f"mem_{digest[:20]}"


def _token_hash(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_required(value: object, field_name: str) -> str:
    clean = _optional_string(value)
    if not clean:
        raise ValueError(f"{field_name} is required")
    return clean


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    clean = str(value).strip()
    return clean or None


def _normalize_choice(value: object, allowed: set[str], field_name: str) -> str:
    clean = _clean_required(value, field_name).replace("-", "_")
    if clean not in allowed:
        expected = ", ".join(sorted(allowed))
        raise ValueError(f"unsupported {field_name}: {value!r}; expected one of {expected}")
    return clean


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("target_event_id must be an integer") from exc


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _metadata(value: object) -> dict:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be an object")
    return {str(key): item for key, item in value.items()}
