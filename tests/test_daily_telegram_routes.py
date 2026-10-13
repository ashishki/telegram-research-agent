"""One native ingress → job/result → exact message binding and continuation."""
from dataclasses import asdict
import json
import pytest

from tests.pai_runtime_fixtures import pai, allow
from tests.test_daily_telegram_transport import telegram_http
from prm.runtime.delivery import DeliveryExecutor, TransportReceipt
from prm.runtime.ingress import TelegramJobIngress
from prm.runtime.transports import BoundedTelegramSender
from prm.telegram_contracts import normalize_update
from prm.storage.postgres import StateConflict, StorageError


def update(index, text, **extra):
    return {'update_id': index, 'message': {'from': {'id': 42}, 'chat': {'id': 42, 'type': 'private'}, 'message_id': index, 'text': text, **extra}}


def test_normalized_quote_and_hidden_forward_do_not_invent_identity():
    value = normalize_update(update(1, 'Synthetic owner question', reply_to_message={'message_id': 10},
        quote={'text': '😀', 'position': 1}, forward_origin={'type': 'hidden_user', 'date': 1, 'sender_user_name': 'Synthetic hidden'}), owner_chat_id='42')
    assert value.schema_version == 'telegram.update.v2' and value.reply_to_message_id == 10
    assert value.quote.position == 1 and value.quote.verified is False
    assert value.forward_origin['source_identity'] is None and value.source_trust == 'untrusted_source'


def test_replay_preserves_job_and_cursor_after_restart(pai):
    root = pai.root
    incoming = update(97001, 'Synthetic durable message')
    first = root.ingress.receive(incoming)
    restarted = TelegramJobIngress(root.queue, owner_ref=root.owner_ref, owner_chat_id='42')
    assert restarted.receive(incoming).job_id == first.job_id
    assert restarted.polling_offset() == 97002
    body = root.queue.store.get(root.owner_ref, 'conversation', first.request_ref).payload
    assert body['telegram_envelope']['schema_version'] == 'telegram.update.v2'
    with pytest.raises(StateConflict): restarted.receive(update(97001, 'changed body'))


def test_foreign_business_stop_and_topics_are_rejected_without_jobs(pai):
    root = pai.root
    foreign = update(97101, 'sensitive_foreign_marker'); foreign['message']['from']['id'] = 43
    assert root.ingress.receive(foreign) is None
    assert root.ingress.receive({'update_id': 97102, 'business_message': update(1, 'sensitive_business_marker')['message']}) is None
    assert root.ingress.receive({'update_id': 97103, 'message_draft_stopped': {'chat': {'id': 42, 'type': 'private'}, 'draft_id': 1}}) is None
    topic = root.ingress.receive(update(97104, 'Стоп', message_thread_id=7))
    assert topic.destination.message_thread_id == 7 and 'недоступ' in topic.text
    assert root.queue.claim(owner=root.owner_ref) is None
    with root.queue.store.transaction() as tx:
        rows = tx.conn.execute('SELECT payload FROM pa_runtime.object_versions WHERE owner=%s', (root.owner_ref,)).fetchall()
        assert 'sensitive_foreign_marker' not in str(rows) and 'sensitive_business_marker' not in str(rows)


def test_forwarded_stop_is_source_data_not_owner_control(pai):
    root = pai.root
    first = root.ingress.receive(update(97201, 'Synthetic active task'))
    forwarded = root.ingress.receive(update(97202, 'Стоп', forward_origin={'type': 'hidden_user', 'date': 1, 'sender_user_name': 'Synthetic'}))
    assert forwarded.job_id != first.job_id
    assert root.queue.status(owner=root.owner_ref, job_id=first.job_id)['status'] == 'queued'


