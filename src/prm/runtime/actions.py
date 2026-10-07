"""Exact proposal -> edit -> confirm -> Graph adapter -> durable receipt."""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
import uuid
from urllib.parse import quote,urlencode
from prm.confirmed_actions import ActionProposal,ActionExecuteRequest,ExecutionOutcome
from prm.capabilities import AuthorizationRequest,CapabilityDenied
from prm.storage.actions import DurableActionStore
from prm.storage.postgres import StorageError
from .delivery import DeliveryExecutor


def _calendar_time(value,timezone_name):
    from zoneinfo import ZoneInfo
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:raise CapabilityDenied('aware event instant required')
    return parsed.astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None).isoformat()


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
            body={'subject':content['title'],'start':{'dateTime':_calendar_time(content['start_at'],content['timezone']),'timeZone':content['timezone']},
                'end':{'dateTime':_calendar_time(content['end_at'],content['timezone']),'timeZone':content['timezone']},'transactionId':action.idempotency_key}
        elif proposal.action_code=='calendar.update':
            path='/v1.0/me/calendars/'+quote(content['calendar_ref'],safe='')+'/events/'+quote(content['event_ref'],safe='');method='PATCH'
            body={'subject':content['title'],'start':{'dateTime':_calendar_time(content['start_at'],content['timezone']),'timeZone':content['timezone']},
                'end':{'dateTime':_calendar_time(content['end_at'],content['timezone']),'timeZone':content['timezone']}}
        elif proposal.action_code=='calendar.cancel':
            path='/v1.0/me/calendars/'+quote(content['calendar_ref'],safe='')+'/events/'+quote(content['event_ref'],safe='')+'/cancel';method='POST';body={'comment':content.get('comment','')}
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
        from prm.storage.actions import _proposal
        with self.transport.connections.store.transaction() as tx:
            row=tx.conn.execute('SELECT payload FROM pa_actions.proposals WHERE owner=%s AND ref=%s',
                (self.transport.owner_ref,receipt.proposal_ref)).fetchone()
        if row is None:return ExecutionOutcome('unknown',error_code='proposal_unavailable')
        proposal=_proposal(row['payload'])
        if proposal.version!=receipt.proposal_version or proposal.digest!=receipt.content_digest:
            return ExecutionOutcome('unknown',error_code='proposal_changed')
        if not any(request.capability=='assistant.action_reconciliation' and request.owner_ref==proposal.owner_ref and
                   request.connection_ref==proposal.connection_ref and request.resource_ref==proposal.resource_ref
                   for request in self.transport.registry.current_transport_requests):raise CapabilityDenied('reconciliation read scope required')
        if proposal.action_code=='mail.send':
            path='/v1.0/me/mailFolders/sentitems/messages?'+urlencode({'$top':'25','$select':'id,internetMessageHeaders','$orderby':'sentDateTime desc'})
        elif proposal.action_code=='calendar.create':
            path='/v1.0/me/calendars/'+quote(proposal.content['calendar_ref'],safe='')+'/events?'+urlencode({'$top':'100','$select':'id,transactionId'})
        else:return ExecutionOutcome('unknown',error_code='update_outcome_not_authoritatively_identifiable')
        value,_=self.transport._guarded_http(path=path,method='GET',body=None,headers=None)
        for item in value.get('value',()):
            if proposal.action_code=='mail.send':
                headers={entry.get('name','').casefold():entry.get('value') for entry in item.get('internetMessageHeaders',())}
                matched=headers.get('x-pai-attempt')==receipt.idempotency_key and headers.get('x-pai-content-digest')==receipt.content_digest
            else:matched=item.get('transactionId')==receipt.idempotency_key
            if matched and isinstance(item.get('id'),str):return ExecutionOutcome('succeeded',provider_operation_ref=item['id'])
        return ExecutionOutcome('unknown',error_code='bounded_lookup_does_not_prove_absence')


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
        if content.get('account_ref',self.transport.account_ref)!=self.transport.account_ref:raise CapabilityDenied('edited account differs')
        content={**content,'account_ref':self.transport.account_ref}
        if proposal.action_code.startswith('calendar.') and proposal.action_code!='calendar.cancel':
            from zoneinfo import ZoneInfo
            ZoneInfo(content['timezone'])
        changed=replace(proposal,version=proposal.version+1,content=content,created_at=datetime.now(timezone.utc),expires_at=datetime.now(timezone.utc)+timedelta(minutes=10))
        self.store.register(changed,expected_version=proposal.version);self._show(changed);return changed

    def _show(self,proposal):
        from prm.conversation import ConfirmationRef,identity_hash
        text='Предпросмотр '+proposal.action_code+': '+__import__('json').dumps(proposal.content,ensure_ascii=False)
        state=self.root.conversations.record_response(self.root.owner_chat_id,text=text[:2400],topic='')
        identity=identity_hash(self.root.owner_chat_id)
        self.root.conversations.offer_confirmation(self.root.owner_chat_id,ConfirmationRef(proposal.proposal_ref,str(proposal.version),
            state.object_refs[0].response_ref,identity,identity,identity,proposal.expires_at))

    def _read(self,proposal,*,path,capability,resource_ref,purpose):
        decision=self.root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=self.root.owner_ref,
            connection_ref=proposal.connection_ref,capability=capability,resource_ref=resource_ref,operation='read',
            data_class='private_connector_metadata',provider_ref='provider_microsoft_graph',purpose=purpose,
            operation_ref='preflight_'+uuid.uuid4().hex),upper_bound=self.upper_bound)
        if not decision.allowed:raise CapabilityDenied(decision.reason)
        return self.transport.request(decision,path=path)

    def _preflight(self,proposal):
        content=proposal.content
        if content.get('account_ref')!=self.transport.account_ref:raise CapabilityDenied('edited preview account differs')
        if proposal.action_code=='mail.send':
            # Exact email addresses are already in the confirmed content. A
            # selected reply context must still identify the same conversation.
            if content.get('thread_message_ref'):
                value,_=self._read(proposal,path='/v1.0/me/messages/'+quote(content['thread_message_ref'],safe='')+'?'+urlencode({'$select':'id,conversationId,from,replyTo'}),
                    capability='assistant.mail_read',resource_ref=proposal.resource_ref,purpose='mail.read')
                if value.get('conversationId')!=content.get('thread_ref'):raise CapabilityDenied('mail thread changed')
                addresses=[item.get('emailAddress',{}).get('address','').casefold() for item in value.get('replyTo',())]
                if not addresses:addresses=[value.get('from',{}).get('emailAddress',{}).get('address','').casefold()]
                if not set(address.casefold() for address in content['to'])<=set(addresses):raise CapabilityDenied('selected reply recipients changed')
            return
        if proposal.action_code in {'calendar.update','calendar.cancel'}:
            value,receipt=self._read(proposal,path='/v1.0/me/calendars/'+quote(content['calendar_ref'],safe='')+'/events/'+quote(content['event_ref'],safe='')+'?'+urlencode({'$select':'id,changeKey'}),
                capability='assistant.calendar_read',resource_ref=self.transport.account_ref,purpose='calendar.read')
            observed=value.get('@odata.etag') or receipt.get('etag')
            if observed!=content.get('etag'):raise CapabilityDenied('event version changed; a new preview is required')
        if proposal.action_code=='calendar.cancel':return
        start=datetime.fromisoformat(content['start_at'].replace('Z','+00:00'));end=datetime.fromisoformat(content['end_at'].replace('Z','+00:00'))
        if start.tzinfo is None or end<=start:raise CapabilityDenied('valid aware calendar interval required')
        path='/v1.0/me/calendars/'+quote(content['calendar_ref'],safe='')+'/calendarView?'+urlencode({'startDateTime':start.isoformat(),'endDateTime':end.isoformat(),'$top':'100','$select':'id,start,end,showAs,isCancelled'})
        value,_=self._read(proposal,path=path,capability='assistant.calendar_read',resource_ref=self.transport.account_ref,purpose='calendar.read')
        if value.get('@odata.nextLink'):raise CapabilityDenied('incomplete free/busy coverage')
        for item in value.get('value',()):
            if item.get('id')==content.get('event_ref') or item.get('isCancelled') or item.get('showAs')=='free':continue
            raise CapabilityDenied('calendar interval is busy; choose another time and preview again')

    def reconcile(self,idempotency_key):
        from .delivery import ReconciliationObservation
        def observe(receipt,proposal):
            outcome=self.adapter.reconcile(receipt)
            if outcome.status!='succeeded':return None
            return ReconciliationObservation(receipt.idempotency_key,proposal.resource_ref,receipt.content_digest,
                'delivered','graph_matching_attempt',outcome.provider_operation_ref)
        return self.executor.reconcile_confirmed_action(store=self.store,idempotency_key=idempotency_key,adapter=observe,upper_bound=self.upper_bound)

    def confirm_and_execute(self,proposal_ref,*,actor_ref,expected_version=None,expected_digest=None):
        if actor_ref!=self.root.owner_ref:raise CapabilityDenied('private owner confirmation required')
        with self.store.store.transaction() as tx:
            current=tx.conn.execute('SELECT version,payload FROM pa_actions.proposals WHERE owner=%s AND ref=%s',(self.root.owner_ref,proposal_ref)).fetchone()
        if expected_version is not None and (current is None or current['version']!=expected_version):raise CapabilityDenied('confirmation version differs')
        if expected_digest is not None and (current is None or current['payload']['content_digest']!=expected_digest):raise CapabilityDenied('confirmation digest differs')
        prior=[receipt for receipt in self.store.all() if receipt.proposal_ref==proposal_ref and current is not None and receipt.proposal_version==current['version']]
        if prior:return prior[-1]
        state=self.root.conversations.load(self.root.owner_chat_id)
        if state is None or state.current_confirmation_ref is None or state.current_confirmation_ref.proposal_ref!=proposal_ref:
            raise CapabilityDenied('one current visible exact preview required')
        from prm.storage.actions import _proposal
        with self.store.store.transaction() as tx:
            row=tx.conn.execute('SELECT payload FROM pa_actions.proposals WHERE owner=%s AND ref=%s',(self.root.owner_ref,proposal_ref)).fetchone()
        if row is None:raise CapabilityDenied('proposal unavailable')
        proposal=_proposal(row['payload'])
        if state.current_confirmation_ref.proposal_version!=str(proposal.version):raise CapabilityDenied('visible preview version changed')
        self._preflight(proposal)
        action=self.store.confirm(proposal_ref,actor_ref=actor_ref)
        if state.current_confirmation_ref.proposal_version!=str(action.proposal.version):raise CapabilityDenied('visible preview version changed')
        decision=self.root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=self.root.owner_ref,
            connection_ref=action.proposal.connection_ref,capability='assistant.action_execute',resource_ref=action.proposal.resource_ref,
            operation='write',data_class='private_connector_content',provider_ref='provider_microsoft_graph',purpose='action.execute',
            operation_ref='action_'+uuid.uuid4().hex),upper_bound=self.upper_bound)
        request=ActionExecuteRequest(decision,self.root.owner_ref,action.proposal.connection_ref,action.proposal.resource_ref,'provider_microsoft_graph')
        return self.executor.execute_confirmed_action(action,request=request,executor=self.adapter,store=self.store)
