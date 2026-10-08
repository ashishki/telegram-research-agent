#!/usr/bin/env python3
"""Strict synthetic acceptance: missing/zero/skipped tests cannot return PASS."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def verify_report(path: Path, *, matrix: dict | None = None) -> tuple[bool, str]:
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        return False, 'missing or oversized pytest report'
    try:
        cases = list(ET.parse(path).getroot().iter('testcase'))
    except ET.ParseError:
        return False, 'invalid pytest report'
    if not cases:
        return False, 'zero acceptance tests'
    observed=[(case.get('classname'),case.get('name')) for case in cases]
    if len(observed)!=len(set(observed)):return False,'duplicate acceptance test nodes'
    if any(case.find(tag) is not None for case in cases for tag in ('skipped', 'failure', 'error')):
        return False, 'skipped, failed or errored acceptance test'
    if matrix is not None:
        nodes = {(case.get('classname', ''), case.get('name', '').split('[')[0]) for case in cases}
        missing = [row['spec_id'] for row in matrix['requirements'] if not any(
            (module=='tests.test_pai_requirements' or module.startswith('tests.test_pai_requirements.'))
            and name==row['case_name'] for module,name in nodes)]
        for row in matrix['scenarios']:
            for key in ('synthetic_test_node', 'recovery_test_node'):
                if not row.get(key): continue
                parts = row[key].split('::')
                if len(parts)!=2 or not parts[0].endswith('.py') or not parts[1]:
                    return False, 'invalid binding test node'
                file, name = parts
                name = name.split('[')[0]
                module = file.removesuffix('.py').replace('/', '.')
                if not any((cls == module or cls.startswith(module + '.')) and actual == name for cls, actual in nodes):
                    missing.append(row['scenario_id'] + '/' + key)
        if missing:
            return False, 'missing binding cases: ' + ', '.join(missing)
    return True, f'{len(cases)} acceptance cases, zero skips/failures'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-spec-matrix', action='store_true')
    args, pytest_args = parser.parse_known_args(argv)
    if not pytest_args or any(arg.startswith('--junit') for arg in pytest_args):
        parser.error('explicit test paths required; the runner owns its report path')
    expanded = []
    for arg in pytest_args:
        if arg == 'tests/test_pai_*.py':
            expanded.extend(sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / 'tests').glob('test_pai_*.py')))
        elif arg in {'-q', '-x', '--disable-warnings'} or arg.startswith('--maxfail='):
            expanded.append(arg)
        elif arg.split('::', 1)[0].endswith('.py') and not arg.startswith('-'):
            expanded.append(arg)
        else:
            parser.error('only explicit Python test paths/nodes and bounded reporting options are allowed')
    if not any(arg.split('::', 1)[0].endswith('.py') for arg in expanded):
        parser.error('at least one explicit test file required; no implicit full-suite run')
    with tempfile.TemporaryDirectory(prefix='pai-acceptance-') as directory:
        report = Path(directory) / 'pytest.xml'
        result = subprocess.run([sys.executable, '-m', 'pytest', '--strict-markers',
                                 *expanded, '-o', 'xfail_strict=True', '--junitxml', str(report)], cwd=ROOT)
        if result.returncode:
            return result.returncode
        matrix = json.loads((ROOT / 'docs/design/PAI.requirements.json').read_text()) if args.require_spec_matrix else None
        passed, detail = verify_report(report, matrix=matrix)
        print(('PAI full-spec acceptance: ' if args.require_spec_matrix else 'PAI scoped test verification (full-spec coverage not checked): ') + detail)
        return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
