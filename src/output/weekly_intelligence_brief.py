from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from config.settings import PROJECT_ROOT, Settings
from output.ai_report_contract import (
    INTELLIGENCE_CONTRACT_VERSION,
    RADAR_INTELLIGENCE_CONTRACT_VERSION,
    build_canonical_intelligence_contract,
)
from output.ai_intelligence_report import (
    _all_atoms,
    _analysis_text,
    _changed_threads,
    _current_week_label,
    _escape,
    _learning_actions,
    _link,
    _personal_learning_loop,
    _truncate_text,
    load_ai_intelligence_context,
)
from output.report_quality import MATCHES_TRACE_RE, ReportQualityFinding, SEVERITY_CRITICAL


OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "weekly_intelligence_briefs"
BRIEF_SECTIONS = (
    ("brief-decision", "Decision Snapshot", "decision_snapshot"),
    ("brief-changes", "What Changed This Week", "week_delta"),
    ("brief-actions", "Actions And Read/Try Prompts", "actions"),
    ("brief-mvp-radar", "MVP Radar", "mvp_radar"),
    ("brief-feedback", "Feedback Prompts", "feedback"),
)
NON_BUILD_READY_RECOMMENDATIONS = {
    "revisit_with_evidence_gap",
    "needs_more_evidence",
    "needs_more_specific_scope",
    "existing_project_context",
    "reject",
}


@dataclass(frozen=True)
class WeeklyIntelligenceBriefSummary:
    week_label: str
    generated_at: str
    html_path: str
    json_path: str
    thread_count: int
    source_atom_count: int
    changed_thread_count: int
    action_count: int
    mvp_status: str
    quality_finding_count: int
    notification_text: str


class WeeklyIntelligenceBriefQualityError(ValueError):
    def __init__(self, findings: list[ReportQualityFinding]) -> None:
        self.findings = findings
        messages = "; ".join(f"{finding.artifact_type}: {finding.message}" for finding in findings)
        super().__init__(f"Weekly Intelligence Brief failed quality gates: {messages}")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def build_weekly_intelligence_brief_artifact(
    context: dict,
    *,
    generated_at: str,
    output_root: str | Path | None = None,
    mvp_radar: Mapping[str, object] | None = None,
    related_artifacts: dict | None = None,
) -> WeeklyIntelligenceBriefSummary:
    normalized_mvp = _normalize_mvp_radar(mvp_radar or {})
    html_text, actions = render_weekly_intelligence_brief_html(
        context,
        generated_at=generated_at,
        mvp_radar=normalized_mvp,
    )
    findings = validate_weekly_intelligence_brief_html(html_text)
    critical = [finding for finding in findings if finding.severity == SEVERITY_CRITICAL]
    if critical:
        raise WeeklyIntelligenceBriefQualityError(critical)

    root = Path(output_root) if output_root is not None else OUTPUT_DIR
    root.mkdir(parents=True, exist_ok=True)
    week_label = str(context.get("week_label") or "")
    html_path = root / f"{week_label}.weekly-brief.html"
    json_path = root / f"{week_label}.weekly-brief.json"
    threads = context.get("threads") or []
    atoms = _all_atoms(threads)
    metadata = _weekly_brief_metadata(
        context,
        generated_at=generated_at,
        html_path=html_path,
        json_path=json_path,
        actions=actions,
        mvp_radar=normalized_mvp,
        quality_findings=findings,
        related_artifacts=related_artifacts or {},
    )
    html_path.write_text(html_text, encoding="utf-8")
    json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = WeeklyIntelligenceBriefSummary(
        week_label=week_label,
        generated_at=generated_at,
        html_path=str(html_path),
        json_path=str(json_path),
        thread_count=len(threads),
        source_atom_count=len(atoms),
        changed_thread_count=len(_changed_threads(threads)),
        action_count=len(actions),
        mvp_status=str(normalized_mvp.get("dossier_status") or normalized_mvp.get("recommendation") or normalized_mvp.get("status") or "unknown"),
        quality_finding_count=len(findings),
        notification_text="",
    )
    return WeeklyIntelligenceBriefSummary(
        **{
            **asdict(summary),
            "notification_text": build_weekly_intelligence_brief_notification(summary),
        }
    )


