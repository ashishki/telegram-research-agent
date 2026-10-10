from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import opencode_pool_review as pool

SCHEMA = {'type':'object','required':['summary','verdict','findings'],
          'properties':{'summary':{'type':'string'},'verdict':{'enum':['PASS','ADVISORY','STOP']},
                        'findings':{'type':'array'}}}


@pytest.mark.parametrize('change', [
    {'model':'glm-5.3'}, {'base_url':'https://example.test/v1'}, {'timeout':True},
    {'timeout':7201}, {'max_output_tokens':393217}, {'max_output_tokens':True},
    {'prompt':'x' * 1000001}, {'session_id':'bad\r\nheader'},
])
def test_invalid_scope_or_bounds_denied_before_http(monkeypatch, change):
    def forbidden(*args, **kwargs):
        pytest.fail('unapproved request reached network')
    monkeypatch.setattr(pool, 'urlopen', forbidden)
    kwargs=dict(api_key='synthetic',model=pool.MODEL,prompt='public JSON packet',session_id='fixture')
    kwargs.update(change)
    with pytest.raises(ValueError):pool.call_pool_model(**kwargs)


def test_selected_model_uses_json_max_effort_and_stable_session_without_retry(monkeypatch):
    calls=[]
    def rejected(request, **kwargs):
        calls.append(request)
        raise TimeoutError('synthetic unknown outcome')
    monkeypatch.setattr(pool, 'urlopen', rejected)
    with pytest.raises(TimeoutError):pool.call_pool_model(api_key='synthetic',model=pool.MODEL,
        prompt='public JSON packet',session_id='fixture-session')
    assert len(calls)==1
    body=json.loads(calls[0].data)
    assert body['reasoning_effort']=='max' and body['response_format']=={'type':'json_object'}
    assert body['max_tokens']==393216 and not body.get('tools')
    assert calls[0].get_header('X-opencode-session')=='fixture-session'


@pytest.mark.parametrize('change', ['model','length','false_pass','false_stop','placeholder'])
def test_incomplete_mismatched_or_contradictory_review_cannot_close_p1(change):
    report={'summary':'The supplied public-code repair contains no observed critical defect; live accounts and operator acceptance remain unverified.', 'verdict':'PASS','findings':[]}
    payload={'model':pool.MODEL,'choices':[{'finish_reason':'stop','message':{}}]}
    if change=='model':payload['model']='glm-5.3'
    elif change=='length':payload['choices'][0]['finish_reason']='length'
    elif change=='false_pass':report['findings']=[{'severity':'P1'}]
    elif change=='false_stop':report['verdict']='STOP'
    else:report['summary']='See summary field.'
    payload['choices'][0]['message']['content']=json.dumps(report)
    with pytest.raises(ValueError):pool.parse_pool_review(payload,SCHEMA)


def test_real_stop_is_preserved_and_separate_from_governed_glm_route():
    import mimo_code_review
    report={'summary':'A concrete critical deletion regression exists in the supplied public code; this review cannot grant human or release acceptance.',
            'verdict':'STOP','findings':[{'severity':'P1'}]}
    payload={'model':pool.MODEL,'choices':[{'finish_reason':'stop','message':{'content':json.dumps(report)}}]}
    assert pool.parse_pool_review(payload,SCHEMA)['verdict']=='STOP'
    assert mimo_code_review.CURRENT_REVIEW_MODEL=='glm-5.3'
    assert pool.MODEL not in mimo_code_review.SUPPORTED_REVIEW_MODELS
