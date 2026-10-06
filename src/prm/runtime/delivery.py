"""Precommitted effect attempts, final policy locks and explicit reconciliation."""
from __future__ import annotations
from dataclasses import dataclass, replace
from datetime import timedelta
import hashlib
import uuid
from zoneinfo import ZoneInfo
from psycopg.types.json import Jsonb

from prm.capabilities import AuthorizationRequest, CapabilityDenied
from prm.storage.postgres import PostgresStore, StorageError, StateConflict, _canonical
from prm.storage.policy import DurableCapabilityRegistry
from prm.watch_jobs import _subscription_from_payload, _subscription_effect, _notification_from_payload, _in_quiet_hours, render_watch_notification

DDL = (
    'CREATE SCHEMA pa_delivery',
    'CREATE TABLE pa_delivery.meta(version integer PRIMARY KEY,checksum text NOT NULL)',
    '''CREATE TABLE pa_delivery.attempts(owner text NOT NULL,id text NOT NULL,attempt_ref text NOT NULL,
       kind text NOT NULL,source_ref text NOT NULL,destination_ref text NOT NULL,digest text NOT NULL,
       payload jsonb NOT NULL,status text NOT NULL CHECK(status IN ('unknown','sent','not_sent')),
       provider_receipt text NOT NULL DEFAULT '',reason text NOT NULL DEFAULT 'prepared',
       created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(owner,id),UNIQUE(attempt_ref))''',
    '''CREATE TABLE pa_delivery.quotas(owner text NOT NULL,id text NOT NULL,schedule_id text NOT NULL,
       local_day date NOT NULL,PRIMARY KEY(owner,id))''',
    'GRANT USAGE ON SCHEMA pa_delivery TO pa_test_app',
    'GRANT SELECT ON pa_delivery.meta TO pa_test_app',
    'GRANT SELECT,INSERT,UPDATE ON pa_delivery.attempts TO pa_test_app',
    'GRANT SELECT,INSERT ON pa_delivery.quotas TO pa_test_app',
)
CHECKSUM = hashlib.sha256('\n'.join(DDL).encode()).hexdigest()


def install_delivery(target):
    if target.user != 'pa_test_migrator':
        raise StorageError('dedicated synthetic migrator required')
    with PostgresStore(target).transaction() as tx:
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)', (87291009,))
        if tx.conn.execute("SELECT to_regclass('pa_delivery.meta') AS meta").fetchone()['meta'] is None:
            for statement in DDL:
                tx.conn.execute(statement)
            tx.conn.execute('INSERT INTO pa_delivery.meta VALUES(1,%s)', (CHECKSUM,))
        else:
            _check(tx.conn)


def _check(conn):
    if conn.execute('SELECT version,checksum FROM pa_delivery.meta').fetchall() != [{'version': 1, 'checksum': CHECKSUM}]:
        raise StorageError('unsupported delivery schema')


@dataclass(frozen=True)
class TransportReceipt:
    provider_receipt: str


@dataclass(frozen=True)
class ReconciliationObservation:
    attempt_ref: str
    destination_ref: str
    content_digest: str
    outcome: str
    evidence_ref: str
    provider_receipt: str = ''


class KnownDeliveryRejection(Exception):
    """Adapter proves the exact effect was rejected before acceptance."""


