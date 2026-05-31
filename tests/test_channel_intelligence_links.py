import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from db.migrate import run_migrations
from output.channel_intelligence import refresh_intelligence_links, refresh_source_observations


class TestChannelIntelligenceLinks(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def _insert_foundation(self, connection: sqlite3.Connection) -> None:
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

    def _insert_post_and_evidence(
        self,
        connection: sqlite3.Connection,
        *,
        post_id: int,
        raw_post_id: int,
        channel: str,
        project_id: int,
        project_name: str,
    ) -> None:
        posted_at = f"2026-05-2{post_id}T09:00:00Z"
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
                "strong",
                0.9,
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
            "INSERT INTO post_topics (post_id, topic_id, confidence) VALUES (?, ?, ?)",
            (post_id, 1, 0.9),
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
                post_id,
                raw_post_id,
                "2026-W22",
                "strong_signal",
                f"Evidence {post_id}",
                channel,
                f"https://t.me/{channel}/{2000 + raw_post_id}",
                posted_at,
                json.dumps(["Agents"]),
                json.dumps([project_name]),
                "fixture",
                posted_at,
            ),
        )

    def _insert_claim(
        self,
        connection: sqlite3.Connection,
        *,
        claim_key: str,
        project_name: str,
        post_id: int,
        evidence_id: int,
        channel: str,
    ) -> None:
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
                claim_key,
                claim_key.replace("claim:", ""),
                "cross_channel_repeated",
                "repeated",
                "strong",
                "2026-W22",
                "2026-W22",
                2,
                2,
                project_name,
                "Agents",
                "[]",
                json.dumps([evidence_id]),
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
                post_id,
                evidence_id,
                "2026-W22",
                channel,
                f"https://t.me/{channel}/{2000 + post_id}",
                f"2026-05-2{post_id}T09:00:00Z",
                "Evidence",
                "fixture",
                project_name,
                "Agents",
                "fixture",
                "2026-05-29T10:01:00Z",
            ),
        )

    def test_refresh_intelligence_links_scopes_to_curated_active_projects(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON;")
                self._insert_foundation(connection)
                self._insert_post_and_evidence(
                    connection,
                    post_id=1,
                    raw_post_id=1,
                    channel="source_a",
                    project_id=1,
                    project_name="telegram-research-agent",
                )
                self._insert_post_and_evidence(
                    connection,
                    post_id=2,
                    raw_post_id=2,
                    channel="source_b",
                    project_id=2,
                    project_name="other-project",
                )
                self._insert_claim(
                    connection,
                    claim_key="claim:telegram",
                    project_name="telegram-research-agent",
                    post_id=1,
                    evidence_id=1,
                    channel="source_a",
                )
                self._insert_claim(
                    connection,
                    claim_key="claim:other",
                    project_name="other-project",
                    post_id=2,
                    evidence_id=2,
                    channel="source_b",
                )
                connection.commit()
                refresh_source_observations(
                    connection,
                    week_label="2026-W22",
                    project_name="telegram-research-agent",
                    topic_label="Agents",
                )

                summary = refresh_intelligence_links(connection, week_label="2026-W22")
                entity_rows = connection.execute(
                    """
                    SELECT entity_label, entity_type, linked_object_type, project_name
                    FROM intelligence_entity_links
                    ORDER BY entity_label, linked_object_type
                    """
                ).fetchall()
                project_rows = connection.execute(
                    """
                    SELECT project_name, linked_object_type, match_reason
                    FROM project_intelligence_links
                    ORDER BY linked_object_type, project_name
                    """
                ).fetchall()
        finally:
            os.unlink(db_path)

        self.assertGreaterEqual(summary["entity_link_count"], 3)
        self.assertGreaterEqual(summary["project_link_count"], 3)
        self.assertIn(
            ("telegram-research-agent", "project", "evidence", "telegram-research-agent"),
            [tuple(row) for row in entity_rows],
        )
        self.assertIn(
            ("Agents", "topic", "evidence", "telegram-research-agent"),
            [tuple(row) for row in entity_rows],
        )
        self.assertIn(
            ("Agents", "topic", "claim", "telegram-research-agent"),
            [tuple(row) for row in entity_rows],
        )
        self.assertNotIn("other-project", {row["project_name"] for row in entity_rows})
        self.assertEqual({row["project_name"] for row in project_rows}, {"telegram-research-agent"})
        self.assertIn("claim", {row["linked_object_type"] for row in project_rows})
        self.assertIn("entity", {row["linked_object_type"] for row in project_rows})
        self.assertIn("source_observation", {row["linked_object_type"] for row in project_rows})

    def test_refresh_intelligence_links_is_idempotent_for_same_scope(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON;")
                self._insert_foundation(connection)
                self._insert_post_and_evidence(
                    connection,
                    post_id=1,
                    raw_post_id=1,
                    channel="source_a",
                    project_id=1,
                    project_name="telegram-research-agent",
                )
                connection.commit()

                first = refresh_intelligence_links(connection, week_label="2026-W22")
                second = refresh_intelligence_links(connection, week_label="2026-W22")
                entity_count = connection.execute("SELECT COUNT(*) FROM intelligence_entity_links").fetchone()[0]
                project_count = connection.execute("SELECT COUNT(*) FROM project_intelligence_links").fetchone()[0]
        finally:
            os.unlink(db_path)

        self.assertEqual(first["entity_link_count"], 2)
        self.assertEqual(second["entity_link_count"], 2)
        self.assertEqual(entity_count, 2)
        self.assertEqual(project_count, 2)


if __name__ == "__main__":
    unittest.main()
