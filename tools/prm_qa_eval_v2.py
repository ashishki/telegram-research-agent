#!/usr/bin/env python3
"""Evaluate private PRM-QA V2 cases through the active application service."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from config.settings import Settings, load_settings  # noqa: E402
from llm.client import suppress_usage_recording  # noqa: E402
from prm.application import PersonalResearchAssistant  # noqa: E402
from prm.contracts import OperatorRequest  # noqa: E402

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "agent.db"
DEFAULT_CASES = PROJECT_ROOT / "data" / "evals" / "private" / "prm_qa" / "cases.v2.jsonl"
DEFAULT_PUBLIC_REPORT = PROJECT_ROOT / "evals" / "prm_qa" / "prm_qa_eval_report.v2.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--public-report", default=str(DEFAULT_PUBLIC_REPORT))
    parser.add_argument("--partition", choices=["all", "development", "tuning", "holdout"], default="all")
    parser.add_argument("--case-limit", type=int, default=0)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-live-eval", action="store_true")
    args = parser.parse_args()

    if args.live and not args.confirm_live_eval:
        parser.error("--live requires --confirm-live-eval")
    if args.live and not _env_enabled("PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS"):
        parser.error("--live requires PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1")
    if not args.live:
        os.environ["PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS"] = "0"
        os.environ["PRM_TELEGRAM_RAG_LLM_SYNTHESIS"] = "0"

    cases = _load_cases(Path(args.cases), partition=args.partition)
    if args.case_limit:
        cases = cases[: max(1, int(args.case_limit))]
    if not cases:
        raise SystemExit("no PRM-QA V2 cases found")

    base = load_settings()
    settings = Settings(
        db_path=str(Path(args.db).resolve()),
        llm_api_key=base.llm_api_key,
        model_provider=base.model_provider,
        telegram_session_path=base.telegram_session_path,
    )
    report = evaluate_cases(cases, settings=settings, live=bool(args.live))
    report["partition"] = args.partition
    output = Path(args.public_report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "case_count": report["case_count"], "public_report": str(output)}, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


def evaluate_cases(cases: Sequence[Mapping[str, Any]], *, settings: Settings, live: bool = False) -> dict[str, Any]:
    assistant = PersonalResearchAssistant(settings=settings)
    observations = []
    for case in cases:
        case_hash = _hash(str(case.get("case_id") or case.get("query") or ""))
        with suppress_usage_recording():
            result = assistant.answer(
                OperatorRequest(
                    query=str(case.get("query") or ""),
                    mode="auto",
                    chat_id=f"prm-qav2-{case_hash}",
                    project_name=str(case.get("project_name") or ""),
                )
            )
        observations.append(_observation(case, result.to_dict()))

    routing_rows = [item["routing"] for item in observations]
    retrieval_rows = [item["retrieval"] for item in observations]
    verification_rows = [item["final_answer_verification"] for item in observations]
    failures = [failure for item in observations for failure in item["failures"]]
    return {
        "schema_version": "prm_qa_eval_report.v2",
        "case_count": len(observations),
        "case_fingerprint": _case_fingerprint(cases),
        "application_boundary": "prm.application.PersonalResearchAssistant",
        "live_runtime_flags": bool(live),
        "status": "pass" if not failures else "fail",
        "job_type_counts": dict(sorted(Counter(str(case.get("job_type") or "unknown") for case in cases).items())),
        "routing": _routing_summary(routing_rows),
        "retrieval": _retrieval_summary(retrieval_rows),
        "retrieval_by_job_type": _retrieval_by_job_type(retrieval_rows),
        "final_answer_verification": _verification_summary(verification_rows),
        "task_success": _task_success_summary(observations),
        "failure_counts": dict(sorted(Counter(failures).items())),
        "cases": [
            {
                "case_id_hash": item["case_id_hash"],
                "job_type": item["job_type"],
                "actual_route": item["routing"]["actual_route"],
                "expected_route": item["routing"]["expected_route"],
                "runtime_status": item["runtime_status"],
                "failure_count": len(item["failures"]),
            }
            for item in observations
        ],
        "privacy": {
            "public_report_contains_queries": False,
            "public_report_contains_raw_telegram_body": False,
            "public_report_contains_source_urls": False,
            "telegram_messages_sent": False,
            "durable_writes_requested": False,
            "provider_egress": bool(live),
        },
        "honesty_boundary": "Eval V2 is automated silver evidence through the active application boundary, not human usefulness proof.",
    }


def _observation(case: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    payload = _mapping(runtime.get("payload"))
    context = _mapping(runtime.get("operator_context"))
    route = _mapping(runtime.get("route"))
    verification = _mapping(runtime.get("final_answer_verification"))
    metrics = _mapping(verification.get("metrics"))
    retrieval = _score_retrieval(case, payload)
    actual_route = str(runtime.get("mode") or "")
    expected_route = str(case.get("expected_route") or "")
    expected_workflow = str(case.get("expected_workflow") or "")
    actual_workflow = str(context.get("primary_workflow") or "")
    expected_mode = "project_clarify" if bool(case.get("expected_clarification")) else expected_route
    workflow_correct = not expected_workflow or actual_workflow == expected_workflow or actual_route == "project_clarify"
    routing = {
        "expected_route": expected_mode,
        "actual_route": actual_route,
        "expected_workflow": expected_workflow,
        "operator_context_workflow": actual_workflow,
        "operator_context_present": bool(context) or actual_route == "project_clarify",
        "router": str(route.get("reason") or "unknown"),
        "workflow_correct": workflow_correct,
        "correct": actual_route == expected_mode and workflow_correct,
    }
    failures = []
    if not routing["correct"]:
        failures.append("route_miss")
    if case.get("expected_external_verification"):
        gate = _mapping(payload.get("answer_gate"))
        if not bool(gate.get("external_verification_required")):
            failures.append("external_verification_boundary_miss")
    if retrieval.get("positive_expected") and retrieval.get("recall_at_5") == 0.0:
        failures.append("retrieval_miss")
    if int(metrics.get("current_fact_violations") or 0):
        failures.append("current_fact_violation")
    if float(metrics.get("unsupported_claim_rate") or 0.0) > 0.50 and int(verification.get("claim_count") or 0):
        failures.append("final_answer_grounding_miss")
    if bool(_mapping(payload.get("privacy")).get("durable_writes")):
        failures.append("durable_write")
    return {
        "case_id_hash": _hash(str(case.get("case_id") or case.get("query") or "")),
        "job_type": str(case.get("job_type") or "unknown"),
        "runtime_status": str(runtime.get("status") or ""),
        "routing": routing,
        "retrieval": retrieval,
        "final_answer_verification": {
            "claim_count": int(verification.get("claim_count") or 0),
            "unsupported_claim_rate": float(metrics.get("unsupported_claim_rate") or 0.0),
            "supported_claim_rate": float(metrics.get("supported_claim_rate") or 0.0),
            "current_fact_violations": int(metrics.get("current_fact_violations") or 0),
        },
        "failures": failures,
    }


def _score_retrieval(case: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    archive = _mapping(payload.get("archive_evidence"))
    linked = _mapping(payload.get("linked_source_evidence"))
    items = [
        *[item for item in archive.get("items") or [] if isinstance(item, Mapping)],
        *[item for item in linked.get("items") or [] if isinstance(item, Mapping)],
    ]
    positives = {str(value) for value in case.get("positive_source_ids") or [] if str(value)}
    groups = {str(value) for value in case.get("positive_source_group_ids") or [] if str(value)}
    positive_expected = bool(positives or groups)
    ranks = [
        index
        for index, item in enumerate(items, start=1)
        if str(item.get("post_id") or "") in positives or _source_group_id(item) in groups
    ]
    best = min(ranks or [0])
    return {
        "job_type": str(case.get("job_type") or "unknown"),
        "positive_expected": positive_expected,
        "result_count": len(items),
        "recall_at_5": 1.0 if best and best <= 5 else 0.0 if positive_expected else None,
        "mrr": round(1.0 / best, 4) if best else 0.0 if positive_expected else None,
        "context_precision_at_5": _context_precision(positives, groups, items[:5]) if items else 0.0 if positive_expected else None,
    }


def _routing_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    return {
        "evaluated_cases": total,
        "route_accuracy": round(sum(1 for row in rows if row.get("correct")) / total, 4) if total else 0.0,
        "workflow_accuracy": round(sum(1 for row in rows if row.get("workflow_correct")) / total, 4) if total else 0.0,
        "operator_context_rate": round(sum(1 for row in rows if row.get("operator_context_present")) / total, 4) if total else 0.0,
        "routers": dict(sorted(Counter(str(row.get("router") or "unknown") for row in rows).items())),
    }


def _retrieval_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    positives = [row for row in rows if row.get("positive_expected")]
    return {
        "evaluated_cases": len(rows),
        "positive_cases": len(positives),
        "recall_at_5": _mean(row.get("recall_at_5") for row in positives),
        "mrr": _mean(row.get("mrr") for row in positives),
        "context_precision_at_5": _mean(row.get("context_precision_at_5") for row in positives),
    }


def _retrieval_by_job_type(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("job_type") or "unknown")].append(row)
    return {key: _retrieval_summary(value) for key, value in sorted(grouped.items())}


def _verification_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "evaluated_cases": len(rows),
        "claim_count_mean": round(statistics.mean(int(row.get("claim_count") or 0) for row in rows), 4) if rows else 0.0,
        "unsupported_claim_rate": _mean(row.get("unsupported_claim_rate") for row in rows),
        "supported_claim_rate": _mean(row.get("supported_claim_rate") for row in rows),
        "current_fact_violations": sum(int(row.get("current_fact_violations") or 0) for row in rows),
    }


def _task_success_summary(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    success = sum(1 for item in observations if not item.get("failures"))
    return {"success_count": success, "miss_count": len(observations) - success, "success_rate": round(success / len(observations), 4) if observations else 0.0}


def _context_precision(positive_ids: set[str], positive_groups: set[str], items: Sequence[Mapping[str, Any]]) -> float:
    if not items:
        return 0.0
    hits = sum(1 for item in items if str(item.get("post_id") or "") in positive_ids or _source_group_id(item) in positive_groups)
    return round(hits / len(items), 4)


def _source_group_id(item: Mapping[str, Any]) -> str:
    for key in ("source_group_id", "repost_cluster_id", "duplicate_cluster_id", "content_hash"):
        value = str(item.get(key) or "").strip()
        if value:
            return f"{key}:{value[:24]}"
    source = str(item.get("source_url") or item.get("post_id") or "")
    return "sha256:" + hashlib.sha256(source.encode()).hexdigest()[:16]


def _load_cases(path: Path, *, partition: str) -> list[Mapping[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        if partition != "all" and case.get("holdout_partition") != partition:
            continue
        rows.append(case)
    return rows


def _case_fingerprint(cases: Sequence[Mapping[str, Any]]) -> str:
    payload = [{"case_id": case.get("case_id"), "job_type": case.get("job_type"), "partition": case.get("holdout_partition")} for case in cases]
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _mean(values: Any) -> float:
    clean = [float(value) for value in values if value is not None]
    return round(sum(clean) / len(clean), 4) if clean else 0.0


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().casefold() in {"1", "true", "yes", "approved"}


if __name__ == "__main__":
    raise SystemExit(main())
