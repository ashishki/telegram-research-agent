import json
import tempfile
import unittest
from pathlib import Path

from output.dogfood_review import (
    build_weekly_dogfood_review,
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


if __name__ == "__main__":
    unittest.main()
