import hashlib
import html
import json
import re
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import urlparse

from config.settings import PROJECT_ROOT, Settings
from db.ai_report_feedback import summarize_ai_report_feedback
from db.frontier_analysis import fetch_frontier_analysis
from output.idea_threads import _thread_terms as _idea_thread_terms
from output.report_quality import (
    MATCHES_TRACE_RE,
    ReportQualityFinding,
    SEVERITY_CRITICAL,
)
from output.reporting_period import (
    EXPLICIT_ISO_WEEK,
    PARTIAL_ISO_WEEK,
    TRAILING_SEVEN_DAYS,
    ReportingPeriod,
    format_human_period_label,
    format_period_display_label,
    register_reporting_period_sqlite,
    reporting_timestamp_sort_key,
    resolve_reporting_period,
)


OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "ai_intelligence"
REQUIRED_SECTIONS = (
    ("executive-brief", "Executive Brief"),
    ("frontier-analysis", "Frontier Analysis"),
    ("what-changed", "What Changed This Week"),
    ("idea-evolution", "Idea Evolution Timelines"),
    ("tools-models-practices", "Tools, Models, and Practices"),
    ("contradictions", "Contradictions and Unresolved Claims"),
    ("read-queue", "Read Queue"),
    ("try-this-week", "Try This Week"),
    ("source-map", "Source Map"),
    ("appendix", "Appendix: grouped source posts"),
)
READ_QUEUE_TYPES = {"tutorial_resource", "case_study", "research_claim", "benchmark_claim"}
PERSONAL_READ_TARGET_COUNT = 5
PERSONAL_TRY_TARGET_COUNT = 2
REACTION_RECEIPT_ITEM_LIMIT = 4


@dataclass(frozen=True)
class AiIntelligenceReportSummary:
    week_label: str
    generated_at: str
    html_path: str
    json_path: str
    thread_count: int
    source_atom_count: int
    source_channel_count: int
    action_count: int
    quality_finding_count: int
    notification_text: str
    run_date: str = ""
    reporting_week: str = ""
    period_mode: str = ""
    analysis_period_start: str = ""
    analysis_period_end: str = ""


class AiIntelligenceReportQualityError(ValueError):
    def __init__(self, findings: list[ReportQualityFinding]) -> None:
        self.findings = findings
        messages = "; ".join(f"{finding.artifact_type}: {finding.message}" for finding in findings)
        super().__init__(f"AI Intelligence report failed quality gates: {messages}")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _current_week_label(now: datetime | None = None) -> str:
    current = now or _utc_now()
    year, week, _ = current.isocalendar()
    return f"{year}-W{week:02d}"


def _week_bounds(week_label: str) -> tuple[datetime, datetime]:
    year_str, week_str = str(week_label).split("-W", maxsplit=1)
    start_date = date.fromisocalendar(int(year_str), int(week_str), 1)
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    return start, start + timedelta(days=7)


def _iso_for_sql(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _explicit_utc_timestamp(value: datetime | str, *, field_name: str) -> datetime:
    """Parse a caller-owned timestamp without accepting an implicit timezone."""

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{field_name} must not be empty")
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be an ISO-8601 UTC timestamp") from exc
    else:
        raise TypeError(f"{field_name} must be a datetime or ISO-8601 string")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include an explicit UTC offset")
    return parsed.astimezone(timezone.utc)


def _parse_array(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _thread_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": int(row["id"]),
        "title": str(row["title"] or ""),
        "slug": str(row["slug"] or ""),
        "summary": str(row["summary"] or ""),
        "status": str(row["status"] or "active"),
        "first_seen_at": str(row["first_seen_at"] or ""),
        "last_seen_at": str(row["last_seen_at"] or ""),
        "momentum_7d": float(row["momentum_7d"] or 0.0),
        "momentum_30d": float(row["momentum_30d"] or 0.0),
        "momentum_90d": float(row["momentum_90d"] or 0.0),
        "atom_count": int(row["atom_count"] or 0),
        "source_channel_count": int(row["source_channel_count"] or 0),
        "source_channels": _parse_array(row["source_channels_json"]),
        "key_entities": _parse_array(row["key_entities_json"]),
        "current_claims": _parse_array(row["current_claims_json"]),
        "superseded_claims": _parse_array(row["superseded_claims_json"]),
        "contradictions": _parse_array(row["contradictions_json"]),
    }


def _atom_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": int(row["id"]),
        "relation": str(row["relation"] or "supports"),
        "week_label": str(row["week_label"] or ""),
        "atom_type": str(row["atom_type"] or ""),
        "claim": str(row["claim"] or ""),
        "summary": str(row["summary"] or ""),
        "evidence_quote": str(row["evidence_quote"] or ""),
        "source_post_ids": _parse_array(row["source_post_ids_json"]),
        "source_urls": _parse_array(row["source_urls_json"]),
        "entities": _parse_array(row["entities_json"]),
        "tools": _parse_array(row["tools_json"]),
        "models": _parse_array(row["models_json"]),
        "practices": _parse_array(row["practices_json"]),
        "confidence": float(row["confidence"] or 0.0),
        "novelty_score": float(row["novelty_score"] or 0.0),
        "practical_utility_score": float(row["practical_utility_score"] or 0.0),
        "staleness_status": str(row["staleness_status"] or "active"),
        "why_it_matters": str(row["why_it_matters"] or ""),
        "first_seen_at": str(row["first_seen_at"] or ""),
        "last_seen_at": str(row["last_seen_at"] or ""),
    }


def _load_thread_atoms(
    connection: sqlite3.Connection,
    *,
    thread_id: int,
    analysis_period_end: datetime,
) -> list[dict]:
    rows = connection.execute(
        """
        SELECT
            idea_thread_atoms.relation,
            knowledge_atoms.*
        FROM idea_thread_atoms
        JOIN knowledge_atoms ON knowledge_atoms.id = idea_thread_atoms.atom_id
        WHERE idea_thread_atoms.thread_id = ?
          AND reporting_utc_micros(knowledge_atoms.last_seen_at) < reporting_utc_micros(?)
        ORDER BY reporting_utc_micros(knowledge_atoms.last_seen_at) DESC, knowledge_atoms.id DESC
        """,
        (
            int(thread_id),
            _iso_for_sql(analysis_period_end),
        ),
    ).fetchall()
    return [_atom_from_row(row) for row in rows]


def _attach_source_posts(
    connection: sqlite3.Connection,
    atoms: list[dict],
    *,
    analysis_period_end: datetime,
) -> None:
    if not atoms or not _table_exists(connection, "posts"):
        return
    source_ids: list[int] = []
    for atom in atoms:
        for value in atom.get("source_post_ids") or []:
            try:
                post_id = int(value)
            except (TypeError, ValueError):
                continue
            if post_id not in source_ids:
                source_ids.append(post_id)
    if not source_ids:
        return
    placeholders = ",".join("?" for _ in source_ids)
    has_raw_posts = _table_exists(connection, "raw_posts")
    if has_raw_posts:
        rows = connection.execute(
            f"""
            SELECT
                posts.id AS post_id,
                posts.content,
                posts.channel_username,
                posts.posted_at,
                raw_posts.message_url,
                raw_posts.text AS raw_text
            FROM posts
            LEFT JOIN raw_posts ON raw_posts.id = posts.raw_post_id
            WHERE posts.id IN ({placeholders})
              AND reporting_utc_micros(posts.posted_at) < reporting_utc_micros(?)
            """,
            [*source_ids, _iso_for_sql(analysis_period_end)],
        ).fetchall()
    else:
        rows = connection.execute(
            f"""
            SELECT
                posts.id AS post_id,
                posts.content,
                posts.channel_username,
                posts.posted_at,
                NULL AS message_url,
                NULL AS raw_text
            FROM posts
            WHERE posts.id IN ({placeholders})
              AND reporting_utc_micros(posts.posted_at) < reporting_utc_micros(?)
            """,
            [*source_ids, _iso_for_sql(analysis_period_end)],
        ).fetchall()
    source_posts = {
        int(row["post_id"]): {
            "post_id": int(row["post_id"]),
            "content": str(row["content"] or row["raw_text"] or ""),
            "channel_username": str(row["channel_username"] or ""),
            "posted_at": str(row["posted_at"] or ""),
            "message_url": str(row["message_url"] or ""),
        }
        for row in rows
    }
    for atom in atoms:
        linked = []
        for value in atom.get("source_post_ids") or []:
            try:
                post_id = int(value)
            except (TypeError, ValueError):
                continue
            post = source_posts.get(post_id)
            if post:
                linked.append(post)
        atom["source_posts"] = linked


def _legacy_reporting_period(week_label: str, generated_at: datetime | None = None) -> ReportingPeriod:
    """Build an unchecked period for legacy context-only callers.

    Weekly artifact entry points resolve and validate periods before calling the
    loader. A few older projections still call the loader directly with only a
    week label, so this adapter preserves that API without weakening generator
    validation.
    """

    current = (generated_at or _utc_now()).astimezone(timezone.utc).replace(microsecond=0)
    period_start, period_end = _week_bounds(week_label)
    return ReportingPeriod(
        run_date=current.date(),
        generated_at=current,
        analysis_period_start=period_start,
        analysis_period_end=period_end,
        reporting_week=week_label,
        period_mode=EXPLICIT_ISO_WEEK,
    )


def _context_period_fields(period: ReportingPeriod) -> dict[str, str]:
    fields = period.to_dict()
    # Retain the V1 aliases consumed by the canonical delta projection.
    fields["week_start"] = fields["analysis_period_start"]
    fields["week_end"] = fields["analysis_period_end"]
    return fields


def _frontier_analysis_for_period(
    connection: sqlite3.Connection,
    *,
    reporting_period: ReportingPeriod,
    canonical_snapshot_fingerprint: str | None = None,
) -> dict | None:
    analysis = fetch_frontier_analysis(
        connection,
        week_label=reporting_period.reporting_week,
    )
    if not analysis:
        return None
    source_context = (analysis.get("analysis") or {}).get("source_context") or {}
    expected = reporting_period.to_dict()
    identity_fields = (
        "reporting_week",
        "week_label",
        "period_mode",
        "analysis_period_start",
        "analysis_period_end",
    )
    if any(
        str(source_context.get(field) or "") != str(expected[field])
        for field in identity_fields
    ):
        return None
    stored_canonical_fingerprint = (
        str(source_context.get("canonical_thread_snapshot_fingerprint") or "") or None
    )
    if stored_canonical_fingerprint != canonical_snapshot_fingerprint:
        return None
    return analysis


def _unique_strings(values) -> list[str]:
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _claims_as_of(atoms: list[dict], *, current: bool) -> list[str]:
    claims: list[str] = []
    non_current = {"superseded", "resolved", "hype_only", "stale"}
    for atom in sorted(
        atoms,
        key=lambda item: reporting_timestamp_sort_key(item.get("last_seen_at")),
        reverse=True,
    ):
        is_current = str(atom.get("staleness_status") or "active") not in non_current
        if is_current != current:
            continue
        claim = str(atom.get("claim") or "").strip()
        if claim and claim not in claims:
            claims.append(claim)
        if len(claims) >= 6:
            break
    return claims


def _thread_status_as_of(atoms: list[dict], *, period_end: datetime, source_channel_count: int) -> str:
    statuses = {str(atom.get("staleness_status") or "active") for atom in atoms}
    non_current = {"superseded", "resolved", "hype_only", "stale"}
    if statuses and all(status in non_current for status in statuses):
        for status in ("superseded", "resolved", "hype_only", "stale"):
            if status in statuses:
                return status
    last_seen = [_parse_iso(atom.get("last_seen_at")) for atom in atoms]
    observed = [value for value in last_seen if value is not None]
    if observed and max(observed) < period_end - timedelta(days=30):
        return "stale"
    average_utility = sum(float(atom.get("practical_utility_score") or 0.0) for atom in atoms) / max(1, len(atoms))
    if len(atoms) >= 3 and source_channel_count >= 2 and average_utility >= 0.75:
        return "production_pattern"
    return "active"


def _momentum_as_of(atoms: list[dict], *, period_end: datetime, days: int, saturation: int) -> float:
    cutoff = period_end - timedelta(days=days)
    count = sum(
        1
        for atom in atoms
        if (observed := _parse_iso(atom.get("last_seen_at"))) is not None and observed >= cutoff
    )
    return min(1.0, count / max(1, saturation))


