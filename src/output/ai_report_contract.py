"""Contract and deterministic gates for weekly AI intelligence reports."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlparse

from output.report_quality import ReportQualityFinding, SEVERITY_CRITICAL


REPORT_CONTRACT_VERSION = "weekly-ai-intelligence-v1"
INTELLIGENCE_CONTRACT_VERSION = "tra-intelligence-contract.v1"
RADAR_INTELLIGENCE_CONTRACT_VERSION = "tra-radar-intelligence-contract.v1"

ALLOWED_DECISION_VERDICTS = {"apply", "study", "watch", "ignore", "defer", "verify_first"}
ALLOWED_ACTION_SCOPES = {"skill", "project", "infra", "reading", "experiment", "verification"}
BROAD_PROJECT_TERMS = {
    "ai",
    "agent",
    "agents",
    "automation",
    "evidence",
    "implementation",
    "memory",
    "research",
    "signal",
    "signals",
    "tool",
    "tools",
    "workflow",
}

REPORT_CONTRACT_SCHEMA: dict[str, Any] = {
    "report_contract": {
        "version": REPORT_CONTRACT_VERSION,
        "html_language": "ru",
        "required_top_level_fields": [
            "decision_cards",
            "claim_cards",
            "deep_explanation_cards",
            "thread_deltas",
            "action_cards",
            "project_diagnostic",
            "feedback_targets",
            "intelligence_contract",
        ],
    },
    "intelligence_contract": {
        "version": INTELLIGENCE_CONTRACT_VERSION,
        "required_entities": [
            "source_observations",
            "evidence_items",
            "claims",
            "knowledge_atoms",
            "idea_threads",
            "decisions",
            "experiments",
            "outcomes",
        ],
    },
    "decision_cards": {
        "required_fields": [
            "id",
            "verdict",
            "title",
            "why_for_operator",
            "evidence_atom_ids",
            "confidence",
            "next_action",
            "success_criterion",
            "feedback_target_id",
        ],
        "verdict_values": sorted(ALLOWED_DECISION_VERDICTS),
    },
    "claim_cards": {
        "required_fields": [
            "id",
            "claim",
            "evidence_atom_ids",
            "source_count",
            "source_urls",
            "evidence_tier",
            "evidence_role",
            "verification_status",
            "quote_verified",
            "claim_scope",
            "time_horizon",
            "confidence",
            "caveat",
            "expiry_hint",
            "staleness_status",
            "wording_policy",
            "next_verification_step",
            "source_independence_key",
        ],
    },
    "deep_explanation_cards": {
        "required_fields": [
            "id",
            "claim_card_id",
            "what_is_this",
            "why_now",
            "how_it_works",
            "where_is_hype",
            "what_to_do",
            "what_not_to_do",
            "caveat",
            "source_urls",
            "evidence_tier",
            "quote_verification_status",
            "what_would_change_my_mind",
        ],
    },
    "thread_deltas": {
        "required_fields": [
            "thread_slug",
            "previous_state",
            "previous_week_state",
            "new_evidence",
            "this_week_evidence",
            "updated_interpretation",
            "confidence_movement",
            "confidence_change",
            "delta_reason",
            "new_evidence_atom_ids",
            "state",
            "why_this_is_one_thread",
            "merge_split_audit_status",
        ],
    },
    "feedback_targets": {
        "required_fields": ["id", "target_type", "prompt", "event_options"],
    },
}

RUSSIAN_REQUIRED_HTML_MARKERS = (
    "Операторский вердикт",
    "Доказательства по ключевым утверждениям",
    "Что изменилось",
    "Операционные действия",
    "Диагностика проектного соответствия",
    "Какой фидбек оставить",
)

LEGACY_ENGLISH_HTML_MARKERS = (
    ">Decision Brief<",
    ">What Changed<",
    ">Study And Do<",
    ">Project Implications<",
    ">Study Now<",
    ">Do Next<",
    ">Do Now<",
    ">Trust Check<",
)

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
TAG_RE = re.compile(r"<[^>]+>")


def build_weekly_ai_report_contract(
    context: Mapping[str, Any],
    *,
    project_links: list[dict] | None = None,
    projects: list[dict] | None = None,
) -> dict[str, Any]:
    """Build the deterministic report contract from already-compressed context."""
    threads = [thread for thread in (context.get("threads") or []) if isinstance(thread, dict)]
    atoms = _all_atoms(threads)
    analysis = context.get("frontier_analysis") or {}
    feedback_context = context.get("feedback_context") or {}
    clean_project_links = [link for link in (project_links or []) if isinstance(link, dict)]
    clean_projects = [project for project in (projects or []) if isinstance(project, dict)]

    feedback_targets = _feedback_targets(analysis, atoms, feedback_context)
    action_cards = _action_cards(analysis, feedback_targets)
    claim_cards = _claim_cards(atoms)
    deep_explanation_cards = _deep_explanation_cards(claim_cards)
    decision_cards = _decision_cards(analysis, claim_cards, action_cards, feedback_targets)
    thread_deltas = _thread_deltas(context, threads)
    project_diagnostic = _project_diagnostic(
        analysis=analysis,
        project_links=clean_project_links,
        projects=clean_projects,
        threads=threads,
    )

    return {
        "report_contract": {
            "version": REPORT_CONTRACT_VERSION,
            "html_language": "ru",
            "operator_copy_language": "ru",
            "source_quote_language": "original",
            "schema": REPORT_CONTRACT_SCHEMA,
            "personalization_confidence": (
                "low" if int(feedback_context.get("event_count") or 0) <= 0 else "observed"
            ),
            "personalization_note": (
                "Нет свежего фидбека: уверенность персонализации низкая."
                if int(feedback_context.get("event_count") or 0) <= 0
                else "Свежий фидбек учтен в ранжировании."
            ),
            "feedback_completion": feedback_context.get("feedback_completion") or {},
            "feedback_used_summary": _feedback_used_summary(feedback_context),
            "feedback_eval_example_count": len(_as_list(feedback_context.get("feedback_eval_examples"))),
            "frontier_prompt_guidance": _as_list(feedback_context.get("frontier_prompt_guidance")),
            "canonical_contract_version": INTELLIGENCE_CONTRACT_VERSION,
        },
        "decision_cards": decision_cards,
        "claim_cards": claim_cards,
        "deep_explanation_cards": deep_explanation_cards,
        "thread_deltas": thread_deltas,
        "action_cards": action_cards,
        "project_diagnostic": project_diagnostic,
        "feedback_targets": feedback_targets,
        "intelligence_contract": build_canonical_intelligence_contract(
            context,
            claim_cards=claim_cards,
            thread_deltas=thread_deltas,
            decision_cards=decision_cards,
        ),
    }


def validate_weekly_ai_report_contract(
    metadata: Mapping[str, Any] | None,
    *,
    html_text: str | None = None,
) -> list[ReportQualityFinding]:
    findings: list[ReportQualityFinding] = []
    payload = metadata if isinstance(metadata, Mapping) else {}
    contract = payload.get("report_contract") if isinstance(payload.get("report_contract"), Mapping) else {}
    if contract.get("version") != REPORT_CONTRACT_VERSION:
        findings.append(_critical("Report contract version is missing or unsupported", "report_contract.version"))
    if contract.get("html_language") != "ru":
        findings.append(_critical("Final HTML language contract must be Russian", "report_contract.html_language"))

    feedback_targets = _as_list(payload.get("feedback_targets"))
    feedback_ids = {str(item.get("id")) for item in feedback_targets if isinstance(item, Mapping)}
    claim_cards = _as_list(payload.get("claim_cards"))
    claim_by_atom_id = _claim_cards_by_atom_id(claim_cards)

    _validate_decision_cards(payload.get("decision_cards"), feedback_ids, claim_by_atom_id, findings)
    _validate_claim_cards(claim_cards, findings)
    _validate_deep_explanation_cards(payload.get("deep_explanation_cards"), findings)
    _validate_thread_deltas(
        payload.get("thread_deltas"),
        findings,
        expected_count=_expected_thread_delta_count(payload),
    )
    _validate_action_cards(payload.get("action_cards"), feedback_ids, findings)
    _validate_project_diagnostic(payload.get("project_diagnostic"), findings)
    _validate_feedback_targets(feedback_targets, findings)
    findings.extend(validate_canonical_intelligence_contract(payload.get("intelligence_contract")))
    if html_text is not None:
        findings.extend(validate_weekly_ai_report_html_language(html_text))
    return findings


def validate_weekly_ai_report_html_language(html_text: str) -> list[ReportQualityFinding]:
    content = html.unescape(str(html_text or ""))
    findings: list[ReportQualityFinding] = []
    if '<html lang="ru"' not in content.lower() and "<html lang='ru'" not in content.lower():
        findings.append(_critical("Final user-facing HTML must declare Russian language", "html lang"))
    for marker in RUSSIAN_REQUIRED_HTML_MARKERS:
        if marker not in content:
            findings.append(_critical(f"Russian user-value section is missing: {marker}", marker))
    for marker in LEGACY_ENGLISH_HTML_MARKERS:
        if marker in content:
            findings.append(_critical("Legacy English report label is visible in final HTML", marker))
    visible = TAG_RE.sub(" ", content)
    if len(CYRILLIC_RE.findall(visible)) < 120:
        findings.append(
            _critical(
                "Final user-facing HTML does not contain enough Russian operator-facing copy",
                "html language",
            )
        )
    return findings


def build_canonical_intelligence_contract(
    context: Mapping[str, Any],
    *,
    claim_cards: list[dict] | None = None,
    thread_deltas: list[dict] | None = None,
    decision_cards: list[dict] | None = None,
    mvp_radar: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical sidecar projection over curated intelligence objects."""
    threads = [thread for thread in (context.get("threads") or []) if isinstance(thread, dict)]
    atoms = _all_atoms(threads)
    cards = [card for card in (claim_cards or _claim_cards(atoms)) if isinstance(card, dict)]
    deltas = [delta for delta in (thread_deltas or _thread_deltas(context, threads)) if isinstance(delta, dict)]
    observations, observation_ids_by_atom = _canonical_source_observations(atoms)
    evidence_items = _canonical_evidence_items(cards, atoms, observation_ids_by_atom)
    claims = _canonical_claims(cards, evidence_items)
    atom_items = _canonical_atoms(atoms, claims, evidence_items)
    thread_items = _canonical_threads(threads, claims, evidence_items, deltas)
    decisions = _canonical_decisions(decision_cards or [], claims)
    payload: dict[str, Any] = {
        "contract_version": INTELLIGENCE_CONTRACT_VERSION,
        "schema_version": INTELLIGENCE_CONTRACT_VERSION,
        "week_label": context.get("week_label"),
        "projection_boundaries": {
            "canonical_state": "SQLite rows and versioned JSON sidecars",
            "rendered_surfaces": ["html", "markdown", "telegram_messages"],
            "llm_prose": "derived_interpretation_not_source_of_truth",
            "market_business_context": "context_only",
            "no_feedback_semantics": "unknown",
        },
        "source_observations": observations,
        "evidence_items": evidence_items,
        "claims": claims,
        "knowledge_atoms": atom_items,
        "idea_threads": thread_items,
        "decisions": decisions,
        "experiments": [],
        "outcomes": [],
    }
    if mvp_radar is not None:
        payload["radar_exchange"] = _canonical_radar_exchange(mvp_radar)
    return payload


