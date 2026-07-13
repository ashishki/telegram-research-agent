import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from config.settings import Settings
from output.knowledge_atlas_report import KnowledgeAtlasSummary
from output.split_intelligence_reports import (
    deliver_split_intelligence_reports,
    generate_split_intelligence_reports,
)
from output.weekly_intelligence_brief import WeeklyIntelligenceBriefSummary


PROJECT_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "report_v2"
    / "project_intelligence_v2_cases.v1.json"
)


class TestProjectIntelligenceSplit(unittest.TestCase):
    def _settings(self) -> Settings:
        return Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="",
            telegram_session_path="",
        )

    def _brief(self) -> WeeklyIntelligenceBriefSummary:
        return WeeklyIntelligenceBriefSummary(
            week_label="2026-W28",
            generated_at="2026-07-13T07:02:52Z",
            html_path="/v1/brief.html",
            json_path="/v1/brief.json",
            thread_count=1,
            source_atom_count=1,
            changed_thread_count=1,
            action_count=1,
            mvp_status="unavailable",
            quality_finding_count=0,
            notification_text="",
        )

    def _atlas(self) -> KnowledgeAtlasSummary:
        return KnowledgeAtlasSummary(
            week_label="2026-W28",
            generated_at="2026-07-13T07:02:52Z",
            html_path="/v1/atlas.html",
            json_path="/v1/atlas.json",
            thread_count=1,
            source_atom_count=1,
            source_channel_count=1,
            trend_count=1,
            quality_finding_count=0,
            notification_text="",
        )

    def _matching_project_package(self, run_id: str) -> dict[str, object]:
        fixture = json.loads(PROJECT_FIXTURE_PATH.read_text(encoding="utf-8"))
        package = fixture["input_package"]
        package["run_id"] = run_id
        package["signal_candidates"][0]["canonical_thread_refs"] = [
            "canonical_thread:project-intelligence"
        ]
        return package

    def _generate(self, events: list[str], **kwargs: object):
        brief_calls = 0

        def load_context(*_args: object, **call_kwargs: object) -> dict[str, object]:
            if call_kwargs.get("feedback_snapshot_at") is None:
                events.append("context:initial")
            else:
                events.append("context:shadow-cutoff")
            return {
                "feedback_context": {"confirmed_event_count": 2},
                "threads": [],
            }

        def build_brief(*_args: object, **_kwargs: object):
            nonlocal brief_calls
            brief_calls += 1
            events.append(f"v1:brief:{brief_calls}")
            return self._brief()

        def build_atlas(*_args: object, **_kwargs: object):
            events.append("v1:atlas")
            return self._atlas()

        with (
            patch(
                "output.split_intelligence_reports.load_ai_intelligence_context",
                side_effect=load_context,
            ),
            patch(
                "output.split_intelligence_reports.load_mvp_radar_summary",
                return_value={},
            ),
            patch(
                "output.split_intelligence_reports.build_weekly_intelligence_brief_artifact",
                side_effect=build_brief,
            ),
            patch(
                "output.split_intelligence_reports.build_knowledge_atlas_artifact",
                side_effect=build_atlas,
            ),
        ):
            return generate_split_intelligence_reports(
                self._settings(),
                week_label="2026-W28",
                output_root=Path("/v1"),
                now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
                run_identity={"run_id": "run-irx9-shadow"},
                **kwargs,
            )

    def test_default_path_preserves_v1_only_behavior_and_empty_shadow_fields(self):
        events: list[str] = []

        summary = self._generate(events)

        self.assertEqual(
            events,
            ["context:initial", "v1:brief:1", "v1:atlas", "v1:brief:2"],
        )
        self.assertIsNone(summary.project_intelligence)
        self.assertEqual(summary.project_intelligence_error, "")
        self.assertIsNone(summary.editorial_intelligence)
        self.assertEqual(summary.editorial_intelligence_error, "")
        self.assertEqual(summary.weekly_brief.html_path, "/v1/brief.html")
        self.assertEqual(summary.knowledge_atlas.html_path, "/v1/atlas.html")

    def test_project_only_runs_after_v1_without_calling_editorial_or_llm(self):
        events: list[str] = []
        package = {"schema_version": "editorial_intelligence_input.v1"}
        project_summary = SimpleNamespace(path="/shadow/project-intelligence.v2.json")
        completion = MagicMock(name="completion")

        with (
            patch(
                "output.editorial_intelligence.build_editorial_input_package",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("shadow:preliminary") or package
                ),
            ) as build_preliminary,
            patch(
                "output.project_intelligence.generate_project_intelligence_artifact",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("shadow:project-generate") or project_summary
                ),
            ) as generate_project,
            patch(
                "output.project_intelligence.load_project_intelligence_artifact",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("shadow:project-load") or {"actions": []}
                ),
            ),
            patch(
                "output.project_intelligence.load_project_action_descriptors",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("shadow:project-descriptors") or []
                ),
            ),
            patch(
                "output.project_intelligence.project_editorial_permissions",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("shadow:permissions") or []
                ),
            ),
            patch(
                "output.editorial_intelligence.generate_editorial_intelligence_artifact"
            ) as generate_editorial,
        ):
            summary = self._generate(
                events,
                project_intelligence_output_root=Path("/shadow"),
                project_intelligence_diagnostics=[{"status": "watch"}],
                editorial_completion=completion,
            )

        self.assertEqual(
            events,
            [
                "context:initial",
                "v1:brief:1",
                "v1:atlas",
                "v1:brief:2",
                "context:shadow-cutoff",
                "shadow:preliminary",
                "shadow:project-generate",
                "shadow:project-load",
                "shadow:project-descriptors",
                "shadow:permissions",
            ],
        )
        build_preliminary.assert_called_once()
        self.assertEqual(build_preliminary.call_args.kwargs["project_permissions"], ())
        self.assertNotIn("projects_yaml_path", generate_project.call_args.kwargs)
        self.assertEqual(
            generate_project.call_args.kwargs["diagnostic_records"],
            ({"status": "watch"},),
        )
        generate_editorial.assert_not_called()
        completion.assert_not_called()
        self.assertIs(summary.project_intelligence, project_summary)
        self.assertEqual(summary.project_intelligence_error, "")

    def test_project_only_real_core_uses_default_descriptors_and_no_llm(self):
        events: list[str] = []
        package = self._matching_project_package("run-irx9-shadow")

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch(
                    "output.editorial_intelligence.build_editorial_input_package",
                    return_value=package,
                ) as build_preliminary,
                patch(
                    "output.editorial_intelligence.generate_editorial_intelligence_artifact"
                ) as generate_editorial,
                patch(
                    "output.editorial_intelligence.complete_with_receipt"
                ) as editorial_llm,
                patch("llm.client.complete_with_receipt") as client_llm,
            ):
                summary = self._generate(
                    events,
                    project_intelligence_output_root=Path(tmpdir),
                )

            project = summary.project_intelligence
            self.assertIsNotNone(project)
            assert project is not None
            self.assertTrue(Path(project.path).is_file())
            self.assertEqual(project.run_id, "run-irx9-shadow")
            self.assertEqual(project.reporting_week, "2026-W28")
            self.assertEqual(project.confirmed_action_count, 1)
            self.assertEqual(project.reader_state, "confirmed_actions")
            self.assertEqual(summary.project_intelligence_error, "")
            self.assertIsNone(summary.editorial_intelligence)
            build_preliminary.assert_called_once()
            self.assertEqual(
                build_preliminary.call_args.kwargs["project_permissions"], ()
            )
            generate_editorial.assert_not_called()
            editorial_llm.assert_not_called()
            client_llm.assert_not_called()

    def test_explicit_empty_diagnostics_disable_default_exact_authority(self):
        events: list[str] = []
        package = self._matching_project_package("run-irx9-explicit-empty")

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch(
                    "output.editorial_intelligence.build_editorial_input_package",
                    return_value=package,
                ),
                patch(
                    "output.editorial_intelligence.generate_editorial_intelligence_artifact"
                ) as generate_editorial,
                patch(
                    "output.editorial_intelligence.complete_with_receipt"
                ) as editorial_llm,
                patch("llm.client.complete_with_receipt") as client_llm,
            ):
                summary = self._generate(
                    events,
                    project_intelligence_output_root=Path(tmpdir),
                    project_intelligence_diagnostics=[],
                )

            project = summary.project_intelligence
            self.assertIsNotNone(project)
            assert project is not None
            self.assertTrue(Path(project.path).is_file())
            self.assertEqual(project.run_id, "run-irx9-explicit-empty")
            self.assertEqual(project.confirmed_action_count, 0)
            self.assertEqual(project.reader_state, "no_confirmed_implication")
            self.assertEqual(summary.project_intelligence_error, "")
            generate_editorial.assert_not_called()
            editorial_llm.assert_not_called()
            client_llm.assert_not_called()

    def test_validated_project_permissions_are_the_only_editorial_handoff(self):
        events: list[str] = []
        package = {"schema_version": "editorial_intelligence_input.v1"}
        artifact = {"schema_version": "project_intelligence.v2"}
        permissions = [
            {
                "project_action_ref": "project-action:tra:eval-gate",
                "signal_id": "signal:eval-gates",
                "project": "telegram-research-agent",
                "permission": "allowed",
                "evidence_refs": ["evidence:1"],
            }
        ]
        project_summary = SimpleNamespace(path="/shadow/project-intelligence.v2.json")
        editorial_summary = SimpleNamespace(
            path="/shadow/editorial-intelligence.v1.json"
        )
        descriptors = [{"project_name": "telegram-research-agent"}]

        with (
            patch(
                "output.editorial_intelligence.build_editorial_input_package",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("shadow:preliminary") or package
                ),
            ) as build_preliminary,
            patch(
                "output.project_intelligence.generate_project_intelligence_artifact",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("shadow:project-generate") or project_summary
                ),
            ) as generate_project,
            patch(
                "output.project_intelligence.load_project_intelligence_artifact",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("shadow:project-load") or artifact
                ),
            ) as load_project,
            patch(
                "output.project_intelligence.load_project_action_descriptors",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("shadow:project-descriptors") or descriptors
                ),
            ) as load_descriptors,
            patch(
                "output.project_intelligence.project_editorial_permissions",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("shadow:permissions") or permissions
                ),
            ) as extract_permissions,
            patch(
                "output.editorial_intelligence.generate_editorial_intelligence_artifact",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("shadow:editorial") or editorial_summary
                ),
            ) as generate_editorial,
        ):
            summary = self._generate(
                events,
                project_intelligence_output_root=Path("/shadow/project"),
                project_intelligence_projects_path=Path("/config/projects.yaml"),
                editorial_output_root=Path("/shadow/editorial"),
            )

        self.assertLess(events.index("v1:brief:2"), events.index("shadow:preliminary"))
        self.assertLess(
            events.index("shadow:permissions"), events.index("shadow:editorial")
        )
        self.assertEqual(events.count("context:shadow-cutoff"), 1)
        self.assertIs(
            build_preliminary.call_args.args[0],
            generate_editorial.call_args.args[0],
        )
        self.assertEqual(
            generate_project.call_args.kwargs["projects_yaml_path"],
            Path("/config/projects.yaml"),
        )
        self.assertNotIn("diagnostic_records", generate_project.call_args.kwargs)
        load_project.assert_called_once_with(project_summary.path)
        load_descriptors.assert_called_once_with(Path("/config/projects.yaml"))
        extract_permissions.assert_called_once_with(
            artifact,
            input_package=package,
            projects=descriptors,
        )
        self.assertIs(
            generate_editorial.call_args.kwargs["project_permissions"], permissions
        )
        self.assertNotIn("project_intelligence", generate_editorial.call_args.kwargs)
        self.assertIs(summary.project_intelligence, project_summary)
        self.assertIs(summary.editorial_intelligence, editorial_summary)

        with (
            patch("bot.telegram_delivery.send_text", return_value=10),
            patch("bot.telegram_delivery.send_document", side_effect=[11, 12]),
        ):
            delivered = deliver_split_intelligence_reports(
                summary,
                chat_id="12345",
                token="token",
            )
        self.assertIs(delivered.project_intelligence, project_summary)
        self.assertEqual(delivered.project_intelligence_error, "")
        self.assertIs(delivered.editorial_intelligence, editorial_summary)
        self.assertEqual(delivered.editorial_intelligence_error, "")
        self.assertEqual(delivered.delivered_message_ids, (10, 11, 12))

    def test_project_failure_falls_back_to_zero_editorial_permissions(self):
        events: list[str] = []
        editorial_summary = SimpleNamespace(
            path="/shadow/editorial-intelligence.v1.json"
        )

        with (
            patch(
                "output.editorial_intelligence.build_editorial_input_package",
                return_value={"schema_version": "editorial_intelligence_input.v1"},
            ),
            patch(
                "output.project_intelligence.generate_project_intelligence_artifact",
                side_effect=RuntimeError("project shadow failed"),
            ),
            patch(
                "output.project_intelligence.load_project_intelligence_artifact"
            ) as load_project,
            patch(
                "output.project_intelligence.load_project_action_descriptors"
            ) as load_descriptors,
            patch(
                "output.project_intelligence.project_editorial_permissions"
            ) as extract_permissions,
            patch(
                "output.editorial_intelligence.generate_editorial_intelligence_artifact",
                return_value=editorial_summary,
            ) as generate_editorial,
        ):
            summary = self._generate(
                events,
                project_intelligence_output_root=Path("/shadow/project"),
                editorial_output_root=Path("/shadow/editorial"),
            )

        load_project.assert_not_called()
        load_descriptors.assert_not_called()
        extract_permissions.assert_not_called()
        self.assertEqual(generate_editorial.call_args.kwargs["project_permissions"], ())
        self.assertIsNone(summary.project_intelligence)
        self.assertEqual(summary.project_intelligence_error, "RuntimeError")
        self.assertIs(summary.editorial_intelligence, editorial_summary)
        self.assertEqual(summary.editorial_intelligence_error, "")

    def test_editorial_failure_does_not_invalidate_project_artifact(self):
        events: list[str] = []
        project_summary = SimpleNamespace(path="/shadow/project-intelligence.v2.json")
        permissions = [
            {
                "project_action_ref": "project-action:tra:eval-gate",
                "signal_id": "signal:eval-gates",
                "project": "telegram-research-agent",
                "permission": "allowed",
                "evidence_refs": ["evidence:1"],
            }
        ]

        with (
            patch(
                "output.editorial_intelligence.build_editorial_input_package",
                return_value={"schema_version": "editorial_intelligence_input.v1"},
            ),
            patch(
                "output.project_intelligence.generate_project_intelligence_artifact",
                return_value=project_summary,
            ),
            patch(
                "output.project_intelligence.load_project_intelligence_artifact",
                return_value={"schema_version": "project_intelligence.v2"},
            ),
            patch(
                "output.project_intelligence.load_project_action_descriptors",
                return_value=[{"project_name": "telegram-research-agent"}],
            ),
            patch(
                "output.project_intelligence.project_editorial_permissions",
                return_value=permissions,
            ),
            patch(
                "output.editorial_intelligence.generate_editorial_intelligence_artifact",
                side_effect=ValueError("editorial shadow failed"),
            ),
        ):
            summary = self._generate(
                events,
                project_intelligence_output_root=Path("/shadow/project"),
                editorial_output_root=Path("/shadow/editorial"),
            )

        self.assertIs(summary.project_intelligence, project_summary)
        self.assertEqual(summary.project_intelligence_error, "")
        self.assertIsNone(summary.editorial_intelligence)
        self.assertEqual(summary.editorial_intelligence_error, "ValueError")
        self.assertEqual(summary.weekly_brief.html_path, "/v1/brief.html")
        self.assertEqual(summary.knowledge_atlas.html_path, "/v1/atlas.html")


if __name__ == "__main__":
    unittest.main()
