#!/usr/bin/env python3
"""Planning-only assertion of expected rejection; never grants approval.

The real project verifier still requires the unmodified upstream validator to
pass. This separate check proves a draft programme stays blocked for exactly
its missing design approval, and rejects every other error/warning.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

from playbook import ROOT, verified_upstream


def expected_rejection(returncode: int, output: str, task_ids: set[str]) -> bool:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    errors = [line for line in lines if line.startswith('error: ')]
    pattern = re.compile(r'^error: docs/tasks\.md:\d+: TASK_DESIGN_APPROVAL_REQUIRED: task (PAI?-[0-9]+) requires an approved design before implementation$')
    matches = [pattern.fullmatch(line) for line in errors]
    return (
        returncode == 1
        and len(errors) == len(task_ids)
        and all(matches)
        and {match.group(1) for match in matches if match} == task_ids
        and len(lines) == len(errors) + 1
        and f'playbook_validate: errors={len(task_ids)} warnings=0' in lines
    )


def draft_task_ids(designs: list[dict], tasks: list[dict]) -> set[str] | None:
    """Known programme union only; approved states still use the raw validator."""
    features = [design['feature_id'] for design in designs]
    if len(set(features)) != len(features) or not set(features) <= {'PA', 'PAI'}:
        raise ValueError('Unexpected programme registry')
    statuses = [design['status'] for design in designs]
    if any(status not in {'draft', 'review_required', 'approved', 'implemented'} for status in statuses):
        raise ValueError('Unexpected design lifecycle state')
    if any(status in {'approved', 'implemented'} for status in statuses):
        return None
    slices = [item for design in designs for item in design['slices']]
    ids = [item['slice_id'] for item in slices]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate programme slice')
    for design in designs:
        if any(not re.fullmatch(re.escape(design['feature_id']) + r'-[0-9]+', item['slice_id']) for item in design['slices']):
            raise ValueError('Slice outside its programme registry')
    task_ids = [item['task_id'] for item in tasks]
    if len(task_ids) != len(set(task_ids)) or set(task_ids) != set(ids):
        raise ValueError('All active tasks must belong to the registered draft programmes')
    if any(item['status'] != 'planned' for item in tasks + slices):
        raise ValueError('An unapproved programme cannot start implementation')
    return set(ids)


def main() -> int:
    try:
        upstream = verified_upstream(ROOT)
        sys.path.insert(0, str(upstream / 'tools'))
        import playbook_validate
        designs = [json.loads((ROOT / 'docs/design/PA.design.json').read_text(encoding='utf-8'))]
        pai = ROOT / 'docs/design/PAI.design.json'
        if pai.is_file():
            designs.append(json.loads(pai.read_text(encoding='utf-8')))
        tasks = [block.to_record() for block in playbook_validate.parse_task_blocks(ROOT / 'docs/tasks.md')]
        result = subprocess.run(
            [sys.executable, str(upstream / 'tools/playbook_validate.py'), '--root', '.', '--check', 'tasks', '--check', 'references'],
            cwd=ROOT, text=True, capture_output=True, check=False, timeout=120,
        )
        output = result.stdout + result.stderr
        task_ids = draft_task_ids(designs, tasks)
        if task_ids is None:
            print(output, end='')
            return result.returncode
        if not expected_rejection(result.returncode, output, task_ids):
            print(output, end='')
            raise ValueError('Unexpected validation result; only exact missing-approval rejection is expected')
        print(f'Expected approval guard verified for {len(task_ids)} planned tasks.')
        print('PLANNING CHECK ONLY: formal programme progression remains blocked until real design approval; project verifier is unchanged.')
        return 0
    except Exception as exc:
        print('PA approval guard check failed: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
