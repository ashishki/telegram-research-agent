import html
import json
import re
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from config.settings import PROJECT_ROOT, Settings
from output.report_quality import (
    MATCHES_TRACE_RE,
    ReportQualityFinding,
    SEVERITY_CRITICAL,
)


OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "ai_intelligence"
REQUIRED_SECTIONS = (
    ("executive-brief", "Executive Brief"),
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
    limit: int,
) -> list[dict]:
    rows = connection.execute(
        """
        SELECT
            idea_thread_atoms.relation,
            knowledge_atoms.*
        FROM idea_thread_atoms
        JOIN knowledge_atoms ON knowledge_atoms.id = idea_thread_atoms.atom_id
        WHERE idea_thread_atoms.thread_id = ?
        ORDER BY knowledge_atoms.last_seen_at DESC, knowledge_atoms.id DESC
        LIMIT ?
        """,
        (int(thread_id), max(1, int(limit or 8))),
    ).fetchall()
    return [_atom_from_row(row) for row in rows]


def load_ai_intelligence_context(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    threads_limit: int = 8,
    atoms_limit: int = 8,
) -> dict:
    connection.row_factory = sqlite3.Row
    if not _table_exists(connection, "idea_threads") or not _table_exists(connection, "idea_thread_atoms"):
        return {"week_label": week_label, "threads": [], "source_channels": []}

    week_start, week_end = _week_bounds(week_label)
    week_start_sql = _iso_for_sql(week_start)
    week_end_sql = _iso_for_sql(week_end)
    rows = connection.execute(
        """
        SELECT *
        FROM idea_threads
        WHERE last_seen_at < ?
        ORDER BY
            CASE WHEN last_seen_at >= ? THEN 0 ELSE 1 END ASC,
            momentum_30d DESC,
            source_channel_count DESC,
            last_seen_at DESC,
            atom_count DESC,
            title ASC
        LIMIT ?
        """,
        (week_end_sql, week_start_sql, max(1, int(threads_limit or 8))),
    ).fetchall()
    threads = []
    for row in rows:
        thread = _thread_from_row(row)
        thread["atoms"] = _load_thread_atoms(
            connection,
            thread_id=thread["id"],
            limit=atoms_limit,
        )
        thread["changed_this_week"] = _thread_changed_this_week(thread, week_start, week_end)
        threads.append(thread)
    return {
        "week_label": week_label,
        "week_start": week_start_sql,
        "week_end": week_end_sql,
        "threads": threads,
        "source_channels": _source_channel_counts(threads),
        "compressed_context": _compressed_context(threads),
    }


def _thread_changed_this_week(thread: dict, week_start: datetime, week_end: datetime) -> bool:
    for atom in thread.get("atoms") or []:
        last_seen = _parse_iso(atom.get("last_seen_at"))
        if last_seen and week_start <= last_seen < week_end:
            return True
    last_seen = _parse_iso(thread.get("last_seen_at"))
    return bool(last_seen and week_start <= last_seen < week_end)


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


def _read_queue_atoms(threads: list[dict]) -> list[dict]:
    candidates = [
        atom
        for atom in _all_atoms(threads)
        if atom.get("atom_type") in READ_QUEUE_TYPES
    ]
    candidates.sort(
        key=lambda atom: (
            float(atom.get("practical_utility_score") or 0.0),
            float(atom.get("novelty_score") or 0.0),
            float(atom.get("confidence") or 0.0),
            str(atom.get("last_seen_at") or ""),
        ),
        reverse=True,
    )
    return candidates[:6]


