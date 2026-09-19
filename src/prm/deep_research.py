"""Bounded, resumable multi-source research with explicit authority seams.

PA-06 intentionally has no default providers, persistence, background worker,
or model loop.  It coordinates caller-injected local archive, PA-05 public-web
and read-only GitHub adapters under one small budget, preserving a safe
checkpoint whenever it returns a partial result.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import re
from threading import Event
from time import monotonic
from typing import Any, Callable, Mapping, Protocol, Sequence

from prm.capabilities import AuthorizationDecision, CapabilityDenied, require_authorized_operation
from prm.public_web import PublicWebBounds, PublicWebProvider, execute_public_web_research
from prm.research_planner import assess_research_gaps


DEEP_RESEARCH_SCHEMA_VERSION = "prm_deep_research.v1"
_MAX_ARCHIVE_QUERIES = 4
_MAX_PUBLIC_TASKS = 3
_MAX_TOOL_CALLS = 8
_MAX_TIMEOUT_SECONDS = 60
_REPOSITORY_REF = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_COMMIT_SHA = re.compile(r"^[0-9a-f]{7,64}$")
_INSTRUCTION_MARKERS = (
    "ignore previous", "system message", "developer message", "assistant instruction",
    "игнорируй предыдущ", "системное сообщение", "инструкция для ассистента",
)


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
        if self.max_cost_usd != 0.0:
            # PA-16 owns paid-model and priced-provider policy. Keeping this
            # zero makes an unknown-priced adapter fail closed rather than
            # treating a development fixture as a spending authorization.
            raise ValueError("deep research has no approved nonzero cost budget")
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
    estimated_cost_usd: float = 0.0

    def __post_init__(self) -> None:
        if not 3 <= len(" ".join(self.public_query.split())) <= 300:
            raise ValueError("public research query is out of range")
        if self.estimated_cost_usd != 0.0:
            raise ValueError("public research task has no approved nonzero cost")


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
        if not isinstance(self.archive_queries, tuple) or not self.archive_queries or len(self.archive_queries) > _MAX_ARCHIVE_QUERIES:
            raise ValueError("research plan requires bounded archive queries")
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
    """Ephemeral resume point; callers choose whether and where to retain it."""

    plan_id: str
    completed_steps: tuple[ResearchStep, ...]
    pending_steps: tuple[str, ...]
    state: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"plan:[0-9a-f]{24}", self.plan_id):
            raise ValueError("research checkpoint plan id is invalid")
        if self.state not in {"partial", "cancelled", "time_budget_exhausted", "complete"}:
            raise ValueError("research checkpoint state is invalid")
        if any(type(step) is not ResearchStep for step in self.completed_steps):
            raise ValueError("research checkpoint step type is invalid")
        if any(step not in {"archive_expansion"} for step in self.pending_steps):
            raise ValueError("research checkpoint cannot schedule an unbounded step")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "state": self.state,
            "completed_steps": [step.to_public_dict() for step in self.completed_steps],
            "pending_steps": list(self.pending_steps),
            "retention": "ephemeral_caller_owned",
        }


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
) -> dict[str, Any]:
    """Run/resume a bounded plan and return typed partial evidence on failure.

    Work starts only after validation and cooperative cancellation checks. The
    initial archive/web/GitHub reads are independent and may run concurrently;
    the sole expansion is a gap-driven *local archive* query, so no generated
    text can fan out public egress.
    """

    if type(plan) is not ResearchPlan:
        raise ValueError("research plan must be typed")
    if checkpoint is not None and (type(checkpoint) is not ResearchCheckpoint or checkpoint.plan_id != plan.plan_id):
        raise ValueError("research checkpoint does not match plan")
    cancellation = cancellation or ResearchCancellation()
    steps = list(checkpoint.completed_steps) if checkpoint is not None else []
    completed_names = {step.name for step in steps}
    started = monotonic()
    pending: list[str] = []

    if cancellation.cancelled:
        return _result(plan, steps, pending=["archive_expansion"], state="cancelled", started=started)

    initial: dict[str, Callable[[], ResearchStep]] = {}
    if "archive_initial" not in completed_names:
        initial["archive_initial"] = lambda: _archive_step(
            "archive_initial", plan.archive_queries[0], archive_reader, limit=plan.budget.max_archive_sources, cancellation=cancellation,
        )
    for index, task in enumerate(plan.public_tasks):
        name = f"public_{index + 1}"
        if name not in completed_names:
            initial[name] = lambda task=task, name=name: _public_step(
                name, task, original_query=original_query, provider=public_provider, bounds=public_bounds, cancellation=cancellation,
            )
    if plan.github_access is not None and "github_context" not in completed_names:
        initial["github_context"] = lambda: _github_step(plan.github_access, github_provider, cancellation=cancellation)

    if len(initial) + len(steps) > plan.budget.max_tool_calls:
        return _result(plan, steps, pending=["archive_expansion"], state="partial", started=started, budget_exhausted=True)
    steps.extend(_run_independent(initial, timeout_seconds=plan.budget.timeout_seconds, cancellation=cancellation, started=started))
    if cancellation.cancelled:
        return _result(plan, steps, pending=["archive_expansion"], state="cancelled", started=started)
    if monotonic() - started >= plan.budget.timeout_seconds:
        return _result(plan, steps, pending=["archive_expansion"], state="time_budget_exhausted", started=started)

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
                steps.append(_archive_step(
                    "archive_expansion", expansion_query, archive_reader, limit=plan.budget.max_archive_sources, cancellation=cancellation,
                ))

    if cancellation.cancelled:
        pending = ["archive_expansion"] if "archive_expansion" not in {step.name for step in steps} else []
        return _result(plan, steps, pending=pending, state="cancelled", started=started)
    if monotonic() - started >= plan.budget.timeout_seconds:
        pending = ["archive_expansion"] if "archive_expansion" not in {step.name for step in steps} else []
        return _result(plan, steps, pending=pending, state="time_budget_exhausted", started=started)
    return _result(plan, steps, pending=pending, state="complete" if not pending else "partial", started=started)


def _run_independent(
    tasks: Mapping[str, Callable[[], ResearchStep]],
    *,
    timeout_seconds: int,
    cancellation: ResearchCancellation,
    started: float,
) -> list[ResearchStep]:
    if not tasks:
        return []
    executor = ThreadPoolExecutor(max_workers=min(4, len(tasks)), thread_name_prefix="prm-research")
    futures: dict[Future[ResearchStep], str] = {executor.submit(callback): name for name, callback in tasks.items()}
    remaining = max(0.0, timeout_seconds - (monotonic() - started))
    done, not_done = wait(futures, timeout=remaining)
    results: list[ResearchStep] = []
    for future in done:
        name = futures[future]
        try:
            results.append(future.result())
        except Exception as exc:  # a provider failure is data, not a retry loop
            results.append(ResearchStep(name, "provider_failed", {"status": "provider_failed", "error_type": type(exc).__name__}))
    for future in not_done:
        future.cancel()
        results.append(ResearchStep(futures[future], "time_budget_exhausted", {"status": "time_budget_exhausted"}))
    # Do not wait past the declared research budget for a non-cooperative
    # adapter. Its result is discarded; callers receive a partial checkpoint.
    executor.shutdown(wait=False, cancel_futures=True)
    return sorted(results, key=lambda item: item.name)


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
) -> dict[str, Any]:
    facts = _facts(steps)
    github = next((step.data for step in steps if step.name == "github_context" and step.status == "verified"), {})
    project_recommendations = _project_recommendations(plan, facts, github)
    partial = state != "complete" or any(step.status not in {"complete", "verified", "verified_current_evidence"} for step in steps)
    checkpoint = ResearchCheckpoint(
        plan_id=plan.plan_id,
        completed_steps=tuple(steps),
        pending_steps=tuple(pending),
        state=state if state in {"partial", "cancelled", "time_budget_exhausted", "complete"} else "partial",
    )
    return {
        "schema_version": DEEP_RESEARCH_SCHEMA_VERSION,
        "status": "partial" if partial else "complete",
        "plan": plan.to_public_dict(),
        "facts": facts,
        "inferences": _inferences(facts, github),
        "project_recommendations": project_recommendations,
        "coverage": {
            "state": state,
            "completed_steps": [step.to_public_dict() for step in steps],
            "pending_steps": list(pending),
            "budget_exhausted": budget_exhausted,
            "elapsed_seconds": round(monotonic() - started, 4),
            "source_gaps": _gaps(steps),
        },
        "checkpoint": checkpoint,
        "write_performed": False,
        "provider_fallback_used": False,
        "automatic_public_expansion": False,
    }


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
            facts.append({
                "kind": "fact", "source_kind": "github_repository_identity", "repository_ref": step.data.get("repository_ref"),
                "commit_sha": step.data.get("commit_sha"), "ref": step.data.get("ref"), "source_url": step.data.get("source_url"),
            })
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


def _fingerprint(query: str) -> str:
    return "sha256:" + hashlib.sha256(query.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
