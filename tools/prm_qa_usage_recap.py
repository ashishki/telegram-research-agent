#!/usr/bin/env python3
"""Aggregate owner-local PRM-QA receipts into a public-safe usage recap."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRIVATE_DIR = PROJECT_ROOT / "data" / "evals" / "private" / "prm_qa" / "interactions"
DEFAULT_PUBLIC_SUMMARY = PROJECT_ROOT / "evals" / "prm_qa" / "prm_qa_usage_recap_summary.v1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", default=str(DEFAULT_PRIVATE_DIR))
    parser.add_argument("--public-summary", default=str(DEFAULT_PUBLIC_SUMMARY))
    args = parser.parse_args()

    receipts = _load_receipts(Path(args.private_dir))
    summary = summarize_receipts(receipts)
    out = Path(args.public_summary)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "receipt_count": summary["receipt_count"], "public_summary": str(out)}, ensure_ascii=False, sort_keys=True))
    return 0


def summarize_receipts(receipts: list[Mapping[str, Any]]) -> dict[str, Any]:
    feedback = Counter(str(_mapping(item.get("feedback")).get("label") or "unknown") for item in receipts)
    feedback_reasons = Counter(str(_mapping(item.get("feedback")).get("reason") or "unknown") for item in receipts)
    jobs = Counter(str(item.get("job_type") or "unknown") for item in receipts)
    workflows = Counter(str(item.get("workflow") or "unknown") for item in receipts)
    intents = Counter(str(item.get("primary_intent") or "unknown") for item in receipts)
    contracts = Counter(str(item.get("response_contract_id") or "unknown") for item in receipts)
    render_modes = Counter(str(_mapping(item.get("render")).get("mode") or "unknown") for item in receipts)
    relevance = {
        key: sum(int(_mapping(item.get("relevance")).get(key) or 0) for item in receipts)
        for key in ("direct_count", "partial_count", "adjacent_count", "unrelated_count")
    }
    answers = [int(_mapping(item.get("render")).get("answer_chars") or 0) for item in receipts]
    external_false_positive = sum(
        1
        for item in receipts
        if str(item.get("primary_intent") or "") in {"archive_lookup", "archive_synthesis", "archive_to_action"}
        and bool(_mapping(item.get("route")).get("external_verification_required"))
    )
    unsupported_project_context = sum(
        1
        for item in receipts
        if str(item.get("primary_intent") or "") in {"archive_lookup", "archive_synthesis", "archive_to_action"}
        and bool(_mapping(item.get("route")).get("project_context_required"))
    )
    return {
        "schema_version": "prm_qa_usage_recap_summary.v2",
        "receipt_count": len(receipts),
        "feedback": dict(sorted(feedback.items())),
        "feedback_reasons": dict(sorted(feedback_reasons.items())),
        "job_types": dict(sorted(jobs.items())),
        "workflows": dict(sorted(workflows.items())),
        "primary_intents": dict(sorted(intents.items())),
        "response_contracts": dict(sorted(contracts.items())),
        "render_modes": dict(sorted(render_modes.items())),
        "relevance_totals": relevance,
        "useful_rate": _rate(feedback.get("useful", 0), len(receipts)),
        "partial_rate": _rate(feedback.get("partial", 0), len(receipts)),
        "miss_rate": _rate(feedback.get("miss", 0), len(receipts)),
        "external_verification_false_positive_rate": _rate(external_false_positive, len(receipts)),
        "unsupported_project_context_rate": _rate(unsupported_project_context, len(receipts)),
        "answer_length": {
            "mean_chars": round(sum(answers) / len(answers), 2) if answers else 0.0,
            "max_chars": max(answers, default=0),
        },
        "save_watch_action_counts": {
            "saved": sum(1 for item in receipts if item.get("save_state") not in {None, "not_requested"}),
            "watched": sum(1 for item in receipts if item.get("watch_state") not in {None, "not_requested"}),
            "actions": sum(1 for item in receipts if item.get("action_state") not in {None, "not_requested"}),
        },
        "privacy": {
            "public_summary_contains_questions": False,
            "public_summary_contains_raw_answers": False,
            "public_summary_contains_source_urls": False,
            "public_summary_contains_candidate_ids": False,
            "private_receipts_gitignored": True,
        },
        "honesty_boundary": "Aggregate interaction receipts are usage instrumentation; product-value claims require explicit operator feedback over time.",
    }


def _load_receipts(path: Path) -> list[Mapping[str, Any]]:
    if not path.exists():
        return []
    receipts = []
    for file_path in sorted(path.glob("*.json")):
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(payload, Mapping):
            receipts.append(payload)
    return receipts


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rate(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
