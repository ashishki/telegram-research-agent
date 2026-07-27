"""Deterministic Knowledge Library topic-page projection for PRM-13.

The module does not read production databases, run retrieval, call providers, or
write files. Callers pass bounded topic evidence and confirmed memory-event
snapshots; the renderer returns a static HTML page and validation receipt.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import escape
from typing import Any, Mapping


KNOWLEDGE_LIBRARY_TOPIC_SCHEMA_VERSION = "knowledge_library_topic_page.v1"
KNOWLEDGE_LIBRARY_VISUAL_RECEIPT_SCHEMA_VERSION = "knowledge_library_visual_receipt.v1"

TOPIC_SECTIONS = (
    "claims",
    "cases",
    "tools",
    "practices",
    "contradictions",
    "project_links",
    "saved_notes",
    "decisions",
    "experiments",
    "open_questions",
)

REQUIRED_VIEWPORTS = (
    {"id": "desktop_1440", "width": 1440, "height": 1000},
    {"id": "mobile_375", "width": 375, "height": 1000},
)

_TOPIC_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
_MEMORY_SECTIONS = {
    "knowledge_note": "saved_notes",
    "watch_topic": "saved_notes",
    "decision": "decisions",
    "experiment": "experiments",
}


class KnowledgeLibraryValidationError(ValueError):
    """Raised when a topic-page DTO cannot satisfy the PRM-13 contract."""


def build_knowledge_library_topic_page(payload: Mapping[str, Any]) -> dict[str, object]:
    topic = _normalize_topic(payload.get("topic"))
    as_of = _clean_text(payload.get("as_of")) or _now_iso()
    section_entries: dict[str, list[dict[str, object]]] = {
        section: [_normalize_entry(item, section=section) for item in _mapping_list(payload.get(section))]
        for section in TOPIC_SECTIONS
    }
    for event in _mapping_list(payload.get("memory_events")):
        memory_entry = _entry_from_memory_event(event)
        if memory_entry is None:
            continue
        section_entries[str(memory_entry.pop("_section"))].append(memory_entry)

    original_sources = _normalize_sources(payload.get("original_sources"))
    archive_hits = [_normalize_archive_hit(item) for item in _mapping_list(payload.get("archive_hits"))]
    for item in archive_hits:
        original_sources.append(item)
    original_sources = _unique_sources(original_sources)

    source_refs = _source_refs_from_sections(section_entries)
    source_refs.extend(source["ref"] for source in original_sources if source.get("ref"))
    source_refs = _unique_texts(source_refs)[:24]

    current_understanding = _clean_text(payload.get("current_understanding"))
    if not current_understanding:
        current_understanding = _derive_current_understanding(section_entries, topic)

    page = {
        "schema_version": KNOWLEDGE_LIBRARY_TOPIC_SCHEMA_VERSION,
        "surface": "knowledge_library_topic_page",
        "topic": topic,
        "as_of": as_of,
        "current_understanding": current_understanding,
        "changes_30d": _build_change_window(30, as_of=as_of, sections=section_entries, sources=original_sources),
        "changes_90d": _build_change_window(90, as_of=as_of, sections=section_entries, sources=original_sources),
        "sections": section_entries,
        "original_sources": original_sources,
        "source_refs": source_refs,
        "open_question_count": len(section_entries["open_questions"]),
        "visual_contract": {
            "schema_version": KNOWLEDGE_LIBRARY_VISUAL_RECEIPT_SCHEMA_VERSION,
            "viewports": list(REQUIRED_VIEWPORTS),
            "checks": {
                "static_html_only": True,
                "responsive_grid": True,
                "mobile_breakpoint": True,
                "overflow_wrap": True,
            },
        },
    }
    return validate_knowledge_library_topic_page(page)


def validate_knowledge_library_topic_page(page: Mapping[str, Any]) -> dict[str, object]:
    errors: list[str] = []
    if page.get("schema_version") != KNOWLEDGE_LIBRARY_TOPIC_SCHEMA_VERSION:
        errors.append("schema_version is invalid")
    topic = page.get("topic")
    if not isinstance(topic, Mapping):
        errors.append("topic must be an object")
    else:
        topic_id = _clean_text(topic.get("topic_id"))
        if not topic_id or not _TOPIC_ID_RE.fullmatch(topic_id):
            errors.append("topic.topic_id is invalid")
        if not _clean_text(topic.get("title")):
            errors.append("topic.title is required")
        if topic.get("source") not in {"query", "watch_topic"}:
            errors.append("topic.source must be query or watch_topic")
    if not _clean_text(page.get("current_understanding")):
        errors.append("current_understanding is required")
    sections = page.get("sections")
    if not isinstance(sections, Mapping):
        errors.append("sections must be an object")
    else:
        missing = [section for section in TOPIC_SECTIONS if section not in sections]
        if missing:
            errors.append("missing sections: " + ", ".join(missing))
        for section in TOPIC_SECTIONS:
            entries = sections.get(section)
            if not isinstance(entries, list):
                errors.append(f"sections.{section} must be a list")
                continue
            for index, entry in enumerate(entries):
                if not isinstance(entry, Mapping):
                    errors.append(f"sections.{section}[{index}] must be an object")
                    continue
                if not _clean_text(entry.get("title")):
                    errors.append(f"sections.{section}[{index}].title is required")
                refs = entry.get("source_refs")
                if not isinstance(refs, list):
                    errors.append(f"sections.{section}[{index}].source_refs must be a list")
    for field in ("changes_30d", "changes_90d"):
        if not isinstance(page.get(field), Mapping):
            errors.append(f"{field} must be an object")
    original_sources = page.get("original_sources")
    if not isinstance(original_sources, list):
        errors.append("original_sources must be a list")
    elif not original_sources:
        errors.append("original_sources must not be empty")
    visual_contract = page.get("visual_contract")
    if not isinstance(visual_contract, Mapping):
        errors.append("visual_contract must be an object")
    elif visual_contract.get("viewports") != list(REQUIRED_VIEWPORTS):
        errors.append("visual_contract viewports must include desktop_1440 and mobile_375")
    if errors:
        raise KnowledgeLibraryValidationError("; ".join(errors))
    return dict(page)


def render_knowledge_library_topic_page_html(page: Mapping[str, Any]) -> str:
    validated = validate_knowledge_library_topic_page(page)
    topic = validated["topic"]
    sections = validated["sections"]
    section_nav = "".join(
        f'<a href="#{escape(section)}">{escape(_section_title(section))}</a>'
        for section in TOPIC_SECTIONS
    )
    section_html = "\n".join(
        _render_section(section, sections[section]) for section in TOPIC_SECTIONS
    )
    source_html = "\n".join(_render_source(source) for source in validated["original_sources"])
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src 'none'; script-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>{escape(str(topic["title"]))} - Knowledge Library</title>
<style>{_stylesheet()}</style>
</head>
<body>
<main class="kl-page" data-surface="knowledge_library_topic_page">
  <header class="kl-hero">
    <p class="kl-eyebrow">Knowledge Library Topic</p>
    <h1>{escape(str(topic["title"]))}</h1>
    <p class="kl-query">{escape(str(topic.get("query") or ""))}</p>
    <p class="kl-understanding">{escape(str(validated["current_understanding"]))}</p>
  </header>
  <nav class="kl-nav" aria-label="Topic sections">{section_nav}</nav>
  <section class="kl-window-grid" aria-label="Change windows">
    {_render_change_window("30 Day Changes", validated["changes_30d"])}
    {_render_change_window("90 Day Changes", validated["changes_90d"])}
  </section>
  {section_html}
  <section class="kl-section" id="original-sources">
    <div class="kl-section-head">
      <p class="kl-eyebrow">Provenance</p>
      <h2>Original Sources</h2>
    </div>
    <ol class="kl-source-list">{source_html}</ol>
  </section>
</main>
</body>
</html>
"""
    validate_knowledge_library_visual_contract(html_doc)
    return html_doc


