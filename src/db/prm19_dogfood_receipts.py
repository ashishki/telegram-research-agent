"""Privacy-safe PRM receipt contracts and temporary SQLite interaction ledger."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


PRM19_DOGFOOD_RECEIPT_SCHEMA_VERSION = "prm19_real_question_receipt.v1"
_OPERATOR_LABELS = {
    "useful": {"yes", "partial", "no", "unknown"},
    "trust": {"high", "medium", "low", "unknown"},
}
_FORBIDDEN_KEYS = {"raw_post_text", "prompt", "completion", "provider_payload", "raw_telegram_text"}
_LEDGER_RETENTION = timedelta(days=90)
_FEEDBACK_ACTIONS = {
    "u": ("useful", "yes"),
    "r": ("wrong_priority", "no"),
    "s": ("too_shallow", "partial"),
    "d": ("applied", "yes"),
}


class PRM19DogfoodReceiptValidationError(ValueError):
    pass


def record_interaction_receipt(
    db_path: str | Path,
    *,
    interaction_id: str,
    chat_id_hash: str,
    answer: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist one metadata-only receipt for an already rendered answer.

    This is not PRM-19 dogfood telemetry. Question text, post bodies, source
    URLs, and provider payloads are rejected before any SQLite write.
    """

    now = datetime.now(timezone.utc)
    receipt = _build_interaction_metadata(interaction_id, chat_id_hash, answer, now)
    with sqlite3.connect(db_path) as connection:
        _prune_expired(connection, now=now)
        connection.execute(
            """
            INSERT OR IGNORE INTO prm_interaction_ledger (
                interaction_id, chat_id_hash, surface, input_kind, answer_status,
                source_count, evidence_classes_json, external_verification_status,
                selected_professional_lens, selected_project, primary_workflow,
                useful_label, receipt_status, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unknown', 'recorded', ?, ?)
            """,
            (
                receipt["interaction_id"], receipt["chat_id_hash"], receipt["surface"],
                receipt["input_kind"], receipt["answer_status"], receipt["source_count"],
                json.dumps(receipt["evidence_classes"], sort_keys=True),
                receipt["external_verification_status"], receipt["selected_professional_lens"],
                receipt["selected_project"], receipt["primary_workflow"], receipt["created_at"],
                receipt["expires_at"],
            ),
        )
    return receipt


def record_feedback_transition(db_path: str | Path, *, interaction_id: str, action_code: str) -> dict[str, Any]:
    """Apply exactly one explicit feedback label to the matching interaction."""

    feedback = _FEEDBACK_ACTIONS.get(action_code)
    if feedback is None:
        raise PRM19DogfoodReceiptValidationError("unsupported feedback action")
    action, useful_label = feedback
    now = _iso(datetime.now(timezone.utc))
    with sqlite3.connect(db_path) as connection:
        _prune_expired(connection)
        row = connection.execute(
            "SELECT expires_at FROM prm_interaction_ledger WHERE interaction_id = ?", (interaction_id,)
        ).fetchone()
        if row is None or _expired(str(row[0])):
            return {"status": "missing_or_expired", "write_performed": False}
        try:
            connection.execute(
                "INSERT INTO prm_interaction_feedback_transitions (interaction_id, feedback_action, useful_label, recorded_at) VALUES (?, ?, ?, ?)",
                (interaction_id, action, useful_label, now),
            )
        except sqlite3.IntegrityError:
            return {"status": "already_recorded", "write_performed": False}
        connection.execute(
            "UPDATE prm_interaction_ledger SET useful_label = ?, feedback_transitioned_at = ? WHERE interaction_id = ?",
            (useful_label, now, interaction_id),
        )
    return {"status": "recorded", "write_performed": True, "useful_label": useful_label}


