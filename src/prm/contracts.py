"""Typed contracts shared by Telegram, CLI and evaluation interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from prm.capabilities import AuthorizationDecision

RequestMode = Literal["auto", "research", "brief", "chat"]
ResponseMode = Literal["research", "brief", "chat", "project_clarify", "clarify"]
PrimaryIntent = Literal[
    "archive_lookup",
    "archive_synthesis",
    "archive_to_action",
    "project_mapping",
    "decision_support",
    "current_fact_verification",
    "memory_action",
    "writer_brief",
    "freeform_chat",
]
ResponseContractId = Literal[
    "archive_lookup.v2",
    "archive_research.v2",
    "project_mapping.v2",
    "decision_support.v2",
    "current_fact.v2",
    "brief.v1",
    "chat.v1",
]


@dataclass(frozen=True, slots=True)
class ModelEgressAccess:
    """One PA-02 reservation carried unchanged into an explicit chat turn."""

    authorization: AuthorizationDecision
    owner_ref: str
    connection_ref: str
    resource_ref: str

    def __post_init__(self) -> None:
        if type(self.authorization) is not AuthorizationDecision or not self.authorization.allowed:
            raise ValueError("model access requires an allowed typed authorization")
        if self.authorization.reservation is None:
            raise ValueError("model access requires a sealed reservation")
        if (
            self.authorization.owner_ref != self.owner_ref
            or self.authorization.connection_ref != self.connection_ref
            or self.authorization.resource_ref != self.resource_ref
            or self.authorization.capability != "model.generate"
            or self.authorization.operation != "model_egress"
            or self.authorization.data_class != "user_provided"
            or self.authorization.purpose != "answer.request"
            # The active PA-03 application invokes the sealed Anthropic
            # adapter. OpenAI has a separate adapter contract and must not be
            # silently substituted through this ingress carrier.
            or self.authorization.provider_ref != "provider_anthropic"
        ):
            raise ValueError("model access does not preserve the PA-02 reservation scope")


@dataclass(frozen=True, slots=True)
class ArchiveSynthesisAccess:
    """The exact paired PA-02 reservations for one private archive answer.

    A text reservation does not authorize an archive excerpt, and an archive
    context reservation does not authorize an answer on its own.  PA-04 carries
    the already-reserved pair to its dedicated, evidence-bound transport.  The
    transport rechecks both reservations immediately before its one request.
    """

    query_authorization: AuthorizationDecision
    context_authorization: AuthorizationDecision
    owner_ref: str
    connection_ref: str
    query_resource_ref: str
    context_resource_ref: str

    def __post_init__(self) -> None:
        query = self.query_authorization
        context = self.context_authorization
        if type(query) is not AuthorizationDecision or type(context) is not AuthorizationDecision:
            raise ValueError("archive synthesis access requires typed authorizations")
        if not query.allowed or not context.allowed or query.reservation is None or context.reservation is None:
            raise ValueError("archive synthesis access requires sealed allowed reservations")
        if (
            query.owner_ref != self.owner_ref
            or context.owner_ref != self.owner_ref
            or query.connection_ref != self.connection_ref
            or context.connection_ref != self.connection_ref
            or query.resource_ref != self.query_resource_ref
            or context.resource_ref != self.context_resource_ref
            or query.provider_ref != "provider_openai"
            or context.provider_ref != "provider_openai"
            or query.capability != "model.generate"
            or context.capability != "model.context_egress"
            or query.operation != "model_egress"
            or context.operation != "model_egress"
            or query.data_class != "user_provided"
            or context.data_class != "private_archive"
            or query.purpose != "answer.request"
            or context.purpose != "answer.context"
        ):
            raise ValueError("archive synthesis access does not preserve the paired PA-02 scope")
        if (
            query.operation_ref is None
            or query.operation_ref != context.operation_ref
            or query.reservation.operation_ref != query.operation_ref
            or context.reservation.operation_ref != context.operation_ref
            or query.reservation.registry is not context.reservation.registry
        ):
            raise ValueError("archive synthesis access requires one paired reservation group")


@dataclass(frozen=True, slots=True)
class OperatorRequest:
    query: str
    mode: RequestMode = "auto"
    chat_id: str = "local-cli"
    input_kind: Literal["text", "voice_transcript"] = "text"
    project_name: str = ""
    remember_dialog: bool = False
    # Telegram transport supplies this authenticated tuple when it exists.  It
    # is optional for read-only CLI/evaluation calls, where plain-language
    # confirmation must fail closed rather than synthesizing an actor.
    actor_id: str | None = None
    owner_chat_id: str | None = None
    # PA-03 receives model access only as a typed, already-reserved PA-02
    # decision. It contains no prompt, credential or provider payload.
    model_access: ModelEgressAccess | None = None
    # PA-04 deliberately uses a different paired scope: current user text plus
    # a bounded private-archive context cannot be substituted for PA-03 chat.
    archive_synthesis_access: ArchiveSynthesisAccess | None = None


@dataclass(frozen=True, slots=True)
class AssistantResult:
    interaction_id: str
    status: str
    mode: ResponseMode
    text: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    operator_context: Mapping[str, Any] = field(default_factory=dict)
    final_answer_verification: Mapping[str, Any] = field(default_factory=dict)
    route: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "interaction_id": self.interaction_id,
            "status": self.status,
            "mode": self.mode,
            "text": self.text,
            # Compatibility alias used by the private UX harness.
            "final_answer": self.text,
            "payload": dict(self.payload),
            "operator_context": dict(self.operator_context),
            "final_answer_verification": dict(self.final_answer_verification),
            "route": dict(self.route),
        }
