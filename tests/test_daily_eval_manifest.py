"""Frozen native synthetic cases and strict trace checks, not model-quality scores."""
from pathlib import Path
import pytest
from prm.runtime.evaluation import load_daily_manifest,verify_daily_trace


def test_manifest_freezes_twenty_native_cases_and_full_target():
    manifest=load_daily_manifest(Path('evals/assistant_judge/daily_tasks.v1.json'))
    assert len(manifest['cases'])==20 and manifest['target_units']==120
    assert sum(manifest['target_counts'].values())==120
    assert manifest['independent_holdout_ready'] is False

from copy import deepcopy
from prm.runtime.evaluation import validate_daily_manifest,daily_digest,make_daily_trace,verify_daily_trace_suite
from prm.storage.postgres import StorageError
from tests.pai_runtime_fixtures import pai
from tests.daily_eval_fixtures import run_daily_fixture

MANIFEST=load_daily_manifest(Path('evals/assistant_judge/daily_tasks.v1.json'))


def relation_fixture(case_index=0):
    import json
    packet=json.loads(Path('docs/evidence/daily-package-03-20261013-traces.json').read_text())
    case=MANIFEST['cases'][case_index]
    trace=deepcopy(next(t for t in packet['traces'] if t['case_id']==case['case_id']))
    trace['manifest_digest']=daily_digest(MANIFEST);trace['case_digest']=daily_digest(case)
    trace['view_kind']=case['receipt_contract']['view_kind']
    for index,item in enumerate(trace['objects'],1):
        item.update(turn_index=index,input_sha256=case['receipt_contract']['turn_input_digests'][index-1],status=trace['outcome']['status'])
    trace['turn_bindings']=deepcopy(trace['objects'])
    assert verify_daily_trace(MANIFEST,trace)['mechanics_met']
    return trace


def minimal_trace():return relation_fixture()


@pytest.mark.parametrize('change',['source','scenario','duplicate','missing','snapshot'])
def test_missing_cases_or_cross_split_source_and_scenario_leaks_fail(change):
    manifest=deepcopy(MANIFEST)
    if change=='source':manifest['cases'][7]['split']='holdout';manifest['cases'][7]['scenario_family']='different_family'
    if change=='scenario':manifest['cases'][5]['split']='holdout';manifest['cases'][5]['scenario_family']=manifest['cases'][4]['scenario_family']
    if change=='duplicate':manifest['cases'][1]['case_id']=manifest['cases'][0]['case_id']
    if change=='missing':manifest['cases'].pop()
    if change=='snapshot':manifest['cases'][0]['sources'][0]['text']='Changed source snapshot'
    with pytest.raises(StorageError):validate_daily_manifest(manifest)


@pytest.mark.parametrize('change',['turn','evidence','binding','digest','latency','secret','false_provider','unknown_field'])
def test_trace_requires_complete_typed_evidence_and_rejects_secret_canaries(change):
    trace=minimal_trace()
    if change=='turn':trace['visible_turns'].pop()
    if change=='evidence':trace['source_snapshots']=[]
    if change=='binding':trace['objects'][0]['kind']='source'
    if change=='digest':trace['manifest_digest']='0'*64
    if change=='latency':trace['duration_ms']=True
    if change=='secret':trace['visible_turns'][1]['text']='PRIVATE_CANARY_DO_NOT_EXPORT'
    if change=='false_provider':trace['provider_execution']=True
    if change=='unknown_field':trace['authorization']='Bearer secret_canary'
    with pytest.raises(StorageError):verify_daily_trace(MANIFEST,trace)


def test_matching_words_or_claimed_success_cannot_replace_constraints():
    trace=minimal_trace();trace['outcome']['status']='provider_egress_required'
    with pytest.raises(StorageError):verify_daily_trace(MANIFEST,trace)
    trace=minimal_trace();trace['outcome']['metrics']['focus_preserved']=False
    assert verify_daily_trace(MANIFEST,trace)['mechanics_met']
    trace=minimal_trace();trace['outcome']['metrics']['model_calls']=2
    with pytest.raises(StorageError):verify_daily_trace(MANIFEST,trace)
    trace=minimal_trace();trace['effects']['unauthorized_write']=1
    assert not verify_daily_trace(MANIFEST,trace)['mechanics_met']
    trace=minimal_trace();trace['outcome']['succeeded']=True
    with pytest.raises(StorageError):verify_daily_trace(MANIFEST,trace)


