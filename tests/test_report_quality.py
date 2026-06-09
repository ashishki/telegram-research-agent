import sqlite3
import tempfile
import unittest
from pathlib import Path

from output.report_quality import (
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    WeeklyReportFacts,
    digest_has_project_insights,
    format_findings_for_notification,
    load_weekly_quality_facts,
    validate_artifact,
    validate_mvp_delivery_consistency,
    validate_weekly_artifact_paths,
    validate_weekly_artifacts,
)


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


if __name__ == "__main__":
    unittest.main()
