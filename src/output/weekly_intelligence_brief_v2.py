"""Deterministic, additive Weekly Intelligence Brief V2 preview.

IRX-6 deliberately keeps this renderer outside the frozen IRX-2 stage policy.
It consumes already-authorized upstream contracts, writes a separate immutable
preview pair, and never ranks candidates, calls a model, or changes delivery.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import secrets
import stat
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from output.editorial_intelligence import (
    EDITORIAL_INPUT_SCHEMA_VERSION,
    EditorialValidationError,
    editorial_input_hash,
    validate_editorial_artifact,
)
from output.editorial_intelligence_prompt import EDITORIAL_SCHEMA_VERSION
from output.mvp_radar_reader import (
    MVP_RADAR_READER_SCHEMA_VERSION,
    MvpRadarReaderError,
    load_bound_mvp_radar_reader,
    validate_mvp_radar_reader_projection,
)
from output.project_intelligence import (
    PROJECT_ACTION_PERMISSIONS_SCHEMA_VERSION,
    PROJECT_INTELLIGENCE_SCHEMA_VERSION,
    ProjectIntelligenceValidationError,
    validate_project_intelligence_projection,
)
from output.reaction_personalization import (
    REACTION_EFFECT_SCHEMA_VERSION,
    ReactionPersonalizationError,
    validate_reaction_effect,
)
from output.report_visuals import (
    REPORT_VISUALS_CONTRACT_VERSION,
    ReportVisualValidationError,
    render_report_visual,
    report_visual_styles,
    validate_report_visual,
)
from output.weekly_run_manifest import (
    MANIFEST_SCHEMA_VERSION,
    SUCCEEDED,
    WeeklyRunManifestError,
    validate_manifest,
    verify_file_checksum,
)


BRIEF_V2_SCHEMA_VERSION = "split_ai_report.v2"
BRIEF_V2_SURFACE = "weekly_brief"
BRIEF_V2_PREVIEW_PROFILE = "irx6_brief_v2_preview.v1"
BRIEF_V2_RENDERER_VERSION = "weekly_intelligence_brief_v2.v1"
BRIEF_V2_DIRECTORY = "weekly_intelligence_briefs_v2"
BRIEF_V2_JSON_FILENAME = "weekly-intelligence-brief.v2.json"
BRIEF_V2_HTML_FILENAME = "weekly-intelligence-brief.v2.html"
BRIEF_V2_SOURCE_CATALOG_SCHEMA_VERSION = "brief_v2_source_catalog.v1"
BRIEF_V2_SOURCE_CATALOG_FILENAME = "weekly-intelligence-brief.v2.sources.json"

MAX_JSON_BYTES = 2_000_000
MAX_HTML_BYTES = 2_000_000
MAX_SOURCE_JSON_BYTES = 8_000_000
TARGET_VISIBLE_WORDS_MIN = 700
TARGET_VISIBLE_WORDS_MAX = 900
HARD_VISIBLE_WORDS_MAX = 1_100

_ROOT_FIELDS = {
    "schema_version",
    "surface",
    "preview_profile",
    "renderer_version",
    "source_schema_versions",
    "run_id",
    "generated_at",
    "period_mode",
    "reporting_period",
    "source_run_status",
    "run_status",
    "partial",
    "partial_reasons_ru",
    "weekly_thesis",
    "decision_matrix",
    "actions",
    "signals",
    "reaction_effect",
    "feedback_effect",
    "project_actions",
    "mvp_radar",
    "feedback_targets",
    "visual_specs",
    "evidence_refs",
    "navigation",
    "technical_refs",
    "source_artifacts",
    "artifact_paths",
    "content_metrics",
}
_SOURCE_SCHEMA_FIELDS = {
    "manifest",
    "editorial",
    "editorial_input",
    "reaction",
    "project_intelligence",
    "project_permissions",
    "mvp_radar_reader",
    "report_visuals",
    "brief_source_catalog",
}
_PERIOD_FIELDS = {
    "reporting_week",
    "analysis_period_start",
    "analysis_period_end",
}
_MATRIX_BUCKETS = ("act", "study", "watch", "ignore")
_CONFIDENCE = {"low", "medium", "high"}
_MATURITY = {
    "single_source",
    "repeated_signal",
    "multi_channel",
    "primary_verified",
    "externally_corroborated",
    "decision_grade",
}
_MATURITY_ORDER = {
    "single_source": 0,
    "repeated_signal": 1,
    "multi_channel": 2,
    "primary_verified": 3,
    "externally_corroborated": 4,
    "decision_grade": 5,
}
_CONFIDENCE_LABELS = {
    "low": "низкая",
    "medium": "средняя",
    "high": "высокая",
}
_MATURITY_LABELS = {
    "single_source": "один источник",
    "repeated_signal": "повторяющийся сигнал",
    "multi_channel": "несколько независимых каналов",
    "primary_verified": "проверено первичным источником",
    "externally_corroborated": "подтверждено внешними данными",
    "decision_grade": "достаточно для ограниченного решения",
}
_DECISION_LABELS = {
    "act": "Действовать",
    "study": "Изучить",
    "watch": "Наблюдать",
    "ignore": "Отложить / не делать",
}
_EFFORT_LABELS = {
    "XS": "До двух часов",
    "S": "Один небольшой рабочий цикл",
    "M": "Несколько согласованных рабочих циклов",
}
_REACTION_REASON_LABELS = {
    "post_not_found": "Часть отмеченных постов не найдена в проверяемом снимке.",
    "outside_analysis_period": "Часть отметок относится к другому периоду.",
    "knowledge_atom_not_extracted": "Для части постов ещё нет атома знаний.",
    "no_thread_link": "Часть атомов пока не связана с темой.",
    "no_canonical_thread_link": "Для части тем ещё нет канонической связи.",
    "stale_or_low_confidence_evidence": "Часть связей устарела или имеет низкую уверенность.",
    "contradicted_or_retracted_evidence": "Часть доказательств противоречива или отозвана.",
    "duplicate_signal": "Повторяющиеся сигналы объединены.",
    "superseded_by_confirmed_feedback": "Подтверждённая обратная связь имела больший приоритет.",
    "report_limit_reached": "Часть пригодных тем не вошла в лимит выпуска.",
    "confirmed_feedback_snapshot_unverified": "Снимок подтверждённой обратной связи не проверен.",
    "snapshot_unverified": "Снимок личных реакций не прошёл проверку.",
}
_KIR_REASON_LABELS = {
    "not_required": "Связь с внутренней темой знаний для этого кандидата не требуется.",
    "passed": "Свежая тема знаний связана с кандидатом и проверяемыми источниками.",
    "missing_kir_thread": "Не хватает совпадающей темы знаний.",
    "stale_kir_thread": "Совпадающая тема знаний устарела.",
    "missing_source_atoms": "В теме знаний не хватает проверяемых атомов.",
    "missing_source_urls": "В теме знаний не хватает проверяемых ссылок.",
    "missing_decision_grade_external_evidence": "Не хватает внешних доказательств достаточной зрелости.",
    "blocking_risk": "Radar зафиксировал блокирующий риск.",
    "profile_mismatch": "Кандидат не соответствует текущему профилю оператора.",
    "missing_operator_fit": "Не подтверждено соответствие рабочему процессу оператора.",
}
_STAGE_LABELS_RU = {
    "knowledge_refresh": "обновление базы знаний",
    "reaction_sync": "синхронизация личных реакций",
    "feedback_snapshot": "снимок подтверждённой обратной связи",
    "canonical_thread_curation": "каноническая группировка тем",
    "frontier_analysis": "анализ исследовательского фронтира",
    "radar": "MVP Radar",
    "editorial_intelligence": "редакционный синтез",
    "weekly_brief": "базовый недельный бриф",
    "knowledge_atlas": "совместимый Atlas V1",
    "knowledge_audit_explorer": "обозреватель технического аудита",
    "reader_value_gates": "проверка читательской ценности",
}
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_OPERATOR_TIME_ZONE = ZoneInfo("Europe/Berlin")
_WEEK_RE = re.compile(r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#@+\-=]{0,299}$")
_VISIBLE_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+(?:[-‑][A-Za-zА-Яа-яЁё0-9]+)*")
_READER_RAW_REF_RE = re.compile(
    r"\b(?:atom|brief|canonical[-_]thread|claim|evidence|feedback|knowledge[-_]atom|permission|project|project[-_]action|reaction|run|signal|source|thread):[A-Za-z0-9]"
)
_READER_RUN_ID_RE = re.compile(r"\btra-weekly-[A-Za-z0-9._-]+")
_READER_INTERNAL_ENUM_RE = re.compile(
    r"\b(?:act|build_allowed|context_only|decision_grade|focused_experiment|high|ignore|low|medium|no_candidate|rank_changed|rank_unchanged|ranking|study|watch)\b"
)
_READER_INTERNAL_PATH_RE = re.compile(r"(?:^|\s)(?:/srv/|data/|docs/|src/|tests/)")
_READER_INTERNAL_PHRASES = (
    "KIR Knowledge Thread",
    "bounded Radar run",
    "manifest-bound",
)


class WeeklyIntelligenceBriefV2Error(ValueError):
    """Base error for the additive Brief V2 preview contract."""


class WeeklyIntelligenceBriefV2ValidationError(WeeklyIntelligenceBriefV2Error):
    """Raised when the closed V2 sidecar contract is violated."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(str(item) for item in errors if str(item).strip())
        super().__init__("; ".join(self.errors) or "Brief V2 validation failed")


class WeeklyIntelligenceBriefV2ArtifactError(WeeklyIntelligenceBriefV2Error):
    """Raised when immutable source or output bytes cannot be trusted."""


@dataclass(frozen=True, slots=True)
class WeeklyIntelligenceBriefV2Summary:
    run_id: str
    reporting_week: str
    run_status: str
    partial: bool
    html_path: str
    json_path: str
    source_catalog_path: str
    signal_count: int
    primary_action_count: int
    secondary_action_count: int
    project_action_count: int
    visual_component_count: int
    meaningful_visual_count: int
    visible_word_count: int
    cache_hit: bool = False


@dataclass(frozen=True, slots=True)
class _StrictJsonRecord:
    value: object
    sha256: str
    size: int


def build_weekly_intelligence_brief_v2(
    *,
    manifest: Mapping[str, object],
    manifest_path: str | Path,
    editorial_artifact: Mapping[str, object],
    editorial_input_package: Mapping[str, object],
    reaction_effect: Mapping[str, object],
    project_intelligence: Mapping[str, object],
    project_descriptors: Sequence[Mapping[str, object]],
    mvp_radar: Mapping[str, object],
    source_artifacts: Mapping[str, Mapping[str, object]],
    artifact_paths: Mapping[str, object],
    compatibility_atlas_path: str | Path | None = None,
    atlas_v2_path: str | Path | None = None,
    audit_explorer_path: str | Path | None = None,
) -> dict[str, object]:
    """Assemble one reader DTO from already-authorized same-run contracts."""

    manifest_value = _json_copy(manifest, "manifest")
    _validate_manifest_identity(manifest_value, manifest_path=manifest_path)
    package = _json_copy(editorial_input_package, "editorial_input_package")
    editorial = _json_copy(editorial_artifact, "editorial_artifact")
    generation_receipt = _mapping(editorial.get("generation_receipt"))
    requested_model = str(generation_receipt.get("requested_model") or "")
    expected_input_hash = (
        editorial_input_hash(package, model=requested_model)
        if requested_model
        else None
    )
    try:
        validate_editorial_artifact(
            editorial,
            input_package=package,
            expected_model=requested_model or None,
            expected_input_hash=expected_input_hash,
        )
    except EditorialValidationError as exc:
        raise WeeklyIntelligenceBriefV2ValidationError(
            [f"editorial_artifact: {item}" for item in exc.errors]
        ) from exc
    _require_input_identity(package, manifest_value)
    _require_editorial_signal_order(editorial, package)

    try:
        reaction = validate_reaction_effect(reaction_effect)
    except (ReactionPersonalizationError, TypeError, ValueError) as exc:
        raise WeeklyIntelligenceBriefV2ValidationError(
            [f"reaction_effect: {exc}"]
        ) from exc
    _require_reaction_identity(reaction, manifest_value)

    try:
        project = validate_project_intelligence_projection(
            project_intelligence,
            input_package=package,
            projects=project_descriptors,
        )
    except ProjectIntelligenceValidationError as exc:
        raise WeeklyIntelligenceBriefV2ValidationError(
            [f"project_intelligence: {item}" for item in exc.errors]
        ) from exc
    _require_period_identity(project, manifest_value, "project_intelligence")

    radar = _json_copy(mvp_radar, "mvp_radar")
    try:
        if radar.get("reader_state") in {"available", "no_candidate"}:
            validate_mvp_radar_reader_projection(radar, manifest=manifest_value)
        else:
            validate_mvp_radar_reader_projection(radar)
    except (MvpRadarReaderError, TypeError, ValueError) as exc:
        raise WeeklyIntelligenceBriefV2ValidationError([f"mvp_radar: {exc}"]) from exc
    _require_radar_identity(radar, manifest_value)
    _require_package_source_parity(
        package,
        reaction=reaction,
        radar=radar,
        manifest=manifest_value,
    )

    evidence_catalog = {
        str(item.get("evidence_ref")): dict(item)
        for item in _mapping_list(package.get("evidence_catalog"))
        if str(item.get("evidence_ref") or "").strip()
    }
    signal_rows = _reader_signals(editorial, evidence_catalog)
    signal_by_ref = {str(item["signal_id"]): item for item in signal_rows}
    decision_matrix, decision_items = _reader_decision_matrix(
        editorial,
        signal_by_ref=signal_by_ref,
    )
    actions = _reader_actions(editorial, signal_by_ref=signal_by_ref)
    project_actions = _reader_project_actions(
        editorial,
        project,
        signal_by_ref=signal_by_ref,
    )
    partial_reasons = _partial_reasons(
        manifest_value,
        editorial,
        reaction,
        radar,
        signal_count=len(signal_rows),
        has_primary=actions["primary"] is not None,
        has_defer=any(
            item.get("emphasis") == "explicit_defer" for item in decision_items
        ),
    )
    period = _period_from_manifest(manifest_value)
    run_id = str(manifest_value["run_id"])
    visual_specs = _visual_specs(
        run_id=run_id,
        period=period,
        decision_items=decision_items,
        reaction_effect=reaction,
        selected_reaction_count=_selected_reaction_count(signal_rows),
        project_actions=project_actions,
        mvp_radar=radar,
        signal_titles={
            str(item["signal_id"]): str(item["title"])
            for item in signal_rows
        },
        decision_contract_complete=(
            not signal_rows
            or (actions["primary"] is not None and any(
                item.get("emphasis") == "explicit_defer"
                for item in decision_items
            ))
        ),
    )
    render_failures = [
        result
        for spec in visual_specs
        if (result := render_report_visual(spec)).render_status == "failed"
    ]
    if render_failures:
        partial_reasons.append(
            "Один или несколько визуальных компонентов не прошли проверку схемы."
        )
    partial_reasons = _unique_text(partial_reasons)
    run_status = "partial" if partial_reasons else "complete"
    feedback_targets = _feedback_targets(run_id, signal_rows, project_actions)
    evidence_refs = _unique_text(
        [
            *[ref for signal in signal_rows for ref in signal["evidence_refs"]],
            *[ref for action in project_actions for ref in action["evidence_refs"]],
        ]
    )
    navigation = _navigation(
        run_id=run_id,
        atlas_v2_path=atlas_v2_path,
        audit_explorer_path=audit_explorer_path,
        compatibility_atlas_path=compatibility_atlas_path,
    )
    sources = _normalize_source_artifacts(source_artifacts)
    paths = _normalize_artifact_paths(artifact_paths)
    technical_refs = {
        "manifest_path": str(Path(manifest_path).resolve()),
        "audit_explorer_path": _mapping(navigation["audit_explorer"]).get(
            "path"
        ),
        "compatibility_atlas_path": _mapping(
            navigation["compatibility_atlas"]
        ).get("path"),
        "editorial_artifact_path": str(sources["editorial"]["path"]),
        "editorial_input_catalog_path": str(
            sources["editorial_input"]["path"]
        ),
        "project_intelligence_path": str(
            sources["project_intelligence"]["path"]
        ),
        "v1_brief_path": str(sources["reaction_source"]["path"]),
    }
    sidecar: dict[str, object] = {
        "schema_version": BRIEF_V2_SCHEMA_VERSION,
        "surface": BRIEF_V2_SURFACE,
        "preview_profile": BRIEF_V2_PREVIEW_PROFILE,
        "renderer_version": BRIEF_V2_RENDERER_VERSION,
        "source_schema_versions": {
            "manifest": MANIFEST_SCHEMA_VERSION,
            "editorial": EDITORIAL_SCHEMA_VERSION,
            "editorial_input": EDITORIAL_INPUT_SCHEMA_VERSION,
            "reaction": REACTION_EFFECT_SCHEMA_VERSION,
            "project_intelligence": PROJECT_INTELLIGENCE_SCHEMA_VERSION,
            "project_permissions": PROJECT_ACTION_PERMISSIONS_SCHEMA_VERSION,
            "mvp_radar_reader": MVP_RADAR_READER_SCHEMA_VERSION,
            "report_visuals": REPORT_VISUALS_CONTRACT_VERSION,
            "brief_source_catalog": BRIEF_V2_SOURCE_CATALOG_SCHEMA_VERSION,
        },
        "run_id": run_id,
        "generated_at": str(manifest_value["generated_at"]),
        "period_mode": str(manifest_value["period_mode"]),
        "reporting_period": period,
        "source_run_status": str(manifest_value["run_status"]),
        "run_status": run_status,
        "partial": bool(partial_reasons),
        "partial_reasons_ru": partial_reasons,
        "weekly_thesis": copy.deepcopy(editorial["weekly_thesis"]),
        "decision_matrix": decision_matrix,
        "actions": actions,
        "signals": signal_rows,
        "reaction_effect": copy.deepcopy(reaction),
        "feedback_effect": copy.deepcopy(editorial["feedback_effect"]),
        "project_actions": project_actions,
        "mvp_radar": radar,
        "feedback_targets": feedback_targets,
        "visual_specs": visual_specs,
        "evidence_refs": evidence_refs,
        "navigation": navigation,
        "technical_refs": technical_refs,
        "source_artifacts": sources,
        "artifact_paths": paths,
        "content_metrics": {
            "visible_word_count": 0,
            "target_min": TARGET_VISIBLE_WORDS_MIN,
            "target_max": TARGET_VISIBLE_WORDS_MAX,
            "hard_max": HARD_VISIBLE_WORDS_MAX,
            "word_budget_status": "pending",
            "visual_component_count": len(visual_specs),
            "meaningful_visual_count": _meaningful_visual_count(visual_specs),
        },
    }
    _validate_weekly_intelligence_brief_v2(
        sidecar,
        manifest=manifest_value,
        verify_metrics=False,
    )
    html = _render_document(sidecar)
    word_count = visible_word_count(html)
    budget_status = _word_budget_status(word_count)
    if budget_status not in {"within_target", "pending"}:
        sidecar["partial_reasons_ru"] = _unique_text(
            [
                *sidecar["partial_reasons_ru"],
                (
                    "Начальный читательский объём вышел за целевой диапазон "
                    f"{TARGET_VISIBLE_WORDS_MIN}–{TARGET_VISIBLE_WORDS_MAX} слов."
                ),
            ]
        )
        sidecar["partial"] = True
        sidecar["run_status"] = "partial"
        html = _render_document(sidecar)
        word_count = visible_word_count(html)
        budget_status = _word_budget_status(word_count)
    sidecar["content_metrics"] = {
        **dict(sidecar["content_metrics"]),
        "visible_word_count": word_count,
        "word_budget_status": budget_status,
    }
    validate_weekly_intelligence_brief_v2(sidecar, manifest=manifest_value)
    return sidecar


