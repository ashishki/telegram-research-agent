from __future__ import annotations

import json
import unittest
from pathlib import Path

from evals.prm_release_gate import (
    EVALUATION_AREAS,
    FINAL_ACCEPTANCE_SCENARIOS,
    PRM_RELEASE_GATE_SCHEMA_VERSION,
    STOP_SHIP_CRITERIA,
    PRMReleaseGateValidationError,
    build_prm_release_gate_receipt,
    summarize_prm_release_gate,
    validate_prm_release_gate_receipt,
)


_REPO_ROOT = Path(__file__).resolve().parents[1]


def _passed_evaluations() -> dict[str, dict[str, object]]:
    return {
        area: {
            "status": "passed",
            "evidence_refs": [f"fixture://eval/{area}"],
        }
        for area in EVALUATION_AREAS
    }


def _passed_scenarios() -> list[dict[str, object]]:
    return [
        {
            "id": scenario_id,
            "status": "passed",
            "evidence_refs": [f"fixture://scenario/{scenario_id}"],
        }
        for scenario_id, _title in FINAL_ACCEPTANCE_SCENARIOS
    ]


def _clear_stop_ship() -> dict[str, dict[str, object]]:
    return {
        criterion: {
            "triggered": False,
            "evidence_refs": [f"fixture://stop-ship/{criterion}"],
        }
        for criterion in STOP_SHIP_CRITERIA
    }


class PRMReleaseGateTests(unittest.TestCase):
    def test_release_gate_records_all_acceptance_scenarios_and_blocks_dogfood(self) -> None:
        scenarios = _passed_scenarios()
        scenarios[1]["status"] = "blocked"
        evaluations = _passed_evaluations()
        evaluations["retrieval"] = {
            "status": "blocked",
            "evidence_refs": ["evals/retrieval/README.md"],
            "notes": "Candidate queries are not human-approved gold labels.",
        }
        stop_ship = _clear_stop_ship()
        stop_ship["unsupported_claims"] = {
            "triggered": True,
            "evidence_refs": ["docs/generation_eval.md"],
        }

        receipt = build_prm_release_gate_receipt(
            scenarios=scenarios,
            evaluations=evaluations,
            reviews=[
                {
                    "id": "prm13-17-review",
                    "area": "block_review",
                    "status": "resolved",
                    "evidence_refs": ["docs/audit/PRM_DEEP_REVIEW_PRM13_17_2026-07-29.md"],
                }
            ],
            stop_ship=stop_ship,
            generated_at="2026-07-29T12:00:00Z",
            project_commit="fixture-commit",
        )

        self.assertEqual(receipt["schema_version"], PRM_RELEASE_GATE_SCHEMA_VERSION)
        self.assertEqual(len(receipt["acceptance_scenarios"]), len(FINAL_ACCEPTANCE_SCENARIOS))
        self.assertEqual(
            {row["id"] for row in receipt["acceptance_scenarios"]},
            {scenario_id for scenario_id, _title in FINAL_ACCEPTANCE_SCENARIOS},
        )
        self.assertEqual(receipt["dogfood_gate"]["status"], "blocked")
        self.assertIn("scenario_not_passed:e2e_02_semantic_topic_multi_month", receipt["dogfood_gate"]["blocking_reasons"])
        self.assertIn("evaluation_not_passed:retrieval", receipt["dogfood_gate"]["blocking_reasons"])
        self.assertIn("stop_ship:unsupported_claims", receipt["dogfood_gate"]["blocking_reasons"])
        self.assertIn("missing_human_dogfood_start_approval", receipt["dogfood_gate"]["blocking_reasons"])
        self.assertFalse(receipt["dogfood_gate"]["dogfood_started"])
        self.assertFalse(receipt["dogfood_gate"]["release_claimed"])
        self.assertIn("dogfood=blocked", summarize_prm_release_gate(receipt))

    def test_release_gate_blocks_without_human_review_acceptance(self) -> None:
        receipt = build_prm_release_gate_receipt(
            scenarios=_passed_scenarios(),
            evaluations=_passed_evaluations(),
            reviews=[
                {
                    "id": "privacy-review",
                    "area": "privacy",
                    "status": "open",
                    "evidence_refs": ["docs/PRIVACY_THREAT_MODEL.md"],
                }
            ],
            stop_ship=_clear_stop_ship(),
            human_approval_ref=None,
        )

        self.assertEqual(receipt["dogfood_gate"]["status"], "blocked")
        self.assertIn("review_unresolved:privacy-review", receipt["dogfood_gate"]["blocking_reasons"])
        self.assertIn("missing_human_dogfood_start_approval", receipt["dogfood_gate"]["blocking_reasons"])

    def test_release_gate_can_be_eligible_only_with_all_passed_and_human_approval(self) -> None:
        receipt = build_prm_release_gate_receipt(
            scenarios=_passed_scenarios(),
            evaluations=_passed_evaluations(),
            reviews=[
                {
                    "id": "privacy-review",
                    "area": "privacy",
                    "status": "accepted_by_human",
                    "evidence_refs": ["fixture://approval/privacy"],
                }
            ],
            stop_ship=_clear_stop_ship(),
            human_approval_ref="fixture://approval/dogfood-start",
        )

        self.assertEqual(receipt["dogfood_gate"]["status"], "eligible")
        self.assertEqual(receipt["dogfood_gate"]["blocking_reasons"], [])
        self.assertFalse(receipt["dogfood_gate"]["dogfood_started"])
        self.assertFalse(receipt["dogfood_gate"]["release_claimed"])

    def test_validation_rejects_missing_scenario_evidence_or_raw_payload_fields(self) -> None:
        receipt = build_prm_release_gate_receipt(
            scenarios=_passed_scenarios(),
            evaluations=_passed_evaluations(),
            reviews=[
                {
                    "id": "privacy-review",
                    "area": "privacy",
                    "status": "resolved",
                    "evidence_refs": ["docs/PRIVACY_THREAT_MODEL.md"],
                }
            ],
            stop_ship=_clear_stop_ship(),
        )

        missing_evidence = dict(receipt)
        missing_evidence["acceptance_scenarios"] = [dict(item) for item in receipt["acceptance_scenarios"]]
        missing_evidence["acceptance_scenarios"][0]["evidence_refs"] = []
        with self.assertRaisesRegex(PRMReleaseGateValidationError, "evidence_refs must not be empty"):
            validate_prm_release_gate_receipt(missing_evidence)

        unsafe = dict(receipt)
        unsafe["raw_post_text"] = "Private Telegram text must not appear in release receipts"
        with self.assertRaisesRegex(PRMReleaseGateValidationError, "forbidden raw payload keys"):
            validate_prm_release_gate_receipt(unsafe)
        self.assertNotIn("Private Telegram text", json.dumps(receipt, ensure_ascii=False))

    def test_committed_prm18_receipt_is_valid_and_blocks_dogfood(self) -> None:
        receipt_path = _REPO_ROOT / "evals" / "prm18_release_gate_receipt_2026-07-29.json"
        with receipt_path.open(encoding="utf-8") as file:
            receipt = json.load(file)

        validated = validate_prm_release_gate_receipt(receipt)

        self.assertEqual(validated["dogfood_gate"]["status"], "blocked")
        self.assertFalse(validated["dogfood_gate"]["dogfood_started"])
        self.assertFalse(validated["dogfood_gate"]["release_claimed"])
        self.assertIn("missing_human_dogfood_start_approval", validated["dogfood_gate"]["blocking_reasons"])
        self.assertIn("stop_ship:unsupported_claims", validated["dogfood_gate"]["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
