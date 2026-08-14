"""Proposed, non-mutating project portfolio context for PRM-UX-4."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


PROJECT_PORTFOLIO_CONTEXT_SCHEMA_VERSION = "project_portfolio_context.v2"
PROJECT_PORTFOLIO_STATUSES = frozenset({"active", "priority", "watch", "reference", "paused", "archived"})
_REQUIRED_FIELDS = (
    "name",
    "status",
    "priority",
    "current_goal",
    "current_blocker",
    "next_proof",
    "preferred_signal_types",
    "owner_confirmation_status",
    "capabilities",
    "aliases",
    "reviewed_metadata",
    "source_metadata",
)


def validate_project_portfolio_context(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an in-memory proposed descriptor without reading or writing project config."""

    missing = [field for field in _REQUIRED_FIELDS if not _has_value(raw.get(field))]
    if missing:
        raise ValueError("project portfolio context missing: " + ", ".join(missing))
    status = str(raw["status"]).strip().casefold()
    if status not in PROJECT_PORTFOLIO_STATUSES:
        raise ValueError("unsupported project portfolio status")
    try:
        priority = int(raw["priority"])
    except (TypeError, ValueError) as exc:
        raise ValueError("project portfolio priority must be an integer") from exc
    if priority < 1:
        raise ValueError("project portfolio priority must be positive")
    return {
        "schema_version": PROJECT_PORTFOLIO_CONTEXT_SCHEMA_VERSION,
        "name": str(raw["name"]).strip(),
        "status": status,
        "priority": priority,
        "current_goal": str(raw["current_goal"]).strip(),
        "current_blocker": str(raw["current_blocker"]).strip(),
        "next_proof": str(raw["next_proof"]).strip(),
        "preferred_signal_types": _string_list(raw["preferred_signal_types"]),
        "excluded_signal_types": _string_list(raw.get("excluded_signal_types") or []),
        "owner_confirmation_status": str(raw["owner_confirmation_status"]).strip().casefold(),
        "capabilities": _string_list(raw["capabilities"]),
        "aliases": _string_list(raw["aliases"]),
        "reviewed_metadata": str(raw["reviewed_metadata"]).strip(),
        "source_metadata": str(raw["source_metadata"]).strip(),
    }


def default_project_portfolio(projects: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return only owner-confirmed active/priority projects for default routing."""

    validated = [validate_project_portfolio_context(project) for project in projects]
    active = [
        project
        for project in validated
        if project["status"] in {"active", "priority"} and project["owner_confirmation_status"] == "confirmed"
    ]
    return sorted(active, key=lambda project: (project["priority"], project["name"].casefold()))


def select_project_portfolio_context(
    projects: Sequence[Mapping[str, Any]], *, named_project: str | None = None
) -> list[dict[str, Any]]:
    """Use an explicitly named project even when it is not in the default active set."""

    validated = [validate_project_portfolio_context(project) for project in projects]
    clean_name = str(named_project or "").strip().casefold()
    if not clean_name:
        return default_project_portfolio(validated)
    return [project for project in validated if project["name"].casefold() == clean_name]


def project_action_recommendation_allowed(project: Mapping[str, Any], *, direct_evidence: bool) -> bool:
    """Keyword overlap alone cannot become a project action recommendation."""

    validated = validate_project_portfolio_context(project)
    return bool(
        direct_evidence
        and validated["status"] in {"active", "priority"}
        and validated["owner_confirmation_status"] == "confirmed"
    )


def _has_value(value: object) -> bool:
    if isinstance(value, (list, tuple)):
        return bool(value)
    return bool(str(value or "").strip())


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("project portfolio signal fields must be lists")
    return [str(item).strip() for item in value if str(item).strip()]
