import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
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

from db.ai_report_feedback import record_ai_report_feedback  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
from output.strategy_reviewer import (  # noqa: E402
    build_strategy_review,
    load_reaction_pattern_observations,
)
from output.weekly_run_manifest import WeeklyRunManifestError, sha256_file  # noqa: E402
import main  # noqa: E402


def _opaque_post_ref(value: str) -> str:
    return "reaction-post:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _opaque_reaction_ref(value: str) -> str:
    return "reaction:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


class TestStrategyReviewer(unittest.TestCase):
    def _make_db(self) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        with patch.dict(os.environ, {"AGENT_DB_PATH": tmp.name}, clear=False):
            run_migrations()
        return tmp.name

    def _write_manifest_observation(
        self,
        root: Path,
        *,
        week_label: str,
        run_id: str,
        generated_at: str,
        reacted_post_refs: list[str],
        source_refs: list[str] | None = None,
        selected: bool = True,
    ) -> tuple[Path, Path]:
        receipt_post_refs = sorted(_opaque_post_ref(value) for value in reacted_post_refs)
        year_text, week_text = week_label.split("-W", 1)
        period_start = datetime.fromisocalendar(int(year_text), int(week_text), 1).replace(
            tzinfo=timezone.utc
        )
        period_end = period_start + timedelta(days=7)
        start_text = period_start.isoformat().replace("+00:00", "Z")
        end_text = period_end.isoformat().replace("+00:00", "Z")
        run_dir = root / run_id
        run_dir.mkdir(parents=True)
        manifest_path = run_dir / "manifest.json"
        sidecar_path = run_dir / "brief.json"
        manifest = {
            "run_id": run_id,
            "run_date": generated_at[:10],
            "generated_at": generated_at,
            "reporting_week": week_label,
            "week_label": week_label,
            "period_mode": "completed_iso_week",
            "analysis_period_start": start_text,
            "analysis_period_end": end_text,
            "pipeline_profile": "irx2_orchestration.v1",
            "run_status": "complete",
            "partial": False,
            "stages": {
                "reaction_sync": {
                    "status": "succeeded",
                    "snapshot_ref": f"reaction-snapshot:{run_id}",
                },
                "weekly_brief": {
                    "status": "succeeded",
                    "json_path": "brief.json",
                    "checksums": {},
                },
            },
        }
        post_count = len(receipt_post_refs)
        reader_reason = (
            "Вы отметили один связанный пост за отчётный период."
            if post_count == 1
            else f"Вы отметили {post_count} связанных поста за отчётный период."
        )
        attribution = {
            "surface_item_ref": "thread:eval-gates",
            "reacted_post_count": post_count,
            "compatibility_thread_ref": "idea_thread:eval-gates",
            "current_thread_ref": "idea_thread:eval-gates",
            "canonical_thread_ref": None,
            "thread_resolution_status": "compatibility_current_thread_only",
            "boost_role": "weak_implicit_interest",
            "reader_reason_ru": reader_reason,
            "evidence_refs": ["atom:1"],
            "reacted_post_refs": receipt_post_refs,
            "source_refs": sorted(source_refs or ["telegram:@ai_lab"]),
        }
        item = {
            **attribution,
            "effect": "rank_changed",
            "boost_applied": True,
            "rank_changed": True,
            "selection_changed": False,
            "linked_only": False,
        }
        audit_item = {
            **attribution,
            "selected": selected,
            "counterfactual_effect": (
                "rank_changed" if selected else "report_limit_reached"
            ),
            "boost_applied": True,
        }
        unconsumed = (
            []
            if selected
            else [
                {
                    "reaction_ref": _opaque_reaction_ref(post_ref),
                    "reason": "report_limit_reached",
                    "reasons": ["report_limit_reached"],
                    "audit_detail": "eligible compatibility thread remained below the report limit",
                }
                for post_ref in receipt_post_refs
            ]
        )
        effect = {
            "schema_version": "reaction_personalization.v1",
            "run_id": run_id,
            "surface": "weekly_brief",
            "reporting_week": week_label,
            "analysis_period_start": start_text,
            "analysis_period_end": end_text,
            "snapshot_ref": f"reaction-snapshot:{run_id}",
            "snapshot_status": "complete",
            "status": "effects_applied" if selected else "linked_no_selection_effect",
            "counts": {
                "personal_reaction_events_detected": len(reacted_post_refs),
                "unique_reacted_posts": len(reacted_post_refs),
                "posts_resolved": len(reacted_post_refs),
                "eligible_period_posts": len(reacted_post_refs),
                "unique_atoms_linked": 1,
                "unique_canonical_threads_linked": 0,
                "canonical_threads_boosted": 0,
                "unique_compatibility_threads_linked": 1,
                "compatibility_threads_boosted": 1,
                "selected_items_linked": 1 if selected else 0,
                "selected_signals_influenced": 1 if selected else 0,
                "unconsumed_reaction_events": 0 if selected else len(reacted_post_refs),
            },
            "influenced_items": [item] if selected else [],
            "linked_only_items": [],
            "eligible_thread_audit": [audit_item],
            "unconsumed_by_reason": (
                {} if selected else {"report_limit_reached": len(reacted_post_refs)}
            ),
            "unconsumed": unconsumed,
            "ranking_policy": {
                "policy_version": "reaction-ranking.v1",
                "strength": "weak",
                "below_confirmed_feedback": True,
                "can_change_evidence_gate": False,
            },
            "reader_summary_ru": (
                f"{post_count} личных реакций → {post_count} постов найдено → "
                "1 атомов знаний → 1 тем → 1 сигналов изменили позицию."
                if selected
                else (
                    "Личные реакции связаны с темами, прошедшими условия, но эти "
                    "темы остались за пределом краткой выборки и не изменили выпуск. "
                    "Это не снижало оценки тем."
                )
            ),
        }
        sidecar = {
            "artifact_type": "weekly_intelligence_brief",
            **{
                field: manifest[field]
                for field in (
                    "run_id",
                    "run_date",
                    "generated_at",
                    "reporting_week",
                    "week_label",
                    "period_mode",
                    "analysis_period_start",
                    "analysis_period_end",
                    "pipeline_profile",
                    "run_status",
                    "partial",
                )
            },
            "manifest_path": str(manifest_path.resolve()),
            "json_path": str(sidecar_path.resolve()),
            "artifact_paths": {"json": str(sidecar_path.resolve())},
            "reaction_effect": effect,
        }
        sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
        manifest["stages"]["weekly_brief"]["checksums"] = {
            "json_path": sha256_file(sidecar_path)
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return manifest_path, sidecar_path

    def test_review_outputs_advisory_categories_and_codex_tasks(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                record_ai_report_feedback(
                    connection,
                    week_label="2026-W28",
                    feedback_type="too_shallow",
                    target_type="report_section",
                    target_ref="deep-explain",
                )
                record_ai_report_feedback(
                    connection,
                    week_label="2026-W28",
                    feedback_type="wrong_priority",
                    target_type="idea_thread",
                    target_ref="agent-frameworks",
                )
                record_ai_report_feedback(
                    connection,
                    week_label="2026-W28",
                    feedback_type="missed_important_post",
                    target_type="missed_post",
                    source_url="https://t.me/ai_lab/999",
                )
                review = build_strategy_review(connection, week_label="2026-W28")
        finally:
            os.unlink(db_path)

        self.assertTrue(review["suggestions"]["change"])
        self.assertTrue(review["suggestions"]["demote"])
        self.assertTrue(review["suggestions"]["test_next_week"])
        self.assertTrue(review["memory_only_updates"])
        self.assertTrue(review["approval_required"])
        self.assertTrue(review["codex_tasks"])
        self.assertTrue(review["risks"])
        self.assertTrue(all(task["requires_approval"] for task in review["codex_tasks"]))
        self.assertTrue(all(task["rationale"] for task in review["codex_tasks"]))
        self.assertTrue(all(task["files"] for task in review["codex_tasks"]))
        self.assertTrue(all(task["acceptance_criteria"] for task in review["codex_tasks"]))
        self.assertTrue(all(task["verification_commands"] for task in review["codex_tasks"]))
        self.assertEqual(review["mutation_policy"]["source_code"], "do_not_modify")
        self.assertEqual(review["mutation_policy"]["profile"], "do_not_modify")

    def test_strategy_reviewer_cli_writes_json_without_mutating_config(self):
        db_path = self._make_db()
        with tempfile.TemporaryDirectory() as output_dir:
            output_path = Path(output_dir) / "strategy-review.json"
            try:
                with sqlite3.connect(db_path) as connection:
                    record_ai_report_feedback(
                        connection,
                        week_label="2026-W28",
                        feedback_type="useful",
                        target_type="action",
                        target_ref="eval-gates",
                    )
                with patch.dict(os.environ, {"AGENT_DB_PATH": db_path}, clear=False):
                    with patch.object(
                        sys,
                        "argv",
                        [
                            "main.py",
                            "strategy-reviewer",
                            "--week",
                            "2026-W28",
                            "--weekly-run-root",
                            str(Path(output_dir) / "weekly-runs"),
                            "--output-path",
                            str(output_path),
                        ],
                    ):
                        exit_code = main.main()
                payload = json.loads(output_path.read_text(encoding="utf-8"))
            finally:
                os.unlink(db_path)

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["suggestions"]["keep"])
        self.assertEqual(payload["mutation_policy"]["projects"], "do_not_modify")

    def test_reaction_pattern_threshold_creates_only_unapproved_proposal(self):
        db_path = self._make_db()
        base = {
            "period_mode": "completed_iso_week",
            "completed": True,
            "compatibility_thread_ref": "idea_thread:eval-gates",
            "canonical_thread_ref": None,
            "source_refs": ["telegram:ai_lab"],
        }
        below_weeks = [
            {**base, "reporting_week": "2026-W26", "post_refs": ["post:1", "post:2"]},
            {**base, "reporting_week": "2026-W27", "post_refs": ["post:3", "post:4"]},
        ]
        below_posts = [
            {**base, "reporting_week": "2026-W26", "post_refs": ["post:1"]},
            {**base, "reporting_week": "2026-W27", "post_refs": ["post:2"]},
            {**base, "reporting_week": "2026-W28", "post_refs": ["post:3"]},
        ]
        qualifying = [
            {**base, "reporting_week": "2026-W26", "post_refs": ["post:1", "post:2"]},
            {**base, "reporting_week": "2026-W27", "post_refs": ["post:3"]},
            {**base, "reporting_week": "2026-W28", "post_refs": ["post:4"]},
        ]
        try:
            with sqlite3.connect(db_path) as connection:
                record_ai_report_feedback(
                    connection,
                    week_label="2026-W28",
                    feedback_type="useful",
                    target_type="idea_thread",
                    target_ref="eval-gates",
                )
                record_ai_report_feedback(
                    connection,
                    week_label="2026-W28",
                    feedback_type="wrong_priority",
                    target_type="idea_thread",
                    target_ref="eval-gates",
                )
                # Adjacent target types and similar-looking refs are not exact
                # thread identities and must not be guessed into the proposal.
                record_ai_report_feedback(
                    connection,
                    week_label="2026-W28",
                    feedback_type="applied_to_project",
                    target_type="action",
                    target_ref="eval-gates",
                )
                record_ai_report_feedback(
                    connection,
                    week_label="2026-W28",
                    feedback_type="not_interested",
                    target_type="idea_thread",
                    target_ref="eval-gates-nearby",
                )
                two_week_review = build_strategy_review(
                    connection,
                    week_label="2026-W28",
                    reaction_pattern_observations=below_weeks,
                )
                three_post_review = build_strategy_review(
                    connection,
                    week_label="2026-W28",
                    reaction_pattern_observations=below_posts,
                )
                qualifying_review = build_strategy_review(
                    connection,
                    week_label="2026-W28",
                    reaction_pattern_observations=qualifying,
                )
        finally:
            os.unlink(db_path)

        self.assertEqual(two_week_review["reaction_pattern_proposals"], [])
        self.assertEqual(three_post_review["reaction_pattern_proposals"], [])
        proposal = qualifying_review["reaction_pattern_proposals"][0]
        self.assertEqual(proposal["status"], "unapproved")
        self.assertFalse(proposal["applied"])
        self.assertTrue(proposal["requires_approval"])
        self.assertEqual(proposal["mutation_policy"], "suggestion_only_no_auto_edit")
        self.assertIsNone(proposal["thread_resolution"]["canonical_thread_ref"])
        self.assertEqual(
            proposal["thread_resolution"]["resolution_status"],
            "compatibility_pending_irx4",
        )
        self.assertEqual(
            proposal["supporting_confirmed_feedback"],
            ["idea_thread:eval-gates"],
        )
        self.assertEqual(
            proposal["contradicting_confirmed_feedback"],
            ["idea_thread:eval-gates"],
        )
        self.assertEqual(proposal["proposed_delta"]["strength"], "weak")
        self.assertIn("below confirmed feedback", proposal["expected_report_effect"])
        self.assertTrue(
            all(value == "do_not_modify" for value in qualifying_review["mutation_policy"].values())
        )

    def test_before_week_is_exclusive_for_reaction_pattern_proposals(self):
        db_path = self._make_db()
        observations = [
            {
                "reporting_week": week,
                "period_mode": "completed_iso_week",
                "completed": True,
                "compatibility_thread_ref": "idea_thread:eval-gates",
                "canonical_thread_ref": None,
                "reacted_post_refs": post_refs,
                "source_refs": ["telegram:@ai_lab"],
            }
            for week, post_refs in (
                ("2026-W26", ["reaction-post:111111111111111111111111"]),
                ("2026-W27", ["reaction-post:222222222222222222222222"]),
                (
                    "2026-W28",
                    [
                        "reaction-post:333333333333333333333333",
                        "reaction-post:444444444444444444444444",
                    ],
                ),
            )
        ]
        try:
            with sqlite3.connect(db_path) as connection:
                before_w28 = build_strategy_review(
                    connection,
                    before_week_label="2026-W28",
                    reaction_pattern_observations=observations,
                )
                before_w29 = build_strategy_review(
                    connection,
                    before_week_label="2026-W29",
                    reaction_pattern_observations=observations,
                )
        finally:
            os.unlink(db_path)

        self.assertEqual(before_w28["reaction_pattern_proposals"], [])
        self.assertEqual(len(before_w29["reaction_pattern_proposals"]), 1)

    def test_manifest_loader_builds_completed_observations_and_proposal(self):
        db_path = self._make_db()
        with tempfile.TemporaryDirectory() as run_root_text:
            run_root = Path(run_root_text)
            self._write_manifest_observation(
                run_root,
                week_label="2026-W26",
                run_id="week-26",
                generated_at="2026-06-29T07:00:00Z",
                reacted_post_refs=["post:1", "post:2"],
            )
            self._write_manifest_observation(
                run_root,
                week_label="2026-W27",
                run_id="week-27",
                generated_at="2026-07-06T07:00:00Z",
                reacted_post_refs=["post:3"],
                source_refs=["telegram:@research_lab"],
                selected=False,
            )
            self._write_manifest_observation(
                run_root,
                week_label="2026-W28",
                run_id="week-28",
                generated_at="2026-07-13T07:00:00Z",
                reacted_post_refs=["post:4"],
            )

            def load_fixture(path, **_kwargs):
                return json.loads(Path(path).read_text(encoding="utf-8"))

            try:
                with patch("output.strategy_reviewer.load_manifest", side_effect=load_fixture):
                    observations = load_reaction_pattern_observations(run_root)
                    with sqlite3.connect(db_path) as connection:
                        review = build_strategy_review(
                            connection,
                            week_label="2026-W28",
                            weekly_run_root=run_root,
                        )
            finally:
                os.unlink(db_path)

        self.assertEqual(len(observations), 3)
        self.assertTrue(all(item["completed"] is True for item in observations))
        self.assertEqual(
            observations[0]["reacted_post_refs"],
            sorted([_opaque_post_ref("post:1"), _opaque_post_ref("post:2")]),
        )
        self.assertEqual(observations[1]["reacted_post_refs"], [_opaque_post_ref("post:3")])
        proposal = review["reaction_pattern_proposals"][0]
        self.assertEqual(proposal["distinct_week_count"], 3)
        self.assertEqual(proposal["distinct_reacted_post_count"], 4)
        self.assertEqual(proposal["source_diversity"], 2)
        self.assertFalse(proposal["applied"])

    def test_manifest_loader_does_not_fallback_when_latest_week_receipt_is_tampered(self):
        with tempfile.TemporaryDirectory() as run_root_text:
            run_root = Path(run_root_text)
            _old_manifest, _old_sidecar = self._write_manifest_observation(
                run_root,
                week_label="2026-W28",
                run_id="older-run",
                generated_at="2026-07-13T07:00:00Z",
                reacted_post_refs=["post:old"],
            )
            _new_manifest, new_sidecar = self._write_manifest_observation(
                run_root,
                week_label="2026-W28",
                run_id="newer-run",
                generated_at="2026-07-13T08:00:00Z",
                reacted_post_refs=["post:new"],
            )
            new_sidecar.write_text("{}", encoding="utf-8")

            def load_fixture(path, **_kwargs):
                return json.loads(Path(path).read_text(encoding="utf-8"))

            with patch("output.strategy_reviewer.validate_manifest", return_value=None):
                with patch("output.strategy_reviewer.load_manifest", side_effect=load_fixture):
                    observations = load_reaction_pattern_observations(run_root)

        self.assertEqual(observations, [])

    def test_manifest_loader_does_not_hide_newest_invalid_period_mode(self):
        with tempfile.TemporaryDirectory() as run_root_text:
            run_root = Path(run_root_text)
            self._write_manifest_observation(
                run_root,
                week_label="2026-W28",
                run_id="older-run",
                generated_at="2026-07-13T07:00:00Z",
                reacted_post_refs=["post:old"],
            )
            new_manifest, _new_sidecar = self._write_manifest_observation(
                run_root,
                week_label="2026-W28",
                run_id="newer-run",
                generated_at="2026-07-13T08:00:00Z",
                reacted_post_refs=["post:new"],
            )
            payload = json.loads(new_manifest.read_text(encoding="utf-8"))
            payload["period_mode"] = "partial_iso_week"
            new_manifest.write_text(json.dumps(payload), encoding="utf-8")

            def load_fixture(path, **_kwargs):
                return json.loads(Path(path).read_text(encoding="utf-8"))

            with patch("output.strategy_reviewer.validate_manifest", return_value=None):
                with patch("output.strategy_reviewer.load_manifest", side_effect=load_fixture):
                    observations = load_reaction_pattern_observations(run_root)

        self.assertEqual(observations, [])

    def test_malformed_newest_week_candidate_blocks_older_valid_receipt(self):
        with tempfile.TemporaryDirectory() as run_root_text:
            run_root = Path(run_root_text)
            self._write_manifest_observation(
                run_root,
                week_label="2026-W28",
                run_id="older-2026-W28",
                generated_at="2026-07-13T07:00:00Z",
                reacted_post_refs=["post:old"],
            )
            malformed_dir = run_root / "newer-2026-W28"
            malformed_dir.mkdir()
            malformed_path = malformed_dir / "manifest.json"
            malformed_path.write_text("{", encoding="utf-8")

            def load_fixture(path, **_kwargs):
                if Path(path) == malformed_path:
                    raise WeeklyRunManifestError("malformed newest candidate")
                return json.loads(Path(path).read_text(encoding="utf-8"))

            with patch("output.strategy_reviewer.validate_manifest", return_value=None):
                with patch("output.strategy_reviewer.load_manifest", side_effect=load_fixture):
                    observations = load_reaction_pattern_observations(run_root)

        self.assertEqual(observations, [])

    def test_invalid_conflicting_week_candidate_blocks_every_trustworthy_week_clue(self):
        with tempfile.TemporaryDirectory() as run_root_text:
            run_root = Path(run_root_text)
            self._write_manifest_observation(
                run_root,
                week_label="2026-W28",
                run_id="older-2026-W28",
                generated_at="2026-07-13T07:00:00Z",
                reacted_post_refs=["post:old"],
            )
            new_manifest, _sidecar = self._write_manifest_observation(
                run_root,
                week_label="2026-W28",
                run_id="newer-2026-W28",
                generated_at="2026-07-13T08:00:00Z",
                reacted_post_refs=["post:new"],
            )
            payload = json.loads(new_manifest.read_text(encoding="utf-8"))
            payload["reporting_week"] = "2026-W27"
            payload["period_mode"] = "partial_iso_week"
            new_manifest.write_text(json.dumps(payload), encoding="utf-8")

            def load_fixture(path, **_kwargs):
                if Path(path) == new_manifest:
                    raise WeeklyRunManifestError("conflicting invalid identity")
                return json.loads(Path(path).read_text(encoding="utf-8"))

            with patch("output.strategy_reviewer.validate_manifest", return_value=None):
                with patch("output.strategy_reviewer.load_manifest", side_effect=load_fixture):
                    observations = load_reaction_pattern_observations(run_root)

        self.assertEqual(observations, [])

    def test_uncontained_newest_manifest_symlink_blocks_older_week_receipt(self):
        with tempfile.TemporaryDirectory() as run_root_text, tempfile.TemporaryDirectory() as external_text:
            run_root = Path(run_root_text)
            external_root = Path(external_text)
            self._write_manifest_observation(
                run_root,
                week_label="2026-W28",
                run_id="older-2026-W28",
                generated_at="2026-07-13T07:00:00Z",
                reacted_post_refs=["post:old"],
            )
            external_manifest, _sidecar = self._write_manifest_observation(
                external_root,
                week_label="2026-W28",
                run_id="external-run",
                generated_at="2026-07-13T08:00:00Z",
                reacted_post_refs=["post:external"],
            )
            lexical_dir = run_root / "newer-2026-W28"
            lexical_dir.mkdir()
            (lexical_dir / "manifest.json").symlink_to(external_manifest)

            def load_fixture(path, **_kwargs):
                return json.loads(Path(path).read_text(encoding="utf-8"))

            with patch("output.strategy_reviewer.validate_manifest", return_value=None):
                with patch("output.strategy_reviewer.load_manifest", side_effect=load_fixture):
                    observations = load_reaction_pattern_observations(run_root)

        self.assertEqual(observations, [])

    def test_explicit_empty_observations_override_weekly_run_loading(self):
        db_path = self._make_db()
        try:
            with sqlite3.connect(db_path) as connection:
                with patch(
                    "output.strategy_reviewer.load_reaction_pattern_observations",
                    side_effect=AssertionError("weekly run loader must not be called"),
                ):
                    review = build_strategy_review(
                        connection,
                        week_label="2026-W28",
                        weekly_run_root="/ignored",
                        reaction_pattern_observations=[],
                    )
        finally:
            os.unlink(db_path)

        self.assertEqual(review["reaction_pattern_proposals"], [])


if __name__ == "__main__":
    unittest.main()
