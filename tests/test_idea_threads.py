import io
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

from config.settings import Settings  # noqa: E402
from db.idea_threads import fetch_idea_thread_atoms, fetch_idea_threads  # noqa: E402
from db.knowledge_atoms import record_knowledge_atom  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
from output.idea_threads import refresh_idea_threads  # noqa: E402
import main  # noqa: E402


class TestIdeaThreads(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name
        with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
            run_migrations()
        return db_path

    def _settings(self, db_path: str) -> Settings:
        return Settings(
            db_path=db_path,
            llm_api_key="",
            model_provider="",
            telegram_session_path="",
        )

    def _seed_atoms(self, db_path: str) -> None:
        with sqlite3.connect(db_path) as connection:
            record_knowledge_atom(
                connection,
                week_label="2026-W28",
                atom_type="engineering_practice",
                claim="Eval gates are becoming the release path for coding agents.",
                summary="A source describes eval gates before agent-written releases.",
                evidence_quote="eval gates before release",
                source_post_ids=[101],
                source_urls=["https://t.me/ai_lab/101"],
                entities=["AI agents", "eval gates"],
                tools=["Codex"],
                practices=["eval-gated release"],
                confidence=0.82,
                practical_utility_score=0.9,
                first_seen_at="2026-07-06T08:00:00Z",
                last_seen_at="2026-07-06T08:00:00Z",
            )
            record_knowledge_atom(
                connection,
                week_label="2026-W28",
                atom_type="workflow_pattern",
                claim="Teams now pair coding-agent changes with eval-gated deploys.",
                summary="A second channel repeats the same workflow pattern.",
                evidence_quote="coding-agent changes with eval-gated deploys",
                source_post_ids=[202],
                source_urls=["https://t.me/ml_ops/202"],
                entities=["AI agents", "eval gates"],
                tools=["Codex"],
                practices=["eval-gated release"],
                confidence=0.76,
                practical_utility_score=0.86,
                first_seen_at="2026-07-07T09:00:00Z",
                last_seen_at="2026-07-07T09:00:00Z",
            )
            record_knowledge_atom(
                connection,
                week_label="2026-W22",
                atom_type="research_claim",
                claim="Browser agents briefly looked like the default automation path.",
                summary="An older claim should remain inspectable even when the thread is stale.",
                evidence_quote="browser agents briefly looked like the default",
                source_post_ids=[303],
                source_urls=["https://t.me/automation/303"],
                entities=["browser agents"],
                tools=["Browser agents"],
                practices=["browser automation"],
                confidence=0.62,
                practical_utility_score=0.45,
                first_seen_at="2026-05-20T10:00:00Z",
                last_seen_at="2026-05-20T10:00:00Z",
            )

    def test_migration_creates_idea_thread_tables_indexes_and_fk(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                table_names = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                thread_columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(idea_threads)").fetchall()
                }
                link_columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(idea_thread_atoms)").fetchall()
                }
                index_names = {
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type = 'index'
                          AND tbl_name IN ('idea_threads', 'idea_thread_atoms')
                        """
                    ).fetchall()
                }
                link_fks = connection.execute("PRAGMA foreign_key_list(idea_thread_atoms)").fetchall()
        finally:
            os.unlink(db_path)

        self.assertIn("idea_threads", table_names)
        self.assertIn("idea_thread_atoms", table_names)
        for column in [
            "slug",
            "status",
            "momentum_7d",
            "momentum_30d",
            "momentum_90d",
            "source_channels_json",
            "current_claims_json",
            "contradictions_json",
        ]:
            self.assertIn(column, thread_columns)
        for column in ["thread_id", "atom_id", "relation", "created_at"]:
            self.assertIn(column, link_columns)
        for index in [
            "idx_idea_threads_slug",
            "idx_idea_threads_status",
            "idx_idea_threads_last_seen",
            "idx_idea_thread_atoms_atom",
        ]:
            self.assertIn(index, index_names)
        self.assertTrue(any(row[2] == "idea_threads" and row[3] == "thread_id" for row in link_fks))
        self.assertTrue(any(row[2] == "knowledge_atoms" and row[3] == "atom_id" for row in link_fks))

    def test_refresh_groups_repeated_atoms_and_preserves_stale_evidence(self):
        db_path = self._make_db()
        self._seed_atoms(db_path)
        now = datetime(2026, 7, 8, tzinfo=timezone.utc)
        try:
            summary = refresh_idea_threads(self._settings(db_path), weeks=12, now=now)
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                threads = fetch_idea_threads(connection, limit=10)
                active_thread = next(thread for thread in threads if thread["atom_count"] == 2)
                stale_thread = next(thread for thread in threads if thread["status"] == "stale")
                active_atoms = fetch_idea_thread_atoms(connection, thread_id=active_thread["id"], limit=10)
                stale_atoms = fetch_idea_thread_atoms(connection, thread_id=stale_thread["id"], limit=10)
        finally:
            os.unlink(db_path)

        self.assertEqual(summary.atoms_seen, 3)
        self.assertEqual(summary.threads_refreshed, 2)
        self.assertEqual(summary.links_refreshed, 3)
        self.assertEqual(active_thread["status"], "active")
        self.assertEqual(active_thread["atom_count"], 2)
        self.assertEqual(active_thread["source_channel_count"], 2)
        self.assertEqual(active_thread["source_channels"], ["ai_lab", "ml_ops"])
        self.assertGreater(active_thread["momentum_7d"], 0.0)
        self.assertEqual([atom["relation"] for atom in active_atoms], ["supports", "supports"])
        self.assertEqual(stale_thread["atom_count"], 1)
        self.assertEqual(len(stale_atoms), 1)
        self.assertIn("Browser agents", stale_atoms[0]["claim"])

    def test_mixed_current_and_superseded_atoms_keep_thread_active(self):
        db_path = self._make_db()
        with sqlite3.connect(db_path) as connection:
            record_knowledge_atom(
                connection,
                week_label="2026-W28",
                atom_type="engineering_practice",
                claim="Eval gates are now the practical default for coding-agent releases.",
                evidence_quote="practical default for coding-agent releases",
                source_post_ids=[401],
                source_urls=["https://t.me/ai_lab/401"],
                entities=["AI agents", "eval gates"],
                tools=["Codex"],
                practices=["eval-gated release"],
                confidence=0.82,
                practical_utility_score=0.9,
                first_seen_at="2026-07-07T08:00:00Z",
                last_seen_at="2026-07-07T08:00:00Z",
            )
            record_knowledge_atom(
                connection,
                week_label="2026-W27",
                atom_type="research_claim",
                claim="Manual spot checks were enough for coding-agent release safety.",
                evidence_quote="manual spot checks were enough",
                source_post_ids=[402],
                source_urls=["https://t.me/ml_ops/402"],
                entities=["AI agents", "eval gates"],
                tools=["Codex"],
                practices=["eval-gated release"],
                confidence=0.5,
                practical_utility_score=0.3,
                staleness_status="superseded",
                first_seen_at="2026-07-01T08:00:00Z",
                last_seen_at="2026-07-01T08:00:00Z",
            )
        try:
            refresh_idea_threads(
                self._settings(db_path),
                weeks=12,
                now=datetime(2026, 7, 8, tzinfo=timezone.utc),
            )
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                thread = fetch_idea_threads(connection, limit=1)[0]
                atoms = fetch_idea_thread_atoms(connection, thread_id=thread["id"], limit=10)
        finally:
            os.unlink(db_path)

        self.assertEqual(thread["status"], "active")
        self.assertEqual(thread["atom_count"], 2)
        self.assertIn("Manual spot checks", thread["superseded_claims"][0])
        self.assertEqual({atom["relation"] for atom in atoms}, {"supports", "supersedes"})

    def test_atom_level_stale_status_marks_thread_stale(self):
        db_path = self._make_db()
        with sqlite3.connect(db_path) as connection:
            record_knowledge_atom(
                connection,
                week_label="2026-W28",
                atom_type="research_claim",
                claim="A workflow claim was recently revisited but is now stale.",
                evidence_quote="recently revisited but is now stale",
                source_post_ids=[501],
                source_urls=["https://t.me/research/501"],
                entities=["workflow claim"],
                confidence=0.6,
                staleness_status="stale",
                first_seen_at="2026-07-07T08:00:00Z",
                last_seen_at="2026-07-07T08:00:00Z",
            )
        try:
            refresh_idea_threads(
                self._settings(db_path),
                weeks=12,
                now=datetime(2026, 7, 8, tzinfo=timezone.utc),
            )
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                thread = fetch_idea_threads(connection, limit=1)[0]
                atoms = fetch_idea_thread_atoms(connection, thread_id=thread["id"], limit=10)
        finally:
            os.unlink(db_path)

        self.assertEqual(thread["status"], "stale")
        self.assertEqual(len(atoms), 1)
        self.assertIn("workflow claim", atoms[0]["claim"])

    def test_idea_threads_cli_refreshes_threads(self):
        db_path = self._make_db()
        self._seed_atoms(db_path)
        stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(sys, "argv", ["main.py", "idea-threads", "--weeks", "12"]):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
            with sqlite3.connect(db_path) as connection:
                thread_count = connection.execute("SELECT COUNT(*) FROM idea_threads").fetchone()[0]
                link_count = connection.execute("SELECT COUNT(*) FROM idea_thread_atoms").fetchone()[0]
        finally:
            os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Idea thread refresh summary", output)
        self.assertIn("atoms_seen=3", output)
        self.assertEqual(thread_count, 2)
        self.assertEqual(link_count, 3)

    def test_memory_inspect_idea_threads_prints_timeline_atoms(self):
        db_path = self._make_db()
        self._seed_atoms(db_path)
        refresh_idea_threads(
            self._settings(db_path),
            weeks=12,
            now=datetime(2026, 7, 8, tzinfo=timezone.utc),
        )
        stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(
                    sys,
                    "argv",
                    ["main.py", "memory", "inspect-idea-threads", "--status", "active"],
                ):
                    with redirect_stdout(stdout):
                        exit_code = main.main()
        finally:
            os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Idea Thread inspection", output)
        self.assertIn("source_of_truth: idea_threads, idea_thread_atoms, knowledge_atoms", output)
        self.assertIn("threads (1):", output)
        self.assertIn("IdeaThread", output)
        self.assertIn("timeline_atoms (2):", output)
        self.assertIn("https://t.me/ai_lab/101", output)
        self.assertIn("Teams now pair coding-agent changes", output)


if __name__ == "__main__":
    unittest.main()
