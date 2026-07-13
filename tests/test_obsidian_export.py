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
from db.canonical_idea_threads import apply_canonical_lifecycle  # noqa: E402
from db.ai_report_feedback import record_ai_report_feedback  # noqa: E402
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

    def _seed_feedback(self, db_path: str) -> None:
        with sqlite3.connect(db_path) as connection:
            record_ai_report_feedback(
                connection,
                week_label="2026-W28",
                feedback_type="useful",
                target_type="action",
                target_ref="eval-gates",
                source_url="https://t.me/ai_lab/101",
            )

    def _seed_many_pruning_atoms(self, db_path: str, *, count: int = 18) -> None:
        with sqlite3.connect(db_path) as connection:
            for index in range(count):
                record_knowledge_atom(
                    connection,
                    week_label="2026-W28",
                    atom_type="tutorial_resource",
                    claim=f"Noise tutorial {index} has a narrow one-off AI workflow detail.",
                    summary=f"Single-use read item {index} for projection pruning.",
                    evidence_quote=f"one-off detail {index}",
                    source_post_ids=[1000 + index],
                    source_urls=[f"https://t.me/noise_channel_{index}/{1000 + index}"],
                    entities=[f"Noise Entity {index}"],
                    tools=[f"Noise Tool {index}"],
                    models=[f"Noise Model {index}"],
                    practices=[f"Noise Practice {index}"],
                    confidence=0.84,
                    novelty_score=0.81,
                    practical_utility_score=0.89,
                    first_seen_at=f"2026-07-07T{index % 10:02d}:00:00Z",
                    last_seen_at=f"2026-07-07T{index % 10:02d}:00:00Z",
                )

    def _seed_pruning_fixture(self, db_path: str) -> None:
        with sqlite3.connect(db_path) as connection:
            record_knowledge_atom(
                connection,
                week_label="2026-W28",
                atom_type="engineering_practice",
                claim="EvalRig catches unsupported agent claims before release.",
                summary="A repeated source-backed workflow pattern is worth keeping in the vault cockpit.",
                evidence_quote="EvalRig catches unsupported agent claims",
                source_post_ids=[901],
                source_urls=["https://t.me/core_lab/901"],
                entities=["agent evals"],
                tools=["EvalRig"],
                models=[],
                practices=["source-backed checklist"],
                confidence=0.86,
                novelty_score=0.62,
                practical_utility_score=0.91,
                first_seen_at="2026-07-06T08:00:00Z",
                last_seen_at="2026-07-06T08:00:00Z",
            )
            record_knowledge_atom(
                connection,
                week_label="2026-W28",
                atom_type="tutorial_resource",
                claim="A tutorial shows EvalRig wired into CI for source-backed checks.",
                summary="This is a bounded read queue item for the same repeated workflow.",
                evidence_quote="EvalRig wired into CI",
                source_post_ids=[902],
                source_urls=["https://t.me/core_lab/902"],
                entities=["agent evals"],
                tools=["EvalRig"],
                models=[],
                practices=["source-backed checklist"],
                confidence=0.82,
                novelty_score=0.8,
                practical_utility_score=0.9,
                first_seen_at="2026-07-07T09:00:00Z",
                last_seen_at="2026-07-07T09:00:00Z",
            )
            for index in range(14):
                record_knowledge_atom(
                    connection,
                    week_label="2026-W28",
                    atom_type="market_signal",
                    claim=f"One-off low-signal noise item {index}.",
                    summary="This should not become a term or channel note.",
                    evidence_quote=f"noise item {index}",
                    source_post_ids=[1000 + index],
                    source_urls=[f"https://t.me/noise{index}/{1000 + index}"],
                    entities=[f"noise entity {index}"],
                    tools=[f"NoiseTool{index}"],
                    models=[],
                    practices=[f"one-off practice {index}"],
                    confidence=0.34,
                    novelty_score=0.22,
                    practical_utility_score=0.24,
                    first_seen_at="2026-07-07T10:00:00Z",
                    last_seen_at="2026-07-07T10:00:00Z",
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
            now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
        )
        return settings

    def test_export_writes_generated_notes_with_sources_and_is_idempotent(self):
        db_path = self._make_db()
        self._seed_atoms(db_path)
        self._seed_feedback(db_path)
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
                try_build_note = Path(vault_dir) / "65-try-build" / "2026-W28-try-build.md"
                project_watch_note = Path(vault_dir) / "75-project-watch" / "2026-W28-project-watch.md"
                feedback_note = Path(vault_dir) / "80-feedback" / "2026-W28-feedback-summary.md"
                strategy_note = Path(vault_dir) / "85-strategy" / "2026-W28-strategy-review.md"
                manifest = Path(vault_dir) / "90-generated" / "export-manifest-2026-W28.json"
                weekly_exists = weekly_note.exists()
                codex_exists = codex_note.exists()
                practice_exists = practice_note.exists()
                ai_lab_exists = ai_lab_note.exists()
                try_build_exists = try_build_note.exists()
                project_watch_exists = project_watch_note.exists()
                feedback_exists = feedback_note.exists()
                strategy_exists = strategy_note.exists()
                manifest_exists = manifest.exists()
                weekly_text = weekly_note.read_text(encoding="utf-8")
                thread_text = thread_note.read_text(encoding="utf-8")
                experiment_text = experiment_notes[0].read_text(encoding="utf-8")
                try_build_text = try_build_note.read_text(encoding="utf-8")
                project_watch_text = project_watch_note.read_text(encoding="utf-8")
                feedback_text = feedback_note.read_text(encoding="utf-8")
                strategy_text = strategy_note.read_text(encoding="utf-8")
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
        self.assertTrue(try_build_exists)
        self.assertTrue(project_watch_exists)
        self.assertTrue(feedback_exists)
        self.assertTrue(strategy_exists)
        self.assertTrue(manifest_exists)
        self.assertTrue(weekly_text.startswith("---\n"))
        self.assertIn(GENERATED_MARKER, weekly_text)
        self.assertIn("[[00-dashboard/index|Dashboard]]", weekly_text)
        self.assertIn("2026-W28.html", weekly_text)
        self.assertIn("## Read Queue", weekly_text)
        self.assertIn("## Try Items", weekly_text)
        self.assertIn("## Build Candidates", weekly_text)
        self.assertIn("[[65-try-build/2026-W28-try-build|Try / Build candidates]]", weekly_text)
        self.assertIn("## Experiment", weekly_text)
        self.assertIn("## Project Watch", weekly_text)
        self.assertIn("[[75-project-watch/2026-W28-project-watch|Project watch]]", weekly_text)
        self.assertIn("## Feedback And Strategy", weekly_text)
        self.assertIn("[[80-feedback/2026-W28-feedback-summary|Feedback summary]]", weekly_text)
        self.assertIn("[[85-strategy/2026-W28-strategy-review|Strategy Reviewer]]", weekly_text)
        self.assertIn(GENERATED_MARKER, thread_text)
        self.assertIn("[[10-weekly/2026-W28|2026-W28]]", thread_text)
        self.assertIn("2026-W28.html#thread-", thread_text)
        self.assertIn("https://t.me/ai_lab/101", thread_text)
        self.assertNotIn("raw_posts", thread_text)
        self.assertIn("## Hypothesis", experiment_text)
        self.assertIn("## Method", experiment_text)
        self.assertIn("## Result", experiment_text)
        self.assertIn("## Decision", experiment_text)
        self.assertIn("## Project Link", experiment_text)
        self.assertIn("## Try", try_build_text)
        self.assertIn("## Build Candidates", try_build_text)
        self.assertIn("## Project Watch", project_watch_text)
        self.assertIn("## Counts", feedback_text)
        self.assertIn("useful: 1", feedback_text)
        self.assertIn("## Codex Tasks", strategy_text)
        self.assertIn("## Mutation Policy", strategy_text)

    def test_raw_thread_note_path_survives_additive_canonical_attribution(self):
        db_path = self._make_db()
        self._seed_atoms(db_path)
        with tempfile.TemporaryDirectory() as vault_dir, tempfile.TemporaryDirectory() as report_root:
            try:
                settings = self._prepare_context(db_path, report_root)
                with sqlite3.connect(db_path) as connection:
                    raw = connection.execute(
                        "SELECT id, slug FROM idea_threads ORDER BY id LIMIT 1"
                    ).fetchone()
                    memberships = [
                        {"atom_id": int(row[0]), "raw_thread_id": int(raw[0])}
                        for row in connection.execute(
                            """
                            SELECT atom_id FROM idea_thread_atoms
                            WHERE thread_id = ? ORDER BY atom_id
                            """,
                            (int(raw[0]),),
                        ).fetchall()
                    ]
                    result = apply_canonical_lifecycle(
                        connection,
                        proposal={
                            "operation": "create",
                            "thread": {
                                "stable_slug": "canonical-eval-gated-release",
                                "title_ru": "Канонический eval-релиз",
                                "title_en": "Canonical eval-gated release",
                                "thesis": "Eval gates make agent releases safer.",
                                "status": "active",
                                "first_seen_at": "2026-07-06T08:00:00Z",
                                "last_seen_at": "2026-07-07T10:00:00Z",
                                "evidence_maturity": "multi_channel",
                                "operator_interest": 0.6,
                                "entities": ["Codex", "Claude"],
                            },
                            "atom_memberships": memberships,
                        },
                        run_id="obsidian-canonical-create",
                        model="deterministic-test-curator",
                        model_version="1",
                        curator_version="irx4-test.v1",
                        reason="Obsidian compatibility fixture",
                        event_at="2026-07-11T00:00:00Z",
                    )
                first = export_obsidian_vault(
                    settings,
                    week_label="2026-W28",
                    vault_path=vault_dir,
                    report_root=report_root,
                )
                raw_path = Path(vault_dir) / "20-idea-threads" / f"{raw[1]}.md"
                first_text = raw_path.read_text(encoding="utf-8")
                second = export_obsidian_vault(
                    settings,
                    week_label="2026-W28",
                    vault_path=vault_dir,
                    report_root=report_root,
                )
                second_text = raw_path.read_text(encoding="utf-8")
                canonical_path_exists = (
                    Path(vault_dir)
                    / "20-idea-threads"
                    / "canonical-eval-gated-release.md"
                ).exists()
            finally:
                os.unlink(db_path)

        canonical_id = result["affected_thread_ids"][0]
        self.assertEqual(first.files_written, second.files_written)
        self.assertIn("## Canonical Registry", first_text)
        self.assertIn(
            "canonical_thread:canonical-eval-gated-release",
            first_text,
        )
        self.assertIn(str(canonical_id), first_text)
        self.assertIn(f'slug: "{raw[1]}"', first_text)
        self.assertIn("canonical_membership_resolved", second_text)
        self.assertFalse(canonical_path_exists)

    def test_export_prunes_one_off_terms_channels_and_read_notes(self):
        db_path = self._make_db()
        self._seed_many_pruning_atoms(db_path)
        with tempfile.TemporaryDirectory() as vault_dir, tempfile.TemporaryDirectory() as report_root:
            try:
                settings = self._prepare_context(db_path, report_root)
                summary = export_obsidian_vault(
                    settings,
                    week_label="2026-W28",
                    vault_path=vault_dir,
                    report_root=report_root,
                    threads_limit=100,
                )
                vault = Path(vault_dir)
                weekly_text = (vault / "10-weekly" / "2026-W28.md").read_text(encoding="utf-8")
                tool_model_notes = list((vault / "30-tools-models").glob("*.md"))
                practice_notes = list((vault / "40-practices").glob("*.md"))
                channel_notes = list((vault / "50-channels").glob("*.md"))
                read_notes = list((vault / "60-read-queue").glob("*.md"))
                experiment_notes = list((vault / "70-experiments").glob("*.md"))
                experiment_text = experiment_notes[0].read_text(encoding="utf-8")
            finally:
                os.unlink(db_path)

        self.assertLessEqual(summary.thread_count, 12)
        self.assertLessEqual(len(tool_model_notes), 8)
        self.assertLessEqual(len(practice_notes), 8)
        self.assertLessEqual(len(channel_notes), 8)
        self.assertLessEqual(len(read_notes), 5)
        self.assertEqual(len(experiment_notes), 1)
        self.assertIn("## Read Queue", weekly_text)
        self.assertIn("## Try Items", weekly_text)
        self.assertIn("## Experiment", weekly_text)
        self.assertIn("## Project Watch", weekly_text)
        self.assertIn("## Hypothesis", experiment_text)
        self.assertIn("## Method", experiment_text)
        self.assertIn("## Result", experiment_text)
        self.assertIn("## Decision", experiment_text)
        self.assertIn("## Manual Promotion", experiment_text)

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

    def test_export_prunes_noisy_terms_channels_and_templates_experiment(self):
        db_path = self._make_db()
        self._seed_pruning_fixture(db_path)
        with tempfile.TemporaryDirectory() as vault_dir, tempfile.TemporaryDirectory() as report_root:
            try:
                settings = self._prepare_context(db_path, report_root)
                summary = export_obsidian_vault(
                    settings,
                    week_label="2026-W28",
                    vault_path=vault_dir,
                    report_root=report_root,
                )
                root = Path(vault_dir)
                weekly_text = (root / "10-weekly" / "2026-W28.md").read_text(encoding="utf-8")
                experiment_note = next((root / "70-experiments").glob("*.md"))
                experiment_text = experiment_note.read_text(encoding="utf-8")
                term_files = sorted((root / "30-tools-models").glob("*.md"))
                practice_files = sorted((root / "40-practices").glob("*.md"))
                channel_files = sorted((root / "50-channels").glob("*.md"))
                thread_files = sorted((root / "20-idea-threads").glob("*.md"))
                evalrig_exists = (root / "30-tools-models" / "evalrig.md").exists()
                noise_tool_exists = (root / "30-tools-models" / "noisetool0.md").exists()
                noise_channel_exists = (root / "50-channels" / "noise0.md").exists()
            finally:
                os.unlink(db_path)

        self.assertLessEqual(summary.files_written, 20)
        self.assertLessEqual(len(thread_files), 2)
        self.assertLessEqual(len(term_files) + len(practice_files), 4)
        self.assertLessEqual(len(channel_files), 2)
        self.assertFalse((root / "source-posts").exists())
        self.assertFalse([path for path in root.rglob("*.md") if path.stem in {str(1000 + index) for index in range(14)}])
        self.assertTrue(evalrig_exists)
        self.assertFalse(noise_tool_exists)
        self.assertFalse(noise_channel_exists)
        self.assertIn("## Read Queue", weekly_text)
        self.assertIn("[[60-read-queue/", weekly_text)
        self.assertIn("## Try Items", weekly_text)
        self.assertIn("## Experiment", weekly_text)
        self.assertIn("[[70-experiments/", weekly_text)
        self.assertIn("## Project Watch", weekly_text)
        self.assertIn("## Hypothesis", experiment_text)
        self.assertIn("## Method", experiment_text)
        self.assertIn("## Result", experiment_text)
        self.assertIn("## Decision", experiment_text)
        self.assertIn("## Project Link", experiment_text)
        self.assertIn("## Manual Promotion", experiment_text)
        self.assertIn(GENERATED_MARKER, experiment_text)


if __name__ == "__main__":
    unittest.main()
