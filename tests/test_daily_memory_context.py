"""Native confirmed context, separate egress, correction/expiry/revoke/deletion."""
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
import time,pytest
from tests.daily08_fixtures import pai,allow,request,note
from prm.capabilities import AuthorizationRequest,CapabilityDenied
from prm.runtime.source_access import result_provenance,source_current
from prm.runtime.memory import MemoryRuntime


ACTOR=dict(chat_id='42',actor_id='42',owner_chat_id='42')


def grants(pai,*,memory=True):
    allow(pai,'model.generate',pai.root.model_resource_ref,'user_provided','answer.request')
    if memory:allow(pai,'model.context_egress','resource_memory','user_provided','dialogue.memory')


def model_context(pai):return '\n'.join(m['content'] for m in pai.requests[-1][2]['messages'] if m['role']=='user' and m['content'].startswith('Untrusted remembered context'))


def test_native_answer_recalls_relevant_confirmed_preference_and_excludes_json_metadata(pai):
    saved=note(pai,'For Python examples prefer short answers.',kind='preference')
    note(pai,'Tomatoes need daylight.',object_ref='memory_unrelated',source=pai.root.queue.store.put(pai.root.owner_ref,'conversation','source_python_metadata',{'query':'Owner unrelated gardening note'},expected_version=0))
    grants(pai);_,answer=request(pai,151001,'/chat Explain Python examples')
    assert saved.object_id in model_context(pai) and 'short answers' in model_context(pai) and 'Tomatoes' not in model_context(pai)
    assert answer['payload']['memory_context_refs']==[saved.object_id]
    found=pai.root.memory.search('Python examples',**ACTOR)
    assert [i.object_id for i in found]==[saved.object_id]


def test_memory_is_not_sent_without_separate_context_grant(pai):
    note(pai,'For Python examples prefer short answers.',kind='preference');grants(pai,memory=False)
    _,answer=request(pai,151010,'/chat Explain Python examples')
    assert not model_context(pai) and answer['payload']['memory_context_refs']==[]


def test_private_memory_needs_read_and_exact_resource_egress_and_revocation_blocks_saved_answer(pai):
    root=pai.root;root.attach_local_services(memory_runtime=MemoryRuntime(root))
    grant=allow(pai,'archive.read',root.archive_resource_ref,'private_archive','research.archive',provider='provider_local',connection=None,operation='read')
    scope=asdict(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,capability='archive.read',resource_ref=root.archive_resource_ref,
        operation='read',data_class='private_archive',provider_ref='provider_local',purpose='research.archive'))
    source=root.queue.store.put(root.owner_ref,'result','private_memory_proof',{'text':'Python private proof','data_classes':['private_archive'],'source_scopes':[scope]},expected_version=0)
    saved=note(pai,'Private Python constraint: bound the local example.',source=source)
    grants(pai);request(pai,151020,'/chat Explain Python examples')
    assert not model_context(pai)
    allow(pai,'model.context_egress',root.archive_resource_ref,'private_archive','dialogue.memory')
    ack,answer=request(pai,151021,'/chat Explain Python examples')
    assert saved.object_id in model_context(pai) and 'private_archive' in answer['payload']['source_data_classes']
    ref=root.queue.status(owner=root.owner_ref,job_id=ack.job_id)['result_ref'];root.registry.revoke_grant(grant.grant_id,owner_ref=root.owner_ref)
    with root.queue.store.transaction() as tx:
        item=tx.get(root.owner_ref,'result',ref);_,scopes=result_provenance(tx,root.owner_ref,item)
        with pytest.raises(CapabilityDenied):source_current(tx,root.registry,root.owner_ref,scopes)
    request(pai,151022,'/chat Explain Python examples')
    assert not model_context(pai)


def test_corrected_version_wins_and_old_derived_answer_fails_current_binding(pai):
    first=note(pai,'Python examples should use lists.');grants(pai)
    ack,answer=request(pai,151030,'/chat Explain Python examples')
    second=note(pai,'Python examples should use tuples.',expected_version=1)
    request(pai,151031,'/chat Explain Python examples')
    assert 'tuples' in model_context(pai) and 'use lists' not in model_context(pai)
    assert second.version==2
    ref=pai.root.queue.status(owner=pai.root.owner_ref,job_id=ack.job_id)['result_ref']
    with pai.root.queue.store.transaction() as tx:
        with pytest.raises(CapabilityDenied):result_provenance(tx,pai.root.owner_ref,tx.get(pai.root.owner_ref,'result',ref))


def test_expired_memory_and_reset_are_distinct_from_permanent_memory(pai):
    expired=note(pai,'Python short-lived constraint.',object_ref='memory_expiring',expires_at=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat())
    stable=note(pai,'Python durable style preference.',object_ref='memory_stable',source=pai.root.queue.store.put(pai.root.owner_ref,'conversation','owner_permanent_source',{'query':'Explicit lasting preference'},expected_version=0))
    time.sleep(1.1);grants(pai);request(pai,151040,'новая тема');request(pai,151041,'/chat Explain Python examples')
    assert expired.object_id not in model_context(pai) and stable.object_id in model_context(pai)
    assert pai.root.memory.inspect(stable.object_id,**ACTOR)


