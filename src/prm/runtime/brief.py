"""Weekly selected sources -> immutable Brief -> application and delivery."""
from dataclasses import dataclass,replace,asdict
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from prm.briefs import BriefBuildRequest,BriefWindow,CoverageSource,build_brief_document,render_brief_document
from prm.contracts import OperatorRequest
from prm.storage.postgres import StorageError


def brief_window(timezone_name,*,end_at=None,period_mode='rolling',generated_at=None):
    zone=ZoneInfo(timezone_name);now=generated_at or datetime.now(timezone.utc)
    end=(end_at or now)
    if end.tzinfo is None or now.tzinfo is None:raise StorageError('aware Brief reference time required')
    end=end.astimezone(zone)
    if period_mode=='calendar_week':
        from datetime import time
        monday=end.date()-timedelta(days=end.weekday())
        end=datetime.combine(monday,time(),zone);start=datetime.combine(monday-timedelta(days=7),time(),zone)
    elif period_mode=='rolling':start=(end.astimezone(timezone.utc)-timedelta(days=7)).astimezone(zone)
    else:raise StorageError('explicit rolling or calendar_week period required')
    return BriefWindow(timezone_name,start,end,now)


@dataclass(frozen=True)
class BriefSourceHook:
    source_ref: str
    authorization_request: object
    collector: object
    upper_bound: int | None