def validate_canonical_intelligence_contract(value: object) -> list[ReportQualityFinding]:
    findings: list[ReportQualityFinding] = []
    payload = value if isinstance(value, Mapping) else {}
    if not payload:
        findings.append(_critical("Canonical intelligence contract is missing", "intelligence_contract"))
        return findings
    if payload.get("contract_version") != INTELLIGENCE_CONTRACT_VERSION:
        findings.append(
            _critical(
                "Canonical intelligence contract version is missing or unsupported",
                "intelligence_contract.contract_version",
            )
        )
    source_ids = {
        str(item.get("id"))
        for item in _as_list(payload.get("source_observations"))
        if isinstance(item, Mapping) and str(item.get("id") or "").strip()
    }
    evidence_items = [item for item in _as_list(payload.get("evidence_items")) if isinstance(item, Mapping)]
    evidence_by_id = {
        str(item.get("id")): item
        for item in evidence_items
        if str(item.get("id") or "").strip()
    }
    for index, item in enumerate(evidence_items, start=1):
        prefix = f"intelligence_contract.evidence_items[{index}]"
        _require_text(
            item,
            (
                "id",
                "evidence_role",
                "evidence_tier",
                "verification_status",
                "polarity",
                "source_observation_id",
            ),
            findings,
            prefix,
        )
        observation_id = str(item.get("source_observation_id") or "")
        if observation_id and observation_id not in source_ids:
            findings.append(_critical("Evidence item references an unknown source observation", f"{prefix}.source_observation_id"))
        if item.get("decision_grade") is True:
            if item.get("context_only") is True:
                findings.append(_critical("Context-only evidence cannot be decision-grade", f"{prefix}.decision_grade"))
            if observation_id not in source_ids:
                findings.append(_critical("Decision-grade evidence must resolve to a source observation", f"{prefix}.source_observation_id"))
            if item.get("quote_verified") is not True:
                findings.append(_critical("Decision-grade evidence must have a verified quote/excerpt", f"{prefix}.quote_verified"))
            tier = str(item.get("evidence_tier") or "")
            if tier.startswith("weak") or tier == "unsupported":
                findings.append(_critical("Weak or unsupported evidence cannot be decision-grade", f"{prefix}.evidence_tier"))
    claims = [item for item in _as_list(payload.get("claims")) if isinstance(item, Mapping)]
    claim_by_id = {
        str(item.get("id")): item
        for item in claims
        if str(item.get("id") or "").strip()
    }
    for index, claim in enumerate(claims, start=1):
        prefix = f"intelligence_contract.claims[{index}]"
        _require_text(
            claim,
            ("id", "statement", "scope", "time_horizon", "confidence_band", "verification_state"),
            findings,
            prefix,
        )
        if "supporting_evidence_item_ids" not in claim:
            findings.append(_critical("Claim must declare supporting evidence item refs", f"{prefix}.supporting_evidence_item_ids"))
        if "contradicting_evidence_item_ids" not in claim:
            findings.append(_critical("Claim must declare contradicting evidence item refs", f"{prefix}.contradicting_evidence_item_ids"))
        supporting = [str(ref) for ref in _as_list(claim.get("supporting_evidence_item_ids"))]
        contradicting = [str(ref) for ref in _as_list(claim.get("contradicting_evidence_item_ids"))]
        for ref in [*supporting, *contradicting]:
            if ref and ref not in evidence_by_id:
                findings.append(_critical("Claim references unknown evidence item", f"{prefix}.evidence_item_ids"))
        if claim.get("decision_grade") is True:
            if not supporting:
                findings.append(_critical("Decision-grade claim must cite supporting evidence", f"{prefix}.supporting_evidence_item_ids"))
            if str(claim.get("verification_state") or "") != "verified":
                findings.append(_critical("Decision-grade claim must have verified state", f"{prefix}.verification_state"))
            if not _as_list(claim.get("source_observation_ids")):
                findings.append(_critical("Decision-grade claim must cite source observations", f"{prefix}.source_observation_ids"))
            for ref in supporting:
                evidence = evidence_by_id.get(ref)
                if evidence and evidence.get("decision_grade") is not True:
                    findings.append(_critical("Decision-grade claim cites non-decision-grade evidence", f"{prefix}.supporting_evidence_item_ids"))
    for index, decision in enumerate(_as_list(payload.get("decisions")), start=1):
        if not isinstance(decision, Mapping):
            continue
        verdict = str(decision.get("verdict") or "")
        if verdict not in {"apply", "study"}:
            continue
        for claim_id in _as_list(decision.get("claim_ids")):
            claim = claim_by_id.get(str(claim_id))
            if claim and claim.get("decision_grade") is not True:
                findings.append(
                    _critical(
                        "Apply/study decision cannot cite a non-decision-grade canonical claim",
                        f"intelligence_contract.decisions[{index}].claim_ids",
                    )
                )
    radar = payload.get("radar_exchange") if isinstance(payload.get("radar_exchange"), Mapping) else None
    if radar:
        if radar.get("contract_version") != RADAR_INTELLIGENCE_CONTRACT_VERSION:
            findings.append(_critical("Radar exchange contract version is missing or unsupported", "intelligence_contract.radar_exchange.contract_version"))
        if radar.get("context_only_can_satisfy_gate") is not False:
            findings.append(_critical("Radar context-only records must not satisfy demand evidence gates", "intelligence_contract.radar_exchange.context_only_can_satisfy_gate"))
    return findings


def _validate_decision_cards(
    value: object,
    feedback_ids: set[str],
    claim_by_atom_id: dict[int, Mapping[str, Any]],
    findings: list[ReportQualityFinding],
) -> None:
    cards = _as_list(value)
    if len(cards) < 3:
        findings.append(_critical("Report must include at least three operator decision cards", "decision_cards"))
        return
    for index, card in enumerate(cards[:5], start=1):
        if not isinstance(card, Mapping):
            findings.append(_critical("Decision card must be an object", f"decision_cards[{index}]"))
            continue
        _require_text(card, ("id", "title", "why_for_operator", "confidence", "next_action", "success_criterion"), findings, f"decision_cards[{index}]")
        verdict = str(card.get("verdict") or "").strip()
        if verdict not in ALLOWED_DECISION_VERDICTS:
            findings.append(_critical("Decision card has an unsupported operator verdict", f"decision_cards[{index}].verdict"))
        if not _as_list(card.get("evidence_atom_ids")):
            findings.append(_critical("Decision card must cite evidence atom IDs", f"decision_cards[{index}].evidence_atom_ids"))
        for value in _as_list(card.get("evidence_atom_ids")):
            try:
                atom_id = int(value)
            except (TypeError, ValueError):
                continue
            claim_card = claim_by_atom_id.get(atom_id)
            if not claim_card:
                continue
            quote_verified = bool(claim_card.get("quote_verified"))
            if quote_verified:
                continue
            if not _claim_card_is_explicitly_weak(claim_card):
                findings.append(
                    _critical(
                        "Decision card cites an unverifiable claim that is not explicitly weak or single-source",
                        f"decision_cards[{index}].evidence_atom_ids",
                    )
                )
            if verdict in {"apply", "study"}:
                findings.append(
                    _critical(
                        "Apply/study decision cards cannot rely on unverifiable claim evidence",
                        f"decision_cards[{index}].evidence_atom_ids",
                    )
                )
        _require_feedback_ref(card, feedback_ids, findings, f"decision_cards[{index}]")


def _validate_claim_cards(cards: list, findings: list[ReportQualityFinding]) -> None:
    if len(cards) < 3:
        findings.append(_critical("Report must include three to five claim evidence cards", "claim_cards"))
        return
    for index, card in enumerate(cards[:5], start=1):
        if not isinstance(card, Mapping):
            findings.append(_critical("Claim card must be an object", f"claim_cards[{index}]"))
            continue
        _require_text(
            card,
            (
                "id",
                "claim",
                "evidence_tier",
                "evidence_role",
                "verification_status",
                "claim_scope",
                "time_horizon",
                "confidence",
                "caveat",
                "expiry_hint",
                "staleness_status",
                "wording_policy",
                "next_verification_step",
                "source_independence_key",
            ),
            findings,
            f"claim_cards[{index}]",
        )
        if not _as_list(card.get("evidence_atom_ids")):
            findings.append(_critical("Claim card must cite atom IDs", f"claim_cards[{index}].evidence_atom_ids"))
        urls = _as_list(card.get("source_urls"))
        if not urls:
            findings.append(_critical("Claim card must include source URLs", f"claim_cards[{index}].source_urls"))
        try:
            source_count = int(card.get("source_count") or 0)
        except (TypeError, ValueError):
            source_count = 0
        if source_count <= 0:
            findings.append(_critical("Claim card must include source count", f"claim_cards[{index}].source_count"))
        if "quote_verified" not in card or not isinstance(card.get("quote_verified"), bool):
            findings.append(_critical("Claim card must include boolean quote_verified", f"claim_cards[{index}].quote_verified"))
        if not bool(card.get("quote_verified")) and not _claim_card_is_explicitly_weak(card):
            findings.append(
                _critical(
                    "Unverifiable top claim must be explicitly labeled weak/single-source and decision-ineligible",
                    f"claim_cards[{index}].quote_verified",
                )
            )
        if (
            (str(card.get("evidence_tier") or "").startswith("weak") or not bool(card.get("quote_verified")))
            and str(card.get("wording_policy") or "") != "cautious_weak_claim"
        ):
            findings.append(
                _critical(
                    "Weak claim must use cautious wording policy",
                    f"claim_cards[{index}].wording_policy",
                )
            )


def _validate_deep_explanation_cards(value: object, findings: list[ReportQualityFinding]) -> None:
    cards = _as_list(value)
    if len(cards) < 3:
        findings.append(_critical("Report must include three to five deep explanation cards", "deep_explanation_cards"))
        return
    required = (
        "id",
        "claim_card_id",
        "title",
        "what_is_this",
        "why_now",
        "how_it_works",
        "where_is_hype",
        "what_to_do",
        "what_not_to_do",
        "caveat",
        "evidence_tier",
        "quote_verification_status",
        "what_would_change_my_mind",
    )
    for index, card in enumerate(cards[:5], start=1):
        if not isinstance(card, Mapping):
            findings.append(_critical("Deep explanation card must be an object", f"deep_explanation_cards[{index}]"))
            continue
        _require_text(card, required, findings, f"deep_explanation_cards[{index}]")
        if not _as_list(card.get("source_urls")):
            findings.append(_critical("Deep explanation card must cite source URLs", f"deep_explanation_cards[{index}].source_urls"))
        if card.get("explanatory_only") is not True:
            findings.append(
                _critical(
                    "Deep explanation card must be labeled explanatory-only",
                    f"deep_explanation_cards[{index}].explanatory_only",
                )
            )


