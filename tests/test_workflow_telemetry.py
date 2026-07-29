from __future__ import annotations

import json
import unittest

from processing.workflow_telemetry import (
    DEFAULT_WEEKLY_COST_LIMIT_USD,
    DEFAULT_WEEKLY_MODEL_CALL_LIMIT,
    REQUIRED_TELEMETRY_METRICS,
    WORKFLOW_CONTRACT_REQUIRED_FIELDS,
    WorkflowTelemetryValidationError,
    assert_no_private_telemetry_text,
    build_workflow_telemetry_receipt,
    get_autonomous_workflow_contracts,
    validate_autonomous_workflow_contracts,
    validate_workflow_telemetry_receipt,
)


PRIVATE_TEXT = "Private Telegram post about unreleased roadmap details"


class WorkflowTelemetryTests(unittest.TestCase):
    def test_autonomous_workflow_contracts_cover_prm17_required_routines(self) -> None:
        contracts = get_autonomous_workflow_contracts()
        receipt = validate_autonomous_workflow_contracts(contracts)

        self.assertEqual(receipt["status"], "passed")
        workflows = {contract["workflow"] for contract in contracts}
        self.assertTrue(
            {
                "telegram_ingestion",
                "archive_indexing",
                "reaction_fast_lane",
                "selective_enrichment",
                "weekly_brief_v3",
                "backup_snapshot",
                "rollback_reindex_dry_run",
            }.issubset(workflows)
        )
        for contract in contracts:
            for field in WORKFLOW_CONTRACT_REQUIRED_FIELDS:
                self.assertIn(field, contract)
            self.assertIsInstance(contract["inputs"], list)
            self.assertIsInstance(contract["outputs"], list)
            self.assertIsInstance(contract["retry_policy"], dict)
            self.assertIn("max_retries", contract["retry_policy"])
            self.assertNotIn(PRIVATE_TEXT, json.dumps(contract, ensure_ascii=False))

    def test_workflow_telemetry_records_required_metrics_and_budget_status(self) -> None:
        receipt = build_workflow_telemetry_receipt(
            workflow="selective_enrichment",
            run_id="run-2026-W30-enrichment",
            idempotency_key="selective_enrichment:fixture:2026-W30",
            observed_at="2026-07-29T11:00:00Z",
            metrics={
                "index_freshness_seconds": 480,
                "queue_age_seconds": 120,
                "retrieval_latency_ms": 42,
                "generation_latency_ms": 2700,
                "model_cost_usd": 0.17,
                "model_calls": 3,
                "tool_calls": 4,
                "no_answer_count": 2,
                "answered_count": 8,
                "weekly_cost_usd": DEFAULT_WEEKLY_COST_LIMIT_USD + 0.01,
                "weekly_model_calls": DEFAULT_WEEKLY_MODEL_CALL_LIMIT,
            },
        )

        self.assertEqual(receipt["schema_version"], "workflow_telemetry_receipt.v1")
        for field in REQUIRED_TELEMETRY_METRICS:
            self.assertIn(field, receipt["metrics"])
        self.assertEqual(receipt["metrics"]["no_answer_rate"], 0.2)
        self.assertEqual(receipt["error"]["class"], "none")
        self.assertFalse(receipt["error"]["message_logged"])
        self.assertTrue(receipt["budget"]["approval_required"])
        self.assertFalse(receipt["privacy"]["raw_post_text_logged"])
        self.assertFalse(receipt["privacy"]["provider_payload_logged"])
        self.assertFalse(receipt["privacy"]["raw_telegram_corpus_egress"])

    def test_workflow_telemetry_redacts_raw_text_and_error_messages(self) -> None:
        receipt = build_workflow_telemetry_receipt(
            workflow="weekly_brief_v3",
            run_id="run-2026-W30-brief",
            idempotency_key="weekly_brief_v3:2026-W30:fixture",
            observed_at="2026-07-29T11:10:00Z",
            metrics={
                "index_freshness_seconds": 30,
                "queue_age_seconds": 10,
                "retrieval_latency_ms": 12,
                "generation_latency_ms": 18,
                "model_cost_usd": 0.0,
                "model_calls": 0,
                "tool_calls": 0,
                "no_answer_count": 0,
                "answered_count": 1,
                "raw_post_text": PRIVATE_TEXT,
                "provider_payload": {"prompt": PRIVATE_TEXT, "completion": PRIVATE_TEXT},
            },
            error=RuntimeError(PRIVATE_TEXT),
        )

        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["error"]["class"], "RuntimeError")
        self.assertIn("raw_post_text", receipt["privacy"]["redacted_fields"])
        self.assertIn("provider_payload", receipt["privacy"]["redacted_fields"])
        self.assertIn("error.message", receipt["privacy"]["redacted_fields"])
        self.assertNotIn(PRIVATE_TEXT, json.dumps(receipt, ensure_ascii=False))
        self.assertEqual(
            assert_no_private_telemetry_text(receipt, [PRIVATE_TEXT]),
            {"status": "passed", "checked_text_count": 1},
        )

    def test_validation_rejects_unsafe_receipt_payload_fields_or_private_text(self) -> None:
        receipt = build_workflow_telemetry_receipt(
            workflow="archive_indexing",
            run_id="run-2026-W30-index",
            idempotency_key="archive_indexing:fixture",
            metrics={
                "index_freshness_seconds": 5,
                "queue_age_seconds": 0,
                "retrieval_latency_ms": 7,
                "generation_latency_ms": 0,
                "model_cost_usd": 0.0,
                "model_calls": 0,
                "tool_calls": 1,
                "no_answer_count": 0,
                "answered_count": 0,
            },
        )

        unsafe = dict(receipt)
        unsafe["raw_post_text"] = PRIVATE_TEXT
        with self.assertRaisesRegex(WorkflowTelemetryValidationError, "forbidden raw payload keys"):
            validate_workflow_telemetry_receipt(unsafe)

        with self.assertRaisesRegex(WorkflowTelemetryValidationError, "private text leaked"):
            assert_no_private_telemetry_text(receipt, ["archive_indexing"])


if __name__ == "__main__":
    unittest.main()
