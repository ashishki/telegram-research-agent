"""Single application service for Telegram, CLI and evaluation interfaces."""

from __future__ import annotations

import os
import re
from typing import Any, Mapping

from assistant.claim_ledger import claim_ledger_public_summary, verify_answer_against_evidence
from assistant.memory_research import MemoryResearchBudget, answer_memory_research
from assistant.operator_context import build_operator_context, validate_operator_context
from assistant.pi_chat import answer_pi_chat
from assistant.prm_chat_display import render_prm_chat_answer
from config.settings import Settings
from prm.archive_contract import ARCHIVE_RESPONSE_INTENTS, apply_archive_response_contract
from prm.contracts import AssistantResult, OperatorRequest
from prm.presentation import render_payload, render_project_clarification
from prm.research_planner import plan_archive_evidence
from prm.research_facade import build_research_facade
from prm.routing import decide_route
from prm.synthesis import synthesize_answer


class PersonalResearchAssistant:
    """Coordinate one bounded PRM request lifecycle."""

    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings

    def answer(self, request: OperatorRequest) -> AssistantResult:
        route = decide_route(request.query, requested_mode=request.mode, explicit_project=request.project_name)
        route_payload = route.to_dict()
        if route.mode == "project_clarify":
            return AssistantResult(
                interaction_id="",
                status="clarify",
                mode="project_clarify",
                text=render_project_clarification(),
                route=route_payload,
            )
        if route.mode == "clarify":
            return AssistantResult(
                interaction_id="",
                status="clarify",
                mode="clarify",
                text="Уточни: найти материалы в архиве, собрать бриф или задать свободный вопрос?",
                route=route_payload,
            )
        if route.primary_intent == "memory_action":
            return self._memory_action_guidance(request, route_payload)

        context = build_operator_context(
            chat_id=request.chat_id,
            query=request.query,
            requested_mode=route.mode,
            input_kind=request.input_kind,
            project_name=route.project_name,
        )
        validate_operator_context(context)
        context_payload = {
            **context.to_dict(),
            "primary_intent": route.primary_intent,
            "response_contract_id": route.response_contract_id,
            "archive_scope": route.archive_scope,
        }

        if route.mode == "chat":
            return self._chat(request, context_payload, route_payload)

        budget = MemoryResearchBudget(
            max_tool_calls=4,
            max_archive_sources=8 if route.primary_intent == "archive_to_action" else (5 if route.mode == "brief" else 4),
            max_archive_candidates=32 if route.primary_intent == "archive_to_action" else 16,
            max_linked_sources=3,
            max_retries=0,
            timeout_seconds=30,
            max_prompt_chars=8000,
            max_model_calls=0,
            max_cost_usd=0.0,
            allow_open_browsing=False,
            allow_provider_egress=False,
            allow_vector_retrieval=_env_enabled("PRM_ARCHIVE_HYBRID_RETRIEVAL"),
            vector_index_path=os.environ.get("PRM_ARCHIVE_VECTOR_INDEX_PATH", "").strip(),
        )
        facade = build_research_facade(
            settings=self.settings,
            question=request.query,
            project_context_required=route.project_context_required,
        )
        payload = answer_memory_research(
            request.query,
            archive_query=route.retrieval_query,
            project_name=route.project_name if route.project_context_required else "",
            settings=self.settings,
            facade=facade,
            limit=8 if route.primary_intent == "archive_to_action" else (5 if route.mode == "brief" else 4),
            budget=budget,
            operator_context=context_payload,
            research_intent=route.primary_intent,
        )
        payload = {
            **dict(payload),
            "question": request.query,
            "primary_intent": route.primary_intent,
            "response_contract_id": route.response_contract_id,
            "route_decision": route_payload,
        }
        payload = _preserve_requested_project_identity(payload, route_payload)
        if route.primary_intent == "archive_to_action":
            candidates = payload.get("archive_candidate_pool") or _mapping(payload.get("archive_evidence")).get("items") or []
            plan = plan_archive_evidence(
                [item for item in candidates if isinstance(item, Mapping)],
                question=request.query,
            )
            payload = {
                **payload,
                "archive_evidence": {**_mapping(payload.get("archive_evidence")), "items": plan["items"]},
                "research_plan": {
                    **{key: value for key, value in plan.items() if key != "items"},
                    "gap_check": _mapping(payload.get("research_gap_check")),
                },
            }
        payload = _apply_route_boundaries(payload, route_payload)
        if route.primary_intent in ARCHIVE_RESPONSE_INTENTS:
            payload = apply_archive_response_contract(
                payload,
                question=request.query,
                route=route_payload,
            )

        deterministic = render_payload(payload, mode=route.mode)
        evidence_items = [
            item
            for item in _mapping(payload.get("evidence_quality")).get("items") or []
            if isinstance(item, Mapping)
        ]
        synthesized = synthesize_answer(
            payload,
            deterministic_fallback=deterministic,
            mode=route.mode,
            evidence_items=evidence_items,
            primary_intent=route.primary_intent,
            response_contract_id=route.response_contract_id,
        )
        final_text = synthesized or deterministic
        gate = _mapping(payload.get("answer_gate"))
        verification = verify_answer_against_evidence(
            final_text,
            evidence_items,
            current_fact_required=_blocking_current_fact_gate(gate),
            project_name=(
                str(_mapping(payload.get("project_fit")).get("project_name") or "")
                if route.project_context_required
                else ""
            ),
        )
        payload = {
            **dict(payload),
            "rendered_final_answer": final_text,
            "rendered_final_answer_verification": verification,
        }
        return AssistantResult(
            interaction_id=context.interaction_id,
            status=str(payload.get("status") or "ok"),
            mode=route.mode,  # type: ignore[arg-type]
            text=final_text,
            payload=payload,
            operator_context=context_payload,
            final_answer_verification={
                "claim_count": int(verification.get("claim_count") or 0),
                "metrics": verification.get("metrics") or {},
                "summary": claim_ledger_public_summary(verification),
            },
            route=route_payload,
        )

    def _chat(self, request: OperatorRequest, context: Mapping[str, Any], route: Mapping[str, Any]) -> AssistantResult:
        if not _env_enabled("PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS"):
            return AssistantResult(
                interaction_id=str(context.get("interaction_id") or ""),
                status="provider_egress_required",
                mode="chat",
                text="Свободный LLM-ответ отключён. Используй обычный вопрос для локального поиска или явно разреши provider egress.",
                operator_context=context,
                route=route,
            )
        result = answer_pi_chat(request.query, settings=self.settings)
        return AssistantResult(
            interaction_id=str(context.get("interaction_id") or ""),
            status=str(result.get("status") or "ok"),
            mode="chat",
            text=render_prm_chat_answer(result, mode="llm-approved"),
            payload=result,
            operator_context=context,
            route=route,
        )

    def _memory_action_guidance(
        self, request: OperatorRequest, route: Mapping[str, Any]
    ) -> AssistantResult:
        interaction_id = build_operator_context(
            chat_id=request.chat_id,
            query=request.query,
            requested_mode="research",
            input_kind=request.input_kind,
            project_name=str(route.get("project_name") or ""),
        ).interaction_id
        text = _render_memory_action_guidance(request.query)
        payload = {
            "status": "needs_confirmation",
            "question": request.query,
            "primary_intent": "memory_action",
            "response_contract_id": route.get("response_contract_id") or "archive_research.v2",
            "route_decision": dict(route),
            "answer_gate": {
                "allow_answer": False,
                "reason": "free_text_memory_action_requires_explicit_preview_confirmation",
            },
            "write_performed": False,
            "requires_confirmation": True,
            "profile_mutation_from_feedback": False,
        }
        return AssistantResult(
            interaction_id=interaction_id,
            status="needs_confirmation",
            mode="research",
            text=text,
            payload=payload,
            operator_context={
                "interaction_id": interaction_id,
                "input_kind": request.input_kind,
                "primary_intent": "memory_action",
                "response_contract_id": payload["response_contract_id"],
            },
            route=route,
        )