def generate_weekly_intelligence_brief(
    settings: Settings,
    *,
    week_label: str | None = None,
    threads_limit: int = 12,
    atoms_limit: int = 8,
    output_root: str | Path | None = None,
    mvp_radar_json_path: str | Path | None = None,
    now: datetime | None = None,
) -> WeeklyIntelligenceBriefSummary:
    clean_week = str(week_label or _current_week_label(now)).strip()
    generated_at = (now or _utc_now()).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        context = load_ai_intelligence_context(
            connection,
            week_label=clean_week,
            threads_limit=max(1, int(threads_limit or 12)),
            atoms_limit=max(1, int(atoms_limit or 8)),
        )
    return build_weekly_intelligence_brief_artifact(
        context,
        generated_at=generated_at,
        output_root=output_root,
        mvp_radar=load_mvp_radar_summary(clean_week, mvp_radar_json_path),
    )


def render_weekly_intelligence_brief_html(
    context: dict,
    *,
    generated_at: str | None = None,
    mvp_radar: Mapping[str, object] | None = None,
) -> tuple[str, list[dict]]:
    week_label = str(context.get("week_label") or "")
    generated = generated_at or _utc_now_iso()
    actions = _learning_actions(context.get("threads") or [], context.get("feedback_context") or {})
    normalized_mvp = _normalize_mvp_radar(mvp_radar or {})
    section_bodies = {
        "brief-decision": _render_decision_snapshot(context, actions, normalized_mvp),
        "brief-changes": _render_week_changes(context),
        "brief-actions": _render_brief_actions(context, actions),
        "brief-mvp-radar": _render_mvp_radar(normalized_mvp),
        "brief-feedback": _render_feedback_prompts(context),
    }
    nav = "".join(f'<a href="#{section_id}">{_escape(title)}</a>' for section_id, title, _kind in BRIEF_SECTIONS)
    sections = "\n".join(
        f'<section id="{section_id}"><h2>{_escape(title)}</h2>{section_bodies[section_id]}</section>'
        for section_id, title, _kind in BRIEF_SECTIONS
    )
    html_text = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="intelligence-contract-version" content="{_escape(INTELLIGENCE_CONTRACT_VERSION)}">
