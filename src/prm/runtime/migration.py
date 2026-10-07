"""Synthetic cutover parity and monotone receipt/tombstone transfer."""
from psycopg import sql
from psycopg.types.json import Jsonb
from .operations import OperationsRuntime,SCHEMAS,restore_bundle
from prm.storage.postgres import StorageError,StateTransaction,_canonical,_identity
import hashlib
import json
from datetime import date,datetime

DOMAIN_TABLES=(
    ('pa_runtime','object_versions'),('pa_runtime','object_heads'),
    ('pa_policy','grants'),('pa_policy','windows'),('pa_policy','operations'),('pa_policy','members'),('pa_policy','call_counts'),
    ('pa_actions','proposals'),('pa_actions','confirmations'),('pa_actions','attempts'),
    ('pa_conversation','states'),('pa_conversation','history'),('pa_briefs','documents'),
    ('pa_jobs','jobs'),('pa_schedule','schedules'),('pa_schedule','previews'),('pa_schedule','occurrences'),
    ('pa_schedule','notifications'),('pa_schedule','baselines'),('pa_schedule','subjects'),
    ('pa_delivery','attempts'),('pa_delivery','quotas'),('pa_connections','accounts'),('pa_connections','flows'),
    ('pa_sources','items'),('pa_sources','sync'),('pa_memory','previews'),('pa_memory','dependencies'),
    ('pa_memory','tombstones'),('pa_cache','entries'),('pa_cache','usage'),('pa_cache','tariffs'),
    ('pa_artifacts','files'),('pa_academic','watches'),
)


def _json_row(row):
    return {key:value.isoformat() if isinstance(value,(date,datetime)) else value for key,value in row.items()}


def _table_metadata(conn,schema,table):
    columns=conn.execute('SELECT column_name,data_type FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position',(schema,table)).fetchall()
    keys=conn.execute('''SELECT a.attname FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indrelid
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum,ord) ON true
        JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum
        WHERE n.nspname=%s AND c.relname=%s AND i.indisprimary ORDER BY k.ord''',(schema,table)).fetchall()
    if not columns or not keys:raise StorageError('versioned domain table unavailable')
    return {column['column_name']:column['data_type'] for column in columns},tuple(key['attname'] for key in keys)


