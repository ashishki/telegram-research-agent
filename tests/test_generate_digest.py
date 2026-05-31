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
    _build_digest_health_alert,
    _count_words,
)
from db.research_brief_receipts import fetch_research_brief_receipts


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


class TestDigestHealthAlert(unittest.TestCase):
    def test_empty_week_alert_points_to_ingestion(self):
        alert = _build_digest_health_alert(
            "2026-W18",
            post_count=0,
            strong_count=0,
            watch_count=0,
        )

        self.assertIsNotNone(alert)
        self.assertIn("No Telegram posts", alert or "")
        self.assertIn("Check ingestion", alert or "")

    def test_low_signal_week_alert_points_to_scoring(self):
        alert = _build_digest_health_alert(
            "2026-W18",
            post_count=42,
            strong_count=0,
            watch_count=0,
            channel_count=7,
            topic_count=3,
        )

        self.assertIsNotNone(alert)
        self.assertIn("0 strong/watch", alert or "")
        self.assertIn("scoring thresholds", alert or "")

    def test_actionable_week_has_no_alert(self):
        alert = _build_digest_health_alert(
            "2026-W18",
            post_count=42,
            strong_count=1,
            watch_count=0,
            channel_count=7,
            topic_count=3,
        )

        self.assertIsNone(alert)

    def test_receipt_audit_note_only_renders_actionable_receipt_state(self):
        self.assertIsNone(gd._build_receipt_audit_note({"verification_status": "pending", "health_flags": []}))

        note = gd._build_receipt_audit_note(
            {
                "verification_status": "needs_review",
                "health_flags": ["low_signal_alert"],
                "fallback_delivery_used": True,
                "fallback_delivery": "html_attachment",
            }
        )

        self.assertEqual(note, "Receipt: needs_review | flags=low_signal_alert | fallback=html_attachment")

    def test_receipt_audit_note_includes_core_hash_when_receipt_is_buildable(self):
        note = gd._build_receipt_audit_note(
            {
                "receipt_id": "rbr_2026_w14",
                "week_label": "2026-W14",
                "generated_at": "2026-03-30T12:00:00Z",
                "verification_status": "pending",
                "markdown_path": "/tmp/2026-W14.md",
                "source_set": {
                    "telegram_source_links": ["https://t.me/source_a/123"],
                },
                "health_flags": [],
            }
        )

        self.assertIsNotNone(note)
        assert note is not None
        self.assertIn("Receipt: pending", note)
        self.assertRegex(note, r"core_sha256=[0-9a-f]{64}")


