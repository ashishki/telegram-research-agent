from __future__ import annotations

import copy
import json
import sqlite3
import unittest
from datetime import datetime, timezone

from output.reaction_personalization import (
    MAX_UNCONSUMED_AUDIT_ITEMS,
    REACTION_EFFECT_SCHEMA_VERSION,
    REACTION_SNAPSHOT_SCHEMA_VERSION,
    UNCONSUMED_REASONS,
    ReactionPersonalizationError,
    ThreadResolution,
    build_reaction_pattern_proposals,
    personalize_thread_candidates,
    primary_unconsumed_reason,
    reaction_effect_for_surface,
    thread_resolution_unconsumed_reason,
    validate_reaction_effect,
    validate_reaction_snapshot,
)
from output.reporting_period import resolve_reporting_period


RUN_ID = "tra-weekly-2026-W28-20260713T070252Z"
SNAPSHOT_REF = f"reaction-snapshot:{RUN_ID}"
OBSERVED_THROUGH = "2026-07-13T07:05:00Z"


class TestReactionPersonalization(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE raw_posts (
                id INTEGER PRIMARY KEY,
                channel_username TEXT NOT NULL,
                message_id INTEGER NOT NULL
            );
            CREATE TABLE posts (
                id INTEGER PRIMARY KEY,
                raw_post_id INTEGER NOT NULL,
                channel_username TEXT NOT NULL,
                posted_at TEXT NOT NULL
            );
            CREATE TABLE knowledge_atoms (
                id INTEGER PRIMARY KEY,
                source_post_ids_json TEXT NOT NULL,
                source_urls_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                staleness_status TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE TABLE idea_threads (
                id INTEGER PRIMARY KEY,
                slug TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT '2026-07-01T00:00:00+00:00'
            );
            CREATE TABLE idea_thread_atoms (
                thread_id INTEGER NOT NULL,
                atom_id INTEGER NOT NULL,
                relation TEXT NOT NULL DEFAULT 'supports',
                created_at TEXT NOT NULL DEFAULT '2026-07-01T00:00:00+00:00',
                PRIMARY KEY (thread_id, atom_id)
            );
            """
        )
        self.period = resolve_reporting_period(
            datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
        )

    def tearDown(self) -> None:
        self.connection.close()

    def _binding(
        self,
        *,
        snapshot_status: str = "complete",
        stage_status: str = "succeeded",
        usable: bool = True,
    ) -> dict[str, object]:
        return {
            "run_id": RUN_ID,
            "snapshot_ref": SNAPSHOT_REF,
            "snapshot_path": "reaction/reaction-snapshot.json",
            "snapshot_sha256": "a" * 64,
            "observed_through": OBSERVED_THROUGH,
            "snapshot_status": snapshot_status,
            "stage_status": stage_status,
            "usable": usable,
        }

    def _observation(
        self,
        post_id: int,
        *,
        message_id: int | None = None,
        channel: str = "@source",
        posted_at: str = "2026-07-12T23:59:59Z",
        emojis: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "post_id": post_id,
            "channel_username": channel,
            "message_id": message_id if message_id is not None else post_id + 100,
            "posted_at": posted_at,
            "raw_emojis": sorted(emojis or ["+"]),
        }

    def _snapshot(
        self,
        observations: list[dict[str, object]],
        *,
        candidate_count: int | None = None,
        checked_count: int | None = None,
    ) -> dict[str, object]:
        count = len(observations) if candidate_count is None else candidate_count
        checked = count if checked_count is None else checked_count
        return {
            "schema_version": REACTION_SNAPSHOT_SCHEMA_VERSION,
            **self.period.to_dict(),
            "run_id": RUN_ID,
            "snapshot_ref": SNAPSHOT_REF,
            "observed_through": OBSERVED_THROUGH,
            "coverage": {
                "candidate_count": count,
                "checked_count": checked,
                "coverage_complete": True,
                "visibility_verified": True,
            },
            "observed_personal_posts": observations,
        }

    def _candidate(
        self,
        thread_id: int,
        *,
        slug: str | None = None,
        status: str = "active",
        momentum: float = 0.5,
        sources: int = 2,
    ) -> dict[str, object]:
        return {
            "id": thread_id,
            "slug": slug or f"thread-{thread_id}",
            "status": status,
            "momentum_30d": momentum,
            "source_channel_count": sources,
        }

    def _seed_post(
        self,
        post_id: int,
        *,
        message_id: int | None = None,
        channel: str = "@source",
        posted_at: str = "2026-07-12T23:59:59+00:00",
    ) -> None:
        raw_id = post_id + 10_000
        self.connection.execute(
            "INSERT INTO raw_posts (id, channel_username, message_id) VALUES (?, ?, ?)",
            (raw_id, channel, message_id if message_id is not None else post_id + 100),
        )
        self.connection.execute(
            """
            INSERT INTO posts (id, raw_post_id, channel_username, posted_at)
            VALUES (?, ?, ?, ?)
            """,
            (post_id, raw_id, channel, posted_at),
        )

    def _seed_lineage(
        self,
        post_id: int,
        thread_id: int,
        *,
        atom_id: int | None = None,
        message_id: int | None = None,
        channel: str = "@source",
        posted_at: str = "2026-07-12T23:59:59+00:00",
        confidence: float = 0.8,
        atom_status: str = "active",
        source_urls: list[str] | None = None,
        with_thread_link: bool = True,
        relation: str = "supports",
        link_created_at: str = "2026-07-01T00:00:00+00:00",
    ) -> None:
        self._seed_post(
            post_id,
            message_id=message_id,
            channel=channel,
            posted_at=posted_at,
        )
        clean_atom_id = atom_id if atom_id is not None else post_id + 20_000
        self.connection.execute(
            """
            INSERT INTO knowledge_atoms (
                id, source_post_ids_json, source_urls_json, confidence,
                staleness_status, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                clean_atom_id,
                json.dumps([post_id]),
                json.dumps(source_urls if source_urls is not None else [f"https://t.me/source/{post_id}"]),
                confidence,
                atom_status,
                "2026-07-12T23:59:59+00:00",
            ),
        )
        if with_thread_link:
            self.connection.execute(
                "INSERT OR IGNORE INTO idea_threads (id, slug, status) VALUES (?, ?, ?)",
                (thread_id, f"thread-{thread_id}", "active"),
            )
            self.connection.execute(
                """
                INSERT INTO idea_thread_atoms (
                    thread_id, atom_id, relation, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (thread_id, clean_atom_id, relation, link_created_at),
            )
        self.connection.commit()

    def _personalize(
        self,
        candidates: list[dict[str, object]],
        observations: list[dict[str, object]],
        *,
        limit: int | None = None,
        receipt_limit: int | None = None,
        feedback: dict[str, object] | None = None,
        feedback_snapshot_usable: bool = True,
        thread_resolver: object | None = None,
        selection_projector=None,
        receipt_surface: str = "weekly_brief",
    ) -> tuple[list[dict], dict]:
        ordered, receipt = personalize_thread_candidates(
            self.connection,
            reporting_period=self.period,
            snapshot_binding=self._binding(),
            snapshot=self._snapshot(observations),
            baseline_candidates=candidates,
            feedback_context=feedback or {},
            limit=limit if limit is not None else len(candidates) or 1,
            receipt_limit=receipt_limit,
            feedback_snapshot_usable=feedback_snapshot_usable,
            thread_resolver=thread_resolver,
            selection_projector=selection_projector,
            receipt_surface=receipt_surface,
        )
        self.assertIsNotNone(receipt)
        return ordered, receipt or {}

    def test_legacy_no_binding_preserves_baseline_and_has_no_receipt(self):
        baseline = [self._candidate(1), self._candidate(2)]
        original = copy.deepcopy(baseline)

        ordered, receipt = personalize_thread_candidates(
            self.connection,
            reporting_period=self.period,
            snapshot_binding=None,
            snapshot=None,
            baseline_candidates=baseline,
            feedback_context={},
            limit=2,
        )

        self.assertEqual(ordered, original)
        self.assertEqual(baseline, original)
        self.assertIsNone(receipt)

    def test_unavailable_and_partial_bindings_do_not_reorder(self):
        baseline = [self._candidate(1), self._candidate(2)]
        for snapshot_status, stage_status, expected_status in (
            ("unavailable", "succeeded", "unavailable"),
            ("partial", "failed", "partial"),
        ):
            with self.subTest(snapshot_status=snapshot_status):
                ordered, receipt = personalize_thread_candidates(
                    self.connection,
                    reporting_period=self.period,
                    snapshot_binding=self._binding(
                        snapshot_status=snapshot_status,
                        stage_status=stage_status,
                        usable=False,
                    ),
                    snapshot=None,
                    baseline_candidates=baseline,
                    feedback_context={},
                    limit=2,
                )
                self.assertEqual(ordered, baseline)
                self.assertEqual(receipt["status"], expected_status)
                self.assertEqual(receipt["counts"]["personal_reaction_events_detected"], 0)

    def test_complete_empty_snapshot_is_unknown_not_negative_and_keeps_order(self):
        baseline = [self._candidate(1), self._candidate(2)]
        ordered, receipt = self._personalize(baseline, [])

        self.assertEqual(ordered, baseline)
        self.assertEqual(receipt["schema_version"], REACTION_EFFECT_SCHEMA_VERSION)
        self.assertEqual(receipt["status"], "no_eligible_reactions")
        self.assertEqual(receipt["counts"]["unique_reacted_posts"], 0)
        self.assertIn("не снижало", receipt["reader_summary_ru"])

    def test_feedback_snapshot_failure_keeps_complete_reaction_identity_but_blocks_boost(self):
        self._seed_lineage(1, 2)
        baseline = [self._candidate(1), self._candidate(2)]

        ordered, receipt = self._personalize(
            baseline,
            [self._observation(1)],
            feedback_snapshot_usable=False,
        )

        self.assertEqual(ordered, baseline)
        self.assertEqual(receipt["status"], "partial")
        self.assertEqual(receipt["snapshot_status"], "complete")
        self.assertEqual(
            receipt["unconsumed_by_reason"],
            {"confirmed_feedback_snapshot_unverified": 1},
        )
        self.assertIn("контекст явной обратной связи", receipt["reader_summary_ru"])
        self.assertNotIn("Синхронизация реакций не завершена", receipt["reader_summary_ru"])

    def test_snapshot_requires_complete_coverage_and_rejects_duplicate_posts(self):
        observation = self._observation(1)
        incomplete = self._snapshot([observation], candidate_count=2, checked_count=1)
        with self.assertRaisesRegex(ReactionPersonalizationError, "coverage is incomplete"):
            validate_reaction_snapshot(
                snapshot_binding=self._binding(),
                snapshot=incomplete,
                reporting_period=self.period,
            )

        duplicated = self._snapshot([observation, dict(observation)])
        with self.assertRaisesRegex(ReactionPersonalizationError, "duplicate posts"):
            validate_reaction_snapshot(
                snapshot_binding=self._binding(),
                snapshot=duplicated,
                reporting_period=self.period,
            )

    def test_half_open_period_uses_stored_post_time_and_accepts_offset_utc(self):
        start = "2026-07-06T00:00:00+00:00"
        end = "2026-07-13T00:00:00+00:00"
        self._seed_lineage(1, 1, posted_at=start)
        self._seed_lineage(2, 2, posted_at=end)
        baseline = [self._candidate(1), self._candidate(2)]

        ordered, receipt = self._personalize(
            baseline,
            [
                self._observation(1, posted_at="2026-07-06T00:00:00Z"),
                self._observation(2, posted_at="2026-07-13T00:00:00Z"),
            ],
        )

        self.assertEqual([item["id"] for item in ordered], [1, 2])
        self.assertEqual(receipt["counts"]["posts_resolved"], 2)
        self.assertEqual(receipt["counts"]["eligible_period_posts"], 1)
        self.assertEqual(receipt["unconsumed_by_reason"], {"outside_analysis_period": 1})

    def test_identity_lineage_is_exact_and_compatibility_thread_is_not_canonical(self):
        self._seed_lineage(1, 1, message_id=101, channel="@Source")
        candidate = self._candidate(1)
        ordered, receipt = self._personalize(
            [candidate],
            [self._observation(1, message_id=101, channel="source")],
        )

        self.assertTrue(ordered[0]["_reaction_interest"])
        item = receipt["linked_only_items"][0]
        self.assertEqual(item["compatibility_thread_ref"], "idea_thread:thread-1")
        self.assertEqual(item["current_thread_ref"], "idea_thread:thread-1")
        self.assertIsNone(item["canonical_thread_ref"])
        self.assertEqual(item["thread_resolution_status"], "compatibility_current_thread_only")
        self.assertEqual(receipt["counts"]["unique_canonical_threads_linked"], 0)

        _ordered, wrong = self._personalize(
            [candidate],
            [self._observation(999, message_id=101, channel="source")],
        )
        self.assertEqual(wrong["unconsumed_by_reason"], {"post_not_found": 1})

    def test_injected_thread_resolver_drives_receipt_and_keeps_irx4_gap_nullable(self):
        self._seed_lineage(1, 1)

        class RecordingResolver:
            def __init__(self):
                self.inputs: list[dict[str, object]] = []

            def resolve(self, thread):
                self.inputs.append(dict(thread))
                return ThreadResolution(
                    compatibility_thread_ref="compatibility:thread-1",
                    current_thread_ref="current:thread-1",
                    canonical_thread_ref=None,
                    resolution_status="compatibility_current_thread_only",
                )

        resolver = RecordingResolver()
        _ordered, receipt = self._personalize(
            [self._candidate(1)],
            [self._observation(1)],
            thread_resolver=resolver,
        )

        self.assertEqual(len(resolver.inputs), 1)
        self.assertEqual(resolver.inputs[0]["slug"], "thread-1")
        self.assertEqual(
            resolver.inputs[0]["atom_relations"],
            [{"atom_id": 20001, "relation": "supports"}],
        )
        item = receipt["linked_only_items"][0]
        self.assertEqual(item["compatibility_thread_ref"], "compatibility:thread-1")
        self.assertEqual(item["current_thread_ref"], "current:thread-1")
        self.assertIsNone(item["canonical_thread_ref"])
        self.assertEqual(receipt["counts"]["unique_canonical_threads_linked"], 0)

    def test_resolver_seam_projects_optional_future_canonical_alias(self):
        self._seed_lineage(1, 1)

        class FutureResolver:
            def resolve(self, _thread):
                return ThreadResolution(
                    compatibility_thread_ref="idea_thread:thread-1",
                    current_thread_ref="idea_thread:thread-1",
                    canonical_thread_ref="canonical_thread:stable-1",
                    resolution_status="canonical_alias_resolved",
                )

        _ordered, receipt = self._personalize(
            [self._candidate(1)],
            [self._observation(1)],
            thread_resolver=FutureResolver(),
        )

        item = receipt["linked_only_items"][0]
        self.assertEqual(item["canonical_thread_ref"], "canonical_thread:stable-1")
        self.assertEqual(receipt["counts"]["unique_canonical_threads_linked"], 1)
        self.assertEqual(receipt["counts"]["canonical_threads_boosted"], 1)

    def test_canonical_attribution_changes_only_receipt_identity_not_ranking_semantics(self):
        self._seed_lineage(1, 2)
        baseline = [self._candidate(1), self._candidate(2)]
        compatibility_order, compatibility = self._personalize(
            baseline,
            [self._observation(1)],
        )

        class StoredIdentityResolver:
            def resolve(self, thread):
                slug = str(thread.get("slug") or "")
                return ThreadResolution(
                    compatibility_thread_ref=f"idea_thread:{slug}",
                    current_thread_ref=f"idea_thread:{slug}",
                    canonical_thread_ref="canonical_thread:stored-stable-thread",
                    resolution_status="canonical_membership_resolved",
                )

        canonical_order, canonical = self._personalize(
            baseline,
            [self._observation(1)],
            thread_resolver=StoredIdentityResolver(),
        )

        self.assertEqual(
            [item["id"] for item in canonical_order],
            [item["id"] for item in compatibility_order],
        )
        self.assertEqual(
            [bool(item.get("_reaction_interest")) for item in canonical_order],
            [bool(item.get("_reaction_interest")) for item in compatibility_order],
        )
        for key, value in compatibility["counts"].items():
            if key not in {
                "unique_canonical_threads_linked",
                "canonical_threads_boosted",
            }:
                self.assertEqual(canonical["counts"][key], value, key)
        effect_field = (
            "influenced_items"
            if compatibility["influenced_items"]
            else "linked_only_items"
        )
        compatibility_item = compatibility[effect_field][0]
        canonical_item = canonical[effect_field][0]
        for field in (
            "surface_item_ref",
            "compatibility_thread_ref",
            "current_thread_ref",
            "reacted_post_refs",
            "source_refs",
            "evidence_refs",
            "boost_role",
            "reacted_post_count",
        ):
            self.assertEqual(canonical_item.get(field), compatibility_item.get(field), field)
        self.assertIsNone(compatibility_item["canonical_thread_ref"])
        self.assertEqual(
            canonical_item["canonical_thread_ref"],
            "canonical_thread:stored-stable-thread",
        )
        self.assertEqual(canonical["counts"]["unique_canonical_threads_linked"], 1)
        self.assertEqual(canonical["counts"]["canonical_threads_boosted"], 1)
        for field in ("selected", "counterfactual_effect", "boost_applied"):
            self.assertEqual(
                canonical["eligible_thread_audit"][0][field],
                compatibility["eligible_thread_audit"][0][field],
            )

    def test_multiple_emoji_are_events_but_only_one_post_and_one_thread_boost(self):
        self._seed_lineage(1, 2)
        baseline = [self._candidate(1), self._candidate(2)]
        ordered, receipt = self._personalize(
            baseline,
            [self._observation(1, emojis=["+", "-"])],
        )

        self.assertEqual([item["id"] for item in ordered], [2, 1])
        self.assertEqual(receipt["counts"]["personal_reaction_events_detected"], 2)
        self.assertEqual(receipt["counts"]["unique_reacted_posts"], 1)
        self.assertEqual(receipt["counts"]["compatibility_threads_boosted"], 1)

    def test_adjacent_reacted_threads_each_receive_one_bounded_boost(self):
        self._seed_lineage(1, 2)
        self._seed_lineage(2, 3)
        ordered, receipt = self._personalize(
            [self._candidate(1), self._candidate(2), self._candidate(3)],
            [self._observation(1), self._observation(2)],
            limit=3,
        )

        self.assertEqual([item["id"] for item in ordered], [2, 3, 1])
        all_items = receipt["influenced_items"] + receipt["linked_only_items"]
        self.assertEqual(receipt["counts"]["compatibility_threads_boosted"], 2)
        self.assertEqual(len(receipt["influenced_items"]), 2)
        self.assertTrue(all(item["boost_applied"] for item in all_items))

    def test_exact_tie_moves_only_one_adjacent_position_and_records_rank_change(self):
        self._seed_lineage(1, 3)
        baseline = [self._candidate(1), self._candidate(2), self._candidate(3)]
        ordered, receipt = self._personalize(
            baseline,
            [self._observation(1)],
            limit=3,
        )

        self.assertEqual([item["id"] for item in ordered], [1, 3, 2])
        self.assertEqual(receipt["influenced_items"][0]["effect"], "rank_changed")
        self.assertTrue(receipt["influenced_items"][0]["boost_applied"])
        self.assertEqual(receipt["counts"]["selected_signals_influenced"], 1)

    def test_tie_at_selection_boundary_records_selection_change(self):
        self._seed_lineage(1, 2)
        baseline = [self._candidate(1), self._candidate(2)]
        ordered, receipt = self._personalize(
            baseline,
            [self._observation(1)],
            limit=1,
        )

        self.assertEqual([item["id"] for item in ordered], [2])
        self.assertEqual(receipt["influenced_items"][0]["effect"], "selection_changed")
        self.assertTrue(receipt["influenced_items"][0]["selection_changed"])

    def test_receipt_limit_does_not_truncate_shared_reader_context(self):
        self._seed_lineage(6, 6)
        baseline = [self._candidate(index) for index in range(1, 7)]

        ordered, receipt = self._personalize(
            baseline,
            [self._observation(6)],
            limit=6,
            receipt_limit=4,
        )

        self.assertEqual(len(ordered), 6)
        self.assertEqual([item["id"] for item in ordered], [1, 2, 3, 4, 5, 6])
        self.assertEqual(receipt["influenced_items"], [])
        self.assertEqual(receipt["linked_only_items"], [])
        self.assertEqual(
            receipt["unconsumed_by_reason"],
            {"report_limit_reached": 1},
        )
        self.assertIn("за пределом краткой выборки", receipt["reader_summary_ru"])
        self.assertNotIn("ни одна не прошла", receipt["reader_summary_ru"])

    def test_explicit_surface_projectors_classify_the_actual_bounded_selection(self):
        self._seed_lineage(6, 6)
        baseline = [self._candidate(index) for index in range(1, 7)]
        observation = [self._observation(6)]

        def atlas_projection(values):
            ranked = list(values)
            for index in range(1, len(ranked)):
                if (
                    ranked[index].get("_reaction_interest") is True
                    and ranked[index - 1].get("_reaction_interest") is not True
                ):
                    ranked[index - 1], ranked[index] = ranked[index], ranked[index - 1]
                    break
            return [f"thread:{item['slug']}" for item in ranked[:6]]

        brief_ordered, brief = self._personalize(
            baseline,
            observation,
            limit=6,
            receipt_limit=4,
            selection_projector=lambda values: [
                f"thread:{item['slug']}" for item in values[:4]
            ],
            receipt_surface="weekly_brief",
        )
        atlas_ordered, atlas = self._personalize(
            baseline,
            observation,
            limit=6,
            receipt_limit=4,
            selection_projector=atlas_projection,
            receipt_surface="knowledge_atlas",
        )

        self.assertEqual(
            [item["id"] for item in brief_ordered],
            [1, 2, 3, 4, 5, 6],
        )
        self.assertEqual(
            [item["id"] for item in atlas_ordered],
            [1, 2, 3, 4, 5, 6],
        )
        self.assertEqual(brief["status"], "linked_no_selection_effect")
        self.assertEqual(brief["influenced_items"], [])
        self.assertEqual(
            brief["unconsumed_by_reason"], {"report_limit_reached": 1}
        )
        self.assertEqual(atlas["status"], "effects_applied")
        self.assertEqual(atlas["influenced_items"][0]["effect"], "rank_changed")
        self.assertEqual(atlas["surface"], "knowledge_atlas")

    def test_numeric_zero_evidence_gates_are_explicitly_ineligible(self):
        for index, field in enumerate(
            (
                "evidence_eligible",
                "safety_eligible",
                "period_eligible",
                "radar_eligible",
                "cited",
            ),
            start=20,
        ):
            with self.subTest(field=field):
                self._seed_lineage(index, index)
                candidate = self._candidate(index)
                candidate[field] = 0
                ordered, receipt = self._personalize(
                    [candidate],
                    [self._observation(index)],
                )
                self.assertNotIn("_reaction_interest", ordered[0])
                self.assertEqual(
                    receipt["unconsumed_by_reason"],
                    {"stale_or_low_confidence_evidence": 1},
                )

    def test_one_post_keeps_selected_and_unselected_thread_lineage(self):
        self._seed_lineage(1, 1, atom_id=20001)
        self.connection.execute(
            "INSERT INTO idea_threads (id, slug, status) VALUES (?, ?, ?)",
            (2, "thread-2", "active"),
        )
        self.connection.execute(
            """
            INSERT INTO idea_thread_atoms (thread_id, atom_id, relation)
            VALUES (?, ?, ?)
            """,
            (2, 20001, "supports"),
        )
        self.connection.commit()

        _ordered, receipt = self._personalize(
            [self._candidate(1), self._candidate(2)],
            [self._observation(1)],
            limit=2,
            receipt_limit=1,
        )

        self.assertEqual(receipt["counts"]["compatibility_threads_boosted"], 2)
        self.assertEqual(receipt["counts"]["selected_items_linked"], 1)
        self.assertEqual(len(receipt["eligible_thread_audit"]), 2)
        self.assertEqual(
            [item["counterfactual_effect"] for item in receipt["eligible_thread_audit"]],
            ["linked_only", "report_limit_reached"],
        )
        self.assertEqual(receipt["counts"]["unconsumed_reaction_events"], 0)

    def test_full_confirmed_feedback_score_precedes_implicit_reaction(self):
        self._seed_lineage(1, 1)
        baseline = [self._candidate(1), self._candidate(2)]
        ordered, receipt = self._personalize(
            baseline,
            [self._observation(1)],
            feedback={"_thread_feedback_scores": {"thread-1": -1, "thread-2": 0}},
        )

        self.assertEqual([item["id"] for item in ordered], [1, 2])
        self.assertEqual(receipt["influenced_items"], [])
        self.assertEqual(
            receipt["unconsumed_by_reason"],
            {"superseded_by_confirmed_feedback": 1},
        )

    def test_exact_negative_feedback_wins_even_when_aggregate_score_is_zero(self):
        self._seed_lineage(1, 1)
        ordered, receipt = self._personalize(
            [self._candidate(1), self._candidate(2)],
            [self._observation(1)],
            feedback={
                "_thread_feedback_scores": {"thread-1": 0},
                "downranked_target_refs": ["idea_thread:thread-1"],
                "promoted_target_refs": ["idea_thread:thread-1"],
            },
        )

        self.assertEqual([item["id"] for item in ordered], [1, 2])
        self.assertNotIn("_reaction_interest", ordered[0])
        self.assertEqual(
            receipt["unconsumed_by_reason"],
            {"superseded_by_confirmed_feedback": 1},
        )

    def test_already_selected_reaction_is_linked_only_not_causal(self):
        self._seed_lineage(1, 1)
        ordered, receipt = self._personalize(
            [self._candidate(1), self._candidate(2)],
            [self._observation(1)],
            limit=1,
        )

        self.assertEqual([item["id"] for item in ordered], [1])
        self.assertEqual(receipt["influenced_items"], [])
        self.assertEqual(receipt["linked_only_items"][0]["effect"], "linked_only")
        self.assertIn("не изменили", receipt["reader_summary_ru"])

    def test_stronger_evidence_cannot_be_rescued_by_reaction(self):
        self._seed_lineage(1, 2)
        baseline = [
            self._candidate(1, momentum=0.9, sources=3),
            self._candidate(2, momentum=0.8, sources=3),
        ]
        ordered, receipt = self._personalize(
            baseline,
            [self._observation(1)],
            limit=1,
        )

        self.assertEqual([item["id"] for item in ordered], [1])
        self.assertEqual(receipt["influenced_items"], [])
        self.assertEqual(receipt["unconsumed_by_reason"], {"report_limit_reached": 1})

    def test_stale_evidence_and_confirmed_negative_feedback_override_reaction(self):
        for post_id, thread_id in ((1, 1), (2, 2)):
            self._seed_lineage(post_id, thread_id)
        baseline = [
            self._candidate(1, status="stale"),
            self._candidate(2),
        ]
        ordered, receipt = self._personalize(
            baseline,
            [self._observation(1), self._observation(2)],
            feedback={"downranked_thread_slugs": ["thread-2"]},
        )

        self.assertEqual([item["id"] for item in ordered], [1, 2])
        self.assertNotIn("_reaction_interest", ordered[0])
        self.assertNotIn("_reaction_interest", ordered[1])
        self.assertEqual(
            receipt["unconsumed_by_reason"],
            {
                "stale_or_low_confidence_evidence": 1,
                "superseded_by_confirmed_feedback": 1,
            },
        )

    def test_stale_low_confidence_duplicate_and_exact_atom_feedback_are_not_rescued(self):
        self._seed_lineage(1, 1, atom_status="stale")
        self._seed_lineage(2, 2, confidence=0.01)
        self._seed_lineage(3, 3, atom_id=23003)
        self._seed_lineage(4, 4, atom_id=24004)
        duplicate = self._candidate(3)
        duplicate["duplicate_signal"] = True
        ordered, receipt = self._personalize(
            [self._candidate(1), self._candidate(2), duplicate, self._candidate(4)],
            [
                self._observation(1),
                self._observation(2),
                self._observation(3),
                self._observation(4),
            ],
            feedback={
                "downranked_atom_refs": ["24004"],
                "downranked_target_refs": ["knowledge_atom:24004"],
            },
        )

        self.assertEqual([item["id"] for item in ordered], [1, 2, 3, 4])
        self.assertEqual(
            receipt["unconsumed_by_reason"],
            {
                "duplicate_signal": 1,
                "stale_or_low_confidence_evidence": 2,
                "superseded_by_confirmed_feedback": 1,
            },
        )

    def test_safety_radar_and_contradicting_membership_cannot_be_rescued(self):
        self._seed_lineage(1, 1)
        self._seed_lineage(2, 2)
        self._seed_lineage(3, 3, relation="contradicts")
        unsafe = self._candidate(1)
        unsafe["safety_eligible"] = False
        radar_ineligible = self._candidate(2)
        radar_ineligible["radar_eligible"] = False

        ordered, receipt = self._personalize(
            [unsafe, radar_ineligible, self._candidate(3)],
            [self._observation(1), self._observation(2), self._observation(3)],
        )

        self.assertEqual([item["id"] for item in ordered], [1, 2, 3])
        self.assertTrue(all("_reaction_interest" not in item for item in ordered))
        self.assertEqual(
            receipt["unconsumed_by_reason"],
            {
                "contradicted_or_retracted_evidence": 1,
                "stale_or_low_confidence_evidence": 2,
            },
        )

    def test_missing_atom_missing_thread_and_retracted_atom_have_stable_reasons(self):
        self._seed_post(1)
        self._seed_lineage(2, 2, with_thread_link=False)
        self._seed_lineage(3, 3, atom_status="superseded")
        baseline = [self._candidate(2), self._candidate(3)]
        _ordered, receipt = self._personalize(
            baseline,
            [self._observation(1), self._observation(2), self._observation(3)],
        )

        self.assertEqual(
            receipt["unconsumed_by_reason"],
            {
                "contradicted_or_retracted_evidence": 1,
                "knowledge_atom_not_extracted": 1,
                "no_thread_link": 1,
            },
        )
        validate_reaction_effect(receipt)

    def test_reason_vocabulary_priority_count_parity_and_bounded_audit(self):
        self.assertEqual(
            UNCONSUMED_REASONS,
            (
                "post_not_found",
                "outside_analysis_period",
                "knowledge_atom_not_extracted",
                "no_thread_link",
                "no_canonical_thread_link",
                "stale_or_low_confidence_evidence",
                "contradicted_or_retracted_evidence",
                "duplicate_signal",
                "superseded_by_confirmed_feedback",
                "report_limit_reached",
                "confirmed_feedback_snapshot_unverified",
                "snapshot_unverified",
            ),
        )
        for reason in UNCONSUMED_REASONS:
            with self.subTest(reason=reason):
                self.assertEqual(primary_unconsumed_reason([reason]), reason)
        self.assertEqual(
            thread_resolution_unconsumed_reason(
                ThreadResolution(
                    compatibility_thread_ref="idea_thread:compat",
                    current_thread_ref="idea_thread:compat",
                    canonical_thread_ref=None,
                ),
                require_canonical=True,
            ),
            "no_canonical_thread_link",
        )
        self.assertEqual(
            primary_unconsumed_reason(
                ["report_limit_reached", "superseded_by_confirmed_feedback"]
            ),
            "superseded_by_confirmed_feedback",
        )

        emojis = [f"reaction-{index:02d}" for index in range(30)]
        _ordered, receipt = self._personalize(
            [self._candidate(1)],
            [self._observation(999, emojis=emojis)],
        )
        self.assertEqual(receipt["unconsumed_by_reason"], {"post_not_found": 30})
        self.assertEqual(receipt["counts"]["unconsumed_reaction_events"], 30)
        self.assertEqual(len(receipt["unconsumed"]), MAX_UNCONSUMED_AUDIT_ITEMS)
        validate_reaction_effect(receipt)

    def test_surface_adapter_preserves_validated_totals_and_reader_copy_hides_audit_ids(self):
        self._seed_lineage(1, 1)
        _ordered, receipt = self._personalize(
            [self._candidate(1)],
            [self._observation(1, emojis=["+"])],
        )
        atlas = reaction_effect_for_surface(receipt, surface="knowledge_atlas")

        self.assertEqual(atlas["surface"], "knowledge_atlas")
        self.assertEqual(atlas["counts"], receipt["counts"])
        reader_text = atlas["reader_summary_ru"]
        self.assertNotIn("idea_thread:", reader_text)
        self.assertNotIn("atom:", reader_text)
        self.assertNotIn("+", reader_text)

    def test_receipt_validator_rejects_effect_status_and_counterfactual_contradictions(self):
        self._seed_lineage(1, 1)
        _ordered, receipt = self._personalize(
            [self._candidate(2), self._candidate(1)],
            [self._observation(1)],
        )
        self.assertEqual(receipt["status"], "effects_applied")

        partial_with_effect = copy.deepcopy(receipt)
        partial_with_effect["status"] = "partial"
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "partial or unavailable receipts cannot contain applied effects",
        ):
            validate_reaction_effect(partial_with_effect)

        zero_influenced_status = copy.deepcopy(receipt)
        zero_influenced_status["status"] = "linked_no_selection_effect"
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "status contradicts",
        ):
            validate_reaction_effect(zero_influenced_status)

        false_boost = copy.deepcopy(receipt)
        false_boost["influenced_items"][0]["boost_applied"] = False
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "counterfactual flags",
        ):
            validate_reaction_effect(false_boost)

    def test_receipt_validator_rejects_impossible_funnels_and_audit_samples(self):
        self._seed_lineage(1, 1)
        _ordered, receipt = self._personalize(
            [self._candidate(1)],
            [self._observation(1)],
        )

        impossible_funnel = copy.deepcopy(receipt)
        impossible_funnel["counts"]["posts_resolved"] = 999
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "funnel counts are not monotonic",
        ):
            validate_reaction_effect(impossible_funnel)

        _ordered, unconsumed_receipt = self._personalize(
            [self._candidate(1)],
            [self._observation(999)],
        )
        duplicate_sample = copy.deepcopy(unconsumed_receipt)
        duplicate_sample["unconsumed"].append(
            copy.deepcopy(duplicate_sample["unconsumed"][0])
        )
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "does not cover the bounded event total",
        ):
            validate_reaction_effect(duplicate_sample)

        overstated_sample = copy.deepcopy(unconsumed_receipt)
        overstated_sample["unconsumed_by_reason"]["post_not_found"] = 0
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "must be positive",
        ):
            validate_reaction_effect(overstated_sample)

        overlap = copy.deepcopy(receipt)
        overlap["counts"]["unconsumed_reaction_events"] = 1
        overlap["unconsumed_by_reason"] = {"report_limit_reached": 1}
        overlap["unconsumed"] = [
            {
                "reaction_ref": "reaction:ffffffffffffffffffffffff",
                "reason": "report_limit_reached",
                "reasons": ["report_limit_reached"],
                "audit_detail": "eligible compatibility thread remained below the report limit",
            }
        ]
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "accounting overlaps",
        ):
            validate_reaction_effect(overlap)

        event_without_post = copy.deepcopy(unconsumed_receipt)
        event_without_post["counts"]["unique_reacted_posts"] = 0
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "both be empty or both be present",
        ):
            validate_reaction_effect(event_without_post)

        false_audit_detail = copy.deepcopy(unconsumed_receipt)
        false_audit_detail["unconsumed"][0]["audit_detail"] = "false explanation"
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "does not match its reason",
        ):
            validate_reaction_effect(false_audit_detail)

        missing_bounded_audit = copy.deepcopy(unconsumed_receipt)
        missing_bounded_audit["unconsumed"] = []
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "does not cover the bounded event total",
        ):
            validate_reaction_effect(missing_bounded_audit)

        invalid_reaction_ref = copy.deepcopy(unconsumed_receipt)
        invalid_reaction_ref["unconsumed"][0]["reaction_ref"] = "plain-reaction"
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "unique opaque reaction refs",
        ):
            validate_reaction_effect(invalid_reaction_ref)

        false_summary = copy.deepcopy(receipt)
        false_summary["reader_summary_ru"] = "Ложное объяснение."
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "does not match the deterministic receipt",
        ):
            validate_reaction_effect(false_summary)

        missing_post_lineage = copy.deepcopy(receipt)
        for field in (
            "personal_reaction_events_detected",
            "unique_reacted_posts",
            "posts_resolved",
            "eligible_period_posts",
        ):
            missing_post_lineage["counts"][field] = 2
        missing_post_lineage["reader_summary_ru"] = (
            "2 личных реакций → 2 постов найдено → 1 атомов знаний → "
            "1 тем → 0 сигналов изменили позицию."
        )
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "reacted-post lineage is missing",
        ):
            validate_reaction_effect(missing_post_lineage)

        false_canonical_link = copy.deepcopy(receipt)
        false_canonical_link["counts"]["unique_canonical_threads_linked"] = 1
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "canonical linked count contradicts",
        ):
            validate_reaction_effect(false_canonical_link)

        _empty_ordered, empty_receipt = self._personalize([], [])
        atoms_without_posts = copy.deepcopy(empty_receipt)
        atoms_without_posts["counts"]["unique_atoms_linked"] = 5
        atoms_without_posts["counts"]["unique_compatibility_threads_linked"] = 3
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "require an eligible-period post",
        ):
            validate_reaction_effect(atoms_without_posts)

    def test_receipt_validator_requires_full_selected_audit_lineage_parity(self):
        self._seed_lineage(1, 1)
        _ordered, receipt = self._personalize(
            [self._candidate(1)],
            [self._observation(1)],
        )

        canonical_mismatch = copy.deepcopy(receipt)
        selected = canonical_mismatch["linked_only_items"][0]
        selected["canonical_thread_ref"] = "canonical_thread:foreign"
        selected["thread_resolution_status"] = "canonical_alias_resolved"
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "contradicts eligible thread audit",
        ):
            validate_reaction_effect(canonical_mismatch)

        current_mismatch = copy.deepcopy(receipt)
        current_mismatch["linked_only_items"][0]["current_thread_ref"] = (
            "idea_thread:foreign"
        )
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "contradicts eligible thread audit",
        ):
            validate_reaction_effect(current_mismatch)

        source_mismatch = copy.deepcopy(receipt)
        source_mismatch["linked_only_items"][0]["source_refs"] = [
            "telegram:@foreign"
        ]
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "contradicts eligible thread audit",
        ):
            validate_reaction_effect(source_mismatch)

        missing_evidence = copy.deepcopy(receipt)
        missing_evidence["linked_only_items"][0]["evidence_refs"] = []
        missing_evidence["eligible_thread_audit"][0]["evidence_refs"] = []
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "requires sorted unique evidence_refs",
        ):
            validate_reaction_effect(missing_evidence)

        strong_role = copy.deepcopy(receipt)
        strong_role["linked_only_items"][0]["boost_role"] = "strong"
        strong_role["eligible_thread_audit"][0]["boost_role"] = "strong"
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "weak-interest policy",
        ):
            validate_reaction_effect(strong_role)

        garbage_evidence = copy.deepcopy(receipt)
        garbage_evidence["linked_only_items"][0]["evidence_refs"] = ["garbage"]
        garbage_evidence["eligible_thread_audit"][0]["evidence_refs"] = ["garbage"]
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "requires sorted unique evidence_refs",
        ):
            validate_reaction_effect(garbage_evidence)

        false_item_reason = copy.deepcopy(receipt)
        false_item_reason["linked_only_items"][0]["reader_reason_ru"] = (
            "Вы отметили 999 постов."
        )
        false_item_reason["eligible_thread_audit"][0]["reader_reason_ru"] = (
            "Вы отметили 999 постов."
        )
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "reader reason does not match",
        ):
            validate_reaction_effect(false_item_reason)

        invalid_post_ref = copy.deepcopy(receipt)
        invalid_post_ref["linked_only_items"][0]["reacted_post_refs"] = ["plain-post"]
        invalid_post_ref["eligible_thread_audit"][0]["reacted_post_refs"] = [
            "plain-post"
        ]
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "requires sorted unique reacted_post_refs",
        ):
            validate_reaction_effect(invalid_post_ref)

        invalid_source_ref = copy.deepcopy(receipt)
        invalid_source_ref["linked_only_items"][0]["source_refs"] = ["raw-id"]
        invalid_source_ref["eligible_thread_audit"][0]["source_refs"] = ["raw-id"]
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "requires sorted unique source_refs",
        ):
            validate_reaction_effect(invalid_source_ref)

    def test_receipt_validator_bounds_union_of_distinct_selected_posts(self):
        self._seed_lineage(1, 1)
        self._seed_lineage(2, 1)
        _ordered, receipt = self._personalize(
            [self._candidate(1)],
            [self._observation(1), self._observation(2)],
        )
        self.assertEqual(
            receipt["linked_only_items"][0]["reacted_post_count"],
            2,
        )

        impossible = copy.deepcopy(receipt)
        impossible["counts"]["eligible_period_posts"] = 1
        with self.assertRaisesRegex(
            ReactionPersonalizationError,
            "references more posts",
        ):
            validate_reaction_effect(impossible)

    def test_pattern_requires_explicit_completed_attestation(self):
        observations = [
            {
                "reporting_week": week,
                "period_mode": "explicit_iso_week",
                "compatibility_thread_ref": "idea_thread:eval-gates",
                "post_refs": [f"p{index}"],
                "source_refs": ["@source"],
            }
            for index, week in enumerate(
                ("2026-W26", "2026-W27", "2026-W28", "2026-W28"),
                start=1,
            )
        ]
        self.assertEqual(
            build_reaction_pattern_proposals(
                observations,
                as_of_week_label="2026-W28",
            ),
            [],
        )
        for observation in observations:
            observation["completed"] = True
        self.assertEqual(
            len(
                build_reaction_pattern_proposals(
                    observations,
                    as_of_week_label="2026-W28",
                )
            ),
            1,
        )

    def test_repeated_pattern_requires_three_completed_weeks_and_four_distinct_posts(self):
        base = {
            "period_mode": "completed_iso_week",
            "completed": True,
            "current_thread_ref": "idea_thread:eval-gates",
            "source_refs": ["@source-a"],
        }
        two_weeks_four_posts = [
            {**base, "reporting_week": "2026-W27", "post_refs": ["p1", "p2"]},
            {**base, "reporting_week": "2026-W28", "post_refs": ["p3", "p4"]},
        ]
        three_weeks_three_posts = [
            {**base, "reporting_week": week, "post_ref": f"p{index}"}
            for index, week in enumerate(("2026-W26", "2026-W27", "2026-W28"), 1)
        ]
        self.assertEqual(
            build_reaction_pattern_proposals(
                two_weeks_four_posts, as_of_week_label="2026-W28"
            ),
            [],
        )
        self.assertEqual(
            build_reaction_pattern_proposals(
                three_weeks_three_posts, as_of_week_label="2026-W28"
            ),
            [],
        )

    def test_qualifying_pattern_creates_unapproved_compatibility_proposal_without_mutation(self):
        observations = [
            {
                "reporting_week": "2026-W26",
                "period_mode": "completed_iso_week",
                "completed": True,
                "compatibility_thread_ref": "idea_thread:eval-gates",
                "canonical_thread_ref": None,
                "post_refs": ["p1", "p2"],
                "source_refs": ["@source-a"],
            },
            {
                "reporting_week": "2026-W27",
                "period_mode": "completed_iso_week",
                "completed": True,
                "compatibility_thread_ref": "idea_thread:eval-gates",
                "post_refs": ["p3"],
                "source_refs": ["@source-b"],
            },
            {
                "reporting_week": "2026-W28",
                "period_mode": "completed_iso_week",
                "completed": True,
                "compatibility_thread_ref": "idea_thread:eval-gates",
                "post_refs": ["p4"],
                "source_refs": ["@source-a"],
            },
            {
                "reporting_week": "2026-W28",
                "period_mode": "partial_iso_week",
                "completed": False,
                "compatibility_thread_ref": "idea_thread:eval-gates",
                "post_refs": ["ignored"],
            },
        ]
        original = copy.deepcopy(observations)

        proposals = build_reaction_pattern_proposals(
            observations,
            as_of_week_label="2026-W28",
        )

        self.assertEqual(observations, original)
        self.assertEqual(len(proposals), 1)
        proposal = proposals[0]
        self.assertEqual(proposal["status"], "unapproved")
        self.assertFalse(proposal["applied"])
        self.assertTrue(proposal["requires_approval"])
        self.assertEqual(proposal["mutation_policy"], "suggestion_only_no_auto_edit")
        self.assertEqual(proposal["distinct_week_count"], 3)
        self.assertEqual(proposal["distinct_reacted_post_count"], 4)
        self.assertEqual(proposal["source_diversity"], 2)
        self.assertIsNone(proposal["thread_resolution"]["canonical_thread_ref"])
        self.assertEqual(
            proposal["thread_resolution"]["resolution_status"],
            "compatibility_pending_irx4",
        )


if __name__ == "__main__":
    unittest.main()
