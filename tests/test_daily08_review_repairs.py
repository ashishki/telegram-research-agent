"""Frozen DAILY08 findings: native schedules, exact versions and loopback wire."""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
import json,time,pytest
from tests.daily08_fixtures import pai,allow,request,setup,create,note,bind
from tests.test_daily_memory_context import grants,model_context,ACTOR
from tests.test_daily_telegram_rich import delivery
from tests.test_daily_telegram_transport import telegram_http
from prm.storage.postgres import StorageError
from prm.capabilities import CapabilityDenied
from prm.runtime.source_access import result_provenance
from prm.runtime.deletion import delete_derived_in


@pytest.mark.parametrize('rich',[False,True])
def test_r01_correction_after_delivery_preparation_blocks_actual_http(pai,telegram_http,monkeypatch,rich):
    saved=note(pai,'Python examples use lists.');grants(pai)
    ack,_=request(pai,180001,'/chat Explain Python examples');executor=delivery(pai,telegram_http)
    executor.sender.rich_messages=rich;original=pai.root.registry.execute_reserved_groups
    def changed(groups,callback,**kwargs):
        note(pai,'Python examples use tuples.',expected_version=1)
        return original(groups,callback,**kwargs)
    monkeypatch.setattr(pai.root.registry,'execute_reserved_groups',changed)
    outcome=executor.deliver_result(owner=pai.root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)
    assert outcome['status']=='unknown' and not telegram_http.requests
    with pytest.raises(CapabilityDenied):executor.deliver_result(owner=pai.root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)
    assert not telegram_http.requests and saved.version==1


def test_r01_expiry_between_multipart_parts_blocks_remaining_http(pai,telegram_http,monkeypatch):
    expires=datetime.now(timezone.utc)+timedelta(seconds=5)
    note(pai,'Python '+('bounded presentation '*400),expires_at=expires.isoformat())
    ack,value=request(pai,180010,'покажи память');assert len(value['text'])>3800
    executor=delivery(pai,telegram_http);executor.sender.rich_messages=False
    original=pai.root.registry.execute_reserved_groups;calls=[]
    def expire(groups,callback,**kwargs):
        result=original(groups,callback,**kwargs);calls.append(1)
        if len(calls)==1:time.sleep(max(0,(expires-datetime.now(timezone.utc)).total_seconds())+.05)
        return result
    monkeypatch.setattr(pai.root.registry,'execute_reserved_groups',expire)
    outcome=executor.deliver_result(owner=pai.root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)
    assert outcome['status']=='unknown' and len(telegram_http.requests)==1


def test_r01_rich_edit_rechecks_memory_after_preparation(pai,telegram_http,monkeypatch):
    note(pai,'Python examples use lists.');grants(pai);ack,_=request(pai,180014,'/chat Explain Python examples')
    executor=delivery(pai,telegram_http)
    first=executor.deliver_result(owner=pai.root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)
    assert first['status']=='sent' and len(telegram_http.requests)==1
    original=pai.root.registry.execute_reserved_groups
    def changed(groups,callback,**kwargs):
        note(pai,'Python examples use tuples.',expected_version=1)
        return original(groups,callback,**kwargs)
    monkeypatch.setattr(pai.root.registry,'execute_reserved_groups',changed)
    edit=executor.edit_rich_result(owner=pai.root.owner_ref,job_id=ack.job_id,message_id=1,delivery_id='r01_memory_edit',destination_ref='destination_private',upper_bound=0)
    assert edit['status']=='unknown' and len(telegram_http.requests)==1


def test_r02_forget_waits_through_atomic_view_and_removes_response_and_history(pai,monkeypatch):
    from threading import Event,Thread
    saved=note(pai,'Owner memory sentinel bounded Python workflow.');root=pai.root
    ack=root.ingress.receive({'update_id':180018,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'покажи память'}})
    entered,release,removed=Event(),Event(),Event();errors=[]
    original=root._conversations._record_origin_in
    def held(*args,**kwargs):
        entered.set();assert release.wait(5);return original(*args,**kwargs)
    monkeypatch.setattr(root._conversations,'_record_origin_in',held)
    def answer():
        try:root.worker().run_once()
        except Exception as exc:errors.append(exc)
    def forget():
        try:root.memory.forget(saved.object_id,**ACTOR);removed.set()
        except Exception as exc:errors.append(exc)
    worker=Thread(target=answer);remover=Thread(target=forget);worker.start()
    try:
        assert entered.wait(5);remover.start();assert not removed.wait(.2)
    finally:
        release.set();worker.join(8)
        if remover.ident:remover.join(8)
    assert removed.is_set() and not errors and not worker.is_alive() and not remover.is_alive()
    with root.queue.store.transaction() as tx:
        assert not tx.conn.execute("SELECT 1 FROM pa_runtime.object_versions WHERE owner=%s AND namespace='result' AND payload::text LIKE %s",(root.owner_ref,'%Owner memory sentinel%')).fetchall()
        assert not tx.conn.execute("SELECT 1 FROM pa_conversation.history WHERE owner=%s AND payload->>'text' LIKE %s",(root.owner_ref,'%Owner memory sentinel%')).fetchall()
    state=root.queue.status(owner=root.owner_ref,job_id=ack.job_id)
    assert state['status'] in {'failed','completed'}
    _,next_view=request(pai,180019,'покажи память');assert next_view['status']=='not_found'


