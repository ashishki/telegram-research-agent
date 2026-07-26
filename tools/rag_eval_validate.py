#!/usr/bin/env python3
"""Validate Playbook RAG Evaluation v2 contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag_eval_lib import validate_contract


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--cases")
    parser.add_argument("--observations")
    parser.add_argument("--result")
    parser.add_argument("--json", dest="json_report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    findings = validate_contract(
        root,
        Path(args.manifest) if Path(args.manifest).is_absolute() else root / args.manifest,
        Path(args.cases) if args.cases and Path(args.cases).is_absolute() else (root / args.cases if args.cases else None),
        Path(args.observations) if args.observations and Path(args.observations).is_absolute() else (root / args.observations if args.observations else None),
        Path(args.result) if args.result and Path(args.result).is_absolute() else (root / args.result if args.result else None),
    )
    payload = {
        "schema_version": "playbook.rag_eval_validation.v1",
        "errors": sum(1 for finding in findings if finding.severity == "error"),
        "warnings": sum(1 for finding in findings if finding.severity == "warning"),
        "findings": [finding.as_dict() for finding in findings],
    }
    if args.json_report:
        report_path = Path(args.json_report)
        if not report_path.is_absolute():
            report_path = root / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for finding in findings:
        print(f"{finding.severity}: {finding.check_id}: {finding.message}")
    print(f"rag_eval_validate: errors={payload['errors']} warnings={payload['warnings']}")
    return 1 if payload["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