def _validate_thread_deltas(value: object, findings: list[ReportQualityFinding], *, expected_count: int) -> None:
    deltas = _as_list(value)
    if not deltas:
        findings.append(_critical("Report must include temporal thread deltas", "thread_deltas"))
        return
    if len(deltas) < expected_count:
        findings.append(
            _critical(
                f"Report must include at least {expected_count} temporal thread deltas",
                "thread_deltas",
            )
        )
    for index, delta in enumerate(deltas[:5], start=1):
        if not isinstance(delta, Mapping):
            findings.append(_critical("Thread delta must be an object", f"thread_deltas[{index}]"))
            continue
        _require_text(
            delta,
            (
                "thread_slug",
                "previous_state",
                "previous_week_state",
                "new_evidence",
                "updated_interpretation",
                "confidence_movement",
                "confidence_change",
                "delta_reason",
                "state",
                "why_this_is_one_thread",
                "merge_split_audit_status",
            ),
            findings,
            f"thread_deltas[{index}]",
        )
        if not _as_list(delta.get("this_week_evidence")):
            findings.append(
                _critical(
                    "Thread delta must include this-week evidence details",
                    f"thread_deltas[{index}].this_week_evidence",
                )
            )
        if delta.get("state") != "insufficient_history" and not _as_list(delta.get("new_evidence_atom_ids")):
            findings.append(
                _critical(
                    "Thread delta must cite this-week evidence atom IDs or mark insufficient history",
                    f"thread_deltas[{index}].new_evidence_atom_ids",
                )
            )


def _validate_action_cards(value: object, feedback_ids: set[str], findings: list[ReportQualityFinding]) -> None:
    cards = _as_list(value)
    if len(cards) < 3:
        findings.append(_critical("Report must include at least three operational action cards", "action_cards"))
        return
    try_count = sum(1 for card in cards if isinstance(card, Mapping) and card.get("action_kind") == "try")
    experiment_count = sum(1 for card in cards if isinstance(card, Mapping) and card.get("action_kind") == "experiment")
    if try_count < 2:
        findings.append(_critical("Report must include at least two try action cards", "action_cards"))
    if experiment_count < 1:
        findings.append(_critical("Report must include at least one experiment action card", "action_cards"))
    for index, card in enumerate(cards[:6], start=1):
        if not isinstance(card, Mapping):
            findings.append(_critical("Action card must be an object", f"action_cards[{index}]"))
            continue
        _require_text(
            card,
            (
                "id",
                "target_ref",
                "action_kind",
                "title",
                "effort",
                "scope",
                "next_step",
                "success_criterion",
                "kill_condition",
                "follow_up_hint",
                "outcome_policy",
            ),
            findings,
            f"action_cards[{index}]",
        )
        if str(card.get("scope") or "").strip() not in ALLOWED_ACTION_SCOPES:
            findings.append(_critical("Action card scope is unsupported", f"action_cards[{index}].scope"))
        if str(card.get("action_kind") or "").strip() not in {"try", "experiment"}:
            findings.append(_critical("Action card kind must be try or experiment", f"action_cards[{index}].action_kind"))
        if not _as_list(card.get("feedback_event_options")):
            findings.append(
                _critical(
                    "Action card must expose feedback event options",
                    f"action_cards[{index}].feedback_event_options",
                )
            )
        _require_feedback_ref(card, feedback_ids, findings, f"action_cards[{index}]")


def _validate_project_diagnostic(value: object, findings: list[ReportQualityFinding]) -> None:
    diagnostic = value if isinstance(value, Mapping) else {}
    if not diagnostic:
        findings.append(_critical("Report must include a project fit diagnostic", "project_diagnostic"))
        return
    if not _as_list(diagnostic.get("checked_projects")):
        findings.append(_critical("Project diagnostic must list checked projects", "project_diagnostic.checked_projects"))
    if "confirmed_leads" not in diagnostic or "project_watch" not in diagnostic or "learning_only_implications" not in diagnostic:
        findings.append(_critical("Project diagnostic must include confirmed/watch/learning tiers", "project_diagnostic"))
    suggestions = _as_list(diagnostic.get("implementation_suggestions"))
    has_project_surface = bool(_as_list(diagnostic.get("confirmed_leads")) or _as_list(diagnostic.get("project_watch")))
    if has_project_surface and not suggestions:
        findings.append(
            _critical(
                "Project leads must include concrete implementation suggestions",
                "project_diagnostic.implementation_suggestions",
            )
        )
    for index, suggestion in enumerate(suggestions[:4], start=1):
        if not isinstance(suggestion, Mapping):
            findings.append(_critical("Implementation suggestion must be an object", f"project_diagnostic.implementation_suggestions[{index}]"))
            continue
        _require_text(
            suggestion,
            ("id", "project", "suggestion_type", "title", "effort", "risk_caveat", "next_step", "source_policy"),
            findings,
            f"project_diagnostic.implementation_suggestions[{index}]",
        )
        if not _as_list(suggestion.get("acceptance_criteria")):
            findings.append(
                _critical(
                    "Implementation suggestion must include acceptance criteria",
                    f"project_diagnostic.implementation_suggestions[{index}].acceptance_criteria",
                )
            )
        if not _as_list(suggestion.get("source_atom_ids")) and not _as_list(suggestion.get("source_urls")):
            findings.append(
                _critical(
                    "Implementation suggestion must include source atom links",
                    f"project_diagnostic.implementation_suggestions[{index}].source_atom_ids",
                )
            )
    if "close_but_not_enough_signals" not in diagnostic:
        findings.append(
            _critical(
                "Project diagnostic must include close-but-not-enough signals",
                "project_diagnostic.close_but_not_enough_signals",
            )
        )
    if "missing_config_suggestions" not in diagnostic:
        findings.append(
            _critical(
                "Project diagnostic must include missing evidence/config suggestions",
                "project_diagnostic.missing_config_suggestions",
            )
        )
    if not _as_list(diagnostic.get("confirmed_leads")) and not str(diagnostic.get("no_confirmed_leads_reason") or "").strip():
        findings.append(
            _critical(
                "Zero confirmed project leads must include diagnostic explanation",
                "project_diagnostic.no_confirmed_leads_reason",
            )
        )
    if not _as_list(diagnostic.get("rejected_broad_overlaps")):
        findings.append(
            _critical(
                "Project diagnostic must expose rejected broad overlaps",
                "project_diagnostic.rejected_broad_overlaps",
            )
        )


def _validate_feedback_targets(value: list, findings: list[ReportQualityFinding]) -> None:
    if len(value) < 3:
        findings.append(_critical("Report must request at least three concrete feedback targets", "feedback_targets"))
        return
    read_count = sum(
        1
        for target in value
        if isinstance(target, Mapping) and str(target.get("target_type") or "") in {"read", "read_queue"}
    )
    action_count = sum(1 for target in value if isinstance(target, Mapping) and str(target.get("target_type") or "") == "action")
    has_missed = any(isinstance(target, Mapping) and str(target.get("target_type") or "") == "missed_post" for target in value)
    has_trust = any(isinstance(target, Mapping) and str(target.get("target_type") or "") == "trust_correction" for target in value)
    if read_count < 2:
        findings.append(_critical("Report must request feedback for at least two read items", "feedback_targets"))
    if action_count < 1:
        findings.append(_critical("Report must request feedback for at least one action", "feedback_targets"))
    if not has_missed:
        findings.append(_critical("Report must request missed-post or no-missed feedback", "feedback_targets"))
    if not has_trust:
        findings.append(_critical("Report must request trust-correction feedback", "feedback_targets"))
    for index, target in enumerate(value[:6], start=1):
        if not isinstance(target, Mapping):
            findings.append(_critical("Feedback target must be an object", f"feedback_targets[{index}]"))
            continue
        _require_text(target, ("id", "target_type", "prompt"), findings, f"feedback_targets[{index}]")
        if not _as_list(target.get("event_options")):
            findings.append(_critical("Feedback target must include event options", f"feedback_targets[{index}].event_options"))


def _feedback_used_summary(feedback_context: Mapping[str, Any]) -> dict:
    counts = feedback_context.get("counts_by_feedback") if isinstance(feedback_context, Mapping) else {}
    counts = counts if isinstance(counts, Mapping) else {}
    changes = feedback_context.get("feedback_changes") if isinstance(feedback_context, Mapping) else {}
    changes = changes if isinstance(changes, Mapping) else {}
    downranked_threads = _as_list(feedback_context.get("downranked_thread_slugs"))
    downranked_atoms = _as_list(feedback_context.get("downranked_atom_refs"))
    downranked_targets = _as_list(feedback_context.get("downranked_target_refs"))
    promoted = _as_list(feedback_context.get("promoted_target_refs"))
    eval_examples = _as_list(feedback_context.get("feedback_eval_examples"))
    if int(feedback_context.get("event_count") or 0) <= 0:
        return {
            "status": "no_feedback",
            "summary": changes.get("summary") or "Нет prior feedback: персонализация остается низкой.",
            "downranked": [],
            "promoted": [],
            "eval_example_count": 0,
        }
    parts = []
    if downranked_threads or downranked_atoms or downranked_targets:
        parts.append(
            f"Понижены похожие темы/атомы: {len(downranked_threads) + len(downranked_atoms) + len(downranked_targets)}."
        )
    if promoted:
        parts.append(f"Повышены похожие цели: {len(promoted)}.")
    if eval_examples:
        parts.append(f"Добавлены eval-примеры из фидбека: {len(eval_examples)}.")
    if not parts and counts:
        parts.append("Фидбек учтен как общий сигнал ранжирования.")
    return {
        "status": "feedback_used",
        "summary": changes.get("summary") or " ".join(parts),
        "counts_by_feedback": dict(counts),
        "downranked": [*downranked_threads, *downranked_atoms, *downranked_targets],
        "promoted": promoted,
        "eval_example_count": len(eval_examples),
    }


