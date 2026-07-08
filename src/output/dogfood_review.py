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
