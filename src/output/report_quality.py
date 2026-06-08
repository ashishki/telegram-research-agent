"""Deterministic quality checks for weekly reader-facing artifacts."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from config.settings import PROJECT_ROOT


SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "output"
DEFAULT_WORD_BUDGETS = {
    "research_brief": 1600,
    "study_plan": 1200,
    "project_insights": 900,
    "implementation_ideas": 1200,
    "mvp_weekly": 1400,
}

MATCHES_TRACE_RE = re.compile(r"\b(?:key takeaway:\s*)?matches:\s*[^.\n]+", re.IGNORECASE)
NO_TELEGRAM_SIGNALS_RE = re.compile(
    r"\bno\s+(?:telegram\s+)?signals?\s+(?:this\s+week|were\s+found|available|identified)\b"
    r"|\bno\s+telegram\s+signals?\b",
    re.IGNORECASE,
)
NO_PROJECT_INSIGHTS_RE = re.compile(
    r"\bno\s+project\s+insights?\s+(?:were\s+)?(?:identified|found|available|this\s+week)\b",
    re.IGNORECASE,
)
MISSING_EVIDENCE_RE = re.compile(
    r"\b(?:no|missing|insufficient|without)\s+(?:independent\s+|external\s+|source\s+)?(?:evidence|sources?)\b",
    re.IGNORECASE,
)
HIGH_CONFIDENCE_RE = re.compile(r"\bconfidence\s*:\s*(?:high|strong|medium)\b", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class WeeklyReportFacts:
    week_label: str | None = None
    post_count: int | None = None
    strong_count: int | None = None
    watch_count: int | None = None
    cultural_count: int | None = None
    noise_count: int | None = None
    project_match_count: int | None = None
    output_word_count: int | None = None

    @property
    def actionable_signal_count(self) -> int:
        return max(0, int(self.strong_count or 0)) + max(0, int(self.watch_count or 0))


@dataclass(frozen=True)
class ReportQualityFinding:
    severity: str
    artifact_type: str
    message: str
    line_hint: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "severity": self.severity,
            "artifact_type": self.artifact_type,
            "message": self.message,
            "line_hint": self.line_hint,
        }


def coerce_weekly_facts(facts: WeeklyReportFacts | Mapping[str, Any] | None) -> WeeklyReportFacts:
    if facts is None:
        return WeeklyReportFacts()
    if isinstance(facts, WeeklyReportFacts):
        return facts

    def _int_value(name: str) -> int | None:
        value = facts.get(name)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    return WeeklyReportFacts(
        week_label=str(facts.get("week_label") or "").strip() or None,
        post_count=_int_value("post_count") if "post_count" in facts else _int_value("total_posts"),
        strong_count=_int_value("strong_count"),
        watch_count=_int_value("watch_count"),
        cultural_count=_int_value("cultural_count"),
        noise_count=_int_value("noise_count"),
        project_match_count=_int_value("project_match_count"),
        output_word_count=_int_value("output_word_count"),
    )


def load_weekly_quality_facts(connection: sqlite3.Connection, week_label: str) -> WeeklyReportFacts:
    if not _table_exists(connection, "quality_metrics"):
        return WeeklyReportFacts(week_label=week_label)
    row = connection.execute(
        """
        SELECT week_label, total_posts, strong_count, watch_count, cultural_count,
               noise_count, project_match_count, output_word_count
        FROM quality_metrics
        WHERE week_label = ?
        LIMIT 1
        """,
        (week_label,),
    ).fetchone()
    if row is None:
        return WeeklyReportFacts(week_label=week_label)
    return _facts_from_quality_row(row)


def validate_artifact(
    artifact_type: str,
    content_md: str | None,
    *,
    facts: WeeklyReportFacts | Mapping[str, Any] | None = None,
    word_budget: int | None = None,
) -> list[ReportQualityFinding]:
    clean_type = str(artifact_type or "unknown").strip() or "unknown"
    content = str(content_md or "")
    weekly_facts = coerce_weekly_facts(facts)
    findings: list[ReportQualityFinding] = []

    if not content.strip():
        return findings

    findings.extend(_find_internal_match_traces(clean_type, content))

    if clean_type == "research_brief":
        findings.extend(_validate_research_brief_structure(content))
    if clean_type == "study_plan":
        findings.extend(_validate_study_plan(content, weekly_facts))

    findings.extend(_validate_source_confidence(clean_type, content))
    findings.extend(_validate_word_budget(clean_type, content, word_budget=word_budget))
    return findings


def validate_weekly_artifacts(
    *,
    week_label: str | None = None,
    digest_md: str | None = None,
    study_plan_md: str | None = None,
    project_insights_md: str | None = None,
    facts: WeeklyReportFacts | Mapping[str, Any] | None = None,
) -> list[ReportQualityFinding]:
    weekly_facts = coerce_weekly_facts(facts)
    findings: list[ReportQualityFinding] = []

    findings.extend(validate_artifact("research_brief", digest_md, facts=weekly_facts))
    findings.extend(validate_artifact("study_plan", study_plan_md, facts=weekly_facts))
    findings.extend(validate_artifact("project_insights", project_insights_md, facts=weekly_facts))

    if project_insights_report_is_empty(project_insights_md) and digest_has_project_insights(digest_md):
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_CRITICAL,
                artifact_type="project_insights",
                message=(
                    "Project Insights artifact says no insights, but the Research Brief "
                    "contains reader-facing project insights"
                ),
                line_hint=_first_matching_line(project_insights_md or "", NO_PROJECT_INSIGHTS_RE),
            )
        )

    return findings


def validate_weekly_artifact_paths(
    week_label: str,
    *,
    facts: WeeklyReportFacts | Mapping[str, Any] | None = None,
    output_root: Path | str | None = None,
) -> list[ReportQualityFinding]:
    texts = load_weekly_artifact_texts(week_label, output_root=output_root)
    return validate_weekly_artifacts(
        week_label=week_label,
        digest_md=texts.get("digest_md"),
        study_plan_md=texts.get("study_plan_md"),
        project_insights_md=texts.get("project_insights_md"),
        facts=facts,
    )


def load_weekly_artifact_texts(
    week_label: str,
    *,
    output_root: Path | str | None = None,
) -> dict[str, str | None]:
    root = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    paths = {
        "digest_md": root / "digests" / f"{week_label}.md",
        "study_plan_md": root / "study_plans" / f"{week_label}.md",
        "project_insights_md": root / "project_insights" / f"{week_label}.md",
    }
    texts: dict[str, str | None] = {}
    for key, path in paths.items():
        try:
            texts[key] = path.read_text(encoding="utf-8") if path.exists() else None
        except OSError:
            texts[key] = None
    return texts


def digest_has_project_insights(content_md: str | None) -> bool:
    section = _extract_heading_section(content_md or "", "Project Insights")
    if not section:
        return False
    if NO_PROJECT_INSIGHTS_RE.search(section):
        return False
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Source:") or line.lower().startswith("key takeaway:"):
            continue
        if line.startswith("**") or line.startswith("- "):
            return True
    return False


def project_insights_report_is_empty(content_md: str | None) -> bool:
    content = str(content_md or "")
    if not content.strip():
        return False
    if NO_PROJECT_INSIGHTS_RE.search(content):
        return True
    section = _extract_heading_section(content, "Project Insights")
    if section is None:
        return False
    substantive = [
        line.strip()
        for line in section.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return not substantive


def format_findings_for_notification(
    findings: list[ReportQualityFinding],
    *,
    limit: int = 2,
) -> str | None:
    critical = [finding for finding in findings if finding.severity == SEVERITY_CRITICAL]
    if not critical:
        return None
    messages = "; ".join(f"{item.artifact_type}: {item.message}" for item in critical[:limit])
    suffix = "" if len(critical) <= limit else f"; +{len(critical) - limit} more"
    return f"Report quality warning: {len(critical)} critical finding(s). {messages}{suffix}"[:500]


def format_finding_for_log(finding: ReportQualityFinding) -> str:
    hint = f" ({finding.line_hint})" if finding.line_hint else ""
    return f"{finding.severity} {finding.artifact_type}: {finding.message}{hint}"


def _find_internal_match_traces(artifact_type: str, content: str) -> list[ReportQualityFinding]:
    findings: list[ReportQualityFinding] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if MATCHES_TRACE_RE.search(line):
            findings.append(
                ReportQualityFinding(
                    severity=SEVERITY_WARNING,
                    artifact_type=artifact_type,
                    message="Internal project-matching trace is visible as reader-facing content",
                    line_hint=_line_hint(line_number, line),
                )
            )
    return findings


def _validate_research_brief_structure(content: str) -> list[ReportQualityFinding]:
    findings: list[ReportQualityFinding] = []
    first_heading = _first_heading(content)
    if first_heading is None or _normalize_heading(first_heading[1]) != "decision brief":
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_WARNING,
                artifact_type="research_brief",
                message="Research Brief does not start with Decision Brief",
                line_hint=_line_hint(first_heading[0], first_heading[2]) if first_heading else None,
            )
        )

    what_changed = _find_heading(content, "What Changed")
    if what_changed is None:
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_WARNING,
                artifact_type="research_brief",
                message="Research Brief is missing What Changed near the top",
                line_hint=None,
            )
        )
        return findings

    detailed_headings = (
        "project insights",
        "additional signals",
        "source map",
        "your projects",
        "macro context",
    )
    detailed_positions = [
        line_number
        for line_number, title, _line in _iter_headings(content)
        if _normalize_heading(title) in detailed_headings
    ]
    if what_changed[0] > 40 or any(line_number < what_changed[0] for line_number in detailed_positions):
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_WARNING,
                artifact_type="research_brief",
                message="What Changed is buried after detailed sections",
                line_hint=_line_hint(what_changed[0], what_changed[2]),
            )
        )
    return findings


def _validate_study_plan(content: str, facts: WeeklyReportFacts) -> list[ReportQualityFinding]:
    if facts.actionable_signal_count <= 0:
        return []
    line_hint = _first_matching_line(content, NO_TELEGRAM_SIGNALS_RE)
    if not line_hint:
        return []
    return [
        ReportQualityFinding(
            severity=SEVERITY_CRITICAL,
            artifact_type="study_plan",
            message=(
                "Study Plan says no Telegram signals while the digest facts show "
                f"{facts.actionable_signal_count} strong/watch signals"
            ),
            line_hint=line_hint,
        )
    ]


def _validate_source_confidence(artifact_type: str, content: str) -> list[ReportQualityFinding]:
    findings: list[ReportQualityFinding] = []
    if HIGH_CONFIDENCE_RE.search(content) and MISSING_EVIDENCE_RE.search(content):
        findings.append(
            ReportQualityFinding(
                severity=SEVERITY_WARNING,
                artifact_type=artifact_type,
                message="Confidence wording conflicts with missing or insufficient evidence",
                line_hint=_first_matching_line(content, HIGH_CONFIDENCE_RE),
            )
        )

    for heading in ("Evidence", "Source Mix", "Confidence"):
        section = _extract_heading_section(content, heading)
        if section is None:
            continue
        if not _has_substantive_section_text(section):
            findings.append(
                ReportQualityFinding(
                    severity=SEVERITY_WARNING,
                    artifact_type=artifact_type,
                    message=f"{heading} section is present but empty",
                    line_hint=_line_hint_for_heading(content, heading),
                )
            )
    return findings


def _validate_word_budget(
    artifact_type: str,
    content: str,
    *,
    word_budget: int | None = None,
) -> list[ReportQualityFinding]:
    budget = word_budget or DEFAULT_WORD_BUDGETS.get(artifact_type, 1200)
    word_count = len(content.split())
    if word_count <= budget:
        return []
    if _has_summary_layer(content):
        return []
    return [
        ReportQualityFinding(
            severity=SEVERITY_WARNING,
            artifact_type=artifact_type,
            message=f"Artifact is {word_count} words without an explicit summary or decision layer",
            line_hint=None,
        )
    ]


def _has_summary_layer(content: str) -> bool:
    summary_headings = {
        "decision brief",
        "executive summary",
        "summary",
        "candidate dossier",
        "actions this week",
    }
    first = _first_heading(content)
    if first is None:
        return False
    normalized = _normalize_heading(first[1])
    if normalized in summary_headings or normalized.startswith("candidate dossier"):
        return True
    return any(_normalize_heading(title) in summary_headings for _line_number, title, _line in _iter_headings(content))


def _extract_heading_section(content: str, heading: str) -> str | None:
    target = _normalize_heading(heading)
    lines = content.splitlines()
    start_index: int | None = None
    start_level = 0
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line.strip())
        if not match:
            continue
        normalized = _normalize_heading(match.group(2))
        if normalized == target or normalized.startswith(f"{target} "):
            start_index = index + 1
            start_level = len(match.group(1))
            break
    if start_index is None:
        return None
    end_index = len(lines)
    for index in range(start_index, len(lines)):
        match = HEADING_RE.match(lines[index].strip())
        if match and len(match.group(1)) <= start_level:
            end_index = index
            break
    return "\n".join(lines[start_index:end_index]).strip()


def _has_substantive_section_text(section: str) -> bool:
    stripped = section.strip()
    if not stripped:
        return False
    low_signal_placeholders = {
        "none",
        "n/a",
        "not available",
        "todo",
        "tbd",
    }
    return stripped.lower() not in low_signal_placeholders


def _iter_headings(content: str) -> list[tuple[int, str, str]]:
    headings: list[tuple[int, str, str]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        match = HEADING_RE.match(line.strip())
        if match:
            headings.append((line_number, match.group(2).strip(), line.strip()))
    return headings


def _first_heading(content: str) -> tuple[int, str, str] | None:
    headings = _iter_headings(content)
    return headings[0] if headings else None


def _find_heading(content: str, heading: str) -> tuple[int, str, str] | None:
    target = _normalize_heading(heading)
    for line_number, title, raw_line in _iter_headings(content):
        normalized = _normalize_heading(title)
        if normalized == target or target in normalized:
            return (line_number, title, raw_line)
    return None


def _normalize_heading(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", str(value).strip().lower()).strip()


def _first_matching_line(content: str, pattern: re.Pattern[str]) -> str | None:
    for line_number, line in enumerate(content.splitlines(), start=1):
        if pattern.search(line):
            return _line_hint(line_number, line)
    return None


def _line_hint_for_heading(content: str, heading: str) -> str | None:
    found = _find_heading(content, heading)
    if found is None:
        return None
    return _line_hint(found[0], found[2])


def _line_hint(line_number: int, line: str) -> str:
    compact = " ".join(str(line).split())
    if len(compact) > 140:
        compact = compact[:137] + "..."
    return f"line {line_number}: {compact}"


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


def _facts_from_quality_row(row: Any) -> WeeklyReportFacts:
    def _get(name: str, index: int) -> Any:
        if isinstance(row, sqlite3.Row):
            return row[name]
        try:
            return row[index]
        except (IndexError, TypeError):
            return None

    return WeeklyReportFacts(
        week_label=str(_get("week_label", 0) or "") or None,
        post_count=_coerce_int(_get("total_posts", 1)),
        strong_count=_coerce_int(_get("strong_count", 2)),
        watch_count=_coerce_int(_get("watch_count", 3)),
        cultural_count=_coerce_int(_get("cultural_count", 4)),
        noise_count=_coerce_int(_get("noise_count", 5)),
        project_match_count=_coerce_int(_get("project_match_count", 6)),
        output_word_count=_coerce_int(_get("output_word_count", 7)),
    )


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
