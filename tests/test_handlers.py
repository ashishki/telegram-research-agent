import os
import sqlite3
import sys
import tempfile
import types
import unittest
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


class TestHandlers(unittest.TestCase):
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
        for command in ["/weekly", "/actions", "/explain", "/projects", "/mvp", "/strategy", "/codex", "/chat", "/hermes"]:
            self.assertIn(command, handlers.HANDLERS)

    def test_handle_chat_uses_bounded_pi_chat(self):
        settings = Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )
        pi_chat_result = {
            "status": "ok",
            "answer": "Hermes answer from curated PI tools.",
            "tool_calls": [{"name": "search_intelligence_items", "arguments": {"query": "eval"}}],
            "tool_results": [],
            "evidence": {"source_refs": ["https://t.me/source/1"]},
            "message": "ok",
        }

        with patch.object(handlers, "answer_pi_chat", return_value=pi_chat_result) as mock_chat:
            with patch.object(handlers, "_get_bot_token", return_value="bot-token"):
                with patch.object(handlers, "send_message") as mock_send_message:
                    handlers.handle_chat(chat_id="42", args="что с eval gates?", settings=settings)

        mock_chat.assert_called_once_with("что с eval gates?", settings=settings)
        self.assertEqual(mock_send_message.call_count, 1)
        self.assertEqual(mock_send_message.call_args_list[0].args[2], "Hermes answer from curated PI tools.")

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
