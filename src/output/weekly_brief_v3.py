"""Deterministic Weekly Brief V3 projection for PRM-16.

The module is a bounded projection layer: it does not read production
databases, run Radar/report generation, call providers, or write files. Callers
pass already-selected context snapshots and the renderer returns static HTML.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import escape
from typing import Any, Mapping


WEEKLY_BRIEF_V3_SCHEMA_VERSION = "weekly_brief_v3.v1"
WEEKLY_BRIEF_V3_VISUAL_RECEIPT_SCHEMA_VERSION = "weekly_brief_v3_visual_receipt.v1"

WEEKLY_BRIEF_V3_REQUIRED_VIEWPORTS = (
    {"id": "desktop_1440", "width": 1440, "height": 1000},
    {"id": "mobile_375", "width": 375, "height": 1000},
)

WEEKLY_BRIEF_V3_SECTIONS = (
    "main_change",
    "act_item",
    "study_item",
    "watch_ignore_item",
    "reaction_summary",
    "project_connection",
    "radar_card",
    "feedback_request",
)

GENERIC_FALLBACK_ACTION_PHRASES = (
    "review the sources",
    "review sources",
    "do more research",
    "look into this",
    "keep an eye on",
    "follow up later",
    "consider exploring",
    "explore this further",
    "investigate further",
    "stay tuned",
)

_BRIEF_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,95}$")


class WeeklyBriefV3ValidationError(ValueError):
    """Raised when a Weekly Brief V3 DTO or static render is invalid."""


def build_weekly_brief_v3(payload: Mapping[str, Any]) -> dict[str, object]:
    """Build a deterministic Weekly Brief V3 DTO from bounded context.

    Input keys intentionally mirror the PRM-16 contract: watch topics, reacted
    posts, questions, saved notes, active projects, repeated signals,
    experiments, feedback, and an optional Radar snapshot.
    """

    week_id = _clean_text(payload.get("week_id") or payload.get("week")) or "unknown-week"
    as_of = _clean_text(payload.get("as_of")) or _now_iso()
    context = _normalize_context(payload)

    main_change = _build_main_change(context)
    act_item = _build_act_item(context)
    study_item = _build_study_item(context)
    watch_ignore_item = _build_watch_ignore_item(context)
    reaction_summary = _build_reaction_summary(context)
    project_connection = _build_project_connection(context)
    radar_card = _build_radar_card(payload.get("radar"))
    feedback_request = _build_feedback_request(payload.get("feedback_request"), act_item=act_item)

    dependency_status = {
        "archive_search": _surface_status(payload, "archive_search_status", default="available"),
        "assistant_answers": _surface_status(payload, "assistant_answers_status", default="available"),
        "knowledge_library": _surface_status(payload, "knowledge_library_status", default="available"),
        "radar": str(radar_card["state"]),
    }
    non_radar_sections = (
        main_change,
        act_item,
        study_item,
        watch_ignore_item,
        reaction_summary,
        project_connection,
        feedback_request,
    )
    non_radar_status = (
        "available"
        if all(section.get("status") in {"available", "requested", "none"} for section in non_radar_sections)
        else "degraded"
    )
    source_refs = _unique_texts(
        ref
        for section in (
            main_change,
            act_item,
            study_item,
            watch_ignore_item,
            reaction_summary,
            project_connection,
            radar_card,
        )
        for ref in _text_list(section.get("source_refs"))
    )[:32]

    brief = {
        "schema_version": WEEKLY_BRIEF_V3_SCHEMA_VERSION,
        "artifact_type": "weekly_brief_v3",
        "brief_id": _brief_id(week_id),
        "week_id": week_id,
        "as_of": as_of,
        "main_change": main_change,
        "act_item": act_item,
        "study_item": study_item,
        "watch_ignore_item": watch_ignore_item,
        "reaction_summary": reaction_summary,
        "project_connection": project_connection,
        "radar_card": radar_card,
        "feedback_request": feedback_request,
        "dependency_status": dependency_status,
        "non_radar_status": non_radar_status,
        "legacy_surface_demotions": _legacy_surface_demotions(),
        "source_refs": source_refs,
        "privacy_boundary": {
            "raw_telegram_text_egress": False,
            "llm_generation": False,
            "live_radar_run": False,
            "production_db_write": False,
        },
        "visual_contract": {
            "schema_version": WEEKLY_BRIEF_V3_VISUAL_RECEIPT_SCHEMA_VERSION,
            "viewports": list(WEEKLY_BRIEF_V3_REQUIRED_VIEWPORTS),
            "checks": {
                "static_html_only": True,
                "responsive_grid": True,
                "mobile_breakpoint": True,
                "overflow_wrap": True,
            },
        },
    }
    return validate_weekly_brief_v3(brief)


def validate_weekly_brief_v3(brief: Mapping[str, Any]) -> dict[str, object]:
    errors: list[str] = []
    if brief.get("schema_version") != WEEKLY_BRIEF_V3_SCHEMA_VERSION:
        errors.append("schema_version is invalid")
    if brief.get("artifact_type") != "weekly_brief_v3":
        errors.append("artifact_type must be weekly_brief_v3")
    brief_id = _clean_text(brief.get("brief_id"))
    if not brief_id or not _BRIEF_ID_RE.fullmatch(brief_id):
        errors.append("brief_id is invalid")

    for section in WEEKLY_BRIEF_V3_SECTIONS:
        value = brief.get(section)
        if not isinstance(value, Mapping):
            errors.append(f"{section} must be an object")
            continue
        if not _clean_text(value.get("title")):
            errors.append(f"{section}.title is required")
        if not _clean_text(value.get("body")):
            errors.append(f"{section}.body is required")
        refs = value.get("source_refs")
        if not isinstance(refs, list):
            errors.append(f"{section}.source_refs must be a list")
        if value.get("status") == "available" and section != "feedback_request" and not refs:
            errors.append(f"{section}.source_refs are required when available")

    act_item = brief.get("act_item")
    if isinstance(act_item, Mapping) and act_item.get("mode") != "ACT":
        errors.append("act_item.mode must be ACT")
    study_item = brief.get("study_item")
    if isinstance(study_item, Mapping) and study_item.get("mode") != "STUDY":
        errors.append("study_item.mode must be STUDY")
    watch_ignore_item = brief.get("watch_ignore_item")
    if isinstance(watch_ignore_item, Mapping) and watch_ignore_item.get("mode") not in {"WATCH", "IGNORE"}:
        errors.append("watch_ignore_item.mode must be WATCH or IGNORE")

    dependency_status = brief.get("dependency_status")
    if not isinstance(dependency_status, Mapping):
        errors.append("dependency_status must be an object")
    else:
        for surface in ("archive_search", "assistant_answers", "knowledge_library", "radar"):
            if not _clean_text(dependency_status.get(surface)):
                errors.append(f"dependency_status.{surface} is required")

    legacy = brief.get("legacy_surface_demotions")
    if not isinstance(legacy, list):
        errors.append("legacy_surface_demotions must be a list")
    else:
        demoted = {entry.get("surface") for entry in legacy if isinstance(entry, Mapping)}
        if {"weekly_brief_v1", "knowledge_atlas"} - demoted:
            errors.append("legacy_surface_demotions must demote weekly_brief_v1 and knowledge_atlas")

    privacy = brief.get("privacy_boundary")
    if not isinstance(privacy, Mapping):
        errors.append("privacy_boundary must be an object")
    elif any(bool(privacy.get(key)) for key in ("raw_telegram_text_egress", "llm_generation", "live_radar_run")):
        errors.append("privacy_boundary must not enable raw egress, LLM generation, or live Radar")

    visual_contract = brief.get("visual_contract")
    if not isinstance(visual_contract, Mapping):
        errors.append("visual_contract must be an object")
    elif visual_contract.get("viewports") != list(WEEKLY_BRIEF_V3_REQUIRED_VIEWPORTS):
        errors.append("visual_contract viewports must include desktop_1440 and mobile_375")

    try:
        validate_weekly_brief_v3_text_has_no_generic_fallbacks(brief)
    except WeeklyBriefV3ValidationError as exc:
        errors.append(str(exc))

    if errors:
        raise WeeklyBriefV3ValidationError("; ".join(errors))
    return dict(brief)


def validate_weekly_brief_v3_text_has_no_generic_fallbacks(value: object) -> dict[str, object]:
    text = _flatten_text(value).lower()
    hits = [phrase for phrase in GENERIC_FALLBACK_ACTION_PHRASES if phrase in text]
    if hits:
        raise WeeklyBriefV3ValidationError(
            "generic fallback action phrase found: " + ", ".join(sorted(hits))
        )
    return {"status": "passed", "checked_phrases": list(GENERIC_FALLBACK_ACTION_PHRASES)}


def render_weekly_brief_v3_html(brief: Mapping[str, Any]) -> str:
    validated = validate_weekly_brief_v3(brief)
    radar = validated["radar_card"]
    radar_html = _render_section("radar_card", radar) if radar.get("included") else ""
    legacy_html = "".join(
        f"<li><strong>{escape(str(entry['label']))}</strong>: {escape(str(entry['reader_role']))}</li>"
        for entry in validated["legacy_surface_demotions"]
        if isinstance(entry, Mapping)
    )
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src 'none'; script-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>{escape(str(validated["week_id"]))} - Weekly Brief V3</title>
<style>{_stylesheet()}</style>
</head>
<body>
<main class="wb3-page" data-surface="weekly_brief_v3">
  <header class="wb3-hero">
    <p class="wb3-eyebrow">Weekly Brief V3</p>
    <h1>{escape(str(validated["week_id"]))}</h1>
    <p>{escape(str(validated["main_change"]["body"]))}</p>
  </header>
  <section class="wb3-main" data-section="main_change">
    <p class="wb3-eyebrow">Main Change</p>
    <h2>{escape(str(validated["main_change"]["title"]))}</h2>
    <p>{escape(str(validated["main_change"]["body"]))}</p>
    {_render_sources(validated["main_change"])}
  </section>
  <section class="wb3-grid" aria-label="Decision items">
    {_render_section("act_item", validated["act_item"])}
    {_render_section("study_item", validated["study_item"])}
    {_render_section("watch_ignore_item", validated["watch_ignore_item"])}
  </section>
  <section class="wb3-grid" aria-label="Context items">
    {_render_section("reaction_summary", validated["reaction_summary"])}
    {_render_section("project_connection", validated["project_connection"])}
    {radar_html}
    {_render_section("feedback_request", validated["feedback_request"])}
  </section>
  <section class="wb3-status" data-section="surface_status">
    <p class="wb3-eyebrow">Surface Status</p>
    <h2>Legacy Surfaces Are Demoted</h2>
    <ul>{legacy_html}</ul>
  </section>
</main>
</body>
</html>
"""
    validate_weekly_brief_v3_visual_contract(html_doc)
    return html_doc


