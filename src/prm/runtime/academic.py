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
            old=self.root.queue.store.get(self.root.owner_ref,'memory',ref)
            payload=merged.to_payload()
            if old and old.payload.get('completion')=='local_done':payload['completion']='local_done';merged=replace(merged,completion='local_done')
            if not old or old.payload!=payload:self.root.queue.store.put(self.root.owner_ref,'memory',ref,payload,expected_version=old.version if old else 0)
            result.append(merged)
        return tuple(result)
    def describe(self,candidates):
        lines=[]
        for item in candidates:
            conflict=conflicting_deadlines(item)
            dates=', '.join(deadline.due_at.isoformat()+' ('+deadline.authority+')' for deadline in item.deadlines)
            lines.append(item.title+' — '+item.category+(' — конфликт сроков: '+dates if conflict else (' — '+dates if dates else ' — срок не подтверждён'))+
                         (' — применимость требует уточнения' if item.eligibility_uncertain else '')+
                         (' — отмечено выполненным локально; сдача в источнике не подтверждена' if item.completion=='local_done' else ''))
        return '\n'.join(lines) or 'В проверенном покрытии кандидатов нет; отсутствующие источники не проверены.'
    def mark_done(self,object_ref,*,actor_ref):
        if actor_ref!=self.root.owner_ref:raise CapabilityDenied('private owner required')
        item=self.root.queue.store.get(self.root.owner_ref,'memory',object_ref)
        if item is None:raise StorageError('academic candidate unavailable')
        payload={**item.payload,'completion':'local_done'}
        self.root.queue.store.put(self.root.owner_ref,'memory',object_ref,payload,expected_version=item.version)
        return {'completion':'local_done','source_submission_performed':False}