@pytest.mark.parametrize('kind',['memory','document'])
@pytest.mark.parametrize('change',['forget','correct'])
def test_r02_views_do_not_leave_orphan_text_after_validation(pai,monkeypatch,kind,change):
    root=pai.root;saved=note(pai,'Python owner rule secret alpha.')
    if kind=='document':
        root,_,_,_,_=setup(pai,count=1);_,_,doc,manifest=create(pai,180020)
        # Explicit fixture dependency for the document view race.
        root.queue.store.put(root.owner_ref,'result','r02_document_parent',{'text':'fixture','memory_bindings':[{'memory_ref':saved.object_id,'version':1,'digest':saved.digest}]},expected_version=0)
        with root.queue.store.transaction() as tx:
            tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s)',(root.owner_ref,'result','r02_document_parent','result',manifest.object_id))
            tx.conn.execute('INSERT INTO pa_memory.dependencies VALUES(%s,%s,%s,%s,%s)',(root.owner_ref,'memory',saved.object_id,'result','r02_document_parent'))
        text='покажи источники'
    else:text='покажи память'
    original=root._conversations.record_model_response
    original_in=root._conversations._record_model_response_in
    def mutate():
        if change=='forget':root.memory.forget(saved.object_id,**ACTOR)
        else:note(pai,'Python owner rule beta.',expected_version=1)
    # Enter the API before it acquires the transaction, after native view read.
    from prm.runtime.focus import FencedConversations
    getter=FencedConversations.__getattr__
    def access(self,name):
        method=getter(self,name)
        if name=='record_model_response':
            def gated(*args,**kwargs):mutate();return method(*args,**kwargs)
            return gated
        return method
    monkeypatch.setattr(FencedConversations,'__getattr__',access)
    _,answer=request(pai,180021,text)
    assert answer['status'] in {'source_unavailable','clarify'}
    with root.queue.store.transaction() as tx:
        rows=tx.conn.execute("SELECT payload FROM pa_conversation.history WHERE owner=%s AND payload->>'text' LIKE %s",(root.owner_ref,'%owner rule secret alpha%')).fetchall()
        # No view was written; pre-existing confirmed-memory data is separate.
        assert not rows
    assert 'owner rule secret alpha' not in answer['text']


def test_r03_actual_wire_retains_each_view_status_diff_and_full_prompt(pai,telegram_http):
    root,value,items,calls,_=setup(pai,count=2);root.feedback.weekly_prompt=True
    ack,first,doc,_=create(pai,180030);executor=delivery(pai,telegram_http)
    executor.deliver_result(owner=root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)
    from prm.telegram_rich import plain_text
    initial=json.loads(telegram_http.requests[-1][1]['rich_message'][0])
    assert root.feedback.optional_prompt() in plain_text(initial) and '/briefmaterials ' in plain_text(initial)
    items[0].update(support_span='Версия beta меняет протокол источника.',source_version='beta')
    _,updated=request(pai,180031,'обнови бриф');assert updated['payload']['brief_refresh']['changed']
    for index,query in enumerate(('применил пункт 1','экспорт PDF','сравни с предыдущей версией','только AI','почему это показано','обнови бриф'),180032):
        ack,answer=request(pai,index,query);assert answer['payload'].get('document_binding'),(query,answer['status'])
        previous=len(telegram_http.requests)
        sent=executor.deliver_result(owner=root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)
        assert sent['status']=='sent'
        packets=telegram_http.requests[previous:]
        assert len(packets)==1 and packets[0][0].endswith('/sendMessage')
        assert packets[0][1]['text'][0]==answer['text']
    assert not pai.requests


def rule_brief(pai):
    root,value,items,_,_=setup(pai,count=6)
    for i,row in enumerate(items):row.update(topic_labels=['AI'] if i==0 else ['Other'],source_group_id='group_'+str(i))
    request(pai,180040,'не показывай тему AI');request(pai,180041,'подтверди сохранение')
    rule=root.feedback.rules()[0]
    return root,value,items,rule


