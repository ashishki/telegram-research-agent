from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from assistant.pi_chat import route_pi_intent
from assistant.pi_facade import PersonalIntelligenceFacade
from assistant.pi_tools import build_pi_tool_catalog, call_pi_tool
from assistant.project_context import render_project_context_answer
from config.settings import Settings


LOCAL_ASK_ALLOWED_TOOLS = frozenset(
    {
        "get_current_week_label",
        "get_weekly_summary",
        "get_artifact_status",
        "get_workbook_sections",
        "get_action_statuses",
        "search_intelligence_items",
        "search_telegram_archive",
        "search_idea_threads",
        "get_idea_thread",
        "get_project_actions",
        "analyze_project_context",
        "get_mvp_radar_status",
        "get_feedback_summary",
        "list_marked_posts",
        "get_strategy_reviewer_notes",
        "request_external_verification",
    }
)
LIMITED_TOOLS = frozenset(
    {
        "search_intelligence_items",
        "search_telegram_archive",
        "search_idea_threads",
        "get_project_actions",
        "analyze_project_context",
        "list_marked_posts",
    }
)
WEEK_ARG_TOOLS = frozenset(
    {
        "get_weekly_summary",
        "get_artifact_status",
        "get_workbook_sections",
        "get_action_statuses",
        "search_idea_threads",
        "get_project_actions",
        "analyze_project_context",
        "get_mvp_radar_status",
        "get_feedback_summary",
        "list_marked_posts",
        "get_strategy_reviewer_notes",
    }
)


def answer_local_memory_question(
    question: str,
    *,
    settings: Settings | None = None,
    facade: PersonalIntelligenceFacade | None = None,
    week_label: str | None = None,
    project_name: str | None = None,
    limit: int = 5,
) -> dict:
    clean_question = " ".join(str(question or "").split())
    if not clean_question:
        return _empty_payload("Question is empty.")

    bounded_limit = max(1, min(10, int(limit or 5)))
    active_facade = facade or PersonalIntelligenceFacade(settings=settings)
    route = _local_route(clean_question, project_name=project_name, week_label=week_label, limit=bounded_limit)
    catalog = build_pi_tool_catalog()
    tool_results: list[dict] = []
    for call in route["tool_calls"]:
        name = str(call.get("name") or "").strip()
        arguments = dict(call.get("arguments") or {})
        tool = catalog.get(name)
        if name not in LOCAL_ASK_ALLOWED_TOOLS or tool is None or not tool.read_only or tool.proposal_only:
            tool_results.append(
                {
                    "name": name,
                    "arguments": arguments,
                    "status": "rejected",
                    "read_only": bool(tool.read_only) if tool else False,
                    "result": {
                        "status": "rejected",
                        "message": f"Tool is not allowed in local memory ask: {name}",
                    },
                }
            )
            continue
        result = call_pi_tool(name, arguments, facade=active_facade, catalog=catalog)
        tool_results.append(
            {
                "name": name,
                "arguments": arguments,
                "status": result.get("status") or "ok",
                "evidence_status": result.get("evidence_status"),
                "read_only": bool(result.get("read_only", True)),
                "result": result,
            }
        )

    evidence = _collect_evidence(tool_results)
    return {
        "schema_version": "local_memory_answer.v1",
        "status": "ok" if tool_results else "empty",
        "question": clean_question,
        "mode": "local_only",
        "intent": route["intent"],
        "tool_calls": [{"name": item["name"], "arguments": item["arguments"]} for item in tool_results],
        "tool_results": tool_results,
        "evidence": evidence,
        "answer": _render_answer_body(tool_results, evidence=evidence),
        "privacy": {
            "model_calls": 0,
            "external_skill_used": False,
            "raw_telegram_corpus_egress": False,
            "bounded_telegram_snippet_provider_egress": False,
            "write_performed": False,
            "startup_migration_run": False,
        },
    }


