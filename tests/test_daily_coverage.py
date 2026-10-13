"""Source completeness and model-selection limits are separate facts."""
from datetime import datetime,timezone,timedelta
import pytest
from prm.source_contracts import SourceResource,SourceBatch,EvidenceBundle,normalize_source_batch

NOW=datetime(2026,10,13,tzinfo=timezone.utc)


def resource(ref='resource_archive',connection=None):
    return SourceResource('owner_synthetic',ref,'archive','private_archive',connection_ref=connection)


def rows(count):
    return [{'evidence_id':f'item_{i}','support_span':'Synthetic source '+str(i),'source_url':'https://example.test/'+str(i),'posted_at':NOW.isoformat(),'source_version':'v1'} for i in range(count)]


def test_legacy_batch_is_unknown_even_with_fewer_than_model_limit():
    batch=normalize_source_batch(rows(2),resource(),checked_at=NOW)
    assert batch.completeness=='unknown' and batch.omitted_count is None
    assert batch.received_count==2 and batch.reason=='legacy_bounded_collector'


def test_complete_three_hundred_candidates_do_not_become_full_model_packet():
    batch=SourceBatch.from_items(rows(300),resource(),checked_at=NOW,completeness='complete',omitted_count=0)
    bundle=EvidenceBundle.select((batch,),maximum_items=48)
    assert bundle.received_count==bundle.candidate_count==300 and bundle.selected_count==48
    assert bundle.model_omitted_count==252 and bundle.cited_count is None
    assert bundle.batches[0].completeness=='complete'


def test_merge_preserves_account_and_resource_identity_with_same_external_id():
    a=SourceBatch.from_items(rows(1),resource(connection='connection_a'),checked_at=NOW,completeness='complete',omitted_count=0)
    b=SourceBatch.from_items(rows(1),resource(connection='connection_b'),checked_at=NOW,completeness='complete',omitted_count=0)
    bundle=EvidenceBundle.select((a,b),maximum_items=48)
    assert len({item.evidence_ref for item in bundle.selected})==2
    assert {item.resource.connection_ref for item in bundle.selected}=={'connection_a','connection_b'}


def test_unknown_dates_are_not_rewritten_to_checked_or_discovery_time():
    value={'evidence_id':'unknown_date','support_span':'Synthetic undated fact','source_url':'https://example.test/undated','first_discovered_at':NOW.isoformat()}
    batch=SourceBatch.from_items([value],resource(),checked_at=NOW,completeness='unknown',reason='publication_unknown')
    item=batch.items[0]
    assert item.publication_time is None and item.event_time is None and item.discovery_time==NOW


def test_later_source_is_not_displaced_by_first_large_batch():
    a=SourceBatch.from_items(rows(300),resource(),checked_at=NOW,completeness='complete',omitted_count=0)
    b=SourceBatch.from_items([dict(rows(1)[0],evidence_id='later')],resource('resource_later'),checked_at=NOW,completeness='complete',omitted_count=0)
    bundle=EvidenceBundle.select((a,b),maximum_items=48)
    assert any(item.external_ref=='later' for item in bundle.selected)

from tests.pai_runtime_fixtures import pai,allow


