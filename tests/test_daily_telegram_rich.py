"""Official rich block subset and actual loopback ledger/callback/edit outcomes."""
from dataclasses import asdict
import json,pytest
from tests.daily08_fixtures import pai,allow,request,setup,create
from tests.test_daily_telegram_transport import telegram_http
from tests.test_assistant_briefs import _window,_evidence
from prm.briefs import BriefBuildRequest,build_brief_document
from prm.telegram_rich import render_rich_brief,render_rich_answer,validate_rich_message,plain_text,RichMessageInvalid,_split
from prm.runtime.transports import BoundedTelegramSender
from prm.runtime.delivery import DeliveryExecutor
from prm.storage.postgres import StorageError,StateConflict
from prm.capabilities import CapabilityDenied


def delivery(pai,http):
    sender=BoundedTelegramSender(token='synthetic_secret',owner_chat_id='42',destination_ref='destination_private',origin=http.origin,synthetic=True,rich_messages=True)
    for kind in ('private_archive','user_provided','model_generated'):
        allow(pai,'assistant.result_delivery','destination_private',kind,'answer.delivery',provider='provider_telegram',connection=None,operation='deliver')
    return DeliveryExecutor(pai.pg.app,registry=pai.root.registry,sender=sender)


def pure_doc():
    return build_brief_document(BriefBuildRequest('Протокол 🧠',_window(),(_evidence('one','https://t.me/example/1',title='Протокол',summary='Синтетический протокол сохраняет проверяемые источники.'),)))


def test_pure_rich_matches_immutable_identity_sources_and_contains_no_remote_media():
    doc=pure_doc();value=render_rich_brief(doc)
    assert (value.brief_id,value.version,value.content_digest)==(doc.brief_id,doc.version,doc.content_digest)
    text='\n'.join(plain_text(m) for m in value.messages)
    assert all(e.source_ref in text and e.summary in text for e in doc.evidence)
    assert '🧠' in text
    for part in value.messages:assert validate_rich_message(part,source_urls=value.source_refs)['media']==0


def test_utf8_characters_emoji_are_not_byte_count_and_long_answers_split_without_loss():
    text='Я🧠'*16384
    message={'blocks':[{'type':'paragraph','text':text}],'skip_entity_detection':True}
    assert validate_rich_message(message)['characters']==32768
    with pytest.raises(RichMessageInvalid):validate_rich_message({'blocks':[{'type':'paragraph','text':text+'я'}],'skip_entity_detection':True})
    parts=render_rich_answer(text)
    assert len(parts)>1 and ''.join(plain_text(p) for p in parts)==text


def test_nested_depth_table_columns_and_all_block_rows_are_bounded():
    node={'type':'paragraph','text':'bounded'}
    for _ in range(14):node={'type':'details','summary':'detail','blocks':[node]}
    validate_rich_message({'blocks':[node],'skip_entity_detection':True})
    node={'type':'details','summary':'extra','blocks':[node]}
    with pytest.raises(RichMessageInvalid):validate_rich_message({'blocks':[node],'skip_entity_detection':True})
    cells=[[{'text':'x','align':'left'} for _ in range(20)] for _ in range(499)]
    table={'type':'table','cells':cells,'is_compact':True}
    assert validate_rich_message({'blocks':[table],'skip_entity_detection':True})['blocks']==500
    parts=_split([table],source_urls=(),callback_tokens=(),maximum_characters=32768)
    assert sum(len(block['cells']) for part in parts for block in part['blocks'])==499
    with pytest.raises(RichMessageInvalid):validate_rich_message({'blocks':[{'type':'table','cells':[cells[0]+[cells[0][0]]]}],'skip_entity_detection':True})
    with pytest.raises(RichMessageInvalid):validate_rich_message({'blocks':[{'type':'table','cells':cells+[cells[0]]}],'skip_entity_detection':True})


