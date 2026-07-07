import html
import json
import logging
import os
import re
import sqlite3
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from config.settings import PROJECT_ROOT, Settings
from output.ai_intelligence_report import (
    _current_week_label,
    _source_channel,
    _week_bounds,
    load_ai_intelligence_context,
)
from output.report_quality import MATCHES_TRACE_RE, ReportQualityFinding, SEVERITY_CRITICAL


LOGGER = logging.getLogger(__name__)
OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "ai_visual_intelligence"
PROJECTS_YAML_PATH = PROJECT_ROOT / "src" / "config" / "projects.yaml"
PROFILE_YAML_PATH = PROJECT_ROOT / "src" / "config" / "profile.yaml"
DEFAULT_ARCHIFY_CANDIDATES = (
    PROJECT_ROOT / ".agents" / "skills" / "archify",
    PROJECT_ROOT / "tools" / "archify",
    Path.home() / ".agents" / "skills" / "archify",
    Path.home() / ".claude" / "skills" / "archify",
    Path.home() / ".codex" / "skills" / "archify",
)
VISUAL_REQUIRED_SECTIONS = (
    ("decision-brief", "Decision Brief"),
    ("what-changed", "What Changed"),
    ("actions", "Study And Do"),
    ("project-implications", "Project Implications"),
    ("knowledge-flow", "Knowledge Flow"),
    ("trend-board", "Trend Board"),
    ("sources", "Sources"),
)
GENERIC_PROJECT_TERMS = {
    "agent",
    "agents",
    "ai",
    "automation",
    "channel",
    "data",
    "developer",
    "evidence",
    "implementation",
    "memory",
    "project",
    "public",
    "research",
    "risk",
    "signal",
    "signals",
    "source",
    "support",
    "tool",
    "workflow",
    "discovery",
    "service",
    "training",
    "voice",
}
STRONG_SINGLE_PROJECT_TERMS = {
    "anthropic",
    "claude",
    "codex",
    "fastapi",
    "github",
    "openai",
    "pathway",
    "postgres",
    "postgresql",
    "rag",
    "redis",
    "sqlite",
    "telethon",
}
GENERIC_PROJECT_PHRASES = {
    "ai agents",
    "ai automation",
    "agent orchestration",
    "workflow automation",
}


@dataclass(frozen=True)
class AiVisualReportSummary:
    week_label: str
    generated_at: str
    html_path: str
    json_path: str
    diagram_html_path: str
    diagram_ir_path: str
    archify_status: str
    thread_count: int
    source_atom_count: int
    source_channel_count: int
    project_link_count: int
    action_count: int
    quality_finding_count: int
    notification_text: str
    delivered_message_id: int | None = None


class AiVisualReportQualityError(ValueError):
    def __init__(self, findings: list[ReportQualityFinding]) -> None:
        self.findings = findings
        messages = "; ".join(f"{finding.artifact_type}: {finding.message}" for finding in findings)
        super().__init__(f"AI Visual report failed quality gates: {messages}")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utc_now_iso() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _escape(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _safe_id(value: object) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip()).strip("-")
    if not slug:
        return "item"
    if not re.match(r"^[a-zA-Z]", slug):
        slug = f"n-{slug}"
    return slug[:48]


def _compact(value: object, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)].rstrip()}..."


def _load_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        LOGGER.warning("Could not load yaml path=%s", path, exc_info=True)
        return {}
    return data if isinstance(data, dict) else {}


def _load_projects(projects_yaml_path: Path = PROJECTS_YAML_PATH) -> list[dict]:
    data = _load_yaml(projects_yaml_path)
    return [project for project in data.get("projects", []) if isinstance(project, dict)]


def _load_profile(profile_yaml_path: Path = PROFILE_YAML_PATH) -> dict:
    return _load_yaml(profile_yaml_path)


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b", str(text or "").lower()))


def _project_keywords(project: dict) -> list[str]:
    values = project.get("keywords")
    if isinstance(values, list) and values:
        return [str(value).strip().lower() for value in values if str(value).strip()]
    fallback = f"{project.get('description') or ''} {project.get('focus') or ''}"
    return sorted(_tokenize(fallback))


def _keyword_hit(keyword: str, text_lower: str, tokens: set[str]) -> bool:
    clean = " ".join(str(keyword or "").lower().split())
    if not clean:
        return False
    if " " in clean:
        return clean not in GENERIC_PROJECT_PHRASES and clean in text_lower
    if clean in GENERIC_PROJECT_TERMS:
        return False
    return clean in STRONG_SINGLE_PROJECT_TERMS and clean in tokens


def _thread_source_urls(thread: dict, *, limit: int = 4) -> list[str]:
    urls: list[str] = []
    for atom in thread.get("atoms") or []:
        for url in atom.get("source_urls") or []:
            clean = str(url or "").strip()
            if clean and clean not in urls:
                urls.append(clean)
            if len(urls) >= limit:
                return urls
    return urls


def _thread_text(thread: dict) -> str:
    parts = [
        thread.get("title") or "",
        thread.get("summary") or "",
        " ".join(thread.get("current_claims") or []),
        " ".join(thread.get("superseded_claims") or []),
        " ".join(thread.get("contradictions") or []),
    ]
    for atom in thread.get("atoms") or []:
        parts.extend(
            [
                atom.get("claim") or "",
                atom.get("summary") or "",
                atom.get("why_it_matters") or "",
                " ".join(atom.get("entities") or []),
                " ".join(atom.get("tools") or []),
                " ".join(atom.get("models") or []),
                " ".join(atom.get("practices") or []),
            ]
        )
    return " ".join(parts)


