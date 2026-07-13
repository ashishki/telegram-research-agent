import io
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from unittest.mock import patch


def _install_stub(module_name: str, **attributes: object) -> None:
    module = sys.modules.get(module_name)
    if module is None:
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module
    for name, value in attributes.items():
        setattr(module, name, value)


_install_stub(
    "anthropic",
    APIConnectionError=Exception,
    APIStatusError=Exception,
    APITimeoutError=Exception,
    Anthropic=object,
    RateLimitError=Exception,
)
_install_stub("telethon", TelegramClient=object)
_install_stub("telethon.errors", FloodWaitError=Exception)
_install_stub("weasyprint")
_install_stub("jinja2")
_install_stub("numpy", asarray=lambda value: value)
_install_stub("sklearn")
_install_stub("sklearn.cluster", KMeans=object)
_install_stub("sklearn.feature_extraction")
_install_stub("sklearn.feature_extraction.text", ENGLISH_STOP_WORDS=set(), TfidfVectorizer=object)
_install_stub("sklearn.metrics", silhouette_score=lambda *_args, **_kwargs: 0.0)

from db.knowledge_atoms import record_knowledge_atom, record_knowledge_extraction_batch  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
from llm.client import LLMError  # noqa: E402
import main  # noqa: E402
from output.knowledge_extraction import week_labels_for_lookback  # noqa: E402


FIXED_EXTRACTION_NOW = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)


