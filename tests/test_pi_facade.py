import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from assistant.pi_facade import PersonalIntelligenceFacade
from config.settings import Settings


class TestPersonalIntelligenceFacade(unittest.TestCase):
    def _settings(self, root: Path) -> Settings:
        return Settings(
            db_path=str(root / "agent.db"),
            llm_api_key="",
            model_provider="",
            telegram_session_path="",
        )

    def _write_workbook(self, root: Path, *, marked_posts: list[dict] | None = None) -> None:
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
                        {"id": "decision-brief", "title": "Операторский вердикт", "title_en": "Decision Brief", "kind": "decision_brief"},
                        {"id": "strong-signals", "title": "Сильные сигналы", "title_en": "Strong Signals", "kind": "strong_signals"},
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
                    "action_cards": [
                        {
                            "id": "action-1",
                            "title": "Try a tiny eval gate",
                            "next_step": "Add one regression guard.",
                            "success_criterion": "Bad agent edit fails before merge.",
                            "effort": "30 min",
                            "scope": "verification",
                        }
                    ],
                    "project_diagnostic": {
                        "implementation_suggestions": [
                            {
                                "project": "telegram-research-agent",
                                "title": "Add eval gate backlog item",
                                "next_step": "Draft one scoped issue.",
                                "effort": "30 min",
                                "risk_caveat": "Do not overbuild.",
                                "acceptance_criteria": ["Issue has owner and test command."],
                                "source_atom_ids": [101],
                                "source_urls": ["https://t.me/ai_lab/101"],
                            }
                        ]
                    },
                    "mvp_radar": {
                        "status": "loaded",
                        "selected_candidate": "LLM Guardrail Watchdog",
                        "dossier_status": "investigate",
                        "recommendation": "revisit_with_evidence_gap",
                        "source_mix": {"readiness": "telegram_only"},
                        "missing_evidence": ["Need external demand."],
                        "next_validation": ["Interview operators."],
                    },
                    "feedback_targets": [],
                    "marked_posts": marked_posts or [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_facade_instantiates_without_external_api_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facade = PersonalIntelligenceFacade(
                settings=self._settings(root),
                output_root=root,
                now=datetime(2026, 7, 8, tzinfo=timezone.utc),
            )
            current = facade.get_current_week_label()

        self.assertEqual(current["status"], "ok")
        self.assertEqual(current["week_label"], "2026-W28")
        self.assertEqual(current["source"], "date")

    def test_missing_workbook_returns_missing_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            result = facade.get_workbook_summary("2026-W28")

        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["week_label"], "2026-W28")
        self.assertEqual(result["artifact_paths"], {"html": None, "json": None})

    def test_missing_mvp_radar_returns_missing_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            result = facade.get_mvp_radar_status("2026-W28")

        self.assertEqual(result["status"], "missing")
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["missing_evidence"], [])

    def test_missing_feedback_table_returns_missing_or_empty_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Path(root / "agent.db").touch()
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            result = facade.get_feedback_summary("2026-W28")

        self.assertIn(result["status"], {"missing", "empty"})
        self.assertEqual(result["counts"], {})

    def test_no_mutation_methods_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)

        for method_name in [
            "edit_code",
            "run_codex",
            "edit_config",
            "mutate_profile",
            "mutate_projects",
        ]:
            self.assertFalse(hasattr(facade, method_name), method_name)

    def test_list_marked_posts_does_not_treat_no_reaction_as_negative(self):
        marked_posts = [
            {
                "post_id": 101,
                "channel_username": "ai_lab",
                "content": "Interesting source that has no visible reaction value in the sidecar.",
                "source_url": "https://t.me/ai_lab/101",
                "reaction": None,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root, marked_posts=marked_posts)
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            result = facade.list_marked_posts("2026-W28")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["items"][0]["reaction"], None)
        self.assertEqual(result["items"][0]["marked_reason_guess"], None)
        self.assertNotEqual(result["items"][0]["marked_reason_guess"], "negative")

    def test_get_workbook_summary_returns_stable_keys(self):
        expected_keys = {
            "status",
            "week_label",
            "title",
            "generated_at",
            "decision_brief",
            "strong_signals",
            "actions",
            "project_actions",
            "mvp_status",
            "artifact_paths",
            "message",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            result = facade.get_workbook_summary("2026-W28")

        self.assertEqual(set(result.keys()), expected_keys)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["strong_signals"])

    def test_get_action_statuses_keeps_missing_feedback_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            Path(root / "agent.db").touch()
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            result = facade.get_action_statuses("2026-W28")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["items"][0]["status"], "unknown")
        self.assertEqual(result["counts"]["unknown"], 1)
        self.assertEqual(result["counts"]["not_interested"], 0)

    def test_search_intelligence_items_reports_curated_fts_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            facade = PersonalIntelligenceFacade(settings=self._settings(root), output_root=root)
            result = facade.search_intelligence_items("радар рынка", limit=5)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["retrieval_decision"]["mode"], "curated_deterministic_plus_sqlite_fts")
        self.assertEqual(result["retrieval_decision"]["raw_telegram_status"], "disabled")
        self.assertTrue(any(item["item_type"] == "mvp_dossier" for item in result["items"]))


if __name__ == "__main__":
    unittest.main()
