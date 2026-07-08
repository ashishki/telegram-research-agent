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
from output.ai_report_contract import (
    build_weekly_ai_report_contract,
    validate_weekly_ai_report_contract,
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
    ("decision-brief", "Операторский вердикт"),
    ("strong-signals", "Сильные сигналы"),
    ("deep-explain", "Глубокое объяснение"),
    ("project-implementation", "Проектная реализация"),
    ("mvp-radar", "MVP Radar"),
    ("read-try-build", "Читать / пробовать / строить"),
    ("feedback", "Какой фидбек оставить"),
    ("appendix", "Приложение: источники и аудит"),
)
WORKBOOK_SECTION_META = {
    "decision-brief": {
        "title_en": "Decision Brief",
        "kind": "decision_brief",
        "progressive_disclosure": False,
        "explanatory_only": False,
    },
    "strong-signals": {
        "title_en": "Strong Signals",
        "kind": "strong_signals",
        "progressive_disclosure": False,
        "explanatory_only": False,
    },
    "deep-explain": {
        "title_en": "Deep Explain",
        "kind": "deep_explain",
        "progressive_disclosure": True,
        "explanatory_only": True,
    },
    "project-implementation": {
        "title_en": "Project Implementation",
        "kind": "project_implementation",
        "progressive_disclosure": True,
        "explanatory_only": False,
    },
    "mvp-radar": {
        "title_en": "MVP Radar",
        "kind": "mvp_radar",
        "progressive_disclosure": False,
        "explanatory_only": False,
    },
    "read-try-build": {
        "title_en": "Read/Try/Build",
        "kind": "read_try_build",
        "progressive_disclosure": False,
        "explanatory_only": False,
    },
    "feedback": {
        "title_en": "Feedback",
        "kind": "feedback",
        "progressive_disclosure": False,
        "explanatory_only": False,
    },
    "appendix": {
        "title_en": "Appendix",
        "kind": "appendix",
        "progressive_disclosure": True,
        "explanatory_only": True,
    },
}
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
BUILD_READY_MVP_RECOMMENDATIONS = {"build", "focused_experiment"}
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


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value in (None, "", {}):
        return []
    return [value]


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


def _candidate_mvp_paths(week_label: str, explicit_path: str | Path | None) -> list[Path]:
    if explicit_path is not None:
        return [Path(explicit_path)]
    return [
        PROJECT_ROOT / "data" / "output" / "mvp_weekly" / f"mvp-weekly-{week_label}.json",
        PROJECT_ROOT.parent / "Demand-to-MVP-Radar" / "reports" / "mvp_of_week" / f"mvp-weekly-{week_label}.json",
    ]


def _load_mvp_radar_dossier(week_label: str, explicit_path: str | Path | None = None) -> dict:
    for path in _candidate_mvp_paths(week_label, explicit_path):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            LOGGER.warning("Could not load MVP Radar JSON path=%s", path, exc_info=True)
            continue
        if isinstance(payload, dict):
            return _normalize_mvp_radar_payload(payload, path)
    return {
        "status": "not_available",
        "source_path": str(explicit_path) if explicit_path else None,
        "selected_candidate": None,
        "recommendation": None,
        "decision": "do_not_build",
        "source_mix": {},
        "kir_evidence": {"status": "not_available"},
        "external_evidence": {"status": "not_available"},
        "missing_evidence": ["Run mvp-weekly or pass --mvp-radar-json to embed a candidate dossier."],
        "next_validation": "Run the conservative MVP Radar pipeline before treating any opportunity as build-ready.",
        "kill_criteria": ["Do not build from workbook context alone."],
        "live_source_intelligence": {"status": "not_available", "policy": "context_only"},
    }


