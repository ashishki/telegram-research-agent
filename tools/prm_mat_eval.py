#!/usr/bin/env python3
"""Validate synthetic PRM-MAT holdout manifests; no model or corpus access."""
from __future__ import annotations
import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", choices=("routing", "safety", "all"), required=True)
    check = parser.parse_args().check
    failures = []
    if check in {"routing", "all"}:
        rows = json.loads((ROOT / "evals/prm_mat/routing_holdouts.v1.json").read_text())
        if len(rows) < 50 or any(not row.get("category") or not row.get("expected_route") for row in rows): failures.append("routing")
    if check in {"safety", "all"}:
        rows = json.loads((ROOT / "evals/prm_mat/safety_holdouts.v1.json").read_text())
        required = {"replay", "ssrf"}
        if not required.issubset({row.get("category") for row in rows}): failures.append("safety")
    print("prm_mat_eval: " + ("ok" if not failures else "failed=" + ",".join(failures)))
    return 0 if not failures else 1
if __name__ == "__main__": raise SystemExit(main())
