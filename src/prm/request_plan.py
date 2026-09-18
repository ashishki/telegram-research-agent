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
    # PRM-SN-3A has no approved public-query executor.  A consent preview is
    # not egress consent, so never derive a query from operator prose here.
    # A later approved adapter must accept an independently constructed,
    # reviewed query field rather than reuse archive/profile input.
    safe_public_query = ""
    return {
        "schema_version": REQUEST_PLAN_SCHEMA_VERSION,
        "archive": {"requested": archive_requested, "allowed": archive_requested, "execution": "local_only"},
        "private_context": {"requested": private_context_requested, "allowed": private_context_requested, "egress": False},
        "public_verification": {
            "requested": public_requested,
            "consent_preview_required": public_requested and not public_mode_consented,
            "consented_mode": bool(public_mode_consented),
            "allowed": False,
            "execution": "capability_off",
            "query": safe_public_query,
            "query_redacted": public_requested and not bool(safe_public_query),
            "max_calls": 0,
            "timeout_seconds": 0,
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