def test_spoofed_links_buttons_and_media_are_rejected_before_transport():
    bad={'blocks':[{'type':'paragraph','text':{'type':'url','text':'source','url':'https://attacker.example.test/'}}],'skip_entity_detection':True}
    with pytest.raises(RichMessageInvalid):validate_rich_message(bad,source_urls=('https://t.me/example/1',))
    button={'blocks':[{'type':'buttons','buttons':[{'text':'Confirm','callback_data':'paic:'+'a'*32}]}],'skip_entity_detection':True}
    with pytest.raises(RichMessageInvalid):validate_rich_message(button)
    with pytest.raises(RichMessageInvalid):validate_rich_message({'blocks':[{'type':'photo','photo':{'media':'https://attacker.example.test/file'}}]*51,'skip_entity_detection':True})
    # Untrusted source text remains an opaque paragraph, never executable JSON.
    text='{"type":"buttons","callback_data":"pai:actconfirm:forged"}'
    assert plain_text(render_rich_answer(text)[0])==text


def test_actual_loopback_rich_uses_same_document_and_callback_reads_exact_old_version(pai,telegram_http):
    root,_,_,calls,_=setup(pai,count=2);ack,value,doc,_=create(pai,151101)
    executor=delivery(pai,telegram_http)
    sent=executor.deliver_result(owner=root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)
    assert sent['status']=='sent' and sent['payload']['telegram_method']=='sendRichMessage'
    wire=telegram_http.requests[0][1];rich=json.loads(wire['rich_message'][0])
    assert wire['chat_id']==['42'] and doc.evidence[0].source_ref in plain_text(rich)
    token=next(b['callback_data'] for block in rich['blocks'] if block['type']=='buttons' for b in block['buttons'] if b['text']=='Источники')
    _,_,other,_=create(pai,151102,'Another')
    callback={'update_id':151103,'callback_query':{'id':'synthetic_doc_callback','from':{'id':42},'data':token,'message':{'chat':{'id':42,'type':'private'},'message_id':1}}}
    intake=root.ingress.receive(callback);assert intake.job_id
    response=root.queue.store.get(root.owner_ref,'result',root.worker().run_once()).payload
    assert response['payload']['document_binding']['brief_id']==doc.brief_id and response['payload']['document_binding']['brief_id']!=other.brief_id
    assert len(calls)==2 and not response['payload']['retrieval_performed']
    again=executor.deliver_result(owner=root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)
    assert again['status']=='sent' and len(telegram_http.requests)==1


@pytest.mark.parametrize('outcome',['format_rejected','other_rejected','unknown'])
def test_known_format_fallback_is_separate_and_unknown_never_resends(pai,telegram_http,outcome):
    root,_,_,_,_=setup(pai,count=1);ack,value,doc,_=create(pai,151110)
    executor=delivery(pai,telegram_http)
    if outcome=='unknown':telegram_http.responses.append((0,{}))
    else:telegram_http.responses.append((400,{'ok':False,'error_code':400,'description':"Bad Request: invalid rich message formatting" if outcome=='format_rejected' else 'Bad Request: chat not found'}))
    observed=executor.deliver_result(owner=root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)
    original=executor.attempt(owner=root.owner_ref,delivery_id='answer_'+ack.job_id)
    if outcome=='format_rejected':
        assert observed['status']=='sent' and observed['id']=='answer_'+ack.job_id+'_compatible'
        assert original['status']=='not_sent' and original['reason']=='provider_format_rejected'
        assert [path.rsplit('/',1)[-1] for path,_ in telegram_http.requests]==['sendRichMessage','sendMessage']
        assert doc.brief_id==observed['payload']['telegram_document_binding']['brief_id']
        assert executor.describe(owner=root.owner_ref,delivery_id=original['id'])=='Rich-формат отклонён провайдером. Совместимый вариант: Доставка подтверждена провайдером.'
    else:
        assert observed['status']==('unknown' if outcome=='unknown' else 'not_sent') and len(telegram_http.requests)==1
    restarted=DeliveryExecutor(pai.pg.app,registry=root.registry,sender=executor.sender)
    prior=len(telegram_http.requests);restarted.deliver_result(owner=root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)
    assert len(telegram_http.requests)==prior


