import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from output.cost_guardrails import evaluate_llm_cost_guardrails, format_cost_guardrail_lines
from output.report_quality import WeeklyReportFacts, validate_weekly_artifact_paths


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def current_month_label() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _validate_month(month: str | None) -> str:
    label = str(month or current_month_label()).strip()
    if not MONTH_RE.match(label):
        raise ValueError("month must use YYYY-MM format")
    return label


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


def _json_list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _reaction_summary(connection: sqlite3.Connection, month: str) -> list[str]:
    if not _table_exists(connection, "reaction_sync_state"):
        return ["- Reaction sync: table missing"]
    rows = connection.execute(
        """
        SELECT emoji, action_key, COUNT(*) AS count
        FROM reaction_sync_state
        WHERE source = 'telegram_reaction'
          AND substr(applied_at, 1, 7) = ?
        GROUP BY emoji, action_key
        ORDER BY count DESC, emoji ASC
        LIMIT 8
        """,
        (month,),
    ).fetchall()
    total = sum(int(row["count"] if isinstance(row, sqlite3.Row) else row[2]) for row in rows)
    lines = [f"- Reaction sync: {total} applied actions"]
    if not rows:
        lines.append("  - none")
        return lines
    for row in rows:
        emoji = row["emoji"] if isinstance(row, sqlite3.Row) else row[0]
        action_key = row["action_key"] if isinstance(row, sqlite3.Row) else row[1]
        count = row["count"] if isinstance(row, sqlite3.Row) else row[2]
        lines.append(f"  - {emoji} {action_key}: {int(count)}")
    return lines


