#!/usr/bin/env python3
"""Generated project verification entrypoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SHELL_NAMES = {"sh", "bash", "zsh", "fish", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "not-a-git-repository"


def artifact_ref(path: Path, root: Path) -> dict[str, str]:
    return {
        "path": str(path.relative_to(root)),
        "sha256": sha256_file(path),
    }


def safe_relative_path(root: Path, raw: str) -> Path | None:
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        return None
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def load_config(root: Path, explicit_path: str | None) -> tuple[dict[str, Any] | None, list[str]]:
    path = Path(explicit_path) if explicit_path else root / ".playbook/project_verification.json"
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        return None, [f"project verification config missing: {path}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"project verification config is invalid JSON: {exc}"]
    if not isinstance(data, dict):
        return None, ["project verification config must be a JSON object"]
    return data, []


def materialize_argv(argv: list[str], root: Path) -> list[str]:
    replacements = {
        "{python}": sys.executable,
        "{root}": str(root),
    }
    rendered: list[str] = []
    for value in argv:
        for placeholder, replacement in replacements.items():
            value = value.replace(placeholder, replacement)
        rendered.append(value)
    return rendered


def has_self_reference(argv: list[str]) -> bool:
    for value in argv:
        normalized = value.replace("\\", "/")
        if normalized == "verify_project.py" or normalized.endswith("/verify_project.py") or "tools/verify_project.py" in normalized:
            return True
    return False


def validate_check(raw: Any, root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return None, ["check must be an object"]
    check_id = raw.get("id")
    argv = raw.get("argv")
    if not isinstance(check_id, str) or not check_id:
        errors.append("check.id must be a non-empty string")
    elif not all(char.isalnum() or char in "_.-" for char in check_id):
        errors.append(f"check {check_id} id may contain only letters, numbers, underscore, dot, or hyphen")
    if not isinstance(argv, list) or not argv or not all(isinstance(part, str) and part for part in argv):
        errors.append(f"check {check_id or '<unknown>'} argv must be a non-empty array of strings")
        argv = []
    argv = list(argv)
    if has_self_reference(argv):
        errors.append(f"check {check_id or '<unknown>'} must not call tools/verify_project.py recursively")
    shell_name = Path(argv[0]).name.lower() if argv else ""
    if shell_name in SHELL_NAMES and raw.get("allow_shell") is not True:
        errors.append(f"check {check_id or '<unknown>'} uses shell execution without allow_shell=true")
    cwd_raw = raw.get("cwd", ".")
    if not isinstance(cwd_raw, str) or safe_relative_path(root, cwd_raw) is None:
        errors.append(f"check {check_id or '<unknown>'} cwd must be relative and stay inside project root")
    expected_exit = raw.get("expected_exit_code", 0)
    if not isinstance(expected_exit, int):
        errors.append(f"check {check_id or '<unknown>'} expected_exit_code must be an integer")
    required = raw.get("required", True)
    if not isinstance(required, bool):
        errors.append(f"check {check_id or '<unknown>'} required must be boolean")
    timeout = raw.get("timeout_seconds")
    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
        errors.append(f"check {check_id or '<unknown>'} timeout_seconds must be positive")
    env = raw.get("env", {})
    if not isinstance(env, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in env.items()):
        errors.append(f"check {check_id or '<unknown>'} env must map strings to strings")
    platforms = raw.get("platforms")
    if platforms is not None and (not isinstance(platforms, list) or not all(isinstance(item, str) for item in platforms)):
        errors.append(f"check {check_id or '<unknown>'} platforms must be an array of strings")
    if errors:
        return None, errors
    return {
        "id": check_id,
        "argv": argv,
        "cwd": cwd_raw,
        "required": required,
        "expected_exit_code": expected_exit,
        "timeout_seconds": timeout,
        "env": env,
        "platforms": platforms,
    }, []


def validate_config(config: dict[str, Any], root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if config.get("schema_version") != "playbook.project_verification.v1":
        errors.append("project verification config schema_version must be playbook.project_verification.v1")
    raw_checks = config.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        errors.append("project verification config checks must be a non-empty array")
        return [], errors
    checks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_checks:
        check, check_errors = validate_check(raw, root)
        errors.extend(check_errors)
        if check is None:
            continue
        if check["id"] in seen:
            errors.append(f"duplicate check id: {check['id']}")
            continue
        seen.add(check["id"])
        checks.append(check)
    return checks, errors


def write_result(root: Path, checks: list[dict[str, Any]], config_errors: list[str], started_at: str) -> Path:
    artifacts_root = root / ".playbook-artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    required_failures = sum(
        1
        for check in checks
        if check.get("required") and not check.get("passed", False)
    )
    payload = {
        "schema_version": "playbook.project_verification_result.v1",
        "project_commit": git_commit(root),
        "started_at": started_at,
        "finished_at": utc_now(),
        "platform": platform.platform(),
        "python_executable": sys.executable,
        "checks": checks,
        "configuration_errors": config_errors,
        "required_failures": required_failures,
    }
    result_path = artifacts_root / "project_verification.json"
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result_path


def run_check(root: Path, artifacts_root: Path, check: dict[str, Any]) -> dict[str, Any]:
    current_platform = sys.platform
    platforms = check.get("platforms")
    argv = materialize_argv(check["argv"], root)
    check_dir = artifacts_root / "project_verification" / check["id"]
    check_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = check_dir / "stdout.txt"
    stderr_path = check_dir / "stderr.txt"
    if platforms and current_platform not in platforms:
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(f"skipped on platform {current_platform}\n", encoding="utf-8")
        passed = not check["required"]
        return {
            "id": check["id"],
            "argv": argv,
            "cwd": check["cwd"],
            "required": check["required"],
            "expected_exit_code": check["expected_exit_code"],
            "exit_code": None,
            "passed": passed,
            "skipped": True,
            "stdout_ref": artifact_ref(stdout_path, root),
            "stderr_ref": artifact_ref(stderr_path, root),
        }
    env = os.environ.copy()
    env.update(check.get("env", {}))
    cwd = safe_relative_path(root, check["cwd"])
    assert cwd is not None
    timed_out = False
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=check.get("timeout_seconds"),
            check=False,
        )
        exit_code = int(completed.returncode)
        stdout = completed.stdout
        stderr = completed.stderr
    except FileNotFoundError as exc:
        exit_code = 127
        stdout = b""
        stderr = f"verify_project: command not found: {exc.filename}\n".encode("utf-8")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout = exc.stdout or b""
        stderr = (exc.stderr or b"") + f"\nverify_project: timeout after {check.get('timeout_seconds')} seconds\n".encode("utf-8")
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    passed = exit_code == check["expected_exit_code"]
    return {
        "id": check["id"],
        "argv": argv,
        "cwd": check["cwd"],
        "required": check["required"],
        "expected_exit_code": check["expected_exit_code"],
        "exit_code": exit_code,
        "passed": passed,
        "skipped": False,
        "timed_out": timed_out,
        "stdout_ref": artifact_ref(stdout_path, root),
        "stderr_ref": artifact_ref(stderr_path, root),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    started_at = utc_now()
    config, load_errors = load_config(root, args.config)
    if config is None:
        result_path = write_result(root, [], load_errors, started_at)
        for error in load_errors:
            print(f"verify_project: {error}", file=sys.stderr)
        print(f"verify_project: result={result_path}")
        return 2
    checks, config_errors = validate_config(config, root)
    if config_errors:
        result_path = write_result(root, [], config_errors, started_at)
        for error in config_errors:
            print(f"verify_project: {error}", file=sys.stderr)
        print(f"verify_project: result={result_path}")
        return 2
    artifacts_root = root / ".playbook-artifacts"
    results = [run_check(root, artifacts_root, check) for check in checks]
    result_path = write_result(root, results, [], started_at)
    required_failures = sum(1 for item in results if item["required"] and not item["passed"])
    for item in results:
        status = "SKIP" if item["skipped"] else "PASS" if item["passed"] else "FAIL"
        print(f"{status}: {item['id']} exit={item['exit_code']}")
    print(f"verify_project: required_failures={required_failures} result={result_path}")
    return 1 if required_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
