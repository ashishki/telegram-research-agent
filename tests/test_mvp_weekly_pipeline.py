import json
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from output.mvp_weekly_pipeline import (
    MvpWeeklyPipelineResult,
    _deliver_result,
    _mvp_artifact_title,
    _period_display_label,
    _prepare_live_intelligence_path,
    _run_radar,
    _write_mvp_operator_message,
    run_mvp_weekly_pipeline,
)
from output.reporting_period import TRAILING_SEVEN_DAYS, resolve_reporting_period


class TestMvpWeeklyPipeline(unittest.TestCase):
    def test_result_keeps_legacy_optional_positional_order(self):
        result = MvpWeeklyPipelineResult(
            "2026-W28",
            "/tmp/seeds.json",
            1,
            "selected",
            None,
            None,
            "Candidate",
            "investigate",
            "needs_more_evidence",
            50,
            {"telegram": True},
        )

        self.assertEqual(result.selected_source_mix, {"telegram": True})
        self.assertEqual(result.radar_run_id, "")

    def _invoke_radar(
        self,
        root: Path,
        *,
        stdout: str,
        run_id: str = "mvp-weekly-identity",
        live_intelligence_path: Path | None = None,
    ):
        radar_repo = root / "radar"
        radar_repo.mkdir(exist_ok=True)
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
                mock_run.return_value = types.SimpleNamespace(stdout=stdout)
                payload = _run_radar(
                    seed_path=seed_path,
                    run_id=run_id,
                    live_intelligence_path=live_intelligence_path,
                )
        return payload, mock_run

    def test_default_pipeline_propagates_completed_period_to_radar_seed_export(self):
        seed_export = types.SimpleNamespace(
            week_label="2026-W28",
            output_path="/tmp/2026-W28.json",
            seed_count=1,
            knowledge_thread_count=0,
            knowledge_threads=[],
            market_pack_path=None,
            market_pain_pack={},
            market_lens_path=None,
            market_baseline_path=None,
            market_delta_path=None,
            market_context_lens={},
        )
        generated_at = datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
        with patch("output.mvp_weekly_pipeline.export_opportunity_seeds", return_value=seed_export) as export:
            with patch(
                "output.mvp_weekly_pipeline._run_radar",
                return_value={
                    "run_id": "mvp-weekly-2026-W28",
                    "status": "no_candidate",
                },
            ) as radar:
                with patch("output.mvp_weekly_pipeline._write_mvp_operator_message"):
                    result = run_mvp_weekly_pipeline(
                        object(),  # type: ignore[arg-type]
                        now=generated_at,
                        deliver=False,
                    )

        period = export.call_args.kwargs["reporting_period"]
        self.assertEqual(period.reporting_week, "2026-W28")
        self.assertEqual(period.period_mode, "completed_iso_week")
        self.assertEqual(period.analysis_period_start.isoformat(), "2026-07-06T00:00:00+00:00")
        self.assertEqual(period.analysis_period_end.isoformat(), "2026-07-13T00:00:00+00:00")
        self.assertEqual(radar.call_args.kwargs["run_id"], "mvp-weekly-2026-W28")
        self.assertEqual(result.reporting_week, "2026-W28")
        self.assertEqual(result.period_mode, "completed_iso_week")
        self.assertEqual(result.analysis_period_end, "2026-07-13T00:00:00Z")

    def test_legacy_days_mode_passes_one_typed_trailing_period_to_seed_export(self):
        seed_export = types.SimpleNamespace(
            week_label="2026-W29",
            output_path="/tmp/2026-W29.json",
            seed_count=0,
            knowledge_thread_count=0,
            knowledge_threads=[],
            market_pack_path=None,
            market_pain_pack={},
            market_lens_path=None,
            market_baseline_path=None,
            market_delta_path=None,
            market_context_lens={},
        )
        generated_at = datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
        with patch("output.mvp_weekly_pipeline.export_opportunity_seeds", return_value=seed_export) as export:
            with patch(
                "output.mvp_weekly_pipeline._run_radar",
                return_value={
                    "run_id": "mvp-weekly-2026-W29",
                    "status": "no_candidate",
                },
            ):
                with patch("output.mvp_weekly_pipeline._write_mvp_operator_message"):
                    result = run_mvp_weekly_pipeline(
                        object(),  # type: ignore[arg-type]
                        days=7,
                        now=generated_at,
                        deliver=False,
                    )

        period = export.call_args.kwargs["reporting_period"]
        self.assertNotIn("days", export.call_args.kwargs)
        self.assertEqual(period.period_mode, TRAILING_SEVEN_DAYS)
        self.assertEqual(period.analysis_period_start.isoformat(), "2026-07-06T07:02:52+00:00")
        self.assertEqual(period.analysis_period_end, generated_at)
        self.assertEqual(result.period_mode, TRAILING_SEVEN_DAYS)

    def test_explicit_week_compatibility_propagates_historical_period(self):
        seed_export = types.SimpleNamespace(
            week_label="2026-W28",
            output_path="/tmp/2026-W28.json",
            seed_count=0,
            knowledge_thread_count=0,
            knowledge_threads=[],
            market_pack_path=None,
            market_pain_pack={},
            market_lens_path=None,
            market_baseline_path=None,
            market_delta_path=None,
            market_context_lens={},
        )
        with patch("output.mvp_weekly_pipeline.export_opportunity_seeds", return_value=seed_export) as export:
            with patch(
                "output.mvp_weekly_pipeline._run_radar",
                return_value={
                    "run_id": "mvp-weekly-2026-W28",
                    "status": "no_candidate",
                },
            ):
                with patch("output.mvp_weekly_pipeline._write_mvp_operator_message"):
                    result = run_mvp_weekly_pipeline(
                        object(),  # type: ignore[arg-type]
                        week_label="2026-W28",
                        now=datetime(2026, 7, 20, 8, tzinfo=timezone.utc),
                        deliver=False,
                    )

        period = export.call_args.kwargs["reporting_period"]
        self.assertEqual(period.period_mode, "explicit_iso_week")
        self.assertEqual(period.analysis_period_start.isoformat(), "2026-07-06T00:00:00+00:00")
        self.assertEqual(period.analysis_period_end.isoformat(), "2026-07-13T00:00:00+00:00")
        self.assertEqual(result.reporting_week, "2026-W28")

    def test_live_snapshot_and_backfill_receive_the_resolved_period(self):
        period = resolve_reporting_period(
            datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = types.SimpleNamespace(db_path=str(Path(tmp_dir) / "agent.db"))
            live_result = types.SimpleNamespace(output_path=Path(tmp_dir) / "live.json")
            with patch(
                "output.source_events.backfill_recent_source_events"
            ) as backfill:
                with patch(
                    "output.live_source_intelligence.build_live_source_intelligence_snapshot",
                    return_value=live_result,
                ) as build_snapshot:
                    output_path = _prepare_live_intelligence_path(
                        settings,  # type: ignore[arg-type]
                        explicit_path=None,
                        enabled=True,
                        reporting_period=period,
                        requested_days=7,
                        backfill=True,
                    )

        self.assertEqual(output_path, live_result.output_path)
        self.assertEqual(
            backfill.call_args.kwargs["analysis_period_start"],
            period.analysis_period_start,
        )
        self.assertEqual(
            backfill.call_args.kwargs["analysis_period_end"],
            period.analysis_period_end,
        )
        self.assertIs(
            build_snapshot.call_args.kwargs["reporting_period"],
            period,
        )

    def test_orchestrated_live_snapshot_requires_full_period_identity(self):
        period = resolve_reporting_period(
            datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "live.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "live_source_intelligence.v1",
                        "window": {
                            "start": "2026-07-06T00:00:00Z",
                            "end": "2026-07-13T00:00:00Z",
                        },
                        "reporting_week": "2026-W27",
                        "week_label": "2026-W27",
                        "period_mode": "explicit_iso_week",
                    }
                ),
                encoding="utf-8",
            )
            settings = types.SimpleNamespace(db_path=str(Path(tmp_dir) / "agent.db"))

            # The legacy explicit-input path keeps its window-only contract.
            self.assertEqual(
                _prepare_live_intelligence_path(
                    settings,  # type: ignore[arg-type]
                    explicit_path=path,
                    enabled=False,
                    reporting_period=period,
                    requested_days=None,
                    backfill=False,
                ),
                path,
            )
            with self.assertRaisesRegex(ValueError, "reporting_week"):
                _prepare_live_intelligence_path(
                    settings,  # type: ignore[arg-type]
                    explicit_path=path,
                    enabled=False,
                    reporting_period=period,
                    requested_days=None,
                    backfill=False,
                    require_period_identity=True,
                )

    def test_resolved_period_and_run_scoped_seed_path_propagate_without_operator_outputs(self):
        period = resolve_reporting_period(
            datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
        )
        seed_export = types.SimpleNamespace(
            week_label="2026-W28",
            output_path="/tmp/run-scoped/seeds.json",
            seed_count=1,
            knowledge_thread_count=0,
            knowledge_threads=[],
            market_pack_path=None,
            market_pain_pack={},
            market_lens_path=None,
            market_baseline_path=None,
            market_delta_path=None,
            market_context_lens={},
        )
        seed_output_path = Path("/tmp/run-scoped/seeds.json")
        radar_payload = {
            "run_id": "radar-run-2026-W28",
            "status": "no_candidate",
            "json_path": "/tmp/run-scoped/radar.json",
        }
        with patch(
            "output.mvp_weekly_pipeline.export_opportunity_seeds",
            return_value=seed_export,
        ) as export:
            with patch(
                "output.mvp_weekly_pipeline._run_radar",
                return_value=radar_payload,
            ) as radar:
                with patch(
                    "output.mvp_weekly_pipeline._write_mvp_operator_message"
                ) as write_message:
                    with patch("output.mvp_weekly_pipeline._deliver_result") as deliver:
                        result = run_mvp_weekly_pipeline(
                            object(),  # type: ignore[arg-type]
                            reporting_period=period,
                            seed_output_path=seed_output_path,
                            radar_run_id="radar-run-2026-W28",
                            emit_operator_outputs=False,
                        )

        self.assertIs(export.call_args.kwargs["reporting_period"], period)
        self.assertEqual(export.call_args.kwargs["output_path"], seed_output_path)
        self.assertEqual(radar.call_args.kwargs["run_id"], "radar-run-2026-W28")
        self.assertEqual(result.radar_run_id, "radar-run-2026-W28")
        self.assertEqual(result.reporting_week, period.reporting_week)
        write_message.assert_not_called()
        deliver.assert_not_called()

    def test_resolved_period_rejects_all_legacy_period_inputs(self):
        period = resolve_reporting_period(
            datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
        )
        conflicts = (
            {"days": 7},
            {"week_label": "2026-W27"},
            {"period_mode": TRAILING_SEVEN_DAYS},
            {"now": datetime(2026, 7, 13, 8, tzinfo=timezone.utc)},
        )
        for conflict in conflicts:
            with self.subTest(conflict=conflict):
                with self.assertRaisesRegex(ValueError, "reporting_period cannot be combined"):
                    run_mvp_weekly_pipeline(
                        object(),  # type: ignore[arg-type]
                        reporting_period=period,
                        **conflict,
                    )

    def test_radar_run_id_alias_rejects_conflicting_legacy_run_id(self):
        with self.assertRaisesRegex(ValueError, "run_id and radar_run_id must match"):
            run_mvp_weekly_pipeline(
                object(),  # type: ignore[arg-type]
                run_id="legacy-radar-run",
                radar_run_id="orchestrated-radar-run",
                now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
            )

    def test_legacy_operator_output_defaults_remain_enabled(self):
        seed_export = types.SimpleNamespace(
            week_label="2026-W28",
            output_path="/tmp/2026-W28.json",
            seed_count=0,
            knowledge_thread_count=0,
            knowledge_threads=[],
            market_pack_path=None,
            market_pain_pack={},
            market_lens_path=None,
            market_baseline_path=None,
            market_delta_path=None,
            market_context_lens={},
        )
        with patch(
            "output.mvp_weekly_pipeline.export_opportunity_seeds",
            return_value=seed_export,
        ) as export:
            with patch(
                "output.mvp_weekly_pipeline._run_radar",
                return_value={"run_id": "mvp-weekly-2026-W28", "status": "no_candidate"},
            ):
                with patch(
                    "output.mvp_weekly_pipeline._write_mvp_operator_message"
                ) as write_message:
                    with patch(
                        "output.mvp_weekly_pipeline._deliver_result",
                        return_value="https://telegra.ph/mvp-weekly",
                    ) as deliver:
                        result = run_mvp_weekly_pipeline(
                            object(),  # type: ignore[arg-type]
                            now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
                        )

        self.assertIsNone(export.call_args.kwargs["output_path"])
        write_message.assert_called_once()
        deliver.assert_called_once()
        self.assertEqual(result.telegraph_url, "https://telegra.ph/mvp-weekly")
        self.assertEqual(result.radar_run_id, "mvp-weekly-2026-W28")

    def test_trailing_mode_is_not_presented_as_an_iso_week_report(self):
        result = MvpWeeklyPipelineResult(
            week_label="2026-W29",
            seed_path="/tmp/seeds.json",
            seed_count=0,
            radar_status="no_candidate",
            report_path=None,
            json_path=None,
            selected_title=None,
            dossier_status=None,
            recommendation=None,
            score=None,
            period_mode=TRAILING_SEVEN_DAYS,
            analysis_period_start="2026-07-06T07:02:52Z",
            analysis_period_end="2026-07-13T07:02:52Z",
        )

        label = _period_display_label(result)
        self.assertIn("trailing seven days", label)
        self.assertNotIn("2026-W29", label)
        self.assertEqual(_mvp_artifact_title(result), f"MVP — {label}")

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
                    with patch(
                        "output.mvp_weekly_pipeline.write_weekly_message"
                    ) as mock_weekly_message:
                        with patch("output.mvp_weekly_pipeline.send_text") as mock_text:
                            with patch("output.mvp_weekly_pipeline.send_document") as mock_document:
                                telegraph_url = _deliver_result(result)

            self.assertEqual(telegraph_url, "https://telegra.ph/mvp-weekly")
            mock_publish.assert_called_once()
            mock_weekly_message.assert_called_once()
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
                    with patch(
                        "output.mvp_weekly_pipeline.write_weekly_message"
                    ) as mock_weekly_message:
                        with patch("output.mvp_weekly_pipeline.send_text") as mock_text:
                            with patch("output.mvp_weekly_pipeline.send_document"):
                                _deliver_result(result)

            notification = mock_text.call_args.kwargs["text"]
            self.assertIn("Решение: пока не строим.", notification)
            self.assertNotIn("Решение: можно рассматривать", notification)
            mock_weekly_message.assert_called_once()

    def test_run_radar_passes_live_intelligence_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            live_path = root / "live.json"
            live_path.write_text("{}", encoding="utf-8")
            json_path = root / "radar-result.json"
            result_fields = {
                "run_id": "mvp-weekly-live",
                "status": "selected",
                "selected_title": None,
                "dossier_status": None,
                "recommendation": None,
                "score": None,
                "selected_source_mix": {},
                "validation_adapter_status": {},
                "matched_external_evidence": [],
                "missing_evidence_by_category": {},
                "decision_change_action": None,
            }
            json_path.write_text(
                json.dumps(
                    {
                        "result": result_fields,
                    }
                ),
                encoding="utf-8",
            )
            payload, mock_run = self._invoke_radar(
                root,
                stdout=json.dumps(
                    {
                        **result_fields,
                        "json_path": str(json_path),
                    }
                ),
                run_id="mvp-weekly-live",
                live_intelligence_path=live_path,
            )

        command = mock_run.call_args.args[0]
        self.assertEqual(payload["status"], "selected")
        self.assertIn("--live-intelligence", command)
        self.assertIn(str(live_path), command)

    def test_run_radar_rejects_non_object_stdout(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaisesRegex(RuntimeError, "must be a JSON object"):
                self._invoke_radar(Path(tmp_dir), stdout="[]")

    def test_run_radar_rejects_malformed_stdout(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaisesRegex(RuntimeError, "malformed JSON output"):
                self._invoke_radar(Path(tmp_dir), stdout="{not-json")

    def test_run_radar_rejects_wrong_stdout_run_id(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaisesRegex(RuntimeError, "result run_id does not match"):
                self._invoke_radar(
                    Path(tmp_dir),
                    stdout=json.dumps(
                        {
                            "run_id": "wrong-run",
                            "json_path": str(Path(tmp_dir) / "unused.json"),
                        }
                    ),
                )

    def test_run_radar_rejects_missing_json_result(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaisesRegex(RuntimeError, "JSON result not found"):
                self._invoke_radar(
                    Path(tmp_dir),
                    stdout=json.dumps(
                        {
                            "run_id": "mvp-weekly-identity",
                            "json_path": str(Path(tmp_dir) / "missing.json"),
                        }
                    ),
                )

    def test_run_radar_rejects_malformed_json_result(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            json_path = root / "malformed.json"
            json_path.write_text("{not-json", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "JSON result is malformed"):
                self._invoke_radar(
                    root,
                    stdout=json.dumps(
                        {
                            "run_id": "mvp-weekly-identity",
                            "json_path": str(json_path),
                        }
                    ),
                )

    def test_run_radar_rejects_wrong_json_result_run_id(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            json_path = root / "wrong-run.json"
            json_path.write_text(
                json.dumps({"result": {"run_id": "wrong-run"}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, r"JSON result\.run_id does not match"):
                self._invoke_radar(
                    root,
                    stdout=json.dumps(
                        {
                            "run_id": "mvp-weekly-identity",
                            "json_path": str(json_path),
                        }
                    ),
                )

    def test_run_radar_rejects_stdout_raw_projection_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            json_path = root / "projection-mismatch.json"
            json_path.write_text(
                json.dumps(
                    {
                        "result": {
                            "run_id": "mvp-weekly-identity",
                            "status": "selected",
                            "selected_title": "Raw candidate",
                            "dossier_status": "investigate",
                            "recommendation": "revisit_with_evidence_gap",
                            "score": 61,
                        }
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "stdout/JSON mismatch for selected_title",
            ):
                self._invoke_radar(
                    root,
                    stdout=json.dumps(
                        {
                            "run_id": "mvp-weekly-identity",
                            "status": "selected",
                            "selected_title": "Stdout candidate",
                            "dossier_status": "investigate",
                            "recommendation": "revisit_with_evidence_gap",
                            "score": 61,
                            "json_path": str(json_path),
                        }
                    ),
                )

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
