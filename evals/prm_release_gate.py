"""Deterministic PRM-18 release and dogfood gate.

The gate aggregates already-produced deterministic receipts. It does not run
live Telegram ingestion, retrieval jobs, LLM judges, browser automation, Radar,
or dogfood workflows.
"""

from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


PRM_RELEASE_GATE_SCHEMA_VERSION = "prm_release_gate.v1"

SCENARIO_STATUSES = {"passed", "failed", "blocked"}
EVALUATION_STATUSES = {"passed", "failed", "blocked", "not_run"}
REVIEW_STATUSES = {"resolved", "accepted_by_human", "open", "blocked"}

EVALUATION_AREAS = (
    "data",
    "retrieval",
    "generation",
    "tool",
    "agent",
    "privacy",
    "cost",
    "ui",
    "end_to_end",
)

STOP_SHIP_CRITERIA = (
    "private_data_leakage",
    "unsupported_claims",
    "retrieval_metric_failure",
    "unsafe_writes",
    "cost_budget_breach",
)

REQUIRED_PRIVACY_FLAGS = (
    "raw_telegram_text_egress",
    "external_skill_used",
    "provider_payload_logged",
    "production_db_mutation",
    "generated_private_report_committed",
)

FINAL_ACCEPTANCE_SCENARIOS = (
    ("e2e_01_known_reacted_post", "Find a known reacted post."),
    ("e2e_02_semantic_topic_multi_month", "Answer a semantic topic question over multiple months."),
    ("e2e_03_compare_cases", "Find and compare several cases."),
    ("e2e_04_project_application", "Apply archive evidence to one active project."),
    ("e2e_05_freshness_boundary", "Answer a freshness/news question with clear date boundaries."),
    ("e2e_06_external_verification", "Trigger external verification without blending evidence classes."),
    ("e2e_07_no_answer_for_gap", "Return insufficient evidence for a corpus gap."),
    ("e2e_08_save_knowledge_note", "Save a Knowledge Note after confirmation."),
    ("e2e_09_create_watch_topic", "Create a Watch Topic after confirmation."),
    ("e2e_10_weekly_brief_v3", "Show a useful secondary Weekly Brief based on actual usage."),
    (
        "e2e_11_knowledge_library_topic",
        "Open a Knowledge Library topic page with changes, memory, contradictions, questions, and sources.",
    ),
)

FORBIDDEN_RECEIPT_KEYS = {
    "raw_post_text",
    "raw_text",
    "telegram_text",
    "message_text",
    "content",
    "provider_payload",
    "prompt",
    "completion",
    "llm_response",
}


class PRMReleaseGateValidationError(ValueError):
    """Raised when a PRM-18 release-gate receipt is invalid or unsafe."""


def build_prm_release_gate_receipt(
    *,
    scenarios: Sequence[Mapping[str, Any]] | None = None,
    evaluations: Mapping[str, Any] | None = None,
    reviews: Sequence[Mapping[str, Any]] | None = None,
    stop_ship: Mapping[str, Any] | None = None,
    human_approval_ref: str | None = None,
    generated_at: str | None = None,
    project_commit: str | None = None,
) -> dict[str, object]:
    scenario_rows = _build_scenarios(scenarios)
    evaluation_rows = _build_evaluations(evaluations)
    review_rows = _build_reviews(reviews)
    stop_ship_rows = _build_stop_ship(stop_ship)
    blockers = _dogfood_blockers(
        scenarios=scenario_rows,
        evaluations=evaluation_rows,
        reviews=review_rows,
        stop_ship=stop_ship_rows,
        human_approval_ref=human_approval_ref,
    )
    receipt = {
        "schema_version": PRM_RELEASE_GATE_SCHEMA_VERSION,
        "artifact_type": "prm_release_gate",
        "generated_at": generated_at or _now_iso(),
        "project_commit": _clean_text(project_commit),
        "acceptance_scenarios": scenario_rows,
        "evaluations": evaluation_rows,
        "review_findings": review_rows,
        "stop_ship": stop_ship_rows,
        "dogfood_gate": {
            "status": "eligible" if not blockers else "blocked",
            "blocking_reasons": blockers,
            "human_approval_ref": _clean_text(human_approval_ref),
            "dogfood_started": False,
            "release_claimed": False,
        },
        "privacy": {
            "raw_telegram_text_egress": False,
            "external_skill_used": False,
            "provider_payload_logged": False,
            "production_db_mutation": False,
            "generated_private_report_committed": False,
        },
        "verification_commands": [
            "PYTHONPATH=src python3 -m pytest tests/test_prm_release_gate.py -q",
            "python3 tools/test_tiers.py focused-prm",
            "python3 tools/test_tiers.py fast-contract",
            "PYTHONPATH=src python3 -m pytest tests/ -q",
            "python3 tools/playbook_validate.py --root . --check tasks --check placeholders --check readiness --check delivery --check references",
            "git diff --check",
        ],
    }
    return validate_prm_release_gate_receipt(receipt)


