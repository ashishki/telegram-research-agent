from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from assistant.feedback_prompts import FEEDBACK_STRATEGIST_SYSTEM_PROMPT, build_feedback_strategist_prompt
from db.ai_report_feedback import (
    APPLICATION_STATUSES,
    FEEDBACK_TYPES,
    FEEDBACK_CLASSIFICATIONS,
    REPORT_SURFACE_ALIASES,
    REPORT_SURFACES,
    TARGET_TYPES,
    confirm_ai_report_feedback_intake,
    discard_ai_report_feedback_intake,
    fetch_ai_report_feedback_intake,
    record_ai_report_feedback,
    record_ai_report_feedback_intake,
    update_ai_report_feedback_intake_summary,
)
from llm.client import LLMClient


URL_RE = re.compile(r"https?://[^\s<>)]+", re.IGNORECASE)
TARGET_RE = re.compile(r"\b(?:target|ref|item|section)=([A-Za-z0-9_.:@/-]+)", re.IGNORECASE)
SURFACE_RE = re.compile(r"\bsurface=([A-Za-z0-9_-]+)", re.IGNORECASE)
SECTION_RE = re.compile(r"\bsection=([A-Za-z0-9_.:@/-]+)", re.IGNORECASE)
ITEM_RE = re.compile(r"\bitem=([A-Za-z0-9_.:@/-]+)", re.IGNORECASE)
WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")
CHANNEL_RE = re.compile(r"@[A-Za-z0-9_]+")
FEEDBACK_STRATEGIST_CATEGORY = "feedback_intake_strategist"


@dataclass(frozen=True)
class FeedbackProposal:
    feedback_type: str
    target_type: str
    target_ref: str | None = None
    report_surface: str | None = None
    section_id: str | None = None
    item_ref: str | None = None
    feedback_classification: str | None = None
    application_status: str | None = None
    application_reason: str | None = None
    originating_report_item_ref: str | None = None
    source_url: str | None = None
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "feedback_type": self.feedback_type,
            "target_type": self.target_type,
            "target_ref": self.target_ref,
            "report_surface": self.report_surface,
            "section_id": self.section_id,
            "item_ref": self.item_ref,
            "feedback_classification": self.feedback_classification,
            "application_status": self.application_status,
            "application_reason": self.application_reason,
            "originating_report_item_ref": self.originating_report_item_ref,
            "source_url": self.source_url,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class FeedbackSuggestion:
    suggestion_type: str
    text: str
    target_ref: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "suggestion_type": self.suggestion_type,
            "target_ref": self.target_ref,
            "text": self.text,
            "manual_only": True,
            "action": "review_manually",
        }


def _compact(value: str | None) -> str:
    return " ".join((value or "").split())


def _split_feedback_lines(text: str) -> list[str]:
    chunks: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip(" -\t")
        if not stripped:
            continue
        chunks.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+", stripped) if part.strip())
    return chunks or [_compact(text)]


def _extract_target_ref(text: str) -> str | None:
    match = TARGET_RE.search(text)
    if match:
        return match.group(1).strip()
    channel = CHANNEL_RE.search(text)
    if channel:
        return channel.group(0)
    quoted = re.search(r"['\"]([^'\"]{2,80})['\"]", text)
    if quoted:
        return _compact(quoted.group(1))[:80]
    return None


def _extract_surface(text: str, *, target_type: str, feedback_classification: str) -> str:
    match = SURFACE_RE.search(text)
    if match:
        normalized = _normalize_surface(match.group(1))
        if normalized:
            return normalized
    lowered = text.lower()
    for token, surface in (
        ("atlas", "knowledge_atlas"),
        ("knowledge atlas", "knowledge_atlas"),
        ("audit", "audit_explorer"),
        ("radar", "mvp_radar"),
        ("mvp", "mvp_radar"),
        ("reaction", "reaction_personalization"),
        ("personalization", "reaction_personalization"),
        ("project", "project_action"),
        ("action", "project_action"),
        ("visual", "visual"),
        ("chart", "visual"),
        ("graph", "visual"),
        ("brief", "weekly_brief"),
    ):
        if token in lowered:
            return surface
    if target_type in {"action", "experiment"} or feedback_classification in {
        "action_completed",
        "applied_to_project",
    }:
        return "project_action"
    if feedback_classification == "radar_decision_useful":
        return "mvp_radar"
    if feedback_classification == "reaction_effect_missing":
        return "reaction_personalization"
    if feedback_classification in {"confusing_visual", "missing_visual"}:
        return "visual"
    return "weekly_brief"


