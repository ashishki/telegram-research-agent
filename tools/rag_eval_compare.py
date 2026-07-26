#!/usr/bin/env python3
"""Compare Playbook RAG Evaluation v2 baseline and candidate results."""

from __future__ import annotations

import argparse
from pathlib import Path

from rag_eval_lib import artifact_ref, compare_results, render_comparison_report, validate_schema, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json", required=True, dest="json_output")
    parser.add_argument("--report", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    manifest_path = Path(args.manifest) if Path(args.manifest).is_absolute() else root / args.manifest
    baseline_path = Path(args.baseline) if Path(args.baseline).is_absolute() else root / args.baseline
    candidate_path = Path(args.candidate) if Path(args.candidate).is_absolute() else root / args.candidate
    comparison = compare_results(root, manifest_path, baseline_path, candidate_path)
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = root / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_comparison_report(comparison), encoding="utf-8")
    comparison["markdown_report_ref"] = artifact_ref(report_path, root, kind="markdown_report")
    findings = validate_schema(root, "rag_eval_comparison.schema.json", comparison, Path("<generated-comparison>"))
    if findings:
        comparison["status"] = "invalid"
        comparison["compatibility_errors"].extend(finding.message for finding in findings)
    output = Path(args.json_output)
    if not output.is_absolute():
        output = root / output
    write_json(output, comparison)
    for finding in findings:
        print(f"{finding.severity}: {finding.check_id}: {finding.message}")
    print(f"rag_eval_compare: status={comparison['status']} result={output} report={report_path}")
    return 0 if comparison["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
