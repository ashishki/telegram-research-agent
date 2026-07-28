import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from assistant.pi_facade import PersonalIntelligenceFacade
from assistant.pi_prompts import PI_TOOL_LOOP_MAX_CALLS
from assistant.pi_tools import (
    CONFIRMATION_GATED_PROPOSAL_TOOLS,
    CONFIRMATION_GATED_WRITE_TOOLS,
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

    def _write_project_descriptors(self, root: Path) -> Path:
        path = root / "projects.yaml"
        path.write_text(
            json.dumps(
                {
                    "projects": [
                        {
                            "name": "Eval-Ground-Truth-Lab",
                            "repo": "ashishki/Eval-Ground-Truth-Lab",
                            "description": "Evaluation lab for coding-agent ground truth and evidence-backed acceptance.",
                            "focus": "gold labels, holdout sets, citation correctness, replayable fixtures",
                            "keywords": [
                                "ground truth",
                                "gold labels",
                                "holdout sets",
                                "citation correctness",
                                "replayable fixtures",
                                "eval",
                            ],
                            "exclude_keywords": ["production mvp"],
                        }
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

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

    def _facade_with_db_and_projects(
        self,
        root: Path,
        db_path: Path,
        projects_path: Path,
    ) -> PersonalIntelligenceFacade:
        return PersonalIntelligenceFacade(
            settings=Settings(
                db_path=str(db_path),
                llm_api_key="",
                model_provider="",
                telegram_session_path="",
            ),
            output_root=root,
            project_descriptors_path=projects_path,
        )

    def _memory_events(self, db_path: Path) -> list[dict]:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.execute(
                """
                SELECT *
                FROM personal_memory_events
                ORDER BY id
                """
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            connection.close()

    def _migrate_db(self, db_path: Path) -> None:
        from db.migrate import run_migrations

        previous = os.environ.get("AGENT_DB_PATH")
        os.environ["AGENT_DB_PATH"] = str(db_path)
        try:
            run_migrations()
        finally:
            if previous is None:
                os.environ.pop("AGENT_DB_PATH", None)
            else:
                os.environ["AGENT_DB_PATH"] = previous

    def _write_archive_db(self, db_path: Path, *, matching: bool = True, content: str | None = None) -> None:
        connection = sqlite3.connect(db_path)
        try:
            content = content or (
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
        self.assertFalse(catalog["confirm_save_proposal"].read_only)
        self.assertTrue(
            all(tool.read_only for name, tool in catalog.items() if name not in CONFIRMATION_GATED_WRITE_TOOLS)
        )
        self.assertTrue(MINIMUM_READ_ONLY_TOOLS.issubset(catalog))
        self.assertTrue(CONFIRMATION_GATED_PROPOSAL_TOOLS.issubset(catalog))
        self.assertTrue(CONFIRMATION_GATED_WRITE_TOOLS.issubset(catalog))
        self.assertTrue(
            all(catalog[name].requires_confirmation for name in CONFIRMATION_GATED_PROPOSAL_TOOLS)
        )
        self.assertTrue(all(catalog[name].proposal_only for name in CONFIRMATION_GATED_PROPOSAL_TOOLS))
        self.assertTrue(catalog["confirm_save_proposal"].requires_confirmation)
        self.assertFalse(catalog["confirm_save_proposal"].proposal_only)
        self.assertEqual(validation["confirmation_gated_write_tool_count"], 1)

    def test_public_tool_descriptors_are_serializable_without_handlers(self):
        descriptors = list_pi_tools()

        self.assertTrue(descriptors)
        self.assertIn("get_weekly_summary", {item["name"] for item in descriptors})
        self.assertIn("get_artifact_status", {item["name"] for item in descriptors})
        self.assertIn("search_telegram_archive", {item["name"] for item in descriptors})
        self.assertIn("analyze_project_context", {item["name"] for item in descriptors})
        self.assertIn("request_external_verification", {item["name"] for item in descriptors})
        self.assertIn("propose_decision", {item["name"] for item in descriptors})
        self.assertIn("propose_action", {item["name"] for item in descriptors})
        self.assertIn("confirm_save_proposal", {item["name"] for item in descriptors})
        self.assertTrue(all("handler" not in item for item in descriptors))
        descriptor_by_name = {item["name"]: item for item in descriptors}
        self.assertFalse(descriptor_by_name["confirm_save_proposal"]["read_only"])
        self.assertTrue(
            all(item["read_only"] is True for item in descriptors if item["name"] != "confirm_save_proposal")
        )

    def test_proposal_tool_is_confirmation_gated_and_does_not_persist(self):
        result = call_pi_tool(
            "propose_action",
            {"title": "Review retrieval eval", "rationale": "Needs human approval."},
            facade=object(),
        )

        self.assertEqual(result["status"], "needs_confirmation")
        self.assertTrue(result["read_only"])
        self.assertEqual(result["result"]["proposal_type"], "action")
        self.assertEqual(result["result"]["proposal"]["object_type"], "action")
        self.assertEqual(result["result"]["proposal"]["operation"], "create")
        self.assertFalse(result["result"]["persisted"])
        self.assertFalse(result["result"]["write_performed"])
        self.assertTrue(result["result"]["confirmation"]["token"].startswith("confirm-"))
        self.assertIn("confirmation", result["message"])

    def test_proposal_tool_does_not_create_database_before_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "memory.db"
            result = call_pi_tool(
                "propose_knowledge_note",
                {
                    "title": "Eval gate note",
                    "body": "Remember to inspect eval gates before release.",
                    "source_refs": ["https://t.me/source/1001"],
                },
                facade=self._facade_with_db(Path(tmp), db_path),
            )

            self.assertEqual(result["status"], "needs_confirmation")
            self.assertFalse(result["result"]["persisted"])
            self.assertFalse(db_path.exists())

    def test_confirm_save_requires_explicit_facade_and_valid_token(self):
        proposal_result = call_pi_tool(
            "propose_watch_topic",
            {"title": "Watch eval agents", "rationale": "Track agent evaluation."},
            facade=object(),
        )
        proposal = proposal_result["result"]["proposal"]

        without_facade = call_pi_tool(
            "confirm_save_proposal",
            {"proposal": proposal, "confirmation_token": proposal_result["result"]["confirmation"]["token"]},
        )

        self.assertEqual(without_facade["status"], "invalid")
        self.assertFalse(without_facade["read_only"])
        self.assertIn("Explicit facade", without_facade["message"])

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "memory.db"
            invalid = call_pi_tool(
                "confirm_save_proposal",
                {"proposal": proposal, "confirmation_token": "confirm-wrong"},
                facade=self._facade_with_db(Path(tmp), db_path),
            )

            self.assertEqual(invalid["status"], "confirmation_required")
            self.assertFalse(invalid["result"]["persisted"])
            self.assertFalse(db_path.exists())

            schema_missing = call_pi_tool(
                "confirm_save_proposal",
                {"proposal": proposal, "confirmation_token": proposal_result["result"]["confirmation"]["token"]},
                facade=self._facade_with_db(Path(tmp), db_path),
            )

            self.assertEqual(schema_missing["status"], "schema_missing")
            self.assertFalse(schema_missing["result"]["write_performed"])
            self.assertFalse(db_path.exists())

    def test_confirm_save_proposal_persists_after_valid_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "memory.db"
            proposal_result = call_pi_tool(
                "propose_knowledge_note",
                {
                    "title": "Eval gate note",
                    "body": "Remember to inspect eval gates before release.",
                    "source_refs": ["https://t.me/source/1001"],
                    "metadata": {"topic": "eval"},
                },
                facade=self._facade_with_db(root, db_path),
            )
            self._migrate_db(db_path)
            confirmed = call_pi_tool(
                "confirm_save_proposal",
                {
                    "proposal": proposal_result["result"]["proposal"],
                    "confirmation_token": proposal_result["result"]["confirmation"]["token"],
                    "confirmed_at": "2026-07-27T10:00:00Z",
                },
                facade=self._facade_with_db(root, db_path),
            )

            self.assertEqual(confirmed["status"], "ok")
            self.assertFalse(confirmed["read_only"])
            self.assertTrue(confirmed["requires_confirmation"])
            self.assertTrue(confirmed["result"]["persisted"])
            self.assertTrue(confirmed["result"]["append_only"])
            events = self._memory_events(db_path)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "created")
            self.assertEqual(events[0]["object_type"], "knowledge_note")
            self.assertEqual(json.loads(events[0]["source_refs_json"]), ["https://t.me/source/1001"])

    def test_decision_and_experiment_history_is_append_only_with_rollback_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "memory.db"
            facade = self._facade_with_db(root, db_path)
            self._migrate_db(db_path)
            create_result = call_pi_tool(
                "propose_experiment",
                {"title": "Try retrieval eval", "body": "Run the focused tier before changing retrieval."},
                facade=facade,
            )
            create_confirmed = call_pi_tool(
                "confirm_save_proposal",
                {
                    "proposal": create_result["result"]["proposal"],
                    "confirmation_token": create_result["result"]["confirmation"]["token"],
                    "confirmed_at": "2026-07-27T10:00:00Z",
                },
                facade=facade,
            )
            memory_id = create_confirmed["result"]["memory_id"]
            edit_result = call_pi_tool(
                "propose_experiment",
                {
                    "operation": "edit",
                    "target_memory_id": memory_id,
                    "title": "Try retrieval eval",
                    "body": "Run focused and fast-contract tiers before retrieval changes.",
                },
                facade=facade,
            )
            edit_confirmed = call_pi_tool(
                "confirm_save_proposal",
                {
                    "proposal": edit_result["result"]["proposal"],
                    "confirmation_token": edit_result["result"]["confirmation"]["token"],
                    "confirmed_at": "2026-07-27T10:05:00Z",
                },
                facade=facade,
            )
            rollback_result = call_pi_tool(
                "propose_experiment",
                {
                    "operation": "rollback",
                    "target_memory_id": memory_id,
                    "target_event_id": edit_confirmed["result"]["event_id"],
                    "title": "Try retrieval eval",
                    "rationale": "Rollback the edited wording.",
                },
                facade=facade,
            )
            rollback_confirmed = call_pi_tool(
                "confirm_save_proposal",
                {
                    "proposal": rollback_result["result"]["proposal"],
                    "confirmation_token": rollback_result["result"]["confirmation"]["token"],
                    "confirmed_at": "2026-07-27T10:10:00Z",
                },
                facade=facade,
            )

            self.assertEqual(rollback_confirmed["status"], "ok")
            events = self._memory_events(db_path)
            self.assertEqual([event["event_type"] for event in events], ["created", "edited", "rolled_back"])
            self.assertEqual({event["memory_id"] for event in events}, {memory_id})
            self.assertEqual(events[2]["rollback_of_event_id"], edit_confirmed["result"]["event_id"])

            delete_result = call_pi_tool(
                "propose_experiment",
                {
                    "operation": "delete",
                    "target_memory_id": memory_id,
                    "title": "Try retrieval eval",
                    "rationale": "Delete without removing audit history.",
                },
                facade=facade,
            )
            delete_confirmed = call_pi_tool(
                "confirm_save_proposal",
                {
                    "proposal": delete_result["result"]["proposal"],
                    "confirmation_token": delete_result["result"]["confirmation"]["token"],
                    "confirmed_at": "2026-07-27T10:12:00Z",
                },
                facade=facade,
            )
            self.assertEqual(delete_confirmed["status"], "ok")
            events = self._memory_events(db_path)
            self.assertEqual([event["event_type"] for event in events], ["created", "edited", "rolled_back", "deleted"])

            decision_result = call_pi_tool(
                "propose_decision",
                {"title": "Defer vector retrieval", "rationale": "PRM-8 has no approved ADR."},
                facade=facade,
            )
            decision_confirmed = call_pi_tool(
                "confirm_save_proposal",
                {
                    "proposal": decision_result["result"]["proposal"],
                    "confirmation_token": decision_result["result"]["confirmation"]["token"],
                    "confirmed_at": "2026-07-27T10:15:00Z",
                },
                facade=facade,
            )
            events = self._memory_events(db_path)
            self.assertEqual(decision_confirmed["result"]["object_type"], "decision")
            self.assertEqual(events[-1]["object_type"], "decision")
            self.assertEqual(events[-1]["event_type"], "created")

    def test_confirm_save_replay_does_not_append_duplicate_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "memory.db"
            facade = self._facade_with_db(root, db_path)
            proposal_result = call_pi_tool(
                "propose_decision",
                {"title": "Keep external skills disabled", "rationale": "No trust record is approved."},
                facade=facade,
            )
            args = {
                "proposal": proposal_result["result"]["proposal"],
                "confirmation_token": proposal_result["result"]["confirmation"]["token"],
                "confirmed_at": "2026-07-27T10:00:00Z",
            }

            self._migrate_db(db_path)
            first = call_pi_tool("confirm_save_proposal", args, facade=facade)
            replay = call_pi_tool("confirm_save_proposal", args, facade=facade)

            self.assertEqual(first["status"], "ok")
            self.assertEqual(replay["status"], "already_confirmed")
            self.assertFalse(replay["result"]["write_performed"])
            events = self._memory_events(db_path)
            self.assertEqual(len(events), 1)
            self.assertEqual(replay["result"]["event_id"], first["result"]["event_id"])

    def test_confirm_save_rejects_missing_targets_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "memory.db"
            facade = self._facade_with_db(root, db_path)
            self._migrate_db(db_path)

            edit_result = call_pi_tool(
                "propose_decision",
                {
                    "operation": "edit",
                    "target_memory_id": "mem_missing",
                    "title": "Missing decision",
                    "body": "This target does not exist.",
                },
                facade=facade,
            )
            rejected_edit = call_pi_tool(
                "confirm_save_proposal",
                {
                    "proposal": edit_result["result"]["proposal"],
                    "confirmation_token": edit_result["result"]["confirmation"]["token"],
                },
                facade=facade,
            )

            self.assertEqual(rejected_edit["status"], "invalid_target")
            self.assertFalse(rejected_edit["result"]["write_performed"])
            self.assertEqual(self._memory_events(db_path), [])

            create_result = call_pi_tool(
                "propose_decision",
                {"title": "Existing decision", "rationale": "Create a valid target."},
                facade=facade,
            )
            created = call_pi_tool(
                "confirm_save_proposal",
                {
                    "proposal": create_result["result"]["proposal"],
                    "confirmation_token": create_result["result"]["confirmation"]["token"],
                },
                facade=facade,
            )
            rollback_result = call_pi_tool(
                "propose_decision",
                {
                    "operation": "rollback",
                    "target_memory_id": created["result"]["memory_id"],
                    "target_event_id": 9999,
                    "title": "Existing decision",
                    "rationale": "Bad rollback target.",
                },
                facade=facade,
            )
            rejected_rollback = call_pi_tool(
                "confirm_save_proposal",
                {
                    "proposal": rollback_result["result"]["proposal"],
                    "confirmation_token": rollback_result["result"]["confirmation"]["token"],
                },
                facade=facade,
            )

            self.assertEqual(rejected_rollback["status"], "invalid_target")
            self.assertFalse(rejected_rollback["result"]["write_performed"])
            self.assertEqual(len(self._memory_events(db_path)), 1)

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

    def test_project_mutation_tools_are_rejected_by_allowlist(self):
        catalog = build_pi_tool_catalog()
        catalog["approve_mvp_build"] = PITool(
            name="approve_mvp_build",
            description="Unsafe build approval.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=lambda _facade, _args: {"status": "ok"},
            read_only=False,
        )

        with self.assertRaisesRegex(ValueError, "Forbidden mutation tools.*approve_mvp_build"):
            validate_pi_tool_catalog(catalog)

    def test_custom_catalog_rejects_unlisted_tool_before_execution(self):
        catalog = build_pi_tool_catalog()

        def fail_if_called(_facade, _args):
            raise AssertionError("unlisted tool handler must not execute")

        catalog["google_search"] = PITool(
            name="google_search",
            description="Unapproved external search.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=fail_if_called,
        )

        result = call_pi_tool("google_search", {"query": "private"}, facade=object(), catalog=catalog)

        self.assertEqual(result["status"], "rejected")
        self.assertIn("explicit allowlist", result["message"])

    def test_archive_search_tool_schema_is_read_only_and_closed(self):
        catalog = build_pi_tool_catalog()
        tool = catalog["search_telegram_archive"]

        self.assertTrue(tool.read_only)
        self.assertEqual(tool.input_schema["additionalProperties"], False)
        self.assertEqual(tool.input_schema["properties"]["filters"]["additionalProperties"], False)
        serialized = json.dumps(tool.input_schema)
        for forbidden in ("write", "confirm", "mutate", "execute_sql", "db_path"):
            self.assertNotIn(forbidden, serialized)

    def test_project_context_tool_schema_is_read_only_and_closed(self):
        catalog = build_pi_tool_catalog()
        tool = catalog["analyze_project_context"]

        self.assertTrue(tool.read_only)
        self.assertFalse(tool.requires_confirmation)
        self.assertEqual(tool.input_schema["additionalProperties"], False)
        serialized = json.dumps(tool.input_schema)
        for forbidden in ("write", "confirm", "mutate", "execute_sql", "db_path", "approve"):
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

    def test_project_context_tool_combines_descriptor_archive_and_curated_knowledge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "archive.db"
            projects_path = self._write_project_descriptors(root)
            self._write_workbook(root)
            self._write_archive_db(
                db_path,
                content=(
                    "Coding-agent evals need ground truth labels, citation correctness checks, "
                    "and holdout sets before release."
                ),
            )
            result = call_pi_tool(
                "analyze_project_context",
                {
                    "query": "What applies to Eval-Ground-Truth-Lab?",
                    "project_name": "Eval-Ground-Truth-Lab",
                    "limit": 3,
                },
                facade=self._facade_with_db_and_projects(root, db_path, projects_path),
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["evidence_status"], "available")
        payload = result["result"]
        self.assertEqual(payload["schema_version"], "project_context_decision_support.v1")
        self.assertEqual(payload["project_name"], "Eval-Ground-Truth-Lab")
        self.assertEqual(payload["relevance_label"], "direct_implication")
        self.assertIn("keywords", payload["descriptor_fields_used"])
        self.assertIn("https://t.me/source/1001", payload["archive_evidence"]["source_refs"])
        self.assertTrue(payload["project_suggestions"])
        self.assertFalse(payload["decision_support"]["automatic_mvp_build_approval"])
        self.assertFalse(payload["decision_support"]["code_mutation_exposed"])
        self.assertFalse(payload["decision_support"]["project_mutation_exposed"])

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
