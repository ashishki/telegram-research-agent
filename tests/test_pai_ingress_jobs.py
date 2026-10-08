"""Real polling, transactional intake and concurrent cancellable application jobs."""
from dataclasses import asdict
import json
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from bot import bot
from prm.application import PersonalResearchAssistant
from prm.runtime.ingress import TelegramJobIngress, AssistantJobWorker
from prm.storage.postgres import migrate, StateConflict, StorageError
from prm.storage.jobs import JobQueue, install_jobs
from prm.storage.conversations import install_conversations
from prm.storage.testing import PostgresSandbox


@pytest.fixture(scope='module')
def sandbox():
    with PostgresSandbox() as value:
        migrate(value.migrator, expected_version=0)
        install_jobs(value.migrator)
        install_conversations(value.migrator)
        yield value


def ingress(sandbox, name, **kwargs):
    return TelegramJobIngress(JobQueue(sandbox.app, **kwargs), owner_ref='owner_ingress_' + name, owner_chat_id='42')


def update(number, text='привет', **changes):
    message = {'chat': {'id': 42, 'type': 'private'}, 'from': {'id': 42}, 'text': text}
    message.update(changes)
    return {'update_id': number, 'message': message}


def test_durable_intake_dedup_restart_and_changed_update_rejected(sandbox):
    current = ingress(sandbox, 'dedup')
    first = current.receive(update(10))
    assert first == ingress(sandbox, 'dedup').receive(update(10))
    assert ingress(sandbox, 'dedup').control('status', first.job_id).text.endswith('queued; попытка 0.')
    with pytest.raises(StateConflict):
        current.receive(update(10, 'different content'))
    assert current.queue.claim(owner=current.owner_ref).job_id == first.job_id
    assert current.queue.claim(owner=current.owner_ref) is None


def test_enqueue_failure_rolls_back_inbox_and_never_acknowledges(sandbox):
    current = ingress(sandbox, 'capacity', admission_limit=1)
    first = current.receive(update(20))
    with pytest.raises(StorageError, match='admission'):
        current.receive(update(21))
    with current.queue.store.transaction() as tx:
        assert tx.conn.execute('SELECT count(*) AS n FROM pa_runtime.object_heads WHERE owner=%s',
                               (current.owner_ref,)).fetchone()['n'] == 1
    current.control('cancel', first.job_id)
    assert current.receive(update(21)).job_id


@pytest.mark.parametrize('media',[
    {'document':{'file_id':'','mime_type':'application/pdf'}},
    {'photo':[{'file_id':''}]},
])
def test_empty_media_reference_is_denied_before_persistence(sandbox,media):
    current=ingress(sandbox,'empty_media_'+('document' if 'document' in media else 'photo'))
    with pytest.raises(StorageError,match='bounded inbound media reference'):
        current.receive(update(909,'',**media))
    with current.queue.store.transaction() as tx:
        count=tx.conn.execute('SELECT count(*) AS n FROM pa_runtime.object_heads WHERE owner=%s',(current.owner_ref,)).fetchone()['n']
    assert count==0 and current.queue.claim(owner=current.owner_ref) is None


@pytest.mark.parametrize('changes', [
    {'from': {'id': 43}}, {'chat': {'id': -10042, 'type': 'group'}},
    {'chat': {'id': 43, 'type': 'private'}}, {'chat': {'id': 42, 'type': 'group'}},
])
def test_private_tuple_checked_for_text_voice_callbacks(sandbox, changes):
    current = ingress(sandbox, 'private')
    for message in [update(30, **changes), update(31, '', voice={'file_id': 'synthetic'}, **changes)]:
        assert current.receive(message) is None
    callback = {'update_id': 32, 'callback_query': {'from': changes.get('from', {'id': 42}),
                'message': {'chat': changes.get('chat', {'id': 42, 'type': 'private'})}, 'data': 'pai:status:job_' + 'a' * 32}}
    assert current.receive(callback) is None


def test_real_polling_accepts_new_request_and_cancel_during_slow_application(sandbox, monkeypatch):
    from bot import prm_handlers
    current = ingress(sandbox, 'slow')
    first = current.receive(update(40, '/chat привет'))
    started, release = Event(), Event()
    failures = []

    class SlowAssistant(PersonalResearchAssistant):
        def answer(self, request):
            started.set()
            assert release.wait(timeout=10)
            return super().answer(request)

    def execute():
        try:
            AssistantJobWorker(current, settings=SimpleNamespace(db_path=':memory:'), assistant_factory=SlowAssistant).run_once()
        except StateConflict as error:
            failures.append(error)

    worker = Thread(target=execute)
    worker.start()
    assert started.wait(timeout=10)
    states = []
    monkeypatch.setattr(bot, '_install_signal_handlers', lambda state: states.append(state))
    monkeypatch.setattr(bot, '_load_bot_env', lambda: ('synthetic-token', '42'))
    sent = []
    monkeypatch.setattr(prm_handlers, 'send_message', lambda *args, **kwargs: sent.append(args[2]))

    def poll(**kwargs):
        states[0].stop_requested = True
        return [update(41, '/chat второй вопрос'), update(42, '/cancel ' + first.job_id)]

    monkeypatch.setattr(bot, '_telegram_get_updates', poll)
    try:
        bot.run_bot(SimpleNamespace(db_path=':memory:'), job_ingress=current)
        assert len(sent) == 2 and 'Запрос сохранён' in sent[0]
        assert sent[1] == 'Задача отменена. Уже начатый внешний вызов мог продолжиться.'
        assert not release.is_set()
        assert ingress(sandbox, 'slow').queue.status(owner=current.owner_ref, job_id=first.job_id)['status'] == 'cancelled'
    finally:
        release.set()
        worker.join(timeout=10)
    assert not worker.is_alive() and len(failures) == 1
    assert current.queue.store.get(current.owner_ref, 'result', 'result_' + first.job_id) is None


