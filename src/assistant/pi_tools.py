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

UNAPPROVED_EXTERNAL_SKILL_TOOL_NAMES = {
    "browser_search",
    "crawl4ai_search",
    "external_web_search",
    "reddit_search",
    "scrape_url",
    "search_web",
    "telegram_channel_parse",
    "web_search",
    "x_search",
}

APPROVED_EXTERNAL_SKILL_TOOL_NAMES: frozenset[str] = frozenset()

NO_EVIDENCE_REQUIRED_TOOLS = {"get_current_week_label"}

MINIMUM_READ_ONLY_TOOLS = {
    "get_current_week_label",
    "get_weekly_summary",
    "get_artifact_status",
    "search_intelligence_items",
    "search_telegram_archive",
    "search_idea_threads",
    "get_idea_thread",
    "get_project_actions",
    "get_mvp_radar_status",
    "get_feedback_summary",
    "list_marked_posts",
    "get_strategy_reviewer_notes",
    "request_external_verification",
}

CONFIRMATION_GATED_PROPOSAL_TOOLS = {
    "propose_knowledge_note",
    "propose_watch_topic",
    "propose_project_link",
    "propose_action",
    "propose_experiment",
    "propose_feedback",
}


@dataclass(frozen=True)
class PITool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    read_only: bool = True
    requires_confirmation: bool = False
    proposal_only: bool = False
    max_calls_per_turn: int = PI_TOOL_LOOP_MAX_CALLS

    def describe(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "read_only": self.read_only,
            "requires_confirmation": self.requires_confirmation,
            "proposal_only": self.proposal_only,
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
        "get_artifact_status": PITool(
            name="get_artifact_status",
            description=PI_TOOL_DESCRIPTIONS["get_artifact_status"],
            input_schema=_schema({"week_label": {"type": ["string", "null"]}}),
            handler=lambda facade, args: facade.get_artifact_status(_optional_string(args.get("week_label"))),
        ),
        "get_workbook_sections": PITool(
            name="get_workbook_sections",
            description=PI_TOOL_DESCRIPTIONS["get_workbook_sections"],
            input_schema=_schema({"week_label": {"type": ["string", "null"]}}),
            handler=_handle_workbook_sections,
        ),
        "get_action_statuses": PITool(
            name="get_action_statuses",
            description=PI_TOOL_DESCRIPTIONS["get_action_statuses"],
            input_schema=_schema({"week_label": {"type": ["string", "null"]}}),
            handler=lambda facade, args: facade.get_action_statuses(_optional_string(args.get("week_label"))),
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
        "search_telegram_archive": PITool(
            name="search_telegram_archive",
            description=PI_TOOL_DESCRIPTIONS["search_telegram_archive"],
            input_schema=_schema(
                {
                    "query": {"type": "string"},
                    "filters": _archive_search_filters_schema(),
                    "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 20},
                },
                required=["query"],
            ),
            handler=lambda facade, args: facade.search_telegram_archive(
                _required_string(args.get("query"), "query"),
                filters=_optional_mapping(args.get("filters")),
                limit=_limit(args.get("limit"), default=10, maximum=20),
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
                }
            ),
            handler=lambda facade, args: facade.get_strategy_reviewer_notes(_optional_string(args.get("week_label"))),
        ),
        "request_external_verification": PITool(
            name="request_external_verification",
            description=PI_TOOL_DESCRIPTIONS["request_external_verification"],
            input_schema=_schema(
                {
                    "question": {"type": "string"},
                    "category": {"type": ["string", "null"]},
                    "reason": {"type": ["string", "null"]},
                },
                required=["question"],
            ),
            handler=lambda _facade, args: _external_verification_request(args),
        ),
        "propose_knowledge_note": _proposal_tool("propose_knowledge_note", "knowledge_note"),
        "propose_watch_topic": _proposal_tool("propose_watch_topic", "watch_topic"),
        "propose_project_link": _proposal_tool("propose_project_link", "project_link"),
        "propose_action": _proposal_tool("propose_action", "action"),
        "propose_experiment": _proposal_tool("propose_experiment", "experiment"),
        "propose_feedback": _proposal_tool("propose_feedback", "feedback"),
    }
    validate_pi_tool_catalog(catalog)
    return catalog


def list_pi_tools(catalog: Mapping[str, PITool] | None = None) -> list[dict]:
    tools = catalog or build_pi_tool_catalog()
    return [tool.describe() for tool in tools.values()]