def validate_prm_release_gate_receipt(receipt: Mapping[str, Any]) -> dict[str, object]:
    errors: list[str] = []
    if receipt.get("schema_version") != PRM_RELEASE_GATE_SCHEMA_VERSION:
        errors.append("schema_version is invalid")
    if receipt.get("artifact_type") != "prm_release_gate":
        errors.append("artifact_type must be prm_release_gate")

    scenarios = receipt.get("acceptance_scenarios")
    if not isinstance(scenarios, list):
        errors.append("acceptance_scenarios must be a list")
    else:
        expected = {scenario_id for scenario_id, _title in FINAL_ACCEPTANCE_SCENARIOS}
        observed_ids = [item.get("id") for item in scenarios if isinstance(item, Mapping)]
        observed = set(observed_ids)
        missing = sorted(expected - observed)
        if missing:
            errors.append("missing acceptance scenarios: " + ", ".join(missing))
        unknown = sorted(observed - expected)
        if unknown:
            errors.append("unknown acceptance scenarios: " + ", ".join(str(value) for value in unknown))
        duplicates = sorted({scenario_id for scenario_id in observed_ids if observed_ids.count(scenario_id) > 1})
        if duplicates:
            errors.append("duplicate acceptance scenarios: " + ", ".join(str(value) for value in duplicates))
        for index, scenario in enumerate(scenarios):
            if not isinstance(scenario, Mapping):
                errors.append(f"acceptance_scenarios[{index}] must be an object")
                continue
            if scenario.get("status") not in SCENARIO_STATUSES:
                errors.append(f"{scenario.get('id') or index}.status is invalid")
            if not _text_list(scenario.get("evidence_refs")):
                errors.append(f"{scenario.get('id') or index}.evidence_refs must not be empty")

    evaluations = receipt.get("evaluations")
    if not isinstance(evaluations, Mapping):
        errors.append("evaluations must be an object")
    else:
        missing_areas = [area for area in EVALUATION_AREAS if area not in evaluations]
        if missing_areas:
            errors.append("missing evaluations: " + ", ".join(missing_areas))
        unknown_areas = sorted(set(evaluations) - set(EVALUATION_AREAS))
        if unknown_areas:
            errors.append("unknown evaluations: " + ", ".join(unknown_areas))
        for area, value in evaluations.items():
            if not isinstance(value, Mapping):
                errors.append(f"evaluations.{area} must be an object")
                continue
            if value.get("status") not in EVALUATION_STATUSES:
                errors.append(f"evaluations.{area}.status is invalid")
            if not _text_list(value.get("evidence_refs")):
                errors.append(f"evaluations.{area}.evidence_refs must not be empty")

    reviews = receipt.get("review_findings")
    if not isinstance(reviews, list):
        errors.append("review_findings must be a list")
    else:
        for index, finding in enumerate(reviews):
            if not isinstance(finding, Mapping):
                errors.append(f"review_findings[{index}] must be an object")
                continue
            if finding.get("status") not in REVIEW_STATUSES:
                errors.append(f"review_findings[{index}].status is invalid")
            if not _text_list(finding.get("evidence_refs")):
                errors.append(f"review_findings[{index}].evidence_refs must not be empty")

    stop_ship = receipt.get("stop_ship")
    if not isinstance(stop_ship, Mapping):
        errors.append("stop_ship must be an object")
    else:
        missing_stop_ship = [key for key in STOP_SHIP_CRITERIA if key not in stop_ship]
        if missing_stop_ship:
            errors.append("missing stop_ship criteria: " + ", ".join(missing_stop_ship))
        unknown_stop_ship = sorted(set(stop_ship) - set(STOP_SHIP_CRITERIA))
        if unknown_stop_ship:
            errors.append("unknown stop_ship criteria: " + ", ".join(unknown_stop_ship))
        for key, value in stop_ship.items():
            if not isinstance(value, Mapping):
                errors.append(f"stop_ship.{key} must be an object")
                continue
            if not isinstance(value.get("triggered"), bool):
                errors.append(f"stop_ship.{key}.triggered must be boolean")
            if not _text_list(value.get("evidence_refs")):
                errors.append(f"stop_ship.{key}.evidence_refs must not be empty")

    gate = receipt.get("dogfood_gate")
    if not isinstance(gate, Mapping):
        errors.append("dogfood_gate must be an object")
    else:
        if gate.get("status") not in {"blocked", "eligible"}:
            errors.append("dogfood_gate.status is invalid")
        if gate.get("dogfood_started") is not False:
            errors.append("dogfood_gate.dogfood_started must be false for PRM-18")
        if gate.get("release_claimed") is not False:
            errors.append("dogfood_gate.release_claimed must be false for PRM-18")
        if gate.get("status") == "eligible" and not _clean_text(gate.get("human_approval_ref")):
            errors.append("dogfood_gate eligible requires human_approval_ref")
        if gate.get("status") == "blocked" and not _text_list(gate.get("blocking_reasons")):
            errors.append("dogfood_gate blocked requires blocking_reasons")

    privacy = receipt.get("privacy")
    if not isinstance(privacy, Mapping):
        errors.append("privacy must be an object")
    else:
        missing_privacy = [field for field in REQUIRED_PRIVACY_FLAGS if field not in privacy]
        if missing_privacy:
            errors.append("missing privacy flags: " + ", ".join(missing_privacy))
        for field, value in privacy.items():
            if field in REQUIRED_PRIVACY_FLAGS and value is not False:
                errors.append(f"privacy.{field} must be false")

    forbidden_paths = _collect_forbidden_receipt_paths(receipt)
    if forbidden_paths:
        errors.append("forbidden raw payload keys in release receipt: " + ", ".join(sorted(forbidden_paths)))
    if errors:
        raise PRMReleaseGateValidationError("; ".join(errors))
    return copy.deepcopy(dict(receipt))