def _learning_actions(threads: list[dict]) -> list[dict]:
    actions = []
    ranked = sorted(
        threads,
        key=lambda thread: (
            thread.get("status") == "production_pattern",
            float(thread.get("momentum_30d") or 0.0),
            int(thread.get("source_channel_count") or 0),
        ),
        reverse=True,
    )
    for thread in ranked:
        if thread.get("status") in {"hype_only", "resolved"}:
            continue
        title = thread.get("title") or thread.get("slug") or "Untitled thread"
        claims = thread.get("current_claims") or thread.get("superseded_claims") or []
        actions.append(
            {
                "title": f"Verify and apply: {title}",
                "body": (
                    "Pick one source-backed claim from this thread, verify the cited posts, "
                    "and turn it into a 30-minute read/try note."
                ),
                "claim": claims[0] if claims else "",
                "source_count": len({url for atom in thread.get("atoms") or [] for url in atom.get("source_urls") or []}),
            }
        )
        if len(actions) >= 4:
            break
    if not actions:
        actions.append(
            {
                "title": "Backfill the knowledge layer",
                "body": "Run Knowledge Atom extraction and Idea Thread refresh before the next weekly report.",
                "claim": "",
                "source_count": 0,
            }
        )
    return actions


def _status_label(status: str) -> str:
    return str(status or "active").replace("_", " ")


def _safe_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return slug or "item"


def _escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


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
    return '<div class="metrics">' + "".join(cards) + "</div>" + lead


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
    atoms = _read_queue_atoms(context["threads"])
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


def _render_try_this_week(actions: list[dict]) -> str:
    cards = []
    for action in actions:
        claim = f'<p class="muted">Anchor claim: {_escape(action["claim"])}</p>' if action.get("claim") else ""
        cards.append(
            '<article class="action-card">'
            f'<h3>{_escape(action["title"])}</h3>'
            f'<p>{_escape(action["body"])}</p>'
            f'{claim}'
            f'<p class="muted">Source links in action context: {_escape(action.get("source_count", 0))}</p>'
            '</article>'
        )
    return "".join(cards)


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


def render_ai_intelligence_html(context: dict, *, generated_at: str | None = None) -> tuple[str, list[dict]]:
    week_label = context["week_label"]
    actions = _learning_actions(context["threads"])
    generated = generated_at or _utc_now_iso()
    section_bodies = {
        "executive-brief": _render_executive_brief(context, actions),
        "what-changed": _render_what_changed(context),
        "idea-evolution": _render_idea_evolution(context),
        "tools-models-practices": _render_terms(context),
        "contradictions": _render_contradictions(context),
        "read-queue": _render_read_queue(context),
        "try-this-week": _render_try_this_week(actions),
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
<title>AI Intelligence Report { _escape(week_label) }</title>
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
<h1>AI Intelligence Report - {_escape(week_label)}</h1>
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
    return (
        f"AI Intelligence Report {summary.week_label} is ready.\n"
        f"Threads: {summary.thread_count} | Source atoms: {summary.source_atom_count} | Actions: {summary.action_count}\n"
        f"Open: {summary.html_path}"
    )


def generate_ai_intelligence_report(
    settings: Settings,
    *,
    week_label: str | None = None,
    threads_limit: int = 8,
    atoms_limit: int = 8,
    output_root: Path | str | None = None,
    now: datetime | None = None,
) -> AiIntelligenceReportSummary:
    clean_week = str(week_label or _current_week_label(now)).strip()
    generated_at = (now or _utc_now()).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        context = load_ai_intelligence_context(
            connection,
            week_label=clean_week,
            threads_limit=threads_limit,
            atoms_limit=atoms_limit,
        )
    html_text, actions = render_ai_intelligence_html(context, generated_at=generated_at)
    findings = validate_ai_intelligence_html(html_text)
    critical = [finding for finding in findings if finding.severity == SEVERITY_CRITICAL]
    if critical:
        raise AiIntelligenceReportQualityError(critical)

    threads = context["threads"]
    atoms = _all_atoms(threads)
    metadata = {
        "week_label": clean_week,
        "generated_at": generated_at,
        "thread_count": len(threads),
        "source_atom_count": len(atoms),
        "source_channel_count": len(context.get("source_channels") or []),
        "action_count": len(actions),
        "sections": [title for _section_id, title in REQUIRED_SECTIONS],
        "compressed_context": context.get("compressed_context") or [],
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
