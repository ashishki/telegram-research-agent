from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Mapping

import yaml

from config.settings import PROJECT_ROOT


LOGGER = logging.getLogger(__name__)
PROJECTS_YAML_PATH = PROJECT_ROOT / "src" / "config" / "projects.yaml"
WORKSPACE_ROOT = PROJECT_ROOT.parent
MAX_PROJECT_CHARS = 1400
MAX_MANUAL_STATE_CHARS = 700


def build_project_memory_pack(
    *,
    projects_yaml_path: Path = PROJECTS_YAML_PATH,
    workspace_root: Path = WORKSPACE_ROOT,
) -> str:
    projects = _load_project_configs(projects_yaml_path)
    if not projects:
        return "Project Memory Pack: no curated projects configured."

    blocks = [
        "Project Memory Pack",
        "Use this as current-work context. Do not suggest already shipped, closed, or explicitly blocked work.",
        "",
    ]
    missing_local: list[str] = []
    for project in projects:
        block = _build_project_block(project, workspace_root=workspace_root)
        if "Local workspace: missing" in block:
            missing_local.append(str(project.get("name") or project.get("repo") or "unknown"))
        blocks.append(block)
        blocks.append("")
    if missing_local:
        blocks.append(f"Local workspace missing for: {', '.join(missing_local)}. Use GitHub freshness snapshot only.")
    return "\n".join(blocks).strip()


def _load_project_configs(projects_yaml_path: Path) -> list[dict]:
    try:
        data = yaml.safe_load(projects_yaml_path.read_text(encoding="utf-8")) or {}
    except Exception:
        LOGGER.warning("Failed to load project configs for memory pack", exc_info=True)
        return []
    return [project for project in data.get("projects", []) if isinstance(project, dict)]


def _build_project_block(project: Mapping[str, object], *, workspace_root: Path) -> str:
    name = str(project.get("name") or "").strip()
    repo = str(project.get("repo") or "").strip()
    focus = _compact(str(project.get("focus") or ""), 220)
    local_path = _resolve_local_repo_path(project, workspace_root)
    lines = [
        f"## {name or repo or 'unknown-project'}",
        f"Repo: {repo or 'not configured'}",
        f"Focus: {focus or 'not specified'}",
    ]
    if local_path is None:
        lines.append("Local workspace: missing")
        return _limit_block(lines)

    lines.append(f"Local workspace: {local_path}")
    manual_state = _read_manual_project_state(local_path)
    if manual_state:
        lines.append("Manual state:")
        lines.extend(f"- {line}" for line in _compact_lines(manual_state, limit=5, char_limit=MAX_MANUAL_STATE_CHARS))
    else:
        lines.append("Manual state: not recorded.")

    commits = _git_lines(local_path, ["log", "--since=28 days ago", "--pretty=format:%cs %h %s", "-n", "8"])
    if commits:
        lines.append("Recently shipped / changed:")
        lines.extend(f"- {line}" for line in commits[:8])

    open_tasks, done_tasks = _task_lines(local_path / "docs" / "tasks.md")
    if open_tasks:
        lines.append("Open tasks:")
        lines.extend(f"- {line}" for line in open_tasks[:5])
    if done_tasks:
        lines.append("Recently completed tasks:")
        lines.extend(f"- {line}" for line in done_tasks[:4])

    changed_areas = _changed_areas(local_path)
    if changed_areas:
        lines.append("Recently touched areas:")
        lines.extend(f"- {line}" for line in changed_areas[:8])
    return _limit_block(lines)


def _resolve_local_repo_path(project: Mapping[str, object], workspace_root: Path) -> Path | None:
    repo = str(project.get("repo") or "").strip()
    name = str(project.get("name") or "").strip()
    repo_name = repo.split("/")[-1] if repo else ""
    candidates = [
        value
        for value in (
            repo_name,
            repo_name.lstrip("-"),
            name,
            name.replace("_", "-"),
            name.replace("-", "_"),
        )
        if value
    ]
    for candidate in dict.fromkeys(candidates):
        path = workspace_root / candidate
        if (path / ".git").is_dir():
            return path
    return None


def _read_manual_project_state(repo_path: Path) -> str:
    for relative in ("docs/project_state.md", "PROJECT_STATE.md", ".codex/project_state.md"):
        path = repo_path / relative
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="ignore")
    return ""


def _git_lines(repo_path: Path, args: list[str]) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception:
        LOGGER.warning("Failed to read git context for %s", repo_path, exc_info=True)
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _task_lines(tasks_path: Path) -> tuple[list[str], list[str]]:
    if not tasks_path.is_file():
        return [], []
    open_tasks: list[str] = []
    done_tasks: list[str] = []
    for line in tasks_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ]"):
            open_tasks.append(_compact(stripped[5:].strip(), 220))
        elif stripped.startswith("- [x]") or stripped.startswith("- [X]"):
            done_tasks.append(_compact(stripped[5:].strip(), 220))
    return open_tasks, done_tasks[-6:]


def _changed_areas(repo_path: Path) -> list[str]:
    lines = _git_lines(repo_path, ["diff", "--name-only", "HEAD~20..HEAD"])
    if not lines:
        lines = _git_lines(repo_path, ["diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"])
    areas: list[str] = []
    for line in lines:
        parts = line.split("/")
        area = parts[0] if len(parts) == 1 else "/".join(parts[:2])
        areas.append(area)
    return list(dict.fromkeys(areas))


def _compact_lines(value: str, *, limit: int, char_limit: int) -> list[str]:
    lines: list[str] = []
    total = 0
    for raw_line in value.splitlines():
        line = raw_line.strip(" -\t")
        if not line or line.startswith("#"):
            continue
        line = _compact(line, 180)
        projected = total + len(line)
        if lines and projected > char_limit:
            break
        lines.append(line)
        total = projected
        if len(lines) >= limit:
            break
    return lines


def _compact(value: str, limit: int) -> str:
    value = " ".join((value or "").split())
    if len(value) <= limit:
        return value
    trimmed = value[: max(0, limit - 1)].rstrip()
    split_at = trimmed.rfind(" ")
    if split_at >= 80:
        trimmed = trimmed[:split_at].rstrip()
    return f"{trimmed}..."


def _limit_block(lines: list[str]) -> str:
    block = "\n".join(lines).strip()
    if len(block) <= MAX_PROJECT_CHARS:
        return block
    return f"{block[:MAX_PROJECT_CHARS - 3].rstrip()}..."
