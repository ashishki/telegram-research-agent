"""Selected Canvas reads and durable obligations with visible date conflicts."""
from dataclasses import replace
from datetime import datetime,timezone
import hashlib
import json
from urllib.parse import urlencode,quote,urlsplit
from prm.academic_inbox import AcademicCandidate,AcademicDeadline,categorize,conflicting_deadlines,derive_stage,require_academic_read_access
from prm.capabilities import CapabilityDenied
from prm.storage.postgres import StorageError
from prm.public_web import _https_get


class CanvasReadAdapter:
    def __init__(self,*,registry,origin,credential,synthetic_transport=None,institution_access_ref=None):
        parsed=urlsplit(origin)
        if parsed.scheme!='https' or not parsed.hostname or parsed.path not in {'','/'} or parsed.username or parsed.query:
            raise StorageError('fixed selected Canvas HTTPS origin required')
        self.registry,self.origin,self._credential=registry,origin.rstrip('/'),credential
        self.synthetic_transport=synthetic_transport;self.institution_access_ref=institution_access_ref

    def fetch_page(self,request,*,surface='assignments'):
        require_academic_read_access(request)
        if self.synthetic_transport is None and not self.institution_access_ref:raise CapabilityDenied('institutional Canvas approval reference required')
        selection=request.selection;output=[]
        if len(selection.course_refs)!=1:raise StorageError('one exact selected course per page; use collect for multiple courses')
        # Each endpoint needs its own current reservation. This request carries
        # one page, never turns one authorization into three endpoint calls.
        course=selection.course_refs[0].removeprefix('course_')
        if surface=='assignments' and selection.include_assignments:
            path='/api/v1/courses/'+quote(course,safe='')+'/assignments?'+urlencode({'per_page':min(selection.max_items,50)})
        elif surface=='announcements' and selection.include_announcements:
            path='/api/v1/announcements?'+urlencode({'context_codes[]':selection.course_refs[0],'start_date':selection.window_start.isoformat(),
                'end_date':selection.window_end.isoformat(),'per_page':min(selection.max_items,50)})
        elif surface=='calendar' and selection.include_calendar:
            path='/api/v1/calendar_events?'+urlencode({'context_codes[]':selection.course_refs[0],'start_date':selection.window_start.date().isoformat(),
                'end_date':selection.window_end.date().isoformat(),'per_page':min(selection.max_items,50),'excludes[]':'assignment'})
        else:raise CapabilityDenied('Canvas surface not explicitly selected')
        if request.cursor:
            cursor=self.registry.store.get(request.owner_ref,'conversation',request.cursor,version=1)
            if cursor is None or (cursor.payload['course_ref'],cursor.payload['surface'],cursor.payload['connection_ref'])!=(selection.course_refs[0],surface,request.connection_ref):
                raise CapabilityDenied('Canvas continuation scope differs')
            path=cursor.payload['path']
        def transport():
            if self.synthetic_transport:
                value=self.synthetic_transport(path)
                return (value.get('rows'),value.get('next_url')) if isinstance(value,dict) else (value,None)
            response=_https_get(self.origin+path,timeout_seconds=8,max_bytes=128000,headers={'Authorization':'Bearer '+self._credential})
            if response['content_type']!='application/json':raise StorageError('Canvas response type differs')
            import re
            match=re.search(r'<([^>]+)>;\s*rel="?next"?',response['headers'].get('link',''))
            return json.loads(response['body']),match.group(1) if match else None
        rows,next_url=self.registry.execute_prepared(request.authorization.reservation,transport)
        self.next_cursor=None
        if next_url:
            from urllib.parse import parse_qs
            parsed=urlsplit(next_url);origin=urlsplit(self.origin);params=parse_qs(parsed.query)
            if (parsed.scheme,parsed.netloc)!=(origin.scheme,origin.netloc) or parsed.path!=path.split('?')[0] or parsed.username or parsed.fragment:
                raise CapabilityDenied('Canvas next page changed source/origin')
            if set(params)-{'page','per_page','context_codes[]','start_date','end_date','excludes[]'}:raise CapabilityDenied('Canvas continuation widened fields')
            if 'context_codes[]' in params and params['context_codes[]']!=[selection.course_refs[0]]:raise CapabilityDenied('Canvas continuation changed course')
            cursor_ref='cursor_'+hashlib.sha256((request.owner_ref+request.connection_ref+next_url).encode()).hexdigest()[:40]
            old=self.registry.store.get(request.owner_ref,'conversation',cursor_ref,version=1)
            payload={'path':parsed.path+'?'+parsed.query,'course_ref':selection.course_refs[0],'surface':surface,'connection_ref':request.connection_ref}
            if old is None:self.registry.store.put(request.owner_ref,'conversation',cursor_ref,payload,expected_version=0)
            elif old.payload!=payload:raise StorageError('Canvas cursor identity differs')
            self.next_cursor=cursor_ref
        if not isinstance(rows,list) or len(rows)>selection.max_items:raise StorageError('Canvas page bound differs')
        for row in rows:
            source=row.get('html_url') or self.origin+'/courses/'+course+'/assignments/'+str(row['id'])
            due=row.get('due_at') if surface=='assignments' else row.get('start_at');deadlines=()
            if due:deadlines=(AcademicDeadline('source_due_at',datetime.fromisoformat(due.replace('Z','+00:00')),'UTC','canvas',source),)
            identifier='academic_'+hashlib.sha256((surface+':'+course+':'+str(row['id'])).encode()).hexdigest()[:32]
            source_kind={'assignments':'canvas_assignment','announcements':'canvas_announcement','calendar':'canvas_calendar'}[surface]
            title=row.get('name') or row.get('title') or 'Canvas item'
            category='obligation' if surface=='assignments' else categorize(source_kind,title)
            output.append(AcademicCandidate(identifier,request.owner_ref,source_kind,title[:240],
                'Источник: выбранный раздел Canvas. Содержимое сдачи и оценки не загружены.',category,'canvas',deadlines=deadlines,
                eligibility_note='Course visibility does not establish eligibility.',eligibility_uncertain=True,source_refs=(source,),
                source_version=str(row.get('updated_at',''))))
        return tuple(output)
    def collect(self,selection,*,owner_ref,connection_ref,upper_bound,max_calls=8):
        from prm.academic_inbox import AcademicFetchRequest
        from prm.capabilities import AuthorizationRequest
        import uuid
        candidates=[];coverage=[];calls=0;complete=True
        for course in selection.course_refs:
            for surface,enabled in (('assignments',selection.include_assignments),('announcements',selection.include_announcements),('calendar',selection.include_calendar)):
                if not enabled:continue
                cursor=None;done=False
                while calls<max_calls:
                    decision=self.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=owner_ref,connection_ref=connection_ref,
                        capability='assistant.academic_read',resource_ref=selection.account_ref,operation='read',data_class='private_connector_content',
                        provider_ref='provider_canvas',purpose='academic.read',operation_ref='canvas_'+uuid.uuid4().hex),upper_bound=upper_bound)
                    if not decision.allowed:coverage.append(course+':'+surface+':scope_denied');break
                    calls+=1
                    try:
                        request=AcademicFetchRequest(decision,owner_ref,connection_ref,replace(selection,course_refs=(course,)),cursor=cursor)
                        candidates.extend(self.fetch_page(request,surface=surface));cursor=self.next_cursor
                        if cursor is None:done=True;coverage.append(course+':'+surface+':checked');break
                    except Exception:coverage.append(course+':'+surface+':unavailable');break
                if not done:complete=False;coverage.append(course+':'+surface+':partial')
        return {'candidates':tuple(candidates),'coverage':coverage,'complete':complete,'tool_calls':calls}


