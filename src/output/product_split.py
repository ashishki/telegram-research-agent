import json
import sqlite3
from typing import Any


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


def _useful_report_weeks(connection: sqlite3.Connection) -> set[str]:
    if not _table_exists(connection, "weekly_usefulness_logs"):
        return set()
    rows = connection.execute(
        """
        SELECT week_label, useful_sections_json, decisions_influenced_json
        FROM weekly_usefulness_logs
        ORDER BY week_label DESC
        """
    ).fetchall()
    weeks: set[str] = set()
    for row in rows:
        week = str(row["week_label"] if isinstance(row, sqlite3.Row) else row[0])
        useful = _json_list(row["useful_sections_json"] if isinstance(row, sqlite3.Row) else row[1])
        decisions = _json_list(row["decisions_influenced_json"] if isinstance(row, sqlite3.Row) else row[2])
        if useful or decisions:
            weeks.add(week)
    return weeks


def _decision_count(connection: sqlite3.Connection) -> int:
    if not _table_exists(connection, "decision_journal"):
        return 0
    row = connection.execute(
        """
        SELECT COUNT(*)
        FROM decision_journal
        WHERE status IN ('acted_on', 'completed')
        """
    ).fetchone()
    return int(row[0] if row else 0)


def _source_intelligence_signal_count(connection: sqlite3.Connection) -> int:
    total = 0
    if _table_exists(connection, "source_observations"):
        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM source_observations
            WHERE COALESCE(acted_on_count, 0) > 0
               OR COALESCE(useful_count, 0) > 0
               OR COALESCE(repeated_claim_count, 0) > 0
               OR COALESCE(low_signal_count, 0) > 0
            """
        ).fetchone()
        total += int(row[0] if row else 0)
    if _table_exists(connection, "artifact_feedback_logs"):
        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM artifact_feedback_logs
            WHERE feedback IN ('useful', 'decision_impacting')
            """
        ).fetchone()
        total += int(row[0] if row else 0)
    return total


def _core_receipt_health(connection: sqlite3.Connection) -> dict[str, int]:
    if not _table_exists(connection, "research_brief_receipts"):
        return {"reviewed": 0, "failed": 0}
    row = connection.execute(
        """
        SELECT
            SUM(CASE WHEN verification_status IN ('verified', 'waived') THEN 1 ELSE 0 END) AS reviewed,
            SUM(CASE WHEN verification_status = 'failed' THEN 1 ELSE 0 END) AS failed
        FROM research_brief_receipts
        """
    ).fetchone()
    if row is None:
        return {"reviewed": 0, "failed": 0}
    reviewed_value = row["reviewed"] if isinstance(row, sqlite3.Row) else row[0]
    failed_value = row["failed"] if isinstance(row, sqlite3.Row) else row[1]
    reviewed = int(reviewed_value or 0)
    failed = int(failed_value or 0)
    return {"reviewed": reviewed, "failed": failed}


def evaluate_product_split_gate(connection: sqlite3.Connection) -> dict[str, Any]:
    useful_weeks = _useful_report_weeks(connection)
    decisions = _decision_count(connection)
    source_intelligence = _source_intelligence_signal_count(connection)
    receipt_health = _core_receipt_health(connection)
    checks = {
        "useful_weekly_reports": {
            "passed": len(useful_weeks) >= 4,
            "observed": len(useful_weeks),
            "required": 4,
        },
        "operator_decisions": {
            "passed": decisions >= 2,
            "observed": decisions,
            "required": 2,
        },
        "source_or_claim_intelligence": {
            "passed": source_intelligence >= 1,
            "observed": source_intelligence,
            "required": 1,
        },
        "core_receipt_health": {
            "passed": receipt_health["reviewed"] >= 1 and receipt_health["failed"] == 0,
            "reviewed": receipt_health["reviewed"],
            "failed": receipt_health["failed"],
            "required_reviewed": 1,
        },
    }
    decision = "go" if all(check["passed"] for check in checks.values()) else "no_go"
    return {
        "decision": decision,
        "useful_weeks": sorted(useful_weeks),
        "checks": checks,
    }


def format_product_split_gate(evaluation: dict[str, Any]) -> str:
    lines = [
        "Product Split Gate",
        f"decision={evaluation['decision']}",
        f"useful_weeks={', '.join(evaluation.get('useful_weeks') or []) or 'none'}",
        "checks:",
    ]
    for name, check in evaluation["checks"].items():
        details = " ".join(f"{key}={value}" for key, value in check.items() if key != "passed")
        lines.append(f"  {name}: {'pass' if check['passed'] else 'fail'} {details}")
    if evaluation["decision"] != "go":
        lines.append("recommendation=keep Telegram Channel Intelligence inside the private assistant for now")
    else:
        lines.append("recommendation=create a separate product plan before adding public UI")
    return "\n".join(lines) + "\n"
