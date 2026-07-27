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
    proposal_id = _proposal_id(proposal)
    token_hash = _token_hash(supplied_token)
    db_file = Path(db_path)
    if not db_file.exists():
        return _not_persisted(
            "schema_missing",
            "personal_memory_events schema is not initialized; run canonical migrations before confirmed saves.",
        )
    with sqlite3.connect(db_file) as connection:
        if not _schema_ready(connection):
            return _not_persisted(
                "schema_missing",
                "personal_memory_events schema is not initialized; run canonical migrations before confirmed saves.",
            )
        existing = _existing_confirmation(connection, proposal_id, token_hash)
        if existing:
            return {
                "status": "already_confirmed",
                "persisted": True,
                "write_performed": False,
                "memory_id": str(existing["memory_id"]),
                "event_id": int(existing["id"]),
                "event_type": str(existing["event_type"]),
                "object_type": str(existing["object_type"]),
                "operation": proposal["operation"],
                "append_only": True,
                "rollback_of_event_id": existing["rollback_of_event_id"],
                "confirmation_receipt": json.loads(str(existing["confirmation_receipt_json"])),
                "message": "Proposal was already confirmed; no new memory event was appended.",
            }
        invalid_target = _invalid_target_reason(connection, proposal)
        if invalid_target:
            return _not_persisted("invalid_target", invalid_target)
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
                proposal_id,
                proposal.get("target_event_id") if event_type == "rolled_back" else None,
                timestamp,
                confirmed_by,
                token_hash,
                json.dumps(
                    {
                        "schema_version": MEMORY_EVENT_SCHEMA_VERSION,
                        "proposal_id": proposal_id,
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
            "proposal_id": proposal_id,
            "confirmed_at": timestamp,
            "confirmed_by": confirmed_by,
            "confirmation_token_hash": token_hash,
        },
        "message": "Confirmed memory proposal persisted as an append-only event.",
    }


def _not_persisted(status: str, message: str) -> dict[str, object]:
    return {
        "status": status,
        "persisted": False,
        "write_performed": False,
        "message": message,
    }


def _schema_ready(connection: sqlite3.Connection) -> bool:
    required_columns = {
        "id",
        "memory_id",
        "object_type",
        "event_type",
        "title",
        "body",
        "rationale",
        "source_refs_json",
        "metadata_json",
        "proposal_id",
        "rollback_of_event_id",
        "created_at",
        "created_by",
        "confirmation_token_hash",
        "confirmation_receipt_json",
    }
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(personal_memory_events)").fetchall()}
    return required_columns.issubset(columns)


def _existing_confirmation(connection: sqlite3.Connection, proposal_id: str, token_hash: str) -> sqlite3.Row | None:
    connection.row_factory = sqlite3.Row
    return connection.execute(
        """
        SELECT *
        FROM personal_memory_events
        WHERE proposal_id = ? AND confirmation_token_hash = ?
        ORDER BY id
        LIMIT 1
        """,
        (proposal_id, token_hash),
    ).fetchone()


def _invalid_target_reason(connection: sqlite3.Connection, proposal: Mapping[str, Any]) -> str | None:
    operation = str(proposal["operation"])
    if operation == "create":
        return None
    target_memory_id = str(proposal.get("target_memory_id") or "")
    object_type = str(proposal["object_type"])
    target = connection.execute(
        """
        SELECT id, object_type
        FROM personal_memory_events
        WHERE memory_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (target_memory_id,),
    ).fetchone()
    if target is None:
        return "target_memory_id does not exist; edit, delete, and rollback require an existing memory object."
    if str(target["object_type"]) != object_type:
        return "target_memory_id belongs to a different memory object_type."
    if operation != "rollback":
        return None
    target_event_id = proposal.get("target_event_id")
    rollback_target = connection.execute(
        """
        SELECT id, memory_id, object_type
        FROM personal_memory_events
        WHERE id = ?
        LIMIT 1
        """,
        (target_event_id,),
    ).fetchone()
    if rollback_target is None:
        return "target_event_id does not exist; rollback requires an existing memory event."
    if str(rollback_target["memory_id"]) != target_memory_id or str(rollback_target["object_type"]) != object_type:
        return "target_event_id does not belong to the requested target_memory_id and object_type."
    return None


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
