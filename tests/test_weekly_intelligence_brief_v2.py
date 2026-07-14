from __future__ import annotations

import copy
import json
import stat
import unittest
from html.parser import HTMLParser
from pathlib import Path

from output.editorial_intelligence import (
    build_editorial_input_package,
    synthesize_editorial_intelligence,
)
from output.mvp_radar_reader import load_bound_mvp_radar_reader
from output.project_intelligence import (
    generate_project_intelligence_artifact,
    load_project_action_descriptors,
    load_project_intelligence_artifact,
    project_editorial_permissions,
)
from output.weekly_intelligence_brief_v2 import (
    BRIEF_V2_DIRECTORY,
    BRIEF_V2_HTML_FILENAME,
    BRIEF_V2_JSON_FILENAME,
    BRIEF_V2_SCHEMA_VERSION,
    BRIEF_V2_SOURCE_CATALOG_FILENAME,
    WeeklyIntelligenceBriefV2ArtifactError,
    WeeklyIntelligenceBriefV2ValidationError,
    _reaction_effect_for_candidate,
    _reaction_visual,
    _radar_visual,
    _render_feedback_effect,
    _render_radar_context,
    _render_document,
    _read_strict_json_value,
    _selected_reaction_count,
    _visual_specs,
    build_weekly_intelligence_brief_v2,
    find_manifest_bound_weekly_intelligence_brief_v2,
    generate_weekly_intelligence_brief_v2_artifact,
    load_manifest_bound_weekly_intelligence_brief_v2,
    render_weekly_intelligence_brief_v2_html,
    validate_weekly_intelligence_brief_v2,
    visible_word_count,
)
from output.weekly_run_manifest import (
    WeeklyRunManifestError,
    load_manifest,
    sha256_file,
)
from tests.test_editorial_intelligence import (
    MODEL,
    _context,
    _receipt,
    _valid_model_output,
)
from tests import test_weekly_intelligence_orchestrator as _orchestrator_tests


class _VisibleCopy(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden = 0
        self._details = 0
        self._summary = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag in {"style", "script", "template", "title"}:
            self._hidden += 1
        elif tag == "details":
            self._details += 1
        elif tag == "summary" and self._details:
            self._summary += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"style", "script", "template", "title"}:
            self._hidden = max(0, self._hidden - 1)
        elif tag == "summary" and self._summary:
            self._summary -= 1
        elif tag == "details" and self._details:
            self._details -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden and (not self._details or self._summary) and data.strip():
            self.parts.append(data.strip())


def _visible_copy(html: str) -> str:
    parser = _VisibleCopy()
    parser.feed(html)
    parser.close()
    return " ".join(parser.parts)