def _project_links(context: dict, projects: list[dict]) -> list[dict]:
    links: list[dict] = []
    for thread in context.get("threads") or []:
        text = _thread_text(thread)
        text_lower = text.lower()
        tokens = _tokenize(text)
        for project in projects:
            keywords = _project_keywords(project)
            hits: list[str] = []
            for keyword in keywords:
                keyword_lower = " ".join(str(keyword or "").lower().split())
                if _keyword_hit(keyword_lower, text_lower, tokens):
                    hits.append(keyword_lower)
                if len(hits) >= 4:
                    break
            if not hits:
                continue
            score = min(1.0, len(hits) / 3)
            confidence = "review"
            if len(hits) >= 3 and float(thread.get("momentum_30d") or 0.0) >= 0.08:
                confidence = "medium"
            if len(hits) >= 4 and int(thread.get("source_channel_count") or 0) >= 2:
                confidence = "higher"
            links.append(
                {
                    "project": str(project.get("name") or project.get("repo") or "unknown-project"),
                    "repo": str(project.get("repo") or ""),
                    "thread_slug": thread.get("slug"),
                    "thread_title": thread.get("title"),
                    "score": round(score, 2),
                    "confidence": confidence,
                    "shared_terms": hits[:4],
                    "why": _compact(
                        f"{thread.get('title') or 'This thread'} may matter because it overlaps "
                        f"{', '.join(hits[:3])}. Treat this as a lead to inspect, not an automatic project decision.",
                        260,
                    ),
                    "next_step": (
                        "Open the linked source atom(s), then decide whether this changes the next project experiment."
                    ),
                    "evidence_urls": _thread_source_urls(thread),
                }
            )
    links.sort(
        key=lambda item: (
            item.get("confidence") == "higher",
            item.get("confidence") == "medium",
            float(item.get("score") or 0.0),
            str(item.get("thread_title") or ""),
        ),
        reverse=True,
    )
    best_by_project: dict[str, dict] = {}
    for link in links:
        project = str(link.get("project") or "")
        if project not in best_by_project:
            best_by_project[project] = link
    return list(best_by_project.values())[:6]


def _all_atoms(threads: list[dict]) -> list[dict]:
    atoms = []
    seen: set[int] = set()
    for thread in threads:
        for atom in thread.get("atoms") or []:
            atom_id = int(atom.get("id") or 0)
            if atom_id in seen:
                continue
            seen.add(atom_id)
            atoms.append(atom)
    return atoms


def _changed_threads(context: dict) -> list[dict]:
    return [thread for thread in context.get("threads") or [] if thread.get("changed_this_week")]


def _this_week_atoms(context: dict) -> list[dict]:
    week_start, week_end = _week_bounds(context["week_label"])
    atoms = []
    for atom in _all_atoms(context.get("threads") or []):
        text = str(atom.get("last_seen_at") or "")
        parsed: datetime | None = None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text) if text else None
        except ValueError:
            parsed = None
        if parsed and parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if parsed and week_start <= parsed.astimezone(timezone.utc) < week_end:
            atoms.append(atom)
    return atoms


def _source_counts(threads: list[dict]) -> list[dict]:
    counts: Counter[str] = Counter()
    for atom in _all_atoms(threads):
        for url in atom.get("source_urls") or []:
            counts[_source_channel(str(url))] += 1
    return [{"channel": channel, "count": count} for channel, count in counts.most_common(12)]


def _term_counts(threads: list[dict], field: str, *, limit: int = 10) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for atom in _all_atoms(threads):
        for term in atom.get(field) or []:
            clean = str(term).strip()
            if clean:
                counts[clean] += 1
    return counts.most_common(limit)


def resolve_archify_root(archify_root: str | Path | None = None) -> Path | None:
    if archify_root is not None and str(archify_root).strip():
        candidate = Path(archify_root)
        cli = candidate / "bin" / "archify.mjs"
        return candidate.resolve() if cli.exists() else None

    candidates: list[Path] = []
    env_root = os.environ.get("ARCHIFY_ROOT", "").strip()
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend(DEFAULT_ARCHIFY_CANDIDATES)
    for candidate in candidates:
        cli = candidate / "bin" / "archify.mjs"
        if cli.exists():
            return candidate.resolve()
    return None


