"""Real durable effect fences against a synthetic HTTP provider and races."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread, Event
from urllib.request import Request, urlopen

import pytest
from tests.pai_runtime_fixtures import pai

from tests.test_pai_scheduler import case, confirm, note
from prm.capabilities import CapabilityGrant, ProviderPolicy, CapabilityDenied
from prm.runtime.delivery import DeliveryExecutor, TransportReceipt, ReconciliationObservation, install_delivery
from prm.runtime.scheduler import install_schedules, WatchCollectionWorker
from prm.storage.jobs import install_jobs
from prm.storage.policy import install_policy
from prm.storage.postgres import migrate, StateConflict
from prm.storage.testing import PostgresSandbox


@pytest.fixture(scope='module')
def sandbox():
    with PostgresSandbox() as value:
        migrate(value.migrator, expected_version=0)
        install_jobs(value.migrator); install_policy(value.migrator); install_schedules(value.migrator); install_delivery(value.migrator)
        from prm.storage.actions import install_actions
        install_actions(value.migrator)
        yield value


def grants(case):
    scheduler, registry, sub, clock, actor = case
    for key, capability, operation, data_class, purpose in (
        ('answer', 'assistant.result_delivery', 'deliver', 'private_archive', 'answer.delivery'),
        ('watch', 'assistant.watch_delivery', 'deliver', 'model_generated', 'watch.delivery'),
        ('reconcile', 'assistant.delivery_reconciliation', 'read', 'private_connector_metadata', 'delivery.reconcile')):
        registry.register_grant(CapabilityGrant(grant_id='grant_' + key, owner_ref=sub.owner_ref, connection_ref=None,
            capability=capability, resource_refs=('destination_private',), operations=(operation,), data_classes=(data_class,),
            purpose=purpose, provider_policy=ProviderPolicy(('provider_telegram',), maximum_request_count=100),
            issued_at=datetime.now(timezone.utc) - timedelta(days=1), expires_at=datetime.now(timezone.utc) + timedelta(days=30), revision=1))


def completed(case):
    scheduler, registry, sub, clock, actor = case
    store = scheduler.queue.store
    item = store.put(sub.owner_ref, 'conversation', 'input_foreground', {'query': 'Synthetic question'}, expected_version=0)
    payload = dict(schema_version=1, input_namespace='conversation', input_ref=item.object_id,
        input_version=1, input_digest=item.digest, connection_ref=None, resource_ref='resource_foreground',
        purpose='local.assistant', consent_revision=1)
    job = scheduler.queue.enqueue(owner=sub.owner_ref, idempotency_key='foreground', payload=payload,
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5))
    lease = scheduler.queue.claim(owner=sub.owner_ref)
    scheduler.queue.complete(lease, {'text': 'Synthetic answer', 'request_ref': 'request_foreground'})
    return job


def pending_watch(case, *, total=1, cap=2):
    scheduler, registry, sub, clock, actor = case
    sub = replace(sub, daily_cap=cap)
    confirm(case, sub)
    scheduler.tick(owner=sub.owner_ref, registry=registry)
    worker = WatchCollectionWorker(scheduler, owner=sub.owner_ref, registry=registry, upper_bound=1,
        collector=lambda source, current: [note(sub, clock[0], subject_ref='subject_' + str(i)) for i in range(total)])
    worker.run_once()
    with scheduler.queue.store.transaction() as tx:
        return [row['id'] for row in tx.conn.execute('SELECT id FROM pa_schedule.notifications WHERE owner=%s ORDER BY id', (sub.owner_ref,)).fetchall()]


def test_fake_server_accepts_but_ack_is_lost_and_restart_never_resends(case):
    scheduler, registry, sub, clock, actor = case
    grants(case); job = completed(case); accepted = []
    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            accepted.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.close_connection = True  # accepted effect, lost response
    server = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    thread = Thread(target=server.serve_forever); thread.start()
    def sender(destination, text, attempt):
        data = json.dumps({'destination': destination, 'text': text, 'attempt': attempt}).encode()
        with urlopen(Request(f'http://127.0.0.1:{server.server_port}/send', data=data), timeout=2) as response:
            return TransportReceipt(response.read().decode())
    try:
        executor = DeliveryExecutor(scheduler.queue.store.target, registry=registry, sender=sender)
        first = executor.deliver_result(owner=sub.owner_ref, job_id=job, destination_ref='destination_private', upper_bound=1)
        assert first['status'] == 'unknown' and len(accepted) == 1
        restarted = DeliveryExecutor(scheduler.queue.store.target, registry=registry, sender=sender)
        assert restarted.deliver_result(owner=sub.owner_ref, job_id=job, destination_ref='destination_private', upper_bound=1)['attempt_ref'] == first['attempt_ref']
        assert len(accepted) == 1 and 'Повтор заблокирован' in restarted.describe(owner=sub.owner_ref, delivery_id=first['id'])
        assert restarted.reconcile(owner=sub.owner_ref, delivery_id=first['id'], adapter=None, upper_bound=1)['status'] == 'unknown'
        assert restarted.reconcile(owner=sub.owner_ref, delivery_id=first['id'], adapter=lambda pending: None, upper_bound=1)['status'] == 'unknown'
    finally:
        server.shutdown(); thread.join(timeout=5); server.server_close()


def test_precommitted_attempt_and_receipt_only_after_real_transport(case):
    scheduler, registry, sub, clock, actor = case
    grants(case); job = completed(case); calls = []
    def sender(destination, text, attempt):
        executor = DeliveryExecutor(scheduler.queue.store.target, registry=registry, sender=None)
        assert executor.attempt(owner=sub.owner_ref, delivery_id='answer_' + job)['status'] == 'unknown'
        calls.append(attempt)
        return TransportReceipt('provider_receipt_1')
    executor = DeliveryExecutor(scheduler.queue.store.target, registry=registry, sender=sender)
    first = executor.deliver_result(owner=sub.owner_ref, job_id=job, destination_ref='destination_private', upper_bound=1)
    assert first['status'] == 'sent' and first['provider_receipt'] == 'provider_receipt_1'
    assert executor.deliver_result(owner=sub.owner_ref, job_id=job, destination_ref='destination_private', upper_bound=1)['status'] == 'sent'
    assert len(calls) == 1
    with pytest.raises(StateConflict): executor.deliver_result(owner=sub.owner_ref, job_id=job, destination_ref='destination_other', upper_bound=1)
    with pytest.raises(CapabilityDenied): executor.deliver_result(owner='foreign', job_id=job, destination_ref='destination_private', upper_bound=1)


def test_pause_winning_before_dispatch_prevents_transport(case, monkeypatch):
    scheduler, registry, sub, clock, actor = case
    grants(case); notification = pending_watch(case)[0]; calls = []
    commit = registry._commit_durable_transport
    def pause_first(reservations,**kwargs):
        scheduler.feedback(sub.subscription_id, 'pause', **actor)
        return commit(reservations,**kwargs)
    monkeypatch.setattr(registry, '_commit_durable_transport', pause_first)
    executor = DeliveryExecutor(scheduler.queue.store.target, registry=registry, sender=lambda *args: calls.append(args))
    assert executor.deliver_watch(owner=sub.owner_ref, notification_id=notification, upper_bound=1)['status'] == 'unknown'
    assert not calls


def test_dispatch_winning_holds_scope_until_pause_ack(case):
    scheduler, registry, sub, clock, actor = case
    grants(case); notification = pending_watch(case)[0]
    started, release, paused = Event(), Event(), Event(); results = []; errors = []
    def sender(*args):
        started.set(); assert release.wait(timeout=5)
        return TransportReceipt('provider_watch_1')
    executor = DeliveryExecutor(scheduler.queue.store.target, registry=registry, sender=sender)
    def send():
        try: results.append(executor.deliver_watch(owner=sub.owner_ref, notification_id=notification, upper_bound=1))
        except Exception as exc: errors.append(exc)
    def pause():
        try: scheduler.feedback(sub.subscription_id, 'pause', **actor); paused.set()
        except Exception as exc: errors.append(exc)
    dispatch = Thread(target=send); dispatch.start(); assert started.wait(timeout=5)
    control = Thread(target=pause); control.start()
    assert not paused.wait(timeout=.15)
    release.set(); dispatch.join(timeout=5); control.join(timeout=5)
    assert not dispatch.is_alive() and not control.is_alive() and not errors
    assert results[0]['status'] == 'sent' and paused.is_set()


def test_revoke_winning_before_final_send_and_foreground_scope_separation(case, monkeypatch):
    scheduler, registry, sub, clock, actor = case
    grants(case); job = completed(case); calls = []
    commit = registry._commit_durable_transport
    def revoke_first(reservations):
        registry.revoke_grant('grant_answer', owner_ref=sub.owner_ref)
        return commit(reservations,**kwargs)
    monkeypatch.setattr(registry, '_commit_durable_transport', revoke_first)
    executor = DeliveryExecutor(scheduler.queue.store.target, registry=registry, sender=lambda *args: calls.append(args))
    assert executor.deliver_result(owner=sub.owner_ref, job_id=job, destination_ref='destination_private', upper_bound=1)['status'] == 'unknown'
    assert not calls
    notification = pending_watch(case)[0]
    registry.revoke_grant('grant_watch', owner_ref=sub.owner_ref)
    with pytest.raises(CapabilityDenied): executor.deliver_watch(owner=sub.owner_ref, notification_id=notification, upper_bound=1)


def test_persistent_watch_cap_blocks_other_effect_even_after_restart(case):
    scheduler, registry, sub, clock, actor = case
    grants(case); first, second = pending_watch(case, total=2, cap=1)
    executor = DeliveryExecutor(scheduler.queue.store.target, registry=registry, sender=lambda *args: TransportReceipt('cap_receipt'))
    assert executor.deliver_watch(owner=sub.owner_ref, notification_id=first, upper_bound=1)['status'] == 'sent'
    restarted = DeliveryExecutor(scheduler.queue.store.target, registry=registry, sender=lambda *args: TransportReceipt('bad_second'))
    with pytest.raises(CapabilityDenied, match='daily delivery cap'):
        restarted.deliver_watch(owner=sub.owner_ref, notification_id=second, upper_bound=1)


def test_provider_reconciliation_is_exact_and_never_retries(case):
    scheduler, registry, sub, clock, actor = case
    grants(case); job = completed(case); calls = []
    def lost(*args): calls.append(args); raise TimeoutError('synthetic ACK loss')
    executor = DeliveryExecutor(scheduler.queue.store.target, registry=registry, sender=lost)
    pending = executor.deliver_result(owner=sub.owner_ref, job_id=job, destination_ref='destination_private', upper_bound=1)
    def wrong(row): return ReconciliationObservation('wrong_attempt', row['destination_ref'], row['digest'], 'delivered', 'proof', 'receipt')
    with pytest.raises(CapabilityDenied): executor.reconcile(owner=sub.owner_ref, delivery_id=pending['id'], adapter=wrong, upper_bound=1)
    assert executor.attempt(owner=sub.owner_ref, delivery_id=pending['id'])['status'] == 'unknown'
    def valid(row): return ReconciliationObservation(row['attempt_ref'], row['destination_ref'], row['digest'], 'delivered', 'provider_lookup_1', 'provider_receipt_2')
    result = executor.reconcile(owner=sub.owner_ref, delivery_id=pending['id'], adapter=valid, upper_bound=1)
    assert result['status'] == 'sent' and result['provider_receipt'] == 'provider_receipt_2'
    assert len(calls) == 1


def test_cancelled_effect_lease_cannot_send_completed_result(case):
    scheduler, registry, sub, clock, actor = case
    grants(case); job = completed(case)
    result = scheduler.queue.store.get(sub.owner_ref, 'result', 'result_' + job)
    payload = dict(schema_version=1, input_namespace='result', input_ref=result.object_id, input_version=1,
        input_digest=result.digest, connection_ref=None, resource_ref='destination_private', purpose='answer.delivery',
        consent_revision=1, effect_key='answer_' + job)
    effect = scheduler.queue.enqueue(owner=sub.owner_ref, idempotency_key='effect_job', payload=payload, mode='effect', kind='effect.dispatch',
        deadline=datetime.now(timezone.utc) + timedelta(minutes=5))
    lease = scheduler.queue.claim(owner=sub.owner_ref, modes=('effect',))
    assert scheduler.queue.cancel(owner=sub.owner_ref, job_id=effect)
    calls = []
    executor = DeliveryExecutor(scheduler.queue.store.target, registry=registry, sender=lambda *args: calls.append(args))
    with pytest.raises(StateConflict): executor.deliver_result(owner=sub.owner_ref, job_id=job, destination_ref='destination_private', upper_bound=1, effect_lease=lease)
    assert not calls


def test_private_delivery_status_and_actual_prm_adapter(case):
    from bot.prm_handlers import deliver_completed_prm_job
    from prm.runtime.ingress import TelegramJobIngress
    scheduler, registry, sub, clock, actor = case
    grants(case); job = completed(case)
    def lost(*args): raise TimeoutError('synthetic lost ACK')
    executor = DeliveryExecutor(scheduler.queue.store.target, registry=registry, sender=lost)
    pending = deliver_completed_prm_job(executor, owner_ref=sub.owner_ref, job_id=job, destination_ref='destination_private', upper_bound=1)
    ingress = TelegramJobIngress(scheduler.queue, owner_ref=sub.owner_ref, owner_chat_id=actor['chat_id'], delivery_executor=executor)
    message = {'update_id': 10, 'message': {'from': {'id': int(actor['chat_id'])}, 'chat': {'id': int(actor['chat_id']), 'type': 'private'},
        'text': '/deliverystatus ' + pending['id']}}
    assert 'Повтор заблокирован' in ingress.receive(message).text
    message['message']['from']['id'] = 999
    assert ingress.receive(message) is None


def test_confirmed_action_uses_same_final_policy_and_durable_receipt(sandbox, tmp_path):
    from tests.test_pai_durable_actions import setup, request, FakeExecutor
    reg, grant, store, action = setup(sandbox, 'common_executor')
    executor = DeliveryExecutor(sandbox.app, registry=reg, sender=None)
    path = tmp_path / 'synthetic_effect.txt'
    first = executor.execute_confirmed_action(action, request=request(reg, grant, 'op_common_1'), executor=FakeExecutor(path), store=store)
    second = executor.execute_confirmed_action(action, request=request(reg, grant, 'op_common_2'), executor=FakeExecutor(path), store=store)
    assert first == second and first.status == 'succeeded'
    assert path.read_text().splitlines() == ['synthetic effect']


def test_connection_loss_after_provider_acceptance_retains_unknown_fence(case, monkeypatch):
    scheduler, registry, sub, clock, actor = case
    grants(case); job = completed(case); opened = []; calls = []
    target = scheduler.queue.store.target
    original_connect = type(target).connect
    def traced_connect(current):
        conn = original_connect(current)
        opened.append(conn)
        return conn
    monkeypatch.setattr(type(target), 'connect', traced_connect)
    def sender(*args):
        calls.append(args)
        # Last opened connection owns the final attempt lock. Disconnect after
        # the fake provider accepted: local rollback cannot undo that effect.
        opened[-1].close()
        return TransportReceipt('provider_accepted_before_disconnect')
    executor = DeliveryExecutor(target, registry=registry, sender=sender)
    first = executor.deliver_result(owner=sub.owner_ref, job_id=job, destination_ref='destination_private', upper_bound=1)
    assert first['status'] == 'unknown'
    assert executor.deliver_result(owner=sub.owner_ref, job_id=job, destination_ref='destination_private', upper_bound=1)['status'] == 'unknown'
    assert len(calls) == 1


def test_action_reconciliation_has_separate_current_read_authority(sandbox, tmp_path):
    from tests.test_pai_durable_actions import setup, request
    reg, grant, store, action = setup(sandbox, 'common_reconcile')
    executor = DeliveryExecutor(sandbox.app, registry=reg, sender=None)
    class Lost:
        def execute(self, action): raise TimeoutError('synthetic ACK loss')
    pending = executor.execute_confirmed_action(action, request=request(reg, grant, 'op_action_lost'), executor=Lost(), store=store)
    assert pending.status == 'unknown'
    def lookup(receipt, proposal):
        return ReconciliationObservation(receipt.idempotency_key, proposal.resource_ref, receipt.content_digest,
                                         'not_delivered', 'provider_strong_absence_1')
    with pytest.raises(CapabilityDenied):
        executor.reconcile_confirmed_action(store=store, idempotency_key=pending.idempotency_key, adapter=lookup, upper_bound=1)
    reg.register_grant(replace(grant, grant_id='grant_action_lookup', capability='assistant.action_reconciliation',
        operations=('read',), data_classes=('private_connector_metadata',), purpose='action.reconcile'))
    resolved = executor.reconcile_confirmed_action(store=store, idempotency_key=pending.idempotency_key, adapter=lookup, upper_bound=1)
    assert resolved.status == 'failed_known' and resolved.reconciled
    assert executor.execute_confirmed_action(action, request=request(reg, grant, 'op_no_automatic_retry'), executor=Lost(), store=store) == resolved


def test_long_mixed_source_answer_records_parts_and_never_resends_unknown(pai):
    from tests.pai_runtime_fixtures import allow
    from datetime import datetime,timezone,timedelta
    from prm.runtime.delivery import DeliveryExecutor,TransportReceipt
    root=pai.root;owner=root.owner_ref
    for kind in ('private_archive','private_connector_content'):
        allow(pai,'assistant.result_delivery','destination_parts',kind,'answer.delivery',provider='provider_telegram',connection=None,operation='deliver')
    item=root.queue.store.put(owner,'conversation','input_parts',{'query':'Synthetic'},expected_version=0)
    job=root.queue.enqueue(owner=owner,idempotency_key='parts_fixture',kind='compute.digest',deadline=datetime.now(timezone.utc)+timedelta(minutes=5),
        payload={'schema_version':1,'input_namespace':'conversation','input_ref':item.object_id,'input_version':1,'input_digest':item.digest,
            'connection_ref':None,'resource_ref':'resource_parts','purpose':'local.assistant','consent_revision':1})
    lease=root.queue.claim(owner=owner,kinds=('compute.digest',))
    root.queue.complete(lease,{'text':'Synthetic long answer. '*400,'data_class':'private_archive','data_classes':['private_archive','private_connector_content']})
    calls=[]
    def sender(destination,text,attempt):
        calls.append((destination,text,attempt))
        if len(calls)==2:raise OSError('synthetic accepted-without-ack')
        return TransportReceipt('part_receipt_'+str(len(calls)))
    executor=DeliveryExecutor(root.queue.store.target,registry=root.registry,sender=sender)
    result=executor.deliver_result(owner=owner,job_id=job,destination_ref='destination_parts',upper_bound=0)
    assert result['status']=='unknown' and len(calls)==2 and all(len(call[1])<=3800 for call in calls)
    assert executor.deliver_result(owner=owner,job_id=job,destination_ref='destination_parts',upper_bound=0)['status']=='unknown'
    assert len(calls)==2


def test_delivery_requires_every_source_class_before_transport(pai):
    from tests.pai_runtime_fixtures import allow
    from datetime import datetime,timezone,timedelta
    root=pai.root;owner=root.owner_ref;calls=[]
    allow(pai,'assistant.result_delivery','destination_mixed','private_archive','answer.delivery',provider='provider_telegram',connection=None,operation='deliver')
    item=root.queue.store.put(owner,'conversation','input_mixed',{'query':'Synthetic'},expected_version=0)
    job=root.queue.enqueue(owner=owner,idempotency_key='mixed_fixture',kind='compute.digest',deadline=datetime.now(timezone.utc)+timedelta(minutes=5),
        payload={'schema_version':1,'input_namespace':'conversation','input_ref':item.object_id,'input_version':1,'input_digest':item.digest,
            'connection_ref':None,'resource_ref':'resource_mixed','purpose':'local.assistant','consent_revision':1})
    root.queue.complete(root.queue.claim(owner=owner,kinds=('compute.digest',)),{'text':'Synthetic mixed answer','data_class':'private_archive','data_classes':['private_archive','private_connector_content']})
    executor=DeliveryExecutor(root.queue.store.target,registry=root.registry,sender=lambda *args:calls.append(args))
    with pytest.raises(CapabilityDenied):executor.deliver_result(owner=owner,job_id=job,destination_ref='destination_mixed',upper_bound=0)
    assert not calls


def test_source_revocation_blocks_delivery_of_a_completed_private_copy(pai):
    from tests.pai_runtime_fixtures import allow,request
    from dataclasses import asdict
    root=pai.root;owner=root.owner_ref;calls=[]
    source=allow(pai,'archive.read','resource_archive','private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    allow(pai,'assistant.result_delivery','destination_revoked','private_archive','answer.delivery',provider='provider_telegram',connection=None,operation='deliver')
    scope=asdict(__import__('prm.capabilities',fromlist=['AuthorizationRequest']).AuthorizationRequest(owner_ref=owner,connection_ref=None,
        capability='archive.read',resource_ref='resource_archive',operation='read',data_class='private_archive',provider_ref='provider_local',purpose='research.archive'))
    root.services['mail']=lambda *args:{'status':'ok','text':'Synthetic derived private answer.','source_data_class':'private_archive','source_scopes':[scope]}
    ack,result=request(pai,9400,'/mail')
    root.registry.revoke_grant(source.grant_id,owner_ref=owner)
    executor=DeliveryExecutor(root.queue.store.target,registry=root.registry,sender=lambda *args:calls.append(args))
    assert executor.deliver_result(owner=owner,job_id=ack.job_id,destination_ref='destination_revoked',upper_bound=0)['status']=='unknown'
    assert not calls
