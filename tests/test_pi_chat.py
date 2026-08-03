import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from assistant.pi_chat import (
    answer_pi_chat,
    route_pi_intent,
    validate_grounded_answer_contract,
)
from assistant.prm_chat_display import build_prm_chat_receipt, render_prm_chat_answer
from assistant.pi_facade import PersonalIntelligenceFacade
from assistant.project_context import build_project_context_decision_support
from assistant.pi_tools import call_pi_tool
from config.settings import Settings
from llm.client import set_usage_db_path


class _FakeFacade:
    def get_workbook_summary(self, week_label=None):
        return {
            "status": "ok",
            "week_label": week_label or "2026-W28",
            "decision_brief": [{"title": "Eval gates", "summary": "Eval gates matter."}],
            "artifact_paths": {"html": "/tmp/workbook.html"},
            "message": "Workbook summary loaded.",
        }

    def get_artifact_status(self, week_label=None):
        return {
            "status": "partial",
            "week_label": week_label or "2026-W28",
            "weekly_brief": {"display_name": "Weekly Brief", "status": "current"},
            "knowledge_atlas": {"display_name": "Knowledge Atlas", "status": "current"},
            "mvp_radar": {"display_name": "MVP Radar", "status": "missing"},
            "mvp_radar_gate": {
                "decision": "do_not_build",
                "matched_gate_evidence_count": 0,
                "market_context_status": "context_only",
            },
            "artifact_paths": {
                "weekly_intelligence_brief_json": "/tmp/2026-W28.weekly-brief.json",
                "knowledge_atlas_json": "/tmp/2026-W28.knowledge-atlas.json",
            },
            "message": "Weekly Brief: current; Knowledge Atlas: current; MVP Radar: missing",
        }

    def search_intelligence_items(self, query, filters=None, limit=10):
        return {
            "status": "ok",
            "query": query,
            "filters": filters or {},
            "items": [
                {
                    "id": "claim-1",
                    "item_type": "claim_card",
                    "title": "Eval gates",
                    "summary": "Eval gates are now release infrastructure.",
                    "source_refs": ["https://t.me/source/1"],
                    "atom_ids": [101],
                }
            ],
            "message": "Curated intelligence items matched deterministic search.",
        }

    def search_telegram_archive(self, query, filters=None, limit=10):
        return {
            "status": "ok",
            "query": query,
            "filters": filters or {},
            "retrieval_mode": "sqlite_fts_archive",
            "items": [
                {
                    "archive_document_id": "tg:-1001:1001",
                    "post_archive_document_id": "tg:-1001:1001",
                    "post_id": 1,
                    "raw_post_id": 100,
                    "channel_username": "@source",
                    "channel_id": -1001,
                    "message_id": 1001,
                    "posted_at": "2026-07-20T10:00:00Z",
                    "source_url": "https://t.me/source/1001",
                    "language": "ru",
                    "snippet": "Agent review automation works over retained Telegram archive posts.",
                    "content_hash": "sha256:fixture",
                    "chunk_index": None,
                    "chunk_count": 1,
                    "reaction_count": 0,
                    "tag_count": 0,
                    "project_names": [],
                }
            ],
            "message": "Telegram archive posts matched SQLite FTS search.",
        }

    def get_action_statuses(self, week_label=None):
        return {
            "status": "ok",
            "week_label": week_label,
            "items": [{"title": "Try eval gate", "status": "unknown"}],
            "message": "Action statuses loaded.",
        }

    def get_project_actions(self, week_label=None):
        return {
            "status": "ok",
            "week_label": week_label,
            "items": [{"project": "telegram-research-agent", "action": "Test Hermes chat"}],
            "message": "Project actions loaded.",
        }

    def analyze_project_context(self, query, project_name=None, week_label=None, limit=5):
        return build_project_context_decision_support(
            query=query,
            project_descriptor={
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
            },
            archive_result={
                "status": "ok",
                "items": [
                    {
                        "archive_document_id": "tg:-1001:1001",
                        "posted_at": "2026-07-20T10:00:00Z",
                        "source_url": "https://t.me/source/1001",
                        "snippet": "Coding-agent evals need ground truth labels, citation correctness checks, and holdout sets.",
                    }
                ],
            },
            curated_result={
                "status": "ok",
                "items": [
                    {
                        "id": "claim-1",
                        "item_type": "claim_card",
                        "summary": "Evidence-backed acceptance fixtures help judge calibration.",
                        "source_refs": ["https://t.me/source/1002"],
                        "atom_ids": [101],
                    }
                ],
            },
        )


