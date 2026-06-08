import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from output.mvp_weekly_pipeline import MvpWeeklyPipelineResult, _deliver_result


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
            self.assertIn("Status: investigate, score 62/100.", notification)
            self.assertIn("Recommendation: revisit_with_evidence_gap.", notification)
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


if __name__ == "__main__":
    unittest.main()
