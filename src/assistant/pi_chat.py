from __future__ import annotations

import json
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
            "message": "Question is empty.",
        }

    active_facade = facade or PersonalIntelligenceFacade(settings=settings)
    catalog = build_pi_tool_catalog()
    plan = _plan_tool_calls(clean_question, catalog=catalog, llm_client=llm_client)
    tool_calls = _normalize_tool_calls(plan.get("tool_calls") if isinstance(plan, Mapping) else None)

    if not tool_calls:
        tool_calls = _fallback_tool_calls(clean_question)

    executed_calls: list[dict] = []
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

    evidence = _collect_chat_evidence(executed_calls)
    answer = _synthesize_answer(
        clean_question,
        executed_calls=executed_calls,
        evidence=evidence,
        llm_client=llm_client,
    )
    return {
        "status": "ok" if executed_calls else "empty",
        "answer": answer,
        "tool_calls": [{"name": call["name"], "arguments": call["arguments"]} for call in executed_calls],
        "tool_results": executed_calls,
        "evidence": evidence,
        "message": "Hermes PI chat answered through bounded read-only tools.",
    }


def _plan_tool_calls(question: str, *, catalog: Mapping[str, Any], llm_client: type[LLMClient]) -> dict:
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
        return {"tool_calls": _fallback_tool_calls(question), "reason": "LLM planning unavailable; deterministic fallback."}
    if isinstance(planned, dict):
        return planned
    return {"tool_calls": _fallback_tool_calls(question), "reason": "LLM plan was not an object."}


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
    lowered = question.casefold()
    calls: list[dict] = []
    if any(term in lowered for term in ("artifact", "артефакт", "brief", "бриф", "atlas", "атлас", "stale", "устар", "missing", "пропал", "нет радара")):
        calls.append({"name": "get_artifact_status", "arguments": {}})
    if any(term in lowered for term in ("mvp", "радар", "продукт", "opportunity", "startup")):
        calls.append({"name": "get_mvp_radar_status", "arguments": {}})
    if any(term in lowered for term in ("кодекс", "codex", "стратег", "strategy", "улучш", "следующ")):
        calls.append({"name": "get_strategy_reviewer_notes", "arguments": {}})
    if any(term in lowered for term in ("делать", "действ", "action", "задач", "проект")):
        calls.append({"name": "get_action_statuses", "arguments": {}})
        calls.append({"name": "get_project_actions", "arguments": {}})
    calls.append({"name": "search_intelligence_items", "arguments": {"query": question, "limit": 5}})
    if len(calls) < 2:
        calls.insert(0, {"name": "get_weekly_summary", "arguments": {}})
    return calls[:PI_TOOL_LOOP_MAX_CALLS]


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
        lines.append("Curated evidence is missing or insufficient; I will not guess beyond available data.")
    return "\n".join(lines)


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
