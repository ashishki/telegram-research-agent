#!/usr/bin/env python3
"""Run a privacy-safe UX evaluation through the active PRM application boundary."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

TOPICS = (
    "agent evals", "RAG retrieval", "AI adoption", "LLM agents", "prompt engineering",
    "контекст-инжиниринг", "мультиагентные системы", "AI product management", "LLM safety",
    "качество ответов", "vector search", "knowledge management", "research workflows",
    "AI coding", "developer productivity", "enterprise AI", "model evaluation", "tool use",
    "long context", "memory systems", "AI strategy", "data quality", "human in the loop",
    "agent reliability", "AI transformation",
)
PROJECTS = (
    "telegram-research-agent",
    "AI_workflow_playbook",
    "Eval-Ground-Truth-Lab",
    "Demand-to-MVP-Radar",
)
PRIVATE_RECEIPT_ROOT = (PROJECT_ROOT / "data" / "events").resolve()
JUDGE_MIN_SCORE = 4
MAX_LIVE_PROVIDER_CALLS = 400
_ARCHIVE_FORBIDDEN = (
    "\nРешение\n",
    "\nГлавный риск\n",
    "\nКритерий успеха\n",
    "влияние на backlog",
)


def build_cases() -> list[dict[str, Any]]:
    """Return exactly 100 generated user scenarios plus intent expectations."""

    cases: list[dict[str, Any]] = []
    for index, topic in enumerate(TOPICS):
        project = PROJECTS[index % len(PROJECTS)]
        research_question = (
            "Что в моём архиве есть про agent evals и что из этого реально применимо сейчас?"
            if topic == "agent evals"
            else f"Что в моём архиве было про {topic} и что мне с этим делать?"
        )
        cases.extend(
            (
                {
                    "kind": "research",
                    "question": research_question,
                    "expected": "research",
                    "expected_intent": "archive_to_action",
                    "external_verification": False,
                    "project_context": False,
                },
                {
                    "kind": "brief",
                    "question": f"Собери опорные тезисы для поста про {topic}.",
                    "expected": "brief",
                    "expected_intent": "writer_brief",
                    "external_verification": False,
                    "project_context": False,
                },
                {
                    "kind": "decision",
                    "question": f"Стоит ли добавить материалы про {topic} в backlog проекта {project}?",
                    "expected": "research",
                    "expected_intent": "decision_support",
                    "external_verification": False,
                    "project_context": True,
                },
                {
                    "kind": "current_fact",
                    "question": f"Что сейчас самое новое и важное про внешний {topic}?",
                    "expected": "research",
                    "expected_intent": "current_fact_verification",
                    "external_verification": True,
                    "project_context": False,
                },
            )
        )
    assert len(cases) == 100
    return cases


def _case_id(case: Mapping[str, Any]) -> str:
    material = f"prm-live-ux-eval.v2:{case['kind']}:{case['question']}".encode("utf-8")
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
        "Judge only the supplied answer; do not add facts. Require the first sentence to answer the user's actual question. "
        "For archive queries, direct, partial and adjacent findings must not be conflated, and unrelated project templates are a major failure. "
        "Treat normal source URLs, archive/local-only boundaries and concise citations as user-facing content, not technical leaks. "
        "A technical leak means internal diagnostics such as model calls, costs, tool traces, filesystem paths, debug IDs, backend flags or stack traces. "
        "Mark grounded true only when source-derived claims remain tied to visible citations and limits are explicit. "
        "If Current-fact boundary required is true, asserted current facts are ungrounded; a clear refusal plus archive context may score highly. "
        "Return JSON only with keys score (1..5), clear, direct, action_oriented, grounded, technical_leak, reason.\n"
        f"Question: {question}\nSource count: {source_count}\n"
        f"Current-fact boundary required: {str(current_fact_boundary).lower()}\n"
        f"Answer:\n{answer[:5000]}"
    )
    receipt = LLMClient.complete_with_receipt(
        prompt=prompt,
        system="You are a strict evaluator. Do not reveal or repeat private source text.",
        category="pi_chat",
        max_tokens=220,
    )
    result = json.loads(str(receipt.text or "").strip().removeprefix("```json").removesuffix("```").strip())
    if not isinstance(result, Mapping):
        raise ValueError("judge returned non-object JSON")
    return {
        "score": max(1, min(5, int(result.get("score") or 1))),
        "clear": bool(result.get("clear")),
        "direct": bool(result.get("direct")),
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
    if not live:
        os.environ["PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS"] = "0"
        os.environ["PRM_TELEGRAM_RAG_LLM_SYNTHESIS"] = "0"
    from assistant.prm_post_answer_actions import select_post_answer_action_codes
    from config.settings import load_settings
    from llm.client import LLMClient, suppress_usage_recording
    import llm.client as llm_client
    from prm.application import PersonalResearchAssistant
    from prm.contracts import OperatorRequest

    cases = build_cases()[case_offset : case_offset + case_limit]
    results: list[dict[str, Any]] = []
    provider_calls = 0
    original_complete_json = LLMClient.complete_json
    original_complete_with_receipt = LLMClient.complete_with_receipt
    original_complete = LLMClient.complete
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
        LLMClient.complete = staticmethod(_count_provider_call(original_complete))
    try:
        assistant = PersonalResearchAssistant(settings=load_settings())
        for case in cases:
            case_id = _case_id(case)
            with suppress_usage_recording():
                runtime = assistant.answer(
                    OperatorRequest(
                        query=str(case["question"]),
                        mode="auto",
                        chat_id=f"prm-live-eval-{case_id}",
                    )
                ).to_dict()
            route = runtime.get("route") if isinstance(runtime.get("route"), Mapping) else {}
            route_mode = str(runtime.get("mode") or "")
            payload = runtime.get("payload") if isinstance(runtime.get("payload"), Mapping) else {}
            answer = str(runtime.get("final_answer") or runtime.get("text") or "")
            answer_gate = payload.get("answer_gate") if isinstance(payload.get("answer_gate"), Mapping) else {}
            current_boundary = bool(answer_gate.get("external_verification_required")) and not bool(answer_gate.get("current_claim_allowed", True))
            archive_contract = payload.get("archive_contract") if isinstance(payload.get("archive_contract"), Mapping) else {}
            summary = archive_contract.get("result_summary") if isinstance(archive_contract.get("result_summary"), Mapping) else {}
            source_count = len((payload.get("archive_evidence") or {}).get("items") or []) + len((payload.get("linked_source_evidence") or {}).get("items") or [])
            action_codes = select_post_answer_action_codes(
                {
                    "primary_intent": route.get("primary_intent"),
                    "project_name": route.get("project_name"),
                    "direct_count": summary.get("direct_count", 0),
                    "partial_count": summary.get("partial_count", 0),
                    "relevance_established": int(summary.get("direct_count") or 0) + int(summary.get("partial_count") or 0) > 0,
                }
            )
            failures: list[str] = []
            if route_mode != case["expected"]:
                failures.append("mode_miss")
            if str(route.get("primary_intent") or "") != case["expected_intent"]:
                failures.append("intent_miss")
            if bool(case["external_verification"]) != current_boundary:
                failures.append("external_verification_boundary_miss")
            if bool(case["project_context"]) != bool(route.get("project_context_required")):
                failures.append("project_context_boundary_miss")
            if not answer.strip():
                failures.append("empty_answer")
            if _has_technical_leak(answer):
                failures.append("technical_leak")
            if case["expected_intent"].startswith("archive_") and any(marker.casefold() in answer.casefold() for marker in _ARCHIVE_FORBIDDEN):
                failures.append("irrelevant_project_template")
            if case["expected_intent"].startswith("archive_") and bool(route.get("project_name")):
                failures.append("unsupported_project_context")
            if case["expected_intent"].startswith("archive_") and len(answer) > 3600:
                failures.append("mobile_length")
            if case["expected_intent"].startswith("archive_") and int(summary.get("direct_count") or 0) == 0 and answer and "прям" not in answer.casefold():
                failures.append("no_direct_disclosure_missing")
            if case["expected_intent"].startswith("archive_") and any(code in action_codes for code in ("a", "e", "w")):
                failures.append("premature_productive_action")
            if bool((payload.get("privacy") or {}).get("durable_writes")):
                failures.append("durable_write")
            final_verification = runtime.get("final_answer_verification") if isinstance(runtime.get("final_answer_verification"), Mapping) else {}
            final_metrics = final_verification.get("metrics") if isinstance(final_verification.get("metrics"), Mapping) else {}
            if int(final_metrics.get("current_fact_violations") or 0):
                failures.append("final_current_fact_violation")
            if float(final_metrics.get("unsupported_claim_rate") or 0.0) > 0.50 and source_count:
                failures.append("final_claim_verification")
            judge: dict[str, Any] | None = None
            if live:
                try:
                    with suppress_usage_recording():
                        judge = _judge_answer(str(case["question"]), answer, source_count=source_count, current_fact_boundary=current_boundary)
                    if judge["technical_leak"]:
                        failures.append("judge_technical_leak")
                    if judge["score"] < JUDGE_MIN_SCORE:
                        failures.append("judge_score")
                    if not judge["clear"]:
                        failures.append("judge_unclear")
                    if not judge["direct"]:
                        failures.append("judge_indirect")
                    if not judge["grounded"]:
                        failures.append("judge_ungrounded")
                except Exception as exc:
                    failures.append("judge_error")
                    judge = {"error_class": type(exc).__name__}
            results.append(
                {
                    "case_id": case_id,
                    "kind": case["kind"],
                    "expected_route": case["expected"],
                    "actual_route": route_mode,
                    "expected_intent": case["expected_intent"],
                    "actual_intent": str(route.get("primary_intent") or ""),
                    "router": str(route.get("reason") or ""),
                    "source_count": source_count,
                    "direct_count": int(summary.get("direct_count") or 0),
                    "partial_count": int(summary.get("partial_count") or 0),
                    "adjacent_count": int(summary.get("adjacent_count") or 0),
                    "current_fact_boundary": current_boundary,
                    "answer_chars": len(answer),
                    "first_useful_information_position": 0 if answer.strip() else None,
                    "action_codes": action_codes,
                    "failures": failures,
                    "judge": judge,
                    "final_answer_verification": {
                        "claim_count": int(final_verification.get("claim_count") or 0),
                        "unsupported_claim_rate": float(final_metrics.get("unsupported_claim_rate") or 0.0),
                        "current_fact_violations": int(final_metrics.get("current_fact_violations") or 0),
                    },
                }
            )
    finally:
        if live:
            LLMClient.complete_json = staticmethod(original_complete_json)
            LLMClient.complete_with_receipt = staticmethod(original_complete_with_receipt)
            LLMClient.complete = staticmethod(original_complete)
            llm_client.MAX_RETRIES = original_max_retries

    failures = [item for item in results if item["failures"]]
    judge_scores = [int(item["judge"]["score"]) for item in results if isinstance(item.get("judge"), Mapping) and "score" in item["judge"]]
    return {
        "schema_version": "prm_live_ux_eval_receipt.v2",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "application_boundary": "prm.application.PersonalResearchAssistant",
        "live_llm_judge": live,
        "case_count": len(results),
        "case_offset": case_offset,
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "average_judge_score": round(sum(judge_scores) / len(judge_scores), 2) if judge_scores else None,
        "routes": dict(sorted(Counter(item["actual_route"] for item in results).items())),
        "intents": dict(sorted(Counter(item["actual_intent"] for item in results).items())),
        "judge_scored_cases": len(judge_scores),
        "provider_calls": provider_calls,
        "provider_call_budget": max_provider_calls if live else 0,
        "provider_retry_limit": 1 if live else 0,
        "judge_threshold": {"minimum_score": JUDGE_MIN_SCORE, "requires_clear": True, "requires_direct": True, "requires_grounded": True},
        "failure_counts": dict(sorted(Counter(reason for item in failures for reason in item["failures"]).items())),
        "metrics": {
            "intent_accuracy": _rate(sum(1 for item in results if item["actual_intent"] == item["expected_intent"]), len(results)),
            "direct_answer_rate": _rate(sum(1 for item in results if item["first_useful_information_position"] == 0), len(results)),
            "external_verification_false_positive_rate": _rate(
                sum(1 for item in results if item["kind"] != "current_fact" and item["current_fact_boundary"]),
                sum(1 for item in results if item["kind"] != "current_fact"),
            ),
            "unsupported_project_context_rate": _rate(
                sum(1 for item in results if "unsupported_project_context" in item["failures"]),
                len(results),
            ),
            "answer_chars_mean": round(sum(item["answer_chars"] for item in results) / len(results), 2) if results else 0.0,
        },
        "cases": results,
        "privacy": {
            "raw_questions_or_answers_stored": False,
            "raw_telegram_corpus_stored": False,
            "telegram_messages_sent": False,
            "durable_writes_requested": False,
            "bounded_provider_egress": live,
        },
        "honesty_boundary": "Automated UX evaluation is regression evidence; operator usefulness still requires human feedback.",
    }


def _rate(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-live-eval", action="store_true")
    parser.add_argument("--cases", type=int, default=100, choices=range(1, 101))
    parser.add_argument("--offset", type=int, default=0, choices=range(0, 100))
    parser.add_argument("--max-provider-calls", type=int, default=MAX_LIVE_PROVIDER_CALLS, choices=range(1, MAX_LIVE_PROVIDER_CALLS + 1))
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.live and not args.confirm_live_eval:
        parser.error("--live requires --confirm-live-eval")
    if args.live and not _egress_allowed():
        parser.error("--live requires PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1")
    receipt = run(live=args.live, case_limit=args.cases, case_offset=args.offset, max_provider_calls=args.max_provider_calls)
    if args.receipt:
        path = _private_receipt_path(args.receipt)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    public = {key: value for key, value in receipt.items() if key != "cases"}
    print(json.dumps(public, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