def test_r04_excluded_rule_remains_bound_and_undo_invalidates_document(pai):
    root,value,items,rule=rule_brief(pai);_,answer,doc,manifest=create(pai,180042)
    assert not any(a.evidence_ref=='evidence_news_0' for s in doc.editorial.stories for a in s.anchors)
    assert manifest.payload['memory_bindings']==[{'memory_ref':rule.object_id,'version':rule.version,'digest':rule.digest}]
    root.memory.forget(rule.object_id,**ACTOR)
    with pytest.raises((StorageError,CapabilityDenied)):root.documents.load(doc.brief_id,doc.version)


def test_r04_private_backed_rule_selection_never_calls_editorial_model(pai):
    root,value,items,rule=rule_brief(pai)
    # Native rule in reply to a protected result inherits that read authority.
    _,_,base,manifest=create(pai,180043)
    source={'namespace':'result','ref':manifest.object_id,'version':manifest.version,'digest':manifest.digest}
    ref=root.memory.preview(object_ref='memory_private_rule',text='Explicit private-backed AI preference.',kind='preference',
        source_refs=(manifest.object_id,),source_bindings=[source],preference_rule={'topic':'AI','signal':'too_long'},**ACTOR)
    private=root.memory.confirm(ref,**ACTOR);calls=[]
    value.editorial=lambda doc:calls.append(doc)
    doc=value.build(topic='Protocol',timezone_name='UTC',end_at=pai.now)
    assert not calls and not pai.requests
    assert private.object_id in {b['memory_ref'] for b in root.briefs.pending_memory_bindings[doc.content_digest]}
    assert 'private_archive' in root.briefs.pending_classes[doc.content_digest]


def test_r04_rule_correction_during_local_editorial_prevents_stale_persistence(pai,monkeypatch):
    from prm import brief_selection
    root,value,items,rule=rule_brief(pai);calls=[];value.editorial=lambda doc:calls.append(doc)
    original=brief_selection.build_attention_editorial
    def changed(*args,**kwargs):
        preview=root.memory.preview(object_ref=rule.object_id,text='Explicit corrected AI selection.',kind='preference',expected_version=1,
            source_refs=tuple(rule.payload['source_refs']),source_bindings=rule.payload['source_bindings'],preference_rule={'topic':'ai','signal':'useful'},**ACTOR)
        root.memory.confirm(preview,**ACTOR)
        return original(*args,**kwargs)
    monkeypatch.setattr(brief_selection,'build_attention_editorial',changed)
    with pytest.raises(CapabilityDenied):value.build(topic='Protocol',timezone_name='UTC',end_at=pai.now)
    assert not calls and not pai.requests


@pytest.mark.parametrize('kind',['rule','project'])
def test_r05_old_export_and_view_cannot_borrow_refreshed_head_bindings(pai,kind):
    if kind=='rule':
        root,value,items,rule=rule_brief(pai);_,answer,first,manifest=create(pai,180050)
        correction=lambda:root.memory.confirm(root.memory.preview(object_ref=rule.object_id,text='Explicit different rule.',kind='preference',
            expected_version=1,source_refs=tuple(rule.payload['source_refs']),source_bindings=rule.payload['source_bindings'],preference_rule={'topic':'ai','signal':'useful'},**ACTOR),**ACTOR)
    else:
        from tests.test_daily07_review_repairs import native_project_brief
        root,value,project,context,actor,_=native_project_brief(pai);root.attach_local_services(brief_runtime=value)
        _,answer,first,manifest=create(pai,180050,'Workflow')
        assert manifest.payload['project_bindings']
        context['descriptor']['current_goal']='Changed owner goal'
        correction=lambda:root.memory.confirm(root.projects.preview(object_ref=project.object_id,context=context,expected_version=1,**actor),**actor)
    _,export=request(pai,180051,'экспорт HTML');export_ref=export['payload']['export']['export_ref']
    _,view=request(pai,180052,'сделай короче');response_ref=view['payload']['conversation']['response_refs'][0]
    correction()
    _,fresh=request(pai,180053,'/document '+json.dumps({'brief_id':first.brief_id,'version':1,'action':'refresh'}))
    assert fresh['payload']['document_binding']['version']==2 and root.documents.load(first.brief_id,2)
    with pytest.raises((StorageError,CapabilityDenied)):root.documents.read_export(export_ref,**ACTOR)
    with root.queue.store.transaction() as tx:
        old=tx.get(root.owner_ref,'result',response_ref)
        with pytest.raises((StorageError,CapabilityDenied)):result_provenance(tx,root.owner_ref,old)
    with pytest.raises((StorageError,CapabilityDenied)):root.documents.load(first.brief_id,1)


