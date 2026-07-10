import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from config.settings import MID_MODEL, STRONG_MODEL, Settings
from db.frontier_analysis import fetch_frontier_analysis, upsert_frontier_analysis
from llm.client import complete
from output.ai_intelligence_report import _current_week_label, load_ai_intelligence_context


LOGGER = logging.getLogger(__name__)
PROMPT_VERSION = "frontier-analysis-v1"
DEFAULT_THREADS_LIMIT = 24
DEFAULT_ATOMS_LIMIT = 8
FRONTIER_ANALYSIS_MAX_TOKENS = 4096


class FrontierAnalysisError(Exception):
    pass


class FrontierAnalysisValidationError(FrontierAnalysisError):
    pass


@dataclass(frozen=True)
class FrontierAnalysisSummary:
    week_label: str
    model: str
    prompt_version: str
    lookback_weeks: int
    threads_analyzed: int
    atoms_analyzed: int
    executive_brief: str
    what_changed_count: int
    trend_narrative_count: int
    study_now_count: int
    action_count: int
    caveat_count: int
    skipped_existing: bool = False


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_frontier_model(model: str | None) -> str:
    selected = str(model or "strong").strip()
    if selected == "strong":
        return STRONG_MODEL
    if selected == "mid":
        return MID_MODEL
    return selected


