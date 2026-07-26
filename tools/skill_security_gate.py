#!/usr/bin/env python3
"""External agent skill security gate.

This tool is intentionally small and dependency-free. It does not replace
SkillSpector; it wraps SkillSpector (or a compatible CLI) with playbook policy:

- discover or accept explicit skill paths
- require a completed trust record for each skill
- run a JSON scan when a scanner is required/available
- fail on high-risk scan results unless explicitly accepted in the trust record

The default command is safe for repositories with no external skills:

    python3 tools/skill_security_gate.py --root . --discover-agent-skills

If no skills are found, the command exits 0 without requiring SkillSpector.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_SKILL_DIRS = (".codex/skills", ".claude/skills", "skills")
BLOCKING_SEVERITIES = {"critical", "high"}
REQUIRED_TRUST_HEADINGS = (
    "## Skill Identity",
    "## Capability Declaration",
    "## Scan Evidence",
    "## Findings Triage",
    "## Signature / Integrity",
    "## Approval Decision",
)


@dataclass(frozen=True)
class SkillTarget:
    path: Path
    slug: str


@dataclass
class ScanSummary:
    risk_score: float | None
    risk_severity: str | None
    risk_recommendation: str | None
    findings: list[dict[str, Any]]
    json_report: Path | None = None
    sarif_report: Path | None = None


@dataclass
class GateResult:
    skill: SkillTarget
    trust_record: Path | None
    scan: ScanSummary | None
    issues: list[str]
    warnings: list[str]


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-").lower()
    return slug or "skill"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def is_skill_path(path: Path) -> bool:
    if path.is_file():
        return path.name.lower() == "skill.md" or path.suffix.lower() in {".md", ".zip"}
    return (path / "SKILL.md").exists()


def infer_slug(path: Path) -> str:
    if path.is_file() and path.name.lower() == "skill.md":
        return slugify(path.parent.name)
    if path.is_file():
        return slugify(path.stem)
    return slugify(path.name)


def parse_skill_arg(raw: str, root: Path) -> SkillTarget:
    if "=" in raw:
        slug_raw, path_raw = raw.split("=", 1)
        slug = slugify(slug_raw)
    else:
        path_raw = raw
        slug = ""
    path = Path(path_raw)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not slug:
        slug = infer_slug(path)
    return SkillTarget(path=path, slug=slug)


def discover_skills(root: Path) -> list[SkillTarget]:
    targets: list[SkillTarget] = []
    seen: set[Path] = set()
    for relative_dir in DEFAULT_SKILL_DIRS:
        base = root / relative_dir
        if not base.exists():
            continue
        if (base / "SKILL.md").exists():
            resolved = base.resolve()
            targets.append(SkillTarget(path=resolved, slug=infer_slug(resolved)))
            seen.add(resolved)
            continue
        for child in sorted(base.iterdir()):
            if not is_skill_path(child):
                continue
            resolved = child.resolve()
            if resolved in seen:
                continue
            targets.append(SkillTarget(path=resolved, slug=infer_slug(resolved)))
            seen.add(resolved)
    return targets


def trust_path_for(skill: SkillTarget, trust_root: Path) -> Path:
    return trust_root / skill.slug / "TRUST_RECORD.md"


def table_value(markdown: str, field_name: str) -> str | None:
    pattern = re.compile(
        r"^\|\s*" + re.escape(field_name) + r"\s*\|\s*(.*?)\s*\|",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(markdown)
    if not match:
        return None
    return match.group(1).strip()


def bullet_value(markdown: str, field_name: str) -> str | None:
    pattern = re.compile(
        r"^-\s*" + re.escape(field_name) + r"\s*:\s*(.*?)\s*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(markdown)
    if not match:
        return None
    return match.group(1).strip()


def value_is_unset(value: str | None) -> bool:
    if value is None:
        return True
    normalized = value.strip().lower()
    if not normalized:
        return True
    return normalized in {
        "tbd",
        "todo",
        "unknown",
        "n/a",
        "not set",
        "yes/no",
        "pass/fail/not run",
        "project-local / global",
        "approved / rejected / deferred",
        "draft | approved | rejected | retired",
    }


def trust_accepts_high_risk(markdown: str) -> bool:
    value = bullet_value(markdown, "Critical/high risk acceptance")
    return value is not None and value.strip().lower() in {"yes", "approved", "accepted"}


def validate_trust_record(path: Path, allow_draft: bool) -> tuple[list[str], list[str], str]:
    issues: list[str] = []
    warnings: list[str] = []
    if not path.exists():
        return [f"missing trust record: {path}"], warnings, ""

    markdown = read_text(path)
    if "{{" in markdown or "}}" in markdown:
        issues.append("trust record still contains template placeholders")

    for heading in REQUIRED_TRUST_HEADINGS:
        if heading not in markdown:
            issues.append(f"trust record missing section: {heading}")

    status_match = re.search(r"^Status:\s*(.*?)\s*$", markdown, flags=re.IGNORECASE | re.MULTILINE)
    status = status_match.group(1).strip().lower() if status_match else ""
    if not status:
        issues.append("trust record missing Status line")
    elif not allow_draft and status != "approved":
        issues.append(f"trust record status must be approved, found: {status}")

    required_identity_fields = (
        "Skill name",
        "Source URL",
        "Publisher / maintainer",
        "Version / tag / commit SHA",
        "Install scope",
        "Update policy",
    )
    for field_name in required_identity_fields:
        if value_is_unset(table_value(markdown, field_name)):
            issues.append(f"trust record missing value: {field_name}")

    signature_verified = table_value(markdown, "Signature verified")
    hash_pinned = table_value(markdown, "Commit/hash pinned")
    signature_ok = signature_verified is not None and signature_verified.strip().lower() == "pass"
    hash_ok = hash_pinned is not None and hash_pinned.strip().lower() == "yes"
    if not signature_ok and not hash_ok:
        issues.append("trust record must show signature verification pass or commit/hash pinned yes")

    decision = bullet_value(markdown, "Decision")
    if not allow_draft and (decision is None or decision.strip().lower() != "approved"):
        issues.append("approval decision must be approved")

    if trust_accepts_high_risk(markdown):
        warnings.append("trust record accepts critical/high risk; verify human approval evidence")

    return issues, warnings, markdown


def recursive_find_first_number(obj: Any, keys: set[str]) -> float | None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in keys:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    pass
        for value in obj.values():
            found = recursive_find_first_number(value, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = recursive_find_first_number(value, keys)
            if found is not None:
                return found
    return None


def recursive_find_first_string(obj: Any, keys: set[str]) -> str | None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() in keys and isinstance(value, str):
                return value
        for value in obj.values():
            found = recursive_find_first_string(value, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = recursive_find_first_string(value, keys)
            if found is not None:
                return found
    return None


def collect_findings(obj: Any) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            lowered = key.lower()
            if lowered in {"findings", "filtered_findings", "issues", "results"} and isinstance(value, list):
                findings.extend(item for item in value if isinstance(item, dict))
            else:
                findings.extend(collect_findings(value))
    elif isinstance(obj, list):
        for value in obj:
            findings.extend(collect_findings(value))
    return findings


def parse_scan_json(path: Path) -> ScanSummary:
    data = json.loads(path.read_text(encoding="utf-8"))
    return ScanSummary(
        risk_score=recursive_find_first_number(data, {"risk_score", "riskscore", "score"}),
        risk_severity=recursive_find_first_string(data, {"risk_severity", "severity"}),
        risk_recommendation=recursive_find_first_string(
            data,
            {"risk_recommendation", "recommendation"},
        ),
        findings=collect_findings(data),
        json_report=path,
    )


def finding_severity(finding: dict[str, Any]) -> str:
    for key in ("severity", "level", "risk_severity"):
        value = finding.get(key)
        if isinstance(value, str):
            return value.strip().lower()
    return ""


def finding_label(finding: dict[str, Any]) -> str:
    for key in ("rule_id", "id", "name", "category", "message", "finding"):
        value = finding.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unnamed finding"


def run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def run_scan(
    skill: SkillTarget,
    reports_dir: Path,
    scanner: str,
    no_llm: bool,
    sarif: bool,
) -> tuple[ScanSummary | None, list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_report = reports_dir / f"{skill.slug}.skillspector.json"
    cmd = [scanner, "scan", str(skill.path), "--format", "json", "--output", str(json_report)]
    if no_llm:
        cmd.append("--no-llm")

    result = run_command(cmd)
    if result.returncode >= 2:
        issues.append(f"SkillSpector scan errored for {skill.slug}: {result.stderr.strip() or result.stdout.strip()}")
        return None, issues, warnings
    if result.returncode == 1:
        warnings.append("SkillSpector returned risk exit code 1; applying playbook policy to JSON report")

    if not json_report.exists():
        issues.append(f"SkillSpector did not write JSON report: {json_report}")
        return None, issues, warnings

    try:
        summary = parse_scan_json(json_report)
    except (json.JSONDecodeError, OSError) as exc:
        issues.append(f"could not parse SkillSpector JSON report {json_report}: {exc}")
        return None, issues, warnings

    if sarif:
        sarif_report = reports_dir / f"{skill.slug}.skillspector.sarif"
        sarif_cmd = [
            scanner,
            "scan",
            str(skill.path),
            "--format",
            "sarif",
            "--output",
            str(sarif_report),
        ]
        if no_llm:
            sarif_cmd.append("--no-llm")
        sarif_result = run_command(sarif_cmd)
        if sarif_result.returncode >= 2:
            issues.append(f"SkillSpector SARIF scan errored for {skill.slug}: {sarif_result.stderr.strip()}")
        elif sarif_report.exists():
            summary.sarif_report = sarif_report
        else:
            warnings.append(f"SkillSpector did not write SARIF report: {sarif_report}")

    return summary, issues, warnings


def evaluate_scan(
    summary: ScanSummary,
    trust_markdown: str,
    max_risk_score: float,
) -> tuple[list[str], list[str]]:
    issues: list[str] = []
    warnings: list[str] = []
    high_risk_accepted = trust_accepts_high_risk(trust_markdown)

    if summary.risk_score is not None and summary.risk_score > max_risk_score:
        message = f"risk score {summary.risk_score:g} exceeds threshold {max_risk_score:g}"
        if high_risk_accepted:
            warnings.append(message + " but trust record accepts high risk")
        else:
            issues.append(message)

    if summary.risk_recommendation and summary.risk_recommendation.strip().upper() == "DO_NOT_INSTALL":
        message = "scanner recommendation is DO_NOT_INSTALL"
        if high_risk_accepted:
            warnings.append(message + " but trust record accepts high risk")
        else:
            issues.append(message)

    blocking = [
        finding
        for finding in summary.findings
        if finding_severity(finding) in BLOCKING_SEVERITIES
    ]
    if blocking and not high_risk_accepted:
        labels = ", ".join(finding_label(finding) for finding in blocking[:5])
        suffix = "" if len(blocking) <= 5 else f", +{len(blocking) - 5} more"
        issues.append(f"blocking scanner findings: {labels}{suffix}")
    elif blocking:
        warnings.append(f"{len(blocking)} high/critical findings accepted by trust record")

    return issues, warnings


def evaluate_skill(args: argparse.Namespace, skill: SkillTarget, scanner_path: str | None) -> GateResult:
    issues: list[str] = []
    warnings: list[str] = []

    if not skill.path.exists():
        issues.append(f"skill path does not exist: {skill.path}")
        return GateResult(skill=skill, trust_record=None, scan=None, issues=issues, warnings=warnings)
    if not is_skill_path(skill.path):
        issues.append(f"path does not look like a skill directory/file: {skill.path}")

    trust_record = trust_path_for(skill, args.trust_root)
    trust_issues, trust_warnings, trust_markdown = validate_trust_record(
        trust_record,
        allow_draft=args.allow_draft_trust,
    )
    if args.require_trust_record:
        issues.extend(trust_issues)
    else:
        warnings.extend(trust_issues)
    warnings.extend(trust_warnings)

    scan: ScanSummary | None = None
    if scanner_path is None:
        scanner_message = "skillspector not found on PATH"
        if args.require_scanner:
            issues.append(scanner_message)
        else:
            warnings.append(scanner_message + "; scan skipped")
    else:
        scan, scan_issues, scan_warnings = run_scan(
            skill=skill,
            reports_dir=args.reports_dir,
            scanner=scanner_path,
            no_llm=args.no_llm,
            sarif=args.sarif,
        )
        issues.extend(scan_issues)
        warnings.extend(scan_warnings)
        if scan is not None:
            scan_issues, scan_warnings = evaluate_scan(
                scan,
                trust_markdown,
                max_risk_score=args.max_risk_score,
            )
            issues.extend(scan_issues)
            warnings.extend(scan_warnings)

    return GateResult(skill=skill, trust_record=trust_record, scan=scan, issues=issues, warnings=warnings)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run playbook external skill security gate.")
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument(
        "--skill",
        action="append",
        default=[],
        help="Skill path, or slug=path. Repeat for multiple skills.",
    )
    parser.add_argument(
        "--discover-agent-skills",
        action="store_true",
        help="Discover skills under .codex/skills, .claude/skills, and skills.",
    )
    parser.add_argument(
        "--trust-root",
        default="docs/security/skills",
        help="Trust record root, relative to --root unless absolute.",
    )
    parser.add_argument(
        "--reports-dir",
        default="reports/skill-security",
        help="Report output directory, relative to --root unless absolute.",
    )
    parser.add_argument("--scanner-command", default="skillspector", help="SkillSpector-compatible CLI name/path.")
    parser.add_argument("--require-trust-record", action="store_true", default=True)
    parser.add_argument("--allow-missing-trust-record", dest="require_trust_record", action="store_false")
    parser.add_argument("--require-scanner", action="store_true", help="Fail if a skill exists but scanner is unavailable.")
    parser.add_argument("--allow-draft-trust", action="store_true", help="Permit draft trust records during local triage.")
    parser.add_argument("--no-llm", action="store_true", default=True, help="Run static-only scanner mode.")
    parser.add_argument("--use-llm", dest="no_llm", action="store_false", help="Allow scanner semantic LLM analysis.")
    parser.add_argument("--sarif", action="store_true", help="Also write SARIF scan output.")
    parser.add_argument("--max-risk-score", type=float, default=50.0)
    return parser


def resolve_path(root: Path, raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.root = Path(args.root).resolve()
    args.trust_root = resolve_path(args.root, args.trust_root)
    args.reports_dir = resolve_path(args.root, args.reports_dir)

    targets = [parse_skill_arg(raw, args.root) for raw in args.skill]
    if args.discover_agent_skills:
        discovered = discover_skills(args.root)
        seen = {target.path for target in targets}
        for target in discovered:
            if target.path not in seen:
                targets.append(target)
                seen.add(target.path)

    if not targets:
        print("skill_security_gate: ok (0 skills)")
        return 0

    scanner_path = shutil.which(args.scanner_command)
    results = [evaluate_skill(args, skill, scanner_path) for skill in targets]

    failed = False
    for result in results:
        print(f"skill_security_gate: {result.skill.slug}: {result.skill.path}")
        if result.trust_record is not None:
            print(f"  trust: {result.trust_record}")
        if result.scan is not None:
            print(f"  scan_json: {result.scan.json_report}")
            if result.scan.sarif_report is not None:
                print(f"  scan_sarif: {result.scan.sarif_report}")
            if result.scan.risk_score is not None:
                print(f"  risk_score: {result.scan.risk_score:g}")
            if result.scan.risk_severity:
                print(f"  risk_severity: {result.scan.risk_severity}")
            if result.scan.risk_recommendation:
                print(f"  recommendation: {result.scan.risk_recommendation}")
        for warning in result.warnings:
            print(f"  WARN: {warning}")
        for issue in result.issues:
            print(f"  FAIL: {issue}")
        if result.issues:
            failed = True

    if failed:
        print("skill_security_gate: failed", file=sys.stderr)
        return 1
    print(f"skill_security_gate: ok ({len(results)} skills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