def _project_thread_as_of(thread: dict, atoms: list[dict], *, period_end: datetime) -> dict:
    """Replace mutable all-time thread aggregates with bounded atom state."""

    source_channels = sorted(
        {
            _source_channel(url)
            for atom in atoms
            for url in (atom.get("source_urls") or [])
            if _source_channel(url)
        }
    )
    current_claims = _claims_as_of(atoms, current=True)
    superseded_claims = _claims_as_of(atoms, current=False)
    summary_claim = current_claims[0] if current_claims else (superseded_claims[0] if superseded_claims else "")
    contradictions = _unique_strings(
        atom.get("claim")
        for atom in atoms
        if atom.get("atom_type") in {"risk_warning", "opinion_shift"}
        or any(
            marker in str(atom.get("claim") or "").lower()
            for marker in (" not ", " risk", " fails", " broken", " contradict")
        )
    )[:6]
    display_terms: list[str] = []
    historical_slugs: list[str] = []
    for atom in sorted(
        atoms,
        key=lambda item: (
            reporting_timestamp_sort_key(item.get("last_seen_at")),
            int(item.get("id") or 0),
        ),
    ):
        slug_terms, atom_terms = _idea_thread_terms(atom)
        historical_slugs.append("-".join(slug_terms) or f"atom-{int(atom.get('id') or 0)}")
        for term in atom_terms:
            if term not in display_terms:
                display_terms.append(term)
    key_entities = display_terms[:8]
    historical_slug = (
        sorted(Counter(historical_slugs).items(), key=lambda item: (-item[1], item[0]))[0][0]
        if historical_slugs
        else str(thread.get("slug") or "")
    )
    first_seen_values = [str(atom.get("first_seen_at") or "") for atom in atoms if atom.get("first_seen_at")]
    last_seen_values = [str(atom.get("last_seen_at") or "") for atom in atoms if atom.get("last_seen_at")]
    bounded = {
        **thread,
        "slug": historical_slug,
        "title": " / ".join(display_terms[:3]) or historical_slug,
        "summary": (
            f"{len(atoms)} atoms across {len(source_channels)} source channel(s)."
            + (f" Latest: {summary_claim}" if summary_claim else "")
        ),
        "first_seen_at": (
            min(first_seen_values, key=reporting_timestamp_sort_key)
            if first_seen_values
            else ""
        ),
        "last_seen_at": (
            max(last_seen_values, key=reporting_timestamp_sort_key)
            if last_seen_values
            else ""
        ),
        "momentum_7d": _momentum_as_of(atoms, period_end=period_end, days=7, saturation=5),
        "momentum_30d": _momentum_as_of(atoms, period_end=period_end, days=30, saturation=12),
        "momentum_90d": _momentum_as_of(atoms, period_end=period_end, days=90, saturation=24),
        "atom_count": len(atoms),
        "source_channel_count": len(source_channels),
        "source_channels": source_channels,
        "key_entities": key_entities,
        "current_claims": current_claims,
        "superseded_claims": superseded_claims,
        "contradictions": contradictions,
        "atoms": atoms,
    }
    bounded["status"] = _thread_status_as_of(
        atoms,
        period_end=period_end,
        source_channel_count=len(source_channels),
    )
    return bounded


def _canonical_atoms_as_of(
    connection: sqlite3.Connection,
    *,
    canonical_thread_id: str,
    analysis_period_end: datetime,
) -> list[dict]:
    """Load the complete versioned membership before applying display caps."""

    rows = connection.execute(
        """
        SELECT history.relation, knowledge_atoms.*
        FROM canonical_idea_thread_atom_history AS history
        JOIN knowledge_atoms ON knowledge_atoms.id = history.atom_id
        WHERE history.canonical_thread_id = ?
          AND reporting_utc_micros(history.valid_from) < reporting_utc_micros(?)
          AND (
              history.valid_to IS NULL
              OR reporting_utc_micros(history.valid_to) >= reporting_utc_micros(?)
          )
          AND reporting_utc_micros(knowledge_atoms.last_seen_at) < reporting_utc_micros(?)
        ORDER BY reporting_utc_micros(knowledge_atoms.last_seen_at) DESC,
                 knowledge_atoms.id DESC
        """,
        (
            canonical_thread_id,
            _iso_for_sql(analysis_period_end),
            _iso_for_sql(analysis_period_end),
            _iso_for_sql(analysis_period_end),
        ),
    ).fetchall()
    return [_atom_from_row(row) for row in rows]


def _canonical_snapshot_payload(
    threads: Sequence[Mapping[str, object]],
    *,
    analysis_period_end: datetime,
) -> dict[str, object]:
    identity = []
    for thread in threads:
        aliases = []
        for alias in thread.get("aliases") or []:
            if isinstance(alias, Mapping):
                aliases.append(
                    (
                        str(alias.get("alias_type") or ""),
                        str(alias.get("alias_value") or alias.get("value") or ""),
                    )
                )
            else:
                aliases.append(("legacy_ref", str(alias or "")))
        identity.append(
            {
                "canonical_thread_id": thread.get("canonical_thread_id"),
                "stable_slug": thread.get("stable_slug"),
                "version": thread.get("version") or thread.get("current_version"),
                "title_ru": thread.get("title_ru"),
                "title_en": thread.get("title_en"),
                "thesis": thread.get("thesis"),
                "status": thread.get("status"),
                "first_seen_at": thread.get("first_seen_at"),
                "last_seen_at": thread.get("last_seen_at"),
                "evidence_maturity": thread.get("evidence_maturity"),
                "operator_interest": thread.get("operator_interest"),
                "curator_version": thread.get("curator_version"),
                "atom_ids": sorted(int(value) for value in thread.get("atom_ids") or []),
                "aliases": sorted(aliases),
                "merged_from": sorted(str(value) for value in thread.get("merged_from") or []),
                "split_from": sorted(str(value) for value in thread.get("split_from") or []),
                # Frontier cache identity includes the exact bounded fields its
                # unchanged prompt serializer consumes, not only atom IDs.
                "frontier_projection": {
                    "slug": thread.get("slug"),
                    "title": thread.get("title"),
                    "status": thread.get("status"),
                    "first_seen_at": thread.get("first_seen_at"),
                    "last_seen_at": thread.get("last_seen_at"),
                    "momentum_7d": thread.get("momentum_7d"),
                    "momentum_30d": thread.get("momentum_30d"),
                    "momentum_90d": thread.get("momentum_90d"),
                    "atom_count": thread.get("atom_count"),
                    "current_claims": list(thread.get("current_claims") or [])[:6],
                    "superseded_claims": list(
                        thread.get("superseded_claims") or []
                    )[:4],
                    "contradictions": list(thread.get("contradictions") or [])[:4],
                    "atoms": [
                        {
                            "id": atom.get("id"),
                            "type": atom.get("atom_type"),
                            "claim": atom.get("claim"),
                            "summary": atom.get("summary"),
                            "why_it_matters": atom.get("why_it_matters"),
                            "confidence": atom.get("confidence"),
                            "novelty": atom.get("novelty_score"),
                            "utility": atom.get("practical_utility_score"),
                            "last_seen_at": atom.get("last_seen_at"),
                        }
                        for atom in list(thread.get("atoms") or [])[:8]
                        if isinstance(atom, Mapping)
                    ],
                },
            }
        )
    identity.sort(key=lambda item: str(item.get("canonical_thread_id") or ""))
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": "canonical_idea_threads.snapshot.v1",
        "as_of": _iso_for_sql(analysis_period_end),
        "thread_count": len(identity),
        "canonical_thread_ids": [
            str(item["canonical_thread_id"])
            for item in identity
            if str(item.get("canonical_thread_id") or "").strip()
        ],
        "fingerprint": "sha256:" + hashlib.sha256(encoded).hexdigest(),
    }


def _canonical_threads_as_of(
    connection: sqlite3.Connection,
    *,
    analysis_period_start: datetime,
    analysis_period_end: datetime,
    atoms_limit: int,
    primary_limit: int = 12,
) -> tuple[list[dict], dict[str, object], list[dict]]:
    """Return bounded primary canonical rows plus the complete audit snapshot."""

    required = (
        "canonical_idea_threads",
        "canonical_idea_thread_versions",
        "canonical_idea_thread_atom_history",
    )
    if any(not _table_exists(connection, table) for table in required):
        return [], {}, []
    from db.canonical_idea_threads import fetch_canonical_threads

    stored_threads = fetch_canonical_threads(
        connection,
        as_of=_iso_for_sql(analysis_period_end),
        limit=501,
        include_atoms=False,
    )
    if len(stored_threads) > 500:
        raise ValueError("canonical registry exceeds the bounded 500-thread snapshot")
    projected: list[dict] = []
    for stored in stored_threads:
        thread = dict(stored)
        canonical_id = str(thread.get("canonical_thread_id") or "").strip()
        stable_slug = str(thread.get("stable_slug") or "").strip()
        if not canonical_id or not stable_slug:
            continue
        all_atoms = _canonical_atoms_as_of(
            connection,
            canonical_thread_id=canonical_id,
            analysis_period_end=analysis_period_end,
        )
        source_channels = sorted(
            {
                _source_channel(url)
                for atom in all_atoms
                for url in atom.get("source_urls") or []
                if _source_channel(url)
            }
        )
        current_claims = _claims_as_of(all_atoms, current=True)
        superseded_claims = _claims_as_of(all_atoms, current=False)
        contradictions = _unique_strings(
            atom.get("claim")
            for atom in all_atoms
            if atom.get("atom_type") in {"risk_warning", "opinion_shift"}
        )[:6]
        aliases = [
            dict(alias) if isinstance(alias, Mapping) else alias
            for alias in thread.get("aliases") or thread.get("raw_thread_aliases") or []
        ]
        atom_ids = [int(atom["id"]) for atom in all_atoms]
        source_post_ids = sorted(
            {
                int(value)
                for atom in all_atoms
                for value in atom.get("source_post_ids") or []
                if str(value).strip().isdigit()
            }
        )
        source_urls = _unique_strings(
            value for atom in all_atoms for value in atom.get("source_urls") or []
        )
        title = str(thread.get("title_ru") or thread.get("title_en") or stable_slug)
        projection = {
            **thread,
            "id": canonical_id,
            "canonical_thread_id": canonical_id,
            "canonical_thread_ref": f"canonical_thread:{stable_slug}",
            "stable_slug": stable_slug,
            # Legacy-shaped fields let existing bounded consumers read the
            # canonical projection without renaming raw compatibility rows.
            "slug": stable_slug,
            "title": title,
            "summary": str(thread.get("thesis") or ""),
            "aliases": aliases,
            "atom_ids": atom_ids,
            "source_post_ids": source_post_ids,
            "source_urls": source_urls,
            "source_refs": source_urls,
            "atom_count": len(all_atoms),
            "source_channel_count": len(source_channels),
            "source_channels": source_channels,
            "key_entities": list(thread.get("entities") or []),
            "current_claims": current_claims,
            "superseded_claims": superseded_claims,
            "contradictions": contradictions,
            "momentum_7d": _momentum_as_of(
                all_atoms, period_end=analysis_period_end, days=7, saturation=5
            ),
            "momentum_30d": _momentum_as_of(
                all_atoms, period_end=analysis_period_end, days=30, saturation=12
            ),
            "momentum_90d": _momentum_as_of(
                all_atoms, period_end=analysis_period_end, days=90, saturation=24
            ),
            "changed_this_week": (
                any(
                    (observed := _parse_iso(atom.get("last_seen_at"))) is not None
                    and analysis_period_start <= observed < analysis_period_end
                    for atom in all_atoms
                )
                or (
                    (version_at := _parse_iso(thread.get("valid_from"))) is not None
                    and analysis_period_start <= version_at < analysis_period_end
                )
                or any(
                    (event_at := _parse_iso(item.get("event_at"))) is not None
                    and analysis_period_start <= event_at < analysis_period_end
                    for item in thread.get("lineage") or []
                    if isinstance(item, Mapping)
                )
            ),
            "atoms": all_atoms[: max(1, int(atoms_limit or 8))],
        }
        _attach_source_posts(
            connection,
            projection["atoms"],
            analysis_period_end=analysis_period_end,
        )
        projected.append(projection)

    snapshot = (
        _canonical_snapshot_payload(
            projected,
            analysis_period_end=analysis_period_end,
        )
        if projected
        else {}
    )
    primary = [
        thread
        for thread in projected
        if str(thread.get("status") or "active") in {"active", "stale"}
        and thread.get("atom_ids")
    ]
    primary.sort(key=lambda item: str(item.get("stable_slug") or ""))
    primary.sort(
        key=lambda item: reporting_timestamp_sort_key(item.get("last_seen_at")),
        reverse=True,
    )
    primary.sort(key=lambda item: bool(item.get("changed_this_week")), reverse=True)
    primary.sort(key=lambda item: str(item.get("status") or "active") == "active", reverse=True)
    return primary[: max(1, min(12, int(primary_limit or 12)))], snapshot, projected


