import unittest
from types import SimpleNamespace
from unittest.mock import patch

from main import build_parser, handle_report_v2_rollout_gate, handle_weekly_intelligence_v2


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


if __name__ == "__main__":
    unittest.main()
