"""Frozen DAILY07-R01..R09 scenarios through real synthetic runtime boundaries."""
from dataclasses import replace
from datetime import timedelta
import json,sqlite3
from threading import Thread,Event
import pytest
from tests.pai_runtime_fixtures import pai,allow,request
from tests.test_daily_github_context import private_reader
from tests.test_daily_research import setup,Reader
from tests.test_daily_brief_editorial import runtime,rows
from tests.test_daily_projects import setup as project_setup,context
from prm.runtime.research import DurableResearchWorker,LocalArchiveReader
from prm.capabilities import CapabilityDenied
from prm.storage.postgres import StorageError,StateConflict


def test_r01_private_legacy_research_never_becomes_public(pai,monkeypatch):
    provider,_,_,_=private_reader(pai,monkeypatch);pai.root.github_context_provider=provider
    worker=DurableResearchWorker(pai.root)
    worker.enqueue({'schema_version':1,'question':'retrieval cache','steps':[{'source':'github','query':'owner/repository'}],'max_tool_calls':3,'deadline_seconds':120},idempotency_key='r01_private_v1')
    value=pai.root.queue.store.get(pai.root.owner_ref,'result',worker.run_once()).payload
    assert value['data_classes']==['private_connector_content'] and value['data_class']=='private_connector_content' and not pai.requests


def test_r02_disconnect_waits_for_bounded_http_credential_lease(pai,monkeypatch):
    from prm.runtime import web
    provider,manager,actor,state=private_reader(pai,monkeypatch)
    original=web._https_get;entered=Event();release=Event();revoked=Event();outcomes=[]
    def http(url,**kwargs):
        if '/contents/' in url:entered.set();assert release.wait(5)
        return original(url,**kwargs)
    monkeypatch.setattr(web,'_https_get',http)
    def read():
        try:outcomes.append(provider.read_repository_context('owner/repository'))
        except CapabilityDenied:outcomes.append('denied_after_read')
    worker=Thread(target=read);worker.start();assert entered.wait(5)
    def revoke():manager.revoke(connection_ref=provider.connection_ref,**actor);revoked.set()
    revoker=Thread(target=revoke);revoker.start()
    assert not revoked.wait(.15)
    release.set();worker.join(5);revoker.join(5)
    assert not worker.is_alive() and not revoker.is_alive() and revoked.is_set()
    count=len(state['calls'])
    with pytest.raises(CapabilityDenied):provider.read_repository_context('owner/repository')
    assert len(state['calls'])==count


def native_job(pai,index):
    root=pai.root;worker,_,_=setup(pai,Reader(second='Retrieval cache is documented here.'))
    ack=root.ingress.receive({'update_id':index,'message':{'message_id':770,'chat':{'id':42,'type':'private'},'from':{'id':42},'text':'Глубоко исследуй retrieval cache'}})
    response=root.queue.store.get(root.owner_ref,'result',root.worker().run_once()).payload
    ref=worker.run_once()
    return worker,ref


def edit_original(pai,index):
    pai.root.ingress.receive({'update_id':index,'edited_message':{'message_id':770,'chat':{'id':42,'type':'private'},'from':{'id':42},'text':'Edited original research question'}})


def test_r03_original_edit_denies_continuation_at_intake(pai):
    worker,ref=native_job(pai,142030);item=pai.root.queue.store.get(pai.root.owner_ref,'result',ref)
    edit_original(pai,142031);calls=list(pai.root.deep_archive_reader.calls)
    with pytest.raises(StorageError):worker.continue_result(result_ref=ref,version=1,digest=item.digest,idempotency_key='r03_after_edit')
    assert pai.root.deep_archive_reader.calls==calls


def test_r03_original_edit_after_continuation_intake_denies_claim(pai):
    worker,ref=native_job(pai,142032);item=pai.root.queue.store.get(pai.root.owner_ref,'result',ref)
    job=worker.continue_result(result_ref=ref,version=1,digest=item.digest,idempotency_key='r03_before_edit')
    calls=list(pai.root.deep_archive_reader.calls);edit_original(pai,142033)
    assert worker.run_once() is None and pai.root.deep_archive_reader.calls==calls
    assert pai.root.queue.status(owner=pai.root.owner_ref,job_id=job)['status']=='quarantined'