def _attach_canonical_compatibility_refs(
    raw_threads: Sequence[dict],
    canonical_threads: Sequence[Mapping[str, object]],
) -> None:
    owners_by_atom: dict[int, set[tuple[str, str]]] = {}
    for canonical in canonical_threads:
        canonical_id = str(canonical.get("canonical_thread_id") or "").strip()
        stable_slug = str(canonical.get("stable_slug") or "").strip()
        if not canonical_id or not stable_slug:
            continue
        for atom_id in canonical.get("atom_ids") or []:
            owners_by_atom.setdefault(int(atom_id), set()).add((canonical_id, stable_slug))
    for thread in raw_threads:
        atom_ids = {
            int(atom.get("id") or 0)
            for atom in thread.get("_delta_atoms") or thread.get("atoms") or []
            if int(atom.get("id") or 0) > 0
        }
        owners = sorted(
            {owner for atom_id in atom_ids for owner in owners_by_atom.get(atom_id, set())}
        )
        thread["canonical_thread_ids"] = [item[0] for item in owners]
        thread["canonical_thread_refs"] = [f"canonical_thread:{item[1]}" for item in owners]
        thread["canonical_stable_slugs"] = [item[1] for item in owners]
        if len(owners) == 1:
            thread["canonical_thread_id"] = owners[0][0]
            thread["canonical_thread_ref"] = f"canonical_thread:{owners[0][1]}"
            thread["canonical_stable_slug"] = owners[0][1]
            thread["canonical_resolution_status"] = "canonical_membership_resolved"
        else:
            thread["canonical_thread_id"] = None
            thread["canonical_thread_ref"] = None
            thread["canonical_stable_slug"] = None
            thread["canonical_resolution_status"] = (
                "canonical_membership_ambiguous"
                if owners
                else "compatibility_current_thread_only"
            )


def _canonical_thread_sidecar(
    thread: Mapping[str, object],
    *,
    provenance_limit: int = 100,
) -> dict[str, object]:
    """Return the bounded public DTO; full provenance remains queryable in DB."""

    clean_limit = max(1, min(100, int(provenance_limit or 100)))
    result = {
        str(key): value
        for key, value in thread.items()
        if not str(key).startswith("_")
    }
    atom_ids = list(result.get("atom_ids") or [])
    source_post_ids = list(result.get("source_post_ids") or [])
    source_urls = list(result.get("source_urls") or [])
    source_refs = list(result.get("source_refs") or [])
    result.update(
        {
            "atom_ids": atom_ids[:clean_limit],
            "source_post_ids": source_post_ids[:clean_limit],
            "source_urls": source_urls[:clean_limit],
            "source_refs": source_refs[:clean_limit],
            "provenance_counts": {
                "atom_ids": len(atom_ids),
                "source_post_ids": len(source_post_ids),
                "source_urls": len(source_urls),
            },
            "provenance_truncated": any(
                len(values) > clean_limit
                for values in (atom_ids, source_post_ids, source_urls, source_refs)
            ),
        }
    )
    return result


def _feedback_context_for_report(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    feedback_snapshot: datetime | None,
) -> dict:
    if _table_exists(connection, "ai_report_feedback_events"):
        return summarize_ai_report_feedback(
            connection,
            before_week_label=week_label,
            created_before=feedback_snapshot,
        )
    return {
        "event_count": 0,
        "counts_by_feedback": {},
        "downranked_thread_slugs": [],
        "downranked_atom_refs": [],
        "downranked_target_refs": [],
        "promoted_target_refs": [],
        "missed_post_eval_examples": [],
        "priority_eval_examples": [],
        "feedback_eval_examples": [],
        "feedback_completion": {
            "completed": False,
            "completed_count": 0,
            "required_count": 4,
            "missing": ["read_items", "action_outcome", "missed_or_no_missed", "trust_correction"],
            "read_event_count": 0,
            "action_event_count": 0,
            "has_missed_or_no_missed": False,
            "trust_correction_count": 0,
        },
        "feedback_changes": {
            "status": "unknown",
            "summary": "No prior feedback is available; personalization state is unknown.",
            "items": ["No confirmed feedback has changed ranking yet; no-feedback is not a negative signal."],
            "downranked": [],
            "promoted": [],
            "eval_example_count": 0,
        },
        "feedback_corrections": [],
        "feedback_effect_traces": [],
        "confirmed_event_count": 0,
        "pending_draft_count": 0,
        "confirmation_state": "confirmed_only",
        "frontier_prompt_guidance": ["No prior feedback is available; state unknown personalization confidence."],
        "recent_events": [],
    }


def load_ai_intelligence_context(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    reporting_period: ReportingPeriod | None = None,
    reaction_snapshot_at: datetime | str | None = None,
    feedback_snapshot_at: datetime | str | None = None,
    reaction_snapshot_binding: dict | None = None,
    reaction_snapshot: dict | None = None,
    feedback_snapshot_usable: bool = True,
    threads_limit: int = 8,
    atoms_limit: int = 8,
) -> dict:
    connection.row_factory = sqlite3.Row
    register_reporting_period_sqlite(connection)
    period = reporting_period or _legacy_reporting_period(week_label)
    if period.week_label != str(week_label).strip():
        raise ValueError("week_label must match reporting_period.week_label")
    period_fields = _context_period_fields(period)
    reaction_snapshot_cutoff = (
        period.generated_at
        if reaction_snapshot_at is None
        else _explicit_utc_timestamp(reaction_snapshot_at, field_name="reaction_snapshot_at")
    )
    reaction_snapshot_iso = _iso_for_sql(reaction_snapshot_cutoff)
    feedback_snapshot = (
        None
        if feedback_snapshot_at is None
        else _explicit_utc_timestamp(
            feedback_snapshot_at,
            field_name="feedback_snapshot_at",
        )
    )
    feedback_context = _feedback_context_for_report(
        connection,
        week_label=week_label,
        feedback_snapshot=feedback_snapshot,
    )
    canonical_threads, canonical_snapshot, canonical_audit_threads = (
        _canonical_threads_as_of(
            connection,
            analysis_period_start=period.analysis_period_start,
            analysis_period_end=period.analysis_period_end,
            atoms_limit=atoms_limit,
            primary_limit=min(12, max(1, int(threads_limit or 8))),
        )
    )
    if not _table_exists(connection, "idea_threads") or not _table_exists(connection, "idea_thread_atoms"):
        result = {
            **period_fields,
            "reaction_snapshot_at": reaction_snapshot_iso,
            "feedback_snapshot_at": (
                _iso_for_sql(feedback_snapshot) if feedback_snapshot is not None else None
            ),
            "feedback_snapshot_usable": bool(feedback_snapshot_usable),
            "threads": [],
            "compatibility_threads": [],
            "canonical_threads": canonical_threads,
            "canonical_thread_snapshot": canonical_snapshot,
            "source_channels": [],
            "marked_posts": [],
            "frontier_analysis": None,
            "compressed_context": [],
            "feedback_context": feedback_context,
        }
        if reaction_snapshot_binding is not None:
            _threads, reaction_effect, reaction_effects = _personalize_report_surfaces(
                connection,
                reporting_period=period,
                snapshot_binding=reaction_snapshot_binding,
                snapshot=reaction_snapshot,
                baseline_candidates=[],
                feedback_context=feedback_context,
                limit=max(1, int(threads_limit or 8)),
                receipt_limit=REACTION_RECEIPT_ITEM_LIMIT,
                feedback_snapshot_usable=feedback_snapshot_usable,
            )
            if reaction_effect is not None:
                result["reaction_effect"] = reaction_effect
                result["reaction_effects"] = reaction_effects
                result["reaction_ranking_context"] = dict(feedback_context)
        return result

    week_start = period.analysis_period_start
    week_end = period.analysis_period_end
    week_end_sql = _iso_for_sql(week_end)
    rows = connection.execute(
        """
        SELECT idea_threads.*
        FROM idea_threads
        WHERE EXISTS (
            SELECT 1
            FROM idea_thread_atoms
            JOIN knowledge_atoms ON knowledge_atoms.id = idea_thread_atoms.atom_id
            WHERE idea_thread_atoms.thread_id = idea_threads.id
              AND reporting_utc_micros(knowledge_atoms.last_seen_at) < reporting_utc_micros(?)
        )
        """,
        (week_end_sql,),
    ).fetchall()
    threads = []
    for row in rows:
        thread = _thread_from_row(row)
        all_atoms = _load_thread_atoms(
            connection,
            thread_id=thread["id"],
            analysis_period_end=week_end,
        )
        if not all_atoms:
            continue
        thread = _project_thread_as_of(thread, all_atoms, period_end=week_end)
        thread["changed_this_week"] = _thread_changed_this_week(thread, week_start, week_end)
        # Delta calculation needs the complete bounded history even when the
        # reader-facing atom list is intentionally compressed.
        thread["_delta_atoms"] = all_atoms
        thread["atoms"] = all_atoms[: max(1, int(atoms_limit or 8))]
        _attach_source_posts(
            connection,
            thread["atoms"],
            analysis_period_end=week_end,
        )
        threads.append(thread)
    _attach_canonical_compatibility_refs(threads, canonical_audit_threads)
    # Match the established ordering using only the bounded as-of projection.
    threads.sort(key=lambda item: str(item.get("title") or ""))
    threads.sort(key=lambda item: int(item.get("atom_count") or 0), reverse=True)
    threads.sort(
        key=lambda item: reporting_timestamp_sort_key(item.get("last_seen_at")),
        reverse=True,
    )
    threads.sort(key=lambda item: int(item.get("source_channel_count") or 0), reverse=True)
    threads.sort(key=lambda item: float(item.get("momentum_30d") or 0.0), reverse=True)
    threads.sort(key=lambda item: bool(item.get("changed_this_week")), reverse=True)
    selected_limit = max(1, int(threads_limit or 8))
    reaction_effect = None
    reaction_ranking_context = None
    if reaction_snapshot_binding is not None:
        reaction_feedback_context = dict(feedback_context)
        reaction_feedback_context["_thread_feedback_scores"] = {
            str(thread.get("slug") or ""): _thread_feedback_score(
                thread,
                feedback_context,
            )
            for thread in threads
            if str(thread.get("slug") or "").strip()
        }
        reaction_ranking_context = reaction_feedback_context
        threads, reaction_effect, reaction_effects = _personalize_report_surfaces(
            connection,
            reporting_period=period,
            snapshot_binding=reaction_snapshot_binding,
            snapshot=reaction_snapshot,
            baseline_candidates=threads,
            feedback_context=reaction_feedback_context,
            limit=selected_limit,
            receipt_limit=min(REACTION_RECEIPT_ITEM_LIMIT, selected_limit),
            feedback_snapshot_usable=feedback_snapshot_usable,
        )
    else:
        threads = threads[:selected_limit]
    result = {
        **period_fields,
        "reaction_snapshot_at": reaction_snapshot_iso,
        "feedback_snapshot_at": (
            _iso_for_sql(feedback_snapshot) if feedback_snapshot is not None else None
        ),
        "feedback_snapshot_usable": bool(feedback_snapshot_usable),
        "threads": threads,
        "compatibility_threads": threads,
        "canonical_threads": canonical_threads,
        "canonical_thread_snapshot": canonical_snapshot,
        "source_channels": _source_channel_counts(threads),
        "marked_posts": _marked_posts_for_period(
            connection,
            reporting_period=period,
            reaction_snapshot_at=reaction_snapshot_cutoff,
        ),
        "frontier_analysis": (
            _frontier_analysis_for_period(
                connection,
                reporting_period=period,
                canonical_snapshot_fingerprint=(
                    str(canonical_snapshot.get("fingerprint") or "") or None
                ),
            )
            if _table_exists(connection, "frontier_analyses")
            else None
        ),
        "compressed_context": _compressed_context(threads),
        "feedback_context": feedback_context,
    }
    if reaction_effect is not None:
        result["reaction_effect"] = reaction_effect
        result["reaction_effects"] = reaction_effects
        result["reaction_ranking_context"] = reaction_ranking_context
    return result


