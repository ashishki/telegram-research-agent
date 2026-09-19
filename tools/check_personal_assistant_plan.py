#!/usr/bin/env python3
"""Check PA planning artifacts against the pinned upstream schemas, offline.

This validates structure and dependency identity, not product correctness,
implementation readiness, design approval, or empirical token savings.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playbook import ROOT, verified_upstream


def main() -> int:
    try:
        upstream = verified_upstream(ROOT)
        from jsonschema import Draft202012Validator
        sys.path.insert(0, str(upstream / 'tools'))
        import playbook_validate
        import feature_design_lib

        def read(path: Path):
            return json.loads(path.read_text(encoding='utf-8'))

        registry_path = ROOT / 'docs/design/PA.design.json'
        registry = read(registry_path)
        manifest = read(ROOT / '.playbook/instruction_manifest.json')
        for name, value in [('feature_design', registry), ('instruction_manifest', manifest)]:
            validator = Draft202012Validator(read(upstream / ('schemas/' + name + '.schema.json')))
            validator.validate(value)
        findings, _ = feature_design_lib.validate_design_file(ROOT, registry_path)
        errors = [f for f in findings if f.severity == 'error']
        if errors:
            raise ValueError('; '.join(f.check_id + ': ' + f.message for f in errors))
        tasks = {b.task_id: b.to_record() for b in playbook_validate.parse_task_blocks(ROOT / 'docs/tasks.md') if b.task_id.startswith('PA-')}
        slices = {s['slice_id']: s for s in registry['slices']}
        if len(slices) != len(registry['slices']) or set(tasks) != set(slices):
            raise ValueError('PA task IDs and unique slice IDs must match')
        for key, item in slices.items():
            if set(tasks[key]['dependencies']) != set(item['dependencies']):
                raise ValueError('Dependency mismatch: ' + key)
            if not tasks[key]['acceptance_criteria'] or not item['verification']:
                raise ValueError('Missing acceptance/verification: ' + key)
        visited, visiting = set(), set()
        def visit(key):
            if key in visiting:
                raise ValueError('Dependency cycle: ' + key)
            if key in visited:
                return
            visiting.add(key)
            for dependency in slices[key]['dependencies']:
                if dependency not in slices:
                    raise ValueError('Unknown dependency: ' + dependency)
                visit(dependency)
            visiting.remove(key)
            visited.add(key)
        for key in slices:
            visit(key)
        for artifact in manifest['artifacts']:
            path = (ROOT / artifact['path']).resolve()
            if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
                raise ValueError('Missing/unsafe instruction reference: ' + artifact['path'])
        required = [registry['brief_ref'], *registry['architecture_refs'], 'docs/PLAYBOOK_ADOPTION.md', 'docs/prompts/personal_assistant_implementer.md', 'docs/ASSISTANT_BOUNDARIES.md']
        for ref in required:
            if not (ROOT / ref.split('#', 1)[0]).is_file():
                raise ValueError('Missing required document: ' + ref)
        for ref, limit in [(registry['brief_ref'], 8000), ('docs/design/PA.md', 20000)]:
            if len((ROOT / ref).read_text(encoding='utf-8')) > limit:
                raise ValueError('Context would be truncated by upstream renderer: ' + ref)
        print(f'PA plan: {len(slices)} consistent slices; schemas, references, dependencies and context limits passed.')
        print('Design state: ' + registry['status'] + '; no product, human-approval or runtime claim.')
        return 0
    except Exception as exc:
        print('PA plan check failed: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
