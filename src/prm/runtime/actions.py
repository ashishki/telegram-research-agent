"""Exact proposal -> edit -> confirm -> Graph adapter -> durable receipt."""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
import uuid
from urllib.parse import quote
from prm.confirmed_actions import ActionProposal,ActionExecuteRequest,ExecutionOutcome
from prm.capabilities import AuthorizationRequest,CapabilityDenied
from prm.storage.actions import DurableActionStore
from prm.storage.postgres import StorageError
from .delivery import DeliveryExecutor


class GraphActionAdapter:
    def __init__(self,transport):self.transport=transport
    def execute(self,action):
        proposal=action.proposal;content=proposal.content
        if proposal.connection_ref!=self.transport.connection_ref or proposal.owner_ref!=self.transport.owner_ref:
            raise CapabilityDenied('confirmed Graph account differs')
        # The outer common executor owns the precommitted attempt and policy
        # lock. Raw HTTP below rechecks connection, without consuming it again.
        if proposal.action_code=='mail.send':
            path='/v1.0/me/sendMail';method='POST'
            body={'message':{'subject':content['subject'],'body':{'contentType':'Text','content':content['body']},
                'toRecipients':[{'emailAddress':{'address':address}} for address in content['to']],
                'internetMessageHeaders':[{'name':'x-pai-attempt','value':action.idempotency_key},{'name':'x-pai-content-digest','value':proposal.digest}]},
                  'saveToSentItems':True}
        elif proposal.action_code=='calendar.create':
            path='/v1.0/me/calendars/'+quote(content['calendar_ref'],safe='')+'/events';method='POST'
            body={'subject':content['title'],'start':{'dateTime':content['start_at'],'timeZone':content['timezone']},
                'end':{'dateTime':content['end_at'],'timeZone':content['timezone']},'transactionId':action.idempotency_key}
        elif proposal.action_code=='calendar.update':
            path='/v1.0/me/events/'+quote(content['event_ref'],safe='');method='PATCH'
            body={'subject':content['title'],'start':{'dateTime':content['start_at'],'timeZone':content['timezone']},
                'end':{'dateTime':content['end_at'],'timeZone':content['timezone']}}
        elif proposal.action_code=='calendar.cancel':
            path='/v1.0/me/events/'+quote(content['event_ref'],safe='')+'/cancel';method='POST';body={'comment':content.get('comment','')}
        else:raise CapabilityDenied('unsupported action; payments/coursework excluded')
        headers={}
        if proposal.action_code in {'calendar.update','calendar.cancel'}:
            if not content.get('etag'):raise CapabilityDenied('current provider ETag required for existing event writes')
            headers['If-Match']=content['etag']
        value,receipt=self.transport.raw_request(action=action,path=path,method=method,body=body,headers=headers)
        provider_ref=value.get('id') or receipt['request_id']
        if not provider_ref:return ExecutionOutcome('unknown',error_code='provider_operation_reference_unavailable')
        return ExecutionOutcome('succeeded',provider_operation_ref=provider_ref)

    def reconcile(self,receipt):
        # A missing sent-item/event lookup never establishes known absence.
        return ExecutionOutcome('unknown',error_code='authoritative_lookup_unavailable')


class ActionRuntime:
    def __init__(self,root,*,graph_transport,upper_bound):
        self.root=root;self.transport=graph_transport;self.upper_bound=upper_bound
        self.store=DurableActionStore(root.queue.store.target,owner_ref=root.owner_ref)
        self.adapter=GraphActionAdapter(graph_transport)
        self.executor=DeliveryExecutor(root.queue.store.target,registry=root.registry,sender=None)

    def preview(self,*,action_code,resource_ref,content,rationale_refs):
        now=datetime.now(timezone.utc)
        if content.get('account_ref',self.transport.account_ref)!=self.transport.account_ref:raise CapabilityDenied('preview account substitution denied')
        content={**content,'account_ref':self.transport.account_ref}
        if action_code.startswith('calendar.'):
            from zoneinfo import ZoneInfo
            if action_code!='calendar.cancel':ZoneInfo(content['timezone'])
            if action_code in {'calendar.update','calendar.cancel'} and not content.get('etag'):raise CapabilityDenied('exact event ETag required in preview')
        proposal=ActionProposal('proposal_'+uuid.uuid4().hex,self.root.owner_ref,self.transport.connection_ref,'provider_microsoft_graph',
            action_code,resource_ref,1,content,tuple(rationale_refs),now,now+timedelta(minutes=10))
        self.store.register(proposal);self._show(proposal);return proposal

    def edit(self,proposal,*,content):
        changed=replace(proposal,version=proposal.version+1,content=content,created_at=datetime.now(timezone.utc),expires_at=datetime.now(timezone.utc)+timedelta(minutes=10))
        self.store.register(changed,expected_version=proposal.version);self._show(changed);return changed

    def _show(self,proposal):
        from prm.conversation import ConfirmationRef,identity_hash
        text='Предпросмотр '+proposal.action_code+': '+__import__('json').dumps(proposal.content,ensure_ascii=False)
        state=self.root.conversations.record_response(self.root.owner_chat_id,text=text[:2400],topic='')
        identity=identity_hash(self.root.owner_chat_id)
        self.root.conversations.offer_confirmation(self.root.owner_chat_id,ConfirmationRef(proposal.proposal_ref,str(proposal.version),
            state.object_refs[0].response_ref,identity,identity,identity,proposal.expires_at))

    def confirm_and_execute(self,proposal_ref,*,actor_ref):
        if actor_ref!=self.root.owner_ref:raise CapabilityDenied('private owner confirmation required')
        with self.store.store.transaction() as tx:
            current=tx.conn.execute('SELECT version FROM pa_actions.proposals WHERE owner=%s AND ref=%s',(self.root.owner_ref,proposal_ref)).fetchone()
        prior=[receipt for receipt in self.store.all() if receipt.proposal_ref==proposal_ref and current is not None and receipt.proposal_version==current['version']]
        if prior:return prior[-1]
        state=self.root.conversations.load(self.root.owner_chat_id)
        if state is None or state.current_confirmation_ref is None or state.current_confirmation_ref.proposal_ref!=proposal_ref:
            raise CapabilityDenied('one current visible exact preview required')
        action=self.store.confirm(proposal_ref,actor_ref=actor_ref)
        if state.current_confirmation_ref.proposal_version!=str(action.proposal.version):raise CapabilityDenied('visible preview version changed')
        decision=self.root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=self.root.owner_ref,
            connection_ref=action.proposal.connection_ref,capability='assistant.action_execute',resource_ref=action.proposal.resource_ref,
            operation='write',data_class='private_connector_content',provider_ref='provider_microsoft_graph',purpose='action.execute',
            operation_ref='action_'+uuid.uuid4().hex),upper_bound=self.upper_bound)
        request=ActionExecuteRequest(decision,self.root.owner_ref,action.proposal.connection_ref,action.proposal.resource_ref,'provider_microsoft_graph')
        return self.executor.execute_confirmed_action(action,request=request,executor=self.adapter,store=self.store)
