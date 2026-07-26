#!/usr/bin/env python3
"""Score Playbook RAG Evaluation v2 observations with deterministic metrics."""

from __future__ import annotations

import argparse
from pathlib import Path

from rag_eval_lib import render_score_report, score_observations, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--cases")
    parser.add_argument("--observations", required=True)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--json", required=True, dest="json_output")
    parser.add_argument("--report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    manifest_path = Path(args.manifest) if Path(args.manifest).is_absolute() else root / args.manifest
    if args.cases:
        cases_path = Path(args.cases) if Path(args.cases).is_absolute() else root / args.cases
    else:
        import json

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cases_path = root / manifest["dataset"]["dataset_path"]
    observations_path = Path(args.observations) if Path(args.observations).is_absolute() else root / args.observations
    result, findings = score_observations(root, manifest_path, cases_path, observations_path, args.condition)
    output = Path(args.json_output)
    if not output.is_absolute():
        output = root / output
    write_json(output, result)
    if args.report:
        report = Path(args.report)
        if not report.is_absolute():
            report = root / report
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(render_score_report(result), encoding="utf-8")
    for finding in findings:
        print(f"{finding.severity}: {finding.check_id}: {finding.message}")
    print(f"rag_eval_score: status={result['status']} result={output}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
