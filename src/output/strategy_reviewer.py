from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from db.ai_report_feedback import summarize_ai_report_feedback


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _task(
    *,
    title: str,
    files: list[str],
    acceptance_criteria: list[str],
    verification_commands: list[str],
    rationale: str,
) -> dict[str, Any]:
    return {
        "title": title,
        "rationale": rationale,
        "files": files,
        "acceptance_criteria": acceptance_criteria,
        "verification_commands": verification_commands,
        "requires_approval": True,
        "mutation_policy": "suggestion_only_no_auto_edit",
    }


def build_strategy_review(
    connection: sqlite3.Connection,
    *,
    week_label: str | None = None,
    before_week_label: str | None = None,
) -> dict[str, Any]:
    summary = summarize_ai_report_feedback(
        connection,
        week_label=week_label,
        before_week_label=before_week_label,
    )
    counts = summary.get("counts_by_feedback") or {}
    has_feedback = int(summary.get("event_count") or 0) > 0

    keep: list[str] = []
    change: list[str] = []
    demote: list[str] = []
    test_next_week: list[str] = []
    approval_required: list[dict[str, str]] = []
    memory_only: list[str] = []
    tasks: list[dict[str, Any]] = []
    risks: list[str] = [
        "Strategy Reviewer is advisory; Hermes must not apply code/config/profile/project changes automatically."
    ]

    if not has_feedback:
        keep.append("Keep the feedback prompt visible; personalization state is unknown until confirmed feedback exists.")
        change.append("Ask for at least one read/try/missed/trust feedback item after the workbook.")
        test_next_week.append("Run the workbook with explicit feedback targets and inspect completion.")
        risks.append("No confirmed feedback is an unknown state, not a negative signal.")
    else:
        memory_only.append("Confirmed feedback is already stored in ai_report_feedback_events; no profile/config edit is required.")
        if counts.get("useful") or counts.get("tried") or counts.get("applied_to_project"):
            keep.append("Keep promoting try/build items that received useful, tried, or applied-to-project feedback.")
        if counts.get("too_shallow"):
            change.append("Increase source-depth checks for sections marked too_shallow.")
            approval_required.append(
                {
                    "change_type": "code_or_prompt",
                    "reason": "Depth behavior requires an approved renderer/prompt/eval change, not an automatic memory write.",
                }
            )
            risks.append("Source-depth changes can weaken evidence gates if they are applied without a regression test.")
            tasks.append(
                _task(
                    title="Add workbook source-depth regression for too_shallow feedback",
                    files=["src/output/ai_visual_report.py", "tests/test_ai_visual_report.py"],
                    acceptance_criteria=[
                        "Workbook shows deeper source/caveat requirements after too_shallow feedback.",
                        "No claim is upgraded without source URLs and caveats.",
                    ],
                    verification_commands=[
                        "PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_ai_visual_report"
                    ],
                    rationale="Operator feedback marked prior analysis too shallow.",
                )
            )
        if counts.get("wrong_priority") or counts.get("not_interested") or counts.get("noise"):
            demote.append("Demote similar threads/actions that match wrong_priority, not_interested, or noise feedback.")
            tasks.append(
                _task(
                    title="Add ranking regression for demoted workbook topics",
                    files=["src/output/ai_intelligence_report.py", "tests/test_ai_intelligence_report.py"],
                    acceptance_criteria=[
                        "wrong_priority/not_interested feedback lowers related read/try/build ranking.",
                        "Useful/tried feedback can still promote explicitly related targets.",
                    ],
                    verification_commands=[
                        "PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_ai_intelligence_report"
                    ],
                    rationale="Operator feedback found priority drift or irrelevant topics.",
                )
            )
        if counts.get("missed_important_post"):
            test_next_week.append("Turn missed important posts into eval examples and verify they appear in next workbook coverage.")
            memory_only.append("Missed-post feedback can remain memory-only until a human approves new eval/code changes.")
        if counts.get("trust_too_high") or counts.get("trust_too_low") or counts.get("verify_first"):
            change.append("Review source-trust calibration before changing trust thresholds.")
            approval_required.append(
                {
                    "change_type": "config",
                    "reason": "Trust threshold/profile changes require explicit operator approval.",
                }
            )
            risks.append("Trust calibration changes require explicit approval because they affect future ranking behavior.")

    if not tasks:
        tasks.append(
            _task(
                title="Review feedback completion after next workbook",
                files=["src/output/ai_report_feedback_intake.py", "tests/test_ai_report_feedback.py"],
                acceptance_criteria=[
                    "Feedback confirmation still writes only confirmed events.",
                    "Strategy review keeps code/config changes suggestion-only.",
                ],
                verification_commands=[
                    "PYTHONPATH=src PYTHONPYCACHEPREFIX=/tmp/telegram-research-pycache python3 -m unittest tests.test_ai_report_feedback"
                ],
                rationale="No targeted code task is justified until more feedback exists.",
            )
        )

    return {
        "generated_at": _now_iso(),
        "week_label": week_label,
        "before_week_label": before_week_label,
        "feedback_summary": summary,
        "suggestions": {
            "keep": keep,
            "change": change,
            "demote": demote,
            "test_next_week": test_next_week,
        },
        "memory_only_updates": memory_only,
        "approval_required": approval_required,
        "codex_tasks": tasks,
        "risks": risks,
        "mutation_policy": {
            "source_code": "do_not_modify",
            "prompts": "do_not_modify",
            "thresholds": "do_not_modify",
            "profile": "do_not_modify",
            "projects": "do_not_modify",
        },
    }


def write_strategy_review(review: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