def test_forget_cascades_context_answer_and_restart_cannot_recall(pai):
    saved=note(pai,'Python examples prefer a bounded local workflow.');grants(pai)
    ack,answer=request(pai,151050,'/chat Explain Python examples')
    ref=pai.root.queue.status(owner=pai.root.owner_ref,job_id=ack.job_id)['result_ref']
    pai.root.memory.forget(saved.object_id,**ACTOR)
    assert pai.root.queue.store.get(pai.root.owner_ref,'result',ref) is None
    assert pai.root.queue.store.get(pai.root.owner_ref,'result',answer['payload']['conversation']['response_refs'][0]) is None
    pai.root.attach_local_services(memory_runtime=MemoryRuntime(pai.root));request(pai,151051,'/chat Explain Python examples')
    assert not model_context(pai)


def test_natural_save_confirm_correct_inspect_export_forget_remain_explicit(pai):
    root=pai.root;root.attach_local_services(memory_runtime=MemoryRuntime(root))
    _,preview=request(pai,151060,'запомни: Python examples should be short.')
    assert preview['status']=='preview' and preview['payload']['save_undo_policy']['status']=='proposed_inactive'
    assert root.memory.search('Python examples',**ACTOR)==[]
    _,saved=request(pai,151061,'подтверди сохранение');ref=saved['payload']['memory_bindings'][0]['memory_ref']
    _,edited=request(pai,151062,'исправь память '+ref+': Python examples should include source links.')
    assert edited['status']=='preview' and root.memory.inspect(ref,**ACTOR).version==1
    request(pai,151063,'подтверди сохранение')
    assert root.memory.inspect(ref,**ACTOR).version==2
    _,shown=request(pai,151064,'найди в памяти Python examples')
    assert 'source links' in shown['text'] and 'should be short' not in shown['text']
    _,export=request(pai,151065,'экспорт памяти');assert ref in export['text']
    _,deleted=request(pai,151066,'забудь '+ref);assert deleted['status']=='complete' and root.memory.inspect(ref,**ACTOR) is None


def test_intervening_task_does_not_confirm_old_memory_preview(pai):
    root=pai.root;root.attach_local_services(memory_runtime=MemoryRuntime(root))
    request(pai,151070,'запомни: Python examples should be short.');request(pai,151071,'новая тема')
    _,value=request(pai,151072,'подтверди сохранение')
    assert value['status']=='clarify' and not root.memory.search('Python',**ACTOR)


def test_memory_deletion_waits_for_admitted_context_http_and_blocks_later_recall(pai,monkeypatch):
    from threading import Event,Thread
    from prm.runtime.model_protocol import ChatCompletionsTransport
    saved=note(pai,'Python examples prefer a bounded local workflow.');grants(pai)
    entered,release,deleting,deleted=Event(),Event(),Event(),Event();errors=[]
    ack=pai.root.ingress.receive({'update_id':151080,'message':{'chat':{'id':42,'type':'private'},'from':{'id':42},'text':'/chat Explain Python examples'}})
    original=ChatCompletionsTransport.send
    def held(self,*args,**kwargs):
        entered.set()
        if not release.wait(5):raise RuntimeError('synthetic HTTP gate timed out')
        return original(self,*args,**kwargs)
    monkeypatch.setattr(ChatCompletionsTransport,'send',held)
    def answer():
        try:pai.root.worker().run_once()
        except Exception as exc:errors.append(exc)
    def forget():
        deleting.set()
        try:pai.root.memory.forget(saved.object_id,**ACTOR);deleted.set()
        except Exception as exc:errors.append(exc)
    worker=Thread(target=answer);remover=Thread(target=forget)
    worker.start()
    try:
        assert entered.wait(5);remover.start();assert deleting.wait(5)
        assert not deleted.wait(.2)
    finally:
        release.set();worker.join(8)
        if remover.ident:remover.join(8)
    assert not worker.is_alive() and not remover.is_alive()
    # Deletion may win the final post-HTTP binding check. That exact denial
    # is allowed; a stale success or another error is not.
    assert len(errors)<=1 and all(type(exc)is CapabilityDenied and str(exc)=='memory changed or deleted' for exc in errors)
    assert deleted.is_set() and pai.root.memory.inspect(saved.object_id,**ACTOR) is None
    ref=pai.root.queue.status(owner=pai.root.owner_ref,job_id=ack.job_id).get('result_ref')
    prior=pai.root.queue.store.get(pai.root.owner_ref,'result',ref) if ref else None
    assert prior is None or (prior.payload['status']=='source_unavailable' and not prior.payload['payload']['memory_context_refs']
        and 'Python examples prefer a bounded local workflow' not in prior.payload['text'])
    assert saved.object_id in model_context(pai) and len(pai.requests)==1
    following=pai.root.ingress.receive({'update_id':151081,'message':{'chat':{'id':42,'type':'private'},'from':{'id':42},'text':'/chat Explain Python examples'}})
    assert following.job_id,following
    fresh_ref=pai.root.worker().run_once()
    assert fresh_ref is not None,pai.root.queue.status(owner=pai.root.owner_ref,job_id=following.job_id)
    assert pai.root.queue.store.get(pai.root.owner_ref,'result',fresh_ref).payload['status']=='ok'
    assert not model_context(pai) and len(pai.requests)==2
