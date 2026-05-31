import pytest

from proof_receipts import build_core_research_brief_receipt, core_receipt_sha256


def test_core_research_brief_receipt_maps_local_receipt_to_proof_contract():
    receipt = build_core_research_brief_receipt(
        {
            "receipt_id": "rbr_2026_w22",
            "week_label": "2026-W22",
            "generated_at": "2026-05-31T09:00:00Z",
            "verification_status": "verified",
            "markdown_path": "data/output/digests/2026-W22.md",
            "source_set": {
                "source_evidence_item_ids": [101],
                "telegram_source_links": ["https://t.me/source_a/1"],
            },
        }
    )

    assert receipt["type"] == "research_brief_receipt"
    assert receipt["schema_version"] == "entropy_core.product_receipt.v1"
    assert receipt["product_id"] == "telegram-research-agent"
    assert receipt["verifier_status"] == "passed"
    assert receipt["entropy_core_level"] == "evidence_lookup_compatible"
    assert {ref["ref_type"] for ref in receipt["evidence_refs"]} == {
        "signal_evidence_item",
        "telegram_source_link",
    }
    assert len(core_receipt_sha256(receipt)) == 64


def test_core_research_brief_receipt_requires_evidence_refs():
    with pytest.raises(ValueError, match="source evidence refs"):
        build_core_research_brief_receipt(
            {
                "receipt_id": "rbr_empty",
                "week_label": "2026-W22",
                "markdown_path": "data/output/digests/2026-W22.md",
                "source_set": {},
            }
        )


def test_core_research_brief_receipt_marks_pending_as_needs_review():
    receipt = build_core_research_brief_receipt(
        {
            "receipt_id": "rbr_pending",
            "week_label": "2026-W22",
            "markdown_path": "data/output/digests/2026-W22.md",
            "verification_status": "pending",
            "source_set": {"source_evidence_item_ids": [101]},
        }
    )

    assert receipt["verifier_status"] == "needs_review"
    assert receipt["verifier_notes"]
