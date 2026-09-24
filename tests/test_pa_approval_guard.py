"""The planning-only negative assertion must never hide unrelated failures."""
import importlib.util
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('pa_approval_guard_check', TOOLS / 'check_pa_approval_guard.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def message(task='PA-00'):
    return f'error: docs/tasks.md:38: TASK_DESIGN_APPROVAL_REQUIRED: task {task} requires an approved design before implementation\nplaybook_validate: errors=1 warnings=0\n'


def test_only_exact_missing_approval_is_expected():
    assert module.expected_rejection(1, message(), {'PA-00'})
    assert not module.expected_rejection(0, message(), {'PA-00'})
    assert not module.expected_rejection(1, message(), {'PA-01'})


def test_other_errors_warnings_and_missing_results_fail():
    assert not module.expected_rejection(1, message().replace('TASK_DESIGN_APPROVAL_REQUIRED', 'TASK_SCHEMA_ERROR'), {'PA-00'})
    assert not module.expected_rejection(1, message() + 'warning: unexpected\n', {'PA-00'})
    assert not module.expected_rejection(1, '', {'PA-00'})


def test_captured_stdout_summary_before_stderr_diagnostics():
    error, summary = message().strip().splitlines()
    assert module.expected_rejection(1, summary + '\n' + error + '\n', {'PA-00'})
