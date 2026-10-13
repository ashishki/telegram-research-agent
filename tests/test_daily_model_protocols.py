"""Bounded protocol doubles; no personal model/key/account calls."""
from dataclasses import replace
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
import json
import pytest
from prm.runtime.model import ModelEndpoint
from prm.runtime.model_protocol import ChatCapabilities,ChatCompletionsTransport
from prm.runtime.model_errors import ModelProviderRejected,ModelResponseInvalid,ModelStreamInterrupted
from prm.storage.postgres import StorageError


@pytest.fixture
def http_model():
    state={'requests':[], 'mode':'ok', 'model':'snapshot_fixture'}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            raw=self.rfile.read(int(self.headers['Content-Length']))
            state['requests'].append((json.loads(raw),dict(self.headers)))
            mode=state['mode']
            if mode=='lost': self.close_connection=True; return
            if mode in {'403','429','500','redirect'}:
                self.send_response(302 if mode=='redirect' else int(mode))
                self.send_header('Location','/should-not-follow')
                self.send_header('Retry-After','17')
                self.end_headers(); self.wfile.write(b'secret_provider_error'); return
            streaming=json.loads(raw)['stream']
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream' if streaming else 'application/json')
            self.end_headers()
            usage={'prompt_tokens':40,'completion_tokens':12,'total_tokens':52,
                'prompt_tokens_details':{'cached_tokens':10},'completion_tokens_details':{'reasoning_tokens':4}}
            if mode=='bad_usage': usage['total_tokens']=999
            if streaming:
                base={'id':'stream_fixture','model':state['model']}
                chunks=[{**base,'choices':[{'index':0,'delta':{'role':'assistant','content':'Синтетический '},'finish_reason':None}]},
                    {**base,'choices':[{'index':0,'delta':{'content':'ответ.'},'finish_reason':'stop'}]}]
                if mode!='no_usage': chunks.append({**base,'choices':[],'usage':usage})
                if mode=='changed_model':chunks[1]['model']='other_model'
                wire=''.join('data: '+json.dumps(c,ensure_ascii=False)+'\r\n\r\n' for c in chunks)
                if mode!='no_done':wire+='data: [DONE]\r\n\r\n'
                self.wfile.write(wire.encode());return
            value={'model':state['model'],'choices':[{'index':0,'finish_reason':'length' if mode=='length' else 'stop','message':{'content':'Синтетический ответ.'}}],'usage':usage}
            wire=json.dumps(value).encode()
            if mode=='oversize':wire=b'x'*1048577
            if mode=='malformed':wire=b'{'
            self.wfile.write(wire)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever);thread.start()
    try:yield state,f'http://127.0.0.1:{server.server_port}/chat/completions'
    finally:server.shutdown();thread.join(5);server.server_close()


def transport(http_model,**capabilities):
    state,url=http_model
    endpoint=ModelEndpoint('provider_openai','connection_fixture',url,'alias_fixture','synthetic_header_canary',synthetic_http=True,
        capabilities=ChatCapabilities(accepted_models=('snapshot_fixture',),**capabilities))
    return ChatCompletionsTransport(endpoint)


def test_explicit_alias_token_parameter_and_observed_receipt(http_model):
    t=transport(http_model,token_parameter='max_tokens')
    result=t.send(t.encode([{'role':'user','content':'Synthetic'}],100),before_request=lambda:None)
    body,headers=http_model[0]['requests'][0]
    assert body['max_tokens']==100 and 'max_completion_tokens' not in body
    assert body['store'] is False and body['stream'] is False
    assert headers['User-Agent']=='telegram-research-agent/1.0'
    assert result.requested_model=='alias_fixture' and result.observed_model=='snapshot_fixture'
    assert result.finish_reason=='stop' and result.usage['reasoning']==4 and result.usage['output']==12
    assert 'synthetic_header_canary' not in repr(t.endpoint)


@pytest.mark.parametrize('mode',['bad_usage','malformed','oversize','length'])
def test_invalid_or_truncated_response_is_not_accepted(http_model,mode):
    http_model[0]['mode']=mode;t=transport(http_model)
    with pytest.raises(ModelResponseInvalid) as failure:t.send(t.encode([],100),before_request=lambda:None)
    assert not failure.value.retry_allowed and 'secret_provider_error' not in str(failure.value)
    assert len(http_model[0]['requests'])==1


@pytest.mark.parametrize('mode',[403,429])
def test_known_rejection_redacts_headers_body_and_never_retries(http_model,mode):
    http_model[0]['mode']=str(mode);t=transport(http_model)
    with pytest.raises(ModelProviderRejected) as failure:t.send(t.encode([],100),before_request=lambda:None)
    assert failure.value.status_code==mode and failure.value.retry_after==17
    assert 'secret' not in str(failure.value) and 'synthetic_header_canary' not in str(failure.value)
    assert len(http_model[0]['requests'])==1