def export_domain_delta(target):
    """Complete frozen selected-state snapshot, never the SQLite archive."""
    if target.target!='synthetic-test' or target.user!='pa_test_migrator':raise StorageError('explicit isolated domain export required')
    with target.connect() as conn:
        with conn.transaction():
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            control=conn.execute('SELECT epoch,egress_enabled,draining FROM pa_control.state WHERE id=1').fetchone()
            if control['egress_enabled'] or not control['draining']:raise StorageError('freeze source before domain transfer')
            if conn.execute("SELECT 1 FROM pa_jobs.jobs WHERE status IN ('leased','running') LIMIT 1").fetchone():raise StorageError('drain source leases before domain transfer')
            tables={};size=0
            for schema,table in DOMAIN_TABLES:
                columns,keys=_table_metadata(conn,schema,table)
                rows=conn.execute(sql.SQL('SELECT * FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(table))).fetchall()
                if len(rows)>100000:raise StorageError('bounded domain transfer exceeded')
                converted=[_json_row(row) for row in rows]
                encoded=json.dumps(converted,sort_keys=True).encode();size+=len(encoded)
                if size>256000000:raise StorageError('domain export exceeds its private bound')
                tables[schema+'.'+table]={'columns':columns,'keys':list(keys),'rows':converted,'sha256':hashlib.sha256(encoded).hexdigest()}
    return {'schema_version':1,'source_epoch':control['epoch'],'tables':tables,'secret_storage':'encrypted vault files are separately controlled; no plaintext credential export'}


def apply_domain_delta(target,delta,*,expected_target_manifest):
    """Exact target precondition, atomic replacement, monotone effect fences."""
    if target.user!='pa_test_migrator' or target.target!='synthetic-test' or delta.get('schema_version')!=1:
        raise StorageError('explicit supported isolated domain import required')
    if state_manifest(target)!=expected_target_manifest:raise StorageError('target changed; forward-fix review required')
    tables=delta.get('tables',{})
    if set(tables)!={schema+'.'+table for schema,table in DOMAIN_TABLES}:raise StorageError('complete domain table set required')
    with target.connect() as conn:
        with conn.transaction():
            control=conn.execute('SELECT egress_enabled,draining FROM pa_control.state WHERE id=1 FOR UPDATE').fetchone()
            if control['egress_enabled'] or not control['draining']:raise StorageError('target must remain frozen and egress off')
            # Lock all imported tables before inspecting their current ledgers.
            for schema,table in DOMAIN_TABLES:
                conn.execute(sql.SQL('LOCK TABLE {}.{} IN ACCESS EXCLUSIVE MODE').format(sql.Identifier(schema),sql.Identifier(table)))
                item=tables[schema+'.'+table];columns,keys=_table_metadata(conn,schema,table)
                if item['columns']!=columns or item['keys']!=list(keys) or hashlib.sha256(json.dumps(item['rows'],sort_keys=True).encode()).hexdigest()!=item['sha256']:
                    raise StorageError('domain schema or row checksum differs')
                if any(set(row)!=set(columns) for row in item['rows']):raise StorageError('domain row columns differ')
            if _state_manifest(conn)!=expected_target_manifest:raise StorageError('target changed before frozen domain import')
            for row in tables['pa_runtime.object_versions']['rows']:
                _identity(row['owner'],row['namespace'],row['object_id'])
                if row['schema_version']!=1 or _canonical(row['payload'])[1]!=row['digest']:
                    raise StorageError('corrupted immutable object blocks domain transfer')
            # Missing or less conservative source fences never erase target effects.
            for schema,table in LEDGERS:
                item=tables[schema+'.'+table];keys=tuple(item['keys']);source={tuple(row[key] for key in keys):row for row in item['rows']}
                old=conn.execute(sql.SQL('SELECT * FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(table))).fetchall()
                for original in old:
                    row=_json_row(original);key=tuple(row[field] for field in keys);incoming=source.get(key)
                    if incoming is None:item['rows'].append(row);source[key]=row;continue
                    if table=='confirmations':
                        if row['payload']!=incoming['payload']:raise StorageError('confirmation content changed across writers')
                        incoming['consumed']=row['consumed'] or incoming['consumed']
                    elif schema=='pa_actions':
                        if row['receipt']['content_digest']!=incoming['receipt']['content_digest']:raise StorageError('action digest differs')
                        if row['receipt']['status']!='unknown':
                            if incoming['receipt']['status']!='unknown' and incoming['receipt']!=row['receipt']:raise StorageError('conflicting terminal action outcomes')
                            incoming.update(row)
                    elif schema=='pa_delivery':
                        if (row['digest'],row['destination_ref'])!=(incoming['digest'],incoming['destination_ref']):raise StorageError('delivery identity differs')
                        if row['status']!='unknown':
                            if incoming['status']!='unknown' and incoming['status']!=row['status']:raise StorageError('conflicting terminal delivery outcomes')
                            incoming.update(row)
            # A second writer's cost reservations require a forward fix, never a refund.
            for table in ('windows','operations','call_counts'):
                item=tables['pa_policy.'+table];keys=item['keys'];source={tuple(row[key] for key in keys):row for row in item['rows']}
                for old in conn.execute(sql.SQL('SELECT * FROM pa_policy.{}').format(sql.Identifier(table))).fetchall():
                    newer=source.get(tuple(old[key] for key in keys))
                    if newer is None:raise StorageError('target budget operation missing from source; forward fix required')
                    if table=='windows' and old['reserved']+old['consumed']>newer['reserved']+newer['consumed']:raise StorageError('budget delta would refund target spend')
                    if table=='call_counts' and old['used']>newer['used']:raise StorageError('budget delta would reset target calls')
                    if table=='operations' and old['state'] in {'prepared','unknown','accepted'} and newer['state'] in {'reserved','cancelled'}:
                        raise StorageError('attempted operation cannot become retryable')
            # Foreign-key dependency order is explicit; heads are deferred.
            for schema,table in reversed(DOMAIN_TABLES):
                conn.execute(sql.SQL('DELETE FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(table)))
            for schema,table in DOMAIN_TABLES:
                item=tables[schema+'.'+table];columns=list(item['columns'])
                statement=sql.SQL('INSERT INTO {}.{}({}) VALUES({})').format(sql.Identifier(schema),sql.Identifier(table),
                    sql.SQL(',').join(map(sql.Identifier,columns)),sql.SQL(',').join(sql.Placeholder() for column in columns))
                for row in item['rows']:
                    params=[Jsonb(row[column]) if item['columns'][column] in {'json','jsonb'} else row[column] for column in columns]
                    conn.execute(statement,params)
            from .deletion import delete_derived_in
            for row in tables['pa_memory.tombstones']['rows']:
                delete_derived_in(StateTransaction(conn),owner=row['owner'],namespace=row['namespace'],object_ref=row['object_ref'])
            conn.execute("UPDATE pa_jobs.jobs SET status=CASE WHEN mode='effect' THEN 'awaiting_reconciliation' ELSE 'retry_wait' END,token=NULL,lease_until=NULL WHERE status IN ('leased','running')")
    return {'status':'domain_delta_applied_egress_off','tables':len(DOMAIN_TABLES),'confirmation_restore':'consumed is monotone','unknown_restore':'never automatically replayed'}


LEDGERS={
    ('pa_actions','confirmations'):('owner','key'),
    ('pa_actions','attempts'):('owner','key'),
    ('pa_delivery','attempts'):('owner','id'),
    ('pa_memory','tombstones'):('owner','namespace','object_ref'),
}


def _state_manifest(conn):
    tables=conn.execute('SELECT schemaname,tablename FROM pg_catalog.pg_tables WHERE schemaname=ANY(%s) ORDER BY schemaname,tablename',(list(SCHEMAS),)).fetchall()
    manifest={}
    for table in tables:
        schema,name=table['schemaname'],table['tablename']
        if (schema,name)==('pa_control','state'):continue
        rows=conn.execute(sql.SQL('SELECT to_jsonb(t) AS value FROM {}.{} t').format(sql.Identifier(schema),sql.Identifier(name))).fetchall()
        values=sorted(json.dumps(row['value'],sort_keys=True,default=str) for row in rows)
        manifest[schema+'.'+name]={'count':len(values),'sha256':hashlib.sha256('\n'.join(values).encode()).hexdigest()}
    return manifest


def state_manifest(target):
    with target.connect() as conn:
        with conn.transaction():
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            return _state_manifest(conn)


def export_receipt_delta(target):
    if target.target!='synthetic-test':raise StorageError('synthetic-only receipt delta export')
    with target.connect() as conn:
        control=conn.execute('SELECT epoch,egress_enabled,draining FROM pa_control.state WHERE id=1').fetchone()
        if control['egress_enabled'] or not control['draining']:raise StorageError('freeze/drain before ledger transfer')
        result={}
        for schema,table in LEDGERS:
            result[schema+'.'+table]=conn.execute(sql.SQL('SELECT * FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(table))).fetchall()
        return {'schema_version':1,'source_epoch':control['epoch'],'ledgers':result}


def apply_receipt_delta(target,delta):
    if target.user!='pa_test_migrator' or delta.get('schema_version')!=1:raise StorageError('explicit supported isolated delta import required')
    with target.connect() as conn:
        with conn.transaction():
            control=conn.execute('SELECT egress_enabled,draining FROM pa_control.state WHERE id=1 FOR UPDATE').fetchone()
            if control['egress_enabled'] or not control['draining']:raise StorageError('delta target must stay frozen and egress off')
            for schema,table in LEDGERS:
                rows=delta['ledgers'].get(schema+'.'+table)
                if not isinstance(rows,list):raise StorageError('complete ledger transfer required')
                keys=LEDGERS[(schema,table)]
                for row in rows:
                    if not isinstance(row,dict) or any(key not in row for key in keys):raise StorageError('invalid ledger row')
                    where=sql.SQL(' AND ').join(sql.SQL('{}=%s').format(sql.Identifier(key)) for key in keys)
                    old=conn.execute(sql.SQL('SELECT * FROM {}.{} WHERE {} FOR UPDATE').format(sql.Identifier(schema),sql.Identifier(table),where),tuple(row[key] for key in keys)).fetchone()
                    value=dict(row)
                    if old:
                        if table=='confirmations':
                            if old['payload']!=row['payload']:raise StorageError('confirmation binding differs')
                            value['consumed']=old['consumed'] or row['consumed']
                        elif schema=='pa_actions':
                            if old['receipt']['content_digest']!=row['receipt']['content_digest']:raise StorageError('action receipt binding differs')
                            if old['receipt']['status']!='unknown':
                                if row['receipt']['status']!='unknown' and old['receipt']!=row['receipt']:raise StorageError('conflicting terminal action receipts')
                                value=old
                        elif schema=='pa_delivery':
                            if (old['digest'],old['destination_ref'])!=(row['digest'],row['destination_ref']):raise StorageError('delivery binding differs')
                            if old['status']!='unknown':
                                if row['status']!='unknown' and old['status']!=row['status']:raise StorageError('conflicting terminal delivery receipts')
                                value=old
                        else:continue
                        columns=[column for column in value if column not in keys]
                        params=[Jsonb(value[column]) if isinstance(value[column],(dict,list)) else value[column] for column in columns]
                        conn.execute(sql.SQL('UPDATE {}.{} SET {} WHERE {}').format(sql.Identifier(schema),sql.Identifier(table),
                            sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(column)) for column in columns),where),[*params,*(row[key] for key in keys)])
                    else:
                        columns=list(value);params=[Jsonb(value[column]) if isinstance(value[column],(dict,list)) else value[column] for column in columns]
                        conn.execute(sql.SQL('INSERT INTO {}.{}({}) VALUES({})').format(sql.Identifier(schema),sql.Identifier(table),
                            sql.SQL(',').join(map(sql.Identifier,columns)),sql.SQL(',').join(sql.Placeholder() for column in columns)),params)
            for row in delta['ledgers']['pa_memory.tombstones']:
                conn.execute('DELETE FROM pa_runtime.object_heads WHERE owner=%s AND namespace=%s AND object_id=%s',(row['owner'],row['namespace'],row['object_ref']))
                conn.execute('DELETE FROM pa_runtime.object_versions WHERE owner=%s AND namespace=%s AND object_id=%s',(row['owner'],row['namespace'],row['object_ref']))
    return {'status':'delta_applied_egress_off','confirmation_restore':'consumed is monotone','unknown_restore':'no automatic resend'}