def test_r04_unknown_prepared_read_cannot_get_new_operation_ids(pai):
    worker,plan,_=setup(pai);job=worker.enqueue(plan,idempotency_key='r04_unknown')
    ref='research_step_'+job+'_0'
    pai.root.queue.store.put(pai.root.owner_ref,'result',ref,{'ref':ref,'source':'archive','status':'read_prepared','tool_calls':1,'evidence':{},'wave':0},expected_version=0)
    item=pai.root.queue.store.get(pai.root.owner_ref,'result',worker.run_once())
    with pytest.raises(StateConflict):worker.continue_result(result_ref=item.object_id,version=1,digest=item.digest,idempotency_key='r04_forbidden_retry')
    assert not pai.root.deep_archive_reader.calls


def test_r05_local_headline_and_truncation_preserve_qualifiers(pai):
    items=rows(pai,1)
    items[0].update(title='Guaranteed refund',support_span='The refund request '+('has been discussed in the current review process ' * 8)+'but no refund has been approved.',importance='critical')
    document=runtime(pai,items).build(topic='Refund',timezone_name='UTC',end_at=pai.now)
    story=document.editorial.stories[0]
    assert story.title!='Guaranteed refund' and 'Краткая формулировка не подтверждена' in story.summary
    assert 'no refund has been approved' in document.evidence[0].summary


@pytest.mark.parametrize('support',['Critical source includes https://primary.example.test/detail and conditions.',
                                   'Critical source includes <details> and conditions.', 'https://primary.example.test/detail'])
def test_r08_required_event_with_url_or_markup_never_becomes_quiet_week(pai,support):
    from prm.briefs import render_brief_document
    items=rows(pai,1);items[0].update(support_span=support,importance='critical')
    document=runtime(pai,items).build(topic='Critical',timezone_name='UTC',end_at=pai.now)
    assert document.editorial.stories or 'editorial_required_event_unrepresented' in document.coverage_manifest.limitations
    assert 'важных изменений по теме не найдено' not in render_brief_document(document)


def native_project_brief(pai):
    from tests.test_archive_search import _make_connection,_insert_post
    root,actor,source=project_setup(pai)
    text='Retrieval cache proves one bounded workflow'
    conn=_make_connection();_insert_post(conn,post_id=1,content=text,posted_at=(pai.now-timedelta(hours=1)).isoformat());conn.commit()
    path=pai.path/'canonical-project.sqlite'
    with sqlite3.connect(path) as disk:conn.backup(disk)
    conn.close();root.settings=type('Settings',(),{'db_path':str(path)})()
    root.deep_archive_reader=LocalArchiveReader(path,root=root)
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request')
    allow(pai,'model.context_egress',root.archive_resource_ref,'private_archive','research.synthesis.archive')
    worker=DurableResearchWorker(root);worker.enqueue({'schema_version':2,'question':'retrieval cache','steps':[{'source':'archive','query':'retrieval cache'}],
        'gap_steps':[],'coverage_terms':['retrieval','cache'],'max_tool_calls':1,'deadline_seconds':120},idempotency_key='r06_native_source')
    evidence=root.queue.store.get(root.owner_ref,'result',worker.run_once())
    assert text in evidence.payload['text']
    c=context(pai,source);c['relationships']=[{'evidence_ref':evidence.object_id,'evidence_version':1,'evidence_digest':evidence.digest,'quote':text,
        'relation':'Supports the current goal','experiment':'One local fixture run','reject_if':'Measured behavior differs'}]
    p=root.projects.preview(object_ref='project_aurora',context=c,**actor);project=root.memory.confirm(p,**actor)
    from prm.runtime.brief import BriefSourceHook,BriefRuntime
    from prm.capabilities import AuthorizationRequest
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','brief.archive',provider='provider_local',connection=None,operation='read')
    scope=AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,capability='archive.read',resource_ref=root.archive_resource_ref,operation='read',data_class='private_archive',provider_ref='provider_local',purpose='brief.archive')
    value=BriefRuntime(root,source_hooks=(BriefSourceHook(scope.resource_ref,scope,root.deep_archive_reader.enumerate_window,0),),editorial=lambda doc:None)
    return root,value,project,c,actor,path


def test_r06_native_canonical_archive_projects_use_exact_identity_and_version(pai):
    root,value,project,_,_,path=native_project_brief(pai)
    document=value.build(topic='Workflow',timezone_name='UTC',end_at=pai.now)
    assert 'Aurora' in document.editorial.stories[0].why_selected and document.editorial.stories[0].next_step.startswith('Возможный эксперимент')
    with sqlite3.connect(path) as conn:conn.execute("UPDATE posts SET content='Retrieval cache now describes another workflow.' WHERE id=1")
    changed=value.build(topic='Workflow',timezone_name='UTC',end_at=pai.now)
    assert 'Aurora' not in changed.editorial.stories[0].why_selected


