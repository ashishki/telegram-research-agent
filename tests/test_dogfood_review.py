import json
import tempfile
import unittest
from pathlib import Path

from output.dogfood_review import (
    WEEKLY_INTELLIGENCE_SCORECARD_VERSION,
    build_weekly_dogfood_review,
    build_weekly_intelligence_scorecard,
    build_weekly_intelligence_scorecard_from_files,
    validate_weekly_intelligence_scorecard,
    write_weekly_intelligence_scorecard,
    summarize_four_week_dogfood_reviews,
    write_weekly_dogfood_review,
)


class TestDogfoodReview(unittest.TestCase):
    def _metrics(self, *, value: int = 4, friction: int = 2) -> dict:
        return {
            "time_to_understand_week_minutes": 25,
            "sections_read": ["Decision Brief", "MVP Radar"],
            "read_items_completed": 1,
            "try_items_completed": 1,
            "experiments_completed": 0,
            "project_actions_created": 1,
            "feedback_events_count": 3,
            "wrong_priority_count": 1,
            "not_interested_count": 0,
            "applied_to_project_count": 1,
            "mvp_build_count": 0,
            "mvp_focused_experiment_count": 0,
            "mvp_investigate_count": 1,
            "mvp_reject_count": 0,
            "decisions_changed_by_system": ["Deferred a weak MVP idea"],
            "user_value_score_1_to_5": value,
            "friction_score_1_to_5": friction,
        }

    def test_build_weekly_review_records_required_metrics(self):
        review = build_weekly_dogfood_review(
            week_label="2026-W28",
            metrics=self._metrics(),
            notes={"best_explanation": "Eval gates", "simplify_next_week": "Shorter strategy message"},
            generated_at="2026-07-08T00:00:00Z",
        )

        self.assertEqual(review["status"], "ok")
        self.assertEqual(review["metrics"]["time_to_understand_week_minutes"], 25)
        self.assertEqual(review["metrics"]["sections_read"], ["Decision Brief", "MVP Radar"])
        self.assertEqual(review["review"]["feedback_signal_count"], 5)
        self.assertEqual(review["review"]["real_actions_completed"], 4)
        self.assertFalse(review["review"]["requires_simplification"])
        self.assertEqual(review["privacy"], "private_operator_artifact_do_not_commit_generated_outputs")

    def test_write_weekly_review_outputs_compact_private_artifacts(self):
        review = build_weekly_dogfood_review(
            week_label="2026-W28",
            metrics=self._metrics(),
            generated_at="2026-07-08T00:00:00Z",
        )
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_weekly_dogfood_review(review, Path(tmp))
            json_payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
            markdown = Path(paths["markdown"]).read_text(encoding="utf-8")

        self.assertEqual(json_payload["week_label"], "2026-W28")
        self.assertIn("# Dogfood Review 2026-W28", markdown)
        self.assertLess(len(markdown.splitlines()), 80)
        self.assertIn("private_operator_artifact_do_not_commit_generated_outputs", markdown)

    def test_missing_optional_metrics_default_without_crashing(self):
        review = build_weekly_dogfood_review(week_label="2026-W28", metrics={})

        self.assertIsNone(review["metrics"]["time_to_understand_week_minutes"])
        self.assertEqual(review["metrics"]["sections_read"], [])
        self.assertEqual(review["review"]["real_actions_completed"], 0)
        self.assertIsNone(review["metrics"]["user_value_score_1_to_5"])

    def test_four_week_summary_captures_success_criteria(self):
        reviews = [
            build_weekly_dogfood_review(week_label=f"2026-W{week}", metrics=self._metrics())
            for week in range(28, 32)
        ]
        summary = summarize_four_week_dogfood_reviews(reviews)

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["workbook_runs"], 4)
        self.assertGreaterEqual(summary["feedback_events_count"], 8)
        self.assertTrue(summary["success_criteria"]["four_workbook_runs"])
        self.assertTrue(summary["success_criteria"]["two_decisions_changed"])
        self.assertEqual(summary["recommendation"], "continue_hpi_as_is")

    def test_four_week_summary_recommends_simplification_when_friction_high(self):
        reviews = [
            build_weekly_dogfood_review(week_label="2026-W28", metrics=self._metrics(friction=2)),
            build_weekly_dogfood_review(week_label="2026-W29", metrics=self._metrics(friction=4)),
            build_weekly_dogfood_review(week_label="2026-W30", metrics=self._metrics(friction=5)),
        ]
        summary = summarize_four_week_dogfood_reviews(reviews)

        self.assertEqual(summary["recommendation"], "simplify_hermes_pi")

    def _weekly_brief_sidecar(self) -> dict:
        return {
            "artifact_type": "weekly_intelligence_brief",
            "week_label": "2026-W28",
            "json_path": "/tmp/2026-W28.weekly-brief.json",
            "artifact_paths": {"json": "/tmp/2026-W28.weekly-brief.json", "html": "/tmp/2026-W28.weekly-brief.html"},
            "report_contract": {"personalization_confidence": "unknown"},
            "intelligence_contract": {"contract_version": "tra-intelligence-contract.v1"},
            "quality_findings": [],
            "actions": [{"title": "Try eval guard"}],
            "project_learning_projection": {
                "learning_intelligence": {
                    "stage_counts": {
                        "read": 2,
                        "understood": 0,
                        "explained": 0,
                        "reproduced": 0,
                        "implemented": 1,
                        "tested": 1,
                        "project-applied": 0,
                        "measured": 0,
                        "stale": 0,
                        "prerequisite_gap": 1,
                    },
                    "objectives": [
                        {"id": "learning-objective:atom:1", "stage": "read", "mastery_claim": "not_claimed"},
                        {"id": "learning-objective:action:1", "stage": "tested", "mastery_claim": "evidence_bounded"},
                    ],
                }
            },
            "mvp_radar_gate": {
                "decision": "do_not_build",
                "matched_gate_evidence_count": 0,
                "context_only_can_satisfy_gate": False,
                "radar_artifact_status": "loaded",
            },
        }

    def _knowledge_atlas_sidecar(self) -> dict:
        return {
            "artifact_type": "knowledge_atlas",
            "week_label": "2026-W28",
            "json_path": "/tmp/2026-W28.knowledge-atlas.json",
            "artifact_paths": {"json": "/tmp/2026-W28.knowledge-atlas.json", "html": "/tmp/2026-W28.knowledge-atlas.html"},
            "quality_findings": [{"severity": "warning", "message": "Fixture warning"}],
        }

    def test_weekly_scorecard_records_dimensions_unknowns_and_incidents(self):
        dogfood = build_weekly_dogfood_review(
            week_label="2026-W28",
            metrics=self._metrics(),
            generated_at="2026-07-08T00:00:00Z",
        )

        scorecard = build_weekly_intelligence_scorecard(
            week_label="2026-W28",
            weekly_brief=self._weekly_brief_sidecar(),
            knowledge_atlas=self._knowledge_atlas_sidecar(),
            dogfood_review=dogfood,
            observations={
                "brief_first_screen_task_success": True,
                "test_regression_count": 0,
                "false_confidence_incidents": [
                    {
                        "severity": "medium",
                        "description": "A draft claim sounded stronger than its evidence.",
                        "source_refs": ["tests/fixtures/intelligence_contract/valid_canonical_sidecar.json"],
                    }
                ],
            },
            generated_at="2026-07-09T00:00:00Z",
        )

        self.assertEqual(scorecard["schema_version"], WEEKLY_INTELLIGENCE_SCORECARD_VERSION)
        self.assertEqual(set(scorecard["dimensions"]), {
            "correctness",
            "relevance",
            "decisions_actions",
            "learning",
            "ux",
            "radar",
            "operations",
        })
        self.assertEqual(scorecard["summary"]["quality_finding_count"], 1)
        self.assertEqual(scorecard["summary"]["false_confidence_incident_count"], 1)
        self.assertIn("correctness.unsupported_claim_rate", scorecard["unknown_metrics"])
        self.assertIn("relevance.personalization_confidence", scorecard["unknown_metrics"])
        self.assertIn("operations.generation_cost_usd", scorecard["unknown_metrics"])
        self.assertEqual(
            scorecard["dimensions"]["radar"]["metrics"]["context_only_gate_violation_count"]["value"],
            0,
        )
        self.assertEqual(
            scorecard["dimensions"]["learning"]["metrics"]["implemented_or_tested_objective_count"]["value"],
            2,
        )
        self.assertEqual(validate_weekly_intelligence_scorecard(scorecard), [])

    def test_weekly_scorecard_can_run_from_sanitized_fixture_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            brief_path = root / "weekly-brief.json"
            atlas_path = root / "knowledge-atlas.json"
            observations_path = root / "observations.json"
            brief_path.write_text(json.dumps(self._weekly_brief_sidecar()), encoding="utf-8")
            atlas_path.write_text(json.dumps(self._knowledge_atlas_sidecar()), encoding="utf-8")
            observations_path.write_text(
                json.dumps({"false_confidence_incidents": [], "atlas_find_source_task_success": True}),
                encoding="utf-8",
            )

            scorecard = build_weekly_intelligence_scorecard_from_files(
                week_label="2026-W28",
                weekly_brief_json_path=brief_path,
                knowledge_atlas_json_path=atlas_path,
                observations_json_path=observations_path,
                generated_at="2026-07-09T00:00:00Z",
            )
            paths = write_weekly_intelligence_scorecard(scorecard, root)
            markdown = Path(paths["markdown"]).read_text(encoding="utf-8")

        self.assertEqual(scorecard["source_artifacts"]["weekly_brief_json_path"], str(brief_path))
        self.assertIn("# Weekly Intelligence Scorecard 2026-W28", markdown)
        self.assertIn("correctness", markdown)
        self.assertEqual(validate_weekly_intelligence_scorecard(scorecard), [])

    def test_scorecard_validator_rejects_missing_dimensions(self):
        findings = validate_weekly_intelligence_scorecard(
            {
                "schema_version": WEEKLY_INTELLIGENCE_SCORECARD_VERSION,
                "dimensions": {},
                "unknown_metrics": ["bad-ref"],
                "false_confidence_incidents": [{"severity": "high"}],
            }
        )

        self.assertIn("missing_dimension:correctness", findings)
        self.assertIn("invalid_unknown_metric_ref", findings)
        self.assertIn("missing_false_confidence_description:1", findings)


if __name__ == "__main__":
    unittest.main()
