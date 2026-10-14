"""Project-aware source-bound Brief, quiet weeks and native persisted history."""
from datetime import timedelta
from dataclasses import replace
from tests.pai_runtime_fixtures import pai,allow,request
from tests.test_daily_projects import setup,context
from prm.runtime.brief import BriefRuntime,BriefSourceHook
from prm.source_contracts import SourceResource,SourceBatch
from prm.capabilities import AuthorizationRequest
from prm.briefs import render_brief_document,BriefBuildRequest,build_brief_document


def rows(pai,count=7):
    return [{'evidence_id':'news_'+str(i),'source_url':'https://primary.example.test/news/'+str(i),
        'title':'Событие '+str(i),'support_span':'Событие '+str(i)+': найдено новое описание протокола.',
        'posted_at':(pai.now-timedelta(hours=1)).isoformat(),'local_archive_provenance':True,
        'source_version':'v1','importance':'critical' if i==6 else 'medium'} for i in range(count)]


def runtime(pai,items):
    root=pai.root
    allow(pai,'archive.read',root.archive_resource_ref,'private_archive','brief.archive',provider='provider_local',connection=None,operation='read')
    scope=AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,capability='archive.read',resource_ref=root.archive_resource_ref,operation='read',data_class='private_archive',provider_ref='provider_local',purpose='brief.archive')
    def collector(window):return SourceBatch.from_items(items,SourceResource(root.owner_ref,scope.resource_ref,'archive','private_archive'),checked_at=pai.now,completeness='complete',omitted_count=0)
    return BriefRuntime(root,source_hooks=(BriefSourceHook(scope.resource_ref,scope,collector,0),),editorial=lambda doc:None)


def test_native_priorities_keep_required_change_five_events_and_three_optional_continuations(pai):
    from prm.runtime.memory import MemoryRuntime
    value=runtime(pai,rows(pai));pai.root.attach_local_services(memory_runtime=MemoryRuntime(pai.root),brief_runtime=value)
    _,answer=request(pai,141800,'Собери обзор недели Протокол')
    assert answer['status'] in {'ok','partial','complete'}
    from prm.conversation import conversation_id_for
    binding=pai.root.briefs.store.get(pai.root.owner_ref,'conversation',pai.root.briefs._binding_ref(conversation_id_for('42'))).payload
    manifest=pai.root.briefs.store.get(pai.root.owner_ref,'result',pai.root.briefs._document_ref(binding['brief_id']),version=1)
    document=pai.root.briefs._decode_document(manifest)
    assert len(document.editorial.stories)==5 and sum(bool(s.next_step) for s in document.editorial.stories)==3
    assert any('Событие 6' in s.summary for s in document.editorial.stories)
    assert manifest.payload['event_selection']['signals'][0]['importance']=='critical'
    assert manifest.payload['event_selection']['events'][0]['last_surfaced_at'] is None
    assert not pai.requests


def test_no_news_is_valid_and_repeated_week_does_not_create_new_stories(pai):
    value=runtime(pai,[])
    empty=value.build(topic='Протокол',timezone_name='UTC',end_at=pai.now)
    assert empty.status=='empty' and not empty.editorial.stories and 'важных изменений' in render_brief_document(empty)
    items=rows(pai,3);value=runtime(pai,items)
    value.answer(topic='Протокол',timezone_name='UTC',end_at=pai.now)
    # Reconstruct the store to prove this is durable history, not an instance list.
    from prm.storage.briefs import DurableBriefStore
    pai.root.briefs=DurableBriefStore(pai.pg.app,owner_ref=pai.root.owner_ref,registry=pai.root.registry)
    second=value.build(topic='Протокол',timezone_name='UTC',end_at=pai.now)
    assert not second.editorial.stories
    assert all(e['novelty']=='repeated' for e in pai.root.briefs.pending_events[second.content_digest]['events'])
    assert 'важных изменений' in render_brief_document(second)
    items[0]['support_span']='Исправление: обнаружен другой протокол.';items[0]['title']='Исправление протокола';items[0]['source_version']='v2'
    changed=value.build(topic='Протокол',timezone_name='UTC',end_at=pai.now)
    assert len(changed.editorial.stories)==1
    assert any(e['novelty']=='changed' for e in pai.root.briefs.pending_events[changed.content_digest]['events'])


