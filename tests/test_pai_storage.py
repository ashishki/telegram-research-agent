"""Real PostgreSQL acceptance on an owned disposable cluster; never SQLite mocks."""
from dataclasses import asdict,replace
import multiprocessing
import subprocess
import sys
import os
from pathlib import Path
import pytest
import psycopg
from prm.storage.postgres import SyntheticTarget,PostgresStore,migrate,StorageError,SchemaMismatch,StateConflict
from prm.storage.testing import PostgresSandbox


@pytest.fixture(scope='module')
def sandbox():
    with PostgresSandbox() as value:
        migrate(value.migrator,expected_version=0)
        yield value


def _race_write(config,barrier,results):
    store=PostgresStore(SyntheticTarget.from_mapping(config))
    with store.transaction() as tx:pid=tx.conn.execute('SELECT pg_backend_pid() AS pid').fetchone()['pid']
    barrier.wait(timeout=10)
    try:
        store.put('synthetic-owner','result','race',{'winner':pid},expected_version=0)
        results.put(('created',pid))
    except StateConflict:results.put(('conflict',pid))


@pytest.mark.parametrize('patch',[{'backend':'sqlite'},{'host':'example.com'},{'port':5432},
    {'database':'production'},{'user':'postgres'},{'target':'production'},{'instance_id':'unknown'}, {'port':True}])
def test_wrong_target_denied_without_connect(sandbox,monkeypatch,patch):
    monkeypatch.setattr(psycopg,'connect',lambda **kwargs:pytest.fail('wrong target reached libpq'))
    with pytest.raises(StorageError):replace(sandbox.app,**patch)


def test_no_default_or_environment_configuration(monkeypatch):
    monkeypatch.setenv('DATABASE_URL','postgresql://private-unapproved-host/production')
    for value in ({},{'backend':'postgresql'},{'dsn':os.environ['DATABASE_URL']}):
        with pytest.raises(StorageError):SyntheticTarget.from_mapping(value)
    with pytest.raises(StorageError):PostgresStore(None)


def test_foreign_cluster_and_privileged_target_denied(sandbox):
    with pytest.raises(StorageError):replace(sandbox.app,instance_id='0'*32).connect()
    with pytest.raises(SchemaMismatch):migrate(sandbox.app,expected_version=1)


def test_migration_repeat_and_version_mismatch(sandbox):
    assert migrate(sandbox.migrator,expected_version=1)==1
    for version in (0,2,True):
        with pytest.raises(SchemaMismatch):migrate(sandbox.migrator,expected_version=version)
    with pytest.raises(SchemaMismatch):migrate(sandbox.migrator,expected_version=1,target_version=2)


def test_real_transactions_versions_owner_scope_and_sql_parameters(sandbox):
    store=PostgresStore(sandbox.app)
    key="result'; DROP TABLE pa_runtime.object_heads; --"
    first=store.put('synthetic-owner','result',key,{'text':'Привет','number':1},expected_version=0)
    second=store.put('synthetic-owner','result',key,{'text':'Версия 2','number':2},expected_version=1)
    assert (first.version,second.version)==(1,2)
    assert store.get('synthetic-owner','result',key,version=1)==first
    assert store.get('synthetic-owner','result',key)==second
    assert store.get('foreign-owner','result',key) is None
    with pytest.raises(StateConflict):store.put('synthetic-owner','result',key,{},expected_version=1)
    with pytest.raises(RuntimeError):
        with store.transaction() as tx:
            tx.put('synthetic-owner','memory','rollback',{'fact':'synthetic'},expected_version=0)
            raise RuntimeError('synthetic rollback')
    assert store.get('synthetic-owner','memory','rollback') is None


def test_process_race_and_fresh_connections(sandbox):
    ctx=multiprocessing.get_context('spawn');barrier=ctx.Barrier(2);results=ctx.Queue()
    workers=[ctx.Process(target=_race_write,args=(asdict(sandbox.app),barrier,results)) for _ in range(2)]
    for worker in workers:worker.start()
    observations=[results.get(timeout=20) for _ in workers]
    for worker in workers:
        worker.join(timeout=20)
        assert worker.exitcode==0
    assert sorted(row[0] for row in observations)==['conflict','created']
    assert len({row[1] for row in observations})==2


def test_payload_bounds_credentials_nonfinite_and_released_transaction(sandbox):
    store=PostgresStore(sandbox.app)
    for value in ({'blob':'x'*65537},{'value':float('nan')},{'nested':{'api_key':'synthetic-credential'}}):
        with pytest.raises(StorageError):store.put('synthetic-owner','result','invalid',value,expected_version=0)
    with store.transaction() as tx:assert tx.get('synthetic-owner','result','invalid') is None
    with pytest.raises(StorageError):tx.get('synthetic-owner','result','invalid')


def test_dump_restore_preserves_exact_ids_versions_and_digests(sandbox):
    source=PostgresStore(sandbox.app)
    restored=PostgresStore(sandbox.restore_copy())
    assert restored.get('synthetic-owner','result','race')==source.get('synthetic-owner','result','race')
    key="result'; DROP TABLE pa_runtime.object_heads; --"
    assert restored.get('synthetic-owner','result',key,version=1)==source.get('synthetic-owner','result',key,version=1)
    assert restored.get('synthetic-owner','result',key)==source.get('synthetic-owner','result',key)


def test_altered_schema_checksum_denies_runtime(sandbox):
    with sandbox.migrator.connect() as conn:
        conn.execute("UPDATE pa_runtime.schema_migrations SET checksum='altered'")
        try:
            with pytest.raises(SchemaMismatch):PostgresStore(sandbox.app).get('synthetic-owner','result','race')
        finally:
            from prm.storage.postgres import MIGRATION_HASH
            conn.execute('UPDATE pa_runtime.schema_migrations SET checksum=%s',(MIGRATION_HASH,))


def test_real_migration_cli_and_explicit_target(sandbox):
    command=[sys.executable,'-m','prm.storage','migrate','--backend','postgresql','--host','127.0.0.1',
        '--port',str(sandbox.port),'--database',sandbox.migrator.database,'--user',sandbox.migrator.user,
        '--instance-id',sandbox.instance_id,'--target','synthetic-test','--expected-version','1']
    result=subprocess.run(command,capture_output=True,text=True,timeout=10)
    assert result.returncode==0
    assert 'schema version: 1' in result.stdout
    command[command.index('--target')+1]='production'
    assert subprocess.run(command,capture_output=True,text=True,timeout=10).returncode==1


def test_ambient_pg_service_cannot_open_a_connection(sandbox,monkeypatch):
    monkeypatch.setenv('PGSERVICE','unapproved-production-service')
    monkeypatch.setattr(psycopg,'connect',lambda **kwargs:pytest.fail('ambient service reached libpq'))
    with pytest.raises(StorageError):sandbox.app.connect()


def test_database_enforces_immutable_versions_and_detects_corruption(sandbox):
    store=PostgresStore(sandbox.app)
    item=store.put('synthetic-owner','memory','integrity',{'text':'synthetic'},expected_version=0)
    with sandbox.app.connect() as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE pa_runtime.object_versions SET payload='{}' WHERE object_id='integrity'")
    with sandbox.migrator.connect() as conn:
        conn.execute("UPDATE pa_runtime.object_versions SET digest=%s WHERE object_id='integrity'",('0'*64,))
        try:
            with pytest.raises(StorageError,match='integrity'):store.get('synthetic-owner','memory','integrity')
        finally:
            conn.execute("UPDATE pa_runtime.object_versions SET digest=%s WHERE object_id='integrity'",(item.digest,))
