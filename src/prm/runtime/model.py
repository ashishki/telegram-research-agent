"""Explicit bounded Chat Completions transport; no ambient key/provider/model."""
from __future__ import annotations
from dataclasses import dataclass, field, fields
import json
import time
import hashlib
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler,ProxyHandler, build_opener

from llm.client import LLMCompletionReceipt, LLMOutcomeUnknown
from prm.capabilities import CapabilityDenied, AuthorizationDecision
from prm.storage.policy import DurableCapabilityRegistry,ScopePreparationUnknown
from prm.storage.postgres import StorageError
from .model_errors import ModelResponseInvalid,ModelAccountingReceipt,ModelPreparationUnknown,ModelAccountingUnconfirmed,ModelCompletionReceipt,ModelProviderRejected,ModelStreamInterrupted
from .model_protocol import ChatCapabilities,ChatCompletionsTransport


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
    capabilities: ChatCapabilities | dict | None = None

    def __post_init__(self):
        try:
            url=urlsplit(self.endpoint);url.port
        except (ValueError,AttributeError):raise StorageError('invalid explicit model endpoint') from None
        if self.capabilities is not None:
            object.__setattr__(self,'capabilities',ChatCapabilities.from_mapping(self.capabilities))
            self.capabilities.validate_route(self.endpoint,synthetic_http=self.synthetic_http)
        if (not self.provider_ref.startswith('provider_') or not self.connection_ref.startswith('connection_')
            or not self.model or len(self.model)>128 or not isinstance(self.token,str)
            or '\n' in self.token or '\r' in self.token or url.username or url.password or url.fragment or url.query
            or type(self.synthetic_http)is not bool
            or type(self.timeout_seconds) is not int or not 1<=self.timeout_seconds<=120):
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
        self.usage_observer=usage_observer;self.task_ref=task_ref;self.attempt_ref=None;self._called=False;self.input_digest=None

    def stream_with_receipt(self,*,on_event,cancelled=None,**kwargs):
        return self._complete(stream=True,on_event=on_event,cancelled=cancelled,**kwargs)

    def complete_with_receipt(self,**kwargs):
        return self._complete(**kwargs)

    def _complete(self,*,prompt,system,max_tokens,category,authorization,data_class,owner_ref,connection_ref,resource_ref,stream=False,on_event=None,cancelled=None):
        endpoint=self.endpoint
        if (authorization is not self.groups[0][0] or authorization.provider_ref!=endpoint.provider_ref
            or connection_ref!=endpoint.connection_ref or owner_ref!=authorization.owner_ref
            or resource_ref!=authorization.resource_ref or data_class!='user_provided'):
            raise CapabilityDenied('configured model differs from sealed access')
        if type(max_tokens)is not int or not 1<=max_tokens<=16000:
            raise StorageError('bounded model output limit required')
        if any(not isinstance(value,str) or len(value)>48000 for value in (prompt,system)):
            raise StorageError('model request exceeds bounded scope')
        messages=[{'role':'system','content':system}]
        for item in self.history:
            if item['role'] not in {'user','assistant'} or not isinstance(item['content'],str) or len(item['content'])>48000:
                raise StorageError('invalid bounded history')
            messages.append(dict(item))
        messages.append({'role':'user','content':prompt})
        adapter=ChatCompletionsTransport(endpoint)
        body=adapter.encode(messages,max_tokens,stream=stream)
        from .model_attempts import prepare_model_attempt,ModelAttemptAlreadyRecorded
        operations=tuple(group[0].operation_ref for group in self.groups)
        digest=hashlib.sha256(body).hexdigest()
        if self._called:raise ModelAttemptAlreadyRecorded(self.attempt_ref or operations[0],operations,
            recorded_digest=self.input_digest,requested_digest=digest)
        self._called=True
        self.input_digest=digest
        self.attempt_ref=prepare_model_attempt(self.registry.store,owner=owner_ref,task_ref=self.task_ref or operations[0],
            purpose=self.groups[0][0].purpose,operation_refs=operations,input_digest=digest)
        started=time.monotonic();http_attempted=False;known_reply_error=None;accepted_reply=None;accounting_unconfirmed=False
        def transport():
            def attempted():
                nonlocal http_attempted
                http_attempted=True
            return adapter.send(body,before_request=attempted,on_event=on_event,cancelled=cancelled,guard=self.guard)
        def checked_transport():
            nonlocal known_reply_error,accepted_reply
            try:
                accepted_reply=transport();return accepted_reply
            except (ModelResponseInvalid,ModelProviderRejected,ModelStreamInterrupted) as error:
                known_reply_error=error;raise
        try:
            reservations=tuple(tuple(decision.reservation for decision in group) for group in self.groups)
            if endpoint.timeout_seconds<=8:
                reply=self.registry.execute_reserved_groups(reservations,checked_transport)
            else:
                reply=self.registry.execute_reserved_groups(reservations,checked_transport,model_timeout_seconds=endpoint.timeout_seconds)
        except CapabilityDenied:raise
        except ScopePreparationUnknown as error:
            raise ScopePreparationUnknown(error.operation_refs,attempt_ref=self.attempt_ref) from None
        except Exception:
            if accepted_reply is not None:
                # The reply was positively observed even if final settlement
                # lost its acknowledgement. Preserve it without another call.
                reply=accepted_reply;accounting_unconfirmed=True
            elif not http_attempted:
                raise ModelPreparationUnknown(self.attempt_ref,operations) from None
            else:
                unknown=ModelCompletionReceipt(text='',model=endpoint.model,requested_model=endpoint.model,input_tokens=0,output_tokens=0,
                    estimated_cost_usd=None,duration_ms=int((time.monotonic()-started)*1000),attempts=1,usage_recorded=False,
                    external_call_attempted=http_attempted,delivery_outcome='rejected' if isinstance(known_reply_error,ModelProviderRejected) else 'unknown')
                # Compound execution may wrap the original validation error.
                error=known_reply_error or LLMOutcomeUnknown(unknown)
                error.operation_refs=operations;error.attempt_ref=self.attempt_ref;error.retry_allowed=False
                if self.usage_observer:
                    try:self.usage_observer(unknown,{'input':None,'cached_input':None,'cache_write':None,'output':None,'reasoning':None,
                        'semantics':known_reply_error.reason_kind if known_reply_error else 'unknown_outcome'},self.groups)
                    except Exception:error.accounting_status='unconfirmed'
                raise error from None
        receipt=ModelCompletionReceipt(text=reply.text,model=reply.observed_model,requested_model=reply.requested_model,
            observed_model=reply.observed_model,finish_reason=reply.finish_reason,input_tokens=reply.usage['input'],
            output_tokens=reply.usage['output'],estimated_cost_usd=None,duration_ms=int((time.monotonic()-started)*1000),
            attempts=1,usage_recorded=False,external_call_attempted=True,delivery_outcome='accepted')
        from .model_attempts import record_model_observation
        try:record_model_observation(self.registry.store,owner=owner_ref,attempt_ref=self.attempt_ref,operation_refs=operations,receipt=receipt,usage=reply.usage)
        except Exception:accounting_unconfirmed=True
        if self.usage_observer:
            normalized=reply.usage
            try:self.usage_observer(receipt,normalized,self.groups)
            except Exception:accounting_unconfirmed=True
        if accounting_unconfirmed:
            from .model_attempts import record_accounting_unconfirmed
            unconfirmed=ModelAccountingReceipt(**{item.name:getattr(receipt,item.name) for item in fields(ModelCompletionReceipt)},
                attempt_ref=self.attempt_ref,operation_refs=operations)
            try:record_accounting_unconfirmed(self.registry.store,owner=owner_ref,receipt=unconfirmed)
            except Exception:raise ModelAccountingUnconfirmed(unconfirmed) from None
            return unconfirmed
        return receipt
