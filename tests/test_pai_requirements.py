"""Named spec obligations. Synthetic evidence is separate from live/human gates.

These cases are prepared during the owner-directed implementation pass and
must be executed only when that pass ends. They do not manufacture approval.
"""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json
import pytest

from tests.pai_runtime_fixtures import pai,allow,request,graph
from prm.capabilities import AuthorizationRequest,CapabilityDenied
from prm.storage.postgres import StorageError,StateConflict

ACTOR={'chat_id':'42','actor_id':'42','owner_chat_id':'42'}


def memory_item(pai,ref='memory_requirement'):
    from prm.runtime.memory import MemoryRuntime
    runtime=MemoryRuntime(pai.root)
    preview=runtime.preview(object_ref=ref,text='Explicit owned synthetic fact',source_refs=('explicit_owner_request',),**ACTOR)
    return runtime,runtime.confirm(preview,**ACTOR)


def watch(pai):
    from prm.runtime.scheduler import WatchScheduler
    from prm.watch_jobs import WatchSubscription
    scheduler=WatchScheduler(pai.root.queue)
    sub=WatchSubscription('watch_requirement',pai.root.owner_ref,1,('source_requirement',),'destination_requirement',
        'meaningful_change','Europe/Berlin',pai.now+timedelta(days=7),2)
    scheduler.confirm(scheduler.preview(sub,**ACTOR),**ACTOR)
    return scheduler,sub


def academic_pair(pai):
    from prm.academic_inbox import AcademicCandidate,AcademicDeadline
    from prm.runtime.academic import AcademicRuntime
    canvas=AcademicCandidate('academic_canvas_requirement',pai.root.owner_ref,'canvas_assignment','Задание','Подтверждённое задание','obligation','canvas',
        deadlines=(AcademicDeadline('due',pai.now+timedelta(days=1),'UTC','canvas','https://canvas.example.test/one'),),
        eligibility_uncertain=True,source_refs=('https://canvas.example.test/one',))
    mail=replace(canvas,candidate_ref='academic_mail_requirement',source_kind='mail',authority='official_message',
        deadlines=(AcademicDeadline('due',pai.now+timedelta(days=2),'UTC','official_message','https://mail.example.test/one'),),
        source_refs=('https://mail.example.test/one',))
    runtime=AcademicRuntime(pai.root)
    merged=runtime.merge((canvas,mail),identity_bindings={canvas.candidate_ref:'assignment_requirement',mail.candidate_ref:'assignment_requirement'})
    ref='academic_'+__import__('hashlib').sha256(b'assignment_requirement').hexdigest()[:32]
    return runtime,merged,ref


def observations(*,cost=1000,succeeded=True):
    return [{'case_id':'case_'+str(index),'input_digest':'input_'+str(index),'source_snapshot':'fixture_snapshot_v1',
        'scope_digest':'fixture_scope_v1','language':'ru' if index%2 else 'en','prompt_version':'fixture_prompt_v1',
        'tool_version':'fixture_tools_v1','requested_model':'fixture_model','observed_model':'fixture_model',
        'task_kind':'simple' if index<10 else 'complex','succeeded':succeeded,'supported_claims':4,'total_claims':4,
        'cost_microdollars':cost,'duration_ms':30+index} for index in range(20)]


def test_requirement_chat_01(pai):
    allow(pai,'model.generate','resource_dialogue','user_provided','answer.request')
    assert request(pai,1,'Привет, объясни идею простыми словами')[1]['status']=='ok'
    assert len([row for row in pai.requests if row[0]=='model'])==1


def test_requirement_chat_02(pai):
    from tests.test_pai_end_to_end import test_chat_multiturn_and_topic_return
    test_chat_multiturn_and_topic_return(pai)


def test_requirement_arch_01(pai):
    from prm.contracts import OperatorRequest
    allow(pai,'model.generate','resource_dialogue','user_provided','answer.request')
    direct=pai.root.answer(OperatorRequest('Привет',mode='chat',chat_id='42',actor_id='42',owner_chat_id='42'),request_ref='direct_interface')
    queued=request(pai,1,'/chat Привет')[1]
    assert direct.status==queued['status']=='ok' and len([row for row in pai.requests if row[0]=='model'])==2


def test_requirement_arch_02(pai):
    runtime,item=memory_item(pai)
    assert pai.root.queue.store.get('owner_foreign','memory',item.object_id) is None
    assert pai.root.queue.store.get(pai.root.owner_ref,'result',item.object_id) is None


