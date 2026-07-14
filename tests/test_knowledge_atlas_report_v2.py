from __future__ import annotations

import copy
from contextlib import contextmanager
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import stat
import unittest
from unittest.mock import patch

from output.knowledge_atlas_report_v2 import (
    ATLAS_V2_DIRECTORY,
    ATLAS_V2_HTML_FILENAME,
    ATLAS_V2_HISTORY_SCHEMA_VERSION,
    ATLAS_V2_JSON_FILENAME,
    ATLAS_V2_LEARNING_EVENTS_SCHEMA_VERSION,
    ATLAS_V2_RELATIONS_SCHEMA_VERSION,
    ATLAS_V2_SCHEMA_VERSION,
    ATLAS_V2_SOURCE_CATALOG_FILENAME,
    AUDIT_EXPLORER_HTML_FILENAME,
    AUDIT_EXPLORER_JSON_FILENAME,
    HARD_VISIBLE_WORDS_MAX,
    MAX_JSON_BYTES,
    KnowledgeAtlasV2ArtifactError,
    KnowledgeAtlasV2ValidationError,
    _learning_projection,
    _reaction_for_thread,
    build_knowledge_atlas_v2,
    find_manifest_bound_knowledge_atlas_v2,
    generate_knowledge_atlas_v2_package,
    load_manifest_bound_knowledge_atlas_v2,
    render_knowledge_atlas_v2_html,
    validate_knowledge_atlas_v2,
)
from output.knowledge_audit_explorer import (
    AUDIT_EXPLORER_SCHEMA_VERSION,
    TECHNICAL_NOTICE_RU,
    build_knowledge_audit_explorer,
    render_knowledge_audit_explorer_html,
)
from output.editorial_intelligence import editorial_input_hash
from output.report_package_security import canonical_json_bytes
from output.report_package_security import (
    ReportPackageSecurityError,
    read_bounded_bytes,
)
from output.report_quality import ReaderValueQualityError
from output.reader_value_quality import reader_visible_word_count
from output.reaction_personalization import (
    _reader_item_reason,
    _reader_summary,
    validate_reaction_effect,
)
from output.weekly_run_manifest import load_manifest
from output.weekly_intelligence_brief_v2 import (
    WeeklyIntelligenceBriefV2ArtifactError,
    generate_weekly_intelligence_brief_v2_artifact,
    load_manifest_bound_weekly_intelligence_brief_v2,
)
from tests import test_weekly_intelligence_brief_v2 as _brief_v2_tests
from tests.test_editorial_intelligence import _context


_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "report_v2"
    / "knowledge_atlas_v2_cases.v1.json"
)


def _reporting_period(manifest: dict[str, object]) -> dict[str, str]:
    return {
        key: str(manifest[key])
        for key in (
            "reporting_week",
            "analysis_period_start",
            "analysis_period_end",
        )
    }


def _weeks(reporting_week: str) -> list[str]:
    year_text, week_text = reporting_week.split("-W", maxsplit=1)
    first = datetime.fromisocalendar(int(year_text), int(week_text), 1)
    first -= timedelta(weeks=11)
    return [
        (first + timedelta(weeks=index)).strftime("%G-W%V")
        for index in range(12)
    ]