def _build_archify_ir(context: dict, *, project_count: int, action_count: int) -> dict:
    threads = context.get("threads") or []
    atoms = _all_atoms(threads)
    source_count = len(_source_counts(threads))
    model = ""
    analysis = context.get("frontier_analysis") or {}
    if analysis:
        model = str(analysis.get("model") or "")
    return {
        "schema_version": 1,
        "diagram_type": "dataflow",
        "meta": {
            "title": f"AI Knowledge Flow {context['week_label']}",
            "subtitle": "Telegram sources to atoms, threads, frontier synthesis, project actions, and memory",
            "output": f"{context['week_label']}.knowledge-flow.html",
            "animation": "trace",
            "viewBox": [1080, 760],
        },
        "stages": [
            {"label": "Sources"},
            {"label": "Atomize"},
            {"label": "Thread"},
            {"label": "Synthesize"},
            {"label": "Act"},
        ],
        "nodes": [
            {
                "id": "sources",
                "type": "external",
                "label": "Telegram Sources",
                "sublabel": f"{source_count} channels",
                "stage": 0,
                "row": 0,
                "tag": "12w input",
            },
            {
                "id": "profile",
                "type": "security",
                "label": "Profile + Projects",
                "sublabel": f"{project_count} project leads",
                "stage": 0,
                "row": 3,
                "tag": "personal fit",
            },
            {
                "id": "atoms",
                "type": "database",
                "label": "Knowledge Atoms",
                "sublabel": f"{len(atoms)} cited atoms",
                "stage": 1,
                "row": 1,
                "tag": "claims",
            },
            {
                "id": "threads",
                "type": "messagebus",
                "label": "Idea Threads",
                "sublabel": f"{len(threads)} timelines",
                "stage": 2,
                "row": 1,
                "tag": "momentum",
            },
            {
                "id": "frontier",
                "type": "backend",
                "label": "Frontier Analysis",
                "sublabel": model or "pending",
                "stage": 3,
                "row": 0,
                "tag": "why now",
            },
            {
                "id": "report",
                "type": "frontend",
                "label": "Visual HTML",
                "sublabel": "interactive artifact",
                "stage": 4,
                "row": 0,
                "tag": "sendable",
            },
            {
                "id": "obsidian",
                "type": "database",
                "label": "Obsidian Vault",
                "sublabel": "long memory",
                "stage": 4,
                "row": 4,
                "tag": "browse",
            },
            {
                "id": "actions",
                "type": "cloud",
                "label": "Study + Do",
                "sublabel": f"{action_count} next moves",
                "stage": 4,
                "row": 2,
                "tag": "operator",
            },
        ],
        "flows": [
            {
                "from": "sources",
                "to": "atoms",
                "label": "posts to claims",
                "classification": "source-grounded",
                "variant": "emphasis",
            },
            {
                "from": "profile",
                "to": "atoms",
                "label": "personal scoring",
                "classification": "profile filter",
                "variant": "security",
            },
            {
                "from": "atoms",
                "to": "threads",
                "label": "claim timelines",
                "classification": "temporal grouping",
                "variant": "emphasis",
            },
            {
                "from": "threads",
                "to": "frontier",
                "label": "compressed context",
                "classification": "top-model input",
                "variant": "emphasis",
            },
            {
                "from": "profile",
                "to": "frontier",
                "label": "portfolio context",
                "classification": "project fit",
                "variant": "dashed",
            },
            {
                "from": "frontier",
                "to": "report",
                "label": "what changed",
                "classification": "human synthesis",
                "variant": "emphasis",
            },
            {
                "from": "threads",
                "to": "report",
                "label": "metrics + links",
                "classification": "deterministic",
                "variant": "default",
            },
            {
                "from": "threads",
                "to": "obsidian",
                "label": "generated notes",
                "classification": "memory projection",
                "variant": "dashed",
            },
            {
                "from": "report",
                "to": "actions",
                "label": "study queue",
                "classification": "this week",
                "variant": "emphasis",
                "labelAt": [960, 320],
            },
            {
                "from": "obsidian",
                "to": "actions",
                "label": "reference back",
                "classification": "longitudinal memory",
                "variant": "default",
                "labelAt": [1000, 526],
            },
        ],
        "cards": [
            {
                "dot": "emerald",
                "title": "What Archify Shows",
                "items": [
                    "The main path is source posts -> atoms -> threads -> frontier synthesis -> action.",
                    "Profile and project context affect scoring and interpretation, not reader-facing gossip.",
                    "Obsidian remains the memory projection while HTML is the weekly decision artifact.",
                ],
            },
            {
                "dot": "violet",
                "title": "Why This Matters",
                "items": [
                    "The report explains how the week changes the existing knowledge base.",
                    "Project leads turn general AI news into portfolio-specific checks.",
                    "The visual artifact can be sent as a standalone Telegram document.",
                ],
            },
        ],
    }


