"""Deterministic, supplied-status PRM operations view; it performs no probes."""
from __future__ import annotations
from typing import Any, Mapping

_SAFE = {"ok", "stale", "unavailable", "unknown"}

def build_prm_status(payload: Mapping[str, Any]) -> dict[str, Any]:
    def section(name: str) -> dict[str, str]:
        value = payload.get(name)
        status = str(value.get("status") if isinstance(value, Mapping) else "unknown")
        return {"status": status if status in _SAFE else "unknown"}
    return {"schema_version": "prm_status.v1", "health": section("health"), "freshness": section("freshness"), "reactions": section("reactions"), "vector": section("vector"), "budget": section("budget"), "secrets_exposed": False, "write_performed": False, "service_action": False}
