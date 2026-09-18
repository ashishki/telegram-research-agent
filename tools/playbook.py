#!/usr/bin/env python3
"""Run the pinned development-only Playbook; never fetch or enable runtime tools."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = frozenset({
    'playbook_validate', 'verify_project', 'resolve_release_readiness',
    'feature_workflow', 'run_codex_role', 'render_codex_exec_prompt',
    'render_slice_context', 'check_maintainability', 'planning_depth',
    'receipt_run', 'cognition_index', 'context_packet_builder',
    'cost_rollup', 'integrity_check', 'skill_security_gate',
})


def git(root: Path, *args: str) -> str:
    result = subprocess.run(['git', '-C', str(root), *args], text=True,
                            capture_output=True, check=False, timeout=30)
    if result.returncode:
        raise ValueError('Git verification failed: ' + ' '.join(args[:2]))
    return result.stdout.strip()


def verified_upstream(root: Path) -> Path:
    root = root.resolve()
    lock = json.loads((root / '.playbook/upstream.lock.json').read_text(encoding='utf-8'))
    rel = Path(lock['path'])
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('Upstream path must be inside this repository')
    candidate = root / rel
    for part in [candidate, *candidate.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise ValueError('Symlinked upstream paths are forbidden')
    upstream = candidate.resolve()
    if not upstream.is_relative_to(root) or not (upstream / '.git').exists():
        raise ValueError('Initialize the pinned submodule: git submodule update --init --checkout -- .playbook/upstream')
    expected = lock['commit']
    if len(expected) != 40 or any(c not in '0123456789abcdef' for c in expected):
        raise ValueError('A full immutable commit SHA is required')
    if Path(git(upstream, 'rev-parse', '--show-toplevel')).resolve() != upstream:
        raise ValueError('Upstream is not an independent Git worktree')
    if git(upstream, 'rev-parse', 'HEAD') != expected:
        raise ValueError('Upstream HEAD does not match the lock')
    entry = git(root, 'ls-files', '--stage', '--', rel.as_posix())
    if not entry.startswith('160000 ' + expected + ' 0\t'):
        raise ValueError('The Git index must pin the same upstream commit')
    url = git(root, 'config', '--file', '.gitmodules', '--get',
              'submodule.ai-workflow-playbook.url')
    if url != lock['repository']:
        raise ValueError('Submodule URL does not match the lock')
    if git(upstream, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('Upstream has local changes; do not execute an unreviewed kit')
    return upstream


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {'-h', '--help'}:
        print('Usage: python tools/playbook.py --check-pin | TOOL [upstream arguments]')
        print('Tools: ' + ', '.join(sorted(TOOLS)))
        return 0
    name, *args = argv
    if name != '--check-pin' and name not in TOOLS:
        print('Unsupported Playbook tool: ' + name, file=sys.stderr)
        return 2
    try:
        upstream = verified_upstream(ROOT)
        if name == '--check-pin':
            print('Playbook pin verified; no model, hook or application runtime enabled.')
            return 0
        script = upstream / 'tools' / (name + '.py')
        if not script.is_file() or script.is_symlink():
            raise ValueError('Pinned tool is missing or symlinked')
        return subprocess.run([sys.executable, str(script), *args], cwd=ROOT,
                              check=False).returncode
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print('Playbook blocked: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
