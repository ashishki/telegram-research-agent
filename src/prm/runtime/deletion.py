"""Invalidate an owned derived dependency graph without touching the archive."""
import hashlib
from psycopg.types.json import Jsonb
from prm.storage.postgres import StorageError


def lineage_lock(conn,owner):
    key=int.from_bytes(hashlib.sha256(('pa.lineage:'+owner).encode()).digest()[:8],'big')%(2**63)
    conn.execute('SELECT pg_advisory_xact_lock(%s)',(key,))


def delete_derived_in(tx,*,owner,namespace,object_ref):
    if namespace not in {'memory','result','conversation'}:raise StorageError('only derived namespaces may be deleted')
    lineage_lock(tx.conn,owner)
    # Creators take the same lineage lock before fencing their input and
    # inserting the output/edge, so no new child can slip behind the snapshot.
    descendants=tx.conn.execute('''WITH RECURSIVE refs(namespace,object_ref) AS (
        SELECT %s::text,%s::text UNION SELECT d.child_namespace,d.child_ref FROM pa_memory.dependencies d
        JOIN refs r ON d.parent_namespace=r.namespace AND d.parent_ref=r.object_ref WHERE d.owner=%s)
        SELECT namespace,object_ref FROM refs ORDER BY namespace,object_ref LIMIT 129''',(namespace,object_ref,owner)).fetchall()
    if len(descendants)>128:raise StorageError('deletion graph exceeds bounded transaction')
    artifacts=0
    for child in descendants:
        space,ref=child['namespace'],child['object_ref']
        tx._object_lock(owner,space,ref)
        old=tx.get(owner,space,ref)
        if old is None:
            existing=tx.conn.execute('SELECT v.payload FROM pa_runtime.object_versions v JOIN pa_runtime.object_heads h USING(owner,namespace,object_id,version) WHERE v.owner=%s AND v.namespace=%s AND v.object_id=%s',(owner,space,ref)).fetchone()
            payload=existing['payload'] if existing else None
        else:payload=old.payload
        tx.conn.execute('INSERT INTO pa_memory.tombstones(owner,namespace,object_ref) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(owner,space,ref))
        tx.conn.execute("UPDATE pa_jobs.jobs SET status='cancelled',token=NULL,lease_until=NULL WHERE owner=%s AND mode='compute' AND status IN ('queued','retry_wait','leased','running') AND (payload->>'input_namespace'=%s AND payload->>'input_ref'=%s OR result_ref=%s)",(owner,space,ref,ref if space=='result' else ''))
        if payload and payload.get('kind')=='brief_manifest':
            tx.conn.execute('DELETE FROM pa_briefs.documents WHERE owner=%s AND id=%s',(owner,payload['brief_id']))
        if space=='memory' and tx.conn.execute("SELECT to_regclass('pa_academic.watches') AS meta").fetchone()['meta'] is not None:
            from .scheduler import WatchScheduler
            bindings=tx.conn.execute('SELECT schedule_id,subject_ref FROM pa_academic.watches WHERE owner=%s AND object_ref=%s ORDER BY schedule_id,subject_ref',(owner,ref)).fetchall()
            for binding in bindings:WatchScheduler.complete_subject_in(tx,owner=owner,subscription_id=binding['schedule_id'],subject_ref=binding['subject_ref'])
            for binding in bindings:
                notes=tx.conn.execute("UPDATE pa_schedule.notifications SET payload=payload || %s WHERE owner=%s AND schedule_id=%s AND subject_ref=%s RETURNING id",
                    (Jsonb({'title':'[deleted by owner]','summary':'[deleted by owner]','why_now':'owner deletion','source_url':None}),owner,binding['schedule_id'],binding['subject_ref'])).fetchall()
                for note in notes:tx.conn.execute("UPDATE pa_delivery.attempts SET payload=jsonb_set(payload,'{text}',%s) WHERE owner=%s AND source_ref=%s AND kind='watch' AND payload->>'text' IS DISTINCT FROM '[deleted by owner]'",(Jsonb('[deleted by owner]'),owner,note['id']))
            tx.conn.execute('DELETE FROM pa_academic.watches WHERE owner=%s AND object_ref=%s',(owner,ref))
        if space=='result':
            if tx.conn.execute("SELECT to_regclass('pa_delivery.attempts') AS meta").fetchone()['meta'] is not None:
                tx.conn.execute("UPDATE pa_delivery.attempts SET payload=jsonb_set(payload,'{text}',%s) WHERE owner=%s AND payload->>'result_ref'=%s AND payload->>'text' IS DISTINCT FROM '[deleted by owner]'",(Jsonb('[deleted by owner]'),owner,ref))
            tx.conn.execute("DELETE FROM pa_conversation.history WHERE owner=%s AND payload->>'response_ref'=%s",(owner,ref))
            tx.conn.execute("DELETE FROM pa_conversation.states WHERE owner=%s AND EXISTS(SELECT 1 FROM jsonb_array_elements(payload->'object_refs') o WHERE o->>'response_ref'=%s)",(owner,ref))
        tx.conn.execute('DELETE FROM pa_cache.entries WHERE owner=%s AND dependencies @> %s',(owner,Jsonb([{'namespace':space,'object_ref':ref}])))
        if tx.conn.execute("SELECT to_regclass('pa_artifacts.files') AS meta").fetchone()['meta'] is not None:
            changed=tx.conn.execute('UPDATE pa_artifacts.files SET deleted=true,cleanup_pending=true WHERE owner=%s AND parent_namespace=%s AND parent_ref=%s AND NOT deleted RETURNING key',(owner,space,ref)).fetchall()
            artifacts+=tx.conn.execute('SELECT count(*) AS n FROM pa_artifacts.files WHERE owner=%s AND parent_namespace=%s AND parent_ref=%s AND deleted AND cleanup_pending',(owner,space,ref)).fetchone()['n']
        tx.conn.execute('DELETE FROM pa_runtime.object_heads WHERE owner=%s AND namespace=%s AND object_id=%s',(owner,space,ref))
        tx.conn.execute('DELETE FROM pa_runtime.object_versions WHERE owner=%s AND namespace=%s AND object_id=%s',(owner,space,ref))
        if space=='memory':
            tx.conn.execute('UPDATE pa_memory.previews SET consumed=true,payload=%s WHERE owner=%s AND object_ref=%s',(Jsonb({'deleted':True}),owner,ref))
    return {'deleted_refs':len(descendants),'pending_artifacts':artifacts}