def _normalize_mvp_radar_payload(payload: dict, path: Path) -> dict:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    selected = payload.get("selected") if isinstance(payload.get("selected"), dict) else {}
    source_mix = {}
    for candidate in (
        result.get("selected_source_mix"),
        selected.get("source_mix"),
        payload.get("selected_source_mix"),
    ):
        if isinstance(candidate, dict):
            source_mix = candidate
            break
    recommendation = str(
        result.get("recommendation")
        or selected.get("recommendation")
        or payload.get("recommendation")
        or ""
    ).strip()
    dossier_status = str(
        result.get("dossier_status")
        or selected.get("dossier_status")
        or payload.get("dossier_status")
        or ""
    ).strip()
    selected_candidate = str(
        result.get("selected_title")
        or selected.get("title")
        or payload.get("selected_title")
        or ""
    ).strip() or None
    missing = _as_list(selected.get("missing_evidence") or result.get("missing_evidence") or payload.get("missing_evidence"))
    kill = _as_list(
        selected.get("kill_criteria")
        or selected.get("kill_threshold")
        or result.get("kill_criteria")
        or payload.get("kill_criteria")
    )
    next_validation = str(
        selected.get("next_validation")
        or selected.get("next_step")
        or result.get("next_validation")
        or payload.get("next_validation")
        or "Collect decision-grade non-Telegram evidence before building."
    ).strip()
    live = {}
    source_counts = result.get("source_counts") if isinstance(result.get("source_counts"), dict) else {}
    if isinstance(source_counts.get("live_intelligence"), dict):
        live = source_counts.get("live_intelligence") or {}
    elif isinstance(payload.get("live_intelligence"), dict):
        live = payload.get("live_intelligence") or {}
    build_ready = recommendation in BUILD_READY_MVP_RECOMMENDATIONS and dossier_status in BUILD_READY_MVP_RECOMMENDATIONS
    return {
        "status": "loaded",
        "source_path": str(path),
        "selected_candidate": selected_candidate,
        "dossier_status": dossier_status or None,
        "recommendation": recommendation or None,
        "score": result.get("score") or selected.get("score") or payload.get("score"),
        "decision": "build_or_experiment" if build_ready else "do_not_build",
        "source_mix": source_mix,
        "kir_evidence": {
            "source_kind": source_mix.get("kir_source_kind"),
            "thread_slug": source_mix.get("kir_thread_slug"),
            "thread_title": source_mix.get("kir_thread_title"),
            "thread_status": source_mix.get("kir_thread_status"),
            "source_atom_count": source_mix.get("kir_source_atom_count"),
            "source_url_count": source_mix.get("kir_source_url_count"),
            "gate_status": source_mix.get("kir_gate_status"),
            "gate_reasons": source_mix.get("kir_gate_reasons") or [],
        },
        "external_evidence": {
            "selected_external_evidence_count": source_mix.get("selected_external_evidence_count"),
            "decision_grade_external": bool(source_mix.get("decision_grade_external")),
            "source_mix_gate": source_mix.get("source_mix_gate"),
            "readiness": source_mix.get("readiness"),
        },
        "missing_evidence": [str(item) for item in missing if str(item).strip()] or ["No missing-evidence list was present in Radar JSON."],
        "next_validation": next_validation,
        "kill_criteria": [str(item) for item in kill if str(item).strip()] or ["Kill if external demand evidence stays weak or source mix remains Telegram-only."],
        "live_source_intelligence": {
            **live,
            "policy": "context_only",
            "used_for_build_decision": False,
        },
    }


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
            source_atom_ids = [
                int(atom.get("id") or 0)
                for atom in (thread.get("atoms") or [])
                if int(atom.get("id") or 0) and (atom.get("source_urls") or [])
            ]
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
                    "source_atom_ids": source_atom_ids[:8],
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
            "title": f"Поток AI-знаний {context['week_label']}",
            "subtitle": "Telegram-источники -> атомы -> темы -> синтез -> действия -> память",
            "output": f"{context['week_label']}.knowledge-flow.html",
            "animation": "trace",
            "viewBox": [1080, 760],
            "evidence_role": "explanatory_only",
            "evidence_note": "Diagram explains workbook dataflow and does not upgrade evidence strength.",
        },
        "stages": [
            {"label": "Источники"},
            {"label": "Атомы"},
            {"label": "Темы"},
            {"label": "Синтез"},
            {"label": "Действия"},
        ],
        "nodes": [
            {
                "id": "sources",
                "type": "external",
                "label": "Telegram-источники",
                "sublabel": f"{source_count} каналов",
                "stage": 0,
                "row": 0,
                "tag": "12w input",
            },
            {
                "id": "profile",
                "type": "security",
                "label": "Профиль + проекты",
                "sublabel": f"{project_count} проектных лидов",
                "stage": 0,
                "row": 3,
                "tag": "personal fit",
            },
            {
                "id": "atoms",
                "type": "database",
                "label": "Атомы знаний",
                "sublabel": f"{len(atoms)} цитированных атомов",
                "stage": 1,
                "row": 1,
                "tag": "claims",
            },
            {
                "id": "threads",
                "type": "messagebus",
                "label": "Темы-таймлайны",
                "sublabel": f"{len(threads)} линий",
                "stage": 2,
                "row": 1,
                "tag": "momentum",
            },
            {
                "id": "frontier",
                "type": "backend",
                "label": "Frontier-синтез",
                "sublabel": model or "pending",
                "stage": 3,
                "row": 0,
                "tag": "why now",
            },
            {
                "id": "report",
                "type": "frontend",
                "label": "HTML-отчет",
                "sublabel": "операторский артефакт",
                "stage": 4,
                "row": 0,
                "tag": "sendable",
            },
            {
                "id": "obsidian",
                "type": "database",
                "label": "Obsidian Vault",
                "sublabel": "длинная память",
                "stage": 4,
                "row": 4,
                "tag": "browse",
            },
            {
                "id": "actions",
                "type": "cloud",
                "label": "Учить + делать",
                "sublabel": f"{action_count} следующих шагов",
                "stage": 4,
                "row": 2,
                "tag": "operator",
            },
        ],
        "flows": [
            {
                "from": "sources",
                "to": "atoms",
                "label": "посты -> утверждения",
                "classification": "source-grounded",
                "variant": "emphasis",
            },
            {
                "from": "profile",
                "to": "atoms",
                "label": "персональная оценка",
                "classification": "profile filter",
                "variant": "security",
            },
            {
                "from": "atoms",
                "to": "threads",
                "label": "таймлайны утверждений",
                "classification": "temporal grouping",
                "variant": "emphasis",
            },
            {
                "from": "threads",
                "to": "frontier",
                "label": "сжатый контекст",
                "classification": "top-model input",
                "variant": "emphasis",
            },
            {
                "from": "profile",
                "to": "frontier",
                "label": "контекст портфеля",
                "classification": "project fit",
                "variant": "dashed",
            },
            {
                "from": "frontier",
                "to": "report",
                "label": "что изменилось",
                "classification": "human synthesis",
                "variant": "emphasis",
            },
            {
                "from": "threads",
                "to": "report",
                "label": "метрики + ссылки",
                "classification": "deterministic",
                "variant": "default",
            },
            {
                "from": "threads",
                "to": "obsidian",
                "label": "сгенерированные заметки",
                "classification": "memory projection",
                "variant": "dashed",
            },
            {
                "from": "report",
                "to": "actions",
                "label": "очередь действий",
                "classification": "this week",
                "variant": "emphasis",
                "labelAt": [960, 320],
            },
            {
                "from": "obsidian",
                "to": "actions",
                "label": "возврат к памяти",
                "classification": "longitudinal memory",
                "variant": "default",
                "labelAt": [1000, 526],
            },
        ],
        "cards": [
            {
                "dot": "emerald",
                "title": "Что показывает Archify",
                "items": [
                    "Главный путь: посты -> атомы -> темы -> frontier-синтез -> действие.",
                    "Профиль и проекты влияют на оценку и интерпретацию, но не подменяют доказательства.",
                    "Obsidian остается проекцией памяти, а HTML - недельным артефактом решений.",
                ],
            },
            {
                "dot": "violet",
                "title": "Зачем это нужно",
                "items": [
                    "Отчет объясняет, как неделя меняет существующую базу знаний.",
                    "Проектные лиды превращают общие AI-сигналы в проверяемые связи с портфелем.",
                    "HTML можно отправить как самостоятельный Telegram-документ.",
                ],
            },
        ],
    }


