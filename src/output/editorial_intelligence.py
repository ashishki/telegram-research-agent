"""IRX-5 bounded editorial synthesis and strict shadow-artifact contract."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from llm.client import LLMCompletionReceipt, complete_with_receipt
from llm.router import route
from output.ai_report_contract import (
    RADAR_INTELLIGENCE_CONTRACT_VERSION,
    build_canonical_intelligence_contract,
    validate_canonical_intelligence_contract,
)
from output.editorial_intelligence_prompt import (
    EDITORIAL_MAX_PROJECT_ACTIONS,
    EDITORIAL_MAX_SIGNALS,
    EDITORIAL_MAX_TOKENS,
    EDITORIAL_PROMPT_VERSION,
    EDITORIAL_SCHEMA_VERSION,
    build_editorial_prompt,
)
from output.mvp_radar_reader import load_bound_mvp_radar_reader
from output.reaction_personalization import (
    ReactionPersonalizationError,
    validate_reaction_effect,
)
from output.weekly_run_manifest import (
    RadarBindingError,
    SUCCEEDED,
    WeeklyRunManifestError,
    load_bound_reaction_snapshot,
    load_manifest,
    validate_radar_run_binding,
    verify_file_checksum,
)


EDITORIAL_INPUT_SCHEMA_VERSION = "editorial_intelligence_input.v1"
EDITORIAL_RECEIPT_SCHEMA_VERSION = "editorial_intelligence_generation.v1"
EDITORIAL_ARTIFACT_FILENAME = "editorial-intelligence.v1.json"
MAX_SIGNAL_CANDIDATES = 8
MAX_RAW_SIGNAL_INPUTS = 32
MAX_EVIDENCE_ITEMS = 24
MAX_FEEDBACK_EVENTS = 20
MAX_FEEDBACK_TARGETS = 8
MAX_INPUT_JSON_CHARS = 80_000
PLANNED_COST_CEILING_USD = 0.80

_MODEL_TOP_LEVEL_FIELDS = {
    "schema_version",
    "run_id",
    "reporting_period",
    "weekly_thesis",
    "decision_matrix",
    "signals",
    "project_actions",
    "feedback_effect",
    "mvp_summary",
    "visual_specs",
    "feedback_targets",
}
_FINAL_TOP_LEVEL_FIELDS = _MODEL_TOP_LEVEL_FIELDS | {
    "generation_status",
    "partial",
    "fallback_reason",
    "generation_receipt",
}
_PERIOD_FIELDS = {
    "reporting_week",
    "analysis_period_start",
    "analysis_period_end",
}
_THESIS_FIELDS = {
    "title",
    "plain_language_summary",
    "why_for_operator",
    "confidence",
    "evidence_refs",
}
_SIGNAL_FIELDS = {
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
}
_REACTION_FIELDS = {"effect", "reader_reason_ru"}
_NEXT_ACTION_FIELDS = {"title", "acceptance_criteria"}
_FEEDBACK_FIELDS = {
    "confirmed_events_considered",
    "applied_changes",
    "unchanged",
    "code_config_required",
    "rejected",
    "pending",
}
_FEEDBACK_ITEM_FIELDS = {"feedback_ref", "reader_summary_ru"}
_MVP_FIELDS = {"radar_ref", "reader_decision", "why", "what_would_change_it"}
_MATRIX_FIELDS = {"act", "study", "watch", "ignore"}
_CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
_SIGNAL_DECISIONS = {"act", "study", "watch", "ignore", "verify_first"}
_REACTION_EFFECTS = {"selection_changed", "rank_changed", "linked_only", "none"}
_RADAR_DECISIONS = {"investigate", "reject", "build_allowed", "unavailable"}
_CAUTIOUS_MARKERS_RU = (
    "пока",
    "предвар",
    "недостаточ",
    "требует провер",
    "нужно провер",
    "не подтвержден",
    "не подтверждён",
    "нельзя считать",
    "не стоит",
    "не начина",
    "возможно",
    "неясно",
    "ограничен",
)
_GENERIC_ACTIONS = {
    "изучить подробнее",
    "провести исследование",
    "провести анализ",
    "продолжить наблюдение",
    "проверить на практике",
    "посмотреть источники",
    "сделать эксперимент",
    "узнать больше",
    "study more",
    "do more research",
    "keep watching",
}
_GENERIC_ACTION_VOCABULARY = {
    "анализ",
    "больше",
    "более",
    "вопрос",
    "далее",
    "дальше",
    "детальнее",
    "еще",
    "ещё",
    "изучить",
    "исследование",
    "исследовать",
    "источники",
    "наблюдать",
    "подробнее",
    "посмотреть",
    "практике",
    "проверить",
    "провести",
    "продолжить",
    "сделать",
    "сигнал",
    "тема",
    "темы",
    "это",
}
_HTML_RE = re.compile(r"<\s*(?:![^>]*|/?\s*[A-Za-z][^>]*)>", re.I)
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LETTER_RE = re.compile(r"[A-Za-zА-Яа-яЁё]")
_SPACE_RE = re.compile(r"\s+")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{5,199}$")
_CANONICAL_THREAD_REF_RE = re.compile(
    r"^canonical_thread:[A-Za-z0-9][A-Za-z0-9._-]{0,199}$"
)
_ISO_WEEK_RE = re.compile(r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RADAR_BUILD_APPROVAL_RE = re.compile(
    r"(?:radar.{0,80}(?:разрешил|одобрил).{0,60}(?:сборк|build)|"
    r"(?:сборк|build).{0,50}(?:разрешена|разрешён|разрешен|одобрен|"
    r"можно\s+начинать)|(?:начать|запустить|приступить\s+к).{0,25}"
    r"(?:сборк|build))",
    re.I,
)
_PERSISTENT_MUTATION_RE = re.compile(
    r"(?:(?:измен|обнов|внедр|перепис|настро|развер|задепло|депло|"
    r"выкат|добав|удал|запуст|релизн|выпуст|модифиц|мигрир).{0,120}"
    r"(?:код|конфиг|проект|продакш|production|систем|deploy|релиз|mvp)|"
    r"(?:код|конфиг|проект|продакш|production|систем|deploy|релиз|mvp)"
    r".{0,120}(?:измен|обнов|внедр|перепис|настро|развер|задепло|депло|"
    r"выкат|добав|удал|запуст|релизн|выпуст|модифиц|мигрир))",
    re.I,
)
_UNPERMITTED_ACTION_DOMAIN_RE = re.compile(
    r"\b(?:код\w*|конфиг\w*|проект\w*|продакш\w*|production\w*|"
    r"deploy\w*|депло\w*|выкат\w*|релиз\w*|pr|merge\w*|commit\w*|"
    r"ветк\w*|репозитор\w*|реализац\w*)\b",
    re.I,
)
_INVESTIGATION_ACTION_RE = re.compile(
    r"(?:провер|свер|изуч|исслед|измер|сравн|подтверд|опроверг|наблюд|"
    r"найт|найти|запрос|воспроизв|оцен)",
    re.I,
)
_READINESS_SUBJECT_RE = re.compile(r"(?:radar|mvp|кандидат)", re.I)
_READINESS_CLAIM_RE = re.compile(
    r"(?:полностью\s+)?готов|готовност|можно\s+(?:выпуск|запуск|собир)|"
    r"разреш[еиё]н|одобрен|выпуск|релиз|launch|build[- ]?ready|"
    r"зел[её]н\w*\s+свет|пора\s+(?:отправ|выпуск|запуск)|готов\s+к\s+merge",
    re.I,
)
_READINESS_NEGATION_RE = re.compile(
    r"(?:не\s+готов|не\s+разреш|не\s+одобрен|нельзя|нет\s+основан|"
    r"только\s+(?:провер|исслед)|пока\s+не)",
    re.I,
)
_MUTATION_NEGATION_RE = re.compile(
    r"(?:не|нельзя|запрещено|избегать|отложить).{0,35}"
    r"(?:измен|обнов|внедр|перепис|настро|развер|задепло|депло|выкат|"
    r"добав|удал|запуст|релизн|выпуст|модифиц|мигрир|сборк)",
    re.I,
)
_COMPLETE_REACTION_STATUSES = {
    "effects_applied",
    "linked_no_selection_effect",
    "no_eligible_reactions",
}
_FAILED_RADAR_STATUS_MARKERS = {
    "disabled",
    "error",
    "failed",
    "failure",
    "missing",
    "partial",
    "skipped",
    "unavailable",
}
_SUPPORTED_RADAR_SCHEMA_VERSIONS = {
    "mvp_of_week.v1",
    "demand_mvp_radar.mvp_of_week.v1",
}


class EditorialIntelligenceError(ValueError):
    """Base failure for bounded editorial synthesis."""


class EditorialInputError(EditorialIntelligenceError):
    """The deterministic package is incomplete or identity-inconsistent."""


class EditorialValidationError(EditorialIntelligenceError):
    """The model or cached artifact violated the strict contract."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(str(error) for error in errors if str(error).strip())
        super().__init__("; ".join(self.errors) or "editorial validation failed")


@dataclass(frozen=True, slots=True)
class EditorialIntelligenceSummary:
    path: str
    run_id: str
    reporting_week: str
    generation_status: str
    partial: bool
    signal_count: int
    model: str
    prompt_version: str
    input_hash: str
    estimated_cost_usd: float
    skipped_existing: bool = False


