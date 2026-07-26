#!/usr/bin/env python3
"""Render task-scoped prompts for isolated codex exec subagents."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

TOOL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL_ROOT / "tools"))

try:
    import playbook_validate
except ImportError as exc:  # pragma: no cover
    raise SystemExit(f"failed to import playbook_validate: {exc}") from exc


ROLE_PROMPTS = {
    "meta_review": [
        "docs/audit/PROMPT_0_META.md",
        "prompts/audit/PROMPT_0_META.md",
    ],
    "arch_review": [
        "docs/audit/PROMPT_1_ARCH.md",
        "prompts/audit/PROMPT_1_ARCH.md",
    ],
    "code_review": [
        "docs/audit/PROMPT_2_CODE.md",
        "prompts/audit/PROMPT_2_CODE.md",
    ],
    "test_critic": [
        "docs/audit/PROMPT_TEST_CRITIC.md",
        "prompts/audit/PROMPT_TEST_CRITIC.md",
    ],
    "privacy_review": [
        "docs/audit/PROMPT_PRIVACY_REVIEW.md",
        "prompts/audit/PROMPT_PRIVACY_REVIEW.md",
    ],
    "fix_from_review": [
        "docs/prompts/PROMPT_FIX_FROM_REVIEW.md",
        "prompts/PROMPT_FIX_FROM_REVIEW.md",
    ],
    "doc_sync": [
        "docs/prompts/PROMPT_DOC_SYNC_AFTER_TASK.md",
        "prompts/PROMPT_DOC_SYNC_AFTER_TASK.md",
    ],
    "consolidated_review": [
        "docs/audit/PROMPT_3_CONSOLIDATED.md",
        "prompts/audit/PROMPT_3_CONSOLIDATED.md",
    ],
}

READ_ONLY_ROLES = {
    "meta_review",
    "arch_review",
    "code_review",
    "test_critic",
    "privacy_review",
    "consolidated_review",
}


def read_text_if_exists(path: Path, limit: int | None = None) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if limit is not None and len(text) > limit:
        return text[:limit] + "\n\n[truncated by render_codex_exec_prompt.py]\n"
    return text


def find_prompt(root: Path, role: str) -> tuple[str, str]:
    for rel in ROLE_PROMPTS[role]:
        for base in (root, TOOL_ROOT):
            path = base / rel
            if path.exists():
                return str(path.relative_to(base)), path.read_text(encoding="utf-8")
    return "", ""


def task_section(tasks_path: Path, task_id: str) -> str:
    lines = tasks_path.read_text(encoding="utf-8", errors="replace").splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if line.startswith(f"### {task_id}:"):
            start = index
            break
    if start is None:
        raise SystemExit(f"task {task_id} not found in {tasks_path}")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("### "):
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def load_task(root: Path, task_id: str) -> tuple[dict[str, Any], str]:
    tasks_path = root / "docs" / "tasks.md"
    if not tasks_path.exists():
        raise SystemExit(f"missing task file: {tasks_path}")
    for block in playbook_validate.parse_task_blocks(tasks_path):
        if block.task_id == task_id:
            return block.to_record(), task_section(tasks_path, task_id)
    raise SystemExit(f"task {task_id} not found in {tasks_path}")


def default_output_path(task_id: str, role: str) -> str:
    suffix = {
        "meta_review": "meta_review",
        "arch_review": "arch_review",
        "code_review": "code_review",
        "test_critic": "test_critic",
        "privacy_review": "privacy_review",
        "fix_from_review": "fix_result",
        "doc_sync": "doc_sync_result",
        "consolidated_review": "consolidated_review",
    }[role]
    return f"docs/verification/{task_id}_{suffix}.md"


def review_report_block(root: Path, reports: list[str]) -> str:
    if not reports:
        return "No review reports supplied."
    parts = []
    for report in reports:
        path = root / report
        content = read_text_if_exists(path, limit=12000)
        if content:
            parts.append(f"### {report}\n\n{content.strip()}")
        else:
            parts.append(f"### {report}\n\n[missing or unreadable]")
    return "\n\n".join(parts)


def command_hint(args: argparse.Namespace, output_path: str) -> str:
    sandbox = "read-only" if args.role in READ_ONLY_ROLES else "workspace-write"
    reviews = " ".join(f"--review {path}" for path in args.review)
    approval = (
        f" --human-approval-ref {args.human_approval_ref}"
        if args.human_approval_ref
        else ""
    )
    return (
        "codex exec \\\n"
        f"  --cd {json.dumps(str(args.root))} \\\n"
        f"  --sandbox {sandbox} \\\n"
        f"  --output-last-message {json.dumps(output_path)} \\\n"
        "  \"$(python3 tools/render_codex_exec_prompt.py "
        f"--root . --task {args.task} --role {args.role}"
        + (f" {reviews}" if reviews else "")
        + approval
        + f" --output-path {output_path})\""
    )


def render(args: argparse.Namespace) -> str:
    root = args.root.resolve()
    task_record, raw_task = load_task(root, args.task)
    output_path = args.output_path or default_output_path(args.task, args.role)
    prompt_ref, prompt_text = find_prompt(root, args.role)
    review_policy = read_text_if_exists(root / "docs" / "REVIEW_POLICY.md", limit=16000)
    delivery_model = read_text_if_exists(root / ".playbook" / "delivery_execution_model.json", limit=12000)
    verification = read_text_if_exists(root / ".playbook" / "project_verification.json", limit=12000)
    current_state = read_text_if_exists(root / "docs" / "CODEX_PROMPT.md", limit=16000)
    evidence_index = read_text_if_exists(root / "docs" / "EVIDENCE_INDEX.md", limit=12000)
    review_reports = review_report_block(root, args.review)

    access_rule = (
        "READ-ONLY: do not modify files. Your final answer is the report."
        if args.role in READ_ONLY_ROLES
        else "WRITE-SCOPED: modify only files allowed by this role and task scope."
    )

    return f"""# Codex Exec Subagent Prompt

Project root: {root}
Task: {args.task}
Role: {args.role}
Expected report path: {output_path}
Prompt source: {prompt_ref or "inline renderer fallback"}

## Access Rule

{access_rule}

Do not commit. Do not push. Do not approve completion. Human approval remains
external when the delivery model or review policy requires it.

## Suggested Invocation

```bash
{command_hint(args, output_path)}
```

## Role Instructions

{prompt_text.strip() if prompt_text else "[No role prompt found. Use the access rule and task scope only.]"}

## Canonical Task Section

```markdown
{raw_task}
```

## Machine Task Record

```json
{json.dumps(task_record, indent=2, sort_keys=True)}
```

## Review Policy

```markdown
{review_policy.strip() if review_policy else "[docs/REVIEW_POLICY.md not present]"}
```

## Delivery Execution Model

```json
{delivery_model.strip() if delivery_model else "[.playbook/delivery_execution_model.json not present]"}
```

## Project Verification Config

```json
{verification.strip() if verification else "[.playbook/project_verification.json not present]"}
```

## Existing Review Reports

{review_reports}

## Evidence Index

```markdown
{evidence_index.strip() if evidence_index else "[docs/EVIDENCE_INDEX.md not present]"}
```

## Current Session State

```markdown
{current_state.strip() if current_state else "[docs/CODEX_PROMPT.md not present]"}
```
"""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--task", required=True)
    parser.add_argument("--role", required=True, choices=sorted(ROLE_PROMPTS))
    parser.add_argument("--review", action="append", default=[])
    parser.add_argument("--human-approval-ref", default="")
    parser.add_argument("--output-path", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    sys.stdout.write(render(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