def validate_weekly_intelligence_brief_v2(
    payload: Mapping[str, object],
    *,
    manifest: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Validate the closed sidecar and return a detached JSON-safe copy."""

    value = _json_copy(payload, "Brief V2 sidecar")
    _validate_weekly_intelligence_brief_v2(value, manifest=manifest)
    return value


def render_weekly_intelligence_brief_v2_html(
    payload: Mapping[str, object],
    *,
    manifest: Mapping[str, object] | None = None,
) -> str:
    """Render one validated sidecar without model, filesystem, or ranking work."""

    value = validate_weekly_intelligence_brief_v2(payload, manifest=manifest)
    return _render_document(value)


def generate_weekly_intelligence_brief_v2_artifact(
    *,
    manifest_path: str | Path,
    editorial_artifact_path: str | Path,
    editorial_input_package: Mapping[str, object],
    project_intelligence_path: str | Path,
    project_descriptors: Sequence[Mapping[str, object]],
    output_root: str | Path,
    allowed_source_roots: Sequence[str | Path] = (),
    knowledge_atlas_v2_json_path: str | Path | None = None,
) -> WeeklyIntelligenceBriefV2Summary:
    """Create or exactly reuse one immutable, manifest-bound preview package."""

    manifest_lexical = Path(manifest_path).expanduser().absolute()
    manifest_file = manifest_lexical.resolve(strict=True)
    if manifest_lexical != manifest_file or manifest_file.name != "manifest.json":
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 requires the canonical manifest.json path"
        )
    run_dir = manifest_file.parent
    manifest_record = _read_strict_json_record(
        manifest_file,
        label="weekly manifest",
        maximum=MAX_SOURCE_JSON_BYTES,
    )
    if not isinstance(manifest_record.value, dict):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "weekly manifest root must be an object"
        )
    strict_manifest = manifest_record.value
    manifest = strict_manifest
    validate_manifest(
        manifest,
        path_base=run_dir,
        allowed_roots=(run_dir,),
        check_artifact_existence=False,
    )
    _validate_manifest_identity(manifest, manifest_path=manifest_file)
    _strict_check_manifest_json_sources(manifest, manifest_file)
    validate_manifest(
        manifest,
        path_base=run_dir,
        allowed_roots=(run_dir,),
        check_artifact_existence=True,
    )
    roots = _unique_paths(
        (
            run_dir,
            Path(output_root).resolve(),
            *(Path(root).resolve(strict=True) for root in allowed_source_roots),
        )
    )
    editorial_file = _contained_source_path(editorial_artifact_path, roots)
    project_file = _contained_source_path(project_intelligence_path, roots)
    editorial_record = _read_strict_json_record(
        editorial_file,
        label="editorial artifact",
        maximum=MAX_SOURCE_JSON_BYTES,
    )
    if not isinstance(editorial_record.value, dict):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "editorial artifact root must be an object"
        )
    editorial = editorial_record.value
    project_record = _read_strict_json_record(
        project_file,
        label="project intelligence",
        maximum=MAX_SOURCE_JSON_BYTES,
    )
    if not isinstance(project_record.value, dict):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "project intelligence root must be an object"
        )
    try:
        project = validate_project_intelligence_projection(project_record.value)
    except ProjectIntelligenceValidationError as exc:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "project intelligence failed its strict projection: " + str(exc)
        ) from exc
    v1_brief_path, v1_brief, v1_brief_record = _load_bound_v1_brief(
        manifest,
        manifest_file,
    )
    reaction = v1_brief.get("reaction_effect")
    if not isinstance(reaction, Mapping):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "manifest-bound V1 Brief has no reaction effect receipt"
        )
    _strict_check_manifest_json_sources(manifest, manifest_file)
    radar = load_bound_mvp_radar_reader(
        manifest,
        path_base=run_dir,
        allowed_roots=(run_dir,),
    )
    atlas_path = _bound_stage_html_path(
        manifest,
        manifest_file,
        stage_name="knowledge_atlas",
    )
    atlas_v2_path, audit_explorer_path = _validated_atlas_navigation_paths(
        knowledge_atlas_v2_json_path,
        manifest_path=manifest_file,
        allowed_source_roots=roots,
    )
    output_dir = _safe_v2_output_directory(
        output_root,
        str(manifest["run_id"]),
    )
    html_path = output_dir / BRIEF_V2_HTML_FILENAME
    json_path = output_dir / BRIEF_V2_JSON_FILENAME
    source_catalog_path = output_dir / BRIEF_V2_SOURCE_CATALOG_FILENAME
    source_catalog = _build_source_catalog(
        manifest=manifest,
        editorial_input_package=editorial_input_package,
        project_descriptors=project_descriptors,
    )
    source_catalog_bytes = _canonical_json_bytes(source_catalog)
    source_artifacts = {
        "manifest": _source_artifact_record(manifest_file, manifest_record),
        "editorial": _source_artifact_record(editorial_file, editorial_record),
        "editorial_input": _source_artifact_bytes(
            source_catalog_path,
            source_catalog_bytes,
        ),
        "project_intelligence": _source_artifact_record(
            project_file,
            project_record,
        ),
        "reaction_source": _source_artifact_record(
            v1_brief_path,
            v1_brief_record,
        ),
    }
    sidecar = build_weekly_intelligence_brief_v2(
        manifest=manifest,
        manifest_path=manifest_file,
        editorial_artifact=editorial,
        editorial_input_package=editorial_input_package,
        reaction_effect=reaction,
        project_intelligence=project,
        project_descriptors=project_descriptors,
        mvp_radar=radar,
        source_artifacts=source_artifacts,
        artifact_paths={
            "html": str(html_path),
            "json": str(json_path),
            "source_catalog": str(source_catalog_path),
        },
        compatibility_atlas_path=atlas_path,
        atlas_v2_path=atlas_v2_path,
        audit_explorer_path=audit_explorer_path,
    )
    html_text = render_weekly_intelligence_brief_v2_html(
        sidecar,
        manifest=manifest,
    )
    _require_reader_value_quality(
        sidecar,
        html_text,
        manifest=manifest,
    )
    html_bytes = html_text.encode("utf-8")
    json_bytes = _canonical_json_bytes(sidecar)
    if (
        len(html_bytes) > MAX_HTML_BYTES
        or len(json_bytes) > MAX_JSON_BYTES
        or len(source_catalog_bytes) > MAX_SOURCE_JSON_BYTES
    ):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 artifact exceeds its byte limit"
        )
    cache_hit = _write_immutable_artifacts(
        (
            (source_catalog_path, source_catalog_bytes),
            (html_path, html_bytes),
            (json_path, json_bytes),
        )
    )
    loaded = load_manifest_bound_weekly_intelligence_brief_v2(
        json_path,
        expected_manifest_path=manifest_file,
        allowed_source_roots=roots,
    )
    if loaded != sidecar:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 write verification changed the sidecar"
        )
    return _summary(sidecar, cache_hit=cache_hit)


def load_manifest_bound_weekly_intelligence_brief_v2(
    path: str | Path,
    *,
    expected_manifest_path: str | Path,
    allowed_source_roots: Sequence[str | Path] = (),
) -> dict[str, object]:
    """Load a V2 preview and re-check its manifest and immutable dependencies."""

    try:
        lexical_source = Path(path).expanduser().absolute()
        source = lexical_source.resolve(strict=True)
    except WeeklyIntelligenceBriefV2Error:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 path is invalid"
        ) from exc
    if lexical_source != source:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 path contains a symlink component"
        )
    _require_private_directory(source.parent, label="Brief V2 package directory")
    sidecar_record = _read_strict_json_record(
        source,
        label="Brief V2",
        maximum=MAX_JSON_BYTES,
        require_private=True,
    )
    if not isinstance(sidecar_record.value, dict):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 root must be an object"
        )
    value = _json_copy(sidecar_record.value, "Brief V2 sidecar")
    _validate_weekly_intelligence_brief_v2(
        value,
        allow_unbound_authoritative_radar=True,
    )
    if (
        source.name != BRIEF_V2_JSON_FILENAME
        or source.parent.name != value.get("run_id")
        or source.parent.parent.name != BRIEF_V2_DIRECTORY
    ):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 is not stored at its exact run-scoped path"
        )
    paths = _mapping(value["artifact_paths"])
    json_lexical = Path(str(paths["json"])).expanduser().absolute()
    if json_lexical != source or json_lexical.resolve(strict=True) != source:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 JSON path does not identify the loaded file"
        )
    manifest_path = Path(str(_mapping(value["technical_refs"])["manifest_path"]))
    manifest_lexical = manifest_path.expanduser().absolute()
    manifest_file = manifest_lexical.resolve(strict=True)
    expected_manifest_lexical = Path(expected_manifest_path).expanduser().absolute()
    expected_manifest_file = expected_manifest_lexical.resolve(strict=True)
    if (
        manifest_lexical != manifest_file
        or expected_manifest_lexical != expected_manifest_file
        or manifest_file != expected_manifest_file
        or manifest_file.name != "manifest.json"
        or manifest_file.parent.name != value.get("run_id")
    ):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 does not use the caller-selected canonical manifest"
        )
    base_roots = _unique_paths(
        (
            source.parent.parent.parent.resolve(),
            *(Path(root).resolve(strict=True) for root in allowed_source_roots),
        )
    )
    _require_contained(manifest_file, base_roots)
    run_dir = manifest_file.parent
    manifest_record = _read_strict_json_record(
        manifest_file,
        label="weekly manifest",
        maximum=MAX_SOURCE_JSON_BYTES,
    )
    if not isinstance(manifest_record.value, dict):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "weekly manifest root must be an object"
        )
    strict_manifest = manifest_record.value
    manifest = strict_manifest
    validate_manifest(
        manifest,
        path_base=run_dir,
        allowed_roots=(run_dir,),
        check_artifact_existence=False,
    )
    _validate_manifest_identity(manifest, manifest_path=manifest_file)
    _strict_check_manifest_json_sources(manifest, manifest_file)
    validate_manifest(
        manifest,
        path_base=run_dir,
        allowed_roots=(run_dir,),
        check_artifact_existence=True,
    )
    _require_sidecar_manifest_identity(value, manifest)
    validate_weekly_intelligence_brief_v2(value, manifest=manifest)

    roots = _unique_paths((*base_roots, run_dir))
    source_artifacts = _mapping(value["source_artifacts"])
    loaded_sources: dict[str, Path] = {}
    loaded_source_records: dict[str, _StrictJsonRecord] = {}
    for name in (
        "manifest",
        "editorial",
        "editorial_input",
        "project_intelligence",
        "reaction_source",
    ):
        descriptor = _mapping(source_artifacts[name])
        source_path = _contained_source_path(descriptor["path"], roots)
        if name == "manifest" and source_path == manifest_file:
            record = manifest_record
        else:
            record = _read_strict_json_record(
                source_path,
                label=f"Brief V2 dependency {name}",
                maximum=MAX_SOURCE_JSON_BYTES,
                require_private=name == "editorial_input",
            )
        if record.sha256 != descriptor["sha256"]:
            raise WeeklyIntelligenceBriefV2ArtifactError(
                f"Brief V2 dependency checksum mismatch: {name}"
            )
        loaded_sources[name] = source_path
        loaded_source_records[name] = record
    if loaded_sources["manifest"] != manifest_file:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 manifest dependency path mismatch"
        )

    editorial_value = loaded_source_records["editorial"].value
    if not isinstance(editorial_value, dict):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "editorial artifact root must be an object"
        )
    editorial = editorial_value
    source_catalog_lexical = Path(str(paths["source_catalog"])).expanduser().absolute()
    source_catalog_path = source_catalog_lexical.resolve(strict=True)
    if source_catalog_lexical != source_catalog_path:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 source catalog path contains a symlink component"
        )
    if source_catalog_path != loaded_sources["editorial_input"]:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 source catalog path mismatch"
        )
    source_catalog_value = loaded_source_records["editorial_input"].value
    if not isinstance(source_catalog_value, dict):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 source catalog root must be an object"
        )
    source_catalog = _validate_source_catalog_value(
        source_catalog_value,
        manifest=manifest,
    )
    editorial_input_package = _mapping(source_catalog["editorial_input_package"])
    project_descriptors = _mapping_list(source_catalog["project_descriptors"])
    _verify_editorial_projection(value, editorial)
    project_value = loaded_source_records["project_intelligence"].value
    if not isinstance(project_value, dict):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "project intelligence root must be an object"
        )
    try:
        project = validate_project_intelligence_projection(project_value)
    except ProjectIntelligenceValidationError as exc:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "project intelligence failed its strict projection: " + str(exc)
        ) from exc
    _verify_project_projection(value, project)
    v1_brief_path = loaded_sources["reaction_source"]
    v1_brief = _validate_bound_v1_brief_record(
        manifest,
        manifest_file,
        v1_brief_path,
        loaded_source_records["reaction_source"],
    )
    if v1_brief_path != loaded_sources["reaction_source"]:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 reaction source is not the manifest-bound V1 Brief"
        )
    if v1_brief.get("reaction_effect") != value["reaction_effect"]:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 reaction receipt differs from its bound source"
        )
    _strict_check_manifest_json_sources(manifest, manifest_file)
    radar = load_bound_mvp_radar_reader(
        manifest,
        path_base=run_dir,
        allowed_roots=(run_dir,),
    )
    if radar != value["mvp_radar"]:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 Radar projection differs from the manifest-bound reader"
        )
    compatibility_atlas_path = _bound_stage_html_path(
        manifest,
        manifest_file,
        stage_name="knowledge_atlas",
    )
    atlas_v2_path, audit_explorer_path = _validated_bound_navigation_paths(
        value.get("navigation"),
        manifest_path=manifest_file,
        allowed_source_roots=roots,
    )
    rebuilt = build_weekly_intelligence_brief_v2(
        manifest=manifest,
        manifest_path=manifest_file,
        editorial_artifact=editorial,
        editorial_input_package=editorial_input_package,
        reaction_effect=_mapping(v1_brief["reaction_effect"]),
        project_intelligence=project,
        project_descriptors=project_descriptors,
        mvp_radar=radar,
        source_artifacts=_mapping(value["source_artifacts"]),
        artifact_paths=paths,
        compatibility_atlas_path=compatibility_atlas_path,
        atlas_v2_path=atlas_v2_path,
        audit_explorer_path=audit_explorer_path,
    )
    if rebuilt != value:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 differs from its deterministic source projection"
        )
    html_lexical = Path(str(paths["html"])).expanduser().absolute()
    html_path = html_lexical.resolve(strict=True)
    source_catalog_lexical = Path(str(paths["source_catalog"])).expanduser().absolute()
    source_catalog_path = source_catalog_lexical.resolve(strict=True)
    if (
        html_lexical != html_path
        or source_catalog_lexical != source_catalog_path
        or html_path.parent != source.parent
        or html_path.name != BRIEF_V2_HTML_FILENAME
        or source_catalog_path.parent != source.parent
        or source_catalog_path.name != BRIEF_V2_SOURCE_CATALOG_FILENAME
    ):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 package uses a noncanonical artifact path"
        )
    actual_html = _read_bounded_bytes(
        html_path,
        label="Brief V2 HTML",
        maximum=MAX_HTML_BYTES,
        require_private=True,
    )
    expected_html = render_weekly_intelligence_brief_v2_html(
        value,
        manifest=manifest,
    ).encode("utf-8")
    if actual_html != expected_html:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 HTML does not match the deterministic sidecar rendering"
        )
    for name, source_path in loaded_sources.items():
        descriptor = _mapping(source_artifacts[name])
        current = _read_strict_json_record(
            source_path,
            label=f"Brief V2 dependency {name}",
            maximum=MAX_SOURCE_JSON_BYTES,
            require_private=name == "editorial_input",
        )
        if (
            current.sha256 != descriptor["sha256"]
            or current.value != loaded_source_records[name].value
        ):
            raise WeeklyIntelligenceBriefV2ArtifactError(
                f"Brief V2 dependency changed while loading: {name}"
            )
    _strict_check_manifest_json_sources(manifest, manifest_file)
    if load_bound_mvp_radar_reader(
        manifest,
        path_base=run_dir,
        allowed_roots=(run_dir,),
    ) != radar:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 Radar dependency changed while loading"
        )
    _require_reader_value_quality(
        value,
        expected_html.decode("utf-8"),
        manifest=manifest,
    )
    return value


def _require_reader_value_quality(
    sidecar: Mapping[str, object],
    rendered_html: str,
    *,
    manifest: Mapping[str, object],
) -> None:
    """Fail closed for the opt-in V2 preview without changing its sidecar."""

    from output.report_quality import (
        READER_VALUE_BLOCKING_V2,
        ReaderValueQualityError,
        evaluate_reader_report_quality,
        require_reader_report_quality,
    )

    report = evaluate_reader_report_quality(
        sidecar,
        rendered_html,
        policy_mode=READER_VALUE_BLOCKING_V2,
        manifest=manifest,
        surface=BRIEF_V2_SURFACE,
    )
    try:
        require_reader_report_quality(report)
    except ReaderValueQualityError as exc:
        codes = [
            str(finding.get("code") or "reader_value.invalid")
            for dimension in report.get("dimensions", [])
            if isinstance(dimension, Mapping)
            for finding in dimension.get("findings", [])
            if isinstance(finding, Mapping)
            and finding.get("severity") == "critical"
        ]
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 failed reader-value quality gates: "
            + ", ".join(codes[:12])
        ) from exc


def find_manifest_bound_weekly_intelligence_brief_v2(
    *,
    output_root: str | Path,
    run_id: str,
    expected_manifest_path: str | Path,
    allowed_source_roots: Sequence[str | Path] = (),
) -> dict[str, object] | None:
    """Find one exact run-scoped preview; never fall back to a week neighbor."""

    clean_run_id = str(run_id)
    if not _RUN_ID_RE.fullmatch(clean_run_id):
        raise WeeklyIntelligenceBriefV2ArtifactError("Brief V2 run_id is invalid")
    try:
        requested_output = Path(output_root).expanduser().absolute()
        canonical_output = requested_output.resolve()
        if requested_output != canonical_output:
            raise WeeklyIntelligenceBriefV2ArtifactError(
                "Brief V2 finder output root must be canonical"
            )
        if not requested_output.exists():
            return None
        output_base = canonical_output.resolve(strict=True)
        v2_root = output_base / BRIEF_V2_DIRECTORY
        if v2_root.is_symlink():
            raise WeeklyIntelligenceBriefV2ArtifactError(
                "Brief V2 finder root is not canonical"
            )
        if not v2_root.exists():
            return None
        if not v2_root.is_dir():
            raise WeeklyIntelligenceBriefV2ArtifactError(
                "Brief V2 finder root is not canonical"
            )
        run_directory = v2_root / clean_run_id
        if run_directory.is_symlink():
            raise WeeklyIntelligenceBriefV2ArtifactError(
                "Brief V2 finder run directory is not canonical"
            )
        if not run_directory.exists():
            return None
        if not run_directory.is_dir():
            raise WeeklyIntelligenceBriefV2ArtifactError(
                "Brief V2 finder run directory is not canonical"
            )
        path = run_directory / BRIEF_V2_JSON_FILENAME
    except WeeklyIntelligenceBriefV2Error:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 finder path is invalid"
        ) from exc
    if path.is_symlink():
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 finder path contains a symlink component"
        )
    if not path.exists() or not path.is_file():
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 finder found an incomplete run package"
        )
    if path.absolute() != path.resolve(strict=True):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 finder path contains a symlink component"
        )
    value = load_manifest_bound_weekly_intelligence_brief_v2(
        path,
        expected_manifest_path=expected_manifest_path,
        allowed_source_roots=allowed_source_roots,
    )
    if value.get("run_id") != clean_run_id:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 finder resolved a different run"
        )
    return value


def visible_word_count(html: str) -> int:
    """Count initially visible reader words, excluding styles and disclosures."""

    return len(_VISIBLE_WORD_RE.findall(_initially_visible_text(html)))


def _initially_visible_text(html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(str(html))
    parser.close()
    return " ".join(parser.parts)


def _reader_visible_internal_token(html: str) -> str | None:
    text = _initially_visible_text(html)
    for pattern in (
        _READER_RAW_REF_RE,
        _READER_RUN_ID_RE,
        _READER_INTERNAL_ENUM_RE,
        _READER_INTERNAL_PATH_RE,
    ):
        match = pattern.search(text)
        if match is not None:
            return match.group(0).strip()
    for phrase in _READER_INTERNAL_PHRASES:
        if phrase in text:
            return phrase
    return None


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0
        self._details_depth = 0
        self._summary_depth = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        if tag in {"style", "script", "template", "title"}:
            self._ignored_depth += 1
        elif tag == "details":
            self._details_depth += 1
        elif tag == "summary" and self._details_depth:
            self._summary_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"style", "script", "template", "title"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
        elif tag == "summary" and self._summary_depth:
            self._summary_depth -= 1
        elif tag == "details" and self._details_depth:
            self._details_depth -= 1

    def handle_data(self, data: str) -> None:
        if (
            not self._ignored_depth
            and (not self._details_depth or self._summary_depth)
            and data.strip()
        ):
            self.parts.append(data.strip())


def _validate_weekly_intelligence_brief_v2(
    value: Mapping[str, object],
    *,
    manifest: Mapping[str, object] | None = None,
    verify_metrics: bool = True,
    allow_unbound_authoritative_radar: bool = False,
) -> None:
    errors: list[str] = []
    _exact_fields(value, _ROOT_FIELDS, "root", errors)
    if value.get("schema_version") != BRIEF_V2_SCHEMA_VERSION:
        errors.append("schema_version mismatch")
    if value.get("surface") != BRIEF_V2_SURFACE:
        errors.append("surface mismatch")
    if value.get("preview_profile") != BRIEF_V2_PREVIEW_PROFILE:
        errors.append("preview_profile mismatch")
    if value.get("renderer_version") != BRIEF_V2_RENDERER_VERSION:
        errors.append("renderer_version mismatch")
    schemas = _object(value.get("source_schema_versions"), "source_schema_versions", errors)
    _exact_fields(schemas, _SOURCE_SCHEMA_FIELDS, "source_schema_versions", errors)
    expected_schemas = {
        "manifest": MANIFEST_SCHEMA_VERSION,
        "editorial": EDITORIAL_SCHEMA_VERSION,
        "editorial_input": EDITORIAL_INPUT_SCHEMA_VERSION,
        "reaction": REACTION_EFFECT_SCHEMA_VERSION,
        "project_intelligence": PROJECT_INTELLIGENCE_SCHEMA_VERSION,
        "project_permissions": PROJECT_ACTION_PERMISSIONS_SCHEMA_VERSION,
        "mvp_radar_reader": MVP_RADAR_READER_SCHEMA_VERSION,
        "report_visuals": REPORT_VISUALS_CONTRACT_VERSION,
        "brief_source_catalog": BRIEF_V2_SOURCE_CATALOG_SCHEMA_VERSION,
    }
    if schemas != expected_schemas:
        errors.append("source_schema_versions mismatch")
    run_id = value.get("run_id")
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        errors.append("run_id is invalid")
    _utc(value.get("generated_at"), "generated_at", errors)
    if value.get("period_mode") not in {"completed_iso_week", "explicit_iso_week"}:
        errors.append("Brief V2 requires a fully completed ISO week")
    period = _validate_period(value.get("reporting_period"), errors)
    if value.get("source_run_status") not in {"complete", "partial"}:
        errors.append("source_run_status must be terminal")
    if value.get("run_status") not in {"complete", "partial"}:
        errors.append("run_status is invalid")
    if not isinstance(value.get("partial"), bool):
        errors.append("partial must be boolean")
    reasons = _string_list(
        value.get("partial_reasons_ru"),
        "partial_reasons_ru",
        errors,
        maximum=12,
        russian=True,
    )
    if bool(reasons) != bool(value.get("partial")):
        errors.append("partial reasons/state mismatch")
    if value.get("run_status") != ("partial" if reasons else "complete"):
        errors.append("run_status does not match partial reasons")

    thesis = _object(value.get("weekly_thesis"), "weekly_thesis", errors)
    _exact_fields(
        thesis,
        {"title", "plain_language_summary", "why_for_operator", "confidence", "evidence_refs"},
        "weekly_thesis",
        errors,
    )
    for field in ("title", "plain_language_summary", "why_for_operator"):
        _russian_text(thesis.get(field), f"weekly_thesis.{field}", errors, 1_000)
    if thesis.get("confidence") not in _CONFIDENCE:
        errors.append("weekly_thesis.confidence is invalid")
    _refs(thesis.get("evidence_refs"), "weekly_thesis.evidence_refs", errors, 8)

    matrix = _object(value.get("decision_matrix"), "decision_matrix", errors)
    _exact_fields(matrix, set(_MATRIX_BUCKETS), "decision_matrix", errors)
    matrix_refs: list[str] = []
    matrix_rows: list[tuple[str, dict[str, object]]] = []
    primary_count = 0
    defer_count = 0
    for bucket in _MATRIX_BUCKETS:
        rows = _object_list(matrix.get(bucket), f"decision_matrix.{bucket}", errors, 3)
        for index, row in enumerate(rows):
            path = f"decision_matrix.{bucket}[{index}]"
            _exact_fields(
                row,
                {"signal_ref", "label_ru", "confidence", "evidence_maturity", "emphasis"},
                path,
                errors,
            )
            ref = _ref(row.get("signal_ref"), f"{path}.signal_ref", errors)
            if ref:
                matrix_refs.append(ref)
            _russian_text(row.get("label_ru"), f"{path}.label_ru", errors, 240)
            if row.get("confidence") not in _CONFIDENCE:
                errors.append(f"{path}.confidence is invalid")
            if row.get("evidence_maturity") not in _MATURITY:
                errors.append(f"{path}.evidence_maturity is invalid")
            emphasis = row.get("emphasis")
            if emphasis not in {"none", "primary_action", "explicit_defer"}:
                errors.append(f"{path}.emphasis is invalid")
            if emphasis == "primary_action":
                primary_count += 1
                if bucket != "act":
                    errors.append(f"{path} primary action must be in act")
            if emphasis == "explicit_defer":
                defer_count += 1
                if bucket != "ignore":
                    errors.append(f"{path} explicit defer must be in ignore")
            matrix_rows.append((bucket, row))
    if len(matrix_refs) != len(set(matrix_refs)):
        errors.append("decision_matrix contains duplicate signal refs")

    signals = _object_list(value.get("signals"), "signals", errors, 3)
    signal_refs: list[str] = []
    signal_by_ref: dict[str, dict[str, object]] = {}
    for index, signal in enumerate(signals):
        path = f"signals[{index}]"
        expected_signal_fields = {
            "signal_id",
            "decision",
            "title",
            "what_happened",
            "plain_explanation",
            "what_changed",
            "why_for_operator",
            "confidence",
            "evidence_refs",
            "reaction_effect",
            "project_implications",
            "next_action",
            "do_not_do",
            "evidence_summary",
            "action_role",
        }
        _exact_fields(signal, expected_signal_fields, path, errors)
        ref = _ref(signal.get("signal_id"), f"{path}.signal_id", errors)
        if ref:
            signal_refs.append(ref)
            signal_by_ref[ref] = signal
        if signal.get("decision") not in {"act", "study", "watch", "ignore", "verify_first"}:
            errors.append(f"{path}.decision is invalid")
        for field in (
            "title",
            "what_happened",
            "plain_explanation",
            "what_changed",
            "why_for_operator",
            "do_not_do",
        ):
            _russian_text(signal.get(field), f"{path}.{field}", errors, 1_000)
        if signal.get("confidence") not in _CONFIDENCE:
            errors.append(f"{path}.confidence is invalid")
        _refs(signal.get("evidence_refs"), f"{path}.evidence_refs", errors, 8)
        signal_reaction = _object(
            signal.get("reaction_effect"),
            f"{path}.reaction_effect",
            errors,
        )
        _exact_fields(
            signal_reaction,
            {"effect", "reader_reason_ru"},
            f"{path}.reaction_effect",
            errors,
        )
        if signal_reaction.get("effect") not in {
            "none",
            "linked_only",
            "rank_changed",
            "selection_changed",
        }:
            errors.append(f"{path}.reaction_effect.effect is invalid")
        _russian_text(
            signal_reaction.get("reader_reason_ru"),
            f"{path}.reaction_effect.reader_reason_ru",
            errors,
            500,
        )
        _refs(
            signal.get("project_implications"),
            f"{path}.project_implications",
            errors,
            2,
        )
        next_action = _object(
            signal.get("next_action"),
            f"{path}.next_action",
            errors,
        )
        _exact_fields(
            next_action,
            {"title", "acceptance_criteria"},
            f"{path}.next_action",
            errors,
        )
        _russian_text(
            next_action.get("title"),
            f"{path}.next_action.title",
            errors,
            400,
        )
        next_criteria = _string_list(
            next_action.get("acceptance_criteria"),
            f"{path}.next_action.acceptance_criteria",
            errors,
            maximum=5,
            russian=True,
        )
        if not next_criteria:
            errors.append(f"{path}.next_action.acceptance_criteria is empty")
        if signal.get("action_role") not in {"primary", "secondary", "not_selected"}:
            errors.append(f"{path}.action_role is invalid")
        _validate_evidence_summary(signal.get("evidence_summary"), path, errors)
        evidence_summary = _mapping(signal.get("evidence_summary"))
        evidence_items = _mapping_list(evidence_summary.get("items"))
        if [str(item.get("evidence_ref") or "") for item in evidence_items] != [
            str(item) for item in signal.get("evidence_refs") or []
        ]:
            errors.append(f"{path}.evidence_summary items differ from evidence_refs")
        if evidence_items:
            rebuilt_summary = _evidence_summary(evidence_items)
            if evidence_summary != rebuilt_summary:
                errors.append(f"{path}.evidence_summary is not deterministic")
    if len(signal_refs) != len(set(signal_refs)):
        errors.append("signals contain duplicate refs")
    if set(signal_refs) != set(matrix_refs):
        errors.append("decision_matrix must exactly cover signals")
    for bucket, row in matrix_rows:
        signal = signal_by_ref.get(str(row.get("signal_ref") or ""))
        if signal is None:
            continue
        if _matrix_bucket(signal.get("decision")) != bucket:
            errors.append("decision_matrix bucket differs from signal decision")
        if row.get("confidence") != signal.get("confidence"):
            errors.append("decision_matrix confidence differs from signal")
        maturity = _mapping(signal.get("evidence_summary")).get(
            "evidence_maturity"
        )
        if row.get("evidence_maturity") != maturity:
            errors.append("decision_matrix maturity differs from signal")

    actions = _object(value.get("actions"), "actions", errors)
    _exact_fields(actions, {"primary", "secondary"}, "actions", errors)
    primary = actions.get("primary")
    if primary is not None:
        _validate_action(primary, "actions.primary", errors, role="primary")
    secondary = _object_list(actions.get("secondary"), "actions.secondary", errors, 2)
    for index, action in enumerate(secondary):
        _validate_action(action, f"actions.secondary[{index}]", errors, role="secondary")
    if signals and not reasons:
        if primary is None or primary_count != 1 or defer_count != 1:
            errors.append("complete non-empty Brief requires one primary and one defer")
    if not signals and (primary is not None or secondary or matrix_refs):
        errors.append("zero-signal Brief cannot contain actions or decisions")
    selected_action_refs: list[str] = []
    action_rows = (
        [("primary", dict(primary))] if isinstance(primary, Mapping) else []
    ) + [("secondary", action) for action in secondary]
    for role, action in action_rows:
        ref = str(action.get("signal_ref") or "")
        selected_action_refs.append(ref)
        signal = signal_by_ref.get(ref)
        if signal is None:
            errors.append(f"actions.{role} cites an unknown signal")
            continue
        expected = _mapping(signal.get("next_action"))
        if (
            action.get("title") != expected.get("title")
            or action.get("acceptance_criteria")
            != expected.get("acceptance_criteria")
        ):
            errors.append(f"actions.{role} differs from the signal next action")
        if signal.get("action_role") != role:
            errors.append(f"actions.{role} differs from signal action_role")
    if len(selected_action_refs) != len(set(selected_action_refs)):
        errors.append("actions contain duplicate signal refs")
    for ref, signal in signal_by_ref.items():
        role = str(signal.get("action_role") or "")
        if role == "not_selected" and ref in selected_action_refs:
            errors.append("not-selected signal is present in actions")
        if role in {"primary", "secondary"} and ref not in selected_action_refs:
            errors.append("selected signal is missing from actions")

    reaction: Mapping[str, object] = {}
    try:
        reaction = validate_reaction_effect(_mapping(value.get("reaction_effect")))
        if run_id and reaction.get("run_id") != run_id:
            errors.append("reaction_effect run_id mismatch")
        if period and any(reaction.get(field) != period[field] for field in _PERIOD_FIELDS):
            errors.append("reaction_effect period mismatch")
    except (ReactionPersonalizationError, TypeError, ValueError) as exc:
        errors.append(f"reaction_effect invalid: {exc}")
    _validate_feedback_effect(value.get("feedback_effect"), errors)
    project_actions = _object_list(value.get("project_actions"), "project_actions", errors, 2)
    for index, action in enumerate(project_actions):
        _validate_project_action(action, f"project_actions[{index}]", errors)
    project_refs = [
        str(action.get("project_action_ref") or "") for action in project_actions
    ]
    signal_project_refs = [
        str(ref)
        for signal in signals
        for ref in signal.get("project_implications") or []
    ]
    if project_refs != signal_project_refs:
        errors.append("project_actions differ from signal project implications")
    if any(
        str(action.get("signal_id") or "") not in signal_by_ref
        for action in project_actions
    ):
        errors.append("project_actions contain an unselected signal")
    radar = _mapping(value.get("mvp_radar"))
    try:
        if manifest is not None and radar.get("reader_state") in {"available", "no_candidate"}:
            validate_mvp_radar_reader_projection(radar, manifest=manifest)
        elif (
            radar.get("reader_state") in {"available", "no_candidate"}
            and not allow_unbound_authoritative_radar
        ):
            raise MvpRadarReaderError(
                "authoritative Radar reader requires the current run manifest"
            )
        else:
            validate_mvp_radar_reader_projection(
                radar,
                _require_succeeded_stage=False,
            )
    except (MvpRadarReaderError, TypeError, ValueError) as exc:
        errors.append(f"mvp_radar invalid: {exc}")
    requires_partial = (
        (manifest is not None and manifest.get("run_status") == "partial")
        or reaction.get("snapshot_status") != "complete"
        or reaction.get("status") in {"partial", "unavailable"}
        or radar.get("reader_state") not in {"available", "no_candidate"}
        or radar.get("partial") is True
    )
    if requires_partial and value.get("partial") is not True:
        errors.append("upstream unavailable state requires a partial Brief")

    targets = _object_list(value.get("feedback_targets"), "feedback_targets", errors, 5)
    if len(targets) != 5:
        errors.append("feedback_targets must contain five prompts")
    for index, target in enumerate(targets):
        _validate_feedback_target(target, f"feedback_targets[{index}]", errors)
    if isinstance(run_id, str) and targets != _feedback_targets(
        run_id,
        signals,
        project_actions,
    ):
        errors.append("feedback_targets differ from the deterministic projection")
    specs = _object_list(value.get("visual_specs"), "visual_specs", errors, 4)
    if len(specs) != 4:
        errors.append("visual_specs must contain four Brief component specs")
    component_types: list[str] = []
    for index, spec in enumerate(specs):
        try:
            component_types.append(validate_report_visual(spec))
        except (ReportVisualValidationError, TypeError, ValueError) as exc:
            errors.append(f"visual_specs[{index}] invalid: {exc}")
    if component_types != [
        "decision_matrix",
        "reaction_funnel",
        "project_impact",
        "radar_gate",
    ]:
        errors.append("visual_specs component order mismatch")
    root_evidence_refs = _refs(
        value.get("evidence_refs"),
        "evidence_refs",
        errors,
        40,
    )
    expected_evidence_refs = _unique_text(
        [
            *[
                ref
                for signal in signals
                for ref in signal.get("evidence_refs") or []
            ],
            *[
                ref
                for action in project_actions
                for ref in action.get("evidence_refs") or []
            ],
        ]
    )
    if root_evidence_refs != expected_evidence_refs:
        errors.append("evidence_refs differ from reader records")
    if isinstance(run_id, str) and period and not errors:
        expected_specs = _visual_specs(
            run_id=run_id,
            period=period,
            decision_items=[
                {"decision": bucket, **row} for bucket, row in matrix_rows
            ],
            reaction_effect=reaction,
            selected_reaction_count=_selected_reaction_count(signals),
            project_actions=project_actions,
            mvp_radar=radar,
            signal_titles={
                str(signal.get("signal_id") or ""): str(
                    signal.get("title") or ""
                )
                for signal in signals
            },
            decision_contract_complete=(
                not signals or (primary is not None and defer_count == 1)
            ),
        )
        if specs != expected_specs:
            errors.append("visual_specs differ from the deterministic projection")
    _validate_navigation(value.get("navigation"), str(run_id or ""), errors)
    _validate_technical_refs(value.get("technical_refs"), errors)
    navigation_value = _mapping(value.get("navigation"))
    technical_value = _mapping(value.get("technical_refs"))
    if technical_value.get("audit_explorer_path") != _mapping(
        navigation_value.get("audit_explorer")
    ).get("path"):
        errors.append("technical_refs.audit_explorer_path differs from navigation")
    if technical_value.get("compatibility_atlas_path") != _mapping(
        navigation_value.get("compatibility_atlas")
    ).get("path"):
        errors.append("technical_refs.compatibility_atlas_path differs from navigation")
    _validate_source_artifacts(value.get("source_artifacts"), errors)
    _validate_artifact_paths(value.get("artifact_paths"), errors)
    _validate_content_metrics(value.get("content_metrics"), specs, errors)
    metrics = _mapping(value.get("content_metrics"))
    if verify_metrics and metrics.get("word_budget_status") == "pending":
        errors.append("content_metrics cannot remain pending")
    if verify_metrics and metrics.get("word_budget_status") == "critical":
        errors.append("Brief V2 exceeds the hard visible-word limit")
    if (
        verify_metrics
        and metrics.get("word_budget_status") in {"short", "warning"}
        and value.get("partial") is not True
    ):
        errors.append("Brief V2 outside the target word range must be partial")
    if manifest is not None:
        try:
            _require_sidecar_manifest_identity(value, manifest)
        except WeeklyIntelligenceBriefV2Error as exc:
            errors.append(str(exc))
    if not errors:
        html = _render_document(value)
        internal_token = _reader_visible_internal_token(html)
        if internal_token is not None:
            errors.append(
                "reader-visible copy exposes an internal token: "
                + internal_token
            )
        if verify_metrics:
            measured = visible_word_count(html)
            if metrics.get("visible_word_count") != measured:
                errors.append("content_metrics.visible_word_count mismatch")
            if metrics.get("word_budget_status") != _word_budget_status(measured):
                errors.append("content_metrics.word_budget_status mismatch")
    if errors:
        raise WeeklyIntelligenceBriefV2ValidationError(errors)


def _reader_signals(
    editorial: Mapping[str, object],
    evidence_catalog: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw_signal in _mapping_list(editorial.get("signals"))[:3]:
        signal = copy.deepcopy(dict(raw_signal))
        refs = [str(value) for value in signal.get("evidence_refs") or []]
        evidence = []
        for ref in refs:
            if ref not in evidence_catalog:
                raise WeeklyIntelligenceBriefV2ValidationError(
                    [f"signal {signal.get('signal_id')} cites unknown evidence {ref}"]
                )
            item = copy.deepcopy(dict(evidence_catalog[ref]))
            item["reader_label_ru"] = _reader_evidence_label(item)
            evidence.append(item)
        summary = _evidence_summary(evidence)
        signal["evidence_summary"] = summary
        signal["action_role"] = "not_selected"
        rows.append(signal)
    return rows


def _reader_decision_matrix(
    editorial: Mapping[str, object],
    *,
    signal_by_ref: Mapping[str, Mapping[str, object]],
) -> tuple[dict[str, list[dict[str, object]]], list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {bucket: [] for bucket in _MATRIX_BUCKETS}
    flat: list[dict[str, object]] = []
    ordered = list(signal_by_ref.items())
    first_act = next(
        (
            ref
            for ref, signal in ordered
            if _matrix_bucket(signal.get("decision")) == "act"
        ),
        None,
    )
    first_ignore = next(
        (
            ref
            for ref, signal in ordered
            if _matrix_bucket(signal.get("decision")) == "ignore"
        ),
        None,
    )
    for ref, signal in ordered:
        bucket = _matrix_bucket(signal.get("decision"))
        if bucket not in result:
            raise WeeklyIntelligenceBriefV2ValidationError(
                [f"signal decision has no reader matrix bucket: {bucket}"]
            )
        item = {
            "signal_ref": ref,
            "label_ru": _decision_copy(bucket, str(signal["title"])),
            "confidence": str(signal["confidence"]),
            "evidence_maturity": str(
                _mapping(signal["evidence_summary"])["evidence_maturity"]
            ),
            "emphasis": (
                "primary_action"
                if bucket == "act" and ref == first_act
                else "explicit_defer"
                if bucket == "ignore" and ref == first_ignore
                else "none"
            ),
        }
        result[bucket].append(item)
        flat.append({"decision": bucket, **item})
    return result, flat


def _reader_actions(
    editorial: Mapping[str, object],
    *,
    signal_by_ref: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    primary_ref = next(
        (
            ref
            for ref, signal in signal_by_ref.items()
            if _matrix_bucket(signal.get("decision")) == "act"
        ),
        None,
    )
    primary = (
        _action_from_signal(signal_by_ref[primary_ref], role="primary")
        if primary_ref in signal_by_ref
        else None
    )
    secondary: list[dict[str, object]] = []
    if primary is not None:
        for raw_signal in _mapping_list(editorial.get("signals")):
            ref = str(raw_signal.get("signal_id") or "")
            if ref == primary_ref or ref not in signal_by_ref:
                continue
            if str(raw_signal.get("decision") or "") == "ignore":
                continue
            secondary.append(_action_from_signal(signal_by_ref[ref], role="secondary"))
            if len(secondary) == 2:
                break
    selected = {
        str(primary["signal_ref"]) if primary else "": "primary",
        **{str(item["signal_ref"]): "secondary" for item in secondary},
    }
    for ref, signal in signal_by_ref.items():
        if isinstance(signal, dict):
            signal["action_role"] = selected.get(ref, "not_selected")
    return {"primary": primary, "secondary": secondary}


def _action_from_signal(
    signal: Mapping[str, object], *, role: str
) -> dict[str, object]:
    action = _mapping(signal.get("next_action"))
    return {
        "role": role,
        "signal_ref": str(signal["signal_id"]),
        "title": str(action.get("title") or ""),
        "acceptance_criteria": [str(value) for value in action.get("acceptance_criteria") or []],
    }


def _reader_project_actions(
    editorial: Mapping[str, object],
    project: Mapping[str, object],
    *,
    signal_by_ref: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    selected_refs = [str(value) for value in editorial.get("project_actions") or []]
    action_by_ref = {
        str(item.get("project_action_ref")): item
        for item in _mapping_list(project.get("confirmed_actions"))
    }
    rows: list[dict[str, object]] = []
    for ref in selected_refs:
        action = action_by_ref.get(ref)
        if action is None:
            raise WeeklyIntelligenceBriefV2ValidationError(
                [f"editorial project action is not confirmed: {ref}"]
            )
        signal_ref = str(action.get("signal_id") or "")
        if signal_ref not in signal_by_ref:
            raise WeeklyIntelligenceBriefV2ValidationError(
                [f"project action cites an unselected signal: {signal_ref}"]
            )
        rows.append(copy.deepcopy(dict(action)))
    return rows


def _evidence_summary(evidence: Sequence[Mapping[str, object]]) -> dict[str, object]:
    independent = max(
        (
            int(_mapping(item.get("source_independence")).get("count") or 0)
            for item in evidence
        ),
        default=0,
    )
    decision_grade = bool(evidence) and all(
        item.get("decision_grade") is True for item in evidence
    )
    primary_verified = any(
        str(item.get("verification_status") or "").casefold()
        == "primary_verified"
        or str(item.get("evidence_tier") or "").casefold()
        == "verified_primary"
        for item in evidence
    )
    if decision_grade and independent >= 2:
        maturity = "decision_grade"
    elif primary_verified:
        maturity = "primary_verified"
    elif independent >= 2:
        maturity = "multi_channel"
    elif len(evidence) >= 2:
        maturity = "repeated_signal"
    else:
        maturity = "single_source"
    confidence = (
        "Доказательства связаны с несколькими независимыми источниками."
        if independent >= 2
        else "Независимое подтверждение пока ограничено."
    )
    limitations = _unique_text(
        [
            str(reason)
            for item in evidence
            for reason in item.get("uncertainty_reasons") or []
            if str(reason).strip()
        ]
    )[:4]
    return {
        "evidence_maturity": maturity,
        "independent_source_count": independent,
        "confidence_reason_ru": confidence,
        "items": [copy.deepcopy(dict(item)) for item in evidence],
        "limitations": limitations,
    }


def _reader_evidence_label(item: Mapping[str, object]) -> str:
    statement = str(item.get("statement") or "").strip()
    if statement and _CYRILLIC_RE.search(statement):
        return statement
    excerpt = str(item.get("verified_excerpt") or "").strip()
    if excerpt and _CYRILLIC_RE.search(excerpt):
        return excerpt
    return "Проверяемое доказательство сохранено в техническом аудите выпуска."


def _visual_specs(
    *,
    run_id: str,
    period: Mapping[str, str],
    decision_items: Sequence[Mapping[str, object]],
    reaction_effect: Mapping[str, object],
    selected_reaction_count: int,
    project_actions: Sequence[Mapping[str, object]],
    mvp_radar: Mapping[str, object],
    signal_titles: Mapping[str, str],
    decision_contract_complete: bool,
) -> list[dict[str, object]]:
    common = {
        "run_id": run_id,
        **period,
    }
    manifest_ref = f"manifest:{run_id}"
    if decision_items and decision_contract_complete:
        decision_status = "available"
        decision_rows = [copy.deepcopy(dict(item)) for item in decision_items]
        decision_extra: dict[str, object] = {}
        decision_refs = _unique_text(
            [
                str(item.get("signal_ref"))
                for item in decision_items
                if str(item.get("signal_ref") or "")
            ]
        )
    elif not decision_items:
        decision_status = "empty"
        decision_rows = []
        decision_extra = {}
        decision_refs = [manifest_ref]
    else:
        decision_status = "unavailable"
        decision_rows = []
        decision_extra = {
            "state_reason_ru": (
                "Редакционный контракт не выделил одновременно основное действие "
                "и явное решение, которое нужно отложить."
            )
        }
        decision_refs = []
    decision = {
        "schema_version": "report_visual.decision_matrix.v1",
        "component_id": "brief-v2-decision-matrix",
        "title_ru": "Матрица решений недели",
        "summary_ru": "Сигналы распределены по четырём явным вариантам решения.",
        **common,
        "data_status": decision_status,
        "source_refs": decision_refs,
        "data_note_ru": "Матрица повторяет проверенный редакционный выбор и не ранжирует сигналы заново.",
        "items": decision_rows,
        **decision_extra,
    }
    reaction = _reaction_visual(
        reaction_effect,
        selected_reaction_count=selected_reaction_count,
        common=common,
        manifest_ref=manifest_ref,
    )
    project = _project_visual(
        project_actions,
        common=common,
        manifest_ref=manifest_ref,
        signal_titles=signal_titles,
    )
    radar = _radar_visual(mvp_radar, common=common, manifest_ref=manifest_ref)
    return [decision, reaction, project, radar]


def _reaction_visual(
    receipt: Mapping[str, object],
    *,
    selected_reaction_count: int,
    common: Mapping[str, object],
    manifest_ref: str,
) -> dict[str, object]:
    counts = _mapping(receipt.get("counts"))
    status = str(receipt.get("status") or "unavailable")
    snapshot = str(receipt.get("snapshot_status") or "unavailable")
    events = int(counts.get("personal_reaction_events_detected") or 0)
    complete = snapshot == "complete" and status in {
        "effects_applied",
        "linked_no_selection_effect",
        "no_eligible_reactions",
    }
    if complete and events == 0:
        data_status = "empty"
        stages: list[dict[str, object]] = []
        reasons: list[str] = []
        snapshot_status = "complete"
        extra: dict[str, object] = {}
    elif complete:
        data_status = "available"
        stages = [
            {"key": "detected", "label_ru": "Реакции", "count": events},
            {
                "key": "posts_resolved",
                "label_ru": "Посты найдены",
                "count": int(counts.get("posts_resolved") or 0),
            },
            {
                "key": "atoms_linked",
                "label_ru": "Связаны с атомами",
                "count": int(counts.get("unique_atoms_linked") or 0),
            },
            {
                "key": "threads_linked",
                "label_ru": "Связаны с темами",
                "count": int(counts.get("unique_compatibility_threads_linked") or 0),
            },
            {
                "key": "signals_selected",
                "label_ru": "Повлияли на сигналы",
                "count": selected_reaction_count,
            },
        ]
        reasons = [
            f"{_REACTION_REASON_LABELS.get(str(reason), 'Часть событий не была использована.')} Событий: {count}."
            for reason, count in sorted(_mapping(receipt.get("unconsumed_by_reason")).items())
        ]
        snapshot_status = "complete"
        extra = {}
    else:
        data_status = "unavailable"
        stages = []
        reasons = []
        snapshot_status = "failed"
        extra = {
            "state_reason_ru": (
                "Снимок влияния личных реакций недоступен или неполон; "
                "персонализация не показана как свежая."
            )
        }
    return {
        "schema_version": "report_visual.reaction_funnel.v1",
        "component_id": "brief-v2-reaction-funnel",
        "title_ru": "Как реакции повлияли на бриф",
        "summary_ru": "Цепочка показывает связь отметок с постами, атомами, темами и выбранными сигналами.",
        **common,
        "data_status": data_status,
        "source_refs": [manifest_ref] if data_status != "unavailable" else [],
        "data_note_ru": "Отсутствие реакции означает неизвестный интерес, а не отрицательную оценку.",
        "snapshot_status": snapshot_status,
        "stages": stages,
        "unconsumed_reasons": reasons,
        **extra,
    }


def _selected_reaction_count(
    signals: Sequence[Mapping[str, object]],
) -> int:
    return sum(
        str(_mapping(signal.get("reaction_effect")).get("effect") or "none")
        in {"rank_changed", "selection_changed"}
        for signal in signals
    )


def _project_visual(
    actions: Sequence[Mapping[str, object]],
    *,
    common: Mapping[str, object],
    manifest_ref: str,
    signal_titles: Mapping[str, str],
) -> dict[str, object]:
    rows = []
    for action in actions:
        signal_ref = str(action.get("signal_id") or "")
        rows.append(
            {
                "project_name": str(action.get("project_name") or ""),
                "signal_ref": signal_ref,
                "signal_label_ru": signal_titles.get(
                    signal_ref,
                    "Проверяемый сигнал текущего выпуска",
                ),
                "suggested_change_ru": str(action.get("suggested_change") or ""),
                "affected_component": str(action.get("affected_component") or ""),
                "likely_files": [str(value) for value in action.get("likely_files") or []],
                "effort": _EFFORT_LABELS.get(
                    str(action.get("effort") or ""),
                    "Оценка требует отдельного уточнения",
                ),
                "confidence": str(action.get("confidence") or "medium"),
                "acceptance_criteria": [
                    str(value) for value in action.get("acceptance_criteria") or []
                ],
                "risk_ru": str(action.get("risk") or ""),
                "evidence_refs": [str(value) for value in action.get("evidence_refs") or []],
                "status": "confirmed",
            }
        )
    return {
        "schema_version": "report_visual.project_impact.v1",
        "component_id": "brief-v2-project-impact",
        "title_ru": "Влияние на проекты",
        "summary_ru": "Показаны только действия с точным разрешением проекта и доказательствами текущего запуска.",
        **common,
        "data_status": "available" if rows else "empty",
        "source_refs": (
            _unique_text([ref for row in rows for ref in row["evidence_refs"]])
            if rows
            else [manifest_ref]
        ),
        "data_note_ru": "Слабые совпадения и существующий контекст не превращаются в проектное действие.",
        "items": rows,
    }


def _radar_visual(
    radar: Mapping[str, object],
    *,
    common: Mapping[str, object],
    manifest_ref: str,
) -> dict[str, object]:
    state = str(radar.get("reader_state") or "invalid")
    if state == "no_candidate":
        return {
            "schema_version": "report_visual.radar_gate.v1",
            "component_id": "brief-v2-radar-gate",
            "title_ru": "Решение MVP Radar",
            "summary_ru": "Radar завершил запуск, но не выбрал кандидата.",
            **common,
            "data_status": "empty",
            "source_refs": [manifest_ref],
            "data_note_ru": "Успешное отсутствие кандидата не заменяется соседним или прошлым результатом.",
            "snapshot_status": "complete",
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
    if state != "available":
        return {
            "schema_version": "report_visual.radar_gate.v1",
            "component_id": "brief-v2-radar-gate",
            "title_ru": "Решение MVP Radar",
            "summary_ru": "Связанный результат Radar не даёт решения по кандидату.",
            **common,
            "data_status": "unavailable",
            "source_refs": [],
            "state_reason_ru": (
                "MVP Radar отключён для этого запуска. Решение по сборке не сформировано."
                if state == "disabled"
                else "Связанный результат MVP Radar недоступен или не прошёл проверку."
            ),
            "data_note_ru": "Несвязанные и соседние файлы Radar не используются как решение.",
            "snapshot_status": "failed",
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
    source_mix = _mapping(radar.get("source_mix"))
    kir_status = str(source_mix.get("kir_gate_status") or "missing_kir_thread")
    kir_gate_status = (
        "not_applicable"
        if kir_status == "not_required"
        else "pass"
        if kir_status == "passed"
        else "blocked"
        if kir_status in {"blocking_risk", "profile_mismatch"}
        else "missing"
    )
    external_passed = source_mix.get("decision_grade_external") is True
    decision = str(radar.get("reader_decision") or "unavailable")
    dossier_raw = str(radar.get("dossier_status") or "investigate")
    dossier = (
        "build_allowed"
        if dossier_raw == "build" and decision == "build_allowed"
        else "focused_experiment"
        if dossier_raw == "focused_experiment" and decision == "investigate"
        else "reject"
        if dossier_raw == "reject" and decision == "reject"
        else "investigate"
    )
    decision_gate_status = (
        "pass"
        if decision == "build_allowed" or dossier == "focused_experiment"
        else "blocked"
        if decision == "reject"
        else "missing"
    )
    gates = [
        {
            "key": "kir_provenance",
            "status": kir_gate_status,
            "reason_ru": _KIR_REASON_LABELS.get(
                kir_status,
                "Статус KIR-проверки требует отдельного просмотра.",
            ),
        },
        {
            "key": "external_evidence",
            "status": "pass" if external_passed else "missing",
            "reason_ru": (
                "Есть минимум два независимых типа внешних доказательств достаточной зрелости."
                if external_passed
                else "Не хватает двух независимых типов внешних доказательств достаточной зрелости."
            ),
        },
        {
            "key": "context_isolation",
            "status": "pass",
            "reason_ru": "Рыночный и несвязанный контекст отделён от доказательств кандидата.",
        },
        {
            "key": "reader_decision",
            "status": decision_gate_status,
            "reason_ru": str(radar.get("decision_reason_ru") or "Решение Radar проверено."),
        },
    ]
    missing = [
        _russian_or_placeholder(value, index, "пробел доказательств")
        for index, value in enumerate(radar.get("missing_evidence") or [], start=1)
    ]
    kill = [
        _russian_or_placeholder(value, index, "критерий остановки")
        for index, value in enumerate(radar.get("kill_criteria") or [], start=1)
    ]
    return {
        "schema_version": "report_visual.radar_gate.v1",
        "component_id": "brief-v2-radar-gate",
        "title_ru": "Решение MVP Radar",
        "summary_ru": "Доказательства кандидата отделены от контекста, который не заполняет гейты.",
        **common,
        "data_status": "available",
        "source_refs": [f"radar:{radar.get('radar_run_id') or common['run_id']}"],
        "data_note_ru": "Только решение Radar, связанное с манифестом текущего запуска, может разрешить сборку.",
        "snapshot_status": "complete",
        "candidate_name": str(radar.get("selected_candidate") or ""),
        "dossier_status": dossier,
        "reader_decision": decision,
        "gates": gates,
        "candidate_evidence_count": len(radar.get("matched_external_proof") or []),
        "context_only_count": len(radar.get("unmatched_context") or []),
        "missing_evidence": missing,
        "next_validation_ru": _russian_or_placeholder(
            radar.get("next_validation"), 1, "следующая проверка"
        ),
        "kill_criteria_ru": (
            " ".join(kill)[:500]
            if kill
            else "Остановить проверку, если кандидат не проходит заявленные гейты."
        ),
    }


def _partial_reasons(
    manifest: Mapping[str, object],
    editorial: Mapping[str, object],
    reaction: Mapping[str, object],
    radar: Mapping[str, object],
    *,
    signal_count: int,
    has_primary: bool,
    has_defer: bool,
) -> list[str]:
    reasons: list[str] = []
    if manifest.get("run_status") == "partial" or manifest.get("partial") is True:
        stages = _mapping(manifest.get("stages"))
        unavailable = [
            _STAGE_LABELS_RU.get(str(name), str(name).replace("_", " "))
            for name, raw_stage in stages.items()
            if _mapping(raw_stage).get("enabled") is True
            and _mapping(raw_stage).get("status") != SUCCEEDED
        ]
        reasons.append(
            "Базовый недельный запуск завершился частично"
            + (
                "; недоступны этапы: " + ", ".join(unavailable[:6]) + "."
                if unavailable
                else "."
            )
        )
    if editorial.get("partial") is True:
        reasons.append("Редакционный синтез доступен только в частичном режиме.")
    if reaction.get("snapshot_status") != "complete" or reaction.get("status") in {
        "partial",
        "unavailable",
    }:
        reasons.append("Данные о влиянии личных реакций неполны.")
    radar_state = str(radar.get("reader_state") or "invalid")
    if radar_state == "disabled":
        reasons.append(
            "MVP Radar отключён для этого запуска; решение по сборке не сформировано."
        )
    elif radar_state not in {"available", "no_candidate"} or radar.get("partial") is True:
        reasons.append("Связанный результат MVP Radar недоступен или не прошёл проверку.")
    if signal_count and not has_primary:
        reasons.append("Редакционный контракт не выделил основное действие недели.")
    if signal_count and not has_defer:
        reasons.append("Редакционный контракт не выделил решение, которое нужно отложить.")
    return _unique_text(reasons)


def _feedback_targets(
    run_id: str,
    signals: Sequence[Mapping[str, object]],
    project_actions: Sequence[Mapping[str, object]],
) -> list[dict[str, str]]:
    first_signal = str(signals[0].get("signal_id") or f"brief:{run_id}") if signals else f"brief:{run_id}"
    first_project = (
        str(project_actions[0].get("project_action_ref") or f"brief:{run_id}")
        if project_actions
        else f"brief:{run_id}"
    )
    signal_target_type = "signal" if signals else "weekly_brief"
    project_target_type = "project_action" if project_actions else "weekly_brief"
    rows = [
        ("useful", "weekly_brief", f"brief:{run_id}", "Что было полезно?"),
        ("priority", signal_target_type, first_signal, "Какой приоритет выбран неверно?"),
        ("depth", signal_target_type, first_signal, "Где объяснение слишком поверхностное?"),
        ("action", project_target_type, first_project, "Какое действие вы выполнили?"),
        ("next", "weekly_brief", f"brief:{run_id}", "Что изменить в следующем выпуске?"),
    ]
    return [
        {
            "id": "feedback:" + hashlib.sha256(
                f"{run_id}\0{key}\0{target_ref}".encode("utf-8")
            ).hexdigest()[:24],
            "target_type": target_type,
            "target_ref": target_ref,
            "prompt_ru": prompt,
        }
        for key, target_type, target_ref, prompt in rows
    ]


def _render_document(value: Mapping[str, object]) -> str:
    period = _mapping(value["reporting_period"])
    signals = _mapping_list(value["signals"])
    thesis = _mapping(value["weekly_thesis"])
    actions = _mapping(value["actions"])
    visuals = [render_report_visual(spec).html for spec in _mapping_list(value["visual_specs"])]
    navigation = _mapping(value["navigation"])
    partial_banner = (
        '<aside class="brief-v2__partial" role="alert"><strong>Выпуск частичный.</strong><ul>'
        + "".join(f"<li>{_e(reason)}</li>" for reason in value["partial_reasons_ru"])
        + "</ul></aside>"
        if value["partial"]
        else ""
    )
    status_label = "Частичный выпуск" if value["partial"] else "Полный выпуск"
    atlas_navigation = _render_navigation_item(_mapping(navigation["atlas_v2"]))
    action_html = _render_actions(actions)
    signals_html = "".join(_render_signal(signal) for signal in signals)
    feedback_html = _render_feedback_effect(_mapping(value["feedback_effect"]))
    reaction_snapshot_html = _render_reaction_snapshot_status(
        _mapping(value["reaction_effect"])
    )
    radar_html = _render_radar_context(_mapping(value["mvp_radar"]))
    prompts = "".join(
        '<li class="brief-v2__prompt" data-feedback-target="{target}">{prompt}</li>'.format(
            target=_e(item["target_ref"]),
            prompt=_e(item["prompt_ru"]),
        )
        for item in _mapping_list(value["feedback_targets"])
    )
    technical = _mapping(value["technical_refs"])
    technical_links = _render_technical_links(technical)
    visual_by_type = {
        str(spec["schema_version"]).split(".")[1]: html
        for spec, html in zip(_mapping_list(value["visual_specs"]), visuals)
    }
    styles = _brief_styles() + "\n" + report_visual_styles()
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
<meta name="brief-schema-version" content="{_e(value['schema_version'])}">
<meta name="brief-renderer-version" content="{_e(value['renderer_version'])}">
<meta name="brief-run-id" content="{_e(value['run_id'])}">
<title>Еженедельный аналитический бриф — {_e(period['reporting_week'])}</title>
<style>{styles}</style>
</head>
<body>
<header class="brief-v2__header">
<p class="brief-v2__kicker">Недельный бриф V2</p>
<h1>Еженедельный аналитический бриф</h1>
<div class="brief-v2__header-grid">
<p><strong>Завершённый период:</strong> {_e(_human_period(period))}</p>
<p><strong>Сформирован:</strong> {_e(_human_timestamp(value['generated_at']))}</p>
<p><strong>Статус:</strong> <span class="brief-v2__status">{_e(status_label)}</span></p>
</div>
<nav aria-label="Навигация выпуска">{atlas_navigation}<a href="#brief-decisions">Решения</a><a href="#brief-signals">Сигналы</a><a href="#brief-radar">MVP Radar</a></nav>
<details class="brief-v2__technical"><summary>Технические детали</summary>{technical_links}</details>
</header>
<main class="irx-report brief-v2">
{partial_banner}
<section class="brief-v2__section brief-v2__thesis" id="brief-thesis">
<p class="brief-v2__eyebrow">Главный вывод недели</p>
<h2>{_e(thesis['title'])}</h2>
<p>{_e(thesis['plain_language_summary'])}</p>
<p><strong>Почему это важно вам:</strong> {_e(thesis['why_for_operator'])}</p>
<p class="brief-v2__meta"><strong>Уверенность:</strong> {_e(_CONFIDENCE_LABELS[str(thesis['confidence'])])}. Основание сохранено в {_e(len(thesis['evidence_refs']))} проверяемых ссылках выпуска.</p>
</section>
<section class="brief-v2__section" id="brief-decisions">
{visual_by_type['decision_matrix']}
{action_html}
</section>
<section class="brief-v2__section" id="brief-signals">
<p class="brief-v2__eyebrow">Главные сигналы</p>
<h2>Что изменилось и почему это важно</h2>
{signals_html if signals_html else '<p class="brief-v2__empty">Подтверждённых изменений для читательского выпуска нет. Нулевой результат не заменён общими советами.</p>'}
</section>
<section class="brief-v2__section" id="brief-personalization">
{reaction_snapshot_html}
{visual_by_type['reaction_funnel']}
{feedback_html}
</section>
<section class="brief-v2__section" id="brief-projects">
{visual_by_type['project_impact']}
</section>
<section class="brief-v2__section" id="brief-radar">
{radar_html}
{visual_by_type['radar_gate']}
</section>
<section class="brief-v2__section" id="brief-feedback">
<p class="brief-v2__eyebrow">Обратная связь по выпуску</p>
<h2>Что уточнить к следующей неделе</h2>
<ul class="brief-v2__prompts">{prompts}</ul>
</section>
</main>
</body>
</html>
"""


def _render_actions(actions: Mapping[str, object]) -> str:
    primary = actions.get("primary")
    secondary = _mapping_list(actions.get("secondary"))
    if not isinstance(primary, Mapping):
        return (
            '<div class="brief-v2__action-state"><strong>Основное действие не сформировано.</strong> '
            "Выпуск не подменяет его общим советом.</div>"
        )
    cards = [
        '<article class="brief-v2__action brief-v2__action--primary"><p class="brief-v2__eyebrow">Основное действие недели</p>'
        f"<h3>{_e(primary['title'])}</h3>{_criteria(primary)}</article>"
    ]
    for index, action in enumerate(secondary, start=1):
        cards.append(
            '<article class="brief-v2__action"><p class="brief-v2__eyebrow">'
            f"Дополнительное действие {index}</p><h3>{_e(action['title'])}</h3>"
            f"{_criteria(action)}</article>"
        )
    return '<div class="brief-v2__actions">' + "".join(cards) + "</div>"


def _render_signal(signal: Mapping[str, object]) -> str:
    evidence = _mapping(signal["evidence_summary"])
    action_role = str(signal.get("action_role") or "not_selected")
    action_reference = (
        "Основное действие недели"
        if action_role == "primary"
        else "Дополнительное действие"
        if action_role == "secondary"
        else "Отдельное действие не выбрано"
    )
    reaction = _mapping(signal["reaction_effect"])
    project_note = (
        "Связь с подтверждённым проектным действием показана ниже."
        if signal.get("project_implications")
        else "Подтверждённого влияния на проекты нет."
    )
    limitations = [
        item for item in evidence.get("limitations") or [] if _CYRILLIC_RE.search(str(item))
    ]
    evidence_items = "".join(
        f"<li>{_e(item['reader_label_ru'])}</li>"
        for item in _mapping_list(evidence.get("items"))
    )
    limitation_items = "".join(f"<li>{_e(item)}</li>" for item in limitations)
    return f"""<article class="brief-v2__signal">
<p class="brief-v2__eyebrow">{_e(_DECISION_LABELS[_matrix_bucket(signal['decision'])])}</p>
<h3>{_e(signal['title'])}</h3>
<p><strong>Что произошло:</strong> {_e(signal['what_happened'])}</p>
<p><strong>Простыми словами:</strong> {_e(signal['plain_explanation'])}</p>
<p><strong>Что изменилось:</strong> {_e(signal['what_changed'])}</p>
<p><strong>Почему это важно вам:</strong> {_e(signal['why_for_operator'])}</p>
<div class="brief-v2__facts"><span>Уверенность: {_e(_CONFIDENCE_LABELS[str(signal['confidence'])])}</span><span>Зрелость: {_e(_MATURITY_LABELS[str(evidence['evidence_maturity'])])}</span><span>Независимых источников: {_e(evidence['independent_source_count'])}</span></div>
<p class="brief-v2__meta">{_e(evidence['confidence_reason_ru'])}</p>
<p><strong>Почему сигнал здесь:</strong> {_e(reaction.get('reader_reason_ru') or 'Личные реакции не изменили выбор сигнала.')}</p>
<p><strong>Связь с проектами:</strong> {_e(project_note)}</p>
<p><strong>Следующий шаг:</strong> {_e(action_reference)}.</p>
<p><strong>Чего не делать:</strong> {_e(signal['do_not_do'])}</p>
<details><summary>Источники и ограничения</summary><ul>{evidence_items}</ul>{('<h4>Ограничения</h4><ul>' + limitation_items + '</ul>') if limitation_items else '<p>Дополнительные ограничения перечислены в техническом аудите.</p>'}</details>
</article>"""


def _render_feedback_effect(effect: Mapping[str, object]) -> str:
    count = int(effect.get("confirmed_events_considered") or 0)
    if count == 0:
        return (
            '<aside class="brief-v2__feedback"><h3>Что изменила подтверждённая обратная связь</h3>'
            "<p>Подтверждённых событий для этого периода нет. Это неизвестное состояние и не штраф.</p></aside>"
        )
    groups = []
    for key, title in (
        ("applied_changes", "Учтено в выпуске"),
        ("unchanged", "Оставлено без изменения"),
        ("code_config_required", "Требует отдельной задачи"),
        ("rejected", "Не применено"),
        ("pending", "Ожидает применения"),
    ):
        rows = _mapping_list(effect.get(key))
        if rows:
            groups.append(
                f"<h4>{_e(title)}</h4><ul>"
                + "".join(f"<li>{_e(item['reader_summary_ru'])}</li>" for item in rows)
                + "</ul>"
            )
    return (
        '<aside class="brief-v2__feedback"><h3>Что изменила подтверждённая обратная связь</h3>'
        f"<p>Рассмотрено подтверждённых событий: {count}.</p>{''.join(groups)}</aside>"
    )


def _render_reaction_snapshot_status(receipt: Mapping[str, object]) -> str:
    label = {
        "complete": "завершён",
        "partial": "частичный",
        "unavailable": "недоступен",
        "failed": "недоступен",
    }.get(str(receipt.get("snapshot_status") or "unavailable"), "недоступен")
    return f'<p class="brief-v2__meta"><strong>Снимок реакций:</strong> {_e(label)}.</p>'


def _render_radar_context(radar: Mapping[str, object]) -> str:
    state = str(radar.get("reader_state") or "invalid")
    if state != "available":
        return ""
    proof = _mapping_list(radar.get("matched_external_proof"))
    context = _mapping_list(radar.get("unmatched_context"))
    proof_rows = "".join(
        f"<li>{_e(_radar_record_label(item, context_only=False))}</li>"
        for item in proof
    )
    context_rows = "".join(
        f"<li>{_e(_radar_record_label(item, context_only=True))}</li>"
        for item in context
    )
    return (
        '<details class="brief-v2__radar-sources">'
        '<summary>Источники решения и отделённый контекст</summary>'
        + (
            f"<h3>Связанные доказательства</h3><ul>{proof_rows}</ul>"
            if proof_rows
            else "<p>Связанных внешних доказательств достаточной зрелости нет.</p>"
        )
        + (
            f"<h3>Контекст, который не заполняет гейты</h3><ul>{context_rows}</ul>"
            if context_rows
            else "<p>Отдельного несвязанного контекста нет.</p>"
        )
        + "</details>"
    )


def _radar_record_label(
    item: Mapping[str, object],
    *,
    context_only: bool,
) -> str:
    title = str(
        item.get("source_title")
        or item.get("title")
        or item.get("source_name")
        or item.get("source_url")
        or "источник без названия"
    ).strip()
    reason = str(item.get("reason") or item.get("source_snippet") or "").strip()
    title_copy = (
        title
        if _CYRILLIC_RE.search(title)
        else "Англоязычное название источника сохранено в техническом аудите"
    )
    role = (
        "Контекст не является доказательством кандидата."
        if context_only
        else "Источник связан с кандидатом и прошёл Radar-проверку."
    )
    if reason:
        reason_copy = (
            reason[:360]
            if _CYRILLIC_RE.search(reason)
            else "Исходное англоязычное пояснение сохранено в техническом аудите."
        )
        return f"{title_copy}. {role} {reason_copy}"
    return f"{title_copy}. {role}"


def _localize_radar_terms(value: str) -> str:
    return (
        value.replace(
            "Добавить совпавший свежий KIR Knowledge Thread для кандидата.",
            "Добавить свежую тему знаний, совпадающую с кандидатом.",
        )
        .replace(
            "Обновить совпавший KIR Knowledge Thread свежими данными.",
            "Обновить совпадающую тему знаний свежими данными.",
        )
        .replace(
            "Обновить совпавшую KIR-провенанс и повторить тот же bounded Radar run.",
            "Обновить происхождение совпадающей темы знаний и повторить тот же ограниченный запуск Radar.",
        )
        .replace("KIR Knowledge Thread", "тему знаний с проверяемым происхождением")
        .replace("KIR-провенанс", "происхождение темы знаний")
        .replace("KIR-тему", "тему знаний")
        .replace("KIR", "внутренней темы знаний")
        .replace("Knowledge Thread", "тему знаний")
        .replace("bounded Radar run", "ограниченный запуск Radar")
        .replace("manifest-bound", "связанное с манифестом")
    )


def _brief_styles() -> str:
    return """
:root{color-scheme:light;--ink:#17212b;--muted:#526273;--line:#cbd5e1;--paper:#fff;--wash:#f5f7fb;--accent:#1d4ed8;--warn:#9a3412;--ok:#166534}
*{box-sizing:border-box}body{margin:0;background:var(--wash);color:var(--ink);font:16px/1.58 system-ui,-apple-system,"Segoe UI",sans-serif}.brief-v2__header{max-width:1100px;margin:0 auto;padding:28px 24px 18px}.brief-v2__kicker,.brief-v2__eyebrow{margin:0 0 7px;color:var(--accent);font-size:.78rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase}.brief-v2__header h1{max-width:900px;margin:0 0 16px;font-size:clamp(2rem,5vw,3.4rem);line-height:1.08}.brief-v2__header-grid{display:flex;flex-wrap:wrap;gap:8px 22px}.brief-v2__header-grid p{margin:0}.brief-v2__status{display:inline-block;border:1px solid currentColor;border-radius:999px;padding:1px 9px;font-weight:700}.brief-v2__header nav{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}.brief-v2__header nav a{border:1px solid var(--line);border-radius:999px;background:var(--paper);padding:6px 11px;color:var(--accent)}.brief-v2__technical{margin-top:12px;color:var(--muted)}.brief-v2__technical summary{cursor:pointer;font-weight:700}.brief-v2__technical ul{margin:8px 0}.brief-v2{max-width:1100px}.brief-v2__section{margin:0 0 16px;padding:22px;border:1px solid var(--line);border-radius:14px;background:var(--paper)}.brief-v2__section>.irx-visual{margin-left:-2px;margin-right:-2px}.brief-v2__partial{margin:0 0 16px;padding:16px 18px;border:2px solid var(--warn);border-radius:12px;background:#fff7ed}.brief-v2__partial ul{margin:8px 0 0}.brief-v2__thesis{border-left:8px solid var(--accent)}.brief-v2__meta{color:var(--muted);font-size:.94rem}.brief-v2__actions{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:12px;margin-top:12px}.brief-v2__action,.brief-v2__signal,.brief-v2__feedback,.brief-v2__radar-state,.brief-v2__action-state{padding:16px;border:1px solid var(--line);border-radius:10px;background:#f8fafc}.brief-v2__action--primary{border:2px solid var(--ok);background:#f0fdf4}.brief-v2__signal+.brief-v2__signal{margin-top:14px}.brief-v2__signal h3{font-size:1.35rem}.brief-v2__facts{display:flex;flex-wrap:wrap;gap:7px;margin:12px 0}.brief-v2__facts span{border:1px solid var(--line);border-radius:999px;padding:3px 9px;background:#fff}.brief-v2__feedback,.brief-v2__radar-state{margin-bottom:14px}.brief-v2__prompts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr));gap:10px;padding:0;list-style:none}.brief-v2__prompt{min-height:84px;padding:14px;border:1px solid var(--line);border-radius:10px;background:#f8fafc;font-weight:700}.brief-v2__empty{padding:16px;border-left:5px solid var(--muted);background:#f8fafc}.brief-v2 details:not(.brief-v2__technical){margin-top:12px}.brief-v2 details summary{cursor:pointer;font-weight:700}.brief-v2 a{color:var(--accent)}
@media(max-width:600px){.brief-v2__header{padding:18px 12px 12px}.brief-v2__header h1{font-size:2rem}.brief-v2__header-grid{display:block}.brief-v2__header-grid p+ p{margin-top:6px}.brief-v2{padding:0 10px}.brief-v2__section{padding:15px}.brief-v2__actions,.brief-v2__prompts{grid-template-columns:1fr}.brief-v2__facts{display:grid;grid-template-columns:1fr}.brief-v2__prompt{min-height:0}}
@media print{body{background:#fff}.brief-v2__header,.brief-v2{max-width:none}.brief-v2__section,.brief-v2__signal,.brief-v2__action{break-inside:avoid}}
""".strip()


def _validate_manifest_identity(
    manifest: Mapping[str, object], *, manifest_path: str | Path
) -> None:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise WeeklyIntelligenceBriefV2ArtifactError("manifest schema mismatch")
    if manifest.get("run_status") not in {"complete", "partial"}:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 preview requires a terminal reader manifest"
        )
    if manifest.get("period_mode") not in {"completed_iso_week", "explicit_iso_week"}:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 preview requires a fully completed ISO week"
        )
    path = Path(manifest_path)
    if not path.is_absolute():
        raise WeeklyIntelligenceBriefV2ArtifactError("manifest path must be absolute")
    run_id = str(manifest.get("run_id") or "")
    if path.name != "manifest.json" or path.parent.name != run_id:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "manifest path does not match its run identity"
        )