def test_unknown_alias_is_rejected_without_prefix_matching(http_model):
    http_model[0]['model']='snapshot_fixture_unapproved';t=transport(http_model)
    with pytest.raises(ModelResponseInvalid):t.send(t.encode([],100),before_request=lambda:None)


def test_stream_complete_and_cancel_partial_no_final_result(http_model):
    t=transport(http_model,streaming=True);events=[]
    result=t.send(t.encode([],100,stream=True),before_request=lambda:None,on_event=events.append)
    assert result.text=='Синтетический ответ.' and result.usage['input']==40
    assert len(events)==2 and all(event.authority=='untrusted_partial' for event in events)
    events=[]
    with pytest.raises(ModelStreamInterrupted) as failure:
        t.send(t.encode([],100,stream=True),before_request=lambda:None,on_event=events.append,cancelled=lambda:bool(events))
    assert failure.value.partial_characters>0 and not failure.value.retry_allowed


@pytest.mark.parametrize('mode',['no_usage','no_done','changed_model'])
def test_stream_requires_done_usage_and_stable_identity(http_model,mode):
    http_model[0]['mode']=mode;t=transport(http_model,streaming=True)
    with pytest.raises((ModelStreamInterrupted,ModelResponseInvalid)):
        t.send(t.encode([],100,stream=True),before_request=lambda:None)


def test_unsupported_stream_or_parameter_fails_before_request(http_model):
    t=transport(http_model)
    with pytest.raises(StorageError):t.encode([],100,stream=True)
    with pytest.raises(StorageError):ChatCapabilities(token_parameter='max_output_tokens')
    assert not http_model[0]['requests']


def test_offline_descriptor_go_session_and_route_requirements():
    from prm.runtime.config import _model
    _model({'provider_ref':'provider_openai','connection_ref':'connection_fixture','model':'gpt-4o','endpoint':'http://127.0.0.1:1/chat/completions','synthetic_http':True,
        'capabilities':{'accepted_models':['gpt-4o-2024-08-06'],'streaming':True,'usage_semantics':'openai_chat_output_includes_reasoning'}})
    with pytest.raises(StorageError):ChatCapabilities(client_kind='opencode_go')
    cap=ChatCapabilities(client_kind='opencode_go',session_ref='session_synthetic',workload_ref='workload_synthetic',token_parameter='max_tokens')
    assert cap.headers()['x-opencode-session']=='session_synthetic'
    assert 'opencode' not in cap.headers()['User-Agent'].lower()
    with pytest.raises(StorageError):_model({'provider_ref':'provider_openai','connection_ref':'connection_fixture','model':'gpt-4o','endpoint':'https://api.example.test/chat/completions','token_env':'PAI_TEST','capabilities':{'protocol':'responses'}})

from tests.pai_runtime_fixtures import pai,allow
from prm.capabilities import AuthorizationRequest
from prm.runtime.model_attempts import ModelAttemptAlreadyRecorded
from llm.client import LLMOutcomeUnknown


@pytest.mark.parametrize('mode',['ok','403','429','lost','500','redirect','bad_usage','cancel'])
def test_scoped_runtime_receipt_accounting_and_reconstruction_fence(pai,http_model,mode):
    root=pai.root;state,url=http_model;state['mode']='ok' if mode=='cancel' else mode
    endpoint=ModelEndpoint('provider_openai','connection_fixture',url,'alias_fixture','',synthetic_http=True,
        capabilities=ChatCapabilities(accepted_models=('snapshot_fixture',),streaming=mode=='cancel',usage_semantics='openai_chat_output_includes_reasoning'))
    allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request')
    def client(operation):
        decision=root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref='connection_fixture',
            provider_ref='provider_openai',capability='model.generate',resource_ref=root.model_resource_ref,operation='model_egress',
            data_class='user_provided',purpose='answer.request',operation_ref=operation),upper_bound=1)
        return root.scoped_client(endpoint,groups=((decision,),),task_ref='daily_protocol_task',attempt_ref=operation),decision
    current,decision=client('daily_protocol_first')
    kwargs=dict(prompt='Synthetic protocol request.',system='Use only this request.',max_tokens=100,category='chat',authorization=decision,
        data_class='user_provided',owner_ref=root.owner_ref,connection_ref='connection_fixture',resource_ref=root.model_resource_ref)
    if mode=='ok':
        receipt=current.complete_with_receipt(**kwargs)
        assert receipt.model==receipt.observed_model=='snapshot_fixture' and receipt.requested_model=='alias_fixture'
        assert receipt.finish_reason=='stop' and receipt.delivery_outcome=='accepted'
        with root.queue.store.transaction() as tx:
            row=tx.conn.execute('SELECT model,usage FROM pa_cache.usage WHERE owner=%s AND task_ref=%s',(root.owner_ref,'daily_protocol_task')).fetchone()
        assert row['model']=='snapshot_fixture' and row['usage']['output']==12 and row['usage']['reasoning']==4
    elif mode=='cancel':
        events=[]
        with pytest.raises(ModelStreamInterrupted) as error:
            current.stream_with_receipt(**kwargs,on_event=events.append,cancelled=lambda:bool(events))
        assert events and error.value.partial_characters>0 and not error.value.retry_allowed
    else:
        exception=ModelProviderRejected if mode in {'403','429'} else ModelResponseInvalid if mode=='bad_usage' else LLMOutcomeUnknown
        with pytest.raises(exception) as error:current.complete_with_receipt(**kwargs)
        assert not error.value.retry_allowed and error.value.attempt_ref
    rebuilt,reserved=client('daily_protocol_second')
    try:
        with pytest.raises(ModelAttemptAlreadyRecorded):rebuilt.complete_with_receipt(**dict(kwargs,authorization=reserved))
    finally:reserved.reservation.abandon_before_transport()
    assert len(state['requests'])==1
    from prm.runtime.cost_cache import CostCacheRuntime
    cost=CostCacheRuntime(root).task_cost('daily_protocol_task')
    assert cost['attempts']==1 and cost['unknown_priced_attempts']==1 and cost['known_microdollars'] is None


