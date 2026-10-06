"""Durable exact confirmations and pre-dispatch attempt fences."""
from __future__ import annotations
from dataclasses import asdict,replace
from datetime import datetime
import hashlib
import json
from psycopg.types.json import Jsonb
from prm.confirmed_actions import (ActionProposal,ActionConfirmation,ConfirmedAction,ActionReceipt,
    ExecutionOutcome,confirm_action,ACTION_EXECUTE_CAPABILITY,ACTION_EXECUTE_OPERATION,ACTION_EXECUTE_PURPOSE,DATA_CLASS)
from prm.capabilities import is_authorized_operation,CapabilityDenied
from .postgres import PostgresStore,StorageError,StateConflict,_canonical
from .policy import DurableCapabilityRegistry

DDL=(
    'CREATE SCHEMA pa_actions',
    'CREATE TABLE pa_actions.meta(version integer PRIMARY KEY,checksum text NOT NULL)',
    '''CREATE TABLE pa_actions.proposals(owner text NOT NULL,ref text NOT NULL,version bigint NOT NULL,
       digest char(64) NOT NULL,payload jsonb NOT NULL,status text NOT NULL CHECK(status IN ('prepared','consumed','cancelled')),
       PRIMARY KEY(owner,ref))''',
    '''CREATE TABLE pa_actions.confirmations(owner text NOT NULL,key text NOT NULL,proposal_ref text NOT NULL,
       payload jsonb NOT NULL,consumed boolean NOT NULL DEFAULT false,PRIMARY KEY(owner,key))''',
    '''CREATE TABLE pa_actions.attempts(owner text NOT NULL,key text NOT NULL,receipt jsonb NOT NULL,
       PRIMARY KEY(owner,key),FOREIGN KEY(owner,key) REFERENCES pa_actions.confirmations(owner,key))''',
    'GRANT USAGE ON SCHEMA pa_actions TO pa_test_app',
    'GRANT SELECT ON pa_actions.meta TO pa_test_app',
    'GRANT SELECT,INSERT,UPDATE ON pa_actions.proposals,pa_actions.confirmations,pa_actions.attempts TO pa_test_app',
)
CHECKSUM=hashlib.sha256('\n'.join(DDL).encode()).hexdigest()


def install_actions(target):
    if target.user!='pa_test_migrator':raise StorageError('dedicated synthetic migrator required')
    with PostgresStore(target).transaction() as tx:
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)',(87291004,))
        if tx.conn.execute("SELECT to_regclass('pa_actions.meta') AS meta").fetchone()['meta'] is None:
            for statement in DDL:tx.conn.execute(statement)
            tx.conn.execute('INSERT INTO pa_actions.meta VALUES(1,%s)',(CHECKSUM,))
        else:_check(tx.conn)


def _check(conn):
    if conn.execute('SELECT version,checksum FROM pa_actions.meta').fetchall()!=[{'version':1,'checksum':CHECKSUM}]:
        raise StorageError('unsupported durable action schema')


def _proposal(payload):
    data=dict(payload);digest=data.pop('content_digest')
    for name in ('created_at','expires_at'):data[name]=datetime.fromisoformat(data[name].replace('Z','+00:00'))
    data['rationale_refs']=tuple(data['rationale_refs'])
    result=ActionProposal(**data)
    if result.digest!=digest:raise StorageError('proposal integrity mismatch')
    return result


def _confirmation(payload):
    data=dict(payload)
    for name in ('confirmed_at','expires_at'):data[name]=datetime.fromisoformat(data[name])
    return ActionConfirmation(**data)


def _encode_confirmation(value):
    result=asdict(value)
    for name in ('confirmed_at','expires_at'):result[name]=getattr(value,name).isoformat()
    return result


def _encode_receipt(value):
    result=asdict(value)
    if value.created_at:result['created_at']=value.created_at.isoformat()
    return result


def _receipt(payload):
    data=dict(payload)
    if data.get('created_at'):data['created_at']=datetime.fromisoformat(data['created_at'])
    ExecutionOutcome(data['status'],provider_operation_ref=data.get('provider_operation_ref',''),error_code=data.get('error_code',''))
    return ActionReceipt(**data)


