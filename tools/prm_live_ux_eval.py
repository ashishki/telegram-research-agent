#!/usr/bin/env python3
"""Run a privacy-safe, live PRM UX evaluation over the local archive.

The harness deliberately exercises the same router, local retrieval and
Telegram renderer used by the manual assistant.  It never sends Telegram
messages or writes to SQLite.  ``--live`` additionally uses the configured
LLM router and a bounded LLM judge; its receipt contains metrics and case
fingerprints only, never questions, answers, snippets, links, or chat ids.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

TOPICS = (
    "agent evals", "RAG retrieval", "AI adoption", "LLM agents", "prompt engineering",
    "контекст-инжиниринг", "мультиагентные системы", "AI product management", "LLM safety",
    "качество ответов", "vector search", "knowledge management", "research workflows",
    "AI coding", "developer productivity", "enterprise AI", "model evaluation", "tool use",
    "long context", "memory systems", "AI strategy", "data quality", "human in the loop",
    "agent reliability", "AI transformation",
)
PRIVATE_RECEIPT_ROOT = (Path(__file__).resolve().parents[1] / "data" / "events").resolve()
JUDGE_MIN_SCORE = 4


def build_cases() -> list[dict[str, str]]:
    """Return exactly 100 generated user scenarios, without operator input."""
    cases: list[dict[str, str]] = []
    for topic in TOPICS:
        cases.extend(
            (
                {"kind": "research", "question": f"Что в моём архиве было про {topic} и что мне с этим делать?", "expected": "research"},
                {"kind": "brief", "question": f"Собери опорные тезисы для поста про {topic}.", "expected": "brief"},
                {"kind": "decision", "question": f"Какие практические выводы для моего проекта можно сделать из материалов про {topic}?", "expected": "research"},
                {"kind": "current_fact", "question": f"Что сейчас самое новое и важное про {topic}?", "expected": "research"},
            )
        )
    assert len(cases) == 100
    return cases


def _case_id(case: Mapping[str, str]) -> str:
    material = f"prm-live-ux-eval.v1:{case['kind']}:{case['question']}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:16]


def _has_technical_leak(text: str) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in (
        "model_calls", "estimated_cost", "tool_calls=", "retrieval_mode", "raw_telegram_corpus",
        "bounded_telegram", "vector_backend", "/srv/", "traceback",
    ))


def _judge_answer(question: str, answer: str, *, source_count: int, current_fact_boundary: bool) -> dict[str, Any]:
    from llm.client import LLMClient

    prompt = (
        "Score this private Telegram-assistant answer as a demanding user and UX designer. "
        "Judge only the supplied answer; do not add facts. Return JSON only with keys "
        "score (integer 1..5), clear (boolean), action_oriented (boolean), grounded (boolean), "
        "technical_leak (boolean), reason (max 160 chars).\n"
        f"Question: {question}\nSource count: {source_count}\n"
        f"Current-fact boundary required: {str(current_fact_boundary).lower()}\n"
        f"Answer:\n{answer[:5000]}"
    )
    receipt = LLMClient.complete_with_receipt(
        prompt=prompt,
        system="You are a strict, concise evaluator. Do not reveal or repeat private source text.",
        category="pi_chat",
        max_tokens=220,
    )
    result = json.loads(str(receipt.text or "").strip().removeprefix("```json").removesuffix("```").strip())
    if not isinstance(result, Mapping):
        raise ValueError("judge returned non-object JSON")
    return {
        "score": max(1, min(5, int(result.get("score") or 1))),
        "clear": bool(result.get("clear")),
        "action_oriented": bool(result.get("action_oriented")),
        "grounded": bool(result.get("grounded")),
        "technical_leak": bool(result.get("technical_leak")),
    }


def _egress_allowed() -> bool:
    return os.environ.get("PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS", "").strip().casefold() in {"1", "true", "yes", "approved"}


def _private_receipt_path(path: Path) -> Path:
    resolved = path.resolve()
    if resolved != PRIVATE_RECEIPT_ROOT and PRIVATE_RECEIPT_ROOT not in resolved.parents:
        raise ValueError(f"receipt path must be under {PRIVATE_RECEIPT_ROOT}")
    return resolved


def run(*, live: bool, case_limit: int, case_offset: int, max_provider_calls: int) -> dict[str, Any]:
    # Imports are intentionally delayed: live mode inherits the runtime flags;
    # dry mode disables egress before handler code sees them.
    if not live:
        os.environ["PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS"] = "0"
        os.environ["PRM_TELEGRAM_AUTO_LLM_ROUTER"] = "0"
        os.environ["PRM_TELEGRAM_RAG_LLM_SYNTHESIS"] = "0"
    from assistant.memory_research import MemoryResearchBudget, answer_memory_research, render_memory_research_answer, render_memory_research_brief
    from bot.handlers import _render_telegram_research_response, _route_auto_message
    from config.settings import load_settings
    from llm.client import LLMClient, suppress_usage_recording
    import llm.client as llm_client

    cases = build_cases()[case_offset : case_offset + case_limit]
    results: list[dict[str, Any]] = []
    provider_calls = 0
    original_complete_json = LLMClient.complete_json
    original_complete_with_receipt = LLMClient.complete_with_receipt
    original_max_retries = llm_client.MAX_RETRIES

    def _count_provider_call(callable_):
        def wrapped(*args: Any, **kwargs: Any):
            nonlocal provider_calls
            if provider_calls >= max_provider_calls:
                raise RuntimeError("prm_live_ux_eval_provider_call_budget_exhausted")
            provider_calls += 1
            return callable_(*args, **kwargs)
        return wrapped

    if live:
        llm_client.MAX_RETRIES = 1
        LLMClient.complete_json = staticmethod(_count_provider_call(original_complete_json))
        LLMClient.complete_with_receipt = staticmethod(_count_provider_call(original_complete_with_receipt))
    try:
        for case in cases:
            case_id = _case_id(case)
            with suppress_usage_recording():
                route = _route_auto_message(f"prm-live-eval-{case_id}", case["question"])
            route_mode = str(route.get("mode") or "")
            budget = MemoryResearchBudget(
            max_tool_calls=4, max_archive_sources=5, max_linked_sources=3, max_retries=0,
            timeout_seconds=30, max_prompt_chars=8000, max_model_calls=0, max_cost_usd=0.0,
            allow_open_browsing=False, allow_provider_egress=False,
            allow_vector_retrieval=os.environ.get("PRM_ARCHIVE_HYBRID_RETRIEVAL", "").casefold() in {"1", "true", "yes", "approved"},
            vector_index_path=os.environ.get("PRM_ARCHIVE_VECTOR_INDEX_PATH", ""),
        )
            payload = answer_memory_research(case["question"], settings=load_settings(), limit=5, budget=budget)
            local_text = render_memory_research_brief(payload) if route_mode == "brief" else render_memory_research_answer(payload)
            current_boundary = bool((payload.get("answer_gate") or {}).get("external_verification_required"))
            with suppress_usage_recording():
                answer = _render_telegram_research_response(payload, local_text=local_text, mode=route_mode if route_mode == "brief" else "research")
            source_count = len((payload.get("archive_evidence") or {}).get("items") or []) + len((payload.get("linked_source_evidence") or {}).get("items") or [])
            deterministic_failures: list[str] = []
            if route_mode != case["expected"]:
                deterministic_failures.append("route")
            if case["kind"] == "current_fact" and not current_boundary:
                deterministic_failures.append("current_fact_boundary")
            if not answer.strip():
                deterministic_failures.append("empty_answer")
            if _has_technical_leak(answer):
                deterministic_failures.append("technical_leak")
            if bool((payload.get("privacy") or {}).get("durable_writes")):
                deterministic_failures.append("durable_write")
            judge: dict[str, Any] | None = None
            if live:
                try:
                    with suppress_usage_recording():
                        judge = _judge_answer(case["question"], answer, source_count=source_count, current_fact_boundary=current_boundary)
                    if judge["technical_leak"]:
                        deterministic_failures.append("judge_technical_leak")
                    if judge["score"] < JUDGE_MIN_SCORE:
                        deterministic_failures.append("judge_score")
                    if not judge["clear"]:
                        deterministic_failures.append("judge_unclear")
                    if not judge["grounded"]:
                        deterministic_failures.append("judge_ungrounded")
                except Exception as exc:  # Preserve the other 99 results if a provider call fails.
                    deterministic_failures.append("judge_error")
                    judge = {"error_class": type(exc).__name__}
            results.append({
                "case_id": case_id, "kind": case["kind"], "expected_route": case["expected"],
                "actual_route": route_mode, "router": str(route.get("router") or ""),
                "source_count": source_count, "current_fact_boundary": current_boundary,
                "answer_chars": len(answer), "failures": deterministic_failures, "judge": judge,
            })
    finally:
        if live:
            LLMClient.complete_json = staticmethod(original_complete_json)
            LLMClient.complete_with_receipt = staticmethod(original_complete_with_receipt)
            llm_client.MAX_RETRIES = original_max_retries

    failures = [item for item in results if item["failures"]]
    judge_scores = [int(item["judge"]["score"]) for item in results if isinstance(item.get("judge"), Mapping) and "score" in item["judge"]]
    return {
        "schema_version": "prm_live_ux_eval_receipt.v1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "live_llm_judge": live,
        "case_count": len(results),
        "case_offset": case_offset,
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "average_judge_score": round(sum(judge_scores) / len(judge_scores), 2) if judge_scores else None,
        "routes": dict(sorted(Counter(item["actual_route"] for item in results).items())),
        "router_implementations": dict(sorted(Counter(item["router"] for item in results).items())),
        "judge_scored_cases": len(judge_scores),
        "provider_calls": provider_calls,
        "provider_call_budget": max_provider_calls if live else 0,
        "provider_retry_limit": 1 if live else 0,
        "judge_threshold": {"minimum_score": JUDGE_MIN_SCORE, "requires_clear": True, "requires_grounded": True},
        "failure_counts": dict(sorted(Counter(reason for item in failures for reason in item["failures"]).items())),
        "cases": results,
        "privacy": {
            "raw_questions_or_answers_stored": False,
            "raw_telegram_corpus_stored": False,
            "telegram_messages_sent": False,
            "durable_writes_requested": False,
            "bounded_provider_egress": live,
            "provider_egress_contract": (
                "bounded Telegram-rendered/source-derived answer (maximum 5000 characters) plus question; no writes"
                if live else "none"
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Enable configured LLM router and bounded LLM judge.")
    parser.add_argument("--confirm-live-eval", action="store_true", help="Required together with --live.")
    parser.add_argument("--cases", type=int, default=100, choices=range(1, 101))
    parser.add_argument("--offset", type=int, default=0, choices=range(0, 100))
    parser.add_argument("--max-provider-calls", type=int, default=300, choices=range(1, 301))
    parser.add_argument("--receipt", type=Path, help="Optional gitignored aggregate-only receipt path.")
    args = parser.parse_args()
    if args.live and not args.confirm_live_eval:
        parser.error("--live requires --confirm-live-eval")
    if args.live and not _egress_allowed():
        parser.error("--live requires PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1 (or approved equivalent)")
    receipt = run(live=args.live, case_limit=args.cases, case_offset=args.offset, max_provider_calls=args.max_provider_calls)
    if args.receipt:
        receipt_path = _private_receipt_path(args.receipt)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    public = {key: value for key, value in receipt.items() if key != "cases"}
    print(json.dumps(public, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
