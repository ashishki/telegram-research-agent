"""Bounded metadata-only Graph reads, paging/delta and durable derived state."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import json
from urllib.parse import quote,urlencode,urlsplit,parse_qs
from urllib.request import Request,ProxyHandler,build_opener
from urllib.error import HTTPError
from psycopg.types.json import Jsonb
from prm.storage.postgres import PostgresStore,StorageError,StateConflict
from prm.capabilities import AuthorizationRequest,CapabilityDenied,require_authorized_operation
from prm.mail_connector import MailMessage,MailFetchPage,require_mail_read_access
from prm.schedule_connectors import CalendarEvent,Contact,require_calendar_read_access,require_contacts_read_access
from .model import NoRedirect

DDL=(
    'CREATE SCHEMA pa_sources',
    'CREATE TABLE pa_sources.meta(version integer PRIMARY KEY,checksum text NOT NULL)',
    '''CREATE TABLE pa_sources.items(owner text NOT NULL,connection_ref text NOT NULL,kind text NOT NULL,id text NOT NULL,
       version text NOT NULL,payload jsonb NOT NULL,deleted boolean NOT NULL DEFAULT false,updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
       PRIMARY KEY(owner,connection_ref,kind,id))''',
    '''CREATE TABLE pa_sources.sync(owner text NOT NULL,connection_ref text NOT NULL,kind text NOT NULL,scope_digest text NOT NULL,
       revision bigint NOT NULL,cursor text,completed boolean NOT NULL DEFAULT false,updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
       PRIMARY KEY(owner,connection_ref,kind,scope_digest))''',
    'GRANT USAGE ON SCHEMA pa_sources TO pa_test_app',
    'GRANT SELECT ON pa_sources.meta TO pa_test_app',
    'GRANT SELECT,INSERT,UPDATE,DELETE ON pa_sources.items,pa_sources.sync TO pa_test_app',
)
CHECKSUM=hashlib.sha256('\n'.join(DDL).encode()).hexdigest()


def install_sources(target):
    if target.user!='pa_test_migrator':raise StorageError('dedicated synthetic migrator required')
    with PostgresStore(target).transaction() as tx:
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)',(87291017,))
        if tx.conn.execute("SELECT to_regclass('pa_sources.meta') AS meta").fetchone()['meta'] is None:
            for statement in DDL:tx.conn.execute(statement)
            tx.conn.execute('INSERT INTO pa_sources.meta VALUES(1,%s)',(CHECKSUM,))


class GraphRateLimited(StorageError):pass
class GraphDeltaReset(StorageError):pass


class GraphTransport:
    def __init__(self,*,registry,connections,owner_ref,connection_ref,account_ref,upper_bound=None):
        if connections.store.target!=registry.store.target:raise StorageError('shared connection/policy backend required')
        self.registry,self.connections,self.owner_ref,self.connection_ref,self.account_ref=registry,connections,owner_ref,connection_ref,account_ref
        self.upper_bound=upper_bound

    def request(self,decision,*,path,method='GET',body=None,headers=None):
        if (decision.owner_ref,decision.connection_ref,decision.provider_ref)!=(self.owner_ref,self.connection_ref,'provider_microsoft_graph'):
            raise CapabilityDenied('Graph transport connection or provider differs')
        if not path.startswith('/v1.0/me/') and path!='/v1.0/me':raise CapabilityDenied('Graph account path substituted')
        if method not in {'GET','POST','PATCH','DELETE'}:raise StorageError('unsupported Graph method')
        if decision.operation=='read' and method!='GET':raise CapabilityDenied('read grant cannot perform a Graph write')
        if method!='GET':raise CapabilityDenied('Graph writes require an exact precommitted action, not this read adapter')
        # Refresh before final policy locks, then hold connection through I/O.
        self.connections.credential(owner=self.owner_ref,connection_ref=self.connection_ref,account_ref=self.account_ref)
        def transport():
            return self._guarded_http(path=path,method=method,body=body,headers=headers)
        reservation=decision.reservation
        if reservation._transport_committed:return self.registry.execute_prepared(reservation,transport)
        return self.registry.execute_reserved((reservation,),transport)

    def _guarded_http(self,*,path,method,body,headers):
        with self.connections.store.transaction() as tx:
            row=tx.conn.execute('SELECT * FROM pa_connections.accounts WHERE owner=%s AND id=%s FOR UPDATE',(self.owner_ref,self.connection_ref)).fetchone()
            now=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            if not row or row['status']!='connected' or row['account_ref']!=self.account_ref or row['expires']<=now:
                raise CapabilityDenied('Graph connection revoked or expired')
            token=self.connections.vault.get(row['secret_ref'])['access_token']
            data=None if body is None else json.dumps(body,ensure_ascii=False).encode()
            if data is not None and len(data)>64000:raise StorageError('Graph request exceeds bound')
            selected={'Accept':'application/json','Authorization':'Bearer '+token,
                      'Prefer':'IdType="ImmutableId"',**(headers or {})}
            if data is not None:selected['Content-Type']='application/json'
            try:
                with build_opener(ProxyHandler({}),NoRedirect()).open(Request(self.connections.graph_origin+path,data=data,headers=selected,method=method),timeout=8) as response:
                    raw=response.read(256001)
                    if len(raw)>256000:raise StorageError('Graph response exceeds bound')
                    value=json.loads(raw) if raw else {}
                    receipt={'status':response.status,'etag':response.headers.get('ETag',''),'request_id':response.headers.get('request-id','')}
            except HTTPError as error:
                if error.code==429:raise GraphRateLimited('Graph rate limited; bounded job retry required') from None
                if error.code==410:raise GraphDeltaReset('Graph delta requires a bounded full sync') from None
                raise StorageError('Graph request rejected') from None
            except Exception:raise StorageError('Graph transport outcome unknown') from None
            if tx.conn.closed:raise StorageError('Graph connection guard lost')
            return value,receipt

    def raw_request(self,*,action,path,method,body,headers):
        proposal=action.proposal
        expected=(proposal.owner_ref,proposal.connection_ref,proposal.resource_ref,'assistant.action_execute','write','provider_microsoft_graph','action.execute')
        if not any((request.owner_ref,request.connection_ref,request.resource_ref,request.capability,request.operation,request.provider_ref,request.purpose)==expected
                   for request in self.registry.current_transport_requests):
            raise CapabilityDenied('Graph write lacks the active final policy guard')
        with self.connections.store.transaction() as tx:
            row=tx.conn.execute('SELECT receipt FROM pa_actions.attempts WHERE owner=%s AND key=%s',(proposal.owner_ref,action.idempotency_key)).fetchone()
            if not row or row['receipt']['status']!='unknown' or row['receipt']['content_digest']!=proposal.digest:
                raise CapabilityDenied('exact precommitted action attempt required')
        return self._guarded_http(path=path,method=method,body=body,headers=headers)

    def background_metadata_read(self,*,source_ref,path):
        if not any((request.owner_ref,request.connection_ref,request.resource_ref,request.provider_ref,request.capability,request.purpose)
                   ==(self.owner_ref,self.connection_ref,source_ref,'provider_microsoft_graph','assistant.watch_collection','watch.collection')
                   for request in self.registry.current_transport_requests):
            raise CapabilityDenied('Graph background read lacks separate current collection authority')
        if not path.startswith('/v1.0/me/mailFolders/') or '/messages?' not in path:
            raise CapabilityDenied('background endpoint is not selected metadata mail')
        fields=parse_qs(urlsplit(path).query).get('$select',[''])[0].split(',')
        if set(fields)-set(GraphMailAdapter.FIELDS):raise CapabilityDenied('background collection widened fields')
        return self._guarded_http(path=path,method='GET',body=None,headers=None)

    def next_path(self,link,*,base_path,allowed_fields):
        parsed=urlsplit(link);origin=urlsplit(self.connections.graph_origin)
        if (parsed.scheme,parsed.netloc)!=(origin.scheme,origin.netloc) or parsed.path!=base_path or parsed.fragment or parsed.username:
            raise CapabilityDenied('Graph page changed account/source endpoint')
        params=parse_qs(parsed.query)
        if any(set(value.split(','))-set(allowed_fields) for value in params.get('$select',[])):
            raise CapabilityDenied('Graph cursor widened selected fields')
        if set(params)-{'$select','$top','$skiptoken','$deltatoken','startDateTime','endDateTime','$filter','$orderby'}:
            raise CapabilityDenied('unsupported Graph cursor parameter')
        return parsed.path+('?' + parsed.query if parsed.query else '')


class GraphMailAdapter:
    FIELDS=('id','subject','from','receivedDateTime','conversationId','parentFolderId','webLink','isRead')
    def __init__(self,transport):self.transport=transport;self.store=PostgresStore(transport.registry.store.target)

    def sync(self,selection,*,max_pages=4):
        if not 1<=max_pages<=10 or len(selection.folders)!=1:raise StorageError('one exact selected folder and bounded pages required')
        owner=self.transport.owner_ref;connection=self.transport.connection_ref;scope=selection.scope_digest
        folder=quote(selection.folders[0],safe='');base='/v1.0/me/mailFolders/'+folder+'/messages/delta'
        with self.store.transaction() as tx:
            state=tx.conn.execute('SELECT * FROM pa_sources.sync WHERE owner=%s AND connection_ref=%s AND kind=%s AND scope_digest=%s',
                                 (owner,connection,'mail',scope)).fetchone()
        cursor=state['cursor'] if state else None;revision=state['revision'] if state else 0;total=0;partial=True
        for page in range(max_pages):
            path=self.transport.next_path(cursor,base_path=base,allowed_fields=self.FIELDS) if cursor else base+'?'+urlencode({'$select':','.join(self.FIELDS),'$top':min(selection.max_items,50)})
            decision=self.transport.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=owner,connection_ref=connection,
                capability='assistant.mail_read',resource_ref=selection.resource_ref,operation='read',data_class='private_connector_metadata',
                provider_ref='provider_microsoft_graph',purpose='mail.read',operation_ref='mailsync_'+__import__('uuid').uuid4().hex),upper_bound=self.transport.upper_bound)
            if not decision.allowed:raise CapabilityDenied(decision.reason)
            try:value,receipt=self.transport.request(decision,path=path)
            except GraphDeltaReset:
                with self.store.transaction() as tx:
                    tx.conn.execute('UPDATE pa_sources.sync SET cursor=NULL,completed=false,revision=revision+1 WHERE owner=%s AND connection_ref=%s AND kind=%s AND scope_digest=%s AND revision=%s',
                                   (owner,connection,'mail',scope,revision))
                return {'status':'delta_reset','processed':total,'coverage':'full_resync_required'}
            rows=value.get('value')
            if not isinstance(rows,list) or len(rows)>selection.max_items:raise StorageError('mail page exceeds selected bound')
            next_link=value.get('@odata.nextLink') or value.get('@odata.deltaLink')
            if next_link:self.transport.next_path(next_link,base_path=base,allowed_fields=self.FIELDS)
            with self.store.transaction() as tx:
                account=tx.conn.execute('SELECT status FROM pa_connections.accounts WHERE owner=%s AND id=%s FOR UPDATE',(owner,connection)).fetchone()
                if not account or account['status']!='connected':raise CapabilityDenied('connection revoked before page commit')
                existing=tx.conn.execute('SELECT revision FROM pa_sources.sync WHERE owner=%s AND connection_ref=%s AND kind=%s AND scope_digest=%s FOR UPDATE',
                                        (owner,connection,'mail',scope)).fetchone()
                if (existing['revision'] if existing else 0)!=revision:raise StateConflict('another sync advanced this selected source')
                for row in rows:
                    if not isinstance(row,dict) or not isinstance(row.get('id'),str):raise StorageError('invalid mail record')
                    deleted='@removed' in row;payload={key:row[key] for key in self.FIELDS if key in row};payload['scope_digest']=scope
                    if not deleted:
                        address=row.get('from',{}).get('emailAddress',{}).get('address','');domain=address.rsplit('@',1)[-1].casefold()
                        moment=datetime.fromisoformat(row['receivedDateTime'].replace('Z','+00:00'))
                        if selection.sender_domains and domain not in selection.sender_domains:continue
                        if selection.since and moment<selection.since or selection.until and moment>=selection.until:continue
                    digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
                    tx.conn.execute('''INSERT INTO pa_sources.items(owner,connection_ref,kind,id,version,payload,deleted) VALUES(%s,%s,'mail',%s,%s,%s,%s)
                        ON CONFLICT(owner,connection_ref,kind,id) DO UPDATE SET version=excluded.version,payload=excluded.payload,deleted=excluded.deleted,updated_at=clock_timestamp()''',
                        (owner,connection,row['id'],digest,Jsonb(payload),deleted));total+=1
                partial=bool(value.get('@odata.nextLink'));revision+=1
                tx.conn.execute('''INSERT INTO pa_sources.sync(owner,connection_ref,kind,scope_digest,revision,cursor,completed) VALUES(%s,%s,'mail',%s,%s,%s,%s)
                    ON CONFLICT(owner,connection_ref,kind,scope_digest) DO UPDATE SET revision=excluded.revision,cursor=excluded.cursor,completed=excluded.completed,updated_at=clock_timestamp()''',
                    (owner,connection,scope,revision,next_link,not partial))
            cursor=next_link
            if not partial:break
        return {'status':'partial' if partial else 'synced','processed':total,'metadata_only':True,'coverage':'selected_folder_app_filter'}

    def fetch_page(self,request):
        if request.authorization is not None and request.authorization.data_class=='private_connector_metadata':
            require_authorized_operation(request.authorization,capability='assistant.mail_read',operation='read',provider_ref='provider_microsoft_graph',
                data_class='private_connector_metadata',owner_ref=request.owner_ref,connection_ref=request.connection_ref,
                resource_ref=request.selection.resource_ref,purpose='mail.read')
        else:require_mail_read_access(request)
        selection=request.selection
        if len(selection.folders)!=1:raise CapabilityDenied('one exact selected mail folder per page')
        base='/v1.0/me/mailFolders/'+quote(selection.folders[0],safe='')+'/messages'
        path=base+'?'+urlencode({'$select':','.join(self.FIELDS),'$top':request.page_size})
        if request.cursor:
            item=self.store.get(request.owner_ref,'conversation',request.cursor,version=1)
            if item is None or item.payload['scope_digest']!=selection.scope_digest or item.payload['connection_ref']!=request.connection_ref:
                raise CapabilityDenied('mail continuation owner/scope differs')
            path=self.transport.next_path(item.payload['url'],base_path=base,allowed_fields=self.FIELDS)
        value,receipt=self.transport.request(request.authorization,path=path)
        rows=value.get('value',[])
        if not isinstance(rows,list) or len(rows)>request.page_size:raise StorageError('mail page exceeds selected size')
        output=[]
        for row in rows:
            address=row.get('from',{}).get('emailAddress',{}).get('address','');domain=address.rsplit('@',1)[-1].casefold()
            if selection.sender_domains and domain not in selection.sender_domains:continue
            moment=datetime.fromisoformat(row['receivedDateTime'].replace('Z','+00:00'))
            if selection.since and moment<selection.since or selection.until and moment>=selection.until:continue
            output.append(MailMessage('message_'+hashlib.sha256(row['id'].encode()).hexdigest()[:32],
                'thread_'+hashlib.sha256(row.get('conversationId',row['id']).encode()).hexdigest()[:32],moment,domain,row.get('subject','')[:240],row.get('subject','')[:400]))
        cursor=None;link=value.get('@odata.nextLink')
        if link:
            self.transport.next_path(link,base_path=base,allowed_fields=self.FIELDS)
            cursor='cursor_'+hashlib.sha256((request.owner_ref+selection.scope_digest+link).encode()).hexdigest()[:40]
            payload={'url':link,'scope_digest':selection.scope_digest,'connection_ref':request.connection_ref}
            old=self.store.get(request.owner_ref,'conversation',cursor,version=1)
            if old is None:self.store.put(request.owner_ref,'conversation',cursor,payload,expected_version=0)
            elif old.payload!=payload:raise StateConflict('mail cursor identity differs')
        return MailFetchPage(tuple(output),cursor,cursor is not None)

    def summary(self,selection):
        with self.store.transaction() as tx:
            account=tx.conn.execute('SELECT status FROM pa_connections.accounts WHERE owner=%s AND id=%s',(self.transport.owner_ref,self.transport.connection_ref)).fetchone()
            if not account or account['status']!='connected':raise CapabilityDenied('mail connection revoked')
            rows=tx.conn.execute("SELECT payload FROM pa_sources.items WHERE owner=%s AND connection_ref=%s AND kind='mail' AND NOT deleted AND payload->>'scope_digest'=%s ORDER BY updated_at DESC LIMIT %s",
                                (self.transport.owner_ref,self.transport.connection_ref,selection.scope_digest,selection.max_items)).fetchall()
        items=[row['payload'] for row in rows]
        return {'text':'\n'.join(str(item.get('subject','Без темы'))+' — '+str(item.get('webLink','')) for item in items[:10]) or 'В выбранном покрытии писем нет.',
                'items':items,'limitation':'Metadata does not prove reply obligation, deadline or body content. Exact wider scope is required when insufficient.'}
    def brief_evidence(self,selection,window):
        with self.store.transaction() as tx:
            state=tx.conn.execute("SELECT completed FROM pa_sources.sync WHERE owner=%s AND connection_ref=%s AND kind='mail' AND scope_digest=%s",
                (self.transport.owner_ref,self.transport.connection_ref,selection.scope_digest)).fetchone()
            if not state or not state['completed']:raise StorageError('mail coverage not yet synchronized')
        summary=self.summary(selection);output=[]
        for item in summary['items']:
            if not window.contains(datetime.fromisoformat(item['receivedDateTime'].replace('Z','+00:00'))):continue
            output.append({'evidence_id':'mail:'+hashlib.sha256(item['id'].encode()).hexdigest()[:32],
                'source_url':item.get('webLink') or 'https://graph.microsoft.com/v1.0/me/messages/'+quote(item['id'],safe=''),
                'title':item.get('subject') or 'Письмо','support_span':item.get('subject') or 'Письмо без темы',
                'posted_at':item['receivedDateTime'],'local_source_provenance':True,'source_kind':'mail',
                'source_owner_ref':self.transport.owner_ref,'importance':'medium','source_state':'active'})
        return output


class GraphCalendarAdapter:
    FIELDS=('id','subject','start','end','isAllDay','isCancelled','type','seriesMasterId','changeKey','webLink')
    def __init__(self,transport):self.transport=transport
    def fetch_page(self,request):
        if request.authorization is not None and request.authorization.data_class=='private_connector_metadata':
            require_authorized_operation(request.authorization,capability='assistant.calendar_read',operation='read',provider_ref='provider_microsoft_graph',
                data_class='private_connector_metadata',owner_ref=request.owner_ref,connection_ref=request.connection_ref,
                resource_ref=request.selection.account_ref,purpose='calendar.read')
        else:require_calendar_read_access(request)
        selection=request.selection
        if selection.account_ref!=self.transport.account_ref or len(selection.calendar_refs)!=1:raise CapabilityDenied('calendar account or selection differs')
        calendar=selection.calendar_refs[0];base='/v1.0/me/calendars/'+quote(calendar,safe='')+'/calendarView'
        path=self.transport.next_path(request.cursor,base_path=base,allowed_fields=self.FIELDS) if request.cursor else base+'?'+urlencode({
            'startDateTime':selection.window_start.isoformat(),'endDateTime':selection.window_end.isoformat(),'$select':','.join(self.FIELDS),'$top':min(selection.max_items,100)})
        value,receipt=self.transport.request(request.authorization,path=path,headers={'Prefer':'IdType="ImmutableId", outlook.timezone="UTC"'})
        rows=value.get('value',[])
        if not isinstance(rows,list) or len(rows)>selection.max_items:raise StorageError('calendar page exceeds bound')
        self.next_cursor=value.get('@odata.nextLink')
        if self.next_cursor:self.transport.next_path(self.next_cursor,base_path=base,allowed_fields=self.FIELDS)
        output=[]
        for row in rows:
            def moment(field):
                value=row[field];parsed=datetime.fromisoformat(value['dateTime'].replace('Z','+00:00'))
                if parsed.tzinfo is None:
                    from zoneinfo import ZoneInfo
                    parsed=parsed.replace(tzinfo=ZoneInfo(value.get('timeZone','UTC')))
                return parsed
            output.append(CalendarEvent(row['id'],calendar,selection.account_ref,row.get('subject','')[:240],moment('start'),moment('end'),'UTC',
                status='cancelled' if row.get('isCancelled') else 'confirmed',all_day=bool(row.get('isAllDay')),
                is_recurring=row.get('type') in {'occurrence','exception'},recurrence_id=row.get('seriesMasterId'),version=row.get('changeKey',''),source_ref=row.get('webLink','')))
        return tuple(output)


class GraphContactsAdapter:
    FIELDS=('id','displayName','emailAddresses')
    def __init__(self,transport):self.transport=transport
    def fetch_page(self,request):
        if request.authorization is not None and request.authorization.data_class=='private_connector_metadata':
            require_authorized_operation(request.authorization,capability='assistant.contacts_read',operation='read',provider_ref='provider_microsoft_graph',
                data_class='private_connector_metadata',owner_ref=request.owner_ref,connection_ref=request.connection_ref,
                resource_ref=request.account_ref,purpose='contacts.read')
        else:require_contacts_read_access(request)
        if request.account_ref!=self.transport.account_ref:raise CapabilityDenied('contacts account differs')
        base='/v1.0/me/contacts'
        path=self.transport.next_path(request.cursor,base_path=base,allowed_fields=self.FIELDS) if request.cursor else base+'?'+urlencode({'$select':','.join(self.FIELDS),'$top':request.page_size})
        value,receipt=self.transport.request(request.authorization,path=path);rows=value.get('value',[])
        if not isinstance(rows,list) or len(rows)>request.page_size:raise StorageError('contacts page exceeds bound')
        self.next_cursor=value.get('@odata.nextLink')
        if self.next_cursor:self.transport.next_path(self.next_cursor,base_path=base,allowed_fields=self.FIELDS)
        output=[]
        for row in rows:
            if request.query and request.query.casefold() not in row.get('displayName','').casefold():continue
            emails=tuple(item['address'] for item in row.get('emailAddresses',[]) if isinstance(item.get('address'),str))
            if emails:output.append(Contact(row['id'],request.account_ref,row.get('displayName','')[:160],emails[:8]))
        return tuple(output)
