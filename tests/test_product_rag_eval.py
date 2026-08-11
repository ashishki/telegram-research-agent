import json
import unittest
from pathlib import Path

from db.product_rag_eval import (
    ProductRagEvalError,
    build_product_rag_eval_manifest,
    build_product_rag_simulation_receipt,
    merge_product_rag_gold_cases,
    validate_product_rag_thresholds,
)


def _thresholds():
    return {
        "schema_version": "product_rag_thresholds.v1",
        "status": "proposed_pending_human_approval",
        "lower_bounds": {
            "recall_at_5": 0.7,
            "recall_at_10": 0.85,
            "citation_precision": 0.9,
            "no_answer_accuracy": 0.9,
            "stale_rejection": 0.85,
        },
        "upper_bounds": {
            "duplicate_top10_rate": 0.15,
            "latency_ms_p95": 1500,
        },
    }


def _cases():
    return [
        {
            "case_id": "PRAG-ARCH-001",
            "category": "archive_recall",
            "language": "ru",
            "query": "найди пост про RAG",
            "validation_status": "candidate_unapproved",
            "human_approved": False,
        },
        {
            "case_id": "PRAG-SEM-001",
            "category": "semantic_phrasing",
            "language": "ru",
            "query": "что у меня было про grounded answers",
            "validation_status": "candidate_unapproved",
            "human_approved": False,
        },
        {
            "case_id": "PRAG-PROJ-001",
            "category": "project_fit",
            "language": "ru",
            "query": "что применимо к telegram-research-agent",
            "validation_status": "candidate_unapproved",
            "human_approved": False,
        },
        {
            "case_id": "PRAG-LINK-001",
            "category": "linked_source_freshness",
            "language": "ru",
            "query": "какие ссылки надо проверить на свежесть",
            "validation_status": "candidate_unapproved",
            "human_approved": False,
        },
        {
            "case_id": "PRAG-NOANS-001",
            "category": "no_answer",
            "language": "ru",
            "query": "докажи то, чего нет в архиве",
            "validation_status": "candidate_unapproved",
            "human_approved": False,
        },
        {
            "case_id": "PRAG-DEC-001",
            "category": "decision_support",
            "language": "ru",
            "query": "что надо применить или игнорировать",
            "validation_status": "candidate_unapproved",
            "human_approved": False,
        },
    ]


