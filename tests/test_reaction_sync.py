import asyncio
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch


class TestReactionSync(unittest.TestCase):
    SUMMARY_KEYS = {
        "posts_checked",
        "posts_with_reactions",
        "matched_reactions",
        "applied_tags",
        "applied_feedback",
        "skipped_unknown",
        "skipped_existing",
        "errors",
    }

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "test.db")
        os.environ["AGENT_DB_PATH"] = self.db_path

    def tearDown(self):
        del os.environ["AGENT_DB_PATH"]
        self.tmpdir.cleanup()

    def _connection_with_post(self) -> tuple[sqlite3.Connection, int]:
        from db.migrate import run_migrations

        run_migrations()
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute(
            """
            INSERT INTO raw_posts (
                channel_username, channel_id, message_id, posted_at,
                text, raw_json, ingested_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("@source", 100, 77, "2026-04-28T00:00:00Z", "Interesting post", "{}", "2026-04-28T00:01:00Z"),
        )
        raw_post_id = int(connection.execute("SELECT id FROM raw_posts").fetchone()["id"])
        connection.execute(
            """
            INSERT INTO posts (raw_post_id, channel_username, posted_at, content, normalized_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (raw_post_id, "@source", "2026-04-28T00:00:00Z", "Interesting post", "2026-04-28T00:02:00Z"),
        )
        post_id = int(connection.execute("SELECT id FROM posts").fetchone()["id"])
        connection.commit()
        return connection, post_id

    def _settings(self):
        from config.settings import Settings

        return Settings(
            db_path=self.db_path,
            llm_api_key="",
            model_provider="test",
            telegram_session_path="test.session",
        )

    def _completed_week_period(self):
        from output.reporting_period import resolve_reporting_period

        return resolve_reporting_period(
            datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
        )

    def _put_post_in_completed_week(self) -> int:
        connection, post_id = self._connection_with_post()
        connection.execute(
            "UPDATE posts SET posted_at = ? WHERE id = ?",
            ("2026-07-12T12:00:00Z", post_id),
        )
        connection.commit()
        connection.close()
        return post_id

    def _run_outcome(
        self,
        *,
        emojis: set[str] | None = None,
        fetch_error: Exception | None = None,
        limit: int = 300,
    ):
        from ingestion.reaction_sync import sync_reactions_with_outcome

        client = _FakeTelegramClient()
        fetch = (
            AsyncMock(side_effect=fetch_error)
            if fetch_error is not None
            else AsyncMock(return_value=set(emojis or set()))
        )
        with patch(
            "ingestion.telegram_client.make_client",
            new=AsyncMock(return_value=client),
        ), patch(
            "ingestion.reaction_sync._fetch_self_reaction_emojis",
            new=fetch,
        ):
            outcome = asyncio.run(
                sync_reactions_with_outcome(
                    self._settings(),
                    limit=limit,
                    reporting_period=self._completed_week_period(),
                )
            )
        self.assertTrue(client.disconnected)
        return outcome

    def test_reaction_sync_state_table_created(self):
        connection, _post_id = self._connection_with_post()
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='reaction_sync_state'"
        ).fetchone()
        self.assertIsNotNone(row)

    def test_apply_reaction_feedback_records_operator_interest_and_raw_emoji(self):
        from ingestion.reaction_sync import apply_reaction_feedback

        connection, post_id = self._connection_with_post()
        summary = apply_reaction_feedback(
            connection,
            post_id=post_id,
            channel_username="@source",
            message_id=77,
            emojis={"🔥"},
        )

        self.assertEqual(summary["matched_reactions"], 1)
        self.assertEqual(summary["applied_tags"], 1)
        self.assertEqual(summary["applied_feedback"], 1)

        tag = connection.execute("SELECT tag FROM user_post_tags WHERE post_id = ?", (post_id,)).fetchone()
        feedback = connection.execute("SELECT feedback FROM signal_feedback WHERE post_id = ?", (post_id,)).fetchone()
        state = connection.execute(
            "SELECT emoji, action_key FROM reaction_sync_state WHERE message_id = 77"
        ).fetchone()

        self.assertEqual(tag["tag"], "interesting")
        self.assertEqual(feedback["feedback"], "operator_marked_interesting")
        self.assertEqual(state["emoji"], "🔥")
        self.assertEqual(state["action_key"], "tag:interesting|feedback:operator_marked_interesting")

    def test_apply_reaction_feedback_is_idempotent(self):
        from ingestion.reaction_sync import apply_reaction_feedback

        connection, post_id = self._connection_with_post()
        apply_reaction_feedback(
            connection,
            post_id=post_id,
            channel_username="@source",
            message_id=77,
            emojis={"✅"},
        )
        second = apply_reaction_feedback(
            connection,
            post_id=post_id,
            channel_username="@source",
            message_id=77,
            emojis={"✅"},
        )

        self.assertEqual(second["skipped_existing"], 1)
        tag_count = connection.execute("SELECT COUNT(*) FROM user_post_tags WHERE post_id = ?", (post_id,)).fetchone()[0]
        feedback_count = connection.execute("SELECT COUNT(*) FROM signal_feedback WHERE post_id = ?", (post_id,)).fetchone()[0]
        self.assertEqual(tag_count, 1)
        self.assertEqual(feedback_count, 1)

    def test_old_reaction_state_prevents_reapplying_same_raw_emoji(self):
        from ingestion.reaction_sync import apply_reaction_feedback

        connection, post_id = self._connection_with_post()
        connection.execute(
            """
            INSERT INTO reaction_sync_state (
                source, channel_username, message_id, emoji, action_key, applied_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "telegram_reaction",
                "@source",
                77,
                "🔥",
                "tag:strong|feedback:marked_important",
                "2026-07-07T12:00:00Z",
            ),
        )
        connection.commit()

        summary = apply_reaction_feedback(
            connection,
            post_id=post_id,
            channel_username="@source",
            message_id=77,
            emojis={"🔥"},
        )

        self.assertEqual(summary["skipped_existing"], 1)
        feedback_count = connection.execute(
            "SELECT COUNT(*) FROM signal_feedback WHERE post_id = ?",
            (post_id,),
        ).fetchone()[0]
        self.assertEqual(feedback_count, 0)

    def test_any_visible_personal_reaction_counts_as_operator_interest(self):
        from ingestion.reaction_sync import apply_reaction_feedback

        connection, post_id = self._connection_with_post()
        summary = apply_reaction_feedback(
            connection,
            post_id=post_id,
            channel_username="@source",
            message_id=77,
            emojis={"🐢"},
        )

        self.assertEqual(summary["matched_reactions"], 1)
        self.assertEqual(summary["skipped_unknown"], 0)
        tag = connection.execute("SELECT tag FROM user_post_tags WHERE post_id = ?", (post_id,)).fetchone()
        feedback = connection.execute("SELECT feedback FROM signal_feedback WHERE post_id = ?", (post_id,)).fetchone()
        state = connection.execute("SELECT emoji FROM reaction_sync_state WHERE message_id = 77").fetchone()
        self.assertEqual(tag["tag"], "interesting")
        self.assertEqual(feedback["feedback"], "operator_marked_interesting")
        self.assertEqual(state["emoji"], "🐢")

    def test_aggregate_only_reaction_counts_are_not_personal_feedback(self):
        from ingestion.reaction_sync import _extract_self_reactions_from_message

        message = _Object(
            reactions=_Object(
                results=[
                    _Object(reaction=_Object(emoticon="🔥"), count=42),
                ],
                recent_reactions=[],
            )
        )

        self.assertEqual(_extract_self_reactions_from_message(message, self_user_id=123), set())

    def test_recent_self_reaction_is_personal_feedback(self):
        from ingestion.reaction_sync import _extract_self_reactions_from_message

        message = _Object(
            reactions=_Object(
                recent_reactions=[
                    _Object(
                        peer_id=_Object(user_id=123),
                        reaction=_Object(emoticon="🔥"),
                    ),
                ],
            )
        )

        self.assertEqual(_extract_self_reactions_from_message(message, self_user_id=123), {"🔥"})

    def test_recent_self_custom_emoji_is_retained_as_opaque_audit_token(self):
        from ingestion.reaction_sync import _extract_self_reactions_from_message

        message = _Object(
            reactions=_Object(
                recent_reactions=[
                    _Object(
                        peer_id=_Object(user_id=123),
                        reaction=_Object(document_id=987654321),
                    ),
                ],
            )
        )

        self.assertEqual(
            _extract_self_reactions_from_message(message, self_user_id=123),
            {"custom_emoji:987654321"},
        )

    def test_double_visibility_lookup_failure_raises_typed_error(self):
        from ingestion.reaction_sync import (
            ReactionVisibilityUnverifiedError,
            _fetch_self_reaction_emojis,
        )

        with self.assertRaises(ReactionVisibilityUnverifiedError):
            asyncio.run(
                _fetch_self_reaction_emojis(
                    _DoubleFailureClient(),
                    "@source",
                    77,
                    123,
                )
            )

    def test_primary_failure_and_empty_recent_fallback_is_unverified(self):
        from ingestion.reaction_sync import (
            ReactionVisibilityUnverifiedError,
            _fetch_self_reaction_emojis,
        )

        messages_module = types.ModuleType("telethon.tl.functions.messages")
        messages_module.GetMessageReactionsListRequest = lambda **values: values
        with patch.dict(
            sys.modules,
            {"telethon.tl.functions.messages": messages_module},
        ):
            with self.assertRaises(ReactionVisibilityUnverifiedError):
                asyncio.run(
                    _fetch_self_reaction_emojis(
                        _PrimaryFailureEmptyRecentClient(),
                        "@source",
                        77,
                        123,
                    )
                )

    def test_fallback_own_chosen_marker_can_attest_personal_reaction(self):
        from ingestion.reaction_sync import _fetch_self_reaction_emojis

        messages_module = types.ModuleType("telethon.tl.functions.messages")
        messages_module.GetMessageReactionsListRequest = lambda **values: values
        with patch.dict(
            sys.modules,
            {"telethon.tl.functions.messages": messages_module},
        ):
            result = asyncio.run(
                _fetch_self_reaction_emojis(
                    _PrimaryFailureChosenMarkerClient(),
                    "@source",
                    77,
                    123,
                )
            )

        self.assertEqual(result, {"🔥"})

    def test_successful_empty_primary_lookup_is_verified_empty(self):
        from ingestion.reaction_sync import _fetch_self_reaction_emojis

        messages_module = types.ModuleType("telethon.tl.functions.messages")
        messages_module.GetMessageReactionsListRequest = lambda **values: values
        with patch.dict(
            sys.modules,
            {"telethon.tl.functions.messages": messages_module},
        ):
            result = asyncio.run(
                _fetch_self_reaction_emojis(
                    _SuccessfulEmptyListClient(),
                    "@source",
                    77,
                    123,
                )
            )

        self.assertEqual(result, set())

    def test_legacy_sync_api_returns_only_existing_count_keys(self):
        from ingestion.reaction_sync import ReactionSyncOutcome, sync_reactions

        summary = {key: 0 for key in self.SUMMARY_KEYS}
        outcome = ReactionSyncOutcome(
            summary=summary,
            observed_personal_posts=(),
            candidate_count=0,
            checked_count=0,
            coverage_complete=True,
            visibility_verified=True,
        )
        with patch(
            "ingestion.reaction_sync.sync_reactions_with_outcome",
            new=AsyncMock(return_value=outcome),
        ):
            result = asyncio.run(sync_reactions(self._settings()))

        self.assertEqual(result, summary)
        self.assertEqual(set(result), self.SUMMARY_KEYS)

    def test_outcome_collapses_multiple_emojis_to_one_observed_post(self):
        post_id = self._put_post_in_completed_week()

        outcome = self._run_outcome(emojis={"🔥", "🐢"})

        self.assertEqual(set(outcome.count_summary()), self.SUMMARY_KEYS)
        self.assertEqual(outcome.candidate_count, 1)
        self.assertEqual(outcome.checked_count, 1)
        self.assertTrue(outcome.coverage_complete)
        self.assertTrue(outcome.visibility_verified)
        self.assertEqual(outcome.summary["posts_with_reactions"], 1)
        self.assertEqual(outcome.summary["matched_reactions"], 2)
        self.assertEqual(len(outcome.observed_personal_posts), 1)
        observed = outcome.observed_personal_posts[0]
        self.assertEqual(observed.post_id, post_id)
        self.assertEqual(observed.channel_username, "@source")
        self.assertEqual(observed.message_id, 77)
        self.assertEqual(observed.raw_emojis, tuple(sorted({"🔥", "🐢"})))

    def test_observed_posts_deduplicate_normalized_channel_and_message(self):
        self._put_post_in_completed_week()
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO raw_posts (
                    channel_username, channel_id, message_id, posted_at,
                    text, raw_json, ingested_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "source",
                    101,
                    77,
                    "2026-07-11T00:00:00Z",
                    "Duplicate identity",
                    "{}",
                    "2026-07-11T00:01:00Z",
                ),
            )
            connection.execute(
                """
                INSERT INTO posts (
                    raw_post_id, channel_username, posted_at, content, normalized_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    cursor.lastrowid,
                    "source",
                    "2026-07-11T00:00:00Z",
                    "Duplicate identity",
                    "2026-07-11T00:02:00Z",
                ),
            )
            connection.commit()

        outcome = self._run_outcome(emojis={"🔥"})

        self.assertEqual(outcome.candidate_count, 2)
        self.assertEqual(outcome.checked_count, 2)
        self.assertEqual(len(outcome.observed_personal_posts), 1)
        self.assertEqual(outcome.observed_personal_posts[0].message_id, 77)

    def test_existing_materialized_reaction_remains_visible_in_outcome(self):
        self._put_post_in_completed_week()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO reaction_sync_state (
                    source, channel_username, message_id, emoji, action_key, applied_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "telegram_reaction",
                    "@source",
                    77,
                    "🔥",
                    "tag:interesting|feedback:operator_marked_interesting",
                    "2026-07-07T12:00:00Z",
                ),
            )
            connection.commit()

        outcome = self._run_outcome(emojis={"🔥"})

        self.assertEqual(outcome.summary["skipped_existing"], 1)
        self.assertEqual(len(outcome.observed_personal_posts), 1)
        self.assertEqual(outcome.observed_personal_posts[0].raw_emojis, ("🔥",))
        self.assertTrue(outcome.visibility_verified)

    def test_removed_old_reaction_is_absent_from_current_outcome(self):
        self._put_post_in_completed_week()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO reaction_sync_state (
                    source, channel_username, message_id, emoji, action_key, applied_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "telegram_reaction",
                    "@source",
                    77,
                    "🔥",
                    "tag:interesting|feedback:operator_marked_interesting",
                    "2026-07-07T12:00:00Z",
                ),
            )
            connection.commit()

        outcome = self._run_outcome(emojis=set())

        self.assertEqual(outcome.observed_personal_posts, ())
        self.assertEqual(outcome.summary["posts_with_reactions"], 0)
        self.assertEqual(outcome.summary["skipped_existing"], 0)
        self.assertTrue(outcome.visibility_verified)

    def test_unverified_candidate_is_an_error_not_verified_empty(self):
        from ingestion.reaction_sync import ReactionVisibilityUnverifiedError

        self._put_post_in_completed_week()
        with self.assertLogs("ingestion.reaction_sync", level="WARNING"):
            outcome = self._run_outcome(
                fetch_error=ReactionVisibilityUnverifiedError("lookup failed")
            )

        self.assertEqual(outcome.candidate_count, 1)
        self.assertEqual(outcome.checked_count, 1)
        self.assertEqual(outcome.summary["errors"], 1)
        self.assertEqual(outcome.observed_personal_posts, ())
        self.assertTrue(outcome.coverage_complete)
        self.assertFalse(outcome.visibility_verified)

    def test_reaction_limit_reports_incomplete_coverage(self):
        self._put_post_in_completed_week()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO raw_posts (
                    channel_username, channel_id, message_id, posted_at,
                    text, raw_json, ingested_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "@second",
                    101,
                    78,
                    "2026-07-11T00:00:00Z",
                    "Second",
                    "{}",
                    "2026-07-11T00:01:00Z",
                ),
            )
            raw_post_id = int(connection.execute("SELECT max(id) FROM raw_posts").fetchone()[0])
            connection.execute(
                """
                INSERT INTO posts (
                    raw_post_id, channel_username, posted_at, content, normalized_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    raw_post_id,
                    "@second",
                    "2026-07-11T00:00:00Z",
                    "Second",
                    "2026-07-11T00:02:00Z",
                ),
            )
            connection.commit()

        outcome = self._run_outcome(emojis=set(), limit=1)

        self.assertEqual(outcome.candidate_count, 2)
        self.assertEqual(outcome.checked_count, 1)
        self.assertEqual(outcome.summary["errors"], 0)
        self.assertFalse(outcome.coverage_complete)
        self.assertFalse(outcome.visibility_verified)

    def test_candidate_selection_uses_exact_reporting_period_when_supplied(self):
        from ingestion.reaction_sync import _load_candidate_posts
        from output.reporting_period import resolve_reporting_period

        connection, _post_id = self._connection_with_post()
        connection.execute(
            "UPDATE posts SET posted_at = ?",
            ("2026-07-12T23:59:59.999999Z",),
        )
        fixtures = (
            ("@future", 101, 78, "2026-07-13T00:00:00Z", "Future"),
            ("@start", 102, 79, "2026-07-06T00:00:00Z", "Start"),
            ("@before", 103, 80, "2026-07-05T23:59:59.999999Z", "Before"),
        )
        for channel, channel_id, message_id, posted_at, content in fixtures:
            cursor = connection.execute(
                """
                INSERT INTO raw_posts (
                    channel_username, channel_id, message_id, posted_at,
                    text, raw_json, ingested_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    channel,
                    channel_id,
                    message_id,
                    posted_at,
                    content,
                    "{}",
                    "2026-07-13T00:01:00Z",
                ),
            )
            connection.execute(
                """
                INSERT INTO posts (
                    raw_post_id, channel_username, posted_at, content, normalized_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (cursor.lastrowid, channel, posted_at, content, "2026-07-13T00:02:00Z"),
            )
        connection.commit()
        period = resolve_reporting_period(
            datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
        )

        rows = _load_candidate_posts(
            connection,
            days=14,
            limit=20,
            reporting_period=period,
        )

        self.assertEqual([row["message_id"] for row in rows], [77, 79])

    def test_production_offset_timestamp_is_canonicalized_for_run_snapshot(self):
        from ingestion.reaction_sync import _canonical_utc_text

        self.assertEqual(
            _canonical_utc_text("2026-07-12T23:59:59+00:00"),
            "2026-07-12T23:59:59Z",
        )


class _Object:
    def __init__(self, **values):
        for key, value in values.items():
            setattr(self, key, value)


class _FakeTelegramClient:
    def __init__(self):
        self.disconnected = False

    async def get_me(self):
        return _Object(id=123)

    async def get_entity(self, channel_username):
        return channel_username

    async def disconnect(self):
        self.disconnected = True


class _DoubleFailureClient:
    async def __call__(self, _request):
        raise RuntimeError("reaction-list lookup failed")

    async def get_messages(self, _entity, *, ids):
        raise RuntimeError(f"message lookup failed for {ids}")


class _SuccessfulEmptyListClient:
    async def __call__(self, _request):
        return _Object(reactions=[], next_offset=None)

    async def get_messages(self, _entity, *, ids):
        raise AssertionError(f"fallback must not run for verified-empty message {ids}")


class _PrimaryFailureEmptyRecentClient:
    async def __call__(self, _request):
        raise RuntimeError("reaction-list lookup failed")

    async def get_messages(self, _entity, *, ids):
        return _Object(reactions=_Object(recent_reactions=[]))


class _PrimaryFailureChosenMarkerClient:
    async def __call__(self, _request):
        raise RuntimeError("reaction-list lookup failed")

    async def get_messages(self, _entity, *, ids):
        return _Object(
            reactions=_Object(
                results=[
                    _Object(
                        reaction=_Object(emoticon="🔥"),
                        count=1,
                        chosen_order=0,
                    )
                ],
                recent_reactions=[],
            )
        )


if __name__ == "__main__":
    unittest.main()