def validate_knowledge_library_visual_contract(html_text: str) -> dict[str, object]:
    lower = html_text.lower()
    checks = {
        "viewport_meta": '<meta name="viewport"' in lower,
        "no_script": "<script" not in lower,
        "no_external_styles": "<link" not in lower and "@import" not in lower,
        "responsive_grid": "repeat(auto-fit" in lower,
        "mobile_breakpoint": "@media (max-width: 760px)" in lower,
        "overflow_wrap": "overflow-wrap: anywhere" in lower,
        "surface_marker": 'data-surface="knowledge_library_topic_page"' in lower,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise KnowledgeLibraryValidationError("visual contract failed: " + ", ".join(failures))
    return {
        "schema_version": KNOWLEDGE_LIBRARY_VISUAL_RECEIPT_SCHEMA_VERSION,
        "viewports": list(REQUIRED_VIEWPORTS),
        "checks": checks,
        "status": "passed",
        "browser_snapshot_status": "not_run_playwright_unavailable",
    }


def _normalize_topic(raw: object) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise KnowledgeLibraryValidationError("topic is required")
    title = _required_text(raw.get("title"), "topic.title")
    topic_id = _clean_text(raw.get("topic_id")) or _slug(title)
    query = _clean_text(raw.get("query")) or title
    source = _clean_text(raw.get("source")) or "query"
    return {
        "topic_id": topic_id,
        "title": title,
        "query": query,
        "source": source,
        "watch_topic_id": _clean_text(raw.get("watch_topic_id")),
    }


def _normalize_entry(raw: Mapping[str, Any], *, section: str) -> dict[str, object]:
    title = _required_text(raw.get("title") or raw.get("claim") or raw.get("question") or raw.get("name"), f"{section}.title")
    body = _clean_text(raw.get("body") or raw.get("summary") or raw.get("text") or raw.get("rationale"))
    entry = {
        "id": _clean_text(raw.get("id")) or f"{section}:{_slug(title)}",
        "title": title,
        "body": body,
        "status": _clean_text(raw.get("status")) or "active",
        "observed_at": _clean_text(raw.get("observed_at") or raw.get("created_at") or raw.get("posted_at")),
        "source_refs": _text_list(raw.get("source_refs") or raw.get("source_urls")),
        "tags": _text_list(raw.get("tags")),
    }
    for optional in ("confidence", "project_name", "tool_name", "practice_type"):
        value = raw.get(optional)
        if value is not None:
            entry[optional] = value
    return entry


def _entry_from_memory_event(event: Mapping[str, Any]) -> dict[str, object] | None:
    object_type = _clean_text(event.get("object_type"))
    section = _MEMORY_SECTIONS.get(object_type)
    if not section:
        return None
    event_type = _clean_text(event.get("event_type")) or "created"
    if event_type not in {"created", "edited", "rolled_back"}:
        return None
    source_refs = _loads_json_list(event.get("source_refs_json"))
    return {
        "_section": section,
        "id": f"memory-event:{event.get('id')}",
        "title": _required_text(event.get("title"), "memory_event.title"),
        "body": _clean_text(event.get("body") or event.get("rationale")),
        "status": event_type,
        "observed_at": _clean_text(event.get("created_at")),
        "source_refs": source_refs,
        "tags": [object_type],
        "memory_id": _clean_text(event.get("memory_id")),
    }


def _normalize_sources(raw: object) -> list[dict[str, object]]:
    return [_normalize_source(item) for item in _mapping_list(raw)]


def _normalize_archive_hit(raw: Mapping[str, Any]) -> dict[str, object]:
    source_url = _clean_text(raw.get("source_url") or raw.get("message_url"))
    label = _clean_text(raw.get("title")) or _clean_text(raw.get("channel_username")) or "Telegram source"
    return {
        "ref": source_url or _clean_text(raw.get("archive_document_id")) or label,
        "label": label,
        "kind": "telegram_archive",
        "observed_at": _clean_text(raw.get("posted_at")),
    }


def _normalize_source(raw: Mapping[str, Any]) -> dict[str, object]:
    ref = _required_text(raw.get("ref") or raw.get("url") or raw.get("source_url"), "source.ref")
    return {
        "ref": ref,
        "label": _clean_text(raw.get("label")) or ref,
        "kind": _clean_text(raw.get("kind")) or "source",
        "observed_at": _clean_text(raw.get("observed_at") or raw.get("posted_at")),
    }


def _source_refs_from_sections(sections: Mapping[str, list[dict[str, object]]]) -> list[str]:
    refs: list[str] = []
    for entries in sections.values():
        for entry in entries:
            refs.extend(str(ref) for ref in entry.get("source_refs") or [] if str(ref).strip())
    return refs


def _build_change_window(
    days: int,
    *,
    as_of: str,
    sections: Mapping[str, list[dict[str, object]]],
    sources: list[dict[str, object]],
) -> dict[str, object]:
    as_of_dt = _parse_datetime(as_of)
    dated_entries: list[dict[str, object]] = []
    for section, entries in sections.items():
        for entry in entries:
            observed_at = _clean_text(entry.get("observed_at"))
            if not observed_at:
                continue
            observed_dt = _parse_datetime(observed_at)
            if observed_dt is None or as_of_dt is None:
                continue
            age_days = (as_of_dt - observed_dt).days
            if 0 <= age_days <= days:
                dated_entries.append({"section": section, "title": entry["title"], "observed_at": observed_at})
    refs = []
    for source in sources:
        observed_dt = _parse_datetime(_clean_text(source.get("observed_at")))
        if observed_dt is None or as_of_dt is None:
            continue
        age_days = (as_of_dt - observed_dt).days
        if 0 <= age_days <= days:
            refs.append(str(source["ref"]))
    return {
        "window_days": days,
        "status": "available" if dated_entries else "empty",
        "new_evidence_count": len(dated_entries),
        "summary": (
            f"{len(dated_entries)} dated items changed in the last {days} days."
            if dated_entries
            else f"No dated topic changes were supplied for the last {days} days."
        ),
        "items": dated_entries[:12],
        "source_refs": _unique_texts(refs)[:12],
    }


def _derive_current_understanding(sections: Mapping[str, list[dict[str, object]]], topic: Mapping[str, object]) -> str:
    claims = sections.get("claims") or []
    if claims:
        first = claims[0]
        body = _clean_text(first.get("body"))
        return body or str(first["title"])
    return f"{topic['title']} is tracked as a Knowledge Library topic, but the supplied evidence is still thin."


def _render_section(section: str, entries: list[Mapping[str, Any]]) -> str:
    cards = "\n".join(_render_entry(entry) for entry in entries)
    if not cards:
        cards = '<p class="kl-empty">No confirmed items supplied for this section.</p>'
    return f"""<section class="kl-section" id="{escape(section)}" data-section="{escape(section)}">
  <div class="kl-section-head">
    <p class="kl-eyebrow">{escape(section.replace("_", " ").title())}</p>
    <h2>{escape(_section_title(section))}</h2>
  </div>
  <div class="kl-card-grid">{cards}</div>
</section>"""


def _render_entry(entry: Mapping[str, Any]) -> str:
    refs = " ".join(f"<span>{escape(str(ref))}</span>" for ref in entry.get("source_refs") or [])
    tags = " ".join(f"<span>{escape(str(tag))}</span>" for tag in entry.get("tags") or [])
    body = _clean_text(entry.get("body"))
    return f"""<article class="kl-card">
  <h3>{escape(str(entry["title"]))}</h3>
  <p>{escape(body) if body else "No summary supplied."}</p>
  <div class="kl-meta"><span>{escape(str(entry.get("status") or "active"))}</span><span>{escape(str(entry.get("observed_at") or "undated"))}</span></div>
  <div class="kl-tags">{tags}</div>
  <div class="kl-refs">{refs}</div>
</article>"""


def _render_change_window(title: str, window: Mapping[str, Any]) -> str:
    items = "".join(
        f"<li><strong>{escape(str(item['section']).replace('_', ' ').title())}</strong>: {escape(str(item['title']))}</li>"
        for item in window.get("items") or []
    )
    if not items:
        items = "<li>No dated supplied changes.</li>"
    return f"""<article class="kl-window">
  <h2>{escape(title)}</h2>
  <p>{escape(str(window.get("summary") or ""))}</p>
  <ol>{items}</ol>
</article>"""


def _render_source(source: Mapping[str, Any]) -> str:
    ref = str(source["ref"])
    label = escape(str(source.get("label") or ref))
    safe_ref = escape(ref, quote=True)
    if ref.startswith(("https://", "http://")):
        rendered_ref = f'<a href="{safe_ref}">{label}</a>'
    else:
        rendered_ref = f"<span>{label}</span>"
    return (
        f"<li>{rendered_ref}<span>{escape(str(source.get('kind') or 'source'))}</span>"
        f"<span>{escape(str(source.get('observed_at') or 'undated'))}</span></li>"
    )


def _section_title(section: str) -> str:
    return {
        "project_links": "Project Links",
        "saved_notes": "Saved Notes",
        "open_questions": "Open Questions",
    }.get(section, section.replace("_", " ").title())


def _stylesheet() -> str:
    return """
.kl-page{box-sizing:border-box;max-width:1180px;margin:0 auto;padding:24px;color:#17212b;background:#fff;font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.kl-page *{box-sizing:border-box;min-width:0;overflow-wrap: anywhere}
.kl-hero{padding:20px 0 18px;border-bottom:4px solid #0f766e}
.kl-eyebrow{margin:0 0 6px;color:#7c2d12;font-size:.78rem;font-weight:800;text-transform:uppercase;letter-spacing:.08em}
.kl-hero h1{margin:0;font-size:2.25rem;line-height:1.1}
.kl-query{max-width:820px;margin:12px 0 0;color:#334155}
.kl-understanding{max-width:900px;margin:16px 0 0;font-size:1.08rem}
.kl-nav{position:sticky;top:0;z-index:2;display:flex;flex-wrap:wrap;gap:8px;margin:0 -24px 24px;padding:10px 24px;border-bottom:1px solid #cbd5e1;background:#f8fafc}
.kl-nav a{color:#1d4ed8;font-weight:700;text-decoration-thickness:2px;text-underline-offset:2px}
.kl-window-grid,.kl-card-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:14px}
.kl-window,.kl-card{padding:14px;border:1px solid #c8d0d8;border-radius:8px;background:#fff}
.kl-window{border-left:5px solid #1d4ed8;background:#eff6ff}
.kl-section{padding:20px 0;border-top:1px solid #e2e8f0}
.kl-section-head{display:grid;grid-template-columns:minmax(0,1fr);gap:2px;margin-bottom:12px}
.kl-section h2,.kl-window h2{margin:0;font-size:1.25rem}
.kl-card h3{margin:0 0 8px;font-size:1rem}
.kl-card p,.kl-window p{margin:0 0 10px;color:#334155}
.kl-meta,.kl-tags,.kl-refs{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.kl-meta span,.kl-tags span,.kl-refs span{padding:2px 7px;border:1px solid #cbd5e1;border-radius:999px;color:#475569;background:#f8fafc;font-size:.82rem}
.kl-empty{margin:0;color:#475569}
.kl-source-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:10px;padding-left:20px}
.kl-source-list li{padding:10px;border:1px solid #cbd5e1;border-radius:8px;background:#f8fafc}
.kl-source-list span{display:block;color:#475569;font-size:.86rem}
.kl-source-list a{color:#1d4ed8;text-decoration-thickness:2px;text-underline-offset:2px}
@media (max-width: 760px){.kl-page{padding:14px}.kl-nav{position:static;margin:0 -14px 18px;padding:10px 14px}.kl-hero h1{font-size:1.65rem}.kl-window-grid,.kl-card-grid,.kl-source-list{grid-template-columns:1fr}}
@media print{.kl-page{max-width:none;padding:0}.kl-nav{position:static}.kl-window,.kl-card,.kl-source-list li{break-inside:avoid}}
""".strip()


def _mapping_list(raw: object) -> list[Mapping[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise KnowledgeLibraryValidationError("expected list of objects")
    result: list[Mapping[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise KnowledgeLibraryValidationError("expected list of objects")
        result.append(item)
    return result


def _loads_json_list(raw: object) -> list[str]:
    if isinstance(raw, list):
        return _text_list(raw)
    if raw is None:
        return []
    try:
        loaded = json.loads(str(raw))
    except json.JSONDecodeError:
        return []
    return _text_list(loaded)


def _text_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        return [_clean_text(raw)] if _clean_text(raw) else []
    return _unique_texts([_clean_text(item) for item in raw if _clean_text(item)])


def _unique_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _unique_sources(sources: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for source in sources:
        ref = str(source.get("ref") or "")
        if not ref or ref in seen:
            continue
        seen.add(ref)
        result.append(source)
    return result[:24]


def _required_text(value: object, field_name: str) -> str:
    clean = _clean_text(value)
    if not clean:
        raise KnowledgeLibraryValidationError(f"{field_name} is required")
    return clean


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:95] or "topic"


def _parse_datetime(value: str) -> datetime | None:
    clean = _clean_text(value)
    if not clean:
        return None
    if clean.endswith("Z"):
        clean = clean[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(clean)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
