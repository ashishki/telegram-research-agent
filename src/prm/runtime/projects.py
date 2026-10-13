"""Explicitly confirmed project memory and source-bound applicability."""
from datetime import datetime,timezone
import json,re,hashlib
from prm.storage.postgres import StorageError,StateConflict
from prm.capabilities import CapabilityDenied
from assistant.project_portfolio_context import validate_project_portfolio_context,project_action_recommendation_allowed
from .profiles import aware


def _alias(value):return ' '.join(value.casefold().split())


def validate_context(value):
    fields={'descriptor','reviewed_at','expires_at','source_bindings','relationships'}
    if not isinstance(value,dict) or set(value)!=fields:raise StorageError('complete versioned project context required')
    descriptor=value['descriptor']
    if not isinstance(descriptor,dict) or len(json.dumps(value).encode())>24000:raise StorageError('bounded project descriptor required')
    try:descriptor=validate_project_portfolio_context(descriptor)
    except (ValueError,TypeError):raise StorageError('project portfolio descriptor invalid') from None
    if descriptor['owner_confirmation_status']!='unknown':raise StorageError('only confirmation can attest a project')
    if aware(value['reviewed_at'])>=aware(value['expires_at']):raise StorageError('project review validity required')
    if len(descriptor['aliases'])>16 or any(not isinstance(x,str) or not 0<len(x)<=128 for x in descriptor['aliases']):raise StorageError('bounded exact project aliases required')
    bindings=value['source_bindings'];relationships=value['relationships']
    if not isinstance(bindings,list) or not 1<=len(bindings)<=16 or not isinstance(relationships,list) or len(relationships)>16:raise StorageError('bounded project provenance required')
    for b in bindings:
        if not isinstance(b,dict) or set(b)!={'namespace','ref','version','digest'} or b['namespace'] not in {'conversation','result','memory'} or type(b['version'])is not int or b['version']<1 or not isinstance(b['ref'],str) or not re.fullmatch('[a-f0-9]{64}',b['digest']):raise StorageError('exact project source binding required')
    for r in relationships:
        if not isinstance(r,dict) or set(r)!={'evidence_ref','evidence_version','evidence_digest','quote','relation','experiment','reject_if'} or type(r['evidence_version'])is not int or r['evidence_version']<1 or any(not isinstance(r[k],str) or not 0<len(r[k])<=2000 for k in ('evidence_ref','quote','relation','experiment','reject_if')) or not re.fullmatch('[a-f0-9]{64}',r['evidence_digest']):raise StorageError('bounded explicit source relationship required')
    return {**value,'descriptor':descriptor}