def _require_input_identity(
    package: Mapping[str, object], manifest: Mapping[str, object]
) -> None:
    if package.get("schema_version") != EDITORIAL_INPUT_SCHEMA_VERSION:
        raise WeeklyIntelligenceBriefV2ValidationError(
            ["editorial input schema mismatch"]
        )
    if package.get("run_id") != manifest.get("run_id"):
        raise WeeklyIntelligenceBriefV2ValidationError(
            ["editorial input run_id mismatch"]
        )
    _require_period_identity(package, manifest, "editorial_input_package")
    run_context = _mapping(package.get("run_context"))
    for field in ("generated_at", "period_mode", "pipeline_profile"):
        if run_context.get(field) != manifest.get(field):
            raise WeeklyIntelligenceBriefV2ValidationError(
                [f"editorial input {field} mismatch"]
            )


def _require_editorial_signal_order(
    editorial: Mapping[str, object],
    package: Mapping[str, object],
) -> None:
    """Enforce the host-owned candidate order that IRX-5 only declares."""

    candidate_order = [
        str(item.get("signal_id") or "")
        for item in _mapping_list(package.get("signal_candidates"))
    ]
    returned_order = [
        str(item.get("signal_id") or "")
        for item in _mapping_list(editorial.get("signals"))
    ]
    positions = {signal_id: index for index, signal_id in enumerate(candidate_order)}
    if any(signal_id not in positions for signal_id in returned_order) or [
        positions[signal_id] for signal_id in returned_order if signal_id in positions
    ] != sorted(positions[signal_id] for signal_id in returned_order if signal_id in positions):
        raise WeeklyIntelligenceBriefV2ValidationError(
            ["editorial signals do not preserve the validated input order"]
        )


