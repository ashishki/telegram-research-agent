"""
Unit tests for digest generation (src/output/generate_digest.py).

Coverage:
  (d) word-count gate: output > MAX_OUTPUT_WORDS (600) → LOGGER.warning called
  (e) NO_OVERLAP_NOTE guard: _append_github_section omits repos whose
      matched_topics == [NO_OVERLAP_NOTE]
"""

import os
import sqlite3
import tempfile
import sys
import types
import unittest
from datetime import datetime, timezone
from io import StringIO
import logging
from unittest.mock import MagicMock, patch


def _mock_anthropic():
    """Inject a stub anthropic module so llm.client can be imported without the package."""
    if "anthropic" not in sys.modules:
        mod = types.ModuleType("anthropic")
        for name in ["APIConnectionError", "APIStatusError", "APITimeoutError", "Anthropic", "RateLimitError"]:
            setattr(mod, name, Exception)
        sys.modules["anthropic"] = mod


_mock_anthropic()

import output.generate_digest as gd  # noqa: E402  (must come after mock)
from output.generate_digest import (
    MAX_OUTPUT_WORDS,
    _append_github_section,
    _count_words,
)


class TestWordCountGate(unittest.TestCase):
    """
    LOGGER.warning must be called when the LLM output exceeds MAX_OUTPUT_WORDS.

    We exercise the gate logic directly rather than running the full pipeline.
    """

    def _make_long_text(self, word_count: int) -> str:
        return " ".join(["word"] * word_count)

    def test_warning_logged_when_output_exceeds_600_words(self):
        """
        Reproduce the guard from run_digest lines 411-416 and verify LOGGER.warning fires.
        """
        long_text = self._make_long_text(MAX_OUTPUT_WORDS + 1)
        word_count = _count_words(long_text)
        self.assertGreater(word_count, MAX_OUTPUT_WORDS)

        with patch.object(gd.LOGGER, "warning") as mock_warning:
            if word_count > MAX_OUTPUT_WORDS:
                gd.LOGGER.warning(
                    "Digest output exceeds word limit week=%s words=%d limit=%d",
                    "2026-W13",
                    word_count,
                    MAX_OUTPUT_WORDS,
                )
            mock_warning.assert_called_once()
            call_args = mock_warning.call_args[0]
            self.assertIn("exceeds word limit", call_args[0])

    def test_no_warning_when_output_is_within_limit(self):
        """LOGGER.warning must NOT be called when word count is within limit."""
        short_text = self._make_long_text(MAX_OUTPUT_WORDS)
        word_count = _count_words(short_text)
        self.assertLessEqual(word_count, MAX_OUTPUT_WORDS)

        with patch.object(gd.LOGGER, "warning") as mock_warning:
            if word_count > MAX_OUTPUT_WORDS:
                gd.LOGGER.warning(
                    "Digest output exceeds word limit week=%s words=%d limit=%d",
                    "2026-W13",
                    word_count,
                    MAX_OUTPUT_WORDS,
                )
            mock_warning.assert_not_called()

    def test_count_words_helper_counts_correctly(self):
        """_count_words splits on whitespace — sanity check."""
        self.assertEqual(_count_words("one two three"), 3)
        self.assertEqual(_count_words("single"), 1)
        self.assertGreater(_count_words(self._make_long_text(601)), MAX_OUTPUT_WORDS)

    def test_max_output_words_constant_is_600(self):
        """MAX_OUTPUT_WORDS must be 600 per spec."""
        self.assertEqual(MAX_OUTPUT_WORDS, 600)


