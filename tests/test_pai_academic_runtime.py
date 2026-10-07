"""Deferred cross-source deadlines, provenance and local completion."""
from datetime import timedelta
from tests.pai_runtime_fixtures import pai
from prm.academic_inbox import AcademicCandidate,AcademicDeadline
from prm.runtime.academic import AcademicRuntime


def test_mail_canvas_conflict_and_local_done_do_not_submit_anything(pai):
    canvas=AcademicCandidate('academic_canvas',pai.root.owner_ref,'canvas_assignment','Задание','Подтверждённое задание','obligation','canvas',
        deadlines=(AcademicDeadline('due',pai.now+timedelta(days=1),'UTC','canvas','https://canvas.example.test/1'),),eligibility_uncertain=True,source_refs=('https://canvas.example.test/1',))
    mail=AcademicCandidate('academic_mail',pai.root.owner_ref,'mail','Задание','Официальное письмо','obligation','official_message',
        deadlines=(AcademicDeadline('due',pai.now+timedelta(days=2),'UTC','official_message','https://mail.example.test/1'),),source_refs=('https://mail.example.test/1',))
    runtime=AcademicRuntime(pai.root);merged=runtime.merge((canvas,mail),identity_bindings={'academic_canvas':'assignment_1','academic_mail':'assignment_1'})
    assert len(merged)==1 and 'конфликт' in runtime.describe(merged) and merged[0].eligibility_uncertain
    ref='academic_'+__import__('hashlib').sha256(b'assignment_1').hexdigest()[:32]
    assert runtime.mark_done(ref,actor_ref=pai.root.owner_ref)['source_submission_performed'] is False
    assert not pai.requests


def test_local_done_atomically_stops_bound_watch_subject_and_future_notifications(pai):
    from tests.test_pai_requirements import academic_pair,watch
    runtime,candidates,ref=academic_pair(pai);scheduler,subscription=watch(pai)
    runtime.link_watch(ref,schedule_id=subscription.subscription_id,subject_ref=ref,actor_ref=pai.root.owner_ref)
    result=runtime.mark_done(ref,actor_ref=pai.root.owner_ref)
    assert result['stopped_watch_subjects']==1 and result['source_submission_performed'] is False
    with pai.root.queue.store.transaction() as tx:
        row=tx.conn.execute('SELECT state FROM pa_schedule.subjects WHERE owner=%s AND schedule_id=%s AND subject_ref=%s',
            (pai.root.owner_ref,subscription.subscription_id,ref)).fetchone()
    assert row['state']=='completed'
    assert pai.root.queue.store.get(pai.root.owner_ref,'memory',ref).payload['completion']=='local_done'
