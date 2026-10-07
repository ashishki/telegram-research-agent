"""Executable review counterexamples and recovery under real synthetic stores."""
from datetime import timedelta
from dataclasses import replace
from urllib.parse import parse_qs,urlsplit
import pytest
from tests.pai_runtime_fixtures import pai,graph,allow
from prm.capabilities import AuthorizationRequest,CapabilityDenied,require_authorized_operation
from prm.storage.postgres import StorageError


def test_reservation_current_storage_failure_is_a_bounded_denial(pai,monkeypatch):
    grant=allow(pai,'model.generate','resource_review','user_provided','answer.request')
    decision=pai.root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=grant.owner_ref,connection_ref='connection_fixture',
        capability='model.generate',resource_ref='resource_review',operation='model_egress',data_class='user_provided',
        provider_ref='provider_openai',purpose='answer.request',operation_ref='review_current_denial'),upper_bound=1)
    assert decision.reservation.current
    def unavailable(*args,**kwargs):raise StorageError('synthetic policy outage')
    monkeypatch.setattr(pai.root.registry,'_decision',unavailable)
    assert decision.reservation.current is False
    assert not pai.requests


def test_changed_oauth_scopes_require_new_connection_and_owner_handshake(pai):
    manager,transport,actor=graph(pai);before=len(pai.requests);before_files=set(manager.vault.path.iterdir())
    with pytest.raises(CapabilityDenied,match='changed OAuth scopes'):
        manager.begin(connection_ref=transport.connection_ref,account_ref=transport.account_ref,scopes=('User.Read','Mail.Read'),**actor)
    assert len(pai.requests)==before and set(manager.vault.path.iterdir())==before_files
    url=manager.begin(connection_ref='connection_new_scopes',account_ref=transport.account_ref,scopes=('User.Read','Mail.Read'),**actor)
    manager.callback(state=parse_qs(urlsplit(url).query)['state'][0],code='synthetic_new_code',redirect_uri=manager.redirect,**actor)
    assert manager.status(owner=pai.root.owner_ref,connection_ref='connection_new_scopes')['scopes']==['User.Read','Mail.Read']
    assert manager.status(owner=pai.root.owner_ref,connection_ref=transport.connection_ref)['scopes']!=['User.Read','Mail.Read']


def test_committed_token_retirement_survives_cleanup_failure_and_restart(pai,monkeypatch):
    from prm.runtime.connections import GraphOAuth
    manager,transport,actor=graph(pai)
    with manager.store.transaction() as tx:
        old=tx.conn.execute('SELECT secret_ref FROM pa_connections.accounts WHERE owner=%s AND id=%s',(pai.root.owner_ref,transport.connection_ref)).fetchone()['secret_ref']
    scopes=tuple(manager.status(owner=pai.root.owner_ref,connection_ref=transport.connection_ref)['scopes'])
    url=manager.begin(connection_ref=transport.connection_ref,account_ref=transport.account_ref,scopes=scopes,**actor)
    delete=manager.vault.delete
    def unavailable(ref):
        if ref==old:raise OSError('synthetic unlink failure')
        return delete(ref)
    with monkeypatch.context() as failure:
        failure.setattr(manager.vault,'delete',unavailable)
        manager.callback(state=parse_qs(urlsplit(url).query)['state'][0],code='synthetic_rotated_code',redirect_uri=manager.redirect,**actor)
    assert (manager.vault.path/old).exists()
    restarted=GraphOAuth(target=pai.pg.app,vault=manager.vault,client_id=manager.client_id,tenant=manager.tenant,redirect_uri=manager.redirect,
        authority=pai.origin,graph_origin=pai.origin,synthetic=True)
    assert restarted.cleanup_retired(owner=pai.root.owner_ref)=={'completed':1,'pending_in_batch':0}
    assert not (manager.vault.path/old).exists()
    assert restarted.credential(owner=pai.root.owner_ref,connection_ref=transport.connection_ref,account_ref=transport.account_ref)=='synthetic_access_fixture'


def test_missing_active_token_requests_interactive_reconnect_without_http(pai):
    manager,transport,_=graph(pai)
    with manager.store.transaction() as tx:
        ref=tx.conn.execute('SELECT secret_ref FROM pa_connections.accounts WHERE owner=%s AND id=%s',(pai.root.owner_ref,transport.connection_ref)).fetchone()['secret_ref']
    manager.vault.delete(ref);before=len(pai.requests)
    with pytest.raises(CapabilityDenied,match='interactive reconnect required'):
        manager.credential(owner=pai.root.owner_ref,connection_ref=transport.connection_ref,account_ref=transport.account_ref)
    assert len(pai.requests)==before


