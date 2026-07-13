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
from db.ai_report_feedback import (  # noqa: E402
    fetch_ai_report_eval_examples,
    fetch_ai_report_feedback,
    fetch_ai_report_feedback_intake,
    fetch_missed_post_eval_examples,
    record_ai_report_feedback,
    record_ai_report_feedback_correction,
    summarize_ai_report_feedback,
)
from db.knowledge_atoms import record_knowledge_atom  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
from output.ai_report_feedback_intake import (  # noqa: E402
    apply_confirmed_feedback_intake,
    create_feedback_intake,
    parse_feedback_text,
)
from output.ai_intelligence_report import generate_ai_intelligence_report  # noqa: E402
from output.idea_threads import refresh_idea_threads  # noqa: E402
import main  # noqa: E402


class _StrategistLLM:
    calls: list[dict] = []

    @staticmethod
    def complete_json(prompt, system="", category="unknown", model=None):
        _StrategistLLM.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "category": category,
                "model": model,
            }
        )
        return {
            "memory_events_proposed": [
                {
                    "feedback_type": "too_shallow",
                    "target_type": "report_section",
                    "target_ref": "eval-gates",
                    "notes": "Needed deeper source checks.",
                },
                {
                    "feedback_type": "applied_to_project",
                    "target_type": "experiment",
                    "target_ref": "radar-eval",
                    "notes": "Applied the recommendation in Radar.",
                },
            ],
            "report_changes_suggested": [
                {"text": "Make evidence depth more explicit.", "target_ref": "claim-cards"}
            ],
            "codex_tasks_suggested": [
                {
                    "title": "Add source-depth regression",
                    "why": "Operator marked eval-gates too shallow.",
                    "likely_files": ["src/output/ai_visual_report.py"],
                    "acceptance": ["Shallow claims are flagged."],
                    "verification": ["python3 -m unittest tests.test_ai_visual_report"],
                }
            ],
            "clarifying_questions": ["Which eval-gates source was missing?"],
            "risk_notes": ["Manual approval required for report changes."],
            "confirmation_summary": "Two memory events proposed; suggestions stay manual-only.",
        }


class _BrokenStrategistLLM:
    @staticmethod
    def complete_json(prompt, system="", category="unknown", model=None):
        raise RuntimeError("offline")


