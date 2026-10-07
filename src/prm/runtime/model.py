"""Explicit bounded Chat Completions transport; no ambient key/provider/model."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import time
import hashlib
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler,ProxyHandler, build_opener

from llm.client import LLMCompletionReceipt, LLMOutcomeUnknown
from prm.capabilities import CapabilityDenied, AuthorizationDecision
from prm.storage.policy import DurableCapabilityRegistry
from prm.storage.postgres import StorageError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise StorageError('provider redirect denied')


@dataclass(frozen=True)
class ModelEndpoint:
    provider_ref: str
    connection_ref: str
    endpoint: str
    model: str
    token: str = field(repr=False, compare=False)
    timeout_seconds: int = 8
    synthetic_http: bool = False

    def __post_init__(self):
        url=urlsplit(self.endpoint)
        if (not self.provider_ref.startswith('provider_') or not self.connection_ref.startswith('connection_')
            or not self.model or len(self.model)>128 or not isinstance(self.token,str)
            or '\n' in self.token or '\r' in self.token or url.username or url.password or url.fragment
            or not 1<=self.timeout_seconds<=8):
            raise StorageError('explicit bounded model endpoint required')
        if self.synthetic_http:
            if url.scheme!='http' or url.hostname!='127.0.0.1' or not url.port:
                raise StorageError('synthetic HTTP requires literal loopback endpoint')
        elif url.scheme!='https' or not url.hostname or not self.token:
            raise StorageError('credential-bound HTTPS model endpoint required')
        elif self.connection_ref!=credential_connection_ref(self.provider_ref,self.endpoint,self.token):
            raise StorageError('model connection must bind the exact configured credential and endpoint')


def credential_connection_ref(provider_ref,endpoint,token):
    return 'connection_'+hashlib.sha256((provider_ref+'\x1f'+endpoint+'\x1f'+token).encode()).hexdigest()[:32]


@dataclass(frozen=True)
class RuntimeModelAccess:
    authorization: AuthorizationDecision
    owner_ref: str
    connection_ref: str
    resource_ref: str

    def __post_init__(self):
        auth=self.authorization
        if (type(auth)is not AuthorizationDecision or not auth.allowed or auth.reservation is None
            or (auth.owner_ref,auth.connection_ref,auth.resource_ref,auth.capability,auth.operation,auth.data_class,auth.purpose)
               !=(self.owner_ref,self.connection_ref,self.resource_ref,'model.generate','model_egress','user_provided','answer.request')):
            raise CapabilityDenied('runtime model access scope differs')


class ScopedModelClient:
    def __init__(self, endpoint: ModelEndpoint, registry: DurableCapabilityRegistry, *, groups, history=(), guard=None,usage_observer=None,task_ref=None):
        self.endpoint,self.registry,self.groups=endpoint,registry,tuple(tuple(group) for group in groups)
        self.history=tuple(history);self.guard=guard
        self.usage_observer=usage_observer;self.task_ref=task_ref;self.attempt_ref=None;self._called=False

    def complete_with_receipt(self,*,prompt,system,max_tokens,category,authorization,data_class,owner_ref,connection_ref,resource_ref):
        endpoint=self.endpoint
        if (authorization is not self.groups[0][0] or authorization.provider_ref!=endpoint.provider_ref
            or connection_ref!=endpoint.connection_ref or owner_ref!=authorization.owner_ref
            or resource_ref!=authorization.resource_ref or data_class!='user_provided'):
            raise CapabilityDenied('configured model differs from sealed access')
        messages=[{'role':'system','content':system}]
        for item in self.history:
            if item['role'] not in {'user','assistant'} or not isinstance(item['content'],str):
                raise StorageError('invalid bounded history')
            messages.append(dict(item))
        messages.append({'role':'user','content':prompt})
        body=json.dumps({'model':endpoint.model,'messages':messages,'max_completion_tokens':max_tokens,
                         'store':False,'stream':False},ensure_ascii=False).encode()
        if len(body)>48000:raise StorageError('model request exceeds bounded scope')
        from .model_attempts import prepare_model_attempt,ModelAttemptAlreadyRecorded
        operations=tuple(group[0].operation_ref for group in self.groups)
        if self._called:raise ModelAttemptAlreadyRecorded(self.attempt_ref or operations[0],operations)
        self._called=True
        self.attempt_ref=prepare_model_attempt(self.registry.store,owner=owner_ref,task_ref=self.task_ref or operations[0],
            purpose=self.groups[0][0].purpose,operation_refs=operations,input_digest=hashlib.sha256(body).hexdigest())
        started=time.monotonic();http_attempted=False
        def transport():
            nonlocal http_attempted
            if self.guard:self.guard()
            headers={'Content-Type':'application/json'}
            if endpoint.token:headers['Authorization']='Bearer '+endpoint.token
            request=Request(endpoint.endpoint,data=body,headers=headers,method='POST')
            http_attempted=True
            with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=endpoint.timeout_seconds) as response:
                if response.headers.get_content_type()!='application/json':raise StorageError('model response type differs')
                raw=response.read(1048577)
                if len(raw)>1048576:raise StorageError('model response exceeds bound')
                value=json.loads(raw)
            choices=value.get('choices')
            if value.get('model')!=endpoint.model or not isinstance(choices,list) or len(choices)!=1:
                raise StorageError('observed model or choice identity differs')
            choice=choices[0]
            if choice.get('finish_reason')!='stop' or choice.get('message',{}).get('tool_calls'):
                raise StorageError('incomplete model output or tool invocation denied')
            text=choice.get('message',{}).get('content')
            if not isinstance(text,str) or not text.strip() or len(text.encode())>24000:raise StorageError('invalid model text')
            usage=value.get('usage',{})
            for key in ('prompt_tokens','completion_tokens'):
                if type(usage.get(key))is not int or not 0<=usage[key]<=1000000:raise StorageError('usage unavailable or invalid')
            return text,usage
        try:
            reservations=tuple(tuple(decision.reservation for decision in group) for group in self.groups)
            text,usage=self.registry.execute_reserved_groups(reservations,transport)
        except CapabilityDenied:raise
        except Exception:
            unknown=LLMCompletionReceipt(text='',model=endpoint.model,input_tokens=0,output_tokens=0,
                estimated_cost_usd=None,duration_ms=int((time.monotonic()-started)*1000),attempts=1,usage_recorded=False,
                external_call_attempted=http_attempted,delivery_outcome='unknown')
            if self.usage_observer:
                self.usage_observer(unknown,{'input':None,'cached_input':None,'cache_write':None,'output':None,'reasoning':None,'semantics':'unknown_outcome'},self.groups)
            error=LLMOutcomeUnknown(unknown)
            error.operation_refs=operations;error.attempt_ref=self.attempt_ref;error.retry_allowed=False
            raise error from None
        receipt=LLMCompletionReceipt(text=text,model=endpoint.model,input_tokens=usage['prompt_tokens'],
            output_tokens=usage['completion_tokens'],estimated_cost_usd=None,duration_ms=int((time.monotonic()-started)*1000),
            attempts=1,usage_recorded=False,external_call_attempted=True,delivery_outcome='accepted')
        if self.usage_observer:
            normalized={'input':usage['prompt_tokens'],'cached_input':usage.get('prompt_tokens_details',{}).get('cached_tokens',0),
                        'cache_write':0,'output':usage['completion_tokens'],'reasoning':usage.get('completion_tokens_details',{}).get('reasoning_tokens',0),
                        'semantics':'openai_chat_output_includes_reasoning' if endpoint.provider_ref=='provider_openai' else 'unknown_compatible_provider'}
            self.usage_observer(receipt,normalized,self.groups)
        return receipt
