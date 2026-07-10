from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from config.settings import PROJECT_ROOT, Settings
from output.ai_report_contract import INTELLIGENCE_CONTRACT_VERSION, build_canonical_intelligence_contract
from output.ai_intelligence_report import (
    _all_atoms,
    _changed_threads,
    _current_week_label,
    _escape,
    _metric_card,
    _momentum_bar,
    _source_channel_counts,
    _source_links,
    _status_label,
    _term_counts,
    _truncate_text,
    load_ai_intelligence_context,
)
from output.report_quality import MATCHES_TRACE_RE, ReportQualityFinding, SEVERITY_CRITICAL


OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "knowledge_atlas"
ATLAS_SECTIONS = (
    ("atlas-overview", "Atlas Overview", "overview"),
    ("idea-map", "Idea Map", "idea_map"),
    ("trend-board", "Trend Board", "trend_board"),
    ("source-contribution", "Source Contribution", "source_contribution"),
    ("study-backlog", "Study Backlog", "study_backlog"),
    ("atlas-appendix", "Atlas Audit", "atlas_audit"),
)


@dataclass(frozen=True)
class KnowledgeAtlasSummary:
    week_label: str
    generated_at: str
    html_path: str
    json_path: str
    thread_count: int
    source_atom_count: int
    source_channel_count: int
    trend_count: int
    quality_finding_count: int
    notification_text: str


class KnowledgeAtlasQualityError(ValueError):
    def __init__(self, findings: list[ReportQualityFinding]) -> None:
        self.findings = findings
        messages = "; ".join(f"{finding.artifact_type}: {finding.message}" for finding in findings)
        super().__init__(f"Knowledge Atlas failed quality gates: {messages}")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def build_knowledge_atlas_artifact(
    context: dict,
    *,
    generated_at: str,
    output_root: str | Path | None = None,
    related_artifacts: dict | None = None,
) -> KnowledgeAtlasSummary:
    html_text = render_knowledge_atlas_html(context, generated_at=generated_at)
    findings = validate_knowledge_atlas_html(html_text)
    critical = [finding for finding in findings if finding.severity == SEVERITY_CRITICAL]
    if critical:
        raise KnowledgeAtlasQualityError(critical)

    root = Path(output_root) if output_root is not None else OUTPUT_DIR
    root.mkdir(parents=True, exist_ok=True)
    week_label = str(context.get("week_label") or "")
    html_path = root / f"{week_label}.knowledge-atlas.html"
    json_path = root / f"{week_label}.knowledge-atlas.json"
    threads = context.get("threads") or []
    atoms = _all_atoms(threads)
    metadata = _knowledge_atlas_metadata(
        context,
        generated_at=generated_at,
        html_path=html_path,
        json_path=json_path,
        quality_findings=findings,
        related_artifacts=related_artifacts or {},
    )
    html_path.write_text(html_text, encoding="utf-8")
    json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = KnowledgeAtlasSummary(
        week_label=week_label,
        generated_at=generated_at,
        html_path=str(html_path),
        json_path=str(json_path),
        thread_count=len(threads),
        source_atom_count=len(atoms),
        source_channel_count=len(context.get("source_channels") or []),
        trend_count=len(_changed_threads(threads)),
        quality_finding_count=len(findings),
        notification_text="",
    )
    return KnowledgeAtlasSummary(
        **{
            **asdict(summary),
            "notification_text": build_knowledge_atlas_notification(summary),
        }
    )


def generate_knowledge_atlas_report(
    settings: Settings,
    *,
    week_label: str | None = None,
    threads_limit: int = 24,
    atoms_limit: int = 8,
    output_root: str | Path | None = None,
    now: datetime | None = None,
) -> KnowledgeAtlasSummary:
    clean_week = str(week_label or _current_week_label(now)).strip()
    generated_at = (now or _utc_now()).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        context = load_ai_intelligence_context(
            connection,
            week_label=clean_week,
            threads_limit=max(1, int(threads_limit or 24)),
            atoms_limit=max(1, int(atoms_limit or 8)),
        )
    return build_knowledge_atlas_artifact(
        context,
        generated_at=generated_at,
        output_root=output_root,
    )


