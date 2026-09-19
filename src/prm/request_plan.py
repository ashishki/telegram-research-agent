"""Bounded, fail-closed scopes for PRM archive and public verification work."""

from __future__ import annotations

from typing import Any, Mapping


REQUEST_PLAN_SCHEMA_VERSION = "prm_request_plan.v1"
_PRIVATE_MARKERS = ("мой ", "моем ", "моём ", "my ", "profile", "профил", "архив", "archive", "telegram")


def build_request_plan(query: str, route: Mapping[str, Any], *, public_mode_consented: bool = False) -> dict[str, Any]:
    """Describe possible scopes without executing a provider or network call."""

    clean = " ".join(str(query or "").split())
    lowered = clean.casefold()
    archive_requested = bool(route.get("archive_scope"))
    public_requested = bool(route.get("external_verification_required"))
    private_context_requested = bool(route.get("project_context_required"))
    # PA-05 has a capability-gated public executor. A plan still never derives
    # a public query from operator prose or records it here: the runtime must
    # receive a separately minimized, scope-bound query with typed access.
    safe_public_query = ""
    public_execution_ready = public_requested and bool(public_mode_consented)
    return {
        "schema_version": REQUEST_PLAN_SCHEMA_VERSION,
        "archive": {"requested": archive_requested, "allowed": archive_requested, "execution": "local_only"},
        "private_context": {"requested": private_context_requested, "allowed": private_context_requested, "egress": False},
        "public_verification": {
            "requested": public_requested,
            "consent_preview_required": public_requested and not public_mode_consented,
            "consented_mode": bool(public_mode_consented),
            "allowed": public_execution_ready,
            "execution": "adapter_and_capability_required" if public_execution_ready else "capability_off",
            "query": safe_public_query,
            "query_redacted": public_requested and not bool(safe_public_query),
            # One discovery call plus at most four separately authorized
            # primary-document reads. Actual limits remain the narrower
            # runtime bounds and sealed reservation count.
            "max_calls": 5 if public_execution_ready else 0,
            "timeout_seconds": 30 if public_execution_ready else 0,
            "max_cost_usd": 0.0,
        },
        "primary_source_fixture_verification": {
            "allowed": False,
            "execution": "capability_off",
            "fixture_origin_only": True,
            "claim_upgrade_allowed": False,
        },
        "write_performed": False,
        "provider_egress": False,
    }
