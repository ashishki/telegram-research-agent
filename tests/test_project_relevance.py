import unittest

from output.project_relevance import score_project_relevance


class TestProjectRelevance(unittest.TestCase):
    def test_matching_keywords_returns_high_score(self):
        projects = [
            {
                "name": "gdev-agent",
                "description": "Multi-tenant AI triage service.",
                "focus": "service layer patterns, cost control, async FastAPI",
            }
        ]

        results = score_project_relevance("FastAPI async cost control", projects)

        self.assertGreaterEqual(results[0]["score"], 0.3)

    def test_no_overlap_returns_low_score(self):
        projects = [
            {
                "name": "gdev-agent",
                "description": "Multi-tenant AI triage service.",
                "focus": "service layer patterns, cost control, async FastAPI",
            },
            {
                "name": "film-school-assistant",
                "description": "Film school learning assistant bot.",
                "focus": "learning path design, content structuring, bot UX",
            },
        ]

        results = score_project_relevance("Quantum chemistry benchmark for protein folding", projects)

        self.assertTrue(all(result["score"] < 0.2 for result in results))

    def test_rationale_contains_matched_keywords(self):
        projects = [
            {
                "name": "gdev-agent",
                "description": "Multi-tenant AI triage service.",
                "focus": "service layer patterns, cost control, async FastAPI",
            }
        ]

        results = score_project_relevance("FastAPI cost control for async APIs", projects)

        self.assertIn("cost", results[0]["rationale"].lower())


if __name__ == "__main__":
    unittest.main()