class AcademicRuntime:
    def __init__(self,root,*,scheduler=None):self.root,self.scheduler=root,scheduler
    def merge(self,candidates,*,identity_bindings):
        groups={}
        for candidate in candidates:
            if candidate.owner_ref!=self.root.owner_ref:raise CapabilityDenied('academic source owner differs')
            canonical=identity_bindings.get(candidate.candidate_ref,candidate.candidate_ref)
            groups.setdefault(canonical,[]).append(candidate)
        result=[]
        for canonical,group in groups.items():
            winner=max(group,key=lambda item:{'canvas':3,'official_message':2,'aggregator':1}[item.authority])
            deadlines=tuple({(item.label,item.due_at):item for entry in group for item in entry.deadlines}.values())
            merged=replace(winner,deadlines=deadlines,source_refs=tuple(dict.fromkeys(ref for entry in group for ref in entry.source_refs)),
                           eligibility_uncertain=any(entry.eligibility_uncertain for entry in group))
            ref='academic_'+hashlib.sha256(canonical.encode()).hexdigest()[:32]
            merged=replace(merged,candidate_ref=ref)
            old=self.root.queue.store.get(self.root.owner_ref,'memory',ref)
            payload={**merged.to_payload(),'source_versions':{entry.candidate_ref:entry.source_version for entry in group}}
            if old and old.payload.get('completion')=='local_done':payload['completion']='local_done';merged=replace(merged,completion='local_done')
            if not old or old.payload!=payload:self.root.queue.store.put(self.root.owner_ref,'memory',ref,payload,expected_version=old.version if old else 0)
            result.append(merged)
        return tuple(result)
    def selected_context(self):
        """Collect only explicitly configured academic metadata selections."""
        result=[];coverage=[]
        for name,scope,collector,bound in getattr(self.root,'academic_source_hooks',()):
            import uuid
            decision=self.root.registry.authorize_and_reserve(replace(scope,operation_ref='academiccontext_'+uuid.uuid4().hex),upper_bound=bound)
            if not decision.allowed:coverage.append(name+':scope_denied');continue
            try:
                batch=self.root.registry.execute_reserved((decision.reservation,),collector)
                if len(batch)>48:raise StorageError('academic metadata batch exceeds bound')
                result.extend(batch);coverage.append(name+':checked')
            except Exception:coverage.append(name+':unavailable')
        return tuple(result),coverage

    def stage(self):
        item=self.root.queue.store.get(self.root.owner_ref,'memory','memory_academic_stage')
        value=item.payload['text'] if item is not None else ''
        return value.removeprefix('academic_stage:') if value.startswith('academic_stage:') and value.removeprefix('academic_stage:') in {'preparation','waiting','studying','completed'} else 'unknown'
    def preview_stage(self,stage,*,actor_ref):
        if actor_ref!=self.root.owner_ref:raise CapabilityDenied('explicit private owner stage selection required')
        if stage not in {'preparation','waiting','studying','completed'}:raise StorageError('unsupported academic stage')
        from .memory import MemoryRuntime
        old=self.root.queue.store.get(self.root.owner_ref,'memory','memory_academic_stage')
        return MemoryRuntime(self.root).preview(object_ref='memory_academic_stage',text='academic_stage:'+stage,source_refs=('explicit_owner_stage',),
            kind='preference',expected_version=old.version if old else 0,chat_id=self.root.owner_chat_id,actor_id=self.root.owner_chat_id,owner_chat_id=self.root.owner_chat_id)
    def describe(self,candidates):
        lines=[]
        for item in candidates:
            conflict=conflicting_deadlines(item)
            dates=', '.join(deadline.due_at.isoformat()+' ('+deadline.authority+')' for deadline in item.deadlines)
            lines.append(item.title+' — '+item.category+(' — конфликт сроков: '+dates if conflict else (' — '+dates if dates else ' — срок не подтверждён'))+
                         (' — применимость требует уточнения' if item.eligibility_uncertain else '')+
                         (' — отмечено выполненным локально; сдача в источнике не подтверждена' if item.completion=='local_done' else '\nОтметить выполненным: /academicdone '+item.candidate_ref))
        return '\n'.join(lines) or 'В проверенном покрытии кандидатов нет; отсутствующие источники не проверены.'
    def mark_done(self,object_ref,*,actor_ref):
        if actor_ref!=self.root.owner_ref:raise CapabilityDenied('private owner required')
        from .scheduler import WatchScheduler
        scheduler=self.scheduler or WatchScheduler(self.root.queue)
        with self.root.queue.store.transaction() as tx:
            from .deletion import lineage_lock
            lineage_lock(tx.conn,self.root.owner_ref)
            bindings=tx.conn.execute('SELECT schedule_id,subject_ref FROM pa_academic.watches WHERE owner=%s AND object_ref=%s ORDER BY schedule_id,subject_ref FOR UPDATE',
                (self.root.owner_ref,object_ref)).fetchall()
            for binding in bindings:scheduler.complete_subject_in(tx,owner=self.root.owner_ref,subscription_id=binding['schedule_id'],subject_ref=binding['subject_ref'])
            item=tx.get(self.root.owner_ref,'memory',object_ref)
            if item is None:raise StorageError('academic candidate unavailable')
            if item.payload.get('completion')!='local_done':
                tx.put(self.root.owner_ref,'memory',object_ref,{**item.payload,'completion':'local_done'},expected_version=item.version)
        return {'completion':'local_done','source_submission_performed':False,'stopped_watch_subjects':len(bindings)}

    def link_watch(self,object_ref,*,schedule_id,subject_ref,actor_ref):
        if actor_ref!=self.root.owner_ref:raise CapabilityDenied('private owner required')
        if not isinstance(subject_ref,str) or not 0<len(subject_ref)<=128:raise StorageError('exact bounded Watch subject required')
        with self.root.queue.store.transaction() as tx:
            from .deletion import lineage_lock
            lineage_lock(tx.conn,self.root.owner_ref)
            item=tx.get(self.root.owner_ref,'memory',object_ref)
            if item is None or not item.payload.get('candidate_ref'):raise StorageError('owned academic item required')
            schedule=tx.conn.execute('SELECT id FROM pa_schedule.schedules WHERE owner=%s AND id=%s FOR UPDATE',(self.root.owner_ref,schedule_id)).fetchone()
            if schedule is None:raise CapabilityDenied('confirmed owned Watch subscription required')
            tx.conn.execute('INSERT INTO pa_academic.watches VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',(self.root.owner_ref,object_ref,schedule_id,subject_ref))
            if item.payload.get('completion')=='local_done':
                from .scheduler import WatchScheduler
                (self.scheduler or WatchScheduler(self.root.queue)).complete_subject_in(tx,owner=self.root.owner_ref,subscription_id=schedule_id,subject_ref=subject_ref)

    def brief_evidence(self,window):
        with self.root.queue.store.transaction() as tx:
            rows=tx.conn.execute("SELECT h.object_id,min(v.created_at) AS discovered_at FROM pa_runtime.object_heads h JOIN pa_runtime.object_versions v USING(owner,namespace,object_id) WHERE h.owner=%s AND h.namespace='memory' AND h.object_id LIKE 'academic_%%' GROUP BY h.object_id ORDER BY h.object_id LIMIT 48",(self.root.owner_ref,)).fetchall()
            items=[(tx.get(self.root.owner_ref,'memory',row['object_id']),row['discovered_at']) for row in rows]
        evidence=[]
        for item,discovered in items:
            if item is None:continue
            value=item.payload
            if value.get('completion') in {'local_done','source_completed'}:continue
            instants=[datetime.fromisoformat(deadline['due_at'].replace('Z','+00:00')) for deadline in value.get('deadlines',[])]
            if not window.contains(discovered) and not any(window.contains(instant) for instant in instants):continue
            for source in value.get('source_refs',[])[:1]:
                evidence.append({'evidence_id':item.object_id,'source_url':source,'title':value['title'],
                    'support_span':value['summary'][:1000]+('; сроки: '+', '.join(instant.isoformat() for instant in instants) if instants else '; срок не подтверждён'),
                    'first_discovered_at':discovered.isoformat(),'source_version':str(item.version),'source_state':'active',
                    'source_kind':'academic','local_source_provenance':True,'source_owner_ref':self.root.owner_ref,
                    'source_data_class':'private_connector_content','importance':'high',
                    'dependency_ref':{'namespace':'memory','object_ref':item.object_id,'version':item.version,'digest':item.digest}})
        return evidence
