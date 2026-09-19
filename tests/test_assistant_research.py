"""Offline PA-06 holdouts for bounded multi-source research."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from threading import Barrier
from types import SimpleNamespace

import pytest

from prm.capabilities import AuthorizationRequest, CapabilityGrant, CapabilityRegistry, ProviderPolicy
from prm.contracts import PublicWebAccess
from prm.deep_research import (
    GitHubReadAccess,
    PublicResearchTask,
    ResearchBudget,
    ResearchCancellation,
    build_research_plan,
    run_bounded_research,
)
from prm.public_web import PublicWebBounds
from integrations.github_readonly import GitHubReadError, ReadOnlyGitHubContextProvider


class _Archive:
    def __init__(self, rows, barrier: Barrier | None = None):
        self.rows = rows
        self.barrier = barrier
        self.queries = []

    def search_archive(self, query, *, limit):
        self.queries.append((query, limit))
        if self.barrier is not None:
            self.barrier.wait(timeout=2)
        return {"status": "ok", "items": self.rows[:limit]}


class _Public:
    def __init__(self, *, barrier: Barrier | None = None, fail=False):
        self.barrier = barrier
        self.fail = fail
        self.queries = []

    def search_public(self, query, *, bounds):
        self.queries.append(query)
        if self.barrier is not None:
            self.barrier.wait(timeout=2)
        if self.fail:
            raise RuntimeError("offline provider failure")
        return [{"url": "https://docs.vendor.example/release", "title": "Official", "snippet": "discovery only"}]

    def fetch_public(self, source_ref, *, bounds):
        return {
            "status": 200,
            "final_url": source_ref,
            "headers": {"content-type": "text/plain"},
            "body": b"Vendor 2.0 is the current supported release.",
            "published_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }


class _GitHub:
    def __init__(self, *, barrier: Barrier | None = None, repository_ref="acme/project", commit_sha="a" * 40):
        self.barrier = barrier
        self.repository_ref = repository_ref
        self.commit_sha = commit_sha
        self.requests = []

    def read_repository_context(self, repository_ref):
        self.requests.append(repository_ref)
        if self.barrier is not None:
            self.barrier.wait(timeout=2)
        return {
            "repository_ref": self.repository_ref,
            "commit_sha": self.commit_sha,
            "ref": "main",
            "summary": "Read-only current repository context.",
        }


def _public_access(query: str, *, fetch_count=1) -> PublicWebAccess:
    now = datetime.now(timezone.utc)
    search = CapabilityGrant(
        grant_id="grant_pa06_web_search",
        owner_ref="owner_pa06",
        connection_ref="connection_pa06",
        capability="web.search",
        resource_refs=("resource_pa06_search",),
        operations=("read",), data_classes=("public",), purpose="public.search",
        provider_policy=ProviderPolicy(("provider_public_web",), maximum_request_count=1),
        issued_at=now - timedelta(minutes=1), expires_at=now + timedelta(minutes=5), revision=1,
    )
    fetch = CapabilityGrant(
        grant_id="grant_pa06_web_fetch",
        owner_ref=search.owner_ref, connection_ref=search.connection_ref,
        capability="web.fetch", resource_refs=("resource_pa06_fetch",),
        operations=("read",), data_classes=("public",), purpose="public.fetch",
        provider_policy=ProviderPolicy(("provider_public_web",), maximum_request_count=fetch_count),
        issued_at=now - timedelta(minutes=1), expires_at=now + timedelta(minutes=5), revision=1,
    )
    registry = CapabilityRegistry((search, fetch))
    search_decision = registry.authorize_and_reserve(AuthorizationRequest(
        owner_ref=search.owner_ref, connection_ref=search.connection_ref, capability="web.search",
        resource_ref="resource_pa06_search", operation="read", data_class="public",
        provider_ref="provider_public_web", purpose="public.search", expected_grant_revision=1,
    ))
    fetches = tuple(registry.authorize_and_reserve(AuthorizationRequest(
        owner_ref=search.owner_ref, connection_ref=search.connection_ref, capability="web.fetch",
        resource_ref="resource_pa06_fetch", operation="read", data_class="public",
        provider_ref="provider_public_web", purpose="public.fetch", expected_grant_revision=1,
    )) for _ in range(fetch_count))
    return PublicWebAccess(
        search_authorization=search_decision, fetch_authorizations=fetches,
        owner_ref=search.owner_ref, connection_ref=search.connection_ref,
        search_resource_ref="resource_pa06_search", fetch_resource_ref="resource_pa06_fetch",
        public_query_digest="sha256:" + hashlib.sha256(" ".join(query.split()).encode()).hexdigest(),
    )


def _github_access(repository_ref="acme/project") -> GitHubReadAccess:
    now = datetime.now(timezone.utc)
    grant = CapabilityGrant(
        grant_id="grant_pa06_github", owner_ref="owner_pa06", connection_ref="connection_pa06",
        capability="github.repository_context", resource_refs=(repository_ref,), operations=("read",),
        data_classes=("public",), purpose="project.context",
        provider_policy=ProviderPolicy(("provider_github",), maximum_request_count=1),
        issued_at=now - timedelta(minutes=1), expires_at=now + timedelta(minutes=5), revision=1,
    )
    decision = CapabilityRegistry((grant,)).authorize_and_reserve(AuthorizationRequest(
        owner_ref=grant.owner_ref, connection_ref=grant.connection_ref, capability=grant.capability,
        resource_ref=repository_ref, operation="read", data_class="public", provider_ref="provider_github",
        purpose="project.context", expected_grant_revision=1,
    ))
    return GitHubReadAccess(
        authorization=decision, owner_ref=grant.owner_ref, connection_ref=grant.connection_ref, repository_ref=repository_ref,
    )


def _bounds():
    return PublicWebBounds(trusted_source_hosts=("docs.vendor.example",), max_fetches=1)


def test_research_combines_independent_sources_and_checked_project_identity(monkeypatch):
    monkeypatch.setattr("prm.public_web._reject_private_resolution", lambda _host: None)
    barrier = Barrier(3)
    archive = _Archive([{
        "archive_document_id": "tg:1", "source_url": "https://t.me/private/1",
        "snippet": "Archive evidence supports a replayable evaluation fixture.",
        "relevance_label": "direct", "supports_action": True,
    }], barrier)
    public_query = "vendor current release official"
    public = _Public(barrier=barrier)
    github = _GitHub(barrier=barrier)
    plan = build_research_plan(
        "What applies to my project? Private context Q-71.", archive_query="agent evaluation fixture",
        public_tasks=(PublicResearchTask(public_query, _public_access(public_query)),),
        github_access=_github_access(), project_name="Acme Project",
    )

    result = run_bounded_research(
        plan, original_query="What applies to my project? Private context Q-71.", archive_reader=archive,
        public_provider=public, public_bounds=_bounds(), github_provider=github,
    )

    assert result["status"] == "complete"
    assert {item["source_kind"] for item in result["facts"]} == {"archive", "public_primary", "github_repository_identity"}
    assert result["project_recommendations"][0]["statement"].endswith("acme/project@" + "a" * 40 + " before proposing a project change.")
    assert public.queries == [public_query]
    assert "Private context Q-71" not in repr(result["plan"])
    assert result["write_performed"] is False


def test_gap_expansion_is_local_bounded_and_provider_failure_is_partial(monkeypatch):
    monkeypatch.setattr("prm.public_web._reject_private_resolution", lambda _host: None)
    archive = _Archive([{
        "archive_document_id": "tg:context", "source_url": "https://t.me/private/context",
        "snippet": "Context only.", "relevance_label": "partial", "supports_action": False,
    }])
    public_query = "vendor current release official"
    plan = build_research_plan(
        "What practice applies?", archive_query="agent evals",
        public_tasks=(PublicResearchTask(public_query, _public_access(public_query)),),
        budget=ResearchBudget(max_tool_calls=4),
    )

    result = run_bounded_research(
        plan, original_query="What practice applies?", archive_reader=archive,
        public_provider=_Public(fail=True), public_bounds=_bounds(), github_provider=None,
    )

    assert result["status"] == "partial"
    assert len(archive.queries) == 2
    assert "agent evals harness regression fixture" in archive.queries[1][0]
    assert "search_failed" in result["coverage"]["source_gaps"]
    assert result["automatic_public_expansion"] is False


def test_cancellation_returns_resumable_checkpoint_without_starting_sources(monkeypatch):
    monkeypatch.setattr("prm.public_web._reject_private_resolution", lambda _host: None)
    archive = _Archive([{
        "archive_document_id": "tg:1", "source_url": "https://t.me/private/1",
        "snippet": "Direct evidence.", "relevance_label": "direct", "supports_action": True,
    }])
    public_query = "vendor current release official"
    public = _Public()
    plan = build_research_plan(
        "What is current?", archive_query="direct evidence",
        public_tasks=(PublicResearchTask(public_query, _public_access(public_query)),),
    )
    cancellation = ResearchCancellation()
    cancellation.cancel()

    cancelled = run_bounded_research(
        plan, original_query="What is current?", archive_reader=archive,
        public_provider=public, public_bounds=_bounds(), github_provider=None, cancellation=cancellation,
    )

    assert cancelled["coverage"]["state"] == "cancelled"
    assert archive.queries == [] and public.queries == []
    resumed = run_bounded_research(
        plan, original_query="What is current?", archive_reader=archive,
        public_provider=public, public_bounds=_bounds(), github_provider=None,
        checkpoint=cancelled["checkpoint"],
    )
    assert resumed["status"] == "complete"
    assert archive.queries and public.queries == [public_query]


def test_repository_identity_mismatch_cannot_create_project_recommendation():
    archive = _Archive([{
        "archive_document_id": "tg:1", "source_url": "https://t.me/private/1",
        "snippet": "Direct evidence.", "relevance_label": "direct", "supports_action": True,
    }])
    plan = build_research_plan(
        "What applies?", archive_query="direct evidence", github_access=_github_access(), project_name="Acme Project",
    )

    result = run_bounded_research(
        plan, original_query="What applies?", archive_reader=archive,
        public_provider=None, public_bounds=None,
        github_provider=_GitHub(repository_ref="attacker/other"),
    )

    assert result["status"] == "partial"
    assert "repository_identity_mismatch" in result["coverage"]["source_gaps"]
    assert result["project_recommendations"] == []


def test_nonzero_cost_budget_is_not_an_implicit_paid_provider_authorization():
    with pytest.raises(ValueError, match="nonzero cost"):
        ResearchBudget(max_cost_usd=0.01)
    with pytest.raises(ValueError, match="nonzero cost"):
        PublicResearchTask("vendor current release official", object(), estimated_cost_usd=0.01)


class _HttpResponse:
    def __init__(self, *, body, url):
        self._body = body
        self._url = url
        self.headers = SimpleNamespace(get_content_type=lambda: "application/json")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self._url

    def read(self, _limit):
        return self._body


def test_readonly_github_adapter_checks_fixed_endpoint_identity_without_env_token(monkeypatch):
    body = b'{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","url":"https://api.github.com/repos/acme/project/commits/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'
    seen = {}

    class _Opener:
        def open(self, req, *, timeout):
            seen["url"] = req.full_url
            seen["authorization"] = req.headers.get("Authorization")
            seen["timeout"] = timeout
            return _HttpResponse(body=body, url=req.full_url)

    monkeypatch.setattr("integrations.github_readonly.request.build_opener", lambda *_handlers: _Opener())
    result = ReadOnlyGitHubContextProvider().read_repository_context("acme/project")

    assert result == {"repository_ref": "acme/project", "commit_sha": "a" * 40, "ref": "HEAD", "summary": ""}
    assert seen["url"] == "https://api.github.com/repos/acme/project/commits/HEAD"
    assert seen["authorization"] is None


def test_readonly_github_adapter_rejects_mismatched_api_identity(monkeypatch):
    body = b'{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","url":"https://api.github.com/repos/attacker/other/commits/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'

    class _Opener:
        def open(self, req, *, timeout):
            return _HttpResponse(body=body, url=req.full_url)

    monkeypatch.setattr("integrations.github_readonly.request.build_opener", lambda *_handlers: _Opener())
    with pytest.raises(GitHubReadError, match="repository_identity_mismatch"):
        ReadOnlyGitHubContextProvider().read_repository_context("acme/project")
