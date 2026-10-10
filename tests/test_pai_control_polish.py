"""Natural controls preserve exact owner/version/delivery/no-replay authority."""
import json
from datetime import timedelta
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs
import pytest
from tests.pai_runtime_fixtures import pai,allow,request,graph
from prm.runtime.actions import ActionRuntime
from prm.runtime.delivery import DeliveryExecutor,TransportReceipt
from prm.runtime.presentation import keyboard,CONFIRM_LABELS,ACTION_CHECK
from prm.runtime.transports import BoundedTelegramSender,navigation_markup
from prm.runtime.watch import wire_archive_watch
from prm.storage.postgres import StorageError


def action(pai):
    root=pai.root;_,transport,_=graph(pai)
    allow(pai,'assistant.action_execute','resource_selected_mail','private_connector_content','action.execute',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='write')
    allow(pai,'assistant.action_reconciliation','resource_selected_mail','private_connector_metadata','action.reconcile',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    allow(pai,'assistant.result_delivery','destination_private','private_connector_content','answer.delivery',provider='provider_telegram',connection=None,operation='deliver')
    root.attach_local_services(action_runtime=ActionRuntime(root,graph_transport=transport,upper_bound=0))
    root.delivery=DeliveryExecutor(pai.pg.app,registry=root.registry,sender=lambda *args:TransportReceipt('synthetic_polish_receipt'))
    return root


def delivered(pai,index,text):
    ack,value=request(pai,index,text)
    assert pai.root.delivery.deliver_result(owner=pai.root.owner_ref,job_id=ack.job_id,destination_ref='destination_private',upper_bound=0)['status']=='sent'
    return value


def preview(pai):
    payload={'action_code':'mail.send','resource_ref':'resource_selected_mail','content':{'to':['recipient@example.test'],'subject':'Учебная Аврора','body':'Работа будет готова завтра утром.'}}
    return '/actpreview '+json.dumps(payload,ensure_ascii=False)


def test_delivered_human_preview_confirm_reconcile_repeat_uses_one_write(pai):
    root=action(pai)
    value=delivered(pai,81001,preview(pai))
    assert 'Кому: recipient@example.test' in value['text'] and 'Текст письма:' in value['text']
    assert 'account_ref' not in value['text'] and 'proposal_' not in value['text']
    assert value['payload']['telegram_navigation']['keyboard'][0][0]['text']==CONFIRM_LABELS['mail.send']
    first=delivered(pai,81002,CONFIRM_LABELS['mail.send'])
    assert first['status']=='unknown' and 'ещё не подтверждено' in first['text']
    resolved=delivered(pai,81003,ACTION_CHECK)
    assert resolved['status']=='succeeded' and '«Отправленных»' in resolved['text'] and 'synthetic_sent_' in resolved['text']
    assert 'адресатом' in resolved['text']
    duplicate=delivered(pai,81004,CONFIRM_LABELS['mail.send'])
    assert duplicate['status']=='succeeded' and 'нового действия не было' in duplicate['text']
    assert len([r for r in pai.requests if r[0]=='write'])==1
    assert not root.conversations.history_for_model('42')


def test_button_before_full_delivery_or_for_another_action_cannot_send(pai):
    root=action(pai)
    request(pai,81101,preview(pai))
    assert request(pai,81102,CONFIRM_LABELS['mail.send'])[1]['status']=='confirmation_unavailable'
    assert not [r for r in pai.requests if r[0]=='write']
    root.conversations.begin_new_topic('42')
    delivered(pai,81103,preview(pai))
    assert request(pai,81104,CONFIRM_LABELS['calendar.create'])[1]['status']=='confirmation_unavailable'
    assert not [r for r in pai.requests if r[0]=='write']


def inbound(number,text):return {'update_id':number,'message':{'chat':{'id':42,'type':'private'},'from':{'id':42},'text':text}}


def test_watch_text_controls_show_consent_state_and_reject_ambiguous_preview(pai):
    root=pai.root;root.ingress.destination_ref='destination_private';wire_archive_watch(root)
    before=root.ingress.receive(inbound(82001,'/watch '+root.archive_resource_ref))
    assert 'Наблюдение ещё не включено' in before.text and '/watchconfirm' not in before.text
    assert before.navigation['keyboard'][0][0]['text']=='Подтвердить наблюдение'
    confirmed=root.ingress.receive(inbound(82002,'Подтвердить наблюдение'))
    assert 'Подписка сохранена' in confirmed.text and 'пока не подтверждена' in confirmed.text
    assert 'проверки ещё не было' in root.ingress.receive(inbound(82003,'Проверить наблюдение')).text
    paused=root.ingress.receive(inbound(82004,'Приостановить наблюдение'))
    assert 'новые сборы и отправки остановлены' in paused.text
    assert 'приостановлена' in root.ingress.receive(inbound(82005,'Проверить наблюдение')).text
    assert 'возобновлена' in root.ingress.receive(inbound(82006,'Возобновить наблюдение')).text
    root.ingress.receive(inbound(82007,'/watch '+root.archive_resource_ref))
    root.ingress.receive(inbound(82008,'/watch '+root.archive_resource_ref))
    assert 'нужен один' in root.ingress.receive(inbound(82009,'Подтвердить наблюдение')).text
    foreign=inbound(82010,'Приостановить наблюдение');foreign['message']['from']['id']=43
    assert root.ingress.receive(foreign) is None


@pytest.mark.parametrize('value',[
    {'kind':'reply_keyboard','keyboard':[[{'text':'Send','callback_data':'secret'}]],'resize_keyboard':True,'one_time_keyboard':True},
    {'kind':'reply_keyboard','keyboard':[[{'text':'x'*91}]],'resize_keyboard':True,'one_time_keyboard':True},
    {'kind':'reply_keyboard','keyboard':[],'resize_keyboard':True,'one_time_keyboard':True},
])
def test_transport_metadata_cannot_smuggle_callback_or_unbounded_controls(value):
    with pytest.raises(StorageError):navigation_markup(value)


def test_native_telegram_adapter_emits_text_keyboard_and_html_without_live_account(pai):
    bodies=[]
    class Provider(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            bodies.append(parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode()))
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
            self.wfile.write(b'{"ok":true,"result":{"chat":{"id":42},"message_id":1}}')
    server=ThreadingHTTPServer(('127.0.0.1',0),Provider);thread=Thread(target=server.serve_forever);thread.start()
    try:
        sender=BoundedTelegramSender(token='synthetic_only',owner_chat_id='42',destination_ref='destination_private',origin=f'http://127.0.0.1:{server.server_port}',synthetic=True)
        sender.send_with_options('destination_private','<b>Предпросмотр</b>','synthetic_attempt',navigation=keyboard('Проверить результат действия'),parse_mode='HTML')
        assert bodies[0]['parse_mode']==['HTML'] and json.loads(bodies[0]['reply_markup'][0])['keyboard']==[[{'text':'Проверить результат действия'}]]
    finally:server.shutdown();thread.join(timeout=5);server.server_close()


def test_long_html_is_split_without_broken_tags_or_entities():
    from prm.runtime.presentation import split_html_messages
    from html.parser import HTMLParser
    text='<b>Заголовок</b>\n<i>'+('Длинная оговорка &amp; источник. '*300)+'</i>'
    parts=split_html_messages(text)
    assert len(parts)>1 and all(len(p)<=3500 for p in parts)
    for part in parts:
        assert '<i>' in part and '</i>' in part
        assert not part.endswith('&am')
        HTMLParser().feed(part)


def test_delivery_records_and_emits_markup_on_last_part_only(pai):
    root=pai.root;sent=[]
    sender=lambda destination,text,attempt:(sent.append(text) or TransportReceipt('synthetic_part_'+str(len(sent))))
    executor=DeliveryExecutor(pai.pg.app,registry=root.registry,sender=sender)
    allow(pai,'assistant.result_delivery','destination_private','user_provided','answer.delivery',provider='provider_telegram',connection=None,operation='deliver')
    item=root.queue.store.put(root.owner_ref,'conversation','input_controls_long',{'query':'synthetic long preview'},expected_version=0)
    job=root.queue.enqueue(owner=root.owner_ref,idempotency_key='controls_long_preview',kind='compute.assistant',deadline=pai.now+timedelta(minutes=3),
        payload={'schema_version':1,'input_namespace':'conversation','input_ref':item.object_id,'input_version':1,'input_digest':item.digest,'connection_ref':None,'resource_ref':'resource_local_request','purpose':'local.assistant','consent_revision':1})
    lease=root.queue.claim(owner=root.owner_ref,kinds=('compute.assistant',))
    root.queue.complete(lease,{'text':'Предпросмотр\n'+'a'*7800,'data_class':'user_provided','data_classes':['user_provided'],'payload':{'telegram_navigation':keyboard('Отправить письмо')}})
    outcome=executor.deliver_result(owner=root.owner_ref,job_id=job,destination_ref='destination_private',upper_bound=0)
    assert outcome['status']=='sent' and len(sent)==3
    with root.queue.store.transaction() as tx:
        parts=tx.conn.execute("SELECT payload FROM pa_delivery.attempts WHERE owner=%s AND id LIKE %s ORDER BY id",(root.owner_ref,'answer_'+job+'_part_%')).fetchall()
    assert all('telegram_navigation' not in row['payload'] for row in parts[:-1])
    assert parts[-1]['payload']['telegram_navigation']['keyboard'][0][0]['text']=='Отправить письмо'


@pytest.mark.parametrize('html,navigation', [(True, True), (False, True), (True, False)])
@pytest.mark.parametrize('last_outcome', ['delivered', 'not_delivered'])
def test_multipart_reconciliation_preserves_html_boundaries_and_last_controls(pai,html,navigation,last_outcome):
    from prm.runtime.delivery import ReconciliationObservation
    root=pai.root;sent=[]
    sender=lambda destination,text,attempt:(sent.append(text) or TransportReceipt('synthetic_part_'+str(len(sent))))
    executor=DeliveryExecutor(pai.pg.app,registry=root.registry,sender=sender)
    for capability,data_class,purpose,operation in [
        ('assistant.result_delivery','user_provided','answer.delivery','deliver'),
        ('assistant.delivery_reconciliation','private_connector_metadata','delivery.reconcile','read')]:
        allow(pai,capability,'destination_private',data_class,purpose,provider='provider_telegram',connection=None,operation=operation)
    item=root.queue.store.put(root.owner_ref,'conversation','input_reconcile_html',{'query':'synthetic long answer'},expected_version=0)
    job=root.queue.enqueue(owner=root.owner_ref,idempotency_key='reconcile_html',kind='compute.assistant',deadline=pai.now+timedelta(minutes=3),
        payload={'schema_version':1,'input_namespace':'conversation','input_ref':item.object_id,'input_version':1,'input_digest':item.digest,'connection_ref':None,'resource_ref':'resource_local_request','purpose':'local.assistant','consent_revision':1})
    options={}
    if html:options['telegram_parse_mode']='HTML'
    if navigation:options['telegram_navigation']=keyboard('Проверить результат действия')
    text='<b>'+'a'*7000+'</b>' if html else 'a'*7800
    root.queue.complete(root.queue.claim(owner=root.owner_ref,kinds=('compute.assistant',)),
        {'text':text,'data_class':'user_provided','data_classes':['user_provided'],'payload':options})
    outcome=executor.deliver_result(owner=root.owner_ref,job_id=job,destination_ref='destination_private',upper_bound=0)
    assert outcome['status']=='sent' and len(sent)==3
    # A crash can leave the precommitted aggregate/last receipt unknown after
    # provider acceptance. The exact child payloads survive the restart.
    with root.queue.store.transaction() as tx:
        tx.conn.execute("UPDATE pa_delivery.attempts SET status='unknown',provider_receipt='' WHERE owner=%s AND id=ANY(%s)",
            (root.owner_ref,[outcome['id'],outcome['id']+'_part_3']))
    seen=[]
    def observe(child):
        seen.append(child['id'])
        return ReconciliationObservation(child['attempt_ref'],child['destination_ref'],child['digest'],last_outcome,'synthetic_exact_receipt',
            'synthetic_final_part' if last_outcome=='delivered' else '')
    restarted=DeliveryExecutor(pai.pg.app,registry=root.registry,sender=sender)
    assert restarted.deliver_result(owner=root.owner_ref,job_id=job,destination_ref='destination_private',upper_bound=0)['status']=='unknown'
    reconciled=restarted.reconcile(owner=root.owner_ref,delivery_id=outcome['id'],adapter=observe,upper_bound=0)
    assert reconciled['status']==('sent' if last_outcome=='delivered' else 'unknown')
    assert seen==[outcome['id']+'_part_3'] and len(sent)==3
    assert restarted.attempt(owner=root.owner_ref,delivery_id=outcome['id']+'_part_3')['status']==('sent' if last_outcome=='delivered' else 'not_sent')
    assert restarted.deliver_result(owner=root.owner_ref,job_id=job,destination_ref='destination_private',upper_bound=0)['status']==reconciled['status']
    assert len(sent)==3


def test_voice_or_foreign_button_is_not_confirmation(pai):
    root=action(pai);delivered(pai,83001,preview(pai))
    incoming=inbound(83002,'');incoming['message'].pop('text');incoming['message']['voice_transcript']='Отправить письмо'
    root.ingress.receive(incoming);ref=root.worker().run_once();value=root.queue.store.get(root.owner_ref,'result',ref).payload
    assert not [r for r in pai.requests if r[0]=='write']
    foreign=inbound(83003,'Отправить письмо');foreign['message']['from']['id']=43
    assert root.ingress.receive(foreign) is None