def build_editorial_input_package(
    context: Mapping[str, object],
    *,
    run_identity: Mapping[str, object],
    radar_binding: Mapping[str, object] | None = None,
    project_permissions: Sequence[Mapping[str, object]] | None = None,
    feedback_snapshot_count: int | None = None,
) -> dict[str, object]:
    """Build one bounded package after deterministic selection and gates.

    ``context['threads']`` is already ordered by the existing deterministic and
    IRX-3 selectors.  This function preserves that order and never reads the
    archive, reranks candidates, or grants a project/Radar permission.
    """

    if not isinstance(context, Mapping):
        raise EditorialInputError("context must be an object")
    if not isinstance(run_identity, Mapping):
        raise EditorialInputError("run_identity must be an object")
    run_id = _required_text(run_identity.get("run_id"), "run_identity.run_id")
    if not _RUN_ID_RE.fullmatch(run_id):
        raise EditorialInputError("run_identity.run_id is invalid")
    period = _period_from_context(context)
    _validate_run_identity(context, run_identity, period)

    run_context, identity_partial_reasons = _run_context_package(
        context,
        run_identity,
        period,
    )
    canonical_contract = build_canonical_intelligence_contract(context)
    canonical_contract_findings = validate_canonical_intelligence_contract(
        canonical_contract
    )
    canonical_contract_partial_reasons = (
        ["canonical_intelligence_contract_invalid"]
        if any(finding.severity == "critical" for finding in canonical_contract_findings)
        else []
    )
    source_observation_ids = {
        str(item.get("id"))
        for item in _mapping_list(canonical_contract.get("source_observations"))
        if str(item.get("id") or "").strip()
    }
    evidence_by_id = {
        str(item.get("id")): dict(item)
        for item in _mapping_list(canonical_contract.get("evidence_items"))
        if str(item.get("id") or "").strip()
        and str(item.get("source_observation_id") or "")
        in source_observation_ids
        and str(item.get("evidence_tier") or "unsupported") != "unsupported"
        and item.get("context_only") is not True
    }
    claims_by_id = {
        str(item.get("id")): dict(item)
        for item in _mapping_list(canonical_contract.get("claims"))
        if str(item.get("id") or "").strip()
    }
    contract_threads = {
        str(item.get("thread_slug")): dict(item)
        for item in _mapping_list(canonical_contract.get("idea_threads"))
        if str(item.get("thread_slug") or "").strip()
    }

    canonical_by_ref: dict[str, Mapping[str, object]] = {}
    for canonical in _mapping_list(context.get("canonical_threads")):
        raw_stable_slug = canonical.get("stable_slug")
        stable_slug = (
            raw_stable_slug.strip()
            if isinstance(raw_stable_slug, str)
            and raw_stable_slug == raw_stable_slug.strip()
            else ""
        )
        raw_canonical_ref = canonical.get("canonical_thread_ref")
        canonical_ref = (
            raw_canonical_ref
            if isinstance(raw_canonical_ref, str)
            and raw_canonical_ref == raw_canonical_ref.strip()
            else ""
        )
        if not canonical_ref and stable_slug:
            canonical_ref = f"canonical_thread:{stable_slug}"
        if canonical_ref and _CANONICAL_THREAD_REF_RE.fullmatch(canonical_ref):
            if canonical_ref in canonical_by_ref:
                raise EditorialInputError(
                    "canonical thread refs must be unique in the bounded context"
                )
            canonical_by_ref[canonical_ref] = canonical

    reaction_receipt, reaction_partial_reasons = _validated_reaction_receipt(
        context,
        run_id=run_id,
        period=period,
    )
    candidates: list[dict[str, object]] = []
    candidate_by_id: dict[str, dict[str, object]] = {}
    canonical_resolution_incomplete = False
    for thread in _mapping_list(context.get("threads"))[:MAX_RAW_SIGNAL_INPUTS]:
        slug = str(thread.get("slug") or "").strip()
        if not slug:
            continue
        raw_canonical_refs = thread.get("canonical_thread_refs")
        canonical_refs = (
            list(raw_canonical_refs[:4])
            if isinstance(raw_canonical_refs, list)
            and all(
                isinstance(value, str)
                and bool(value)
                and value == value.strip()
                for value in raw_canonical_refs
            )
            and len(raw_canonical_refs) == len(set(raw_canonical_refs))
            else []
        )
        if len(canonical_refs) == 1 and _CANONICAL_THREAD_REF_RE.fullmatch(
            canonical_refs[0]
        ):
            signal_id = f"signal:{canonical_refs[0].split(':', maxsplit=1)[1]}"
        else:
            signal_id = f"signal:{slug}"
        contract_thread = contract_threads.get(slug, {})
        evidence_refs = [
            str(value)
            for value in contract_thread.get("evidence_item_ids") or []
            if str(value) in evidence_by_id
        ]
        evidence_refs = _unique_strings(evidence_refs)[:6]
        # A source-grounded editorial signal without a resolvable eligible ref
        # is not selectable.  It remains available in the existing Audit/V1
        # surfaces but never becomes an uncited IRX-5 claim.
        if not evidence_refs:
            continue
        canonical = (
            canonical_by_ref.get(canonical_refs[0])
            if len(canonical_refs) == 1
            and _CANONICAL_THREAD_REF_RE.fullmatch(canonical_refs[0])
            else None
        )
        if canonical is None:
            canonical_resolution_incomplete = True
            continue
        if signal_id in candidate_by_id:
            # IRX-4 canonical identity collapses compatibility fragments while
            # retaining the first IRX-3-selected position and all bounded refs.
            existing = candidate_by_id[signal_id]
            existing["source_thread_refs"] = _unique_strings(
                [*(existing.get("source_thread_refs") or []), f"idea_thread:{slug}"]
            )
            existing["evidence_refs"] = _unique_strings(
                [*(existing.get("evidence_refs") or []), *evidence_refs]
            )[:8]
            existing["reaction_effect"] = _stronger_reaction_effect(
                _as_mapping(existing.get("reaction_effect")),
                _candidate_reaction_effect(reaction_receipt, slug),
            )
            continue
        semantic_source = canonical
        candidate = {
            "signal_id": signal_id,
            "source_thread_refs": [f"idea_thread:{slug}"],
            "canonical_thread_refs": canonical_refs,
            "title": _bounded_text(
                semantic_source.get("title")
                or semantic_source.get("title_ru")
                or semantic_source.get("title_en")
                or slug,
                240,
            ),
            "summary": _bounded_text(
                semantic_source.get("summary")
                or semantic_source.get("thesis")
                or "",
                500,
            ),
            "status": _bounded_text(
                semantic_source.get("status") or "active",
                80,
            ),
            "changed_this_week": bool(semantic_source.get("changed_this_week")),
            "current_claims": [
                _bounded_text(value, 360)
                for value in (semantic_source.get("current_claims") or [])[:3]
                if str(value).strip()
            ],
            "evidence_refs": evidence_refs,
            "reaction_effect": _candidate_reaction_effect(reaction_receipt, slug),
        }
        candidates.append(candidate)
        candidate_by_id[signal_id] = candidate

    # Collapse compatibility fragments across the bounded raw input before the
    # editorial candidate cap, otherwise one fragmented canonical topic can
    # crowd out distinct preselected topics.
    candidates = candidates[:MAX_SIGNAL_CANDIDATES]
    selected_evidence = _unique_strings(
        [ref for candidate in candidates for ref in candidate["evidence_refs"]]
    )[:MAX_EVIDENCE_ITEMS]
    selected_evidence_set = set(selected_evidence)
    for candidate in candidates:
        candidate["evidence_refs"] = [
            ref for ref in candidate["evidence_refs"] if ref in selected_evidence_set
        ]
    candidates = [candidate for candidate in candidates if candidate["evidence_refs"]]
    for candidate in candidates:
        confidence_ceiling = _candidate_confidence_ceiling(
            candidate["evidence_refs"],
            evidence_by_id=evidence_by_id,
            claims_by_id=claims_by_id,
        )
        allowed_decisions = ["study", "watch", "ignore", "verify_first"]
        if confidence_ceiling in {"medium", "high"}:
            allowed_decisions.insert(0, "act")
        candidate["confidence_ceiling"] = confidence_ceiling
        candidate["allowed_decisions"] = allowed_decisions
    evidence_catalog = [
        _evidence_prompt_item(evidence_by_id[evidence_id], claims_by_id)
        for evidence_id in selected_evidence
    ]

    feedback, feedback_partial_reasons = _feedback_permissions(
        context.get("feedback_context"),
        feedback_snapshot_count=feedback_snapshot_count,
        feedback_snapshot_usable=context.get("feedback_snapshot_usable"),
        feedback_snapshot_at=context.get("feedback_snapshot_at"),
        expected_cutoff=period["analysis_period_end"],
    )
    projects = _project_permission_package(project_permissions or (), candidates)
    radar, radar_partial_reasons = _radar_permission_package(
        run_id=run_id,
        period=period,
        run_context=run_context,
        binding=radar_binding,
    )
    candidate_confidences = [
        str(candidate["confidence_ceiling"]) for candidate in candidates
    ]
    thesis_ceiling = max(
        candidate_confidences,
        key=lambda value: _CONFIDENCE_ORDER[value],
        default="low",
    )
    canonical_snapshot, canonical_partial_reasons = _canonical_snapshot_package(
        context.get("canonical_thread_snapshot"),
        period=period,
    )
    if canonical_resolution_incomplete:
        canonical_partial_reasons.append("canonical_resolution_incomplete")
    partial_reasons = _unique_strings(
        [
            *identity_partial_reasons,
            *canonical_contract_partial_reasons,
            *canonical_partial_reasons,
            *reaction_partial_reasons,
            *feedback_partial_reasons,
            *radar_partial_reasons,
        ]
    )[:12]

    package: dict[str, object] = {
        "schema_version": EDITORIAL_INPUT_SCHEMA_VERSION,
        "run_id": run_id,
        "reporting_period": period,
        "run_context": run_context,
        "release_policy": {
            "requires_partial": bool(partial_reasons),
            "model_call_allowed": not partial_reasons,
            "partial_reasons": partial_reasons,
        },
        "selection_policy": {
            "owner": "deterministic_preselected_context",
            "preserve_input_order": True,
            "max_signal_candidates": MAX_SIGNAL_CANDIDATES,
            "max_output_signals": EDITORIAL_MAX_SIGNALS,
            "max_input_json_chars": MAX_INPUT_JSON_CHARS,
            "max_output_tokens": EDITORIAL_MAX_TOKENS,
            "planned_cost_ceiling_usd": PLANNED_COST_CEILING_USD,
            "verify_first_matrix_bucket": "study",
            "model_may_rerank_or_expand": False,
            "thesis_confidence_ceiling": thesis_ceiling,
        },
        "zero_change_thesis": _zero_change_thesis(),
        "signal_candidates": candidates,
        "evidence_catalog": evidence_catalog,
        "canonical_snapshot": canonical_snapshot,
        "reaction_policy": {
            "absence_semantics": "unknown_not_negative",
            "model_may_recompute_effect": False,
        },
        "feedback_permissions": feedback,
        "project_permissions": projects,
        "radar_permission": radar,
        # IRX-8 and IRX-12 own these systems.  IRX-5 exposes explicit empty
        # permission sets so the model cannot invent their records early.
        "visual_spec_permissions": [],
        "feedback_target_permissions": [],
        "frontier_context": _frontier_prompt_context(context.get("frontier_analysis")),
        "bounds": {
            "signal_candidates": len(candidates),
            "evidence_items": len(evidence_catalog),
            "feedback_events": int(feedback["confirmed_events_considered"]),
            "project_actions": len(projects),
        },
    }
    _ensure_json(package, field="editorial input package")
    package_size = len(json.dumps(package, ensure_ascii=False, sort_keys=True))
    if package_size > MAX_INPUT_JSON_CHARS:
        raise EditorialInputError(
            "editorial input package exceeds the bounded size limit"
        )
    return package