class BriefRuntime:
    def __init__(self,root,*,source_hooks=(),editorial=None):
        if len(source_hooks)>16:raise StorageError('bounded selected Brief sources required')
        self.root,self.source_hooks=root,tuple(source_hooks)
        self.editorial=editorial or (RuntimeBriefEditorial(root) if root.model_endpoint is not None else None)

    def build(self,*,topic,timezone_name,end_at=None,previous_document=None,comparison_document=None,period_mode='rolling',window_override=None):
        window=window_override or brief_window(timezone_name,end_at=end_at,period_mode=period_mode)
        if window.timezone!=timezone_name or window.end_at-window.start_at>__import__('datetime').timedelta(days=8):raise StorageError('bounded exact Brief window required')
        from prm.source_contracts import SourceResource,SourceBatch,EvidenceBundle,normalize_source_batch
        evidence=[];coverage=[];limits=[];used_scopes=[];batches=[]
        for hook in self.source_hooks:
            if hook.authorization_request.owner_ref!=self.root.owner_ref or hook.authorization_request.resource_ref!=hook.source_ref:
                raise StorageError('Brief hook source scope differs')
            import uuid
            decision=self.root.registry.authorize_and_reserve(replace(hook.authorization_request,operation_ref='briefsource_'+uuid.uuid4().hex),upper_bound=hook.upper_bound)
            if not decision.allowed:
                coverage.append(CoverageSource(hook.source_ref,'unavailable','scope denied'));continue
            try:
                observed=self.root.registry.execute_reserved((decision.reservation,),lambda:hook.collector(window))
                resource=SourceResource(self.root.owner_ref,hook.source_ref,'archive' if hook.authorization_request.data_class=='private_archive' else 'local',hook.authorization_request.data_class,connection_ref=hook.authorization_request.connection_ref)
                if type(observed)is SourceBatch:
                    if any(r.owner_ref!=resource.owner_ref or r.resource_ref!=resource.resource_ref or r.connection_ref!=resource.connection_ref or r.data_class!=resource.data_class for r in observed.selected_resources):raise StorageError('Brief selected resource/owner differs')
                    batch=observed
                else:batch=normalize_source_batch(observed,resource,checked_at=datetime.now(timezone.utc))
                if any(item.get('source_data_class',resource.data_class)!=resource.data_class for item in batch):raise StorageError('collector cannot relabel source privacy')
                if any(item.get('local_source_provenance') and item.get('source_owner_ref')!=self.root.owner_ref for item in batch):
                    raise StorageError('Brief personal source owner differs')
                batches.append(batch)
                evidence.extend(batch);coverage.append(CoverageSource(hook.source_ref,'checked' if batch.completeness=='complete' else 'partial',batch.reason))
                used_scopes.append(asdict(replace(hook.authorization_request,operation_ref=None)))
            except Exception:
                # Only a still-unprepared reservation can be abandoned. A
                # possibly processed collector retains its unknown fence/cost.
                decision.reservation.abandon_before_transport()
                coverage.append(CoverageSource(hook.source_ref,'unavailable','collection unavailable'))
        received=sum(len(b) for b in batches)
        # Retain at most2048 candidate records across all selected sources. Read
        # observations remain separate, including local cap omissions.
        if received>2048:
            groups=[sorted(b.items,key=lambda r:({'critical':0,'high':1,'medium':2,'low':3}.get(r.payload.get('importance'),4),r.external_ref)) for b in batches]
            kept=[[] for _ in batches];index=0
            while sum(map(len,kept))<2048 and any(index<len(g) for g in groups):
                for n,group in enumerate(groups):
                    if index<len(group) and sum(map(len,kept))<2048:kept[n].append(group[index])
                index+=1
            batches=[replace(b,items=tuple(kept[n]),completeness='partial' if len(kept[n])<len(b) else b.completeness,
                omitted_count=b.omitted_count+len(b)-len(kept[n]) if b.omitted_count is not None else None,
                reason='candidate_global_cap' if len(kept[n])<len(b) else b.reason,
                continuation='received_selection_cap' if len(kept[n])<len(b) else b.continuation) for n,b in enumerate(batches)]
            limits.append('candidate_global_cap')
        from prm.briefs import _evidence_from_mapping
        eligible=set()
        for batch in batches:
            for record in batch.items:
                try:_evidence_from_mapping(record.payload,window=window)
                except ValueError:continue
                eligible.add(record.evidence_ref)
        from prm.event_clusters import cluster_events
        from prm.brief_selection import select_events,event_signals,build_attention_editorial,admit_editorial_wording,brief_ref
        selection_digest=self.root.archive_selection.digest if self.root.archive_selection else None
        history=self.root.briefs.event_history(topic=topic,selection_digest=selection_digest) if hasattr(self.root.briefs,'event_history') else ()
        projects=[]
        if hasattr(self.root,'projects'):
            with self.root.queue.store.transaction() as tx:
                projects=self.root.projects.list_in(tx)[:3]
                bridge=self.root.projects.bridge_brief_in(tx,[r for b in batches for r in b.items if r.evidence_ref in eligible],projects)
            if bridge:
                from prm.source_contracts import SourceRecord
                new=[];new_eligible=set()
                for batch in batches:
                    converted=[]
                    for old in batch.items:
                        record=SourceRecord.from_item(bridge[old.evidence_ref],old.resource) if old.evidence_ref in bridge else old
                        converted.append(record)
                        if old.evidence_ref in eligible:new_eligible.add(record.evidence_ref)
                    new.append(replace(batch,items=tuple(converted)))
                batches=new;eligible=new_eligible
        records=list({r.evidence_ref:r for b in batches for r in b.items if r.evidence_ref in eligible}.values())
        events=cluster_events(records,history=history)
        rules=self.root.feedback.rules() if hasattr(self.root,'feedback') else ()
        affected=[event_signals(e,projects=projects,rules=rules)[1]['feedback'] for e in events]
        memory_bindings=list({(b['memory_ref'],b['version'],b['digest']):b for signal in affected for b in signal['rule_bindings']}.values())
        decisions=select_events(events,projects=projects,rules=rules,maximum=20)
        baseline=EvidenceBundle.select(tuple(batches),maximum_items=0,eligible_refs=frozenset(eligible)) if batches else None
        bundle=replace(baseline,selected=tuple(row[1] for row in decisions)) if baseline else None
        if bundle:
            evidence=[r.payload for r in bundle.selected]
            if bundle.model_omitted_count:
                limits.append('model_packet_omitted:'+str(bundle.model_omitted_count))
                coverage=[replace(c,state='partial',reason='model_packet_bounded') if c.state=='checked' else c for c in coverage]
            if bundle.conflict_count:limits.append('conflicting_source_versions:'+str(bundle.conflict_count))
            if bundle.excluded_refs:limits.append('invalid_or_outside_window_candidates:'+str(len(bundle.excluded_refs)))
        if not self.source_hooks:limits.append('selected_sources_unavailable')
        request=BriefBuildRequest(topic,window,tuple(evidence),self.root.owner_ref,tuple(coverage),tuple(limits),
            previous_document=previous_document,comparison_document=comparison_document,period_basis='previous_calendar_week' if period_mode=='calendar_week' else 'rolling_seven_days')
        document=build_brief_document(request)
        classes={resource.data_class for batch in batches for resource in batch.selected_resources}
        snapshots=tuple({b.watermark for b in batches if b.watermark and any(r.kind=='archive' for r in b.selected_resources)}) if self.root.archive_selection else ()
        # Editorial prose may improve explanation, but cannot decide source
        # scope, project identity, novelty or optional continuation authority.
        local_editorial=build_attention_editorial(document,decisions)
        offered=None
        # Confirmed rules affect the packet including excluded candidates.
        # Keep rule-derived editorial local: no derived private selection is
        # sent to a model under only the original source-hook authority.
        if self.editorial is not None and not memory_bindings:
            editorial=self.editorial(document,data_classes=classes,source_scopes=used_scopes,archive_snapshots=snapshots) if type(self.editorial)is RuntimeBriefEditorial else self.editorial(document)
            if editorial is not None:offered=editorial
        document=build_brief_document(replace(request,editorial=admit_editorial_wording(local_editorial,offered,document.evidence)))
        included={a.evidence_ref for s in document.editorial.stories for a in s.anchors}
        required={brief_ref(r) for e,r,s in decisions if e.conflict or s['importance'] in {'critical','high'}}
        if required-included:
            request=replace(request,limitations=tuple(dict.fromkeys((*request.limitations,'editorial_required_event_unrepresented'))),
                coverage=tuple(replace(c,state='partial',reason='editorial_required_event_unrepresented') if c.state=='checked' else c for c in request.coverage))
            document=build_brief_document(replace(request,editorial=document.editorial))
        dependencies=[r.payload['dependency_ref'] for b in batches for r in b.items if r.payload.get('dependency_ref')]
        used_projects={s['project']['project_ref'] for _,r,s in decisions if s['project'] and brief_ref(r) in included}
        if used_projects:
            with self.root.queue.store.transaction() as tx:
                for project in projects:
                    if project.object_id not in used_projects:continue
                    current=self.root.projects._get_in(tx,project.object_id,project.version)
                    c,s,a=self.root.projects.provenance_in(tx,current);classes.update(c)
                    used_scopes.extend(s);snapshots=tuple(set(snapshots)|set(a))
                    dependencies.append({'namespace':'memory','object_ref':project.object_id,'version':project.version,'digest':project.digest})
        used_scopes=list({__import__('json').dumps(s,sort_keys=True):s for s in used_scopes}.values())
        if not hasattr(self.root.briefs,'pending_coverage'):self.root.briefs.pending_coverage={}
        self.root.briefs.pending_coverage[document.content_digest]=bundle.metadata() if bundle else {'schema_version':'assistant.evidence_bundle.v1','received_count':0,'candidate_count':0,'selected_count':0,'cited_count':None,'batches':[]}
        self.root.briefs.pending_coverage[document.content_digest]['enumeration_received_count']=received
        self.root.briefs.pending_coverage[document.content_digest]['candidate_global_cap']=2048
        self.root.briefs.pending_coverage[document.content_digest]['document_evidence_count']=len(document.evidence)
        self.root.briefs.pending_coverage[document.content_digest]['event_count']=len(events)
        self.root.briefs.pending_coverage[document.content_digest]['event_duplicate_count']=len(records)-len(events)
        if not hasattr(self.root.briefs,'pending_events'):self.root.briefs.pending_events={}
        project_bindings=[{'project_ref':p.object_id,'version':p.version,'digest':p.digest} for p in projects if p.object_id in used_projects]
        if memory_bindings:
            from .memory_context import binding_provenance,memory_current
            with self.root.queue.store.transaction() as tx:
                for b in memory_bindings:
                    item=memory_current(tx,self.root.owner_ref,b)
                    c,s,a=binding_provenance(self.root,tx,item.payload.get('source_bindings',[]));classes.update(c);used_scopes.extend(s);snapshots=tuple(set(snapshots)|set(a))
                    dependencies.append({'namespace':'memory','object_ref':b['memory_ref'],'version':b['version'],'digest':b['digest']})
            used_scopes=list({__import__('json').dumps(s,sort_keys=True):s for s in used_scopes}.values())
        if not hasattr(self.root.briefs,'pending_memory_bindings'):self.root.briefs.pending_memory_bindings={}
        self.root.briefs.pending_memory_bindings[document.content_digest]=memory_bindings
        if not hasattr(self.root.briefs,'pending_project_bindings'):self.root.briefs.pending_project_bindings={}
        self.root.briefs.pending_project_bindings[document.content_digest]=project_bindings
        self.root.briefs.pending_events[document.content_digest]={'selection_digest':selection_digest,
            'events':[{**e.metadata(),'editorial_included':brief_ref(r) in included} for e,r,_ in decisions],
            'signals':[{k:v for k,v in s.items() if k!='project'}|{'event_ref':e.event_ref,'revision':e.revision,
                'brief_evidence_ref':brief_ref(r),'editorial_included':brief_ref(r) in included,
                'project_binding':None if not s['project'] else {k:s['project'][k] for k in ('project_ref','version','digest')}} for e,r,s in decisions]}
        cluster_refs={r.evidence_ref:(e.event_ref,e.revision) for e in events for r in e.records}
        selected={r.evidence_ref for r in bundle.selected} if bundle else set()
        editorial_selected={r.evidence_ref for _,r,_ in decisions if brief_ref(r) in included}
        if not hasattr(self.root.briefs,'pending_inventory'):self.root.briefs.pending_inventory={}
        self.root.briefs.pending_inventory[document.content_digest]=[{**r.metadata(),'source_url':r.payload.get('source_url'),
            'event_ref':cluster_refs.get(r.evidence_ref,(None,None))[0],'event_revision':cluster_refs.get(r.evidence_ref,(None,None))[1],
            'packet_selected':r.evidence_ref in selected,'editorial_included':r.evidence_ref in editorial_selected,
            'selected':r.evidence_ref in editorial_selected,'reason':'selected' if r.evidence_ref in editorial_selected else 'editorial_omitted' if r.evidence_ref in selected else 'ineligible' if r.evidence_ref not in eligible else 'event_duplicate' if any(r in e.records and len(e.records)>1 and any(p.evidence_ref in selected for p in e.records) for e in events) else 'model_packet_limit'} for b in batches for r in b.items]
        self.root.briefs.pending_dependencies[document.content_digest]=dependencies
        self.root.briefs.pending_classes[document.content_digest]=tuple(sorted(classes)) or ('user_provided',)
        self.root.briefs.pending_scopes[document.content_digest]=used_scopes
        if not hasattr(self.root.briefs,'pending_snapshots'):self.root.briefs.pending_snapshots={}
        self.root.briefs.pending_snapshots[document.content_digest]=list(snapshots)
        return document

    def answer(self,*,topic,timezone_name,end_at=None,period_mode='rolling',prepared_document=None):
        from prm.contracts import AssistantResult
        from prm.capabilities import CapabilityDenied
        document=prepared_document or self.build(topic=topic,timezone_name=timezone_name,end_at=end_at,period_mode=period_mode)
        ref=self.root.task_context.get();original=self.root.queue.store.get(self.root.owner_ref,'conversation',ref) if ref else None
        if original is not None:
            if not hasattr(self.root.briefs,'pending_original_inputs'):self.root.briefs.pending_original_inputs={}
            self.root.briefs.pending_original_inputs[document.content_digest]=[{'namespace':'conversation','ref':original.object_id,'version':original.version,'digest':original.digest}]
        # Publish the immutable source-bound manifest first; atomic view writing
        # then links text/origin to it before releasing the lineage transaction.
        # Both initial weekly and explicit refresh use this native path.
        request_ref=ref or document.brief_id+':'+str(document.version)
        try:
            self.root.briefs.persist_document(document,chat_id=self.root.owner_chat_id,actor_id=self.root.owner_chat_id,owner_chat_id=self.root.owner_chat_id)
            document,manifest=self.root.documents.load(document.brief_id,document.version)
            result=self.root.documents.remember_view(request_ref,document,manifest,render_brief_document(document,view='telegram'),view='telegram',
                extra={'brief_document_created':True,'automatic_job_created':False,'notification_sent':False})
        except (StorageError,CapabilityDenied):
            return AssistantResult(request_ref,'source_unavailable','brief','Обзор не опубликован: сохранённый контекст или исходный запрос изменён. Можно собрать актуальный обзор заново.',
                payload={'source_data_class':'user_provided','source_data_classes':['user_provided']})
        classes=self.root.briefs.pending_classes.get(document.content_digest,('private_archive','private_connector_content'))
        snapshots=self.root.briefs.pending_snapshots.get(document.content_digest,[])
        inventory_hint='\nМатериалы выборки: /briefmaterials '+document.brief_id+' '+str(document.version)+' 0'
        prompt=self.root.feedback.optional_prompt() if hasattr(self.root,'feedback') else ''
        return replace(result,text=result.text+inventory_hint+('\n'+prompt if prompt else ''),payload={**result.payload,
            'document_binding':{'brief_id':document.brief_id,'version':document.version,'content_digest':document.content_digest,'story_number':None},
            'brief_inventory_hint':inventory_hint.strip(),'weekly_feedback_prompt':prompt,
            'archive_snapshots':snapshots,'source_data_classes':list(classes),'source_data_class':classes[0],'source_scopes':self.root.briefs.pending_scopes.get(document.content_digest,[]),'source_coverage':self.root.briefs.pending_coverage.get(document.content_digest)})

    def materials(self,*,brief_id,version,offset=0,limit=20,guard=lambda:None):
        if type(version)is not int or version<1 or type(offset)is not int or not 0<=offset<=2048 or type(limit)is not int or not 1<=limit<=20:raise StorageError('bounded exact Brief material request required')
        from .source_access import source_current
        store=self.root.briefs.store;owner=self.root.owner_ref
        with store.transaction() as tx:
            from .deletion import lineage_lock
            lineage_lock(tx.conn,owner);guard()
            parent=self.root.briefs._document_ref(brief_id);manifest=tx.get(owner,'result',parent,version=version)
            if manifest is None or manifest.payload.get('brief_id')!=brief_id:raise StorageError('Brief version unavailable')
            scopes=manifest.payload.get('source_scopes',[]);snapshots=manifest.payload.get('archive_snapshots',[])
            from .source_access import project_bindings_current
            project_bindings_current(tx,owner,manifest.payload.get('project_bindings',[]))
            from .source_access import memory_bindings_current
            memory_bindings_current(tx,owner,manifest.payload.get('memory_bindings',[]))
            source_current(tx,self.root.registry,owner,scopes,archive_snapshots=snapshots,require_snapshot=True)
            pages=manifest.payload.get('material_pages',[]);rows=[];seen=0;dependencies=[parent]
            for page in pages:
                if seen+page['count']<=offset:seen+=page['count'];continue
                item=tx.get(owner,'result',page['ref'],version=1)
                if item is None or item.digest!=page['digest'] or item.payload['parent_ref']!=parent or item.payload['brief_version']!=version:raise StorageError('Brief inventory changed or unavailable')
                start=max(0,offset-seen);rows.extend(item.payload['rows'][start:start+limit-len(rows)]);dependencies.append(page['ref']);seen+=page['count']
                if len(rows)>=limit:break
            lines=[('В обзоре' if row['selected'] else 'Вне обзора ('+row['reason']+')')+': '+str(row.get('source_url') or row['external_ref']) for row in rows]
            total=sum(p['count'] for p in pages)
            text='Материалы сохранённой выборки: '+str(total)+'. '+('Перечень пуст.' if not lines else '\n'+'\n'.join(lines))
            if offset+len(rows)<total:text+='\nДальше: /briefmaterials '+brief_id+' '+str(version)+' '+str(offset+len(rows))
            return {'status':'read','text':text,'materials':rows,'inventory_count':total,
                'source_data_classes':manifest.payload.get('source_data_classes',['user_provided']),
                'source_scopes':scopes,'archive_snapshots':snapshots,'source_result_refs':dependencies}


