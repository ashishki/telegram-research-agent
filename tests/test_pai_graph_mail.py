"""Deferred real multi-page Graph adapter with transactional cursor state."""
import pytest
from tests.pai_runtime_fixtures import pai,graph,allow
from prm.runtime.graph import GraphMailAdapter
from prm.mail_connector import MailScopeSelection
from prm.capabilities import CapabilityDenied


def test_actual_mail_pages_commit_minimal_fields_and_selected_scope(pai):
    manager,transport,actor=graph(pai)
    allow(pai,'assistant.mail_read','resource_selected_mail','private_connector_metadata','mail.read',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    selection=MailScopeSelection('provider_microsoft_graph','resource_selected_mail',folders=('inbox',),sender_domains=('example.test',))
    adapter=GraphMailAdapter(transport);result=adapter.sync(selection)
    assert result['status']=='synced' and result['processed']==2
    summary=adapter.summary(selection)
    assert len(summary['items'])==2 and all('body' not in item and 'attachments' not in item for item in summary['items'])
    assert 'reply obligation' in summary['limitation']
    manager.revoke(connection_ref=transport.connection_ref,**actor)
    with pytest.raises(CapabilityDenied):adapter.summary(selection)


def test_reused_mail_cursor_still_requires_exact_selection_and_current_grant(pai):
    from dataclasses import replace
    from prm.capabilities import AuthorizationRequest
    from prm.mail_connector import MailFetchRequest
    manager,transport,actor=graph(pai)
    grant=allow(pai,'assistant.mail_read','resource_selected_mail','private_connector_content','mail.read',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    selection=MailScopeSelection('provider_microsoft_graph','resource_selected_mail',folders=('inbox',))
    adapter=GraphMailAdapter(transport)
    def access(ref):
        return pai.root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=pai.root.owner_ref,connection_ref=transport.connection_ref,
            capability='assistant.mail_read',resource_ref=selection.resource_ref,operation='read',data_class='private_connector_content',
            provider_ref='provider_microsoft_graph',purpose='mail.read',operation_ref=ref),upper_bound=0)
    request=MailFetchRequest(access('cursor_first'),pai.root.owner_ref,transport.connection_ref,selection)
    first=adapter.fetch_page(request);before=len(pai.requests)
    changed=replace(request,authorization=access('cursor_changed'),selection=replace(selection,folders=('otherfolder',)),cursor=first.next_cursor)
    with pytest.raises(CapabilityDenied,match='continuation owner/scope'):adapter.fetch_page(changed)
    assert len(pai.requests)==before
    pai.root.registry.revoke_grant(grant.grant_id,owner_ref=pai.root.owner_ref)
    with pytest.raises(CapabilityDenied):adapter.fetch_page(replace(request,cursor=first.next_cursor))
    assert len(pai.requests)==before


@pytest.mark.parametrize('row',[{'receivedDateTime':'not-a-date'},{'receivedDateTime':'2026-01-01T12:00:00'},{'from':[],'receivedDateTime':'2026-01-01T12:00:00Z'},{'from':None,'receivedDateTime':'2026-01-01T12:00:00Z'}])
def test_malformed_mail_metadata_raises_typed_storage_error(row):
    from prm.runtime.graph import _mail_metadata
    from prm.storage.postgres import StorageError
    with pytest.raises(StorageError,match='mail metadata shape differs'):_mail_metadata(row)


@pytest.mark.parametrize('changed',[{'receivedDateTime':'invalid'},{'from':None},{'body':None},{'body':{'contentType':[]}}])
def test_selected_mail_body_malformed_provider_shape_is_typed(pai,monkeypatch,changed):
    from prm.storage.postgres import StorageError
    manager,transport,actor=graph(pai)
    selection=MailScopeSelection('provider_microsoft_graph','resource_selected_mail',folders=('inbox',))
    allow(pai,'assistant.mail_read',selection.resource_ref,'private_connector_metadata','mail.read',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    adapter=GraphMailAdapter(transport);adapter.sync(selection)
    message=adapter.summary(selection)['items'][0]['id']
    allow(pai,'assistant.mail_read',message,'private_connector_content','mail.read',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    original=transport.request
    def malformed(*args,**kwargs):
        value,retry=original(*args,**kwargs);return {**value,**changed},retry
    monkeypatch.setattr(transport,'request',malformed)
    with pytest.raises(StorageError):adapter.read_message(selection,message)
