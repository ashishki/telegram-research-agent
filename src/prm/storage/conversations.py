"""Persist the existing dialogue semantics; navigation and immutable results are separate."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime,timedelta
from functools import wraps
import hashlib
import json
import uuid
from psycopg.types.json import Jsonb
from prm.conversation import ConversationStore,ConversationState,ResponseObjectRef,ConfirmationRef,conversation_id_for
from .postgres import PostgresStore,StorageError,StateConflict,_canonical

DDL=(
    'CREATE SCHEMA pa_conversation',
    'CREATE TABLE pa_conversation.meta(version integer PRIMARY KEY,checksum text NOT NULL)',
    '''CREATE TABLE pa_conversation.states(owner text NOT NULL,id text NOT NULL,version bigint NOT NULL,
       expires timestamptz NOT NULL,payload jsonb NOT NULL,PRIMARY KEY(owner,id))''',
    '''CREATE TABLE pa_conversation.history(owner text NOT NULL,conversation_id text NOT NULL,id text NOT NULL,
       expires timestamptz NOT NULL,payload jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(owner,id))''',
    'GRANT USAGE ON SCHEMA pa_conversation TO pa_test_app',
    'GRANT SELECT ON pa_conversation.meta TO pa_test_app',
    'GRANT SELECT,INSERT,UPDATE,DELETE ON pa_conversation.states,pa_conversation.history TO pa_test_app',
)
CHECKSUM=hashlib.sha256('\n'.join(DDL).encode()).hexdigest()


def install_conversations(target):
    if target.user!='pa_test_migrator':raise StorageError('dedicated synthetic migrator required')
    with PostgresStore(target).transaction() as tx:
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)',(87291005,))
        if tx.conn.execute("SELECT to_regclass('pa_conversation.meta') AS meta").fetchone()['meta'] is None:
            for statement in DDL:tx.conn.execute(statement)
            tx.conn.execute('INSERT INTO pa_conversation.meta VALUES(1,%s)',(CHECKSUM,))
        else:_check(tx.conn)


def _check(conn):
    if conn.execute('SELECT version,checksum FROM pa_conversation.meta').fetchall()!=[{'version':1,'checksum':CHECKSUM}]:
        raise StorageError('unsupported durable dialogue schema')


def _confirmation(data):
    if data is None:return None
    data=dict(data);data['expires_at']=datetime.fromisoformat(data['expires_at'])
    return ConfirmationRef(**data)


def _encode_confirmation(value):
    if value is None:return None
    data=asdict(value);data['expires_at']=value.expires_at.isoformat();return data


class DurableConversationStore(ConversationStore):
    """One owner-bound backend, fresh state each call, SQL-serialized dialogue mutations."""
    def __init__(self,target,*,owner_ref,history_retention_seconds:int):
        if not isinstance(owner_ref,str) or not owner_ref or len(owner_ref)>128:raise StorageError('explicit owner required')
        if type(history_retention_seconds)is not int or not 0<=history_retention_seconds<=30*86400:
            raise StorageError('explicit bounded history retention required')
        self.store=PostgresStore(target);self.owner_ref=owner_ref;self.history_retention_seconds=history_retention_seconds
    def _lock(self,conn,conversation_id):
        value=int.from_bytes(hashlib.sha256((self.owner_ref+'\x1f'+conversation_id).encode()).digest()[:8],'big')%(2**63)
        conn.execute('SELECT pg_advisory_xact_lock(%s)',(value,))
    def _decode(self,tx,payload):
        data=dict(payload);objects=[]
        for ref in data['object_refs']:
            item=tx.get(self.owner_ref,'result',ref['response_ref'],version=1)
            if not item or item.payload['version']!=ref['version']:raise StorageError('dialogue result version unavailable')
            value=dict(item.payload);value['item_refs']=tuple(value['item_refs']);value['item_texts']=tuple(value['item_texts'])
            objects.append(ResponseObjectRef(**value))
        data['object_refs']=tuple(objects)
        for key in ('message_refs','pending_request_ids','cancelled_request_ids'):data[key]=tuple(data[key])
        data['current_confirmation_ref']=_confirmation(data['current_confirmation_ref'])
        data['visible_confirmation_refs']=tuple(_confirmation(value) for value in data['visible_confirmation_refs'])
        data['expires_at']=datetime.fromisoformat(data['expires_at'])
        return ConversationState(**data)
    def _save(self,tx,state,old_version):
        payload=asdict(state)
        for result in state.object_refs:
            value=json.loads(_canonical(asdict(result))[0])
            existing=tx.get(self.owner_ref,'result',result.response_ref)
            if existing:
                if existing.payload!=value:raise StateConflict('immutable dialogue result changed')
            else:tx.put(self.owner_ref,'result',result.response_ref,value,expected_version=0)
        payload['object_refs']=[{'response_ref':value.response_ref,'version':value.version} for value in state.object_refs]
        payload['current_confirmation_ref']=_encode_confirmation(state.current_confirmation_ref)
        payload['visible_confirmation_refs']=[_encode_confirmation(value) for value in state.visible_confirmation_refs]
        payload['expires_at']=state.expires_at.isoformat();payload=json.loads(_canonical(payload)[0])
        if old_version is None:
            tx.conn.execute('INSERT INTO pa_conversation.states VALUES(%s,%s,1,%s,%s)',(self.owner_ref,state.conversation_id,state.expires_at,Jsonb(payload)))
        else:
            changed=tx.conn.execute('''UPDATE pa_conversation.states SET version=version+1,expires=%s,payload=%s
                WHERE owner=%s AND id=%s AND version=%s RETURNING id''',(state.expires_at,Jsonb(payload),self.owner_ref,state.conversation_id,old_version)).fetchone()
            if not changed:raise StateConflict('dialogue version changed')
    def _run(self,method,chat_id,*args,**kwargs):
        conversation_id=conversation_id_for(chat_id)
        with self.store.transaction() as tx:
            _check(tx.conn);self._lock(tx.conn,conversation_id)
            now=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            row=tx.conn.execute('SELECT * FROM pa_conversation.states WHERE owner=%s AND id=%s FOR UPDATE',(self.owner_ref,conversation_id)).fetchone()
            local=ConversationStore()
            if row and row['expires']>now:local._states[conversation_id]=self._decode(tx,row['payload'])
            kwargs['now']=now
            result=getattr(local,method)(chat_id,*args,**kwargs)
            state=local._states.get(conversation_id)
            if state and method not in {'load','resolve_plain_yes','is_cancelled'}:
                self._save(tx,state,row['version'] if row else None)
                if method=='record_response' and self.history_retention_seconds:
                    text=str(kwargs.get('text',''))[:2400]
                    tx.conn.execute('INSERT INTO pa_conversation.history(owner,conversation_id,id,expires,payload) VALUES(%s,%s,%s,%s,%s)',
                        (self.owner_ref,conversation_id,uuid.uuid4().hex,now+timedelta(seconds=self.history_retention_seconds),
                         Jsonb({'role':'assistant','text':text,'response_ref':state.object_refs[0].response_ref})))
            elif row and not state:
                tx.conn.execute('DELETE FROM pa_conversation.states WHERE owner=%s AND id=%s',(self.owner_ref,conversation_id))
            return result
    def cancel_request(self,request_id,*,now=None):
        with self.store.transaction() as tx:
            _check(tx.conn)
            moment=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            rows=tx.conn.execute('''SELECT * FROM pa_conversation.states WHERE owner=%s AND expires>%s
                AND (payload->'pending_request_ids') ? %s ORDER BY id FOR UPDATE''',(self.owner_ref,moment,request_id)).fetchall()
            if len(rows)!=1:return None
            local=ConversationStore();state=self._decode(tx,rows[0]['payload']);local._states[state.conversation_id]=state
            updated=local.cancel_request(request_id,now=moment)
            if updated:self._save(tx,updated,rows[0]['version'])
            return updated
    def clear(self):
        with self.store.transaction() as tx:
            _check(tx.conn)
            tx.conn.execute('DELETE FROM pa_conversation.states WHERE owner=%s',(self.owner_ref,))
            tx.conn.execute('DELETE FROM pa_conversation.history WHERE owner=%s',(self.owner_ref,))
    def history(self,chat_id):
        with self.store.transaction() as tx:
            _check(tx.conn)
            return tuple({'role':row['payload']['role'],'text':row['payload']['text']} for row in tx.conn.execute('''SELECT payload FROM pa_conversation.history
                WHERE owner=%s AND conversation_id=%s AND expires>clock_timestamp() ORDER BY created_at,id''',(self.owner_ref,conversation_id_for(chat_id))).fetchall())
    def history_for_model(self,chat_id):
        with self.store.transaction() as tx:
            return tuple(row['payload'] for row in tx.conn.execute('''SELECT payload FROM pa_conversation.history WHERE owner=%s
                AND conversation_id=%s AND expires>clock_timestamp() AND payload->>'source_data_class'='model_generated' ORDER BY created_at,id''',
                (self.owner_ref,conversation_id_for(chat_id))).fetchall())
    def tag_response_source(self,response_ref,data_class):
        if data_class not in {'model_generated','private_archive','private_connector_metadata','private_connector_content','user_provided','public'}:
            raise StorageError('explicit response origin class required')
        with self.store.transaction() as tx:
            tx.conn.execute("UPDATE pa_conversation.history SET payload=jsonb_set(payload,'{source_data_class}',%s) WHERE owner=%s AND payload->>'response_ref'=%s",
                (Jsonb(data_class),self.owner_ref,response_ref))
    def response_origin(self,response_ref):
        ref='response_origin_'+hashlib.sha256(response_ref.encode()).hexdigest()[:32]
        item=self.store.get(self.owner_ref,'conversation',ref)
        return tuple(item.payload['data_classes']) if item else ('private_archive','private_connector_content','user_provided')

    def response_source_scopes(self,response_ref):
        ref='response_origin_'+hashlib.sha256(response_ref.encode()).hexdigest()[:32]
        item=self.store.get(self.owner_ref,'conversation',ref)
        return tuple(item.payload.get('source_scopes',())) if item else ()

    def record_origin(self,response_ref,data_classes,*,source_scopes=()):
        classes=tuple(sorted(set(data_classes)))
        if not classes or not set(classes)<= {'model_generated','private_archive','private_connector_metadata','private_connector_content','user_provided','public'}:
            raise StorageError('explicit response origin classes required')
        from prm.runtime.deletion import lineage_lock
        ref='response_origin_'+hashlib.sha256(response_ref.encode()).hexdigest()[:32]
        with self.store.transaction() as tx:
            lineage_lock(tx.conn,self.owner_ref)
            if tx.get(self.owner_ref,'result',response_ref) is None:raise StorageError('response unavailable')
            old=tx.get(self.owner_ref,'conversation',ref)
            payload={'response_ref':response_ref,'data_classes':list(classes),'source_scopes':list(source_scopes)}
            if old and old.payload!=payload:raise StateConflict('response origin cannot be relabelled')
            if old is None:tx.put(self.owner_ref,'conversation',ref,payload,expected_version=0)
            if tx.conn.execute("SELECT to_regclass('pa_memory.dependencies') AS meta").fetchone()['meta'] is not None:
                tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                    (self.owner_ref,'result',response_ref,'conversation',ref))
        if classes==('model_generated',):self.tag_response_source(response_ref,'model_generated')

    def purge_history(self):
        with self.store.transaction() as tx:
            _check(tx.conn)
            return tx.conn.execute('DELETE FROM pa_conversation.history WHERE owner=%s AND expires<=clock_timestamp()',(self.owner_ref,)).rowcount


def _method(name):
    @wraps(getattr(ConversationStore,name))
    def wrapped(self,chat_id,*args,**kwargs):return self._run(name,chat_id,*args,**kwargs)
    return wrapped


for _name in ('load','start','active_or_start','begin_new_topic','record_response','offer_confirmation','resolve_plain_yes',
              'start_request','finish_request','cancel','is_cancelled'):
    setattr(DurableConversationStore,_name,_method(_name))
