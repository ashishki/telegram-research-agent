import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from assistant.pi_facade import PersonalIntelligenceFacade
from assistant.pi_prompts import PI_TOOL_LOOP_MAX_CALLS
from assistant.pi_tools import (
    CONFIRMATION_GATED_PROPOSAL_TOOLS,
    FORBIDDEN_TOOL_NAMES,
    MINIMUM_READ_ONLY_TOOLS,
    PITool,
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

    def _facade_with_db(self, root: Path, db_path: Path) -> PersonalIntelligenceFacade:
        return PersonalIntelligenceFacade(
            settings=Settings(
                db_path=str(db_path),
                llm_api_key="",
                model_provider="",
                telegram_session_path="",
            ),
            output_root=root,
        )

    def _write_archive_db(self, db_path: Path, *, matching: bool = True) -> None:
        connection = sqlite3.connect(db_path)
        try:
            content = (
                "Agent review automation works over retained Telegram archive posts."
                if matching
                else "Unrelated retained post about weekly planning."
            )
            connection.executescript(
                """
                CREATE TABLE raw_posts (
                    id INTEGER PRIMARY KEY,
                    channel_username TEXT NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    posted_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL DEFAULT '',
                    ingested_at TEXT NOT NULL DEFAULT '2026-07-20T10:00:00Z',
                    message_url TEXT,
                    forward_from TEXT
                );
                CREATE TABLE posts (
                    id INTEGER PRIMARY KEY,
                    raw_post_id INTEGER NOT NULL UNIQUE,
                    channel_username TEXT NOT NULL,
                    posted_at TEXT NOT NULL,
                    content TEXT NOT NULL,
                    url_count INTEGER NOT NULL DEFAULT 0,
                    has_code INTEGER NOT NULL DEFAULT 0,
                    language_detected TEXT,
                    word_count INTEGER NOT NULL DEFAULT 0,
                    normalized_at TEXT NOT NULL DEFAULT '2026-07-20T10:00:00Z'
                );
                CREATE VIRTUAL TABLE posts_fts USING fts5(
                    content,
                    content='posts',
                    content_rowid='id'
                );
                """
            )
            connection.execute(
                """
                INSERT INTO raw_posts (
                    id, channel_username, channel_id, message_id, posted_at, message_url
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (100, "@source", -1001, 1001, "2026-07-20T10:00:00Z", "https://t.me/source/1001"),
            )
            connection.execute(
                """
                INSERT INTO posts (
                    id, raw_post_id, channel_username, posted_at, content,
                    language_detected, word_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (1, 100, "@source", "2026-07-20T10:00:00Z", content, "ru", len(content.split())),
            )
            connection.execute("INSERT INTO posts_fts(rowid, content) VALUES (?, ?)", (1, content))
            connection.commit()
        finally:
            connection.close()

    def test_catalog_is_read_only_and_bounded(self):
        catalog = build_pi_tool_catalog()
        validation = validate_pi_tool_catalog(catalog)

        self.assertEqual(validation["status"], "ok")
        self.assertLessEqual(validation["max_calls_per_turn"], 4)
        self.assertEqual(PI_TOOL_LOOP_MAX_CALLS, validation["max_calls_per_turn"])
        self.assertFalse(FORBIDDEN_TOOL_NAMES.intersection(catalog))
        self.assertTrue(all(tool.read_only for tool in catalog.values()))
        self.assertTrue(MINIMUM_READ_ONLY_TOOLS.issubset(catalog))
        self.assertTrue(CONFIRMATION_GATED_PROPOSAL_TOOLS.issubset(catalog))
        self.assertTrue(
            all(catalog[name].requires_confirmation for name in CONFIRMATION_GATED_PROPOSAL_TOOLS)
        )
        self.assertTrue(all(catalog[name].proposal_only for name in CONFIRMATION_GATED_PROPOSAL_TOOLS))

    def test_public_tool_descriptors_are_serializable_without_handlers(self):
        descriptors = list_pi_tools()

        self.assertTrue(descriptors)
        self.assertIn("get_weekly_summary", {item["name"] for item in descriptors})
        self.assertIn("get_artifact_status", {item["name"] for item in descriptors})
        self.assertIn("search_telegram_archive", {item["name"] for item in descriptors})
        self.assertIn("request_external_verification", {item["name"] for item in descriptors})
        self.assertIn("propose_action", {item["name"] for item in descriptors})
        self.assertTrue(all("handler" not in item for item in descriptors))
        self.assertTrue(all(item["read_only"] is True for item in descriptors))

    def test_proposal_tool_is_confirmation_gated_and_does_not_persist(self):
        result = call_pi_tool(
            "propose_action",
            {"title": "Review retrieval eval", "rationale": "Needs human approval."},
            facade=object(),
        )

        self.assertEqual(result["status"], "needs_confirmation")
        self.assertTrue(result["read_only"])
        self.assertEqual(result["result"]["proposal_type"], "action")
        self.assertFalse(result["result"]["persisted"])
        self.assertIn("confirmation", result["message"])

    def test_external_verification_request_does_not_run_skill_or_persist(self):
        result = call_pi_tool(
            "request_external_verification",
            {
                "question": "What visa rule applies now?",
                "category": "visa",
                "reason": "Visa questions require current external evidence.",
            },
            facade=object(),
        )

        self.assertEqual(result["status"], "needs_external_verification")
        self.assertEqual(result["evidence_status"], "insufficient")
        self.assertEqual(result["result"]["category"], "visa")
        self.assertEqual(result["result"]["external_evidence"]["status"], "not_run_unapproved")
        self.assertFalse(result["result"]["external_evidence"]["external_skill_used"])
        self.assertFalse(result["result"]["persistence"]["stored_research_note"])
        self.assertTrue(result["result"]["persistence"]["requires_human_confirmation"])

    def test_unapproved_external_skill_tool_is_rejected_by_allowlist(self):
        catalog = build_pi_tool_catalog()
        catalog["web_search"] = PITool(
            name="web_search",
            description="Unapproved external web search.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=lambda _facade, _args: {"status": "ok"},
        )

        with self.assertRaisesRegex(ValueError, "Unapproved external-skill tools.*web_search"):
            validate_pi_tool_catalog(catalog)

    def test_archive_search_tool_schema_is_read_only_and_closed(self):
        catalog = build_pi_tool_catalog()
        tool = catalog["search_telegram_archive"]

        self.assertTrue(tool.read_only)
        self.assertEqual(tool.input_schema["additionalProperties"], False)
        self.assertEqual(tool.input_schema["properties"]["filters"]["additionalProperties"], False)
        serialized = json.dumps(tool.input_schema)
        for forbidden in ("write", "confirm", "mutate", "execute_sql", "db_path"):
            self.assertNotIn(forbidden, serialized)

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

    def test_archive_search_tool_returns_source_link_without_atoms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "archive.db"
            self._write_archive_db(db_path)
            result = call_pi_tool(
                "search_telegram_archive",
                {"query": "agent review", "limit": 3},
                facade=self._facade_with_db(root, db_path),
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["evidence_status"], "available")
        self.assertEqual(result["tool_name"], "search_telegram_archive")
        self.assertIn("https://t.me/source/1001", result["evidence"]["source_refs"])
        self.assertEqual(result["result"]["items"][0]["archive_document_id"], "tg:-1001:1001")
        self.assertEqual(result["result"]["items"][0]["source_url"], "https://t.me/source/1001")
        self.assertEqual(result["evidence"]["atom_ids"], [])

    def test_archive_search_tool_no_answer_has_insufficient_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "archive.db"
            self._write_archive_db(db_path, matching=False)
            result = call_pi_tool(
                "search_telegram_archive",
                {"query": "nonexistentterm", "limit": 3},
                facade=self._facade_with_db(root, db_path),
            )

        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["evidence_status"], "insufficient")
        self.assertEqual(result["result"]["items"], [])
        self.assertEqual(result["evidence"]["source_refs"], [])

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