def _extract_section_id(text: str, *, target_type: str, report_surface: str) -> str:
    match = SECTION_RE.search(text)
    if match:
        return _clean_identifier(match.group(1), default=target_type)
    if report_surface == "project_action":
        return "project_actions"
    if report_surface == "mvp_radar":
        return "mvp_radar"
    if report_surface == "reaction_personalization":
        return "reaction_personalization"
    if report_surface == "knowledge_atlas":
        return "knowledge_atlas"
    if report_surface == "visual":
        return "visuals"
    return target_type if target_type != "report" else "report"


def _extract_item_ref(text: str, *, target_ref: str | None, section_id: str) -> str:
    match = ITEM_RE.search(text)
    if match:
        return _compact(match.group(1))[:200]
    return (target_ref or section_id or "report")[:200]


def _classification_for_feedback(feedback_type: str, lowered: str) -> str:
    clean = _compact(feedback_type).replace("-", "_").lower()
    if clean in FEEDBACK_CLASSIFICATIONS:
        return clean
    if "too long" in lowered or "too-long" in lowered:
        return "too_long"
    if "confusing visual" in lowered or "unclear visual" in lowered:
        return "confusing_visual"
    if "missing visual" in lowered or "needs visual" in lowered:
        return "missing_visual"
    if "duplicate" in lowered:
        return "duplicate_content"
    if "radar" in lowered and ("useful" in lowered or "helpful" in lowered):
        return "radar_decision_useful"
    if "reaction" in lowered and ("missing" in lowered or "did not affect" in lowered):
        return "reaction_effect_missing"
    if "trust" in lowered or "verify" in lowered:
        return "source_trust_correction"
    if clean in {"not_interested", "noise"}:
        return "wrong_priority"
    if clean == "tried":
        return "action_completed"
    return "desired_report_change"


def _application_status_for_classification(feedback_classification: str, feedback_type: str) -> str:
    if feedback_type in {"retraction", "accidental_feedback"}:
        return "rejected"
    if feedback_classification in {
        "too_shallow",
        "too_long",
        "confusing_visual",
        "missing_visual",
        "duplicate_content",
        "reaction_effect_missing",
        "source_trust_correction",
    }:
        return "code_config_required"
    if feedback_classification in {
        "useful",
        "wrong_priority",
        "action_completed",
        "applied_to_project",
        "radar_decision_useful",
    }:
        return "applied"
    if feedback_type == "missed_important_post":
        return "pending"
    return "unchanged"


def _clean_identifier(value: object, *, default: str) -> str:
    clean = _compact(str(value or "")).replace(" ", "_").replace("-", "_")
    return clean[:160] or default


def _normalize_surface(value: object) -> str | None:
    clean = _compact(str(value or "")).replace("-", "_").lower()
    clean = REPORT_SURFACE_ALIASES.get(clean, clean)
    return clean if clean in REPORT_SURFACES else None


def _extract_url(text: str) -> str | None:
    match = URL_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(".,;")


