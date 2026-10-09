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
            if body['messages'][-1]['content']=='Synthetic invalid usage':value['usage']['prompt_tokens_details']={'cached_tokens':[]}
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


def test_chat_fallback_provider_without_data_class_grant_is_not_called(pai):
    from dataclasses import replace
    from prm.capabilities import AuthorizationRequest,CapabilityDenied
    from tests.pai_runtime_fixtures import allow,request
    root=pai.root;alternate=replace(root.model_endpoint,provider_ref='provider_mimo')
    allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request',provider='provider_mimo')
    allow(pai,'model.context_egress',root.archive_resource_ref,'private_archive','answer.context')
    def reserve(provider,capability,resource,data_class,purpose,operation):
        return root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref='connection_fixture',
            provider_ref=provider,capability=capability,resource_ref=resource,operation='model_egress',data_class=data_class,
            purpose=purpose,operation_ref=operation),upper_bound=1)
    text=reserve('provider_mimo','model.generate',root.model_resource_ref,'user_provided','answer.request','fallback_text_scope')
    context=reserve('provider_openai','model.context_egress',root.archive_resource_ref,'private_archive','answer.context','fallback_private_scope')
    assert text.allowed and context.allowed
    private='Synthetic private archive excerpt for a provider with no private grant.'
    count=len(pai.requests)
    client=root.scoped_client(alternate,groups=((text,),(context,)),task_ref='fallback_privacy',attempt_ref='fallback_privacy',
        history=({'role':'user','content':private},))
    try:
        with pytest.raises(CapabilityDenied,match='share owner, connection, provider'):
            client.complete_with_receipt(prompt='Summarize the selected source',system='Use the supplied source.',max_tokens=100,
                category='chat',authorization=text,data_class='user_provided',owner_ref=root.owner_ref,
                connection_ref='connection_fixture',resource_ref=root.model_resource_ref)
        assert len(pai.requests)==count
    finally:text.reservation.abandon_before_transport();context.reservation.abandon_before_transport()
    state=root.conversations.record_response('42',text=private,topic='',item_texts=(private,))
    root.conversations.record_origin(state.object_refs[0].response_ref,('private_archive',))
    root.model_endpoint=alternate
    assert request(pai,8810,'/chat Explain a new generic topic')[1]['status']=='ok'
    sent=[row for row in pai.requests[count:] if row[0]=='model']
    assert len(sent)==1 and private not in json.dumps(sent[0][2])


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
        with pytest.raises(ModelAttemptAlreadyRecorded) as replay:second.complete_with_receipt(**dict(kwargs,authorization=new_decision,prompt='Divergent synthetic body'))
        assert replay.value.input_changed and replay.value.recorded_digest!=replay.value.requested_digest
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
    fixed=root.scoped_client(root.model_endpoint,groups=((decision,),),task_ref='local_validation_task',attempt_ref='local_validation_fixture')
    for limit in (0,True,16001):
        with pytest.raises(StorageError,match='bounded model output limit'):fixed.complete_with_receipt(**dict(kwargs,max_tokens=limit))
    with root.queue.store.transaction() as tx:
        count=tx.conn.execute("SELECT count(*) AS n FROM pa_runtime.object_heads WHERE owner=%s AND object_id LIKE 'model_attempt_%%'",(root.owner_ref,)).fetchone()['n']
    assert count==0 and not pai.requests
    current=next(row for row in root.registry.snapshot(root.owner_ref)['operations'] if row['ref']=='local_validation_fixture')
    assert current['state']=='reserved'
    assert fixed.complete_with_receipt(**kwargs).delivery_outcome=='accepted'
    assert len([row for row in pai.requests if row[0]=='model'])==1


def test_separate_explicit_chat_requests_may_repeat_content_with_separate_accounting(runtime):
    root,requests,now=runtime;grant(root,now)
    for index in (71,72):assert turn(root,index,'/chat тот же явный вопрос')['status']=='ok'
    assert len(requests)==2
    operations=root.registry.snapshot(root.owner_ref)['operations']
    assert len({row['ref'] for row in operations if row['state']=='accepted'})==2


def test_cancel_after_model_response_preserves_charge_and_prevents_result_completion(pai,monkeypatch):
    from tests.pai_runtime_fixtures import allow
    allow(pai,'model.generate','resource_dialogue','user_provided','answer.request')
    ack=pai.root.ingress.receive({'update_id':9301,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'/chat Synthetic cancellation question'}})
    original=pai.root.registry.execute_reserved_groups
    def cancel_after_response(*args,**kwargs):
        result=original(*args,**kwargs)
        assert pai.root.queue.cancel(owner=pai.root.owner_ref,job_id=ack.job_id)
        return result
    monkeypatch.setattr(pai.root.registry,'execute_reserved_groups',cancel_after_response)
    from prm.storage.postgres import StateConflict
    with pytest.raises(StateConflict):pai.root.worker().run_once()
    state=pai.root.queue.status(owner=pai.root.owner_ref,job_id=ack.job_id)
    assert state['status']=='cancelled' and not state['result_ref']
    assert len([row for row in pai.requests if row[0]=='model'])==1
    assert all(w['consumed']==1 for w in pai.root.registry.snapshot(pai.root.owner_ref)['windows'])