class _FakeLLM:
    @staticmethod
    def complete_json(prompt, system="", category="unknown", model=None):
        return {
            "tool_calls": [
                {"name": "get_weekly_summary", "arguments": {"week_label": "2026-W28"}},
                {"name": "search_intelligence_items", "arguments": {"query": "eval gates", "limit": 3}},
            ],
            "reason": "Need weekly context and specific curated evidence.",
        }

    @staticmethod
    def complete(prompt, system="", max_tokens=2048, category="unknown", model=None):
        assert "Eval gates are now release infrastructure" in prompt
        assert "https://t.me/source/1" in prompt
        return "Eval gates matter this week. Source: https://t.me/source/1; atom:101."


class _BrokenPlannerLLM(_FakeLLM):
    @staticmethod
    def complete_json(prompt, system="", category="unknown", model=None):
        raise RuntimeError("planner unavailable")

    @staticmethod
    def complete(prompt, system="", max_tokens=2048, category="unknown", model=None):
        return "Hermes found curated actions and evidence. Source: https://t.me/source/1."


class _NoAnswerLLM(_BrokenPlannerLLM):
    @staticmethod
    def complete(prompt, system="", max_tokens=2048, category="unknown", model=None):
        raise RuntimeError("answer unavailable")


class _ArchiveSearchLLM(_FakeLLM):
    @staticmethod
    def complete_json(prompt, system="", category="unknown", model=None):
        return {
            "tool_calls": [
                {"name": "search_telegram_archive", "arguments": {"query": "agent review", "limit": 3}},
            ],
            "reason": "Need original Telegram source evidence.",
        }

    @staticmethod
    def complete(prompt, system="", max_tokens=2048, category="unknown", model=None):
        assert "https://t.me/source/1001" in prompt
        return "Нашёл пост в архиве: https://t.me/source/1001"


class _ExternalVerificationLLM(_FakeLLM):
    @staticmethod
    def complete_json(prompt, system="", category="unknown", model=None):
        raise AssertionError("External verification routes must bypass LLM planning.")

    @staticmethod
    def complete(prompt, system="", max_tokens=2048, category="unknown", model=None):
        assert "external_evidence" in prompt
        assert "not_run_unapproved" in prompt
        return "\n".join(
            [
                "Archive evidence: no Telegram archive evidence was collected for this verification request.",
                "External verification: required and not run.",
                "Unknowns: current external truth; independent source corroboration; Telegram archive support.",
            ]
        )


class _SaveProposalLLM(_FakeLLM):
    @staticmethod
    def complete_json(prompt, system="", category="unknown", model=None):
        return {
            "tool_calls": [
                {
                    "name": "propose_knowledge_note",
                    "arguments": {
                        "title": "Save only after confirmation",
                        "body": "Chat text must not become durable memory automatically.",
                    },
                }
            ],
            "reason": "Draft a proposal only.",
        }

    @staticmethod
    def complete(prompt, system="", max_tokens=2048, category="unknown", model=None):
        assert "needs_confirmation" in prompt
        assert "confirm_save_proposal" in prompt
        return "I drafted a save proposal. It is not stored until you confirm it."


class _ProjectContextLLM(_FakeLLM):
    @staticmethod
    def complete_json(prompt, system="", category="unknown", model=None):
        raise AssertionError("Project context routes must bypass LLM planning.")

    @staticmethod
    def complete(prompt, system="", max_tokens=2048, category="unknown", model=None):
        raise AssertionError("Project context answer is deterministic.")


