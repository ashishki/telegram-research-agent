#!/usr/bin/env python3
"""Run the pinned development-only Playbook; never fetch or enable runtime tools."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from types import ModuleType
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


def load_generated_verifier(upstream: Path) -> ModuleType:
    """Load only the literal verifier from the already verified pinned kit.

    Do not import or execute the initializer: it is an installer, not a runtime
    dependency. Refuse changed template shapes rather than evaluating code.
    """
    source_path = upstream / 'tools/init_playbook_project.py'
    if source_path.is_symlink() or not source_path.is_file():
        raise ValueError('Pinned verifier template is missing or symlinked')
    tree = ast.parse(source_path.read_text(encoding='utf-8'), filename=str(source_path))
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == 'verify_project_script']
    if len(functions) != 1 or len(functions[0].body) != 1:
        raise ValueError('Unexpected pinned verifier template shape')
    returned = functions[0].body[0]
    if not (isinstance(returned, ast.Return) and isinstance(returned.value, ast.Constant)
            and isinstance(returned.value.value, str)):
        raise ValueError('Verifier template must be a literal string, not executable generation')
    source = returned.value.value
    module = ModuleType('_pinned_playbook_generated_verifier')
    module.__file__ = str(source_path) + '::verify_project_script'
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    if not callable(getattr(module, 'main', None)):
        raise ValueError('Pinned verifier template has no callable entrypoint')
    return module


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
        if name == 'verify_project':
            verifier = load_generated_verifier(upstream)
            previous_argv = sys.argv
            try:
                sys.argv = ['tools/verify_project.py', *args]
                return int(verifier.main())
            finally:
                sys.argv = previous_argv
        script = upstream / 'tools' / (name + '.py')
        if not script.is_file() or script.is_symlink():
            raise ValueError('Pinned tool is missing or symlinked')
        return subprocess.run([sys.executable, str(script), *args], cwd=ROOT,
                              check=False).returncode
    except (OSError, ValueError, KeyError, SyntaxError, subprocess.TimeoutExpired) as exc:
        print('Playbook blocked: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
