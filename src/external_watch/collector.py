"""Feature-flagged source-bounded UTD shadow collector. No delivery path."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .adapters import AdapterError, canonical_hash, parse_html_document, parse_localist
from .fetch import FetchError, safe_fetch
from .profile import load_confirmed_utd_profile
from .relevance import classify
from .selection import select_candidates
from .store import ShadowStore

SOURCE_URLS = {
    "calendar": "https://calendar.utdallas.edu/api/2/events?days=14&pp=100&page=1",
    "isso": "https://isso.utdallas.edu/",
    "basic_needs": "https://basicneeds.utdallas.edu/resource-hub/",
}


@dataclass(frozen=True)
class ShadowRunResult:
    enabled: bool
    profile_loaded: bool
    changes: tuple[dict[str, Any], ...]
    candidates: tuple[dict[str, Any], ...]
    source_status: Mapping[str, str]


class ShadowCollector:
    def __init__(self, *, prm_db: str | Path, sidecar_db: str | Path, enabled: bool = False):
        self.prm_db = Path(prm_db)
        self.store = ShadowStore(sidecar_db)
        self.enabled = bool(enabled)

    def run_once(self) -> ShadowRunResult:
        if not self.enabled:
            return ShadowRunResult(False, False, (), (), {})
        profile = load_confirmed_utd_profile(self.prm_db)
        if not profile or profile.get("paused"):
            return ShadowRunResult(True, bool(profile), (), (), {})
        selected = set(profile.get("categories") or []) - set(profile.get("muted_sources") or [])
        sources = []
        if selected & {"program", "career", "ai", "spouse_family"}:
            sources.append("calendar")
        if "isso" in selected:
            sources.append("isso")
        if "benefits" in selected:
            sources.append("basic_needs")
        changes: list[dict[str, Any]] = []
        status: dict[str, str] = {}
        for source in sources:
            try:
                fetched = safe_fetch(SOURCE_URLS[source])
                if source == "calendar":
                    items = parse_localist(fetched.body)
                else:
                    items = parse_html_document(fetched.body, source=source, canonical_url=SOURCE_URLS[source])
                rel = {str(item["item_key"]): classify(item, profile) for item in items}
                hashes = {str(item["item_key"]): canonical_hash(item) for item in items}
                changes.extend(self.store.apply_success(source, items, hashes, rel))
                status[source] = "ok"
            except (FetchError, AdapterError) as exc:
                code = getattr(exc, "code", "schema_drift")
                self.store.health(source, "error", error_code=code, detail=str(exc)[:500])
                status[source] = code
        candidates = select_candidates(changes, profile)
        return ShadowRunResult(True, True, tuple(changes), tuple(candidates), status)