def test_requirement_mem_01(pai):
    from prm.storage.conversations import DurableConversationStore
    state=pai.root.conversations.record_response('42',text='Первый\nВторой',item_texts=('Первый объект','Второй объект'))
    restored=DurableConversationStore(pai.pg.app,owner_ref=pai.root.owner_ref,history_retention_seconds=3600).load('42')
    assert restored.conversation_id==state.conversation_id and restored.object_refs[0].item_texts[1]=='Второй объект'


def test_requirement_mem_02(pai):
    runtime,item=memory_item(pai)
    preview=runtime.preview(object_ref=item.object_id,text='Corrected fact',source_refs=('explicit_owner_correction',),expected_version=item.version,**ACTOR)
    changed=runtime.confirm(preview,**ACTOR)
    assert changed.version==2 and runtime.export(**ACTOR)[0]['text']=='Corrected fact'
    runtime.forget(item.object_id,**ACTOR)
    assert runtime.inspect(item.object_id,**ACTOR) is None


def test_requirement_mem_03(pai):
    runtime,item=memory_item(pai)
    assert item.payload['lifecycle']=='indexed' and item.payload['source_refs']==['explicit_owner_request']
    assert item.payload['explicit_owner_request'] is True


def test_requirement_perm_01(pai):
    grant=allow(pai,'model.generate','resource_dialogue','user_provided','answer.request')
    req=AuthorizationRequest(owner_ref=pai.root.owner_ref,connection_ref='connection_fixture',capability='model.generate',resource_ref='resource_dialogue',
        operation='model_egress',data_class='user_provided',provider_ref='provider_openai',purpose='answer.request')
    assert pai.root.registry.authorize(req).allowed
    assert not pai.root.registry.authorize(replace(req,provider_ref='provider_other')).allowed
    assert not pai.root.registry.authorize(replace(req,purpose='different.purpose')).allowed
    pai.root.registry.revoke_grant(grant.grant_id,owner_ref=pai.root.owner_ref)
    assert not pai.root.registry.authorize(req).allowed


def test_requirement_search_01(pai):
    from tests.test_pai_archive_search import test_canonical_spans_reach_real_runtime_http_and_verify
    test_canonical_spans_reach_real_runtime_http_and_verify(pai)


def test_requirement_search_02(pai):
    from prm.routing import decide_route
    assert decide_route('Объясни текст',requested_mode='chat',explicit_project='').mode=='chat'
    assert decide_route('в архиве agent evals',requested_mode='research',explicit_project='').mode!='chat'
    assert not pai.requests


def test_requirement_search_03(pai):
    from tests.test_pai_deep_research import test_cancel_before_claim_stops_every_research_source
    test_cancel_before_claim_stops_every_research_source(pai)


def test_requirement_search_04(pai):
    from assistant.claim_ledger import verify_answer_against_evidence
    evidence=[{'evidence_id':'fixture_1','source_url':'https://example.test/a','support_span':'Retries do not prove an unknown send failed.'}]
    verdict=verify_answer_against_evidence('Retries prove an unknown send failed. (https://example.test/a)',evidence)
    assert verdict['metrics']['unsupported_claim_rate']>0


def test_requirement_rag_01():
    from tests.test_archive_search import _make_connection,_insert_post
    from db.archive_search import search_telegram_archive
    conn=_make_connection()
    try:
        _insert_post(conn,post_id=1,content='Agent evals use task success and groundedness.')
        _insert_post(conn,post_id=2,content='Проверка агентов оценивает успешность задач и обоснованность ответов.',language='ru')
        assert search_telegram_archive(conn,'agent evals')[0].post_id==1
        assert search_telegram_archive(conn,'агентов')[0].post_id==2
    finally:conn.close()


def test_requirement_evidence_01(pai):
    from tests.test_pai_brief_runtime import stored_brief
    doc,state=stored_brief(pai)
    item=doc.evidence[0]
    assert item.evidence_ref and item.source_ref.startswith('https://') and item.observed_at.tzinfo
    assert doc.content_digest and doc.owner_ref==pai.root.owner_ref


def test_requirement_evidence_02(pai):
    runtime,merged,ref=academic_pair(pai)
    assert len(merged)==1 and len(merged[0].deadlines)==2 and 'конфликт' in runtime.describe(merged)


def test_requirement_evidence_03(pai,monkeypatch):
    from tests.test_pai_web_github import test_brave_discovery_is_distinct_from_document_read
    test_brave_discovery_is_distinct_from_document_read(monkeypatch)
    from prm.public_web import _validate_https_url
    with pytest.raises(Exception):_validate_https_url('http://127.0.0.1/private')