class TestAiReportFeedback(unittest.TestCase):
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

    def _seed_atom(self, db_path: str) -> None:
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
                confidence=0.84,
                novelty_score=0.6,
                practical_utility_score=0.92,
                first_seen_at="2026-07-06T08:00:00Z",
                last_seen_at="2026-07-06T08:00:00Z",
            )

    def test_migration_creates_ai_report_feedback_table_and_indexes(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                table = connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name = 'ai_report_feedback_events'
                    """
                ).fetchone()
                columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(ai_report_feedback_events)").fetchall()
                }
                indexes = {
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type = 'index' AND tbl_name = 'ai_report_feedback_events'
                        """
                    ).fetchall()
                }
                intake_table = connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name = 'ai_report_feedback_intakes'
                    """
                ).fetchone()
                intake_columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(ai_report_feedback_intakes)").fetchall()
                }
        finally:
            os.unlink(db_path)

        self.assertIsNotNone(table)
        for column in ["week_label", "feedback_type", "target_type", "target_ref", "source_url", "notes"]:
            self.assertIn(column, columns)
        self.assertIn("idx_ai_report_feedback_week", indexes)
        self.assertIn("idx_ai_report_feedback_type", indexes)
        self.assertIn("idx_ai_report_feedback_target", indexes)
        self.assertIsNotNone(intake_table)
        for column in [
            "input_kind",
            "raw_text",
            "transcript_text",
            "proposals_json",
            "suggestions_json",
            "status",
        ]:
            self.assertIn(column, intake_columns)

    def test_migration_rebuilds_old_feedback_check_for_corrections(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = tmp.name
        try:
            with sqlite3.connect(db_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE ai_report_feedback_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        week_label TEXT NOT NULL CHECK(length(trim(week_label)) > 0),
                        report_path TEXT,
                        feedback_type TEXT NOT NULL CHECK(feedback_type IN (
                            'read',
                            'useful',
                            'tried',
                            'applied_to_project',
                            'too_shallow',
                            'missed_important_post',
                            'no_missed_posts',
                            'wrong_priority',
                            'not_interested',
                            'noise',
                            'trust_too_high',
                            'trust_too_low',
                            'verify_first'
                        )),
                        target_type TEXT NOT NULL DEFAULT 'report' CHECK(target_type IN (
                            'report',
                            'report_section',
                            'idea_thread',
                            'knowledge_atom',
                            'source_channel',
                            'read_queue',
                            'experiment',
                            'action',
                            'missed_post',
                            'trust_correction'
                        )),
                        target_ref TEXT,
                        source_url TEXT,
                        notes TEXT,
                        created_at TEXT NOT NULL,
                        recorded_by TEXT NOT NULL DEFAULT 'operator'
                    );
                    INSERT INTO ai_report_feedback_events (
                        week_label, feedback_type, target_type, target_ref, notes, created_at, recorded_by
                    )
                    VALUES (
                        '2026-W27', 'wrong_priority', 'idea_thread', 'agent-frameworks',
                        'Original event before contract expansion.', '2026-07-01T09:00:00Z', 'operator'
                    );
                    """
                )
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                run_migrations()
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                original = fetch_ai_report_feedback(connection, feedback_id=1, limit=1)[0]
                correction = record_ai_report_feedback_correction(
                    connection,
                    week_label="2026-W27",
                    corrected_feedback_id=1,
                    correction_type="retraction",
                    notes="Append-only correction after migration.",
                    created_at="2026-07-01T10:00:00Z",
                )
        finally:
            os.unlink(db_path)

        self.assertEqual(original["feedback_type"], "wrong_priority")
        self.assertEqual(correction["feedback_type"], "retraction")
        self.assertEqual(correction["target_type"], "feedback_event")

    def test_feedback_text_parser_extracts_feedback_and_manual_suggestions(self):
        parsed = parse_feedback_text(
            """
            Useful target=claim-cards: the claim cards were useful.
            Not interested target=toy-demos in toy demos.
            Wrong priority target=agent-frameworks.
            Too shallow target=eval-gates.
            Tried target=run-eval in a local project.
            Applied to project target=Demand-to-MVP-Radar.
            Missed post https://t.me/ai_lab/999 about eval gates.
            Source trust: @ai_lab trust too low; verify first @hype_channel.
            Project correction: Radar is Python, not Node.
            Preference: prefer practical case studies.
            Config: increase lookback to 21 days.
            Codex task: add tests for KIR gates.
            """,
            input_kind="voice_transcript",
            transcript_text="operator voice transcript",
        )

        feedback_types = {proposal["feedback_type"] for proposal in parsed["proposals"]}
        suggestion_types = {suggestion["suggestion_type"] for suggestion in parsed["suggestions"]}

        self.assertEqual(parsed["input_kind"], "voice_transcript")
        self.assertEqual(parsed["transcript_text"], "operator voice transcript")
        self.assertTrue(
            {
                "useful",
                "not_interested",
                "wrong_priority",
                "too_shallow",
                "tried",
                "applied_to_project",
                "missed_important_post",
                "trust_too_low",
                "verify_first",
            }.issubset(feedback_types)
        )
        self.assertTrue(
            {"project_correction", "source_trust", "preference", "config", "codex_task"}.issubset(
                suggestion_types
            )
        )
        self.assertTrue(all(suggestion["manual_only"] for suggestion in parsed["suggestions"]))

    def test_feedback_strategist_path_uses_opus_category_and_separates_outputs(self):
        _StrategistLLM.calls = []
        parsed = parse_feedback_text(
            "Too shallow target=eval-gates, but I applied target=radar-eval to project.",
            input_kind="voice_transcript",
            transcript_text="Too shallow target=eval-gates.",
            week_label="2026-W28",
            llm_client=_StrategistLLM,
        )

        self.assertEqual(_StrategistLLM.calls[0]["category"], "feedback_intake_strategist")
        self.assertIn("private feedback strategist", _StrategistLLM.calls[0]["system"])
        self.assertIn("Input kind: voice_transcript", _StrategistLLM.calls[0]["prompt"])
        self.assertEqual(parsed["strategy_source"], "feedback_intake_strategist")
        self.assertEqual(
            {event["feedback_type"] for event in parsed["memory_events_proposed"]},
            {"too_shallow", "applied_to_project"},
        )
        self.assertEqual(parsed["proposals"], parsed["memory_events_proposed"])
        self.assertEqual(parsed["report_changes_suggested"][0]["suggestion_type"], "report_change")
        self.assertEqual(parsed["codex_tasks_suggested"][0]["suggestion_type"], "codex_task")
        self.assertEqual(parsed["clarifying_questions"][0]["suggestion_type"], "clarifying_question")
        self.assertEqual(parsed["risk_notes"][0]["suggestion_type"], "risk_note")
        self.assertIn("Two memory events", parsed["confirmation_summary"])

    def test_feedback_strategist_falls_back_to_deterministic_parser(self):
        parsed = parse_feedback_text(
            "Useful target=claim-cards. Config: adjust lookback manually.",
            week_label="2026-W28",
            llm_client=_BrokenStrategistLLM,
        )

        self.assertEqual(parsed["strategy_source"], "heuristic")
        self.assertEqual([proposal["feedback_type"] for proposal in parsed["proposals"]], ["useful"])
        self.assertEqual([suggestion["suggestion_type"] for suggestion in parsed["suggestions"]], ["config"])

    def test_feedback_intake_writes_memory_only_after_confirmation(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                intake = create_feedback_intake(
                    connection,
                    week_label="2026-W28",
                    text=(
                        "Useful target=claim-cards. "
                        "Missed post https://t.me/ai_lab/999. "
                        "Config: increase lookback manually."
                    ),
                    input_kind="text",
                )
                pending_events = fetch_ai_report_feedback(connection, week_label="2026-W28", limit=10)
                pending_intakes = fetch_ai_report_feedback_intake(
                    connection,
                    intake_id=int(intake["id"]),
                    limit=1,
                )

                result = apply_confirmed_feedback_intake(connection, intake_id=int(intake["id"]))
                confirmed_events = fetch_ai_report_feedback(connection, week_label="2026-W28", limit=10)
                confirmed_intake = fetch_ai_report_feedback_intake(
                    connection,
                    intake_id=int(intake["id"]),
                    limit=1,
                )[0]
        finally:
            os.unlink(db_path)

        self.assertIn("No memory has been written yet.", intake["confirmation_summary"])
        self.assertEqual(pending_events, [])
        self.assertEqual(pending_intakes[0]["status"], "pending")
        self.assertEqual(len(result["created_events"]), 2)
        self.assertEqual({event["feedback_type"] for event in confirmed_events}, {"useful", "missed_important_post"})
        self.assertEqual(confirmed_intake["status"], "confirmed")
        self.assertEqual({suggestion["suggestion_type"] for suggestion in result["suggestions"]}, {"config"})

    def test_feedback_intake_stores_strategist_draft_without_memory_write(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                intake = create_feedback_intake(
                    connection,
                    week_label="2026-W28",
                    text="Too shallow target=eval-gates. Applied target=radar-eval to project.",
                    input_kind="voice_transcript",
                    llm_client=_StrategistLLM,
                )
                events_before_confirm = fetch_ai_report_feedback(connection, week_label="2026-W28", limit=10)
                intakes = fetch_ai_report_feedback_intake(connection, intake_id=int(intake["id"]), limit=1)
        finally:
            os.unlink(db_path)

        self.assertEqual(events_before_confirm, [])
        self.assertEqual(intakes[0]["status"], "pending")
        self.assertEqual(
            {proposal["feedback_type"] for proposal in intakes[0]["proposals"]},
            {"too_shallow", "applied_to_project"},
        )
        self.assertIn("Strategist summary: Two memory events proposed", intake["confirmation_summary"])
        self.assertIn("No memory has been written yet.", intake["confirmation_summary"])

    def test_feedback_events_include_provenance_and_effect_window(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                event = record_ai_report_feedback(
                    connection,
                    week_label="2026-W27",
                    report_path="data/output/ai_intelligence/2026-W27.html",
                    feedback_type="useful",
                    target_type="idea_thread",
                    target_ref="eval-gates",
                    source_url="https://t.me/ai_lab/101",
                    notes="Useful because it changed the weekly read queue.",
                    created_at="2026-07-01T10:00:00Z",
                    recorded_by="operator",
                )
                summary = summarize_ai_report_feedback(connection, before_week_label="2026-W28")
        finally:
            os.unlink(db_path)

        self.assertEqual(event["confirmation_state"], "confirmed")
        self.assertEqual(event["signal_strength"], "strong_positive")
        self.assertEqual(event["feedback_provenance"]["source"], "operator_feedback_event")
        self.assertEqual(event["feedback_provenance"]["event_id"], event["id"])
        self.assertEqual(event["feedback_provenance"]["source_url"], "https://t.me/ai_lab/101")
        self.assertEqual(event["effect_window"]["feedback_week_label"], "2026-W27")
        self.assertEqual(event["effect_window"]["applies_from_week_label"], "2026-W28")
        self.assertTrue(event["effect_window"]["applies_to_future_artifacts_only"])
        self.assertEqual(summary["confirmation_state"], "confirmed_only")
        self.assertEqual(summary["confirmed_event_count"], 1)
        self.assertEqual(summary["pending_draft_count"], 0)
        self.assertEqual(summary["feedback_effect_traces"][0]["provenance"]["event_id"], event["id"])

    def test_optional_feedback_cutoff_is_exact_and_legacy_summary_stays_unbounded(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                record_ai_report_feedback(
                    connection,
                    week_label="2026-W27",
                    feedback_type="useful",
                    target_type="idea_thread",
                    target_ref="before-cutoff",
                    created_at="2026-07-12T23:59:59.999999Z",
                )
                record_ai_report_feedback(
                    connection,
                    week_label="2026-W27",
                    feedback_type="useful",
                    target_type="idea_thread",
                    target_ref="at-cutoff-equivalent-offset",
                    created_at="2026-07-13T02:00:00+02:00",
                )
                bounded = summarize_ai_report_feedback(
                    connection,
                    before_week_label="2026-W28",
                    created_before="2026-07-13T00:00:00Z",
                )
                legacy = summarize_ai_report_feedback(
                    connection,
                    before_week_label="2026-W28",
                )
        finally:
            os.unlink(db_path)

        self.assertEqual(bounded["event_count"], 1)
        self.assertEqual(bounded["promoted_target_refs"], ["idea_thread:before-cutoff"])
        self.assertEqual(legacy["event_count"], 2)

    def test_feedback_correction_appends_without_rewriting_prior_event(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                original = record_ai_report_feedback(
                    connection,
                    week_label="2026-W27",
                    feedback_type="wrong_priority",
                    target_type="idea_thread",
                    target_ref="agent-frameworks",
                    notes="I thought this was the wrong priority.",
                    created_at="2026-07-01T09:00:00Z",
                )
                correction = record_ai_report_feedback_correction(
                    connection,
                    week_label="2026-W27",
                    corrected_feedback_id=int(original["id"]),
                    correction_type="retraction",
                    notes="Retracted after review; the thread was relevant.",
                    created_at="2026-07-01T10:00:00Z",
                )
                fetched = fetch_ai_report_feedback(connection, week_label="2026-W27", limit=10)
                original_after = fetch_ai_report_feedback(connection, feedback_id=int(original["id"]), limit=1)[0]
                summary = summarize_ai_report_feedback(connection, before_week_label="2026-W28")
        finally:
            os.unlink(db_path)

        self.assertEqual(len(fetched), 2)
        self.assertEqual(original_after["feedback_type"], "wrong_priority")
        self.assertEqual(correction["feedback_type"], "retraction")
        self.assertEqual(correction["target_type"], "feedback_event")
        self.assertEqual(correction["correction"]["corrects_feedback_id"], original["id"])
        self.assertTrue(correction["correction"]["append_only"])
        self.assertFalse(correction["correction"]["rewrites_prior_event"])
        self.assertEqual(summary["feedback_corrections"][0]["corrects_feedback_id"], original["id"])
        self.assertFalse(summary["feedback_corrections"][0]["rewrites_prior_event"])

    def test_record_fetch_summary_and_missed_eval_examples(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                feedback_types = [
                    "read",
                    "read",
                    "useful",
                    "tried",
                    "too-shallow",
                    "missed-important-post",
                    "no-missed-posts",
                    "wrong-priority",
                    "not-interested",
                    "trust-too-high",
                ]
                for index, feedback_type in enumerate(feedback_types, start=1):
                    target_type = {
                        "too-shallow": "idea-thread",
                        "wrong-priority": "knowledge-atom",
                        "not-interested": "idea-thread",
                        "tried": "action",
                        "trust-too-high": "trust-correction",
                        "no-missed-posts": "missed-post",
                    }.get(feedback_type, "read-queue" if feedback_type == "read" else "report-section")
                    record_ai_report_feedback(
                        connection,
                        week_label="2026-W27",
                        report_path="data/output/ai_intelligence/2026-W27.html",
                        feedback_type=feedback_type,
                        target_type=target_type,
                        target_ref="42" if feedback_type == "wrong-priority" else f"eval-gates-{feedback_type}-{index}",
                        source_url="https://t.me/ai_lab/999" if feedback_type == "missed-important-post" else None,
                        notes=f"note for {feedback_type}",
                    )
                fetched = fetch_ai_report_feedback(connection, week_label="2026-W27", limit=10)
                summary = summarize_ai_report_feedback(connection, before_week_label="2026-W28")
                examples = fetch_missed_post_eval_examples(connection, week_label="2026-W27")
                all_examples = fetch_ai_report_eval_examples(connection, week_label="2026-W27")
        finally:
            os.unlink(db_path)

        self.assertEqual(len(fetched), 10)
        self.assertEqual(summary["event_count"], 10)
        self.assertEqual(summary["counts_by_feedback"]["read"], 2)
        self.assertEqual(summary["counts_by_feedback"]["too_shallow"], 1)
        self.assertEqual(summary["downranked_atom_refs"], ["42"])
        self.assertIn("action:eval-gates-tried-4", summary["promoted_target_refs"] or [])
        self.assertNotIn("read_queue:eval-gates-read-1", summary["promoted_target_refs"] or [])
        self.assertEqual(len(summary["missed_post_eval_examples"]), 1)
        self.assertEqual(len(summary["priority_eval_examples"]), 2)
        self.assertGreaterEqual(len(summary["feedback_eval_examples"]), 3)
        self.assertTrue(summary["feedback_completion"]["completed"])
        self.assertEqual(summary["feedback_changes"]["status"], "feedback_used")
        self.assertIn("Promoted", summary["feedback_changes"]["summary"])
        self.assertIn("Downranked", summary["feedback_changes"]["summary"])
        self.assertIn("Downrank similar items", " ".join(summary["frontier_prompt_guidance"]))
        self.assertEqual(examples[0]["source_url"], "https://t.me/ai_lab/999")
        self.assertEqual({example["example_type"] for example in all_examples}, {"missed_post", "priority_calibration"})

    def test_feedback_context_appears_in_next_ai_report(self):
        db_path = self._make_db()
        try:
            self._seed_atom(db_path)
            with tempfile.TemporaryDirectory() as output_dir:
                settings = self._settings(db_path)
                with sqlite3.connect(db_path) as connection:
                    connection.row_factory = sqlite3.Row
                    record_ai_report_feedback(
                        connection,
                        week_label="2026-W27",
                        feedback_type="too_shallow",
                        target_type="idea_thread",
                        target_ref="eval-gates",
                        notes="Needed deeper source checks.",
                    )
                    record_ai_report_feedback(
                        connection,
                        week_label="2026-W27",
                        feedback_type="missed_important_post",
                        target_type="report_section",
                        target_ref="read-queue",
                        source_url="https://t.me/ai_lab/999",
                        notes="Missed a practical eval guide.",
                    )
                refresh_idea_threads(
                    settings,
                    weeks=12,
                    now=datetime(2026, 7, 8, tzinfo=timezone.utc),
                )
                summary = generate_ai_intelligence_report(
                    settings,
                    week_label="2026-W28",
                    output_root=output_dir,
                    now=datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc),
                )
                html_text = Path(summary.html_path).read_text(encoding="utf-8")
        finally:
            os.unlink(db_path)

        self.assertIn("Personalization Context", html_text)
        self.assertIn("What Feedback Changed This Week", html_text)
        self.assertIn("too shallow=1", html_text)
        self.assertIn("Missed-post eval examples available", html_text)
        self.assertIn("Convert missed-post feedback into an eval example", html_text)

    def test_log_and_inspect_ai_report_feedback_cli(self):
        db_path = self._make_db()
        record_stdout = io.StringIO()
        inspect_stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(
                    sys,
                    "argv",
                    [
                        "main.py",
                        "log-ai-report-feedback",
                        "--week",
                        "2026-W28",
                        "--feedback",
                        "missed-important-post",
                        "--target-type",
                        "report-section",
                        "--target-ref",
                        "read-queue",
                        "--source-url",
                        "https://t.me/ai_lab/999",
                        "--notes",
                        "Missed a practical eval guide.",
                    ],
                ):
                    with redirect_stdout(record_stdout):
                        record_exit = main.main()
                with patch.object(
                    sys,
                    "argv",
                    [
                        "main.py",
                        "memory",
                        "inspect-ai-report-feedback",
                        "--week",
                        "2026-W28",
                        "--eval-examples",
                    ],
                ):
                    with redirect_stdout(inspect_stdout):
                        inspect_exit = main.main()
        finally:
            os.unlink(db_path)

        self.assertEqual(record_exit, 0)
        self.assertEqual(inspect_exit, 0)
        self.assertIn("Recorded AI report feedback", record_stdout.getvalue())
        inspect_output = inspect_stdout.getvalue()
        self.assertIn("AI Report Feedback inspection", inspect_output)
        self.assertIn("missed_important_post", inspect_output)
        self.assertIn("feedback_eval_examples (1):", inspect_output)
        self.assertIn("https://t.me/ai_lab/999", inspect_output)

    def test_log_ai_report_feedback_cli_accepts_no_missed_and_trust_correction(self):
        db_path = self._make_db()
        stdout = io.StringIO()
        try:
            with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                with patch.object(
                    sys,
                    "argv",
                    [
                        "main.py",
                        "log-ai-report-feedback",
                        "--week",
                        "2026-W28",
                        "--feedback",
                        "no-missed-posts",
                        "--target-type",
                        "missed-post",
                        "--target-ref",
                        "weekly-report",
                    ],
                ):
                    with redirect_stdout(stdout):
                        no_missed_exit = main.main()
                with patch.object(
                    sys,
                    "argv",
                    [
                        "main.py",
                        "log-ai-report-feedback",
                        "--week",
                        "2026-W28",
                        "--feedback",
                        "trust-too-low",
                        "--target-type",
                        "trust-correction",
                        "--target-ref",
                        "claim-1",
                    ],
                ):
                    with redirect_stdout(stdout):
                        trust_exit = main.main()
                with sqlite3.connect(db_path) as connection:
                    summary = summarize_ai_report_feedback(connection, week_label="2026-W28")
        finally:
            os.unlink(db_path)

        self.assertEqual(no_missed_exit, 0)
        self.assertEqual(trust_exit, 0)
        self.assertEqual(summary["counts_by_feedback"]["no_missed_posts"], 1)
        self.assertEqual(summary["counts_by_feedback"]["trust_too_low"], 1)
        self.assertIn("read_items", summary["feedback_completion"]["missing"])

    def test_no_feedback_summary_is_unknown_not_negative(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                summary = summarize_ai_report_feedback(connection, before_week_label="2026-W28")
        finally:
            os.unlink(db_path)

        self.assertEqual(summary["event_count"], 0)
        self.assertEqual(summary["feedback_changes"]["status"], "unknown")
        self.assertIn("no-feedback is not a negative signal", summary["feedback_changes"]["items"][0])


if __name__ == "__main__":
    unittest.main()
