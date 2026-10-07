"""Deferred acceptance: real HTTP, composition, ingress and twenty turns."""
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
import json
import pytest
from tests.pai_runtime_fixtures import pai

from prm.capabilities import CapabilityGrant,ProviderPolicy
from prm.storage.postgres import migrate
from prm.storage.testing import PostgresSandbox
from prm.storage.policy import install_policy,DurableCapabilityRegistry
from prm.storage.conversations import install_conversations
from prm.storage.jobs import install_jobs
from prm.runtime.composition import AssistantRuntime
from prm.runtime.model import ModelEndpoint


@pytest.fixture
def runtime():
    requests=[]
    class Provider(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));requests.append(body)
            value={'model':'fixture_model','choices':[{'finish_reason':'stop','message':{'content':'Синтетическое объяснение с достаточным контекстом.'}}],
                   'usage':{'prompt_tokens':40,'completion_tokens':12}}
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(value).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Provider);thread=Thread(target=server.serve_forever);thread.start()
    try:
        with PostgresSandbox() as pg:
            migrate(pg.migrator,expected_version=0);install_policy(pg.migrator);install_conversations(pg.migrator);install_jobs(pg.migrator)
            from prm.briefs import brief_owner_ref_from_authenticated_private_tuple
            owner=brief_owner_ref_from_authenticated_private_tuple('42','42','42');refs=('request_chat','job_chat','day_chat','month_chat')
            registry=DurableCapabilityRegistry(pg.app,budget_refs=refs,job_budget=True);now=datetime.now(timezone.utc)
            for kind,ref in zip(('request','job','day','month'),refs):
                registry.configure_window(owner=owner,ref=ref,kind=kind,capacity=1000,starts=now-timedelta(days=1),ends=now+timedelta(days=1))
            root=AssistantRuntime(target=pg.app,settings=SimpleNamespace(db_path=':memory:'),owner_ref=owner,owner_chat_id='42',registry=registry,
                model_endpoint=ModelEndpoint('provider_openai','connection_fixture',f'http://127.0.0.1:{server.server_port}/chat/completions','fixture_model','',synthetic_http=True),
                model_upper_bound=1,history_retention_seconds=3600)
            yield root,requests,now
    finally:server.shutdown();thread.join(timeout=5);server.server_close()


def grant(root,now,*,history=False):
    root.registry.register_grant(CapabilityGrant('grant_history' if history else 'grant_text',root.owner_ref,'connection_fixture',
        'model.context_egress' if history else 'model.generate',('resource_dialogue',),('model_egress',),
        ('model_generated',) if history else ('user_provided',),'dialogue.history' if history else 'answer.request',
        ProviderPolicy(('provider_openai',),maximum_request_count=1000),now-timedelta(days=1),now+timedelta(days=1),1))


