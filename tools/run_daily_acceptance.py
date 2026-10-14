#!/usr/bin/env python3
"""Scoped local daily-package acceptance; no historical suite or provider calls."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TESTS = ('tests/test_daily_entrypoint.py', 'tests/test_daily_controls.py', 'tests/test_daily_dispatch.py',
         'tests/test_daily_telegram_routes.py', 'tests/test_daily_telegram_transport.py',
         'tests/test_daily_model_protocols.py', 'tests/test_daily_eval_manifest.py',
         'tests/test_daily_conversation.py', 'tests/test_daily_coverage.py',
         'tests/test_daily_profiles.py','tests/test_daily_projects.py','tests/test_daily_source_freshness.py',
         'tests/test_daily_retrieval.py','tests/test_daily_web_route.py','tests/test_daily_synthesis.py','tests/test_daily_brief_selection.py',
         'tests/test_daily_github_context.py','tests/test_daily_research.py','tests/test_daily_event_clusters.py','tests/test_daily_brief_editorial.py',
         'tests/test_daily07_review_repairs.py',
         'tests/test_daily_document_dialogue.py','tests/test_daily_feedback.py','tests/test_daily_memory_context.py','tests/test_daily_telegram_rich.py',
         'tests/test_daily08_review_repairs.py')


def main():
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'), PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    return subprocess.run([sys.executable, str(ROOT / 'tools/run_pai_acceptance.py'), '-q', *TESTS], cwd=ROOT, env=env, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