def _require_package_source_parity(
    package: Mapping[str, object],
    *,
    reaction: Mapping[str, object],
    radar: Mapping[str, object],
    manifest: Mapping[str, object],
) -> None:
    errors: list[str] = []
    for index, candidate in enumerate(
        _mapping_list(package.get("signal_candidates"))
    ):
        expected_reaction = _reaction_effect_for_candidate(
            reaction,
            candidate.get("source_thread_refs"),
        )
        if candidate.get("reaction_effect") != expected_reaction:
            errors.append(
                f"signal_candidates[{index}].reaction_effect differs from the bound receipt"
            )

    feedback_stage = _mapping(
        _mapping(manifest.get("stages")).get("feedback_snapshot")
    )
    record_counts = _mapping(feedback_stage.get("record_counts"))
    confirmed_count = record_counts.get("confirmed_events")
    package_feedback = _mapping(package.get("feedback_permissions"))
    if isinstance(confirmed_count, int) and not isinstance(confirmed_count, bool):
        if package_feedback.get("confirmed_events_considered") != confirmed_count:
            errors.append(
                "editorial feedback permissions differ from the manifest snapshot"
            )

    radar_permission = _mapping(package.get("radar_permission"))
    radar_state = str(radar.get("reader_state") or "invalid")
    if radar_state in {"available", "no_candidate"}:
        expected_ref = f"radar:{radar.get('radar_run_id')}"
        if radar_permission.get("radar_ref") != expected_ref:
            errors.append("editorial Radar permission ref mismatch")
        if radar_permission.get("radar_artifact_sha256") != _mapping(
            radar.get("artifact_ref")
        ).get("radar_json_sha256"):
            errors.append("editorial Radar artifact checksum mismatch")
        selected = radar_permission.get("selected_candidate")
        if radar_state == "available":
            expected_selected = {
                "title": radar.get("selected_candidate"),
                "dossier_status": radar.get("dossier_status"),
                "recommendation": radar.get("recommendation"),
            }
            selected_map = _mapping(selected)
            if any(
                selected_map.get(field) != expected
                for field, expected in expected_selected.items()
            ):
                errors.append("editorial Radar candidate mismatch")
            expected_decision = (
                "reject" if radar.get("reader_decision") == "reject" else "investigate"
            )
        else:
            if selected is not None:
                errors.append("no-candidate Radar permission contains a candidate")
            expected_decision = "unavailable"
        if radar_permission.get("allowed_reader_decisions") != [expected_decision]:
            errors.append("editorial Radar decision permission mismatch")
        if radar_permission.get("build_allowed") is not False:
            errors.append("editorial Radar permission weakens the build gate")
    elif (
        radar_permission.get("radar_ref")
        or radar_permission.get("selected_candidate") is not None
        or radar_permission.get("allowed_reader_decisions") != ["unavailable"]
    ):
        errors.append("unavailable Radar has an editorial authority claim")
    if radar_permission.get("context_only_can_satisfy_gate") is not False:
        errors.append("editorial Radar permission promotes context-only evidence")
    if errors:
        raise WeeklyIntelligenceBriefV2ValidationError(errors)