def test_project_uses_only_current_confirmed_exact_relationship_and_no_obligation(pai):
    root,actor,source=setup(pai)
    text='Синтетический эксперимент проверяет ограниченный сценарий.'
    evidence=root.queue.store.put(root.owner_ref,'result','project_news_proof',{'text':text,'data_classes':['user_provided']},expected_version=0)
    c=context(pai,source)
    c['relationships']=[{'evidence_ref':evidence.object_id,'evidence_version':1,'evidence_digest':evidence.digest,
        'quote':text,'relation':'Помогает проверить текущую цель','experiment':'Проверить один локальный сценарий',
        'reject_if':'Измерение не подтверждает эффект'}]
    preview=root.projects.preview(object_ref='project_aurora',context=c,**actor);root.memory.confirm(preview,**actor)
    items=rows(pai,1);items[0].update(title='Ограниченный сценарий',support_span=text,
        dependency_ref={'namespace':'result','object_ref':evidence.object_id,'version':1,'digest':evidence.digest})
    value=runtime(pai,items);document=value.build(topic='Сценарий',timezone_name='UTC',end_at=pai.now)
    story=document.editorial.stories[0]
    assert 'Aurora' in story.why_selected and story.next_step.startswith('Возможный эксперимент:') and 'Измерение' in story.caveat
    assert all('обязан' not in s.next_step for s in document.editorial.stories)
    assert any(d['namespace']=='memory' and d['object_ref']=='project_aurora' for d in root.briefs.pending_dependencies[document.content_digest])
    # A keyword/name match and an old evidence version cannot manufacture the link.
    items[0].pop('dependency_ref');items[0]['title']='Aurora'
    weak=value.build(topic='Сценарий',timezone_name='UTC',end_at=pai.now)
    assert 'Aurora' not in weak.editorial.stories[0].why_selected and 'Возможный эксперимент' not in weak.editorial.stories[0].next_step
    items[0]['dependency_ref']={'namespace':'result','object_ref':evidence.object_id,'version':2,'digest':evidence.digest}
    changed=value.build(topic='Сценарий',timezone_name='UTC',end_at=pai.now)
    assert 'Возможный эксперимент' not in changed.editorial.stories[0].next_step


def test_corrected_deadlines_with_same_canonical_url_are_preserved_in_document(pai):
    items=rows(pai,2)
    for i,item in enumerate(items):item.update(canonical_url='https://primary.example.test/deadline',conflict_group='deadline',conflict_value=str(20+2*i),
        support_span='Приём закрывается '+str(20+2*i)+' октября.',title='Срок приёма',source_version='v'+str(i))
    document=runtime(pai,items).build(topic='Срок',timezone_name='UTC',end_at=pai.now)
    assert len(document.evidence)==2 and len(document.conflicts)==1
    assert all('расходятся' in s.caveat for s in document.editorial.stories)
    assert not document.deduplication


def test_uncertain_same_family_and_explicit_source_versions_are_not_suppressed():
    from tests.test_assistant_briefs import _window,_evidence
    a=_evidence('one','https://t.me/example/1',title='One',summary='Version alpha remains available.',repost_family_id='shared_family')
    b=_evidence('two','https://t.me/example/2',title='Two',summary='Version beta remains available.',repost_family_id='shared_family')
    document=build_brief_document(BriefBuildRequest('Versions',_window(),(a,b)))
    assert len(document.evidence)==2 and not document.deduplication
    b.update(support_span=a['support_span'],source_version='v2')
    a['source_version']='v1'
    document=build_brief_document(BriefBuildRequest('Versions',_window(),(a,b)))
    assert len(document.evidence)==2 and not document.deduplication


def test_model_cannot_relabel_opportunity_as_obligation_or_remove_required_event(pai):
    from prm.brief_editorial import BriefEditorial,BriefStory,StoryAnchor
    items=rows(pai)
    value=runtime(pai,items)
    def malicious(document):
        source=document.evidence[0]
        return BriefEditorial((BriefStory('Invented verified deadline','You must submit immediately.',
            'Submission is mandatory.','Submission is mandatory.','Confirmed urgent obligation.',
            'Submit the coursework automatically.','', (StoryAnchor(source.evidence_ref,source.summary),)),),
            tuple(e.evidence_ref for e in document.evidence if e!=source))
    value.editorial=malicious
    document=value.build(topic='Протокол',timezone_name='UTC',end_at=pai.now)
    assert len(document.editorial.stories)==5 and any('Событие 6' in s.summary for s in document.editorial.stories)
    assert all('must submit' not in s.summary and 'automatically' not in s.next_step for s in document.editorial.stories)
