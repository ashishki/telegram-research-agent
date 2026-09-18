"""Single application service for Telegram, CLI and evaluation interfaces."""

from __future__ import annotations

import os
import re
import hashlib
from typing import Any, Mapping, Sequence

from assistant.claim_ledger import claim_ledger_public_summary, verify_answer_against_evidence
from assistant.memory_research import MemoryResearchBudget, answer_memory_research
from assistant.operator_context import build_operator_context, validate_operator_context
from assistant.pi_chat import answer_pi_chat
from assistant.prm_chat_display import render_prm_chat_answer
from config.settings import Settings
from external_watch.delivery import render_on_demand_edition
from external_watch.editions import project_edition
from external_watch.selection import rank_edition_events
from prm.archive_contract import ARCHIVE_RESPONSE_INTENTS, apply_archive_response_contract
from prm.contracts import AssistantResult, OperatorRequest
from prm.presentation import render_payload, render_project_clarification
from prm.research_planner import plan_archive_evidence
from prm.research_facade import build_research_facade
from prm.request_plan import build_request_plan
from prm.routing import decide_route
from prm.synthesis import synthesize_answer


class PersonalResearchAssistant:
    """Coordinate one bounded PRM request lifecycle."""

    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings

    def answer(self, request: OperatorRequest) -> AssistantResult:
        route = decide_route(request.query, requested_mode=request.mode, explicit_project=request.project_name)
        route_payload = route.to_dict()
        request_plan = build_request_plan(request.query, route_payload)
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
        mixed_archive_current = route.archive_scope and route.external_verification_required
        payload = answer_memory_research(
            request.query,
            archive_query=route.retrieval_query,
            project_name=route.project_name if route.project_context_required else "",
            settings=self.settings,
            facade=facade,
            limit=8 if route.primary_intent == "archive_to_action" else (5 if route.mode == "brief" else 4),
            budget=budget,
            operator_context=context_payload,
            # Preserve a requested archive portion even when the same message
            # also asks for a current external fact which is unavailable.
            research_intent="archive_lookup" if mixed_archive_current else route.primary_intent,
        )
        payload = {
            **dict(payload),
            "question": request.query,
            "primary_intent": "archive_lookup" if mixed_archive_current else route.primary_intent,
            "response_contract_id": "archive_research.v2" if mixed_archive_current else route.response_contract_id,
            "route_decision": route_payload,
            "request_plan": request_plan,
            "primary_source_verification": request_plan["primary_source_fixture_verification"],
        }
        payload = _preserve_requested_project_identity(payload, route_payload)
        if route.primary_intent == "archive_to_action":
            # This PRM-SN goal permits no provider egress.  Do not call a
            # planner whose optional environment capability could reach one;
            # preserve the already local candidate ordering and expose the
            # restriction explicitly.
            payload = {
                **payload,
                "research_plan": {
                    "status": "local_planner_disabled",
                    "gap_check": _mapping(payload.get("research_gap_check")),
                    "provider_egress": False,
                },
            }
        payload = _apply_route_boundaries(payload, route_payload, mixed_archive_current=mixed_archive_current)
        if route.primary_intent in ARCHIVE_RESPONSE_INTENTS or mixed_archive_current:
            payload = apply_archive_response_contract(
                payload,
                question=request.query,
                route=route_payload,
            )

        deterministic = render_payload(payload, mode=route.mode)
        local_archive_evidence = {
            (str(item.get("source_url") or ""), str(item.get("snippet") or ""))
            for item in _mapping(payload.get("archive_evidence")).get("items") or []
            if isinstance(item, Mapping) and str(item.get("archive_document_id") or "")
        }
        evidence_items = [
            {
                **dict(item),
                "local_archive_provenance": (
                    str(item.get("source_url") or ""),
                    str(item.get("support_span") or item.get("snippet") or ""),
                ) in local_archive_evidence,
            }
            for item in _mapping(payload.get("evidence_quality")).get("items") or []
            if isinstance(item, Mapping)
        ]
        # No synthesis capability is invoked in this assigned local-only
        # implementation, regardless of environment flags.
        final_text = deterministic
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
        publication_allowed = _final_answer_publication_allowed(
            verification, gate, response_contract_id=str(payload.get("response_contract_id") or route.response_contract_id)
        )
        final_publication_allowed = publication_allowed
        if not publication_allowed:
            # Preserve a useful answer without presenting unchecked synthesis as
            # fact.  This path is local-only and shows the selected excerpts
            # with their actual source URLs.
            final_text = _render_verified_evidence_fallback(
                evidence_items,
                boundary=str(payload.get("mixed_current_boundary") or ""),
                local_only=bool(payload.get("mixed_current_boundary")),
            )
            verification = verify_answer_against_evidence(
                final_text,
                evidence_items,
                # The mixed fallback contains only attributed local archive
                # excerpts plus a current-fact boundary; it does not publish a
                # current claim and may remain useful while verification is
                # still required for that separate part.
                current_fact_required=_blocking_current_fact_gate(gate) and not bool(payload.get("mixed_current_boundary")),
                project_name="",
            )
            final_publication_allowed = (
                _mixed_archive_fallback_allowed(verification)
                if bool(payload.get("mixed_current_boundary"))
                else _final_answer_publication_allowed(verification, gate)
            )
            if not final_publication_allowed:
                final_text = "Не удалось собрать проверяемый источник-атрибутированный ответ. Уточни запрос или источник."
                verification = verify_answer_against_evidence(
                    final_text,
                    evidence_items,
                    current_fact_required=_blocking_current_fact_gate(gate),
                    project_name="",
                )
                final_publication_allowed = _final_answer_publication_allowed(verification, gate)
        payload = {
            **dict(payload),
            "rendered_final_answer": final_text,
            "rendered_final_answer_verification": verification,
            "final_answer_publication": {
                "allowed": final_publication_allowed,
                "fallback_used": not publication_allowed,
                "reason": "verified" if final_publication_allowed else "final_claim_verification_incomplete_or_unsupported",
            },
        }
        return AssistantResult(
            interaction_id=context.interaction_id,
            status=(
                "partial_needs_external_verification"
                if bool(payload.get("mixed_current_boundary"))
                else "needs_external_verification"
                if _blocking_current_fact_gate(gate)
                else str(payload.get("status") or "ok")
            ),
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

    def render_topic_edition(
        self,
        request: OperatorRequest,
        *,
        topic_id: str,
        items: Sequence[Mapping[str, Any]],
        window_start: str,
        window_end: str,
        checked_at: str,
        source_health: Mapping[str, str] | None = None,
        detail_event_id: str = "",
        prior_events: Sequence[Mapping[str, Any]] = (),
    ) -> AssistantResult:
        """Render caller-supplied, already-authorized items without fetching or sending.

        This is the application seam for an explicit topic-edition request.
        Collection, durable edition state, scheduling and Telegram transport are
        intentionally absent: those become separate, confirmation-gated work.
        """
        edition = project_edition(
            items,
            topic_id=topic_id,
            window_start=window_start,
            window_end=window_end,
            checked_at=checked_at,
            prior_events=prior_events,
        )
        if not bool(edition["window"]["valid"]):
            text = "Окно выпуска некорректно; новости не проверялись. Укажи начало и конец в ISO-времени."
            status = "invalid_edition_window"
        else:
            text = render_on_demand_edition(
                rank_edition_events(edition["events"]), source_health=source_health, detail_event_id=detail_event_id
            )
            status = "ok" if edition["events"] else "no_news_or_source_unavailable"
        return AssistantResult(
            interaction_id=hashlib.sha256(f"{request.chat_id}\x1f{request.query}\x1f{edition['edition_id']}".encode()).hexdigest()[:24],
            status=status,
            mode="brief",
            text=text,
            payload={
                "edition": edition,
                "source_health": dict(source_health or {}),
                "detail_event_id": detail_event_id,
                "write_performed": False,
                "automatic_job_created": False,
                "notification_sent": False,
            },
            operator_context={"input_kind": request.input_kind, "topic_id": topic_id, "ephemeral": True},
            route={"mode": "brief", "primary_intent": "topic_edition", "topic_id": topic_id},
        )

    def _chat(self, request: OperatorRequest, context: Mapping[str, Any], route: Mapping[str, Any]) -> AssistantResult:
        return AssistantResult(
            interaction_id=str(context.get("interaction_id") or ""),
            status="provider_egress_required",
            mode="chat",
            text="Свободный LLM-ответ отключён в этом режиме. Используй локальный архивный вопрос; внешний режим требует отдельного утверждённого capability.",
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


def _apply_route_boundaries(
    payload: Mapping[str, Any], route: Mapping[str, Any], *, mixed_archive_current: bool = False
) -> dict[str, Any]:
    result = dict(payload)
    if bool(route.get("external_verification_required")):
        gate = _mapping(result.get("answer_gate"))
        result["answer_gate"] = {
            **gate,
            "status": "needs_external_verification",
            "reason": gate.get("reason") or "current_external_fact_required",
            "allow_answer": bool(mixed_archive_current),
            "current_claim_allowed": False,
            "no_answer_required": not mixed_archive_current,
            "external_verification_required": True,
        }
        if mixed_archive_current:
            result["mixed_current_boundary"] = (
                "Текущий внешний факт не подтверждён: внешняя проверка не запускалась; "
                "ниже — только архивная часть вопроса."
            )
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


def _final_answer_publication_allowed(
    verification: Mapping[str, Any], gate: Mapping[str, Any], *, response_contract_id: str = ""
) -> bool:
    """Whether rendered factual text is safe to publish as an answer."""
    metrics = _mapping(verification.get("metrics"))
    if not bool(verification.get("verification_complete", True)):
        return False
    if int(metrics.get("current_fact_violations") or 0):
        return False
    if float(metrics.get("unsupported_claim_rate") or 0.0) > 0.0:
        return False
    factual = [
        claim for claim in verification.get("claims") or []
        if isinstance(claim, Mapping) and str(claim.get("claim_type") or "") != "boundary"
    ]
    if _blocking_current_fact_gate(gate):
        # A useful current-fact boundary is publishable only when the verifier
        # actually extracted no factual claim.  Do not let the route bypass an
        # unsupported current value should a renderer regress.
        return not factual and any(
            isinstance(claim, Mapping) and str(claim.get("claim_type") or "") == "boundary"
            for claim in verification.get("claims") or []
        )
    return all(
        bool(claim.get("evidence_refs"))
        and all(str(status) == "supported" for status in _mapping(claim.get("citation_support")).values())
        for claim in factual
    )


def _mixed_archive_fallback_allowed(verification: Mapping[str, Any]) -> bool:
    """Allow cited local excerpts while preserving a separate current boundary."""

    metrics = _mapping(verification.get("metrics"))
    return (
        bool(verification.get("verification_complete", True))
        and float(metrics.get("unsupported_claim_rate") or 0.0) == 0.0
        and int(metrics.get("current_fact_violations") or 0) == 0
    )


def _render_verified_evidence_fallback(
    evidence_items: list[Mapping[str, Any]], *, boundary: str = "", local_only: bool = False
) -> str:
    lines = ["Я не публикую свободный пересказ: финальная проверка не подтвердила все фактические формулировки."]
    if boundary:
        lines.append(boundary)
    for item in evidence_items[:3]:
        span = " ".join(str(item.get("support_span") or item.get("snippet") or "").split())[:300]
        span = re.sub(r"[.!?。！？]+\s+", "; ", span)
        url = str(item.get("source_url") or "").strip()
        # Mixed-current fallback is an archive view: never make an arbitrary
        # HTTPS source survive as local evidence.
        # In mixed mode provenance is established only by the application’s
        # URL match against canonical archive evidence, not a caller-supplied
        # identifier on an otherwise external Telegram item.
        local_provenance = bool(item.get("local_archive_provenance"))
        if span and url.startswith("https://") and (not local_only or (url.startswith("https://t.me/") and local_provenance)):
            lines.append(f"- {span}\n  Источник: {url}")
    if len(lines) == 1:
        lines.append("Подходящего проверяемого фрагмента в выбранных источниках нет.")
    return "\n".join(lines)


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().casefold() in {"1", "true", "yes", "approved"}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _blocking_current_fact_gate(gate: Mapping[str, Any]) -> bool:
    return (
        bool(gate.get("external_verification_required"))
        and not bool(gate.get("current_claim_allowed", True))
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
