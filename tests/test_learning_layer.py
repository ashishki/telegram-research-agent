import unittest

from output.learning_layer import LEARNING_STAGES, build_project_learning_projection, extract_learning_gaps


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
        self.assertEqual(stages["learning-objective:action:action-1"], "prerequisite_gap")
        self.assertEqual(stages["learning-objective:action:action-2"], "measured")
        self.assertEqual(learning["feedback_state"], "unknown")
        self.assertTrue(project["rejected_overlaps"])


if __name__ == "__main__":
    unittest.main()
