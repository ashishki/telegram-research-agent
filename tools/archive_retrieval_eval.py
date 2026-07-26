#!/usr/bin/env python3
"""Run deterministic archive FTS retrieval evaluation without gold fabrication."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--db", default="data/agent.db")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", required=True, dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    _load_src(root)

    from db.archive_retrieval_eval import (
        evaluate_archive_retrieval,
        validate_archive_retrieval_eval_report,
    )

    cases_path = Path(args.cases)
    if not cases_path.is_absolute():
        cases_path = root / cases_path
    output_path = Path(args.json_output)
    if not output_path.is_absolute():
        output_path = root / output_path
    db_path = str(args.db)
    if not db_path.startswith("file:"):
        db_path = str((root / db_path).resolve())

    cases = _load_jsonl(cases_path)
    connection = sqlite3.connect(
        db_path if db_path.startswith("file:") else f"file:{db_path}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        report = validate_archive_retrieval_eval_report(
            evaluate_archive_retrieval(connection, cases, limit=args.limit)
        )
    finally:
        connection.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    dataset = report["dataset"]
    assert isinstance(dataset, dict)
    print(
        "archive_retrieval_eval: "
        f"rows={dataset['row_count']} "
        f"gold={dataset['gold_row_count']} "
        f"candidates={dataset['candidate_row_count']} "
        f"output={output_path.resolve().relative_to(root)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
