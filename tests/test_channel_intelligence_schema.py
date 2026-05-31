import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from db.migrate import run_migrations


class TestChannelIntelligenceSchema(unittest.TestCase):
    TABLES = [
        "channel_narratives",
        "channel_repeated_claims",
        "claim_occurrences",
        "source_observations",
        "intelligence_entity_links",
        "project_intelligence_links",
        "narrative_claim_links",
        "channel_intelligence_weekly_rollups",
    ]

    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def test_migration_creates_channel_intelligence_tables(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                table_names = {
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type = 'table'
                        """
                    ).fetchall()
                }
                narrative_columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(channel_narratives)").fetchall()
                }
                claim_columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(channel_repeated_claims)").fetchall()
                }
                occurrence_fks = connection.execute("PRAGMA foreign_key_list(claim_occurrences)").fetchall()
                narrative_claim_fks = connection.execute("PRAGMA foreign_key_list(narrative_claim_links)").fetchall()
        finally:
            os.unlink(db_path)

        for table in self.TABLES:
            self.assertIn(table, table_names)
        for column_name in [
            "narrative_key",
            "status",
            "project_name",
            "topic_label",
            "evidence_item_ids_json",
            "refresh_scope_json",
        ]:
            self.assertIn(column_name, narrative_columns)
        for column_name in [
            "claim_key",
            "normalized_claim",
            "occurrence_count",
            "channel_count",
            "evidence_strength",
            "entity_labels_json",
        ]:
            self.assertIn(column_name, claim_columns)
        self.assertTrue(any(row[2] == "channel_repeated_claims" and row[3] == "claim_id" for row in occurrence_fks))
        self.assertTrue(any(row[2] == "posts" and row[3] == "post_id" for row in occurrence_fks))
        self.assertTrue(any(row[2] == "signal_evidence_items" and row[3] == "signal_evidence_item_id" for row in occurrence_fks))
        self.assertTrue(any(row[2] == "channel_narratives" and row[3] == "narrative_id" for row in narrative_claim_fks))
        self.assertTrue(any(row[2] == "channel_repeated_claims" and row[3] == "claim_id" for row in narrative_claim_fks))

    def test_channel_intelligence_schema_accepts_minimal_derived_rows(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON;")
                now = "2026-05-31T12:00:00Z"
                claim_id = connection.execute(
                    """
                    INSERT INTO channel_repeated_claims (
                        claim_key,
                        normalized_claim,
                        status,
                        first_seen_week,
                        last_seen_week,
                        occurrence_count,
                        channel_count,
                        project_name,
                        topic_label,
                        extraction_version,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "claim:local-agents",
                        "Local coding agents are moving into production use.",
                        "repeated",
                        "2026-W21",
                        "2026-W22",
                        2,
                        2,
                        "telegram-research-agent",
                        "Agents",
                        "test-v1",
                        now,
                        now,
                    ),
                ).lastrowid
                narrative_id = connection.execute(
                    """
                    INSERT INTO channel_narratives (
                        narrative_key,
                        title,
                        status,
                        project_name,
                        topic_label,
                        first_seen_week,
                        last_seen_week,
                        supporting_post_count,
                        supporting_channel_count,
                        linked_claim_count,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "narrative:local-agent-prod",
                        "Local agents move toward production",
                        "active",
                        "telegram-research-agent",
                        "Agents",
                        "2026-W21",
                        "2026-W22",
                        3,
                        2,
                        1,
                        now,
                        now,
                    ),
                ).lastrowid
                connection.execute(
                    """
                    INSERT INTO narrative_claim_links (
                        narrative_id,
                        claim_id,
                        link_reason,
                        shared_evidence_count,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (narrative_id, claim_id, "shared evidence rows", 2, now),
                )
                connection.execute(
                    """
                    INSERT INTO source_observations (
                        channel_username,
                        week_label,
                        scope_key,
                        post_count,
                        evidence_count,
                        acted_on_count,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("source_a", "2026-W22", "project:telegram-research-agent", 5, 2, 1, now, now),
                )
                connection.execute(
                    """
                    INSERT INTO channel_intelligence_weekly_rollups (
                        week_label,
                        scope_key,
                        project_name,
                        section_name,
                        item_type,
                        item_id,
                        input_row_ids_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "2026-W22",
                        "project:telegram-research-agent",
                        "telegram-research-agent",
                        "emerging_narratives",
                        "narrative",
                        str(narrative_id),
                        '{"narrative_ids":[1],"claim_ids":[1]}',
                        now,
                        now,
                    ),
                )
                connection.commit()
                linked_count = connection.execute("SELECT COUNT(*) FROM narrative_claim_links").fetchone()[0]
                observation_count = connection.execute("SELECT COUNT(*) FROM source_observations").fetchone()[0]
                rollup_count = connection.execute("SELECT COUNT(*) FROM channel_intelligence_weekly_rollups").fetchone()[0]
        finally:
            os.unlink(db_path)

        self.assertEqual(linked_count, 1)
        self.assertEqual(observation_count, 1)
        self.assertEqual(rollup_count, 1)


if __name__ == "__main__":
    unittest.main()
