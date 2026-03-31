import unittest
from unittest.mock import patch

import yaml

from output.signal_report import format_signal_report


class TestSignalReport(unittest.TestCase):
    def test_empty_posts_has_all_headers(self):
        report = format_signal_report([], settings=None)

        for header in (
            "## Strong Signals",
            "## Watch",
            "## Cultural",
            "## Ignored",
            "## Think Layer",
            "## Stats",
        ):
            self.assertIn(header, report)

    def test_strong_before_watch(self):
        posts = [
            {"id": 1, "content": "strong signal content", "signal_score": 0.9, "bucket": "strong", "routed_model": "claude-opus-4-6", "score_breakdown": "{}"},
            {"id": 2, "content": "watch signal content", "signal_score": 0.5, "bucket": "watch", "routed_model": "claude-sonnet-4-6", "score_breakdown": "{}"},
        ]

        report = format_signal_report(posts, settings=None)

        self.assertLess(report.index("## Strong Signals"), report.index("## Watch"))

    def test_ignored_shows_count_not_content(self):
        posts = [
            {"id": 1, "content": "secret content one", "signal_score": 0.1, "bucket": "noise", "routed_model": "claude-haiku-4-5-20251001", "score_breakdown": "{}"},
            {"id": 2, "content": "secret content two", "signal_score": 0.2, "bucket": "noise", "routed_model": "claude-haiku-4-5-20251001", "score_breakdown": "{}"},
            {"id": 3, "content": "secret content three", "signal_score": 0.3, "bucket": "noise", "routed_model": "claude-haiku-4-5-20251001", "score_breakdown": "{}"},
        ]

        report = format_signal_report(posts, settings=None)

        self.assertIn("3 posts", report)
        self.assertNotIn("secret content", report)

    def test_strong_entry_includes_score_and_model(self):
        posts = [
            {
                "id": 1,
                "content": "A strong post about agent workflows and inference optimization for production systems",
                "signal_score": 0.85,
                "bucket": "strong",
                "routed_model": "claude-opus-4-6",
                "score_breakdown": "{}",
            }
        ]

        report = format_signal_report(posts, settings=None)

        self.assertIn("[score=0.85]", report)
        self.assertIn("[model=claude-opus-4-6]", report)

    def test_strong_posts_sorted_descending(self):
        posts = [
            {"id": 1, "content": "lower priority strong", "signal_score": 0.71, "bucket": "strong", "routed_model": "m1", "score_breakdown": "{}"},
            {"id": 2, "content": "higher priority strong", "signal_score": 0.95, "bucket": "strong", "routed_model": "m2", "score_breakdown": "{}"},
        ]

        report = format_signal_report(posts, settings=None)

        self.assertLess(report.index("higher priority strong"), report.index("lower priority strong"))

    def test_project_relevance_section_shows_matches_above_threshold(self):
        posts = [
            {
                "id": 1,
                "content": "Multi tenant AI triage service FastAPI Redis cost control async",
                "signal_score": 0.85,
                "bucket": "strong",
                "routed_model": "claude-opus-4-6",
                "score_breakdown": "{}",
            }
        ]

        report = format_signal_report(posts, settings=None)

        self.assertIn("## Project Relevance", report)
        self.assertIn("[gdev-agent]", report)
        self.assertIn("(score=", report)

    def test_project_relevance_skips_section_when_projects_config_fails(self):
        posts = [
            {"id": 1, "content": "FastAPI async cost control", "signal_score": 0.85, "bucket": "strong", "routed_model": "m1", "score_breakdown": "{}"}
        ]

        with patch("output.signal_report.yaml.safe_load", side_effect=yaml.YAMLError("invalid yaml")):
            report = format_signal_report(posts, settings=None)

        self.assertNotIn("## Project Relevance", report)


if __name__ == "__main__":
    unittest.main()
