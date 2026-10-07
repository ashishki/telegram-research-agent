"""Real shared PostgreSQL policy; external transport is the only fake."""
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
import multiprocessing
import uuid
import pytest
from prm.capabilities import CapabilityGrant,ProviderPolicy,AuthorizationRequest,commit_transport_reservations
from prm.storage.postgres import migrate,StateConflict
from prm.storage.testing import PostgresSandbox
from prm.storage.policy import DurableCapabilityRegistry,install_policy


@pytest.fixture(scope='module')
def sandbox():
    with PostgresSandbox() as value:
        migrate(value.migrator,expected_version=0);install_policy(value.migrator)
        yield value


def registry(sandbox,name,capacity=10):
    owner='owner_synthetic_'+name
    refs=tuple(kind+'_'+name for kind in ('request','day','month'))
    reg=DurableCapabilityRegistry(sandbox.app,budget_refs=refs)
    now=datetime.now(timezone.utc)
    for kind,ref in zip(('request','day','month'),refs):
        reg.configure_window(owner=owner,ref=ref,kind=kind,capacity=capacity,starts=now-timedelta(hours=1),ends=now+timedelta(days=1))
    grant=CapabilityGrant('grant_synthetic_primary',owner,None,'model.generate',('resource_conversation',),('model_egress',),
        ('user_provided',),'answer.request',ProviderPolicy(('provider_openai',),maximum_request_count=1000),now-timedelta(minutes=1),now+timedelta(hours=1),1)
    reg.register_grant(grant)
    return reg,grant


def request(grant,operation):
    return AuthorizationRequest(grant.owner_ref,grant.capability,'resource_conversation','model_egress','user_provided',
        'provider_openai',grant.purpose,expected_grant_revision=grant.revision,operation_ref=operation)


def test_grant_expiring_during_final_lock_wait_cannot_dispatch(sandbox,monkeypatch):
    from threading import Thread,Event
    from prm.capabilities import CapabilityDenied
    reg,grant=registry(sandbox,'expiry_wait')
    grant=replace(grant,revision=2,expires_at=datetime.now(timezone.utc)+timedelta(seconds=.4))
    reg.replace_grant(grant)
    decision=reg.authorize_and_reserve(request(grant,'op_expiry_wait'),upper_bound=1)
    assert decision.allowed
    locked=Event();errors=[]
    def hold_grant():
        try:
            with sandbox.app.connect() as conn:
                with conn.transaction():
                    conn.execute('SELECT grant_id FROM pa_policy.grants WHERE owner=%s FOR UPDATE',(grant.owner_ref,))
                    locked.set();conn.execute('SELECT pg_sleep(.6)')
        except Exception as exc:errors.append(exc);locked.set()
    worker=Thread(target=hold_grant)
    prepare=reg._commit_durable_transport
    def prepare_then_contend(reservations):
        result=prepare(reservations)
        worker.start();assert locked.wait(timeout=5)
        return result
    monkeypatch.setattr(reg,'_commit_durable_transport',prepare_then_contend)
    calls=[]
    try:
        with pytest.raises(CapabilityDenied):reg.execute_reserved((decision.reservation,),lambda:calls.append('dispatched'))
    finally:worker.join(timeout=5)
    assert not worker.is_alive() and not errors and not calls


def _reserve_worker(config,refs,grant,barrier,result):
    from prm.storage.postgres import SyntheticTarget
    reg=DurableCapabilityRegistry(SyntheticTarget.from_mapping(config),budget_refs=refs)
    barrier.wait(timeout=10)
    accepted=0
    for index in range(10):
        decision=reg.authorize_and_reserve(request(grant,'op_'+uuid.uuid4().hex),upper_bound=1)
        if decision.allowed:accepted+=1
    result.put(accepted)


def test_two_processes_cannot_double_reserve_common_budget(sandbox):
    reg,grant=registry(sandbox,'race',10)
    ctx=multiprocessing.get_context('spawn');barrier=ctx.Barrier(2);results=ctx.Queue()
    workers=[ctx.Process(target=_reserve_worker,args=(asdict(sandbox.app),reg.budget_refs,grant,barrier,results)) for _ in range(2)]
    for worker in workers:worker.start()
    counts=[results.get(timeout=30) for _ in workers]
    for worker in workers:worker.join(timeout=20);assert worker.exitcode==0
    assert sum(counts)==10
    assert all(row['reserved']==10 and row['consumed']==0 for row in reg.snapshot(grant.owner_ref)['windows'])