def completed(pai, index, text):
    ack = pai.root.ingress.receive(update(index, '/chat Synthetic request'))
    lease = pai.root.queue.claim(owner=pai.root.owner_ref, kinds=('compute.assistant',))
    pai.root.queue.complete(lease, {'request_ref': ack.request_ref, 'text': text, 'status': 'ok', 'data_class': 'user_provided', 'payload': {}})
    return ack


def delivery(pai, telegram_http):
    allow(pai, 'assistant.result_delivery', 'destination_private', 'user_provided', 'answer.delivery', provider='provider_telegram', connection=None, operation='deliver')
    sender = BoundedTelegramSender(token='synthetic_secret', owner_chat_id='42', destination_ref='destination_private', origin=telegram_http.origin, synthetic=True)
    executor = DeliveryExecutor(pai.pg.app, registry=pai.root.registry, sender=sender)
    pai.root.ingress.delivery_executor=executor; pai.root.ingress.destination_ref='destination_private'; pai.root.ingress.delivery_upper_bound=0
    return executor


def test_exact_result_version_navigation_and_reply_after_other_result(pai, telegram_http):
    root = pai.root; executor = delivery(pai, telegram_http)
    a = completed(pai, 97301, 'A😀 B — Synthetic result A')
    first = executor.deliver_result(owner=root.owner_ref, job_id=a.job_id, destination_ref='destination_private', upper_bound=0)
    assert first['status'] == 'sent' and first['payload']['schema_version'] == 'telegram.delivery.v2'
    b = completed(pai, 97302, 'Synthetic result B')
    executor.deliver_result(owner=root.owner_ref, job_id=b.job_id, destination_ref='destination_private', upper_bound=0)
    binding = root.ingress.bindings.for_message(root.ingress.telegram_destination, 1)
    assert binding.response_ref == 'result_' + a.job_id and binding.response_version == 1
    control = root.ingress.receive(update(97303, 'Что с задачей?', reply_to_message={'message_id': 1}, quote={'text': '😀', 'position': 1}))
    assert control.job_id == a.job_id
    follow = root.ingress.receive(update(97304, 'коротко', reply_to_message={'message_id': 1}, quote={'text': '😀', 'position': 1}))
    body = root.queue.store.get(root.owner_ref, 'conversation', follow.request_ref).payload
    assert body['reply_target']['result_ref'] == 'result_' + a.job_id and body['telegram_envelope']['quote']['verified'] is True
    markup = json.loads(telegram_http.requests[0][1]['reply_markup'][0])
    assert markup['inline_keyboard'][0][0]['callback_data'].startswith('paic:')


def test_edit_creates_revision_and_invalidates_old_controls_without_new_job(pai):
    root = pai.root
    a = root.ingress.receive(update(97401, 'Synthetic original'))
    token = root.ingress.bindings.issue_control(command='cancel', job_id=a.job_id)
    edited = update(97402, 'Changed source'); edited['message']['message_id'] = 97401
    edited = {'update_id': 97402, 'edited_message': edited['message']}
    reply = root.ingress.receive(edited)
    assert reply.job_id is None and 'исправл' in reply.text.casefold()
    assert root.queue.status(owner=root.owner_ref, job_id=a.job_id)['status'] == 'cancelled'
    assert root.ingress.bindings.resolve_control(token, destination=root.ingress.telegram_destination) is None
    assert root.queue.claim(owner=root.owner_ref) is None


def test_timeout_after_final_send_remains_unknown_on_replay(pai, telegram_http):
    root = pai.root; executor = delivery(pai, telegram_http)
    ack = completed(pai, 97501, 'Synthetic unknown send')
    telegram_http.responses.append((0, {}))
    assert executor.deliver_result(owner=root.owner_ref, job_id=ack.job_id, destination_ref='destination_private', upper_bound=0)['status'] == 'unknown'
    assert executor.deliver_result(owner=root.owner_ref, job_id=ack.job_id, destination_ref='destination_private', upper_bound=0)['status'] == 'unknown'
    assert len(telegram_http.requests) == 1


