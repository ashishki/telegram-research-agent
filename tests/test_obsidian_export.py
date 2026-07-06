import io
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
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
from db.knowledge_atoms import record_knowledge_atom  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
from output.ai_intelligence_report import generate_ai_intelligence_report  # noqa: E402
from output.idea_threads import refresh_idea_threads  # noqa: E402
from output.obsidian_export import (  # noqa: E402
    GENERATED_MARKER,
    ObsidianExportError,
    export_obsidian_vault,
)
import main  # noqa: E402


class TestObsidianExport(unittest.TestCase):
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
                models=["Claude"],
                practices=["eval-gated release"],
                confidence=0.84,
                novelty_score=0.6,
                practical_utility_score=0.92,
                first_seen_at="2026-07-06T08:00:00Z",
                last_seen_at="2026-07-06T08:00:00Z",
            )
            record_knowledge_atom(
                connection,
                week_label="2026-W28",
                atom_type="tutorial_resource",
                claim="A tutorial shows how to wire coding-agent eval checks into CI.",
                summary="The post is a useful read queue item for eval-gated release setup.",
                evidence_quote="wire coding-agent eval checks into CI",
                source_post_ids=[202],
                source_urls=["https://t.me/ml_ops/202"],
                entities=["AI agents", "eval gates"],
                tools=["Codex"],
                models=["Claude"],
                practices=["eval-gated release"],
                confidence=0.78,
                novelty_score=0.72,
                practical_utility_score=0.88,
                first_seen_at="2026-07-07T09:00:00Z",
                last_seen_at="2026-07-07T09:00:00Z",
            )

    def _prepare_context(self, db_path: str, report_root: str) -> Settings:
        settings = self._settings(db_path)
        refresh_idea_threads(
            settings,
            weeks=12,
            now=datetime(2026, 7, 8, tzinfo=timezone.utc),
        )
        generate_ai_intelligence_report(
            settings,
            week_label="2026-W28",
            output_root=report_root,
            now=datetime(2026, 7, 8, tzinfo=timezone.utc),
        )
        return settings

    def test_export_writes_generated_notes_with_sources_and_is_idempotent(self):
        db_path = self._make_db()
        self._seed_atoms(db_path)
        with tempfile.TemporaryDirectory() as vault_dir, tempfile.TemporaryDirectory() as report_root:
            try:
                settings = self._prepare_context(db_path, report_root)
                first = export_obsidian_vault(
                    settings,
                    week_label="2026-W28",
                    vault_path=vault_dir,
                    report_root=report_root,
                )
                first_files = sorted(path.relative_to(vault_dir) for path in Path(vault_dir).rglob("*.md"))
                second = export_obsidian_vault(
                    settings,
                    week_label="2026-W28",
                    vault_path=vault_dir,
                    report_root=report_root,
                )
                second_files = sorted(path.relative_to(vault_dir) for path in Path(vault_dir).rglob("*.md"))
                weekly_note = Path(vault_dir) / "10-weekly" / "2026-W28.md"
                thread_note = next((Path(vault_dir) / "20-idea-threads").glob("*.md"))
                codex_note = Path(vault_dir) / "30-tools-models" / "codex.md"
                practice_note = Path(vault_dir) / "40-practices" / "eval-gated-release.md"
                ai_lab_note = Path(vault_dir) / "50-channels" / "ai-lab.md"
                read_notes = list((Path(vault_dir) / "60-read-queue").glob("*.md"))
                experiment_notes = list((Path(vault_dir) / "70-experiments").glob("*.md"))
                manifest = Path(vault_dir) / "90-generated" / "export-manifest-2026-W28.json"
                weekly_exists = weekly_note.exists()
                codex_exists = codex_note.exists()
                practice_exists = practice_note.exists()
                ai_lab_exists = ai_lab_note.exists()
                manifest_exists = manifest.exists()
                weekly_text = weekly_note.read_text(encoding="utf-8")
                thread_text = thread_note.read_text(encoding="utf-8")
            finally:
                os.unlink(db_path)

        self.assertEqual(first.files_written, second.files_written)
        self.assertEqual(first_files, second_files)
        self.assertTrue(weekly_exists)
        self.assertTrue(codex_exists)
        self.assertTrue(practice_exists)
        self.assertTrue(ai_lab_exists)
        self.assertTrue(read_notes)
        self.assertTrue(experiment_notes)
        self.assertTrue(manifest_exists)
        self.assertTrue(weekly_text.startswith("---\n"))
        self.assertIn(GENERATED_MARKER, weekly_text)
        self.assertIn("[[00-dashboard/index|Dashboard]]", weekly_text)
        self.assertIn("2026-W28.html", weekly_text)
        self.assertIn(GENERATED_MARKER, thread_text)
        self.assertIn("[[10-weekly/2026-W28|2026-W28]]", thread_text)
        self.assertIn("2026-W28.html#thread-", thread_text)
        self.assertIn("https://t.me/ai_lab/101", thread_text)
        self.assertNotIn("raw_posts", thread_text)

    def test_export_refuses_to_overwrite_hand_authored_notes(self):
        db_path = self._make_db()
        self._seed_atoms(db_path)
        with tempfile.TemporaryDirectory() as vault_dir, tempfile.TemporaryDirectory() as report_root:
            protected = Path(vault_dir) / "10-weekly" / "2026-W28.md"
            protected.parent.mkdir(parents=True)
            protected.write_text("# hand authored\n", encoding="utf-8")
            try:
                settings = self._prepare_context(db_path, report_root)
                with self.assertRaises(ObsidianExportError):
                    export_obsidian_vault(
                        settings,
                        week_label="2026-W28",
                        vault_path=vault_dir,
                        report_root=report_root,
                    )
                protected_text = protected.read_text(encoding="utf-8")
            finally:
                os.unlink(db_path)

        self.assertEqual(protected_text, "# hand authored\n")

    def test_obsidian_export_cli_supports_scoped_namespace(self):
        db_path = self._make_db()
        self._seed_atoms(db_path)
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as vault_dir, tempfile.TemporaryDirectory() as report_root:
            try:
                settings = self._prepare_context(db_path, report_root)
                with patch.dict(os.environ, {"AGENT_DB_PATH": settings.db_path}, clear=False):
                    with patch.object(
                        sys,
                        "argv",
                        [
                            "main.py",
                            "obsidian-export",
                            "--week",
                            "2026-W28",
                            "--vault-path",
                            vault_dir,
                            "--namespace",
                            "_generated/ai-intelligence",
                            "--report-root",
                            report_root,
                        ],
                    ):
                        with redirect_stdout(stdout):
                            exit_code = main.main()
                namespaced_weekly = Path(vault_dir) / "_generated" / "ai-intelligence" / "10-weekly" / "2026-W28.md"
                root_weekly = Path(vault_dir) / "10-weekly" / "2026-W28.md"
                namespaced_exists = namespaced_weekly.exists()
                root_exists = root_weekly.exists()
            finally:
                os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertTrue(namespaced_exists)
        self.assertFalse(root_exists)
        self.assertIn("_generated/ai-intelligence", output)
        self.assertIn("week=2026-W28", output)
        self.assertIn("files=", output)


if __name__ == "__main__":
    unittest.main()