def test_real_application_results_are_bound_to_each_request_and_cli(sandbox, tmp_path, capsys):
    from prm.cli import main
    current = ingress(sandbox, 'results')
    first = current.receive(update(50, '/chat привет'))
    settings = SimpleNamespace(db_path=':memory:')
    assert AssistantJobWorker(current, settings=settings).run_once()
    second = current.receive(update(51, '/chat новая тема'))
    assert AssistantJobWorker(ingress(sandbox, 'results'), settings=settings).run_once()
    result = current.queue.store.get(current.owner_ref, 'result', 'result_' + first.job_id)
    assert result.payload['request_ref'] == first.request_ref != second.request_ref
    assert current.control('result', first.job_id).text == result.payload['text']
    config = tmp_path / 'synthetic.json'
    config.write_text(json.dumps(asdict(sandbox.app)))
    third = current.receive(update(52, '/chat привет'))
    common = ['--synthetic-target', str(config), '--owner-ref', current.owner_ref, '--owner-chat-id', '42']
    assert main(['job-worker', '--db-path', ':memory:', *common]) == 0
    assert current.queue.status(owner=current.owner_ref, job_id=third.job_id)['status'] == 'completed'
    assert main(['job-result', first.job_id, '--synthetic-target', str(config), '--owner-ref', current.owner_ref,
                 '--owner-chat-id', '42']) == 0
    assert result.payload['text'] in capsys.readouterr().out
    assert ingress(sandbox, 'foreign').control('result', first.job_id).text == 'Задача не найдена.'


def test_cli_explicit_durable_assistant_composition(sandbox, tmp_path, monkeypatch):
    from prm import cli
    config = tmp_path / 'target.json'
    config.write_text(json.dumps(asdict(sandbox.app)))
    observed = []
    monkeypatch.setattr(cli, 'load_settings', lambda: SimpleNamespace(db_path=':memory:'))
    monkeypatch.setattr(cli, 'run_bot', lambda settings, **kwargs: observed.append(kwargs))
    assert cli.main(['assistant', '--synthetic-target', str(config), '--owner-ref', 'owner_cli', '--owner-chat-id', '42']) == 0
    assert isinstance(observed[0]['job_ingress'], TelegramJobIngress)
    with pytest.raises(ValueError, match='complete owner'):
        cli.main(['assistant', '--synthetic-target', str(config)])


def test_voice_transcript_and_raw_voice_are_queued_without_transcription(sandbox):
    current = ingress(sandbox, 'voice')
    transcript = current.receive(update(60, '', voice={'transcript': 'привет'}))
    assert AssistantJobWorker(current, settings=SimpleNamespace(db_path=':memory:')).run_once()
    body = current.queue.store.get(current.owner_ref, 'conversation', transcript.request_ref).payload
    assert body['input_kind'] == 'voice_transcript'
    raw = current.receive(update(61, '', voice={'file_id': 'synthetic_file_ref'}))
    assert AssistantJobWorker(current, settings=SimpleNamespace(db_path=':memory:')).run_once()
    assert current.queue.store.get(current.owner_ref, 'result', 'result_' + raw.job_id).payload['status'] == 'voice_unavailable'


def test_callback_cancel_does_not_authorize_unrelated_actions(sandbox):
    current = ingress(sandbox, 'callback')
    first = current.receive(update(70))
    callback = {'update_id': 71, 'callback_query': {'from': {'id': 42},
        'message': {'chat': {'id': 42, 'type': 'private'}}, 'data': 'pai:cancel:' + first.job_id}}
    assert current.receive(callback).text == 'Задача отменена.'
    callback['callback_query']['data'] = 'confirm:anything'
    assert 'недоступно' in current.receive(callback).text


def test_polling_replays_failed_commit_without_advancing_offset(sandbox, monkeypatch):
    current = ingress(sandbox, 'retry', admission_limit=1)
    first = current.receive(update(80))
    states, offsets = [], []
    monkeypatch.setattr(bot, '_install_signal_handlers', lambda state: states.append(state))
    monkeypatch.setattr(bot, '_load_bot_env', lambda: ('synthetic-token', '42'))
    from bot import prm_handlers
    monkeypatch.setattr(prm_handlers, 'send_message', lambda *args, **kwargs: None)

    def poll(**kwargs):
        offsets.append(kwargs['offset'])
        if len(offsets) == 2:
            current.control('cancel', first.job_id)
            states[0].stop_requested = True
        return [update(81)]

    monkeypatch.setattr(bot, '_telegram_get_updates', poll)
    bot.run_bot(SimpleNamespace(db_path=':memory:'), job_ingress=current)
    assert offsets == [None, None]
    assert current.receive(update(81)).job_id
