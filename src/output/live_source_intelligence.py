from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config.settings import PROJECT_ROOT
from output.opportunity_seed_export import classify_demand_surfaces
from output.reporting_period import ReportingPeriod
from output.source_events import DEFAULT_SOURCE_EVENT_ROOT


DEFAULT_LIVE_INTELLIGENCE_ROOT = PROJECT_ROOT / "data" / "output" / "live_source_intelligence"
SNAPSHOT_SCHEMA_VERSION = "live_source_intelligence.v1"


@dataclass(frozen=True)
class LiveSourceIntelligenceResult:
    week_label: str
    output_path: Path
    event_count: int
    repeated_claim_count: int
    pathway_available: bool


def build_live_source_intelligence_snapshot(
    *,
    days: int = 14,
    event_root: Path | str | None = None,
    output_path: Path | str | None = None,
    now: datetime | None = None,
    reporting_period: ReportingPeriod | None = None,
) -> LiveSourceIntelligenceResult:
    if reporting_period is not None and now is not None:
        raise ValueError("reporting_period cannot be combined with now")
    generated_at = (
        reporting_period.generated_at
        if reporting_period is not None
        else (now or datetime.now(timezone.utc))
    )
    generated_at = _as_utc(generated_at)
    if reporting_period is not None:
        window_start = reporting_period.analysis_period_start
        window_end = reporting_period.analysis_period_end
        window_days = max(
            1,
            math.ceil((window_end - window_start).total_seconds() / 86_400),
        )
        week_label = reporting_period.week_label
    else:
        window_days = max(1, int(days or 14))
        window_end = generated_at
        window_start = window_end - timedelta(days=window_days)
        week_label = _week_label(generated_at)
    root = Path(event_root) if event_root is not None else DEFAULT_SOURCE_EVENT_ROOT
    events = _load_events(root, window_start=window_start, window_end=window_end)
    snapshot = _build_snapshot(
        events,
        event_root=root,
        window_start=window_start,
        window_end=window_end,
        generated_at=generated_at,
        days=window_days,
    )
    if reporting_period is not None:
        snapshot.update(reporting_period.to_dict())
    target = Path(output_path) if output_path is not None else DEFAULT_LIVE_INTELLIGENCE_ROOT / f"{week_label}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return LiveSourceIntelligenceResult(
        week_label=week_label,
        output_path=target,
        event_count=len(events),
        repeated_claim_count=len(snapshot["repeated_claim_candidates"]),
        pathway_available=bool(snapshot["pathway"]["available"]),
    )


def load_live_source_intelligence(path: Path | str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("live source intelligence snapshot must be a JSON object")
    if payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("unsupported live source intelligence schema_version")
    return payload


def _build_snapshot(
    events: list[dict[str, Any]],
    *,
    event_root: Path,
    window_start: datetime,
    window_end: datetime,
    generated_at: datetime,
    days: int,
) -> dict[str, Any]:
    channel_counts: Counter[str] = Counter()
    channel_latest: dict[str, str] = {}
    channel_latest_time: dict[str, datetime] = {}
    surface_counts: Counter[str] = Counter()
    claim_events: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for event in events:
        channel = _text(event.get("channel_username")) or "unknown"
        channel_counts[channel] += 1
        posted_at = _text(event.get("posted_at"))
        posted_time = _event_time(event)
        if posted_at and posted_time is not None and (
            channel not in channel_latest_time or posted_time > channel_latest_time[channel]
        ):
            channel_latest[channel] = posted_at
            channel_latest_time[channel] = posted_time

        text = _text(event.get("text"))
        for surface in classify_demand_surfaces(text):
            surface_counts[surface] += 1
        claim = _normalized_claim(text)
        if claim:
            claim_events[claim].append(event)

    repeated_claims = _repeated_claim_candidates(claim_events)
    top_channels = [
        {
            "channel_username": channel,
            "event_count": count,
            "latest_posted_at": channel_latest.get(channel),
        }
        for channel, count in channel_counts.most_common(12)
    ]
    demand_surfaces = [
        {"surface": surface, "count": count}
        for surface, count in surface_counts.most_common(12)
    ]
    pathway_available = _pathway_available()
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "generation_mode": "deterministic_event_log",
        "source_event_root": str(event_root),
        "window": {
            "days": days,
            "start": window_start.isoformat().replace("+00:00", "Z"),
            "end": window_end.isoformat().replace("+00:00", "Z"),
        },
        "pathway": {
            "available": pathway_available,
            "status": "available" if pathway_available else "not_installed",
            "contract": "Pathway sidecar may consume the same JSONL event stream; this snapshot is the deterministic fallback.",
        },
        "events_scanned": len(events),
        "channels": top_channels,
        "demand_surfaces": demand_surfaces,
        "repeated_claim_candidates": repeated_claims,
        "radar_context": {
            "summary": _radar_summary(events, top_channels, demand_surfaces, repeated_claims),
            "top_channels": [item["channel_username"] for item in top_channels[:5]],
            "top_demand_surfaces": [item["surface"] for item in demand_surfaces[:5]],
            "repeated_claim_count": len(repeated_claims),
            "context_only": True,
        },
    }