def test_archive_enumerates_week_before_model_selection_and_keeps_half_open_bounds(pai):
    import sqlite3
    from tests.test_archive_search import _make_connection,_insert_post
    from prm.briefs import BriefWindow
    from prm.runtime.research import LocalArchiveReader
    from prm.runtime.brief import BriefRuntime,BriefSourceHook
    from prm.capabilities import AuthorizationRequest
    start=pai.now-timedelta(days=7);end=pai.now
    conn=_make_connection()
    for i in range(300):_insert_post(conn,post_id=i+1,posted_at=(start+timedelta(minutes=i)).isoformat(),content='Synthetic weekly source '+str(i))
    _insert_post(conn,post_id=301,posted_at=end.isoformat(),content='End boundary must be excluded')
    conn.commit()
    path=pai.path/'synthetic-archive.sqlite'
    with sqlite3.connect(path) as saved:conn.backup(saved)
    conn.close()
    reader=LocalArchiveReader(path,root=pai.root);window=BriefWindow('UTC',start,end,pai.now)
    batch=reader.window_evidence(window)
    assert batch.completeness=='complete' and batch.received_count==300 and batch.omitted_count==0
    assert all(r.payload['support_span']!='End boundary must be excluded' for r in batch.items)
    assert any(r.publication_time==start for r in batch.items)
    page=reader.window_evidence(window,limit=50)
    assert page.completeness=='partial' and page.omitted_count==250 and page.continuation=='offset:50'
    allow(pai,'archive.read',pai.root.archive_resource_ref,'private_archive','brief.archive',provider='provider_local',connection=None,operation='read')
    scope=AuthorizationRequest(owner_ref=pai.root.owner_ref,connection_ref=None,capability='archive.read',resource_ref=pai.root.archive_resource_ref,operation='read',data_class='private_archive',provider_ref='provider_local',purpose='brief.archive')
    doc=BriefRuntime(pai.root,source_hooks=(BriefSourceHook(scope.resource_ref,scope,reader.window_evidence,0),),editorial=lambda doc:None).build(topic='Synthetic week',timezone_name='UTC',end_at=end)
    coverage=pai.root.briefs.pending_coverage[doc.content_digest]
    assert coverage['received_count']==300 and coverage['selected_count']==20 and coverage['model_omitted_count']==280
    assert doc.status=='partial' and not pai.requests


def test_unavailable_empty_and_partial_pages_do_not_share_completeness():
    r=resource()
    empty=SourceBatch.from_items([],r,checked_at=NOW,completeness='complete',omitted_count=0)
    unavailable=SourceBatch.from_items([],r,checked_at=None,completeness='unavailable',reason='scope_denied')
    partial=SourceBatch.from_items(rows(2),r,checked_at=NOW,completeness='partial',reason='more_pages',continuation='page2')
    assert [b.completeness for b in (empty,unavailable,partial)]==['complete','unavailable','partial']
    assert unavailable.checked_at is None and partial.omitted_count is None


def test_same_version_conflict_is_preserved_and_citations_bind_selected_identity():
    a=SourceBatch.from_items(rows(1),resource(),checked_at=NOW,completeness='complete',omitted_count=0)
    b=SourceBatch.from_items([dict(rows(1)[0],support_span='Synthetic conflicting fact')],resource(),checked_at=NOW,completeness='complete',omitted_count=0)
    bundle=EvidenceBundle.select((a,b),maximum_items=2)
    assert bundle.conflict_count==1 and bundle.candidate_count==2
    assert bundle.with_citations((bundle.selected[0].evidence_ref,)).cited_count==1
    from prm.storage.postgres import StorageError
    with pytest.raises(StorageError):bundle.with_citations(('evidence_unselected',))


def test_brief_legacy_source_cannot_claim_complete_or_relabel_privacy(pai):
    from prm.runtime.brief import BriefRuntime,BriefSourceHook
    from prm.capabilities import AuthorizationRequest
    allow(pai,'archive.read',pai.root.archive_resource_ref,'private_archive','brief.archive',provider='provider_local',connection=None,operation='read')
    scope=AuthorizationRequest(owner_ref=pai.root.owner_ref,connection_ref=None,capability='archive.read',resource_ref=pai.root.archive_resource_ref,operation='read',data_class='private_archive',provider_ref='provider_local',purpose='brief.archive')
    observed=rows(1);observed[0]['posted_at']=pai.now.isoformat()
    builder=BriefRuntime(pai.root,source_hooks=(BriefSourceHook(scope.resource_ref,scope,lambda w:observed,0),),editorial=lambda doc:None)
    doc=builder.build(topic='Synthetic',timezone_name='UTC',end_at=pai.now+timedelta(seconds=1))
    assert doc.status=='partial' and pai.root.briefs.pending_coverage[doc.content_digest]['batches'][0]['completeness']=='unknown'
    observed[0]['source_data_class']='public'
    denied=builder.build(topic='Synthetic',timezone_name='UTC')
    assert not denied.evidence and not pai.requests


