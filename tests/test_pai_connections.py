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


def test_secret_store_binding_protects_at_rest_revoke_and_export(pai,capsys):
    import json,stat
    from pathlib import Path
    from cryptography.fernet import Fernet
    from prm.storage.postgres import StorageError
    from prm.runtime.connections import TokenVault
    from prm.runtime.migration import export_domain_delta
    manager,transport,actor=graph(pai)
    with manager.store.transaction() as tx:
        ref=tx.conn.execute('SELECT secret_ref FROM pa_connections.accounts WHERE owner=%s AND id=%s',
            (pai.root.owner_ref,transport.connection_ref)).fetchone()['secret_ref']
    ciphertext=(manager.vault.path/ref).read_bytes()
    assert b'synthetic_access_fixture' not in ciphertext and b'synthetic_refresh_fixture' not in ciphertext
    assert stat.S_IMODE(manager.vault.path.stat().st_mode)==0o700
    assert stat.S_IMODE((manager.vault.path/ref).stat().st_mode)==0o600
    wrong=TokenVault(directory=manager.vault.path,encryption_key=Fernet.generate_key())
    with pytest.raises(StorageError,match='credential unavailable'):wrong.get(ref)
    forbidden=Path(__file__).resolve().parents[1]/'uncreated_synthetic_vault'
    with pytest.raises(StorageError,match='outside application code and Git'):
        TokenVault(directory=forbidden,encryption_key=Fernet.generate_key())
    assert not forbidden.exists()
    pai.ops.kill_switch();exported=json.dumps(export_domain_delta(pai.pg.migrator))
    assert 'synthetic_access_fixture' not in exported and 'synthetic_refresh_fixture' not in exported
    assert ciphertext.decode() not in exported
    manager.revoke(connection_ref=transport.connection_ref,**actor)
    assert not (manager.vault.path/ref).exists()
    captured=capsys.readouterr();assert 'synthetic_access_fixture' not in captured.out+captured.err


def test_same_connection_refresh_is_serialized_before_http(pai,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    manager,transport,actor=graph(pai)
    with manager.store.transaction() as tx:
        tx.conn.execute("UPDATE pa_connections.accounts SET expires=clock_timestamp()-interval '1 second' WHERE owner=%s AND id=%s",
            (pai.root.owner_ref,transport.connection_ref))
    entered,released,second_entered=Event(),Event(),Event();calls=[];original=manager._http
    def held_http(url,**kwargs):
        if kwargs.get('form',{}).get('grant_type')=='refresh_token':
            calls.append(url);entered.set();assert released.wait(5)
        return original(url,**kwargs)
    monkeypatch.setattr(manager,'_http',held_http)
    kwargs={'owner':pai.root.owner_ref,'connection_ref':transport.connection_ref,'account_ref':transport.account_ref}
    def second_credential():
        second_entered.set()
        return manager.credential(**kwargs)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(manager.credential,**kwargs)
        try:
            assert entered.wait(5)
            second=pool.submit(second_credential)
            assert second_entered.wait(5)
        finally:released.set()
        assert first.result(timeout=5)=='synthetic_access_fixture'
        assert second.result(timeout=5)=='synthetic_access_fixture'
    assert len(calls)==1