def _reaction_effect_for_candidate(
    receipt: Mapping[str, object],
    source_thread_refs: object,
) -> dict[str, object]:
    refs = [
        "thread:" + str(value).split(":", maxsplit=1)[1]
        for value in source_thread_refs or []
        if isinstance(value, str) and value.startswith("idea_thread:")
    ] if isinstance(source_thread_refs, list) else []
    priority = {"none": 0, "linked_only": 1, "rank_changed": 2, "selection_changed": 3}
    selected: Mapping[str, object] | None = None
    items_by_ref: dict[str, Mapping[str, object]] = {}
    for field in ("influenced_items", "linked_only_items"):
        for item in _mapping_list(receipt.get(field)):
            surface_ref = str(item.get("surface_item_ref") or "")
            if surface_ref in refs and surface_ref not in items_by_ref:
                items_by_ref[surface_ref] = item
    for surface_ref in refs:
        item = items_by_ref.get(surface_ref)
        if item is not None:
            effect = str(item.get("effect") or "linked_only")
            if selected is None or priority.get(effect, 0) > priority.get(
                str(selected.get("effect") or "none"),
                0,
            ):
                selected = item
    surface_ref = str(selected.get("surface_item_ref")) if selected else (refs[0] if refs else "")
    if selected is not None:
        return {
            "effect": str(selected.get("effect") or "linked_only"),
            "source_surface_item_ref": surface_ref,
            "reader_reason_ru": str(
                selected.get("reader_reason_ru")
                or "Реакция связана с сигналом, но не заменяет доказательства."
            )[:360],
        }
    return {
        "effect": "none",
        "source_surface_item_ref": surface_ref,
        "reader_reason_ru": (
            "Подтвержденного влияния реакций на этот сигнал нет; "
            "отсутствие реакции не означает отрицательный интерес."
        ),
    }


