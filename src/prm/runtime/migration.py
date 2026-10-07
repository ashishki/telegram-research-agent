"""Synthetic cutover parity and monotone receipt/tombstone transfer."""
from psycopg import sql
from psycopg.types.json import Jsonb
from .operations import OperationsRuntime,SCHEMAS,restore_bundle
from prm.storage.postgres import StorageError
import hashlib
import json


LEDGERS={
    ('pa_actions','confirmations'):('owner','key'),
    ('pa_actions','attempts'):('owner','key'),
    ('pa_delivery','attempts'):('owner','id'),
    ('pa_memory','tombstones'):('owner','namespace','object_ref'),
}


def state_manifest(target):
    with target.connect() as conn:
        tables=conn.execute('SELECT schemaname,tablename FROM pg_catalog.pg_tables WHERE schemaname=ANY(%s) ORDER BY schemaname,tablename',(list(SCHEMAS),)).fetchall()
        manifest={}
        for table in tables:
            schema,name=table['schemaname'],table['tablename']
            if (schema,name)==('pa_control','state'):continue
            rows=conn.execute(sql.SQL('SELECT to_jsonb(t) AS value FROM {}.{} t').format(sql.Identifier(schema),sql.Identifier(name))).fetchall()
            values=sorted(json.dumps(row['value'],sort_keys=True,default=str) for row in rows)
            manifest[schema+'.'+name]={'count':len(values),'sha256':hashlib.sha256('\n'.join(values).encode()).hexdigest()}
        return manifest


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
