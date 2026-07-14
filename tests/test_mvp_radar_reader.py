import copy
import json
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from output.ai_report_contract import RADAR_INTELLIGENCE_CONTRACT_VERSION
from output.mvp_radar_reader import (
    MVP_RADAR_READER_SCHEMA_VERSION,
    MvpRadarReaderError,
    adapt_legacy_mvp_radar_payload,
    build_mvp_radar_reader_projection,
    load_bound_mvp_radar_reader,
    load_unbound_mvp_radar_reader,
    missing_mvp_radar_projection,
    validate_mvp_radar_reader_projection,
)
from output.reporting_period import resolve_reporting_period
from output.weekly_run_manifest import (
    build_initial_manifest,
    build_radar_run_binding,
    sha256_file,
    start_stage,
    succeed_stage,
    write_radar_run_binding,
)
from output.weekly_intelligence_brief import _normalize_mvp_radar


RUN_AT = datetime(2026, 7, 13, 7, 2, 52, tzinfo=timezone.utc)
TITLE = "Bound operator evidence scanner"
RADAR_RUN_ID = "radar-reader-contract-run"


@dataclass(frozen=True)
class _BoundRadar:
    run_dir: Path
    manifest: dict[str, Any]
    binding: dict[str, Any]
    payload: dict[str, Any]
    seeds: list[dict[str, Any]]
    raw_path: Path
    seed_path: Path
    binding_path: Path