def test_rejected_typed_brief_batch_never_enters_selection(pai):
    from prm.runtime.brief import BriefRuntime,BriefSourceHook
    from prm.capabilities import AuthorizationRequest
    from prm.source_contracts import SourceResource,SourceBatch
    root=pai.root
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','brief.archive',provider='provider_local',connection=None,operation='read')
    scope=AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,capability='archive.read',resource_ref=root.archive_resource_ref,operation='read',data_class='private_archive',provider_ref='provider_local',purpose='brief.archive')
    value=rows(1)[0];value.update(posted_at=pai.now.isoformat(),source_data_class='public',local_archive_provenance=True)
    batch=SourceBatch.from_items([value],SourceResource(root.owner_ref,root.archive_resource_ref,'archive','private_archive'),checked_at=pai.now,completeness='complete',omitted_count=0)
    doc=BriefRuntime(root,source_hooks=(BriefSourceHook(scope.resource_ref,scope,lambda w:batch,0),),editorial=lambda doc:None).build(topic='Synthetic',timezone_name='UTC',end_at=pai.now+timedelta(seconds=1))
    assert not doc.evidence
    assert root.briefs.pending_coverage[doc.content_digest]['received_count']==0
    assert root.briefs.pending_scopes[doc.content_digest]==[]


def test_research_collector_cannot_relabel_archive_as_public(pai):
    from prm.runtime.research import DurableResearchWorker
    from prm.source_contracts import SourceResource,SourceBatch
    root=pai.root
    value=rows(1)[0]
    metadata=SourceBatch.from_items([value],SourceResource(root.owner_ref,'resource_unselected','web','public'),checked_at=pai.now,completeness='complete',omitted_count=0).metadata()
    class Reader:
        def search_archive(self,*args,**kwargs):return {'items':[value],'source_batch':metadata}
    root.deep_archive_reader=Reader()
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request')
    allow(pai,'model.context_egress',root.public_fetch_ref,'public','research.synthesis.public')
    worker=DurableResearchWorker(root)
    worker.enqueue({'schema_version':1,'question':'Synthetic question','steps':[{'source':'archive','query':'Synthetic'}],'max_tool_calls':1,'deadline_seconds':60},idempotency_key='daily_privacy_relabel')
    output=root.queue.store.get(root.owner_ref,'result',worker.run_once()).payload
    assert not pai.requests and output['answer_payload']['source_coverage']['received_count']==0


def test_native_attach_graph_archive_hook_binds_runtime_owner(pai):
    import sqlite3
    from types import SimpleNamespace
    from tests.test_archive_search import _make_connection,_insert_post
    from prm.runtime.brief import BriefRuntime
    root=pai.root;conn=_make_connection()
    _insert_post(conn,post_id=1,posted_at=(pai.now-timedelta(hours=1)).isoformat(),content='Synthetic native archive hook')
    conn.commit();path=pai.path/'native-archive.sqlite'
    with sqlite3.connect(path) as saved:conn.backup(saved)
    conn.close();root.settings.db_path=path
    root.attach_graph(SimpleNamespace(owner_ref=root.owner_ref,registry=root.registry))
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','brief.archive',provider='provider_local',connection=None,operation='read')
    doc=BriefRuntime(root,source_hooks=root.brief_source_hooks,editorial=lambda doc:None).build(topic='Synthetic',timezone_name='UTC',end_at=pai.now)
    assert len(doc.evidence)==1 and root.briefs.pending_coverage[doc.content_digest]['received_count']==1
    assert not pai.requests


def test_research_read_revocation_before_synthesis_blocks_egress(pai):
    from prm.runtime.research import DurableResearchWorker
    root=pai.root
    class Reader:
        def search_archive(self,*args,**kwargs):return {'items':rows(1)}
    root.deep_archive_reader=Reader()
    source=allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request')
    allow(pai,'model.context_egress',root.archive_resource_ref,'private_archive','research.synthesis.archive')
    class RevokingWorker(DurableResearchWorker):
        def _gather(self,*args):
            value=super()._gather(*args)
            root.registry.revoke_grant(source.grant_id,owner_ref=root.owner_ref)
            return value
    worker=RevokingWorker(root)
    worker.enqueue({'schema_version':1,'question':'Synthetic','steps':[{'source':'archive','query':'Synthetic'}],'max_tool_calls':1,'deadline_seconds':60},idempotency_key='daily_synthesis_revocation')
    output=root.queue.store.get(root.owner_ref,'result',worker.run_once()).payload
    assert not pai.requests and output['answer_payload']['source_coverage']['received_count']==0