class RuntimeBriefEditorial:
    def __init__(self,root):self.root=root
    def __call__(self,document,*,data_classes=None,source_scopes=(),archive_snapshots=()):
        import hashlib,json,uuid
        from prm.capabilities import AuthorizationRequest
        from prm.brief_editorial import BriefEditorial
        from .model import ScopedModelClient
        if not document.evidence:return None
        root=self.root;endpoint=root.endpoint_for('brief_editorial');operation='briefeditorial_'+uuid.uuid4().hex;groups=[]
        if endpoint is None:return None
        scopes=[('model.generate',root.model_resource_ref,'user_provided','answer.request')]
        selected=set(data_classes or {'private_archive'})
        if not selected<= {'private_archive','private_connector_metadata','private_connector_content','user_provided','public'}:raise StorageError('unknown Brief source data class')
        for data_class in sorted(selected):
            scopes.append(('model.context_egress',root.archive_resource_ref if data_class=='private_archive' else 'resource_personal_brief',
                           data_class,'brief.editorial_archive' if data_class=='private_archive' else 'brief.editorial_personal'))
        for index,(capability,resource,data_class,purpose) in enumerate(scopes):
            decision=root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=endpoint.connection_ref,
                capability=capability,resource_ref=resource,operation='model_egress',data_class=data_class,provider_ref=endpoint.provider_ref,
                purpose=purpose,operation_ref=operation+'_'+str(index)),upper_bound=root.model_upper_bound)
            if not decision.allowed:
                for group in groups:group[0].reservation.abandon_before_transport()
                return None
            groups.append((decision,))
        sources=[{'evidence_ref':item.evidence_ref,'title':item.title,'summary':item.summary,'source_ref':item.source_ref} for item in document.evidence]
        client=root.scoped_client(endpoint,groups=groups,task_ref=document.brief_id,attempt_ref=operation,history=({'role':'user','content':'Untrusted selected evidence: '+json.dumps(sources,ensure_ascii=False)},),profile_role='brief_editorial',source_scopes=source_scopes,archive_snapshots=archive_snapshots)
        try:
            receipt=client.complete_with_receipt(prompt=document.topic,
                system='Return JSON {stories:[{title,summary,explanation,plain_explanation,why_selected,next_step,caveat,anchors:[{evidence_ref,quote}]}],omitted_refs:[]}. Write every reader-facing field in Russian; keep JSON keys unchanged and source quotes verbatim. Select at most five actual events. Each quote must be an exact selected source substring of at least 16 characters. Explain importance separately from facts. Preserve deadlines/conflicts/coverage. No tools or external claims.',
                max_tokens=3500,category='brief_editorial',authorization=groups[0][0],data_class='user_provided',owner_ref=root.owner_ref,
                connection_ref=endpoint.connection_ref,resource_ref=root.model_resource_ref)
            return BriefEditorial.from_dict(json.loads(receipt.text),document.evidence)
        except Exception:return None
        finally:
            for group in groups:group[0].reservation.abandon_before_transport()