class WeeklyIntelligenceBriefV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _orchestrator_tests.TestWeeklyIntelligenceOrchestrator(
            methodName=(
                "test_verified_reaction_outcome_is_immutable_bound_and_passed_to_context"
            )
        )
        cls.fixture.setUp()
        try:
            cls._build_rich_fixture()
        except Exception:
            cls.fixture.tearDown()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.tearDown()

    @classmethod
    def _build_rich_fixture(cls) -> None:
        helper = cls.fixture
        cls.run_id = "tra-weekly-2026-W28-irx6-rich-test"
        context = copy.deepcopy(_context(thread_count=3))
        context.update(helper.period.to_dict())
        context.update(
            run_id=cls.run_id,
            week_label=helper.period.reporting_week,
        )
        context["feedback_context"] = {
            "event_count": 0,
            "confirmed_event_count": 0,
            "feedback_effect_traces": [],
        }
        context["reaction_effect"] = helper._empty_complete_reaction_effect(
            cls.run_id
        )
        result = helper._run(
            run_id=cls.run_id,
            _context=context,
            _real_context=False,
        )
        cls.run_result = result
        cls.manifest_path = Path(result.manifest_path)
        cls.manifest = load_manifest(
            cls.manifest_path,
            path_base=cls.manifest_path.parent,
            allowed_roots=(cls.manifest_path.parent,),
            check_artifact_existence=True,
        )
        v1_brief = json.loads(
            Path(result.weekly_brief_json_path).read_text(encoding="utf-8")
        )
        cls.reaction = v1_brief["reaction_effect"]
        context["reaction_effect"] = copy.deepcopy(cls.reaction)
        identity = {
            key: cls.manifest[key]
            for key in (
                "run_id",
                "run_date",
                "generated_at",
                "reporting_week",
                "analysis_period_start",
                "analysis_period_end",
                "period_mode",
                "pipeline_profile",
            )
        }
        identity["manifest_path"] = str(cls.manifest_path.resolve())
        binding = json.loads(
            (cls.manifest_path.parent / "radar" / "radar-run-binding.json").read_text(
                encoding="utf-8"
            )
        )
        preliminary = build_editorial_input_package(
            context,
            run_identity=identity,
            radar_binding=binding,
            project_permissions=(),
            feedback_snapshot_count=0,
        )
        candidate = preliminary["signal_candidates"][0]
        canonical_ref = candidate["canonical_thread_refs"][0]
        descriptor = {
            "name": "telegram-research-agent",
            "repo": "ashishki/telegram-research-agent",
            "description": "Проверяемый проект для читательского брифа.",
            "focus": "Детерминированная читательская поверхность.",
            "keywords": ["бриф", "доказательства"],
            "project_intelligence": {
                "schema_version": "project_action_permissions.v1",
                "action_permissions": [
                    {
                        "permission_id": "brief-v2-reader-action",
                        "canonical_thread_refs": [canonical_ref],
                        "why_this_project": (
                            "Проект уже формирует недельный бриф и может применить "
                            "точное ограниченное улучшение."
                        ),
                        "affected_component": "Weekly Intelligence Brief V2",
                        "suggested_change": (
                            "Добавить проверяемое читательское действие для "
                            "выбранного сигнала."
                        ),
                        "likely_files": [
                            "src/output/weekly_intelligence_brief_v2.py",
                            "tests/test_weekly_intelligence_brief_v2.py",
                        ],
                        "effort": "S",
                        "acceptance_criteria": [
                            (
                                "Действие связано только с доказательствами "
                                "выбранного сигнала."
                            ),
                            "Проверка не меняет базовую доставку V1.",
                        ],
                        "risk": (
                            "Нельзя выдавать слабое совпадение за подтверждённое "
                            "проектное действие."
                        ),
                        "priority": 10,
                    }
                ],
            },
        }
        cls.projects_path = helper.root / "irx6-projects.json"
        cls.projects_path.write_text(
            json.dumps({"projects": [descriptor]}, ensure_ascii=False),
            encoding="utf-8",
        )
        cls.project_descriptors = load_project_action_descriptors(
            cls.projects_path
        )
        diagnostic = {
            "project_name": "telegram-research-agent",
            "permission_id": "brief-v2-reader-action",
            "signal_id": candidate["signal_id"],
            "canonical_thread_ref": canonical_ref,
            "status": "confirmed",
            "reason_ru": (
                "Точный проект, каноническая тема и зрелые доказательства "
                "совпали с разрешением хоста."
            ),
            "evidence_refs": list(candidate["evidence_refs"]),
        }
        project_summary = generate_project_intelligence_artifact(
            preliminary,
            output_root=helper.root / "project-intelligence",
            projects_yaml_path=cls.projects_path,
            diagnostic_records=[diagnostic],
        )
        cls.project_path = Path(project_summary.path)
        cls.project = load_project_intelligence_artifact(cls.project_path)
        permissions = project_editorial_permissions(
            cls.project,
            input_package=preliminary,
            projects=cls.project_descriptors,
        )
        cls.package = build_editorial_input_package(
            context,
            run_identity=identity,
            radar_binding=binding,
            project_permissions=permissions,
            feedback_snapshot_count=0,
        )
        model_output = _valid_model_output(cls.package, signal_count=3)
        signal_refs = [item["signal_id"] for item in model_output["signals"]]
        model_output["signals"][0]["decision"] = "act"
        model_output["signals"][1]["decision"] = "watch"
        model_output["signals"][2]["decision"] = "ignore"
        model_output["decision_matrix"] = {
            "act": [signal_refs[0]],
            "study": [],
            "watch": [signal_refs[1]],
            "ignore": [signal_refs[2]],
        }
        project_ref = permissions[0]["project_action_ref"]
        model_output["signals"][0]["project_implications"] = [project_ref]
        model_output["project_actions"] = [project_ref]
        cls.editorial = synthesize_editorial_intelligence(
            cls.package,
            model=MODEL,
            completion=lambda **_kwargs: _receipt(
                json.dumps(model_output, ensure_ascii=False)
            ),
            generated_at=cls.manifest["generated_at"],
        )
        cls.editorial_path = helper.root / "editorial.json"
        cls.editorial_path.write_text(
            json.dumps(cls.editorial, ensure_ascii=False),
            encoding="utf-8",
        )
        cls.radar = load_bound_mvp_radar_reader(
            cls.manifest,
            path_base=cls.manifest_path.parent,
            allowed_roots=(cls.manifest_path.parent,),
        )
        cls.summary = generate_weekly_intelligence_brief_v2_artifact(
            manifest_path=cls.manifest_path,
            editorial_artifact_path=cls.editorial_path,
            editorial_input_package=cls.package,
            project_intelligence_path=cls.project_path,
            project_descriptors=cls.project_descriptors,
            output_root=helper.root,
            allowed_source_roots=(helper.root,),
        )
        cls.sidecar = load_manifest_bound_weekly_intelligence_brief_v2(
            cls.summary.json_path,
            expected_manifest_path=cls.manifest_path,
            allowed_source_roots=(helper.root,),
        )

    def test_rich_reader_contract_is_complete_bounded_and_in_target(self) -> None:
        sidecar = self.sidecar
        self.assertEqual(sidecar["schema_version"], BRIEF_V2_SCHEMA_VERSION)
        self.assertEqual(sidecar["run_status"], "complete")
        self.assertFalse(sidecar["partial"])
        self.assertEqual(len(sidecar["signals"]), 3)
        self.assertEqual(set(sidecar["decision_matrix"]), {"act", "study", "watch", "ignore"})
        self.assertEqual(len(sidecar["decision_matrix"]["act"]), 1)
        self.assertEqual(len(sidecar["decision_matrix"]["ignore"]), 1)
        self.assertIsNotNone(sidecar["actions"]["primary"])
        self.assertLessEqual(len(sidecar["actions"]["secondary"]), 2)
        self.assertEqual(len(sidecar["project_actions"]), 1)
        self.assertEqual(len(sidecar["feedback_targets"]), 5)
        metrics = sidecar["content_metrics"]
        self.assertEqual(metrics["word_budget_status"], "within_target")
        self.assertGreaterEqual(metrics["visible_word_count"], 700)
        self.assertLessEqual(metrics["visible_word_count"], 900)
        self.assertEqual(metrics["visual_component_count"], 4)
        self.assertGreaterEqual(metrics["meaningful_visual_count"], 3)

    def test_html_is_russian_offline_responsive_and_hides_internal_copy(self) -> None:
        html = render_weekly_intelligence_brief_v2_html(
            self.sidecar,
            manifest=self.manifest,
        )
        visible = _visible_copy(html)
        self.assertIn("Завершённый период", visible)
        self.assertIn("CEST", visible)
        self.assertIn("Еженедельный аналитический бриф", visible)
        self.assertIn("Главный вывод недели", visible)
        self.assertIn("Как реакции повлияли на бриф", visible)
        self.assertIn("Снимок реакций: завершён", visible)
        self.assertIn("Что изменила подтверждённая обратная связь", visible)
        self.assertIn("MVP Radar", visible)
        self.assertIn("Что было полезно?", visible)
        self.assertNotIn("signal:", visible)
        self.assertNotIn("project_action:", visible)
        self.assertNotIn("build_allowed", visible)
        self.assertNotIn("focused_experiment", visible)
        self.assertNotIn("ranking", visible.casefold())
        self.assertNotIn("Weekly Intelligence Brief V2", visible)
        self.assertNotIn("src/output/", visible)
        self.assertNotIn("KIR Knowledge Thread", visible)
        self.assertNotIn("bounded Radar run", visible)
        self.assertNotIn("manifest-bound", visible)
        self.assertNotIn("KIR", visible)
        self.assertEqual(visible.count("Кандидат:"), 1)
        self.assertEqual(visible.count("Следующая проверка:"), 1)
        self.assertIn("default-src 'none'", html)
        self.assertIn("@media(max-width:600px)", html)
        self.assertNotIn("<script", html.casefold())
        self.assertEqual(visible_word_count(html), self.sidecar["content_metrics"]["visible_word_count"])

    def test_public_consumers_reject_authoritative_radar_without_manifest(self) -> None:
        for consumer in (
            validate_weekly_intelligence_brief_v2,
            render_weekly_intelligence_brief_v2_html,
        ):
            with self.subTest(consumer=consumer.__name__), self.assertRaisesRegex(
                WeeklyIntelligenceBriefV2ValidationError,
                "authoritative Radar reader requires the current run manifest",
            ):
                consumer(self.sidecar)

    def test_generation_is_byte_stable_and_cache_safe(self) -> None:
        before_package = copy.deepcopy(self.package)
        html_bytes = Path(self.summary.html_path).read_bytes()
        json_bytes = Path(self.summary.json_path).read_bytes()
        catalog_bytes = Path(self.summary.source_catalog_path).read_bytes()

        cached = generate_weekly_intelligence_brief_v2_artifact(
            manifest_path=self.manifest_path,
            editorial_artifact_path=self.editorial_path,
            editorial_input_package=self.package,
            project_intelligence_path=self.project_path,
            project_descriptors=self.project_descriptors,
            output_root=self.fixture.root,
            allowed_source_roots=(self.fixture.root,),
        )

        self.assertTrue(cached.cache_hit)
        self.assertEqual(Path(cached.html_path).read_bytes(), html_bytes)
        self.assertEqual(Path(cached.json_path).read_bytes(), json_bytes)
        self.assertEqual(Path(cached.source_catalog_path).read_bytes(), catalog_bytes)
        self.assertEqual(self.package, before_package)

    def test_primary_and_defer_follow_host_signal_order_not_matrix_order(self) -> None:
        model_output = _valid_model_output(self.package, signal_count=3)
        refs = [item["signal_id"] for item in model_output["signals"]]
        model_output["signals"][0]["decision"] = "act"
        model_output["signals"][1]["decision"] = "act"
        model_output["signals"][2]["decision"] = "ignore"
        model_output["decision_matrix"] = {
            "act": [refs[1], refs[0]],
            "study": [],
            "watch": [],
            "ignore": [refs[2]],
        }
        model_output["project_actions"] = []
        editorial = synthesize_editorial_intelligence(
            self.package,
            model=MODEL,
            completion=lambda **_kwargs: _receipt(
                json.dumps(model_output, ensure_ascii=False)
            ),
            generated_at=self.manifest["generated_at"],
        )
        root = self.fixture.root / "host-order-preview"

        sidecar = build_weekly_intelligence_brief_v2(
            manifest=self.manifest,
            manifest_path=self.manifest_path.resolve(),
            editorial_artifact=editorial,
            editorial_input_package=self.package,
            reaction_effect=self.reaction,
            project_intelligence=self.project,
            project_descriptors=self.project_descriptors,
            mvp_radar=self.radar,
            source_artifacts=self.sidecar["source_artifacts"],
            artifact_paths={
                "html": str((root / BRIEF_V2_HTML_FILENAME).resolve()),
                "json": str((root / BRIEF_V2_JSON_FILENAME).resolve()),
                "source_catalog": str(
                    (root / BRIEF_V2_SOURCE_CATALOG_FILENAME).resolve()
                ),
            },
            compatibility_atlas_path=self.run_result.atlas_html_path,
        )

        self.assertEqual(sidecar["actions"]["primary"]["signal_ref"], refs[0])
        self.assertEqual(
            [row["signal_ref"] for row in sidecar["decision_matrix"]["act"]],
            [refs[0], refs[1]],
        )
        self.assertEqual(
            sidecar["decision_matrix"]["ignore"][0]["signal_ref"],
            refs[2],
        )

    def test_reaction_funnel_counts_selected_v2_effects_not_v1_selector_count(self) -> None:
        receipt = copy.deepcopy(self.reaction)
        receipt["status"] = "effects_applied"
        receipt["snapshot_status"] = "complete"
        receipt["counts"] = {
            **receipt["counts"],
            "personal_reaction_events_detected": 5,
            "posts_resolved": 4,
            "unique_atoms_linked": 4,
            "unique_compatibility_threads_linked": 3,
            "selected_signals_influenced": 3,
        }
        signals = copy.deepcopy(self.sidecar["signals"])
        signals[0]["reaction_effect"]["effect"] = "rank_changed"
        decision_items = [
            {"decision": bucket, **row}
            for bucket, rows in self.sidecar["decision_matrix"].items()
            for row in rows
        ]

        specs = _visual_specs(
            run_id=self.run_id,
            period=self.sidecar["reporting_period"],
            decision_items=decision_items,
            reaction_effect=receipt,
            selected_reaction_count=_selected_reaction_count(signals),
            project_actions=self.sidecar["project_actions"],
            mvp_radar=self.radar,
            signal_titles={
                signal["signal_id"]: signal["title"] for signal in signals
            },
            decision_contract_complete=True,
        )

        self.assertEqual(receipt["counts"]["selected_signals_influenced"], 3)
        self.assertEqual(specs[1]["stages"][-1]["count"], 1)

    def test_reaction_feedback_and_radar_reader_states_are_explicit(self) -> None:
        common = {"run_id": self.run_id, **self.sidecar["reporting_period"]}
        empty = _reaction_visual(
            self.reaction,
            selected_reaction_count=0,
            common=common,
            manifest_ref=f"manifest:{self.run_id}",
        )
        available_receipt = copy.deepcopy(self.reaction)
        available_receipt["status"] = "effects_applied"
        available_receipt["counts"] = {
            **available_receipt["counts"],
            "personal_reaction_events_detected": 2,
            "posts_resolved": 2,
            "unique_atoms_linked": 2,
            "unique_compatibility_threads_linked": 1,
        }
        available = _reaction_visual(
            available_receipt,
            selected_reaction_count=1,
            common=common,
            manifest_ref=f"manifest:{self.run_id}",
        )
        partial_receipt = copy.deepcopy(available_receipt)
        partial_receipt["snapshot_status"] = "partial"
        partial_receipt["status"] = "partial"
        unavailable = _reaction_visual(
            partial_receipt,
            selected_reaction_count=0,
            common=common,
            manifest_ref=f"manifest:{self.run_id}",
        )

        self.assertEqual(empty["data_status"], "empty")
        self.assertEqual(available["data_status"], "available")
        self.assertEqual(available["stages"][-1]["count"], 1)
        self.assertEqual(unavailable["data_status"], "unavailable")
        self.assertEqual(unavailable["snapshot_status"], "failed")

        feedback_html = _render_feedback_effect(
            {
                "confirmed_events_considered": 2,
                "applied_changes": [
                    {"reader_summary_ru": "Уточнено основное действие недели."}
                ],
                "unchanged": [
                    {"reader_summary_ru": "Приоритет сигнала оставлен без изменения."}
                ],
                "requires_code_or_config": [],
            }
        )
        self.assertIn("Рассмотрено подтверждённых событий: 2", feedback_html)
        self.assertIn("Уточнено основное действие недели", feedback_html)

        no_candidate = _render_radar_context({"reader_state": "no_candidate"})
        disabled = _render_radar_context({"reader_state": "disabled"})
        unavailable_radar = _render_radar_context({"reader_state": "invalid"})
        self.assertEqual(no_candidate, "")
        self.assertEqual(disabled, "")
        self.assertEqual(unavailable_radar, "")

    def test_focused_experiment_radar_preserves_bounded_permission(self) -> None:
        radar = copy.deepcopy(self.radar)
        radar["dossier_status"] = "focused_experiment"
        radar["reader_decision"] = "investigate"
        radar["decision_reason_ru"] = (
            "Radar разрешил только ограниченный проверочный эксперимент; "
            "полная сборка не разрешена."
        )
        spec = _radar_visual(
            radar,
            common={"run_id": self.run_id, **self.sidecar["reporting_period"]},
            manifest_ref=f"manifest:{self.run_id}",
        )

        self.assertEqual(spec["dossier_status"], "focused_experiment")
        reader_gate = next(
            gate for gate in spec["gates"] if gate["key"] == "reader_decision"
        )
        self.assertEqual(reader_gate["status"], "pass")

    def test_reader_visible_internal_refs_fail_closed(self) -> None:
        payload = copy.deepcopy(self.sidecar)
        payload["weekly_thesis"]["title"] += " signal:internal-id"
        payload["content_metrics"]["visible_word_count"] = visible_word_count(
            _render_document(payload)
        )

        with self.assertRaisesRegex(
            WeeklyIntelligenceBriefV2ValidationError,
            "reader-visible copy exposes an internal token",
        ):
            validate_weekly_intelligence_brief_v2(
                payload,
                manifest=self.manifest,
            )

    def test_equal_reaction_effects_follow_editorial_source_order(self) -> None:
        receipt = {
            "influenced_items": [
                {
                    "surface_item_ref": "thread:second",
                    "effect": "rank_changed",
                    "reader_reason_ru": "Вторая тема пришла первой в receipt.",
                },
                {
                    "surface_item_ref": "thread:first",
                    "effect": "rank_changed",
                    "reader_reason_ru": "Первая тема главнее в редакционном пакете.",
                },
            ],
            "linked_only_items": [],
        }

        effect = _reaction_effect_for_candidate(
            receipt,
            ["idea_thread:first", "idea_thread:second"],
        )

        self.assertEqual(effect["source_surface_item_ref"], "thread:first")
        self.assertEqual(
            effect["reader_reason_ru"],
            "Первая тема главнее в редакционном пакете.",
        )

    def test_missing_primary_is_explicit_partial_without_invented_action(self) -> None:
        model_output = _valid_model_output(self.package, signal_count=3)
        signal_refs = [item["signal_id"] for item in model_output["signals"]]
        model_output["signals"][0]["decision"] = "study"
        model_output["signals"][1]["decision"] = "watch"
        model_output["signals"][2]["decision"] = "ignore"
        model_output["decision_matrix"] = {
            "act": [],
            "study": [signal_refs[0]],
            "watch": [signal_refs[1]],
            "ignore": [signal_refs[2]],
        }
        model_output["project_actions"] = []
        editorial = synthesize_editorial_intelligence(
            self.package,
            model=MODEL,
            completion=lambda **_kwargs: _receipt(
                json.dumps(model_output, ensure_ascii=False)
            ),
            generated_at=self.manifest["generated_at"],
        )
        root = self.fixture.root / "partial-preview"
        sidecar = build_weekly_intelligence_brief_v2(
            manifest=self.manifest,
            manifest_path=self.manifest_path.resolve(),
            editorial_artifact=editorial,
            editorial_input_package=self.package,
            reaction_effect=self.reaction,
            project_intelligence=self.project,
            project_descriptors=self.project_descriptors,
            mvp_radar=self.radar,
            source_artifacts=self.sidecar["source_artifacts"],
            artifact_paths={
                "html": str((root / BRIEF_V2_HTML_FILENAME).resolve()),
                "json": str((root / BRIEF_V2_JSON_FILENAME).resolve()),
                "source_catalog": str(
                    (root / BRIEF_V2_SOURCE_CATALOG_FILENAME).resolve()
                ),
            },
            compatibility_atlas_path=self.run_result.atlas_html_path,
        )

        self.assertEqual(sidecar["run_status"], "partial")
        self.assertTrue(sidecar["partial"])
        self.assertIsNone(sidecar["actions"]["primary"])
        self.assertEqual(sidecar["actions"]["secondary"], [])
        self.assertEqual(sidecar["visual_specs"][0]["data_status"], "unavailable")
        self.assertIn("основное действие", " ".join(sidecar["partial_reasons_ru"]).lower())

    def test_missing_defer_is_explicit_partial(self) -> None:
        model_output = _valid_model_output(self.package, signal_count=3)
        refs = [item["signal_id"] for item in model_output["signals"]]
        model_output["signals"][0]["decision"] = "act"
        model_output["signals"][1]["decision"] = "watch"
        model_output["signals"][2]["decision"] = "watch"
        model_output["decision_matrix"] = {
            "act": [refs[0]],
            "study": [],
            "watch": [refs[1], refs[2]],
            "ignore": [],
        }
        model_output["project_actions"] = []
        editorial = synthesize_editorial_intelligence(
            self.package,
            model=MODEL,
            completion=lambda **_kwargs: _receipt(
                json.dumps(model_output, ensure_ascii=False)
            ),
            generated_at=self.manifest["generated_at"],
        )
        root = self.fixture.root / "missing-defer-preview"

        sidecar = build_weekly_intelligence_brief_v2(
            manifest=self.manifest,
            manifest_path=self.manifest_path.resolve(),
            editorial_artifact=editorial,
            editorial_input_package=self.package,
            reaction_effect=self.reaction,
            project_intelligence=self.project,
            project_descriptors=self.project_descriptors,
            mvp_radar=self.radar,
            source_artifacts=self.sidecar["source_artifacts"],
            artifact_paths={
                "html": str((root / BRIEF_V2_HTML_FILENAME).resolve()),
                "json": str((root / BRIEF_V2_JSON_FILENAME).resolve()),
                "source_catalog": str(
                    (root / BRIEF_V2_SOURCE_CATALOG_FILENAME).resolve()
                ),
            },
            compatibility_atlas_path=self.run_result.atlas_html_path,
        )

        self.assertTrue(sidecar["partial"])
        self.assertEqual(sidecar["run_status"], "partial")
        self.assertIn("отложить", " ".join(sidecar["partial_reasons_ru"]).lower())
        self.assertEqual(sidecar["visual_specs"][0]["data_status"], "unavailable")

    def test_bound_loader_rejects_coordinated_derived_projection_tamper(self) -> None:
        path = Path(self.summary.json_path)
        original = path.read_bytes()
        try:
            payload = copy.deepcopy(self.sidecar)
            payload["actions"]["primary"]["title"] = "Подменённое действие читателя"
            path.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(
                (WeeklyIntelligenceBriefV2ArtifactError, WeeklyIntelligenceBriefV2ValidationError)
            ):
                load_manifest_bound_weekly_intelligence_brief_v2(
                    path,
                    expected_manifest_path=self.manifest_path,
                    allowed_source_roots=(self.fixture.root,),
                )
        finally:
            path.write_bytes(original)

    def test_bound_loader_rejects_source_catalog_tamper(self) -> None:
        path = Path(self.summary.source_catalog_path)
        original = path.read_bytes()
        try:
            payload = json.loads(original)
            payload["editorial_input_package"]["signal_candidates"][0][
                "reaction_effect"
            ]["effect"] = "selection_changed"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(WeeklyIntelligenceBriefV2ArtifactError):
                load_manifest_bound_weekly_intelligence_brief_v2(
                    self.summary.json_path,
                    expected_manifest_path=self.manifest_path,
                    allowed_source_roots=(self.fixture.root,),
                )
        finally:
            path.write_bytes(original)

    def test_bound_loader_rejects_manifest_alias_duplicate_keys_and_html_alias(self) -> None:
        manifest_alias = self.manifest_path.with_name("manifest-copy.json")
        manifest_original = self.manifest_path.read_bytes()
        sidecar_path = Path(self.summary.json_path)
        sidecar_original = sidecar_path.read_bytes()
        html_alias = Path(self.summary.html_path).with_name("alternate.html")
        manifest_symlink = self.manifest_path.with_name("manifest-symlink.json")
        try:
            manifest_alias.write_bytes(manifest_original)
            with self.assertRaises(WeeklyIntelligenceBriefV2ArtifactError):
                load_manifest_bound_weekly_intelligence_brief_v2(
                    self.summary.json_path,
                    expected_manifest_path=manifest_alias,
                    allowed_source_roots=(self.fixture.root,),
                )

            manifest_symlink.symlink_to(self.manifest_path)
            with self.assertRaisesRegex(
                WeeklyIntelligenceBriefV2ArtifactError,
                "caller-selected canonical manifest",
            ):
                load_manifest_bound_weekly_intelligence_brief_v2(
                    self.summary.json_path,
                    expected_manifest_path=manifest_symlink,
                    allowed_source_roots=(self.fixture.root,),
                )

            duplicate = manifest_original.replace(
                b'  "schema_version": "weekly_run_manifest.v1",\n',
                (
                    b'  "schema_version": "weekly_run_manifest.v1",\n'
                    b'  "schema_version": "weekly_run_manifest.v1",\n'
                ),
                1,
            )
            self.assertNotEqual(duplicate, manifest_original)
            self.manifest_path.write_bytes(duplicate)
            with self.assertRaisesRegex(
                WeeklyIntelligenceBriefV2ArtifactError,
                "duplicate JSON key",
            ):
                load_manifest_bound_weekly_intelligence_brief_v2(
                    self.summary.json_path,
                    expected_manifest_path=self.manifest_path,
                    allowed_source_roots=(self.fixture.root,),
                )
            self.manifest_path.write_bytes(manifest_original)

            html_alias.write_bytes(Path(self.summary.html_path).read_bytes())
            payload = json.loads(sidecar_original)
            payload["artifact_paths"]["html"] = str(html_alias.resolve())
            sidecar_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                WeeklyIntelligenceBriefV2ArtifactError,
                "noncanonical artifact path",
            ):
                load_manifest_bound_weekly_intelligence_brief_v2(
                    sidecar_path,
                    expected_manifest_path=self.manifest_path,
                    allowed_source_roots=(self.fixture.root,),
                )
        finally:
            self.manifest_path.write_bytes(manifest_original)
            sidecar_path.write_bytes(sidecar_original)
            manifest_alias.unlink(missing_ok=True)
            manifest_symlink.unlink(missing_ok=True)
            html_alias.unlink(missing_ok=True)

    def test_generation_rejects_symlinked_output_root_and_publishes_private_files(self) -> None:
        for artifact in (
            self.summary.html_path,
            self.summary.json_path,
            self.summary.source_catalog_path,
        ):
            self.assertEqual(stat.S_IMODE(Path(artifact).stat().st_mode), 0o600)

        requested = self.fixture.root / "symlinked-output"
        outside = self.fixture.root / "outside-output" / BRIEF_V2_DIRECTORY
        requested.mkdir()
        outside.mkdir(parents=True)
        (requested / BRIEF_V2_DIRECTORY).symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(
            WeeklyIntelligenceBriefV2ArtifactError,
            "symlink|canonical",
        ):
            generate_weekly_intelligence_brief_v2_artifact(
                manifest_path=self.manifest_path,
                editorial_artifact_path=self.editorial_path,
                editorial_input_package=self.package,
                project_intelligence_path=self.project_path,
                project_descriptors=self.project_descriptors,
                output_root=requested,
                allowed_source_roots=(self.fixture.root,),
            )

        ancestor_target = self.fixture.root / "ancestor-output-target"
        ancestor_target.mkdir()
        ancestor_alias = self.fixture.root / "ancestor-output-alias"
        ancestor_alias.symlink_to(ancestor_target, target_is_directory=True)
        with self.assertRaisesRegex(
            WeeklyIntelligenceBriefV2ArtifactError,
            "canonical",
        ):
            generate_weekly_intelligence_brief_v2_artifact(
                manifest_path=self.manifest_path,
                editorial_artifact_path=self.editorial_path,
                editorial_input_package=self.package,
                project_intelligence_path=self.project_path,
                project_descriptors=self.project_descriptors,
                output_root=ancestor_alias / "nested",
                allowed_source_roots=(self.fixture.root,),
            )
        self.assertFalse((ancestor_target / "nested").exists())
        self.assertEqual(list(outside.iterdir()), [])

        requested_leaf = self.fixture.root / "symlinked-output-leaf"
        requested_leaf.symlink_to(
            self.fixture.root / "outside-output",
            target_is_directory=True,
        )
        with self.assertRaisesRegex(
            WeeklyIntelligenceBriefV2ArtifactError,
            "canonical",
        ):
            generate_weekly_intelligence_brief_v2_artifact(
                manifest_path=self.manifest_path,
                editorial_artifact_path=self.editorial_path,
                editorial_input_package=self.package,
                project_intelligence_path=self.project_path,
                project_descriptors=self.project_descriptors,
                output_root=requested_leaf,
                allowed_source_roots=(self.fixture.root,),
            )

    def test_bound_loader_rejects_public_package_permissions(self) -> None:
        path = Path(self.summary.html_path)
        original_mode = stat.S_IMODE(path.stat().st_mode)
        try:
            path.chmod(0o644)
            with self.assertRaisesRegex(
                WeeklyIntelligenceBriefV2ArtifactError,
                "not private",
            ):
                load_manifest_bound_weekly_intelligence_brief_v2(
                    self.summary.json_path,
                    expected_manifest_path=self.manifest_path,
                    allowed_source_roots=(self.fixture.root,),
                )
        finally:
            path.chmod(original_mode)

    def test_finder_rejects_symlinked_v2_root(self) -> None:
        requested = self.fixture.root / "finder-symlink-output"
        requested.mkdir()
        (requested / BRIEF_V2_DIRECTORY).symlink_to(
            self.fixture.root / BRIEF_V2_DIRECTORY,
            target_is_directory=True,
        )

        with self.assertRaises(WeeklyIntelligenceBriefV2ArtifactError):
            find_manifest_bound_weekly_intelligence_brief_v2(
                output_root=requested,
                run_id=self.run_id,
                expected_manifest_path=self.manifest_path,
                allowed_source_roots=(self.fixture.root,),
            )

        ancestor_target = self.fixture.root / "finder-ancestor-target"
        ancestor_target.mkdir()
        ancestor_alias = self.fixture.root / "finder-ancestor-alias"
        ancestor_alias.symlink_to(ancestor_target, target_is_directory=True)
        with self.assertRaisesRegex(
            WeeklyIntelligenceBriefV2ArtifactError,
            "canonical",
        ):
            find_manifest_bound_weekly_intelligence_brief_v2(
                output_root=ancestor_alias / "nested",
                run_id=self.run_id,
                expected_manifest_path=self.manifest_path,
                allowed_source_roots=(self.fixture.root,),
            )

    def test_finder_rejects_incomplete_or_dangling_exact_run_package(self) -> None:
        requested = self.fixture.root / "finder-incomplete-output"
        run_directory = requested / BRIEF_V2_DIRECTORY / self.run_id
        run_directory.mkdir(parents=True)

        with self.assertRaisesRegex(
            WeeklyIntelligenceBriefV2ArtifactError,
            "incomplete run package",
        ):
            find_manifest_bound_weekly_intelligence_brief_v2(
                output_root=requested,
                run_id=self.run_id,
                expected_manifest_path=self.manifest_path,
                allowed_source_roots=(self.fixture.root,),
            )

        (run_directory / BRIEF_V2_JSON_FILENAME).symlink_to(
            run_directory / "missing-preview.json"
        )
        with self.assertRaisesRegex(
            WeeklyIntelligenceBriefV2ArtifactError,
            "symlink component",
        ):
            find_manifest_bound_weekly_intelligence_brief_v2(
                output_root=requested,
                run_id=self.run_id,
                expected_manifest_path=self.manifest_path,
                allowed_source_roots=(self.fixture.root,),
            )

    def test_generation_rejects_manifest_outside_its_run_directory_before_publish(self) -> None:
        wrong_run_directory = self.fixture.root / "wrong-manifest-parent"
        wrong_run_directory.mkdir()
        copied_manifest = wrong_run_directory / "manifest.json"
        copied_manifest.write_bytes(self.manifest_path.read_bytes())
        output_root = self.fixture.root / "wrong-manifest-output"

        with self.assertRaisesRegex(
            WeeklyIntelligenceBriefV2ArtifactError,
            "run identity",
        ):
            generate_weekly_intelligence_brief_v2_artifact(
                manifest_path=copied_manifest,
                editorial_artifact_path=self.editorial_path,
                editorial_input_package=self.package,
                project_intelligence_path=self.project_path,
                project_descriptors=self.project_descriptors,
                output_root=output_root,
                allowed_source_roots=(self.fixture.root,),
            )
        self.assertFalse((output_root / BRIEF_V2_DIRECTORY).exists())

    def test_strict_reader_bounds_and_rejects_overflow_and_deep_json(self) -> None:
        cases = {
            "overflow.json": b'{"value":1e999}',
            "deep.json": ("[" * 1_500 + "0" + "]" * 1_500).encode("utf-8"),
            "oversized.json": b" " * 33,
        }
        for filename, payload in cases.items():
            with self.subTest(filename=filename):
                path = self.fixture.root / filename
                path.write_bytes(payload)
                maximum = 32 if filename == "oversized.json" else 8_000_000
                with self.assertRaises(WeeklyIntelligenceBriefV2ArtifactError):
                    _read_strict_json_value(
                        path,
                        label=filename,
                        maximum=maximum,
                    )

    def test_generation_strictly_rejects_duplicate_bound_reaction_snapshot(self) -> None:
        manifest_original = self.manifest_path.read_bytes()
        manifest = json.loads(manifest_original)
        relative = manifest["stages"]["reaction_sync"]["artifact_refs"][
            "snapshot_path"
        ]
        snapshot_path = self.manifest_path.parent / relative
        snapshot_original = snapshot_path.read_bytes()
        snapshot = json.loads(snapshot_original)
        duplicate = (
            b'{"schema_version":'
            + json.dumps(snapshot["schema_version"]).encode("utf-8")
            + b","
            + snapshot_original[1:]
        )
        try:
            snapshot_path.write_bytes(duplicate)
            manifest["stages"]["reaction_sync"]["checksums"][
                "snapshot_path"
            ] = sha256_file(snapshot_path)
            self.manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                WeeklyIntelligenceBriefV2ArtifactError,
                "duplicate JSON key",
            ):
                generate_weekly_intelligence_brief_v2_artifact(
                    manifest_path=self.manifest_path,
                    editorial_artifact_path=self.editorial_path,
                    editorial_input_package=self.package,
                    project_intelligence_path=self.project_path,
                    project_descriptors=self.project_descriptors,
                    output_root=self.fixture.root / "strict-reaction-output",
                    allowed_source_roots=(self.fixture.root,),
                )
        finally:
            snapshot_path.write_bytes(snapshot_original)
            self.manifest_path.write_bytes(manifest_original)

    def test_generation_rejects_wrong_run_bound_reaction_snapshot(self) -> None:
        manifest_original = self.manifest_path.read_bytes()
        manifest = json.loads(manifest_original)
        relative = manifest["stages"]["reaction_sync"]["artifact_refs"][
            "snapshot_path"
        ]
        snapshot_path = self.manifest_path.parent / relative
        snapshot_original = snapshot_path.read_bytes()
        snapshot = json.loads(snapshot_original)
        snapshot["run_id"] = "foreign-reaction-run"
        try:
            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False),
                encoding="utf-8",
            )
            manifest["stages"]["reaction_sync"]["checksums"][
                "snapshot_path"
            ] = sha256_file(snapshot_path)
            self.manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                WeeklyRunManifestError,
                "reaction snapshot identity mismatch: run_id",
            ):
                generate_weekly_intelligence_brief_v2_artifact(
                    manifest_path=self.manifest_path,
                    editorial_artifact_path=self.editorial_path,
                    editorial_input_package=self.package,
                    project_intelligence_path=self.project_path,
                    project_descriptors=self.project_descriptors,
                    output_root=self.fixture.root / "wrong-reaction-output",
                    allowed_source_roots=(self.fixture.root,),
                )
        finally:
            snapshot_path.write_bytes(snapshot_original)
            self.manifest_path.write_bytes(manifest_original)

    def test_validator_rejects_critical_word_budget(self) -> None:
        payload = copy.deepcopy(self.sidecar)
        payload["signals"][0]["what_happened"] = " ".join(
            ["Проверяемое изменение"] * 140
        )
        html = _render_document(payload)
        count = visible_word_count(html)
        self.assertGreater(count, 1_100)
        payload["content_metrics"]["visible_word_count"] = count
        payload["content_metrics"]["word_budget_status"] = "critical"
        with self.assertRaisesRegex(
            WeeklyIntelligenceBriefV2ValidationError,
            "hard visible-word limit",
        ):
            validate_weekly_intelligence_brief_v2(payload, manifest=self.manifest)

    def test_finder_is_exact_and_rejects_unsafe_run_ids(self) -> None:
        found = find_manifest_bound_weekly_intelligence_brief_v2(
            output_root=self.fixture.root,
            run_id=self.run_id,
            expected_manifest_path=self.manifest_path,
            allowed_source_roots=(self.fixture.root,),
        )
        self.assertEqual(found, self.sidecar)
        self.assertIsNone(
            find_manifest_bound_weekly_intelligence_brief_v2(
                output_root=self.fixture.root,
                run_id="tra-weekly-2026-W28-neighbor-run",
                expected_manifest_path=self.manifest_path,
                allowed_source_roots=(self.fixture.root,),
            )
        )
        for value in ("../escape", "/tmp/escape", "bad/id", "a" * 129):
            with self.subTest(run_id=value), self.assertRaises(
                WeeklyIntelligenceBriefV2ArtifactError
            ):
                find_manifest_bound_weekly_intelligence_brief_v2(
                    output_root=self.fixture.root,
                    run_id=value,
                    expected_manifest_path=self.manifest_path,
                    allowed_source_roots=(self.fixture.root,),
                )

    def test_v2_files_are_additive_and_do_not_replace_v1_paths(self) -> None:
        output_dir = Path(self.summary.json_path).parent
        self.assertEqual(output_dir.parent.name, BRIEF_V2_DIRECTORY)
        self.assertTrue(Path(self.run_result.weekly_brief_json_path).is_file())
        self.assertNotEqual(
            Path(self.run_result.weekly_brief_json_path).resolve(),
            Path(self.summary.json_path).resolve(),
        )
        self.assertEqual(
            set(path.name for path in output_dir.iterdir()),
            {
                BRIEF_V2_HTML_FILENAME,
                BRIEF_V2_JSON_FILENAME,
                BRIEF_V2_SOURCE_CATALOG_FILENAME,
            },
        )
        self.assertEqual(self.sidecar["navigation"]["atlas_v2"]["status"], "unavailable")
        self.assertEqual(
            self.sidecar["navigation"]["audit_explorer"]["status"],
            "unavailable",
        )


if __name__ == "__main__":
    unittest.main()
