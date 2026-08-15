import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import nullcontext
from unittest.mock import patch


def _install_stub(module_name: str, **attributes: object) -> None:
    if module_name in sys.modules:
        return
    module = types.ModuleType(module_name)
    for name, value in attributes.items():
        setattr(module, name, value)
    sys.modules[module_name] = module


_install_stub(
    "anthropic",
    APIConnectionError=Exception,
    APIStatusError=Exception,
    APITimeoutError=Exception,
    Anthropic=object,
    RateLimitError=Exception,
)
_install_stub("telethon")
_install_stub("weasyprint")
_install_stub("jinja2")

from config.settings import Settings  # noqa: E402
from db.ai_report_feedback import fetch_ai_report_feedback, fetch_ai_report_feedback_intake  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
from output.report_schema import DigestResult  # noqa: E402
from output.mvp_weekly_pipeline import MvpWeeklyPipelineResult  # noqa: E402
import bot.handlers as handlers  # noqa: E402


def _fake_prm_chat_payload(answer: str = "Hermes answer from curated PI tools.") -> dict:
    return {
        "status": "ok",
        "answer": answer,
        "tool_calls": [{"name": "search_intelligence_items", "arguments": {"query": "eval"}}],
        "tool_results": [
            {
                "name": "search_telegram_archive",
                "result": {
                    "result": {
                        "items": [
                            {
                                "source_url": "https://t.me/source/1",
                                "snippet": "RAW PRIVATE TOOL PAYLOAD",
                            }
                        ]
                    }
                },
            }
        ],
        "evidence": {"source_refs": ["https://t.me/source/1"], "atom_ids": [101]},
        "answer_contract": {
            "source_links": ["https://t.me/source/1"],
            "archive_support": {"status": "available", "source_count": 1},
            "unknowns": ["independent source corroboration"],
            "external_verification": {
                "required": False,
                "status": "not_required",
                "category": None,
                "reason": None,
                "external_source_links": [],
            },
        },
        "trace": {
            "termination_reason": "answered_with_evidence",
            "privacy_boundary": {
                "write_performed": False,
                "confirmation_gated_write": False,
                "bounded_telegram_snippet_provider_egress": True,
                "raw_telegram_corpus_egress": False,
            },
        },
        "telemetry": {
            "planning": {"model_calls": 1, "estimated_cost_usd": 0.00001},
            "generation": {"model_calls": 1, "estimated_cost_usd": 0.00002},
            "privacy": {
                "bounded_telegram_snippet_provider_egress": True,
                "raw_telegram_corpus_egress": False,
            },
        },
        "message": "ok",
    }


def _fake_research_payload(question: str = "что у меня было про AI transformation?") -> dict:
    return {
        "status": "ok",
        "question": question,
        "direct_answer": "По локальному архиву найдено 2 источника про AI transformation.",
        "archive_evidence": {
            "status": "ok",
            "retrieval_mode": "hybrid_local_vector_archive_query_planner",
            "items": [
                {
                    "posted_at": "2026-08-01T12:00:00Z",
                    "channel_username": "@ai_channel",
                    "snippet": "AI transformation pilots often fail to show measurable ROI.",
                    "source_url": "https://t.me/ai_channel/101",
                    "retrieval_mode": "sqlite_fts_archive",
                }
            ],
            "source_refs": ["https://t.me/ai_channel/101"],
        },
        "linked_source_evidence": {"items": []},
        "project_fit": {"relevance_label": "no_match"},
        "answer_gate": {
            "allow_answer": True,
            "external_verification_required": False,
            "current_claim_allowed": True,
            "reason": "answerable",
        },
        "next_steps": {"apply": [], "watch": ["Keep as source-backed editorial angle."], "ignore": [], "study": []},
        "unknowns": ["current external truth"],
        "privacy": {"model_calls": 0, "provider_egress": False},
        "receipt": {"budget": {"max_tool_calls": 4, "max_archive_sources": 5}, "tool_calls_used": 4},
    }


