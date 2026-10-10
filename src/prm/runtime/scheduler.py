"""Explicit PostgreSQL Watch scheduler and bounded collection worker."""
from __future__ import annotations

from dataclasses import dataclass, replace, asdict
from datetime import datetime, timedelta, timezone
import hashlib
import uuid
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb
from prm.capabilities import AuthorizationRequest, CapabilityDenied
from prm.storage.jobs import JobQueue
from prm.storage.policy import DurableCapabilityRegistry
from prm.storage.postgres import PostgresStore, StorageError, StateConflict, _canonical
from prm.watch_jobs import (WatchSubscription, WatchNotification, watch_owner_ref_from_authenticated_private_tuple,
    _subscription_payload, _subscription_from_payload, _notification_payload, _subscription_effect,
    _stage_matches_trigger, _deadline_stage_due_at, _in_quiet_hours)

DDL = (
    'CREATE SCHEMA pa_schedule',
    'CREATE TABLE pa_schedule.meta(version integer PRIMARY KEY,checksum text NOT NULL)',
    '''CREATE TABLE pa_schedule.previews(owner text NOT NULL,id text NOT NULL,payload jsonb NOT NULL,
       digest text NOT NULL,expires timestamptz NOT NULL,consumed boolean NOT NULL DEFAULT false,PRIMARY KEY(owner,id))''',
    '''CREATE TABLE pa_schedule.schedules(owner text NOT NULL,id text NOT NULL,revision bigint NOT NULL,
       payload jsonb NOT NULL,input_ref text NOT NULL,input_version bigint NOT NULL,input_digest text NOT NULL,
       interval_seconds integer NOT NULL,next_due timestamptz NOT NULL,generation bigint NOT NULL DEFAULT 0,
       token text,lease_until timestamptz,last_tick timestamptz,last_reason text NOT NULL DEFAULT '',PRIMARY KEY(owner,id))''',
    '''CREATE TABLE pa_schedule.occurrences(owner text NOT NULL,schedule_id text NOT NULL,revision bigint NOT NULL,
       due_at timestamptz NOT NULL,job_id text NOT NULL,PRIMARY KEY(owner,schedule_id,revision,due_at))''',
    '''CREATE TABLE pa_schedule.notifications(owner text NOT NULL,id text NOT NULL,schedule_id text NOT NULL,
       revision bigint NOT NULL,subject_ref text NOT NULL,event_ref text NOT NULL,fingerprint text NOT NULL,
       payload jsonb NOT NULL,due_at timestamptz NOT NULL,status text NOT NULL,PRIMARY KEY(owner,id))''',
    '''CREATE TABLE pa_schedule.baselines(owner text NOT NULL,event_ref text NOT NULL,fingerprint text NOT NULL,
       PRIMARY KEY(owner,event_ref))''',
    '''CREATE TABLE pa_schedule.subjects(owner text NOT NULL,schedule_id text NOT NULL,subject_ref text NOT NULL,
       state text NOT NULL,PRIMARY KEY(owner,schedule_id,subject_ref))''',
    'GRANT USAGE ON SCHEMA pa_schedule TO pa_test_app',
    'GRANT SELECT ON pa_schedule.meta TO pa_test_app',
    'GRANT SELECT,INSERT,UPDATE ON pa_schedule.previews,pa_schedule.schedules,pa_schedule.occurrences,pa_schedule.notifications,pa_schedule.baselines,pa_schedule.subjects TO pa_test_app',
)
CHECKSUM = hashlib.sha256('\n'.join(DDL).encode()).hexdigest()


def install_schedules(target):
    if target.user != 'pa_test_migrator':
        raise StorageError('dedicated synthetic migrator required')
    with PostgresStore(target).transaction() as tx:
        tx.conn.execute('SELECT pg_advisory_xact_lock(%s)', (87291008,))
        if tx.conn.execute("SELECT to_regclass('pa_schedule.meta') AS meta").fetchone()['meta'] is None:
            for statement in DDL:
                tx.conn.execute(statement)
            tx.conn.execute('INSERT INTO pa_schedule.meta VALUES(1,%s)', (CHECKSUM,))
        else:
            _check(tx.conn)


