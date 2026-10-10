"""The planning-only negative assertion must never hide unrelated failures."""
import importlib.util
import sys
from pathlib import Path
from copy import deepcopy
import pytest

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


def programmes():
    designs=[{'feature_id':'PA','status':'review_required','slices':[{'slice_id':'PA-00','status':'planned'}]},
             {'feature_id':'PAI','status':'draft','slices':[{'slice_id':'PAI-00','status':'planned'}]}]
    tasks=[{'task_id':'PA-00','status':'planned'},{'task_id':'PAI-00','status':'planned'}]
    return designs,tasks


def test_exact_pa_pai_union_is_expected_rejection_without_hiding_other_failures():
    designs,tasks=programmes();ids=module.draft_task_ids(designs,tasks)
    errors='\n'.join(message(task).splitlines()[0] for task in sorted(ids))
    output=errors+'\nplaybook_validate: errors=2 warnings=0\n'
    assert module.expected_rejection(1,output,ids)
    assert not module.expected_rejection(0,output,ids)
    assert not module.expected_rejection(1,output+'error: unexpected\n',ids)
    assert not module.expected_rejection(1,message('PA-00'),ids)
    assert not module.expected_rejection(1,output.replace('PAI-00','PAI-01'),ids)


@pytest.mark.parametrize('change',['foreign_task','missing_task','duplicate_task','duplicate_slice','wrong_prefix','wrong_feature','unknown_state','started_task','started_slice'])
def test_union_denies_unregistered_duplicate_malformed_or_started_programme(change):
    designs,tasks=programmes()
    if change=='foreign_task':tasks.append({'task_id':'RFX-00','status':'planned'})
    elif change=='missing_task':tasks.pop()
    elif change=='duplicate_task':tasks.append(deepcopy(tasks[0]))
    elif change=='duplicate_slice':designs[0]['slices'].append(deepcopy(designs[0]['slices'][0]))
    elif change=='wrong_prefix':designs[1]['slices'][0]['slice_id']='PA-99'
    elif change=='wrong_feature':designs[1]['feature_id']='FOREIGN'
    elif change=='unknown_state':designs[1]['status']='self_approved'
    elif change=='started_task':tasks[1]['status']='completed'
    else:designs[1]['slices'][0]['status']='in_progress'
    with pytest.raises(ValueError):module.draft_task_ids(designs,tasks)


def test_any_approved_programme_requires_real_raw_upstream_validation():
    designs,tasks=programmes();designs[0]['status']='approved'
    assert module.draft_task_ids(designs,tasks) is None


def test_legacy_pa_only_draft_remains_supported():
    designs,tasks=programmes()
    assert module.draft_task_ids(designs[:1],tasks[:1])=={'PA-00'}
