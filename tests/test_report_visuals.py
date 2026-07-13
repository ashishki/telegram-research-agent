"""Focused contract tests for the shared Report V2 visual component system."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import unittest

from output.report_visuals import (
    REPORT_VISUALS_CONTRACT_VERSION,
    SUPPORTED_VISUAL_SCHEMAS,
    ReportVisualValidationError,
    render_report_visual,
    render_visual_document,
    report_visual_styles,
    validate_report_visual,
)


def _common(
    component: str, status: str = "available", *, partial: bool = False
) -> dict:
    spec = {
        "schema_version": f"report_visual.{component}.v1",
        "component_id": component.replace("_", "-"),
        "title_ru": f"Проверка компонента {component}",
        "summary_ru": "Показывает проверенные данные завершенного периода.",
        "run_id": "tra-weekly-2026-W28-20260713T070252Z",
        "reporting_week": "2026-W28",
        "analysis_period_start": "2026-07-06T00:00:00Z",
        "analysis_period_end": "2026-07-13T00:00:00Z",
        "data_status": status,
        "source_refs": [] if status == "unavailable" else [f"manifest:{component}"],
        "data_note_ru": "Данные взяты из проверенного снимка; вывод ограничен этим периодом.",
    }
    if status == "unavailable":
        spec["state_reason_ru"] = "Расчет upstream-компонента не завершился успешно."
    elif status == "stale":
        spec.update(
            {
                "state_reason_ru": "Показаны данные предыдущего запуска, а не текущего.",
                "stale_from_run_id": "tra-weekly-2026-W27-20260706T070252Z",
                "stale_from_period": "2026-W27",
            }
        )
    if partial:
        spec["partial_reasons_ru"] = ["Одна часть связей рассчитана не полностью."]
    return spec


def build_decision_matrix(status: str = "available", *, partial: bool = False) -> dict:
    spec = _common("decision_matrix", status, partial=partial)
    spec["items"] = [
        {
            "decision": "watch",
            "label_ru": "Наблюдать за повторным сигналом",
            "signal_ref": "signal:watch",
            "confidence": "medium",
            "evidence_maturity": "repeated_signal",
            "emphasis": "none",
        },
        {
            "decision": "ignore",
            "label_ru": "Явно отложить слабую гипотезу",
            "signal_ref": "signal:defer",
            "confidence": "low",
            "evidence_maturity": "single_source",
            "emphasis": "explicit_defer",
        },
        {
            "decision": "act",
            "label_ru": "Проверить контракт периода",
            "signal_ref": "signal:act",
            "confidence": "high",
            "evidence_maturity": "decision_grade",
            "emphasis": "primary_action",
        },
        {
            "decision": "study",
            "label_ru": "Изучить независимое подтверждение",
            "signal_ref": "signal:study",
            "confidence": "medium",
            "evidence_maturity": "multi_channel",
            "emphasis": "none",
        },
    ]
    if status in {"empty", "unavailable"}:
        spec["items"] = []
    return spec


def build_reaction_funnel(status: str = "available", *, partial: bool = False) -> dict:
    spec = _common("reaction_funnel", status, partial=partial)
    spec.update(
        {
            "snapshot_status": "partial" if partial else "complete",
            "stages": [
                {"key": "detected", "label_ru": "Реакции", "count": 8},
                {"key": "posts_resolved", "label_ru": "Посты найдены", "count": 4},
                {"key": "atoms_linked", "label_ru": "Связаны с атомами", "count": 7},
                {"key": "threads_linked", "label_ru": "Связаны с темами", "count": 5},
                {
                    "key": "signals_selected",
                    "label_ru": "Повлияли на сигналы",
                    "count": 2,
                },
            ],
            "unconsumed_reasons": [
                "Один пост не прошел разрешение ссылки.",
                "Одна реакция относится к предыдущему периоду.",
            ],
        }
    )
    if status in {"empty", "unavailable"}:
        spec["stages"] = []
        spec["unconsumed_reasons"] = []
    if status == "unavailable":
        spec["snapshot_status"] = "failed"
    return spec


def build_radar_gate(status: str = "available", *, partial: bool = False) -> dict:
    spec = _common("radar_gate", status, partial=partial)
    spec.update(
        {
            "snapshot_status": "complete",
            "candidate_name": "Проверка голосового рабочего процесса",
            "dossier_status": "investigate",
            "reader_decision": "investigate",
            "gates": [
                {
                    "key": "operator_fit",
                    "status": "missing",
                    "reason_ru": "Не хватает проверки на реальной задаче.",
                },
                {
                    "key": "kir_evidence",
                    "status": "pass",
                    "reason_ru": "Есть независимое подтверждение проблемы.",
                },
            ],
            "candidate_evidence_count": 2,
            "context_only_count": 4,
            "missing_evidence": [
                "Нужен замер времени оператора.",
                "Нужна повторная проверка сценария.",
            ],
            "next_validation_ru": "Провести проверку на двух реальных задачах.",
            "kill_criteria_ru": "Остановить, если экономия времени не подтверждается.",
        }
    )
    if status in {"empty", "unavailable"}:
        spec.update(
            {
                "candidate_name": None,
                "dossier_status": "unavailable",
                "reader_decision": "unavailable",
                "gates": [],
                "candidate_evidence_count": 0,
                "context_only_count": 0,
                "missing_evidence": [],
                "next_validation_ru": "",
                "kill_criteria_ru": "",
            }
        )
    if status == "unavailable":
        spec["snapshot_status"] = "failed"
    return spec


def _project_item(name: str, signal: str, status: str) -> dict:
    return {
        "project_name": name,
        "signal_ref": signal,
        "signal_label_ru": "Проверяемый сигнал о происхождении решения",
        "suggested_change_ru": "Показать происхождение решения в отчете.",
        "affected_component": "Weekly Brief",
        "likely_files": ["tests/test_reader.py", "src/output/reader.py"],
        "effort": "Около двух часов",
        "confidence": "high" if status == "confirmed" else "medium",
        "acceptance_criteria": [
            "Читатель видит ограничение данных.",
            "Отчет сохраняет проверяемую ссылку.",
        ],
        "risk_ru": "Не представить корреляцию как доказанную причинность.",
        "evidence_refs": [f"evidence:{signal}"],
        "status": status,
    }


def build_project_impact(status: str = "available", *, partial: bool = False) -> dict:
    spec = _common("project_impact", status, partial=partial)
    spec["items"] = [
        _project_item("Второй проект", "signal:watch-project", "watch"),
        _project_item("Основной проект", "signal:confirmed-project", "confirmed"),
    ]
    if status in {"empty", "unavailable"}:
        spec["items"] = []
    return spec


def _graph_node(index: int, *, priority: int | None = None) -> dict:
    return {
        "canonical_thread_id": f"private-thread-token-{index:02d}",
        "title_ru": f"Каноническая тема номер {index}",
        "status": "growing" if index % 2 else "watch",
        "evidence_volume": index + 2,
        "evidence_maturity": "multi_channel" if index % 2 else "repeated_signal",
        "operator_interest_score": round((index % 5) / 5, 2),
        "display_priority": index if priority is None else priority,
    }


def build_knowledge_graph(status: str = "available", *, partial: bool = False) -> dict:
    spec = _common("knowledge_graph", status, partial=partial)
    spec.update(
        {
            "encoding": {
                "node_size": "evidence_volume",
                "node_border": "evidence_maturity",
                "node_accent": "operator_interest",
            },
            "audit_explorer_path": "audit/knowledge-audit-explorer.html",
            "nodes": [_graph_node(2), _graph_node(0), _graph_node(1)],
            "edges": [
                {
                    "source_thread_id": "private-thread-token-00",
                    "target_thread_id": "private-thread-token-01",
                    "relation": "supports",
                    "weight": 2,
                    "evidence_refs": ["evidence:edge-01"],
                },
                {
                    "source_thread_id": "private-thread-token-02",
                    "target_thread_id": "private-thread-token-01",
                    "relation": "contradicts",
                    "weight": 1,
                    "evidence_refs": ["evidence:edge-21"],
                },
            ],
        }
    )
    if status in {"empty", "unavailable"}:
        spec["nodes"] = []
        spec["edges"] = []
    return spec


def build_thread_timeline(status: str = "available", *, partial: bool = False) -> dict:
    spec = _common("thread_timeline", status, partial=partial)
    spec.update(
        {
            "weeks": [
                "2026-W17",
                "2026-W18",
                "2026-W19",
                "2026-W20",
                "2026-W21",
                "2026-W22",
                "2026-W23",
                "2026-W24",
                "2026-W25",
                "2026-W26",
                "2026-W27",
                "2026-W28",
            ],
            "series": [
                {
                    "canonical_thread_id": "thread-b",
                    "title_ru": "Вторая динамическая тема",
                    "momentum": [
                        0.1,
                        0.2,
                        0.3,
                        0.4,
                        0.5,
                        0.6,
                        0.7,
                        0.8,
                        0.9,
                        1,
                        1.1,
                        1.2,
                    ],
                    "evidence_count": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                    "events": [],
                },
                {
                    "canonical_thread_id": "thread-a",
                    "title_ru": "Первая динамическая тема",
                    "momentum": [
                        0,
                        None,
                        0.1,
                        0.1,
                        0.2,
                        0.2,
                        0.2,
                        0.3,
                        0.3,
                        0.3,
                        0.4,
                        0.4,
                    ],
                    "evidence_count": [0, None, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4],
                    "events": [
                        {
                            "week": "2026-W28",
                            "type": "milestone",
                            "label_ru": "Получено первичное подтверждение.",
                        },
                        {
                            "week": "2026-W26",
                            "type": "contradiction",
                            "label_ru": "Зафиксировано раннее противоречие.",
                        },
                    ],
                },
            ],
        }
    )
    if status == "empty":
        spec["series"] = []
        spec["weeks"] = spec["weeks"][-4:]
    elif status == "stale":
        spec["weeks"] = [
            "2026-W16",
            "2026-W17",
            "2026-W18",
            "2026-W19",
            "2026-W20",
            "2026-W21",
            "2026-W22",
            "2026-W23",
            "2026-W24",
            "2026-W25",
            "2026-W26",
            "2026-W27",
        ]
        for series in spec["series"]:
            for event in series["events"]:
                if event["week"] == "2026-W28":
                    event["week"] = "2026-W27"
    elif status == "unavailable":
        spec["weeks"] = []
        spec["series"] = []
    return spec


def build_source_thread_heatmap(
    status: str = "available", *, partial: bool = False
) -> dict:
    spec = _common("source_thread_heatmap", status, partial=partial)
    spec.update(
        {
            "value": "independent_support_count",
            "sources": [
                {
                    "source_id": "source-unclassified",
                    "label": "Источник без вклада",
                    "independence_group": "unknown-group",
                    "classification_status": "available",
                },
                {
                    "source_id": "source-known",
                    "label": "Проверенный источник",
                    "independence_group": "group-one",
                    "classification_status": "available",
                },
            ],
            "threads": [
                {"canonical_thread_id": "thread-b", "title_ru": "Вторая тема"},
                {"canonical_thread_id": "thread-a", "title_ru": "Первая тема"},
            ],
            "cells": [
                {
                    "source_id": "source-known",
                    "canonical_thread_id": "thread-a",
                    "mention_count": 4,
                    "independent_support_count": 1,
                    "evidence_refs": ["evidence:heat-a"],
                },
                {
                    "source_id": "source-known",
                    "canonical_thread_id": "thread-b",
                    "mention_count": 2,
                    "independent_support_count": 2,
                    "evidence_refs": ["evidence:heat-b"],
                },
            ],
        }
    )
    if status in {"empty", "unavailable"}:
        spec["sources"] = []
        spec["threads"] = []
        spec["cells"] = []
    return spec


_MATURITY_KEYS = (
    "single_source",
    "repeated_signal",
    "multi_channel",
    "primary_verified",
    "externally_corroborated",
    "decision_grade",
    "unknown",
)


def build_evidence_maturity(
    status: str = "available", *, partial: bool = False
) -> dict:
    spec = _common("evidence_maturity", status, partial=partial)
    labels = (
        "Один источник",
        "Повторяющийся сигнал",
        "Несколько независимых каналов",
        "Проверено первичным источником",
        "Подтверждено внешними данными",
        "Достаточно для решения",
        "Зрелость неизвестна",
    )
    counts = (2, 2, 1, 1, 1, 1, 1)
    spec["levels"] = [
        {"key": key, "label_ru": label, "count": count}
        for key, label, count in zip(_MATURITY_KEYS, labels, counts)
    ]
    spec["thread_count"] = sum(counts)
    if status in {"empty", "unavailable"}:
        spec["levels"] = []
        spec["thread_count"] = 0
    return spec


_LEARNING = (
    ("marked", "Отмечено", "reaction"),
    ("read", "Прочитано", "read_receipt"),
    ("understood", "Понято", "comprehension_check"),
    ("explained", "Объяснено", "explanation"),
    ("tried", "Испробовано", "trial"),
    ("implemented", "Внедрено", "implementation"),
    ("measured", "Измерено", "measurement"),
)


def build_learning_progression(
    status: str = "available", *, partial: bool = False
) -> dict:
    spec = _common("learning_progression", status, partial=partial)
    counts = (10, 8, 6, 4, 3, 2, 1)
    spec["stages"] = [
        {
            "key": key,
            "label_ru": label,
            "count": count,
            "observation_status": "confirmed",
            "confirmation_kind": kind,
            "evidence_refs": [f"evidence:learning-{key}"],
        }
        for (key, label, kind), count in zip(_LEARNING, counts)
    ]
    if status in {"empty", "unavailable"}:
        spec["stages"] = []
    return spec


def build_evidence_badge(status: str = "available", *, partial: bool = False) -> dict:
    spec = _common("evidence_badge", status, partial=partial)
    spec.update(
        {
            "confidence": "medium",
            "confidence_reason_ru": "Два независимых источника согласуются по сути.",
            "evidence_maturity": "multi_channel",
            "source_count": 3,
            "independent_source_count": 2,
        }
    )
    if status in {"empty", "unavailable"}:
        spec.update(
            {
                "confidence": None,
                "confidence_reason_ru": None,
                "evidence_maturity": None,
                "source_count": None,
                "independent_source_count": None,
            }
        )
    return spec


BUILDERS = {
    "decision_matrix": build_decision_matrix,
    "reaction_funnel": build_reaction_funnel,
    "radar_gate": build_radar_gate,
    "project_impact": build_project_impact,
    "knowledge_graph": build_knowledge_graph,
    "thread_timeline": build_thread_timeline,
    "source_thread_heatmap": build_source_thread_heatmap,
    "evidence_maturity": build_evidence_maturity,
    "learning_progression": build_learning_progression,
    "evidence_badge": build_evidence_badge,
}


class ReportVisualContractTests(unittest.TestCase):
    def assert_failed(self, spec: object, warning_fragment: str | None = None) -> None:
        result = render_report_visual(spec)  # type: ignore[arg-type]
        self.assertEqual(result.render_status, "failed")
        self.assertTrue(result.warnings)
        self.assertIn('role="alert"', result.html)
        self.assertIn("Ошибка схемы", result.html)
        self.assertNotIn("<svg", result.html)
        if warning_fragment:
            self.assertIn(warning_fragment, result.warnings[0])

    def test_catalog_dispatch_markers_and_serializable_receipt(self) -> None:
        self.assertEqual(REPORT_VISUALS_CONTRACT_VERSION, "report_visuals.v1")
        self.assertEqual(len(SUPPORTED_VISUAL_SCHEMAS), 10)
        self.assertEqual(
            set(BUILDERS),
            {
                schema.removeprefix("report_visual.").removesuffix(".v1")
                for schema in SUPPORTED_VISUAL_SCHEMAS
            },
        )

        for component, builder in BUILDERS.items():
            with self.subTest(component=component):
                spec = builder()
                self.assertEqual(validate_report_visual(spec), component)
                result = render_report_visual(spec)
                self.assertEqual(result.component_type, component)
                self.assertEqual(result.component_id, spec["component_id"])
                self.assertEqual(result.schema_version, spec["schema_version"])
                self.assertEqual(result.render_status, "complete")
                self.assertEqual(result.source_ref_count, 1)
                self.assertEqual(
                    set(result.as_dict()),
                    {
                        "html",
                        "component_id",
                        "component_type",
                        "schema_version",
                        "render_status",
                        "data_status",
                        "source_ref_count",
                        "warnings",
                    },
                )
                for marker in (
                    'data-irx-visual="true"',
                    f'data-component="{component}"',
                    f'data-component-id="{spec["component_id"]}"',
                    f'data-schema-version="{spec["schema_version"]}"',
                    'data-render-status="complete"',
                    'data-data-status="available"',
                    'data-source-ref-count="1"',
                ):
                    self.assertIn(marker, result.html)
                self.assertIn("Данные и ограничение", result.html)
                self.assertIn('aria-labelledby="', result.html)
                self.assertIn("<h2", result.html)

    def test_all_components_cover_available_empty_unavailable_stale_and_partial(
        self,
    ) -> None:
        expectations = {
            "available": ("complete", "available"),
            "empty": ("complete", "empty"),
            "unavailable": ("partial", "unavailable"),
            "stale": ("partial", "stale"),
        }
        for component, builder in BUILDERS.items():
            for state, (render_status, data_status) in expectations.items():
                with self.subTest(component=component, state=state):
                    result = render_report_visual(builder(state))
                    self.assertEqual(result.render_status, render_status)
                    self.assertEqual(result.data_status, data_status)
                    self.assertIn(f'data-data-status="{data_status}"', result.html)
                    self.assertIn(f'data-render-status="{render_status}"', result.html)
                    self.assertTrue(result.html.strip())
                    if state in {"unavailable", "stale"}:
                        self.assertTrue(result.warnings)
                    expected_role = (
                        "supporting" if component == "evidence_badge" else "data"
                    )
                    self.assertIn(f'data-visual-role="{expected_role}"', result.html)

            with self.subTest(component=component, state="partial"):
                result = render_report_visual(builder(partial=True))
                self.assertEqual(result.render_status, "partial")
                self.assertEqual(result.data_status, "available")
                self.assertTrue(result.warnings)
                self.assertIn("рассчитана не полностью", result.html)

    def test_missing_domain_field_fails_every_schema_without_blank_visual(self) -> None:
        domain_fields = {
            "decision_matrix": "items",
            "reaction_funnel": "stages",
            "radar_gate": "gates",
            "project_impact": "items",
            "knowledge_graph": "nodes",
            "thread_timeline": "series",
            "source_thread_heatmap": "cells",
            "evidence_maturity": "levels",
            "learning_progression": "stages",
            "evidence_badge": "confidence",
        }
        for component, field in domain_fields.items():
            with self.subTest(component=component):
                spec = BUILDERS[component]()
                del spec[field]
                with self.assertRaises(ReportVisualValidationError):
                    validate_report_visual(spec)
                self.assert_failed(spec, "отсутствуют поля")

    def test_unknown_schema_and_non_mapping_fail_safely(self) -> None:
        self.assert_failed(
            {"schema_version": "report_visual.future.v9"}, "неподдерживаемая"
        )
        self.assert_failed(["not", "a", "mapping"], "ожидался объект")
        result = render_report_visual(
            {"schema_version": "<unsafe>", "component_id": "BAD ID"}
        )
        self.assertEqual(result.component_id, "invalid-visual")
        self.assertNotIn("<unsafe>", result.html)
        self.assertIn("&lt;unsafe&gt;", result.html)

    def test_determinism_for_identical_and_reordered_unordered_inputs(self) -> None:
        for component, builder in BUILDERS.items():
            with self.subTest(component=component, mode="identical"):
                spec = builder()
                self.assertEqual(
                    render_report_visual(spec).html,
                    render_report_visual(deepcopy(spec)).html,
                )

        reorder_cases = {
            "decision_matrix": ("items",),
            "reaction_funnel": ("unconsumed_reasons",),
            "radar_gate": ("gates", "missing_evidence"),
            "project_impact": ("items",),
            "knowledge_graph": ("nodes", "edges"),
            "thread_timeline": ("series",),
            "source_thread_heatmap": ("sources", "threads", "cells"),
        }
        for component, fields in reorder_cases.items():
            with self.subTest(component=component, mode="reordered"):
                original = BUILDERS[component]()
                reordered = deepcopy(original)
                for field in fields:
                    reordered[field] = list(reversed(reordered[field]))
                if component == "project_impact":
                    for item in reordered["items"]:
                        item["likely_files"].reverse()
                        item["acceptance_criteria"].reverse()
                if component == "thread_timeline":
                    for series in reordered["series"]:
                        series["events"].reverse()
                self.assertEqual(
                    render_report_visual(original).html,
                    render_report_visual(reordered).html,
                )

        specs = [builder() for builder in BUILDERS.values()]
        self.assertEqual(
            render_visual_document(specs), render_visual_document(deepcopy(specs))
        )

    def test_escaping_safe_references_and_standalone_offline_document(self) -> None:
        spec = build_decision_matrix()
        spec["title_ru"] = 'Русский <script>alert("x")</script> заголовок'
        spec["summary_ru"] = 'Русское описание <img src=x onerror="boom">.'
        spec["data_note_ru"] = "Русские данные & ограничение <b>важно</b>."
        result = render_report_visual(spec)
        self.assertEqual(result.render_status, "complete")
        self.assertNotIn("<script", result.html.lower())
        self.assertNotIn("<img", result.html.lower())
        self.assertNotIn("<b>", result.html.lower())
        self.assertIn("&lt;script&gt;", result.html)
        self.assertIn("&lt;img", result.html)
        self.assertIn("&lt;b&gt;", result.html)

        for unsafe_ref in (
            "javascript:alert(1)",
            "../private/evidence",
            "/etc/passwd",
            "ftp://example.com/a",
            "mailto:x@example.com",
            "about:blank",
            "https://host:bad/x",
            "https://host:99999/x",
            "source://evil.example/private",
            "manifest://evil.example/x",
        ):
            with self.subTest(unsafe_ref=unsafe_ref):
                bad = build_decision_matrix()
                bad["source_refs"] = [unsafe_ref]
                self.assert_failed(bad)
        malformed_url = build_decision_matrix()
        malformed_url["source_refs"] = ["http://[bad"]
        self.assert_failed(malformed_url, "некорректная URL")

        document = render_visual_document([spec], title_ru="Русская галерея <проверка>")
        self.assertTrue(document.startswith('<!doctype html><html lang="ru">'))
        self.assertIn('http-equiv="Content-Security-Policy"', document)
        for directive in (
            "default-src &#x27;none&#x27;",
            "script-src &#x27;none&#x27;",
            "connect-src &#x27;none&#x27;",
            "object-src &#x27;none&#x27;",
        ):
            self.assertIn(directive, document)
        self.assertNotIn("<script", document.lower())
        self.assertNotRegex(document.lower(), r"(?:https?:)?//")
        self.assertNotIn("@import", document.lower())
        self.assertNotIn("url(", document.lower())

        css = report_visual_styles()
        self.assertIn("max-width:1440px", css)
        self.assertIn("@media (max-width:600px)", css)
        self.assertIn("@media print", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn("position:sticky", css)
        self.assertNotIn("linear-gradient", css)

    def test_svg_accessibility_and_semantic_alternatives(self) -> None:
        graph = render_report_visual(build_knowledge_graph()).html
        self.assertIn("<svg", graph)
        self.assertIn('viewBox="', graph)
        self.assertIn('role="img"', graph)
        self.assertIn("<title", graph)
        self.assertIn("<desc", graph)
        self.assertIn("<ol", graph)
        self.assertIn("Доказанные отношения", graph)

        timeline = render_report_visual(build_thread_timeline()).html
        self.assertIn('role="img"', timeline)
        self.assertIn("<title", timeline)
        self.assertIn("<desc", timeline)
        self.assertIn("<table", timeline)
        self.assertIn("Динамика", timeline)

        heatmap = render_report_visual(build_source_thread_heatmap()).html
        self.assertIn('<table class="irx-visual__heatmap">', heatmap)
        self.assertIn('scope="row"', heatmap)
        self.assertIn('scope="col"', heatmap)
        self.assertIn("Сводка по темам", heatmap)

    def test_graph_truncates_to_twelve_without_exposing_raw_thread_ids(self) -> None:
        spec = build_knowledge_graph()
        spec["nodes"] = [_graph_node(index) for index in range(13)]
        spec["edges"] = []
        result = render_report_visual(spec)
        self.assertEqual(result.render_status, "partial")
        self.assertTrue(result.warnings)
        self.assertIn("исключено: 1", result.html)
        self.assertEqual(result.html.count('role="group"'), 12)
        for node in spec["nodes"]:
            self.assertNotIn(node["canonical_thread_id"], result.html)

        empty = render_report_visual(build_knowledge_graph("empty"))
        self.assertIn("Открыть Audit Explorer", empty.html)
        self.assertIn('href="audit/knowledge-audit-explorer.html"', empty.html)

        unsafe = build_knowledge_graph()
        unsafe["audit_explorer_path"] = "../private/audit.html"
        self.assert_failed(unsafe, "родительские сегменты")

    def test_graph_layout_is_stable_under_priority_ties_and_cycles(self) -> None:
        spec = build_knowledge_graph()
        for node in spec["nodes"]:
            node["display_priority"] = 5
        spec["edges"].append(
            {
                "source_thread_id": "private-thread-token-01",
                "target_thread_id": "private-thread-token-00",
                "relation": "depends_on",
                "weight": 1,
                "evidence_refs": ["evidence:cycle-10"],
            }
        )
        reversed_spec = deepcopy(spec)
        reversed_spec["nodes"].reverse()
        reversed_spec["edges"].reverse()
        first = render_report_visual(spec)
        second = render_report_visual(reversed_spec)
        self.assertEqual(first.render_status, "complete")
        self.assertEqual(first.html, second.html)

        long_label = "Щ" * 100
        long_spec = build_knowledge_graph()
        long_spec["nodes"][0]["title_ru"] = long_label
        long_html = render_report_visual(long_spec).html
        svg_html = long_html.split("</svg>", 1)[0]
        visible_svg_labels = re.findall(r"<text[^>]*>(.*?)</text>", svg_html)
        self.assertNotIn(long_label, visible_svg_labels)
        self.assertIn('clip-path="url(#', svg_html)
        self.assertIn(long_label, long_html)

        huge = build_knowledge_graph()
        huge["nodes"][0]["evidence_volume"] = 10**10000
        self.assert_failed(huge, "не больше")

        overflow = build_knowledge_graph()
        overflow["nodes"][0]["operator_interest_score"] = 10**10000
        self.assert_failed(overflow, "вне допустимого диапазона")

    def test_timeline_distinguishes_missing_from_observed_zero(self) -> None:
        result = render_report_visual(build_thread_timeline())
        self.assertEqual(result.render_status, "complete")
        self.assertIn("разрыв линии", result.html)
        self.assertIn("наблюдаемый ноль", result.html)
        self.assertIn("нет данных", result.html)
        self.assertIn("<circle", result.html)
        self.assertGreaterEqual(result.html.count("<polyline"), 3)

        short = build_thread_timeline()
        short["weeks"] = short["weeks"][-3:]
        for series in short["series"]:
            series["momentum"] = series["momentum"][-3:]
            series["evidence_count"] = series["evidence_count"][-3:]
            series["events"] = [
                event for event in series["events"] if event["week"] in short["weeks"]
            ]
        self.assert_failed(short, "короче 12 недель")
        short["partial_reasons_ru"] = ["Доступны только три исторических снимка."]
        self.assertEqual(render_report_visual(short).render_status, "partial")

        all_null = build_thread_timeline()
        all_null["series"][0]["momentum"] = [None] * 12
        self.assert_failed(all_null, "без единого наблюдения")

    def test_reaction_lineage_allows_nonmonotonic_entities_but_not_more_posts_than_events(
        self,
    ) -> None:
        valid = build_reaction_funnel()
        self.assertGreater(valid["stages"][2]["count"], valid["stages"][1]["count"])
        rendered = render_report_visual(valid)
        self.assertEqual(rendered.render_status, "complete")
        self.assertIn("не является процентом конверсии", rendered.html)

        invalid = deepcopy(valid)
        invalid["stages"][0]["count"] = 3
        invalid["stages"][1]["count"] = 4
        self.assert_failed(invalid, "не может быть меньше")

        incomplete = build_reaction_funnel()
        incomplete["stages"].pop()
        self.assert_failed(incomplete, "ровно пять")

        impossible_zero = build_reaction_funnel()
        impossible_zero["stages"][1]["count"] = 0
        self.assert_failed(impossible_zero, "downstream counts")

        too_many_signals = build_reaction_funnel()
        too_many_signals["stages"][-1]["count"] = 4
        self.assert_failed(too_many_signals, "не больше трех")

        laundered_label = build_reaction_funnel()
        laundered_label["stages"][0]["label_ru"] = "Повлияли на итоговое решение"
        self.assert_failed(laundered_label, "фиксированная подпись")

        snapshot_partial = build_reaction_funnel()
        snapshot_partial["snapshot_status"] = "partial"
        rendered_partial = render_report_visual(snapshot_partial)
        self.assertEqual(rendered_partial.render_status, "partial")
        self.assertIn("Снимок связей реакций частичный", rendered_partial.html)

    def test_radar_never_turns_context_only_records_into_build_evidence(self) -> None:
        invalid = build_radar_gate()
        invalid["reader_decision"] = "build_allowed"
        invalid["dossier_status"] = "build_allowed"
        invalid["candidate_evidence_count"] = 0
        invalid["gates"] = [
            {
                "key": "evidence",
                "status": "pass",
                "reason_ru": "Контекст формально доступен.",
            }
        ]
        self.assert_failed(invalid, "context-only")

        valid = deepcopy(invalid)
        valid["candidate_evidence_count"] = 1
        result = render_report_visual(valid)
        self.assertEqual(result.render_status, "complete")
        self.assertIn("Доказательства кандидата", result.html)
        self.assertIn("Только контекст", result.html)
        self.assertIn("не заполняют проверки Radar", result.html)
        self.assertIn("Статус досье", result.html)
        self.assertIn("Решение для читателя", result.html)

        dossier_projection = build_radar_gate()
        dossier_projection["reader_decision"] = "reject"
        changed_dossier = deepcopy(dossier_projection)
        changed_dossier["dossier_status"] = "build_allowed"
        self.assertNotEqual(
            render_report_visual(dossier_projection).html,
            render_report_visual(changed_dossier).html,
        )

        escalated = deepcopy(valid)
        escalated["dossier_status"] = "investigate"
        self.assert_failed(escalated, "не может повысить")

        rejected = build_radar_gate()
        rejected["dossier_status"] = "reject"
        rejected["reader_decision"] = "investigate"
        self.assert_failed(rejected, "нельзя повысить")

        blank_guidance = build_radar_gate()
        blank_guidance["next_validation_ru"] = ""
        self.assert_failed(blank_guidance, "не может быть пустой")

        stale_empty = build_radar_gate("empty")
        stale_empty["missing_evidence"] = ["Старый пробел кандидата."]
        self.assert_failed(stale_empty, "candidate guidance")

        stale_unavailable = build_radar_gate("unavailable")
        stale_unavailable["kill_criteria_ru"] = "Старый критерий кандидата."
        self.assert_failed(stale_unavailable, "candidate guidance")

        blocked = deepcopy(valid)
        blocked["gates"][0]["status"] = "blocked"
        self.assert_failed(blocked, "несовместим")

    def test_project_limit_action_styling_and_local_path_validation(self) -> None:
        result = render_report_visual(build_project_impact())
        self.assertEqual(result.html.count('data-actionable="true"'), 1)
        self.assertEqual(result.html.count('data-actionable="false"'), 1)
        self.assertIn("Подтверждено", result.html)
        self.assertIn("Наблюдать", result.html)
        self.assertIn("Проверяемый сигнал о происхождении решения", result.html)
        self.assertIn("Связанных доказательств", result.html)

        too_many = build_project_impact()
        too_many["items"].extend(
            [
                _project_item("Третий проект", "signal:third", "confirmed"),
                _project_item("Четвертый проект", "signal:fourth", "confirmed"),
            ]
        )
        self.assert_failed(too_many, "не больше двух")

        unsafe_path = build_project_impact()
        unsafe_path["items"][0]["likely_files"] = ["../private/secret.py"]
        self.assert_failed(unsafe_path, "родительские сегменты")

        watch_only = build_project_impact()
        watch_only["items"] = [
            item for item in watch_only["items"] if item["status"] != "confirmed"
        ]
        watch_result = render_report_visual(watch_only)
        self.assertEqual(watch_result.render_status, "complete")
        self.assertIn(
            "Подтвержденного влияния на активные проекты нет", watch_result.html
        )

    def test_heatmap_declares_metric_and_keeps_unknown_distinct_from_zero(self) -> None:
        spec = build_source_thread_heatmap()
        result = render_report_visual(spec)
        self.assertEqual(result.render_status, "complete")
        self.assertIn("число независимых подтверждений", result.html)
        self.assertIn("Упоминания: 4; независимая поддержка: 1", result.html)
        self.assertIn("Ноль означает классифицированное отсутствие", result.html)

        unknown = deepcopy(spec)
        unknown["sources"][0]["classification_status"] = "unavailable"
        unknown["partial_reasons_ru"] = [
            "Классификация одного источника пока недоступна."
        ]
        unknown_result = render_report_visual(unknown)
        self.assertEqual(unknown_result.render_status, "partial")
        self.assertIn("Классификация источника недоступна", unknown_result.html)

        impossible = deepcopy(spec)
        impossible["cells"][0]["independent_support_count"] = 5
        self.assert_failed(impossible, "не может превышать mentions")

        classified_unknown = deepcopy(spec)
        classified_unknown["sources"][0]["classification_status"] = "unavailable"
        classified_unknown["partial_reasons_ru"] = [
            "Классификация одного источника пока недоступна."
        ]
        classified_unknown["cells"].append(
            {
                "source_id": "source-unclassified",
                "canonical_thread_id": "thread-a",
                "mention_count": 1,
                "independent_support_count": 1,
                "evidence_refs": ["evidence:should-not-exist"],
            }
        )
        self.assert_failed(classified_unknown, "неклассифицированного source")

    def test_maturity_population_must_equal_fixed_ordered_buckets(self) -> None:
        valid = render_report_visual(build_evidence_maturity())
        self.assertEqual(valid.render_status, "complete")
        self.assertIn("Зрелость неизвестна", valid.html)
        self.assertIn("канонических тем", valid.html)

        bad_sum = build_evidence_maturity()
        bad_sum["levels"][0]["count"] += 1
        self.assert_failed(bad_sum, "точно совпадать")

        missing_unknown = build_evidence_maturity()
        missing_unknown["levels"].pop()
        missing_unknown["thread_count"] = sum(
            level["count"] for level in missing_unknown["levels"]
        )
        self.assert_failed(missing_unknown, "все шесть уровней")

        laundered = build_evidence_maturity()
        laundered["levels"][0]["label_ru"] = "Достаточно для решения"
        self.assert_failed(laundered, "фиксированная подпись")

    def test_learning_requires_stage_specific_confirmation_and_monotonic_counts(
        self,
    ) -> None:
        valid = render_report_visual(build_learning_progression())
        self.assertEqual(valid.render_status, "complete")
        self.assertIn("Личная реакция подтверждает только", valid.html)

        wrong_confirmation = build_learning_progression()
        wrong_confirmation["stages"][1]["confirmation_kind"] = "reaction"
        self.assert_failed(wrong_confirmation, "требует независимое подтверждение")

        laundered = build_learning_progression()
        laundered["stages"][0]["label_ru"] = "Измерено"
        self.assert_failed(laundered, "фиксированная подпись")

        increasing = build_learning_progression()
        increasing["stages"][2]["count"] = 9
        self.assert_failed(increasing, "невозрастающей")

        all_zero = build_learning_progression()
        for stage in all_zero["stages"]:
            stage["count"] = 0
        self.assert_failed(all_zero, "data_status=empty")

        unknown = build_learning_progression()
        unknown_stage = unknown["stages"][-1]
        unknown_stage.update(
            {
                "count": None,
                "observation_status": "unknown",
                "confirmation_kind": "none",
                "evidence_refs": [],
            }
        )
        self.assert_failed(unknown, "partial-причину")
        unknown["partial_reasons_ru"] = [
            "Измерение результата пока не синхронизировано."
        ]
        rendered = render_report_visual(unknown)
        self.assertEqual(rendered.render_status, "partial")
        self.assertIn("неизвестно", rendered.html)

    def test_badge_is_supporting_semantics_not_a_meaningful_visual(self) -> None:
        result = render_report_visual(build_evidence_badge())
        self.assertIn('data-visual-role="supporting"', result.html)
        self.assertIn("Уверенность", result.html)
        self.assertIn("Зрелость доказательств", result.html)

        invalid = build_evidence_badge()
        invalid["independent_source_count"] = 4
        self.assert_failed(invalid, "не может превышать source_count")

        zero_sources = build_evidence_badge()
        zero_sources["source_count"] = 0
        zero_sources["independent_source_count"] = 0
        self.assert_failed(zero_sources, "хотя бы один источник")

        fake_multi_channel = build_evidence_badge()
        fake_multi_channel["independent_source_count"] = 1
        self.assert_failed(fake_multi_channel, "минимум два")

    def test_visual_document_rejects_duplicate_component_ids(self) -> None:
        first = build_decision_matrix()
        second = build_evidence_badge()
        second["component_id"] = first["component_id"]
        with self.assertRaisesRegex(
            ReportVisualValidationError, "повторяющиеся DOM id"
        ):
            render_visual_document([first, second])

    def test_visual_document_keeps_multiple_schema_failures_accessible(self) -> None:
        document = render_visual_document([{}, {}])

        self.assertEqual(document.count('data-render-status="failed"'), 2)
        self.assertIn('data-component-id="invalid-visual-1"', document)
        self.assertIn('data-component-id="invalid-visual-2"', document)
        ids = re.findall(r'\sid="([^"]+)"', document)
        self.assertEqual(len(ids), len(set(ids)))

        caller_owned = build_decision_matrix()
        caller_owned["component_id"] = "invalid-visual-2"
        document = render_visual_document([caller_owned, {}])
        self.assertIn('data-component-id="invalid-visual-2"', document)
        self.assertIn('data-component-id="invalid-visual-2-2"', document)

        failed_caller_owned = {"component_id": "invalid-visual-2"}
        document = render_visual_document([failed_caller_owned, {}])
        self.assertIn('data-component-id="invalid-visual-2"', document)
        self.assertIn('data-component-id="invalid-visual-2-2"', document)

        derived_collision = build_decision_matrix()
        derived_collision["component_id"] = "invalid-visual-2-title"
        document = render_visual_document([derived_collision, {}])
        self.assertIn('data-component-id="invalid-visual-2-2"', document)

    def test_visual_document_rejects_mixed_identity_and_derived_id_collisions(
        self,
    ) -> None:
        decision = build_decision_matrix()
        radar = build_radar_gate()
        radar["run_id"] = "other-run-same-period"
        with self.assertRaisesRegex(ReportVisualValidationError, "document identity"):
            render_visual_document([decision, radar])

        graph = build_knowledge_graph()
        graph["component_id"] = "foo"
        badge = build_evidence_badge()
        badge["component_id"] = "foo-svg"
        with self.assertRaisesRegex(ReportVisualValidationError, "производные id"):
            render_visual_document([graph, badge])

    def test_period_and_stale_identity_cannot_be_mislabeled(self) -> None:
        wrong_period = build_decision_matrix()
        wrong_period["analysis_period_start"] = "2026-07-05T00:00:00Z"
        self.assert_failed(wrong_period, "завершенной ISO-неделей")

        stale = build_decision_matrix("stale")
        stale["stale_from_run_id"] = stale["run_id"]
        self.assert_failed(stale, "другому run")

        stale = build_decision_matrix("stale")
        stale["stale_from_period"] = stale["reporting_week"]
        self.assert_failed(stale, "предыдущему reporting week")

        future_stale = build_decision_matrix("stale")
        future_stale["stale_from_period"] = "2026-W29"
        self.assert_failed(future_stale, "предыдущему reporting week")

        impossible_stale = build_decision_matrix("stale")
        impossible_stale["stale_from_period"] = "2021-W53"
        self.assert_failed(impossible_stale, "недопустимая ISO-неделя")

    def test_visual_document_namespaces_internal_svg_ids_across_components(
        self,
    ) -> None:
        first = build_knowledge_graph()
        second = build_knowledge_graph()
        second["component_id"] = "knowledge-graph-secondary"
        document = render_visual_document([first, second])
        ids = re.findall(r'\sid="([^"]+)"', document)
        duplicates = sorted({value for value in ids if ids.count(value) > 1})
        self.assertEqual(duplicates, [], f"duplicate DOM ids: {duplicates}")

    def test_committed_fixture_pack_and_gallery_match_the_renderer(self) -> None:
        fixture_dir = Path(__file__).parent / "fixtures" / "report_v2"

        def reject_duplicate_keys(
            pairs: list[tuple[str, object]],
        ) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"duplicate fixture key: {key}")
                result[key] = value
            return result

        pack = json.loads(
            (fixture_dir / "visual_components.v1.json").read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
        self.assertEqual(pack["fixture_version"], "report_visual_fixture_pack.v1")
        self.assertEqual(len(pack["specs"]), 10)
        self.assertEqual(
            {spec["schema_version"] for spec in pack["specs"]},
            set(SUPPORTED_VISUAL_SCHEMAS),
        )
        fixture_results = [render_report_visual(spec) for spec in pack["specs"]]
        self.assertTrue(
            all(
                result.render_status == "complete"
                and result.data_status == "available"
                and not result.warnings
                for result in fixture_results
            )
        )
        gallery = render_visual_document(
            pack["specs"], title_ru="Галерея компонентов отчёта V2"
        )
        self.assertEqual(
            gallery + "\n",
            (fixture_dir / "visual_components.v1.html").read_text(encoding="utf-8"),
        )
        self.assertEqual(gallery.count('data-irx-visual="true"'), 10)


if __name__ == "__main__":
    unittest.main()
