import unittest

from output.learning_layer import (
    LEARNING_STAGES,
    build_project_learning_projection,
    extract_learning_gaps,
    learning_feedback_display,
    migrate_legacy_learning_records,
)


class TestLearningLayer(unittest.TestCase):
    def test_topic_not_in_project_focus_is_returned_as_gap(self):
        posts = [
            {"content": "Langchain agent orchestration patterns", "bucket": "strong", "signal_score": 0.9},
            {"content": "Langchain memory and retrieval updates", "bucket": "strong", "signal_score": 0.88},
            {"content": "Langchain chains for production workflows", "bucket": "watch", "signal_score": 0.7},
            {"content": "Langchain observability in multi-step pipelines", "bucket": "watch", "signal_score": 0.68},
            {"content": "Langchain tools for agent execution", "bucket": "watch", "signal_score": 0.66},
        ]
        projects = [
            {
                "name": "gdev-agent",
                "description": "Multi-tenant AI triage service. FastAPI, PostgreSQL/pgvector, Redis.",
                "focus": "service layer patterns, eval pipeline, cost control, async FastAPI",
            }
        ]

        gaps = extract_learning_gaps(posts, projects)

        self.assertTrue(any(gap["topic"] == "langchain" and gap["frequency"] == 5 for gap in gaps))

    def test_topic_in_project_focus_is_not_a_gap(self):
        posts = [
            {"content": "FastAPI service patterns for async systems", "bucket": "strong", "signal_score": 0.9},
            {"content": "FastAPI eval hooks for backend APIs", "bucket": "strong", "signal_score": 0.88},
            {"content": "FastAPI deployment guardrails and routing", "bucket": "watch", "signal_score": 0.7},
            {"content": "FastAPI middleware for cost control", "bucket": "watch", "signal_score": 0.68},
            {"content": "FastAPI async performance tuning", "bucket": "watch", "signal_score": 0.66},
        ]
        projects = [
            {
                "name": "gdev-agent",
                "description": "Multi-tenant AI triage service. FastAPI, PostgreSQL/pgvector, Redis.",
                "focus": "service layer patterns, eval pipeline, cost control, multi-tenant RLS, async FastAPI",
            }
        ]

        gaps = extract_learning_gaps(posts, projects)

        self.assertNotIn("fastapi", {gap["topic"] for gap in gaps})

    def test_project_learning_projection_keeps_context_and_stage_boundaries(self):
        projection = build_project_learning_projection(
            {
                "week_label": "2026-W28",
                "threads": [
                    {
                        "slug": "market-adoption",
                        "title": "Market adoption",
                        "atoms": [
                            {
                                "id": 1,
                                "claim": "Teams ask for adoption evidence before expanding AI usage.",
                                "atom_type": "market_signal",
                                "source_urls": ["https://t.me/market/1"],
                            }
                        ],
                    }
                ],
                "feedback_context": {"event_count": 0},
            },
            actions=[
                {
                    "id": "action-1",
                    "title": "Implement adoption metric",
                    "next_step": "Write code",
                    "success_criterion": "Metric is tested",
                },
                {
                    "id": "action-2",
                    "title": "Measure applied eval gate",
                    "source_atom_ids": [1],
                    "feedback_types": ["measured"],
                    "outcome_evidence": ["metric improved"],
                },
            ],
            project_diagnostic={
                "rejected_broad_overlaps": [{"project": "agent", "term": "workflow", "reason": "broad_overlap_suppressed"}],
                "missing_evidence": ["Need project-specific source."],
            },
        )

        project = projection["project_intelligence"]
        learning = projection["learning_intelligence"]

        self.assertEqual(project["external_signals"][0]["context_policy"], "context_only")
        self.assertEqual(set(learning["allowed_stages"]), set(LEARNING_STAGES))
        stages = {item["id"]: item["stage"] for item in learning["objectives"]}
        self.assertEqual(stages["learning-objective:atom:1"], "surfaced")
        self.assertEqual(stages["learning-objective:action:action-1"], "surfaced")
        self.assertEqual(stages["learning-objective:action:action-2"], "measured")
        self.assertEqual(learning["feedback_state"], "unknown")
        self.assertEqual(learning["no_feedback_label"], "unknown")
        self.assertTrue(project["rejected_overlaps"])

    def test_legacy_source_presence_maps_to_indexed_or_surfaced_only(self):
        rows = migrate_legacy_learning_records(
            [
                {
                    "id": "legacy-source-url",
                    "stage": "read",
                    "source_url": "https://t.me/source/1",
                },
                {
                    "id": "legacy-surfaced",
                    "learning_stage": "read",
                    "source_atom_ids": [101],
                    "surface_id": "brief:item:1",
                },
                {
                    "id": "explicit-read",
                    "learning_stage": "read",
                    "source_refs": ["https://t.me/source/2"],
                    "learning_evidence_receipts": [
                        {"stage": "read", "receipt_id": "feedback:read:1"}
                    ],
                },
            ]
        )

        by_id = {item["id"]: item for item in rows}
        self.assertEqual(by_id["legacy-source-url"]["learning_state"], "indexed")
        self.assertEqual(by_id["legacy-surfaced"]["learning_state"], "surfaced")
        self.assertEqual(by_id["explicit-read"]["learning_state"], "read")
        self.assertEqual(
            by_id["legacy-source-url"]["migration_policy"],
            "legacy_source_presence_maps_to_indexed_or_surfaced_only",
        )

    def test_progress_states_require_explicit_evidence_receipts(self):
        rows = migrate_legacy_learning_records(
            [
                {
                    "id": "fabricated-applied",
                    "stage": "implemented",
                    "source_refs": ["https://t.me/source/1"],
                },
                {
                    "id": "explicit-applied",
                    "stage": "implemented",
                    "source_refs": ["https://t.me/source/1"],
                    "feedback_types": ["applied_to_project"],
                },
                {
                    "id": "explicit-measured",
                    "stage": "tested",
                    "outcome_evidence": ["metric improved"],
                },
            ]
        )

        by_id = {item["id"]: item for item in rows}
        self.assertEqual(by_id["fabricated-applied"]["learning_state"], "surfaced")
        self.assertEqual(by_id["explicit-applied"]["learning_state"], "applied")
        self.assertEqual(by_id["explicit-measured"]["learning_state"], "measured")

    def test_no_feedback_display_is_unknown(self):
        self.assertEqual(learning_feedback_display({}), "unknown")
        self.assertEqual(learning_feedback_display({"event_count": 0}), "unknown")
        self.assertEqual(learning_feedback_display({"feedback_types": ["read"]}), "observed")


if __name__ == "__main__":
    unittest.main()