def test_actual_polling_acknowledges_callback_and_keeps_receipt_binding(pai, monkeypatch):
    from bot import bot, prm_handlers
    root = pai.root
    ack = root.ingress.receive(update(97601, 'Synthetic pending'))
    token = root.ingress.bindings.issue_control(command='status', job_id=ack.job_id)
    state, acks, sends, allowed = [], [], [], []
    monkeypatch.setattr(bot, '_load_bot_env', lambda: ('synthetic_secret', '42'))
    monkeypatch.setattr(bot, '_install_signal_handlers', lambda value: state.append(value))
    monkeypatch.setattr(bot, '_telegram_answer_callback', lambda token, ref, text: acks.append(ref))
    def send(*args, **kwargs):
        sends.append(kwargs)
        return TransportReceipt('telegram:42:500', destination=root.ingress.telegram_destination, message_id=500, method='sendMessage')
    monkeypatch.setattr(prm_handlers, 'send_message', send)
    def poll(**kwargs):
        allowed.append(kwargs.get('allowed_updates'))
        state[0].stop_requested = True
        return [{'update_id': 97602, 'callback_query': {'id': 'synthetic_callback', 'from': {'id': 42}, 'data': token, 'message': {'chat': {'id': 42, 'type': 'private'}, 'message_id': 100}}}]
    monkeypatch.setattr(bot, '_telegram_get_updates', poll)
    bot.run_bot(root.settings, job_ingress=root.ingress)
    assert acks == ['synthetic_callback']
    assert 'business_message' not in allowed[0]
    assert root.ingress.bindings.for_message(root.ingress.telegram_destination, 500).job_ref == ack.job_id


def test_polling_quarantines_poison_and_conflict_then_accepts_next(pai, monkeypatch):
    from bot import bot, prm_handlers
    root = pai.root; states = []
    root.ingress.receive(update(97701, 'Immutable original'))
    monkeypatch.setattr(bot, '_load_bot_env', lambda: ('synthetic_secret', '42'))
    monkeypatch.setattr(bot, '_install_signal_handlers', lambda value: states.append(value))
    monkeypatch.setattr(prm_handlers, 'send_message', lambda *args, **kwargs: None)
    def poll(**kwargs):
        states[0].stop_requested = True
        return [update(97701, 'Conflicting immutable body'), update(97702, 'bad', document={'file_id': '', 'mime_type': 'application/pdf'}), update(97703, 'Valid next request')]
    monkeypatch.setattr(bot, '_telegram_get_updates', poll)
    bot.run_bot(root.settings, job_ingress=root.ingress)
    assert root.ingress.polling_offset() == 97704
    with root.queue.store.transaction() as tx:
        statuses = [row['payload']['disposition'] for row in tx.conn.execute("SELECT payload FROM pa_runtime.object_versions WHERE owner=%s AND payload->>'schema_version'='telegram.inbox.v2'", (root.owner_ref,)).fetchall()]
    assert statuses.count('quarantined') == 2


def test_reply_worker_uses_a_and_preserves_current_b_focus(pai, telegram_http):
    root = pai.root; executor = delivery(pai, telegram_http)
    a = completed(pai, 97801, 'Synthetic A: preserve the original deadline tomorrow morning.')
    executor.deliver_result(owner=root.owner_ref, job_id=a.job_id, destination_ref='destination_private', upper_bound=0)
    b = completed(pai, 97802, 'Synthetic B: a different subject.')
    executor.deliver_result(owner=root.owner_ref, job_id=b.job_id, destination_ref='destination_private', upper_bound=0)
    root.conversations.record_response('42', text='Synthetic B current focus', topic='B')
    before = root.conversations.load('42')
    ack = root.ingress.receive(update(97803, 'коротко', reply_to_message={'message_id': 1}))
    ref = root.worker().run_once()
    value = root.queue.store.get(root.owner_ref, 'result', ref).payload
    assert 'Synthetic A' in value['text'] and 'Synthetic B current focus' not in value['text']
    assert root.conversations.load('42') == before
    assert value['request_ref'] == ack.request_ref and not pai.requests


