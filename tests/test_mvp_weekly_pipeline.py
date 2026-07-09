import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from output.mvp_weekly_pipeline import MvpWeeklyPipelineResult, _deliver_result, _run_radar, _write_mvp_operator_message


class TestMvpWeeklyPipeline(unittest.TestCase):
    def test_deliver_result_publishes_telegraph_and_sends_document(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "mvp.md"
            report_path.write_text(
                "# MVP of the Week: Operator Fit Tool\n\n## Evidence\n\n- Source-backed point.",
                encoding="utf-8",
            )
            result = MvpWeeklyPipelineResult(
                week_label="2026-W22",
                seed_path="/tmp/seeds.json",
                seed_count=4,
                radar_status="selected",
                report_path=str(report_path),
                json_path="/tmp/mvp.json",
                selected_title="Operator Fit Tool",
                dossier_status="investigate",
                recommendation="revisit_with_evidence_gap",
                score=62,
                selected_source_mix={
                    "readiness": "credential_limited",
                    "reddit_api_status": "missing_credentials",
                    "missing_credentials": ["reddit_demand_live"],
                },
                matched_external_evidence=[],
                decision_change_action={
                    "matched_external_evidence_count": 0,
                    "matched_external_source_types": [],
                    "next_query": '"operator fit tool" workaround',
                    "next_validation_action": (
                        'Run `"operator fit tool" workaround` and attach only candidate-matched evidence.'
                    ),
                },
                source_counts={
                    "live_intelligence": {
                        "events_scanned": 12,
                        "repeated_claim_count": 2,
                        "pathway": {"status": "not_installed"},
                    }
                },
            )

            with patch.dict(
                "os.environ",
                {
                    "TELEGRAM_BOT_TOKEN": "bot-token",
                    "TELEGRAM_OWNER_CHAT_ID": "42",
                },
            ):
                with patch(
                    "output.mvp_weekly_pipeline.publish_article",
                    return_value="https://telegra.ph/mvp-weekly",
                ) as mock_publish:
                    with patch("output.mvp_weekly_pipeline.send_text") as mock_text:
                        with patch("output.mvp_weekly_pipeline.send_document") as mock_document:
                            telegraph_url = _deliver_result(result)

            self.assertEqual(telegraph_url, "https://telegra.ph/mvp-weekly")
            mock_publish.assert_called_once()
            notification = mock_text.call_args.kwargs["text"]
            self.assertIn("MVP-кандидат 2026-W22: Operator Fit Tool", notification)
            self.assertIn("Решение: пока не строим.", notification)
            self.assertIn("0 Telegram-сигналов", notification)
            self.assertIn("Live intelligence: найдено 2 повторяющихся тезисов.", notification)
            self.assertIn(
                'Валидация: 0 matched external evidence; types=none; '
                'next query: "operator fit tool" workaround',
                notification,
            )
            self.assertIn("https://telegra.ph/mvp-weekly", notification)
            self.assertEqual(
                mock_text.call_args.kwargs["reply_markup"]["inline_keyboard"][0][0]["callback_data"],
                "art:2026-W22:mvp:u",
            )
            mock_document.assert_called_once_with(
                chat_id="42",
                file_path=str(report_path),
                caption="MVP of the Week 2026-W22",
                token="bot-token",
            )

    def test_deliver_result_does_not_claim_build_when_recommendation_revisits(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "mvp.md"
            report_path.write_text("# Candidate Dossier\n", encoding="utf-8")
            result = MvpWeeklyPipelineResult(
                week_label="2026-W24",
                seed_path="/tmp/seeds.json",
                seed_count=3,
                radar_status="selected",
                report_path=str(report_path),
                json_path="/tmp/mvp.json",
                selected_title="Operator Fit Tool",
                dossier_status="build",
                recommendation="revisit_with_evidence_gap",
                score=80,
            )

            with patch.dict(
                "os.environ",
                {
                    "TELEGRAM_BOT_TOKEN": "bot-token",
                    "TELEGRAM_OWNER_CHAT_ID": "42",
                },
            ):
                with patch("output.mvp_weekly_pipeline.publish_article", return_value=None):
                    with patch("output.mvp_weekly_pipeline.send_text") as mock_text:
                        with patch("output.mvp_weekly_pipeline.send_document"):
                            _deliver_result(result)

            notification = mock_text.call_args.kwargs["text"]
            self.assertIn("Решение: пока не строим.", notification)
            self.assertNotIn("Решение: можно рассматривать", notification)

    def test_run_radar_passes_live_intelligence_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            radar_repo = root / "radar"
            radar_repo.mkdir()
            live_path = root / "live.json"
            live_path.write_text("{}", encoding="utf-8")
            seed_path = root / "seeds.json"
            seed_path.write_text("[]", encoding="utf-8")

            with patch.dict(
                "os.environ",
                {
                    "RADAR_REPO_PATH": str(radar_repo),
                    "RADAR_PYTHON": "/usr/bin/python3",
                    "DMR_DATA_DIR": str(root / "data"),
                    "DMR_REPORT_DIR": str(root / "reports"),
                },
                clear=False,
            ):
                with patch("output.mvp_weekly_pipeline.subprocess.run") as mock_run:
                    mock_run.return_value = types.SimpleNamespace(
                        stdout='{"status":"selected"}'
                    )
                    payload = _run_radar(
                        seed_path=seed_path,
                        run_id="mvp-weekly-live",
                        live_intelligence_path=live_path,
                    )

        command = mock_run.call_args.args[0]
        self.assertEqual(payload["status"], "selected")
        self.assertIn("--live-intelligence", command)
        self.assertIn(str(live_path), command)

    def test_operator_message_explains_empty_market_pack(self):
        result = MvpWeeklyPipelineResult(
            week_label="2026-W28",
            seed_path="/tmp/seeds.json",
            seed_count=0,
            radar_status="no_candidate",
            report_path=None,
            json_path=None,
            selected_title=None,
            dossier_status="reject",
            recommendation="needs_more_evidence",
            score=None,
            market_pack_path="/tmp/market.json",
            market_pain_pack={
                "status": "empty",
                "posts_scanned": 0,
                "radar_gate_audit": {
                    "summary": "no market/business posts found in bounded lookback",
                    "build_ready_evidence": False,
                },
            },
        )

        with patch("output.mvp_weekly_pipeline.write_weekly_message") as mock_write:
            notification = _write_mvp_operator_message(result)

        self.assertIn("Market pack: empty bounded lookback", notification)
        self.assertIn("no market/business posts found", notification)
        mock_write.assert_called_once()


if __name__ == "__main__":
    unittest.main()