<meta name="radar-intelligence-contract-version" content="{_escape(RADAR_INTELLIGENCE_CONTRACT_VERSION)}">
<title>Weekly Intelligence Brief { _escape(week_label) }</title>
<style>
:root {{ color-scheme: light; --ink:#17202a; --muted:#65717d; --line:#d8dee6; --panel:#ffffff; --bg:#f5f7f9; --accent:#1d4ed8; --ok:#166534; --warn:#92400e; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--ink); line-height:1.54; }}
a {{ color:#0b63ce; text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
header {{ max-width:980px; margin:0 auto; padding:30px 24px 16px; }}
.kicker {{ color:var(--accent); font-weight:700; text-transform:uppercase; font-size:12px; margin:0 0 8px; letter-spacing:.08em; }}
h1 {{ font-size:32px; line-height:1.16; margin:0 0 8px; letter-spacing:0; }}
h2 {{ font-size:21px; line-height:1.24; margin:0 0 14px; letter-spacing:0; }}
h3 {{ font-size:17px; line-height:1.3; margin:0 0 8px; letter-spacing:0; }}
p {{ margin:0 0 12px; }}
nav {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:16px; }}
nav a {{ border:1px solid var(--line); background:#fff; border-radius:6px; padding:7px 10px; color:#26323f; font-size:13px; }}
main {{ max-width:980px; margin:0 auto; padding:0 24px 38px; }}
section {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; margin:0 0 12px; }}
.muted {{ color:var(--muted); font-size:13px; }}
.decision-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px; margin:0 0 14px; }}
.decision-card, .brief-card {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#fbfcfd; }}
.decision-value {{ display:block; font-size:23px; font-weight:700; }}
.tag {{ display:inline-block; border:1px solid #bdd2ff; background:#eff6ff; color:#1d4ed8; border-radius:999px; padding:2px 8px; font-size:12px; font-weight:700; }}
.status-investigate {{ color:var(--warn); }}
.status-build {{ color:var(--ok); }}
.mvp-gate-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:10px; margin:10px 0 14px; }}
.mvp-gate-panel, .mvp-action-panel {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#f7fafc; }}
.mvp-gate-panel p:last-child, .mvp-action-panel p:last-child {{ margin-bottom:0; }}
.evidence-list li, .missing-list li {{ margin-bottom:7px; }}
code {{ background:#eef2f7; border:1px solid var(--line); border-radius:5px; padding:1px 5px; white-space:normal; overflow-wrap:anywhere; }}
.action-list {{ display:grid; grid-template-columns:1fr; gap:10px; }}
.action-card {{ border:1px solid var(--line); border-radius:8px; padding:13px; background:#fbfcfd; }}
.sources {{ margin-top:6px; font-size:13px; }}
ol, ul {{ padding-left:22px; }}
@media (max-width:720px) {{ h1 {{ font-size:27px; }} header, main {{ padding-left:16px; padding-right:16px; }} section {{ padding:16px; }} }}
</style>
</head>
<body>
<header>
<p class="kicker">Weekly Intelligence Brief</p>
<h1>Weekly Intelligence Brief - {_escape(week_label)}</h1>
<p class="muted">Generated {_escape(generated)}. Short operational readout; the cumulative map lives in Knowledge Atlas.</p>
<nav>{nav}</nav>
</header>
<main>
{sections}
</main>
</body>
</html>
"""
    return html_text, actions


def validate_weekly_intelligence_brief_html(html_text: str) -> list[ReportQualityFinding]:
    findings: list[ReportQualityFinding] = []
    content = str(html_text or "")
    if "<!doctype html>" not in content.lower():
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="weekly_intelligence_brief",
                message="Weekly Intelligence Brief must be standalone HTML",
                line_hint="doctype",
            )
        )
    for section_id, title, _kind in BRIEF_SECTIONS:
        if f'id="{section_id}"' not in content:
            findings.append(
                ReportQualityFinding(
                    severity=SEVERITY_CRITICAL,
                    artifact_type="weekly_intelligence_brief",
                    message=f"Required Weekly Brief section is missing: {title}",
                    line_hint=section_id,
                )
            )
    for line_number, line in enumerate(content.splitlines(), start=1):
        if MATCHES_TRACE_RE.search(line):
            findings.append(
                ReportQualityFinding(
                    severity=SEVERITY_CRITICAL,
                    artifact_type="weekly_intelligence_brief",
                    message="Internal matching trace is visible in Weekly Brief",
                    line_hint=f"line {line_number}",
                )
            )
    if content.find('id="brief-actions"') > content.find('id="brief-mvp-radar"'):
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="weekly_intelligence_brief",
                message="Weekly Brief must surface actions before deeper MVP detail",
                line_hint="brief-actions",
            )
        )
    if len(content) > 90000:
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="weekly_intelligence_brief",
                message="Weekly Brief is too long for a short operational surface",
                line_hint="html length",
            )
        )
    return findings


def load_mvp_radar_summary(week_label: str, explicit_path: str | Path | None = None) -> dict:
    for path in _candidate_mvp_paths(week_label, explicit_path):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            result = _normalize_mvp_radar(payload)
            result["source_path"] = str(path)
            return result
    return {
        "status": "not_available",
        "selected_candidate": None,
        "dossier_status": None,
        "recommendation": "needs_more_evidence",
        "source_mix": {},
        "missing_evidence": ["MVP Radar JSON artifact was not available for this week."],
        "next_validation": ["Run mvp-weekly after opportunity seed export."],
        "source_path": str(explicit_path) if explicit_path else None,
    }


def build_weekly_intelligence_brief_notification(summary: WeeklyIntelligenceBriefSummary) -> str:
    return (
        f"Weekly Intelligence Brief {summary.week_label} is ready.\n"
        f"Changed: {summary.changed_thread_count} | Actions: {summary.action_count} | MVP: {summary.mvp_status}\n"
        f"Open: {summary.html_path}"
    )


def _weekly_brief_metadata(
    context: dict,
    *,
    generated_at: str,
    html_path: Path,
    json_path: Path,
    actions: list[dict],
    mvp_radar: dict,
    quality_findings: list[ReportQualityFinding],
    related_artifacts: dict,
) -> dict:
    threads = context.get("threads") or []
    atoms = _all_atoms(threads)
    learning_loop = _personal_learning_loop(threads, actions, context.get("feedback_context") or {})
    intelligence_contract = build_canonical_intelligence_contract(
        context,
        mvp_radar=mvp_radar,
    )
    sections = [
        {
            "id": section_id,
            "title": title,
            "title_en": title,
            "kind": kind,
            "summary": _section_metadata_summary(context, actions, mvp_radar, section_id),
        }
        for section_id, title, kind in BRIEF_SECTIONS
    ]
    return {
        "schema_version": "split_ai_report.v1",
        "contract_version": INTELLIGENCE_CONTRACT_VERSION,
        "radar_contract_version": RADAR_INTELLIGENCE_CONTRACT_VERSION,
        "artifact_type": "weekly_intelligence_brief",
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
        "changed_thread_count": len(_changed_threads(threads)),
        "actions": actions,
        "personal_learning_loop": learning_loop,
        "intelligence_contract": intelligence_contract,
        "mvp_radar": mvp_radar,
        "feedback_context": context.get("feedback_context") or {},
        "quality_findings": [finding.as_dict() for finding in quality_findings],
        "retrieval_note": "Weekly Intelligence Brief is the short operational weekly surface; Knowledge Atlas owns cumulative context.",
    }


def _render_decision_snapshot(context: dict, actions: list[dict], mvp_radar: Mapping[str, object]) -> str:
    threads = context.get("threads") or []
    changed = _changed_threads(threads)
    mvp_status = str(mvp_radar.get("dossier_status") or mvp_radar.get("recommendation") or mvp_radar.get("status") or "unknown")
    decision_class = "status-build" if mvp_status in {"build", "focused_experiment"} else "status-investigate"
    return (
        '<div class="decision-grid">'
        f'<div class="decision-card"><span class="decision-value">{_escape(len(changed))}</span><span class="muted">changed threads</span></div>'
        f'<div class="decision-card"><span class="decision-value">{_escape(len(actions))}</span><span class="muted">operator actions</span></div>'
        f'<div class="decision-card"><span class="decision-value {decision_class}">{_escape(mvp_status)}</span><span class="muted">MVP Radar status</span></div>'
        f'<div class="decision-card"><span class="decision-value">{_escape(len(_all_atoms(threads)))}</span><span class="muted">source atoms in brief context</span></div>'
        "</div>"
        "<p>Read this first for this week's decisions. Use Knowledge Atlas only when you need trend history or source contribution.</p>"
    )


def _render_week_changes(context: dict) -> str:
    analysis = context.get("frontier_analysis") or {}
    changes = analysis.get("what_changed") or []
    if changes:
        items = []
        for item in changes[:5]:
            title = _analysis_text(item, "title", "change", "topic") or "Change"
            body = _analysis_text(item, "summary", "why_it_matters", "reason")
            items.append(f"<li><b>{_escape(title)}</b><p>{_escape(body)}</p></li>")
        return f"<ol>{''.join(items)}</ol>"
    changed_threads = _changed_threads(context.get("threads") or [])
    if not changed_threads:
        return "<p>No current-week Idea Thread movement is visible.</p>"
    items = []
    for thread in changed_threads[:5]:
        items.append(
            "<li>"
            f"<b>{_escape(thread.get('title') or thread.get('slug') or 'Untitled')}</b>"
            f"<p>{_escape(_truncate_text(thread.get('summary') or '', 220))}</p>"
            "</li>"
        )
    return f"<ol>{''.join(items)}</ol>"


def _render_brief_actions(context: dict, actions: list[dict]) -> str:
    cards = []
    for action in actions[:4]:
        cards.append(
            '<article class="action-card">'
            f'<h3>{_escape(action.get("title") or "Action")}</h3>'
            f'<p>{_escape(action.get("body") or "")}</p>'
            f'<p class="muted">Why selected: {_escape(action.get("why_selected") or "")}</p>'
            f'<p class="muted">Source links in action context: {_escape(action.get("source_count", 0))}</p>'
            '</article>'
        )
    loop = _personal_learning_loop(context.get("threads") or [], actions, context.get("feedback_context") or {})
    read_items = []
    for index, item in enumerate((loop.get("read_items") or [])[:3], start=1):
        source = _link(item.get("source_url") or "", f"Read {index}") if item.get("source_url") else '<span class="muted">source pending</span>'
        read_items.append(
            f'<li><b>{_escape(item.get("claim") or "Read item")}</b>'
            f'<p class="muted">Why selected: {_escape(item.get("why_selected") or "")}</p>{source}</li>'
        )
    try_items = "".join(
        f'<li><b>{_escape(item.get("title") or "Try item")}</b>: {_escape(item.get("body") or "")}'
        f'<p class="muted">Why selected: {_escape(item.get("why_selected") or "")}</p></li>'
        for item in (loop.get("try_items") or [])[:2]
    )
    return (
        '<div class="action-list">'
        + "".join(cards)
        + "</div>"
        '<div class="brief-card"><h3>Read Next</h3><ol>'
        + "".join(read_items)
        + '</ol></div><div class="brief-card"><h3>Try Next</h3><ol>'
        + try_items
        + "</ol></div>"
    )


def _render_mvp_radar(mvp_radar: Mapping[str, object]) -> str:
    candidate = str(mvp_radar.get("selected_candidate") or "No candidate selected")
    recommendation = str(mvp_radar.get("recommendation") or mvp_radar.get("dossier_status") or "needs_more_evidence")
    decision = "Do not build yet." if recommendation in NON_BUILD_READY_RECOMMENDATIONS else "Focused experiment may be allowed."
    missing = "".join(f"<li>{_escape(item)}</li>" for item in _string_values(mvp_radar.get("missing_evidence"))[:5])
    summary = _mvp_validation_summary(mvp_radar)
    missing_checklist = _render_missing_evidence_checklist(mvp_radar)
    if not missing_checklist:
        missing_checklist = f'<ul class="missing-list">{missing or "<li>No missing evidence listed.</li>"}</ul>'
    source_path = str(mvp_radar.get("source_path") or "")
    source_link = f'<p class="sources">{_link(source_path, "MVP Radar JSON")}</p>' if source_path else ""
    return (
        '<article class="brief-card">'
        f'<h3>{_escape(candidate)}</h3>'
        f'<p><span class="tag">{_escape(recommendation)}</span> {_escape(decision)}</p>'
        f'{source_link}'
        "<h3>MVP Radar Gate Card</h3>"
        '<div class="mvp-gate-grid">'
        '<div class="mvp-gate-panel">'
        f'<p><b>Matched gate evidence:</b> {_escape(str(summary["matched_gate_count"]))} '
        f'item(s), {_escape(summary["matched_source_types"])}.</p>'
        f'<p class="muted">{_escape(summary["external_context_note"])}</p>'
        '</div>'
        '<div class="mvp-gate-panel">'
        f'<p><b>Adapter status:</b> {_escape(summary["adapter_status"])}</p>'
        '<p class="muted">Market context: context only, not proof.</p>'
        '</div>'
        '</div>'
        f'{_render_validation_query_pack(mvp_radar, summary)}'
        f'{_render_matched_evidence(mvp_radar)}'
        "<h3>Missing Evidence Checklist</h3>"
        f'{missing_checklist}'
        "<h3>What Would Change The Decision</h3>"
        f'{_render_decision_change_action(mvp_radar, summary)}'
        "</article>"
    )


def _render_feedback_prompts(context: dict) -> str:
    feedback = context.get("feedback_context") or {}
    completion = feedback.get("feedback_completion") or {}
    missing = _string_values(completion.get("missing"))
    prompts = [
        "Which read item did you actually open?",
        "Which action changed a project decision?",
        "What was missing or overrated this week?",
    ]
    if missing:
        prompts.append("Feedback still missing: " + ", ".join(missing[:4]))
    return "<ul>" + "".join(f"<li>{_escape(prompt)}</li>" for prompt in prompts) + "</ul>"


def _normalize_mvp_radar(payload: Mapping[str, object]) -> dict:
    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
    selected = payload.get("selected") if isinstance(payload.get("selected"), Mapping) else {}
    candidate = (
        _clean_text(result.get("selected_title"))
        or _clean_text(selected.get("title"))
        or _clean_text(payload.get("selected_candidate"))
        or _clean_text(payload.get("selected_title"))
    )
    recommendation = (
        _clean_text(result.get("recommendation"))
        or _clean_text(selected.get("recommendation"))
        or _clean_text(payload.get("recommendation"))
    )
    dossier_status = (
        _clean_text(result.get("dossier_status"))
        or _clean_text(selected.get("dossier_status"))
        or _clean_text(payload.get("dossier_status"))
    )
    return {
        "status": _clean_text(payload.get("status")) or "loaded",
        "selected_candidate": candidate,
        "dossier_status": dossier_status,
        "recommendation": recommendation,
        "score": result.get("score") or selected.get("score") or payload.get("score"),
        "source_mix": _first_mapping(result.get("selected_source_mix"), selected.get("source_mix"), payload.get("source_mix")),
        "missing_evidence": _string_values(selected.get("missing_evidence") or result.get("missing_evidence") or payload.get("missing_evidence")),
        "next_validation": _string_values(selected.get("next_validation") or selected.get("next_step") or result.get("next_validation") or payload.get("next_validation")),
        "validation_queries": _first_mapping(selected.get("validation_queries"), payload.get("validation_queries"), result.get("validation_queries")),
        "matched_external_evidence": _object_list(selected.get("matched_external_evidence") or payload.get("matched_external_evidence") or result.get("matched_external_evidence")),
        "missing_evidence_by_category": _first_mapping(selected.get("missing_evidence_by_category"), payload.get("missing_evidence_by_category"), result.get("missing_evidence_by_category")),
        "validation_adapter_status": _first_mapping(payload.get("validation_adapter_status"), result.get("validation_adapter_status")),
        "decision_context": _first_mapping(payload.get("decision_context"), result.get("decision_context")),
        "decision_change_action": _first_mapping(selected.get("decision_change_action"), payload.get("decision_change_action"), result.get("decision_change_action")),
        "source_path": _clean_text(payload.get("source_path")),
    }


def _candidate_mvp_paths(week_label: str, explicit_path: str | Path | None) -> list[Path]:
    if explicit_path is not None:
        return [Path(explicit_path)]
    return [
        PROJECT_ROOT / "data" / "output" / "mvp_weekly" / f"mvp-weekly-{week_label}.json",
        PROJECT_ROOT / "data" / "output" / "mvp_weekly" / f"{week_label}.json",
        PROJECT_ROOT.parent / "Demand-to-MVP-Radar" / "reports" / "mvp_of_week" / f"mvp-weekly-{week_label}.json",
    ]


def _section_metadata_summary(
    context: dict,
    actions: list[dict],
    mvp_radar: Mapping[str, object],
    section_id: str,
) -> str:
    if section_id == "brief-decision":
        return f"{len(_changed_threads(context.get('threads') or []))} changed threads and {len(actions)} actions."
    if section_id == "brief-changes":
        return "This week's frontier changes or changed Idea Threads."
    if section_id == "brief-actions":
        return "Short read/try/action queue for the operator."
    if section_id == "brief-mvp-radar":
        summary = _mvp_validation_summary(mvp_radar)
        return (
            f"{mvp_radar.get('recommendation') or mvp_radar.get('dossier_status') or 'MVP Radar status'}; "
            f"{summary['matched_gate_count']} matched external gate item(s); next query: {summary['next_query'] or 'not listed'}."
        )
    return "Feedback prompts for the next report loop."


def _string_values(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    if value in (None, "", {}):
        return []
    return [str(value).strip()]


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _first_mapping(*values: object) -> dict:
    for value in values:
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _object_list(value: object) -> list[dict]:
    if not isinstance(value, (list, tuple)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _mvp_validation_summary(mvp_radar: Mapping[str, object]) -> dict[str, object]:
    matches = _object_list(mvp_radar.get("matched_external_evidence"))
    gate_matches = [
        match
        for match in matches
        if bool(match.get("supports_gate")) and bool(match.get("decision_grade", True))
    ]
    source_types = sorted(
        {
            str(match.get("source_type") or "").strip()
            for match in gate_matches
            if str(match.get("source_type") or "").strip()
        }
    )
    decision_context = _first_mapping(mvp_radar.get("decision_context"))
    external_context = _first_mapping(decision_context.get("external_research_context"))
    unmatched_count = _safe_int(external_context.get("record_count")) if external_context else 0
    adapter_status = _adapter_status_summary(_first_mapping(mvp_radar.get("validation_adapter_status")))
    next_query = _next_validation_query(mvp_radar)
    if gate_matches:
        context_note = "Matched decision-grade external evidence is allowed to affect Radar gates."
    elif unmatched_count:
        context_note = f"{unmatched_count} external context record(s) were unmatched and do not satisfy gates."
    else:
        context_note = "No matched external validation evidence found; run the next repeatable search."
    return {
        "matched_gate_count": len(gate_matches),
        "matched_source_types": ", ".join(source_types) or "types: none",
        "adapter_status": adapter_status,
        "external_context_note": context_note,
        "next_query": str(next_query.get("query") or ""),
        "next_intent": str(next_query.get("intent") or ""),
    }


def _adapter_status_summary(statuses: Mapping[str, object]) -> str:
    if not statuses:
        return "not reported"
    parts = []
    for name, details in list(statuses.items())[:4]:
        detail_map = _first_mapping(details)
        parts.append(f"{name}={detail_map.get('status') or 'unknown'}")
    return "; ".join(parts) or "not reported"


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _next_validation_query(mvp_radar: Mapping[str, object]) -> dict[str, object]:
    action = _first_mapping(mvp_radar.get("decision_change_action"))
    if action.get("next_query"):
        return {
            "query": str(action.get("next_query") or ""),
            "intent": str(action.get("next_intent") or action.get("missing_category") or ""),
            "source": "decision_change_action",
        }
    validation_queries = _first_mapping(mvp_radar.get("validation_queries"))
    next_query = validation_queries.get("next_query")
    if isinstance(next_query, Mapping) and next_query.get("query"):
        return {
            "query": str(next_query.get("query") or ""),
            "intent": str(next_query.get("intent") or ""),
            "source": "validation_queries",
        }
    missing = _first_mapping(mvp_radar.get("missing_evidence_by_category"))
    for category, details in missing.items():
        detail_map = _first_mapping(details)
        if detail_map.get("next_query"):
            return {
                "query": str(detail_map.get("next_query") or ""),
                "intent": str(detail_map.get("next_intent") or category),
                "source": "missing_evidence_by_category",
            }
    for item in _string_values(mvp_radar.get("next_validation")):
        return {"query": item, "intent": "operator_validation", "source": "legacy_next_validation"}
    return {}


def _render_validation_query_pack(mvp_radar: Mapping[str, object], summary: Mapping[str, object]) -> str:
    validation_queries = _first_mapping(mvp_radar.get("validation_queries"))
    queries_by_intent = _first_mapping(validation_queries.get("queries_by_intent"))
    next_query = str(summary.get("next_query") or "")
    next_intent = str(summary.get("next_intent") or "external_validation")
    lead = (
        f'<p><b>Next repeatable search:</b> <code>{_escape(next_query)}</code> '
        f'<span class="muted">({ _escape(next_intent) })</span></p>'
        if next_query
        else '<p><b>Next repeatable search:</b> Run Radar with fresh validation sources.</p>'
    )
    items = []
    for intent in ("search_demand", "manual_workarounds", "reddit_forum_complaints", "wtp_signals"):
        records = queries_by_intent.get(intent)
        if not isinstance(records, list) or not records:
            continue
        first = records[0]
        if not isinstance(first, Mapping):
            continue
        query = str(first.get("query") or "").strip()
        if query:
            items.append(f"<li>{_escape(intent)}: <code>{_escape(query)}</code></li>")
    query_list = f"<ul>{''.join(items[:4])}</ul>" if items else ""
    return "<h3>Validation Query Pack</h3>" + lead + query_list


def _render_matched_evidence(mvp_radar: Mapping[str, object]) -> str:
    matches = _object_list(mvp_radar.get("matched_external_evidence"))
    if not matches:
        return (
            "<h3>Matched Evidence By Source/Kind</h3>"
            "<p>No matched external validation evidence found. External research context is context only until it matches the selected candidate.</p>"
        )
    items = []
    for match in matches[:4]:
        source = str(match.get("source_type") or "unknown")
        kind = str(match.get("evidence_kind") or "unknown")
        query = str(match.get("query") or "no query")
        supports = "gating" if bool(match.get("supports_gate")) else "context only"
        url = str(match.get("source_url") or "")
        suffix = f" {_link(url, 'source')}" if url else ""
        items.append(
            f"<li><b>{_escape(source)} / {_escape(kind)}</b>: {_escape(supports)}; "
            f"query <code>{_escape(query)}</code>.{suffix}</li>"
        )
    return "<h3>Matched Evidence By Source/Kind</h3><ul class=\"evidence-list\">" + "".join(items) + "</ul>"


def _render_missing_evidence_checklist(mvp_radar: Mapping[str, object]) -> str:
    missing = _first_mapping(mvp_radar.get("missing_evidence_by_category"))
    items = []
    for category, details in list(missing.items())[:5]:
        detail_map = _first_mapping(details)
        reasons = _string_values(detail_map.get("missing_evidence"))
        reason = reasons[0] if reasons else str(detail_map.get("evidence_kind") or "missing evidence")
        query = str(detail_map.get("next_query") or "").strip()
        query_suffix = f" Next: <code>{_escape(query)}</code>" if query else ""
        items.append(f"<li><b>{_escape(category)}</b>: {_escape(reason)}.{query_suffix}</li>")
    if not items:
        return ""
    return '<ul class="missing-list">' + "".join(items) + "</ul>"


def _render_decision_change_action(
    mvp_radar: Mapping[str, object],
    summary: Mapping[str, object],
) -> str:
    action = _first_mapping(mvp_radar.get("decision_change_action"))
    action_text = str(action.get("next_validation_action") or "").strip()
    required = str(action.get("required_gate_change") or "").strip()
    context_rule = str(action.get("context_only_results_rule") or "").strip()
    next_query = str(summary.get("next_query") or "")
    if not action_text and next_query:
        action_text = f"Run `{next_query}` and attach only candidate-matched external evidence."
    if not action_text:
        action_text = "Run the validation query pack and attach candidate-matched external evidence."
    if not required:
        required = "Two independent matched decision-grade external source types before build/focused status."
    if not context_rule:
        context_rule = "Unmatched external research and market lens records remain context only."
    return (
        '<div class="mvp-action-panel">'
        f"<p>{_escape(action_text)}</p>"
        f"<p><b>Gate change required:</b> {_escape(required)}</p>"
        f'<p class="muted">{_escape(context_rule)}</p>'
        "</div>"
    )
