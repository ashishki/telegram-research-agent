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