def _personalize_report_surfaces(
    connection: sqlite3.Connection,
    *,
    reporting_period: ReportingPeriod,
    snapshot_binding: Mapping[str, object],
    snapshot: Mapping[str, object] | None,
    baseline_candidates: list[dict],
    feedback_context: Mapping[str, object],
    limit: int,
    receipt_limit: int,
    feedback_snapshot_usable: bool,
) -> tuple[list[dict], dict | None, dict[str, dict]]:
    """Classify effects against the exact bounded Brief and Atlas selectors."""

    from output.idea_thread_curator import StoredCanonicalThreadResolver
    from output.reaction_personalization import personalize_thread_candidates

    def brief_projection(values: Sequence[Mapping[str, object]]) -> list[str]:
        actions = _learning_actions(
            [dict(value) for value in values],
            dict(feedback_context),
        )
        return [
            str(action.get("surface_item_ref") or "").strip()
            for action in actions[:4]
            if str(action.get("surface_item_ref") or "").strip()
        ]

    def atlas_projection(values: Sequence[Mapping[str, object]]) -> list[str]:
        return [
            f"thread:{str(value.get('slug') or '').strip()}"
            for value in _reaction_ranked_threads_for_navigation(
                values,
                feedback_context,
                limit=12,
            )
            if str(value.get("slug") or "").strip()
        ]

    common = {
        "reporting_period": reporting_period,
        "snapshot_binding": snapshot_binding,
        "snapshot": snapshot,
        "baseline_candidates": baseline_candidates,
        "feedback_context": feedback_context,
        "limit": limit,
        "receipt_limit": receipt_limit,
        "feedback_snapshot_usable": feedback_snapshot_usable,
        "thread_resolver": StoredCanonicalThreadResolver(
            connection,
            as_of=_iso_for_sql(reporting_period.analysis_period_end),
        ),
    }
    ordered, brief_effect = personalize_thread_candidates(
        connection,
        **common,
        selection_projector=brief_projection,
        receipt_surface="weekly_brief",
    )
    atlas_ordered, atlas_effect = personalize_thread_candidates(
        connection,
        **common,
        selection_projector=atlas_projection,
        receipt_surface="knowledge_atlas",
    )
    if [item.get("id") for item in ordered] != [item.get("id") for item in atlas_ordered]:
        raise RuntimeError("reaction personalization produced divergent surface order")
    effects = {
        effect["surface"]: effect
        for effect in (brief_effect, atlas_effect)
        if isinstance(effect, dict)
    }
    return ordered, brief_effect, effects


def _thread_changed_this_week(thread: dict, week_start: datetime, week_end: datetime) -> bool:
    for atom in thread.get("atoms") or []:
        last_seen = _parse_iso(atom.get("last_seen_at"))
        if last_seen and week_start <= last_seen < week_end:
            return True
    return False


def _compressed_context(threads: list[dict]) -> list[dict]:
    context = []
    for thread in threads:
        context.append(
            {
                "slug": thread["slug"],
                "title": thread["title"],
                "status": thread["status"],
                "momentum_7d": thread["momentum_7d"],
                "momentum_30d": thread["momentum_30d"],
                "source_channels": thread["source_channels"][:8],
                "current_claims": thread["current_claims"][:5],
                "superseded_claims": thread["superseded_claims"][:3],
                "contradictions": thread["contradictions"][:3],
                "source_atom_ids": [atom["id"] for atom in thread.get("atoms") or []],
            }
        )
    return context


def _source_channel(url: str) -> str:
    parsed = urlparse(str(url or ""))
    if parsed.netloc.endswith("t.me"):
        parts = [part for part in parsed.path.split("/") if part]
        if parts:
            return parts[0]
    return parsed.netloc or "unknown"


def _source_channel_counts(threads: list[dict]) -> list[dict]:
    counts: Counter[str] = Counter()
    for thread in threads:
        for atom in thread.get("atoms") or []:
            for url in atom.get("source_urls") or []:
                counts[_source_channel(url)] += 1
    return [
        {"channel": channel, "count": count}
        for channel, count in counts.most_common()
        if channel
    ]


def _marked_posts_for_period(
    connection: sqlite3.Connection,
    *,
    reporting_period: ReportingPeriod,
    reaction_snapshot_at: datetime,
    limit: int = 8,
) -> list[dict]:
    required_tables = ("signal_feedback", "posts", "raw_posts")
    if not all(_table_exists(connection, table_name) for table_name in required_tables):
        return []
    rows = connection.execute(
        """
        SELECT
            signal_feedback.feedback,
            signal_feedback.recorded_at,
            posts.id AS post_id,
            posts.channel_username,
            posts.posted_at,
            posts.content,
            raw_posts.message_url
        FROM signal_feedback
        JOIN posts ON posts.id = signal_feedback.post_id
        LEFT JOIN raw_posts ON raw_posts.id = posts.raw_post_id
        WHERE signal_feedback.feedback IN ('operator_marked_interesting', 'marked_important')
          AND reporting_utc_micros(posts.posted_at) >= reporting_utc_micros(?)
          AND reporting_utc_micros(posts.posted_at) < reporting_utc_micros(?)
          AND reporting_utc_micros(signal_feedback.recorded_at) <= reporting_utc_micros(?)
        ORDER BY reporting_utc_micros(signal_feedback.recorded_at) DESC, signal_feedback.id DESC
        LIMIT ?
        """,
        (
            _iso_for_sql(reporting_period.analysis_period_start),
            _iso_for_sql(reporting_period.analysis_period_end),
            _iso_for_sql(reaction_snapshot_at),
            max(1, int(limit or 8)),
        ),
    ).fetchall()
    return [
        {
            "post_id": int(row["post_id"]),
            "feedback": str(row["feedback"] or ""),
            "recorded_at": str(row["recorded_at"] or ""),
            "posted_at": str(row["posted_at"] or ""),
            "channel_username": str(row["channel_username"] or ""),
            "content": str(row["content"] or ""),
            "source_url": str(row["message_url"] or ""),
        }
        for row in rows
    ]


def _all_atoms(threads: list[dict]) -> list[dict]:
    atoms = []
    seen = set()
    for thread in threads:
        for atom in thread.get("atoms") or []:
            if atom["id"] in seen:
                continue
            seen.add(atom["id"])
            atoms.append(atom)
    return atoms


def _term_counts(threads: list[dict], field: str) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for atom in _all_atoms(threads):
        for term in atom.get(field) or []:
            counts[term] += 1
    return counts.most_common(12)


def _changed_threads(threads: list[dict]) -> list[dict]:
    return [thread for thread in threads if thread.get("changed_this_week")]


GENERIC_FEEDBACK_REFS = {
    "report",
    "weekly-report",
    "claim-cards",
    "read-queue",
    "missed-post",
    "action",
    "experiment",
}


def _feedback_ref_terms(feedback: dict, *keys: str) -> set[str]:
    terms: set[str] = set()
    for key in keys:
        for raw in feedback.get(key) or []:
            text = str(raw or "").strip().lower()
            if not text:
                continue
            candidates = {text}
            if ":" in text:
                candidates.add(text.split(":", maxsplit=1)[1])
                candidates.add(text.rsplit(":", maxsplit=1)[-1])
            for candidate in candidates:
                clean = candidate.strip()
                if len(clean) < 3 or clean in GENERIC_FEEDBACK_REFS:
                    continue
                terms.add(clean)
                terms.add(clean.replace("-", " ").replace("_", " "))
    return {term for term in terms if len(term) >= 3}


def _matches_feedback_term(text: str, terms: set[str]) -> bool:
    haystack = f" {str(text or '').lower()} "
    normalized = haystack.replace("-", " ").replace("_", " ")
    return any(term in haystack or term in normalized for term in terms)


def _thread_search_text(thread: dict) -> str:
    parts = [
        thread.get("slug") or "",
        thread.get("title") or "",
        thread.get("summary") or "",
        " ".join(thread.get("current_claims") or []),
        " ".join(thread.get("superseded_claims") or []),
    ]
    for atom in thread.get("atoms") or []:
        parts.extend(
            [
                atom.get("claim") or "",
                atom.get("summary") or "",
                atom.get("why_it_matters") or "",
                " ".join(atom.get("entities") or []),
                " ".join(atom.get("tools") or []),
                " ".join(atom.get("practices") or []),
            ]
        )
    return " ".join(parts)


def _thread_feedback_score(thread: dict, feedback: dict) -> int:
    slug = str(thread.get("slug") or "").strip().lower()
    promoted_refs = {str(value or "").strip().lower() for value in feedback.get("promoted_target_refs") or []}
    downranked_refs = {str(value or "").strip().lower() for value in feedback.get("downranked_target_refs") or []}
    score = 0
    if slug and f"idea_thread:{slug}" in promoted_refs:
        score += 2
    downranked_slugs = {str(value or "").strip().lower() for value in feedback.get("downranked_thread_slugs") or []}
    if slug and (f"idea_thread:{slug}" in downranked_refs or slug in downranked_slugs):
        score -= 2
    text = _thread_search_text(thread)
    if _matches_feedback_term(text, _feedback_ref_terms(feedback, "promoted_target_refs")):
        score += 1
    if _matches_feedback_term(text, _feedback_ref_terms(feedback, "downranked_target_refs", "downranked_thread_slugs")):
        score -= 1
    return score


def _atom_search_text(atom: dict, thread: dict) -> str:
    return " ".join(
        [
            str(atom.get("id") or ""),
            atom.get("claim") or "",
            atom.get("summary") or "",
            atom.get("why_it_matters") or "",
            " ".join(atom.get("entities") or []),
            " ".join(atom.get("tools") or []),
            " ".join(atom.get("practices") or []),
            thread.get("slug") or "",
            thread.get("title") or "",
        ]
    )


def _atom_feedback_score(atom: dict, thread: dict, feedback: dict) -> int:
    atom_id = str(atom.get("id") or "").strip()
    promoted_refs = {str(value or "").strip().lower() for value in feedback.get("promoted_target_refs") or []}
    downranked_refs = {str(value or "").strip().lower() for value in feedback.get("downranked_target_refs") or []}
    score = _thread_feedback_score(thread, feedback)
    if atom_id:
        if f"knowledge_atom:{atom_id}" in promoted_refs or f"read_queue:atom:{atom_id}" in promoted_refs:
            score += 2
        if f"knowledge_atom:{atom_id}" in downranked_refs or f"read_queue:atom:{atom_id}" in downranked_refs:
            score -= 2
    text = _atom_search_text(atom, thread)
    if _matches_feedback_term(text, _feedback_ref_terms(feedback, "promoted_target_refs")):
        score += 1
    if _matches_feedback_term(text, _feedback_ref_terms(feedback, "downranked_target_refs", "downranked_atom_refs")):
        score -= 1
    return score


def _ranking_factor(label: str, value: object, weight: str, evidence: object | None = None) -> dict:
    return {
        "label": label,
        "value": value,
        "weight": weight,
        "evidence": evidence,
    }


def _atom_ranking_factors(atom: dict, thread: dict, feedback: dict) -> list[dict]:
    feedback_score = _atom_feedback_score(atom, thread, feedback)
    factors = [
        _ranking_factor("practical_utility", round(float(atom.get("practical_utility_score") or 0.0), 3), "high"),
        _ranking_factor("novelty", round(float(atom.get("novelty_score") or 0.0), 3), "medium"),
        _ranking_factor("confidence", round(float(atom.get("confidence") or 0.0), 3), "medium"),
        _ranking_factor("freshness", str(atom.get("last_seen_at") or "")[:10], "medium"),
        _ranking_factor("source_refs", len(atom.get("source_urls") or []), "high", atom.get("source_urls") or []),
        _ranking_factor("feedback_score", feedback_score, "high", _feedback_factor_evidence(feedback)),
    ]
    if thread.get("slug"):
        factors.append(_ranking_factor("thread", thread.get("slug"), "medium"))
    return factors


def _thread_ranking_factors(thread: dict, feedback: dict) -> list[dict]:
    feedback_score = _thread_feedback_score(thread, feedback)
    return [
        _ranking_factor("momentum_30d", round(float(thread.get("momentum_30d") or 0.0), 3), "medium"),
        _ranking_factor("source_channel_count", int(thread.get("source_channel_count") or 0), "medium"),
        _ranking_factor("status", thread.get("status") or "active", "medium"),
        _ranking_factor("feedback_score", feedback_score, "high", _feedback_factor_evidence(feedback)),
    ]


def _feedback_factor_evidence(feedback: dict) -> dict:
    return {
        "promoted": list(feedback.get("promoted_target_refs") or [])[:5],
        "downranked": list(feedback.get("downranked_target_refs") or [])[:5],
        "event_count": int(feedback.get("event_count") or 0),
        "confirmation_state": feedback.get("confirmation_state") or "confirmed_only",
    }


def _why_selected_from_factors(factors: list[dict]) -> str:
    feedback = next((factor for factor in factors if factor.get("label") == "feedback_score"), {})
    feedback_value = int(feedback.get("value") or 0)
    if feedback_value > 0:
        return "Selected because confirmed feedback promoted similar targets, with source-backed utility still checked."
    if feedback_value < 0:
        return "Kept only with caution because confirmed feedback downranked a related target."
    source_refs = next((factor for factor in factors if factor.get("label") == "source_refs"), {})
    source_count = int(source_refs.get("value") or 0)
    utility = next((factor for factor in factors if factor.get("label") == "practical_utility"), {})
    if source_count > 0:
        return f"Selected for source-backed utility ({utility.get('value', 'unknown')}) with no confirmed feedback override."
    return "Selected as a fallback because no stronger source-backed personalized item was available."