def validate_editorial_model_output(
    payload: Mapping[str, object],
    *,
    input_package: Mapping[str, object],
) -> dict[str, object]:
    """Validate and normalize strict model-authored JSON against permissions."""

    errors: list[str] = []
    if not isinstance(payload, Mapping):
        raise EditorialValidationError(("model output must be an object",))
    output = dict(payload)
    _exact_keys(output, _MODEL_TOP_LEVEL_FIELDS, "root", errors)
    if output.get("schema_version") != EDITORIAL_SCHEMA_VERSION:
        errors.append("schema_version mismatch")
    if output.get("run_id") != input_package.get("run_id"):
        errors.append("run_id mismatch")
    _validate_period(output.get("reporting_period"), input_package, errors)

    candidates = {
        str(item.get("signal_id")): item
        for item in _mapping_list(input_package.get("signal_candidates"))
        if str(item.get("signal_id") or "").strip()
    }
    evidence_ids = {
        str(item.get("evidence_ref"))
        for item in _mapping_list(input_package.get("evidence_catalog"))
        if str(item.get("evidence_ref") or "").strip()
    }
    thesis = _as_object(output.get("weekly_thesis"), "weekly_thesis", errors)
    _exact_keys(thesis, _THESIS_FIELDS, "weekly_thesis", errors)
    _validate_russian_fields(
        thesis,
        ("title", "plain_language_summary", "why_for_operator"),
        "weekly_thesis",
        errors,
    )
    _max_text(thesis.get("title"), 240, "weekly_thesis.title", errors)
    _max_text(
        thesis.get("plain_language_summary"),
        1_000,
        "weekly_thesis.plain_language_summary",
        errors,
    )
    _max_text(
        thesis.get("why_for_operator"), 800, "weekly_thesis.why_for_operator", errors
    )
    thesis_refs = _string_list(
        thesis.get("evidence_refs"), "weekly_thesis.evidence_refs", errors
    )
    if len(thesis_refs) > 8:
        errors.append("weekly_thesis.evidence_refs exceeds limit")
    if not set(thesis_refs).issubset(evidence_ids):
        errors.append("weekly_thesis contains unknown evidence_refs")
    thesis_confidence = _confidence(
        thesis.get("confidence"), "weekly_thesis.confidence", errors
    )
    thesis_ceiling = str(
        _as_mapping(input_package.get("selection_policy")).get(
            "thesis_confidence_ceiling"
        )
        or "low"
    )
    thesis_ref_ceiling = _refs_confidence_ceiling(
        thesis_refs,
        input_package=input_package,
    )
    if _CONFIDENCE_ORDER.get(thesis_ref_ceiling, 0) < _CONFIDENCE_ORDER.get(
        thesis_ceiling, 0
    ):
        thesis_ceiling = thesis_ref_ceiling
    _validate_confidence_ceiling(
        thesis_confidence, thesis_ceiling, "weekly_thesis", errors
    )
    if thesis_confidence == "low":
        _require_cautious_copy(
            thesis,
            ("plain_language_summary", "why_for_operator"),
            "weekly_thesis",
            errors,
        )

    signals_value = output.get("signals")
    if not isinstance(signals_value, list):
        errors.append("signals must be a list")
        signals_value = []
    changed_candidates = any(
        item.get("changed_this_week") is True for item in candidates.values()
    )
    if changed_candidates and not signals_value:
        errors.append("changed eligible candidates require at least one signal")
    if signals_value and not thesis_refs:
        errors.append("weekly_thesis requires evidence_refs when signals are returned")
    if not signals_value and thesis_confidence != "low":
        errors.append("zero-change editorial output requires low thesis confidence")
    if (
        not signals_value
        and not changed_candidates
        and thesis != input_package.get("zero_change_thesis")
    ):
        errors.append("zero-change thesis must match deterministic host projection")
    if len(signals_value) > EDITORIAL_MAX_SIGNALS:
        errors.append(f"signals exceeds limit {EDITORIAL_MAX_SIGNALS}")
    signal_ids: list[str] = []
    returned_project_refs: list[str] = []
    action_texts: list[tuple[str, str]] = []
    for index, raw_signal in enumerate(signals_value):
        path = f"signals[{index}]"
        signal = _as_object(raw_signal, path, errors)
        _exact_keys(signal, _SIGNAL_FIELDS, path, errors)
        raw_signal_id = signal.get("signal_id")
        signal_id = raw_signal_id.strip() if isinstance(raw_signal_id, str) else ""
        if not isinstance(raw_signal_id, str) or raw_signal_id != signal_id:
            errors.append(f"{path}.signal_id must be an exact non-empty string")
        if signal_id not in candidates:
            errors.append(f"{path}.signal_id is not an eligible candidate")
            candidate: Mapping[str, object] = {}
        else:
            candidate = candidates[signal_id]
        if signal_id in signal_ids:
            errors.append(f"{path}.signal_id is duplicated")
        signal_ids.append(signal_id)
        decision = str(signal.get("decision") or "")
        if decision not in _SIGNAL_DECISIONS:
            errors.append(f"{path}.decision is invalid")
        elif decision not in set(candidate.get("allowed_decisions") or []):
            errors.append(f"{path}.decision exceeds deterministic permission")
        _validate_russian_fields(
            signal,
            (
                "title",
                "what_happened",
                "plain_explanation",
                "what_changed",
                "why_for_operator",
                "do_not_do",
            ),
            path,
            errors,
        )
        _max_text(signal.get("title"), 240, f"{path}.title", errors)
        for field in (
            "what_happened",
            "plain_explanation",
            "what_changed",
            "why_for_operator",
        ):
            _max_text(signal.get(field), 900, f"{path}.{field}", errors)
        _max_text(signal.get("do_not_do"), 500, f"{path}.do_not_do", errors)
        signal_refs = _string_list(
            signal.get("evidence_refs"), f"{path}.evidence_refs", errors
        )
        allowed_signal_refs = set(candidate.get("evidence_refs") or [])
        if not signal_refs:
            errors.append(f"{path} requires evidence_refs")
        if len(signal_refs) > 8:
            errors.append(f"{path}.evidence_refs exceeds limit")
        if not set(signal_refs).issubset(allowed_signal_refs):
            errors.append(f"{path} contains cross-signal or unknown evidence_refs")
        signal_confidence = _confidence(
            signal.get("confidence"), f"{path}.confidence", errors
        )
        ceiling = str(candidate.get("confidence_ceiling") or "low")
        refs_ceiling = _refs_confidence_ceiling(
            signal_refs,
            input_package=input_package,
        )
        if _CONFIDENCE_ORDER.get(refs_ceiling, 0) < _CONFIDENCE_ORDER.get(
            ceiling, 0
        ):
            ceiling = refs_ceiling
        _validate_confidence_ceiling(signal_confidence, ceiling, path, errors)
        if signal_confidence == "low" or ceiling == "low":
            _require_cautious_copy(
                signal,
                (
                    "what_happened",
                    "plain_explanation",
                    "what_changed",
                    "why_for_operator",
                ),
                path,
                errors,
            )

        reaction = _as_object(
            signal.get("reaction_effect"), f"{path}.reaction_effect", errors
        )
        _exact_keys(reaction, _REACTION_FIELDS, f"{path}.reaction_effect", errors)
        effect = str(reaction.get("effect") or "")
        if effect not in _REACTION_EFFECTS:
            errors.append(f"{path}.reaction_effect.effect is invalid")
        expected_effect = str(
            _as_mapping(candidate.get("reaction_effect")).get("effect") or "none"
        )
        if effect != expected_effect:
            errors.append(
                f"{path}.reaction_effect does not match the validated receipt"
            )
        _require_russian(
            reaction.get("reader_reason_ru"),
            f"{path}.reaction_effect.reader_reason_ru",
            errors,
        )
        _max_text(
            reaction.get("reader_reason_ru"),
            500,
            f"{path}.reaction_effect.reader_reason_ru",
            errors,
        )
        expected_reason = str(
            _as_mapping(candidate.get("reaction_effect")).get("reader_reason_ru")
            or ""
        )
        if reaction.get("reader_reason_ru") != expected_reason:
            errors.append(
                f"{path}.reaction_effect.reader_reason_ru must match the validated receipt"
            )

        project_refs = _string_list(
            signal.get("project_implications"), f"{path}.project_implications", errors
        )
        allowed_project_refs = {
            str(item.get("project_action_ref"))
            for item in _mapping_list(input_package.get("project_permissions"))
            if str(item.get("signal_id") or "") == signal_id
        }
        if not set(project_refs).issubset(allowed_project_refs):
            errors.append(
                f"{path}.project_implications exceeds deterministic permission"
            )
        returned_project_refs.extend(project_refs)

        next_action = _as_object(
            signal.get("next_action"), f"{path}.next_action", errors
        )
        _exact_keys(next_action, _NEXT_ACTION_FIELDS, f"{path}.next_action", errors)
        action_title = _require_russian(
            next_action.get("title"), f"{path}.next_action.title", errors
        )
        _max_text(action_title, 400, f"{path}.next_action.title", errors)
        criteria = _string_list(
            next_action.get("acceptance_criteria"),
            f"{path}.next_action.acceptance_criteria",
            errors,
        )
        if not criteria:
            errors.append(f"{path}.next_action.acceptance_criteria must not be empty")
        if len(criteria) > 5:
            errors.append(f"{path}.next_action.acceptance_criteria exceeds limit")
        for criterion_index, criterion in enumerate(criteria):
            _require_russian(
                criterion,
                f"{path}.next_action.acceptance_criteria[{criterion_index}]",
                errors,
            )
            _max_text(
                criterion,
                400,
                f"{path}.next_action.acceptance_criteria[{criterion_index}]",
                errors,
            )
            action_texts.append(
                (
                    f"{path}.next_action.acceptance_criteria[{criterion_index}]",
                    criterion,
                )
            )
        do_not_do = str(signal.get("do_not_do") or "")
        action_texts.extend(
            (
                (f"{path}.next_action.title", action_title),
                (f"{path}.do_not_do", do_not_do),
            )
        )

    _validate_matrix(output.get("decision_matrix"), signal_ids, signals_value, errors)
    _validate_duplicate_or_generic_actions(action_texts, errors)
    _validate_project_actions(
        output.get("project_actions"),
        input_package,
        signal_ids,
        returned_project_refs,
        errors,
    )
    _validate_feedback_effect(output.get("feedback_effect"), input_package, errors)
    _validate_mvp_summary(output.get("mvp_summary"), input_package, errors)
    _validate_permission_ref_list(
        output.get("visual_specs"),
        input_package.get("visual_spec_permissions"),
        "visual_specs",
        errors,
    )
    _validate_permission_ref_list(
        output.get("feedback_targets"),
        input_package.get("feedback_target_permissions"),
        "feedback_targets",
        errors,
        limit=MAX_FEEDBACK_TARGETS,
    )
    _validate_narrative_permissions(output, errors)
    _reject_markup(output, errors)
    if len(json.dumps(output, ensure_ascii=False, sort_keys=True)) > 50_000:
        errors.append("editorial model output exceeds the bounded size limit")
    if errors:
        raise EditorialValidationError(errors)
    _ensure_json(output, field="editorial model output")
    return output


def synthesize_editorial_intelligence(
    input_package: Mapping[str, object],
    *,
    model: str | None = None,
    completion: Callable[..., LLMCompletionReceipt] | None = None,
    generated_at: datetime | str | None = None,
) -> dict[str, object]:
    """Synthesize an already trusted package for tests/internal composition.

    Production callers must use :func:`generate_editorial_intelligence_artifact`,
    which binds Radar and feedback inputs to persisted IRX-2 manifest bytes
    before this lower-level pure synthesis boundary can call the model.
    """

    selected_model = _select_editorial_model(model)
    input_hash = editorial_input_hash(input_package, model=selected_model)
    receipt: LLMCompletionReceipt | None = None
    failure_code: str | None = None
    validation_errors: list[str] = []
    release_policy = _as_mapping(input_package.get("release_policy"))
    release_reasons = _unique_strings(release_policy.get("partial_reasons") or [])
    release_policy_errors = _release_policy_errors(release_policy)
    if release_policy_errors:
        failure_code = "deterministic_input_partial"
        validation_errors = release_policy_errors
        model_payload = _deterministic_partial_fallback(input_package)
    elif release_policy.get("requires_partial") is True or release_reasons:
        failure_code = "deterministic_input_partial"
        validation_errors = release_reasons[:12] or ["release_policy_partial"]
        model_payload = _deterministic_partial_fallback(input_package)
    else:
        try:
            system, prompt = build_editorial_prompt(input_package)
            complete = completion or complete_with_receipt
            receipt = complete(
                prompt=prompt,
                system=system,
                max_tokens=EDITORIAL_MAX_TOKENS,
                category="editorial_intelligence",
                model=selected_model,
            )
            if not isinstance(receipt, LLMCompletionReceipt):
                raise TypeError("completion must return LLMCompletionReceipt")
            receipt_errors = _completion_receipt_errors(receipt)
            if receipt_errors:
                receipt = None
                raise EditorialValidationError(receipt_errors)
            if receipt.model != selected_model:
                raise EditorialValidationError(
                    ("completion receipt model does not match requested model",)
                )
            parsed = _strict_json_loads(receipt.text)
            if not isinstance(parsed, Mapping):
                raise EditorialValidationError(
                    ("model output must be a JSON object",)
                )
            model_payload = validate_editorial_model_output(
                parsed, input_package=input_package
            )
        except json.JSONDecodeError:
            failure_code = "invalid_json"
            model_payload = _deterministic_partial_fallback(input_package)
        except EditorialValidationError as exc:
            failure_code = "validation_failed"
            validation_errors = list(exc.errors[:12])
            model_payload = _deterministic_partial_fallback(input_package)
        except (
            Exception
        ) as exc:  # LLM/provider failures become an explicit partial artifact.
            failure_code = "model_error"
            validation_errors = [exc.__class__.__name__]
            model_payload = _deterministic_partial_fallback(input_package)

    is_partial = failure_code is not None
    artifact = {
        **model_payload,
        "generation_status": "partial" if is_partial else "complete",
        "partial": is_partial,
        "fallback_reason": failure_code,
        "generation_receipt": _generation_receipt(
            input_hash=input_hash,
            requested_model=selected_model,
            receipt=receipt,
            generated_at=generated_at,
            completion_mode="deterministic_fallback" if is_partial else "model",
            validation_errors=validation_errors,
        ),
    }
    validate_editorial_artifact(
        artifact,
        input_package=input_package,
        expected_model=selected_model,
        expected_input_hash=input_hash,
    )
    return artifact


