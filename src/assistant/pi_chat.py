from __future__ import annotations

import json
import time
from typing import Any, Mapping

from assistant.pi_facade import PersonalIntelligenceFacade
from assistant.pi_prompts import PI_ASSISTANT_SYSTEM_PROMPT, PI_TOOL_LOOP_MAX_CALLS
from assistant.pi_tools import build_pi_tool_catalog, call_pi_tool
from config.settings import Settings
from llm.client import LLMClient


MAX_TOOL_RESULT_CHARS = 8000
MAX_FINAL_CONTEXT_CHARS = 24000


def answer_pi_chat(
    question: str,
    *,
    settings: Settings | None = None,
    facade: PersonalIntelligenceFacade | None = None,
    llm_client: type[LLMClient] = LLMClient,
) -> dict:
    clean_question = " ".join(str(question or "").split())
    if not clean_question:
        return {
            "status": "invalid",
            "answer": "Напиши вопрос или задачу для Hermes.",
            "tool_calls": [],
            "tool_results": [],
            "evidence": {},
            "trace": _empty_trace(termination_reason="invalid_request"),
            "message": "Question is empty.",
        }

    active_facade = facade or PersonalIntelligenceFacade(settings=settings)
    catalog = build_pi_tool_catalog()
    deterministic_route = route_pi_intent(clean_question)
    planning_started = time.perf_counter()
    plan = _plan_tool_calls(
        clean_question,
        catalog=catalog,
        llm_client=llm_client,
        deterministic_route=deterministic_route,
    )
    planning_latency_ms = _elapsed_ms(planning_started)
    tool_calls = _normalize_tool_calls(plan.get("tool_calls") if isinstance(plan, Mapping) else None)
    planner = str(plan.get("planner") or "llm") if isinstance(plan, Mapping) else "llm"
    planning_model_calls = 1 if isinstance(plan, Mapping) and plan.get("model_call_attempted") is True else 0

    if not tool_calls:
        tool_calls = list(deterministic_route["tool_calls"])
        planner = "deterministic"

    executed_calls: list[dict] = []
    retrieval_started = time.perf_counter()
    for call in tool_calls[:PI_TOOL_LOOP_MAX_CALLS]:
        tool_name = str(call.get("name") or "").strip()
        if tool_name not in catalog:
            executed_calls.append(
                {
                    "name": tool_name,
                    "arguments": dict(call.get("arguments") or {}),
                    "status": "rejected",
                    "result": {"status": "missing", "message": f"Tool is not in read-only PI catalog: {tool_name}"},
                }
            )
            continue
        arguments = dict(call.get("arguments") or {})
        result = call_pi_tool(tool_name, arguments, facade=active_facade, catalog=catalog)
        executed_calls.append(
            {
                "name": tool_name,
                "arguments": arguments,
                "status": result.get("status") or "ok",
                "evidence_status": result.get("evidence_status"),
                "result": _compact_result(result),
            }
        )

    retrieval_latency_ms = _elapsed_ms(retrieval_started)
    evidence = _collect_chat_evidence(executed_calls)
    generation_started = time.perf_counter()
    answer = _synthesize_answer(
        clean_question,
        executed_calls=executed_calls,
        evidence=evidence,
        llm_client=llm_client,
    )
    generation_latency_ms = _elapsed_ms(generation_started)
    trace = _build_assistant_trace(
        route=deterministic_route,
        planner=planner,
        executed_calls=executed_calls,
        evidence=evidence,
    )
    answer_contract = _build_answer_contract(
        answer,
        executed_calls=executed_calls,
        evidence=evidence,
        trace=trace,
    )
    telemetry = _build_answer_telemetry(
        planning_latency_ms=planning_latency_ms,
        retrieval_latency_ms=retrieval_latency_ms,
        generation_latency_ms=generation_latency_ms,
        planning_model_calls=planning_model_calls,
        generation_model_calls=1,
        tool_call_count=len(executed_calls),
    )
    return {
        "status": "ok" if executed_calls else "empty",
        "answer": answer,
        "tool_calls": [{"name": call["name"], "arguments": call["arguments"]} for call in executed_calls],
        "tool_results": executed_calls,
        "evidence": evidence,
        "trace": trace,
        "answer_contract": answer_contract,
        "telemetry": telemetry,
        "message": "Hermes PI chat answered through bounded read-only tools.",
    }


