"""Owner admission focus and versioned read targets, not confirmation authority."""
from __future__ import annotations
from dataclasses import dataclass,asdict
from datetime import datetime,timedelta
import hashlib
import re
from prm.storage.postgres import PostgresStore,StorageError,StateConflict
from prm.conversation import conversation_id_for,CONVERSATION_TTL
from .deletion import lineage_lock

EXPLICIT_REF=re.compile(r'\b(?:result_job_[a-f0-9]+|response_[a-f0-9]{24})\b')
NEW={'/new','новая тема','начни новую тему'}
CONTROLS={'да','yes','подтверждаю','проверить отправку','подтвердить отправку'}


@dataclass(frozen=True)
class ConversationFocus:
    scope_ref: str
    generation: int
    request_ref: str
    object_ref: str | None
    object_version: int | None
    project_ref: str | None
    project_version: int | None
    project_label: str | None
    source_filters: tuple[str,...]
    thread_id: int | None
    expires_at: str
    schema_version: str = 'assistant.conversation_focus.v1'


class FocusStore:
    def __init__(self,root):self.root=root;self.store=root.queue.store;self.owner=root.owner_ref
    def scope(self):
        route=self.root.ingress.telegram_destination
        return 'focus_'+hashlib.sha256((route.bot_ref+'\x1f'+route.chat_id+'\x1f'+str(route.message_thread_id)).encode()).hexdigest()[:32]
    def ticket_ref(self,request_ref):return 'focus_ticket_'+hashlib.sha256(request_ref.encode()).hexdigest()[:32]
    def _lock(self,tx):
        value=int.from_bytes(hashlib.sha256((self.owner+self.scope()).encode()).digest()[:8],'big')%(2**63)
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)',(value,))
    def _dependency(self,tx,ns,parent,child):
        if tx.conn.execute("SELECT to_regclass('pa_memory.dependencies') AS meta").fetchone()['meta'] is None:return
        tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(self.owner,ns,parent,'conversation',child))
    def _current(self,tx):
        index=tx.get(self.owner,'conversation',self.scope()+'_index')
        row=tx.get(self.owner,'conversation',index.payload['slot_ref']) if index else None
        if row and datetime.fromisoformat(row.payload['expires_at'])<=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']:return None
        return row
    def admit_in(self,tx,request_ref,body):
        self._lock(tx);ticket_ref=self.ticket_ref(request_ref)
        existing=tx.get(self.owner,'conversation',ticket_ref)
        if existing is not None:return existing.payload
        current=self._current(tx);old=current.payload if current else {}
        query=body.get('query','');reset=query.strip().casefold() in NEW
        target=body.get('reply_target');explicit=EXPLICIT_REF.findall(query)
        targets=list(dict.fromkeys(explicit))
        named=re.search(r'(?i)(?:документ|результат|обзор)\s+[«"]([^»"]{1,160})[»"]',query)
        if target is None and not targets and named:
            wanted=named[1].strip().casefold()
            matches=tx.conn.execute("SELECT j.id,j.result_ref,v.payload FROM pa_jobs.jobs j JOIN pa_runtime.object_versions v ON v.owner=j.owner AND v.namespace='conversation' AND v.object_id=j.payload->>'input_ref' AND v.version=1 WHERE j.owner=%s AND j.status='completed' ORDER BY j.available_at DESC LIMIT 64",(self.owner,)).fetchall()
            for match in matches:
                original=match['payload'].get('query','').strip()
                title=original.split(' ',1)[1] if original.startswith('/') and ' ' in original else original
                if title.casefold()==wanted and match['result_ref']:targets.append(match['result_ref'])
            targets=list(dict.fromkeys(targets))
        isolated=target is not None or bool(targets)
        if target is None and len(targets)==1:target={'result_ref':targets[0],'result_version':1}
        if target is None and not isolated and not reset and not old.get('object_ref'):
            row=tx.conn.execute('SELECT payload FROM pa_conversation.states WHERE owner=%s AND id=%s AND expires>clock_timestamp()',(self.owner,conversation_id_for(self.root.owner_chat_id))).fetchone()
            refs=row['payload']['object_refs'] if row else []
            if refs:target={'result_ref':refs[0]['response_ref'],'result_version':1}
        if not isolated and not reset and old.get('object_ref'):target={'result_ref':old['object_ref'],'result_version':old['object_version']}
        generation=old.get('generation',0)+(0 if isolated else 1)
        now=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
        project_ref=old.get('project_ref') if not reset else None
        project_label=old.get('project_label') if not reset else None
        if body.get('telegram_envelope',{}).get('source_trust')!='untrusted_source':
            project=re.search(r'(?i)(?:проект(?:е|а)?|project)\s*[:«\" ]+([^»\"\n.!?,]{1,64})',query)
            if project:
                project_label=project[1].strip();project_ref='project_'+hashlib.sha256(project_label.casefold().encode()).hexdigest()[:24]
        slot_ref=old.get('scope_ref') if isolated else 'focus_slot_'+hashlib.sha256(request_ref.encode()).hexdigest()[:32]
        ticket={'schema_version':'assistant.focus_admission.v1','request_ref':request_ref,'scope_ref':slot_ref,
            'generation':generation,'isolated':isolated,'target':target,'ambiguous':len(targets)>1,
            'project_ref':project_ref,'project_version':1 if project_ref else None,'project_label':project_label,
            'source_filters':[] if reset else old.get('source_filters',[]),'thread_id':self.root.ingress.telegram_destination.message_thread_id}
        self._dependency(tx,'conversation',request_ref,ticket_ref)
        project_source=request_ref if project_ref and project_label!=old.get('project_label') else old.get('project_source_ref')
        ticket['project_source_ref']=project_source
        if project_source and project_source!=request_ref:self._dependency(tx,'conversation',project_source,ticket_ref)
        tx.put(self.owner,'conversation',ticket_ref,ticket,expected_version=0)
        if target:self._dependency(tx,'result',target['result_ref'],ticket_ref)
        if not isolated:
            focus=ConversationFocus(slot_ref,generation,request_ref,None if reset else old.get('object_ref'),
                None if reset else old.get('object_version'),project_ref,1 if project_ref else None,project_label,
                tuple(ticket['source_filters']),self.root.ingress.telegram_destination.message_thread_id,(now+CONVERSATION_TTL).isoformat())
            tx.put(self.owner,'conversation',slot_ref,{**asdict(focus),'project_source_ref':project_source},expected_version=0)
            index=tx.get(self.owner,'conversation',self.scope()+'_index')
            tx.put(self.owner,'conversation',self.scope()+'_index',{'schema_version':'assistant.focus_index.v1','slot_ref':slot_ref},expected_version=index.version if index else 0)
            self._dependency(tx,'conversation',request_ref,slot_ref)
            if project_source and project_source!=request_ref:self._dependency(tx,'conversation',project_source,slot_ref)
            if focus.object_ref:self._dependency(tx,'result',focus.object_ref,slot_ref)
            # A new owner task invalidates old confirmation aliases immediately;
            # exact confirm/reconcile requests keep their existing authority path.
            from .presentation import CONFIRM_LABELS,ACTION_CHECK
            protected=CONTROLS|{t.casefold() for t in CONFIRM_LABELS.values()}|{ACTION_CHECK.casefold()}
            if query.strip().casefold() not in protected and not query.startswith(('/actconfirm','/actreconcile','/memoryconfirm')):
                cid=conversation_id_for(self.root.owner_chat_id);self.root._conversations._lock(tx.conn,cid)
                tx.conn.execute("UPDATE pa_conversation.states SET version=version+1,payload=jsonb_set(jsonb_set(payload,'{current_confirmation_ref}','null'::jsonb),'{visible_confirmation_refs}','[]'::jsonb) WHERE owner=%s AND id=%s",(self.owner,cid))
        return ticket
    def ticket(self,request_ref):
        item=self.store.get(self.owner,'conversation',self.ticket_ref(request_ref));return item.payload if item else None
    def current_in(self,tx,request_ref):
        ticket=tx.get(self.owner,'conversation',self.ticket_ref(request_ref));current=self._current(tx)
        return bool(ticket and current and not ticket.payload['isolated'] and current.payload['request_ref']==ticket.payload.get('foreground_ref',request_ref) and current.payload['generation']==ticket.payload['generation'])
    def record_plan(self,request_ref,plan,guard):
        import json
        with self.store.transaction() as tx:
            lineage_lock(tx.conn,self.owner);self._lock(tx);guard()
            ref='task_plan_'+hashlib.sha256(request_ref.encode()).hexdigest()[:32]
            payload={'schema_version':'assistant.task_plan.v1','request_ref':request_ref,'plan':json.loads(json.dumps(plan.to_dict()))}
            old=tx.get(self.owner,'conversation',ref)
            if old and old.payload!=payload:raise StateConflict('admitted task plan changed')
            if old is None:tx.put(self.owner,'conversation',ref,payload,expected_version=0)
            self._dependency(tx,'conversation',request_ref,ref)
            if self.current_in(tx,request_ref) and plan.source_filters:
                row=self._current(tx)
                tx.put(self.owner,'conversation',row.object_id,{**row.payload,'source_filters':list(plan.source_filters)},expected_version=row.version)

    def inherit_in(self,tx,parent_ref,child_ref):
        ticket=tx.get(self.owner,'conversation',self.ticket_ref(parent_ref))
        if ticket is None:return
        value={**ticket.payload,'request_ref':child_ref,'foreground_ref':ticket.payload.get('foreground_ref',parent_ref)}
        ref=self.ticket_ref(child_ref)
        old=tx.get(self.owner,'conversation',ref)
        if old is not None and old.payload!=value:raise StateConflict('child focus admission differs')
        if old is None:tx.put(self.owner,'conversation',ref,value,expected_version=0)
        self._dependency(tx,'conversation',child_ref,ref)
        self._dependency(tx,'conversation',parent_ref,child_ref)

    def complete_in(self,tx,lease,ref,result):
        self._lock(tx)
        if not self.current_in(tx,lease.payload['input_ref']):return
        row=self._current(tx);value={**row.payload,'object_ref':ref,'object_version':1}
        tx.put(self.owner,'conversation',row.object_id,value,expected_version=row.version)
        self._dependency(tx,'result',ref,row.object_id)
    def resolve(self,ticket,*,guard):
        if ticket.get('ambiguous'):raise StorageError('ambiguous focus target')
        target=ticket.get('target')
        if not target:return None
        with self.store.transaction() as tx:
            lineage_lock(tx.conn,self.owner);guard()
            item=tx.get(self.owner,'result',target['result_ref'],version=target['result_version'])
            if item is None:raise StorageError('focus result version unavailable')
            from .source_access import source_current,result_provenance
            classes,scopes=result_provenance(tx,self.owner,item)
            source_current(tx,self.root.registry,self.owner,scopes)
            rows=tx.conn.execute("SELECT j.payload FROM pa_jobs.jobs j JOIN pa_runtime.object_versions v ON v.owner=j.owner AND v.namespace='result' AND v.object_id=j.result_ref AND v.version=1 WHERE j.owner=%s AND (j.result_ref=%s OR (v.payload->'payload'->'conversation'->'response_refs') ? %s)",(self.owner,target['result_ref'],target['result_ref'])).fetchall()
            for row in rows:self.root.queue._input(tx,self.owner,row['payload'])
            return item,classes,scopes


class FencedConversations:
    """Short mutations share the admission lock; model I/O never holds it."""
    def __init__(self,root,request_ref,lease):self.root,self.request_ref,self.lease=root,request_ref,lease;self.store=root._conversations
    def __getattr__(self,name):
        method=getattr(self.store,name)
        if name not in {'load','start','active_or_start','begin_new_topic','record_response','offer_confirmation','resolve_plain_yes','start_request','finish_request','cancel','is_cancelled','history','history_for_model','user_prompts_for_model'}:return method
        def scoped(chat_id,*args,**kwargs):
            with self.root.queue.store.transaction() as tx:
                lineage_lock(tx.conn,self.root.owner_ref);self.root.focus._lock(tx)
                self.root.queue._fenced(tx,self.lease)
                main=self.root.focus.current_in(tx,self.request_ref)
                target=chat_id if main else self.request_ref
                if name in {'history','history_for_model','user_prompts_for_model'}:return method(target,*args,**kwargs)
                return self.store._run_in(tx,name,target,*args,**kwargs)
        return scoped