def _load_events(
    event_root: Path,
    *,
    window_start: datetime,
    window_end: datetime,
) -> list[dict[str, Any]]:
    if not event_root.exists():
        return []
    events: list[dict[str, Any]] = []
    for path in sorted(event_root.glob("*.jsonl")):
        if not _date_file_overlaps(path, window_start=window_start, window_end=window_end):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            event_time = _event_time(event)
            if event_time is not None and window_start <= event_time < window_end:
                events.append(event)
    return _dedupe_events(events)


def _date_file_overlaps(path: Path, *, window_start: datetime, window_end: datetime) -> bool:
    try:
        file_date = datetime.fromisoformat(path.stem).date()
    except ValueError:
        return True
    return window_start.date() <= file_date <= window_end.date()


def _event_time(event: dict[str, Any]) -> datetime | None:
    # Reporting evidence belongs to the post's publication period. Capture time
    # remains provenance, but must not move a historical post into a later run.
    value = _text(event.get("posted_at")) or _text(event.get("captured_at"))
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must include an explicit timezone")
    return value.astimezone(timezone.utc)


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for event in events:
        upstream_id = _text(event.get("upstream_id"))
        if not upstream_id:
            continue
        by_id[upstream_id] = event
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(
        by_id.values(),
        key=lambda item: (
            _event_time(item) or minimum,
            _text(item.get("upstream_id")),
        ),
    )


def _normalized_claim(text: str) -> str:
    clean = re.sub(r"https?://\S+", " ", text.lower())
    clean = re.sub(r"[^a-zа-я0-9\s-]", " ", clean)
    tokens = [token for token in clean.split() if len(token) > 2]
    if len(tokens) < 5:
        return ""
    return " ".join(tokens[:18])


def _repeated_claim_candidates(claim_events: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for claim, events in claim_events.items():
        channels = sorted({_text(event.get("channel_username")) or "unknown" for event in events})
        if len(events) < 2 and len(channels) < 2:
            continue
        candidates.append(
            {
                "claim_key": _claim_key(claim),
                "normalized_claim": claim,
                "event_count": len(events),
                "channels": channels,
                "sample_event_ids": [_text(event.get("upstream_id")) for event in events[:5]],
            }
        )
    candidates.sort(key=lambda item: (-int(item["event_count"]), str(item["normalized_claim"])))
    return candidates[:20]


def _radar_summary(
    events: list[dict[str, Any]],
    channels: list[dict[str, Any]],
    demand_surfaces: list[dict[str, Any]],
    repeated_claims: list[dict[str, Any]],
) -> str:
    if not events:
        return "No live source events in the selected window."
    surface = demand_surfaces[0]["surface"] if demand_surfaces else "none"
    channel = channels[0]["channel_username"] if channels else "none"
    return (
        f"{len(events)} live source event(s); top_channel={channel}; "
        f"top_demand_surface={surface}; repeated_claim_candidates={len(repeated_claims)}. "
        "Context only; does not satisfy external evidence gates."
    )


def _pathway_available() -> bool:
    try:
        __import__("pathway")
    except ImportError:
        return False
    return True


def _claim_key(claim: str) -> str:
    import hashlib

    return "claim:" + hashlib.sha256(claim.encode("utf-8")).hexdigest()[:16]


def _week_label(value: datetime) -> str:
    year, week, _weekday = value.isocalendar()
    return f"{year}-W{week:02d}"


def _text(value: Any) -> str:
    return str(value or "").strip()
