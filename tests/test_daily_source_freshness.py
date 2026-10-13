"""Selected canonical ingestion/edits/deletes/cursor/quota and source serving guards."""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
from pathlib import Path
import sqlite3,pytest,json
from tests.pai_runtime_fixtures import pai,allow,request
from ingestion.selected_archive import ArchiveSelection,SelectedArchive,install_selected_archive
from prm.storage.postgres import StorageError,StateConflict
from prm.runtime.research import LocalArchiveReader,DurableResearchWorker


def setup(pai,mode='import',**limits):
    root=pai.root;path=pai.path/'selected-archive.sqlite'
    conn=sqlite3.connect(path);conn.executescript(Path('src/db/schema.sql').read_text());install_selected_archive(conn)
    selection=ArchiveSelection(root.owner_ref,root.archive_resource_ref,1,((1,'@synthetic'),),mode=mode,**limits)
    archive=SelectedArchive(conn,selection);archive.register();root.settings.db_path=path;root.archive_selection=selection
    from prm.runtime.archive import selected_source_guard,SelectedArchiveRuntime
    root.registry.selected_source_guard=lambda owner,scopes,**kwargs:selected_source_guard(root,owner,scopes,**kwargs)
    root.selected_archive=SelectedArchiveRuntime(root);root.services['archive']=root.selected_archive.service
    return root,conn,archive


def event(pai,revision=1,text='Synthetic source experiment',deleted=False,channel_id=1,message_id=1):
    return {'channel_id':channel_id,'message_id':message_id,'revision':revision,'posted_at':(pai.now-timedelta(hours=1)).isoformat(),'text':text,'deleted':deleted}


def page(pai,events,**changes):return {'page_id':'page1','expected_cursor':None,'next_cursor':None,'events':events,'watermark':pai.now.isoformat(),'complete':True,**changes}


def test_atomic_import_duplicate_cursor_edits_deletes_keep_canonical_ids_and_no_enrichment(pai):
    root,conn,archive=setup(pai)
    packet=page(pai,[event(pai)])
    assert archive.apply_page(**packet)['changed']==1
    ids=conn.execute('SELECT p.id,r.id FROM posts p JOIN raw_posts r ON r.id=p.raw_post_id').fetchone()
    assert archive.apply_page(**packet)['changed']==1 and conn.execute('SELECT used FROM pa_archive_quota').fetchone()[0]==1
    reader=LocalArchiveReader(root.settings.db_path,root=root)
    assert reader.search_archive('Synthetic',limit=8)['source_count']==1
    archive.apply_page(**page(pai,[event(pai,revision=2,text='Edited synthetic source')],page_id='page2'))
    assert conn.execute('SELECT p.id,r.id FROM posts p JOIN raw_posts r ON r.id=p.raw_post_id').fetchone()==ids
    assert reader.search_archive('Edited',limit=8)['source_count']==1
    archive.apply_page(**page(pai,[event(pai,revision=3,text='',deleted=True)],page_id='page3'))
    assert reader.search_archive('Edited',limit=8)['source_count']==0
    archive.apply_page(**page(pai,[event(pai,revision=2,text='Edited synthetic source')],page_id='page4'))
    assert conn.execute('SELECT content FROM posts').fetchone()[0]==''
    assert conn.execute('SELECT count(*) FROM knowledge_atoms').fetchone()[0]==0
    assert not archive.status()['history_complete']
    conn.close()


def test_selected_filters_apply_before_topk_window_and_reaction_count(pai):
    root,conn,archive=setup(pai,mode='session')
    archive.apply_page(**page(pai,[event(pai)]))
    other=SelectedArchive(conn,replace(archive.selection,resource_ref='resource_other',channels=((2,'@unselected'),)));other.register()
    other.apply_page(**page(pai,[event(pai,channel_id=2,message_id=2)]))
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    reader=LocalArchiveReader(root.settings.db_path,root=root);result=reader.search_archive('Synthetic',limit=8)
    assert result['source_count']==1 and result['items'][0]['channel_username']=='@synthetic' and result['source_freshness']['fresh']
    from prm.briefs import BriefWindow
    batch=reader.window_evidence(BriefWindow('UTC',pai.now-timedelta(days=7),pai.now,pai.now))
    assert batch.received_count==1 and batch.selected_resources[0].scope_digest==archive.selection.digest
    from ingestion.reaction_sync import _load_candidate_posts_with_count
    conn.row_factory=sqlite3.Row
    rows,count=_load_candidate_posts_with_count(conn,days=7,limit=200,channel_usernames=('@synthetic',))
    assert count==len(rows)==1
    conn.close()