def _build_concept_diagram_ir(report_contract: dict) -> dict:
    deep_cards = report_contract.get("deep_explanation_cards") or []
    card = deep_cards[0] if deep_cards else {}
    title = str(card.get("title") or "Strong signal").strip()
    return {
        "schema_version": 1,
        "diagram_type": "concept",
        "renderer": "local_svg",
        "deterministic": True,
        "external_assets": False,
        "meta": {
            "title": f"Concept map: {title[:72]}",
            "evidence_role": "explanatory_only",
            "evidence_note": "Concept diagram explains the selected signal and does not upgrade evidence strength.",
        },
        "nodes": [
            {"id": "signal", "label": "Signal", "text": title[:96], "x": 40, "y": 80, "tone": "green"},
            {
                "id": "evidence",
                "label": "Evidence",
                "text": str(card.get("evidence_tier") or "evidence tier pending"),
                "x": 360,
                "y": 40,
                "tone": "blue",
            },
            {
                "id": "caveat",
                "label": "Caveat",
                "text": str(card.get("caveat") or "caveat pending")[:96],
                "x": 360,
                "y": 160,
                "tone": "amber",
            },
            {
                "id": "action",
                "label": "Operator move",
                "text": str(card.get("what_to_do") or "verify then try")[:96],
                "x": 680,
                "y": 100,
                "tone": "rose",
            },
        ],
        "links": [
            {"from": "signal", "to": "evidence", "label": "check sources"},
            {"from": "signal", "to": "caveat", "label": "bound claim"},
            {"from": "evidence", "to": "action", "label": "if verified"},
            {"from": "caveat", "to": "action", "label": "kill condition"},
        ],
    }


def _fallback_diagram_html(ir: dict, reason: str) -> str:
    title = _escape((ir.get("meta") or {}).get("title") or "Поток AI-знаний")
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
<html lang="ru">
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
<p>Резервная диаграмма Archify. Причина: {_escape(reason)}</p>
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


def _verdict_label(value: object) -> str:
    labels = {
        "apply": "применить",
        "study": "изучить",
        "watch": "наблюдать",
        "ignore": "игнорировать",
        "defer": "отложить",
        "verify_first": "сначала проверить",
    }
    return labels.get(str(value or ""), str(value or "проверить"))


def _render_operator_verdict(report_contract: dict) -> str:
    contract = report_contract.get("report_contract") or {}
    cards = report_contract.get("decision_cards") or []
    card_html = []
    for card in cards[:5]:
        atom_ids = ", ".join(str(value) for value in (card.get("evidence_atom_ids") or []))
        card_html.append(
            "<article>"
            f'<p class="status-pill">{_escape(_verdict_label(card.get("verdict")))}</p>'
            f"<h3>{_escape(card.get('title') or '')}</h3>"
            f"<p>{_escape(card.get('why_for_operator') or '')}</p>"
            f"<p><b>Следующий шаг:</b> {_escape(card.get('next_action') or '')}</p>"
            f"<p><b>Критерий успеха:</b> {_escape(card.get('success_criterion') or '')}</p>"
            f'<p class="muted">Доверие: {_escape(card.get("confidence") or "low")} | '
            f'атомы: {_escape(atom_ids or "нет")} | фидбек: <code>{_escape(card.get("feedback_target_id") or "")}</code></p>'
            "</article>"
        )
    if not card_html:
        return (
            "<p>Нет сохраненного операторского вердикта для этой недели.</p>"
            '<p class="muted">Запустите <code>frontier-analysis --lookback-weeks 12</code> и пересоберите отчет.</p>'
        )
    return (
        f'<p class="section-note">{_escape(contract.get("personalization_note") or "")}</p>'
        '<div class="card-grid frontier-cards">'
        + "".join(card_html)
        + "</div>"
    )


def _render_claim_evidence(report_contract: dict) -> str:
    cards = report_contract.get("claim_cards") or []
    rows = []
    for card in cards[:5]:
        source_links = " ".join(
            _source_link(str(url), f"S{index}")
            for index, url in enumerate(card.get("source_urls") or [], start=1)
        )
        atom_ids = ", ".join(str(value) for value in (card.get("evidence_atom_ids") or []))
        rows.append(
            "<article>"
            f"<h3>{_escape(card.get('claim') or '')}</h3>"
            f'<p class="muted">Атомы: {_escape(atom_ids or "нет")} | '
            f'источники: {_escape(card.get("source_count") or 0)} | '
            f'уровень: {_escape(card.get("evidence_tier") or "")} | '
            f'роль: {_escape(card.get("evidence_role") or "")} | '
            f'доверие: {_escape(card.get("confidence") or "")}</p>'
            f'<p><b>Проверка цитаты:</b> {_escape(card.get("verification_status") or "")} | '
            f'quote_verified={_escape(card.get("quote_verified"))} | '
            f'независимость: {_escape(card.get("source_independence_key") or "")}</p>'
            f'<p><b>Область и горизонт:</b> {_escape(card.get("claim_scope") or "")} | {_escape(card.get("time_horizon") or "")}</p>'
            f"<p><b>Оговорка:</b> {_escape(card.get('caveat') or '')}</p>"
            f"<p><b>Срок годности / staleness:</b> {_escape(card.get('expiry_hint') or '')} | "
            f"{_escape(card.get('staleness_status') or '')}</p>"
            f"<p><b>Wording policy:</b> {_escape(card.get('wording_policy') or '')}</p>"
            f"<p><b>Проверить дальше:</b> {_escape(card.get('next_verification_step') or '')}</p>"
            f'<p class="muted">Цитата: {_escape(card.get("evidence_quote") or "ожидает проверки")} | Источники: {source_links or "нет ссылок"}</p>'
            "</article>"
        )
    if not rows:
        return '<p class="muted">Нет карточек утверждений с доказательствами.</p>'
    return (
        '<p class="section-note">Эти карточки отделяют важные утверждения от слабых или одноисточниковых сигналов.</p>'
        '<div class="card-grid compact-grid">'
        + "".join(rows)
        + "</div>"
    )


