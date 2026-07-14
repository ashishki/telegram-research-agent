"""Strict reader projection for one manifest-bound MVP Radar result.

IRX-10 deliberately keeps Radar scoring and evidence gates in the sibling
producer.  This module only verifies the immutable IRX-2 handoff and translates
the producer result into a bounded reader contract.  A legacy JSON file remains
diagnostically readable, but an unbound file can never authorize an experiment
or build decision.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from output.ai_report_contract import (
    RADAR_GATE_SOURCE_TYPES,
    RADAR_INTELLIGENCE_CONTRACT_VERSION,
)
from output.weekly_run_manifest import (
    DISABLED,
    RADAR_BINDING_SCHEMA_VERSION,
    SUCCEEDED,
    RadarBindingError,
    WeeklyRunManifestError,
    validate_manifest,
    validate_radar_run_binding,
)


MVP_RADAR_READER_SCHEMA_VERSION = "mvp_radar_reader.v1"
SUPPORTED_RADAR_SCHEMA_VERSIONS = frozenset(
    {"mvp_of_week.v1", "demand_mvp_radar.mvp_of_week.v1"}
)

READER_STATES = frozenset(
    {
        "available",
        "no_candidate",
        "missing",
        "invalid",
        "disabled",
        "unbound_legacy",
    }
)
READER_DECISIONS = frozenset(
    {"investigate", "reject", "build_allowed", "unavailable"}
)
DOSSIER_STATUSES = frozenset(
    {"build", "focused_experiment", "investigate", "reject"}
)
RECOMMENDATIONS = frozenset(
    {
        "build",
        "existing_project_context",
        "focused_experiment",
        "investigate",
        "needs_more_evidence",
        "needs_more_specific_scope",
        "reject",
        "revisit_with_evidence_gap",
    }
)
EVIDENCE_KINDS = frozenset(
    {
        "repeated_complaint",
        "manual_workaround",
        "search_demand",
        "competitor_traction",
        "wtp_signal",
        "developer_issue",
        "negative_signal",
    }
)
KIR_GATE_STATUSES = frozenset(
    {
        "not_required",
        "passed",
        "missing_kir_thread",
        "stale_kir_thread",
        "missing_source_atoms",
        "missing_source_urls",
        "missing_decision_grade_external_evidence",
        "blocking_risk",
        "profile_mismatch",
        "missing_operator_fit",
    }
)

_NO_CANDIDATE_REASON_RU = (
    "Radar успешно завершил запуск, но не нашёл кандидата с достаточной исходной базой."
)
_NO_CANDIDATE_CHANGE_CONDITION = "Нужен новый набор пригодных opportunity seeds."
_NO_CANDIDATE_NEXT_VALIDATION = "Собрать пригодные seeds и повторить Radar."

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ISO_WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")
_SAFE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,299}$")
_SOURCE_TYPE_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_MAX_PROJECTION_BYTES = 160_000
_MAX_SEEDS = 256
_MAX_EXTERNAL = 24
_MAX_CONTEXT = 16
_MAX_KIR = 8
_MAX_MISSING = 24
_MAX_KILL = 8
_MAX_BOUND_JSON_BYTES = 4_000_000


class MvpRadarReaderError(ValueError):
    """Raised when Radar bytes cannot satisfy the strict reader contract."""


def load_bound_mvp_radar_reader(
    manifest: Mapping[str, Any],
    *,
    path_base: str | Path,
    allowed_roots: Sequence[str | Path] = (),
) -> dict[str, Any]:
    """Load one same-run projection or return an explicit fail-closed state."""

    try:
        return _load_bound_mvp_radar_reader(
            manifest,
            path_base=path_base,
            allowed_roots=allowed_roots,
        )
    except Exception as exc:
        return _unavailable_projection(
            {},
            reader_state="invalid",
            reasons=[
                "MVP Radar reader не смог безопасно разобрать связанный пакет: "
                + _safe_reason(exc)
            ],
        )


def _load_bound_mvp_radar_reader(
    manifest: Mapping[str, Any],
    *,
    path_base: str | Path,
    allowed_roots: Sequence[str | Path] = (),
) -> dict[str, Any]:
    """Internal loader; the public boundary above is guaranteed fail-closed."""

    manifest_map = manifest if isinstance(manifest, Mapping) else {}
    try:
        base = Path(path_base)
        roots = tuple(allowed_roots) or (base,)
    except (TypeError, ValueError) as exc:
        return _unavailable_projection(
            manifest_map,
            reader_state="invalid",
            reasons=[f"Manifest Radar path scope is invalid: {_safe_reason(exc)}"],
        )
    try:
        validate_manifest(
            manifest_map,
            path_base=base,
            allowed_roots=roots,
            check_artifact_existence=False,
        )
    except (
        WeeklyRunManifestError,
        TypeError,
        ValueError,
        RecursionError,
        OverflowError,
    ) as exc:
        return _unavailable_projection(
            manifest_map,
            reader_state="invalid",
            reasons=[f"Manifest Radar identity is invalid: {_safe_reason(exc)}"],
        )

    radar_stage = _mapping(_mapping(manifest_map.get("stages")).get("radar"))
    if radar_stage.get("status") == DISABLED or not _mapping(
        _mapping(manifest_map.get("stage_policy")).get("radar")
    ).get("enabled", True):
        return _unavailable_projection(
            manifest_map,
            reader_state="disabled",
            reasons=[
                "MVP Radar отключен для этого запуска. Решение по сборке не сформировано."
            ],
            partial=False,
        )
    if radar_stage.get("status") != SUCCEEDED:
        return _unavailable_projection(
            manifest_map,
            reader_state="missing",
            reasons=[
                "Связанный с запуском результат MVP Radar недоступен; пакет является частичным."
            ],
        )

    try:
        binding_path = _bound_path(base, radar_stage.get("binding_path"))
        binding_sha256 = _required_text(
            radar_stage.get("binding_sha256"), "Radar binding checksum", 64
        )
        binding = _load_json_object(
            binding_path,
            "Radar binding",
            expected_sha256=binding_sha256,
        )
        validate_radar_run_binding(
            binding,
            manifest=manifest_map,
            path_base=base,
            allowed_roots=roots,
            verify_files=False,
        )
        _validate_stage_binding_parity(radar_stage, binding)

        raw_ref = _mapping(binding.get("radar_json_ref"))
        seed_ref = _mapping(binding.get("seed_export_ref"))
        raw_path = _bound_path(base, raw_ref.get("path"))
        seed_path = _bound_path(base, seed_ref.get("path"))
        radar_payload = _load_json_object(
            raw_path,
            "Radar JSON",
            expected_sha256=_required_text(
                raw_ref.get("sha256"),
                "Radar JSON checksum",
                64,
            ),
        )
        seed_payload = _load_json_array(
            seed_path,
            "Radar seed export",
            expected_sha256=_required_text(
                seed_ref.get("sha256"),
                "Radar seed checksum",
                64,
            ),
        )
        projection = build_mvp_radar_reader_projection(
            manifest_map,
            binding=binding,
            radar_payload=radar_payload,
            seed_payload=seed_payload,
            binding_ref={
                "path": str(radar_stage.get("binding_path")),
                "sha256": binding_sha256,
            },
        )
        validate_mvp_radar_reader_projection(projection, manifest=manifest_map)
        return projection
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        MvpRadarReaderError,
        RadarBindingError,
        WeeklyRunManifestError,
        TypeError,
        ValueError,
        RecursionError,
        OverflowError,
    ) as exc:
        return _unavailable_projection(
            manifest_map,
            reader_state="invalid",
            reasons=[
                "Связанный с запуском результат MVP Radar не прошёл проверку целостности: "
                + _safe_reason(exc)
            ],
            artifact_ref=_artifact_ref_from_stage(radar_stage),
        )


def build_mvp_radar_reader_projection(
    manifest: Mapping[str, Any],
    *,
    binding: Mapping[str, Any],
    radar_payload: Mapping[str, Any],
    seed_payload: Sequence[object],
    binding_ref: Mapping[str, str] | None = None,
    _require_succeeded_stage: bool = True,
) -> dict[str, Any]:
    """Build a deterministic projection from already loaded immutable inputs."""

    if not isinstance(manifest, Mapping):
        raise MvpRadarReaderError("Radar manifest must be an object")
    if not isinstance(binding, Mapping):
        raise MvpRadarReaderError("Radar binding must be an object")
    if not isinstance(radar_payload, Mapping):
        raise MvpRadarReaderError("Radar JSON must be an object")
    if (
        not isinstance(seed_payload, Sequence)
        or isinstance(seed_payload, (str, bytes, bytearray, Mapping))
    ):
        raise MvpRadarReaderError("Radar seed export must be an array")
    if len(seed_payload) > _MAX_SEEDS:
        raise MvpRadarReaderError("Radar seed export exceeds the bounded reader limit")
    input_shape = {"max_nodes": 60_000, "max_depth": 20, "max_text": 16_384}
    _validate_json_shape(manifest, "Radar manifest", **input_shape)
    _validate_json_shape(binding, "Radar binding", **input_shape)
    _validate_json_shape(radar_payload, "Radar JSON", **input_shape)
    _validate_json_shape(list(seed_payload), "Radar seed export", **input_shape)
    try:
        validate_manifest(manifest)
        validate_radar_run_binding(binding, manifest=manifest, verify_files=False)
    except (
        WeeklyRunManifestError,
        TypeError,
        ValueError,
        RecursionError,
        OverflowError,
    ) as exc:
        raise MvpRadarReaderError(str(exc)) from exc
    if binding.get("radar_contract_version") != RADAR_INTELLIGENCE_CONTRACT_VERSION:
        raise MvpRadarReaderError("unsupported Radar intelligence contract version")
    if binding.get("radar_schema_version") not in SUPPORTED_RADAR_SCHEMA_VERSIONS:
        raise MvpRadarReaderError("unsupported Radar JSON schema version")
    if radar_payload.get("schema_version") != binding.get("radar_schema_version"):
        raise MvpRadarReaderError("Radar JSON schema does not match the binding")
    raw_contract = radar_payload.get("contract_version")
    if raw_contract not in (None, binding.get("radar_contract_version")):
        raise MvpRadarReaderError("Radar JSON contract does not match the binding")
    _validate_seed_period(seed_payload, manifest)
    if binding_ref is None:
        radar_stage = _mapping(_mapping(manifest.get("stages")).get("radar"))
        if radar_stage.get("binding_path") and radar_stage.get("binding_sha256"):
            binding_ref = {
                "path": str(radar_stage.get("binding_path")),
                "sha256": str(radar_stage.get("binding_sha256")),
            }

    result = _required_mapping(radar_payload.get("result"), "Radar result")
    radar_run_id = _required_ref(result.get("run_id"), "Radar result.run_id")
    if radar_run_id != binding.get("radar_run_id"):
        raise MvpRadarReaderError("Radar result.run_id does not match the binding")
    raw_status = _required_text(result.get("status"), "Radar result.status", 80)
    if raw_status not in {"selected", "no_evidence", "no_candidate"}:
        raise MvpRadarReaderError("unsupported Radar result status")
    _validate_status_projection(binding, result)

    raw_selected_value = radar_payload.get("selected")
    selected = (
        _required_mapping(raw_selected_value, "Radar selected candidate")
        if raw_selected_value is not None
        else None
    )
    bound_selected = binding.get("selected_candidate")
    if bound_selected != raw_selected_value:
        raise MvpRadarReaderError("binding selected_candidate differs from Radar JSON")
    if (raw_status == "selected") != (selected is not None):
        raise MvpRadarReaderError("Radar selected status contradicts the selected candidate")
    if selected is None:
        for field in (
            "selected_title",
            "dossier_status",
            "recommendation",
            "score",
            "selected_source_mix",
        ):
            if result.get(field) is not None:
                raise MvpRadarReaderError(
                    f"no-candidate Radar result has contradictory {field}"
                )
        projection = _no_candidate_projection(
            manifest,
            binding=binding,
            radar_status=raw_status,
            binding_ref=binding_ref,
        )
        validate_mvp_radar_reader_projection(
            projection,
            manifest=manifest,
            _require_succeeded_stage=_require_succeeded_stage,
        )
        return projection

    candidate = _candidate_projection(selected, result, radar_run_id=radar_run_id)
    title = candidate["title"]
    candidate_key = str(candidate["candidate_id"]).removeprefix("candidate:")
    source_mix = _required_mapping(selected.get("source_mix"), "selected.source_mix")
    if result.get("selected_source_mix") != selected.get("source_mix"):
        raise MvpRadarReaderError("Radar result/selected source mix mismatch")

    matches = _consistent_external_evidence(radar_payload, result, selected)
    normalized_matches = [
        _normalize_external_evidence(item, candidate_title=title)
        for item in matches[:_MAX_EXTERNAL]
    ]
    if len(matches) > _MAX_EXTERNAL:
        raise MvpRadarReaderError("matched external evidence exceeds the reader limit")
    gate_proof = [item for item in normalized_matches if item["gate_eligible"]]
    bound_seed_count = _candidate_seed_count(seed_payload, candidate_key=candidate_key)
    _validate_source_mix(
        source_mix,
        gate_proof,
        bound_candidate_seed_count=bound_seed_count,
    )

    kir = _matched_kir_provenance(
        seed_payload,
        candidate_key=candidate_key,
        source_mix=source_mix,
        analysis_period_end=str(manifest.get("analysis_period_end") or ""),
    )
    context, decision_context = _normalize_context(radar_payload.get("decision_context"))
    missing_categories = _consistent_missing_categories(radar_payload, result, selected)
    missing = _missing_evidence(selected, missing_categories)
    validation_queries = _consistent_mapping(
        "validation_queries",
        radar_payload.get("validation_queries"),
        selected.get("validation_queries"),
        allow_empty=False,
    )
    decision_change = _consistent_mapping(
        "decision_change_action",
        radar_payload.get("decision_change_action"),
        result.get("decision_change_action"),
        selected.get("decision_change_action"),
        allow_empty=False,
    )
    next_query = _next_query(decision_change, validation_queries)
    _validate_decision_change(
        decision_change,
        gate_proof,
        next_query,
        dossier_status=candidate["dossier_status"],
    )

    reader_decision = _reader_decision(candidate, source_mix, gate_proof)
    decision_reason = _required_text(
        selected.get("decision_reason"), "selected.decision_reason", 160
    )
    kill_criteria = _text_list(
        selected.get("kill_criteria"),
        "selected.kill_criteria",
        limit=_MAX_KILL,
        item_limit=500,
        required=True,
    )
    next_experiment = _text_list(
        selected.get("next_experiment"),
        "selected.next_experiment",
        limit=8,
        item_limit=500,
        required=True,
    )
    change_condition = _reader_change_condition(
        reader_decision=reader_decision,
        dossier_status=candidate["dossier_status"],
        source_mix=source_mix,
        gate_proof=gate_proof,
        missing_evidence=missing,
    )
    next_validation = _reader_next_validation(
        next_query,
        reader_decision=reader_decision,
        source_mix=source_mix,
        gate_proof=gate_proof,
    )
    safe_decision_change = copy.deepcopy(dict(decision_change))
    safe_decision_change["producer_required_gate_change"] = decision_change.get(
        "required_gate_change"
    )
    safe_decision_change["producer_next_validation_action"] = decision_change.get(
        "next_validation_action"
    )
    safe_decision_change["producer_context_only_results_rule"] = decision_change.get(
        "context_only_results_rule"
    )
    safe_decision_change["required_gate_change"] = change_condition
    safe_decision_change["next_validation_action"] = next_validation
    safe_decision_change["context_only_results_rule"] = _reader_context_rule()

    projection = {
        "schema_version": MVP_RADAR_READER_SCHEMA_VERSION,
        "contract_version": RADAR_INTELLIGENCE_CONTRACT_VERSION,
        "reader_state": "available",
        "candidate_state": "selected",
        "status": raw_status,
        "snapshot_status": "complete",
        "partial": False,
        "partial_reasons": [],
        **_identity_projection(manifest, radar_run_id=radar_run_id),
        "artifact_ref": _artifact_ref(binding, binding_ref),
        "source_path": str(_mapping(binding.get("radar_json_ref")).get("path") or ""),
        "selected_candidate": title,
        "candidate": candidate,
        "dossier_status": candidate["dossier_status"],
        "recommendation": candidate["recommendation"],
        "score": candidate["score"],
        "reader_decision": reader_decision,
        "decision_reason": decision_reason,
        "decision_reason_ru": _decision_reason_ru(
            reader_decision,
            dossier_status=candidate["dossier_status"],
            proof_count=len(gate_proof),
        ),
        "source_mix": copy.deepcopy(dict(source_mix)),
        "bound_candidate_seed_count": bound_seed_count,
        "matched_kir_provenance": kir,
        "matched_external_evidence": normalized_matches,
        "matched_external_proof": gate_proof,
        "unmatched_context": context,
        "decision_context": decision_context,
        "missing_evidence": missing,
        "missing_evidence_by_category": missing_categories,
        "validation_queries": copy.deepcopy(dict(validation_queries)),
        "decision_change_action": safe_decision_change,
        "change_condition": change_condition,
        "next_validation_query": next_query,
        "next_validation": next_validation,
        "next_experiment": next_experiment,
        "kill_criteria": kill_criteria,
        "evidence_policy": _evidence_policy(),
    }
    validate_mvp_radar_reader_projection(
        projection,
        manifest=manifest,
        _require_succeeded_stage=_require_succeeded_stage,
    )
    return projection


def adapt_legacy_mvp_radar_payload(
    payload: Mapping[str, Any],
    *,
    source_path: str | Path | None,
    expected_week: str,
) -> dict[str, Any]:
    """Read a V1/unbound file as diagnostic context without decision authority."""

    if not isinstance(payload, Mapping):
        raise MvpRadarReaderError("Legacy Radar payload must be an object")
    if not isinstance(expected_week, str):
        raise MvpRadarReaderError("Expected Radar week must be text")
    _validate_json_shape(
        payload,
        "legacy Radar payload",
        max_nodes=60_000,
        max_depth=20,
        max_text=16_384,
    )
    _validate_utf8_text(expected_week, "expected Radar week")
    reported_week = str(
        payload.get("reporting_week") or payload.get("week_label") or ""
    ).strip()
    if reported_week and reported_week != expected_week:
        return _legacy_unavailable(
            expected_week,
            source_path=source_path,
            reason=(
                f"Radar JSON относится к {reported_week}, а запрошен {expected_week}; "
                "решение недоступно."
            ),
        )

    result = _mapping(payload.get("result"))
    selected = _mapping(payload.get("selected"))
    title = _first_text(
        result.get("selected_title"),
        selected.get("title"),
        payload.get("selected_candidate"),
        payload.get("selected_title"),
    )
    dossier_status = _first_text(
        result.get("dossier_status"),
        selected.get("dossier_status"),
        payload.get("dossier_status"),
    )
    recommendation = _first_text(
        result.get("recommendation"),
        selected.get("recommendation"),
        payload.get("recommendation"),
    )
    score = _optional_score(
        _first_present(result, selected, payload, field="score"), "legacy score"
    )
    raw_status = _first_text(payload.get("status"), result.get("status")) or "loaded"
    missing = _legacy_texts(
        selected.get("missing_evidence")
        or result.get("missing_evidence")
        or payload.get("missing_evidence")
    )
    kill = _legacy_texts(
        selected.get("kill_criteria")
        or result.get("kill_criteria")
        or payload.get("kill_criteria")
    )
    source_mix = _first_mapping_value(
        result.get("selected_source_mix"),
        selected.get("source_mix"),
        payload.get("source_mix"),
    )
    candidate = None
    if title:
        candidate_id = _first_text(selected.get("candidate_id")) or (
            "candidate:legacy-" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:24]
        )
        candidate = {
            "candidate_id": candidate_id,
            "candidate_id_source": (
                "producer" if selected.get("candidate_id") else "legacy_title_hash"
            ),
            "title": title,
            "dossier_status": dossier_status or "investigate",
            "recommendation": recommendation or "needs_more_evidence",
            "confidence": _first_text(selected.get("confidence")),
            "score": score,
        }
    projection = {
        "schema_version": MVP_RADAR_READER_SCHEMA_VERSION,
        "contract_version": RADAR_INTELLIGENCE_CONTRACT_VERSION,
        "reader_state": "unbound_legacy",
        "candidate_state": "untrusted_legacy" if candidate else "unknown_due_to_unavailable_radar",
        "status": raw_status,
        "snapshot_status": "failed",
        "partial": True,
        "partial_reasons": [
            "Legacy Radar JSON не связан с manifest этого запуска; он показан только для диагностики."
        ],
        "manifest_run_id": "",
        "radar_run_id": _first_text(result.get("run_id")),
        "reporting_week": expected_week,
        "analysis_period_start": "",
        "analysis_period_end": "",
        "artifact_ref": {
            "radar_json_path": str(source_path or ""),
            "radar_json_sha256": "",
            "binding_schema_version": "",
            "binding_path": "",
            "binding_sha256": "",
        },
        "source_path": str(source_path or ""),
        "selected_candidate": title or None,
        "candidate": candidate,
        "dossier_status": dossier_status or None,
        "recommendation": recommendation or "needs_more_evidence",
        "score": score,
        "reader_decision": "unavailable",
        "decision_reason": _first_text(selected.get("decision_reason"))
        or "legacy_unbound",
        "decision_reason_ru": (
            "Несвязанный legacy-артефакт не даёт права на эксперимент или сборку."
        ),
        "source_mix": source_mix,
        "bound_candidate_seed_count": 0,
        "matched_kir_provenance": [],
        "matched_external_evidence": [],
        "matched_external_proof": [],
        "unmatched_context": [],
        "decision_context": {},
        "missing_evidence": missing
        or ["Нужен manifest-bound Radar JSON для этого запуска."],
        "missing_evidence_by_category": {},
        "validation_queries": _first_mapping_value(
            selected.get("validation_queries"), payload.get("validation_queries")
        ),
        "decision_change_action": _first_mapping_value(
            selected.get("decision_change_action"),
            payload.get("decision_change_action"),
            result.get("decision_change_action"),
        ),
        "change_condition": "Нужен валидный same-run Radar binding.",
        "next_validation_query": None,
        "next_validation": "Повторить Radar в составе нового weekly run.",
        "next_experiment": [],
        "kill_criteria": kill,
        "evidence_policy": _evidence_policy(),
    }
    validate_mvp_radar_reader_projection(projection)
    return projection


def missing_mvp_radar_projection(
    expected_week: str,
    *,
    source_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return an explicit missing state for a non-orchestrated V1 reader."""

    return _unavailable_projection(
        {"run_id": "", "reporting_week": expected_week},
        reader_state="missing",
        reasons=[
            "MVP Radar JSON для запрошенного периода недоступен; решение не сформировано."
        ],
        artifact_ref={
            **_empty_artifact_ref(),
            "radar_json_path": str(source_path or ""),
        },
    )


