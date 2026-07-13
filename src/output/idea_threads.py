import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from config.settings import Settings
from db.idea_threads import link_idea_thread_atom, upsert_idea_thread
from output.reporting_period import register_reporting_period_sqlite


STOPWORDS = {
    "about",
    "after",
    "agent",
    "agents",
    "being",
    "before",
    "build",
    "coding",
    "from",
    "have",
    "into",
    "more",
    "that",
    "their",
    "this",
    "tool",
    "tools",
    "using",
    "with",
}
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9-]{2,}")


@dataclass(frozen=True)
class IdeaThreadSummary:
    atoms_seen: int
    threads_refreshed: int
    links_refreshed: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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


def _parse_array(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _normalize_utc_boundary(value: datetime | str, *, field_name: str) -> datetime:
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise TypeError(f"{field_name} must be a datetime or ISO-8601 timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include an explicit timezone")
    return parsed.astimezone(timezone.utc)


def _load_atoms(
    connection: sqlite3.Connection,
    *,
    weeks: int,
    limit: int | None,
    now: datetime,
    analysis_period_end: datetime | None,
) -> list[dict]:
    clauses: list[str] = []
    params: list[object] = []
    if weeks and weeks > 0:
        cutoff = now - timedelta(days=weeks * 7)
        clauses.append(
            "reporting_utc_micros(last_seen_at) >= reporting_utc_micros(?)"
        )
        params.append(cutoff.isoformat().replace("+00:00", "Z"))
    if analysis_period_end is not None:
        clauses.append(
            "reporting_utc_micros(last_seen_at) < reporting_utc_micros(?)"
        )
        params.append(analysis_period_end.isoformat().replace("+00:00", "Z"))
    limit_sql = "LIMIT ?" if limit and limit > 0 else ""
    if limit and limit > 0:
        params.append(int(limit))
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(
        f"""
        SELECT *
        FROM knowledge_atoms
        {where_sql}
        ORDER BY reporting_utc_micros(last_seen_at) ASC, id ASC
        {limit_sql}
        """,
        params,
    ).fetchall()
    atoms: list[dict] = []
    for row in rows:
        atoms.append(
            {
                "id": int(row["id"]),
                "atom_type": str(row["atom_type"] or ""),
                "claim": str(row["claim"] or ""),
                "summary": str(row["summary"] or ""),
                "source_urls": _parse_array(row["source_urls_json"]),
                "entities": _parse_array(row["entities_json"]),
                "tools": _parse_array(row["tools_json"]),
                "models": _parse_array(row["models_json"]),
                "practices": _parse_array(row["practices_json"]),
                "confidence": float(row["confidence"] or 0.0),
                "practical_utility_score": float(row["practical_utility_score"] or 0.0),
                "staleness_status": str(row["staleness_status"] or "active"),
                "first_seen_at": str(row["first_seen_at"] or ""),
                "last_seen_at": str(row["last_seen_at"] or ""),
            }
        )
    return atoms


def _slug_token(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized


def _claim_terms(claim: str) -> list[str]:
    terms: list[str] = []
    for match in TOKEN_RE.findall(claim.lower()):
        token = _slug_token(match)
        if token and token not in STOPWORDS and token not in terms:
            terms.append(token)
        if len(terms) >= 3:
            break
    return terms


def _display_term(value: str) -> str:
    return " ".join(str(value).strip().split())


def _thread_terms(atom: dict) -> tuple[list[str], list[str]]:
    display_terms: list[str] = []
    for field in ("tools", "models", "entities", "practices"):
        for value in atom.get(field) or []:
            display = _display_term(value)
            slug = _slug_token(display)
            if slug and slug not in STOPWORDS and slug not in [_slug_token(item) for item in display_terms]:
                display_terms.append(display)
    if not display_terms:
        display_terms = _claim_terms(atom.get("claim") or "")
    slug_terms = sorted({_slug_token(term) for term in display_terms if _slug_token(term)})[:3]
    return slug_terms, display_terms[:5]


def _source_channel(url: str) -> str:
    parsed = urlparse(str(url or ""))
    if parsed.netloc.endswith("t.me"):
        parts = [part for part in parsed.path.split("/") if part]
        if parts:
            return parts[0]
    return parsed.netloc or "unknown"


def _group_atoms(atoms: list[dict]) -> dict[str, dict]:
    groups: dict[str, dict] = {}
    for atom in atoms:
        slug_terms, display_terms = _thread_terms(atom)
        slug = "-".join(slug_terms) or f"atom-{atom['id']}"
        group = groups.setdefault(
            slug,
            {
                "slug": slug,
                "display_terms": [],
                "atoms": [],
            },
        )
        for term in display_terms:
            if term not in group["display_terms"]:
                group["display_terms"].append(term)
        group["atoms"].append(atom)
    return groups


def _momentum(atoms: list[dict], *, now: datetime, days: int, saturation_count: int) -> float:
    cutoff = now - timedelta(days=days)
    count = 0
    for atom in atoms:
        last_seen = _parse_iso(atom.get("last_seen_at"))
        if last_seen and last_seen >= cutoff:
            count += 1
    return min(1.0, count / max(1, saturation_count))


def _thread_status(atoms: list[dict], *, now: datetime, source_channel_count: int) -> str:
    statuses = {str(atom.get("staleness_status") or "active") for atom in atoms}
    non_current_statuses = {"superseded", "resolved", "hype_only", "stale"}
    has_current_evidence = any(status not in non_current_statuses for status in statuses)
    if not has_current_evidence:
        if "superseded" in statuses:
            return "superseded"
        if "resolved" in statuses:
            return "resolved"
        if "hype_only" in statuses:
            return "hype_only"
        if "stale" in statuses:
            return "stale"
    last_seen_values = [_parse_iso(atom.get("last_seen_at")) for atom in atoms]
    last_seen_values = [value for value in last_seen_values if value is not None]
    if last_seen_values and max(last_seen_values) < now - timedelta(days=30):
        return "stale"
    avg_utility = sum(float(atom.get("practical_utility_score") or 0.0) for atom in atoms) / max(1, len(atoms))
    if len(atoms) >= 3 and source_channel_count >= 2 and avg_utility >= 0.75:
        return "production_pattern"
    return "active"


def _relation_for_atom(atom: dict) -> str:
    if atom.get("staleness_status") == "superseded":
        return "supersedes"
    if atom.get("atom_type") in {"risk_warning", "opinion_shift"}:
        return "contradicts"
    return "supports"


def _claims(atoms: list[dict], *, include_current: bool) -> list[str]:
    result: list[str] = []
    for atom in sorted(atoms, key=lambda item: item.get("last_seen_at") or "", reverse=True):
        staleness = atom.get("staleness_status")
        is_current = staleness not in {"superseded", "resolved", "hype_only", "stale"}
        if include_current != is_current:
            continue
        claim = str(atom.get("claim") or "").strip()
        if claim and claim not in result:
            result.append(claim)
        if len(result) >= 6:
            break
    return result


def _contradictions(atoms: list[dict]) -> list[str]:
    result: list[str] = []
    for atom in atoms:
        claim = str(atom.get("claim") or "")
        text = claim.lower()
        if atom.get("atom_type") in {"risk_warning", "opinion_shift"} or any(
            marker in text for marker in (" not ", " risk", " fails", " broken", " contradict")
        ):
            if claim and claim not in result:
                result.append(claim)
    return result[:6]


def refresh_idea_threads(
    settings: Settings,
    *,
    weeks: int = 12,
    limit: int | None = None,
    now: datetime | None = None,
    analysis_period_end: datetime | str | None = None,
) -> IdeaThreadSummary:
    current = now or _utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    exclusive_end = (
        _normalize_utc_boundary(
            analysis_period_end,
            field_name="analysis_period_end",
        )
        if analysis_period_end is not None
        else None
    )
    links_refreshed = 0
    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        register_reporting_period_sqlite(connection)
        atoms = _load_atoms(
            connection,
            weeks=weeks,
            limit=limit,
            now=current,
            analysis_period_end=exclusive_end,
        )
        groups = _group_atoms(atoms)
        for group in groups.values():
            group_atoms = group["atoms"]
            channels = sorted(
                {
                    _source_channel(url)
                    for atom in group_atoms
                    for url in atom.get("source_urls") or []
                    if _source_channel(url)
                }
            )
            first_seen = min(atom["first_seen_at"] for atom in group_atoms if atom.get("first_seen_at"))
            last_seen = max(atom["last_seen_at"] for atom in group_atoms if atom.get("last_seen_at"))
            display_terms = group["display_terms"] or [group["slug"].replace("-", " ")]
            title = " / ".join(display_terms[:3])
            current_claims = _claims(group_atoms, include_current=True)
            superseded_claims = _claims(group_atoms, include_current=False)
            summary_claim = current_claims[0] if current_claims else (superseded_claims[0] if superseded_claims else "")
            summary = (
                f"{len(group_atoms)} atoms across {len(channels)} source channel(s)."
                + (f" Latest: {summary_claim}" if summary_claim else "")
            )
            thread = upsert_idea_thread(
                connection,
                slug=group["slug"],
                title=title,
                summary=summary,
                status=_thread_status(group_atoms, now=current, source_channel_count=len(channels)),
                first_seen_at=first_seen,
                last_seen_at=last_seen,
                momentum_7d=_momentum(group_atoms, now=current, days=7, saturation_count=5),
                momentum_30d=_momentum(group_atoms, now=current, days=30, saturation_count=12),
                momentum_90d=_momentum(group_atoms, now=current, days=90, saturation_count=24),
                atom_count=len(group_atoms),
                source_channels=channels,
                key_entities=display_terms,
                current_claims=current_claims,
                superseded_claims=superseded_claims,
                contradictions=_contradictions(group_atoms),
            )
            for atom in group_atoms:
                link_idea_thread_atom(
                    connection,
                    thread_id=thread["id"],
                    atom_id=atom["id"],
                    relation=_relation_for_atom(atom),
                )
                links_refreshed += 1
    return IdeaThreadSummary(
        atoms_seen=len(atoms),
        threads_refreshed=len(groups),
        links_refreshed=links_refreshed,
    )


def format_idea_thread_summary(summary: IdeaThreadSummary) -> str:
    return (
        "Idea thread refresh summary\n"
        f"atoms_seen={summary.atoms_seen} "
        f"threads_refreshed={summary.threads_refreshed} "
        f"links_refreshed={summary.links_refreshed}\n"
    )
