from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Mapping

import yaml

from config.settings import PROJECT_ROOT


LOGGER = logging.getLogger(__name__)
PROJECTS_YAML_PATH = PROJECT_ROOT / "src" / "config" / "projects.yaml"
WORKSPACE_ROOT = PROJECT_ROOT.parent
MAX_PROJECT_CHARS = 1400
DEFAULT_VAULT_PATHS = (
    WORKSPACE_ROOT / "engineering-cognition-vault",
    Path("/srv/codex-entropy/repos/product-3/engineering-cognition-vault"),
)


def build_project_memory_pack(
    *,
    projects_yaml_path: Path = PROJECTS_YAML_PATH,
    workspace_root: Path = WORKSPACE_ROOT,
    vault_root: Path | None = None,
) -> str:
    projects = _load_project_configs(projects_yaml_path)
    if not projects:
        return "Project Memory Pack: no curated projects configured."

    resolved_vault = vault_root or _resolve_vault_root(workspace_root)
    vault_status = _refresh_vault(resolved_vault)
    blocks = [
        "Project Memory Pack",
        "Use this as current-work context. Do not suggest already shipped, closed, or explicitly blocked work.",
        f"Engineering Cognition Vault: {resolved_vault if resolved_vault else 'not found'}",
        f"Vault freshness: {vault_status}",
        "",
    ]
    if resolved_vault:
        global_vault_context = _global_vault_context(resolved_vault)
        if global_vault_context:
            blocks.append(global_vault_context)
            blocks.append("")
    missing_local: list[str] = []
    for project in projects:
        block = _build_project_block(project, workspace_root=workspace_root, vault_root=resolved_vault)
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


def _build_project_block(project: Mapping[str, object], *, workspace_root: Path, vault_root: Path | None) -> str:
    name = str(project.get("name") or "").strip()
    repo = str(project.get("repo") or "").strip()
    focus = _compact(str(project.get("focus") or ""), 220)
    local_path = _resolve_local_repo_path(project, workspace_root)
    lines = [
        f"## {name or repo or 'unknown-project'}",
        f"Repo: {repo or 'not configured'}",
        f"Focus: {focus or 'not specified'}",
    ]
    vault_lines = _vault_project_lines(vault_root, _project_slug(project))
    if vault_lines:
        lines.append("Vault cognition:")
        lines.extend(f"- {line}" for line in vault_lines)
    if local_path is None:
        lines.append("Local workspace: missing")
        return _limit_block(lines)

    lines.append(f"Local workspace: {local_path}")
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


def _project_slug(project: Mapping[str, object]) -> str:
    name = str(project.get("name") or "").strip()
    repo = str(project.get("repo") or "").strip().split("/")[-1]
    slug = name or repo
    return slug.lstrip("-").replace("_", "-").lower()


def _resolve_vault_root(workspace_root: Path) -> Path | None:
    env_path = os.environ.get("COGNITION_VAULT_PATH", "").strip()
    candidates = [Path(env_path)] if env_path else []
    candidates.extend(DEFAULT_VAULT_PATHS)
    candidates.append(workspace_root / "engineering-cognition-vault")
    for candidate in candidates:
        try:
            if candidate and (candidate / ".git").is_dir():
                return candidate
        except OSError:
            LOGGER.warning("Skipping inaccessible cognition vault candidate path=%s", candidate)
    return None


