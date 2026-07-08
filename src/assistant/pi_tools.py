from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from assistant.pi_facade import PersonalIntelligenceFacade
from assistant.pi_prompts import PI_TOOL_DESCRIPTIONS, PI_TOOL_LOOP_MAX_CALLS


ToolHandler = Callable[[PersonalIntelligenceFacade, Mapping[str, Any]], dict]

FORBIDDEN_TOOL_NAMES = {
    "edit_code",
    "run_codex",
    "edit_config",
    "mutate_profile",
    "mutate_projects",
    "write_feedback",
    "record_feedback",
    "confirm_feedback",
    "mutate_db",
    "execute_sql",
}

NO_EVIDENCE_REQUIRED_TOOLS = {"get_current_week_label"}


@dataclass(frozen=True)
class PITool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    read_only: bool = True
    max_calls_per_turn: int = PI_TOOL_LOOP_MAX_CALLS

    def describe(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "read_only": self.read_only,
            "max_calls_per_turn": self.max_calls_per_turn,
            "input_schema": self.input_schema,
        }

    def call(self, facade: PersonalIntelligenceFacade, arguments: Mapping[str, Any] | None = None) -> dict:
        args = dict(arguments or {})
        try:
            result = self.handler(facade, args)
        except (TypeError, ValueError) as exc:
            return _tool_response(
                self.name,
                {
                    "status": "invalid",
                    "message": str(exc),
                },
            )
        return _tool_response(self.name, result)


def build_pi_tool_catalog() -> dict[str, PITool]:
    catalog = {
        "get_current_week_label": PITool(
            name="get_current_week_label",
            description=PI_TOOL_DESCRIPTIONS["get_current_week_label"],
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=lambda facade, _args: facade.get_current_week_label(),
        ),
        "get_weekly_summary": PITool(
            name="get_weekly_summary",
            description=PI_TOOL_DESCRIPTIONS["get_weekly_summary"],
            input_schema=_schema({"week_label": {"type": ["string", "null"]}}),
            handler=lambda facade, args: facade.get_workbook_summary(_optional_string(args.get("week_label"))),
        ),
        "get_workbook_sections": PITool(
            name="get_workbook_sections",
            description=PI_TOOL_DESCRIPTIONS["get_workbook_sections"],
            input_schema=_schema({"week_label": {"type": ["string", "null"]}}),
            handler=_handle_workbook_sections,
        ),
        "search_intelligence_items": PITool(
            name="search_intelligence_items",
            description=PI_TOOL_DESCRIPTIONS["search_intelligence_items"],
            input_schema=_schema(
                {
                    "query": {"type": "string"},
                    "filters": {"type": ["object", "null"]},
                    "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 50},
                },
                required=["query"],
            ),
            handler=lambda facade, args: facade.search_intelligence_items(
                _required_string(args.get("query"), "query"),
                filters=_optional_mapping(args.get("filters")),
                limit=_limit(args.get("limit"), default=10),
            ),
        ),
        "search_idea_threads": PITool(
            name="search_idea_threads",
            description=PI_TOOL_DESCRIPTIONS["search_idea_threads"],
            input_schema=_schema(
                {
                    "query": {"type": "string"},
                    "week_label": {"type": ["string", "null"]},
                    "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 50},
                },
                required=["query"],
            ),
            handler=lambda facade, args: facade.search_idea_threads(
                _required_string(args.get("query"), "query"),
                week_label=_optional_string(args.get("week_label")),
                limit=_limit(args.get("limit"), default=10),
            ),
        ),
        "get_idea_thread": PITool(
            name="get_idea_thread",
            description=PI_TOOL_DESCRIPTIONS["get_idea_thread"],
            input_schema=_schema({"slug": {"type": "string"}}, required=["slug"]),
            handler=lambda facade, args: facade.get_idea_thread(_required_string(args.get("slug"), "slug")),
        ),
        "get_project_actions": PITool(
            name="get_project_actions",
            description=PI_TOOL_DESCRIPTIONS["get_project_actions"],
            input_schema=_schema({"week_label": {"type": ["string", "null"]}}),
            handler=lambda facade, args: facade.get_project_actions(_optional_string(args.get("week_label"))),
        ),
        "get_mvp_radar_status": PITool(
            name="get_mvp_radar_status",
            description=PI_TOOL_DESCRIPTIONS["get_mvp_radar_status"],
            input_schema=_schema({"week_label": {"type": ["string", "null"]}}),
            handler=lambda facade, args: facade.get_mvp_radar_status(_optional_string(args.get("week_label"))),
        ),
        "get_feedback_summary": PITool(
            name="get_feedback_summary",
            description=PI_TOOL_DESCRIPTIONS["get_feedback_summary"],
            input_schema=_schema({"week_label": {"type": ["string", "null"]}}),
            handler=lambda facade, args: facade.get_feedback_summary(_optional_string(args.get("week_label"))),
        ),
        "list_marked_posts": PITool(
            name="list_marked_posts",
            description=PI_TOOL_DESCRIPTIONS["list_marked_posts"],
            input_schema=_schema(
                {
                    "week_label": {"type": ["string", "null"]},
                    "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 50},
                }
            ),
            handler=lambda facade, args: facade.list_marked_posts(
                week_label=_optional_string(args.get("week_label")),
                limit=_limit(args.get("limit"), default=20),
            ),
        ),
        "get_strategy_reviewer_notes": PITool(
            name="get_strategy_reviewer_notes",
            description=PI_TOOL_DESCRIPTIONS["get_strategy_reviewer_notes"],
            input_schema=_schema(
                {
                    "week_label": {"type": ["string", "null"]},
                    "query": {"type": ["string", "null"]},
                    "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 20},
                }
            ),
            handler=_handle_strategy_reviewer_notes,
        ),
    }
    validate_pi_tool_catalog(catalog)
    return catalog