def validate_pi_tool_catalog(catalog: Mapping[str, PITool]) -> dict:
    forbidden = sorted(FORBIDDEN_TOOL_NAMES.intersection(catalog))
    unapproved_external = sorted(
        UNAPPROVED_EXTERNAL_SKILL_TOOL_NAMES.intersection(catalog).difference(APPROVED_EXTERNAL_SKILL_TOOL_NAMES)
    )
    writable = sorted(name for name, tool in catalog.items() if not tool.read_only)
    missing_read_only = sorted(MINIMUM_READ_ONLY_TOOLS.difference(catalog))
    missing_proposals = sorted(CONFIRMATION_GATED_PROPOSAL_TOOLS.difference(catalog))
    unsafe_proposals = sorted(
        name
        for name in CONFIRMATION_GATED_PROPOSAL_TOOLS.intersection(catalog)
        if not catalog[name].requires_confirmation or not catalog[name].proposal_only
    )
    if forbidden:
        raise ValueError(f"Forbidden mutation tools in PI catalog: {', '.join(forbidden)}")
    if unapproved_external:
        raise ValueError(f"Unapproved external-skill tools in PI catalog: {', '.join(unapproved_external)}")
    if writable:
        raise ValueError(f"PI catalog tools must be read-only: {', '.join(writable)}")
    if missing_read_only:
        raise ValueError(f"Missing minimum read-only PI tools: {', '.join(missing_read_only)}")
    if missing_proposals:
        raise ValueError(f"Missing confirmation-gated proposal tools: {', '.join(missing_proposals)}")
    if unsafe_proposals:
        raise ValueError(f"Proposal tools must be confirmation-gated: {', '.join(unsafe_proposals)}")
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


def _proposal_tool(name: str, proposal_type: str) -> PITool:
    return PITool(
        name=name,
        description=PI_TOOL_DESCRIPTIONS[name],
        input_schema=_schema(
            {
                "title": {"type": "string"},
                "rationale": {"type": ["string", "null"]},
                "source_refs": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                },
            },
            required=["title"],
        ),
        handler=lambda _facade, args: _proposal_response(proposal_type, args),
        read_only=True,
        requires_confirmation=True,
        proposal_only=True,
    )


def _proposal_response(proposal_type: str, args: Mapping[str, Any]) -> dict:
    return {
        "status": "needs_confirmation",
        "proposal_type": proposal_type,
        "proposal": {
            "title": _required_string(args.get("title"), "title"),
            "rationale": _optional_string(args.get("rationale")),
            "source_refs": _string_list(args.get("source_refs")),
        },
        "persisted": False,
        "message": "Proposal drafted only; human confirmation is required before persistence.",
    }


def _external_verification_request(args: Mapping[str, Any]) -> dict:
    question = _required_string(args.get("question"), "question")
    category = _optional_string(args.get("category")) or "unstable_or_high_stakes_claim"
    reason = _optional_string(args.get("reason")) or "The answer needs current or high-stakes evidence outside Telegram."
    return {
        "status": "needs_external_verification",
        "question": question,
        "category": category,
        "reason": reason,
        "telegram_evidence": {
            "role": "discovery_context_only",
            "status": "not_collected_by_this_tool",
            "source_refs": [],
        },
        "external_evidence": {
            "status": "not_run_unapproved",
            "source_refs": [],
            "external_skill_used": False,
            "approved_trust_record": False,
            "trust_record_required": True,
        },
        "unknowns": [
            "current external truth",
            "independent source corroboration",
        ],
        "persistence": {
            "stored_research_note": False,
            "requires_human_confirmation": True,
        },
        "privacy_boundary": {
            "raw_telegram_corpus_egress": False,
            "external_skill_used": False,
            "write_performed": False,
        },
        "message": "External verification is required; no external request was run and no note was stored.",
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


def _archive_search_filters_schema() -> dict:
    string_or_array = {
        "oneOf": [
            {"type": "string"},
            {"type": "array", "items": {"type": "string"}},
        ]
    }
    return {
        "type": ["object", "null"],
        "properties": {
            "channel_usernames": string_or_array,
            "channels": string_or_array,
            "languages": string_or_array,
            "language": string_or_array,
            "date_from": {"type": ["string", "null"]},
            "date_to": {"type": ["string", "null"]},
            "reacted_only": {"type": ["boolean", "null"]},
            "reactions": string_or_array,
            "reaction": string_or_array,
            "tags": string_or_array,
            "tag": string_or_array,
            "project_names": string_or_array,
            "project_name": string_or_array,
        },
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