def test_research_delivery_preserves_top_level_read_scopes(pai):
    from prm.runtime.research import DurableResearchWorker
    from prm.runtime.delivery import DeliveryExecutor
    root=pai.root;calls=[]
    class Reader:
        def search_archive(self,*args,**kwargs):return {'items':rows(1)}
    root.deep_archive_reader=Reader()
    source=allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    allow(pai,'assistant.result_delivery','destination_daily','private_archive','answer.delivery',provider='provider_telegram',connection=None,operation='deliver')
    worker=DurableResearchWorker(root)
    job=worker.enqueue({'schema_version':1,'question':'Synthetic','steps':[{'source':'archive','query':'Synthetic'}],'max_tool_calls':1,'deadline_seconds':60},idempotency_key='daily_delivery_revocation')
    worker.run_once();root.registry.revoke_grant(source.grant_id,owner_ref=root.owner_ref)
    executor=DeliveryExecutor(root.queue.store.target,registry=root.registry,sender=lambda *args:calls.append(args))
    receipt=executor.deliver_result(owner=root.owner_ref,job_id=job,destination_ref='destination_daily',upper_bound=0)
    assert receipt['status']=='unknown' and not calls


@pytest.mark.parametrize('field,value',[('owner_ref','owner_other'),('resource_ref','resource_other'),('kind','web'),('data_class','public'),('connection_ref','connection_other'),('scope_digest','unexpected_scope')])
def test_stored_research_metadata_is_revalidated_before_selection(pai,field,value):
    from prm.runtime.research import DurableResearchWorker
    root=pai.root
    class Reader:
        def search_archive(self,*args,**kwargs):return {'items':rows(1)}
    root.deep_archive_reader=Reader()
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request')
    allow(pai,'model.context_egress',root.archive_resource_ref,'private_archive','research.synthesis.archive')
    class AlteredWorker(DurableResearchWorker):
        def _gather(self,*args):
            step=super()._gather(*args)
            step['source_batch']['selected_resources'][0][field]=value
            return step
    worker=AlteredWorker(root)
    worker.enqueue({'schema_version':1,'question':'Synthetic','steps':[{'source':'archive','query':'Synthetic'}],'max_tool_calls':1,'deadline_seconds':60},idempotency_key='daily_stored_'+field)
    output=root.queue.store.get(root.owner_ref,'result',worker.run_once()).payload
    assert output['status']=='partial' and output['answer_payload']['source_coverage']['received_count']==0 and not pai.requests


def test_research_coverage_counts_received_and_rejected_projection_separately(pai):
    from prm.runtime.research import DurableResearchWorker
    root=pai.root
    observed=rows(2);observed[1]['source_url']='unsupported://synthetic'
    class Reader:
        def search_archive(self,*args,**kwargs):return {'items':observed}
    root.deep_archive_reader=Reader()
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    worker=DurableResearchWorker(root)
    worker.enqueue({'schema_version':1,'question':'Synthetic','steps':[{'source':'archive','query':'Synthetic'}],'max_tool_calls':1,'deadline_seconds':60},idempotency_key='daily_projections')
    coverage=root.queue.store.get(root.owner_ref,'result',worker.run_once()).payload['answer_payload']['source_coverage']
    assert coverage['received_count']==2 and coverage['candidate_count']==coverage['selected_count']==1 and coverage['projection_rejected_count']==1


