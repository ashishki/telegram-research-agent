from dataclasses import replace
from datetime import datetime,timedelta,timezone
import pytest
from prm.conversation import ConfirmationRef,classify_turn,identity_hash
from prm.storage.postgres import migrate
from prm.storage.testing import PostgresSandbox
from prm.storage.conversations import DurableConversationStore,install_conversations


@pytest.fixture(scope='module')
def sandbox():
    with PostgresSandbox() as value:
        migrate(value.migrator,expected_version=0);install_conversations(value.migrator)
        yield value


def store(sandbox,owner='owner_synthetic_primary',retention=30):
    return DurableConversationStore(sandbox.app,owner_ref=owner,history_retention_seconds=retention)


def test_restart_keeps_exact_response_and_second_item(sandbox):
    first=store(sandbox)
    state=first.record_response('501',text='Два важных пункта',topic='AI',item_texts=('Первый','Второй'))
    restarted=store(sandbox)
    loaded=restarted.load('501')
    assert loaded==state
    turn=classify_turn('а второе',loaded)
    assert turn.response_ref==state.object_refs[0].response_ref
    assert turn.item_ref==state.object_refs[0].item_refs[1]
    assert loaded.object_refs[0].item_texts[1]=='Второй'
    assert store(sandbox,'owner_synthetic_foreign').load('501') is None


def test_confirmation_restart_new_topic_and_cancel(sandbox):
    first=store(sandbox);state=first.record_response('502',text='Сохранить результат?')
    ref=ConfirmationRef('proposal_synthetic_confirm','version1',state.object_refs[0].response_ref,
        identity_hash('502'),identity_hash('502'),identity_hash('502'),datetime.now(timezone.utc)+timedelta(minutes=5))
    first.offer_confirmation('502',ref)
    restarted=store(sandbox)
    resolved=restarted.resolve_plain_yes('502',actor_id='502',owner_chat_id='502',proposal_versions={ref.proposal_ref:'version1'})
    assert resolved.status=='resolved'
    assert restarted.resolve_plain_yes('502',actor_id='foreign',owner_chat_id='502',proposal_versions={ref.proposal_ref:'version1'}).status=='unavailable'
    restarted.begin_new_topic('502')
    assert restarted.resolve_plain_yes('502',actor_id='502',owner_chat_id='502',proposal_versions={ref.proposal_ref:'version1'}).status=='unavailable'
    restarted.start_request('502','request_synthetic');assert store(sandbox).cancel_request('request_synthetic') is not None
    assert first.is_cancelled('502','request_synthetic')


def test_two_pending_or_expired_proposals_do_not_resolve_plain_yes(sandbox):
    current=store(sandbox);state=current.record_response('503',text='Подтверждение')
    ref=ConfirmationRef('proposal_synthetic_a','version1',state.object_refs[0].response_ref,identity_hash('503'),identity_hash('503'),identity_hash('503'),datetime.now(timezone.utc)+timedelta(minutes=5))
    current.offer_confirmation('503',ref)
    with sandbox.migrator.connect() as conn:
        row=conn.execute("SELECT payload FROM pa_conversation.states WHERE id=%s",(state.conversation_id,)).fetchone()
        payload=row['payload'];other=dict(payload['visible_confirmation_refs'][0]);other['proposal_ref']='proposal_synthetic_b'
        payload['visible_confirmation_refs'].append(other)
        from psycopg.types.json import Jsonb
        conn.execute('UPDATE pa_conversation.states SET payload=%s WHERE id=%s',(Jsonb(payload),state.conversation_id))
    assert store(sandbox).resolve_plain_yes('503',actor_id='503',owner_chat_id='503',proposal_versions={ref.proposal_ref:'version1'}).status=='ambiguous_or_unavailable'
    with sandbox.migrator.connect() as conn:conn.execute("UPDATE pa_conversation.states SET expires=clock_timestamp()-interval '1 second' WHERE id=%s",(state.conversation_id,))
    assert current.load('503') is None


def test_old_result_stays_immutable_history_is_owner_bound_and_deleted(sandbox):
    current=store(sandbox)
    first=current.record_response('504',text='Первый результат')
    current.record_response('504',text='Следующий результат')
    loaded=store(sandbox).load('504')
    assert loaded.object_refs[1]==first.object_refs[0]
    assert len(current.history('504'))==2
    assert store(sandbox,'owner_foreign').history('504')==()
    with sandbox.migrator.connect() as conn:conn.execute("UPDATE pa_conversation.history SET expires=clock_timestamp()-interval '1 second' WHERE conversation_id=%s",(first.conversation_id,))
    assert current.purge_history()==2
    assert current.history('504')==()
    nohistory=store(sandbox,'owner_synthetic_nohistory',retention=0)
    nohistory.record_response('505',text='Synthetic temporary response')
    assert nohistory.history('505')==()


def _record_worker(config,owner,index):
    from prm.storage.postgres import SyntheticTarget
    target=SyntheticTarget.from_mapping(config)
    current=DurableConversationStore(target,owner_ref=owner,history_retention_seconds=30)
    current.start_request('506','request_'+str(index))


def test_separate_workers_do_not_lose_dialogue_updates(sandbox):
    from dataclasses import asdict
    import multiprocessing
    current=store(sandbox);current.start('506')
    ctx=multiprocessing.get_context('spawn')
    workers=[ctx.Process(target=_record_worker,args=(asdict(sandbox.app),'owner_synthetic_primary',index)) for index in range(2)]
    for worker in workers:worker.start()
    for worker in workers:worker.join(timeout=20);assert worker.exitcode==0
    assert set(current.load('506').pending_request_ids)=={'request_0','request_1'}


def test_actual_application_accepts_durable_conversation_control(sandbox):
    from types import SimpleNamespace
    from prm.application import PersonalResearchAssistant
    from prm.contracts import OperatorRequest
    current=store(sandbox);current.record_response('507',text='Old topic')
    assistant=PersonalResearchAssistant(settings=SimpleNamespace(db_path=':memory:'),conversations=current)
    assistant.answer(OperatorRequest(query='/new',mode='chat',chat_id='507'))
    assert store(sandbox).load('507').topic==''
    assert store(sandbox).load('507').current_confirmation_ref is None
