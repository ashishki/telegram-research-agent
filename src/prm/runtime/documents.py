"""Exact immutable document dialogue and explicit current-source refresh."""
from dataclasses import replace
from datetime import datetime,timezone
import json,re
from html import escape
from prm.briefs import BriefWindow,BriefVersionRef,classify_brief_followup,render_brief_document,_content_digest
from prm.contracts import AssistantResult
from prm.storage.postgres import StorageError,StateConflict
from prm.capabilities import CapabilityDenied


class DocumentDialogueRuntime:
    def __init__(self,root):self.root=root

    @staticmethod
    def is_refresh(query):
        if query.startswith('/document '):
            try:return json.loads(query.partition(' ')[2]).get('action')=='refresh'
            except (ValueError,AttributeError):return False
        return bool(re.search(r'(?i)(?:^|:\s*)(?:обнови (?:бриф|обзор|отч[её]т|данные обзора)|refresh brief|update brief)[.!?]?$',query.strip()))

    def load(self,brief_id,version,*,guard=lambda:None):
        from .source_access import result_provenance,source_current
        store=self.root.briefs
        with store.store.transaction() as tx:
            from .deletion import lineage_lock
            lineage_lock(tx.conn,self.root.owner_ref);guard()
            item=tx.get(self.root.owner_ref,'result',store._document_ref(brief_id),version=version)
            if item is None or item.payload.get('brief_id')!=brief_id:raise StorageError('exact Brief version unavailable')
            _,scopes=result_provenance(tx,self.root.owner_ref,item)
            source_current(tx,self.root.registry,self.root.owner_ref,scopes,archive_snapshots=item.payload.get('archive_snapshots',[]),require_snapshot=True)
            return store._decode_document(item),item

    def resolve_current(self,request,*,request_ref,lease,guard):
        ticket=self.root.focus.ticket(request_ref) if lease else None
        if ticket and ticket.get('ambiguous'):raise StorageError('ambiguous document target')
        if ticket and ticket.get('target'):
            item,_,_=self.root.focus.resolve(ticket,guard=guard)
            value=item.payload.get('payload',item.payload)
            target=value.get('document_binding') or value.get('brief_document')
            if target:
                doc,manifest=self.load(target['brief_id'],target['version'],guard=guard)
                if target.get('content_digest',doc.content_digest)!=doc.content_digest:raise StorageError('document digest differs from target')
                return doc,manifest,target.get('story_number',value.get('brief_followup',{}).get('item_number'))
            return None
        return None

    def _named(self,query,guard):
        match=re.fullmatch(r'(?is)(?:обзор|документ|отч[её]т)\s+[«"]([^»"]{1,160})[»"](?:\s+версия\s+(\d{1,4}))?\s*:\s*(.+)',query)
        if not match:return None
        with self.root.queue.store.transaction() as tx:
            rows=tx.conn.execute("SELECT id,version FROM pa_briefs.documents WHERE owner=%s AND lower(payload->>'topic')=lower(%s) ORDER BY version DESC LIMIT 32",(self.root.owner_ref,match[1])).fetchall()
        valid=[]
        for row in rows:
            if match[2] and row['version']!=int(match[2]):continue
            if any(r[0].brief_id==row['id'] for r in valid):continue
            try:doc,item=self.load(row['id'],row['version'],guard=guard)
            except (StorageError,CapabilityDenied):continue
            valid.append((doc,item,None))
        if len(valid)!=1:raise StorageError('named document missing or ambiguous')
        return valid[0],match[3]

    def remember_view(self,request_ref,document,manifest,text,*,view,active_item=None,extra=None):
        root=self.root;scopes=manifest.payload.get('source_scopes',[]);snapshots=manifest.payload.get('archive_snapshots',[])
        classes=manifest.payload.get('source_data_classes',['user_provided'])
        exact=[{'namespace':'result','ref':manifest.object_id,'version':manifest.version,'digest':manifest.digest}]
        from .source_access import result_provenance,source_current
        def current(tx):
            item=tx.get(root.owner_ref,'result',manifest.object_id,version=manifest.version)
            if item is None or item.digest!=manifest.digest:raise CapabilityDenied('exact document view deleted or changed')
            result_provenance(tx,root.owner_ref,item)
            source_current(tx,root.registry,root.owner_ref,scopes,archive_snapshots=snapshots,require_snapshot=True)
        state=root.conversations.record_model_response(root.owner_chat_id,text=text,query='',topic=document.topic,data_classes=classes,
            source_scopes=scopes,archive_snapshots=snapshots,memory_bindings=manifest.payload.get('memory_bindings',[]),
            project_bindings=manifest.payload.get('project_bindings',[]),original_input_bindings=manifest.payload.get('original_input_bindings',[]),
            source_result_bindings=exact,provenance_guard=current)
        root.briefs.bind_visible(conversation_id=state.conversation_id,response_ref=state.object_refs[0].response_ref,
            document=document,active_item_number=active_item,authenticated_chat_id=root.owner_chat_id,
            authenticated_actor_id=root.owner_chat_id,authenticated_owner_chat_id=root.owner_chat_id)
        payload={'brief_document':document.to_dict(),'brief_inspection':document.inspect(),'brief_view':view,'telegram_parse_mode':'HTML',
            'document_binding':{'brief_id':document.brief_id,'version':document.version,'content_digest':document.content_digest,'story_number':active_item},
            'conversation':{'response_refs':[state.object_refs[0].response_ref]},'source_data_classes':classes,'source_data_class':classes[0],
            'source_result_bindings':exact,'memory_bindings':manifest.payload.get('memory_bindings',[]),'project_bindings':manifest.payload.get('project_bindings',[]),
            'original_input_bindings':manifest.payload.get('original_input_bindings',[]),
            'source_scopes':scopes,'archive_snapshots':snapshots,'retrieval_performed':False,'write_performed':False,**(extra or {})}
        return AssistantResult(request_ref,'partial_brief' if document.status=='partial' else 'ok','brief',text,payload=payload)

    def view_current(self,request,*,request_ref,lease,guard,why_signals=False):
        resolved=self.resolve_current(request,request_ref=request_ref,lease=lease,guard=guard)
        if resolved is None:return AssistantResult(request_ref,'clarify','chat','Выбери обзор и пункт: ответь на сообщение с обзором.',payload={'source_data_class':'user_provided'})
        doc,manifest,active=resolved
        text=render_brief_document(doc,view='why' if active else 'apply',item_number=active)
        if why_signals:
            signals=(manifest.payload.get('event_selection') or {}).get('signals',[])
            refs={a.evidence_ref for a in doc.editorial.stories[active-1].anchors} if active and doc.editorial else set()
            selected=[s for s in signals if s.get('brief_evidence_ref') in refs] if refs else [s for s in signals if s.get('editorial_included')][:5]
            lines=[]
            for row in selected:
                lines.append('Важность: '+str(row.get('importance','unknown'))+'; новизна: '+str(row.get('novelty','unknown'))+'; надёжность: '+str(row.get('reliability','unknown'))+'.')
                if row.get('feedback',{}).get('rule_bindings'):lines.append('Правило темы учтено; его можно отменить явной командой.')
            text+='\n\n'+escape('\n'.join(lines))+'\nОтсутствие реакции не означает отсутствие интереса.'
        return self.remember_view(request_ref,doc,manifest,text,view='why',active_item=active)

    def _refresh(self,request,request_ref,lease,guard,explicit=None):
        root=self.root
        if not hasattr(root,'brief_runtime'):raise StorageError('selected Brief source runtime unavailable')
        if explicit is None:
            ticket=root.focus.ticket(request_ref) if lease else None
            if not ticket or not ticket.get('target'):raise StorageError('exact document refresh target required')
            pointer=root.focus.resolve_document_metadata(ticket,guard=guard)
        else:pointer=explicit
        store=root.briefs
        with store.store.transaction() as tx:
            from .source_access import source_current,original_inputs_current
            guard();prior=tx.get(root.owner_ref,'result',store._document_ref(pointer['brief_id']),version=pointer['version'])
            head=tx.get(root.owner_ref,'result',store._document_ref(pointer['brief_id']))
            if prior is None or head is None:raise StorageError('refresh document unavailable')
            original_inputs_current(tx,root.owner_ref,prior.payload.get('original_input_bindings',[]))
            source_current(tx,root.registry,root.owner_ref,prior.payload.get('source_scopes',[]))
            # Read retained period metadata only. No stale text/project advice is
            # projected into a fresh answer when old bindings are no longer current.
            row=tx.conn.execute("SELECT payload->'window' AS window,payload->>'topic' AS topic FROM pa_briefs.documents WHERE owner=%s AND id=%s AND version=%s",(root.owner_ref,pointer['brief_id'],pointer['version'])).fetchone()
            if row is None:raise StorageError('refresh period metadata unavailable')
            old_selection=prior.payload.get('event_selection') or {};next_version=head.version+1
        w=row['window'];window=BriefWindow.from_iso(timezone_name=w['timezone'],start_at=w['start_at'],end_at=w['end_at'])
        fresh=root.brief_runtime.build(topic=row['topic'],timezone_name=window.timezone,window_override=window)
        old_digest=fresh.content_digest
        previous=BriefVersionRef(pointer['brief_id'],head.version)
        values=dict(topic=fresh.topic,window=fresh.window,evidence=fresh.evidence,coverage=fresh.coverage_manifest,deduplication=fresh.deduplication,
            conflicts=fresh.conflicts,selection_reasons=fresh.selection_reasons,previous_version=previous,comparison_ref=fresh.comparison_ref,
            period_basis='revised_current_sources',editorial=fresh.editorial)
        fresh=replace(fresh,brief_id=pointer['brief_id'],version=next_version,previous_version=previous,period_basis=values['period_basis'],content_digest=_content_digest(**values))
        for name in ('pending_dependencies','pending_classes','pending_scopes','pending_inventory','pending_coverage','pending_events','pending_project_bindings','pending_snapshots','pending_memory_bindings'):
            cache=getattr(store,name,{})
            if old_digest in cache:cache[fresh.content_digest]=cache[old_digest]
        current=store.pending_events.get(fresh.content_digest,{})
        old={e['event_ref']:e['revision'] for e in old_selection.get('events',[])};new={e['event_ref']:e['revision'] for e in current.get('events',[])}
        diff={'added':sorted(new.keys()-old.keys()),'removed':sorted(old.keys()-new.keys()),'changed':sorted(k for k in old.keys()&new.keys() if old[k]!=new[k]),
            'compared_version':pointer['version'],'previous_version':head.version,'new_source_search':True}
        answer=root.brief_runtime.answer(topic=fresh.topic,timezone_name=fresh.window.timezone,prepared_document=fresh)
        text='Обновление: источники проверены заново; создана версия '+str(fresh.version)+'.\nСобытия: новых '+str(len(diff['added']))+', изменённых '+str(len(diff['changed']))+', отсутствующих в новой выборке '+str(len(diff['removed']))+'.\n\n'+answer.text
        return replace(answer,text=text,payload={**answer.payload,'brief_refresh':{'performed':True,**diff},'retrieval_performed':True})

    def try_answer(self,request,*,request_ref,lease,guard):
        query=request.query.strip();explicit=None
        if lease:
            with self.root.queue.store.transaction() as tx:body=self.root.queue._input(tx,self.root.owner_ref,lease.payload).payload
            if body.get('telegram_envelope',{}).get('source_trust')=='untrusted_source':return None
        if query.startswith('/document '):
            explicit=json.loads(query.partition(' ')[2])
            if (not isinstance(explicit,dict) or not {'brief_id','version','action'}<=set(explicit) or set(explicit)-{'brief_id','version','action','story_number','format','topics'}
                or type(explicit['version'])is not int or explicit['version']<1 or explicit['action'] not in {'full','explain','why','sources','apply','short','topics','compare','refresh','export','save'}):raise StorageError('bounded document action required')
            if (not isinstance(explicit['brief_id'],str) or not re.fullmatch(r'brief_[a-f0-9]{16,64}',explicit['brief_id'])
                or explicit.get('story_number')is not None and (type(explicit['story_number'])is not int or not 1<=explicit['story_number']<=20)
                or explicit.get('format','markdown') not in {'html','markdown','pdf'}
                or not isinstance(explicit.get('topics',[]),list) or len(explicit.get('topics',[]))>4
                or any(not isinstance(t,str) or not 1<=len(t)<=120 for t in explicit.get('topics',[]))):raise StorageError('typed exact document fields required')
            query={'full':'покажи полный бриф','explain':'поясни пункт '+str(explicit.get('story_number',1)),'why':'почему это важно',
                'sources':'покажи источники','apply':'что из этого применить','short':'сделай короче','topics':'только '+','.join(explicit.get('topics',[])),
                'compare':'сравни с прошлой неделей','refresh':'обнови бриф','export':'экспорт '+explicit.get('format','markdown'),
                'save':'сохрани'+(' пункт '+str(explicit['story_number']) if explicit.get('story_number') else '')}[explicit['action']]
        named_query=None
        named_match=re.fullmatch(r'(?is)(?:обзор|документ|отч[её]т)\s+[«"]([^»"]{1,160})[»"](?:\s+версия\s+(\d{1,4}))?\s*:\s*(.+)',query)
        if named_match:named_query=query;query=named_match[3]
        export=re.fullmatch(r'(?i)(?:экспорт|экспортируй|выгрузи)(?:\s+(html|markdown|md|pdf))?',query)
        save=re.fullmatch(r'(?i)(?:сохрани|запомни)(?:\s+пункт\s*(\d{1,2}))?',query)
        if not export and not save and not self.is_refresh(query) and classify_brief_followup(query) is None and query.casefold().rstrip('?!') not in {'почему это важно','покажи источники','что дальше','какие ограничения'}:return None
        try:
            if explicit and self.is_refresh(query):return self._refresh(request,request_ref,lease,guard,explicit)
            named=self._named(named_query,guard) if named_query else None
            if named:resolved,query=named
            elif explicit:
                doc,manifest=self.load(explicit['brief_id'],explicit['version'],guard=guard);resolved=doc,manifest,explicit.get('story_number')
            elif self.is_refresh(query):return self._refresh(request,request_ref,lease,guard,explicit)
            else:resolved=self.resolve_current(request,request_ref=request_ref,lease=lease,guard=guard)
            if resolved is None:return None
            document,manifest,active=resolved
            if self.is_refresh(query):return self._refresh(request,request_ref,lease,guard,{'brief_id':document.brief_id,'version':document.version})
            followup=classify_brief_followup(query,active_item_number=active)
            if query.casefold().rstrip('?!')=='покажи источники' and active is None:
                text='Источники этой версии:\n'+'\n'.join('<a href="'+escape(e.source_ref,quote=True)+'">'+escape(e.title)+'</a>' for e in document.evidence)
                return self.remember_view(request_ref,document,manifest,text,view='sources')
            if save:
                if not hasattr(self.root,'memory'):raise StorageError('confirmed memory capability unavailable')
                number=int(save[1]) if save[1] else active
                count=len(document.editorial.stories) if document.editorial else len(document.items)
                if number is None:text='Сохранённая ссылка на обзор «'+document.topic+'», версия '+str(document.version)+'. Период: '+document.window.start_at.date().isoformat()+' — '+document.window.end_at.date().isoformat()+'.'
                elif not 1<=number<=count:raise StorageError('story unavailable')
                elif document.editorial:
                    story=document.editorial.stories[number-1];refs={a.evidence_ref for a in story.anchors};text='\n'.join(e.summary+' ('+e.source_ref+')' for e in document.evidence if e.evidence_ref in refs)
                else:text=document.items[number-1].summary
                from .memory_dialogue import MemoryDialogueRuntime
                return MemoryDialogueRuntime(self.root).preview(request_ref,lease,text=text,source_bindings=[{'namespace':'result','ref':manifest.object_id,'version':manifest.version,'digest':manifest.digest}])
            if export:
                from prm.report_exports import render_report
                format=(export[1] or 'markdown').casefold();format='markdown' if format=='md' else format
                artifact=render_report(document,format)
                body=artifact.body
                # Binary exports are local artifacts; never place PDF bytes in chat JSON.
                import hashlib
                raw=body.encode() if isinstance(body,str) else body
                export_ref=self._save_export(request_ref,document,manifest,format,raw)
                extra={'export':{'format':format,'identity':{'brief_id':document.brief_id,'version':document.version,'content_digest':document.content_digest},
                    'export_ref':export_ref,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'delivery':'local_artifact_not_sent'}}
                if format=='markdown':extra['export']['text']=body
                return self.remember_view(request_ref,document,manifest,'Экспорт '+format.upper()+' подготовлен для этой версии. Содержание и источники сохранены.',view='export',extra=extra)
            if followup is None:raise StorageError('exact story required for this continuation')
            view={'explain_item':'item','why_item':'why','simplify_item':'simplify','next_step_item':'next_step','sources_item':'sources','caveat_item':'caveat','shorten':'short','filter_topics':'topics','less_technical':'less_technical','apply':'apply','full':'full','compare_weeks':'comparison'}[followup.kind]
            comparison=None
            if view=='comparison':
                if document.previous_version:comparison,_=self.load(document.previous_version.brief_id,document.previous_version.version,guard=guard)
                elif document.comparison_ref:comparison,_=self.load(document.comparison_ref.brief_id,document.comparison_ref.version,guard=guard)
            count=len(document.editorial.stories) if document.editorial else len(document.items)
            number=followup.item_number
            if number is not None and not 1<=number<=count:raise StorageError('story unavailable')
            text=render_brief_document(document,view=view,item_number=number,topics=followup.topics,comparison_document=comparison)
            return self.remember_view(request_ref,document,manifest,text,view=view,active_item=number,
                extra={'brief_followup':{'kind':followup.kind,'item_number':number,'source':'exact_persisted_document','topics':list(followup.topics)}})
        except (StorageError,CapabilityDenied,ValueError,KeyError,TypeError):
            return AssistantResult(request_ref,'clarify','chat','Выбери точный обзор, версию и пункт. Недоступные или устаревшие источники требуют новой проверки; прежнее подтверждение не возобновляется.',payload={'source_data_class':'user_provided','document_unavailable':True})

    def _save_export(self,request_ref,document,manifest,format,body):
        import base64,hashlib
        if len(body)>4*1024*1024:raise StorageError('local export exceeds bound')
        owner=self.root.owner_ref;ref='document_export_'+hashlib.sha256((request_ref+':'+format+':'+document.content_digest).encode()).hexdigest()[:32]
        with self.root.queue.store.transaction() as tx:
            from .deletion import lineage_lock
            from .source_access import source_current,result_provenance
            lineage_lock(tx.conn,owner)
            current=tx.get(owner,'result',manifest.object_id,version=manifest.version)
            if current is None or current.digest!=manifest.digest:raise StorageError('export document deleted')
            _,scopes=result_provenance(tx,owner,current);source_current(tx,self.root.registry,owner,scopes,archive_snapshots=manifest.payload.get('archive_snapshots',[]),require_snapshot=True)
            old=tx.get(owner,'result',ref)
            if old:return ref
            parts=[]
            for index,start in enumerate(range(0,len(body),24000)):
                part_ref=ref+'_p'+str(index)
                part=tx.put(owner,'result',part_ref,{'kind':'document_export_part','body_base64':base64.b64encode(body[start:start+24000]).decode()},expected_version=0)
                parts.append({'ref':part_ref,'digest':part.digest})
                tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(owner,'result',ref,'result',part_ref))
            tx.put(owner,'result',ref,{'kind':'document_export','brief_id':document.brief_id,'version':document.version,'content_digest':document.content_digest,
                'format':format,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'parts':parts,
                'data_classes':manifest.payload.get('source_data_classes',['user_provided']),'source_scopes':list(scopes),
                'archive_snapshots':manifest.payload.get('archive_snapshots',[]),
                'memory_bindings':manifest.payload.get('memory_bindings',[]),'project_bindings':manifest.payload.get('project_bindings',[]),
                'original_input_bindings':manifest.payload.get('original_input_bindings',[]),
                'source_result_bindings':[{'namespace':'result','ref':manifest.object_id,'version':manifest.version,'digest':manifest.digest}]},expected_version=0)
            tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(owner,'result',manifest.object_id,'result',ref))
            tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(owner,'conversation',request_ref,'result',ref))
        return ref

    def read_export(self,export_ref,*,chat_id,actor_id,owner_chat_id):
        from prm.briefs import brief_owner_ref_from_authenticated_private_tuple
        if brief_owner_ref_from_authenticated_private_tuple(chat_id,actor_id,owner_chat_id)!=self.root.owner_ref:raise CapabilityDenied('exact private export owner required')
        import base64,hashlib
        with self.root.queue.store.transaction() as tx:
            from .deletion import lineage_lock
            lineage_lock(tx.conn,self.root.owner_ref);item=tx.get(self.root.owner_ref,'result',export_ref)
            if item is None or item.payload.get('kind')!='document_export':raise StorageError('export unavailable')
            from .source_access import result_provenance,source_current
            manifest=tx.get(self.root.owner_ref,'result',self.root.briefs._document_ref(item.payload['brief_id']),version=item.payload['version'])
            if manifest is None or manifest.payload.get('content_digest')!=item.payload['content_digest']:raise StorageError('export document unavailable')
            _,scopes=result_provenance(tx,self.root.owner_ref,manifest)
            source_current(tx,self.root.registry,self.root.owner_ref,scopes,archive_snapshots=manifest.payload.get('archive_snapshots',[]),require_snapshot=True)
            parts=[]
            for binding in item.payload['parts']:
                part=tx.get(self.root.owner_ref,'result',binding['ref'],version=1)
                if part is None or part.digest!=binding['digest']:raise StorageError('export part changed or deleted')
                parts.append(base64.b64decode(part.payload['body_base64'],validate=True))
            body=b''.join(parts)
            if len(body)!=item.payload['bytes'] or hashlib.sha256(body).hexdigest()!=item.payload['sha256']:raise StorageError('export body integrity differs')
            return body,item.payload['format']
