"""Single application service for Telegram, CLI and evaluation interfaces."""

from __future__ import annotations

import os
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
            max_archive_sources=5 if route.mode == "brief" else 4,
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
            limit=5 if route.mode == "brief" else 4,
            budget=budget,
            operator_context=context_payload,
        )
        payload = {
            **dict(payload),
            "question": request.query,
            "primary_intent": route.primary_intent,
            "response_contract_id": route.response_contract_id,
            "route_decision": route_payload,
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
            current_fact_required=bool(gate.get("external_verification_required"))
            and not bool(gate.get("current_claim_allowed", True)),
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


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().casefold() in {"1", "true", "yes", "approved"}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
