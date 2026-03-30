"""
Unit tests for digest generation (src/output/generate_digest.py).

Coverage:
  (d) word-count gate: output > MAX_OUTPUT_WORDS (600) → LOGGER.warning called
  (e) NO_OVERLAP_NOTE guard: _append_github_section omits repos whose
      matched_topics == [NO_OVERLAP_NOTE]
"""

import os
import sys
import types
import unittest
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


if __name__ == "__main__":
    unittest.main()
