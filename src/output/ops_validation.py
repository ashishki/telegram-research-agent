import inspect
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from bot import bot as bot_module


def _cutoff_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=max(1, int(days or 14)))).isoformat().replace("+00:00", "Z")


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


def validate_reaction_sync(connection: sqlite3.Connection, *, days: int = 14) -> dict[str, Any]:
    cutoff = _cutoff_iso(days)
    if not _table_exists(connection, "reaction_sync_state"):
        return {
            "name": "reaction_sync",
            "status": "failed",
            "details": {"reason": "reaction_sync_state table missing"},
        }
    row = connection.execute(
        """
        SELECT COUNT(*) AS applied_count,
               MAX(applied_at) AS latest_applied_at
        FROM reaction_sync_state
        WHERE source = 'telegram_reaction'
          AND applied_at >= ?
        """,
        (cutoff,),
    ).fetchone()
    applied_count = int(row["applied_count"] if isinstance(row, sqlite3.Row) else row[0] or 0)
    latest_applied_at = row["latest_applied_at"] if isinstance(row, sqlite3.Row) else row[1]
    status = "passed" if applied_count > 0 else "needs_live_event"
    return {
        "name": "reaction_sync",
        "status": status,
        "details": {
            "days": max(1, int(days or 14)),
            "applied_count": applied_count,
            "latest_applied_at": latest_applied_at or "none",
        },
    }


def validate_callback_dispatch(connection: sqlite3.Connection, *, days: int = 14) -> dict[str, Any]:
    cutoff = _cutoff_iso(days)
    source = inspect.getsource(bot_module._telegram_get_updates)
    callback_update_enabled = "callback_query" in source
    if not _table_exists(connection, "decision_journal"):
        return {
            "name": "callback_dispatch",
            "status": "failed",
            "details": {
                "reason": "decision_journal table missing",
                "callback_update_enabled": callback_update_enabled,
            },
        }
    row = connection.execute(
        """
        SELECT COUNT(*) AS callback_decisions,
               MAX(recorded_at) AS latest_recorded_at
        FROM decision_journal
        WHERE recorded_by = 'telegram_button'
          AND recorded_at >= ?
        """,
        (cutoff,),
    ).fetchone()
    callback_decisions = int(row["callback_decisions"] if isinstance(row, sqlite3.Row) else row[0] or 0)
    latest_recorded_at = row["latest_recorded_at"] if isinstance(row, sqlite3.Row) else row[1]
    status = "passed" if callback_update_enabled and callback_decisions > 0 else "needs_live_event"
    return {
        "name": "callback_dispatch",
        "status": status,
        "details": {
            "days": max(1, int(days or 14)),
            "callback_update_enabled": callback_update_enabled,
            "callback_decisions": callback_decisions,
            "latest_recorded_at": latest_recorded_at or "none",
        },
    }


def validate_ops(connection: sqlite3.Connection, *, kind: str = "all", days: int = 14) -> list[dict[str, Any]]:
    if kind == "reaction-sync":
        return [validate_reaction_sync(connection, days=days)]
    if kind == "callbacks":
        return [validate_callback_dispatch(connection, days=days)]
    return [
        validate_reaction_sync(connection, days=days),
        validate_callback_dispatch(connection, days=days),
    ]


def format_ops_validation(results: list[dict[str, Any]]) -> str:
    lines = ["OPS Validation"]
    for result in results:
        lines.append(f"{result['name']}: {result['status']}")
        for key, value in result.get("details", {}).items():
            lines.append(f"  {key}={value}")
    return "\n".join(lines) + "\n"
