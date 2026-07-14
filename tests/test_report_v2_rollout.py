import unittest
from datetime import datetime, timezone

from output.intelligence_retrieval_items import IntelligenceRetrievalItem
from output.report_v2_rollout import (
    PUBLISHED_ROLLOUT_CONTRACTS,
    REPORT_V2_OPERATOR_COMMAND,
    REPORT_V2_ROLLOUT_RECEIPT_VERSION,
    build_report_v2_rollout_receipt_from_evidence,
)


RUN_AT = datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc)


class TestReportV2RolloutReceipt(unittest.TestCase):
    def _artifact_status(self):
        return {
            "status": "ok",
            "week_label": "2026-W28",
            "run_id": "rollout-run",
            "run_status": "complete",
            "manifest_path": "/tmp/weekly/rollout-run/manifest.json",
            "weekly_brief": {
                "status": "current",
                "json_path": "/tmp/weekly/rollout-run/weekly_brief/2026-W28.weekly-brief.json",
                "html_path": "/tmp/weekly/rollout-run/weekly_brief/2026-W28.weekly-brief.html",
            },
            "knowledge_atlas": {
                "status": "current",
                "json_path": "/tmp/weekly/rollout-run/knowledge_atlas/2026-W28.knowledge-atlas.json",
                "html_path": "/tmp/weekly/rollout-run/knowledge_atlas/2026-W28.knowledge-atlas.html",
            },
            "knowledge_atlas_v2": {"status": "current"},
            "knowledge_audit_explorer": {"status": "current"},
            "mvp_radar": {"status": "current"},
            "mvp_radar_gate": {
                "decision": "investigate",
                "radar_artifact_status": "loaded",
                "context_only_can_satisfy_gate": False,
            },
        }

    def _manifest(self):
        return {
            "schema_version": "weekly_run_manifest.v1",
            "run_id": "rollout-run",
            "run_status": "complete",
            "period_mode": "completed_iso_week",
            "stages": {
                "reaction_sync": {"status": "succeeded"},
                "feedback_snapshot": {"status": "succeeded"},
                "radar": {"status": "succeeded"},
                "editorial_intelligence": {"status": "succeeded"},
                "weekly_brief": {"status": "succeeded"},
                "knowledge_atlas": {"status": "succeeded"},
            },
        }

    def _items(self, *, include_feedback_receipt=True):
        items = [
            IntelligenceRetrievalItem(
                id="brief_v2:rollout-run:thesis",
                item_type="weekly_thesis",
                week_label="2026-W28",
                title="Brief V2",
                text="Reader thesis",
                schema_version="split_ai_report.v2",
                surface="weekly_brief",
                run_id="rollout-run",
            ),
            IntelligenceRetrievalItem(
                id="atlas_v2_thread:rollout-run:thread",
                item_type="atlas_v2_thread",
                week_label="2026-W28",
                title="Atlas V2",
                text="Reader atlas",
                schema_version="split_ai_report.v2",
                surface="knowledge_atlas",
                run_id="rollout-run",
            ),
            IntelligenceRetrievalItem(
                id="project_action:rollout-run:1",
                item_type="project_action",
                week_label="2026-W28",
                title="Project action",
                text="Concrete project implication",
                schema_version="split_ai_report.v2",
                surface="weekly_brief",
                run_id="rollout-run",
            ),
            IntelligenceRetrievalItem(
                id="reaction_effect:rollout-run",
                item_type="reaction_effect",
                week_label="2026-W28",
                title="Reaction receipt",
                text="Reaction effect receipt",
                schema_version="split_ai_report.v2",
                surface="weekly_brief",
                run_id="rollout-run",
            ),
        ]
        if include_feedback_receipt:
            items.append(
                IntelligenceRetrievalItem(
                    id="confirmed_feedback:rollout-run",
                    item_type="confirmed_feedback_effect",
                    week_label="2026-W28",
                    title="Feedback receipt",
                    text="Confirmed feedback receipt",
                    schema_version="split_ai_report.v2",
                    surface="weekly_brief",
                    run_id="rollout-run",
                )
            )
        return items

    def _fixture_manifest(self, *, recorded=True):
        return {
            "scenarios": [{"id": "release-candidate"}],
            "visual_regression": {
                "baseline_status": "recorded" if recorded else "prerequisite_required",
                "approved_snapshot_hashes": (
                    {
                        "desktop_1440": "a" * 64,
                        "mobile_375": "b" * 64,
                    }
                    if recorded
                    else {}
                ),
            },
        }

    def _complete_receipt(self, **overrides):
        defaults = {
            "week_label": "2026-W28",
            "artifact_status": self._artifact_status(),
            "manifest": self._manifest(),
            "manifest_path": "/tmp/weekly/rollout-run/manifest.json",
            "retrieval_items": self._items(),
            "brief_v2": {
                "schema_version": "split_ai_report.v2",
                "surface": "weekly_brief",
                "run_status": "complete",
                "partial": False,
                "visual_specs": [{"component_id": "brief-visual"}],
                "project_actions": [{"title": "Concrete project action"}],
            },
            "atlas_v2": {
                "schema_version": "split_ai_report.v2",
                "surface": "knowledge_atlas",
                "run_status": "complete",
                "partial": False,
                "visual_specs": [{"component_id": "atlas-visual"}],
            },
            "feedback_summary": {"status": "ok", "recent_events": [{"id": 1}]},
            "cost_summary": {"status": "passed", "total_cost_usd": 0.42, "max_weekly_cost_usd": 5.0},
            "fixture_manifest": self._fixture_manifest(recorded=True),
            "generated_at": RUN_AT,
        }
        defaults.update(overrides)
        return build_report_v2_rollout_receipt_from_evidence(**defaults)

    def test_receipt_passes_only_with_all_current_evidence(self):
        receipt = self._complete_receipt()

        self.assertEqual(receipt["schema_version"], REPORT_V2_ROLLOUT_RECEIPT_VERSION)
        self.assertEqual(receipt["dogfood_start_status"], "eligible")
        self.assertEqual(receipt["dogfood_week_1"]["status"], "not_started")
        self.assertEqual(receipt["operator_commands"]["v2_candidate_command"], REPORT_V2_OPERATOR_COMMAND)
        self.assertEqual(PUBLISHED_ROLLOUT_CONTRACTS["intelligence_contract"], "tra-intelligence-contract.v2")
        self.assertEqual(receipt["blocking_gates"], [])
        self.assertTrue(all(gate["status"] == "passed" for gate in receipt["gates"]))

    def test_missing_private_or_visual_evidence_blocks_without_claiming_dogfood(self):
        artifact_status = {
            "status": "missing",
            "week_label": "2026-W28",
            "weekly_brief": {"status": "missing"},
            "knowledge_atlas": {"status": "missing"},
            "mvp_radar": {"status": "missing"},
            "mvp_radar_gate": {
                "decision": "do_not_build",
                "radar_artifact_status": "missing",
                "context_only_can_satisfy_gate": False,
            },
        }

        receipt = self._complete_receipt(
            artifact_status=artifact_status,
            manifest=None,
            manifest_path=None,
            retrieval_items=[],
            brief_v2=None,
            atlas_v2=None,
            feedback_summary={"status": "missing"},
            cost_summary={"status": "blocked", "reason": "llm_usage_table_missing"},
            fixture_manifest=self._fixture_manifest(recorded=False),
        )

        self.assertEqual(receipt["dogfood_start_status"], "blocked")
        self.assertEqual(receipt["dogfood_week_1"]["status"], "not_started")
        self.assertIn("period", receipt["blocking_gates"])
        self.assertIn("visual", receipt["blocking_gates"])
        self.assertIn("cost", receipt["blocking_gates"])
        self.assertTrue(receipt["dogfood_policy"]["no_fabricated_evidence"])

    def test_no_feedback_is_ready_when_feedback_surface_is_readable(self):
        receipt = self._complete_receipt(
            retrieval_items=self._items(include_feedback_receipt=False),
            feedback_summary={"status": "ok", "recent_events": []},
        )

        feedback_gate = next(gate for gate in receipt["gates"] if gate["name"] == "feedback_readiness")
        self.assertEqual(feedback_gate["status"], "passed")
        self.assertEqual(receipt["dogfood_start_status"], "eligible")


if __name__ == "__main__":
    unittest.main()