def test_conflicting_page_cursor_quota_and_future_watermark_fail_without_partial_writes(pai):
    root,conn,archive=setup(pai,daily_quota=1)
    archive.apply_page(**page(pai,[event(pai)],next_cursor='next',complete=False))
    with pytest.raises(StateConflict):archive.apply_page(**page(pai,[event(pai,revision=2)],page_id='cursor_bad'))
    with pytest.raises(StorageError):archive.apply_page(**page(pai,[event(pai,message_id=2)],page_id='quota_bad',expected_cursor='next'))
    with pytest.raises(StorageError):archive.apply_page(**page(pai,[],page_id='future',watermark=(pai.now+timedelta(days=1)).isoformat(),expected_cursor='next'))
    with pytest.raises(StateConflict):archive.apply_page(**page(pai,[event(pai,text='Changed page')],next_cursor='next',complete=False))
    assert archive.current()['cursor']=='next' and conn.execute('SELECT count(*) FROM raw_posts').fetchone()[0]==1
    conn.close()


def test_partial_outage_old_watermark_and_forward_never_claim_full_history(pai):
    root,conn,archive=setup(pai,mode='session')
    archive.apply_page(**page(pai,[event(pai)],next_cursor='next',complete=False))
    assert not archive.status()['fresh']
    archive.outage();assert archive.current()['outcome']=='unavailable' and archive.current()['watermark']==pai.now.isoformat()
    assert not archive.status()['fresh']
    archive.apply_page(**page(pai,[],page_id='finished',expected_cursor='next'))
    assert archive.status()['fresh'] and not archive.status(pai.now+timedelta(days=3))['fresh']
    conn.close()


def test_separate_owner_import_write_scope_and_native_freshness_status(pai):
    root,conn,archive=setup(pai);actor={'chat_id':'42','actor_id':'42','owner_chat_id':'42'}
    from prm.capabilities import CapabilityDenied
    with pytest.raises(CapabilityDenied):root.selected_archive.import_page(packet=page(pai,[event(pai)]),**actor)
    allow(pai,'archive.ingest',root.archive_resource_ref,'private_archive','archive.import',provider='provider_local',connection=None,operation='write')
    assert root.selected_archive.import_page(packet=page(pai,[event(pai)]),**actor)['changed']==1
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','archive.status',provider='provider_local',connection=None,operation='read')
    _,output=request(pai,122000,'/archives')
    assert output['payload']['source_freshness']['mode']=='import' and not output['payload']['source_freshness']['history_complete']
    assert not pai.requests
    conn.close()


def test_pause_blocks_cached_retrieval_stored_focus_and_final_research_delivery(pai):
    root,conn,archive=setup(pai);archive.apply_page(**page(pai,[event(pai)]))
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    reader=LocalArchiveReader(root.settings.db_path,root=root);assert reader.search_archive('Synthetic',limit=8)['source_count']==1
    worker=DurableResearchWorker(root);job=worker.enqueue({'schema_version':1,'question':'Synthetic','steps':[{'source':'archive','query':'Synthetic'}],'max_tool_calls':1,'deadline_seconds':60},idempotency_key='daily_selected_pause')
    result=worker.run_once();item=root.queue.store.get(root.owner_ref,'result',result)
    assert item.payload['source_freshness'][0]['mode']=='import'
    archive.pause()
    with pytest.raises(StorageError):reader.search_archive('Synthetic',limit=8)
    with pytest.raises(StorageError):root.focus.resolve({'target':{'result_ref':result,'result_version':1}},guard=lambda:None)
    from prm.runtime.delivery import DeliveryExecutor
    allow(pai,'assistant.result_delivery','destination_source_pause','private_archive','answer.delivery',provider='provider_telegram',connection=None,operation='deliver')
    calls=[];executor=DeliveryExecutor(root.queue.store.target,registry=root.registry,sender=lambda *args:calls.append(args))
    assert executor.deliver_result(owner=root.owner_ref,job_id=job,destination_ref='destination_source_pause',upper_bound=0)['status']=='unknown' and not calls
    conn.close()


