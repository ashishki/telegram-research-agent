"""Natural job controls select exact owner-bound objects and preserve other focus."""
import pytest
from tests.pai_runtime_fixtures import pai
from prm.runtime.ingress import TelegramJobIngress
from prm.telegram_contracts import TelegramDestination, TelegramMessageBinding
from prm.storage.postgres import StateConflict, StorageError


def update(index, text, **extra):
    return {'update_id': index, 'message': {'from': {'id': 42}, 'chat': {'id': 42, 'type': 'private'},
                                         'text': text, **extra}}


def test_zero_one_two_jobs_and_restart_selection(pai):
    ingress = pai.root.ingress
    assert 'Нет' in ingress.receive(update(96001, 'Что с задачей?')).text
    a = ingress.receive(update(96002, '/chat Synthetic task A', message_id=20))
    assert ingress.receive(update(96003, 'Что с задачей?')).job_id == a.job_id
    b = ingress.receive(update(96004, '/chat Synthetic task B', message_id=21))
    choice = ingress.receive(update(96005, 'Стоп'))
    assert choice.job_id is None and 'Выбери' in choice.text
    assert 'Synthetic task A' in choice.text and 'Synthetic task B' in choice.text
    assert pai.root.queue.status(owner=pai.root.owner_ref, job_id=a.job_id)['status'] == 'queued'
    restarted = TelegramJobIngress(pai.root.queue, owner_ref=pai.root.owner_ref, owner_chat_id='42')
    stopped = restarted.receive(update(96006, 'Стоп', reply_to_message={'message_id': 20}))
    assert stopped.job_id == a.job_id
    assert pai.root.queue.status(owner=pai.root.owner_ref, job_id=b.job_id)['status'] == 'queued'


def test_opaque_selection_callback_is_owner_route_and_expiry_bound(pai):
    ingress = pai.root.ingress
    a = ingress.receive(update(96101, 'Synthetic first job'))
    ingress.receive(update(96102, 'Synthetic second job'))
    choice = ingress.receive(update(96103, 'Стоп'))
    token = next(row[0]['callback_data'] for row in choice.navigation['inline_keyboard'] if row[0]['text'] == 'Synthetic first job')
    assert len(token.encode()) <= 64 and 'Synthetic' not in token and a.job_id not in token
    callback = {'update_id': 96104, 'callback_query': {'from': {'id': 43},
        'message': {'chat': {'id': 42, 'type': 'private'}}, 'data': token}}
    assert ingress.receive(callback) is None
    callback['callback_query']['from']['id'] = 42
    callback['callback_query']['message']['message_thread_id'] = 3
    assert 'недоступ' in ingress.receive(callback).text
    callback['callback_query']['message'].pop('message_thread_id')
    assert ingress.receive(callback).job_id == a.job_id
    # Navigation controls never authorize an action or repeat a completed send.
    assert 'cancelled' in ingress.receive(callback).text


def test_expired_control_does_not_cancel_job(pai):
    import time
    ack = pai.root.ingress.receive(update(96110, 'Synthetic expiry job'))
    token = pai.root.ingress.bindings.issue_control(command='cancel', job_id=ack.job_id, ttl_seconds=1)
    time.sleep(1.05)
    callback = {'update_id': 96111, 'callback_query': {'from': {'id': 42},
        'message': {'chat': {'id': 42, 'type': 'private'}}, 'data': token}}
    assert 'устарела' in pai.root.ingress.receive(callback).text
    assert pai.root.queue.status(owner=pai.root.owner_ref, job_id=ack.job_id)['status'] == 'queued'


def test_message_binding_survives_restart_and_does_not_guess_unknown_reply(pai):
    ingress = pai.root.ingress
    ack = ingress.receive(update(96201, 'Synthetic job'))
    route = TelegramDestination(chat_id='42')
    ingress.bindings.bind_message(TelegramMessageBinding(pai.root.owner_ref, route, 120, ack.job_id))
    assert 'не найд' in ingress.receive(update(96202, 'Стоп', reply_to_message={'message_id': 999})).text
    restarted = TelegramJobIngress(pai.root.queue, owner_ref=pai.root.owner_ref, owner_chat_id='42')
    assert restarted.receive(update(96203, 'Что с задачей?', reply_to_message={'message_id': 120})).job_id == ack.job_id


def test_cancel_does_not_clear_other_conversation_or_unknown_effect(pai):
    root = pai.root
    ack = root.ingress.receive(update(96301, 'Synthetic cancellable job'))
    lease = root.queue.claim(owner=root.owner_ref, kinds=('compute.assistant',))
    root.conversations.record_response('42', text='Synthetic unrelated focus', topic='project B')
    before = root.conversations.load('42')
    root.queue.checkpoint(lease, {'stage': 'answering', 'outcome': 'unknown'})
    assert root.ingress.receive(update(96302, 'Стоп')).job_id == ack.job_id
    assert root.conversations.load('42') == before
    assert root.queue.status(owner=root.owner_ref, job_id=ack.job_id)['checkpoint']['outcome'] == 'unknown'
    with pytest.raises(StateConflict, match='cancelled'):
        root.queue.complete(lease, {'text': 'late result'})


