"""Coherent answers keep strict source publication and durable deletion fences."""
import json
from datetime import timedelta
import pytest
from tests.pai_runtime_fixtures import pai,allow
from prm.runtime.research_answer import accepted_answer,coverage_text
from prm.runtime.research import DurableResearchWorker

EVIDENCE=[{'evidence_id':'synthetic_1','source_url':'https://example.test/aurora/1','support_span':'Аврора: тест normalize_email проверяет пробелы и нижний регистр.'},
          {'evidence_id':'synthetic_2','source_url':'https://example.test/aurora/2','support_span':'Аврора: тест slugify добавлен. Результат пока не измерен.'}]


def response(*rows):return json.dumps({'findings':list(rows)},ensure_ascii=False)
def finding(index=0,**changed):
    item=EVIDENCE[index]
    return {'text':item['support_span'],'source_url':item['source_url'],'quote':item['support_span'],**changed}


def test_structured_answer_publishes_only_source_supported_claims():
    result=accepted_answer(response(finding(),finding(1)),EVIDENCE)
    assert result is not None and 'normalize_email' in result[0] and 'не измерен' in result[0]
    assert all(item['source_url'] in result[0] for item in EVIDENCE)
    assert result[1]['verification_complete'] and result[1]['metrics']['unsupported_claim_rate']==0


@pytest.mark.parametrize('changed',[
    {'source_url':'https://attacker.example.test/forged'},
    {'quote':'Новая цитата отсутствует в выбранном источнике.'},
    {'text':'Аврора: тест normalize_email улучшил качество на 80%.'},
    {'text':'Аврора: тест normalize_email не проверяет пробелы и нижний регистр.'},
    {'text':'Бета: тест normalize_email проверяет пробелы и нижний регистр.'},
    {'text':'Аврора: тест normalize_email проверяет пробелы и нижний регистр. Оплата уже подтверждена.'},
])
def test_one_bad_finding_rejects_whole_generated_candidate(changed):
    assert accepted_answer(response(finding(1),finding(**changed)),EVIDENCE) is None


@pytest.mark.parametrize('value',['{}','{"findings":[]}','{"findings":[],"tools":["send_mail"]}','{"findings":not-json}',response({'text':'x'})])
def test_malformed_or_instruction_shaped_response_never_publishes(value):
    assert accepted_answer(value,EVIDENCE) is None


def test_coverage_distinguishes_bounded_results_unknowns_and_failed_sources():
    text=coverage_text([{'status':'gathered'},{'status':'source_unavailable'}],2,[EVIDENCE[0]['source_url']],['github: source_unavailable'],found_count=2)
    assert '1 из 2' in text and 'найдено материалов: 2' in text and 'процитировано: 1' in text
    assert 'не проверка всего архива' in text and 'неизвестным' in text and 'публичный репозиторий' in text


def prepare(pai):
    root=pai.root
    allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request')
    allow(pai,'model.context_egress',root.archive_resource_ref,'private_archive','research.synthesis.archive')
    worker=DurableResearchWorker(root)
    plan={'schema_version':1,'question':'Какие тесты добавлены в Авроре?','steps':[{'source':'archive','query':'Аврора'}],'max_tool_calls':1,'deadline_seconds':180}
    job=worker.enqueue(plan,idempotency_key='structured_polish_fixture')
    lease=root.queue.claim(owner=root.owner_ref,kinds=('compute.research',),lease_seconds=300)
    ref='research_step_'+job+'_0'
    completed=[{'ref':ref,'status':'gathered','source':'archive','tool_calls':1,'evidence':{'items':EVIDENCE}}]
    root.queue.store.put(root.owner_ref,'result',ref,completed[0],expected_version=0)
    return worker,plan,lease,completed


def test_durable_synthesis_accepts_structured_model_and_never_repeats(pai,monkeypatch):
    worker,plan,lease,completed=prepare(pai)
    # Exercise the actual scoped HTTP client; only the loopback reply content differs.
    from prm.runtime.model import ScopedModelClient
    original=ScopedModelClient.complete_with_receipt
    def complete(self,**kwargs):
        receipt=original(self,**kwargs)
        from dataclasses import replace
        return replace(receipt,text=response(finding(),finding(1)))
    monkeypatch.setattr(ScopedModelClient,'complete_with_receipt',complete)
    result=worker._synthesize(plan,completed,lease)
    assert result['status']=='synthesized_verified' and result['model_reply_observed']
    assert result['synthesis_outcome']=='verified' and result['found_count']==2
    assert len([r for r in pai.requests if r[0]=='model'])==1
    assert worker._synthesize(plan,completed,lease)==result
    assert len([r for r in pai.requests if r[0]=='model'])==1


@pytest.mark.parametrize('parent',['source','main'])
def test_deletion_removes_internal_synthesis_snapshot(pai,monkeypatch,parent):
    worker,plan,lease,completed=prepare(pai)
    result=worker._synthesize(plan,completed,lease)
    assert result['status']=='evidence_only' and result['synthesis_outcome']=='rejected_by_verifier'
    from prm.runtime.deletion import delete_derived_in
    ref=completed[0]['ref'] if parent=='source' else 'result_'+lease.job_id
    with pai.root.queue.store.transaction() as tx:delete_derived_in(tx,owner=pai.root.owner_ref,namespace='result',object_ref=ref)
    assert pai.root.queue.store.get(pai.root.owner_ref,'result','research_synthesis_'+lease.job_id) is None


def test_source_sentence_projection_does_not_change_number_or_negation_guards():
    item={'evidence_id':'numbers','source_url':'https://example.test/numbers','support_span':'Аврора: было 2 теста. Аврора: результат не измерен.'}
    wrong={'text':'Аврора: было 20 тестов.','source_url':item['source_url'],'quote':'Аврора: было 2 теста.'}
    assert accepted_answer(response(wrong),[item]) is None
    wrong={'text':'Аврора: результат измерен.','source_url':item['source_url'],'quote':'Аврора: результат не измерен.'}
    assert accepted_answer(response(wrong),[item]) is None
