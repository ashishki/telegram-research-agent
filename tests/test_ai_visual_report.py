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
from db.frontier_analysis import upsert_frontier_analysis  # noqa: E402
from db.knowledge_atoms import record_knowledge_atom  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
from output.ai_visual_report import generate_ai_visual_report  # noqa: E402
from output.idea_threads import refresh_idea_threads  # noqa: E402
import main  # noqa: E402


class TestAiVisualReport(unittest.TestCase):
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

    def _seed(self, db_path: str) -> Settings:
        settings = self._settings(db_path)
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
                practices=["eval-gated release", "CI checks"],
                confidence=0.84,
                novelty_score=0.6,
                practical_utility_score=0.92,
                why_it_matters="This is actionable for AI engineering release discipline.",
                first_seen_at="2026-07-06T08:00:00Z",
                last_seen_at="2026-07-06T08:00:00Z",
            )
            record_knowledge_atom(
                connection,
                week_label="2026-W28",
                atom_type="market_signal",
                claim="AI rollout teams need measurable adoption evidence.",
                summary="A source describes adoption metrics for working teams.",
                evidence_quote="measurable adoption evidence",
                source_post_ids=[202],
                source_urls=["https://t.me/rollout/202"],
                entities=["AI adoption", "training"],
                tools=["RAG"],
                models=["Claude"],
                practices=["adoption metrics", "manager approval"],
                confidence=0.8,
                novelty_score=0.68,
                practical_utility_score=0.9,
                why_it_matters="It maps to AI rollout project workflows.",
                first_seen_at="2026-07-07T09:00:00Z",
                last_seen_at="2026-07-07T09:00:00Z",
            )
            upsert_frontier_analysis(
                connection,
                week_label="2026-W28",
                generated_at="2026-07-08T00:00:00Z",
                model="claude-opus-4-8",
                prompt_version="frontier-analysis-v1",
                lookback_weeks=12,
                threads_analyzed=2,
                atoms_analyzed=2,
                executive_brief="Top-model synthesis says eval-gated agents and measurable rollout evidence now belong in the same operating system.",
                what_changed=[
                    {
                        "title": "Agent work moved closer to release discipline",
                        "summary": "The thread combines practice, CI, and rollout evidence.",
                        "why_it_matters": "It changes what should be measured before trusting an AI workflow.",
                    }
                ],
                trend_narratives=[
                    {
                        "title": "Eval-gated agent workflows",
                        "narrative": "The idea moved from isolated coding-agent use toward repeatable operations.",
                    }
                ],
                study_now=[
                    {
                        "topic": "Coding-agent eval design",
                        "reason": "It bridges useful demos and reliable team workflows.",
                        "priority": "high",
                    }
                ],
                actions=[
                    {
                        "title": "Build one tiny eval gate",
                        "next_step": "Catch a bad agent edit before merge.",
                        "success_criterion": "A failing edit is blocked.",
                    }
                ],
                caveats=["Evidence is limited to the exported thread set."],
                analysis={},
            )
        refresh_idea_threads(settings, weeks=12, now=datetime(2026, 7, 8, tzinfo=timezone.utc))
        return settings

    def _fake_archify_root(self, root: Path) -> Path:
        archify_root = root / "archify"
        bin_dir = archify_root / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "archify.mjs").write_text(
            """
import fs from 'node:fs';
const [cmd, type, input, output] = process.argv.slice(2);
if (cmd === 'render') {
  const payload = JSON.parse(fs.readFileSync(input, 'utf8'));
  fs.writeFileSync(output, `<!doctype html><html><body><h1>${payload.meta.title}</h1><svg id="archify-diagram"></svg><button>Export</button></body></html>`);
  process.exit(0);
}
if (cmd === 'check') {
  console.log(JSON.stringify({ checks: ['fake-ok'] }));
  process.exit(0);
}
process.exit(2);
""".strip(),
            encoding="utf-8",
        )
        return archify_root

    def test_generates_archify_backed_visual_report(self):
        db_path = self._make_db()
        with tempfile.TemporaryDirectory() as output_dir, tempfile.TemporaryDirectory() as tool_dir:
            try:
                settings = self._seed(db_path)
                archify_root = self._fake_archify_root(Path(tool_dir))
                summary = generate_ai_visual_report(
                    settings,
                    week_label="2026-W28",
                    output_root=output_dir,
                    archify_root=archify_root,
                    now=datetime(2026, 7, 8, tzinfo=timezone.utc),
                )
                html_text = Path(summary.html_path).read_text(encoding="utf-8")
                metadata = json.loads(Path(summary.json_path).read_text(encoding="utf-8"))
                diagram_html_exists = Path(summary.diagram_html_path).exists()
                diagram_ir_exists = Path(summary.diagram_ir_path).exists()
            finally:
                os.unlink(db_path)

        self.assertEqual(summary.archify_status, "rendered")
        self.assertTrue(diagram_html_exists)
        self.assertTrue(diagram_ir_exists)
        self.assertIn("AI Visual Intelligence - 2026-W28", html_text)
        self.assertIn("Knowledge Flow", html_text)
        self.assertIn("Archify", html_text)
        self.assertIn("<iframe", html_text)
        self.assertIn("Project Fit", html_text)
        self.assertIn("Coding-agent eval design", html_text)
        self.assertNotIn("Matches:", html_text)
        self.assertEqual(metadata["archify"]["status"], "rendered")
        self.assertEqual(metadata["diagram_ir"]["diagram_type"], "dataflow")
        self.assertTrue(metadata["project_links"])

    def test_visual_report_falls_back_when_archify_is_missing(self):
        db_path = self._make_db()
        with tempfile.TemporaryDirectory() as output_dir:
            try:
                settings = self._seed(db_path)
                summary = generate_ai_visual_report(
                    settings,
                    week_label="2026-W28",
                    output_root=output_dir,
                    archify_root="/missing/archify",
                    now=datetime(2026, 7, 8, tzinfo=timezone.utc),
                )
                html_text = Path(summary.html_path).read_text(encoding="utf-8")
            finally:
                os.unlink(db_path)

        self.assertEqual(summary.archify_status, "fallback_missing")
        self.assertIn("Archify fallback diagram", html_text)
        self.assertIn("Knowledge Flow", html_text)

    def test_ai_visual_report_cli_can_deliver_document(self):
        db_path = self._make_db()
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as output_dir, tempfile.TemporaryDirectory() as tool_dir:
            try:
                settings = self._seed(db_path)
                archify_root = self._fake_archify_root(Path(tool_dir))
                with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                    with patch("bot.telegram_delivery.send_document", return_value=123) as send_document:
                        with patch.object(
                            sys,
                            "argv",
                            [
                                "main.py",
                                "ai-visual-report",
                                "--week",
                                "2026-W28",
                                "--skip-refresh",
                                "--output-root",
                                output_dir,
                                "--archify-root",
                                str(archify_root),
                                "--deliver",
                                "--chat-id",
                                "@research_channel",
                                "--token",
                                "token",
                            ],
                        ):
                            with redirect_stdout(stdout):
                                exit_code = main.main()
                html_path = Path(output_dir) / "2026-W28.visual.html"
                html_exists = html_path.exists()
            finally:
                os.unlink(db_path)

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertTrue(html_exists)
        self.assertEqual(send_document.call_count, 1)
        self.assertIn("archify=rendered", output)
        self.assertIn("delivered_message_id=123", output)


if __name__ == "__main__":
    unittest.main()
