import unittest

from output.learning_layer import extract_learning_gaps


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


if __name__ == "__main__":
    unittest.main()