def _refresh_vault(vault_root: Path | None) -> str:
    if vault_root is None:
        return "missing; vault context unavailable"
    status = _git_lines(vault_root, ["status", "--porcelain"])
    if status:
        return "dirty; pull skipped to avoid overwriting local vault work"
    upstream = _git_lines(vault_root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if not upstream:
        return "no upstream; pull skipped"
    pull = _run_git(vault_root, ["pull", "--ff-only"])
    if pull.returncode != 0:
        return _compact(f"pull failed: {pull.stderr or pull.stdout}", 220)
    head = _git_lines(vault_root, ["rev-parse", "--short", "HEAD"])
    return f"pulled latest; head={head[0] if head else 'unknown'}"


def _global_vault_context(vault_root: Path) -> str:
    lines = ["## Vault portfolio context"]
    findings = _matching_lines(vault_root / "40-findings" / "open-findings-map.md", "[[", limit=8)
    if findings:
        lines.append("Open cross-project findings:")
        lines.extend(f"- {line}" for line in findings)
    patterns = _pattern_titles(vault_root / "50-patterns", limit=8)
    if patterns:
        lines.append("Reusable patterns / anti-patterns:")
        lines.extend(f"- {line}" for line in patterns)
    return _limit_block(lines) if len(lines) > 1 else ""


def _vault_project_lines(vault_root: Path | None, slug: str) -> list[str]:
    if vault_root is None or not slug:
        return []
    project_map = vault_root / "10-projects" / f"{slug}.md"
    catalog = vault_root / "_generated" / "summaries" / f"{slug}.catalog.md"
    lines: list[str] = []
    if project_map.is_file():
        for heading in ("Active Capability Profiles", "Open Findings", "Context Packet Scopes", "Eval Memory"):
            section_lines = _markdown_section_lines(project_map, heading, limit=4)
            if section_lines:
                lines.append(f"{heading}: {'; '.join(section_lines)}")
    else:
        lines.append("project map missing in vault")
    if catalog.is_file():
        canonical = _markdown_table_rows(catalog, "Canonical Artifacts", limit=4)
        if canonical:
            lines.append(f"Catalog canonical artifacts: {'; '.join(canonical)}")
    else:
        lines.append("generated catalog missing in vault")
    return [_compact(line, 260) for line in lines if line]


def _git_lines(repo_path: Path, args: list[str]) -> list[str]:
    result = _run_git(repo_path, args)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _run_git(repo_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    askpass_path = _write_github_askpass()
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    if askpass_path:
        env["GIT_ASKPASS"] = str(askpass_path)
    try:
        return subprocess.run(
            ["git", "-c", f"safe.directory={repo_path}", "-C", str(repo_path), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
            env=env,
        )
    except Exception:
        LOGGER.warning("Failed to read git context for %s", repo_path, exc_info=True)
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="")
    finally:
        if askpass_path is not None:
            try:
                askpass_path.unlink()
            except OSError:
                pass


def _write_github_askpass() -> Path | None:
    if not os.environ.get("GITHUB_TOKEN"):
        return None
    handle = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
    path = Path(handle.name)
    with handle:
        handle.write(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  *Username*) printf '%s\\n' x-access-token ;;\n"
            "  *) printf '%s\\n' \"$GITHUB_TOKEN\" ;;\n"
            "esac\n"
        )
    path.chmod(0o700)
    return path


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


def _matching_lines(path: Path, pattern: str, *, limit: int) -> list[str]:
    if not path.is_file():
        return []
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if pattern not in line or line.startswith("| Project |") or line.startswith("|---"):
            continue
        lines.append(_compact(line.strip("| "), 220))
        if len(lines) >= limit:
            break
    return lines


def _pattern_titles(pattern_dir: Path, *, limit: int) -> list[str]:
    if not pattern_dir.is_dir():
        return []
    titles: list[str] = []
    for path in sorted(pattern_dir.glob("*.md")):
        title = ""
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if line.startswith("# "):
                title = line[2:].strip()
                break
        titles.append(title or path.stem.replace("-", " "))
        if len(titles) >= limit:
            break
    return titles


def _markdown_section_lines(path: Path, heading: str, *, limit: int) -> list[str]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    in_section = False
    section_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("## "):
            in_section = line[3:].strip().lower() == heading.lower()
            continue
        if not in_section:
            continue
        if not line or line.startswith("|---") or line.startswith("| Project |"):
            continue
        if line.startswith("#"):
            break
        section_lines.append(_compact(line.strip("-| "), 180))
        if len(section_lines) >= limit:
            break
    return section_lines


def _markdown_table_rows(path: Path, heading: str, *, limit: int) -> list[str]:
    rows = _markdown_section_lines(path, heading, limit=limit + 3)
    cleaned: list[str] = []
    for row in rows:
        if row.startswith("Path | Kind") or row.startswith("------"):
            continue
        cleaned.append(row)
        if len(cleaned) >= limit:
            break
    return cleaned


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
