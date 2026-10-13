"""Matched synthetic precision/recall and independent partial admission."""
import json,hashlib
from pathlib import Path
import pytest
from prm.research_blocks import assess_blocks,fact_proof
from prm.runtime.research_answer import accepted_answer,assessed_answer

URL='https://example.test/alpha'
SPAN='Service Alpha reduced latency to 20 milliseconds.'
EVIDENCE=[{'source_url':URL,'support_span':SPAN}]

def packet(*rows):return json.dumps({'schema_version':1,'blocks':rows},ensure_ascii=False)
def fact(id='f1',**changes):return {'id':id,'kind':'fact','text':SPAN,'quote':SPAN,'source_url':URL,**changes}

def test_matched_frozen_facts_preserve_numbers_entities_negation_urls_and_translation():
    path=Path('evals/synthesis/daily-20261013.json')
    assert hashlib.sha256(path.read_bytes()).hexdigest()=='ffc1171781c9cfa3515f39d9e8c30c0efa25f45db7c80fb20873e05813979041'
    for case in json.loads(path.read_text())['cases']:
        evidence=[{'source_url':URL,'support_span':case['quote']}]
        assert bool(fact_proof(case['text'],case['quote'],case['source_url'],evidence))==case['expected_supported'],case['id']

def test_one_bad_claim_preserves_supported_block_and_rejects_dependent_advice():
    bad=fact('f2',text='Service Beta reduced latency to 99 milliseconds.')
    advice={'id':'r1','kind':'recommendation','premises':['f2'],'goal':'latency','conditions':['f2'],'action':'run_local_experiment'}
    outcome=assess_blocks(packet(fact(),bad,advice),EVIDENCE,question='Investigate latency')
    assert outcome['status']=='partial_supported' and [b['id'] for b in outcome['blocks']]==['f1']
    assert len(outcome['rejected_blocks'])==2 and 'Beta' not in outcome['text'] and '99' not in outcome['text']

def test_inference_advice_require_supported_premise_and_current_requested_goal():
    inference={'id':'i1','kind':'inference','premises':['f1'],'relation':'needs_measurement','uncertainty':'requires_measurement'}
    advice={'id':'r1','kind':'recommendation','premises':['f1'],'goal':'latency','conditions':['f1'],'action':'run_local_experiment'}
    outcome=assess_blocks(packet(fact(),inference,advice),EVIDENCE,question='Investigate latency')
    assert [b['kind'] for b in outcome['blocks']]==['fact','inference','recommendation']
    assert 'результат' in outcome['text'] and outcome['blocks'][2]['uncertainty']=='requires_measurement'
    outcome=assess_blocks(packet(fact(),dict(advice,goal='unrequested project')),EVIDENCE,question='Investigate latency')
    assert len(outcome['blocks'])==1 and outcome['rejected_blocks']

def test_contradictory_numbers_remain_separate_not_one_confident_conclusion():
    other='Service Alpha reduced latency to 30 milliseconds.';url='https://example.test/beta'
    outcome=assess_blocks(packet(fact(),fact('f2',text=other,quote=other,source_url=url)),EVIDENCE+[{'source_url':url,'support_span':other}])
    assert len(outcome['blocks'])==2 and outcome['conflicts']==[['f1','f2']] and outcome['status']=='partial_supported'

@pytest.mark.parametrize('bad',[{'premises':['missing']},{'relation':[]},{'uncertainty':[]},{'extra':'send'}])
def test_malformed_derived_block_cannot_discard_good_fact_or_create_authority(bad):
    row={'id':'i1','kind':'inference','premises':['f1'],'relation':'hypothesis','uncertainty':'preliminary',**bad}
    value=assess_blocks(packet(fact(),row),EVIDENCE)
    assert len(value['blocks'])==1 and value['rejected_blocks']

def test_plaintext_legacy_cannot_bypass_new_ordered_fact_guard():
    assert assessed_answer(SPAN.rstrip('. ')+' ('+URL+').',EVIDENCE,question='latency') is not None
    assert assessed_answer('Service latency reduced Alpha to 20 milliseconds ('+URL+').',EVIDENCE,question='latency') is None
    assert assess_blocks('{"schema_version":1,"schema_version":1,"blocks":[]}',EVIDENCE) is None