@pytest.mark.parametrize('mode',['invalid','accepted','accepted_settlement_loss'])
def test_known_invalid_model_response_retains_typed_no_retry_even_if_accounting_fails(runtime,monkeypatch,mode):
    from prm.capabilities import AuthorizationRequest
    from prm.runtime.model_errors import ModelResponseInvalid
    from prm.runtime.model_attempts import ModelAttemptAlreadyRecorded
    from prm.storage.postgres import StorageError
    root,requests,now=runtime;grant(root,now)
    def client(operation):
        decision=root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref='connection_fixture',capability='model.generate',
            resource_ref='resource_dialogue',operation='model_egress',data_class='user_provided',provider_ref='provider_openai',purpose='answer.request',operation_ref=operation),upper_bound=1)
        return root.scoped_client(root.model_endpoint,groups=((decision,),),task_ref='invalid_reply_task',attempt_ref=operation),decision
    current,decision=client('invalid_reply_attempt')
    def failed_observer(*args):raise StorageError('synthetic accounting failure')
    current.usage_observer=failed_observer
    kwargs={'prompt':'Synthetic invalid usage' if mode=='invalid' else 'Synthetic accepted usage','system':'Answer this question.','max_tokens':80,'category':'chat','authorization':decision,
        'data_class':'user_provided','owner_ref':root.owner_ref,'connection_ref':'connection_fixture','resource_ref':'resource_dialogue'}
    if mode=='accepted_settlement_loss':
        from prm.storage.policy import ScopeTransportUnknown
        original=root.registry.execute_reserved_groups
        def failed_settlement(*args,**kwargs):
            original(*args,**kwargs);raise ScopeTransportUnknown(('invalid_reply_attempt',))
        monkeypatch.setattr(root.registry,'execute_reserved_groups',failed_settlement)
    if mode=='invalid':
        with pytest.raises(ModelResponseInvalid) as failure:current.complete_with_receipt(**kwargs)
        observed=failure.value
    else:
        observed=current.complete_with_receipt(**kwargs)
        assert observed.delivery_outcome=='accepted' and observed.text and not observed.usage_recorded and observed.estimated_cost_usd is None
        durable=root.registry.store.get(root.owner_ref,'conversation',observed.attempt_ref)
        assert durable.payload['accounting_status']=='unconfirmed' and durable.payload['provider_outcome']=='accepted'
        assert durable.payload['estimated_cost_usd'] is None and 'text' not in durable.payload
    assert not observed.retry_allowed and observed.operation_refs==('invalid_reply_attempt',)
    assert observed.accounting_status=='unconfirmed'
    replay,reserved=client('invalid_reply_fresh_reservation')
    try:
        with pytest.raises(ModelAttemptAlreadyRecorded):replay.complete_with_receipt(**dict(kwargs,authorization=reserved))
    finally:reserved.reservation.abandon_before_transport()
    assert len(requests)==1


def test_model_preparation_unknown_is_distinct_from_provider_unknown(runtime,monkeypatch):
    from prm.capabilities import AuthorizationRequest
    from prm.storage.policy import ScopePreparationUnknown
    root,requests,now=runtime;grant(root,now)
    decision=root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref='connection_fixture',capability='model.generate',
        resource_ref='resource_dialogue',operation='model_egress',data_class='user_provided',provider_ref='provider_openai',purpose='answer.request',operation_ref='preparation_unknown_model'),upper_bound=1)
    client=root.scoped_client(root.model_endpoint,groups=((decision,),),task_ref='preparation_unknown_task',attempt_ref=decision.operation_ref)
    def unknown_prepare(*args,**kwargs):raise ScopePreparationUnknown((decision.operation_ref,))
    monkeypatch.setattr(root.registry,'_commit_durable_transport',unknown_prepare)
    with pytest.raises(ScopePreparationUnknown) as error:client.complete_with_receipt(prompt='Synthetic preflight',system='Answer.',max_tokens=80,category='chat',authorization=decision,
        data_class='user_provided',owner_ref=root.owner_ref,connection_ref='connection_fixture',resource_ref='resource_dialogue')
    assert not error.value.external_call_attempted and not error.value.retry_allowed and error.value.attempt_ref
    assert not requests


@pytest.mark.parametrize('marker_failure',[False,True])
def test_accepted_unconfirmed_accounting_survives_application_result_storage(pai,monkeypatch,marker_failure):
    from prm.runtime.cost_cache import CostCacheRuntime
    from tests.pai_runtime_fixtures import allow,request
    allow(pai,'model.generate','resource_dialogue','user_provided','answer.request')
    def failed(*args,**kwargs):raise OSError('synthetic accounting failure')
    monkeypatch.setattr(CostCacheRuntime,'record',failed)
    if marker_failure:
        from prm.runtime import model_attempts
        monkeypatch.setattr(model_attempts,'record_accounting_unconfirmed',failed)
    ack,result=request(pai,9401,'/chat Synthetic accepted response with accounting failure')
    assert result['status']=='ok' and result['text'] and result['payload']['accounting_status']=='unconfirmed'
    assert len([row for row in pai.requests if row[0]=='model'])==1