class DeliveryExecutor:
    def __init__(self, target, *, registry: DurableCapabilityRegistry, sender):
        if type(registry) is not DurableCapabilityRegistry or registry.store.target != target:
            raise StorageError('shared current durable policy required')
        self.store, self.registry, self.sender = PostgresStore(target), registry, sender

    def attempt(self, *, owner, delivery_id):
        with self.store.transaction() as tx:
            _check(tx.conn)
            return tx.conn.execute('SELECT * FROM pa_delivery.attempts WHERE owner=%s AND id=%s', (owner, delivery_id)).fetchone()

    def deliver_result(self, *, owner, job_id, destination_ref, upper_bound, effect_lease=None):
        with self.store.transaction() as tx:
            job = tx.conn.execute('SELECT status,result_ref FROM pa_jobs.jobs WHERE owner=%s AND id=%s', (owner, job_id)).fetchone()
            if job is None or job['status'] != 'completed':
                raise CapabilityDenied('completed owner-bound result required')
            result = tx.get(owner, 'result', job['result_ref'], version=1)
            if result is None or not isinstance(result.payload.get('text'), str):
                raise StorageError('result unavailable')
            payload = {'text': result.payload['text'], 'result_ref': result.object_id, 'result_digest': result.digest,
                       'request_ref': result.payload.get('request_ref')}
            if effect_lease is not None:
                from prm.storage.jobs import JobQueue
                if (effect_lease.owner != owner or effect_lease.mode != 'effect'
                    or effect_lease.payload.get('effect_key') != 'answer_' + job_id
                    or (effect_lease.payload['input_namespace'], effect_lease.payload['input_ref'], effect_lease.payload['input_version'], effect_lease.payload['input_digest'])
                       != ('result', result.object_id, result.version, result.digest)):
                    raise CapabilityDenied('effect lease does not bind the exact result')
                JobQueue(self.store.target)._fenced(tx, effect_lease)
        return self._deliver(owner=owner, delivery_id='answer_' + job_id, kind='answer', source_ref=job_id,
            destination_ref=destination_ref, payload=payload, upper_bound=upper_bound, effect_lease=effect_lease)

    def deliver_watch(self, *, owner, notification_id, upper_bound):
        with self.store.transaction() as tx:
            note = tx.conn.execute('SELECT * FROM pa_schedule.notifications WHERE owner=%s AND id=%s', (owner, notification_id)).fetchone()
            if note is None:
                raise CapabilityDenied('owner-bound notification required')
            subrow = tx.conn.execute('SELECT payload FROM pa_schedule.schedules WHERE owner=%s AND id=%s', (owner, note['schedule_id'])).fetchone()
            sub = _subscription_from_payload(subrow['payload'])
            notification = _notification_from_payload(note['payload'])
            payload = {'text': render_watch_notification(notification), 'schedule_id': note['schedule_id'],
                       'revision': note['revision'], 'notification_digest': _canonical(note['payload'])[1]}
        return self._deliver(owner=owner, delivery_id='watch_' + notification_id, kind='watch', source_ref=notification_id,
            destination_ref=sub.destination_ref, payload=payload, upper_bound=upper_bound)

    def _guard_watch(self, tx, owner, source_ref, payload, destination_ref, *, reserve_quota=False, delivery_id=None):
        conn = tx.conn
        # Scope locks persist through the actual sender. Pause acknowledgements
        # wait if dispatch already won; they never claim an effect was undone.
        row = conn.execute('SELECT * FROM pa_schedule.schedules WHERE owner=%s AND id=%s FOR UPDATE', (owner, payload['schedule_id'])).fetchone()
        if row is None:
            raise CapabilityDenied('subscription unavailable')
        sub = _subscription_from_payload(row['payload'])
        now = conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
        note = conn.execute('SELECT * FROM pa_schedule.notifications WHERE owner=%s AND id=%s FOR UPDATE', (owner, source_ref)).fetchone()
        if (row['revision'] != payload['revision'] or sub.destination_ref != destination_ref
            or _subscription_effect(sub, now=now) != 'active' or note is None or note['status'] != 'queued'
            or note['due_at'] > now or _canonical(note['payload'])[1] != payload['notification_digest']):
            raise CapabilityDenied('notification paused, revised, superseded or not due')
        local = now.astimezone(ZoneInfo(sub.timezone_name))
        if _in_quiet_hours(sub, local=local) and not (note['payload']['urgent'] and sub.allow_urgent_during_quiet_hours):
            raise CapabilityDenied('quiet hours')
        if reserve_quota:
            count = conn.execute('SELECT count(*) AS n FROM pa_delivery.quotas WHERE owner=%s AND schedule_id=%s AND local_day=%s',
                                 (owner, sub.subscription_id, local.date())).fetchone()['n']
            if count >= sub.daily_cap:
                raise CapabilityDenied('daily delivery cap')
            conn.execute('INSERT INTO pa_delivery.quotas VALUES(%s,%s,%s,%s)', (owner, delivery_id, sub.subscription_id, local.date()))
        else:
            quota = conn.execute('SELECT local_day FROM pa_delivery.quotas WHERE owner=%s AND id=%s', (owner, delivery_id)).fetchone()
            if quota is None or quota['local_day'] != local.date():
                raise CapabilityDenied('delivery day changed after preparation')

    def _deliver(self, *, owner, delivery_id, kind, source_ref, destination_ref, payload, upper_bound, effect_lease=None):
        if not isinstance(destination_ref, str) or not 0 < len(destination_ref) <= 128:
            raise StorageError('bounded destination reference required')
        _, digest = _canonical(payload)
        existing = self.attempt(owner=owner, delivery_id=delivery_id)
        if existing:
            if (existing['digest'], existing['destination_ref'], existing['kind'], existing['source_ref']) != (digest, destination_ref, kind, source_ref):
                raise StateConflict('delivery identity already binds different content or destination')
            return existing
        operation = 'send_' + hashlib.sha256(delivery_id.encode()).hexdigest()[:40]
        request = AuthorizationRequest(owner_ref=owner, connection_ref=None,
            capability='assistant.watch_delivery' if kind == 'watch' else 'assistant.result_delivery',
            resource_ref=destination_ref, operation='deliver', data_class='model_generated' if kind == 'watch' else 'private_archive',
            provider_ref='provider_telegram', purpose='watch.delivery' if kind == 'watch' else 'answer.delivery', operation_ref=operation)
        decision = self.registry.authorize_and_reserve(request, upper_bound=upper_bound)
        if not decision.allowed:
            concurrent = self.attempt(owner=owner, delivery_id=delivery_id)
            if concurrent:
                if concurrent['digest'] != digest or concurrent['destination_ref'] != destination_ref:
                    raise StateConflict('concurrent delivery scope differs')
                return concurrent
            raise CapabilityDenied(decision.reason)
        try:
            with self.store.transaction() as tx:
                _check(tx.conn)
                if kind == 'watch':
                    self._guard_watch(tx, owner, source_ref, payload, destination_ref, reserve_quota=True, delivery_id=delivery_id)
                if effect_lease is not None:
                    from prm.storage.jobs import JobQueue
                    JobQueue(self.store.target)._fenced(tx, effect_lease)
                tx.conn.execute('''INSERT INTO pa_delivery.attempts(owner,id,attempt_ref,kind,source_ref,destination_ref,digest,payload,status)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'unknown')''',
                    (owner, delivery_id, 'attempt_' + uuid.uuid4().hex, kind, source_ref, destination_ref, digest, Jsonb(payload)))
        except Exception:
            decision.reservation.abandon_before_transport()
            raise
        status, receipt, reason = 'unknown', '', 'transport_outcome_unknown'
        def transport():
            with self.store.transaction() as tx:
                if kind == 'watch':
                    self._guard_watch(tx, owner, source_ref, payload, destination_ref, delivery_id=delivery_id)
                if effect_lease is not None:
                    from prm.storage.jobs import JobQueue
                    JobQueue(self.store.target)._fenced(tx, effect_lease)
                row = tx.conn.execute('SELECT * FROM pa_delivery.attempts WHERE owner=%s AND id=%s FOR UPDATE', (owner, delivery_id)).fetchone()
                if row['status'] != 'unknown' or row['digest'] != digest:
                    raise CapabilityDenied('attempt already settled or changed')
                result = self.sender(destination_ref, payload['text'], row['attempt_ref'])
                if tx.conn.closed:
                    raise StorageError('final scope connection lost; retain unknown attempt')
                return result
        try:
            result = self.registry.execute_reserved((decision.reservation,), transport)
            if type(result) is not TransportReceipt or not isinstance(result.provider_receipt, str) or not 0 < len(result.provider_receipt) <= 256:
                raise StorageError('typed actual provider receipt required')
            status, receipt, reason = 'sent', result.provider_receipt, 'provider_accepted'
        except KnownDeliveryRejection:
            status, reason = 'not_sent', 'provider_rejected'
        except Exception:
            pass
        with self.store.transaction() as tx:
            row = tx.conn.execute('SELECT status FROM pa_delivery.attempts WHERE owner=%s AND id=%s FOR UPDATE', (owner, delivery_id)).fetchone()
            if row['status'] == 'unknown':
                tx.conn.execute('UPDATE pa_delivery.attempts SET status=%s,provider_receipt=%s,reason=%s WHERE owner=%s AND id=%s',
                                (status, receipt, reason, owner, delivery_id))
                if kind == 'watch' and status != 'unknown':
                    tx.conn.execute('UPDATE pa_schedule.notifications SET status=%s WHERE owner=%s AND id=%s', (status, owner, source_ref))
        return self.attempt(owner=owner, delivery_id=delivery_id)

    def reconcile(self, *, owner, delivery_id, adapter, upper_bound):
        pending = self.attempt(owner=owner, delivery_id=delivery_id)
        if pending is None:
            raise StorageError('attempt unavailable')
        if pending['status'] != 'unknown' or adapter is None:
            return pending
        request = AuthorizationRequest(owner_ref=owner, connection_ref=None, capability='assistant.delivery_reconciliation',
            resource_ref=pending['destination_ref'], operation='read', data_class='private_connector_metadata',
            provider_ref='provider_telegram', purpose='delivery.reconcile', operation_ref='reconcile_' + uuid.uuid4().hex)
        decision = self.registry.authorize_and_reserve(request, upper_bound=upper_bound)
        if not decision.allowed:
            raise CapabilityDenied(decision.reason)
        def reconcile_locked():
            with self.store.transaction() as tx:
                if pending['kind'] == 'watch':
                    tx.conn.execute('SELECT id FROM pa_schedule.schedules WHERE owner=%s AND id=%s FOR UPDATE', (owner, pending['payload']['schedule_id']))
                    tx.conn.execute('SELECT id FROM pa_schedule.notifications WHERE owner=%s AND id=%s FOR UPDATE', (owner, pending['source_ref']))
                row = tx.conn.execute('SELECT * FROM pa_delivery.attempts WHERE owner=%s AND id=%s FOR UPDATE', (owner, delivery_id)).fetchone()
                if row['status'] != 'unknown':
                    return
                observation = adapter(row)
                if observation is None:
                    return
                if (type(observation) is not ReconciliationObservation or observation.attempt_ref != row['attempt_ref']
                    or observation.destination_ref != row['destination_ref'] or observation.content_digest != row['digest']
                    or observation.outcome not in {'delivered', 'not_delivered'} or not isinstance(observation.evidence_ref, str)
                    or not 0 < len(observation.evidence_ref) <= 256 or not isinstance(observation.provider_receipt, str)
                    or len(observation.provider_receipt) > 256 or (observation.outcome == 'delivered' and not observation.provider_receipt)):
                    raise CapabilityDenied('reconciliation evidence does not bind the actual attempt')
                status = 'sent' if observation.outcome == 'delivered' else 'not_sent'
                tx.conn.execute('UPDATE pa_delivery.attempts SET status=%s,provider_receipt=%s,reason=%s WHERE owner=%s AND id=%s',
                    (status, observation.provider_receipt, 'reconciled:' + observation.evidence_ref[:256], owner, delivery_id))
                if row['kind'] == 'watch':
                    tx.conn.execute('UPDATE pa_schedule.notifications SET status=%s WHERE owner=%s AND id=%s', (status, owner, row['source_ref']))
        self.registry.execute_reserved((decision.reservation,), reconcile_locked)
        return self.attempt(owner=owner, delivery_id=delivery_id)

    def execute_confirmed_action(self, action, *, request, executor, store):
        from prm.storage.actions import DurableActionStore
        if type(store) is not DurableActionStore or store.store.target != self.store.target:
            raise StorageError('shared durable action ledger required')
        if request.authorization is None or request.authorization.reservation is None or request.authorization.reservation._registry is not self.registry:
            raise CapabilityDenied('shared final policy required')
        return store.execute(action, request=request, executor=executor)

    def reconcile_confirmed_action(self, *, store, idempotency_key, adapter, upper_bound):
        from prm.storage.actions import DurableActionStore, _proposal, _receipt, _encode_receipt
        if type(store) is not DurableActionStore or store.store.target != self.store.target:
            raise StorageError('shared durable action ledger required')
        receipt = store.get(idempotency_key)
        if receipt is None:
            raise StorageError('action attempt unavailable')
        if receipt.status != 'unknown' or adapter is None:
            return receipt
        with self.store.transaction() as tx:
            row = tx.conn.execute('SELECT payload FROM pa_actions.proposals WHERE owner=%s AND ref=%s', (store.owner_ref, receipt.proposal_ref)).fetchone()
            proposal = _proposal(row['payload'])
        request = AuthorizationRequest(owner_ref=store.owner_ref, connection_ref=proposal.connection_ref,
            capability='assistant.action_reconciliation', resource_ref=proposal.resource_ref, operation='read',
            data_class='private_connector_metadata', provider_ref=proposal.provider_id, purpose='action.reconcile',
            operation_ref='actionreconcile_' + uuid.uuid4().hex)
        decision = self.registry.authorize_and_reserve(request, upper_bound=upper_bound)
        if not decision.allowed:
            raise CapabilityDenied(decision.reason)
        def reconcile_locked():
            with self.store.transaction() as tx:
                tx.conn.execute('SELECT ref FROM pa_actions.proposals WHERE owner=%s AND ref=%s FOR UPDATE', (store.owner_ref, receipt.proposal_ref))
                row = tx.conn.execute('SELECT receipt FROM pa_actions.attempts WHERE owner=%s AND key=%s FOR UPDATE', (store.owner_ref, idempotency_key)).fetchone()
                current = _receipt(row['receipt'])
                if current.status != 'unknown':
                    return
                evidence = adapter(current, proposal)
                if evidence is None:
                    return
                if (type(evidence) is not ReconciliationObservation or evidence.attempt_ref != current.idempotency_key
                    or evidence.destination_ref != proposal.resource_ref or evidence.content_digest != current.content_digest
                    or evidence.outcome not in {'delivered', 'not_delivered'} or not isinstance(evidence.evidence_ref, str)
                    or not 0 < len(evidence.evidence_ref) <= 256 or not isinstance(evidence.provider_receipt, str)
                    or len(evidence.provider_receipt) > 256 or (evidence.outcome == 'delivered' and not evidence.provider_receipt)):
                    raise CapabilityDenied('action reconciliation evidence scope differs')
                resolved = replace(current, status='succeeded' if evidence.outcome == 'delivered' else 'failed_known',
                    provider_operation_ref=evidence.provider_receipt, error_code='' if evidence.outcome == 'delivered' else 'provider_not_delivered', reconciled=True)
                tx.conn.execute('UPDATE pa_actions.attempts SET receipt=%s WHERE owner=%s AND key=%s',
                    (Jsonb(_encode_receipt(resolved)), store.owner_ref, idempotency_key))
        self.registry.execute_reserved((decision.reservation,), reconcile_locked)
        return store.get(idempotency_key)

    def describe(self, *, owner, delivery_id):
        attempt = self.attempt(owner=owner, delivery_id=delivery_id)
        if attempt is None:
            return 'Попытка доставки не найдена.'
        return {'unknown': 'Исход доставки неизвестен. Повтор заблокирован; нужна сверка с провайдером.',
                'sent': 'Доставка подтверждена провайдером.', 'not_sent': 'Провайдер подтвердил отсутствие доставки. Автоматического повтора нет.'}[attempt['status']]
