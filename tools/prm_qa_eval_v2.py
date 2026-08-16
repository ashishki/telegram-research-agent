#!/usr/bin/env python3
"""Run PRM-QA Eval V2 through the actual runtime route and renderer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from bot.handlers import _run_prm_auto_message_once  # noqa: E402
from config.settings import Settings, load_settings  # noqa: E402
from llm.client import suppress_usage_recording  # noqa: E402


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
    parser.add_argument("--live", action="store_true", help="Use runtime provider-gated router/synthesis flags as configured.")
    parser.add_argument("--confirm-live-eval", action="store_true")
    args = parser.parse_args()
    if args.live and not args.confirm_live_eval:
        parser.error("--live requires --confirm-live-eval")
    if args.live and os.environ.get("PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS", "").casefold() not in {"1", "true", "yes", "approved"}:
        parser.error("--live requires PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1")
    if not args.live:
        os.environ["PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS"] = "0"
        os.environ["PRM_TELEGRAM_AUTO_LLM_ROUTER"] = "0"
        os.environ["PRM_TELEGRAM_RAG_LLM_SYNTHESIS"] = "0"

    cases = _load_cases(Path(args.cases), partition=args.partition)
    if args.case_limit:
        cases = cases[: max(1, int(args.case_limit))]
    if not cases:
        raise SystemExit("no PRM-QA V2 cases found; run tools/prm_qa_generate_private_eval_v2.py first")
    base_settings = load_settings()
    settings = Settings(
        db_path=str(Path(args.db).resolve()),
        llm_api_key=base_settings.llm_api_key,
        model_provider=base_settings.model_provider,
        telegram_session_path=base_settings.telegram_session_path,
    )
    report = evaluate_cases(cases, settings=settings, live=bool(args.live))
    report["partition"] = args.partition
    out = Path(args.public_report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "case_count": report["case_count"], "public_report": str(out)}, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


def evaluate_cases(cases: Sequence[Mapping[str, Any]], *, settings: Settings, live: bool = False) -> dict[str, Any]:
    observations = []
    for case in cases:
        case_hash = _hash(str(case.get("case_id") or case.get("query") or ""))
        with suppress_usage_recording():
            runtime = _run_prm_auto_message_once(
                f"prm-qav2-{case_hash}",
                str(case.get("query") or ""),
                settings,
                remember_dialog=False,
            )
        observations.append(_observation(case, runtime))
    route_rows = [obs["routing"] for obs in observations]
    retrieval_rows = [obs["retrieval"] for obs in observations]
    verification_rows = [obs["final_answer_verification"] for obs in observations]
    failures = [failure for obs in observations for failure in obs["failures"]]
    report = {
        "schema_version": "prm_qa_eval_report.v2",
        "case_count": len(observations),
        "case_fingerprint": _case_fingerprint(cases),
        "live_runtime_flags": bool(live),
        "status": "pass" if not failures else "fail",
        "job_type_counts": dict(sorted(Counter(str(case.get("job_type") or "unknown") for case in cases).items())),
        "routing": _routing_summary(route_rows),
        "retrieval": _retrieval_summary(retrieval_rows),
        "retrieval_by_job_type": _retrieval_by_job_type(retrieval_rows),
        "final_answer_verification": _final_verification_summary(verification_rows),
        "task_success": _task_success_summary(observations),
        "failure_counts": dict(sorted(Counter(failures).items())),
        "cases": [
            {
                "case_id_hash": obs["case_id_hash"],
                "job_type": obs["job_type"],
                "actual_route": obs["routing"]["actual_route"],
                "expected_route": obs["routing"]["expected_route"],
                "runtime_status": obs["runtime_status"],
                "failure_count": len(obs["failures"]),
            }
            for obs in observations
        ],
        "privacy": {
            "public_report_contains_queries": False,
            "public_report_contains_raw_telegram_body": False,
            "public_report_contains_source_urls": False,
            "telegram_messages_sent": False,
            "durable_writes_requested": False,
            "provider_egress": bool(live),
        },
        "honesty_boundary": "Eval V2 is automated silver evidence over real runtime route/renderer, not human usefulness proof.",
    }
    return report


def _observation(case: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, Any]:
    payload = runtime.get("payload") if isinstance(runtime.get("payload"), Mapping) else {}
    route = runtime.get("route") if isinstance(runtime.get("route"), Mapping) else {}
    operator_context = runtime.get("operator_context") if isinstance(runtime.get("operator_context"), Mapping) else {}
    final_verification = runtime.get("final_answer_verification") if isinstance(runtime.get("final_answer_verification"), Mapping) else {}
    final_metrics = final_verification.get("metrics") if isinstance(final_verification.get("metrics"), Mapping) else {}
    retrieval = _score_retrieval(case, payload)
    actual_route = str(runtime.get("mode") or route.get("mode") or "")
    expected_route = str(case.get("expected_route") or "")
    expected_workflow = str(case.get("expected_workflow") or "")
    actual_workflow = str(operator_context.get("primary_workflow") or "")
    workflow_correct = not expected_workflow or actual_workflow == expected_workflow
    routing = {
        "expected_route": expected_route,
        "actual_route": actual_route,
        "expected_workflow": expected_workflow,
        "operator_context_workflow": actual_workflow,
        "operator_context_present": bool(operator_context),
        "router": str(route.get("router") or ""),
        "workflow_correct": workflow_correct,
        "correct": actual_route == expected_route and workflow_correct and bool(operator_context or actual_route == "project_clarify"),
    }
    failures = []
    if not routing["correct"]:
        failures.append("route_miss")
    if case.get("expected_external_verification"):
        answer_gate = payload.get("answer_gate") if isinstance(payload.get("answer_gate"), Mapping) else {}
        if not bool(answer_gate.get("external_verification_required")):
            failures.append("external_verification_boundary_miss")
    if retrieval.get("positive_expected") and retrieval.get("recall_at_5") == 0.0:
        failures.append("retrieval_miss")
    if int(final_metrics.get("current_fact_violations") or 0):
        failures.append("current_fact_violation")
    if float(final_metrics.get("unsupported_claim_rate") or 0.0) > 0.50 and int(final_verification.get("claim_count") or 0):
        failures.append("final_answer_grounding_miss")
    if bool((payload.get("privacy") or {}).get("durable_writes")):
        failures.append("durable_write")
    return {
        "case_id_hash": _hash(str(case.get("case_id") or case.get("query") or "")),
        "job_type": str(case.get("job_type") or "unknown"),
        "runtime_status": str(runtime.get("status") or ""),
        "routing": routing,
        "retrieval": retrieval,
        "final_answer_verification": {
            "claim_count": int(final_verification.get("claim_count") or 0),
            "unsupported_claim_rate": float(final_metrics.get("unsupported_claim_rate") or 0.0),
            "supported_claim_rate": float(final_metrics.get("supported_claim_rate") or 0.0),
            "current_fact_violations": int(final_metrics.get("current_fact_violations") or 0),
        },
        "failures": failures,
    }


def _score_retrieval(case: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    archive = payload.get("archive_evidence") if isinstance(payload.get("archive_evidence"), Mapping) else {}
    linked = payload.get("linked_source_evidence") if isinstance(payload.get("linked_source_evidence"), Mapping) else {}
    items = [
        *[item for item in archive.get("items") or [] if isinstance(item, Mapping)],
        *[item for item in linked.get("items") or [] if isinstance(item, Mapping)],
    ]
    positives = {str(value) for value in case.get("positive_source_ids") or [] if str(value)}
    positive_groups = {str(value) for value in case.get("positive_source_group_ids") or [] if str(value)}
    positive_expected = bool(positives or positive_groups)
    ranks = []
    for index, item in enumerate(items, start=1):
        if str(item.get("post_id") or "") in positives:
            ranks.append(index)
        if _source_group_id(item) in positive_groups:
            ranks.append(index)
    best_rank = min(ranks or [0])
    return {
        "job_type": str(case.get("job_type") or "unknown"),
        "positive_expected": positive_expected,
        "result_count": len(items),
        "recall_at_5": 1.0 if best_rank and best_rank <= 5 else 0.0 if positive_expected else None,
        "mrr": round(1.0 / best_rank, 4) if best_rank else 0.0 if positive_expected else None,
        "context_precision_at_5": _context_precision(case, items[:5]) if items else 0.0 if positive_expected else None,
    }


def _routing_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    correct = sum(1 for row in rows if row.get("correct"))
    return {
        "evaluated_cases": total,
        "route_accuracy": round(correct / total, 4) if total else 0.0,
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
    return {job_type: _retrieval_summary(values) for job_type, values in sorted(grouped.items())}


def _final_verification_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "evaluated_cases": len(rows),
        "claim_count_mean": round(statistics.mean(int(row.get("claim_count") or 0) for row in rows), 4) if rows else 0.0,
        "unsupported_claim_rate": _mean(row.get("unsupported_claim_rate") for row in rows),
        "supported_claim_rate": _mean(row.get("supported_claim_rate") for row in rows),
        "current_fact_violations": sum(int(row.get("current_fact_violations") or 0) for row in rows),
    }


def _task_success_summary(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    success = sum(1 for obs in observations if not obs.get("failures"))
    return {
        "success_count": success,
        "miss_count": len(observations) - success,
        "success_rate": round(success / len(observations), 4) if observations else 0.0,
    }


def _context_precision(case: Mapping[str, Any], items: Sequence[Mapping[str, Any]]) -> float:
    positives = {str(value) for value in case.get("positive_source_ids") or [] if str(value)}
    positive_groups = {str(value) for value in case.get("positive_source_group_ids") or [] if str(value)}
    if not items:
        return 0.0
    hits = sum(1 for item in items if str(item.get("post_id") or "") in positives or _source_group_id(item) in positive_groups)
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


def _mean(values: Any) -> float:
    clean = [float(value) for value in values if value is not None]
    return round(sum(clean) / len(clean), 4) if clean else 0.0


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _case_fingerprint(cases: Sequence[Mapping[str, Any]]) -> str:
    payload = [{"case_id": case.get("case_id"), "job_type": case.get("job_type"), "partition": case.get("holdout_partition")} for case in cases]
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