def _require_reaction_identity(
    reaction: Mapping[str, object], manifest: Mapping[str, object]
) -> None:
    expected = {
        "run_id": manifest.get("run_id"),
        "surface": "weekly_brief",
        **_period_from_manifest(manifest),
    }
    if any(reaction.get(field) != value for field, value in expected.items()):
        raise WeeklyIntelligenceBriefV2ValidationError(
            ["reaction receipt identity mismatch"]
        )


def _require_radar_identity(
    radar: Mapping[str, object], manifest: Mapping[str, object]
) -> None:
    if radar.get("reader_state") in {"available", "no_candidate"}:
        expected = {
            "manifest_run_id": manifest.get("run_id"),
            **_period_from_manifest(manifest),
        }
        if any(radar.get(field) != value for field, value in expected.items()):
            raise WeeklyIntelligenceBriefV2ValidationError(
                ["Radar reader identity mismatch"]
            )


def _require_period_identity(
    payload: Mapping[str, object],
    manifest: Mapping[str, object],
    label: str,
) -> None:
    period = _mapping(payload.get("reporting_period"))
    expected = _period_from_manifest(manifest)
    if period != expected:
        raise WeeklyIntelligenceBriefV2ValidationError(
            [f"{label} reporting period mismatch"]
        )


def _require_sidecar_manifest_identity(
    value: Mapping[str, object], manifest: Mapping[str, object]
) -> None:
    expected = {
        "run_id": manifest.get("run_id"),
        "generated_at": manifest.get("generated_at"),
        "period_mode": manifest.get("period_mode"),
        "reporting_period": _period_from_manifest(manifest),
        "source_run_status": manifest.get("run_status"),
    }
    if any(value.get(field) != expected_value for field, expected_value in expected.items()):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 sidecar/manifest identity mismatch"
        )


def _period_from_manifest(manifest: Mapping[str, object]) -> dict[str, str]:
    return {
        field: str(manifest.get(field) or "") for field in _PERIOD_FIELDS
    }


def _strict_check_manifest_json_sources(
    manifest: Mapping[str, object],
    manifest_path: Path,
) -> None:
    run_dir = manifest_path.parent.resolve()
    seen: dict[Path, str | None] = {}
    stages = _mapping(manifest.get("stages"))
    for stage_name, raw_stage in stages.items():
        stage = _mapping(raw_stage)
        if stage.get("status") != SUCCEEDED:
            continue
        checksums = _mapping(stage.get("checksums"))
        candidates: list[tuple[str, object, str | None]] = []
        for field, value in stage.items():
            if not str(field).endswith("_path") or not str(value or "").strip():
                continue
            checksum = str(checksums.get(field) or "") or None
            if stage_name == "radar":
                checksum = {
                    "artifact_path": str(stage.get("artifact_sha256") or ""),
                    "binding_path": str(stage.get("binding_sha256") or ""),
                    "seed_export_path": str(stage.get("seed_export_sha256") or ""),
                }.get(str(field), checksum) or None
            candidates.append((str(field), value, checksum))
        for container_name in ("dependency_refs", "artifact_refs"):
            for field, value in _mapping(stage.get(container_name)).items():
                if not str(value or "").strip():
                    continue
                checksum = str(checksums.get(field) or "") or None
                if (
                    stage_name == "radar"
                    and field == "binding_path"
                    and checksum is None
                ):
                    checksum = str(stage.get("binding_sha256") or "") or None
                candidates.append(
                    (f"{container_name}.{field}", value, checksum)
                )
        for field, value, checksum in candidates:
            source = _bound_path(run_dir, value)
            if source.suffix.casefold() != ".json":
                continue
            previous_checksum = seen.get(source)
            if source in seen:
                if (
                    previous_checksum is not None
                    and checksum is not None
                    and previous_checksum != checksum
                ):
                    raise WeeklyIntelligenceBriefV2ArtifactError(
                        "manifest JSON source has conflicting checksums"
                    )
                continue
            record = _read_strict_json_record(
                source,
                label=f"manifest source {stage_name}.{field}",
                maximum=MAX_SOURCE_JSON_BYTES,
            )
            if checksum is not None and record.sha256 != checksum:
                raise WeeklyIntelligenceBriefV2ArtifactError(
                    f"manifest source checksum mismatch: {stage_name}.{field}"
                )
            seen[source] = checksum


def _load_bound_v1_brief(
    manifest: Mapping[str, object], manifest_path: Path
) -> tuple[Path, dict[str, object], _StrictJsonRecord]:
    stage = _mapping(_mapping(manifest.get("stages")).get("weekly_brief"))
    if stage.get("status") != SUCCEEDED:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "manifest-bound V1 Brief did not succeed"
        )
    run_dir = manifest_path.parent.resolve()
    json_path = _bound_path(run_dir, stage.get("json_path"))
    record = _read_strict_json_record(
        json_path,
        label="manifest-bound V1 Brief",
        maximum=MAX_SOURCE_JSON_BYTES,
    )
    payload = _validate_bound_v1_brief_record(
        manifest,
        manifest_path,
        json_path,
        record,
    )
    return json_path, payload, record


def _validate_bound_v1_brief_record(
    manifest: Mapping[str, object],
    manifest_path: Path,
    json_path: Path,
    record: _StrictJsonRecord,
) -> dict[str, object]:
    stage = _mapping(_mapping(manifest.get("stages")).get("weekly_brief"))
    if stage.get("status") != SUCCEEDED:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "manifest-bound V1 Brief did not succeed"
        )
    expected_path = _bound_path(
        manifest_path.parent.resolve(),
        stage.get("json_path"),
    )
    if json_path != expected_path:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "manifest-bound V1 Brief path mismatch"
        )
    checksums = _mapping(stage.get("checksums"))
    expected_checksum = str(checksums.get("json_path") or "")
    if record.sha256 != expected_checksum:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "manifest-bound V1 Brief checksum mismatch"
        )
    if not isinstance(record.value, dict):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "manifest-bound V1 Brief root must be an object"
        )
    payload = record.value
    expected = {
        "artifact_type": "weekly_intelligence_brief",
        "run_id": manifest.get("run_id"),
        "generated_at": manifest.get("generated_at"),
        "reporting_week": manifest.get("reporting_week"),
        "analysis_period_start": manifest.get("analysis_period_start"),
        "analysis_period_end": manifest.get("analysis_period_end"),
        "period_mode": manifest.get("period_mode"),
    }
    if any(payload.get(field) != value for field, value in expected.items()):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "manifest-bound V1 Brief identity mismatch"
        )
    return payload


