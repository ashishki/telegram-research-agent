"""Whole-week enumeration, fair ranked selection, exact inventory and periods."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import sqlite3,json
import pytest
from tests.pai_runtime_fixtures import pai,allow,request
from tests.test_archive_search import _make_connection,_insert_post
from prm.briefs import BriefWindow
from prm.capabilities import AuthorizationRequest,CapabilityDenied
from prm.runtime.brief import BriefRuntime,BriefSourceHook,brief_window
from prm.runtime.research import LocalArchiveReader
from prm.runtime.memory import MemoryRuntime
from prm.source_contracts import SourceResource,SourceBatch
from prm.storage.postgres import StorageError


def archive_file(pai,count=200):
    conn=_make_connection();start=pai.now-timedelta(days=7)
    for i in range(count):_insert_post(conn,post_id=i+1,posted_at=(start+timedelta(hours=1,minutes=i)).isoformat(),
        content='Security advisory: incompatible protocol change.' if i==0 else 'Synthetic weekly material '+str(i))
    path=pai.path/'weekly.sqlite';conn.commit()
    with sqlite3.connect(path) as saved:conn.backup(saved)
    conn.close();return path


def builder(pai,path):
    root=pai.root;reader=LocalArchiveReader(path,root=root)
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','brief.archive',provider='provider_local',connection=None,operation='read')
    archive_scope=AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,capability='archive.read',resource_ref=root.archive_resource_ref,
        operation='read',data_class='private_archive',provider_ref='provider_local',purpose='brief.archive')
    allow(pai,'fixture.mail','resource_late_mail','private_connector_metadata','brief.fixture_mail',provider='provider_local',connection=None,operation='read')
    scope=AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,capability='fixture.mail',resource_ref='resource_late_mail',
        operation='read',data_class='private_connector_metadata',provider_ref='provider_local',purpose='brief.fixture_mail')
    row={'evidence_id':'late_mail','source_url':'https://mail.example.test/later','support_span':'Synthetic late source obligation.',
        'title':'Late small source','posted_at':(pai.now-timedelta(hours=1)).isoformat(),'source_version':'v1','local_source_provenance':True,
        'source_owner_ref':root.owner_ref,'source_kind':'mail','importance':'medium'}
    def collect(window):return SourceBatch.from_items([row],SourceResource(root.owner_ref,scope.resource_ref,'mail',scope.data_class),checked_at=pai.now,completeness='complete',omitted_count=0)
    return BriefRuntime(root,source_hooks=(BriefSourceHook(root.archive_resource_ref,archive_scope,reader.enumerate_window,0),BriefSourceHook(scope.resource_ref,scope,collect,0)),editorial=lambda doc:None)


def test_native_week_selects_early_important_and_late_small_source_and_persists_inventory(pai):
    root=pai.root;runtime=builder(pai,archive_file(pai));root.attach_local_services(brief_runtime=runtime,memory_runtime=MemoryRuntime(root))
    _,answer=request(pai,124000,'Собери обзор недели Synthetic')
    coverage=answer['payload']['source_coverage']
    assert coverage['enumeration_received_count']==coverage['received_count']==201 and coverage['selected_count']==20 and coverage['model_omitted_count']==181
    assert 'Security advisory' in answer['text'] and 'Synthetic late source obligation' in answer['text']
    from prm.conversation import conversation_id_for
    binding=root.briefs.store.get(root.owner_ref,'conversation',root.briefs._binding_ref(conversation_id_for('42'))).payload
    ref=root.briefs._document_ref(binding['brief_id']);manifest=root.briefs.store.get(root.owner_ref,'result',ref,version=1)
    assert sum(p['count'] for p in manifest.payload['material_pages'])==201 and len(manifest.payload['material_pages'])>1
    _,view=request(pai,124001,'/briefmaterials '+binding['brief_id']+' 1 180')
    assert view['status']=='read' and view['payload']['inventory_count']==201
    assert set(view['payload']['source_data_classes'])=={'private_archive','private_connector_metadata'}
    assert all('support_span' not in r and 'encoded_payload' not in r for r in view['payload']['materials']) and not pai.requests
    from prm.storage.briefs import DurableBriefStore
    root.briefs=DurableBriefStore(pai.pg.app,owner_ref=root.owner_ref,registry=root.registry)
    assert runtime.materials(brief_id=binding['brief_id'],version=1,offset=180)['inventory_count']==201
    from prm.runtime.deletion import delete_derived_in
    with root.queue.store.transaction() as tx:delete_derived_in(tx,owner=root.owner_ref,namespace='result',object_ref=ref)
    assert all(root.queue.store.get(root.owner_ref,'result',p['ref']) is None for p in manifest.payload['material_pages'])
    with pytest.raises(StorageError):runtime.materials(brief_id=binding['brief_id'],version=1)


def test_paginated_cap_and_half_open_unknown_late_and_removed_publication(pai):
    path=archive_file(pai,220);window=BriefWindow('UTC',pai.now-timedelta(days=7),pai.now,pai.now)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE posts SET posted_at='' WHERE id=2")
        conn.execute('UPDATE raw_posts SET ingested_at=? WHERE id=102',((pai.now-timedelta(hours=1)).isoformat(),))
        conn.execute('UPDATE posts SET posted_at=? WHERE id=3',((pai.now-timedelta(days=20)).isoformat(),))
        conn.execute('UPDATE raw_posts SET ingested_at=? WHERE id=103',((pai.now-timedelta(hours=1)).isoformat(),))
        conn.execute("UPDATE posts SET content='' WHERE id=4")
        conn.execute('UPDATE posts SET posted_at=? WHERE id=5',(pai.now.isoformat(),))
    reader=LocalArchiveReader(path,root=pai.root);batch=reader.enumerate_window(window,page_size=32)
    assert len(batch)==218 and batch.completeness=='complete'
    unknown=next(r for r in batch.items if r.external_ref.endswith(':1002'))
    late=next(r for r in batch.items if r.external_ref.endswith(':1003'))
    assert unknown.publication_time is None and unknown.discovery_time is not None
    assert late.publication_time<window.start_at and window.contains(late.discovery_time)
    capped=reader.enumerate_window(window,maximum_items=80,page_size=32)
    assert len(capped)==80 and capped.omitted_count==138 and capped.reason=='enumeration_cap' and capped.continuation=='offset:80'


def test_inventory_rechecks_revocation_and_selected_snapshot_without_model(pai):
    from tests.test_daily_source_freshness import setup,event,page
    root,conn,archive=setup(pai,mode='session');archive.apply_page(**page(pai,[event(pai)]))
    scope=AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,capability='archive.read',resource_ref=root.archive_resource_ref,
        operation='read',data_class='private_archive',provider_ref='provider_local',purpose='brief.archive')
    grant=allow(pai,scope.capability,scope.resource_ref,scope.data_class,scope.purpose,provider='provider_local',connection=None,operation='read')
    runtime=BriefRuntime(root,source_hooks=(BriefSourceHook(scope.resource_ref,scope,LocalArchiveReader(root.settings.db_path,root=root).enumerate_window,0),),editorial=lambda doc:None)
    doc=runtime.build(topic='Synthetic',timezone_name='UTC',end_at=pai.now)
    state=root.conversations.record_response('42',text='Synthetic report',topic='')
    root.briefs.bind_visible(conversation_id=state.conversation_id,response_ref=state.object_refs[0].response_ref,document=doc,
        authenticated_chat_id='42',authenticated_actor_id='42',authenticated_owner_chat_id='42')
    assert runtime.materials(brief_id=doc.brief_id,version=1)['inventory_count']==1
    archive.outage()
    with pytest.raises(StorageError):runtime.materials(brief_id=doc.brief_id,version=1)
    root.registry.revoke_grant(grant.grant_id,owner_ref=root.owner_ref)
    with pytest.raises(CapabilityDenied):runtime.materials(brief_id=doc.brief_id,version=1)
    assert not pai.requests;conn.close()


def test_calendar_week_and_rolling_are_explicit_across_dst():
    moment=datetime(2026,10,26,12,tzinfo=timezone.utc)
    calendar=brief_window('Europe/Berlin',end_at=moment,period_mode='calendar_week',generated_at=moment)
    assert calendar.start_at.date().isoformat()=='2026-10-19' and calendar.end_at.date().isoformat()=='2026-10-26'
    assert (calendar.end_at.astimezone(timezone.utc)-calendar.start_at.astimezone(timezone.utc)).total_seconds()==169*3600
    rolling=brief_window('Europe/Berlin',end_at=moment,period_mode='rolling',generated_at=moment)
    assert (rolling.end_at.astimezone(timezone.utc)-rolling.start_at.astimezone(timezone.utc)).total_seconds()==168*3600
    assert calendar.contains(calendar.start_at) and not calendar.contains(calendar.end_at)
    with pytest.raises(StorageError):brief_window('UTC',period_mode='invented')


def test_empty_checked_week_has_zero_inventory_and_no_invented_events(pai):
    runtime=builder(pai,archive_file(pai,0));runtime.source_hooks=runtime.source_hooks[:1]
    document=runtime.build(topic='Synthetic empty',timezone_name='UTC',end_at=pai.now)
    assert not document.evidence and not pai.root.briefs.pending_inventory[document.content_digest]
    assert pai.root.briefs.pending_coverage[document.content_digest]['received_count']==0
    assert pai.root.briefs.pending_classes[document.content_digest]==('private_archive',) and pai.root.briefs.pending_scopes[document.content_digest]