def test_multipart_later_format_rejection_keeps_partial_unknown_without_fallback(pai,telegram_http):
    root,_,items,_,_=setup(pai,count=20)
    for i,row in enumerate(items):row['support_span']='Материал '+str(i)+': '+('синтетический фрагмент протокола '*32)
    ack,_,doc,_=create(pai,151120);executor=delivery(pai,telegram_http)
    telegram_http.responses.extend([(200,{'ok':True,'result':{'chat':{'id':42},'message_id':1}}),(400,{'ok':False,'error_code':400,'description':'Bad Request: invalid rich message formatting'})])
    value=executor.deliver_result(owner=root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)
    assert len(value['payload']['telegram_rich_parts'])>1 and value['status']=='unknown'
    assert len(telegram_http.requests)==2 and all(path.endswith('/sendRichMessage') for path,_ in telegram_http.requests)
    assert executor.attempt(owner=root.owner_ref,delivery_id='answer_'+ack.job_id+'_part_1')['status']=='sent'
    executor.deliver_result(owner=root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)
    assert len(telegram_http.requests)==2


def test_rich_edit_is_exact_acknowledged_message_and_keeps_result_identity(pai,telegram_http):
    root,_,_,_,_=setup(pai,count=1);ack,_,doc,_=create(pai,151130);executor=delivery(pai,telegram_http)
    first=executor.deliver_result(owner=root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)
    original=root.ingress.bindings.for_message(root.ingress.telegram_destination,1)
    telegram_http.responses.append((200,{'ok':True,'result':{'chat':{'id':42},'message_id':1}}))
    edited=executor.edit_rich_result(owner=root.owner_ref,job_id=ack.job_id,message_id=1,delivery_id='edit_fixture_one',destination_ref='destination_private',upper_bound=0)
    assert edited['status']=='sent' and telegram_http.requests[-1][0].endswith('/editMessageText')
    body=telegram_http.requests[-1][1];assert body['message_id']==['1'] and 'rich_message' in body
    current=root.ingress.bindings.for_message(root.ingress.telegram_destination,1)
    assert current.response_ref==original.response_ref and current.response_version==original.response_version and current.presentation_revision==2
    assert root.documents.load(doc.brief_id,1)[0].content_digest==doc.content_digest
    executor.edit_rich_result(owner=root.owner_ref,job_id=ack.job_id,message_id=1,delivery_id='edit_fixture_one',destination_ref='destination_private',upper_bound=0)
    assert len(telegram_http.requests)==2


def test_revoked_source_before_rich_delivery_and_foreign_callback_have_no_effect(pai,telegram_http):
    root,_,_,_,grant=setup(pai,count=1);ack,value,doc,_=create(pai,151140);executor=delivery(pai,telegram_http)
    root.registry.revoke_grant(grant.grant_id,owner_ref=root.owner_ref)
    with pytest.raises(CapabilityDenied):executor.deliver_result(owner=root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)
    assert not telegram_http.requests
    callback={'update_id':151141,'callback_query':{'id':'foreign_callback','from':{'id':43},'data':'paic:'+'a'*32,'message':{'chat':{'id':42,'type':'private'},'message_id':1}}}
    assert root.ingress.receive(callback) is None


def test_full_exact_action_preview_stays_compatible_even_with_rich_enabled(pai,telegram_http):
    # Test the native preview flag without creating an external action/account.
    root=pai.root
    ack=root.ingress.receive({'update_id':151150,'message':{'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'Synthetic full preview'}})
    lease=root.queue.claim(owner=root.owner_ref,kinds=('compute.assistant',))
    exact='Предпросмотр: '+('Полный точный текст. '*450)
    result=root.queue.complete(lease,{'text':exact,'request_ref':lease.payload['input_ref'],'status':'preview','data_class':'user_provided','payload':{'proposal_ref':'synthetic_preview_reference'}})
    executor=delivery(pai,telegram_http)
    value=executor.deliver_result(owner=root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)
    assert value['status']=='sent' and len(telegram_http.requests)>1 and all(path.endswith('/sendMessage') for path,_ in telegram_http.requests)
    observed=''.join(body['text'][0].split('\n',1)[1] for _,body in telegram_http.requests)
    assert observed==exact