def _read_queue_atoms(threads: list[dict], feedback_context: dict | None = None) -> list[dict]:
    feedback = feedback_context or {}
    downranked_threads = set(feedback.get("downranked_thread_slugs") or [])
    downranked_atoms = {str(value) for value in feedback.get("downranked_atom_refs") or []}
    atoms = []
    seen = set()
    for thread in threads:
        if thread.get("slug") in downranked_threads:
            continue
        for atom in thread.get("atoms") or []:
            atom_id = str(atom.get("id") or "")
            if atom_id in downranked_atoms or atom_id in seen:
                continue
            seen.add(atom_id)
            scored_atom = dict(atom)
            scored_atom["_feedback_score"] = _atom_feedback_score(atom, thread, feedback)
            scored_atom["_ranking_factors"] = _atom_ranking_factors(atom, thread, feedback)
            scored_atom["_why_selected"] = _why_selected_from_factors(scored_atom["_ranking_factors"])
            atoms.append(scored_atom)
    preferred = [atom for atom in atoms if atom.get("atom_type") in READ_QUEUE_TYPES]
    fallback = [atom for atom in atoms if atom.get("atom_type") not in READ_QUEUE_TYPES]

    def score_key(atom: dict) -> tuple[float, float, float, float, str]:
        return (
            float(atom.get("_feedback_score") or 0.0),
            float(atom.get("practical_utility_score") or 0.0),
            float(atom.get("novelty_score") or 0.0),
            float(atom.get("confidence") or 0.0),
            str(atom.get("last_seen_at") or ""),
        )

    preferred.sort(key=score_key, reverse=True)
    fallback.sort(key=score_key, reverse=True)
    candidates = preferred + fallback
    return candidates[:PERSONAL_READ_TARGET_COUNT]


def _primary_source_url(atom: dict) -> str:
    urls = atom.get("source_urls") or []
    return str(urls[0]) if urls else ""


def _personal_learning_loop(
    threads: list[dict],
    actions: list[dict],
    feedback_context: dict | None = None,
) -> dict:
    feedback = feedback_context or {}
    read_atoms = _read_queue_atoms(threads, feedback)
    read_items = [
        {
            "atom_id": atom.get("id"),
            "claim": atom.get("claim") or "Untitled source",
            "summary": atom.get("summary") or atom.get("why_it_matters") or "",
            "source_url": _primary_source_url(atom),
            "ranking_factors": atom.get("_ranking_factors") or [],
            "why_selected": atom.get("_why_selected") or "",
        }
        for atom in read_atoms[:PERSONAL_READ_TARGET_COUNT]
    ]
    while len(read_items) < PERSONAL_READ_TARGET_COUNT:
        slot = len(read_items) + 1
        read_items.append(
            {
                "atom_id": None,
                "claim": f"Open read slot {slot}",
                "summary": "Backfill this slot by running Knowledge Atom extraction for the current week.",
                "source_url": "",
                "ranking_factors": [
                    _ranking_factor("fallback", "open_slot", "low"),
                    _ranking_factor("feedback_score", 0, "high", _feedback_factor_evidence(feedback)),
                ],
                "why_selected": "Open slot because no source-backed read target was available; no-feedback is unknown, not negative.",
            }
        )

    term_candidates: list[dict] = []
    for label, field in (("Tool", "tools"), ("Workflow", "practices")):
        for term, count in _term_counts(threads, field):
            term_candidates.append({"kind": label, "name": term, "count": count})
    seen_terms = set()
    try_items = []
    for item in term_candidates:
        key = str(item["name"]).lower()
        if key in seen_terms:
            continue
        seen_terms.add(key)
        try_items.append(
            {
                "title": f"{item['kind']}: {item['name']}",
                "body": f"Try it against one current workflow and note whether it changes speed, quality, or review effort.",
                "source_count": item["count"],
                "ranking_factors": [
                    _ranking_factor("term_kind", item["kind"], "medium"),
                    _ranking_factor("source_mentions", item["count"], "medium"),
                    _ranking_factor("feedback_score", 0, "high", _feedback_factor_evidence(feedback)),
                ],
                "why_selected": "Selected because the term appears in curated source atoms and has no confirmed feedback override.",
            }
        )
        if len(try_items) >= PERSONAL_TRY_TARGET_COUNT:
            break
    fallback_try = [
        {
            "title": "Workflow: source-grounded eval checklist",
            "body": "Apply the strongest thread claim to a tiny eval checklist before trusting agent output.",
            "source_count": 0,
            "ranking_factors": [_ranking_factor("fallback", "source_grounded_eval", "low")],
            "why_selected": "Fallback workflow when source-backed personalized try items are sparse.",
        },
        {
            "title": "Workflow: weekly read/try note",
            "body": "Turn one read item into a short implementation note with source links and a next action.",
            "source_count": 0,
            "ranking_factors": [_ranking_factor("fallback", "weekly_read_try_note", "low")],
            "why_selected": "Fallback workflow to preserve the read-to-action loop.",
        },
    ]
    for item in fallback_try:
        if len(try_items) >= PERSONAL_TRY_TARGET_COUNT:
            break
        try_items.append(item)

    first_action = actions[0] if actions else {}
    missed_examples = feedback.get("missed_post_eval_examples") or []
    if missed_examples:
        experiment_title = "Convert one missed post into an eval example"
        experiment_body = "Use missed-post feedback to add a concrete example to next week's report evaluation checklist."
    else:
        action_title = str(first_action.get("title") or "Backfill the knowledge layer")
        experiment_title = f"30-minute experiment: {action_title.replace('Verify and apply: ', '')}"
        experiment_body = str(first_action.get("body") or "Run extraction and refresh Idea Threads before the next report.")

    counts = feedback.get("counts_by_feedback") or {}
    if int(counts.get("too_shallow") or 0) > 0:
        skill_gap = "Source verification depth: improve evidence checks before adopting a claim."
    elif int(counts.get("wrong_priority") or 0) > 0:
        skill_gap = "Priority calibration: connect each trial to an active engineering workflow."
    elif read_atoms:
        skill_gap = "Synthesis discipline: turn read items into source-backed engineering notes."
    else:
        skill_gap = "Knowledge coverage: extract enough atoms to fill the weekly read queue."

    if int(feedback.get("event_count") or 0) > 0:
        reflection = "Which feedback signal changed this week's priorities, and should it become a standing scoring rule?"
    else:
        reflection = "Which read or try item produced a reusable AI systems engineering pattern?"

    return {
        "read_items": read_items,
        "try_items": try_items[:PERSONAL_TRY_TARGET_COUNT],
        "small_experiment": {"title": experiment_title, "body": experiment_body},
        "skill_gap": skill_gap,
        "reflection_question": reflection,
    }


def _learning_actions(threads: list[dict], feedback_context: dict | None = None) -> list[dict]:
    feedback = feedback_context or {}
    downranked = set(feedback.get("downranked_thread_slugs") or [])
    counts = feedback.get("counts_by_feedback") or {}
    missed_examples = feedback.get("missed_post_eval_examples") or []
    depth_note = ""
    if int(counts.get("too_shallow") or 0) > 0:
        depth_note = " Recent feedback asked for deeper evidence, so verify source quality before applying it."
    priority_note = ""
    if int(counts.get("wrong_priority") or 0) > 0:
        priority_note = " Recent feedback flagged priority drift, so tie the trial to an active workflow."
    actions = []
    def action_order_key(thread: Mapping[str, object]) -> tuple[object, ...]:
        return (
            _thread_feedback_score(dict(thread), feedback),
            thread.get("status") == "production_pattern",
            float(thread.get("momentum_30d") or 0.0),
            int(thread.get("source_channel_count") or 0),
        )

    baseline_seeded = sorted(
        threads,
        key=lambda thread: int(
            thread.get("_reaction_baseline_position")
            if isinstance(thread.get("_reaction_baseline_position"), int)
            else len(threads)
        ),
    )
    ranked = sorted(
        (
            thread
            for thread in baseline_seeded
            if thread.get("slug") not in downranked
            and thread.get("status") not in {"hype_only", "resolved"}
        ),
        key=action_order_key,
        reverse=True,
    )
    # IRX-3 is one weak adjacent promotion inside the exact Brief action
    # selector.  Existing evidence/feedback sorting remains untouched when the
    # marker is absent, and unequal stronger keys can never be crossed.
    from output.reaction_personalization import reaction_close_order_key

    index = 1
    while index < len(ranked):
        candidate = ranked[index]
        previous = ranked[index - 1]
        if (
            candidate.get("_reaction_interest") is True
            and previous.get("_reaction_interest") is not True
            and action_order_key(candidate) == action_order_key(previous)
            and reaction_close_order_key(candidate, feedback)
            == reaction_close_order_key(previous, feedback)
        ):
            ranked[index - 1], ranked[index] = candidate, previous
            index += 1
            continue
        index += 1
    for thread in ranked:
        title = thread.get("title") or thread.get("slug") or "Untitled thread"
        claims = thread.get("current_claims") or thread.get("superseded_claims") or []
        ranking_factors = _thread_ranking_factors(thread, feedback)
        actions.append(
            {
                "title": f"Verify and apply: {title}",
                "thread_slug": thread.get("slug"),
                "surface_item_ref": f"thread:{thread.get('slug')}",
                "body": (
                    "Pick one source-backed claim from this thread, verify the cited posts, "
                    "and turn it into a 30-minute read/try note."
                    f"{depth_note}{priority_note}"
                ),
                "claim": claims[0] if claims else "",
                "source_count": len({url for atom in thread.get("atoms") or [] for url in atom.get("source_urls") or []}),
                "ranking_factors": ranking_factors,
                "why_selected": _why_selected_from_factors(ranking_factors),
            }
        )
        if len(actions) >= 4:
            break
    if missed_examples and len(actions) < 4:
        example = missed_examples[0]
        source_url = example.get("source_url") or "the missed source"
        actions.append(
            {
                "title": "Convert missed-post feedback into an eval example",
                "body": (
                    f"Review {source_url}, decide which report section missed it, "
                    "and add the pattern to next week's evaluation checklist."
                ),
                "claim": example.get("notes") or "",
                "source_count": 1 if example.get("source_url") else 0,
                "ranking_factors": [
                    _ranking_factor("missed_post_eval_example", example.get("source_url") or example.get("target_ref"), "high"),
                    _ranking_factor("feedback_score", 1, "high", _feedback_factor_evidence(feedback)),
                ],
                "why_selected": "Selected because confirmed missed-post feedback created an eval example for the next report.",
            }
        )
    if not actions:
        actions.append(
            {
                "title": "Backfill the knowledge layer",
                "body": "Run Knowledge Atom extraction and Idea Thread refresh before the next weekly report.",
                "claim": "",
                "source_count": 0,
                "ranking_factors": [_ranking_factor("fallback", "knowledge_layer_backfill", "low")],
                "why_selected": "Fallback action because no ranked source-backed thread action was available.",
            }
        )
    return actions


def _reaction_ranked_threads_for_navigation(
    threads: Sequence[Mapping[str, object]],
    feedback_context: Mapping[str, object] | None = None,
    *,
    limit: int = 12,
) -> list[dict]:
    """Apply one IRX-3 tie promotion inside the exact Atlas navigation cap."""

    values = [dict(thread) for thread in threads]
    ranked = sorted(
        values,
        key=lambda thread: int(
            thread.get("_reaction_baseline_position")
            if isinstance(thread.get("_reaction_baseline_position"), int)
            else len(values)
        ),
    )
    from output.reaction_personalization import reaction_close_order_key

    boundary = min(len(ranked), max(1, int(limit or 1)) + 1)
    index = 1
    while index < boundary:
        candidate = ranked[index]
        previous = ranked[index - 1]
        if (
            candidate.get("_reaction_interest") is True
            and previous.get("_reaction_interest") is not True
            and _thread_feedback_score(candidate, dict(feedback_context or {}))
            == _thread_feedback_score(previous, dict(feedback_context or {}))
            and reaction_close_order_key(candidate, feedback_context or {})
            == reaction_close_order_key(previous, feedback_context or {})
        ):
            ranked[index - 1], ranked[index] = candidate, previous
            index += 1
            continue
        index += 1
    return ranked[: max(1, int(limit or 1))]


def _status_label(status: str) -> str:
    return str(status or "active").replace("_", " ")


def _safe_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return slug or "item"


def _escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _reaction_effect_for_surface(context: dict, surface: str) -> dict | None:
    effects = context.get("reaction_effects")
    if isinstance(effects, Mapping):
        surface_effect = effects.get(surface)
        if isinstance(surface_effect, dict):
            from output.reaction_personalization import validate_reaction_effect

            return validate_reaction_effect(surface_effect)
    raw = context.get("reaction_effect")
    if not isinstance(raw, dict) or raw.get("schema_version") != "reaction_personalization.v1":
        return None
    from output.reaction_personalization import reaction_effect_for_surface

    return reaction_effect_for_surface(raw, surface=surface)


