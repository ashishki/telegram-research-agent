#!/usr/bin/env python3
"""Roll up provider-agnostic AI cost telemetry JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_INPUT = "docs/ai_cost_telemetry.jsonl"
DEFAULT_OUTPUT = "reports/ai_cost_rollup.md"

REQUIRED_FIELDS = {
    "timestamp",
    "project",
    "run_id",
    "source",
    "provider",
    "model",
    "agent_role",
    "environment",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost_usd",
}

NUMERIC_FIELDS = {
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cached_input_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
    "estimated_cost_usd",
    "latency_ms",
    "retry_count",
    "tool_call_count",
}


@dataclass
class Finding:
    severity: str
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Telemetry JSONL path.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Markdown rollup output path.")
    parser.add_argument(
        "--require-file",
        action="store_true",
        help="Fail if the telemetry input file does not exist.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on malformed lines, missing fields, or inconsistent token totals.",
    )
    parser.add_argument(
        "--max-total-cost",
        type=float,
        default=None,
        help="Fail if total estimated cost exceeds this USD threshold.",
    )
    parser.add_argument(
        "--max-run-cost",
        type=float,
        default=None,
        help="Fail if any run_id exceeds this USD threshold.",
    )
    return parser.parse_args()


def as_number(value: Any, field: str, line_no: int, findings: list[Finding]) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        findings.append(Finding("ERROR", f"line {line_no}: `{field}` must be numeric"))
        return 0
    if value < 0:
        findings.append(Finding("ERROR", f"line {line_no}: `{field}` must be non-negative"))
        return 0
    return float(value)


def read_entries(path: Path, strict: bool) -> tuple[list[dict[str, Any]], list[Finding]]:
    entries: list[dict[str, Any]] = []
    findings: list[Finding] = []
    if not path.exists():
        return entries, findings

    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            findings.append(Finding("ERROR", f"line {line_no}: invalid JSON: {exc.msg}"))
            continue
        if not isinstance(entry, dict):
            findings.append(Finding("ERROR", f"line {line_no}: entry must be a JSON object"))
            continue

        missing = sorted(field for field in REQUIRED_FIELDS if field not in entry)
        if missing:
            findings.append(
                Finding("ERROR", f"line {line_no}: missing required fields: {', '.join(missing)}")
            )
            if strict:
                continue

        for field in NUMERIC_FIELDS:
            if field in entry:
                entry[field] = as_number(entry[field], field, line_no, findings)

        total = int(entry.get("total_tokens", 0) or 0)
        expected_total = int(entry.get("input_tokens", 0) or 0) + int(
            entry.get("output_tokens", 0) or 0
        )
        if total and expected_total and total != expected_total:
            findings.append(
                Finding(
                    "ERROR" if strict else "WARN",
                    f"line {line_no}: total_tokens={total} but input+output={expected_total}",
                )
            )

        entries.append(entry)

    return entries, findings


def summarize(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_run: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_task: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_model: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_agent: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_workload: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_routing_level: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    totals: dict[str, float] = defaultdict(float)

    for entry in entries:
        cost = float(entry.get("estimated_cost_usd", 0) or 0)
        tokens = float(entry.get("total_tokens", 0) or 0)
        cache_read_tokens = float(entry.get("cache_read_tokens", 0) or 0)
        cache_write_tokens = float(entry.get("cache_write_tokens", 0) or 0)
        retries = float(entry.get("retry_count", 0) or 0)
        tools = float(entry.get("tool_call_count", 0) or 0)
        latency = float(entry.get("latency_ms", 0) or 0)
        cache_hit = 1 if entry.get("cache_hit") is True else 0

        totals["cost"] += cost
        totals["tokens"] += tokens
        totals["cache_read_tokens"] += cache_read_tokens
        totals["cache_write_tokens"] += cache_write_tokens
        totals["cache_hits"] += cache_hit
        totals["retries"] += retries
        totals["tool_calls"] += tools
        totals["latency_ms"] += latency
        totals["entries"] += 1

        for bucket, key in (
            (by_run, str(entry.get("run_id", "unknown"))),
            (by_task, str(entry.get("task", "unknown"))),
            (by_model, str(entry.get("model", "unknown"))),
            (by_agent, str(entry.get("agent_role", "unknown"))),
            (by_workload, str(entry.get("workload_class", "unknown"))),
            (by_routing_level, str(entry.get("routing_maturity_level", "unknown"))),
        ):
            bucket[key]["cost"] += cost
            bucket[key]["tokens"] += tokens
            bucket[key]["cache_read_tokens"] += cache_read_tokens
            bucket[key]["cache_write_tokens"] += cache_write_tokens
            bucket[key]["cache_hits"] += cache_hit
            bucket[key]["retries"] += retries
            bucket[key]["tool_calls"] += tools
            bucket[key]["latency_ms"] += latency
            bucket[key]["entries"] += 1

    return {
        "totals": totals,
        "by_run": by_run,
        "by_task": by_task,
        "by_model": by_model,
        "by_agent": by_agent,
        "by_workload": by_workload,
        "by_routing_level": by_routing_level,
    }


def md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def table(title: str, rows: dict[str, dict[str, float]], *, limit: int = 20) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| Key | Entries | Cost USD | Tokens | Cache Read | Cache Write | Cache Hit % | Retries | Tool Calls | Avg Latency ms |",
        "|-----|---------|----------|--------|------------|-------------|-------------|---------|------------|----------------|",
    ]
    sorted_rows = sorted(rows.items(), key=lambda item: item[1].get("cost", 0), reverse=True)
    for key, values in sorted_rows[:limit]:
        entries = int(values.get("entries", 0))
        avg_latency = values.get("latency_ms", 0) / entries if entries else 0
        cache_hit_rate = (values.get("cache_hits", 0) / entries * 100) if entries else 0
        lines.append(
            "| {key} | {entries} | {cost:.6f} | {tokens} | {cache_read} | {cache_write} | {cache_hit:.1f}% | {retries} | {tools} | {latency:.1f} |".format(
                key=md_cell(key),
                entries=entries,
                cost=values.get("cost", 0),
                tokens=int(values.get("tokens", 0)),
                cache_read=int(values.get("cache_read_tokens", 0)),
                cache_write=int(values.get("cache_write_tokens", 0)),
                cache_hit=cache_hit_rate,
                retries=int(values.get("retries", 0)),
                tools=int(values.get("tool_calls", 0)),
                latency=avg_latency,
            )
        )
    if not sorted_rows:
        lines.append("| none | 0 | 0.000000 | 0 | 0 | 0 | 0.0% | 0 | 0 | 0.0 |")
    lines.append("")
    return lines


def render_markdown(summary: dict[str, Any], findings: list[Finding]) -> str:
    totals = summary["totals"]
    entries = int(totals.get("entries", 0))
    avg_latency = totals.get("latency_ms", 0) / entries if entries else 0
    cache_hit_rate = (totals.get("cache_hits", 0) / entries * 100) if entries else 0
    lines = [
        "# AI Cost Rollup",
        "",
        "Generated by `tools/cost_rollup.py`.",
        "",
        "## Totals",
        "",
        "| Entries | Cost USD | Tokens | Cache Read | Cache Write | Cache Hit % | Retries | Tool Calls | Avg Latency ms |",
        "|---------|----------|--------|------------|-------------|-------------|---------|------------|----------------|",
        "| {entries} | {cost:.6f} | {tokens} | {cache_read} | {cache_write} | {cache_hit:.1f}% | {retries} | {tools} | {latency:.1f} |".format(
            entries=entries,
            cost=totals.get("cost", 0),
            tokens=int(totals.get("tokens", 0)),
            cache_read=int(totals.get("cache_read_tokens", 0)),
            cache_write=int(totals.get("cache_write_tokens", 0)),
            cache_hit=cache_hit_rate,
            retries=int(totals.get("retries", 0)),
            tools=int(totals.get("tool_calls", 0)),
            latency=avg_latency,
        ),
        "",
    ]
    lines.extend(table("By Run", summary["by_run"]))
    lines.extend(table("By Task", summary["by_task"]))
    lines.extend(table("By Model", summary["by_model"]))
    lines.extend(table("By Agent Role", summary["by_agent"]))
    lines.extend(table("By Workload Class", summary["by_workload"]))
    lines.extend(table("By Routing Maturity", summary["by_routing_level"]))

    lines.extend(["## Findings", ""])
    if findings:
        for finding in findings:
            lines.append(f"- {finding.severity}: {finding.message}")
    else:
        lines.append("none")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    findings: list[Finding] = []
    if not input_path.exists() and args.require_file:
        findings.append(Finding("ERROR", f"telemetry file missing: {input_path}"))

    entries, read_findings = read_entries(input_path, args.strict)
    findings.extend(read_findings)
    summary = summarize(entries)

    total_cost = summary["totals"].get("cost", 0)
    if args.max_total_cost is not None and total_cost > args.max_total_cost:
        findings.append(
            Finding(
                "ERROR",
                f"total cost {total_cost:.6f} exceeds max-total-cost {args.max_total_cost:.6f}",
            )
        )

    if args.max_run_cost is not None:
        for run_id, values in summary["by_run"].items():
            cost = values.get("cost", 0)
            if cost > args.max_run_cost:
                findings.append(
                    Finding(
                        "ERROR",
                        f"run {run_id} cost {cost:.6f} exceeds max-run-cost {args.max_run_cost:.6f}",
                    )
                )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown(summary, findings), encoding="utf-8")

    for finding in findings:
        print(f"{finding.severity}: {finding.message}")

    errors = [finding for finding in findings if finding.severity == "ERROR"]
    if errors:
        print(f"cost_rollup: failed with {len(errors)} error(s)", file=sys.stderr)
        return 1
    print(f"cost_rollup: ok ({len(entries)} entries, ${total_cost:.6f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
