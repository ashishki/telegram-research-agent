"""IRX-7 opt-in Knowledge Atlas V2 reader package.

The existing week-keyed Knowledge Atlas remains the authoritative V1 audit
artifact.  This module projects that checksum-bound, historical-as-of snapshot
into a deterministic reader surface and publishes it next to a versioned Audit
Explorer without changing the frozen weekly-run stage policy.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from html import escape
import copy
import json
import math
from pathlib import Path
import re
from typing import Any
from urllib.parse import unquote, urlsplit

from output.editorial_intelligence import (
    EDITORIAL_INPUT_SCHEMA_VERSION,
    EditorialValidationError,
    editorial_input_hash,
    validate_editorial_artifact,
)
from output.editorial_intelligence_prompt import EDITORIAL_SCHEMA_VERSION
from output.knowledge_audit_explorer import (
    AUDIT_EXPLORER_SCHEMA_VERSION,
    build_knowledge_audit_explorer,
    render_knowledge_audit_explorer_html,
    validate_knowledge_audit_explorer,
)
from output.reaction_personalization import (
    REACTION_EFFECT_SCHEMA_VERSION,
    ReactionPersonalizationError,
    validate_reaction_effect,
)
from output.report_package_security import (
    ReportPackageSecurityError,
    canonical_json_bytes,
    canonical_output_directory,
    publish_immutable_directory,
    read_bounded_bytes,
    read_strict_json_record,
    require_exact_directory_entries,
    require_private_directory,
    sha256_bytes,
    unique_paths,
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
)


ATLAS_V2_SCHEMA_VERSION = "split_ai_report.v2"
ATLAS_V2_SURFACE = "knowledge_atlas"
ATLAS_V2_PREVIEW_PROFILE = "knowledge_atlas_v2.opt_in.v1"
ATLAS_V2_RENDERER_VERSION = "knowledge_atlas_v2.v1"
ATLAS_V2_SOURCE_CATALOG_SCHEMA_VERSION = "knowledge_atlas_v2_sources.v1"
ATLAS_V2_SOURCE_CONTRIBUTIONS_SCHEMA_VERSION = (
    "knowledge_atlas_source_contributions.v1"
)
ATLAS_V2_RELATIONS_SCHEMA_VERSION = "knowledge_atlas_relations.v1"
ATLAS_V2_HISTORY_SCHEMA_VERSION = "knowledge_atlas_history.v1"
ATLAS_V2_LEARNING_EVENTS_SCHEMA_VERSION = "knowledge_atlas_learning_events.v1"
ATLAS_V2_DIRECTORY = "knowledge_atlases_v2"
ATLAS_V2_HTML_FILENAME = "knowledge-atlas.v2.html"
ATLAS_V2_JSON_FILENAME = "knowledge-atlas.v2.json"
ATLAS_V2_SOURCE_CATALOG_FILENAME = "knowledge-atlas-sources.v1.json"
AUDIT_EXPLORER_HTML_FILENAME = "knowledge-audit-explorer.v1.html"
AUDIT_EXPLORER_JSON_FILENAME = "knowledge-audit-explorer.v1.json"
ATLAS_V2_PACKAGE_FILENAMES = frozenset(
    {
        ATLAS_V2_HTML_FILENAME,
        ATLAS_V2_JSON_FILENAME,
        ATLAS_V2_SOURCE_CATALOG_FILENAME,
        AUDIT_EXPLORER_HTML_FILENAME,
        AUDIT_EXPLORER_JSON_FILENAME,
    }
)

MAX_PRIMARY_THREADS = 12
MIN_PRIMARY_THREADS = 8
MAX_STUDY_BACKLOG = 6
MAX_JSON_BYTES = 2_000_000
MAX_HTML_BYTES = 4_000_000
MAX_SOURCE_BYTES = 4_000_000
HARD_VISIBLE_WORDS_MAX = 1_500

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{5,199}$")
_ISO_WEEK_RE = re.compile(r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$")
_SAFE_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,94}[a-z0-9])?$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_MATURITY_ORDER = (
    "single_source",
    "repeated_signal",
    "multi_channel",
    "primary_verified",
    "externally_corroborated",
    "decision_grade",
)
_MATURITY_WITH_UNKNOWN = (*_MATURITY_ORDER, "unknown")
_MATURITY_LABELS = {
    "single_source": "Один источник",
    "repeated_signal": "Повторяющийся сигнал",
    "multi_channel": "Несколько независимых каналов",
    "primary_verified": "Проверено первичным источником",
    "externally_corroborated": "Подтверждено внешними данными",
    "decision_grade": "Достаточно для решения",
    "unknown": "Зрелость неизвестна",
}
_GRAPH_RELATIONS = {"supports", "depends_on", "contradicts", "converges_with"}
_GRAPH_STATUSES = {"growing", "watch", "stale", "contradicted"}
_CANONICAL_LIFECYCLE_STATUSES = {
    "active",
    "stale",
    "merged",
    "split",
    "resolved",
    "archived",
}
_SOURCE_CLASSES = {
    "primary",
    "vendor_primary",
    "first_party_observation",
    "external_analysis",
    "unknown",
}
_REFERENCE_PREFIXES = {
    "artifact",
    "atom",
    "audit",
    "candidate",
    "canonical_thread",
    "claim",
    "decision",
    "evidence",
    "feedback",
    "idea_thread",
    "learning-objective",
    "project",
    "radar",
    "reaction-post",
    "reaction-snapshot",
    "read-receipt",
    "read_queue",
    "sha256",
    "signal",
    "source_observation",
    "study",
    "thread",
}
_LEARNING_KEYS = (
    "marked",
    "read",
    "understood",
    "explained",
    "tried",
    "implemented",
    "measured",
)
_LEARNING_LABELS = {
    "marked": "Отмечено",
    "read": "Прочитано",
    "understood": "Понято",
    "explained": "Объяснено",
    "tried": "Испробовано",
    "implemented": "Внедрено",
    "measured": "Измерено",
}
_LEARNING_CONFIRMATION = {
    "marked": "reaction",
    "read": "read_receipt",
    "understood": "comprehension_check",
    "explained": "explanation",
    "tried": "trial",
    "implemented": "implementation",
    "measured": "measurement",
}

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
    "as_of",
    "source_run_status",
    "source_contract_statuses",
    "run_status",
    "partial",
    "partial_reasons_ru",
    "primary_thread_ids",
    "canonical_threads",
    "thread_relations",
    "timeline",
    "source_thread_matrix",
    "evidence_maturity",
    "operator_interest",
    "learning_progression",
    "study_backlog",
    "visual_specs",
    "technical_refs",
    "source_artifacts",
    "artifact_paths",
    "content_metrics",
}
_THREAD_FIELDS = {
    "canonical_thread_id",
    "stable_slug",
    "title_ru",
    "thesis",
    "lifecycle_status",
    "lifecycle_observation_status",
    "display_status",
    "first_seen_at",
    "last_seen_at",
    "last_meaningful_change",
    "evidence_count",
    "evidence_refs",
    "evidence_maturity",
    "independent_source_count",
    "external_source_count",
    "decision_grade_evidence_count",
    "operator_interest",
    "merge_split_summary",
    "audit_ref",
}
_RELATION_FIELDS = {
    "source_thread_id",
    "target_thread_id",
    "relation",
    "weight",
    "evidence_refs",
}
_SOURCE_ARTIFACT_KEYS = {
    "manifest",
    "v1_brief_json",
    "v1_atlas_json",
    "v1_atlas_html",
    "editorial",
    "source_catalog",
    "audit_explorer_json",
    "audit_explorer_html",
}
_ARTIFACT_PATH_KEYS = {"html", "json", "source_catalog"}


class KnowledgeAtlasV2Error(ValueError):
    """Base error for the additive Atlas V2 preview."""


class KnowledgeAtlasV2ValidationError(KnowledgeAtlasV2Error):
    """Raised when the closed reader contract is invalid."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(str(item) for item in errors if str(item).strip())
        super().__init__("; ".join(self.errors) or "Knowledge Atlas V2 validation failed")


class KnowledgeAtlasV2ArtifactError(KnowledgeAtlasV2Error):
    """Raised when manifest, source, or immutable package bytes are untrusted."""


@dataclass(frozen=True, slots=True)
class KnowledgeAtlasV2Summary:
    run_id: str
    reporting_week: str
    run_status: str
    partial: bool
    html_path: str
    json_path: str
    source_catalog_path: str
    audit_html_path: str
    audit_json_path: str
    primary_thread_count: int
    relation_count: int
    visual_component_count: int
    meaningful_visual_count: int
    visible_word_count: int
    cache_hit: bool = False