def _apply_route_boundaries(payload: Mapping[str, Any], route: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    if str(route.get("primary_intent") or "") == "current_fact_verification":
        gate = _mapping(result.get("answer_gate"))
        result["answer_gate"] = {
            **gate,
            "status": "needs_external_verification",
            "reason": gate.get("reason") or "current_external_fact_required",
            "allow_answer": False,
            "current_claim_allowed": False,
            "no_answer_required": True,
            "external_verification_required": True,
        }
    return result


def _preserve_requested_project_identity(payload: Mapping[str, Any], route: Mapping[str, Any]) -> dict[str, Any]:
    requested = str(route.get("project_name") or "").strip()
    if not requested or not bool(route.get("project_context_required")):
        return dict(payload)
    project = _mapping(payload.get("project_fit"))
    current = str(project.get("project_name") or "").strip()
    if current == requested:
        return dict(payload)
    guidance = (
        f"Проект {requested} указан пользователем. Я не подменяю его"
        + (f" на {current}" if current else "")
        + "; применимость ниже — только слабая архивная гипотеза."
    )
    return {
        **dict(payload),
        "project_fit": {
            **project,
            "project_name": requested,
            "relevance_label": "explicit_project_identity_preserved",
            "guidance": guidance,
            "inferred_project_name": current or None,
        },
    }


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().casefold() in {"1", "true", "yes", "approved"}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _blocking_current_fact_gate(gate: Mapping[str, Any]) -> bool:
    return (
        bool(gate.get("external_verification_required"))
        and not bool(gate.get("current_claim_allowed", True))
        and (bool(gate.get("no_answer_required")) or not bool(gate.get("allow_answer", False)))
    )


def _render_memory_action_guidance(query: str) -> str:
    lowered = str(query or "").casefold()
    wants_watch = any(marker in lowered for marker in ("следи", "наблюдай", "watch"))
    subject = _memory_action_subject(query)
    if wants_watch:
        title = "Черновик наблюдения"
        body = (
            "Буду следить только после явного подтверждения темы. "
            "UTD-профиль, источники и память автоматически не меняются."
        )
        next_step = "Чтобы сделать это точнее, задай тему как обычный вопрос или используй кнопку «Следить» под релевантным ответом."
    else:
        title = "Черновик заметки"
        body = (
            "Это preview из свободного follow-up. Durable запись появится только после отдельного подтверждения; "
            "профиль и память автоматически не меняются."
        )
        next_step = "Если это про последний ответ в Telegram, безопаснее использовать кнопку «Сохранить» под ним: там уже есть найденные источники."
    return "\n\n".join(
        [
            f"{title}: запись не создана.",
            "Что будет сохранено после подтверждения:\n"
            f"- Тема: {subject}\n"
            "- Основание: только этот текстовый запрос; без локальных источников это не считается подтверждённым фактом.",
            body,
            f"Следующий шаг: {next_step}",
        ]
    )


def _memory_action_subject(query: str) -> str:
    clean = " ".join(str(query or "").split())
    if not clean:
        return "не указана"
    match = re.search(
        r"В архиве по теме (?P<topic>.+?)\.(?: Для проекта (?P<project>.+?)\.)? Уточнение:",
        clean,
        flags=re.IGNORECASE,
    )
    if match is not None:
        topic = str(match.group("topic") or "").strip(" .:;")
        project = str(match.group("project") or "").strip(" .:;")
        if topic and project:
            return f"{topic} для проекта {project}"[:220]
        if topic:
            return topic[:220]
    return clean[:220]