@pytest.mark.parametrize('span',['Service Alpha may reduce latency to 20 milliseconds.',"Service Alpha can't reduce latency to 20 milliseconds.",'Service Alpha could reduce latency to 20 milliseconds if tested.'])
def test_extracting_a_phrase_cannot_drop_uncertainty_conditional_or_contracted_negation(span):
    evidence=[{'source_url':URL,'support_span':span}]
    assert fact_proof('Service Alpha reduce latency to 20 milliseconds.',span,URL,evidence) is None

@pytest.mark.parametrize('span,quote,claim',[
    ('Service Alpha did not reduce latency to 20 milliseconds.','reduce latency to 20 milliseconds','reduce latency to 20 milliseconds'),
    ('Service Alpha may reduce latency to 20 milliseconds.','reduce latency to 20 milliseconds','reduce latency to 20 milliseconds'),
    ('Service Alpha works with Service Beta to reduce latency to 20 milliseconds.','Service Beta to reduce latency to 20 milliseconds','Service Beta reduce latency to 20 milliseconds'),
])
def test_quote_crop_cannot_hide_polarity_modality_or_original_actor(span,quote,claim):
    assert fact_proof(claim,quote,URL,[{'source_url':URL,'support_span':span}]) is None

from tests.pai_runtime_fixtures import pai,allow

def test_actual_loopback_block_response_preserves_supported_subset_in_durable_worker_and_archive_transport(pai):
    from dataclasses import replace
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from threading import Thread
    import sqlite3
    from tests.test_archive_search import _make_connection,_insert_post
    from prm.runtime.research import DurableResearchWorker,LocalArchiveReader
    from prm.runtime.archive import RuntimeArchiveTransport
    from prm.synthesis import synthesize_archive_response
    from tests.test_prm_synthesis import _archive_payload,_archive_evidence
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));calls.append(body)
            selected=[]
            for message in body['messages']:
                content=message.get('content','')
                for prefix in ('Untrusted verified reads: ','Untrusted cited archive evidence: '):
                    if isinstance(content,str) and content.startswith(prefix):selected=json.loads(content[len(prefix):])
            source=selected[0];span=source.get('support_span',source.get('text'));url=source.get('source_url',source.get('source_ref'))
            response=packet(fact(text=span,quote=span,source_url=url),fact('f2',text='Service Beta invented number 99.',quote=span,source_url=url))
            raw=json.dumps({'model':'fixture_model','choices':[{'finish_reason':'stop','message':{'content':response}}],
                'usage':{'prompt_tokens':40,'completion_tokens':20}}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever);thread.start()
    root=pai.root;root.model_endpoint=replace(root.model_endpoint,endpoint=f'http://127.0.0.1:{server.server_port}/chat/completions')
    try:
        conn=_make_connection();_insert_post(conn,post_id=1,content=SPAN);conn.commit();path=pai.path/'blocks.sqlite'
        with sqlite3.connect(path) as saved:conn.backup(saved)
        conn.close();root.deep_archive_reader=LocalArchiveReader(path,root=root)
        allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
        allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request')
        allow(pai,'model.context_egress',root.archive_resource_ref,'private_archive','research.synthesis.archive')
        worker=DurableResearchWorker(root);worker.enqueue({'schema_version':1,'question':'Investigate latency','steps':[{'source':'archive','query':'latency'}],
            'max_tool_calls':1,'deadline_seconds':60},idempotency_key='native_blocks')
        ref=worker.run_once();result=root.queue.store.get(root.owner_ref,'result',ref).payload
        assert result['status']=='partial_supported' and [b['id'] for b in result['answer_payload']['blocks']]==['f1']
        assert '99' not in result['text'] and len(calls)==1 and worker.run_once() is None
        allow(pai,'model.context_egress',root.archive_resource_ref,'private_archive','answer.context')
        outcome=synthesize_archive_response(_archive_payload(),question='agent evals',evidence_items=_archive_evidence(),access=None,
            transport=RuntimeArchiveTransport(root,request_ref='native_archive_blocks',guard=lambda:None,context_resource_ref=root.archive_resource_ref))
        assert outcome.status=='generated_partially_verified' and outcome.block_assessment['rejected_blocks']
        assert len(calls)==2 and '99' not in outcome.text and not pai.requests
    finally:server.shutdown();thread.join(timeout=5);server.server_close()