def test_native_session_page_and_known_id_delete_preserve_publication_and_fence_outage(pai):
    from types import SimpleNamespace
    from ingestion.selected_archive import TelegramSelectedCollector
    root,conn,archive=setup(pai,mode='session');calls=[]
    original=pai.now-timedelta(hours=1)
    message=SimpleNamespace(id=1,peer_id=SimpleNamespace(channel_id=1),date=original,edit_date=None,message='Synthetic native selected source',photo=None,video=None,document=None,fwd_from=None,views=1)
    class Client:
        async def get_me(self):calls.append('me');return SimpleNamespace(id=42)
        async def get_entity(self,name):calls.append(name);return SimpleNamespace(id=1)
        def iter_messages(self,entity,**kwargs):
            async def values():yield message
            return values()
        async def get_messages(self,entity,ids):return [None]
    collector=TelegramSelectedCollector(Client());actor={'chat_id':'42','actor_id':'42','owner_chat_id':'42'}
    allow(pai,'archive.session_read',root.archive_resource_ref,'private_archive','archive.sync',provider='provider_telegram',connection='connection_selected_session',operation='read')
    allow(pai,'archive.ingest',root.archive_resource_ref,'private_archive','archive.sync',provider='provider_local',connection=None,operation='write')
    output=root.selected_archive.collect_page(collector,connection_ref='connection_selected_session',**actor)
    assert output['status']=='committed' and not output['full_history_verified']
    assert conn.execute('SELECT posted_at FROM raw_posts').fetchone()[0]==original.isoformat()
    deleted=root.selected_archive.collect_page(collector,connection_ref='connection_selected_session',known_ids=(1,),**actor)
    assert deleted['status']=='committed' and conn.execute('SELECT posted_at FROM raw_posts').fetchone()[0]==original.isoformat()
    assert conn.execute('SELECT content FROM posts').fetchone()[0]==''
    class LostClient(Client):
        async def get_me(self):calls.append('lost');raise TimeoutError('Synthetic read ACK loss')
    bad=TelegramSelectedCollector(LostClient())
    with pytest.raises(Exception):root.selected_archive.collect_page(bad,connection_ref='connection_selected_session',known_ids=(2,),**actor)
    before=len(calls)
    assert root.selected_archive.collect_page(bad,connection_ref='connection_selected_session',known_ids=(2,),**actor)['status']=='source_outcome_unknown' and len(calls)==before
    assert archive.current()['outcome']=='unavailable' and not pai.requests
    conn.close()