def _check(conn):
    if conn.execute('SELECT version,checksum FROM pa_schedule.meta').fetchall() != [{'version': 1, 'checksum': CHECKSUM}]:
        raise StorageError('unsupported schedule schema')


def _time(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise StorageError('aware fixture clock required')
    return value.astimezone(timezone.utc)


def next_due(subscription, after, interval_seconds):
    """First future civil-time slot. A gap rolls forward; a fold runs once."""
    after = _time(after)
    if subscription.frequency == 'immediate':
        return after + timedelta(seconds=interval_seconds)
    zone = ZoneInfo(subscription.timezone_name)
    local = after.astimezone(zone)
    hour, minute = map(int, subscription.delivery_time.split(':'))
    for offset in range(9):
        day = local.date() + timedelta(days=offset)
        if subscription.frequency == 'weekly' and day.weekday() != subscription.delivery_weekday:
            continue
        candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone, fold=0).astimezone(timezone.utc)
        if candidate > after:
            return candidate
    raise StorageError('future schedule slot unavailable')


@dataclass(frozen=True)
class ScheduleLease:
    owner: str
    schedule_id: str
    revision: int
    generation: int
    token: str


class WatchScheduler:
    def __init__(self, queue: JobQueue, *, clock=None,source_bindings=None):
        self.queue, self.clock = queue, clock
        self.source_bindings=dict(source_bindings or {})
    def collection_request(self,subscription,source,*,operation_ref=None):
        request=collection_request(subscription,source,operation_ref=operation_ref)
        binding=self.source_bindings.get(source)
        if binding:
            return replace(request,connection_ref=binding['connection_ref'],provider_ref=binding['provider_ref'],data_class=binding.get('data_class',request.data_class))
        return request

    def _now(self, conn):
        return _time(self.clock()) if self.clock else conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']

    def _owner(self, chat_id, actor_id, owner_chat_id):
        owner = watch_owner_ref_from_authenticated_private_tuple(chat_id, actor_id, owner_chat_id)
        if owner is None:
            raise CapabilityDenied('authenticated private owner required')
        return owner

    def preview(self, subscription: WatchSubscription, *, chat_id, actor_id, owner_chat_id, interval_seconds=300):
        if type(subscription) is not WatchSubscription or self._owner(chat_id, actor_id, owner_chat_id) != subscription.owner_ref:
            raise CapabilityDenied('subscription owner differs')
        if type(interval_seconds) is not int or not 60 <= interval_seconds <= 86400:
            raise StorageError('bounded polling interval required')
        payload = {'subscription': _subscription_payload(subscription), 'interval_seconds': interval_seconds}
        _, digest = _canonical(payload)
        ref = 'watchconfirm_' + uuid.uuid4().hex
        with self.queue.store.transaction() as tx:
            _check(tx.conn)
            now = self._now(tx.conn)
            if subscription.expires_at <= now:
                raise StorageError('subscription already expired')
            tx.conn.execute('INSERT INTO pa_schedule.previews(owner,id,payload,digest,expires) VALUES(%s,%s,%s,%s,%s)',
                            (subscription.owner_ref, ref, Jsonb(payload), digest, now + timedelta(minutes=10)))
        return ref

    def confirm(self, preview_ref, *, chat_id, actor_id, owner_chat_id):
        owner = self._owner(chat_id, actor_id, owner_chat_id)
        with self.queue.store.transaction() as tx:
            conn = tx.conn; _check(conn)
            row = conn.execute('SELECT * FROM pa_schedule.previews WHERE owner=%s AND id=%s FOR UPDATE', (owner, preview_ref)).fetchone()
            now = self._now(conn)
            if row is None or row['consumed'] or row['expires'] <= now or _canonical(row['payload'])[1] != row['digest']:
                raise StateConflict('preview unavailable, changed or consumed')
            subscription = _subscription_from_payload(row['payload']['subscription'])
            # Serialize first creation as well as revisions.
            lock = int.from_bytes(hashlib.sha256((owner + subscription.subscription_id).encode()).digest()[:8], 'big') % (2**63)
            conn.execute('SELECT pg_advisory_xact_lock(%s)', (lock,))
            prior = conn.execute('SELECT revision FROM pa_schedule.schedules WHERE owner=%s AND id=%s FOR UPDATE',
                                 (owner, subscription.subscription_id)).fetchone()
            if subscription.owner_ref != owner or subscription.expires_at <= now or subscription.consent_revision != (prior['revision'] + 1 if prior else 1):
                raise StateConflict('subscription revision or expiry changed')
            ref = 'schedule_' + hashlib.sha256(subscription.subscription_id.encode()).hexdigest()[:32]
            item = tx.put(owner, 'conversation', ref, row['payload']['subscription'], expected_version=prior['revision'] if prior else 0)
            interval = row['payload']['interval_seconds']
            due = now if subscription.frequency == 'immediate' else next_due(subscription, now, interval)
            conn.execute('''INSERT INTO pa_schedule.schedules(owner,id,revision,payload,input_ref,input_version,input_digest,interval_seconds,next_due)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(owner,id) DO UPDATE SET
                revision=excluded.revision,payload=excluded.payload,input_ref=excluded.input_ref,input_version=excluded.input_version,
                input_digest=excluded.input_digest,interval_seconds=excluded.interval_seconds,next_due=excluded.next_due,
                token=NULL,lease_until=NULL,last_reason='revised' ''',
                (owner, subscription.subscription_id, subscription.consent_revision, Jsonb(row['payload']['subscription']), item.object_id,
                 item.version, item.digest, interval, due))
            conn.execute("UPDATE pa_schedule.notifications SET status='cancelled' WHERE owner=%s AND schedule_id=%s AND status='queued'",
                         (owner, subscription.subscription_id))
            conn.execute('UPDATE pa_schedule.previews SET consumed=true WHERE owner=%s AND id=%s', (owner, preview_ref))
        return subscription

    def claim_due(self, *, owner):
        with self.queue.store.transaction() as tx:
            conn = tx.conn; _check(conn); now = self._now(conn)
            row = conn.execute('''SELECT * FROM pa_schedule.schedules WHERE owner=%s AND next_due<=%s
                AND (token IS NULL OR lease_until<=%s) ORDER BY next_due,id FOR UPDATE SKIP LOCKED LIMIT 1''', (owner, now, now)).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            conn.execute('UPDATE pa_schedule.schedules SET generation=generation+1,token=%s,lease_until=%s WHERE owner=%s AND id=%s',
                         (token, now + timedelta(seconds=10), owner, row['id']))
            return ScheduleLease(owner, row['id'], row['revision'], row['generation'] + 1, token)

    def _fenced(self, conn, lease):
        now = self._now(conn)
        row = conn.execute('''SELECT * FROM pa_schedule.schedules WHERE owner=%s AND id=%s AND revision=%s
            AND generation=%s AND token=%s AND lease_until>%s FOR UPDATE''',
            (lease.owner, lease.schedule_id, lease.revision, lease.generation, lease.token, now)).fetchone()
        if row is None:
            raise StateConflict('scheduler lease stale or revised')
        return row, now

    def advance(self, lease, *, registry):
        if type(registry) is not DurableCapabilityRegistry or registry.store.target != self.queue.store.target:
            raise StorageError('shared durable policy required')
        with self.queue.store.transaction() as tx:
            conn = tx.conn; _check(conn); row, now = self._fenced(conn, lease)
            sub = _subscription_from_payload(row['payload'])
            reason = _subscription_effect(sub, now=now)
            job = None
            if reason == 'active':
                for source in sub.source_refs:
                    request = self.collection_request(sub, source)
                    if not registry.authorize(request).allowed:
                        reason = 'collection_grant_denied'
                        break
            if reason == 'active':
                payload = {'schema_version': 1, 'input_namespace': 'conversation', 'input_ref': row['input_ref'],
                    'input_version': row['input_version'], 'input_digest': row['input_digest'], 'connection_ref': None,
                    'resource_ref': sub.subscription_id, 'purpose': 'watch.collection', 'consent_revision': sub.consent_revision}
                # Use DB time for the queue deadline even with a fixture clock.
                dbnow = conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
                key = 'watch_' + hashlib.sha256((sub.subscription_id + ':' + str(sub.consent_revision) + ':' + row['next_due'].isoformat()).encode()).hexdigest()[:40]
                job = self.queue.enqueue_in(tx, owner=lease.owner, idempotency_key=key, payload=payload,
                    deadline=dbnow + timedelta(minutes=10), kind='compute.watch')
                conn.execute('INSERT INTO pa_schedule.occurrences VALUES(%s,%s,%s,%s,%s)',
                             (lease.owner, sub.subscription_id, sub.consent_revision, row['next_due'], job))
            # Compute from NOW, never enqueue every missed historical slot.
            due = next_due(sub, now, row['interval_seconds'])
            conn.execute('UPDATE pa_schedule.schedules SET next_due=%s,token=NULL,lease_until=NULL,last_tick=%s,last_reason=%s WHERE owner=%s AND id=%s',
                         (due, now, reason, lease.owner, sub.subscription_id))
        return job

    def tick(self, *, owner, registry):
        lease = self.claim_due(owner=owner)
        return self.advance(lease, registry=registry) if lease else None

    def feedback(self, subscription_id, action, *, chat_id, actor_id, owner_chat_id, until=None):
        owner = self._owner(chat_id, actor_id, owner_chat_id)
        if action not in {'pause', 'unsubscribe', 'snooze', 'done', 'resume'}:
            raise StorageError('unsupported Watch feedback')
        with self.queue.store.transaction() as tx:
            _check(tx.conn)
            row = tx.conn.execute('SELECT * FROM pa_schedule.schedules WHERE owner=%s AND id=%s FOR UPDATE', (owner, subscription_id)).fetchone()
            if row is None:
                raise StorageError('subscription unavailable')
            sub = _subscription_from_payload(row['payload']); now = self._now(tx.conn)
            if action == 'snooze' and (until is None or not now < _time(until) <= min(sub.expires_at, now + timedelta(days=30))):
                raise StorageError('bounded snooze required')
            if sub.lifecycle in {'cancelled', 'completed'}:
                raise StateConflict('terminal subscription requires a new confirmed revision')
            sub = replace(sub, lifecycle={'pause': 'paused', 'unsubscribe': 'cancelled', 'done': 'completed'}.get(action, 'active'),
                          paused_until=until if action == 'snooze' else None)
            tx.conn.execute('UPDATE pa_schedule.schedules SET payload=%s,token=NULL,lease_until=NULL,next_due=%s,last_reason=%s WHERE owner=%s AND id=%s',
                (Jsonb(_subscription_payload(sub)), until if action == 'snooze' else now, action, owner, subscription_id))
            if action != 'resume':
                tx.conn.execute("UPDATE pa_schedule.notifications SET status='cancelled' WHERE owner=%s AND schedule_id=%s AND status='queued'", (owner, subscription_id))

    def status(self, *, owner, subscription_id):
        with self.queue.store.transaction() as tx:
            _check(tx.conn)
            row = tx.conn.execute('SELECT payload,next_due,last_tick,last_reason FROM pa_schedule.schedules WHERE owner=%s AND id=%s', (owner, subscription_id)).fetchone()
            if row is None:
                return None
            now = self._now(tx.conn)
            occurrence=tx.conn.execute('SELECT j.status,j.result_ref FROM pa_schedule.occurrences o JOIN pa_jobs.jobs j ON j.owner=o.owner AND j.id=o.job_id WHERE o.owner=%s AND o.schedule_id=%s ORDER BY o.due_at DESC LIMIT 1',
                (owner,subscription_id)).fetchone()
            last=tx.get(owner,'result',occurrence['result_ref']) if occurrence and occurrence['result_ref'] else None
            return {'intent_saved': True, 'scheduler_observed_recently': row['last_tick'] is not None and now - row['last_tick'] < timedelta(minutes=10),
                    'lifecycle': _subscription_from_payload(row['payload']).lifecycle, 'last_reason': row['last_reason'], 'next_due_at': row['next_due'],
                    'last_collection':last.payload if last else None}

    def complete_subject(self, subscription_id, subject_ref, *, chat_id, actor_id, owner_chat_id):
        owner = self._owner(chat_id, actor_id, owner_chat_id)
        with self.queue.store.transaction() as tx:
            self.complete_subject_in(tx,owner=owner,subscription_id=subscription_id,subject_ref=subject_ref)

    @staticmethod
    def complete_subject_in(tx,*,owner,subscription_id,subject_ref):
        _check(tx.conn)
        row=tx.conn.execute('SELECT id FROM pa_schedule.schedules WHERE owner=%s AND id=%s FOR UPDATE',(owner,subscription_id)).fetchone()
        if row is None:raise StorageError('subscription unavailable')
        tx.conn.execute("INSERT INTO pa_schedule.subjects VALUES(%s,%s,%s,'completed') ON CONFLICT(owner,schedule_id,subject_ref) DO UPDATE SET state='completed'",(owner,subscription_id,subject_ref))
        tx.conn.execute("UPDATE pa_schedule.notifications SET status='cancelled' WHERE owner=%s AND schedule_id=%s AND subject_ref=%s AND status='queued'",(owner,subscription_id,subject_ref))