def summarize_prm_release_gate(receipt: Mapping[str, Any]) -> str:
    value = validate_prm_release_gate_receipt(receipt)
    gate = value["dogfood_gate"]
    scenarios = value["acceptance_scenarios"]
    passed = sum(1 for scenario in scenarios if scenario["status"] == "passed")
    failed = sum(1 for scenario in scenarios if scenario["status"] == "failed")
    blocked = sum(1 for scenario in scenarios if scenario["status"] == "blocked")
    reasons = ", ".join(gate["blocking_reasons"]) if gate["blocking_reasons"] else "none"
    return (
        f"PRM release gate: dogfood={gate['status']}; "
        f"scenarios passed={passed} failed={failed} blocked={blocked}; "
        f"blocking_reasons={reasons}."
    )


def _build_scenarios(scenarios: Sequence[Mapping[str, Any]] | None) -> list[dict[str, object]]:
    by_id = {
        _clean_text(item.get("id")): item
        for item in scenarios or []
        if isinstance(item, Mapping) and _clean_text(item.get("id"))
    }
    result: list[dict[str, object]] = []
    for scenario_id, title in FINAL_ACCEPTANCE_SCENARIOS:
        raw = by_id.get(scenario_id, {})
        status = _status(raw.get("status"), allowed=SCENARIO_STATUSES, default="blocked")
        evidence_refs = _text_list(raw.get("evidence_refs"))
        if not evidence_refs:
            evidence_refs = ["docs/final_acceptance_plan.md"]
        result.append(
            {
                "id": scenario_id,
                "title": title,
                "status": status,
                "evidence_refs": evidence_refs,
                "notes": _clean_text(raw.get("notes")),
            }
        )
    return result


def _build_evaluations(evaluations: Mapping[str, Any] | None) -> dict[str, dict[str, object]]:
    raw = evaluations if isinstance(evaluations, Mapping) else {}
    result: dict[str, dict[str, object]] = {}
    for area in EVALUATION_AREAS:
        value = raw.get(area) if isinstance(raw.get(area), Mapping) else {}
        result[area] = {
            "status": _status(value.get("status"), allowed=EVALUATION_STATUSES, default="blocked"),
            "evidence_refs": _text_list(value.get("evidence_refs")) or _default_evaluation_refs(area),
            "notes": _clean_text(value.get("notes")),
        }
    return result


def _build_reviews(reviews: Sequence[Mapping[str, Any]] | None) -> list[dict[str, object]]:
    rows = []
    for index, review in enumerate(reviews or [], start=1):
        if not isinstance(review, Mapping):
            continue
        rows.append(
            {
                "id": _clean_text(review.get("id")) or f"review-{index}",
                "area": _clean_text(review.get("area")) or "review",
                "status": _status(review.get("status"), allowed=REVIEW_STATUSES, default="open"),
                "evidence_refs": _text_list(review.get("evidence_refs")) or ["docs/REVIEW_POLICY.md"],
                "notes": _clean_text(review.get("notes")),
            }
        )
    if not rows:
        rows.append(
            {
                "id": "review-gate",
                "area": "test_critic_privacy_review",
                "status": "blocked",
                "evidence_refs": ["docs/REVIEW_POLICY.md"],
                "notes": "No review acceptance receipt was supplied.",
            }
        )
    return rows


