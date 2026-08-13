import pytest

from db.prm19_dogfood_receipts import (
    PRM19DogfoodReceiptValidationError,
    build_real_question_receipt,
    build_smoke_receipt,
    validate_real_question_receipt,
)


def _payload() -> dict:
    return {
        "question_id": "q-001",
        "asked_at": "2026-08-12T10:00:00Z",
        "surface": "telegram",
        "input_kind": "text",
        "intent_chosen": "research",
        "external_verification_status": "not_needed",
        "useful": "partial",
        "trust": "medium",
        "evidence_classes": ["telegram_archive"],
    }


def test_real_question_receipt_schema_privacy():
    receipt = build_real_question_receipt(_payload())

    assert receipt["privacy"] == {
        "raw_post_text_recorded": False,
        "provider_payload_recorded": False,
        "durable_write_confirmed": False,
    }
    assert receipt["dogfood_started"] is False
    with pytest.raises(PRM19DogfoodReceiptValidationError, match="forbidden raw payload keys"):
        validate_real_question_receipt({**receipt, "raw_post_text": "private"})


def test_smoke_receipt_not_dogfood_start():
    result = build_smoke_receipt([_payload()])

    assert result["status"] == "smoke_only_not_dogfood"
    assert result["question_count"] == 1
    assert result["dogfood_started"] is False
    assert result["write_performed"] is False


def test_operator_labels_are_primary():
    receipt = build_real_question_receipt({**_payload(), "useful": "yes", "trust": "high"})

    assert receipt["useful"] == "yes"
    assert receipt["trust"] == "high"
    assert "llm_judge" not in receipt