def _proposal(
    *,
    feedback_type: str,
    target_type: str,
    text: str,
    target_ref: str | None = None,
    source_url: str | None = None,
    report_surface: str | None = None,
    section_id: str | None = None,
    item_ref: str | None = None,
    feedback_classification: str | None = None,
) -> FeedbackProposal:
    clean_feedback = feedback_type.replace("-", "_")
    clean_target = target_type.replace("-", "_")
    lowered = text.lower()
    clean_classification = feedback_classification or _classification_for_feedback(clean_feedback, lowered)
    clean_surface = report_surface or _extract_surface(
        text,
        target_type=clean_target,
        feedback_classification=clean_classification,
    )
    clean_target_ref = target_ref or _extract_target_ref(text)
    clean_section = section_id or _extract_section_id(
        text,
        target_type=clean_target,
        report_surface=clean_surface,
    )
    clean_item_ref = item_ref or _extract_item_ref(
        text,
        target_ref=clean_target_ref,
        section_id=clean_section,
    )
    application_status = _application_status_for_classification(clean_classification, clean_feedback)
    return FeedbackProposal(
        feedback_type=clean_feedback,
        target_type=clean_target,
        target_ref=clean_target_ref,
        report_surface=clean_surface,
        section_id=clean_section,
        item_ref=clean_item_ref,
        feedback_classification=clean_classification,
        application_status=application_status,
        application_reason=f"Draft classification {clean_classification} has proposed status {application_status}.",
        originating_report_item_ref=(
            clean_item_ref
            if clean_target in {"action", "experiment"}
            or clean_classification in {"action_completed", "applied_to_project"}
            else None
        ),
        source_url=source_url or _extract_url(text),
        notes=_compact(text)[:500],
    )


