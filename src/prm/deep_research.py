"""Bounded, resumable multi-source research with explicit authority seams.

PA-06 intentionally has no default providers, persistence, queue, scheduler,
or model loop.  It coordinates caller-injected local archive, PA-05 public-web
and read-only GitHub adapters under one small budget. Each external callback
runs in an ephemeral, supervised local process so a cancel/deadline cannot
leave egress running after a partial result is returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
import secrets
from threading import Event, Lock
from time import monotonic
from typing import Any, Mapping, Protocol, Sequence

from prm.capabilities import AuthorizationDecision, CapabilityDenied, require_authorized_operation
from prm.contracts import PublicWebAccess
from prm.public_web import PublicWebBounds, PublicWebProvider, execute_public_web_research
from prm.research_planner import assess_research_gaps
from prm.research_worker import SupervisedWork, run_supervised_work


DEEP_RESEARCH_SCHEMA_VERSION = "prm_deep_research.v1"
_MAX_PUBLIC_TASKS = 3
_MAX_TOOL_CALLS = 8
_MAX_TIMEOUT_SECONDS = 60
_REPOSITORY_REF = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{7,64}$")
_INSTRUCTION_MARKERS = (
    "ignore previous", "system message", "developer message", "assistant instruction",
    "игнорируй предыдущ", "системное сообщение", "инструкция для ассистента",
)
_CHECKPOINT_SIGNING_KEY = secrets.token_bytes(32)
_CHECKPOINT_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_CHECKPOINT_SIGNATURE = re.compile(r"^hmac-sha256:[0-9a-f]{64}$")


class ArchiveResearchReader(Protocol):
    """Read-only local archive seam; no provider or account access."""

    def search_archive(self, query: str, *, limit: int) -> Mapping[str, Any]: ...


class GitHubContextProvider(Protocol):
    """Read one already-authorized repository identity and current ref."""

    def read_repository_context(self, repository_ref: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ResearchBudget:
    max_tool_calls: int = 6
    timeout_seconds: int = 30
    max_cost_usd: float = 0.0
    max_archive_sources: int = 5

    def __post_init__(self) -> None:
        if not 1 <= self.max_tool_calls <= _MAX_TOOL_CALLS:
            raise ValueError("deep research tool budget is out of range")
        if not 1 <= self.timeout_seconds <= _MAX_TIMEOUT_SECONDS:
            raise ValueError("deep research time budget is out of range")
        if not 0.0 <= float(self.max_cost_usd) <= 100.0:
            raise ValueError("deep research cost budget is out of range")
        if not 1 <= self.max_archive_sources <= 10:
            raise ValueError("deep research archive source limit is out of range")

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_tool_calls": self.max_tool_calls,
            "timeout_seconds": self.timeout_seconds,
            "max_cost_usd": self.max_cost_usd,
            "max_archive_sources": self.max_archive_sources,
        }


@dataclass(frozen=True, slots=True)
class GitHubReadAccess:
    """One sealed PA-02 scope for a public, exact repository context read."""

    authorization: AuthorizationDecision
    owner_ref: str
    connection_ref: str | None
    repository_ref: str

    def __post_init__(self) -> None:
        decision = self.authorization
        if type(decision) is not AuthorizationDecision or not decision.allowed or decision.reservation is None:
            raise ValueError("github context requires a sealed allowed authorization")
        if not _REPOSITORY_REF.fullmatch(self.repository_ref):
            raise ValueError("github repository identity is invalid")
        if (
            decision.owner_ref != self.owner_ref
            or decision.connection_ref != self.connection_ref
            or decision.resource_ref != self.repository_ref
            or decision.provider_ref != "provider_github"
            or decision.capability != "github.repository_context"
            or decision.operation != "read"
            or decision.data_class != "public"
            or decision.purpose != "project.context"
        ):
            raise ValueError("github context authorization is out of scope")


@dataclass(frozen=True, slots=True)
class PublicResearchTask:
    """One separately minimized PA-05 query; never an archive-derived string."""

    public_query: str
    access: object

    def __post_init__(self) -> None:
        if not 3 <= len(" ".join(self.public_query.split())) <= 300:
            raise ValueError("public research query is out of range")


class ResearchCostLedger:
    """Per-plan cost reservation; unknown price is refused before transport."""

    def __init__(self, maximum_usd: float) -> None:
        self._maximum_usd = float(maximum_usd)
        self._consumed_usd = 0.0
        self._unknown_price_refusals = 0
        self._observed_tariffs: list[dict[str, Any]] = []
        self._lock = Lock()

    def reserve_and_consume(self, quote: object) -> str:
        with self._lock:
            if not isinstance(quote, Mapping):
                self._unknown_price_refusals += 1
                return "unknown_price"
            provider_ref = str(quote.get("provider_ref") or "")
            tariff_version = str(quote.get("tariff_version") or "")
            estimate = quote.get("estimated_cost_usd")
            if (
                provider_ref != "provider_public_web"
                or not tariff_version
                or not isinstance(estimate, (int, float))
                or isinstance(estimate, bool)
                or float(estimate) < 0
            ):
                self._unknown_price_refusals += 1
                return "unknown_price"
            amount = float(estimate)
            if self._consumed_usd + amount > self._maximum_usd + 1e-12:
                return "cost_budget_exhausted"
            self._consumed_usd += amount
            self._observed_tariffs.append({"provider_ref": provider_ref, "tariff_version": tariff_version, "estimated_cost_usd": amount})
            return "allowed"

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "maximum_usd": self._maximum_usd,
                "consumed_usd": round(self._consumed_usd, 8),
                "unknown_price_refusals": self._unknown_price_refusals,
                "observed_tariffs": list(self._observed_tariffs),
            }


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    """A finite source plan whose expansion can only add local archive reads."""

    plan_id: str
    query_fingerprint: str
    archive_queries: tuple[str, ...]
    public_tasks: tuple[PublicResearchTask, ...] = ()
    github_access: GitHubReadAccess | None = None
    project_name: str = ""
    budget: ResearchBudget = field(default_factory=ResearchBudget)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"plan:[0-9a-f]{24}", self.plan_id):
            raise ValueError("research plan id is invalid")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.query_fingerprint):
            raise ValueError("research query fingerprint is invalid")
        # The initial local read is exactly one query. A single deterministic
        # gap result may add one later archive expansion; public queries are
        # independent, separately authorized tasks rather than generated
        # variants of private/archive text.
        if not isinstance(self.archive_queries, tuple) or len(self.archive_queries) != 1:
            raise ValueError("research plan requires one initial archive query")
        if any(not 2 <= len(" ".join(item.split())) <= 400 for item in self.archive_queries):
            raise ValueError("research archive query is invalid")
        if not isinstance(self.public_tasks, tuple) or len(self.public_tasks) > _MAX_PUBLIC_TASKS:
            raise ValueError("research plan public task count is invalid")
        if any(type(item) is not PublicResearchTask for item in self.public_tasks):
            raise ValueError("research plan public task type is invalid")
        if self.github_access is not None and type(self.github_access) is not GitHubReadAccess:
            raise ValueError("research plan github access type is invalid")
        if type(self.budget) is not ResearchBudget:
            raise ValueError("research plan budget type is invalid")
        initial_calls = 1 + len(self.public_tasks) + (1 if self.github_access is not None else 0)
        if initial_calls > self.budget.max_tool_calls:
            raise ValueError("research plan exceeds its tool budget")

    def to_public_dict(self) -> dict[str, Any]:
        """Expose plan shape without raw local or public query text."""

        return {
            "schema_version": DEEP_RESEARCH_SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "archive_query_count": len(self.archive_queries),
            "public_query_count": len(self.public_tasks),
            "github_repository_requested": self.github_access.repository_ref if self.github_access is not None else None,
            "project_name": self.project_name or None,
            "budget": self.budget.to_dict(),
            "paid_workload_enabled": False,
            "automatic_expansion": "local_archive_only",
        }


@dataclass(frozen=True, slots=True)
class ResearchStep:
    name: str
    status: str
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "source_count": len(_items(self.data)),
            "coverage": str(self.data.get("coverage") or self.data.get("status") or self.status),
        }


@dataclass(frozen=True, slots=True)
class ResearchCheckpoint:
    """Process-signed, plan-bound ephemeral resume receipt.

    It can be held by a caller for a same-process retry, but it cannot be
    assembled from arbitrary completed steps.  PA-09 owns durable jobs and
    persistence; a restart intentionally invalidates this receipt.
    """

    plan_id: str
    completed_steps: tuple[ResearchStep, ...]
    pending_steps: tuple[str, ...]
    state: str
    plan_binding: str
    integrity_token: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"plan:[0-9a-f]{24}", self.plan_id):
            raise ValueError("research checkpoint plan id is invalid")
        if self.state not in {"partial", "cancelled", "time_budget_exhausted", "complete"}:
            raise ValueError("research checkpoint state is invalid")
        if any(type(step) is not ResearchStep for step in self.completed_steps):
            raise ValueError("research checkpoint step type is invalid")
        if any(not re.fullmatch(r"(?:archive_initial|archive_expansion|public_[1-3]|github_context)", step) for step in self.pending_steps):
            raise ValueError("research checkpoint cannot schedule an unbounded step")
        if not _CHECKPOINT_DIGEST.fullmatch(self.plan_binding):
            raise ValueError("research checkpoint plan binding is invalid")
        if not _CHECKPOINT_SIGNATURE.fullmatch(self.integrity_token):
            raise ValueError("research checkpoint integrity token is invalid")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "state": self.state,
            "completed_steps": [step.to_public_dict() for step in self.completed_steps],
            "pending_steps": list(self.pending_steps),
            "retention": "ephemeral_process_signed",
            "resume_requires": "same_process_matching_plan_and_scope",
        }


@dataclass(frozen=True, slots=True)
class ResearchResult(Mapping[str, Any]):
    """Typed partial result returned by the PA-06 engine and application.

    Mapping compatibility keeps established render/test callers read-only while
    making the result/checkpoint boundary explicit for the active application
    ingress. The payload contains no provider credentials or raw public query.
    """

    status: str
    plan: Mapping[str, Any]
    facts: tuple[Mapping[str, Any], ...]
    inferences: tuple[Mapping[str, Any], ...]
    project_recommendations: tuple[Mapping[str, Any], ...]
    coverage: Mapping[str, Any]
    checkpoint: ResearchCheckpoint
    write_performed: bool = False
    provider_fallback_used: bool = False
    automatic_public_expansion: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DEEP_RESEARCH_SCHEMA_VERSION,
            "status": self.status,
            "plan": dict(self.plan),
            "facts": [dict(item) for item in self.facts],
            "inferences": [dict(item) for item in self.inferences],
            "project_recommendations": [dict(item) for item in self.project_recommendations],
            "coverage": dict(self.coverage),
            "checkpoint": self.checkpoint,
            "write_performed": self.write_performed,
            "provider_fallback_used": self.provider_fallback_used,
            "automatic_public_expansion": self.automatic_public_expansion,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self):
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())


class ResearchCancellation:
    """A cooperative cancellation signal checked before every external step."""

    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


def build_research_plan(
    query: str,
    *,
    archive_query: str | None = None,
    public_tasks: Sequence[PublicResearchTask] = (),
    github_access: GitHubReadAccess | None = None,
    project_name: str = "",
    budget: ResearchBudget | None = None,
) -> ResearchPlan:
    """Build a finite plan; it never derives a public query from ``query``."""

    clean = " ".join(str(query or "").split())
    local_query = " ".join(str(archive_query or clean).split())
    if not clean or not local_query:
        raise ValueError("research query is required")
    current_budget = budget or ResearchBudget()
    fingerprint = _fingerprint(clean)
    plan_id = "plan:" + hashlib.sha256(
        f"{fingerprint}\x1f{local_query}\x1f{project_name}".encode("utf-8")
    ).hexdigest()[:24]
    return ResearchPlan(
        plan_id=plan_id,
        query_fingerprint=fingerprint,
        archive_queries=(local_query,),
        public_tasks=tuple(public_tasks),
        github_access=github_access,
        project_name=" ".join(str(project_name or "").split())[:160],
        budget=current_budget,
    )


def run_bounded_research(
    plan: ResearchPlan,
    *,
    original_query: str,
    archive_reader: ArchiveResearchReader | None,
    public_provider: PublicWebProvider | None,
    public_bounds: PublicWebBounds | None,
    github_provider: GitHubContextProvider | None,
    cancellation: ResearchCancellation | None = None,
    checkpoint: ResearchCheckpoint | None = None,
) -> ResearchResult:
    """Run/resume a bounded plan and return typed partial evidence on failure.

    Work starts only after validation and cooperative cancellation checks. The
    initial archive/web/GitHub reads are independent and may run concurrently;
    the sole expansion is a gap-driven *local archive* query, so no generated
    text can fan out public egress.
    """

    if type(plan) is not ResearchPlan:
        raise ValueError("research plan must be typed")
    if checkpoint is not None:
        if type(checkpoint) is not ResearchCheckpoint or checkpoint.plan_id != plan.plan_id:
            raise ValueError("research checkpoint does not match plan")
        if not _checkpoint_is_trusted(plan, checkpoint):
            raise ValueError("research checkpoint is untrusted or belongs to a different source scope")
    cancellation = cancellation or ResearchCancellation()
    # A checkpoint resumes only work stopped before a worker was authorized.
    # Once parent-side authority was consumed, a provider call may have begun
    # even if it was killed before a response reached us. Preserve that unknown
    # outcome as partial coverage; a caller needs a fresh plan/scope to retry.
    prior_steps = list(checkpoint.completed_steps) if checkpoint is not None else []
    resumable_statuses = {"cancelled_before_start"}
    steps = [step for step in prior_steps if step.status not in resumable_statuses]
    completed_names = {step.name for step in steps}
    started = monotonic()
    pending: list[str] = []
    cost_ledger = ResearchCostLedger(plan.budget.max_cost_usd)

    if cancellation.cancelled:
        return _result(plan, steps, pending=["archive_initial"], state="cancelled", started=started, cost_ledger=cost_ledger)

    initial: list[SupervisedWork] = []
    if "archive_initial" not in completed_names:
        initial.append(_archive_work(
            "archive_initial", plan.archive_queries[0], archive_reader,
            limit=plan.budget.max_archive_sources, cancellation=cancellation,
        ))
    for index, task in enumerate(plan.public_tasks):
        name = f"public_{index + 1}"
        if name not in completed_names:
            prepared = _public_work(
                name, task, original_query=original_query, provider=public_provider,
                bounds=public_bounds, cancellation=cancellation, cost_ledger=cost_ledger,
            )
            if type(prepared) is ResearchStep:
                steps.append(prepared)
            else:
                initial.append(prepared)
    if plan.github_access is not None and "github_context" not in completed_names:
        initial.append(_github_work(plan.github_access, github_provider, cancellation=cancellation))

    if len(initial) + len(steps) > plan.budget.max_tool_calls:
        return _result(plan, steps, pending=["archive_expansion"], state="partial", started=started, budget_exhausted=True, cost_ledger=cost_ledger)
    steps.extend(_run_independent(
        initial, deadline_monotonic=started + plan.budget.timeout_seconds, cancellation=cancellation,
    ))
    if cancellation.cancelled:
        pending = [
            step.name for step in steps
            if step.status == "cancelled_before_start"
        ]
        return _result(plan, steps, pending=pending, state="cancelled", started=started, cost_ledger=cost_ledger)
    if monotonic() - started >= plan.budget.timeout_seconds:
        pending = []
        return _result(plan, steps, pending=pending, state="time_budget_exhausted", started=started, cost_ledger=cost_ledger)

    if "archive_expansion" not in {step.name for step in steps}:
        expansion_query = _gap_expansion_query(plan, steps)
        if expansion_query:
            if len(steps) >= plan.budget.max_tool_calls:
                pending.append("archive_expansion")
            elif archive_reader is None:
                steps.append(ResearchStep("archive_expansion", "archive_unavailable", {"status": "archive_unavailable"}))
            elif cancellation.cancelled:
                pending.append("archive_expansion")
            else:
                steps.extend(_run_independent(
                    [_archive_work(
                        "archive_expansion", expansion_query, archive_reader,
                        limit=plan.budget.max_archive_sources, cancellation=cancellation,
                    )],
                    deadline_monotonic=started + plan.budget.timeout_seconds,
                    cancellation=cancellation,
                ))

    if cancellation.cancelled:
        pending = ["archive_expansion"] if "archive_expansion" not in {step.name for step in steps} else []
        return _result(plan, steps, pending=pending, state="cancelled", started=started, cost_ledger=cost_ledger)
    if monotonic() - started >= plan.budget.timeout_seconds:
        pending = ["archive_expansion"] if "archive_expansion" not in {step.name for step in steps} else []
        return _result(plan, steps, pending=pending, state="time_budget_exhausted", started=started, cost_ledger=cost_ledger)
    return _result(plan, steps, pending=pending, state="complete" if not pending else "partial", started=started, cost_ledger=cost_ledger)


def _run_independent(
    tasks: Sequence[SupervisedWork],
    *,
    deadline_monotonic: float,
    cancellation: ResearchCancellation,
) -> list[ResearchStep]:
    """Run only supervised child callbacks; never leave one alive on return."""

    results = run_supervised_work(
        tasks,
        deadline_monotonic=deadline_monotonic,
        cancelled=lambda: cancellation.cancelled,
    )
    return sorted(
        [item for item in results if type(item) is ResearchStep],
        key=lambda item: item.name,
    )


def _archive_work(
    name: str,
    query: str,
    reader: ArchiveResearchReader | None,
    *,
    limit: int,
    cancellation: ResearchCancellation,
) -> SupervisedWork:
    return SupervisedWork(
        name=name,
        callback=lambda: _archive_step(name, query, reader, limit=limit, cancellation=cancellation),
        fallback=lambda status: ResearchStep(name, status, {"status": status}),
        # ArchiveResearchReader is the local-only PA-04 seam, not a provider
        # adapter. Making this explicit keeps worker start default-deny.
        preflight=lambda: None,
    )


def _public_work(
    name: str,
    task: PublicResearchTask,
    *,
    original_query: str,
    provider: PublicWebProvider | None,
    bounds: PublicWebBounds | None,
    cancellation: ResearchCancellation,
    cost_ledger: ResearchCostLedger,
) -> SupervisedWork | ResearchStep:
    """Prepare one public read without allowing a child to mint authority.

    The tariff is observed and reserved in the parent before any child starts.
    Parent preflight then consumes the exact one-use PA-02 slots before it
    sends the child its start signal.  The child inherited the sealed snapshot
    and repeats the normal PA-05 checks at the real transport call.
    """

    if provider is None or bounds is None:
        _abandon_public_access(task.access)
        return ResearchStep(name, "provider_unavailable", {"status": "provider_unavailable", "provider_called": False})
    quote_provider = getattr(provider, "research_cost_quote", None)
    try:
        quote = quote_provider() if callable(quote_provider) else None
    except Exception:
        quote = None
    cost_status = cost_ledger.reserve_and_consume(quote)
    if cost_status != "allowed":
        _abandon_public_access(task.access)
        return ResearchStep(name, cost_status, {"status": cost_status, "provider_called": False})
    return SupervisedWork(
        name=name,
        callback=lambda: _public_step(
            name, task, original_query=original_query, provider=provider,
            bounds=bounds, cancellation=cancellation,
        ),
        fallback=lambda status: ResearchStep(name, status, {"status": status}),
        preflight=lambda: _preflight_public_access(name, task, bounds),
    )


def _github_work(
    access: GitHubReadAccess,
    provider: GitHubContextProvider | None,
    *,
    cancellation: ResearchCancellation,
) -> SupervisedWork:
    return SupervisedWork(
        name="github_context",
        callback=lambda: _github_step(access, provider, cancellation=cancellation),
        fallback=lambda status: ResearchStep("github_context", status, {"status": status}),
        preflight=lambda: _preflight_github_access(access, provider),
    )


def _preflight_public_access(
    name: str,
    task: PublicResearchTask,
    bounds: PublicWebBounds | None,
) -> ResearchStep | None:
    """Consume every possible PA-05 egress slot before a worker can start.

    Reserving all bounded fetch slots is intentionally conservative.  The
    parent cannot observe which URLs the forked child will discover, so it
    must not leave an extra parent-side slot usable after the child starts.
    """

    access = task.access
    if type(access) is not PublicWebAccess or bounds is None:
        _abandon_public_access(access)
        return ResearchStep(name, "authorization_required", {"status": "authorization_required"})
    try:
        require_authorized_operation(
            access.search_authorization,
            capability="web.search",
            operation="read",
            provider_ref="provider_public_web",
            data_class="public",
            owner_ref=access.owner_ref,
            connection_ref=access.connection_ref,
            resource_ref=access.search_resource_ref,
            purpose="public.search",
        )
        for decision in access.fetch_authorizations[:bounds.max_fetches]:
            require_authorized_operation(
                decision,
                capability="web.fetch",
                operation="read",
                provider_ref="provider_public_web",
                data_class="public",
                owner_ref=access.owner_ref,
                connection_ref=access.connection_ref,
                resource_ref=access.fetch_resource_ref,
                purpose="public.fetch",
            )
    except CapabilityDenied:
        _abandon_public_access(access)
        return ResearchStep(name, "authorization_required", {"status": "authorization_required"})
    for decision in access.fetch_authorizations[bounds.max_fetches:]:
        _abandon(decision)
    return None


def _preflight_github_access(
    access: GitHubReadAccess,
    provider: GitHubContextProvider | None,
) -> ResearchStep | None:
    if provider is None:
        _abandon(access.authorization)
        return ResearchStep("github_context", "provider_unavailable", {"status": "provider_unavailable"})
    try:
        require_authorized_operation(
            access.authorization,
            capability="github.repository_context",
            operation="read",
            provider_ref="provider_github",
            data_class="public",
            owner_ref=access.owner_ref,
            connection_ref=access.connection_ref,
            resource_ref=access.repository_ref,
            purpose="project.context",
        )
    except CapabilityDenied:
        _abandon(access.authorization)
        return ResearchStep("github_context", "authorization_required", {"status": "authorization_required"})
    return None


def _archive_step(
    name: str,
    query: str,
    reader: ArchiveResearchReader | None,
    *,
    limit: int,
    cancellation: ResearchCancellation,
) -> ResearchStep:
    if cancellation.cancelled:
        return ResearchStep(name, "cancelled_before_start", {"status": "cancelled_before_start"})
    if reader is None:
        return ResearchStep(name, "archive_unavailable", {"status": "archive_unavailable"})
    try:
        raw = reader.search_archive(query, limit=limit)
    except Exception as exc:
        return ResearchStep(name, "archive_failed", {"status": "archive_failed", "error_type": type(exc).__name__})
    rows = [dict(item) for item in _items(raw)][:limit]
    return ResearchStep(name, "complete", {"status": str(raw.get("status") or "ok"), "items": rows, "coverage": "local_archive"})


def _public_step(
    name: str,
    task: PublicResearchTask,
    *,
    original_query: str,
    provider: PublicWebProvider | None,
    bounds: PublicWebBounds | None,
    cancellation: ResearchCancellation,
) -> ResearchStep:
    if cancellation.cancelled:
        return ResearchStep(name, "cancelled_before_start", {"status": "cancelled_before_start"})
    result = execute_public_web_research(
        public_query=task.public_query,
        original_query=original_query,
        access=task.access,  # the PA-05 executor requires its exact typed carrier
        provider=provider,
        bounds=bounds,
    )
    return ResearchStep(name, str(result.get("status") or "public_web_unavailable"), result)


def _github_step(
    access: GitHubReadAccess,
    provider: GitHubContextProvider | None,
    *,
    cancellation: ResearchCancellation,
) -> ResearchStep:
    if cancellation.cancelled:
        return ResearchStep("github_context", "cancelled_before_start", {"status": "cancelled_before_start"})
    if provider is None:
        if access.authorization.reservation is not None:
            access.authorization.reservation.abandon_before_transport()
        return ResearchStep("github_context", "provider_unavailable", {"status": "provider_unavailable"})
    try:
        require_authorized_operation(
            access.authorization,
            capability="github.repository_context",
            operation="read",
            provider_ref="provider_github",
            data_class="public",
            owner_ref=access.owner_ref,
            connection_ref=access.connection_ref,
            resource_ref=access.repository_ref,
            purpose="project.context",
        )
        raw = provider.read_repository_context(access.repository_ref)
    except CapabilityDenied:
        _abandon(access.authorization)
        return ResearchStep("github_context", "authorization_required", {"status": "authorization_required"})
    except Exception as exc:
        return ResearchStep("github_context", "provider_failed", {"status": "provider_failed", "error_type": type(exc).__name__})
    if not isinstance(raw, Mapping):
        return ResearchStep("github_context", "invalid_repository_context", {"status": "invalid_repository_context"})
    repository_ref = str(raw.get("repository_ref") or "")
    commit_sha = str(raw.get("commit_sha") or "").casefold()
    ref = str(raw.get("ref") or "").strip()
    if repository_ref != access.repository_ref or not _COMMIT_SHA.fullmatch(commit_sha) or not ref:
        return ResearchStep("github_context", "repository_identity_mismatch", {"status": "repository_identity_mismatch"})
    summary = " ".join(str(raw.get("summary") or "").split())[:800]
    if any(marker in summary.casefold() for marker in _INSTRUCTION_MARKERS):
        return ResearchStep("github_context", "untrusted_repository_instruction", {"status": "untrusted_repository_instruction"})
    return ResearchStep("github_context", "verified", {
        "status": "verified",
        "coverage": "checked_repository_identity",
        "repository_ref": repository_ref,
        "commit_sha": commit_sha,
        "ref": ref,
        "fetched_at": _now(),
        "source_url": f"https://github.com/{repository_ref}/commit/{commit_sha}",
        "summary": summary,
    })


def _gap_expansion_query(plan: ResearchPlan, steps: Sequence[ResearchStep]) -> str:
    initial = next((step for step in steps if step.name == "archive_initial"), None)
    if initial is None or initial.status != "complete":
        return ""
    gap = assess_research_gaps(_items(initial.data), question=plan.archive_queries[0])
    if str(gap.get("status") or "") != "needs_gap_search":
        return ""
    variants = [" ".join(str(item or "").split()) for item in gap.get("query_variants") or []]
    return next((item for item in variants if item), "")


def _result(
    plan: ResearchPlan,
    steps: Sequence[ResearchStep],
    *,
    pending: Sequence[str],
    state: str,
    started: float,
    budget_exhausted: bool = False,
    cost_ledger: ResearchCostLedger,
) -> ResearchResult:
    facts = _facts(steps)
    github = next((step.data for step in steps if step.name == "github_context" and step.status == "verified"), {})
    project_recommendations = _project_recommendations(plan, facts, github)
    partial = state != "complete" or any(step.status not in {"complete", "verified", "verified_current_evidence"} for step in steps)
    checkpoint = _issue_checkpoint(
        plan,
        completed_steps=tuple(steps),
        pending_steps=tuple(pending),
        state=state if state in {"partial", "cancelled", "time_budget_exhausted", "complete"} else "partial",
    )
    return ResearchResult(
        status="partial" if partial else "complete",
        plan=plan.to_public_dict(),
        facts=tuple(facts),
        inferences=tuple(_inferences(facts, github)),
        project_recommendations=tuple(project_recommendations),
        coverage={
            "state": state,
            "completed_steps": [step.to_public_dict() for step in steps],
            "pending_steps": list(pending),
            "budget_exhausted": budget_exhausted,
            "elapsed_seconds": round(monotonic() - started, 4),
            "source_gaps": _gaps(steps),
            "cost": cost_ledger.to_dict(),
        },
        checkpoint=checkpoint,
    )


def _issue_checkpoint(
    plan: ResearchPlan,
    *,
    completed_steps: tuple[ResearchStep, ...],
    pending_steps: tuple[str, ...],
    state: str,
) -> ResearchCheckpoint:
    binding = _checkpoint_plan_binding(plan)
    return ResearchCheckpoint(
        plan_id=plan.plan_id,
        completed_steps=completed_steps,
        pending_steps=pending_steps,
        state=state,
        plan_binding=binding,
        integrity_token=_checkpoint_integrity(
            plan_id=plan.plan_id,
            plan_binding=binding,
            completed_steps=completed_steps,
            pending_steps=pending_steps,
            state=state,
        ),
    )


def _checkpoint_is_trusted(plan: ResearchPlan, checkpoint: ResearchCheckpoint) -> bool:
    binding = _checkpoint_plan_binding(plan)
    if not hmac.compare_digest(checkpoint.plan_binding, binding):
        return False
    expected = _checkpoint_integrity(
        plan_id=checkpoint.plan_id,
        plan_binding=checkpoint.plan_binding,
        completed_steps=checkpoint.completed_steps,
        pending_steps=checkpoint.pending_steps,
        state=checkpoint.state,
    )
    return hmac.compare_digest(checkpoint.integrity_token, expected)


def _checkpoint_plan_binding(plan: ResearchPlan) -> str:
    """Bind a receipt to its exact source identities and sealed scopes."""

    public_sources: list[dict[str, Any]] = []
    for task in plan.public_tasks:
        access = task.access
        if type(access) is not PublicWebAccess:
            public_sources.append({"access_type": type(access).__name__})
            continue
        public_sources.append({
            "query_digest": access.public_query_digest,
            "owner_ref": access.owner_ref,
            "connection_ref": access.connection_ref,
            "search_resource_ref": access.search_resource_ref,
            "fetch_resource_ref": access.fetch_resource_ref,
            "search_authorization": _authorization_scope(access.search_authorization),
            "fetch_authorizations": [_authorization_scope(item) for item in access.fetch_authorizations],
        })
    github = None
    if plan.github_access is not None:
        github = {
            "repository_ref": plan.github_access.repository_ref,
            "owner_ref": plan.github_access.owner_ref,
            "connection_ref": plan.github_access.connection_ref,
            "authorization": _authorization_scope(plan.github_access.authorization),
        }
    binding = {
        "schema_version": DEEP_RESEARCH_SCHEMA_VERSION,
        "plan_id": plan.plan_id,
        "query_fingerprint": plan.query_fingerprint,
        "archive_query_fingerprints": [_fingerprint(item) for item in plan.archive_queries],
        "public_sources": public_sources,
        "github_source": github,
        "project_name": plan.project_name,
        "budget": plan.budget.to_dict(),
    }
    return _fingerprint(_canonical_checkpoint_json(binding))


def _authorization_scope(decision: AuthorizationDecision) -> dict[str, Any]:
    return {
        "grant_ref": decision.grant_ref,
        "grant_revision": decision.grant_revision,
        "owner_ref": decision.owner_ref,
        "connection_ref": decision.connection_ref,
        "resource_ref": decision.resource_ref,
        "capability": decision.capability,
        "operation": decision.operation,
        "data_class": decision.data_class,
        "provider_ref": decision.provider_ref,
        "purpose": decision.purpose,
    }


def _checkpoint_integrity(
    *,
    plan_id: str,
    plan_binding: str,
    completed_steps: Sequence[ResearchStep],
    pending_steps: Sequence[str],
    state: str,
) -> str:
    payload = {
        "plan_id": plan_id,
        "plan_binding": plan_binding,
        "completed_steps": [
            {"name": item.name, "status": item.status, "data": _checkpoint_value(item.data)}
            for item in completed_steps
        ],
        "pending_steps": list(pending_steps),
        "state": state,
    }
    digest = hmac.new(
        _CHECKPOINT_SIGNING_KEY,
        _canonical_checkpoint_json(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return "hmac-sha256:" + digest


def _checkpoint_value(value: object) -> Any:
    """Canonicalize result data for integrity without exposing it elsewhere."""

    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            return {"nonfinite_float": repr(value)}
        return value
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest(), "length": len(value)}
    if isinstance(value, datetime):
        return {"datetime": value.isoformat()}
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            return {"mapping_repr": repr(value)}
        return {key: _checkpoint_value(item) for key, item in value.items()}
    if isinstance(value, Sequence):
        return [_checkpoint_value(item) for item in value]
    return {"value_type": type(value).__name__, "value_repr": repr(value)}


def _canonical_checkpoint_json(value: object) -> str:
    return json.dumps(_checkpoint_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def render_research_fact_section(result: ResearchResult) -> str:
    """Render only exact cited facts for the generic claim-ledger verifier."""

    fact_lines: list[str] = []
    for fact in result.facts:
        span = " ".join(str(fact.get("support_span") or "").split())
        source = str(fact.get("source_url") or "")
        if span and source:
            fact_lines.extend(("Факт: " + span, "Источник: " + source))
    if not fact_lines:
        return "Я не могу подтвердить актуальный внешний факт: исследование вернуло только частичное покрытие."
    return "\n".join(["Проверенные факты:", *fact_lines[:12]])


def render_research_result(result: ResearchResult) -> str:
    """Render fact, inference and recommendation as visibly different kinds."""

    fact_section = render_research_fact_section(result)
    if fact_section.startswith("Я не могу подтвердить актуальный внешний факт"):
        return fact_section
    lines = fact_section.splitlines()
    if result.inferences:
        lines.append("Инференция (не факт): " + str(result.inferences[0].get("statement") or ""))
    if result.project_recommendations:
        recommendation = result.project_recommendations[0]
        lines.append("Рекомендация (требует человеческого решения): " + str(recommendation.get("statement") or ""))
        lines.append("Условия: " + ", ".join(str(item) for item in recommendation.get("conditions") or []))
    return "\n".join(lines)


def _facts(steps: Sequence[ResearchStep]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for step in steps:
        if step.name.startswith("archive_") and step.status == "complete":
            for item in _items(step.data):
                span = " ".join(str(item.get("support_span") or item.get("snippet") or "").split())[:400]
                source = str(item.get("source_url") or "")
                if span and source:
                    facts.append({"kind": "fact", "source_kind": "archive", "support_span": span, "source_url": source})
        elif step.name.startswith("public_") and step.status == "verified_current_evidence":
            for item in step.data.get("evidence_items") or []:
                if isinstance(item, Mapping):
                    facts.append({
                        "kind": "fact", "source_kind": "public_primary", "support_span": str(item.get("support_span") or "")[:400],
                        "source_url": str(item.get("source_url") or ""), "freshness": str(item.get("freshness") or "unknown"),
                    })
        elif step.name == "github_context" and step.status == "verified":
            fact = {
                "kind": "fact", "source_kind": "github_repository_identity", "repository_ref": step.data.get("repository_ref"),
                "commit_sha": step.data.get("commit_sha"), "ref": step.data.get("ref"), "source_url": step.data.get("source_url"),
            }
            if str(step.data.get("summary") or ""):
                fact["support_span"] = str(step.data.get("summary") or "")[:240]
            facts.append(fact)
    return facts[:16]


def _inferences(facts: Sequence[Mapping[str, Any]], github: Mapping[str, Any]) -> list[dict[str, Any]]:
    source_kinds = {str(item.get("source_kind") or "") for item in facts}
    if {"archive", "public_primary"} <= source_kinds:
        return [{"kind": "inference", "statement": "Archive and public evidence were both available; their applicability remains conditional.", "basis": ["archive", "public_primary"]}]
    if github:
        return [{"kind": "inference", "statement": "Repository identity was checked at the cited ref; source applicability still requires human judgment.", "basis": ["github_repository_identity"]}]
    return []


def _project_recommendations(plan: ResearchPlan, facts: Sequence[Mapping[str, Any]], github: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not plan.project_name or not github:
        return []
    source_refs = [str(item.get("source_url") or "") for item in facts if str(item.get("source_url") or "")]
    if len(source_refs) < 2:
        return []
    repository_ref = str(github.get("repository_ref") or "")
    commit_sha = str(github.get("commit_sha") or "")
    return [{
        "kind": "project_recommendation",
        "project_name": plan.project_name,
        "statement": f"Review the cited evidence against {repository_ref}@{commit_sha} before proposing a project change.",
        "conditions": ["repository_identity_checked", "at_least_two_cited_facts", "human_confirmation_required_for_any_change"],
        "evidence_refs": source_refs[:5],
        "write_performed": False,
    }]


def _gaps(steps: Sequence[ResearchStep]) -> list[str]:
    gaps = [step.status for step in steps if step.status not in {"complete", "verified", "verified_current_evidence"}]
    return list(dict.fromkeys(gaps))


def _items(value: Mapping[str, Any] | object) -> list[Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return []
    return [item for item in value.get("items") or [] if isinstance(item, Mapping)]


def _abandon(decision: AuthorizationDecision) -> None:
    if decision.reservation is not None:
        decision.reservation.abandon_before_transport()


def _abandon_public_access(access: object) -> None:
    if type(access) is not PublicWebAccess:
        return
    for decision in (access.search_authorization, *access.fetch_authorizations):
        _abandon(decision)


def _fingerprint(query: str) -> str:
    return "sha256:" + hashlib.sha256(query.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
