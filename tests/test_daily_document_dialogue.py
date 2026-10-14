"""Native exact documents/versions, fresh reads and persisted export provenance."""
import json,pytest
from tests.daily08_fixtures import pai,allow,request,setup,create,bind,reply
from prm.storage.postgres import StorageError
from prm.capabilities import CapabilityDenied


def test_old_reply_after_other_document_and_restart_preserves_exact_story_and_foreground(pai):
    root,_,_,calls,_=setup(pai,count=3)
    old,old_value,first,_=create(pai,150801,'Alpha');bind(pai,old,old_value,801)
    current,current_value,second,_=create(pai,150802,'Beta')
    current_ref=root.queue.status(owner=root.owner_ref,job_id=current.job_id)['result_ref']
    from prm.storage.briefs import DurableBriefStore
    root.briefs=DurableBriefStore(pai.pg.app,owner_ref=root.owner_ref,registry=root.registry)
    _,value=reply(pai,150803,'поясни пункт 2',801)
    target=value['payload']['document_binding']
    assert (target['brief_id'],target['version'],target['story_number'])==(first.brief_id,1,2)
    assert target['brief_id']!=second.brief_id and not value['payload']['retrieval_performed'] and len(calls)==2
    with root.queue.store.transaction() as tx:assert root.focus._current(tx).payload['object_ref']==current_ref
    assert not pai.requests


def test_restyle_keeps_digest_refresh_reads_sources_and_compares_event_revisions(pai):
    root,_,items,calls,_=setup(pai,count=2);_,_,first,_=create(pai,150810)
    _,short=request(pai,150811,'сделай короче')
    assert short['payload']['document_binding']['content_digest']==first.content_digest and len(calls)==1
    items[0].update(support_span='Версия beta исправляет описание протокола.',source_version='v2')
    _,value=request(pai,150812,'обнови бриф')
    target=value['payload']['document_binding'];second,_=root.documents.load(target['brief_id'],target['version'])
    assert second.brief_id==first.brief_id and second.version==2 and second.previous_version.version==1 and len(calls)==2
    assert second.content_digest!=first.content_digest and value['payload']['brief_refresh']['new_source_search']
    assert value['payload']['brief_refresh']['changed'] and 'beta' in second.evidence[0].summary
    _,comparison=request(pai,150813,'сравни с предыдущей версией')
    assert comparison['payload']['brief_view']=='comparison' and len(calls)==2
    explicit='/document '+json.dumps({'brief_id':first.brief_id,'version':1,'action':'full'})
    _,old=request(pai,150814,explicit)
    assert old['payload']['document_binding']['content_digest']==first.content_digest


def test_ambiguous_named_document_and_wrong_story_do_not_launch_search(pai):
    root,_,_,calls,_=setup(pai,count=2);create(pai,150820,'Same');create(pai,150821,'Same')
    _,ambiguous=request(pai,150822,'обзор «Same»: поясни пункт 2')
    assert ambiguous['status']=='clarify' and len(calls)==2 and not pai.requests
    _,missing=request(pai,150823,'поясни пункт 9')
    assert missing['status']=='clarify' and len(calls)==2


def test_revoked_document_and_refresh_never_leak_old_facts_or_fall_into_model(pai):
    root,_,_,calls,grant=setup(pai,count=1);_,_,doc,_=create(pai,150830)
    root.registry.revoke_grant(grant.grant_id,owner_ref=root.owner_ref)
    _,value=request(pai,150831,'поясни пункт 1')
    assert value['status']=='clarify' and 'Событие 0' not in value['text'] and len(calls)==1
    _,refresh=request(pai,150832,'/document '+json.dumps({'brief_id':doc.brief_id,'version':1,'action':'refresh'}))
    assert refresh['status']=='clarify' and len(calls)==1 and not pai.requests


@pytest.mark.parametrize('format',['markdown','html','pdf'])
def test_exports_are_real_local_bytes_of_exact_version_and_revocation_blocks_read(pai,format):
    root,_,_,_,grant=setup(pai,count=1);_,_,doc,_=create(pai,150840)
    _,answer=request(pai,150841,'экспорт '+format)
    metadata=answer['payload']['export'];body,observed=root.documents.read_export(metadata['export_ref'],chat_id='42',actor_id='42',owner_chat_id='42')
    assert observed==format and len(body)==metadata['bytes'] and metadata['identity']['content_digest']==doc.content_digest
    if format=='pdf':assert body.startswith(b'%PDF')
    else:assert doc.evidence[0].source_ref.encode() in body
    with pytest.raises(CapabilityDenied):root.documents.read_export(metadata['export_ref'],chat_id='43',actor_id='43',owner_chat_id='42')
    root.registry.revoke_grant(grant.grant_id,owner_ref=root.owner_ref)
    with pytest.raises(CapabilityDenied):root.documents.read_export(metadata['export_ref'],chat_id='42',actor_id='42',owner_chat_id='42')


def test_new_plain_task_with_simpler_wording_does_not_restyle_old_brief(pai):
    root,_,_,calls,_=setup(pai,count=2);create(pai,150850)
    allow(pai,'model.generate',root.model_resource_ref,'user_provided','answer.request')
    _,answer=request(pai,150851,'объясни проще Python decorators')
    assert answer['status']=='ok' and answer['payload'].get('model_call_attempted') and not answer['payload'].get('brief_document') and len(calls)==1
    assert pai.requests[-1][2]['messages'][-1]['content']=='объясни проще Python decorators'
