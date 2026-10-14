"""Bounded confirmed memory retrieval and exact source/egress provenance."""
from dataclasses import replace
import hashlib,json,re,uuid
from prm.capabilities import AuthorizationRequest,CapabilityDenied
from prm.storage.postgres import StorageError,StateConflict,_canonical

STOP=frozenset('a an the and or for to of is this that what how my me about i я мне мой моя мои это для про что как и в на по пожалуйста покажи объясни память'.split())


def terms(text):return frozenset(w for w in re.findall(r'[\w]+',str(text).casefold()) if len(w)>2 and w not in STOP)


def validate_bindings(values):
    if not isinstance(values,(list,tuple)) or not 1<=len(values)<=16:raise StorageError('bounded exact memory source bindings required')
    result=[]
    for b in values:
        if (not isinstance(b,dict) or set(b)!={'namespace','ref','version','digest'} or b['namespace'] not in {'conversation','result','memory'}
            or not isinstance(b['ref'],str) or not 1<=len(b['ref'])<=128 or type(b['version'])is not int or b['version']<1
            or not isinstance(b['digest'],str) or not re.fullmatch(r'[a-f0-9]{64}',b['digest'])):raise StorageError('invalid memory source binding')
        if b not in result:result.append(dict(b))
    return result


def memory_current(tx,owner,binding,*,require_typed=False,depth=0):
    if depth>4:raise StorageError('bounded transitive memory source required')
    ref=binding.get('memory_ref',binding.get('ref'))
    tx.conn.execute("SELECT version FROM pa_runtime.object_heads WHERE owner=%s AND namespace='memory' AND object_id=%s FOR SHARE",(owner,ref)).fetchone()
    item=tx.get(owner,'memory',ref)
    if item is None or (item.version,item.digest)!=(binding['version'],binding['digest']):raise CapabilityDenied('memory changed or deleted')
    if item.payload.get('kind')=='project':
        from .source_access import project_bindings_current
        project_bindings_current(tx,owner,[{'project_ref':ref,'version':item.version,'digest':item.digest}]);return item
    receipt=item.payload.get('memory_confirmation')
    if not isinstance(receipt,dict):raise CapabilityDenied('memory confirmation provenance unavailable')
    row=tx.conn.execute('SELECT object_ref,payload,digest,expected_version,consumed FROM pa_memory.previews WHERE owner=%s AND id=%s',(owner,receipt['preview_ref'])).fetchone()
    raw={k:v for k,v in item.payload.items() if k!='memory_confirmation'}
    if (not row or not row['consumed'] or row['object_ref']!=ref or row['expected_version']+1!=item.version
        or row['digest']!=receipt['digest'] or row['payload']!=raw or _canonical(raw)[1]!=receipt['digest']):raise CapabilityDenied('memory confirmation differs')
    if require_typed and not item.payload.get('source_bindings'):raise CapabilityDenied('legacy memory source bindings unavailable')
    if item.payload.get('expires_at'):
        from .profiles import aware
        if aware(item.payload['expires_at'])<=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']:raise CapabilityDenied('memory expired')
    for b in item.payload.get('source_bindings',[]):
        parent=tx.get(owner,b['namespace'],b['ref'])
        if parent is None or (parent.version,parent.digest)!=(b['version'],b['digest']):raise CapabilityDenied('memory source changed or deleted')
        if b['namespace']=='memory':memory_current(tx,owner,b,depth=depth+1)
        if b['namespace']=='conversation':
            for origin in (parent.payload.get('telegram_envelope',{}),parent.payload.get('reply_target',{})):
                if origin.get('source_revision_ref'):
                    source=tx.get(owner,'conversation',origin['source_revision_ref'])
                    if source is None or source.version!=origin.get('source_revision'):raise CapabilityDenied('memory original source edited or deleted')
    return item


def binding_provenance(root,tx,bindings):
    from .source_access import result_provenance,result_archive_snapshots,source_current
    classes={'user_provided'};scopes={};snapshots=set()
    for b in bindings:
        item=tx.get(root.owner_ref,b['namespace'],b['ref'])
        if item is None or (item.version,item.digest)!=(b['version'],b['digest']):raise CapabilityDenied('memory source unavailable')
        if b['namespace']=='result':c,s=result_provenance(tx,root.owner_ref,item);a=result_archive_snapshots(tx,root.owner_ref,item)
        elif b['namespace']=='memory':
            item=memory_current(tx,root.owner_ref,b)
            if item.payload.get('kind')=='project':c,s,a=root.projects.provenance_in(tx,item)
            else:c=item.payload.get('source_data_classes',['user_provided']);s=item.payload.get('source_scopes',[]);a=item.payload.get('archive_snapshots',[])
        else:
            c=['user_provided'];s=[];a=[]
            from prm.storage.telegram import TelegramBindings
            root.ingress.bindings.request_current_in(tx,item)
            target=item.payload.get('reply_target')
            if target:
                parent=tx.get(root.owner_ref,'result',target['result_ref'],version=target['result_version'])
                if parent is None:raise CapabilityDenied('memory selected source unavailable')
                c,s=result_provenance(tx,root.owner_ref,parent);a=result_archive_snapshots(tx,root.owner_ref,parent)
        source_current(tx,root.registry,root.owner_ref,s,archive_snapshots=a,require_snapshot=True)
        classes.update(c);snapshots.update(a)
        for scope in s:scopes[json.dumps(scope,sort_keys=True)]=scope
    return sorted(classes),list(scopes.values()),sorted(snapshots)


