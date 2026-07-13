import copy
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from db.idea_threads import link_idea_thread_atom, upsert_idea_thread
from db.knowledge_atoms import record_knowledge_atom
from db.canonical_idea_threads import (
    apply_canonical_lifecycle,
    fetch_canonical_threads,
    resolve_canonical_atoms,
)
from output.idea_thread_curator import (
    CURATOR_PROPOSAL_SCHEMA_VERSION,
    GROUPING_CANDIDATE_SCHEMA_VERSION,
    CuratorContractError,
    StoredCanonicalThreadResolver,
    apply_curator_proposal,
    build_curator_proposal,
    generate_grouping_candidates,
    record_curator_proposal,
    validate_curator_proposal,
)


class TestIdeaThreadCurator(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute(
            """
            CREATE TABLE idea_threads (
                id INTEGER PRIMARY KEY,
                slug TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                source_channels_json TEXT NOT NULL DEFAULT '[]',
                key_entities_json TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE knowledge_atoms (
                id INTEGER PRIMARY KEY,
                atom_type TEXT NOT NULL,
                claim TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                evidence_quote TEXT NOT NULL DEFAULT '',
                source_post_ids_json TEXT NOT NULL,
                source_urls_json TEXT NOT NULL,
                entities_json TEXT NOT NULL DEFAULT '[]',
                tools_json TEXT NOT NULL DEFAULT '[]',
                models_json TEXT NOT NULL DEFAULT '[]',
                practices_json TEXT NOT NULL DEFAULT '[]',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE idea_thread_atoms (
                thread_id INTEGER NOT NULL,
                atom_id INTEGER NOT NULL,
                relation TEXT NOT NULL DEFAULT 'supports',
                PRIMARY KEY (thread_id, atom_id)
            )
            """
        )

    def tearDown(self) -> None:
        self.connection.close()

    def _thread(self, thread_id: int, slug: str, *, title: str | None = None) -> None:
        self.connection.execute(
            """
            INSERT INTO idea_threads (
                id, slug, title, summary, status, first_seen_at, last_seen_at,
                source_channels_json, key_entities_json
            ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                thread_id,
                slug,
                title or slug.replace("-", " ").title(),
                f"Raw compatibility cluster {slug}",
                "2026-07-01T00:00:00Z",
                "2026-07-08T00:00:00Z",
                f'["source-{thread_id}"]',
                "[]",
            ),
        )

    def _atom(
        self,
        atom_id: int,
        thread_id: int,
        *,
        claim: str,
        entities: list[str] | None = None,
        models: list[str] | None = None,
        practices: list[str] | None = None,
    ) -> None:
        import json

        self.connection.execute(
            """
            INSERT INTO knowledge_atoms (
                id, atom_type, claim, summary, evidence_quote,
                source_post_ids_json, source_urls_json, entities_json,
                tools_json, models_json, practices_json, first_seen_at,
                last_seen_at
            ) VALUES (?, 'engineering_practice', ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, ?)
            """,
            (
                atom_id,
                claim,
                claim,
                claim,
                json.dumps([10_000 + atom_id]),
                json.dumps([f"https://t.me/source_{thread_id}/{10_000 + atom_id}"]),
                json.dumps(entities or []),
                json.dumps(models or []),
                json.dumps(practices or []),
                "2026-07-01T00:00:00Z",
                "2026-07-08T00:00:00Z",
            ),
        )
        self.connection.execute(
            "INSERT INTO idea_thread_atoms (thread_id, atom_id, relation) VALUES (?, ?, 'supports')",
            (thread_id, atom_id),
        )
        self.connection.commit()

    def _seed_fragmented_fable(self) -> None:
        self._thread(1, "fable-5-prototypes")
        self._atom(
            101,
            1,
            claim="Fable 5 exports interactive prototypes into maintainable code.",
            entities=["Fable"],
            models=["Fable 5"],
            practices=["portable prototype workflow"],
        )
        self._thread(2, "claude-fable-code-port")
        self._atom(
            102,
            2,
            claim="Claude Fable converts interactive prototypes into maintainable code.",
            entities=["Anthropic", "Fable"],
            models=["Claude Fable 5"],
            practices=["portable prototype workflow"],
        )

    def test_fable_claude_fragments_group_on_non_entity_practice_with_full_provenance(self):
        self._seed_fragmented_fable()

        candidates = generate_grouping_candidates(self.connection, run_id="run-2026-w28")
        grouping = [item for item in candidates if item["kind"] == "grouping_review"]

        self.assertEqual(len(grouping), 1)
        candidate = grouping[0]
        self.assertEqual(candidate["schema_version"], GROUPING_CANDIDATE_SCHEMA_VERSION)
        self.assertEqual(
            candidate["signals"]["shared_non_entity_practices"],
            ["portable-prototype-workflow"],
        )
        self.assertEqual(
            [item["raw_thread_id"] for item in candidate["raw_threads"]], [1, 2]
        )
        self.assertEqual(
            [item["atom_id"] for item in candidate["atom_evidence"]], [101, 102]
        )
        self.assertEqual(len(candidate["source_provenance"]), 4)
        self.assertTrue(candidate["provenance_complete"])
        self.assertFalse(candidate["signals"]["model_version_difference_is_split_evidence"])

    def test_shared_vendor_entity_alone_never_creates_grouping_candidate(self):
        self._thread(1, "fable-pricing")
        self._atom(
            201,
            1,
            claim="Fable changed enterprise subscription pricing and account limits.",
            entities=["Fable"],
            models=["Fable 5"],
            practices=["commercial subscription review"],
        )
        self._thread(2, "fable-code-export")
        self._atom(
            202,
            2,
            claim="Fable exports generated interfaces into a typed repository.",
            entities=["Fable"],
            models=["Fable 5"],
            practices=["prototype code handoff"],
        )

        candidates = generate_grouping_candidates(self.connection, run_id="run-entity")

        self.assertEqual(
            [item for item in candidates if item["kind"] == "grouping_review"], []
        )

    def test_model_version_aliases_group_and_do_not_create_version_only_split(self):
        self._thread(1, "claude-sonnet-35-evals")
        self._atom(
            301,
            1,
            claim="Claude Sonnet 3.5 runs eval gates before coding releases.",
            entities=["Anthropic"],
            models=["Claude Sonnet 3.5"],
            practices=["eval gated coding workflow"],
        )
        self._thread(2, "claude-sonnet-4-evals")
        self._atom(
            302,
            2,
            claim="Claude Sonnet 4 runs eval gates before coding releases.",
            entities=["Anthropic"],
            models=["Claude Sonnet 4"],
            practices=["eval gated coding workflow"],
        )
        self._atom(
            303,
            2,
            claim="Claude Sonnet 4 executes eval gates ahead of coding releases.",
            entities=["Anthropic"],
            models=["Claude Sonnet 4.1"],
            practices=["eval gated coding workflow"],
        )

        candidates = generate_grouping_candidates(self.connection, run_id="run-models")

        grouping = [item for item in candidates if item["kind"] == "grouping_review"]
        self.assertEqual(len(grouping), 1)
        self.assertEqual(
            grouping[0]["signals"]["model_aliases_audit_only"],
            ["Claude Sonnet 3.5", "Claude Sonnet 4", "Claude Sonnet 4.1"],
        )
        self.assertFalse(
            any(
                item["kind"] == "split_review"
                and item["raw_threads"][0]["raw_thread_id"] == 2
                for item in candidates
            )
        )

    def test_broad_raw_vendor_bucket_creates_bounded_split_review(self):
        self._thread(1, "claude-anthropic")
        self._atom(
            401,
            1,
            claim="Claude account access was restricted in one region.",
            entities=["Anthropic", "Claude"],
            models=["Claude 4"],
            practices=["regional access risk review"],
        )
        self._atom(
            402,
            1,
            claim="Claude agents improve repository work through repeated self-evaluation.",
            entities=["Anthropic", "Claude"],
            models=["Claude 4"],
            practices=["iterative agent self evaluation"],
        )

        candidates = generate_grouping_candidates(self.connection, run_id="run-split")
        split = [item for item in candidates if item["kind"] == "split_review"]

        self.assertEqual(len(split), 1)
        self.assertEqual(
            split[0]["allowed_operations"], ["split", "keep_together", "defer"]
        )
        self.assertEqual(
            [cluster["atom_ids"] for cluster in split[0]["suggested_output_identities"]],
            [[401], [402]],
        )
        self.assertTrue(split[0]["provenance_complete"])
        self.assertFalse(split[0]["signals"]["model_version_difference_is_split_evidence"])

    def test_version_only_atoms_inside_one_raw_thread_do_not_propose_split(self):
        self._thread(1, "claude-sonnet-versions")
        self._atom(
            451,
            1,
            claim="Claude Sonnet 3.5",
            entities=["Anthropic"],
            models=["Claude Sonnet 3.5"],
        )
        self._atom(
            452,
            1,
            claim="Claude Sonnet 4.1",
            entities=["Anthropic"],
            models=["Claude Sonnet 4.1"],
        )

        candidates = generate_grouping_candidates(self.connection, run_id="run-versions")

        self.assertFalse(any(item["kind"] == "split_review" for item in candidates))

    def test_reruns_and_hard_candidate_bounds_are_deterministic(self):
        words = [
            "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf",
            "hotel", "india", "juliet", "kilo", "lima", "mango", "november",
        ]
        for pair_index, word in enumerate(words, start=1):
            for side in range(2):
                thread_id = (pair_index * 10) + side
                atom_id = 5000 + thread_id
                self._thread(thread_id, f"{word}-thread-{side}")
                self._atom(
                    atom_id,
                    thread_id,
                    claim=f"{word} detail{side}",
                    entities=["Shared Vendor"],
                    models=[f"Model {side + 1}"],
                    practices=[f"{word}practice"],
                )

        first = generate_grouping_candidates(
            self.connection,
            run_id="run-bounds",
            max_candidates=999,
            max_raw_threads=999,
            max_threads_per_candidate=999,
            max_atoms_per_thread=999,
            max_sources_per_candidate=999,
        )
        second = generate_grouping_candidates(
            self.connection,
            run_id="run-bounds",
            max_candidates=999,
            max_raw_threads=999,
            max_threads_per_candidate=999,
            max_atoms_per_thread=999,
            max_sources_per_candidate=999,
        )

        self.assertEqual(first, second)
        self.assertEqual(len(first), 12)
        self.assertTrue(all(len(item["raw_threads"]) <= 6 for item in first))
        self.assertTrue(all(len(item["atom_evidence"]) <= 24 for item in first))
        self.assertTrue(all(len(item["source_provenance"]) <= 24 for item in first))

    def test_strong_model_output_is_inert_proposal_and_cannot_replace_identity(self):
        self._seed_fragmented_fable()
        candidate = next(
            item
            for item in generate_grouping_candidates(self.connection, run_id="run-proposal")
            if item["kind"] == "grouping_review"
        )
        before_dump = "\n".join(self.connection.iterdump())

        proposal = build_curator_proposal(
            candidate,
            {
                "thread": {
                    "title_ru": "Перенос прототипов в поддерживаемый код",
                    "title_en": "Prototype-to-maintainable-code workflow",
                    "thesis": "Прототип становится частью инженерного цикла, а не тупиком.",
                    "status": "active",
                    "first_seen_at": "2026-07-01T00:00:00Z",
                    "last_seen_at": "2026-07-08T00:00:00Z",
                }
            },
            run_id="run-proposal",
            operation="create",
            curator="bounded-strong-model",
            curator_version="curator.v1",
            model="strong-model",
            model_version="2026-07",
            reason="Both fragments cite the same portable prototype workflow.",
        )

        self.assertEqual(proposal["schema_version"], CURATOR_PROPOSAL_SCHEMA_VERSION)
        self.assertEqual(proposal["status"], "proposed")
        self.assertFalse(proposal["applied"])
        self.assertTrue(proposal["requires_deterministic_validation"])
        self.assertEqual(proposal["mutation_policy"], "proposal_only")
        self.assertEqual(proposal["run_id"], "run-proposal")
        self.assertEqual(proposal["operation"], "create")
        self.assertEqual(proposal["target"], proposal["thread"])
        self.assertEqual(proposal["suggested_identity"], candidate["suggested_identity"])
        self.assertEqual(proposal["evidence"]["atom_ids"], [101, 102])
        self.assertEqual("\n".join(self.connection.iterdump()), before_dump)

        replaced = copy.deepcopy(proposal["thread"])
        replaced["stable_slug"] = "model-invented-slug"
        with self.assertRaisesRegex(CuratorContractError, "stable suggested identity"):
            build_curator_proposal(
                candidate,
                {"thread": replaced},
                run_id="run-proposal",
                operation="create",
                curator="bounded-strong-model",
                curator_version="curator.v1",
                model="strong-model",
                model_version="2026-07",
                reason="Unsupported identity rewrite.",
            )

    def test_keep_separate_is_a_justified_audit_proposal_without_mutation_shape(self):
        self._seed_fragmented_fable()
        candidate = next(
            item
            for item in generate_grouping_candidates(self.connection, run_id="run-audit")
            if item["kind"] == "grouping_review"
        )
        before_dump = "\n".join(self.connection.iterdump())

        proposal = build_curator_proposal(
            candidate,
            {},
            run_id="run-audit",
            operation="keep_separate",
            curator="bounded-strong-model",
            curator_version="curator.v1",
            model="strong-model",
            model_version="2026-07",
            reason="Despite shared practice, the evidence supports different lifecycle owners.",
        )

        self.assertEqual(proposal["operation"], "keep_separate")
        self.assertEqual(proposal["mutation_policy"], "audit_only_no_canonical_mutation")
        self.assertEqual(proposal["review_subject"]["raw_thread_ids"], [1, 2])
        for mutation_key in ("thread", "target", "atom_memberships", "aliases", "outputs"):
            self.assertNotIn(mutation_key, proposal)
        self.assertEqual("\n".join(self.connection.iterdump()), before_dump)

    def test_validation_rejects_stale_raw_membership_before_persistence(self):
        self._seed_fragmented_fable()
        candidate = next(
            item
            for item in generate_grouping_candidates(self.connection, run_id="run-stale")
            if item["kind"] == "grouping_review"
        )
        proposal = build_curator_proposal(
            candidate,
            {
                "thread": {
                    "title_ru": "Перенос прототипов",
                    "title_en": "Prototype handoff",
                    "thesis": "Prototype evidence is curated into one durable workflow.",
                    "first_seen_at": "2026-07-01T00:00:00Z",
                    "last_seen_at": "2026-07-08T00:00:00Z",
                }
            },
            run_id="run-stale",
            operation="create",
            curator="bounded-strong-model",
            curator_version="curator.v1",
            model="strong-model",
            model_version="2026-07",
            reason="Shared stored practice evidence.",
        )
        self._atom(
            199,
            1,
            claim="A later stored atom changes the raw membership snapshot.",
            practices=["portable prototype workflow"],
        )

        findings = validate_curator_proposal(self.connection, proposal)

        self.assertTrue(any("raw atom membership changed" in item for item in findings))

    def test_validation_recomputes_non_entity_gate_before_any_merge_application(self):
        self._seed_fragmented_fable()
        candidate = next(
            item
            for item in generate_grouping_candidates(self.connection, run_id="run-semantic-gate")
            if item["kind"] == "grouping_review"
        )
        proposal = build_curator_proposal(
            candidate,
            {
                "thread": {
                    "title_ru": "Проверяемая тема",
                    "title_en": "Validated idea",
                    "thesis": "Only stored non-entity evidence can support this grouping.",
                    "first_seen_at": "2026-07-01T00:00:00Z",
                    "last_seen_at": "2026-07-08T00:00:00Z",
                }
            },
            run_id="run-semantic-gate",
            operation="create",
            curator="bounded-strong-model",
            curator_version="curator.v1",
            model="strong-model",
            model_version="2026-07",
            reason="Originally shared practice evidence.",
        )
        self.connection.execute(
            """
            UPDATE knowledge_atoms
            SET claim = 'Fable', summary = 'Fable', evidence_quote = 'Fable',
                practices_json = '[]'
            WHERE id IN (101, 102)
            """
        )
        self.connection.commit()

        findings = validate_curator_proposal(self.connection, proposal)

        self.assertIn("candidate snapshot fingerprint is stale", findings)
        self.assertTrue(
            any("entity or model overlap alone cannot merge" in item for item in findings)
        )

    def test_split_model_output_must_assign_every_atom_once_and_remains_proposal_only(self):
        self._thread(1, "claude-anthropic")
        self._atom(
            601,
            1,
            claim="Claude access restrictions affect regional availability.",
            entities=["Anthropic", "Claude"],
            models=["Claude 4"],
            practices=["regional access risk review"],
        )
        self._atom(
            602,
            1,
            claim="Claude agents improve repositories through self evaluation.",
            entities=["Anthropic", "Claude"],
            models=["Claude 4"],
            practices=["iterative agent self evaluation"],
        )
        candidate = next(
            item
            for item in generate_grouping_candidates(self.connection, run_id="run-split-proposal")
            if item["kind"] == "split_review"
        )
        outputs = []
        for index, suggestion in enumerate(candidate["suggested_output_identities"]):
            outputs.append(
                {
                    "thread": {
                        "title_ru": f"Тема {index + 1}",
                        "title_en": f"Idea {index + 1}",
                        "thesis": f"Distinct evidence thesis {index + 1}.",
                        "status": "active",
                        "first_seen_at": "2026-07-01T00:00:00Z",
                        "last_seen_at": "2026-07-08T00:00:00Z",
                    },
                    "atom_memberships": [
                        {
                            "atom_id": atom_id,
                            "raw_thread_id": 1,
                            "relation": "supports",
                        }
                        for atom_id in suggestion["atom_ids"]
                    ],
                    "aliases": [],
                }
            )
        before_dump = "\n".join(self.connection.iterdump())

        proposal = build_curator_proposal(
            candidate,
            {"source_thread_id": "ct_0123456789abcdef01234567", "outputs": outputs},
            run_id="run-split-proposal",
            operation="split",
            curator="bounded-strong-model",
            curator_version="curator.v1",
            model="strong-model",
            model_version="2026-07",
            reason="The raw vendor bucket contains two disjoint practice clusters.",
        )

        self.assertEqual(proposal["operation"], "split")
        self.assertEqual(proposal["status"], "proposed")
        self.assertFalse(proposal["applied"])
        self.assertEqual(len(proposal["outputs"]), 2)
        self.assertEqual("\n".join(self.connection.iterdump()), before_dump)

        missing = copy.deepcopy(outputs)
        missing.pop()
        with self.assertRaisesRegex(CuratorContractError, "every suggested output"):
            build_curator_proposal(
                candidate,
                {"source_thread_id": "ct_0123456789abcdef01234567", "outputs": missing},
                run_id="run-split-proposal",
                operation="split",
                curator="bounded-strong-model",
                curator_version="curator.v1",
                model="strong-model",
                model_version="2026-07",
                reason="Incomplete assignment.",
            )

    def test_stored_resolver_uses_exact_as_of_atom_memberships_and_keeps_ambiguity_nullable(self):
        resolver = StoredCanonicalThreadResolver(
            self.connection, as_of="2026-07-13T00:00:00Z"
        )
        with patch(
            "output.idea_thread_curator._canonical_alias_owners_as_of",
            return_value=set(),
        ), patch(
            "output.idea_thread_curator._period_bounded_atom_ids",
            return_value=[6, 7],
        ), patch(
            "db.canonical_idea_threads.resolve_canonical_atoms",
            return_value={"canonical_thread_id": "ct_stable", "stable_slug": "stable-idea"},
        ) as resolve:
            resolved = resolver.resolve(
                {"slug": "raw-thread", "atom_ids": [7, 6, 7]}
            )

        self.assertEqual(resolved.compatibility_thread_ref, "idea_thread:raw-thread")
        self.assertEqual(resolved.current_thread_ref, "idea_thread:raw-thread")
        self.assertEqual(resolved.canonical_thread_ref, "canonical_thread:stable-idea")
        self.assertEqual(resolved.resolution_status, "canonical_membership_resolved")
        resolve.assert_called_once_with(
            self.connection, [6, 7], as_of="2026-07-13T00:00:00.000000Z"
        )

        with patch(
            "output.idea_thread_curator._canonical_alias_owners_as_of",
            return_value=set(),
        ), patch(
            "output.idea_thread_curator._period_bounded_atom_ids",
            return_value=[6, 7],
        ), patch(
            "db.canonical_idea_threads.resolve_canonical_atoms", return_value=None
        ):
            ambiguous = resolver.resolve({"slug": "raw-thread", "atom_ids": [6, 7]})
        self.assertIsNone(ambiguous.canonical_thread_ref)
        self.assertEqual(
            ambiguous.resolution_status, "compatibility_current_thread_only"
        )

    def test_stored_resolver_uses_historical_raw_alias_before_future_raw_atoms(self):
        full = sqlite3.connect(":memory:")
        schema_path = Path(__file__).resolve().parents[1] / "src" / "db" / "schema.sql"
        full.executescript(schema_path.read_text(encoding="utf-8"))
        try:
            atom_a = record_knowledge_atom(
                full,
                week_label="2026-W28",
                atom_type="engineering_practice",
                claim="Historical atom A belongs to the release-gate idea.",
                summary="Visible before the completed W28 boundary.",
                evidence_quote="historical atom A",
                source_post_ids=[8101],
                source_urls=["https://t.me/history/8101"],
                practices=["release gate"],
                first_seen_at="2026-07-08T00:00:00Z",
                last_seen_at="2026-07-08T00:00:00Z",
            )
            raw = upsert_idea_thread(
                full,
                slug="mutable-release-gate-cluster",
                title="Mutable release gate cluster",
                summary="Raw compatibility state may gain later atoms.",
                status="active",
                first_seen_at="2026-07-08T00:00:00Z",
                last_seen_at="2026-07-08T00:00:00Z",
                momentum_7d=0.5,
                momentum_30d=0.5,
                momentum_90d=0.5,
                atom_count=1,
                source_channels=["history"],
                key_entities=[],
                current_claims=[atom_a["claim"]],
            )
            link_idea_thread_atom(
                full, thread_id=raw["id"], atom_id=atom_a["id"]
            )
            apply_canonical_lifecycle(
                full,
                proposal={
                    "operation": "create",
                    "thread": {
                        "stable_slug": "release-gates-for-agents",
                        "title_ru": "Релизные гейты для агентов",
                        "title_en": "Release gates for agents",
                        "thesis": "Release gates make agent changes safer to ship.",
                        "status": "active",
                        "first_seen_at": "2026-07-08T00:00:00Z",
                        "last_seen_at": "2026-07-08T00:00:00Z",
                        "evidence_maturity": "single_source",
                    },
                    "atom_memberships": [
                        {"atom_id": atom_a["id"], "raw_thread_id": raw["id"]}
                    ],
                },
                run_id="historical-alias-create",
                model="deterministic-test",
                model_version="1",
                curator_version="irx4-test.v1",
                reason="Create the W28 canonical owner.",
                event_at="2026-07-10T00:00:00Z",
            )

            atom_b = record_knowledge_atom(
                full,
                week_label="2026-W29",
                atom_type="engineering_practice",
                claim="Future atom B joins the mutable raw thread in W29.",
                summary="It must not erase the historical W28 owner.",
                evidence_quote="future atom B",
                source_post_ids=[8102],
                source_urls=["https://t.me/history/8102"],
                practices=["release gate"],
                first_seen_at="2026-07-15T00:00:00Z",
                last_seen_at="2026-07-15T00:00:00Z",
            )
            link_idea_thread_atom(
                full, thread_id=raw["id"], atom_id=atom_b["id"]
            )
            full.execute(
                """
                UPDATE idea_threads
                SET atom_count = 2, last_seen_at = ?
                WHERE id = ?
                """,
                ("2026-07-15T00:00:00Z", raw["id"]),
            )
            full.commit()

            self.assertIsNone(
                resolve_canonical_atoms(
                    full,
                    [atom_a["id"], atom_b["id"]],
                    as_of="2026-07-13T00:00:00Z",
                )
            )
            resolution = StoredCanonicalThreadResolver(
                full, as_of="2026-07-13T00:00:00Z"
            ).resolve(
                {
                    "id": raw["id"],
                    "slug": raw["slug"],
                    "atom_ids": [atom_a["id"], atom_b["id"]],
                }
            )
            self.assertEqual(
                resolution.canonical_thread_ref,
                "canonical_thread:release-gates-for-agents",
            )
            self.assertEqual(
                resolution.resolution_status, "canonical_membership_resolved"
            )
        finally:
            full.close()

    def test_merge_rejects_canonical_sources_unrelated_to_candidate_atom_evidence(self):
        full = sqlite3.connect(":memory:")
        schema_path = Path(__file__).resolve().parents[1] / "src" / "db" / "schema.sql"
        full.executescript(schema_path.read_text(encoding="utf-8"))
        raw_ids: list[int] = []
        atom_ids: list[int] = []
        atom_specs = (
            ("candidate-alpha", "Alpha exports prototypes into maintainable code.", "portable prototype workflow"),
            ("candidate-beta", "Beta exports prototypes into maintainable code.", "portable prototype workflow"),
            ("unrelated-pricing", "Pricing governance changes account limits.", "commercial subscription review"),
            ("unrelated-security", "Deployment security rotates service credentials.", "credential rotation review"),
        )
        for index, (slug, claim, practice) in enumerate(atom_specs, start=1):
            atom = record_knowledge_atom(
                full,
                week_label="2026-W28",
                atom_type="engineering_practice",
                claim=claim,
                summary=claim,
                evidence_quote=practice,
                source_post_ids=[800 + index],
                source_urls=[f"https://t.me/source_{index}/{800 + index}"],
                entities=["Shared Vendor"],
                practices=[practice],
                confidence=0.8,
                practical_utility_score=0.8,
                first_seen_at="2026-07-01T00:00:00Z",
                last_seen_at="2026-07-08T00:00:00Z",
            )
            raw = upsert_idea_thread(
                full,
                slug=slug,
                title=slug.replace("-", " ").title(),
                summary="Mutable raw compatibility cluster.",
                status="active",
                first_seen_at="2026-07-01T00:00:00Z",
                last_seen_at="2026-07-08T00:00:00Z",
                momentum_7d=0.5,
                momentum_30d=0.5,
                momentum_90d=0.5,
                atom_count=1,
                source_channels=[f"source_{index}"],
                key_entities=["Shared Vendor"],
                current_claims=[claim],
            )
            link_idea_thread_atom(full, thread_id=raw["id"], atom_id=atom["id"])
            raw_ids.append(int(raw["id"]))
            atom_ids.append(int(atom["id"]))
        self.assertEqual(atom_ids, [1, 2, 3, 4])

        unrelated_source_ids: list[str] = []
        for offset, atom_id in enumerate(atom_ids[2:], start=3):
            created = apply_canonical_lifecycle(
                full,
                proposal={
                    "operation": "create",
                    "thread": {
                        "stable_slug": f"unrelated-canonical-{offset}",
                        "title_ru": f"Несвязанная тема {offset}",
                        "title_en": f"Unrelated canonical {offset}",
                        "thesis": f"Unrelated lifecycle evidence {offset}.",
                        "status": "active",
                        "first_seen_at": "2026-07-01T00:00:00Z",
                        "last_seen_at": "2026-07-08T00:00:00Z",
                    },
                    "atom_memberships": [
                        {"atom_id": atom_id, "raw_thread_id": raw_ids[offset - 1]}
                    ],
                    "aliases": [],
                },
                run_id=f"seed-unrelated-{offset}",
                operation="create",
                model="deterministic-test",
                model_version="1",
                curator_version="curator.v1",
                reason="Seed an unrelated canonical source.",
                event_at="2026-07-11T00:00:00Z",
                actor="curator",
            )
            unrelated_source_ids.append(
                str(created["canonical_threads"][0]["canonical_thread_id"])
            )

        candidate = next(
            item
            for item in generate_grouping_candidates(full, run_id="run-merge-binding")
            if item["kind"] == "grouping_review"
            and [thread["raw_thread_id"] for thread in item["raw_threads"]]
            == raw_ids[:2]
        )
        proposal = build_curator_proposal(
            candidate,
            {
                "thread": {
                    "title_ru": "Перенос прототипов",
                    "title_en": "Prototype handoff",
                    "thesis": "Candidate evidence belongs to the prototype workflow.",
                    "status": "active",
                    "first_seen_at": "2026-07-01T00:00:00Z",
                    "last_seen_at": "2026-07-08T00:00:00Z",
                },
                "source_thread_ids": unrelated_source_ids,
            },
            run_id="run-merge-binding",
            operation="merge",
            curator="bounded-strong-model",
            curator_version="curator.v1",
            model="strong-model",
            model_version="2026-07",
            reason="Attempt to merge canonical sources unrelated to the candidate atoms.",
        )
        self.assertEqual(
            proposal["target"]["atom_memberships"], proposal["atom_memberships"]
        )
        self.assertEqual(proposal["target"]["aliases"], proposal["aliases"])

        with self.assertRaisesRegex(
            CuratorContractError, "reserved nested fields: thread"
        ):
            build_curator_proposal(
                candidate,
                {
                    "thread": {
                        "title_ru": "Внешняя проверенная тема",
                        "title_en": "Outer validated identity",
                        "thesis": "The nested descriptor must not override this target.",
                        "first_seen_at": "2026-07-01T00:00:00Z",
                        "last_seen_at": "2026-07-08T00:00:00Z",
                        "thread": {
                            "stable_slug": "model-invented-nested-slug",
                            "canonical_thread_id": "ct_0123456789abcdef01234567",
                            "title_ru": "Подмена",
                            "title_en": "Nested override",
                            "thesis": "This descriptor must never reach persistence.",
                        },
                    },
                    "source_thread_ids": unrelated_source_ids,
                },
                run_id="run-merge-binding",
                operation="merge",
                curator="bounded-strong-model",
                curator_version="curator.v1",
                model="strong-model",
                model_version="2026-07",
                reason="Attempt a nested merge target identity override.",
            )

        findings = validate_curator_proposal(
            full, proposal, event_at="2026-07-13T12:00:00Z"
        )
        self.assertIn(
            "merge sources are not the exact current canonical owners of candidate atoms",
            findings,
        )
        self.assertIn(
            "merge source memberships do not exactly match candidate atom evidence",
            findings,
        )
        with self.assertRaisesRegex(
            CuratorContractError, "exact current canonical owners"
        ):
            apply_curator_proposal(
                full, proposal, event_at="2026-07-13T12:00:00Z"
            )

        nested_bypass = copy.deepcopy(proposal)
        nested_bypass["target"]["atom_memberships"] = [
            {"atom_id": atom_id, "raw_thread_id": raw_id, "relation": "supports"}
            for atom_id, raw_id in zip(atom_ids[2:], raw_ids[2:])
        ]
        nested_findings = validate_curator_proposal(
            full, nested_bypass, event_at="2026-07-13T12:00:00Z"
        )
        self.assertIn(
            "merge target atom_memberships must equal normalized candidate memberships",
            nested_findings,
        )

        nested_alias_bypass = copy.deepcopy(proposal)
        nested_alias_bypass["target"]["aliases"] = [
            {"alias_type": "manual", "alias_value": "unbound-nested-alias"}
        ]
        alias_findings = validate_curator_proposal(
            full, nested_alias_bypass, event_at="2026-07-13T12:00:00Z"
        )
        self.assertIn(
            "merge target aliases must equal normalized proposal aliases",
            alias_findings,
        )

        nested_identity_bypass = copy.deepcopy(proposal)
        nested_identity_bypass["target"]["thread"] = {
            "stable_slug": "model-invented-nested-slug",
            "canonical_thread_id": "ct_0123456789abcdef01234567",
        }
        identity_findings = validate_curator_proposal(
            full, nested_identity_bypass, event_at="2026-07-13T12:00:00Z"
        )
        self.assertIn(
            "merge target contains reserved nested fields: thread",
            identity_findings,
        )
        full.close()

    def test_explicit_record_validate_apply_wrappers_keep_raw_state_and_proposal_boundary(self):
        full = sqlite3.connect(":memory:")
        schema_path = Path(__file__).resolve().parents[1] / "src" / "db" / "schema.sql"
        full.executescript(schema_path.read_text(encoding="utf-8"))
        atoms = []
        for index, (slug, model) in enumerate(
            (("fable-prototype", "Fable 5"), ("claude-fable-port", "Claude Fable 5")),
            start=1,
        ):
            atom = record_knowledge_atom(
                full,
                week_label="2026-W28",
                atom_type="engineering_practice",
                claim=f"{model} turns interactive prototypes into maintainable code.",
                summary="The same portable handoff practice appears in a separate fragment.",
                evidence_quote="portable prototype workflow",
                source_post_ids=[700 + index],
                source_urls=[f"https://t.me/source_{index}/{700 + index}"],
                entities=["Fable", "Anthropic"],
                models=[model],
                practices=["portable prototype workflow"],
                confidence=0.8,
                practical_utility_score=0.8,
                first_seen_at="2026-07-01T00:00:00Z",
                last_seen_at="2026-07-08T00:00:00Z",
            )
            thread = upsert_idea_thread(
                full,
                slug=slug,
                title=slug.replace("-", " ").title(),
                summary="Mutable raw compatibility cluster.",
                status="active",
                first_seen_at="2026-07-01T00:00:00Z",
                last_seen_at="2026-07-08T00:00:00Z",
                momentum_7d=0.5,
                momentum_30d=0.5,
                momentum_90d=0.5,
                atom_count=1,
                source_channels=[f"source_{index}"],
                key_entities=["Fable", "Anthropic"],
                current_claims=[atom["claim"]],
            )
            link_idea_thread_atom(
                full, thread_id=thread["id"], atom_id=atom["id"]
            )
            atoms.append(atom)
        candidate = next(
            item
            for item in generate_grouping_candidates(full, run_id="run-integration")
            if item["kind"] == "grouping_review"
        )
        audit_proposal = build_curator_proposal(
            candidate,
            {},
            run_id="run-integration",
            operation="keep_separate",
            curator="bounded-strong-model",
            curator_version="curator.v1",
            model="strong-model",
            model_version="2026-07",
            reason="The shared practice was reviewed but remains two distinct lifecycle owners.",
        )
        self.assertEqual(
            validate_curator_proposal(
                full, audit_proposal, event_at="2026-07-13T10:00:00Z"
            ),
            (),
        )
        audit_record = record_curator_proposal(
            full, audit_proposal, proposed_at="2026-07-13T10:00:00Z"
        )
        self.assertEqual(audit_record["operation"], "keep_separate")
        self.assertEqual(fetch_canonical_threads(full), [])
        proposal = build_curator_proposal(
            candidate,
            {
                "thread": {
                    "title_ru": "Перенос прототипа в поддерживаемый код",
                    "title_en": "Prototype-to-maintainable-code handoff",
                    "thesis": "Portable prototypes become evidence-backed engineering inputs.",
                    "status": "active",
                    "first_seen_at": "2026-07-01T00:00:00Z",
                    "last_seen_at": "2026-07-08T00:00:00Z",
                    "evidence_maturity": "multi_channel",
                }
            },
            run_id="run-integration",
            operation="create",
            curator="bounded-strong-model",
            curator_version="curator.v1",
            model="strong-model",
            model_version="2026-07",
            reason="Two raw fragments share independently stored workflow evidence.",
        )
        raw_before = {
            "threads": full.execute(
                "SELECT id, slug, title, status FROM idea_threads ORDER BY id"
            ).fetchall(),
            "memberships": full.execute(
                "SELECT thread_id, atom_id, relation FROM idea_thread_atoms ORDER BY thread_id, atom_id"
            ).fetchall(),
        }

        findings = validate_curator_proposal(
            full, proposal, event_at="2026-07-13T12:00:00Z"
        )
        self.assertEqual(findings, ())
        recorded = record_curator_proposal(
            full, proposal, proposed_at="2026-07-13T11:00:00Z"
        )
        self.assertEqual(recorded["decision_status"], "proposed")
        self.assertEqual(fetch_canonical_threads(full), [])

        applied = apply_curator_proposal(
            full, proposal, event_at="2026-07-13T12:00:00Z"
        )

        self.assertEqual(len(applied["canonical_threads"]), 1)
        canonical = applied["canonical_threads"][0]
        self.assertEqual(canonical["stable_slug"], candidate["suggested_identity"]["stable_slug"])
        self.assertEqual(canonical["atom_ids"], sorted(atom["id"] for atom in atoms))
        resolver = StoredCanonicalThreadResolver(
            full, as_of="2026-07-14T00:00:00Z"
        )
        resolution = resolver.resolve(
            {
                "slug": "fable-prototype",
                "atom_ids": sorted(atom["id"] for atom in atoms),
            }
        )
        self.assertEqual(
            resolution.canonical_thread_ref,
            f"canonical_thread:{canonical['stable_slug']}",
        )
        self.assertEqual(
            raw_before,
            {
                "threads": full.execute(
                    "SELECT id, slug, title, status FROM idea_threads ORDER BY id"
                ).fetchall(),
                "memberships": full.execute(
                    "SELECT thread_id, atom_id, relation FROM idea_thread_atoms ORDER BY thread_id, atom_id"
                ).fetchall(),
            },
        )
        full.close()

    def test_apply_rechecks_raw_evidence_inside_atomic_lifecycle_transaction(self):
        full = sqlite3.connect(":memory:")
        schema_path = Path(__file__).resolve().parents[1] / "src" / "db" / "schema.sql"
        full.executescript(schema_path.read_text(encoding="utf-8"))
        for index, slug in enumerate(
            ("fable-atomic-one", "fable-atomic-two"), start=1
        ):
            atom = record_knowledge_atom(
                full,
                week_label="2026-W28",
                atom_type="engineering_practice",
                claim=f"Fragment {index} preserves a portable prototype workflow.",
                summary="Stored non-entity practice evidence supports grouping.",
                evidence_quote="portable prototype workflow",
                source_post_ids=[800 + index],
                source_urls=[f"https://t.me/atomic_{index}/{800 + index}"],
                entities=["Fable"],
                models=[f"Fable {index}"],
                practices=["portable prototype workflow"],
                confidence=0.8,
                practical_utility_score=0.8,
                first_seen_at="2026-07-01T00:00:00Z",
                last_seen_at="2026-07-08T00:00:00Z",
            )
            thread = upsert_idea_thread(
                full,
                slug=slug,
                title=slug.replace("-", " ").title(),
                summary="Mutable raw compatibility cluster.",
                status="active",
                first_seen_at="2026-07-01T00:00:00Z",
                last_seen_at="2026-07-08T00:00:00Z",
                momentum_7d=0.5,
                momentum_30d=0.5,
                momentum_90d=0.5,
                atom_count=1,
                source_channels=[f"atomic_{index}"],
                key_entities=["Fable"],
                current_claims=[atom["claim"]],
            )
            link_idea_thread_atom(full, thread_id=thread["id"], atom_id=atom["id"])

        candidate = next(
            item
            for item in generate_grouping_candidates(full, run_id="run-atomic-gap")
            if item["kind"] == "grouping_review"
        )
        proposal = build_curator_proposal(
            candidate,
            {
                "thread": {
                    "title_ru": "Атомарная проверка переноса прототипа",
                    "title_en": "Atomic prototype handoff validation",
                    "thesis": "Only a fresh stored evidence snapshot may create this thread.",
                    "status": "active",
                    "first_seen_at": "2026-07-01T00:00:00Z",
                    "last_seen_at": "2026-07-08T00:00:00Z",
                }
            },
            run_id="run-atomic-gap",
            operation="create",
            curator="bounded-strong-model",
            curator_version="curator.v1",
            model="strong-model",
            model_version="2026-07",
            reason="The proposal was valid at its original stored snapshot.",
        )
        self.assertEqual(
            validate_curator_proposal(
                full, proposal, event_at="2026-07-13T12:00:00Z"
            ),
            (),
        )
        candidate_atom_ids = tuple(
            int(item["atom_id"]) for item in candidate["atom_evidence"]
        )

        from db.canonical_idea_threads import apply_canonical_lifecycle

        raw_at_atomic_entry: dict[str, object] = {}

        def mutate_in_former_validation_gap(connection, **kwargs):
            connection.execute(
                """
                UPDATE knowledge_atoms
                SET claim = 'Fable', summary = 'Fable', evidence_quote = 'Fable',
                    practices_json = '[]',
                    source_urls_json = '["https://t.me/changed/source"]'
                WHERE id IN (?, ?)
                """,
                candidate_atom_ids,
            )
            connection.commit()
            raw_at_atomic_entry["atoms"] = connection.execute(
                """
                SELECT id, claim, practices_json, source_urls_json
                FROM knowledge_atoms
                WHERE id IN (?, ?)
                ORDER BY id
                """,
                candidate_atom_ids,
            ).fetchall()
            raw_at_atomic_entry["memberships"] = connection.execute(
                """
                SELECT thread_id, atom_id, relation
                FROM idea_thread_atoms
                ORDER BY thread_id, atom_id
                """
            ).fetchall()
            return apply_canonical_lifecycle(connection, **kwargs)

        with patch(
            "db.canonical_idea_threads.apply_canonical_lifecycle",
            side_effect=mutate_in_former_validation_gap,
        ):
            with self.assertRaisesRegex(
                CuratorContractError, "candidate snapshot fingerprint is stale"
            ):
                apply_curator_proposal(
                    full, proposal, event_at="2026-07-13T12:00:00Z"
                )

        self.assertEqual(fetch_canonical_threads(full), [])
        self.assertEqual(
            raw_at_atomic_entry,
            {
                "atoms": full.execute(
                    """
                    SELECT id, claim, practices_json, source_urls_json
                    FROM knowledge_atoms
                    WHERE id IN (?, ?)
                    ORDER BY id
                    """,
                    candidate_atom_ids,
                ).fetchall(),
                "memberships": full.execute(
                    """
                    SELECT thread_id, atom_id, relation
                    FROM idea_thread_atoms
                    ORDER BY thread_id, atom_id
                    """
                ).fetchall(),
            },
        )
        decision = full.execute(
            """
            SELECT decision_status, validation_status, validation_errors_json
            FROM canonical_idea_thread_curator_decisions
            WHERE run_id = 'run-atomic-gap'
            """
        ).fetchone()
        self.assertIsNotNone(decision)
        self.assertEqual(decision[:2], ("rejected", "rejected"))
        self.assertIn("candidate snapshot fingerprint is stale", decision[2])
        full.close()


if __name__ == "__main__":
    unittest.main()
