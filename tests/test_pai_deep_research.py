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


def test_interrupted_prepared_step_is_not_read_again(pai):
    from prm.runtime.research import DurableResearchWorker
    root=pai.root;worker=DurableResearchWorker(root)
    job=worker.enqueue({'schema_version':1,'question':'Synthetic research','steps':[{'source':'archive','query':'synthetic'}],
        'max_tool_calls':1,'deadline_seconds':180},idempotency_key='interrupted_step_fixture')
    ref='research_step_'+job+'_0'
    root.queue.store.put(root.owner_ref,'result',ref,{'ref':ref,'source':'archive','status':'read_prepared','tool_calls':1,'evidence':{}},expected_version=0)
    class ForbiddenReader:
        def search_archive(self,*args,**kwargs):raise AssertionError('prepared read must not be repeated')
    root.deep_archive_reader=ForbiddenReader()
    result=root.queue.store.get(root.owner_ref,'result',worker.run_once())
    assert 'source_outcome_unknown' in result.payload['gaps'][0]
    assert result.payload['tool_calls']==1
