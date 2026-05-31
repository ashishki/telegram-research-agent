import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from db.migrate import run_migrations
from output.channel_intelligence import refresh_source_observations


class TestChannelIntelligenceSourceObservations(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def _insert_topic_and_project(self, connection: sqlite3.Connection) -> tuple[int, int]:
        connection.execute(
            """
            INSERT INTO projects (id, name, description, keywords, active)
            VALUES (?, ?, ?, ?, ?)
            """,
            (1, "telegram-research-agent", "fixture", "telegram", 1),
        )
        connection.execute(
            """
            INSERT INTO projects (id, name, description, keywords, active)
            VALUES (?, ?, ?, ?, ?)
            """,
            (2, "other-project", "fixture", "other", 1),
        )
        connection.execute(
            """
            INSERT INTO topics (id, label, description, first_seen, last_seen, post_count)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (1, "Agents", "fixture", "2026-05-25T09:00:00Z", "2026-05-25T09:00:00Z", 0),
        )
        return 1, 1

    def _insert_post(
        self,
        connection: sqlite3.Connection,
        *,
        post_id: int,
        raw_post_id: int,
        channel: str,
        posted_at: str,
        bucket: str,
        signal_score: float,
        project_id: int,
        topic_id: int,
        project_name: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO raw_posts (
                id,
                channel_username,
                channel_id,
                message_id,
                posted_at,
                text,
                raw_json,
                ingested_at,
                message_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                raw_post_id,
                channel,
                1000 + raw_post_id,
                2000 + raw_post_id,
                posted_at,
                f"Post {post_id}",
                "{}",
                posted_at,
                f"https://t.me/{channel}/{2000 + raw_post_id}",
            ),
        )
        connection.execute(
            """
            INSERT INTO posts (
                id,
                raw_post_id,
                channel_username,
                posted_at,
                content,
                normalized_at,
                bucket,
                signal_score,
                scored_at,
                project_matches
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id,
                raw_post_id,
                channel,
                posted_at,
                f"Post {post_id}",
                posted_at,
                bucket,
                signal_score,
                posted_at,
                json.dumps([project_name]),
            ),
        )
        connection.execute(
            """
            INSERT INTO post_project_links (post_id, project_id, relevance_score, note, tier, rationale)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (post_id, project_id, 0.9, "fixture", "direct", "fixture"),
        )
        connection.execute(
            """
            INSERT INTO post_topics (post_id, topic_id, confidence)
            VALUES (?, ?, ?)
            """,
            (post_id, topic_id, 0.9),
        )

    def test_refresh_source_observations_derives_counters_from_canonical_rows(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON;")
                _, topic_id = self._insert_topic_and_project(connection)
                self._insert_post(
                    connection,
                    post_id=1,
                    raw_post_id=1,
                    channel="source_a",
                    posted_at="2026-05-25T09:00:00Z",
                    bucket="strong",
                    signal_score=0.91,
                    project_id=1,
                    topic_id=topic_id,
                    project_name="telegram-research-agent",
                )
                self._insert_post(
                    connection,
                    post_id=2,
                    raw_post_id=2,
                    channel="source_a",
                    posted_at="2026-05-26T09:00:00Z",
                    bucket="noise",
                    signal_score=0.12,
                    project_id=1,
                    topic_id=topic_id,
                    project_name="telegram-research-agent",
                )
                self._insert_post(
                    connection,
                    post_id=3,
                    raw_post_id=3,
                    channel="source_b",
                    posted_at="2026-05-27T09:00:00Z",
                    bucket="strong",
                    signal_score=0.81,
                    project_id=2,
                    topic_id=topic_id,
                    project_name="other-project",
                )
                connection.execute(
                    """
                    INSERT INTO signal_evidence_items (
                        post_id,
                        raw_post_id,
                        week_label,
                        evidence_kind,
                        excerpt_text,
                        source_channel,
                        message_url,
                        posted_at,
                        topic_labels_json,
                        project_names_json,
                        selection_reason,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        1,
                        "2026-W22",
                        "strong_signal",
                        "Source-backed agent operations claim.",
                        "source_a",
                        "https://t.me/source_a/2001",
                        "2026-05-25T09:00:00Z",
                        json.dumps(["Agents"]),
                        json.dumps(["telegram-research-agent"]),
                        "fixture",
                        "2026-05-25T09:05:00Z",
                    ),
                )
                connection.execute(
                    "INSERT INTO signal_feedback (post_id, feedback, recorded_at) VALUES (?, ?, ?)",
                    (1, "acted_on", "2026-05-28T09:00:00Z"),
                )
                connection.execute(
                    "INSERT INTO signal_feedback (post_id, feedback, recorded_at) VALUES (?, ?, ?)",
                    (2, "skipped", "2026-05-28T10:00:00Z"),
                )
                connection.execute(
                    """
                    INSERT INTO user_post_tags (post_id, tag, note, recorded_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (2, "low_signal", "too generic", "2026-05-28T11:00:00Z"),
                )
                connection.execute(
                    """
                    INSERT INTO decision_journal (
                        decision_scope,
                        subject_ref_type,
                        subject_ref_id,
                        project_name,
                        status,
                        reason,
                        recorded_by,
                        recorded_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "signal",
                        "post_id",
                        "1",
                        "telegram-research-agent",
                        "acted_on",
                        "fixture",
                        "user",
                        "2026-05-28T12:00:00Z",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO weekly_usefulness_logs (
                        week_label,
                        useful_sections_json,
                        not_useful_sections_json,
                        decisions_influenced_json,
                        weak_evidence_notes_json,
                        channels_gaining_trust_json,
                        channels_losing_trust_json,
                        notes,
                        recorded_at,
                        recorded_by
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "2026-W22",
                        "[]",
                        "[]",
                        "[]",
                        "[]",
                        json.dumps(["source_a"]),
                        json.dumps(["source_b"]),
                        None,
                        "2026-05-29T09:00:00Z",
                        "operator",
                    ),
                )
                cursor = connection.execute(
                    """
                    INSERT INTO channel_repeated_claims (
                        claim_key,
                        normalized_claim,
                        claim_type,
                        status,
                        evidence_strength,
                        first_seen_week,
                        last_seen_week,
                        occurrence_count,
                        channel_count,
                        project_name,
                        topic_label,
                        entity_labels_json,
                        evidence_item_ids_json,
                        refresh_scope_json,
                        extraction_version,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "claim:source-a",
                        "source a repeated claim",
                        "cross_channel_repeated",
                        "repeated",
                        "strong",
                        "2026-W22",
                        "2026-W22",
                        2,
                        2,
                        "telegram-research-agent",
                        "Agents",
                        "[]",
                        "[]",
                        "{}",
                        "fixture",
                        "2026-05-29T10:00:00Z",
                        "2026-05-29T10:00:00Z",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO claim_occurrences (
                        claim_id,
                        post_id,
                        signal_evidence_item_id,
                        week_label,
                        source_channel,
                        message_url,
                        posted_at,
                        occurrence_text,
                        extraction_reason,
                        project_name,
                        topic_label,
                        extraction_version,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cursor.lastrowid,
                        1,
                        1,
                        "2026-W22",
                        "source_a",
                        "https://t.me/source_a/2001",
                        "2026-05-25T09:00:00Z",
                        "Source-backed agent operations claim.",
                        "fixture",
                        "telegram-research-agent",
                        "Agents",
                        "fixture",
                        "2026-05-29T10:01:00Z",
                    ),
                )
                connection.commit()

                summary = refresh_source_observations(
                    connection,
                    week_label="2026-W22",
                    project_name="telegram-research-agent",
                    topic_label="Agents",
                )
                row = connection.execute(
                    """
                    SELECT *
                    FROM source_observations
                    WHERE channel_username = ? AND week_label = ? AND scope_key = ?
                    """,
                    (
                        "source_a",
                        "2026-W22",
                        "project:telegram-research-agent|topic:Agents",
                    ),
                ).fetchone()
                source_b_row = connection.execute(
                    """
                    SELECT *
                    FROM source_observations
                    WHERE channel_username = ? AND scope_key = ?
                    """,
                    (
                        "source_b",
                        "project:telegram-research-agent|topic:Agents",
                    ),
                ).fetchone()
                counters = json.loads(row["counters_json"])
        finally:
            os.unlink(db_path)

        self.assertEqual(summary["source_observation_count"], 2)
        self.assertIsNotNone(row)
        self.assertEqual(row["post_count"], 2)
        self.assertEqual(row["scored_count"], 2)
        self.assertEqual(row["evidence_count"], 1)
        self.assertEqual(row["cited_count"], 1)
        self.assertEqual(row["acted_on_count"], 1)
        self.assertEqual(row["skipped_count"], 1)
        self.assertEqual(row["low_signal_count"], 1)
        self.assertEqual(row["repeated_claim_count"], 1)
        self.assertEqual(row["useful_count"], 1)
        self.assertEqual(counters["bucket_counts"], {"noise": 1, "strong": 1})
        self.assertEqual(counters["feedback_counts"], {"acted_on": 1, "skipped": 1})
        self.assertEqual(counters["tag_counts"], {"low_signal": 1})
        self.assertIn("weekly_usefulness:1", counters["usefulness_refs"])
        self.assertEqual(source_b_row["post_count"], 0)
        self.assertEqual(source_b_row["useful_count"], 0)
        self.assertEqual(json.loads(source_b_row["counters_json"])["usefulness_counts"]["losing_trust"], 1)

    def test_refresh_source_observations_is_idempotent_for_same_scope(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON;")
                _, topic_id = self._insert_topic_and_project(connection)
                self._insert_post(
                    connection,
                    post_id=1,
                    raw_post_id=1,
                    channel="source_a",
                    posted_at="2026-05-25T09:00:00Z",
                    bucket="strong",
                    signal_score=0.91,
                    project_id=1,
                    topic_id=topic_id,
                    project_name="telegram-research-agent",
                )
                connection.commit()

                first = refresh_source_observations(connection, week_label="2026-W22")
                second = refresh_source_observations(connection, week_label="2026-W22")
                row_count = connection.execute("SELECT COUNT(*) FROM source_observations").fetchone()[0]
        finally:
            os.unlink(db_path)

        self.assertEqual(first["source_observation_count"], 1)
        self.assertEqual(second["source_observation_count"], 1)
        self.assertEqual(row_count, 1)


if __name__ == "__main__":
    unittest.main()
