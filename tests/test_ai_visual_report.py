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
from output.ai_visual_report import _escape, _project_links, generate_ai_visual_report  # noqa: E402
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

    def _insert_post(
        self,
        connection: sqlite3.Connection,
        *,
        post_id: int,
        channel_username: str,
        message_id: int,
        content: str,
    ) -> None:
        posted_at = "2026-07-06T08:00:00Z"
        raw_post_id = post_id + 1000
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
                raw_post_id,
                message_id,
                posted_at,
                content,
                None,
                None,
                None,
                0,
                f"https://t.me/{channel_username}/{message_id}",
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

    def _seed(self, db_path: str) -> Settings:
        settings = self._settings(db_path)
        with sqlite3.connect(db_path) as connection:
            self._insert_post(
                connection,
                post_id=101,
                channel_username="ai_lab",
                message_id=101,
                content="Codex headless automation now pairs with eval gates before release for safer agent edits.",
            )
            self._insert_post(
                connection,
                post_id=202,
                channel_username="rollout",
                message_id=202,
                content="AI rollout teams now ask for measurable adoption evidence before expanding usage.",
            )
            self._insert_post(
                connection,
                post_id=303,
                channel_username="research",
                message_id=303,
                content="The warning is simple: shallow eval suites hide risk in agent-written changes.",
            )
            record_knowledge_atom(
                connection,
                week_label="2026-W28",
                atom_type="engineering_practice",
                claim="Eval-гейты становятся обязательным этапом релиза для coding agents.",
                summary="Источник описывает eval-гейты перед релизом изменений, написанных агентом.",
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
                why_it_matters="Это применимо к дисциплине релизов в AI engineering.",
                first_seen_at="2026-07-06T08:00:00Z",
                last_seen_at="2026-07-06T08:00:00Z",
            )
            record_knowledge_atom(
                connection,
                week_label="2026-W28",
                atom_type="market_signal",
                claim="Командам внедрения AI нужны измеримые доказательства adoption.",
                summary="Источник описывает adoption-метрики для рабочих команд.",
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
                why_it_matters="Это связано с workflow проектов по внедрению AI.",
                first_seen_at="2026-07-07T09:00:00Z",
                last_seen_at="2026-07-07T09:00:00Z",
            )
            record_knowledge_atom(
                connection,
                week_label="2026-W28",
                atom_type="risk_warning",
                claim="Мелкие eval-наборы могут скрывать риск от agent-written изменений.",
                summary="Источник предупреждает, что поверхностные проверки не ловят часть дефектов.",
                evidence_quote="shallow eval suites hide risk",
                source_post_ids=[303],
                source_urls=["https://t.me/research/303"],
                entities=["AI agents", "eval gates"],
                tools=["Codex"],
                models=["Claude"],
                practices=["release checks", "risk review"],
                confidence=0.78,
                novelty_score=0.62,
                practical_utility_score=0.88,
                why_it_matters="Это задает границу доверия к автоматизированным изменениям.",
                first_seen_at="2026-07-07T11:00:00Z",
                last_seen_at="2026-07-07T11:00:00Z",
            )
            upsert_frontier_analysis(
                connection,
                week_label="2026-W28",
                generated_at="2026-07-08T00:00:00Z",
                model="claude-opus-4-8",
                prompt_version="frontier-analysis-v1",
                lookback_weeks=12,
                threads_analyzed=2,
                atoms_analyzed=3,
                executive_brief="Синтез недели: eval-гейты для coding agents и измеримые adoption-метрики теперь нужно читать как одну операционную систему. Главный вывод не в демо, а в проверяемом пути от agent-written изменения до релиза и внедрения.",
                what_changed=[
                    {
                        "title": "Agent work сдвинулся ближе к релизной дисциплине",
                        "summary": "Тема теперь объединяет практику, CI, риск и adoption-доказательства.",
                        "why_it_matters": "Это меняет то, что нужно измерять перед доверием к AI workflow.",
                    }
                ],
                trend_narratives=[
                    {
                        "title": "Eval-gated agent workflows",
                        "narrative": "Идея сдвинулась от одиночного применения coding agents к повторяемым операционным проверкам.",
                    }
                ],
                study_now=[
                    {
                        "topic": "Дизайн eval для coding agents",
                        "reason": "Это мост между полезными демо и надежными командными workflow.",
                        "priority": "high",
                    }
                ],
                actions=[
                    {
                        "title": "Собрать один маленький eval-гейт",
                        "next_step": "Поймать плохое agent-edit изменение до merge.",
                        "success_criterion": "Падающее изменение блокируется до merge.",
                    }
                ],
                caveats=["Доказательства ограничены экспортированным набором тем и требуют проверки цитат."],
                analysis={
                    "source_context": {
                        "run_date": "2026-07-13",
                        "generated_at": "2026-07-13T07:02:52Z",
                        "analysis_period_start": "2026-07-06T00:00:00Z",
                        "analysis_period_end": "2026-07-13T00:00:00Z",
                        "reporting_week": "2026-W28",
                        "week_label": "2026-W28",
                        "period_mode": "explicit_iso_week",
                    }
                },
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
                mvp_json_path = Path(output_dir) / "mvp-weekly-2026-W28.json"
                mvp_json_path.write_text(
                    json.dumps(
                        {
                            "result": {
                                "selected_title": "LLM Guardrail Watchdog",
                                "dossier_status": "investigate",
                                "recommendation": "revisit_with_evidence_gap",
                                "score": 61,
                                "selected_source_mix": {
                                    "readiness": "telegram_only",
                                    "selected_external_evidence_count": 1,
                                    "decision_grade_external": False,
                                    "kir_source_kind": "knowledge_thread",
                                    "kir_thread_slug": "eval-gates",
                                    "kir_thread_title": "Eval gates",
                                    "kir_thread_status": "active",
                                    "kir_source_atom_count": 3,
                                    "kir_source_url_count": 4,
                                    "kir_gate_status": "blocked",
                                    "kir_gate_reasons": ["missing decision-grade external evidence"],
                                },
                                "source_counts": {
                                    "live_intelligence": {
                                        "fresh_sources": 2,
                                    }
                                },
                            },
                            "selected": {
                                "missing_evidence": ["Need stronger non-Telegram demand evidence."],
                                "next_validation": "Interview 3 operators before any build.",
                                "kill_criteria": ["Kill if no operator commits to a follow-up."],
                            },
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                summary = generate_ai_visual_report(
                    settings,
                    week_label="2026-W28",
                    output_root=output_dir,
                    archify_root=archify_root,
                    mvp_radar_json_path=mvp_json_path,
                    now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
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
        self.assertIn("AI-интеллект за неделю: 6-12 июля 2026", html_text)
        self.assertIn("Сгенерировано 2026-07-13T07:02:52Z", html_text)
        self.assertIn("Операторский вердикт", html_text)
        self.assertIn("Сильные сигналы", html_text)
        self.assertIn("Глубокое объяснение", html_text)
        self.assertIn("What is this", html_text)
        self.assertIn("Why now", html_text)
        self.assertIn("How it works", html_text)
        self.assertIn("Where is hype", html_text)
        self.assertIn("What to do", html_text)
        self.assertIn("What not to do", html_text)
        self.assertIn("What would change my mind", html_text)
        self.assertIn("Concept diagram", html_text)
        self.assertIn("concept-diagram", html_text)
        self.assertIn("MVP Radar", html_text)
        self.assertIn("LLM Guardrail Watchdog", html_text)
        self.assertIn("Do not build", html_text)
        self.assertIn("KIR evidence", html_text)
        self.assertIn("External evidence", html_text)
        self.assertIn("context-only", html_text)
        self.assertIn("Читать / пробовать / строить", html_text)
        self.assertIn("Приложение: источники и аудит", html_text)
        self.assertIn("Доказательства по ключевым утверждениям", html_text)
        self.assertIn("Срок годности / staleness", html_text)
        self.assertIn("Wording policy", html_text)
        self.assertIn("Карта потока знаний", html_text)
        self.assertIn("Explanatory only", html_text)
        self.assertIn("Archify", html_text)
        self.assertIn("<iframe", html_text)
        self.assertIn("<details", html_text)
        self.assertIn("Диагностика проектного соответствия", html_text)
        self.assertIn("Дизайн eval для coding agents", html_text)
        self.assertNotIn("Matches:", html_text)
        self.assertLess(len(html_text), 250000)
        self.assertEqual(metadata["run_date"], "2026-07-13")
        self.assertEqual(metadata["reporting_week"], "2026-W28")
        self.assertEqual(metadata["week_label"], "2026-W28")
        self.assertEqual(metadata["period_mode"], "explicit_iso_week")
        self.assertEqual(metadata["analysis_period_start"], "2026-07-06T00:00:00Z")
        self.assertEqual(metadata["analysis_period_end"], "2026-07-13T00:00:00Z")
        self.assertEqual(metadata["archify"]["status"], "rendered")
        self.assertEqual(metadata["diagram_ir"]["diagram_type"], "dataflow")
        self.assertEqual(metadata["diagram_ir"]["meta"]["evidence_role"], "explanatory_only")
        self.assertEqual(metadata["concept_diagram_ir"]["diagram_type"], "concept")
        self.assertEqual(metadata["concept_diagram_ir"]["renderer"], "local_svg")
        self.assertTrue(metadata["concept_diagram_ir"]["deterministic"])
        self.assertFalse(metadata["concept_diagram_ir"]["external_assets"])
        self.assertEqual(metadata["concept_diagram_ir"]["meta"]["evidence_role"], "explanatory_only")
        self.assertTrue(metadata["project_links"])
        self.assertIn("Проектная реализация", metadata["sections"])
        workbook_titles = {section["title_en"] for section in metadata["workbook_sections"]}
        self.assertTrue(
            {
                "Decision Brief",
                "Strong Signals",
                "Deep Explain",
                "Project Implementation",
                "MVP Radar",
                "Read/Try/Build",
                "Feedback",
                "Appendix",
            }.issubset(workbook_titles)
        )
        self.assertTrue(
            any(
                section["progressive_disclosure"] and section["explanatory_only"]
                for section in metadata["workbook_sections"]
                if section["id"] == "deep-explain"
            )
        )
        self.assertTrue(metadata["workbook_contract"]["explanatory_surfaces_do_not_upgrade_evidence"])
        self.assertEqual(metadata["mvp_radar"]["status"], "loaded")
        self.assertEqual(metadata["mvp_radar"]["decision"], "do_not_build")
        self.assertEqual(metadata["mvp_radar"]["selected_candidate"], "LLM Guardrail Watchdog")
        self.assertEqual(metadata["mvp_radar"]["kir_evidence"]["thread_slug"], "eval-gates")
        self.assertFalse(metadata["mvp_radar"]["external_evidence"]["decision_grade_external"])
        self.assertFalse(metadata["mvp_radar"]["live_source_intelligence"]["used_for_build_decision"])
        self.assertEqual(metadata["report_contract"]["html_language"], "ru")
        self.assertGreaterEqual(len(metadata["decision_cards"]), 3)
        self.assertGreaterEqual(len(metadata["claim_cards"]), 3)
        self.assertGreaterEqual(len(metadata["deep_explanation_cards"]), 3)
        for card in metadata["deep_explanation_cards"][:3]:
            self.assertTrue(card["source_urls"])
            self.assertTrue(card["caveat"])
            self.assertTrue(card["evidence_tier"])
            self.assertTrue(card["quote_verification_status"])
            self.assertTrue(card["what_would_change_my_mind"])
            self.assertTrue(card["explanatory_only"])
        self.assertTrue(all(card["quote_verified"] for card in metadata["claim_cards"][:3]))
        self.assertTrue(all(card["verification_status"] == "verified" for card in metadata["claim_cards"][:3]))
        self.assertTrue(all(card["source_independence_key"] for card in metadata["claim_cards"][:3]))
        self.assertTrue(all(card["staleness_status"] for card in metadata["claim_cards"][:3]))
        self.assertTrue(all(card["wording_policy"] for card in metadata["claim_cards"][:3]))
        self.assertTrue(all(card["next_verification_step"] for card in metadata["claim_cards"][:3]))
        self.assertTrue(metadata["thread_deltas"])
        self.assertTrue(all(delta["this_week_evidence"] for delta in metadata["thread_deltas"]))
        self.assertTrue(all(delta["why_this_is_one_thread"] for delta in metadata["thread_deltas"]))
        self.assertTrue(all(delta["merge_split_audit_status"] for delta in metadata["thread_deltas"]))
        self.assertIn("confirmed_leads", metadata["project_diagnostic"])
        self.assertIn("project_watch", metadata["project_diagnostic"])
        self.assertIn("PR/backlog candidates", html_text)
        suggestions = metadata["project_diagnostic"]["implementation_suggestions"]
        self.assertTrue(suggestions)
        for suggestion in suggestions:
            self.assertTrue(suggestion["effort"])
            self.assertTrue(suggestion["acceptance_criteria"])
            self.assertTrue(suggestion["risk_caveat"])
            self.assertTrue(suggestion["source_atom_ids"] or suggestion["source_urls"])
        self.assertIn("learning_only_implications", metadata["project_diagnostic"])
        self.assertIn("close_but_not_enough_signals", metadata["project_diagnostic"])
        self.assertIn("missing_config_suggestions", metadata["project_diagnostic"])
        self.assertGreaterEqual(len(metadata["action_cards"]), 3)
        self.assertGreaterEqual(sum(1 for card in metadata["action_cards"] if card["action_kind"] == "try"), 2)
        self.assertGreaterEqual(sum(1 for card in metadata["action_cards"] if card["action_kind"] == "experiment"), 1)
        self.assertTrue(all(card["target_ref"] for card in metadata["action_cards"]))
        self.assertTrue(all(card["follow_up_hint"] for card in metadata["action_cards"]))
        self.assertTrue(all(card["outcome_policy"] for card in metadata["action_cards"]))
        self.assertTrue(metadata["feedback_targets"])
        self.assertIn("AI-интеллект", summary.notification_text)
        self.assertIn("Проектные лиды", summary.notification_text)

    def test_project_implications_ignore_generic_keyword_overlap(self):
        context = {
            "threads": [
                {
                    "slug": "generic-ai-workflow",
                    "title": "AI workflow evidence is discussed across posts",
                    "summary": "The thread mentions workflow, evidence, tools, and automation in broad terms.",
                    "current_claims": ["Teams are still comparing AI workflow tool options."],
                    "superseded_claims": [],
                    "contradictions": [],
                    "momentum_30d": 0.4,
                    "source_channel_count": 3,
                    "atoms": [
                        {
                            "claim": "Generic AI workflow discussion",
                            "summary": "No project-specific phrase appears.",
                            "why_it_matters": "Useful background, but not a project lead.",
                            "entities": ["AI"],
                            "tools": ["tool"],
                            "models": [],
                            "practices": ["workflow", "evidence"],
                            "source_urls": ["https://t.me/example/1"],
                        }
                    ],
                }
            ]
        }
        projects = [
            {
                "name": "workflow-to-agent-studio",
                "keywords": ["AI automation", "workflow", "evidence", "tool"],
            }
        ]

        self.assertEqual(_project_links(context, projects), [])

    def test_zero_metrics_are_rendered_as_zero(self):
        self.assertEqual(_escape(0), "0")

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
                    now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
                )
                html_text = Path(summary.html_path).read_text(encoding="utf-8")
            finally:
                os.unlink(db_path)

        self.assertEqual(summary.archify_status, "fallback_missing")
        self.assertIn("Резервная диаграмма Archify", html_text)
        self.assertIn("Карта потока знаний", html_text)

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
