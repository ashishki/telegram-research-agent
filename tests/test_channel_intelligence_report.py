import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from db.migrate import run_migrations
from output.channel_intelligence_report import render_channel_intelligence_report


class TestChannelIntelligenceReport(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def test_render_report_includes_citations_weak_labels_and_input_ids(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON;")
                claim_id = connection.execute(
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
                        "claim:report",
                        "report claim",
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
                        "[1, 2]",
                        "{}",
                        "fixture",
                        "2026-05-29T10:00:00Z",
                        "2026-05-29T10:00:00Z",
                    ),
                ).lastrowid
                weak_claim_id = connection.execute(
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
                        "claim:weak-report",
                        "weak report claim",
                        "single_occurrence",
                        "weak",
                        "weak",
                        "2026-W22",
                        "2026-W22",
                        1,
                        1,
                        "telegram-research-agent",
                        "Agents",
                        "[]",
                        "[3]",
                        "{}",
                        "fixture",
                        "2026-05-29T10:00:00Z",
                        "2026-05-29T10:00:00Z",
                    ),
                ).lastrowid
                connection.execute(
                    """
                    INSERT INTO claim_occurrences (
                        claim_id,
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
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        claim_id,
                        "2026-W22",
                        "source_a",
                        "https://t.me/source_a/100",
                        "2026-05-25T09:00:00Z",
                        "report claim",
                        "fixture",
                        "telegram-research-agent",
                        "Agents",
                        "fixture",
                        "2026-05-29T10:00:00Z",
                    ),
                )
                narrative_id = connection.execute(
                    """
                    INSERT INTO channel_narratives (
                        narrative_key,
                        title,
                        summary,
                        status,
                        project_name,
                        topic_label,
                        first_seen_week,
                        last_seen_week,
                        supporting_post_count,
                        supporting_channel_count,
                        linked_claim_count,
                        evidence_item_ids_json,
                        source_channels_json,
                        refresh_scope_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "narrative:report",
                        "Agents signals for telegram-research-agent in 2026-W22",
                        "fixture",
                        "active",
                        "telegram-research-agent",
                        "Agents",
                        "2026-W22",
                        "2026-W22",
                        2,
                        2,
                        1,
                        "[1, 2]",
                        '["source_a"]',
                        "{}",
                        "2026-05-29T10:00:00Z",
                        "2026-05-29T10:00:00Z",
                    ),
                ).lastrowid
                connection.execute(
                    """
                    INSERT INTO narrative_claim_links (
                        narrative_id,
                        claim_id,
                        link_reason,
                        shared_evidence_count,
                        shared_entities_json,
                        confidence,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (narrative_id, claim_id, "fixture", 2, '["Agents"]', 0.9, "2026-05-29T10:00:00Z"),
                )
                connection.execute(
                    """
                    INSERT INTO source_observations (
                        channel_username,
                        week_label,
                        scope_key,
                        project_name,
                        topic_label,
                        post_count,
                        scored_count,
                        evidence_count,
                        cited_count,
                        acted_on_count,
                        skipped_count,
                        rejected_count,
                        low_signal_count,
                        repeated_claim_count,
                        useful_count,
                        counters_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "source_a",
                        "2026-W22",
                        "project:telegram-research-agent|topic:Agents",
                        "telegram-research-agent",
                        "Agents",
                        3,
                        3,
                        0,
                        0,
                        0,
                        1,
                        0,
                        3,
                        1,
                        0,
                        '{"post_ids":[1,2,3]}',
                        "2026-05-29T10:00:00Z",
                        "2026-05-29T10:00:00Z",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO project_intelligence_links (
                        project_name,
                        linked_object_type,
                        linked_object_id,
                        week_label,
                        relevance_score,
                        match_reason,
                        evidence_item_ids_json,
                        active_project,
                        refresh_scope_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "telegram-research-agent",
                        "narrative",
                        str(narrative_id),
                        "2026-W22",
                        0.9,
                        "fixture",
                        "[1, 2]",
                        1,
                        "{}",
                        "2026-05-29T10:00:00Z",
                        "2026-05-29T10:00:00Z",
                    ),
                )
                connection.commit()

                report = render_channel_intelligence_report(
                    connection,
                    week_label="2026-W22",
                    project_name="telegram-research-agent",
                    topic_label="Agents",
                    limit=10,
                )
        finally:
            os.unlink(db_path)

        self.assertIn("# Channel Intelligence Report - 2026-W22", report)
        self.assertIn("source_of_truth: derived SQLite rows", report)
        self.assertIn(f"narrative_id={narrative_id}", report)
        self.assertIn(f"claim_id={claim_id}", report)
        self.assertIn(f"claim_id={weak_claim_id} [weak-evidence]", report)
        self.assertIn("https://t.me/source_a/100", report)
        self.assertIn("source_observation_id=", report)
        self.assertIn("[weak-evidence]: source_a", report)
        self.assertIn("input_row_ids:", report)
        self.assertIn("project_link_id=", report)


if __name__ == "__main__":
    unittest.main()
