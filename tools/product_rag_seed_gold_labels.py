#!/usr/bin/env python3
"""Generate operator-approved PRM-24 seed gold labels from local read-only FTS."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Mapping


DEFAULT_APPROVAL_REF = "operator-approval-2026-08-11-all-50-generated-gold"


def _load_src(root: Path) -> None:
    src = str((root / "src").resolve())
    if src not in sys.path:
        sys.path.insert(0, src)


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_no}: JSONL row must be an object")
        rows.append(value)
    return rows


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--db", default="data/agent.db")
    parser.add_argument("--cases", default="evals/retrieval/product_rag_candidate.jsonl")
    parser.add_argument("--jsonl", required=True, dest="jsonl_output")
    parser.add_argument("--approval-ref", default=DEFAULT_APPROVAL_REF)
    parser.add_argument("--max-variants", type=int, default=4)
    parser.add_argument("--max-expected", type=int, default=10)
    return parser


def _sqlite_uri(root: Path, value: str) -> str:
    if value.startswith("file:"):
        return value
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return f"file:{path.resolve()}?mode=ro"


def _base_label(case: Mapping[str, object], *, approval_ref: str) -> dict[str, object]:
    return {
        "case_id": str(case["case_id"]),
        "human_approved": True,
        "human_approval_ref": approval_ref,
        "approval_scope": "operator instructed Codex to create all 50 generated PRM-24 gold labels",
        "label_source": "local_sqlite_fts_query_planner",
        "label_method": "operator_authorized_codex_generated_from_read_only_local_archive_search",
        "label_quality": "operator_approved_generated_seed_not_independent_human_review",
        "raw_telegram_text_included": False,
    }


def _is_freshness_case(case: Mapping[str, object]) -> bool:
    return str(case.get("category") or "") == "linked_source_freshness"


def _is_no_answer_case(case: Mapping[str, object]) -> bool:
    return str(case.get("category") or "") == "no_answer"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _label_for_case(
    connection: sqlite3.Connection,
    case: Mapping[str, object],
    *,
    approval_ref: str,
    max_variants: int,
    max_expected: int,
) -> dict[str, object]:
    from assistant.memory_research import _archive_query_variants
    from db.archive_search import search_telegram_archive

    label = _base_label(case, approval_ref=approval_ref)
    case_id = str(case["case_id"])
    query = str(case["query"])
    if _is_no_answer_case(case):
        label["expected_no_answer"] = True
        label["no_answer_basis"] = "operator-approved generated seed label; local archive may contain related discussion but not proof of the asserted current/project state"
        if case_id == "PRAG-NOANS-004":
            label["external_verification_required"] = True
        return label

    variants = _archive_query_variants(query, project_name=None, max_variants=max_variants)
    seen: set[str] = set()
    expected_archive_document_ids: list[str] = []
    expected_post_ids: list[str] = []
    for variant in variants:
        for result in search_telegram_archive(connection, variant, limit=max_expected):
            if result.archive_document_id in seen:
                continue
            seen.add(result.archive_document_id)
            expected_archive_document_ids.append(result.archive_document_id)
            expected_post_ids.append(str(result.post_id))
            if len(expected_archive_document_ids) >= max_expected:
                break
        if len(expected_archive_document_ids) >= max_expected:
            break

    if not expected_archive_document_ids:
        raise RuntimeError(f"{case_id}: local FTS query planner returned no scoreable expected documents")

    label["expected_archive_document_ids"] = expected_archive_document_ids
    label["expected_post_ids"] = expected_post_ids
    label["retrieval_query_variants"] = variants
    if _is_freshness_case(case):
        label["external_verification_required"] = True
        label["freshness_expectation"] = "requires_external_verification_before_current_claim_or_action"
    return label


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    _load_src(root)

    cases = _load_jsonl(_resolve(root, args.cases))
    output_path = _resolve(root, args.jsonl_output)
    max_variants = max(1, min(8, int(args.max_variants or 4)))
    max_expected = max(1, min(20, int(args.max_expected or 10)))

    connection = sqlite3.connect(_sqlite_uri(root, args.db), uri=True)
    connection.row_factory = sqlite3.Row
    try:
        labels = [
            _label_for_case(
                connection,
                case,
                approval_ref=str(args.approval_ref),
                max_variants=max_variants,
                max_expected=max_expected,
            )
            for case in cases
        ]
    finally:
        connection.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in labels),
        encoding="utf-8",
    )
    print(
        "product_rag_seed_gold_labels: "
        f"rows={len(labels)} "
        f"approval_ref={args.approval_ref} "
        f"output={output_path.resolve().relative_to(root)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