def _fallback_diagram_html(ir: dict, reason: str) -> str:
    title = _escape((ir.get("meta") or {}).get("title") or "AI Knowledge Flow")
    nodes = ir.get("nodes") or []
    flows = ir.get("flows") or []
    node_map = {str(node.get("id")): node for node in nodes if isinstance(node, dict)}
    flow_items = []
    for flow in flows:
        if not isinstance(flow, dict):
            continue
        source = node_map.get(str(flow.get("from"))) or {}
        target = node_map.get(str(flow.get("to"))) or {}
        flow_items.append(
            "<li>"
            f"<b>{_escape(source.get('label') or flow.get('from'))}</b> -> "
            f"<b>{_escape(target.get('label') or flow.get('to'))}</b>"
            f"<span>{_escape(flow.get('label') or '')}</span>"
            "</li>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#111827; color:#f8fafc; }}
main {{ padding:22px; }}
h1 {{ font-size:22px; margin:0 0 8px; letter-spacing:0; }}
p {{ color:#cbd5e1; margin:0 0 18px; }}
ol {{ display:grid; gap:10px; padding-left:22px; }}
li {{ border:1px solid #334155; border-radius:8px; padding:10px; background:#1f2937; }}
span {{ display:block; color:#93c5fd; font-size:13px; margin-top:4px; }}
</style>
</head>
<body>
<main>
<h1>{title}</h1>
<p>Archify fallback diagram. Reason: {_escape(reason)}</p>
<ol>{"".join(flow_items)}</ol>
</main>
</body>
</html>
"""


def _run_archify(
    *,
    archify_root: Path | None,
    diagram_ir: dict,
    ir_path: Path,
    html_path: Path,
) -> tuple[str, str]:
    ir_path.write_text(json.dumps(diagram_ir, ensure_ascii=False, indent=2), encoding="utf-8")
    if archify_root is None:
        reason = "ARCHIFY_ROOT is not configured and no local skill directory was found"
        html_path.write_text(_fallback_diagram_html(diagram_ir, reason), encoding="utf-8")
        return "fallback_missing", reason
    cli = archify_root / "bin" / "archify.mjs"
    try:
        render = subprocess.run(
            ["node", str(cli), "render", "dataflow", str(ir_path), str(html_path)],
            cwd=str(archify_root),
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if render.returncode != 0:
            reason = _compact(render.stderr or render.stdout or "archify render failed", 500)
            html_path.write_text(_fallback_diagram_html(diagram_ir, reason), encoding="utf-8")
            return "fallback_render_failed", reason
        check = subprocess.run(
            ["node", str(cli), "check", str(html_path)],
            cwd=str(archify_root),
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if check.returncode != 0:
            reason = _compact(check.stderr or check.stdout or "archify check failed", 500)
            html_path.write_text(_fallback_diagram_html(diagram_ir, reason), encoding="utf-8")
            return "fallback_check_failed", reason
    except (OSError, subprocess.TimeoutExpired) as exc:
        reason = _compact(str(exc), 500)
        html_path.write_text(_fallback_diagram_html(diagram_ir, reason), encoding="utf-8")
        return "fallback_exception", reason
    return "rendered", str(archify_root)


def _analysis_items(analysis: dict, key: str) -> list:
    values = analysis.get(key) if isinstance(analysis, dict) else []
    return values if isinstance(values, list) else []


def _analysis_text(item: object, *keys: str) -> str:
    if isinstance(item, dict):
        for key in keys:
            value = str(item.get(key) or "").strip()
            if value:
                return value
        return " ".join(str(value).strip() for value in item.values() if str(value).strip())
    return str(item or "").strip()


def _sentences(value: object, *, limit: int = 3) -> list[str]:
    text = " ".join(str(value or "").split())
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()][:limit]


def _render_item_cards(items: list, *, title_keys: tuple[str, ...], body_keys: tuple[str, ...], limit: int = 4) -> str:
    cards = []
    for item in items[:limit]:
        title = _analysis_text(item, *title_keys)
        body = _analysis_text(item, *body_keys)
        cards.append(
            "<article>"
            f"<h3>{_escape(title or 'Untitled')}</h3>"
            f"<p>{_escape(body)}</p>"
            "</article>"
        )
    return "".join(cards)


def _render_decision_brief(context: dict) -> str:
    analysis = context.get("frontier_analysis") or {}
    if not analysis:
        return (
            "<p>No saved frontier-model synthesis exists for this week yet.</p>"
            '<p class="muted">Run <code>frontier-analysis --lookback-weeks 12</code>, then regenerate this visual report.</p>'
        )
    brief_lines = "".join(f"<li>{_escape(sentence)}</li>" for sentence in _sentences(analysis.get("executive_brief"), limit=3))
    actions = _analysis_items(analysis, "actions")
    study_now = _analysis_items(analysis, "study_now")
    caveats = _analysis_items(analysis, "caveats")
    do_now = _render_item_cards(
        actions,
        title_keys=("title", "action"),
        body_keys=("next_step", "success_criterion", "why"),
        limit=2,
    )
    study = _render_item_cards(
        study_now,
        title_keys=("topic", "title"),
        body_keys=("reason", "why_it_matters"),
        limit=2,
    )
    caveat_items = "".join(
        f"<li>{_escape(_analysis_text(item, 'caveat', 'summary'))}</li>"
        for item in caveats[:3]
    )
    if not do_now:
        do_now = '<p class="muted">No top-model action queue has been saved yet.</p>'
    if not study:
        study = '<p class="muted">No top-model study queue has been saved yet.</p>'
    if not caveat_items:
        caveat_items = "<li>No explicit caveats were saved for this week.</li>"
    return (
        '<div class="decision-layout">'
        '<article class="decision-main">'
        "<h3>Main Read</h3>"
        f'<ol class="decision-list">{brief_lines}</ol>'
        "</article>"
        '<article class="decision-watchout">'
        "<h3>Trust Check</h3>"
        f"<ul>{caveat_items}</ul>"
        "</article>"
        "</div>"
        '<div class="split action-first">'
        f'<div><h3>Do Now</h3><div class="card-grid">{do_now}</div></div>'
        f'<div><h3>Study Next</h3><div class="card-grid">{study}</div></div>'
        "</div>"
    )


def _render_what_changed(context: dict) -> str:
    analysis = context.get("frontier_analysis") or {}
    if not analysis:
        return _render_week_delta(context)
    what_changed = _analysis_items(analysis, "what_changed")
    narratives = _analysis_items(analysis, "trend_narratives")
    changed_html = _render_item_cards(
        what_changed,
        title_keys=("title", "change", "topic"),
        body_keys=("summary", "why_it_matters", "reason"),
        limit=4,
    )
    narrative_html = "".join(
        "<li>"
        f"<b>{_escape(_analysis_text(item, 'title', 'thread_slug'))}</b>"
        f"<span>{_escape(_analysis_text(item, 'narrative', 'summary'))}</span>"
        "</li>"
        for item in narratives[:4]
    )
    return (
        _render_week_delta(context)
        +
        "<h3>Top-Model Interpretation</h3>"
        '<div class="card-grid frontier-cards">'
        f"{changed_html}"
        "</div>"
        '<ol class="narrative-list">'
        f"{narrative_html}"
        "</ol>"
        f'<p class="muted">Synthesis model: {_escape(analysis.get("model") or "")} | '
        f'{_escape(analysis.get("threads_analyzed") or 0)} threads | '
        f'{_escape(analysis.get("atoms_analyzed") or 0)} atoms</p>'
    )


def _bar(value: float, *, label: str = "") -> str:
    percent = max(0, min(100, round(float(value or 0.0) * 100)))
    return (
        '<div class="bar" title="' + _escape(label or f"{percent}%") + '">'
        f'<span style="width:{percent}%"></span>'
        "</div>"
    )


def _render_week_delta(context: dict) -> str:
    changed = _changed_threads(context)
    atoms = _this_week_atoms(context)
    atom_type_counts = Counter(str(atom.get("atom_type") or "unknown") for atom in atoms)
    type_rows = "".join(
        "<li>"
        f"<b>{_escape(atom_type.replace('_', ' '))}</b>"
        f"{_bar(count / max(1, len(atoms)), label=str(count))}"
        f"<span>{_escape(count)} atoms</span>"
        "</li>"
        for atom_type, count in atom_type_counts.most_common(8)
    )
    changed_rows = "".join(
        "<article>"
        f"<h3>{_escape(thread.get('title') or thread.get('slug'))}</h3>"
        f"<p>{_escape(_compact((thread.get('current_claims') or [''])[0], 220))}</p>"
        f"{_bar(thread.get('momentum_30d') or 0.0, label='30d momentum')}"
        "</article>"
        for thread in changed[:6]
    )
    if not changed_rows:
        changed_rows = '<p class="muted">No Idea Thread crossed the current ISO week window in this context.</p>'
    return (
        '<div class="metrics-row">'
        f'<div><b>{_escape(len(changed))}</b><span>changed threads</span></div>'
        f'<div><b>{_escape(len(atoms))}</b><span>atoms this week</span></div>'
        f'<div><b>{_escape(len(_source_counts(context.get("threads") or [])))}</b><span>source channels</span></div>'
        "</div>"
        '<div class="split">'
        f'<div><h3>New Or Updated Threads</h3><div class="card-grid">{changed_rows}</div></div>'
        f'<div><h3>Atom Mix</h3><ul class="distribution">{type_rows or "<li>No current-week atoms.</li>"}</ul></div>'
        "</div>"
    )


def _render_project_implications(project_links: list[dict]) -> str:
    if not project_links:
        return (
            "<p>No project implications were strong enough to show confidently in this report context.</p>"
            '<p class="muted">This is intentional: broad overlaps such as AI, workflow, evidence, and tool are suppressed so the report does not show noisy project guesses. '
            'Update <code>src/config/projects.yaml</code> with more specific project phrases or extract more Knowledge Atoms to improve this section.</p>'
        )
    rows = []
    for link in project_links:
        terms = ", ".join(link.get("shared_terms") or [])
        source_links = " ".join(
            _source_link(url, f"S{index}")
            for index, url in enumerate(link.get("evidence_urls") or [], start=1)
        )
        confidence = str(link.get("confidence") or "review").replace("_", " ")
        rows.append(
            '<article class="project-implication">'
            '<div class="project-head">'
            f'<h3>{_escape(link.get("project") or "")}</h3>'
            f'<span class="status-pill">{_escape(confidence)}</span>'
            "</div>"
            f'<p><b>{_escape(link.get("thread_title") or "")}</b></p>'
            f'<p>{_escape(link.get("why") or "")}</p>'
            f'<p><b>Next check:</b> {_escape(link.get("next_step") or "")}</p>'
            f'<p class="muted">Shared terms: {_escape(terms or "none")} | Evidence: {source_links or "source pending"}</p>'
            "</article>"
        )
    return (
        '<p class="section-note">These are conservative leads from project config overlap. '
        "They should guide what to inspect next, not automatically rewrite project priorities.</p>"
        '<div class="card-grid project-grid compact-grid">'
        + "".join(rows)
        + "</div>"
    )


def _render_trend_board(context: dict) -> str:
    threads = context.get("threads") or []
    cards = []
    for thread in sorted(threads, key=lambda item: float(item.get("momentum_30d") or 0.0), reverse=True)[:10]:
        cards.append(
            '<article class="trend-card">'
            f'<h3>{_escape(thread.get("title") or thread.get("slug"))}</h3>'
            f'<p>{_escape(_compact(thread.get("summary") or "", 220))}</p>'
            '<div class="trend-bars">'
            f'<label>7d {_bar(thread.get("momentum_7d") or 0.0, label="7d momentum")}</label>'
            f'<label>30d {_bar(thread.get("momentum_30d") or 0.0, label="30d momentum")}</label>'
            f'<label>90d {_bar(thread.get("momentum_90d") or 0.0, label="90d momentum")}</label>'
            "</div>"
            f'<p class="muted">{_escape(thread.get("atom_count") or 0)} atoms | '
            f'{_escape(thread.get("source_channel_count") or 0)} channels | '
            f'{_escape(str(thread.get("status") or "").replace("_", " "))}</p>'
            "</article>"
        )
    term_groups = (
        ("Tools", _term_counts(threads, "tools")),
        ("Models", _term_counts(threads, "models")),
        ("Practices", _term_counts(threads, "practices")),
    )
    terms_html = []
    for label, terms in term_groups:
        term_items = "".join(
            f'<li><span>{_escape(term)}</span>{_bar(count / max(1, terms[0][1] if terms else 1), label=str(count))}</li>'
            for term, count in terms[:8]
        )
        terms_html.append(f"<article><h3>{_escape(label)}</h3><ul class=\"term-list\">{term_items}</ul></article>")
    return '<div class="split"><div class="card-grid">' + "".join(cards) + "</div><div>" + "".join(terms_html) + "</div></div>"


def _source_link(url: str, label: str) -> str:
    clean = str(url or "").strip()
    if not clean:
        return ""
    return f'<a href="{_escape(clean)}">{_escape(label)}</a>'


def _render_actions(context: dict) -> str:
    analysis = context.get("frontier_analysis") or {}
    study_now = _analysis_items(analysis, "study_now")
    actions = _analysis_items(analysis, "actions")
    study_html = "".join(
        "<article>"
        f"<h3>{_escape(_analysis_text(item, 'topic', 'title'))}</h3>"
        f"<p>{_escape(_analysis_text(item, 'reason', 'why_it_matters'))}</p>"
        f'<p class="muted">Priority: {_escape(_analysis_text(item, "priority") or "medium")}</p>'
        "</article>"
        for item in study_now[:6]
    )
    action_html = "".join(
        "<article>"
        f"<h3>{_escape(_analysis_text(item, 'title', 'action'))}</h3>"
        f"<p>{_escape(_analysis_text(item, 'next_step', 'why', 'success_criterion'))}</p>"
        "</article>"
        for item in actions[:6]
    )
    if not study_html:
        study_html = '<p class="muted">No frontier study queue has been saved yet.</p>'
    if not action_html:
        action_html = '<p class="muted">No frontier action queue has been saved yet.</p>'
    return (
        '<div class="split">'
        f'<div><h3>Study Now</h3><div class="card-grid">{study_html}</div></div>'
        f'<div><h3>Do Next</h3><div class="card-grid">{action_html}</div></div>'
        "</div>"
    )


def _render_sources(context: dict) -> str:
    channels = _source_counts(context.get("threads") or [])
    rows = []
    for item in channels:
        channel = str(item.get("channel") or "unknown")
        link = f"https://t.me/{channel}" if channel != "unknown" and "." not in channel else ""
        label = f"@{channel}" if link else channel
        rows.append(
            "<tr>"
            f"<td>{_source_link(link, label) if link else _escape(label)}</td>"
            f"<td>{_escape(item.get('count') or 0)}</td>"
            "</tr>"
        )
    source_atoms = []
    for atom in sorted(_all_atoms(context.get("threads") or []), key=lambda item: float(item.get("practical_utility_score") or 0.0), reverse=True)[:12]:
        links = " ".join(_source_link(url, f"S{index}") for index, url in enumerate(atom.get("source_urls") or [], start=1))
        source_atoms.append(
            "<li>"
            f"<b>{_escape(_compact(atom.get('claim') or '', 160))}</b>"
            f"<span>{links or 'source link pending'}</span>"
            "</li>"
        )
    return (
        '<div class="split">'
        '<div><h3>Source Channels</h3><table><thead><tr><th>Channel</th><th>Atoms</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div>"
        '<div><h3>Evidence Links</h3><ol class="source-list">'
        + "".join(source_atoms)
        + "</ol></div>"
        "</div>"
    )


def _render_html(
    context: dict,
    *,
    generated_at: str,
    diagram_html: str,
    diagram_html_path: Path,
    archify_status: str,
    project_links: list[dict],
) -> str:
    week_label = context["week_label"]
    threads = context.get("threads") or []
    atoms = _all_atoms(threads)
    nav = "".join(f'<a href="#{section_id}">{_escape(title)}</a>' for section_id, title in VISUAL_REQUIRED_SECTIONS)
    diagram_srcdoc = _escape(diagram_html)
    profile = _load_profile()
    boost_topics = ", ".join(str(item) for item in (profile.get("boost_topics") or [])[:8])
    hero_actions = _analysis_items(context.get("frontier_analysis") or {}, "actions")
    hero_action_items = "".join(
        f"<li>{_escape(_analysis_text(item, 'title', 'action'))}</li>"
        for item in hero_actions[:2]
    )
    hero_actions_html = (
        f'<div class="hero-actions"><b>Do now</b><ol>{hero_action_items}</ol></div>'
        if hero_action_items
        else ""
    )
    sections = {
        "decision-brief": _render_decision_brief(context),
        "what-changed": _render_what_changed(context),
        "actions": _render_actions(context),
        "project-implications": _render_project_implications(project_links),
        "knowledge-flow": (
            '<p class="section-note">This diagram explains how the report was built. '
            "Read the decision sections first; use this map when auditing the pipeline.</p>"
            '<div class="diagram-shell">'
            f'<iframe title="Archify knowledge flow" srcdoc="{diagram_srcdoc}"></iframe>'
            "</div>"
            f'<p class="muted">Diagram renderer: {_escape(archify_status)} | '
            f'Standalone diagram: {_source_link(str(diagram_html_path), diagram_html_path.name)}</p>'
        ),
        "trend-board": _render_trend_board(context),
        "sources": _render_sources(context),
    }
    section_html = "\n".join(
        f'<section id="{section_id}"><h2>{_escape(title)}</h2>{sections[section_id]}</section>'
        for section_id, title in VISUAL_REQUIRED_SECTIONS
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Decision Intelligence { _escape(week_label) }</title>
<style>
:root {{ color-scheme: light; --ink:#172026; --muted:#62717f; --bg:#eef3f1; --panel:#fff; --line:#d6dfdc; --green:#0f766e; --blue:#2563eb; --rose:#be123c; --amber:#b45309; --soft:#f8fafc; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--ink); line-height:1.55; }}
a {{ color:#0b63ce; text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
header {{ position:relative; overflow:hidden; background:#10231f; color:#f8fafc; padding:30px 24px 24px; }}
header::after {{ content:""; position:absolute; inset:auto 0 0 0; height:5px; background:linear-gradient(90deg,#14b8a6,#2563eb,#f59e0b,#e11d48); }}
.hero {{ max-width:1180px; margin:0 auto; display:grid; grid-template-columns:minmax(0,1.25fr) minmax(260px,.75fr); gap:22px; align-items:end; }}
.kicker {{ color:#99f6e4; font-size:12px; font-weight:800; text-transform:uppercase; letter-spacing:.08em; margin:0 0 7px; }}
h1 {{ font-size:38px; line-height:1.08; margin:0 0 10px; letter-spacing:0; }}
h2 {{ font-size:23px; line-height:1.2; margin:0 0 14px; letter-spacing:0; }}
h3 {{ font-size:16px; line-height:1.26; margin:0 0 7px; letter-spacing:0; }}
p {{ margin:0 0 11px; }}
.lead {{ font-size:18px; max-width:900px; color:#26333d; }}
.muted {{ color:var(--muted); font-size:13px; }}
.hero-metrics {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }}
.hero-metrics div, section, article {{ border:1px solid var(--line); border-radius:8px; }}
.hero-metrics div {{ padding:12px; background:rgba(255,255,255,.08); border-color:rgba(255,255,255,.18); }}
.hero-metrics b {{ display:block; font-size:27px; line-height:1; }}
.hero-metrics span {{ color:#cbd5e1; font-size:12px; }}
.hero-actions {{ margin-top:12px; border:1px solid rgba(153,246,228,.36); border-radius:8px; padding:10px 12px; background:rgba(15,118,110,.18); max-width:760px; }}
.hero-actions b {{ display:block; color:#99f6e4; font-size:13px; margin-bottom:4px; text-transform:uppercase; }}
.hero-actions ol {{ margin:0; padding-left:20px; color:#f8fafc; display:grid; gap:2px; }}
nav {{ max-width:1180px; margin:18px auto 0; display:flex; flex-wrap:wrap; gap:8px; }}
nav a {{ color:#eff6ff; border:1px solid rgba(255,255,255,.22); border-radius:6px; padding:7px 10px; background:rgba(255,255,255,.08); font-size:13px; }}
main {{ max-width:1180px; margin:0 auto; padding:14px 24px 46px; }}
section {{ background:var(--panel); padding:20px; margin:0 0 14px; }}
article {{ background:#fbfdfc; padding:13px; margin:0; }}
.card-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(235px,1fr)); gap:10px; }}
.compact-grid {{ grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); }}
.frontier-cards article:first-child {{ border-color:#99f6e4; background:#f0fdfa; }}
.narrative-list, .source-list {{ padding-left:22px; margin:14px 0 0; }}
.narrative-list li, .source-list li {{ margin:0 0 9px; }}
.narrative-list span, .source-list span {{ display:block; color:var(--muted); font-size:13px; }}
.decision-layout {{ display:grid; grid-template-columns:minmax(0,1.2fr) minmax(260px,.8fr); gap:12px; margin-bottom:14px; }}
.decision-main {{ background:#f0fdfa; border-color:#99f6e4; }}
.decision-watchout {{ background:#fff7ed; border-color:#fed7aa; }}
.decision-list {{ margin:0; padding-left:22px; display:grid; gap:8px; font-size:17px; }}
.action-first article {{ background:#f8fafc; }}
.section-note {{ color:#425466; margin-top:-2px; max-width:860px; }}
.project-head {{ display:flex; align-items:flex-start; justify-content:space-between; gap:10px; }}
.status-pill {{ display:inline-block; border:1px solid #cbd5e1; border-radius:999px; padding:2px 8px; color:#334155; background:#f8fafc; font-size:12px; font-weight:700; white-space:nowrap; }}
.project-implication {{ background:#fbfdfc; }}
.diagram-shell {{ width:100%; height:min(70vh,720px); min-height:520px; border:1px solid var(--line); border-radius:8px; overflow:hidden; background:#0f172a; }}
.diagram-shell iframe {{ width:100%; height:100%; border:0; display:block; }}
.metrics-row {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px; margin:0 0 16px; }}
.metrics-row div {{ border:1px solid var(--line); border-radius:8px; background:#f8fafc; padding:13px; }}
.metrics-row b {{ display:block; font-size:26px; line-height:1; color:var(--green); }}
.metrics-row span {{ color:var(--muted); font-size:13px; }}
.split {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(280px,.72fr); gap:14px; align-items:start; }}
.bar {{ height:8px; border-radius:999px; background:#e5e7eb; overflow:hidden; margin:8px 0 5px; }}
.bar span {{ display:block; height:100%; background:linear-gradient(90deg,#0f766e,#2563eb,#f59e0b); }}
.distribution, .term-list {{ list-style:none; padding:0; margin:0; display:grid; gap:10px; }}
.distribution li, .term-list li {{ border:1px solid var(--line); border-radius:8px; padding:10px; background:#fbfdfc; }}
.trend-card {{ display:grid; gap:6px; }}
.trend-bars label {{ display:block; font-size:12px; color:var(--muted); }}
table {{ width:100%; border-collapse:collapse; }}
th, td {{ border-bottom:1px solid var(--line); text-align:left; padding:9px 8px; }}
code {{ background:#eef2f6; border:1px solid #d7dee7; border-radius:4px; padding:1px 4px; }}
.profile-note {{ color:#cbd5e1; font-size:13px; margin-top:10px; }}
@media (max-width:860px) {{ .hero, .split, .decision-layout {{ grid-template-columns:1fr; }} h1 {{ font-size:27px; }} main {{ padding-left:14px; padding-right:14px; }} header {{ padding-left:14px; padding-right:14px; }} section {{ padding:14px; }} .profile-note {{ display:none; }} .hero-metrics {{ grid-template-columns:repeat(4,minmax(0,1fr)); }} .hero-metrics div {{ padding:8px; }} .hero-metrics b {{ font-size:20px; }} .hero-metrics span {{ font-size:11px; }} .hero-actions {{ font-size:13px; }} .diagram-shell {{ height:430px; min-height:430px; }} .decision-list {{ font-size:15px; }} .compact-grid {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<header>
<div class="hero">
<div>
<p class="kicker">AI Knowledge Intelligence</p>
<h1>AI Decision Intelligence - {_escape(week_label)}</h1>
<p>Briefing-first weekly artifact: what changed, what to do, what to study, and which project leads deserve inspection.</p>
<p class="profile-note">Profile anchors: {_escape(boost_topics or "profile topics unavailable")}</p>
{hero_actions_html}
</div>
<div class="hero-metrics">
<div><b>{_escape(len(threads))}</b><span>idea threads</span></div>
<div><b>{_escape(len(atoms))}</b><span>source atoms</span></div>
<div><b>{_escape(len(_source_counts(threads)))}</b><span>source channels</span></div>
<div><b>{_escape(len(project_links))}</b><span>project leads</span></div>
</div>
</div>
<nav>{nav}</nav>
</header>
<main>
<p class="muted">Generated {_escape(generated_at)}. Frontier synthesis drives the briefing; deterministic code renders metrics, sources, and the Archify pipeline map.</p>
{section_html}
</main>
</body>
</html>
"""


def validate_ai_visual_html(html_text: str) -> list[ReportQualityFinding]:
    content = html.unescape(str(html_text or ""))
    findings: list[ReportQualityFinding] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if MATCHES_TRACE_RE.search(line):
            findings.append(
                ReportQualityFinding(
                    severity=SEVERITY_CRITICAL,
                    artifact_type="ai_visual_report",
                    message="Internal matching trace is visible in the AI Visual report",
                    line_hint=f"line {line_number}: {line.strip()[:160]}",
                )
            )
    for section_id, title in VISUAL_REQUIRED_SECTIONS:
        if f'id="{section_id}"' not in html_text:
            findings.append(
                ReportQualityFinding(
                    severity=SEVERITY_CRITICAL,
                    artifact_type="ai_visual_report",
                    message=f"Required section is missing: {title}",
                    line_hint=section_id,
                )
            )
    if "<iframe" not in html_text:
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="ai_visual_report",
                message="Archify diagram iframe is missing",
                line_hint="knowledge-flow",
            )
        )
    if "Decision Brief" not in html_text:
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="ai_visual_report",
                message="Decision brief surface is missing",
                line_hint="decision-brief",
            )
        )
    if "Project Implications" not in html_text:
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="ai_visual_report",
                message="Project implications surface is missing",
                line_hint="project-implications",
            )
        )
    return findings


def build_ai_visual_notification(summary: AiVisualReportSummary) -> str:
    return (
        f"AI Decision Intelligence {summary.week_label} is ready.\n"
        f"Threads: {summary.thread_count} | Atoms: {summary.source_atom_count} | "
        f"Project leads: {summary.project_link_count} | Archify: {summary.archify_status}\n"
        f"HTML: {summary.html_path}"
    )


def _write_files(
    *,
    week_label: str,
    html_text: str,
    metadata: dict,
    output_root: Path | str | None,
) -> tuple[Path, Path]:
    root = Path(output_root) if output_root is not None else OUTPUT_DIR
    root.mkdir(parents=True, exist_ok=True)
    html_path = root / f"{week_label}.visual.html"
    json_path = root / f"{week_label}.visual.json"
    html_path.write_text(html_text, encoding="utf-8")
    metadata["html_path"] = str(html_path)
    metadata["json_path"] = str(json_path)
    json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return html_path, json_path


def generate_ai_visual_report(
    settings: Settings,
    *,
    week_label: str | None = None,
    threads_limit: int = 12,
    atoms_limit: int = 8,
    output_root: Path | str | None = None,
    archify_root: str | Path | None = None,
    now: datetime | None = None,
) -> AiVisualReportSummary:
    clean_week = str(week_label or _current_week_label(now)).strip()
    generated_at = (now or _utc_now()).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    root = Path(output_root) if output_root is not None else OUTPUT_DIR
    root.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        context = load_ai_intelligence_context(
            connection,
            week_label=clean_week,
            threads_limit=max(1, int(threads_limit or 12)),
            atoms_limit=max(1, int(atoms_limit or 8)),
        )
    projects = _load_projects()
    project_links = _project_links(context, projects)
    analysis = context.get("frontier_analysis") or {}
    action_count = len(_analysis_items(analysis, "actions"))
    diagram_ir = _build_archify_ir(context, project_count=len(project_links), action_count=action_count)
    ir_path = root / f"{clean_week}.knowledge-flow.archify.json"
    diagram_html_path = root / f"{clean_week}.knowledge-flow.archify.html"
    resolved_archify_root = resolve_archify_root(archify_root)
    archify_status, archify_detail = _run_archify(
        archify_root=resolved_archify_root,
        diagram_ir=diagram_ir,
        ir_path=ir_path,
        html_path=diagram_html_path,
    )
    diagram_html = diagram_html_path.read_text(encoding="utf-8")
    html_text = _render_html(
        context,
        generated_at=generated_at,
        diagram_html=diagram_html,
        diagram_html_path=diagram_html_path,
        archify_status=archify_status,
        project_links=project_links,
    )
    findings = validate_ai_visual_html(html_text)
    critical = [finding for finding in findings if finding.severity == SEVERITY_CRITICAL]
    if critical:
        raise AiVisualReportQualityError(critical)
    threads = context.get("threads") or []
    atoms = _all_atoms(threads)
    metadata = {
        "week_label": clean_week,
        "generated_at": generated_at,
        "thread_count": len(threads),
        "source_atom_count": len(atoms),
        "source_channel_count": len(_source_counts(threads)),
        "project_link_count": len(project_links),
        "action_count": action_count,
        "sections": [title for _section_id, title in VISUAL_REQUIRED_SECTIONS],
        "archify": {
            "status": archify_status,
            "detail": archify_detail,
            "root": str(resolved_archify_root) if resolved_archify_root else None,
            "diagram_html_path": str(diagram_html_path),
            "diagram_ir_path": str(ir_path),
        },
        "frontier_analysis": context.get("frontier_analysis"),
        "project_links": project_links,
        "diagram_ir": diagram_ir,
        "quality_findings": [finding.as_dict() for finding in findings],
    }
    html_path, json_path = _write_files(
        week_label=clean_week,
        html_text=html_text,
        metadata=metadata,
        output_root=root,
    )
    summary = AiVisualReportSummary(
        week_label=clean_week,
        generated_at=generated_at,
        html_path=str(html_path),
        json_path=str(json_path),
        diagram_html_path=str(diagram_html_path),
        diagram_ir_path=str(ir_path),
        archify_status=archify_status,
        thread_count=len(threads),
        source_atom_count=len(atoms),
        source_channel_count=len(_source_counts(threads)),
        project_link_count=len(project_links),
        action_count=action_count,
        quality_finding_count=len(findings),
        notification_text="",
    )
    return AiVisualReportSummary(
        **{
            **asdict(summary),
            "notification_text": build_ai_visual_notification(summary),
        }
    )


def deliver_ai_visual_report(
    summary: AiVisualReportSummary,
    *,
    chat_id: str | None = None,
    token: str | None = None,
) -> AiVisualReportSummary:
    from bot.telegram_delivery import send_document

    clean_chat_id = str(chat_id or os.environ.get("TELEGRAM_OWNER_CHAT_ID", "")).strip()
    clean_token = str(token or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
    if not clean_chat_id or not clean_token:
        LOGGER.info("AI Visual report delivery skipped because Telegram credentials are missing")
        return summary
    message_id = send_document(
        chat_id=clean_chat_id,
        file_path=summary.html_path,
        caption=f"AI Decision Intelligence {summary.week_label}",
        token=clean_token,
    )
    return AiVisualReportSummary(
        **{
            **asdict(summary),
            "delivered_message_id": message_id,
        }
    )