def _descriptor(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


@contextmanager
def _restored_file(path: Path):
    original = path.read_bytes()
    mode = stat.S_IMODE(path.stat().st_mode)
    try:
        yield original
    finally:
        path.write_bytes(original)
        path.chmod(mode)


class KnowledgeAtlasReportV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        with patch(
            "tests.test_weekly_intelligence_brief_v2._context",
            side_effect=lambda thread_count=3: _context(thread_count=8),
        ):
            _brief_v2_tests.WeeklyIntelligenceBriefV2Tests.setUpClass()
        cls.support = _brief_v2_tests.WeeklyIntelligenceBriefV2Tests
        try:
            cls._prepare_atlas_package()
        except Exception:
            _brief_v2_tests.WeeklyIntelligenceBriefV2Tests.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        _brief_v2_tests.WeeklyIntelligenceBriefV2Tests.tearDownClass()

    @classmethod
    def _prepare_atlas_package(cls) -> None:
        cls.root = cls.support.fixture.root
        cls.manifest_path = Path(cls.support.manifest_path).resolve()
        cls.manifest = load_manifest(
            cls.manifest_path,
            path_base=cls.manifest_path.parent,
            allowed_roots=(cls.manifest_path.parent,),
            check_artifact_existence=True,
        )
        atlas_stage = cls.manifest["stages"]["knowledge_atlas"]
        cls.v1_json_path = (cls.manifest_path.parent / atlas_stage["json_path"]).resolve()
        cls.v1_html_path = (cls.manifest_path.parent / atlas_stage["html_path"]).resolve()
        cls.v1 = json.loads(cls.v1_json_path.read_text(encoding="utf-8"))
        cls._make_persisted_lifecycle_complete()
        cls.manifest = load_manifest(
            cls.manifest_path,
            path_base=cls.manifest_path.parent,
            allowed_roots=(cls.manifest_path.parent,),
            check_artifact_existence=True,
        )
        brief_stage = cls.manifest["stages"]["weekly_brief"]
        cls.v1_brief_path = (
            cls.manifest_path.parent / brief_stage["json_path"]
        ).resolve()
        cls.v1_brief = json.loads(cls.v1_brief_path.read_text(encoding="utf-8"))
        cls.source_contributions = cls._contributions_for(cls.v1)
        cls.historical_observations = cls._history_for(cls.v1)
        thread_ids = [
            str(item["canonical_thread_id"])
            for item in cls.v1["canonical_threads"]
        ]
        cls.valid_relations = [
            {
                **copy.deepcopy(cls.fixture["thread_relations"]["accepted"][0]),
                "source_thread_id": thread_ids[0],
                "target_thread_id": thread_ids[1],
                "evidence_refs": list(
                    cls.source_contributions["contributions"][0]["evidence_refs"]
                ),
            }
        ]
        read_event = copy.deepcopy(cls.fixture["learning_observations"][1])
        cls.learning_events = [
            {
                "stage": "read",
                "canonical_thread_id": thread_ids[6],
                "observed_at": (
                    datetime.fromisoformat(
                        str(cls.manifest["analysis_period_start"]).replace(
                            "Z", "+00:00"
                        )
                    )
                    + timedelta(days=5)
                ).isoformat().replace("+00:00", "Z"),
                "confirmation_kind": read_event["confirmation_kind"],
                "evidence_refs": list(read_event["evidence_refs"][:1]),
            }
        ]
        cls.relation_contract = cls._bound_contract(
            ATLAS_V2_RELATIONS_SCHEMA_VERSION,
            cls.valid_relations,
        )
        cls.history_contract = cls._bound_contract(
            ATLAS_V2_HISTORY_SCHEMA_VERSION,
            cls.historical_observations,
        )
        cls.learning_contract = cls._bound_contract(
            ATLAS_V2_LEARNING_EVENTS_SCHEMA_VERSION,
            cls.learning_events,
        )
        cls.output_root = cls.root / "atlas-v2-dedicated"
        cls.summary = generate_knowledge_atlas_v2_package(
            manifest_path=cls.manifest_path,
            editorial_artifact_path=cls.support.editorial_path,
            editorial_input_package=cls.support.package,
            output_root=cls.output_root,
            allowed_source_roots=(cls.root,),
            validated_relations=cls.relation_contract,
            historical_observations=cls.history_contract,
            learning_events=cls.learning_contract,
            source_contributions=cls.source_contributions,
        )
        cls.sidecar_path = Path(cls.summary.json_path)
        cls.html_path = Path(cls.summary.html_path)
        cls.source_catalog_path = Path(cls.summary.source_catalog_path)
        cls.audit_path = Path(cls.summary.audit_json_path)
        cls.audit_html_path = Path(cls.summary.audit_html_path)
        cls.sidecar = load_manifest_bound_knowledge_atlas_v2(
            cls.sidecar_path,
            expected_manifest_path=cls.manifest_path,
            allowed_source_roots=(cls.root,),
        )
        cls.audit = json.loads(cls.audit_path.read_text(encoding="utf-8"))
        cls._pure_counter = 0

    @classmethod
    def _make_persisted_lifecycle_complete(cls) -> None:
        end = datetime.fromisoformat(
            str(cls.manifest["analysis_period_end"]).replace("Z", "+00:00")
        )
        for index, thread in enumerate(cls.v1["canonical_threads"]):
            first = str(thread.get("first_seen_at") or "")
            if not first:
                first = (end - timedelta(weeks=20 - index)).isoformat().replace(
                    "+00:00", "Z"
                )
                thread["first_seen_at"] = first
            last = str(thread.get("last_seen_at") or "")
            if not last:
                last = (end - timedelta(days=index + 1)).isoformat().replace(
                    "+00:00", "Z"
                )
                thread["last_seen_at"] = last
            thread["updated_at"] = last
            thread["operator_interest"] = 0.0
        v1_bytes = canonical_json_bytes(cls.v1)
        cls.v1_json_path.write_bytes(v1_bytes)
        cls.manifest["stages"]["knowledge_atlas"]["checksums"][
            "json_path"
        ] = hashlib.sha256(v1_bytes).hexdigest()
        cls.manifest_path.write_text(
            json.dumps(cls.manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def _bound_contract(
        cls,
        schema_version: str,
        items: list[dict[str, object]],
        *,
        status: str = "available",
    ) -> dict[str, object]:
        period = _reporting_period(cls.manifest)
        return {
            "schema_version": schema_version,
            "run_id": cls.manifest["run_id"],
            "reporting_period": period,
            "as_of": period["analysis_period_end"],
            "status": status,
            "items": copy.deepcopy(items),
        }

    @classmethod
    def _contributions_for(
        cls,
        v1: dict[str, object],
        *,
        sources: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        fixture_contract = cls.fixture["source_contributions"]
        source_rows = copy.deepcopy(sources or fixture_contract["sources"])
        source_ids = [str(item["source_id"]) for item in source_rows]
        navigation_by_slug = {
            str(item["slug"]): item
            for item in v1["thread_navigation"]["threads"]
        }
        rows: list[dict[str, object]] = []
        for index, thread in enumerate(v1["canonical_threads"]):
            source_id = source_ids[index % len(source_ids)]
            navigation = navigation_by_slug[str(thread["stable_slug"])]
            refs = list(navigation.get("source_urls") or [])[:1]
            if not refs:
                evidence = navigation.get("evidence_items") or []
                refs = list(evidence[0].get("source_urls") or [])[:1] if evidence else []
            if not refs:
                raise AssertionError("rich fixture requires manifest-bound evidence refs")
            source_class = next(
                str(item["source_class"])
                for item in source_rows
                if item["source_id"] == source_id
            )
            rows.append(
                {
                    "source_id": source_id,
                    "canonical_thread_id": str(thread["canonical_thread_id"]),
                    "mention_count": 1,
                    "independent_support_count": (
                        0 if source_class == "vendor_primary" else 1
                    ),
                    "decision_grade_evidence_count": 0,
                    "evidence_refs": refs,
                }
            )
        period = _reporting_period(cls.manifest)
        return {
            "schema_version": "knowledge_atlas_source_contributions.v1",
            "run_id": cls.manifest["run_id"],
            "reporting_period": period,
            "as_of": period["analysis_period_end"],
            "classification_status": "complete",
            "sources": source_rows,
            "contributions": rows,
            "limitation_ru": (
                "Независимость считается только по явно классифицированным "
                "группам; повторные упоминания не создают новое подтверждение."
            ),
        }

    @classmethod
    def _history_for(
        cls,
        v1: dict[str, object],
        *,
        include_missing: bool = False,
    ) -> list[dict[str, object]]:
        weeks = _weeks(str(cls.manifest["reporting_week"]))
        result: list[dict[str, object]] = []
        for thread_index, thread in enumerate(v1["canonical_threads"]):
            for week_index, week in enumerate(weeks):
                momentum: float | None = round((thread_index + week_index) / 10, 2)
                evidence: int | None = 1 + week_index // 4
                if thread_index == 0 and week_index == 5:
                    momentum = 0.0
                    evidence = 0
                if include_missing and thread_index == 0 and week_index == 6:
                    momentum = None
                    evidence = None
                result.append(
                    {
                        "canonical_thread_id": str(thread["canonical_thread_id"]),
                        "week": week,
                        "momentum": momentum,
                        "evidence_count": evidence,
                    }
                )
        return result

    @classmethod
    def _expanded_v1(cls, count: int) -> dict[str, object]:
        value = copy.deepcopy(cls.v1)
        threads = list(value["canonical_threads"])
        navigation = list(value["thread_navigation"]["threads"])
        while len(threads) < count:
            number = len(threads) + 1
            thread = copy.deepcopy(threads[0])
            thread.update(
                canonical_thread_id=f"canonical-{number:02d}",
                canonical_thread_ref=f"canonical_thread:signal-{number:02d}",
                stable_slug=f"signal-{number:02d}",
                title=f"Каноническая тема {number}",
                summary=(
                    f"Уникальный проверяемый тезис канонической темы номер {number}."
                ),
                atom_ids=[9000 + number],
                source_post_ids=[19000 + number],
                source_urls=[f"https://example.org/atlas/thread-{number}"],
                source_refs=[f"https://example.org/atlas/thread-{number}"],
            )
            threads.append(thread)
            nav = copy.deepcopy(navigation[0])
            nav.update(
                id=f"atlas-thread-signal-{number:02d}",
                slug=f"signal-{number:02d}",
                title=f"Canonical thread {number}",
                current_understanding=f"Проверяемое понимание темы номер {number}.",
                change_since_previous_period=(
                    f"Добавлена отдельная запись темы номер {number}."
                ),
                source_urls=[f"https://example.org/atlas/thread-{number}"],
            )
            for evidence in nav.get("evidence_items", []):
                evidence["source_urls"] = [
                    f"https://example.org/atlas/thread-{number}"
                ]
            navigation.append(nav)
        value["canonical_threads"] = threads[:count]
        value["canonical_thread_count"] = count
        value["thread_count"] = count
        value["primary_canonical_thread_ids"] = [
            str(item["canonical_thread_id"]) for item in threads[:count]
        ]
        value["thread_navigation"]["threads"] = navigation[:count]
        value["thread_navigation"]["thread_count"] = count
        value["thread_navigation"]["source_atom_count"] = count
        snapshot = value.get("canonical_thread_snapshot")
        if isinstance(snapshot, dict):
            snapshot.pop("canonical_thread_ids", None)
            snapshot.pop("thread_count", None)
        return value

    @classmethod
    def _audit_for_v1(cls, v1: dict[str, object]) -> dict[str, object]:
        cls._pure_counter += 1
        target = cls.root / f"audit-pure-{cls._pure_counter}"
        sources = {
            "manifest": _descriptor(cls.manifest_path),
            "v1_atlas_html": _descriptor(cls.v1_html_path),
            "v1_atlas_json": _descriptor(cls.v1_json_path),
        }
        return build_knowledge_audit_explorer(
            cls.manifest,
            cls.manifest_path,
            v1,
            cls.v1_html_path,
            cls.v1_json_path,
            {
                "html": str((target / AUDIT_EXPLORER_HTML_FILENAME).resolve()),
                "json": str((target / AUDIT_EXPLORER_JSON_FILENAME).resolve()),
            },
            sources,
        )

    @classmethod
    def _build_pure(
        cls,
        *,
        v1: dict[str, object] | None = None,
        v1_brief: dict[str, object] | None = None,
        editorial_artifact: dict[str, object] | None = None,
        editorial_input_package: dict[str, object] | None = None,
        audit: dict[str, object] | None = None,
        relations: list[dict[str, object]] | None = None,
        history: list[dict[str, object]] | None = None,
        learning: list[dict[str, object]] | None = None,
        contributions: dict[str, object] | None = None,
    ) -> dict[str, object]:
        source = copy.deepcopy(v1 or cls.v1)
        audit_value = audit or cls._audit_for_v1(source)
        cls._pure_counter += 1
        target = cls.root / f"atlas-pure-{cls._pure_counter}"
        return build_knowledge_atlas_v2(
            manifest=cls.manifest,
            manifest_path=cls.manifest_path,
            v1_atlas=source,
            v1_brief=v1_brief or cls.v1_brief,
            editorial_artifact=editorial_artifact or cls.support.editorial,
            editorial_input_package=editorial_input_package or cls.support.package,
            audit_explorer=audit_value,
            source_artifacts=cls.sidecar["source_artifacts"],
            artifact_paths={
                "html": str((target / ATLAS_V2_HTML_FILENAME).resolve()),
                "json": str((target / ATLAS_V2_JSON_FILENAME).resolve()),
                "source_catalog": str(
                    (target / ATLAS_V2_SOURCE_CATALOG_FILENAME).resolve()
                ),
            },
            validated_relations=(
                cls._bound_contract(
                    ATLAS_V2_RELATIONS_SCHEMA_VERSION,
                    cls.valid_relations if relations is None else relations,
                )
            ),
            historical_observations=(
                cls._bound_contract(
                    ATLAS_V2_HISTORY_SCHEMA_VERSION,
                    cls._history_for(source) if history is None else history,
                )
            ),
            learning_events=cls._bound_contract(
                ATLAS_V2_LEARNING_EVENTS_SCHEMA_VERSION,
                cls.learning_events if learning is None else learning,
            ),
            source_contributions=(
                cls._contributions_for(source)
                if contributions is None
                else contributions
            ),
        )

    def test_reader_contract_is_closed_russian_visual_and_within_budget(self) -> None:
        sidecar = self.sidecar
        self.assertEqual(sidecar["schema_version"], ATLAS_V2_SCHEMA_VERSION)
        self.assertEqual(sidecar["surface"], "knowledge_atlas")
        self.assertEqual(sidecar["run_status"], "complete")
        self.assertFalse(sidecar["partial"])
        self.assertEqual(len(sidecar["primary_thread_ids"]), 8)
        self.assertEqual(len(sidecar["canonical_threads"]), 8)
        self.assertEqual(len(sidecar["timeline"]["weeks"]), 12)
        self.assertEqual(len(sidecar["visual_specs"]), 5)
        self.assertGreaterEqual(sidecar["content_metrics"]["meaningful_visual_count"], 4)
        self.assertLessEqual(
            sidecar["content_metrics"]["visible_word_count"],
            HARD_VISIBLE_WORDS_MAX,
        )
        self.assertEqual(
            sidecar["content_metrics"]["word_budget_status"], "within_budget"
        )
        html = self.html_path.read_text(encoding="utf-8")
        self.assertEqual(
            sidecar["content_metrics"]["visible_word_count"],
            reader_visible_word_count(html),
        )
        visible = _brief_v2_tests._visible_copy(html)
        self.assertIn("Что растёт", visible)
        self.assertIn("Где мало доказательств", visible)
        self.assertIn("Ограничения", visible)
        self.assertNotIn("canonical-01", visible)
        self.assertNotIn("atom:", visible)
        self.assertNotIn(str(self.manifest["run_id"]), visible)
        self.assertNotRegex(html, r"<(?:script|iframe)\b")
        self.assertNotRegex(html, r"(?:src|href)=[\"']https?://")
        self.assertEqual(
            render_knowledge_atlas_v2_html(sidecar, manifest=self.manifest),
            html,
        )
        visuals = {item["schema_version"]: item for item in sidecar["visual_specs"]}
        self.assertEqual(
            visuals["report_visual.thread_timeline.v1"]["data_status"],
            "available",
        )
        self.assertEqual(
            visuals["report_visual.source_thread_heatmap.v1"]["data_status"],
            "available",
        )
        graph = visuals["report_visual.knowledge_graph.v1"]
        self.assertEqual(
            graph["data_status"],
            "available" if graph["nodes"] else "empty",
        )
        self.assertTrue(all(any("А" <= char <= "я" for char in item["title_ru"]) for item in visuals.values()))

    def test_primary_boundaries_accept_8_and_12_and_reject_7_and_13(self) -> None:
        self.assertEqual(len(self.sidecar["primary_thread_ids"]), 8)
        twelve_v1 = self._expanded_v1(12)
        twelve = self._build_pure(v1=twelve_v1)
        self.assertEqual(len(twelve["primary_thread_ids"]), 12)
        self.assertEqual(len(twelve["canonical_threads"]), 12)
        self.assertLessEqual(twelve["content_metrics"]["visible_word_count"], 1500)

        for count in (7, 13):
            with self.subTest(count=count):
                value = self._expanded_v1(count)
                if count == 7:
                    value["canonical_threads"] = value["canonical_threads"][:7]
                with self.assertRaisesRegex(
                    KnowledgeAtlasV2ValidationError,
                    "8|12|exceeds|primary",
                ):
                    self._build_pure(v1=value, audit=self.audit)

    def test_manifest_identity_as_of_and_host_canonical_order_are_exact(self) -> None:
        expected_ids = list(self.v1["primary_canonical_thread_ids"])
        self.assertEqual(self.sidecar["primary_thread_ids"], expected_ids)
        self.assertEqual(self.sidecar["run_id"], self.manifest["run_id"])
        self.assertEqual(self.sidecar["reporting_period"], _reporting_period(self.manifest))
        self.assertEqual(self.sidecar["as_of"], self.manifest["analysis_period_end"])
        self.assertEqual(self.audit["canonical_thread_snapshot"]["as_of"], self.sidecar["as_of"])

        stale = copy.deepcopy(self.v1)
        stale["canonical_thread_snapshot"]["as_of"] = "2026-01-01T00:00:00Z"
        with self.assertRaisesRegex(
            KnowledgeAtlasV2ValidationError,
            "as_of",
        ):
            self._build_pure(v1=stale, audit=self.audit)

        wrong_manifest = copy.deepcopy(self.manifest)
        wrong_manifest["analysis_period_end"] = "2026-01-01T00:00:00Z"
        with self.assertRaises(KnowledgeAtlasV2ValidationError):
            validate_knowledge_atlas_v2(self.sidecar, manifest=wrong_manifest)

    def test_duplicate_identity_reader_content_and_backlog_fail_closed(self) -> None:
        duplicate_id = copy.deepcopy(self.v1)
        duplicate_id["canonical_threads"][1]["canonical_thread_id"] = (
            duplicate_id["canonical_threads"][0]["canonical_thread_id"]
        )
        with self.assertRaisesRegex(
            KnowledgeAtlasV2ValidationError,
            "unique|duplicated",
        ):
            self._build_pure(v1=duplicate_id, audit=self.audit)

        duplicate_copy = copy.deepcopy(self.v1)
        duplicate_copy["canonical_threads"][1]["title"] = (
            duplicate_copy["canonical_threads"][0]["title"]
        )
        duplicate_copy["canonical_threads"][1]["summary"] = (
            duplicate_copy["canonical_threads"][0]["summary"]
        )
        with self.assertRaises(KnowledgeAtlasV2ValidationError):
            self._build_pure(v1=duplicate_copy, audit=self.audit)

        duplicate_backlog = copy.deepcopy(self.sidecar)
        duplicate_backlog["study_backlog"].append(
            copy.deepcopy(duplicate_backlog["study_backlog"][0])
        )
        with self.assertRaisesRegex(
            KnowledgeAtlasV2ValidationError,
            "backlog|duplicated|duplicate",
        ):
            validate_knowledge_atlas_v2(duplicate_backlog, manifest=self.manifest)

    def test_relations_require_known_typed_evidence_and_never_entity_overlap(self) -> None:
        self.assertEqual(self.sidecar["thread_relations"], self.valid_relations)
        graph = next(
            item
            for item in self.sidecar["visual_specs"]
            if item["schema_version"] == "report_visual.knowledge_graph.v1"
        )
        self.assertTrue(all("relation" in edge for edge in graph["edges"]))

        vendor_only = copy.deepcopy(self.valid_relations[0])
        vendor_only["evidence_refs"] = []
        unsupported = copy.deepcopy(self.valid_relations[0])
        unsupported["relation"] = "same_vendor"
        self_edge = copy.deepcopy(self.valid_relations[0])
        self_edge["target_thread_id"] = self_edge["source_thread_id"]
        forged = copy.deepcopy(self.valid_relations[0])
        forged["evidence_refs"] = ["evidence:totally-forged-not-in-any-source"]
        for relation in (vendor_only, unsupported, self_edge, forged):
            with self.subTest(relation=relation):
                with self.assertRaises(KnowledgeAtlasV2ValidationError):
                    self._build_pure(relations=[relation])
        rejected_case = self.fixture["thread_relations"]["rejected"][0]
        self.assertEqual(rejected_case["rejection_reason"], "vendor_entity_overlap_only")
        self.assertNotIn(
            rejected_case["candidate_relation"],
            [item["relation"] for item in self.sidecar["thread_relations"]],
        )

    def test_timeline_preserves_exact_order_zero_missing_and_lineage_semantics(self) -> None:
        self.assertEqual(self.sidecar["timeline"]["coverage_status"], "complete")
        partial = self._build_pure(
            history=self._history_for(self.v1, include_missing=True)
        )
        timeline = partial["timeline"]
        self.assertEqual(timeline["weeks"], _weeks(self.manifest["reporting_week"]))
        self.assertEqual(timeline["coverage_status"], "partial")
        first = timeline["series"][0]
        self.assertEqual(first["momentum"][5], 0.0)
        self.assertEqual(first["evidence_count"][5], 0)
        self.assertIsNone(first["momentum"][6])
        self.assertIsNone(first["evidence_count"][6])
        self.assertIn("Ноль", timeline["zero_semantics_ru"])
        self.assertIn("недоступен", timeline["missing_semantics_ru"])
        self.assertTrue(partial["partial"])
        self.assertTrue(
            any("двенадцать недель" in reason for reason in partial["partial_reasons_ru"])
        )

        reordered = copy.deepcopy(self.sidecar)
        reordered["timeline"]["weeks"] = list(
            reversed(reordered["timeline"]["weeks"])
        )
        with self.assertRaisesRegex(
            KnowledgeAtlasV2ValidationError,
            "12 consecutive weeks|timeline",
        ):
            validate_knowledge_atlas_v2(reordered, manifest=self.manifest)

    def test_source_contract_is_identity_bound_and_caps_maturity_authority(self) -> None:
        catalog = json.loads(self.source_catalog_path.read_text(encoding="utf-8"))
        contract = catalog["source_contributions"]
        self.assertEqual(
            set(contract),
            {
                "schema_version",
                "run_id",
                "reporting_period",
                "as_of",
                "classification_status",
                "sources",
                "contributions",
                "limitation_ru",
            },
        )
        self.assertEqual(contract["run_id"], self.manifest["run_id"])
        self.assertEqual(contract["as_of"], self.manifest["analysis_period_end"])

        wrong_run = copy.deepcopy(self.source_contributions)
        wrong_run["run_id"] = "neighbor-run-2026-W28"
        with self.assertRaisesRegex(KnowledgeAtlasV2ValidationError, "run_id"):
            self._build_pure(contributions=wrong_run)

        inflated = copy.deepcopy(self.source_contributions)
        inflated["contributions"][0]["independent_support_count"] = 2
        with self.assertRaisesRegex(
            KnowledgeAtlasV2ValidationError,
            "overstates support",
        ):
            self._build_pure(contributions=inflated)

        declared = copy.deepcopy(self.v1)
        declared["canonical_threads"][0]["evidence_maturity"] = "decision_grade"
        conservative = self._build_pure(v1=declared)
        self.assertEqual(
            conservative["canonical_threads"][0]["evidence_maturity"], "unknown"
        )

        same_group_sources = [
            {
                "source_id": "source/telegram-a",
                "label": "Telegram A",
                "source_class": "external_analysis",
                "independence_group": "publisher/telegram",
                "classification_status": "available",
            },
            {
                "source_id": "source/telegram-b",
                "label": "Telegram B",
                "source_class": "external_analysis",
                "independence_group": "publisher/telegram",
                "classification_status": "available",
            },
        ]
        grouped = self._contributions_for(declared, sources=same_group_sources)
        first_id = declared["canonical_threads"][0]["canonical_thread_id"]
        first_thread = declared["canonical_threads"][0]
        first_navigation = next(
            item
            for item in declared["thread_navigation"]["threads"]
            if item["slug"] == first_thread["stable_slug"]
        )
        bound_refs = list(first_navigation.get("source_urls") or [])
        bound_refs.extend(
            atom if str(atom).startswith("atom:") else f"atom:{atom}"
            for atom in first_thread.get("atom_ids") or []
        )
        bound_refs = list(dict.fromkeys(bound_refs))
        self.assertGreaterEqual(len(bound_refs), 2)
        grouped["contributions"] = [
            {
                "source_id": source["source_id"],
                "canonical_thread_id": first_id,
                "mention_count": 1,
                "independent_support_count": 1,
                "decision_grade_evidence_count": 0,
                "evidence_refs": [bound_refs[index]],
            }
            for index, source in enumerate(same_group_sources)
        ]
        declared["canonical_threads"][0]["evidence_maturity"] = "multi_channel"
        grouped_result = self._build_pure(v1=declared, contributions=grouped)
        first = grouped_result["canonical_threads"][0]
        self.assertEqual(first["independent_source_count"], 1)
        self.assertEqual(first["evidence_maturity"], "unknown")

        hostile_ref = copy.deepcopy(self.source_contributions)
        hostile_ref["contributions"][-1]["evidence_refs"] = [
            "evidence:a/../../secret"
        ]
        with self.assertRaisesRegex(
            KnowledgeAtlasV2ValidationError,
            "unsafe reference",
        ):
            self._build_pure(contributions=hostile_ref)

    def _divergent_reaction_receipts(
        self,
    ) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        thread = self.v1["canonical_threads"][0]
        slug = str(thread["stable_slug"])
        atom_id = int((thread.get("atom_ids") or [7101])[0])
        post_ref = "reaction-post:111111111111111111111111"
        source_ref = "telegram:@source"
        evidence_ref = f"atom:{atom_id}"
        reason = _reader_item_reason(1)
        audit_item = {
            "surface_item_ref": f"thread:{slug}",
            "selected": True,
            "boost_applied": True,
            "compatibility_thread_ref": f"idea_thread:{slug}",
            "current_thread_ref": f"idea_thread:{slug}",
            "canonical_thread_ref": f"canonical_thread:{slug}",
            "thread_resolution_status": "canonical_membership_resolved",
            "boost_role": "weak_implicit_interest",
            "reacted_post_count": 1,
            "reader_reason_ru": reason,
            "reacted_post_refs": [post_ref],
            "source_refs": [source_ref],
            "evidence_refs": [evidence_ref],
        }

        def item(effect: str) -> dict[str, object]:
            flags = {
                "rank_changed": {
                    "rank_changed": True,
                    "selection_changed": False,
                    "linked_only": False,
                },
                "linked_only": {
                    "rank_changed": False,
                    "selection_changed": False,
                    "linked_only": True,
                },
            }[effect]
            return {
                **{
                    key: value
                    for key, value in audit_item.items()
                    if key != "selected"
                },
                "effect": effect,
                **flags,
            }

        counts = {
            "personal_reaction_events_detected": 1,
            "unique_reacted_posts": 1,
            "posts_resolved": 1,
            "eligible_period_posts": 1,
            "unique_atoms_linked": 1,
            "unique_canonical_threads_linked": 1,
            "canonical_threads_boosted": 1,
            "unique_compatibility_threads_linked": 1,
            "compatibility_threads_boosted": 1,
            "selected_items_linked": 1,
            "selected_signals_influenced": 0,
            "unconsumed_reaction_events": 0,
        }
        identity = {
            "schema_version": "reaction_personalization.v1",
            "run_id": self.manifest["run_id"],
            "reporting_week": self.manifest["reporting_week"],
            "analysis_period_start": self.manifest["analysis_period_start"],
            "analysis_period_end": self.manifest["analysis_period_end"],
            "snapshot_ref": f"reaction-snapshot:{self.manifest['run_id']}",
            "snapshot_status": "complete",
            "counts": counts,
            "unconsumed_by_reason": {},
            "unconsumed": [],
            "ranking_policy": {
                "policy_version": "reaction-ranking.v1",
                "strength": "weak",
                "below_confirmed_feedback": True,
                "can_change_evidence_gate": False,
            },
        }
        brief = {
            **identity,
            "surface": "weekly_brief",
            "status": "linked_no_selection_effect",
            "influenced_items": [],
            "linked_only_items": [item("linked_only")],
            "eligible_thread_audit": [
                {**audit_item, "counterfactual_effect": "linked_only"}
            ],
        }
        brief["reader_summary_ru"] = _reader_summary(
            str(brief["status"]),
            counts,
            snapshot_status="complete",
        )
        atlas_counts = {**counts, "selected_signals_influenced": 1}
        atlas = {
            **identity,
            "surface": "knowledge_atlas",
            "status": "effects_applied",
            "counts": atlas_counts,
            "influenced_items": [item("rank_changed")],
            "linked_only_items": [],
            "eligible_thread_audit": [
                {**audit_item, "counterfactual_effect": "rank_changed"}
            ],
        }
        atlas["reader_summary_ru"] = _reader_summary(
            str(atlas["status"]),
            atlas_counts,
            snapshot_status="complete",
        )
        editorial_effect = {
            "effect": "linked_only",
            "source_surface_item_ref": f"thread:{slug}",
            "reader_reason_ru": reason,
        }
        return (
            validate_reaction_effect(brief),
            validate_reaction_effect(atlas),
            editorial_effect,
        )

    def _editorial_for_package(
        self,
        package: dict[str, object],
        *,
        slug: str,
        reaction_effect: dict[str, object],
    ) -> dict[str, object]:
        editorial = copy.deepcopy(self.support.editorial)
        signal = next(
            item
            for item in editorial["signals"]
            if item["signal_id"] == f"signal:{slug}"
        )
        signal["reaction_effect"] = {
            "effect": reaction_effect["effect"],
            "reader_reason_ru": reaction_effect["reader_reason_ru"],
        }
        receipt = editorial["generation_receipt"]
        receipt["input_hash"] = editorial_input_hash(
            package,
            model=str(receipt["requested_model"]),
        )
        return editorial

    def test_brief_reaction_controls_editorial_while_atlas_controls_reader_interest(
        self,
    ) -> None:
        brief_receipt, atlas_receipt, editorial_effect = (
            self._divergent_reaction_receipts()
        )
        v1 = copy.deepcopy(self.v1)
        v1["reaction_effect"] = atlas_receipt
        v1_brief = copy.deepcopy(self.v1_brief)
        v1_brief["reaction_effect"] = brief_receipt
        package = copy.deepcopy(self.support.package)
        slug = str(v1["canonical_threads"][0]["stable_slug"])
        candidate = next(
            item
            for item in package["signal_candidates"]
            if f"idea_thread:{slug}" in item["source_thread_refs"]
        )
        candidate["reaction_effect"] = editorial_effect
        editorial = self._editorial_for_package(
            package,
            slug=slug,
            reaction_effect=editorial_effect,
        )

        result = self._build_pure(
            v1=v1,
            v1_brief=v1_brief,
            editorial_artifact=editorial,
            editorial_input_package=package,
            contributions=self._contributions_for(v1),
        )
        first = result["canonical_threads"][0]
        self.assertEqual(
            first["operator_interest"]["current_reaction_count"],
            1,
        )
        self.assertIn(
            "reaction-post:111111111111111111111111",
            first["operator_interest"]["current_reaction_evidence_refs"],
        )

        wrong_authority = copy.deepcopy(package)
        wrong_candidate = next(
            item
            for item in wrong_authority["signal_candidates"]
            if f"idea_thread:{slug}" in item["source_thread_refs"]
        )
        wrong_candidate["reaction_effect"] = {
            **editorial_effect,
            "effect": "rank_changed",
        }
        wrong_editorial = self._editorial_for_package(
            wrong_authority,
            slug=slug,
            reaction_effect=wrong_candidate["reaction_effect"],
        )
        with self.assertRaisesRegex(
            KnowledgeAtlasV2ValidationError,
            "reaction_effect differs",
        ):
            self._build_pure(
                v1=v1,
                v1_brief=v1_brief,
                editorial_artifact=wrong_editorial,
                editorial_input_package=wrong_authority,
                contributions=self._contributions_for(v1),
            )

        wrong_surface_brief = copy.deepcopy(v1_brief)
        wrong_surface_brief["reaction_effect"]["surface"] = "knowledge_atlas"
        with self.assertRaisesRegex(
            KnowledgeAtlasV2ValidationError,
            "Brief reaction receipt surface mismatch",
        ):
            self._build_pure(
                v1=v1,
                v1_brief=wrong_surface_brief,
                editorial_artifact=editorial,
                editorial_input_package=package,
                contributions=self._contributions_for(v1),
            )

    def test_reaction_feedback_and_learning_are_separate_non_inference_channels(self) -> None:
        receipt = self.fixture["reaction_effect"]
        count, refs = _reaction_for_thread(receipt, "reaction-interest-is-weak")
        self.assertEqual(count, 1)
        self.assertEqual(
            refs.count("reaction-post:111111111111111111111111"),
            1,
        )
        self.assertEqual(len(refs), len(set(refs)))

        threads = [
            {
                "canonical_thread_id": item["canonical_thread_id"],
                "stable_slug": item["stable_slug"],
            }
            for item in self.fixture["canonical_threads"]
        ]
        learning = _learning_projection(
            threads,
            reaction=receipt,
            event_contract={
                "status": "available",
                "items": [copy.deepcopy(self.fixture["learning_observations"][1])],
            },
        )
        stages = {item["key"]: item for item in learning["stages"]}
        self.assertEqual(stages["marked"]["confirmation_kind"], "reaction")
        self.assertEqual(stages["read"]["confirmation_kind"], "read_receipt")
        self.assertEqual(stages["understood"]["observation_status"], "unknown")
        self.assertIsNone(stages["understood"]["count"])

        interest = self.sidecar["operator_interest"]
        self.assertIn("current_reactions", interest)
        self.assertIn("confirmed_feedback", interest)
        sidecar_stages = {
            item["key"]: item for item in self.sidecar["learning_progression"]["stages"]
        }
        self.assertEqual(sidecar_stages["read"]["observation_status"], "confirmed")
        self.assertEqual(sidecar_stages["understood"]["observation_status"], "unknown")
        self.assertTrue(
            all(
                item["operator_interest"]["learning_inference"] == "none"
                for item in self.sidecar["canonical_threads"]
            )
        )

    def test_audit_explorer_preserves_detail_deep_links_aliases_and_lineage(self) -> None:
        audit = self.audit
        self.assertEqual(audit["schema_version"], AUDIT_EXPLORER_SCHEMA_VERSION)
        self.assertEqual(audit["technical_notice_ru"], TECHNICAL_NOTICE_RU)
        self.assertEqual(audit["canonical_thread_count"], 8)
        self.assertGreater(audit["raw_thread_count"], 0)
        self.assertEqual(len(audit["deep_links"]), 16)
        html = self.audit_html_path.read_text(encoding="utf-8")
        self.assertIn(TECHNICAL_NOTICE_RU, html)
        for link in audit["deep_links"]:
            self.assertEqual(
                link["href"],
                f"{AUDIT_EXPLORER_HTML_FILENAME}#{link['anchor']}",
            )
            self.assertIn(f'id="{link["anchor"]}"', html)
        navigation = audit["thread_navigation"]["threads"]
        self.assertTrue(any(item["evidence_items"] for item in navigation))
        self.assertTrue(
            any(
                evidence.get("evidence_quote")
                for item in navigation
                for evidence in item["evidence_items"]
            )
        )

        enriched = copy.deepcopy(self.v1)
        fixture_thread = self.fixture["canonical_threads"][0]
        enriched["canonical_threads"][0]["aliases"] = copy.deepcopy(
            fixture_thread["aliases"]
        )
        enriched["canonical_threads"][0]["merged_from"] = copy.deepcopy(
            fixture_thread["merged_from"]
        )
        enriched["canonical_threads"][0]["lineage"] = copy.deepcopy(
            fixture_thread["lineage"]
        )
        enriched_audit = self._audit_for_v1(enriched)
        canonical = enriched_audit["canonical_threads"][0]
        self.assertEqual(canonical["aliases"], fixture_thread["aliases"])
        self.assertEqual(canonical["merged_from"], fixture_thread["merged_from"])
        self.assertEqual(canonical["lineage"], fixture_thread["lineage"])
        enriched_html = render_knowledge_audit_explorer_html(
            enriched_audit,
            self.v1_html_path.read_text(encoding="utf-8"),
            manifest=self.manifest,
        )
        self.assertIn("release-gate-updates", enriched_html)
        self.assertIn("decision:merge-release-gates", enriched_html)

    def test_generation_is_byte_deterministic_private_and_cache_exact(self) -> None:
        paths = (
            self.html_path,
            self.sidecar_path,
            self.source_catalog_path,
            self.audit_html_path,
            self.audit_path,
        )
        before = {path.name: path.read_bytes() for path in paths}
        summary = generate_knowledge_atlas_v2_package(
            manifest_path=self.manifest_path,
            editorial_artifact_path=self.support.editorial_path,
            editorial_input_package=self.support.package,
            output_root=self.output_root,
            allowed_source_roots=(self.root,),
            validated_relations=self.relation_contract,
            historical_observations=self.history_contract,
            learning_events=self.learning_contract,
            source_contributions=self.source_contributions,
        )
        self.assertTrue(summary.cache_hit)
        self.assertEqual(before, {path.name: path.read_bytes() for path in paths})
        self.assertEqual(stat.S_IMODE(self.sidecar_path.parent.stat().st_mode), 0o700)
        for path in paths:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_package_reader_rejects_fifo_without_blocking(self) -> None:
        fifo_path = self.root / "atlas-v2-fifo"
        if fifo_path.exists():
            fifo_path.unlink()
        os.mkfifo(fifo_path, mode=0o600)
        try:
            with self.assertRaisesRegex(
                ReportPackageSecurityError,
                "regular file",
            ):
                read_bounded_bytes(fifo_path, label="fifo", maximum=16)
        finally:
            fifo_path.unlink(missing_ok=True)

    def test_visual_source_refs_are_exact_atlas_owned_refs(self) -> None:
        for replacement in (["garbage"], ["atom:"]):
            with self.subTest(replacement=replacement):
                mutated = copy.deepcopy(self.sidecar)
                mutated["visual_specs"][0]["source_refs"] = replacement
                with self.assertRaisesRegex(
                    KnowledgeAtlasV2ValidationError,
                    "source_refs",
                ):
                    validate_knowledge_atlas_v2(mutated, manifest=self.manifest)

    def test_reader_value_gate_blocks_before_publish_and_on_strict_load(self) -> None:
        blocked = {"summary": {"delivery_decision": "block"}}
        error = ReaderValueQualityError(blocked)
        blocked_root = self.root / "atlas-v2-quality-blocked"
        target = blocked_root / ATLAS_V2_DIRECTORY / self.manifest["run_id"]
        with patch(
            "output.report_quality.require_reader_report_quality",
            side_effect=error,
        ):
            with self.assertRaisesRegex(
                KnowledgeAtlasV2ArtifactError,
                "failed reader-value quality gates",
            ):
                generate_knowledge_atlas_v2_package(
                    manifest_path=self.manifest_path,
                    editorial_artifact_path=self.support.editorial_path,
                    editorial_input_package=self.support.package,
                    output_root=blocked_root,
                    allowed_source_roots=(self.root,),
                    validated_relations=self.relation_contract,
                    historical_observations=self.history_contract,
                    learning_events=self.learning_contract,
                    source_contributions=self.source_contributions,
                )
        self.assertFalse(target.exists())

        with patch(
            "output.report_quality.require_reader_report_quality",
            side_effect=error,
        ):
            with self.assertRaisesRegex(
                KnowledgeAtlasV2ArtifactError,
                "failed reader-value quality gates",
            ):
                load_manifest_bound_knowledge_atlas_v2(
                    self.sidecar_path,
                    expected_manifest_path=self.manifest_path,
                    allowed_source_roots=(self.root,),
                )

    def test_strict_loader_rejects_tamper_duplicate_nonfinite_and_oversize_json(self) -> None:
        with _restored_file(self.html_path) as original:
            self.html_path.write_bytes(original + b"\n<!-- tamper -->\n")
            with self.assertRaises(KnowledgeAtlasV2ArtifactError):
                load_manifest_bound_knowledge_atlas_v2(
                    self.sidecar_path,
                    expected_manifest_path=self.manifest_path,
                    allowed_source_roots=(self.root,),
                )

        with _restored_file(self.sidecar_path) as original:
            text = original.decode("utf-8")
            needle = f'"run_id": "{self.manifest["run_id"]}",'
            self.assertIn(needle, text)
            self.sidecar_path.write_text(
                text.replace(needle, f"{needle}\n  {needle}", 1),
                encoding="utf-8",
            )
            self.sidecar_path.chmod(0o600)
            with self.assertRaisesRegex(
                KnowledgeAtlasV2ArtifactError,
                "duplicate JSON key|invalid Atlas V2 sidecar",
            ):
                load_manifest_bound_knowledge_atlas_v2(
                    self.sidecar_path,
                    expected_manifest_path=self.manifest_path,
                    allowed_source_roots=(self.root,),
                )

        with _restored_file(self.sidecar_path) as original:
            text = original.decode("utf-8")
            text = text.replace('"visible_word_count": ', '"visible_word_count": NaN, "discarded": ', 1)
            self.sidecar_path.write_text(text, encoding="utf-8")
            self.sidecar_path.chmod(0o600)
            with self.assertRaisesRegex(
                KnowledgeAtlasV2ArtifactError,
                "non-finite|invalid Atlas V2 sidecar",
            ):
                load_manifest_bound_knowledge_atlas_v2(
                    self.sidecar_path,
                    expected_manifest_path=self.manifest_path,
                    allowed_source_roots=(self.root,),
                )

        with _restored_file(self.sidecar_path):
            self.sidecar_path.write_bytes(b"{" + b" " * (MAX_JSON_BYTES + 1))
            self.sidecar_path.chmod(0o600)
            with self.assertRaisesRegex(KnowledgeAtlasV2ArtifactError, "byte limit"):
                load_manifest_bound_knowledge_atlas_v2(
                    self.sidecar_path,
                    expected_manifest_path=self.manifest_path,
                    allowed_source_roots=(self.root,),
                )

    def test_loader_rejects_source_swap_public_paths_aliases_and_partial_packages(self) -> None:
        with _restored_file(self.source_catalog_path) as original:
            self.source_catalog_path.write_bytes(original + b"\n")
            self.source_catalog_path.chmod(0o600)
            with self.assertRaisesRegex(
                KnowledgeAtlasV2ArtifactError,
                "checksum mismatch",
            ):
                load_manifest_bound_knowledge_atlas_v2(
                    self.sidecar_path,
                    expected_manifest_path=self.manifest_path,
                    allowed_source_roots=(self.root,),
                )

        with _restored_file(Path(self.support.editorial_path)) as original:
            Path(self.support.editorial_path).write_bytes(original + b"\n")
            with self.assertRaisesRegex(
                KnowledgeAtlasV2ArtifactError,
                "checksum mismatch",
            ):
                load_manifest_bound_knowledge_atlas_v2(
                    self.sidecar_path,
                    expected_manifest_path=self.manifest_path,
                    allowed_source_roots=(self.root,),
                )

        package_mode = stat.S_IMODE(self.sidecar_path.parent.stat().st_mode)
        try:
            self.sidecar_path.parent.chmod(0o755)
            with self.assertRaisesRegex(
                KnowledgeAtlasV2ArtifactError,
                "private",
            ):
                load_manifest_bound_knowledge_atlas_v2(
                    self.sidecar_path,
                    expected_manifest_path=self.manifest_path,
                    allowed_source_roots=(self.root,),
                )
        finally:
            self.sidecar_path.parent.chmod(package_mode)

        alias = self.root / "atlas-v2-sidecar-alias.json"
        alias.symlink_to(self.sidecar_path)
        with self.assertRaisesRegex(KnowledgeAtlasV2ArtifactError, "symlink"):
            load_manifest_bound_knowledge_atlas_v2(
                alias,
                expected_manifest_path=self.manifest_path,
                allowed_source_roots=(self.root,),
            )

        partial_root = self.root / "atlas-v2-partial"
        partial_dir = partial_root / ATLAS_V2_DIRECTORY / self.manifest["run_id"]
        partial_dir.mkdir(parents=True, mode=0o700)
        partial_dir.chmod(0o700)
        partial_sidecar = partial_dir / ATLAS_V2_JSON_FILENAME
        partial_sidecar.write_bytes(self.sidecar_path.read_bytes())
        partial_sidecar.chmod(0o600)
        with self.assertRaises(KnowledgeAtlasV2ArtifactError):
            find_manifest_bound_knowledge_atlas_v2(
                output_root=partial_root,
                run_id=self.manifest["run_id"],
                expected_manifest_path=self.manifest_path,
                allowed_source_roots=(self.root,),
            )

        with self.assertRaises(KnowledgeAtlasV2ArtifactError):
            find_manifest_bound_knowledge_atlas_v2(
                output_root=self.output_root,
                run_id="../neighbor-run",
                expected_manifest_path=self.manifest_path,
                allowed_source_roots=(self.root,),
            )

        symlink_root = self.root / "atlas-v2-finder-alias"
        symlink_root.mkdir()
        (symlink_root / ATLAS_V2_DIRECTORY).symlink_to(
            self.output_root / ATLAS_V2_DIRECTORY,
            target_is_directory=True,
        )
        with self.assertRaisesRegex(KnowledgeAtlasV2ArtifactError, "finder root"):
            find_manifest_bound_knowledge_atlas_v2(
                output_root=symlink_root,
                run_id=self.manifest["run_id"],
                expected_manifest_path=self.manifest_path,
                allowed_source_roots=(self.root,),
            )

    def test_hostile_url_wrong_manifest_and_sidecar_path_are_rejected(self) -> None:
        hostile = copy.deepcopy(self.v1)
        hostile["canonical_threads"][0]["source_urls"] = ["javascript:alert(1)"]
        hostile["canonical_threads"][0]["source_refs"] = ["javascript:alert(1)"]
        nav = hostile["thread_navigation"]["threads"][0]
        nav["source_urls"] = ["javascript:alert(1)"]
        for evidence in nav["evidence_items"]:
            evidence["source_urls"] = ["javascript:alert(1)"]
        with self.assertRaises(Exception) as raised:
            self._build_pure(v1=hostile)
        self.assertRegex(str(raised.exception), "URL|evidence|source")

        invalid_port = copy.deepcopy(self.v1)
        invalid_port["canonical_threads"][-1]["source_urls"] = [
            "https://example.com:bad/x"
        ]
        with self.assertRaisesRegex(
            Exception,
            "source URL|unsafe reference|manifest-bound evidence|absolute HTTP",
        ):
            self._build_pure(v1=invalid_port)

        neighbor = self.root / "neighbor" / self.manifest["run_id"]
        neighbor.mkdir(parents=True)
        wrong_manifest = neighbor / "manifest.json"
        wrong_manifest.write_bytes(self.manifest_path.read_bytes())
        with self.assertRaisesRegex(
            KnowledgeAtlasV2ArtifactError,
            "manifest selection mismatch",
        ):
            load_manifest_bound_knowledge_atlas_v2(
                self.sidecar_path,
                expected_manifest_path=wrong_manifest,
                allowed_source_roots=(self.root,),
            )

        with _restored_file(self.sidecar_path):
            changed_path = copy.deepcopy(self.sidecar)
            neighbor_html = self.root / "neighbor" / "knowledge-atlas.v2.html"
            neighbor_html.write_text("neighbor", encoding="utf-8")
            changed_path["artifact_paths"]["html"] = str(neighbor_html.resolve())
            self.sidecar_path.write_bytes(canonical_json_bytes(changed_path))
            self.sidecar_path.chmod(0o600)
            with self.assertRaisesRegex(
                KnowledgeAtlasV2ArtifactError,
                "html path mismatch",
            ):
                load_manifest_bound_knowledge_atlas_v2(
                    self.sidecar_path,
                    expected_manifest_path=self.manifest_path,
                    allowed_source_roots=(self.root,),
                )

    def test_brief_navigation_accepts_only_explicit_strict_atlas_package(self) -> None:
        brief_summary = generate_weekly_intelligence_brief_v2_artifact(
            manifest_path=self.manifest_path,
            editorial_artifact_path=self.support.editorial_path,
            editorial_input_package=self.support.package,
            project_intelligence_path=self.support.project_path,
            project_descriptors=self.support.project_descriptors,
            output_root=self.root / "brief-v2-with-atlas-navigation",
            allowed_source_roots=(self.root,),
            knowledge_atlas_v2_json_path=self.sidecar_path,
        )
        brief = load_manifest_bound_weekly_intelligence_brief_v2(
            brief_summary.json_path,
            expected_manifest_path=self.manifest_path,
            allowed_source_roots=(self.root,),
        )
        self.assertEqual(brief["navigation"]["atlas_v2"]["status"], "available")
        self.assertEqual(
            brief["navigation"]["atlas_v2"]["path"],
            str(self.html_path),
        )
        self.assertEqual(
            brief["navigation"]["audit_explorer"]["path"],
            str(self.audit_html_path),
        )

        with self.assertRaisesRegex(
            WeeklyIntelligenceBriefV2ArtifactError,
            "strict bound loading|Atlas V2",
        ):
            generate_weekly_intelligence_brief_v2_artifact(
                manifest_path=self.manifest_path,
                editorial_artifact_path=self.support.editorial_path,
                editorial_input_package=self.support.package,
                project_intelligence_path=self.support.project_path,
                project_descriptors=self.support.project_descriptors,
                output_root=self.root / "brief-v2-invalid-atlas-navigation",
                allowed_source_roots=(self.root,),
                knowledge_atlas_v2_json_path=self.v1_json_path,
            )


if __name__ == "__main__":
    unittest.main()
