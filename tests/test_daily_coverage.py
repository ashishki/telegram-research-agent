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
