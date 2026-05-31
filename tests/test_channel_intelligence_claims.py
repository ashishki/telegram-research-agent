import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from db.migrate import run_migrations
from output.channel_intelligence import refresh_repeated_claims


class TestChannelIntelligenceClaims(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def _insert_post_and_evidence(
        self,
        connection: sqlite3.Connection,
        *,
        post_id: int,
        raw_post_id: int,
        channel: str,
        text: str,
        week_label: str = "2026-W22",
        project_names: list[str] | None = None,
        topic_labels: list[str] | None = None,
    ) -> None:
        posted_at = f"2026-05-2{post_id}T10:00:00Z"
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
                text,
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
                normalized_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (post_id, raw_post_id, channel, posted_at, text, posted_at),
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
                week_label,
                "strong_signal",
                text,
                channel,
                f"https://t.me/{channel}/{2000 + raw_post_id}",
                posted_at,
                json.dumps(topic_labels or ["Agents"]),
                json.dumps(project_names or ["telegram-research-agent"]),
                "fixture",
                posted_at,
            ),
        )

    def test_refresh_repeated_claims_classifies_cross_same_and_weak_claims(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON;")
                self._insert_post_and_evidence(
                    connection,
                    post_id=1,
                    raw_post_id=1,
                    channel="source_a",
                    text="Local coding agents are moving into production use.",
                )
                self._insert_post_and_evidence(
                    connection,
                    post_id=2,
                    raw_post_id=2,
                    channel="source_b",
                    text="Local coding agents are moving into production use.",
                )
                self._insert_post_and_evidence(
                    connection,
                    post_id=3,
                    raw_post_id=3,
                    channel="source_c",
                    text="One channel repeats its own benchmark claim.",
                )
                self._insert_post_and_evidence(
                    connection,
                    post_id=4,
                    raw_post_id=4,
                    channel="source_c",
                    text="One channel repeats its own benchmark claim.",
                )
                self._insert_post_and_evidence(
                    connection,
                    post_id=5,
                    raw_post_id=5,
                    channel="source_d",
                    text="A lonely claim appears only once.",
                )
                connection.commit()

                summary = refresh_repeated_claims(connection, week_label="2026-W22")
                claims = {
                    row["normalized_claim"]: dict(row)
                    for row in connection.execute(
                        """
                        SELECT normalized_claim, claim_type, status, evidence_strength,
                               occurrence_count, channel_count
                        FROM channel_repeated_claims
                        ORDER BY normalized_claim
                        """
                    ).fetchall()
                }
                occurrence_count = connection.execute("SELECT COUNT(*) FROM claim_occurrences").fetchone()[0]
        finally:
            os.unlink(db_path)

        self.assertEqual(summary["evidence_rows"], 5)
        self.assertEqual(summary["claim_count"], 3)
        self.assertEqual(summary["repeated_claims"], 2)
        self.assertEqual(summary["weak_claims"], 1)
        cross = claims["local coding agents are moving into production use"]
        self.assertEqual(cross["claim_type"], "cross_channel_repeated")
        self.assertEqual(cross["status"], "repeated")
        self.assertEqual(cross["evidence_strength"], "strong")
        self.assertEqual(cross["occurrence_count"], 2)
        self.assertEqual(cross["channel_count"], 2)
        same = claims["one channel repeats its own benchmark claim"]
        self.assertEqual(same["claim_type"], "same_channel_repeated")
        self.assertEqual(same["status"], "repeated")
        self.assertEqual(same["evidence_strength"], "moderate")
        self.assertEqual(same["occurrence_count"], 2)
        self.assertEqual(same["channel_count"], 1)
        weak = claims["a lonely claim appears only once"]
        self.assertEqual(weak["claim_type"], "single_occurrence")
        self.assertEqual(weak["status"], "weak")
        self.assertEqual(occurrence_count, 5)

    def test_refresh_repeated_claims_respects_project_scope(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON;")
                self._insert_post_and_evidence(
                    connection,
                    post_id=1,
                    raw_post_id=1,
                    channel="source_a",
                    text="Scoped claim appears twice.",
                    project_names=["telegram-research-agent"],
                )
                self._insert_post_and_evidence(
                    connection,
                    post_id=2,
                    raw_post_id=2,
                    channel="source_b",
                    text="Scoped claim appears twice.",
                    project_names=["other-project"],
                )
                connection.commit()

                summary = refresh_repeated_claims(
                    connection,
                    week_label="2026-W22",
                    project_name="telegram-research-agent",
                )
                claim = connection.execute(
                    """
                    SELECT occurrence_count, channel_count, project_name
                    FROM channel_repeated_claims
                    WHERE normalized_claim = ?
                    """,
                    ("scoped claim appears twice",),
                ).fetchone()
        finally:
            os.unlink(db_path)

        self.assertEqual(summary["evidence_rows"], 1)
        self.assertEqual(summary["weak_claims"], 1)
        self.assertEqual(claim["occurrence_count"], 1)
        self.assertEqual(claim["channel_count"], 1)
        self.assertEqual(claim["project_name"], "telegram-research-agent")


if __name__ == "__main__":
    unittest.main()