def validate_weekly_brief_v3_visual_contract(html_text: str) -> dict[str, object]:
    lower = html_text.lower()
    checks = {
        "viewport_meta": '<meta name="viewport"' in lower,
        "no_script": "<script" not in lower,
        "no_external_styles": "<link" not in lower and "@import" not in lower,
        "responsive_grid": "repeat(auto-fit" in lower,
        "mobile_breakpoint": "@media (max-width: 760px)" in lower,
        "overflow_wrap": "overflow-wrap: anywhere" in lower,
        "surface_marker": 'data-surface="weekly_brief_v3"' in lower,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise WeeklyBriefV3ValidationError("visual contract failed: " + ", ".join(failures))
    return {
        "schema_version": WEEKLY_BRIEF_V3_VISUAL_RECEIPT_SCHEMA_VERSION,
        "viewports": list(WEEKLY_BRIEF_V3_REQUIRED_VIEWPORTS),
        "checks": checks,
        "status": "passed",
        "browser_snapshot_status": "not_run_playwright_unavailable",
    }


def _normalize_context(payload: Mapping[str, Any]) -> dict[str, list[dict[str, object]]]:
    keys = (
        "watch_topics",
        "reacted_posts",
        "questions",
        "saved_notes",
        "active_projects",
        "repeated_signals",
        "experiments",
        "feedback",
    )
    return {key: [_normalize_entry(item, category=key) for item in _mapping_list(payload.get(key))] for key in keys}


def _build_main_change(context: Mapping[str, list[dict[str, object]]]) -> dict[str, object]:
    candidates = (
        context["repeated_signals"]
        + context["watch_topics"]
        + context["reacted_posts"]
        + context["questions"]
        + context["saved_notes"]
    )
    entry = _first_source_backed(candidates) or _first(candidates)
    if entry:
        delta = _clean_text(entry.get("delta") or entry.get("trend") or entry.get("change"))
        body = _clean_text(entry.get("body"))
        if delta and body:
            body = f"{body} Change marker: {delta}."
        elif delta:
            body = f"Change marker: {delta}."
        return _section(
            mode="CHANGE",
            title=_clean_text(entry.get("title")) or "Source-backed weekly change",
            body=body or "A supplied signal changed enough to become the main weekly change.",
            source_refs=_text_list(entry.get("source_refs")),
            status="available" if _text_list(entry.get("source_refs")) else "insufficient_evidence",
            evidence_type=str(entry.get("category") or "signal"),
        )
    return _section(
        mode="CHANGE",
        title="No source-backed change selected",
        body="No supplied watch topic, reaction, question, note, or repeated signal carried enough evidence for a main change.",
        status="insufficient_evidence",
    )


def _build_act_item(context: Mapping[str, list[dict[str, object]]]) -> dict[str, object]:
    candidates = context["active_projects"] + context["experiments"] + context["reacted_posts"]
    for entry in candidates:
        action = _clean_text(entry.get("next_action") or entry.get("action") or entry.get("recommendation"))
        if action:
            return _section(
                mode="ACT",
                title=action,
                body=_clean_text(entry.get("body"))
                or f"Apply this to {_clean_text(entry.get('project')) or _clean_text(entry.get('title'))}.",
                source_refs=_text_list(entry.get("source_refs")),
                status="available" if _text_list(entry.get("source_refs")) else "insufficient_evidence",
                project=_clean_text(entry.get("project")),
                evidence_type=str(entry.get("category") or "project"),
            )
    return _section(
        mode="ACT",
        title="No source-backed action selected",
        body="No supplied project, experiment, or reaction contained a concrete next action with evidence.",
        status="insufficient_evidence",
    )


def _build_study_item(context: Mapping[str, list[dict[str, object]]]) -> dict[str, object]:
    candidates = context["questions"] + context["saved_notes"] + context["watch_topics"]
    for entry in candidates:
        study = _clean_text(entry.get("study_prompt") or entry.get("question") or entry.get("next_study"))
        if study or entry:
            title = study or _clean_text(entry.get("title")) or "Study supplied evidence"
            body = _clean_text(entry.get("body")) or "Use this evidence to clarify an open question before saving a stronger memory."
            return _section(
                mode="STUDY",
                title=title,
                body=body,
                source_refs=_text_list(entry.get("source_refs")),
                status="available" if _text_list(entry.get("source_refs")) else "insufficient_evidence",
                evidence_type=str(entry.get("category") or "question"),
            )
    return _section(
        mode="STUDY",
        title="No source-backed study item selected",
        body="No supplied question, note, or watch topic contained enough evidence for a study item.",
        status="insufficient_evidence",
    )


def _build_watch_ignore_item(context: Mapping[str, list[dict[str, object]]]) -> dict[str, object]:
    candidates = context["watch_topics"] + context["repeated_signals"] + context["feedback"]
    entry = _first_source_backed(candidates) or _first(candidates)
    if entry:
        raw_mode = _clean_text(entry.get("mode") or entry.get("stance") or entry.get("decision")).lower()
        mode = "IGNORE" if raw_mode in {"ignore", "reject", "rejected", "drop"} else "WATCH"
        title = _clean_text(entry.get("title")) or f"{mode.title()} supplied signal"
        body = _clean_text(entry.get("body")) or "Track this only if new evidence changes its strength or project relevance."
        return _section(
            mode=mode,
            title=title,
            body=body,
            source_refs=_text_list(entry.get("source_refs")),
            status="available" if _text_list(entry.get("source_refs")) else "insufficient_evidence",
            evidence_type=str(entry.get("category") or "watch_topic"),
        )
    return _section(
        mode="IGNORE",
        title="No watch item selected",
        body="No supplied watch topic, repeated signal, or feedback item carried enough evidence to track this week.",
        status="insufficient_evidence",
    )


def _build_reaction_summary(context: Mapping[str, list[dict[str, object]]]) -> dict[str, object]:
    reacted = context["reacted_posts"]
    feedback = context["feedback"]
    counts: dict[str, int] = {}
    refs: list[str] = []
    for entry in reacted + feedback:
        label = _clean_text(entry.get("reaction") or entry.get("feedback") or entry.get("label")) or "unlabeled"
        counts[label] = counts.get(label, 0) + 1
        refs.extend(_text_list(entry.get("source_refs")))
    total = sum(counts.values())
    if total:
        summary = ", ".join(f"{label}={count}" for label, count in sorted(counts.items()))
        return _section(
            mode="REACTIONS",
            title=f"{total} reaction or feedback events processed",
            body=f"Reaction summary: {summary}.",
            source_refs=_unique_texts(refs),
            status="available" if refs else "insufficient_evidence",
            total=total,
            counts=counts,
        )
    return _section(
        mode="REACTIONS",
        title="No reactions processed",
        body="No reacted posts or feedback events were supplied for this V3 projection.",
        status="none",
        total=0,
        counts={},
    )


def _build_project_connection(context: Mapping[str, list[dict[str, object]]]) -> dict[str, object]:
    projects = context["active_projects"]
    entry = _first_source_backed(projects) or _first(projects)
    if entry:
        project = _clean_text(entry.get("project") or entry.get("title")) or "Active project"
        rationale = _clean_text(entry.get("rationale") or entry.get("body"))
        body = rationale or "A supplied active project has a source-backed connection to this week's evidence."
        return _section(
            mode="PROJECT",
            title=f"Project: {project}",
            body=body,
            source_refs=_text_list(entry.get("source_refs")),
            status="available" if _text_list(entry.get("source_refs")) else "insufficient_evidence",
            project=project,
        )
    return _section(
        mode="PROJECT",
        title="No active project connection supplied",
        body="No active project matched the supplied weekly context, so the brief records an honest zero.",
        status="none",
    )


def _build_radar_card(raw: object) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        return _section(
            mode="RADAR",
            title="Radar not included",
            body="No Radar snapshot was supplied for this bounded Weekly Brief V3 projection.",
            status="not_included",
            state="not_included",
            included=False,
        )
    state = _clean_text(raw.get("state") or raw.get("status")) or "available"
    error = _clean_text(raw.get("error") or raw.get("failure") or raw.get("message"))
    source_refs = _text_list(raw.get("source_refs") or raw.get("source_urls"))
    if state.lower() in {"failed", "error", "unavailable"} or error:
        return _section(
            mode="RADAR",
            title="Radar unavailable",
            body=f"Radar failed locally: {error or state}. Non-Radar brief sections remain valid.",
            source_refs=source_refs,
            status="failed",
            state="failed",
            included=True,
        )
    return _section(
        mode="RADAR",
        title=_clean_text(raw.get("title")) or "Radar candidate",
        body=_clean_text(raw.get("body") or raw.get("summary")) or "Radar supplied a candidate snapshot.",
        source_refs=source_refs,
        status="available" if source_refs else "insufficient_evidence",
        state="available",
        included=True,
        decision=_clean_text(raw.get("decision")),
    )


def _build_feedback_request(raw: object, *, act_item: Mapping[str, object]) -> dict[str, object]:
    if isinstance(raw, Mapping):
        title = _clean_text(raw.get("title") or raw.get("question")) or "Brief feedback requested"
        body = _clean_text(raw.get("body") or raw.get("prompt")) or "Mark the ACT item useful, weak, noisy, or decision-impacting."
    else:
        action_title = _clean_text(act_item.get("title")) or "this ACT item"
        title = "Brief feedback requested"
        body = f"Mark whether '{action_title}' was useful, weak, noisy, or decision-impacting."
    return _section(mode="FEEDBACK", title=title, body=body, source_refs=[], status="requested")


def _section(
    *,
    mode: str,
    title: str,
    body: str,
    source_refs: object | None = None,
    status: str = "available",
    **extra: object,
) -> dict[str, object]:
    section: dict[str, object] = {
        "mode": mode,
        "status": status,
        "title": _clean_text(title),
        "body": _clean_text(body),
        "source_refs": _text_list(source_refs),
    }
    for key, value in extra.items():
        if value is not None and value != "":
            section[key] = value
    return section


def _normalize_entry(raw: Mapping[str, Any], *, category: str) -> dict[str, object]:
    title = _clean_text(raw.get("title") or raw.get("name") or raw.get("topic") or raw.get("question"))
    body = _clean_text(raw.get("body") or raw.get("summary") or raw.get("text") or raw.get("rationale"))
    source_refs = _text_list(raw.get("source_refs") or raw.get("source_urls") or raw.get("ref") or raw.get("source_url"))
    value: dict[str, object] = {
        "category": category,
        "title": title,
        "body": body,
        "source_refs": source_refs,
        "observed_at": _clean_text(raw.get("observed_at") or raw.get("created_at") or raw.get("posted_at")),
        "project": _clean_text(raw.get("project") or raw.get("project_name")),
        "reaction": _clean_text(raw.get("reaction")),
        "feedback": _clean_text(raw.get("feedback")),
        "label": _clean_text(raw.get("label")),
        "mode": _clean_text(raw.get("mode")),
        "stance": _clean_text(raw.get("stance")),
        "decision": _clean_text(raw.get("decision")),
        "delta": _clean_text(raw.get("delta")),
        "trend": _clean_text(raw.get("trend")),
        "change": _clean_text(raw.get("change")),
        "next_action": _clean_text(raw.get("next_action")),
        "action": _clean_text(raw.get("action")),
        "recommendation": _clean_text(raw.get("recommendation")),
        "study_prompt": _clean_text(raw.get("study_prompt")),
        "next_study": _clean_text(raw.get("next_study")),
        "question": _clean_text(raw.get("question")),
        "rationale": _clean_text(raw.get("rationale")),
    }
    return value


def _legacy_surface_demotions() -> list[dict[str, object]]:
    return [
        {
            "surface": "weekly_brief_v1",
            "label": "Weekly Brief V1",
            "status": "demoted",
            "reader_role": "compatibility artifact only; not the PRM decision surface",
        },
        {
            "surface": "knowledge_atlas",
            "label": "Knowledge Atlas",
            "status": "demoted",
            "reader_role": "internal audit/debug surface; Knowledge Library topic pages are primary",
        },
    ]


def _render_section(section_id: str, section: Mapping[str, object]) -> str:
    mode = escape(str(section.get("mode") or section_id))
    return (
        f'<section class="wb3-card" data-section="{escape(section_id)}">'
        f'<p class="wb3-mode">{mode}</p>'
        f'<h2>{escape(str(section["title"]))}</h2>'
        f'<p>{escape(str(section["body"]))}</p>'
        f"{_render_sources(section)}"
        "</section>"
    )


def _render_sources(section: Mapping[str, object]) -> str:
    refs = _text_list(section.get("source_refs"))
    if not refs:
        return '<p class="wb3-sources">Sources: none supplied for this section</p>'
    links = ", ".join(escape(ref) for ref in refs[:6])
    return f'<p class="wb3-sources">Sources: {links}</p>'


def _stylesheet() -> str:
    return """
:root {
  color-scheme: light;
  --bg: #f7f7f4;
  --ink: #202124;
  --muted: #5f6368;
  --line: #d8d8d0;
  --panel: #ffffff;
  --accent: #146c5f;
  --accent-2: #8f4f24;
}
* { box-sizing: border-box; }
html { background: var(--bg); }
body {
  margin: 0;
  color: var(--ink);
  background: var(--bg);
  font: 16px/1.55 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.wb3-page {
  width: min(1120px, calc(100% - 32px));
  margin: 0 auto;
  padding: 28px 0 40px;
  overflow-wrap: anywhere;
}
.wb3-hero, .wb3-main, .wb3-status {
  border-bottom: 1px solid var(--line);
  padding: 20px 0 24px;
}
.wb3-hero h1 {
  margin: 0 0 10px;
  font-size: 42px;
  line-height: 1.08;
  font-weight: 760;
  letter-spacing: 0;
}
.wb3-hero p, .wb3-main p, .wb3-card p, .wb3-status p {
  max-width: 72ch;
}
.wb3-eyebrow, .wb3-mode {
  margin: 0 0 8px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}
.wb3-main h2, .wb3-status h2, .wb3-card h2 {
  margin: 0 0 10px;
  font-size: 21px;
  line-height: 1.22;
  letter-spacing: 0;
}
.wb3-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
  margin: 16px 0;
}
.wb3-card {
  min-height: 190px;
  padding: 16px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.wb3-card:nth-child(2n) {
  border-top-color: var(--accent-2);
}
.wb3-sources {
  margin-top: 14px;
  color: var(--muted);
  font-size: 13px;
}
.wb3-status ul {
  margin: 10px 0 0;
  padding-left: 20px;
}
@media (max-width: 760px) {
  .wb3-page {
    width: min(100% - 20px, 680px);
    padding-top: 18px;
  }
  .wb3-hero h1 {
    font-size: 32px;
  }
  .wb3-grid {
    grid-template-columns: 1fr;
  }
  .wb3-card {
    min-height: 0;
  }
}
"""


def _mapping_list(raw: object) -> list[Mapping[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return [item for item in raw if isinstance(item, Mapping)]
    return []


def _first(values: list[dict[str, object]]) -> dict[str, object] | None:
    return values[0] if values else None


def _first_source_backed(values: list[dict[str, object]]) -> dict[str, object] | None:
    for value in values:
        if _text_list(value.get("source_refs")):
            return value
    return None


def _surface_status(payload: Mapping[str, Any], key: str, *, default: str) -> str:
    value = _clean_text(payload.get(key))
    return value or default


def _brief_id(week_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._:-]+", "-", week_id.strip()).strip("-")
    return slug[:96] or "unknown-week"


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _text_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [_clean_text(raw)] if _clean_text(raw) else []
    if isinstance(raw, (list, tuple, set)):
        return [_clean_text(item) for item in raw if _clean_text(item)]
    return [_clean_text(raw)] if _clean_text(raw) else []


def _unique_texts(values: object) -> list[str]:
    if values is None:
        iterable: list[object] = []
    elif isinstance(values, str):
        iterable = [values]
    else:
        try:
            iterable = list(values)  # type: ignore[arg-type]
        except TypeError:
            iterable = [values]
    seen: set[str] = set()
    result: list[str] = []
    for value in iterable:
        text = _clean_text(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _flatten_text(value: object) -> str:
    if isinstance(value, Mapping):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_text(item) for item in value)
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
