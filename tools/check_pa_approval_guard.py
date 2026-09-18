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
    pattern = re.compile(r'^error: docs/tasks\.md:\d+: TASK_DESIGN_APPROVAL_REQUIRED: task (PA-[0-9]+) requires an approved design before implementation$')
    matches = [pattern.fullmatch(line) for line in errors]
    return (
        returncode == 1
        and len(errors) == len(task_ids)
        and all(matches)
        and {match.group(1) for match in matches if match} == task_ids
        and len(lines) == len(errors) + 1
        and lines[-1] == f'playbook_validate: errors={len(task_ids)} warnings=0'
    )


def main() -> int:
    try:
        upstream = verified_upstream(ROOT)
        sys.path.insert(0, str(upstream / 'tools'))
        import playbook_validate
        design = json.loads((ROOT / 'docs/design/PA.design.json').read_text(encoding='utf-8'))
        tasks = [block.to_record() for block in playbook_validate.parse_task_blocks(ROOT / 'docs/tasks.md')]
        result = subprocess.run(
            [sys.executable, str(upstream / 'tools/playbook_validate.py'), '--root', '.', '--check', 'tasks', '--check', 'references'],
            cwd=ROOT, text=True, capture_output=True, check=False, timeout=120,
        )
        output = result.stdout + result.stderr
        if design['status'] in {'approved', 'implemented'}:
            print(output, end='')
            return result.returncode
        if design['status'] not in {'draft', 'review_required'}:
            raise ValueError('Unexpected design lifecycle state')
        task_ids = {item['task_id'] for item in tasks}
        if task_ids != {item['slice_id'] for item in design['slices']}:
            raise ValueError('All active tasks must belong to this draft programme')
        if any(item['status'] != 'planned' for item in tasks) or any(item['status'] != 'planned' for item in design['slices']):
            raise ValueError('An unapproved programme cannot start implementation')
        if not expected_rejection(result.returncode, output, task_ids):
            print(output, end='')
            raise ValueError('Unexpected validation result; only exact missing-approval rejection is expected')
        print(f'Expected approval guard verified for {len(task_ids)} planned tasks.')
        print('PLANNING CHECK ONLY: implementation remains blocked until real design approval; project verifier is unchanged.')
        return 0
    except Exception as exc:
        print('PA approval guard check failed: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
