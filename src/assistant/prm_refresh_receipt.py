"""Privacy-safe operator projection for the already-approved archive refresh path."""

from __future__ import annotations

from typing import Any, Mapping


def build_operator_refresh_receipt(refresh_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Project refresh counts and safety flags without raw post text or local paths."""

    before = _mapping(refresh_payload.get("before"))
    after = _mapping(refresh_payload.get("after"))
    privacy = _mapping(refresh_payload.get("privacy"))
    status = str(refresh_payload.get("status") or "failed")
    return {
        "schema_version": "prm_operator_refresh_receipt.v1",
        "status": status,
        "new_posts": max(0, int(after.get("posts") or 0) - int(before.get("posts") or 0)),
        "channels_touched": int(refresh_payload.get("channels_touched") or 0),
        "latest_posted_at": str(after.get("max_posted_at") or ""),
        "reaction_summary": {"status": "not_run"},
        "enrichment": {"status": "not_run"},
        "boundaries": {
            "report_generation": False,
            "provider_egress": bool(privacy.get("provider_egress")),
            "migrations_run": bool(privacy.get("migrations_run")),
            "reaction_sync": bool(privacy.get("reaction_sync")),
            "vector_rebuild": bool(privacy.get("local_vector_sidecar_write")),
            "dogfood_evidence": bool(privacy.get("dogfood_evidence")),
            "release_claim": bool(privacy.get("release_claim")),
        },
    }


def build_refresh_failure_receipt() -> dict[str, Any]:
    """Failure is observable while preserving the existing archive and prohibited-work boundary."""

    return {
        "schema_version": "prm_operator_refresh_receipt.v1",
        "status": "failed",
        "new_posts": 0,
        "channels_touched": 0,
        "latest_posted_at": "",
        "reaction_summary": {"status": "not_run"},
        "enrichment": {"status": "not_run"},
        "boundaries": {
            "report_generation": False,
            "provider_egress": False,
            "migrations_run": False,
            "reaction_sync": False,
            "vector_rebuild": False,
            "dogfood_evidence": False,
            "release_claim": False,
        },
    }


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