def test_r07_saved_project_binding_revalidates_after_restart_and_replacement(pai):
    root,value,project,c,actor,_=native_project_brief(pai)
    answer=value.answer(topic='Workflow',timezone_name='UTC',end_at=pai.now)
    from prm.conversation import conversation_id_for
    binding=root.briefs.store.get(root.owner_ref,'conversation',root.briefs._binding_ref(conversation_id_for('42'))).payload
    manifest=root.briefs.store.get(root.owner_ref,'result',root.briefs._document_ref(binding['brief_id']),version=1)
    assert manifest.payload['project_bindings']==[{'project_ref':project.object_id,'version':1,'digest':project.digest}]
    c['descriptor']['current_goal']='Changed current goal'
    p=root.projects.preview(object_ref=project.object_id,context=c,expected_version=1,**actor);root.memory.confirm(p,**actor)
    from prm.storage.briefs import DurableBriefStore
    root.briefs=DurableBriefStore(pai.pg.app,owner_ref=root.owner_ref,registry=root.registry)
    with pytest.raises(CapabilityDenied):root.briefs._decode_document(manifest)
    with pytest.raises(CapabilityDenied):value.materials(brief_id=binding['brief_id'],version=1)
    from prm.runtime.source_access import result_provenance
    with root.queue.store.transaction() as tx:
        item=tx.get(root.owner_ref,'result',answer.payload['conversation']['response_refs'][0])
        with pytest.raises(CapabilityDenied):result_provenance(tx,root.owner_ref,item)
        from prm.runtime.delivery import DeliveryExecutor
        delivery=DeliveryExecutor(root.queue.store.target,registry=root.registry,sender=lambda *a:None)
        with pytest.raises(CapabilityDenied):delivery._source_current(tx,root.owner_ref,{'result_ref':item.object_id,'result_digest':item.digest,'source_scopes':[]})
    from prm.runtime.reader import PrivateReportRuntime
    reader=PrivateReportRuntime(root,artifact_root=pai.path/'r07-artifacts');token=reader.issue_session(**actor)
    assert reader.artifact(token,brief_id=binding['brief_id'],version=1,format='html') is None


def test_r07_matching_saved_version_also_rejects_expired_context(pai):
    root,actor,source=project_setup(pai)
    c=context(pai,source,reviewed_at=(pai.now-timedelta(days=2)).isoformat(),expires_at=(pai.now-timedelta(days=1)).isoformat())
    preview=root.projects.preview(object_ref='project_aurora',context=c,**actor);item=root.memory.confirm(preview,**actor)
    from prm.runtime.source_access import project_bindings_current
    with root.queue.store.transaction() as tx:
        with pytest.raises(CapabilityDenied):project_bindings_current(tx,root.owner_ref,[{'project_ref':item.object_id,'version':item.version,'digest':item.digest}])


def test_r09_omitted_stories_are_new_on_next_week_and_inventory_labels_differ(pai):
    value=runtime(pai,rows(pai));value.answer(topic='Protocol',timezone_name='UTC',end_at=pai.now)
    document=value.build(topic='Protocol',timezone_name='UTC',end_at=pai.now)
    events=pai.root.briefs.pending_events[document.content_digest]['events']
    assert sum(e['novelty']=='new' for e in events)==2
    inventory=pai.root.briefs.pending_inventory[document.content_digest]
    assert any(r['packet_selected'] and not r['selected'] for r in inventory)


@pytest.mark.parametrize('location',['ninth_record','after_span_bound'])
def test_r10_coverage_uses_actual_bounded_answer_packet(pai,location):
    class PacketReader(Reader):
        def search_archive(self,query,*,limit):
            self.calls.append(query)
            if query!='retrieval':return {'items':[{'evidence_id':'gap','source_url':'https://t.me/synthetic/gap','support_span':'Cache is documented here.','source_version':'v1'}]}
            texts=['Retrieval is documented here.']*9 if location=='ninth_record' else ['Retrieval '+('padding '*170)+'cache']
            if location=='ninth_record':texts[-1]='Cache is documented here.'
            return {'items':[{'evidence_id':'first_'+str(i),'source_url':'https://t.me/synthetic/'+str(i),'support_span':t,'source_version':'v1'} for i,t in enumerate(texts)]}
    worker,plan,_=setup(pai,PacketReader());worker.enqueue(plan,idempotency_key='r10_'+location)
    value=pai.root.queue.store.get(pai.root.owner_ref,'result',worker.run_once()).payload
    assert pai.root.deep_archive_reader.calls==['retrieval','cache'] and value['tool_calls']==2
    assert value['coverage']['sufficient'] and 'https://t.me/synthetic/gap' in value['answer_payload']['source_refs']
