#!/usr/bin/env python3
"""Validate product RAG eval metadata without running retrieval or embeddings."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_src(root: Path) -> None:
    src = str((root / "src").resolve())
    if src not in sys.path:
        sys.path.insert(0, src)


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON value must be an object")
    return value


def _load_jsonl(path: Path, *, missing_ok: bool = False) -> list[dict[str, object]]:
    if missing_ok and not path.exists():
        return []
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
    parser.add_argument("--thresholds", default="evals/retrieval/product_rag_thresholds.json")
    parser.add_argument("--json", required=True, dest="json_output")
    parser.add_argument("--min-rows", type=int, default=50)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    _load_src(root)

    from db.product_rag_eval import build_product_rag_eval_manifest

    cases = _load_jsonl(_resolve(root, args.cases))
    labels = _load_jsonl(_resolve(root, args.labels), missing_ok=True)
    thresholds = _load_json(_resolve(root, args.thresholds))
    manifest = build_product_rag_eval_manifest(
        cases,
        labels=labels,
        thresholds=thresholds,
        min_rows=args.min_rows,
    )

    output_path = _resolve(root, args.json_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    dataset = manifest["dataset"]
    gold = manifest["gold_labels"]
    assert isinstance(dataset, dict)
    assert isinstance(gold, dict)
    print(
        "product_rag_eval_manifest: "
        f"cases={dataset['case_count']} "
        f"gold_labels={gold['count']} "
        f"output={output_path.resolve().relative_to(root)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
