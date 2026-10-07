"""Narrow PostgreSQL queue, fenced leases and reference-only job payloads."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
import uuid
from psycopg.types.json import Jsonb
from .postgres import PostgresStore,StorageError,StateConflict,_canonical

DDL=(
    'CREATE SCHEMA pa_jobs',
    'CREATE TABLE pa_jobs.meta(version integer PRIMARY KEY,checksum text NOT NULL)',
    '''CREATE TABLE pa_jobs.jobs(owner text NOT NULL,id text NOT NULL,idempotency_key text NOT NULL,kind text NOT NULL,
       mode text NOT NULL CHECK(mode IN ('compute','effect')),status text NOT NULL
       CHECK(status IN ('queued','leased','running','retry_wait','completed','cancelled','failed','quarantined','awaiting_reconciliation')),
       priority integer NOT NULL,payload jsonb NOT NULL,deadline timestamptz NOT NULL,
       available_at timestamptz NOT NULL DEFAULT clock_timestamp(),generation bigint NOT NULL DEFAULT 0,
       token text,lease_until timestamptz,attempts integer NOT NULL DEFAULT 0,max_attempts integer NOT NULL,
       checkpoint jsonb NOT NULL DEFAULT '{}',result_ref text,error_code text NOT NULL DEFAULT '',
       PRIMARY KEY(owner,id),UNIQUE(owner,idempotency_key))''',
    'CREATE INDEX jobs_ready ON pa_jobs.jobs(status,available_at,priority)',
    'GRANT USAGE ON SCHEMA pa_jobs TO pa_test_app',
    'GRANT SELECT ON pa_jobs.meta TO pa_test_app',
    'GRANT SELECT,INSERT,UPDATE ON pa_jobs.jobs TO pa_test_app',
)
CHECKSUM=hashlib.sha256('\n'.join(DDL).encode()).hexdigest()


def install_jobs(target):
    if target.user!='pa_test_migrator':raise StorageError('dedicated synthetic migrator required')
    with PostgresStore(target).transaction() as tx:
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)',(87291006,))
        if tx.conn.execute("SELECT to_regclass('pa_jobs.meta') AS meta").fetchone()['meta'] is None:
            for statement in DDL:tx.conn.execute(statement)
            tx.conn.execute('INSERT INTO pa_jobs.meta VALUES(1,%s)',(CHECKSUM,))
        else:_check(tx.conn)


def _check(conn):
    if conn.execute('SELECT version,checksum FROM pa_jobs.meta').fetchall()!=[{'version':1,'checksum':CHECKSUM}]:
        raise StorageError('unsupported durable queue schema')


def _ref(value):
    if not isinstance(value,str) or not value or len(value)>128 or value.strip()!=value:raise StorageError('invalid job reference')
    return value


def _payload(value):
    required={'schema_version','input_namespace','input_ref','input_version','input_digest',
              'connection_ref','resource_ref','purpose','consent_revision'}
    if not isinstance(value,dict) or set(value) not in (required,required|{'effect_key'}):raise StorageError('job payload must contain only versioned refs')
    if type(value['schema_version'])is not int or value['schema_version']!=1 or type(value['input_version'])is not int or value['input_version']<1:
        raise StorageError('unsupported job payload version')
    if not isinstance(value['input_digest'],str) or not re.fullmatch('[a-f0-9]{64}',value['input_digest']):raise StorageError('invalid job input digest')
    _ref(value['input_ref'])
    _ref(value['resource_ref']);_ref(value['purpose'])
    if value['connection_ref'] is not None:_ref(value['connection_ref'])
    if type(value['consent_revision'])is not int or value['consent_revision']<1:raise StorageError('invalid job consent revision')
    if 'effect_key'in value:_ref(value['effect_key'])
    return json.loads(_canonical(value)[0])


@dataclass(frozen=True)
class JobLease:
    owner: str
    job_id: str
    generation: int
    token: str
    lease_until: datetime
    payload: dict
    checkpoint: dict
    mode: str
    kind: str = 'compute.digest'


class JobQueue:
    def __init__(self,target,*,admission_limit=100):
        if type(admission_limit)is not int or not 1<=admission_limit<=10000:raise StorageError('bounded admission required')
        self.store=PostgresStore(target);self.admission_limit=admission_limit
    def _input(self,tx,owner,payload):
        item=tx.get(owner,payload['input_namespace'],payload['input_ref'],version=payload['input_version'])
        if not item or item.digest!=payload['input_digest']:raise StorageError('job input identity/version/digest unavailable')
        return item
    def enqueue_in(self,tx,*,owner,idempotency_key,payload,deadline,kind='compute.digest',mode='compute',priority=0,max_attempts=3):
        _check(tx.conn);_ref(owner);_ref(idempotency_key);payload=_payload(payload)
        if (mode not in {'compute','effect'} or kind not in {'compute.digest','compute.assistant','compute.watch','compute.research','effect.dispatch'} or (kind.startswith('compute.')!=(mode=='compute'))
            or (mode=='effect')!=('effect_key'in payload) or type(priority)is not int or not -1000<=priority<=1000
            or type(max_attempts)is not int or not 1<=max_attempts<=5 or not isinstance(deadline,datetime) or deadline.tzinfo is None):
            raise StorageError('invalid bounded job intent')
        self._input(tx,owner,payload)
        lock=int.from_bytes(hashlib.sha256(('pa.jobs.admission:'+owner).encode()).digest()[:8],'big')%(2**63)
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)',(lock,))
        existing=tx.conn.execute('SELECT id,payload,kind,mode FROM pa_jobs.jobs WHERE owner=%s AND idempotency_key=%s',(owner,idempotency_key)).fetchone()
        if existing:
            if existing['payload']!=payload or existing['kind']!=kind or existing['mode']!=mode:raise StateConflict('idempotency key belongs to a different intent')
            return existing['id']
        count=tx.conn.execute("SELECT count(*) AS n FROM pa_jobs.jobs WHERE owner=%s AND status IN ('queued','leased','running','retry_wait')",(owner,)).fetchone()['n']
        if count>=self.admission_limit:raise StorageError('queue admission limit reached')
        now=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
        if deadline<=now:raise StorageError('job deadline has expired')
        job_id='job_'+uuid.uuid4().hex
        tx.conn.execute('''INSERT INTO pa_jobs.jobs(owner,id,idempotency_key,kind,mode,status,priority,payload,deadline,max_attempts)
            VALUES(%s,%s,%s,%s,%s,'queued',%s,%s,%s,%s)''',(owner,job_id,idempotency_key,kind,mode,priority,Jsonb(payload),deadline,max_attempts))
        return job_id
    def enqueue(self,**kwargs):
        with self.store.transaction() as tx:return self.enqueue_in(tx,**kwargs)
    def claim(self,*,owner,lease_seconds=30,modes=('compute',),kinds=None):
        _ref(owner)
        if type(lease_seconds)is not int or not 1<=lease_seconds<=300 or not isinstance(modes,tuple) or not set(modes)<= {'compute','effect'}:
            raise StorageError('invalid bounded worker claim')
        if kinds is not None and (not isinstance(kinds,tuple) or not kinds or not set(kinds)<= {'compute.digest','compute.assistant','compute.watch','compute.research','effect.dispatch'}):
            raise StorageError('invalid worker kind filter')
        with self.store.transaction() as tx:
            conn=tx.conn;_check(conn)
            if conn.execute("SELECT to_regclass('pa_control.state') AS table_ref").fetchone()['table_ref'] is not None:
                control=conn.execute('SELECT draining FROM pa_control.state WHERE id=1').fetchone()
                if not control or control['draining']:return None
            lock=int.from_bytes(hashlib.sha256(('pa.jobs.claim:'+owner).encode()).digest()[:8],'big')%(2**63)
            conn.execute('SELECT pg_advisory_xact_lock(%s)',(lock,))
            conn.execute("UPDATE pa_jobs.jobs SET status='failed',error_code='deadline' WHERE owner=%s AND status IN ('queued','retry_wait') AND deadline<=clock_timestamp()",(owner,))
            row=conn.execute('''SELECT * FROM pa_jobs.jobs WHERE owner=%s AND mode=ANY(%s) AND (%s::text[] IS NULL OR kind=ANY(%s)) AND status IN ('queued','retry_wait')
                AND available_at<=clock_timestamp() AND deadline>clock_timestamp()
                AND (kind<>'compute.assistant' OR NOT EXISTS(SELECT 1 FROM pa_jobs.jobs active
                    WHERE active.owner=%s AND active.kind='compute.assistant' AND active.status IN ('leased','running')
                    AND active.lease_until>clock_timestamp()))
                ORDER BY priority DESC,id FOR UPDATE SKIP LOCKED LIMIT 1''',(owner,list(modes),list(kinds) if kinds else None,list(kinds) if kinds else None,owner)).fetchone()
            if not row:return None
            try:payload=_payload(row['payload']);self._input(tx,owner,payload)
            except StorageError:
                conn.execute("UPDATE pa_jobs.jobs SET status='quarantined',error_code='payload_or_input' WHERE owner=%s AND id=%s",(owner,row['id']))
                return None
            token=uuid.uuid4().hex
            lease=conn.execute('''UPDATE pa_jobs.jobs SET status='leased',generation=generation+1,token=%s,
                lease_until=least(deadline,clock_timestamp()+(%s*interval '1 second')),attempts=attempts+1
                WHERE owner=%s AND id=%s RETURNING generation,lease_until''',(token,lease_seconds,owner,row['id'])).fetchone()
            return JobLease(owner,row['id'],lease['generation'],token,lease['lease_until'],payload,row['checkpoint'],row['mode'],row['kind'])
    def _fenced(self,tx,lease):
        if type(lease)is not JobLease:raise StorageError('typed fenced lease required')
        _check(tx.conn)
        row=tx.conn.execute('''SELECT * FROM pa_jobs.jobs WHERE owner=%s AND id=%s AND generation=%s AND token=%s
            AND status IN ('leased','running') AND lease_until>clock_timestamp() AND deadline>clock_timestamp() FOR UPDATE''',
            (lease.owner,lease.job_id,lease.generation,lease.token)).fetchone()
        if not row:raise StateConflict('lease stale, expired or cancelled')
        if row['payload']!=lease.payload:raise StorageError('lease payload changed')
        self._input(tx,lease.owner,lease.payload)
        return row
    def heartbeat(self,lease,*,lease_seconds=30):
        if type(lease_seconds)is not int or not 1<=lease_seconds<=300:raise StorageError('invalid heartbeat bound')
        with self.store.transaction() as tx:
            self._fenced(tx,lease)
            return tx.conn.execute('''UPDATE pa_jobs.jobs SET lease_until=least(deadline,clock_timestamp()+(%s*interval '1 second'))
                WHERE owner=%s AND id=%s RETURNING lease_until''',(lease_seconds,lease.owner,lease.job_id)).fetchone()['lease_until']
    def checkpoint(self,lease,value):
        payload=json.loads(_canonical(value)[0])
        if len(json.dumps(payload).encode())>16384:raise StorageError('checkpoint exceeds its bound')
        with self.store.transaction() as tx:
            self._fenced(tx,lease)
            tx.conn.execute("UPDATE pa_jobs.jobs SET status='running',checkpoint=%s WHERE owner=%s AND id=%s",(Jsonb(payload),lease.owner,lease.job_id))
    def complete(self,lease,result):
        if lease.mode!='compute':raise StorageError('effect completion requires its separate durable receipt executor')
        with self.store.transaction() as tx:
            self._fenced(tx,lease);ref='result_'+lease.job_id
            tx.put(lease.owner,'result',ref,result,expected_version=0)
            if tx.conn.execute("SELECT to_regclass('pa_memory.dependencies') AS table_ref").fetchone()['table_ref'] is not None:
                tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                    (lease.owner,lease.payload['input_namespace'],lease.payload['input_ref'],'result',ref))
            tx.conn.execute("UPDATE pa_jobs.jobs SET status='completed',result_ref=%s,token=NULL,lease_until=NULL WHERE owner=%s AND id=%s",(ref,lease.owner,lease.job_id))
            return ref
    def cancel(self,*,owner,job_id):
        with self.store.transaction() as tx:
            _check(tx.conn)
            row=tx.conn.execute("UPDATE pa_jobs.jobs SET status='cancelled',token=NULL,lease_until=NULL WHERE owner=%s AND id=%s AND status IN ('queued','retry_wait','leased','running') RETURNING id",(owner,job_id)).fetchone()
            return bool(row)
    def retry_compute(self,lease,*,delay_seconds=1,error_code='compute_unavailable'):
        if lease.mode!='compute' or type(delay_seconds)is not int or not 1<=delay_seconds<=300:
            raise StorageError('only bounded safe compute retry is supported')
        if error_code not in {'compute_unavailable','source_unavailable','rate_limited'}:
            raise StorageError('unknown retry reason')
        with self.store.transaction() as tx:
            row=self._fenced(tx,lease)
            state='failed' if row['attempts']>=row['max_attempts'] else 'retry_wait'
            tx.conn.execute('''UPDATE pa_jobs.jobs SET status=%s,token=NULL,lease_until=NULL,error_code=%s,
                available_at=clock_timestamp()+(%s*interval '1 second') WHERE owner=%s AND id=%s''',
                (state,error_code,delay_seconds,lease.owner,lease.job_id))
    def recover_expired(self,*,owner):
        with self.store.transaction() as tx:
            conn=tx.conn;_check(conn)
            rows=conn.execute("SELECT * FROM pa_jobs.jobs WHERE owner=%s AND status IN ('leased','running') AND lease_until<=clock_timestamp() ORDER BY id FOR UPDATE SKIP LOCKED",(owner,)).fetchall()
            for row in rows:
                if row['mode']=='effect':status='awaiting_reconciliation'
                elif row['attempts']>=row['max_attempts'] or row['deadline']<=conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']:status='failed'
                else:status='retry_wait'
                conn.execute('''UPDATE pa_jobs.jobs SET status=%s,token=NULL,lease_until=NULL,
                    available_at=clock_timestamp()+interval '1 second',error_code='expired_worker'
                    WHERE owner=%s AND id=%s''',(status,owner,row['id']))
            return len(rows)
    def status(self,*,owner,job_id):
        with self.store.transaction() as tx:
            _check(tx.conn)
            return tx.conn.execute('SELECT id,status,generation,attempts,checkpoint,result_ref,error_code FROM pa_jobs.jobs WHERE owner=%s AND id=%s',(owner,job_id)).fetchone()