def _decision_summary(connection: sqlite3.Connection, month: str) -> list[str]:
    if not _table_exists(connection, "decision_journal"):
        return ["- Inline decisions: table missing"]
    rows = connection.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM decision_journal
        WHERE recorded_by = 'telegram_button'
          AND substr(recorded_at, 1, 7) = ?
        GROUP BY status
        ORDER BY count DESC, status ASC
        """,
        (month,),
    ).fetchall()
    total = sum(int(row["count"] if isinstance(row, sqlite3.Row) else row[1]) for row in rows)
    lines = [f"- Inline decisions: {total}"]
    if not rows:
        lines.append("  - none")
        return lines
    for row in rows:
        status = row["status"] if isinstance(row, sqlite3.Row) else row[0]
        count = row["count"] if isinstance(row, sqlite3.Row) else row[1]
        lines.append(f"  - {status}: {int(count)}")
    return lines


def _usefulness_summary(connection: sqlite3.Connection, month: str) -> list[str]:
    if not _table_exists(connection, "weekly_usefulness_logs"):
        return ["- Weekly usefulness: table missing"]
    rows = connection.execute(
        """
        SELECT week_label, useful_sections_json, not_useful_sections_json,
               decisions_influenced_json, weak_evidence_notes_json,
               channels_gaining_trust_json, channels_losing_trust_json
        FROM weekly_usefulness_logs
        WHERE substr(recorded_at, 1, 7) = ?
        ORDER BY recorded_at ASC, id ASC
        """,
        (month,),
    ).fetchall()
    useful = not_useful = decisions = weak = trust_up = trust_down = 0
    weeks: list[str] = []
    for row in rows:
        weeks.append(str(row["week_label"] if isinstance(row, sqlite3.Row) else row[0]))
        useful += len(_json_list(row["useful_sections_json"] if isinstance(row, sqlite3.Row) else row[1]))
        not_useful += len(_json_list(row["not_useful_sections_json"] if isinstance(row, sqlite3.Row) else row[2]))
        decisions += len(_json_list(row["decisions_influenced_json"] if isinstance(row, sqlite3.Row) else row[3]))
        weak += len(_json_list(row["weak_evidence_notes_json"] if isinstance(row, sqlite3.Row) else row[4]))
        trust_up += len(_json_list(row["channels_gaining_trust_json"] if isinstance(row, sqlite3.Row) else row[5]))
        trust_down += len(_json_list(row["channels_losing_trust_json"] if isinstance(row, sqlite3.Row) else row[6]))
    return [
        f"- Weekly usefulness logs: {len(rows)} weeks={', '.join(sorted(set(weeks))) if weeks else 'none'}",
        f"  - useful_sections={useful} not_useful_sections={not_useful} decisions={decisions}",
        f"  - weak_evidence={weak} trust_up={trust_up} trust_down={trust_down}",
    ]


def _cost_summary(connection: sqlite3.Connection, month: str) -> list[str]:
    if not _table_exists(connection, "llm_usage"):
        return ["- LLM cost: table missing"]
    row = connection.execute(
        """
        SELECT COUNT(*) AS calls,
               COALESCE(SUM(input_tokens), 0) AS input_tokens,
               COALESCE(SUM(output_tokens), 0) AS output_tokens,
               COALESCE(SUM(cost_usd), 0.0) AS cost_usd,
               COALESCE(SUM(est_cost_usd), 0.0) AS est_cost_usd
        FROM llm_usage
        WHERE substr(called_at, 1, 7) = ?
        """,
        (month,),
    ).fetchone()
    calls = int(row["calls"] if isinstance(row, sqlite3.Row) else row[0])
    input_tokens = int(row["input_tokens"] if isinstance(row, sqlite3.Row) else row[1])
    output_tokens = int(row["output_tokens"] if isinstance(row, sqlite3.Row) else row[2])
    cost_usd = float(row["cost_usd"] if isinstance(row, sqlite3.Row) else row[3])
    est_cost_usd = float(row["est_cost_usd"] if isinstance(row, sqlite3.Row) else row[4])
    return [
        f"- LLM usage: calls={calls} input_tokens={input_tokens} output_tokens={output_tokens}",
        f"  - cost_usd=${cost_usd:.6f} est_cost_usd=${est_cost_usd:.6f}",
        *format_cost_guardrail_lines(
            evaluate_llm_cost_guardrails(connection, month=month)
        ),
    ]


def _receipt_summary(connection: sqlite3.Connection, month: str) -> list[str]:
    if not _table_exists(connection, "research_brief_receipts"):
        return ["- Research Brief receipts: table missing"]
    rows = connection.execute(
        """
        SELECT week_label, fallback_delivery_used, health_flags_json
        FROM research_brief_receipts
        WHERE substr(generated_at, 1, 7) = ?
        """,
        (month,),
    ).fetchall()
    empty_or_low = 0
    fallback = 0
    weeks: list[str] = []
    for row in rows:
        weeks.append(str(row["week_label"] if isinstance(row, sqlite3.Row) else row[0]))
        fallback += 1 if int(row["fallback_delivery_used"] if isinstance(row, sqlite3.Row) else row[1] or 0) else 0
        flags = _json_list(row["health_flags_json"] if isinstance(row, sqlite3.Row) else row[2])
        if "empty_week_alert" in flags or "low_signal_alert" in flags:
            empty_or_low += 1
    return [
        f"- Research Brief receipts: {len(rows)} weeks={', '.join(sorted(set(weeks))) if weeks else 'none'}",
        f"  - empty_or_low_signal={empty_or_low} fallback_delivery={fallback}",
    ]


def _artifact_feedback_summary(connection: sqlite3.Connection, month: str) -> list[str]:
    if not _table_exists(connection, "artifact_feedback_logs"):
        return ["- Artifact feedback: table missing"]
    rows = connection.execute(
        """
        SELECT feedback, COUNT(*) AS count
        FROM artifact_feedback_logs
        WHERE substr(recorded_at, 1, 7) = ?
        GROUP BY feedback
        ORDER BY count DESC, feedback ASC
        """,
        (month,),
    ).fetchall()
    total = sum(int(row["count"] if isinstance(row, sqlite3.Row) else row[1]) for row in rows)
    lines = [f"- Artifact feedback: {total}"]
    if not rows:
        lines.append("  - none")
        return lines
    for row in rows:
        feedback = row["feedback"] if isinstance(row, sqlite3.Row) else row[0]
        count = row["count"] if isinstance(row, sqlite3.Row) else row[1]
        lines.append(f"  - {feedback}: {int(count)}")
    return lines


def _report_quality_summary(
    connection: sqlite3.Connection,
    month: str,
    *,
    report_output_root: Path | str | None = None,
) -> list[str]:
    if not _table_exists(connection, "quality_metrics"):
        return ["- Report quality: quality_metrics table missing"]
    rows = connection.execute(
        """
        SELECT week_label, total_posts, strong_count, watch_count, cultural_count,
               noise_count, project_match_count, output_word_count
        FROM quality_metrics
        WHERE substr(computed_at, 1, 7) = ?
        ORDER BY week_label ASC
        """,
        (month,),
    ).fetchall()
    if not rows:
        return ["- Report quality: no quality metric weeks"]

    findings = []
    for row in rows:
        if isinstance(row, sqlite3.Row):
            facts = WeeklyReportFacts(
                week_label=str(row["week_label"] or ""),
                post_count=int(row["total_posts"] or 0),
                strong_count=int(row["strong_count"] or 0),
                watch_count=int(row["watch_count"] or 0),
                cultural_count=int(row["cultural_count"] or 0),
                noise_count=int(row["noise_count"] or 0),
                project_match_count=int(row["project_match_count"] or 0),
                output_word_count=int(row["output_word_count"] or 0),
            )
        else:
            facts = WeeklyReportFacts(
                week_label=str(row[0] or ""),
                post_count=int(row[1] or 0),
                strong_count=int(row[2] or 0),
                watch_count=int(row[3] or 0),
                cultural_count=int(row[4] or 0),
                noise_count=int(row[5] or 0),
                project_match_count=int(row[6] or 0),
                output_word_count=int(row[7] or 0),
            )
        findings.extend(
            validate_weekly_artifact_paths(
                facts.week_label or "",
                facts=facts,
                output_root=report_output_root,
            )
        )

    critical_count = sum(1 for finding in findings if finding.severity == "critical")
    warning_count = sum(1 for finding in findings if finding.severity == "warning")
    lines = [
        f"- Report quality: {len(findings)} findings across {len(rows)} week(s)",
        f"  - critical={critical_count} warning={warning_count}",
    ]
    for finding in findings[:6]:
        hint = f" ({finding.line_hint})" if finding.line_hint else ""
        lines.append(f"  - {finding.severity} {finding.artifact_type}: {finding.message}{hint}")
    if len(findings) > 6:
        lines.append(f"  - +{len(findings) - 6} more")
    return lines


def build_monthly_operator_report(
    connection: sqlite3.Connection,
    *,
    month: str | None = None,
    report_output_root: Path | str | None = None,
) -> str:
    clean_month = _validate_month(month)
    lines = [
        f"# Operator Report {clean_month}",
        "",
        "## Feedback",
        *_reaction_summary(connection, clean_month),
        *_decision_summary(connection, clean_month),
        *_usefulness_summary(connection, clean_month),
        *_artifact_feedback_summary(connection, clean_month),
        "",
        "## Cost",
        *_cost_summary(connection, clean_month),
        "",
        "## Delivery And Receipt Health",
        *_receipt_summary(connection, clean_month),
        "",
        "## Report Quality",
        *_report_quality_summary(connection, clean_month, report_output_root=report_output_root),
    ]
    return "\n".join(lines).rstrip() + "\n"
