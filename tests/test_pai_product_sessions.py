"""Regressions discovered by real-provider product conversation evaluation."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json
import pytest
from tests.pai_runtime_fixtures import pai, allow, request
from prm.routing import decide_route
from prm.storage.postgres import StorageError, _canonical


@pytest.mark.parametrize('text',[
    'А как называется мой проект и что я сейчас изучаю?',
    'Как меня зовут сейчас?',
    'О чём мы говорили сейчас?',
])
def test_personal_dialogue_recall_is_not_external_current_fact(text):
    result=decide_route(text,requested_mode='chat')
    assert result.mode=='chat' and not result.external_verification_required


@pytest.mark.parametrize('text',[
    'Как меня зовут и кто сейчас CEO OpenAI?',
    'Как называется мой проект и какая текущая цена Python-хостинга?',
    'Что я сейчас изучаю? Проверь в интернете актуальные версии.',
])
def test_personal_words_never_override_real_external_fact_request(text):
    result=decide_route(text,requested_mode='chat')
    assert result.mode=='research' and result.external_verification_required


def test_chat_recall_through_worker_does_not_read_curated_memory_or_overflow(pai):
    allow(pai,'model.generate','resource_dialogue','user_provided','answer.request')
    result=request(pai,48101,'/chat А как называется мой проект и что я сейчас изучаю?')[1]
    assert result['status']=='ok' and result['payload']['model_call_attempted']
    assert 'curated_memory' not in result['payload'] and len(_canonical(result)[0].encode())<=65536
    assert len([row for row in pai.requests if row[0]=='model'])==1


def test_large_verified_result_is_losslessly_chunked_and_scope_projection_preserved(pai):
    from prm.runtime.result_payloads import bounded_result_record, resolve_result_payload
    root=pai.root;store=root.queue.store
    item=store.put(root.owner_ref,'conversation','input_large_eval',{'query':'Synthetic large verified result'},expected_version=0)
    job=root.queue.enqueue(owner=root.owner_ref,idempotency_key='large_result_eval',kind='compute.assistant',deadline=pai.now+timedelta(minutes=3),
        payload={'schema_version':1,'input_namespace':'conversation','input_ref':item.object_id,'input_version':1,'input_digest':item.digest,
                 'connection_ref':None,'resource_ref':'resource_large_eval','purpose':'local.assistant','consent_revision':1})
    lease=root.queue.claim(owner=root.owner_ref,kinds=('compute.assistant',))
    visible=root.conversations.record_response('42',text='Current synthetic source-bound response.')
    original={'curated_memory':'Синтетическое диагностическое описание. '*2000,'verification':{'claims':[{'supported':True,'source':'fixture'}]*200},
              'source_data_class':'private_archive','source_data_classes':['private_archive'],'source_scopes':[],
              'conversation':{'response_refs':[visible.object_refs[0].response_ref]},'model_call_attempted':False}
    record={'request_ref':item.object_id,'text':'Проверенный синтетический вывод.','status':'ok','data_class':'private_archive',
            'data_classes':['private_archive'],'interaction_id':'fixture','payload':original}
    compact=bounded_result_record(root.queue,lease,record)
    assert len(_canonical(compact)[0].encode())<=65536
    assert compact['payload']['source_data_classes']==['private_archive']
    assert compact['payload']['conversation']==original['conversation']
    root.queue.complete(lease,compact)
    assert resolve_result_payload(store,owner=root.owner_ref,record=compact)==original
    with pytest.raises(StorageError):resolve_result_payload(store,owner='owner_other_fixture',record=compact)
    changed=json.loads(json.dumps(compact));changed['payload']['source_data_classes']=['public']
    with pytest.raises(StorageError,match='scope projection'):resolve_result_payload(store,owner=root.owner_ref,record=changed)
    changed=json.loads(json.dumps(compact));changed['payload']['payload_storage']['sha256']='0'*64
    with pytest.raises(StorageError):resolve_result_payload(store,owner=root.owner_ref,record=changed)
    from prm.runtime.deletion import delete_derived_in
    with store.transaction() as tx:
        deleted=delete_derived_in(tx,owner=root.owner_ref,namespace='conversation',object_ref=item.object_id)
    assert deleted['deleted_refs']>=len(compact['payload']['payload_storage']['chunk_refs'])+2
    with pytest.raises(StorageError):resolve_result_payload(store,owner=root.owner_ref,record=compact)
    with pytest.raises(StorageError):bounded_result_record(root.queue,lease,record)


def test_extended_model_deadline_holds_real_guard_connections_and_resets_default(pai):
    from prm.capabilities import AuthorizationRequest
    root=pai.root;allow(pai,'model.generate','resource_dialogue','user_provided','answer.request')
    decision=root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref='connection_fixture',
        capability='model.generate',resource_ref='resource_dialogue',operation='model_egress',data_class='user_provided',
        provider_ref='provider_openai',purpose='answer.request',operation_ref='op_extended_model_fixture'),upper_bound=1)
    seen=[]
    def transport():
        with root.queue.store.transaction() as tx:
            seen.append(tx.conn.execute("SELECT current_setting('idle_in_transaction_session_timeout') AS bound").fetchone()['bound'])
        return 'actual guarded synthetic response'
    assert root.registry.execute_reserved_groups(((decision.reservation,),),transport,model_timeout_seconds=30)=='actual guarded synthetic response'
    assert seen==['35s']
    with root.queue.store.transaction() as tx:
        assert tx.conn.execute("SELECT current_setting('idle_in_transaction_session_timeout') AS bound").fetchone()['bound']=='15s'


def test_extended_deadline_cannot_apply_to_delivery_or_other_effects(pai):
    from prm.capabilities import AuthorizationRequest,CapabilityDenied
    root=pai.root;allow(pai,'assistant.result_delivery','destination_private','model_generated','answer.delivery',provider='provider_telegram',connection=None,operation='deliver')
    decision=root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,
        capability='assistant.result_delivery',resource_ref='destination_private',operation='deliver',data_class='model_generated',
        provider_ref='provider_telegram',purpose='answer.delivery',operation_ref='op_not_model_extended'),upper_bound=1)
    calls=[]
    with pytest.raises(CapabilityDenied,match='model-only'):
        root.registry.execute_reserved_groups(((decision.reservation,),),lambda:calls.append(True),model_timeout_seconds=30)
    assert calls==[]


def test_runtime_weekly_reply_binds_first_built_version_without_phantom_refresh(pai):
    from prm.runtime.brief import BriefRuntime,BriefSourceHook
    from prm.capabilities import AuthorizationRequest
    from tests.test_assistant_briefs import _evidence
    root=pai.root
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','brief.archive',provider='provider_local',connection=None,operation='read')
    scope=AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,capability='archive.read',resource_ref=root.archive_resource_ref,
        operation='read',data_class='private_archive',provider_ref='provider_local',purpose='brief.archive')
    hook=BriefSourceHook(root.archive_resource_ref,scope,lambda window:[_evidence('weekly_fixture','https://example.test/weekly',
        title='Синтетическое событие',summary='Подтверждённое синтетическое изменение без выдуманного эффекта.',posted_at=(window.end_at-timedelta(days=1)).isoformat())],0)
    runtime=BriefRuntime(root,source_hooks=(hook,),editorial=lambda document:None)
    root.attach_local_services(brief_runtime=runtime)
    result=request(pai,49105,'/weekly Важное за неделю')[1]
    state=root.conversations.load('42')
    document=root.briefs.resolve_visible(conversation_id=state.conversation_id,response_ref=state.object_refs[0].response_ref)[0]
    assert document.version==1 and document.previous_version is None
    assert document.evidence and result['status'] in {'ok','partial_brief'}


def test_supplied_dialogue_context_has_own_scope_and_survives_restart_then_new(pai):
    from prm.storage.conversations import DurableConversationStore
    root=pai.root
    allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request')
    allow(pai,'model.context_egress',root.model_resource_ref,'model_generated','dialogue.history')
    original='/chat В учебном проекте Аврора я обещала прислать работу завтра утром.'
    supplied=original.partition(' ')[2]
    request(pai,49200,original)
    request(pai,49201,'/chat Какой срок я назвала?')
    sent=[row[2] for row in pai.requests if row[0]=='model']
    assert supplied not in json.dumps(sent[-1],ensure_ascii=False)
    grant=allow(pai,'model.context_egress',root.model_resource_ref,'user_provided','dialogue.history')
    root.conversations=DurableConversationStore(pai.pg.app,owner_ref=root.owner_ref,history_retention_seconds=3600)
    request(pai,49202,'/chat Как называется проект и какой срок?')
    body=[row[2] for row in pai.requests if row[0]=='model'][-1]
    assert supplied in json.dumps(body,ensure_ascii=False) and len(body['messages'])<=6
    root.registry.revoke_grant(grant.grant_id,owner_ref=root.owner_ref)
    request(pai,49203,'/chat Повтори срок')
    body=[row[2] for row in pai.requests if row[0]=='model'][-1]
    assert supplied not in json.dumps(body,ensure_ascii=False)
    allow(pai,'model.context_egress',root.model_resource_ref,'user_provided','dialogue.history')
    request(pai,49204,'/new')
    request(pai,49205,'/chat Другая тема: фикстуры')
    body=[row[2] for row in pai.requests if row[0]=='model'][-1]
    assert supplied not in json.dumps(body,ensure_ascii=False)
    assert DurableConversationStore(pai.pg.app,owner_ref='owner_foreign',history_retention_seconds=3600).user_prompts_for_model('42')==()


def test_supplied_dialogue_context_is_bounded_expiring_and_not_saved_memory(pai):
    root=pai.root
    for index in range(8):
        state=root.conversations.record_response('42',text='Synthetic response '+str(index))
        ref=state.object_refs[0].response_ref
        root.conversations.record_origin(ref,('model_generated',))
        root.conversations.attach_user_prompt(ref,'Synthetic supplied turn '+str(index)+' '+('x'*2000))
    values=root.conversations.user_prompts_for_model('42')
    assert len(values)==4 and len(''.join(values))==4800
    assert values[0].startswith('Synthetic supplied turn 0') and values[-1].startswith('Synthetic supplied turn 7')
    with root.queue.store.transaction() as tx:
        assert tx.conn.execute("SELECT count(*) AS count FROM pa_runtime.object_heads WHERE owner=%s AND namespace='memory'",(root.owner_ref,)).fetchone()['count']==0
        tx.conn.execute("UPDATE pa_conversation.history SET expires=clock_timestamp()-interval '1 second' WHERE owner=%s",(root.owner_ref,))
    assert root.conversations.user_prompts_for_model('42')==()


def test_private_response_cannot_be_promoted_to_user_dialogue_context(pai):
    root=pai.root
    state=root.conversations.record_response('42',text='Synthetic selected connector text.')
    ref=state.object_refs[0].response_ref
    root.conversations.record_origin(ref,('private_connector_content',))
    root.conversations.attach_user_prompt(ref,'Synthetic selected connector prompt.')
    assert root.conversations.user_prompts_for_model('42')==()


def test_shortening_numbered_answer_keeps_actual_step_and_never_calls_model(pai):
    root=pai.root
    state=root.conversations.record_response('42',text='1. **Проверь, есть ли в проекте тесты.**\nПосмотри папку tests.\n2. Напиши первый тест.')
    root.conversations.record_origin(state.object_refs[0].response_ref,('model_generated',))
    result=request(pai,49210,'Сделай короче')[1]
    assert 'Проверь, есть ли в проекте тесты.' in result['text'] and result['text']!='1.'
    assert not [row for row in pai.requests if row[0]=='model']


def test_chat_display_preserves_bullet_and_paragraph_structure():
    from prm.application import _clean_model_answer
    assert _clean_model_answer('  1. Первый пункт\n2. Второй пункт\n\nПоследний абзац.  ')== '1. Первый пункт\n2. Второй пункт\n\nПоследний абзац.'


def test_fixed_a4_pdf_layout_does_not_inherit_streaming_page_margins():
    from weasyprint import HTML
    from tests.test_assistant_report_exports import _editorial_document
    from prm.report_exports import render_paginated_html
    html=str(render_paginated_html(_editorial_document(),stories_per_page=1,sources_per_page=1).body)
    def no_network(url):raise AssertionError('report layout must be offline')
    pages=HTML(string=html,url_fetcher=no_network).render().pages
    assert len(pages)==html.count('class="page"')
    for page in pages:
        for box in page._page_box.descendants():
            if type(box).__name__=='TextBox' and box.text.strip():
                assert box.position_x>=0 and box.position_y>=0
                assert box.position_x+box.width<=page.width+1
                assert box.position_y+box.height<=page.height+1


def test_long_editorial_pdf_uses_flow_layout_instead_of_clipping_sources():
    from dataclasses import replace
    from io import BytesIO
    import re
    from pypdf import PdfReader
    from tests.test_assistant_report_exports import _editorial_document
    from prm.report_exports import render_paginated_html,render_paginated_pdf,_render_with_weasyprint,BriefReportRenderError
    document=_editorial_document();story=document.editorial.stories[0]
    story=replace(story,explanation=('Синтетическое длинное объяснение с сохранёнными ограничениями. '*15)[:850],
        why_selected=('Причина выбора требует аккуратной проверки источника. '*6)[:280],
        next_step=('Проверить исходные материалы перед использованием вывода. '*6)[:280],
        caveat=('Измеренного результата нет; нужно сохранить эту оговорку. '*6)[:280])
    document=replace(document,editorial=replace(document.editorial,stories=(story,)))
    with pytest.raises(BriefReportRenderError,match='page_overflow'):
        _render_with_weasyprint(str(render_paginated_html(document).body))
    artifact=render_paginated_pdf(document)
    text=' '.join(page.extract_text() or '' for page in PdfReader(BytesIO(artifact.body)).pages)
    normalized=re.sub(r'\s+',' ',text)
    assert 'Второй источник описывает ограничение и сохраняет исходную оговорку.' in normalized
    assert 'Измеренного результата нет;' in normalized
