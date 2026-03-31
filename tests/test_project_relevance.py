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

    def test_exclude_keywords_suppress_score_below_threshold(self):
        projects = [
            {
                "name": "telegram-research-agent",
                "description": "Weekly digest from Telegram channels.",
                "focus": "digest quality, clustering accuracy",
                "keywords": ["digest", "clustering", "signal"],
                "exclude_keywords": ["film"],
            }
        ]

        results = score_project_relevance("Telegram digest clustering for film students", projects)

        self.assertLess(results[0]["score"], 0.1)
        self.assertIn("excluded", results[0]["rationale"].lower())

    def test_explicit_keywords_list_used_for_matching(self):
        projects = [
            {
                "name": "ai-workflow-playbook",
                "description": "Reusable AI workflow.",
                "focus": "",
                "keywords": ["workflow", "automation", "agent"],
            }
        ]

        results = score_project_relevance("Agent workflow automation for code review", projects)

        self.assertGreaterEqual(results[0]["score"], 0.3)

    def test_rationale_includes_matched_explicit_keyword(self):
        projects = [
            {
                "name": "ai-workflow-playbook",
                "description": "Reusable AI workflow.",
                "focus": "",
                "keywords": ["workflow", "automation", "agent"],
            }
        ]

        results = score_project_relevance("Workflow automation for code review", projects)

        self.assertIn("workflow", results[0]["rationale"].lower())


if __name__ == "__main__":
    unittest.main()
