"""Selected calendar/contacts composition with independent fresh page grants."""
from dataclasses import asdict,replace
from datetime import datetime,timezone
import hashlib
import json
import uuid
from urllib.parse import quote
from psycopg.types.json import Jsonb
from prm.capabilities import AuthorizationRequest,CapabilityDenied
from prm.schedule_connectors import CalendarFetchRequest,ContactsFetchRequest,detect_conflicts,free_busy,resolve_recipient
from prm.storage.postgres import StorageError,StateConflict
from .graph import GraphCalendarAdapter,GraphContactsAdapter


class GraphScheduleRuntime:
    def __init__(self,transport):self.transport=transport;self.calendar=GraphCalendarAdapter(transport);self.contacts=GraphContactsAdapter(transport)
    def _access(self,capability,purpose):
        decision=self.transport.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=self.transport.owner_ref,
            connection_ref=self.transport.connection_ref,capability=capability,resource_ref=self.transport.account_ref,operation='read',
            data_class='private_connector_metadata',provider_ref='provider_microsoft_graph',purpose=purpose,operation_ref='schedule_'+uuid.uuid4().hex),
            upper_bound=self.transport.upper_bound)
        if not decision.allowed:raise CapabilityDenied(decision.reason)
        return decision
    def read_calendar(self,selection,*,max_pages=4):
        if not 1<=max_pages<=10:raise StorageError('bounded calendar paging required')
        owner=self.transport.owner_ref;connection=self.transport.connection_ref
        digest=hashlib.sha256(json.dumps(selection.to_payload(),sort_keys=True).encode()).hexdigest()
        events=[];pages=0;complete=True
        for calendar_ref in selection.calendar_refs:
            cursor=None;single=replace(selection,calendar_refs=(calendar_ref,))
            while pages<max_pages:
                decision=self._access('assistant.calendar_read','calendar.read')
                batch=self.calendar.fetch_page(CalendarFetchRequest(decision,owner,connection,single,cursor=cursor));pages+=1
                with self.transport.connections.store.transaction() as tx:
                    account=tx.conn.execute('SELECT status FROM pa_connections.accounts WHERE owner=%s AND id=%s FOR UPDATE',(owner,connection)).fetchone()
                    if not account or account['status']!='connected':raise CapabilityDenied('calendar connection revoked')
                    for item in batch:
                        payload=asdict(item)
                        for name in ('start_at','end_at'):payload[name]=payload[name].isoformat()
                        payload['scope_digest']=digest
                        payload['provider_original_timezones']=self.calendar.original_timezones.get(item.event_ref,{})
                        tx.conn.execute('''INSERT INTO pa_sources.items(owner,connection_ref,kind,id,version,payload,deleted) VALUES(%s,%s,'calendar',%s,%s,%s,%s)
                            ON CONFLICT(owner,connection_ref,kind,id) DO UPDATE SET version=excluded.version,payload=excluded.payload,deleted=excluded.deleted,updated_at=clock_timestamp()''',
                            (owner,connection,item.event_ref,item.version or hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),Jsonb(payload),item.status=='cancelled'))
                    tx.conn.execute('''INSERT INTO pa_sources.sync(owner,connection_ref,kind,scope_digest,revision,cursor,completed) VALUES(%s,%s,'calendar',%s,1,%s,false)
                        ON CONFLICT(owner,connection_ref,kind,scope_digest) DO UPDATE SET revision=pa_sources.sync.revision+1,cursor=excluded.cursor,completed=false,updated_at=clock_timestamp()''',
                        (owner,connection,digest,self.calendar.next_cursor))
                events.extend(batch);cursor=self.calendar.next_cursor
                if cursor is None:break
            else:complete=False
            if cursor is not None:complete=False
            if pages>=max_pages and calendar_ref!=selection.calendar_refs[-1]:complete=False;break
        if complete:
            with self.transport.connections.store.transaction() as tx:
                tx.conn.execute("UPDATE pa_sources.items SET deleted=true WHERE owner=%s AND connection_ref=%s AND kind='calendar' AND payload->>'scope_digest'=%s AND NOT(id=ANY(%s))",
                    (owner,connection,digest,[event.event_ref for event in events]))
                tx.conn.execute("UPDATE pa_sources.sync SET completed=true,cursor=NULL WHERE owner=%s AND connection_ref=%s AND kind='calendar' AND scope_digest=%s",(owner,connection,digest))
        visible=tuple(event for event in events if event.status!='cancelled')
        conflicts=detect_conflicts(visible)
        return {'events':visible,'conflicts':conflicts,'free_busy':free_busy(visible,local_timezone=selection.local_timezone),
            'status':'read' if complete else 'partial','text':'\n'.join(event.title+' — '+event.start_at.astimezone(__import__('zoneinfo').ZoneInfo(selection.local_timezone)).isoformat() for event in visible)+
                ('\nКонфликты расписания: '+str(len(conflicts)) if conflicts else ''),'coverage_complete':complete}
    def resolve_contact(self,query,*,max_pages=4):
        contacts=[];cursor=None
        for index in range(max_pages):
            decision=self._access('assistant.contacts_read','contacts.read')
            request=ContactsFetchRequest(decision,self.transport.owner_ref,self.transport.connection_ref,'provider_microsoft_graph',self.transport.account_ref,query=query,cursor=cursor)
            batch=self.contacts.fetch_page(request);contacts.extend(batch);cursor=self.contacts.next_cursor
            if cursor is None:break
        result=resolve_recipient(query,tuple(contacts),accounts=(self.transport.account_ref,))
        return {'resolution':result,'contacts':tuple(contacts),'coverage_complete':cursor is None,
                'text':'Найдено адресатов: '+str(len(contacts))+'. При нескольких совпадениях требуется точный выбор.'}

    def brief_evidence(self,selection,window):
        """Read only the completed selected snapshot under the caller's grant."""
        if selection.window_start>window.start_at or selection.window_end<window.end_at:raise StorageError('selected calendar snapshot does not cover the requested report period')
        digest=hashlib.sha256(json.dumps(selection.to_payload(),sort_keys=True).encode()).hexdigest()
        with self.transport.connections.store.transaction() as tx:
            account=tx.conn.execute('SELECT status FROM pa_connections.accounts WHERE owner=%s AND id=%s',
                (self.transport.owner_ref,self.transport.connection_ref)).fetchone()
            state=tx.conn.execute("SELECT completed FROM pa_sources.sync WHERE owner=%s AND connection_ref=%s AND kind='calendar' AND scope_digest=%s",
                (self.transport.owner_ref,self.transport.connection_ref,digest)).fetchone()
            if not account or account['status']!='connected' or not state or not state['completed']:
                raise StorageError('selected calendar coverage unavailable')
            rows=tx.conn.execute("SELECT payload,updated_at FROM pa_sources.items WHERE owner=%s AND connection_ref=%s AND kind='calendar' AND NOT deleted AND payload->>'scope_digest'=%s ORDER BY id LIMIT 48",
                (self.transport.owner_ref,self.transport.connection_ref,digest)).fetchall()
        evidence=[]
        for row in rows:
            item=row['payload'];start=datetime.fromisoformat(item['start_at'])
            if not window.contains(start):continue
            source=item.get('source_ref') or 'https://graph.microsoft.com/v1.0/me/events/'+quote(item['event_ref'],safe='')
            evidence.append({'evidence_id':'calendar:'+hashlib.sha256((self.transport.account_ref+item['event_ref']).encode()).hexdigest()[:32],
                'source_url':source,'title':item['title'] or 'Событие календаря',
                'support_span':(item['title'] or 'Событие')+'; начало '+item['start_at']+'; окончание '+item['end_at'],
                'event_at':item['start_at'],'first_discovered_at':row['updated_at'].isoformat(),
                'source_version':item['version'],'source_state':'active','source_kind':'calendar','local_source_provenance':True,
                'source_owner_ref':self.transport.owner_ref,'source_connection_ref':self.transport.connection_ref,
                'source_data_class':'private_connector_metadata','importance':'high'})
        return evidence
