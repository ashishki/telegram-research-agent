"""Typed contracts shared by Telegram, CLI and evaluation interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import TYPE_CHECKING, Any, Literal, Mapping

from prm.capabilities import AuthorizationDecision

if TYPE_CHECKING:
    from prm.deep_research import ResearchCancellation, ResearchPlan

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
class PublicWebAccess:
    """Sealed PA-02 scopes for one public search and bounded source reads.

    This carrier contains only authorization metadata.  It never carries a
    private query, credentials, an HTTP client, source content or a fallback
    provider.  Search and fetch are deliberately different capabilities: a
    search snippet cannot authorize reading a document, and a document-read
    grant cannot authorize a new public search.
    """

    search_authorization: AuthorizationDecision
    fetch_authorizations: tuple[AuthorizationDecision, ...]
    owner_ref: str
    connection_ref: str | None
    search_resource_ref: str
    fetch_resource_ref: str
    # The separately minimized public query is bound by digest when the
    # authorization is assembled.  This carrier never retains raw query text,
    # so a later caller cannot substitute the original private prompt.
    public_query_digest: str

    def __post_init__(self) -> None:
        search = self.search_authorization
        fetches = self.fetch_authorizations
        if type(search) is not AuthorizationDecision or not isinstance(fetches, tuple) or not fetches or len(fetches) > 4:
            raise ValueError("public web access requires bounded typed authorizations")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.public_query_digest):
            raise ValueError("public web access requires a normalized public query digest")
        if not _matches_public_web_authorization(
            search,
            owner_ref=self.owner_ref,
            connection_ref=self.connection_ref,
            resource_ref=self.search_resource_ref,
            capability="web.search",
            purpose="public.search",
        ):
            raise ValueError("public web search authorization is out of scope")
        if len({id(item) for item in fetches}) != len(fetches):
            raise ValueError("public web fetch authorizations must be distinct")
        if any(
            type(item) is not AuthorizationDecision
            or not _matches_public_web_authorization(
                item,
                owner_ref=self.owner_ref,
                connection_ref=self.connection_ref,
                resource_ref=self.fetch_resource_ref,
                capability="web.fetch",
                purpose="public.fetch",
            )
            for item in fetches
        ):
            raise ValueError("public web fetch authorization is out of scope")


def _matches_public_web_authorization(
    decision: AuthorizationDecision,
    *,
    owner_ref: str,
    connection_ref: str | None,
    resource_ref: str,
    capability: str,
    purpose: str,
) -> bool:
    return bool(
        decision.allowed
        and decision.reservation is not None
        and decision.owner_ref == owner_ref
        and decision.connection_ref == connection_ref
        and decision.resource_ref == resource_ref
        and decision.provider_ref == "provider_public_web"
        and decision.capability == capability
        and decision.operation == "read"
        and decision.data_class == "public"
        and decision.purpose == purpose
    )


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
    # PA-05 never derives a public query from archive/profile text.  A caller
    # must separately supply a minimized public query plus this typed access;
    # omitted values retain the current-fact boundary without network activity.
    public_web_query: str = ""
    public_web_access: PublicWebAccess | None = None
    # PA-06 receives an already-built bounded plan. It is not inferred from
    # chat text, so transport ingress cannot turn an ordinary request into a
    # multi-source agent loop.
    deep_research_plan: "ResearchPlan | None" = None
    deep_research_cancellation: "ResearchCancellation | None" = None


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
