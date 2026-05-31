import sqlite3
import unittest

from proof_receipts import (
    build_core_research_brief_receipt,
    core_receipt_sha256,
    verify_core_research_brief_evidence_refs,
)


class TestCoreResearchBriefReceipt(unittest.TestCase):
    def _make_evidence_connection(self, evidence_ids: list[int] | None = None) -> sqlite3.Connection:
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE signal_evidence_items (id INTEGER PRIMARY KEY)")
        for evidence_id in evidence_ids or []:
            connection.execute(
                "INSERT INTO signal_evidence_items (id) VALUES (?)",
                (evidence_id,),
            )
        connection.commit()
        self.addCleanup(connection.close)
        return connection

    def test_core_research_brief_receipt_maps_local_receipt_to_proof_contract(self):
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

        self.assertEqual(receipt["type"], "research_brief_receipt")
        self.assertEqual(receipt["schema_version"], "entropy_core.product_receipt.v1")
        self.assertEqual(receipt["product_id"], "telegram-research-agent")
        self.assertEqual(receipt["verifier_status"], "passed")
        self.assertEqual(receipt["entropy_core_level"], "evidence_lookup_compatible")
        self.assertEqual(
            {ref["ref_type"] for ref in receipt["evidence_refs"]},
            {"signal_evidence_item", "telegram_source_link"},
        )
        self.assertEqual(len(core_receipt_sha256(receipt)), 64)

    def test_core_research_brief_receipt_requires_evidence_refs(self):
        with self.assertRaisesRegex(ValueError, "source evidence refs"):
            build_core_research_brief_receipt(
                {
                    "receipt_id": "rbr_empty",
                    "week_label": "2026-W22",
                    "markdown_path": "data/output/digests/2026-W22.md",
                    "source_set": {},
                }
            )

    def test_core_research_brief_receipt_marks_pending_as_needs_review(self):
        receipt = build_core_research_brief_receipt(
            {
                "receipt_id": "rbr_pending",
                "week_label": "2026-W22",
                "markdown_path": "data/output/digests/2026-W22.md",
                "verification_status": "pending",
                "source_set": {"source_evidence_item_ids": [101]},
            }
        )

        self.assertEqual(receipt["verifier_status"], "needs_review")
        self.assertTrue(receipt["verifier_notes"])

    def test_core_evidence_lookup_passes_for_resolved_refs(self):
        connection = self._make_evidence_connection([101])
        receipt = build_core_research_brief_receipt(
            {
                "receipt_id": "rbr_valid",
                "week_label": "2026-W22",
                "markdown_path": "data/output/digests/2026-W22.md",
                "verification_status": "verified",
                "source_set": {
                    "source_evidence_item_ids": [101],
                    "telegram_source_links": ["https://t.me/source_a/123"],
                },
            }
        )

        result = verify_core_research_brief_evidence_refs(connection, receipt)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["checked_ref_count"], 2)
        self.assertEqual(result["resolved_signal_evidence_item_ids"], [101])
        self.assertEqual(result["checked_telegram_source_links"], ["https://t.me/source_a/123"])
        self.assertEqual(result["failures"], [])
        self.assertFalse(result["runtime_dependency"])

    def test_core_evidence_lookup_fails_for_missing_signal_evidence_row(self):
        connection = self._make_evidence_connection([])
        receipt = build_core_research_brief_receipt(
            {
                "receipt_id": "rbr_missing",
                "week_label": "2026-W22",
                "markdown_path": "data/output/digests/2026-W22.md",
                "verification_status": "verified",
                "source_set": {"source_evidence_item_ids": [999]},
            }
        )

        result = verify_core_research_brief_evidence_refs(connection, receipt)

        self.assertEqual(result["status"], "failed")
        self.assertIn("missing signal_evidence_item refs: 999", result["failures"])

    def test_core_evidence_lookup_fails_for_malformed_telegram_link(self):
        connection = self._make_evidence_connection([])
        receipt = build_core_research_brief_receipt(
            {
                "receipt_id": "rbr_bad_link",
                "week_label": "2026-W22",
                "markdown_path": "data/output/digests/2026-W22.md",
                "verification_status": "verified",
                "source_set": {"telegram_source_links": ["https://example.com/not-telegram"]},
            }
        )

        result = verify_core_research_brief_evidence_refs(connection, receipt)

        self.assertEqual(result["status"], "failed")
        self.assertIn(
            "malformed Telegram source link: https://example.com/not-telegram",
            result["failures"],
        )


if __name__ == "__main__":
    unittest.main()
