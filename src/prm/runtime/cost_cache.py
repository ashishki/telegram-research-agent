"""Versioned provider usage, unique task costs and scope/version-aware caches."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal,ROUND_CEILING
import hashlib
import json
from psycopg.types.json import Jsonb
from prm.storage.postgres import PostgresStore,StorageError,StateConflict,_canonical

DDL=(
    'CREATE SCHEMA pa_cache',
    'CREATE TABLE pa_cache.meta(version integer PRIMARY KEY,checksum text NOT NULL)',
    '''CREATE TABLE pa_cache.entries(owner text NOT NULL,key text NOT NULL,kind text NOT NULL,payload jsonb NOT NULL,
       dependencies jsonb NOT NULL,expires timestamptz NOT NULL,PRIMARY KEY(owner,key))''',
    '''CREATE TABLE pa_cache.usage(owner text NOT NULL,attempt_ref text NOT NULL,task_ref text NOT NULL,provider text NOT NULL,
       model text NOT NULL,tariff_version text,usage jsonb NOT NULL,cost_microdollars bigint,latency_ms bigint NOT NULL,
       outcome text NOT NULL,PRIMARY KEY(owner,attempt_ref))''',
    '''CREATE TABLE pa_cache.tariffs(provider text NOT NULL,model text NOT NULL,version text NOT NULL,payload jsonb NOT NULL,
       PRIMARY KEY(provider,model,version))''',
    'GRANT USAGE ON SCHEMA pa_cache TO pa_test_app',
    'GRANT SELECT ON pa_cache.meta TO pa_test_app',
    'GRANT SELECT,INSERT,UPDATE,DELETE ON pa_cache.entries TO pa_test_app',
    'GRANT SELECT,INSERT ON pa_cache.usage,pa_cache.tariffs TO pa_test_app',
)
CHECKSUM=hashlib.sha256('\n'.join(DDL).encode()).hexdigest()


def install_cost_cache(target):
    if target.user!='pa_test_migrator':raise StorageError('dedicated synthetic migrator required')
    with PostgresStore(target).transaction() as tx:
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)',(87291023,))
        if tx.conn.execute("SELECT to_regclass('pa_cache.meta') AS meta").fetchone()['meta'] is None:
            for statement in DDL:tx.conn.execute(statement)
            tx.conn.execute('INSERT INTO pa_cache.meta VALUES(1,%s)',(CHECKSUM,))


class CostCacheRuntime:
    def __init__(self,root):self.root=root;self.store=root.queue.store
    def register_tariff(self,*,provider,model,version,input_per_million,cached_input_per_million,output_per_million,source_ref,valid_until):
        rates=[Decimal(str(value)) for value in (input_per_million,cached_input_per_million,output_per_million)]
        if any(not value.is_finite() or value<0 for value in rates) or not source_ref.startswith('https://') or valid_until.tzinfo is None:
            raise StorageError('explicit sourced finite versioned tariff required')
        payload={'input':str(rates[0]),'cache_read':str(rates[1]),'output':str(rates[2]),'source_ref':source_ref,'valid_until':valid_until.isoformat()}
        with self.store.transaction() as tx:
            tx.conn.execute('INSERT INTO pa_cache.tariffs VALUES(%s,%s,%s,%s)',(provider,model,version,Jsonb(payload)))
    def record(self,*,task_ref,attempt_ref,provider,model,usage,latency_ms,outcome,tariff_version=None):
        if outcome not in {'accepted','unknown','not_attempted'} or type(latency_ms)is not int or latency_ms<0:raise StorageError('bounded actual attempt metadata required')
        if not isinstance(usage,dict) or any(key not in {'input','cached_input','cache_write','output','reasoning','semantics'} for key in usage):
            raise StorageError('normalized provider usage required')
        for name in ('input','cached_input','cache_write','output','reasoning'):
            value=usage.get(name)
            if value is not None and (type(value)is not int or not 0<=value<=10000000):raise StorageError('invalid token count')
        cost=None
        with self.store.transaction() as tx:
            if tariff_version is not None and usage.get('semantics')=='openai_chat_output_includes_reasoning':
                row=tx.conn.execute('SELECT payload FROM pa_cache.tariffs WHERE provider=%s AND model=%s AND version=%s',(provider,model,tariff_version)).fetchone()
                if row and datetime.fromisoformat(row['payload']['valid_until'])>datetime.now(timezone.utc) and all(usage.get(name)is not None for name in ('input','cached_input','output')):
                    if usage['cached_input']>usage['input'] or usage.get('reasoning',0)>usage['output']:raise StorageError('provider token subsets inconsistent')
                    price=row['payload'];cost=int(((usage['input']-usage['cached_input'])*Decimal(price['input'])+
                        usage['cached_input']*Decimal(price['cache_read'])+usage['output']*Decimal(price['output'])).to_integral_value(rounding=ROUND_CEILING))
            old=tx.conn.execute('SELECT task_ref,provider,model,tariff_version,usage,cost_microdollars,latency_ms,outcome FROM pa_cache.usage WHERE owner=%s AND attempt_ref=%s',
                                (self.root.owner_ref,attempt_ref)).fetchone()
            values={'task_ref':task_ref,'provider':provider,'model':model,'tariff_version':tariff_version,'usage':usage,
                    'cost_microdollars':cost,'latency_ms':latency_ms,'outcome':outcome}
            if old:
                if old!=values:raise StateConflict('attempt cost cannot be counted twice with changed semantics')
            else:tx.conn.execute('INSERT INTO pa_cache.usage VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                                 (self.root.owner_ref,attempt_ref,task_ref,provider,model,tariff_version,Jsonb(usage),cost,latency_ms,outcome))
        return cost
    def task_cost(self,task_ref):
        with self.store.transaction() as tx:
            return tx.conn.execute('SELECT count(*) AS attempts,sum(cost_microdollars) AS known_microdollars,count(*) FILTER(WHERE cost_microdollars IS NULL) AS unknown_priced_attempts FROM pa_cache.usage WHERE owner=%s AND task_ref=%s',
                                   (self.root.owner_ref,task_ref)).fetchone()
    def key(self,*,kind,parameters,dependencies,provider=None,model=None,version=None):
        value={'owner':self.root.owner_ref,'kind':kind,'parameters':parameters,'dependencies':dependencies,'provider':provider,'model':model,'version':version}
        return hashlib.sha256(_canonical(value)[0].encode()).hexdigest()
    def put(self,*,key,kind,payload,dependencies,ttl_seconds):
        if kind not in {'extraction','retrieval','render'} or not 1<=ttl_seconds<=86400 or len(dependencies)>32:raise StorageError('bounded non-effect cache required')
        _canonical(payload)
        with self.store.transaction() as tx:
            from .deletion import lineage_lock
            lineage_lock(tx.conn,self.root.owner_ref)
            for dependency in dependencies:
                item=tx.get(self.root.owner_ref,dependency['namespace'],dependency['object_ref'],version=dependency['version'])
                if item is None or item.digest!=dependency['digest']:raise StorageError('cache dependency unavailable')
            tx.conn.execute('INSERT INTO pa_cache.entries VALUES(%s,%s,%s,%s,%s,clock_timestamp()+(%s*interval \'1 second\')) ON CONFLICT(owner,key) DO UPDATE SET payload=excluded.payload,dependencies=excluded.dependencies,expires=excluded.expires',
                (self.root.owner_ref,key,kind,Jsonb(payload),Jsonb(dependencies),ttl_seconds))
    def get(self,*,key,authorization_request):
        if authorization_request.owner_ref!=self.root.owner_ref or not self.root.registry.authorize(authorization_request).allowed:return None
        with self.store.transaction() as tx:
            if authorization_request.connection_ref is not None:
                account=tx.conn.execute('SELECT status FROM pa_connections.accounts WHERE owner=%s AND id=%s',(self.root.owner_ref,authorization_request.connection_ref)).fetchone()
                if not account or account['status']!='connected':return None
            row=tx.conn.execute('SELECT payload,dependencies FROM pa_cache.entries WHERE owner=%s AND key=%s AND expires>clock_timestamp()',(self.root.owner_ref,key)).fetchone()
            if not row:return None
            for dependency in row['dependencies']:
                item=tx.get(self.root.owner_ref,dependency['namespace'],dependency['object_ref'])
                if item is None or item.version!=dependency['version'] or item.digest!=dependency['digest']:return None
            return row['payload']