def validate_editorial_artifact(
    artifact: Mapping[str, object],
    *,
    input_package: Mapping[str, object],
    expected_model: str | None = None,
    expected_input_hash: str | None = None,
) -> None:
    errors: list[str] = []
    if not isinstance(artifact, Mapping):
        raise EditorialValidationError(("editorial artifact must be an object",))
    payload = dict(artifact)
    _exact_keys(payload, _FINAL_TOP_LEVEL_FIELDS, "root", errors)
    status = str(payload.get("generation_status") or "")
    partial = payload.get("partial")
    fallback_reason = payload.get("fallback_reason")
    if status not in {"complete", "partial"}:
        errors.append("generation_status is invalid")
    if not isinstance(partial, bool) or partial != (status == "partial"):
        errors.append("partial projection does not match generation_status")
    if status == "complete" and fallback_reason is not None:
        errors.append("complete artifact cannot have fallback_reason")
    if status == "partial" and not str(fallback_reason or "").strip():
        errors.append("partial artifact requires fallback_reason")
    release_policy = _as_mapping(input_package.get("release_policy"))
    errors.extend(_release_policy_errors(release_policy))
    if status == "complete" and release_policy.get("requires_partial") is True:
        errors.append("complete artifact violates deterministic release policy")

    model_payload = {key: payload.get(key) for key in _MODEL_TOP_LEVEL_FIELDS}
    if status == "complete":
        try:
            validate_editorial_model_output(model_payload, input_package=input_package)
        except EditorialValidationError as exc:
            errors.extend(exc.errors)
    else:
        _validate_partial_fallback(model_payload, input_package, errors)

    generation_receipt = _as_object(
        payload.get("generation_receipt"), "generation_receipt", errors
    )
    required_receipt_fields = {
        "schema_version",
        "prompt_version",
        "editorial_schema_version",
        "requested_model",
        "model",
        "input_hash",
        "generated_at",
        "max_input_json_chars",
        "max_tokens",
        "planned_cost_ceiling_usd",
        "cost_ceiling_exceeded",
        "input_tokens",
        "output_tokens",
        "estimated_cost_usd",
        "duration_ms",
        "attempts",
        "usage_recorded",
        "completion_mode",
        "validation_errors",
    }
    _exact_keys(
        generation_receipt, required_receipt_fields, "generation_receipt", errors
    )
    if generation_receipt.get("schema_version") != EDITORIAL_RECEIPT_SCHEMA_VERSION:
        errors.append("generation_receipt.schema_version mismatch")
    if generation_receipt.get("prompt_version") != EDITORIAL_PROMPT_VERSION:
        errors.append("generation_receipt.prompt_version mismatch")
    if generation_receipt.get("editorial_schema_version") != EDITORIAL_SCHEMA_VERSION:
        errors.append("generation_receipt.editorial_schema_version mismatch")
    if (
        expected_model is not None
        and generation_receipt.get("requested_model") != expected_model
    ):
        errors.append("generation_receipt.requested_model mismatch")
    if (
        expected_input_hash is not None
        and generation_receipt.get("input_hash") != expected_input_hash
    ):
        errors.append("generation_receipt.input_hash mismatch")
    if not re.fullmatch(
        r"sha256:[0-9a-f]{64}", str(generation_receipt.get("input_hash") or "")
    ):
        errors.append("generation_receipt.input_hash is invalid")
    if not str(generation_receipt.get("model") or "").strip():
        errors.append("generation_receipt.model is required")
    if not str(generation_receipt.get("requested_model") or "").strip():
        errors.append("generation_receipt.requested_model is required")
    if (
        status == "complete"
        and generation_receipt.get("model")
        != generation_receipt.get("requested_model")
    ):
        errors.append("complete receipt model must match the requested model")
    if generation_receipt.get("max_tokens") != EDITORIAL_MAX_TOKENS:
        errors.append("generation_receipt.max_tokens mismatch")
    if generation_receipt.get("max_input_json_chars") != MAX_INPUT_JSON_CHARS:
        errors.append("generation_receipt.max_input_json_chars mismatch")
    if generation_receipt.get("planned_cost_ceiling_usd") != PLANNED_COST_CEILING_USD:
        errors.append("generation_receipt.planned_cost_ceiling_usd mismatch")
    for field in ("input_tokens", "output_tokens", "duration_ms", "attempts"):
        value = generation_receipt.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"generation_receipt.{field} must be a non-negative integer")
    cost = generation_receipt.get("estimated_cost_usd")
    if (
        not isinstance(cost, (int, float))
        or isinstance(cost, bool)
        or not math.isfinite(float(cost))
        or float(cost) < 0
    ):
        errors.append("generation_receipt.estimated_cost_usd is invalid")
    expected_cost_warning = (
        isinstance(cost, (int, float))
        and not isinstance(cost, bool)
        and float(cost) > PLANNED_COST_CEILING_USD
    )
    if generation_receipt.get("cost_ceiling_exceeded") is not expected_cost_warning:
        errors.append("generation_receipt.cost_ceiling_exceeded mismatch")
    if not isinstance(generation_receipt.get("usage_recorded"), bool):
        errors.append("generation_receipt.usage_recorded must be boolean")
    receipt_errors = generation_receipt.get("validation_errors")
    if (
        not isinstance(receipt_errors, list)
        or len(receipt_errors) > 12
        or any(
            not isinstance(value, str) or len(value) > 240
            for value in (receipt_errors or [])
        )
    ):
        errors.append("generation_receipt.validation_errors is invalid")
    if status == "complete" and generation_receipt.get("attempts", 0) < 1:
        errors.append("complete generation receipt requires at least one attempt")
    if status == "complete" and receipt_errors:
        errors.append("complete generation receipt cannot retain validation errors")
    try:
        _canonical_timestamp(str(generation_receipt.get("generated_at") or ""))
    except EditorialInputError:
        errors.append("generation_receipt.generated_at is invalid")
    expected_mode = "deterministic_fallback" if status == "partial" else "model"
    if generation_receipt.get("completion_mode") != expected_mode:
        errors.append("generation_receipt.completion_mode mismatch")
    _reject_markup(payload, errors)
    if errors:
        raise EditorialValidationError(errors)


def generate_editorial_intelligence_artifact(
    context: Mapping[str, object],
    *,
    run_identity: Mapping[str, object],
    output_root: str | os.PathLike[str],
    radar_binding: Mapping[str, object] | None = None,
    project_permissions: Sequence[Mapping[str, object]] | None = None,
    feedback_snapshot_count: int | None = None,
    model: str | None = None,
    completion: Callable[..., LLMCompletionReceipt] | None = None,
    generated_at: datetime | str | None = None,
) -> EditorialIntelligenceSummary:
    """Persist one run-scoped shadow artifact without changing V1 renderers."""

    (
        verified_radar_binding,
        verified_feedback_count,
        persisted_input_reasons,
    ) = _load_persisted_run_inputs(
        run_identity,
        supplied_radar_binding=radar_binding,
        context=context,
    )
    package = build_editorial_input_package(
        context,
        run_identity=run_identity,
        radar_binding=verified_radar_binding,
        project_permissions=project_permissions,
        feedback_snapshot_count=verified_feedback_count,
    )
    if (
        feedback_snapshot_count is not None
        and verified_feedback_count is not None
        and feedback_snapshot_count != verified_feedback_count
    ):
        persisted_input_reasons = [
            *persisted_input_reasons,
            "supplied_feedback_snapshot_count_mismatch",
        ]
    _merge_release_reasons(package, persisted_input_reasons)
    selected_model = _select_editorial_model(model)
    input_hash = editorial_input_hash(package, model=selected_model)
    root = Path(output_root)
    run_id = str(package["run_id"])
    path = root / run_id / "editorial" / EDITORIAL_ARTIFACT_FILENAME
    if path.exists():
        try:
            cached = _strict_json_loads(path.read_text(encoding="utf-8"))
            validate_editorial_artifact(
                cached,
                input_package=package,
                expected_model=selected_model,
                expected_input_hash=input_hash,
            )
            if cached.get("partial") is False:
                return _summary(path, cached, skipped_existing=True)
        except (OSError, UnicodeError, json.JSONDecodeError, EditorialValidationError) as exc:
            raise EditorialInputError(
                "editorial artifact path is immutable; use a new run_id"
            ) from exc
        raise EditorialInputError(
            "partial editorial artifact is immutable; use a new run_id"
        )
    artifact = synthesize_editorial_intelligence(
        package,
        model=selected_model,
        completion=completion,
        generated_at=generated_at,
    )
    _atomic_create_json(path, artifact)
    return _summary(path, artifact, skipped_existing=False)


def _load_persisted_run_inputs(
    run_identity: Mapping[str, object],
    *,
    supplied_radar_binding: Mapping[str, object] | None,
    context: Mapping[str, object],
) -> tuple[Mapping[str, object] | None, int | None, list[str]]:
    """Load authoritative Radar/feedback inputs from one persisted IRX-2 run.

    The in-memory binding is comparison material only.  Editorial generation
    trusts the immutable manifest binding and referenced bytes after checksum,
    containment, run/period, and stage validation.
    """

    manifest_path_value = run_identity.get("manifest_path")
    if (
        not isinstance(manifest_path_value, str)
        or not manifest_path_value
        or manifest_path_value != manifest_path_value.strip()
    ):
        return None, None, ["weekly_manifest_path_missing"]
    try:
        manifest_path = Path(manifest_path_value).resolve(strict=True)
        run_dir = manifest_path.parent
        strict_manifest = _strict_json_loads(
            manifest_path.read_text(encoding="utf-8")
        )
        manifest = load_manifest(
            manifest_path,
            path_base=run_dir,
            allowed_roots=(run_dir,),
            check_artifact_existence=False,
        )
        if not isinstance(strict_manifest, Mapping) or dict(strict_manifest) != manifest:
            raise EditorialInputError("persisted weekly manifest changed while loading")
        identity_fields = (
            "run_id",
            "run_date",
            "generated_at",
            "reporting_week",
            "analysis_period_start",
            "analysis_period_end",
            "period_mode",
            "pipeline_profile",
        )
        if any(
            not isinstance(run_identity.get(field), str)
            or run_identity.get(field) != manifest.get(field)
            for field in identity_fields
        ):
            raise EditorialInputError("persisted weekly manifest identity mismatch")
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        EditorialInputError,
        EditorialValidationError,
        WeeklyRunManifestError,
    ):
        return None, None, ["weekly_manifest_unverified"]

    reasons: list[str] = []
    stages = _as_mapping(manifest.get("stages"))
    reaction_stage = _as_mapping(stages.get("reaction_sync"))
    reaction_receipt: object = None
    reaction_effects = context.get("reaction_effects")
    if isinstance(reaction_effects, Mapping):
        reaction_receipt = reaction_effects.get("weekly_brief")
    if reaction_receipt is None:
        reaction_receipt = context.get("reaction_effect")
    try:
        expected_snapshot_ref = f"reaction-snapshot:{manifest['run_id']}"
        if (
            reaction_stage.get("status") != SUCCEEDED
            or reaction_stage.get("snapshot_ref") != expected_snapshot_ref
            or not isinstance(reaction_receipt, Mapping)
            or reaction_receipt.get("snapshot_ref") != expected_snapshot_ref
        ):
            raise EditorialInputError("reaction receipt/manifest binding mismatch")
        reaction_counts = _as_mapping(reaction_receipt.get("counts"))
        stage_counts = _as_mapping(reaction_stage.get("record_counts"))
        manifest_reaction_event_count = stage_counts.get(
            "personal_reaction_events_detected"
        )
        if (
            manifest_reaction_event_count is not None
            and reaction_counts.get("personal_reaction_events_detected")
            != manifest_reaction_event_count
        ):
            raise EditorialInputError("reaction receipt count differs from manifest")
        bound_reaction_snapshot = load_bound_reaction_snapshot(
            manifest,
            path_base=run_dir,
            allowed_roots=(run_dir,),
            verify_file=True,
        )
        if bound_reaction_snapshot is None and (
            reaction_receipt.get("status") != "no_eligible_reactions"
            or bool(reaction_receipt.get("influenced_items"))
            or bool(reaction_receipt.get("linked_only_items"))
        ):
            raise EditorialInputError(
                "legacy unbound reaction stage cannot support personalization"
            )
    except (EditorialInputError, WeeklyRunManifestError):
        reasons.append("reaction_receipt_integrity_invalid")

    feedback_stage = _as_mapping(stages.get("feedback_snapshot"))
    feedback_count: int | None = None
    raw_feedback_count = feedback_stage.get("confirmed_event_count")
    if (
        feedback_stage.get("status") == SUCCEEDED
        and feedback_stage.get("cutoff") == manifest.get("analysis_period_end")
        and isinstance(raw_feedback_count, int)
        and not isinstance(raw_feedback_count, bool)
        and raw_feedback_count >= 0
    ):
        feedback_count = raw_feedback_count
    else:
        reasons.append("feedback_snapshot_not_succeeded")

    radar_stage = _as_mapping(stages.get("radar"))
    authoritative_binding: Mapping[str, object] | None = None
    try:
        if radar_stage.get("status") != SUCCEEDED:
            raise EditorialInputError("persisted Radar stage is not succeeded")
        binding_path = _resolve_run_artifact_path(
            run_dir,
            radar_stage.get("binding_path"),
            field="stages.radar.binding_path",
        )
        binding_sha256 = radar_stage.get("binding_sha256")
        if not isinstance(binding_sha256, str):
            raise EditorialInputError("persisted Radar binding checksum is missing")
        verify_file_checksum(binding_path, binding_sha256)
        loaded_binding = _strict_json_loads(binding_path.read_text(encoding="utf-8"))
        if not isinstance(loaded_binding, Mapping):
            raise EditorialInputError("persisted Radar binding must be an object")
        authoritative_binding = dict(loaded_binding)
        if supplied_radar_binding is not None and dict(supplied_radar_binding) != dict(
            authoritative_binding
        ):
            raise EditorialInputError("supplied Radar binding differs from manifest")
        validate_radar_run_binding(
            authoritative_binding,
            manifest=manifest,
            path_base=run_dir,
            allowed_roots=(run_dir,),
            verify_files=True,
        )
        ref_parity = (
            ("seed_export_ref", "path", "seed_export_path"),
            ("seed_export_ref", "sha256", "seed_export_sha256"),
            ("radar_json_ref", "path", "artifact_path"),
            ("radar_json_ref", "sha256", "artifact_sha256"),
        )
        for ref_name, ref_field, stage_field in ref_parity:
            ref = _as_mapping(authoritative_binding.get(ref_name))
            if ref.get(ref_field) != radar_stage.get(stage_field):
                raise EditorialInputError(
                    f"persisted Radar binding/stage mismatch for {stage_field}"
                )
        reader = load_bound_mvp_radar_reader(
            manifest,
            path_base=run_dir,
            allowed_roots=(run_dir,),
        )
        if reader.get("reader_state") not in {"available", "no_candidate"}:
            raise EditorialInputError(
                "persisted Radar bytes do not satisfy the reader contract"
            )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        EditorialInputError,
        EditorialValidationError,
        WeeklyRunManifestError,
    ):
        authoritative_binding = None
        reasons.append("radar_binding_integrity_invalid")
    return authoritative_binding, feedback_count, _unique_strings(reasons)


