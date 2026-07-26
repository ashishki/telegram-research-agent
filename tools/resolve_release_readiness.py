#!/usr/bin/env python3
"""Resolve release readiness from already-produced verification evidence.

This command is intentionally post-verification. `tools/verify_project.py`
creates `.playbook-artifacts/project_verification.json`; this resolver checks
that result against the current exact HEAD, artifact hashes, and release
readiness invariants.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

import playbook_validate  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(root: Path) -> dict[str, object]:
    findings = []
    findings.extend(playbook_validate.active_scaffold_placeholder_findings(root))
    findings.extend(playbook_validate.validate_delivery(root))
    findings.extend(playbook_validate.validate_release_verification(root))
    errors = [finding for finding in findings if finding.severity == "error"]
    return {
        "schema_version": "playbook.release_readiness_result.v1",
        "root": str(root),
        "checked_at": utc_now(),
        "status": "release_ready" if not errors else "blocked",
        "findings": [finding.as_dict() for finding in findings],
        "summary": {
            "errors": len(errors),
            "warnings": sum(1 for finding in findings if finding.severity == "warning"),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Generated project root.")
    parser.add_argument(
        "--json",
        default=".playbook-artifacts/release_readiness.json",
        help="Path for machine-readable release readiness result, relative to root unless absolute.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    report = resolve(root)
    output_path = Path(args.json)
    if not output_path.is_absolute():
        output_path = root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for finding in report["findings"]:
        print(
            "{severity}: {path}:{line}: {check_id}: {message}".format(**finding),
            file=sys.stderr if finding["severity"] == "error" else sys.stdout,
        )
    print(f"resolve_release_readiness: status={report['status']} result={output_path}")
    return 0 if report["status"] == "release_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