def list_interaction_receipts(db_path: str | Path, *, chat_id_hash: str, limit: int = 20) -> list[dict[str, Any]]:
    """Owner-scoped review view containing only privacy-safe receipt metadata."""

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        _prune_expired(connection)
        rows = connection.execute(
            "SELECT interaction_id, surface, input_kind, answer_status, source_count, evidence_classes_json, "
            "external_verification_status, selected_professional_lens, selected_project, primary_workflow, "
            "useful_label, feedback_transitioned_at, receipt_status, created_at, expires_at "
            "FROM prm_interaction_ledger WHERE chat_id_hash = ? ORDER BY created_at DESC LIMIT ?",
            (chat_id_hash, max(1, min(int(limit), 100))),
        ).fetchall()
    return [
        {**{key: value for key, value in dict(row).items() if key != "evidence_classes_json"}, "evidence_classes": json.loads(row["evidence_classes_json"])}
        for row in rows
    ]


def export_interaction_aggregate(db_path: str | Path) -> dict[str, Any]:
    """Return local aggregate counts; no identities, raw text, or public export."""

    with sqlite3.connect(db_path) as connection:
        _prune_expired(connection)
        rows = connection.execute("SELECT useful_label, COUNT(*) FROM prm_interaction_ledger GROUP BY useful_label").fetchall()
    labels = {"yes": 0, "partial": 0, "no": 0, "unknown": 0}
    labels.update({str(label): int(count) for label, count in rows})
    return {"schema_version": "prm_interaction_aggregate.v1", "receipt_count": sum(labels.values()), "useful_labels": labels, "public_export": False, "dogfood_started": False}


def build_real_question_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize operator-owned metadata; it does not write or start dogfood."""

    receipt = {
        "schema_version": PRM19_DOGFOOD_RECEIPT_SCHEMA_VERSION,
        "question_id": _required(payload, "question_id"),
        "asked_at": _required(payload, "asked_at"),
        "surface": _enum(payload, "surface", {"telegram", "cli"}),
        "input_kind": _enum(payload, "input_kind", {"text", "voice_transcript"}),
        "selected_professional_lens": _string(payload.get("selected_professional_lens")) or "unknown",
        "selected_project": _string(payload.get("selected_project")) or "unknown",
        "intent_chosen": _string(payload.get("intent_chosen")) or "unknown",
        "clarification_required": bool(payload.get("clarification_required")),
        "answer_latency_seconds": max(0.0, float(payload.get("answer_latency_seconds") or 0.0)),
        "source_count": max(0, int(payload.get("source_count") or 0)),
        "external_verification_status": _enum(
            payload, "external_verification_status", {"not_needed", "required_not_run", "approved_run", "unavailable"}
        ),
        "useful": _operator_label(payload, "useful"),
        "trust": _operator_label(payload, "trust"),
        "rephrase_required": bool(payload.get("rephrase_required")),
        "incorrect_or_irrelevant_evidence": bool(payload.get("incorrect_or_irrelevant_evidence")),
        "saved_action": _string(payload.get("saved_action")) or "none",
        "decision_or_action_influenced": _string(payload.get("decision_or_action_influenced")) or "unknown",
        "time_saved_estimate_minutes": max(0.0, float(payload.get("time_saved_estimate_minutes") or 0.0)),
        "operator_correction": _string(payload.get("operator_correction")),
        "feedback_notes": _string(payload.get("feedback_notes")),
        "evidence_classes": _strings(payload.get("evidence_classes")),
        "privacy": {"raw_post_text_recorded": False, "provider_payload_recorded": False, "durable_write_confirmed": bool(payload.get("durable_write_confirmed"))},
        "dogfood_started": False,
        "write_performed": False,
    }
    return validate_real_question_receipt(receipt)


def build_smoke_receipt(receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate up to ten fixture/operator metadata rows without dogfood activation."""

    if len(receipts) > 10:
        raise PRM19DogfoodReceiptValidationError("smoke receipt supports at most 10 questions")
    return {
        "schema_version": "prm19_smoke_receipt.v1",
        "status": "smoke_only_not_dogfood",
        "question_count": len(receipts),
        "receipts": [build_real_question_receipt(item) for item in receipts],
        "dogfood_started": False,
        "write_performed": False,
    }