def test_result_control_preserves_delivery_scope_and_unknown_status(pai):
    root = pai.root
    ack = root.ingress.receive(update(96401, '/chat привет'))
    root.worker().run_once()
    answer = root.ingress.receive(update(96402, 'Верни результат'))
    assert answer.job_id == ack.job_id and 'scope' in answer.text
    assert not pai.requests


def test_started_effect_is_preserved_for_reconciliation(pai):
    root = pai.root
    ack = root.ingress.receive(update(96501, 'Synthetic parent input'))
    with root.queue.store.transaction() as tx:
        payload = tx.conn.execute('SELECT payload,deadline FROM pa_jobs.jobs WHERE owner=%s AND id=%s', (root.owner_ref, ack.job_id)).fetchone()
    job = root.queue.enqueue(owner=root.owner_ref, idempotency_key='synthetic_started_effect',
        payload={**payload['payload'], 'effect_key': 'synthetic_effect_key'}, deadline=payload['deadline'], kind='effect.dispatch', mode='effect')
    root.queue.claim(owner=root.owner_ref, modes=('effect',))
    assert 'сверки' in root.ingress.control('cancel', job).text
    assert root.queue.status(owner=root.owner_ref, job_id=job)['status'] == 'awaiting_reconciliation'


def test_polling_passes_bound_choice_buttons(pai, monkeypatch):
    from bot import bot, prm_handlers
    root = pai.root
    root.ingress.receive(update(96601, 'Synthetic first'))
    root.ingress.receive(update(96602, 'Synthetic second'))
    states, sent = [], []
    monkeypatch.setattr(bot, '_load_bot_env', lambda: ('synthetic_token', '42'))
    monkeypatch.setattr(bot, '_install_signal_handlers', lambda state: states.append(state))
    monkeypatch.setattr(prm_handlers, 'send_message', lambda *args, **kwargs: sent.append(kwargs))
    def poll(**kwargs):
        states[0].stop_requested = True
        return [update(96603, 'Стоп')]
    monkeypatch.setattr(bot, '_telegram_get_updates', poll)
    bot.run_bot(root.settings, job_ingress=root.ingress)
    assert len(sent[0]['reply_markup']['inline_keyboard']) == 2


def test_deleted_input_cannot_create_or_use_controls(pai):
    from prm.runtime.deletion import delete_derived_in
    root = pai.root
    ack = root.ingress.receive(update(96701, 'Synthetic deletable', message_id=1))
    token = root.ingress.bindings.issue_control(command='status', job_id=ack.job_id)
    with root.queue.store.transaction() as tx:
        delete_derived_in(tx, owner=root.owner_ref, namespace='conversation', object_ref=ack.request_ref)
    assert root.ingress.bindings.resolve_control(token, destination=root.ingress.telegram_destination) is None
    assert root.ingress.bindings.for_message(root.ingress.telegram_destination, 1) is None
    with pytest.raises(StorageError, match='input'):
        root.ingress.bindings.issue_control(command='status', job_id=ack.job_id)


def test_stop_update_replay_after_restart_keeps_original_target(pai):
    root = pai.root
    first = root.ingress.receive(update(96801, 'Synthetic A'))
    stop = update(96802, 'Стоп')
    assert root.ingress.receive(stop).job_id == first.job_id
    second = root.ingress.receive(update(96803, 'Synthetic B'))
    restarted = TelegramJobIngress(root.queue, owner_ref=root.owner_ref, owner_chat_id='42')
    assert restarted.receive(stop).job_id == first.job_id
    assert root.queue.status(owner=root.owner_ref, job_id=second.job_id)['status'] == 'queued'


def test_ambiguous_stop_replay_does_not_become_single_job_cancel(pai):
    root = pai.root
    a = root.ingress.receive(update(96811, 'Synthetic A'))
    b = root.ingress.receive(update(96812, 'Synthetic B'))
    stop = update(96813, 'Стоп')
    assert root.ingress.receive(stop).job_id is None
    root.queue.cancel(owner=root.owner_ref, job_id=a.job_id)
    assert root.ingress.receive(stop).job_id is None
    assert root.queue.status(owner=root.owner_ref, job_id=b.job_id)['status'] == 'queued'


def test_effect_claim_between_status_and_cancel_preserves_unknown_fence(pai, monkeypatch):
    root = pai.root
    ack = root.ingress.receive(update(96821, 'Synthetic parent'))
    with root.queue.store.transaction() as tx:
        row = tx.conn.execute('SELECT payload,deadline FROM pa_jobs.jobs WHERE owner=%s AND id=%s', (root.owner_ref, ack.job_id)).fetchone()
    job = root.queue.enqueue(owner=root.owner_ref, idempotency_key='synthetic_race_effect',
        payload={**row['payload'], 'effect_key': 'synthetic_race_key'}, deadline=row['deadline'], mode='effect', kind='effect.dispatch')
    cancel = root.queue.cancel
    claims = []
    def claimed_before_cancel(**kwargs):
        claims.append(root.queue.claim(owner=root.owner_ref, modes=('effect',)))
        return cancel(**kwargs)
    monkeypatch.setattr(root.queue, 'cancel', claimed_before_cancel)
    reply = root.ingress.control('cancel', job)
    assert 'сверки' in reply.text
    state = root.queue.status(owner=root.owner_ref, job_id=job)
    assert state['status'] == 'awaiting_reconciliation' and state['attempts'] == 1
    with pytest.raises(StateConflict): root.queue.heartbeat(claims[0])
