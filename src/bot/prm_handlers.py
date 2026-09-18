"""Focused active Telegram command surface for the PRM assistant."""

from __future__ import annotations

import logging
import os
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from assistant.prm_post_answer_actions import build_post_answer_actions, canonical_private_owner_id
from assistant.utd_profile import (
    is_utd_profile_intent,
    is_utd_question,
    render_utd_question_preview,
    start_utd_profile_onboarding,
)
from bot.telegram_delivery import _send_text_internal
from config.settings import Settings
from prm.application import PersonalResearchAssistant
from prm.capabilities import (
    AuthorizationDecision,
    AuthorizationRequest,
    CapabilityGrant,
    CapabilityRegistry,
    CapabilityDenied,
    ProviderPolicy,
    describe_current_capability_scope,
    require_authorized_operation,
    transport_purpose,
)
from prm.contracts import OperatorRequest

LOGGER = logging.getLogger(__name__)
PRM_SAFE_COMMANDS = frozenset(
    {
        "/start",
        "/help",
        "/auto",
        "/auto_voice",
        "/research",
        "/brief",
        "/chat",
        "/utd",
        "/status",
        "/privacy",
        "/refresh",
        "/reactions",
    }
)
_PRM_DIALOG_TTL = timedelta(minutes=20)
_MAX_PRM_DIALOGS = 200
_PRM_DIALOG_STATE: dict[str, dict[str, Any]] = {}
TELEGRAM_PROVIDER_REF = "provider_telegram"
RESULT_DELIVERY_CAPABILITY = "assistant.result_delivery"
RESULT_DELIVERY_DATA_CLASS = "private_archive"
UTD_DRAFT_CAPABILITY = "assistant.utd_draft"
LOCAL_PROVIDER_REF = "provider_local"
MAX_EPHEMERAL_REPLY_SENDS = 8


