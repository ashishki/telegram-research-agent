"""Deferred real fake-OAuth handshake, vault and owner/revoke checks."""
import pytest
from tests.pai_runtime_fixtures import pai,graph
from prm.capabilities import CapabilityDenied


def test_real_pkce_callback_establishes_account_and_ciphertext_only(pai):
    manager,transport,actor=graph(pai)
    state=manager.status(owner=pai.root.owner_ref,connection_ref=transport.connection_ref)
    assert state['status']=='connected' and state['account_ref']=='account_synthetic'
    assert any(row[0]=='oauth' and 'code_verifier' in row[2] for row in pai.requests)
    assert all(b'synthetic_access_fixture' not in path.read_bytes() for path in manager.vault.path.iterdir())
    manager.revoke(connection_ref=transport.connection_ref,**actor)
    with pytest.raises(CapabilityDenied):manager.credential(owner=pai.root.owner_ref,connection_ref=transport.connection_ref,account_ref='account_synthetic')


def test_foreign_actor_cannot_begin_or_consume_own_oauth_state(pai):
    manager,transport,actor=graph(pai)
    count=len(pai.requests)
    with pytest.raises(CapabilityDenied):manager.begin(connection_ref='connection_foreign',account_ref='account_synthetic',scopes=('User.Read',),**dict(actor,actor_id='99'))
    assert len(pai.requests)==count


def test_retirement_never_deletes_a_reference_active_under_another_owner(pai):
    from psycopg.types.json import Jsonb
    manager,transport,actor=graph(pai)
    ref=manager.vault.put({'access_token':'synthetic_cross_owner_active'})
    with manager.store.transaction() as tx:
        tx.conn.execute("INSERT INTO pa_connections.accounts(owner,id,account_ref,scopes,revision,status,secret_ref,expires) VALUES(%s,%s,%s,%s,1,'connected',%s,clock_timestamp()+interval '1 hour')",
            ('owner_other_fixture','connection_other_fixture','account_other_fixture',Jsonb(['User.Read']),ref))
        manager._queue_retirement(tx,pai.root.owner_ref,ref)
    result=manager.cleanup_retired(owner=pai.root.owner_ref)
    assert result['completed']==0 and result['pending_in_batch']==1
    assert manager.vault.get(ref)['access_token']=='synthetic_cross_owner_active'