def _render_reaction_effect_receipt(context: dict, surface: str) -> str:
    """Render only deterministic Russian totals; audit identities stay in JSON."""

    effect = _reaction_effect_for_surface(context, surface)
    if effect is None:
        return ""
    status = str(effect.get("status") or "")
    snapshot_status = str(effect.get("snapshot_status") or "")
    counts = effect.get("counts") if isinstance(effect.get("counts"), dict) else {}
    events = max(0, int(counts.get("personal_reaction_events_detected") or 0))
    posts = max(
        0,
        int(
            counts.get("unique_reacted_posts")
            if status == "partial" and snapshot_status == "complete"
            else counts.get("posts_resolved")
            or 0
        ),
    )
    posts_label = (
        "постов с подтверждёнными реакциями"
        if status == "partial" and snapshot_status == "complete"
        else "найдено постов"
    )
    atoms = max(0, int(counts.get("unique_atoms_linked") or 0))
    canonical_threads = max(
        0,
        int(counts.get("unique_canonical_threads_linked") or 0),
    )
    compatibility_threads = max(
        0,
        int(counts.get("unique_compatibility_threads_linked") or 0),
    )
    threads = canonical_threads or compatibility_threads
    influenced = max(0, int(counts.get("selected_signals_influenced") or 0))
    selected_linked = max(0, int(counts.get("selected_items_linked") or 0))
    linked_only = max(0, selected_linked - influenced)
    unconsumed = max(0, int(counts.get("unconsumed_reaction_events") or 0))
    if status in {"partial", "unavailable"}:
        if snapshot_status == "complete":
            if events:
                message = (
                    "Личные реакции на источники периода подтверждены, но контекст "
                    "явной обратной связи не удалось полностью проверить. Поэтому "
                    "персонализация по реакциям не применялась."
                )
            else:
                message = (
                    "Снимок личных реакций за период подтверждён, но контекст "
                    "явной обратной связи не удалось полностью проверить. Поэтому "
                    "персонализация по реакциям не применялась."
                )
        else:
            message = (
                "Синхронизация реакций не завершена. Персонализация по реакциям "
                "для этого запуска не применялась."
            )
    elif status == "no_eligible_reactions":
        if int(counts.get("compatibility_threads_boosted") or 0) > 0:
            message = (
                "Личные реакции связаны с темами, прошедшими условия, но эти "
                "темы остались за пределом краткой выборки и не изменили выпуск. "
                "Это не снижало оценки тем."
            )
        elif events:
            message = (
                "Личные реакции на источники периода найдены, но ни одна не прошла "
                "все условия для влияния на выпуск. Это не снижало оценки тем."
            )
        else:
            message = (
                "Для источников этого периода личные реакции не найдены. Это не снижало "
                "оценки тем и не трактовалось как отсутствие интереса."
            )
    elif status == "linked_no_selection_effect":
        if selected_linked == 0 and int(counts.get("compatibility_threads_boosted") or 0) > 0:
            message = (
                "Личные реакции связаны с темами, прошедшими условия, но эти "
                "темы остались за пределом краткой выборки и не изменили выпуск. "
                "Это не снижало оценки тем."
            )
        else:
            message = (
                "Ваши отметки связаны с темами выпуска, но не изменили их место: "
                "они уже прошли по силе доказательств."
            )
    else:
        message = (
            f"{events} личных реакций → {posts} постов найдено → {atoms} атомов знаний "
            f"→ {threads} тем → {influenced} сигналов изменили позицию в выпуске."
        )
    totals = (
        f"Сводка: {events} личных реакций; {posts_label} — {posts}; "
        f"атомов знаний — {atoms}; связанных тем — {threads}; "
        f"изменённых сигналов — {influenced}; связей без изменения — {linked_only}; "
        f"не использовано реакций — {unconsumed}."
    )
    item_reasons: list[str] = []
    for index, item in enumerate(effect.get("influenced_items") or [], start=1):
        if not isinstance(item, dict):
            continue
        post_count = max(0, int(item.get("reacted_post_count") or 0))
        title = _reaction_reader_item_title(context, item, index=index)
        item_reasons.append(
            f"{title}. Почему сигнал изменил место: вы отметили "
            f"{post_count} связанных постов за отчётный период. "
            "Сигнал всё равно прошёл проверку доказательств."
        )
    for index, item in enumerate(effect.get("linked_only_items") or [], start=1):
        if not isinstance(item, dict):
            continue
        post_count = max(0, int(item.get("reacted_post_count") or 0))
        title = _reaction_reader_item_title(context, item, index=index)
        item_reasons.append(
            f"{title}. {post_count} отмеченных постов связаны с сигналом, "
            "но не изменили его место: "
            "он уже входил в выборку по силе доказательств."
        )
    reason_labels = {
        "post_not_found": "исходный пост не найден в сохранённых данных",
        "outside_analysis_period": "пост находится вне отчётного периода",
        "knowledge_atom_not_extracted": "для поста ещё нет атома знаний",
        "no_thread_link": "атом пока не связан с темой",
        "no_canonical_thread_link": "каноническая связь темы ещё не подтверждена",
        "stale_or_low_confidence_evidence": "доказательства устарели или недостаточно надёжны",
        "contradicted_or_retracted_evidence": "доказательства опровергнуты или отозваны",
        "duplicate_signal": "идея уже представлена более сильным сигналом",
        "superseded_by_confirmed_feedback": "приоритет определила подтверждённая обратная связь",
        "report_limit_reached": "сигнал остался за пределом краткой выборки",
        "confirmed_feedback_snapshot_unverified": "контекст подтверждённой обратной связи не удалось проверить",
        "snapshot_unverified": "текущую видимость реакции не удалось подтвердить",
    }
    reason_summary = []
    raw_reason_counts = effect.get("unconsumed_by_reason")
    if isinstance(raw_reason_counts, dict):
        for reason, count in raw_reason_counts.items():
            if reason in reason_labels and int(count or 0) > 0:
                reason_summary.append(f"{int(count)} — {reason_labels[reason]}")
    reason_html = (
        "<p><strong>Почему часть реакций не использована:</strong> "
        + _escape("; ".join(reason_summary))
        + ".</p>"
        if reason_summary
        else ""
    )
    item_html = (
        "<ul>" + "".join(f"<li>{_escape(reason)}</li>" for reason in item_reasons) + "</ul>"
        if item_reasons
        else ""
    )
    return (
        '<aside class="reaction-receipt">'
        "<h2>Как реакции повлияли на выпуск</h2>"
        f"<p>{_escape(message)}</p>"
        f'<p class="muted">{_escape(totals)}</p>'
        f"{item_html}{reason_html}"
        "</aside>"
    )


def _render_reaction_item_reason(
    context: dict,
    surface: str,
    surface_item_ref: object,
) -> str:
    """Return a card-level Russian receipt without exposing audit identity."""

    clean_ref = str(surface_item_ref or "").strip()
    if not clean_ref:
        return ""
    effect = _reaction_effect_for_surface(context, surface)
    if effect is None:
        return ""
    for field in ("influenced_items", "linked_only_items"):
        for item in effect.get(field) or []:
            if not isinstance(item, dict) or item.get("surface_item_ref") != clean_ref:
                continue
            post_count = max(0, int(item.get("reacted_post_count") or 0))
            if field == "influenced_items":
                copy = (
                    "Почему этот сигнал здесь: вы отметили "
                    f"{post_count} связанных постов за отчётный период. "
                    "Сигнал всё равно прошёл проверку доказательств."
                )
            else:
                copy = (
                    f"{post_count} отмеченных постов связаны с этим сигналом, "
                    "но не изменили его место: он уже входил в выборку по "
                    "силе доказательств."
                )
            return f'<p class="reaction-item-reason"><strong>{_escape(copy)}</strong></p>'
    return ""


def _reaction_reader_item_title(
    context: Mapping[str, object],
    item: Mapping[str, object],
    *,
    index: int,
) -> str:
    ref = str(item.get("surface_item_ref") or "")
    for thread in context.get("threads") or []:
        if not isinstance(thread, Mapping):
            continue
        slug = str(thread.get("slug") or "").strip()
        if slug and ref == f"thread:{slug}":
            return str(thread.get("title") or slug)
    return f"Связанный сигнал {index}"


