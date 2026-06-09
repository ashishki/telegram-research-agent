from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.settings import PROJECT_ROOT
from output.report_quality import (
    ReportQualityFinding,
    load_weekly_quality_facts,
    validate_weekly_artifact_paths,
)
from output.source_trust import explain_source_downrank


DEFAULT_EDITORIAL_MEMORY_ROOT = PROJECT_ROOT / "data" / "output" / "editorial_memory"


@dataclass(frozen=True)
class WeeklyEditorialMemory:
    week_label: str
    markdown: str
    sidecar_path: Path | None
    keep_count: int
    change_count: int
    demote_count: int
    test_count: int


def build_weekly_editorial_memory(
    connection: sqlite3.Connection,
    *,
    week_label: str,
    output_root: Path | str | None = None,
    write_sidecar: bool = True,
) -> WeeklyEditorialMemory:
    clean_week = str(week_label or "").strip()
    if not clean_week:
        raise ValueError("week_label is required")

    keep: list[str] = []
    change: list[str] = []
    demote: list[str] = []
    test_next: list[str] = []

    _add_artifact_feedback(connection, clean_week, keep=keep, change=change)
    _add_usefulness_logs(connection, clean_week, keep=keep, change=change, demote=demote)
    findings = _report_quality_findings(connection, clean_week, output_root=output_root)
    for finding in findings:
        change.append(f"{finding.artifact_type}: {finding.message}")
        test_next.append(f"Re-check {finding.artifact_type}: {finding.message}")
    _add_receipt_warnings(connection, clean_week, change=change, test_next=test_next)
    _add_source_downrank(connection, demote=demote)

    markdown = _render_editorial_memory(
        week_label=clean_week,
        keep=_dedupe(keep),
        change=_dedupe(change),
        demote=_dedupe(demote),
        test_next=_dedupe(test_next),
    )
    sidecar_path = None
    if write_sidecar:
        root = Path(output_root) if output_root is not None else DEFAULT_EDITORIAL_MEMORY_ROOT
        if root.name != "editorial_memory":
            root = root / "editorial_memory"
        root.mkdir(parents=True, exist_ok=True)
        sidecar_path = root / f"{clean_week}.md"
        sidecar_path.write_text(markdown, encoding="utf-8")

    return WeeklyEditorialMemory(
        week_label=clean_week,
        markdown=markdown,
        sidecar_path=sidecar_path,
        keep_count=len(_section_items(markdown, "Keep")),
        change_count=len(_section_items(markdown, "Change")),
        demote_count=len(_section_items(markdown, "Demote")),
        test_count=len(_section_items(markdown, "Test Next Week")),
    )


def build_monthly_editorial_memory_summary(
    connection: sqlite3.Connection,
    *,
    month: str,
    output_root: Path | str | None = None,
) -> list[str]:
    weeks = _weeks_with_editorial_signals(connection, month)
    if not weeks:
        return ["- Editorial memory: no weekly editorial signals"]
    lines = [f"- Editorial memory: {len(weeks)} week(s) with local signals"]
    for week in weeks[:6]:
        memory = build_weekly_editorial_memory(
            connection,
            week_label=week,
            output_root=output_root,
            write_sidecar=False,
        )
        lines.append(
            f"  - {week}: keep={memory.keep_count} change={memory.change_count} "
            f"demote={memory.demote_count} test_next={memory.test_count}"
        )
    if len(weeks) > 6:
        lines.append(f"  - +{len(weeks) - 6} more")
    return lines


def _add_artifact_feedback(
    connection: sqlite3.Connection,
    week_label: str,
    *,
    keep: list[str],
    change: list[str],
) -> None:
    if not _table_exists(connection, "artifact_feedback_logs"):
        return
    rows = connection.execute(
        """
        SELECT artifact_type, feedback, section, item_ref, notes, COUNT(*) AS count
        FROM artifact_feedback_logs
        WHERE week_label = ?
        GROUP BY artifact_type, feedback, section, item_ref, notes
        ORDER BY count DESC, artifact_type ASC, feedback ASC
        LIMIT 12
        """,
        (week_label,),
    ).fetchall()
    for row in rows:
        artifact_type = _cell(row, "artifact_type", 0)
        feedback = _cell(row, "feedback", 1)
        target = _target_label(
            artifact_type,
            _cell(row, "section", 2),
            _cell(row, "item_ref", 3),
        )
        notes = _cell(row, "notes", 4)
        count = int(_cell(row, "count", 5) or 0)
        note = f" note={notes}" if notes else ""
        line = f"{target}: {feedback} x{count}{note}"
        if feedback in {"useful", "decision_impacting"}:
            keep.append(line)
        else:
            change.append(line)


def _add_usefulness_logs(
    connection: sqlite3.Connection,
    week_label: str,
    *,
    keep: list[str],
    change: list[str],
    demote: list[str],
) -> None:
    if not _table_exists(connection, "weekly_usefulness_logs"):
        return
    rows = connection.execute(
        """
        SELECT useful_sections_json, not_useful_sections_json,
               decisions_influenced_json, weak_evidence_notes_json,
               channels_gaining_trust_json, channels_losing_trust_json, notes
        FROM weekly_usefulness_logs
        WHERE week_label = ?
        ORDER BY recorded_at DESC, id DESC
        LIMIT 5
        """,
        (week_label,),
    ).fetchall()
    for row in rows:
        for value in _json_list(_cell(row, "useful_sections_json", 0)):
            keep.append(f"Useful section: {value}")
        for value in _json_list(_cell(row, "decisions_influenced_json", 2)):
            keep.append(f"Decision influenced: {value}")
        for value in _json_list(_cell(row, "channels_gaining_trust_json", 4)):
            keep.append(f"Channel gaining trust: {value}")
        for value in _json_list(_cell(row, "not_useful_sections_json", 1)):
            change.append(f"Not useful section: {value}")
        for value in _json_list(_cell(row, "weak_evidence_notes_json", 3)):
            change.append(f"Weak evidence note: {value}")
        for value in _json_list(_cell(row, "channels_losing_trust_json", 5)):
            demote.append(f"Channel losing trust: {value}")
        notes = _cell(row, "notes", 6)
        if notes:
            change.append(f"Operator note: {notes}")