def list_pi_tools(catalog: Mapping[str, PITool] | None = None) -> list[dict]:
    tools = catalog or build_pi_tool_catalog()
    return [tool.describe() for tool in tools.values()]


def validate_pi_tool_catalog(catalog: Mapping[str, PITool]) -> dict:
    forbidden = sorted(FORBIDDEN_TOOL_NAMES.intersection(catalog))
    writable = sorted(name for name, tool in catalog.items() if not tool.read_only)
    if forbidden:
        raise ValueError(f"Forbidden mutation tools in PI catalog: {', '.join(forbidden)}")
    if writable:
        raise ValueError(f"PI catalog tools must be read-only: {', '.join(writable)}")
    return {
        "status": "ok",
        "tool_count": len(catalog),
        "max_calls_per_turn": PI_TOOL_LOOP_MAX_CALLS,
        "message": "PI tool catalog is read-only.",
    }


def call_pi_tool(
    name: str,
    arguments: Mapping[str, Any] | None = None,
    *,
    facade: PersonalIntelligenceFacade | None = None,
    catalog: Mapping[str, PITool] | None = None,
) -> dict:
    tools = catalog or build_pi_tool_catalog()
    clean_name = str(name or "").strip()
    tool = tools.get(clean_name)
    if tool is None:
        return _tool_response(
            clean_name,
            {
                "status": "missing",
                "message": f"Unknown read-only PI tool: {clean_name}",
            },
        )
    return tool.call(facade or PersonalIntelligenceFacade(), arguments)


def _handle_workbook_sections(facade: PersonalIntelligenceFacade, args: Mapping[str, Any]) -> dict:
    week_label = _optional_string(args.get("week_label"))
    if not week_label:
        current = facade.get_current_week_label()
        week_label = _optional_string(current.get("week_label"))
    if not week_label:
        return {
            "status": "missing",
            "week_label": None,
            "sections": [],
            "message": "Week label is unavailable.",
        }
    return facade.get_workbook_sections(week_label)


