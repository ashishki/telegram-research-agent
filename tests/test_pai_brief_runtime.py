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
