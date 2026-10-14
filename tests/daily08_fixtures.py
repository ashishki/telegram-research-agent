"""Deferred package8 native fixtures; no private/live data or import-time I/O."""
from datetime import timedelta
from dataclasses import asdict
from tests.pai_runtime_fixtures import pai,allow,request
from tests.test_daily_brief_editorial import rows
from prm.runtime.memory import MemoryRuntime
from prm.runtime.brief import BriefRuntime,BriefSourceHook
from prm.capabilities import AuthorizationRequest
from prm.source_contracts import SourceBatch,SourceResource
from prm.telegram_contracts import TelegramMessageBinding


def setup(pai,*,count=6):
    root=pai.root;items=rows(pai,count);calls=[]
    grant=allow(pai,'archive.read',root.archive_resource_ref,'private_archive','brief.archive',provider='provider_local',connection=None,operation='read')
    scope=AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,capability='archive.read',resource_ref=root.archive_resource_ref,
        operation='read',data_class='private_archive',provider_ref='provider_local',purpose='brief.archive')
    def collector(window):
        calls.append(window)
        return SourceBatch.from_items(items,SourceResource(root.owner_ref,scope.resource_ref,'archive','private_archive'),checked_at=pai.now,completeness='complete',omitted_count=0)
    value=BriefRuntime(root,source_hooks=(BriefSourceHook(scope.resource_ref,scope,collector,0),),editorial=lambda doc:None)
    root.attach_local_services(memory_runtime=MemoryRuntime(root),brief_runtime=value)
    return root,value,items,calls,grant


def create(pai,index,topic='Protocol'):
    ack,value=request(pai,index,'Собери обзор недели '+topic)
    pointer=value['payload']['document_binding']
    doc,manifest=pai.root.documents.load(pointer['brief_id'],pointer['version'])
    return ack,value,doc,manifest


def bind(pai,ack,value,message_id):
    """Explicit message-binding fixture only; real HTTP delivery is separate."""
    result=pai.root.queue.status(owner=pai.root.owner_ref,job_id=ack.job_id)['result_ref']
    pai.root.ingress.bindings.bind_message(TelegramMessageBinding(pai.root.owner_ref,pai.root.ingress.telegram_destination,message_id,
        ack.job_id,response_ref=result,response_version=1,origin_kind='bot'))


def reply(pai,index,text,message_id):
    ack=pai.root.ingress.receive({'update_id':index,'message':{'message_id':index,'from':{'id':42},'chat':{'id':42,'type':'private'},'text':text,
        'reply_to_message':{'message_id':message_id,'from':{'id':99,'is_bot':True},'chat':{'id':42,'type':'private'}}}})
    ref=pai.root.worker().run_once()
    return ack,pai.root.queue.store.get(pai.root.owner_ref,'result',ref).payload


def note(pai,text,*,kind='note',object_ref='memory_fixture_context',source=None,expected_version=0,expires_at=None):
    root=pai.root
    if not hasattr(root,'memory'):root.attach_local_services(memory_runtime=MemoryRuntime(root))
    source=source or root.queue.store.put(root.owner_ref,'conversation','memory_source_'+str(expected_version),{'query':'Explicit synthetic owner note: '+text},expected_version=0)
    namespace='result' if source.object_id.startswith('private_') else 'conversation'
    actor=dict(chat_id='42',actor_id='42',owner_chat_id='42')
    ref=root.memory.preview(object_ref=object_ref,text=text,source_refs=(source.object_id,),kind=kind,expected_version=expected_version,
        source_bindings=({'namespace':namespace,'ref':source.object_id,'version':source.version,'digest':source.digest},),expires_at=expires_at,**actor)
    return root.memory.confirm(ref,**actor)
