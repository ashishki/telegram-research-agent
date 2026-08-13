"""Privacy-safe, non-persisting PRM-19 evaluation receipt contracts."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


PRM19_DOGFOOD_RECEIPT_SCHEMA_VERSION = "prm19_real_question_receipt.v1"
_OPERATOR_LABELS = {
    "useful": {"yes", "partial", "no", "unknown"},
    "trust": {"high", "medium", "low", "unknown"},
}
_FORBIDDEN_KEYS = {"raw_post_text", "prompt", "completion", "provider_payload", "raw_telegram_text"}


class PRM19DogfoodReceiptValidationError(ValueError):
    pass


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
