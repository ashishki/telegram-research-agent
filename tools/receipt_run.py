#!/usr/bin/env python3
"""Run a command and write a schema-valid CommandReceipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TIMEOUT_EXIT_CODE = 124


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(args: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.returncode, result.stdout.strip()


def git_commit(cwd: Path) -> str:
    code, stdout = run_git(["rev-parse", "HEAD"], cwd)
    return stdout if code == 0 and stdout else "not-a-git-repository"


def git_dirty(cwd: Path) -> list[str]:
    code, stdout = run_git(["status", "--short"], cwd)
    if code != 0:
        return ["not-a-git-repository"]
    return stdout.splitlines() if stdout else []


def git_diff_stat(cwd: Path) -> str:
    code, stdout = run_git(["diff", "--stat"], cwd)
    if code != 0:
        return "not-a-git-repository\n"
    return stdout + ("\n" if stdout else "")


def redact(data: bytes, patterns: list[str]) -> tuple[bytes, bool]:
    if not patterns:
        return data, False
    text = data.decode("utf-8", errors="replace")
    changed = False
    for pattern in patterns:
        updated = re.sub(pattern, "[REDACTED]", text)
        changed = changed or updated != text
        text = updated
    return text.encode("utf-8"), changed


def environment_summary() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--producer", default="tools/receipt_run.py")
    parser.add_argument("--parent-receipt-id", default=None)
    parser.add_argument(
        "--redact-pattern",
        action="append",
        default=[],
        help="Regex pattern redacted from stdout/stderr before artifacts are written.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command after --")
    return parser


def normalize_command(command: list[str]) -> list[str]:
    if command and command[0] == "--":
        command = command[1:]
    return command


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = normalize_command(args.command)
    if not command:
        print("receipt_run: missing command after --", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cwd = Path.cwd().resolve()
    receipt_id = f"{args.task_id}-{int(time.time())}-{uuid.uuid4().hex[:8]}"

    commit_before = git_commit(cwd)
    dirty_before = git_dirty(cwd)
    start = utc_now()
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.timeout,
            check=False,
        )
        exit_code = int(completed.returncode)
        stdout = completed.stdout
        stderr = completed.stderr
    except FileNotFoundError as exc:
        exit_code = 127
        stdout = b""
        stderr = f"receipt_run: command not found: {exc.filename}\n".encode("utf-8")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = TIMEOUT_EXIT_CODE
        stdout = exc.stdout or b""
        stderr = (exc.stderr or b"") + f"\nreceipt_run: timeout after {args.timeout} seconds\n".encode(
            "utf-8"
        )
    end = utc_now()

    stdout, stdout_redacted = redact(stdout, args.redact_pattern)
    stderr, stderr_redacted = redact(stderr, args.redact_pattern)

    stdout_path = output_dir / "stdout.txt"
    stderr_path = output_dir / "stderr.txt"
    diff_path = output_dir / "diff_stat.txt"
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    diff_path.write_text(git_diff_stat(cwd), encoding="utf-8")

    commit_after = git_commit(cwd)
    dirty_after = git_dirty(cwd)
    redaction_status = "redacted" if stdout_redacted or stderr_redacted else "not_requested"
    if args.redact_pattern and not (stdout_redacted or stderr_redacted):
        redaction_status = "not_applicable"

    receipt = {
        "schema_version": "playbook.command_receipt.v1",
        "receipt_id": receipt_id,
        "task_id": args.task_id,
        "producer": args.producer,
        "command_argv": command,
        "working_directory": str(cwd),
        "start_timestamp": start,
        "end_timestamp": end,
        "exit_code": exit_code,
        "stdout_artifact_path": stdout_path.name,
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_artifact_path": stderr_path.name,
        "stderr_sha256": sha256_file(stderr_path),
        "repo_commit_before": commit_before,
        "repo_commit_after": commit_after,
        "dirty_state_before": dirty_before,
        "dirty_state_after": dirty_after,
        "diff_stat_artifact_path": diff_path.name,
        "diff_stat_sha256": sha256_file(diff_path),
        "environment_summary": environment_summary() | {"timeout": args.timeout, "timed_out": timed_out},
        "parent_receipt_id": args.parent_receipt_id,
        "redaction_status": redaction_status,
    }
    (output_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