def _truncate_text(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _link(url: str, label: str | None = None) -> str:
    clean = str(url or "").strip()
    if not clean:
        return ""
    return f'<a href="{_escape(clean)}">{_escape(label or clean)}</a>'


def _metric_card(label: str, value: object, detail: str) -> str:
    return (
        '<div class="metric">'
        f'<span class="metric-value">{_escape(value)}</span>'
        f'<span class="metric-label">{_escape(label)}</span>'
        f'<span class="metric-detail">{_escape(detail)}</span>'
        '</div>'
    )


def _momentum_bar(value: float) -> str:
    percent = max(0, min(100, round(float(value or 0.0) * 100)))
    return (
        '<div class="momentum" aria-label="Momentum">'
        f'<span style="width:{percent}%"></span>'
        '</div>'
        f'<span class="muted">{percent}% 30d momentum</span>'
    )


def _claim_list(claims: list[str], *, empty: str = "No current claims.") -> str:
    if not claims:
        return f"<p class=\"muted\">{_escape(empty)}</p>"
    items = "".join(f"<li>{_escape(claim)}</li>" for claim in claims[:5])
    return f"<ul>{items}</ul>"


def _source_links(atom: dict, *, limit: int = 3) -> str:
    urls = atom.get("source_urls") or []
    if not urls:
        return '<span class="muted">No source link</span>'
    links = [_link(url, f"S{index}") for index, url in enumerate(urls[:limit], start=1)]
    return " ".join(links)


def _render_feedback_context(context: dict) -> str:
    feedback = context.get("feedback_context") or {}
    counts = feedback.get("counts_by_feedback") or {}
    count_text = ", ".join(f"{name.replace('_', ' ')}={count}" for name, count in sorted(counts.items())) or "none"
    changes = feedback.get("feedback_changes") or {}
    change_items = changes.get("items") or []
    if not change_items:
        change_items = ["No confirmed feedback has changed ranking yet; no-feedback is not a negative signal."]
    change_summary = changes.get("summary") or "No prior feedback is available; personalization state is unknown."
    missed = feedback.get("missed_post_eval_examples") or []
    missed_text = ""
    if missed:
        missed_text = f"<li>Missed-post eval examples available: {_escape(len(missed))}</li>"
    return (
        '<div class="feedback-context">'
        "<h3>Personalization Context</h3>"
        "<ul>"
        f"<li>Prior report feedback: {_escape(count_text)}</li>"
        f"{missed_text}"
        "</ul>"
        "<h4>What Feedback Changed This Week</h4>"
        f"<p>{_escape(change_summary)}</p>"
        "<ul>"
        + "".join(f"<li>{_escape(item)}</li>" for item in change_items[:6])
        + "</ul>"
        "</div>"
    )


def _render_marked_posts(context: dict) -> str:
    marked_posts = context.get("marked_posts") or []
    if not marked_posts:
        return ""
    items = []
    for post in marked_posts[:8]:
        label = post.get("source_url") or f"post {post.get('post_id')}"
        source = _link(str(post.get("source_url") or ""), label) if post.get("source_url") else _escape(label)
        snippet = _escape(_truncate_text(str(post.get("content") or ""), 180))
        channel = _escape(post.get("channel_username") or "unknown")
        items.append(f"<li>{source} <span class=\"muted\">{channel}</span><br>{snippet}</li>")
    return (
        '<div class="feedback-context">'
        "<h3>Posts you marked this week</h3>"
        "<ul>"
        + "".join(items)
        + "</ul>"
        "</div>"
    )


def _render_executive_brief(context: dict, actions: list[dict]) -> str:
    threads = context["threads"]
    atoms = _all_atoms(threads)
    channels = context.get("source_channels") or []
    top_threads = threads[:3]
    cards = [
        _metric_card("Threads", len(threads), "active knowledge surfaces in this report"),
        _metric_card("Source Atoms", len(atoms), "cited Knowledge Atoms in context"),
        _metric_card("Channels", len(channels), "unique source channels"),
        _metric_card("Actions", len(actions), "personal read/try prompts"),
    ]
    if top_threads:
        lead_items = "".join(
            f"<li><b>{_escape(thread['title'])}</b> "
            f"<span class=\"tag\">{_escape(_status_label(thread['status']))}</span></li>"
            for thread in top_threads
        )
        lead = f"<p>Top evolving AI intelligence threads this week:</p><ul>{lead_items}</ul>"
    else:
        lead = (
            "<p>No Idea Threads are available yet. Generate Knowledge Atoms, refresh Idea Threads, "
            "then rerun this report.</p>"
        )
    return (
        '<div class="metrics">'
        + "".join(cards)
        + "</div>"
        + lead
        + _render_feedback_context(context)
        + _render_marked_posts(context)
    )


def _analysis_text(item: object, *keys: str) -> str:
    if isinstance(item, dict):
        for key in keys:
            value = str(item.get(key) or "").strip()
            if value:
                return value
        values = [str(value).strip() for value in item.values() if str(value).strip()]
        return " ".join(values[:2])
    return str(item or "").strip()


def _render_analysis_cards(items: list, *, title_keys: tuple[str, ...], body_keys: tuple[str, ...], empty: str) -> str:
    if not items:
        return f'<p class="muted">{_escape(empty)}</p>'
    cards = []
    for item in items[:6]:
        title = _analysis_text(item, *title_keys) or "Untitled"
        body = _analysis_text(item, *body_keys)
        cards.append(
            '<article class="analysis-card">'
            f'<h4>{_escape(title)}</h4>'
            f'<p>{_escape(body)}</p>'
            '</article>'
        )
    return "".join(cards)


def _render_frontier_analysis(context: dict) -> str:
    analysis = context.get("frontier_analysis")
    if not analysis:
        return (
            '<div class="frontier-pending">'
            "<p>No top-model synthesis has been saved for this week yet.</p>"
            '<p class="muted">Run <code>frontier-analysis --lookback-weeks 12</code> after refreshing Idea Threads, '
            "then regenerate this report.</p>"
            "</div>"
        )
    return (
        '<div class="frontier-analysis">'
        f'<p class="frontier-brief">{_escape(analysis.get("executive_brief") or "")}</p>'
        '<div class="analysis-grid">'
        '<div><h3>What Changed</h3>'
        + _render_analysis_cards(
            analysis.get("what_changed") or [],
            title_keys=("title", "change", "topic"),
            body_keys=("summary", "why_it_matters", "reason"),
            empty="No changes synthesized.",
        )
        + '</div><div><h3>Study Now</h3>'
        + _render_analysis_cards(
            analysis.get("study_now") or [],
            title_keys=("topic", "title"),
            body_keys=("reason", "why_it_matters"),
            empty="No study recommendations synthesized.",
        )
        + '</div><div><h3>Do Next</h3>'
        + _render_analysis_cards(
            analysis.get("actions") or [],
            title_keys=("title", "action"),
            body_keys=("next_step", "success_criterion", "why"),
            empty="No actions synthesized.",
        )
        + '</div></div>'
        '<h3>Trend Narratives</h3>'
        + _render_analysis_cards(
            analysis.get("trend_narratives") or [],
            title_keys=("title", "thread_slug"),
            body_keys=("narrative", "summary"),
            empty="No trend narratives synthesized.",
        )
        + '<h3>Caveats</h3>'
        + _claim_list([_analysis_text(item, "caveat", "summary") for item in analysis.get("caveats") or []], empty="No caveats synthesized.")
        + f'<p class="muted">Top-model synthesis: {_escape(analysis.get("model") or "")} · '
        f'{_escape(analysis.get("threads_analyzed") or 0)} threads · {_escape(analysis.get("atoms_analyzed") or 0)} atoms</p>'
        "</div>"
    )


def _render_what_changed(context: dict) -> str:
    changed = _changed_threads(context["threads"])
    if not changed:
        return "<p>No Idea Threads changed inside this ISO week window.</p>"
    articles = []
    for thread in changed[:6]:
        articles.append(
            '<article class="thread-card">'
            f'<h3>{_escape(thread["title"])}</h3>'
            f'<p class="muted">Last seen {_escape(thread["last_seen_at"])} · '
            f'{_escape(_status_label(thread["status"]))}</p>'
            f'{_claim_list(thread.get("current_claims") or [], empty="No current claims for this thread.")}'
            '</article>'
        )
    return "".join(articles)


def _render_idea_evolution(context: dict) -> str:
    threads = context["threads"]
    if not threads:
        return "<p>No Idea Threads are available for timeline rendering.</p>"
    parts = []
    for thread in threads:
        timeline_items = []
        for atom in reversed(thread.get("atoms") or []):
            timeline_items.append(
                '<li>'
                f'<span class="timeline-date">{_escape(str(atom.get("last_seen_at") or "")[:10])}</span>'
                f'<b>{_escape(atom.get("atom_type") or "atom")}</b>: {_escape(atom.get("claim") or "")}'
                f'<div class="sources">{_source_links(atom)}</div>'
                '</li>'
            )
        timeline = f"<ol class=\"timeline\">{''.join(timeline_items)}</ol>" if timeline_items else "<p class=\"muted\">No linked atoms.</p>"
        parts.append(
            '<article class="thread-card">'
            f'<h3 id="thread-{_escape(_safe_id(thread["slug"]))}">{_escape(thread["title"])}</h3>'
            f'<p>{_escape(thread.get("summary") or "")}</p>'
            f'<p><span class="tag">{_escape(_status_label(thread["status"]))}</span> '
            f'<span class="muted">first seen {_escape(thread["first_seen_at"][:10])} · '
            f'last seen {_escape(thread["last_seen_at"][:10])}</span></p>'
            f'{_momentum_bar(thread.get("momentum_30d") or 0.0)}'
            f'{_claim_list(thread.get("current_claims") or [], empty="No current claims.")}'
            f'{timeline}'
            '</article>'
        )
    return "".join(parts)


def _render_terms(context: dict) -> str:
    threads = context["threads"]
    groups = (
        ("Tools", _term_counts(threads, "tools")),
        ("Models", _term_counts(threads, "models")),
        ("Practices", _term_counts(threads, "practices")),
        ("Entities", _term_counts(threads, "entities")),
    )
    columns = []
    for title, counts in groups:
        if counts:
            items = "".join(f"<li>{_escape(term)} <span class=\"muted\">{count}</span></li>" for term, count in counts)
        else:
            items = '<li class="muted">No terms captured yet.</li>'
        columns.append(f'<div class="term-column"><h3>{_escape(title)}</h3><ul>{items}</ul></div>')
    return '<div class="term-grid">' + "".join(columns) + "</div>"


def _render_contradictions(context: dict) -> str:
    entries = []
    for thread in context["threads"]:
        contradictions = list(thread.get("contradictions") or [])
        contradictions.extend(thread.get("superseded_claims") or [])
        for atom in thread.get("atoms") or []:
            if atom.get("relation") in {"contradicts", "supersedes"} and atom.get("claim"):
                contradictions.append(atom["claim"])
        if not contradictions:
            continue
        unique = []
        for claim in contradictions:
            if claim not in unique:
                unique.append(claim)
        entries.append(
            '<article class="thread-card">'
            f'<h3>{_escape(thread["title"])}</h3>'
            f'{_claim_list(unique, empty="No contradictions.")}'
            '</article>'
        )
    if not entries:
        return "<p>No contradictions or superseded claims are visible in the current thread set.</p>"
    return "".join(entries)


def _render_read_queue(context: dict) -> str:
    atoms = _read_queue_atoms(context["threads"], context.get("feedback_context") or {})
    if not atoms:
        return "<p>No tutorial, case-study, benchmark, or research-claim atoms are available yet.</p>"
    items = []
    for atom in atoms:
        items.append(
            '<article class="thread-card compact">'
            f'<h3>{_escape(atom["claim"])}</h3>'
            f'<p>{_escape(atom.get("summary") or atom.get("why_it_matters") or "")}</p>'
            f'<p class="sources">{_source_links(atom, limit=4)}</p>'
            '</article>'
        )
    return "".join(items)


def _render_personal_learning_loop(context: dict, actions: list[dict]) -> str:
    loop = _personal_learning_loop(
        context["threads"],
        actions,
        context.get("feedback_context") or {},
    )
    read_items = []
    for index, item in enumerate(loop["read_items"], start=1):
        source_link = (
            _link(item.get("source_url") or "", f"Read {index}")
            if item.get("source_url")
            else '<span class="muted">source pending</span>'
        )
        read_items.append(
            '<li class="learning-read-item">'
            f'<b>{_escape(index)}. {_escape(item.get("claim") or "Untitled source")}</b>'
            f'<p>{_escape(item.get("summary") or "")}</p>'
            f'<p class="muted">Why selected: {_escape(item.get("why_selected") or "")}</p>'
            f'<p class="sources">{source_link}</p>'
            '</li>'
        )
    try_items = []
    for item in loop["try_items"]:
        try_items.append(
            '<li class="learning-try-item">'
            f'<b>{_escape(item.get("title") or "Try item")}</b>'
            f'<p>{_escape(item.get("body") or "")}</p>'
            f'<p class="muted">Why selected: {_escape(item.get("why_selected") or "")}</p>'
            f'<p class="muted">Source mentions: {_escape(item.get("source_count", 0))}</p>'
            '</li>'
        )
    experiment = loop["small_experiment"]
    return (
        '<div class="learning-loop">'
        "<h3>Personal Learning Loop</h3>"
        '<div class="learning-grid">'
        '<div><h4>Five Posts To Read</h4>'
        f'<ol class="learning-read-list">{"".join(read_items)}</ol></div>'
        '<div><h4>Two Tools Or Workflows To Try</h4>'
        f'<ol class="learning-try-list">{"".join(try_items)}</ol></div>'
        "</div>"
        '<div class="learning-followups">'
        '<article class="learning-experiment">'
        f'<h4>Small Experiment</h4><p><b>{_escape(experiment.get("title") or "")}</b></p>'
        f'<p>{_escape(experiment.get("body") or "")}</p>'
        '</article>'
        '<article class="learning-skill-gap">'
        f'<h4>Skill Gap</h4><p>{_escape(loop["skill_gap"])}</p>'
        '</article>'
        '<article class="learning-reflection">'
        f'<h4>Reflection Question</h4><p>{_escape(loop["reflection_question"])}</p>'
        '</article>'
        '</div>'
        '</div>'
    )


def _render_try_this_week(context: dict, actions: list[dict]) -> str:
    cards = []
    for action in actions:
        claim = f'<p class="muted">Anchor claim: {_escape(action["claim"])}</p>' if action.get("claim") else ""
        cards.append(
            '<article class="action-card">'
            f'<h3>{_escape(action["title"])}</h3>'
            f'<p>{_escape(action["body"])}</p>'
            f'<p class="muted">Why selected: {_escape(action.get("why_selected") or "")}</p>'
            f'{claim}'
            f'<p class="muted">Source links in action context: {_escape(action.get("source_count", 0))}</p>'
            '</article>'
        )
    return _render_personal_learning_loop(context, actions) + "".join(cards)


def _render_source_map(context: dict) -> str:
    channels = context.get("source_channels") or []
    if not channels:
        return "<p>No source channels are available in the Idea Thread layer yet.</p>"
    rows = []
    for item in channels:
        channel = item["channel"]
        label = f"@{channel}" if channel != "unknown" and "." not in channel else channel
        channel_link = f"https://t.me/{channel}" if channel != "unknown" and "." not in channel else ""
        rendered_channel = _link(channel_link, label) if channel_link else _escape(label)
        rows.append(f"<tr><td>{rendered_channel}</td><td>{_escape(item['count'])}</td></tr>")
    return '<table><thead><tr><th>Source</th><th>Atoms cited</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>"


def _render_appendix(context: dict) -> str:
    threads = context["threads"]
    if not threads:
        return "<p>No source posts are available yet.</p>"
    parts = []
    for thread in threads:
        atom_items = []
        for atom in thread.get("atoms") or []:
            atom_items.append(
                '<li>'
                f'<b>Atom {atom["id"]}</b> · {_escape(atom.get("atom_type") or "atom")} · '
                f'{_escape(atom.get("claim") or "")}'
                f'<div class="sources">{_source_links(atom, limit=6)}</div>'
                '</li>'
            )
        if not atom_items:
            atom_items.append('<li class="muted">No source atoms linked.</li>')
        parts.append(
            '<details>'
            f'<summary>{_escape(thread["title"])} · {_escape(thread["slug"])}</summary>'
            f'<ul>{"".join(atom_items)}</ul>'
            '</details>'
        )
    return "".join(parts)


def _human_period_label(context: dict) -> str:
    period_start = _parse_iso(context.get("analysis_period_start") or context.get("week_start"))
    period_end = _parse_iso(context.get("analysis_period_end") or context.get("week_end"))
    if period_start is None or period_end is None:
        try:
            period_start, period_end = _week_bounds(str(context.get("week_label") or ""))
        except (TypeError, ValueError):
            return str(context.get("week_label") or "")
    return format_human_period_label(
        period_mode=str(context.get("period_mode") or EXPLICIT_ISO_WEEK),
        reporting_week=str(context.get("reporting_week") or context.get("week_label") or ""),
        analysis_period_start=period_start,
        analysis_period_end=period_end,
    )


def _period_title(context: dict, artifact_name: str) -> str:
    label = _human_period_label(context)
    week_label = str(context.get("week_label") or "")
    if str(context.get("period_mode") or "") in {TRAILING_SEVEN_DAYS, PARTIAL_ISO_WEEK}:
        return f"{artifact_name} - {label}"
    return f"{artifact_name} - {label} ({week_label})" if week_label else f"{artifact_name} - {label}"


def _period_metadata(context: dict, *, generated_at: str) -> dict[str, object]:
    return {
        "run_date": context.get("run_date") or generated_at[:10],
        "generated_at": generated_at,
        "reporting_week": context.get("reporting_week") or context.get("week_label"),
        "week_label": context.get("week_label") or context.get("reporting_week"),
        "period_mode": context.get("period_mode") or EXPLICIT_ISO_WEEK,
        "analysis_period_start": context.get("analysis_period_start") or context.get("week_start"),
        "analysis_period_end": context.get("analysis_period_end") or context.get("week_end"),
    }


def render_ai_intelligence_html(context: dict, *, generated_at: str | None = None) -> tuple[str, list[dict]]:
    week_label = context["week_label"]
    actions = _learning_actions(context["threads"], context.get("feedback_context") or {})
    generated = generated_at or str(context.get("generated_at") or _utc_now_iso())
    report_title = _period_title(context, "AI Intelligence Report")
    section_bodies = {
        "executive-brief": _render_executive_brief(context, actions),
        "frontier-analysis": _render_frontier_analysis(context),
        "what-changed": _render_what_changed(context),
        "idea-evolution": _render_idea_evolution(context),
        "tools-models-practices": _render_terms(context),
        "contradictions": _render_contradictions(context),
        "read-queue": _render_read_queue(context),
        "try-this-week": _render_try_this_week(context, actions),
        "source-map": _render_source_map(context),
        "appendix": _render_appendix(context),
    }
    nav = "".join(f'<a href="#{section_id}">{_escape(title)}</a>' for section_id, title in REQUIRED_SECTIONS)
    sections = "\n".join(
        f'<section id="{section_id}"><h2>{_escape(title)}</h2>{section_bodies[section_id]}</section>'
        for section_id, title in REQUIRED_SECTIONS
    )
    html_text = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(report_title)}</title>