class ProjectRuntime:
    def __init__(self,root):self.root=root;self.memory=root.memory;self.store=root.queue.store
    def _live(self,tx,binding):
        item=tx.get(self.root.owner_ref,binding['namespace'],binding['ref'])
        if item is None or item.version!=binding['version'] or item.digest!=binding['digest']:raise StorageError('project source changed or deleted')
        if binding['namespace']=='result':
            from .source_access import result_provenance,source_current
            _,scopes=result_provenance(tx,self.root.owner_ref,item);source_current(tx,self.root.registry,self.root.owner_ref,scopes)
        return item
    def preview(self,*,object_ref,context,expected_version=0,**actor):
        context=validate_context(context)
        if any(b['namespace']=='memory' and b['ref']==object_ref for b in context['source_bindings']):raise StorageError('project cannot depend on its own replaced version')
        return self.memory.preview(object_ref=object_ref,text=context['descriptor']['name'],source_refs=tuple(b['ref'] for b in context['source_bindings']),kind='project',project_context=context,expected_version=expected_version,**actor)
    def validate_in(self,tx,context,object_ref):
        context=validate_context(context)
        for binding in context['source_bindings']:self._live(tx,binding)
        for relation in context['relationships']:
            evidence=self._live(tx,{'namespace':'result','ref':relation['evidence_ref'],'version':relation['evidence_version'],'digest':relation['evidence_digest']})
            text=evidence.payload.get('text',evidence.payload.get('display_text',''))
            if relation['quote'] not in text:raise StorageError('project relationship quote not supported')
        aliases={_alias(x) for x in [context['descriptor']['name'],*context['descriptor']['aliases']]}
        rows=tx.conn.execute("SELECT object_id FROM pa_runtime.object_heads WHERE owner=%s AND namespace='memory' AND object_id<>%s ORDER BY object_id LIMIT 1000",(self.root.owner_ref,object_ref)).fetchall()
        for row in rows:
            other=tx.get(self.root.owner_ref,'memory',row['object_id'])
            if other and other.payload.get('kind')=='project':
                d=other.payload['project_context']['descriptor']
                if aliases&{_alias(x) for x in [d['name'],*d['aliases']]}:raise StateConflict('project aliases are ambiguous')
        return context
    def _get_in(self,tx,object_ref,version=None,allow_stale=False):
        item=tx.get(self.root.owner_ref,'memory',object_ref)
        if item is None or item.payload.get('kind')!='project' or version is not None and item.version!=version:raise StorageError('current project version unavailable')
        context=item.payload['project_context'];proof=item.payload.get('project_confirmation')
        if not proof:raise StorageError('confirmed project provenance unavailable')
        row=tx.conn.execute('SELECT consumed,digest,object_ref,payload FROM pa_memory.previews WHERE owner=%s AND id=%s',(self.root.owner_ref,proof['preview_ref'])).fetchone()
        if not row or not row['consumed'] or row['object_ref']!=object_ref or row['digest']!=proof['digest'] or row['payload'].get('project_context')!={**context,'descriptor':{**context['descriptor'],'owner_confirmation_status':'unknown'}}:raise StorageError('project confirmation does not bind exact context')
        now=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
        if not allow_stale and not aware(context['reviewed_at'])<=now<aware(context['expires_at']):raise StorageError('project context needs owner recheck')
        for binding in context['source_bindings']:self._live(tx,binding)
        return item
    def get(self,object_ref,*,version=None,allow_stale=False,**actor):
        self.memory._owner(**actor)
        with self.store.transaction() as tx:return self._get_in(tx,object_ref,version,allow_stale)
    def list_in(self,tx):
        rows=tx.conn.execute("SELECT object_id FROM pa_runtime.object_heads WHERE owner=%s AND namespace='memory' ORDER BY object_id LIMIT 1000",(self.root.owner_ref,)).fetchall()
        output=[]
        for row in rows:
            try:output.append(self._get_in(tx,row['object_id']))
            except (StorageError,CapabilityDenied):continue
        return output
    def resolve_named_in(self,tx,name):
        found=[i for i in self.list_in(tx) if _alias(name) in {_alias(x) for x in [i.payload['project_context']['descriptor']['name'],*i.payload['project_context']['descriptor']['aliases']]}]
        if len(found)>1:raise StorageError('ambiguous project alias')
        return found[0] if found else None
    def applicability(self,*,object_ref,version,evidence_ref,**actor):
        self.memory._owner(**actor)
        with self.store.transaction() as tx:
            item=self._get_in(tx,object_ref,version);context=item.payload['project_context'];descriptor=context['descriptor']
            relations=[r for r in context['relationships'] if r['evidence_ref']==evidence_ref]
            relation=relations[0] if len(relations)==1 else None
            evidence=self._live(tx,{'namespace':'result','ref':relation['evidence_ref'],'version':relation['evidence_version'],'digest':relation['evidence_digest']}) if relation else None
            allowed=project_action_recommendation_allowed(descriptor,direct_evidence=relation is not None)
            if relation and relation['quote'] not in evidence.payload.get('text',evidence.payload.get('display_text','')):allowed=False
            from .source_access import result_provenance
            classes,scopes=result_provenance(tx,self.root.owner_ref,evidence) if evidence else (('user_provided',),())
            return {'project_ref':item.object_id,'project_version':item.version,'goal':descriptor['current_goal'],'blocker':descriptor['current_blocker'],
                'status':'candidate_experiment' if allowed else 'weak_watch','action_recommendation':allowed,
                'relationship':relation if allowed else None,'next_proof':descriptor['next_proof'] if allowed else None,
                'cost':'unknown','execution_authority':False,'human_usefulness':None,'source_data_classes':list(classes),'source_scopes':list(scopes)}
    def service(self,request,request_ref,guard):
        actor={'chat_id':request.chat_id,'actor_id':request.actor_id,'owner_chat_id':request.owner_chat_id};self.memory._owner(**actor);guard()
        command,_,arg=request.query.partition(' ')
        if command=='/projectpreview':
            value=json.loads(arg)
            reference=self.preview(object_ref=value['object_ref'],context=value['context'],expected_version=value.get('version',0),**actor)
            return {'status':'preview','text':'Предпросмотр проекта: '+json.dumps(value['context'],ensure_ascii=False)+'\n/projectconfirm '+reference,'preview_ref':reference,'source_data_class':'user_provided'}
        if command=='/projectconfirm':
            item=self.memory.confirm(arg,**actor)
            if item.payload['kind']!='project':raise StorageError('project confirmation required')
            return {'status':'saved','text':'Проект сохранён: '+item.payload['project_context']['descriptor']['name'],'source_data_class':'user_provided','source_memory_refs':[item.object_id]}
        if command=='/projectapply':value=json.loads(arg);output=self.applicability(**value,**actor);refs=[value['object_ref']]
        else:
            with self.store.transaction() as tx:
                items=self.list_in(tx) if command=='/projects' or not arg else [self.resolve_named_in(tx,arg)]
                items=[i for i in items if i]
            output=[{'project_ref':i.object_id,'version':i.version,**{k:str(v)[:600] for k,v in i.payload['project_context']['descriptor'].items() if k in {'name','status','current_goal','current_blocker','next_proof'}}} for i in items[:3]];refs=[i.object_id for i in items[:3]]
        classes=output.get('source_data_classes',['user_provided']) if isinstance(output,dict) else ['user_provided']
        scopes=output.get('source_scopes',[]) if isinstance(output,dict) else []
        return {'status':'found' if output else 'not_found','text':json.dumps(output,ensure_ascii=False),'source_data_class':classes[0],'source_data_classes':classes,'source_scopes':scopes,'source_memory_refs':refs}