class DurableActionStore:
    def __init__(self,target,*,owner_ref):self.store=PostgresStore(target);self.owner_ref=owner_ref
    def register(self,proposal:ActionProposal,*,expected_version=0):
        if type(proposal)is not ActionProposal or proposal.owner_ref!=self.owner_ref or proposal.status!='prepared':
            raise CapabilityDenied('proposal does not belong to the current owner')
        payload=json.loads(_canonical(proposal.to_payload())[0]);_proposal(payload)
        with self.store.transaction() as tx:
            conn=tx.conn;_check(conn)
            existing=conn.execute('SELECT version FROM pa_actions.proposals WHERE owner=%s AND ref=%s FOR UPDATE',(self.owner_ref,proposal.proposal_ref)).fetchone()
            if existing:
                if existing['version']!=expected_version or proposal.version<=expected_version:raise StateConflict('proposal version changed')
                attempts=conn.execute('''SELECT a.receipt FROM pa_actions.attempts a JOIN pa_actions.confirmations c
                    ON a.owner=c.owner AND a.key=c.key WHERE c.owner=%s AND c.proposal_ref=%s''',(self.owner_ref,proposal.proposal_ref)).fetchall()
                if any(row['receipt']['status']=='unknown' for row in attempts):raise StateConflict('unknown attempt must be reconciled before editing')
                conn.execute("UPDATE pa_actions.proposals SET version=%s,digest=%s,payload=%s,status='prepared' WHERE owner=%s AND ref=%s",
                    (proposal.version,proposal.digest,Jsonb(payload),self.owner_ref,proposal.proposal_ref))
            else:
                if expected_version!=0:raise StateConflict('proposal missing')
                conn.execute("INSERT INTO pa_actions.proposals VALUES(%s,%s,%s,%s,%s,'prepared')",
                    (self.owner_ref,proposal.proposal_ref,proposal.version,proposal.digest,Jsonb(payload)))
    def confirm(self,proposal_ref,*,actor_ref):
        with self.store.transaction() as tx:
            conn=tx.conn;_check(conn)
            row=conn.execute('SELECT * FROM pa_actions.proposals WHERE owner=%s AND ref=%s FOR UPDATE',(self.owner_ref,proposal_ref)).fetchone()
            if not row or row['status']!='prepared':raise CapabilityDenied('proposal is not currently confirmable')
            proposal=_proposal(row['payload']);now=conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            action=confirm_action(proposal,owner_ref=self.owner_ref,actor_ref=actor_ref,now=now)
            saved=conn.execute('''INSERT INTO pa_actions.confirmations(owner,key,proposal_ref,payload) VALUES(%s,%s,%s,%s)
                ON CONFLICT DO NOTHING RETURNING key''',(self.owner_ref,action.idempotency_key,proposal_ref,Jsonb(_encode_confirmation(action.confirmation)))).fetchone()
            if not saved:
                old=conn.execute('SELECT payload,consumed FROM pa_actions.confirmations WHERE owner=%s AND key=%s',(self.owner_ref,action.idempotency_key)).fetchone()
                if old['consumed']:raise CapabilityDenied('confirmation has already been consumed')
                action=replace(action,confirmation=_confirmation(old['payload']))
            return action
    def cancel(self,proposal_ref):
        with self.store.transaction() as tx:
            _check(tx.conn)
            tx.conn.execute("UPDATE pa_actions.proposals SET status='cancelled' WHERE owner=%s AND ref=%s",(self.owner_ref,proposal_ref))
    def get(self,key):
        with self.store.transaction() as tx:
            _check(tx.conn)
            row=tx.conn.execute('SELECT receipt FROM pa_actions.attempts WHERE owner=%s AND key=%s',(self.owner_ref,key)).fetchone()
            return _receipt(row['receipt']) if row else None
    def all(self):
        with self.store.transaction() as tx:
            _check(tx.conn)
            return tuple(_receipt(row['receipt']) for row in tx.conn.execute('SELECT receipt FROM pa_actions.attempts WHERE owner=%s ORDER BY key',(self.owner_ref,)).fetchall())
    def put(self,receipt):
        if type(receipt)is not ActionReceipt:raise StorageError('typed receipt required')
        ExecutionOutcome(receipt.status,provider_operation_ref=receipt.provider_operation_ref,error_code=receipt.error_code)
        with self.store.transaction() as tx:
            conn=tx.conn;_check(conn)
            old=conn.execute('SELECT receipt FROM pa_actions.attempts WHERE owner=%s AND key=%s FOR UPDATE',(self.owner_ref,receipt.idempotency_key)).fetchone()
            if not old:raise StateConflict('no durable attempt to settle')
            previous=_receipt(old['receipt'])
            if (previous.proposal_ref,previous.proposal_version,previous.content_digest)!=(receipt.proposal_ref,receipt.proposal_version,receipt.content_digest):
                raise StateConflict('receipt does not match durable attempt')
            if previous.status!='unknown' and receipt!=previous:raise StateConflict('terminal receipt cannot be rewritten')
            conn.execute('UPDATE pa_actions.attempts SET receipt=%s WHERE owner=%s AND key=%s',
                (Jsonb(_encode_receipt(receipt)),self.owner_ref,receipt.idempotency_key))
    def execute(self,action,*,request,executor,now=None):
        if type(action)is not ConfirmedAction or action.proposal.owner_ref!=self.owner_ref or request.owner_ref!=self.owner_ref:
            raise CapabilityDenied('foreign action owner')
        action=replace(action,proposal=replace(action.proposal,content=json.loads(_canonical(dict(action.proposal.content))[0])))
        if (action.confirmation.owner_ref,action.confirmation.actor_ref)!=(self.owner_ref,self.owner_ref):raise CapabilityDenied('foreign confirmation actor')
        proposal=action.proposal
        if (action.confirmation.proposal_ref,action.confirmation.proposal_version,action.confirmation.content_digest)!=(proposal.proposal_ref,proposal.version,proposal.digest):
            raise CapabilityDenied('confirmation does not bind the exact proposal')
        if (request.connection_ref,request.resource_ref,request.provider_id)!=(proposal.connection_ref,proposal.resource_ref,proposal.provider_id):
            raise CapabilityDenied('action request scope mismatch')
        existing=self.get(action.idempotency_key)
        if existing:
            if request.authorization and request.authorization.reservation:
                request.authorization.reservation.abandon_before_transport()
            return existing
        auth=request.authorization
        if not is_authorized_operation(auth,capability=ACTION_EXECUTE_CAPABILITY,operation=ACTION_EXECUTE_OPERATION,
            provider_ref=request.provider_id,data_class=DATA_CLASS,owner_ref=self.owner_ref,connection_ref=request.connection_ref,
            resource_ref=request.resource_ref,purpose=ACTION_EXECUTE_PURPOSE):raise CapabilityDenied('current scoped action grant required')
        if type(auth.reservation.registry)is not DurableCapabilityRegistry:raise CapabilityDenied('durable action requires shared policy')
        with self.store.transaction() as tx:
            conn=tx.conn;_check(conn)
            row=conn.execute('SELECT * FROM pa_actions.proposals WHERE owner=%s AND ref=%s FOR UPDATE',(self.owner_ref,proposal.proposal_ref)).fetchone()
            confirmation=conn.execute('SELECT * FROM pa_actions.confirmations WHERE owner=%s AND key=%s FOR UPDATE',(self.owner_ref,action.idempotency_key)).fetchone()
            moment=conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            if (not row or row['version']!=proposal.version or row['digest']!=proposal.digest or row['payload']!=proposal.to_payload() or row['status']!='prepared'
                or not confirmation or confirmation['consumed'] or _confirmation(confirmation['payload'])!=action.confirmation
                or action.consume(now=moment) is None):
                existing=conn.execute('SELECT receipt FROM pa_actions.attempts WHERE owner=%s AND key=%s',(self.owner_ref,action.idempotency_key)).fetchone()
                if existing:return _receipt(existing['receipt'])
                raise CapabilityDenied('stale, expired or unconfirmed action')
            pending=ActionReceipt(action.idempotency_key,proposal.proposal_ref,proposal.version,proposal.digest,'unknown',error_code='prepared',created_at=moment)
            conn.execute('UPDATE pa_actions.confirmations SET consumed=true WHERE owner=%s AND key=%s',(self.owner_ref,action.idempotency_key))
            conn.execute("UPDATE pa_actions.proposals SET status='consumed' WHERE owner=%s AND ref=%s",(self.owner_ref,proposal.proposal_ref))
            conn.execute('INSERT INTO pa_actions.attempts VALUES(%s,%s,%s)',(self.owner_ref,action.idempotency_key,Jsonb(_encode_receipt(pending))))
        def invoke():
            with self.store.transaction() as tx:
                row=tx.conn.execute('SELECT * FROM pa_actions.proposals WHERE owner=%s AND ref=%s FOR UPDATE',(self.owner_ref,proposal.proposal_ref)).fetchone()
                moment=tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
                if (row['status']=='cancelled' or row['version']!=proposal.version or row['digest']!=proposal.digest
                    or proposal.expires_at<=moment or action.confirmation.expires_at<=moment):
                    raise CapabilityDenied('proposal cancelled or changed before dispatch')
                outcome=executor.execute(action)
                if tx.conn.closed:raise StorageError('final action scope connection lost')
                return outcome
        try:
            outcome=auth.reservation.registry.execute_reserved((auth.reservation,),invoke)
            if type(outcome)is not ExecutionOutcome:outcome=ExecutionOutcome('unknown',error_code='invalid_provider_outcome')
        except Exception as error:outcome=ExecutionOutcome('unknown',error_code=type(error).__name__)
        receipt=replace(pending,status=outcome.status,provider_operation_ref=outcome.provider_operation_ref,error_code=outcome.error_code)
        self.put(receipt)
        return receipt