def _resolve_run_artifact_path(
    run_dir: Path,
    value: object,
    *,
    field: str,
) -> Path:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EditorialInputError(f"{field} is invalid")
    candidate = Path(value)
    resolved = (candidate if candidate.is_absolute() else run_dir / candidate).resolve(
        strict=True
    )
    try:
        resolved.relative_to(run_dir)
    except ValueError as exc:
        raise EditorialInputError(f"{field} escapes the persisted run") from exc
    return resolved


def _merge_release_reasons(
    package: dict[str, object],
    reasons: Sequence[str],
) -> None:
    policy = _as_mapping(package.get("release_policy"))
    merged = _unique_strings(
        [*(policy.get("partial_reasons") or []), *reasons]
    )[:12]
    package["release_policy"] = {
        "requires_partial": bool(merged),
        "model_call_allowed": not merged,
        "partial_reasons": merged,
    }


def editorial_input_hash(input_package: Mapping[str, object], *, model: str) -> str:
    envelope = {
        "schema_version": EDITORIAL_SCHEMA_VERSION,
        "prompt_version": EDITORIAL_PROMPT_VERSION,
        "model": str(model),
        "max_tokens": EDITORIAL_MAX_TOKENS,
        "input_package": dict(input_package),
    }
    encoded = json.dumps(
        envelope,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _select_editorial_model(model: str | None) -> str:
    required_model = str(route("synthesis")).strip()
    if model is not None and (
        not isinstance(model, str) or not model or model != model.strip()
    ):
        raise EditorialInputError(
            "editorial synthesis model must match the strong synthesis route"
        )
    selected_model = required_model if model is None else model
    if not required_model or selected_model != required_model:
        raise EditorialInputError(
            "editorial synthesis model must match the strong synthesis route"
        )
    return selected_model


def _period_from_context(context: Mapping[str, object]) -> dict[str, str]:
    aliases = {
        "reporting_week": "week_label",
        "analysis_period_start": "week_start",
        "analysis_period_end": "week_end",
    }
    period: dict[str, str] = {}
    for field, alias in aliases.items():
        raw_value = context.get(field)
        if raw_value is None or raw_value == "":
            raw_value = context.get(alias)
        if (
            not isinstance(raw_value, str)
            or not raw_value
            or raw_value != raw_value.strip()
        ):
            raise EditorialInputError(f"context.{field} is required")
        period[field] = raw_value
    return period


def _zero_change_thesis() -> dict[str, object]:
    return {
        "title": "За период нет подтвержденных изменений",
        "plain_language_summary": (
            "Пока среди допустимых сигналов не найдено нового изменения, "
            "подкрепленного достаточными проверяемыми доказательствами."
        ),
        "why_for_operator": (
            "Не начинайте сборку или изменение проекта по этой неделе; "
            "сохраните наблюдение до появления проверяемого изменения."
        ),
        "confidence": "low",
        "evidence_refs": [],
    }


def _release_policy_errors(value: Mapping[str, object]) -> list[str]:
    expected = {"requires_partial", "model_call_allowed", "partial_reasons"}
    if set(value) != expected:
        return ["release_policy fields mismatch"]
    requires_partial = value.get("requires_partial")
    model_call_allowed = value.get("model_call_allowed")
    raw_reasons = value.get("partial_reasons")
    if not isinstance(requires_partial, bool) or not isinstance(
        model_call_allowed, bool
    ):
        return ["release_policy boolean projection is invalid"]
    if (
        not isinstance(raw_reasons, list)
        or len(raw_reasons) > 12
        or any(not isinstance(item, str) or not item.strip() for item in raw_reasons)
        or len(raw_reasons) != len(set(raw_reasons))
    ):
        return ["release_policy partial reasons are invalid"]
    if requires_partial != bool(raw_reasons) or model_call_allowed == requires_partial:
        return ["release_policy state projection is inconsistent"]
    return []


def _strict_json_loads(text: str) -> object:
    def object_from_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise EditorialValidationError((f"duplicate JSON key: {key}",))
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise EditorialValidationError((f"non-finite JSON number: {value}",))

    return json.loads(
        text,
        object_pairs_hook=object_from_pairs,
        parse_constant=reject_constant,
    )


def _validate_run_identity(
    context: Mapping[str, object],
    identity: Mapping[str, object],
    period: Mapping[str, str],
) -> None:
    for field in _PERIOD_FIELDS:
        identity_value = str(identity.get(field) or "").strip()
        if identity_value and identity_value != period[field]:
            raise EditorialInputError(f"run_identity.{field} mismatch")
    context_run_id = str(context.get("run_id") or "").strip()
    if context_run_id and context_run_id != str(identity.get("run_id") or "").strip():
        raise EditorialInputError("context.run_id mismatch")
    for field in ("run_date", "generated_at", "period_mode"):
        identity_value = str(identity.get(field) or "").strip()
        context_value = str(context.get(field) or "").strip()
        if identity_value and context_value and identity_value != context_value:
            raise EditorialInputError(f"run_identity.{field} mismatch")


def _run_context_package(
    context: Mapping[str, object],
    identity: Mapping[str, object],
    period: Mapping[str, str],
) -> tuple[dict[str, str], list[str]]:
    reasons: list[str] = []
    for field in _PERIOD_FIELDS:
        if str(identity.get(field) or "").strip() != period[field]:
            reasons.append(f"run_identity_{field}_missing")
    reporting_week = str(period.get("reporting_week") or "")
    if not _ISO_WEEK_RE.fullmatch(reporting_week):
        reasons.append("reporting_week_invalid")
    for field in ("analysis_period_start", "analysis_period_end"):
        try:
            _canonical_timestamp(period[field])
        except EditorialInputError:
            reasons.append(f"{field}_invalid")

    result: dict[str, str] = {}
    for field, limit in (
        ("run_date", 40),
        ("generated_at", 80),
        ("period_mode", 80),
        ("pipeline_profile", 120),
        ("manifest_path", 2_000),
    ):
        value = str(identity.get(field) or "").strip()
        result[field] = _bounded_text(value, limit)
        if not value:
            reasons.append(f"run_identity_{field}_missing")
    if result["generated_at"]:
        try:
            _canonical_timestamp(result["generated_at"])
        except EditorialInputError:
            reasons.append("run_identity_generated_at_invalid")
    return result, _unique_strings(reasons)


def _canonical_snapshot_package(
    value: object,
    *,
    period: Mapping[str, str],
) -> tuple[dict[str, str], list[str]]:
    snapshot = dict(value) if isinstance(value, Mapping) else {}
    result = {
        "schema_version": _bounded_text(snapshot.get("schema_version") or "", 120),
        "as_of": _bounded_text(snapshot.get("as_of") or "", 80),
        "fingerprint": _bounded_text(snapshot.get("fingerprint") or "", 160),
    }
    reasons: list[str] = []
    if result["schema_version"] != "canonical_idea_threads.snapshot.v1":
        reasons.append("canonical_snapshot_schema_invalid")
    if result["as_of"] != period["analysis_period_end"]:
        reasons.append("canonical_snapshot_as_of_mismatch")
    if not _SHA256_RE.fullmatch(result["fingerprint"]):
        reasons.append("canonical_snapshot_fingerprint_invalid")
    return result, reasons


def _validated_reaction_receipt(
    context: Mapping[str, object],
    *,
    run_id: str,
    period: Mapping[str, str],
) -> tuple[Mapping[str, object], list[str]]:
    receipt: object = None
    effects = context.get("reaction_effects")
    if isinstance(effects, Mapping):
        receipt = effects.get("weekly_brief")
    if receipt is None:
        candidate = context.get("reaction_effect")
        if isinstance(candidate, Mapping):
            receipt = candidate
    if not isinstance(receipt, Mapping):
        return {}, ["reaction_receipt_missing"]
    try:
        validated = validate_reaction_effect(receipt)
    except ReactionPersonalizationError:
        return {}, ["reaction_receipt_invalid"]
    expected_identity = {
        "run_id": run_id,
        "surface": "weekly_brief",
        **period,
    }
    if any(validated.get(field) != value for field, value in expected_identity.items()):
        return {}, ["reaction_receipt_identity_mismatch"]
    if (
        validated.get("snapshot_status") != "complete"
        or validated.get("status") not in _COMPLETE_REACTION_STATUSES
    ):
        return {}, ["reaction_receipt_partial"]
    return validated, []


def _candidate_confidence_ceiling(
    evidence_refs: Sequence[str],
    *,
    evidence_by_id: Mapping[str, Mapping[str, object]],
    claims_by_id: Mapping[str, Mapping[str, object]],
) -> str:
    if not evidence_refs:
        return "low"
    for ref in evidence_refs:
        evidence = evidence_by_id.get(ref, {})
        if str(evidence.get("polarity") or "").lower() in {
            "contradicting",
            "negative",
        }:
            return "low"
        claim = claims_by_id.get(str(evidence.get("claim_id") or ""), {})
        source_independence = claim.get("source_independence")
        independent_sources = 0
        if isinstance(source_independence, Mapping):
            try:
                independent_sources = int(source_independence.get("count") or 0)
            except (TypeError, ValueError):
                independent_sources = 0
        if evidence.get("decision_grade") is not True or independent_sources < 2:
            return "low"
    # IRX-5 never upgrades Telegram evidence to a production-grade conclusion.
    return "medium"


def _refs_confidence_ceiling(
    evidence_refs: Sequence[str],
    *,
    input_package: Mapping[str, object],
) -> str:
    if not evidence_refs:
        return "low"
    candidates = _mapping_list(input_package.get("signal_candidates"))
    for ref in evidence_refs:
        owner_ceilings = [
            str(candidate.get("confidence_ceiling") or "low")
            for candidate in candidates
            if ref in set(candidate.get("evidence_refs") or [])
        ]
        if not owner_ceilings or any(value != "medium" for value in owner_ceilings):
            return "low"
    return "medium"


def _evidence_prompt_item(
    evidence: Mapping[str, object],
    claims_by_id: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    claim = claims_by_id.get(str(evidence.get("claim_id") or ""), {})
    return {
        "evidence_ref": str(evidence.get("id") or ""),
        "claim_ref": str(evidence.get("claim_id") or ""),
        "statement": _bounded_text(claim.get("statement") or "", 420),
        "verified_excerpt": _bounded_text(evidence.get("verified_excerpt") or "", 240),
        "evidence_tier": str(evidence.get("evidence_tier") or "unsupported"),
        "verification_status": str(evidence.get("verification_status") or "unknown"),
        "decision_grade": evidence.get("decision_grade") is True,
        "context_only": evidence.get("context_only") is True,
        "polarity": str(evidence.get("polarity") or "supporting"),
        "source_independence": dict(claim.get("source_independence") or {}),
        "uncertainty_reasons": [
            _bounded_text(value, 240)
            for value in (claim.get("uncertainty_reasons") or [])[:3]
            if str(value).strip()
        ],
    }


def _candidate_reaction_effect(
    receipt: Mapping[str, object], slug: str
) -> dict[str, object]:
    surface_ref = f"thread:{slug}"
    for key in ("influenced_items", "linked_only_items"):
        for item in _mapping_list(receipt.get(key)):
            if str(item.get("surface_item_ref") or "") == surface_ref:
                effect = str(item.get("effect") or "linked_only")
                if effect in _REACTION_EFFECTS - {"none"}:
                    return {
                        "effect": effect,
                        "source_surface_item_ref": surface_ref,
                        "reader_reason_ru": _bounded_text(
                            item.get("reader_reason_ru")
                            or "Реакция связана с сигналом, но не заменяет доказательства.",
                            360,
                        ),
                    }
    return {
        "effect": "none",
        "source_surface_item_ref": surface_ref,
        "reader_reason_ru": (
            "Подтвержденного влияния реакций на этот сигнал нет; "
            "отсутствие реакции не означает отрицательный интерес."
        ),
    }


def _stronger_reaction_effect(
    left: Mapping[str, object],
    right: Mapping[str, object],
) -> dict[str, object]:
    priority = {"none": 0, "linked_only": 1, "rank_changed": 2, "selection_changed": 3}
    left_effect = str(left.get("effect") or "none")
    right_effect = str(right.get("effect") or "none")
    return dict(
        right if priority.get(right_effect, 0) > priority.get(left_effect, 0) else left
    )


def _feedback_permissions(
    value: object,
    *,
    feedback_snapshot_count: int | None,
    feedback_snapshot_usable: object = None,
    feedback_snapshot_at: object = None,
    expected_cutoff: str = "",
) -> tuple[dict[str, object], list[str]]:
    feedback = value if isinstance(value, Mapping) else {}
    raw_confirmed = feedback.get("confirmed_event_count")
    if raw_confirmed is None:
        raw_confirmed = feedback.get("event_count") or 0
    if not isinstance(raw_confirmed, int) or isinstance(raw_confirmed, bool):
        raise EditorialInputError(
            "feedback confirmed_event_count must be an integer"
        )
    confirmed = raw_confirmed
    if confirmed < 0:
        raise EditorialInputError("feedback confirmed_event_count must be non-negative")
    partial_reasons: list[str] = []
    if feedback_snapshot_usable is not True:
        partial_reasons.append("feedback_snapshot_not_usable")
    if feedback_snapshot_at is None:
        partial_reasons.append("feedback_snapshot_cutoff_unbound")
    elif feedback_snapshot_at != expected_cutoff:
        partial_reasons.append("feedback_snapshot_cutoff_mismatch")
    if feedback_snapshot_count is not None and (
        not isinstance(feedback_snapshot_count, int)
        or isinstance(feedback_snapshot_count, bool)
    ):
        raise EditorialInputError("feedback snapshot count must be an integer")
    if feedback_snapshot_count is None and confirmed:
        partial_reasons.append("feedback_snapshot_unbound")
    elif feedback_snapshot_count is not None and confirmed != feedback_snapshot_count:
        partial_reasons.append("feedback_snapshot_count_mismatch")
    receipt = _as_mapping(feedback.get("feedback_application_receipt"))
    receipt_events: list[dict[str, object]] = []
    receipt_bucket_map = {
        "applied": "applied_changes",
        "unchanged": "unchanged",
        "code_config_required": "code_config_required",
        "rejected": "rejected",
        "pending": "pending",
    }
    for status, classification in receipt_bucket_map.items():
        for item in _mapping_list(receipt.get(status)):
            feedback_ref = str(item.get("feedback_ref") or "").strip()
            if not feedback_ref:
                continue
            receipt_events.append(
                {
                    "feedback_ref": feedback_ref,
                    "feedback_type": str(item.get("feedback_type") or "desired_report_change"),
                    "feedback_classification": str(
                        item.get("feedback_classification") or "desired_report_change"
                    ),
                    "target_type": str(_as_mapping(item.get("legacy_target")).get("target_type") or "report"),
                    "target_ref": str(_as_mapping(item.get("legacy_target")).get("target_ref") or ""),
                    "report_surface": str(item.get("report_surface") or "weekly_brief"),
                    "section_id": str(item.get("section_id") or "report"),
                    "item_ref": str(item.get("item_ref") or "report"),
                    "application_status": status,
                    "application_reason": str(item.get("application_reason") or ""),
                    "originating_report_item_ref": str(item.get("originating_report_item_ref") or ""),
                    "classification": classification,
                    "reader_summary_ru": str(
                        item.get("reader_summary_ru")
                        or "Подтверждённая обратная связь рассмотрена детерминированным слоем."
                    ),
                }
            )
    if receipt_events:
        if len(receipt_events) != min(confirmed, MAX_FEEDBACK_EVENTS):
            partial_reasons.append("feedback_receipt_count_mismatch")
        return (
            {
                "confirmed_events_available": confirmed,
                "confirmed_events_considered": len(receipt_events[:MAX_FEEDBACK_EVENTS]),
                "truncated": confirmed > len(receipt_events[:MAX_FEEDBACK_EVENTS]),
                "events": receipt_events[:MAX_FEEDBACK_EVENTS],
                "loaded_is_not_applied": True,
                "classification_owner": "deterministic_host",
            },
            _unique_strings(partial_reasons),
        )
    raw_traces = feedback.get("feedback_effect_traces")
    expected_trace_count = min(confirmed, MAX_FEEDBACK_EVENTS)
    if not isinstance(raw_traces, list):
        traces: list[Mapping[str, object]] = []
        partial_reasons.append("feedback_trace_count_mismatch")
    else:
        bounded_raw_traces = raw_traces[:MAX_FEEDBACK_EVENTS]
        traces = _mapping_list(bounded_raw_traces)
        if (
            len(raw_traces) != expected_trace_count
            or len(traces) != expected_trace_count
        ):
            partial_reasons.append("feedback_trace_count_mismatch")
    corrected_event_ids = {
        str(item.get("corrects_feedback_id"))
        for item in _mapping_list(feedback.get("feedback_corrections"))
        if str(item.get("corrects_feedback_id") or "").strip()
    }
    events: list[dict[str, object]] = []
    seen_refs: set[str] = set()
    for trace in traces:
        event_id = str(
            trace.get("event_id")
            or _as_mapping(trace.get("provenance")).get("event_id")
            or ""
        ).strip()
        if not event_id:
            raise EditorialInputError("feedback effect trace requires event_id")
        feedback_ref = f"feedback:{event_id}"
        if feedback_ref in seen_refs:
            raise EditorialInputError("feedback effect trace IDs must be unique")
        seen_refs.add(feedback_ref)
        feedback_type = str(trace.get("feedback_type") or "unknown")
        target_type = str(trace.get("target_type") or "unknown")
        target_ref = str(trace.get("target_ref") or "")
        explicit_effect = str(
            trace.get("effect") or trace.get("applied_effect") or ""
        )
        applied = (
            event_id not in corrected_event_ids
            and (
                trace.get("applied") is True
                or explicit_effect
                in {
                    "selection_changed",
                    "rank_changed",
                    "editorial_context_changed",
                }
            )
        )
        requires_separate = feedback_type in {
            "missed_important_post",
            "too_shallow",
            "trust_too_high",
            "trust_too_low",
            "verify_first",
        }
        classification = "applied_changes" if applied else ("code_config_required" if requires_separate else "unchanged")
        reader_summary = {
            "applied_changes": (
                "Событие явно изменило детерминированный выбор или редакционный "
                "контекст до редакционного шага."
            ),
            "unchanged": (
                "Событие загружено и рассмотрено, но подтвержденного изменения "
                "выбора в этом выпуске нет."
            ),
            "code_config_required": (
                "Событие требует отдельной задачи в коде или конфигурации и не "
                "считается примененным в этом выпуске."
            ),
            "rejected": "Событие рассмотрено, но не применено из-за отклонения или ретракции.",
            "pending": "Событие подтверждено и ожидает отдельного применения в следующем артефакте.",
        }[classification]
        events.append(
            {
                "feedback_ref": feedback_ref,
                "feedback_type": feedback_type,
                "feedback_classification": str(
                    trace.get("feedback_classification") or "desired_report_change"
                ),
                "target_type": target_type,
                "target_ref": target_ref,
                "report_surface": str(trace.get("report_surface") or "weekly_brief"),
                "section_id": str(trace.get("section_id") or "report"),
                "item_ref": str(trace.get("item_ref") or target_ref or "report"),
                "application_status": str(
                    trace.get("application_status")
                    or ("applied" if classification == "applied_changes" else classification)
                ),
                "application_reason": str(trace.get("application_reason") or ""),
                "originating_report_item_ref": str(trace.get("originating_report_item_ref") or ""),
                "classification": classification,
                "reader_summary_ru": reader_summary,
            }
        )
    return (
        {
            "confirmed_events_available": confirmed,
            "confirmed_events_considered": len(events),
            "truncated": confirmed > len(events),
            "events": events,
            "loaded_is_not_applied": True,
            "classification_owner": "deterministic_host",
        },
        _unique_strings(partial_reasons),
    )


def _project_permission_package(
    values: Sequence[Mapping[str, object]],
    candidates: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    signal_ids = {str(candidate.get("signal_id")) for candidate in candidates}
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, Mapping):
            raise EditorialInputError("project permission must be an object")
        ref = _required_text(raw.get("project_action_ref"), "project_action_ref")
        signal_id = _required_text(raw.get("signal_id"), "project permission signal_id")
        if ref in seen:
            raise EditorialInputError("project permission refs must be unique")
        if signal_id not in signal_ids:
            raise EditorialInputError(
                "project permission references an ineligible signal"
            )
        evidence_refs = _unique_strings(raw.get("evidence_refs") or [])
        candidate = next(
            item for item in candidates if item.get("signal_id") == signal_id
        )
        if not evidence_refs or not set(evidence_refs).issubset(
            set(candidate.get("evidence_refs") or [])
        ):
            raise EditorialInputError(
                "project permission evidence must close over its signal"
            )
        if str(raw.get("permission") or "") != "allowed":
            raise EditorialInputError(
                "only deterministic allowed project actions may enter the package"
            )
        seen.add(ref)
        result.append(
            {
                "project_action_ref": ref,
                "signal_id": signal_id,
                "project": _bounded_text(
                    _required_text(raw.get("project"), "project permission project"),
                    160,
                ),
                "permission": "allowed",
                "evidence_refs": evidence_refs,
            }
        )
        if len(result) >= EDITORIAL_MAX_PROJECT_ACTIONS:
            break
    return result


def _radar_permission_package(
    *,
    run_id: str,
    period: Mapping[str, str],
    run_context: Mapping[str, str],
    binding: Mapping[str, object] | None,
) -> tuple[dict[str, object], list[str]]:
    if binding is None:
        return _unavailable_radar_permission(), ["radar_binding_missing"]
    if not isinstance(binding, Mapping):
        return _unavailable_radar_permission(), ["radar_binding_invalid"]
    try:
        validate_radar_run_binding(binding, verify_files=False)
    except RadarBindingError:
        return _unavailable_radar_permission(), ["radar_binding_invalid"]
    if (
        binding.get("radar_contract_version")
        != RADAR_INTELLIGENCE_CONTRACT_VERSION
        or binding.get("radar_schema_version")
        not in _SUPPORTED_RADAR_SCHEMA_VERSIONS
    ):
        return _unavailable_radar_permission(), ["radar_binding_version_unsupported"]
    expected_identity = {
        "manifest_run_id": run_id,
        "reporting_week": period["reporting_week"],
        "week_label": period["reporting_week"],
        "analysis_period_start": period["analysis_period_start"],
        "analysis_period_end": period["analysis_period_end"],
        "run_date": run_context.get("run_date", ""),
        "generated_at": run_context.get("generated_at", ""),
        "period_mode": run_context.get("period_mode", ""),
    }
    if any(binding.get(field) != value for field, value in expected_identity.items()):
        return _unavailable_radar_permission(), ["radar_binding_identity_mismatch"]
    radar_run_id = str(binding.get("radar_run_id") or "")
    candidate = binding.get("selected_candidate")
    projection = binding.get("status_projection")
    assert isinstance(projection, Mapping)
    raw_projection_status = projection.get("status")
    projection_status = (
        raw_projection_status.strip().lower()
        if isinstance(raw_projection_status, str)
        else ""
    )
    status_tokens = set(re.split(r"[^a-z]+", projection_status))
    failure_fragment = re.search(
        r"(?:fail|error|partial|unavail|missing|disable|skip|not[_-]?ready)",
        projection_status,
    )
    if (
        not projection_status
        or status_tokens & _FAILED_RADAR_STATUS_MARKERS
        or failure_fragment is not None
    ):
        return _unavailable_radar_permission(), ["radar_result_not_complete"]
    candidate_payload = dict(candidate) if isinstance(candidate, Mapping) else None
    expected_projection_statuses = (
        {"selected"} if candidate_payload else {"no_candidate", "no_evidence"}
    )
    if raw_projection_status not in expected_projection_statuses:
        return _unavailable_radar_permission(), ["radar_result_inconsistent"]
    missing = []
    if candidate_payload:
        raw_title = candidate_payload.get("title") or candidate_payload.get(
            "selected_title"
        )
        raw_dossier_status = candidate_payload.get("dossier_status")
        raw_recommendation = candidate_payload.get("recommendation")
        title = raw_title if isinstance(raw_title, str) else ""
        dossier_status = (
            raw_dossier_status if isinstance(raw_dossier_status, str) else ""
        )
        recommendation = (
            raw_recommendation if isinstance(raw_recommendation, str) else ""
        )
        if (
            not title
            or title != title.strip()
            or dossier_status != dossier_status.strip()
            or recommendation != recommendation.strip()
            or dossier_status
            not in {"build", "focused_experiment", "investigate", "reject"}
            or recommendation
            not in {
                "build",
                "existing_project_context",
                "focused_experiment",
                "investigate",
                "needs_more_evidence",
                "needs_more_specific_scope",
                "reject",
                "revisit_with_evidence_gap",
            }
        ):
            return _unavailable_radar_permission(), ["radar_candidate_invalid"]
        raw_candidate_id = (
            candidate_payload.get("candidate_id")
            if "candidate_id" in candidate_payload
            else candidate_payload.get("id")
        )
        if raw_candidate_id is not None and (
            not isinstance(raw_candidate_id, str)
            or not raw_candidate_id
            or raw_candidate_id != raw_candidate_id.strip()
        ):
            return _unavailable_radar_permission(), ["radar_candidate_invalid"]
        candidate_id = raw_candidate_id or ""
        if not candidate_id:
            candidate_id = "candidate:" + hashlib.sha256(
                f"{radar_run_id}\0{title}".encode("utf-8")
            ).hexdigest()[:24]
        raw_missing = candidate_payload.get("missing_evidence") or []
        if not isinstance(raw_missing, list) or any(
            not isinstance(value, str)
            or not value
            or value != value.strip()
            for value in raw_missing
        ):
            return _unavailable_radar_permission(), ["radar_candidate_invalid"]
        missing = [_bounded_text(value, 240) for value in raw_missing[:5]]
        reader_decision = (
            "reject"
            if dossier_status == "reject" or recommendation == "reject"
            else "investigate"
        )
        why = (
            "Radar отклонил кандидата; сборка не разрешена."
            if reader_decision == "reject"
            else (
                "Radar разрешает только ограниченную проверку кандидата; "
                "сборка не разрешена."
            )
        )
        what_would_change_it = (
            "Нужно закрыть перечисленные пробелы доказательств и повторить "
            "Radar-гейт."
        )
    else:
        reader_decision = "unavailable"
        why = "Radar не выбрал кандидата для этого запуска; сборка не разрешена."
        what_would_change_it = (
            "Нужен валидный кандидат и новый связанный с запуском Radar-гейт."
        )
    return {
        "radar_ref": f"radar:{radar_run_id}",
        "status": _bounded_text(projection_status, 80),
        "selected_candidate": (
            {
                "candidate_id": _bounded_text(candidate_id, 160),
                "title": _bounded_text(
                    candidate_payload.get("title")
                    or candidate_payload.get("selected_title")
                    or "",
                    240,
                ),
                "dossier_status": _bounded_text(
                    candidate_payload.get("dossier_status") or "", 100
                ),
                "recommendation": _bounded_text(
                    candidate_payload.get("recommendation") or "", 120
                ),
                "missing_evidence": missing,
            }
            if candidate_payload
            else None
        ),
        # The current deterministic Radar contract grants at most a focused
        # investigation.  It has no full build permission, so IRX-5 can never
        # emit build_allowed even when a model asks for it.
        "allowed_reader_decisions": [reader_decision],
        "build_allowed": False,
        "context_only_can_satisfy_gate": False,
        "why": why,
        "what_would_change_it": what_would_change_it,
        "radar_artifact_sha256": _as_mapping(binding.get("radar_json_ref")).get(
            "sha256"
        ),
    }, []


def _unavailable_radar_permission() -> dict[str, object]:
    return {
        "radar_ref": "",
        "status": "unavailable",
        "selected_candidate": None,
        "allowed_reader_decisions": ["unavailable"],
        "build_allowed": False,
        "context_only_can_satisfy_gate": False,
        "why": (
            "Связанный с запуском валидный Radar-результат недоступен; "
            "сборка не разрешена."
        ),
        "what_would_change_it": (
            "Нужен валидный Radar-артефакт, связанный с этим запуском."
        ),
        "radar_artifact_sha256": None,
    }


def _frontier_prompt_context(value: object) -> dict[str, object]:
    analysis = value if isinstance(value, Mapping) else {}
    return {
        "available": bool(analysis),
        "executive_brief": _bounded_text(analysis.get("executive_brief") or "", 500),
        "what_changed": [
            {
                key: _bounded_text(item.get(key) or "", 300)
                for key in ("title", "summary", "why_it_matters")
                if str(item.get(key) or "").strip()
            }
            for item in _mapping_list(analysis.get("what_changed"))[:3]
        ],
        "caveats": [
            _bounded_text(value, 240)
            for value in (analysis.get("caveats") or [])[:4]
            if str(value).strip()
        ],
        "source_policy": "narrative_context_not_primary_evidence",
    }


def _validate_period(
    value: object,
    input_package: Mapping[str, object],
    errors: list[str],
) -> None:
    period = _as_object(value, "reporting_period", errors)
    _exact_keys(period, _PERIOD_FIELDS, "reporting_period", errors)
    if period != input_package.get("reporting_period"):
        errors.append("reporting_period mismatch")


def _validate_matrix(
    value: object,
    signal_ids: Sequence[str],
    signals: Sequence[object],
    errors: list[str],
) -> None:
    matrix = _as_object(value, "decision_matrix", errors)
    _exact_keys(matrix, _MATRIX_FIELDS, "decision_matrix", errors)
    flattened: list[str] = []
    for bucket in ("act", "study", "watch", "ignore"):
        refs = _string_list(matrix.get(bucket), f"decision_matrix.{bucket}", errors)
        flattened.extend(refs)
    if len(flattened) != len(set(flattened)):
        errors.append("decision_matrix contains duplicate signal refs")
    if set(flattened) != set(signal_ids):
        errors.append("decision_matrix must exactly cover returned signals")
    decision_by_id = {
        str(signal.get("signal_id")): str(signal.get("decision"))
        for signal in signals
        if isinstance(signal, Mapping)
    }
    for bucket in ("act", "study", "watch", "ignore"):
        for signal_id in matrix.get(bucket) or []:
            decision = decision_by_id.get(str(signal_id))
            expected = "study" if decision == "verify_first" else decision
            if expected != bucket:
                errors.append(f"decision_matrix bucket mismatch for {signal_id}")


def _validate_project_actions(
    value: object,
    input_package: Mapping[str, object],
    returned_signal_ids: Sequence[str],
    returned_project_refs: Sequence[str],
    errors: list[str],
) -> None:
    refs = _string_list(value, "project_actions", errors)
    if len(refs) > EDITORIAL_MAX_PROJECT_ACTIONS:
        errors.append("project_actions exceeds limit")
    allowed = {
        str(item.get("project_action_ref"))
        for item in _mapping_list(input_package.get("project_permissions"))
        if str(item.get("signal_id") or "") in set(returned_signal_ids)
    }
    if not set(refs).issubset(allowed):
        errors.append("project_actions exceeds deterministic permission")
    if len(returned_project_refs) != len(set(returned_project_refs)):
        errors.append("project implications repeat a project action")
    if set(refs) != set(returned_project_refs):
        errors.append("project_actions must exactly match signal implications")


def _validate_feedback_effect(
    value: object,
    input_package: Mapping[str, object],
    errors: list[str],
) -> None:
    effect = _as_object(value, "feedback_effect", errors)
    _exact_keys(effect, _FEEDBACK_FIELDS, "feedback_effect", errors)
    permissions = _as_mapping(input_package.get("feedback_permissions"))
    expected_count = int(permissions.get("confirmed_events_considered") or 0)
    raw_count = effect.get("confirmed_events_considered")
    if not isinstance(raw_count, int) or isinstance(raw_count, bool):
        actual_count = -1
        errors.append("feedback_effect.confirmed_events_considered must be an integer")
    else:
        actual_count = raw_count
    if actual_count != expected_count:
        errors.append("feedback_effect confirmed event count mismatch")
    allowed_by_class: dict[str, set[str]] = {
        name: set()
        for name in ("applied_changes", "unchanged", "code_config_required", "rejected", "pending")
    }
    expected_summaries: dict[str, str] = {}
    for item in _mapping_list(permissions.get("events")):
        classification = str(item.get("classification") or "")
        if classification in allowed_by_class:
            feedback_ref = str(item.get("feedback_ref") or "")
            allowed_by_class[classification].add(feedback_ref)
            expected_summaries[feedback_ref] = str(
                item.get("reader_summary_ru") or ""
            )
    seen: set[str] = set()
    for classification in ("applied_changes", "unchanged", "code_config_required", "rejected", "pending"):
        items = effect.get(classification)
        if not isinstance(items, list):
            errors.append(f"feedback_effect.{classification} must be a list")
            continue
        for index, raw_item in enumerate(items):
            path = f"feedback_effect.{classification}[{index}]"
            item = _as_object(raw_item, path, errors)
            _exact_keys(item, _FEEDBACK_ITEM_FIELDS, path, errors)
            feedback_ref = str(item.get("feedback_ref") or "")
            if feedback_ref not in allowed_by_class[classification]:
                errors.append(f"{path} is not allowed in this classification")
            if feedback_ref in seen:
                errors.append(f"{path} duplicates a feedback event")
            seen.add(feedback_ref)
            _require_russian(
                item.get("reader_summary_ru"), f"{path}.reader_summary_ru", errors
            )
            _max_text(
                item.get("reader_summary_ru"),
                500,
                f"{path}.reader_summary_ru",
                errors,
            )
            if item.get("reader_summary_ru") != expected_summaries.get(feedback_ref):
                errors.append(f"{path}.reader_summary_ru must match host projection")
    expected_refs = set().union(*allowed_by_class.values())
    if seen != expected_refs:
        errors.append("every considered feedback event must be classified exactly once")


def _validate_mvp_summary(
    value: object,
    input_package: Mapping[str, object],
    errors: list[str],
) -> None:
    summary = _as_object(value, "mvp_summary", errors)
    _exact_keys(summary, _MVP_FIELDS, "mvp_summary", errors)
    permission = _as_mapping(input_package.get("radar_permission"))
    if summary.get("radar_ref") != permission.get("radar_ref"):
        errors.append("mvp_summary.radar_ref mismatch")
    decision = str(summary.get("reader_decision") or "")
    if decision not in _RADAR_DECISIONS:
        errors.append("mvp_summary.reader_decision is invalid")
    if decision not in set(permission.get("allowed_reader_decisions") or []):
        errors.append(
            "mvp_summary.reader_decision exceeds deterministic Radar permission"
        )
    _require_russian(summary.get("why"), "mvp_summary.why", errors)
    _require_russian(
        summary.get("what_would_change_it"), "mvp_summary.what_would_change_it", errors
    )
    _max_text(summary.get("why"), 700, "mvp_summary.why", errors)
    _max_text(
        summary.get("what_would_change_it"),
        700,
        "mvp_summary.what_would_change_it",
        errors,
    )
    if summary.get("why") != permission.get("why"):
        errors.append("mvp_summary.why must match deterministic Radar projection")
    if summary.get("what_would_change_it") != permission.get(
        "what_would_change_it"
    ):
        errors.append(
            "mvp_summary.what_would_change_it must match deterministic Radar projection"
        )


def _validate_permission_ref_list(
    value: object,
    permissions: object,
    field: str,
    errors: list[str],
    *,
    limit: int = 12,
) -> None:
    refs = _string_list(value, field, errors)
    if len(refs) > limit:
        errors.append(f"{field} exceeds limit")
    allowed = {str(item) for item in (permissions or []) if str(item).strip()}
    if not set(refs).issubset(allowed):
        errors.append(f"{field} exceeds deterministic permission")


def _validate_partial_fallback(
    payload: Mapping[str, object],
    input_package: Mapping[str, object],
    errors: list[str],
) -> None:
    expected = _deterministic_partial_fallback(input_package)
    if dict(payload) != expected:
        errors.append("partial fallback must exactly match deterministic projection")


def _deterministic_partial_fallback(
    input_package: Mapping[str, object],
) -> dict[str, object]:
    feedback_permissions = _as_mapping(input_package.get("feedback_permissions"))
    feedback_lists: dict[str, list[dict[str, str]]] = {
        "applied_changes": [],
        "unchanged": [],
        "code_config_required": [],
        "rejected": [],
        "pending": [],
    }
    for event in _mapping_list(feedback_permissions.get("events")):
        classification = str(event.get("classification") or "unchanged")
        if classification in feedback_lists:
            feedback_lists[classification].append(
                {
                    "feedback_ref": str(event.get("feedback_ref") or ""),
                    "reader_summary_ru": str(event.get("reader_summary_ru") or ""),
                }
            )
    radar = _as_mapping(input_package.get("radar_permission"))
    allowed = [str(value) for value in radar.get("allowed_reader_decisions") or []]
    reader_decision = "unavailable" if "unavailable" in allowed else allowed[0]
    return {
        "schema_version": EDITORIAL_SCHEMA_VERSION,
        "run_id": input_package.get("run_id"),
        "reporting_period": dict(_as_mapping(input_package.get("reporting_period"))),
        "weekly_thesis": {
            "title": "Частичный редакционный выпуск",
            "plain_language_summary": (
                "Редакционный синтез не прошел проверку, поэтому полный вывод недели не публикуется."
            ),
            "why_for_operator": (
                "Используйте исходные проверяемые материалы и дождитесь валидного повторного синтеза."
            ),
            "confidence": "low",
            "evidence_refs": [],
        },
        "decision_matrix": {"act": [], "study": [], "watch": [], "ignore": []},
        "signals": [],
        "project_actions": [],
        "feedback_effect": {
            "confirmed_events_considered": int(
                feedback_permissions.get("confirmed_events_considered") or 0
            ),
            **feedback_lists,
        },
        "mvp_summary": {
            "radar_ref": str(radar.get("radar_ref") or ""),
            "reader_decision": reader_decision,
            "why": str(
                radar.get("why")
                or "Частичный редакционный режим не повышает решение Radar."
            ),
            "what_would_change_it": str(
                radar.get("what_would_change_it")
                or "Нужен валидный связанный Radar-результат."
            ),
        },
        "visual_specs": [],
        "feedback_targets": [],
    }


def _completion_receipt_errors(receipt: LLMCompletionReceipt) -> list[str]:
    errors: list[str] = []
    if not isinstance(receipt.text, str):
        errors.append("completion receipt text must be a string")
    if not isinstance(receipt.model, str) or not receipt.model.strip():
        errors.append("completion receipt model is required")
    for field in ("input_tokens", "output_tokens", "duration_ms", "attempts"):
        value = getattr(receipt, field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"completion receipt {field} must be non-negative")
    if isinstance(receipt.attempts, int) and receipt.attempts < 1:
        errors.append("completion receipt attempts must be positive")
    cost = receipt.estimated_cost_usd
    if (
        not isinstance(cost, (int, float))
        or isinstance(cost, bool)
        or not math.isfinite(float(cost))
        or float(cost) < 0
    ):
        errors.append("completion receipt estimated cost is invalid")
    if not isinstance(receipt.usage_recorded, bool):
        errors.append("completion receipt usage_recorded must be boolean")
    return errors


def _generation_receipt(
    *,
    input_hash: str,
    requested_model: str,
    receipt: LLMCompletionReceipt | None,
    generated_at: datetime | str | None,
    completion_mode: str,
    validation_errors: Sequence[str],
) -> dict[str, object]:
    return {
        "schema_version": EDITORIAL_RECEIPT_SCHEMA_VERSION,
        "prompt_version": EDITORIAL_PROMPT_VERSION,
        "editorial_schema_version": EDITORIAL_SCHEMA_VERSION,
        "requested_model": requested_model,
        "model": receipt.model if receipt is not None else requested_model,
        "input_hash": input_hash,
        "generated_at": _canonical_timestamp(generated_at),
        "max_input_json_chars": MAX_INPUT_JSON_CHARS,
        "max_tokens": EDITORIAL_MAX_TOKENS,
        "planned_cost_ceiling_usd": PLANNED_COST_CEILING_USD,
        "input_tokens": int(receipt.input_tokens if receipt is not None else 0),
        "output_tokens": int(receipt.output_tokens if receipt is not None else 0),
        "estimated_cost_usd": round(
            float(receipt.estimated_cost_usd if receipt is not None else 0.0), 8
        ),
        "cost_ceiling_exceeded": bool(
            receipt is not None
            and receipt.estimated_cost_usd > PLANNED_COST_CEILING_USD
        ),
        "duration_ms": int(receipt.duration_ms if receipt is not None else 0),
        "attempts": int(receipt.attempts if receipt is not None else 0),
        "usage_recorded": bool(
            receipt.usage_recorded if receipt is not None else False
        ),
        "completion_mode": completion_mode,
        "validation_errors": [str(value)[:240] for value in validation_errors[:12]],
    }


def _summary(
    path: Path,
    artifact: Mapping[str, object],
    *,
    skipped_existing: bool,
) -> EditorialIntelligenceSummary:
    receipt = _as_mapping(artifact.get("generation_receipt"))
    period = _as_mapping(artifact.get("reporting_period"))
    return EditorialIntelligenceSummary(
        path=str(path),
        run_id=str(artifact.get("run_id") or ""),
        reporting_week=str(period.get("reporting_week") or ""),
        generation_status=str(artifact.get("generation_status") or "partial"),
        partial=bool(artifact.get("partial", True)),
        signal_count=len(artifact.get("signals") or []),
        model=str(receipt.get("model") or ""),
        prompt_version=str(receipt.get("prompt_version") or ""),
        input_hash=str(receipt.get("input_hash") or ""),
        estimated_cost_usd=float(receipt.get("estimated_cost_usd") or 0.0),
        skipped_existing=skipped_existing,
    )


def _atomic_create_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    else:
        try:
            os.unlink(temporary)
        except OSError:
            pass


def _canonical_timestamp(value: datetime | str | None) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise EditorialInputError("generated_at must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EditorialInputError("generated_at must include an explicit timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    path: str,
    errors: list[str],
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        errors.append(f"{path} fields mismatch missing={missing} extra={extra}")


def _as_object(value: object, path: str, errors: list[str]) -> dict[str, object]:
    if not isinstance(value, Mapping):
        errors.append(f"{path} must be an object")
        return {}
    return dict(value)


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    return (
        [item for item in (value or []) if isinstance(item, Mapping)]
        if isinstance(value, list)
        else []
    )


def _string_list(value: object, path: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{path} must be a list")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{path}[{index}] must be a non-empty string")
            continue
        clean = item.strip()
        if item != clean:
            errors.append(f"{path}[{index}] must not contain surrounding whitespace")
        result.append(clean)
    if len(result) != len(set(result)):
        errors.append(f"{path} contains duplicates")
    return result


def _confidence(value: object, path: str, errors: list[str]) -> str:
    confidence = str(value or "")
    if confidence not in _CONFIDENCE_ORDER:
        errors.append(f"{path} is invalid")
        return "low"
    return confidence


def _validate_confidence_ceiling(
    actual: str,
    ceiling: str,
    path: str,
    errors: list[str],
) -> None:
    if (
        ceiling not in _CONFIDENCE_ORDER
        or _CONFIDENCE_ORDER[actual] > _CONFIDENCE_ORDER[ceiling]
    ):
        errors.append(f"{path}.confidence exceeds deterministic evidence ceiling")


def _validate_russian_fields(
    value: Mapping[str, object],
    fields: Sequence[str],
    path: str,
    errors: list[str],
) -> None:
    for field in fields:
        _require_russian(value.get(field), f"{path}.{field}", errors)


def _require_russian(value: object, path: str, errors: list[str]) -> str:
    if not isinstance(value, str):
        errors.append(f"{path} must be a string")
        return ""
    text = value.strip()
    if value != text:
        errors.append(f"{path} must not contain surrounding whitespace")
    if not text:
        errors.append(f"{path} is required")
    else:
        letters = _LETTER_RE.findall(text)
        cyrillic = _CYRILLIC_RE.findall(text)
        if len(cyrillic) < 3 or (
            letters and len(cyrillic) / len(letters) < 0.25
        ):
            errors.append(f"{path} must contain Russian reader copy")
    return text


def _max_text(value: object, limit: int, path: str, errors: list[str]) -> None:
    if len(str(value or "")) > limit:
        errors.append(f"{path} exceeds {limit} characters")


def _require_cautious_copy(
    value: Mapping[str, object],
    fields: Sequence[str],
    path: str,
    errors: list[str],
) -> None:
    for field in fields:
        text = str(value.get(field) or "").lower()
        if not any(marker in text for marker in _CAUTIOUS_MARKERS_RU):
            errors.append(
                f"{path}.{field} low evidence requires explicit cautious wording"
            )


def _validate_duplicate_or_generic_actions(
    values: Sequence[tuple[str, str]],
    errors: list[str],
) -> None:
    normalized: dict[str, str] = {}
    for path, text in values:
        clean = _normalize_sentence(text)
        if not clean:
            continue
        tokens = clean.split()
        generic_short = bool(
            len(tokens) <= 4
            and re.match(
                r"^(?:не\s+)?(?:изучить|проверить|посмотреть|наблюдать|"
                r"проанализировать|исследовать|продолжить|сделать)\b",
                clean,
            )
        )
        generic_vocabulary = bool(
            2 <= len(tokens) <= 7
            and all(token in _GENERIC_ACTION_VOCABULARY for token in tokens)
        )
        if clean in _GENERIC_ACTIONS or generic_short or generic_vocabulary:
            errors.append(f"{path} is a generic action")
        if clean in normalized:
            errors.append(f"{path} duplicates {normalized[clean]}")
        else:
            normalized[clean] = path


def _validate_narrative_permissions(
    output: Mapping[str, object],
    errors: list[str],
) -> None:
    authored_fields: list[tuple[str, object]] = []
    thesis = _as_mapping(output.get("weekly_thesis"))
    for field in ("title", "plain_language_summary", "why_for_operator"):
        authored_fields.append((f"weekly_thesis.{field}", thesis.get(field)))
    for index, signal in enumerate(_mapping_list(output.get("signals"))):
        project_refs = _string_list(
            signal.get("project_implications"),
            f"signals[{index}].project_implications",
            [],
        )
        for field in (
            "title",
            "what_happened",
            "plain_explanation",
            "what_changed",
            "why_for_operator",
        ):
            authored_fields.append((f"signals[{index}].{field}", signal.get(field)))
        action = _as_mapping(signal.get("next_action"))
        action_values: list[tuple[str, object]] = []
        authored_fields.append(
            (f"signals[{index}].next_action.title", action.get("title"))
        )
        action_values.append(
            (f"signals[{index}].next_action.title", action.get("title"))
        )
        criteria = action.get("acceptance_criteria")
        criteria_values = criteria if isinstance(criteria, list) else []
        for criterion_index, criterion in enumerate(criteria_values):
            item = (
                "signals["
                f"{index}].next_action.acceptance_criteria[{criterion_index}]",
                criterion,
            )
            authored_fields.append(item)
            action_values.append(item)
        action_title = action.get("title")
        if isinstance(action_title, str) and not _INVESTIGATION_ACTION_RE.search(
            action_title
        ):
            errors.append(
                f"signals[{index}].next_action.title must be a bounded "
                "verification or research action"
            )
        if not project_refs:
            for path, value in action_values:
                if isinstance(value, str) and _UNPERMITTED_ACTION_DOMAIN_RE.search(
                    value
                ):
                    errors.append(
                        f"{path} references project/code/deployment without "
                        "deterministic project permission"
                    )
    for path, value in authored_fields:
        if not isinstance(value, str):
            continue
        if _RADAR_BUILD_APPROVAL_RE.search(value):
            errors.append(f"{path} contradicts deterministic Radar permission")
        if (
            _PERSISTENT_MUTATION_RE.search(value)
            and not _MUTATION_NEGATION_RE.search(value)
        ):
            errors.append(f"{path} invents an unpermitted persistent mutation")
        if (
            _READINESS_SUBJECT_RE.search(value)
            and _READINESS_CLAIM_RE.search(value)
            and not _READINESS_NEGATION_RE.search(value)
        ):
            errors.append(f"{path} invents Radar/MVP readiness")


def _normalize_sentence(value: object) -> str:
    text = str(value or "").lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9]+", " ", text, flags=re.I)
    return _SPACE_RE.sub(" ", text).strip()


def _reject_markup(value: object, errors: list[str]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if _HTML_RE.search(encoded):
        errors.append("editorial JSON must not contain HTML, SVG, or script markup")


def _ensure_json(value: object, *, field: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EditorialInputError(f"{field} must be strict JSON") from exc


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise EditorialInputError(f"{field} is required")
    return value


def _bounded_text(value: object, limit: int) -> str:
    text = _SPACE_RE.sub(" ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _unique_strings(values: object) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values if isinstance(values, (list, tuple, set)) else []:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