def validate_real_question_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    if _FORBIDDEN_KEYS & set(receipt):
        raise PRM19DogfoodReceiptValidationError("forbidden raw payload keys")
    normalized = dict(receipt)
    if normalized.get("schema_version") != PRM19_DOGFOOD_RECEIPT_SCHEMA_VERSION:
        raise PRM19DogfoodReceiptValidationError("unsupported schema version")
    if normalized.get("dogfood_started") is not False or normalized.get("write_performed") is not False:
        raise PRM19DogfoodReceiptValidationError("receipt cannot start dogfood or write")
    privacy = normalized.get("privacy")
    if not isinstance(privacy, Mapping) or privacy.get("raw_post_text_recorded") or privacy.get("provider_payload_recorded"):
        raise PRM19DogfoodReceiptValidationError("privacy-safe receipt required")
    return normalized


def _required(payload: Mapping[str, Any], key: str) -> str:
    value = _string(payload.get(key))
    if not value:
        raise PRM19DogfoodReceiptValidationError(f"{key} is required")
    return value


def _enum(payload: Mapping[str, Any], key: str, values: set[str]) -> str:
    value = _required(payload, key)
    if value not in values:
        raise PRM19DogfoodReceiptValidationError(f"unsupported {key}")
    return value


def _operator_label(payload: Mapping[str, Any], key: str) -> str:
    value = _string(payload.get(key)) or "unknown"
    if value not in _OPERATOR_LABELS[key]:
        raise PRM19DogfoodReceiptValidationError(f"unsupported {key}")
    return value


def _string(value: object) -> str:
    return " ".join(str(value or "").split())


def _strings(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [_string(item) for item in value if _string(item)]


def _build_interaction_metadata(interaction_id: str, chat_id_hash: str, answer: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    forbidden = _FORBIDDEN_KEYS & set(answer)
    if forbidden or any(key in answer for key in ("question", "direct_answer", "body", "source_refs")):
        raise PRM19DogfoodReceiptValidationError("raw answer payload is not allowed in interaction ledger")
    professional = answer.get("professional_answer") if isinstance(answer.get("professional_answer"), Mapping) else {}
    external = answer.get("external_verification") if isinstance(answer.get("external_verification"), Mapping) else {}
    allowed_statuses = {"supported", "partial", "insufficient_evidence", "verification_required", "unknown"}
    verification_statuses = {"not_needed", "required_not_run", "approved_run", "unavailable", "unknown"}
    status = _string(professional.get("answer_status") or answer.get("answer_status")) or "unknown"
    verification = _string(external.get("status") or answer.get("external_verification_status")) or "unknown"
    return {
        "interaction_id": _required({"interaction_id": interaction_id}, "interaction_id"),
        "chat_id_hash": _required({"chat_id_hash": chat_id_hash}, "chat_id_hash"),
        "surface": "telegram",
        "input_kind": _string(answer.get("input_kind")) if _string(answer.get("input_kind")) in {"text", "voice_transcript"} else "unknown",
        "answer_status": status if status in allowed_statuses else "unknown",
        "source_count": max(0, int(answer.get("source_count") or 0)),
        "evidence_classes": sorted(set(_strings(answer.get("evidence_classes")))),
        "external_verification_status": verification if verification in verification_statuses else "unknown",
        "selected_professional_lens": _string(professional.get("professional_lens") or answer.get("selected_professional_lens")) or "unknown",
        "selected_project": _string(answer.get("selected_project")) or "unknown",
        "primary_workflow": _string(professional.get("primary_workflow") or answer.get("primary_workflow")) or "unknown",
        "created_at": _iso(now),
        "expires_at": _iso(now + _LEDGER_RETENTION),
    }


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _expired(value: str) -> bool:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) <= datetime.now(timezone.utc)


def _prune_expired(connection: sqlite3.Connection, *, now: datetime | None = None) -> None:
    """Enforce the bounded private-retention window before any ledger read/write."""

    cutoff = _iso(now or datetime.now(timezone.utc))
    connection.execute(
        "DELETE FROM prm_interaction_feedback_transitions WHERE interaction_id IN "
        "(SELECT interaction_id FROM prm_interaction_ledger WHERE expires_at <= ?)",
        (cutoff,),
    )
    connection.execute("DELETE FROM prm_interaction_ledger WHERE expires_at <= ?", (cutoff,))
