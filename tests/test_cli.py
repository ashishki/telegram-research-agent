from contextlib import redirect_stdout
from io import StringIO
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from main import (
    BOT_RUNTIME_PRM_ASSISTANT,
    build_parser,
    handle_memory_chat,
    handle_memory_ask,
    handle_memory_research,
    handle_prm_assistant,
    handle_report_v2_rollout_gate,
    handle_weekly_intelligence_v2,
)


def _fake_prm_chat_payload() -> dict:
    return {
        "status": "ok",
        "answer": "Grounded PRM answer.",
        "evidence": {
            "source_refs": ["https://t.me/source/1"],
            "atom_ids": [101],
            "thread_slugs": [],
            "artifact_paths": {},
        },
        "answer_contract": {
            "source_links": ["https://t.me/source/1"],
            "archive_support": {"status": "available", "source_count": 1},
            "unknowns": ["market freshness"],
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
    }


class TestCli(unittest.TestCase):
    def test_bootstrap_accepts_days_window(self):
        args = build_parser().parse_args(["bootstrap", "--days", "84"])

        self.assertEqual(args.days, 84)

    def test_bootstrap_rejects_non_positive_days_window(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["bootstrap", "--days", "0"])

    def test_weekly_intelligence_v2_parser_preserves_week_compatibility(self):
        args = build_parser().parse_args(
            [
                "weekly-intelligence-v2",
                "--week",
                "2026-W28",
                "--run-id",
                "historical-run",
                "--disable-radar",
            ]
        )

        self.assertEqual(args.week, "2026-W28")
        self.assertEqual(args.run_id, "historical-run")
        self.assertTrue(args.disable_radar)
        self.assertIs(args.handler, handle_weekly_intelligence_v2)

    def test_weekly_intelligence_v2_exit_codes_are_terminal_status_aware(self):
        args = build_parser().parse_args(["weekly-intelligence-v2"])
        base = {
            "run_id": "run",
            "manifest_path": "/tmp/run/manifest.json",
            "partial": False,
            "reporting_week": "2026-W28",
            "analysis_period_start": "2026-07-06T00:00:00Z",
            "analysis_period_end": "2026-07-13T00:00:00Z",
            "weekly_brief_html_path": None,
            "atlas_html_path": None,
            "radar_json_path": None,
            "delivered_message_ids": (),
        }
        for status, expected in (("complete", 0), ("partial", 2), ("failed", 1)):
            with self.subTest(status=status), patch("main.load_settings"), patch(
                "main.run_migrations"
            ), patch(
                "output.weekly_intelligence_orchestrator.run_weekly_intelligence_v2",
                return_value=SimpleNamespace(
                    **{
                        **base,
                        "run_status": status,
                        "partial": status == "partial",
                    }
                ),
            ):
                self.assertEqual(handle_weekly_intelligence_v2(args), expected)

    def test_report_v2_rollout_gate_parser_is_explicit(self):
        args = build_parser().parse_args(
            [
                "report-v2-rollout-gate",
                "--week",
                "2026-W28",
                "--output-root",
                "/tmp/output",
                "--json",
            ]
        )

        self.assertEqual(args.week, "2026-W28")
        self.assertEqual(args.output_root, "/tmp/output")
        self.assertTrue(args.json)
        self.assertIs(args.handler, handle_report_v2_rollout_gate)

    def test_report_v2_rollout_gate_exit_codes_blocked_start(self):
        args = build_parser().parse_args(["report-v2-rollout-gate"])
        receipt = {
            "dogfood_start_status": "blocked",
            "blocking_gates": ["period"],
            "gates": [
                {
                    "name": "period",
                    "status": "blocked",
                    "summary": "missing run",
                    "blocks_dogfood": True,
                }
            ],
            "operator_commands": {
                "v2_candidate_command": "weekly-intelligence-v2",
                "start_gate_command": "report-v2-rollout-gate",
            },
            "dogfood_week_1": {"blocked_evidence": ["missing run"]},
        }
        with patch("main.load_settings"), patch("main.run_migrations"), patch(
            "output.report_v2_rollout.build_report_v2_rollout_receipt",
            return_value=receipt,
        ):
            self.assertEqual(handle_report_v2_rollout_gate(args), 2)

    def test_prm_assistant_parser_is_explicit(self):
        args = build_parser().parse_args(["prm-assistant"])

        self.assertIs(args.handler, handle_prm_assistant)

    def test_prm_assistant_skips_startup_migrations_and_uses_safe_mode(self):
        args = build_parser().parse_args(["prm-assistant"])
        settings = SimpleNamespace(db_path="/tmp/agent.db")

        with patch("main.load_settings", return_value=settings), patch("main.run_migrations") as migrations_mock, patch(
            "main.run_bot"
        ) as run_bot_mock:
            self.assertEqual(handle_prm_assistant(args), 0)

        migrations_mock.assert_not_called()
        run_bot_mock.assert_called_once_with(settings, runtime_mode=BOT_RUNTIME_PRM_ASSISTANT)

    def test_memory_ask_parser_is_user_facing(self):
        args = build_parser().parse_args(["memory", "ask", "что", "есть", "по", "eval", "--limit", "3"])

        self.assertEqual(args.question, ["что", "есть", "по", "eval"])
        self.assertEqual(args.limit, 3)
        self.assertIs(args.handler, handle_memory_ask)

    def test_memory_ask_llm_requires_provider_egress_before_pi_chat(self):
        args = build_parser().parse_args(["memory", "ask", "--llm-approved", "что", "есть", "по", "eval"])

        with patch("main.load_settings") as settings_mock, patch("assistant.pi_chat.answer_pi_chat") as chat_mock:
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(handle_memory_ask(args), 2)

        settings_mock.assert_not_called()
        chat_mock.assert_not_called()
        self.assertIn("--allow-provider-egress", output.getvalue())
        self.assertIn("No provider call was made", output.getvalue())

    def test_memory_ask_llm_approved_renders_privacy_safe_contract(self):
        args = build_parser().parse_args(
            ["memory", "ask", "--llm-approved", "--allow-provider-egress", "что", "есть", "по", "eval"]
        )
        settings = SimpleNamespace(db_path="/tmp/agent.db")

        with patch("main.load_settings", return_value=settings), patch(
            "assistant.pi_chat.answer_pi_chat",
            return_value=_fake_prm_chat_payload(),
        ) as chat_mock:
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(handle_memory_ask(args), 0)

        chat_mock.assert_called_once_with("что есть по eval", settings=settings)
        rendered = output.getvalue()
        self.assertIn("PRM Chat", rendered)
        self.assertIn("Grounded PRM answer.", rendered)
        self.assertIn("Sources\n- https://t.me/source/1", rendered)
        self.assertIn("Archive support: status=supported; source_count=1", rendered)
        self.assertIn("Unknowns\n- market freshness", rendered)
        self.assertIn(
            "Privacy: mode=llm-approved; model_calls=2; estimated_cost_usd=0.00003000; "
            "bounded_telegram_snippet_provider_egress=true; raw_telegram_corpus_egress=false; "
            "durable_writes=false",
            rendered,
        )

    def test_memory_chat_parser_and_unapproved_refusal(self):
        args = build_parser().parse_args(["memory", "chat"])

        self.assertIs(args.handler, handle_memory_chat)
        with patch("main.load_settings") as settings_mock, patch("assistant.pi_chat.answer_pi_chat") as chat_mock:
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(handle_memory_chat(args), 2)

        settings_mock.assert_not_called()
        chat_mock.assert_not_called()
        self.assertIn("--allow-provider-egress", output.getvalue())

    def test_memory_chat_interactive_runs_repeated_questions_with_fake_chat(self):
        args = build_parser().parse_args(["memory", "chat", "--allow-provider-egress"])
        settings = SimpleNamespace(db_path="/tmp/agent.db")

        with patch("main.load_settings", return_value=settings), patch(
            "assistant.pi_chat.answer_pi_chat",
            return_value=_fake_prm_chat_payload(),
        ) as chat_mock, patch("sys.stdin", StringIO("first question\n\n/exit\n")):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(handle_memory_chat(args), 0)

        chat_mock.assert_called_once_with("first question", settings=settings)
        rendered = output.getvalue()
        self.assertIn("PRM Chat interactive", rendered)
        self.assertIn("Grounded PRM answer.", rendered)
        self.assertIn("Privacy: mode=llm-approved", rendered)

    def test_memory_research_parser_is_local_and_bounded(self):
        args = build_parser().parse_args(
            [
                "memory",
                "research",
                "--project",
                "Eval-Ground-Truth-Lab",
                "--max-tool-calls",
                "4",
                "--max-linked-sources",
                "2",
                "что",
                "есть",
                "по",
                "eval",
            ]
        )

        self.assertEqual(args.question, ["что", "есть", "по", "eval"])
        self.assertEqual(args.project, "Eval-Ground-Truth-Lab")
        self.assertEqual(args.max_tool_calls, 4)
        self.assertEqual(args.max_linked_sources, 2)
        self.assertIs(args.handler, handle_memory_research)

    def test_memory_research_handler_skips_migrations_and_renders_answer(self):
        args = build_parser().parse_args(["memory", "research", "что", "есть", "по", "eval"])
        settings = SimpleNamespace(db_path="/tmp/agent.db")
        payload = {
            "schema_version": "memory_research_answer.v1",
            "status": "ok",
            "question": "что есть по eval",
            "answer": "rendered research body",
            "privacy": {"model_calls": 0},
            "receipt": {"budget": {}, "tool_calls_used": 0},
        }

        with patch("main.load_settings", return_value=settings), patch("main.run_migrations") as migrations_mock, patch(
            "assistant.memory_research.answer_memory_research",
            return_value=payload,
        ) as research_mock, patch(
            "assistant.memory_research.render_memory_research_answer",
            return_value="rendered research",
        ):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(handle_memory_research(args), 0)

        migrations_mock.assert_not_called()
        research_mock.assert_called_once()
        call_kwargs = research_mock.call_args.kwargs
        self.assertEqual(research_mock.call_args.args[0], "что есть по eval")
        self.assertIs(call_kwargs["settings"], settings)
        self.assertEqual(call_kwargs["week_label"], None)
        self.assertEqual(call_kwargs["project_name"], None)
        self.assertEqual(call_kwargs["limit"], 5)
        self.assertEqual(call_kwargs["budget"].max_model_calls, 0)
        self.assertFalse(call_kwargs["budget"].allow_open_browsing)
        self.assertFalse(call_kwargs["budget"].allow_provider_egress)
        self.assertEqual(output.getvalue(), "rendered research\n")

    def test_memory_research_handler_returns_refusal_code(self):
        args = build_parser().parse_args(["memory", "research", "browse", "web"])
        settings = SimpleNamespace(db_path="/tmp/agent.db")
        payload = {
            "schema_version": "memory_research_answer.v1",
            "status": "refused",
            "question": "browse web",
            "message": "Open-ended browsing is not approved.",
            "receipt": {"privacy": {"model_calls": 0}},
            "privacy": {"model_calls": 0},
        }

        with patch("main.load_settings", return_value=settings), patch(
            "assistant.memory_research.answer_memory_research",
            return_value=payload,
        ), patch(
            "assistant.memory_research.render_memory_research_answer",
            return_value="refused",
        ):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(handle_memory_research(args), 2)

        self.assertEqual(output.getvalue(), "refused\n")

    def test_memory_ask_handler_skips_migrations_and_renders_answer(self):
        args = build_parser().parse_args(["memory", "ask", "что", "есть", "по", "eval"])
        settings = SimpleNamespace(db_path="/tmp/agent.db")
        payload = {
            "schema_version": "local_memory_answer.v1",
            "status": "ok",
            "question": "что есть по eval",
            "mode": "local_only",
            "answer": "Evidence answer",
            "privacy": {"model_calls": 0},
        }

        with patch("main.load_settings", return_value=settings), patch("main.run_migrations") as migrations_mock, patch(
            "assistant.local_memory_ask.answer_local_memory_question",
            return_value=payload,
        ) as ask_mock, patch(
            "assistant.local_memory_ask.render_local_memory_answer",
            return_value="rendered answer",
        ):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(handle_memory_ask(args), 0)

        migrations_mock.assert_not_called()
        ask_mock.assert_called_once_with(
            "что есть по eval",
            settings=settings,
            week_label=None,
            project_name=None,
            limit=5,
        )
        self.assertEqual(output.getvalue(), "rendered answer\n")


if __name__ == "__main__":
    unittest.main()