class TestMvpRadarReader(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.period = resolve_reporting_period(RUN_AT)
        self.case_number = 0

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _external(
        self,
        source_type: str,
        index: int,
        *,
        context_only: bool = False,
        negative: bool = False,
    ) -> dict[str, Any]:
        return {
            "matched_candidate_title": TITLE,
            "source_type": source_type,
            "source_name": f"{source_type} source",
            "source_id": f"source:{source_type}:{index}",
            "source_url": f"https://evidence.example/{source_type}/{index}",
            "source_title": f"Evidence {index}",
            "source_snippet": "A candidate-specific pain and workaround observation.",
            "source_fingerprint": f"evidence:{source_type}:{index}",
            "evidence_kind": "negative_signal" if negative else "repeated_complaint",
            "captured_at": "2026-07-10T10:00:00Z",
            "query": f'"{TITLE}" problem',
            "match_basis": "same_candidate_icp_pain_workaround",
            "decision_grade": True,
            "supports_gate": True,
            "negative_signal": negative,
            "context_only": context_only,
            "radar_role": (
                "context_only" if context_only else "matched_external_evidence"
            ),
            "build_ready_evidence": True,
        }

    def _seeds(self, *, include_kir: bool) -> list[dict[str, Any]]:
        base = {
            **self.period.to_dict(),
            "contract_version": RADAR_INTELLIGENCE_CONTRACT_VERSION,
        }
        if not include_kir:
            return [{**base, "source_kind": "manual", "title": TITLE}]
        return [
            {
                **base,
                "source_kind": "knowledge_thread",
                "title": TITLE,
                "mvp_shape": TITLE,
                "captured_at": "2026-07-10T00:00:00Z",
                "upstream_id": "seed:knowledge-thread:reader-contract",
                "knowledge_thread_slug": "operator-evidence-scanner",
                "knowledge_thread_title": "Operator evidence scanner",
                "knowledge_thread_status": "active",
                "source_atom_ids": ["atom:101", "atom:102"],
                "source_urls": ["https://knowledge.example/thread/reader-contract"],
                "radar_role": "candidate_evidence",
                "context_only": False,
                "build_ready_evidence": False,
            }
        ]

    def _payload(
        self,
        *,
        dossier_status: str = "investigate",
        recommendation: str = "revisit_with_evidence_gap",
        external: list[dict[str, Any]] | None = None,
        include_kir: bool = True,
        include_context: bool = True,
        no_candidate: bool = False,
    ) -> dict[str, Any]:
        if no_candidate:
            return {
                "schema_version": "mvp_of_week.v1",
                "result": {"run_id": RADAR_RUN_ID, "status": "no_candidate"},
                "selected": None,
            }

        evidence = copy.deepcopy(external or [])
        gate_proof = [
            item
            for item in evidence
            if item["supports_gate"]
            and item["decision_grade"]
            and not item["context_only"]
            and not item["negative_signal"]
            and item["source_type"] not in {"market_context", "telegram", "x"}
        ]
        source_types = sorted({item["source_type"] for item in gate_proof})
        source_mix: dict[str, Any] = {
            "selected_external_evidence_count": len(gate_proof),
            "selected_external_source_types": source_types,
            "decision_grade_external": len(gate_proof) >= 2 and len(source_types) >= 2,
            "selected_telegram_seed_evidence_count": 1 if include_kir else 0,
            "kir_required": include_kir,
            "kir_gate_status": "passed" if include_kir else "not_required",
            "kir_has_fresh_thread": include_kir,
            "kir_source_atom_count": 2 if include_kir else 0,
            "kir_source_url_count": 1 if include_kir else 0,
        }
        if include_kir:
            source_mix.update(
                {
                    "kir_source_kind": "knowledge_thread",
                    "kir_thread_slug": "operator-evidence-scanner",
                    "kir_thread_title": "Operator evidence scanner",
                    "kir_thread_status": "active",
                }
            )

        query = f'"{TITLE}" problem'
        missing = [] if len(gate_proof) >= 2 else ["Need independent external demand."]
        categories = (
            {}
            if not missing
            else {
                "external_corroboration": {
                    "evidence_kind": "search_demand",
                    "missing_evidence": missing,
                    "next_intent": "search_demand",
                    "next_query": query,
                }
            }
        )
        validation_queries = {
            "schema_version": "radar_validation_evidence.v1",
            "next_query": {"query": query, "intent": "search_demand"},
        }
        decision_change = {
            "current_gate": dossier_status,
            "matched_external_evidence_count": len(gate_proof),
            "matched_external_source_types": source_types,
            "next_query": query,
            "next_intent": "search_demand",
            "missing_category": "external_corroboration",
            "next_validation_action": "Run the bounded candidate-specific query.",
            "required_gate_change": "Add two independent candidate-specific source types.",
            "market_context_role": "context_only_not_proof",
            "context_only_results_rule": "context-only records do not satisfy gates",
        }
        selected = {
            "candidate_id": "candidate:bound-operator-evidence-scanner",
            "title": TITLE,
            "dossier_status": dossier_status,
            "recommendation": recommendation,
            "confidence": "medium",
            "score": 63,
            "decision_reason": "The bounded producer gate determines this status.",
            "source_mix": copy.deepcopy(source_mix),
            "matched_external_evidence": copy.deepcopy(evidence),
            "missing_evidence": list(missing),
            "missing_evidence_by_category": copy.deepcopy(categories),
            "validation_queries": copy.deepcopy(validation_queries),
            "decision_change_action": copy.deepcopy(decision_change),
            "next_experiment": ["Run one scoped operator validation interview."],
            "kill_criteria": ["Stop if no repeated candidate-specific pain is found."],
        }
        result = {
            "run_id": RADAR_RUN_ID,
            "status": "selected",
            "selected_title": TITLE,
            "dossier_status": dossier_status,
            "recommendation": recommendation,
            "score": 63,
            "selected_source_mix": copy.deepcopy(source_mix),
            "matched_external_evidence": copy.deepcopy(evidence),
            "missing_evidence_by_category": copy.deepcopy(categories),
            "decision_change_action": copy.deepcopy(decision_change),
        }
        payload: dict[str, Any] = {
            "schema_version": "mvp_of_week.v1",
            "result": result,
            "selected": selected,
            "matched_external_evidence": copy.deepcopy(evidence),
            "missing_evidence_by_category": copy.deepcopy(categories),
            "validation_queries": copy.deepcopy(validation_queries),
            "decision_change_action": copy.deepcopy(decision_change),
        }
        if include_context:
            payload["decision_context"] = {
                "market_context": {
                    "status": "context_only",
                    "summary": "Market framing is useful only as context.",
                    "record_count": 1,
                    "context_only": True,
                    "build_ready_evidence": False,
                    "source_gate_satisfied": False,
                    "records": [
                        {
                            "source_id": "market:1",
                            "source_type": "market_context",
                            "source_title": "Market context",
                            "source_url": "https://context.example/market/1",
                            "reason": "No candidate-specific match.",
                            "context_only": True,
                            "build_ready_evidence": False,
                            "source_gate_satisfied": False,
                        }
                    ],
                },
                "external_research_context": {
                    "status": "context_only",
                    "summary": "Unmatched research remains context.",
                    "record_count": 1,
                    "context_only": True,
                    "build_ready_evidence": False,
                    "source_gate_satisfied": False,
                    "records": [
                        {
                            "source_id": "research:1",
                            "source_type": "serp_unmatched",
                            "source_title": "Adjacent research",
                            "source_url": "https://context.example/research/1",
                            "reason": "Different candidate and ICP.",
                            "context_only": True,
                            "build_ready_evidence": False,
                            "source_gate_satisfied": False,
                        }
                    ],
                },
            }
        return payload

    def _bound(
        self,
        *,
        payload: dict[str, Any] | None = None,
        seeds: list[dict[str, Any]] | None = None,
    ) -> _BoundRadar:
        self.case_number += 1
        run_dir = self.root / f"case-{self.case_number}"
        radar_dir = run_dir / "radar"
        radar_dir.mkdir(parents=True)
        manifest = build_initial_manifest(
            self.period,
            run_id=f"reader-manifest-run-{self.case_number}",
        )
        manifest = start_stage(manifest, "radar", at=RUN_AT)
        resolved_payload = copy.deepcopy(payload or self._payload())
        resolved_seeds = copy.deepcopy(
            seeds if seeds is not None else self._seeds(include_kir=True)
        )
        raw_path = radar_dir / "radar-result.json"
        seed_path = radar_dir / "seeds.json"
        binding_path = radar_dir / "radar-run-binding.json"
        raw_path.write_text(
            json.dumps(resolved_payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        seed_path.write_text(
            json.dumps(resolved_seeds, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        result = resolved_payload["result"]
        status_projection = {
            key: result[key]
            for key in (
                "status",
                "selected_title",
                "dossier_status",
                "recommendation",
                "score",
                "selected_source_mix",
            )
            if key in result
        }
        binding = build_radar_run_binding(
            manifest,
            radar_run_id=RADAR_RUN_ID,
            radar_contract_version=RADAR_INTELLIGENCE_CONTRACT_VERSION,
            radar_schema_version="mvp_of_week.v1",
            seed_export_path="radar/seeds.json",
            radar_json_path="radar/radar-result.json",
            selected_candidate=resolved_payload.get("selected"),
            status_projection=status_projection,
            created_at=RUN_AT,
            path_base=run_dir,
            allowed_roots=(run_dir,),
        )
        write_radar_run_binding(
            binding_path,
            binding,
            manifest=manifest,
            path_base=run_dir,
            allowed_roots=(run_dir,),
        )
        manifest = succeed_stage(
            manifest,
            "radar",
            at=RUN_AT,
            updates={
                "radar_run_id": RADAR_RUN_ID,
                "artifact_path": "radar/radar-result.json",
                "artifact_sha256": sha256_file(raw_path),
                "binding_path": "radar/radar-run-binding.json",
                "binding_sha256": sha256_file(binding_path),
                "seed_export_path": "radar/seeds.json",
                "seed_export_sha256": sha256_file(seed_path),
                "reporting_week": self.period.reporting_week,
                "artifact_refs": {
                    "binding_path": "radar/radar-run-binding.json"
                },
            },
        )
        return _BoundRadar(
            run_dir=run_dir,
            manifest=manifest,
            binding=binding,
            payload=resolved_payload,
            seeds=resolved_seeds,
            raw_path=raw_path,
            seed_path=seed_path,
            binding_path=binding_path,
        )

    def _load(self, bundle: _BoundRadar) -> dict[str, Any]:
        return load_bound_mvp_radar_reader(
            bundle.manifest,
            path_base=bundle.run_dir,
            allowed_roots=(bundle.run_dir,),
        )

    def test_bound_investigate_projects_kir_and_two_context_lanes(self) -> None:
        bundle = self._bound()

        projection = self._load(bundle)

        self.assertEqual(projection["reader_state"], "available")
        self.assertEqual(projection["reader_decision"], "investigate")
        self.assertEqual(projection["selected_candidate"], TITLE)
        self.assertEqual(projection["candidate"]["candidate_id_source"], "producer")
        self.assertEqual(projection["radar_run_id"], RADAR_RUN_ID)
        self.assertEqual(
            projection["manifest_run_id"], bundle.manifest["run_id"]
        )
        self.assertEqual(len(projection["matched_kir_provenance"]), 1)
        self.assertEqual(
            projection["matched_kir_provenance"][0]["source_atom_ids"],
            ["atom:101", "atom:102"],
        )
        self.assertEqual(
            {item["lane"] for item in projection["unmatched_context"]},
            {"market_context", "external_research_context"},
        )
        self.assertTrue(
            all(item["context_only"] for item in projection["unmatched_context"])
        )
        self.assertFalse(
            any(
                item["source_gate_satisfied"]
                for item in projection["unmatched_context"]
            )
        )
        self.assertEqual(projection["matched_external_proof"], [])
        self.assertEqual(
            projection["next_validation_query"]["query"], f'"{TITLE}" problem'
        )
        validate_mvp_radar_reader_projection(
            projection, manifest=bundle.manifest
        )

    def test_focused_experiment_and_build_have_distinct_reader_authority(self) -> None:
        evidence = [self._external("reddit", 1), self._external("serp", 2)]
        cases = (
            ("focused_experiment", "focused_experiment", "investigate"),
            ("build", "build", "build_allowed"),
        )
        for dossier, recommendation, expected in cases:
            with self.subTest(dossier=dossier):
                payload = self._payload(
                    dossier_status=dossier,
                    recommendation=recommendation,
                    external=evidence,
                    include_kir=False,
                    include_context=False,
                )
                bundle = self._bound(
                    payload=payload,
                    seeds=self._seeds(include_kir=False),
                )

                projection = self._load(bundle)

                self.assertEqual(projection["reader_state"], "available")
                self.assertEqual(projection["reader_decision"], expected)
                self.assertEqual(len(projection["matched_external_proof"]), 2)
                self.assertEqual(
                    {item["source_type"] for item in projection["matched_external_proof"]},
                    {"reddit", "serp"},
                )

    def test_successful_no_candidate_is_not_reported_as_missing(self) -> None:
        payload = self._payload(no_candidate=True)
        bundle = self._bound(payload=payload, seeds=[])

        projection = self._load(bundle)

        self.assertEqual(projection["reader_state"], "no_candidate")
        self.assertEqual(projection["candidate_state"], "no_candidate")
        self.assertEqual(projection["snapshot_status"], "complete")
        self.assertFalse(projection["partial"])
        self.assertIsNone(projection["selected_candidate"])
        self.assertEqual(projection["reader_decision"], "unavailable")

    def test_context_x_and_negative_records_never_enter_gate_proof(self) -> None:
        forged = [
            self._external("serp", 1, context_only=True),
            self._external("x", 2),
            self._external("reddit", 3, negative=True),
        ]
        payload = self._payload(external=forged)
        bundle = self._bound(payload=payload)

        projection = self._load(bundle)

        self.assertEqual(projection["reader_state"], "available")
        self.assertEqual(len(projection["matched_external_evidence"]), 3)
        self.assertEqual(projection["matched_external_proof"], [])
        self.assertTrue(
            all(
                item["gate_eligible"] is False
                for item in projection["matched_external_evidence"]
            )
        )
        self.assertFalse(projection["evidence_policy"]["x_can_satisfy_gate"])
        self.assertFalse(
            projection["evidence_policy"]["negative_signal_can_satisfy_gate"]
        )

        unsafe_build = self._payload(
            dossier_status="build",
            recommendation="build",
            external=forged,
        )
        with self.assertRaisesRegex(
            MvpRadarReaderError, "independent external proof"
        ):
            build_mvp_radar_reader_projection(
                bundle.manifest,
                binding={
                    **bundle.binding,
                    "selected_candidate": unsafe_build["selected"],
                    "status_projection": {
                        key: unsafe_build["result"][key]
                        for key in (
                            "status",
                            "selected_title",
                            "dossier_status",
                            "recommendation",
                            "score",
                            "selected_source_mix",
                        )
                    },
                },
                radar_payload=unsafe_build,
                seed_payload=bundle.seeds,
            )

    def test_projection_parity_mismatches_raise_before_reader_authority(self) -> None:
        bundle = self._bound()
        selected_mismatch = copy.deepcopy(bundle.binding)
        selected_mismatch["selected_candidate"]["title"] = "Another candidate"
        with self.assertRaisesRegex(
            MvpRadarReaderError, "selected_candidate differs"
        ):
            build_mvp_radar_reader_projection(
                bundle.manifest,
                binding=selected_mismatch,
                radar_payload=bundle.payload,
                seed_payload=bundle.seeds,
            )

        result_mismatch = copy.deepcopy(bundle.payload)
        result_mismatch["result"]["selected_source_mix"] = {
            "decision_grade_external": True
        }
        with self.assertRaisesRegex(MvpRadarReaderError, "status projection differs"):
            build_mvp_radar_reader_projection(
                bundle.manifest,
                binding=bundle.binding,
                radar_payload=result_mismatch,
                seed_payload=bundle.seeds,
            )

    def test_loader_fails_closed_on_raw_or_binding_checksum_change(self) -> None:
        raw_bundle = self._bound()
        raw_bundle.raw_path.write_text("{}", encoding="utf-8")
        raw_projection = self._load(raw_bundle)
        self.assertEqual(raw_projection["reader_state"], "invalid")
        self.assertTrue(raw_projection["partial"])
        self.assertEqual(raw_projection["reader_decision"], "unavailable")
        self.assertIn("целостности", raw_projection["partial_reasons"][0])

        binding_bundle = self._bound()
        binding_bundle.binding_path.write_text("{}", encoding="utf-8")
        binding_projection = self._load(binding_bundle)
        self.assertEqual(binding_projection["reader_state"], "invalid")
        self.assertEqual(binding_projection["reader_decision"], "unavailable")

    def test_bound_loader_rejects_duplicate_keys_and_float_overflow(self) -> None:
        for poison in ("duplicate", "float-overflow"):
            with self.subTest(poison=poison):
                bundle = self._bound()
                raw = json.dumps(
                    bundle.payload,
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
                if poison == "duplicate":
                    raw = b'{"schema_version":"mvp_of_week.v1",' + raw[1:]
                else:
                    raw = raw[:-1] + b',"ignored_overflow":1e999}'
                bundle.raw_path.write_bytes(raw)

                binding = copy.deepcopy(bundle.binding)
                binding["radar_json_ref"]["sha256"] = sha256_file(
                    bundle.raw_path
                )
                bundle.binding_path.write_text(
                    json.dumps(binding, ensure_ascii=False, sort_keys=True),
                    encoding="utf-8",
                )
                manifest = copy.deepcopy(bundle.manifest)
                manifest["stages"]["radar"]["artifact_sha256"] = sha256_file(
                    bundle.raw_path
                )
                manifest["stages"]["radar"]["binding_sha256"] = sha256_file(
                    bundle.binding_path
                )

                projection = load_bound_mvp_radar_reader(
                    manifest,
                    path_base=bundle.run_dir,
                    allowed_roots=(bundle.run_dir,),
                )

                self.assertEqual(projection["reader_state"], "invalid")
                self.assertEqual(projection["reader_decision"], "unavailable")

    def test_wrong_radar_run_or_reporting_week_is_rejected(self) -> None:
        bundle = self._bound()
        wrong_run = copy.deepcopy(bundle.payload)
        wrong_run["result"]["run_id"] = "different-radar-run"
        with self.assertRaisesRegex(MvpRadarReaderError, "run_id does not match"):
            build_mvp_radar_reader_projection(
                bundle.manifest,
                binding=bundle.binding,
                radar_payload=wrong_run,
                seed_payload=bundle.seeds,
            )

        wrong_week = copy.deepcopy(bundle.binding)
        wrong_week["reporting_week"] = "2026-W27"
        wrong_week["week_label"] = "2026-W27"
        with self.assertRaisesRegex(
            MvpRadarReaderError, "reporting period|reporting_week"
        ):
            build_mvp_radar_reader_projection(
                bundle.manifest,
                binding=wrong_week,
                radar_payload=bundle.payload,
                seed_payload=bundle.seeds,
            )

        wrong_seed_week = copy.deepcopy(bundle.seeds)
        wrong_seed_week[0]["reporting_week"] = "2026-W27"
        with self.assertRaisesRegex(MvpRadarReaderError, "reporting_week mismatch"):
            build_mvp_radar_reader_projection(
                bundle.manifest,
                binding=bundle.binding,
                radar_payload=bundle.payload,
                seed_payload=wrong_seed_week,
            )

    def test_unbound_legacy_is_diagnostic_and_wrong_week_is_invalid(self) -> None:
        legacy_payload = {
            "reporting_week": self.period.reporting_week,
            "result": {
                "run_id": "legacy-radar-run",
                "status": "selected",
                "selected_title": "Legacy candidate",
                "dossier_status": "investigate",
                "recommendation": "revisit_with_evidence_gap",
                "score": 42,
            },
            "selected": {
                "title": "Legacy candidate",
                "missing_evidence": ["Need a same-run binding."],
                "kill_criteria": ["Stop on no evidence."],
            },
        }

        projection = adapt_legacy_mvp_radar_payload(
            legacy_payload,
            source_path="legacy/mvp-weekly-2026-W28.json",
            expected_week=self.period.reporting_week,
        )

        self.assertEqual(projection["reader_state"], "unbound_legacy")
        self.assertEqual(projection["selected_candidate"], "Legacy candidate")
        self.assertEqual(projection["reader_decision"], "unavailable")
        self.assertTrue(projection["partial"])
        self.assertEqual(projection["matched_external_proof"], [])
        self.assertFalse(
            projection["evidence_policy"]["unbound_legacy_can_authorize"]
        )

        forged_reader = adapt_legacy_mvp_radar_payload(
            {
                **projection,
                "schema_version": MVP_RADAR_READER_SCHEMA_VERSION,
                "reader_state": "available",
                "reader_decision": "build_allowed",
            },
            source_path="legacy/forged-reader.json",
            expected_week=self.period.reporting_week,
        )
        self.assertEqual(forged_reader["reader_state"], "unbound_legacy")
        self.assertEqual(forged_reader["reader_decision"], "unavailable")
        self.assertEqual(forged_reader["matched_external_proof"], [])

        wrong_week = adapt_legacy_mvp_radar_payload(
            {**legacy_payload, "reporting_week": "2026-W27"},
            source_path="legacy/mvp-weekly-2026-W27.json",
            expected_week=self.period.reporting_week,
        )
        self.assertEqual(wrong_week["reader_state"], "invalid")
        self.assertIsNone(wrong_week["candidate"])
        self.assertEqual(wrong_week["reader_decision"], "unavailable")
        self.assertIn("2026-W27", wrong_week["partial_reasons"][0])

    def test_disabled_and_missing_states_are_explicit(self) -> None:
        disabled = build_initial_manifest(
            self.period,
            run_id="reader-disabled-run",
            radar_enabled=False,
        )
        disabled_projection = load_bound_mvp_radar_reader(
            disabled,
            path_base=self.root,
            allowed_roots=(self.root,),
        )
        self.assertEqual(disabled_projection["reader_state"], "disabled")
        self.assertEqual(
            disabled_projection["candidate_state"], "intentionally_disabled"
        )
        self.assertFalse(disabled_projection["partial"])

        pending = build_initial_manifest(
            self.period,
            run_id="reader-pending-run",
        )
        missing_projection = load_bound_mvp_radar_reader(
            pending,
            path_base=self.root,
            allowed_roots=(self.root,),
        )
        self.assertEqual(missing_projection["reader_state"], "missing")
        self.assertTrue(missing_projection["partial"])
        self.assertEqual(missing_projection["reader_decision"], "unavailable")

        legacy_missing = missing_mvp_radar_projection(
            self.period.reporting_week,
            source_path="missing/radar.json",
        )
        self.assertEqual(legacy_missing["reader_state"], "missing")
        self.assertEqual(
            legacy_missing["artifact_ref"]["radar_json_path"],
            "missing/radar.json",
        )

    def test_strict_brief_consumer_requires_exact_current_manifest_identity(self) -> None:
        payload = self._payload(
            dossier_status="build",
            recommendation="build",
            external=[self._external("reddit", 1), self._external("serp", 2)],
            include_kir=False,
            include_context=False,
        )
        bundle = self._bound(payload=payload, seeds=self._seeds(include_kir=False))
        projection = self._load(bundle)
        expected = {**self.period.to_dict(), "run_id": bundle.manifest["run_id"]}

        bound = _normalize_mvp_radar(
            projection,
            expected_identity=expected,
            run_manifest=bundle.manifest,
        )
        unbound = _normalize_mvp_radar(
            projection,
            expected_identity=expected,
            run_manifest=None,
        )
        replayed = _normalize_mvp_radar(
            projection,
            expected_identity={**expected, "reporting_week": "2026-W27"},
            run_manifest=bundle.manifest,
        )

        self.assertEqual(bound["reader_state"], "available")
        self.assertEqual(bound["reader_decision"], "build_allowed")
        for rejected in (unbound, replayed):
            self.assertEqual(rejected["reader_state"], "invalid")
            self.assertEqual(rejected["reader_decision"], "unavailable")
            self.assertIsNone(rejected["candidate"])

    def test_kir_freshness_matches_producer_any_fresh_semantics(self) -> None:
        evidence = [self._external("reddit", 1), self._external("serp", 2)]
        payload = self._payload(
            dossier_status="build",
            recommendation="build",
            external=evidence,
            include_kir=True,
            include_context=False,
        )
        stale = self._seeds(include_kir=True)[0]
        stale["knowledge_thread_status"] = "stale"
        fresh = copy.deepcopy(stale)
        fresh.update(
            {
                "upstream_id": "seed:knowledge-thread:reader-contract-fresh",
                "knowledge_thread_slug": "operator-evidence-scanner-fresh",
                "knowledge_thread_title": "Operator evidence scanner fresh",
                "knowledge_thread_status": "active",
                "source_atom_ids": ["atom:103"],
                "source_urls": ["https://knowledge.example/thread/fresh"],
            }
        )
        source_mix = payload["selected"]["source_mix"]
        source_mix.update(
            {
                "selected_telegram_seed_evidence_count": 2,
                "kir_has_fresh_thread": True,
                "kir_source_atom_count": 3,
                "kir_source_url_count": 2,
                "kir_thread_status": "stale",
            }
        )
        payload["result"]["selected_source_mix"] = copy.deepcopy(source_mix)
        bundle = self._bound(payload=payload, seeds=[stale, fresh])

        projection = self._load(bundle)

        self.assertEqual(projection["reader_decision"], "build_allowed")
        self.assertEqual(len(projection["matched_kir_provenance"]), 2)

        stale_payload = self._payload(
            external=evidence,
            include_kir=True,
            include_context=False,
        )
        stale_mix = stale_payload["selected"]["source_mix"]
        stale_mix.update(
            {
                "selected_telegram_seed_evidence_count": 2,
                "kir_gate_status": "stale_kir_thread",
                "kir_has_fresh_thread": False,
                "kir_source_atom_count": 3,
                "kir_source_url_count": 2,
                "kir_thread_status": "stale",
            }
        )
        stale_payload["result"]["selected_source_mix"] = copy.deepcopy(stale_mix)
        both_stale = copy.deepcopy(fresh)
        both_stale["knowledge_thread_status"] = "stale"
        stale_bundle = self._bound(payload=stale_payload, seeds=[stale, both_stale])

        stale_projection = self._load(stale_bundle)

        self.assertEqual(stale_projection["reader_decision"], "investigate")
        self.assertIn("KIR Knowledge Thread", stale_projection["change_condition"])
        self.assertNotIn("два независимых", stale_projection["change_condition"])

    def test_validator_rejects_state_fiction_and_invalid_gate_enums(self) -> None:
        no_candidate_bundle = self._bound(
            payload=self._payload(no_candidate=True),
            seeds=[],
        )
        no_candidate = self._load(no_candidate_bundle)
        for field, value in (
            ("dossier_status", "build"),
            ("recommendation", "build"),
            ("score", 99),
            ("source_mix", {"decision_grade_external": True}),
        ):
            with self.subTest(state="no_candidate", field=field):
                forged = copy.deepcopy(no_candidate)
                forged[field] = value
                with self.assertRaises(MvpRadarReaderError):
                    validate_mvp_radar_reader_projection(
                        forged,
                        manifest=no_candidate_bundle.manifest,
                    )

        missing = missing_mvp_radar_projection(self.period.reporting_week)
        for field, value in (
            ("partial", False),
            ("snapshot_status", "complete"),
            ("dossier_status", "build"),
            ("recommendation", "build"),
            ("source_mix", {"decision_grade_external": True}),
        ):
            with self.subTest(state="missing", field=field):
                forged = copy.deepcopy(missing)
                forged[field] = value
                if field == "partial":
                    forged["partial_reasons"] = []
                with self.assertRaises(MvpRadarReaderError):
                    validate_mvp_radar_reader_projection(forged)

        bundle = self._bound()
        available = self._load(bundle)
        with self.assertRaisesRegex(MvpRadarReaderError, "current run manifest"):
            validate_mvp_radar_reader_projection(available)
        for field, value in (
            ("bound_candidate_seed_count", -1),
            ("kir_gate_status", "banana"),
        ):
            with self.subTest(state="available", field=field):
                forged = copy.deepcopy(available)
                if field == "kir_gate_status":
                    forged["source_mix"][field] = value
                else:
                    forged[field] = value
                    forged["source_mix"]["selected_telegram_seed_evidence_count"] = value
                with self.assertRaises(MvpRadarReaderError):
                    validate_mvp_radar_reader_projection(
                        forged,
                        manifest=bundle.manifest,
                    )

        malformed_manifest = copy.deepcopy(bundle.manifest)
        malformed_manifest["stages"]["knowledge_refresh"]["status"] = []
        with self.assertRaises(MvpRadarReaderError):
            validate_mvp_radar_reader_projection(
                available,
                manifest=malformed_manifest,
            )

        running_manifest = start_stage(
            build_initial_manifest(
                self.period,
                run_id=bundle.manifest["run_id"],
            ),
            "radar",
            at=RUN_AT,
        )
        with self.assertRaisesRegex(MvpRadarReaderError, "succeeded manifest stage"):
            validate_mvp_radar_reader_projection(
                available,
                manifest=running_manifest,
            )

    def test_loader_rejects_nonfinite_json_and_malformed_manifest_without_raising(self) -> None:
        bundle = self._bound()
        poisoned = copy.deepcopy(bundle.payload)
        poisoned["ignored_poison"] = float("nan")
        bundle.raw_path.write_text(
            json.dumps(poisoned, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        binding = copy.deepcopy(bundle.binding)
        binding["radar_json_ref"]["sha256"] = sha256_file(bundle.raw_path)
        bundle.binding_path.write_text(
            json.dumps(binding, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        manifest = copy.deepcopy(bundle.manifest)
        manifest["stages"]["radar"]["artifact_sha256"] = sha256_file(bundle.raw_path)
        manifest["stages"]["radar"]["binding_sha256"] = sha256_file(
            bundle.binding_path
        )

        projection = load_bound_mvp_radar_reader(
            manifest,
            path_base=bundle.run_dir,
            allowed_roots=(bundle.run_dir,),
        )

        self.assertEqual(projection["reader_state"], "invalid")
        self.assertEqual(projection["reader_decision"], "unavailable")

        malformed_manifests = (
            {"run_id": "bad\nid", "reporting_week": "2026-W28"},
            {
                "run_id": "valid-run",
                "reporting_week": "2026-W28\n",
                "analysis_period_start": "2026-07-06T00:00:00Z",
            },
            {"run_id": "x" * 5_000, "reporting_week": "2026-W28"},
        )
        for malformed in malformed_manifests:
            with self.subTest(manifest=repr(malformed)[:80]):
                result = load_bound_mvp_radar_reader(
                    malformed,
                    path_base=self.root,
                    allowed_roots=(self.root,),
                )
                self.assertEqual(result["reader_state"], "invalid")
                self.assertEqual(result["reader_decision"], "unavailable")

    def test_unbound_loader_fails_closed_on_hostile_json_shapes(self) -> None:
        cases = {
            "invalid-utf8.json": b"\xff\xfe",
            "deep.json": ("[" * 1_500 + "0" + "]" * 1_500).encode(),
            "huge-int.json": ("{\"value\":" + "9" * 5_000 + "}").encode(),
            "oversized.json": b" " * 4_000_001,
        }
        for filename, content in cases.items():
            with self.subTest(filename=filename):
                path = self.root / filename
                path.write_bytes(content)
                projection = load_unbound_mvp_radar_reader(
                    path,
                    expected_week=self.period.reporting_week,
                )
                self.assertEqual(projection["reader_state"], "invalid")
                self.assertEqual(projection["reader_decision"], "unavailable")

    def test_projected_context_rule_is_fixed_and_cannot_claim_gate_authority(self) -> None:
        payload = self._payload()
        unsafe = "Context is not merely proof; it guarantees build."
        payload["decision_change_action"]["context_only_results_rule"] = unsafe
        payload["result"]["decision_change_action"][
            "context_only_results_rule"
        ] = unsafe
        payload["selected"]["decision_change_action"][
            "context_only_results_rule"
        ] = unsafe
        bundle = self._bound(payload=payload)

        projection = self._load(bundle)
        rule = projection["decision_change_action"]["context_only_results_rule"]

        self.assertEqual(projection["reader_state"], "available")
        self.assertNotIn("guarantees build", rule)
        self.assertIn("не удовлетворяют evidence gates", rule)

    def test_builder_is_deterministic_does_not_mutate_and_enforces_bounds(self) -> None:
        bundle = self._bound()
        manifest_before = copy.deepcopy(bundle.manifest)
        binding_before = copy.deepcopy(bundle.binding)
        payload_before = copy.deepcopy(bundle.payload)
        seeds_before = copy.deepcopy(bundle.seeds)

        first = build_mvp_radar_reader_projection(
            bundle.manifest,
            binding=bundle.binding,
            radar_payload=bundle.payload,
            seed_payload=bundle.seeds,
            binding_ref={
                "path": "radar/radar-run-binding.json",
                "sha256": sha256_file(bundle.binding_path),
            },
        )
        second = build_mvp_radar_reader_projection(
            bundle.manifest,
            binding=bundle.binding,
            radar_payload=bundle.payload,
            seed_payload=bundle.seeds,
            binding_ref={
                "path": "radar/radar-run-binding.json",
                "sha256": sha256_file(bundle.binding_path),
            },
        )

        self.assertEqual(first, second)
        self.assertEqual(bundle.manifest, manifest_before)
        self.assertEqual(bundle.binding, binding_before)
        self.assertEqual(bundle.payload, payload_before)
        self.assertEqual(bundle.seeds, seeds_before)
        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)
        )

        oversized_seeds = [copy.deepcopy(bundle.seeds[0]) for _ in range(257)]
        with self.assertRaisesRegex(MvpRadarReaderError, "bounded reader limit"):
            build_mvp_radar_reader_projection(
                bundle.manifest,
                binding=bundle.binding,
                radar_payload=bundle.payload,
                seed_payload=oversized_seeds,
            )

        oversized_evidence = [self._external("serp", index) for index in range(25)]
        oversized_payload = copy.deepcopy(bundle.payload)
        oversized_payload["matched_external_evidence"] = oversized_evidence
        oversized_payload["result"]["matched_external_evidence"] = copy.deepcopy(
            oversized_evidence
        )
        oversized_payload["selected"]["matched_external_evidence"] = copy.deepcopy(
            oversized_evidence
        )
        oversized_binding = copy.deepcopy(bundle.binding)
        oversized_binding["selected_candidate"] = copy.deepcopy(
            oversized_payload["selected"]
        )
        with self.assertRaisesRegex(
            MvpRadarReaderError, "matched external evidence exceeds"
        ):
            build_mvp_radar_reader_projection(
                bundle.manifest,
                binding=oversized_binding,
                radar_payload=oversized_payload,
                seed_payload=bundle.seeds,
            )


if __name__ == "__main__":
    unittest.main()
