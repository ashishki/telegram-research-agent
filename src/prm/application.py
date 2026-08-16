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
from prm.contracts import AssistantResult, OperatorRequest
from prm.presentation import render_payload, render_project_clarification
from prm.routing import decide_route
from prm.synthesis import synthesize_answer


class PersonalResearchAssistant:
    """Coordinate one side-effect-free PRM request lifecycle."""

    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings

    def answer(self, request: OperatorRequest) -> AssistantResult:
        route = decide_route(request.query, requested_mode=request.mode, explicit_project=request.project_name)
        if route.mode == "project_clarify":
            return AssistantResult(
                interaction_id="",
                status="clarify",
                mode="project_clarify",
                text=render_project_clarification(),
                route=route.to_dict(),
            )
        if route.mode == "clarify":
            return AssistantResult(
                interaction_id="",
                status="clarify",
                mode="clarify",
                text="Уточни: найти материалы в архиве, собрать бриф или задать свободный вопрос?",
                route=route.to_dict(),
            )

        context = build_operator_context(
            chat_id=request.chat_id,
            query=request.query,
            requested_mode=route.mode,
            input_kind=request.input_kind,
            project_name=route.project_name,
        )
        validate_operator_context(context)

        if route.mode == "chat":
            return self._chat(request, context.to_dict(), route.to_dict())

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
        payload = answer_memory_research(
            request.query,
            archive_query=route.retrieval_query,
            project_name=route.project_name,
            settings=self.settings,
            limit=5 if route.mode == "brief" else 4,
            budget=budget,
            operator_context=context.to_dict(),
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
        )
        final_text = synthesized or deterministic
        gate = _mapping(payload.get("answer_gate"))
        verification = verify_answer_against_evidence(
            final_text,
            evidence_items,
            current_fact_required=bool(gate.get("external_verification_required"))
            and not bool(gate.get("current_claim_allowed", True)),
            project_name=str(_mapping(payload.get("project_fit")).get("project_name") or ""),
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
            operator_context=context.to_dict(),
            final_answer_verification={
                "claim_count": int(verification.get("claim_count") or 0),
                "metrics": verification.get("metrics") or {},
                "summary": claim_ledger_public_summary(verification),
            },
            route=route.to_dict(),
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


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().casefold() in {"1", "true", "yes", "approved"}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
