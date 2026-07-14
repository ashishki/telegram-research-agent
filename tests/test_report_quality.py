import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from output.report_quality import (
    READER_VALUE_BLOCKING_V2,
    READER_VALUE_WARN_ONLY_V1,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    ReaderValueQualityError,
    WeeklyReportFacts,
    digest_has_project_insights,
    evaluate_reader_report_quality,
    format_findings_for_notification,
    format_reader_quality_warning,
    load_weekly_quality_facts,
    require_reader_report_quality,
    validate_artifact,
    validate_mvp_delivery_consistency,
    validate_reader_report_quality,
    validate_weekly_artifact_paths,
    validate_weekly_artifacts,
)
from output.reader_value_quality import ReaderQualityContractError
from output.report_visuals import render_report_visual, validate_report_visual


class TestReportQualityValidation(unittest.TestCase):
    def test_matches_trace_as_takeaway_returns_warning(self):
        findings = validate_artifact(
            "research_brief",
            "\n".join(
                [
                    "## Decision Brief",
                    "- Evaluated: 10 posts.",
                    "",
                    "## Project Insights",
                    "- Key takeaway: Matches: claude, git",
                    "",
                    "## What Changed",
                    "- watch: 1",
                ]
            ),
        )

        self.assertTrue(any(finding.severity == SEVERITY_WARNING for finding in findings))
        self.assertTrue(any("project-matching trace" in finding.message for finding in findings))

    def test_missing_decision_brief_returns_warning(self):
        findings = validate_artifact(
            "research_brief",
            "## Macro Context\n- Signal details\n\n## What Changed\n- watch: 1\n",
        )

        self.assertTrue(any("Decision Brief" in finding.message for finding in findings))

    def test_buried_what_changed_returns_warning(self):
        findings = validate_artifact(
            "research_brief",
            "## Decision Brief\n- Evaluated: 10 posts.\n\n"
            "## Project Insights\n- One detail\n\n"
            "## What Changed\n- watch: 2\n",
        )

        self.assertTrue(any("What Changed is buried" in finding.message for finding in findings))

    def test_study_plan_no_telegram_signals_with_watch_count_returns_critical(self):
        findings = validate_artifact(
            "study_plan",
            "# Study Plan\n\nNo Telegram signals this week. Plan is anchored to projects.",
            facts=WeeklyReportFacts(week_label="2026-W24", post_count=179, watch_count=56),
        )

        self.assertTrue(any(finding.severity == SEVERITY_CRITICAL for finding in findings))
        self.assertTrue(any("Study Plan says no Telegram signals" in finding.message for finding in findings))

    def test_project_insights_empty_while_digest_has_insights_returns_critical(self):
        digest = "\n".join(
            [
                "## Decision Brief",
                "- Evaluated: 179 posts.",
                "",
                "## Project Insights",
                "**telegram-research-agent**",
                "- Source-backed report quality gate signal.",
                "",
                "## What Changed",
                "- watch: 56",
            ]
        )
        project_insights = "## Project Insights - 2026-W24\n\nNo project insights were identified this week.\n"

        findings = validate_weekly_artifacts(
            week_label="2026-W24",
            digest_md=digest,
            project_insights_md=project_insights,
            facts=WeeklyReportFacts(week_label="2026-W24", post_count=179, watch_count=56),
        )

        self.assertTrue(digest_has_project_insights(digest))
        self.assertTrue(any(finding.artifact_type == "project_insights" for finding in findings))
        self.assertTrue(any(finding.severity == SEVERITY_CRITICAL for finding in findings))

    def test_mvp_delivery_build_claim_with_revisit_recommendation_returns_critical(self):
        findings = validate_mvp_delivery_consistency(
            status="build",
            recommendation="revisit_with_evidence_gap",
            notification_text=(
                "MVP of the Week 2026-W24 is ready.\n"
                "Status: build, score 80/100.\n"
                "Recommendation: revisit_with_evidence_gap."
            ),
        )

        self.assertTrue(any(finding.artifact_type == "mvp_weekly" for finding in findings))
        self.assertGreaterEqual(
            sum(1 for finding in findings if finding.severity == SEVERITY_CRITICAL),
            1,
        )

    def test_weekly_artifacts_validate_mvp_delivery_consistency(self):
        findings = validate_weekly_artifacts(
            week_label="2026-W24",
            mvp_status="focused_experiment",
            mvp_recommendation="needs_more_evidence",
            mvp_notification_text="Status: focused_experiment.",
            facts=WeeklyReportFacts(week_label="2026-W24"),
        )

        self.assertTrue(any(finding.artifact_type == "mvp_weekly" for finding in findings))

    def test_overlong_report_without_summary_returns_warning(self):
        content = "## Macro Context\n" + " ".join(["word"] * 61)
        findings = validate_artifact("research_brief", content, word_budget=60)

        self.assertTrue(any("without an explicit summary" in finding.message for finding in findings))

    def test_critical_findings_format_for_notification(self):
        findings = validate_artifact(
            "study_plan",
            "No Telegram signals this week.",
            facts=WeeklyReportFacts(week_label="2026-W24", watch_count=2),
        )

        notification = format_findings_for_notification(findings)

        self.assertIsNotNone(notification)
        self.assertIn("Report quality warning", notification or "")
        self.assertIn("critical", notification or "")

    def test_validate_weekly_artifact_paths_loads_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir)
            (output_root / "digests").mkdir()
            (output_root / "study_plans").mkdir()
            (output_root / "project_insights").mkdir()
            (output_root / "digests" / "2026-W24.md").write_text(
                "## Decision Brief\n- Evaluated\n\n"
                "## Project Insights\n**project**\n- useful insight\n\n"
                "## What Changed\n- watch: 1\n",
                encoding="utf-8",
            )
            (output_root / "study_plans" / "2026-W24.md").write_text(
                "No Telegram signals this week.",
                encoding="utf-8",
            )
            (output_root / "project_insights" / "2026-W24.md").write_text(
                "## Project Insights - 2026-W24\n\nNo project insights were identified this week.\n",
                encoding="utf-8",
            )

            findings = validate_weekly_artifact_paths(
                "2026-W24",
                facts=WeeklyReportFacts(week_label="2026-W24", post_count=10, watch_count=1),
                output_root=output_root,
            )

        self.assertGreaterEqual(sum(1 for finding in findings if finding.severity == SEVERITY_CRITICAL), 2)

    def test_load_weekly_quality_facts_reads_quality_metrics(self):
        with sqlite3.connect(":memory:") as connection:
            connection.row_factory = sqlite3.Row
            connection.execute(
                """
                CREATE TABLE quality_metrics (
                    week_label TEXT,
                    total_posts INTEGER,
                    strong_count INTEGER,
                    watch_count INTEGER,
                    cultural_count INTEGER,
                    noise_count INTEGER,
                    project_match_count INTEGER,
                    output_word_count INTEGER
                )
                """
            )
            connection.execute(
                """
                INSERT INTO quality_metrics (
                    week_label, total_posts, strong_count, watch_count, cultural_count,
                    noise_count, project_match_count, output_word_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("2026-W24", 179, 0, 56, 7, 116, 22, 1822),
            )

            facts = load_weekly_quality_facts(connection, "2026-W24")

        self.assertEqual(facts.week_label, "2026-W24")
        self.assertEqual(facts.post_count, 179)
        self.assertEqual(facts.watch_count, 56)
        self.assertEqual(facts.actionable_signal_count, 56)


class TestReaderValueQuality(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixture_root = Path(__file__).parent / "fixtures" / "report_v2"
        cls.cases = json.loads(
            (fixture_root / "reader_value_quality_cases.v1.json").read_text(
                encoding="utf-8"
            )
        )
        cls.visual_specs = json.loads(
            (fixture_root / "visual_components.v1.json").read_text(encoding="utf-8")
        )["specs"]
        from tests.test_weekly_intelligence_brief_v2 import (
            WeeklyIntelligenceBriefV2Tests,
        )

        cls.brief_fixture = WeeklyIntelligenceBriefV2Tests
        cls.brief_fixture.setUpClass()
        cls.brief_sidecar = copy.deepcopy(cls.brief_fixture.sidecar)
        cls.brief_manifest = copy.deepcopy(cls.brief_fixture.manifest)
        cls.brief_html = Path(cls.brief_fixture.summary.html_path).read_text(
            encoding="utf-8"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.brief_fixture.tearDownClass()

    @staticmethod
    def _findings(report: dict[str, object]) -> list[dict[str, object]]:
        return [
            finding
            for dimension in report["dimensions"]
            for finding in dimension["findings"]
        ]

    def _w29_case(self, name: str) -> tuple[dict[str, object], str]:
        case = copy.deepcopy(self.cases[name])
        if "html" in case:
            return case["sidecar"], case["html"]
        html = (
            case["html_prefix"]
            + " ".join(
                [case["repeat_visible_word"]] * case["repeat_visible_word_count"]
            )
            + case["html_suffix"]
        )
        return case["sidecar"], html

    def _atlas_target(self) -> tuple[dict[str, object], str, str]:
        target = copy.deepcopy(self.cases["atlas_target_contract"])
        threads = target["threads"]
        for index, thread in enumerate(threads, start=1):
            thread["evidence_maturity"] = "repeated_signal"
            thread["independent_source_count"] = 1
            thread["evidence_refs"] = [f"evidence:atlas:{index}"]
        primary = [thread["canonical_thread_id"] for thread in threads]
        visuals = copy.deepcopy(self.visual_specs[4:8])

        graph = visuals[0]
        graph["nodes"] = [
            {
                "canonical_thread_id": thread["canonical_thread_id"],
                "title_ru": thread["title_ru"],
                "status": "growing",
                "evidence_volume": index,
                "evidence_maturity": "repeated_signal",
                "operator_interest_score": 0.5,
                "display_priority": 100 - index,
            }
            for index, thread in enumerate(threads, start=1)
        ]
        graph["edges"] = []

        timeline = visuals[1]
        timeline_templates = copy.deepcopy(timeline["series"])
        timeline["series"] = []
        for index, thread in enumerate(threads):
            row = copy.deepcopy(timeline_templates[index % len(timeline_templates)])
            row["canonical_thread_id"] = thread["canonical_thread_id"]
            row["title_ru"] = thread["title_ru"]
            timeline["series"].append(row)

        heatmap = visuals[2]
        heatmap["threads"] = [
            {
                "canonical_thread_id": thread["canonical_thread_id"],
                "title_ru": thread["title_ru"],
            }
            for thread in threads
        ]
        heatmap["cells"] = []
        for source_index, source in enumerate(heatmap["sources"], start=1):
            for thread_index, thread in enumerate(threads, start=1):
                count = 1 if source_index == 1 else 0
                heatmap["cells"].append(
                    {
                        "source_id": source["source_id"],
                        "canonical_thread_id": thread["canonical_thread_id"],
                        "mention_count": count,
                        "independent_support_count": count,
                        "evidence_refs": (
                            [f"evidence:heatmap:{source_index}:{thread_index}"]
                            if count
                            else []
                        ),
                    }
                )

        maturity = visuals[3]
        for level in maturity["levels"]:
            level["count"] = 8 if level["key"] == "repeated_signal" else 0
        maturity["thread_count"] = 8
        self.assertEqual(
            [validate_report_visual(spec) for spec in visuals],
            [
                "knowledge_graph",
                "thread_timeline",
                "source_thread_heatmap",
                "evidence_maturity",
            ],
        )

        sidecar = {
            "schema_version": "split_ai_report.v2",
            "surface": "knowledge_atlas",
            "run_id": target["run_id"],
            "reporting_week": target["reporting_week"],
            "reporting_period": {
                "reporting_week": target["reporting_week"],
                "analysis_period_start": target["analysis_period_start"],
                "analysis_period_end": target["analysis_period_end"],
            },
            "generated_at": target["generated_at"],
            "period_mode": "explicit_iso_week",
            "run_status": "complete",
            "partial": False,
            "primary_thread_ids": primary,
            "canonical_threads": threads,
            "operator_interest": {"status": "available"},
            "visual_specs": visuals,
        }
        visual_html = "".join(render_report_visual(spec).html for spec in visuals)
        html = (
            '<!doctype html><html lang="ru"><body><main>'
            "<h1>Карта устойчивого знания</h1>"
            "<p>Восемь канонических тем показывают доказательства, изменения и интерес оператора.</p>"
            f"{visual_html}"
            "<details><summary>Открыть техническую справку</summary>"
            "<p>Скрытые детали происхождения.</p></details>"
            "</main></body></html>"
        )
        return sidecar, html, visual_html

    def test_rich_brief_v2_passes_all_independent_dimensions(self):
        report = evaluate_reader_report_quality(
            self.brief_sidecar,
            self.brief_html,
            policy_mode=READER_VALUE_BLOCKING_V2,
            manifest=self.brief_manifest,
            surface="weekly_brief",
        )

        validate_reader_report_quality(report)
        self.assertEqual(report["summary"]["delivery_decision"], "allow")
        self.assertEqual(report["summary"]["overall_status"], "pass")
        self.assertEqual(self._findings(report), [])
        self.assertIn(
            "empty",
            {spec["data_status"] for spec in self.brief_sidecar["visual_specs"]},
        )
        self.assertEqual(
            self.brief_sidecar["content_metrics"]["meaningful_visual_count"],
            4,
        )
        self.assertEqual(
            [dimension["name"] for dimension in report["dimensions"]],
            [
                "structural_validity",
                "evidence_validity",
                "editorial_quality",
                "personalization_quality",
                "visual_quality",
                "project_usefulness",
                "radar_completeness",
            ],
        )

    def test_sanitized_w29_patterns_fail_with_actionable_repairs(self):
        expected = {
            "w29_brief_failure": {
                "period.not_completed_week",
                "brief.thesis_missing",
                "brief.action_duplicate",
                "brief.action_generic",
                "brief.defer_decision_missing",
                "personalization.reaction_receipt_missing",
                "project.action_not_specific",
                "radar.unavailable",
                "reader.internal_token_visible",
                "visual.meaningful_count_low",
                "metrics.blank_cell",
            },
            "w29_atlas_failure": {
                "period.not_completed_week",
                "atlas.legacy_audit_surface",
                "atlas.primary_thread_limit",
                "atlas.duplicate_content",
                "atlas.maturity_label_unsupported",
                "atlas.raw_detail_primary",
                "atlas.visible_length_critical",
                "reader.internal_token_visible",
                "visual.meaningful_count_low",
            },
        }
        surfaces = {
            "w29_brief_failure": "weekly_brief",
            "w29_atlas_failure": "knowledge_atlas",
        }
        for name, required_codes in expected.items():
            with self.subTest(name=name):
                sidecar, html = self._w29_case(name)
                report = evaluate_reader_report_quality(
                    sidecar,
                    html,
                    policy_mode=READER_VALUE_WARN_ONLY_V1,
                    surface=surfaces[name],
                )
                findings = self._findings(report)
                codes = {finding["code"] for finding in findings}
                self.assertTrue(required_codes.issubset(codes), required_codes - codes)
                self.assertEqual(
                    report["summary"]["delivery_decision"],
                    "allow_with_warnings",
                )
                self.assertGreater(report["summary"]["critical_count"], 0)
                for finding in findings:
                    self.assertTrue(finding["affected_item"])
                    self.assertTrue(finding["evidence"])
                    self.assertTrue(finding["reader_impact_ru"])
                    self.assertTrue(finding["repair_hint_ru"])

    def test_same_w29_defects_block_under_v2_policy(self):
        sidecar, html = self._w29_case("w29_brief_failure")

        report = evaluate_reader_report_quality(
            sidecar,
            html,
            policy_mode=READER_VALUE_BLOCKING_V2,
            surface="weekly_brief",
        )

        self.assertEqual(report["summary"]["delivery_decision"], "block")
        with self.assertRaises(ReaderValueQualityError):
            require_reader_report_quality(report)

    def test_atlas_target_contract_fixture_passes(self):
        sidecar, html, _visual_html = self._atlas_target()

        report = evaluate_reader_report_quality(
            sidecar,
            html,
            policy_mode=READER_VALUE_BLOCKING_V2,
            surface="knowledge_atlas",
        )

        validate_reader_report_quality(report)
        self.assertEqual(report["summary"]["delivery_decision"], "allow")
        self.assertEqual(self._findings(report), [])
        self.assertEqual(
            [
                dimension["status"]
                for dimension in report["dimensions"]
                if dimension["name"] in {"project_usefulness", "radar_completeness"}
            ],
            ["not_applicable", "not_applicable"],
        )

    def test_decorative_svg_and_forged_marker_do_not_count(self):
        sidecar, html = self._w29_case("w29_brief_failure")
        self.assertIn("<svg", html)
        self.assertIn("data-irx-visual", html)

        report = evaluate_reader_report_quality(
            sidecar,
            html,
            policy_mode=READER_VALUE_BLOCKING_V2,
            surface="weekly_brief",
        )
        codes = {finding["code"] for finding in self._findings(report)}

        self.assertIn("visual.meaningful_count_low", codes)
        self.assertIn("visual.marker_parity_mismatch", codes)

    def test_supporting_evidence_badge_is_valid_but_not_a_counted_visual(self):
        sidecar, _html, _visual_html = self._atlas_target()
        badge = copy.deepcopy(self.visual_specs[9])
        sidecar["visual_specs"][1]["series"] = sidecar["visual_specs"][1]["series"][:1]
        sidecar["visual_specs"].append(badge)
        html = (
            '<!doctype html><html lang="ru"><body><h1>Карта знаний</h1>'
            "<p>Поддерживающий знак поясняет уверенность, но не заменяет визуальную связь.</p>"
            + "".join(
                render_report_visual(spec).html for spec in sidecar["visual_specs"]
            )
            + "</body></html>"
        )

        report = evaluate_reader_report_quality(
            sidecar,
            html,
            policy_mode=READER_VALUE_BLOCKING_V2,
            surface="knowledge_atlas",
        )

        self.assertEqual(report["summary"]["delivery_decision"], "allow")
        self.assertEqual(
            [
                finding
                for finding in self._findings(report)
                if finding["dimension"] == "visual_quality"
            ],
            [],
        )

    def test_hidden_or_laundered_exact_visuals_do_not_count(self):
        sidecar, _html, visual_html = self._atlas_target()
        wrappers = {
            "template": f"<template>{visual_html}</template>",
            "closed_details": (
                f"<details><summary>Скрытые компоненты</summary>{visual_html}</details>"
            ),
            "nested_closed_details": (
                "<details><summary>Внешняя справка</summary>"
                "<details><summary>Вложенные компоненты</summary>"
                f"{visual_html}</details></details>"
            ),
            "hidden": f"<div hidden>{visual_html}</div>",
            "css_class": (
                "<style>.stealth{display:none}</style>"
                f'<div class="stealth">{visual_html}</div>'
            ),
            "comment_laundering": (
                f"<!--{visual_html}-->"
                + "".join(
                    render_report_visual(spec).html.split(">", 1)[0] + "></section>"
                    for spec in sidecar["visual_specs"]
                )
            ),
        }
        for name, wrapped in wrappers.items():
            with self.subTest(name=name):
                html = (
                    '<!doctype html><html lang="ru"><body><h1>Карта знаний</h1>'
                    "<p>Компоненты должны быть видимыми и проверяемыми.</p>"
                    f"{wrapped}</body></html>"
                )
                report = evaluate_reader_report_quality(
                    sidecar,
                    html,
                    policy_mode=READER_VALUE_BLOCKING_V2,
                    surface="knowledge_atlas",
                )
                codes = {finding["code"] for finding in self._findings(report)}
                self.assertIn("visual.meaningful_count_low", codes)
                self.assertIn("visual.initial_visibility_mismatch", codes)

    def test_duplicate_visual_and_document_ids_fail_closed(self):
        sidecar, _html, _visual_html = self._atlas_target()
        for spec in sidecar["visual_specs"]:
            spec["component_id"] = "atlas-duplicate-component"
        html = (
            '<!doctype html><html lang="ru"><body><h1>Карта знаний</h1>'
            "<p>Каждый компонент обязан иметь уникальную документную идентичность.</p>"
            + "".join(
                render_report_visual(spec).html for spec in sidecar["visual_specs"]
            )
            + "</body></html>"
        )

        report = evaluate_reader_report_quality(
            sidecar,
            html,
            policy_mode=READER_VALUE_BLOCKING_V2,
            surface="knowledge_atlas",
        )
        codes = {finding["code"] for finding in self._findings(report)}

        self.assertIn("html.dom_id_duplicate", codes)
        self.assertIn("visual.component_id_duplicate", codes)
        self.assertEqual(report["summary"]["delivery_decision"], "block")

    def test_external_or_active_presentation_sources_fail_closed(self):
        sidecar, _html, visual_html = self._atlas_target()
        mutations = {
            "stylesheet_link": (
                '<link rel="stylesheet" '
                'href="data:text/css,.stealth%7Bdisplay%3Anone%7D">'
                f'<div class="stealth">{visual_html}</div>'
            ),
            "css_import": (
                '<style>@import url("data:text/css,.stealth%7Bdisplay%3Anone%7D");</style>'
                f'<div class="stealth">{visual_html}</div>'
            ),
            "script": (f"<script>document.body.hidden=true</script>{visual_html}"),
        }
        for name, content in mutations.items():
            with self.subTest(name=name):
                html = (
                    '<!doctype html><html lang="ru"><body><h1>Карта знаний</h1>'
                    "<p>Standalone reader surface не принимает активные источники.</p>"
                    f"{content}</body></html>"
                )
                report = evaluate_reader_report_quality(
                    sidecar,
                    html,
                    policy_mode=READER_VALUE_BLOCKING_V2,
                    surface="knowledge_atlas",
                )
                self.assertIn(
                    "html.external_presentation_forbidden",
                    {finding["code"] for finding in self._findings(report)},
                )
                self.assertEqual(report["summary"]["delivery_decision"], "block")

    def test_atlas_visual_identity_and_maturity_parity_fail_closed(self):
        baseline, _html, _visual_html = self._atlas_target()
        mutations = []

        identity = copy.deepcopy(baseline)
        identity["visual_specs"][0]["nodes"][0]["canonical_thread_id"] = (
            "thread/not-in-registry"
        )
        mutations.append((identity, "atlas.visual_thread_identity_unknown"))

        maturity = copy.deepcopy(baseline)
        levels = maturity["visual_specs"][3]["levels"]
        for level in levels:
            if level["key"] == "single_source":
                level["count"] = 1
            elif level["key"] == "repeated_signal":
                level["count"] = 7
        mutations.append((maturity, "atlas.maturity_distribution_mismatch"))

        authority = copy.deepcopy(baseline)
        authority_thread = authority["canonical_threads"][0]
        authority_thread["evidence_maturity"] = "externally_corroborated"
        authority_thread["independent_source_count"] = 2
        authority_thread["evidence_refs"] = [
            "evidence:telegram:first",
            "evidence:telegram:second",
        ]
        for level in authority["visual_specs"][3]["levels"]:
            if level["key"] == "repeated_signal":
                level["count"] = 7
            elif level["key"] == "externally_corroborated":
                level["count"] = 1
        mutations.append((authority, "atlas.maturity_authority_missing"))

        forged_types = copy.deepcopy(authority)
        forged_thread = forged_types["canonical_threads"][0]
        forged_thread["external_source_count"] = True
        forged_thread["evidence_refs"] = [False, {"source": "forged"}]
        mutations.append((forged_types, "atlas.maturity_authority_missing"))
        mutations.append((forged_types, "atlas.primary_evidence_missing"))

        for sidecar, expected_code in mutations:
            with self.subTest(expected_code=expected_code):
                html = (
                    '<!doctype html><html lang="ru"><body><h1>Карта знаний</h1>'
                    "<p>Проверяем согласованность канонических данных.</p>"
                    + "".join(
                        render_report_visual(spec).html
                        for spec in sidecar["visual_specs"]
                    )
                    + "</body></html>"
                )
                report = evaluate_reader_report_quality(
                    sidecar,
                    html,
                    policy_mode=READER_VALUE_BLOCKING_V2,
                    surface="knowledge_atlas",
                )
                self.assertIn(
                    expected_code,
                    {finding["code"] for finding in self._findings(report)},
                )
                self.assertEqual(report["summary"]["delivery_decision"], "block")

    def test_brief_full_html_parity_rejects_manual_edit(self):
        edited = self.brief_html.replace(
            "</body>",
            '<svg aria-label="decorative"></svg></body>',
        )

        report = evaluate_reader_report_quality(
            self.brief_sidecar,
            edited,
            policy_mode=READER_VALUE_BLOCKING_V2,
            manifest=self.brief_manifest,
            surface="weekly_brief",
        )

        self.assertIn(
            "brief.html_parity_mismatch",
            {finding["code"] for finding in self._findings(report)},
        )
        self.assertEqual(report["summary"]["delivery_decision"], "block")

    def test_reaction_identity_mismatch_is_actionable(self):
        sidecar = copy.deepcopy(self.brief_sidecar)
        sidecar["reaction_effect"]["run_id"] = "different-run"

        report = evaluate_reader_report_quality(
            sidecar,
            self.brief_html,
            policy_mode=READER_VALUE_BLOCKING_V2,
            manifest=self.brief_manifest,
            surface="weekly_brief",
        )

        self.assertIn(
            "personalization.reaction_identity_mismatch",
            {finding["code"] for finding in self._findings(report)},
        )

    def test_product_names_do_not_mask_or_trigger_internal_id_gate(self):
        sidecar, _html = self._w29_case("w29_brief_failure")
        safe_html = (
            '<!doctype html><html lang="ru-RU"><body>'
            "<p>Apple Watch и Ranking Systems названы как продукты источника.</p>"
            "</body></html>"
        )
        unsafe_html = safe_html.replace(
            "</body>",
            "<p>action-1-verify-and-apply</p></body>",
        )

        safe_report = evaluate_reader_report_quality(
            sidecar,
            safe_html,
            policy_mode=READER_VALUE_WARN_ONLY_V1,
            surface="weekly_brief",
        )
        unsafe_report = evaluate_reader_report_quality(
            sidecar,
            unsafe_html,
            policy_mode=READER_VALUE_WARN_ONLY_V1,
            surface="weekly_brief",
        )

        self.assertNotIn(
            "reader.internal_token_visible",
            {finding["code"] for finding in self._findings(safe_report)},
        )
        self.assertNotIn(
            "language.document_not_russian",
            {finding["code"] for finding in self._findings(safe_report)},
        )
        self.assertIn(
            "reader.internal_token_visible",
            {finding["code"] for finding in self._findings(unsafe_report)},
        )

    def test_partial_type_and_repeated_action_body_fail_closed(self):
        sidecar, html = self._w29_case("w29_brief_failure")
        sidecar["partial"] = "false"
        sidecar["actions"] = [
            {"title": "Проверка первого сигнала", "next_step": "Проверить подробнее"},
            {"title": "Проверка второго сигнала", "next_step": "Проверить подробнее"},
        ]

        report = evaluate_reader_report_quality(
            sidecar,
            html,
            policy_mode=READER_VALUE_BLOCKING_V2,
            surface="weekly_brief",
        )
        codes = {finding["code"] for finding in self._findings(report)}

        self.assertIn("status.partial_type_invalid", codes)
        self.assertIn("brief.action_body_duplicate", codes)
        self.assertIn("brief.action_body_generic", codes)
        self.assertFalse(report["summary"]["partial"])

    def test_evaluator_failure_is_an_explicit_blocking_finding(self):
        for surface in ("weekly_brief", "knowledge_atlas"):
            with (
                self.subTest(surface=surface),
                patch(
                    "output.reader_value_quality._evaluate",
                    side_effect=RuntimeError("fixture failure"),
                ),
            ):
                report = evaluate_reader_report_quality(
                    {"surface": surface},
                    "",
                    policy_mode=READER_VALUE_BLOCKING_V2,
                    surface=surface,
                )
                validate_reader_report_quality(report)
                self.assertEqual(
                    [finding["code"] for finding in self._findings(report)],
                    ["evaluator.failed"],
                )
                with self.assertRaises(ReaderValueQualityError):
                    require_reader_report_quality(report)

    def test_closed_result_contract_rejects_forged_aggregates(self):
        valid = evaluate_reader_report_quality(
            self.brief_sidecar,
            self.brief_html,
            policy_mode=READER_VALUE_BLOCKING_V2,
            manifest=self.brief_manifest,
            surface="weekly_brief",
        )
        mutations = []

        unknown = copy.deepcopy(valid)
        unknown["unknown"] = True
        mutations.append(unknown)

        inconsistent = copy.deepcopy(valid)
        inconsistent["summary"]["critical_count"] = True
        mutations.append(inconsistent)

        all_not_applicable = copy.deepcopy(valid)
        for dimension in all_not_applicable["dimensions"]:
            dimension["status"] = "not_applicable"
            dimension["severity"] = "none"
            dimension["findings"] = []
        mutations.append(all_not_applicable)

        for mutation in mutations:
            with self.subTest(keys=sorted(mutation)):
                with self.assertRaises(ReaderQualityContractError):
                    validate_reader_report_quality(mutation)

    def test_evaluation_order_and_reader_warning_are_deterministic_and_safe(self):
        sidecar, html = self._w29_case("w29_brief_failure")
        first = evaluate_reader_report_quality(
            sidecar,
            html,
            policy_mode=READER_VALUE_WARN_ONLY_V1,
            surface="weekly_brief",
        )
        second = evaluate_reader_report_quality(
            copy.deepcopy(sidecar),
            html,
            policy_mode=READER_VALUE_WARN_ONLY_V1,
            surface="weekly_brief",
        )

        self.assertEqual(first, second)
        warning = format_reader_quality_warning([first])
        self.assertIsNotNone(warning)
        self.assertIn("недельный бриф", warning or "")
        self.assertNotIn("weekly_brief", warning or "")
        self.assertLessEqual(len(warning or ""), 500)




if __name__ == "__main__":
    unittest.main()