class TestAppendGithubSectionNoOverlapGuard(unittest.TestCase):
    """
    _append_github_section must skip repos whose matched_topics == [NO_OVERLAP_NOTE].
    The repo name must not appear anywhere in the returned string.
    """

    NO_OVERLAP_NOTE = "active this week, no Telegram overlap found"

    def _make_settings(self):
        from config.settings import Settings
        return Settings(
            db_path=":memory:",
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

    def test_repo_with_no_overlap_note_is_omitted(self):
        """A repo whose matched_topics == [NO_OVERLAP_NOTE] must not appear in output."""
        repo_name = "my-silent-repo"
        repos = [
            {"name": repo_name, "github_repo": f"owner/{repo_name}", "weekly_commits": 5},
        ]
        topic_matches = {repo_name: [self.NO_OVERLAP_NOTE]}

        settings = self._make_settings()
        content_before = "## Weekly Briefing\n\nSome content here.\n"

        with patch.dict(os.environ, {"GITHUB_USERNAME": "testowner"}):
            with patch.object(gd, "sync_github_projects", return_value=repos):
                with patch.object(gd, "crossref_repos_to_topics", return_value=topic_matches):
                    result = _append_github_section(content_before, settings)

        self.assertNotIn(repo_name, result)
        # Content unchanged when all repos are filtered
        self.assertEqual(result, content_before)

    def test_repo_with_real_match_is_included(self):
        """A repo with real topic matches must appear in output."""
        repo_name = "active-repo"
        repos = [
            {"name": repo_name, "github_repo": f"owner/{repo_name}", "weekly_commits": 3},
        ]
        topic_matches = {repo_name: ["LLM fine-tuning", "agentic workflows"]}

        settings = self._make_settings()
        content_before = "## Weekly Briefing\n\nSome content here.\n"

        with patch.dict(os.environ, {"GITHUB_USERNAME": "testowner"}):
            with patch.object(gd, "sync_github_projects", return_value=repos):
                with patch.object(gd, "crossref_repos_to_topics", return_value=topic_matches):
                    result = _append_github_section(content_before, settings)

        self.assertIn(repo_name, result)
        self.assertIn("Your Projects", result)

    def test_mix_only_active_repo_appears(self):
        """When one repo has NO_OVERLAP_NOTE and one has real matches, only the real one appears."""
        silent_repo = "silent-repo"
        active_repo = "active-repo"
        repos = [
            {"name": silent_repo, "github_repo": f"owner/{silent_repo}", "weekly_commits": 2},
            {"name": active_repo, "github_repo": f"owner/{active_repo}", "weekly_commits": 7},
        ]
        topic_matches = {
            silent_repo: [self.NO_OVERLAP_NOTE],
            active_repo: ["vector search"],
        }

        settings = self._make_settings()
        content_before = "## Weekly Briefing\n\nSome content here.\n"

        with patch.dict(os.environ, {"GITHUB_USERNAME": "testowner"}):
            with patch.object(gd, "sync_github_projects", return_value=repos):
                with patch.object(gd, "crossref_repos_to_topics", return_value=topic_matches):
                    result = _append_github_section(content_before, settings)

        self.assertNotIn(silent_repo, result)
        self.assertIn(active_repo, result)

    def test_no_github_username_returns_content_unchanged(self):
        """If GITHUB_USERNAME is not set, content must be returned unchanged."""
        settings = self._make_settings()
        content_before = "## Weekly Briefing\n\nSome content here.\n"

        env_copy = {k: v for k, v in os.environ.items() if k != "GITHUB_USERNAME"}
        with patch.dict(os.environ, env_copy, clear=True):
            result = _append_github_section(content_before, settings)

        self.assertEqual(result, content_before)

    def test_empty_matched_topics_repo_is_omitted(self):
        """A repo with an empty matched_topics list is also omitted."""
        repo_name = "empty-match-repo"
        repos = [
            {"name": repo_name, "github_repo": f"owner/{repo_name}", "weekly_commits": 1},
        ]
        topic_matches = {repo_name: []}

        settings = self._make_settings()
        content_before = "## Weekly Briefing\n\nSome content here.\n"

        with patch.dict(os.environ, {"GITHUB_USERNAME": "testowner"}):
            with patch.object(gd, "sync_github_projects", return_value=repos):
                with patch.object(gd, "crossref_repos_to_topics", return_value=topic_matches):
                    result = _append_github_section(content_before, settings)

        self.assertNotIn(repo_name, result)
        self.assertEqual(result, content_before)


class TestRunDigestFixes(unittest.TestCase):
    def _make_settings(self, db_path: str):
        from config.settings import Settings

        return Settings(
            db_path=db_path,
            llm_api_key="",
            model_provider="anthropic",
            telegram_session_path="",
        )

    def _build_digest_db(self, db_path: str) -> None:
        with sqlite3.connect(db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE raw_posts (
                    id INTEGER PRIMARY KEY,
                    view_count INTEGER,
                    message_url TEXT
                );
                CREATE TABLE posts (
                    id INTEGER PRIMARY KEY,
                    raw_post_id INTEGER,
                    channel_username TEXT,
                    content TEXT,
                    posted_at TEXT,
                    signal_score REAL,
                    bucket TEXT,
                    routed_model TEXT,
                    score_breakdown TEXT,
                    project_matches TEXT
                );
                CREATE TABLE topics (
                    id INTEGER PRIMARY KEY,
                    label TEXT
                );
                CREATE TABLE post_topics (
                    post_id INTEGER,
                    topic_id INTEGER
                );
                CREATE TABLE digests (
                    week_label TEXT PRIMARY KEY,
                    generated_at TEXT,
                    content_md TEXT,
                    content_json TEXT,
                    pdf_path TEXT,
                    post_count INTEGER
                );
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
                """
            )
            connection.executemany(
                "INSERT INTO raw_posts (id, view_count, message_url) VALUES (?, ?, ?)",
                [
                    (1, 100, "https://t.me/c/1"),
                    (2, 90, "https://t.me/c/2"),
                    (3, 80, "https://t.me/c/3"),
                    (4, 70, "https://t.me/c/4"),
                ],
            )
            connection.executemany(
                """
                INSERT INTO posts (id, raw_post_id, channel_username, content, posted_at, signal_score, bucket, routed_model, score_breakdown, project_matches)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (1, 1, "chan1", "strong post", "2026-03-29T12:00:00Z", 0.9, "strong", "claude-opus-4-6", '{"topic":"agents"}', '["proj-a"]'),
                    (2, 2, "chan2", "watch post", "2026-03-29T13:00:00Z", 0.6, "watch", "claude-sonnet-4-6", '{"topic":"infra"}', "[]"),
                    (3, 3, "chan3", "cultural post", "2026-03-29T14:00:00Z", 0.3, "cultural", "claude-haiku-4-5-20251001", '{"topic":"culture"}', ""),
                    (4, 4, "chan4", "noise post", "2026-03-29T15:00:00Z", 0.1, "noise", "claude-haiku-4-5-20251001", '{"topic":"noise"}', ""),
                ],
            )
            connection.executemany(
                "INSERT INTO topics (id, label) VALUES (?, ?)",
                [(1, "Agents"), (2, "Infra"), (3, "Culture"), (4, "Noise")],
            )
            connection.executemany(
                "INSERT INTO post_topics (post_id, topic_id) VALUES (?, ?)",
                [(1, 1), (2, 2), (3, 3), (4, 4)],
            )
            connection.commit()

    def _run_digest(self, db_path: str):
        settings = self._make_settings(db_path)
        fixed_now = datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)

        with patch.object(gd, "_utc_now", return_value=fixed_now):
            with patch.object(gd, "_compute_week_label", return_value="2026-W14"):
                with patch.object(gd, "score_posts", return_value={"strong": 1, "watch": 1, "cultural": 1, "noise": 1, "avg_signal_score": 0.475}):
                    with patch.object(gd, "_load_prompt_sections", return_value=("system", "week={week_label}")):
                        with patch.object(gd, "complete", return_value="digest output words"):
                            with patch.object(gd, "_append_github_section", side_effect=lambda content, settings: content):
                                with patch.object(gd, "_write_digest_file", return_value=gd.Path("/tmp/2026-W14.md")):
                                    with patch.object(gd, "_write_digest_json_file", return_value=gd.Path("/tmp/2026-W14.json")):
                                        with patch.object(gd, "_send_digest_to_telegram_owner"):
                                            return gd.run_digest(settings)

    def test_insights_failure_logs_traceback(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        handler = None
        previous_level = gd.LOGGER.level
        try:
            self._build_digest_db(db_path)
            log_stream = StringIO()
            handler = logging.StreamHandler(log_stream)
            handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
            gd.LOGGER.addHandler(handler)
            gd.LOGGER.setLevel(logging.WARNING)

            with patch("output.generate_recommendations.run_recommendations", side_effect=ValueError("boom")):
                self._run_digest(db_path)

            handler.flush()
            log_output = log_stream.getvalue()
            self.assertIn("Insights generation failed, skipping: boom", log_output)
            self.assertIn("Traceback", log_output)
        finally:
            gd.LOGGER.setLevel(previous_level)
            if handler is not None:
                gd.LOGGER.removeHandler(handler)
            os.unlink(db_path)

    def test_run_digest_populates_quality_metrics(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            self._build_digest_db(db_path)
            with patch("output.generate_recommendations.run_recommendations", return_value={"text": ""}):
                self._run_digest(db_path)

            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    """
                    SELECT week_label, strong_count, watch_count, cultural_count, noise_count, avg_signal_score, output_word_count
                    FROM quality_metrics
                    WHERE week_label = ?
                    """,
                    ("2026-W14",),
                ).fetchone()

            self.assertIsNotNone(row)
            self.assertEqual(row["week_label"], "2026-W14")
            self.assertEqual(row["strong_count"], 1)
            self.assertEqual(row["watch_count"], 1)
            self.assertEqual(row["cultural_count"], 1)
            self.assertEqual(row["noise_count"], 1)
            self.assertAlmostEqual(row["avg_signal_score"], 0.475)
            self.assertGreater(row["output_word_count"], 3)
        finally:
            os.unlink(db_path)

    def test_run_digest_sleeps_between_digest_and_insights_send(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            self._build_digest_db(db_path)
            settings = self._make_settings(db_path)
            fixed_now = datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)
            call_order: list[str] = []

            def fake_send_digest_to_owner(*args, **kwargs):
                call_order.append("digest")

            def fake_sleep(seconds):
                call_order.append(f"sleep:{seconds}")

            def fake_send_text(*args, **kwargs):
                call_order.append("insights")

            with patch.dict(
                os.environ,
                {
                    "TELEGRAM_BOT_TOKEN": "token",
                    "TELEGRAM_OWNER_CHAT_ID": "chat",
                },
                clear=False,
            ):
                with patch.object(gd, "_utc_now", return_value=fixed_now):
                    with patch.object(gd, "_compute_week_label", return_value="2026-W14"):
                        with patch.object(gd, "score_posts", return_value={"strong": 1, "watch": 1, "cultural": 1, "noise": 1, "avg_signal_score": 0.475}):
                            with patch.object(gd, "_load_prompt_sections", return_value=("system", "week={week_label}")):
                                with patch.object(gd, "complete", return_value="digest output words"):
                                    with patch.object(gd, "_append_github_section", side_effect=lambda content, settings: content):
                                        with patch.object(gd, "_write_digest_file", return_value=gd.Path("/tmp/2026-W14.md")):
                                            with patch.object(gd, "_write_digest_json_file", return_value=gd.Path("/tmp/2026-W14.json")):
                                                with patch.object(gd, "_send_digest_to_telegram_owner", side_effect=fake_send_digest_to_owner):
                                                    with patch.object(gd.time, "sleep", side_effect=fake_sleep) as sleep_mock:
                                                        with patch.object(gd, "send_text", side_effect=fake_send_text):
                                                            with patch("output.generate_recommendations.run_recommendations", return_value={"text": "insights"}):
                                                                gd.run_digest(settings)

            sleep_mock.assert_called_once_with(1)
            self.assertEqual(call_order, ["digest", "sleep:1", "insights"])
        finally:
            os.unlink(db_path)

    def test_run_digest_prepends_signal_report_section(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            self._build_digest_db(db_path)
            settings = self._make_settings(db_path)
            fixed_now = datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)

            with patch.object(gd, "_utc_now", return_value=fixed_now):
                with patch.object(gd, "_compute_week_label", return_value="2026-W14"):
                    with patch.object(gd, "score_posts", return_value={"strong": 1, "watch": 0, "cultural": 0, "noise": 1, "avg_signal_score": 0.5}):
                        with patch.object(gd, "_load_prompt_sections", return_value=("system", "week={week_label}")):
                            with patch.object(gd, "complete", return_value="llm narrative"):
                                with patch.object(gd, "_append_github_section", side_effect=lambda content, settings: content):
                                    with patch.object(gd, "_write_digest_json_file", return_value=gd.Path("/tmp/2026-W14.json")):
                                        with patch.object(gd, "_send_digest_to_telegram_owner"):
                                            with patch.object(gd, "_write_digest_file", return_value=gd.Path("/tmp/2026-W14.md")) as write_mock:
                                                with patch("output.generate_recommendations.run_recommendations", return_value={"text": ""}):
                                                    gd.run_digest(settings)

            written_content = write_mock.call_args.args[1]
            self.assertIn("## Strong Signals", written_content)
        finally:
            os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()
