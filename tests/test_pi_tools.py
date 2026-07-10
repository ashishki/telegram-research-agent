import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from assistant.pi_facade import PersonalIntelligenceFacade
from assistant.pi_prompts import PI_TOOL_LOOP_MAX_CALLS
from assistant.pi_tools import (
    FORBIDDEN_TOOL_NAMES,
    build_pi_tool_catalog,
    call_pi_tool,
    list_pi_tools,
    validate_pi_tool_catalog,
)
from config.settings import Settings


class TestPITools(unittest.TestCase):
    def _settings(self, root: Path) -> Settings:
        return Settings(
            db_path=str(root / "missing.db"),
            llm_api_key="",
            model_provider="",
            telegram_session_path="",
        )

    def _write_workbook(self, root: Path) -> None:
        output_dir = root / "ai_visual_intelligence"
        output_dir.mkdir(parents=True)
        html_path = output_dir / "2026-W28.visual.html"
        json_path = output_dir / "2026-W28.visual.json"
        html_path.write_text("<!doctype html><title>workbook</title>", encoding="utf-8")
        json_path.write_text(
            json.dumps(
                {
                    "week_label": "2026-W28",
                    "generated_at": "2026-07-08T00:00:00Z",
                    "html_path": str(html_path),
                    "workbook_sections": [
                        {
                            "id": "decision-brief",
                            "title": "Операторский вердикт",
                            "title_en": "Decision Brief",
                            "kind": "decision_brief",
                        },
                        {
                            "id": "strong-signals",
                            "title": "Сильные сигналы",
                            "title_en": "Strong Signals",
                            "kind": "strong_signals",
                        },
                    ],
                    "decision_cards": [
                        {
                            "id": "decision-1",
                            "verdict": "study",
                            "title": "Study eval gates",
                            "why_for_operator": "Eval gates matter this week.",
                            "next_action": "Read one source.",
                            "confidence": "medium",
                            "evidence_atom_ids": [101],
                        }
                    ],
                    "claim_cards": [
                        {
                            "id": "claim-1",
                            "claim": "Eval gates are becoming release infrastructure for coding agents.",
                            "caveat": "Evidence is still source-limited.",
                            "source_urls": ["https://t.me/ai_lab/101"],
                            "evidence_atom_ids": [101],
                            "evidence_tier": "primary_source",
                            "verification_status": "verified",
                            "confidence": 0.8,
                        }
                    ],
                    "project_diagnostic": {
                        "implementation_suggestions": [
                            {
                                "id": "project-action-1",
                                "project": "telegram-research-agent",
                                "title": "Add eval gate backlog item",
                                "next_step": "Draft one scoped issue.",
                                "source_atom_ids": [101],
                                "source_urls": ["https://t.me/ai_lab/101"],
                            }
                        ]
                    },
                    "feedback_targets": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_split_artifacts(self, root: Path) -> None:
        brief_dir = root / "weekly_intelligence_briefs"
        atlas_dir = root / "knowledge_atlas"
        brief_dir.mkdir(parents=True)
        atlas_dir.mkdir(parents=True)
        (brief_dir / "2026-W28.weekly-brief.html").write_text("<!doctype html><title>Brief</title>", encoding="utf-8")
        (atlas_dir / "2026-W28.knowledge-atlas.html").write_text("<!doctype html><title>Atlas</title>", encoding="utf-8")
        (brief_dir / "2026-W28.weekly-brief.json").write_text(
            json.dumps({"week_label": "2026-W28", "generated_at": "2026-07-08T00:00:00Z"}),
            encoding="utf-8",
        )
        (atlas_dir / "2026-W28.knowledge-atlas.json").write_text(
            json.dumps({"week_label": "2026-W28", "generated_at": "2026-07-08T00:00:00Z"}),
            encoding="utf-8",
        )

    def _facade(self, root: Path) -> PersonalIntelligenceFacade:
        return PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)

    def test_catalog_is_read_only_and_bounded(self):
        catalog = build_pi_tool_catalog()
        validation = validate_pi_tool_catalog(catalog)

        self.assertEqual(validation["status"], "ok")
        self.assertLessEqual(validation["max_calls_per_turn"], 4)
        self.assertEqual(PI_TOOL_LOOP_MAX_CALLS, validation["max_calls_per_turn"])
        self.assertFalse(FORBIDDEN_TOOL_NAMES.intersection(catalog))
        self.assertTrue(all(tool.read_only for tool in catalog.values()))

    def test_public_tool_descriptors_are_serializable_without_handlers(self):
        descriptors = list_pi_tools()

        self.assertTrue(descriptors)
        self.assertIn("get_weekly_summary", {item["name"] for item in descriptors})
        self.assertIn("get_artifact_status", {item["name"] for item in descriptors})
        self.assertTrue(all("handler" not in item for item in descriptors))
        self.assertTrue(all(item["read_only"] is True for item in descriptors))

    def test_weekly_summary_tool_returns_evidence_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            result = call_pi_tool(
                "get_weekly_summary",
                {"week_label": "2026-W28"},
                facade=self._facade(root),
            )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["read_only"])
        self.assertEqual(result["tool_name"], "get_weekly_summary")
        self.assertEqual(result["evidence_status"], "available")
        self.assertIn("artifact_paths", result["evidence"])
        self.assertEqual(result["result"]["week_label"], "2026-W28")

    def test_artifact_status_tool_reports_split_artifacts_and_missing_radar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_split_artifacts(root)
            facade = PersonalIntelligenceFacade(
                settings=self._settings(root),
                output_root=root,
                now=datetime(2026, 7, 8, tzinfo=timezone.utc),
            )
            result = call_pi_tool(
                "get_artifact_status",
                {"week_label": "2026-W28"},
                facade=facade,
            )

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["evidence_status"], "available")
        self.assertEqual(result["result"]["weekly_brief"]["status"], "current")
        self.assertEqual(result["result"]["knowledge_atlas"]["status"], "current")
        self.assertEqual(result["result"]["mvp_radar"]["status"], "missing")
        self.assertEqual(result["result"]["mvp_radar_gate"]["decision"], "do_not_build")
        self.assertIn("weekly_intelligence_brief_json", result["evidence"]["artifact_paths"])

    def test_missing_data_returns_insufficient_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = call_pi_tool(
                "get_mvp_radar_status",
                {"week_label": "2026-W28"},
                facade=self._facade(root),
            )

        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["evidence_status"], "insufficient")
        self.assertEqual(result["result"]["missing_evidence"], [])

    def test_search_tool_uses_curated_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            result = call_pi_tool(
                "search_intelligence_items",
                {"query": "eval gates", "filters": {"item_type": "claim_card"}, "limit": 3},
                facade=self._facade(root),
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["evidence_status"], "available")
        self.assertTrue(result["result"]["items"])
        self.assertEqual(result["result"]["items"][0]["item_type"], "claim_card")
        self.assertNotIn("raw_telegram_post", {item["item_type"] for item in result["result"]["items"]})

    def test_strategy_reviewer_tool_is_curated_and_graceful_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = call_pi_tool(
                "get_strategy_reviewer_notes",
                {"week_label": "2026-W28"},
                facade=self._facade(root),
            )

        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["evidence_status"], "insufficient")
        self.assertEqual(result["result"]["suggestions"]["keep"], [])
        self.assertEqual(result["result"]["codex_tasks"], [])
        self.assertEqual(result["result"]["mutation_policy"]["source_code"], "do_not_modify")

    def test_unknown_and_invalid_tool_calls_return_dto_errors(self):
        unknown = call_pi_tool("edit_code", {"path": "x"})
        invalid = call_pi_tool("search_intelligence_items", {"limit": 5})

        self.assertEqual(unknown["status"], "missing")
        self.assertEqual(unknown["evidence_status"], "insufficient")
        self.assertEqual(invalid["status"], "invalid")
        self.assertEqual(invalid["evidence_status"], "insufficient")


if __name__ == "__main__":
    unittest.main()