def send_message(
    token: str,
    chat_id: str,
    text: str,
    parse_mode: str | None = None,
    escape_markdown: bool = False,
    reply_markup: dict | None = None,
    delivery_authorization: AuthorizationDecision | None = None,
    actor_id: str | None = None,
    owner_chat_id: str | None = None,
) -> None:
    """Send PA-originated Telegram content only with a current grant.

    Calls from text, voice and UTD/callback paths share this single final-send
    boundary. An omitted decision denies before the Telegram transport rather
    than treating a token or private chat as authority.
    """

    del escape_markdown
    if not _require_prm_delivery_authorization(
        token=token,
        chat_id=chat_id,
        authorization=delivery_authorization,
        actor_id=actor_id,
        owner_chat_id=owner_chat_id,
    ):
        return
    try:
        kwargs: dict[str, object] = {
            "chat_id": chat_id,
            "text": text,
            "token": token,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        _send_text_internal(**kwargs)
    except Exception:
        LOGGER.warning("Failed to send PRM Telegram message")


def consume_private_reply_authorization(
    *,
    token: str,
    chat_id: str,
    authorization: AuthorizationDecision | None,
    actor_id: str | None,
    owner_chat_id: str | None,
) -> bool:
    """Consume the exact-private decision before any PA Telegram response."""

    return _require_prm_delivery_authorization(
        token=token,
        chat_id=chat_id,
        authorization=authorization,
        actor_id=actor_id,
        owner_chat_id=owner_chat_id,
    )


def dispatch_prm_command(
    chat_id: str,
    text: str,
    settings: Settings,
    *,
    actor_id: str | None = None,
    owner_chat_id: str | None = None,
    delivery_authorizations: Sequence[AuthorizationDecision] = (),
    utd_draft_authorization: AuthorizationDecision | None = None,
) -> None:
    command, args = _split_command(text)

    def send_private_reply(
        message: str,
        *,
        reply_markup: dict | None = None,
    ) -> None:
        """Use one turn-bound return-envelope decision for a short reply."""

        send_message(
            _token(),
            chat_id,
            message,
            reply_markup=reply_markup,
            delivery_authorization=_first_delivery_authorization(delivery_authorizations),
            actor_id=actor_id,
            owner_chat_id=owner_chat_id,
        )

    if command not in PRM_SAFE_COMMANDS:
        send_private_reply(
            "Эта команда не входит в активный интерфейс. Используй обычный вопрос или /help.",
        )
        return
    if command in {"/start", "/help"}:
        send_private_reply(_help_text())
        return
    if command == "/privacy":
        if actor_id != chat_id or owner_chat_id != chat_id:
            send_private_reply("Сведения о правах недоступны для этого чата.")
            return
        # PA-02 has no durable grant source yet. Rendering the empty registry is
        # intentional: it shows the exact default-deny scope without creating,
        # persisting, or pretending to revoke a connection.
        send_private_reply(describe_current_capability_scope(()))
        return
    if command == "/utd":
        _start_utd_profile(
            chat_id,
            settings=settings,
            seed_text=args,
            authorization=utd_draft_authorization,
            delivery_authorization=_first_delivery_authorization(delivery_authorizations),
            actor_id=actor_id,
            owner_chat_id=owner_chat_id,
        )
        return
    if command in {"/status", "/refresh", "/reactions"}:
        _delegate_safe_ops(command, chat_id, args, settings)
        return
    content_commands = {"/auto", "/auto_voice", "/research", "/brief", "/chat"}
    if command in content_commands and is_utd_profile_intent(args):
        _start_utd_profile(
            chat_id,
            settings=settings,
            seed_text=args,
            authorization=utd_draft_authorization,
            delivery_authorization=_first_delivery_authorization(delivery_authorizations),
            actor_id=actor_id,
            owner_chat_id=owner_chat_id,
        )
        return
    if (
        command in content_commands
        and is_utd_question(args)
        and not _explicit_archive_request(args)
    ):
        send_private_reply(render_utd_question_preview(args, db_path=settings.db_path))
        return

    mode = {"/research": "research", "/brief": "brief", "/chat": "chat"}.get(
        command, "auto"
    )
    input_kind = "voice_transcript" if command == "/auto_voice" else "text"
    if not args:
        send_private_reply("Напиши вопрос после команды или просто отправь обычное сообщение.")
        return
    if _is_memory_action_followup(args):
        send_private_reply(
            "Это действие недоступно. Отправь запрос заново, чтобы получить новую кнопку действия."
        )
        return
    dialog = _resolve_prm_dialog_query(chat_id, args, mode=mode)
    if dialog.get("kind") == "post_answer_action":
        send_private_reply(
            "Это действие недоступно. Отправь запрос заново, чтобы получить новую кнопку действия."
        )
        return
    if dialog.get("kind") == "short_next_step":
        send_private_reply(str(dialog.get("message") or "Следующий шаг не найден."))
        return

    effective_args = str(dialog.get("effective_query") or args)
    assistant = PersonalResearchAssistant(settings=settings)
    try:
        result = assistant.answer(
            OperatorRequest(
                query=effective_args,
                mode=mode,
                chat_id=chat_id,
                input_kind=input_kind,
            )
        )  # type: ignore[arg-type]
    except Exception as exc:
        LOGGER.warning("PRM request failed command=%s", command, exc_info=True)
        send_private_reply(f"Не смог обработать запрос: {type(exc).__name__}")
        return
    action_bundle = _post_answer_action_bundle(
        result.payload,
        settings=settings,
        chat_id=chat_id,
        actor_id=actor_id,
        owner_chat_id=owner_chat_id,
    )
    markup = action_bundle.get("reply_markup") if isinstance(action_bundle, Mapping) else None
    _send_chunks(
        chat_id,
        result.text,
        reply_markup=markup,
        actor_id=actor_id,
        owner_chat_id=owner_chat_id,
        delivery_authorizations=delivery_authorizations,
    )
    result_status = str(getattr(result, "status", "ok") or "ok")
    result_mode = str(getattr(result, "mode", mode) or mode)
    if result_status == "ok" and result_mode in {"research", "brief"}:
        result_route = _mapping(getattr(result, "route", {}))
        _remember_prm_dialog(
            chat_id,
            effective_args,
            mode=result_mode,
            # A prior topic belongs only to a composed follow-up.  For a new
            # explicit query, preserve the answered route so the next short
            # follow-up cannot resurrect Topic A over Topic B.
            topic=str(
                (dialog.get("previous_topic") if bool(dialog.get("used")) else "")
                or result_route.get("retrieval_query")
                or effective_args
            ),
            project_name=str(result_route.get("project_name") or _mapping(result.payload).get("project_name") or ""),
            action_context_id=str(action_bundle.get("context_id") or "") if isinstance(action_bundle, Mapping) else "",
                action_codes=[
                    str(code)
                    for code in ((action_bundle.get("action_codes") or []) if isinstance(action_bundle, Mapping) else [])
                    if str(code)
                ],
            last_answer=result.text,
            direct_count=_archive_result_count(result.payload, "direct_count"),
            partial_count=_archive_result_count(result.payload, "partial_count"),
            adjacent_count=_archive_result_count(result.payload, "adjacent_count"),
            current_fact_boundary=_current_fact_boundary(result.payload),
            direct_only_filter=bool(dialog.get("previous_direct_only")) or _is_direct_only_request(effective_args),
        )
    elif result_status == "needs_confirmation" and _mapping(getattr(result, "route", {})).get("primary_intent") == "memory_action":
        _remember_pending_prm_action(
            chat_id,
            action=_memory_action_code(args),
            message=result.text,
        )


def _start_utd_profile(
    chat_id: str,
    *,
    settings: Settings,
    seed_text: str,
    authorization: AuthorizationDecision | None = None,
    delivery_authorization: AuthorizationDecision | None = None,
    actor_id: str | None = None,
    owner_chat_id: str | None = None,
) -> None:
    if not _require_utd_draft_authorization(
        chat_id=chat_id,
        authorization=authorization,
        actor_id=actor_id,
        owner_chat_id=owner_chat_id,
    ):
        return
    result = start_utd_profile_onboarding(
        settings.db_path,
        chat_id=chat_id,
        seed_text=seed_text,
    )
    send_message(
        _token(),
        chat_id,
        str(result.get("message") or "UTD-черновик недоступен."),
        reply_markup=result.get("reply_markup"),
        delivery_authorization=delivery_authorization,
        actor_id=actor_id,
        owner_chat_id=owner_chat_id,
    )


def _delegate_safe_ops(command: str, chat_id: str, args: str, settings: Settings) -> None:
    # Legacy handlers own their historical Telegram sends and have no PA-02
    # capability boundary.  Do not route PA ingress through them until their
    # exact operations/receipts receive a separately scoped implementation.
    del command, chat_id, args, settings
    LOGGER.warning("PA operation denied before legacy dispatch")


def _post_answer_markup(
    payload: Mapping[str, Any], *, settings: Settings, chat_id: str
) -> dict | None:
    bundle = _post_answer_action_bundle(payload, settings=settings, chat_id=chat_id)
    return bundle.get("reply_markup") if isinstance(bundle, Mapping) else None


def _post_answer_action_bundle(
    payload: Mapping[str, Any], *, settings: Settings, chat_id: str,
    actor_id: str | None = None, owner_chat_id: str | None = None,
) -> dict[str, Any]:
    gate = _mapping(payload.get("answer_gate"))
    if not bool(gate.get("allow_answer", True)):
        return {}
    archive = _mapping(payload.get("archive_evidence"))
    source_refs = [
        str(item.get("source_url") or item.get("telegram_url") or "")
        for item in archive.get("items") or []
        if isinstance(item, Mapping)
    ]
    professional = _mapping(payload.get("professional_answer"))
    project = _mapping(payload.get("project_fit"))
    contract = _mapping(payload.get("archive_contract"))
    summary = _mapping(contract.get("result_summary"))
    direct_count = int(summary.get("direct_count") or 0)
    partial_count = int(summary.get("partial_count") or 0)
    return build_post_answer_actions(
        {
            "query": payload.get("question"),
            "direct_answer": payload.get("direct_answer"),
            "source_refs": source_refs,
            "project_name": project.get("project_name"),
            "answer_status": professional.get("answer_status")
            or contract.get("answer_status"),
            "source_count": len(source_refs),
            "direct_count": direct_count,
            "partial_count": partial_count,
            "relevance_established": direct_count + partial_count > 0,
            "primary_intent": payload.get("primary_intent"),
            "response_contract_id": payload.get("response_contract_id"),
            "selected_professional_lens": professional.get("professional_lens"),
            "primary_workflow": professional.get("primary_workflow"),
            "professional_answer": professional,
            "archive_evidence": archive,
            "retrieval_policy": _mapping(payload.get("retrieval_policy")),
            "evidence_quality": _mapping(payload.get("evidence_quality")),
            "claim_ledger": _mapping(payload.get("claim_ledger")),
            "receipt": _mapping(payload.get("receipt")),
            "privacy": _mapping(payload.get("privacy")),
            "route_decision": _mapping(payload.get("route_decision")),
            "archive_contract": contract,
            "render_mode": "telegram_archive_contract_v2" if contract else "telegram_legacy",
        },
        db_path=settings.db_path,
        chat_id=chat_id,
        actor_id=actor_id,
        owner_chat_id=owner_chat_id,
    )


def _send_chunks(
    chat_id: str,
    text: str,
    *,
    reply_markup: dict | None,
    actor_id: str | None = None,
    owner_chat_id: str | None = None,
    delivery_authorizations: Sequence[AuthorizationDecision] = (),
    limit: int = 3400,
) -> None:
    """Deliver a PA answer only through exact one-use Telegram grants.

    Omitted decisions deny the final Telegram side effect rather than treating
    a bot token or a private chat as consent. Runtime ingress supplies only a
    short-lived, exact private return envelope, one decision per transport
    chunk.
    """

    delivery_owner_ref = _private_delivery_owner_ref(chat_id, actor_id, owner_chat_id)
    chunks = _split_telegram_text(text, limit=limit)
    if delivery_owner_ref is None or len(delivery_authorizations) < len(chunks):
        LOGGER.warning("PRM result delivery denied before Telegram send")
        return
    decisions = iter(delivery_authorizations)
    for index, chunk in enumerate(chunks):
        decision = next(decisions, None)
        if decision is None:
            LOGGER.warning("PRM result delivery denied before Telegram send")
            return
        send_message(
            _token(),
            chat_id,
            chunk,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
            delivery_authorization=decision,
            actor_id=actor_id,
            owner_chat_id=owner_chat_id,
        )


def _private_delivery_owner_ref(
    chat_id: str,
    actor_id: str | None,
    owner_chat_id: str | None,
) -> str | None:
    """Map the authenticated private Telegram tuple to a policy owner ref."""

    values = tuple(canonical_private_owner_id(value) for value in (chat_id, actor_id, owner_chat_id))
    if any(value is None for value in values) or len(set(values)) != 1:
        return None
    return f"owner_telegram_{values[0]}"


def issue_private_reply_authorizations(
    *,
    token: str,
    chat_id: str,
    actor_id: str | None,
    owner_chat_id: str | None,
    maximum_send_count: int = MAX_EPHEMERAL_REPLY_SENDS,
) -> tuple[AuthorizationDecision, ...]:
    """Mint bounded in-memory return-envelope decisions for one inbound turn.

    This is not a durable grant source and grants no read, provider-egress,
    background-job, connection-management, or third-party send authority. It
    can only return a response to the authenticated private Telegram tuple over
    the exact bot connection that received the turn.
    """

    owner_ref = _private_delivery_owner_ref(chat_id, actor_id, owner_chat_id)
    connection_ref = _telegram_connection_ref(token)
    if owner_ref is None or connection_ref is None or maximum_send_count < 1:
        return ()
    now = datetime.now(timezone.utc)
    grant = CapabilityGrant(
        grant_id=f"grant_ephemeral_reply_{uuid.uuid4().hex}",
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        capability=RESULT_DELIVERY_CAPABILITY,
        resource_refs=(chat_id,),
        operations=("deliver",),
        data_classes=(RESULT_DELIVERY_DATA_CLASS,),
        purpose="answer.delivery",
        provider_policy=ProviderPolicy(
            (TELEGRAM_PROVIDER_REF,),
            maximum_request_count=maximum_send_count,
        ),
        issued_at=now,
        expires_at=now + timedelta(minutes=2),
        revision=1,
    )
    request = AuthorizationRequest(
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        capability=RESULT_DELIVERY_CAPABILITY,
        resource_ref=chat_id,
        operation="deliver",
        data_class=RESULT_DELIVERY_DATA_CLASS,
        provider_ref=TELEGRAM_PROVIDER_REF,
        purpose="answer.delivery",
        expected_grant_revision=1,
    )
    registry = CapabilityRegistry((grant,))
    return tuple(registry.authorize_and_reserve(request, now=now) for _ in range(maximum_send_count))


def _first_delivery_authorization(
    authorizations: Sequence[AuthorizationDecision],
) -> AuthorizationDecision | None:
    return authorizations[0] if authorizations else None


def _require_utd_draft_authorization(
    *,
    chat_id: str,
    authorization: AuthorizationDecision | None,
    actor_id: str | None,
    owner_chat_id: str | None,
) -> bool:
    owner_ref = _private_delivery_owner_ref(chat_id, actor_id, owner_chat_id)
    if owner_ref is None:
        LOGGER.warning("UTD draft denied before local write")
        return False
    try:
        require_authorized_operation(
            authorization,
            capability=UTD_DRAFT_CAPABILITY,
            operation="write",
            provider_ref=LOCAL_PROVIDER_REF,
            data_class="user_provided",
            owner_ref=owner_ref,
            connection_ref=None,
            resource_ref=chat_id,
            purpose=transport_purpose(
                provider_ref=LOCAL_PROVIDER_REF,
                capability=UTD_DRAFT_CAPABILITY,
                operation="write",
            ),
        )
    except CapabilityDenied:
        LOGGER.warning("UTD draft denied before local write")
        return False
    return True


def _require_prm_delivery_authorization(
    *,
    token: str,
    chat_id: str,
    authorization: AuthorizationDecision | None,
    actor_id: str | None,
    owner_chat_id: str | None,
) -> bool:
    delivery_owner_ref = _private_delivery_owner_ref(chat_id, actor_id, owner_chat_id)
    delivery_connection_ref = _telegram_connection_ref(token)
    if delivery_owner_ref is None or delivery_connection_ref is None:
        LOGGER.warning("PRM result delivery denied before Telegram send")
        return False
    try:
        require_authorized_operation(
            authorization,
            capability=RESULT_DELIVERY_CAPABILITY,
            operation="deliver",
            provider_ref=TELEGRAM_PROVIDER_REF,
            data_class=RESULT_DELIVERY_DATA_CLASS,
            owner_ref=delivery_owner_ref,
            connection_ref=delivery_connection_ref,
            resource_ref=chat_id,
            purpose=transport_purpose(
                provider_ref=TELEGRAM_PROVIDER_REF,
                capability=RESULT_DELIVERY_CAPABILITY,
                operation="deliver",
            ),
        )
    except CapabilityDenied:
        LOGGER.warning("PRM result delivery denied before Telegram send")
        return False
    return True


def _telegram_connection_ref(token: str) -> str | None:
    """Bind the policy connection ref to the exact configured bot token.

    The token is never returned, logged or stored.  Only a bounded opaque
    digest-derived connection reference participates in the in-memory grant
    comparison, so a reservation for another Telegram bot cannot authorize this
    transport.
    """

    clean_token = str(token or "").strip()
    if not clean_token:
        return None
    return f"connection_telegram_{hashlib.sha256(clean_token.encode('utf-8')).hexdigest()[:32]}"


def _split_telegram_text(text: str, *, limit: int = 3400) -> list[str]:
    clean = str(text or "").strip()
    if not clean:
        return [""]
    chunks: list[str] = []
    current = ""
    for paragraph in clean.split("\n\n"):
        pieces = _bounded_pieces(paragraph, limit=limit)
        for piece in pieces:
            candidate = piece if not current else f"{current}\n\n{piece}"
            if len(candidate) <= limit:
                current = candidate
                continue
            if current:
                chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return chunks or [clean[:limit]]


def _bounded_pieces(paragraph: str, *, limit: int) -> list[str]:
    if len(paragraph) <= limit:
        return [paragraph]
    lines = paragraph.splitlines() or [paragraph]
    result: list[str] = []
    current = ""
    for line in lines:
        if len(line) > limit:
            if current:
                result.append(current)
                current = ""
            result.extend(line[index : index + limit] for index in range(0, len(line), limit))
            continue
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= limit:
            current = candidate
        else:
            result.append(current)
            current = line
    if current:
        result.append(current)
    return result


def _explicit_archive_request(text: str) -> bool:
    normalized = " ".join(str(text or "").casefold().split())
    return any(marker in normalized for marker in ("в архиве", "по архиву", "archive"))


def _split_command(text: str) -> tuple[str, str]:
    clean = str(text or "").strip()
    if not clean.startswith("/"):
        return "/auto", clean
    parts = clean.split(maxsplit=1)
    command = parts[0].split("@", 1)[0].casefold()
    return command, parts[1].strip() if len(parts) > 1 else ""


def _resolve_prm_dialog_query(
    chat_id: str,
    query: str,
    *,
    mode: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    clean = _clean_operator_text(query)
    if mode not in {"auto", "research", "brief"}:
        return {
            "used": False,
            "kind": "query",
            "question": clean,
            "previous_question": "",
            "previous_topic": "",
            "effective_query": clean,
        }
    entry = _active_prm_dialog(_prm_dialog_key(chat_id), now=now)
    previous = str(entry.get("last_query") or "")
    previous_topic = str(entry.get("last_topic") or "").strip()
    previous_project = str(entry.get("last_project_name") or "").strip()
    previous_direct_only = bool(entry.get("direct_only_filter"))
    if previous and _is_memory_action_followup(clean):
        action = _memory_action_code(clean)
        available = {str(code) for code in entry.get("last_action_codes") or []}
        context_id = str(entry.get("last_action_context_id") or "")
        if context_id and action in available:
            return {
                "used": True,
                "kind": "post_answer_action",
                "question": clean,
                "previous_question": previous,
                "previous_topic": previous_topic,
                "effective_query": clean,
                "action_context_id": context_id,
                "post_answer_action": action,
            }
    if previous and _is_short_next_step_followup(clean):
        return {
            "used": True,
            "kind": "short_next_step",
            "question": clean,
            "previous_question": previous,
            "previous_topic": previous_topic,
            "effective_query": clean,
            "message": _render_short_next_step(entry),
        }
    if previous and _is_prm_research_followup(clean):
        if _is_project_followup(clean):
            base = previous_topic or previous
            direct_clause = " Фильтр: только прямые находки." if previous_direct_only else ""
            effective = _clean_operator_text(
                f"В архиве по теме {base}.{direct_clause} Сопоставь с проектом: {clean}"
            )[:900]
        elif previous_topic:
            project_clause = f" Для проекта {previous_project}." if previous_project else ""
            direct_clause = " Фильтр: только прямые находки." if previous_direct_only else ""
            effective = _clean_operator_text(
                f"В архиве по теме {previous_topic}.{project_clause}{direct_clause} Уточнение: {clean}"
            )[:900]
        else:
            effective = _clean_operator_text(f"{previous}. Уточнение: {clean}")[:900]
        return {
            "used": True,
            "kind": "query",
            "question": clean,
            "previous_question": previous,
            "previous_topic": previous_topic,
            "previous_project": previous_project,
            "previous_direct_only": previous_direct_only,
            "effective_query": effective,
        }
    return {
        "used": False,
        "kind": "query",
        "question": clean,
        "previous_question": previous,
        "previous_topic": previous_topic,
        "previous_project": previous_project,
        "previous_direct_only": previous_direct_only,
        "effective_query": clean,
    }


def _remember_prm_dialog(
    chat_id: str,
    effective_query: str,
    *,
    mode: str,
    topic: str = "",
    project_name: str = "",
    action_context_id: str = "",
    action_codes: list[str] | tuple[str, ...] = (),
    last_answer: str = "",
    pending_action: str = "",
    direct_only_filter: bool = False,
    direct_count: int = 0,
    partial_count: int = 0,
    adjacent_count: int = 0,
    current_fact_boundary: bool = False,
) -> None:
    if mode not in {"research", "brief"}:
        return
    clean = _clean_operator_text(effective_query)
    if not clean:
        return
    key = _prm_dialog_key(chat_id)
    if len(_PRM_DIALOG_STATE) >= _MAX_PRM_DIALOGS and key not in _PRM_DIALOG_STATE:
        oldest = next(iter(_PRM_DIALOG_STATE))
        _PRM_DIALOG_STATE.pop(oldest, None)
    _PRM_DIALOG_STATE[key] = {
        "last_query": clean[:700],
        "last_topic": _clean_topic_label(topic)[:240],
        "last_project_name": _clean_operator_text(project_name)[:120],
        "mode": mode,
        "last_action_context_id": _clean_operator_text(action_context_id)[:80],
        "last_action_codes": [str(code)[:8] for code in action_codes if str(code)],
        "last_answer": _clean_operator_text(last_answer)[:500],
        "pending_action": _clean_operator_text(pending_action)[:8],
        "direct_only_filter": bool(direct_only_filter),
        "direct_count": max(0, int(direct_count or 0)),
        "partial_count": max(0, int(partial_count or 0)),
        "adjacent_count": max(0, int(adjacent_count or 0)),
        "current_fact_boundary": bool(current_fact_boundary),
        "updated_at": datetime.now(timezone.utc),
    }


def _remember_pending_prm_action(chat_id: str, *, action: str, message: str) -> None:
    entry = _active_prm_dialog(_prm_dialog_key(chat_id))
    if not entry:
        return
    _remember_prm_dialog(
        chat_id,
        str(entry.get("last_query") or message),
        mode=str(entry.get("mode") or "research"),
        topic=str(entry.get("last_topic") or ""),
        project_name=str(entry.get("last_project_name") or ""),
        action_context_id=str(entry.get("last_action_context_id") or ""),
        action_codes=[str(code) for code in entry.get("last_action_codes") or []],
        last_answer=message,
        pending_action=_memory_action_code(action),
        direct_only_filter=bool(entry.get("direct_only_filter")),
        direct_count=int(entry.get("direct_count") or 0),
        partial_count=int(entry.get("partial_count") or 0),
        adjacent_count=int(entry.get("adjacent_count") or 0),
        current_fact_boundary=False,
    )


def _active_prm_dialog(key: str, *, now: datetime | None = None) -> dict[str, Any]:
    entry = _PRM_DIALOG_STATE.get(key)
    if not isinstance(entry, Mapping):
        return {}
    updated_at = entry.get("updated_at")
    timestamp = now or datetime.now(timezone.utc)
    if not isinstance(updated_at, datetime) or timestamp - updated_at > _PRM_DIALOG_TTL:
        _PRM_DIALOG_STATE.pop(key, None)
        return {}
    return dict(entry)


def _is_prm_research_followup(query: str) -> bool:
    clean = _clean_operator_text(query)
    lowered = clean.casefold()
    if not clean or len(clean) > 110:
        return False
    strong_followup_markers = (
        "а примен",
        "применимо это",
        "из этого",
        "собери из этого",
        "покажи только",
        "только прям",
        "коротко",
        "кратко",
        "сохрани",
        "запомни",
        "следи",
        "watch",
        "save",
        "next step",
        "за прошл",
        "за последн",
        "last week",
    )
    if any(lowered.startswith(marker) for marker in strong_followup_markers):
        return not _contains_new_topic_request(lowered)
    if _contains_prm_research_anchor(lowered):
        return False
    followup_markers = (
        "а ",
        "и ",
        "почему",
        "зачем",
        "покажи только",
        "только прям",
        "прямые",
        "подробнее",
        "разверни",
        "сравни",
        "коротко",
        "следующий шаг",
        "какой следующий шаг",
        "сохрани",
        "запомни",
        "следи",
        "watch",
        "save",
        "why",
        "what else",
        "next step",
        "за прошл",
        "за последн",
        "last week",
    )
    if any(lowered.startswith(marker) for marker in followup_markers):
        return True
    token_count = len([token for token in lowered.replace("?", " ").split() if token])
    return token_count <= 5 and lowered.endswith("?")


def _is_project_followup(query: str) -> bool:
    lowered = _clean_operator_text(query).casefold()
    return any(
        marker in lowered
        for marker in (
            "к проекту",
            "проекту",
            "для проекта",
            "мой проект",
            "моему проекту",
            "project",
            "repo",
            "backlog",
            "бэклог",
        )
    )


def _is_memory_action_followup(query: str) -> bool:
    lowered = _clean_operator_text(query).casefold()
    return any(marker in lowered for marker in ("сохрани", "запомни", "следи", "watch", "save"))


def _memory_action_code(query: str) -> str:
    lowered = _clean_operator_text(query).casefold()
    if lowered in {"w", "n"}:
        return lowered
    return "w" if any(marker in lowered for marker in ("следи", "watch", "наблюдай")) else "n"


def _is_short_next_step_followup(query: str) -> bool:
    lowered = _clean_operator_text(query).casefold()
    return any(
        marker in lowered
        for marker in (
            "коротко",
            "кратко",
            "какой следующий шаг",
            "следующий шаг",
            "next step",
        )
    )


def _is_direct_only_request(query: str) -> bool:
    lowered = _clean_operator_text(query).casefold()
    return any(marker in lowered for marker in ("только прям", "прямые находки", "direct only", "only direct"))


def _render_short_next_step(entry: Mapping[str, Any]) -> str:
    pending = str(entry.get("pending_action") or "")
    if pending:
        if pending == "w":
            topic = str(entry.get("last_topic") or "этой теме")
            return f"Следующий шаг: подтвердить черновик темы наблюдения {topic}, если предпросмотр точен. Это сохранит только подтверждённую тему; UTD-профиль не меняется."
        return "Следующий шаг: подтвердить черновик заметки, если предпросмотр точно отражает то, что нужно сохранить. Без подтверждения запись не создаётся."
    if bool(entry.get("current_fact_boundary")):
        return "Следующий шаг: разрешить внешнюю проверку официальных источников; без неё я не буду выдавать текущий факт за подтверждённый."
    direct = int(entry.get("direct_count") or 0)
    partial = int(entry.get("partial_count") or 0)
    adjacent = int(entry.get("adjacent_count") or 0)
    topic = str(entry.get("last_topic") or "этой теме")
    if direct:
        return f"Следующий шаг: взять одну прямую находку по теме {topic} и превратить её в маленький regression/action item."
    if partial or adjacent:
        return f"Следующий шаг: уточнить поиск по теме {topic} до одного термина, канала или периода; смежные материалы пока не считать доказательством."
    return f"Следующий шаг: переформулировать запрос по теме {topic} точнее или выбрать другой источник/период."


def _contains_new_topic_request(lowered: str) -> bool:
    return any(
        marker in lowered
        for marker in (
            "в архиве",
            "мой архив",
            "моём архиве",
            "utd",
            "dallas",
            "isso",
        )
    )


def _contains_prm_research_anchor(lowered: str) -> bool:
    anchors = (
        "в архиве",
        "мой архив",
        "моём архиве",
        "telegram",
        "телеграм",
        "utd",
        "dallas",
        "isso",
        "ai ",
        "ии",
        "rag",
        "раг",
        "eval",
        "vector",
        "вектор",
    )
    return any(anchor in lowered for anchor in anchors)


def _prm_dialog_key(chat_id: str) -> str:
    return hashlib.sha256(f"prm.active-dialog.v1:{chat_id}".encode("utf-8")).hexdigest()[:24]


def _clean_operator_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _clean_topic_label(value: object) -> str:
    clean = _clean_operator_text(value)
    lowered = clean.casefold()
    if "уточнение:" in lowered:
        clean = clean[: lowered.index("уточнение:")].strip()
    for prefix in ("В архиве по теме ", "в архиве по теме ", "по теме "):
        if clean.startswith(prefix):
            clean = clean[len(prefix) :].strip()
    return clean.strip(" .:;")


def _archive_result_count(payload: Mapping[str, Any], key: str) -> int:
    contract = _mapping(_mapping(payload).get("archive_contract"))
    summary = _mapping(contract.get("result_summary"))
    return max(0, int(summary.get(key) or 0))


def _current_fact_boundary(payload: Mapping[str, Any]) -> bool:
    gate = _mapping(_mapping(payload).get("answer_gate"))
    return (
        bool(gate.get("external_verification_required"))
        and not bool(gate.get("current_claim_allowed", True))
        and (bool(gate.get("no_answer_required")) or not bool(gate.get("allow_answer", False)))
    )


def _token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _help_text() -> str:
    return (
        "Я один помощник для двух связанных задач.\n\n"
        "AI-архив: ищу по твоему Telegram-архиву, отделяю прямые совпадения от "
        "смежных материалов и помогаю применить найденное к проектам. Просто задай вопрос.\n\n"
        "UTD / Dallas: понимаю вопросы про программу, карьеру, AI-события, ISSO, "
        "льготы и семью. Ответы не придумывают свежие даты или условия доступности: "
        "если нужен актуальный факт, я объясню, что нужна официальная страница. Свежие UTD-источники "
        "доступны только через отдельно подтверждённые темы; "
        "сохранение темы само по себе не включает мониторинг, уведомления или доставку.\n\n"
        "Чтобы собрать персональный scope, напиши: «Настроить мой UTD-профиль». "
        "Сначала будет черновик и полный предпросмотр; ничего постоянного не сохранится без "
        "отдельного подтверждения.\n\n"
        "Команда /privacy показывает действующие границы прав. Если активных прав нет, "
        "внешние модели и передача материалов заблокированы.\n\n"
        "Примеры обычных сообщений:\n"
        "• Что в архиве есть про agent evals?\n"
        "• Что из найденного применимо к моему проекту?\n"
        "• Есть ли актуальный UTD deadline для моей программы?\n"
        "• Подходит ли это UTD-событие супруге?"
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