def _render_what_changed(context: dict, report_contract: dict) -> str:
    deltas = report_contract.get("thread_deltas") or []
    delta_html = []
    for delta in deltas[:5]:
        atom_ids = ", ".join(str(value) for value in (delta.get("new_evidence_atom_ids") or []))
        evidence_items = "".join(
            "<li>"
            f"<b>Atom { _escape(item.get('atom_id') or '') }</b> "
            f"{_escape(item.get('claim') or '')}"
            f"<span>{_escape(item.get('last_seen_at') or '')} | доверие: {_escape(item.get('confidence') or '')}</span>"
            "</li>"
            for item in (delta.get("this_week_evidence") or [])[:4]
            if isinstance(item, dict)
        )
        delta_html.append(
            "<article>"
            f"<h3>{_escape(delta.get('title') or delta.get('thread_slug') or '')}</h3>"
            f"<p><b>Было:</b> {_escape(delta.get('previous_state') or '')}</p>"
            f"<p><b>Новое свидетельство:</b> {_escape(delta.get('new_evidence') or '')}</p>"
            f'<ol class="narrative-list">{evidence_items or "<li>Нет деталей по атомам текущей недели.</li>"}</ol>'
            f"<p><b>Теперь читаю так:</b> {_escape(delta.get('updated_interpretation') or '')}</p>"
            f'<p class="muted">Движение доверия: {_escape(delta.get("confidence_movement") or "")} | '
            f'состояние: {_escape(delta.get("state") or "")} | атомы: {_escape(atom_ids or "недостаточно истории")}</p>'
            f'<p class="muted">Почему одна тема: {_escape(delta.get("why_this_is_one_thread") or "")}</p>'
            f'<p class="muted">Аудит: {_escape(delta.get("merge_split_audit_status") or "")} | '
            f'причина дельты: {_escape(delta.get("delta_reason") or "")}</p>'
            "</article>"
        )
    return (
        _render_week_delta(context)
        + "<h3>Дельты тем</h3>"
        '<div class="card-grid compact-grid">'
        + ("".join(delta_html) or '<p class="muted">Нет сохраненных временных дельт.</p>')
        + "</div>"
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
        f"<span>{_escape(count)} атомов</span>"
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
        changed_rows = '<p class="muted">В этом контексте нет Idea Thread, который пересек окно текущей ISO-недели.</p>'
    return (
        '<div class="metrics-row">'
        f'<div><b>{_escape(len(changed))}</b><span>измененных тем</span></div>'
        f'<div><b>{_escape(len(atoms))}</b><span>атомов за неделю</span></div>'
        f'<div><b>{_escape(len(_source_counts(context.get("threads") or [])))}</b><span>каналов-источников</span></div>'
        "</div>"
        '<div class="split">'
        f'<div><h3>Новые или обновленные темы</h3><div class="card-grid">{changed_rows}</div></div>'
        f'<div><h3>Смесь атомов</h3><ul class="distribution">{type_rows or "<li>Нет атомов текущей недели.</li>"}</ul></div>'
        "</div>"
    )


def _render_project_diagnostic(report_contract: dict) -> str:
    diagnostic = report_contract.get("project_diagnostic") or {}
    confirmed_links = diagnostic.get("confirmed_leads") or []
    project_watch = diagnostic.get("project_watch") or []

    def _project_cards(links: list[dict], *, empty: str) -> str:
        rows = []
        for link in links:
            source_links = " ".join(
                _source_link(url, f"S{index}")
                for index, url in enumerate(link.get("evidence_urls") or [], start=1)
            )
            confidence = str(link.get("confidence") or "review").replace("_", " ")
            terms = ", ".join(str(value) for value in (link.get("shared_terms") or []))
            rows.append(
                '<article class="project-implication">'
                '<div class="project-head">'
                f'<h3>{_escape(link.get("project") or "")}</h3>'
                f'<span class="status-pill">{_escape(confidence)}</span>'
                "</div>"
                f'<p><b>{_escape(link.get("thread_title") or "")}</b></p>'
                f'<p>{_escape(link.get("why") or "")}</p>'
                f'<p><b>Следующая проверка:</b> {_escape(link.get("next_step") or "")}</p>'
                f'<p class="muted">Термины: {_escape(terms or "нет")} | Источники: {source_links or "ссылки ожидают проверки"}</p>'
                "</article>"
            )
        return '<div class="card-grid project-grid compact-grid">' + "".join(rows) + "</div>" if rows else f"<p>{_escape(empty)}</p>"

    close_rows = []
    for signal in (diagnostic.get("close_but_not_enough_signals") or [])[:6]:
        terms = ", ".join(str(value) for value in (signal.get("rejected_terms") or []))
        close_rows.append(
            "<li>"
            f"<b>{_escape(signal.get('project') or '')}</b> / {_escape(signal.get('thread_title') or '')}"
            f"<span>{_escape(signal.get('reason') or '')} Термины: {_escape(terms or 'нет')}."
            f" Нужно: {_escape(signal.get('needed_evidence') or '')}</span>"
            "</li>"
        )
    close_html = "".join(close_rows) or "<li>Нет близких, но недостаточных совпадений.</li>"

    rejected_items = []
    for item in (diagnostic.get("rejected_broad_overlaps") or [])[:10]:
        if isinstance(item, dict):
            rejected_items.append(
                f"{item.get('project') or 'project'}:{item.get('term') or ''}"
            )
        else:
            rejected_items.append(str(item))
    rejected = ", ".join(rejected_items)

    learning = "".join(
        "<li>"
        f"<b>{_escape(item.get('topic') or '')}</b>"
        f"<span>{_escape(item.get('reason') or '')}</span>"
        "</li>"
        for item in (diagnostic.get("learning_only_implications") or [])[:4]
        if isinstance(item, dict)
    )
    missing = "".join(f"<li>{_escape(item)}</li>" for item in (diagnostic.get("missing_evidence") or [])[:4])
    missing_config = "".join(
        f"<li>{_escape(item)}</li>"
        for item in (diagnostic.get("missing_config_suggestions") or [])[:4]
    )
    suggestion_cards = []
    for suggestion in (diagnostic.get("implementation_suggestions") or [])[:4]:
        criteria = "".join(
            f"<li>{_escape(item)}</li>" for item in (suggestion.get("acceptance_criteria") or [])[:4]
        )
        source_links = " ".join(
            _source_link(str(url), f"S{index}")
            for index, url in enumerate(suggestion.get("source_urls") or [], start=1)
        )
        atom_ids = ", ".join(str(value) for value in (suggestion.get("source_atom_ids") or []))
        suggestion_cards.append(
            '<article class="project-implication">'
            f'<p class="status-pill">{_escape(suggestion.get("suggestion_type") or "backlog")}</p>'
            f"<h3>{_escape(suggestion.get('title') or '')}</h3>"
            f"<p><b>Effort:</b> {_escape(suggestion.get('effort') or '')}</p>"
            f"<p><b>Next step:</b> {_escape(suggestion.get('next_step') or '')}</p>"
            f"<p><b>Risk/caveat:</b> {_escape(suggestion.get('risk_caveat') or '')}</p>"
            f"<p><b>Acceptance criteria:</b></p><ul>{criteria or '<li>Нужно сформулировать критерии.</li>'}</ul>"
            f'<p class="muted">Source atoms: {_escape(atom_ids or "нет")} | Источники: {source_links or "нет ссылок"}</p>'
            "</article>"
        )
    checked = ", ".join(str(value) for value in (diagnostic.get("checked_projects") or []))
    confirmed_empty = diagnostic.get("no_confirmed_leads_reason") or "Подтвержденных проектных лидов нет."
    return (
        '<p class="section-note">Проектная диагностика консервативна: широкие совпадения не становятся решениями.</p>'
        f'<p class="muted">Проверенные проекты: {_escape(checked or "нет списка")} | '
        f'подавленные широкие совпадения: {_escape(rejected or "нет")}</p>'
        "<h3>Подтвержденные проектные лиды</h3>"
        + _project_cards(confirmed_links, empty=str(confirmed_empty))
        + "<h3>Проекты под наблюдением</h3>"
        + _project_cards(project_watch, empty="Нет слабых project-watch совпадений.")
        + "<h3>PR/backlog candidates</h3>"
        + (
            '<div class="card-grid project-grid compact-grid">' + "".join(suggestion_cards) + "</div>"
            if suggestion_cards
            else "<p>Нет PR/backlog кандидатов: проектная связь пока не доказана.</p>"
        )
        + "<h3>Близко, но недостаточно</h3>"
        f'<ol class="narrative-list">{close_html}</ol>'
        + "<h3>Учебные следствия без проектного решения</h3>"
        f'<ol class="narrative-list">{learning or "<li>Нет учебных следствий.</li>"}</ol>'
        + "<h3>Чего не хватает для лида</h3>"
        f"<ul>{missing or '<li>Нужны более специфичные источники.</li>'}</ul>"
        + "<h3>Что уточнить в конфиге</h3>"
        f"<ul>{missing_config or '<li>Добавить специфичные project keywords.</li>'}</ul>"
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
            f'<p class="muted">{_escape(thread.get("atom_count") or 0)} атомов | '
            f'{_escape(thread.get("source_channel_count") or 0)} каналов | '
            f'{_escape(str(thread.get("status") or "").replace("_", " "))}</p>'
            "</article>"
        )
    term_groups = (
        ("Инструменты", _term_counts(threads, "tools")),
        ("Модели", _term_counts(threads, "models")),
        ("Практики", _term_counts(threads, "practices")),
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


def _action_kind_label(value: object) -> str:
    return {
        "try": "попробовать",
        "experiment": "эксперимент",
    }.get(str(value or ""), str(value or ""))


def _render_actions(report_contract: dict) -> str:
    actions = report_contract.get("action_cards") or []
    action_html = "".join(
        "<article>"
        f'<p class="status-pill">{_escape(_action_kind_label(item.get("action_kind")))}</p>'
        f"<h3>{_escape(item.get('title') or '')}</h3>"
        f"<p><b>Следующий шаг:</b> {_escape(item.get('next_step') or '')}</p>"
        f"<p><b>Успех:</b> {_escape(item.get('success_criterion') or '')}</p>"
        f"<p><b>Когда остановиться:</b> {_escape(item.get('kill_condition') or '')}</p>"
        f"<p><b>Повторная проверка:</b> {_escape(item.get('follow_up_hint') or '')}</p>"
        f"<p><b>Правило результата:</b> {_escape(item.get('outcome_policy') or '')}</p>"
        f'<p class="muted">Усилие: {_escape(item.get("effort") or "")} | '
        f'область: {_escape(item.get("scope") or "")} | цель: <code>{_escape(item.get("target_ref") or "")}</code> | '
        f'фидбек: <code>{_escape(item.get("feedback_target_id") or "")}</code></p>'
        "</article>"
        for item in actions[:6]
    )
    return (
        '<p class="section-note">Каждое действие должно быть проверяемым: есть усилие, область, критерий успеха, условие остановки и цель фидбека.</p>'
        '<div class="card-grid compact-grid">'
        + (action_html or '<p class="muted">Нет сохраненных операционных действий.</p>')
        + "</div>"
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
            f"<span>{links or 'ссылка на источник ожидает проверки'}</span>"
            "</li>"
        )
    return (
        '<div class="split">'
        '<div><h3>Каналы-источники</h3><table><thead><tr><th>Канал</th><th>Атомы</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div>"
        '<div><h3>Ссылки на доказательства</h3><ol class="source-list">'
        + "".join(source_atoms)
        + "</ol></div>"
        "</div>"
    )


def _render_feedback_targets(report_contract: dict) -> str:
    targets = report_contract.get("feedback_targets") or []
    contract = report_contract.get("report_contract") or {}
    used = contract.get("feedback_used_summary") or {}
    completion = contract.get("feedback_completion") or {}
    used_summary = used.get("summary") or contract.get("personalization_note") or ""
    completion_text = (
        f"Минимум прошлого фидбека: {completion.get('completed_count', 0)}/{completion.get('required_count', 4)}."
        if completion
        else "Минимум прошлого фидбека еще не закрыт."
    )
    feedback_guidance_text = (
        "Следующий frontier-анализ использует prior feedback для понижения шумных тем и повышения полезных действий."
        if used.get("status") == "feedback_used"
        else "Пока prior feedback нет, поэтому персонализация помечена как низкая."
    )
    rows = []
    for target in targets[:8]:
        options = ", ".join(str(value) for value in (target.get("event_options") or []))
        rows.append(
            "<article>"
            f"<h3>{_escape(target.get('prompt') or '')}</h3>"
            f"<p>{_escape(target.get('why_needed') or '')}</p>"
            f'<p class="muted">Тип: {_escape(target.get("target_type") or "")} | '
            f'цель: <code>{_escape(target.get("id") or "")}</code> | варианты: {_escape(options)}</p>'
            "</article>"
        )
    return (
        '<p class="section-note">Минимальный фидбек недели нужен, чтобы следующий отчет изменил ранжирование, а не повторил старые приоритеты.</p>'
        f'<p><b>{_escape(used_summary)}</b></p>'
        f'<p class="muted">{_escape(completion_text)} {_escape(feedback_guidance_text)}</p>'
        '<div class="card-grid compact-grid">'
        + ("".join(rows) or '<p class="muted">Нет целей фидбека.</p>')
        + "</div>"
    )


def _workbook_sections_metadata() -> list[dict]:
    sections = []
    for section_id, title in VISUAL_REQUIRED_SECTIONS:
        meta = WORKBOOK_SECTION_META.get(section_id, {})
        sections.append(
            {
                "id": section_id,
                "title": title,
                "title_en": meta.get("title_en") or title,
                "kind": meta.get("kind") or section_id.replace("-", "_"),
                "progressive_disclosure": bool(meta.get("progressive_disclosure")),
                "explanatory_only": bool(meta.get("explanatory_only")),
            }
        )
    return sections


def _details(summary: str, body: str, *, open_by_default: bool = False) -> str:
    open_attr = " open" if open_by_default else ""
    return f'<details{open_attr}><summary>{_escape(summary)}</summary>{body}</details>'


def _render_strong_signals(report_contract: dict) -> str:
    return (
        '<p class="section-note">Сильные сигналы опираются на claim cards; диаграммы и объяснения ниже не повышают уровень доказательности.</p>'
        "<h3>Доказательства по ключевым утверждениям</h3>"
        + _render_claim_evidence(report_contract)
    )


def _render_deep_explain(
    context: dict,
    report_contract: dict,
    *,
    concept_diagram_ir: dict,
    diagram_srcdoc: str,
    diagram_html_path: Path,
    archify_status: str,
) -> str:
    diagram = (
        '<p class="section-note">Explanatory only: карта объясняет поток данных workbook и не повышает evidence strength.</p>'
        '<div class="diagram-shell">'
        f'<iframe title="Archify карта потока знаний" srcdoc="{diagram_srcdoc}"></iframe>'
        "</div>"
        f'<p class="muted">Рендер диаграммы: {_escape(archify_status)} | '
        f'отдельный файл: {_source_link(str(diagram_html_path), diagram_html_path.name)}</p>'
    )
    return (
        '<p class="section-note">Explanatory only: этот раздел помогает понять связи и тренды, но не заменяет проверенные источники.</p>'
        + _render_deep_explanation_cards(report_contract)
        + _details("Concept diagram", _render_concept_diagram(concept_diagram_ir), open_by_default=True)
        + _details("Что изменилось", _render_what_changed(context, report_contract), open_by_default=True)
        + _details("Доска трендов", _render_trend_board(context))
        + _details("Карта потока знаний", diagram)
    )


def _render_concept_diagram(ir: dict) -> str:
    nodes = {str(node.get("id")): node for node in (ir.get("nodes") or []) if isinstance(node, dict)}
    tone_colors = {
        "green": ("#ecfdf5", "#0f766e"),
        "blue": ("#eff6ff", "#2563eb"),
        "amber": ("#fffbeb", "#b45309"),
        "rose": ("#fff1f2", "#be123c"),
    }
    links = []
    for link in ir.get("links") or []:
        if not isinstance(link, dict):
            continue
        source = nodes.get(str(link.get("from")))
        target = nodes.get(str(link.get("to")))
        if not source or not target:
            continue
        sx = int(source.get("x") or 0) + 220
        sy = int(source.get("y") or 0) + 42
        tx = int(target.get("x") or 0)
        ty = int(target.get("y") or 0) + 42
        label_x = (sx + tx) // 2
        label_y = (sy + ty) // 2 - 6
        links.append(
            f'<path d="M {sx} {sy} C {sx + 60} {sy}, {tx - 60} {ty}, {tx} {ty}" />'
            f'<text x="{label_x}" y="{label_y}">{_escape(link.get("label") or "")}</text>'
        )
    node_html = []
    for node in nodes.values():
        x = int(node.get("x") or 0)
        y = int(node.get("y") or 0)
        fill, stroke = tone_colors.get(str(node.get("tone") or ""), ("#f8fafc", "#475569"))
        node_html.append(
            f'<g transform="translate({x},{y})">'
            f'<rect width="220" height="86" rx="8" fill="{fill}" stroke="{stroke}" />'
            f'<text class="node-label" x="14" y="24">{_escape(node.get("label") or "")}</text>'
            f'<foreignObject x="14" y="34" width="192" height="42"><div xmlns="http://www.w3.org/1999/xhtml">{_escape(_compact(node.get("text") or "", 90))}</div></foreignObject>'
            "</g>"
        )
    return (
        '<figure class="concept-diagram">'
        f'<figcaption>{_escape((ir.get("meta") or {}).get("title") or "Concept diagram")} · '
        'Explanatory only, not evidence.</figcaption>'
        '<svg viewBox="0 0 940 280" role="img" aria-label="Concept diagram">'
        '<defs><style>path{fill:none;stroke:#64748b;stroke-width:2} text{font:12px sans-serif;fill:#475569}.node-label{font-weight:800;fill:#172026} foreignObject div{font:12px sans-serif;color:#172026;line-height:1.25}</style></defs>'
        + "".join(links)
        + "".join(node_html)
        + "</svg>"
        "</figure>"
    )


def _render_deep_explanation_cards(report_contract: dict) -> str:
    cards = report_contract.get("deep_explanation_cards") or []
    rendered = []
    for card in cards[:5]:
        sources = " ".join(
            _source_link(str(url), f"S{index}")
            for index, url in enumerate(card.get("source_urls") or [], start=1)
        )
        rendered.append(
            '<article class="deep-card">'
            f"<h3>{_escape(card.get('title') or '')}</h3>"
            f"<p><b>What is this:</b> {_escape(card.get('what_is_this') or '')}</p>"
            f"<p><b>Why now:</b> {_escape(card.get('why_now') or '')}</p>"
            f"<p><b>How it works:</b> {_escape(card.get('how_it_works') or '')}</p>"
            f"<p><b>Where is hype:</b> {_escape(card.get('where_is_hype') or '')}</p>"
            f"<p><b>What to do:</b> {_escape(card.get('what_to_do') or '')}</p>"
            f"<p><b>What not to do:</b> {_escape(card.get('what_not_to_do') or '')}</p>"
            f"<p><b>What would change my mind:</b> {_escape(card.get('what_would_change_my_mind') or '')}</p>"
            f'<p class="muted">Evidence tier: {_escape(card.get("evidence_tier") or "")} | '
            f'quote status: {_escape(card.get("quote_verification_status") or "")} | '
            f'caveat: {_escape(card.get("caveat") or "")} | sources: {sources or "нет ссылок"}</p>'
            '<p class="muted">Explanatory only: this card does not upgrade evidence strength.</p>'
            "</article>"
        )
    return '<div class="card-grid compact-grid">' + "".join(rendered) + "</div>" if rendered else ""


def _render_mvp_radar(dossier: dict) -> str:
    missing = "".join(f"<li>{_escape(item)}</li>" for item in (dossier.get("missing_evidence") or [])[:6])
    kill = "".join(f"<li>{_escape(item)}</li>" for item in (dossier.get("kill_criteria") or [])[:5])
    source_mix = dossier.get("source_mix") or {}
    source_mix_rows = "".join(
        f"<li><b>{_escape(key)}</b>: {_escape(value)}</li>"
        for key, value in sorted(source_mix.items())
        if key
    )
    kir = dossier.get("kir_evidence") or {}
    external = dossier.get("external_evidence") or {}
    kir_rows = "".join(f"<li><b>{_escape(key)}</b>: {_escape(value)}</li>" for key, value in sorted(kir.items()))
    external_rows = "".join(
        f"<li><b>{_escape(key)}</b>: {_escape(value)}</li>" for key, value in sorted(external.items())
    )
    live = dossier.get("live_source_intelligence") or {}
    decision = dossier.get("decision") or "do_not_build"
    decision_text = "Do not build" if decision == "do_not_build" else "Build/experiment gate passed"
    return (
        '<p class="section-note">MVP Radar remains conservative: workbook context is not a build recommendation.</p>'
        '<article class="project-implication">'
        f'<p class="status-pill">{_escape(decision_text)}</p>'
        f"<h3>{_escape(dossier.get('selected_candidate') or 'No selected MVP candidate')}</h3>"
        f"<p><b>Status:</b> {_escape(dossier.get('dossier_status') or dossier.get('status') or 'unknown')} | "
        f"<b>Recommendation:</b> {_escape(dossier.get('recommendation') or 'none')} | "
        f"<b>Score:</b> {_escape(dossier.get('score') if dossier.get('score') is not None else 'n/a')}</p>"
        f"<p><b>Next validation:</b> {_escape(dossier.get('next_validation') or '')}</p>"
        "<h4>Source mix</h4>"
        f"<ul>{source_mix_rows or '<li>No source mix available.</li>'}</ul>"
        "<h4>KIR evidence</h4>"
        f"<ul>{kir_rows or '<li>KIR evidence not available.</li>'}</ul>"
        "<h4>External evidence</h4>"
        f"<ul>{external_rows or '<li>External evidence not available.</li>'}</ul>"
        "<h4>Missing evidence</h4>"
        f"<ul>{missing or '<li>No missing evidence supplied.</li>'}</ul>"
        "<h4>Kill criteria</h4>"
        f"<ul>{kill or '<li>Kill if external validation remains weak.</li>'}</ul>"
        f'<p class="muted">Live source intelligence: context-only; used_for_build_decision={_escape(live.get("used_for_build_decision", False))}. '
        f'JSON: {_escape(dossier.get("source_path") or "not available")}</p>'
        "</article>"
    )


def _render_appendix(
    context: dict,
    *,
    diagram_srcdoc: str,
    diagram_html_path: Path,
    archify_status: str,
) -> str:
    diagram = (
        '<p class="section-note">Explanatory only: эта диаграмма описывает путь данных и не является источником доказательств.</p>'
        '<div class="diagram-shell">'
        f'<iframe title="Archify карта потока знаний" srcdoc="{diagram_srcdoc}"></iframe>'
        "</div>"
        f'<p class="muted">Рендер диаграммы: {_escape(archify_status)} | '
        f'отдельный файл: {_source_link(str(diagram_html_path), diagram_html_path.name)}</p>'
    )
    return (
        _details("Источники", _render_sources(context), open_by_default=True)
        + _details("Карта потока знаний", diagram)
        + '<p class="muted">HTML standalone: стили, контракт, iframe srcdoc и ссылки на sidecar сгенерированы вместе с workbook.</p>'
    )


def _render_html(
    context: dict,
    *,
    generated_at: str,
    diagram_html: str,
    diagram_html_path: Path,
    archify_status: str,
    project_links: list[dict],
    report_contract: dict,
    concept_diagram_ir: dict,
    mvp_radar: dict,
) -> str:
    week_label = context["week_label"]
    threads = context.get("threads") or []
    atoms = _all_atoms(threads)
    nav = "".join(f'<a href="#{section_id}">{_escape(title)}</a>' for section_id, title in VISUAL_REQUIRED_SECTIONS)
    diagram_srcdoc = _escape(diagram_html)
    profile = _load_profile()
    boost_topics = ", ".join(str(item) for item in (profile.get("boost_topics") or [])[:8])
    hero_actions = report_contract.get("action_cards") or []
    hero_action_items = "".join(
        f"<li>{_escape(item.get('title') or '')}</li>"
        for item in hero_actions[:2]
    )
    hero_actions_html = (
        f'<div class="hero-actions"><b>Сделать сейчас</b><ol>{hero_action_items}</ol></div>'
        if hero_action_items
        else ""
    )
    sections = {
        "decision-brief": _render_operator_verdict(report_contract),
        "strong-signals": _render_strong_signals(report_contract),
        "deep-explain": _render_deep_explain(
            context,
            report_contract,
            concept_diagram_ir=concept_diagram_ir,
            diagram_srcdoc=diagram_srcdoc,
            diagram_html_path=diagram_html_path,
            archify_status=archify_status,
        ),
        "project-implementation": (
            "<h3>Диагностика проектного соответствия</h3>" + _render_project_diagnostic(report_contract)
        ),
        "mvp-radar": _render_mvp_radar(mvp_radar),
        "read-try-build": "<h3>Операционные действия</h3>" + _render_actions(report_contract),
        "feedback": _render_feedback_targets(report_contract),
        "appendix": _render_appendix(
            context,
            diagram_srcdoc=diagram_srcdoc,
            diagram_html_path=diagram_html_path,
            archify_status=archify_status,
        ),
    }
    section_html = "\n".join(
        f'<section id="{section_id}"><h2>{_escape(title)}</h2>{sections[section_id]}</section>'
        for section_id, title in VISUAL_REQUIRED_SECTIONS
    )
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Еженедельная AI-разведка { _escape(week_label) }</title>
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
.concept-diagram {{ margin:0; border:1px solid var(--line); border-radius:8px; background:#fff; padding:12px; overflow:auto; }}
.concept-diagram figcaption {{ font-size:13px; color:var(--muted); margin-bottom:8px; }}
.concept-diagram svg {{ min-width:760px; width:100%; height:auto; display:block; }}
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
details {{ border:1px solid var(--line); border-radius:8px; background:#fbfdfc; padding:12px 14px; margin:10px 0; }}
summary {{ cursor:pointer; font-weight:750; color:#10231f; }}
details > *:not(summary) {{ margin-top:12px; }}
.profile-note {{ color:#cbd5e1; font-size:13px; margin-top:10px; }}
@media (max-width:860px) {{ .hero, .split, .decision-layout {{ grid-template-columns:1fr; }} h1 {{ font-size:27px; }} main {{ padding-left:14px; padding-right:14px; }} header {{ padding-left:14px; padding-right:14px; }} section {{ padding:14px; }} .profile-note {{ display:none; }} .hero-metrics {{ grid-template-columns:repeat(4,minmax(0,1fr)); }} .hero-metrics div {{ padding:8px; }} .hero-metrics b {{ font-size:20px; }} .hero-metrics span {{ font-size:11px; }} .hero-actions {{ font-size:13px; }} .diagram-shell {{ height:430px; min-height:430px; }} .decision-list {{ font-size:15px; }} .compact-grid {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<header>
<div class="hero">
<div>
<p class="kicker">Еженедельная AI-разведка</p>
<h1>AI-интеллект за неделю - {_escape(week_label)}</h1>
<p>Операторский отчет: что изменилось, какие утверждения доказаны слабо, что читать, что пробовать и какой фидбек оставить.</p>
<p class="profile-note">Якоря профиля: {_escape(boost_topics or "темы профиля недоступны")}</p>
{hero_actions_html}
</div>
<div class="hero-metrics">
<div><b>{_escape(len(threads))}</b><span>тем</span></div>
<div><b>{_escape(len(atoms))}</b><span>атомов источников</span></div>
<div><b>{_escape(len(_source_counts(threads)))}</b><span>каналов</span></div>
<div><b>{_escape(len(project_links))}</b><span>проектных лидов</span></div>
</div>
</div>
<nav>{nav}</nav>
</header>
<main>
<p class="muted">Сгенерировано {_escape(generated_at)}. Frontier-синтез дает интерпретацию; детерминированный код отвечает за метрики, источники, контракт качества и карту Archify.</p>
{section_html}
</main>
</body>
</html>
"""


def validate_ai_visual_html(html_text: str) -> list[ReportQualityFinding]:
    content = html.unescape(str(html_text or ""))
    findings: list[ReportQualityFinding] = []
    if "<!doctype html>" not in str(html_text or "").lower():
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="ai_visual_report",
                message="Standalone workbook HTML must include a doctype",
                line_hint="doctype",
            )
        )
    if len(str(html_text or "")) > 250000:
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="ai_visual_report",
                message="Workbook HTML is too large and risks becoming a wall of text",
                line_hint=f"chars={len(str(html_text or ''))}",
            )
        )
    if "<details" not in str(html_text or ""):
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="ai_visual_report",
                message="Deep workbook sections must use progressive disclosure",
                line_hint="details",
            )
        )
    if "Explanatory only" not in content:
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="ai_visual_report",
                message="Diagrams and explanations must be labeled as explanatory-only",
                line_hint="explanatory-only",
            )
        )
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
    if "Операторский вердикт" not in html_text:
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="ai_visual_report",
                message="Operator verdict surface is missing",
                line_hint="operator-verdict",
            )
        )
    if "Диагностика проектного соответствия" not in html_text:
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="ai_visual_report",
                message="Project fit diagnostic surface is missing",
                line_hint="project-diagnostic",
            )
        )
    return findings


def build_ai_visual_notification(summary: AiVisualReportSummary) -> str:
    return (
        f"AI-интеллект {summary.week_label} готов.\n"
        f"Темы: {summary.thread_count} | Атомы: {summary.source_atom_count} | "
        f"Проектные лиды: {summary.project_link_count} | Archify: {summary.archify_status}\n"
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
    mvp_radar_json_path: str | Path | None = None,
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
    report_contract = build_weekly_ai_report_contract(
        context,
        project_links=project_links,
        projects=projects,
    )
    mvp_radar = _load_mvp_radar_dossier(clean_week, mvp_radar_json_path)
    concept_diagram_ir = _build_concept_diagram_ir(report_contract)
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
        report_contract=report_contract,
        concept_diagram_ir=concept_diagram_ir,
        mvp_radar=mvp_radar,
    )
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
        "workbook_sections": _workbook_sections_metadata(),
        "workbook_contract": {
            "artifact_type": "weekly_ai_intelligence_workbook",
            "first_screen": "concise_decision_brief",
            "deep_sections_use_progressive_disclosure": True,
            "max_html_chars": 250000,
            "explanatory_surfaces_do_not_upgrade_evidence": True,
        },
        **report_contract,
        "mvp_radar": mvp_radar,
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
        "concept_diagram_ir": concept_diagram_ir,
    }
    findings = [
        *validate_ai_visual_html(html_text),
        *validate_weekly_ai_report_contract(metadata, html_text=html_text),
    ]
    critical = [finding for finding in findings if finding.severity == SEVERITY_CRITICAL]
    if critical:
        raise AiVisualReportQualityError(critical)
    metadata["quality_findings"] = [finding.as_dict() for finding in findings]
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
        caption=f"AI-интеллект {summary.week_label}",
        token=clean_token,
    )
    return AiVisualReportSummary(
        **{
            **asdict(summary),
            "delivered_message_id": message_id,
        }
    )
