import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from db.knowledge_atoms import (
    fetch_knowledge_atoms,
    record_knowledge_atom,
    record_knowledge_extraction_batch,
    complete_knowledge_extraction_batch,
)
from db.migrate import run_migrations


class TestKnowledgeAtoms(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def test_migration_creates_knowledge_atom_tables_indexes_and_fk(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                table_names = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                atom_columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(knowledge_atoms)").fetchall()
                }
                batch_columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(knowledge_extraction_batches)").fetchall()
                }
                index_names = {
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type = 'index'
                          AND tbl_name IN ('knowledge_atoms', 'knowledge_extraction_batches')
                        """
                    ).fetchall()
                }
                atom_fks = connection.execute("PRAGMA foreign_key_list(knowledge_atoms)").fetchall()
        finally:
            os.unlink(db_path)

        self.assertIn("knowledge_extraction_batches", table_names)
        self.assertIn("knowledge_atoms", table_names)
        for column in [
            "batch_key",
            "week_label",
            "channel_username",
            "post_count",
            "model",
            "prompt_version",
            "status",
        ]:
            self.assertIn(column, batch_columns)
        for column in [
            "atom_key",
            "extraction_batch_id",
            "atom_type",
            "claim",
            "source_post_ids_json",
            "source_urls_json",
            "entities_json",
            "confidence",
            "novelty_score",
            "practical_utility_score",
            "staleness_status",
        ]:
            self.assertIn(column, atom_columns)
        for index in [
            "idx_knowledge_batches_week",
            "idx_knowledge_batches_status",
            "idx_knowledge_atoms_type",
            "idx_knowledge_atoms_staleness",
            "idx_knowledge_atoms_last_seen",
        ]:
            self.assertIn(index, index_names)
        self.assertTrue(
            any(row[2] == "knowledge_extraction_batches" and row[3] == "extraction_batch_id" for row in atom_fks)
        )

    def test_record_batch_and_atom_round_trip(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON;")
                batch = record_knowledge_extraction_batch(
                    connection,
                    week_label="2026-W28",
                    channel_username="@ai_lab",
                    post_count=12,
                    model="claude-haiku-4-5",
                    prompt_version="knowledge-atoms-v1",
                    started_at="2026-07-06T08:00:00Z",
                )
                atom = record_knowledge_atom(
                    connection,
                    extraction_batch_id=batch["id"],
                    week_label="2026-W28",
                    atom_type="engineering_practice",
                    claim="Eval-driven agent workflows are becoming a practical release discipline.",
                    summary="Multiple posts tie coding-agent adoption to eval suites.",
                    evidence_quote="Teams are adding evals before letting coding agents touch release paths.",
                    source_post_ids=[101, "102"],
                    source_urls=[
                        "https://t.me/ai_lab/101",
                        "https://t.me/ai_lab/102",
                    ],
                    entities=["AI agents", "evals"],
                    tools=["Codex"],
                    practices=["release evals"],
                    confidence=0.82,
                    novelty_score=0.61,
                    practical_utility_score=0.9,
                    frontier_relevance_score=0.7,
                    operator_relevance_score=0.8,
                    why_it_matters="This is directly useful for AI systems engineering workflow design.",
                    first_seen_at="2026-07-06T08:00:00Z",
                    last_seen_at="2026-07-06T09:00:00Z",
                )
                completed = complete_knowledge_extraction_batch(
                    connection,
                    batch_id=batch["id"],
                    completed_at="2026-07-06T09:05:00Z",
                )
                fetched = fetch_knowledge_atoms(connection, week_label="2026-W28")
        finally:
            os.unlink(db_path)

        self.assertEqual(batch["status"], "running")
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(atom["source_post_ids"], [101, 102])
        self.assertEqual(atom["source_urls"][0], "https://t.me/ai_lab/101")
        self.assertEqual(atom["entities"], ["AI agents", "evals"])
        self.assertEqual(atom["confidence"], 0.82)
        self.assertEqual([row["id"] for row in fetched], [atom["id"]])

    def test_atom_upsert_is_idempotent_by_atom_key(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                first = record_knowledge_atom(
                    connection,
                    atom_type="tool_release",
                    claim="A coding tool released a new headless mode.",
                    evidence_quote="New headless mode is available for automation.",
                    source_post_ids=[201],
                    source_urls=["https://t.me/tools/201"],
                    confidence=0.5,
                    first_seen_at="2026-07-06T08:00:00Z",
                    last_seen_at="2026-07-06T08:00:00Z",
                )
                second = record_knowledge_atom(
                    connection,
                    atom_type="tool_release",
                    claim="A coding tool released a new headless mode.",
                    evidence_quote="New headless mode is available for automation.",
                    source_post_ids=[201],
                    source_urls=["https://t.me/tools/201"],
                    confidence=0.75,
                    first_seen_at="2026-07-05T08:00:00Z",
                    last_seen_at="2026-07-07T08:00:00Z",
                )
                row_count = connection.execute("SELECT COUNT(*) FROM knowledge_atoms").fetchone()[0]
        finally:
            os.unlink(db_path)

        self.assertEqual(row_count, 1)
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["confidence"], 0.75)
        self.assertEqual(second["first_seen_at"], "2026-07-05T08:00:00Z")
        self.assertEqual(second["last_seen_at"], "2026-07-07T08:00:00Z")

    def test_atom_requires_source_citations(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                with self.assertRaises(ValueError):
                    record_knowledge_atom(
                        connection,
                        atom_type="research_claim",
                        claim="A claim without sources should not persist.",
                        evidence_quote="No usable citation was present.",
                        source_post_ids=[],
                        source_urls=["https://t.me/research/1"],
                    )
                with self.assertRaises(ValueError):
                    record_knowledge_atom(
                        connection,
                        atom_type="research_claim",
                        claim="A claim without URLs should not persist.",
                        evidence_quote="No usable URL was present.",
                        source_post_ids=[1],
                        source_urls=[],
                    )
        finally:
            os.unlink(db_path)

    def test_schema_rejects_non_array_source_post_ids(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """
                        INSERT INTO knowledge_atoms (
                            atom_key,
                            atom_type,
                            claim,
                            evidence_quote,
                            source_post_ids_json,
                            source_urls_json,
                            first_seen_at,
                            last_seen_at,
                            created_at,
                            updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "knowledge-atom:bad-json",
                            "research_claim",
                            "A malformed atom should fail.",
                            "Malformed source ids.",
                            "{}",
                            '["https://t.me/research/1"]',
                            "2026-07-06T08:00:00Z",
                            "2026-07-06T08:00:00Z",
                            "2026-07-06T08:00:00Z",
                            "2026-07-06T08:00:00Z",
                        ),
                    )
        finally:
            os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()