@pytest.mark.parametrize('change',['edit','delete'])
def test_r06_original_input_fences_direct_named_export_refresh_and_saved_memory(pai,change):
    root,_,_,calls,_=setup(pai,count=1)
    ack=root.ingress.receive({'update_id':180060,'message':{'message_id':770,'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'Собери обзор недели Protocol'}})
    answer=root.queue.store.get(root.owner_ref,'result',root.worker().run_once()).payload
    pointer=answer['payload']['document_binding'];doc,manifest=root.documents.load(pointer['brief_id'],1)
    _,export=request(pai,180061,'экспорт HTML');export_ref=export['payload']['export']['export_ref']
    _,preview=request(pai,180062,'сохрани пункт 1');_,saved=request(pai,180063,'подтверди сохранение');memory_ref=saved['payload']['memory_bindings'][0]['memory_ref']
    assert manifest.payload['original_input_bindings'][0]['ref']==ack.request_ref
    if change=='edit':root.ingress.receive({'update_id':180064,'edited_message':{'message_id':770,'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'Changed original weekly request'}})
    else:
        with root.queue.store.transaction() as tx:delete_derived_in(tx,owner=root.owner_ref,namespace='conversation',object_ref=ack.request_ref)
    with pytest.raises((StorageError,CapabilityDenied)):root.documents.load(doc.brief_id,1)
    with pytest.raises((StorageError,CapabilityDenied)):root.documents.read_export(export_ref,**ACTOR)
    if change=='edit':
        with pytest.raises(CapabilityDenied):root.memory.inspect(memory_ref,**ACTOR)
        assert not root.memory.search('синтетический протокол',**ACTOR)
    else:assert root.memory.inspect(memory_ref,**ACTOR) is None
    for i,query in enumerate(('/document '+json.dumps({'brief_id':doc.brief_id,'version':1,'action':'refresh'}),'обзор «Protocol»: экспорт HTML'),180065):
        _,answer=request(pai,i,query);assert answer['status']=='clarify'
    assert len(calls)==1 and not pai.requests


@pytest.mark.parametrize('large',[False,True])
def test_r07_forget_after_atomic_response_settles_compute_without_retry(pai,monkeypatch,large):
    saved=note(pai,'Python examples owner note.');grants(pai);root=pai.root
    original=root.answer
    def lost(*args,**kwargs):
        result=original(*args,**kwargs);root.memory.forget(saved.object_id,**ACTOR)
        return replace(result,payload={**result.payload,**({'diagnostic':'x'*70000} if large else {})})
    monkeypatch.setattr(root,'answer',lost)
    ack=root.ingress.receive({'update_id':180070,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'/chat Explain Python examples'}})
    assert root.worker().run_once() is None
    state=root.queue.status(owner=root.owner_ref,job_id=ack.job_id)
    assert state['status']=='failed' and state['error_code']=='derived_source_unavailable' and state['result_ref'] is None
    assert saved.object_id in model_context(pai) and len(pai.requests)==1
    monkeypatch.setattr(root,'answer',original)
    request(pai,180071,'/chat Explain Python examples');assert not model_context(pai) and len(pai.requests)==2


def test_r08_story_reaction_replay_and_r09_documented_labels_are_native(pai):
    root,_,_,_,_=setup(pai,count=2);create(pai,180080)
    ack,view=request(pai,180081,'поясни пункт 2');bind(pai,ack,view,770)
    update={'update_id':180082,'message_reaction':{'chat':{'id':42,'type':'private'},'message_id':770,'user':{'id':42},'old_reaction':[],'new_reaction':[{'type':'emoji','emoji':'👎'}]}}
    one=root.ingress.receive(update);root.ingress.receive(update)
    with root.queue.store.transaction() as tx:
        rows=tx.conn.execute("SELECT payload FROM pa_runtime.object_versions WHERE owner=%s AND namespace='result' AND payload->>'kind'='feedback_event'",(root.owner_ref,)).fetchall()
    assert len(rows)==1 and rows[0]['payload']['event']['story_number']==2 and rows[0]['payload']['event']['interest']=='positive'
    for i,(label,kind) in enumerate((('это знаю','known'),('слишком длинно пункт 2','too_long'),('не моя тема пункт 2','not_topic')),180083):
        _,event=request(pai,i,label)
        assert event['payload']['feedback_event']['kind']==kind and event['payload']['feedback_event']['story_number']==2
    assert not pai.requests
