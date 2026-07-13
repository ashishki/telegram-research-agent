import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from db.canonical_idea_threads import (
    CanonicalLifecycleError,
    apply_canonical_lifecycle,
    fetch_canonical_provenance,
    fetch_canonical_thread,
    fetch_canonical_threads,
    fetch_curator_decision,
    resolve_canonical_atoms,
    resolve_canonical_thread,
    stable_canonical_thread_id,
    validate_canonical_lifecycle,
)
from db.idea_threads import link_idea_thread_atom, upsert_idea_thread
from db.knowledge_atoms import record_knowledge_atom
from db.migrate import run_migrations


class TestCanonicalIdeaThreads(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.db_path = tmp.name
        with patch.dict(os.environ, {"AGENT_DB_PATH": self.db_path}, clear=False):
            run_migrations()
        self.connection = sqlite3.connect(self.db_path)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._run_counter = 0

    def tearDown(self) -> None:
        self.connection.close()
        for suffix in ("", "-shm", "-wal"):
            try:
                os.unlink(self.db_path + suffix)
            except FileNotFoundError:
                pass

    def _atom(self, index: int, *, entity: str = "Claude") -> int:
        atom = record_knowledge_atom(
            self.connection,
            week_label="2026-W28",
            atom_type="research_claim",
            claim=f"Canonical claim {index}",
            summary=f"Summary {index}",
            evidence_quote=f"Verbatim evidence {index}",
            source_post_ids=[1000 + index],
            source_urls=[f"https://t.me/source/{1000 + index}"],
            entities=[entity],
            confidence=0.7,
            first_seen_at=f"2026-07-{index:02d}T08:00:00Z",
            last_seen_at=f"2026-07-{index:02d}T08:00:00Z",
        )
        return int(atom["id"])

    def _raw_thread(self, index: int, atom_ids: list[int]) -> int:
        raw = upsert_idea_thread(
            self.connection,
            slug=f"raw-thread-{index}",
            title=f"Raw Thread {index}",
            summary="Mutable compatibility projection",
            status="active",
            first_seen_at="2026-07-01T08:00:00Z",
            last_seen_at="2026-07-10T08:00:00Z",
            momentum_7d=0.5,
            momentum_30d=0.4,
            momentum_90d=0.3,
            atom_count=len(atom_ids),
            source_channels=["source"],
            key_entities=["Claude"],
            current_claims=[f"Claim {value}" for value in atom_ids],
        )
        raw_id = int(raw["id"])
        for atom_id in atom_ids:
            link_idea_thread_atom(
                self.connection,
                thread_id=raw_id,
                atom_id=atom_id,
                relation="supports",
                created_at="2026-07-10T09:00:00Z",
            )
        return raw_id

    def _thread_descriptor(
        self,
        slug: str,
        *,
        title_suffix: str | None = None,
        first_seen_at: str = "2026-07-01T08:00:00Z",
        last_seen_at: str = "2026-07-10T08:00:00Z",
    ) -> dict:
        suffix = title_suffix or slug.replace("-", " ").title()
        return {
            "stable_slug": slug,
            "title_ru": f"Русский тезис {suffix}",
            "title_en": f"English thesis {suffix}",
            "thesis": f"Durable idea-level thesis for {suffix}.",
            "status": "active",
            "first_seen_at": first_seen_at,
            "last_seen_at": last_seen_at,
            "evidence_maturity": "multi_channel",
            "operator_interest": 0.6,
            "entities": ["Claude", "Anthropic"],
        }

    def _apply(
        self,
        proposal: dict,
        *,
        event_at: str,
        operation: str | None = None,
        actor: str = "curator",
    ) -> dict:
        self._run_counter += 1
        return apply_canonical_lifecycle(
            self.connection,
            proposal=proposal,
            run_id=f"run-{self._run_counter}",
            operation=operation,
            model="deterministic-test-curator",
            model_version="1",
            curator_version="irx4-test.v1",
            reason=f"focused test decision {self._run_counter}",
            event_at=event_at,
            actor=actor,
        )

    def _create(
        self,
        slug: str,
        atom_ids: list[int],
        *,
        raw_thread_id: int | None = None,
        event_at: str = "2026-07-11T00:00:00Z",
        aliases: list[dict] | None = None,
        title_suffix: str | None = None,
    ) -> dict:
        memberships = [
            {
                "atom_id": atom_id,
                **({"raw_thread_id": raw_thread_id} if raw_thread_id is not None else {}),
            }
            for atom_id in atom_ids
        ]
        proposal = {
            "operation": "create",
            "thread": self._thread_descriptor(slug, title_suffix=title_suffix),
            "atom_memberships": memberships,
            "aliases": aliases or [],
        }
        return self._apply(proposal, event_at=event_at)

    def test_migration_is_additive_and_creates_temporal_constraints(self):
        table_names = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        index_names = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }
        for table_name in (
            "canonical_idea_threads",
            "canonical_idea_thread_versions",
            "canonical_idea_thread_atom_history",
            "canonical_idea_thread_alias_history",
            "canonical_idea_thread_lineage",
            "canonical_idea_thread_curator_decisions",
        ):
            self.assertIn(table_name, table_names)
        for index_name in (
            "uq_canonical_idea_thread_versions_current",
            "uq_canonical_atom_current_owner",
            "uq_canonical_alias_current_owner",
            "uq_canonical_idea_threads_active_title_ru",
        ):
            self.assertIn(index_name, index_names)
        raw_columns = {
            row[1] for row in self.connection.execute("PRAGMA table_info(idea_threads)")
        }
        raw_link_columns = {
            row[1] for row in self.connection.execute("PRAGMA table_info(idea_thread_atoms)")
        }
        self.assertNotIn("canonical_thread_id", raw_columns)
        self.assertEqual(raw_link_columns, {"thread_id", "atom_id", "relation", "created_at"})

    def test_create_normalizes_utc_preserves_raw_provenance_and_is_idempotent(self):
        atom_id = self._atom(1)
        raw_id = self._raw_thread(1, [atom_id])
        proposal = {
            "operation": "create",
            "event_at": "2026-07-11T02:00:00+02:00",
            "thread": self._thread_descriptor("claude-j-space"),
            "atom_memberships": [{"atom_id": atom_id, "raw_thread_id": raw_id}],
            "aliases": [{"alias_type": "legacy_ref", "alias_value": "old:j-space"}],
        }
        kwargs = {
            "proposal": proposal,
            "run_id": "stable-run",
            "model": "deterministic-test-curator",
            "model_version": "1",
            "curator_version": "irx4-test.v1",
            "reason": "stable create",
        }
        first = apply_canonical_lifecycle(self.connection, **kwargs)
        second = apply_canonical_lifecycle(self.connection, **kwargs)
        thread_id = stable_canonical_thread_id("claude-j-space")
        self.assertEqual(first["affected_thread_ids"], [thread_id])
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        current = fetch_canonical_provenance(self.connection, thread_id)
        self.assertEqual(current["valid_from"], "2026-07-11T00:00:00.000000Z")
        self.assertEqual(current["atom_ids"], [atom_id])
        self.assertEqual(current["raw_thread_ids"], [raw_id])
        self.assertEqual(current["source_post_ids"], [1001])
        self.assertEqual(current["source_urls"], ["https://t.me/source/1001"])
        self.assertEqual(current["atoms"][0]["evidence_quote"], "Verbatim evidence 1")
        self.assertRegex(current["snapshot_fingerprint"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            resolve_canonical_thread(self.connection, "idea_thread:raw-thread-1")[
                "canonical_thread_id"
            ],
            thread_id,
        )
        self.assertEqual(
            resolve_canonical_atoms(self.connection, [atom_id])["canonical_thread_id"],
            thread_id,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM canonical_idea_thread_versions"
            ).fetchone()[0],
            1,
        )

    def test_update_has_exclusive_boundary_and_rejects_slug_churn_atom_loss_and_titles(self):
        atom_a = self._atom(1)
        atom_b = self._atom(2)
        first = self._create("agent-evals", [atom_a], title_suffix="Agent Evals")
        thread_id = first["affected_thread_ids"][0]
        correction = {
            "operation": "update",
            "thread": {
                "canonical_thread_id": thread_id,
                "title_ru": "Русский тезис Агентские eval-гейты",
                "title_en": "English thesis Agent eval gates",
                "thesis": "Eval gates increasingly govern agent release safety.",
                "last_seen_at": "2026-07-12T08:00:00Z",
            },
            "atom_ids": [atom_a, atom_b],
        }
        self._apply(correction, event_at="2026-07-13T00:00:00Z")
        at_boundary = fetch_canonical_thread(
            self.connection, thread_id, as_of="2026-07-13T00:00:00Z"
        )
        after_boundary = fetch_canonical_thread(
            self.connection, thread_id, as_of="2026-07-13T00:00:00.000001Z"
        )
        self.assertEqual(at_boundary["title_en"], "English thesis Agent Evals")
        self.assertEqual(at_boundary["atom_ids"], [atom_a])
        self.assertEqual(after_boundary["title_en"], "English thesis Agent eval gates")
        self.assertEqual(after_boundary["atom_ids"], [atom_a, atom_b])

        churn = {
            "operation": "update",
            "thread": {
                "canonical_thread_id": thread_id,
                "stable_slug": "renamed-agent-evals",
            },
        }
        self.assertRegex(
            validate_canonical_lifecycle(
                self.connection,
                churn,
                curator_version="irx4-test.v1",
                event_at="2026-07-14T00:00:00Z",
            )[0],
            "canonical_thread_id|stable_slug",
        )
        atom_loss = {
            "operation": "update",
            "thread": {"canonical_thread_id": thread_id},
            "atom_ids": [atom_a],
        }
        self.assertIn(
            "atom loss",
            validate_canonical_lifecycle(
                self.connection,
                atom_loss,
                curator_version="irx4-test.v1",
                event_at="2026-07-14T00:00:00Z",
            )[0],
        )
        atom_c = self._atom(3)
        duplicate_title = {
            "operation": "create",
            "thread": self._thread_descriptor("another-thread", title_suffix="Agent eval gates"),
            "atom_ids": [atom_c],
        }
        self.assertIn(
            "duplicate active",
            validate_canonical_lifecycle(
                self.connection,
                duplicate_title,
                curator_version="irx4-test.v1",
                event_at="2026-07-14T00:00:00Z",
            )[0],
        )

    def test_merge_transfers_memberships_aliases_and_preserves_historical_old_refs(self):
        atom_a = self._atom(1, entity="Fable")
        atom_b = self._atom(2, entity="Fable 5")
        raw_a = self._raw_thread(1, [atom_a])
        raw_b = self._raw_thread(2, [atom_b])
        source_a = self._create("fable-pricing", [atom_a], raw_thread_id=raw_a)
        source_b = self._create(
            "fable-native-port", [atom_b], raw_thread_id=raw_b, event_at="2026-07-11T00:00:01Z"
        )
        source_ids = [source_a["affected_thread_ids"][0], source_b["affected_thread_ids"][0]]
        merge = {
            "operation": "merge",
            "source_thread_ids": source_ids,
            "target": {
                "thread": self._thread_descriptor(
                    "fable-generated-software-economics", title_suffix="Fable Software Economics"
                )
            },
        }
        result = self._apply(merge, event_at="2026-07-13T00:00:00Z")
        target_id = stable_canonical_thread_id("fable-generated-software-economics")
        self.assertIn(target_id, result["affected_thread_ids"])
        target = fetch_canonical_thread(self.connection, target_id)
        self.assertEqual(target["atom_ids"], [atom_a, atom_b])
        self.assertEqual(target["raw_thread_ids"], [raw_a, raw_b])
        self.assertEqual(target["merged_from"], sorted(source_ids))
        self.assertEqual(
            {fetch_canonical_thread(self.connection, value)["status"] for value in source_ids},
            {"merged"},
        )
        self.assertEqual(
            resolve_canonical_thread(self.connection, "idea_thread:raw-thread-1")[
                "canonical_thread_id"
            ],
            target_id,
        )
        historical = resolve_canonical_thread(
            self.connection,
            "idea_thread:raw-thread-1",
            as_of="2026-07-13T00:00:00Z",
        )
        self.assertEqual(historical["canonical_thread_id"], source_ids[0])
        self.assertEqual(
            resolve_canonical_atoms(
                self.connection, [atom_a], as_of="2026-07-13T00:00:00Z"
            )["canonical_thread_id"],
            source_ids[0],
        )
        self.assertEqual(
            resolve_canonical_atoms(
                self.connection, [atom_a], as_of="2026-07-13T00:00:00.000001Z"
            )["canonical_thread_id"],
            target_id,
        )

    def test_split_one_broad_raw_thread_keeps_old_alias_and_partitions_atoms(self):
        atom_a = self._atom(1)
        atom_b = self._atom(2)
        raw_id = self._raw_thread(1, [atom_a, atom_b])
        source = self._create("claude-mixed-ideas", [atom_a, atom_b], raw_thread_id=raw_id)
        source_id = source["affected_thread_ids"][0]
        split = {
            "operation": "split",
            "source_thread_id": source_id,
            "outputs": [
                {
                    "thread": self._thread_descriptor(
                        "claude-interpretability", title_suffix="Claude Interpretability"
                    ),
                    "atom_ids": [atom_a],
                },
                {
                    "thread": self._thread_descriptor(
                        "agent-release-safety", title_suffix="Agent Release Safety"
                    ),
                    "atom_ids": [atom_b],
                },
            ],
        }
        self._apply(split, event_at="2026-07-13T00:00:00Z")
        output_a = stable_canonical_thread_id("claude-interpretability")
        output_b = stable_canonical_thread_id("agent-release-safety")
        self.assertEqual(fetch_canonical_thread(self.connection, source_id)["status"], "split")
        self.assertEqual(fetch_canonical_thread(self.connection, output_a)["atom_ids"], [atom_a])
        self.assertEqual(fetch_canonical_thread(self.connection, output_b)["atom_ids"], [atom_b])
        self.assertEqual(fetch_canonical_thread(self.connection, output_a)["split_from"], [source_id])
        self.assertEqual(fetch_canonical_thread(self.connection, output_b)["split_from"], [source_id])
        self.assertIsNone(resolve_canonical_atoms(self.connection, [atom_a, atom_b]))
        self.assertEqual(resolve_canonical_atoms(self.connection, [atom_a])["canonical_thread_id"], output_a)
        self.assertEqual(resolve_canonical_atoms(self.connection, [atom_b])["canonical_thread_id"], output_b)
        old_ref = resolve_canonical_thread(self.connection, "idea_thread:raw-thread-1")
        self.assertEqual(old_ref["canonical_thread_id"], source_id)
        self.assertEqual(old_ref["split_into"], sorted([output_a, output_b]))

        losing_split = {
            "operation": "split",
            "source_thread_id": output_a,
            "outputs": [
                {
                    "thread": self._thread_descriptor("loss-a", title_suffix="Loss A"),
                    "atom_ids": [atom_a],
                },
                {
                    "thread": self._thread_descriptor("loss-b", title_suffix="Loss B"),
                    "atom_ids": [],
                },
            ],
        }
        errors = validate_canonical_lifecycle(
            self.connection,
            losing_split,
            curator_version="irx4-test.v1",
            event_at="2026-07-14T00:00:00Z",
        )
        self.assertTrue(errors)

    def test_merge_one_source_into_existing_target_is_incremental(self):
        atom_a = self._atom(1)
        atom_b = self._atom(2)
        target = self._create("existing-target", [atom_a], title_suffix="Existing Target")
        source = self._create(
            "incremental-source",
            [atom_b],
            event_at="2026-07-11T00:00:01Z",
            title_suffix="Incremental Source",
        )
        target_id = target["affected_thread_ids"][0]
        source_id = source["affected_thread_ids"][0]
        self._apply(
            {
                "operation": "merge",
                "source_thread_ids": [source_id],
                "target": {
                    "canonical_thread_id": target_id,
                    "title_ru": "Расширенный существующий тезис",
                    "title_en": "Expanded existing target",
                    "thesis": "The existing durable target gains one incremental fragment.",
                },
            },
            event_at="2026-07-13T00:00:00Z",
        )
        current = fetch_canonical_thread(self.connection, target_id)
        self.assertEqual(current["atom_ids"], [atom_a, atom_b])
        self.assertEqual(current["merged_from"], [source_id])
        self.assertEqual(fetch_canonical_thread(self.connection, source_id)["status"], "merged")

    def test_duplicate_ownership_alias_collision_and_lineage_cycle_are_rejected_atomically(self):
        atom_a = self._atom(1)
        atom_b = self._atom(2)
        first = self._create(
            "first-thread",
            [atom_a],
            aliases=[{"alias_type": "manual", "alias_value": "shared-alias"}],
        )
        second_id = stable_canonical_thread_id("second-thread")
        duplicate_owner = {
            "operation": "create",
            "thread": self._thread_descriptor("second-thread", title_suffix="Second Thread"),
            "atom_ids": [atom_a],
        }
        with self.assertRaisesRegex(CanonicalLifecycleError, "already has active"):
            self._apply(duplicate_owner, event_at="2026-07-12T00:00:00Z")
        self.assertIsNone(fetch_canonical_thread(self.connection, second_id))
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM canonical_idea_thread_versions"
            ).fetchone()[0],
            1,
        )
        alias_collision = {
            "operation": "create",
            "thread": self._thread_descriptor("alias-collision", title_suffix="Alias Collision"),
            "atom_ids": [atom_b],
            "aliases": [{"alias_type": "manual", "alias_value": "SHARED-ALIAS"}],
        }
        with self.assertRaisesRegex(CanonicalLifecycleError, "alias collision"):
            self._apply(alias_collision, event_at="2026-07-12T00:00:01Z")

        second = self._create(
            "second-thread", [atom_b], event_at="2026-07-12T00:00:02Z", title_suffix="Second Thread"
        )
        first_id = first["affected_thread_ids"][0]
        second_id = second["affected_thread_ids"][0]
        self.connection.execute(
            """
            INSERT INTO canonical_idea_thread_lineage (
                relation_type, from_thread_id, to_thread_id, decision_id,
                event_at, reason, created_at
            ) VALUES ('split', ?, ?, 'manual-cycle-fixture',
                      '2026-07-12T00:00:03Z', 'cycle fixture', '2026-07-12T00:00:03Z')
            """,
            (second_id, first_id),
        )
        self.connection.commit()
        atom_c = self._atom(3)
        third = self._create(
            "third-thread", [atom_c], event_at="2026-07-12T00:00:04Z", title_suffix="Third Thread"
        )
        merge_cycle = {
            "operation": "merge",
            "source_thread_ids": [first_id, third["affected_thread_ids"][0]],
            "target": {"canonical_thread_id": second_id},
        }
        self.assertIn(
            "cycle",
            validate_canonical_lifecycle(
                self.connection,
                merge_cycle,
                curator_version="irx4-test.v1",
                event_at="2026-07-13T00:00:00Z",
            )[0],
        )

    def test_alias_types_are_namespaced_and_untyped_ambiguity_fails_closed(self):
        atom_a = self._atom(1)
        atom_b = self._atom(2)
        raw_id = self._raw_thread(1, [atom_b])
        first = self._create(
            "manual-number-alias",
            [atom_a],
            aliases=[{"alias_type": "manual", "alias_value": str(raw_id)}],
        )
        second = self._create(
            "raw-number-alias",
            [atom_b],
            raw_thread_id=raw_id,
            event_at="2026-07-11T00:00:01Z",
        )
        self.assertIsNone(resolve_canonical_thread(self.connection, str(raw_id)))
        self.assertEqual(
            resolve_canonical_thread(
                self.connection, str(raw_id), alias_type="manual"
            )["canonical_thread_id"],
            first["affected_thread_ids"][0],
        )
        self.assertEqual(
            resolve_canonical_thread(
                self.connection, str(raw_id), alias_type="raw_thread_id"
            )["canonical_thread_id"],
            second["affected_thread_ids"][0],
        )

    def test_operator_correction_appends_history_and_invalid_actor_is_audited(self):
        atom_id = self._atom(1)
        created = self._create("operator-fix", [atom_id], title_suffix="Operator Fix")
        thread_id = created["affected_thread_ids"][0]
        correction = {
            "operation": "operator_correction",
            "thread": {
                "canonical_thread_id": thread_id,
                "title_ru": "Исправленный оператором тезис",
                "title_en": "Operator-corrected thesis",
                "thesis": "The corrected thesis remains fully auditable.",
            },
        }
        applied = self._apply(
            correction,
            event_at="2026-07-13T00:00:00Z",
            actor="operator:owner",
        )
        self.assertEqual(
            fetch_canonical_thread(self.connection, thread_id)["title_en"],
            "Operator-corrected thesis",
        )
        historical = fetch_canonical_thread(
            self.connection, thread_id, as_of="2026-07-13T00:00:00Z"
        )
        self.assertEqual(historical["title_en"], "English thesis Operator Fix")
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM canonical_idea_thread_versions WHERE canonical_thread_id = ?",
                (thread_id,),
            ).fetchone()[0],
            2,
        )
        self.assertEqual(applied["decision"]["actor"], "operator:owner")

        invalid = {
            "operation": "operator_correction",
            "thread": {"canonical_thread_id": thread_id, "thesis": "Unauthorised change"},
        }
        with self.assertRaisesRegex(CanonicalLifecycleError, "operator actor"):
            self._apply(invalid, event_at="2026-07-14T00:00:00Z", actor="curator")
        rejected = self.connection.execute(
            """
            SELECT decision_id FROM canonical_idea_thread_curator_decisions
            WHERE operation = 'operator_correction' AND decision_status = 'rejected'
            ORDER BY proposed_at DESC LIMIT 1
            """
        ).fetchone()[0]
        audit = fetch_curator_decision(self.connection, rejected)
        self.assertEqual(audit["validation_status"], "rejected")
        self.assertEqual(
            fetch_canonical_thread(self.connection, thread_id)["title_en"],
            "Operator-corrected thesis",
        )

    def test_stale_transition_is_historical_and_idempotent_without_provenance_churn(self):
        atom_id = self._atom(1)
        raw_id = self._raw_thread(1, [atom_id])
        created = self._create("stale-watch", [atom_id], raw_thread_id=raw_id)
        thread_id = created["affected_thread_ids"][0]
        before = fetch_canonical_thread(self.connection, thread_id)
        proposal = {"operation": "stale", "canonical_thread_id": thread_id}
        kwargs = {
            "proposal": proposal,
            "run_id": "stable-stale-run",
            "model": "deterministic-test-curator",
            "model_version": "1",
            "curator_version": "irx4-test.v1",
            "reason": "no qualifying evidence in the bounded period",
            "event_at": "2026-07-13T00:00:00Z",
        }
        first = apply_canonical_lifecycle(self.connection, **kwargs)
        second = apply_canonical_lifecycle(self.connection, **kwargs)
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        at_boundary = fetch_canonical_thread(
            self.connection, thread_id, as_of="2026-07-13T00:00:00Z"
        )
        after_boundary = fetch_canonical_thread(
            self.connection, thread_id, as_of="2026-07-13T00:00:00.000001Z"
        )
        self.assertEqual(at_boundary["status"], "active")
        self.assertEqual(after_boundary["status"], "stale")
        self.assertEqual(after_boundary["atom_ids"], before["atom_ids"])
        self.assertEqual(after_boundary["aliases"], before["aliases"])
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM canonical_idea_thread_versions WHERE canonical_thread_id = ?",
                (thread_id,),
            ).fetchone()[0],
            2,
        )

    def test_audit_only_raw_candidate_decisions_never_mutate_registry(self):
        atom_a = self._atom(1)
        atom_b = self._atom(2)
        raw_a = self._raw_thread(1, [atom_a])
        raw_b = self._raw_thread(2, [atom_b])
        proposal = {
            "operation": "keep_separate",
            "source_records": [
                {"raw_thread_id": raw_a, "atom_ids": [atom_a]},
                {"raw_thread_id": raw_b, "atom_ids": [atom_b]},
            ],
            "evidence": [{"reason": "same vendor, different theses"}],
        }
        result = self._apply(proposal, event_at="2026-07-13T00:00:00Z")
        self.assertTrue(result["decision"]["result"]["audit_only"])
        self.assertEqual(fetch_canonical_threads(self.connection), [])
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM canonical_idea_thread_versions"
            ).fetchone()[0],
            0,
        )

        together = {
            "operation": "keep_together",
            "review_subject": {"raw_thread_id": raw_a, "atom_ids": [atom_a]},
            "evidence": [{"reason": "model version alone does not split"}],
        }
        result = self._apply(together, event_at="2026-07-13T00:00:01Z")
        self.assertTrue(result["decision"]["result"]["audit_only"])
        deferred = {
            "operation": "defer",
            "evidence": [{"reason": "insufficient semantic evidence"}],
        }
        result = self._apply(deferred, event_at="2026-07-13T00:00:02Z")
        self.assertTrue(result["decision"]["result"]["audit_only"])

    def test_raw_tables_are_byte_for_byte_unchanged_by_canonical_lifecycle(self):
        atom_a = self._atom(1)
        atom_b = self._atom(2)
        raw_a = self._raw_thread(1, [atom_a])
        raw_b = self._raw_thread(2, [atom_b])
        before_threads = self.connection.execute(
            "SELECT * FROM idea_threads ORDER BY id"
        ).fetchall()
        before_links = self.connection.execute(
            "SELECT * FROM idea_thread_atoms ORDER BY thread_id, atom_id"
        ).fetchall()
        first = self._create("raw-parity-a", [atom_a], raw_thread_id=raw_a)
        second = self._create(
            "raw-parity-b", [atom_b], raw_thread_id=raw_b, event_at="2026-07-11T00:00:01Z"
        )
        self._apply(
            {
                "operation": "merge",
                "source_thread_ids": [
                    first["affected_thread_ids"][0],
                    second["affected_thread_ids"][0],
                ],
                "target": {
                    "thread": self._thread_descriptor(
                        "raw-parity-merged", title_suffix="Raw Parity Merged"
                    )
                },
            },
            event_at="2026-07-13T00:00:00Z",
        )
        self.assertEqual(
            self.connection.execute("SELECT * FROM idea_threads ORDER BY id").fetchall(),
            before_threads,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT * FROM idea_thread_atoms ORDER BY thread_id, atom_id"
            ).fetchall(),
            before_links,
        )


if __name__ == "__main__":
    unittest.main()