def _plan_tool_calls(
    question: str,
    *,
    catalog: Mapping[str, Any],
    llm_client: type[LLMClient],
    deterministic_route: Mapping[str, Any],
) -> dict:
    tool_descriptions = [
        {
            "name": name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for name, tool in catalog.items()
    ]
    prompt = (
        "Choose read-only PI tools to answer the operator question.\n"
        "Return JSON only with this shape:\n"
        '{"tool_calls":[{"name":"tool_name","arguments":{}}],"reason":"short reason"}\n\n'
        "Rules:\n"
        "- Use only listed tools.\n"
        f"- Use at most {PI_TOOL_LOOP_MAX_CALLS} tool calls.\n"
        "- Prefer get_weekly_summary for weekly orientation.\n"
        "- Prefer get_artifact_status for Brief/Atlas/Radar freshness or stale/missing artifact questions.\n"
        "- Prefer search_telegram_archive when the operator asks to find original Telegram posts, archive evidence, source links, reacted posts, or channel/date-filtered posts.\n"
        "- Prefer search_intelligence_items for specific questions.\n"
        "- Prefer get_mvp_radar_status for MVP/product opportunity questions.\n"
        "- Prefer get_strategy_reviewer_notes for improvement/Codex/process questions.\n"
        "- Prefer get_action_statuses or get_project_actions for what-to-do questions.\n"
        "- Never request mutation/code/config/Codex execution tools.\n\n"
        f"Question: {question}\n\n"
        f"Available tools:\n{json.dumps(tool_descriptions, ensure_ascii=False)}"
    )
    try:
        planned = llm_client.complete_json(
            prompt=prompt,
            system=PI_ASSISTANT_SYSTEM_PROMPT,
            category="pi_chat",
        )
    except Exception:
        return {
            "tool_calls": list(deterministic_route["tool_calls"]),
            "reason": "LLM planning unavailable; deterministic fallback.",
            "planner": "deterministic",
            "model_call_attempted": True,
        }
    if isinstance(planned, dict):
        planned.setdefault("planner", "llm")
        planned["model_call_attempted"] = True
        return planned
    return {
        "tool_calls": list(deterministic_route["tool_calls"]),
        "reason": "LLM plan was not an object.",
        "planner": "deterministic",
        "model_call_attempted": True,
    }


def _synthesize_answer(
    question: str,
    *,
    executed_calls: list[dict],
    evidence: dict,
    llm_client: type[LLMClient],
) -> str:
    compact_calls = _truncate_text(json.dumps(executed_calls, ensure_ascii=False, indent=2), MAX_FINAL_CONTEXT_CHARS)
    prompt = (
        "Answer the operator's Telegram message as Hermes.\n\n"
        "Rules:\n"
        "- Answer in the same language as the operator.\n"
        "- Be concise and practical.\n"
        "- Use only the provided read-only tool results for source-grounded claims.\n"
        "- If evidence is missing, say what is missing instead of guessing.\n"
        "- Distinguish source-backed facts, interpretation, model background, market/business context, and matched external evidence.\n"
        "- Market/business context is context_only and cannot satisfy MVP Radar gates.\n"
        "- Missing or stale Radar never permits build/focused decisions.\n"
        "- Do not claim you changed code/config/profile/projects or ran Codex.\n"
        "- If the operator asks for feedback/voice, explain the confirmation flow.\n"
        "- Include source refs, atom ids, thread slugs, or artifact paths when useful.\n\n"
        f"Question:\n{question}\n\n"
        f"Tool results:\n{compact_calls}\n\n"
        f"Collected evidence:\n{json.dumps(evidence, ensure_ascii=False)}"
    )
    try:
        answer = llm_client.complete(
            prompt=prompt,
            system=PI_ASSISTANT_SYSTEM_PROMPT,
            max_tokens=900,
            category="pi_chat",
        ).strip()
    except Exception:
        return _fallback_answer(question, executed_calls=executed_calls, evidence=evidence)
    return answer or _fallback_answer(question, executed_calls=executed_calls, evidence=evidence)


def _fallback_tool_calls(question: str) -> list[dict]:
    return list(route_pi_intent(question)["tool_calls"])


def route_pi_intent(question: str) -> dict[str, object]:
    lowered = question.casefold()
    calls: list[dict[str, object]]
    intent = "general_memory"
    if any(term in lowered for term in ("external", "externally", "внешн", "проверь в интернете", "verify outside")):
        intent = "external_verification"
        calls = [
            {
                "name": "request_external_verification",
                "arguments": {
                    "question": question,
                    "reason": "archive evidence may be insufficient or time-sensitive",
                },
            }
        ]
    elif any(term in lowered for term in ("реакц", "reacted", "reaction", "marked by me", "отмеченн")):
        intent = "reaction_recall"
        calls = [
            {
                "name": "search_telegram_archive",
                "arguments": {"query": question, "filters": {"reacted_only": True}, "limit": 5},
            }
        ]
    elif any(term in lowered for term in ("которого нет", "несуществ", "no answer", "no-answer")):
        intent = "no_answer_probe"
        calls = [
            {"name": "search_telegram_archive", "arguments": {"query": question, "limit": 5}},
        ]
    elif any(term in lowered for term in ("сравни", "compare", "versus", " vs ")):
        intent = "comparison"
        calls = [
            {"name": "search_telegram_archive", "arguments": {"query": question, "limit": 8}},
            {"name": "search_intelligence_items", "arguments": {"query": question, "limit": 8}},
        ]
    elif any(term in lowered for term in ("кейс", "case", "пример", "examples")):
        intent = "case_search"
        calls = [
            {"name": "search_telegram_archive", "arguments": {"query": question, "limit": 8}},
            {"name": "search_intelligence_items", "arguments": {"query": question, "limit": 8}},
        ]
    elif any(term in lowered for term in ("новост", "fresh", "latest", "сегодня", "recent")):
        intent = "news_or_freshness"
        calls = [
            {"name": "search_telegram_archive", "arguments": {"query": question, "limit": 8}},
            {
                "name": "request_external_verification",
                "arguments": {
                    "question": question,
                    "reason": "freshness claims may require external verification",
                },
            },
        ]
    elif any(term in lowered for term in ("проект", "project", "примен", "apply", "life")):
        intent = "project_application"
        calls = [
            {"name": "get_project_actions", "arguments": {}},
            {"name": "search_telegram_archive", "arguments": {"query": question, "limit": 5}},
            {"name": "search_intelligence_items", "arguments": {"query": question, "limit": 5}},
        ]
    elif any(term in lowered for term in ("найди", "find", "архив", "archive", "telegram", "телеграм", "пост", "source", "ссылк")):
        intent = "exact_search"
        calls = [
            {"name": "search_telegram_archive", "arguments": {"query": question, "limit": 5}},
        ]
    elif any(term in lowered for term in ("artifact", "артефакт", "brief", "бриф", "atlas", "атлас", "stale", "устар", "missing", "пропал", "нет радара")):
        intent = "artifact_status"
        calls = [{"name": "get_artifact_status", "arguments": {}}]
    elif any(term in lowered for term in ("mvp", "радар", "opportunity", "startup")):
        intent = "radar_status"
        calls = [{"name": "get_mvp_radar_status", "arguments": {}}]
    elif any(term in lowered for term in ("кодекс", "codex", "стратег", "strategy", "улучш", "следующ")):
        intent = "strategy_notes"
        calls = [{"name": "get_strategy_reviewer_notes", "arguments": {}}]
    else:
        intent = "concept_search"
        calls = [
            {"name": "search_intelligence_items", "arguments": {"query": question, "limit": 5}},
            {"name": "search_telegram_archive", "arguments": {"query": question, "limit": 5}},
        ]
    return {
        "schema_version": "pi_intent_route.v1",
        "intent": intent,
        "tool_calls": calls[:PI_TOOL_LOOP_MAX_CALLS],
        "privacy_boundary": "bounded_read_only_no_raw_corpus",
    }


def _normalize_tool_calls(raw_calls: Any) -> list[dict]:
    if not isinstance(raw_calls, list):
        return []
    normalized = []
    for raw_call in raw_calls:
        if not isinstance(raw_call, Mapping):
            continue
        name = str(raw_call.get("name") or "").strip()
        arguments = raw_call.get("arguments")
        if not name:
            continue
        normalized.append({"name": name, "arguments": dict(arguments) if isinstance(arguments, Mapping) else {}})
    return normalized


def _compact_result(result: Mapping[str, Any]) -> dict:
    text = json.dumps(result, ensure_ascii=False)
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return dict(result)
    compact = {
        "status": result.get("status"),
        "tool_name": result.get("tool_name"),
        "evidence_status": result.get("evidence_status"),
        "evidence": result.get("evidence"),
        "message": result.get("message"),
        "result": result.get("result"),
    }
    compact_text = json.dumps(compact, ensure_ascii=False)
    if len(compact_text) <= MAX_TOOL_RESULT_CHARS:
        return compact
    compact["result"] = _truncate_text(str(compact.get("result") or ""), MAX_TOOL_RESULT_CHARS // 2)
    return compact


def _collect_chat_evidence(executed_calls: list[dict]) -> dict:
    source_refs: list[str] = []
    atom_ids: list[str | int] = []
    thread_slugs: list[str] = []
    artifact_paths: dict[str, str] = {}
    for call in executed_calls:
        evidence = (call.get("result") or {}).get("evidence") or {}
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


def _fallback_answer(question: str, *, executed_calls: list[dict], evidence: dict) -> str:
    del question
    lines = ["Hermes checked the curated PI tools."]
    for call in executed_calls[:4]:
        result = call.get("result") or {}
        status = result.get("status") or call.get("status")
        message = result.get("message") or ""
        lines.append(f"- {call.get('name')}: {status}. {message}".strip())
    refs = evidence.get("source_refs") or []
    atoms = evidence.get("atom_ids") or []
    artifacts = evidence.get("artifact_paths") or {}
    if refs:
        lines.append("Sources: " + ", ".join(str(ref) for ref in refs[:5]))
    if atoms:
        lines.append("Atoms: " + ", ".join(str(atom) for atom in atoms[:8]))
    if artifacts:
        lines.append("Artifacts: " + ", ".join(str(path) for path in artifacts.values()))
    if not refs and not atoms and not artifacts:
        lines.append("Evidence is missing or insufficient; I will not guess beyond available data.")
    return "\n".join(lines)


def validate_grounded_answer_contract(contract: Mapping[str, Any]) -> dict[str, object]:
    required_fields = {
        "schema_version",
        "direct_answer",
        "archive_support",
        "source_links",
        "uncertainty",
        "freshness_date_boundary",
        "model_background",
        "external_verification",
        "optional_next_action",
        "insufficient_evidence",
    }
    missing = sorted(field for field in required_fields if field not in contract)
    if missing:
        raise ValueError(f"grounded answer contract missing fields: {', '.join(missing)}")
    if contract.get("schema_version") != "grounded_answer_contract.v1":
        raise ValueError("grounded answer contract schema_version is invalid")
    if not isinstance(contract.get("source_links"), list):
        raise ValueError("grounded answer source_links must be a list")
    if not isinstance(contract.get("archive_support"), Mapping):
        raise ValueError("grounded answer archive_support must be an object")
    if not isinstance(contract.get("model_background"), Mapping):
        raise ValueError("grounded answer model_background must be an object")
    return dict(contract)


def _build_answer_contract(
    answer: str,
    *,
    executed_calls: list[dict],
    evidence: dict,
    trace: Mapping[str, Any],
) -> dict[str, object]:
    source_links = [str(ref) for ref in evidence.get("source_refs") or [] if str(ref).strip()]
    source_dates = _collect_source_dates(executed_calls)
    termination_reason = str(trace.get("termination_reason") or "")
    insufficient = bool(trace.get("insufficient_evidence")) or not source_links
    external_required = termination_reason == "needs_external_verification"
    contract = {
        "schema_version": "grounded_answer_contract.v1",
        "direct_answer": _first_answer_line(answer),
        "archive_support": {
            "status": "available" if source_links else "insufficient_evidence",
            "source_count": len(source_links),
            "claim_scope": "archive_supported" if source_links else "not_archive_supported",
        },
        "source_links": source_links[:10],
        "uncertainty": (
            "Archive evidence is bounded to returned sources."
            if source_links
            else "No sufficient archive evidence was returned."
        ),
        "freshness_date_boundary": {
            "max_source_date": max(source_dates) if source_dates else None,
            "source_date_count": len(source_dates),
        },
        "model_background": {
            "used": bool(not source_links and answer.strip()),
            "label": "background_not_archive_supported" if not source_links and answer.strip() else "not_used",
        },
        "external_verification": {
            "required": external_required,
            "reason": "fresh_or_external_claim" if external_required else None,
        },
        "optional_next_action": (
            "Approve external verification before treating this as current fact."
            if external_required
            else None
        ),
        "insufficient_evidence": insufficient,
    }
    return validate_grounded_answer_contract(contract)


def _build_answer_telemetry(
    *,
    planning_latency_ms: float,
    retrieval_latency_ms: float,
    generation_latency_ms: float,
    planning_model_calls: int,
    generation_model_calls: int,
    tool_call_count: int,
) -> dict[str, object]:
    return {
        "schema_version": "pi_answer_telemetry.v1",
        "planning": {
            "latency_ms": planning_latency_ms,
            "model_calls": planning_model_calls,
            "estimated_cost_usd": 0.0,
        },
        "retrieval": {
            "latency_ms": retrieval_latency_ms,
            "tool_calls": tool_call_count,
            "estimated_cost_usd": 0.0,
        },
        "generation": {
            "latency_ms": generation_latency_ms,
            "model_calls": generation_model_calls,
            "estimated_cost_usd": 0.0,
        },
        "privacy": {
            "raw_post_text_logged": False,
            "raw_tool_payload_logged": False,
            "provider_payload_logged": False,
        },
    }


def _collect_source_dates(executed_calls: list[dict]) -> list[str]:
    dates: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            posted_at = item.get("posted_at")
            if isinstance(posted_at, str) and posted_at.strip():
                dates.append(posted_at.strip())
            for value in item.values():
                visit(value)
            return
        if isinstance(item, list):
            for child in item:
                visit(child)

    for call in executed_calls:
        visit(call.get("result"))
    return _unique(dates)


def _first_answer_line(answer: str) -> str:
    for line in str(answer or "").splitlines():
        clean = line.strip()
        if clean:
            return clean[:1000]
    return ""


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _build_assistant_trace(
    *,
    route: Mapping[str, Any],
    planner: str,
    executed_calls: list[dict],
    evidence: dict,
) -> dict[str, object]:
    termination_reason = _termination_reason(executed_calls, evidence)
    return {
        "schema_version": "pi_assistant_trace.v1",
        "intent": route.get("intent") or "unknown",
        "planner": planner,
        "tool_traces": [
            {
                "name": call.get("name"),
                "arguments": dict(call.get("arguments") or {}),
                "status": call.get("status"),
                "evidence_status": call.get("evidence_status"),
                "result_count": _trace_result_count(call),
                "privacy_boundary": "bounded_read_only_no_raw_corpus",
            }
            for call in executed_calls
        ],
        "termination_reason": termination_reason,
        "insufficient_evidence": termination_reason
        in {"insufficient_evidence", "needs_external_verification"},
        "privacy_boundary": {
            "raw_telegram_text_egress": False,
            "external_skill_used": False,
            "write_performed": False,
            "bounded_read_only_tools": True,
        },
    }


def _empty_trace(*, termination_reason: str) -> dict[str, object]:
    return {
        "schema_version": "pi_assistant_trace.v1",
        "intent": "invalid_request",
        "planner": "none",
        "tool_traces": [],
        "termination_reason": termination_reason,
        "insufficient_evidence": False,
        "privacy_boundary": {
            "raw_telegram_text_egress": False,
            "external_skill_used": False,
            "write_performed": False,
            "bounded_read_only_tools": True,
        },
    }


def _termination_reason(executed_calls: list[dict], evidence: dict) -> str:
    if not executed_calls:
        return "invalid_request"
    statuses = {str(call.get("status") or "") for call in executed_calls}
    if "needs_external_verification" in statuses:
        return "needs_external_verification"
    if statuses.intersection({"rejected", "missing", "invalid"}):
        return "tool_error_degraded"
    if any(evidence.get(key) for key in ("source_refs", "atom_ids", "thread_slugs", "artifact_paths")):
        return "answered_with_evidence"
    if statuses.intersection({"insufficient", "insufficient_evidence"}):
        return "insufficient_evidence"
    return "insufficient_evidence"


def _trace_result_count(call: Mapping[str, Any]) -> int:
    result = call.get("result")
    if not isinstance(result, Mapping):
        return 0
    payload = result.get("result")
    candidates = [payload, result]
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        for key in (
            "items",
            "results",
            "sections",
            "decision_brief",
            "claim_cards",
            "actions",
            "observed_personal_posts",
        ):
            value = candidate.get(key)
            if isinstance(value, list):
                return len(value)
    return 0


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n...[truncated]"


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