def turn(root,index,text):
    incoming={'update_id':index,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':text}}
    ack=root.ingress.receive(incoming);ref=root.worker().run_once()
    return root.queue.store.get(root.owner_ref,'result',ref).payload


def test_twenty_turns_use_real_http_and_scoped_history(runtime):
    root,requests,now=runtime;grant(root,now);grant(root,now,history=True)
    for index in range(20):assert turn(root,index,'/chat объясни идею '+str(index))['status']=='ok'
    assert len(requests)==20
    assert any(message['role']=='assistant' for message in requests[-1]['messages'])
    assert len(requests[-1]['messages'])<=6
    count=len(requests)
    assert turn(root,20,'коротко')['status']=='ok'
    assert turn(root,21,'да')['status']=='confirmation_unavailable'
    assert len(requests)==count
    turn(root,22,'/new')
    turn(root,23,'/chat привет')
    assert not any(message['role']=='assistant' for message in requests[-1]['messages'])


def test_no_grants_no_http_and_history_scope_is_separate(runtime):
    root,requests,now=runtime
    assert turn(root,1,'/chat привет')['status']=='provider_egress_required'
    assert not requests
    grant(root,now)
    assert turn(root,2,'/chat объясни текст')['status']=='ok'
    assert turn(root,3,'/chat подробнее')['status']=='ok'
    assert not any(message['role']=='assistant' for message in requests[-1]['messages'])
    root.registry.revoke_grant('grant_text',owner_ref=root.owner_ref)
    count=len(requests);turn(root,4,'/chat ещё один запрос');assert len(requests)==count


def test_shortening_private_connector_response_keeps_its_origin(pai):
    from tests.pai_runtime_fixtures import request
    root=pai.root
    root.services['mail']=lambda *args:{'status':'ok','text':'Synthetic selected message subject and additional details.','source_data_class':'private_connector_content'}
    _,original=request(pai,9100,'/mail')
    _,shortened=request(pai,9101,'короче')
    assert original['data_class']=='private_connector_content'
    assert shortened['data_classes']==['private_connector_content']
    assert not root.conversations.history_for_model('42')


def test_unknown_model_call_has_logical_fence_across_fresh_reservations(pai):
    from dataclasses import replace
    from tests.pai_runtime_fixtures import allow
    from prm.capabilities import AuthorizationRequest
    from prm.runtime.model_attempts import ModelAttemptAlreadyRecorded
    from llm.client import LLMOutcomeUnknown
    root=pai.root
    allow(pai,'model.generate','resource_dialogue','user_provided','answer.request')
    def client(operation):
        scope=AuthorizationRequest(owner_ref=root.owner_ref,connection_ref='connection_fixture',capability='model.generate',resource_ref='resource_dialogue',
            operation='model_egress',data_class='user_provided',provider_ref='provider_openai',purpose='answer.request',operation_ref=operation)
        decision=root.registry.authorize_and_reserve(scope,upper_bound=1)
        return root.scoped_client(root.model_endpoint,groups=((decision,),),task_ref='logical_unknown_fixture',attempt_ref=operation),decision
    first,decision=client('unknown_model_first')
    kwargs={'prompt':'Synthetic ACK-loss question.','system':'Answer current synthetic question.','max_tokens':80,'category':'chat',
        'authorization':decision,'data_class':'user_provided','owner_ref':root.owner_ref,'connection_ref':'connection_fixture','resource_ref':'resource_dialogue'}
    with pytest.raises(LLMOutcomeUnknown) as failed:first.complete_with_receipt(**kwargs)
    assert failed.value.operation_refs==('unknown_model_first',) and not failed.value.retry_allowed
    second,new_decision=client('unknown_model_fresh_reservation')
    try:
        with pytest.raises(ModelAttemptAlreadyRecorded):second.complete_with_receipt(**dict(kwargs,authorization=new_decision))
        with pytest.raises(ModelAttemptAlreadyRecorded):first.complete_with_receipt(**kwargs)
        assert len([row for row in pai.requests if row[0]=='model'])==1
    finally:new_decision.reservation.abandon_before_transport()


def test_local_payload_validation_creates_no_model_fence_and_can_be_corrected(pai):
    from tests.pai_runtime_fixtures import allow
    from prm.capabilities import AuthorizationRequest
    from prm.storage.postgres import StorageError
    root=pai.root
    allow(pai,'model.generate','resource_dialogue','user_provided','answer.request')
    scope=AuthorizationRequest(owner_ref=root.owner_ref,connection_ref='connection_fixture',capability='model.generate',resource_ref='resource_dialogue',
        operation='model_egress',data_class='user_provided',provider_ref='provider_openai',purpose='answer.request',operation_ref='local_validation_fixture')
    decision=root.registry.authorize_and_reserve(scope,upper_bound=1)
    kwargs={'prompt':'Synthetic valid question','system':'Answer this question.','max_tokens':80,'category':'chat','authorization':decision,
        'data_class':'user_provided','owner_ref':root.owner_ref,'connection_ref':'connection_fixture','resource_ref':'resource_dialogue'}
    bad=root.scoped_client(root.model_endpoint,groups=((decision,),),task_ref='local_validation_task',attempt_ref='local_validation_fixture',history=({'role':'assistant','content':{}},))
    with pytest.raises(StorageError,match='invalid bounded history'):bad.complete_with_receipt(**kwargs)
    with root.queue.store.transaction() as tx:
        count=tx.conn.execute("SELECT count(*) AS n FROM pa_runtime.object_heads WHERE owner=%s AND object_id LIKE 'model_attempt_%%'",(root.owner_ref,)).fetchone()['n']
    assert count==0 and not pai.requests
    current=next(row for row in root.registry.snapshot(root.owner_ref)['operations'] if row['ref']=='local_validation_fixture')
    assert current['state']=='reserved'
    fixed=root.scoped_client(root.model_endpoint,groups=((decision,),),task_ref='local_validation_task',attempt_ref='local_validation_fixture')
    assert fixed.complete_with_receipt(**kwargs).delivery_outcome=='accepted'
    assert len([row for row in pai.requests if row[0]=='model'])==1