def render_local_memory_answer(payload: Mapping[str, Any]) -> str:
    if payload.get("status") == "invalid":
        return str(payload.get("message") or "Question is empty.")

    lines = [
        "PRM Memory",
        f"Question: {payload.get('question') or ''}",
        f"Mode: {payload.get('mode') or 'local_only'}; no LLM, no external search, no writes.",
        "",
    ]
    answer = str(payload.get("answer") or "").strip()
    if answer:
        lines.append(answer)
    else:
        lines.append("No local evidence matched. I will not guess beyond available data.")

    privacy = payload.get("privacy") or {}
    lines.extend(
        [
            "",
            "Boundary",
            (
                "model_calls={model_calls} external_skill_used={external_skill_used} "
                "write_performed={write_performed} raw_corpus_egress={raw_telegram_corpus_egress}"
            ).format(
                model_calls=privacy.get("model_calls", 0),
                external_skill_used=bool(privacy.get("external_skill_used")),
                write_performed=bool(privacy.get("write_performed")),
                raw_telegram_corpus_egress=bool(privacy.get("raw_telegram_corpus_egress")),
            ),
            (
                "Privacy: mode=local-only; model_calls={model_calls}; estimated_cost_usd=0; "
                "bounded_telegram_snippet_provider_egress={bounded_telegram_snippet_provider_egress}; "
                "raw_telegram_corpus_egress={raw_telegram_corpus_egress}; durable_writes={durable_writes}"
            ).format(
                model_calls=privacy.get("model_calls", 0),
                bounded_telegram_snippet_provider_egress=_bool_text(
                    privacy.get("bounded_telegram_snippet_provider_egress")
                ),
                raw_telegram_corpus_egress=_bool_text(privacy.get("raw_telegram_corpus_egress")),
                durable_writes=_bool_text(privacy.get("write_performed")),
            ),
        ]
    )
    return "\n".join(lines).rstrip()


def _local_route(
    question: str,
    *,
    project_name: str | None,
    week_label: str | None,
    limit: int,
) -> dict[str, object]:
    if project_name:
        return {
            "intent": "project_application",
            "tool_calls": [
                {
                    "name": "analyze_project_context",
                    "arguments": {
                        "query": question,
                        "project_name": project_name,
                        "week_label": week_label,
                        "limit": limit,
                    },
                }
            ],
        }

    route = route_pi_intent(question)
    calls = []
    for call in route.get("tool_calls") or []:
        if not isinstance(call, Mapping):
            continue
        name = str(call.get("name") or "").strip()
        arguments = dict(call.get("arguments") or {})
        if name in LIMITED_TOOLS:
            arguments["limit"] = limit
        if week_label and name in WEEK_ARG_TOOLS:
            arguments["week_label"] = week_label
        if week_label and name == "search_intelligence_items":
            filters = dict(arguments.get("filters") or {})
            filters["week_label"] = week_label
            arguments["filters"] = filters
        calls.append({"name": name, "arguments": arguments})
    return {
        "intent": route.get("intent") or "general_memory",
        "tool_calls": calls,
    }


def _render_answer_body(tool_results: list[dict], *, evidence: Mapping[str, Any]) -> str:
    project_context = _first_project_context(tool_results)
    if project_context is not None:
        return render_project_context_answer(project_context)

    lines: list[str] = []
    external_requests = _external_requests(tool_results)
    if external_requests:
        lines.append("External verification is required before treating this as current fact.")
        for request in external_requests[:2]:
            lines.append(f"- {request.get('category') or 'external'}: {request.get('reason') or 'needs verification'}")
        lines.append("No external request was run.")

    curated = _curated_items(tool_results)
    if curated:
        lines.append("Knowledge signals")
        for item in curated[:5]:
            title = item.get("title") or item.get("id") or item.get("item_type") or "item"
            summary = item.get("summary") or item.get("text") or item.get("claim") or ""
            lines.append(f"- {title}: {_short(summary, 220)}")
            refs = _source_refs(item)
            if refs:
                lines.append(f"  sources: {', '.join(_display_ref(ref) for ref in refs[:3])}")

    archive = _archive_items(tool_results)
    if archive:
        if lines:
            lines.append("")
        lines.append("Archive evidence")
        for item in archive[:5]:
            date = str(item.get("posted_at") or "")[:10] or "date unknown"
            channel = item.get("channel_username") or "source"
            snippet = item.get("snippet") or item.get("content") or ""
            lines.append(f"- {date} {channel}: {_short(snippet, 260)}")
            if item.get("source_url"):
                lines.append(f"  source: {item['source_url']}")

    artifacts = evidence.get("artifact_paths") or {}
    if isinstance(artifacts, Mapping) and artifacts:
        if lines:
            lines.append("")
        lines.append("Artifacts")
        for key, path in list(artifacts.items())[:5]:
            lines.append(f"- {key}: {_display_ref(path)}")

    if not lines:
        lines.append("No local evidence matched. I will not guess beyond available data.")
    return "\n".join(lines).rstrip()