def _feedback_targets(analysis: Mapping[str, Any], atoms: list[dict], feedback_context: Mapping[str, Any]) -> list[dict]:
    targets: list[dict] = []
    actions = _analysis_items(analysis, "actions")
    action_targets = actions[:3]
    while len(action_targets) < 3:
        action_targets.append({"title": f"Операционное действие {len(action_targets) + 1}"})
    for index, action in enumerate(action_targets, start=1):
        targets.append(
            {
                "id": f"action-{index}-feedback",
                "target_type": "action",
                "target_ref": f"action-{index}",
                "prompt": f"После попытки отметьте результат действия: {_analysis_text(action, 'title', 'action')}.",
                "event_options": ["tried", "useful", "applied_to_project", "wrong_priority", "too_shallow", "not_interested"],
                "why_needed": "Это связывает недельный отчет с реальным результатом, а не только с намерением.",
            }
        )
    read_atoms = atoms[:2]
    while len(read_atoms) < 2:
        read_atoms.append({})
    for index, atom in enumerate(read_atoms[:2], start=1):
        target_id = "read-queue-feedback" if index == 1 else f"read-queue-{index}-feedback"
        atom_id = atom.get("id") if isinstance(atom, Mapping) else None
        targets.append(
            {
                "id": target_id,
                "target_type": "read_queue",
                "target_ref": f"atom:{atom_id}" if atom_id else f"read-slot-{index}",
                "prompt": f"Отметьте прочитанный источник {index}: полезно, слишком мелко или не по приоритету.",
                "event_options": ["read", "useful", "too_shallow", "wrong_priority", "not_interested"],
                "why_needed": "Так система учится отличать полезные источники от шумных.",
            }
        )
    targets.append(
        {
            "id": "missed-post-feedback",
            "target_type": "missed_post",
            "target_ref": "weekly-report",
            "prompt": "Укажите важный пропущенный пост или явно отметьте, что пропусков не было.",
            "event_options": ["missed_important_post", "no_missed_posts"],
            "why_needed": "Пропущенные посты становятся eval-примерами для следующей недели.",
        }
    )
    targets.append(
        {
            "id": "trust-correction-feedback",
            "target_type": "trust_correction",
            "target_ref": "claim_cards",
            "prompt": "Исправьте доверие к одному утверждению: завышено, занижено или нужна проверка.",
            "event_options": ["trust_too_high", "trust_too_low", "verify_first"],
            "why_needed": (
                "При отсутствии фидбека персонализация остается низкой."
                if int(feedback_context.get("event_count") or 0) <= 0
                else "Это уточняет ранжирование похожих утверждений."
            ),
        }
    )
    return _dedupe_by_id(targets)[:8]


def _action_cards(analysis: Mapping[str, Any], feedback_targets: list[dict]) -> list[dict]:
    target_ids = [target["id"] for target in feedback_targets if str(target.get("target_type")) == "action"]
    cards: list[dict] = []
    for index, item in enumerate(_analysis_items(analysis, "actions")[:6], start=1):
        title = _analysis_text(item, "title", "action") or f"Действие {index}"
        success = _analysis_text(item, "success_criterion") or "Есть наблюдаемый результат."
        scope = _infer_scope(title, _analysis_text(item, "next_step", "why"))
        cards.append(
            {
                "id": f"action-{index}",
                "target_ref": f"action-{index}",
                "action_kind": "experiment" if scope == "experiment" else "try",
                "title": title,
                "effort": _infer_effort(title),
                "scope": scope,
                "next_step": _analysis_text(item, "next_step", "why") or title,
                "success_criterion": success,
                "kill_condition": "Остановить, если за один короткий цикл нет измеримого результата или источник не подтверждает пользу.",
                "follow_up_hint": "Вернуться к этому пункту в следующем недельном фидбеке.",
                "feedback_event_options": ["tried", "useful", "applied_to_project", "wrong_priority", "too_shallow", "not_interested"],
                "outcome_policy": "Не считать действие полезным, пока фидбек не содержит tried/useful/applied_to_project.",
                "feedback_target_id": target_ids[index - 1] if index - 1 < len(target_ids) else "trust-correction-feedback",
            }
        )
    study_items = _analysis_items(analysis, "study_now")
    while sum(1 for card in cards if card.get("action_kind") == "try") < 2:
        index = len(cards) + 1
        study = study_items[(index - 1) % len(study_items)] if study_items else {}
        topic = _analysis_text(study, "topic", "title") or "ключевой источник недели"
        cards.append(
            {
                "id": f"action-{index}",
                "target_ref": f"action-{index}",
                "action_kind": "try",
                "title": f"Проверить на практике: {topic}",
                "effort": "30 мин",
                "scope": "skill",
                "next_step": "Взять один источник из отчета и выписать применимый прием.",
                "success_criterion": "Есть один конкретный прием, который можно повторить или отклонить.",
                "kill_condition": "Остановить, если источник не дает проверяемого приема за 30 минут.",
                "follow_up_hint": "В фидбеке отметить tried/useful или too_shallow/wrong_priority.",
                "feedback_event_options": ["tried", "useful", "wrong_priority", "too_shallow", "not_interested"],
                "outcome_policy": "Не считать useful без явного фидбека оператора.",
                "feedback_target_id": target_ids[index - 1] if index - 1 < len(target_ids) else "trust-correction-feedback",
            }
        )
    if not any(card.get("action_kind") == "experiment" for card in cards):
        index = len(cards) + 1
        cards.append(
            {
                "id": f"action-{index}",
                "target_ref": f"action-{index}",
                "action_kind": "experiment",
                "title": "Запустить маленький недельный эксперимент",
                "effort": "60 мин",
                "scope": "experiment",
                "next_step": "Выбрать один claim card и проверить его на мини-задаче или benchmark.",
                "success_criterion": "Есть измеримый результат, заметка о качестве и решение продолжать/убить.",
                "kill_condition": "Остановить, если claim не подтверждается источником или не дает измеримого эффекта.",
                "follow_up_hint": "Записать tried/useful/applied_to_project или wrong_priority.",
                "feedback_event_options": ["tried", "useful", "applied_to_project", "wrong_priority", "too_shallow"],
                "outcome_policy": "Эксперимент засчитывается только после outcome feedback.",
                "feedback_target_id": target_ids[index - 1] if index - 1 < len(target_ids) else "trust-correction-feedback",
            }
        )
    return cards[:6]


def _claim_cards(atoms: list[dict]) -> list[dict]:
    cards: list[dict] = []
    for index, atom in enumerate(sorted(atoms, key=_atom_score, reverse=True)[:5], start=1):
        urls = [str(url).strip() for url in (atom.get("source_urls") or []) if str(url).strip()]
        source_posts = [post for post in (atom.get("source_posts") or []) if isinstance(post, Mapping)]
        source_post_ids = _int_values(atom.get("source_post_ids"))
        independence_keys = _source_independence_keys(urls, source_posts)
        source_count = len(urls)
        independent_sources = len(independence_keys)
        verification = _verify_evidence_quote(str(atom.get("evidence_quote") or ""), source_posts)
        evidence_role = _evidence_role(str(atom.get("atom_type") or ""))
        evidence_tier = _evidence_tier(
            atom_type=str(atom.get("atom_type") or ""),
            source_count=source_count,
            independent_sources=independent_sources,
            quote_verified=verification["quote_verified"],
        )
        decision_eligible = bool(verification["quote_verified"] and source_count > 0)
        cards.append(
            {
                "id": f"claim-{index}",
                "claim": str(atom.get("claim") or atom.get("summary") or "").strip(),
                "evidence_atom_ids": [int(atom.get("id") or 0)],
                "source_post_ids": source_post_ids,
                "source_count": source_count,
                "source_urls": urls,
                "source_type": str(atom.get("atom_type") or "unknown"),
                "independent_sources": independent_sources,
                "source_independence_key": independence_keys[0] if independence_keys else "unknown",
                "source_independence_keys": independence_keys,
                "evidence_tier": evidence_tier,
                "evidence_role": evidence_role,
                "confidence": _confidence_label(atom.get("confidence")),
                "evidence_quote": str(atom.get("evidence_quote") or "").strip(),
                "quote_verified": verification["quote_verified"],
                "quote_verified_source_post_ids": verification["source_post_ids"],
                "verification_status": verification["verification_status"],
                "claim_scope": _claim_scope(str(atom.get("atom_type") or "")),
                "time_horizon": _time_horizon(str(atom.get("atom_type") or "")),
                "decision_eligible": decision_eligible,
                "staleness_status": str(atom.get("staleness_status") or "active"),
                "caveat": _claim_caveat(
                    source_count=source_count,
                    independent_sources=independent_sources,
                    quote_verified=verification["quote_verified"],
                    verification_status=verification["verification_status"],
                ),
                "expiry_hint": str(atom.get("expiry_hint") or "").strip() or _expiry_hint(str(atom.get("atom_type") or "")),
                "wording_policy": (
                    "cautious_weak_claim"
                    if evidence_tier.startswith("weak") or not verification["quote_verified"]
                    else "source_bounded"
                ),
                "next_verification_step": _verification_action(
                    quote_verified=verification["quote_verified"],
                    independent_sources=independent_sources,
                    verification_status=verification["verification_status"],
                ),
            }
        )
    return cards


def _deep_explanation_cards(claim_cards: list[dict]) -> list[dict]:
    cards: list[dict] = []
    for index, claim in enumerate(claim_cards[:5], start=1):
        claim_text = str(claim.get("claim") or "").strip()
        scope = str(claim.get("claim_scope") or "general").replace("_", " ")
        tier = str(claim.get("evidence_tier") or "unknown")
        verification = str(claim.get("verification_status") or "unknown")
        caveat = str(claim.get("caveat") or "Evidence caveat is not available.").strip()
        cards.append(
            {
                "id": f"deep-explain-{index}",
                "claim_card_id": claim.get("id"),
                "title": claim_text[:96] or f"Signal {index}",
                "what_is_this": (
                    f"Plain-language reading: this is a {scope} signal about {claim_text}"
                    if claim_text
                    else f"Plain-language reading: this is a {scope} signal."
                ),
                "why_now": (
                    "It appears among the strongest current claim cards, so it is worth checking before the next weekly plan."
                ),
                "how_it_works": (
                    "Start from the cited source, verify the quote, then translate the claim into one read/try/build action."
                ),
                "where_is_hype": (
                    "Treat it as hype if the quote is unverified, the source is single-channel, or the claim has no measurable workflow outcome."
                ),
                "what_to_do": claim.get("next_verification_step")
                or "Verify the cited source and run one small check before acting on it.",
                "what_not_to_do": (
                    "Do not generalize this beyond its source scope or treat it as build-ready without independent evidence."
                ),
                "caveat": caveat,
                "source_urls": claim.get("source_urls") or [],
                "evidence_tier": tier,
                "quote_verification_status": verification,
                "what_would_change_my_mind": (
                    "A stronger independent source contradicts it, the cited quote cannot be verified, or a small trial fails."
                ),
                "explanatory_only": True,
            }
        )
    return cards


def _decision_cards(
    analysis: Mapping[str, Any],
    claim_cards: list[dict],
    action_cards: list[dict],
    feedback_targets: list[dict],
) -> list[dict]:
    cards: list[dict] = []
    evidence_ids = _top_claim_atom_ids(claim_cards)
    for index, action in enumerate(action_cards[:2], start=1):
        cards.append(
            {
                "id": f"decision-{index}",
                "verdict": "apply" if index == 1 else "verify_first",
                "title": action["title"],
                "why_for_operator": action["next_step"],
                "evidence_atom_ids": evidence_ids,
                "confidence": "medium" if evidence_ids else "low",
                "next_action": action["next_step"],
                "success_criterion": action["success_criterion"],
                "feedback_target_id": action["feedback_target_id"],
            }
        )
    study_items = _analysis_items(analysis, "study_now")
    for item in study_items[: max(0, 4 - len(cards))]:
        index = len(cards) + 1
        cards.append(
            {
                "id": f"decision-{index}",
                "verdict": "study",
                "title": _analysis_text(item, "topic", "title") or f"Тема для изучения {index}",
                "why_for_operator": _analysis_text(item, "reason", "why_it_matters") or "Тема повышает качество инженерных решений.",
                "evidence_atom_ids": evidence_ids,
                "confidence": "medium" if evidence_ids else "low",
                "next_action": "Прочитать источники и выписать один применимый инженерный прием.",
                "success_criterion": "Сформулирован один прием, который можно проверить на практике.",
                "feedback_target_id": "read-queue-feedback",
            }
        )
    caveats = _analysis_items(analysis, "caveats")
    if len(cards) < 3:
        cards.append(
            {
                "id": f"decision-{len(cards) + 1}",
                "verdict": "verify_first",
                "title": "Сначала проверить слабые утверждения",
                "why_for_operator": _analysis_text(caveats[0], "caveat", "summary") if caveats else "Часть сигналов может быть одноисточниковой или спекулятивной.",
                "evidence_atom_ids": evidence_ids,
                "confidence": "low",
                "next_action": "Проверить карточки утверждений с низкой независимостью источников.",
                "success_criterion": "Для ключевого утверждения найдено подтверждение или оно понижено в приоритете.",
                "feedback_target_id": "trust-correction-feedback",
            }
        )
    feedback_ids = {str(target.get("id")) for target in feedback_targets}
    for card in cards:
        if card.get("feedback_target_id") not in feedback_ids:
            card["feedback_target_id"] = "trust-correction-feedback"
    return cards[:5]