def _bound_stage_html_path(
    manifest: Mapping[str, object],
    manifest_path: Path,
    *,
    stage_name: str,
) -> Path | None:
    stage = _mapping(_mapping(manifest.get("stages")).get(stage_name))
    if stage.get("status") != SUCCEEDED:
        return None
    path = _bound_path(manifest_path.parent.resolve(), stage.get("html_path"))
    checksums = _mapping(stage.get("checksums"))
    try:
        verify_file_checksum(path, str(checksums.get("html_path") or ""))
    except WeeklyRunManifestError as exc:
        raise WeeklyIntelligenceBriefV2ArtifactError(str(exc)) from exc
    return path


def _verify_editorial_projection(
    sidecar: Mapping[str, object], editorial: Mapping[str, object]
) -> None:
    if editorial.get("schema_version") != EDITORIAL_SCHEMA_VERSION:
        raise WeeklyIntelligenceBriefV2ArtifactError("editorial source schema mismatch")
    if editorial.get("run_id") != sidecar.get("run_id"):
        raise WeeklyIntelligenceBriefV2ArtifactError("editorial source run mismatch")
    if editorial.get("weekly_thesis") != sidecar.get("weekly_thesis"):
        raise WeeklyIntelligenceBriefV2ArtifactError("editorial thesis projection mismatch")
    if editorial.get("feedback_effect") != sidecar.get("feedback_effect"):
        raise WeeklyIntelligenceBriefV2ArtifactError("editorial feedback projection mismatch")
    source_signals = _mapping_list(editorial.get("signals"))
    reader_signals = _mapping_list(sidecar.get("signals"))
    if len(source_signals) != len(reader_signals):
        raise WeeklyIntelligenceBriefV2ArtifactError("editorial signal count mismatch")
    added = {"evidence_summary", "action_role"}
    for source_signal, reader_signal in zip(source_signals, reader_signals):
        projected = {key: value for key, value in reader_signal.items() if key not in added}
        if projected != source_signal:
            raise WeeklyIntelligenceBriefV2ArtifactError("editorial signal projection mismatch")
    if [str(value) for value in editorial.get("project_actions") or []] != [
        str(item.get("project_action_ref"))
        for item in _mapping_list(sidecar.get("project_actions"))
    ]:
        raise WeeklyIntelligenceBriefV2ArtifactError("editorial project projection mismatch")


def _verify_project_projection(
    sidecar: Mapping[str, object], project: Mapping[str, object]
) -> None:
    confirmed = {
        str(item.get("project_action_ref")): item
        for item in _mapping_list(project.get("confirmed_actions"))
    }
    for action in _mapping_list(sidecar.get("project_actions")):
        if confirmed.get(str(action.get("project_action_ref"))) != action:
            raise WeeklyIntelligenceBriefV2ArtifactError(
                "Brief V2 project action differs from Project Intelligence"
            )


def _validate_evidence_summary(
    value: object, signal_path: str, errors: list[str]
) -> None:
    summary = _object(value, f"{signal_path}.evidence_summary", errors)
    _exact_fields(
        summary,
        {"evidence_maturity", "independent_source_count", "confidence_reason_ru", "items", "limitations"},
        f"{signal_path}.evidence_summary",
        errors,
    )
    if summary.get("evidence_maturity") not in _MATURITY:
        errors.append(f"{signal_path}.evidence_summary.evidence_maturity is invalid")
    count = summary.get("independent_source_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        errors.append(f"{signal_path}.evidence_summary.independent_source_count is invalid")
    _russian_text(
        summary.get("confidence_reason_ru"),
        f"{signal_path}.evidence_summary.confidence_reason_ru",
        errors,
        500,
    )
    items = _object_list(summary.get("items"), f"{signal_path}.evidence_summary.items", errors, 8)
    for index, item in enumerate(items):
        if "reader_label_ru" not in item:
            errors.append(f"{signal_path}.evidence_summary.items[{index}] lacks reader label")
        else:
            _russian_text(
                item.get("reader_label_ru"),
                f"{signal_path}.evidence_summary.items[{index}].reader_label_ru",
                errors,
                600,
            )
    _string_list(
        summary.get("limitations"),
        f"{signal_path}.evidence_summary.limitations",
        errors,
        maximum=4,
    )


def _validate_action(value: object, path: str, errors: list[str], *, role: str) -> None:
    action = _object(value, path, errors)
    _exact_fields(action, {"role", "signal_ref", "title", "acceptance_criteria"}, path, errors)
    if action.get("role") != role:
        errors.append(f"{path}.role mismatch")
    _ref(action.get("signal_ref"), f"{path}.signal_ref", errors)
    _russian_text(action.get("title"), f"{path}.title", errors, 400)
    criteria = _string_list(
        action.get("acceptance_criteria"),
        f"{path}.acceptance_criteria",
        errors,
        maximum=5,
        russian=True,
    )
    if not criteria:
        errors.append(f"{path}.acceptance_criteria is empty")


def _validate_project_action(value: Mapping[str, object], path: str, errors: list[str]) -> None:
    required = {
        "project_action_ref",
        "project_name",
        "project_repo",
        "permission_id",
        "signal_id",
        "canonical_thread_ref",
        "why_this_project",
        "affected_component",
        "suggested_change",
        "likely_files",
        "effort",
        "acceptance_criteria",
        "risk",
        "priority",
        "confidence",
        "evidence_refs",
        "status",
    }
    _exact_fields(value, required, path, errors)
    if value.get("status") != "confirmed":
        errors.append(f"{path}.status must be confirmed")
    if value.get("confidence") not in {"medium", "high"}:
        errors.append(f"{path}.confidence is invalid")
    _refs(value.get("evidence_refs"), f"{path}.evidence_refs", errors, 12)
    for field in ("why_this_project", "suggested_change", "risk"):
        _russian_text(value.get(field), f"{path}.{field}", errors, 1_200)


def _validate_feedback_effect(value: object, errors: list[str]) -> None:
    effect = _object(value, "feedback_effect", errors)
    fields = {
        "confirmed_events_considered",
        "applied_changes",
        "unchanged",
        "code_config_required",
        "rejected",
        "pending",
    }
    _exact_fields(effect, fields, "feedback_effect", errors)
    count = effect.get("confirmed_events_considered")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        errors.append("feedback_effect.confirmed_events_considered is invalid")
    for field in fields - {"confirmed_events_considered"}:
        rows = _object_list(effect.get(field), f"feedback_effect.{field}", errors, 20)
        for index, item in enumerate(rows):
            _exact_fields(item, {"feedback_ref", "reader_summary_ru"}, f"feedback_effect.{field}[{index}]", errors)
            _russian_text(item.get("reader_summary_ru"), f"feedback_effect.{field}[{index}].reader_summary_ru", errors, 600)


def _validate_feedback_target(value: Mapping[str, object], path: str, errors: list[str]) -> None:
    _exact_fields(value, {"id", "target_type", "target_ref", "prompt_ru"}, path, errors)
    for field in ("id", "target_type", "target_ref"):
        _ref(value.get(field), f"{path}.{field}", errors)
    _russian_text(value.get("prompt_ru"), f"{path}.prompt_ru", errors, 200)


def _validate_navigation(value: object, run_id: str, errors: list[str]) -> None:
    navigation = _object(value, "navigation", errors)
    fields = {"atlas_v2", "audit_explorer", "compatibility_atlas"}
    _exact_fields(navigation, fields, "navigation", errors)
    for field in fields:
        item = _object(navigation.get(field), f"navigation.{field}", errors)
        _exact_fields(item, {"status", "path", "label_ru"}, f"navigation.{field}", errors)
        if item.get("status") not in {"available", "unavailable"}:
            errors.append(f"navigation.{field}.status is invalid")
        _russian_text(item.get("label_ru"), f"navigation.{field}.label_ru", errors, 160)
        path = item.get("path")
        if (item.get("status") == "available") != isinstance(path, str):
            errors.append(f"navigation.{field} path/status mismatch")
        if isinstance(path, str):
            _safe_path_text(path, f"navigation.{field}.path", errors)
    atlas = _object(navigation.get("atlas_v2"), "navigation.atlas_v2", errors)
    audit = _object(
        navigation.get("audit_explorer"),
        "navigation.audit_explorer",
        errors,
    )
    if (atlas.get("status") == "available") != (
        audit.get("status") == "available"
    ):
        errors.append("Atlas V2 and Audit Explorer navigation availability differs")
    if atlas.get("status") == "available" and audit.get("status") == "available":
        atlas_path = Path(str(atlas.get("path") or ""))
        audit_path = Path(str(audit.get("path") or ""))
        if (
            atlas_path.name != "knowledge-atlas.v2.html"
            or audit_path.name != "knowledge-audit-explorer.v1.html"
            or atlas_path.parent != audit_path.parent
            or atlas_path.parent.name != run_id
        ):
            errors.append("Atlas V2 navigation does not identify one exact-run package")


def _validate_technical_refs(value: object, errors: list[str]) -> None:
    refs = _object(value, "technical_refs", errors)
    fields = {
        "manifest_path",
        "audit_explorer_path",
        "compatibility_atlas_path",
        "editorial_artifact_path",
        "editorial_input_catalog_path",
        "project_intelligence_path",
        "v1_brief_path",
    }
    _exact_fields(refs, fields, "technical_refs", errors)
    for field in fields:
        path = refs.get(field)
        if path is None and field in {"audit_explorer_path", "compatibility_atlas_path"}:
            continue
        _safe_path_text(path, f"technical_refs.{field}", errors)


def _validate_source_artifacts(value: object, errors: list[str]) -> None:
    sources = _object(value, "source_artifacts", errors)
    fields = {
        "manifest",
        "editorial",
        "editorial_input",
        "project_intelligence",
        "reaction_source",
    }
    _exact_fields(sources, fields, "source_artifacts", errors)
    for field in fields:
        item = _object(sources.get(field), f"source_artifacts.{field}", errors)
        _exact_fields(item, {"path", "sha256"}, f"source_artifacts.{field}", errors)
        _safe_path_text(item.get("path"), f"source_artifacts.{field}.path", errors)
        if not isinstance(item.get("sha256"), str) or not _SHA_RE.fullmatch(str(item.get("sha256"))):
            errors.append(f"source_artifacts.{field}.sha256 is invalid")


def _validate_artifact_paths(value: object, errors: list[str]) -> None:
    paths = _object(value, "artifact_paths", errors)
    _exact_fields(
        paths,
        {"html", "json", "source_catalog"},
        "artifact_paths",
        errors,
    )
    for field in ("html", "json", "source_catalog"):
        _safe_path_text(paths.get(field), f"artifact_paths.{field}", errors)


def _validate_content_metrics(
    value: object,
    specs: Sequence[Mapping[str, object]],
    errors: list[str],
) -> None:
    metrics = _object(value, "content_metrics", errors)
    fields = {
        "visible_word_count",
        "target_min",
        "target_max",
        "hard_max",
        "word_budget_status",
        "visual_component_count",
        "meaningful_visual_count",
    }
    _exact_fields(metrics, fields, "content_metrics", errors)
    for field in (
        "visible_word_count",
        "target_min",
        "target_max",
        "hard_max",
        "visual_component_count",
        "meaningful_visual_count",
    ):
        item = metrics.get(field)
        if not isinstance(item, int) or isinstance(item, bool) or item < 0:
            errors.append(f"content_metrics.{field} is invalid")
    if metrics.get("target_min") != TARGET_VISIBLE_WORDS_MIN or metrics.get("target_max") != TARGET_VISIBLE_WORDS_MAX or metrics.get("hard_max") != HARD_VISIBLE_WORDS_MAX:
        errors.append("content_metrics word limits mismatch")
    if metrics.get("word_budget_status") not in {"pending", "short", "within_target", "warning", "critical"}:
        errors.append("content_metrics.word_budget_status is invalid")
    if metrics.get("visual_component_count") != len(specs):
        errors.append("content_metrics.visual_component_count mismatch")
    if metrics.get("meaningful_visual_count") != _meaningful_visual_count(specs):
        errors.append("content_metrics.meaningful_visual_count mismatch")


def _navigation(
    *,
    run_id: str,
    atlas_v2_path: str | Path | None,
    audit_explorer_path: str | Path | None,
    compatibility_atlas_path: str | Path | None,
) -> dict[str, dict[str, object]]:
    if (atlas_v2_path is None) != (audit_explorer_path is None):
        raise WeeklyIntelligenceBriefV2ValidationError(
            ["Atlas V2 and Audit Explorer navigation must be bound together"]
        )
    if atlas_v2_path is not None and Path(atlas_v2_path).parent != Path(
        str(audit_explorer_path)
    ).parent:
        raise WeeklyIntelligenceBriefV2ValidationError(
            ["Atlas V2 and Audit Explorer navigation must share one package"]
        )
    return {
        "atlas_v2": _navigation_item(
            atlas_v2_path,
            available_label="Открыть Knowledge Atlas V2",
            unavailable_label="Knowledge Atlas V2 пока недоступен",
            expected_name="knowledge-atlas.v2.html",
            expected_parent=run_id,
            fail_if_supplied=True,
        ),
        "audit_explorer": _navigation_item(
            audit_explorer_path,
            available_label="Открыть Knowledge Audit Explorer",
            unavailable_label="Knowledge Audit Explorer пока недоступен",
            expected_name="knowledge-audit-explorer.v1.html",
            expected_parent=run_id,
            fail_if_supplied=True,
        ),
        "compatibility_atlas": _navigation_item(
            compatibility_atlas_path,
            available_label="Открыть совместимый Atlas V1",
            unavailable_label="Совместимый Atlas V1 недоступен",
        ),
    }


def _navigation_item(
    path: str | Path | None,
    *,
    available_label: str,
    unavailable_label: str,
    expected_name: str | None = None,
    expected_parent: str | None = None,
    fail_if_supplied: bool = False,
) -> dict[str, object]:
    resolved: str | None = None
    if path is not None and str(path).strip():
        try:
            lexical = Path(path).expanduser().absolute()
            candidate = lexical.resolve(strict=True)
            if (
                lexical == candidate
                and candidate.is_file()
                and (expected_name is None or candidate.name == expected_name)
                and (expected_parent is None or candidate.parent.name == expected_parent)
            ):
                resolved = str(candidate)
        except (OSError, RuntimeError, ValueError, TypeError):
            resolved = None
        if resolved is None and fail_if_supplied:
            raise WeeklyIntelligenceBriefV2ValidationError(
                [f"explicit navigation path is invalid: {expected_name or 'artifact'}"]
            )
    return {
        "status": "available" if resolved else "unavailable",
        "path": resolved,
        "label_ru": available_label if resolved else unavailable_label,
    }


def _validated_atlas_navigation_paths(
    atlas_json_path: str | Path | None,
    *,
    manifest_path: Path,
    allowed_source_roots: Sequence[Path],
) -> tuple[str | None, str | None]:
    if atlas_json_path is None:
        return None, None
    try:
        from output.knowledge_atlas_report_v2 import (
            KnowledgeAtlasV2Error,
            load_manifest_bound_knowledge_atlas_v2,
        )

        atlas = load_manifest_bound_knowledge_atlas_v2(
            atlas_json_path,
            expected_manifest_path=manifest_path,
            allowed_source_roots=allowed_source_roots,
        )
        return (
            str(_mapping(atlas["artifact_paths"])["html"]),
            str(_mapping(atlas["technical_refs"])["audit_explorer_path"]),
        )
    except (KnowledgeAtlasV2Error, OSError, RuntimeError, ValueError) as exc:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "explicit Atlas V2 navigation failed strict bound loading"
        ) from exc


def _validated_bound_navigation_paths(
    raw_navigation: object,
    *,
    manifest_path: Path,
    allowed_source_roots: Sequence[Path],
) -> tuple[str | None, str | None]:
    navigation = _mapping(raw_navigation)
    atlas_item = _mapping(navigation.get("atlas_v2"))
    audit_item = _mapping(navigation.get("audit_explorer"))
    atlas_available = atlas_item.get("status") == "available"
    audit_available = audit_item.get("status") == "available"
    if atlas_available != audit_available:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Atlas V2 and Audit Explorer navigation binding is incomplete"
        )
    if not atlas_available:
        return None, None
    atlas_html = Path(str(atlas_item.get("path") or ""))
    atlas_json = atlas_html.parent / "knowledge-atlas.v2.json"
    expected_atlas, expected_audit = _validated_atlas_navigation_paths(
        atlas_json,
        manifest_path=manifest_path,
        allowed_source_roots=allowed_source_roots,
    )
    if atlas_item.get("path") != expected_atlas or audit_item.get("path") != expected_audit:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 navigation differs from the strict Atlas V2 package"
        )
    return expected_atlas, expected_audit


def _render_navigation_item(item: Mapping[str, object]) -> str:
    if item.get("status") == "available":
        return f'<a href="{_path_href(item["path"])}">{_e(item["label_ru"])}</a>'
    return f'<span class="brief-v2__status">{_e(item["label_ru"])}</span>'


def _render_technical_links(refs: Mapping[str, object]) -> str:
    rows = [
        ("Manifest запуска", refs.get("manifest_path")),
        ("Каталог проверенных входов V2", refs.get("editorial_input_catalog_path")),
        ("Knowledge Audit Explorer", refs.get("audit_explorer_path")),
        ("Совместимый Atlas V1", refs.get("compatibility_atlas_path")),
    ]
    return "<ul>" + "".join(
        (
            f'<li><a href="{_path_href(path)}">{_e(label)}</a></li>'
            if path
            else f"<li>{_e(label)}: не сформирован.</li>"
        )
        for label, path in rows
    ) + "</ul>"


def _source_artifact_record(
    path: Path,
    record: _StrictJsonRecord,
) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": record.sha256}


