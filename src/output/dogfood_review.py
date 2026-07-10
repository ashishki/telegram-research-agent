from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


DOGFOOD_METRIC_KEYS = {
    "time_to_understand_week_minutes",
    "sections_read",
    "read_items_completed",
    "try_items_completed",
    "experiments_completed",
    "project_actions_created",
    "feedback_events_count",
    "wrong_priority_count",
    "not_interested_count",
    "applied_to_project_count",
    "mvp_build_count",
    "mvp_focused_experiment_count",
    "mvp_investigate_count",
    "mvp_reject_count",
    "decisions_changed_by_system",
    "user_value_score_1_to_5",
    "friction_score_1_to_5",
}

DOGFOOD_NOTE_KEYS = {
    "best_explanation",
    "weakest_section",
    "promote_source_or_thread",
    "demote_source_or_thread",
    "simplify_next_week",
}

WEEKLY_INTELLIGENCE_SCORECARD_VERSION = "weekly-intelligence-scorecard.v1"
SCORECARD_DIMENSIONS = (
    "correctness",
    "relevance",
    "decisions_actions",
    "learning",
    "ux",
    "radar",
    "operations",
)
UNKNOWN_METRIC_STATES = {"unknown", "not_measured"}


def build_weekly_dogfood_review(
    *,
    week_label: str,
    metrics: Mapping[str, Any],
    notes: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict:
    clean_week = _required_text(week_label, "week_label")
    normalized = normalize_dogfood_metrics(metrics)
    normalized_notes = {
        key: _optional_text((notes or {}).get(key))
        for key in sorted(DOGFOOD_NOTE_KEYS)
        if _optional_text((notes or {}).get(key))
    }
    return {
        "status": "ok",
        "week_label": clean_week,
        "generated_at": generated_at or _now_iso(),
        "metrics": normalized,
        "notes": normalized_notes,
        "review": {
            "real_actions_completed": _real_actions_count(normalized),
            "feedback_signal_count": _feedback_signal_count(normalized),
            "decisions_changed_count": len(normalized["decisions_changed_by_system"]),
            "mvp_status_counts": {
                "build": normalized["mvp_build_count"],
                "focused_experiment": normalized["mvp_focused_experiment_count"],
                "investigate": normalized["mvp_investigate_count"],
                "reject": normalized["mvp_reject_count"],
            },
            "requires_simplification": _requires_simplification(normalized),
        },
        "privacy": "private_operator_artifact_do_not_commit_generated_outputs",
    }


def normalize_dogfood_metrics(metrics: Mapping[str, Any] | None) -> dict:
    raw = dict(metrics or {})
    return {
        "time_to_understand_week_minutes": _optional_int(raw.get("time_to_understand_week_minutes")),
        "sections_read": _string_list(raw.get("sections_read")),
        "read_items_completed": _nonnegative_int(raw.get("read_items_completed")),
        "try_items_completed": _nonnegative_int(raw.get("try_items_completed")),
        "experiments_completed": _nonnegative_int(raw.get("experiments_completed")),
        "project_actions_created": _nonnegative_int(raw.get("project_actions_created")),
        "feedback_events_count": _nonnegative_int(raw.get("feedback_events_count")),
        "wrong_priority_count": _nonnegative_int(raw.get("wrong_priority_count")),
        "not_interested_count": _nonnegative_int(raw.get("not_interested_count")),
        "applied_to_project_count": _nonnegative_int(raw.get("applied_to_project_count")),
        "mvp_build_count": _nonnegative_int(raw.get("mvp_build_count")),
        "mvp_focused_experiment_count": _nonnegative_int(raw.get("mvp_focused_experiment_count")),
        "mvp_investigate_count": _nonnegative_int(raw.get("mvp_investigate_count")),
        "mvp_reject_count": _nonnegative_int(raw.get("mvp_reject_count")),
        "decisions_changed_by_system": _string_list(raw.get("decisions_changed_by_system")),
        "user_value_score_1_to_5": _score_or_none(raw.get("user_value_score_1_to_5")),
        "friction_score_1_to_5": _score_or_none(raw.get("friction_score_1_to_5")),
    }


def write_weekly_dogfood_review(review: Mapping[str, Any], output_dir: str | Path) -> dict:
    week = _required_text(review.get("week_label"), "week_label")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / f"dogfood-review-{week}.json"
    markdown_path = root / f"dogfood-review-{week}.md"
    json_path.write_text(json.dumps(dict(review), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(format_weekly_dogfood_markdown(review), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def build_weekly_intelligence_scorecard(
    *,
    week_label: str,
    weekly_brief: Mapping[str, Any] | None = None,
    knowledge_atlas: Mapping[str, Any] | None = None,
    dogfood_review: Mapping[str, Any] | None = None,
    observations: Mapping[str, Any] | None = None,
    source_artifacts: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict:
    clean_week = _required_text(week_label, "week_label")
    brief = weekly_brief if isinstance(weekly_brief, Mapping) else {}
    atlas = knowledge_atlas if isinstance(knowledge_atlas, Mapping) else {}
    review = dogfood_review if isinstance(dogfood_review, Mapping) else {}
    observed = observations if isinstance(observations, Mapping) else {}
    false_confidence_incidents = _false_confidence_incidents(observed)
    dimensions = _scorecard_dimensions(
        weekly_brief=brief,
        knowledge_atlas=atlas,
        dogfood_review=review,
        observations=observed,
        false_confidence_incidents=false_confidence_incidents,
    )
    unknown_metrics = _unknown_metric_refs(dimensions)
    quality_finding_count = _quality_finding_count(brief) + _quality_finding_count(atlas)
    return {
        "schema_version": WEEKLY_INTELLIGENCE_SCORECARD_VERSION,
        "artifact_type": "weekly_intelligence_scorecard",
        "week_label": clean_week,
        "generated_at": generated_at or _now_iso(),
        "source_artifacts": _source_artifacts(source_artifacts, brief, atlas, review),
        "dimensions": dimensions,
        "unknown_metrics": unknown_metrics,
        "false_confidence_incidents": false_confidence_incidents,
        "summary": {
            "dimension_count": len(dimensions),
            "measured_metric_count": _measured_metric_count(dimensions),
            "unknown_metric_count": len(unknown_metrics),
            "quality_finding_count": quality_finding_count,
            "false_confidence_incident_count": len(false_confidence_incidents),
            "scorecard_status": "needs_baseline",
        },
        "privacy": "sanitized_fixture_or_private_operator_artifact",
    }


def build_weekly_intelligence_scorecard_from_files(
    *,
    week_label: str,
    weekly_brief_json_path: str | Path,
    knowledge_atlas_json_path: str | Path | None = None,
    dogfood_review_json_path: str | Path | None = None,
    observations_json_path: str | Path | None = None,
    generated_at: str | None = None,
) -> dict:
    brief_path = Path(weekly_brief_json_path)
    atlas_path = Path(knowledge_atlas_json_path) if knowledge_atlas_json_path else None
    review_path = Path(dogfood_review_json_path) if dogfood_review_json_path else None
    observations_path = Path(observations_json_path) if observations_json_path else None
    brief = _read_json_mapping(brief_path)
    atlas = _read_json_mapping(atlas_path) if atlas_path else {}
    review = _read_json_mapping(review_path) if review_path else {}
    observations = _read_json_mapping(observations_path) if observations_path else {}
    return build_weekly_intelligence_scorecard(
        week_label=week_label,
        weekly_brief=brief,
        knowledge_atlas=atlas,
        dogfood_review=review,
        observations=observations,
        source_artifacts={
            "weekly_brief_json_path": str(brief_path),
            "knowledge_atlas_json_path": str(atlas_path) if atlas_path else None,
            "dogfood_review_json_path": str(review_path) if review_path else None,
            "observations_json_path": str(observations_path) if observations_path else None,
        },
        generated_at=generated_at,
    )


def validate_weekly_intelligence_scorecard(scorecard: Mapping[str, Any] | None) -> list[str]:
    payload = scorecard if isinstance(scorecard, Mapping) else {}
    findings: list[str] = []
    if payload.get("schema_version") != WEEKLY_INTELLIGENCE_SCORECARD_VERSION:
        findings.append("unsupported_scorecard_schema_version")
    dimensions = payload.get("dimensions") if isinstance(payload.get("dimensions"), Mapping) else {}
    for dimension in SCORECARD_DIMENSIONS:
        if dimension not in dimensions:
            findings.append(f"missing_dimension:{dimension}")
            continue
        metrics = dimensions[dimension].get("metrics") if isinstance(dimensions[dimension], Mapping) else {}
        if not isinstance(metrics, Mapping) or not metrics:
            findings.append(f"missing_metrics:{dimension}")
    for ref in payload.get("unknown_metrics") or []:
        if not isinstance(ref, str) or "." not in ref:
            findings.append("invalid_unknown_metric_ref")
    for index, incident in enumerate(payload.get("false_confidence_incidents") or [], start=1):
        if not isinstance(incident, Mapping):
            findings.append(f"invalid_false_confidence_incident:{index}")
            continue
        if not _optional_text(incident.get("description")):
            findings.append(f"missing_false_confidence_description:{index}")
    return findings


def write_weekly_intelligence_scorecard(scorecard: Mapping[str, Any], output_dir: str | Path) -> dict:
    week = _required_text(scorecard.get("week_label"), "week_label")
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / f"weekly-intelligence-scorecard-{week}.json"
    markdown_path = root / f"weekly-intelligence-scorecard-{week}.md"
    json_path.write_text(json.dumps(dict(scorecard), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(format_weekly_intelligence_scorecard_markdown(scorecard), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def format_weekly_intelligence_scorecard_markdown(scorecard: Mapping[str, Any]) -> str:
    lines = [
        f"# Weekly Intelligence Scorecard {scorecard.get('week_label')}",
        "",
        f"Generated: {scorecard.get('generated_at')}",
        f"Schema: {scorecard.get('schema_version')}",
        f"Privacy: {scorecard.get('privacy')}",
        "",
        "## Summary",
    ]
    for key, value in dict(scorecard.get("summary") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Dimensions"])
    for dimension in SCORECARD_DIMENSIONS:
        payload = (scorecard.get("dimensions") or {}).get(dimension) or {}
        lines.append(f"### {dimension}")
        lines.append(f"- status: {payload.get('status')}")
        for metric_key, metric in sorted(dict(payload.get("metrics") or {}).items()):
            lines.append(
                f"- {metric_key}: {metric.get('value')} "
                f"({metric.get('state')}; {metric.get('source')})"
            )
    incidents = scorecard.get("false_confidence_incidents") or []
    if incidents:
        lines.extend(["", "## False-Confidence Incidents"])
        for incident in incidents:
            lines.append(f"- {incident.get('severity')}: {incident.get('description')}")
    return "\n".join(lines).strip() + "\n"


def format_weekly_dogfood_markdown(review: Mapping[str, Any]) -> str:
    metrics = dict(review.get("metrics") or {})
    notes = dict(review.get("notes") or {})
    summary = dict(review.get("review") or {})
    lines = [
        f"# Dogfood Review {review.get('week_label')}",
        "",
        f"Generated: {review.get('generated_at')}",
        f"Privacy: {review.get('privacy')}",
        "",
        "## Metrics",
    ]
    for key in sorted(DOGFOOD_METRIC_KEYS):
        lines.append(f"- {key}: {metrics.get(key)}")
    lines.extend(["", "## Summary"])
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    if notes:
        lines.extend(["", "## Notes"])
        for key, value in notes.items():
            lines.append(f"- {key}: {value}")
    return "\n".join(lines).strip() + "\n"


def summarize_four_week_dogfood_reviews(reviews: Iterable[Mapping[str, Any]]) -> dict:
    rows = [dict(review) for review in reviews]
    metrics = [dict(row.get("metrics") or {}) for row in rows]
    feedback_events = sum(_nonnegative_int(row.get("feedback_events_count")) for row in metrics)
    real_actions = sum(_real_actions_count(row) for row in metrics)
    decisions = [
        decision
        for row in metrics
        for decision in _string_list(row.get("decisions_changed_by_system"))
    ]
    value_scores = [score for row in metrics if (score := _score_or_none(row.get("user_value_score_1_to_5"))) is not None]
    friction_scores = [score for row in metrics if (score := _score_or_none(row.get("friction_score_1_to_5"))) is not None]
    success = {
        "four_workbook_runs": len(rows) >= 4,
        "four_feedback_sessions": sum(1 for row in metrics if _nonnegative_int(row.get("feedback_events_count")) > 0) >= 4,
        "eight_to_twelve_feedback_events": feedback_events >= 8,
        "four_real_actions_or_decisions": real_actions + len(decisions) >= 4,
        "two_decisions_changed": len(decisions) >= 2,
        "not_a_second_job": not friction_scores or max(friction_scores[-2:]) < 4,
    }
    return {
        "status": "ok" if rows else "empty",
        "weeks_covered": [row.get("week_label") for row in rows if row.get("week_label")],
        "workbook_runs": len(rows),
        "feedback_events_count": feedback_events,
        "real_actions_completed": real_actions,
        "decisions_changed_by_system": decisions,
        "average_user_value_score": _average(value_scores),
        "average_friction_score": _average(friction_scores),
        "success_criteria": success,
        "recommendation": _dogfood_recommendation(success, value_scores, friction_scores),
    }


def _scorecard_dimensions(
    *,
    weekly_brief: Mapping[str, Any],
    knowledge_atlas: Mapping[str, Any],
    dogfood_review: Mapping[str, Any],
    observations: Mapping[str, Any],
    false_confidence_incidents: list[dict],
) -> dict:
    review_metrics = dogfood_review.get("metrics") if isinstance(dogfood_review.get("metrics"), Mapping) else {}
    review_summary = dogfood_review.get("review") if isinstance(dogfood_review.get("review"), Mapping) else {}
    projection = (
        weekly_brief.get("project_learning_projection")
        if isinstance(weekly_brief.get("project_learning_projection"), Mapping)
        else {}
    )
    learning = projection.get("learning_intelligence") if isinstance(projection.get("learning_intelligence"), Mapping) else {}
    mvp_gate = weekly_brief.get("mvp_radar_gate") if isinstance(weekly_brief.get("mvp_radar_gate"), Mapping) else {}
    dimensions = {
        "correctness": _dimension(
            {
                "canonical_contract_present": _metric(
                    bool((weekly_brief.get("intelligence_contract") or {}).get("contract_version")),
                    source="weekly_brief.intelligence_contract",
                ),
                "quality_finding_count": _metric(
                    _quality_finding_count(weekly_brief) + _quality_finding_count(knowledge_atlas),
                    source="split_sidecars.quality_findings",
                ),
                "false_confidence_incident_count": _metric(
                    len(false_confidence_incidents),
                    source="observations.false_confidence_incidents",
                ),
                "unsupported_claim_rate": _metric_unknown("needs reviewer-labeled claim fixture"),
            }
        ),
        "relevance": _dimension(
            {
                "personalization_confidence": _metric(
                    _contract_value(weekly_brief, "personalization_confidence") or "unknown",
                    source="weekly_brief.report_contract",
                ),
                "wrong_priority_count": _metric_from_review(
                    review_metrics,
                    "wrong_priority_count",
                    source="dogfood_review.metrics",
                ),
                "precision_at_3_personally_useful": _metric_unknown("requires dogfood labels"),
                "ignored_but_repeated_topic_rate": _metric_unknown("requires repeated-theme labels"),
            }
        ),
        "decisions_actions": _dimension(
            {
                "action_count": _metric(len(weekly_brief.get("actions") or []), source="weekly_brief.actions"),
                "actions_completed": _metric_from_summary(
                    review_summary,
                    "real_actions_completed",
                    source="dogfood_review.review",
                ),
                "decisions_changed_count": _metric(
                    len(_string_list(review_metrics.get("decisions_changed_by_system")))
                    if review_metrics
                    else None,
                    source="dogfood_review.metrics",
                ),
                "experiments_completed": _metric_from_review(
                    review_metrics,
                    "experiments_completed",
                    source="dogfood_review.metrics",
                ),
            }
        ),
        "learning": _dimension(
            {
                "learning_objective_count": _metric(
                    len(learning.get("objectives") or []),
                    source="project_learning_projection.learning_intelligence.objectives",
                ),
                "implemented_or_tested_objective_count": _metric(
                    _implemented_or_tested_count(learning),
                    source="project_learning_projection.learning_intelligence.stage_counts",
                ),
                "read_counted_as_mastery_incident_count": _metric(
                    _read_mastery_incident_count(learning),
                    source="project_learning_projection.learning_intelligence.objectives",
                ),
                "learning_linked_to_project_evidence": _metric_unknown("requires outcome evidence after dogfood"),
            }
        ),
        "ux": _dimension(
            {
                "time_to_understand_week_minutes": _metric_from_review(
                    review_metrics,
                    "time_to_understand_week_minutes",
                    source="dogfood_review.metrics",
                    allow_none=True,
                ),
                "brief_first_screen_task_success": _metric_from_observations(
                    observations,
                    "brief_first_screen_task_success",
                ),
                "atlas_find_source_task_success": _metric_from_observations(
                    observations,
                    "atlas_find_source_task_success",
                ),
                "feedback_friction_score": _metric_from_review(
                    review_metrics,
                    "friction_score_1_to_5",
                    source="dogfood_review.metrics",
                    allow_none=True,
                ),
            }
        ),
        "radar": _dimension(
            {
                "matched_gate_evidence_count": _metric(
                    _optional_int(mvp_gate.get("matched_gate_evidence_count"))
                    if mvp_gate
                    else None,
                    source="weekly_brief.mvp_radar_gate",
                ),
                "context_only_gate_violation_count": _metric(
                    1 if bool(mvp_gate.get("context_only_can_satisfy_gate")) else 0
                    if mvp_gate
                    else None,
                    source="weekly_brief.mvp_radar_gate",
                ),
                "radar_gate_decision": _metric(
                    mvp_gate.get("decision") if mvp_gate else None,
                    source="weekly_brief.mvp_radar_gate",
                ),
                "stale_or_missing_radar_incident_count": _metric(
                    1 if str(mvp_gate.get("radar_artifact_status") or "") == "missing" else 0
                    if mvp_gate
                    else None,
                    source="weekly_brief.mvp_radar_gate",
                ),
            }
        ),
        "operations": _dimension(
            {
                "artifact_generation_success": _metric(
                    bool(weekly_brief.get("artifact_paths") or weekly_brief.get("html_path")),
                    source="weekly_brief.artifact_paths",
                ),
                "missing_artifact_count": _metric(
                    _missing_artifact_count(weekly_brief, knowledge_atlas),
                    source="split_sidecars.artifact_paths",
                ),
                "test_regression_count": _metric_from_observations(
                    observations,
                    "test_regression_count",
                ),
                "generation_cost_usd": _metric_not_measured("cost is not recorded by deterministic fixture"),
                "generation_latency_seconds": _metric_not_measured("latency is not recorded by deterministic fixture"),
            }
        ),
    }
    return dimensions


def _dimension(metrics: Mapping[str, dict]) -> dict:
    measured = any(metric.get("state") == "measured" for metric in metrics.values())
    return {
        "status": "measured" if measured else "unknown",
        "metrics": dict(metrics),
    }


def _metric(value: Any, *, source: str, note: str | None = None) -> dict:
    if value is None:
        return _metric_unknown(note or "not available in deterministic fixture", source=source)
    if value == "unknown":
        return _metric_unknown(note or "explicitly unknown", source=source)
    if value == "not_measured":
        return _metric_not_measured(note or "explicitly not measured", source=source)
    return {"value": value, "state": "measured", "source": source, "note": note}


def _metric_unknown(note: str, *, source: str = "not_available") -> dict:
    return {"value": "unknown", "state": "unknown", "source": source, "note": note}


def _metric_not_measured(note: str, *, source: str = "not_measured") -> dict:
    return {"value": "not_measured", "state": "not_measured", "source": source, "note": note}


def _metric_from_review(
    metrics: Mapping[str, Any],
    key: str,
    *,
    source: str,
    allow_none: bool = False,
) -> dict:
    if not metrics or key not in metrics:
        return _metric_unknown("dogfood metric not recorded yet", source=source)
    value = metrics.get(key)
    if allow_none and value is None:
        return _metric_unknown("dogfood metric not recorded yet", source=source)
    return _metric(value, source=source)


def _metric_from_summary(summary: Mapping[str, Any], key: str, *, source: str) -> dict:
    if not summary or key not in summary:
        return _metric_unknown("dogfood summary not recorded yet", source=source)
    return _metric(summary.get(key), source=source)


def _metric_from_observations(observations: Mapping[str, Any], key: str) -> dict:
    if key not in observations:
        return _metric_unknown("manual observation not recorded yet", source=f"observations.{key}")
    return _metric(observations.get(key), source=f"observations.{key}")


def _unknown_metric_refs(dimensions: Mapping[str, Any]) -> list[str]:
    refs = []
    for dimension, payload in dimensions.items():
        metrics = payload.get("metrics") if isinstance(payload, Mapping) else {}
        for key, metric in dict(metrics).items():
            if isinstance(metric, Mapping) and metric.get("state") in UNKNOWN_METRIC_STATES:
                refs.append(f"{dimension}.{key}")
    return refs


def _measured_metric_count(dimensions: Mapping[str, Any]) -> int:
    count = 0
    for payload in dimensions.values():
        metrics = payload.get("metrics") if isinstance(payload, Mapping) else {}
        count += sum(1 for metric in dict(metrics).values() if isinstance(metric, Mapping) and metric.get("state") == "measured")
    return count


def _quality_finding_count(payload: Mapping[str, Any]) -> int:
    return len([item for item in payload.get("quality_findings") or [] if isinstance(item, Mapping)])


def _contract_value(weekly_brief: Mapping[str, Any], key: str) -> Any:
    contract = weekly_brief.get("report_contract") if isinstance(weekly_brief.get("report_contract"), Mapping) else {}
    return contract.get(key)


def _implemented_or_tested_count(learning: Mapping[str, Any]) -> int:
    counts = learning.get("stage_counts") if isinstance(learning.get("stage_counts"), Mapping) else {}
    return sum(_nonnegative_int(counts.get(stage)) for stage in ("implemented", "tested", "project-applied", "measured"))


def _read_mastery_incident_count(learning: Mapping[str, Any]) -> int:
    incidents = 0
    for objective in learning.get("objectives") or []:
        if not isinstance(objective, Mapping):
            continue
        if str(objective.get("mastery_claim") or "") == "claimed_from_reading_only":
            incidents += 1
    return incidents


def _missing_artifact_count(weekly_brief: Mapping[str, Any], knowledge_atlas: Mapping[str, Any]) -> int:
    missing = 0
    for payload in (weekly_brief, knowledge_atlas):
        if not payload:
            missing += 1
            continue
        paths = payload.get("artifact_paths") if isinstance(payload.get("artifact_paths"), Mapping) else {}
        if not paths and not payload.get("html_path") and not payload.get("json_path"):
            missing += 1
    return missing


def _source_artifacts(
    explicit: Mapping[str, Any] | None,
    weekly_brief: Mapping[str, Any],
    knowledge_atlas: Mapping[str, Any],
    dogfood_review: Mapping[str, Any],
) -> dict:
    result = {key: value for key, value in dict(explicit or {}).items() if value}
    if weekly_brief and "weekly_brief_json_path" not in result:
        result["weekly_brief_json_path"] = weekly_brief.get("json_path")
    if knowledge_atlas and "knowledge_atlas_json_path" not in result:
        result["knowledge_atlas_json_path"] = knowledge_atlas.get("json_path")
    if dogfood_review and "dogfood_review_json_path" not in result:
        result["dogfood_review_json_path"] = dogfood_review.get("json_path")
    return {key: value for key, value in result.items() if value}


def _false_confidence_incidents(observations: Mapping[str, Any]) -> list[dict]:
    result = []
    for index, incident in enumerate(observations.get("false_confidence_incidents") or [], start=1):
        if not isinstance(incident, Mapping):
            continue
        result.append(
            {
                "id": _optional_text(incident.get("id")) or f"false-confidence-{index}",
                "severity": _optional_text(incident.get("severity")) or "unknown",
                "description": _optional_text(incident.get("description")) or "",
                "source_refs": _string_list(incident.get("source_refs")),
                "status": _optional_text(incident.get("status")) or "open",
            }
        )
    return result


def _read_json_mapping(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON fixture must be an object: {path}")
    return payload


def _dogfood_recommendation(success: Mapping[str, bool], value_scores: list[int], friction_scores: list[int]) -> str:
    if friction_scores and len(friction_scores) >= 2 and all(score >= 4 for score in friction_scores[-2:]):
        return "simplify_hermes_pi"
    if value_scores and len(value_scores) >= 2 and all(score <= 2 for score in value_scores[-2:]):
        return "focus_workbook_feedback"
    if success and all(success.values()):
        return "continue_hpi_as_is"
    return "continue_dogfood_until_evidence_is_sufficient"


def _real_actions_count(metrics: Mapping[str, Any]) -> int:
    return (
        _nonnegative_int(metrics.get("read_items_completed"))
        + _nonnegative_int(metrics.get("try_items_completed"))
        + _nonnegative_int(metrics.get("experiments_completed"))
        + _nonnegative_int(metrics.get("project_actions_created"))
        + _nonnegative_int(metrics.get("applied_to_project_count"))
    )


def _feedback_signal_count(metrics: Mapping[str, Any]) -> int:
    return (
        _nonnegative_int(metrics.get("feedback_events_count"))
        + _nonnegative_int(metrics.get("wrong_priority_count"))
        + _nonnegative_int(metrics.get("not_interested_count"))
        + _nonnegative_int(metrics.get("applied_to_project_count"))
    )


def _requires_simplification(metrics: Mapping[str, Any]) -> bool:
    friction = _score_or_none(metrics.get("friction_score_1_to_5"))
    value = _score_or_none(metrics.get("user_value_score_1_to_5"))
    return bool((friction is not None and friction >= 4) or (value is not None and value <= 2))


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _required_text(value: Any, field_name: str) -> str:
    text = _optional_text(value)
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _nonnegative_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    return max(0, int(value))


def _score_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    score = int(value)
    if score < 1 or score > 5:
        raise ValueError("dogfood scores must be between 1 and 5")
    return score


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _average(values: list[int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)