def _build_stop_ship(stop_ship: Mapping[str, Any] | None) -> dict[str, dict[str, object]]:
    raw = stop_ship if isinstance(stop_ship, Mapping) else {}
    result: dict[str, dict[str, object]] = {}
    for criterion in STOP_SHIP_CRITERIA:
        value = raw.get(criterion) if isinstance(raw.get(criterion), Mapping) else {}
        result[criterion] = {
            "triggered": bool(value.get("triggered", True)),
            "evidence_refs": _text_list(value.get("evidence_refs")) or _default_stop_ship_refs(criterion),
            "notes": _clean_text(value.get("notes")),
        }
    return result


def _dogfood_blockers(
    *,
    scenarios: Sequence[Mapping[str, Any]],
    evaluations: Mapping[str, Mapping[str, Any]],
    reviews: Sequence[Mapping[str, Any]],
    stop_ship: Mapping[str, Mapping[str, Any]],
    human_approval_ref: str | None,
) -> list[str]:
    blockers: list[str] = []
    for scenario in scenarios:
        if scenario.get("status") != "passed":
            blockers.append(f"scenario_not_passed:{scenario['id']}")
    for area, evaluation in evaluations.items():
        if evaluation.get("status") != "passed":
            blockers.append(f"evaluation_not_passed:{area}")
    for finding in reviews:
        if finding.get("status") not in {"resolved", "accepted_by_human"}:
            blockers.append(f"review_unresolved:{finding['id']}")
    for criterion, value in stop_ship.items():
        if value.get("triggered"):
            blockers.append(f"stop_ship:{criterion}")
    if not _clean_text(human_approval_ref):
        blockers.append("missing_human_dogfood_start_approval")
    return _unique_texts(blockers)


def _default_evaluation_refs(area: str) -> list[str]:
    return {
        "data": ["docs/RAG_DATA_READINESS.md", "docs/final_acceptance_plan.md"],
        "retrieval": ["docs/retrieval_eval.md", "evals/retrieval/README.md"],
        "generation": ["docs/generation_eval.md", "docs/final_acceptance_plan.md"],
        "tool": ["docs/tool_eval.md", "docs/AGENT_HARNESS_DESIGN.md"],
        "agent": ["docs/agent_eval.md", "docs/AGENT_HARNESS_DESIGN.md"],
        "privacy": ["docs/PRIVACY_THREAT_MODEL.md"],
        "cost": ["docs/COST_BUDGET.md"],
        "ui": ["docs/report_format.md", "tests/test_knowledge_library.py", "tests/test_weekly_brief_v3.py"],
        "end_to_end": ["docs/final_acceptance_plan.md"],
    }[area]


def _default_stop_ship_refs(criterion: str) -> list[str]:
    return {
        "private_data_leakage": ["docs/PRIVACY_THREAT_MODEL.md"],
        "unsupported_claims": ["docs/generation_eval.md", "docs/final_acceptance_plan.md"],
        "retrieval_metric_failure": ["docs/retrieval_eval.md", "evals/retrieval/README.md"],
        "unsafe_writes": ["docs/PRIVACY_THREAT_MODEL.md", "docs/AGENT_HARNESS_DESIGN.md"],
        "cost_budget_breach": ["docs/COST_BUDGET.md"],
    }[criterion]


def _status(raw: object, *, allowed: set[str], default: str) -> str:
    value = _clean_text(raw)
    return value if value in allowed else default


def _collect_forbidden_receipt_paths(value: object, *, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for raw_key, raw_value in value.items():
            key = _clean_text(raw_key)
            path = f"{prefix}.{key}" if prefix else key
            if key.lower() in FORBIDDEN_RECEIPT_KEYS or key.lower().endswith("_raw_text"):
                paths.append(path)
                continue
            paths.extend(_collect_forbidden_receipt_paths(raw_value, prefix=path))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            paths.extend(_collect_forbidden_receipt_paths(item, prefix=f"{prefix}[{index}]"))
    return paths


def _text_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        clean = _clean_text(raw)
        return [clean] if clean else []
    if isinstance(raw, (list, tuple, set)):
        return _unique_texts(_clean_text(item) for item in raw if _clean_text(item))
    clean = _clean_text(raw)
    return [clean] if clean else []


def _unique_texts(values: Sequence[str] | Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