def render_knowledge_atlas_html(context: dict, *, generated_at: str | None = None) -> str:
    week_label = str(context.get("week_label") or "")
    generated = generated_at or _utc_now_iso()
    section_bodies = {
        "atlas-overview": _render_atlas_overview(context),
        "idea-map": _render_idea_map(context),
        "trend-board": _render_trend_board(context),
        "source-contribution": _render_source_contribution(context),
        "study-backlog": _render_study_backlog(context),
        "atlas-appendix": _render_atlas_appendix(context),
    }
    nav = "".join(f'<a href="#{section_id}">{_escape(title)}</a>' for section_id, title, _kind in ATLAS_SECTIONS)
    sections = "\n".join(
        f'<section id="{section_id}"><h2>{_escape(title)}</h2>{section_bodies[section_id]}</section>'
        for section_id, title, _kind in ATLAS_SECTIONS
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="intelligence-contract-version" content="{_escape(INTELLIGENCE_CONTRACT_VERSION)}">
<title>Knowledge Atlas { _escape(week_label) }</title>
<style>
:root {{ color-scheme: light; --ink:#18212b; --muted:#66717e; --line:#d8dee6; --panel:#ffffff; --bg:#f5f7f9; --accent:#0f766e; --warn:#a16207; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--ink); line-height:1.56; }}
a {{ color:#075985; text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
header {{ max-width:1180px; margin:0 auto; padding:32px 24px 18px; }}
.kicker {{ color:var(--accent); font-weight:700; text-transform:uppercase; font-size:12px; margin:0 0 8px; letter-spacing:.08em; }}
h1 {{ font-size:34px; line-height:1.16; margin:0 0 8px; letter-spacing:0; }}
h2 {{ font-size:22px; line-height:1.24; margin:0 0 16px; letter-spacing:0; }}
h3 {{ font-size:17px; line-height:1.3; margin:0 0 8px; letter-spacing:0; }}
p {{ margin:0 0 12px; }}
nav {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:18px; }}
nav a {{ border:1px solid var(--line); background:#fff; border-radius:6px; padding:7px 10px; color:#26323f; font-size:13px; }}
main {{ max-width:1180px; margin:0 auto; padding:0 24px 42px; }}
section {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:20px; margin:0 0 14px; }}
.muted {{ color:var(--muted); font-size:13px; }}
.metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:0 0 16px; }}
.metric {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#fbfcfd; }}
.metric-value {{ display:block; font-size:24px; font-weight:700; }}
.metric-label {{ display:block; font-weight:700; }}
.metric-detail {{ display:block; color:var(--muted); font-size:13px; }}
.atlas-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:12px; }}
.atlas-card {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fbfcfd; }}
.tag {{ display:inline-block; border:1px solid #b6ddd6; background:#ecfdf5; color:#115e59; border-radius:999px; padding:2px 8px; font-size:12px; font-weight:700; }}
.momentum {{ height:8px; border-radius:999px; background:#e5e7eb; overflow:hidden; margin:6px 0 4px; }}
.momentum span {{ display:block; height:100%; background:linear-gradient(90deg,#0f766e,#ca8a04); }}
.timeline {{ padding-left:22px; }}
.timeline li {{ margin:0 0 12px; }}
.sources {{ margin-top:6px; font-size:13px; }}
.term-board {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; }}
.term-column {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#fbfcfd; }}
table {{ width:100%; border-collapse:collapse; }}
th, td {{ border-bottom:1px solid var(--line); text-align:left; padding:9px 8px; }}
@media (max-width:720px) {{ h1 {{ font-size:27px; }} header, main {{ padding-left:16px; padding-right:16px; }} section {{ padding:16px; }} }}
</style>
</head>
<body>
<header>
<p class="kicker">AI Knowledge Atlas</p>
<h1>Knowledge Atlas - {_escape(week_label)}</h1>
<p class="muted">Generated {_escape(generated)} from bounded Idea Thread and Knowledge Atom context. This is a rolling knowledge map, not a raw Telegram mirror.</p>
<nav>{nav}</nav>
</header>
<main>
{sections}
</main>
</body>
</html>
"""


def validate_knowledge_atlas_html(html_text: str) -> list[ReportQualityFinding]:
    findings: list[ReportQualityFinding] = []
    content = str(html_text or "")
    if "<!doctype html>" not in content.lower():
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="knowledge_atlas",
                message="Knowledge Atlas must be standalone HTML",
                line_hint="doctype",
            )
        )
    for section_id, title, _kind in ATLAS_SECTIONS:
        if f'id="{section_id}"' not in content:
            findings.append(
                ReportQualityFinding(
                    severity=SEVERITY_CRITICAL,
                    artifact_type="knowledge_atlas",
                    message=f"Required Atlas section is missing: {title}",
                    line_hint=section_id,
                )
            )
    for line_number, line in enumerate(content.splitlines(), start=1):
        if MATCHES_TRACE_RE.search(line):
            findings.append(
                ReportQualityFinding(
                    severity=SEVERITY_CRITICAL,
                    artifact_type="knowledge_atlas",
                    message="Internal matching trace is visible in Knowledge Atlas",
                    line_hint=f"line {line_number}",
                )
            )
    if "raw Telegram mirror" not in content:
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="knowledge_atlas",
                message="Knowledge Atlas must state that it is not a raw Telegram mirror",
                line_hint="header",
            )
        )
    return findings


def build_knowledge_atlas_notification(summary: KnowledgeAtlasSummary) -> str:
    return (
        f"Knowledge Atlas {summary.week_label} is ready.\n"
        f"Threads: {summary.thread_count} | Atoms: {summary.source_atom_count} | Changed: {summary.trend_count}\n"
        f"Open: {summary.html_path}"
    )


def _knowledge_atlas_metadata(
    context: dict,
    *,
    generated_at: str,
    html_path: Path,
    json_path: Path,
    quality_findings: list[ReportQualityFinding],
    related_artifacts: dict,
) -> dict:
    threads = context.get("threads") or []
    atoms = _all_atoms(threads)
    intelligence_contract = build_canonical_intelligence_contract(context)
    sections = [
        {
            "id": section_id,
            "title": title,
            "title_en": title,
            "kind": kind,
            "summary": _section_metadata_summary(context, section_id),
        }
        for section_id, title, kind in ATLAS_SECTIONS
    ]
    return {
        "schema_version": "split_ai_report.v1",
        "contract_version": INTELLIGENCE_CONTRACT_VERSION,
        "artifact_type": "knowledge_atlas",
        "week_label": context.get("week_label"),
        "generated_at": generated_at,
        "html_path": str(html_path),
        "json_path": str(json_path),
        "artifact_paths": {"html": str(html_path), "json": str(json_path)},
        "related_artifacts": related_artifacts,
        "sections": [section["title"] for section in sections],
        "workbook_sections": sections,
        "artifact_sections": sections,
        "thread_count": len(threads),
        "source_atom_count": len(atoms),
        "source_channel_count": len(context.get("source_channels") or []),
        "changed_thread_count": len(_changed_threads(threads)),
        "intelligence_contract": intelligence_contract,
        "compressed_context": context.get("compressed_context") or [],
        "source_channels": context.get("source_channels") or [],
        "quality_findings": [finding.as_dict() for finding in quality_findings],
        "retrieval_note": "Knowledge Atlas is a rolling/cumulative knowledge map over curated objects, not raw Telegram runtime memory.",
    }


def _render_atlas_overview(context: dict) -> str:
    threads = context.get("threads") or []
    atoms = _all_atoms(threads)
    changed = _changed_threads(threads)
    cards = [
        _metric_card("Threads", len(threads), "bounded rolling knowledge threads"),
        _metric_card("Source Atoms", len(atoms), "curated cited atoms in the atlas"),
        _metric_card("Channels", len(context.get("source_channels") or []), "source contribution map"),
        _metric_card("Changed", len(changed), "threads with current-week movement"),
    ]
    return (
        '<div class="metrics">'
        + "".join(cards)
        + "</div>"
        '<p>This Atlas is for long-running AI/business learning: trend memory, source contribution, and study backlog. '
        "Weekly decisions live in the Weekly Intelligence Brief.</p>"
    )


def _render_idea_map(context: dict) -> str:
    threads = context.get("threads") or []
    if not threads:
        return "<p>No Idea Threads are available yet.</p>"
    cards = []
    for thread in threads[:12]:
        claims = "".join(f"<li>{_escape(claim)}</li>" for claim in (thread.get("current_claims") or [])[:3])
        if not claims:
            claims = '<li class="muted">No current claims captured.</li>'
        cards.append(
            '<article class="atlas-card">'
            f'<h3>{_escape(thread.get("title") or thread.get("slug") or "Untitled thread")}</h3>'
            f'<p><span class="tag">{_escape(_status_label(thread.get("status") or "active"))}</span> '
            f'<span class="muted">last seen {_escape(str(thread.get("last_seen_at") or "")[:10])}</span></p>'
            f'{_momentum_bar(float(thread.get("momentum_30d") or 0.0))}'
            f'<p>{_escape(_truncate_text(thread.get("summary") or "", 220))}</p>'
            f"<ul>{claims}</ul>"
            "</article>"
        )
    return '<div class="atlas-grid">' + "".join(cards) + "</div>"


def _render_trend_board(context: dict) -> str:
    changed = _changed_threads(context.get("threads") or [])
    if not changed:
        return "<p>No Idea Threads changed inside this ISO week window.</p>"
    items = []
    for thread in changed[:8]:
        atom_rows = []
        for atom in (thread.get("atoms") or [])[:4]:
            atom_rows.append(
                '<li>'
                f'<b>{_escape(str(atom.get("last_seen_at") or "")[:10])}</b> '
                f'{_escape(atom.get("claim") or "")}'
                f'<div class="sources">{_source_links(atom, limit=3)}</div>'
                '</li>'
            )
        items.append(
            '<article class="atlas-card">'
            f'<h3>{_escape(thread.get("title") or thread.get("slug") or "Untitled")}</h3>'
            f'<ol class="timeline">{"".join(atom_rows)}</ol>'
            "</article>"
        )
    return '<div class="atlas-grid">' + "".join(items) + "</div>"


def _render_source_contribution(context: dict) -> str:
    channels = context.get("source_channels") or _source_channel_counts(context.get("threads") or [])
    if not channels:
        return "<p>No source channels are available in the curated layer yet.</p>"
    rows = []
    for item in channels[:20]:
        channel = str(item.get("channel") or "unknown")
        label = f"@{channel}" if channel != "unknown" and "." not in channel else channel
        href = f"https://t.me/{channel}" if channel != "unknown" and "." not in channel else ""
        source = f'<a href="{_escape(href)}">{_escape(label)}</a>' if href else _escape(label)
        rows.append(f"<tr><td>{source}</td><td>{_escape(item.get('count') or 0)}</td></tr>")
    term_columns = []
    for title, field in (("Tools", "tools"), ("Models", "models"), ("Practices", "practices")):
        counts = _term_counts(context.get("threads") or [], field)
        items = "".join(f"<li>{_escape(term)} <span class=\"muted\">{count}</span></li>" for term, count in counts[:8])
        term_columns.append(f'<div class="term-column"><h3>{_escape(title)}</h3><ul>{items or "<li>No terms yet.</li>"}</ul></div>')
    return (
        '<table><thead><tr><th>Source</th><th>Atoms cited</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
        '<h3>Concept Contribution</h3>'
        '<div class="term-board">'
        + "".join(term_columns)
        + "</div>"
    )


def _render_study_backlog(context: dict) -> str:
    atoms = sorted(
        _all_atoms(context.get("threads") or []),
        key=lambda atom: (
            float(atom.get("practical_utility_score") or 0.0),
            float(atom.get("novelty_score") or 0.0),
            str(atom.get("last_seen_at") or ""),
        ),
        reverse=True,
    )
    if not atoms:
        return "<p>No study backlog atoms are available yet.</p>"
    cards = []
    for atom in atoms[:10]:
        cards.append(
            '<article class="atlas-card">'
            f'<h3>{_escape(atom.get("claim") or "Untitled atom")}</h3>'
            f'<p>{_escape(_truncate_text(atom.get("summary") or atom.get("why_it_matters") or "", 220))}</p>'
            f'<p class="muted">{_escape(atom.get("atom_type") or "atom")} · utility {_escape(atom.get("practical_utility_score") or 0)}</p>'
            f'<p class="sources">{_source_links(atom, limit=4)}</p>'
            '</article>'
        )
    return '<div class="atlas-grid">' + "".join(cards) + "</div>"


def _render_atlas_appendix(context: dict) -> str:
    threads = context.get("threads") or []
    rows = []
    for thread in threads[:30]:
        rows.append(
            "<tr>"
            f"<td>{_escape(thread.get('slug') or '')}</td>"
            f"<td>{_escape(thread.get('status') or '')}</td>"
            f"<td>{_escape(thread.get('atom_count') or len(thread.get('atoms') or []))}</td>"
            f"<td>{_escape(thread.get('last_seen_at') or '')}</td>"
            "</tr>"
        )
    return (
        '<p class="muted">Bounded audit table for the thread set rendered in this Atlas.</p>'
        '<table><thead><tr><th>Thread</th><th>Status</th><th>Atoms</th><th>Last seen</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def _section_metadata_summary(context: dict, section_id: str) -> str:
    threads = context.get("threads") or []
    if section_id == "atlas-overview":
        return f"{len(threads)} threads and {len(_all_atoms(threads))} source atoms in bounded atlas context."
    if section_id == "idea-map":
        return "Rolling map of current Idea Threads and claims."
    if section_id == "trend-board":
        return f"{len(_changed_threads(threads))} threads changed in the current week window."
    if section_id == "source-contribution":
        return "Source/channel and concept contribution board."
    if section_id == "study-backlog":
        return "Highest-utility atoms to study later."
    return "Bounded audit metadata for the Atlas."
