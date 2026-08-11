#!/usr/bin/env python3
"""Build scoreable PRM-24 product RAG gold cases from candidates and labels."""

from __future__ import annotations

import argparse
import json
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


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--cases", default="evals/retrieval/product_rag_candidate.jsonl")
    parser.add_argument("--labels", default="evals/retrieval/product_rag_gold_labels.jsonl")
    parser.add_argument("--jsonl", required=True, dest="jsonl_output")
    parser.add_argument("--min-rows", type=int, default=50)
    parser.add_argument("--allow-partial", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    _load_src(root)

    from db.product_rag_eval import merge_product_rag_gold_cases

    gold_cases = merge_product_rag_gold_cases(
        _load_jsonl(_resolve(root, args.cases)),
        _load_jsonl(_resolve(root, args.labels)),
        min_rows=args.min_rows,
        require_all_labels=not args.allow_partial,
    )

    output_path = _resolve(root, args.jsonl_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in gold_cases),
        encoding="utf-8",
    )
    print(
        "product_rag_gold_cases: "
        f"rows={len(gold_cases)} "
        f"output={output_path.resolve().relative_to(root)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
