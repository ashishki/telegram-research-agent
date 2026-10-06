"""Shared grants and conservative money/call reservations; source content is never authority."""
from __future__ import annotations
from dataclasses import asdict,replace
from datetime import datetime,timezone
import hashlib
import json
import uuid
import time

from psycopg.types.json import Jsonb
from prm.capabilities import (CapabilityRegistry,CapabilityGrant,AuthorizationRequest,AuthorizationDecision,
    BudgetReservation,CapabilityDenied,decode_capability_grant_document,_openai_compound_member_kind)
from .postgres import PostgresStore,SyntheticTarget,StorageError,StateConflict,migrate,_canonical

DDL=(
    'CREATE SCHEMA pa_policy',
    'CREATE TABLE pa_policy.meta(version integer PRIMARY KEY, checksum text NOT NULL)',
    '''CREATE TABLE pa_policy.grants(owner text NOT NULL,grant_id text NOT NULL,revision bigint NOT NULL CHECK(revision>0),
       document jsonb NOT NULL,PRIMARY KEY(owner,grant_id))''',
    '''CREATE TABLE pa_policy.windows(owner text NOT NULL,ref text NOT NULL,kind text NOT NULL CHECK(kind IN ('request','job','day','month')),
       capacity bigint NOT NULL CHECK(capacity>=0),reserved bigint NOT NULL DEFAULT 0 CHECK(reserved>=0),
       consumed bigint NOT NULL DEFAULT 0 CHECK(consumed>=0),starts timestamptz NOT NULL,ends timestamptz NOT NULL,
       CHECK(starts<ends),CHECK(reserved+consumed<=capacity),PRIMARY KEY(owner,ref))''',
    '''CREATE TABLE pa_policy.operations(owner text NOT NULL,ref text NOT NULL,state text NOT NULL
       CHECK(state IN ('reserved','prepared','accepted','unknown','cancelled')),upper_bound bigint NOT NULL CHECK(upper_bound>=0),
       actual bigint,windows jsonb NOT NULL,PRIMARY KEY(owner,ref))''',
    '''CREATE TABLE pa_policy.members(owner text NOT NULL,operation_ref text NOT NULL,member_id text NOT NULL,
       grant_id text NOT NULL,revision bigint NOT NULL,request jsonb NOT NULL,
       PRIMARY KEY(owner,operation_ref,member_id),FOREIGN KEY(owner,operation_ref) REFERENCES pa_policy.operations(owner,ref))''',
    '''CREATE TABLE pa_policy.call_counts(owner text NOT NULL,grant_id text NOT NULL,revision bigint NOT NULL,
       used bigint NOT NULL CHECK(used>=0),PRIMARY KEY(owner,grant_id,revision))''',
    'GRANT USAGE ON SCHEMA pa_policy TO pa_test_app',
    'GRANT SELECT ON pa_policy.meta TO pa_test_app',
    'GRANT SELECT,INSERT,UPDATE ON pa_policy.grants,pa_policy.windows,pa_policy.operations,pa_policy.call_counts TO pa_test_app',
    'GRANT SELECT,INSERT,DELETE ON pa_policy.members TO pa_test_app',
)
CHECKSUM=hashlib.sha256('\n'.join(DDL).encode()).hexdigest()


def install_policy(target:SyntheticTarget):
    if target.user!='pa_test_migrator':raise StorageError('dedicated synthetic migrator required')
    with PostgresStore(target).transaction() as tx:
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)',(87291003,))
        if tx.conn.execute("SELECT to_regclass('pa_policy.meta') AS meta").fetchone()['meta'] is None:
            for statement in DDL:tx.conn.execute(statement)
            tx.conn.execute('INSERT INTO pa_policy.meta VALUES(1,%s)',(CHECKSUM,))
        else:_check_schema(tx.conn)


def _check_schema(conn):
    if conn.execute('SELECT version,checksum FROM pa_policy.meta').fetchall()!=[{'version':1,'checksum':CHECKSUM}]:
        raise StorageError('unsupported durable policy schema')


def _ref(value):
    if not isinstance(value,str) or not value or len(value)>128 or value.strip()!=value:raise StorageError('invalid opaque policy reference')
    return value


def _amount(value):
    if type(value) is not int or not 0<=value<2**63:raise StorageError('known bounded integer cost required')
    return value


