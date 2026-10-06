"""Real multiprocess claims, crashes, fencing and transactional queue admission."""
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
import multiprocessing
import os
import time
import pytest
from prm.storage.postgres import PostgresStore,SyntheticTarget,migrate,StateConflict,StorageError
from prm.storage.testing import PostgresSandbox
from prm.storage.jobs import JobQueue,install_jobs
from prm.runtime.worker import ComputeWorker


@pytest.fixture(scope='module')
def sandbox():
    with PostgresSandbox() as value:
        migrate(value.migrator,expected_version=0);install_jobs(value.migrator)
        yield value


def intent(sandbox,name):
    owner='owner_job_'+name
    obj=PostgresStore(sandbox.app).put(owner,'result','input_'+name,{'text':'synthetic input'},expected_version=0)
    return owner,{'schema_version':1,'input_namespace':'result','input_ref':obj.object_id,'input_version':obj.version,
        'input_digest':obj.digest,'connection_ref':None,'resource_ref':'resource_synthetic','purpose':'local.compute','consent_revision':1}


def enqueue(queue,owner,payload,key,**changes):
    return queue.enqueue(owner=owner,idempotency_key=key,payload=payload,deadline=datetime.now(timezone.utc)+timedelta(minutes=5),**changes)


def _claim_worker(config,owner,barrier,results):
    queue=JobQueue(SyntheticTarget.from_mapping(config));barrier.wait(timeout=10)
    lease=queue.claim(owner=owner)
    results.put(lease.job_id if lease else None)


def _crash_checkpoint(config,owner,results):
    queue=JobQueue(SyntheticTarget.from_mapping(config));lease=queue.claim(owner=owner,lease_seconds=1)
    queue.checkpoint(lease,{'step':1,'safe':'compute_only'})
    results.send(lease);results.close();os._exit(0)


def _run_worker(config,owner,result):
    queue=JobQueue(SyntheticTarget.from_mapping(config))
    result.put(ComputeWorker(queue,owner=owner).run_once())


def test_two_processes_never_claim_same_job(sandbox):
    owner,payload=intent(sandbox,'race');queue=JobQueue(sandbox.app);job=enqueue(queue,owner,payload,'same-intent')
    assert enqueue(queue,owner,payload,'same-intent')==job
    ctx=multiprocessing.get_context('spawn');barrier=ctx.Barrier(2);results=ctx.Queue()
    workers=[ctx.Process(target=_claim_worker,args=(asdict(sandbox.app),owner,barrier,results)) for _ in range(2)]
    for worker in workers:worker.start()
    outcomes=[results.get(timeout=20) for _ in workers]
    for worker in workers:worker.join(timeout=20);assert worker.exitcode==0
    assert outcomes.count(job)==1 and outcomes.count(None)==1


def test_killed_compute_resumes_checkpoint_new_generation_and_stale_writer_denied(sandbox):
    owner,payload=intent(sandbox,'recover');queue=JobQueue(sandbox.app);job=enqueue(queue,owner,payload,'recover-intent')
    ctx=multiprocessing.get_context('spawn');parent,child=ctx.Pipe(duplex=False)
    worker=ctx.Process(target=_crash_checkpoint,args=(asdict(sandbox.app),owner,child));worker.start();child.close()
    assert parent.poll(15);old=parent.recv();worker.join(timeout=20);assert worker.exitcode==0
    time.sleep(1.1);assert queue.recover_expired(owner=owner)==1
    time.sleep(1.1);new=queue.claim(owner=owner)
    assert new.generation==old.generation+1 and new.checkpoint=={'step':1,'safe':'compute_only'}
    with pytest.raises(StateConflict):queue.complete(old,{'stale':True})
    with pytest.raises(StateConflict):queue.heartbeat(old)
    queue.complete(new,{'resumed':True})
    assert queue.status(owner=owner,job_id=job)['status']=='completed'