def _dedupe_dicts(items: list[dict[str, Any]], key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = tuple(item.get(field) for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _suggestion_type(text: str) -> str | None:
    lowered = text.lower()
    if "project correction" in lowered or "project-correction" in lowered or "project is" in lowered:
        return "project_correction"
    if "source trust" in lowered or "source-trust" in lowered or "trust source" in lowered:
        return "source_trust"
    if "preference" in lowered or "prefer " in lowered or "i prefer" in lowered:
        return "preference"
    if "config" in lowered or "configuration" in lowered or "setting" in lowered:
        return "config"
    if "codex task" in lowered or "codex-task" in lowered or "codex should" in lowered:
        return "codex_task"
    return None


def _heuristic_parse_feedback_text(
    text: str,
    *,
    input_kind: str = "text",
    transcript_text: str | None = None,
    week_label: str | None = None,
) -> dict[str, Any]:
    del week_label
    raw_text = _compact(text)
    if not raw_text:
        raise ValueError("feedback text is required")

    proposals: list[dict[str, Any]] = []
    suggestions: list[dict[str, Any]] = []

    for chunk in _split_feedback_lines(text):
        lowered = chunk.lower()
        compact_chunk = _compact(chunk)

        if "missed" in lowered and ("post" in lowered or "source" in lowered or _extract_url(chunk)):
            url = _extract_url(chunk)
            proposals.append(
                _proposal(
                    feedback_type="missed_important_post",
                    target_type="missed_post",
                    target_ref=url or _extract_target_ref(chunk) or "missed-post",
                    source_url=url,
                    text=chunk,
                ).as_dict()
            )
        if "not interested" in lowered or "not-interesting" in lowered or "not relevant" in lowered:
            proposals.append(
                _proposal(feedback_type="not_interested", target_type="idea_thread", text=chunk).as_dict()
            )
        if "wrong priority" in lowered or "wrong-priority" in lowered or "overpriorit" in lowered:
            proposals.append(
                _proposal(feedback_type="wrong_priority", target_type="idea_thread", text=chunk).as_dict()
            )
        if "too shallow" in lowered or "too-shallow" in lowered or "not deep enough" in lowered:
            proposals.append(
                _proposal(feedback_type="too_shallow", target_type="report_section", text=chunk).as_dict()
            )
        if "too long" in lowered or "too-long" in lowered or "too verbose" in lowered:
            proposals.append(
                _proposal(
                    feedback_type="too_long",
                    target_type="report_section",
                    text=chunk,
                    feedback_classification="too_long",
                ).as_dict()
            )
        if "confusing visual" in lowered or "unclear visual" in lowered or "visual is confusing" in lowered:
            proposals.append(
                _proposal(
                    feedback_type="confusing_visual",
                    target_type="report_section",
                    text=chunk,
                    report_surface="visual",
                    feedback_classification="confusing_visual",
                ).as_dict()
            )
        if "missing visual" in lowered or "needs visual" in lowered or "add a visual" in lowered:
            proposals.append(
                _proposal(
                    feedback_type="missing_visual",
                    target_type="report_section",
                    text=chunk,
                    report_surface="visual",
                    feedback_classification="missing_visual",
                ).as_dict()
            )
        if "duplicate content" in lowered or "duplicate section" in lowered or "repeated content" in lowered:
            proposals.append(
                _proposal(
                    feedback_type="duplicate_content",
                    target_type="report_section",
                    text=chunk,
                    feedback_classification="duplicate_content",
                ).as_dict()
            )
        if "action completed" in lowered or "completed action" in lowered or "done action" in lowered:
            proposals.append(
                _proposal(
                    feedback_type="action_completed",
                    target_type="action",
                    text=chunk,
                    feedback_classification="action_completed",
                ).as_dict()
            )
        if "applied to project" in lowered or "applied-to-project" in lowered or "used in project" in lowered:
            proposals.append(
                _proposal(feedback_type="applied_to_project", target_type="experiment", text=chunk).as_dict()
            )
        elif "tried" in lowered or "tested" in lowered or "ran this" in lowered:
            proposals.append(_proposal(feedback_type="tried", target_type="action", text=chunk).as_dict())
        if "useful" in lowered or "helpful" in lowered or "valuable" in lowered:
            feedback_type = "radar_decision_useful" if "radar" in lowered else "useful"
            target_type = "report" if feedback_type == "radar_decision_useful" else "report_section"
            proposals.append(_proposal(feedback_type=feedback_type, target_type=target_type, text=chunk).as_dict())
        if "reaction effect missing" in lowered or (
            "reaction" in lowered and ("missing" in lowered or "did not affect" in lowered)
        ):
            proposals.append(
                _proposal(
                    feedback_type="reaction_effect_missing",
                    target_type="report_section",
                    text=chunk,
                    report_surface="reaction_personalization",
                    feedback_classification="reaction_effect_missing",
                ).as_dict()
            )
        if "trust too high" in lowered or "overtrusted" in lowered:
            proposals.append(
                _proposal(feedback_type="trust_too_high", target_type="trust_correction", text=chunk).as_dict()
            )
        if "trust too low" in lowered or "undertrusted" in lowered:
            proposals.append(
                _proposal(feedback_type="trust_too_low", target_type="trust_correction", text=chunk).as_dict()
            )
        if "verify first" in lowered or "needs verification" in lowered or "verify before" in lowered:
            proposals.append(
                _proposal(feedback_type="verify_first", target_type="trust_correction", text=chunk).as_dict()
            )

        suggestion = _suggestion_type(chunk)
        if suggestion:
            suggestions.append(
                FeedbackSuggestion(
                    suggestion_type=suggestion,
                    target_ref=_extract_target_ref(chunk),
                    text=compact_chunk[:500],
                ).as_dict()
            )

    return {
        "input_kind": input_kind,
        "raw_text": raw_text,
        "transcript_text": _compact(transcript_text) or None,
        "proposals": _dedupe_dicts(
            proposals,
            (
                "feedback_type",
                "target_type",
                "target_ref",
                "report_surface",
                "section_id",
                "item_ref",
                "feedback_classification",
                "source_url",
                "notes",
            ),
        ),
        "suggestions": _dedupe_dicts(suggestions, ("suggestion_type", "target_ref", "text")),
        "memory_events_proposed": _dedupe_dicts(
            proposals,
            (
                "feedback_type",
                "target_type",
                "target_ref",
                "report_surface",
                "section_id",
                "item_ref",
                "feedback_classification",
                "source_url",
                "notes",
            ),
        ),
        "report_changes_suggested": [
            suggestion for suggestion in suggestions if suggestion.get("suggestion_type") != "codex_task"
        ],
        "codex_tasks_suggested": [
            suggestion for suggestion in suggestions if suggestion.get("suggestion_type") == "codex_task"
        ],
        "clarifying_questions": [],
        "risk_notes": [],
        "confirmation_summary": "",
        "strategy_source": "heuristic",
    }


def parse_feedback_text(
    text: str,
    *,
    input_kind: str = "text",
    transcript_text: str | None = None,
    week_label: str | None = None,
    llm_client: type[LLMClient] = LLMClient,
) -> dict[str, Any]:
    raw_text = _compact(text)
    if not raw_text:
        raise ValueError("feedback text is required")

    try:
        return _parse_feedback_with_strategist(
            raw_text,
            input_kind=input_kind,
            transcript_text=transcript_text,
            week_label=week_label,
            llm_client=llm_client,
        )
    except Exception:
        return _heuristic_parse_feedback_text(
            raw_text,
            input_kind=input_kind,
            transcript_text=transcript_text,
            week_label=week_label,
        )


def _parse_feedback_with_strategist(
    text: str,
    *,
    input_kind: str,
    transcript_text: str | None,
    week_label: str | None,
    llm_client: type[LLMClient],
) -> dict[str, Any]:
    response = llm_client.complete_json(
        prompt=build_feedback_strategist_prompt(week_label=week_label, input_kind=input_kind, text=text),
        system=FEEDBACK_STRATEGIST_SYSTEM_PROMPT,
        category=FEEDBACK_STRATEGIST_CATEGORY,
    )
    if not isinstance(response, dict):
        raise ValueError("feedback strategist response must be a JSON object")

    memory_events = _normalize_memory_events(response.get("memory_events_proposed"))
    report_changes = _normalize_text_suggestions(
        response.get("report_changes_suggested"),
        suggestion_type="report_change",
    )
    codex_tasks = _normalize_codex_tasks(response.get("codex_tasks_suggested"))
    questions = _normalize_text_suggestions(
        response.get("clarifying_questions"),
        suggestion_type="clarifying_question",
    )
    risks = _normalize_text_suggestions(response.get("risk_notes"), suggestion_type="risk_note")
    suggestions = _dedupe_dicts(
        [*report_changes, *codex_tasks, *questions, *risks],
        ("suggestion_type", "target_ref", "text"),
    )

    return {
        "input_kind": input_kind,
        "raw_text": text,
        "transcript_text": _compact(transcript_text) or None,
        "proposals": memory_events,
        "suggestions": suggestions,
        "memory_events_proposed": memory_events,
        "report_changes_suggested": report_changes,
        "codex_tasks_suggested": codex_tasks,
        "clarifying_questions": questions,
        "risk_notes": risks,
        "confirmation_summary": _compact(str(response.get("confirmation_summary") or ""))[:700],
        "strategy_source": "feedback_intake_strategist",
    }


def _normalize_memory_events(value: object) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            continue
        feedback_type = _normalize_allowed(item.get("feedback_type"), FEEDBACK_TYPES)
        target_type = _normalize_allowed(item.get("target_type") or "report", TARGET_TYPES)
        if not feedback_type or not target_type:
            continue
        feedback_classification = _normalize_allowed(
            item.get("feedback_classification") or item.get("classification"),
            FEEDBACK_CLASSIFICATIONS,
        )
        if not feedback_classification:
            feedback_classification = _classification_for_feedback(feedback_type, str(item.get("notes") or "").lower())
        report_surface = _normalize_surface(item.get("report_surface") or item.get("surface"))
        if not report_surface:
            report_surface = _extract_surface(
                str(item.get("notes") or ""),
                target_type=target_type,
                feedback_classification=feedback_classification,
            )
        section_id = _clean_identifier(
            item.get("section_id") or item.get("section") or target_type,
            default=target_type,
        )
        target_ref = _compact(str(item.get("target_ref") or ""))[:120] or None
        item_ref = _compact(str(item.get("item_ref") or item.get("item") or target_ref or section_id))[:200]
        application_status = _normalize_allowed(item.get("application_status"), APPLICATION_STATUSES)
        if not application_status:
            application_status = _application_status_for_classification(feedback_classification, feedback_type)
        notes = _compact(str(item.get("notes") or ""))[:500] or None
        events.append(
            {
                "feedback_type": feedback_type,
                "target_type": target_type,
                "target_ref": target_ref,
                "report_surface": report_surface,
                "section_id": section_id,
                "item_ref": item_ref,
                "feedback_classification": feedback_classification,
                "application_status": application_status,
                "application_reason": _compact(str(item.get("application_reason") or ""))[:500]
                or f"Strategist proposed {feedback_classification} with {application_status} status.",
                "originating_report_item_ref": _compact(
                    str(item.get("originating_report_item_ref") or "")
                )[:200]
                or (
                    item_ref
                    if target_type in {"action", "experiment"}
                    or feedback_classification in {"action_completed", "applied_to_project"}
                    else None
                ),
                "source_url": _clean_url(item.get("source_url")),
                "notes": notes,
            }
        )
    return _dedupe_dicts(
        events,
        (
            "feedback_type",
            "target_type",
            "target_ref",
            "report_surface",
            "section_id",
            "item_ref",
            "feedback_classification",
            "source_url",
            "notes",
        ),
    )


def _normalize_text_suggestions(value: object, *, suggestion_type: str) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for item in _as_list(value):
        target_ref: str | None = None
        if isinstance(item, dict):
            text = _compact(str(item.get("text") or item.get("question") or item.get("note") or ""))
            target_ref = _compact(str(item.get("target_ref") or ""))[:120] or None
        else:
            text = _compact(str(item or ""))
        if not text:
            continue
        suggestions.append(
            {
                "suggestion_type": suggestion_type,
                "target_ref": target_ref,
                "text": text[:500],
                "manual_only": True,
                "action": "review_manually",
            }
        )
    return suggestions


def _normalize_codex_tasks(value: object) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            title = _compact(str(item.get("title") or "Codex task draft"))
            why = _compact(str(item.get("why") or item.get("rationale") or ""))
            text = f"{title}: {why}" if why else title
            task = {
                "suggestion_type": "codex_task",
                "target_ref": _compact(str(item.get("target_ref") or ""))[:120] or None,
                "text": text[:500],
                "manual_only": True,
                "action": "review_manually",
                "title": title[:160],
                "why": why[:500] or None,
                "likely_files": _compact_string_list(item.get("likely_files") or item.get("files")),
                "acceptance": _compact_string_list(item.get("acceptance") or item.get("acceptance_criteria")),
                "verification": _compact_string_list(item.get("verification") or item.get("verification_commands")),
            }
        else:
            text = _compact(str(item or ""))
            if not text:
                continue
            task = {
                "suggestion_type": "codex_task",
                "target_ref": None,
                "text": text[:500],
                "manual_only": True,
                "action": "review_manually",
            }
        tasks.append(task)
    return tasks


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _compact_string_list(value: object, *, limit: int = 6) -> list[str]:
    result: list[str] = []
    for item in _as_list(value):
        clean = _compact(str(item or ""))
        if clean:
            result.append(clean[:200])
    return result[:limit]


def _normalize_allowed(value: object, allowed: set[str]) -> str | None:
    clean = _compact(str(value or "")).replace("-", "_").lower()
    return clean if clean in allowed else None


def _clean_url(value: object) -> str | None:
    clean = _compact(str(value or "")).rstrip(".,;")
    if not clean or not URL_RE.match(clean):
        return None
    return clean[:500]


def format_feedback_confirmation(intake: dict[str, Any]) -> str:
    proposals = intake.get("proposals") or []
    suggestions = intake.get("suggestions") or []
    lines = [
        f"AI workbook feedback draft #{intake['id']}",
        f"week={intake['week_label']} status={intake['status']} input={intake['input_kind']}",
        "",
    ]
    if proposals:
        lines.append("Proposed memory writes:")
        for proposal in proposals:
            target = f"{proposal.get('target_type')}:{proposal.get('target_ref') or 'report'}"
            scoped = (
                f" surface={proposal.get('report_surface') or 'weekly_brief'}"
                f" section={proposal.get('section_id') or 'report'}"
                f" item={proposal.get('item_ref') or proposal.get('target_ref') or 'report'}"
            )
            classification = (
                f" classification={proposal.get('feedback_classification') or 'desired_report_change'}"
                f" application={proposal.get('application_status') or 'unchanged'}"
            )
            source = f" source={proposal.get('source_url')}" if proposal.get("source_url") else ""
            lines.append(f"- {proposal.get('feedback_type')} -> {target}{scoped}{classification}{source}")
    else:
        lines.append("Proposed memory writes: none")

    if suggestions:
        lines.extend(["", "Manual-only suggestions:"])
        for suggestion in suggestions:
            lines.append(f"- {suggestion.get('suggestion_type')}: {suggestion.get('text')}")

    strategist_summary = _compact(str(intake.get("strategist_summary") or ""))
    if strategist_summary:
        lines.extend(["", f"Strategist summary: {strategist_summary[:700]}"])

    lines.extend(
        [
            "",
            "No memory has been written yet.",
            f"Confirm with /feedback_confirm {intake['id']} or discard with /feedback_discard {intake['id']}.",
        ]
    )
    return "\n".join(lines)


def create_feedback_intake(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    text: str,
    input_kind: str = "text",
    report_path: str | None = None,
    recorded_by: str = "operator",
    llm_client: type[LLMClient] = LLMClient,
) -> dict[str, Any]:
    parsed = parse_feedback_text(
        text,
        input_kind=input_kind,
        transcript_text=text if input_kind == "voice_transcript" else None,
        week_label=week_label,
        llm_client=llm_client,
    )
    draft = record_ai_report_feedback_intake(
        connection,
        week_label=week_label,
        input_kind=input_kind,
        raw_text=text,
        transcript_text=parsed.get("transcript_text"),
        proposals=parsed.get("proposals") or [],
        suggestions=parsed.get("suggestions") or [],
        confirmation_summary="",
        report_path=report_path,
        recorded_by=recorded_by,
    )
    summary = format_feedback_confirmation(
        {
            **draft,
            "strategist_summary": parsed.get("confirmation_summary"),
        }
    )
    return update_ai_report_feedback_intake_summary(
        connection,
        intake_id=int(draft["id"]),
        confirmation_summary=summary,
    )


def apply_confirmed_feedback_intake(
    connection: sqlite3.Connection,
    *,
    intake_id: int,
    recorded_by: str = "operator_confirmed",
) -> dict[str, Any]:
    rows = fetch_ai_report_feedback_intake(connection, intake_id=int(intake_id), limit=1)
    if not rows:
        raise ValueError(f"feedback intake not found: {intake_id}")
    intake = rows[0]
    if intake["status"] != "pending":
        raise ValueError(f"feedback intake is {intake['status']}, not pending")

    created_events: list[dict[str, Any]] = []
    try:
        for proposal in intake.get("proposals") or []:
            created_events.append(
                record_ai_report_feedback(
                    connection,
                    week_label=intake["week_label"],
                    report_path=intake.get("report_path"),
                    feedback_type=str(proposal.get("feedback_type") or ""),
                    target_type=str(proposal.get("target_type") or "report"),
                    target_ref=proposal.get("target_ref"),
                    report_surface=proposal.get("report_surface"),
                    section_id=proposal.get("section_id"),
                    item_ref=proposal.get("item_ref"),
                    feedback_classification=proposal.get("feedback_classification"),
                    application_status=proposal.get("application_status"),
                    application_reason=proposal.get("application_reason"),
                    originating_report_item_ref=proposal.get("originating_report_item_ref"),
                    source_url=proposal.get("source_url"),
                    notes=proposal.get("notes"),
                    recorded_by=recorded_by,
                    commit=False,
                )
            )
        confirmed = confirm_ai_report_feedback_intake(connection, int(intake_id), commit=False)
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return {
        "intake": confirmed,
        "created_events": created_events,
        "suggestions": intake.get("suggestions") or [],
    }


def discard_feedback_intake(connection: sqlite3.Connection, *, intake_id: int) -> dict[str, Any]:
    return discard_ai_report_feedback_intake(connection, int(intake_id))