<style>
:root {{ color-scheme: light; --ink:#1d252c; --muted:#65717d; --line:#d8dee4; --panel:#ffffff; --bg:#f3f5f7; --accent:#166534; --accent-2:#92400e; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:var(--bg); color:var(--ink); line-height:1.58; }}
a {{ color:#0b63ce; text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
header {{ max-width:1120px; margin:0 auto; padding:34px 24px 18px; }}
.kicker {{ color:var(--accent); font-weight:700; text-transform:uppercase; letter-spacing:.08em; font-size:12px; margin:0 0 8px; }}
h1 {{ font-size:34px; line-height:1.16; margin:0 0 10px; letter-spacing:0; }}
h2 {{ font-size:22px; line-height:1.24; margin:0 0 16px; letter-spacing:0; }}
h3 {{ font-size:17px; line-height:1.3; margin:0 0 8px; letter-spacing:0; }}
h4 {{ font-size:14px; line-height:1.3; margin:0 0 8px; letter-spacing:0; text-transform:uppercase; color:var(--muted); }}
p {{ margin:0 0 12px; }}
nav {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:18px; }}
nav a {{ border:1px solid var(--line); background:#fff; border-radius:6px; padding:7px 10px; color:#24313d; font-size:13px; }}
main {{ max-width:1120px; margin:0 auto; padding:0 24px 42px; }}
section {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:20px; margin:0 0 14px; }}
.metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:0 0 16px; }}
.metric {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#fbfcfd; }}
.metric-value {{ display:block; font-size:24px; font-weight:700; }}
.metric-label {{ display:block; font-weight:700; }}
.metric-detail, .muted {{ color:var(--muted); font-size:13px; }}
.thread-card, .action-card {{ border:1px solid var(--line); border-radius:8px; padding:14px; margin:0 0 12px; background:#fbfcfd; }}
.thread-card.compact {{ padding:12px; }}
.frontier-brief {{ font-size:17px; color:#24313d; max-width:860px; }}
.analysis-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; margin:14px 0; }}
.analysis-card {{ border:1px solid var(--line); border-radius:8px; padding:12px; margin:0 0 10px; background:#fbfcfd; }}
code {{ background:#eef2f6; border:1px solid #d7dee7; border-radius:4px; padding:1px 4px; }}
.tag {{ display:inline-block; border:1px solid #bbd4c1; background:#edf7ef; color:#14532d; border-radius:999px; padding:2px 8px; font-size:12px; font-weight:700; }}
.momentum {{ height:8px; border-radius:999px; background:#e5e7eb; overflow:hidden; margin:6px 0 4px; }}
.momentum span {{ display:block; height:100%; background:linear-gradient(90deg, #16a34a, #d97706); }}
.timeline {{ padding-left:22px; }}
.timeline li {{ margin:0 0 12px; }}
.timeline-date {{ display:inline-block; min-width:84px; color:var(--muted); font-size:13px; }}
.sources {{ margin-top:6px; font-size:13px; }}
.sources a {{ display:inline-block; margin-right:8px; }}
.term-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; }}
.term-column {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#fbfcfd; }}
.learning-loop {{ border:1px solid #cbd5e1; border-radius:8px; padding:14px; margin:0 0 12px; background:#f8fafc; }}
.learning-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }}
.learning-read-list, .learning-try-list {{ padding-left:22px; margin:0 0 10px; }}
.learning-read-item, .learning-try-item {{ margin:0 0 12px; }}
.learning-followups {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:10px; margin-top:12px; }}
.learning-experiment, .learning-skill-gap, .learning-reflection {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#fff; }}
table {{ width:100%; border-collapse:collapse; }}
th, td {{ border-bottom:1px solid var(--line); text-align:left; padding:9px 8px; }}
details {{ border:1px solid var(--line); border-radius:8px; padding:10px 12px; margin:0 0 10px; background:#fbfcfd; }}
summary {{ cursor:pointer; font-weight:700; }}
@media (max-width: 720px) {{ h1 {{ font-size:27px; }} header, main {{ padding-left:16px; padding-right:16px; }} section {{ padding:16px; }} }}
</style>
</head>
<body>
<header>
<p class="kicker">AI Knowledge Intelligence</p>
<h1>{_escape(report_title)}</h1>
<p class="muted">Analysis period: {_escape(_human_period_label(context))}.</p>
<p class="muted">Period mode: {_escape(str(context.get("period_mode") or EXPLICIT_ISO_WEEK))}.</p>
<p class="muted">Generated {_escape(generated)} from compressed Idea Thread and Knowledge Atom context.</p>
<nav>{nav}</nav>
</header>
<main>
{sections}
</main>
</body>
</html>
"""
    return html_text, actions


def validate_ai_intelligence_html(html_text: str) -> list[ReportQualityFinding]:
    content = html.unescape(str(html_text or ""))
    findings: list[ReportQualityFinding] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if MATCHES_TRACE_RE.search(line):
            findings.append(
                ReportQualityFinding(
                    severity=SEVERITY_CRITICAL,
                    artifact_type="ai_intelligence_report",
                    message="Internal matching trace is visible in the AI Intelligence report",
                    line_hint=f"line {line_number}: {line.strip()[:160]}",
                )
            )
    for section_id, title in REQUIRED_SECTIONS:
        if f'id="{section_id}"' not in html_text:
            findings.append(
                ReportQualityFinding(
                    severity=SEVERITY_CRITICAL,
                    artifact_type="ai_intelligence_report",
                    message=f"Required section is missing: {title}",
                    line_hint=section_id,
                )
            )
    if 'class="action-card"' not in html_text:
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="ai_intelligence_report",
                message="Personal learning actions are missing from Try This Week",
                line_hint="try-this-week",
            )
        )
    if 'class="learning-loop"' not in html_text:
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="ai_intelligence_report",
                message="Personal learning loop is missing from Try This Week",
                line_hint="try-this-week",
            )
        )
    if html_text.count('class="learning-read-item"') < PERSONAL_READ_TARGET_COUNT:
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="ai_intelligence_report",
                message="Personal learning loop must include five read targets",
                line_hint="try-this-week",
            )
        )
    if html_text.count('class="learning-try-item"') < PERSONAL_TRY_TARGET_COUNT:
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="ai_intelligence_report",
                message="Personal learning loop must include two try targets",
                line_hint="try-this-week",
            )
        )
    for marker, message in (
        ('class="learning-experiment"', "Personal learning loop must include a small experiment"),
        ('class="learning-skill-gap"', "Personal learning loop must include a skill gap"),
        ('class="learning-reflection"', "Personal learning loop must include a reflection question"),
    ):
        if marker not in html_text:
            findings.append(
                ReportQualityFinding(
                    severity=SEVERITY_CRITICAL,
                    artifact_type="ai_intelligence_report",
                    message=message,
                    line_hint="try-this-week",
                )
            )
    return findings


def _write_report_files(
    *,
    week_label: str,
    html_text: str,
    metadata: dict,
    output_root: Path | str | None = None,
) -> tuple[Path, Path]:
    root = Path(output_root) if output_root is not None else OUTPUT_DIR
    root.mkdir(parents=True, exist_ok=True)
    html_path = root / f"{week_label}.html"
    json_path = root / f"{week_label}.json"
    html_path.write_text(html_text, encoding="utf-8")
    metadata["html_path"] = str(html_path)
    metadata["json_path"] = str(json_path)
    json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return html_path, json_path


def build_ai_intelligence_notification(summary: AiIntelligenceReportSummary) -> str:
    period_label = format_period_display_label(
        period_mode=summary.period_mode,
        reporting_week=summary.reporting_week or summary.week_label,
        analysis_period_start=summary.analysis_period_start,
        analysis_period_end=summary.analysis_period_end,
    )
    return (
        f"AI Intelligence Report {period_label} is ready.\n"
        f"Threads: {summary.thread_count} | Source atoms: {summary.source_atom_count} | Actions: {summary.action_count}\n"
        f"Open: {summary.html_path}"
    )


def generate_ai_intelligence_report(
    settings: Settings,
    *,
    week_label: str | None = None,
    period_mode: str | None = None,
    threads_limit: int = 8,
    atoms_limit: int = 8,
    output_root: Path | str | None = None,
    now: datetime | None = None,
) -> AiIntelligenceReportSummary:
    period = resolve_reporting_period(
        now,
        week_label=week_label,
        period_mode=period_mode,
    )
    clean_week = period.week_label
    period_fields = period.to_dict()
    generated_at = period_fields["generated_at"]
    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        context = load_ai_intelligence_context(
            connection,
            week_label=clean_week,
            reporting_period=period,
            threads_limit=threads_limit,
            atoms_limit=atoms_limit,
        )
    html_text, actions = render_ai_intelligence_html(context, generated_at=generated_at)
    personal_learning_loop = _personal_learning_loop(
        context["threads"],
        actions,
        context.get("feedback_context") or {},
    )
    findings = validate_ai_intelligence_html(html_text)
    critical = [finding for finding in findings if finding.severity == SEVERITY_CRITICAL]
    if critical:
        raise AiIntelligenceReportQualityError(critical)

    threads = context["threads"]
    atoms = _all_atoms(threads)
    metadata = {
        **_period_metadata(context, generated_at=generated_at),
        "thread_count": len(threads),
        "canonical_thread_count": len(context.get("canonical_threads") or []),
        "canonical_threads": [
            _canonical_thread_sidecar(thread)
            for thread in (context.get("canonical_threads") or [])
            if isinstance(thread, Mapping)
        ][:12],
        "canonical_thread_snapshot": dict(
            context.get("canonical_thread_snapshot") or {}
        ),
        "raw_compatibility_thread_count": len(threads),
        "source_atom_count": len(atoms),
        "source_channel_count": len(context.get("source_channels") or []),
        "action_count": len(actions),
        "sections": [title for _section_id, title in REQUIRED_SECTIONS],
        "compressed_context": context.get("compressed_context") or [],
        "frontier_analysis": context.get("frontier_analysis"),
        "feedback_context": context.get("feedback_context") or {},
        "marked_posts": context.get("marked_posts") or [],
        "personal_learning_loop": personal_learning_loop,
        "quality_findings": [finding.as_dict() for finding in findings],
        "actions": actions,
    }
    html_path, json_path = _write_report_files(
        week_label=clean_week,
        html_text=html_text,
        metadata=metadata,
        output_root=output_root,
    )
    summary = AiIntelligenceReportSummary(
        week_label=clean_week,
        generated_at=generated_at,
        run_date=period_fields["run_date"],
        reporting_week=period_fields["reporting_week"],
        period_mode=period_fields["period_mode"],
        analysis_period_start=period_fields["analysis_period_start"],
        analysis_period_end=period_fields["analysis_period_end"],
        html_path=str(html_path),
        json_path=str(json_path),
        thread_count=len(threads),
        source_atom_count=len(atoms),
        source_channel_count=len(context.get("source_channels") or []),
        action_count=len(actions),
        quality_finding_count=len(findings),
        notification_text="",
    )
    return AiIntelligenceReportSummary(
        **{
            **asdict(summary),
            "notification_text": build_ai_intelligence_notification(summary),
        }
    )
