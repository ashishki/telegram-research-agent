import sqlite3
import unittest

from proof_receipts import (
    build_core_research_brief_receipt,
    core_receipt_sha256,
    summarize_research_brief_evidence,
    verify_core_research_brief_evidence_refs,
)


class TestCoreResearchBriefReceipt(unittest.TestCase):
    REQUIRED_CORE_FIELDS = {
        "type": str,
        "schema_version": str,
        "product_id": str,
        "receipt_id": str,
        "week_label": str,
        "artifact_ref": str,
        "artifact_sha256": str,
        "generated_at": str,
        "evidence_refs": list,
        "verifier_status": str,
        "verifier_notes": list,
        "entropy_core_level": str,
    }

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

    def test_core_research_brief_receipt_schema_contract_is_pinned(self):
        receipt = build_core_research_brief_receipt(
            {
                "receipt_id": "rbr_schema",
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

        self.assertEqual(set(receipt), set(self.REQUIRED_CORE_FIELDS))
        for field, expected_type in self.REQUIRED_CORE_FIELDS.items():
            self.assertIsInstance(receipt[field], expected_type, field)
        self.assertEqual(receipt["schema_version"], "entropy_core.product_receipt.v1")
        self.assertEqual(receipt["verifier_status"], "passed")
        self.assertRegex(receipt["artifact_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(len(receipt["evidence_refs"]), 2)
        for evidence_ref in receipt["evidence_refs"]:
            self.assertEqual(
                set(evidence_ref),
                {"ref_id", "ref_type", "supports", "checksum_sha256"},
            )
            self.assertIsInstance(evidence_ref["ref_id"], str)
            self.assertIsInstance(evidence_ref["ref_type"], str)
            self.assertIsInstance(evidence_ref["supports"], str)
            self.assertRegex(evidence_ref["checksum_sha256"], r"^[0-9a-f]{64}$")

    def test_core_receipt_hash_is_deterministic_for_equivalent_payloads(self):
        payload_a = {
            "type": "research_brief_receipt",
            "schema_version": "entropy_core.product_receipt.v1",
            "product_id": "telegram-research-agent",
            "receipt_id": "rbr_hash",
            "week_label": "2026-W22",
            "artifact_ref": "data/output/digests/2026-W22.md",
            "artifact_sha256": "0" * 64,
            "generated_at": "2026-05-31T09:00:00Z",
            "evidence_refs": [
                {
                    "ref_id": "signal_evidence_item:101",
                    "ref_type": "signal_evidence_item",
                    "supports": "2026-W22",
                    "checksum_sha256": "1" * 64,
                }
            ],
            "verifier_status": "passed",
            "verifier_notes": [],
            "entropy_core_level": "evidence_lookup_compatible",
        }
        payload_b = {
            "week_label": "2026-W22",
            "receipt_id": "rbr_hash",
            "product_id": "telegram-research-agent",
            "schema_version": "entropy_core.product_receipt.v1",
            "type": "research_brief_receipt",
            "artifact_ref": "data/output/digests/2026-W22.md",
            "generated_at": "2026-05-31T09:00:00Z",
            "artifact_sha256": "0" * 64,
            "evidence_refs": payload_a["evidence_refs"],
            "entropy_core_level": "evidence_lookup_compatible",
            "verifier_notes": [],
            "verifier_status": "passed",
        }

        self.assertEqual(core_receipt_sha256(payload_a), core_receipt_sha256(payload_b))

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

    def test_research_brief_evidence_summary_counts_verified_refs_and_channels(self):
        connection = self._make_evidence_connection([101])
        connection.execute(
            "CREATE TABLE posts (id INTEGER PRIMARY KEY, channel_username TEXT)"
        )
        connection.executemany(
            "INSERT INTO posts (id, channel_username) VALUES (?, ?)",
            [(1, "source_a"), (2, "source_a"), (3, "source_b")],
        )
        connection.commit()

        summary = summarize_research_brief_evidence(
            connection,
            {
                "receipt_id": "rbr_summary",
                "week_label": "2026-W22",
                "markdown_path": "data/output/digests/2026-W22.md",
                "verification_status": "verified",
                "post_counts": {"strong_count": 1, "watch_count": 0},
                "source_set": {
                    "source_evidence_item_ids": [101],
                    "telegram_source_links": ["https://t.me/source_a/123"],
                    "source_post_ids": [1, 2, 3],
                },
            },
        )

        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["local_evidence_row_count"], 1)
        self.assertEqual(summary["telegram_source_link_count"], 1)
        self.assertEqual(summary["top_channels"][0], {"channel": "source_a", "count": 2})
        self.assertEqual(summary["confidence_level"], "medium")
        self.assertFalse(summary["runtime_dependency"])

    def test_research_brief_evidence_summary_marks_missing_refs_failed(self):
        connection = self._make_evidence_connection([])

        summary = summarize_research_brief_evidence(
            connection,
            {
                "receipt_id": "rbr_empty",
                "week_label": "2026-W22",
                "markdown_path": "data/output/digests/2026-W22.md",
                "verification_status": "pending",
                "post_counts": {"strong_count": 0, "watch_count": 0},
                "source_set": {},
            },
        )

        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["local_evidence_row_count"], 0)
        self.assertEqual(summary["telegram_source_link_count"], 0)
        self.assertEqual(summary["confidence_level"], "low")
        self.assertIn("source evidence refs", summary["failures"][0])


if __name__ == "__main__":
    unittest.main()