def test_revoke_and_revision_before_transport_deny_in_another_registry(sandbox):
    reg,grant=registry(sandbox,'revoke')
    other=DurableCapabilityRegistry(sandbox.app,budget_refs=reg.budget_refs)
    decision=reg.authorize_and_reserve(request(grant,'op_revoke'),upper_bound=1)
    assert decision.allowed and decision.reservation.current
    other.revoke_grant(grant.grant_id,owner_ref=grant.owner_ref)
    assert not decision.reservation.consume()
    assert not reg.authorize(request(grant,'op_after_revoke')).allowed
    reg2,grant2=registry(sandbox,'revision')
    decision2=reg2.authorize_and_reserve(request(grant2,'op_revision'),upper_bound=1)
    reg2.replace_grant(replace(grant2,revision=2))
    assert not commit_transport_reservations((decision2.reservation,))


def test_unknown_spend_restart_and_rollover_do_not_refund_or_retry(sandbox):
    reg,grant=registry(sandbox,'unknown',2)
    decision=reg.authorize_and_reserve(request(grant,'op_unknown'),upper_bound=2)
    assert decision.allowed and decision.reservation.consume()
    decision.reservation.record_delivery_outcome('unknown')
    restarted=DurableCapabilityRegistry(sandbox.app,budget_refs=reg.budget_refs)
    assert not restarted.authorize_and_reserve(request(grant,'op_unknown'),upper_bound=2).allowed
    assert not restarted.authorize_and_reserve(request(grant,'op_new'),upper_bound=1).allowed
    assert all(w['consumed']==2 and w['reserved']==0 for w in restarted.snapshot(grant.owner_ref)['windows'])
    now=datetime.now(timezone.utc);newrefs=tuple(ref+'_funded_new' for ref in reg.budget_refs)
    for kind,ref in zip(('day','month','request'),newrefs):
        restarted.configure_window(owner=grant.owner_ref,ref=ref,kind=kind,capacity=2,starts=now-timedelta(seconds=1),ends=now+timedelta(days=2))
    new=DurableCapabilityRegistry(sandbox.app,budget_refs=newrefs)
    assert not new.authorize_and_reserve(request(grant,'op_unknown'),upper_bound=2).allowed
    assert new.authorize_and_reserve(request(grant,'op_explicit_new'),upper_bound=1).allowed


def test_scope_unknown_price_and_window_reset_fail_closed(sandbox):
    reg,grant=registry(sandbox,'scope')
    assert reg.authorize_and_reserve(request(grant,'op_unknown_price')).reason=='unknown_price'
    for change in ({'purpose':'different.purpose'},{'provider_ref':'provider_other'},{'owner_ref':'owner_synthetic_foreign'},{'resource_ref':'resource_other'}):
        assert not reg.authorize_and_reserve(replace(request(grant,'op_denied_'+uuid.uuid4().hex),**change),upper_bound=1).allowed
    now=datetime.now(timezone.utc)
    with pytest.raises(StateConflict):reg.configure_window(owner=grant.owner_ref,ref=reg.budget_refs[0],kind='request',capacity=100,starts=now,ends=now+timedelta(days=2))
    assert all(w['reserved']==0 for w in reg.snapshot(grant.owner_ref)['windows'])


def test_text_context_group_commits_once_and_settles_once(sandbox):
    reg,grant=registry(sandbox,'compound',5)
    context_grant=replace(grant,grant_id='grant_synthetic_context',capability='model.context_egress',resource_refs=('resource_archive',),
        data_classes=('private_archive',),purpose='answer.context')
    reg.register_grant(context_grant)
    text=reg.authorize_and_reserve(request(grant,'op_compound'),upper_bound=3)
    context_request=AuthorizationRequest(context_grant.owner_ref,'model.context_egress','resource_archive','model_egress','private_archive',
        'provider_openai','answer.context',operation_ref='op_compound',expected_grant_revision=1)
    context=reg.authorize_and_reserve(context_request,upper_bound=3)
    assert text.allowed and context.allowed
    assert not commit_transport_reservations((text.reservation,))
    assert commit_transport_reservations((text.reservation,context.reservation))
    assert not commit_transport_reservations((text.reservation,context.reservation))
    text.reservation.record_delivery_outcome('accepted')
    context.reservation.record_delivery_outcome('accepted')
    assert all(w['consumed']==3 and w['reserved']==0 for w in reg.snapshot(grant.owner_ref)['windows'])
    reg.settle(grant.owner_ref,'op_compound',outcome='accepted',actual=2)
    reg.settle(grant.owner_ref,'op_compound',outcome='accepted',actual=2)
    assert all(w['consumed']==2 for w in reg.snapshot(grant.owner_ref)['windows'])


