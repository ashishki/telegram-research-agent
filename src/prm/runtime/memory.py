"""Explicit memory mutations and irreversible deletion fences for derived state."""
from datetime import datetime,timedelta,timezone
import hashlib
import uuid
from psycopg.types.json import Jsonb
from prm.briefs import brief_owner_ref_from_authenticated_private_tuple
from prm.capabilities import CapabilityDenied
from prm.storage.postgres import PostgresStore,StorageError,StateConflict,_canonical

DDL=(
    'CREATE SCHEMA pa_memory',
    'CREATE TABLE pa_memory.meta(version integer PRIMARY KEY,checksum text NOT NULL)',
    '''CREATE TABLE pa_memory.previews(owner text NOT NULL,id text NOT NULL,object_ref text NOT NULL,payload jsonb NOT NULL,
       digest text NOT NULL,expected_version bigint NOT NULL,expires timestamptz NOT NULL,consumed boolean NOT NULL DEFAULT false,PRIMARY KEY(owner,id))''',
    '''CREATE TABLE pa_memory.tombstones(owner text NOT NULL,namespace text NOT NULL,object_ref text NOT NULL,
       deleted_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(owner,namespace,object_ref))''',
    '''CREATE TABLE pa_memory.dependencies(owner text NOT NULL,parent_namespace text NOT NULL,parent_ref text NOT NULL,
       child_namespace text NOT NULL,child_ref text NOT NULL,PRIMARY KEY(owner,parent_namespace,parent_ref,child_namespace,child_ref))''',
    'GRANT USAGE ON SCHEMA pa_memory TO pa_test_app',
    'GRANT SELECT ON pa_memory.meta TO pa_test_app',
    'GRANT SELECT,INSERT,UPDATE ON pa_memory.previews TO pa_test_app',
    'GRANT SELECT,INSERT ON pa_memory.tombstones TO pa_test_app',
    'GRANT SELECT,INSERT,DELETE ON pa_memory.dependencies TO pa_test_app',
    'GRANT DELETE ON pa_runtime.object_heads,pa_runtime.object_versions TO pa_test_app',
)
CHECKSUM=hashlib.sha256('\n'.join(DDL).encode()).hexdigest()


def install_memory(target):
    if target.user!='pa_test_migrator':raise StorageError('dedicated synthetic migrator required')
    with PostgresStore(target).transaction() as tx:
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)',(87291021,))
        if tx.conn.execute("SELECT to_regclass('pa_memory.meta') AS meta").fetchone()['meta'] is None:
            for statement in DDL:tx.conn.execute(statement)
            tx.conn.execute('INSERT INTO pa_memory.meta VALUES(1,%s)',(CHECKSUM,))