def test_requirement_brief_01(pai):
    from tests.test_pai_brief_runtime import stored_brief
    doc,state=stored_brief(pai)
    assert doc.sections and doc.evidence and doc.window.timezone=='Europe/Berlin'


def test_requirement_brief_02(pai):
    from tests.test_pai_brief_runtime import stored_brief
    from prm.briefs import render_brief_document
    doc,state=stored_brief(pai)
    rendered=render_brief_document(doc)
    assert rendered and doc.selection_reasons and doc.coverage_manifest.sources


def test_requirement_brief_03(pai):
    from tests.test_pai_brief_runtime import test_immutable_brief_and_visible_item_survive_store_reconstruction
    test_immutable_brief_and_visible_item_survive_store_reconstruction(pai)


def test_requirement_brief_04(pai):
    from tests.test_pai_brief_runtime import stored_brief
    doc,state=stored_brief(pai)
    assert doc.selection_reasons and all(item.selection_reasons for section in doc.sections for item in section.items)


def test_requirement_brief_05():
    from tests.test_assistant_briefs import _window
    window=_window()
    assert window.contains(window.start_at) and not window.contains(window.end_at)
    assert (window.end_at.astimezone(timezone.utc)-window.start_at.astimezone(timezone.utc)).total_seconds()==25*3600


def test_requirement_brief_06(pai):
    from tests.test_pai_brief_runtime import test_no_selected_sources_is_partial_not_a_fabricated_quiet_week
    test_no_selected_sources_is_partial_not_a_fabricated_quiet_week(pai)


def test_requirement_brief_07(pai):
    from tests.test_pai_brief_runtime import stored_brief
    doc,state=stored_brief(pai)
    before=len(pai.requests)
    result=request(pai,1,'пункт 1')[1]
    assert result['status']=='ok' and len(pai.requests)==before


def test_requirement_visual_01(pai):
    from tests.test_pai_brief_runtime import stored_brief
    from prm.briefs import render_brief_document
    doc,state=stored_brief(pai)
    card=render_brief_document(doc)
    assert len(card)<=2400 and 'http' not in card[-4:]


def test_requirement_visual_02(pai):
    from tests.test_pai_report_runtime import test_actual_reader_subprocess_versions_and_private_http_headers
    test_actual_reader_subprocess_versions_and_private_http_headers(pai)


def test_requirement_visual_03(pai):
    from tests.test_pai_brief_runtime import stored_brief
    from prm.runtime.reader import PrivateReportRuntime
    from pypdf import PdfReader
    import io
    doc,state=stored_brief(pai);reader=PrivateReportRuntime(pai.root,artifact_root=pai.path/'pdf_artifacts')
    token=reader.issue_session(**ACTOR);body,kind=reader.artifact(token,brief_id=doc.brief_id,version=doc.version,format='pdf')
    parsed=PdfReader(io.BytesIO(body));text='\n'.join(page.extract_text() or '' for page in parsed.pages)
    assert parsed.pages and 'Важное' in text and 'example.test' in text


def test_requirement_visual_04(pai):
    from tests.test_pai_brief_runtime import stored_brief
    from prm.report_exports import render_markdown
    doc,state=stored_brief(pai);artifact=render_markdown(doc)
    assert doc.content_digest in artifact.body and 'https://example.test/event' in artifact.body


def test_requirement_watch_01(pai):
    scheduler,sub=watch(pai)
    value=scheduler.status(owner=pai.root.owner_ref,subscription_id=sub.subscription_id)
    assert value['intent_saved'] and not value['scheduler_observed_recently']


def test_requirement_watch_02(pai):
    scheduler,sub=watch(pai)
    scheduler.feedback(sub.subscription_id,'pause',**ACTOR)
    assert scheduler.tick(owner=pai.root.owner_ref,registry=pai.root.registry) is None


def test_requirement_watch_03(pai):
    from prm.runtime.scheduler import next_due
    scheduler,sub=watch(pai);daily=replace(sub,frequency='daily',delivery_time='02:30')
    first=next_due(daily,datetime(2026,10,25,0,0,tzinfo=timezone.utc),300)
    assert first==datetime(2026,10,25,0,30,tzinfo=timezone.utc)
    assert next_due(daily,first,300).date().isoformat()=='2026-10-26'


