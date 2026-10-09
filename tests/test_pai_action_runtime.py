"""Deferred actual preview/edit/confirm -> Graph HTTP -> exact receipt."""
import pytest
from tests.pai_runtime_fixtures import pai,graph,allow
from prm.runtime.actions import ActionRuntime
from prm.capabilities import CapabilityDenied


def test_edited_preview_confirm_and_double_click_have_one_actual_write(pai):
    manager,transport,actor=graph(pai)
    allow(pai,'assistant.action_execute','resource_selected_mail','private_connector_content','action.execute',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='write')
    runtime=ActionRuntime(pai.root,graph_transport=transport,upper_bound=0)
    preview=runtime.preview(action_code='mail.send',resource_ref='resource_selected_mail',content={'to':['recipient@example.test'],'subject':'Synthetic','body':'First body'},rationale_refs=('source_fixture',))
    edited=runtime.edit(preview,content={**preview.content,'body':'Edited body'})
    assert edited.digest!=preview.digest and edited.version==2
    first=runtime.confirm_and_execute(edited.proposal_ref,actor_ref=pai.root.owner_ref)
    second=runtime.confirm_and_execute(edited.proposal_ref,actor_ref=pai.root.owner_ref)
    assert first==second and first.status=='unknown' and first.provider_operation_ref==''
    allow(pai,'assistant.action_reconciliation','resource_selected_mail','private_connector_metadata','action.reconcile',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    resolved=runtime.reconcile(first.idempotency_key)
    assert resolved.status=='succeeded' and resolved.provider_operation_ref.startswith('synthetic_sent_')
    assert runtime.confirm_and_execute(edited.proposal_ref,actor_ref=pai.root.owner_ref)==resolved
    writes=[row for row in pai.requests if row[0]=='write'];assert len(writes)==1
    assert writes[0][2]['message']['body']['content']=='Edited body'
    with pytest.raises(CapabilityDenied):runtime.confirm_and_execute(edited.proposal_ref,actor_ref='owner_foreign')


def test_calendar_write_checks_free_busy_before_consuming_confirmation(pai):
    from datetime import timedelta
    manager,transport,actor=graph(pai)
    allow(pai,'assistant.calendar_read',transport.account_ref,'private_connector_metadata','calendar.read',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    allow(pai,'assistant.action_execute','resource_selected_calendar','private_connector_content','action.execute',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='write')
    runtime=ActionRuntime(pai.root,graph_transport=transport,upper_bound=0)
    preview=runtime.preview(action_code='calendar.create',resource_ref='resource_selected_calendar',content={'calendar_ref':'calendar_fixture','title':'Synthetic meeting',
        'start_at':(pai.now+timedelta(hours=1)).isoformat(),'end_at':(pai.now+timedelta(hours=2)).isoformat(),'timezone':'Europe/Berlin'},rationale_refs=('source_fixture',))
    with pytest.raises(CapabilityDenied,match='busy'):runtime.confirm_and_execute(preview.proposal_ref,actor_ref=pai.root.owner_ref)
    assert not [row for row in pai.requests if row[0]=='write']
    assert not runtime.store.all()


@pytest.mark.parametrize('ack_loss',[False,True])
@pytest.mark.parametrize('authorized_read',[False,True])
def test_mail_202_and_ack_loss_need_separate_exact_reconciliation_read(pai,ack_loss,authorized_read):
    manager,transport,actor=graph(pai)
    allow(pai,'assistant.action_execute','resource_selected_mail','private_connector_content','action.execute',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='write')
    runtime=ActionRuntime(pai.root,graph_transport=transport,upper_bound=0)
    preview=runtime.preview(action_code='mail.send',resource_ref='resource_selected_mail',content={'to':['recipient@example.test'],
        'subject':'Synthetic ACK-loss mail' if ack_loss else 'Synthetic202','body':'Synthetic content'},rationale_refs=('source_fixture',))
    pending=runtime.confirm_and_execute(preview.proposal_ref,actor_ref=pai.root.owner_ref)
    assert pending.status=='unknown' and pending.provider_operation_ref==''
    reads_before=len([x for x in pai.requests if x[0]=='read'])
    if authorized_read:
        allow(pai,'assistant.action_reconciliation','resource_selected_mail','private_connector_metadata','action.reconcile',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
        resolved=runtime.reconcile(pending.idempotency_key)
        assert resolved.status=='succeeded' and resolved.provider_operation_ref.startswith('synthetic_sent_')
        assert len([x for x in pai.requests if x[0]=='read'])==reads_before+1
    else:
        with pytest.raises(CapabilityDenied):runtime.reconcile(pending.idempotency_key)
        assert len([x for x in pai.requests if x[0]=='read'])==reads_before
    assert runtime.confirm_and_execute(preview.proposal_ref,actor_ref=pai.root.owner_ref)==runtime.store.get(pending.idempotency_key)
    assert len([x for x in pai.requests if x[0]=='write'])==1


def test_mail_reconciliation_denies_missing_oauth_scope_before_http(pai):
    from psycopg.types.json import Jsonb
    manager,transport,actor=graph(pai)
    allow(pai,'assistant.action_execute','resource_selected_mail','private_connector_content','action.execute',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='write')
    allow(pai,'assistant.action_reconciliation','resource_selected_mail','private_connector_metadata','action.reconcile',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    runtime=ActionRuntime(pai.root,graph_transport=transport,upper_bound=0)
    preview=runtime.preview(action_code='mail.send',resource_ref='resource_selected_mail',content={'to':['recipient@example.test'],'subject':'Synthetic scope loss','body':'Synthetic'},rationale_refs=('source_fixture',))
    pending=runtime.confirm_and_execute(preview.proposal_ref,actor_ref=pai.root.owner_ref)
    with manager.store.transaction() as tx:
        tx.conn.execute('UPDATE pa_connections.accounts SET scopes=%s,revision=revision+1 WHERE owner=%s AND id=%s',
            (Jsonb(['User.Read','Mail.Send']),pai.root.owner_ref,transport.connection_ref))
    before=len(pai.requests)
    with pytest.raises(CapabilityDenied,match='provider evidence read scope'):runtime.reconcile(pending.idempotency_key)
    assert len(pai.requests)==before and runtime.store.get(pending.idempotency_key).status=='unknown'


def test_mail_reconciliation_mismatched_digest_keeps_unknown(pai):
    manager,transport,actor=graph(pai)
    allow(pai,'assistant.action_execute','resource_selected_mail','private_connector_content','action.execute',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='write')
    allow(pai,'assistant.action_reconciliation','resource_selected_mail','private_connector_metadata','action.reconcile',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    runtime=ActionRuntime(pai.root,graph_transport=transport,upper_bound=0)
    preview=runtime.preview(action_code='mail.send',resource_ref='resource_selected_mail',content={'to':['recipient@example.test'],'subject':'Synthetic mismatched evidence','body':'Synthetic'},rationale_refs=('source_fixture',))
    pending=runtime.confirm_and_execute(preview.proposal_ref,actor_ref=pai.root.owner_ref)
    sent=next(x[2] for x in pai.requests if x[0]=='write')
    sent['message']['internetMessageHeaders'][1]['value']='different_digest'
    assert runtime.reconcile(pending.idempotency_key).status=='unknown'
    assert runtime.confirm_and_execute(preview.proposal_ref,actor_ref=pai.root.owner_ref)==pending
    assert len([x for x in pai.requests if x[0]=='write'])==1