def _handle_strategy_reviewer_notes(facade: PersonalIntelligenceFacade, args: Mapping[str, Any]) -> dict:
    filters = {"item_type": "strategy_reviewer_note"}
    week_label = _optional_string(args.get("week_label"))
    if week_label:
        filters["week_label"] = week_label
    result = facade.search_intelligence_items(
        _optional_string(args.get("query")) or "strategy reviewer",
        filters=filters,
        limit=_limit(args.get("limit"), default=5, maximum=20),
    )
    return {
        "status": result.get("status", "empty"),
        "week_label": week_label,
        "items": list(result.get("items") or []),
        "message": result.get("message") or "No Strategy Reviewer notes are available.",
    }


def _tool_response(tool_name: str, result: Mapping[str, Any]) -> dict:
    normalized = dict(result)
    status = str(normalized.get("status") or "ok")
    evidence = _collect_evidence(normalized)
    if tool_name in NO_EVIDENCE_REQUIRED_TOOLS and status == "ok":
        evidence_status = "not_required"
    elif _has_evidence(evidence):
        evidence_status = "available"
    else:
        evidence_status = "insufficient"
    return {
        "status": status,
        "tool_name": tool_name,
        "read_only": True,
        "evidence_status": evidence_status,
        "evidence": evidence,
        "result": normalized,
        "message": normalized.get("message") or _default_message(status, evidence_status),
    }


def _collect_evidence(value: Any) -> dict:
    source_refs: list[str] = []
    atom_ids: list[str | int] = []
    thread_slugs: list[str] = []
    artifact_paths: dict[str, str] = {}

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, raw_value in item.items():
                if key in {"source_refs", "source_urls"}:
                    source_refs.extend(_string_list(raw_value))
                    continue
                if key == "source_url":
                    single = _optional_string(raw_value)
                    if single:
                        source_refs.append(single)
                    continue
                if key in {"atom_ids", "source_atom_ids"}:
                    atom_ids.extend(_id_list(raw_value))
                    continue
                if key == "thread_slug":
                    slug = _optional_string(raw_value)
                    if slug:
                        thread_slugs.append(slug)
                    continue
                if key == "artifact_paths" and isinstance(raw_value, Mapping):
                    for path_key, path_value in raw_value.items():
                        clean_path = _optional_string(path_value)
                        if clean_path:
                            artifact_paths[str(path_key)] = clean_path
                    continue
                visit(raw_value)
            return
        if isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return {
        "source_refs": _unique(source_refs),
        "atom_ids": _unique(atom_ids),
        "thread_slugs": _unique(thread_slugs),
        "artifact_paths": artifact_paths,
    }


def _has_evidence(evidence: Mapping[str, Any]) -> bool:
    return any(
        bool(evidence.get(key))
        for key in ("source_refs", "atom_ids", "thread_slugs", "artifact_paths")
    )


def _schema(properties: Mapping[str, Any], required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required or []),
        "additionalProperties": False,
    }


def _optional_mapping(value: Any) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("filters must be an object")
    return dict(value)


def _required_string(value: Any, field_name: str) -> str:
    clean = _optional_string(value)
    if not clean:
        raise ValueError(f"{field_name} is required")
    return clean


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    clean = str(value).strip()
    return clean or None


def _limit(value: Any, *, default: int, maximum: int = 50) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    return max(1, min(maximum, parsed))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _id_list(value: Any) -> list[str | int]:
    if value is None:
        return []
    if isinstance(value, str | int):
        return [value]
    if isinstance(value, list | tuple | set):
        return [item for item in value if item is not None and str(item).strip()]
    return [value]


def _unique(values: list[Any]) -> list:
    result = []
    seen = set()
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _default_message(status: str, evidence_status: str) -> str:
    if status in {"missing", "empty"} or evidence_status == "insufficient":
        return "Curated evidence is missing or insufficient."
    return "PI tool completed."