def _thread_deltas(context: Mapping[str, Any], threads: list[dict]) -> list[dict]:
    week_start = _parse_iso(context.get("week_start"))
    week_end = _parse_iso(context.get("week_end"))
    candidates = [thread for thread in threads if thread.get("changed_this_week")] or threads
    deltas: list[dict] = []
    for thread in candidates[:5]:
        atoms = sorted(
            [atom for atom in (thread.get("atoms") or []) if isinstance(atom, dict)],
            key=lambda item: str(item.get("last_seen_at") or ""),
        )
        previous_atoms, this_week_atoms = _split_thread_atoms(atoms, week_start=week_start, week_end=week_end)
        if not this_week_atoms:
            this_week_atoms = atoms[-2:] if atoms else []
        insufficient = not previous_atoms
        new_evidence_ids = [int(atom.get("id") or 0) for atom in this_week_atoms if int(atom.get("id") or 0)]
        previous_state = _previous_thread_state(previous_atoms)
        if insufficient:
            previous_state = "Недостаточно истории до этой недели: нет более ранних атомов для сравнения."
        this_week_evidence = [_evidence_delta_item(atom) for atom in this_week_atoms[:4]]
        updated_interpretation = _updated_thread_interpretation(thread, this_week_atoms)
        confidence_change = _confidence_change(previous_atoms, this_week_atoms, insufficient=insufficient)
        deltas.append(
            {
                "thread_id": thread.get("id"),
                "thread_slug": str(thread.get("slug") or ""),
                "title": str(thread.get("title") or thread.get("slug") or ""),
                "previous_state": previous_state,
                "previous_week_state": previous_state,
                "new_evidence": _compact("; ".join(str(atom.get("claim") or "") for atom in this_week_atoms[:3]), 320),
                "this_week_evidence": this_week_evidence,
                "updated_interpretation": updated_interpretation,
                "confidence_movement": confidence_change,
                "confidence_change": confidence_change,
                "delta_reason": _delta_reason(
                    insufficient=insufficient,
                    previous_atoms=previous_atoms,
                    this_week_atoms=this_week_atoms,
                ),
                "new_evidence_atom_ids": [] if insufficient else new_evidence_ids,
                "state": _thread_delta_state(thread, previous_atoms, this_week_atoms, insufficient=insufficient),
                "why_this_is_one_thread": _why_this_is_one_thread(thread, atoms),
                "merge_split_audit_status": _merge_split_audit_status(thread, atoms),
            }
        )
    return deltas


def _project_diagnostic(
    *,
    analysis: Mapping[str, Any],
    project_links: list[dict],
    projects: list[dict],
    threads: list[dict],
) -> dict:
    checked_projects = [
        str(project.get("name") or project.get("repo") or "").strip()
        for project in projects
        if str(project.get("name") or project.get("repo") or "").strip()
    ]
    confirmed = []
    watch = []
    for link in project_links:
        item = {
            "project": link.get("project"),
            "repo": link.get("repo"),
            "thread_slug": link.get("thread_slug"),
            "thread_title": link.get("thread_title"),
            "confidence": link.get("confidence"),
            "why": link.get("why"),
            "next_step": link.get("next_step"),
            "evidence_urls": link.get("evidence_urls") or [],
            "source_atom_ids": link.get("source_atom_ids") or [],
            "shared_terms": link.get("shared_terms") or [],
        }
        if str(link.get("confidence") or "") == "higher" and len(link.get("evidence_urls") or []) >= 2:
            confirmed.append(item)
        else:
            watch.append(item)
    close_signals = _close_but_not_enough_signals(
        projects=projects,
        threads=threads,
        linked_pairs={(str(link.get("project")), str(link.get("thread_slug"))) for link in project_links},
    )
    rejected_broad = _rejected_broad_overlaps(close_signals)
    study_items = _analysis_items(analysis, "study_now")
    learning = [
        {
            "topic": _analysis_text(item, "topic", "title"),
            "reason": _analysis_text(item, "reason", "why_it_matters"),
        }
        for item in study_items[:4]
    ]
    if not learning:
        learning = [
            {
                "topic": str(thread.get("title") or thread.get("slug") or ""),
                "reason": "Полезно как обучение, но проектная связь пока не доказана.",
            }
            for thread in threads[:3]
        ]
    return {
        "checked_projects": checked_projects or ["src/config/projects.yaml"],
        "checked_project_count": len(checked_projects),
        "confirmed_leads": confirmed[:4],
        "project_watch": watch[:6],
        "implementation_suggestions": _implementation_suggestions(confirmed, watch),
        "learning_only_implications": learning[:4],
        "close_but_not_enough_signals": close_signals[:8],
        "rejected_broad_overlaps": rejected_broad or ["AI", "workflow", "evidence", "tool"],
        "no_confirmed_leads_reason": (
            "Нет подтвержденных проектных лидов: совпадения по широким словам подавлены, "
            "а специфичных доказательств в текущем контексте недостаточно."
        ),
        "missing_evidence": [
            "Нужны специфичные сущности проекта, а не только общие слова.",
            "Нужны source atoms с прямой связью с репозиторием или рабочим процессом.",
        ],
        "missing_config_suggestions": [
            "Добавить в projects.yaml уникальные названия продуктов, библиотек, API и доменные фразы.",
            "Добавить ожидаемые workflows проекта, чтобы learning-only сигнал мог стать project watch.",
        ],
    }


def _canonical_source_observations(atoms: list[dict]) -> tuple[list[dict], dict[int, list[str]]]:
    observations: list[dict] = []
    observation_ids_by_atom: dict[int, list[str]] = {}
    seen: set[str] = set()
    for atom in atoms:
        atom_id = _safe_int_value(atom.get("id"))
        urls = [str(url).strip() for url in (atom.get("source_urls") or []) if str(url).strip()]
        posts = [post for post in (atom.get("source_posts") or []) if isinstance(post, Mapping)]
        for post in posts:
            post_id = _safe_int_value(post.get("post_id"))
            url = str(post.get("message_url") or "").strip() or (urls[0] if urls else "")
            channel = str(post.get("channel_username") or "").strip()
            observation_id = f"source_observation:telegram_post:{post_id or _slug(url or channel or atom_id)}"
            if observation_id not in seen:
                seen.add(observation_id)
                observations.append(
                    {
                        "id": observation_id,
                        "source_type": "telegram_post",
                        "url": url,
                        "observed_at": str(post.get("posted_at") or atom.get("last_seen_at") or atom.get("first_seen_at") or ""),
                        "raw_excerpt": _source_excerpt(atom, post),
                        "metadata": {
                            "channel_username": channel,
                            "post_id": post_id or None,
                            "atom_ids": [atom_id] if atom_id else [],
                        },
                        "collection_method": "telegram_ingestion",
                        "ingestion_provenance": {
                            "derived_from": "knowledge_atom.source_posts",
                            "knowledge_atom_id": atom_id or None,
                        },
                    }
                )
            if atom_id:
                observation_ids_by_atom.setdefault(atom_id, [])
                if observation_id not in observation_ids_by_atom[atom_id]:
                    observation_ids_by_atom[atom_id].append(observation_id)
        for index, url in enumerate(urls, start=1):
            observation_id = f"source_observation:url:{_slug(url)}"
            if observation_id not in seen:
                seen.add(observation_id)
                observations.append(
                    {
                        "id": observation_id,
                        "source_type": "telegram_link" if "t.me/" in url else "web_link",
                        "url": url,
                        "observed_at": str(atom.get("last_seen_at") or atom.get("first_seen_at") or ""),
                        "raw_excerpt": _source_excerpt(atom, {}),
                        "metadata": {
                            "atom_ids": [atom_id] if atom_id else [],
                            "source_index": index,
                        },
                        "collection_method": "sidecar_projection",
                        "ingestion_provenance": {
                            "derived_from": "knowledge_atom.source_urls",
                            "knowledge_atom_id": atom_id or None,
                        },
                    }
                )
            if atom_id:
                observation_ids_by_atom.setdefault(atom_id, [])
                if observation_id not in observation_ids_by_atom[atom_id]:
                    observation_ids_by_atom[atom_id].append(observation_id)
    return observations, observation_ids_by_atom


def _canonical_evidence_items(
    claim_cards: list[dict],
    atoms: list[dict],
    observation_ids_by_atom: dict[int, list[str]],
) -> list[dict]:
    atom_by_id = {_safe_int_value(atom.get("id")): atom for atom in atoms if _safe_int_value(atom.get("id"))}
    items: list[dict] = []
    for claim in claim_cards:
        claim_id = str(claim.get("id") or "").strip() or "claim"
        atom_ids = _int_values(claim.get("evidence_atom_ids"))
        observation_ids = _unique(
            observation_id
            for atom_id in atom_ids
            for observation_id in observation_ids_by_atom.get(atom_id, [])
        )
        if not observation_ids:
            observation_ids = [""]
        for index, observation_id in enumerate(observation_ids, start=1):
            source_atom = next((atom_by_id.get(atom_id) for atom_id in atom_ids if atom_by_id.get(atom_id)), {})
            polarity = _canonical_polarity(source_atom, claim)
            context_only = bool(claim.get("context_only")) or str(claim.get("radar_role") or "") == "context_only"
            quote_verified = bool(claim.get("quote_verified"))
            tier = str(claim.get("evidence_tier") or "unsupported")
            verification_status = str(claim.get("verification_status") or "unknown")
            decision_grade = bool(
                observation_id
                and quote_verified
                and bool(claim.get("decision_eligible"))
                and not context_only
                and not tier.startswith("weak")
                and tier != "unsupported"
            )
            items.append(
                {
                    "id": f"evidence_item:{claim_id}:{index}",
                    "claim_id": claim_id,
                    "source_observation_id": observation_id,
                    "source_observation_ref": observation_id,
                    "atom_ids": atom_ids,
                    "quote": str(claim.get("evidence_quote") or "").strip(),
                    "verified_excerpt": str(claim.get("evidence_quote") or "").strip() if quote_verified else "",
                    "evidence_role": str(claim.get("evidence_role") or "commentary"),
                    "evidence_tier": tier,
                    "independence_key": _canonical_independence_key(claim, index),
                    "independence_keys": _as_list(claim.get("source_independence_keys")),
                    "verification_status": verification_status,
                    "quote_verified": quote_verified,
                    "date_relevance": str(claim.get("staleness_status") or "unknown"),
                    "scope": str(claim.get("claim_scope") or "general"),
                    "expiry_hint": str(claim.get("expiry_hint") or ""),
                    "polarity": polarity,
                    "context_only": context_only,
                    "decision_grade": decision_grade,
                    "radar_gate_eligible": False,
                }
            )
    return items


