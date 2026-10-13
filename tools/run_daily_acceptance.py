#!/usr/bin/env python3
"""Scoped local daily-package acceptance; no historical suite or provider calls."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TESTS = ('tests/test_daily_entrypoint.py', 'tests/test_daily_controls.py', 'tests/test_daily_dispatch.py',
         'tests/test_daily_telegram_routes.py', 'tests/test_daily_telegram_transport.py')


def main():
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    return subprocess.run([sys.executable, '-m', 'pytest', '-q', *TESTS], cwd=ROOT, env=env, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