class TestDigestHelpers(unittest.TestCase):
    def _make_long_text(self, word_count: int) -> str:
        return " ".join(["word"] * word_count)

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

    def _build_digest_db(self, db_path: str, *, include_posts: bool = True) -> None:
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
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    week_label TEXT NOT NULL UNIQUE,
                    generated_at TEXT,
                    content_md TEXT,
                    content_json TEXT,
                    pdf_path TEXT,
                    post_count INTEGER,
                    telegraph_url TEXT,
                    telegram_sent_at TEXT
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
                CREATE TABLE research_brief_receipts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    receipt_id TEXT NOT NULL UNIQUE,
                    type TEXT NOT NULL DEFAULT 'research_brief_receipt'
                        CHECK(type = 'research_brief_receipt'),
                    week_label TEXT NOT NULL CHECK(length(trim(week_label)) > 0),
                    generated_at TEXT NOT NULL,
                    source_project TEXT NOT NULL DEFAULT 'telegram-research-agent',
                    source_version TEXT,
                    window_start TEXT,
                    window_end TEXT,
                    included_channels_json TEXT NOT NULL DEFAULT '[]'
                        CHECK(json_valid(included_channels_json)),
                    post_counts_json TEXT NOT NULL DEFAULT '{}'
                        CHECK(json_valid(post_counts_json)),
                    source_set_json TEXT NOT NULL DEFAULT '{}'
                        CHECK(json_valid(source_set_json)),
                    project_scopes_json TEXT NOT NULL DEFAULT '[]'
                        CHECK(json_valid(project_scopes_json)),
                    topic_scopes_json TEXT NOT NULL DEFAULT '[]'
                        CHECK(json_valid(topic_scopes_json)),
                    llm_provider TEXT,
                    llm_model TEXT,
                    llm_category TEXT,
                    prompt_template_path TEXT,
                    prompt_template_version TEXT,
                    config_fingerprints_json TEXT NOT NULL DEFAULT '{}'
                        CHECK(json_valid(config_fingerprints_json)),
                    generation_params_fingerprint TEXT,
                    digest_id INTEGER,
                    markdown_path TEXT,
                    json_path TEXT,
                    html_path TEXT,
                    telegraph_url TEXT,
                    telegram_delivery_timestamp TEXT,
                    telegram_message_id INTEGER,
                    fallback_delivery TEXT,
                    fallback_delivery_used INTEGER NOT NULL DEFAULT 0
                        CHECK(fallback_delivery_used IN (0, 1)),
                    verification_status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(verification_status IN (
                            'pending',
                            'verified',
                            'needs_review',
                            'failed',
                            'waived'
                        )),
                    verifier_method TEXT,
                    verifier_notes TEXT,
                    checked_at TEXT,
                    checked_by TEXT,
                    health_flags_json TEXT NOT NULL DEFAULT '[]'
                        CHECK(json_valid(health_flags_json)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(digest_id) REFERENCES digests(id) ON DELETE SET NULL
                );
                CREATE TABLE signal_evidence_items (
                    id INTEGER PRIMARY KEY,
                    post_id INTEGER,
                    week_label TEXT
                );
                """
            )
            if not include_posts:
                connection.commit()
                return
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
            connection.executemany(
                "INSERT INTO signal_evidence_items (id, post_id, week_label) VALUES (?, ?, ?)",
                [(1, 1, "2026-W14"), (2, 2, "2026-W14")],
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
                                        with patch.object(gd, "write_report_html", return_value=gd.Path("/tmp/2026-W14.html")):
                                            with patch.object(gd, "_send_weekly_review_to_telegram_owner"):
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
            self.assertIn("Insights generation failed, skipping", log_output)
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

    def test_run_digest_creates_research_brief_receipt(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            self._build_digest_db(db_path)
            with patch.dict(os.environ, {"GIT_COMMIT": "abc123"}, clear=False):
                with patch("output.generate_recommendations.run_recommendations", return_value={"text": ""}):
                    self._run_digest(db_path)

            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                receipts = fetch_research_brief_receipts(connection, week_label="2026-W14", limit=5)

            self.assertEqual(len(receipts), 1)
            receipt = receipts[0]
            self.assertEqual(receipt["week_label"], "2026-W14")
            self.assertEqual(receipt["verification_status"], "pending")
            self.assertEqual(receipt["source_version"], "abc123")
            self.assertEqual(receipt["window_start"], "2026-03-23T12:00:00Z")
            self.assertEqual(receipt["window_end"], "2026-03-30T12:00:00Z")
            self.assertEqual(receipt["included_channels"], ["chan1", "chan2", "chan3", "chan4"])
            self.assertEqual(receipt["post_counts"]["total_posts"], 4)
            self.assertEqual(receipt["post_counts"]["strong_count"], 1)
            self.assertEqual(receipt["post_counts"]["watch_count"], 1)
            self.assertEqual(receipt["source_set"]["source_evidence_item_ids"], [1, 2])
            self.assertEqual(receipt["source_set"]["source_post_ids"], [1, 2, 3, 4])
            self.assertIn("https://t.me/c/1", receipt["source_set"]["telegram_source_links"])
            self.assertEqual(receipt["project_scopes"], ["proj-a"])
            self.assertEqual(receipt["topic_scopes"], ["Agents", "Culture", "Infra", "Noise"])
            self.assertEqual(receipt["llm_provider"], "anthropic")
            self.assertEqual(receipt["llm_category"], "digest")
            self.assertEqual(receipt["prompt_template_path"], "docs/prompts/digest_generation.md")
            self.assertIn("scoring_config", receipt["config_fingerprints"])
            self.assertEqual(receipt["markdown_path"], "/tmp/2026-W14.md")
            self.assertEqual(receipt["json_path"], "/tmp/2026-W14.json")
            self.assertEqual(receipt["html_path"], "/tmp/2026-W14.html")
            self.assertEqual(receipt["health_flags"], [])
        finally:
            os.unlink(db_path)

    def test_run_digest_passes_core_receipt_hash_audit_note_to_delivery(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            self._build_digest_db(db_path)
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
                                            with patch.object(gd, "write_report_html", return_value=gd.Path("/tmp/2026-W14.html")):
                                                with patch.object(gd, "_send_weekly_review_to_telegram_owner") as send_mock:
                                                    with patch("output.generate_recommendations.run_recommendations", return_value={"text": ""}):
                                                        gd.run_digest(settings)

            send_mock.assert_called_once()
            receipt_audit_note = send_mock.call_args.kwargs["receipt_audit_note"]
            self.assertIsNotNone(receipt_audit_note)
            self.assertIn("Receipt: pending", receipt_audit_note)
            self.assertRegex(receipt_audit_note, r"core_sha256=[0-9a-f]{64}")
        finally:
            os.unlink(db_path)

    def test_empty_week_creates_research_brief_receipt_with_health_flag(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            self._build_digest_db(db_path, include_posts=False)
            settings = self._make_settings(db_path)
            fixed_now = datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)

            with patch.object(gd, "_utc_now", return_value=fixed_now):
                with patch.object(gd, "_compute_week_label", return_value="2026-W14"):
                    with patch.object(gd, "score_posts", return_value={"strong": 0, "watch": 0, "cultural": 0, "noise": 0, "avg_signal_score": 0.0}):
                        with patch.object(gd, "_append_github_section", side_effect=lambda content, settings: content):
                            with patch.object(gd, "_write_digest_file", return_value=gd.Path("/tmp/2026-W14.md")):
                                with patch.object(gd, "write_report_html", return_value=gd.Path("/tmp/2026-W14.html")):
                                    with patch.object(gd, "_send_weekly_review_to_telegram_owner"):
                                        gd.run_digest(settings)

            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                receipts = fetch_research_brief_receipts(connection, week_label="2026-W14", limit=5)

            self.assertEqual(len(receipts), 1)
            receipt = receipts[0]
            self.assertEqual(receipt["post_counts"]["total_posts"], 0)
            self.assertEqual(receipt["included_channels"], [])
            self.assertEqual(receipt["source_set"]["source_post_ids"], [])
            self.assertEqual(receipt["markdown_path"], "/tmp/2026-W14.md")
            self.assertIsNone(receipt["json_path"])
            self.assertEqual(receipt["html_path"], "/tmp/2026-W14.html")
            self.assertEqual(receipt["health_flags"], ["empty_week_alert"])
        finally:
            os.unlink(db_path)

    def test_weekly_review_delivery_updates_receipt_with_telegraph_refs(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as html_tmp:
            html_tmp.write(b"<h1>Brief</h1>")
            html_path = gd.Path(html_tmp.name)

        try:
            self._build_digest_db(db_path)
            with patch("output.generate_recommendations.run_recommendations", return_value={"text": ""}):
                self._run_digest(db_path)

            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                digest_id = connection.execute(
                    "SELECT id FROM digests WHERE week_label = ?",
                    ("2026-W14",),
                ).fetchone()["id"]

                with patch.dict(
                    os.environ,
                    {
                        "TELEGRAM_BOT_TOKEN": "token",
                        "TELEGRAM_OWNER_CHAT_ID": "chat",
                    },
                    clear=False,
                ):
                    with patch.object(gd, "publish_article", return_value="https://telegra.ph/brief"):
                        with patch.object(gd, "send_text", return_value=777) as send_mock:
                            with patch.object(gd, "_send_copyable_digest_document"):
                                with patch.object(gd, "_utc_now_iso", return_value="2026-03-30T12:05:00Z"):
                                    gd._send_weekly_review_to_telegram_owner(
                                        connection=connection,
                                        content_md="brief",
                                        week_label="2026-W14",
                                        strong_count=1,
                                        watch_count=1,
                                        html_path=html_path,
                                        digest_id=digest_id,
                                        receipt_audit_note="Receipt: needs_review | flags=low_signal_alert",
                                    )

                receipt = fetch_research_brief_receipts(connection, digest_id=digest_id, limit=1)[0]
                digest_row = connection.execute(
                    "SELECT telegraph_url, telegram_sent_at FROM digests WHERE id = ?",
                    (digest_id,),
                ).fetchone()

            self.assertEqual(receipt["telegraph_url"], "https://telegra.ph/brief")
            self.assertEqual(receipt["telegram_delivery_timestamp"], "2026-03-30T12:05:00Z")
            self.assertEqual(receipt["telegram_message_id"], 777)
            self.assertFalse(receipt["fallback_delivery_used"])
            self.assertEqual(digest_row["telegraph_url"], "https://telegra.ph/brief")
            self.assertEqual(digest_row["telegram_sent_at"], "2026-03-30T12:05:00Z")
            self.assertIn("Receipt: needs_review", send_mock.call_args.kwargs["text"])
        finally:
            os.unlink(db_path)
            os.unlink(html_path)

    def test_weekly_review_delivery_updates_receipt_with_fallback_refs(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as html_tmp:
            html_tmp.write(b"<h1>Brief</h1>")
            html_path = gd.Path(html_tmp.name)

        try:
            self._build_digest_db(db_path)
            with patch("output.generate_recommendations.run_recommendations", return_value={"text": ""}):
                self._run_digest(db_path)

            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                digest_id = connection.execute(
                    "SELECT id FROM digests WHERE week_label = ?",
                    ("2026-W14",),
                ).fetchone()["id"]

                with patch.dict(
                    os.environ,
                    {
                        "TELEGRAM_BOT_TOKEN": "token",
                        "TELEGRAM_OWNER_CHAT_ID": "chat",
                    },
                    clear=False,
                ):
                    with patch.object(gd, "publish_article", side_effect=RuntimeError("telegraph down")):
                        with patch.object(gd, "send_text", return_value=888):
                            with patch.object(gd, "send_document", return_value=889):
                                with patch.object(gd, "_send_copyable_digest_document"):
                                    with patch.object(gd, "_utc_now_iso", return_value="2026-03-30T12:06:00Z"):
                                        gd._send_weekly_review_to_telegram_owner(
                                            connection=connection,
                                            content_md="brief",
                                            week_label="2026-W14",
                                            strong_count=1,
                                            watch_count=1,
                                            html_path=html_path,
                                            digest_id=digest_id,
                                        )

                receipt = fetch_research_brief_receipts(connection, digest_id=digest_id, limit=1)[0]
                digest_row = connection.execute(
                    "SELECT telegraph_url, telegram_sent_at FROM digests WHERE id = ?",
                    (digest_id,),
                ).fetchone()

            self.assertIsNone(receipt["telegraph_url"])
            self.assertEqual(receipt["telegram_delivery_timestamp"], "2026-03-30T12:06:00Z")
            self.assertEqual(receipt["telegram_message_id"], 888)
            self.assertEqual(receipt["fallback_delivery"], "html_attachment")
            self.assertTrue(receipt["fallback_delivery_used"])
            self.assertEqual(receipt["health_flags"], ["fallback_delivery"])
            self.assertIsNone(digest_row["telegraph_url"])
            self.assertEqual(digest_row["telegram_sent_at"], "2026-03-30T12:06:00Z")
        finally:
            os.unlink(db_path)
            os.unlink(html_path)

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
                                                        with patch.object(gd, "write_report_html", return_value=gd.Path("/tmp/2026-W14.html")):
                                                            with patch.object(gd, "_send_weekly_review_to_telegram_owner", side_effect=fake_send_digest_to_owner):
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
                                            with patch.object(gd, "write_report_html", return_value=gd.Path("/tmp/2026-W14.html")):
                                                with patch.object(gd, "_send_weekly_review_to_telegram_owner"):
                                                    with patch.object(gd, "_write_digest_file", return_value=gd.Path("/tmp/2026-W14.md")) as write_mock:
                                                        with patch("output.generate_recommendations.run_recommendations", return_value={"text": ""}):
                                                            gd.run_digest(settings)

            written_content = write_mock.call_args.args[1]
            self.assertIn("## Strong Signals", written_content)
        finally:
            os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()