def memory_text(item):
    if item.payload.get('kind')=='project':
        d=item.payload['project_context']['descriptor']
        return ' '.join(str(d.get(k,'')) for k in ('name','aliases','current_goal','current_blocker','next_proof'))
    return str(item.payload.get('text',''))


def retrieve_memory(root,tx,query,*,limit=20,typed=False):
    wanted=terms(query)
    if not wanted:return []
    # Bounded most-recent owner heads; payload metadata cannot match the query.
    rows=tx.conn.execute("SELECT h.object_id FROM pa_runtime.object_heads h JOIN pa_runtime.object_versions v USING(owner,namespace,object_id,version) WHERE h.owner=%s AND h.namespace='memory' AND v.payload->>'kind'=ANY(%s) ORDER BY v.created_at DESC,h.object_id LIMIT 128",(root.owner_ref,['note','preference','learning','project'])).fetchall()
    ranked=[]
    for row in rows:
        item=tx.get(root.owner_ref,'memory',row['object_id']);text=memory_text(item)
        overlap=wanted&terms(text)
        if not overlap:continue
        try:
            item=memory_current(tx,root.owner_ref,{'memory_ref':item.object_id,'version':item.version,'digest':item.digest},require_typed=typed)
            if item.payload.get('kind')=='project':root.projects._get_in(tx,item.object_id,item.version)
            else:binding_provenance(root,tx,item.payload.get('source_bindings',[]))
        except (StorageError,CapabilityDenied,KeyError,TypeError,ValueError):continue
        ranked.append((len(overlap)+(2 if query.casefold() in text.casefold() else 0),item))
    ranked.sort(key=lambda p:(-p[0],p[1].object_id))
    return [item for _,item in ranked[:limit]]


def context_packet(root,query,request_ref,endpoint,*,available_groups):
    """Each admitted resource/class needs its own context grant; no silent scope."""
    if not hasattr(root,'memory') or available_groups<1:return {'items':[],'groups':[],'bindings':[],'classes':[],'scopes':[],'snapshots':[]}
    with root.queue.store.transaction() as tx:items=retrieve_memory(root,tx,query,limit=4,typed=True)
    accepted=[];groups=[];bindings=[];classes=set();scopes={};snapshots=set();authorized={}
    for item in items:
        with root.queue.store.transaction() as tx:
            current=memory_current(tx,root.owner_ref,{'memory_ref':item.object_id,'version':item.version,'digest':item.digest},require_typed=True)
            if current.payload.get('kind')=='project':c,s,a=root.projects.provenance_in(tx,current)
            else:c,s,a=binding_provenance(root,tx,current.payload.get('source_bindings',[]))
        requests=[('resource_memory','user_provided')]
        for kind in c:
            if kind=='user_provided':continue
            resources={scope['resource_ref'] for scope in s if scope['data_class']==kind}
            if not resources:resources={'resource_memory'}
            requests.extend((ref,kind) for ref in sorted(resources))
        needed=[p for p in dict.fromkeys(requests) if p not in authorized]
        if len(groups)+len(needed)>available_groups:continue
        local=[]
        for resource,kind in needed:
            operation='memory_context_'+hashlib.sha256((request_ref+'\x1f'+item.object_id+'\x1f'+resource+'\x1f'+kind).encode()).hexdigest()[:40]
            decision=root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=endpoint.connection_ref,
                capability='model.context_egress',resource_ref=resource,operation='model_egress',data_class=kind,provider_ref=endpoint.provider_ref,
                purpose='dialogue.memory',operation_ref=operation),upper_bound=root.model_upper_bound)
            if not decision.allowed:break
            local.append(((resource,kind),(decision,)))
        if len(local)!=len(needed):
            for _,group in local:group[0].reservation.abandon_before_transport()
            continue
        for key,group in local:authorized[key]=group;groups.append(group)
        accepted.append({'memory_ref':item.object_id,'version':item.version,'kind':item.payload['kind'],'text':memory_text(item)[:1200],
            'lifecycle':item.payload.get('lifecycle','indexed'),'authority':'confirmed_owner_context_not_execution_authority'})
        bindings.append({'memory_ref':item.object_id,'version':item.version,'digest':item.digest})
        classes.update(c);snapshots.update(a)
        for scope in s:scopes[json.dumps(scope,sort_keys=True)]=scope
    return {'items':accepted,'groups':groups,'bindings':bindings,'classes':sorted(classes),'scopes':list(scopes.values()),'snapshots':sorted(snapshots)}


SAVE_UNDO_POLICY={'status':'proposed_inactive','scope':'unambiguous explicit new owner note','confirmation':'preview_required_until_owner_adoption',
    'undo':'exact-version explicit delete; consumed receipts/tombstones remain','exclusions':['preferences','projects','learning_state','private_source_promotion']}