def test_actual_adapter_call_rechecks_scope_and_preserves_unknown_after_error(sandbox):
    reg,grant=registry(sandbox,'transport')
    decision=reg.authorize_and_reserve(request(grant,'op_transport'),upper_bound=2)
    calls=[]
    assert reg.execute_reserved((decision.reservation,),lambda:calls.append('external-io') or {'ok':True})=={'ok':True}
    assert calls==['external-io']
    failed=reg.authorize_and_reserve(request(grant,'op_failed_transport'),upper_bound=2)
    def transport():
        calls.append('uncertain-io')
        raise TimeoutError('synthetic provider ACK lost')
    with pytest.raises(TimeoutError):reg.execute_reserved((failed.reservation,),transport)
    assert len(calls)==2
    assert reg.snapshot(grant.owner_ref)['operations'][-1]['state'] in {'accepted','unknown'}
    assert not reg.authorize_and_reserve(request(grant,'op_failed_transport'),upper_bound=2).allowed


def test_connection_failure_has_no_in_memory_permission_fallback(sandbox,monkeypatch):
    reg,grant=registry(sandbox,'outage')
    from prm.storage.postgres import StorageError
    monkeypatch.setattr(type(sandbox.app),'connect',lambda self:(_ for _ in ()).throw(StorageError('synthetic outage')))
    assert not reg.authorize(request(grant,'op_outage')).allowed
    assert not reg.authorize_and_reserve(request(grant,'op_outage'),upper_bound=1).allowed


def test_abandoned_context_does_not_authorize_context_or_double_spend(sandbox):
    reg,grant=registry(sandbox,'abandon_context',5)
    context_grant=replace(grant,grant_id='grant_synthetic_context',capability='model.context_egress',resource_refs=('resource_archive',),data_classes=('private_archive',),purpose='answer.context')
    reg.register_grant(context_grant)
    text=reg.authorize_and_reserve(request(grant,'op_context_optional'),upper_bound=2)
    context=reg.authorize_and_reserve(AuthorizationRequest(grant.owner_ref,'model.context_egress','resource_archive','model_egress','private_archive','provider_openai','answer.context',operation_ref='op_context_optional'),upper_bound=2)
    context.reservation.abandon_before_transport()
    assert not context.reservation.current
    assert commit_transport_reservations((text.reservation,))
    assert not context.reservation.consume()
    text.reservation.record_delivery_outcome('accepted')
    assert all(w['consumed']==2 and w['reserved']==0 for w in reg.snapshot(grant.owner_ref)['windows'])


def test_prepared_operation_survives_worker_loss_without_provider_retry(sandbox):
    reg,grant=registry(sandbox,'prepared')
    decision=reg.authorize_and_reserve(request(grant,'op_prepared_lost_worker'),upper_bound=2)
    assert decision.reservation.consume()
    restarted=DurableCapabilityRegistry(sandbox.app,budget_refs=reg.budget_refs)
    assert not restarted.authorize_and_reserve(request(grant,'op_prepared_lost_worker'),upper_bound=2).allowed
    assert all(w['reserved']==2 for w in restarted.snapshot(grant.owner_ref)['windows'])


def test_compound_preparation_fault_is_unknown_and_first_group_cannot_replay(sandbox,monkeypatch):
    from prm.storage.policy import ScopePreparationUnknown
    from prm.storage.postgres import StorageError
    reg,grant=registry(sandbox,'group_partial_fault',capacity=10)
    first=reg.authorize_and_reserve(request(grant,'group_first'),upper_bound=1)
    second=reg.authorize_and_reserve(request(grant,'group_second'),upper_bound=1)
    real=reg._commit_durable_transport
    def failing(group,*,strict=False):
        if group[0].operation_ref=='group_second':raise StorageError('synthetic state outage')
        return real(group,strict=strict)
    monkeypatch.setattr(reg,'_commit_durable_transport',failing)
    calls=[]
    with pytest.raises(ScopePreparationUnknown) as failed:reg.execute_reserved_groups(((first.reservation,),(second.reservation,)),lambda:calls.append(True))
    assert not failed.value.retry_allowed and 'group_first' in failed.value.operation_refs and not calls
    assert not reg.authorize_and_reserve(request(grant,'group_first'),upper_bound=1).allowed
    operation=next(row for row in reg.snapshot(grant.owner_ref)['operations'] if row['ref']=='group_first')
    assert operation['state']=='unknown'
