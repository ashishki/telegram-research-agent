"""Explicit source/version feedback, positive emoji, scoped confirmed rule effects."""
from datetime import datetime,timezone
import json,pytest
from tests.daily08_fixtures import pai,request,setup,create,bind
from prm.feedback import FeedbackEvent,from_legacy_feedback
from prm.capabilities import CapabilityDenied


@pytest.mark.parametrize('emoji',['👎','🤬','👍','🤔','💡'])
def test_each_visible_emoji_is_positive_interest_and_absence_unknown(emoji):
    args=dict(owner_ref='owner_synthetic',brief_id='brief_'+'a'*24,brief_version=1,content_digest='sha256:'+'b'*64,observed_at=datetime.now(timezone.utc).isoformat())
    value=from_legacy_feedback({'emoji':[emoji]},**args,personal_reaction=True).to_dict()
    assert value['interest']=='positive' and value['learning_state']=='unknown' and not value['profile_changed']
    empty=from_legacy_feedback({'emoji':[]},**args,personal_reaction=True).to_dict()
    assert empty['kind']=='unknown' and empty['interest']=='unknown'


def test_explicit_application_is_version_bound_not_measured_or_profile_confirmation(pai):
    root,_,_,_,_=setup(pai,count=2);_,_,doc,_=create(pai,150901)
    _,answer=request(pai,150902,'применил пункт 2')
    event=answer['payload']['feedback_event']
    assert event['brief_id']==doc.brief_id and event['brief_version']==1 and event['story_number']==2
    assert event['learning_state']=='applied' and not event['profile_changed'] and 'измеренный эффект неизвестен' in answer['text']
    assert not root.feedback.rules() and not pai.requests


def test_native_reaction_replay_keeps_one_event_foreign_owner_rejected(pai):
    root,_,_,_,_=setup(pai,count=1);ack,value,doc,_=create(pai,150910);bind(pai,ack,value,910)
    update={'update_id':150911,'message_reaction':{'chat':{'id':42,'type':'private'},'user':{'id':42},'message_id':910,'new_reaction':[{'type':'emoji','emoji':'👎'}]}}
    assert root.ingress.receive(update) is None;assert root.ingress.receive(update) is None
    with root.queue.store.transaction() as tx:
        events=tx.conn.execute("SELECT v.payload FROM pa_runtime.object_heads h JOIN pa_runtime.object_versions v USING(owner,namespace,object_id,version) WHERE h.owner=%s AND h.namespace='result' AND v.payload->>'kind'='feedback_event'",(root.owner_ref,)).fetchall()
    assert len(events)==1 and events[0]['payload']['event']['interest']=='positive'
    assert events[0]['payload']['event']['brief_id']==doc.brief_id and not root.feedback.rules()
    foreign={'update_id':150912,'message_reaction':{**update['message_reaction'],'user':{'id':43}}}
    assert root.ingress.receive(foreign) is None


def test_confirmed_rule_changes_only_matching_topic_and_undo_restores_selection(pai):
    root,value,items,_,_=setup(pai,count=6)
    for item in items:item['topic_labels']=['Other']
    items[0]['topic_labels']=['AI']
    baseline=value.build(topic='Protocol',timezone_name='UTC',end_at=pai.now)
    assert any(a.evidence_ref=='evidence_news_0' for s in baseline.editorial.stories for a in s.anchors)
    _,preview=request(pai,150920,'не показывай тему AI')
    assert preview['status']=='preview' and not root.feedback.rules()
    _,saved=request(pai,150921,'подтверди сохранение')
    rules=root.feedback.rules();assert len(rules)==1 and rules[0].payload['preference_rule']=={'topic':'ai','signal':'not_topic'}
    selected=value.build(topic='Protocol',timezone_name='UTC',end_at=pai.now)
    assert not any(a.evidence_ref=='evidence_news_0' for s in selected.editorial.stories for a in s.anchors)
    assert len(selected.editorial.stories)==5
    _,undone=request(pai,150922,'отмени правило '+rules[0].object_id)
    assert undone['status']=='complete' and not root.feedback.rules()
    restored=value.build(topic='Protocol',timezone_name='UTC',end_at=pai.now)
    assert any(a.evidence_ref=='evidence_news_0' for s in restored.editorial.stories for a in s.anchors)


def test_confirmed_topic_rule_cannot_hide_critical_change(pai):
    root,value,items,_,_=setup(pai,count=7)
    for row in items:row['topic_labels']=['AI']
    request(pai,150930,'не показывай тему AI');request(pai,150931,'подтверди сохранение')
    document=value.build(topic='Protocol',timezone_name='UTC',end_at=pai.now)
    assert any(a.evidence_ref=='evidence_news_6' for story in document.editorial.stories for a in story.anchors)


def test_actual_legacy_artifact_shape_imports_exact_binding_without_inventing_application(pai):
    from db.artifact_feedback import record_artifact_feedback
    # Dedicated in-memory SQLite, independent of any configured personal DB.
    import sqlite3
    conn=sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE artifact_feedback_logs(id INTEGER PRIMARY KEY,week_label TEXT,artifact_type TEXT,artifact_path TEXT,digest_id INTEGER,section TEXT,item_ref TEXT,feedback TEXT,source_evidence_item_ids_json TEXT,notes TEXT,recorded_at TEXT,recorded_by TEXT)')
    row=record_artifact_feedback(conn,week_label='2026-W42',feedback='decision_impacting');conn.close()
    root,_,_,_,_=setup(pai,count=1);_,_,doc,_=create(pai,150940)
    args=dict(brief_id=doc.brief_id,version=1,content_digest=doc.content_digest,legacy_ref='synthetic_artifact_row_'+str(row['id']),idempotency_key='row_one',chat_id='42',actor_id='42',owner_chat_id='42')
    with pytest.raises(CapabilityDenied):root.feedback.import_legacy(row,**args)
    event=root.feedback.import_legacy(row,**args,confirmed_owner=True)
    assert event.payload['event']['kind']=='useful' and event.payload['event']['learning_state']=='unknown' and not root.feedback.rules()


def test_feedback_prompt_is_optional_single_foreground_question(pai):
    root,value,_,_,_=setup(pai,count=1)
    assert root.feedback.optional_prompt()==''
    root.feedback.weekly_prompt=True
    _,answer=request(pai,150950,'Собери обзор недели Protocol')
    assert answer['text'].count('отметь один пункт')==1 and answer['payload'].get('automatic_job_created') is False
