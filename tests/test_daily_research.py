"""Two-wave native jobs, exact continuation and prepared-read recovery."""
import pytest
from tests.pai_runtime_fixtures import pai,allow,request
from prm.runtime.research import DurableResearchWorker
from prm.storage.postgres import StorageError,StateConflict


class Reader:
    def __init__(self,first='Retrieval is described here.',second='Cache is described here.'):
        self.first,self.second=first,second;self.calls=[]
    def search_archive(self,query,*,limit):
        self.calls.append(query);text=self.first if query=='retrieval' else self.second
        return {'items':[{'evidence_id':'fixture_'+str(len(self.calls)),'source_url':'https://t.me/synthetic/'+str(len(self.calls)),
                          'support_span':text,'source_version':'v1'}]}


def setup(pai,reader=None):
    pai.root.deep_archive_reader=reader or Reader()
    grant=allow(pai,'archive.read',pai.root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    plan={'schema_version':2,'question':'retrieval cache','steps':[{'source':'archive','query':'retrieval'}],
          'gap_steps':[{'source':'archive','query':'cache'}],'coverage_terms':['retrieval','cache'],'max_tool_calls':2,'deadline_seconds':180}
    return DurableResearchWorker(pai.root),plan,grant


def test_useful_second_wave_preserves_both_evidence_checkpoints_and_scopes(pai):
    worker,plan,_=setup(pai);job=worker.enqueue(plan,idempotency_key='daily_second_wave')
    result=pai.root.queue.store.get(pai.root.owner_ref,'result',worker.run_once()).payload
    assert pai.root.deep_archive_reader.calls==['retrieval','cache']
    assert result['stop_reason']=='coverage_sufficient' and result['tool_calls']==2 and len(result['evidence_refs'])==2
    assert result['coverage']['missing_terms']==[] and result['data_classes']==['private_archive']
    assert pai.root.queue.status(owner=pai.root.owner_ref,job_id=job)['checkpoint']['coverage']['sufficient']


def test_sufficient_first_wave_stops_without_unused_reads(pai):
    worker,plan,_=setup(pai,Reader(first='Retrieval cache is documented here.'))
    worker.enqueue(plan,idempotency_key='daily_first_sufficient')
    value=pai.root.queue.store.get(pai.root.owner_ref,'result',worker.run_once()).payload
    assert pai.root.deep_archive_reader.calls==['retrieval'] and value['tool_calls']==1 and value['stop_reason']=='coverage_sufficient'


def test_insufficient_budget_is_truthful_partial(pai):
    worker,plan,_=setup(pai);plan['max_tool_calls']=1
    worker.enqueue(plan,idempotency_key='daily_budget')
    result=pai.root.queue.store.get(pai.root.owner_ref,'result',worker.run_once()).payload
    assert result['status']=='partial' and result['stop_reason']=='tool_call_limit' and result['coverage']['missing_terms']==['cache']
    assert pai.root.deep_archive_reader.calls==['retrieval']


def test_restart_between_waves_does_not_repeat_completed_read(pai,monkeypatch):
    worker,plan,_=setup(pai);job=worker.enqueue(plan,idempotency_key='daily_restart_between')
    original=pai.root.queue.checkpoint
    def crash(lease,value):
        original(lease,value)
        if value['phase']=='gap_check':raise RuntimeError('synthetic worker crash')
    monkeypatch.setattr(pai.root.queue,'checkpoint',crash)
    with pytest.raises(RuntimeError):worker.run_once()
    assert pai.root.deep_archive_reader.calls==['retrieval']
    with pai.root.queue.store.transaction() as tx:tx.conn.execute("UPDATE pa_jobs.jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE owner=%s AND id=%s",(pai.root.owner_ref,job))
    monkeypatch.setattr(pai.root.queue,'checkpoint',original)
    assert DurableResearchWorker(pai.root).run_once() is None
    assert pai.root.queue.status(owner=pai.root.owner_ref,job_id=job)['status']=='retry_wait'
    with pai.root.queue.store.transaction() as tx:tx.conn.execute("UPDATE pa_jobs.jobs SET available_at=clock_timestamp()-interval '1 second' WHERE owner=%s AND id=%s",(pai.root.owner_ref,job))
    result=pai.root.queue.store.get(pai.root.owner_ref,'result',DurableResearchWorker(pai.root).run_once()).payload
    assert pai.root.deep_archive_reader.calls==['retrieval','cache'] and result['tool_calls']==2


def test_prepared_read_unknown_stops_gap_wave_without_replay(pai):
    worker,plan,_=setup(pai);job=worker.enqueue(plan,idempotency_key='daily_prepared_unknown')
    ref='research_step_'+job+'_0'
    pai.root.queue.store.put(pai.root.owner_ref,'result',ref,{'ref':ref,'source':'archive','status':'read_prepared','tool_calls':1,'evidence':{},'wave':0},expected_version=0)
    result=pai.root.queue.store.get(pai.root.owner_ref,'result',worker.run_once()).payload
    assert pai.root.deep_archive_reader.calls==[] and result['unknown_tool_calls']==1 and result['stop_reason']=='source_unavailable_or_unknown'


def test_cancel_between_waves_forbids_next_read_and_completion(pai,monkeypatch):
    worker,plan,_=setup(pai);job=worker.enqueue(plan,idempotency_key='daily_cancel_between')
    original=pai.root.queue.checkpoint
    def cancel(lease,value):
        original(lease,value)
        if value['phase']=='gap_check':pai.root.queue.cancel(owner=pai.root.owner_ref,job_id=job)
    monkeypatch.setattr(pai.root.queue,'checkpoint',cancel)
    with pytest.raises(StorageError):worker.run_once()
    assert pai.root.deep_archive_reader.calls==['retrieval'] and pai.root.queue.store.get(pai.root.owner_ref,'result','result_'+job) is None


def test_revoked_cached_read_never_enables_gap_or_model(pai,monkeypatch):
    worker,plan,grant=setup(pai);job=worker.enqueue(plan,idempotency_key='daily_revoke_cache')
    original=pai.root.queue.checkpoint
    def revoke(lease,value):
        original(lease,value)
        if value['phase']=='gap_check':pai.root.registry.revoke_grant(grant.grant_id,owner_ref=pai.root.owner_ref)
    monkeypatch.setattr(pai.root.queue,'checkpoint',revoke)
    value=pai.root.queue.store.get(pai.root.owner_ref,'result',worker.run_once()).payload
    assert value['status']=='partial' and value['coverage']['stop_extra_wave'] and not pai.requests
    assert pai.root.deep_archive_reader.calls==['retrieval'] and value['evidence_refs']==[]


def test_gap_wave_cannot_expand_sources_or_declassify_private_question(pai):
    worker,plan,_=setup(pai)
    plan['gap_steps']=[{'source':'public','query':'retrieval'}]
    with pytest.raises(StorageError):worker.enqueue(plan,idempotency_key='expansion_denied')
    plan['question']='my email contains retrieval cache';plan['steps']=[{'source':'public','query':'retrieval cache'}];plan['gap_steps']=[]
    with pytest.raises(StorageError):worker.enqueue(plan,idempotency_key='private_web_denied')
    assert not pai.requests


def test_exact_continuation_refreshes_same_sources_and_rejects_changed_digest(pai):
    worker,plan,_=setup(pai);worker.enqueue(plan,idempotency_key='daily_continue_original')
    ref=worker.run_once();item=pai.root.queue.store.get(pai.root.owner_ref,'result',ref)
    with pytest.raises(StateConflict):worker.continue_result(result_ref=ref,version=1,digest='0'*64,idempotency_key='wrong_digest')
    job=worker.continue_result(result_ref=ref,version=1,digest=item.digest,idempotency_key='exact_continue')
    value=pai.root.queue.store.get(pai.root.owner_ref,'result',worker.run_once()).payload
    assert value['continuation_of']=={'ref':ref,'version':1,'digest':item.digest}
    assert pai.root.deep_archive_reader.calls==['retrieval','cache','retrieval','cache']
    assert pai.root.queue.status(owner=pai.root.owner_ref,job_id=job)['status']=='completed'


def test_native_natural_research_and_exact_command_continuation(pai):
    worker,_,_=setup(pai,Reader(first='Retrieval cache is documented here.',second='Retrieval cache is documented here.'))
    _,answer=request(pai,140700,'Глубоко исследуй retrieval cache')
    assert answer['status']=='queued' and answer['payload']['job_ref']
    ref=worker.run_once();value=pai.root.queue.store.get(pai.root.owner_ref,'result',ref).payload
    assert value['research_plan_version']==2 and value['coverage']['sufficient']
    _,continuation=request(pai,140701,'/deepcontinue '+ref+' 1')
    assert continuation['status']=='queued' and continuation['payload']['job_ref']!=answer['payload']['job_ref']


def test_native_typed_multisource_plan_runs_independent_reads_in_parallel(pai,monkeypatch):
    import base64,json
    from threading import Barrier
    from prm.runtime import web
    from prm.runtime.web import GitHubReadProvider
    from tests.test_daily_conversation import FakePlanner,plan as task_plan
    barrier=Barrier(2,timeout=3)
    class ParallelReader(Reader):
        def search_archive(self,*args,**kwargs):
            barrier.wait();return super().search_archive(*args,**kwargs)
    worker,_,_=setup(pai,ParallelReader())
    allow(pai,'github.repository_context','owner/repository','public','project.context',provider='provider_github',connection=None,operation='read')
    def http(url,**kwargs):
        if '/commits/' in url:barrier.wait();value={'sha':'a'*40}
        else:value={'path':'README.md','encoding':'base64','size':27,'content':base64.b64encode(b'Cache is documented here.').decode(),'sha':'b'*40}
        return {'content_type':'application/json','body':json.dumps(value).encode()}
    monkeypatch.setattr(web,'_https_get',http)
    pai.root.github_context_provider=GitHubReadProvider(registry=pai.root.registry,owner_ref=pai.root.owner_ref,repository_ref='owner/repository',ref='main',upper_bound=0)
    pai.root.intent_planner=FakePlanner(task_plan(intent='research',steps=[{'tool':'archive.search','argument':'retrieval'},{'tool':'github.read','argument':''}],source_filters=['archive','github'],max_tool_calls=5))
    _,answer=request(pai,140702,'retrieval cache')
    assert answer['status']=='queued'
    result=pai.root.queue.store.get(pai.root.owner_ref,'result',worker.run_once()).payload
    assert result['coverage']['sufficient'] and result['tool_calls']==3 and result['data_classes']==['private_archive','public']
    assert pai.root.deep_archive_reader.calls==['retrieval']


def test_source_conflict_never_becomes_sufficient_after_gap(pai):
    class ConflictReader(Reader):
        def search_archive(self,*args,**kwargs):
            value=super().search_archive(*args,**kwargs)
            value['items'][0].update(conflict_group='release',conflict_value='old' if len(self.calls)==1 else 'new',support_span='Retrieval cache version is disputed.')
            value['conflicts']=['release disputed']
            return value
    worker,plan,_=setup(pai,ConflictReader());worker.enqueue(plan,idempotency_key='daily_conflict')
    value=pai.root.queue.store.get(pai.root.owner_ref,'result',worker.run_once()).payload
    assert value['status']=='partial' and value['stop_reason']=='source_conflict' and not value['coverage']['sufficient']


def test_expired_deadline_never_starts_first_read(pai):
    worker,plan,_=setup(pai);job=worker.enqueue(plan,idempotency_key='daily_expired_deadline')
    with pai.root.queue.store.transaction() as tx:tx.conn.execute("UPDATE pa_jobs.jobs SET deadline=clock_timestamp()-interval '1 second' WHERE owner=%s AND id=%s",(pai.root.owner_ref,job))
    assert worker.run_once() is None and not pai.root.deep_archive_reader.calls
    assert pai.root.queue.status(owner=pai.root.owner_ref,job_id=job)['error_code']=='deadline'