def _empty_payload(message: str) -> dict:
    return {
        "schema_version": "local_memory_answer.v1",
        "status": "invalid",
        "question": "",
        "mode": "local_only",
        "intent": "invalid_request",
        "tool_calls": [],
        "tool_results": [],
        "evidence": {"source_refs": [], "atom_ids": [], "thread_slugs": [], "artifact_paths": {}},
        "answer": "",
        "privacy": {
            "model_calls": 0,
            "external_skill_used": False,
            "raw_telegram_corpus_egress": False,
            "bounded_telegram_snippet_provider_egress": False,
            "write_performed": False,
            "startup_migration_run": False,
        },
        "message": message,
    }


def _collect_evidence(tool_results: list[dict]) -> dict:
    source_refs: list[str] = []
    atom_ids: list[str | int] = []
    thread_slugs: list[str] = []
    artifact_paths: dict[str, str] = {}
    for call in tool_results:
        result = call.get("result") or {}
        evidence = result.get("evidence") if isinstance(result, Mapping) else None
        if not isinstance(evidence, Mapping):
            continue
        source_refs.extend(str(ref) for ref in evidence.get("source_refs") or [] if str(ref).strip())
        atom_ids.extend(atom for atom in evidence.get("atom_ids") or [] if str(atom).strip())
        thread_slugs.extend(str(slug) for slug in evidence.get("thread_slugs") or [] if str(slug).strip())
        paths = evidence.get("artifact_paths")
        if isinstance(paths, Mapping):
            artifact_paths.update({str(key): str(value) for key, value in paths.items() if str(value).strip()})
    return {
        "source_refs": _unique(source_refs)[:10],
        "atom_ids": _unique(atom_ids)[:20],
        "thread_slugs": _unique(thread_slugs)[:10],
        "artifact_paths": artifact_paths,
    }


def _display_ref(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    root_text = str(Path(__file__).resolve().parents[2])
    if text.startswith(root_text + "/"):
        return text[len(root_text) + 1 :]
    return text


def _first_project_context(tool_results: list[dict]) -> dict | None:
    for call in tool_results:
        if call.get("name") != "analyze_project_context":
            continue
        result = call.get("result") or {}
        payload = result.get("result") if isinstance(result, Mapping) else None
        if isinstance(payload, Mapping):
            return dict(payload)
    return None


def _curated_items(tool_results: list[dict]) -> list[dict]:
    items: list[dict] = []
    for call in tool_results:
        if call.get("name") not in {"search_intelligence_items", "search_idea_threads", "get_idea_thread"}:
            continue
        payload = _tool_payload(call)
        items.extend(dict(item) for item in payload.get("items") or [] if isinstance(item, Mapping))
    return items


def _archive_items(tool_results: list[dict]) -> list[dict]:
    items: list[dict] = []
    for call in tool_results:
        if call.get("name") != "search_telegram_archive":
            continue
        payload = _tool_payload(call)
        items.extend(dict(item) for item in payload.get("items") or [] if isinstance(item, Mapping))
    return items


def _external_requests(tool_results: list[dict]) -> list[dict]:
    requests: list[dict] = []
    for call in tool_results:
        if call.get("name") != "request_external_verification":
            continue
        payload = _tool_payload(call)
        if payload:
            requests.append(payload)
    return requests


def _tool_payload(call: Mapping[str, Any]) -> dict:
    result = call.get("result") or {}
    if not isinstance(result, Mapping):
        return {}
    payload = result.get("result")
    return dict(payload) if isinstance(payload, Mapping) else {}


def _source_refs(item: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("source_refs", "source_urls"):
        value = item.get(key)
        if isinstance(value, list):
            refs.extend(str(ref) for ref in value if str(ref).strip())
        elif isinstance(value, str) and value.strip():
            refs.append(value)
    if isinstance(item.get("source_url"), str) and item["source_url"].strip():
        refs.append(item["source_url"])
    return _unique(refs)


def _short(value: object, limit: int) -> str:
    compact = " ".join(str(value or "").split())
    if len(compact) <= limit:
        return compact or "n/a"
    return compact[: limit - 1].rstrip() + "..."


def _unique(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    unique: list[Any] = []
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique


def _bool_text(value: object) -> str:
    return "true" if bool(value) else "false"