def test_graph_summary_uses_one_snapshot_during_same_count_sync(pai):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from tests.pai_runtime_fixtures import graph
    from prm.runtime.graph import GraphMailAdapter
    from prm.mail_connector import MailScopeSelection
    _,transport,_=graph(pai)
    allow(pai,'assistant.mail_read','resource_selected_mail','private_connector_metadata','mail.read',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    selection=MailScopeSelection('provider_microsoft_graph','resource_selected_mail',folders=('inbox',))
    adapter=GraphMailAdapter(transport);adapter.sync(selection);store=adapter.store
    before=adapter.summary(selection);changed=[]
    class Conn:
        def __init__(self,conn):self.conn=conn
        def execute(self,sql,*args):
            cursor=self.conn.execute(sql,*args)
            if sql.startswith('SELECT payload,version FROM pa_sources.items'):
                records=cursor.fetchall()
                with store.transaction() as other:
                    other.conn.execute("UPDATE pa_sources.items SET version='new_version',payload=jsonb_set(payload,'{subject}','\"Changed synthetic subject\"'::jsonb) WHERE owner=%s AND connection_ref=%s AND kind='mail'",(transport.owner_ref,transport.connection_ref))
                    other.conn.execute("UPDATE pa_sources.sync SET updated_at=clock_timestamp() WHERE owner=%s AND connection_ref=%s AND kind='mail'",(transport.owner_ref,transport.connection_ref))
                changed.append(True)
                return SimpleNamespace(fetchall=lambda:records)
            return cursor
    class Store:
        @contextmanager
        def transaction(self,**kwargs):
            with store.transaction(**kwargs) as tx:yield SimpleNamespace(conn=Conn(tx.conn))
    adapter.store=Store();during=adapter.summary(selection);adapter.store=store;after=adapter.summary(selection)
    assert changed and during==before and after['source_batch']['checked_at']!=before['source_batch']['checked_at']
    assert all(item['source_version']=='new_version' for item in after['items'])


def test_research_final_transport_holds_read_grant_lock(pai,monkeypatch):
    from psycopg.errors import LockNotAvailable
    from prm.runtime.research import DurableResearchWorker
    from prm.runtime.model_protocol import ChatCompletionsTransport
    root=pai.root;locked=[]
    class Reader:
        def search_archive(self,*args,**kwargs):return {'items':rows(1)}
    root.deep_archive_reader=Reader()
    source=allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request')
    allow(pai,'model.context_egress',root.archive_resource_ref,'private_archive','research.synthesis.archive')
    send=ChatCompletionsTransport.send
    def checked_send(self,*args,**kwargs):
        with root.queue.store.target.connect() as conn:
            with pytest.raises(LockNotAvailable):
                with conn.transaction():conn.execute('SELECT grant_id FROM pa_policy.grants WHERE owner=%s AND grant_id=%s FOR UPDATE NOWAIT',(root.owner_ref,source.grant_id))
        locked.append(True)
        return send(self,*args,**kwargs)
    monkeypatch.setattr(ChatCompletionsTransport,'send',checked_send)
    worker=DurableResearchWorker(root)
    worker.enqueue({'schema_version':1,'question':'Synthetic','steps':[{'source':'archive','query':'Synthetic'}],'max_tool_calls':1,'deadline_seconds':60},idempotency_key='daily_source_lock')
    result=root.queue.store.get(root.owner_ref,'result',worker.run_once()).payload
    assert locked==[True] and len(pai.requests)==1 and result['answer_payload']['model_reply_observed']


def test_protected_result_without_read_authority_is_not_dispatched(pai):
    from prm.runtime.delivery import DeliveryExecutor
    from prm.capabilities import CapabilityDenied
    root=pai.root;calls=[]
    ack=root.ingress.receive({'update_id':119800,'message':{'chat':{'id':42,'type':'private'},'from':{'id':42},'text':'Synthetic private fixture'}})
    lease=root.queue.claim(owner=root.owner_ref,kinds=('compute.assistant',))
    root.queue.complete(lease,{'text':'Synthetic protected copy','data_classes':['private_archive'],'data_class':'private_archive'})
    allow(pai,'assistant.result_delivery','destination_no_authority','private_archive','answer.delivery',provider='provider_telegram',connection=None,operation='deliver')
    executor=DeliveryExecutor(root.queue.store.target,registry=root.registry,sender=lambda *args:calls.append(args))
    with pytest.raises(CapabilityDenied):executor.deliver_result(owner=root.owner_ref,job_id=ack.job_id,destination_ref='destination_no_authority',upper_bound=0)
    assert not calls and executor.attempt(owner=root.owner_ref,delivery_id='answer_'+ack.job_id) is None