def _canonical_claims(claim_cards: list[dict], evidence_items: list[dict]) -> list[dict]:
    evidence_by_claim: dict[str, list[dict]] = {}
    for item in evidence_items:
        evidence_by_claim.setdefault(str(item.get("claim_id") or ""), []).append(item)
    claims: list[dict] = []
    for card in claim_cards:
        claim_id = str(card.get("id") or "").strip()
        if not claim_id:
            continue
        related = evidence_by_claim.get(claim_id, [])
        supporting = [
            str(item.get("id"))
            for item in related
            if str(item.get("polarity") or "") in {"supporting", "positive"}
        ]
        contradicting = [
            str(item.get("id"))
            for item in related
            if str(item.get("polarity") or "") in {"contradicting", "negative"}
        ]
        source_observation_ids = _unique(item.get("source_observation_id") for item in related if item.get("source_observation_id"))
        verification_state = "verified" if bool(card.get("quote_verified")) else str(card.get("verification_status") or "unknown")
        decision_grade = bool(
            card.get("decision_eligible")
            and verification_state == "verified"
            and supporting
            and source_observation_ids
            and all(item.get("decision_grade") is True for item in related if str(item.get("id")) in supporting)
        )
        claims.append(
            {
                "id": claim_id,
                "statement": str(card.get("claim") or "").strip(),
                "scope": str(card.get("claim_scope") or "general"),
                "time_horizon": str(card.get("time_horizon") or "unknown"),
                "supporting_evidence_item_ids": supporting,
                "contradicting_evidence_item_ids": contradicting,
                "source_observation_ids": source_observation_ids,
                "source_independence": {
                    "count": _safe_int_value(card.get("independent_sources")),
                    "keys": _as_list(card.get("source_independence_keys"))
                    or [str(card.get("source_independence_key") or "unknown")],
                },
                "confidence_band": str(card.get("confidence") or "unknown"),
                "uncertainty_reasons": [str(card.get("caveat") or "").strip()] if str(card.get("caveat") or "").strip() else [],
                "verification_state": verification_state,
                "decision_grade": decision_grade,
                "insufficient_evidence": not decision_grade,
                "wording_policy": str(card.get("wording_policy") or ""),
                "next_verification_step": str(card.get("next_verification_step") or ""),
                "atom_ids": _int_values(card.get("evidence_atom_ids")),
            }
        )
    return claims


def _canonical_atoms(atoms: list[dict], claims: list[dict], evidence_items: list[dict]) -> list[dict]:
    claim_ids_by_atom: dict[int, list[str]] = {}
    evidence_ids_by_atom: dict[int, list[str]] = {}
    for claim in claims:
        for atom_id in _int_values(claim.get("atom_ids")):
            claim_ids_by_atom.setdefault(atom_id, []).append(str(claim.get("id")))
    for evidence in evidence_items:
        for atom_id in _int_values(evidence.get("atom_ids")):
            evidence_ids_by_atom.setdefault(atom_id, []).append(str(evidence.get("id")))
    result: list[dict] = []
    for atom in atoms:
        atom_id = _safe_int_value(atom.get("id"))
        if not atom_id:
            continue
        result.append(
            {
                "id": f"knowledge_atom:{atom_id}",
                "atom_id": atom_id,
                "claim": str(atom.get("claim") or ""),
                "summary": str(atom.get("summary") or ""),
                "atom_type": str(atom.get("atom_type") or ""),
                "relation": str(atom.get("relation") or "supports"),
                "why_it_matters": str(atom.get("why_it_matters") or ""),
                "first_seen_at": str(atom.get("first_seen_at") or ""),
                "last_seen_at": str(atom.get("last_seen_at") or ""),
                "staleness_status": str(atom.get("staleness_status") or "active"),
                "claim_ids": _unique(claim_ids_by_atom.get(atom_id, [])),
                "evidence_item_ids": _unique(evidence_ids_by_atom.get(atom_id, [])),
                "source_urls": [str(url) for url in (atom.get("source_urls") or []) if str(url).strip()],
            }
        )
    return result


def _canonical_threads(
    threads: list[dict],
    claims: list[dict],
    evidence_items: list[dict],
    thread_deltas: list[dict],
) -> list[dict]:
    claim_ids_by_atom: dict[int, list[str]] = {}
    evidence_ids_by_atom: dict[int, list[str]] = {}
    for claim in claims:
        for atom_id in _int_values(claim.get("atom_ids")):
            claim_ids_by_atom.setdefault(atom_id, []).append(str(claim.get("id")))
    for evidence in evidence_items:
        for atom_id in _int_values(evidence.get("atom_ids")):
            evidence_ids_by_atom.setdefault(atom_id, []).append(str(evidence.get("id")))
    deltas_by_slug = {
        str(delta.get("thread_slug") or ""): delta
        for delta in thread_deltas
        if str(delta.get("thread_slug") or "").strip()
    }
    result: list[dict] = []
    for thread in threads:
        slug = str(thread.get("slug") or "").strip()
        atoms = [atom for atom in (thread.get("atoms") or []) if isinstance(atom, Mapping)]
        atom_ids = [_safe_int_value(atom.get("id")) for atom in atoms if _safe_int_value(atom.get("id"))]
        delta = deltas_by_slug.get(slug, {})
        result.append(
            {
                "id": f"idea_thread:{slug or _safe_int_value(thread.get('id'))}",
                "thread_slug": slug,
                "title": str(thread.get("title") or slug),
                "status": str(thread.get("status") or "active"),
                "atom_ids": atom_ids,
                "claim_ids": _unique(claim_id for atom_id in atom_ids for claim_id in claim_ids_by_atom.get(atom_id, [])),
                "evidence_item_ids": _unique(evidence_id for atom_id in atom_ids for evidence_id in evidence_ids_by_atom.get(atom_id, [])),
                "previous_state": str(delta.get("previous_state") or ""),
                "current_state": str(delta.get("updated_interpretation") or thread.get("summary") or ""),
                "delta_basis": _thread_delta_basis(delta),
                "new_evidence_atom_ids": _int_values(delta.get("new_evidence_atom_ids")),
                "momentum_vs_evidence": {
                    "momentum_7d": _float(thread.get("momentum_7d")),
                    "momentum_30d": _float(thread.get("momentum_30d")),
                    "evidence_growth": bool(_as_list(delta.get("new_evidence_atom_ids"))),
                    "momentum_is_not_evidence": True,
                },
                "contradictions": _as_list(thread.get("contradictions")),
                "merge_split_audit_status": str(delta.get("merge_split_audit_status") or ""),
            }
        )
    return result


def _canonical_decisions(decision_cards: list[dict], claims: list[dict]) -> list[dict]:
    claim_ids_by_atom: dict[int, list[str]] = {}
    decision_grade_claims = {str(claim.get("id")) for claim in claims if claim.get("decision_grade") is True}
    for claim in claims:
        for atom_id in _int_values(claim.get("atom_ids")):
            claim_ids_by_atom.setdefault(atom_id, []).append(str(claim.get("id")))
    result: list[dict] = []
    for card in decision_cards:
        atom_ids = _int_values(card.get("evidence_atom_ids"))
        all_claim_ids = _unique(claim_id for atom_id in atom_ids for claim_id in claim_ids_by_atom.get(atom_id, []))
        verdict = str(card.get("verdict") or "")
        if verdict in {"apply", "study"}:
            claim_ids = [claim_id for claim_id in all_claim_ids if claim_id in decision_grade_claims]
            context_claim_ids = [claim_id for claim_id in all_claim_ids if claim_id not in decision_grade_claims]
        else:
            claim_ids = all_claim_ids
            context_claim_ids = []
        result.append(
            {
                "id": str(card.get("id") or ""),
                "verdict": verdict,
                "title": str(card.get("title") or ""),
                "claim_ids": claim_ids,
                "context_claim_ids": context_claim_ids,
                "evidence_atom_ids": atom_ids,
                "source_policy": "decision_grade_claims_required_for_apply_or_study",
                "evidence_state": (
                    "decision_grade"
                    if claim_ids and all(claim_id in decision_grade_claims for claim_id in claim_ids)
                    else "insufficient_or_verify_first"
                ),
                "next_action": str(card.get("next_action") or ""),
                "success_criterion": str(card.get("success_criterion") or ""),
            }
        )
    return result


def _canonical_radar_exchange(mvp_radar: Mapping[str, Any]) -> dict[str, Any]:
    matches = [item for item in _as_list(mvp_radar.get("matched_external_evidence")) if isinstance(item, Mapping)]
    context_only = [
        item
        for item in matches
        if item.get("context_only") is True or item.get("supports_gate") is False or str(item.get("radar_role") or "") == "context_only"
    ]
    matched_gate = [
        item
        for item in matches
        if bool(item.get("supports_gate")) and bool(item.get("decision_grade", True)) and item.get("context_only") is not True
    ]
    return {
        "contract_version": RADAR_INTELLIGENCE_CONTRACT_VERSION,
        "status": str(mvp_radar.get("status") or "unknown"),
        "selected_candidate": str(mvp_radar.get("selected_candidate") or ""),
        "recommendation": str(mvp_radar.get("recommendation") or mvp_radar.get("dossier_status") or ""),
        "matched_external_evidence_count": len(matched_gate),
        "context_only_evidence_count": len(context_only),
        "context_only_can_satisfy_gate": False,
        "missing_evidence": [str(item) for item in _as_list(mvp_radar.get("missing_evidence")) if str(item).strip()],
    }


def _source_excerpt(atom: Mapping[str, Any], post: Mapping[str, Any]) -> str:
    quote = str(atom.get("evidence_quote") or "").strip()
    if quote:
        return _compact(quote, 320)
    summary = str(atom.get("summary") or atom.get("claim") or "").strip()
    if summary:
        return _compact(summary, 320)
    return _compact(post.get("content") or "", 320)


def _canonical_polarity(atom: Mapping[str, Any] | None, claim: Mapping[str, Any]) -> str:
    atom = atom or {}
    relation = str(atom.get("relation") or "").strip()
    atom_type = str(atom.get("atom_type") or claim.get("source_type") or "").strip()
    role = str(claim.get("evidence_role") or "").strip()
    if relation == "contradicts" or role == "contradiction":
        return "contradicting"
    if atom_type in {"risk_warning", "opinion_shift"}:
        return "negative"
    return "supporting"