class MemoryRuntime:
    LIFECYCLES={'indexed','surfaced','opened','read','understood','explained','tried','applied','measured','rejected','stale'}
    def __init__(self,root):self.root=root;self.store=root.queue.store
    def _owner(self,chat_id,actor_id,owner_chat_id):
        owner=brief_owner_ref_from_authenticated_private_tuple(chat_id,actor_id,owner_chat_id)
        if owner!=self.root.owner_ref:raise CapabilityDenied('explicit private memory owner required')
        return owner
    def preview(self,*,object_ref,text,source_refs,kind='note',lifecycle='indexed',expected_version=0,chat_id,actor_id,owner_chat_id):
        owner=self._owner(chat_id,actor_id,owner_chat_id)
        if kind not in {'note','preference','learning'} or lifecycle not in self.LIFECYCLES or not isinstance(text,str) or not 0<len(text)<=12000:
            raise StorageError('bounded explicit memory content required')
        if not isinstance(source_refs,tuple) or not source_refs or len(source_refs)>16:raise StorageError('explicit provenance required')
        payload={'text':text,'source_refs':list(source_refs),'kind':kind,'lifecycle':lifecycle,'explicit_owner_request':True}
        _,digest=_canonical(payload);ref='memoryconfirm_'+uuid.uuid4().hex
        with self.store.transaction() as tx:
            tx.conn.execute('INSERT INTO pa_memory.previews(owner,id,object_ref,payload,digest,expected_version,expires) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                (owner,ref,object_ref,Jsonb(payload),digest,expected_version,datetime.now(timezone.utc)+timedelta(minutes=10)))
        return ref
    def confirm(self,preview_ref,*,chat_id,actor_id,owner_chat_id):
        owner=self._owner(chat_id,actor_id,owner_chat_id)
        with self.store.transaction() as tx:
            row=tx.conn.execute('SELECT * FROM pa_memory.previews WHERE owner=%s AND id=%s FOR UPDATE',(owner,preview_ref)).fetchone()
            now=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            if not row or row['consumed'] or row['expires']<=now or _canonical(row['payload'])[1]!=row['digest']:raise StateConflict('memory preview changed, expired or consumed')
            item=tx.put(owner,'memory',row['object_ref'],row['payload'],expected_version=row['expected_version'])
            tx.conn.execute('UPDATE pa_memory.previews SET consumed=true WHERE owner=%s AND id=%s',(owner,preview_ref));return item
    def inspect(self,object_ref,*,chat_id,actor_id,owner_chat_id):
        owner=self._owner(chat_id,actor_id,owner_chat_id);return self.store.get(owner,'memory',object_ref)
    def forget(self,object_ref,*,chat_id,actor_id,owner_chat_id):
        owner=self._owner(chat_id,actor_id,owner_chat_id)
        with self.store.transaction() as tx:
            tx.conn.execute("SELECT id FROM pa_jobs.jobs WHERE owner=%s AND payload->>'input_namespace'='memory' AND payload->>'input_ref'=%s ORDER BY id FOR UPDATE",(owner,object_ref)).fetchall()
            descendants=tx.conn.execute('''WITH RECURSIVE refs(namespace,object_ref) AS (
                SELECT 'memory'::text,%s::text UNION SELECT d.child_namespace,d.child_ref FROM pa_memory.dependencies d JOIN refs r
                ON d.parent_namespace=r.namespace AND d.parent_ref=r.object_ref WHERE d.owner=%s)
                SELECT namespace,object_ref FROM refs ORDER BY namespace,object_ref LIMIT 129''',(object_ref,owner)).fetchall()
            if len(descendants)>128:raise StorageError('deletion dependency batch exceeds bound')
            for child in descendants:
                namespace,ref=child['namespace'],child['object_ref'];tx._object_lock(owner,namespace,ref)
                tx.conn.execute('INSERT INTO pa_memory.tombstones(owner,namespace,object_ref) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(owner,namespace,ref))
                tx.conn.execute("UPDATE pa_jobs.jobs SET status='cancelled',token=NULL,lease_until=NULL WHERE owner=%s AND payload->>'input_namespace'=%s AND payload->>'input_ref'=%s AND mode='compute'",(owner,namespace,ref))
                tx.conn.execute('DELETE FROM pa_runtime.object_heads WHERE owner=%s AND namespace=%s AND object_id=%s',(owner,namespace,ref))
                tx.conn.execute('DELETE FROM pa_runtime.object_versions WHERE owner=%s AND namespace=%s AND object_id=%s',(owner,namespace,ref))
            # Fence before removing content; all future reads/writes consult it.
            tx.conn.execute('INSERT INTO pa_memory.tombstones(owner,namespace,object_ref) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(owner,'memory',object_ref))
            tx.conn.execute("UPDATE pa_jobs.jobs SET status='cancelled',token=NULL,lease_until=NULL WHERE owner=%s AND payload->>'input_namespace'='memory' AND payload->>'input_ref'=%s AND status IN ('queued','leased','running','retry_wait')",(owner,object_ref))
            tx.conn.execute('DELETE FROM pa_runtime.object_heads WHERE owner=%s AND namespace=%s AND object_id=%s',(owner,'memory',object_ref))
            tx.conn.execute('DELETE FROM pa_runtime.object_versions WHERE owner=%s AND namespace=%s AND object_id=%s',(owner,'memory',object_ref))
            tx.conn.execute('UPDATE pa_memory.previews SET consumed=true,payload=%s WHERE owner=%s AND object_ref=%s',(Jsonb({'deleted':True}),owner,object_ref))
            if tx.conn.execute("SELECT to_regclass('pa_cache.entries') AS table_ref").fetchone()['table_ref']:
                tx.conn.execute('DELETE FROM pa_cache.entries WHERE owner=%s AND dependencies @> %s',(owner,Jsonb([{'namespace':'memory','object_ref':object_ref}])))
        return {'deleted':True,'object_ref':object_ref,'backup_limitation':'Past backup content persists until its retention expiry; restore must apply current tombstones before egress.'}
    def register_dependency(self,*,parent_namespace,parent_ref,child_namespace,child_ref):
        with self.store.transaction() as tx:
            if tx.get(self.root.owner_ref,parent_namespace,parent_ref) is None or tx.get(self.root.owner_ref,child_namespace,child_ref) is None:
                raise StorageError('live owner-bound dependency objects required')
            tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                            (self.root.owner_ref,parent_namespace,parent_ref,child_namespace,child_ref))
    def export(self,*,chat_id,actor_id,owner_chat_id):
        owner=self._owner(chat_id,actor_id,owner_chat_id)
        with self.store.transaction() as tx:
            rows=tx.conn.execute("SELECT object_id FROM pa_runtime.object_heads WHERE owner=%s AND namespace='memory' ORDER BY object_id LIMIT 1000",(owner,)).fetchall()
            return [item.payload for row in rows if (item:=tx.get(owner,'memory',row['object_id'])) is not None]
