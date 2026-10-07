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
        from .deletion import delete_derived_in
        with self.store.transaction() as tx:
            state=delete_derived_in(tx,owner=owner,namespace='memory',object_ref=object_ref)
        if getattr(self.root,'reader',None) is not None:
            self.root.reader.cleanup_deleted()
            with self.store.transaction() as tx:
                pending=tx.conn.execute('SELECT count(*) AS n FROM pa_artifacts.files WHERE owner=%s AND deleted AND cleanup_pending',(owner,)).fetchone()['n']
            state['pending_artifacts']=pending
        return {'deleted':True,'object_ref':object_ref,**state,
                'deletion_state':'cleanup_pending' if state['pending_artifacts'] else 'complete',
                'backup_limitation':'Past backup content persists until its retention expiry; restore applies current tombstones before egress.'}
    def register_dependency(self,*,parent_namespace,parent_ref,child_namespace,child_ref):
        with self.store.transaction() as tx:
            from .deletion import lineage_lock
            lineage_lock(tx.conn,self.root.owner_ref)
            if tx.get(self.root.owner_ref,parent_namespace,parent_ref) is None or tx.get(self.root.owner_ref,child_namespace,child_ref) is None:
                raise StorageError('live owner-bound dependency objects required')
            tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                            (self.root.owner_ref,parent_namespace,parent_ref,child_namespace,child_ref))
    def search(self,query,*,chat_id,actor_id,owner_chat_id,limit=20):
        owner=self._owner(chat_id,actor_id,owner_chat_id)
        if not isinstance(query,str) or len(query)>500 or not 1<=limit<=50:raise StorageError('bounded memory search required')
        with self.store.transaction() as tx:
            rows=tx.conn.execute('''SELECT h.object_id FROM pa_runtime.object_heads h JOIN pa_runtime.object_versions v USING(owner,namespace,object_id,version)
                WHERE h.owner=%s AND h.namespace='memory' AND position(lower(%s) in lower(v.payload::text))>0
                ORDER BY h.object_id LIMIT %s''',(owner,query,limit)).fetchall()
            return [item for row in rows if (item:=tx.get(owner,'memory',row['object_id'])) is not None]

    def export(self,*,chat_id,actor_id,owner_chat_id):
        owner=self._owner(chat_id,actor_id,owner_chat_id)
        with self.store.transaction() as tx:
            rows=tx.conn.execute("SELECT object_id FROM pa_runtime.object_heads WHERE owner=%s AND namespace='memory' ORDER BY object_id LIMIT 1000",(owner,)).fetchall()
            return [item.payload for row in rows if (item:=tx.get(owner,'memory',row['object_id'])) is not None]