def test_selected_source_read_lock_is_held_through_pg_guard_and_released_on_exit(pai):
    import fcntl
    from prm.runtime.source_access import source_current
    from prm.capabilities import AuthorizationRequest
    from dataclasses import asdict
    root,conn,archive=setup(pai);archive.apply_page(**page(pai,[event(pai)]))
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    scope=asdict(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,capability='archive.read',resource_ref=root.archive_resource_ref,operation='read',data_class='private_archive',provider_ref='provider_local',purpose='research.archive'))
    with open(root.settings.db_path,'rb') as other:
        with root.queue.store.transaction() as tx:
            source_current(tx,root.registry,root.owner_ref,[scope])
            with pytest.raises(BlockingIOError):fcntl.flock(other.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        fcntl.flock(other.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(other.fileno(),fcntl.LOCK_UN)
    conn.close()


def test_canonical_tombstone_is_global_across_overlapping_resource_scopes(pai):
    root,conn,archive=setup(pai)
    archive.apply_page(**page(pai,[event(pai,revision=3,deleted=True,text='')]))
    other=SelectedArchive(conn,replace(archive.selection,resource_ref='resource_other'));other.register()
    other.apply_page(**page(pai,[event(pai,revision=2,text='Synthetic resurrection attempt')]))
    assert conn.execute('SELECT content FROM posts').fetchone()[0]==''
    conn.close()


def test_ordinary_native_research_cannot_egress_unselected_archive_channel(pai):
    root,conn,archive=setup(pai)
    archive.apply_page(**page(pai,[event(pai,text='Synthetic SELECTED CANARY experiment')]))
    other=SelectedArchive(conn,replace(archive.selection,resource_ref='resource_other',channels=((2,'@unselected'),)));other.register()
    other.apply_page(**page(pai,[event(pai,text='Synthetic UNSELECTED CANARY experiment',channel_id=2,message_id=2)]))
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request')
    allow(pai,'model.context_egress',root.archive_resource_ref,'private_archive','answer.context')
    _,output=request(pai,122300,'/research Найди в Telegram Synthetic experiment')
    packet=json.dumps(pai.requests,ensure_ascii=False)
    assert 'UNSELECTED CANARY' not in packet and 'UNSELECTED CANARY' not in output['text']
    assert output['payload']['source_scopes']
    conn.close()


def test_reused_username_cannot_admit_unselected_channel_id(pai):
    root,conn,archive=setup(pai);archive.apply_page(**page(pai,[event(pai)]))
    other=SelectedArchive(conn,replace(archive.selection,resource_ref='resource_other',channels=((2,'@synthetic'),)));other.register()
    other.apply_page(**page(pai,[event(pai,channel_id=2,message_id=2)],page_id='other'))
    result=LocalArchiveReader(root.settings.db_path,root=root).search_archive('Synthetic',limit=8)
    assert result['source_count']==1 and result['items'][0]['channel_id']==1
    conn.close()


def test_saved_research_snapshot_is_blocked_after_canonical_edit_and_outage(pai):
    root,conn,archive=setup(pai,mode='session');archive.apply_page(**page(pai,[event(pai)]))
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    worker=DurableResearchWorker(root);job=worker.enqueue({'schema_version':1,'question':'Synthetic','steps':[{'source':'archive','query':'Synthetic'}],'max_tool_calls':1,'deadline_seconds':60},idempotency_key='stale_snapshot')
    ref=worker.run_once();ticket={'target':{'result_ref':ref,'result_version':1}}
    archive.apply_page(**page(pai,[event(pai,revision=2,text='Changed private source')],page_id='edited'))
    with pytest.raises(StorageError):root.focus.resolve(ticket,guard=lambda:None)
    from prm.runtime.delivery import DeliveryExecutor
    allow(pai,'assistant.result_delivery','destination_changed','private_archive','answer.delivery',provider='provider_telegram',connection=None,operation='deliver')
    calls=[];executor=DeliveryExecutor(root.queue.store.target,registry=root.registry,sender=lambda *args:calls.append(args))
    assert executor.deliver_result(owner=root.owner_ref,job_id=job,destination_ref='destination_changed',upper_bound=0)['status']=='unknown' and not calls
    conn.close()


def test_historical_observation_dates_do_not_reset_today_import_quota(pai):
    root,conn,archive=setup(pai,daily_quota=1)
    first=pai.now-timedelta(days=3);second=pai.now-timedelta(days=2)
    a=event(pai);a['posted_at']=(first-timedelta(hours=1)).isoformat()
    archive.apply_page(**page(pai,[a],checked_at=first.isoformat(),watermark=first.isoformat()))
    b=event(pai,message_id=2);b['posted_at']=(second-timedelta(hours=1)).isoformat()
    with pytest.raises(StorageError):archive.apply_page(**page(pai,[b],page_id='historical2',checked_at=second.isoformat(),watermark=second.isoformat()))
    assert conn.execute('SELECT day,used FROM pa_archive_quota').fetchone()==(datetime.now(timezone.utc).date().isoformat(),1)
    conn.close()


def test_saved_snapshot_outage_and_delete_prevent_model_synthesis_and_raw_alias_serving(pai):
    from prm.runtime.research import DurableResearchWorker
    root,conn,archive=setup(pai,mode='session');archive.apply_page(**page(pai,[event(pai)]))
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request')
    allow(pai,'model.context_egress',root.archive_resource_ref,'private_archive','research.synthesis.archive')
    class ChangingWorker(DurableResearchWorker):
        def _gather(self,*args):
            step=super()._gather(*args)
            with sqlite3.connect(root.settings.db_path) as updated:SelectedArchive(updated,archive.selection).outage()
            return step
    worker=ChangingWorker(root)
    worker.enqueue({'schema_version':1,'question':'Synthetic','steps':[{'source':'archive','query':'Synthetic'}],'max_tool_calls':1,'deadline_seconds':60},idempotency_key='post_read_outage')
    ref=worker.run_once();assert not pai.requests and root.queue.store.get(root.owner_ref,'result',ref).payload['status']=='partial'
    archive.apply_page(**page(pai,[],page_id='recovered'))
    _,answer=request(pai,122500,'/research Найди в Telegram Synthetic')
    aliases=answer['payload']['conversation']['response_refs'];before=len(pai.requests)
    archive.apply_page(**page(pai,[event(pai,revision=2,deleted=True,text='')],page_id='deleted_after_answer'))
    with pytest.raises(StorageError):root.focus.resolve({'target':{'result_ref':aliases[0],'result_version':1}},guard=lambda:None)
    assert len(pai.requests)==before
    conn.close()


def test_selected_window_and_reactions_filter_exact_identity_and_watch_carries_snapshot(pai):
    from prm.briefs import BriefWindow
    from ingestion.reaction_sync import _load_candidate_posts_with_count
    from prm.runtime.watch import wire_archive_watch
    from types import SimpleNamespace
    root,conn,archive=setup(pai);archive.apply_page(**page(pai,[event(pai)]))
    other=SelectedArchive(conn,replace(archive.selection,resource_ref='resource_other',channels=((2,'@synthetic'),)));other.register();other.apply_page(**page(pai,[event(pai,channel_id=2,message_id=2)],page_id='other'))
    batch=LocalArchiveReader(root.settings.db_path,root=root).window_evidence(BriefWindow('UTC',pai.now-timedelta(days=1),pai.now,pai.now))
    assert batch.received_count==1 and batch.watermark in archive.status()['archive_snapshots']
    conn.row_factory=sqlite3.Row
    rows,count=_load_candidate_posts_with_count(conn,7,200,channel_identities=archive.selection.channels)
    assert len(rows)==count==1
    wire_archive_watch(root)
    note=root.watch_collector.collector(root.archive_resource_ref,SimpleNamespace(timezone_name='UTC',subscription_id='watch_'+('a'*32)))
    assert len(note)==1 and note[0].archive_snapshots==tuple(archive.status()['archive_snapshots'])
    conn.close()


def test_private_reader_rechecks_source_snapshot_after_render_before_read(pai,monkeypatch):
    from dataclasses import asdict
    from prm.briefs import BriefBuildRequest,CoverageSource,build_brief_document
    from prm.capabilities import AuthorizationRequest
    from prm.runtime.reader import PrivateReportRuntime
    from tests.test_assistant_briefs import _window,_evidence
    import prm.runtime.reader as reader_module
    root,conn,archive=setup(pai,mode='session');archive.apply_page(**page(pai,[event(pai)]))
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','brief.archive',provider='provider_local',connection=None,operation='read')
    scope=asdict(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,capability='archive.read',resource_ref=root.archive_resource_ref,
        operation='read',data_class='private_archive',provider_ref='provider_local',purpose='brief.archive'))
    document=build_brief_document(BriefBuildRequest('Synthetic private report',_window(),
        (_evidence('event_1','https://example.test/event',title='Private source',summary='OLD PRIVATE SOURCE'),),
        owner_ref=root.owner_ref,coverage=(CoverageSource('source_synthetic','checked'),)))
    root.briefs.pending_classes[document.content_digest]=('private_archive',)
    root.briefs.pending_scopes[document.content_digest]=[scope]
    root.briefs.pending_snapshots={document.content_digest:archive.status()['archive_snapshots']}
    state=root.conversations.record_response('42',text='Synthetic report',topic='')
    root.briefs.bind_visible(conversation_id=state.conversation_id,response_ref=state.object_refs[0].response_ref,document=document,
        authenticated_chat_id='42',authenticated_actor_id='42',authenticated_owner_chat_id='42')
    reader=PrivateReportRuntime(root,artifact_root=pai.path/'reader')
    token=reader.issue_session(chat_id='42',actor_id='42',owner_chat_id='42')
    original=reader_module.subprocess.run;rendered=[]
    def outage_after_render(*args,**kwargs):
        result=original(*args,**kwargs)
        archive.outage();rendered.append(True)
        return result
    with monkeypatch.context() as patch:
        patch.setattr(reader_module.subprocess,'run',outage_after_render)
        result=reader.artifact(token,brief_id=document.brief_id,version=document.version,format='markdown')
    assert rendered==[True] and result is None
    conn.close()
