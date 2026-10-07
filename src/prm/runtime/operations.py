"""Default-off execution epochs, private backup and isolated restore tooling."""
from datetime import datetime,timezone
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import time
import uuid
from psycopg import sql
from prm.storage.postgres import PostgresStore,StorageError,SyntheticTarget

SCHEMAS=('pa_runtime','pa_policy','pa_actions','pa_conversation','pa_jobs','pa_schedule','pa_delivery','pa_briefs','pa_connections','pa_sources','pa_memory','pa_cache','pa_artifacts','pa_academic','pa_control')
DDL=(
    'CREATE SCHEMA pa_control',
    '''CREATE TABLE pa_control.state(id integer PRIMARY KEY CHECK(id=1),epoch text NOT NULL,egress_enabled boolean NOT NULL DEFAULT false,
       draining boolean NOT NULL DEFAULT false,updated_at timestamptz NOT NULL DEFAULT clock_timestamp())''',
    'GRANT USAGE ON SCHEMA pa_control TO pa_test_app',
    'GRANT SELECT,UPDATE ON pa_control.state TO pa_test_app',
)


def install_operations(target):
    if target.user!='pa_test_migrator':raise StorageError('dedicated synthetic migrator required')
    with PostgresStore(target).transaction() as tx:
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)',(87291024,))
        if tx.conn.execute("SELECT to_regclass('pa_control.state') AS meta").fetchone()['meta'] is None:
            for statement in DDL:tx.conn.execute(statement)
            tx.conn.execute('INSERT INTO pa_control.state(id,epoch) VALUES(1,%s)',(uuid.uuid4().hex,))