def test_manual_quote_wrong_utf16_offset_is_unverified(pai, telegram_http):
    root = pai.root; executor = delivery(pai, telegram_http)
    a = completed(pai, 97901, 'A😀 B')
    executor.deliver_result(owner=root.owner_ref, job_id=a.job_id, destination_ref='destination_private', upper_bound=0)
    ack = root.ingress.receive(update(97902, 'Поясни', reply_to_message={'message_id': 1}, quote={'text': '😀', 'position': 2, 'is_manual': True}))
    body = root.queue.store.get(root.owner_ref, 'conversation', ack.request_ref).payload
    assert body['telegram_envelope']['quote']['verified'] is False


def test_edited_preview_cannot_be_confirmed_or_reexecuted(pai):
    from tests.test_pai_control_polish import action, preview
    root = action(pai)
    incoming = update(98001, preview(pai))
    ack = root.ingress.receive(incoming)
    ref = root.worker().run_once()
    proposal = root.queue.store.get(root.owner_ref, 'result', ref).payload['payload']['proposal_ref']
    edit = update(98002, '/actconfirm ' + proposal, message_id=98001)
    root.ingress.receive({'update_id': 98002, 'edited_message': edit['message']})
    follow = root.ingress.receive(update(98003, 'да'))
    value = root.queue.store.get(root.owner_ref, 'result', root.worker().run_once()).payload
    assert value['status'] == 'confirmation_unavailable'
    assert not [item for item in pai.requests if item[0] == 'write']
    with root.queue.store.transaction() as tx:
        assert tx.conn.execute('SELECT status FROM pa_actions.proposals WHERE owner=%s AND ref=%s', (root.owner_ref, proposal)).fetchone()['status'] == 'cancelled'


def test_legacy_unknown_delivery_read_without_digest_rewrite_or_send(pai, telegram_http):
    root = pai.root
    ack = completed(pai, 98101, 'Synthetic legacy result')
    old = DeliveryExecutor(pai.pg.app, registry=root.registry, sender=lambda *args: (_ for _ in ()).throw(StorageError('synthetic unknown')))
    allow(pai, 'assistant.result_delivery', 'destination_private', 'user_provided', 'answer.delivery', provider='provider_telegram', connection=None, operation='deliver')
    before = old.deliver_result(owner=root.owner_ref, job_id=ack.job_id, destination_ref='destination_private', upper_bound=0)
    assert before['status'] == 'unknown' and 'schema_version' not in before['payload']
    current = delivery(pai, telegram_http)
    after = current.deliver_result(owner=root.owner_ref, job_id=ack.job_id, destination_ref='destination_private', upper_bound=0)
    assert after['digest'] == before['digest'] and after['payload'] == before['payload']
    assert not telegram_http.requests


