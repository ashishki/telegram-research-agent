"""Single application service for Telegram, CLI and evaluation interfaces."""

from __future__ import annotations

import os
import re
import hashlib
import uuid
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
from llm.client import LLMClient, LLMOutcomeUnknown, suppress_usage_recording
from prm.conversation import (
    GLOBAL_CONVERSATIONS,
    ConversationState,
    ConversationStore,
    assemble_safe_dialogue_context,
    classify_turn,
)
from prm.archive_contract import ARCHIVE_RESPONSE_INTENTS, apply_archive_response_contract
from prm.contracts import AssistantResult, OperatorRequest
from prm.presentation import render_payload, render_project_clarification
from prm.research_planner import plan_archive_evidence
from prm.research_facade import build_research_facade
from prm.request_plan import build_request_plan
from prm.routing import decide_route
from prm.synthesis import synthesize_archive_response


class PersonalResearchAssistant:
    """Coordinate one bounded PRM request lifecycle."""

    def __init__(
        self,
        *,
        settings: Settings,
        conversations: ConversationStore | None = None,
        llm_client: type[LLMClient] = LLMClient,
    ) -> None:
        self.settings = settings
        self.conversations = conversations or GLOBAL_CONVERSATIONS
        self.llm_client = llm_client

    def answer(self, request: OperatorRequest) -> AssistantResult:
        conversation = self.conversations.active_or_start(request.chat_id)
        turn = classify_turn(request.query, conversation)
        if turn.kind == "cancel":
            self.conversations.cancel(request.chat_id)
            return self._conversation_control_result(
                request,
                conversation,
                status="cancelled",
                text="Текущая задача отменена. Новое сообщение начнёт отдельную тему; никакое подтверждение не будет использовано.",
            )
        if turn.kind == "reset_topic":
            self.conversations.begin_new_topic(request.chat_id)
            return self._conversation_control_result(
                request,
                conversation,
                status="topic_reset",
                text="Начинаем новую тему. Предыдущий ответ и подтверждения не будут использованы.",
            )
        if turn.kind == "plain_yes":
            resolution = self.conversations.resolve_plain_yes(
                request.chat_id,
                actor_id=request.actor_id,
                owner_chat_id=request.owner_chat_id,
                # PA-13 will provide the authoritative proposal-version loader.
                # Until then a text confirmation must fail closed.
                proposal_versions=None,
            )
            return self._conversation_control_result(
                request,
                conversation,
                status="confirmation_unavailable",
                text=(
                    "Подтверждение сейчас недоступно: нужен один текущий видимый предпросмотр с "
                    "точной версией действия. Я не выберу действие по прошлой теме."
                    if resolution.status != "resolved"
                    else "Подтверждение выбрано; выполнение появится только после отдельного защищённого шага."
                ),
                confirmation_status=resolution.status,
            )
        if turn.kind == "next_step" and turn.response_ref:
            response = next((item for item in conversation.object_refs if item.response_ref == turn.response_ref), None)
            if response is not None:
                topic = conversation.topic or "этой теме"
                return self._conversation_control_result(
                    request,
                    conversation,
                    status="ok",
                    text=(
                        f"Следующий шаг: уточни один термин, источник или период по теме {topic}; "
                        "предыдущий ответ не запускает действие сам по себе."
                    ),
                    response_ref=response.response_ref,
                )
        if turn.kind == "shorten" and turn.response_ref:
            response = next((item for item in conversation.object_refs if item.response_ref == turn.response_ref), None)
            if response is not None:
                shortened = _shorten_visible_response(response.display_text)
                result = self._conversation_control_result(
                    request,
                    conversation,
                    status="ok",
                    text=shortened,
                    response_ref=turn.response_ref,
                )
                return self._remember_conversation_result(request, result, topic=conversation.topic)
        if turn.kind == "select_item" and turn.response_ref and turn.item_ref:
            response = next((item for item in conversation.object_refs if item.response_ref == turn.response_ref), None)
            if response is not None and turn.item_ref in response.item_refs:
                index = response.item_refs.index(turn.item_ref)
                result = self._conversation_control_result(
                    request,
                    conversation,
                    status="ok",
                    text=response.item_texts[index],
                    response_ref=turn.item_ref,
                )
                return self._remember_conversation_result(request, result, topic=conversation.topic)
        # All ordinary text starts an independent topic for confirmation
        # purposes.  Read-only archive follow-up composition remains separate
        # transport compatibility and cannot retain action authority.
        conversation = self.conversations.begin_new_topic(request.chat_id)
        route = decide_route(request.query, requested_mode=request.mode, explicit_project=request.project_name)
        route_payload = route.to_dict()
        request_plan = build_request_plan(request.query, route_payload)
        if route.mode == "project_clarify":
            return self._remember_conversation_result(request, AssistantResult(
                interaction_id="",
                status="clarify",
                mode="project_clarify",
                text=render_project_clarification(),
                route=route_payload,
            ), topic="")
        if route.mode == "clarify":
            return self._remember_conversation_result(request, AssistantResult(
                interaction_id="",
                status="clarify",
                mode="clarify",
                text="Уточни: найти материалы в архиве, собрать бриф или задать свободный вопрос?",
                route=route_payload,
            ), topic="")
        if route.primary_intent == "memory_action":
            return self._remember_conversation_result(
                request,
                self._memory_action_guidance(request, route_payload),
                topic="",
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
            return self._remember_conversation_result(
                request,
                self._chat(request, context_payload, route_payload, conversation=conversation),
                topic="general conversation",
            )

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
            (
                str(item.get("source_url") or ""),
                str(
                    item.get("archive_document_id")
                    or item.get("post_archive_document_id")
                    or item.get("post_id")
                    or item.get("source_url")
                    or ""
                ),
            )
            for item in _mapping(payload.get("archive_evidence")).get("items") or []
            if isinstance(item, Mapping)
            and str(
                item.get("archive_document_id")
                or item.get("post_archive_document_id")
                or item.get("post_id")
                or item.get("source_url")
                or ""
            )
        }
        evidence_items = [
            {
                **dict(item),
                "local_archive_provenance": (
                    str(item.get("source_url") or ""), str(item.get("evidence_id") or ""),
                ) in local_archive_evidence,
            }
            for item in _mapping(payload.get("evidence_quality")).get("items") or []
            if isinstance(item, Mapping)
        ]
        selected_archive_evidence = _selected_archive_evidence_items(
            evidence_items,
            archive_contract=_mapping(payload.get("archive_contract")),
        )
        final_text = deterministic
        gate = _mapping(payload.get("answer_gate"))
        if route.primary_intent in ARCHIVE_RESPONSE_INTENTS and not bool(payload.get("mixed_current_boundary")):
            synthesis = synthesize_archive_response(
                payload,
                question=request.query,
                evidence_items=evidence_items,
                access=request.archive_synthesis_access,
            )
        else:
            synthesis = None
        if synthesis is not None and synthesis.text is not None:
            final_text = synthesis.text
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
        archive_synthesis_verified = synthesis is not None and synthesis.status == "generated_verified" and synthesis.text is not None
        publication_allowed = _final_answer_publication_allowed(
            verification,
            gate,
            response_contract_id=str(payload.get("response_contract_id") or route.response_contract_id),
            archive_source_bound=archive_synthesis_verified,
        )
        final_publication_allowed = publication_allowed
        if not publication_allowed:
            empty_next_step = _empty_evidence_next_step(route_payload)
            # Preserve a useful answer without presenting unchecked synthesis as
            # fact.  This path is local-only and shows the selected excerpts
            # with their actual source URLs.
            final_text = _render_verified_evidence_fallback(
                selected_archive_evidence,
                boundary=str(payload.get("mixed_current_boundary") or ""),
                local_only=bool(payload.get("mixed_current_boundary")),
                empty_next_step=empty_next_step,
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
                final_text = _render_terminal_empty_answer(empty_next_step)
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
                "reason": (
                    "archive_source_bound_verified"
                    if final_publication_allowed and archive_synthesis_verified
                    else "verified"
                    if final_publication_allowed
                    else "final_claim_verification_incomplete_or_unsupported"
                ),
            },
            "retrieval_generation_measurement": _retrieval_generation_measurement(payload, synthesis=synthesis),
            "archive_synthesis_verification": {
                "status": str(synthesis.status) if synthesis is not None else "not_attempted",
                "method": "exact_selected_span_with_bounded_paraphrase.v1" if archive_synthesis_verified else "not_published",
                "published": archive_synthesis_verified and final_publication_allowed,
            },
        }
        return self._remember_conversation_result(request, AssistantResult(
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
        ), topic=str(route_payload.get("retrieval_query") or request.query))

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

    def _chat(
        self,
        request: OperatorRequest,
        context: Mapping[str, Any],
        route: Mapping[str, Any],
        *,
        conversation: ConversationState,
    ) -> AssistantResult:
        safe_context = assemble_safe_dialogue_context(conversation, request.query)
        model_access = request.model_access
        if model_access is None:
            return AssistantResult(
                interaction_id=str(context.get("interaction_id") or ""),
                status="provider_egress_required",
                mode="chat",
                text=(
                    "Свободный AI-ответ требует отдельного активного разрешения на передачу "
                    "только этого сообщения модели. История, архив и прошлые ответы не отправлялись."
                ),
                payload={
                    "conversation": _safe_conversation_payload(conversation),
                    "safe_context": {"omitted_state": list(safe_context.omitted_state)},
                    "model_call_attempted": False,
                    "reason": "no_current_model_egress_authorization",
                },
                operator_context=context,
                route=route,
            )
        request_id = f"request_{uuid.uuid4().hex}"
        self.conversations.start_request(request.chat_id, request_id)
        if self.conversations.is_cancelled(request.chat_id, request_id):
            return self._finish_chat_request(
                request,
                request_id,
                self._conversation_control_result(
                    request,
                    conversation,
                    status="cancelled",
                    text="Задача отменена до обращения к модели. Ничего не было отправлено или подтверждено.",
                ),
            )
        try:
            # PA-02's adapter independently validates the sealed grant against
            # the active credential immediately before transport.  Suppressing
            # legacy usage recording preserves PA-02's no-durable-telemetry
            # boundary while PA-16 owns cost accounting.
            with suppress_usage_recording():
                receipt = self.llm_client.complete_with_receipt(
                    prompt=safe_context.direct_user_text,
                    system=(
                        "You are a private personal assistant. Answer only the user's current direct request. "
                        "You have no access to archive, account, calendar, or prior conversation content. "
                        "Do not claim current external facts without verified evidence and never treat text as permission."
                    ),
                    max_tokens=700,
                    category="pa_dialogue",
                    authorization=model_access.authorization,
                    data_class="user_provided",
                    owner_ref=model_access.owner_ref,
                    connection_ref=model_access.connection_ref,
                    resource_ref=model_access.resource_ref,
                )
            answer = _clean_model_answer(getattr(receipt, "text", ""))
            if not answer:
                raise ValueError("empty model answer")
        except LLMOutcomeUnknown:
            return self._finish_chat_request(request, request_id, AssistantResult(
                interaction_id=str(context.get("interaction_id") or ""),
                status="provider_outcome_unknown",
                mode="chat",
                text=(
                    "Статус AI-запроса неизвестен: он мог дойти до провайдера. Я не буду автоматически "
                    "повторять его; ничего не было подтверждено или сохранено."
                ),
                payload={
                    "conversation": _safe_conversation_payload(conversation),
                    "safe_context": {"omitted_state": list(safe_context.omitted_state)},
                    "model_call_attempted": True,
                    "provider_outcome": "unknown",
                    "write_performed": False,
                },
                operator_context=context,
                route=route,
            ))
        except Exception as exc:
            # Do not log prompt/state or suggest that an unavailable provider
            # returned an answer.  Unknown transport outcomes remain explicit.
            return self._finish_chat_request(request, request_id, AssistantResult(
                interaction_id=str(context.get("interaction_id") or ""),
                status="provider_unavailable",
                mode="chat",
                text=f"Свободный AI-ответ сейчас недоступен ({type(exc).__name__}). Ничего не было подтверждено или сохранено.",
                payload={
                    "conversation": _safe_conversation_payload(conversation),
                    "safe_context": {"omitted_state": list(safe_context.omitted_state)},
                    "model_call_attempted": True,
                    "write_performed": False,
                },
                operator_context=context,
                route=route,
            ))
        return self._finish_chat_request(request, request_id, AssistantResult(
            interaction_id=str(context.get("interaction_id") or ""),
            status="ok",
            mode="chat",
            text=answer,
            payload={
                "conversation": _safe_conversation_payload(conversation),
                "safe_context": {"omitted_state": list(safe_context.omitted_state)},
                "model_call_attempted": True,
                "write_performed": False,
            },
            operator_context=context,
            route=route,
        ))

    def cancel(self, request_id: str) -> bool:
        """Cancel one unambiguous ephemeral PA-03 request by its opaque ID."""

        return self.conversations.cancel_request(request_id) is not None

    def _finish_chat_request(
        self,
        request: OperatorRequest,
        request_id: str,
        result: AssistantResult,
    ) -> AssistantResult:
        cancelled = self.conversations.is_cancelled(request.chat_id, request_id)
        state = self.conversations.finish_request(request.chat_id, request_id)
        if cancelled:
            payload = {
                **dict(result.payload),
                "request_id": request_id,
                "cancelled": True,
                "conversation": _safe_conversation_payload(state) if state is not None else {},
            }
            return AssistantResult(
                interaction_id=result.interaction_id,
                status="cancelled_after_model_boundary" if bool(result.payload.get("model_call_attempted")) else "cancelled",
                mode=result.mode,
                text=(
                    "Задача отменена. Результат модели не будет использован; никакое действие не подтверждено или сохранено."
                ),
                payload=payload,
                operator_context=result.operator_context,
                final_answer_verification=result.final_answer_verification,
                route=result.route,
            )
        payload = {**dict(result.payload), "request_id": request_id}
        return AssistantResult(
            interaction_id=result.interaction_id,
            status=result.status,
            mode=result.mode,
            text=result.text,
            payload=payload,
            operator_context=result.operator_context,
            final_answer_verification=result.final_answer_verification,
            route=result.route,
        )

    def _conversation_control_result(
        self,
        request: OperatorRequest,
        conversation: ConversationState,
        *,
        status: str,
        text: str,
        response_ref: str | None = None,
        confirmation_status: str | None = None,
    ) -> AssistantResult:
        payload: dict[str, Any] = {
            "conversation": _safe_conversation_payload(conversation),
            "write_performed": False,
            "model_call_attempted": False,
        }
        if response_ref is not None:
            payload["response_ref"] = response_ref
        if confirmation_status is not None:
            payload["confirmation_status"] = confirmation_status
        return AssistantResult(
            interaction_id="",
            status=status,
            mode="chat",
            text=text,
            payload=payload,
            route={"mode": "chat", "primary_intent": "freeform_chat", "conversation_control": status},
        )

    def _remember_conversation_result(
        self,
        request: OperatorRequest,
        result: AssistantResult,
        *,
        topic: str,
    ) -> AssistantResult:
        # Control responses must not replace the object that a user was trying
        # to refer to; a fresh visible result does replace it and clears any
        # previous confirmation reference.
        if result.status in {"cancelled", "confirmation_unavailable"}:
            return result
        state = self.conversations.record_response(request.chat_id, text=result.text, topic=topic)
        payload = {**dict(result.payload), "conversation": _safe_conversation_payload(state)}
        return AssistantResult(
            interaction_id=result.interaction_id,
            status=result.status,
            mode=result.mode,
            text=result.text,
            payload=payload,
            operator_context=result.operator_context,
            final_answer_verification=result.final_answer_verification,
            route=result.route,
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


def _selected_archive_evidence_items(
    evidence_items: Sequence[Mapping[str, Any]],
    *,
    archive_contract: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    """Keep fallback excerpts within the immutable archive response contract.

    ``evidence_quality`` can contain diagnostics or locally retrieved candidates
    which were deliberately excluded from the direct/partial/adjacent archive
    contract.  They must neither reach the synthesis provider nor reappear
    after that provider's output is rejected.
    """

    selected = {
        (str(finding.get("evidence_id") or "").strip(), str(finding.get("source_url") or "").strip())
        for field in ("direct_findings", "partial_findings", "adjacent_findings")
        for finding in archive_contract.get(field) or ()
        if isinstance(finding, Mapping)
        if str(finding.get("evidence_id") or "").strip() and str(finding.get("source_url") or "").strip()
    }
    return [
        item
        for item in evidence_items
        if item.get("local_archive_provenance") is True
        and (str(item.get("evidence_id") or "").strip(), str(item.get("source_url") or "").strip()) in selected
    ]


def _retrieval_generation_measurement(payload: Mapping[str, Any], *, synthesis: Any | None) -> dict[str, Any]:
    """Expose bounded retrieval/generation facts without recording source text."""

    archive = _mapping(payload.get("archive_evidence"))
    receipt = _mapping(payload.get("receipt"))
    selected = [item for item in archive.get("items") or [] if isinstance(item, Mapping)]
    retrieval = {
        "status": str(archive.get("status") or "unknown"),
        "retrieval_mode": str(archive.get("retrieval_mode") or _mapping(receipt.get("retrieval_policy")).get("mode") or "unknown"),
        "candidate_count": len([item for item in payload.get("archive_candidate_pool") or [] if isinstance(item, Mapping)]),
        "selected_source_count": len(selected),
        "attempted_query_count": len([item for item in archive.get("attempted_queries") or [] if isinstance(item, Mapping)]),
    }
    if synthesis is None:
        generation: dict[str, Any] = {
            "status": "skipped_current_or_non_archive_boundary",
            "provider_egress_attempted": False,
            "context_egress_attempted": False,
        }
    else:
        generation = {"status": str(synthesis.status), **dict(synthesis.measurement)}
    return {
        "schema_version": "prm_retrieval_generation_measurement.v1",
        "retrieval": retrieval,
        "generation": generation,
    }


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
    verification: Mapping[str, Any], gate: Mapping[str, Any], *, response_contract_id: str = "", archive_source_bound: bool = False
) -> bool:
    """Whether rendered factual text is safe to publish as an answer."""
    metrics = _mapping(verification.get("metrics"))
    if not bool(verification.get("verification_complete", True)):
        return False
    if int(metrics.get("current_fact_violations") or 0):
        return False
    if not archive_source_bound and float(metrics.get("unsupported_claim_rate") or 0.0) > 0.0:
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
    if archive_source_bound:
        # ``synthesize_archive_response`` already establishes a stricter
        # source-bound condition for generated archive claims. The generic
        # ledger remains in the payload as an independent lexical diagnostic;
        # it must not turn a checked safe paraphrase into an evidence fallback.
        return True
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
    evidence_items: list[Mapping[str, Any]],
    *,
    boundary: str = "",
    local_only: bool = False,
    empty_next_step: str = "",
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
        lines.extend(
            (
                "Прямых проверяемых находок в выбранной локальной выдаче нет.",
                f"Следующий шаг: {empty_next_step or 'уточни термин, источник или период; либо попроси показать частичные и смежные совпадения.'}",
            )
        )
    return "\n".join(lines)


def _empty_evidence_next_step(route: Mapping[str, Any]) -> str:
    intent = str(route.get("primary_intent") or "")
    mode = str(route.get("mode") or "")
    if intent == "writer_brief" or mode == "brief":
        return "уточни термин, источник или период; либо разреши частичные и смежные материалы как фон для осторожного брифа."
    if intent in {"project_mapping", "decision_support"}:
        return "уточни термин или период; либо попроси показать частичные и смежные материалы, прежде чем связывать вывод с проектом."
    if intent == "archive_lookup":
        return "назови один термин, канал или период; либо попроси показать частичные и смежные совпадения."
    return "уточни термин, источник или период; либо попроси показать частичные и смежные совпадения."


def _render_terminal_empty_answer(next_step: str) -> str:
    """Keep a no-evidence terminal answer useful without inventing a claim."""
    # Keep this as the verifier's established non-factual refusal shape: a
    # second imperative sentence would be classified as an unsupported claim.
    return f"Не удалось собрать проверяемый ответ: {next_step}"


def _safe_conversation_payload(state: ConversationState) -> dict[str, object]:
    """Expose only opaque state metadata to renderers/tests, never dialogue text."""

    return {
        "conversation_id": state.conversation_id,
        "summary_version": state.summary_version,
        "response_refs": [item.response_ref for item in state.object_refs],
        "has_current_confirmation": state.current_confirmation_ref is not None,
        "retention": "ephemeral_clear_on_restart",
    }


def _shorten_visible_response(text: str) -> str:
    """A local selected-object reduction that never re-egresses old model text."""

    clean = " ".join(str(text or "").split())
    if not clean:
        return "Для сокращения сначала нужен видимый ответ."
    for marker in (". ", "! ", "? ", "\n"):
        if marker in clean:
            return clean.split(marker, 1)[0].rstrip(".!? ") + "."
    return clean[:420].rstrip() + ("…" if len(clean) > 420 else "")


def _clean_model_answer(value: object) -> str:
    return " ".join(str(value or "").split())[:2_400]


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
            "Это предпросмотр из свободного продолжения диалога. Постоянная запись появится только после отдельного подтверждения; "
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