class OperationsRuntime:
    def __init__(self,target,*,artifact_root=None):self.store=PostgresStore(target);self.artifact_root=Path(artifact_root) if artifact_root else None
    def status(self):
        try:
            with self.store.transaction() as tx:
                state=tx.conn.execute('SELECT epoch,egress_enabled,draining FROM pa_control.state WHERE id=1').fetchone()
                jobs=tx.conn.execute('SELECT status,count(*) AS count FROM pa_jobs.jobs GROUP BY status').fetchall()
                unknown=tx.conn.execute("SELECT count(*) AS count,max(clock_timestamp()-created_at) AS oldest FROM pa_delivery.attempts WHERE status='unknown'").fetchone()
                usage=tx.conn.execute('SELECT count(*) AS attempts,sum(cost_microdollars) AS known_cost_microdollars,count(*) FILTER(WHERE cost_microdollars IS NULL) AS unknown_cost_attempts FROM pa_cache.usage').fetchone()
                lag=tx.conn.execute("SELECT extract(epoch FROM max(clock_timestamp()-available_at)) AS seconds FROM pa_jobs.jobs WHERE status IN ('queued','retry_wait')").fetchone()
                waits=tx.conn.execute("SELECT count(*) AS connections,count(*) FILTER(WHERE wait_event_type='Lock') AS waiting_for_lock FROM pg_catalog.pg_stat_activity WHERE datname=current_database() AND application_name='pa-local-synthetic'").fetchone()
                freshness=tx.conn.execute("SELECT kind,count(*) AS selected_scopes,count(*) FILTER(WHERE completed) AS completed_scopes,extract(epoch FROM clock_timestamp()-min(updated_at)) AS oldest_seconds FROM pa_sources.sync GROUP BY kind").fetchall()
                latency=tx.conn.execute('SELECT percentile_cont(.95) WITHIN GROUP(ORDER BY latency_ms) AS p95_ms FROM pa_cache.usage').fetchone()
            disk=shutil.disk_usage(self.artifact_root) if self.artifact_root else None
            return {'database':'ready','execution':state,'jobs':jobs,'unknown_count':unknown['count'],
                'oldest_unknown_seconds':unknown['oldest'].total_seconds() if unknown['oldest'] else None,
                'queue_age_seconds':float(lag['seconds']) if lag['seconds'] is not None else None,'usage':usage,'latency':latency,
                'disk_free_bytes':disk.free if disk else None,'lock_wait':waits['waiting_for_lock'],'database_connections':waits['connections'],
                'connection_pool':'direct_bounded_connections','sync_freshness':freshness,'backup_status':'requires_manifest'}
        except Exception:return {'database':'down','egress_enabled':False,'error':'runtime_state_unavailable'}
    def drain(self):
        with self.store.transaction() as tx:tx.conn.execute('UPDATE pa_control.state SET draining=true,updated_at=clock_timestamp() WHERE id=1')
    def kill_switch(self):
        with self.store.transaction() as tx:tx.conn.execute('UPDATE pa_control.state SET egress_enabled=false,draining=true,updated_at=clock_timestamp() WHERE id=1')
    def permit_synthetic_egress(self,*,expected_epoch,operator_request_ref):
        if self.store.target.target!='synthetic-test' or not isinstance(operator_request_ref,str) or not operator_request_ref.startswith('synthetic_operator_'):
            raise StorageError('explicit synthetic operator request required; production resume excluded')
        with self.store.transaction() as tx:
            row=tx.conn.execute('UPDATE pa_control.state SET egress_enabled=true,draining=false,updated_at=clock_timestamp() WHERE id=1 AND epoch=%s RETURNING epoch',(expected_epoch,)).fetchone()
            if row is None:raise StorageError('execution epoch changed')
    def backup(self,*,destination):
        target=self.store.target
        if target.user!='pa_test_migrator':raise StorageError('explicit synthetic migrator backup target required')
        destination=Path(destination)
        if not destination.is_absolute() or destination.exists():raise StorageError('new private backup directory required')
        destination.mkdir(mode=0o700)
        with target.connect() as conn:
            active=conn.execute("SELECT count(*) AS n FROM pa_jobs.jobs WHERE status IN ('leased','running')").fetchone()['n']
            if active:raise StorageError('drain active leases before taking a cutover snapshot')
            tables=conn.execute("SELECT schemaname,tablename FROM pg_catalog.pg_tables WHERE schemaname=ANY(%s) ORDER BY schemaname,tablename",(list(SCHEMAS),)).fetchall()
            state=conn.execute('SELECT epoch,egress_enabled,draining FROM pa_control.state WHERE id=1').fetchone()
            if state['egress_enabled'] or not state['draining']:raise StorageError('freeze and disable egress before taking a cutover snapshot')
            epoch=state['epoch']
        dump=destination/'state.dump';started=time.monotonic()
        args=['/usr/lib/postgresql/14/bin/pg_dump','-h',target.host,'-p',str(target.port),'-U',target.user,'-d',target.database,'-Fc','-f',str(dump)]
        for schema in sorted({row['schemaname'] for row in tables}):args.extend(['-n',schema])
        try:subprocess.run(args,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PGPASSFILE':'/dev/null'},check=True,timeout=60,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except Exception:raise StorageError('synthetic state backup failed') from None
        os.chmod(dump,0o600)
        artifacts=[]
        if self.artifact_root:
            root=self.artifact_root.resolve();out=destination/'artifacts';out.mkdir(mode=0o700);total=0
            for source in sorted(root.iterdir()):
                if source.is_symlink() or not source.is_file():continue
                size=source.stat().st_size;total+=size
                if total>512000000 or len(artifacts)>=10000:raise StorageError('artifact backup exceeds bound')
                name=source.name
                if '/' in name or name.startswith('.'):continue
                shutil.copyfile(source,out/name);os.chmod(out/name,0o600)
                artifacts.append({'name':name,'sha256':hashlib.sha256((out/name).read_bytes()).hexdigest(),'bytes':size})
        manifest={'schema_version':1,'postgres_major':14,'epoch':epoch,'snapshot_at':datetime.now(timezone.utc).isoformat(),
            'dump_sha256':hashlib.sha256(dump.read_bytes()).hexdigest(),'tables':tables,'artifacts':artifacts,
            'backup_elapsed_seconds':time.monotonic()-started,'rpo_seconds':'requires_writer_freeze_measurement','wal_replay':'not_configured; consistent pg_dump snapshot'}
        (destination/'manifest.json').write_text(json.dumps(manifest,indent=2));os.chmod(destination/'manifest.json',0o600)
        return manifest


def restore_bundle(*,bundle,target,artifact_root,tombstones=()):
    if type(target)is not SyntheticTarget or target.user!='pa_test_migrator':raise StorageError('fresh identified synthetic restore target required')
    bundle=Path(bundle);manifest=json.loads((bundle/'manifest.json').read_text());dump=bundle/'state.dump'
    if manifest.get('schema_version')!=1 or manifest.get('postgres_major')!=14 or hashlib.sha256(dump.read_bytes()).hexdigest()!=manifest['dump_sha256']:
        raise StorageError('backup manifest/checksum differs')
    with target.connect() as conn:
        existing=conn.execute('SELECT nspname FROM pg_catalog.pg_namespace WHERE nspname=ANY(%s)',(list(SCHEMAS),)).fetchall()
        if existing:raise StorageError('restore never overwrites an existing runtime namespace')
    out=Path(artifact_root)
    if not out.is_absolute() or out.exists() or out.is_symlink():raise StorageError('fresh isolated artifact restore directory required')
    for entry in manifest['artifacts']:
        name=entry['name']
        if not re.fullmatch(r'[a-f0-9]{64}\.(?:html|markdown|pdf)',name):raise StorageError('artifact manifest path substituted')
        source=bundle/'artifacts'/name
        if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest()!=entry['sha256']:raise StorageError('artifact checksum differs')
    started=time.monotonic()
    command=['/usr/lib/postgresql/14/bin/pg_restore','-h',target.host,'-p',str(target.port),'-U',target.user,'-d',target.database,
             '--exit-on-error','--single-transaction','--no-owner',str(dump)]
    try:subprocess.run(command,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PGPASSFILE':'/dev/null'},check=True,timeout=60,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except Exception:raise StorageError('isolated restore failed; target remains unpromoted') from None
    epoch=uuid.uuid4().hex
    with target.connect() as conn:
        with conn.transaction():
            conn.execute('UPDATE pa_control.state SET epoch=%s,egress_enabled=false,draining=true,updated_at=clock_timestamp() WHERE id=1',(epoch,))
            conn.execute("UPDATE pa_jobs.jobs SET status=CASE WHEN mode='effect' THEN 'awaiting_reconciliation' ELSE 'retry_wait' END,token=NULL,lease_until=NULL WHERE status IN ('leased','running')")
            from .deletion import delete_derived_in
            from prm.storage.postgres import StateTransaction
            all_tombstones=list(tombstones)+[(row['owner'],row['namespace'],row['object_ref']) for row in
                conn.execute('SELECT owner,namespace,object_ref FROM pa_memory.tombstones').fetchall()]
            for owner,namespace,ref in all_tombstones:
                delete_derived_in(StateTransaction(conn),owner=owner,namespace=namespace,object_ref=ref)
    out.mkdir(mode=0o700)
    for entry in manifest['artifacts']:
        shutil.copyfile(bundle/'artifacts'/entry['name'],out/entry['name']);os.chmod(out/entry['name'],0o600)
    root_digest=hashlib.sha256(str(out.resolve()).encode()).hexdigest()
    with target.connect() as conn:
        with conn.transaction():
            # Restored bytes belong to the new private directory. Deletions from
            # either writer take precedence over the backed-up file manifest.
            rows=conn.execute('SELECT owner,key,deleted FROM pa_artifacts.files FOR UPDATE').fetchall()
            indexed={row['key'] for row in rows}
            for row in rows:
                if not re.fullmatch(r'[a-f0-9]{64}\.(?:html|markdown|pdf)',row['key']):raise StorageError('invalid restored artifact key')
                if row['deleted']:(out/row['key']).unlink(missing_ok=True)
                conn.execute('UPDATE pa_artifacts.files SET root_digest=%s,cleanup_pending=false WHERE owner=%s AND key=%s',
                    (root_digest,row['owner'],row['key']))
            for entry in manifest['artifacts']:
                if entry['name'] not in indexed:(out/entry['name']).unlink(missing_ok=True)
    return {'status':'restored_egress_off','execution_epoch':epoch,'restore_elapsed_seconds':time.monotonic()-started,
            'rpo_seconds':manifest['rpo_seconds'],'lost_interval_reconciliation':'required','unknown_effects':'preserved; never automatic retry'}
