import copy
import json
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from config.settings import Settings
from db.canonical_idea_threads import apply_canonical_lifecycle
from db.idea_threads import link_idea_thread_atom, upsert_idea_thread
from db.knowledge_atoms import record_knowledge_atom
from db.migrate import run_migrations
from output.ai_report_contract import INTELLIGENCE_CONTRACT_VERSION
from output.intelligence_retrieval_items import (
    _items_from_workbook,
    _mvp_item,
    _select_weekly_v2_manifest,
    build_retrieval_items,
    load_latest_workbook_json,
    search_retrieval_items,
)
from output.learning_layer import LEARNING_STAGES, PROJECT_LEARNING_PROJECTION_VERSION
from output.weekly_intelligence_brief_v2 import (
    BRIEF_V2_DIRECTORY,
    generate_weekly_intelligence_brief_v2_artifact,
)
from output.weekly_run_manifest import create_manifest, sha256_file


class TestIntelligenceRetrievalItems(unittest.TestCase):
    def _settings(self, root: Path) -> Settings:
        return Settings(
            db_path=str(root / "missing.db"),
            llm_api_key="",
            model_provider="",
            telegram_session_path="",
        )

    def _canonical_contract(self) -> dict:
        return {
            "contract_version": INTELLIGENCE_CONTRACT_VERSION,
            "schema_version": INTELLIGENCE_CONTRACT_VERSION,
            "week_label": "2026-W28",
            "projection_boundaries": {
                "canonical_state": "SQLite rows and versioned JSON sidecars",
                "rendered_surfaces": ["html"],
                "llm_prose": "derived_interpretation_not_source_of_truth",
                "market_business_context": "context_only",
                "no_feedback_semantics": "unknown",
            },
            "source_observations": [
                {
                    "id": "source_observation:telegram_post:101",
                    "source_type": "telegram_post",
                    "url": "https://t.me/ai_lab/101",
                    "observed_at": "2026-07-08T00:00:00Z",
                    "raw_excerpt": "eval gates before release",
                    "metadata": {"atom_ids": [101]},
                    "collection_method": "telegram_ingestion",
                    "ingestion_provenance": {"derived_from": "fixture"},
                }
            ],
            "evidence_items": [
                {
                    "id": "evidence_item:claim-1:1",
                    "claim_id": "claim-1",
                    "source_observation_id": "source_observation:telegram_post:101",
                    "source_observation_ref": "source_observation:telegram_post:101",
                    "atom_ids": [101],
                    "quote": "eval gates before release",
                    "verified_excerpt": "eval gates before release",
                    "evidence_role": "practice_report",
                    "evidence_tier": "verified_single_source",
                    "independence_key": "telegram:ai_lab",
                    "independence_keys": ["telegram:ai_lab"],
                    "verification_status": "verified",
                    "quote_verified": True,
                    "date_relevance": "active",
                    "scope": "practice",
                    "expiry_hint": "Review next month.",
                    "polarity": "supporting",
                    "context_only": False,
                    "decision_grade": True,
                    "radar_gate_eligible": False,
                }
            ],
            "claims": [
                {
                    "id": "claim-1",
                    "statement": "Eval gates are becoming release infrastructure for coding agents.",
                    "scope": "practice",
                    "time_horizon": "medium_to_long",
                    "supporting_evidence_item_ids": ["evidence_item:claim-1:1"],
                    "contradicting_evidence_item_ids": [],
                    "source_observation_ids": ["source_observation:telegram_post:101"],
                    "source_independence": {"count": 1, "keys": ["telegram:ai_lab"]},
                    "confidence_band": "medium",
                    "uncertainty_reasons": ["Single-source until independently confirmed."],
                    "verification_state": "verified",
                    "decision_grade": True,
                    "insufficient_evidence": False,
                    "wording_policy": "source_bounded",
                    "next_verification_step": "Find independent confirmation.",
                    "atom_ids": [101],
                }
            ],
            "knowledge_atoms": [],
            "idea_threads": [],
            "decisions": [],
            "experiments": [],
            "outcomes": [],
        }

    def _write_workbook(self, root: Path, *, reaction_effect: dict | None = None) -> Path:
        output_dir = root / "ai_visual_intelligence"
        output_dir.mkdir(parents=True)
        json_path = output_dir / "2026-W28.visual.json"
        html_path = output_dir / "2026-W28.visual.html"
        html_path.write_text("<!doctype html><title>workbook</title>", encoding="utf-8")
        json_path.write_text(
            json.dumps(
                {
                    "week_label": "2026-W28",
                    "generated_at": "2026-07-08T00:00:00Z",
                    "html_path": str(html_path),
                    "workbook_sections": [
                        {"id": "decision-brief", "title": "Операторский вердикт", "title_en": "Decision Brief", "kind": "decision_brief"},
                        {"id": "strong-signals", "title": "Сильные сигналы", "title_en": "Strong Signals", "kind": "strong_signals"},
                        {"id": "project-implementation", "title": "Проектная реализация", "title_en": "Project Implementation", "kind": "project_implementation"},
                    ],
                    "decision_cards": [
                        {
                            "id": "decision-1",
                            "verdict": "study",
                            "title": "Study eval-gated agent releases",
                            "why_for_operator": "Eval gates are relevant this week.",
                            "next_action": "Read the cited source.",
                            "confidence": "medium",
                            "evidence_atom_ids": [101],
                        }
                    ],
                    "claim_cards": [
                        {
                            "id": "claim-1",
                            "claim": "Eval gates are becoming release infrastructure for coding agents.",
                            "caveat": "Evidence is still source-limited.",
                            "source_urls": ["https://t.me/ai_lab/101"],
                            "evidence_atom_ids": [101],
                            "evidence_tier": "primary_source",
                            "verification_status": "verified",
                            "quote_verified": True,
                            "confidence": 0.8,
                            "staleness_status": "active",
                        }
                    ],
                    "action_cards": [
                        {
                            "id": "action-1",
                            "title": "Try a tiny eval gate",
                            "next_step": "Add one regression guard.",
                            "success_criterion": "Bad agent edit fails before merge.",
                        }
                    ],
                    "project_diagnostic": {
                        "implementation_suggestions": [
                            {
                                "id": "project-action-1",
                                "project": "telegram-research-agent",
                                "title": "Add eval gate backlog item",
                                "next_step": "Draft one scoped issue.",
                                "effort": "30 min",
                                "risk_caveat": "Do not overbuild.",
                                "acceptance_criteria": ["Issue has owner and test command."],
                                "source_atom_ids": [101],
                                "source_urls": ["https://t.me/ai_lab/101"],
                                "suggestion_type": "backlog",
                            }
                        ]
                    },
                    "project_learning_projection": {
                        "schema_version": PROJECT_LEARNING_PROJECTION_VERSION,
                        "week_label": "2026-W28",
                        "source_policy": {
                            "confirmed_project_implication": "requires project-specific evidence and source refs",
                            "broad_overlap": "rejected_not_confirmed",
                            "market_business_context": "context_only",
                            "no_feedback_semantics": "unknown",
                            "passive_reading": "not_mastery",
                        },
                        "project_intelligence": {
                            "external_signals": [
                                {
                                    "id": "external-signal:101",
                                    "title": "Eval gates are becoming release infrastructure for coding agents.",
                                    "thread_slug": "eval-gates",
                                    "atom_type": "engineering_practice",
                                    "context_policy": "source_backed",
                                    "source_atom_ids": [101],
                                    "source_refs": ["https://t.me/ai_lab/101"],
                                    "evidence_state": "source_ref_available",
                                }
                            ],
                            "confirmed_implications": [],
                            "weak_watches": [],
                            "rejected_overlaps": [
                                {
                                    "project": "telegram-research-agent",
                                    "term": "workflow",
                                    "reason": "broad_overlap_suppressed",
                                    "confirmation_state": "rejected",
                                }
                            ],
                            "tiny_pr_ideas": [
                                {
                                    "id": "project-action-1",
                                    "project": "telegram-research-agent",
                                    "title": "Add eval gate backlog item",
                                    "next_step": "Draft one scoped issue.",
                                    "source_atom_ids": [101],
                                    "source_refs": ["https://t.me/ai_lab/101"],
                                    "source_policy": "source refs required before project work",
                                }
                            ],
                            "stale_decisions": [],
                            "research_debt": [{"debt_type": "missing_evidence", "description": "Need project-specific source."}],
                            "repeated_themes_without_action": [],
                        },
                        "learning_intelligence": {
                            "allowed_stages": list(LEARNING_STAGES),
                            "stage_definitions": {stage: stage for stage in LEARNING_STAGES},
                            "stage_counts": {stage: (1 if stage == "read" else 0) for stage in LEARNING_STAGES},
                            "objectives": [
                                {
                                    "id": "learning-objective:atom:101",
                                    "topic": "Eval gates are becoming release infrastructure for coding agents.",
                                    "stage": "read",
                                    "target_stage": "implemented",
                                    "stage_evidence": "source atom with source refs",
                                    "source_atom_ids": [101],
                                    "source_refs": ["https://t.me/ai_lab/101"],
                                    "feedback_state": "unknown",
                                    "mastery_claim": "not_claimed",
                                }
                            ],
                            "experiments": [],
                            "outcomes": [],
                            "feedback_state": "unknown",
                            "mastery_policy": "read is source exposure, not mastery",
                        },
                    },
                    "mvp_radar": {
                        "status": "loaded",
                        "selected_candidate": "LLM Guardrail Watchdog",
                        "dossier_status": "investigate",
                        "recommendation": "revisit_with_evidence_gap",
                        "source_mix": {"readiness": "telegram_only"},
                        "missing_evidence": ["Need external demand."],
                        "next_validation": ["Interview operators."],
                    },
                    **({"reaction_effect": reaction_effect} if reaction_effect is not None else {}),
                    "feedback_targets": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return json_path

    def test_builds_retrieval_items_from_minimal_workbook_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)

        item_types = {item.item_type for item in items}
        self.assertIn("workbook_section", item_types)
        self.assertIn("claim_card", item_types)
        self.assertIn("action_card", item_types)
        self.assertIn("project_diagnostic", item_types)
        self.assertIn("project_intelligence", item_types)
        self.assertIn("learning_objective", item_types)
        self.assertIn("mvp_dossier", item_types)

    def test_self_claimed_strict_reader_is_downgraded_without_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = self._write_workbook(root)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            payload["mvp_radar"] = {
                "schema_version": "mvp_radar_reader.v1",
                "reader_state": "available",
                "status": "selected",
                "selected_candidate": "Bound Reader Candidate",
                "candidate": {
                    "candidate_id": "candidate:radar-42",
                    "title": "Bound Reader Candidate",
                },
                "dossier_status": "investigate",
                "recommendation": "needs_more_evidence",
                "reader_decision": "investigate",
                "decision_reason_ru": "Сборка закрыта до независимой проверки спроса.",
                "missing_evidence": ["Нужна независимая жалоба оператора."],
                "change_condition": "Два независимых источника подтвердят одну боль.",
                "next_validation": "Проверить запрос operator rollback pain.",
                "kill_criteria": ["Закрыть кандидата, если боль не повторяется."],
                "matched_kir_provenance": [
                    {
                        "seed_ref": "seed:kir-42",
                        "thread_slug": "rollback-guardrails",
                    }
                ],
                "matched_external_proof": [
                    {
                        "evidence_ref": "external:42",
                        "source_type": "issue_tracker",
                        "gate_eligible": True,
                    }
                ],
                "unmatched_context": [
                    {
                        "context_ref": "context:market-42",
                        "context_only": True,
                    }
                ],
                "source_path": "/bound/run/radar-reader.json",
            }
            json_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )

            items = build_retrieval_items(
                self._settings(root),
                week_label="2026-W28",
                output_root=root,
            )

        radar = next(item for item in items if item.item_type == "mvp_dossier")
        self.assertTrue(radar.id.startswith("mvp_dossier:2026-W28:candidate-legacy-"))
        self.assertEqual(radar.status, "unbound_legacy")
        self.assertIn("Диагностика MVP Radar", radar.title)
        for marker in (
            "Несвязанный legacy-артефакт не даёт права",
            "Нужна независимая жалоба оператора.",
            "Закрыть кандидата, если боль не повторяется.",
            "Нужен валидный same-run Radar binding.",
            "Повторить Radar в составе нового weekly run.",
        ):
            self.assertIn(marker, radar.text)
        for untrusted_marker in (
            "rollback-guardrails",
            "external:42",
            "context:market-42",
        ):
            self.assertNotIn(untrusted_marker, radar.text)
        self.assertEqual(radar.source_refs, [str(json_path)])

    def test_manifest_bound_workbook_recovers_strict_radar_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            brief_dir = run_dir / "weekly_brief"
            brief_dir.mkdir(parents=True)
            manifest_path = run_dir / "manifest.json"
            manifest_path.write_text("{}", encoding="utf-8")
            sidecar_path = brief_dir / "2026-W28.weekly-brief.json"
            sidecar_path.write_text("{}", encoding="utf-8")
            manifest = {
                "run_status": "complete",
                "run_id": "retrieval-bound-run",
                "reporting_week": "2026-W28",
                "stages": {
                    "weekly_brief": {
                        "status": "succeeded",
                        "json_path": "weekly_brief/2026-W28.weekly-brief.json",
                    }
                },
            }
            strict_projection = {
                "schema_version": "mvp_radar_reader.v1",
                "reader_state": "available",
                "selected_candidate": "Manifest-bound candidate",
                "candidate": {"candidate_id": "candidate:bound-retrieval"},
                "dossier_status": "focused_experiment",
                "recommendation": "focused_experiment",
                "reader_decision": "investigate",
                "decision_reason_ru": "Разрешён только узкий эксперимент.",
                "matched_kir_provenance": [{"thread_slug": "bound-thread"}],
                "matched_external_proof": [{"evidence_ref": "bound-proof"}],
                "unmatched_context": [],
                "source_mix": {"kir_gate_status": "passed"},
                "source_path": "radar/result.json",
            }
            workbook = {
                "week_label": "2026-W28",
                "run_id": "retrieval-bound-run",
                "manifest_path": str(manifest_path),
                "_artifact_kind": "weekly_intelligence_brief",
                "_artifact_paths": {"json": str(sidecar_path)},
                "mvp_radar": {
                    "schema_version": "mvp_radar_reader.v1",
                    "reader_state": "available",
                    "selected_candidate": "Embedded value is not trusted",
                },
            }

            with (
                patch(
                    "output.intelligence_retrieval_items.load_manifest",
                    return_value=manifest,
                ) as load_manifest_mock,
                patch(
                    "output.intelligence_retrieval_items.load_bound_mvp_radar_reader",
                    return_value=strict_projection,
                ),
            ):
                items = _items_from_workbook(workbook)

        radar = next(item for item in items if item.item_type == "mvp_dossier")
        self.assertEqual(radar.title, "Manifest-bound candidate")
        self.assertEqual(radar.status, "focused_experiment")
        self.assertNotIn("bound-thread", radar.text)
        self.assertNotIn("bound-proof", radar.text)
        self.assertIn("Связанных внешних доказательств: 1", radar.text)
        self.assertNotIn("Embedded value is not trusted", radar.text)
        self.assertTrue(load_manifest_mock.call_args.kwargs["check_artifact_existence"])

    def test_unbound_radar_build_claim_is_labeled_diagnostic_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = self._write_workbook(root)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            payload["mvp_radar"] = {
                "status": "selected",
                "selected_candidate": "Unbound forged candidate",
                "dossier_status": "build",
                "recommendation": "build",
                "reader_decision": "build_allowed",
            }
            json_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )

            items = build_retrieval_items(
                self._settings(root),
                week_label="2026-W28",
                output_root=root,
            )

        radar = next(item for item in items if item.item_type == "mvp_dossier")
        self.assertEqual(radar.status, "unbound_legacy")
        self.assertIn("не даёт права", radar.summary)
        self.assertNotIn("build", radar.text)
        self.assertIn("Решение Radar недоступно", radar.text)
        self.assertIn("Диагностика MVP Radar", radar.title)

    def test_authoritative_no_candidate_has_no_diagnostic_or_raw_enum_copy(self):
        radar = _mvp_item(
            {
                "schema_version": "mvp_radar_reader.v1",
                "reader_state": "no_candidate",
                "selected_candidate": None,
                "decision_reason_ru": (
                    "Проверка завершена, но ни один кандидат не прошёл отбор."
                ),
            },
            "2026-W28",
            authoritative=True,
        )

        self.assertEqual(radar.title, "MVP Radar: кандидат не выбран")
        self.assertNotIn("diagnostic", radar.text.casefold())
        self.assertNotIn("no_candidate", radar.text)
        self.assertIn("кандидат для решения не выбран", radar.text)

    def test_malformed_workbook_json_is_bounded_and_skipped(self):
        cases = {
            "invalid_utf8": b"\xff\xfe",
            "deep": ("[" * 1_500 + "0" + "]" * 1_500).encode(),
            "huge_integer": ("{\"value\":" + "9" * 5_000 + "}").encode(),
            "oversized": b" " * 8_000_001,
        }
        for label, content in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                visual_dir = root / "ai_visual_intelligence"
                visual_dir.mkdir(parents=True)
                (visual_dir / "2026-W28.visual.json").write_bytes(content)

                items = build_retrieval_items(
                    self._settings(root),
                    week_label="2026-W28",
                    output_root=root,
                )

                self.assertFalse(
                    any(item.item_type == "mvp_dossier" for item in items)
                )

    def test_reaction_effect_is_available_as_additive_audit_retrieval(self):
        receipt = {
            "schema_version": "reaction_personalization.v1",
            "run_id": "tra-weekly-2026-W28-test",
            "surface": "weekly_brief",
            "reporting_week": "2026-W28",
            "analysis_period_start": "2026-07-06T00:00:00Z",
            "analysis_period_end": "2026-07-13T00:00:00Z",
            "snapshot_ref": "reaction-snapshot:tra-weekly-2026-W28-test",
            "snapshot_status": "complete",
            "status": "effects_applied",
            "reader_summary_ru": (
                "1 личных реакций → 1 постов найдено → 1 атомов знаний → "
                "2 тем → 1 сигналов изменили позицию."
            ),
            "counts": {
                "personal_reaction_events_detected": 1,
                "unique_reacted_posts": 1,
                "posts_resolved": 1,
                "eligible_period_posts": 1,
                "unique_atoms_linked": 1,
                "unique_canonical_threads_linked": 0,
                "canonical_threads_boosted": 0,
                "unique_compatibility_threads_linked": 2,
                "compatibility_threads_boosted": 2,
                "selected_items_linked": 1,
                "selected_signals_influenced": 1,
                "unconsumed_reaction_events": 0,
            },
            "influenced_items": [
                {
                    "surface_item_ref": "signal:eval-gates",
                    "effect": "rank_changed",
                    "boost_applied": True,
                    "rank_changed": True,
                    "selection_changed": False,
                    "linked_only": False,
                    "compatibility_thread_ref": "idea_thread:eval-gates",
                    "current_thread_ref": "idea_thread:eval-gates",
                    "canonical_thread_ref": None,
                    "thread_resolution_status": "compatibility_current_thread_only",
                    "boost_role": "weak_implicit_interest",
                    "reacted_post_count": 1,
                    "reacted_post_refs": ["reaction-post:111111111111111111111111"],
                    "source_refs": ["telegram:@source"],
                    "evidence_refs": ["atom:101"],
                    "reader_reason_ru": "Вы отметили один связанный пост за отчётный период.",
                }
            ],
            "linked_only_items": [],
            "eligible_thread_audit": [
                {
                    "surface_item_ref": "signal:eval-gates",
                    "selected": True,
                    "counterfactual_effect": "rank_changed",
                    "boost_applied": True,
                    "compatibility_thread_ref": "idea_thread:eval-gates",
                    "current_thread_ref": "idea_thread:eval-gates",
                    "canonical_thread_ref": None,
                    "thread_resolution_status": "compatibility_current_thread_only",
                    "boost_role": "weak_implicit_interest",
                    "reacted_post_count": 1,
                    "reacted_post_refs": ["reaction-post:111111111111111111111111"],
                    "source_refs": ["telegram:@source"],
                    "evidence_refs": ["atom:101"],
                    "reader_reason_ru": "Вы отметили один связанный пост за отчётный период.",
                },
                {
                    "surface_item_ref": "signal:eval-runtime",
                    "selected": False,
                    "counterfactual_effect": "report_limit_reached",
                    "boost_applied": True,
                    "compatibility_thread_ref": "idea_thread:eval-runtime",
                    "current_thread_ref": "idea_thread:eval-runtime",
                    "canonical_thread_ref": None,
                    "thread_resolution_status": "compatibility_current_thread_only",
                    "boost_role": "weak_implicit_interest",
                    "reacted_post_count": 1,
                    "reacted_post_refs": ["reaction-post:111111111111111111111111"],
                    "source_refs": ["telegram:@source"],
                    "evidence_refs": ["atom:101"],
                    "reader_reason_ru": "Вы отметили один связанный пост за отчётный период.",
                },
            ],
            "unconsumed_by_reason": {},
            "unconsumed": [],
            "ranking_policy": {
                "policy_version": "reaction-ranking.v1",
                "strength": "weak",
                "below_confirmed_feedback": True,
                "can_change_evidence_gate": False,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root, reaction_effect=receipt)
            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)

        summary = next(item for item in items if item.item_type == "reaction_effect")
        influence = next(item for item in items if item.item_type == "reaction_influence")
        unselected = next(
            item for item in items if item.item_type == "reaction_eligible_unselected"
        )
        self.assertEqual(summary.status, "effects_applied")
        self.assertEqual(influence.thread_slug, "eval-gates")
        self.assertEqual(influence.atom_ids, [101])
        self.assertIn("reaction-snapshot:tra-weekly-2026-W28-test", influence.source_refs)
        self.assertIn("reaction-post:111111111111111111111111", influence.source_refs)
        self.assertIn("telegram:@source", influence.source_refs)
        self.assertEqual(unselected.thread_slug, "eval-runtime")
        self.assertEqual(unselected.status, "report_limit_reached")
        self.assertIn("reaction-post:111111111111111111111111", unselected.source_refs)

    def test_workbook_without_reaction_receipt_keeps_v1_retrieval_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)

        self.assertNotIn("reaction_effect", {item.item_type for item in items})

    def test_builds_retrieval_items_from_split_weekly_brief_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            visual_dir = root / "ai_visual_intelligence"
            visual_dir.mkdir(parents=True)
            visual_html = visual_dir / "2026-W28.visual.html"
            visual_json = visual_dir / "2026-W28.visual.json"
            visual_html.write_text("<!doctype html><title>workbook</title>", encoding="utf-8")
            visual_json.write_text(
                json.dumps(
                    {
                        "week_label": "2026-W28",
                        "generated_at": "2026-07-08T00:00:00Z",
                        "html_path": str(visual_html),
                        "workbook_sections": [
                            {"id": "decision-brief", "title": "Decision Brief", "title_en": "Decision Brief", "kind": "decision_brief"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output_dir = root / "weekly_intelligence_briefs"
            output_dir.mkdir(parents=True)
            html_path = output_dir / "2026-W28.weekly-brief.html"
            json_path = output_dir / "2026-W28.weekly-brief.json"
            html_path.write_text("<!doctype html><title>Weekly Intelligence Brief</title>", encoding="utf-8")
            json_path.write_text(
                json.dumps(
                    {
                        "schema_version": "split_ai_report.v1",
                        "artifact_type": "weekly_intelligence_brief",
                        "contract_version": INTELLIGENCE_CONTRACT_VERSION,
                        "week_label": "2026-W28",
                        "generated_at": "2026-07-08T00:00:00Z",
                        "html_path": str(html_path),
                        "workbook_sections": [
                            {
                                "id": "brief-actions",
                                "title": "Actions And Read/Try Prompts",
                                "title_en": "Actions And Read/Try Prompts",
                                "kind": "actions",
                                "summary": "Try a tiny eval gate.",
                            }
                        ],
                        "artifact_sections": [
                            {
                                "id": "brief-actions",
                                "title": "Actions And Read/Try Prompts",
                                "kind": "actions",
                                "summary": "Try a tiny eval gate.",
                            }
                        ],
                        "actions": [
                            {
                                "title": "Try a tiny eval gate",
                                "body": "Add one regression guard.",
                                "source_count": 1,
                            }
                        ],
                        "mvp_radar": {
                            "selected_candidate": "Agent Eval Gate Scanner",
                            "recommendation": "revisit_with_evidence_gap",
                        },
                        "intelligence_contract": self._canonical_contract(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)

        brief_sections = [
            item for item in items
            if item.item_type == "workbook_section" and item.id.endswith(":brief-actions")
        ]
        self.assertEqual(len(brief_sections), 1)
        self.assertIn("Try a tiny eval gate", brief_sections[0].text)
        self.assertTrue(any(item.item_type == "mvp_dossier" for item in items))
        self.assertTrue(any(item.item_type == "canonical_claim" for item in items))
        self.assertTrue(any(item.item_type == "canonical_evidence" for item in items))

    def test_search_returns_matching_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)
            results = search_retrieval_items(items, "eval gates", limit=5)

        self.assertTrue(results)
        self.assertIn("eval", results[0]["title"].lower())
        self.assertIn("source_refs", results[0])
        self.assertIn("atom_ids", results[0])

    def test_canonical_retrieval_is_additive_and_old_refs_remain_searchable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "agent.db"
            with patch.dict(os.environ, {"AGENT_DB_PATH": str(db_path)}, clear=False):
                run_migrations()
            with sqlite3.connect(db_path) as connection:
                atom = record_knowledge_atom(
                    connection,
                    week_label="2026-W28",
                    atom_type="engineering_practice",
                    claim="Fable-generated software changes code-port economics.",
                    summary="Canonical retrieval fixture.",
                    evidence_quote="code-port economics",
                    source_post_ids=[501],
                    source_urls=["https://t.me/fable_lab/501"],
                    entities=["Fable 5"],
                    models=["Fable 5"],
                    practices=["generated software porting"],
                    first_seen_at="2026-07-07T00:00:00Z",
                    last_seen_at="2026-07-07T00:00:00Z",
                )
                raw = upsert_idea_thread(
                    connection,
                    slug="fable-5-code-port",
                    title="Fable 5 code port",
                    summary="Mutable raw compatibility thread.",
                    status="active",
                    first_seen_at="2026-07-07T00:00:00Z",
                    last_seen_at="2026-07-07T00:00:00Z",
                    momentum_7d=0.5,
                    momentum_30d=0.5,
                    momentum_90d=0.5,
                    atom_count=1,
                    source_channels=["fable_lab"],
                    key_entities=["Fable 5"],
                    current_claims=[atom["claim"]],
                )
                link_idea_thread_atom(
                    connection,
                    thread_id=int(raw["id"]),
                    atom_id=int(atom["id"]),
                )
                apply_canonical_lifecycle(
                    connection,
                    proposal={
                        "operation": "create",
                        "thread": {
                            "stable_slug": "fable-generated-software-porting",
                            "title_ru": "Портирование ПО с Fable",
                            "title_en": "Fable generated software porting",
                            "thesis": "Generated software changes porting economics.",
                            "status": "active",
                            "first_seen_at": "2026-07-07T00:00:00Z",
                            "last_seen_at": "2026-07-07T00:00:00Z",
                            "evidence_maturity": "single_source",
                            "operator_interest": 0.4,
                            "entities": ["Fable", "Fable 5"],
                        },
                        "atom_memberships": [
                            {
                                "atom_id": int(atom["id"]),
                                "raw_thread_id": int(raw["id"]),
                            }
                        ],
                        "aliases": [
                            {
                                "alias_type": "legacy_ref",
                                "alias_value": "old fable reference",
                            }
                        ],
                    },
                    run_id="retrieval-canonical-create",
                    model="deterministic-test-curator",
                    model_version="1",
                    curator_version="irx4-test.v1",
                    reason="retrieval compatibility fixture",
                    event_at="2026-07-11T00:00:00Z",
                )
            settings = Settings(
                db_path=str(db_path),
                llm_api_key="",
                model_provider="",
                telegram_session_path="",
            )
            items = build_retrieval_items(
                settings,
                week_label="2026-W28",
                output_root=root,
            )
            results = search_retrieval_items(
                items,
                "old fable reference",
                filters={"item_type": "canonical_thread"},
                limit=3,
            )

        ids = {item.id for item in items}
        self.assertIn("idea_thread:fable-5-code-port", ids)
        self.assertIn("canonical_thread:fable-generated-software-porting", ids)
        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]["id"],
            "canonical_thread:fable-generated-software-porting",
        )
        self.assertIn(int(atom["id"]), results[0]["atom_ids"])
        self.assertIn("https://t.me/fable_lab/501", results[0]["source_refs"])

    def test_builds_atlas_thread_retrieval_items_from_thread_navigation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            atlas_dir = root / "knowledge_atlas"
            atlas_dir.mkdir(parents=True)
            html_path = atlas_dir / "2026-W28.knowledge-atlas.html"
            json_path = atlas_dir / "2026-W28.knowledge-atlas.json"
            html_path.write_text("<!doctype html><title>Knowledge Atlas</title>", encoding="utf-8")
            json_path.write_text(
                json.dumps(
                    {
                        "schema_version": "split_ai_report.v1",
                        "artifact_type": "knowledge_atlas",
                        "contract_version": INTELLIGENCE_CONTRACT_VERSION,
                        "week_label": "2026-W28",
                        "generated_at": "2026-07-08T00:00:00Z",
                        "html_path": str(html_path),
                        "workbook_sections": [
                            {
                                "id": "thread-navigation",
                                "title": "Thread Navigation",
                                "title_en": "Thread Navigation",
                                "kind": "thread_navigation",
                                "summary": "Atlas thread drill-down.",
                            }
                        ],
                        "thread_navigation": {
                            "schema_version": "knowledge_atlas_thread_navigation.v1",
                            "threads": [
                                {
                                    "slug": "eval-gates",
                                    "title": "Eval Gates",
                                    "status": "active",
                                    "current_understanding": "Eval gates are becoming release infrastructure.",
                                    "change_since_previous_period": "More source-backed release evidence appeared.",
                                    "claims": ["Eval gates matter before agent-written releases."],
                                    "evidence_items": [
                                        {
                                            "atom_id": 101,
                                            "claim": "Eval gates are becoming release infrastructure.",
                                            "source_urls": ["https://t.me/ai_lab/101"],
                                        }
                                    ],
                                    "source_urls": ["https://t.me/ai_lab/101"],
                                    "source_diversity": {"source_count": 1, "channels": ["@ai_lab"]},
                                    "project_connections": [{"connection_type": "project_watch", "rationale": "Relevant to agent evaluation."}],
                                    "decisions": [{"decision": "verify_first", "rationale": "Verify source quality."}],
                                    "open_questions": ["Can another source confirm it?"],
                                    "study_next": ["Read the eval gate source."],
                                }
                            ],
                        },
                        "intelligence_contract": self._canonical_contract(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)
            results = search_retrieval_items(items, "release infrastructure", filters={"item_type": "atlas_thread"}, limit=3)

        self.assertTrue(results)
        self.assertEqual(results[0]["item_type"], "atlas_thread")
        self.assertEqual(results[0]["thread_slug"], "eval-gates")
        self.assertIn("https://t.me/ai_lab/101", results[0]["source_refs"])
        self.assertIn(101, results[0]["atom_ids"])

    def test_atlas_v2_requires_exact_surface_and_strict_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "weekly_intelligence_runs" / "run-1" / "manifest.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text("{}", encoding="utf-8")
            package = root / "knowledge_atlases_v2" / "run-1"
            package.mkdir(parents=True)
            json_path = package / "knowledge-atlas.v2.json"
            html_path = package / "knowledge-atlas.v2.html"
            catalog_path = package / "knowledge-atlas-sources.v1.json"
            for path in (json_path, html_path, catalog_path):
                path.write_text("{}", encoding="utf-8")
            sidecar = {
                "schema_version": "split_ai_report.v2",
                "surface": "knowledge_atlas",
                "run_id": "run-1",
                "generated_at": "2026-07-13T00:00:00Z",
                "run_status": "complete",
                "reporting_period": {"reporting_week": "2026-W28"},
                "artifact_paths": {
                    "json": str(json_path),
                    "html": str(html_path),
                    "source_catalog": str(catalog_path),
                },
                "technical_refs": {
                    "audit_explorer_path": str(package / "knowledge-audit-explorer.v1.html"),
                    "audit_explorer_json_path": str(package / "knowledge-audit-explorer.v1.json"),
                },
                "canonical_threads": [
                    {
                        "stable_slug": "eval-gates",
                        "title_ru": "Гейты качества агентов",
                        "thesis": "Проверки становятся частью пути выпуска.",
                        "display_status": "growing",
                        "evidence_maturity": "repeated_signal",
                        "evidence_refs": ["atom:101", "https://t.me/ai_lab/101"],
                        "audit_ref": "knowledge-audit-explorer.v1.html#atlas-thread-eval-gates",
                        "operator_interest": {
                            "current_reaction_count": 1,
                            "confirmed_feedback_count": 0,
                        },
                    }
                ],
                "study_backlog": [
                    {
                        "title_ru": "Гейты качества агентов",
                        "reason_ru": "Нужен второй независимый источник.",
                        "next_step_ru": "Проверить первичный источник.",
                        "priority": "medium",
                        "evidence_refs": ["atom:101"],
                        "audit_ref": "knowledge-audit-explorer.v1.html#atlas-thread-eval-gates",
                    }
                ],
            }
            candidate = {
                **copy.deepcopy(sidecar),
                "_artifact_kind": "knowledge_atlas_v2",
                "_artifact_paths": dict(sidecar["artifact_paths"]),
            }
            with patch(
                "output.intelligence_retrieval_items.load_manifest_bound_knowledge_atlas_v2",
                return_value=copy.deepcopy(sidecar),
            ) as strict_load:
                items = _items_from_workbook(
                    candidate,
                    v2_expected_manifest_path=manifest_path,
                )

        self.assertEqual(
            [item.item_type for item in items],
            ["atlas_v2_thread", "atlas_v2_study"],
        )
        self.assertEqual(items[0].id, "atlas_v2_thread:run-1:eval-gates")
        self.assertEqual(items[0].schema_version, "split_ai_report.v2")
        self.assertEqual(items[0].surface, "knowledge_atlas")
        self.assertEqual(items[0].run_id, "run-1")
        self.assertIn(101, items[0].atom_ids or [])
        strict_load.assert_called_once()

    def test_unknown_shared_v2_surface_never_falls_back_to_v1_atlas_parser(self):
        forged = {
            "schema_version": "split_ai_report.v2",
            "surface": "unknown_surface",
            "thread_navigation": {
                "threads": [
                    {
                        "slug": "forged",
                        "title": "Forged legacy fallback",
                    }
                ]
            },
        }

        self.assertEqual(_items_from_workbook(forged), [])

    def test_filters_apply_before_broad_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)
            results = search_retrieval_items(
                items,
                "eval gates",
                filters={"item_type": "project_diagnostic", "project_name": "other-project"},
                limit=10,
            )

        self.assertEqual(results, [])

    def test_empty_missing_sources_return_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)

        self.assertEqual(items, [])

    def test_no_raw_telegram_post_source_is_required_for_p0(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)

        self.assertTrue(items)
        self.assertFalse({"raw_post", "telegram_post", "raw_telegram_post"}.intersection({item.item_type for item in items}))

    def test_returned_items_include_source_refs_and_atom_ids_even_when_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_workbook(root)
            items = build_retrieval_items(self._settings(root), week_label="2026-W28", output_root=root)
            results = search_retrieval_items(items, "tiny eval gate", filters={"item_type": "action_card"}, limit=1)

        self.assertTrue(results)
        self.assertIn("source_refs", results[0])
        self.assertIn("atom_ids", results[0])
        self.assertEqual(results[0]["source_refs"], [])
        self.assertEqual(results[0]["atom_ids"], [])

    def test_strategy_reviewer_projection_uses_output_scoped_weekly_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with sqlite3.connect(root / "missing.db") as connection:
                connection.execute("CREATE TABLE ai_report_feedback_events (id INTEGER)")
            review = {
                "generated_at": "2026-07-13T08:00:00Z",
                "suggestions": {"test_next_week": []},
                "memory_only_updates": [],
                "approval_required": [],
                "codex_tasks": [],
                "reaction_pattern_proposals": [
                    {
                        "proposal_id": "reaction-pattern:test",
                        "status": "unapproved",
                        "applied": False,
                    }
                ],
            }
            with patch(
                "output.intelligence_retrieval_items.build_strategy_review",
                return_value=review,
            ) as build_review:
                items = build_retrieval_items(
                    self._settings(root),
                    week_label="2026-W28",
                    output_root=root,
                )

        strategy_item = next(item for item in items if item.item_type == "strategy_reviewer_note")
        self.assertIn("1 unapproved reaction pattern", strategy_item.summary or "")
        self.assertIn("reaction-pattern:test", strategy_item.text)
        self.assertEqual(
            build_review.call_args.kwargs["weekly_run_root"],
            root / "weekly_intelligence_runs",
        )


class TestWeeklyBriefV2Retrieval(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from tests import test_weekly_intelligence_brief_v2 as support

        cls.support = support.WeeklyIntelligenceBriefV2Tests
        cls.support.setUpClass()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.support.tearDownClass()

    def _settings(self) -> Settings:
        return Settings(
            db_path=str(self.support.fixture.root / "retrieval-missing.db"),
            llm_api_key="",
            model_provider="",
            telegram_session_path="",
        )

    def test_strict_v2_projects_reader_items_without_replacing_v1_loader(self):
        items = build_retrieval_items(
            self._settings(),
            week_label="2026-W28",
            output_root=self.support.fixture.root,
            weekly_run_root=self.support.manifest_path.parent.parent,
        )
        by_type: dict[str, list] = {}
        for item in items:
            by_type.setdefault(item.item_type, []).append(item)

        self.assertEqual(len(by_type["weekly_thesis"]), 1)
        self.assertEqual(len(by_type["brief_signal"]), 3)
        self.assertEqual(len(by_type["brief_decision"]), 3)
        self.assertEqual(len(by_type["brief_action"]), 2)
        self.assertEqual(len(by_type["project_action"]), 1)
        self.assertEqual(len(by_type["reaction_effect"]), 1)
        self.assertEqual(len(by_type["confirmed_feedback_effect"]), 1)
        self.assertEqual(len(by_type["feedback_target"]), 5)
        self.assertEqual(len(by_type["mvp_dossier"]), 1)
        radar = by_type["mvp_dossier"][0]
        self.assertNotIn("diagnostic", radar.title.casefold())
        self.assertEqual(radar.status, "investigate")
        self.assertIn(self.support.summary.json_path, radar.source_refs or [])
        for item in by_type["brief_signal"]:
            self.assertIn(self.support.summary.json_path, item.source_refs or [])
            self.assertIsNone(item.confidence)
        reader_text = " ".join(item.text for item in items)
        for internal in (
            "project_action:",
            "signal:",
            "decision_grade",
            "primary_action",
            "KIR Knowledge Thread",
            "bounded Radar run",
        ):
            self.assertNotIn(internal, reader_text)
        v2_reader_text = " ".join(
            item.text for item in items if item.id.startswith("brief_v2")
        )
        self.assertNotIn("medium", v2_reader_text)

        self.assertIsNone(
            load_latest_workbook_json(
                self._settings(),
                "2026-W28",
                output_root=self.support.fixture.root,
            )
        )

    def test_output_root_symlink_loop_fails_closed_without_legacy_radar_fallback(self):
        loop = self.support.fixture.root / "retrieval-output-loop"
        loop.symlink_to(loop, target_is_directory=True)

        with patch(
            "output.intelligence_retrieval_items.load_mvp_radar_status",
            side_effect=AssertionError("legacy fallback must stay closed"),
        ):
            items = build_retrieval_items(
                self._settings(),
                week_label="2026-W28",
                output_root=loop,
                weekly_run_root=self.support.manifest_path.parent.parent,
            )

        self.assertFalse(any(item.item_type == "weekly_thesis" for item in items))
        self.assertFalse(any(item.item_type == "mvp_dossier" for item in items))

    def test_direct_or_mutated_v2_mapping_has_no_authority(self):
        self.assertEqual(_items_from_workbook(self.support.sidecar), [])
        forged = copy.deepcopy(self.support.sidecar)
        forged["_artifact_kind"] = "weekly_intelligence_brief_v2"
        forged["_artifact_paths"] = {
            "json": self.support.summary.json_path,
            "html": self.support.summary.html_path,
            "source_catalog": self.support.summary.source_catalog_path,
        }
        forged["weekly_thesis"]["title"] = "Подменённый тезис"
        self.assertEqual(_items_from_workbook(forged), [])

    def test_external_trusted_roots_and_many_junk_dirs_keep_exact_v2_visible(self):
        isolated = self.support.fixture.root / "isolated-v2-output"
        v2_root = isolated / BRIEF_V2_DIRECTORY
        v2_root.mkdir(parents=True)
        for index in range(80):
            (v2_root / f"000-junk-{index:03d}").mkdir()
        summary = generate_weekly_intelligence_brief_v2_artifact(
            manifest_path=self.support.manifest_path,
            editorial_artifact_path=self.support.editorial_path,
            editorial_input_package=self.support.package,
            project_intelligence_path=self.support.project_path,
            project_descriptors=self.support.project_descriptors,
            output_root=isolated,
            allowed_source_roots=(self.support.fixture.root,),
        )

        items = build_retrieval_items(
            self._settings(),
            week_label="2026-W28",
            output_root=isolated,
            weekly_run_root=self.support.manifest_path.parent.parent,
            v2_source_roots=(self.support.fixture.root,),
        )

        self.assertTrue(any(item.item_type == "weekly_thesis" for item in items))
        self.assertTrue(
            any(summary.json_path in (item.source_refs or []) for item in items)
        )

    def test_symlink_loop_in_exact_v2_path_fails_closed_without_crashing(self):
        isolated = self.support.fixture.root / "loop-v2-output"
        v2_root = isolated / BRIEF_V2_DIRECTORY
        v2_root.mkdir(parents=True)
        loop = v2_root / self.support.run_id
        loop.symlink_to(loop, target_is_directory=True)

        with patch(
            "output.intelligence_retrieval_items.load_mvp_radar_status",
            side_effect=AssertionError("legacy fallback must stay closed"),
        ):
            items = build_retrieval_items(
                self._settings(),
                week_label="2026-W28",
                output_root=isolated,
                weekly_run_root=self.support.manifest_path.parent.parent,
                v2_source_roots=(self.support.fixture.root,),
            )

        self.assertFalse(
            any(item.item_type.startswith("brief_") for item in items)
        )

    def test_tampered_v2_is_omitted_without_legacy_radar_fallback(self):
        path = Path(self.support.summary.json_path)
        original = path.read_bytes()
        try:
            payload = json.loads(original)
            payload["run_id"] = "tra-weekly-2026-W28-foreign-preview"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with patch(
                "output.intelligence_retrieval_items.load_mvp_radar_status",
                side_effect=AssertionError("legacy fallback must stay closed"),
            ):
                items = build_retrieval_items(
                    self._settings(),
                    week_label="2026-W28",
                    output_root=self.support.fixture.root,
                    weekly_run_root=self.support.manifest_path.parent.parent,
                )
            self.assertFalse(
                any(item.item_type.startswith("brief_") for item in items)
            )
            self.assertFalse(
                any(item.item_type == "mvp_dossier" for item in items)
            )
            self.assertFalse(
                any(
                    self.support.summary.json_path in (item.source_refs or [])
                    for item in items
                )
            )
        finally:
            path.write_bytes(original)

    def test_authoritative_v2_replaces_conventional_v1_radar_dossier(self):
        conventional_root = self.support.fixture.root / "weekly_intelligence_briefs"
        conventional_root.mkdir(exist_ok=True)
        conventional = conventional_root / "2026-W28.weekly-brief.json"
        conventional.write_bytes(
            Path(self.support.run_result.weekly_brief_json_path).read_bytes()
        )
        try:
            items = build_retrieval_items(
                self._settings(),
                week_label="2026-W28",
                output_root=self.support.fixture.root,
                weekly_run_root=self.support.manifest_path.parent.parent,
            )
        finally:
            conventional.unlink()

        dossiers = [item for item in items if item.item_type == "mvp_dossier"]
        self.assertEqual(len(dossiers), 1)
        self.assertNotIn("диагност", dossiers[0].title.casefold())
        self.assertIn(
            self.support.summary.json_path,
            dossiers[0].source_refs or [],
        )

    def test_absent_opt_in_v2_preserves_conventional_v1_radar(self):
        isolated = self.support.fixture.root / "no-v2-attempt-output"
        conventional_root = isolated / "weekly_intelligence_briefs"
        conventional_root.mkdir(parents=True)
        (conventional_root / "2026-W28.weekly-brief.json").write_bytes(
            Path(self.support.run_result.weekly_brief_json_path).read_bytes()
        )

        items = build_retrieval_items(
            self._settings(),
            week_label="2026-W28",
            output_root=isolated,
            weekly_run_root=self.support.manifest_path.parent.parent,
        )

        dossiers = [item for item in items if item.item_type == "mvp_dossier"]
        self.assertEqual(len(dossiers), 1)
        self.assertIn("Диагностика", dossiers[0].title)

    def test_absent_v2_does_not_fallback_from_invalid_manifest_outputs(self):
        isolated = self.support.fixture.root / "invalid-manifest-no-v2-output"
        conventional_root = isolated / "weekly_intelligence_briefs"
        conventional_root.mkdir(parents=True)
        (conventional_root / "2026-W28.weekly-brief.json").write_bytes(
            Path(self.support.run_result.weekly_brief_json_path).read_bytes()
        )
        manifest_path = self.support.manifest_path
        manifest_original = manifest_path.read_bytes()
        manifest = json.loads(manifest_original)
        relative = manifest["stages"]["reaction_sync"]["artifact_refs"][
            "snapshot_path"
        ]
        snapshot_path = manifest_path.parent / relative
        snapshot_original = snapshot_path.read_bytes()
        snapshot = json.loads(snapshot_original)
        snapshot["run_id"] = "foreign-retrieval-reaction-run"
        try:
            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False),
                encoding="utf-8",
            )
            manifest["stages"]["reaction_sync"]["checksums"][
                "snapshot_path"
            ] = sha256_file(snapshot_path)
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False),
                encoding="utf-8",
            )
            with patch(
                "output.intelligence_retrieval_items.load_mvp_radar_status",
                side_effect=AssertionError("legacy fallback must stay closed"),
            ):
                items = build_retrieval_items(
                    self._settings(),
                    week_label="2026-W28",
                    output_root=isolated,
                    weekly_run_root=manifest_path.parent.parent,
                )
        finally:
            snapshot_path.write_bytes(snapshot_original)
            manifest_path.write_bytes(manifest_original)

        self.assertFalse(any(item.item_type == "mvp_dossier" for item in items))

    def test_incomplete_exact_v2_package_blocks_legacy_radar_fallback(self):
        isolated = self.support.fixture.root / "incomplete-v2-output"
        summary = generate_weekly_intelligence_brief_v2_artifact(
            manifest_path=self.support.manifest_path,
            editorial_artifact_path=self.support.editorial_path,
            editorial_input_package=self.support.package,
            project_intelligence_path=self.support.project_path,
            project_descriptors=self.support.project_descriptors,
            output_root=isolated,
            allowed_source_roots=(self.support.fixture.root,),
        )
        Path(summary.json_path).unlink()

        with patch(
            "output.intelligence_retrieval_items.load_mvp_radar_status",
            side_effect=AssertionError("legacy fallback must stay closed"),
        ):
            items = build_retrieval_items(
                self._settings(),
                week_label="2026-W28",
                output_root=isolated,
                weekly_run_root=self.support.manifest_path.parent.parent,
                v2_source_roots=(self.support.fixture.root,),
            )

        self.assertFalse(any(item.item_type == "mvp_dossier" for item in items))
        self.assertFalse(any(item.item_type == "weekly_thesis" for item in items))

    def test_newer_running_manifest_blocks_older_v2_and_legacy_fallback(self):
        run_root = self.support.manifest_path.parent.parent
        manifest_path, _manifest = create_manifest(
            run_root,
            self.support.fixture.period,
            run_id="zzzz-current-running-2026-W28",
        )
        try:
            with patch(
                "output.intelligence_retrieval_items.load_mvp_radar_status",
                side_effect=AssertionError("legacy fallback must stay closed"),
            ):
                items = build_retrieval_items(
                    self._settings(),
                    week_label="2026-W28",
                    output_root=self.support.fixture.root,
                    weekly_run_root=run_root,
                )
        finally:
            manifest_path.unlink()
            manifest_path.parent.rmdir()

        self.assertFalse(any(item.item_type == "weekly_thesis" for item in items))
        self.assertFalse(any(item.item_type == "mvp_dossier" for item in items))

    def test_authenticated_newer_manifest_recovers_from_old_invalid_candidate(self):
        run_root = self.support.fixture.root / "selector-recovery-runs"
        invalid_dir = run_root / "old-invalid-2026-W28"
        invalid_dir.mkdir(parents=True)
        invalid_path = invalid_dir / "manifest.json"
        invalid_path.write_text(
            '{"reporting_week":"2026-W28",broken',
            encoding="utf-8",
        )
        future_period = replace(
            self.support.fixture.period,
            run_date=datetime(2099, 7, 14, tzinfo=timezone.utc).date(),
            generated_at=datetime(2099, 7, 14, 8, 0, tzinfo=timezone.utc),
            period_mode="explicit_iso_week",
        )
        current_path, _manifest = create_manifest(
            run_root,
            future_period,
            run_id="authenticated-current-2026-W28",
        )

        selected = _select_weekly_v2_manifest(
            "2026-W28",
            weekly_run_root=run_root,
        )

        self.assertEqual(selected, current_path.resolve())

    def test_uncontained_current_manifest_blocks_older_v2(self):
        run_root = self.support.manifest_path.parent.parent
        external_root = self.support.fixture.root / "external-current-runs"
        external_manifest, _manifest = create_manifest(
            external_root,
            self.support.fixture.period,
            run_id="zzzz-uncontained-2026-W28",
        )
        lexical_run = run_root / external_manifest.parent.name
        lexical_run.symlink_to(external_manifest.parent, target_is_directory=True)
        try:
            with patch(
                "output.intelligence_retrieval_items.load_mvp_radar_status",
                side_effect=AssertionError("legacy fallback must stay closed"),
            ):
                items = build_retrieval_items(
                    self._settings(),
                    week_label="2026-W28",
                    output_root=self.support.fixture.root,
                    weekly_run_root=run_root,
                )
        finally:
            lexical_run.unlink()

        self.assertFalse(any(item.item_type == "weekly_thesis" for item in items))
        self.assertFalse(any(item.item_type == "mvp_dossier" for item in items))

    def test_invalid_current_manifest_and_dangling_v2_root_fail_closed(self):
        run_root = self.support.manifest_path.parent.parent
        invalid_dir = run_root / "zzzz-invalid-2026-W28"
        invalid_dir.mkdir()
        invalid_manifest = invalid_dir / "manifest.json"
        invalid_manifest.write_text(
            '{"schema_version":"weekly_run_manifest.v1",'
            '"schema_version":"weekly_run_manifest.v1",'
            '"reporting_week":"2026-W28"}',
            encoding="utf-8",
        )
        try:
            with patch(
                "output.intelligence_retrieval_items.load_mvp_radar_status",
                side_effect=AssertionError("legacy fallback must stay closed"),
            ):
                items = build_retrieval_items(
                    self._settings(),
                    week_label="2026-W28",
                    output_root=self.support.fixture.root,
                    weekly_run_root=run_root,
                )
        finally:
            invalid_manifest.unlink()
            invalid_dir.rmdir()
        self.assertFalse(any(item.item_type == "weekly_thesis" for item in items))

        dangling_output = self.support.fixture.root / "dangling-v2-output"
        dangling_output.mkdir()
        (dangling_output / BRIEF_V2_DIRECTORY).symlink_to(
            dangling_output / "missing-target",
            target_is_directory=True,
        )
        with patch(
            "output.intelligence_retrieval_items.load_mvp_radar_status",
            side_effect=AssertionError("legacy fallback must stay closed"),
        ):
            dangling_items = build_retrieval_items(
                self._settings(),
                week_label="2026-W28",
                output_root=dangling_output,
                weekly_run_root=run_root,
            )
        self.assertFalse(
            any(item.item_type == "mvp_dossier" for item in dangling_items)
        )

    def test_output_root_with_symlinked_ancestor_fails_closed(self):
        target = self.support.fixture.root / "retrieval-ancestor-target"
        target.mkdir()
        alias = self.support.fixture.root / "retrieval-ancestor-alias"
        alias.symlink_to(target, target_is_directory=True)
        with patch(
            "output.intelligence_retrieval_items.load_mvp_radar_status",
            side_effect=AssertionError("legacy fallback must stay closed"),
        ):
            items = build_retrieval_items(
                self._settings(),
                week_label="2026-W28",
                output_root=alias / "nested",
                weekly_run_root=self.support.manifest_path.parent.parent,
            )

        self.assertFalse(any(item.item_type == "mvp_dossier" for item in items))
        self.assertFalse(any(item.item_type == "weekly_thesis" for item in items))


if __name__ == "__main__":
    unittest.main()