def test_requirement_watch_04(pai):
    scheduler,sub=watch(pai)
    scheduler.feedback(sub.subscription_id,'unsubscribe',**ACTOR)
    assert scheduler.status(owner=pai.root.owner_ref,subscription_id=sub.subscription_id)['lifecycle']=='cancelled'


def test_requirement_connect_01(pai):
    from tests.test_pai_graph_mail import test_actual_mail_pages_commit_minimal_fields_and_selected_scope
    test_actual_mail_pages_commit_minimal_fields_and_selected_scope(pai)


def test_requirement_connect_02(pai):
    from tests.test_pai_connections import test_real_pkce_callback_establishes_account_and_ciphertext_only
    test_real_pkce_callback_establishes_account_and_ciphertext_only(pai)


def test_requirement_connect_03(pai):
    manager,transport,actor=graph(pai)
    state=manager.status(owner=pai.root.owner_ref,connection_ref=transport.connection_ref)
    assert 'Mail.ReadBasic' in state['scopes'] and 'Mail.Send' in state['scopes']
    grant=allow(pai,'assistant.mail_read','resource_mail','private_connector_metadata','mail.read',provider='provider_microsoft_graph',connection=transport.connection_ref,operation='read')
    decision=pai.root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=pai.root.owner_ref,connection_ref=transport.connection_ref,
        capability='assistant.mail_read',resource_ref='resource_mail',operation='read',data_class='private_connector_metadata',
        provider_ref='provider_microsoft_graph',purpose='mail.read',operation_ref='mail_read_cannot_send'),upper_bound=0)
    before=len(pai.requests)
    with pytest.raises(CapabilityDenied):transport.request(decision,path='/v1.0/me/sendMail',method='POST',body={'message':{}})
    assert len(pai.requests)==before and not [entry for entry in pai.requests if entry[0]=='write']


def test_requirement_academic_01(pai):
    runtime,merged,ref=academic_pair(pai)
    assert merged[0].owner_ref==pai.root.owner_ref and pai.root.queue.store.get(pai.root.owner_ref,'memory',ref)


def test_requirement_academic_02(pai):
    runtime,merged,ref=academic_pair(pai)
    assert runtime.stage()=='unknown'
    preview=runtime.preview_stage('studying',actor_ref=pai.root.owner_ref)
    from prm.runtime.memory import MemoryRuntime
    assert runtime.stage()=='unknown'
    MemoryRuntime(pai.root).confirm(preview,**ACTOR)
    assert runtime.stage()=='studying'


def test_requirement_academic_03():
    from prm.academic_inbox import CanvasScopeSelection
    now=datetime.now(timezone.utc)
    with pytest.raises(ValueError):CanvasScopeSelection('provider_canvas','account_fixture',('course_12',),now,now+timedelta(days=2),'UTC',fetch_grades=True)
    with pytest.raises(ValueError):CanvasScopeSelection('provider_canvas','account_fixture',('course_12',),now,now+timedelta(days=2),'UTC',fetch_submissions=True)


def test_requirement_academic_04(pai):
    runtime,merged,ref=academic_pair(pai)
    assert merged[0].deadlines[0].due_at!=merged[0].deadlines[1].due_at
    assert all(deadline.authority in {'canvas','official_message'} for deadline in merged[0].deadlines)


def test_requirement_academic_05(pai):
    runtime,merged,ref=academic_pair(pai);scheduler,sub=watch(pai)
    runtime.link_watch(ref,schedule_id=sub.subscription_id,subject_ref=ref,actor_ref=pai.root.owner_ref)
    result=runtime.mark_done(ref,actor_ref=pai.root.owner_ref)
    assert result['stopped_watch_subjects']==1 and not result['source_submission_performed']
    with pai.root.queue.store.transaction() as tx:
        row=tx.conn.execute('SELECT state FROM pa_schedule.subjects WHERE owner=%s AND schedule_id=%s AND subject_ref=%s',(pai.root.owner_ref,sub.subscription_id,ref)).fetchone()
    assert row['state']=='completed'


def test_requirement_act_01(pai):
    from tests.test_pai_action_runtime import test_edited_preview_confirm_and_double_click_have_one_actual_write
    test_edited_preview_confirm_and_double_click_have_one_actual_write(pai)


def test_requirement_act_02(pai):
    from prm.runtime.actions import ActionRuntime
    manager,transport,actor=graph(pai);actions=ActionRuntime(pai.root,graph_transport=transport,upper_bound=0)
    proposal=actions.preview(action_code='mail.send',resource_ref='resource_mail',content={'to':['one@example.test'],'subject':'One','body':'First'},rationale_refs=('fixture_source',))
    changed=actions.edit(proposal,content={**proposal.content,'to':['two@example.test']})
    assert changed.digest!=proposal.digest and changed.version==2 and changed.expires_at>pai.now