class TestHandlers(unittest.TestCase):
    def setUp(self):
        handlers._RESEARCH_DIALOG_STATE.clear()
        handlers._RESEARCH_DIALOG_MODE_STATE.clear()

    def test_send_message_does_not_escape_plain_text_when_parse_mode_is_none(self):
        with patch.object(handlers, "_send_text_internal") as mock_send:
            handlers.send_message("bot-token", "42", "1. Открой weekly HTML Workbook.", parse_mode=None)

        mock_send.assert_called_once_with(
            chat_id="42",
            text="1. Открой weekly HTML Workbook.",
            token="bot-token",
            parse_mode=None,
        )

    def test_send_message_escapes_only_markdown_v2_text(self):
        with patch.object(handlers, "_send_text_internal") as mock_send:
            handlers.send_message("bot-token", "42", "1. Открой weekly HTML Workbook.", parse_mode="MarkdownV2")

        mock_send.assert_called_once_with(
            chat_id="42",
            text=r"1\. Открой weekly HTML Workbook\.",
            token="bot-token",
            parse_mode="MarkdownV2",
        )

    def test_handle_start_is_plain_compact_and_without_escape_artifacts(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
            with patch.object(handlers, "send_message") as mock_send_message:
                handlers.handle_start(chat_id="42", args="", settings=settings)

        message = mock_send_message.call_args.args[2]
        self.assertIn("Просто напиши вопрос или отправь голосовое.", message)
        self.assertIn("Ручные команды остаются запасным вариантом", message)
        self.assertNotIn(r"\.", message)
        self.assertNotIn(r"1\.", message)

    def test_prm_start_is_operator_facing(self):
        settings = Settings(db_path=":memory:", llm_api_key="", model_provider="anthropic", telegram_session_path="")

        with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
            with patch.object(handlers, "send_message") as mock_send_message:
                handlers.handle_prm_start(chat_id="42", args="", settings=settings)

        message = mock_send_message.call_args.args[2]
        self.assertIn("Что обсуждали про agent evals", message)
        self.assertIn("Сохранение заметки всегда требует явного подтверждения", message)
        for internal in ("PRM_", "LLM", "Dogfood", "runtime", "hybrid RAG"):
            self.assertNotIn(internal, message)

    def test_handle_digest_sends_markdown_content_without_parse_mode(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            with sqlite3.connect(db_path) as connection:
                connection.execute("CREATE TABLE digests (week_label TEXT, content_md TEXT)")
                connection.execute(
                    "INSERT INTO digests (week_label, content_md) VALUES (?, ?)",
                    ("2026-W14", "* legacy markdown *"),
                )
                connection.commit()

            settings = Settings(
                db_path=db_path,
                llm_api_key="",
                model_provider="anthropic",
                telegram_session_path="",
            )

            with patch.object(handlers, "_compute_week_label", return_value="2026-W14"):
                with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                    with patch.object(handlers, "send_text") as mock_send_text:
                        handlers.handle_digest(chat_id="42", args="", settings=settings)

            mock_send_text.assert_called_once_with(
                chat_id="42",
                text="* legacy markdown *",
                token="bot-token",
                parse_mode=None,
            )
        finally:
            os.unlink(db_path)

    def test_handle_run_digest_relies_on_run_digest_delivery_only(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        summary = DigestResult(week_label="2026-W14", output_path="/tmp/digest.md", post_count=3, json_path="/tmp/digest.json")

        with patch.object(handlers, "run_digest", return_value=summary) as mock_run_digest:
            with patch.object(handlers, "send_report_preview") as mock_send_report_preview:
                with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                    handlers.handle_run_digest(chat_id="42", args="", settings=settings)

        mock_run_digest.assert_called_once_with(settings)
        mock_send_report_preview.assert_called_once_with(
            chat_id="42",
            title="Дайджест сгенерирован",
            summary_lines=["/tmp/digest.md", "/tmp/digest.json"],
            week_label="2026-W14",
            token="bot-token",
        )

    def test_handle_run_mvp_weekly_sends_preview(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        summary = MvpWeeklyPipelineResult(
            week_label="2026-W22",
            seed_path="/tmp/seeds.json",
            seed_count=4,
            radar_status="selected",
            report_path="/tmp/mvp.md",
            json_path="/tmp/mvp.json",
            selected_title="Telegram Channel SEO Site Generator",
            dossier_status="generated",
            recommendation="focused_experiment",
            score=78,
        )

        with patch.object(handlers, "run_mvp_weekly_pipeline", return_value=summary) as mock_run:
            with patch.object(handlers, "send_report_preview") as mock_preview:
                with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                    handlers.handle_run_mvp_weekly(chat_id="42", args="", settings=settings)

        mock_run.assert_called_once_with(settings, deliver=True)
        mock_preview.assert_called_once()
        self.assertEqual(mock_preview.call_args.kwargs["title"], "MVP of the Week generated")
        self.assertTrue(
            any(
                "Telegram Channel SEO Site Generator" in line
                for line in mock_preview.call_args.kwargs["summary_lines"]
            )
        )

    def test_hpi_hermes_commands_are_registered(self):
        for command in [
            "/weekly",
            "/actions",
            "/explain",
            "/projects",
            "/mvp",
            "/strategy",
            "/codex",
            "/chat",
            "/hermes",
            "/auto",
            "/research",
            "/brief",
        ]:
            self.assertIn(command, handlers.HANDLERS)

    def test_handle_chat_uses_bounded_pi_chat(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        pi_chat_result = _fake_prm_chat_payload()

        with patch.dict(os.environ, {"PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": "1"}, clear=False):
            with patch.object(handlers, "answer_pi_chat", return_value=pi_chat_result) as mock_chat:
                with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                    with patch.object(handlers, "send_message") as mock_send_message:
                        handlers.handle_chat(chat_id="42", args="что с eval gates?", settings=settings)

        mock_chat.assert_called_once_with("что с eval gates?", settings=settings)
        self.assertEqual(mock_send_message.call_count, 1)
        message = mock_send_message.call_args_list[0].args[2]
        self.assertIn("PRM Chat", message)
        self.assertIn("Hermes answer from curated PI tools.", message)
        self.assertIn("Sources\n- https://t.me/source/1", message)
        self.assertIn("Archive support: status=supported; source_count=1", message)
        self.assertIn("Unknowns\n- independent source corroboration", message)
        self.assertIn("Privacy: mode=llm-approved", message)
        self.assertNotIn("RAW PRIVATE TOOL PAYLOAD", message)

    def test_handle_chat_requires_telegram_provider_egress_flag(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        with patch.dict(os.environ, {"PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": ""}, clear=False):
            with patch.object(handlers, "answer_pi_chat") as mock_chat:
                with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                    with patch.object(handlers, "send_message") as mock_send_message:
                        handlers.handle_chat(chat_id="42", args="что с eval gates?", settings=settings)

        mock_chat.assert_not_called()
        message = mock_send_message.call_args.args[2]
        self.assertIn("provider egress is not approved", message)
        self.assertIn("/research <question>", message)
        self.assertIn("No provider call was made", message)

    def test_prm_safe_start_help_hides_legacy_generation_commands(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
            with patch.object(handlers, "send_message") as mock_send_message:
                handlers.dispatch_command(
                    chat_id="42",
                    text="/start",
                    settings=settings,
                    runtime_mode=handlers.BOT_RUNTIME_PRM_ASSISTANT,
                )

        message = mock_send_message.call_args.args[2]
        self.assertIn("Личный помощник по исследованию", message)
        self.assertIn("Просто напиши вопрос или отправь голосовое.", message)
        self.assertIn("Что обсуждали про agent evals", message)
        self.assertIn("Команды /research и /brief — запасной вариант.", message)
        self.assertIn("Сохранение заметки всегда требует явного подтверждения.", message)
        self.assertNotIn("/run_digest", message)
        self.assertNotIn("/run_mvp_weekly", message)
        self.assertNotIn("/feedback_confirm", message)
        self.assertNotIn("PRM_TELEGRAM_", message)

    def test_prm_start_copy_contract_after_prm_ux_1(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
            with patch.object(handlers, "send_message") as mock_send_message:
                handlers.dispatch_command(
                    chat_id="42",
                    text="/help",
                    settings=settings,
                    runtime_mode=handlers.BOT_RUNTIME_PRM_ASSISTANT,
                )

        message = mock_send_message.call_args.args[2]
        self.assertIn("Просто напиши вопрос или отправь голосовое.", message)
        self.assertIn("Команды /research и /brief — запасной вариант.", message)

    def test_refresh_owner_only(self):
        settings = Settings(db_path=":memory:", llm_api_key="", model_provider="anthropic", telegram_session_path="")
        with patch.dict(os.environ, {"TELEGRAM_OWNER_CHAT_ID": "42"}, clear=False):
            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as send_mock:
                    handlers.handle_refresh("41", "", settings)
                    self.assertIn("только владельцу", send_mock.call_args.args[2])
                    handlers.handle_refresh("42", "", settings)

        self.assertIn("Статус обновления (dry-run)", send_mock.call_args.args[2])
        self.assertIn("Ничего не запускалось", send_mock.call_args.args[2])

    def test_reactions_owner_only_and_readonly_proposal(self):
        settings = Settings(db_path="/missing.db", llm_api_key="", model_provider="anthropic", telegram_session_path="")
        receipt = {"fixture": "reaction-receipt"}

        with patch.dict(os.environ, {"TELEGRAM_OWNER_CHAT_ID": "42"}, clear=False):
            with patch.object(handlers, "_load_reaction_receipt_readonly", return_value=receipt):
                with patch.object(handlers, "render_operator_reaction_receipt", return_value="Реакции в архиве"):
                    with patch.object(handlers, "build_reaction_preference_proposal", return_value={"status": "needs_confirmation", "write_performed": False}):
                        with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                            with patch.object(handlers, "send_message") as send_mock:
                                handlers.handle_reactions("41", "", settings)
                                self.assertIn("только владельцу", send_mock.call_args.args[2])
                                handlers.handle_reactions("42", "", settings)

        self.assertIn("Реакции в архиве", send_mock.call_args.args[2])
        self.assertIn("не сохранено", send_mock.call_args.args[2])

    def test_auto_route_intent_acknowledgement_copy(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        payload = {"status": "ok", "question": "what changed?", "privacy": {"model_calls": 0}}

        with patch.dict(os.environ, {"PRM_TELEGRAM_AUTO_LLM_ROUTER": "", "PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": ""}, clear=False):
            with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
                with patch.object(handlers, "render_memory_research_answer", return_value="PRM Research"):
                    with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                        with patch.object(handlers, "send_message") as mock_send_message:
                            handlers.handle_auto(chat_id="42", args="что нового?", settings=settings)

        research_mock.assert_called_once()
        message = mock_send_message.call_args.args[2]
        self.assertTrue(message.startswith("Проверю по локальному архиву."))
        self.assertEqual(message.count("Проверю по локальному архиву."), 1)

    def test_auto_route_ambiguous_intent_clarification_is_local(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        with patch.dict(os.environ, {"PRM_TELEGRAM_AUTO_LLM_ROUTER": "1", "PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": "1"}, clear=False):
            with patch.object(handlers.LLMClient, "complete_json") as llm_mock:
                with patch.object(handlers, "answer_memory_research") as research_mock:
                    with patch.object(handlers, "answer_pi_chat") as chat_mock:
                        with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                            with patch.object(handlers, "send_message") as mock_send_message:
                                handlers.handle_auto(chat_id="42", args="помоги", settings=settings)

        llm_mock.assert_not_called()
        research_mock.assert_not_called()
        chat_mock.assert_not_called()
        self.assertEqual(mock_send_message.call_count, 1)
        message = mock_send_message.call_args.args[2]
        self.assertIn("Уточни", message)
        self.assertIn("найти", message)
        self.assertIn("бриф", message)

    def test_auto_route_keeps_project_decision_request_in_grounded_research(self):
        with patch.dict(os.environ, {"PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": "1", "PRM_TELEGRAM_AUTO_LLM_ROUTER": "1"}, clear=False):
            with patch.object(handlers.LLMClient, "complete_json") as llm_mock:
                route = handlers._route_auto_message(
                    "project-decision-route",
                    "Какие практические выводы для моего проекта можно сделать из материалов про AI adoption?",
                )

        self.assertEqual(route["mode"], "research")
        self.assertEqual(route["router"], "deterministic_project_decision")
        self.assertFalse(route["model_call_attempted"])
        llm_mock.assert_not_called()

    def test_prm_safe_command_allowlist_blocks_legacy_generators(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        with patch.object(handlers, "run_digest") as mock_run_digest:
            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as mock_send_message:
                    handlers.dispatch_command(
                        chat_id="42",
                        text="/run_digest force",
                        settings=settings,
                        runtime_mode=handlers.BOT_RUNTIME_PRM_ASSISTANT,
                    )

        mock_run_digest.assert_not_called()
        message = mock_send_message.call_args.args[2]
        self.assertIn("не входит в обычный путь", message)
        self.assertIn("Просто напиши", message)
        self.assertIn("Никаких legacy-отчётов", message)

    def test_prm_safe_blocks_operator_message_write_router(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        with patch.object(handlers, "classify_operator_message") as classify_mock:
            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as mock_send_message:
                    handlers.dispatch_command(
                        chat_id="42",
                        text="/message напомни завтра проверить workbook",
                        settings=settings,
                        runtime_mode=handlers.BOT_RUNTIME_PRM_ASSISTANT,
                    )

        classify_mock.assert_not_called()
        message = mock_send_message.call_args.args[2]
        self.assertIn("не входит в обычный путь", message)
        self.assertIn("/research", message)

    def test_prm_safe_blocks_direct_feedback_confirmation(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        with patch.object(handlers, "apply_confirmed_feedback_intake") as confirm_mock:
            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as mock_send_message:
                    handlers.dispatch_command(
                        chat_id="42",
                        text="/feedback_confirm 1",
                        settings=settings,
                        runtime_mode=handlers.BOT_RUNTIME_PRM_ASSISTANT,
                    )

        confirm_mock.assert_not_called()
        message = mock_send_message.call_args.args[2]
        self.assertIn("не входит в обычный путь", message)
        self.assertIn("скрытых записей", message)

    def test_prm_safe_command_allowlist_allows_chat(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        pi_chat_result = _fake_prm_chat_payload(answer="Safe PRM answer.")

        with patch.dict(os.environ, {"PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": "1"}, clear=False):
            with patch.object(handlers, "answer_pi_chat", return_value=pi_chat_result) as mock_chat:
                with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                    with patch.object(handlers, "send_message") as mock_send_message:
                        handlers.dispatch_command(
                            chat_id="42",
                            text="/chat what changed?",
                            settings=settings,
                            runtime_mode=handlers.BOT_RUNTIME_PRM_ASSISTANT,
                        )

        mock_chat.assert_called_once_with("what changed?", settings=settings)
        message = mock_send_message.call_args.args[2]
        self.assertIn("Safe PRM answer.", message)
        self.assertIn("Archive support: status=supported", message)
        self.assertIn("Privacy: mode=llm-approved", message)

    def test_handle_research_uses_local_memory_research_without_pi_chat(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        payload = {"status": "ok", "question": "что дальше?", "privacy": {"model_calls": 0}}

        with patch.object(handlers, "answer_pi_chat") as chat_mock:
            with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
                with patch.object(handlers, "render_memory_research_answer", return_value="PRM Research\nPrivacy: mode=local-research; model_calls=0") as render_mock:
                    with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                        with patch.object(handlers, "send_message") as mock_send_message:
                            handlers.handle_research(chat_id="42", args="что дальше?", settings=settings)

        chat_mock.assert_not_called()
        research_mock.assert_called_once()
        self.assertEqual(research_mock.call_args.args[0], "что дальше?")
        self.assertIs(research_mock.call_args.kwargs["settings"], settings)
        self.assertEqual(research_mock.call_args.kwargs["limit"], 4)
        budget = research_mock.call_args.kwargs["budget"]
        self.assertEqual(budget.max_model_calls, 0)
        self.assertFalse(budget.allow_provider_egress)
        self.assertFalse(budget.allow_open_browsing)
        self.assertFalse(budget.allow_vector_retrieval)
        render_mock.assert_called_once_with(payload)
        message = mock_send_message.call_args.args[2]
        self.assertIn("Короткий вывод", message)
        self.assertIn("Источники", message)
        self.assertNotIn("PRM Research", message)
        self.assertNotIn("Privacy:", message)
        self.assertNotIn("model_calls", message)

    def test_handle_research_can_use_approved_local_hybrid_vector_retrieval(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        payload = {"status": "ok", "question": "что дальше?", "privacy": {"model_calls": 0}}

        with patch.dict(
            os.environ,
            {
                "PRM_ARCHIVE_HYBRID_RETRIEVAL": "approved",
                "PRM_ARCHIVE_VECTOR_INDEX_PATH": "/tmp/archive-vector.sqlite",
            },
            clear=False,
        ):
            with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
                with patch.object(handlers, "render_memory_research_answer", return_value="PRM Research"):
                    with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                        with patch.object(handlers, "send_message"):
                            handlers.handle_research(chat_id="42", args="что дальше?", settings=settings)

        budget = research_mock.call_args.kwargs["budget"]
        self.assertTrue(budget.allow_vector_retrieval)
        self.assertEqual(budget.vector_index_path, "/tmp/archive-vector.sqlite")

    def test_telegram_report_strips_technical_metrics_from_local_fallback(self):
        text = "\n".join(
            [
                "PRM Research",
                "Короткий ответ",
                "Есть источники по теме.",
                "Лимиты: tool_calls=4/4; sources<=5; debug=false",
                "Privacy: mode=local-research; model_calls=0; estimated_cost_usd=0; durable_writes=false",
                "Источники",
                "- https://t.me/ai_channel/101",
            ]
        )

        cleaned = handlers._telegram_report_without_technical_metrics(text)

        self.assertIn("PRM Research", cleaned)
        self.assertIn("Есть источники по теме.", cleaned)
        self.assertIn("Источники", cleaned)
        self.assertNotIn("Лимиты", cleaned)
        self.assertNotIn("Privacy:", cleaned)
        self.assertNotIn("model_calls", cleaned)
        self.assertNotIn("tool_calls", cleaned)

    def test_telegram_research_answer_first_contract(self):
        payload = _fake_research_payload("что у меня было про AI transformation?")

        rendered = handlers._render_telegram_research_response(
            payload,
            local_text="PRM Research\nInternal local fallback",
            mode="research",
        )

        for heading in (
            "Короткий вывод",
            "Что найдено",
            "Почему это важно тебе",
            "Что сделать",
            "Где доказательства слабые",
            "Источники",
        ):
            self.assertIn(heading, rendered)
        self.assertIn("https://t.me/ai_channel/101", rendered)
        self.assertIn("недостаточно данных", rendered.casefold())

    def test_telegram_professional_answer_uses_shared_dto_and_cited_findings(self):
        payload = _fake_research_payload()
        payload["professional_answer"] = {
            "schema_version": "professional_answer.v1",
            "answer_status": "supported",
            "short_answer": "Сигнал стоит проверить в проектном контексте.",
            "key_findings": [{"claim": "Нужен regression case.", "citation": "https://t.me/ai_channel/101"}],
            "project_context": {"relevance_label": "no_match"},
            "recommended_action": "Добавить один regression case.",
            "uncertainty": ["current external truth"],
            "citations": [{"source_url": "https://t.me/ai_channel/101"}],
            "external_verification": {"required": False},
        }

        rendered = handlers._render_telegram_research_response(payload, local_text="ignored", mode="research")

        for heading in ("Короткий вывод", "Что найдено", "Почему это важно тебе", "Что сделать", "Чего пока не делать", "Где доказательства слабые", "Источники"):
            self.assertIn(heading, rendered)
        self.assertIn("Нужен regression case.", rendered)
        self.assertIn("https://t.me/ai_channel/101", rendered)
        self.assertNotIn("ignored", rendered)

    def test_telegram_approved_synthesis_precedes_professional_dto(self):
        payload = _fake_research_payload()
        payload["professional_answer"] = {"schema_version": "professional_answer.v1", "short_answer": "DTO fallback"}

        with patch.dict(os.environ, {"PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": "1", "PRM_TELEGRAM_RAG_LLM_SYNTHESIS": "1"}, clear=False):
            with patch.object(handlers, "_synthesize_telegram_rag_answer", return_value="Полированный ответ") as synthesis:
                rendered = handlers._render_telegram_research_response(payload, local_text="ignored", mode="research")

        self.assertEqual(rendered, "Полированный ответ")
        synthesis.assert_called_once_with(payload, mode="research")

    def test_telegram_synthesis_falls_back_when_russian_answer_is_wrong_language(self):
        payload = _fake_research_payload("что в архиве было про evals?")
        payload["professional_answer"] = {"schema_version": "professional_answer.v1", "short_answer": "Безопасный fallback"}

        with patch.dict(os.environ, {"PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": "1", "PRM_TELEGRAM_RAG_LLM_SYNTHESIS": "1"}, clear=False):
            with patch.object(handlers, "_synthesize_telegram_rag_answer", side_effect=RuntimeError("wrong_language_llm_synthesis")):
                rendered = handlers._render_telegram_research_response(payload, local_text="ignored", mode="research")

        self.assertIn("Безопасный fallback", rendered)

    def test_telegram_synthesis_rejects_wrong_language_inside_synthesizer(self):
        payload = _fake_research_payload("что в архиве было про evals?")

        with patch.object(handlers.LLMClient, "complete_with_receipt", return_value=types.SimpleNamespace(text="English only response")):
            with self.assertRaisesRegex(RuntimeError, "wrong_language_llm_synthesis"):
                handlers._synthesize_telegram_rag_answer(payload, mode="research")

    def test_telegram_synthesis_requires_entailment_verdict_before_returning_text(self):
        payload = _fake_research_payload("что в архиве было про evals?")

        with patch.object(handlers.LLMClient, "complete_with_receipt", return_value=types.SimpleNamespace(text="Русский ответ с источником")):
            with patch.object(
                handlers.LLMClient,
                "complete_with_receipt",
                side_effect=(types.SimpleNamespace(text="Русский ответ с источником"), types.SimpleNamespace(text="PASS")),
            ) as completion:
                rendered = handlers._synthesize_telegram_rag_answer(payload, mode="research")

        self.assertIn("Русский ответ", rendered)
        self.assertEqual(completion.call_count, 2)
        self.assertEqual(completion.call_args.kwargs["max_tokens"], 80)
        self.assertEqual(completion.call_args.kwargs["max_attempts"], 1)
        self.assertIn("proposed_answer", completion.call_args.kwargs["prompt"])

    def test_telegram_synthesis_suppresses_usage_for_both_provider_calls(self):
        payload = _fake_research_payload("что в архиве было про evals?")

        with patch.object(handlers, "suppress_usage_recording", side_effect=nullcontext) as suppress:
            with patch.object(
                handlers.LLMClient,
                "complete_with_receipt",
                side_effect=(types.SimpleNamespace(text="Русский ответ с источником"), types.SimpleNamespace(text="PASS")),
            ):
                handlers._synthesize_telegram_rag_answer(payload, mode="research")

        self.assertEqual(suppress.call_count, 2)

    def test_telegram_synthesis_fails_closed_when_entailment_rejects_answer(self):
        payload = _fake_research_payload("что в архиве было про evals?")

        with patch.object(
            handlers.LLMClient,
            "complete_with_receipt",
            side_effect=(types.SimpleNamespace(text="Русский ответ с неподтверждённой деталью"), types.SimpleNamespace(text="FAIL")),
        ):
            with self.assertRaisesRegex(RuntimeError, "unsupported_llm_synthesis"):
                handlers._synthesize_telegram_rag_answer(payload, mode="research")

    def test_telegram_synthesis_fails_closed_when_entailment_response_is_invalid(self):
        payload = _fake_research_payload("что в архиве было про evals?")

        with patch.object(
            handlers.LLMClient,
            "complete_with_receipt",
            side_effect=(types.SimpleNamespace(text="Русский ответ с источником"), types.SimpleNamespace(text="uncertain")),
        ):
            with self.assertRaisesRegex(RuntimeError, "unsupported_llm_synthesis"):
                handlers._synthesize_telegram_rag_answer(payload, mode="research")

    def test_telegram_synthesis_rejects_non_exact_entailment_pass_token(self):
        for verdict in ("pass", " PASS", "PASS\n", "PASS."):
            with self.subTest(verdict=verdict):
                with patch.object(handlers.LLMClient, "complete_with_receipt", return_value=types.SimpleNamespace(text=verdict)):
                    self.assertFalse(handlers._telegram_rag_synthesis_is_entailing("Ответ", {}))

    def test_telegram_synthesis_falls_back_when_entailment_verifier_errors(self):
        payload = _fake_research_payload("что в архиве было про evals?")
        payload["professional_answer"] = {"schema_version": "professional_answer.v1", "short_answer": "Безопасный fallback"}

        with patch.dict(os.environ, {"PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": "1", "PRM_TELEGRAM_RAG_LLM_SYNTHESIS": "1"}, clear=False):
            with patch.object(
                handlers.LLMClient,
                "complete_with_receipt",
                side_effect=(types.SimpleNamespace(text="Русский ответ с источником"), RuntimeError("provider unavailable")),
            ) as synthesis:
                rendered = handlers._render_telegram_research_response(payload, local_text="ignored", mode="research")

        self.assertIn("Безопасный fallback", rendered)
        self.assertEqual(synthesis.call_args.kwargs["max_attempts"], 1)

    def test_telegram_verification_dto_never_enters_synthesis(self):
        payload = _fake_research_payload()
        payload["professional_answer"] = {
            "schema_version": "professional_answer.v1",
            "answer_status": "verification_required",
            "short_answer": "Нужна проверка.",
            "external_verification": {"required": True},
        }

        with patch.dict(os.environ, {"PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": "1", "PRM_TELEGRAM_RAG_LLM_SYNTHESIS": "1"}, clear=False):
            with patch.object(handlers, "_synthesize_telegram_rag_answer") as synthesis:
                rendered = handlers._render_telegram_research_response(payload, local_text="ignored", mode="research")

        synthesis.assert_not_called()
        self.assertIn("Требуется отдельная внешняя проверка", rendered)

    def test_telegram_synthesis_context_bounds_and_redacts_professional_contract(self):
        payload = _fake_research_payload()
        payload["professional_answer"] = {
            "short_answer": "/srv/private " + "a" * 500,
            "key_findings": [{"claim": "model_calls=9\n" + "b" * 400, "citation": "/srv/secret\n" + "c" * 300}],
            "recommended_action": "post_id=1\n" + "d" * 400,
            "uncertainty": ["/srv/private\n" + "e" * 300],
        }

        context = handlers._telegram_rag_synthesis_context(payload, mode="research")
        contract = context["professional_contract"]

        self.assertLessEqual(len(contract["short_answer"]), 420)
        self.assertLessEqual(len(contract["findings"][0]["claim"]), 300)
        self.assertLessEqual(len(contract["findings"][0]["citation"]), 240)
        self.assertLessEqual(len(contract["recommended_action"]), 320)
        self.assertLessEqual(len(contract["uncertainty"][0]), 220)
        self.assertNotIn("/srv/", str(contract))
        self.assertNotIn("model_calls", str(contract))
        self.assertNotIn("post_id", str(contract))

    def test_telegram_synthesis_context_normalizes_all_evidence_urls(self):
        payload = _fake_research_payload()
        payload["linked_source_evidence"] = {"items": [{"normalized_title": "Linked", "normalized_url": "https://example.test/linked", "text_excerpt": "Linked evidence."}]}
        payload["professional_answer"] = {"key_findings": [{"claim": "Professional evidence.", "citation": "https://example.test/professional"}, {"claim": "Unlinked evidence.", "citation": ""}]}

        context = handlers._telegram_rag_synthesis_context(payload, mode="research")

        self.assertEqual(context["archive"]["sources"][0]["source_url"], "https://t.me/ai_channel/101")
        self.assertEqual(context["linked_sources"][0]["source_url"], "https://example.test/linked")
        self.assertEqual(context["professional_contract"]["findings"][0]["source_url"], "https://example.test/professional")
        self.assertEqual(context["professional_contract"]["findings"][1]["source_url"], "")

    def test_telegram_professional_answer_renders_workflow_section(self):
        payload = _fake_research_payload()
        payload["professional_answer"] = {
            "schema_version": "professional_answer.v1", "answer_status": "supported", "short_answer": "Вывод.",
            "key_findings": [], "project_context": {}, "workflow_section": {"validation_step": "Проверить гипотезу на одном кейсе."},
            "recommended_action": None, "uncertainty": [], "citations": [], "external_verification": {"required": False},
        }

        rendered = handlers._render_telegram_research_response(payload, local_text="ignored", mode="research")

        self.assertIn("Рабочий фокус", rendered)
        self.assertIn("Проверить гипотезу на одном кейсе.", rendered)

    def test_telegram_professional_answer_renders_career_workflow_section(self):
        payload = _fake_research_payload()
        payload["professional_answer"] = {
            "schema_version": "professional_answer.v1", "answer_status": "supported", "short_answer": "Вывод.",
            "key_findings": [], "project_context": {},
            "workflow_section": {"recurring_requirement": "Умение строить воспроизводимые evaluation-петли."},
            "recommended_action": None, "uncertainty": [], "citations": [], "external_verification": {"required": False},
        }

        rendered = handlers._render_telegram_research_response(payload, local_text="ignored", mode="research")

        self.assertIn("Рабочий фокус", rendered)
        self.assertIn("Умение строить воспроизводимые evaluation-петли.", rendered)

    def test_telegram_research_hides_internal_receipts(self):
        payload = _fake_research_payload("что у меня было про AI transformation?")
        payload["repo_project_context"] = {
            "status": "matched",
            "summary_ru": "Смотри /srv/private/repo и post_id=123.",
            "source_refs": ["/srv/private/repo/docs/tasks.md"],
        }

        rendered = handlers._render_telegram_research_response(
            payload,
            local_text="PRM Research\nmodel_calls=1\n/srv/private/archive.db\npost_id=123",
            mode="research",
        )

        for forbidden in ("/srv/", "model_calls", "post_id=", "retrieval_mode", "PRM Research"):
            self.assertNotIn(forbidden, rendered)

    def test_telegram_current_fact_answer_first_boundary(self):
        payload = _fake_research_payload("какая текущая цена акций Nvidia сегодня?")
        payload["answer_gate"] = {
            "allow_answer": False,
            "external_verification_required": True,
            "current_claim_allowed": False,
            "reason": "current_external_fact_required",
        }
        payload["unknowns"] = ["external verification before current claims"]

        rendered = handlers._render_telegram_research_response(
            payload,
            local_text="PRM Research\nOld archive context says $100.",
            mode="research",
        )

        self.assertTrue(rendered.startswith("Внешняя проверка нужна"))
        self.assertIn("Короткий вывод", rendered)
        self.assertIn("не подтверждена", rendered)
        self.assertNotIn("Old archive context says", rendered)

    def test_handle_research_can_send_llm_synthesis_after_local_rag(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        payload = _fake_research_payload()
        receipt = types.SimpleNamespace(
            text=(
                "PRM Research: AI transformation\n\n"
                "Короткий вывод\nAI pilots need ROI proof, not adoption theater.\n\n"
                "Что видно по источникам\n- pilots often fail to show measurable ROI.\n\n"
                "Источники\n- https://t.me/ai_channel/101\n\n"
                "Границы\nЛокальный архив, без live web."
            ),
            estimated_cost_usd=0.00004,
        )

        with patch.dict(
            os.environ,
            {"PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": "1", "PRM_TELEGRAM_RAG_LLM_SYNTHESIS": "1"},
            clear=False,
        ):
            with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
                with patch.object(handlers, "render_memory_research_answer", return_value="LOCAL RAG FALLBACK") as render_mock:
                    with patch.object(
                        handlers.LLMClient,
                        "complete_with_receipt",
                        side_effect=(receipt, types.SimpleNamespace(text="PASS")),
                    ) as llm_mock:
                        with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                            with patch.object(handlers, "send_message") as mock_send_message:
                                handlers.handle_research(
                                    chat_id="42",
                                    args="что у меня было про AI transformation?",
                                    settings=settings,
                                )

        research_mock.assert_called_once()
        render_mock.assert_called_once_with(payload)
        self.assertEqual(llm_mock.call_count, 2)
        synthesis_prompt = llm_mock.call_args_list[0].kwargs["prompt"]
        verifier_prompt = llm_mock.call_args_list[1].kwargs["prompt"]
        self.assertIn("AI transformation pilots", synthesis_prompt)
        self.assertIn("polished, ready-to-read Telegram report", synthesis_prompt)
        self.assertIn("Group related sources by topic", synthesis_prompt)
        self.assertIn("Use a clean visual layout", synthesis_prompt)
        self.assertIn("Do not show technical metrics", synthesis_prompt)
        self.assertIn("hard source eligibility boundary", synthesis_prompt)
        self.assertIn("Every source-derived factual assertion", synthesis_prompt)
        self.assertIn("close paraphrase of one supplied snippet", synthesis_prompt)
        self.assertIn("only an explicitly labelled practical suggestion", synthesis_prompt)
        self.assertIn("Return exactly one word: PASS or FAIL", verifier_prompt)
        self.assertIn("lacks a supplied source_url", verifier_prompt)
        message = mock_send_message.call_args.args[2]
        self.assertIn("PRM Research", message)
        self.assertIn("AI pilots need ROI proof", message)
        self.assertIn("Что видно по источникам", message)
        self.assertIn("Границы", message)
        self.assertNotIn("Privacy:", message)
        self.assertNotIn("model_calls", message)
        self.assertNotIn("estimated_cost", message)
        self.assertNotIn("bounded_telegram_snippet_provider_egress", message)

    def test_telegram_rag_synthesis_context_carries_strict_time_window(self):
        payload = _fake_research_payload("Что было интересного по моделям за последние две недели?")
        payload["time_window"] = {
            "requested": True,
            "strict": True,
            "label": "2026-07-28–2026-08-11",
            "date_from": "2026-07-28T00:00:00Z",
            "date_to": "2026-08-12T00:00:00Z",
            "source": "последние две недели",
        }

        context = handlers._telegram_rag_synthesis_context(payload, mode="research")

        self.assertTrue(context["time_window"]["requested"])
        self.assertTrue(context["time_window"]["strict"])
        self.assertEqual(context["time_window"]["label"], "2026-07-28–2026-08-11")
        self.assertEqual(context["archive"]["sources"][0]["date"], "2026-08-01")

    def test_handle_research_uses_volatile_dialog_context_for_short_followups(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        handlers._RESEARCH_DIALOG_STATE.clear()
        payload = {"status": "ok", "question": "placeholder", "privacy": {"model_calls": 0}}

        with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
            with patch.object(handlers, "render_memory_research_answer", return_value="PRM Research") as render_mock:
                with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                    with patch.object(handlers, "send_message"):
                        handlers.handle_research(chat_id="42", args="AI transformation компаний: где эффект?", settings=settings)
                        handlers.handle_research(chat_id="42", args="а почему?", settings=settings)

        self.assertEqual(research_mock.call_count, 2)
        second_question = research_mock.call_args_list[1].args[0]
        self.assertIn("AI transformation компаний", second_question)
        self.assertIn("Уточнение: а почему?", second_question)
        second_payload = render_mock.call_args_list[1].args[0]
        self.assertEqual(second_payload["question"], "а почему?")
        self.assertTrue(second_payload["dialog_context"]["used"])
        self.assertIn("AI transformation компаний", second_payload["dialog_context"]["previous_question"])

    def test_handle_research_brief_uses_local_memory_research_without_pi_chat(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        payload = {"status": "ok", "question": "brief", "privacy": {"model_calls": 0}}

        with patch.object(handlers, "answer_pi_chat") as chat_mock:
            with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
                with patch.object(handlers, "render_memory_research_brief", return_value="PRM редакторский бриф\nmodel_calls=0\nPrivacy: mode=local-research") as render_mock:
                    with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                        with patch.object(handlers, "send_message") as mock_send_message:
                            handlers.handle_research_brief(
                                chat_id="42",
                                args="собери тезисы про AI transformation",
                                settings=settings,
                            )

        chat_mock.assert_not_called()
        research_mock.assert_called_once()
        budget = research_mock.call_args.kwargs["budget"]
        self.assertEqual(budget.max_model_calls, 0)
        self.assertFalse(budget.allow_provider_egress)
        self.assertFalse(budget.allow_open_browsing)
        self.assertFalse(budget.allow_vector_retrieval)
        render_mock.assert_called_once()
        message = mock_send_message.call_args.args[2]
        self.assertIn("PRM редакторский бриф", message)
        self.assertNotIn("model_calls=0", message)
        self.assertNotIn("Privacy:", message)

    def test_prm_safe_command_allowlist_allows_research(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        payload = {"status": "ok", "question": "what changed?"}

        with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
            with patch.object(handlers, "answer_pi_chat") as chat_mock:
                with patch.object(handlers, "render_memory_research_answer", return_value="PRM Research\nlocal-only"):
                    with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                        with patch.object(handlers, "send_message") as mock_send_message:
                            handlers.dispatch_command(
                                chat_id="42",
                                text="/research what changed?",
                                settings=settings,
                                runtime_mode=handlers.BOT_RUNTIME_PRM_ASSISTANT,
                            )

        chat_mock.assert_not_called()
        research_mock.assert_called_once()
        message = mock_send_message.call_args.args[2]
        self.assertIn("PRM Research", message)

    def test_prm_safe_command_allowlist_allows_brief(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        payload = {"status": "ok", "question": "brief"}

        with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
            with patch.object(handlers, "answer_pi_chat") as chat_mock:
                with patch.object(handlers, "render_memory_research_brief", return_value="PRM редакторский бриф"):
                    with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                        with patch.object(handlers, "send_message") as mock_send_message:
                            handlers.dispatch_command(
                                chat_id="42",
                                text="/brief AI transformation тезисы",
                                settings=settings,
                                runtime_mode=handlers.BOT_RUNTIME_PRM_ASSISTANT,
                            )

        chat_mock.assert_not_called()
        research_mock.assert_called_once()
        self.assertIn("PRM редакторский бриф", mock_send_message.call_args.args[2])

    def test_handle_auto_routes_editorial_plain_text_to_brief_without_llm(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        payload = {"status": "ok", "question": "brief"}

        with patch.dict(os.environ, {"PRM_TELEGRAM_AUTO_LLM_ROUTER": "", "PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": ""}, clear=False):
            with patch.object(handlers.LLMClient, "complete_json") as llm_mock:
                with patch.object(handlers, "answer_pi_chat") as chat_mock:
                    with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
                        with patch.object(handlers, "render_memory_research_brief", return_value="PRM редакторский бриф"):
                            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                                with patch.object(handlers, "send_message") as mock_send_message:
                                    handlers.handle_auto(
                                        chat_id="42",
                                        args="собери опорные тезисы для поста про AI transformation",
                                        settings=settings,
                                    )

        llm_mock.assert_not_called()
        chat_mock.assert_not_called()
        research_mock.assert_called_once()
        self.assertIn("PRM редакторский бриф", mock_send_message.call_args.args[2])

    def test_handle_auto_routes_archive_plain_text_to_research_without_llm(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        payload = {"status": "ok", "question": "research"}

        with patch.dict(os.environ, {"PRM_TELEGRAM_AUTO_LLM_ROUTER": "", "PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": ""}, clear=False):
            with patch.object(handlers.LLMClient, "complete_json") as llm_mock:
                with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
                    with patch.object(handlers, "render_memory_research_answer", return_value="PRM Research"):
                        with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                            with patch.object(handlers, "send_message") as mock_send_message:
                                handlers.handle_auto(
                                    chat_id="42",
                                    args="что у меня было про AI transformation компаний?",
                                    settings=settings,
                                )

        llm_mock.assert_not_called()
        research_mock.assert_called_once()
        self.assertIn("PRM Research", mock_send_message.call_args.args[2])

    def test_handle_auto_uses_llm_router_when_explicitly_enabled(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        payload = {"status": "ok", "question": "brief"}

        with patch.dict(
            os.environ,
            {"PRM_TELEGRAM_AUTO_LLM_ROUTER": "1", "PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": "1"},
            clear=False,
        ):
            with patch.object(
                handlers.LLMClient,
                "complete_json",
                return_value={
                    "mode": "brief",
                    "confidence": 0.91,
                    "reason": "editor brief requested",
                    "retrieval_query": "AI transformation company outcomes",
                },
            ) as llm_mock:
                with patch.object(handlers, "answer_pi_chat") as chat_mock:
                    with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
                        with patch.object(handlers, "render_memory_research_brief", return_value="PRM редакторский бриф"):
                            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                                with patch.object(handlers, "send_message") as mock_send_message:
                                    handlers.handle_auto(chat_id="42", args="сделай редакторский бриф", settings=settings)

        llm_mock.assert_called_once()
        chat_mock.assert_not_called()
        research_mock.assert_called_once()
        self.assertEqual(research_mock.call_args.kwargs["archive_query"], "AI transformation company outcomes")
        self.assertIn("PRM редакторский бриф", mock_send_message.call_args.args[2])

    def test_handle_auto_passes_explicit_git_project_to_research(self):
        settings = Settings(db_path=":memory:", llm_api_key="", model_provider="anthropic", telegram_session_path="")
        payload = {"status": "ok", "question": "research"}

        with patch.dict(os.environ, {"PRM_TELEGRAM_AUTO_LLM_ROUTER": "", "PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": ""}, clear=False):
            with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
                with patch.object(handlers, "render_memory_research_answer", return_value="PRM Research"):
                    with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                        with patch.object(handlers, "send_message"):
                            handlers.handle_auto(
                                chat_id="42",
                                args="Сделай deep research по agent evals для проекта gdev-agent",
                                settings=settings,
                            )

        self.assertEqual(research_mock.call_args.kwargs["project_name"], "gdev-agent")

    def test_telegram_project_relation_explains_explicit_project_match(self):
        relation = handlers._telegram_project_relation(
            {
                "project_name": "gdev-agent",
                "relevance_label": "weak_watch",
                "matched_terms": ["eval", "agent runtime"],
            }
        )

        self.assertIn("gdev-agent", relation)
        self.assertIn("eval", relation)
        self.assertIn("проектное действие пока не доказано", relation)

    def test_handle_auto_rejects_llm_chat_for_archive_question(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        payload = {"status": "ok", "question": "research"}

        with patch.dict(
            os.environ,
            {"PRM_TELEGRAM_AUTO_LLM_ROUTER": "1", "PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": "1"},
            clear=False,
        ):
            with patch.object(
                handlers.LLMClient,
                "complete_json",
                return_value={"mode": "chat", "confidence": 0.96, "reason": "bad route"},
            ) as llm_mock:
                with patch.object(handlers, "answer_pi_chat") as chat_mock:
                    with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
                        with patch.object(handlers, "render_memory_research_answer", return_value="PRM Research"):
                            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                                with patch.object(handlers, "send_message") as mock_send_message:
                                    handlers.handle_auto(
                                        chat_id="42",
                                        args="что у меня было в постах про AI transformation компаний?",
                                        settings=settings,
                                    )

        llm_mock.assert_called_once()
        chat_mock.assert_not_called()
        research_mock.assert_called_once()
        self.assertIn("PRM Research", mock_send_message.call_args.args[2])

    def test_handle_auto_keeps_generation_local_without_auto_llm_router_flag(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        payload = {"status": "ok", "question": "research"}

        with patch.dict(
            os.environ,
            {"PRM_TELEGRAM_AUTO_LLM_ROUTER": "", "PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": "1"},
            clear=False,
        ):
            with patch.object(handlers.LLMClient, "complete_json") as llm_mock:
                with patch.object(handlers, "answer_pi_chat") as chat_mock:
                    with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
                        with patch.object(handlers, "render_memory_research_answer", return_value="PRM Research"):
                            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                                with patch.object(handlers, "send_message") as mock_send_message:
                                    handlers.handle_auto(
                                        chat_id="42",
                                        args="перепиши этот текст проще",
                                        settings=settings,
                                    )

        llm_mock.assert_not_called()
        chat_mock.assert_not_called()
        research_mock.assert_called_once()
        self.assertIn("PRM Research", mock_send_message.call_args.args[2])

    def test_handle_auto_routes_to_chat_when_llm_router_selects_chat(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        with patch.dict(
            os.environ,
            {"PRM_TELEGRAM_AUTO_LLM_ROUTER": "1", "PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": "1"},
            clear=False,
        ):
            with patch.object(
                handlers.LLMClient,
                "complete_json",
                return_value={"mode": "chat", "confidence": 0.88, "reason": "rewrite requested"},
            ) as llm_mock:
                with patch.object(handlers, "answer_pi_chat", return_value=_fake_prm_chat_payload()) as chat_mock:
                    with patch.object(handlers, "answer_memory_research") as research_mock:
                        with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                            with patch.object(handlers, "send_message") as mock_send_message:
                                handlers.handle_auto(
                                    chat_id="42",
                                    args="перепиши этот текст проще",
                                    settings=settings,
                                )

        llm_mock.assert_called_once()
        chat_mock.assert_called_once()
        research_mock.assert_not_called()
        self.assertIn("PRM Chat", mock_send_message.call_args.args[2])

    def test_handle_auto_keeps_current_fact_boundary_local_even_with_llm_router_enabled(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        payload = {"status": "needs_external_verification", "question": "research"}

        with patch.dict(
            os.environ,
            {"PRM_TELEGRAM_AUTO_LLM_ROUTER": "1", "PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": "1"},
            clear=False,
        ):
            with patch.object(handlers.LLMClient, "complete_json") as llm_mock:
                with patch.object(handlers, "answer_pi_chat") as chat_mock:
                    with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
                        with patch.object(handlers, "render_memory_research_answer", return_value="PRM Research"):
                            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                                with patch.object(handlers, "send_message") as mock_send_message:
                                    handlers.handle_auto(
                                        chat_id="42",
                                        args="какая текущая цена акций Nvidia сегодня?",
                                        settings=settings,
                                    )

        llm_mock.assert_not_called()
        chat_mock.assert_not_called()
        research_mock.assert_called_once()
        self.assertIn("PRM Research", mock_send_message.call_args.args[2])

    def test_handle_auto_voice_passes_one_ephemeral_context_to_retrieval(self):
        settings = Settings(db_path=":memory:", llm_api_key="", model_provider="anthropic", telegram_session_path="")
        payload = {"status": "ok", "question": "research"}

        with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
            with patch.object(handlers, "render_memory_research_answer", return_value="PRM Research") as render_mock:
                with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                    with patch.object(handlers, "send_message"):
                        handlers.handle_auto_voice(chat_id="42", args="что было в архиве про evals?", settings=settings)

        context = render_mock.call_args.args[0]["operator_context"]
        assert context["input_kind"] == "voice_transcript"
        assert context["primary_workflow"] == "archive_research"
        assert context["chat_id_hash"] != "42"
        assert research_mock.call_args.kwargs["operator_context"]["interaction_id"] == context["interaction_id"]

    def test_handle_auto_falls_back_local_when_llm_router_errors(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        payload = {"status": "ok", "question": "research"}

        with patch.dict(
            os.environ,
            {"PRM_TELEGRAM_AUTO_LLM_ROUTER": "1", "PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS": "1"},
            clear=False,
        ):
            with patch.object(handlers.LLMClient, "complete_json", side_effect=RuntimeError("no key")) as llm_mock:
                with patch.object(handlers, "answer_pi_chat") as chat_mock:
                    with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
                        with patch.object(handlers, "render_memory_research_answer", return_value="PRM Research"):
                            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                                with patch.object(handlers, "send_message") as mock_send_message:
                                    handlers.handle_auto(
                                        chat_id="42",
                                        args="перепиши этот текст проще",
                                        settings=settings,
                                    )

        llm_mock.assert_called_once()
        chat_mock.assert_not_called()
        research_mock.assert_called_once()
        self.assertIn("PRM Research", mock_send_message.call_args.args[2])

    def test_handle_auto_short_followup_keeps_previous_brief_mode(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        payload = {"status": "ok", "question": "brief"}

        with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
            with patch.object(handlers, "render_memory_research_brief", return_value="PRM редакторский бриф") as brief_render:
                with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                    with patch.object(handlers, "send_message"):
                        handlers.handle_auto(chat_id="42", args="собери тезисы про AI transformation", settings=settings)
                        handlers.handle_auto(chat_id="42", args="а почему?", settings=settings)

        self.assertEqual(research_mock.call_count, 2)
        self.assertEqual(brief_render.call_count, 2)
        second_question = research_mock.call_args_list[1].args[0]
        self.assertIn("собери тезисы про AI transformation", second_question)
        self.assertIn("Уточнение: а почему?", second_question)

    def test_auto_context_session_changes_for_new_topic(self):
        settings = Settings(db_path=":memory:", llm_api_key="", model_provider="anthropic", telegram_session_path="")
        payload = {"status": "ok", "question": "research"}

        with patch.object(handlers, "answer_memory_research", return_value=payload) as research_mock:
            with patch.object(handlers, "render_memory_research_answer", return_value="PRM Research"):
                with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                    with patch.object(handlers, "send_message"):
                        handlers.handle_auto(chat_id="42", args="что было про evals?", settings=settings)
                        handlers.handle_auto(chat_id="42", args="а почему?", settings=settings)
                        handlers.handle_auto(chat_id="42", args="что было про RAG?", settings=settings)

        sessions = [call.kwargs["operator_context"]["session_id"] for call in research_mock.call_args_list]
        self.assertEqual(sessions[0], sessions[1])
        self.assertNotEqual(sessions[1], sessions[2])

    def test_handle_ask_delegates_to_pi_chat_not_raw_telegram_answer(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        with patch.object(handlers, "handle_chat") as mock_handle_chat:
            handlers.handle_ask(chat_id="42", args="что важно?", settings=settings)

        mock_handle_chat.assert_called_once_with("42", "что важно?", settings)

    def test_handle_operator_message_routes_chat_intent(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        with patch.object(
            handlers,
            "classify_operator_message",
            return_value={"intent": "chat", "confidence": 0.8, "reason": "question"},
        ) as classify_mock, patch.object(handlers, "handle_chat") as chat_mock:
            handlers.handle_operator_message(chat_id="42", args="что делать с workbook?", settings=settings)

        classify_mock.assert_called_once_with("что делать с workbook?", input_kind="text")
        chat_mock.assert_called_once_with("42", "что делать с workbook?", settings)

    def test_handle_operator_message_routes_voice_feedback_intent(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        with patch.object(
            handlers,
            "classify_operator_message",
            return_value={"intent": "feedback", "confidence": 0.9, "reason": "operator feedback"},
        ) as classify_mock, patch.object(handlers, "_handle_feedback_intake") as feedback_mock:
            handlers.handle_voice_message(chat_id="42", args="полезно, но слишком shallow", settings=settings)

        classify_mock.assert_called_once_with("полезно, но слишком shallow", input_kind="voice_transcript")
        feedback_mock.assert_called_once_with(
            "42",
            "полезно, но слишком shallow",
            settings,
            input_kind="voice_transcript",
        )

    def test_handle_operator_message_routes_reminder_intent(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        with patch.object(
            handlers,
            "classify_operator_message",
            return_value={"intent": "reminder", "confidence": 0.9, "reason": "reminder"},
        ), patch.object(handlers, "handle_remind") as remind_mock:
            handlers.handle_operator_message(chat_id="42", args="напомни завтра дать feedback", settings=settings)

        remind_mock.assert_called_once_with("42", "напомни завтра дать feedback", settings)

    def test_handle_weekly_formats_read_only_pi_summary(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        pi_result = {
            "status": "ok",
            "tool_name": "get_weekly_summary",
            "read_only": True,
            "evidence_status": "available",
            "evidence": {"artifact_paths": {"html": "/tmp/2026-W28.visual.html"}},
            "result": {
                "status": "ok",
                "week_label": "2026-W28",
                "decision_brief": [
                    {"title": "Study eval gates", "summary": "Eval gates matter this week."}
                ],
                "strong_signals": [
                    {"claim": "Eval gates are becoming release infrastructure."}
                ],
                "actions": [
                    {"title": "Try a tiny eval gate", "next_step": "Add one regression guard."}
                ],
                "project_actions": [],
                "artifact_paths": {"html": "/tmp/2026-W28.visual.html", "json": "/tmp/2026-W28.visual.json"},
                "message": "Workbook summary loaded.",
            },
            "message": "Workbook summary loaded.",
        }

        with patch.object(handlers, "_pi_tool", return_value=pi_result) as mock_pi_tool:
            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as mock_send_message:
                    handlers.handle_weekly(chat_id="42", args="2026-W28", settings=settings)

        mock_pi_tool.assert_called_once_with(settings, "get_weekly_summary", {"week_label": "2026-W28"})
        message = mock_send_message.call_args.args[2]
        self.assertIn("Hermes weekly 2026-W28", message)
        self.assertIn("Eval gates are becoming release infrastructure", message)
        self.assertIn("/tmp/2026-W28.visual.html", message)

    def test_handle_actions_formats_status_projection(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        pi_result = {
            "status": "ok",
            "tool_name": "get_action_statuses",
            "read_only": True,
            "evidence_status": "insufficient",
            "evidence": {},
            "result": {
                "status": "ok",
                "week_label": "2026-W28",
                "items": [
                    {
                        "action_id": "action-1",
                        "title": "Try eval gate",
                        "status": "unknown",
                        "follow_up_hint": "Report tried/useful or reject.",
                        "outcome_policy": "Do not count without feedback.",
                    }
                ],
                "counts": {"unknown": 1, "wrong_priority": 0, "not_interested": 0},
            },
            "message": "Action statuses loaded.",
        }

        with patch.object(handlers, "_pi_tool", return_value=pi_result) as mock_pi_tool:
            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as mock_send_message:
                    handlers.handle_actions(chat_id="42", args="2026-W28", settings=settings)

        mock_pi_tool.assert_called_once_with(settings, "get_action_statuses", {"week_label": "2026-W28"})
        message = mock_send_message.call_args.args[2]
        self.assertIn("Hermes actions 2026-W28", message)
        self.assertIn("[unknown] Try eval gate", message)
        self.assertIn("Status counts: unknown=1", message)
        self.assertNotIn("not_interested=0", message)

    def test_handle_explain_uses_curated_search_tool(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        pi_result = {
            "status": "ok",
            "tool_name": "search_intelligence_items",
            "read_only": True,
            "evidence_status": "available",
            "evidence": {"source_refs": ["https://t.me/ai_lab/101"], "atom_ids": [101]},
            "result": {
                "status": "ok",
                "items": [
                    {
                        "item_type": "claim_card",
                        "title": "Eval gates",
                        "summary": "A curated claim card summary.",
                        "source_refs": ["https://t.me/ai_lab/101"],
                        "atom_ids": [101],
                    }
                ],
            },
            "message": "Curated intelligence items matched deterministic search.",
        }

        with patch.object(handlers, "_pi_tool", return_value=pi_result) as mock_pi_tool:
            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as mock_send_message:
                    handlers.handle_explain(chat_id="42", args="2026-W28 eval gates", settings=settings)

        mock_pi_tool.assert_called_once_with(
            settings,
            "search_intelligence_items",
            {"query": "eval gates", "filters": {"week_label": "2026-W28"}, "limit": 3},
        )
        message = mock_send_message.call_args.args[2]
        self.assertIn("Hermes explain: eval gates", message)
        self.assertIn("claim_card: Eval gates", message)
        self.assertIn("https://t.me/ai_lab/101", message)

    def test_handle_mvp_missing_status_returns_clear_fallback(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        pi_result = {
            "status": "missing",
            "tool_name": "get_mvp_radar_status",
            "read_only": True,
            "evidence_status": "insufficient",
            "evidence": {},
            "result": {
                "status": "missing",
                "week_label": "2026-W28",
                "message": "MVP Radar result is missing.",
            },
            "message": "MVP Radar result is missing.",
        }

        with patch.object(handlers, "_pi_tool", return_value=pi_result):
            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as mock_send_message:
                    handlers.handle_mvp(chat_id="42", args="2026-W28", settings=settings)

        message = mock_send_message.call_args.args[2]
        self.assertIn("MVP Radar status is missing", message)
        self.assertIn("MVP Radar result is missing", message)

    def test_handle_strategy_formats_structured_reviewer_summary(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        pi_result = {
            "status": "ok",
            "tool_name": "get_strategy_reviewer_notes",
            "read_only": True,
            "evidence_status": "insufficient",
            "evidence": {},
            "result": {
                "status": "ok",
                "week_label": "2026-W28",
                "suggestions": {
                    "keep": ["Keep useful project actions."],
                    "change": ["Increase source-depth checks."],
                    "demote": ["Demote wrong-priority topics."],
                    "test_next_week": ["Turn missed posts into eval examples."],
                },
                "memory_only_updates": ["Confirmed feedback is stored."],
                "approval_required": [
                    {"change_type": "config", "reason": "Trust thresholds require approval."}
                ],
                "codex_tasks": [
                    {
                        "title": "Add source-depth regression",
                        "rationale": "Operator feedback marked analysis too shallow.",
                        "files": ["src/output/ai_visual_report.py", "tests/test_ai_visual_report.py"],
                        "acceptance_criteria": ["No claim is upgraded without source URLs."],
                        "verification_commands": ["python3 -m unittest tests.test_ai_visual_report"],
                    }
                ],
                "risks": ["Do not apply code/config changes automatically."],
                "mutation_policy": {"source_code": "do_not_modify", "profile": "do_not_modify"},
                "message": "Strategy Reviewer notes loaded.",
            },
            "message": "Strategy Reviewer notes loaded.",
        }

        with patch.object(handlers, "_pi_tool", return_value=pi_result) as mock_pi_tool:
            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as mock_send_message:
                    handlers.handle_strategy(chat_id="42", args="2026-W28", settings=settings)

        mock_pi_tool.assert_called_once_with(settings, "get_strategy_reviewer_notes", {"week_label": "2026-W28"})
        message = mock_send_message.call_args.args[2]
        for expected in [
            "Keep",
            "Change",
            "Demote",
            "Test next week",
            "Memory-only updates",
            "Approval required",
            "Codex tasks",
            "Add source-depth regression",
            "files: src/output/ai_visual_report.py",
            "acceptance: No claim is upgraded without source URLs.",
            "verify: python3 -m unittest tests.test_ai_visual_report",
            "Risks",
            "Mutation policy",
            "source_code=do_not_modify",
        ]:
            self.assertIn(expected, message)

    def test_handle_codex_only_prepares_prompt(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

        with patch.object(handlers, "_pi_tool") as mock_pi_tool:
            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as mock_send_message:
                    handlers.handle_codex(chat_id="42", args="HPI-4 test prompt", settings=settings)

        mock_pi_tool.assert_not_called()
        message = mock_send_message.call_args.args[2]
        self.assertIn("Codex prompt draft", message)
        self.assertIn("HPI-4 test prompt", message)
        self.assertIn("No Codex command has been executed.", message)

    def test_handle_remind_creates_pending_reminder(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                run_migrations()
            settings = Settings(
                db_path=db_path,
                llm_api_key="",
                model_provider="anthropic",
                telegram_session_path="",
            )

            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as mock_send_message:
                    handlers.handle_remind(
                        chat_id="42",
                        args="завтра 18:00 дать feedback по Workbook",
                        settings=settings,
                    )

            message = mock_send_message.call_args.args[2]
            self.assertIn("Напоминание добавлено #1", message)
            self.assertIn("Asia/Tbilisi", message)
            self.assertIn("сделал / не сделал", message)
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    "SELECT text, reminder_type, status FROM operator_reminders WHERE id = 1"
                ).fetchone()
            self.assertEqual(row["text"], "дать feedback по Workbook")
            self.assertEqual(row["reminder_type"], "feedback")
            self.assertEqual(row["status"], "pending")
        finally:
            os.unlink(db_path)

    def test_handle_reminders_lists_pending_reminders(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                run_migrations()
            settings = Settings(
                db_path=db_path,
                llm_api_key="",
                model_provider="anthropic",
                telegram_session_path="",
            )
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO operator_reminders (
                        due_at, text, reminder_type, status, created_at, recorded_by
                    )
                    VALUES (?, ?, ?, 'pending', ?, ?)
                    """,
                    ("2026-07-08T10:00:00Z", "прочитать Workbook", "read_watch", "2026-07-08T00:00:00Z", "test"),
                )
                connection.commit()

            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as mock_send_message:
                    handlers.handle_reminders(chat_id="42", args="", settings=settings)

            message = mock_send_message.call_args.args[2]
            self.assertIn("Активные напоминания", message)
            self.assertIn("Asia/Tbilisi", message)
            self.assertIn("прочитать Workbook", message)
        finally:
            os.unlink(db_path)

    def test_handle_feedback_drafts_summary_without_memory_write_until_confirmed(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                run_migrations()
            settings = Settings(
                db_path=db_path,
                llm_api_key="",
                model_provider="anthropic",
                telegram_session_path="",
            )

            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as mock_send_message:
                    handlers.handle_feedback(
                        chat_id="42",
                        args="2026-W28 Useful target=claim-cards. Config: adjust lookback manually.",
                        settings=settings,
                    )

            draft_message = mock_send_message.call_args.args[2]
            self.assertIn("AI workbook feedback draft #1", draft_message)
            self.assertIn("No memory has been written yet.", draft_message)

            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                self.assertEqual(fetch_ai_report_feedback(connection, week_label="2026-W28"), [])
                intakes = fetch_ai_report_feedback_intake(connection, status="pending", limit=10)
                self.assertEqual(len(intakes), 1)
                self.assertEqual(intakes[0]["input_kind"], "text")

            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as mock_confirm_message:
                    handlers.handle_feedback_confirm(chat_id="42", args="1", settings=settings)

            confirm_message = mock_confirm_message.call_args.args[2]
            self.assertIn("Confirmed feedback draft #1", confirm_message)
            self.assertIn("memory_writes=1", confirm_message)

            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                events = fetch_ai_report_feedback(connection, week_label="2026-W28")
                intakes = fetch_ai_report_feedback_intake(connection, intake_id=1, limit=1)
            self.assertEqual([event["feedback_type"] for event in events], ["useful"])
            self.assertEqual(intakes[0]["status"], "confirmed")
        finally:
            os.unlink(db_path)

    def test_handle_feedback_voice_accepts_transcript_text(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                run_migrations()
            settings = Settings(
                db_path=db_path,
                llm_api_key="",
                model_provider="anthropic",
                telegram_session_path="",
            )

            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as mock_send_message:
                    handlers.handle_feedback_voice(
                        chat_id="42",
                        args="2026-W28 Too shallow target=eval-gates.",
                        settings=settings,
                    )

            self.assertIn("AI workbook feedback draft #1", mock_send_message.call_args.args[2])
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                intakes = fetch_ai_report_feedback_intake(connection, status="pending", limit=10)
            self.assertEqual(intakes[0]["input_kind"], "voice_transcript")
            self.assertEqual(intakes[0]["transcript_text"], "Too shallow target=eval-gates.")
        finally:
            os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()