def test_unknown_reasoning_subset_does_not_block_known_total_output_price(pai):
    from prm.runtime.cost_cache import CostCacheRuntime
    from datetime import timedelta
    cache=CostCacheRuntime(pai.root)
    cache.register_tariff(provider='provider_openai',model='fixture_model',version='daily_price',input_per_million=2,
        cached_input_per_million=.5,output_per_million=10,source_ref='https://example.test/synthetic_tariff',valid_until=pai.now+timedelta(days=1))
    usage={'input':100,'cached_input':20,'cache_write':None,'output':40,'reasoning':None,'semantics':'openai_chat_output_includes_reasoning'}
    assert cache.record(task_ref='daily_cost',attempt_ref='daily_cost_attempt',provider='provider_openai',model='fixture_model',usage=usage,
        latency_ms=1,outcome='accepted',tariff_version='daily_price')==570


def test_text_capabilities_cannot_silently_advertise_speech_or_vision():
    from prm.runtime.speech import SpeechTranscriber
    from prm.runtime.vision import VisionAdapter
    endpoint=ModelEndpoint('provider_openai','connection_fixture','http://127.0.0.1:1/chat/completions','fixture_model','',synthetic_http=True,capabilities=ChatCapabilities(streaming=True))
    for adapter in (SpeechTranscriber,VisionAdapter):
        with pytest.raises(StorageError,match='separate modality contract'):adapter(object(),endpoint=endpoint,upper_bound=0)


def test_sse_parser_bounds_wire_event_and_tool_authority():
    from io import BytesIO
    endpoint=ModelEndpoint('provider_openai','connection_fixture','http://127.0.0.1:1/chat/completions','fixture_model','',synthetic_http=True,capabilities=ChatCapabilities(streaming=True))
    adapter=ChatCompletionsTransport(endpoint)
    base={'id':'fixture_stream','model':'fixture_model','choices':[{'index':0,'delta':{'tool_calls':[{'name':'send'}]},'finish_reason':None}]}
    wires=[b'data: '+b'x'*65537+b'\n\n',b':'+b'x'*65535+b'\n',('data: '+json.dumps(base)+'\n\n').encode()]
    for wire in wires:
        with pytest.raises(ModelResponseInvalid):adapter._stream(BytesIO(wire),lambda:None,None)
    empty={'id':'fixture_stream','model':'fixture_model','choices':[{'index':0,'delta':{},'finish_reason':None}]}
    repeated=('data: '+json.dumps(empty)+'\n\n').encode()*2049
    with pytest.raises(ModelResponseInvalid):adapter._stream(BytesIO(repeated),lambda:None,None)


@pytest.mark.parametrize('trigger',['cancel','deadline','guard'])
def test_terminal_sse_read_rechecks_before_acceptance(trigger):
    from io import BytesIO
    from prm.runtime.model_errors import ModelStreamInterrupted
    state={'changed':False}
    base={'id':'fixture_stream','model':'fixture_model'}
    chunks=[{**base,'choices':[{'index':0,'delta':{'content':'Synthetic result'},'finish_reason':'stop'}]},
        {**base,'choices':[],'usage':{'prompt_tokens':1,'completion_tokens':1}}]
    wire=''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n'
    class Reader(BytesIO):
        def readline(self,*args):
            line=super().readline(*args)
            if self.tell()==len(wire.encode()):state['changed']=True
            return line
    def guard():
        if state['changed']:
            if trigger=='guard':raise StorageError('synthetic source changed')
            raise ModelStreamInterrupted(trigger)
    endpoint=ModelEndpoint('provider_openai','connection_fixture','http://127.0.0.1:1/chat/completions','fixture_model','',synthetic_http=True,capabilities=ChatCapabilities(streaming=True))
    with pytest.raises((ModelStreamInterrupted,StorageError)):
        ChatCompletionsTransport(endpoint)._stream(Reader(wire.encode()),guard,None)
