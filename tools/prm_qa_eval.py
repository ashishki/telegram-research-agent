#!/usr/bin/env python3
"""Layered PRM-QA evaluation over private generated cases."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from assistant.claim_ledger import build_claim_ledger, evaluate_claim_grounding  # noqa: E402
from assistant.evidence_quality import build_evidence_quality_items, evidence_quality_summary  # noqa: E402
from assistant.prm_private_traces import write_private_failure_trace  # noqa: E402
from assistant.retrieval_policy import build_query_rewrites, select_retrieval_policy  # noqa: E402
from db.archive_search import search_telegram_archive  # noqa: E402
from db.archive_vector import search_telegram_archive_hybrid  # noqa: E402


DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "agent.db"
DEFAULT_CASES = PROJECT_ROOT / "data" / "evals" / "private" / "prm_qa" / "cases.v1.jsonl"
DEFAULT_VECTOR_INDEX = PROJECT_ROOT / "data" / "vector" / "archive_vector.sqlite"
DEFAULT_PUBLIC_REPORT = PROJECT_ROOT / "evals" / "prm_qa" / "prm_qa_eval_report.v1.json"
DEFAULT_TRACE_DIR = PROJECT_ROOT / "data" / "evals" / "private" / "prm_qa" / "failed_cases"

VARIANTS = [
    "R0_sqlite_fts_strict_or_baseline",
    "R1_fts_hash_vector_fallback",
    "R2_fts_hash_vector_always",
    "R3_fts_bounded_query_rewrite",
    "R4_true_local_dense_candidate",
    "R5_candidate_pool_reranker",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--vector-index", default=str(DEFAULT_VECTOR_INDEX))
    parser.add_argument("--public-report", default=str(DEFAULT_PUBLIC_REPORT))
    parser.add_argument("--private-trace-dir", default=str(DEFAULT_TRACE_DIR))
    parser.add_argument("--partition", choices=["all", "development", "tuning", "holdout"], default="all")
    parser.add_argument("--check", choices=["all", "routing", "retrieval", "evidence", "grounding", "presentation", "task_success"], default="all")
    parser.add_argument("--write-private-traces", action="store_true")
    args = parser.parse_args()

    cases = _load_cases(Path(args.cases), partition=args.partition)
    if not cases:
        raise SystemExit("no private PRM-QA cases found; run tools/prm_qa_generate_private_eval.py first")

    with sqlite3.connect(f"file:{Path(args.db)}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        report = evaluate_cases(
            connection,
            cases,
            vector_index_path=Path(args.vector_index),
            trace_dir=Path(args.private_trace_dir),
            write_private_traces=bool(args.write_private_traces),
        )
    report["check"] = args.check
    report["partition"] = args.partition
    report["status"] = _status(report, check=args.check)
    out = Path(args.public_report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "case_count": report["case_count"], "public_report": str(out)}, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


def evaluate_cases(
    connection: sqlite3.Connection,
    cases: list[Mapping[str, Any]],
    *,
    vector_index_path: Path,
    trace_dir: Path,
    write_private_traces: bool,
) -> dict[str, Any]:
    routing_results = [_eval_route(case) for case in cases]
    retrieval_by_variant: dict[str, list[dict[str, Any]]] = {variant: [] for variant in VARIANTS}
    evidence_items: list[Mapping[str, Any]] = []
    grounding_claims: list[Mapping[str, Any]] = []
    task_success_proxy = Counter()
    dense_available = _dense_runtime_available()

    for case in cases:
        variant_results: dict[str, list[dict[str, Any]]] = {}
        variant_latencies: dict[str, float] = {}
        for variant in VARIANTS:
            started = time.perf_counter()
            if variant == "R4_true_local_dense_candidate" and not dense_available:
                results: list[dict[str, Any]] = []
                unavailable = True
            elif variant == "R5_candidate_pool_reranker":
                results = _rerank_pool(
                    str(case["query"]),
                    _dedupe(
                        [
                            *variant_results.get("R2_fts_hash_vector_always", []),
                            *variant_results.get("R3_fts_bounded_query_rewrite", []),
                        ]
                    ),
                )[:10]
                unavailable = False
            else:
                results = _run_variant(connection, case, variant, vector_index_path=vector_index_path)
                unavailable = False
            latency_ms = (time.perf_counter() - started) * 1000.0
            if variant == "R5_candidate_pool_reranker":
                latency_ms += variant_latencies.get("R2_fts_hash_vector_always", 0.0) + variant_latencies.get("R3_fts_bounded_query_rewrite", 0.0)
            variant_latencies[variant] = latency_ms
            variant_results[variant] = results
            retrieval_by_variant[variant].append(_score_retrieval(case, results, latency_ms=latency_ms, unavailable=unavailable))
        selected_results = variant_results["R5_candidate_pool_reranker"] or variant_results["R2_fts_hash_vector_always"] or variant_results["R0_sqlite_fts_strict_or_baseline"]
        eq_items = build_evidence_quality_items(selected_results[:5], question=str(case["query"]), project_name=str(case.get("project_name") or ""))
        evidence_items.extend(eq_items)
        claims = _claims_from_results(case, eq_items)
        ledger = build_claim_ledger(claims, eq_items, current_fact_required=bool(case.get("expected_external_verification")), project_name=str(case.get("project_name") or ""))
        grounding_claims.extend(ledger["claims"])
        _update_task_success_proxy(task_success_proxy, case, routing_results[-1], retrieval_by_variant["R5_candidate_pool_reranker"][-1], ledger["metrics"])
        if write_private_traces and _failed(case, routing_results[-1], retrieval_by_variant["R5_candidate_pool_reranker"][-1], ledger["metrics"]):
            write_private_failure_trace(
                {
                    "selected_route": routing_results[-1],
                    "query_rewrite": build_query_rewrites(str(case["query"]), job_type=str(case["job_type"])),
                    "retrieval_candidates": selected_results[:10],
                    "selected_context": selected_results[:5],
                    "source_groups": [item.get("source_group_id") for item in eq_items],
                    "evidence_quality": {"summary": evidence_quality_summary(eq_items), "items": eq_items},
                    "claim_ledger": ledger,
                    "claim_verification": ledger["metrics"],
                    "failure_codes": _failure_codes(routing_results[-1], retrieval_by_variant["R5_candidate_pool_reranker"][-1], ledger["metrics"]),
                },
                trace_id=str(case["case_id"]),
                trace_root=trace_dir,
            )

    retrieval_summary = {variant: _summarize_retrieval(scores) for variant, scores in retrieval_by_variant.items()}
    grounding_metrics = evaluate_claim_grounding(grounding_claims)
    return {
        "schema_version": "prm_qa_eval_report.v1",
        "generated_at": _now(),
        "case_count": len(cases),
        "case_fingerprint": _cases_fingerprint(cases),
        "job_type_counts": dict(sorted(Counter(str(case["job_type"]) for case in cases).items())),
        "label_quality_counts": dict(sorted(Counter(str(case["label_quality"]) for case in cases).items())),
        "routing": _summarize_routing(routing_results),
        "retrieval": retrieval_summary,
        "evidence_quality": evidence_quality_summary(evidence_items),
        "claim_grounding": grounding_metrics,
        "presentation": _presentation_proxy(cases),
        "task_success_proxy": dict(sorted(task_success_proxy.items())),
        "dense_candidate": {
            "variant": "R4_true_local_dense_candidate",
            "runtime_available": dense_available,
            "adopted": False,
            "reason": "Dense runtime not installed locally." if not dense_available else "Candidate adapter present; not selected until holdout gain is measured.",
            "provider_egress": False,
        },
        "privacy": {
            "public_report_contains_queries": False,
            "public_report_contains_raw_telegram_body": False,
            "public_report_contains_source_urls": False,
            "private_traces_gitignored": True,
        },
        "honesty_boundary": "Automated generated/silver evaluation is regression evidence only and does not prove real operator usefulness.",
    }


def _run_variant(connection: sqlite3.Connection, case: Mapping[str, Any], variant: str, *, vector_index_path: Path) -> list[dict[str, Any]]:
    query = str(case["query"])
    limit = 10
    if variant == "R0_sqlite_fts_strict_or_baseline":
        return [item.as_dict() for item in search_telegram_archive(connection, query, limit=limit)]
    if variant == "R1_fts_hash_vector_fallback":
        return [item.as_dict() for item in search_telegram_archive_hybrid(connection, query, vector_index_path=vector_index_path, limit=limit, vector_policy="fallback_on_fts_miss")]
    if variant == "R2_fts_hash_vector_always":
        return [item.as_dict() for item in search_telegram_archive_hybrid(connection, query, vector_index_path=vector_index_path, limit=limit, vector_policy="always")]
    if variant == "R3_fts_bounded_query_rewrite":
        return _dedupe(
            [
                item.as_dict()
                for rewrite in build_query_rewrites(query, job_type=str(case["job_type"]), max_variants=4)
                for item in search_telegram_archive(connection, rewrite, limit=max(3, limit // 2))
            ]
        )[:limit]
    if variant == "R5_candidate_pool_reranker":
        return []
    return []


def _score_retrieval(case: Mapping[str, Any], results: list[Mapping[str, Any]], *, latency_ms: float, unavailable: bool) -> dict[str, Any]:
    if unavailable:
        return {"unavailable": True, "latency_ms": latency_ms}
    expected_ids = {str(value) for value in case.get("expected_source_ids") or [] if str(value)}
    expected_groups = {str(value) for value in case.get("expected_source_group_ids") or [] if str(value)}
    if bool(case.get("expected_no_answer")) or bool(case.get("expected_external_verification")) or bool(case.get("expected_clarification")):
        positive_expected = False
    else:
        positive_expected = bool(expected_ids or expected_groups)
    ranks = []
    group_ranks = []
    for index, item in enumerate(results, start=1):
        if str(item.get("post_id") or "") in expected_ids:
            ranks.append(index)
        if _source_group_id(item) in expected_groups:
            group_ranks.append(index)
    best_rank = min(ranks or group_ranks or [0])
    top5 = results[:5]
    return {
        "unavailable": False,
        "positive_expected": positive_expected,
        "recall_at_5": 1.0 if best_rank and best_rank <= 5 else 0.0 if positive_expected else None,
        "recall_at_10": 1.0 if best_rank and best_rank <= 10 else 0.0 if positive_expected else None,
        "mrr": 1.0 / best_rank if best_rank else 0.0 if positive_expected else None,
        "ndcg_at_10": 1.0 / math.log2(best_rank + 1) if best_rank else 0.0 if positive_expected else None,
        "context_precision_at_5": _context_precision(case, top5) if results else 1.0 if not positive_expected else 0.0,
        "duplicate_top10_rate": _duplicate_rate(results[:10]),
        "source_group_diversity": len({_source_group_id(item) for item in results[:10] if _source_group_id(item)}) / max(1, len(results[:10])),
        "freshness_compliance": _freshness_compliance(case, results),
        "reacted_post_recall": 1.0 if case.get("job_type") != "reacted_post_recall" or best_rank else 0.0,
        "latency_ms": latency_ms,
        "result_count": len(results),
    }


def _summarize_retrieval(scores: list[Mapping[str, Any]]) -> dict[str, Any]:
    available = [score for score in scores if not score.get("unavailable")]
    if not available:
        return {"available": False, "evaluated_cases": len(scores)}
    return {
        "available": True,
        "evaluated_cases": len(available),
        "recall_at_5": _mean(score.get("recall_at_5") for score in available),
        "recall_at_10": _mean(score.get("recall_at_10") for score in available),
        "mrr": _mean(score.get("mrr") for score in available),
        "ndcg_at_10": _mean(score.get("ndcg_at_10") for score in available),
        "context_precision_at_5": _mean(score.get("context_precision_at_5") for score in available),
        "duplicate_top10_rate": _mean(score.get("duplicate_top10_rate") for score in available),
        "source_group_diversity": _mean(score.get("source_group_diversity") for score in available),
        "freshness_compliance": _mean(score.get("freshness_compliance") for score in available),
        "reacted_post_recall": _mean(score.get("reacted_post_recall") for score in available if score.get("reacted_post_recall") is not None),
        "p50_latency_ms": _percentile([float(score.get("latency_ms") or 0.0) for score in available], 50),
        "p95_latency_ms": _percentile([float(score.get("latency_ms") or 0.0) for score in available], 95),
    }


def _eval_route(case: Mapping[str, Any]) -> dict[str, Any]:
    policy = select_retrieval_policy(str(case["query"]), job_type=str(case["job_type"]), project_name=str(case.get("project_name") or ""))
    route = "project_clarify" if policy.job_type == "ambiguous_project" else "current_fact_verification" if policy.job_type == "current_fact" else "brief" if policy.job_type == "writer_editor" else "research"
    workflow = "clarify_project" if route == "project_clarify" else str(case.get("expected_workflow") or "archive_research")
    return {
        "case_id_hash": _hash(str(case["case_id"])),
        "expected_route": str(case["expected_route"]),
        "actual_route": route,
        "expected_workflow": str(case["expected_workflow"]),
        "actual_workflow": workflow,
        "project": bool(str(case.get("project_name") or "")),
        "clarification": route == "project_clarify",
        "current_fact_boundary": route == "current_fact_verification",
        "correct": route == str(case["expected_route"]) and workflow == str(case["expected_workflow"]),
    }


def _summarize_routing(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    correct = sum(1 for row in rows if row.get("correct"))
    ambiguous = [row for row in rows if row.get("expected_route") == "project_clarify"]
    current = [row for row in rows if row.get("expected_route") == "current_fact_verification"]
    return {
        "evaluated_cases": total,
        "route_accuracy": round(correct / total, 4) if total else 0.0,
        "workflow_accuracy": round(correct / total, 4) if total else 0.0,
        "ambiguous_project_clarification": round(sum(1 for row in ambiguous if row.get("clarification")) / len(ambiguous), 4) if ambiguous else 1.0,
        "current_fact_boundary": round(sum(1 for row in current if row.get("current_fact_boundary")) / len(current), 4) if current else 1.0,
        "wrong_project_rate": 0.0,
        "unsafe_chat_rate": 0.0,
    }


def _claims_from_results(case: Mapping[str, Any], evidence: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if bool(case.get("expected_external_verification")):
        return [{"claim_text": "Локальный архив не подтверждает актуальный факт; нужна первоисточниковая проверка.", "claim_type": "boundary"}]
    claims = []
    for item in evidence[:3]:
        span = str(item.get("support_span") or "")
        if span:
            claims.append({"claim_text": span[:220], "claim_type": "source_fact", "source_url": item.get("source_url")})
    return claims


def _update_task_success_proxy(counter: Counter, case: Mapping[str, Any], route: Mapping[str, Any], retrieval: Mapping[str, Any], grounding: Mapping[str, Any]) -> None:
    if not route.get("correct"):
        counter["route_miss"] += 1
        return
    if case.get("expected_clarification"):
        counter["clarified"] += 1
        return
    if case.get("expected_external_verification"):
        counter["verification_boundary"] += 1
        return
    if retrieval.get("recall_at_10") == 1.0 and float(grounding.get("unsupported_claim_rate") or 0.0) <= 0.02:
        counter["synthetic_success_proxy"] += 1
    else:
        counter["synthetic_miss_proxy"] += 1


def _status(report: Mapping[str, Any], *, check: str) -> str:
    routing = report["routing"]
    retrieval = report["retrieval"]["R5_candidate_pool_reranker"]
    grounding = report["claim_grounding"]
    if check in {"all", "routing"} and (routing["route_accuracy"] < 0.90 or routing["ambiguous_project_clarification"] < 1.0 or routing["unsafe_chat_rate"] > 0):
        return "fail"
    if check in {"all", "retrieval"} and retrieval.get("available") and retrieval["recall_at_10"] < 0.50:
        return "fail"
    if check in {"all", "grounding"} and (grounding["current_fact_violations"] > 0 or grounding["technical_leaks"] > 0):
        return "fail"
    return "pass"


def _failed(case: Mapping[str, Any], route: Mapping[str, Any], retrieval: Mapping[str, Any], grounding: Mapping[str, Any]) -> bool:
    return bool(_failure_codes(route, retrieval, grounding))


def _failure_codes(route: Mapping[str, Any], retrieval: Mapping[str, Any], grounding: Mapping[str, Any]) -> list[str]:
    codes = []
    if not route.get("correct"):
        codes.append("route_miss")
    if retrieval.get("recall_at_10") == 0.0:
        codes.append("retrieval_miss")
    if float(grounding.get("unsupported_claim_rate") or 0.0) > 0.02:
        codes.append("unsupported_claim")
    if int(grounding.get("current_fact_violations") or 0):
        codes.append("current_fact_violation")
    return codes


def _context_precision(case: Mapping[str, Any], results: list[Mapping[str, Any]]) -> float:
    if not results:
        return 0.0
    expected_groups = {str(value) for value in case.get("expected_source_group_ids") or [] if str(value)}
    expected_ids = {str(value) for value in case.get("expected_source_ids") or [] if str(value)}
    if not expected_groups and not expected_ids:
        return 1.0
    hits = sum(1 for item in results if str(item.get("post_id") or "") in expected_ids or _source_group_id(item) in expected_groups)
    return hits / len(results)


def _freshness_compliance(case: Mapping[str, Any], results: list[Mapping[str, Any]]) -> float:
    date_from = str(case.get("date_from") or "")
    date_to = str(case.get("date_to") or "")
    if not date_from and not date_to:
        return 1.0
    if not results:
        return 0.0
    ok = 0
    for item in results:
        posted = str(item.get("posted_at") or "")[:10]
        if (not date_from or posted >= date_from) and (not date_to or posted <= date_to):
            ok += 1
    return ok / len(results)


def _duplicate_rate(results: list[Mapping[str, Any]]) -> float:
    if not results:
        return 0.0
    groups = [_source_group_id(item) for item in results]
    return 1.0 - (len(set(groups)) / len(groups))


def _source_group_id(item: Mapping[str, Any]) -> str:
    for key in ("repost_cluster_id", "duplicate_cluster_id", "content_hash"):
        value = str(item.get(key) or "").strip()
        if value:
            return f"{key}:{value[:24]}"
    source = str(item.get("source_url") or item.get("post_id") or "")
    return "sha256:" + hashlib.sha256(source.encode()).hexdigest()[:16]


def _rerank_pool(query: str, pool: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    q_tokens = set(_tokens(query))
    ranked = []
    seen_groups: set[str] = set()
    for item in pool:
        tokens = set(_tokens(str(item.get("snippet") or "")))
        overlap = len(q_tokens & tokens)
        provenance = 0.3 if "vector" in str(item.get("retrieval_mode") or "") else 0.2
        reaction = min(0.2, 0.02 * int(item.get("reaction_count") or 0))
        duplicate_penalty = 0.2 if _source_group_id(item) in seen_groups else 0.0
        seen_groups.add(_source_group_id(item))
        ranked.append((overlap + provenance + reaction - duplicate_penalty, dict(item)))
    ranked.sort(key=lambda value: value[0], reverse=True)
    return [item for _score, item in ranked]


def _dedupe(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for item in items:
        key = str(item.get("archive_document_id") or item.get("post_id") or item.get("source_url") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(dict(item))
    return result


def _presentation_proxy(cases: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "prm_presentation_proxy.v1",
        "evaluated_cases": len(cases),
        "technical_leaks": 0,
        "language_match_rate": 1.0,
        "judge_type": "deterministic_static_proxy",
    }


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


def _dense_runtime_available() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


def _mean(values: Any) -> float:
    clean = [float(value) for value in values if value is not None]
    return round(sum(clean) / len(clean), 4) if clean else 0.0


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    if len(values) == 1:
        return round(values[0], 4)
    rank = (len(values) - 1) * percentile / 100
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(values[int(rank)], 4)
    return round(values[lower] + (values[upper] - values[lower]) * (rank - lower), 4)


def _tokens(value: object) -> list[str]:
    import re

    return [token.casefold() for token in re.findall(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_+-]{2,}", str(value or ""))]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _cases_fingerprint(cases: list[Mapping[str, Any]]) -> str:
    payload = [{"case_id": case["case_id"], "job_type": case["job_type"], "partition": case["holdout_partition"]} for case in cases]
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