def test_refresh_ack_loss_keeps_a_durable_fence_across_reconstructed_clients(pai):
    from prm.runtime.connections import GraphOAuth,CredentialRefreshUnknown
    manager,transport,actor=graph(pai)
    with manager.store.transaction() as tx:
        row=tx.conn.execute('SELECT secret_ref FROM pa_connections.accounts WHERE owner=%s AND id=%s',(pai.root.owner_ref,transport.connection_ref)).fetchone()
        bundle=manager.vault.get(row['secret_ref']);bundle['refresh_token']='synthetic_ack_loss_refresh'
        manager.vault.delete(row['secret_ref']);ref=manager.vault.put(bundle)
        tx.conn.execute('UPDATE pa_connections.accounts SET secret_ref=%s,expires=%s WHERE owner=%s AND id=%s',(ref,pai.now-timedelta(seconds=1),pai.root.owner_ref,transport.connection_ref))
    with pytest.raises(CredentialRefreshUnknown) as failure:
        manager.credential(owner=pai.root.owner_ref,connection_ref=transport.connection_ref,account_ref=transport.account_ref)
    assert not failure.value.retry_allowed
    restarted=GraphOAuth(target=pai.pg.app,vault=manager.vault,client_id=manager.client_id,tenant=manager.tenant,redirect_uri=manager.redirect,
        authority=pai.origin,graph_origin=pai.origin,synthetic=True)
    assert restarted.status(owner=pai.root.owner_ref,connection_ref=transport.connection_ref)['status']=='awaiting_refresh'
    with pytest.raises(CapabilityDenied):restarted.credential(owner=pai.root.owner_ref,connection_ref=transport.connection_ref,account_ref=transport.account_ref)
    assert len([row for row in pai.requests if row[0]=='oauth' and row[2].get('grant_type')==['refresh_token']])==1
    scopes=tuple(restarted.status(owner=pai.root.owner_ref,connection_ref=transport.connection_ref)['scopes'])
    url=restarted.begin(connection_ref=transport.connection_ref,account_ref=transport.account_ref,scopes=scopes,**actor)
    restarted.callback(state=parse_qs(urlsplit(url).query)['state'][0],code='synthetic_reconnect',redirect_uri=manager.redirect,**actor)
    assert restarted.credential(owner=pai.root.owner_ref,connection_ref=transport.connection_ref,account_ref=transport.account_ref)=='synthetic_access_fixture'


def test_successful_refresh_commits_fence_before_http_and_reuses_only_new_token(pai,monkeypatch):
    manager,transport,_=graph(pai)
    with manager.store.transaction() as tx:
        tx.conn.execute('UPDATE pa_connections.accounts SET expires=%s WHERE owner=%s AND id=%s',(pai.now-timedelta(seconds=1),pai.root.owner_ref,transport.connection_ref))
    http=manager._http;observed=[]
    def inspect_fence(url,**kwargs):
        observed.append(manager.status(owner=pai.root.owner_ref,connection_ref=transport.connection_ref)['status'])
        return http(url,**kwargs)
    monkeypatch.setattr(manager,'_http',inspect_fence)
    for _ in range(2):assert manager.credential(owner=pai.root.owner_ref,connection_ref=transport.connection_ref,account_ref=transport.account_ref)=='synthetic_access_fixture'
    assert observed==['awaiting_refresh']
    assert manager.status(owner=pai.root.owner_ref,connection_ref=transport.connection_ref)['status']=='connected'
    assert len([row for row in pai.requests if row[0]=='oauth' and row[2].get('grant_type')==['refresh_token']])==1


