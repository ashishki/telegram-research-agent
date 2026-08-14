"""Ephemeral, validated request context for the PRM assistant.

The context is intentionally in-memory only.  It carries a normalized query
through a single request, but it is not a transcript, receipt, or a durable
session record.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import re
from typing import Literal
from uuid import uuid4

from assistant.rag_answer_gate import assess_rag_answer_gate


OPERATOR_CONTEXT_SCHEMA_VERSION = "operator_context.v1"
Workflow = Literal[
    "archive_research", "writer_editor_brief", "current_fact_verification", "generic_chat", "insufficient_evidence"
]
InputKind = Literal["text", "voice_transcript"]


@dataclass(frozen=True)
class OperatorContext:
    schema_version: str
    interaction_id: str
    chat_id_hash: str
    session_id: str
    input_kind: InputKind
    language: str
    normalized_query: str
    primary_intent: str
    primary_workflow: Workflow
    secondary_lens: str | None
    explicit_lens: str | None
    inferred_lens: str | None
    project_name: str | None
    project_selection_source: str | None
    date_from: str | None
    date_to: str | None
    freshness_requirement: str
    evidence_requirements: tuple[str, ...]
    external_verification_requirement: bool
    answer_mode: str
    clarification_required: bool
    route_confidence: float
    durable_write_allowed: bool
    privacy_mode: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_operator_context(
    *,
    chat_id: str,
    query: str,
    requested_mode: str = "research",
    input_kind: InputKind = "text",
    project_name: str = "",
    now: datetime | None = None,
) -> OperatorContext:
    """Select exactly one safe workflow without doing I/O or retaining text."""

    normalized_query = " ".join(str(query or "").split())
    gate = assess_rag_answer_gate(normalized_query, source_count=1)
    mode = str(requested_mode or "research").casefold()
    workflow, intent, confidence, clarification = _select_workflow(
        normalized_query, mode=mode, gate_reason=str(gate["reason"])
    )
    selected_project = " ".join(str(project_name or "").split()) or None
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    language = "ru" if re.search(r"[А-Яа-яЁё]", normalized_query) else "en"
    return OperatorContext(
        schema_version=OPERATOR_CONTEXT_SCHEMA_VERSION,
        interaction_id=str(uuid4()),
        chat_id_hash=_hash_chat_id(chat_id),
        session_id=_session_id(chat_id),
        input_kind=input_kind,
        language=language,
        normalized_query=normalized_query,
        primary_intent=intent,
        primary_workflow=workflow,
        secondary_lens=None,
        explicit_lens=None,
        inferred_lens=None,
        project_name=selected_project,
        project_selection_source="explicit_named_project" if selected_project else None,
        date_from=None,
        date_to=None,
        freshness_requirement="current_evidence" if workflow == "current_fact_verification" else "archive_scoped",
        evidence_requirements=("cited_archive_context",) if workflow != "generic_chat" else (),
        external_verification_requirement=bool(gate["external_verification_required"]),
        answer_mode="clarification" if clarification else "grounded",
        clarification_required=clarification,
        route_confidence=confidence,
        durable_write_allowed=False,
        privacy_mode="ephemeral_local_only",
        created_at=timestamp.isoformat().replace("+00:00", "Z"),
    )


def validate_operator_context(context: OperatorContext) -> None:
    if context.schema_version != OPERATOR_CONTEXT_SCHEMA_VERSION:
        raise ValueError("unsupported operator context schema")
    if not context.interaction_id or not context.chat_id_hash or not context.session_id:
        raise ValueError("operator context identity is required")
    if context.input_kind not in {"text", "voice_transcript"}:
        raise ValueError("invalid operator context input kind")
    if context.primary_workflow not in {
        "archive_research", "writer_editor_brief", "current_fact_verification", "generic_chat", "insufficient_evidence"
    }:
        raise ValueError("exactly one allowed workflow is required")
    if context.durable_write_allowed:
        raise ValueError("operator context cannot authorize durable writes")


def _select_workflow(query: str, *, mode: str, gate_reason: str) -> tuple[Workflow, str, float, bool]:
    if gate_reason in {"current_external_fact_required", "unsupported_project_state_claim"}:
        return "current_fact_verification", "current_fact", 0.95, False
    if not query:
        return "insufficient_evidence", "clarification", 0.0, True
    if mode == "clarify":
        return "insufficient_evidence", "clarification", 0.0, True
    if mode == "brief":
        return "writer_editor_brief", "editorial_brief", 0.72, False
    if mode == "chat":
        return "generic_chat", "conversation", 0.55, False
    return "archive_research", "archive_research", 0.55, False


def _hash_chat_id(chat_id: str) -> str:
    return hashlib.sha256(f"prm.operator-context.v1:{chat_id}".encode("utf-8")).hexdigest()[:24]


def _session_id(chat_id: str) -> str:
    return hashlib.sha256(f"prm.operator-session.v1:{chat_id}".encode("utf-8")).hexdigest()[:24]