class _WrongArchivePlannerLLM(_ArchiveSearchLLM):
    @staticmethod
    def complete_json(prompt, system="", category="unknown", model=None):
        return {
            "tool_calls": [
                {"name": "get_weekly_summary", "arguments": {"week_label": "2026-W28"}},
            ],
            "reason": "Wrong planner route for a deterministic archive query.",
        }


class _EmptyArchiveFacade(_FakeFacade):
    def search_telegram_archive(self, query, filters=None, limit=10):
        return {
            "status": "insufficient_evidence",
            "query": query,
            "filters": filters or {},
            "retrieval_mode": "sqlite_fts_archive",
            "items": [],
            "message": "No retained Telegram archive evidence matched the query.",
        }


class _ArchiveNoAnswerLLM(_ArchiveSearchLLM):
    @staticmethod
    def complete(prompt, system="", max_tokens=2048, category="unknown", model=None):
        raise RuntimeError("answer unavailable")


class _HallucinatedNoAnswerLLM(_ArchiveSearchLLM):
    @staticmethod
    def complete(prompt, system="", max_tokens=2048, category="unknown", model=None):
        return "Нашёл пост в архиве: https://t.me/source/1001"


class _Receipt:
    def __init__(self, text: str, *, usage_recorded: bool):
        self.text = text
        self.model = "claude-haiku-4-5"
        self.input_tokens = 10
        self.output_tokens = 5
        self.estimated_cost_usd = 0.00001
        self.duration_ms = 1
        self.attempts = 1
        self.usage_recorded = usage_recorded


class _UsageRecordingReceiptLLM:
    @staticmethod
    def complete_with_receipt(**kwargs):
        from llm import client as llm_client_module

        usage_recorded = llm_client_module._record_usage(
            str(kwargs.get("category") or "unknown"),
            "claude-haiku-4-5",
            10,
            5,
            1,
        )
        if "max_tokens" in kwargs:
            return _Receipt("Eval gates matter this week. Source: https://t.me/source/1.", usage_recorded=usage_recorded)
        return _Receipt(
            json.dumps(
                {
                    "tool_calls": [
                        {"name": "search_intelligence_items", "arguments": {"query": "eval gates", "limit": 3}}
                    ],
                    "reason": "Need curated evidence.",
                }
            ),
            usage_recorded=usage_recorded,
        )