def test_calendar_narrowing_and_partial_coverage_preserve_other_calendar_records(pai):
    from prm.runtime.schedule import GraphScheduleRuntime
    from prm.schedule_connectors import CalendarScopeSelection
    _,transport,_=graph(pai)
    allow(pai,'assistant.calendar_read',transport.account_ref,'private_connector_metadata','calendar.read',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    runtime=GraphScheduleRuntime(transport)
    selection=CalendarScopeSelection('provider_microsoft_graph',transport.account_ref,('calendar_one','calendar_two'),pai.now,pai.now+timedelta(days=2),'UTC')
    assert runtime.read_calendar(selection)['coverage_complete']
    assert runtime.read_calendar(replace(selection,calendar_refs=('calendar_one',)))['coverage_complete']
    assert not runtime.read_calendar(selection,max_pages=1)['coverage_complete']
    with transport.connections.store.transaction() as tx:
        rows=tx.conn.execute("SELECT id,deleted FROM pa_sources.items WHERE owner=%s AND connection_ref=%s AND kind='calendar' AND payload->>'calendar_ref'='calendar_two'",(pai.root.owner_ref,transport.connection_ref)).fetchall()
    assert len(rows)==2 and all(not row['deleted'] for row in rows)


def test_unknown_action_ack_loss_is_explicit_and_restart_cannot_send_again(pai):
    from prm.runtime.actions import ActionRuntime
    _,transport,_=graph(pai)
    allow(pai,'assistant.action_execute','resource_mail','private_connector_content','action.execute',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='write')
    runtime=ActionRuntime(pai.root,graph_transport=transport,upper_bound=0)
    preview=runtime.preview(action_code='mail.send',resource_ref='resource_mail',content={'to':['synthetic@example.test'],'subject':'Synthetic ACK-loss mail','body':'Synthetic body'},rationale_refs=('source_fixture',))
    receipt=runtime.confirm_and_execute(preview.proposal_ref,actor_ref=pai.root.owner_ref)
    assert receipt.status=='unknown' and not receipt.retry_allowed
    assert receipt.error_code=='action_storage_unavailable'
    restarted=ActionRuntime(pai.root,graph_transport=transport,upper_bound=0)
    assert restarted.confirm_and_execute(preview.proposal_ref,actor_ref=pai.root.owner_ref)==receipt
    assert len([row for row in pai.requests if row[0]=='write'])==1


def test_body_read_rejects_unselected_ids_before_http_and_provenance_is_not_authority(pai):
    from prm.runtime.graph import GraphMailAdapter
    from prm.mail_connector import MailScopeSelection
    _,transport,_=graph(pai)
    selected=MailScopeSelection('provider_microsoft_graph',transport.account_ref,folders=('inbox',),sender_domains=('example.test',))
    allow(pai,'assistant.mail_read',selected.resource_ref,'private_connector_metadata','mail.read',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    adapter=GraphMailAdapter(transport);adapter.sync(selected)
    allow(pai,'assistant.mail_read','message_outside','private_connector_content','mail.read',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    before=len(pai.requests)
    with pytest.raises(CapabilityDenied,match='sync selected message metadata'):
        adapter.read_message(selected,'message_outside')
    assert len(pai.requests)==before
    allow(pai,'assistant.mail_read','message_1','private_connector_content','mail.read',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    result=adapter.read_message(selected,'message_1')
    assert result['content']=='Synthetic selected body.'
    assert pai.requests[-1][1].startswith('/v1.0/me/mailFolders/inbox/messages/message_1?')
    scope=result['source_scope'];assert isinstance(scope,dict) and scope['operation_ref'] is None
    decision=pai.root.registry.authorize(AuthorizationRequest(**scope))
    assert decision.allowed and decision.reservation is None
    before=len(pai.requests)
    for candidate in (scope,decision):
        with pytest.raises(CapabilityDenied,match='exact shared-policy reservation'):
            transport.request(candidate,path='/v1.0/me/messages/message_1')
    assert len(pai.requests)==before
    with pytest.raises(CapabilityDenied):require_authorized_operation(decision,capability='assistant.mail_read',operation='read',
        provider_ref='provider_microsoft_graph',data_class='private_connector_content',owner_ref=pai.root.owner_ref,
        connection_ref=transport.connection_ref,resource_ref='message_1',purpose='mail.read')


@pytest.mark.parametrize('failure_type,label',[(CapabilityDenied,'scope_denied'),(OSError,'unavailable')])
def test_late_academic_scope_denial_is_distinct_from_transport_failure(pai,failure_type,label):
    from prm.runtime.academic import CanvasReadAdapter
    from prm.academic_inbox import CanvasScopeSelection
    allow(pai,'assistant.academic_read','account_canvas','private_connector_content','academic.read',provider='provider_canvas',connection='connection_canvas',operation='read')
    def failed(path):raise failure_type('synthetic source failure')
    adapter=CanvasReadAdapter(registry=pai.root.registry,origin='https://canvas.example.test',credential='synthetic',synthetic_transport=failed)
    selection=CanvasScopeSelection('provider_canvas','account_canvas',('course_12',),pai.now,pai.now+timedelta(days=2),'UTC',include_announcements=False,include_calendar=False)
    result=adapter.collect(selection,owner_ref=pai.root.owner_ref,connection_ref='connection_canvas',upper_bound=0)
    assert result['candidates']==() and result['complete'] is False
    assert 'course_12:assignments:'+label in result['coverage'] and not any(value.endswith(':checked') for value in result['coverage'])


def test_calendar_preview_and_edit_validate_timezone_and_read_window_bound(pai):
    from prm.runtime.actions import ActionRuntime
    from zoneinfo import ZoneInfoNotFoundError
    _,transport,_=graph(pai);runtime=ActionRuntime(pai.root,graph_transport=transport,upper_bound=0)
    content={'calendar_ref':'calendar_fixture','title':'Synthetic','start_at':pai.now.isoformat(),'end_at':(pai.now+timedelta(hours=1)).isoformat(),'timezone':'UTC'}
    before=len(pai.requests)
    with pytest.raises(ZoneInfoNotFoundError):runtime.preview(action_code='calendar.create',resource_ref='resource_calendar',content={**content,'timezone':'Invalid/Zone'},rationale_refs=('fixture',))
    with pytest.raises(CapabilityDenied,match='370 days'):runtime.preview(action_code='calendar.create',resource_ref='resource_calendar',content={**content,'end_at':(pai.now+timedelta(days=371)).isoformat()},rationale_refs=('fixture',))
    preview=runtime.preview(action_code='calendar.create',resource_ref='resource_calendar',content=content,rationale_refs=('fixture',))
    with pytest.raises(CapabilityDenied,match='370 days'):runtime.edit(preview,content={**content,'end_at':(pai.now+timedelta(days=371)).isoformat()})
    assert len(pai.requests)==before and not runtime.store.all()