def _canonical_independence_key(claim: Mapping[str, Any], index: int) -> str:
    keys = _as_list(claim.get("source_independence_keys"))
    if 0 <= index - 1 < len(keys):
        return str(keys[index - 1] or "unknown")
    return str(claim.get("source_independence_key") or "unknown")


def _thread_delta_basis(delta: Mapping[str, Any]) -> str:
    if not delta:
        return "unknown"
    if str(delta.get("state") or "") == "insufficient_history":
        return "insufficient_history"
    if _as_list(delta.get("new_evidence_atom_ids")):
        return "new_evidence"
    if str(delta.get("confidence_movement") or "") in {"up", "down_or_cooling"}:
        return "momentum_without_new_evidence"
    return "interpretation_update"


def _safe_int_value(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _implementation_suggestions(confirmed: list[dict], watch: list[dict]) -> list[dict]:
    suggestions: list[dict] = []
    for index, item in enumerate([*confirmed, *watch][:4], start=1):
        project = str(item.get("project") or "unknown-project")
        thread_title = str(item.get("thread_title") or item.get("thread_slug") or "source signal")
        source_atom_ids = []
        for value in item.get("source_atom_ids") or []:
            try:
                atom_id = int(value)
            except (TypeError, ValueError):
                continue
            if atom_id:
                source_atom_ids.append(atom_id)
        source_urls = [str(url) for url in item.get("evidence_urls") or [] if str(url).strip()]
        suggestion_type = "pr" if str(item.get("repo") or "").strip() else "backlog"
        suggestions.append(
            {
                "id": f"project-implementation-{index}",
                "project": project,
                "suggestion_type": suggestion_type,
                "title": f"{project}: проверить {thread_title}",
                "effort": "1-2h discovery + 30m write-up",
                "acceptance_criteria": [
                    "Есть ссылка на source atom и исходный пост.",
                    "Сформулирован минимальный PR/backlog item или явно записано no-go.",
                    "Риск/ограничение перенесены в issue/PR description.",
                ],
                "risk_caveat": (
                    "Не открывать PR, если связь держится только на широких терминах или source atom не подтверждает проектный workflow."
                ),
                "next_step": item.get("next_step") or "Проверить source atoms и решить, нужен ли backlog item.",
                "source_atom_ids": source_atom_ids,
                "source_urls": source_urls,
                "source_policy": "source atoms are required; broad keyword overlap is not enough",
            }
        )
    return suggestions


def _close_but_not_enough_signals(
    *,
    projects: list[dict],
    threads: list[dict],
    linked_pairs: set[tuple[str, str]],
) -> list[dict]:
    signals: list[dict] = []
    for project in projects:
        project_name = str(project.get("name") or project.get("repo") or "unknown-project")
        terms = _project_terms(project)
        broad_terms = [term for term in terms if term in BROAD_PROJECT_TERMS]
        if not broad_terms:
            continue
        for thread in threads:
            thread_slug = str(thread.get("slug") or "")
            if (project_name, thread_slug) in linked_pairs:
                continue
            words = _thread_words(thread)
            hits = [term for term in broad_terms if term in words]
            if not hits:
                continue
            signals.append(
                {
                    "project": project_name,
                    "thread_slug": thread_slug,
                    "thread_title": str(thread.get("title") or thread_slug),
                    "rejected_terms": hits[:5],
                    "reason": "Совпадение только по широким словам; этого недостаточно для проектного лида.",
                    "needed_evidence": "Нужна специфичная сущность, API, repo/workflow phrase или source atom с прямой связью.",
                }
            )
            if len(signals) >= 8:
                return signals
    return signals


def _rejected_broad_overlaps(signals: list[dict]) -> list[dict]:
    rejected: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for signal in signals:
        project = str(signal.get("project") or "")
        for term in signal.get("rejected_terms") or []:
            key = (project, str(term))
            if key in seen:
                continue
            seen.add(key)
            rejected.append(
                {
                    "project": project,
                    "term": str(term),
                    "reason": "broad_overlap_suppressed",
                }
            )
    return rejected[:12]


def _project_terms(project: Mapping[str, Any]) -> list[str]:
    values = project.get("keywords")
    raw_terms: list[str] = []
    if isinstance(values, list):
        raw_terms.extend(str(value) for value in values)
    raw_terms.extend([str(project.get("description") or ""), str(project.get("focus") or "")])
    terms: list[str] = []
    for value in raw_terms:
        for term in re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{1,}\b", value.lower()):
            if term not in terms:
                terms.append(term)
    return terms


def _thread_words(thread: Mapping[str, Any]) -> set[str]:
    parts = [
        str(thread.get("title") or ""),
        str(thread.get("summary") or ""),
        " ".join(str(value) for value in (thread.get("current_claims") or [])),
    ]
    for atom in thread.get("atoms") or []:
        if not isinstance(atom, Mapping):
            continue
        parts.extend(
            [
                str(atom.get("claim") or ""),
                str(atom.get("summary") or ""),
                " ".join(str(value) for value in (atom.get("entities") or [])),
                " ".join(str(value) for value in (atom.get("tools") or [])),
                " ".join(str(value) for value in (atom.get("practices") or [])),
            ]
        )
    return set(re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{1,}\b", " ".join(parts).lower()))


def _expected_thread_delta_count(payload: Mapping[str, Any]) -> int:
    try:
        thread_count = int(payload.get("thread_count") or 0)
    except (TypeError, ValueError):
        thread_count = 0
    if thread_count <= 0:
        return 1
    return min(5, thread_count)


def _split_thread_atoms(
    atoms: list[dict],
    *,
    week_start: datetime | None,
    week_end: datetime | None,
) -> tuple[list[dict], list[dict]]:
    if week_start is None:
        return [], atoms
    previous_atoms: list[dict] = []
    this_week_atoms: list[dict] = []
    for atom in atoms:
        last_seen = _parse_iso(atom.get("last_seen_at"))
        if last_seen is None:
            continue
        if last_seen < week_start:
            previous_atoms.append(atom)
        elif week_end is None or last_seen < week_end:
            this_week_atoms.append(atom)
    return previous_atoms, this_week_atoms


def _previous_thread_state(previous_atoms: list[dict]) -> str:
    if not previous_atoms:
        return "Недостаточно истории до этой недели."
    latest = sorted(previous_atoms, key=lambda item: str(item.get("last_seen_at") or ""), reverse=True)[0]
    return _compact(str(latest.get("claim") or latest.get("summary") or "Предыдущий атом без краткого утверждения."), 260)


def _evidence_delta_item(atom: Mapping[str, Any]) -> dict:
    return {
        "atom_id": int(atom.get("id") or 0),
        "claim": _compact(atom.get("claim") or atom.get("summary") or "", 220),
        "source_urls": [str(url) for url in (atom.get("source_urls") or []) if str(url).strip()][:3],
        "last_seen_at": str(atom.get("last_seen_at") or ""),
        "confidence": _confidence_label(atom.get("confidence")),
    }


def _updated_thread_interpretation(thread: Mapping[str, Any], this_week_atoms: list[dict]) -> str:
    current_claims = [str(value).strip() for value in (thread.get("current_claims") or []) if str(value).strip()]
    if current_claims:
        return _compact(current_claims[0], 280)
    if this_week_atoms:
        return _compact(str(this_week_atoms[-1].get("claim") or this_week_atoms[-1].get("summary") or ""), 280)
    return _compact(thread.get("summary") or "Недостаточно данных для обновленной интерпретации.", 280)


def _confidence_change(previous_atoms: list[dict], this_week_atoms: list[dict], *, insufficient: bool) -> str:
    if insufficient:
        return "insufficient_history"
    previous_avg = _avg_confidence(previous_atoms)
    current_avg = _avg_confidence(this_week_atoms)
    if current_avg >= previous_avg + 0.08:
        return "up"
    if current_avg <= previous_avg - 0.08:
        return "down"
    return "flat_or_uncertain"


def _avg_confidence(atoms: list[dict]) -> float:
    if not atoms:
        return 0.0
    return sum(_float(atom.get("confidence")) for atom in atoms) / max(1, len(atoms))


def _delta_reason(*, insufficient: bool, previous_atoms: list[dict], this_week_atoms: list[dict]) -> str:
    if insufficient:
        return "Тема новая или в контексте нет прошлых атомов: отчет честно помечает недостаток истории."
    if len(this_week_atoms) > len(previous_atoms):
        return "На этой неделе появилось больше связанных атомов, чем было в предыдущем состоянии темы."
    if this_week_atoms:
        return "Новые атомы этой недели уточнили уже существующую тему."
    return "Нет явного нового атома в недельном окне; дельта требует ручной проверки."


def _thread_delta_state(
    thread: Mapping[str, Any],
    previous_atoms: list[dict],
    this_week_atoms: list[dict],
    *,
    insufficient: bool,
) -> str:
    if insufficient:
        return "insufficient_history"
    status = str(thread.get("status") or "active")
    if status in {"stale", "superseded", "hype_only", "production_pattern"}:
        return status
    if any(str(atom.get("relation") or "") == "contradicts" or str(atom.get("atom_type") or "") in {"risk_warning", "opinion_shift"} for atom in this_week_atoms):
        return "contested"
    if len(this_week_atoms) >= 2 or _avg_confidence(this_week_atoms) > _avg_confidence(previous_atoms) + 0.08:
        return "accelerating"
    return "updated"


def _why_this_is_one_thread(thread: Mapping[str, Any], atoms: list[dict]) -> str:
    terms: list[str] = []
    for field in ("key_entities", "source_channels"):
        for value in thread.get(field) or []:
            clean = str(value).strip()
            if clean and clean not in terms:
                terms.append(clean)
    for atom in atoms:
        for field in ("entities", "tools", "models", "practices"):
            for value in atom.get(field) or []:
                clean = str(value).strip()
                if clean and clean not in terms:
                    terms.append(clean)
                if len(terms) >= 5:
                    break
            if len(terms) >= 5:
                break
        if len(terms) >= 5:
            break
    if terms:
        return "Связано общими сущностями/практиками: " + ", ".join(terms[:5]) + "."
    return "Связано группировкой Idea Thread; нужно проверить термины при merge/split audit."


def _merge_split_audit_status(thread: Mapping[str, Any], atoms: list[dict]) -> str:
    atom_count = int(thread.get("atom_count") or len(atoms))
    source_channels = int(thread.get("source_channel_count") or 0)
    key_entities = [str(value).strip() for value in (thread.get("key_entities") or []) if str(value).strip()]
    if atom_count >= 5 and source_channels <= 1:
        return "review_possible_overmerge_single_channel"
    if atom_count >= 4 and len(key_entities) <= 1:
        return "review_possible_split_low_shared_entities"
    return "ok"


def _all_atoms(threads: list[dict]) -> list[dict]:
    atoms: list[dict] = []
    seen: set[int] = set()
    for thread in threads:
        for atom in thread.get("atoms") or []:
            if not isinstance(atom, dict):
                continue
            atom_id = int(atom.get("id") or 0)
            if atom_id in seen:
                continue
            seen.add(atom_id)
            atoms.append(atom)
    return atoms


def _analysis_items(analysis: Mapping[str, Any], key: str) -> list:
    values = analysis.get(key) if isinstance(analysis, Mapping) else []
    return values if isinstance(values, list) else []


def _analysis_text(item: object, *keys: str) -> str:
    if isinstance(item, Mapping):
        for key in keys:
            value = str(item.get(key) or "").strip()
            if value:
                return value
        return " ".join(str(value).strip() for value in item.values() if str(value).strip())
    return str(item or "").strip()


def _atom_score(atom: Mapping[str, Any]) -> tuple[float, float, float, str]:
    return (
        _float(atom.get("practical_utility_score")),
        _float(atom.get("confidence")),
        _float(atom.get("novelty_score")),
        str(atom.get("last_seen_at") or ""),
    )


def _top_claim_atom_ids(claim_cards: list[dict]) -> list[int]:
    ids: list[int] = []
    for card in claim_cards[:3]:
        if not card.get("decision_eligible"):
            continue
        for value in card.get("evidence_atom_ids") or []:
            try:
                atom_id = int(value)
            except (TypeError, ValueError):
                continue
            if atom_id and atom_id not in ids:
                ids.append(atom_id)
    return ids


def _confidence_label(value: object) -> str:
    score = _float(value)
    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def _confidence_movement(thread: Mapping[str, Any]) -> str:
    momentum_7d = _float(thread.get("momentum_7d"))
    momentum_30d = _float(thread.get("momentum_30d"))
    if momentum_7d > momentum_30d * 1.2 and momentum_7d > 0:
        return "up"
    if momentum_30d > momentum_7d * 1.4 and momentum_30d > 0:
        return "down_or_cooling"
    return "flat_or_uncertain"


def _claim_caveat(
    *,
    source_count: int,
    independent_sources: int,
    quote_verified: bool,
    verification_status: str,
) -> str:
    if not quote_verified:
        if verification_status == "missing_source_text":
            return "Слабая карточка: ссылка есть, но локальный текст источника недоступен для сверки цитаты."
        if verification_status == "quote_not_found":
            return "Слабая карточка: цитата не найдена в локальном тексте источника, нужна ручная проверка."
        if verification_status == "missing_quote":
            return "Слабая карточка: нет проверяемой цитаты, не использовать как установленный факт."
        return "Слабая карточка: доказательство не прошло автоматическую проверку."
    if independent_sources >= 2:
        return "Цитата найдена в локальном источнике; есть несколько независимых ключей, но контекст все равно нужно проверить."
    if source_count >= 1:
        return "Цитата проверена, но источник один: не считать это установленным трендом без независимого подтверждения."
    return "Источник не найден: утверждение нельзя использовать как решение без проверки."


def _verify_evidence_quote(quote: str, source_posts: list[Mapping[str, Any]]) -> dict:
    clean_quote = str(quote or "").strip()
    if not clean_quote:
        return {
            "quote_verified": False,
            "verification_status": "missing_quote",
            "source_post_ids": [],
        }
    if not source_posts:
        return {
            "quote_verified": False,
            "verification_status": "missing_source_text",
            "source_post_ids": [],
        }
    normalized_quote = _normalize_quote_text(clean_quote)
    verified_ids: list[int] = []
    for post in source_posts:
        content = str(post.get("content") or "")
        if normalized_quote and normalized_quote in _normalize_quote_text(content):
            try:
                post_id = int(post.get("post_id") or 0)
            except (TypeError, ValueError):
                post_id = 0
            if post_id:
                verified_ids.append(post_id)
    if verified_ids:
        return {
            "quote_verified": True,
            "verification_status": "verified",
            "source_post_ids": verified_ids,
        }
    return {
        "quote_verified": False,
        "verification_status": "quote_not_found",
        "source_post_ids": [],
    }


def _normalize_quote_text(value: str) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"[^0-9a-zа-яё]+", " ", text)
    return " ".join(text.split())


def _evidence_role(atom_type: str) -> str:
    mapping = {
        "tool_release": "primary_announcement",
        "model_update": "primary_announcement",
        "pricing_or_limit_change": "access_or_pricing_notice",
        "regulatory_or_access_change": "access_or_pricing_notice",
        "benchmark_claim": "benchmark_claim",
        "research_claim": "research_claim",
        "risk_warning": "risk_warning",
        "case_study": "case_study",
        "tutorial_resource": "tutorial",
        "market_signal": "market_signal",
        "opinion_shift": "commentary",
        "workflow_pattern": "practice_report",
        "engineering_practice": "practice_report",
    }
    return mapping.get(atom_type, "commentary")


def _evidence_tier(
    *,
    atom_type: str,
    source_count: int,
    independent_sources: int,
    quote_verified: bool,
) -> str:
    if source_count <= 0:
        return "unsupported"
    if not quote_verified:
        return "weak_single_source" if source_count == 1 else "weak_unverified"
    if independent_sources >= 2:
        return "verified_multi_source"
    if atom_type in {"tool_release", "model_update", "pricing_or_limit_change", "regulatory_or_access_change"}:
        return "verified_primary"
    return "verified_single_source"


def _claim_scope(atom_type: str) -> str:
    mapping = {
        "tool_release": "tool",
        "model_update": "model",
        "workflow_pattern": "workflow",
        "engineering_practice": "practice",
        "benchmark_claim": "benchmark",
        "market_signal": "market",
        "risk_warning": "risk",
        "case_study": "case",
        "tutorial_resource": "tutorial",
        "opinion_shift": "opinion",
        "research_claim": "research",
        "pricing_or_limit_change": "pricing_or_access",
        "regulatory_or_access_change": "regulatory_or_access",
    }
    return mapping.get(atom_type, "general")


def _time_horizon(atom_type: str) -> str:
    if atom_type in {"pricing_or_limit_change", "regulatory_or_access_change", "tool_release", "model_update"}:
        return "short"
    if atom_type in {"benchmark_claim", "market_signal", "opinion_shift"}:
        return "medium"
    return "medium_to_long"


def _verification_action(
    *,
    quote_verified: bool,
    independent_sources: int,
    verification_status: str,
) -> str:
    if not quote_verified:
        if verification_status == "missing_source_text":
            return "Загрузить локальный текст source post или открыть ссылку и вручную сверить цитату."
        if verification_status == "quote_not_found":
            return "Открыть source post, найти точную цитату или понизить утверждение до noise."
        return "Добавить проверяемую цитату и ссылку на источник."
    if independent_sources < 2:
        return "Найти независимое подтверждение до сильной формулировки тренда."
    return "Проверить контекст цитаты и отслеживать противоречащие источники."


def _expiry_hint(atom_type: str) -> str:
    if atom_type in {"pricing_or_limit_change", "regulatory_or_access_change"}:
        return "Проверить заново перед использованием: условия могут быстро измениться."
    if atom_type in {"model_update", "tool_release", "benchmark_claim"}:
        return "Считать свежим только до следующего релиза или независимого benchmark."
    return "Пересмотреть через 30-90 дней или при появлении противоречащих источников."


def _infer_effort(title: str) -> str:
    text = title.lower()
    if any(token in text for token in ("audit", "провер", "review")):
        return "30 мин"
    if any(token in text for token in ("prototype", "benchmark", "эксперимент", "deploy")):
        return "60 мин"
    return "30 мин"


def _infer_scope(title: str, body: str) -> str:
    text = f"{title} {body}".lower()
    if any(token in text for token in ("read", "study", "изуч", "прочит")):
        return "reading"
    if any(token in text for token in ("benchmark", "prototype", "эксперимент", "test harness")):
        return "experiment"
    if any(token in text for token in ("cost", "api", "infra", "serving", "deploy")):
        return "infra"
    if any(token in text for token in ("project", "repo", "hiring", "rubric")):
        return "project"
    return "skill"


def _source_channel(url: str) -> str:
    parsed = urlparse(str(url or ""))
    if parsed.netloc.endswith("t.me"):
        parts = [part for part in parsed.path.split("/") if part]
        if parts:
            return parts[0]
    return parsed.netloc or "unknown"


def _source_independence_keys(urls: list[str], source_posts: list[Mapping[str, Any]]) -> list[str]:
    keys: list[str] = []
    for post in source_posts:
        channel = str(post.get("channel_username") or "").strip().lstrip("@")
        if channel:
            key = f"telegram:{channel}"
            if key not in keys:
                keys.append(key)
    for url in urls:
        channel = _source_channel(url)
        key = f"telegram:{channel}" if channel and "." not in channel else f"domain:{channel or 'unknown'}"
        if key not in keys:
            keys.append(key)
    return keys


def _int_values(values: object) -> list[int]:
    result: list[int] = []
    for value in values or []:
        try:
            clean = int(value)
        except (TypeError, ValueError):
            continue
        if clean and clean not in result:
            result.append(clean)
    return result


def _claim_cards_by_atom_id(cards: list) -> dict[int, Mapping[str, Any]]:
    result: dict[int, Mapping[str, Any]] = {}
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        for atom_id in _int_values(card.get("evidence_atom_ids")):
            result[atom_id] = card
    return result


def _claim_card_is_explicitly_weak(card: Mapping[str, Any]) -> bool:
    tier = str(card.get("evidence_tier") or "")
    caveat = str(card.get("caveat") or "").casefold()
    decision_eligible = bool(card.get("decision_eligible"))
    return (
        not decision_eligible
        and (tier.startswith("weak") or tier == "unsupported")
        and ("слаб" in caveat or "одноисточник" in caveat or "unverified" in caveat)
    )


def _parse_iso(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _compact(value: object, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)].rstrip()}..."