class TestPIChat(unittest.TestCase):
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

    def test_answer_pi_chat_runs_llm_planned_read_only_tools(self):
        result = answer_pi_chat("Что с eval gates?", facade=_FakeFacade(), llm_client=_FakeLLM)

        self.assertEqual(result["status"], "ok")
        self.assertIn("Eval gates matter", result["answer"])
        self.assertEqual([call["name"] for call in result["tool_calls"]], ["get_weekly_summary", "search_intelligence_items"])
        self.assertIn("https://t.me/source/1", result["evidence"]["source_refs"])
        self.assertIn(101, result["evidence"]["atom_ids"])
        self.assertTrue(all(call["name"] != "run_codex" for call in result["tool_calls"]))
        self.assertEqual(result["trace"]["schema_version"], "pi_assistant_trace.v1")
        self.assertEqual(result["trace"]["termination_reason"], "answered_with_evidence")
        self.assertFalse(result["trace"]["privacy_boundary"]["raw_telegram_text_egress"])
        self.assertEqual(result["trace"]["tool_traces"][1]["result_count"], 1)
        self.assertEqual(result["telemetry"]["schema_version"], "pi_answer_telemetry.v1")
        self.assertEqual(result["telemetry"]["planning"]["model_calls"], 1)
        self.assertEqual(result["telemetry"]["generation"]["model_calls"], 1)

    def test_answer_pi_chat_rejects_non_catalog_tool(self):
        class BadToolLLM(_FakeLLM):
            @staticmethod
            def complete_json(prompt, system="", category="unknown", model=None):
                return {"tool_calls": [{"name": "run_codex", "arguments": {"prompt": "do it"}}]}

        result = answer_pi_chat("Запусти Codex", facade=_FakeFacade(), llm_client=BadToolLLM)

        self.assertEqual(result["tool_results"][0]["status"], "rejected")
        self.assertIn("not in read-only PI catalog", result["tool_results"][0]["result"]["message"])

    def test_answer_pi_chat_can_use_archive_search_with_source_link(self):
        result = answer_pi_chat("Найди пост про agent review", facade=_FakeFacade(), llm_client=_ArchiveSearchLLM)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            result["tool_calls"],
            [
                {
                    "name": "search_telegram_archive",
                    "arguments": {"query": "Найди пост про agent review", "limit": 5},
                }
            ],
        )
        self.assertEqual(result["trace"]["planner"], "deterministic")
        self.assertEqual(result["telemetry"]["planning"]["model_calls"], 0)
        self.assertIn("https://t.me/source/1001", result["answer"])
        self.assertIn("https://t.me/source/1001", result["evidence"]["source_refs"])
        self.assertTrue(result["trace"]["privacy_boundary"]["raw_telegram_text_egress"])
        self.assertFalse(result["trace"]["privacy_boundary"]["raw_telegram_corpus_egress"])
        self.assertTrue(result["trace"]["privacy_boundary"]["bounded_telegram_snippet_provider_egress"])
        contract = validate_grounded_answer_contract(result["answer_contract"])
        self.assertEqual(contract["archive_support"]["status"], "available")
        self.assertEqual(contract["source_links"], ["https://t.me/source/1001"])
        self.assertEqual(
            contract["freshness_date_boundary"]["max_source_date"],
            "2026-07-20T10:00:00Z",
        )
        self.assertFalse(contract["model_background"]["used"])
        self.assertFalse(contract["external_verification"]["required"])

    def test_prm_chat_display_shows_contract_without_raw_tool_payload(self):
        result = answer_pi_chat("Найди пост про agent review", facade=_FakeFacade(), llm_client=_ArchiveSearchLLM)

        rendered = render_prm_chat_answer(result, mode="llm-approved")
        self.assertIn("PRM Chat", rendered)
        self.assertIn("Нашёл пост в архиве", rendered)
        self.assertIn("Sources\n- https://t.me/source/1001", rendered)
        self.assertIn("Archive support: status=supported; source_count=1", rendered)
        self.assertIn("Unknowns: none", rendered)
        self.assertIn(
            "Privacy: mode=llm-approved; model_calls=1; estimated_cost_usd=0; "
            "bounded_telegram_snippet_provider_egress=true; raw_telegram_corpus_egress=false; "
            "durable_writes=false",
            rendered,
        )
        self.assertNotIn("Agent review automation works over retained Telegram archive posts", rendered)

        receipt = build_prm_chat_receipt(result, mode="llm-approved")
        self.assertEqual(receipt["schema_version"], "prm_chat_display.v1")
        self.assertEqual(receipt["archive_support"]["status"], "supported")
        self.assertTrue(receipt["privacy"]["bounded_telegram_snippet_provider_egress"])
        self.assertNotIn(
            "Agent review automation works over retained Telegram archive posts",
            json.dumps(receipt, ensure_ascii=False),
        )

    def test_deterministic_archive_route_ignores_wrong_llm_plan(self):
        result = answer_pi_chat("Найди пост про agent review", facade=_FakeFacade(), llm_client=_WrongArchivePlannerLLM)

        self.assertEqual(result["trace"]["planner"], "deterministic")
        self.assertEqual([call["name"] for call in result["tool_calls"]], ["search_telegram_archive"])
        self.assertEqual(result["telemetry"]["planning"]["model_calls"], 0)

    def test_answer_pi_chat_no_answer_does_not_fabricate_archive_citation(self):
        result = answer_pi_chat("Найди пост которого нет", facade=_EmptyArchiveFacade(), llm_client=_ArchiveNoAnswerLLM)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["tool_results"][0]["status"], "insufficient_evidence")
        self.assertEqual(result["evidence"]["source_refs"], [])
        self.assertIn("insufficient_evidence", result["answer"])
        self.assertNotIn("https://t.me/source/1001", result["answer"])
        self.assertEqual(result["trace"]["termination_reason"], "insufficient_evidence")
        self.assertTrue(result["trace"]["insufficient_evidence"])
        self.assertEqual(result["answer_contract"]["archive_support"]["status"], "insufficient_evidence")
        self.assertTrue(result["answer_contract"]["insufficient_evidence"])
        self.assertEqual(
            result["answer_contract"]["model_background"]["label"],
            "background_not_archive_supported",
        )

    def test_answer_pi_chat_replaces_hallucinated_no_answer_generation(self):
        result = answer_pi_chat("Найди пост которого нет", facade=_EmptyArchiveFacade(), llm_client=_HallucinatedNoAnswerLLM)

        self.assertEqual(result["trace"]["termination_reason"], "insufficient_evidence")
        self.assertIn("Evidence is missing or insufficient", result["answer"])
        self.assertNotIn("https://t.me/source/1001", result["answer"])
        self.assertEqual(result["answer_contract"]["archive_support"]["status"], "insufficient_evidence")

    def test_answer_pi_chat_falls_back_when_planning_fails(self):
        result = answer_pi_chat("Что делать с eval gates?", facade=_FakeFacade(), llm_client=_BrokenPlannerLLM)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["tool_calls"])
        self.assertIn("Source:", result["answer"])

    def test_answer_pi_chat_falls_back_to_artifact_status_for_brief_atlas_radar(self):
        result = answer_pi_chat("Какие артефакты Brief Atlas Radar актуальны?", facade=_FakeFacade(), llm_client=_NoAnswerLLM)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["tool_calls"][0]["name"], "get_artifact_status")
        self.assertIn("get_artifact_status", result["answer"])
        self.assertIn("MVP Radar", result["tool_results"][0]["result"]["message"])
        self.assertIn("/tmp/2026-W28.weekly-brief.json", result["answer"])

    def test_answer_pi_chat_handles_empty_question(self):
        result = answer_pi_chat("", facade=_FakeFacade(), llm_client=_FakeLLM)

        self.assertEqual(result["status"], "invalid")
        self.assertIn("Напиши вопрос", result["answer"])
        self.assertEqual(result["trace"]["termination_reason"], "invalid_request")

    def test_deterministic_router_covers_exact_reaction_and_no_answer(self):
        exact = route_pi_intent("Найди пост про agent review")
        self.assertEqual(exact["intent"], "exact_search")
        self.assertEqual(exact["tool_calls"][0]["name"], "search_telegram_archive")

        reaction = route_pi_intent("Найди отмеченный мной реакцией пост")
        self.assertEqual(reaction["intent"], "reaction_recall")
        self.assertEqual(
            reaction["tool_calls"][0]["arguments"]["filters"],
            {"reacted_only": True},
        )

        no_answer = route_pi_intent("Найди пост которого нет")
        self.assertEqual(no_answer["intent"], "no_answer_probe")
        self.assertEqual(no_answer["tool_calls"][0]["name"], "search_telegram_archive")

    def test_external_verification_route_does_not_call_external_provider(self):
        route = route_pi_intent("Проверь во внешних источниках свежую новость")

        self.assertEqual(route["intent"], "external_verification")
        self.assertEqual(route["tool_calls"][0]["name"], "request_external_verification")
        self.assertEqual(route["tool_calls"][0]["arguments"]["category"], "explicit_external_verification")

    def test_high_stakes_categories_require_external_verification(self):
        cases = {
            "pricing": "What is the OpenAI pricing for this model?",
            "legal": "Is this contract clause legal?",
            "medical": "What medical treatment is recommended here?",
            "financial": "Should I invest in this stock?",
            "career_market": "What is the job market for AI engineers?",
            "visa": "What visa rule applies to this case?",
        }

        for expected_category, question in cases.items():
            with self.subTest(expected_category=expected_category):
                route = route_pi_intent(question)
                tool_names = [call["name"] for call in route["tool_calls"]]

                self.assertEqual(route["intent"], "external_verification")
                self.assertEqual(tool_names, ["request_external_verification"])
                self.assertEqual(route["tool_calls"][0]["arguments"]["category"], expected_category)

    def test_external_verification_terms_do_not_overmatch_internal_questions(self):
        openclaw = route_pi_intent("Что известно про openclaw из архива?")
        project_now = route_pi_intent("What should I do now about project actions?")

        self.assertEqual(openclaw["intent"], "exact_search")
        self.assertEqual(project_now["intent"], "project_application")

    def test_project_application_answer_uses_project_context_support(self):
        result = answer_pi_chat(
            "What applies to Eval-Ground-Truth-Lab project?",
            facade=_FakeFacade(),
            llm_client=_ProjectContextLLM,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["trace"]["planner"], "deterministic")
        self.assertEqual(result["telemetry"]["planning"]["model_calls"], 0)
        self.assertEqual(result["telemetry"]["generation"]["model_calls"], 0)
        self.assertEqual(result["telemetry"]["generation"]["cost_source"], "deterministic_project_context")
        self.assertEqual([call["name"] for call in result["tool_calls"]], ["analyze_project_context"])
        self.assertIn("Eval-Ground-Truth-Lab -> direct_implication", result["answer"])
        self.assertIn("Descriptor fields used:", result["answer"])
        self.assertIn("https://t.me/source/1001", result["answer"])
        self.assertIn("no MVP build approval", result["answer"])
        self.assertFalse(result["trace"]["privacy_boundary"]["write_performed"])
        self.assertFalse(result["trace"]["privacy_boundary"]["raw_telegram_corpus_egress"])
        self.assertFalse(result["trace"]["privacy_boundary"]["bounded_telegram_snippet_provider_egress"])

        contract = validate_grounded_answer_contract(result["answer_contract"])
        self.assertEqual(contract["archive_support"]["status"], "available")
        self.assertIn("https://t.me/source/1001", contract["source_links"])

    def test_external_verification_answer_separates_evidence_and_unknowns(self):
        result = answer_pi_chat(
            "What is the current price for this product?",
            facade=_FakeFacade(),
            llm_client=_ExternalVerificationLLM,
        )

        self.assertEqual(result["trace"]["planner"], "deterministic")
        self.assertEqual([call["name"] for call in result["tool_calls"]], ["request_external_verification"])
        self.assertEqual(result["trace"]["termination_reason"], "needs_external_verification")
        self.assertFalse(result["trace"]["privacy_boundary"]["external_skill_used"])
        self.assertFalse(result["trace"]["privacy_boundary"]["raw_telegram_corpus_egress"])
        self.assertFalse(result["trace"]["privacy_boundary"]["bounded_telegram_snippet_provider_egress"])

        contract = validate_grounded_answer_contract(result["answer_contract"])
        self.assertEqual(contract["archive_support"]["status"], "insufficient_evidence")
        self.assertEqual(contract["external_verification"]["status"], "required_not_run")
        self.assertEqual(contract["external_verification"]["category"], "pricing")
        self.assertEqual(contract["external_verification"]["external_source_links"], [])
        self.assertIn("current external truth", contract["unknowns"])
        self.assertIn("Telegram archive support", contract["unknowns"])
        self.assertEqual(
            contract["evidence_sections"]["archive_evidence"]["source_links"],
            [],
        )
        self.assertEqual(contract["evidence_sections"]["external_evidence"]["status"], "required_not_run")

    def test_chat_save_request_drafts_proposal_without_persisting_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "memory.db"
            facade = PersonalIntelligenceFacade(
                settings=Settings(
                    db_path=str(db_path),
                    llm_api_key="",
                    model_provider="",
                    telegram_session_path="",
                ),
                output_root=root,
            )
            result = answer_pi_chat(
                "Save this as a note: chat text must not become durable memory.",
                facade=facade,
                llm_client=_SaveProposalLLM,
            )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["tool_calls"][0]["name"], "propose_knowledge_note")
            self.assertEqual(result["tool_results"][0]["status"], "needs_confirmation")
            self.assertFalse(result["tool_results"][0]["result"]["result"]["persisted"])
            self.assertEqual(result["trace"]["termination_reason"], "needs_confirmation")
            self.assertEqual(result["trace"]["tool_traces"][0]["privacy_boundary"], "proposal_only_no_write")
            self.assertFalse(result["trace"]["privacy_boundary"]["write_performed"])
            self.assertFalse(db_path.exists())
            rendered = render_prm_chat_answer(result, mode="llm-approved")
            self.assertIn("pending_confirmation=true", rendered)
            self.assertIn("durable_writes=false", rendered)

    def test_confirmed_save_trace_marks_confirmation_gated_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "memory.db"
            self._migrate_db(db_path)
            facade = PersonalIntelligenceFacade(
                settings=Settings(
                    db_path=str(db_path),
                    llm_api_key="",
                    model_provider="",
                    telegram_session_path="",
                ),
                output_root=root,
            )
            proposal_result = call_pi_tool(
                "propose_decision",
                {"title": "Record explicit confirmation", "rationale": "Trace writes must be visible."},
                facade=facade,
            )

            class ConfirmSaveLLM(_FakeLLM):
                @staticmethod
                def complete_json(prompt, system="", category="unknown", model=None):
                    return {
                        "tool_calls": [
                            {
                                "name": "confirm_save_proposal",
                                "arguments": {
                                    "proposal": proposal_result["result"]["proposal"],
                                    "confirmation_token": proposal_result["result"]["confirmation"]["token"],
                                    "confirmed_at": "2026-07-27T10:00:00Z",
                                },
                            }
                        ],
                        "reason": "Operator supplied the exact proposal and token.",
                    }

                @staticmethod
                def complete(prompt, system="", max_tokens=2048, category="unknown", model=None):
                    return "Confirmed memory proposal persisted."

            result = answer_pi_chat("Confirm this saved decision", facade=facade, llm_client=ConfirmSaveLLM)

            self.assertEqual(result["tool_results"][0]["status"], "ok")
            self.assertEqual(result["trace"]["termination_reason"], "confirmed_write")
            self.assertTrue(result["trace"]["privacy_boundary"]["write_performed"])
            self.assertEqual(result["trace"]["tool_traces"][0]["privacy_boundary"], "confirmation_gated_write")

    def test_answer_telemetry_separates_retrieval_generation_and_excludes_raw_text(self):
        result = answer_pi_chat("Найди пост про agent review", facade=_FakeFacade(), llm_client=_ArchiveSearchLLM)

        telemetry = result["telemetry"]
        self.assertIn("latency_ms", telemetry["retrieval"])
        self.assertIn("latency_ms", telemetry["generation"])
        self.assertEqual(telemetry["retrieval"]["tool_calls"], 1)
        self.assertEqual(telemetry["retrieval"]["estimated_cost_usd"], 0.0)
        self.assertEqual(telemetry["generation"]["estimated_cost_usd"], 0.0)
        self.assertEqual(telemetry["generation"]["cost_source"], "fake_or_unmetered_no_receipt")
        self.assertTrue(telemetry["privacy"]["bounded_telegram_snippet_provider_egress"])
        self.assertFalse(telemetry["privacy"]["raw_telegram_corpus_egress"])
        self.assertFalse(telemetry["privacy"]["raw_post_text_logged"])
        self.assertNotIn(
            "Agent review automation works",
            json.dumps(telemetry, ensure_ascii=False),
        )

    def test_pi_chat_suppresses_llm_usage_database_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "usage.db"
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE llm_usage (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        called_at TEXT NOT NULL,
                        model TEXT NOT NULL,
                        task_type TEXT,
                        input_tokens INTEGER NOT NULL DEFAULT 0,
                        output_tokens INTEGER NOT NULL DEFAULT 0,
                        est_cost_usd REAL NOT NULL DEFAULT 0.0,
                        category TEXT,
                        cost_usd REAL NOT NULL DEFAULT 0.0,
                        duration_ms INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
            set_usage_db_path(str(db_path))
            try:
                result = answer_pi_chat("Что с eval gates?", facade=_FakeFacade(), llm_client=_UsageRecordingReceiptLLM)
            finally:
                set_usage_db_path("")

            with sqlite3.connect(db_path) as connection:
                usage_count = connection.execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0]

        self.assertEqual(result["status"], "ok")
        self.assertEqual(usage_count, 0)
        self.assertFalse(result["telemetry"]["privacy"]["llm_usage_db_write_performed"])


if __name__ == "__main__":
    unittest.main()