def test_suite_cannot_accept_missing_or_duplicate_cases():
    trace=minimal_trace()
    for traces in ([],[trace]*20):
        with pytest.raises(StorageError):verify_daily_trace_suite(MANIFEST,traces)


def test_public_projection_withholds_undeclared_assistant_and_rejects_secret_input():
    case=MANIFEST['cases'][0];sample=minimal_trace()
    kwargs=dict(objects=sample['objects'],status='ok',metrics=sample['outcome']['metrics'],effects=sample['effects'],duration_ms=1,
        tool_results=sample['tool_results'],model_observations=sample['model_observations'],turn_bindings=sample['turn_bindings'])
    trace=make_daily_trace(MANIFEST,case,turns=[{'role':'user','text':case['turns'][0]},{'role':'assistant','text':'Undeclared private provider content.'}],**kwargs)
    assert trace['visible_turns'][1]['text'] is None and 'private provider' not in str(trace)
    with pytest.raises(StorageError):make_daily_trace(MANIFEST,case,turns=[{'role':'user','text':'sk-'+('x'*24)}],**kwargs)



@pytest.mark.parametrize('case',MANIFEST['cases'],ids=lambda case:case['case_id'])
def test_daily_native_case(case,pai,tmp_path):
    trace=run_daily_fixture(case,pai,MANIFEST)
    result=verify_daily_trace(MANIFEST,trace)
    assert result['mechanics_met'],trace['outcome']
    assert not result['provider_execution'] and result['quality_score'] is None
    assert trace['duration_ms']>=0 and trace['cost_microdollars'] is None
    import json
    (tmp_path/(case['case_id']+'.json')).write_text(json.dumps(trace,ensure_ascii=False,indent=2)+'\n')


@pytest.mark.parametrize('change',['source_ref','source_digest','version','tool','tool_status','model_identity','model_input','result_input'])
def test_real_trace_rejects_unrelated_receipt_relationships(change):
    manifest=MANIFEST
    trace=relation_fixture(6)
    if change=='source_ref':trace['objects'][0]['ref_digest']='a'*64
    if change=='source_digest':trace['objects'][0]['digest']='b'*64
    if change=='version':trace['objects'][0]['version']=999
    if change=='tool':trace['tool_results'][0]={'tool':'action.dispatch','status':'denied','calls':0}
    if change=='tool_status':trace['tool_results'][0]['status']='denied'
    if change=='model_identity':trace['model_observations'][0]['observed_model']='unrelated_model'
    if change=='model_input':trace['model_observations'][0]['input_digest']='c'*64
    if change=='result_input':
        if 'turn_bindings' in trace:trace['turn_bindings'][0]['input_sha256']='d'*64
        else:trace['objects'][0]['ref_digest']='d'*64
    with pytest.raises(StorageError):verify_daily_trace(manifest,trace)


def test_capture_refuses_head_drift_before_publication(tmp_path,monkeypatch):
    import importlib.util
    from tests import pai_runtime_fixtures,daily_eval_fixtures
    spec=importlib.util.spec_from_file_location('daily_capture',Path('tools/run_daily_eval.py'))
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    counter={'head':0}
    def check_output(args,**kwargs):
        if args[1]=='rev-parse':
            counter['head']+=1
            return ('a'*40 if counter['head']==1 else 'b'*40)+'\n'
        return b''
    from types import SimpleNamespace
    monkeypatch.setattr(runner.subprocess,'check_output',check_output)
    monkeypatch.setattr(runner.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=0))
    def fixture(path):yield object()
    monkeypatch.setattr(pai_runtime_fixtures,'pai',SimpleNamespace(__wrapped__=fixture))
    monkeypatch.setattr(daily_eval_fixtures,'run_daily_fixture',lambda *args:None)
    output=tmp_path/'should-not-publish.json'
    assert runner.main(['--output',str(output)])==1
    assert not output.exists()