class TestKnowledgeExtractionCli(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name
        with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
            run_migrations()
            with sqlite3.connect(db_path) as connection:
                self._insert_post(
                    connection,
                    post_id=1,
                    raw_post_id=1,
                    channel_username="@ai_lab",
                    message_id=101,
                    content="Codex headless automation now pairs with eval gates before release.",
                )
                connection.commit()
        return db_path

    def _insert_post(
        self,
        connection: sqlite3.Connection,
        *,
        post_id: int,
        raw_post_id: int,
        channel_username: str,
        message_id: int,
        content: str,
    ) -> None:
        posted_at = "2026-07-06T08:00:00Z"
        connection.execute(
            """
            INSERT INTO raw_posts (
                id, channel_username, channel_id, message_id, posted_at, text, media_type,
                media_caption, forward_from, view_count, message_url, raw_json, ingested_at, image_description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                raw_post_id,
                channel_username,
                1000 + raw_post_id,
                message_id,
                posted_at,
                content,
                None,
                None,
                None,
                0,
                None,
                "{}",
                posted_at,
                None,
            ),
        )
        connection.execute(
            """
            INSERT INTO posts (
                id, raw_post_id, channel_username, posted_at, content, url_count, has_code,
                language_detected, word_count, normalized_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id,
                raw_post_id,
                channel_username,
                posted_at,
                content,
                0,
                0,
                "en",
                len(content.split()),
                posted_at,
            ),
        )

    def _atom_payload(self) -> str:
        return json.dumps(
            {
                "atoms": [
                    {
                        "atom_type": "engineering_practice",
                        "claim": "Codex headless automation is being paired with eval gates.",
                        "summary": "A source post describes headless automation with eval release gates.",
                        "evidence_quote": "pairs with eval gates before release",
                        "source_post_ids": [1],
                        "entities": ["Codex", "eval gates"],
                        "tools": ["Codex"],
                        "models": [],
                        "practices": ["eval-gated release"],
                        "confidence": 0.8,
                        "novelty_score": 0.6,
                        "practical_utility_score": 0.9,
                        "frontier_relevance_score": 0.5,
                        "operator_relevance_score": 0.7,
                        "staleness_status": "active",
                        "why_it_matters": "Useful for AI systems engineering release discipline.",
                    }
                ]
            }
        )

    @patch("output.knowledge_extraction._utc_now", return_value=FIXED_EXTRACTION_NOW)
    def test_knowledge_extract_cli_records_atoms_and_batches(self, _fixed_now):
        db_path = self._make_db()
        stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch("output.knowledge_extraction.complete", return_value=self._atom_payload()):
                    with patch.object(
                        sys,
                        "argv",
                        ["main.py", "knowledge-extract", "--weeks", "1", "--model", "cheap", "--batch-size", "2"],
                    ):
                        with redirect_stdout(stdout):
                            exit_code = main.main()
            with sqlite3.connect(db_path) as connection:
                atom_row = connection.execute(
                    "SELECT atom_type, source_urls_json FROM knowledge_atoms"
                ).fetchone()
                batch_row = connection.execute(
                    "SELECT status, post_count FROM knowledge_extraction_batches"
                ).fetchone()
        finally:
            os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Knowledge extraction summary", output)
        self.assertIn("atoms_recorded=1", output)
        self.assertEqual(atom_row[0], "engineering_practice")
        self.assertEqual(json.loads(atom_row[1]), ["https://t.me/ai_lab/101"])
        self.assertEqual(batch_row[0], "completed")
        self.assertEqual(batch_row[1], 1)

    @patch("output.knowledge_extraction._utc_now", return_value=FIXED_EXTRACTION_NOW)
    def test_knowledge_extract_skips_completed_batches(self, _fixed_now):
        db_path = self._make_db()
        first_stdout = io.StringIO()
        second_stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch("output.knowledge_extraction.complete", return_value=self._atom_payload()):
                    with patch.object(
                        sys,
                        "argv",
                        ["main.py", "knowledge-extract", "--weeks", "1", "--model", "cheap", "--batch-size", "2"],
                    ):
                        with redirect_stdout(first_stdout):
                            first_exit = main.main()
                with patch("output.knowledge_extraction.complete", side_effect=AssertionError("should skip")):
                    with patch.object(
                        sys,
                        "argv",
                        ["main.py", "knowledge-extract", "--weeks", "1", "--model", "cheap", "--batch-size", "2"],
                    ):
                        with redirect_stdout(second_stdout):
                            second_exit = main.main()
            with sqlite3.connect(db_path) as connection:
                atom_count = connection.execute("SELECT COUNT(*) FROM knowledge_atoms").fetchone()[0]
        finally:
            os.unlink(db_path)

        self.assertEqual(first_exit, 0)
        self.assertEqual(second_exit, 0)
        self.assertEqual(atom_count, 1)
        self.assertIn("batches_skipped=1", second_stdout.getvalue())

    @patch("output.knowledge_extraction._utc_now", return_value=FIXED_EXTRACTION_NOW)
    def test_knowledge_extract_marks_batch_failed_on_invalid_json(self, _fixed_now):
        db_path = self._make_db()
        stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch("output.knowledge_extraction.complete", return_value="{not-json"):
                    with patch.object(
                        sys,
                        "argv",
                        ["main.py", "knowledge-extract", "--weeks", "1", "--model", "cheap", "--batch-size", "2"],
                    ):
                        with redirect_stdout(stdout):
                            exit_code = main.main()
            with sqlite3.connect(db_path) as connection:
                batch_row = connection.execute(
                    "SELECT status, error FROM knowledge_extraction_batches"
                ).fetchone()
                atom_count = connection.execute("SELECT COUNT(*) FROM knowledge_atoms").fetchone()[0]
        finally:
            os.unlink(db_path)

        self.assertEqual(exit_code, 1)
        self.assertEqual(batch_row[0], "failed")
        self.assertIn("invalid JSON", batch_row[1])
        self.assertEqual(atom_count, 0)
        self.assertIn("errors=1", stdout.getvalue())

    @patch("output.knowledge_extraction._utc_now", return_value=FIXED_EXTRACTION_NOW)
    def test_knowledge_extract_retries_invalid_json_once(self, _fixed_now):
        db_path = self._make_db()
        stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch(
                    "output.knowledge_extraction.complete",
                    side_effect=["{not-json", self._atom_payload()],
                ) as complete:
                    with patch.object(
                        sys,
                        "argv",
                        ["main.py", "knowledge-extract", "--weeks", "1", "--model", "cheap", "--batch-size", "2"],
                    ):
                        with redirect_stdout(stdout):
                            exit_code = main.main()
            with sqlite3.connect(db_path) as connection:
                batch_row = connection.execute(
                    "SELECT status, error FROM knowledge_extraction_batches"
                ).fetchone()
                atom_count = connection.execute("SELECT COUNT(*) FROM knowledge_atoms").fetchone()[0]
        finally:
            os.unlink(db_path)

        self.assertEqual(exit_code, 0)
        self.assertEqual(complete.call_count, 2)
        self.assertEqual(batch_row[0], "completed")
        self.assertIsNone(batch_row[1])
        self.assertEqual(atom_count, 1)
        self.assertIn("errors=0", stdout.getvalue())

    @patch("output.knowledge_extraction._utc_now", return_value=FIXED_EXTRACTION_NOW)
    def test_knowledge_extract_aborts_on_low_credit_error(self, _fixed_now):
        db_path = self._make_db()
        stdout = io.StringIO()
        quota_error = LLMError("Anthropic completion failed")
        quota_error.__cause__ = RuntimeError("Your credit balance is too low to access the Anthropic API.")
        try:
            with sqlite3.connect(db_path) as connection:
                self._insert_post(
                    connection,
                    post_id=2,
                    raw_post_id=2,
                    channel_username="@ai_lab",
                    message_id=102,
                    content="A second post should not be processed after provider credit exhaustion.",
                )
                connection.commit()
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch("output.knowledge_extraction.complete", side_effect=quota_error) as complete:
                    with patch.object(
                        sys,
                        "argv",
                        ["main.py", "knowledge-extract", "--weeks", "1", "--model", "cheap", "--batch-size", "1"],
                    ):
                        with redirect_stdout(stdout):
                            exit_code = main.main()
            with sqlite3.connect(db_path) as connection:
                batch_rows = connection.execute(
                    "SELECT status, error FROM knowledge_extraction_batches ORDER BY id"
                ).fetchall()
        finally:
            os.unlink(db_path)

        self.assertEqual(exit_code, 1)
        self.assertEqual(complete.call_count, 1)
        self.assertEqual(len(batch_rows), 1)
        self.assertEqual(batch_rows[0][0], "failed")
        self.assertIn("Anthropic completion failed", batch_rows[0][1])
        self.assertIn("batches_total=1", stdout.getvalue())

    def test_lookback_labels_preserve_iso_year_at_calendar_boundary(self):
        labels = week_labels_for_lookback(
            3,
            now=datetime(2024, 12, 31, 23, 59, tzinfo=timezone.utc),
        )

        self.assertEqual(labels, ("2024-W51", "2024-W52", "2025-W01"))

    def test_memory_inspect_knowledge_atoms_prints_batches_and_atoms(self):
        db_path = self._make_db()
        stdout = io.StringIO()
        try:
            with sqlite3.connect(db_path) as connection:
                batch = record_knowledge_extraction_batch(
                    connection,
                    week_label="2026-W28",
                    channel_username="@ai_lab",
                    post_count=1,
                    model="claude-haiku-4-5",
                    prompt_version="knowledge-atoms-v1",
                    status="completed",
                    completed_at="2026-07-06T08:05:00Z",
                )
                record_knowledge_atom(
                    connection,
                    extraction_batch_id=batch["id"],
                    week_label="2026-W28",
                    atom_type="workflow_pattern",
                    claim="Agents are being gated by evals.",
                    evidence_quote="eval gates before release",
                    source_post_ids=[1],
                    source_urls=["https://t.me/ai_lab/101"],
                    confidence=0.7,
                    practical_utility_score=0.8,
                    entities=["agents", "evals"],
                )
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(
                    sys,
                    "argv",
                    ["main.py", "memory", "inspect-knowledge-atoms", "--week", "2026-W28"],
                ):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
        finally:
            os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Knowledge Atom inspection", output)
        self.assertIn("source_of_truth: knowledge_extraction_batches", output)
        self.assertIn("batches (1):", output)
        self.assertIn("atoms (1):", output)
        self.assertIn("KnowledgeAtom", output)
        self.assertIn("Agents are being gated by evals.", output)


if __name__ == "__main__":
    unittest.main()
