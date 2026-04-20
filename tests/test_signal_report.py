import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import yaml

from output.signal_report import _build_auto_watch_lines, format_signal_report


class TestSignalReport(unittest.TestCase):
    def test_empty_posts_has_all_headers(self):
        report = format_signal_report([], settings=None)

        for header in (
            "## Strong Signals",
            "## Decisions to Consider",
            "## Watch",
            "## Cultural",
            "## Ignored",
            "## Think Layer",
            "## Stats",
            "## What Changed",
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

    def test_strong_entry_includes_source_url_when_present(self):
        posts = [
            {
                "id": 1,
                "content": "A strong post about agent workflows and inference optimization for production systems",
                "signal_score": 0.85,
                "bucket": "strong",
                "routed_model": "claude-opus-4-6",
                "score_breakdown": "{}",
                "message_url": "https://t.me/testchan/123",
            }
        ]

        report = format_signal_report(posts, settings=None)

        self.assertIn("| Source: https://t.me/testchan/123", report)

    def test_strong_entry_omits_source_url_when_missing(self):
        posts = [
            {
                "id": 1,
                "content": "A strong post without source url in the payload",
                "signal_score": 0.85,
                "bucket": "strong",
                "routed_model": "claude-opus-4-6",
                "score_breakdown": "{}",
                "message_url": "",
            }
        ]

        report = format_signal_report(posts, settings=None)

        self.assertNotIn("| Source:", report)

    def test_project_action_queue_groups_matches_by_project(self):
        posts = [
            {
                "id": 1,
                "content": "Multi tenant AI triage service FastAPI Redis cost control async",
                "signal_score": 0.85,
                "bucket": "strong",
                "routed_model": "claude-opus-4-6",
                "score_breakdown": "{}",
            }
            ,
            {
                "id": 2,
                "content": "Telegram digest quality insight generation clustering accuracy delivery UX for weekly research workflow",
                "signal_score": 0.72,
                "bucket": "watch",
                "routed_model": "claude-sonnet-4-6",
                "score_breakdown": "{}",
                "message_url": "https://t.me/test/2",
            }
        ]

        report = format_signal_report(posts, settings=None)

        self.assertIn("## Project Action Queue", report)
        self.assertIn("**gdev-agent**", report)
        self.assertIn("**telegram-research-agent**", report)
        self.assertIn("[relevance=", report)

    def test_project_relevance_skips_section_when_projects_config_fails(self):
        posts = [
            {"id": 1, "content": "FastAPI async cost control", "signal_score": 0.85, "bucket": "strong", "routed_model": "m1", "score_breakdown": "{}"}
        ]

        with patch("output.signal_report.yaml.safe_load", side_effect=yaml.YAMLError("invalid yaml")):
            report = format_signal_report(posts, settings=None)

        self.assertNotIn("## Project Action Queue", report)

    def test_what_changed_uses_previous_quality_metrics_row(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE quality_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        week_label TEXT NOT NULL UNIQUE,
                        computed_at TEXT NOT NULL,
                        total_posts INTEGER NOT NULL DEFAULT 0,
                        strong_count INTEGER NOT NULL DEFAULT 0,
                        watch_count INTEGER NOT NULL DEFAULT 0,
                        cultural_count INTEGER NOT NULL DEFAULT 0,
                        noise_count INTEGER NOT NULL DEFAULT 0,
                        avg_signal_score REAL,
                        project_match_count INTEGER NOT NULL DEFAULT 0,
                        output_word_count INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO quality_metrics (
                        week_label, computed_at, strong_count, watch_count, noise_count
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    ("2026-W13", "2026-03-24T00:00:00Z", 3, 1, 4),
                )
                connection.commit()

            posts = [
                {"id": 1, "content": "strong item", "signal_score": 0.9, "bucket": "strong", "routed_model": "m1", "score_breakdown": "{}"},
                {"id": 2, "content": "strong item two", "signal_score": 0.88, "bucket": "strong", "routed_model": "m1", "score_breakdown": "{}"},
                {"id": 3, "content": "watch item one", "signal_score": 0.55, "bucket": "watch", "routed_model": "m2", "score_breakdown": "{}"},
                {"id": 4, "content": "watch item two", "signal_score": 0.52, "bucket": "watch", "routed_model": "m2", "score_breakdown": "{}"},
                {"id": 5, "content": "noise item", "signal_score": 0.05, "bucket": "noise", "routed_model": "m3", "score_breakdown": "{}"},
            ]

            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                report = format_signal_report(posts, settings=None)

            self.assertIn("## What Changed", report)
            self.assertIn("strong: 2 (was 3, -1)", report)
            self.assertIn("watch: 2 (was 1, +1)", report)
            self.assertIn("noise: 1 (was 4, -3)", report)
        finally:
            os.unlink(db_path)

    def test_decisions_section_uses_strong_long_post(self):
        long_content = " ".join(f"word{i}" for i in range(90))
        posts = [
            {
                "id": 1,
                "content": long_content,
                "signal_score": 0.92,
                "bucket": "strong",
                "routed_model": "claude-opus-4-6",
                "score_breakdown": "{}",
                "word_count": 90,
            }
        ]

        report = format_signal_report(posts, settings=None)

        self.assertIn("## Decisions to Consider", report)
        self.assertIn("- Consider:", report)

    def test_reader_mode_excludes_project_insight_posts_from_additional_signals(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            with sqlite3.connect(db_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE user_post_tags (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        post_id INTEGER NOT NULL,
                        tag TEXT NOT NULL,
                        note TEXT,
                        recorded_at TEXT NOT NULL
                    );
                    """
                )
                connection.commit()

            posts = [
                {
                    "id": 1,
                    "content": "Project security signal",
                    "signal_score": 0.81,
                    "bucket": "watch",
                    "routed_model": "m1",
                    "score_breakdown": "{}",
                    "message_url": "https://t.me/test/1",
                    "channel_username": "@test",
                },
                {
                    "id": 2,
                    "content": "Secondary workflow signal",
                    "signal_score": 0.74,
                    "bucket": "watch",
                    "routed_model": "m2",
                    "score_breakdown": "{}",
                    "message_url": "https://t.me/test/2",
                    "channel_username": "@test",
                },
            ]

            class _Settings:
                def __init__(self, path: str):
                    self.db_path = path

            judged = {
                1: {
                    "include": True,
                    "category": "interesting",
                    "title": "Project-only signal",
                    "key_takeaway": "Important for one project.",
                    "why_now": "Needs action now.",
                    "project_name": "gdev-agent",
                    "project_application": "Add security guardrails.",
                    "confidence": 0.9,
                },
                2: {
                    "include": True,
                    "category": "interesting",
                    "title": "Additional signal",
                    "key_takeaway": "Separate item.",
                    "why_now": "Still useful.",
                    "project_name": "",
                    "project_application": "",
                    "confidence": 0.7,
                },
            }

            with patch("output.signal_report._load_projects", return_value=[{"name": "gdev-agent"}]):
                with patch("output.signal_report._load_profile", return_value={}):
                    with patch("output.signal_report.judge_recent_posts", return_value=judged):
                        report = format_signal_report(posts, settings=_Settings(db_path), reader_mode=True)

            self.assertIn("## Project Insights", report)
            self.assertIn("## Additional Signals", report)
            self.assertEqual(report.count("**Project-only signal**"), 1)
            self.assertEqual(report.count("**Additional signal**"), 1)
        finally:
            os.unlink(db_path)

    def test_auto_watch_lines_include_interesting_items_with_false_include_and_high_confidence(self):
        posts = [
            {
                "id": 7,
                "content": "Useful workflow signal",
                "message_url": "https://t.me/test/7",
                "channel_username": "@test",
            }
        ]
        judged_by_post = {
            7: {
                "include": False,
                "category": "interesting",
                "title": "Interesting signal",
                "key_takeaway": "Worth tracking.",
                "why_now": "Useful soon.",
                "project_application": "",
                "confidence": 0.7,
            }
        }

        lines = _build_auto_watch_lines(posts, tag_details_by_post={}, judged_by_post=judged_by_post)

        self.assertNotEqual(["No additional high-confidence auto-selected signals this week."], lines)
        self.assertTrue(any("Interesting signal" in line for line in lines))

    def test_auto_watch_lines_skip_interesting_items_with_false_include_and_low_confidence(self):
        posts = [
            {
                "id": 8,
                "content": "Weak workflow signal",
                "message_url": "https://t.me/test/8",
                "channel_username": "@test",
            }
        ]
        judged_by_post = {
            8: {
                "include": False,
                "category": "interesting",
                "title": "Weak signal",
                "key_takeaway": "Probably not enough.",
                "why_now": "Not urgent.",
                "project_application": "",
                "confidence": 0.5,
            }
        }

        lines = _build_auto_watch_lines(posts, tag_details_by_post={}, judged_by_post=judged_by_post)

        self.assertEqual(["No additional high-confidence auto-selected signals this week."], lines)

    def test_reader_mode_uses_settings_db_path_for_what_changed_baseline(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            with sqlite3.connect(db_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE quality_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        week_label TEXT NOT NULL UNIQUE,
                        computed_at TEXT NOT NULL,
                        total_posts INTEGER NOT NULL DEFAULT 0,
                        strong_count INTEGER NOT NULL DEFAULT 0,
                        watch_count INTEGER NOT NULL DEFAULT 0,
                        cultural_count INTEGER NOT NULL DEFAULT 0,
                        noise_count INTEGER NOT NULL DEFAULT 0,
                        avg_signal_score REAL,
                        project_match_count INTEGER NOT NULL DEFAULT 0,
                        output_word_count INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE TABLE user_post_tags (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        post_id INTEGER NOT NULL,
                        tag TEXT NOT NULL,
                        note TEXT,
                        recorded_at TEXT NOT NULL
                    );
                    """
                )
                connection.execute(
                    """
                    INSERT INTO quality_metrics (
                        week_label, computed_at, strong_count, watch_count, noise_count
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    ("2026-W13", "2026-03-24T00:00:00Z", 2, 1, 3),
                )
                connection.commit()

            class _Settings:
                def __init__(self, path: str):
                    self.db_path = path

            with patch("output.signal_report._load_profile", return_value={}):
                with patch("output.signal_report._load_projects", return_value=[]):
                    with patch("output.signal_report.judge_recent_posts", return_value={}):
                        report = format_signal_report([], settings=_Settings(db_path), reader_mode=True)

            self.assertIn("## What Changed", report)
            self.assertIn("strong: 0 (was 2, -2)", report)
            self.assertIn("watch: 0 (was 1, -1)", report)
            self.assertIn("noise: 0 (was 3, -3)", report)
            self.assertNotIn("No comparison baseline available.", report)
        finally:
            os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()