def build_knowledge_atlas_v2(
    *,
    manifest: Mapping[str, object],
    manifest_path: str | Path,
    v1_atlas: Mapping[str, object],
    v1_brief: Mapping[str, object],
    editorial_artifact: Mapping[str, object],
    editorial_input_package: Mapping[str, object],
    audit_explorer: Mapping[str, object],
    source_artifacts: Mapping[str, Mapping[str, object]],
    artifact_paths: Mapping[str, object],
    validated_relations: Mapping[str, object] | None = None,
    historical_observations: Mapping[str, object] | None = None,
    learning_events: Mapping[str, object] | None = None,
    source_contributions: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build one reader DTO from exact V1/as-of and IRX-5 contracts."""

    manifest_value = _json_copy(manifest, "manifest")
    v1 = _json_copy(v1_atlas, "V1 Atlas")
    brief = _json_copy(v1_brief, "V1 Brief")
    editorial = _json_copy(editorial_artifact, "editorial artifact")
    editorial_input = _json_copy(editorial_input_package, "editorial input")
    audit = validate_knowledge_audit_explorer(audit_explorer, manifest=manifest_value)
    _validate_build_identity(
        manifest_value,
        manifest_path=manifest_path,
        v1_atlas=v1,
        v1_brief=brief,
        editorial=editorial,
        editorial_input=editorial_input,
        audit_explorer=audit,
    )

    source_threads = _mapping_list(v1.get("canonical_threads"))
    if len(source_threads) > 100:
        raise KnowledgeAtlasV2ValidationError(
            ["V1 canonical_threads exceeds the bounded Audit compatibility input"]
        )
    if len(source_threads) < MIN_PRIMARY_THREADS:
        raise KnowledgeAtlasV2ValidationError(
            [
                f"V1 historical-as-of canonical registry must contain {MIN_PRIMARY_THREADS}–{MAX_PRIMARY_THREADS} primary threads"
            ]
        )
    primary_ids = _primary_ids(v1, source_threads, editorial, editorial_input)
    if not MIN_PRIMARY_THREADS <= len(primary_ids) <= MAX_PRIMARY_THREADS:
        raise KnowledgeAtlasV2ValidationError(
            [
                f"primary_thread_ids must contain {MIN_PRIMARY_THREADS}–{MAX_PRIMARY_THREADS} canonical IDs"
            ]
        )
    source_threads_by_id = {
        str(item.get("canonical_thread_id") or ""): item for item in source_threads
    }
    primary_source_threads = [source_threads_by_id[thread_id] for thread_id in primary_ids]

    relation_contract = _validate_bound_input_contract(
        validated_relations,
        manifest=manifest_value,
        schema_version=ATLAS_V2_RELATIONS_SCHEMA_VERSION,
        label="validated_relations",
        maximum=100,
        item_normalizer=_normalize_relation_contract_item,
    )
    history_contract = _validate_bound_input_contract(
        historical_observations,
        manifest=manifest_value,
        schema_version=ATLAS_V2_HISTORY_SCHEMA_VERSION,
        label="historical_observations",
        maximum=MAX_PRIMARY_THREADS * 12,
        item_normalizer=_normalize_history_contract_item,
    )
    learning_contract = _validate_bound_input_contract(
        learning_events,
        manifest=manifest_value,
        schema_version=ATLAS_V2_LEARNING_EVENTS_SCHEMA_VERSION,
        label="learning_events",
        maximum=MAX_PRIMARY_THREADS * len(_LEARNING_KEYS),
        item_normalizer=_normalize_learning_contract_item,
    )

    allowed_evidence_by_thread, decision_grade_refs_by_thread = (
        _bound_thread_evidence_authority(
            primary_source_threads,
            v1_atlas=v1,
            editorial_input=editorial_input,
        )
    )
    contribution_contract = _validate_source_contributions(
        source_contributions
        if source_contributions is not None
        else _unavailable_source_contributions(manifest_value),
        manifest=manifest_value,
        known_thread_ids=set(primary_ids),
        allowed_evidence_by_thread=allowed_evidence_by_thread,
        decision_grade_refs_by_thread=decision_grade_refs_by_thread,
    )
    evidence_basis = _thread_evidence_basis(contribution_contract)
    audit_links = {
        str(item.get("thread_ref") or ""): str(item.get("href") or "")
        for item in _mapping_list(audit.get("deep_links"))
    }
    editorial_evidence = {
        str(item.get("signal_id") or "").removeprefix("signal:"): _strings(
            item.get("evidence_refs")
        )
        for item in _mapping_list(editorial_input.get("signal_candidates"))
    }
    navigation_evidence = {
        str(item.get("slug") or ""): _unique_text(
            [
                *_strings(item.get("source_urls")),
                *[
                    ref
                    for evidence_item in _mapping_list(item.get("evidence_items"))
                    for ref in _strings(evidence_item.get("source_urls"))
                ],
            ]
        )
        for item in _mapping_list(
            _mapping(v1.get("thread_navigation")).get("threads")
        )
    }
    reaction = _mapping(v1.get("reaction_effect"))
    feedback_permissions = _mapping(editorial_input.get("feedback_permissions"))
    feedback_status = _feedback_channel_status(editorial_input)
    canonical_threads = [
        _reader_thread(
            item,
            audit_links=audit_links,
            reaction=reaction,
            feedback=_mapping(editorial.get("feedback_effect")),
            feedback_permissions=feedback_permissions,
            feedback_status=feedback_status,
            evidence_basis=evidence_basis.get(
                str(item.get("canonical_thread_id") or ""),
                {},
            ),
            fallback_evidence_refs=_unique_text(
                [
                    *navigation_evidence.get(str(item.get("stable_slug") or ""), []),
                    *editorial_evidence.get(str(item.get("stable_slug") or ""), []),
                ]
            ),
        )
        for item in primary_source_threads
    ]
    by_id = {str(item["canonical_thread_id"]): item for item in canonical_threads}
    canonical_threads = [by_id[thread_id] for thread_id in primary_ids]
    relations = _normalized_relations(
        _mapping_list(relation_contract["items"]),
        known_ids=set(primary_ids),
        evidence_by_thread={
            str(item["canonical_thread_id"]): set(_strings(item.get("evidence_refs")))
            for item in canonical_threads
        },
    )
    contradicted_ids = {
        str(item["target_thread_id"])
        for item in relations
        if item.get("relation") == "contradicts"
    }
    for item in canonical_threads:
        if item["canonical_thread_id"] in contradicted_ids:
            item["display_status"] = "contradicted"
    period = _period_from_manifest(manifest_value)
    timeline = _timeline_projection(
        reporting_week=period["reporting_week"],
        threads=canonical_threads,
        source_threads={
            str(item.get("canonical_thread_id") or ""): item for item in source_threads
        },
        observation_contract=history_contract,
    )
    source_matrix = _source_matrix(canonical_threads, contribution_contract)
    maturity = _maturity_projection(canonical_threads)
    operator_interest = _operator_interest_projection(
        canonical_threads,
        reaction=reaction,
        feedback=_mapping(editorial.get("feedback_effect")),
        feedback_permissions=feedback_permissions,
        feedback_status=feedback_status,
    )
    learning = _learning_projection(
        canonical_threads,
        reaction=reaction,
        event_contract=learning_contract,
    )
    backlog = _study_backlog(canonical_threads)
    run_id = str(manifest_value["run_id"])
    technical_refs = {
        "manifest_path": str(Path(manifest_path).expanduser().absolute()),
        "audit_explorer_path": str(
            _mapping(audit["artifact_paths"])["html"]
        ),
        "audit_explorer_json_path": str(
            _mapping(audit["artifact_paths"])["json"]
        ),
        "compatibility_atlas_path": str(
            _mapping(audit["technical_refs"])["v1_atlas_html_path"]
        ),
        "compatibility_atlas_json_path": str(
            _mapping(audit["technical_refs"])["v1_atlas_json_path"]
        ),
    }
    visual_specs = _visual_specs(
        run_id=run_id,
        period=period,
        threads=canonical_threads,
        relations=relations,
        timeline=timeline,
        source_matrix=source_matrix,
        maturity=maturity,
        learning=learning,
    )
    editorial_source_status = (
        "partial"
        if editorial.get("partial") is True
        or _mapping(editorial_input.get("release_policy")).get("requires_partial")
        is True
        else "complete"
    )
    partial_reasons: list[str] = []
    if manifest_value.get("run_status") == "partial":
        partial_reasons.append(
            "Исходный недельный запуск завершён частично; ограничения сохранены без подстановки соседних данных."
        )
    if reaction.get("snapshot_status") != "complete":
        partial_reasons.append(
            "Снимок личных реакций недоступен; отсутствие внимания не интерпретируется как отрицательный сигнал."
        )
    if editorial_source_status == "partial":
        partial_reasons.append(
            "Редакционный контракт завершён частично; неполные сигналы не повышены до полного выпуска."
        )
    if feedback_status != "available":
        partial_reasons.append(
            "Доступность подтверждённой обратной связи ограничена; неизвестное не заменено нулём."
        )
    if operator_interest.get("historical_attention_status") != "available":
        partial_reasons.append(
            "Историческое внимание доступно не для всех тем; оно показано отдельно от текущих реакций."
        )
    if relation_contract.get("status") != "available":
        partial_reasons.append(
            "Контракт типизированных связей недоступен или неполон; сходство сущностей не использовано вместо доказательств."
        )
    if timeline.get("coverage_status") != "complete":
        partial_reasons.append(
            "История за двенадцать недель неполна; нули сохранены отдельно от отсутствующих наблюдений."
        )
    if learning_contract.get("status") != "available":
        partial_reasons.append(
            "Контракт событий обучения недоступен или неполон; неподтверждённые переходы оставлены неизвестными."
        )
    if contribution_contract.get("classification_status") != "complete":
        partial_reasons.append(str(contribution_contract["limitation_ru"]))
    if any(
        item.get("lifecycle_observation_status") != "available"
        for item in canonical_threads
    ):
        partial_reasons.append(
            "Для части канонических тем даты жизненного цикла недоступны; неизвестные значения не заменены датой запуска."
        )
    partial_reasons = _unique_text(partial_reasons)
    sidecar: dict[str, object] = {
        "schema_version": ATLAS_V2_SCHEMA_VERSION,
        "surface": ATLAS_V2_SURFACE,
        "preview_profile": ATLAS_V2_PREVIEW_PROFILE,
        "renderer_version": ATLAS_V2_RENDERER_VERSION,
        "source_schema_versions": {
            "manifest": MANIFEST_SCHEMA_VERSION,
            "compatibility_brief": "split_ai_report.v1",
            "compatibility_atlas": "split_ai_report.v1",
            "editorial": EDITORIAL_SCHEMA_VERSION,
            "editorial_input": EDITORIAL_INPUT_SCHEMA_VERSION,
            "reaction": REACTION_EFFECT_SCHEMA_VERSION,
            "report_visuals": REPORT_VISUALS_CONTRACT_VERSION,
            "audit_explorer": AUDIT_EXPLORER_SCHEMA_VERSION,
            "source_catalog": ATLAS_V2_SOURCE_CATALOG_SCHEMA_VERSION,
            "source_contributions": ATLAS_V2_SOURCE_CONTRIBUTIONS_SCHEMA_VERSION,
            "relations": ATLAS_V2_RELATIONS_SCHEMA_VERSION,
            "history": ATLAS_V2_HISTORY_SCHEMA_VERSION,
            "learning_events": ATLAS_V2_LEARNING_EVENTS_SCHEMA_VERSION,
        },
        "run_id": run_id,
        "generated_at": str(manifest_value["generated_at"]),
        "period_mode": str(manifest_value["period_mode"]),
        "reporting_period": period,
        "as_of": period["analysis_period_end"],
        "source_run_status": str(manifest_value["run_status"]),
        "source_contract_statuses": {
            "editorial": editorial_source_status,
            "relations": str(relation_contract["status"]),
            "history": str(history_contract["status"]),
            "learning_events": str(learning_contract["status"]),
        },
        "run_status": "partial" if partial_reasons else "complete",
        "partial": bool(partial_reasons),
        "partial_reasons_ru": partial_reasons,
        "primary_thread_ids": primary_ids,
        "canonical_threads": canonical_threads,
        "thread_relations": relations,
        "timeline": timeline,
        "source_thread_matrix": source_matrix,
        "evidence_maturity": maturity,
        "operator_interest": operator_interest,
        "learning_progression": learning,
        "study_backlog": backlog,
        "visual_specs": visual_specs,
        "technical_refs": technical_refs,
        "source_artifacts": _normalize_source_artifacts(source_artifacts),
        "artifact_paths": _normalize_artifact_paths(artifact_paths),
        "content_metrics": {
            "visible_word_count": 0,
            "hard_max": HARD_VISIBLE_WORDS_MAX,
            "word_budget_status": "pending",
            "visual_component_count": len(visual_specs),
            "meaningful_visual_count": _meaningful_visual_count(visual_specs),
        },
    }
    _validate_knowledge_atlas_v2(sidecar, manifest=manifest_value, verify_metrics=False)
    html = _render_document(sidecar)
    word_count = _reader_visible_word_count(html)
    sidecar["content_metrics"] = {
        **dict(_mapping(sidecar["content_metrics"])),
        "visible_word_count": word_count,
        "word_budget_status": "within_budget" if word_count <= HARD_VISIBLE_WORDS_MAX else "exceeded",
    }
    validate_knowledge_atlas_v2(sidecar, manifest=manifest_value)
    return sidecar


def validate_knowledge_atlas_v2(
    payload: Mapping[str, object],
    *,
    manifest: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Validate the closed sidecar and return a detached JSON-safe copy."""

    value = _json_copy(payload, "Knowledge Atlas V2 sidecar")
    _validate_knowledge_atlas_v2(value, manifest=manifest)
    return value


def render_knowledge_atlas_v2_html(
    payload: Mapping[str, object],
    *,
    manifest: Mapping[str, object] | None = None,
) -> str:
    """Render validated reader HTML without filesystem, clock, or ranking work."""

    return _render_document(validate_knowledge_atlas_v2(payload, manifest=manifest))


def summary_as_dict(summary: KnowledgeAtlasV2Summary) -> dict[str, object]:
    return asdict(summary)


def generate_knowledge_atlas_v2_package(
    *,
    manifest_path: str | Path,
    editorial_artifact_path: str | Path,
    editorial_input_package: Mapping[str, object],
    output_root: str | Path,
    allowed_source_roots: Sequence[str | Path] = (),
    validated_relations: Mapping[str, object] | None = None,
    historical_observations: Mapping[str, object] | None = None,
    learning_events: Mapping[str, object] | None = None,
    source_contributions: Mapping[str, object] | None = None,
) -> KnowledgeAtlasV2Summary:
    """Create or exactly reuse one immutable Atlas/Audit run package."""

    try:
        manifest_file = _canonical_existing_path(manifest_path, label="weekly manifest")
        if manifest_file.name != "manifest.json":
            raise KnowledgeAtlasV2ArtifactError("Atlas V2 requires canonical manifest.json")
        manifest_record = read_strict_json_record(
            manifest_file,
            label="weekly manifest",
            maximum=MAX_SOURCE_BYTES,
        )
        if not isinstance(manifest_record.value, dict):
            raise KnowledgeAtlasV2ArtifactError("weekly manifest root must be an object")
        manifest = manifest_record.value
        validate_manifest(
            manifest,
            path_base=manifest_file.parent,
            allowed_roots=(manifest_file.parent,),
            check_artifact_existence=False,
        )
        _require_terminal_manifest(manifest, manifest_file)
        validate_manifest(
            manifest,
            path_base=manifest_file.parent,
            allowed_roots=(manifest_file.parent,),
            check_artifact_existence=True,
        )
        run_dir = manifest_file.parent
        roots = unique_paths(
            [
                run_dir,
                Path(output_root).expanduser().absolute(),
                *[Path(root).expanduser().absolute() for root in allowed_source_roots],
            ]
        )
        v1_json_path, v1_html_path = _bound_v1_atlas_paths(manifest, manifest_file)
        _require_contained_canonical(v1_json_path, roots)
        _require_contained_canonical(v1_html_path, roots)
        v1_json_record = read_strict_json_record(
            v1_json_path,
            label="manifest-bound V1 Atlas JSON",
            maximum=MAX_SOURCE_BYTES,
        )
        if not isinstance(v1_json_record.value, dict):
            raise KnowledgeAtlasV2ArtifactError("V1 Atlas JSON root must be an object")
        v1_atlas = v1_json_record.value
        v1_html_bytes = read_bounded_bytes(
            v1_html_path,
            label="manifest-bound V1 Atlas HTML",
            maximum=MAX_SOURCE_BYTES,
        )
        _verify_stage_checksum(manifest, "knowledge_atlas", "json_path", v1_json_record.sha256)
        _verify_stage_checksum(
            manifest,
            "knowledge_atlas",
            "html_path",
            sha256_bytes(v1_html_bytes),
        )
        v1_brief_json_path = _bound_v1_brief_json_path(manifest, manifest_file)
        _require_contained_canonical(v1_brief_json_path, roots)
        v1_brief_record = read_strict_json_record(
            v1_brief_json_path,
            label="manifest-bound V1 Brief JSON",
            maximum=MAX_SOURCE_BYTES,
        )
        if not isinstance(v1_brief_record.value, dict):
            raise KnowledgeAtlasV2ArtifactError("V1 Brief JSON root must be an object")
        v1_brief = v1_brief_record.value
        _verify_stage_checksum(
            manifest,
            "weekly_brief",
            "json_path",
            v1_brief_record.sha256,
        )
        editorial_file = _canonical_existing_path(
            editorial_artifact_path,
            label="editorial artifact",
        )
        _require_contained_canonical(editorial_file, roots)
        editorial_record = read_strict_json_record(
            editorial_file,
            label="editorial artifact",
            maximum=MAX_SOURCE_BYTES,
        )
        if not isinstance(editorial_record.value, dict):
            raise KnowledgeAtlasV2ArtifactError("editorial artifact root must be an object")
        editorial = editorial_record.value

        run_id = str(manifest["run_id"])
        output_dir = canonical_output_directory(
            output_root,
            ATLAS_V2_DIRECTORY,
            run_id,
        )
        paths = {
            "html": output_dir / ATLAS_V2_HTML_FILENAME,
            "json": output_dir / ATLAS_V2_JSON_FILENAME,
            "source_catalog": output_dir / ATLAS_V2_SOURCE_CATALOG_FILENAME,
            "audit_html": output_dir / AUDIT_EXPLORER_HTML_FILENAME,
            "audit_json": output_dir / AUDIT_EXPLORER_JSON_FILENAME,
        }
        source_catalog = _build_source_catalog(
            manifest=manifest,
            editorial_input_package=editorial_input_package,
            validated_relations=validated_relations,
            historical_observations=historical_observations,
            learning_events=learning_events,
            source_contributions=source_contributions,
        )
        source_catalog_bytes = canonical_json_bytes(source_catalog)
        audit_sources = {
            "manifest": _source_descriptor(manifest_file, manifest_record.sha256, manifest_record.size),
            "v1_atlas_html": _source_descriptor(
                v1_html_path,
                sha256_bytes(v1_html_bytes),
                len(v1_html_bytes),
            ),
            "v1_atlas_json": _source_descriptor(
                v1_json_path,
                v1_json_record.sha256,
                v1_json_record.size,
            ),
        }
        audit = build_knowledge_audit_explorer(
            manifest,
            manifest_file,
            v1_atlas,
            v1_html_path,
            v1_json_path,
            {"html": str(paths["audit_html"]), "json": str(paths["audit_json"])},
            audit_sources,
        )
        audit_html_text = render_knowledge_audit_explorer_html(
            audit,
            v1_html_bytes.decode("utf-8"),
            manifest=manifest,
        )
        audit_html_bytes = audit_html_text.encode("utf-8")
        audit_json_bytes = canonical_json_bytes(audit)
        source_artifacts = {
            **audit_sources,
            "v1_brief_json": _source_descriptor(
                v1_brief_json_path,
                v1_brief_record.sha256,
                v1_brief_record.size,
            ),
            "editorial": _source_descriptor(
                editorial_file,
                editorial_record.sha256,
                editorial_record.size,
            ),
            "source_catalog": _source_descriptor(
                paths["source_catalog"],
                sha256_bytes(source_catalog_bytes),
                len(source_catalog_bytes),
            ),
            "audit_explorer_json": _source_descriptor(
                paths["audit_json"],
                sha256_bytes(audit_json_bytes),
                len(audit_json_bytes),
            ),
            "audit_explorer_html": _source_descriptor(
                paths["audit_html"],
                sha256_bytes(audit_html_bytes),
                len(audit_html_bytes),
            ),
        }
        sidecar = build_knowledge_atlas_v2(
            manifest=manifest,
            manifest_path=manifest_file,
            v1_atlas=v1_atlas,
            v1_brief=v1_brief,
            editorial_artifact=editorial,
            editorial_input_package=editorial_input_package,
            audit_explorer=audit,
            source_artifacts=source_artifacts,
            artifact_paths={
                "html": str(paths["html"]),
                "json": str(paths["json"]),
                "source_catalog": str(paths["source_catalog"]),
            },
            validated_relations=_mapping(source_catalog["validated_relations"]),
            historical_observations=_mapping(source_catalog["historical_observations"]),
            learning_events=_mapping(source_catalog["learning_events"]),
            source_contributions=_mapping(source_catalog["source_contributions"]),
        )
        html_text = render_knowledge_atlas_v2_html(sidecar, manifest=manifest)
        _require_reader_value_quality(sidecar, html_text, manifest=manifest)
        html_bytes = html_text.encode("utf-8")
        json_bytes = canonical_json_bytes(sidecar)
        limits = (
            (html_bytes, MAX_HTML_BYTES, "Atlas HTML"),
            (json_bytes, MAX_JSON_BYTES, "Atlas JSON"),
            (source_catalog_bytes, MAX_SOURCE_BYTES, "Atlas source catalog"),
            (audit_html_bytes, MAX_HTML_BYTES, "Audit Explorer HTML"),
            (audit_json_bytes, MAX_JSON_BYTES, "Audit Explorer JSON"),
        )
        for data, maximum, label in limits:
            if len(data) > maximum:
                raise KnowledgeAtlasV2ArtifactError(f"{label} exceeds byte limit")
        cache_hit = publish_immutable_directory(
            (
                (paths["source_catalog"], source_catalog_bytes),
                (paths["audit_html"], audit_html_bytes),
                (paths["audit_json"], audit_json_bytes),
                (paths["html"], html_bytes),
                (paths["json"], json_bytes),
            )
        )
        loaded = load_manifest_bound_knowledge_atlas_v2(
            paths["json"],
            expected_manifest_path=manifest_file,
            allowed_source_roots=roots,
        )
        if loaded != sidecar:
            raise KnowledgeAtlasV2ArtifactError("Atlas V2 write verification changed sidecar")
        return _summary(sidecar, cache_hit=cache_hit)
    except KnowledgeAtlasV2Error:
        raise
    except (ReportPackageSecurityError, WeeklyRunManifestError, OSError, ValueError) as exc:
        raise KnowledgeAtlasV2ArtifactError(str(exc)) from exc


def load_manifest_bound_knowledge_atlas_v2(
    path: str | Path,
    *,
    expected_manifest_path: str | Path,
    allowed_source_roots: Sequence[str | Path] = (),
) -> dict[str, object]:
    """Strictly load one exact-run Atlas and rebuild all deterministic bytes."""

    try:
        source = _canonical_existing_path(path, label="Atlas V2 sidecar")
        require_private_directory(source.parent, label="Atlas V2 package directory")
        require_exact_directory_entries(
            source.parent,
            tuple(sorted(ATLAS_V2_PACKAGE_FILENAMES)),
            label="Atlas V2 package directory",
        )
        sidecar_record = read_strict_json_record(
            source,
            label="Atlas V2 sidecar",
            maximum=MAX_JSON_BYTES,
            require_private=True,
        )
        if not isinstance(sidecar_record.value, dict):
            raise KnowledgeAtlasV2ArtifactError("Atlas V2 root must be an object")
        value = validate_knowledge_atlas_v2(sidecar_record.value)
        run_id = str(value["run_id"])
        if (
            source.name != ATLAS_V2_JSON_FILENAME
            or source.parent.name != run_id
            or source.parent.parent.name != ATLAS_V2_DIRECTORY
        ):
            raise KnowledgeAtlasV2ArtifactError("Atlas V2 is outside its exact run path")
        paths = _mapping(value["artifact_paths"])
        expected_package_paths = {
            "html": source.parent / ATLAS_V2_HTML_FILENAME,
            "json": source,
            "source_catalog": source.parent / ATLAS_V2_SOURCE_CATALOG_FILENAME,
        }
        for name, expected in expected_package_paths.items():
            actual = _canonical_existing_path(paths[name], label=f"Atlas V2 {name}")
            if actual != expected:
                raise KnowledgeAtlasV2ArtifactError(f"Atlas V2 {name} path mismatch")
        technical = _mapping(value["technical_refs"])
        manifest_file = _canonical_existing_path(
            technical["manifest_path"],
            label="Atlas V2 manifest dependency",
        )
        caller_manifest = _canonical_existing_path(
            expected_manifest_path,
            label="caller-selected manifest",
        )
        if manifest_file != caller_manifest:
            raise KnowledgeAtlasV2ArtifactError("Atlas V2 manifest selection mismatch")
        base_roots = unique_paths(
            [
                source.parent.parent.parent,
                manifest_file.parent,
                *[Path(root).expanduser().absolute() for root in allowed_source_roots],
            ]
        )
        _require_contained_canonical(manifest_file, base_roots)
        manifest_record = read_strict_json_record(
            manifest_file,
            label="weekly manifest",
            maximum=MAX_SOURCE_BYTES,
        )
        if not isinstance(manifest_record.value, dict):
            raise KnowledgeAtlasV2ArtifactError("weekly manifest root must be an object")
        manifest = manifest_record.value
        validate_manifest(
            manifest,
            path_base=manifest_file.parent,
            allowed_roots=(manifest_file.parent,),
            check_artifact_existence=True,
        )
        _require_terminal_manifest(manifest, manifest_file)
        validate_knowledge_atlas_v2(value, manifest=manifest)

        descriptors = _mapping(value["source_artifacts"])
        descriptor_path_expectations = {
            "manifest": manifest_file,
            "v1_brief_json": _bound_v1_brief_json_path(manifest, manifest_file),
            "v1_atlas_json": _bound_v1_atlas_paths(manifest, manifest_file)[0],
            "v1_atlas_html": _bound_v1_atlas_paths(manifest, manifest_file)[1],
            "source_catalog": source.parent / ATLAS_V2_SOURCE_CATALOG_FILENAME,
            "audit_explorer_json": source.parent / AUDIT_EXPLORER_JSON_FILENAME,
            "audit_explorer_html": source.parent / AUDIT_EXPLORER_HTML_FILENAME,
        }
        for name, expected_path in descriptor_path_expectations.items():
            actual_path = _canonical_existing_path(
                _mapping(descriptors[name])["path"],
                label=f"Atlas V2 dependency {name}",
            )
            if actual_path != expected_path:
                raise KnowledgeAtlasV2ArtifactError(
                    f"Atlas V2 dependency path mismatch: {name}"
                )
        loaded_bytes: dict[str, bytes] = {}
        loaded_json: dict[str, object] = {}
        for name in _SOURCE_ARTIFACT_KEYS:
            descriptor = _mapping(descriptors[name])
            dependency = _canonical_existing_path(
                descriptor["path"],
                label=f"Atlas V2 dependency {name}",
            )
            _require_contained_canonical(dependency, base_roots)
            maximum = MAX_HTML_BYTES if name.endswith("html") else MAX_SOURCE_BYTES
            data = read_bounded_bytes(
                dependency,
                label=f"Atlas V2 dependency {name}",
                maximum=maximum,
                require_private=name in {
                    "source_catalog",
                    "audit_explorer_json",
                    "audit_explorer_html",
                },
            )
            if sha256_bytes(data) != descriptor.get("sha256") or len(data) != descriptor.get("size"):
                raise KnowledgeAtlasV2ArtifactError(f"Atlas V2 dependency checksum mismatch: {name}")
            loaded_bytes[name] = data
            if not name.endswith("html"):
                record = read_strict_json_record(
                    dependency,
                    label=f"Atlas V2 dependency {name}",
                    maximum=maximum,
                    require_private=name in {"source_catalog", "audit_explorer_json"},
                )
                loaded_json[name] = record.value
        if loaded_json.get("manifest") != manifest:
            raise KnowledgeAtlasV2ArtifactError("Atlas V2 manifest bytes/source mismatch")
        v1_atlas = loaded_json.get("v1_atlas_json")
        v1_brief = loaded_json.get("v1_brief_json")
        editorial = loaded_json.get("editorial")
        source_catalog = loaded_json.get("source_catalog")
        audit = loaded_json.get("audit_explorer_json")
        if not all(
            isinstance(item, dict)
            for item in (v1_atlas, v1_brief, editorial, source_catalog, audit)
        ):
            raise KnowledgeAtlasV2ArtifactError("Atlas V2 JSON dependency root mismatch")
        catalog = _validate_source_catalog(source_catalog, manifest=manifest)
        if loaded_bytes["source_catalog"] != canonical_json_bytes(catalog):
            raise KnowledgeAtlasV2ArtifactError(
                "Atlas V2 source catalog is not canonical JSON"
            )
        v1_json_path, v1_html_path = _bound_v1_atlas_paths(manifest, manifest_file)
        if (
            _canonical_existing_path(descriptors["v1_atlas_json"]["path"], label="V1 Atlas JSON") != v1_json_path
            or _canonical_existing_path(descriptors["v1_atlas_html"]["path"], label="V1 Atlas HTML") != v1_html_path
        ):
            raise KnowledgeAtlasV2ArtifactError("Atlas V2 V1 source is not manifest-bound")
        _verify_stage_checksum(manifest, "knowledge_atlas", "json_path", sha256_bytes(loaded_bytes["v1_atlas_json"]))
        _verify_stage_checksum(manifest, "knowledge_atlas", "html_path", sha256_bytes(loaded_bytes["v1_atlas_html"]))
        _verify_stage_checksum(
            manifest,
            "weekly_brief",
            "json_path",
            sha256_bytes(loaded_bytes["v1_brief_json"]),
        )
        audit_paths = {
            "html": str(source.parent / AUDIT_EXPLORER_HTML_FILENAME),
            "json": str(source.parent / AUDIT_EXPLORER_JSON_FILENAME),
        }
        expected_audit = build_knowledge_audit_explorer(
            manifest,
            manifest_file,
            v1_atlas,
            v1_html_path,
            v1_json_path,
            audit_paths,
            {
                name: descriptors[name]
                for name in ("manifest", "v1_atlas_html", "v1_atlas_json")
            },
        )
        if audit != expected_audit:
            raise KnowledgeAtlasV2ArtifactError("Audit Explorer differs from deterministic V1 adapter")
        if loaded_bytes["audit_explorer_json"] != canonical_json_bytes(expected_audit):
            raise KnowledgeAtlasV2ArtifactError(
                "Audit Explorer JSON differs from canonical bytes"
            )
        expected_audit_html = render_knowledge_audit_explorer_html(
            expected_audit,
            loaded_bytes["v1_atlas_html"].decode("utf-8"),
            manifest=manifest,
        ).encode("utf-8")
        if loaded_bytes["audit_explorer_html"] != expected_audit_html:
            raise KnowledgeAtlasV2ArtifactError("Audit Explorer HTML parity mismatch")
        expected = build_knowledge_atlas_v2(
            manifest=manifest,
            manifest_path=manifest_file,
            v1_atlas=v1_atlas,
            v1_brief=v1_brief,
            editorial_artifact=editorial,
            editorial_input_package=_mapping(catalog["editorial_input_package"]),
            audit_explorer=expected_audit,
            source_artifacts=descriptors,
            artifact_paths=paths,
            validated_relations=_mapping(catalog["validated_relations"]),
            historical_observations=_mapping(catalog["historical_observations"]),
            learning_events=_mapping(catalog["learning_events"]),
            source_contributions=_mapping(catalog["source_contributions"]),
        )
        if expected != value:
            raise KnowledgeAtlasV2ArtifactError("Atlas V2 differs from deterministic source projection")
        html_bytes = read_bounded_bytes(
            expected_package_paths["html"],
            label="Atlas V2 HTML",
            maximum=MAX_HTML_BYTES,
            require_private=True,
        )
        expected_html = render_knowledge_atlas_v2_html(value, manifest=manifest).encode("utf-8")
        if html_bytes != expected_html:
            raise KnowledgeAtlasV2ArtifactError("Atlas V2 HTML parity mismatch")
        # Re-read every dependency to close the source-swap/TOCTOU window.
        for name, first in loaded_bytes.items():
            current = read_bounded_bytes(
                descriptors[name]["path"],
                label=f"Atlas V2 dependency recheck {name}",
                maximum=MAX_HTML_BYTES if name.endswith("html") else MAX_SOURCE_BYTES,
                require_private=name in {
                    "source_catalog",
                    "audit_explorer_json",
                    "audit_explorer_html",
                },
            )
            if current != first:
                raise KnowledgeAtlasV2ArtifactError(f"Atlas V2 dependency changed while loading: {name}")
        if read_bounded_bytes(
            source,
            label="Atlas V2 sidecar recheck",
            maximum=MAX_JSON_BYTES,
            require_private=True,
        ) != canonical_json_bytes(value):
            raise KnowledgeAtlasV2ArtifactError(
                "Atlas V2 sidecar changed while loading"
            )
        if read_bounded_bytes(
            expected_package_paths["html"],
            label="Atlas V2 HTML recheck",
            maximum=MAX_HTML_BYTES,
            require_private=True,
        ) != expected_html:
            raise KnowledgeAtlasV2ArtifactError("Atlas V2 HTML changed while loading")
        _require_reader_value_quality(value, expected_html.decode("utf-8"), manifest=manifest)
        require_exact_directory_entries(
            source.parent,
            tuple(sorted(ATLAS_V2_PACKAGE_FILENAMES)),
            label="Atlas V2 package directory recheck",
        )
        return value
    except KnowledgeAtlasV2Error:
        raise
    except (ReportPackageSecurityError, WeeklyRunManifestError, OSError, ValueError) as exc:
        raise KnowledgeAtlasV2ArtifactError(str(exc)) from exc


def find_manifest_bound_knowledge_atlas_v2(
    *,
    output_root: str | Path,
    run_id: str,
    expected_manifest_path: str | Path,
    allowed_source_roots: Sequence[str | Path] = (),
) -> dict[str, object] | None:
    """Find only the caller-selected run; never use a week/neighbor fallback."""

    if not _RUN_ID_RE.fullmatch(str(run_id or "")):
        raise KnowledgeAtlasV2ArtifactError("Atlas V2 run_id is invalid")
    try:
        requested = Path(output_root).expanduser().absolute()
        canonical = requested.resolve()
        if requested != canonical:
            raise KnowledgeAtlasV2ArtifactError("Atlas V2 finder root must be canonical")
        if not canonical.exists():
            return None
        root = canonical / ATLAS_V2_DIRECTORY
        if not root.exists():
            return None
        if root.is_symlink() or not root.is_dir() or root.resolve(strict=True) != root:
            raise KnowledgeAtlasV2ArtifactError("Atlas V2 finder root is invalid")
        candidate = root / str(run_id) / ATLAS_V2_JSON_FILENAME
        if not candidate.exists():
            return None
        return load_manifest_bound_knowledge_atlas_v2(
            candidate,
            expected_manifest_path=expected_manifest_path,
            allowed_source_roots=allowed_source_roots,
        )
    except KnowledgeAtlasV2Error:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise KnowledgeAtlasV2ArtifactError("Atlas V2 finder path is invalid") from exc


def _summary(sidecar: Mapping[str, object], *, cache_hit: bool) -> KnowledgeAtlasV2Summary:
    paths = _mapping(sidecar["artifact_paths"])
    technical = _mapping(sidecar["technical_refs"])
    metrics = _mapping(sidecar["content_metrics"])
    period = _mapping(sidecar["reporting_period"])
    return KnowledgeAtlasV2Summary(
        run_id=str(sidecar["run_id"]),
        reporting_week=str(period["reporting_week"]),
        run_status=str(sidecar["run_status"]),
        partial=bool(sidecar["partial"]),
        html_path=str(paths["html"]),
        json_path=str(paths["json"]),
        source_catalog_path=str(paths["source_catalog"]),
        audit_html_path=str(technical["audit_explorer_path"]),
        audit_json_path=str(technical["audit_explorer_json_path"]),
        primary_thread_count=len(sidecar["primary_thread_ids"]),
        relation_count=len(sidecar["thread_relations"]),
        visual_component_count=int(metrics["visual_component_count"]),
        meaningful_visual_count=int(metrics["meaningful_visual_count"]),
        visible_word_count=int(metrics["visible_word_count"]),
        cache_hit=cache_hit,
    )


def _validate_build_identity(
    manifest: Mapping[str, object],
    *,
    manifest_path: str | Path,
    v1_atlas: Mapping[str, object],
    v1_brief: Mapping[str, object],
    editorial: Mapping[str, object],
    editorial_input: Mapping[str, object],
    audit_explorer: Mapping[str, object],
) -> None:
    errors: list[str] = []
    path = Path(manifest_path).expanduser().absolute()
    run_id = str(manifest.get("run_id") or "")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append("manifest schema mismatch")
    if not _RUN_ID_RE.fullmatch(run_id):
        errors.append("manifest run_id is invalid")
    if path.name != "manifest.json" or path.parent.name != run_id:
        errors.append("manifest path does not match run_id")
    if manifest.get("run_status") not in {"complete", "partial"}:
        errors.append("Atlas V2 requires a terminal reader manifest")
    if manifest.get("period_mode") not in {"completed_iso_week", "explicit_iso_week"}:
        errors.append("Atlas V2 requires a completed or explicit ISO week")
    period = _period_from_manifest(manifest)
    if not _ISO_WEEK_RE.fullmatch(period["reporting_week"]):
        errors.append("manifest reporting_week is invalid")
    if v1_atlas.get("schema_version") != "split_ai_report.v1" or v1_atlas.get(
        "artifact_type"
    ) != "knowledge_atlas":
        errors.append("compatibility Atlas schema/type mismatch")
    expected_flat = {
        "run_id": run_id,
        "generated_at": manifest.get("generated_at"),
        "period_mode": manifest.get("period_mode"),
        **period,
    }
    for field, expected in expected_flat.items():
        if v1_atlas.get(field) != expected:
            errors.append(f"compatibility Atlas {field} mismatch")
    if v1_brief.get("schema_version") != "split_ai_report.v1" or v1_brief.get(
        "artifact_type"
    ) != "weekly_intelligence_brief":
        errors.append("compatibility Brief schema/type mismatch")
    for field, expected in expected_flat.items():
        if v1_brief.get(field) != expected:
            errors.append(f"compatibility Brief {field} mismatch")
    if v1_atlas.get("canonical_thread_snapshot", {}).get("as_of") != period[
        "analysis_period_end"
    ]:
        errors.append("compatibility Atlas canonical snapshot as_of mismatch")
    if editorial_input.get("schema_version") != EDITORIAL_INPUT_SCHEMA_VERSION:
        errors.append("editorial input schema mismatch")
    if editorial_input.get("run_id") != run_id:
        errors.append("editorial input run_id mismatch")
    if _mapping(editorial_input.get("reporting_period")) != period:
        errors.append("editorial input reporting period mismatch")
    run_context = _mapping(editorial_input.get("run_context"))
    for field in ("generated_at", "period_mode", "pipeline_profile"):
        if run_context.get(field) != manifest.get(field):
            errors.append(f"editorial input {field} mismatch")
    receipt = _mapping(editorial.get("generation_receipt"))
    requested_model = str(receipt.get("requested_model") or "")
    try:
        validate_editorial_artifact(
            editorial,
            input_package=editorial_input,
            expected_model=requested_model or None,
            expected_input_hash=(
                editorial_input_hash(editorial_input, model=requested_model)
                if requested_model
                else None
            ),
        )
    except EditorialValidationError as exc:
        errors.extend(f"editorial artifact: {item}" for item in exc.errors)
    if editorial.get("run_id") != run_id or _mapping(
        editorial.get("reporting_period")
    ) != period:
        errors.append("editorial artifact run/period mismatch")
    reaction = _mapping(v1_atlas.get("reaction_effect"))
    brief_reaction = _mapping(v1_brief.get("reaction_effect"))
    try:
        validate_reaction_effect(reaction)
    except (ReactionPersonalizationError, TypeError, ValueError) as exc:
        errors.append(f"compatibility Atlas reaction receipt invalid: {exc}")
    else:
        expected_reaction = {"run_id": run_id, "surface": "knowledge_atlas", **period}
        for field, expected in expected_reaction.items():
            if reaction.get(field) != expected:
                errors.append(f"reaction receipt {field} mismatch")
    try:
        validate_reaction_effect(brief_reaction)
    except (ReactionPersonalizationError, TypeError, ValueError) as exc:
        errors.append(f"compatibility Brief reaction receipt invalid: {exc}")
    else:
        expected_brief_reaction = {
            "run_id": run_id,
            "surface": "weekly_brief",
            **period,
        }
        for field, expected in expected_brief_reaction.items():
            if brief_reaction.get(field) != expected:
                errors.append(f"Brief reaction receipt {field} mismatch")
        errors.extend(
            _editorial_reaction_parity_errors(
                editorial_input,
                reaction=brief_reaction,
            )
        )
    if reaction and brief_reaction:
        errors.extend(_cross_surface_reaction_errors(brief_reaction, reaction))
    errors.extend(_editorial_signal_order_errors(editorial, editorial_input))
    if audit_explorer.get("run_id") != run_id or _mapping(
        audit_explorer.get("reporting_period")
    ) != period:
        errors.append("Audit Explorer run/period mismatch")
    if errors:
        raise KnowledgeAtlasV2ValidationError(errors)


def _primary_ids(
    v1: Mapping[str, object],
    threads: Sequence[Mapping[str, object]],
    editorial: Mapping[str, object],
    editorial_input: Mapping[str, object],
) -> list[str]:
    known_order = [str(item.get("canonical_thread_id") or "") for item in threads]
    if not all(known_order) or len(known_order) != len(set(known_order)):
        raise KnowledgeAtlasV2ValidationError(
            ["canonical thread identities must be non-empty and unique"]
        )
    raw_declared = v1.get("primary_canonical_thread_ids")
    if raw_declared is None:
        declared = known_order
    elif (
        not isinstance(raw_declared, list)
        or not raw_declared
        or len(raw_declared) > 100
        or not all(
            isinstance(item, str) and item and item == item.strip()
            for item in raw_declared
        )
    ):
        raise KnowledgeAtlasV2ValidationError(
            ["primary canonical IDs must be a strict non-empty string list"]
        )
    else:
        declared = list(raw_declared)
    if len(declared) != len(set(declared)):
        raise KnowledgeAtlasV2ValidationError(["primary canonical IDs are duplicated"])
    unknown = sorted(set(declared).difference(known_order))
    if unknown:
        raise KnowledgeAtlasV2ValidationError(
            [f"primary canonical IDs are unknown: {', '.join(unknown[:4])}"]
        )
    selected_signal_ids = {
        str(item.get("signal_id") or "")
        for item in _mapping_list(editorial.get("signals"))
    }
    selected_slugs = [
        signal_id.removeprefix("signal:")
        for signal_id in (
            str(item.get("signal_id") or "")
            for item in _mapping_list(editorial_input.get("signal_candidates"))
        )
        if signal_id in selected_signal_ids
    ]
    by_slug = {
        str(item.get("stable_slug") or ""): str(item.get("canonical_thread_id") or "")
        for item in threads
    }
    editorial_ids = [by_slug[slug] for slug in selected_slugs if slug in by_slug]
    return _unique_text([*editorial_ids, *declared])


def _editorial_signal_order_errors(
    editorial: Mapping[str, object],
    editorial_input: Mapping[str, object],
) -> list[str]:
    """Keep ordering authority in the deterministic IRX-5 input package."""

    candidate_order = [
        str(item.get("signal_id") or "")
        for item in _mapping_list(editorial_input.get("signal_candidates"))
    ]
    returned_order = [
        str(item.get("signal_id") or "")
        for item in _mapping_list(editorial.get("signals"))
    ]
    positions = {signal_id: index for index, signal_id in enumerate(candidate_order)}
    if (
        len(candidate_order) != len(positions)
        or len(returned_order) != len(set(returned_order))
        or any(signal_id not in positions for signal_id in returned_order)
        or [positions[signal_id] for signal_id in returned_order if signal_id in positions]
        != sorted(
            positions[signal_id]
            for signal_id in returned_order
            if signal_id in positions
        )
    ):
        return ["editorial signals do not preserve the validated input order"]
    return []


def _editorial_reaction_parity_errors(
    editorial_input: Mapping[str, object],
    *,
    reaction: Mapping[str, object],
) -> list[str]:
    errors: list[str] = []
    for index, candidate in enumerate(
        _mapping_list(editorial_input.get("signal_candidates"))
    ):
        expected = _reaction_effect_for_candidate(
            reaction,
            candidate.get("source_thread_refs"),
        )
        if candidate.get("reaction_effect") != expected:
            errors.append(
                f"signal_candidates[{index}].reaction_effect differs from the bound receipt"
            )
    return errors


def _cross_surface_reaction_errors(
    brief_reaction: Mapping[str, object],
    atlas_reaction: Mapping[str, object],
) -> list[str]:
    common_fields = (
        "schema_version",
        "run_id",
        "reporting_week",
        "analysis_period_start",
        "analysis_period_end",
        "snapshot_ref",
        "snapshot_status",
        "ranking_policy",
    )
    if any(
        brief_reaction.get(field) != atlas_reaction.get(field)
        for field in common_fields
    ):
        return ["reaction receipts differ in cross-surface common identity"]
    common_count_fields = (
        "personal_reaction_events_detected",
        "unique_reacted_posts",
        "posts_resolved",
        "eligible_period_posts",
        "unique_atoms_linked",
        "unique_canonical_threads_linked",
        "canonical_threads_boosted",
        "unique_compatibility_threads_linked",
        "compatibility_threads_boosted",
    )
    brief_counts = _mapping(brief_reaction.get("counts"))
    atlas_counts = _mapping(atlas_reaction.get("counts"))
    if any(
        brief_counts.get(field) != atlas_counts.get(field)
        for field in common_count_fields
    ):
        return ["reaction receipts differ in cross-surface common funnel"]

    def shared_audit(value: Mapping[str, object]) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for item in _mapping_list(value.get("eligible_thread_audit")):
            compatibility_ref = str(item.get("compatibility_thread_ref") or "")
            if compatibility_ref:
                result[compatibility_ref] = {
                    key: copy.deepcopy(field_value)
                    for key, field_value in item.items()
                    if key not in {"selected", "counterfactual_effect"}
                }
        return result

    if shared_audit(brief_reaction) != shared_audit(atlas_reaction):
        return ["reaction receipts differ in cross-surface attribution"]
    return []


def _reaction_effect_for_candidate(
    receipt: Mapping[str, object],
    source_thread_refs: object,
) -> dict[str, object]:
    refs = (
        [
            "thread:" + value.split(":", maxsplit=1)[1]
            for value in source_thread_refs
            if isinstance(value, str) and value.startswith("idea_thread:")
        ]
        if isinstance(source_thread_refs, list)
        else []
    )
    priority = {"none": 0, "linked_only": 1, "rank_changed": 2, "selection_changed": 3}
    items_by_ref: dict[str, Mapping[str, object]] = {}
    for field in ("influenced_items", "linked_only_items"):
        for item in _mapping_list(receipt.get(field)):
            surface_ref = str(item.get("surface_item_ref") or "")
            if surface_ref in refs and surface_ref not in items_by_ref:
                items_by_ref[surface_ref] = item
    selected: Mapping[str, object] | None = None
    for surface_ref in refs:
        item = items_by_ref.get(surface_ref)
        if item is None:
            continue
        if selected is None or priority.get(str(item.get("effect") or "none"), 0) > priority.get(
            str(selected.get("effect") or "none"),
            0,
        ):
            selected = item
    surface_ref = (
        str(selected.get("surface_item_ref"))
        if selected is not None
        else refs[0]
        if refs
        else ""
    )
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


def _reader_thread(
    source: Mapping[str, object],
    *,
    audit_links: Mapping[str, str],
    reaction: Mapping[str, object],
    feedback: Mapping[str, object],
    feedback_permissions: Mapping[str, object],
    feedback_status: str,
    evidence_basis: Mapping[str, object],
    fallback_evidence_refs: Sequence[str],
) -> dict[str, object]:
    canonical_id = _required_text(source.get("canonical_thread_id"), "canonical_thread_id")
    slug = _required_text(source.get("stable_slug"), f"{canonical_id}.stable_slug")
    if not _SAFE_SLUG_RE.fullmatch(slug):
        raise KnowledgeAtlasV2ValidationError([f"{canonical_id} stable_slug is invalid"])
    title = _required_text(
        source.get("title_ru") or source.get("title"), f"{canonical_id}.title_ru"
    )
    thesis = _required_text(
        source.get("thesis") or source.get("summary"), f"{canonical_id}.thesis"
    )
    evidence_refs = _unique_text(
        [
            *[
                ref
                for ref in _strings(evidence_basis.get("evidence_refs"))
                if _safe_reference(ref)
            ],
            *_source_urls(source),
            *[
                ref
                for ref in _unique_text(fallback_evidence_refs)
                if _safe_reference(ref)
            ],
        ]
    )[:20]
    if not evidence_refs:
        raise KnowledgeAtlasV2ValidationError(
            [f"{canonical_id} has no resolvable evidence refs"]
        )
    independent = _nonnegative_int(
        evidence_basis.get("independent_source_count"),
        default=0,
    )
    external = _nonnegative_int(
        evidence_basis.get("external_source_count"),
        default=0,
    )
    decision_grade = _nonnegative_int(
        evidence_basis.get("decision_grade_evidence_count"),
        default=0,
    )
    summary = source.get("evidence_summary")
    if summary is not None:
        summary_value = _json_copy(_mapping(summary), f"{canonical_id}.evidence_summary")
        _exact(
            summary_value,
            {
                "independent_source_count",
                "external_source_count",
                "decision_grade_evidence_count",
                "evidence_refs",
            },
            f"{canonical_id}.evidence_summary",
        )
        expected_summary = {
            "independent_source_count": independent,
            "external_source_count": external,
            "decision_grade_evidence_count": decision_grade,
            "evidence_refs": _strings(evidence_basis.get("evidence_refs")),
        }
        if summary_value != expected_summary:
            raise KnowledgeAtlasV2ValidationError(
                [f"{canonical_id} evidence_summary differs from source authority"]
            )
    declared_maturity = str(source.get("evidence_maturity") or "unknown")
    maturity = _authoritative_maturity(
        declared_maturity,
        independent_source_count=independent,
        external_source_count=external,
        decision_grade_evidence_count=decision_grade,
        mention_count=_nonnegative_int(evidence_basis.get("mention_count"), default=0),
        has_primary_source=evidence_basis.get("has_primary_source") is True,
        source_classification_status=str(
            evidence_basis.get("classification_status") or "unavailable"
        ),
        authoritative_evidence_ref_count=len(
            set(_strings(evidence_basis.get("evidence_refs")))
        ),
    )
    lifecycle = str(source.get("status") or "active")
    if lifecycle not in _CANONICAL_LIFECYCLE_STATUSES:
        raise KnowledgeAtlasV2ValidationError(
            [f"{canonical_id} canonical lifecycle status is invalid"]
        )
    changed = bool(source.get("changed_this_week"))
    display_status = (
        "stale"
        if lifecycle == "stale"
        else "growing"
        if lifecycle == "active" and changed
        else "watch"
    )
    reaction_status = (
        "available" if reaction.get("snapshot_status") == "complete" else "unavailable"
    )
    current_reaction_count, current_reaction_refs = _reaction_for_thread(reaction, slug)
    if reaction_status == "unavailable":
        current_reaction_count = None
        current_reaction_refs = []
    historical_status = (
        "available" if source.get("operator_interest") is not None else "unavailable"
    )
    historical_score = (
        _finite_score(source.get("operator_interest"), default=0.0)
        if historical_status == "available"
        else None
    )
    feedback_count = (
        _feedback_count_for_thread(feedback, feedback_permissions, slug)
        if feedback_status != "unavailable"
        else None
    )
    thread_ref = f"canonical_thread:{slug}"
    audit_ref = audit_links.get(thread_ref) or (
        f"{AUDIT_EXPLORER_HTML_FILENAME}#atlas-thread-{_safe_fragment(slug)}"
    )
    lineage = {
        key: _strings(source.get(key))
        for key in ("merged_from", "merged_into", "split_from", "split_into")
    }
    first_seen = str(source.get("first_seen_at") or "") or None
    last_seen = str(source.get("last_seen_at") or "") or None
    last_change = _meaningful_change_timestamp(source)
    lifecycle_values = (first_seen, last_seen, last_change)
    lifecycle_observation_status = (
        "available"
        if all(lifecycle_values)
        else "unavailable"
        if not any(lifecycle_values)
        else "partial"
    )
    return {
        "canonical_thread_id": canonical_id,
        "stable_slug": slug,
        "title_ru": title,
        "thesis": thesis,
        "lifecycle_status": lifecycle,
        "lifecycle_observation_status": lifecycle_observation_status,
        "display_status": display_status,
        "first_seen_at": first_seen,
        "last_seen_at": last_seen,
        "last_meaningful_change": last_change,
        "evidence_count": _nonnegative_int(
            source.get("atom_count"), default=len(source.get("atom_ids") or evidence_refs)
        ),
        "evidence_refs": evidence_refs[:20],
        "evidence_maturity": maturity,
        "independent_source_count": independent,
        "external_source_count": external,
        "decision_grade_evidence_count": decision_grade,
        "operator_interest": {
            "current_reaction_status": reaction_status,
            "current_reaction_count": current_reaction_count,
            "current_reaction_evidence_refs": current_reaction_refs[:12],
            "historical_attention_status": historical_status,
            "historical_attention_score": historical_score,
            "confirmed_feedback_status": feedback_status,
            "confirmed_feedback_count": feedback_count,
            "learning_inference": "none",
        },
        "merge_split_summary": lineage,
        "audit_ref": audit_ref,
    }


def _normalized_relations(
    values: Sequence[Mapping[str, object]],
    *,
    known_ids: set[str],
    evidence_by_thread: Mapping[str, set[str]],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(values):
        relation = _json_copy(raw, f"validated_relations[{index}]")
        _exact(relation, _RELATION_FIELDS, f"validated_relations[{index}]")
        source = _required_text(relation.get("source_thread_id"), "relation source")
        target = _required_text(relation.get("target_thread_id"), "relation target")
        kind = str(relation.get("relation") or "")
        refs = _strings(relation.get("evidence_refs"))
        weight = _positive_int(relation.get("weight"), "relation weight")
        if source not in known_ids or target not in known_ids:
            raise KnowledgeAtlasV2ValidationError(["relation references unknown canonical thread"])
        if source == target:
            raise KnowledgeAtlasV2ValidationError(["self relation is forbidden"])
        if kind not in _GRAPH_RELATIONS:
            raise KnowledgeAtlasV2ValidationError([f"unsupported relation type: {kind}"])
        if not refs:
            raise KnowledgeAtlasV2ValidationError(["typed graph relation requires evidence refs"])
        if any(not _safe_reference(ref) for ref in refs):
            raise KnowledgeAtlasV2ValidationError(
                ["typed graph relation contains an unsafe evidence ref"]
            )
        endpoint_evidence = evidence_by_thread.get(source, set()).union(
            evidence_by_thread.get(target, set())
        )
        if not set(refs).issubset(endpoint_evidence):
            raise KnowledgeAtlasV2ValidationError(
                ["typed graph relation evidence is not bound to either endpoint"]
            )
        key = (source, target, kind)
        if key in seen:
            raise KnowledgeAtlasV2ValidationError(["duplicate typed graph relation"])
        seen.add(key)
        result.append(
            {
                "source_thread_id": source,
                "target_thread_id": target,
                "relation": kind,
                "weight": weight,
                "evidence_refs": refs[:20],
            }
        )
    return sorted(
        result,
        key=lambda item: (
            str(item["source_thread_id"]),
            str(item["target_thread_id"]),
            str(item["relation"]),
        ),
    )


def _meaningful_change_timestamp(source: Mapping[str, object]) -> str | None:
    explicit = _unique_text(
        source.get(field)
        for field in ("last_meaningful_change", "updated_at", "valid_from")
    )
    lineage = _unique_text(
        item.get("event_at") for item in _mapping_list(source.get("lineage"))
    )
    candidates: list[tuple[datetime, str]] = []
    for value in [*explicit, *lineage]:
        try:
            candidates.append((_parse_timestamp(value), value))
        except ValueError:
            raise KnowledgeAtlasV2ValidationError(
                ["canonical meaningful-change timestamp is invalid"]
            )
    return max(candidates)[1] if candidates else None


def _timeline_projection(
    *,
    reporting_week: str,
    threads: Sequence[Mapping[str, object]],
    source_threads: Mapping[str, Mapping[str, object]],
    observation_contract: Mapping[str, object],
) -> dict[str, object]:
    weeks = _twelve_weeks(reporting_week)
    known_ids = {str(thread["canonical_thread_id"]) for thread in threads}
    observations: dict[tuple[str, str], tuple[float | None, int | None]] = {}
    for index, raw in enumerate(_mapping_list(observation_contract.get("items"))):
        item = _json_copy(raw, f"historical_observations[{index}]")
        _exact(
            item,
            {"canonical_thread_id", "week", "momentum", "evidence_count"},
            f"historical_observations[{index}]",
        )
        thread_id = str(item.get("canonical_thread_id") or "")
        week = str(item.get("week") or "")
        if thread_id not in known_ids or week not in weeks:
            raise KnowledgeAtlasV2ValidationError(
                ["historical observation has unknown thread/week"]
            )
        key = (thread_id, week)
        if key in observations:
            raise KnowledgeAtlasV2ValidationError(["duplicate historical observation"])
        momentum = item.get("momentum")
        if momentum is not None:
            momentum = _finite_score(momentum, default=-1.0, maximum=None)
            if momentum < 0:
                raise KnowledgeAtlasV2ValidationError(["timeline momentum must be non-negative"])
        evidence = item.get("evidence_count")
        if evidence is not None:
            evidence = _nonnegative_int(evidence)
        observations[key] = (momentum, evidence)
    series: list[dict[str, object]] = []
    for thread in threads:
        thread_id = str(thread["canonical_thread_id"])
        source = source_threads[thread_id]
        events = _timeline_events(source, weeks)
        series.append(
            {
                "canonical_thread_id": thread_id,
                "title_ru": str(thread["title_ru"]),
                "momentum": [observations.get((thread_id, week), (None, None))[0] for week in weeks],
                "evidence_count": [observations.get((thread_id, week), (None, None))[1] for week in weeks],
                "events": events,
            }
        )
    all_observed = all(
        (str(thread["canonical_thread_id"]), week) in observations
        and all(
            value is not None
            for value in observations[(str(thread["canonical_thread_id"]), week)]
        )
        for thread in threads
        for week in weeks
    )
    source_status = str(observation_contract.get("status") or "unavailable")
    return {
        "weeks": weeks,
        "series": series,
        "source_status": source_status,
        "coverage_status": (
            "unavailable"
            if source_status == "unavailable"
            else "complete"
            if all_observed and source_status == "available"
            else "partial"
        ),
        "zero_semantics_ru": "Ноль означает наблюдаемое отсутствие импульса или новых доказательств.",
        "missing_semantics_ru": "Пустое значение означает, что исторический снимок недели недоступен.",
    }


def _timeline_events(source: Mapping[str, object], weeks: Sequence[str]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for raw in _mapping_list(source.get("lineage")):
        relation = str(raw.get("relation_type") or "")
        if relation not in {"merge", "split"}:
            continue
        week = _iso_week_for_timestamp(raw.get("event_at"))
        if week not in weeks:
            continue
        result.append(
            {
                "week": week,
                "type": relation,
                "label_ru": (
                    "Сохранено слияние канонической темы."
                    if relation == "merge"
                    else "Сохранено разделение канонической темы."
                ),
            }
        )
    return [dict(item) for item in _dedupe_objects(result)[:12]]


def _bound_thread_evidence_authority(
    threads: Sequence[Mapping[str, object]],
    *,
    v1_atlas: Mapping[str, object],
    editorial_input: Mapping[str, object],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    navigation_by_slug = {
        str(item.get("slug") or ""): item
        for item in _mapping_list(
            _mapping(v1_atlas.get("thread_navigation")).get("threads")
        )
    }
    candidate_refs_by_slug = {
        str(item.get("signal_id") or "").removeprefix("signal:"): set(
            _strings(item.get("evidence_refs"))
        )
        for item in _mapping_list(editorial_input.get("signal_candidates"))
    }
    decision_grade_refs = {
        str(item.get("evidence_ref") or item.get("id") or "")
        for item in _mapping_list(editorial_input.get("evidence_catalog"))
        if item.get("decision_grade") is True
    }
    allowed: dict[str, set[str]] = {}
    decision: dict[str, set[str]] = {}
    for thread in threads:
        thread_id = str(thread.get("canonical_thread_id") or "")
        slug = str(thread.get("stable_slug") or "")
        navigation = navigation_by_slug.get(slug, {})
        raw_refs: list[str] = [
            *_strings(thread.get("evidence_refs")),
            *_source_urls(thread),
            *[
                ref
                for ref in _strings(thread.get("source_refs"))
                if not _safe_http_url(ref)
            ],
            *_strings(navigation.get("source_urls")),
            *candidate_refs_by_slug.get(slug, set()),
        ]
        for atom_id in [
            *_strings(thread.get("atom_ids")),
            *[
                atom
                for evidence_item in _mapping_list(navigation.get("evidence_items"))
                for atom in _strings(evidence_item.get("atom_ids"))
            ],
        ]:
            raw_refs.append(
                atom_id if atom_id.startswith("atom:") else f"atom:{atom_id}"
            )
        raw_refs.extend(
            ref
            for evidence_item in _mapping_list(navigation.get("evidence_items"))
            for ref in [
                *_strings(evidence_item.get("source_urls")),
                *_strings(evidence_item.get("evidence_refs")),
            ]
        )
        bound = {ref for ref in raw_refs if _safe_reference(ref)}
        allowed[thread_id] = bound
        decision[thread_id] = bound.intersection(decision_grade_refs)
    return allowed, decision


def _unavailable_source_contributions(
    manifest: Mapping[str, object],
) -> dict[str, object]:
    period = _period_from_manifest(manifest)
    return {
        "schema_version": ATLAS_V2_SOURCE_CONTRIBUTIONS_SCHEMA_VERSION,
        "run_id": str(manifest.get("run_id") or ""),
        "reporting_period": period,
        "as_of": period["analysis_period_end"],
        "classification_status": "unavailable",
        "sources": [],
        "contributions": [],
        "limitation_ru": (
            "Классификация независимости источников не передана; ссылки сохранены, "
            "но не считаются независимыми подтверждениями."
        ),
    }


def _validate_source_contributions(
    raw: Mapping[str, object],
    *,
    manifest: Mapping[str, object],
    known_thread_ids: set[str] | None,
    allowed_evidence_by_thread: Mapping[str, set[str]] | None = None,
    decision_grade_refs_by_thread: Mapping[str, set[str]] | None = None,
) -> dict[str, object]:
    value = _json_copy(raw, "source_contributions")
    errors: list[str] = []
    _collect_exact(
        value,
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
        "source_contributions",
        errors,
    )
    period = _period_from_manifest(manifest)
    expected_identity = {
        "schema_version": ATLAS_V2_SOURCE_CONTRIBUTIONS_SCHEMA_VERSION,
        "run_id": manifest.get("run_id"),
        "reporting_period": period,
        "as_of": period["analysis_period_end"],
    }
    for field, expected in expected_identity.items():
        if value.get(field) != expected:
            errors.append(f"source_contributions {field} mismatch")
    status = str(value.get("classification_status") or "")
    if status not in {"complete", "partial", "unavailable"}:
        errors.append("source_contributions classification_status is invalid")
    limitation = str(value.get("limitation_ru") or "")
    if not _safe_reader_text(limitation, russian=True, maximum=600):
        errors.append("source_contributions limitation_ru is invalid")

    sources = _mapping_list_strict(
        value.get("sources"),
        "source_contributions.sources",
        errors,
        40,
    )
    sources_by_id: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(sources):
        path = f"source_contributions.sources[{index}]"
        _collect_exact(
            source,
            {
                "source_id",
                "label",
                "source_class",
                "independence_group",
                "classification_status",
            },
            path,
            errors,
        )
        source_id = str(source.get("source_id") or "")
        group = str(source.get("independence_group") or "")
        if not _SAFE_ID_RE.fullmatch(source_id):
            errors.append(f"{path}.source_id is invalid")
        if source_id in sources_by_id:
            errors.append(f"{path}.source_id is duplicated")
        if not _safe_reader_text(source.get("label"), maximum=220):
            errors.append(f"{path}.label is invalid")
        if source.get("source_class") not in _SOURCE_CLASSES:
            errors.append(f"{path}.source_class is invalid")
        if not _SAFE_ID_RE.fullmatch(group):
            errors.append(f"{path}.independence_group is invalid")
        if source.get("classification_status") not in {"available", "unavailable"}:
            errors.append(f"{path}.classification_status is invalid")
        sources_by_id[source_id] = source

    contributions = _mapping_list_strict(
        value.get("contributions"),
        "source_contributions.contributions",
        errors,
        800,
    )
    contribution_keys: set[tuple[str, str]] = set()
    independent_ref_groups: dict[tuple[str, str], set[str]] = {}
    decision_claimed_by_thread: Counter[str] = Counter()
    cited_decision_refs_by_thread: dict[str, set[str]] = {}
    for index, item in enumerate(contributions):
        path = f"source_contributions.contributions[{index}]"
        _collect_exact(
            item,
            {
                "source_id",
                "canonical_thread_id",
                "mention_count",
                "independent_support_count",
                "decision_grade_evidence_count",
                "evidence_refs",
            },
            path,
            errors,
        )
        source_id = str(item.get("source_id") or "")
        thread_id = str(item.get("canonical_thread_id") or "")
        mentions = _checked_nonnegative_int(
            item.get("mention_count"),
            f"{path}.mention_count",
            errors,
        )
        independent = _checked_nonnegative_int(
            item.get("independent_support_count"),
            f"{path}.independent_support_count",
            errors,
        )
        decision_grade = _checked_nonnegative_int(
            item.get("decision_grade_evidence_count"),
            f"{path}.decision_grade_evidence_count",
            errors,
        )
        refs = _bounded_strings(
            item.get("evidence_refs"),
            f"{path}.evidence_refs",
            errors,
            maximum=20,
        )
        if not _SAFE_ID_RE.fullmatch(thread_id):
            errors.append(f"{path}.canonical_thread_id is invalid")
        if known_thread_ids is not None and thread_id not in known_thread_ids:
            errors.append(f"{path}.canonical_thread_id is outside the primary set")
        source = sources_by_id.get(source_id)
        if source is None:
            errors.append(f"{path}.source_id is unknown")
        elif source.get("classification_status") != "available":
            errors.append(f"{path} uses an unavailable source classification")
        if independent > mentions or independent > 1:
            errors.append(f"{path}.independent_support_count overstates support")
        if mentions < 1:
            errors.append(f"{path}.mention_count must be positive for a contribution")
        if decision_grade > len(refs):
            errors.append(f"{path}.decision_grade_evidence_count exceeds evidence refs")
        if mentions == 0 and (independent or decision_grade or refs):
            errors.append(f"{path} zero mention has evidence authority")
        if mentions > 0 and not refs:
            errors.append(f"{path} nonzero mention requires evidence refs")
        if any(not _safe_reference(ref) for ref in refs):
            errors.append(f"{path}.evidence_refs contains an unsafe reference")
        if allowed_evidence_by_thread is not None and not set(refs).issubset(
            allowed_evidence_by_thread.get(thread_id, set())
        ):
            errors.append(f"{path}.evidence_refs are outside manifest-bound evidence")
        if decision_grade_refs_by_thread is not None and decision_grade > len(
            set(refs).intersection(
                decision_grade_refs_by_thread.get(thread_id, set())
            )
        ):
            errors.append(f"{path}.decision_grade_evidence_count lacks upstream authority")
        decision_claimed_by_thread[thread_id] += decision_grade
        if decision_grade_refs_by_thread is not None:
            cited_decision_refs_by_thread.setdefault(thread_id, set()).update(
                set(refs).intersection(
                    decision_grade_refs_by_thread.get(thread_id, set())
                )
            )
        key = (source_id, thread_id)
        if key in contribution_keys:
            errors.append(f"{path} duplicates another source/thread contribution")
        contribution_keys.add(key)
        if independent and source is not None:
            group = str(source.get("independence_group") or "")
            for ref in refs:
                independent_ref_groups.setdefault((thread_id, ref), set()).add(group)

    if any(len(groups) > 1 for groups in independent_ref_groups.values()):
        errors.append(
            "one evidence ref cannot grant independent support to multiple source groups"
        )
    if decision_grade_refs_by_thread is not None and any(
        count > len(cited_decision_refs_by_thread.get(thread_id, set()))
        for thread_id, count in decision_claimed_by_thread.items()
    ):
        errors.append(
            "decision-grade contribution counts reuse upstream evidence authority"
        )

    if status == "unavailable" and (sources or contributions):
        errors.append("unavailable source classification must not contain sources/cells")
    if status == "complete" and (
        not sources
        or any(source.get("classification_status") != "available" for source in sources)
    ):
        errors.append("complete source classification requires available sources")
    if status == "partial" and not sources:
        errors.append("partial source classification requires bounded source metadata")
    if errors:
        raise KnowledgeAtlasV2ValidationError(_unique_text(errors))
    value["sources"] = sorted(sources, key=lambda item: str(item["source_id"]))
    normalized_contributions = []
    for item in contributions:
        normalized = dict(item)
        normalized["evidence_refs"] = sorted(_strings(item.get("evidence_refs")))
        normalized_contributions.append(normalized)
    value["contributions"] = sorted(
        normalized_contributions,
        key=lambda item: (
            str(item["source_id"]),
            str(item["canonical_thread_id"]),
        ),
    )
    return value


def _thread_evidence_basis(
    contract: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    sources = {
        str(item.get("source_id") or ""): item
        for item in _mapping_list(contract.get("sources"))
    }
    accumulated: dict[str, dict[str, Any]] = {}
    for item in _mapping_list(contract.get("contributions")):
        thread_id = str(item.get("canonical_thread_id") or "")
        source = sources[str(item.get("source_id") or "")]
        row = accumulated.setdefault(
            thread_id,
            {
                "groups": set(),
                "external_groups": set(),
                "mention_count": 0,
                "decision_grade_evidence_count": 0,
                "evidence_refs": [],
                "has_primary_source": False,
            },
        )
        mentions = int(item["mention_count"])
        independent = int(item["independent_support_count"])
        group = str(source["independence_group"])
        row["mention_count"] += mentions
        if independent:
            row["groups"].add(group)
            if source.get("source_class") == "external_analysis":
                row["external_groups"].add(group)
        if mentions and source.get("source_class") in {"primary", "vendor_primary"}:
            row["has_primary_source"] = True
        row["decision_grade_evidence_count"] += int(
            item["decision_grade_evidence_count"]
        )
        row["evidence_refs"] = _unique_text(
            [*row["evidence_refs"], *_strings(item.get("evidence_refs"))]
        )
    result: dict[str, dict[str, object]] = {}
    for thread_id, row in accumulated.items():
        result[thread_id] = {
            "classification_status": "available",
            "independent_source_count": len(row["groups"]),
            "external_source_count": len(row["external_groups"]),
            "decision_grade_evidence_count": row[
                "decision_grade_evidence_count"
            ],
            "mention_count": row["mention_count"],
            "evidence_refs": list(row["evidence_refs"]),
            "has_primary_source": row["has_primary_source"],
        }
    return result


def _authoritative_maturity(
    declared: str,
    *,
    independent_source_count: int,
    external_source_count: int,
    decision_grade_evidence_count: int,
    mention_count: int,
    has_primary_source: bool,
    source_classification_status: str,
    authoritative_evidence_ref_count: int,
) -> str:
    if declared not in _MATURITY_ORDER or source_classification_status != "available":
        return "unknown"
    supported = {
        "single_source": mention_count >= 1,
        "repeated_signal": mention_count >= 2,
        "multi_channel": (
            independent_source_count >= 2 and authoritative_evidence_ref_count >= 2
        ),
        "primary_verified": has_primary_source,
        "externally_corroborated": (
            independent_source_count >= 2 and external_source_count >= 1
            and authoritative_evidence_ref_count >= 2
        ),
        "decision_grade": (
            independent_source_count >= 2
            and external_source_count >= 1
            and decision_grade_evidence_count >= 1
            and authoritative_evidence_ref_count >= 2
        ),
    }
    return declared if supported[declared] else "unknown"


def _source_matrix(
    threads: Sequence[Mapping[str, object]],
    contract: Mapping[str, object],
) -> dict[str, object]:
    thread_rows = [
        {
            "canonical_thread_id": str(thread["canonical_thread_id"]),
            "title_ru": str(thread["title_ru"]),
        }
        for thread in threads
    ]
    known_ids = {str(thread["canonical_thread_id"]) for thread in threads}
    sources = [
        {
            "source_id": str(item["source_id"]),
            "label": str(item["label"]),
            "source_class": str(item["source_class"]),
            "independence_group": str(item["independence_group"]),
            "classification_status": str(item["classification_status"]),
        }
        for item in _mapping_list(contract.get("sources"))
    ]
    cells = [
        {
            "source_id": str(item["source_id"]),
            "canonical_thread_id": str(item["canonical_thread_id"]),
            "mention_count": int(item["mention_count"]),
            "independent_support_count": int(item["independent_support_count"]),
            "decision_grade_evidence_count": int(
                item["decision_grade_evidence_count"]
            ),
            "evidence_refs": list(item["evidence_refs"]),
        }
        for item in _mapping_list(contract.get("contributions"))
        if str(item.get("canonical_thread_id") or "") in known_ids
    ]
    return {
        "value": "independent_support_count",
        "classification_status": str(contract["classification_status"]),
        "sources": sources,
        "threads": thread_rows,
        "cells": cells,
        "semantics_ru": str(contract["limitation_ru"]),
    }


def _maturity_projection(threads: Sequence[Mapping[str, object]]) -> dict[str, object]:
    counts = Counter(str(thread.get("evidence_maturity") or "unknown") for thread in threads)
    return {
        "thread_count": len(threads),
        "levels": [
            {"key": key, "label_ru": _MATURITY_LABELS[key], "count": counts.get(key, 0)}
            for key in _MATURITY_WITH_UNKNOWN
        ],
        "authority_ru": (
            "Зрелость ограничена проверяемым числом групп источников; self-declared высокий уровень не повышает тему."
        ),
    }


def _operator_interest_projection(
    threads: Sequence[Mapping[str, object]],
    *,
    reaction: Mapping[str, object],
    feedback: Mapping[str, object],
    feedback_permissions: Mapping[str, object],
    feedback_status: str,
) -> dict[str, object]:
    current = []
    historical = []
    for thread in threads:
        interest = _mapping(thread.get("operator_interest"))
        if _nonnegative_int(interest.get("current_reaction_count"), default=0) > 0:
            current.append(
                {
                    "canonical_thread_id": str(thread["canonical_thread_id"]),
                    "event_count": int(interest["current_reaction_count"]),
                    "evidence_refs": _strings(interest.get("current_reaction_evidence_refs")),
                }
            )
        if _finite_score(
            interest.get("historical_attention_score"), default=0.0
        ) > 0:
            historical.append(
                {
                    "canonical_thread_id": str(thread["canonical_thread_id"]),
                    "score": float(interest["historical_attention_score"]),
                    "state": "decayed_registry_hint",
                }
            )
    confirmed = [
        {
            "feedback_ref": str(item.get("feedback_ref") or ""),
            "reader_summary_ru": str(item.get("reader_summary_ru") or ""),
        }
        for key in ("applied_changes", "unchanged", "requires_code_or_config")
        for item in _mapping_list(feedback.get(key))
        if str(item.get("feedback_ref") or "")
    ] if feedback_status != "unavailable" else []
    historical_statuses = {
        str(_mapping(thread.get("operator_interest")).get("historical_attention_status"))
        for thread in threads
    }
    historical_status = (
        "available"
        if historical_statuses == {"available"}
        else "unavailable"
        if historical_statuses == {"unavailable"}
        else "partial"
    )
    feedback_available = (
        _nonnegative_int(
            feedback_permissions.get("confirmed_events_available"), default=0
        )
        if feedback_status != "unavailable"
        else None
    )
    feedback_considered = (
        _nonnegative_int(
            feedback_permissions.get("confirmed_events_considered"), default=0
        )
        if feedback_status != "unavailable"
        else None
    )
    feedback_truncated = (
        feedback_permissions.get("truncated") is True
        if feedback_status != "unavailable"
        else None
    )
    return {
        "current_reactions_status": (
            "available"
            if reaction.get("snapshot_status") == "complete"
            else "unavailable"
        ),
        "historical_attention_status": historical_status,
        "confirmed_feedback_status": feedback_status,
        "confirmed_feedback_events_available": feedback_available,
        "confirmed_feedback_events_considered": feedback_considered,
        "confirmed_feedback_truncated": feedback_truncated,
        "current_reactions": current,
        "decayed_historical_attention": historical,
        "confirmed_feedback": confirmed,
        "semantics_ru": (
            "Реакция — слабый текущий интерес; подтверждённая обратная связь и историческое внимание показаны отдельно и не доказывают понимание."
        ),
    }


def _learning_projection(
    threads: Sequence[Mapping[str, object]],
    *,
    reaction: Mapping[str, object],
    event_contract: Mapping[str, object],
) -> dict[str, object]:
    observations: dict[str, tuple[int, str, list[str]]] = {}
    reaction_basis, reaction_refs = _reaction_learning_basis(
        reaction,
        threads,
    )
    reaction_thread_ids = set(reaction_basis)
    reaction_count = len(reaction_thread_ids)
    if reaction_count and reaction_refs:
        observations["marked"] = (reaction_count, "reaction", reaction_refs)
    known_ids = {str(thread["canonical_thread_id"]) for thread in threads}
    events_by_stage: dict[str, list[Mapping[str, object]]] = {
        key: [] for key in _LEARNING_KEYS
    }
    for item in _mapping_list(event_contract.get("items")):
        thread_id = str(item.get("canonical_thread_id") or "")
        stage = str(item.get("stage") or "")
        if thread_id not in known_ids or stage not in events_by_stage:
            raise KnowledgeAtlasV2ValidationError(
                ["learning event is outside the primary canonical population"]
            )
        events_by_stage[stage].append(item)
    for stage in _LEARNING_KEYS:
        items = events_by_stage[stage]
        if not items:
            continue
        refs = sorted(
            {
                ref
                for item in items
                for ref in _strings(item.get("evidence_refs"))
            }
        )
        kind = _LEARNING_CONFIRMATION[stage]
        if stage == "marked":
            event_thread_ids = {
                str(item.get("canonical_thread_id") or "") for item in items
            }
            if (
                not reaction_count
                or not event_thread_ids.issubset(reaction_thread_ids)
                or any(
                    not set(_strings(item.get("evidence_refs"))).intersection(
                        reaction_basis.get(
                            str(item.get("canonical_thread_id") or ""), set()
                        )
                    )
                    for item in items
                )
            ):
                raise KnowledgeAtlasV2ValidationError(
                    ["marked learning event is not bound to the Atlas reaction receipt"]
                )
            observations[stage] = (
                len(reaction_thread_ids.union(event_thread_ids)),
                kind,
                sorted(set(reaction_refs).union(refs))[:20],
            )
        else:
            observations[stage] = (len(items), kind, refs[:20])
    stages: list[dict[str, object]] = []
    prior: int | None = None
    for key in _LEARNING_KEYS:
        if key not in observations:
            stages.append(
                {
                    "key": key,
                    "label_ru": _LEARNING_LABELS[key],
                    "count": None,
                    "observation_status": "unknown",
                    "confirmation_kind": "none",
                    "evidence_refs": [],
                }
            )
            continue
        count, kind, refs = observations[key]
        if prior is not None and count > prior:
            raise KnowledgeAtlasV2ValidationError(
                ["learning progression confirmed counts must be non-increasing"]
            )
        prior = count
        stages.append(
            {
                "key": key,
                "label_ru": _LEARNING_LABELS[key],
                "count": count,
                "observation_status": "confirmed",
                "confirmation_kind": kind,
                "evidence_refs": refs[:20],
            }
        )
    contract_status = str(event_contract.get("status") or "unavailable")
    reaction_available = reaction.get("snapshot_status") == "complete"
    return {
        "status": (
            "available"
            if contract_status == "available" and reaction_available
            else "unavailable"
            if contract_status == "unavailable" and not reaction_available
            else "partial"
        ),
        "stages": stages,
        "scope_thread_count": len(threads),
        "semantics_ru": (
            "Каждый переход требует собственного подтверждения; реакция подтверждает только «Отмечено», а неизвестное остаётся неизвестным."
        ),
    }


def _reaction_learning_observation(
    reaction: Mapping[str, object],
    threads: Sequence[Mapping[str, object]],
) -> tuple[int, list[str]]:
    basis, refs = _reaction_learning_basis(reaction, threads)
    return (len(basis), refs) if basis and refs else (0, [])


def _reaction_learning_basis(
    reaction: Mapping[str, object],
    threads: Sequence[Mapping[str, object]],
) -> tuple[dict[str, set[str]], list[str]]:
    if reaction.get("snapshot_status") != "complete":
        return {}, []
    target_ids = {
        f"canonical_thread:{thread.get('stable_slug')}": str(
            thread.get("canonical_thread_id") or ""
        )
        for thread in threads
        if thread.get("stable_slug") and thread.get("canonical_thread_id")
    }
    targets = set(target_ids)
    audit_rows = [
        item
        for item in _mapping_list(reaction.get("eligible_thread_audit"))
        if item.get("canonical_thread_ref") in targets
    ]
    rows = audit_rows or [
        item
        for item in [
            *_mapping_list(reaction.get("influenced_items")),
            *_mapping_list(reaction.get("linked_only_items")),
        ]
        if item.get("canonical_thread_ref") in targets
    ]
    basis: dict[str, set[str]] = {}
    for item in rows:
        target = str(item.get("canonical_thread_ref") or "")
        if target not in target_ids or not (
            _strings(item.get("reacted_post_refs"))
            or _nonnegative_int(
                item.get("reacted_post_count")
                if item.get("reacted_post_count") is not None
                else item.get("reaction_event_count"),
                default=0,
            )
        ):
            continue
        item_refs = {
            ref
            for ref in [
                *_strings(item.get("evidence_refs")),
                *_strings(item.get("source_refs")),
                *_strings(item.get("reacted_post_refs")),
            ]
            if _safe_reference(ref)
        }
        if item_refs:
            basis.setdefault(target_ids[target], set()).update(item_refs)
    refs = sorted({ref for item_refs in basis.values() for ref in item_refs})
    return (basis, refs) if basis and refs else ({}, [])


def _study_backlog(threads: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    ranked = sorted(
        threads,
        key=lambda item: (
            0 if item["display_status"] in {"stale", "contradicted"} else 1,
            _MATURITY_WITH_UNKNOWN.index(str(item["evidence_maturity"])),
            str(item["title_ru"]).casefold(),
        ),
    )
    rows: list[dict[str, object]] = []
    normalized: list[set[str]] = []
    reasons_seen: set[str] = set()
    for thread in ranked:
        tokens = set(_normalize_text(thread["title_ru"]).split())
        if any(_jaccard(tokens, previous) >= 0.8 for previous in normalized if tokens | previous):
            continue
        normalized.append(tokens)
        status = str(thread["display_status"])
        maturity = str(thread["evidence_maturity"])
        reason = (
            "Тема устаревает и требует проверки актуальности по новому независимому источнику."
            if status == "stale"
            else "В теме есть противоречие; сначала нужно проверить границы утверждения."
            if status == "contradicted"
            else "Доказательная база пока ограничена одной группой источников."
            if maturity in {"single_source", "repeated_signal", "unknown"}
            else "Тема важна для накопленного знания, но следующий учебный переход не подтверждён."
        )
        reason_key = _normalize_text(reason)
        if reason_key in reasons_seen:
            continue
        reasons_seen.add(reason_key)
        rows.append(
            {
                "canonical_thread_id": str(thread["canonical_thread_id"]),
                "title_ru": str(thread["title_ru"]),
                "priority": "high" if status in {"stale", "contradicted"} else "medium",
                "reason_ru": reason,
                "next_step_ru": f"Проверить один новый первичный источник по теме «{thread['title_ru']}» и сохранить результат отдельно.",
                "evidence_refs": _strings(thread["evidence_refs"])[:4],
                "audit_ref": str(thread["audit_ref"]),
            }
        )
        if len(rows) >= MAX_STUDY_BACKLOG:
            break
    return rows


def _visual_specs(
    *,
    run_id: str,
    period: Mapping[str, str],
    threads: Sequence[Mapping[str, object]],
    relations: Sequence[Mapping[str, object]],
    timeline: Mapping[str, object],
    source_matrix: Mapping[str, object],
    maturity: Mapping[str, object],
    learning: Mapping[str, object],
) -> list[dict[str, object]]:
    common = {
        "run_id": run_id,
        "reporting_week": period["reporting_week"],
        "analysis_period_start": period["analysis_period_start"],
        "analysis_period_end": period["analysis_period_end"],
    }
    graph_threads = [
        thread for thread in threads if thread.get("evidence_maturity") != "unknown"
    ][:8]
    graph_ids = {str(thread["canonical_thread_id"]) for thread in graph_threads}
    graph = {
        "schema_version": "report_visual.knowledge_graph.v1",
        "component_id": "atlas-knowledge-graph",
        "title_ru": "Карта канонических тем",
        "summary_ru": (
            "Размер узла показывает объём доказательств, граница — их зрелость, а акцент — отдельный интерес оператора."
        ),
        **common,
        "data_status": "available" if graph_threads else "empty",
        "source_refs": ["artifact:knowledge-atlas-v2#canonical-threads"],
        "data_note_ru": (
            "Связи появляются только при явном типе и проверяемом evidence ref; общая компания или сущность не создаёт ребро. Reader-граф ограничен восемью темами, полный реестр сохранён ниже."
        ),
        "encoding": {
            "node_size": "evidence_volume",
            "node_border": "evidence_maturity",
            "node_accent": "operator_interest",
        },
        "audit_explorer_path": AUDIT_EXPLORER_HTML_FILENAME,
        "nodes": [
            {
                "canonical_thread_id": str(thread["canonical_thread_id"]),
                "title_ru": str(thread["title_ru"]),
                "status": str(thread["display_status"]),
                "evidence_volume": int(thread["evidence_count"]),
                "evidence_maturity": str(thread["evidence_maturity"]),
                "operator_interest_score": _thread_interest_score(thread),
                "display_priority": (MAX_PRIMARY_THREADS - index) * 10,
            }
            for index, thread in enumerate(graph_threads)
        ],
        "edges": [
            dict(item)
            for item in relations
            if item.get("source_thread_id") in graph_ids
            and item.get("target_thread_id") in graph_ids
        ],
    }
    timeline_series = [
        item
        for item in _mapping_list(timeline.get("series"))
        if any(value is not None for value in item.get("momentum", []))
        or any(value is not None for value in item.get("evidence_count", []))
    ][:3]
    timeline_source_status = str(timeline.get("source_status") or "unavailable")
    timeline_data_status = (
        "unavailable"
        if timeline_source_status == "unavailable"
        else "available"
        if timeline_series
        else "empty"
    )
    timeline_spec = {
        "schema_version": "report_visual.thread_timeline.v1",
        "component_id": "atlas-thread-timeline",
        "title_ru": "Двенадцать недель изменений",
        "summary_ru": (
            "Разрыв ряда означает недоступный снимок, а нулевая точка — наблюдаемое отсутствие импульса."
        ),
        **common,
        "data_status": timeline_data_status,
        "source_refs": (
            []
            if timeline_data_status == "unavailable"
            else ["artifact:knowledge-atlas-v2#timeline"]
        ),
        "data_note_ru": (
            str(timeline["missing_semantics_ru"])
            + " На первой странице показаны три темы с наблюдениями; полный ряд всех первичных тем сохранён в sidecar и исходном каталоге."
        ),
        "partial_reasons_ru": (
            [
                "До внедрения полной истории некоторые прошлые недельные снимки честно отмечены как недоступные."
            ]
            if timeline_data_status == "available"
            and timeline.get("coverage_status") == "partial"
            else []
        ),
        **(
            {
                "state_reason_ru": (
                    "Исторический контракт этого запуска недоступен; текущие данные не подставлены в прошлые недели."
                )
            }
            if timeline_data_status == "unavailable"
            else {}
        ),
        "weeks": list(timeline["weeks"]) if timeline_data_status == "available" else [],
        "series": copy.deepcopy(timeline_series) if timeline_data_status == "available" else [],
    }
    matrix_sources, matrix_threads, matrix_cells = _visual_source_matrix_subset(
        source_matrix
    )
    matrix_status = str(source_matrix.get("classification_status") or "unavailable")
    heatmap_status = (
        "unavailable"
        if matrix_status == "unavailable"
        else "available"
        if matrix_sources and matrix_cells
        else "empty"
    )
    heatmap_available = heatmap_status == "available"
    heatmap = {
        "schema_version": "report_visual.source_thread_heatmap.v1",
        "component_id": "atlas-source-heatmap",
        "title_ru": "Вклад источников в темы",
        "summary_ru": (
            "Матрица отделяет число упоминаний от консервативно посчитанной независимой поддержки."
        ),
        **common,
        "data_status": heatmap_status,
        "source_refs": (
            []
            if heatmap_status == "unavailable"
            else ["artifact:knowledge-atlas-v2#source-thread-matrix"]
        ),
        "data_note_ru": (
            str(source_matrix["semantics_ru"])
            + " Reader-матрица ограничена четырьмя темами и четырьмя группами; полная проекция остаётся в sidecar."
        ),
        **(
            {
                "state_reason_ru": (
                    "В запуске нет валидированного контракта классификации источников; URL не используются как эвристика независимости."
                )
            }
            if heatmap_status == "unavailable"
            else {}
        ),
        "value": str(source_matrix["value"]),
        "sources": copy.deepcopy(matrix_sources) if heatmap_available else [],
        "threads": copy.deepcopy(matrix_threads) if heatmap_available else [],
        "cells": copy.deepcopy(matrix_cells) if heatmap_available else [],
    }
    maturity_spec = {
        "schema_version": "report_visual.evidence_maturity.v1",
        "component_id": "atlas-evidence-maturity",
        "title_ru": "Зрелость доказательств",
        "summary_ru": (
            "Распределение показывает основание доверия по всем первичным каноническим темам."
        ),
        **common,
        "data_status": "available" if threads else "empty",
        "source_refs": ["artifact:knowledge-atlas-v2#evidence-maturity"],
        "data_note_ru": str(maturity["authority_ru"]),
        "levels": copy.deepcopy(maturity["levels"]),
        "thread_count": int(maturity["thread_count"]),
    }
    confirmed_learning = any(
        item.get("observation_status") == "confirmed"
        for item in _mapping_list(learning.get("stages"))
    )
    learning_status = str(learning.get("status") or "unavailable")
    learning_data_status = (
        "unavailable"
        if learning_status == "unavailable"
        else "available"
        if confirmed_learning
        else "empty"
    )
    learning_spec = {
        "schema_version": "report_visual.learning_progression.v1",
        "component_id": "atlas-learning-progression",
        "title_ru": "Подтверждённое обучение",
        "summary_ru": (
            "Стадии разделены: реакция отмечает интерес, но не доказывает чтение, понимание или внедрение."
        ),
        **common,
        "data_status": learning_data_status,
        "source_refs": (
            []
            if learning_data_status == "unavailable"
            else ["artifact:knowledge-atlas-v2#learning-progression"]
        ),
        "data_note_ru": str(learning["semantics_ru"]),
        "partial_reasons_ru": (
            ["Неподтверждённые стадии обучения сохранены как неизвестные, а не как нулевые."]
            if learning_data_status == "available"
            and any(
                item.get("observation_status") == "unknown"
                for item in _mapping_list(learning.get("stages"))
            )
            else []
        ),
        **(
            {
                "state_reason_ru": (
                    "Контракт подтверждённых событий обучения недоступен."
                )
            }
            if learning_data_status == "unavailable"
            else {}
        ),
        "stages": (
            copy.deepcopy(learning["stages"])
            if learning_data_status == "available"
            else []
        ),
    }
    specs = [graph, timeline_spec, heatmap, maturity_spec, learning_spec]
    for spec in specs:
        try:
            validate_report_visual(spec)
        except ReportVisualValidationError as exc:
            raise KnowledgeAtlasV2ValidationError(
                [f"visual {spec.get('component_id')} invalid: {exc}"]
            ) from exc
    return specs


def _visual_source_matrix_subset(
    source_matrix: Mapping[str, object],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    all_cells = _mapping_list(source_matrix.get("cells"))
    threads_with_cells = {
        str(item.get("canonical_thread_id") or "") for item in all_cells
    }
    thread_ids = _unique_text(
        str(item.get("canonical_thread_id") or "")
        for item in _mapping_list(source_matrix.get("threads"))
        if item.get("canonical_thread_id") in threads_with_cells
    )[:4]
    thread_id_set = set(thread_ids)
    candidate_cells = [
        item
        for item in all_cells
        if item.get("canonical_thread_id") in thread_id_set
    ]
    sources_with_cells = {
        str(item.get("source_id") or "") for item in candidate_cells
    }
    source_ids = _unique_text(
        str(item.get("source_id") or "")
        for item in _mapping_list(source_matrix.get("sources"))
        if item.get("source_id") in sources_with_cells
    )[:4]
    source_id_set = set(source_ids)
    sources = [
        {
            "source_id": str(item["source_id"]),
            "label": str(item["label"]),
            "independence_group": str(item["independence_group"]),
            "classification_status": str(item["classification_status"]),
        }
        for item in _mapping_list(source_matrix.get("sources"))
        if item.get("source_id") in source_id_set
    ]
    threads = [
        item
        for item in _mapping_list(source_matrix.get("threads"))
        if item.get("canonical_thread_id") in thread_id_set
    ]
    cells = [
        {
            "source_id": str(item["source_id"]),
            "canonical_thread_id": str(item["canonical_thread_id"]),
            "mention_count": int(item["mention_count"]),
            "independent_support_count": int(item["independent_support_count"]),
            "evidence_refs": list(item["evidence_refs"]),
        }
        for item in candidate_cells
        if item.get("source_id") in source_id_set
    ]
    return sources, threads, cells


def _thread_interest_score(thread: Mapping[str, object]) -> float:
    interest = _mapping(thread.get("operator_interest"))
    if _nonnegative_int(interest.get("confirmed_feedback_count"), default=0):
        return 1.0
    if _nonnegative_int(interest.get("current_reaction_count"), default=0):
        return 0.65
    return min(0.5, _finite_score(interest.get("historical_attention_score"), default=0.0))


def _meaningful_visual_count(specs: Sequence[Mapping[str, object]]) -> int:
    return len(
        {
            str(spec.get("schema_version") or "")
            for spec in specs
            if spec.get("data_status") in {"available", "empty"}
            and render_report_visual(spec).render_status != "failed"
        }
    )


def _validate_knowledge_atlas_v2(
    value: Mapping[str, object],
    *,
    manifest: Mapping[str, object] | None = None,
    verify_metrics: bool = True,
) -> None:
    errors: list[str] = []
    _collect_exact(value, _ROOT_FIELDS, "root", errors)
    expected_scalars = {
        "schema_version": ATLAS_V2_SCHEMA_VERSION,
        "surface": ATLAS_V2_SURFACE,
        "preview_profile": ATLAS_V2_PREVIEW_PROFILE,
        "renderer_version": ATLAS_V2_RENDERER_VERSION,
    }
    for field, expected in expected_scalars.items():
        if value.get(field) != expected:
            errors.append(f"{field} mismatch")
    run_id = str(value.get("run_id") or "")
    if not _RUN_ID_RE.fullmatch(run_id):
        errors.append("run_id is invalid")
    try:
        _parse_timestamp(value.get("generated_at"))
    except ValueError:
        errors.append("generated_at is invalid")
    if value.get("period_mode") not in {"completed_iso_week", "explicit_iso_week"}:
        errors.append("period_mode is invalid")
    period = _mapping(value.get("reporting_period"))
    _collect_exact(
        period,
        {"reporting_week", "analysis_period_start", "analysis_period_end"},
        "reporting_period",
        errors,
    )
    week = str(period.get("reporting_week") or "")
    if not _ISO_WEEK_RE.fullmatch(week):
        errors.append("reporting_period.reporting_week is invalid")
    period_datetimes: dict[str, datetime] = {}
    for field in ("analysis_period_start", "analysis_period_end"):
        try:
            period_datetimes[field] = _parse_timestamp(period.get(field))
        except ValueError:
            errors.append(f"reporting_period.{field} is invalid")
    if (
        len(period_datetimes) == 2
        and period_datetimes["analysis_period_start"]
        >= period_datetimes["analysis_period_end"]
    ):
        errors.append("reporting_period bounds are not increasing")
    if value.get("as_of") != period.get("analysis_period_end"):
        errors.append("as_of must equal analysis_period_end")
    if value.get("source_run_status") not in {"complete", "partial"}:
        errors.append("source_run_status is invalid")
    source_contract_statuses = _mapping(value.get("source_contract_statuses"))
    _collect_exact(
        source_contract_statuses,
        {"editorial", "relations", "history", "learning_events"},
        "source_contract_statuses",
        errors,
    )
    if source_contract_statuses.get("editorial") not in {"complete", "partial"}:
        errors.append("source_contract_statuses.editorial is invalid")
    for field in ("relations", "history", "learning_events"):
        if source_contract_statuses.get(field) not in {
            "available",
            "partial",
            "unavailable",
        }:
            errors.append(f"source_contract_statuses.{field} is invalid")
    partial = value.get("partial")
    if not isinstance(partial, bool):
        errors.append("partial must be boolean")
        partial = False
    reasons = _bounded_strings(
        value.get("partial_reasons_ru"),
        "partial_reasons_ru",
        errors,
        maximum=12,
    )
    if any(not _safe_reader_text(item, russian=True, maximum=600) for item in reasons):
        errors.append("partial_reasons_ru contains unsafe reader copy")
    expected_run_status = "partial" if partial else "complete"
    if value.get("run_status") != expected_run_status:
        errors.append("run_status/partial mismatch")
    if bool(reasons) != bool(partial):
        errors.append("partial_reasons_ru/partial mismatch")

    source_versions = _mapping(value.get("source_schema_versions"))
    expected_versions = {
        "manifest": MANIFEST_SCHEMA_VERSION,
        "compatibility_brief": "split_ai_report.v1",
        "compatibility_atlas": "split_ai_report.v1",
        "editorial": EDITORIAL_SCHEMA_VERSION,
        "editorial_input": EDITORIAL_INPUT_SCHEMA_VERSION,
        "reaction": REACTION_EFFECT_SCHEMA_VERSION,
        "report_visuals": REPORT_VISUALS_CONTRACT_VERSION,
        "audit_explorer": AUDIT_EXPLORER_SCHEMA_VERSION,
        "source_catalog": ATLAS_V2_SOURCE_CATALOG_SCHEMA_VERSION,
        "source_contributions": ATLAS_V2_SOURCE_CONTRIBUTIONS_SCHEMA_VERSION,
        "relations": ATLAS_V2_RELATIONS_SCHEMA_VERSION,
        "history": ATLAS_V2_HISTORY_SCHEMA_VERSION,
        "learning_events": ATLAS_V2_LEARNING_EVENTS_SCHEMA_VERSION,
    }
    if source_versions != expected_versions:
        errors.append("source_schema_versions mismatch")

    primary = _bounded_strings(
        value.get("primary_thread_ids"),
        "primary_thread_ids",
        errors,
        maximum=MAX_PRIMARY_THREADS,
    )
    if not MIN_PRIMARY_THREADS <= len(primary) <= MAX_PRIMARY_THREADS:
        errors.append("primary_thread_ids must contain 8–12 canonical IDs")
    threads = _mapping_list_strict(
        value.get("canonical_threads"), "canonical_threads", errors, MAX_PRIMARY_THREADS
    )
    if len(threads) != len(primary):
        errors.append("canonical_threads must exactly match primary_thread_ids population")
    thread_ids: list[str] = []
    titles: list[str] = []
    theses: list[str] = []
    for index, thread in enumerate(threads):
        path = f"canonical_threads[{index}]"
        _collect_exact(thread, _THREAD_FIELDS, path, errors)
        thread_id = _plain_text(thread.get("canonical_thread_id"))
        slug = _plain_text(thread.get("stable_slug"))
        title = _plain_text(thread.get("title_ru"))
        thesis = _plain_text(thread.get("thesis"))
        if not _SAFE_ID_RE.fullmatch(thread_id):
            errors.append(f"{path}.canonical_thread_id is invalid")
        if not _SAFE_SLUG_RE.fullmatch(slug):
            errors.append(f"{path}.stable_slug is invalid")
        if not _safe_reader_text(title, russian=True, maximum=260) or not _safe_reader_text(
            thesis,
            russian=True,
            maximum=700,
        ):
            errors.append(f"{path} title/thesis must be reader-facing Russian")
        lifecycle = str(thread.get("lifecycle_status") or "")
        if lifecycle not in _CANONICAL_LIFECYCLE_STATUSES:
            errors.append(f"{path}.lifecycle_status is invalid")
        if thread.get("display_status") not in _GRAPH_STATUSES:
            errors.append(f"{path}.display_status is invalid")
        lifecycle_observation_status = str(
            thread.get("lifecycle_observation_status") or ""
        )
        if lifecycle_observation_status not in {"available", "partial", "unavailable"}:
            errors.append(f"{path}.lifecycle_observation_status is invalid")
        thread_dates: dict[str, datetime] = {}
        lifecycle_fields = ("first_seen_at", "last_seen_at", "last_meaningful_change")
        present_lifecycle_fields = [
            field for field in lifecycle_fields if thread.get(field) is not None
        ]
        expected_lifecycle_observation_status = (
            "available"
            if len(present_lifecycle_fields) == len(lifecycle_fields)
            else "unavailable"
            if not present_lifecycle_fields
            else "partial"
        )
        if lifecycle_observation_status != expected_lifecycle_observation_status:
            errors.append(f"{path}.lifecycle_observation_status/data mismatch")
        for field in present_lifecycle_fields:
            try:
                thread_dates[field] = _parse_timestamp(thread.get(field))
            except ValueError:
                errors.append(f"{path}.{field} is invalid")
        if {
            "first_seen_at",
            "last_seen_at",
        }.issubset(thread_dates) and thread_dates["first_seen_at"] > thread_dates[
            "last_seen_at"
        ]:
            errors.append(f"{path} first_seen_at is after last_seen_at")
        if {
            "first_seen_at",
            "last_meaningful_change",
        }.issubset(thread_dates) and thread_dates[
            "last_meaningful_change"
        ] < thread_dates["first_seen_at"]:
            errors.append(f"{path} last_meaningful_change predates first_seen_at")
        if thread_dates:
            as_of = period_datetimes.get("analysis_period_end")
            if as_of is not None and any(item > as_of for item in thread_dates.values()):
                errors.append(f"{path} lifecycle timestamp is after as_of")
        maturity = str(thread.get("evidence_maturity") or "")
        if maturity not in _MATURITY_WITH_UNKNOWN:
            errors.append(f"{path}.evidence_maturity is invalid")
        evidence_refs = _bounded_strings(
            thread.get("evidence_refs"), f"{path}.evidence_refs", errors, maximum=20
        )
        if not evidence_refs:
            errors.append(f"{path}.evidence_refs must not be empty")
        for ref in evidence_refs:
            if not _safe_reference(ref):
                errors.append(f"{path}.evidence_refs contains an unsafe reference")
        evidence_count = _checked_nonnegative_int(
            thread.get("evidence_count"), f"{path}.evidence_count", errors
        )
        independent = _checked_nonnegative_int(
            thread.get("independent_source_count"),
            f"{path}.independent_source_count",
            errors,
        )
        external = _checked_nonnegative_int(
            thread.get("external_source_count"),
            f"{path}.external_source_count",
            errors,
        )
        decision_grade = _checked_nonnegative_int(
            thread.get("decision_grade_evidence_count"),
            f"{path}.decision_grade_evidence_count",
            errors,
        )
        if evidence_count < len(evidence_refs):
            # Multiple refs per atom are legitimate; the count is not used as
            # authority for maturity, so this is intentionally not an error.
            pass
        if maturity in {"externally_corroborated", "decision_grade"} and (
            independent < 2 or len(evidence_refs) < 2 or external < 1
        ):
            errors.append(f"{path} high maturity lacks authoritative source basis")
        if maturity == "decision_grade" and decision_grade < 1:
            errors.append(f"{path} decision-grade maturity lacks decision evidence")
        interest = _mapping(thread.get("operator_interest"))
        _collect_exact(
            interest,
            {
                "current_reaction_status",
                "current_reaction_count",
                "current_reaction_evidence_refs",
                "historical_attention_status",
                "historical_attention_score",
                "confirmed_feedback_status",
                "confirmed_feedback_count",
                "learning_inference",
            },
            f"{path}.operator_interest",
            errors,
        )
        reaction_status = str(interest.get("current_reaction_status") or "")
        if reaction_status not in {"available", "unavailable"}:
            errors.append(f"{path}.operator_interest.current_reaction_status is invalid")
        reaction_count = interest.get("current_reaction_count")
        if reaction_status == "available":
            _checked_nonnegative_int(
                reaction_count,
                f"{path}.operator_interest.current_reaction_count",
                errors,
            )
        elif reaction_count is not None:
            errors.append(f"{path} unavailable reactions require count=null")
        reaction_refs = _bounded_strings(
            interest.get("current_reaction_evidence_refs"),
            f"{path}.operator_interest.current_reaction_evidence_refs",
            errors,
            maximum=12,
        )
        if _nonnegative_int(reaction_count, default=0) and not reaction_refs:
            errors.append(f"{path} current reactions require evidence refs")
        if not _nonnegative_int(reaction_count, default=0) and reaction_refs:
            errors.append(f"{path} zero current reactions cannot retain reaction refs")
        if any(not _safe_reference(ref) for ref in reaction_refs):
            errors.append(f"{path} contains unsafe reaction evidence refs")
        score = interest.get("historical_attention_score")
        historical_status = str(interest.get("historical_attention_status") or "")
        if historical_status not in {"available", "unavailable"}:
            errors.append(f"{path}.operator_interest.historical_attention_status is invalid")
        if historical_status == "unavailable" and score is not None:
            errors.append(f"{path} unavailable historical attention requires score=null")
        elif historical_status == "available" and (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
            or not 0 <= float(score) <= 1
        ):
            errors.append(f"{path}.operator_interest.historical_attention_score is invalid")
        feedback_status = str(interest.get("confirmed_feedback_status") or "")
        feedback_count = interest.get("confirmed_feedback_count")
        if feedback_status not in {"available", "partial", "unavailable"}:
            errors.append(f"{path}.operator_interest.confirmed_feedback_status is invalid")
        if feedback_status == "unavailable":
            if feedback_count is not None:
                errors.append(f"{path} unavailable feedback requires count=null")
        else:
            _checked_nonnegative_int(
                feedback_count,
                f"{path}.operator_interest.confirmed_feedback_count",
                errors,
            )
        if interest.get("learning_inference") != "none":
            errors.append(f"{path}.operator_interest cannot infer learning")
        lineage = _mapping(thread.get("merge_split_summary"))
        _collect_exact(
            lineage,
            {"merged_from", "merged_into", "split_from", "split_into"},
            f"{path}.merge_split_summary",
            errors,
        )
        for key in ("merged_from", "merged_into", "split_from", "split_into"):
            lineage_refs = _bounded_strings(
                lineage.get(key),
                f"{path}.merge_split_summary.{key}",
                errors,
                maximum=40,
            )
            if any(not _safe_reference(ref) or ref == thread_id for ref in lineage_refs):
                errors.append(f"{path}.merge_split_summary.{key} is invalid")
        audit_ref = str(thread.get("audit_ref") or "")
        if not re.fullmatch(
            rf"{re.escape(AUDIT_EXPLORER_HTML_FILENAME)}#[A-Za-z0-9][A-Za-z0-9._:-]{{0,199}}",
            audit_ref,
        ):
            errors.append(f"{path}.audit_ref is not a package-local Audit deep link")
        thread_ids.append(thread_id)
        titles.append(title)
        theses.append(thesis)
    if thread_ids != primary:
        errors.append("canonical_threads order/identity differs from primary_thread_ids")
    if len(thread_ids) != len(set(thread_ids)):
        errors.append("canonical_thread_id values are duplicated")
    _reject_duplicate_reader_text(titles, "canonical title", errors)
    _reject_duplicate_reader_text(theses, "canonical thesis", errors)

    relations = _mapping_list_strict(
        value.get("thread_relations"), "thread_relations", errors, 100
    )
    thread_evidence_by_id = {
        str(item.get("canonical_thread_id") or ""): set(
            _strings(item.get("evidence_refs"))
        )
        for item in threads
    }
    relation_keys: set[tuple[str, str, str]] = set()
    for index, relation in enumerate(relations):
        path = f"thread_relations[{index}]"
        _collect_exact(relation, _RELATION_FIELDS, path, errors)
        source = str(relation.get("source_thread_id") or "")
        target = str(relation.get("target_thread_id") or "")
        kind = str(relation.get("relation") or "")
        refs = _bounded_strings(
            relation.get("evidence_refs"), f"{path}.evidence_refs", errors, maximum=20
        )
        if source not in thread_ids or target not in thread_ids or source == target:
            errors.append(f"{path} has invalid endpoints")
        if kind not in _GRAPH_RELATIONS:
            errors.append(f"{path}.relation is invalid")
        _checked_positive_int(relation.get("weight"), f"{path}.weight", errors)
        if not refs:
            errors.append(f"{path} requires typed evidence-backed refs")
        if any(not _safe_reference(ref) for ref in refs):
            errors.append(f"{path}.evidence_refs contains an unsafe reference")
        endpoint_evidence = thread_evidence_by_id.get(source, set()).union(
            thread_evidence_by_id.get(target, set())
        )
        if refs and not set(refs).issubset(endpoint_evidence):
            errors.append(f"{path}.evidence_refs are not bound to relation endpoints")
        key = (source, target, kind)
        if key in relation_keys:
            errors.append(f"{path} duplicates another relation")
        relation_keys.add(key)

    contradicted_ids = {
        str(item.get("target_thread_id") or "")
        for item in relations
        if item.get("relation") == "contradicts"
    }
    for index, thread in enumerate(threads):
        thread_id = str(thread.get("canonical_thread_id") or "")
        lifecycle = str(thread.get("lifecycle_status") or "")
        display = str(thread.get("display_status") or "")
        if thread_id in contradicted_ids:
            if display != "contradicted":
                errors.append(
                    f"canonical_threads[{index}] contradiction/display status mismatch"
                )
        elif display == "contradicted":
            errors.append(
                f"canonical_threads[{index}] contradiction lacks a typed evidence-backed edge"
            )
        elif lifecycle == "stale" and display != "stale":
            errors.append(f"canonical_threads[{index}] stale lifecycle/display mismatch")
        elif lifecycle in {"merged", "split", "resolved", "archived"} and display != "watch":
            errors.append(
                f"canonical_threads[{index}] terminal lifecycle/display mismatch"
            )

    _validate_timeline(value.get("timeline"), threads, week, errors)
    _validate_source_matrix(value.get("source_thread_matrix"), threads, errors)
    _validate_maturity(value.get("evidence_maturity"), threads, errors)
    _validate_interest(value.get("operator_interest"), threads, errors)
    _validate_learning(value.get("learning_progression"), len(threads), errors)
    _validate_backlog(value.get("study_backlog"), primary, errors)
    if source_contract_statuses.get("relations") == "unavailable" and relations:
        errors.append("unavailable relations contract cannot expose relations")
    timeline_value = _mapping(value.get("timeline"))
    if timeline_value.get("source_status") != source_contract_statuses.get("history"):
        errors.append("timeline source status differs from history contract")
    interest_value = _mapping(value.get("operator_interest"))
    learning_value = _mapping(value.get("learning_progression"))
    learning_contract_status = source_contract_statuses.get("learning_events")
    reaction_available = interest_value.get("current_reactions_status") == "available"
    expected_learning_status = (
        "available"
        if learning_contract_status == "available" and reaction_available
        else "unavailable"
        if learning_contract_status == "unavailable" and not reaction_available
        else "partial"
    )
    if learning_value.get("status") != expected_learning_status:
        errors.append("learning progression status differs from bound sources")
    expected_partial_reasons: list[str] = []
    if value.get("source_run_status") == "partial":
        expected_partial_reasons.append(
            "Исходный недельный запуск завершён частично; ограничения сохранены без подстановки соседних данных."
        )
    if interest_value.get("current_reactions_status") != "available":
        expected_partial_reasons.append(
            "Снимок личных реакций недоступен; отсутствие внимания не интерпретируется как отрицательный сигнал."
        )
    if source_contract_statuses.get("editorial") == "partial":
        expected_partial_reasons.append(
            "Редакционный контракт завершён частично; неполные сигналы не повышены до полного выпуска."
        )
    if interest_value.get("confirmed_feedback_status") != "available":
        expected_partial_reasons.append(
            "Доступность подтверждённой обратной связи ограничена; неизвестное не заменено нулём."
        )
    if interest_value.get("historical_attention_status") != "available":
        expected_partial_reasons.append(
            "Историческое внимание доступно не для всех тем; оно показано отдельно от текущих реакций."
        )
    if source_contract_statuses.get("relations") != "available":
        expected_partial_reasons.append(
            "Контракт типизированных связей недоступен или неполон; сходство сущностей не использовано вместо доказательств."
        )
    if timeline_value.get("coverage_status") != "complete":
        expected_partial_reasons.append(
            "История за двенадцать недель неполна; нули сохранены отдельно от отсутствующих наблюдений."
        )
    if source_contract_statuses.get("learning_events") != "available":
        expected_partial_reasons.append(
            "Контракт событий обучения недоступен или неполон; неподтверждённые переходы оставлены неизвестными."
        )
    matrix_value = _mapping(value.get("source_thread_matrix"))
    if matrix_value.get("classification_status") != "complete":
        expected_partial_reasons.append(str(matrix_value.get("semantics_ru") or ""))
    if any(
        item.get("lifecycle_observation_status") != "available" for item in threads
    ):
        expected_partial_reasons.append(
            "Для части канонических тем даты жизненного цикла недоступны; неизвестные значения не заменены датой запуска."
        )
    if reasons != _unique_text(expected_partial_reasons):
        errors.append("partial_reasons_ru differs from deterministic source limitations")

    specs = _mapping_list_strict(value.get("visual_specs"), "visual_specs", errors, 5)
    expected_schemas = [
        "report_visual.knowledge_graph.v1",
        "report_visual.thread_timeline.v1",
        "report_visual.source_thread_heatmap.v1",
        "report_visual.evidence_maturity.v1",
        "report_visual.learning_progression.v1",
    ]
    expected_component_ids = [
        "atlas-knowledge-graph",
        "atlas-thread-timeline",
        "atlas-source-heatmap",
        "atlas-evidence-maturity",
        "atlas-learning-progression",
    ]
    if [str(spec.get("schema_version") or "") for spec in specs] != expected_schemas:
        errors.append("visual_specs schema/order mismatch")
    if [str(spec.get("component_id") or "") for spec in specs] != expected_component_ids:
        errors.append("visual_specs component identity/order mismatch")
    for index, spec in enumerate(specs):
        try:
            validate_report_visual(spec)
        except (ReportVisualValidationError, TypeError, ValueError) as exc:
            errors.append(f"visual_specs[{index}] invalid: {exc}")
        for field, expected in {
            "run_id": run_id,
            "reporting_week": week,
            "analysis_period_start": period.get("analysis_period_start"),
            "analysis_period_end": period.get("analysis_period_end"),
        }.items():
            if spec.get(field) != expected:
                errors.append(f"visual_specs[{index}].{field} mismatch")
    if len(specs) == 5:
        expected_visual_source_refs = [
            ["artifact:knowledge-atlas-v2#canonical-threads"],
            (
                []
                if specs[1].get("data_status") == "unavailable"
                else ["artifact:knowledge-atlas-v2#timeline"]
            ),
            (
                []
                if specs[2].get("data_status") == "unavailable"
                else ["artifact:knowledge-atlas-v2#source-thread-matrix"]
            ),
            ["artifact:knowledge-atlas-v2#evidence-maturity"],
            (
                []
                if specs[4].get("data_status") == "unavailable"
                else ["artifact:knowledge-atlas-v2#learning-progression"]
            ),
        ]
        for index, expected_refs in enumerate(expected_visual_source_refs):
            if specs[index].get("source_refs") != expected_refs:
                errors.append(f"visual_specs[{index}].source_refs mismatch")
    if len(specs) == 5:
        graph = specs[0]
        graph_threads = [
            thread
            for thread in threads
            if thread.get("evidence_maturity") != "unknown"
        ][:8]
        graph_ids = {
            str(thread["canonical_thread_id"]) for thread in graph_threads
        }
        if _mapping_list(graph.get("nodes")) != [
            {
                "canonical_thread_id": str(thread["canonical_thread_id"]),
                "title_ru": str(thread["title_ru"]),
                "status": str(thread["display_status"]),
                "evidence_volume": int(thread["evidence_count"]),
                "evidence_maturity": str(thread["evidence_maturity"]),
                "operator_interest_score": _thread_interest_score(thread),
                "display_priority": (MAX_PRIMARY_THREADS - index) * 10,
            }
            for index, thread in enumerate(graph_threads)
        ]:
            errors.append("knowledge graph nodes differ from canonical_threads")
        expected_graph_edges = [
            relation
            for relation in relations
            if relation.get("source_thread_id") in graph_ids
            and relation.get("target_thread_id") in graph_ids
        ]
        if _mapping_list(graph.get("edges")) != expected_graph_edges:
            errors.append("knowledge graph edges differ from thread_relations")
        timeline = _mapping(value.get("timeline"))
        expected_timeline_series = [
            item
            for item in _mapping_list(timeline.get("series"))
            if any(value is not None for value in item.get("momentum", []))
            or any(value is not None for value in item.get("evidence_count", []))
        ][:3]
        expected_timeline_weeks = (
            timeline.get("weeks") if specs[1].get("data_status") == "available" else []
        )
        if specs[1].get("weeks") != expected_timeline_weeks or specs[1].get(
            "series"
        ) != (
            expected_timeline_series
            if specs[1].get("data_status") == "available"
            else []
        ):
            errors.append("timeline visual differs from timeline projection")
        matrix = _mapping(value.get("source_thread_matrix"))
        matrix_sources, matrix_threads, matrix_cells = _visual_source_matrix_subset(
            matrix
        )
        expected_matrix = {
            "value": matrix.get("value"),
            "sources": matrix_sources,
            "threads": matrix_threads,
            "cells": matrix_cells,
        }
        for field, expected_matrix_value in expected_matrix.items():
            if specs[2].get("data_status") != "available" and field != "value":
                expected_matrix_value = []
            if specs[2].get(field) != expected_matrix_value:
                errors.append(f"heatmap visual differs from source_thread_matrix.{field}")
        maturity = _mapping(value.get("evidence_maturity"))
        if specs[3].get("levels") != maturity.get("levels") or specs[3].get(
            "thread_count"
        ) != maturity.get("thread_count"):
            errors.append("maturity visual differs from evidence_maturity")
        learning = _mapping(value.get("learning_progression"))
        expected_learning_stages = (
            learning.get("stages")
            if specs[4].get("data_status") == "available"
            else []
        )
        if specs[4].get("stages") != expected_learning_stages:
            errors.append("learning visual differs from learning_progression")

    technical = _mapping(value.get("technical_refs"))
    _collect_exact(
        technical,
        {
            "manifest_path",
            "audit_explorer_path",
            "audit_explorer_json_path",
            "compatibility_atlas_path",
            "compatibility_atlas_json_path",
        },
        "technical_refs",
        errors,
    )
    for field in technical:
        if not _safe_absolute_path_text(technical[field]):
            errors.append(f"technical_refs.{field} must be absolute")
    if len(technical.values()) != len(set(technical.values())):
        errors.append("technical_refs paths must be duplicate-free")
    artifacts = _mapping(value.get("source_artifacts"))
    if set(artifacts) != _SOURCE_ARTIFACT_KEYS:
        errors.append("source_artifacts keys mismatch")
    for name, descriptor in artifacts.items():
        _validate_source_descriptor(descriptor, f"source_artifacts.{name}", errors)
    source_paths = [
        str(_mapping(descriptor).get("path") or "")
        for descriptor in artifacts.values()
    ]
    if len(source_paths) != len(set(source_paths)):
        errors.append("source_artifacts paths must be duplicate-free")
    paths = _mapping(value.get("artifact_paths"))
    if set(paths) != _ARTIFACT_PATH_KEYS:
        errors.append("artifact_paths keys mismatch")
    for name, raw_path in paths.items():
        if not _safe_absolute_path_text(raw_path):
            errors.append(f"artifact_paths.{name} must be absolute")
    if len(paths.values()) != len(set(paths.values())):
        errors.append("artifact_paths must be duplicate-free")

    metrics = _mapping(value.get("content_metrics"))
    _collect_exact(
        metrics,
        {
            "visible_word_count",
            "hard_max",
            "word_budget_status",
            "visual_component_count",
            "meaningful_visual_count",
        },
        "content_metrics",
        errors,
    )
    _checked_nonnegative_int(metrics.get("visible_word_count"), "content_metrics.visible_word_count", errors)
    if metrics.get("hard_max") != HARD_VISIBLE_WORDS_MAX:
        errors.append("content_metrics.hard_max mismatch")
    if metrics.get("visual_component_count") != len(specs):
        errors.append("content_metrics.visual_component_count mismatch")
    try:
        meaningful = _meaningful_visual_count(specs)
    except Exception as exc:
        errors.append(f"content_metrics meaningful visual evaluation failed: {exc}")
        meaningful = -1
    if metrics.get("meaningful_visual_count") != meaningful:
        errors.append("content_metrics.meaningful_visual_count mismatch")
    if verify_metrics and not errors:
        measured = _reader_visible_word_count(_render_document(value))
        if metrics.get("visible_word_count") != measured:
            errors.append("content_metrics.visible_word_count mismatch")
        expected_budget = "within_budget" if measured <= HARD_VISIBLE_WORDS_MAX else "exceeded"
        if metrics.get("word_budget_status") != expected_budget:
            errors.append("content_metrics.word_budget_status mismatch")
        if measured > HARD_VISIBLE_WORDS_MAX:
            errors.append("initial visible Atlas copy exceeds 1,500 words")
    elif not verify_metrics and metrics.get("word_budget_status") != "pending":
        errors.append("initial content_metrics.word_budget_status must be pending")

    if manifest is not None:
        manifest_value = _mapping(manifest)
        expected_manifest = {
            "run_id": manifest_value.get("run_id"),
            "generated_at": manifest_value.get("generated_at"),
            "period_mode": manifest_value.get("period_mode"),
            "reporting_period": _period_from_manifest(manifest_value),
            "source_run_status": manifest_value.get("run_status"),
            "as_of": manifest_value.get("analysis_period_end"),
        }
        for field, expected in expected_manifest.items():
            if value.get(field) != expected:
                errors.append(f"manifest identity mismatch: {field}")
    if errors:
        raise KnowledgeAtlasV2ValidationError(_unique_text(errors))


def _validate_timeline(
    raw: object,
    threads: Sequence[Mapping[str, object]],
    reporting_week: str,
    errors: list[str],
) -> None:
    primary = [str(item.get("canonical_thread_id") or "") for item in threads]
    title_by_id = {
        str(item.get("canonical_thread_id") or ""): str(item.get("title_ru") or "")
        for item in threads
    }
    timeline = _mapping(raw)
    _collect_exact(
        timeline,
        {
            "weeks",
            "series",
            "source_status",
            "coverage_status",
            "zero_semantics_ru",
            "missing_semantics_ru",
        },
        "timeline",
        errors,
    )
    weeks = _bounded_strings(timeline.get("weeks"), "timeline.weeks", errors, maximum=12)
    try:
        expected_weeks = _twelve_weeks(reporting_week)
    except KnowledgeAtlasV2ValidationError as exc:
        errors.extend(exc.errors)
        expected_weeks = []
    if weeks != expected_weeks or len(weeks) != 12:
        errors.append("timeline.weeks must be the exact 12 consecutive weeks")
    source_status = str(timeline.get("source_status") or "")
    if source_status not in {"available", "partial", "unavailable"}:
        errors.append("timeline.source_status is invalid")
    if timeline.get("coverage_status") not in {"complete", "partial", "unavailable"}:
        errors.append("timeline.coverage_status is invalid")
    if timeline.get("zero_semantics_ru") != (
        "Ноль означает наблюдаемое отсутствие импульса или новых доказательств."
    ):
        errors.append("timeline.zero_semantics_ru mismatch")
    if timeline.get("missing_semantics_ru") != (
        "Пустое значение означает, что исторический снимок недели недоступен."
    ):
        errors.append("timeline.missing_semantics_ru mismatch")
    series = _mapping_list_strict(timeline.get("series"), "timeline.series", errors, MAX_PRIMARY_THREADS)
    if [str(item.get("canonical_thread_id") or "") for item in series] != list(primary):
        errors.append("timeline.series identities/order mismatch")
    any_missing = False
    for index, item in enumerate(series):
        path = f"timeline.series[{index}]"
        _collect_exact(
            item,
            {"canonical_thread_id", "title_ru", "momentum", "evidence_count", "events"},
            path,
            errors,
        )
        thread_id = str(item.get("canonical_thread_id") or "")
        if item.get("title_ru") != title_by_id.get(thread_id):
            errors.append(f"{path}.title_ru differs from canonical reader record")
        momentum = item.get("momentum")
        evidence = item.get("evidence_count")
        if not isinstance(momentum, list) or len(momentum) != 12:
            errors.append(f"{path}.momentum must contain 12 values")
            momentum = []
        if not isinstance(evidence, list) or len(evidence) != 12:
            errors.append(f"{path}.evidence_count must contain 12 values")
            evidence = []
        for position, number in enumerate(momentum):
            if number is None:
                any_missing = True
            elif isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(float(number)) or number < 0:
                errors.append(f"{path}.momentum[{position}] is invalid")
        for position, number in enumerate(evidence):
            if number is None:
                any_missing = True
            elif isinstance(number, bool) or not isinstance(number, int) or number < 0:
                errors.append(f"{path}.evidence_count[{position}] is invalid")
        events = _mapping_list_strict(item.get("events"), f"{path}.events", errors, 50)
        event_keys: set[tuple[str, str, str]] = set()
        for event in events:
            _collect_exact(event, {"week", "type", "label_ru"}, f"{path}.events[]", errors)
            key = (
                str(event.get("week") or ""),
                str(event.get("type") or ""),
                str(event.get("label_ru") or ""),
            )
            if (
                key[0] not in weeks
                or key[1] not in {"merge", "split", "milestone", "contradiction"}
                or not _safe_reader_text(key[2], russian=True, maximum=360)
            ):
                errors.append(f"{path} contains invalid timeline event")
            if key in event_keys:
                errors.append(f"{path} contains duplicate timeline event")
            event_keys.add(key)
    expected_coverage = (
        "unavailable"
        if source_status == "unavailable"
        else "partial"
        if any_missing or source_status == "partial"
        else "complete"
    )
    if timeline.get("coverage_status") != expected_coverage:
        errors.append("timeline.coverage_status does not match missing observations")


def _validate_source_matrix(
    raw: object,
    threads: Sequence[Mapping[str, object]],
    errors: list[str],
) -> None:
    primary = [str(item.get("canonical_thread_id") or "") for item in threads]
    matrix = _mapping(raw)
    _collect_exact(
        matrix,
        {
            "value",
            "classification_status",
            "sources",
            "threads",
            "cells",
            "semantics_ru",
        },
        "source_thread_matrix",
        errors,
    )
    if matrix.get("value") != "independent_support_count":
        errors.append("source_thread_matrix.value mismatch")
    status = str(matrix.get("classification_status") or "")
    if status not in {"complete", "partial", "unavailable"}:
        errors.append("source_thread_matrix.classification_status is invalid")
    if not _safe_reader_text(matrix.get("semantics_ru"), russian=True, maximum=600):
        errors.append("source_thread_matrix.semantics_ru is invalid")
    sources = _mapping_list_strict(matrix.get("sources"), "source_thread_matrix.sources", errors, 40)
    source_ids: list[str] = []
    sources_by_id: dict[str, Mapping[str, object]] = {}
    for index, source in enumerate(sources):
        path = f"source_thread_matrix.sources[{index}]"
        _collect_exact(
            source,
            {
                "source_id",
                "label",
                "source_class",
                "independence_group",
                "classification_status",
            },
            path,
            errors,
        )
        source_id = str(source.get("source_id") or "")
        source_ids.append(source_id)
        sources_by_id[source_id] = source
        if not _SAFE_ID_RE.fullmatch(source_id):
            errors.append(f"{path}.source_id is invalid")
        if not _safe_reader_text(source.get("label"), maximum=220):
            errors.append(f"{path}.label is invalid")
        if source.get("source_class") not in _SOURCE_CLASSES:
            errors.append(f"{path}.source_class is invalid")
        if not _SAFE_ID_RE.fullmatch(str(source.get("independence_group") or "")):
            errors.append(f"{path}.independence_group is invalid")
        if source.get("classification_status") not in {"available", "unavailable"}:
            errors.append(f"{path} classification invalid")
    if len(source_ids) != len(set(source_ids)):
        errors.append("source_thread_matrix source IDs are duplicated")
    thread_rows = _mapping_list_strict(matrix.get("threads"), "source_thread_matrix.threads", errors, MAX_PRIMARY_THREADS)
    if [str(item.get("canonical_thread_id") or "") for item in thread_rows] != list(primary):
        errors.append("source_thread_matrix thread identities/order mismatch")
    title_by_id = {
        str(item.get("canonical_thread_id") or ""): str(item.get("title_ru") or "")
        for item in threads
    }
    for index, item in enumerate(thread_rows):
        path = f"source_thread_matrix.threads[{index}]"
        _collect_exact(item, {"canonical_thread_id", "title_ru"}, path, errors)
        thread_id = str(item.get("canonical_thread_id") or "")
        if item.get("title_ru") != title_by_id.get(thread_id):
            errors.append(f"{path}.title_ru differs from canonical reader record")
    cells = _mapping_list_strict(matrix.get("cells"), "source_thread_matrix.cells", errors, 800)
    cell_keys: set[tuple[str, str]] = set()
    groups_by_thread: dict[str, set[str]] = {}
    external_by_thread: dict[str, set[str]] = {}
    mentions_by_thread: Counter[str] = Counter()
    decision_by_thread: Counter[str] = Counter()
    primary_source_threads: set[str] = set()
    refs_by_thread: dict[str, set[str]] = {}
    independent_ref_groups: dict[tuple[str, str], set[str]] = {}
    for index, cell in enumerate(cells):
        path = f"source_thread_matrix.cells[{index}]"
        _collect_exact(
            cell,
            {
                "source_id",
                "canonical_thread_id",
                "mention_count",
                "independent_support_count",
                "decision_grade_evidence_count",
                "evidence_refs",
            },
            path,
            errors,
        )
        source_id = str(cell.get("source_id") or "")
        thread_id = str(cell.get("canonical_thread_id") or "")
        mentions = _checked_nonnegative_int(cell.get("mention_count"), f"{path}.mention_count", errors)
        independent = _checked_nonnegative_int(
            cell.get("independent_support_count"), f"{path}.independent_support_count", errors
        )
        decision_grade = _checked_nonnegative_int(
            cell.get("decision_grade_evidence_count"),
            f"{path}.decision_grade_evidence_count",
            errors,
        )
        refs = _bounded_strings(cell.get("evidence_refs"), f"{path}.evidence_refs", errors, maximum=20)
        source = sources_by_id.get(source_id)
        if source is None or thread_id not in primary:
            errors.append(f"{path} references unknown source/thread")
        elif source.get("classification_status") != "available":
            errors.append(f"{path} uses unavailable source classification")
        if independent > mentions or independent > 1:
            errors.append(f"{path} overstates independent support")
        if mentions < 1:
            errors.append(f"{path}.mention_count must be positive for a contribution")
        if decision_grade > len(refs):
            errors.append(f"{path} overstates decision-grade evidence")
        if mentions and not refs:
            errors.append(f"{path} nonzero cell requires evidence refs")
        if not mentions and (independent or decision_grade or refs):
            errors.append(f"{path} zero cell has evidence authority")
        if any(not _safe_reference(ref) for ref in refs):
            errors.append(f"{path}.evidence_refs contains an unsafe reference")
        key = (source_id, thread_id)
        if key in cell_keys:
            errors.append(f"{path} duplicates another cell")
        cell_keys.add(key)
        if source is not None and thread_id in primary:
            mentions_by_thread[thread_id] += mentions
            decision_by_thread[thread_id] += decision_grade
            refs_by_thread.setdefault(thread_id, set()).update(refs)
            if mentions and source.get("source_class") in {"primary", "vendor_primary"}:
                primary_source_threads.add(thread_id)
            if independent:
                group = str(source.get("independence_group") or "")
                groups_by_thread.setdefault(thread_id, set()).add(group)
                for ref in refs:
                    independent_ref_groups.setdefault((thread_id, ref), set()).add(
                        group
                    )
                if source.get("source_class") == "external_analysis":
                    external_by_thread.setdefault(thread_id, set()).add(group)
    if any(len(groups) > 1 for groups in independent_ref_groups.values()):
        errors.append(
            "source_thread_matrix reuses one evidence ref across independent groups"
        )
    if any(
        decision_by_thread[thread_id] > len(refs_by_thread.get(thread_id, set()))
        for thread_id in decision_by_thread
    ):
        errors.append("source_thread_matrix decision counts reuse evidence refs")
    if status == "unavailable" and (sources or cells):
        errors.append("unavailable source_thread_matrix must not contain source authority")
    if status == "complete" and (
        not sources
        or any(source.get("classification_status") != "available" for source in sources)
    ):
        errors.append("complete source_thread_matrix requires available sources")
    if status == "partial" and not sources:
        errors.append("partial source_thread_matrix requires bounded source metadata")
    for index, thread in enumerate(threads):
        thread_id = str(thread.get("canonical_thread_id") or "")
        expected_counts = {
            "independent_source_count": len(groups_by_thread.get(thread_id, set())),
            "external_source_count": len(external_by_thread.get(thread_id, set())),
            "decision_grade_evidence_count": decision_by_thread[thread_id],
        }
        for field, expected in expected_counts.items():
            if thread.get(field) != expected:
                errors.append(
                    f"canonical_threads[{index}].{field} differs from source matrix authority"
                )
        if not refs_by_thread.get(thread_id, set()).issubset(
            set(_strings(thread.get("evidence_refs")))
        ):
            errors.append(
                f"canonical_threads[{index}].evidence_refs omit source matrix evidence"
            )
        maturity = str(thread.get("evidence_maturity") or "unknown")
        if maturity != "unknown" and _authoritative_maturity(
            maturity,
            independent_source_count=expected_counts["independent_source_count"],
            external_source_count=expected_counts["external_source_count"],
            decision_grade_evidence_count=expected_counts[
                "decision_grade_evidence_count"
            ],
            mention_count=mentions_by_thread[thread_id],
            has_primary_source=thread_id in primary_source_threads,
            source_classification_status=(
                "available" if thread_id in refs_by_thread else "unavailable"
            ),
            authoritative_evidence_ref_count=len(
                refs_by_thread.get(thread_id, set())
            ),
        ) != maturity:
            errors.append(
                f"canonical_threads[{index}].evidence_maturity lacks source authority"
            )


def _validate_maturity(
    raw: object,
    threads: Sequence[Mapping[str, object]],
    errors: list[str],
) -> None:
    maturity = _mapping(raw)
    _collect_exact(maturity, {"thread_count", "levels", "authority_ru"}, "evidence_maturity", errors)
    if maturity.get("thread_count") != len(threads):
        errors.append("evidence_maturity.thread_count mismatch")
    expected = Counter(str(thread.get("evidence_maturity") or "unknown") for thread in threads)
    levels = _mapping_list_strict(maturity.get("levels"), "evidence_maturity.levels", errors, 7)
    if len(levels) != 7:
        errors.append("evidence_maturity.levels must include six levels and unknown")
    for index, key in enumerate(_MATURITY_WITH_UNKNOWN):
        if index >= len(levels):
            break
        level = levels[index]
        _collect_exact(level, {"key", "label_ru", "count"}, f"evidence_maturity.levels[{index}]", errors)
        if level != {"key": key, "label_ru": _MATURITY_LABELS[key], "count": expected.get(key, 0)}:
            errors.append(f"evidence_maturity.levels[{index}] population mismatch")


def _validate_interest(
    raw: object,
    threads: Sequence[Mapping[str, object]],
    errors: list[str],
) -> None:
    primary = [str(item.get("canonical_thread_id") or "") for item in threads]
    thread_by_id = {
        str(item.get("canonical_thread_id") or ""): item for item in threads
    }
    interest = _mapping(raw)
    _collect_exact(
        interest,
        {
            "current_reactions_status",
            "historical_attention_status",
            "confirmed_feedback_status",
            "confirmed_feedback_events_available",
            "confirmed_feedback_events_considered",
            "confirmed_feedback_truncated",
            "current_reactions",
            "decayed_historical_attention",
            "confirmed_feedback",
            "semantics_ru",
        },
        "operator_interest",
        errors,
    )
    current_status = str(interest.get("current_reactions_status") or "")
    historical_status = str(interest.get("historical_attention_status") or "")
    feedback_status = str(interest.get("confirmed_feedback_status") or "")
    if current_status not in {"available", "unavailable"}:
        errors.append("operator_interest.current_reactions_status is invalid")
    if historical_status not in {"available", "partial", "unavailable"}:
        errors.append("operator_interest.historical_attention_status is invalid")
    if feedback_status not in {"available", "partial", "unavailable"}:
        errors.append("operator_interest.confirmed_feedback_status is invalid")
    if not _safe_reader_text(interest.get("semantics_ru"), russian=True, maximum=600):
        errors.append("operator_interest.semantics_ru is invalid")

    thread_interest = {
        thread_id: _mapping(_mapping(thread_by_id[thread_id]).get("operator_interest"))
        for thread_id in primary
    }
    expected_current_statuses = {
        str(item.get("current_reaction_status") or "")
        for item in thread_interest.values()
    }
    if expected_current_statuses != {current_status}:
        errors.append("operator_interest current reaction availability mismatch")
    historical_thread_statuses = {
        str(item.get("historical_attention_status") or "")
        for item in thread_interest.values()
    }
    expected_historical_status = (
        "available"
        if historical_thread_statuses == {"available"}
        else "unavailable"
        if historical_thread_statuses == {"unavailable"}
        else "partial"
    )
    if historical_status != expected_historical_status:
        errors.append("operator_interest historical availability mismatch")
    feedback_thread_statuses = {
        str(item.get("confirmed_feedback_status") or "")
        for item in thread_interest.values()
    }
    if feedback_thread_statuses != {feedback_status}:
        errors.append("operator_interest feedback availability mismatch")

    current = _mapping_list_strict(
        interest.get("current_reactions"),
        "operator_interest.current_reactions",
        errors,
        MAX_PRIMARY_THREADS,
    )
    current_ids: list[str] = []
    for index, item in enumerate(current):
        path = f"operator_interest.current_reactions[{index}]"
        _collect_exact(
            item,
            {"canonical_thread_id", "event_count", "evidence_refs"},
            path,
            errors,
        )
        thread_id = str(item.get("canonical_thread_id") or "")
        count = _checked_positive_int(item.get("event_count"), f"{path}.event_count", errors)
        refs = _bounded_strings(
            item.get("evidence_refs"),
            f"{path}.evidence_refs",
            errors,
            maximum=12,
        )
        if thread_id not in thread_by_id or not refs:
            errors.append(f"{path} lacks a known thread/evidence basis")
        if any(not _safe_reference(ref) for ref in refs):
            errors.append(f"{path}.evidence_refs contains an unsafe reference")
        expected = thread_interest.get(thread_id, {})
        if expected and (
            expected.get("current_reaction_count") != count
            or expected.get("current_reaction_evidence_refs") != refs
        ):
            errors.append(f"{path} differs from canonical thread reaction projection")
        current_ids.append(thread_id)
    if len(current_ids) != len(set(current_ids)):
        errors.append("operator_interest.current_reactions identities are duplicated")
    expected_current_ids = [
        thread_id
        for thread_id in primary
        if _nonnegative_int(
            thread_interest[thread_id].get("current_reaction_count"), default=0
        )
        > 0
    ]
    if current_ids != expected_current_ids:
        errors.append("operator_interest.current_reactions population/order mismatch")
    if current_status == "unavailable" and current:
        errors.append("unavailable reaction snapshot cannot expose current reactions")

    historical = _mapping_list_strict(
        interest.get("decayed_historical_attention"),
        "operator_interest.decayed_historical_attention",
        errors,
        MAX_PRIMARY_THREADS,
    )
    historical_ids: list[str] = []
    for index, item in enumerate(historical):
        path = f"operator_interest.decayed_historical_attention[{index}]"
        _collect_exact(item, {"canonical_thread_id", "score", "state"}, path, errors)
        thread_id = str(item.get("canonical_thread_id") or "")
        score = item.get("score")
        if (
            thread_id not in thread_by_id
            or isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
            or not 0 < float(score) <= 1
            or item.get("state") != "decayed_registry_hint"
        ):
            errors.append(f"{path} is invalid")
        expected_score = thread_interest.get(thread_id, {}).get(
            "historical_attention_score"
        )
        if expected_score != score:
            errors.append(f"{path}.score differs from canonical thread projection")
        historical_ids.append(thread_id)
    if len(historical_ids) != len(set(historical_ids)):
        errors.append("operator_interest.decayed_historical_attention identities are duplicated")
    expected_historical_ids = [
        thread_id
        for thread_id in primary
        if _finite_score(
            thread_interest[thread_id].get("historical_attention_score"),
            default=0.0,
        )
        > 0
    ]
    if historical_ids != expected_historical_ids:
        errors.append("operator_interest.decayed_historical_attention population/order mismatch")
    if historical_status == "unavailable" and historical:
        errors.append("unavailable historical attention cannot expose observations")

    feedback_rows = _mapping_list_strict(
        interest.get("confirmed_feedback"),
        "operator_interest.confirmed_feedback",
        errors,
        40,
    )
    feedback_refs: list[str] = []
    for index, item in enumerate(feedback_rows):
        path = f"operator_interest.confirmed_feedback[{index}]"
        _collect_exact(item, {"feedback_ref", "reader_summary_ru"}, path, errors)
        ref = str(item.get("feedback_ref") or "")
        if not _safe_reference(ref):
            errors.append(f"{path}.feedback_ref is invalid")
        if not _safe_reader_text(
            item.get("reader_summary_ru"),
            russian=True,
            maximum=500,
        ):
            errors.append(f"{path}.reader_summary_ru is invalid")
        feedback_refs.append(ref)
    if len(feedback_refs) != len(set(feedback_refs)):
        errors.append("operator_interest.confirmed_feedback refs are duplicated")
    available = interest.get("confirmed_feedback_events_available")
    considered = interest.get("confirmed_feedback_events_considered")
    truncated = interest.get("confirmed_feedback_truncated")
    if feedback_status == "unavailable":
        if any(value is not None for value in (available, considered, truncated)):
            errors.append("unavailable feedback requires null availability metadata")
        if feedback_rows:
            errors.append("unavailable feedback cannot expose confirmed rows")
    else:
        available_count = _checked_nonnegative_int(
            available,
            "operator_interest.confirmed_feedback_events_available",
            errors,
        )
        considered_count = _checked_nonnegative_int(
            considered,
            "operator_interest.confirmed_feedback_events_considered",
            errors,
        )
        if not isinstance(truncated, bool):
            errors.append("operator_interest.confirmed_feedback_truncated is invalid")
        if available_count < considered_count:
            errors.append("operator_interest feedback considered exceeds available")
        if considered_count != len(feedback_rows):
            errors.append("operator_interest feedback row/count mismatch")
        if isinstance(truncated, bool) and truncated != (available_count > considered_count):
            errors.append("operator_interest feedback truncated/count mismatch")


def _validate_learning(raw: object, thread_count: int, errors: list[str]) -> None:
    learning = _mapping(raw)
    _collect_exact(
        learning,
        {"status", "stages", "scope_thread_count", "semantics_ru"},
        "learning_progression",
        errors,
    )
    if learning.get("status") not in {"available", "partial", "unavailable"}:
        errors.append("learning_progression.status mismatch")
    if learning.get("scope_thread_count") != thread_count:
        errors.append("learning_progression.scope_thread_count mismatch")
    if not _safe_reader_text(learning.get("semantics_ru"), russian=True, maximum=600):
        errors.append("learning_progression.semantics_ru is invalid")
    stages = _mapping_list_strict(learning.get("stages"), "learning_progression.stages", errors, 7)
    if len(stages) != 7:
        errors.append("learning_progression must contain all seven stages")
    prior: int | None = None
    for index, key in enumerate(_LEARNING_KEYS):
        if index >= len(stages):
            break
        stage = stages[index]
        _collect_exact(
            stage,
            {"key", "label_ru", "count", "observation_status", "confirmation_kind", "evidence_refs"},
            f"learning_progression.stages[{index}]",
            errors,
        )
        if stage.get("key") != key or stage.get("label_ru") != _LEARNING_LABELS[key]:
            errors.append(f"learning_progression.stages[{index}] identity mismatch")
        status = stage.get("observation_status")
        refs = _bounded_strings(stage.get("evidence_refs"), f"learning_progression.stages[{index}].evidence_refs", errors, maximum=20)
        if status == "unknown":
            if stage.get("count") is not None or stage.get("confirmation_kind") != "none" or refs:
                errors.append(f"learning_progression.stages[{index}] unknown semantics invalid")
        elif status == "confirmed":
            count = _checked_positive_int(
                stage.get("count"),
                f"learning_progression.stages[{index}].count",
                errors,
            )
            if stage.get("confirmation_kind") != _LEARNING_CONFIRMATION[key] or not refs:
                errors.append(f"learning_progression.stages[{index}] confirmation basis invalid")
            if any(not _safe_reference(ref) for ref in refs):
                errors.append(
                    f"learning_progression.stages[{index}].evidence_refs contains an unsafe reference"
                )
            if prior is not None and count > prior:
                errors.append("learning_progression confirmed counts increase")
            prior = count
        else:
            errors.append(f"learning_progression.stages[{index}].observation_status invalid")


def _validate_backlog(raw: object, primary: Sequence[str], errors: list[str]) -> None:
    rows = _mapping_list_strict(raw, "study_backlog", errors, MAX_STUDY_BACKLOG)
    identities: list[str] = []
    labels: list[str] = []
    next_steps: list[str] = []
    token_sets: list[set[str]] = []
    for index, row in enumerate(rows):
        path = f"study_backlog[{index}]"
        _collect_exact(
            row,
            {"canonical_thread_id", "title_ru", "priority", "reason_ru", "next_step_ru", "evidence_refs", "audit_ref"},
            path,
            errors,
        )
        thread_id = str(row.get("canonical_thread_id") or "")
        if thread_id not in primary:
            errors.append(f"{path}.canonical_thread_id is unknown")
        if row.get("priority") not in {"high", "medium", "low"}:
            errors.append(f"{path}.priority is invalid")
        title = str(row.get("title_ru") or "")
        reason = str(row.get("reason_ru") or "")
        next_step = str(row.get("next_step_ru") or "")
        if not (
            _safe_reader_text(title, russian=True, maximum=260)
            and _safe_reader_text(reason, russian=True, maximum=600)
            and _safe_reader_text(next_step, russian=True, maximum=600)
        ):
            errors.append(f"{path} reader copy must be Russian")
        refs = _bounded_strings(row.get("evidence_refs"), f"{path}.evidence_refs", errors, maximum=4)
        if not refs:
            errors.append(f"{path}.evidence_refs must not be empty")
        if any(not _safe_reference(ref) for ref in refs):
            errors.append(f"{path}.evidence_refs contains an unsafe reference")
        if not re.fullmatch(
            rf"{re.escape(AUDIT_EXPLORER_HTML_FILENAME)}#[A-Za-z0-9][A-Za-z0-9._:-]{{0,199}}",
            str(row.get("audit_ref") or ""),
        ):
            errors.append(f"{path}.audit_ref is invalid")
        identities.append(thread_id)
        labels.append(title)
        next_steps.append(next_step)
        tokens = set(_normalize_text(f"{title} {reason} {next_step}").split())
        if any(_jaccard(tokens, previous) >= 0.88 for previous in token_sets if tokens | previous):
            errors.append(f"{path} is a near-duplicate backlog row")
        token_sets.append(tokens)
    if len(identities) != len(set(identities)):
        errors.append("study_backlog canonical items are duplicated")
    _reject_duplicate_reader_text(labels, "study backlog title", errors)
    _reject_duplicate_reader_text(next_steps, "study backlog next step", errors)


def _render_document(value: Mapping[str, object]) -> str:
    period = _mapping(value["reporting_period"])
    threads = _mapping_list(value["canonical_threads"])
    interest = _mapping(value["operator_interest"])
    backlog = _mapping_list(value["study_backlog"])
    visuals = [render_report_visual(spec).html for spec in _mapping_list(value["visual_specs"])]
    visual_by_schema = {
        str(spec.get("schema_version")): html
        for spec, html in zip(_mapping_list(value["visual_specs"]), visuals)
    }
    growing = [item for item in threads if item.get("display_status") == "growing"]
    weakening = [
        item
        for item in threads
        if item.get("display_status") in {"stale", "contradicted"}
    ]
    low_evidence = [
        item
        for item in threads
        if item.get("evidence_maturity") in {"single_source", "repeated_signal", "unknown"}
    ]
    partial_banner = (
        '<aside class="run-status-partial" role="alert"><strong>Карта частичная.</strong><ul>'
        + "".join(f"<li>{_e(reason)}</li>" for reason in value["partial_reasons_ru"])
        + "</ul></aside>"
        if value["partial"]
        else ""
    )
    overview_cards = "".join(
        (
            _overview_card("Что растёт?", growing, "Новых подтверждённых движений нет."),
            _overview_card(
                "Что слабеет?",
                weakening,
                "Среди первичных тем нет явно устаревающих или противоречивых.",
            ),
            _attention_overview_card(interest, threads),
            _overview_card(
                "Где мало доказательств?",
                low_evidence,
                "У первичных тем нет явно слабой доказательной базы.",
            ),
        )
    )
    registry = "".join(_thread_registry_row(item) for item in threads)
    backlog_html = (
        "<ol>"
        + "".join(
            "<li><strong>{title}</strong> — {reason} <a href=\"{audit}\">проверить происхождение</a>.</li>".format(
                title=_e(item["title_ru"]),
                reason=_e(item["reason_ru"]),
                audit=_e(item["audit_ref"]),
            )
            for item in backlog
        )
        + "</ol>"
        if backlog
        else '<p class="atlas-v2__empty">Учебный backlog пуст: это не означает, что все стадии обучения подтверждены.</p>'
    )
    technical = _mapping(value["technical_refs"])
    metrics = _mapping(value["content_metrics"])
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="atlas-schema-version" content="{_e(value['schema_version'])}">
<title>Карта знаний — {_e(period['reporting_week'])}</title>
<style>{_atlas_styles()}\n{report_visual_styles()}</style>
</head>
<body>
<header class="atlas-v2__header">
<p class="atlas-v2__kicker">Knowledge Atlas V2 · предварительный reader package</p>
<h1>Карта накопленного знания</h1>
<p>Период: <strong>{_e(period['analysis_period_start'])}</strong> — <strong>{_e(period['analysis_period_end'])}</strong>. Состояние канонического реестра зафиксировано на конец периода.</p>
<p class="atlas-v2__meta">Показано {len(threads)} канонических тем. Реакции, подтверждённая обратная связь, зрелость доказательств и обучение не смешиваются.</p>
<nav aria-label="Разделы карты"><a href="#overview">Обзор</a><a href="#graph">Связи</a><a href="#history">История</a><a href="#sources">Источники</a><a href="#registry">Реестр</a><a href="#study">Изучить дальше</a></nav>
</header>
<main class="atlas-v2 irx-report">
{partial_banner}
<section id="overview" class="atlas-v2__section atlas-v2__overview">
<h2>Ответы перед деталями</h2>
<div class="atlas-v2__overview-grid">{overview_cards}</div>
</section>
<section id="graph" class="atlas-v2__section">
<h2>Канонические связи</h2>
{visual_by_schema['report_visual.knowledge_graph.v1']}
</section>
<section id="history" class="atlas-v2__section">
<h2>Изменения за двенадцать недель</h2>
{visual_by_schema['report_visual.thread_timeline.v1']}
</section>
<section id="sources" class="atlas-v2__section">
<h2>Источники и независимая поддержка</h2>
{visual_by_schema['report_visual.source_thread_heatmap.v1']}
</section>
<section id="maturity" class="atlas-v2__section">
<h2>Зрелость доказательств</h2>
{visual_by_schema['report_visual.evidence_maturity.v1']}
</section>
<section id="learning" class="atlas-v2__section">
<h2>Подтверждённое обучение</h2>
{visual_by_schema['report_visual.learning_progression.v1']}
</section>
<section id="registry" class="atlas-v2__section">
<h2>Канонический реестр</h2>
<p>Заголовок и тезис — читательская проекция. Полные атомы, цитаты, aliases, memberships и merge/split provenance находятся в техническом обозревателе.</p>
<div class="atlas-v2__registry">{registry}</div>
</section>
<section id="study" class="atlas-v2__section">
<h2>Ограниченный backlog изучения</h2>
{backlog_html}
</section>
<section class="atlas-v2__section atlas-v2__audit-callout">
<h2>Нужны доказательства и сырые детали?</h2>
<p><a href="{_e(AUDIT_EXPLORER_HTML_FILENAME)}"><strong>Открыть Knowledge Audit Explorer</strong></a>. Это отдельная техническая поверхность без читательского лимита: там сохранены атомы, цитаты, ссылки, raw memberships, aliases и история curator решений.</p>
<details class="atlas-v2__technical"><summary>Технические ссылки и точная identity</summary>
<ul><li>Run: {_e(value['run_id'])}</li><li>Manifest: {_e(technical['manifest_path'])}</li><li>Audit JSON: {_e(technical['audit_explorer_json_path'])}</li><li>Совместимый V1 Atlas: {_e(technical['compatibility_atlas_path'])}</li><li>Видимых слов: {_e(metrics['visible_word_count'])} из {_e(metrics['hard_max'])}.</li></ul>
</details>
</section>
</main>
</body>
</html>
"""


def _overview_card(
    title: str,
    threads: Sequence[Mapping[str, object]],
    empty: str,
) -> str:
    body = (
        "<ul>"
        + "".join(
            f"<li><a href=\"#thread-{_e(_safe_fragment(item['stable_slug']))}\">{_e(item['title_ru'])}</a></li>"
            for item in threads[:3]
        )
        + "</ul>"
        if threads
        else f'<p class="atlas-v2__empty">{_e(empty)}</p>'
    )
    return f'<article class="atlas-v2__overview-card"><h3>{_e(title)}</h3>{body}</article>'


def _attention_overview_card(
    interest: Mapping[str, object],
    threads: Sequence[Mapping[str, object]],
) -> str:
    thread_by_id = {
        str(item.get("canonical_thread_id") or ""): item for item in threads
    }
    current_ids = [
        str(item.get("canonical_thread_id") or "")
        for item in _mapping_list(interest.get("current_reactions"))
    ]
    historical_ids = [
        str(item.get("canonical_thread_id") or "")
        for item in _mapping_list(interest.get("decayed_historical_attention"))
    ]
    feedback_ids = [
        str(item.get("canonical_thread_id") or "")
        for item in threads
        if _nonnegative_int(
            _mapping(item.get("operator_interest")).get("confirmed_feedback_count"),
            default=0,
        )
    ]

    def channel_line(label: str, status: str, ids: Sequence[str]) -> str:
        if status == "unavailable":
            return f"<li><strong>{_e(label)}:</strong> неизвестно.</li>"
        titles = [
            str(thread_by_id[thread_id]["title_ru"])
            for thread_id in ids[:2]
            if thread_id in thread_by_id
        ]
        value = ", ".join(titles) if titles else "подтверждённых событий нет"
        suffix = " Данные частичны." if status == "partial" else ""
        return (
            f"<li><strong>{_e(label)}:</strong> {_e(value)}.{_e(suffix)}</li>"
        )

    feedback_rows = _mapping_list(interest.get("confirmed_feedback"))
    feedback_line = channel_line(
        "Подтверждённая обратная связь",
        str(interest.get("confirmed_feedback_status") or "unavailable"),
        feedback_ids,
    )
    if feedback_rows and not feedback_ids:
        feedback_line = (
            "<li><strong>Подтверждённая обратная связь:</strong> "
            f"событий: {_e(len(feedback_rows))}; привязка к конкретной теме не сохранена.</li>"
        )
    body = "<ul>" + "".join(
        (
            channel_line(
                "Текущие реакции",
                str(interest.get("current_reactions_status") or "unavailable"),
                current_ids,
            ),
            channel_line(
                "Затухающее историческое внимание",
                str(interest.get("historical_attention_status") or "unavailable"),
                historical_ids,
            ),
            feedback_line,
        )
    ) + "</ul>"
    return (
        '<article class="atlas-v2__overview-card"><h3>Чему уделялось внимание?</h3>'
        + body
        + "</article>"
    )


def _thread_registry_row(thread: Mapping[str, object]) -> str:
    interest = _mapping(thread["operator_interest"])
    status_labels = {
        "growing": "растёт",
        "watch": "наблюдать",
        "stale": "устаревает",
        "contradicted": "есть противоречия",
    }
    lineage = _mapping(thread["merge_split_summary"])
    lineage_count = sum(len(_strings(lineage.get(key))) for key in lineage)
    current = (
        str(interest["current_reaction_count"])
        if interest.get("current_reaction_status") == "available"
        else "неизвестно"
    )
    historical = (
        str(interest["historical_attention_score"])
        if interest.get("historical_attention_status") == "available"
        else "неизвестно"
    )
    feedback = (
        str(interest["confirmed_feedback_count"])
        if interest.get("confirmed_feedback_status") in {"available", "partial"}
        else "неизвестно"
    )
    attention = (
        f"текущих реакций: {current}; затухающее историческое внимание: {historical}; "
        f"подтверждённой обратной связи: {feedback}"
    )
    last_change = thread.get("last_meaningful_change") or "неизвестно"
    return (
        f'<article id="thread-{_e(_safe_fragment(thread["stable_slug"]))}" class="atlas-v2__thread">'
        f"<h3>{_e(thread['title_ru'])}</h3>"
        f"<p>{_e(thread['thesis'])}</p>"
        f'<p class="atlas-v2__facts"><span>Статус: {_e(status_labels[str(thread["display_status"])])}</span>'
        f'<span>Зрелость: {_e(_MATURITY_LABELS[str(thread["evidence_maturity"])])}</span>'
        f'<span>Источниковых групп: {_e(thread["independent_source_count"])}</span>'
        f'<span>Последнее значимое изменение: {_e(last_change)}</span></p>'
        '<details><summary>Ограничения, внимание и provenance</summary>'
        f"<p>{_e(attention)}. Эти признаки не означают переход обучения.</p>"
        f"<p>Событий merge/split: {_e(lineage_count)}. Стабильная ссылка: {_e(thread['canonical_thread_id'])}.</p>"
        f'<p><a href="{_e(thread["audit_ref"])}">Полная техническая карточка и доказательства</a>.</p>'
        "</details></article>"
    )


def _atlas_styles() -> str:
    return """
:root{color-scheme:light;--ink:#17212b;--muted:#526273;--line:#cbd5e1;--paper:#fff;--wash:#f5f7fb;--accent:#1d4ed8;--warn:#9a3412}
*{box-sizing:border-box}body{margin:0;background:var(--wash);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}.atlas-v2__header{max-width:1180px;margin:0 auto;padding:28px 24px 18px}.atlas-v2__kicker{margin:0 0 6px;color:var(--accent);font-size:.78rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase}.atlas-v2__header h1{margin:0 0 12px;font-size:clamp(2rem,5vw,3.5rem);line-height:1.08}.atlas-v2__header p{max-width:920px}.atlas-v2__meta{color:var(--muted)}.atlas-v2__header nav{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.atlas-v2__header nav a{border:1px solid var(--line);border-radius:999px;background:#fff;padding:6px 11px}.atlas-v2{max-width:1180px}.atlas-v2__section{margin:0 0 16px;padding:22px;border:1px solid var(--line);border-radius:14px;background:var(--paper)}.atlas-v2__section>h2{margin-top:0}.atlas-v2__overview-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.atlas-v2__overview-card,.atlas-v2__thread{padding:14px;border:1px solid var(--line);border-radius:10px;background:#f8fafc}.atlas-v2__overview-card h3,.atlas-v2__thread h3{margin-top:0}.atlas-v2__overview-card ul{padding-left:20px}.atlas-v2__empty{color:var(--muted)}.atlas-v2__registry{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.atlas-v2__facts{display:flex;flex-wrap:wrap;gap:6px}.atlas-v2__facts span{border:1px solid var(--line);border-radius:999px;padding:3px 8px;background:#fff}.run-status-partial{margin:0 0 16px;padding:16px 18px;border:2px solid var(--warn);border-radius:12px;background:#fff7ed}.atlas-v2__technical{margin-top:12px;color:var(--muted)}a{color:var(--accent);text-decoration-thickness:2px;text-underline-offset:2px}summary{cursor:pointer;font-weight:700}
@media(max-width:820px){.atlas-v2__overview-grid,.atlas-v2__registry{grid-template-columns:1fr 1fr}}
@media(max-width:600px){.atlas-v2__header{padding:18px 12px 12px}.atlas-v2{padding:0 10px}.atlas-v2__section{padding:14px}.atlas-v2__overview-grid,.atlas-v2__registry{grid-template-columns:1fr}}
@media print{body{background:#fff}.atlas-v2__header,.atlas-v2{max-width:none}.atlas-v2__section,.atlas-v2__thread{break-inside:avoid}}
""".strip()


def _validate_bound_input_contract(
    raw: Mapping[str, object] | None,
    *,
    manifest: Mapping[str, object],
    schema_version: str,
    label: str,
    maximum: int,
    item_normalizer: Any,
) -> dict[str, object]:
    period = _period_from_manifest(manifest)
    if raw is None:
        value: dict[str, object] = {
            "schema_version": schema_version,
            "run_id": str(manifest.get("run_id") or ""),
            "reporting_period": period,
            "as_of": period["analysis_period_end"],
            "status": "unavailable",
            "items": [],
        }
    else:
        if not isinstance(raw, Mapping):
            raise KnowledgeAtlasV2ValidationError(
                [f"{label} must be an identity-bound object"]
            )
        value = _json_copy(raw, label)
    _exact(
        value,
        {"schema_version", "run_id", "reporting_period", "as_of", "status", "items"},
        label,
    )
    expected_identity = {
        "schema_version": schema_version,
        "run_id": manifest.get("run_id"),
        "reporting_period": period,
        "as_of": period["analysis_period_end"],
    }
    mismatches = [
        field for field, expected in expected_identity.items() if value.get(field) != expected
    ]
    if mismatches:
        raise KnowledgeAtlasV2ValidationError(
            [f"{label} {field} mismatch" for field in mismatches]
        )
    status = str(value.get("status") or "")
    if status not in {"available", "partial", "unavailable"}:
        raise KnowledgeAtlasV2ValidationError([f"{label}.status is invalid"])
    raw_items = value.get("items")
    if (
        not isinstance(raw_items, list)
        or len(raw_items) > maximum
        or not all(isinstance(item, Mapping) for item in raw_items)
    ):
        raise KnowledgeAtlasV2ValidationError([f"{label}.items is invalid"])
    if status == "unavailable" and raw_items:
        raise KnowledgeAtlasV2ValidationError(
            [f"{label} unavailable contract must not contain items"]
        )
    normalized_items = [
        item_normalizer(item, index=index, manifest=manifest, label=label)
        for index, item in enumerate(raw_items)
    ]
    keys = [_bound_contract_item_key(schema_version, item) for item in normalized_items]
    if len(keys) != len(set(keys)):
        raise KnowledgeAtlasV2ValidationError([f"{label}.items contains duplicates"])
    value["items"] = sorted(
        normalized_items,
        key=lambda item: _bound_contract_item_key(schema_version, item),
    )
    return value


def _bound_contract_item_key(
    schema_version: str,
    item: Mapping[str, object],
) -> tuple[object, ...]:
    if schema_version == ATLAS_V2_RELATIONS_SCHEMA_VERSION:
        return (
            str(item.get("source_thread_id") or ""),
            str(item.get("target_thread_id") or ""),
            str(item.get("relation") or ""),
        )
    if schema_version == ATLAS_V2_HISTORY_SCHEMA_VERSION:
        return (
            str(item.get("canonical_thread_id") or ""),
            str(item.get("week") or ""),
        )
    if schema_version == ATLAS_V2_LEARNING_EVENTS_SCHEMA_VERSION:
        return (
            _LEARNING_KEYS.index(str(item.get("stage") or "")),
            str(item.get("canonical_thread_id") or ""),
        )
    raise KnowledgeAtlasV2ValidationError(["unknown Atlas V2 bound input schema"])


def _normalized_contract_refs(value: object, *, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > 20
        or not all(
            isinstance(item, str) and item and item == item.strip() for item in value
        )
    ):
        raise KnowledgeAtlasV2ValidationError([f"{label} is invalid"])
    refs = list(value)
    if len(refs) != len(set(refs)):
        raise KnowledgeAtlasV2ValidationError([f"{label} contains duplicates"])
    if any(not _safe_reference(ref) for ref in refs):
        raise KnowledgeAtlasV2ValidationError([f"{label} contains an unsafe reference"])
    return sorted(refs)


def _normalize_relation_contract_item(
    raw: Mapping[str, object],
    *,
    index: int,
    manifest: Mapping[str, object],
    label: str,
) -> dict[str, object]:
    del manifest
    item = _json_copy(raw, f"{label}.items[{index}]")
    _exact(item, _RELATION_FIELDS, f"{label}.items[{index}]")
    source = str(item.get("source_thread_id") or "")
    target = str(item.get("target_thread_id") or "")
    relation = str(item.get("relation") or "")
    weight = item.get("weight")
    if (
        not _SAFE_ID_RE.fullmatch(source)
        or not _SAFE_ID_RE.fullmatch(target)
        or source == target
        or relation not in _GRAPH_RELATIONS
        or isinstance(weight, bool)
        or not isinstance(weight, int)
        or weight <= 0
    ):
        raise KnowledgeAtlasV2ValidationError(
            [f"{label}.items[{index}] has invalid typed relation fields"]
        )
    item["evidence_refs"] = _normalized_contract_refs(
        item.get("evidence_refs"),
        label=f"{label}.items[{index}].evidence_refs",
    )
    return item


def _normalize_history_contract_item(
    raw: Mapping[str, object],
    *,
    index: int,
    manifest: Mapping[str, object],
    label: str,
) -> dict[str, object]:
    del manifest
    item = _json_copy(raw, f"{label}.items[{index}]")
    _exact(
        item,
        {"canonical_thread_id", "week", "momentum", "evidence_count"},
        f"{label}.items[{index}]",
    )
    thread_id = str(item.get("canonical_thread_id") or "")
    week = str(item.get("week") or "")
    if not _SAFE_ID_RE.fullmatch(thread_id) or not _ISO_WEEK_RE.fullmatch(week):
        raise KnowledgeAtlasV2ValidationError(
            [f"{label}.items[{index}] has invalid thread/week identity"]
        )
    momentum = item.get("momentum")
    if momentum is not None:
        momentum = _finite_score(momentum, default=-1.0, maximum=None)
        if momentum < 0:
            raise KnowledgeAtlasV2ValidationError(
                [f"{label}.items[{index}].momentum must be non-negative"]
            )
    evidence = item.get("evidence_count")
    if evidence is not None and (
        isinstance(evidence, bool) or not isinstance(evidence, int) or evidence < 0
    ):
        raise KnowledgeAtlasV2ValidationError(
            [f"{label}.items[{index}].evidence_count is invalid"]
        )
    item["momentum"] = momentum
    item["evidence_count"] = evidence
    return item


def _normalize_learning_contract_item(
    raw: Mapping[str, object],
    *,
    index: int,
    manifest: Mapping[str, object],
    label: str,
) -> dict[str, object]:
    item = _json_copy(raw, f"{label}.items[{index}]")
    _exact(
        item,
        {
            "stage",
            "canonical_thread_id",
            "observed_at",
            "confirmation_kind",
            "evidence_refs",
        },
        f"{label}.items[{index}]",
    )
    stage = str(item.get("stage") or "")
    thread_id = str(item.get("canonical_thread_id") or "")
    if (
        stage not in _LEARNING_KEYS
        or not _SAFE_ID_RE.fullmatch(thread_id)
        or item.get("confirmation_kind") != _LEARNING_CONFIRMATION.get(stage)
    ):
        raise KnowledgeAtlasV2ValidationError(
            [f"{label}.items[{index}] has invalid learning identity/confirmation"]
        )
    try:
        observed = _parse_timestamp(item.get("observed_at"))
        period = _period_from_manifest(manifest)
        start = _parse_timestamp(period["analysis_period_start"])
        end = _parse_timestamp(period["analysis_period_end"])
    except ValueError as exc:
        raise KnowledgeAtlasV2ValidationError(
            [f"{label}.items[{index}].observed_at is invalid"]
        ) from exc
    if not start <= observed < end:
        raise KnowledgeAtlasV2ValidationError(
            [f"{label}.items[{index}].observed_at is outside the reporting period"]
        )
    item["observed_at"] = observed.isoformat().replace("+00:00", "Z")
    item["evidence_refs"] = _normalized_contract_refs(
        item.get("evidence_refs"),
        label=f"{label}.items[{index}].evidence_refs",
    )
    return item


def _build_source_catalog(
    *,
    manifest: Mapping[str, object],
    editorial_input_package: Mapping[str, object],
    validated_relations: Mapping[str, object] | None,
    historical_observations: Mapping[str, object] | None,
    learning_events: Mapping[str, object] | None,
    source_contributions: Mapping[str, object] | None,
) -> dict[str, object]:
    period = _period_from_manifest(manifest)
    catalog = {
        "schema_version": ATLAS_V2_SOURCE_CATALOG_SCHEMA_VERSION,
        "run_id": str(manifest.get("run_id") or ""),
        "reporting_period": period,
        "as_of": period["analysis_period_end"],
        "editorial_input_package": _json_copy(
            editorial_input_package,
            "editorial_input_package",
        ),
        "validated_relations": _validate_bound_input_contract(
            validated_relations,
            manifest=manifest,
            schema_version=ATLAS_V2_RELATIONS_SCHEMA_VERSION,
            label="validated_relations",
            maximum=100,
            item_normalizer=_normalize_relation_contract_item,
        ),
        "historical_observations": _validate_bound_input_contract(
            historical_observations,
            manifest=manifest,
            schema_version=ATLAS_V2_HISTORY_SCHEMA_VERSION,
            label="historical_observations",
            maximum=MAX_PRIMARY_THREADS * 12,
            item_normalizer=_normalize_history_contract_item,
        ),
        "learning_events": _validate_bound_input_contract(
            learning_events,
            manifest=manifest,
            schema_version=ATLAS_V2_LEARNING_EVENTS_SCHEMA_VERSION,
            label="learning_events",
            maximum=MAX_PRIMARY_THREADS * len(_LEARNING_KEYS),
            item_normalizer=_normalize_learning_contract_item,
        ),
        "source_contributions": _validate_source_contributions(
            source_contributions
            if source_contributions is not None
            else _unavailable_source_contributions(manifest),
            manifest=manifest,
            known_thread_ids=None,
        ),
    }
    return _validate_source_catalog(catalog, manifest=manifest)


def _validate_source_catalog(
    value: Mapping[str, object],
    *,
    manifest: Mapping[str, object],
) -> dict[str, object]:
    catalog = _json_copy(value, "Atlas V2 source catalog")
    errors: list[str] = []
    _collect_exact(
        catalog,
        {
            "schema_version",
            "run_id",
            "reporting_period",
            "as_of",
            "editorial_input_package",
            "validated_relations",
            "historical_observations",
            "learning_events",
            "source_contributions",
        },
        "source_catalog",
        errors,
    )
    period = _period_from_manifest(manifest)
    if catalog.get("schema_version") != ATLAS_V2_SOURCE_CATALOG_SCHEMA_VERSION:
        errors.append("source_catalog schema mismatch")
    if catalog.get("run_id") != manifest.get("run_id"):
        errors.append("source_catalog run_id mismatch")
    if _mapping(catalog.get("reporting_period")) != period:
        errors.append("source_catalog reporting period mismatch")
    if catalog.get("as_of") != period["analysis_period_end"]:
        errors.append("source_catalog as_of mismatch")
    editorial_input = _mapping(catalog.get("editorial_input_package"))
    if editorial_input.get("schema_version") != EDITORIAL_INPUT_SCHEMA_VERSION:
        errors.append("source_catalog editorial input schema mismatch")
    if editorial_input.get("run_id") != manifest.get("run_id"):
        errors.append("source_catalog editorial input run_id mismatch")
    try:
        normalized_contributions = _validate_source_contributions(
            _mapping(catalog.get("source_contributions")),
            manifest=manifest,
            known_thread_ids=None,
        )
        if catalog.get("source_contributions") != normalized_contributions:
            errors.append("source_catalog.source_contributions is not canonical")
    except KnowledgeAtlasV2ValidationError as exc:
        errors.extend(
            f"source_catalog.source_contributions: {item}" for item in exc.errors
        )
    for field, schema_version, maximum, normalizer in (
        (
            "validated_relations",
            ATLAS_V2_RELATIONS_SCHEMA_VERSION,
            100,
            _normalize_relation_contract_item,
        ),
        (
            "historical_observations",
            ATLAS_V2_HISTORY_SCHEMA_VERSION,
            MAX_PRIMARY_THREADS * 12,
            _normalize_history_contract_item,
        ),
        (
            "learning_events",
            ATLAS_V2_LEARNING_EVENTS_SCHEMA_VERSION,
            MAX_PRIMARY_THREADS * len(_LEARNING_KEYS),
            _normalize_learning_contract_item,
        ),
    ):
        try:
            normalized = _validate_bound_input_contract(
                _mapping(catalog.get(field)),
                manifest=manifest,
                schema_version=schema_version,
                label=field,
                maximum=maximum,
                item_normalizer=normalizer,
            )
            if catalog.get(field) != normalized:
                errors.append(f"source_catalog.{field} is not canonical")
        except KnowledgeAtlasV2ValidationError as exc:
            errors.extend(f"source_catalog.{field}: {item}" for item in exc.errors)
    if errors:
        raise KnowledgeAtlasV2ValidationError(errors)
    return catalog


def _require_reader_value_quality(
    sidecar: Mapping[str, object],
    rendered_html: str,
    *,
    manifest: Mapping[str, object],
) -> None:
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
        surface=ATLAS_V2_SURFACE,
    )
    try:
        require_reader_report_quality(report)
    except ReaderValueQualityError as exc:
        codes = [
            str(finding.get("code") or "reader_value.invalid")
            for dimension in report.get("dimensions", [])
            if isinstance(dimension, Mapping)
            for finding in dimension.get("findings", [])
            if isinstance(finding, Mapping) and finding.get("severity") == "critical"
        ]
        raise KnowledgeAtlasV2ArtifactError(
            "Atlas V2 failed reader-value quality gates: " + ", ".join(codes[:12])
        ) from exc


def _require_terminal_manifest(manifest: Mapping[str, object], manifest_file: Path) -> None:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise KnowledgeAtlasV2ArtifactError("manifest schema mismatch")
    run_id = str(manifest.get("run_id") or "")
    if not _RUN_ID_RE.fullmatch(run_id):
        raise KnowledgeAtlasV2ArtifactError("manifest run_id is invalid")
    if manifest_file.name != "manifest.json" or manifest_file.parent.name != run_id:
        raise KnowledgeAtlasV2ArtifactError("manifest path/run identity mismatch")
    if manifest.get("run_status") not in {"complete", "partial"}:
        raise KnowledgeAtlasV2ArtifactError(
            "Atlas V2 requires a terminal reader manifest"
        )
    if manifest.get("period_mode") not in {
        "completed_iso_week",
        "explicit_iso_week",
    }:
        raise KnowledgeAtlasV2ArtifactError(
            "Atlas V2 requires a completed or explicit ISO week"
        )


def _bound_v1_atlas_paths(
    manifest: Mapping[str, object], manifest_file: Path
) -> tuple[Path, Path]:
    stage = _mapping(_mapping(manifest.get("stages")).get("knowledge_atlas"))
    if stage.get("status") != SUCCEEDED:
        raise KnowledgeAtlasV2ArtifactError("manifest-bound V1 Atlas did not succeed")
    json_path = _bound_manifest_path(stage.get("json_path"), manifest_file.parent)
    html_path = _bound_manifest_path(stage.get("html_path"), manifest_file.parent)
    return json_path, html_path


def _bound_v1_brief_json_path(
    manifest: Mapping[str, object], manifest_file: Path
) -> Path:
    stage = _mapping(_mapping(manifest.get("stages")).get("weekly_brief"))
    if stage.get("status") != SUCCEEDED:
        raise KnowledgeAtlasV2ArtifactError("manifest-bound V1 Brief did not succeed")
    return _bound_manifest_path(stage.get("json_path"), manifest_file.parent)


def _bound_manifest_path(value: object, run_dir: Path) -> Path:
    text = str(value or "")
    if not text:
        raise KnowledgeAtlasV2ArtifactError("manifest artifact path is missing")
    lexical = Path(text).expanduser()
    if not lexical.is_absolute():
        lexical = run_dir / lexical
    return _canonical_existing_path(lexical, label="manifest artifact")


def _verify_stage_checksum(
    manifest: Mapping[str, object],
    stage_name: str,
    field: str,
    actual: str,
) -> None:
    stage = _mapping(_mapping(manifest.get("stages")).get(stage_name))
    expected = str(_mapping(stage.get("checksums")).get(field) or "")
    if not expected or actual != expected:
        raise KnowledgeAtlasV2ArtifactError(
            f"manifest checksum mismatch: {stage_name}.{field}"
        )


def _source_descriptor(path: Path, checksum: str, size: int) -> dict[str, object]:
    return {"path": str(path), "sha256": checksum, "size": size}


def _normalize_source_artifacts(
    value: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    copied = _json_copy(value, "source_artifacts")
    errors: list[str] = []
    if set(copied) != _SOURCE_ARTIFACT_KEYS:
        errors.append("source_artifacts keys mismatch")
    result: dict[str, dict[str, object]] = {}
    for name, descriptor in copied.items():
        if not isinstance(descriptor, Mapping):
            errors.append(f"source_artifacts.{name} must be an object")
            continue
        item = dict(descriptor)
        _validate_source_descriptor(item, f"source_artifacts.{name}", errors)
        result[str(name)] = item
    if errors:
        raise KnowledgeAtlasV2ValidationError(errors)
    return result


def _normalize_artifact_paths(value: Mapping[str, object]) -> dict[str, str]:
    copied = _json_copy(value, "artifact_paths")
    errors: list[str] = []
    if set(copied) != _ARTIFACT_PATH_KEYS:
        errors.append("artifact_paths keys mismatch")
    result: dict[str, str] = {}
    for name, raw in copied.items():
        text = str(raw or "")
        if not _safe_absolute_path_text(text):
            errors.append(f"artifact_paths.{name} must be absolute")
        result[str(name)] = text
    if len(result.values()) != len(set(result.values())):
        errors.append("artifact_paths must be duplicate-free")
    if errors:
        raise KnowledgeAtlasV2ValidationError(errors)
    return result


def _validate_source_descriptor(
    value: object,
    path: str,
    errors: list[str],
) -> None:
    descriptor = _mapping(value)
    _collect_exact(descriptor, {"path", "sha256", "size"}, path, errors)
    source_path = str(descriptor.get("path") or "")
    if not _safe_absolute_path_text(source_path):
        errors.append(f"{path}.path must be absolute")
    if not re.fullmatch(r"[0-9a-f]{64}", str(descriptor.get("sha256") or "")):
        errors.append(f"{path}.sha256 is invalid")
    _checked_positive_int(descriptor.get("size"), f"{path}.size", errors)


def _canonical_existing_path(value: str | Path | object, *, label: str) -> Path:
    try:
        lexical = Path(str(value)).expanduser().absolute()
        resolved = lexical.resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise KnowledgeAtlasV2ArtifactError(f"{label} path is invalid") from exc
    if lexical != resolved:
        raise KnowledgeAtlasV2ArtifactError(
            f"{label} path contains a symlink component"
        )
    return resolved


def _safe_absolute_path_text(value: object) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if re.search(r"[\x00-\x1f\x7f]", value):
        return False
    path = Path(value)
    return (
        path.is_absolute()
        and ".." not in path.parts
        and "." not in path.parts
        and str(path) == value
    )


def _require_contained_canonical(path: Path, roots: Sequence[Path]) -> None:
    resolved = _canonical_existing_path(path, label="source artifact")
    allowed = [Path(root).resolve(strict=True) for root in roots if Path(root).exists()]
    if not any(resolved.is_relative_to(root) for root in allowed):
        raise KnowledgeAtlasV2ArtifactError("source artifact escapes allowed roots")


def _reader_visible_word_count(html: str) -> int:
    from output.reader_value_quality import reader_visible_word_count

    return reader_visible_word_count(html)


def _period_from_manifest(manifest: Mapping[str, object]) -> dict[str, str]:
    return {
        "reporting_week": str(manifest.get("reporting_week") or ""),
        "analysis_period_start": str(manifest.get("analysis_period_start") or ""),
        "analysis_period_end": str(manifest.get("analysis_period_end") or ""),
    }


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _mapping_list_strict(
    value: object,
    path: str,
    errors: list[str],
    maximum: int,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > maximum or not all(
        isinstance(item, Mapping) for item in value
    ):
        errors.append(f"{path} must be a bounded object list")
        return []
    return [dict(item) for item in value]


def _json_copy(value: Mapping[str, object], label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise KnowledgeAtlasV2ValidationError([f"{label} must be an object"])
    try:
        result = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise KnowledgeAtlasV2ValidationError(
            [f"{label} must be finite JSON: {exc}"]
        ) from exc
    if not isinstance(result, dict):
        raise KnowledgeAtlasV2ValidationError([f"{label} must be an object"])
    return result


def _exact(value: Mapping[str, object], fields: set[str], path: str) -> None:
    actual = set(value)
    if actual != fields:
        raise KnowledgeAtlasV2ValidationError(
            [
                f"{path} fields mismatch: missing={sorted(fields - actual)}, "
                f"unknown={sorted(actual - fields)}"
            ]
        )


def _collect_exact(
    value: Mapping[str, object],
    fields: set[str],
    path: str,
    errors: list[str],
) -> None:
    actual = set(value)
    if actual != fields:
        errors.append(
            f"{path} fields mismatch: missing={sorted(fields - actual)}, "
            f"unknown={sorted(actual - fields)}"
        )


def _required_text(value: object, path: str) -> str:
    text = _plain_text(value)
    if not text or len(text) > 2_000:
        raise KnowledgeAtlasV2ValidationError([f"{path} is required and bounded"])
    return text


def _plain_text(value: object) -> str:
    return str(value).strip() if isinstance(value, (str, int, float)) else ""


def _safe_reader_text(
    value: object,
    *,
    russian: bool = False,
    maximum: int,
) -> bool:
    if not isinstance(value, str) or value != value.strip() or not value:
        return False
    if len(value) > maximum or re.search(r"[\x00-\x1f\x7f<>]", value):
        return False
    return not russian or _has_cyrillic(value)


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        rows: Sequence[object] = [value]
    elif isinstance(value, (list, tuple)):
        rows = value
    else:
        rows = []
    return _unique_text(str(item).strip() for item in rows if str(item).strip())


def _bounded_strings(
    value: object,
    path: str,
    errors: list[str],
    *,
    maximum: int,
) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum or not all(
        isinstance(item, str)
        and item
        and item == item.strip()
        and len(item) <= 2_000
        for item in value
    ):
        errors.append(f"{path} must be a bounded string list")
        return []
    if len(value) != len(set(value)):
        errors.append(f"{path} contains duplicates")
    return list(value)


def _unique_text(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _dedupe_objects(
    values: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        if key not in seen:
            seen.add(key)
            result.append(dict(value))
    return result


def _nonnegative_int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise KnowledgeAtlasV2ValidationError(["expected non-negative integer"])
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise KnowledgeAtlasV2ValidationError(
            ["expected non-negative integer"]
        ) from exc
    if result < 0 or isinstance(value, float) and not value.is_integer():
        raise KnowledgeAtlasV2ValidationError(["expected non-negative integer"])
    return result


def _positive_int(value: object, path: str) -> int:
    result = _nonnegative_int(value)
    if result <= 0:
        raise KnowledgeAtlasV2ValidationError([f"{path} must be positive"])
    return result


def _checked_nonnegative_int(
    value: object, path: str, errors: list[str]
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"{path} must be a non-negative integer")
        return 0
    return value


def _checked_positive_int(value: object, path: str, errors: list[str]) -> int:
    result = _checked_nonnegative_int(value, path, errors)
    if result <= 0:
        errors.append(f"{path} must be positive")
    return result


def _finite_score(
    value: object,
    *,
    default: float,
    maximum: float | None = 1.0,
) -> float:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        raise KnowledgeAtlasV2ValidationError(["expected finite score"])
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise KnowledgeAtlasV2ValidationError(["expected finite score"]) from exc
    if (
        not math.isfinite(result)
        or result < 0
        or maximum is not None
        and result > maximum
    ):
        raise KnowledgeAtlasV2ValidationError(["expected finite bounded score"])
    return result


def _source_urls(source: Mapping[str, object]) -> list[str]:
    direct = _strings(source.get("source_urls"))
    source_ref_strings = [
        str(item).strip()
        for item in source.get("source_refs") or []
        if isinstance(item, str) and str(item).strip()
    ] if isinstance(source.get("source_refs"), list) else []
    nested = [
        url
        for item in _mapping_list(source.get("source_refs"))
        for url in _strings(item.get("source_urls"))
    ]
    reference_urls = []
    for ref in source_ref_strings:
        try:
            scheme = urlsplit(ref).scheme.casefold()
        except ValueError:
            scheme = "invalid"
        if scheme in {"http", "https"} or scheme and scheme not in _REFERENCE_PREFIXES:
            reference_urls.append(ref)
    candidates = _unique_text([*direct, *nested, *reference_urls])
    if any(not _safe_http_url(ref) for ref in candidates):
        raise KnowledgeAtlasV2ValidationError(
            ["canonical thread contains an unsafe source URL"]
        )
    return candidates


def _safe_http_url(value: object) -> bool:
    text = str(value or "")
    if (
        not text
        or text != text.strip()
        or re.search(r"[\x00-\x20\x7f<>\"'\\]", text)
        or len(text) > 2_000
    ):
        return False
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError:
        return False
    decoded_path_segments = unquote(parsed.path).split("/")
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and (port is None or 1 <= port <= 65_535)
        and not any(segment in {".", ".."} for segment in decoded_path_segments)
    )


def _safe_reference(value: object) -> bool:
    text = str(value or "")
    if _safe_http_url(text):
        return True
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/#@+\-=]{0,299}", text):
        return False
    if ":" not in text:
        return False
    prefix, payload = text.split(":", maxsplit=1)
    if (
        prefix not in _REFERENCE_PREFIXES
        or not payload
        or len(payload) > 240
        or not re.fullmatch(r"[A-Za-z0-9@][A-Za-z0-9._/#@+\-=]{0,239}", payload)
    ):
        return False
    return not any(
        segment in {".", ".."} for segment in payload.split("/")
    )


def _reaction_for_thread(
    reaction: Mapping[str, object], slug: str
) -> tuple[int, list[str]]:
    if reaction.get("snapshot_status") != "complete":
        return 0, []
    target = f"canonical_thread:{slug}"
    audit_rows = [
        item
        for item in _mapping_list(reaction.get("eligible_thread_audit"))
        if item.get("canonical_thread_ref") == target
    ]
    rows = audit_rows or [
        item
        for item in [
            *_mapping_list(reaction.get("influenced_items")),
            *_mapping_list(reaction.get("linked_only_items")),
        ]
        if item.get("canonical_thread_ref") == target
    ]
    refs = _unique_text(
        ref
        for item in rows
        for ref in [
            *_strings(item.get("evidence_refs")),
            *_strings(item.get("source_refs")),
            *_strings(item.get("reacted_post_refs")),
        ]
        if _safe_reference(ref)
    )
    post_refs = _unique_text(
        ref for item in rows for ref in _strings(item.get("reacted_post_refs"))
    )
    event_count = len(post_refs) or max(
        (
            _nonnegative_int(
                item.get("reacted_post_count")
                if item.get("reacted_post_count") is not None
                else item.get("reaction_event_count"),
                default=0,
            )
            for item in rows
        ),
        default=0,
    )
    return event_count, refs


def _feedback_channel_status(editorial_input: Mapping[str, object]) -> str:
    reasons = _strings(
        _mapping(editorial_input.get("release_policy")).get("partial_reasons")
    )
    feedback_reasons = [reason for reason in reasons if reason.startswith("feedback_")]
    if any(
        marker in reason
        for reason in feedback_reasons
        for marker in (
            "not_usable",
            "cutoff_unbound",
            "cutoff_mismatch",
            "snapshot_unbound",
        )
    ):
        return "unavailable"
    return "partial" if feedback_reasons else "available"


def _feedback_count_for_thread(
    feedback: Mapping[str, object],
    feedback_permissions: Mapping[str, object],
    slug: str,
) -> int:
    markers = {
        f"canonical_thread:{slug}",
        f"thread:{slug}",
        f"idea_thread:{slug}",
    }
    confirmed_refs = {
        str(item.get("feedback_ref") or "")
        for key in ("applied_changes", "unchanged", "requires_code_or_config")
        for item in _mapping_list(feedback.get(key))
        if str(item.get("feedback_ref") or "")
    }
    return sum(
        1
        for item in _mapping_list(feedback_permissions.get("events"))
        if str(item.get("feedback_ref") or "") in confirmed_refs
        and str(item.get("target_ref") or "") in markers
    )


def _twelve_weeks(reporting_week: str) -> list[str]:
    if not _ISO_WEEK_RE.fullmatch(reporting_week):
        raise KnowledgeAtlasV2ValidationError(["reporting_week is invalid"])
    year, week = reporting_week.split("-W")
    try:
        current = datetime.fromisocalendar(int(year), int(week), 1)
    except ValueError as exc:
        raise KnowledgeAtlasV2ValidationError(
            ["reporting_week is invalid"]
        ) from exc
    return [
        f"{day.isocalendar().year:04d}-W{day.isocalendar().week:02d}"
        for day in (
            current - timedelta(weeks=offset)
            for offset in reversed(range(12))
        )
    ]


def _iso_week_for_timestamp(value: object) -> str:
    try:
        stamp = _parse_timestamp(value)
    except ValueError:
        return ""
    iso = stamp.isocalendar()
    return f"{iso.year:04d}-W{iso.week:02d}"


def _parse_timestamp(value: object) -> datetime:
    text = str(value or "")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    stamp = datetime.fromisoformat(text)
    if stamp.tzinfo is None:
        raise ValueError("timezone is required")
    return stamp.astimezone(timezone.utc)


def _safe_fragment(value: object) -> str:
    clean = re.sub(
        r"[^a-z0-9]+",
        "-",
        str(value or "").casefold(),
    ).strip("-")
    return clean[:96] or "thread"


def _normalize_text(value: object) -> str:
    return " ".join(
        re.sub(
            r"[^0-9a-zа-яё]+",
            " ",
            str(value or "").casefold(),
        ).split()
    )


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def _reject_duplicate_reader_text(
    values: Sequence[str],
    label: str,
    errors: list[str],
) -> None:
    normalized = [_normalize_text(value) for value in values]
    duplicates = sorted(
        {item for item in normalized if item and normalized.count(item) > 1}
    )
    if duplicates:
        errors.append(f"{label} values are duplicated")


def _has_cyrillic(value: object) -> bool:
    return re.search(r"[А-Яа-яЁё]", str(value or "")) is not None


def _e(value: object) -> str:
    return escape(str(value), quote=True)
