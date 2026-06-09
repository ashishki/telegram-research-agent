from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass


DEFAULT_WEEKLY_BUDGET_USD = 0.25
DEFAULT_SPIKE_RATIO = 2.0
WEEKLY_BUDGET_ENV = "LLM_WEEKLY_COST_BUDGET_USD"
SPIKE_RATIO_ENV = "LLM_WEEKLY_COST_SPIKE_RATIO"


@dataclass(frozen=True)
class CategoryCost:
    category: str
    call_count: int
    cost_usd: float


@dataclass(frozen=True)
class CostGuardrailReport:
    status: str
    weekly_budget_usd: float
    spike_ratio_threshold: float
    latest_week: str | None
    latest_week_cost_usd: float
    previous_week: str | None
    previous_week_cost_usd: float
    highest_cost_category: CategoryCost | None
    category_costs: tuple[CategoryCost, ...]
    warnings: tuple[str, ...]
    suggested_actions: tuple[str, ...]


def evaluate_llm_cost_guardrails(
    connection: sqlite3.Connection,
    *,
    month: str | None = None,
    weekly_budget_usd: float | None = None,
    spike_ratio_threshold: float | None = None,
) -> CostGuardrailReport:
    budget = weekly_budget_usd if weekly_budget_usd is not None else _float_env(
        WEEKLY_BUDGET_ENV,
        DEFAULT_WEEKLY_BUDGET_USD,
    )
    spike_ratio = spike_ratio_threshold if spike_ratio_threshold is not None else _float_env(
        SPIKE_RATIO_ENV,
        DEFAULT_SPIKE_RATIO,
    )
    if not _table_exists(connection, "llm_usage"):
        return CostGuardrailReport(
            status="no_usage",
            weekly_budget_usd=budget,
            spike_ratio_threshold=spike_ratio,
            latest_week=None,
            latest_week_cost_usd=0.0,
            previous_week=None,
            previous_week_cost_usd=0.0,
            highest_cost_category=None,
            category_costs=(),
            warnings=("llm_usage table missing",),
            suggested_actions=(),
        )

    weekly_rows = _weekly_cost_rows(connection, month=month)
    category_costs = _category_costs(connection, month=month)
    highest = category_costs[0] if category_costs else None
    if not weekly_rows:
        return CostGuardrailReport(
            status="no_usage",
            weekly_budget_usd=budget,
            spike_ratio_threshold=spike_ratio,
            latest_week=None,
            latest_week_cost_usd=0.0,
            previous_week=None,
            previous_week_cost_usd=0.0,
            highest_cost_category=highest,
            category_costs=category_costs,
            warnings=("no llm_usage rows in selected period",),
            suggested_actions=(),
        )

    latest = weekly_rows[0]
    previous = weekly_rows[1] if len(weekly_rows) > 1 else None
    latest_week = str(latest["week"])
    latest_cost = float(latest["week_cost"] or 0.0)
    previous_week = str(previous["week"]) if previous is not None else None
    previous_cost = float(previous["week_cost"] or 0.0) if previous is not None else 0.0

    warnings: list[str] = []
    if latest_cost > budget:
        warnings.append(
            f"weekly budget exceeded: ${latest_cost:.6f} > ${budget:.6f}"
        )
    if previous_cost > 0 and latest_cost >= previous_cost * spike_ratio:
        warnings.append(
            f"weekly cost spike: ${latest_cost:.6f} vs ${previous_cost:.6f}"
        )

    return CostGuardrailReport(
        status="warning" if warnings else "ok",
        weekly_budget_usd=budget,
        spike_ratio_threshold=spike_ratio,
        latest_week=latest_week,
        latest_week_cost_usd=latest_cost,
        previous_week=previous_week,
        previous_week_cost_usd=previous_cost,
        highest_cost_category=highest,
        category_costs=category_costs,
        warnings=tuple(warnings),
        suggested_actions=_suggested_actions(warnings, highest),
    )


def format_cost_guardrail_lines(report: CostGuardrailReport) -> list[str]:
    if report.latest_week is None:
        lines = [
            (
                "- LLM cost guardrail: "
                f"status={report.status} budget=${report.weekly_budget_usd:.6f}"
            )
        ]
    else:
        lines = [
            (
                "- LLM cost guardrail: "
                f"status={report.status} budget=${report.weekly_budget_usd:.6f} "
                f"latest_week={report.latest_week} "
                f"latest_cost=${report.latest_week_cost_usd:.6f}"
            )
        ]
    if report.previous_week:
        lines.append(
            f"  - previous_week={report.previous_week} "
            f"previous_cost=${report.previous_week_cost_usd:.6f} "
            f"spike_threshold={report.spike_ratio_threshold:.2f}x"
        )
    if report.highest_cost_category is not None:
        item = report.highest_cost_category
        lines.append(
            f"  - highest_cost_category={item.category} "
            f"calls={item.call_count} cost=${item.cost_usd:.6f}"
        )
    for warning in report.warnings:
        lines.append(f"  - warning: {warning}")
    for action in report.suggested_actions:
        lines.append(f"  - suggested_action: {action}")
    return lines


def _weekly_cost_rows(connection: sqlite3.Connection, *, month: str | None) -> list[sqlite3.Row]:
    where = "WHERE substr(called_at, 1, 7) = ?" if month else ""
    params = (month,) if month else ()
    return list(
        connection.execute(
            f"""
            SELECT
                strftime('%Y-W%W', called_at) AS week,
                COALESCE(SUM(cost_usd), 0.0) AS week_cost,
                COUNT(*) AS call_count
            FROM llm_usage
            {where}
            GROUP BY week
            ORDER BY week DESC
            """,
            params,
        ).fetchall()
    )


def _category_costs(
    connection: sqlite3.Connection,
    *,
    month: str | None,
) -> tuple[CategoryCost, ...]:
    where = "WHERE substr(called_at, 1, 7) = ?" if month else ""
    params = (month,) if month else ()
    rows = connection.execute(
        f"""
        SELECT
            COALESCE(NULLIF(category, ''), 'uncategorized') AS category,
            COUNT(*) AS call_count,
            COALESCE(SUM(cost_usd), 0.0) AS cost_usd
        FROM llm_usage
        {where}
        GROUP BY COALESCE(NULLIF(category, ''), 'uncategorized')
        ORDER BY cost_usd DESC, category ASC
        """,
        params,
    ).fetchall()
    return tuple(
        CategoryCost(
            category=str(row["category"]),
            call_count=int(row["call_count"] or 0),
            cost_usd=float(row["cost_usd"] or 0.0),
        )
        for row in rows
    )


def _suggested_actions(
    warnings: list[str],
    highest: CategoryCost | None,
) -> tuple[str, ...]:
    if not warnings:
        return ()
    actions = [
        "reduce candidate count before synthesis",
        "use cheaper model for high-volume categories",
    ]
    if highest is not None and highest.category in {"mvp_weekly", "radar", "mvp"}:
        actions.append("defer Radar source expansion until budget recovers")
    else:
        actions.append("defer Radar source expansion if weekly cost remains high")
    return tuple(actions)


def _float_env(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, "").strip())
    except ValueError:
        return default
    return value if value > 0 else default


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