def invalid_mvp_radar_projection(
    expected_week: str,
    *,
    source_path: str | Path | None = None,
    reason: str = "MVP Radar JSON не прошёл проверку reader-контракта.",
) -> dict[str, Any]:
    """Return an explicit fail-closed state for malformed unbound Radar JSON."""

    return _legacy_unavailable(
        expected_week,
        source_path=source_path,
        reason=reason,
    )


def load_unbound_mvp_radar_reader(
    path: str | Path,
    *,
    expected_week: str,
) -> dict[str, Any]:
    """Load bounded legacy JSON as diagnostic-only reader context."""

    try:
        source_path = Path(path)
        payload = _load_json_object(source_path, "Legacy Radar JSON")
        return adapt_legacy_mvp_radar_payload(
            payload,
            source_path=source_path,
            expected_week=expected_week,
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        RecursionError,
        OverflowError,
    ) as exc:
        return invalid_mvp_radar_projection(
            expected_week,
            source_path=path,
            reason=f"MVP Radar JSON недействителен: {_safe_reason(exc)}",
        )


def validate_mvp_radar_reader_projection(
    projection: Mapping[str, Any],
    *,
    manifest: Mapping[str, Any] | None = None,
    _require_succeeded_stage: bool = True,
) -> None:
    """Validate reader authority, bounds, and identity without mutating input."""

    if not isinstance(projection, Mapping):
        raise MvpRadarReaderError("Radar reader projection must be an object")
    _validate_json_shape(projection, "projection")
    if projection.get("schema_version") != MVP_RADAR_READER_SCHEMA_VERSION:
        raise MvpRadarReaderError("unsupported Radar reader schema")
    if projection.get("contract_version") != RADAR_INTELLIGENCE_CONTRACT_VERSION:
        raise MvpRadarReaderError("unsupported Radar reader contract")
    state = projection.get("reader_state")
    if not isinstance(state, str) or state not in READER_STATES:
        raise MvpRadarReaderError("invalid Radar reader state")
    if (
        state in {"available", "no_candidate"}
        and manifest is None
        and _require_succeeded_stage
    ):
        raise MvpRadarReaderError(
            "authoritative Radar reader requires the current run manifest"
        )
    decision = projection.get("reader_decision")
    if not isinstance(decision, str) or decision not in READER_DECISIONS:
        raise MvpRadarReaderError("invalid Radar reader decision")
    for field in ("partial",):
        if not isinstance(projection.get(field), bool):
            raise MvpRadarReaderError(f"{field} must be boolean")
    partial_reasons = _text_list(
        projection.get("partial_reasons"),
        "partial_reasons",
        limit=12,
        item_limit=600,
        required=False,
    )
    if bool(projection.get("partial")) != bool(partial_reasons):
        raise MvpRadarReaderError("partial state/reasons mismatch")
    if not isinstance(projection.get("snapshot_status"), str) or projection.get(
        "snapshot_status"
    ) not in {"complete", "failed"}:
        raise MvpRadarReaderError("invalid Radar snapshot status")
    candidate = projection.get("candidate")
    if candidate is not None and not isinstance(candidate, Mapping):
        raise MvpRadarReaderError("Radar candidate must be an object or null")
    if state == "available":
        if not isinstance(candidate, Mapping) or not projection.get("selected_candidate"):
            raise MvpRadarReaderError("available Radar projection requires a candidate")
        if projection.get("partial") or projection.get("snapshot_status") != "complete":
            raise MvpRadarReaderError("available Radar projection cannot be partial")
        title = _required_text(candidate.get("title"), "candidate.title", 300)
        _required_candidate_id(candidate.get("candidate_id"), title=title)
        if title != projection.get("selected_candidate"):
            raise MvpRadarReaderError("candidate title projection mismatch")
        if not isinstance(candidate.get("dossier_status"), str) or candidate.get(
            "dossier_status"
        ) not in DOSSIER_STATUSES:
            raise MvpRadarReaderError("invalid candidate dossier status")
        if not isinstance(candidate.get("recommendation"), str) or candidate.get(
            "recommendation"
        ) not in RECOMMENDATIONS:
            raise MvpRadarReaderError("invalid candidate recommendation")
        _validate_available_projection(projection, candidate)
    elif state in {"missing", "invalid", "disabled", "no_candidate"}:
        if candidate is not None or projection.get("selected_candidate") is not None:
            raise MvpRadarReaderError("unavailable/no-candidate state cannot expose a candidate")
        if decision != "unavailable":
            raise MvpRadarReaderError("unavailable/no-candidate state cannot grant authority")
        if state == "no_candidate":
            _validate_no_candidate_projection(projection)
        else:
            _validate_unavailable_projection(projection)
            if state == "disabled":
                if (
                    projection.get("partial") is not False
                    or projection.get("snapshot_status") != "failed"
                    or partial_reasons
                ):
                    raise MvpRadarReaderError("disabled Radar state is inconsistent")
            elif (
                projection.get("partial") is not True
                or projection.get("snapshot_status") != "failed"
                or not partial_reasons
            ):
                raise MvpRadarReaderError(
                    "unavailable Radar state must remain explicitly partial"
                )
    elif state == "unbound_legacy":
        if decision != "unavailable":
            raise MvpRadarReaderError("unbound legacy Radar cannot grant authority")
        if (
            projection.get("partial") is not True
            or projection.get("snapshot_status") != "failed"
            or not partial_reasons
        ):
            raise MvpRadarReaderError("unbound legacy Radar must remain explicitly partial")

    artifact_ref = _required_mapping(projection.get("artifact_ref"), "artifact_ref")
    _validate_artifact_ref(artifact_ref, authoritative=state in {"available", "no_candidate"})
    if state in {"available", "no_candidate"} and projection.get(
        "source_path"
    ) != artifact_ref.get("radar_json_path"):
        raise MvpRadarReaderError("Radar source/artifact path mismatch")

    policy = _required_mapping(projection.get("evidence_policy"), "evidence_policy")
    if (
        policy.get("context_only_can_satisfy_gate") is not False
        or policy.get("market_context_can_satisfy_gate") is not False
        or policy.get("unbound_legacy_can_authorize") is not False
        or policy.get("negative_signal_can_satisfy_gate") is not False
        or policy.get("x_can_satisfy_gate") is not False
    ):
        raise MvpRadarReaderError("Radar evidence policy weakens a gate")
    matches = projection.get("matched_external_evidence")
    if not isinstance(matches, list) or len(matches) > _MAX_EXTERNAL:
        raise MvpRadarReaderError("matched_external_evidence must be bounded")
    proof = projection.get("matched_external_proof")
    if not isinstance(proof, list) or len(proof) > _MAX_EXTERNAL:
        raise MvpRadarReaderError("matched_external_proof must be bounded")
    for item in proof:
        if not isinstance(item, Mapping) or not _projection_gate_eligible(item):
            raise MvpRadarReaderError("gate proof contains an ineligible record")
    if state != "available" and (matches or proof):
        raise MvpRadarReaderError("non-authoritative Radar state contains external proof")
    context = projection.get("unmatched_context")
    if not isinstance(context, list) or len(context) > _MAX_CONTEXT:
        raise MvpRadarReaderError("unmatched context must be bounded")
    for item in context:
        if (
            not isinstance(item, Mapping)
            or item.get("context_only") is not True
            or item.get("build_ready_evidence") is not False
            or item.get("source_gate_satisfied") is not False
        ):
            raise MvpRadarReaderError("unmatched context contradicts gate policy")
    _text_list(
        projection.get("missing_evidence"),
        "missing_evidence",
        limit=_MAX_MISSING,
        item_limit=600,
        required=False,
    )
    _text_list(
        projection.get("kill_criteria"),
        "kill_criteria",
        limit=_MAX_KILL,
        item_limit=500,
        required=False,
    )
    if manifest is not None and state in {"available", "no_candidate"}:
        if not isinstance(manifest, Mapping):
            raise MvpRadarReaderError("Radar manifest must be an object")
        try:
            validate_manifest(manifest)
        except (
            WeeklyRunManifestError,
            TypeError,
            ValueError,
            RecursionError,
            OverflowError,
        ) as exc:
            raise MvpRadarReaderError(str(exc)) from exc
        expected = _identity_projection(
            manifest, radar_run_id=str(projection.get("radar_run_id") or "")
        )
        if any(projection.get(key) != value for key, value in expected.items()):
            raise MvpRadarReaderError("Radar reader/manifest identity mismatch")
        stage = _mapping(_mapping(manifest.get("stages")).get("radar"))
        if _require_succeeded_stage and stage.get("status") != SUCCEEDED:
            raise MvpRadarReaderError(
                "authoritative Radar reader requires a succeeded manifest stage"
            )
        stage_run_id = stage.get("radar_run_id")
        if stage_run_id not in (None, projection.get("radar_run_id")):
            raise MvpRadarReaderError("Radar reader/stage run identity mismatch")
        if stage.get("status") == SUCCEEDED:
            parity = {
                "radar_json_path": stage.get("artifact_path"),
                "radar_json_sha256": stage.get("artifact_sha256"),
                "binding_path": stage.get("binding_path"),
                "binding_sha256": stage.get("binding_sha256"),
            }
            if any(artifact_ref.get(key) != value for key, value in parity.items()):
                raise MvpRadarReaderError("Radar reader/stage artifact identity mismatch")
    try:
        encoded = json.dumps(
            projection, ensure_ascii=False, sort_keys=True, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise MvpRadarReaderError("Radar reader projection is not JSON-safe") from exc
    if len(encoded) > _MAX_PROJECTION_BYTES:
        raise MvpRadarReaderError("Radar reader projection exceeds byte limit")


def _validate_json_shape(
    value: object,
    field: str,
    *,
    max_nodes: int = 4_000,
    max_depth: int = 12,
    max_text: int = 4_000,
) -> None:
    node_count = 0
    active: set[int] = set()

    def visit(item: object, path: str, depth: int) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > max_nodes or depth > max_depth:
            raise MvpRadarReaderError(f"{field} exceeds structural bounds")
        if item is None or isinstance(item, (bool, int)):
            return
        if isinstance(item, float):
            if not math.isfinite(item):
                raise MvpRadarReaderError(f"{path} contains a non-finite number")
            return
        if isinstance(item, str):
            if len(item) > max_text or _CONTROL_RE.search(item):
                raise MvpRadarReaderError(f"{path} contains unsafe text")
            _validate_utf8_text(item, path)
            return
        if isinstance(item, Mapping):
            if len(item) > 256 or id(item) in active:
                raise MvpRadarReaderError(f"{path} contains an invalid object graph")
            active.add(id(item))
            try:
                for key, child in item.items():
                    if not isinstance(key, str) or not key or len(key) > 160:
                        raise MvpRadarReaderError(f"{path} contains an invalid key")
                    visit(child, f"{path}.{key}", depth + 1)
            finally:
                active.remove(id(item))
            return
        if isinstance(item, list):
            if len(item) > 256 or id(item) in active:
                raise MvpRadarReaderError(f"{path} contains an invalid array graph")
            active.add(id(item))
            try:
                for index, child in enumerate(item):
                    visit(child, f"{path}[{index}]", depth + 1)
            finally:
                active.remove(id(item))
            return
        raise MvpRadarReaderError(f"{path} is not JSON-compatible")

    visit(value, field, 0)


def _validate_available_projection(
    projection: Mapping[str, Any], candidate: Mapping[str, Any]
) -> None:
    if projection.get("candidate_state") != "selected" or projection.get("status") != "selected":
        raise MvpRadarReaderError("available Radar projection has invalid candidate state")
    if candidate.get("candidate_id_source") != "producer":
        raise MvpRadarReaderError("available Radar candidate lacks producer identity")
    _validate_authoritative_identity(projection)
    _required_text(candidate.get("confidence"), "candidate.confidence", 80)
    _optional_score(candidate.get("score"), "candidate.score")
    radar_run_id = _required_ref(projection.get("radar_run_id"), "radar_run_id")
    if candidate.get("radar_run_id") != radar_run_id:
        raise MvpRadarReaderError("candidate/Radar run identity mismatch")
    if (
        projection.get("dossier_status") != candidate.get("dossier_status")
        or projection.get("recommendation") != candidate.get("recommendation")
        or projection.get("score") != candidate.get("score")
    ):
        raise MvpRadarReaderError("candidate/top-level projection mismatch")

    matches = projection.get("matched_external_evidence")
    proof = projection.get("matched_external_proof")
    if not isinstance(matches, list) or not isinstance(proof, list):
        raise MvpRadarReaderError("available Radar evidence must be lists")
    expected_proof = []
    for item in matches:
        if not isinstance(item, Mapping):
            raise MvpRadarReaderError("matched external evidence contains a non-object")
        _validate_normalized_external_evidence(
            item, candidate_title=str(candidate.get("title") or "")
        )
        if item.get("gate_eligible") is True:
            expected_proof.append(item)
    if proof != expected_proof:
        raise MvpRadarReaderError("gate proof differs from normalized matched evidence")

    source_mix = _required_mapping(projection.get("source_mix"), "source_mix")
    bound_seed_count = projection.get("bound_candidate_seed_count")
    if (
        not isinstance(bound_seed_count, int)
        or isinstance(bound_seed_count, bool)
        or not 0 <= bound_seed_count <= _MAX_SEEDS
    ):
        raise MvpRadarReaderError("bound candidate seed count must be an integer")
    _validate_source_mix(
        source_mix,
        proof,
        bound_candidate_seed_count=bound_seed_count,
    )
    expected_decision = _reader_decision(candidate, source_mix, proof)
    if projection.get("reader_decision") != expected_decision:
        raise MvpRadarReaderError("Radar reader decision contradicts verified gates")
    _validate_kir_projection(
        projection.get("matched_kir_provenance"),
        source_mix,
        analysis_period_end=str(projection.get("analysis_period_end") or ""),
    )
    _required_text(projection.get("decision_reason"), "decision_reason", 160)
    _required_text(projection.get("decision_reason_ru"), "decision_reason_ru", 1000)
    _text_list(
        projection.get("next_experiment"),
        "next_experiment",
        limit=8,
        item_limit=500,
        required=True,
    )
    _text_list(
        projection.get("kill_criteria"),
        "kill_criteria",
        limit=_MAX_KILL,
        item_limit=500,
        required=True,
    )
    _required_mapping(
        projection.get("missing_evidence_by_category"),
        "missing_evidence_by_category",
    )
    validation_queries = _required_mapping(
        projection.get("validation_queries"), "validation_queries"
    )
    if not validation_queries:
        raise MvpRadarReaderError("available Radar validation queries are missing")
    decision_change = _required_mapping(
        projection.get("decision_change_action"), "decision_change_action"
    )
    if not decision_change:
        raise MvpRadarReaderError("available Radar decision-change action is missing")
    next_query = _next_query(decision_change, validation_queries)
    _validate_decision_change(
        decision_change,
        proof,
        next_query,
        dossier_status=str(candidate.get("dossier_status") or ""),
    )
    if projection.get("next_validation_query") != next_query:
        raise MvpRadarReaderError("Radar next validation query projection mismatch")
    safe_change = _reader_change_condition(
        reader_decision=expected_decision,
        dossier_status=str(candidate.get("dossier_status") or ""),
        source_mix=source_mix,
        gate_proof=proof,
        missing_evidence=_text_list(
            projection.get("missing_evidence"),
            "missing_evidence",
            limit=_MAX_MISSING,
            item_limit=600,
            required=False,
        ),
    )
    safe_next = _reader_next_validation(
        next_query,
        reader_decision=expected_decision,
        source_mix=source_mix,
        gate_proof=proof,
    )
    if (
        projection.get("change_condition") != safe_change
        or projection.get("next_validation") != safe_next
        or decision_change.get("required_gate_change") != safe_change
        or decision_change.get("next_validation_action") != safe_next
        or decision_change.get("context_only_results_rule")
        != _reader_context_rule()
    ):
        raise MvpRadarReaderError("Radar decision-change text projection mismatch")
    _validate_decision_context_projection(
        projection.get("decision_context"), projection.get("unmatched_context")
    )


def _validate_no_candidate_projection(projection: Mapping[str, Any]) -> None:
    status = projection.get("status")
    if (
        projection.get("candidate_state") != "no_candidate"
        or not isinstance(status, str)
        or status not in {"no_evidence", "no_candidate"}
        or projection.get("partial") is not False
        or projection.get("snapshot_status") != "complete"
    ):
        raise MvpRadarReaderError("no-candidate Radar projection is inconsistent")
    expected_scalars = {
        "selected_candidate": None,
        "candidate": None,
        "dossier_status": None,
        "recommendation": None,
        "score": None,
        "reader_decision": "unavailable",
        "decision_reason": "no_candidate",
        "decision_reason_ru": _NO_CANDIDATE_REASON_RU,
        "bound_candidate_seed_count": 0,
        "next_validation_query": None,
        "change_condition": _NO_CANDIDATE_CHANGE_CONDITION,
        "next_validation": _NO_CANDIDATE_NEXT_VALIDATION,
    }
    if any(projection.get(field) != expected for field, expected in expected_scalars.items()):
        raise MvpRadarReaderError("no-candidate Radar projection contains candidate fiction")
    for field in (
        "source_mix",
        "decision_context",
        "missing_evidence_by_category",
        "validation_queries",
        "decision_change_action",
    ):
        if projection.get(field) != {}:
            raise MvpRadarReaderError("no-candidate Radar projection contains invented state")
    for field in (
        "matched_kir_provenance",
        "matched_external_evidence",
        "matched_external_proof",
        "unmatched_context",
        "next_experiment",
        "kill_criteria",
    ):
        if projection.get(field) != []:
            raise MvpRadarReaderError("no-candidate Radar projection contains invented evidence")
    if projection.get("missing_evidence") != [
        "Нет выбранного кандидата для проверки."
    ]:
        raise MvpRadarReaderError("no-candidate missing-evidence projection is invalid")
    _validate_authoritative_identity(projection)


def _validate_unavailable_projection(projection: Mapping[str, Any]) -> None:
    expected_scalars = {
        "selected_candidate": None,
        "candidate": None,
        "dossier_status": None,
        "recommendation": None,
        "score": None,
        "reader_decision": "unavailable",
        "bound_candidate_seed_count": 0,
        "next_validation_query": None,
    }
    if any(projection.get(field) != expected for field, expected in expected_scalars.items()):
        raise MvpRadarReaderError("unavailable Radar projection contains candidate fiction")
    for field in (
        "source_mix",
        "decision_context",
        "missing_evidence_by_category",
        "validation_queries",
        "decision_change_action",
    ):
        if projection.get(field) != {}:
            raise MvpRadarReaderError("unavailable Radar projection contains invented state")
    for field in (
        "matched_kir_provenance",
        "matched_external_evidence",
        "matched_external_proof",
        "unmatched_context",
        "next_experiment",
        "kill_criteria",
    ):
        if projection.get(field) != []:
            raise MvpRadarReaderError("unavailable Radar projection contains invented evidence")


def _validate_authoritative_identity(projection: Mapping[str, Any]) -> None:
    _required_ref(projection.get("manifest_run_id"), "manifest_run_id")
    _required_ref(projection.get("radar_run_id"), "radar_run_id")
    week = _required_text(projection.get("reporting_week"), "reporting_week", 8)
    if not _ISO_WEEK_RE.fullmatch(week):
        raise MvpRadarReaderError("Radar reporting_week is invalid")
    _required_text(
        projection.get("analysis_period_start"), "analysis_period_start", 80
    )
    _required_text(projection.get("analysis_period_end"), "analysis_period_end", 80)


def _validate_artifact_ref(
    value: Mapping[str, Any], *, authoritative: bool
) -> None:
    expected_fields = {
        "radar_json_path",
        "radar_json_sha256",
        "binding_schema_version",
        "binding_path",
        "binding_sha256",
    }
    if set(value) != expected_fields:
        raise MvpRadarReaderError("Radar artifact_ref fields are invalid")
    for field in expected_fields:
        raw = value.get(field)
        if not isinstance(raw, str) or len(raw) > 2000 or _CONTROL_RE.search(raw):
            raise MvpRadarReaderError(f"artifact_ref.{field} is invalid")
    if authoritative:
        if not value.get("radar_json_path") or not re.fullmatch(
            r"[0-9a-f]{64}", str(value.get("radar_json_sha256") or "")
        ):
            raise MvpRadarReaderError("authoritative Radar artifact identity is missing")
        if value.get("binding_schema_version") != RADAR_BINDING_SCHEMA_VERSION:
            raise MvpRadarReaderError("Radar binding schema identity is invalid")


def _validate_decision_context_projection(value: object, unmatched: object) -> None:
    context = _required_mapping(value, "decision_context")
    if not isinstance(unmatched, list):
        raise MvpRadarReaderError("unmatched context must be a list")
    flattened: list[Mapping[str, Any]] = []
    if set(context) - {"market_context", "external_research_context"}:
        raise MvpRadarReaderError("decision context contains an unsupported lane")
    for lane_name, lane_value in context.items():
        lane = _required_mapping(lane_value, f"decision_context.{lane_name}")
        records = lane.get("records")
        if (
            lane.get("status") != "context_only"
            or lane.get("context_only") is not True
            or lane.get("build_ready_evidence") is not False
            or lane.get("source_gate_satisfied") is not False
            or not isinstance(records, list)
            or not isinstance(lane.get("record_count"), int)
            or isinstance(lane.get("record_count"), bool)
            or lane.get("record_count", 0) < len(records)
        ):
            raise MvpRadarReaderError("decision context lane contradicts context-only policy")
        for record in records:
            if (
                not isinstance(record, Mapping)
                or record.get("lane") != lane_name
                or record.get("context_only") is not True
                or record.get("build_ready_evidence") is not False
                or record.get("source_gate_satisfied") is not False
                or record.get("radar_role") != "context_only"
            ):
                raise MvpRadarReaderError("decision context record is inconsistent")
            flattened.append(record)
    if flattened != unmatched:
        raise MvpRadarReaderError("decision context/unmatched projection mismatch")


def _validate_normalized_external_evidence(
    item: Mapping[str, Any], *, candidate_title: str
) -> None:
    _required_ref(item.get("evidence_ref"), "external evidence_ref")
    evidence_kind = _required_text(
        item.get("evidence_kind"), "external evidence_kind", 80
    )
    if evidence_kind not in EVIDENCE_KINDS:
        raise MvpRadarReaderError("external evidence_kind is unsupported")
    source_type = _required_text(item.get("source_type"), "external source_type", 80)
    if not _SOURCE_TYPE_RE.fullmatch(source_type):
        raise MvpRadarReaderError("external source_type must be canonical lowercase")
    if item.get("matched_candidate_title") != candidate_title:
        raise MvpRadarReaderError("external evidence candidate projection mismatch")
    source_url = _safe_url(
        item.get("source_url"), "external source_url", required=False
    )
    for field in (
        "decision_grade",
        "supports_gate",
        "negative_signal",
        "context_only",
        "build_ready_evidence",
        "gate_eligible",
    ):
        if not isinstance(item.get(field), bool):
            raise MvpRadarReaderError(f"external evidence {field} must be boolean")
    if item.get("negative_signal") is not (
        evidence_kind.casefold() == "negative_signal"
    ):
        raise MvpRadarReaderError("external evidence negative-signal flag is inconsistent")
    expected_gate = (
        item.get("supports_gate") is True
        and item.get("decision_grade") is True
        and item.get("context_only") is False
        and item.get("negative_signal") is False
        and source_type in RADAR_GATE_SOURCE_TYPES
        and bool(source_url)
    )
    if (
        item.get("gate_eligible") is not expected_gate
        or item.get("build_ready_evidence") is not expected_gate
    ):
        raise MvpRadarReaderError("external evidence gate projection is inconsistent")
    expected_role = "context_only" if item.get("context_only") else "matched_external_evidence"
    if item.get("radar_role") != expected_role:
        raise MvpRadarReaderError("external evidence Radar role is inconsistent")


def _projection_gate_eligible(item: Mapping[str, Any]) -> bool:
    return (
        item.get("gate_eligible") is True
        and item.get("supports_gate") is True
        and item.get("decision_grade") is True
        and item.get("context_only") is False
        and item.get("negative_signal") is False
        and item.get("build_ready_evidence") is True
        and item.get("source_type") in RADAR_GATE_SOURCE_TYPES
        and bool(item.get("source_url"))
    )


def _validate_kir_projection(
    value: object,
    source_mix: Mapping[str, Any],
    *,
    analysis_period_end: str,
) -> None:
    if not isinstance(value, list) or len(value) > _MAX_KIR:
        raise MvpRadarReaderError("matched KIR provenance must be bounded")
    atom_ids: set[str] = set()
    source_urls: set[str] = set()
    seed_refs: set[str] = set()
    freshness: list[bool] = []
    for item in value:
        if (
            not isinstance(item, Mapping)
            or item.get("context_only") is not False
            or item.get("radar_role") != "candidate_evidence"
            or item.get("build_ready_evidence") is not False
        ):
            raise MvpRadarReaderError("matched KIR provenance is not candidate evidence")
        seed_ref = _required_ref(item.get("seed_ref"), "KIR seed_ref")
        if seed_ref in seed_refs:
            raise MvpRadarReaderError("matched KIR provenance contains duplicate seeds")
        seed_refs.add(seed_ref)
        _required_ref(item.get("thread_slug"), "KIR thread_slug")
        _required_text(item.get("thread_title"), "KIR thread_title", 300)
        thread_status = _required_text(
            item.get("thread_status"), "KIR thread_status", 80
        )
        captured_at = _required_text(item.get("captured_at"), "KIR captured_at", 80)
        freshness.append(
            _kir_is_fresh(
                status=thread_status,
                captured_at=captured_at,
                analysis_period_end=analysis_period_end,
            )
        )
        atom_ids.update(
            _ref_list(item.get("source_atom_ids"), "KIR source_atom_ids", limit=32)
        )
        source_urls.update(
            _url_list(item.get("source_urls"), "KIR source_urls", limit=16)
        )
    if value and source_mix.get("kir_required") is not True:
        raise MvpRadarReaderError("matched KIR provenance contradicts source mix")
    if source_mix.get("kir_gate_status") == "passed" and not value:
        raise MvpRadarReaderError("passing KIR projection has no provenance")
    if source_mix.get("kir_has_fresh_thread") is not any(freshness):
        raise MvpRadarReaderError("KIR freshness/source mix mismatch")
    if source_mix.get("kir_gate_status") == "passed" and not any(freshness):
        raise MvpRadarReaderError("passing KIR provenance is stale")
    if (
        source_mix.get("kir_source_atom_count") != len(atom_ids)
        or source_mix.get("kir_source_url_count") != len(source_urls)
    ):
        raise MvpRadarReaderError("matched KIR provenance count mismatch")
    if value:
        first = value[0]
        parity = {
            "kir_source_kind": "knowledge_thread",
            "kir_thread_slug": first.get("thread_slug"),
            "kir_thread_title": first.get("thread_title"),
            "kir_thread_status": first.get("thread_status"),
        }
        if any(source_mix.get(field) != expected for field, expected in parity.items()):
            raise MvpRadarReaderError("matched KIR provenance/source mix mismatch")


def _candidate_projection(
    selected: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    radar_run_id: str,
) -> dict[str, Any]:
    title = _required_text(selected.get("title"), "selected.title", 300)
    if result.get("selected_title") != title:
        raise MvpRadarReaderError("Radar result/selected title mismatch")
    dossier_status = _required_text(
        selected.get("dossier_status"), "selected.dossier_status", 80
    )
    recommendation = _required_text(
        selected.get("recommendation"), "selected.recommendation", 120
    )
    if dossier_status not in DOSSIER_STATUSES:
        raise MvpRadarReaderError("unsupported Radar dossier status")
    if recommendation not in RECOMMENDATIONS:
        raise MvpRadarReaderError("unsupported Radar recommendation")
    if result.get("dossier_status") != dossier_status:
        raise MvpRadarReaderError("Radar result/selected dossier status mismatch")
    if result.get("recommendation") != recommendation:
        raise MvpRadarReaderError("Radar result/selected recommendation mismatch")
    score = _optional_score(selected.get("score"), "selected.score")
    if result.get("score") != selected.get("score"):
        raise MvpRadarReaderError("Radar result/selected score mismatch")
    candidate_id = _required_candidate_id(selected.get("candidate_id"), title=title)
    confidence = _required_text(selected.get("confidence"), "selected.confidence", 80)
    return {
        "candidate_id": candidate_id,
        "candidate_id_source": "producer",
        "title": title,
        "dossier_status": dossier_status,
        "recommendation": recommendation,
        "confidence": confidence,
        "score": score,
        "radar_run_id": radar_run_id,
    }


def _reader_decision(
    candidate: Mapping[str, Any],
    source_mix: Mapping[str, Any],
    gate_proof: Sequence[Mapping[str, Any]],
) -> str:
    dossier = candidate["dossier_status"]
    recommendation = candidate["recommendation"]
    if dossier == "reject":
        if recommendation not in {
            "reject",
            "existing_project_context",
            "needs_more_evidence",
            "needs_more_specific_scope",
            "revisit_with_evidence_gap",
        }:
            raise MvpRadarReaderError("reject dossier contradicts recommendation")
        return "reject"
    if dossier == "investigate":
        if recommendation in {"build", "focused_experiment", "reject"}:
            raise MvpRadarReaderError("investigate dossier contradicts recommendation")
        return "investigate"
    if dossier == "focused_experiment":
        if recommendation != "focused_experiment":
            raise MvpRadarReaderError("focused experiment status/recommendation mismatch")
        _require_build_gates(source_mix, gate_proof)
        return "investigate"
    if dossier == "build":
        if recommendation != "build":
            raise MvpRadarReaderError("build status/recommendation mismatch")
        _require_build_gates(source_mix, gate_proof)
        return "build_allowed"
    raise MvpRadarReaderError("unsupported Radar dossier status")


def _require_build_gates(
    source_mix: Mapping[str, Any], gate_proof: Sequence[Mapping[str, Any]]
) -> None:
    source_types = {str(item.get("source_type")) for item in gate_proof}
    if len(gate_proof) < 2 or len(source_types) < 2:
        raise MvpRadarReaderError("build/focused status lacks independent external proof")
    if source_mix.get("decision_grade_external") is not True:
        raise MvpRadarReaderError("build/focused status lacks decision-grade source mix")
    if source_mix.get("kir_required") is True and source_mix.get("kir_gate_status") != "passed":
        raise MvpRadarReaderError("build/focused status lacks a passing KIR gate")


def _consistent_external_evidence(
    payload: Mapping[str, Any],
    result: Mapping[str, Any],
    selected: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    values = [
        payload.get("matched_external_evidence"),
        result.get("matched_external_evidence"),
        selected.get("matched_external_evidence"),
    ]
    concrete = [value for value in values if value is not None]
    if not concrete or any(value != concrete[0] for value in concrete[1:]):
        raise MvpRadarReaderError("Radar matched external evidence projections differ")
    if not isinstance(concrete[0], list) or any(
        not isinstance(item, Mapping) for item in concrete[0]
    ):
        raise MvpRadarReaderError("matched external evidence must be an object list")
    return list(concrete[0])


def _normalize_external_evidence(
    value: Mapping[str, Any], *, candidate_title: str
) -> dict[str, Any]:
    matched_title = _required_text(
        value.get("matched_candidate_title"),
        "external evidence matched_candidate_title",
        300,
    )
    if matched_title != candidate_title:
        raise MvpRadarReaderError("external evidence is matched to another candidate")
    source_type = _required_text(value.get("source_type"), "external source_type", 80)
    if not _SOURCE_TYPE_RE.fullmatch(source_type):
        raise MvpRadarReaderError("external source_type must be canonical lowercase")
    source_url = _safe_url(value.get("source_url"), "external source_url", required=False)
    fingerprint = _required_ref(
        value.get("source_fingerprint"), "external source_fingerprint"
    )
    evidence_kind = _required_text(
        value.get("evidence_kind"), "external evidence_kind", 80
    )
    if evidence_kind not in EVIDENCE_KINDS:
        raise MvpRadarReaderError("external evidence_kind is unsupported")
    for field in ("negative_signal", "supports_gate", "decision_grade"):
        if not isinstance(value.get(field), bool):
            raise MvpRadarReaderError(f"external evidence {field} must be boolean")
    for field in ("context_only", "build_ready_evidence"):
        if field in value and not isinstance(value.get(field), bool):
            raise MvpRadarReaderError(f"external evidence {field} must be boolean")
    role = value.get("radar_role")
    if role is not None and (
        not isinstance(role, str)
        or role not in {"context_only", "matched_external_evidence"}
    ):
        raise MvpRadarReaderError("external evidence radar_role is invalid")
    context_only = value.get("context_only") is True or role == "context_only"
    if role == "matched_external_evidence" and context_only:
        raise MvpRadarReaderError("external evidence role contradicts context_only")
    negative = value.get("negative_signal") is True
    if negative is not (evidence_kind.casefold() == "negative_signal"):
        raise MvpRadarReaderError("external evidence negative-signal flag is inconsistent")
    supports_gate = value.get("supports_gate") is True
    decision_grade = value.get("decision_grade") is True
    build_ready_present = "build_ready_evidence" in value
    build_ready = value.get("build_ready_evidence") is not False
    gate_eligible = (
        supports_gate
        and decision_grade
        and not context_only
        and not negative
        and source_type in RADAR_GATE_SOURCE_TYPES
        and bool(source_url)
        and (build_ready or not build_ready_present)
    )
    return {
        "evidence_ref": fingerprint,
        "evidence_kind": evidence_kind,
        "source_type": source_type,
        "source_name": _optional_text(value.get("source_name"), 160),
        "source_id": _optional_text(value.get("source_id"), 240),
        "source_url": source_url,
        "source_title": _optional_text(value.get("source_title"), 400),
        "source_snippet": _optional_text(value.get("source_snippet"), 1000),
        "captured_at": _optional_text(value.get("captured_at"), 80),
        "query": _optional_text(value.get("query"), 500),
        "matched_candidate_title": matched_title,
        "match_basis": _optional_text(value.get("match_basis"), 160),
        "decision_grade": decision_grade,
        "supports_gate": supports_gate,
        "negative_signal": negative,
        "context_only": context_only,
        "radar_role": "matched_external_evidence" if not context_only else "context_only",
        "build_ready_evidence": gate_eligible,
        "gate_eligible": gate_eligible,
    }


def _validate_source_mix(
    source_mix: Mapping[str, Any],
    gate_proof: Sequence[Mapping[str, Any]],
    *,
    bound_candidate_seed_count: int,
) -> None:
    fingerprints = [str(item.get("evidence_ref")) for item in gate_proof]
    if len(fingerprints) != len(set(fingerprints)):
        raise MvpRadarReaderError("duplicate external fingerprint entered gate proof")
    source_types = sorted({str(item.get("source_type")) for item in gate_proof})
    raw_count = source_mix.get("selected_external_evidence_count")
    if not isinstance(raw_count, int) or isinstance(raw_count, bool) or raw_count < 0:
        raise MvpRadarReaderError("invalid selected external evidence count")
    if raw_count != len(gate_proof):
        raise MvpRadarReaderError("source mix external evidence count mismatch")
    raw_types = source_mix.get("selected_external_source_types")
    if not isinstance(raw_types, list) or raw_types != source_types:
        raise MvpRadarReaderError("source mix external source types mismatch")
    expected_grade = len(gate_proof) >= 2 and len(source_types) >= 2
    if source_mix.get("decision_grade_external") is not expected_grade:
        raise MvpRadarReaderError("source mix decision-grade flag mismatch")
    if not isinstance(source_mix.get("kir_required"), bool):
        raise MvpRadarReaderError("source mix kir_required must be boolean")
    declared_seed_count = source_mix.get("selected_telegram_seed_evidence_count")
    if (
        not isinstance(declared_seed_count, int)
        or isinstance(declared_seed_count, bool)
        or not 0 <= declared_seed_count <= _MAX_SEEDS
        or declared_seed_count != bound_candidate_seed_count
    ):
        raise MvpRadarReaderError("source mix selected Telegram seed count mismatch")
    if source_mix.get("kir_required") is not (bound_candidate_seed_count > 0):
        raise MvpRadarReaderError("source mix KIR requirement contradicts bound seeds")
    kir_status = _required_text(
        source_mix.get("kir_gate_status"), "source mix kir_gate_status", 80
    )
    if kir_status not in KIR_GATE_STATUSES:
        raise MvpRadarReaderError("source mix kir_gate_status is unsupported")
    if source_mix.get("kir_required") is False and kir_status != "not_required":
        raise MvpRadarReaderError("non-required KIR source mix has an invalid status")
    if source_mix.get("kir_required") is True and kir_status == "not_required":
        raise MvpRadarReaderError("required KIR source mix cannot be not_required")
    if not isinstance(source_mix.get("kir_has_fresh_thread"), bool):
        raise MvpRadarReaderError("source mix kir_has_fresh_thread must be boolean")
    for field in ("kir_source_atom_count", "kir_source_url_count"):
        count = source_mix.get(field)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise MvpRadarReaderError(f"source mix {field} must be non-negative")
    if kir_status == "passed" and (
        source_mix.get("kir_has_fresh_thread") is not True
        or source_mix.get("kir_source_atom_count", 0) <= 0
        or source_mix.get("kir_source_url_count", 0) <= 0
    ):
        raise MvpRadarReaderError("passing KIR source mix is not fresh and sourced")


def _candidate_seed_count(
    seed_payload: Sequence[object], *, candidate_key: str
) -> int:
    count = 0
    for raw in seed_payload:
        if not isinstance(raw, Mapping):
            raise MvpRadarReaderError("Radar seed export contains a non-object row")
        if not _seed_matches_candidate(raw, candidate_key=candidate_key):
            continue
        upstream_id = str(raw.get("upstream_id") or "")
        is_candidate_seed = (
            upstream_id.startswith("telegram:")
            or raw.get("source_kind") == "knowledge_thread"
        )
        if (
            is_candidate_seed
            and raw.get("radar_role") == "candidate_evidence"
            and raw.get("context_only") is False
            and raw.get("build_ready_evidence") is False
        ):
            count += 1
    return count


def _seed_matches_candidate(
    seed: Mapping[str, Any], *, candidate_key: str
) -> bool:
    shape = str(seed.get("mvp_shape") or seed.get("title") or "").strip()
    return _normalized_candidate_key(shape) == candidate_key


def _normalized_candidate_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9а-яё]+", "-", value.lower()).strip("-")
    return normalized or "untitled"


def _matched_kir_provenance(
    seed_payload: Sequence[object],
    *,
    candidate_key: str,
    source_mix: Mapping[str, Any],
    analysis_period_end: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    freshness: list[bool] = []
    for raw in seed_payload:
        if not isinstance(raw, Mapping):
            raise MvpRadarReaderError("Radar seed export contains a non-object row")
        if raw.get("source_kind") != "knowledge_thread":
            continue
        if not _seed_matches_candidate(raw, candidate_key=candidate_key):
            continue
        if raw.get("context_only") is not False:
            raise MvpRadarReaderError("KIR provenance context_only must be false")
        if raw.get("radar_role") != "candidate_evidence":
            raise MvpRadarReaderError("KIR provenance must be candidate evidence")
        if raw.get("build_ready_evidence") is not False:
            raise MvpRadarReaderError("KIR provenance must not claim build readiness")
        source_urls = _url_list(raw.get("source_urls"), "KIR source_urls", limit=16)
        if not source_urls:
            first_url = _safe_url(raw.get("source_url"), "KIR source_url", required=False)
            source_urls = [first_url] if first_url else []
        atom_ids = _ref_list(raw.get("source_atom_ids"), "KIR source_atom_ids", limit=32)
        thread_status = _required_text(
            raw.get("knowledge_thread_status"), "KIR thread status", 80
        )
        captured_at = _required_text(raw.get("captured_at"), "KIR captured_at", 80)
        freshness.append(
            _kir_is_fresh(
                status=thread_status,
                captured_at=captured_at,
                analysis_period_end=analysis_period_end,
            )
        )
        result.append(
            {
                "seed_ref": _required_ref(raw.get("upstream_id"), "KIR upstream_id"),
                "thread_slug": _required_ref(
                    raw.get("knowledge_thread_slug"), "KIR thread slug"
                ),
                "thread_title": _required_text(
                    raw.get("knowledge_thread_title"), "KIR thread title", 300
                ),
                "thread_status": thread_status,
                "captured_at": captured_at,
                "source_atom_ids": atom_ids,
                "source_urls": source_urls,
                "radar_role": str(raw.get("radar_role") or "candidate_evidence"),
                "context_only": False,
                "build_ready_evidence": bool(raw.get("build_ready_evidence", False)),
            }
        )
        if len(result) > _MAX_KIR:
            raise MvpRadarReaderError("matched KIR provenance exceeds the reader limit")
    kir_required = source_mix.get("kir_required") is True
    if source_mix.get("kir_gate_status") == "passed" and not result:
        raise MvpRadarReaderError("passing source mix lacks bound KIR provenance")
    if source_mix.get("kir_has_fresh_thread") is not any(freshness):
        raise MvpRadarReaderError("KIR freshness/source mix mismatch")
    if source_mix.get("kir_gate_status") == "passed" and not any(freshness):
        raise MvpRadarReaderError("passing KIR provenance is stale")
    if result and not kir_required:
        raise MvpRadarReaderError("bound KIR provenance contradicts kir_required=false")
    atom_ids = {item for row in result for item in row["source_atom_ids"]}
    source_urls = {item for row in result for item in row["source_urls"]}
    for field, expected in (
        ("kir_source_atom_count", len(atom_ids)),
        ("kir_source_url_count", len(source_urls)),
    ):
        raw = source_mix.get(field)
        if raw is not None and raw != expected:
            raise MvpRadarReaderError(f"source mix {field} mismatch")
    if result:
        first = result[0]
        parity = {
            "kir_source_kind": "knowledge_thread",
            "kir_thread_slug": first["thread_slug"],
            "kir_thread_title": first["thread_title"],
            "kir_thread_status": first["thread_status"],
        }
        for field, expected in parity.items():
            if source_mix.get(field) not in (None, expected):
                raise MvpRadarReaderError(f"source mix {field} mismatch")
    return result


def _kir_is_fresh(
    *, status: str, captured_at: str, analysis_period_end: str
) -> bool:
    if status.casefold() in {"stale", "superseded", "resolved", "hype_only"}:
        return False
    try:
        captured = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        period_end = datetime.fromisoformat(
            analysis_period_end.replace("Z", "+00:00")
        )
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        if period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=timezone.utc)
        age_days = max(
            (
                period_end.astimezone(timezone.utc)
                - captured.astimezone(timezone.utc)
            ).days,
            0,
        )
    except (ValueError, OverflowError) as exc:
        raise MvpRadarReaderError("KIR freshness timestamps are invalid") from exc
    return age_days <= 30


def _normalize_context(value: object) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if value is None:
        return [], {}
    context = _required_mapping(value, "decision_context")
    output: list[dict[str, Any]] = []
    normalized: dict[str, Any] = {}
    for lane in ("market_context", "external_research_context"):
        raw_lane = context.get(lane)
        if raw_lane in (None, {}):
            continue
        lane_map = _required_mapping(raw_lane, f"decision_context.{lane}")
        if (
            lane_map.get("context_only") is not True
            or lane_map.get("source_gate_satisfied") is not False
        ):
            raise MvpRadarReaderError(f"{lane} contradicts context-only policy")
        if lane == "market_context" and lane_map.get("build_ready_evidence") is not False:
            raise MvpRadarReaderError("market context is marked build-ready")
        records = lane_map.get("records")
        if not isinstance(records, list):
            raise MvpRadarReaderError(f"{lane}.records must be a list")
        if len(output) + len(records) > _MAX_CONTEXT:
            raise MvpRadarReaderError("unmatched context exceeds the reader limit")
        normalized_records = []
        for raw in records:
            record = _required_mapping(raw, f"{lane} record")
            if record.get("context_only") is not True:
                raise MvpRadarReaderError(f"{lane} record is not context-only")
            if record.get("source_gate_satisfied") not in (None, False):
                raise MvpRadarReaderError(f"{lane} record claims a satisfied gate")
            if record.get("build_ready_evidence") not in (None, False):
                raise MvpRadarReaderError(f"{lane} record is marked build-ready")
            item = {
                "context_ref": _context_ref(lane, record),
                "lane": lane,
                "title": _first_text(record.get("source_title"), record.get("title")),
                "source_type": _first_text(
                    record.get("source_type"), record.get("source_kind"), lane
                ),
                "source_url": _safe_url(
                    record.get("source_url"), f"{lane} source_url", required=False
                ),
                "reason": _first_text(record.get("reason"), lane_map.get("summary")),
                "radar_role": "context_only",
                "context_only": True,
                "build_ready_evidence": False,
                "source_gate_satisfied": False,
            }
            normalized_records.append(item)
            output.append(item)
        declared_count = lane_map.get("record_count")
        if (
            not isinstance(declared_count, int)
            or isinstance(declared_count, bool)
            or declared_count < len(records)
        ):
            raise MvpRadarReaderError(f"{lane}.record_count is invalid")
        normalized[lane] = {
            "status": "context_only",
            "record_count": declared_count,
            "records": normalized_records,
            "context_only": True,
            "build_ready_evidence": False,
            "source_gate_satisfied": False,
        }
    if len(output) > _MAX_CONTEXT:
        raise MvpRadarReaderError("unmatched context exceeds the reader limit")
    return output, normalized


def _consistent_missing_categories(
    payload: Mapping[str, Any],
    result: Mapping[str, Any],
    selected: Mapping[str, Any],
) -> dict[str, Any]:
    value = _consistent_mapping(
        "missing_evidence_by_category",
        payload.get("missing_evidence_by_category"),
        result.get("missing_evidence_by_category"),
        selected.get("missing_evidence_by_category"),
        allow_empty=True,
    )
    if len(value) > 16:
        raise MvpRadarReaderError("missing evidence categories exceed the reader limit")
    return copy.deepcopy(dict(value))


def _missing_evidence(
    selected: Mapping[str, Any], categories: Mapping[str, Any]
) -> list[str]:
    values = _text_list(
        selected.get("missing_evidence"),
        "selected.missing_evidence",
        limit=_MAX_MISSING,
        item_limit=600,
        required=False,
    )
    for category, details in categories.items():
        _required_text(category, "missing evidence category", 100)
        detail_map = _required_mapping(details, f"missing category {category}")
        for item in _text_list(
            detail_map.get("missing_evidence"),
            f"missing category {category}",
            limit=8,
            item_limit=600,
            required=False,
        ):
            if item not in values:
                values.append(item)
                if len(values) > _MAX_MISSING:
                    raise MvpRadarReaderError("missing evidence exceeds the reader limit")
    return values


def _next_query(
    action: Mapping[str, Any], validation_queries: Mapping[str, Any]
) -> dict[str, str] | None:
    action_query = _optional_text(action.get("next_query"), 500)
    action_intent = _optional_text(action.get("next_intent"), 120)
    action_category = _optional_text(action.get("missing_category"), 120)
    pack_next = _mapping(validation_queries.get("next_query"))
    pack_query = _optional_text(pack_next.get("query"), 500)
    pack_intent = _optional_text(pack_next.get("intent"), 120)
    if action_query and pack_query and action_query != pack_query:
        raise MvpRadarReaderError("decision action and validation pack next query differ")
    if action_intent and pack_intent and action_intent != pack_intent:
        raise MvpRadarReaderError("decision action and validation pack intent differ")
    query = action_query or pack_query
    if not query:
        return None
    return {
        "query": query,
        "intent": action_intent or pack_intent,
        "category": action_category,
    }


def _validate_decision_change(
    action: Mapping[str, Any],
    gate_proof: Sequence[Mapping[str, Any]],
    next_query: Mapping[str, str] | None,
    *,
    dossier_status: str,
) -> None:
    if action.get("current_gate") != dossier_status:
        raise MvpRadarReaderError("decision-change current gate mismatch")
    count = action.get("matched_external_evidence_count")
    if not isinstance(count, int) or isinstance(count, bool) or count != len(gate_proof):
        raise MvpRadarReaderError("decision-change evidence count mismatch")
    types = sorted({str(item.get("source_type")) for item in gate_proof})
    if action.get("matched_external_source_types") != types:
        raise MvpRadarReaderError("decision-change source types mismatch")
    if action.get("market_context_role") != "context_only_not_proof":
        raise MvpRadarReaderError("decision-change market context role is unsafe")
    _required_text(
        action.get("next_validation_action"),
        "decision-change next validation action",
        1000,
    )
    _required_text(
        action.get("required_gate_change"),
        "decision-change required gate change",
        1000,
    )
    rule = _required_text(
        action.get("context_only_results_rule"),
        "decision-change context-only rule",
        500,
    ).casefold()
    if rule != _reader_context_rule().casefold() and (
        "context" not in rule
        or not any(token in rule for token in ("not", "do not", "remain"))
    ):
        raise MvpRadarReaderError("decision-change context-only rule is missing")
    if not next_query and len(gate_proof) < 2:
        raise MvpRadarReaderError("incomplete gate has no next validation query")


def _reader_change_condition(
    *,
    reader_decision: str,
    dossier_status: str,
    source_mix: Mapping[str, Any],
    gate_proof: Sequence[Mapping[str, Any]],
    missing_evidence: Sequence[str],
) -> str:
    if reader_decision == "build_allowed":
        return (
            "Build-гейты уже выполнены; решение будет понижено, если исчезнет свежая "
            "KIR-провенанс или останется меньше двух независимых decision-grade внешних "
            "типов источников."
        )
    kir_status = str(source_mix.get("kir_gate_status") or "")
    kir_conditions = {
        "missing_kir_thread": "Добавить совпавший свежий KIR Knowledge Thread для кандидата.",
        "stale_kir_thread": "Обновить совпавший KIR Knowledge Thread свежими данными.",
        "missing_source_atoms": "Привязать к KIR-треду проверяемые source atom IDs.",
        "missing_source_urls": "Привязать к KIR-треду проверяемые source URLs.",
        "blocking_risk": "Снять блокирующие риски, зафиксированные Radar.",
        "profile_mismatch": "Подтвердить узкий operator-fit без текущего profile mismatch.",
        "missing_operator_fit": "Добавить положительное доказательство operator fit.",
    }
    if source_mix.get("kir_required") is True and kir_status in kir_conditions:
        return kir_conditions[kir_status]
    source_types = {str(item.get("source_type") or "") for item in gate_proof}
    if len(gate_proof) < 2 or len(source_types) < 2:
        return (
            "Добавить минимум два независимых candidate-specific decision-grade внешних "
            "типа источников; context-only записи не учитываются."
        )
    if missing_evidence:
        return "Закрыть подтверждённый Radar evidence gap: " + str(missing_evidence[0])
    if dossier_status == "focused_experiment":
        return (
            "Внешний evidence gate выполнен; повысить решение можно только после "
            "ограниченного эксперимента и проверки его kill criteria."
        )
    return "Повторить Radar после устранения причин текущего dossier status."


def _reader_next_validation(
    next_query: Mapping[str, str] | None,
    *,
    reader_decision: str,
    source_mix: Mapping[str, Any],
    gate_proof: Sequence[Mapping[str, Any]],
) -> str:
    kir_status = str(source_mix.get("kir_gate_status") or "")
    if source_mix.get("kir_required") is True and kir_status in {
        "missing_kir_thread",
        "stale_kir_thread",
        "missing_source_atoms",
        "missing_source_urls",
    }:
        return "Обновить совпавшую KIR-провенанс и повторить тот же bounded Radar run."
    if reader_decision == "build_allowed":
        return "Провести ограниченный пилот и проверить заявленные kill criteria до расширения."
    source_types = {str(item.get("source_type") or "") for item in gate_proof}
    if (len(gate_proof) < 2 or len(source_types) < 2) and next_query and next_query.get(
        "query"
    ):
        return (
            f"Выполнить candidate-specific запрос `{next_query['query']}` и приложить "
            "только явно совпавшие внешние доказательства."
        )
    if next_query and next_query.get("query"):
        return f"Проверить следующий Radar gap запросом `{next_query['query']}`."
    return "Повторить Radar после получения нового candidate-specific доказательства."


def _reader_context_rule() -> str:
    return (
        "Unmatched external research, market context, Telegram и X остаются "
        "context-only и не удовлетворяют evidence gates."
    )


def _validate_seed_period(
    seeds: Sequence[object], manifest: Mapping[str, Any]
) -> None:
    expected = {
        "reporting_week": manifest.get("reporting_week"),
        "week_label": manifest.get("week_label"),
        "period_mode": manifest.get("period_mode"),
        "analysis_period_start": manifest.get("analysis_period_start"),
        "analysis_period_end": manifest.get("analysis_period_end"),
    }
    for index, raw in enumerate(seeds):
        if not isinstance(raw, Mapping):
            raise MvpRadarReaderError(f"Radar seed {index} is not an object")
        for field, value in expected.items():
            if raw.get(field) != value:
                raise MvpRadarReaderError(f"Radar seed {index} {field} mismatch")
        if raw.get("contract_version") not in (
            None,
            RADAR_INTELLIGENCE_CONTRACT_VERSION,
        ):
            raise MvpRadarReaderError(f"Radar seed {index} contract mismatch")


def _validate_status_projection(
    binding: Mapping[str, Any], result: Mapping[str, Any]
) -> None:
    projection = _required_mapping(binding.get("status_projection"), "status_projection")
    allowed = {
        "status",
        "selected_title",
        "dossier_status",
        "recommendation",
        "score",
        "selected_source_mix",
    }
    if "status" not in projection or not set(projection).issubset(allowed):
        raise MvpRadarReaderError("binding status projection has unsafe fields")
    for field, value in projection.items():
        if result.get(field) != value:
            raise MvpRadarReaderError(f"binding status projection differs for {field}")


def _validate_stage_binding_parity(
    stage: Mapping[str, Any], binding: Mapping[str, Any]
) -> None:
    parity = (
        ("seed_export_ref", "path", "seed_export_path"),
        ("seed_export_ref", "sha256", "seed_export_sha256"),
        ("radar_json_ref", "path", "artifact_path"),
        ("radar_json_ref", "sha256", "artifact_sha256"),
    )
    for ref_name, ref_field, stage_field in parity:
        if _mapping(binding.get(ref_name)).get(ref_field) != stage.get(stage_field):
            raise MvpRadarReaderError(f"Radar binding/stage mismatch for {stage_field}")


def _no_candidate_projection(
    manifest: Mapping[str, Any],
    *,
    binding: Mapping[str, Any],
    radar_status: str,
    binding_ref: Mapping[str, str] | None,
) -> dict[str, Any]:
    return {
        "schema_version": MVP_RADAR_READER_SCHEMA_VERSION,
        "contract_version": RADAR_INTELLIGENCE_CONTRACT_VERSION,
        "reader_state": "no_candidate",
        "candidate_state": "no_candidate",
        "status": radar_status,
        "snapshot_status": "complete",
        "partial": False,
        "partial_reasons": [],
        **_identity_projection(
            manifest, radar_run_id=str(binding.get("radar_run_id") or "")
        ),
        "artifact_ref": _artifact_ref(binding, binding_ref),
        "source_path": str(_mapping(binding.get("radar_json_ref")).get("path") or ""),
        "selected_candidate": None,
        "candidate": None,
        "dossier_status": None,
        "recommendation": None,
        "score": None,
        "reader_decision": "unavailable",
        "decision_reason": "no_candidate",
        "decision_reason_ru": _NO_CANDIDATE_REASON_RU,
        "source_mix": {},
        "bound_candidate_seed_count": 0,
        "matched_kir_provenance": [],
        "matched_external_evidence": [],
        "matched_external_proof": [],
        "unmatched_context": [],
        "decision_context": {},
        "missing_evidence": ["Нет выбранного кандидата для проверки."],
        "missing_evidence_by_category": {},
        "validation_queries": {},
        "decision_change_action": {},
        "change_condition": _NO_CANDIDATE_CHANGE_CONDITION,
        "next_validation_query": None,
        "next_validation": _NO_CANDIDATE_NEXT_VALIDATION,
        "next_experiment": [],
        "kill_criteria": [],
        "evidence_policy": _evidence_policy(),
    }


def _unavailable_projection(
    manifest: Mapping[str, Any],
    *,
    reader_state: str,
    reasons: Sequence[str],
    partial: bool = True,
    artifact_ref: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    manifest_map = manifest if isinstance(manifest, Mapping) else {}
    raw_run_id = _safe_bounded_text(manifest_map.get("run_id"), 128)
    run_id = raw_run_id if _RUN_ID_RE.fullmatch(raw_run_id) else ""
    raw_week = _safe_bounded_text(manifest_map.get("reporting_week"), 8)
    reporting_week = raw_week if _ISO_WEEK_RE.fullmatch(raw_week) else ""
    safe_reasons = [
        text
        for raw in list(reasons)[:12]
        if (text := _safe_bounded_text(raw, 600))
    ] or ["MVP Radar недоступен."]
    raw_artifact = artifact_ref if isinstance(artifact_ref, Mapping) else {}
    safe_artifact_ref = {
        field: _safe_bounded_text(raw_artifact.get(field), 2000)
        for field in _empty_artifact_ref()
    }
    projection = {
        "schema_version": MVP_RADAR_READER_SCHEMA_VERSION,
        "contract_version": RADAR_INTELLIGENCE_CONTRACT_VERSION,
        "reader_state": reader_state,
        "candidate_state": (
            "intentionally_disabled"
            if reader_state == "disabled"
            else "unknown_due_to_unavailable_radar"
        ),
        "status": "intentionally_disabled" if reader_state == "disabled" else "not_available",
        "snapshot_status": "failed",
        "partial": partial,
        "partial_reasons": safe_reasons if partial else [],
        "manifest_run_id": run_id,
        "radar_run_id": "",
        "reporting_week": reporting_week,
        "analysis_period_start": _safe_bounded_text(
            manifest_map.get("analysis_period_start"), 80
        ),
        "analysis_period_end": _safe_bounded_text(
            manifest_map.get("analysis_period_end"), 80
        ),
        "artifact_ref": safe_artifact_ref,
        "source_path": "",
        "selected_candidate": None,
        "candidate": None,
        "dossier_status": None,
        "recommendation": None,
        "score": None,
        "reader_decision": "unavailable",
        "decision_reason": reader_state,
        "decision_reason_ru": safe_reasons[0],
        "source_mix": {},
        "bound_candidate_seed_count": 0,
        "matched_kir_provenance": [],
        "matched_external_evidence": [],
        "matched_external_proof": [],
        "unmatched_context": [],
        "decision_context": {},
        "missing_evidence": safe_reasons,
        "missing_evidence_by_category": {},
        "validation_queries": {},
        "decision_change_action": {},
        "change_condition": "Нужен валидный Radar artifact, связанный с этим запуском.",
        "next_validation_query": None,
        "next_validation": "Повторить MVP Radar в новом weekly run.",
        "next_experiment": [],
        "kill_criteria": [],
        "evidence_policy": _evidence_policy(),
    }
    validate_mvp_radar_reader_projection(projection)
    return projection


def _legacy_unavailable(
    expected_week: str,
    *,
    source_path: str | Path | None,
    reason: str,
) -> dict[str, Any]:
    return _unavailable_projection(
        {"run_id": "", "reporting_week": expected_week},
        reader_state="invalid",
        reasons=[reason],
        artifact_ref={
            **_empty_artifact_ref(),
            "radar_json_path": str(source_path or ""),
        },
    )


def _identity_projection(
    manifest: Mapping[str, Any], *, radar_run_id: str
) -> dict[str, str]:
    return {
        "manifest_run_id": str(manifest.get("run_id") or ""),
        "radar_run_id": radar_run_id,
        "reporting_week": str(manifest.get("reporting_week") or ""),
        "analysis_period_start": str(manifest.get("analysis_period_start") or ""),
        "analysis_period_end": str(manifest.get("analysis_period_end") or ""),
    }


def _artifact_ref(
    binding: Mapping[str, Any], binding_ref: Mapping[str, str] | None
) -> dict[str, str]:
    raw = _mapping(binding.get("radar_json_ref"))
    return {
        "radar_json_path": str(raw.get("path") or ""),
        "radar_json_sha256": str(raw.get("sha256") or ""),
        "binding_schema_version": RADAR_BINDING_SCHEMA_VERSION,
        "binding_path": str(_mapping(binding_ref).get("path") or ""),
        "binding_sha256": str(_mapping(binding_ref).get("sha256") or ""),
    }


def _artifact_ref_from_stage(stage: Mapping[str, Any]) -> dict[str, str]:
    return {
        "radar_json_path": str(stage.get("artifact_path") or ""),
        "radar_json_sha256": str(stage.get("artifact_sha256") or ""),
        "binding_schema_version": RADAR_BINDING_SCHEMA_VERSION,
        "binding_path": str(stage.get("binding_path") or ""),
        "binding_sha256": str(stage.get("binding_sha256") or ""),
    }


def _empty_artifact_ref() -> dict[str, str]:
    return {
        "radar_json_path": "",
        "radar_json_sha256": "",
        "binding_schema_version": "",
        "binding_path": "",
        "binding_sha256": "",
    }


def _evidence_policy() -> dict[str, bool]:
    return {
        "context_only_can_satisfy_gate": False,
        "market_context_can_satisfy_gate": False,
        "unbound_legacy_can_authorize": False,
        "negative_signal_can_satisfy_gate": False,
        "x_can_satisfy_gate": False,
    }


def _decision_reason_ru(
    reader_decision: str, *, dossier_status: str, proof_count: int
) -> str:
    if reader_decision == "build_allowed":
        return (
            f"Radar разрешил сборку: статус {dossier_status}, подтверждено "
            f"{proof_count} candidate-specific внешних доказательств."
        )
    if reader_decision == "reject":
        return "Radar отклонил кандидата; сборка и эксперимент не разрешены."
    if dossier_status == "focused_experiment":
        return (
            "Radar разрешил только ограниченный проверочный эксперимент; "
            "полная сборка не разрешена."
        )
    return "Radar оставил кандидата на исследовании; сборка не разрешена."


def _context_ref(lane: str, record: Mapping[str, Any]) -> str:
    basis = "\0".join(
        str(record.get(field) or "")
        for field in ("source_id", "source_url", "source_title", "title")
    )
    return f"context:{lane}:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def _consistent_mapping(
    label: str, *values: object, allow_empty: bool
) -> Mapping[str, Any]:
    concrete = [value for value in values if value is not None]
    if not concrete:
        if allow_empty:
            return {}
        raise MvpRadarReaderError(f"{label} is missing")
    if any(value != concrete[0] for value in concrete[1:]):
        raise MvpRadarReaderError(f"{label} projections differ")
    value = concrete[0]
    if not isinstance(value, Mapping) or (not value and not allow_empty):
        raise MvpRadarReaderError(f"{label} must be a non-empty object")
    return value


def _first_present(*mappings: Mapping[str, Any], field: str) -> object:
    for mapping in mappings:
        if field in mapping:
            return mapping[field]
    return None


def _first_mapping_value(*values: object) -> dict[str, Any]:
    for value in values:
        if isinstance(value, Mapping):
            return copy.deepcopy(dict(value))
    return {}


def _first_text(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _legacy_texts(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip()[:600] for item in value if str(item).strip()][:_MAX_MISSING]
    if value not in (None, "", {}):
        return [str(value).strip()[:600]]
    return []


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _required_mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MvpRadarReaderError(f"{field} must be an object")
    return value


def _validate_utf8_text(value: str, field: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise MvpRadarReaderError(f"{field} contains invalid Unicode") from exc


def _safe_bounded_text(value: object, limit: int) -> str:
    if not isinstance(value, str) or value != value.strip():
        return ""
    if len(value) > limit or _CONTROL_RE.search(value):
        return ""
    try:
        value.encode("utf-8")
    except UnicodeError:
        return ""
    return value


def _required_text(value: object, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise MvpRadarReaderError(f"{field} must be non-empty trimmed text")
    if len(value) > limit or _CONTROL_RE.search(value):
        raise MvpRadarReaderError(f"{field} is unsafe or too long")
    _validate_utf8_text(value, field)
    return value


def _optional_text(value: object, limit: int) -> str:
    if value in (None, ""):
        return ""
    return _required_text(value, "optional Radar text", limit)


def _required_ref(value: object, field: str) -> str:
    text = _required_text(value, field, 300)
    if not _SAFE_REF_RE.fullmatch(text):
        raise MvpRadarReaderError(f"{field} is not a safe reference")
    return text


def _required_candidate_id(value: object, *, title: str) -> str:
    candidate_id = _required_text(value, "candidate_id", 320)
    if candidate_id != f"candidate:{_normalized_candidate_key(title)}":
        raise MvpRadarReaderError("candidate_id does not match producer key")
    return candidate_id


def _optional_score(value: object, field: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
        raise MvpRadarReaderError(f"{field} must be an integer from 0 to 100")
    return value


def _text_list(
    value: object,
    field: str,
    *,
    limit: int,
    item_limit: int,
    required: bool,
) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list) or len(value) > limit:
        raise MvpRadarReaderError(f"{field} must be a bounded list")
    result = [_required_text(item, field, item_limit) for item in value]
    if required and not result:
        raise MvpRadarReaderError(f"{field} must not be empty")
    if len(result) != len(set(result)):
        raise MvpRadarReaderError(f"{field} contains duplicates")
    return result


def _ref_list(value: object, field: str, *, limit: int) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        raise MvpRadarReaderError(f"{field} must be a bounded list")
    result = [_required_ref(str(item), field) for item in value]
    if len(result) != len(set(result)):
        raise MvpRadarReaderError(f"{field} contains duplicates")
    return result


def _url_list(value: object, field: str, *, limit: int) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        raise MvpRadarReaderError(f"{field} must be a bounded list")
    result = [_safe_url(item, field, required=True) for item in value]
    if len(result) != len(set(result)):
        raise MvpRadarReaderError(f"{field} contains duplicates")
    return result


def _safe_url(value: object, field: str, *, required: bool) -> str:
    if value in (None, "") and not required:
        return ""
    text = _required_text(value, field, 2000)
    try:
        parsed = urlsplit(text)
        hostname = parsed.hostname
    except ValueError as exc:
        raise MvpRadarReaderError(f"{field} must be a safe HTTP(S) URL") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or parsed.username
        or parsed.password is not None
        or any(char.isspace() for char in parsed.netloc)
        or any(char.isspace() for char in hostname)
    ):
        raise MvpRadarReaderError(f"{field} must be a safe HTTP(S) URL")
    return text


def _bound_path(base: Path, value: object) -> Path:
    text = _required_text(value, "bound Radar path", 2000)
    path = Path(text)
    return path if path.is_absolute() else base / path


def _load_json_object(
    path: Path,
    label: str,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    value = _load_json_value(
        path,
        label,
        expected_sha256=expected_sha256,
    )
    if not isinstance(value, dict):
        raise MvpRadarReaderError(f"{label} must be an object")
    return value


def _load_json_array(
    path: Path,
    label: str,
    *,
    expected_sha256: str | None = None,
) -> list[object]:
    value = _load_json_value(
        path,
        label,
        expected_sha256=expected_sha256,
    )
    if not isinstance(value, list):
        raise MvpRadarReaderError(f"{label} must be an array")
    return value


def _load_json_value(
    path: Path,
    label: str,
    *,
    expected_sha256: str | None,
) -> object:
    file_descriptor: int | None = None
    try:
        file_descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        metadata = os.fstat(file_descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise MvpRadarReaderError(f"{label} must be a regular file")
        with os.fdopen(file_descriptor, "rb") as handle:
            file_descriptor = None
            data = handle.read(_MAX_BOUND_JSON_BYTES + 1)
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
    if len(data) > _MAX_BOUND_JSON_BYTES:
        raise MvpRadarReaderError(f"{label} exceeds the bounded reader byte limit")
    actual_sha256 = hashlib.sha256(data).hexdigest()
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise MvpRadarReaderError(f"{label} checksum mismatch")
    try:
        text = data.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
            parse_float=_strict_json_float,
        )
    except (json.JSONDecodeError, UnicodeError, RecursionError, OverflowError) as exc:
        raise MvpRadarReaderError(f"invalid {label}: {exc}") from exc


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise MvpRadarReaderError(f"duplicate JSON key is forbidden: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> object:
    raise MvpRadarReaderError(f"non-finite JSON number is forbidden: {value}")


def _strict_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise MvpRadarReaderError(f"non-finite JSON number is forbidden: {value}")
    return parsed


def _safe_reason(error: BaseException) -> str:
    text = " ".join(str(error).split())[:260]
    return text or error.__class__.__name__
