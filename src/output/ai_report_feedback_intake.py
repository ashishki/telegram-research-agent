from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from db.ai_report_feedback import (
    confirm_ai_report_feedback_intake,
    discard_ai_report_feedback_intake,
    fetch_ai_report_feedback_intake,
    record_ai_report_feedback,
    record_ai_report_feedback_intake,
    update_ai_report_feedback_intake_summary,
)


URL_RE = re.compile(r"https?://[^\s<>)]+", re.IGNORECASE)
TARGET_RE = re.compile(r"\b(?:target|ref|item|section)=([A-Za-z0-9_.:@/-]+)", re.IGNORECASE)
WEEK_RE = re.compile(r"^\d{4}-W\d{2}$")
CHANNEL_RE = re.compile(r"@[A-Za-z0-9_]+")


@dataclass(frozen=True)
class FeedbackProposal:
    feedback_type: str
    target_type: str
    target_ref: str | None = None
    source_url: str | None = None
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "feedback_type": self.feedback_type,
            "target_type": self.target_type,
            "target_ref": self.target_ref,
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
) -> FeedbackProposal:
    return FeedbackProposal(
        feedback_type=feedback_type,
        target_type=target_type,
        target_ref=target_ref or _extract_target_ref(text),
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


def parse_feedback_text(
    text: str,
    *,
    input_kind: str = "text",
    transcript_text: str | None = None,
) -> dict[str, Any]:
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
        if "applied to project" in lowered or "applied-to-project" in lowered or "used in project" in lowered:
            proposals.append(
                _proposal(feedback_type="applied_to_project", target_type="experiment", text=chunk).as_dict()
            )
        elif "tried" in lowered or "tested" in lowered or "ran this" in lowered:
            proposals.append(_proposal(feedback_type="tried", target_type="action", text=chunk).as_dict())
        if "useful" in lowered or "helpful" in lowered or "valuable" in lowered:
            proposals.append(_proposal(feedback_type="useful", target_type="report_section", text=chunk).as_dict())
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
            ("feedback_type", "target_type", "target_ref", "source_url", "notes"),
        ),
        "suggestions": _dedupe_dicts(suggestions, ("suggestion_type", "target_ref", "text")),
    }


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
            source = f" source={proposal.get('source_url')}" if proposal.get("source_url") else ""
            lines.append(f"- {proposal.get('feedback_type')} -> {target}{source}")
    else:
        lines.append("Proposed memory writes: none")

    if suggestions:
        lines.extend(["", "Manual-only suggestions:"])
        for suggestion in suggestions:
            lines.append(f"- {suggestion.get('suggestion_type')}: {suggestion.get('text')}")

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
) -> dict[str, Any]:
    parsed = parse_feedback_text(text, input_kind=input_kind, transcript_text=text if input_kind == "voice_transcript" else None)
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
    summary = format_feedback_confirmation(draft)
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
