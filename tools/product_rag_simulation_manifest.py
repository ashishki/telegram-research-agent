#!/usr/bin/env python3
"""Build a privacy-safe, non-gating receipt for PRM-24 label drafts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--drafts", default="evals/retrieval/product_rag_gold_label_drafts.jsonl")
    parser.add_argument("--json", required=True, dest="json_output")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from db.product_rag_eval import build_product_rag_simulation_receipt

    drafts_path = root / args.drafts
    drafts = [json.loads(line) for line in drafts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    receipt = build_product_rag_simulation_receipt(drafts)
    output = root / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"product_rag_simulation_manifest: drafts={receipt['drafts']['count']} output={output.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
