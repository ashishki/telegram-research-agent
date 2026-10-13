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


def minimal_trace():
    case=MANIFEST['cases'][0]
    return make_daily_trace(MANIFEST,case,turns=[{'role':'user','text':case['turns'][0]},
        {'role':'assistant','text':MANIFEST['public_visible_texts'][0]}],
        objects=[{'kind':'result','ref_digest':'a'*64,'version':1,'digest':'b'*64}],
        status='ok',metrics={'model_calls':1},effects={name:0 for name in case['must_not_effects']},duration_ms=1,tool_results=[{'tool':'model.generate','status':'ok','calls':1}],model_observations=[{'requested_model':'fixture_model','observed_model':'fixture_model','finish_reason':'stop','protocol':'chat_completions','usage':{'input':40,'output':12,'cached_input':10,'reasoning':4,'cache_write':None,'semantics':'openai_chat_output_includes_reasoning'},'input_digest':'c'*64,'duration_ms':1,'provider_outcome':'accepted'}])


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
    assert not verify_daily_trace(MANIFEST,trace)['mechanics_met']
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
    case=MANIFEST['cases'][0]
    kwargs=dict(objects=[{'kind':'result','ref_digest':'a'*64,'version':1,'digest':'b'*64}],status='ok',metrics={'model_calls':0},effects={n:0 for n in case['must_not_effects']},duration_ms=1,tool_results=[{'tool':'model.generate','status':'ok','calls':0}])
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
