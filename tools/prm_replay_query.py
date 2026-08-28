#!/usr/bin/env python3
"""Replay one PRM archive query without provider egress or durable writes.

Fixture mode is suitable for public regression tests. Local DB mode exercises
the active application boundary but stores the detailed receipt only under the
private gitignored eval directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from assistant.archive_relevance import rank_archive_items  # noqa: E402
from config.settings import Settings, load_settings  # noqa: E402
from prm.application import PersonalResearchAssistant  # noqa: E402
from prm.archive_contract import build_archive_response_contract  # noqa: E402
from prm.contracts import OperatorRequest  # noqa: E402
from prm.presentation import render_payload  # noqa: E402
from prm.routing import decide_route  # noqa: E402

DEFAULT_PRIVATE_ROOT = PROJECT_ROOT / "data" / "evals" / "private" / "prm_replay"
DEFAULT_QUERY = "Что в архиве есть про agent evals и что из этого применимо?"


def _fixture_replay_parts(
    query: str, fixture: Mapping[str, Any]
) -> tuple[Any, list[dict[str, Any]], dict[str, Any], str]:
    route = decide_route(query)
    candidates = [item for item in fixture.get("items") or [] if isinstance(item, Mapping)]
    ranked = rank_archive_items(query, candidates)
    contract = build_archive_response_contract(
        question=query,
        archive_items=ranked,
        primary_intent=route.primary_intent,
        response_contract_id=route.response_contract_id,
        explicit_project=route.project_name,
        external_verification_required=route.external_verification_required,
    )
    rendered = render_payload(
        {
            "response_contract_id": contract["response_contract_id"],
            "archive_contract": contract,
        },
        mode="research",
    )
    return route, ranked, contract, rendered


def replay_fixture(query: str, fixture: Mapping[str, Any]) -> dict[str, Any]:
    route, ranked, contract, rendered = _fixture_replay_parts(query, fixture)
    summary = dict(contract["result_summary"])
    return {
        "schema_version": "prm_private_replay.v1",
        "query": query,
        "query_hash": _hash(query),
        "route": route.to_dict(),
        "candidate_trace": [
            {
                "candidate_id": str(item.get("archive_document_id") or item.get("post_id") or ""),
                "matched_query_variant": str(item.get("matched_query_variant") or ""),
                "retrieval_mode": str(item.get("retrieval_mode") or "fixture"),
                "lexical_rank": item.get("rank"),
                "semantic_score": item.get("semantic_score"),
                "fusion_score": item.get("fusion_score"),
                "relevance_label": item.get("relevance_label"),
                "directness_score": item.get("directness_score"),
                "relevance_reason": item.get("relevance_reason"),
                "selected": item.get("relevance_label") != "unrelated",
            }
            for item in ranked
        ],
        "selected_evidence_ids": [
            str(item.get("evidence_id") or "")
            for field in ("direct_findings", "partial_findings", "adjacent_findings")
            for item in contract.get(field) or []
            if isinstance(item, Mapping)
        ],
        "answer_gate": {
            "external_verification_required": route.external_verification_required,
            "reason": "route_boundary",
        },
        "response_contract_id": contract["response_contract_id"],
        "render_mode": "archive_contract_v2",
        "rendered_answer": rendered,
        "answer_chars": len(rendered),
        "first_useful_information_position": 0 if rendered else None,
        "result_summary": summary,
        "privacy": {
            "provider_egress": False,
            "telegram_messages_sent": False,
            "durable_writes": False,
            "public_report_allowed": False,
        },
    }


def replay_query(
    query: str,
    *,
    fixture: Sequence[Mapping[str, Any]] | Mapping[str, Any],
) -> dict[str, Any]:
    """Backward-compatible public fixture replay for the focused regression suite."""

    payload: Mapping[str, Any]
    if isinstance(fixture, Mapping):
        payload = fixture
    else:
        payload = {"items": list(fixture)}
    route, ranked, contract, rendered = _fixture_replay_parts(query, payload)
    trace = replay_fixture(query, payload)
    return {
        **trace,
        "route": route.to_dict(),
        "candidates": [dict(item) for item in ranked],
        "archive_contract": contract,
        "render": {
            "decision_template_rendered": False,
            "answer_chars": len(rendered),
        },
    }


def replay_application(query: str, *, db_path: str) -> dict[str, Any]:
    os.environ["PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS"] = "0"
    os.environ["PRM_TELEGRAM_RAG_LLM_SYNTHESIS"] = "0"
    base = load_settings()
    settings = Settings(
        db_path=str(Path(db_path).resolve()),
        llm_api_key=base.llm_api_key,
        model_provider=base.model_provider,
        telegram_session_path=base.telegram_session_path,
    )
    result = PersonalResearchAssistant(settings=settings).answer(
        OperatorRequest(query=query, mode="auto", chat_id=f"private-replay-{_hash(query)}")
    )
    runtime = result.to_dict()
    payload = runtime.get("payload") if isinstance(runtime.get("payload"), Mapping) else {}
    contract = payload.get("archive_contract") if isinstance(payload.get("archive_contract"), Mapping) else {}
    return {
        "schema_version": "prm_private_replay.v1",
        "query": query,
        "query_hash": _hash(query),
        "route": runtime.get("route") or {},
        "candidate_trace": _candidate_trace(payload),
        "selected_evidence_ids": _selected_ids(contract),
        "answer_gate": payload.get("answer_gate") or {},
        "response_contract_id": payload.get("response_contract_id"),
        "render_mode": "application_boundary",
        "rendered_answer": runtime.get("final_answer") or runtime.get("text") or "",
        "answer_chars": len(str(runtime.get("final_answer") or runtime.get("text") or "")),
        "first_useful_information_position": 0 if str(runtime.get("final_answer") or runtime.get("text") or "").strip() else None,
        "result_summary": contract.get("result_summary") or {},
        "final_answer_verification": runtime.get("final_answer_verification") or {},
        "privacy": {
            "provider_egress": False,
            "telegram_messages_sent": False,
            "durable_writes": False,
            "public_report_allowed": False,
        },
    }


def public_summary(trace: Mapping[str, Any]) -> dict[str, Any]:
    route = trace.get("route") if isinstance(trace.get("route"), Mapping) else {}
    summary = trace.get("result_summary") if isinstance(trace.get("result_summary"), Mapping) else {}
    return {
        "schema_version": "prm_replay_public_summary.v1",
        "query_hash": trace.get("query_hash"),
        "primary_intent": route.get("primary_intent"),
        "response_contract_id": trace.get("response_contract_id"),
        "direct_count": int(summary.get("direct_count") or 0),
        "partial_count": int(summary.get("partial_count") or 0),
        "adjacent_count": int(summary.get("adjacent_count") or 0),
        "answer_chars": int(trace.get("answer_chars") or 0),
        "privacy": {
            "contains_query": False,
            "contains_raw_query": False,
            "contains_raw_answer": False,
            "contains_source_urls": False,
            "contains_private_candidate_ids": False,
        },
    }


def _candidate_trace(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    archive = payload.get("archive_evidence") if isinstance(payload.get("archive_evidence"), Mapping) else {}
    result = []
    for item in archive.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        result.append(
            {
                "candidate_id": str(item.get("archive_document_id") or item.get("post_id") or ""),
                "matched_query_variant": item.get("matched_query_variant"),
                "retrieval_mode": item.get("retrieval_mode"),
                "lexical_rank": item.get("rank"),
                "semantic_score": item.get("semantic_score"),
                "fusion_score": item.get("fusion_score"),
                "relevance_label": item.get("relevance_label"),
                "directness_score": item.get("directness_score"),
                "relevance_reason": item.get("relevance_reason"),
                "selected": item.get("relevance_label") != "unrelated",
            }
        )
    return result


def _selected_ids(contract: Mapping[str, Any]) -> list[str]:
    return [
        str(item.get("evidence_id") or "")
        for field in ("direct_findings", "partial_findings", "adjacent_findings")
        for item in contract.get(field) or []
        if isinstance(item, Mapping)
    ]


def _load_fixture(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("fixture root must be an object")
    return payload


def _private_path(path: Path) -> Path:
    resolved = path.resolve()
    root = DEFAULT_PRIVATE_ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"private trace must stay under {root}")
    return resolved


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", type=Path)
    source.add_argument("--db", type=Path)
    parser.add_argument("--private-trace", type=Path)
    parser.add_argument("--show-private", action="store_true", help="Print the full private trace; requires --private-trace.")
    args = parser.parse_args()

    if args.fixture:
        trace = replay_fixture(args.query, _load_fixture(args.fixture))
    else:
        trace = replay_application(args.query, db_path=str(args.db))
    if args.show_private and not args.private_trace:
        parser.error("--show-private requires --private-trace so detailed output stays inside the private boundary")
    if args.private_trace:
        destination = _private_path(args.private_trace)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output = trace if args.show_private else public_summary(trace)
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