def collection_request(subscription, source, *, operation_ref=None):
    return AuthorizationRequest(owner_ref=subscription.owner_ref, connection_ref=None, capability='assistant.watch_collection',
        resource_ref=source, operation='read', data_class='private_connector_metadata', provider_ref='provider_watch_source',
        purpose='watch.collection', operation_ref=operation_ref)


class WatchCollectionWorker:
    def __init__(self, scheduler, *, owner, registry, collector, upper_bound):
        if type(registry) is not DurableCapabilityRegistry or registry.store.target != scheduler.queue.store.target:
            raise StorageError('shared durable registry required')
        self.scheduler, self.owner, self.registry = scheduler, owner, registry
        self.collector, self.upper_bound = collector, upper_bound

    def run_once(self):
        queue = self.scheduler.queue
        lease = queue.claim(owner=self.owner, kinds=('compute.watch',), lease_seconds=300)
        if lease is None:
            return None
        # Reserve outside the subscription lock, then acquire policy before
        # subscription, matching the future shared effect executor lock order.
        item = queue.store.get(lease.owner, 'conversation', lease.payload['input_ref'], version=lease.payload['input_version'])
        sub = _subscription_from_payload(item.payload)
        notifications = [];source_scopes={}
        for index, source in enumerate(sub.source_refs):
            queue.checkpoint(lease, {'stage': 'collecting', 'source_number': index})
            decision = self.registry.authorize_and_reserve(self.scheduler.collection_request(sub, source,
                operation_ref=f'watchread_{lease.job_id}_{lease.generation}_{index}'), upper_bound=self.upper_bound)
            if not decision.allowed:
                return queue.complete(lease, {'status': 'collection_denied', 'notifications': 0})
            def transport():
                with queue.store.transaction() as tx:
                    # Guard current lifecycle and job fence THROUGH bounded I/O.
                    row = tx.conn.execute('SELECT * FROM pa_schedule.schedules WHERE owner=%s AND id=%s FOR UPDATE',
                                          (lease.owner, sub.subscription_id)).fetchone()
                    current = _subscription_from_payload(row['payload'])
                    if row['revision'] != sub.consent_revision or _subscription_effect(current, now=self.scheduler._now(tx.conn)) != 'active':
                        raise CapabilityDenied('subscription paused, revised or expired')
                    queue._fenced(tx, lease)
                    result = self.collector(source, current)
                    if tx.conn.closed:
                        raise StorageError('collection scope connection lost')
                    return result
            collected = self.registry.execute_reserved((decision.reservation,), transport)
            source_scopes[source]=asdict(replace(decision.reservation._request,operation_ref=None))
            if not isinstance(collected, (tuple, list)) or len(collected) > 32:
                raise StorageError('bounded notification batch required')
            for notification in collected:
                if (type(notification) is not WatchNotification or notification.owner_ref != sub.owner_ref
                    or notification.subscription_id != sub.subscription_id or notification.source_ref != source):
                    raise StorageError('collector notification scope differs')
                notifications.append(notification)
        with queue.store.transaction() as tx:
            conn = tx.conn
            row = conn.execute('SELECT * FROM pa_schedule.schedules WHERE owner=%s AND id=%s FOR UPDATE', (lease.owner, sub.subscription_id)).fetchone()
            current = _subscription_from_payload(row['payload']); now = self.scheduler._now(conn)
            if row['revision'] != sub.consent_revision or _subscription_effect(current, now=now) != 'active':
                raise StateConflict('subscription changed after collection')
            queue._fenced(tx, lease)
            count = 0
            for note in notifications:
                if not _stage_matches_trigger(note.delivery_stage, current.trigger):
                    raise StorageError('notification trigger differs')
                subject = conn.execute('SELECT state FROM pa_schedule.subjects WHERE owner=%s AND schedule_id=%s AND subject_ref=%s',
                                       (lease.owner, sub.subscription_id, note.subject_ref)).fetchone()
                if subject and subject['state'] != 'active':
                    continue
                baseline = conn.execute('SELECT fingerprint FROM pa_schedule.baselines WHERE owner=%s AND event_ref=%s FOR UPDATE',
                                        (lease.owner, note.event_identity)).fetchone()
                if baseline and baseline['fingerprint'] == note.evidence_fingerprint:
                    continue
                key = note.idempotency_key(previous_evidence_fingerprint=baseline['fingerprint'] if baseline else None)
                conn.execute("UPDATE pa_schedule.notifications SET status='cancelled' WHERE owner=%s AND schedule_id=%s AND subject_ref=%s AND fingerprint<>%s AND status='queued'",
                             (lease.owner, sub.subscription_id, note.subject_ref, note.evidence_fingerprint))
                due = _deadline_stage_due_at(note, note.delivery_stage) if note.delivery_stage.startswith('deadline:') else note.due_at
                payload={**_notification_payload(note),'source_scopes':[source_scopes[note.source_ref]]}
                conn.execute("INSERT INTO pa_schedule.notifications VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued') ON CONFLICT DO NOTHING",
                    (lease.owner, key, sub.subscription_id, sub.consent_revision, note.subject_ref, note.event_identity,
                     note.evidence_fingerprint, Jsonb(payload), due))
                conn.execute('INSERT INTO pa_schedule.baselines VALUES(%s,%s,%s) ON CONFLICT(owner,event_ref) DO UPDATE SET fingerprint=excluded.fingerprint',
                             (lease.owner, note.event_identity, note.evidence_fingerprint))
                count += 1
            ref = 'result_' + lease.job_id
            tx.put(lease.owner, 'result', ref, {'status': 'collected', 'notifications': count}, expected_version=0)
            conn.execute("UPDATE pa_jobs.jobs SET status='completed',result_ref=%s,token=NULL,lease_until=NULL WHERE owner=%s AND id=%s", (ref, lease.owner, lease.job_id))
        return ref

    def eligible_notifications(self):
        """Candidates only: fresh delivery grant and final attempt are PAI-09."""
        with self.scheduler.queue.store.transaction() as tx:
            conn = tx.conn; _check(conn); now = self.scheduler._now(conn)
            rows = conn.execute("SELECT * FROM pa_schedule.notifications WHERE owner=%s AND status='queued' AND due_at<=%s ORDER BY due_at,id", (self.owner, now)).fetchall()
            output = []
            per_schedule = {}
            for row in rows:
                subrow = conn.execute('SELECT payload,revision FROM pa_schedule.schedules WHERE owner=%s AND id=%s', (self.owner, row['schedule_id'])).fetchone()
                sub = _subscription_from_payload(subrow['payload'])
                if subrow['revision'] != row['revision'] or _subscription_effect(sub, now=now) != 'active':
                    continue
                local = now.astimezone(ZoneInfo(sub.timezone_name))
                if _in_quiet_hours(sub, local=local) and not (row['payload']['urgent'] and sub.allow_urgent_during_quiet_hours):
                    continue
                used = per_schedule.get(sub.subscription_id, 0)
                if used >= sub.daily_cap:
                    continue
                output.append(row); per_schedule[sub.subscription_id] = used + 1
            return output
