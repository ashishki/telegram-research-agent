"""Real isolated PostgreSQL scheduler, policy, leases and Watch collection."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from itertools import count
import multiprocessing

import pytest

from prm.capabilities import CapabilityGrant, ProviderPolicy, CapabilityDenied
from prm.storage.postgres import migrate, SyntheticTarget, StorageError, StateConflict
from prm.storage.policy import DurableCapabilityRegistry, install_policy
from prm.storage.jobs import JobQueue, install_jobs
from prm.storage.testing import PostgresSandbox
from prm.runtime.scheduler import WatchScheduler, WatchCollectionWorker, install_schedules, next_due
from prm.watch_jobs import WatchSubscription, WatchNotification, watch_owner_ref_from_authenticated_private_tuple


@pytest.fixture(scope='module')
def sandbox():
    with PostgresSandbox() as value:
        migrate(value.migrator, expected_version=0)
        install_jobs(value.migrator); install_policy(value.migrator); install_schedules(value.migrator)
        yield value


SEQUENCE = count(100)


@pytest.fixture
def case(sandbox):
    chat = str(next(SEQUENCE))
    owner = watch_owner_ref_from_authenticated_private_tuple(chat, chat, chat)
    now = datetime.now(timezone.utc)
    clock = [now]
    scheduler = WatchScheduler(JobQueue(sandbox.app), clock=lambda: clock[0])
    registry = DurableCapabilityRegistry(sandbox.app, budget_refs=('request_' + chat, 'job_' + chat, 'day_' + chat, 'month_' + chat), job_budget=True)
    grant = CapabilityGrant(grant_id='grant_watch_' + chat, owner_ref=owner, connection_ref=None,
        capability='assistant.watch_collection', resource_refs=('source_synthetic',), operations=('read',),
        data_classes=('private_connector_metadata',), purpose='watch.collection',
        provider_policy=ProviderPolicy(('provider_watch_source',), maximum_request_count=100),
        issued_at=now - timedelta(days=1), expires_at=now + timedelta(days=30), revision=1)
    registry.register_grant(grant)
    for kind, ref in zip(('request', 'job', 'day', 'month'), registry.budget_refs):
        registry.configure_window(owner=owner, ref=ref, kind=kind, capacity=100, starts=now - timedelta(days=1), ends=now + timedelta(days=2))
    sub = WatchSubscription(subscription_id='watch_synthetic_' + chat, owner_ref=owner, consent_revision=1,
        source_refs=('source_synthetic',), destination_ref='destination_private', trigger='meaningful_change',
        timezone_name='Europe/Berlin', expires_at=now + timedelta(days=30), daily_cap=2)
    return scheduler, registry, sub, clock, {'chat_id': chat, 'actor_id': chat, 'owner_chat_id': chat}


def confirm(case, subscription=None):
    scheduler, registry, sub, clock, actor = case
    ref = scheduler.preview(subscription or sub, **actor)
    return scheduler.confirm(ref, **actor)


def _tick_process(config, owner, budgets, moment, barrier, outcomes):
    queue = JobQueue(SyntheticTarget.from_mapping(config))
    scheduler = WatchScheduler(queue, clock=lambda: datetime.fromisoformat(moment))
    registry = DurableCapabilityRegistry(queue.store.target, budget_refs=tuple(budgets), job_budget=True)
    barrier.wait(timeout=10)
    outcomes.put(scheduler.tick(owner=owner, registry=registry))


def note(sub, now, **changes):
    values = dict(subscription_id=sub.subscription_id, owner_ref=sub.owner_ref, subject_ref='subject_synthetic',
        change_version='version_1', delivery_stage='change', title='Synthetic deadline update',
        change_summary='Deadline moved to Wednesday.', relevance_reason='Selected synthetic programme.',
        source_ref='source_synthetic', due_at=now)
    values.update(changes)
    return WatchNotification(**values)


def test_two_schedulers_and_repeated_tick_enqueue_once(case, sandbox):
    scheduler, registry, sub, clock, actor = case
    confirm(case)
    ctx = multiprocessing.get_context('spawn'); barrier = ctx.Barrier(2); outcomes = ctx.Queue()
    workers = [ctx.Process(target=_tick_process, args=(asdict(sandbox.app), sub.owner_ref, registry.budget_refs,
               clock[0].isoformat(), barrier, outcomes)) for _ in range(2)]
    for worker in workers: worker.start()
    results = [outcomes.get(timeout=20) for _ in workers]
    for worker in workers:
        worker.join(timeout=20); assert worker.exitcode == 0
    assert sum(value is not None for value in results) == 1
    assert scheduler.tick(owner=sub.owner_ref, registry=registry) is None
    with scheduler.queue.store.transaction() as tx:
        assert tx.conn.execute('SELECT count(*) AS n FROM pa_schedule.occurrences WHERE owner=%s', (sub.owner_ref,)).fetchone()['n'] == 1


def test_exact_owner_preview_expiry_and_single_use(case):
    scheduler, registry, sub, clock, actor = case
    with pytest.raises(CapabilityDenied):
        scheduler.preview(sub, **dict(actor, actor_id='999'))
    ref = scheduler.preview(sub, **actor)
    scheduler.confirm(ref, **actor)
    with pytest.raises(StateConflict): scheduler.confirm(ref, **actor)
    ref = scheduler.preview(replace(sub, consent_revision=2), **actor)
    clock[0] += timedelta(minutes=11)
    with pytest.raises(StateConflict): scheduler.confirm(ref, **actor)


def test_downtime_coalesces_and_scheduler_lease_recovers(case):
    scheduler, registry, sub, clock, actor = case
    confirm(case)
    abandoned = scheduler.claim_due(owner=sub.owner_ref)
    clock[0] += timedelta(days=7)
    recovered = scheduler.claim_due(owner=sub.owner_ref)
    assert recovered.generation == abandoned.generation + 1
    with pytest.raises(StateConflict): scheduler.advance(abandoned, registry=registry)
    assert scheduler.advance(recovered, registry=registry)
    assert scheduler.tick(owner=sub.owner_ref, registry=registry) is None
    state = scheduler.status(owner=sub.owner_ref, subscription_id=sub.subscription_id)
    assert state['next_due_at'] == clock[0] + timedelta(seconds=300)


def test_daily_wall_schedule_spring_gap_and_fall_fold(case):
    sub = replace(case[2], trigger='digest', frequency='daily', delivery_time='02:30', timezone_name='Europe/Berlin')
    spring = datetime(2026, 3, 29, 0, 0, tzinfo=timezone.utc)
    due = next_due(sub, spring, 300)
    assert due == datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc)
    first_fold = next_due(sub, datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc), 300)
    assert first_fold == datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)
    assert next_due(sub, first_fold, 300).date().isoformat() == '2026-10-26'


def test_pause_snooze_done_unsubscribe_and_status_are_truthful(case):
    scheduler, registry, sub, clock, actor = case
    confirm(case)
    state = scheduler.status(owner=sub.owner_ref, subscription_id=sub.subscription_id)
    assert state['intent_saved'] and not state['scheduler_observed_recently']
    scheduler.feedback(sub.subscription_id, 'pause', **actor)
    assert scheduler.tick(owner=sub.owner_ref, registry=registry) is None
    scheduler.feedback(sub.subscription_id, 'snooze', until=clock[0] + timedelta(hours=1), **actor)
    assert scheduler.tick(owner=sub.owner_ref, registry=registry) is None
    clock[0] += timedelta(hours=1)
    assert scheduler.tick(owner=sub.owner_ref, registry=registry)
    scheduler.feedback(sub.subscription_id, 'done', **actor)
    assert scheduler.tick(owner=sub.owner_ref, registry=registry) is None
    with pytest.raises(StateConflict): scheduler.feedback(sub.subscription_id, 'resume', **actor)
    assert scheduler.status(owner=sub.owner_ref, subscription_id=sub.subscription_id)['lifecycle'] == 'completed'
    revised = replace(sub, consent_revision=2)
    confirm(case, revised)
    scheduler.feedback(sub.subscription_id, 'unsubscribe', **actor)
    assert scheduler.tick(owner=sub.owner_ref, registry=registry) is None


def test_revocation_before_tick_and_after_enqueue_prevents_collection(case):
    scheduler, registry, sub, clock, actor = case
    confirm(case)
    job = scheduler.tick(owner=sub.owner_ref, registry=registry)
    registry.revoke_grant('grant_watch_' + actor['chat_id'], owner_ref=sub.owner_ref)
    calls = []
    worker = WatchCollectionWorker(scheduler, owner=sub.owner_ref, registry=registry,
        collector=lambda *args: calls.append(args), upper_bound=1)
    ref = worker.run_once()
    assert not calls and scheduler.queue.store.get(sub.owner_ref, 'result', ref).payload['status'] == 'collection_denied'
    clock[0] += timedelta(minutes=5)
    assert scheduler.tick(owner=sub.owner_ref, registry=registry) is None
    assert scheduler.status(owner=sub.owner_ref, subscription_id=sub.subscription_id)['last_reason'] == 'collection_grant_denied'


def test_pause_after_enqueue_guards_actual_adapter(case):
    scheduler, registry, sub, clock, actor = case
    confirm(case); scheduler.tick(owner=sub.owner_ref, registry=registry)
    scheduler.feedback(sub.subscription_id, 'pause', **actor)
    calls = []
    worker = WatchCollectionWorker(scheduler, owner=sub.owner_ref, registry=registry,
        collector=lambda *args: calls.append(args), upper_bound=1)
    with pytest.raises(CapabilityDenied): worker.run_once()
    assert not calls


def test_material_change_dedup_quiet_hours_and_caps(case):
    scheduler, registry, sub, clock, actor = case
    # Whole-day quiet interval at this fixture minute; collection remains read
    # scoped but no eligible delivery candidate is returned during quiet hours.
    local = clock[0].astimezone(__import__('zoneinfo').ZoneInfo(sub.timezone_name))
    start = local.replace(minute=0).strftime('%H:%M')
    end = (local + timedelta(hours=1)).replace(minute=0).strftime('%H:%M')
    sub = replace(sub, quiet_start=start, quiet_end=end)
    confirm(case, sub)
    batch = [note(sub, clock[0], subject_ref='subject_' + str(index)) for index in range(3)]
    worker = WatchCollectionWorker(scheduler, owner=sub.owner_ref, registry=registry,
        collector=lambda source, current: batch, upper_bound=1)
    scheduler.tick(owner=sub.owner_ref, registry=registry)
    assert worker.run_once()
    assert worker.eligible_notifications() == []
    clock[0] += timedelta(hours=2)
    assert len(worker.eligible_notifications()) == 2
    scheduler.tick(owner=sub.owner_ref, registry=registry)
    ref = worker.run_once()
    assert scheduler.queue.store.get(sub.owner_ref, 'result', ref).payload['notifications'] == 0


def test_source_deadline_recalculation_cancels_old_waiting_version(case):
    scheduler, registry, sub, clock, actor = case
    sub = replace(sub, trigger='deadline_reminder')
    confirm(case, sub)
    deadline = clock[0] + timedelta(days=2)
    batch = [note(sub, clock[0], delivery_stage='deadline:1d', source_deadline_at=deadline,
                  source_deadline_timezone='Europe/Berlin')]
    worker = WatchCollectionWorker(scheduler, owner=sub.owner_ref, registry=registry,
        collector=lambda source, current: batch, upper_bound=1)
    scheduler.tick(owner=sub.owner_ref, registry=registry); worker.run_once()
    batch[0] = replace(batch[0], source_deadline_at=deadline + timedelta(days=1), change_version='version_2')
    clock[0] += timedelta(minutes=5)
    scheduler.tick(owner=sub.owner_ref, registry=registry); worker.run_once()
    with scheduler.queue.store.transaction() as tx:
        rows = tx.conn.execute('SELECT status,due_at FROM pa_schedule.notifications WHERE owner=%s ORDER BY due_at', (sub.owner_ref,)).fetchall()
    assert [row['status'] for row in rows] == ['cancelled', 'queued']
    assert rows[1]['due_at'] == deadline


def test_revision_invalidates_scheduler_and_old_jobs(case):
    scheduler, registry, sub, clock, actor = case
    confirm(case)
    lease = scheduler.claim_due(owner=sub.owner_ref)
    confirm(case, replace(sub, consent_revision=2))
    with pytest.raises(StateConflict): scheduler.advance(lease, registry=registry)
    assert scheduler.tick(owner=sub.owner_ref, registry=registry)


def test_ingress_watch_controls_distinguish_intent_and_running_scheduler(case):
    from prm.runtime.ingress import TelegramJobIngress
    scheduler, registry, sub, clock, actor = case
    ref = scheduler.preview(sub, **actor)
    ingress = TelegramJobIngress(scheduler.queue, owner_ref=sub.owner_ref, owner_chat_id=actor['chat_id'], watch_scheduler=scheduler)
    def inbound(number, command):
        return {'update_id': number, 'message': {'text': command, 'chat': {'id': int(actor['chat_id']), 'type': 'private'}, 'from': {'id': int(actor['actor_id'])}}}
    assert 'Подписка сохранена' in ingress.receive(inbound(1, '/watchconfirm ' + ref)).text
    assert 'пока не подтверждена' in ingress.receive(inbound(2, '/watchstatus ' + sub.subscription_id)).text
    scheduler.tick(owner=sub.owner_ref, registry=registry)
    assert 'наблюдалась недавно' in ingress.receive(inbound(3, '/watchstatus ' + sub.subscription_id)).text
    ingress.receive(inbound(4, '/watchpause ' + sub.subscription_id))
    assert scheduler.status(owner=sub.owner_ref, subscription_id=sub.subscription_id)['lifecycle'] == 'paused'


def test_completed_subject_suppresses_future_notifications(case):
    scheduler, registry, sub, clock, actor = case
    confirm(case)
    scheduler.complete_subject(sub.subscription_id, 'subject_synthetic', **actor)
    scheduler.tick(owner=sub.owner_ref, registry=registry)
    worker = WatchCollectionWorker(scheduler, owner=sub.owner_ref, registry=registry,
        collector=lambda source, current: [note(sub, clock[0])], upper_bound=1)
    ref = worker.run_once()
    assert scheduler.queue.store.get(sub.owner_ref, 'result', ref).payload['notifications'] == 0


def test_foreground_grant_does_not_authorize_background_collection(case):
    scheduler, registry, sub, clock, actor = case
    registry.revoke_grant('grant_watch_' + actor['chat_id'], owner_ref=sub.owner_ref)
    registry.register_grant(CapabilityGrant(grant_id='grant_foreground_' + actor['chat_id'], owner_ref=sub.owner_ref,
        connection_ref=None, capability='archive.read', resource_refs=('source_synthetic',), operations=('read',),
        data_classes=('private_connector_metadata',), purpose='foreground.research',
        provider_policy=ProviderPolicy(('provider_watch_source',), maximum_request_count=100),
        issued_at=clock[0] - timedelta(days=1), expires_at=clock[0] + timedelta(days=30), revision=1))
    confirm(case)
    assert scheduler.tick(owner=sub.owner_ref, registry=registry) is None


def test_queue_failure_does_not_advance_schedule_or_lose_occurrence(case):
    scheduler, registry, sub, clock, actor = case
    scheduler.queue.admission_limit = 1
    confirm(case)
    first = scheduler.tick(owner=sub.owner_ref, registry=registry)
    clock[0] += timedelta(minutes=5)
    due = scheduler.status(owner=sub.owner_ref, subscription_id=sub.subscription_id)['next_due_at']
    with pytest.raises(StorageError, match='admission'):
        scheduler.tick(owner=sub.owner_ref, registry=registry)
    assert scheduler.status(owner=sub.owner_ref, subscription_id=sub.subscription_id)['next_due_at'] == due
    scheduler.queue.cancel(owner=sub.owner_ref, job_id=first)
    clock[0] += timedelta(seconds=11)
    assert scheduler.tick(owner=sub.owner_ref, registry=registry)
    with scheduler.queue.store.transaction() as tx:
        assert tx.conn.execute('SELECT count(*) AS n FROM pa_schedule.occurrences WHERE owner=%s', (sub.owner_ref,)).fetchone()['n'] == 2