def _grant_document(grant,now):
    CapabilityRegistry((grant,))  # reuse the existing sealing/validation contract
    return {'schema_version':'assistant.capability_grant.v1','grant_id':grant.grant_id,'owner_ref':grant.owner_ref,
        'connection_ref':grant.connection_ref,'capability':{'name':grant.capability,'resource_refs':list(grant.resource_refs),
        'operations':list(grant.operations),'data_classes':list(grant.data_classes),'purpose':grant.purpose},
        'provider_policy':{'egress':'allow' if grant.provider_policy.egress_allowed else 'deny',
        'permitted_provider_refs':list(grant.provider_policy.permitted_provider_refs),
        'fallback_allowed':grant.provider_policy.fallback_allowed,'maximum_request_count':grant.provider_policy.maximum_request_count},
        'validity':{'issued_at':grant.issued_at.isoformat(),'expires_at':grant.expires_at.isoformat() if grant.expires_at else None,
        'revoked_at':grant.revoked_at.isoformat() if grant.revoked_at else None,'revision':grant.revision},'status':'active'}


def _decode(row,now):
    doc=json.loads(json.dumps(row['document']))
    validity=doc['validity'];issued=datetime.fromisoformat(validity['issued_at'].replace('Z','+00:00'))
    check_now=max(now,issued)
    revoked=datetime.fromisoformat(validity['revoked_at'].replace('Z','+00:00')) if validity['revoked_at'] else None
    expires=datetime.fromisoformat(validity['expires_at'].replace('Z','+00:00')) if validity['expires_at'] else None
    doc['status']='revoked' if revoked and revoked<=check_now else 'expired' if expires and expires<=check_now else 'active'
    grant=decode_capability_grant_document(doc,now=check_now)
    if grant.grant_id!=row['grant_id'] or grant.owner_ref!=row['owner'] or grant.revision!=row['revision']:
        raise StorageError('corrupt grant binding')
    return grant


class DurableReservation(BudgetReservation):
    __slots__=('member_id',)
    def __init__(self,*,member_id,**kwargs):super().__init__(**kwargs);self.member_id=member_id