def _float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _unique(values) -> list:
    result = []
    seen: set[str] = set()
    for value in values:
        if value in (None, ""):
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _slug(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9а-яё]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:80] or "item"


def _dedupe_by_id(values: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for value in values:
        value_id = str(value.get("id") or "").strip()
        if not value_id or value_id in seen:
            continue
        seen.add(value_id)
        result.append(value)
    return result


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _require_text(
    payload: Mapping[str, Any],
    fields: tuple[str, ...],
    findings: list[ReportQualityFinding],
    prefix: str,
) -> None:
    for field in fields:
        if not str(payload.get(field) or "").strip():
            findings.append(_critical(f"Required report contract field is missing: {field}", f"{prefix}.{field}"))


def _require_feedback_ref(
    payload: Mapping[str, Any],
    feedback_ids: set[str],
    findings: list[ReportQualityFinding],
    prefix: str,
) -> None:
    target_id = str(payload.get("feedback_target_id") or "").strip()
    if not target_id:
        findings.append(_critical("Card must reference a feedback target", f"{prefix}.feedback_target_id"))
    elif target_id not in feedback_ids:
        findings.append(_critical("Card references an unknown feedback target", f"{prefix}.feedback_target_id"))


def _critical(message: str, line_hint: str) -> ReportQualityFinding:
    return ReportQualityFinding(
        severity=SEVERITY_CRITICAL,
        artifact_type="ai_intelligence_report_contract",
        message=message,
        line_hint=line_hint,
    )
