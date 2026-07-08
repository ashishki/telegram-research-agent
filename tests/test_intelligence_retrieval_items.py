import json
import tempfile
import unittest
from pathlib import Path

from config.settings import Settings
from output.intelligence_retrieval_items import (
    build_retrieval_items,
    search_retrieval_items,
)


class TestIntelligenceRetrievalItems(unittest.TestCase):
    def _settings(self, root: Path) -> Settings:
        return Settings(
            db_path=str(root / "missing.db"),
            llm_api_key="",
            model_provider="",
            telegram_session_path="",
        )

    def _write_workbook(self, root: Path) -> Path:
        output_dir = root / "ai_visual_intelligence"
        output_dir.mkdir(parents=True)
        json_path = output_dir / "2026-W28.visual.json"
        html_path = output_dir / "2026-W28.visual.html"
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
                        {"id": "project-implementation", "title": "Проектная реализация", "title_en": "Project Implementation", "kind": "project_implementation"},
                    ],
                    "decision_cards": [
                        {
                            "id": "decision-1",
                            "verdict": "study",
                            "title": "Study eval-gated agent releases",
                            "why_for_operator": "Eval gates are relevant this week.",
                            "next_action": "Read the cited source.",
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
                            "quote_verified": True,
                            "confidence": 0.8,
                            "staleness_status": "active",
                        }
                    ],
                    "action_cards": [
                        {
                            "id": "action-1",
                            "title": "Try a tiny eval gate",
                            "next_step": "Add one regression guard.",
                            "success_criterion": "Bad agent edit fails before merge.",
                        }
                    ],
                    "project_diagnostic": {
                        "implementation_suggestions": [
                            {
                                "id": "project-action-1",
                                "project": "telegram-research-agent",
                                "title": "Add eval gate backlog item",
                                "next_step": "Draft one scoped issue.",
                                "effort": "30 min",
                                "risk_caveat": "Do not overbuild.",
                                "acceptance_criteria": ["Issue has owner and test command."],
                                "source_atom_ids": [101],
                                "source_urls": ["https://t.me/ai_lab/101"],
                                "suggestion_type": "backlog",
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
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return json_path

    def test_builds_retrieval_items_from_minimal_workbook_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)

        item_types = {item.item_type for item in items}
        self.assertIn("workbook_section", item_types)
        self.assertIn("claim_card", item_types)
        self.assertIn("action_card", item_types)
        self.assertIn("project_diagnostic", item_types)
        self.assertIn("mvp_dossier", item_types)

    def test_search_returns_matching_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)
            results = search_retrieval_items(items, "eval gates", limit=5)

        self.assertTrue(results)
        self.assertIn("eval", results[0]["title"].lower())
        self.assertIn("source_refs", results[0])
        self.assertIn("atom_ids", results[0])

    def test_filters_apply_before_broad_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)
            results = search_retrieval_items(
                items,
                "eval gates",
                filters={"item_type": "project_diagnostic", "project_name": "other-project"},
                limit=10,
            )

        self.assertEqual(results, [])

    def test_empty_missing_sources_return_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)

        self.assertEqual(items, [])

    def test_no_raw_telegram_post_source_is_required_for_p0(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)

        self.assertTrue(items)
        self.assertFalse({"raw_post", "telegram_post", "raw_telegram_post"}.intersection({item.item_type for item in items}))

    def test_returned_items_include_source_refs_and_atom_ids_even_when_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)
            results = search_retrieval_items(items, "tiny eval gate", filters={"item_type": "action_card"}, limit=1)

        self.assertTrue(results)
        self.assertIn("source_refs", results[0])
        self.assertIn("atom_ids", results[0])
        self.assertEqual(results[0]["source_refs"], [])
        self.assertEqual(results[0]["atom_ids"], [])


if __name__ == "__main__":
    unittest.main()
