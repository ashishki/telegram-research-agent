import unittest

from output.action_status import build_action_status_projection, summarize_action_statuses


class TestActionStatusProjection(unittest.TestCase):
    def _workbook(self) -> dict:
        return {
            "week_label": "2026-W28",
            "action_cards": [
                {
                    "id": "action-1",
                    "target_ref": "action-1",
                    "feedback_target_id": "action-1-feedback",
                    "title": "Try eval gate",
                    "action_kind": "try",
                    "follow_up_hint": "Report tried/useful or reject.",
                    "outcome_policy": "Do not count without feedback.",
                },
                {
                    "id": "action-2",
                    "target_ref": "action-2",
                    "feedback_target_id": "action-2-feedback",
                    "title": "Apply to Radar",
                    "action_kind": "experiment",
                },
                {
                    "id": "action-3",
                    "target_ref": "action-3",
                    "feedback_target_id": "action-3-feedback",
                    "title": "Read source",
                    "action_kind": "try",
                },
            ],
        }

    def test_projects_action_status_from_confirmed_feedback(self):
        items = build_action_status_projection(
            self._workbook(),
            [
                {
                    "feedback_type": "tried",
                    "target_type": "action",
                    "target_ref": "action-1-feedback",
                    "created_at": "2026-07-08T10:00:00Z",
                    "source_url": "https://t.me/ai_lab/101",
                },
                {
                    "feedback_type": "wrong_priority",
                    "target_type": "action",
                    "target_ref": "action-2",
                    "created_at": "2026-07-08T11:00:00Z",
                },
            ],
        )

        by_id = {item["action_id"]: item for item in items}
        self.assertEqual(by_id["action-1"]["status"], "tried")
        self.assertEqual(by_id["action-1"]["source_refs"], ["https://t.me/ai_lab/101"])
        self.assertEqual(by_id["action-2"]["status"], "wrong_priority")
        self.assertEqual(by_id["action-3"]["status"], "unknown")
        self.assertEqual(summarize_action_statuses(items)["unknown"], 1)

    def test_missing_feedback_stays_unknown_not_negative(self):
        items = build_action_status_projection(self._workbook(), [])

        self.assertTrue(items)
        self.assertTrue(all(item["status"] == "unknown" for item in items))
        self.assertEqual(summarize_action_statuses(items)["not_interested"], 0)
        self.assertEqual(summarize_action_statuses(items)["wrong_priority"], 0)


if __name__ == "__main__":
    unittest.main()
