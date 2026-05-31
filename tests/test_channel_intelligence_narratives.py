import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from db.migrate import run_migrations
from output.channel_intelligence import refresh_narrative_candidates


class TestChannelIntelligenceNarratives(unittest.TestCase):
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
            INSERT INTO topics (id, label, description, first_seen, last_seen, post_count)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (1, "Agents", "fixture", "2026-05-25T09:00:00Z", "2026-05-25T09:00:00Z", 0),
        )

    def _insert_evidence(self, connection: sqlite3.Connection, evidence_id: int, channel: str) -> None:
        posted_at = f"2026-05-{24 + evidence_id:02d}T09:00:00Z"
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
                evidence_id,
                channel,
                1000 + evidence_id,
                2000 + evidence_id,
                posted_at,
                f"Evidence {evidence_id}",
                "{}",
                posted_at,
                f"https://t.me/{channel}/{2000 + evidence_id}",
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
                evidence_id,
                evidence_id,
                channel,
                posted_at,
                f"Evidence {evidence_id}",
                posted_at,
                "strong",
                0.9,
                posted_at,
                json.dumps(["telegram-research-agent"]),
            ),
        )
        connection.execute(
            """
            INSERT INTO signal_evidence_items (
                id,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence_id,
                evidence_id,
                evidence_id,
                "2026-W22",
                "strong_signal",
                f"Evidence {evidence_id}",
                channel,
                f"https://t.me/{channel}/{2000 + evidence_id}",
                posted_at,
                json.dumps(["Agents"]),
                json.dumps(["telegram-research-agent"]),
                "fixture",
                posted_at,
            ),
        )

    def _insert_claim(
        self,
        connection: sqlite3.Connection,
        *,
        claim_id: int,
        evidence_ids: list[int],
        channel: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO channel_repeated_claims (
                id,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                claim_id,
                f"claim:{claim_id}",
                f"claim {claim_id}",
                "cross_channel_repeated",
                "repeated",
                "strong",
                "2026-W22",
                "2026-W22",
                len(evidence_ids),
                2,
                "telegram-research-agent",
                "Agents",
                "[]",
                json.dumps(evidence_ids),
                "{}",
                "fixture",
                "2026-05-29T10:00:00Z",
                "2026-05-29T10:00:00Z",
            ),
        )
        for evidence_id in evidence_ids:
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
                    claim_id,
                    evidence_id,
                    evidence_id,
                    "2026-W22",
                    channel,
                    f"https://t.me/{channel}/{2000 + evidence_id}",
                    f"2026-05-{24 + evidence_id:02d}T09:00:00Z",
                    f"Evidence {evidence_id}",
                    "fixture",
                    "telegram-research-agent",
                    "Agents",
                    "fixture",
                    "2026-05-29T10:01:00Z",
                ),
            )

    def test_refresh_narrative_candidates_creates_links_with_supporting_evidence(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON;")
                self._insert_foundation(connection)
                for evidence_id, channel in [(1, "source_a"), (2, "source_b"), (3, "source_c")]:
                    self._insert_evidence(connection, evidence_id, channel)
                self._insert_claim(connection, claim_id=1, evidence_ids=[1, 2], channel="source_a")
                self._insert_claim(connection, claim_id=2, evidence_ids=[2, 3], channel="source_b")
                connection.commit()

                summary = refresh_narrative_candidates(connection, week_label="2026-W22")
                narrative = connection.execute("SELECT * FROM channel_narratives").fetchone()
                link_count = connection.execute("SELECT COUNT(*) FROM narrative_claim_links").fetchone()[0]
                project_link = connection.execute(
                    """
                    SELECT *
                    FROM project_intelligence_links
                    WHERE linked_object_type = 'narrative'
                    """
                ).fetchone()
        finally:
            os.unlink(db_path)

        self.assertEqual(summary["narrative_count"], 1)
        self.assertEqual(summary["active_narratives"], 1)
        self.assertEqual(narrative["status"], "active")
        self.assertEqual(narrative["project_name"], "telegram-research-agent")
        self.assertEqual(json.loads(narrative["evidence_item_ids_json"]), [1, 2, 3])
        self.assertEqual(narrative["linked_claim_count"], 2)
        self.assertEqual(link_count, 2)
        self.assertIsNotNone(project_link)

    def test_refresh_narrative_candidates_rejects_over_aggregated_group(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON;")
                self._insert_foundation(connection)
                for evidence_id in range(1, 5):
                    self._insert_evidence(connection, evidence_id, f"source_{evidence_id}")
                    self._insert_claim(
                        connection,
                        claim_id=evidence_id,
                        evidence_ids=[evidence_id],
                        channel=f"source_{evidence_id}",
                    )
                connection.commit()

                summary = refresh_narrative_candidates(
                    connection,
                    week_label="2026-W22",
                    max_claims_per_narrative=2,
                )
                narrative = connection.execute("SELECT * FROM channel_narratives").fetchone()
                link_count = connection.execute("SELECT COUNT(*) FROM narrative_claim_links").fetchone()[0]
        finally:
            os.unlink(db_path)

        self.assertEqual(summary["narrative_count"], 1)
        self.assertEqual(summary["rejected_narratives"], 1)
        self.assertEqual(narrative["status"], "rejected")
        self.assertEqual(narrative["linked_claim_count"], 0)
        self.assertEqual(link_count, 0)
        self.assertTrue(json.loads(narrative["refresh_scope_json"])["over_aggregated"])


if __name__ == "__main__":
    unittest.main()