def _report_quality_findings(
    connection: sqlite3.Connection,
    week_label: str,
    *,
    output_root: Path | str | None,
) -> list[ReportQualityFinding]:
    facts = load_weekly_quality_facts(connection, week_label)
    return validate_weekly_artifact_paths(week_label, facts=facts, output_root=output_root)


def _add_receipt_warnings(
    connection: sqlite3.Connection,
    week_label: str,
    *,
    change: list[str],
    test_next: list[str],
) -> None:
    if not _table_exists(connection, "research_brief_receipts"):
        return
    row = connection.execute(
        """
        SELECT verification_status, fallback_delivery_used, health_flags_json
        FROM research_brief_receipts
        WHERE week_label = ?
        ORDER BY generated_at DESC, id DESC
        LIMIT 1
        """,
        (week_label,),
    ).fetchone()
    if row is None:
        return
    verification_status = _cell(row, "verification_status", 0)
    if verification_status and verification_status not in {"verified", "waived", "passed"}:
        change.append(f"Receipt verification status: {verification_status}")
        test_next.append("Verify Research Brief receipt evidence before delivery")
    if int(_cell(row, "fallback_delivery_used", 1) or 0):
        change.append("Delivery fallback was used for Research Brief")
    for flag in _json_list(_cell(row, "health_flags_json", 2)):
        change.append(f"Receipt health flag: {flag}")


def _add_source_downrank(connection: sqlite3.Connection, *, demote: list[str]) -> None:
    for item in explain_source_downrank(connection, days=30, limit=3):
        reasons = ", ".join(
            f"{reason}={count}" for reason, count in sorted(item["reason_counts"].items())
        )
        demote.append(f"{item['channel']}: {reasons}")


def _render_editorial_memory(
    *,
    week_label: str,
    keep: list[str],
    change: list[str],
    demote: list[str],
    test_next: list[str],
) -> str:
    lines = [
        f"# Weekly Editorial Memory {week_label}",
        "",
        "Source: operator/system-authored local telemetry only. No model-generated judgments.",
        "",
        "## Keep",
        *_bullet_lines(keep, fallback="No keep signals recorded."),
        "",
        "## Change",
        *_bullet_lines(change, fallback="No change signals recorded."),
        "",
        "## Demote",
        *_bullet_lines(demote, fallback="No demotion signals recorded."),
        "",
        "## Test Next Week",
        *_bullet_lines(test_next, fallback="No follow-up tests recorded."),
    ]
    return "\n".join(lines).rstrip() + "\n"


def _weeks_with_editorial_signals(connection: sqlite3.Connection, month: str) -> list[str]:
    weeks: set[str] = set()
    if _table_exists(connection, "weekly_usefulness_logs"):
        weeks.update(
            str(_cell(row, "week_label", 0))
            for row in connection.execute(
                """
                SELECT DISTINCT week_label
                FROM weekly_usefulness_logs
                WHERE substr(recorded_at, 1, 7) = ?
                """,
                (month,),
            ).fetchall()
            if _cell(row, "week_label", 0)
        )
    if _table_exists(connection, "artifact_feedback_logs"):
        weeks.update(
            str(_cell(row, "week_label", 0))
            for row in connection.execute(
                """
                SELECT DISTINCT week_label
                FROM artifact_feedback_logs
                WHERE substr(recorded_at, 1, 7) = ?
                """,
                (month,),
            ).fetchall()
            if _cell(row, "week_label", 0)
        )
    if _table_exists(connection, "research_brief_receipts"):
        weeks.update(
            str(_cell(row, "week_label", 0))
            for row in connection.execute(
                """
                SELECT DISTINCT week_label
                FROM research_brief_receipts
                WHERE substr(generated_at, 1, 7) = ?
                """,
                (month,),
            ).fetchall()
            if _cell(row, "week_label", 0)
        )
    return sorted(weeks)


def _json_list(value: str | None) -> list[Any]:
    try:
        decoded = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return decoded if isinstance(decoded, list) else []


def _target_label(artifact_type: str, section: str | None, item_ref: str | None) -> str:
    parts = [str(artifact_type or "artifact")]
    if section:
        parts.append(str(section))
    if item_ref:
        parts.append(str(item_ref))
    return " / ".join(parts)


def _cell(row: sqlite3.Row | tuple[Any, ...], key: str, index: int) -> Any:
    return row[key] if isinstance(row, sqlite3.Row) else row[index]


def _bullet_lines(values: list[str], *, fallback: str) -> list[str]:
    return [f"- {value}" for value in values] if values else [f"- {fallback}"]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = " ".join(str(value).split())
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _section_items(markdown: str, heading: str) -> list[str]:
    lines = markdown.splitlines()
    marker = f"## {heading}"
    try:
        start = lines.index(marker) + 1
    except ValueError:
        return []
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    return [line for line in lines[start:end] if line.startswith("- ")]


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None
