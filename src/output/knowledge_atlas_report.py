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
    _link,
    _metric_card,
    _momentum_bar,
    _learning_actions,
    _source_channel_counts,
    _source_links,
    _status_label,
    _term_counts,
    _truncate_text,
    load_ai_intelligence_context,
)
from output.learning_layer import build_project_learning_projection
from output.report_quality import MATCHES_TRACE_RE, ReportQualityFinding, SEVERITY_CRITICAL


OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "knowledge_atlas"
ATLAS_SECTIONS = (
    ("atlas-overview", "Atlas Overview", "overview"),
    ("thread-navigation", "Thread Navigation", "thread_navigation"),
    ("project-learning", "Project And Learning Intelligence", "project_learning"),
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
    project_learning_projection = _atlas_project_learning_projection(context)
    section_bodies = {
        "atlas-overview": _render_atlas_overview(context),
        "thread-navigation": _render_thread_navigation(context),
        "project-learning": _render_project_learning_projection(project_learning_projection),
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
.thread-nav-grid {{ display:grid; grid-template-columns:minmax(220px,300px) minmax(0,1fr); gap:14px; align-items:start; }}
.thread-index {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#fbfcfd; }}
.thread-index ol {{ margin:8px 0 0; padding-left:20px; }}
.thread-detail {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:#fbfcfd; margin:0 0 12px; }}
.thread-detail-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:10px; }}
.evidence-item {{ border:1px solid var(--line); border-radius:8px; padding:10px; background:#fff; }}
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
@media (max-width:860px) {{ .thread-nav-grid {{ grid-template-columns:1fr; }} }}
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
    project_learning_projection = _atlas_project_learning_projection(context)
    intelligence_contract = build_canonical_intelligence_contract(
        context,
        project_learning_projection=project_learning_projection,
    )
    thread_navigation = _thread_navigation_model(context)
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
        "thread_navigation": thread_navigation,
        "project_learning_projection": project_learning_projection,
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


def _thread_navigation_model(context: dict) -> dict:
    threads = context.get("threads") or []
    items = [_thread_navigation_item(thread) for thread in threads[:12]]
    return {
        "schema_version": "knowledge_atlas_thread_navigation.v1",
        "week_label": context.get("week_label"),
        "thread_count": len(items),
        "source_atom_count": len(_all_atoms(threads)),
        "threads": items,
        "bounded_context_note": "Atlas navigation is built from curated Idea Threads and Knowledge Atoms, not raw Telegram firehose.",
    }


def _thread_navigation_item(thread: dict) -> dict:
    atoms = [atom for atom in (thread.get("atoms") or []) if isinstance(atom, dict)]
    evidence_items = [_atlas_evidence_item(atom) for atom in atoms[:6]]
    source_urls = _unique_string(
        url
        for atom in atoms
        for url in (atom.get("source_urls") or [])
        if str(url or "").strip()
    )
    source_channels = _unique_string(
        _source_channel_from_url(url)
        for url in source_urls
        if _source_channel_from_url(url)
    )
    current_claims = _string_values(thread.get("current_claims"))
    contradictions = _string_values(thread.get("contradictions"))
    superseded = _string_values(thread.get("superseded_claims"))
    return {
        "id": f"atlas-thread-{_slug(thread.get('slug') or thread.get('title') or 'thread')}",
        "slug": thread.get("slug"),
        "title": thread.get("title") or thread.get("slug") or "Untitled thread",
        "status": thread.get("status") or "active",
        "maturity": _thread_maturity(thread),
        "momentum_30d": float(thread.get("momentum_30d") or 0.0),
        "evidence_growth": {
            "atom_count": int(thread.get("atom_count") or len(atoms)),
            "rendered_evidence_count": len(evidence_items),
            "source_channel_count": int(thread.get("source_channel_count") or len(source_channels)),
            "changed_this_week": bool(thread.get("changed_this_week")),
        },
        "current_understanding": thread.get("summary") or (current_claims[0] if current_claims else ""),
        "change_since_previous_period": _thread_change_summary(thread, atoms),
        "timeline": _thread_timeline(atoms),
        "claims": current_claims[:5],
        "evidence_items": evidence_items,
        "contradictions": contradictions[:5],
        "superseded_claims": superseded[:5],
        "source_diversity": {
            "source_count": len(source_urls),
            "source_channel_count": len(source_channels),
            "channels": source_channels[:8],
        },
        "project_connections": _project_connections(thread, atoms),
        "decisions": _thread_decisions(thread),
        "open_questions": _open_questions(thread, atoms),
        "study_next": _study_next(thread, atoms),
        "source_urls": source_urls[:8],
    }


def _atlas_evidence_item(atom: dict) -> dict:
    urls = _string_values(atom.get("source_urls"))
    return {
        "atom_id": atom.get("id"),
        "claim": atom.get("claim"),
        "summary": atom.get("summary"),
        "evidence_quote": atom.get("evidence_quote"),
        "relation": atom.get("relation") or "supports",
        "atom_type": atom.get("atom_type"),
        "week_label": atom.get("week_label"),
        "last_seen_at": atom.get("last_seen_at"),
        "confidence": atom.get("confidence"),
        "source_urls": urls[:4],
    }


def _thread_timeline(atoms: list[dict]) -> list[dict]:
    rows = []
    for atom in sorted(atoms, key=lambda item: str(item.get("last_seen_at") or ""), reverse=True)[:6]:
        rows.append(
            {
                "date": str(atom.get("last_seen_at") or "")[:10],
                "atom_id": atom.get("id"),
                "claim": atom.get("claim"),
                "relation": atom.get("relation") or "supports",
                "source_urls": _string_values(atom.get("source_urls"))[:3],
            }
        )
    return rows


def _thread_maturity(thread: dict) -> str:
    atom_count = int(thread.get("atom_count") or len(thread.get("atoms") or []))
    source_channels = int(thread.get("source_channel_count") or 0)
    status = str(thread.get("status") or "")
    if status in {"production_pattern", "resolved"} or (atom_count >= 4 and source_channels >= 2):
        return "mature"
    if atom_count >= 2:
        return "developing"
    return "early"


def _thread_change_summary(thread: dict, atoms: list[dict]) -> str:
    if thread.get("changed_this_week"):
        latest = next((atom for atom in atoms if atom.get("claim")), None)
        if latest:
            return f"Current-week movement: {latest.get('claim')}"
        return "Current-week movement is visible, but no rendered atom claim is available."
    if atoms:
        return "No current-week movement in the bounded Atlas window; keep as background context."
    return "No atom-level evidence is available in this Atlas window."


def _project_connections(thread: dict, atoms: list[dict]) -> list[dict]:
    text = " ".join(
        [
            str(thread.get("title") or ""),
            str(thread.get("summary") or ""),
            " ".join(_string_values(thread.get("current_claims"))),
            " ".join(str(atom.get("claim") or "") for atom in atoms),
            " ".join(" ".join(_string_values(atom.get("tools"))) for atom in atoms),
        ]
    ).lower()
    connections = []
    if any(term in text for term in ("codex", "eval", "agent", "rag", "telegram")):
        connections.append(
            {
                "project": "telegram-research-agent",
                "connection_type": "project_watch",
                "rationale": "Thread overlaps current AI intelligence and evaluation workflows; verify before turning into project work.",
            }
        )
    if not connections:
        connections.append(
            {
                "project": None,
                "connection_type": "learning_only_implication",
                "rationale": "No active project connection is explicit in the curated thread evidence.",
            }
        )
    return connections[:3]


def _thread_decisions(thread: dict) -> list[dict]:
    status = str(thread.get("status") or "active")
    if status in {"hype_only", "resolved"}:
        decision = "defer"
        rationale = f"Thread status is {status}; keep evidence visible but do not make it a weekly action."
    elif bool(thread.get("changed_this_week")):
        decision = "verify_first"
        rationale = "Current-week movement exists; verify source evidence before acting."
    else:
        decision = "watch"
        rationale = "No current-week change; keep it in Atlas context."
    return [{"decision": decision, "rationale": rationale}]


def _open_questions(thread: dict, atoms: list[dict]) -> list[str]:
    questions = []
    if not _string_values(thread.get("contradictions")):
        questions.append("What would contradict the current understanding?")
    if int(thread.get("source_channel_count") or 0) <= 1:
        questions.append("Can an independent source confirm this thread?")
    if not atoms:
        questions.append("Which source atom should anchor this thread?")
    return questions[:3]


def _study_next(thread: dict, atoms: list[dict]) -> list[str]:
    items = []
    for atom in sorted(atoms, key=lambda item: float(item.get("practical_utility_score") or 0.0), reverse=True)[:2]:
        if atom.get("claim"):
            items.append(str(atom.get("claim")))
    if not items:
        items.append(f"Review thread: {thread.get('title') or thread.get('slug') or 'Untitled thread'}")
    return items[:3]


def _render_thread_navigation(context: dict) -> str:
    navigation = _thread_navigation_model(context)
    threads = [item for item in navigation.get("threads") or [] if isinstance(item, dict)]
    if not threads:
        return "<p>No navigable Idea Threads are available yet.</p>"
    index_items = "".join(
        f'<li><a href="#{_escape(thread["id"])}">{_escape(thread.get("title") or "Thread")}</a>'
        f'<p class="muted">{_escape(thread.get("status") or "active")} · {_escape(thread.get("maturity") or "early")}</p></li>'
        for thread in threads
    )
    detail_cards = "".join(_render_thread_detail(thread) for thread in threads[:8])
    return (
        '<div class="thread-nav-grid">'
        '<aside class="thread-index"><h3>Thread Index</h3>'
        f'<ol>{index_items}</ol>'
        '<p class="muted">Bounded to curated Idea Threads; not a raw Telegram mirror.</p>'
        '</aside>'
        f'<div>{detail_cards}</div>'
        '</div>'
    )


def _render_thread_detail(thread: dict) -> str:
    evidence_items = [item for item in thread.get("evidence_items") or [] if isinstance(item, dict)]
    timeline_items = [item for item in thread.get("timeline") or [] if isinstance(item, dict)]
    claims = _html_list(thread.get("claims"), "No current claims captured.")
    contradictions = _html_list(thread.get("contradictions"), "No explicit contradictions captured.")
    questions = _html_list(thread.get("open_questions"), "No open questions captured.")
    study = _html_list(thread.get("study_next"), "No study-next item captured.")
    sources = "".join(f'<li>{_link(url, url)}</li>' for url in (thread.get("source_urls") or [])[:5]) or '<li class="muted">No source links captured.</li>'
    evidence = "".join(_render_evidence_item(item) for item in evidence_items[:4]) or '<p class="muted">No rendered evidence items.</p>'
    timeline = "".join(_render_timeline_item(item) for item in timeline_items[:5]) or '<li class="muted">No timeline entries captured.</li>'
    project_connections = "".join(
        f'<li><b>{_escape(item.get("connection_type") or "connection")}</b>: {_escape(item.get("rationale") or "")}</li>'
        for item in (thread.get("project_connections") or [])[:3]
        if isinstance(item, dict)
    ) or '<li class="muted">No project connections.</li>'
    decisions = "".join(
        f'<li><b>{_escape(item.get("decision") or "watch")}</b>: {_escape(item.get("rationale") or "")}</li>'
        for item in (thread.get("decisions") or [])[:3]
        if isinstance(item, dict)
    ) or '<li class="muted">No decision projection.</li>'
    growth = thread.get("evidence_growth") if isinstance(thread.get("evidence_growth"), dict) else {}
    diversity = thread.get("source_diversity") if isinstance(thread.get("source_diversity"), dict) else {}
    return (
        f'<article class="thread-detail" id="{_escape(thread.get("id") or "")}">'
        f'<h3>{_escape(thread.get("title") or "Thread")}</h3>'
        f'<p><span class="tag">{_escape(_status_label(thread.get("status") or "active"))}</span> '
        f'<span class="muted">maturity {_escape(thread.get("maturity") or "early")}</span></p>'
        f'<p>{_escape(_truncate_text(thread.get("current_understanding") or "", 260))}</p>'
        f'<p class="muted"><b>Change since previous period:</b> {_escape(_truncate_text(thread.get("change_since_previous_period") or "", 220))}</p>'
        f'<h3>Thread Timeline</h3><ol class="timeline">{timeline}</ol>'
        '<div class="thread-detail-grid">'
        f'<div><h3>Claims</h3>{claims}</div>'
        f'<div><h3>Contradictions</h3>{contradictions}</div>'
        f'<div><h3>Open Questions</h3>{questions}</div>'
        f'<div><h3>Study Next</h3>{study}</div>'
        '</div>'
        '<div class="thread-detail-grid">'
        f'<div><h3>Momentum Vs Evidence</h3><p>Momentum {_escape(str(thread.get("momentum_30d") or 0))}; {_escape(str(growth.get("atom_count", 0)))} atoms; {_escape(str(growth.get("source_channel_count", 0)))} source channel(s); changed this week: {_escape(str(bool(growth.get("changed_this_week"))).lower())}.</p></div>'
        f'<div><h3>Source Diversity</h3><p>{_escape(str(diversity.get("source_count", 0)))} source link(s); channels: {_escape(", ".join(diversity.get("channels") or []) or "none")}.</p></div>'
        f'<div><h3>Project Connections</h3><ul>{project_connections}</ul></div>'
        f'<div><h3>Decisions</h3><ul>{decisions}</ul></div>'
        '</div>'
        f'<h3>Evidence Pane</h3><div class="thread-detail-grid">{evidence}</div>'
        f'<h3>Original Source Links</h3><ul>{sources}</ul>'
        '</article>'
    )


def _atlas_project_learning_projection(context: dict) -> dict:
    actions = _learning_actions(context.get("threads") or [], context.get("feedback_context") or {})
    return build_project_learning_projection(
        context,
        actions=actions,
        feedback_context=context.get("feedback_context") or {},
    )


def _render_project_learning_projection(projection: dict) -> str:
    project = projection.get("project_intelligence") if isinstance(projection.get("project_intelligence"), dict) else {}
    learning = projection.get("learning_intelligence") if isinstance(projection.get("learning_intelligence"), dict) else {}
    external = "".join(
        '<article class="atlas-card">'
        f'<h3>{_escape(item.get("title") or "External signal")}</h3>'
        f'<p class="muted">{_escape(item.get("atom_type") or "unknown")} · {_escape(item.get("context_policy") or "source_backed")}</p>'
        f'<p class="sources">{_source_link_list(item.get("source_refs"))}</p>'
        '</article>'
        for item in _object_list(project.get("external_signals"))[:4]
    )
    confirmed = _projection_list(
        project.get("confirmed_implications"),
        empty_text="No confirmed project implication.",
        title_key="project",
        body_key="thread_title",
    )
    watches = _projection_list(
        project.get("weak_watches"),
        empty_text="No weak project watch.",
        title_key="project",
        body_key="thread_title",
    )
    rejected = "".join(
        f'<li>{_escape(item.get("project") or "Project")} / {_escape(item.get("term") or "term")}: {_escape(item.get("reason") or "rejected")}</li>'
        for item in _object_list(project.get("rejected_overlaps"))[:8]
    ) or '<li class="muted">No rejected broad overlaps recorded.</li>'
    ideas = _projection_list(
        project.get("tiny_pr_ideas"),
        empty_text="No source-backed tiny PR idea yet.",
        title_key="title",
        body_key="next_step",
    )
    stale = _projection_list(
        project.get("stale_decisions"),
        empty_text="No stale decision projection.",
        title_key="title",
        body_key="review_reason",
    )
    debt = "".join(
        f'<li><b>{_escape(item.get("debt_type") or "debt")}</b>: {_escape(item.get("description") or "")}</li>'
        for item in _object_list(project.get("research_debt"))[:8]
    ) or '<li class="muted">No research debt recorded.</li>'
    repeated = "".join(
        f'<li>{_escape(item.get("theme") or "theme")} <span class="muted">{_escape(item.get("frequency") or 0)} atom(s)</span></li>'
        for item in _object_list(project.get("repeated_themes_without_action"))[:8]
    ) or '<li class="muted">No repeated source theme without action.</li>'
    stage_counts = learning.get("stage_counts") if isinstance(learning.get("stage_counts"), dict) else {}
    stage_rows = "".join(
        f"<tr><td>{_escape(stage)}</td><td>{_escape(stage_counts.get(stage, 0))}</td></tr>"
        for stage in learning.get("allowed_stages") or []
    )
    objectives = "".join(
        f'<li><b>{_escape(item.get("topic") or "Learning objective")}</b> '
        f'<span class="tag">{_escape(item.get("stage") or "unknown")}</span>'
        f'<p class="muted">{_escape(item.get("stage_evidence") or "")}</p></li>'
        for item in _object_list(learning.get("objectives"))[:8]
    ) or '<li class="muted">No learning objectives projected.</li>'
    return (
        '<h3>External Signals</h3><div class="atlas-grid">'
        + (external or '<article class="atlas-card"><p class="muted">No external signals projected.</p></article>')
        + '</div><div class="thread-detail-grid">'
        f'<div><h3>Confirmed Implications</h3>{confirmed}</div>'
        f'<div><h3>Weak Watches</h3>{watches}</div>'
        f'<div><h3>Rejected Overlaps</h3><ul>{rejected}</ul></div>'
        f'<div><h3>Tiny PR Ideas</h3>{ideas}</div>'
        f'<div><h3>Stale Decisions</h3>{stale}</div>'
        f'<div><h3>Research Debt</h3><ul>{debt}</ul></div>'
        f'<div><h3>Repeated Themes Without Action</h3><ul>{repeated}</ul></div>'
        f'<div><h3>Learning Stages</h3><table><tbody>{stage_rows}</tbody></table>'
        '<p class="muted">Passive reading is not mastery; no feedback stays unknown.</p>'
        f'<ol>{objectives}</ol></div>'
        '</div>'
    )


def _render_timeline_item(item: dict) -> str:
    source_links = " ".join(_link(url, f"source {index}") for index, url in enumerate(item.get("source_urls") or [], start=1))
    return (
        "<li>"
        f'<b>{_escape(item.get("date") or "unknown date")}</b> '
        f'{_escape(item.get("claim") or "Timeline item")}'
        f'<p class="muted">Atom {_escape(str(item.get("atom_id") or ""))} · {_escape(item.get("relation") or "supports")} {source_links}</p>'
        "</li>"
    )


def _render_evidence_item(item: dict) -> str:
    source_links = " ".join(_link(url, f"source {index}") for index, url in enumerate(item.get("source_urls") or [], start=1))
    return (
        '<div class="evidence-item">'
        f'<p><b>{_escape(item.get("claim") or "Evidence item")}</b></p>'
        f'<p class="muted">Atom { _escape(item.get("atom_id") or "") } · {_escape(item.get("atom_type") or "atom")} · {_escape(item.get("relation") or "supports")}</p>'
        f'<p>{_escape(_truncate_text(item.get("evidence_quote") or item.get("summary") or "", 180))}</p>'
        f'<p class="sources">{source_links or "source pending"}</p>'
        '</div>'
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
    if section_id == "thread-navigation":
        return f"{len(threads[:12])} navigable thread detail cards with evidence panes and source links."
    if section_id == "project-learning":
        return "Project implications, weak watches, rejected overlaps, research debt, and learning stage projection."
    if section_id == "idea-map":
        return "Rolling map of current Idea Threads and claims."
    if section_id == "trend-board":
        return f"{len(_changed_threads(threads))} threads changed in the current week window."
    if section_id == "source-contribution":
        return "Source/channel and concept contribution board."
    if section_id == "study-backlog":
        return "Highest-utility atoms to study later."
    return "Bounded audit metadata for the Atlas."


def _projection_list(value: object, *, empty_text: str, title_key: str, body_key: str) -> str:
    rows = []
    for item in _object_list(value)[:8]:
        title = _escape(item.get(title_key) or item.get("project") or item.get("title") or "Item")
        body = _escape(item.get(body_key) or item.get("next_step") or item.get("source_policy") or "")
        rows.append(f"<li><b>{title}</b><p class=\"muted\">{body}</p></li>")
    if not rows:
        return f'<p class="muted">{_escape(empty_text)}</p>'
    return "<ul>" + "".join(rows) + "</ul>"


def _html_list(value: object, empty_text: str) -> str:
    items = _string_values(value)
    if not items:
        return f'<p class="muted">{_escape(empty_text)}</p>'
    return "<ul>" + "".join(f"<li>{_escape(item)}</li>" for item in items[:6]) + "</ul>"


def _object_list(value: object) -> list[dict]:
    return [item for item in (value if isinstance(value, list) else []) if isinstance(item, dict)]


def _source_link_list(value: object) -> str:
    links = _string_values(value)
    return " ".join(_link(url, f"source {index}") for index, url in enumerate(links[:4], start=1)) or '<span class="muted">source pending</span>'


def _string_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]
    return _unique_string(str(item).strip() for item in values if str(item).strip())


def _unique_string(values) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _source_channel_from_url(url: object) -> str:
    text = str(url or "").strip()
    marker = "t.me/"
    if marker not in text:
        return ""
    channel = text.split(marker, maxsplit=1)[1].split("/", maxsplit=1)[0].strip()
    return f"@{channel}" if channel else ""


def _slug(value: object) -> str:
    text = "".join(ch.lower() if ch.isascii() and ch.isalnum() else "-" for ch in str(value or "item"))
    parts = [part for part in text.split("-") if part]
    return "-".join(parts[:8]) or "item"