def test_requirement_act_03(pai):
    from tests.test_pai_action_runtime import test_edited_preview_confirm_and_double_click_have_one_actual_write
    test_edited_preview_confirm_and_double_click_have_one_actual_write(pai)


def test_requirement_media_01(pai):
    from prm.runtime.media import MediaRuntime
    media=MediaRuntime(pai.root,temporary_root=pai.path/'voice')
    ref='transcript_fixture';pai.root.queue.store.put(pai.root.owner_ref,'result',ref,{'text':'old','version':1},expected_version=0)
    changed=media.revise_transcript(ref,text='corrected',expected_version=1)
    assert changed.version==2 and changed.payload['text']=='corrected'


def test_requirement_media_02(pai):
    from tests.test_pai_media_runtime import test_malicious_mime_is_rejected_before_file_and_plain_voice_is_cleaned
    test_malicious_mime_is_rejected_before_file_and_plain_voice_is_cleaned(pai)


def test_requirement_media_03(pai):
    from tests.test_pai_brief_runtime import stored_brief
    doc,state=stored_brief(pai)
    assert pai.root.briefs.resolve_visible(conversation_id=state.conversation_id,response_ref=state.object_refs[0].response_ref)[0].version==doc.version


def test_requirement_sec_01(pai):
    from tests.test_pai_end_to_end import test_source_injection_secret_query_and_fallback_denials
    test_source_injection_secret_query_and_fallback_denials(pai)


def test_requirement_sec_02(pai):
    before=len(pai.requests);request(pai,1,'Привет')
    assert len(pai.requests)==before
    assert pai.root.model_endpoint.synthetic_http and not pai.root.model_endpoint.token


def test_requirement_sec_03(pai):
    manager,transport,actor=graph(pai)
    assert all(path.stat().st_mode & 0o077==0 for path in manager.vault.path.iterdir())
    assert 'synthetic_access_fixture' not in str(manager.status(owner=pai.root.owner_ref,connection_ref=transport.connection_ref))


def test_requirement_sec_04(pai):
    from tests.test_pai_migration import test_new_deletion_delta_after_snapshot_survives_rollback_rehearsal
    test_new_deletion_delta_after_snapshot_survives_rollback_rehearsal(pai)


def test_requirement_ux_01(pai):
    ack=pai.root.ingress.receive({'update_id':1,'message':{'chat':{'id':42,'type':'private'},'from':{'id':42},'text':'Привет'}})
    assert ack.job_id and '/status '+ack.job_id in ack.text


def test_requirement_ux_02(pai):
    allow(pai,'model.generate','resource_dialogue','user_provided','answer.request')
    value=request(pai,1,'/chat объясни кратко')[1]
    assert value['status']=='ok' and value['text'] and len(value['text'])<2400


def test_requirement_ux_03(pai):
    from tests.test_pai_end_to_end import test_object_followups_confirmation_cancel_restart
    test_object_followups_confirmation_cancel_restart(pai)


def test_requirement_ux_04(pai):
    ack=pai.root.ingress.receive({'update_id':1,'message':{'chat':{'id':42,'type':'private'},'from':{'id':42},'text':'Долгий вопрос'}})
    value=pai.root.queue.status(owner=pai.root.owner_ref,job_id=ack.job_id)
    assert value['status']=='queued' and value['attempts']==0
    pai.root.ingress.control('cancel',ack.job_id)
    assert pai.root.worker().run_once() is None


def test_requirement_ux_05(pai):
    from prm.runtime.delivery import DeliveryExecutor
    executor=DeliveryExecutor(pai.pg.app,registry=pai.root.registry,sender=None)
    assert executor.attempt(owner=pai.root.owner_ref,delivery_id='nonexistent') is None
    assert 'не найдена' in executor.describe(owner=pai.root.owner_ref,delivery_id='nonexistent')


def test_requirement_ops_01(pai):
    incoming={'update_id':1,'message':{'chat':{'id':42,'type':'private'},'from':{'id':42},'text':'Привет'}}
    first=pai.root.ingress.receive(incoming);second=pai.root.ingress.receive(incoming)
    assert first.job_id==second.job_id