class TestProductRagEval(unittest.TestCase):
    def test_simulation_receipt_is_explicitly_non_gating(self):
        receipt = build_product_rag_simulation_receipt([
            {"case_id": "PRAG-NOANS-001", "draft_status": "needs_operator_confirmation", "human_approved": False, "suggested_outcome": "expected_no_answer"},
            {"case_id": "PRAG-NOANS-004", "draft_status": "needs_operator_confirmation", "human_approved": False, "suggested_outcome": "external_verification_required"},
        ])
        self.assertEqual(receipt["status"], "non_gating_simulation_operator_confirmation_required")
        self.assertEqual(receipt["gold_labels"]["count"], 0)
        self.assertFalse(receipt["vector_backend_gate"]["embeddings_run"])

        with self.assertRaisesRegex(ProductRagEvalError, "human_approved=false"):
            build_product_rag_simulation_receipt([
                {"case_id": "PRAG-NOANS-001", "draft_status": "needs_operator_confirmation", "human_approved": True, "suggested_outcome": "expected_no_answer"},
            ])

    def test_prepared_drafts_are_not_gold_labels(self):
        draft_path = Path(__file__).resolve().parents[1] / "evals/retrieval/product_rag_gold_label_drafts.jsonl"
        drafts = [json.loads(line) for line in draft_path.read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertEqual(len(drafts), 7)
        self.assertTrue(all(row["human_approved"] is False for row in drafts))
        self.assertTrue(all(row["draft_status"] == "needs_operator_confirmation" for row in drafts))

    def test_operator_approved_generated_gold_labels_cover_all_product_rows(self):
        root = Path(__file__).resolve().parents[1]
        cases = [json.loads(line) for line in (root / "evals/retrieval/product_rag_candidate.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        labels = [json.loads(line) for line in (root / "evals/retrieval/product_rag_gold_labels.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        thresholds = json.loads((root / "evals/retrieval/product_rag_thresholds.json").read_text(encoding="utf-8"))

        self.assertEqual(len(labels), 50)
        self.assertEqual({row["case_id"] for row in labels}, {row["case_id"] for row in cases})
        self.assertTrue(all(row["human_approved"] is True for row in labels))
        self.assertTrue(all(row["human_approval_ref"] == "operator-approval-2026-08-11-all-50-generated-gold" for row in labels))
        self.assertTrue(all(row["label_source"] == "local_sqlite_fts_query_planner" for row in labels))
        self.assertTrue(all(row["raw_telegram_text_included"] is False for row in labels))
        no_answer_labels = [row for row in labels if row["case_id"].startswith("PRAG-NOANS-")]
        evidence_labels = [row for row in labels if not row["case_id"].startswith("PRAG-NOANS-")]
        self.assertEqual(len(no_answer_labels), 7)
        self.assertTrue(all(row["expected_no_answer"] is True for row in no_answer_labels))
        self.assertTrue(all("expected_archive_document_ids" not in row for row in no_answer_labels))
        self.assertEqual(len(evidence_labels), 43)
        self.assertTrue(all(row["expected_archive_document_ids"] for row in evidence_labels))
        self.assertTrue(all(row["retrieval_query_variants"] for row in evidence_labels))
        self.assertTrue(next(row for row in labels if row["case_id"] == "PRAG-NOANS-004")["external_verification_required"])

        manifest = build_product_rag_eval_manifest(cases, labels=labels, thresholds=thresholds)
        self.assertEqual(manifest["gold_labels"]["count"], 50)
        self.assertEqual(manifest["gold_labels"]["status"], "human_approved_gold_labels_present")
        self.assertEqual(manifest["gold_labels"]["coverage_status"], "full_coverage")
        self.assertEqual(manifest["vector_backend_gate"]["status"], "requires_human_approved_adr_before_vector_adoption")

    def test_manifest_accepts_privacy_safe_candidates_and_empty_gold_labels(self):
        manifest = build_product_rag_eval_manifest(_cases(), thresholds=_thresholds(), min_rows=6)

        self.assertEqual(manifest["schema_version"], "product_rag_eval_manifest.v1")
        self.assertEqual(manifest["dataset"]["case_count"], 6)
        self.assertEqual(manifest["gold_labels"]["count"], 0)
        self.assertEqual(manifest["gold_labels"]["status"], "blocked_no_human_approved_gold")
        self.assertEqual(manifest["gold_labels"]["coverage_status"], "no_coverage")
        self.assertFalse(manifest["privacy"]["queries_included"])
        self.assertFalse(manifest["vector_backend_gate"]["vector_backend_adopted"])

    def test_candidate_rows_must_not_include_gold_labels_or_raw_text(self):
        cases = _cases()
        cases[0] = {**cases[0], "expected_source_urls": ["https://t.me/source/1"]}

        with self.assertRaisesRegex(ProductRagEvalError, "forbidden candidate fields"):
            build_product_rag_eval_manifest(cases, thresholds=_thresholds(), min_rows=6)

        cases = _cases()
        cases[0] = {**cases[0], "snippet": "copied text"}
        with self.assertRaisesRegex(ProductRagEvalError, "forbidden candidate fields"):
            build_product_rag_eval_manifest(cases, thresholds=_thresholds(), min_rows=6)

    def test_gold_labels_must_be_human_approved_and_scoreable(self):
        with self.assertRaisesRegex(ProductRagEvalError, "human_approved=true"):
            build_product_rag_eval_manifest(
                _cases(),
                labels=[{"case_id": "PRAG-ARCH-001", "human_approved": False, "expected_post_ids": [1]}],
                thresholds=_thresholds(),
                min_rows=6,
            )

        with self.assertRaisesRegex(ProductRagEvalError, "expected source IDs/URLs"):
            build_product_rag_eval_manifest(
                _cases(),
                labels=[{"case_id": "PRAG-ARCH-001", "human_approved": True, "human_approval_ref": "operator-labels-2026-08-08"}],
                thresholds=_thresholds(),
                min_rows=6,
            )

        with self.assertRaisesRegex(ProductRagEvalError, "human_approval_ref"):
            build_product_rag_eval_manifest(
                _cases(),
                labels=[{"case_id": "PRAG-NOANS-001", "human_approved": True, "expected_no_answer": True}],
                thresholds=_thresholds(),
                min_rows=6,
            )

        manifest = build_product_rag_eval_manifest(
            _cases(),
            labels=[{"case_id": "PRAG-NOANS-001", "human_approved": True, "human_approval_ref": "operator-labels-2026-08-08", "expected_no_answer": True}],
            thresholds=_thresholds(),
            min_rows=6,
        )

        self.assertEqual(manifest["gold_labels"]["count"], 1)
        self.assertEqual(manifest["gold_labels"]["coverage_status"], "partial_coverage")
        self.assertEqual(manifest["vector_backend_gate"]["status"], "requires_human_approved_adr_before_vector_adoption")

    def test_gold_cases_merge_requires_approved_labels_and_keeps_candidate_file_label_free(self):
        cases = _cases()
        labels = [
            {"case_id": case["case_id"], "human_approved": True, "human_approval_ref": "operator-labels-2026-08-11", "expected_post_ids": [index]}
            for index, case in enumerate(cases, start=1)
        ]

        merged = merge_product_rag_gold_cases(cases, labels, min_rows=6)

        self.assertEqual(len(merged), 6)
        self.assertTrue(all(row["human_approved"] is True for row in merged))
        self.assertEqual(merged[0]["validation_status"], "human_approved_gold")
        self.assertEqual(merged[0]["query"], cases[0]["query"])
        self.assertNotIn("snippet", merged[0])

        with self.assertRaisesRegex(ProductRagEvalError, "missing gold labels"):
            merge_product_rag_gold_cases(cases, labels[:-1], min_rows=6)

    def test_thresholds_require_recall_citation_no_answer_stale_duplicate_and_latency(self):
        thresholds = _thresholds()
        del thresholds["lower_bounds"]["citation_precision"]

        with self.assertRaisesRegex(ProductRagEvalError, "citation_precision"):
            validate_product_rag_thresholds(thresholds)

        thresholds = _thresholds()
        thresholds["lower_bounds"]["recall_at_10"] = 0.5
        with self.assertRaisesRegex(ProductRagEvalError, "recall_at_10"):
            validate_product_rag_thresholds(thresholds)


if __name__ == "__main__":
    unittest.main()