def _source_artifact_bytes(path: Path, data: bytes) -> dict[str, str]:
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _build_source_catalog(
    *,
    manifest: Mapping[str, object],
    editorial_input_package: Mapping[str, object],
    project_descriptors: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    package = _json_copy(editorial_input_package, "editorial_input_package")
    try:
        descriptors = json.loads(
            json.dumps(
                list(project_descriptors),
                ensure_ascii=False,
                allow_nan=False,
            )
        )
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise WeeklyIntelligenceBriefV2ValidationError(
            ["project_descriptors must be strict JSON"]
        ) from exc
    if not isinstance(descriptors, list) or any(
        not isinstance(item, dict) for item in descriptors
    ):
        raise WeeklyIntelligenceBriefV2ValidationError(
            ["project_descriptors must be an object list"]
        )
    if len(descriptors) > 64:
        raise WeeklyIntelligenceBriefV2ValidationError(
            ["project_descriptors exceeds the source-catalog limit"]
        )
    return {
        "schema_version": BRIEF_V2_SOURCE_CATALOG_SCHEMA_VERSION,
        "run_id": str(manifest.get("run_id") or ""),
        "reporting_period": _period_from_manifest(manifest),
        "editorial_input_schema_version": EDITORIAL_INPUT_SCHEMA_VERSION,
        "editorial_input_package": package,
        "project_descriptor_schema_version": (
            PROJECT_ACTION_PERMISSIONS_SCHEMA_VERSION
        ),
        "project_descriptors": descriptors,
    }


def _validate_source_catalog_value(
    payload: Mapping[str, object],
    *,
    manifest: Mapping[str, object],
) -> dict[str, object]:
    value = _json_copy(payload, "Brief V2 source catalog")
    expected_fields = {
        "schema_version",
        "run_id",
        "reporting_period",
        "editorial_input_schema_version",
        "editorial_input_package",
        "project_descriptor_schema_version",
        "project_descriptors",
    }
    if set(value) != expected_fields:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 source catalog fields mismatch"
        )
    if (
        value.get("schema_version") != BRIEF_V2_SOURCE_CATALOG_SCHEMA_VERSION
        or value.get("editorial_input_schema_version")
        != EDITORIAL_INPUT_SCHEMA_VERSION
        or value.get("project_descriptor_schema_version")
        != PROJECT_ACTION_PERMISSIONS_SCHEMA_VERSION
        or value.get("run_id") != manifest.get("run_id")
        or value.get("reporting_period") != _period_from_manifest(manifest)
    ):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 source catalog identity mismatch"
        )
    package = value.get("editorial_input_package")
    descriptors = value.get("project_descriptors")
    if not isinstance(package, Mapping):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 source catalog input package is invalid"
        )
    if (
        not isinstance(descriptors, list)
        or len(descriptors) > 64
        or any(not isinstance(item, Mapping) for item in descriptors)
    ):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 source catalog project descriptors are invalid"
        )
    _require_input_identity(package, manifest)
    return value


def _normalize_source_artifacts(
    value: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for name in (
        "manifest",
        "editorial",
        "editorial_input",
        "project_intelligence",
        "reaction_source",
    ):
        item = _mapping(value.get(name))
        path = str(item.get("path") or "")
        sha = str(item.get("sha256") or "")
        if not path or not Path(path).is_absolute() or not _SHA_RE.fullmatch(sha):
            raise WeeklyIntelligenceBriefV2ValidationError(
                [f"source_artifacts.{name} is invalid"]
            )
        result[name] = {"path": str(Path(path).resolve()), "sha256": sha}
    return result


def _normalize_artifact_paths(value: Mapping[str, object]) -> dict[str, str]:
    result = {
        field: str(value.get(field) or "")
        for field in ("html", "json", "source_catalog")
    }
    if any(not path or not Path(path).is_absolute() for path in result.values()):
        raise WeeklyIntelligenceBriefV2ValidationError(
            ["artifact_paths must be absolute"]
        )
    return {field: str(Path(path).resolve()) for field, path in result.items()}


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _safe_v2_output_directory(output_root: str | Path, run_id: str) -> Path:
    if not _RUN_ID_RE.fullmatch(run_id):
        raise WeeklyIntelligenceBriefV2ArtifactError("Brief V2 run_id is invalid")
    try:
        requested_output = Path(output_root).expanduser().absolute()
        output_base = requested_output.resolve()
        if requested_output != output_base:
            raise WeeklyIntelligenceBriefV2ArtifactError(
                "Brief V2 requested output root must be canonical"
            )
        output_base.mkdir(parents=True, exist_ok=True)
        v2_root = output_base / BRIEF_V2_DIRECTORY
        if v2_root.is_symlink():
            raise WeeklyIntelligenceBriefV2ArtifactError(
                "Brief V2 output root must not be a symlink"
            )
        v2_root.mkdir(exist_ok=True)
        if not v2_root.is_dir() or v2_root.resolve() != v2_root:
            raise WeeklyIntelligenceBriefV2ArtifactError(
                "Brief V2 output root is not canonical"
            )
        target = v2_root / run_id
        if target.is_symlink():
            raise WeeklyIntelligenceBriefV2ArtifactError(
                "Brief V2 run directory must not be a symlink"
            )
        if target.exists() and (not target.is_dir() or target.resolve() != target):
            raise WeeklyIntelligenceBriefV2ArtifactError(
                "Brief V2 run directory is not canonical"
            )
        return target
    except WeeklyIntelligenceBriefV2Error:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 output directory is invalid"
        ) from exc


def _write_immutable_artifacts(
    artifacts: Sequence[tuple[Path, bytes]],
) -> bool:
    if not artifacts:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 immutable package is empty"
        )
    paths = [path for path, _data in artifacts]
    if len(paths) != len(set(paths)):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 immutable package contains duplicate paths"
        )
    parents = {path.parent for path in paths}
    if len(parents) != 1:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 immutable package must share one directory"
        )
    target_directory = paths[0].parent
    if target_directory.is_symlink() or target_directory.parent.is_symlink():
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 immutable path contains a symlink"
        )
    if any(path.is_symlink() for path in paths):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 immutable file must not be a symlink"
        )
    exists = tuple(path.exists() for path in paths)
    if any(exists):
        if not all(exists):
            raise WeeklyIntelligenceBriefV2ArtifactError(
                "immutable Brief V2 package is incomplete"
            )
        _require_private_directory(
            target_directory,
            label="immutable Brief V2 package directory",
        )
        if any(
            _read_bounded_bytes(
                path,
                label=f"immutable Brief V2 file {path.name}",
                maximum=len(data),
                require_private=True,
            )
            != data
            for path, data in artifacts
        ):
            raise WeeklyIntelligenceBriefV2ArtifactError(
                "immutable Brief V2 path differs; create a new run_id"
            )
        return True
    target_directory.parent.mkdir(parents=True, exist_ok=True)
    if target_directory.parent.resolve() != target_directory.parent:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 immutable parent is not canonical"
        )
    parent_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    staging_name = f".{target_directory.name}.{secrets.token_hex(12)}"
    parent_fd: int | None = None
    staging_fd: int | None = None
    staging_created = False
    published = False
    try:
        parent_fd = os.open(target_directory.parent, parent_flags)
        os.mkdir(staging_name, mode=0o700, dir_fd=parent_fd)
        staging_created = True
        staging_fd = os.open(staging_name, parent_flags, dir_fd=parent_fd)
        for path, data in artifacts:
            file_fd = os.open(
                path.name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=staging_fd,
            )
            with os.fdopen(file_fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        os.fsync(staging_fd)
        os.rename(
            staging_name,
            target_directory.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        published = True
        os.fsync(parent_fd)
        return False
    except OSError as exc:
        if (
            not target_directory.is_symlink()
            and all(path.is_file() for path in paths)
            and all(
                _read_bounded_bytes(
                    path,
                    label=f"immutable Brief V2 file {path.name}",
                    maximum=len(data),
                    require_private=True,
                )
                == data
                for path, data in artifacts
            )
        ):
            return True
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "immutable Brief V2 package could not be published"
        ) from exc
    finally:
        if not published and staging_fd is not None:
            for path in paths:
                try:
                    os.unlink(path.name, dir_fd=staging_fd)
                except FileNotFoundError:
                    pass
        if staging_fd is not None:
            os.close(staging_fd)
        if not published and staging_created and parent_fd is not None:
            try:
                os.rmdir(staging_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        if parent_fd is not None:
            os.close(parent_fd)


def _summary(
    sidecar: Mapping[str, object], *, cache_hit: bool
) -> WeeklyIntelligenceBriefV2Summary:
    actions = _mapping(sidecar["actions"])
    metrics = _mapping(sidecar["content_metrics"])
    paths = _mapping(sidecar["artifact_paths"])
    period = _mapping(sidecar["reporting_period"])
    return WeeklyIntelligenceBriefV2Summary(
        run_id=str(sidecar["run_id"]),
        reporting_week=str(period["reporting_week"]),
        run_status=str(sidecar["run_status"]),
        partial=bool(sidecar["partial"]),
        html_path=str(paths["html"]),
        json_path=str(paths["json"]),
        source_catalog_path=str(paths["source_catalog"]),
        signal_count=len(sidecar["signals"]),
        primary_action_count=1 if actions.get("primary") else 0,
        secondary_action_count=len(actions.get("secondary") or []),
        project_action_count=len(sidecar["project_actions"]),
        visual_component_count=int(metrics["visual_component_count"]),
        meaningful_visual_count=int(metrics["meaningful_visual_count"]),
        visible_word_count=int(metrics["visible_word_count"]),
        cache_hit=cache_hit,
    )


def summary_as_dict(summary: WeeklyIntelligenceBriefV2Summary) -> dict[str, object]:
    """Stable JSON-friendly summary helper for orchestration adapters."""

    return asdict(summary)


def _read_strict_json_value(path: Path, *, label: str, maximum: int) -> object:
    return _read_strict_json_record(
        path,
        label=label,
        maximum=maximum,
    ).value


def _read_strict_json_record(
    path: Path,
    *,
    label: str,
    maximum: int,
    require_private: bool = False,
) -> _StrictJsonRecord:
    data = _read_bounded_bytes(
        path,
        label=label,
        maximum=maximum,
        require_private=require_private,
    )
    try:
        text = data.decode("utf-8")
    except UnicodeError as exc:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            f"cannot decode {label}: {exc}"
        ) from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
            parse_float=_strict_json_float,
        )
    except (
        json.JSONDecodeError,
        RecursionError,
        OverflowError,
        ValueError,
        WeeklyIntelligenceBriefV2Error,
    ) as exc:
        raise WeeklyIntelligenceBriefV2ArtifactError(f"invalid {label}: {exc}") from exc
    return _StrictJsonRecord(
        value=value,
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
    )


def _read_bounded_bytes(
    path: Path,
    *,
    label: str,
    maximum: int,
    require_private: bool = False,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    file_descriptor: int | None = None
    try:
        file_descriptor = os.open(path, flags)
        metadata = os.fstat(file_descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise WeeklyIntelligenceBriefV2ArtifactError(
                f"{label} is not a regular file"
            )
        if require_private and metadata.st_mode & 0o077:
            raise WeeklyIntelligenceBriefV2ArtifactError(
                f"{label} is not private"
            )
        with os.fdopen(file_descriptor, "rb") as handle:
            file_descriptor = None
            data = handle.read(maximum + 1)
        if len(data) > maximum:
            raise WeeklyIntelligenceBriefV2ArtifactError(
                f"{label} exceeds byte limit"
            )
        return data
    except WeeklyIntelligenceBriefV2Error:
        raise
    except OSError as exc:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            f"cannot read {label}: {exc}"
        ) from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)


def _require_private_directory(path: Path, *, label: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            f"cannot inspect {label}: {exc}"
        ) from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_mode & 0o077
    ):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            f"{label} is not a private canonical directory"
        )


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise WeeklyIntelligenceBriefV2ArtifactError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise WeeklyIntelligenceBriefV2ArtifactError(f"non-finite JSON constant: {value}")


def _strict_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            f"non-finite JSON number: {value}"
        )
    return parsed


def _json_copy(value: Mapping[str, object], label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise WeeklyIntelligenceBriefV2ValidationError([f"{label} must be an object"])
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise WeeklyIntelligenceBriefV2ValidationError(
            [f"{label} must be strict JSON"]
        ) from exc


def _contained_source_path(
    value: str | Path | object, roots: Sequence[Path]
) -> Path:
    try:
        path = Path(str(value)).resolve(strict=True)
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "source artifact path is invalid"
        ) from exc
    _require_contained(path, roots)
    return path


def _require_contained(path: Path, roots: Sequence[Path]) -> None:
    if not any(path.is_relative_to(root.resolve()) for root in roots):
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "Brief V2 dependency escapes allowed roots"
        )


def _unique_paths(values: Sequence[Path]) -> tuple[Path, ...]:
    result: list[Path] = []
    for value in values:
        resolved = value.resolve()
        if resolved not in result:
            result.append(resolved)
    return tuple(result)


def _bound_path(base: Path, value: object) -> Path:
    raw = str(value or "")
    path = Path(raw)
    if not raw or path.is_absolute():
        raise WeeklyIntelligenceBriefV2ArtifactError("manifest artifact path is invalid")
    try:
        resolved = (base / path).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise WeeklyIntelligenceBriefV2ArtifactError(
            "manifest artifact path is invalid"
        ) from exc
    _require_contained(resolved, (base,))
    return resolved


def _path_href(value: object) -> str:
    return escape(str(value), quote=True)


def _human_period(period: Mapping[str, object]) -> str:
    start = datetime.fromisoformat(str(period["analysis_period_start"]).replace("Z", "+00:00"))
    end = datetime.fromisoformat(str(period["analysis_period_end"]).replace("Z", "+00:00"))
    inclusive = end.date().fromordinal(end.date().toordinal() - 1)
    return f"{start:%d.%m.%Y}–{inclusive:%d.%m.%Y}"


def _human_timestamp(value: object) -> str:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(
        _OPERATOR_TIME_ZONE
    )
    return parsed.strftime("%d.%m.%Y, %H:%M %Z")


def _criteria(action: Mapping[str, object]) -> str:
    return "<ul>" + "".join(
        f"<li>{_e(item)}</li>" for item in action.get("acceptance_criteria") or []
    ) + "</ul>"


def _decision_copy(bucket: str, title: str) -> str:
    prefixes = {
        "act": "Применить проверенный вывод по теме",
        "study": "Уточнить доказательства по теме",
        "watch": "Следить за изменениями по теме",
        "ignore": "Отложить решения по теме",
    }
    return f"{prefixes[bucket]} «{title}»"


def _matrix_bucket(value: object) -> str:
    decision = str(value)
    return "study" if decision == "verify_first" else decision


def _russian_or_placeholder(value: object, index: int, label: str) -> str:
    text = str(value or "").strip()
    if text and _CYRILLIC_RE.search(text):
        return _localize_radar_terms(text)[:500]
    if text:
        return f"Исходное англоязычное поле Radar «{label}» №{index} сохранено в техническом аудите."
    return f"Проверить {label} №{index}, сохранённый в связанном Radar-досье."


def _meaningful_visual_count(specs: Sequence[Mapping[str, object]]) -> int:
    return sum(
        render_report_visual(spec).render_status != "failed"
        and spec.get("data_status") in {"available", "empty"}
        for spec in specs
    )


def _word_budget_status(count: int) -> str:
    if count < TARGET_VISIBLE_WORDS_MIN:
        return "short"
    if count <= TARGET_VISIBLE_WORDS_MAX:
        return "within_target"
    if count <= HARD_VISIBLE_WORDS_MAX:
        return "warning"
    return "critical"


def _exact_fields(
    value: Mapping[str, object],
    expected: set[str],
    path: str,
    errors: list[str],
) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        errors.append(f"{path} missing fields: {', '.join(missing)}")
    if unknown:
        errors.append(f"{path} unknown fields: {', '.join(unknown)}")


def _object(value: object, path: str, errors: list[str]) -> dict[str, object]:
    if not isinstance(value, Mapping):
        errors.append(f"{path} must be an object")
        return {}
    return dict(value)


def _object_list(
    value: object,
    path: str,
    errors: list[str],
    maximum: int,
) -> list[dict[str, object]]:
    if not isinstance(value, list):
        errors.append(f"{path} must be a list")
        return []
    if len(value) > maximum:
        errors.append(f"{path} exceeds limit {maximum}")
    result = []
    for index, item in enumerate(value[:maximum]):
        if not isinstance(item, Mapping):
            errors.append(f"{path}[{index}] must be an object")
            continue
        result.append(dict(item))
    return result


def _string_list(
    value: object,
    path: str,
    errors: list[str],
    *,
    maximum: int,
    russian: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{path} must be a list")
        return []
    if len(value) > maximum:
        errors.append(f"{path} exceeds limit {maximum}")
    result: list[str] = []
    for index, item in enumerate(value[:maximum]):
        if not isinstance(item, str) or not item or item != item.strip():
            errors.append(f"{path}[{index}] is invalid")
            continue
        if russian and not _CYRILLIC_RE.search(item):
            errors.append(f"{path}[{index}] must contain Russian reader text")
        result.append(item)
    if len(result) != len(set(result)):
        errors.append(f"{path} contains duplicates")
    return result


def _refs(value: object, path: str, errors: list[str], maximum: int) -> list[str]:
    refs = _string_list(value, path, errors, maximum=maximum)
    for index, ref in enumerate(refs):
        if not _REF_RE.fullmatch(ref) or _CONTROL_RE.search(ref) or any(char.isspace() for char in ref):
            errors.append(f"{path}[{index}] is an unsafe ref")
    return refs


def _ref(value: object, path: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not _REF_RE.fullmatch(value) or any(char.isspace() for char in value):
        errors.append(f"{path} is an unsafe ref")
        return ""
    return value


def _russian_text(value: object, path: str, errors: list[str], maximum: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        errors.append(f"{path} is required")
        return ""
    if len(value) > maximum or _CONTROL_RE.search(value):
        errors.append(f"{path} exceeds safe text bounds")
    if not _CYRILLIC_RE.search(value):
        errors.append(f"{path} must contain Russian reader text")
    return value


def _safe_path_text(value: object, path: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        errors.append(f"{path} is required")
        return ""
    if len(value) > 2_000 or _CONTROL_RE.search(value) or "\x00" in value:
        errors.append(f"{path} is unsafe")
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value):
        errors.append(f"{path} must be a filesystem path, not a URI")
    return value


def _validate_period(value: object, errors: list[str]) -> dict[str, str]:
    period = _object(value, "reporting_period", errors)
    _exact_fields(period, _PERIOD_FIELDS, "reporting_period", errors)
    week = period.get("reporting_week")
    if not isinstance(week, str) or not _WEEK_RE.fullmatch(week):
        errors.append("reporting_period.reporting_week is invalid")
    start = _utc(period.get("analysis_period_start"), "reporting_period.analysis_period_start", errors)
    end = _utc(period.get("analysis_period_end"), "reporting_period.analysis_period_end", errors)
    if start and end and (start >= end or (end - start).days != 7):
        errors.append("reporting_period must be one completed seven-day interval")
    return {field: str(period.get(field) or "") for field in _PERIOD_FIELDS}


def _utc(value: object, path: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        errors.append(f"{path} must be UTC text")
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        errors.append(f"{path} is invalid")
        return None
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        errors.append(f"{path} must be UTC")
        return None
    return parsed


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: object) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _unique_text(values: Sequence[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _e(value: object) -> str:
    return escape(str(value), quote=True)
