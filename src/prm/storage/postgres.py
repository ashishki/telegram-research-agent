"""Process-local transactions on an explicitly identified synthetic PostgreSQL."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
import re
from typing import Iterator

import psycopg
from psycopg.types.json import Jsonb
from psycopg.rows import dict_row


class StorageError(RuntimeError): pass
class StateConflict(StorageError): pass
class SchemaMismatch(StorageError): pass

SCHEMA_VERSION = 1
NAMESPACES = frozenset({'conversation', 'result', 'memory'})
MIGRATION = (
    'CREATE SCHEMA pa_runtime',
    '''CREATE TABLE pa_runtime.schema_migrations (
        version integer PRIMARY KEY CHECK(version > 0), checksum text NOT NULL,
        applied_at timestamptz NOT NULL DEFAULT clock_timestamp())''',
    '''CREATE TABLE pa_runtime.object_versions (
        owner varchar(128) NOT NULL CHECK(length(owner)>0),
        namespace text NOT NULL CHECK(namespace IN ('conversation','result','memory')),
        object_id varchar(128) NOT NULL CHECK(length(object_id)>0),
        version bigint NOT NULL CHECK(version>0), schema_version integer NOT NULL CHECK(schema_version=1),
        payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),
        digest char(64) NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(owner,namespace,object_id,version))''',
    '''CREATE TABLE pa_runtime.object_heads (
        owner varchar(128) NOT NULL, namespace text NOT NULL, object_id varchar(128) NOT NULL,
        version bigint NOT NULL CHECK(version>0), PRIMARY KEY(owner,namespace,object_id),
        FOREIGN KEY(owner,namespace,object_id,version)
          REFERENCES pa_runtime.object_versions(owner,namespace,object_id,version)
          DEFERRABLE INITIALLY DEFERRED)''',
    'GRANT USAGE ON SCHEMA pa_runtime TO pa_test_app',
    'GRANT SELECT ON pa_runtime.schema_migrations TO pa_test_app',
    'GRANT SELECT, INSERT ON pa_runtime.object_versions TO pa_test_app',
    'GRANT SELECT, INSERT, UPDATE ON pa_runtime.object_heads TO pa_test_app',
)
MIGRATION_HASH = hashlib.sha256('\n'.join(MIGRATION).encode()).hexdigest()


def require_no_ambient_pg_configuration():
    if any(name.startswith('PG') for name in os.environ):
        raise StorageError('ambient PostgreSQL configuration is not permitted for synthetic targets')


@dataclass(frozen=True)
class SyntheticTarget:
    backend: str
    host: str
    port: int
    database: str
    user: str
    instance_id: str
    target: str

    def __post_init__(self):
        if (self.backend != 'postgresql' or self.host != '127.0.0.1' or self.target != 'synthetic-test'
            or type(self.port) is not int or not 1024 < self.port <= 65535 or self.port == 5432
            or not isinstance(self.database, str) or not re.fullmatch(r'pa_test_[a-z0-9_]{1,40}', self.database)
            or self.user not in {'pa_test_app', 'pa_test_migrator'}
            or not isinstance(self.instance_id, str) or not re.fullmatch(r'[a-f0-9]{32}', self.instance_id)):
            raise StorageError('explicit isolated synthetic PostgreSQL target required')

    @classmethod
    def from_mapping(cls, value: dict):
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise StorageError('complete explicit backend configuration required; no defaults')
        return cls(**value)

    def connect(self):
        require_no_ambient_pg_configuration()
        try:
            conn = psycopg.connect(host=self.host, hostaddr=self.host, port=self.port,
                dbname=self.database, user=self.user, password='', passfile='/dev/null',
                sslmode='disable', gssencmode='disable', connect_timeout=3, autocommit=True,
                application_name='pa-local-synthetic', row_factory=dict_row,
                options='-c search_path=pg_catalog -c statement_timeout=2000 -c lock_timeout=1000 -c idle_in_transaction_session_timeout=15000')
            with conn.transaction():
                identity = conn.execute("SELECT current_database() AS db,current_user AS role,current_setting('cluster_name') AS marker").fetchone()
                role = conn.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication FROM pg_catalog.pg_roles WHERE rolname=current_user').fetchone()
                if (identity['db'] != self.database or identity['role'] != self.user
                    or identity['marker'] != 'pa-synthetic-' + self.instance_id or any(role.values())):
                    raise StorageError('database is not the identified unprivileged synthetic target')
            return conn
        except StorageError:
            if 'conn' in locals(): conn.close()
            raise
        except psycopg.Error:
            if 'conn' in locals(): conn.close()
            raise StorageError('synthetic PostgreSQL connection unavailable') from None


def _version(conn) -> int:
    if conn.execute("SELECT to_regclass('pa_runtime.schema_migrations') AS meta").fetchone()['meta'] is None:
        if conn.execute("SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname='pa_runtime') AS present").fetchone()['present']:
            raise SchemaMismatch('unrecognized existing runtime schema')
        return 0
    rows = conn.execute('SELECT version,checksum FROM pa_runtime.schema_migrations ORDER BY version').fetchall()
    if len(rows) != 1 or rows[0] != {'version': 1, 'checksum': MIGRATION_HASH}:
        raise SchemaMismatch('unsupported or altered runtime schema')
    return 1


def migrate(target: SyntheticTarget, *, expected_version: int, target_version: int = SCHEMA_VERSION) -> int:
    if target.user != 'pa_test_migrator' or type(expected_version) is not int or expected_version not in {0,1} or type(target_version) is not int or target_version != 1:
        raise SchemaMismatch('explicit supported migration version and dedicated migrator required')
    with target.connect() as conn:
        try:
            with conn.transaction():
                conn.execute('SELECT pg_advisory_xact_lock(%s)', (87291002,))
                current = _version(conn)
                if current != expected_version:
                    raise SchemaMismatch('migration starting version changed')
                if current == 0:
                    for statement in MIGRATION: conn.execute(statement)
                    conn.execute('INSERT INTO pa_runtime.schema_migrations(version,checksum) VALUES(%s,%s)', (1,MIGRATION_HASH))
            return 1
        except psycopg.Error:
            raise StorageError('synthetic migration failed and rolled back') from None


def _identity(owner: str, namespace: str, object_id: str):
    if not isinstance(namespace,str) or namespace not in NAMESPACES or any(not isinstance(s,str) or not s or s.strip()!=s or len(s)>128 for s in (owner,object_id)):
        raise StorageError('invalid scoped object identity')


def _canonical(payload: dict) -> tuple[str,str]:
    if not isinstance(payload,dict): raise StorageError('object payload must be a dictionary')
    def check(value):
        if isinstance(value,dict):
            for key, child in value.items():
                if not isinstance(key,str) or key.lower() in {'password','api_key','secret','access_token','refresh_token','authorization','cookie'}:
                    raise StorageError('credentials cannot be stored in runtime objects')
                check(child)
        elif isinstance(value,list):
            for child in value: check(child)
    try:
        check(payload)
        encoded=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
    except (ValueError,TypeError,RecursionError):
        raise StorageError('invalid bounded JSON object') from None
    if len(encoded.encode())>65536: raise StorageError('object payload exceeds its bound')
    return encoded,hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True)
class StateObject:
    owner: str
    namespace: str
    object_id: str
    version: int
    payload: dict
    digest: str


class StateTransaction:
    def __init__(self,conn): self.conn,self.pid=conn,os.getpid()
    def _check(self):
        if self.pid!=os.getpid() or self.conn.closed: raise StorageError('transaction cannot be reused across processes or after close')
    def put(self,owner,namespace,object_id,payload,*,expected_version:int):
        self._check();_identity(owner,namespace,object_id)
        self._object_lock(owner,namespace,object_id)
        if self._deleted(owner,namespace,object_id):raise StateConflict('deleted object cannot be resurrected')
        if type(expected_version) is not int or not 0<=expected_version<2**63-1: raise StateConflict('invalid expected version')
        encoded,digest=_canonical(payload)
        if expected_version==0:
            row=self.conn.execute('''INSERT INTO pa_runtime.object_heads(owner,namespace,object_id,version)
                VALUES(%s,%s,%s,1) ON CONFLICT DO NOTHING RETURNING version''',(owner,namespace,object_id)).fetchone()
        else:
            row=self.conn.execute('''UPDATE pa_runtime.object_heads SET version=version+1
                WHERE owner=%s AND namespace=%s AND object_id=%s AND version=%s RETURNING version''',
                (owner,namespace,object_id,expected_version)).fetchone()
        if row is None: raise StateConflict('object changed; reload its current version')
        self.conn.execute('''INSERT INTO pa_runtime.object_versions(owner,namespace,object_id,version,schema_version,payload,digest)
            VALUES(%s,%s,%s,%s,1,%s,%s)''',(owner,namespace,object_id,row['version'],Jsonb(json.loads(encoded)),digest))
        return StateObject(owner,namespace,object_id,row['version'],json.loads(encoded),digest)
    def get(self,owner,namespace,object_id,*,version:int|None=None):
        self._check();_identity(owner,namespace,object_id)
        if self._deleted(owner,namespace,object_id):return None
        if version is not None and (type(version) is not int or version<=0): raise StorageError('invalid object version')
        if version is None:
            row=self.conn.execute('''SELECT v.version,v.payload,v.digest FROM pa_runtime.object_versions v
                JOIN pa_runtime.object_heads h USING(owner,namespace,object_id,version)
                WHERE v.owner=%s AND v.namespace=%s AND v.object_id=%s''',(owner,namespace,object_id)).fetchone()
        else:
            row=self.conn.execute('''SELECT version,payload,digest FROM pa_runtime.object_versions
                WHERE owner=%s AND namespace=%s AND object_id=%s AND version=%s''',(owner,namespace,object_id,version)).fetchone()
        if row is None:return None
        _,digest=_canonical(row['payload'])
        if digest!=row['digest']:raise StorageError('stored object integrity check failed')
        return StateObject(owner,namespace,object_id,row['version'],row['payload'],digest)

    def _deleted(self,owner,namespace,object_id):
        if self.conn.execute("SELECT to_regclass('pa_memory.tombstones') AS table_ref").fetchone()['table_ref'] is None:return False
        return self.conn.execute('SELECT 1 FROM pa_memory.tombstones WHERE owner=%s AND namespace=%s AND object_ref=%s',
                                 (owner,namespace,object_id)).fetchone() is not None
    def _object_lock(self,owner,namespace,object_id):
        value=int.from_bytes(hashlib.sha256((owner+'\x1f'+namespace+'\x1f'+object_id).encode()).digest()[:8],'big')%(2**63)
        self.conn.execute('SELECT pg_advisory_xact_lock(%s)',(value,))


class PostgresStore:
    def __init__(self,target:SyntheticTarget):
        if not isinstance(target,SyntheticTarget):raise StorageError('explicit typed target required')
        self.target=target
    @contextmanager
    def transaction(self)->Iterator[StateTransaction]:
        with self.target.connect() as conn:
            try:
                with conn.transaction():
                    if _version(conn)!=SCHEMA_VERSION:raise SchemaMismatch('runtime schema must be migrated explicitly')
                    yield StateTransaction(conn)
            except psycopg.Error:
                raise StorageError('state transaction failed and rolled back') from None
    def get(self,*args,**kwargs):
        with self.transaction() as tx:return tx.get(*args,**kwargs)
    def put(self,*args,**kwargs):
        with self.transaction() as tx:return tx.put(*args,**kwargs)
