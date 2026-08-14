import unittest
from pathlib import Path

from assistant.project_portfolio_context import (
    PROJECT_PORTFOLIO_CONTEXT_SCHEMA_VERSION,
    default_project_portfolio,
    project_action_recommendation_allowed,
    select_project_portfolio_context,
    validate_project_portfolio_context,
)
from assistant.project_context import load_project_descriptors


def _project(name: str, status: str, *, confirmed: str = "confirmed", priority: int = 1) -> dict:
    return {
        "name": name,
        "status": status,
        "priority": priority,
        "current_goal": "prove one bounded workflow",
        "current_blocker": "needs evidence",
        "next_proof": "one fixture test",
        "preferred_signal_types": ["eval case"],
        "owner_confirmation_status": confirmed,
        "capabilities": ["eval"],
        "aliases": [name],
        "reviewed_metadata": "operator-approved-2026-08-14",
        "source_metadata": "local-project-config",
    }


class TestProjectPortfolioContext(unittest.TestCase):
    def test_project_context_v2_schema(self):
        project = validate_project_portfolio_context(_project("memory", "priority"))

        self.assertEqual(project["schema_version"], PROJECT_PORTFOLIO_CONTEXT_SCHEMA_VERSION)
        self.assertEqual(project["status"], "priority")
        self.assertEqual(project["priority"], 1)
        self.assertEqual(project["capabilities"], ["eval"])
        self.assertEqual(project["aliases"], ["memory"])
        with self.assertRaises(ValueError):
            validate_project_portfolio_context(_project("invalid", "not-a-status"))

    def test_default_project_set_excludes_watch_reference(self):
        projects = [
            _project("priority", "priority", priority=2),
            _project("active", "active", priority=1),
            _project("watch", "watch"),
            _project("reference", "reference"),
            _project("unconfirmed", "priority", confirmed="proposed"),
        ]

        selected = select_project_portfolio_context(projects)

        self.assertEqual([project["name"] for project in selected], ["active", "priority"])
        explicit = select_project_portfolio_context(projects, named_project="watch")
        self.assertEqual([project["name"] for project in explicit], ["watch"])

    def test_keyword_overlap_is_not_project_action(self):
        active = _project("active", "priority")
        watch = _project("watch", "watch")

        self.assertFalse(project_action_recommendation_allowed(active, direct_evidence=False))
        self.assertTrue(project_action_recommendation_allowed(active, direct_evidence=True))
        self.assertFalse(project_action_recommendation_allowed(watch, direct_evidence=True))

    def test_real_v2_config_excludes_non_routable_legacy_records(self):
        path = Path(__file__).resolve().parents[1] / "src" / "config" / "projects.yaml"
        projects = load_project_descriptors(path)
        self.assertEqual(len(projects), 10)
        self.assertNotIn("entropy_protocol", {project["name"] for project in projects})
        self.assertTrue(all(project["schema_version"] == PROJECT_PORTFOLIO_CONTEXT_SCHEMA_VERSION for project in projects))
        self.assertTrue(all(project["reviewed_metadata"] == "operator-approved-2026-08-14" for project in projects))


if __name__ == "__main__":
    unittest.main()
