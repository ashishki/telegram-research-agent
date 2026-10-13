"""Explicit Chat Completions capabilities and bounded transport. No ambient keys."""
from __future__ import annotations
from dataclasses import dataclass,field
from typing import Protocol
from urllib.request import Request,ProxyHandler,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.parse import urlsplit
import json
import re
import time
from prm.storage.postgres import StorageError
from .model_errors import ModelProviderRejected,ModelResponseInvalid,ModelStreamInterrupted,DEFINITIVE_REJECTIONS


@dataclass(frozen=True)
class ChatCapabilities:
    protocol: str = 'chat_completions'
    token_parameter: str = 'max_completion_tokens'
    accepted_models: tuple[str,...] = ()
    streaming: bool = False
    usage_semantics: str = 'unknown_compatible_provider'
    store_false: bool = True
    client_kind: str = 'standard'
    session_ref: str | None = None
    workload_ref: str | None = None

    def __post_init__(self):
        if (self.protocol!='chat_completions' or self.token_parameter not in {'max_tokens','max_completion_tokens'}
            or type(self.streaming)is not bool or type(self.store_false)is not bool
            or self.usage_semantics not in {'unknown_compatible_provider','openai_chat_output_includes_reasoning'}
            or self.client_kind not in {'standard','opencode_go'}
            or not isinstance(self.accepted_models,tuple) or len(self.accepted_models)>8
            or len(set(self.accepted_models))!=len(self.accepted_models)
            or any(not isinstance(x,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,128}',x) for x in self.accepted_models)):
            raise StorageError('invalid explicit model capabilities')
        for value,prefix in ((self.session_ref,'session_'),(self.workload_ref,'workload_')):
            if value is not None and (not isinstance(value,str) or not re.fullmatch(prefix+r'[A-Za-z0-9_-]{1,96}',value)):
                raise StorageError('opaque model session/workload reference required')
        if self.client_kind=='opencode_go' and (not self.session_ref or not self.workload_ref):
            raise StorageError('Go requires explicit stable session and selected workload')

    @classmethod
    def from_mapping(cls,value):
        if type(value)is cls:return value
        if not isinstance(value,dict):raise StorageError('explicit model capabilities object required')
        value=dict(value)
        if 'accepted_models' in value:
            if not isinstance(value['accepted_models'],list):raise StorageError('typed model alias list required')
            value['accepted_models']=tuple(value['accepted_models'])
        try:return cls(**value)
        except (TypeError,ValueError):raise StorageError('invalid explicit model capabilities') from None

    def headers(self):
        headers={'Content-Type':'application/json','User-Agent':'telegram-research-agent/1.0'}
        if self.client_kind=='opencode_go':headers['x-opencode-session']=self.session_ref
        return headers

    def validate_route(self,endpoint,*,synthetic_http=False):
        url=urlsplit(endpoint)
        if not synthetic_http and self.client_kind=='opencode_go':
            if (url.scheme,url.netloc,url.path)!=('https','opencode.ai','/zen/go/v1/chat/completions'):
                raise StorageError('Go descriptor must use the exact selected Go endpoint')


@dataclass(frozen=True)
class ModelReply:
    text: str = field(repr=False)
    requested_model: str
    observed_model: str
    finish_reason: str
    usage: dict


@dataclass(frozen=True)
class ModelDelta:
    text: str = field(repr=False)
    sequence: int
    authority: str = 'untrusted_partial'


class ModelTransport(Protocol):
    def encode(self,messages,max_tokens,*,stream=False)->bytes: ...
    def send(self,body,*,before_request,on_event=None,cancelled=None,guard=None)->ModelReply: ...


class DenyRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise StorageError('selected model redirect denied')


def normalize_chat_usage(value,semantics):
    if not isinstance(value,dict):raise ModelResponseInvalid()
    for key in ('prompt_tokens','completion_tokens'):
        if type(value.get(key))is not int or not 0<=value[key]<=1000000:raise ModelResponseInvalid()
    if 'total_tokens' in value and (type(value['total_tokens'])is not int or value['total_tokens']!=value['prompt_tokens']+value['completion_tokens']):
        raise ModelResponseInvalid()
    subsets=[]
    for name,key,total in (('prompt_tokens_details','cached_tokens','prompt_tokens'),('completion_tokens_details','reasoning_tokens','completion_tokens')):
        detail=value.get(name)
        if detail is None:subsets.append(None);continue
        if not isinstance(detail,dict):raise ModelResponseInvalid()
        count=detail.get(key)
        if count is not None and (type(count)is not int or not 0<=count<=value[total]):raise ModelResponseInvalid()
        subsets.append(count)
    return {'input':value['prompt_tokens'],'output':value['completion_tokens'],'cached_input':subsets[0],
        'reasoning':subsets[1],'cache_write':None,'semantics':semantics}


def _json(raw):
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('duplicate JSON field')
            value[key]=item
        return value
    try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('constant')))
    except (ValueError,UnicodeError,RecursionError):raise ModelResponseInvalid() from None


