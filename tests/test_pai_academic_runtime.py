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