def _parse_json_object(raw_text: str) -> dict:
    text = str(raw_text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FrontierAnalysisValidationError(f"frontier model returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise FrontierAnalysisValidationError("frontier model JSON root must be an object")
    return parsed


def _as_list(value: object, field_name: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise FrontierAnalysisValidationError(f"{field_name} must be a list")
    return value


def _clean_items(values: object, field_name: str, *, limit: int) -> list[dict | str]:
    cleaned = []
    for item in _as_list(values, field_name):
        if isinstance(item, dict):
            compact = {
                str(key).strip(): value
                for key, value in item.items()
                if str(key).strip() and value not in (None, "", [], {})
            }
            if compact:
                cleaned.append(compact)
        else:
            text = str(item or "").strip()
            if text:
                cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _validate_payload(payload: dict) -> dict:
    executive_brief = str(payload.get("executive_brief") or "").strip()
    if not executive_brief:
        raise FrontierAnalysisValidationError("executive_brief is required")
    normalized = {
        "executive_brief": executive_brief,
        "what_changed": _clean_items(payload.get("what_changed"), "what_changed", limit=8),
        "trend_narratives": _clean_items(payload.get("trend_narratives"), "trend_narratives", limit=8),
        "study_now": _clean_items(payload.get("study_now"), "study_now", limit=8),
        "actions": _clean_items(payload.get("actions"), "actions", limit=8),
        "caveats": _clean_items(payload.get("caveats"), "caveats", limit=8),
    }
    if not normalized["what_changed"]:
        raise FrontierAnalysisValidationError("what_changed must contain at least one item")
    if not normalized["study_now"]:
        raise FrontierAnalysisValidationError("study_now must contain at least one item")
    if not normalized["actions"]:
        raise FrontierAnalysisValidationError("actions must contain at least one item")
    return normalized


def _atom_for_prompt(atom: dict) -> dict:
    return {
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


def _thread_for_prompt(thread: dict) -> dict:
    return {
        "slug": thread.get("slug"),
        "title": thread.get("title"),
        "status": thread.get("status"),
        "first_seen_at": thread.get("first_seen_at"),
        "last_seen_at": thread.get("last_seen_at"),
        "momentum_7d": thread.get("momentum_7d"),
        "momentum_30d": thread.get("momentum_30d"),
        "momentum_90d": thread.get("momentum_90d"),
        "atom_count": thread.get("atom_count"),
        "current_claims": (thread.get("current_claims") or [])[:6],
        "superseded_claims": (thread.get("superseded_claims") or [])[:4],
        "contradictions": (thread.get("contradictions") or [])[:4],
        "atoms": [_atom_for_prompt(atom) for atom in (thread.get("atoms") or [])[:8]],
    }


def _build_prompt(context: dict, *, lookback_weeks: int) -> str:
    prompt_context = {
        "week_label": context.get("week_label"),
        "week_start": context.get("week_start"),
        "week_end": context.get("week_end"),
        "lookback_weeks": lookback_weeks,
        "threads": [_thread_for_prompt(thread) for thread in context.get("threads") or []],
        "feedback_context": context.get("feedback_context") or {},
    }
    return (
        "You are the frontier-model analyst for a personal AI systems engineering intelligence desk.\n"
        "Use the compressed Knowledge Atom and Idea Thread context to write the human-facing synthesis.\n"
        "Do not center source/channel names; source identity is internal scoring context. Focus on what changed, "
        "why it matters, what to study now, and what to do next.\n"
        "All user-facing string values that will appear in the weekly HTML report must be written in Russian. "
        "Keep JSON keys, enum-like values, and source quotes in their original language.\n"
        "Use feedback_context explicitly: downrank topics similar to wrong_priority, not_interested, or noise "
        "events; promote topics similar to tried, useful, or applied_to_project events; treat read as weak observation; treat "
        "missed-post and priority-calibration feedback_eval_examples as eval examples for coverage and ranking. "
        "If feedback_context has no events, say personalization state is unknown, not negative.\n"
        "Return JSON only with this shape:\n"
        "{"
        "\"executive_brief\":\"3-5 sentence direct brief\","
        "\"what_changed\":[{\"title\":\"change\",\"summary\":\"why it changed\",\"why_it_matters\":\"operator impact\"}],"
        "\"trend_narratives\":[{\"thread_slug\":\"slug\",\"title\":\"trend\",\"narrative\":\"how it evolved over time\",\"status\":\"active\"}],"
        "\"study_now\":[{\"topic\":\"topic\",\"reason\":\"why now\",\"priority\":\"high|medium|low\"}],"
        "\"actions\":[{\"title\":\"action\",\"next_step\":\"specific next step\",\"success_criterion\":\"observable result\"}],"
        "\"caveats\":[\"uncertainty or evidence caveat\"]"
        "}.\n"
        "Keep every item concise and decision-oriented. Prefer fewer, stronger items over broad coverage.\n"
        f"Context JSON:\n{json.dumps(prompt_context, ensure_ascii=False, indent=2)}"
    )


def _analysis_summary(row: dict, *, skipped_existing: bool = False) -> FrontierAnalysisSummary:
    return FrontierAnalysisSummary(
        week_label=row["week_label"],
        model=row["model"],
        prompt_version=row["prompt_version"],
        lookback_weeks=row["lookback_weeks"],
        threads_analyzed=row["threads_analyzed"],
        atoms_analyzed=row["atoms_analyzed"],
        executive_brief=row["executive_brief"],
        what_changed_count=len(row.get("what_changed") or []),
        trend_narrative_count=len(row.get("trend_narratives") or []),
        study_now_count=len(row.get("study_now") or []),
        action_count=len(row.get("actions") or []),
        caveat_count=len(row.get("caveats") or []),
        skipped_existing=skipped_existing,
    )


def run_frontier_analysis(
    settings: Settings,
    *,
    week_label: str | None = None,
    lookback_weeks: int = 12,
    model: str = "strong",
    threads_limit: int = DEFAULT_THREADS_LIMIT,
    atoms_limit: int = DEFAULT_ATOMS_LIMIT,
    force: bool = False,
) -> FrontierAnalysisSummary:
    clean_week = str(week_label or _current_week_label()).strip()
    resolved_model = resolve_frontier_model(model)
    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        existing = fetch_frontier_analysis(connection, week_label=clean_week)
        if existing and not force:
            return _analysis_summary(existing, skipped_existing=True)
        context = load_ai_intelligence_context(
            connection,
            week_label=clean_week,
            threads_limit=max(1, int(threads_limit or DEFAULT_THREADS_LIMIT)),
            atoms_limit=max(1, int(atoms_limit or DEFAULT_ATOMS_LIMIT)),
        )
        threads = context.get("threads") or []
        if not threads:
            raise FrontierAnalysisError("no Idea Threads available; run knowledge-extract and idea-threads first")
        atoms_seen = len({atom["id"] for thread in threads for atom in thread.get("atoms") or []})
        raw = complete(
            prompt=_build_prompt(context, lookback_weeks=max(1, int(lookback_weeks or 1))),
            system="You synthesize source-grounded AI intelligence into strict JSON for a human weekly report.",
            max_tokens=FRONTIER_ANALYSIS_MAX_TOKENS,
            category="frontier_analysis",
            model=resolved_model,
        )
        payload = _validate_payload(_parse_json_object(raw))
        analysis = {
            **payload,
            "source_context": {
                "week_label": clean_week,
                "lookback_weeks": max(1, int(lookback_weeks or 1)),
                "threads_analyzed": len(threads),
                "atoms_analyzed": atoms_seen,
            },
        }
        row = upsert_frontier_analysis(
            connection,
            week_label=clean_week,
            generated_at=_utc_now_iso(),
            model=resolved_model,
            prompt_version=PROMPT_VERSION,
            lookback_weeks=max(1, int(lookback_weeks or 1)),
            threads_analyzed=len(threads),
            atoms_analyzed=atoms_seen,
            executive_brief=payload["executive_brief"],
            what_changed=payload["what_changed"],
            trend_narratives=payload["trend_narratives"],
            study_now=payload["study_now"],
            actions=payload["actions"],
            caveats=payload["caveats"],
            analysis=analysis,
        )
    return _analysis_summary(row)


def format_frontier_analysis_summary(summary: FrontierAnalysisSummary) -> str:
    skipped = " skipped_existing=true" if summary.skipped_existing else ""
    return (
        "Frontier analysis summary\n"
        f"week={summary.week_label} model={summary.model} prompt_version={summary.prompt_version}{skipped}\n"
        f"counts: threads={summary.threads_analyzed} atoms={summary.atoms_analyzed} "
        f"what_changed={summary.what_changed_count} narratives={summary.trend_narrative_count} "
        f"study_now={summary.study_now_count} actions={summary.action_count} caveats={summary.caveat_count}\n"
        f"executive_brief={summary.executive_brief}\n"
    )