class DurableCapabilityRegistry(CapabilityRegistry):
    """The same adapter contract, with fresh DB authority and atomic operation groups."""
    def __init__(self,target:SyntheticTarget,*,budget_refs:tuple[str,...],job_budget:bool=False):
        super().__init__(())
        if not isinstance(budget_refs,tuple) or len(set(budget_refs))!=len(budget_refs) or len(budget_refs) not in {3,4}:
            raise StorageError('explicit request/day/month budget context required')
        for value in budget_refs:_ref(value)
        self.store=PostgresStore(target);self.budget_refs=tuple(sorted(budget_refs));self.job_budget=job_budget
    def _now(self,conn):return conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
    def _grants(self,conn,owner,now,*,lock=False):
        rows=conn.execute('SELECT owner,grant_id,revision,document FROM pa_policy.grants WHERE owner=%s ORDER BY grant_id'+(' FOR UPDATE' if lock else ''),(owner,)).fetchall()
        return [_decode(row,now) for row in rows]
    def _decision(self,conn,request,*,lock=False):
        _check_schema(conn);now=self._now(conn)
        grants=self._grants(conn,request.owner_ref,now,lock=lock)
        return CapabilityRegistry(grants).authorize(request,now=now),grants,now
    def register_grant(self,grant:CapabilityGrant):
        if type(grant) is not CapabilityGrant:raise StorageError('typed grant required')
        with self.store.transaction() as tx:
            _check_schema(tx.conn);now=self._now(tx.conn);doc=_grant_document(grant,now)
            row=tx.conn.execute('''INSERT INTO pa_policy.grants VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING grant_id''',
                               (grant.owner_ref,grant.grant_id,grant.revision,Jsonb(doc))).fetchone()
            if row is None:raise StateConflict('grant already registered')
    def replace_grant(self,grant:CapabilityGrant):
        if type(grant) is not CapabilityGrant:raise StorageError('typed grant required')
        with self.store.transaction() as tx:
            _check_schema(tx.conn);doc=_grant_document(grant,self._now(tx.conn))
            row=tx.conn.execute('''UPDATE pa_policy.grants SET revision=%s,document=%s
                WHERE owner=%s AND grant_id=%s AND revision<%s RETURNING grant_id''',
                (grant.revision,Jsonb(doc),grant.owner_ref,grant.grant_id,grant.revision)).fetchone()
            if row is None:raise StateConflict('grant replacement must increase current revision')
    def revoke_grant(self,grant_ref,*,owner_ref,revoked_at=None):
        if revoked_at is not None:raise StorageError('revocation uses database time')
        with self.store.transaction() as tx:
            _check_schema(tx.conn)
            row=tx.conn.execute('SELECT owner,grant_id,revision,document FROM pa_policy.grants WHERE owner=%s AND grant_id=%s FOR UPDATE',(owner_ref,grant_ref)).fetchone()
            if row is None:raise StorageError('unknown scoped grant')
            grant=_decode(row,self._now(tx.conn));grant=replace(grant,revoked_at=self._now(tx.conn),revision=grant.revision+1)
            tx.conn.execute('UPDATE pa_policy.grants SET revision=%s,document=%s WHERE owner=%s AND grant_id=%s',
                (grant.revision,Jsonb(_grant_document(grant,self._now(tx.conn))),owner_ref,grant_ref))
    def configure_window(self,*,owner,ref,kind,capacity,starts,ends):
        _ref(owner);_ref(ref);_amount(capacity)
        if kind not in {'request','job','day','month'} or starts.tzinfo is None or ends.tzinfo is None or starts>=ends:
            raise StorageError('invalid explicit budget window')
        with self.store.transaction() as tx:
            _check_schema(tx.conn)
            row=tx.conn.execute('''INSERT INTO pa_policy.windows(owner,ref,kind,capacity,starts,ends)
                VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING ref''',(owner,ref,kind,capacity,starts,ends)).fetchone()
            if row is None:raise StateConflict('budget windows cannot reset existing spend')
    def authorize(self,request,*,now=None):
        if now is not None:raise StorageError('durable policy uses database time')
        request=replace(request)
        try:
            with self.store.transaction() as tx:return self._decision(tx.conn,request)[0]
        except (StorageError,ValueError,KeyError,TypeError):return self._deny(request,'durable_policy_unavailable')
    def _deny(self,request,reason,decision=None):
        if decision is not None:return replace(decision,allowed=False,reason=reason,reservation=None)
        return AuthorizationDecision(False,reason,None,None,request.owner_ref,request.connection_ref,request.resource_ref,
            request.capability,request.operation,request.data_class,request.provider_ref,request.purpose,request.operation_ref)
    def authorize_and_reserve(self,request,*,upper_bound=None,now=None):
        if now is not None:raise StorageError('durable policy uses database time')
        request=replace(request)
        if request.operation_ref is None:return self._deny(request,'operation_reference_required')
        if upper_bound is None:return self._deny(request,'unknown_price')
        _amount(upper_bound)
        try:
            with self.store.transaction() as tx:
                conn=tx.conn;decision,grants,moment=self._decision(conn,request,lock=True)
                if not decision.allowed:return decision
                grant=next(g for g in grants if g.grant_id==decision.grant_ref)
                sealed=replace(request,grant_ref=grant.grant_id,expected_grant_revision=grant.revision)
                op=conn.execute('SELECT * FROM pa_policy.operations WHERE owner=%s AND ref=%s FOR UPDATE',(request.owner_ref,request.operation_ref)).fetchone()
                if op:
                    if op['state']!='reserved':return self._deny(request,'operation_already_attempted',decision)
                    members=conn.execute('SELECT request FROM pa_policy.members WHERE owner=%s AND operation_ref=%s',(request.owner_ref,request.operation_ref)).fetchall()
                    kinds={_openai_compound_member_kind(AuthorizationRequest(**m['request'])) for m in members}
                    kind=_openai_compound_member_kind(sealed)
                    if (len(members)!=1 or kind is None or kinds!=({'text'} if kind=='context' else {'context'})
                        or op['upper_bound']!=upper_bound or op['windows']!=list(self.budget_refs)
                        or any(m['request']['provider_ref']!=sealed.provider_ref or m['request']['connection_ref']!=sealed.connection_ref for m in members)):
                        return self._deny(request,'operation_scope_conflict',decision)
                count=conn.execute('SELECT used FROM pa_policy.call_counts WHERE owner=%s AND grant_id=%s AND revision=%s',
                    (grant.owner_ref,grant.grant_id,grant.revision)).fetchone()
                if (count['used'] if count else 0)>=grant.provider_policy.maximum_request_count:return self._deny(request,'grant_budget_exhausted',decision)
                if not op:
                    windows=conn.execute('SELECT * FROM pa_policy.windows WHERE owner=%s AND ref=ANY(%s) ORDER BY ref FOR UPDATE',
                        (request.owner_ref,list(self.budget_refs))).fetchall()
                    kinds={w['kind'] for w in windows};required={'request','day','month'}|({'job'} if self.job_budget else set())
                    if len(windows)!=len(self.budget_refs) or kinds!=required or len(kinds)!=len(windows):return self._deny(request,'budget_context_missing',decision)
                    if any(not w['starts']<=moment<w['ends'] or w['reserved']+w['consumed']+upper_bound>w['capacity'] for w in windows):
                        return self._deny(request,'budget_exhausted',decision)
                    conn.execute('UPDATE pa_policy.windows SET reserved=reserved+%s WHERE owner=%s AND ref=ANY(%s)',(upper_bound,request.owner_ref,list(self.budget_refs)))
                    conn.execute("INSERT INTO pa_policy.operations VALUES(%s,%s,'reserved',%s,NULL,%s)",
                        (request.owner_ref,request.operation_ref,upper_bound,Jsonb(list(self.budget_refs))))
                conn.execute('''INSERT INTO pa_policy.call_counts VALUES(%s,%s,%s,1)
                    ON CONFLICT(owner,grant_id,revision) DO UPDATE SET used=pa_policy.call_counts.used+1''',(grant.owner_ref,grant.grant_id,grant.revision))
                member=uuid.uuid4().hex
                conn.execute('INSERT INTO pa_policy.members VALUES(%s,%s,%s,%s,%s,%s)',
                    (request.owner_ref,request.operation_ref,member,grant.grant_id,grant.revision,Jsonb(asdict(sealed))))
                reservation=DurableReservation(registry=self,request=sealed,grant_ref=grant.grant_id,grant_revision=grant.revision,member_id=member)
                return replace(decision,operation_ref=request.operation_ref,reservation=reservation)
        except (StorageError,ValueError,KeyError,TypeError):return self._deny(request,'durable_policy_unavailable')
    def _reservation_is_current(self,reservation):
        request=reservation._request
        try:
            with self.store.transaction() as tx:
                decision,_,_=self._decision(tx.conn,request)
                row=tx.conn.execute('''SELECT o.state,m.request FROM pa_policy.operations o JOIN pa_policy.members m
                    ON o.owner=m.owner AND o.ref=m.operation_ref WHERE o.owner=%s AND o.ref=%s AND m.member_id=%s''',
                    (request.owner_ref,request.operation_ref,reservation.member_id)).fetchone()
                return bool(decision.allowed and row and row['state']=='reserved' and row['request']==asdict(request))
        except (StorageError,ValueError,KeyError,TypeError):return False
    def _commit_durable_transport(self,reservations):
        if not reservations or any(type(r) is not DurableReservation or r.registry is not self for r in reservations):return False
        owners={r._request.owner_ref for r in reservations};refs={r.operation_ref for r in reservations}
        if len(owners)!=1 or len(refs)!=1:return False
        owner=next(iter(owners));ref=next(iter(refs))
        try:
            with self.store.transaction() as tx:
                conn=tx.conn;_check_schema(conn);now=self._now(conn);grants=self._grants(conn,owner,now,lock=True)
                op=conn.execute('SELECT * FROM pa_policy.operations WHERE owner=%s AND ref=%s FOR UPDATE',(owner,ref)).fetchone()
                members=conn.execute('SELECT * FROM pa_policy.members WHERE owner=%s AND operation_ref=%s',(owner,ref)).fetchall()
                if not op or op['state']!='reserved' or {m['member_id'] for m in members}!={r.member_id for r in reservations}:return False
                auth=CapabilityRegistry(grants)
                if any(r._consumed or r._abandoned or not auth.authorize(r._request,now=now).allowed for r in reservations):return False
                by_id={m['member_id']:m for m in members}
                if any(by_id[r.member_id]['request']!=asdict(r._request) for r in reservations):return False
                conn.execute("UPDATE pa_policy.operations SET state='prepared' WHERE owner=%s AND ref=%s",(owner,ref))
            for r in reservations:r._consumed=True;r._transport_committed=True
            return True
        except (StorageError,ValueError,KeyError,TypeError):return False
    def _commit_single_transport_reservation(self,reservation):return self._commit_durable_transport((reservation,))
    def _record_operation_outcome(self,reservation,outcome):
        if outcome not in {'accepted','unknown'}:raise StorageError('invalid provider outcome')
        self.settle(reservation._request.owner_ref,reservation.operation_ref,outcome=outcome)
    def settle(self,owner,operation_ref,*,outcome,actual=None):
        if outcome not in {'accepted','unknown'}:raise StorageError('invalid outcome')
        if actual is not None:_amount(actual)
        with self.store.transaction() as tx:
            conn=tx.conn;_check_schema(conn)
            op=conn.execute('SELECT * FROM pa_policy.operations WHERE owner=%s AND ref=%s FOR UPDATE',(owner,operation_ref)).fetchone()
            if not op or op['state'] not in {'prepared','accepted','unknown'}:raise StateConflict('no attempted operation to settle')
            if actual is not None and actual>op['upper_bound']:raise StorageError('reported cost exceeds reserved bound')
            if op['actual'] is not None:
                if actual==op['actual']:return
                raise StateConflict('usage already settled')
            windows=conn.execute('SELECT ref FROM pa_policy.windows WHERE owner=%s AND ref=ANY(%s) ORDER BY ref FOR UPDATE',(owner,op['windows'])).fetchall()
            if len(windows)!=len(op['windows']):raise StorageError('budget ledger incomplete')
            charge=actual if actual is not None else op['upper_bound']
            if op['state']=='prepared':
                conn.execute('UPDATE pa_policy.windows SET reserved=reserved-%s,consumed=consumed+%s WHERE owner=%s AND ref=ANY(%s)',
                    (op['upper_bound'],charge,owner,op['windows']))
            elif actual is not None:
                conn.execute('UPDATE pa_policy.windows SET consumed=consumed-%s WHERE owner=%s AND ref=ANY(%s)',
                    (op['upper_bound']-actual,owner,op['windows']))
            conn.execute('UPDATE pa_policy.operations SET state=%s,actual=%s WHERE owner=%s AND ref=%s',(outcome,actual,owner,operation_ref))
    def _abandon_operation(self,reservation):
        request=reservation._request
        with self.store.transaction() as tx:
            conn=tx.conn;_check_schema(conn)
            self._grants(conn,request.owner_ref,self._now(conn),lock=True)
            op=conn.execute('SELECT * FROM pa_policy.operations WHERE owner=%s AND ref=%s FOR UPDATE',(request.owner_ref,request.operation_ref)).fetchone()
            if not op or op['state']!='reserved':return
            conn.execute('DELETE FROM pa_policy.members WHERE owner=%s AND operation_ref=%s AND member_id=%s',(request.owner_ref,request.operation_ref,reservation.member_id))
            remaining=conn.execute('SELECT request FROM pa_policy.members WHERE owner=%s AND operation_ref=%s',(request.owner_ref,request.operation_ref)).fetchall()
            if _openai_compound_member_kind(request)=='context' and len(remaining)==1 and _openai_compound_member_kind(AuthorizationRequest(**remaining[0]['request']))=='text':return
            conn.execute('UPDATE pa_policy.windows SET reserved=reserved-%s WHERE owner=%s AND ref=ANY(%s)',(op['upper_bound'],request.owner_ref,op['windows']))
            conn.execute("UPDATE pa_policy.operations SET state='cancelled' WHERE owner=%s AND ref=%s",(request.owner_ref,request.operation_ref))
    def snapshot(self,owner):
        with self.store.transaction() as tx:
            _check_schema(tx.conn)
            return {'windows':tx.conn.execute('SELECT ref,capacity,reserved,consumed FROM pa_policy.windows WHERE owner=%s ORDER BY ref',(owner,)).fetchall(),
                'operations':tx.conn.execute('SELECT ref,state,upper_bound,actual FROM pa_policy.operations WHERE owner=%s ORDER BY ref',(owner,)).fetchall()}
    def execute_reserved(self,reservations,transport):
        """Invoke one bounded adapter under current grant locks; durable attempt precedes I/O."""
        reservations=tuple(reservations)
        if not self._commit_durable_transport(reservations):raise CapabilityDenied('current durable transport authorization denied')
        owner=reservations[0]._request.owner_ref;operation=reservations[0].operation_ref
        try:
            with self.store.transaction() as tx:
                conn=tx.conn;_check_schema(conn);now=self._now(conn)
                ids=sorted({r.grant_ref for r in reservations})
                rows=conn.execute('''SELECT owner,grant_id,revision,document FROM pa_policy.grants
                    WHERE owner=%s AND grant_id=ANY(%s) ORDER BY grant_id FOR UPDATE''',(owner,ids)).fetchall()
                auth=CapabilityRegistry([_decode(row,now) for row in rows])
                if any(not auth.authorize(r._request,now=now).allowed for r in reservations):
                    raise CapabilityDenied('grant changed before transport')
                started=time.monotonic()
                result=transport()
                if time.monotonic()-started>10:raise StorageError('bounded transport deadline exceeded; outcome requires reconciliation')
            self.settle(owner,operation,outcome='accepted')
            return result
        except Exception:
            self.settle(owner,operation,outcome='unknown')
            raise
