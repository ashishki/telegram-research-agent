#!/usr/bin/env python3
"""Read-only integrity checks for playbook references."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


PATH_RE = re.compile(r"`([^`]+)`")
SKIP_VALUES = {
    "",
    ".",
    "n/a",
    "none",
    "unknown",
    "{{DATE}}",
    "{{PROJECT_NAME}}",
}


@dataclass
class Finding:
    severity: str
    path: Path
    line: int
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument(
        "--strict-generated",
        action="store_true",
        help="Fail when generated context packet references are missing.",
    )
    return parser.parse_args()


def looks_like_path(value: str) -> bool:
    if value in SKIP_VALUES:
        return False
    if value.startswith(("http://", "https://", "#")):
        return False
    if " " in value and "/" not in value:
        return False
    if value.startswith("{{") and value.endswith("}}"):
        return False
    return (
        "/" in value
        or value.endswith((".md", ".py", ".json", ".yml", ".yaml", ".toml", ".txt"))
        or value in {"README.md", "PLAYBOOK.md"}
    )


def normalize_reference(value: str) -> str:
    value = value.strip()
    value = value.split("::", 1)[0]
    value = value.split("#", 1)[0]
    return value.rstrip("/")


def reference_exists(root: Path, value: str) -> bool:
    ref = normalize_reference(value)
    if not ref or not looks_like_path(ref):
        return True
    return (root / ref).exists()


def check_backtick_paths(
    root: Path,
    doc: Path,
    *,
    generated_warning: bool = False,
) -> list[Finding]:
    findings: list[Finding] = []
    if not doc.exists():
        return findings

    severity = "WARN" if generated_warning else "ERROR"
    for line_no, line in enumerate(doc.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        for match in PATH_RE.finditer(line):
            raw = match.group(1).strip()
            if not looks_like_path(raw):
                continue
            if not reference_exists(root, raw):
                missing_severity = severity
                normalized = normalize_reference(raw)
                if normalized == "docs/context-packets" or normalized.startswith(("generated/", "docs/context-packets/")):
                    missing_severity = "WARN"
                findings.append(
                    Finding(
                        severity=missing_severity,
                        path=doc,
                        line=line_no,
                        message=f"Missing referenced path `{raw}`",
                    )
                )
    return findings


def check_context_packet_paths(root: Path, strict_generated: bool) -> list[Finding]:
    packet_dir = root / "docs" / "context-packets"
    if not packet_dir.exists():
        return []
    findings: list[Finding] = []
    for packet in sorted(packet_dir.rglob("*.md")):
        findings.extend(
            check_backtick_paths(
                root,
                packet,
                generated_warning=not strict_generated,
            )
        )
    return findings


def check_task_context_refs(root: Path) -> list[Finding]:
    tasks = root / "docs" / "tasks.md"
    if not tasks.exists():
        return []
    findings: list[Finding] = []
    in_context_refs = False
    for line_no, line in enumerate(tasks.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("Context-Refs:"):
            in_context_refs = True
        elif in_context_refs and re.match(r"^[A-Za-z][A-Za-z0-9_-]+:", stripped):
            in_context_refs = False
        if not in_context_refs:
            continue
        for match in PATH_RE.finditer(line):
            raw = match.group(1).strip()
            if looks_like_path(raw) and not reference_exists(root, raw):
                findings.append(
                    Finding("ERROR", tasks, line_no, f"Missing Context-Refs path `{raw}`")
                )
    return findings


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    docs_to_check = [
        root / "docs" / "COGNITION_MANIFEST.md",
        root / "docs" / "EVIDENCE_INDEX.md",
    ]

    findings: list[Finding] = []
    for doc in docs_to_check:
        findings.extend(check_backtick_paths(root, doc))
    findings.extend(check_task_context_refs(root))
    findings.extend(check_context_packet_paths(root, args.strict_generated))

    for finding in findings:
        rel = finding.path.relative_to(root)
        print(f"{finding.severity}: {rel}:{finding.line}: {finding.message}")

    errors = [finding for finding in findings if finding.severity == "ERROR"]
    if errors:
        print(f"integrity_check: failed with {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("integrity_check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