class ChatCompletionsTransport:
    """Internal adapter. Caller must hold sealed reservations through send()."""
    def __init__(self,endpoint):
        self.endpoint=endpoint
        self.capabilities=endpoint.capabilities or ChatCapabilities(usage_semantics=
            'openai_chat_output_includes_reasoning' if endpoint.provider_ref=='provider_openai' else 'unknown_compatible_provider')

    def encode(self,messages,max_tokens,*,stream=False):
        cap=self.capabilities
        if type(max_tokens)is not int or not 1<=max_tokens<=16000:raise StorageError('bounded model output limit required')
        if type(stream)is not bool or stream and not cap.streaming:raise StorageError('selected model streaming is unsupported')
        if not isinstance(messages,list) or len(messages)>32:raise StorageError('bounded model messages required')
        for message in messages:
            if (not isinstance(message,dict) or set(message)!={'role','content'} or message['role'] not in {'system','user','assistant'}
                or not isinstance(message['content'],str) or len(message['content'])>48000):raise StorageError('invalid bounded history')
        value={'model':self.endpoint.model,'messages':messages,cap.token_parameter:max_tokens,'stream':stream}
        if cap.store_false:value['store']=False
        if stream:value['stream_options']={'include_usage':True}
        raw=json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
        if len(raw)>48000:raise StorageError('model request exceeds bounded scope')
        return raw

    def _identity(self,value):
        model=value.get('model')
        if model not in (self.endpoint.model,*self.capabilities.accepted_models):raise ModelResponseInvalid()
        return model

    def _reply(self,value):
        if not isinstance(value,dict):raise ModelResponseInvalid()
        model=self._identity(value);choices=value.get('choices')
        if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict):raise ModelResponseInvalid()
        choice=choices[0];message=choice.get('message')
        if type(choice.get('index',0))is not int or choice.get('index',0)!=0 or choice.get('finish_reason')!='stop' or not isinstance(message,dict) or message.get('tool_calls') or message.get('function_call') or message.get('refusal'):
            raise ModelResponseInvalid(finish_reason=choice.get('finish_reason') if choice.get('finish_reason') in {'length','content_filter','tool_calls','function_call'} else None)
        text=message.get('content')
        if not isinstance(text,str) or not text.strip() or len(text.encode())>24000:raise ModelResponseInvalid()
        return ModelReply(text,self.endpoint.model,model,'stop',normalize_chat_usage(value.get('usage'),self.capabilities.usage_semantics))

    def send(self,body,*,before_request,on_event=None,cancelled=None,guard=None):
        started=time.monotonic()
        stream=_json(body).get('stream') is True
        def check():
            if guard:guard()
            if cancelled and cancelled():raise ModelStreamInterrupted('cancelled')
            if time.monotonic()-started>self.endpoint.timeout_seconds:raise ModelStreamInterrupted('deadline')
        check();headers=self.capabilities.headers()
        if self.endpoint.token:headers['Authorization']='Bearer '+self.endpoint.token
        request=Request(self.endpoint.endpoint,data=body,headers=headers,method='POST')
        before_request()
        try:
            with build_opener(ProxyHandler({}),DenyRedirect()).open(request,timeout=self.endpoint.timeout_seconds) as response:
                if stream:
                    if response.headers.get_content_type()!='text/event-stream':raise ModelResponseInvalid()
                    return self._stream(response,check,on_event)
                if response.headers.get_content_type()!='application/json':raise ModelResponseInvalid()
                raw=response.read(1048577);check()
                if len(raw)>1048576:raise ModelResponseInvalid()
                return self._reply(_json(raw))
        except HTTPError as error:
            code=error.code;retry=error.headers.get('Retry-After','')
            error.close()
            if code in DEFINITIVE_REJECTIONS:
                raise ModelProviderRejected(code,retry_after=int(retry) if retry.isascii() and retry.isdigit() and len(retry)<=5 and int(retry)<=86400 else None) from None
            raise StorageError('selected model transport outcome is unknown') from None
        except (ModelResponseInvalid,ModelProviderRejected,ModelStreamInterrupted):raise
        except Exception:raise StorageError('selected model transport outcome is unknown') from None

    def _stream(self,response,check,on_event):
        data=[];wire=0;events=0;text=[];size=0;identity=None;model=None;finish=None;usage=None
        while True:
            try:check()
            except ModelStreamInterrupted as error:
                error.partial_characters=sum(map(len,text));raise
            line=response.readline(65537);wire+=len(line)
            if wire>1048576 or len(line)>65536:raise ModelResponseInvalid()
            if not line:raise ModelStreamInterrupted('incomplete',partial_characters=sum(map(len,text)))
            if line in {b'\n',b'\r\n'}:
                if not data:continue
                events+=1
                if events>2048:raise ModelResponseInvalid()
                raw=b'\n'.join(data);data=[]
                if raw==b'[DONE]':
                    if finish!='stop' or usage is None or not ''.join(text).strip():
                        raise ModelStreamInterrupted('incomplete',partial_characters=sum(map(len,text)))
                    return ModelReply(''.join(text),self.endpoint.model,model,finish,usage)
                value=_json(raw)
                if not isinstance(value,dict):raise ModelResponseInvalid()
                current_model=self._identity(value);current_id=value.get('id')
                if not isinstance(current_id,str) or not 1<=len(current_id)<=128:raise ModelResponseInvalid()
                if identity is not None and (current_id!=identity or current_model!=model):raise ModelResponseInvalid()
                identity,model=current_id,current_model
                choices=value.get('choices')
                if choices==[]:
                    if finish!='stop' or usage is not None:raise ModelResponseInvalid()
                    usage=normalize_chat_usage(value.get('usage'),self.capabilities.usage_semantics);continue
                if finish is not None or usage is not None or not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict):raise ModelResponseInvalid()
                choice=choices[0];delta=choice.get('delta')
                if type(choice.get('index'))is not int or choice.get('index')!=0 or not isinstance(delta,dict) or set(delta)-{'role','content'} or delta.get('role','assistant')!='assistant':raise ModelResponseInvalid()
                part=delta.get('content')
                if part is not None:
                    if not isinstance(part,str):raise ModelResponseInvalid()
                    size+=len(part.encode())
                    if size>24000:raise ModelResponseInvalid()
                    text.append(part)
                    if on_event and part:on_event(ModelDelta(part,events))
                reason=choice.get('finish_reason')
                if reason is not None:
                    if reason!='stop':raise ModelResponseInvalid(finish_reason=reason if reason in {'length','content_filter','tool_calls'} else None)
                    finish=reason
            elif line.startswith(b'data:'):
                data.append(line[5:].strip())
                if sum(map(len,data))>65536:raise ModelResponseInvalid()
            elif line.startswith(b':'):continue
            elif line.strip():raise ModelResponseInvalid()
