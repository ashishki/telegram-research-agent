import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from db.migrate import run_migrations
from db.research_brief_receipts import (
    fetch_research_brief_receipts,
    record_research_brief_receipt,
)


class TestResearchBriefReceipts(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def test_migration_creates_research_brief_receipts_table_and_indexes(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                table_row = connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name = ?
                    """,
                    ("research_brief_receipts",),
                ).fetchone()
                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(research_brief_receipts)"
                    ).fetchall()
                }
                index_names = {
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type = 'index'
                          AND tbl_name = ?
                        ORDER BY name ASC
                        """,
                        ("research_brief_receipts",),
                    ).fetchall()
                }
                foreign_keys = connection.execute(
                    "PRAGMA foreign_key_list(research_brief_receipts)"
                ).fetchall()
        finally:
            os.unlink(db_path)

        self.assertIsNotNone(table_row)
        for column_name in [
            "receipt_id",
            "type",
            "week_label",
            "generated_at",
            "included_channels_json",
            "post_counts_json",
            "source_set_json",
            "project_scopes_json",
            "topic_scopes_json",
            "config_fingerprints_json",
            "digest_id",
            "fallback_delivery",
            "fallback_delivery_used",
            "verification_status",
            "health_flags_json",
            "created_at",
            "updated_at",
        ]:
            self.assertIn(column_name, columns)
        self.assertIn("idx_research_brief_receipts_week_label", index_names)
        self.assertIn("idx_research_brief_receipts_digest_id", index_names)
        self.assertIn("idx_research_brief_receipts_verification_status", index_names)
        self.assertIn("idx_research_brief_receipts_generated_at", index_names)
        self.assertTrue(
            any(
                row[2] == "digests"
                and row[3] == "digest_id"
                and row[4] == "id"
                and row[6].upper() == "SET NULL"
                for row in foreign_keys
            )
        )

    def test_record_and_fetch_receipt_round_trips_json_fields_and_defaults(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON;")
                digest_id = connection.execute(
                    """
                    INSERT INTO digests (
                        week_label,
                        generated_at,
                        content_md,
                        post_count
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    ("2026-W22", "2026-05-29T09:00:00Z", "# Brief", 3),
                ).lastrowid
                connection.commit()

                receipt = record_research_brief_receipt(
                    connection,
                    receipt_id="rbr_test_2026_w22",
                    week_label="2026-W22",
                    generated_at="2026-05-29T10:00:00Z",
                    source_version="abc123",
                    window_start="2026-05-22T00:00:00Z",
                    window_end="2026-05-29T00:00:00Z",
                    included_channels=["@source_a", "@source_b"],
                    post_counts={"total": 3, "strong": 1, "watch": 2},
                    source_set={
                        "telegram_source_links": ["https://t.me/source_a/1"],
                        "source_evidence_item_ids": [101, 102],
                    },
                    project_scopes=["telegram-research-agent"],
                    topic_scopes=["agent-memory"],
                    llm_provider="anthropic",
                    llm_model="claude-test",
                    llm_category="weekly_brief",
                    prompt_template_path="docs/prompts/digest_generation.md",
                    prompt_template_version="sha256:test",
                    config_fingerprints={"projects": "sha256:projects"},
                    generation_params_fingerprint="sha256:params",
                    digest_id=digest_id,
                    markdown_path="data/output/digests/2026-W22.md",
                    json_path="data/output/digests/2026-W22.json",
                    html_path="data/output/digests/2026-W22.html",
                    health_flags=["low_signal_alert"],
                )
                stored = connection.execute(
                    """
                    SELECT included_channels_json, post_counts_json,
                           source_set_json, project_scopes_json,
                           topic_scopes_json, config_fingerprints_json,
                           health_flags_json, verification_status,
                           fallback_delivery_used
                    FROM research_brief_receipts
                    WHERE receipt_id = ?
                    """,
                    ("rbr_test_2026_w22",),
                ).fetchone()
                by_receipt = fetch_research_brief_receipts(
                    connection,
                    receipt_id="rbr_test_2026_w22",
                )
                by_week = fetch_research_brief_receipts(connection, week_label="2026-W22")
                by_digest = fetch_research_brief_receipts(connection, digest_id=digest_id)
                by_status = fetch_research_brief_receipts(
                    connection,
                    verification_status="pending",
                )
        finally:
            os.unlink(db_path)

        self.assertEqual(receipt["receipt_id"], "rbr_test_2026_w22")
        self.assertEqual(receipt["type"], "research_brief_receipt")
        self.assertEqual(receipt["source_project"], "telegram-research-agent")
        self.assertEqual(receipt["verification_status"], "pending")
        self.assertFalse(receipt["fallback_delivery_used"])
        self.assertEqual(receipt["included_channels"], ["@source_a", "@source_b"])
        self.assertEqual(receipt["post_counts"], {"strong": 1, "total": 3, "watch": 2})
        self.assertEqual(
            receipt["source_set"],
            {
                "telegram_source_links": ["https://t.me/source_a/1"],
                "source_evidence_item_ids": [101, 102],
            },
        )
        self.assertEqual(receipt["project_scopes"], ["telegram-research-agent"])
        self.assertEqual(receipt["topic_scopes"], ["agent-memory"])
        self.assertEqual(receipt["config_fingerprints"], {"projects": "sha256:projects"})
        self.assertEqual(receipt["health_flags"], ["low_signal_alert"])
        self.assertEqual(json.loads(stored[0]), ["@source_a", "@source_b"])
        self.assertEqual(json.loads(stored[1]), {"strong": 1, "total": 3, "watch": 2})
        self.assertEqual(json.loads(stored[2])["source_evidence_item_ids"], [101, 102])
        self.assertEqual(json.loads(stored[3]), ["telegram-research-agent"])
        self.assertEqual(json.loads(stored[4]), ["agent-memory"])
        self.assertEqual(json.loads(stored[5]), {"projects": "sha256:projects"})
        self.assertEqual(json.loads(stored[6]), ["low_signal_alert"])
        self.assertEqual(stored[7], "pending")
        self.assertEqual(stored[8], 0)
        self.assertEqual([row["receipt_id"] for row in by_receipt], ["rbr_test_2026_w22"])
        self.assertEqual([row["receipt_id"] for row in by_week], ["rbr_test_2026_w22"])
        self.assertEqual([row["receipt_id"] for row in by_digest], ["rbr_test_2026_w22"])
        self.assertIn("rbr_test_2026_w22", [row["receipt_id"] for row in by_status])

    def test_record_rejects_empty_week_label(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                with self.assertRaises(ValueError):
                    record_research_brief_receipt(connection, week_label="   ")
                count = connection.execute(
                    "SELECT COUNT(*) FROM research_brief_receipts"
                ).fetchone()[0]
        finally:
            os.unlink(db_path)

        self.assertEqual(count, 0)

    def test_record_rejects_unsupported_verification_status(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                with self.assertRaises(ValueError):
                    record_research_brief_receipt(
                        connection,
                        week_label="2026-W22",
                        verification_status="unknown",
                    )
                with self.assertRaises(ValueError):
                    fetch_research_brief_receipts(
                        connection,
                        verification_status="unknown",
                    )
                count = connection.execute(
                    "SELECT COUNT(*) FROM research_brief_receipts"
                ).fetchone()[0]
        finally:
            os.unlink(db_path)

        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