def test_polling_worker_final_send_use_real_loopback_transport(pai, telegram_http, monkeypatch):
    from bot import bot
    root = pai.root; root.model_endpoint = None
    executor = delivery(pai, telegram_http)
    states = []
    monkeypatch.setattr(bot, 'BOT_API_BASE', telegram_http.origin)
    monkeypatch.setattr(bot, '_load_bot_env', lambda: ('synthetic_secret', '42'))
    monkeypatch.setattr(bot, '_install_signal_handlers', lambda state: states.append(state))
    native_poll = bot._telegram_get_updates
    def poll(**kwargs):
        states[0].stop_requested = True
        return native_poll(**kwargs)
    monkeypatch.setattr(bot, '_telegram_get_updates', poll)
    telegram_http.responses.extend([
        (200, {'ok': True, 'result': [update(98201, '/chat привет')]}),
        (200, {'ok': True, 'result': {'chat': {'id': 42}, 'message_id': 500}}),
    ])
    bot.run_bot(root.settings, job_ingress=root.ingress)
    ref = root.worker().run_once()
    with root.queue.store.transaction() as tx:
        job = tx.conn.execute('SELECT id FROM pa_jobs.jobs WHERE owner=%s AND result_ref=%s', (root.owner_ref, ref)).fetchone()['id']
    attempt = executor.deliver_result(owner=root.owner_ref, job_id=job, destination_ref='destination_private', upper_bound=0)
    assert attempt['status'] == 'sent'
    assert [path.rsplit('/', 1)[-1] for path, _ in telegram_http.requests] == ['getUpdates', 'sendMessage', 'sendMessage']
    assert root.ingress.bindings.for_message(root.ingress.telegram_destination, 500).job_ref == job
    assert root.ingress.bindings.for_message(root.ingress.telegram_destination, 3).response_ref == ref
    assert not pai.requests


def test_deletion_blocks_copied_ambiguity_reply_at_final_dispatch(pai):
    from prm.runtime.deletion import delete_derived_in
    root = pai.root
    a = root.ingress.receive(update(98301, 'Synthetic private choice A'))
    root.ingress.receive(update(98302, 'Synthetic private choice B'))
    incoming = update(98303, 'Стоп')
    reply = root.ingress.receive(incoming)
    ref, fresh = root.ingress.inbox.prepare_reply(incoming, reply)
    assert fresh
    with root.queue.store.transaction() as tx:
        delete_derived_in(tx, owner=root.owner_ref, namespace='conversation', object_ref=a.request_ref)
        remaining = tx.conn.execute('SELECT payload FROM pa_runtime.object_versions WHERE owner=%s', (root.owner_ref,)).fetchall()
        assert 'Synthetic private choice A' not in str(remaining)
    calls = []
    with pytest.raises(StorageError): root.ingress.inbox.dispatch_reply(ref, reply, lambda: calls.append('send'))
    assert not calls


def test_preview_delivered_by_other_bot_does_not_authorize_plain_yes(pai):
    from tests.test_pai_control_polish import action, preview
    root = action(pai)
    original = root.ingress
    ack = root.ingress.receive(update(98401, preview(pai)))
    root.worker().run_once()
    root.delivery.deliver_result(owner=root.owner_ref, job_id=ack.job_id, destination_ref='destination_private', upper_bound=0)
    root.ingress = TelegramJobIngress(root.queue, owner_ref=root.owner_ref, owner_chat_id='42', bot_ref='bot_other')
    root.ingress.durable_results = True
    root.ingress.receive(update(98402, 'да'))
    value = root.queue.store.get(root.owner_ref, 'result', root.worker().run_once()).payload
    assert value['status'] == 'confirmation_unavailable'
    assert not [item for item in pai.requests if item[0] == 'write']
    root.ingress = original
    root.ingress.receive(update(98403, 'да'))
    root.worker().run_once()
    assert len([item for item in pai.requests if item[0] == 'write']) == 1


def test_bot_namespace_and_result_version_cannot_alias_other_job(pai):
    root = pai.root
    a = completed(pai, 98501, 'Synthetic A')
    b = completed(pai, 98502, 'Synthetic B')
    with pytest.raises(StorageError): root.ingress.bindings.issue_control(command='result', job_id=a.job_id, response_ref='result_' + b.job_id, response_version=1)
    with pytest.raises(StorageError): root.ingress.bindings.issue_control(command='result', job_id=a.job_id, response_ref='result_' + a.job_id, response_version=True)
    other = TelegramJobIngress(root.queue, owner_ref=root.owner_ref, owner_chat_id='42', bot_ref='bot_other')
    same_id = other.receive(update(98501, 'Synthetic other bot input'))
    assert same_id.job_id != a.job_id and same_id.request_ref != a.request_ref
