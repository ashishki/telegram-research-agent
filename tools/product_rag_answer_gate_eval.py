#!/usr/bin/env python3
"""Run deterministic PRM-28 no-vector product RAG answer-gate evaluation."""

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
    parser.add_argument("--cases", default="evals/retrieval/product_rag_gold_cases.jsonl")
    parser.add_argument("--json", required=True, dest="json_output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    _load_src(root)

    from db.product_rag_answer_gate_eval import evaluate_product_rag_answer_gate

    report = evaluate_product_rag_answer_gate(_load_jsonl(_resolve(root, args.cases)))
    output_path = _resolve(root, args.json_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    dataset = report["dataset"]
    metrics = report["metrics"]
    assert isinstance(dataset, dict)
    assert isinstance(metrics, dict)
    print(
        "product_rag_answer_gate_eval: "
        f"rows={dataset['row_count']} "
        f"no_answer_accuracy={metrics['no_answer_accuracy']} "
        f"external_verification_boundary_accuracy={metrics['external_verification_boundary_accuracy']} "
        f"output={output_path.resolve().relative_to(root)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
