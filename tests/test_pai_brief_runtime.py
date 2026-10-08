"""Deferred complete Brief application/persistence and source omission tests."""
from tests.pai_runtime_fixtures import pai
from tests.test_assistant_briefs import _window,_evidence
from prm.briefs import BriefBuildRequest,CoverageSource,build_brief_document
from prm.storage.briefs import DurableBriefStore


def stored_brief(pai):
    request=BriefBuildRequest('Неделя: важные события',_window(),(_evidence('event_1','https://example.test/event',title='Важное событие',summary='Подтверждённое событие для синтетического отчёта.'),),
        owner_ref=pai.root.owner_ref,coverage=(CoverageSource('source_synthetic','checked'),))
    document=build_brief_document(request)
    state=pai.root.conversations.record_response('42',text='Отчёт недели',topic='')
    pai.root.briefs.bind_visible(conversation_id=state.conversation_id,response_ref=state.object_refs[0].response_ref,document=document,
        authenticated_chat_id='42',authenticated_actor_id='42',authenticated_owner_chat_id='42')
    return document,state


def test_immutable_brief_and_visible_item_survive_store_reconstruction(pai):
    document,state=stored_brief(pai)
    restored=DurableBriefStore(pai.pg.app,owner_ref=pai.root.owner_ref)
    loaded=restored.resolve_visible(conversation_id=state.conversation_id,response_ref=state.object_refs[0].response_ref)
    assert loaded[0].content_digest==document.content_digest
    assert [item.evidence_ref for item in loaded[0].evidence]==[item.evidence_ref for item in document.evidence]
    assert restored.resolve_visible(conversation_id=state.conversation_id,response_ref='response_foreign') is None


def test_no_selected_sources_is_partial_not_a_fabricated_quiet_week(pai):
    from prm.runtime.brief import BriefRuntime
    document=BriefRuntime(pai.root).build(topic='Важное за неделю',timezone_name='Europe/Berlin')
    assert document.status!='complete' and not document.evidence


def test_brief_failed_collection_preserves_unknown_charge_and_can_be_reconciled(pai):
    from prm.runtime.brief import BriefRuntime,BriefSourceHook
    from prm.capabilities import AuthorizationRequest
    from tests.pai_runtime_fixtures import allow
    allow(pai,'archive.read','resource_failed_brief','private_archive','brief.archive',provider='provider_local',connection=None,operation='read')
    scope=AuthorizationRequest(owner_ref=pai.root.owner_ref,connection_ref=None,capability='archive.read',resource_ref='resource_failed_brief',
        operation='read',data_class='private_archive',provider_ref='provider_local',purpose='brief.archive')
    def failed(window):raise OSError('synthetic possibly processed source failure')
    document=BriefRuntime(pai.root,source_hooks=(BriefSourceHook(scope.resource_ref,scope,failed,2),),editorial=lambda doc:None).build(topic='Synthetic',timezone_name='UTC')
    assert not document.evidence
    snapshot=pai.root.registry.snapshot(pai.root.owner_ref);op=snapshot['operations'][0]
    assert op['state']=='unknown' and all(w['reserved']==0 and w['consumed']==2 for w in snapshot['windows'])
    pai.root.registry.settle(pai.root.owner_ref,op['ref'],outcome='unknown',actual=0)
    assert all(w['consumed']==0 for w in pai.root.registry.snapshot(pai.root.owner_ref)['windows'])


def test_brief_scope_denial_before_transport_releases_only_unprepared_reservation(pai,monkeypatch):
    from prm.runtime.brief import BriefRuntime,BriefSourceHook
    from prm.capabilities import AuthorizationRequest
    from tests.pai_runtime_fixtures import allow
    grant=allow(pai,'archive.read','resource_denied_brief','private_archive','brief.archive',provider='provider_local',connection=None,operation='read')
    scope=AuthorizationRequest(owner_ref=pai.root.owner_ref,connection_ref=None,capability='archive.read',resource_ref='resource_denied_brief',
        operation='read',data_class='private_archive',provider_ref='provider_local',purpose='brief.archive')
    original=pai.root.registry._commit_durable_transport;calls=[]
    def revoke(group,**kwargs):
        pai.root.registry.revoke_grant(grant.grant_id,owner_ref=pai.root.owner_ref);return original(group,**kwargs)
    monkeypatch.setattr(pai.root.registry,'_commit_durable_transport',revoke)
    doc=BriefRuntime(pai.root,source_hooks=(BriefSourceHook(scope.resource_ref,scope,lambda window:calls.append(window),2),),editorial=lambda doc:None).build(topic='Synthetic',timezone_name='UTC')
    assert not doc.evidence and calls==[]
    assert all(w['reserved']==0 and w['consumed']==0 for w in pai.root.registry.snapshot(pai.root.owner_ref)['windows'])
