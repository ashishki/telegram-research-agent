"""Deferred durable bounded plan/checkpoint/cancellation behavior."""
from tests.pai_runtime_fixtures import pai,allow
from prm.runtime.research import DurableResearchWorker


def test_real_research_job_has_progress_results_and_partial_source_outcome(pai):
    worker=DurableResearchWorker(pai.root)
    plan={'schema_version':1,'question':'agent evals','steps':[{'source':'archive','query':'agent evals'},{'source':'github','query':'owner/repository'}],
          'max_tool_calls':3,'deadline_seconds':120}
    job=worker.enqueue(plan,idempotency_key='synthetic_research')
    assert worker.enqueue(plan,idempotency_key='synthetic_research')==job
    ref=worker.run_once();result=pai.root.queue.store.get(pai.root.owner_ref,'result',ref)
    assert result.payload['status']=='partial' and result.payload['gaps']
    assert pai.root.queue.status(owner=pai.root.owner_ref,job_id=job)['checkpoint']['phase']=='verify'


def test_cancel_before_claim_stops_every_research_source(pai):
    worker=DurableResearchWorker(pai.root)
    plan={'schema_version':1,'question':'question','steps':[{'source':'public','query':'explicit minimized query'}],'max_tool_calls':4,'deadline_seconds':120}
    job=worker.enqueue(plan,idempotency_key='cancel_research')
    assert pai.root.queue.cancel(owner=pai.root.owner_ref,job_id=job)
    assert worker.run_once() is None and not pai.requests