def test_requirement_ops_02(pai):
    from tests.test_pai_operations_runtime import test_actual_backup_restore_isolated_epoch_and_egress_off
    test_actual_backup_restore_isolated_epoch_and_egress_off(pai)


def test_requirement_migration_01(pai):
    from tests.test_pai_migration import test_new_deletion_delta_after_snapshot_survives_rollback_rehearsal
    test_new_deletion_delta_after_snapshot_survives_rollback_rehearsal(pai)


def test_requirement_cost_01(pai):
    req=AuthorizationRequest(owner_ref=pai.root.owner_ref,connection_ref='connection_fixture',capability='model.generate',resource_ref='resource_dialogue',
        operation='model_egress',data_class='user_provided',provider_ref='provider_openai',purpose='answer.request',operation_ref='unknown_quote')
    allow(pai,'model.generate','resource_dialogue','user_provided','answer.request')
    assert not pai.root.registry.authorize_and_reserve(req,upper_bound=None).allowed


def test_requirement_cost_02(pai):
    from tests.test_pai_cost_cache import test_usage_subsets_are_not_double_counted_and_unknown_is_not_zero
    test_usage_subsets_are_not_double_counted_and_unknown_is_not_zero(pai)


def test_requirement_model_01(pai):
    from prm.runtime.profiles import ModelProfiles
    base=pai.root.model_endpoint;cheap=replace(base,model='fixture_cheap');strong=replace(base,model='fixture_strong')
    profiles=ModelProfiles({'balanced':{'chat':base},'economical':{'chat':cheap},'maximum':{'chat':strong}})
    assert profiles.select(role='chat',quality='economical') is base
    assert profiles.select(role='chat',quality='maximum') is strong
    assert profiles.select(role='chat',manual_model='fixture_cheap') is cheap


def test_requirement_model_02(pai):
    from prm.runtime.profiles import ModelProfiles
    profiles=ModelProfiles({'balanced':{'chat':pai.root.model_endpoint}})
    with pytest.raises(StorageError):profiles.select(role='vision')
    assert not pai.requests


def test_requirement_quality_01():
    from prm.runtime.evaluation import compare_task_observations
    value=compare_task_observations(observations(),observations(cost=500))
    assert value['quality_non_regressed'] and value['savings_microdollars']==10000 and value['thresholds_met']
    assert not value['human_acceptance'] and not value['release_authority']


def test_requirement_eval_01():
    from prm.runtime.evaluation import compare_task_observations
    value=compare_task_observations(observations(),observations())
    assert value['evidence_layer']=='observed_dataset_only' and value['release_authority'] is False


def test_requirement_eval_02():
    from prm.runtime.evaluation import compare_task_observations
    changed=observations();changed[0]['source_snapshot']='different_snapshot'
    with pytest.raises(StorageError):compare_task_observations(observations(),changed)
    changed=observations();changed[0]['observed_model']='different_model'
    with pytest.raises(StorageError):compare_task_observations(observations(),changed)


def test_requirement_eval_03():
    from prm.runtime.release import prepare_candidate,completion_allowed
    candidate=prepare_candidate(Path(__file__).resolve().parents[1])
    assert candidate['gates']['human_visual_usefulness']=='pending' and not completion_allowed(candidate)


def test_requirement_done_01():
    from prm.runtime.release import prepare_candidate,completion_allowed
    candidate=prepare_candidate(Path(__file__).resolve().parents[1])
    assert not completion_allowed(candidate,human_acceptance_ref='an_unverified_string')
    assert candidate['gates']['actual_providers']=='pending_scoped_access'


def test_requirement_plan_01():
    repo=Path(__file__).resolve().parents[1]
    value=json.loads((repo/'docs/design/PAI.requirements.json').read_text())
    assert len(value['requirements'])==69 and len(value['scenarios'])==10
    assert (repo/'src/prm/runtime/composition.py').is_file()


def test_requirement_plan_02():
    repo=Path(__file__).resolve().parents[1]
    assert (repo/'tools/playbook.py').is_file() and (repo/'.playbook/upstream').is_dir()
    assert 'd570163ab17ec3b4245187c778f1e8d89af9690f' in (repo/'docs/PLAYBOOK_ADOPTION.md').read_text()


def test_requirement_plan_03():
    repo=Path(__file__).resolve().parents[1]
    manifest=json.loads((repo/'docs/design/PAI.requirements.json').read_text())
    assert all(row['review_roles'] and row['human_gate'] for row in manifest['requirements'])
    assert (repo/'docs/CODEX_PROMPT.md').stat().st_size<12000