def test_unknown_effect_is_never_reclaimed_as_compute_or_resent(sandbox):
    owner,payload=intent(sandbox,'effect');payload={**payload,'effect_key':'action_synthetic_unknown'};queue=JobQueue(sandbox.app)
    job=enqueue(queue,owner,payload,'effect-intent',mode='effect',kind='effect.dispatch')
    assert queue.claim(owner=owner) is None
    lease=queue.claim(owner=owner,modes=('effect',),lease_seconds=1)
    assert lease is not None
    time.sleep(1.1);queue.recover_expired(owner=owner)
    assert queue.status(owner=owner,job_id=job)['status']=='awaiting_reconciliation'
    assert queue.claim(owner=owner,modes=('effect',)) is None
    with pytest.raises(StorageError):queue.complete(lease,{'sent':True})


def test_atomic_domain_change_queue_rollback_and_backpressure(sandbox):
    owner,payload=intent(sandbox,'atomic');queue=JobQueue(sandbox.app,admission_limit=1)
    with pytest.raises(RuntimeError):
        with queue.store.transaction() as tx:
            tx.put(owner,'memory','domain_change',{'changed':True},expected_version=0)
            queue.enqueue_in(tx,owner=owner,idempotency_key='rolled-back',payload=payload,deadline=datetime.now(timezone.utc)+timedelta(minutes=5))
            raise RuntimeError('synthetic rollback')
    assert queue.store.get(owner,'memory','domain_change') is None
    job=enqueue(queue,owner,payload,'admitted')
    with pytest.raises(StorageError,match='admission'):enqueue(queue,owner,payload,'overflow')
    assert queue.cancel(owner=owner,job_id=job)
    assert enqueue(queue,owner,payload,'after_cancel')


def test_cancel_and_unsupported_payload_deny_fenced_writes(sandbox):
    owner,payload=intent(sandbox,'cancel');queue=JobQueue(sandbox.app);job=enqueue(queue,owner,payload,'cancel-intent')
    lease=queue.claim(owner=owner);assert queue.cancel(owner=owner,job_id=job)
    with pytest.raises(StateConflict):queue.checkpoint(lease,{'late':True})
    bad=enqueue(queue,owner,payload,'corrupted-version')
    with sandbox.migrator.connect() as conn:
        conn.execute("UPDATE pa_jobs.jobs SET payload=jsonb_set(payload,'{schema_version}','2') WHERE owner=%s AND id=%s",(owner,bad))
    assert queue.claim(owner=owner) is None
    assert queue.status(owner=owner,job_id=bad)['status']=='quarantined'


def test_actual_compute_worker_in_separate_process(sandbox):
    owner,payload=intent(sandbox,'worker');queue=JobQueue(sandbox.app);job=enqueue(queue,owner,payload,'worker-intent')
    ctx=multiprocessing.get_context('spawn');results=ctx.Queue();worker=ctx.Process(target=_run_worker,args=(asdict(sandbox.app),owner,results))
    worker.start();ref=results.get(timeout=20);worker.join(timeout=20);assert worker.exitcode==0
    assert queue.status(owner=owner,job_id=job)['status']=='completed'
    assert queue.store.get(owner,'result',ref).payload['input_digest']==payload['input_digest']


def test_priorities_deadlines_heartbeat_and_retry_limits(sandbox):
    owner,payload=intent(sandbox,'bounds');queue=JobQueue(sandbox.app)
    low=enqueue(queue,owner,payload,'low-priority',priority=0)
    high=enqueue(queue,owner,payload,'high-priority',priority=10,max_attempts=1)
    lease=queue.claim(owner=owner,lease_seconds=5);assert lease.job_id==high
    assert queue.heartbeat(lease)>lease.lease_until
    queue.retry_compute(lease,delay_seconds=1)
    assert queue.status(owner=owner,job_id=high)['status']=='failed'
    nextlease=queue.claim(owner=owner);assert nextlease.job_id==low
    queue.retry_compute(nextlease,delay_seconds=1)
    assert queue.claim(owner=owner) is None
    time.sleep(1.1);assert queue.claim(owner=owner).job_id==low
    with pytest.raises(StorageError):queue.enqueue(owner=owner,idempotency_key='expired',payload=payload,deadline=datetime.now(timezone.utc)-timedelta(seconds=1))
    with pytest.raises(StorageError):enqueue(queue,owner,{**payload,'authorization':{'allowed':True}},'bad-authority')
