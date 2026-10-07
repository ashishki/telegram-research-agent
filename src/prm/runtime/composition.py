"""One explicit composition root for Telegram, CLI and durable workers."""
from __future__ import annotations
from dataclasses import replace
import hashlib

from prm.application import PersonalResearchAssistant
from prm.capabilities import AuthorizationRequest
from prm.contracts import OperatorRequest
from prm.storage.conversations import DurableConversationStore
from prm.storage.jobs import JobQueue
from prm.storage.postgres import StorageError
from .model import ModelEndpoint, RuntimeModelAccess, ScopedModelClient
from .ingress import TelegramJobIngress, AssistantJobWorker


class AssistantRuntime:
    def __init__(self,*,target,settings,owner_ref,owner_chat_id,registry,model_endpoint=None,
                 model_resource_ref='resource_dialogue',model_upper_bound=None,history_retention_seconds=0,
                 archive_resource_ref='resource_archive',
                 public_web_bounds=None,public_search_ref='resource_public_search',public_fetch_ref='resource_public_primary',public_upper_bound=None,
                 tariff_version=None,
                 public_web_provider=None,deep_archive_reader=None,github_context_provider=None):
        if registry.store.target!=target:raise StorageError('one shared runtime policy backend required')
        self.queue=JobQueue(target);self.settings=settings;self.owner_ref=owner_ref;self.owner_chat_id=owner_chat_id
        from prm.briefs import brief_owner_ref_from_authenticated_private_tuple
        if brief_owner_ref_from_authenticated_private_tuple(owner_chat_id,owner_chat_id,owner_chat_id)!=owner_ref:
            raise StorageError('runtime owner must be derived from the exact private tuple')
        self.registry=registry;self.model_endpoint=model_endpoint;self.model_resource_ref=model_resource_ref
        self.services={}
        self.model_upper_bound=model_upper_bound
        self.tariff_version=tariff_version
        self.archive_resource_ref=archive_resource_ref
        self.public_web_bounds=public_web_bounds;self.public_search_ref=public_search_ref;self.public_fetch_ref=public_fetch_ref;self.public_upper_bound=public_upper_bound
        self.conversations=DurableConversationStore(target,owner_ref=owner_ref,history_retention_seconds=history_retention_seconds)
        from prm.storage.briefs import DurableBriefStore
        self.briefs=DurableBriefStore(target,owner_ref=owner_ref)
        self.public_web_provider=public_web_provider;self.deep_archive_reader=deep_archive_reader;self.github_context_provider=github_context_provider
        self.ingress=TelegramJobIngress(self.queue,owner_ref=owner_ref,owner_chat_id=owner_chat_id)
        self.ingress.durable_results=True
        self.ingress.cancel_callback=lambda job_id:self.conversations.cancel(self.owner_chat_id)

    def worker(self):
        return AssistantJobWorker(self.ingress,settings=self.settings,runtime=self,
            voice_resolver=self.resolve_voice if hasattr(self,'media') and hasattr(self,'media_downloader') else None)
    def resolve_voice(self,file_ref,lease):
        with self.queue.store.transaction() as tx:self.queue._fenced(tx,lease)
        content=self.media_downloader.download(file_ref,kind='voice');asset=self.media.ingest(content=content,kind='voice',mime_type='audio/ogg')
        try:
            value=self.media.extract(asset)
            if value['status']!='transcribed':raise StorageError('authorized transcription adapter unavailable')
            return value['pages'][0][1]
        finally:self.media.cleanup(asset)
    def answer_media(self,body,*,request_ref,lease):
        if not hasattr(self,'media') or not hasattr(self,'media_downloader'):raise StorageError('media adapter unavailable')
        with self.queue.store.transaction() as tx:self.queue._fenced(tx,lease)
        selection=body['media_input'];content=self.media_downloader.download(selection['file_ref'],kind=selection['kind'])
        asset=self.media.ingest(content=content,kind=selection['kind'],mime_type=selection['mime_type'])
        value=self.media.question(asset,selection['question'],request_ref=request_ref)
        from prm.contracts import AssistantResult
        return AssistantResult(request_ref,value['status'],'research',value['text'],payload={**value,'source_data_class':'user_provided'})

    def answer(self,request:OperatorRequest,*,request_ref,lease=None):
        if (request.chat_id,request.actor_id,request.owner_chat_id)!=(self.owner_chat_id,)*3:
            raise StorageError('runtime request must preserve exact private owner')
        def guard():
            if lease is not None:
                with self.queue.store.transaction() as tx:self.queue._fenced(tx,lease)
        guard()
        if hasattr(self,'actions') and request.input_kind=='text' and request.query.strip().casefold() in {'да','yes','подтверждаю'}:
            from prm.contracts import AssistantResult
            with self.queue.store.transaction() as tx:
                rows=tx.conn.execute("SELECT ref,version FROM pa_actions.proposals WHERE owner=%s AND status='prepared'",(self.owner_ref,)).fetchall()
            versions={row['ref']:str(row['version']) for row in rows}
            resolution=self.conversations.resolve_plain_yes(request.chat_id,actor_id=request.actor_id,owner_chat_id=request.owner_chat_id,proposal_versions=versions)
            if resolution.status=='resolved':
                receipt=self.actions.confirm_and_execute(resolution.confirmation_ref.proposal_ref,actor_ref=self.owner_ref)
                return AssistantResult(request_ref,receipt.status,'chat','Исход подтверждённого действия: '+receipt.status,
                    payload={'receipt_ref':receipt.idempotency_key,'source_data_class':'private_connector_content'})
            return AssistantResult(request_ref,'confirmation_unavailable','chat','Для подтверждения нужен один текущий видимый предпросмотр с точной версией.')
        lowered=request.query.casefold()
        service=None
        for name,words in {'actions':('/actpreview','/actedit','/actconfirm'),
                           'mail':('/mail','что в почте','что требует ответа в почте'),'calendar':('/calendar','покажи календарь','конфликты расписания'),
                           'contacts':('/contacts','найди адресата'),'academic':('/academic','покажи академическую сводку'),
                           'memory':('/memory','/remember','/forget'),'media':('/transcriptedit',),'brief':('/weekly',)}.items():
            if name in self.services and (request.mode!='chat' or request.query.startswith('/')) and any(lowered.startswith(word) for word in words):service=self.services[name];break
        if service is not None:
            from prm.contracts import AssistantResult
            value=service(request,request_ref,guard);guard()
            if isinstance(value,AssistantResult):return value
            if name in {'mail','calendar','contacts','academic'}:value['source_data_class']='private_connector_metadata'
            elif name=='memory':value['source_data_class']='user_provided'
            elif name=='actions':value['source_data_class']='private_connector_content'
            if value.get('status') not in {'preview'}:
                self.conversations.record_response(request.chat_id,text=value['text'],topic='',item_texts=tuple(value['text'].splitlines()[:8]))
            return AssistantResult(request_ref,value.get('status','ok'),'research',value['text'],payload=value)
        if request.query.strip().casefold() in {'/new','новая тема','начни новую тему'}:
            from prm.conversation import conversation_id_for
            with self.queue.store.transaction() as tx:
                tx.conn.execute('DELETE FROM pa_conversation.history WHERE owner=%s AND conversation_id=%s',
                                (self.owner_ref,conversation_id_for(request.chat_id)))
        client=None;access=None;groups=[];history=[]
        from prm.routing import decide_route
        route=decide_route(request.query,requested_mode=request.mode,explicit_project=request.project_name)
        if self.model_endpoint is not None and route.mode=='chat':
            endpoint=self.model_endpoint
            operation='chat_'+hashlib.sha256(request_ref.encode()).hexdigest()[:40]
            text_request=AuthorizationRequest(owner_ref=self.owner_ref,connection_ref=endpoint.connection_ref,
                capability='model.generate',resource_ref=self.model_resource_ref,operation='model_egress',data_class='user_provided',
                provider_ref=endpoint.provider_ref,purpose='answer.request',operation_ref=operation)
            decision=self.registry.authorize_and_reserve(text_request,upper_bound=self.model_upper_bound)
            if decision.allowed:
                groups.append((decision,))
                # Prior assistant output is a separate data class and purpose.
                # Omitted history is never silently substituted into text scope.
                prior=self.conversations.history_for_model(request.chat_id)[-4:]
                if prior:
                    history_request=replace(text_request,capability='model.context_egress',data_class='model_generated',
                        purpose='dialogue.history',operation_ref=operation+'_history')
                    context=self.registry.authorize_and_reserve(history_request,upper_bound=self.model_upper_bound)
                    if context.allowed:
                        groups.append((context,));history=[{'role':'assistant','content':item['text'][:2400]} for item in prior]
                access=RuntimeModelAccess(decision,self.owner_ref,endpoint.connection_ref,self.model_resource_ref)
                def observe(receipt,usage,observed_groups):
                    if self.tariff_version is None:return
                    from .cost_cache import CostCacheRuntime
                    cost=CostCacheRuntime(self).record(task_ref=request_ref,attempt_ref=operation,provider=endpoint.provider_ref,model=endpoint.model,
                        usage=usage,latency_ms=receipt.duration_ms,outcome=receipt.delivery_outcome,tariff_version=self.tariff_version)
                    if cost is not None:
                        for index,group in enumerate(observed_groups):self.registry.settle(self.owner_ref,group[0].operation_ref,outcome='accepted',actual=cost if index==0 else 0)
                client=ScopedModelClient(endpoint,self.registry,groups=groups,history=history,guard=guard,usage_observer=observe)
        options=dict(settings=self.settings,conversations=self.conversations,public_web_provider=self.public_web_provider,
                     briefs=self.briefs,public_web_bounds=self.public_web_bounds,deep_archive_reader=self.deep_archive_reader,github_context_provider=self.github_context_provider)
        public_access=None
        if request.public_web_query and self.public_web_provider is not None and self.public_web_bounds is not None:
            from .web import reserve_public_access,AuthorizedPublicWeb
            public_access=reserve_public_access(self,request.public_web_query,request_ref=request_ref,search_ref=self.public_search_ref,
                fetch_ref=self.public_fetch_ref,bounds=self.public_web_bounds,upper_bound=self.public_upper_bound)
            if public_access is not None:
                options['public_web_provider']=AuthorizedPublicWeb(self.public_web_provider,self.registry,public_access,guard=guard)
        from .archive import RuntimeArchiveTransport
        options['archive_synthesis_transport']=RuntimeArchiveTransport(self,request_ref=request_ref,guard=guard,context_resource_ref=self.archive_resource_ref)
        if client is not None:options['llm_client']=client
        assistant=PersonalResearchAssistant(**options)
        try:
            result=assistant.answer(replace(request,model_access=access,public_web_access=public_access))
            guard()
            if result.payload.get('model_call_attempted') and result.status=='ok' and type(access)is RuntimeModelAccess:
                state=self.conversations.record_response(request.chat_id,text=result.text,topic='')
                self.conversations.tag_response_source(state.object_refs[0].response_ref,'model_generated')
                result=replace(result,payload={**result.payload,'source_data_class':'model_generated',
                    'conversation':{'conversation_id':state.conversation_id,'summary_version':state.summary_version,
                                    'response_refs':[item.response_ref for item in state.object_refs],'retention':'durable_expiring'}})
            return result
        finally:
            if public_access is not None:
                for decision in (public_access.search_authorization,*public_access.fetch_authorizations):decision.reservation.abandon_before_transport()
            for group in groups:
                for decision in group:decision.reservation.abandon_before_transport()

    def attach_graph(self,transport,*,mail_selection=None,calendar_selection=None):
        if (transport.owner_ref,transport.registry)!=(self.owner_ref,self.registry):raise StorageError('selected Graph runtime owner differs')
        from .graph import GraphMailAdapter
        from .schedule import GraphScheduleRuntime
        schedule=GraphScheduleRuntime(transport)
        self.schedule_runtime=schedule
        self.brief_source_hooks=[]
        from .brief import BriefSourceHook
        from .research import LocalArchiveReader
        from prm.capabilities import AuthorizationRequest
        self.brief_source_hooks.append(BriefSourceHook(self.archive_resource_ref,AuthorizationRequest(owner_ref=self.owner_ref,
            connection_ref=None,capability='archive.read',resource_ref=self.archive_resource_ref,operation='read',data_class='private_archive',
            provider_ref='provider_local',purpose='brief.archive'),LocalArchiveReader(self.settings.db_path).window_evidence,0))
        if mail_selection is not None:
            adapter=GraphMailAdapter(transport)
            def mail(request,request_ref,guard):
                guard();sync=adapter.sync(mail_selection);guard();summary=adapter.summary(mail_selection)
                from .connector_summary import summarize_metadata
                fallback='Проверено писем в выбранном покрытии: '+str(len(summary['items']))+'. Необходимость ответа и сроки не подтверждены метаданными.\n'+summary['text']
                text,measurement=summarize_metadata(self,question=request.query,request_ref=request_ref,resource_ref=mail_selection.resource_ref,
                    items=summary['items'],fallback=fallback,guard=guard)
                return {'status':sync['status'],'text':text,'items':summary['items'],'limitations':[summary['limitation']],
                        'summary_measurement':measurement,'source_data_class':'private_connector_metadata',
                        'needed_scope_when_insufficient':{'data_class':'private_connector_content','message_refs':[item['id'] for item in summary['items'][:5]],
                            'fields':['id','body'],'provider_token_permission':'Mail.Read (account-wide); app filter is exact message selection'}}
            self.services['mail']=mail
            self.brief_source_hooks.append(BriefSourceHook(mail_selection.resource_ref,AuthorizationRequest(owner_ref=self.owner_ref,
                connection_ref=transport.connection_ref,capability='assistant.mail_read',resource_ref=mail_selection.resource_ref,operation='read',
                data_class='private_connector_metadata',provider_ref='provider_microsoft_graph',purpose='mail.read'),
                lambda window:adapter.brief_evidence(mail_selection,window),transport.upper_bound))
        if calendar_selection is not None:
            def calendar(request,request_ref,guard):
                guard();value=schedule.read_calendar(calendar_selection);guard()
                return {'status':value['status'],'text':value['text'],'coverage_complete':value['coverage_complete'],
                        'event_refs':[event.event_ref for event in value['events']],'conflicts':[list(pair) for pair in value['conflicts']]}
            self.services['calendar']=calendar
        def contacts(request,request_ref,guard):
            guard();query=request.query.removeprefix('/contacts').strip();value=schedule.resolve_contact(query);guard()
            return {'text':value['text'],'status':'partial' if not value['coverage_complete'] else 'ok',
                    'contact_refs':[item.contact_ref for item in value['contacts']]}
        self.services['contacts']=contacts

    def attach_local_services(self,*,brief_runtime=None,action_runtime=None,memory_runtime=None,academic_runtime=None):
        if memory_runtime is not None:
            self.memory=memory_runtime
            def memory(request,request_ref,guard):
                import json,uuid
                command,_,argument=request.query.partition(' ')
                actor=dict(chat_id=self.owner_chat_id,actor_id=self.owner_chat_id,owner_chat_id=self.owner_chat_id)
                guard()
                if command=='/remember':
                    ref=memory_runtime.preview(object_ref='memory_'+uuid.uuid4().hex,text=argument,source_refs=('user_request:'+request_ref,),**actor)
                    return {'status':'preview','text':'Предпросмотр сохранения: '+argument+'\nПодтверди: /memoryconfirm '+ref,'preview_ref':ref}
                if command=='/memoryconfirm':
                    item=memory_runtime.confirm(argument,**actor);return {'status':'saved','text':'Сохранено: '+item.object_id,'object_ref':item.object_id}
                if command=='/forget':
                    value=memory_runtime.forget(argument,**actor);return {'status':'deleted','text':'Память удалена. '+value['backup_limitation'],'object_ref':argument}
                item=memory_runtime.inspect(argument,**actor)
                return {'status':'found' if item else 'not_found','text':item.payload['text'] if item else 'Запись не найдена.'}
            self.services['memory']=memory
        if action_runtime is not None:
            self.actions=action_runtime
            def actions(request,request_ref,guard):
                import json
                command,_,argument=request.query.partition(' ');guard()
                if command=='/actconfirm':
                    if request.input_kind!='text':raise StorageError('editable voice transcription is not write confirmation; use the exact text/button preview')
                    receipt=action_runtime.confirm_and_execute(argument,actor_ref=self.owner_ref)
                    return {'status':receipt.status,'text':'Исход действия: '+receipt.status+'. Provider ref: '+receipt.provider_operation_ref,
                            'receipt_ref':receipt.idempotency_key,'delivery_completion':'provider acceptance is distinct from recipient delivery'}
                if command=='/actpreview':
                    value=json.loads(argument)
                    proposal=action_runtime.preview(action_code=value['action_code'],resource_ref=value['resource_ref'],content=value['content'],rationale_refs=('user_request:'+request_ref,))
                elif command=='/actedit':
                    ref,_,body=argument.partition(' ')
                    from prm.storage.actions import _proposal
                    with self.queue.store.transaction() as tx:
                        row=tx.conn.execute('SELECT payload FROM pa_actions.proposals WHERE owner=%s AND ref=%s',(self.owner_ref,ref)).fetchone()
                    if row is None:raise StorageError('proposal unavailable')
                    proposal=action_runtime.edit(_proposal(row['payload']),content=json.loads(body))
                else:raise StorageError('exact action command required')
                return {'status':'preview','text':'Предпросмотр '+proposal.action_code+': '+json.dumps(proposal.content,ensure_ascii=False)+'\n/actconfirm '+proposal.proposal_ref,
                        'proposal_ref':proposal.proposal_ref,'version':proposal.version,'content_digest':proposal.digest}
            self.services['actions']=actions
        if brief_runtime is not None:
            self.brief_runtime=brief_runtime
            self.services['brief']=lambda request,request_ref,guard:brief_runtime.answer(topic=request.query.removeprefix('/weekly').strip() or 'Важное за неделю',timezone_name='Europe/Berlin')
        if academic_runtime is not None:self.academic=academic_runtime


def runtime_from_config(config,*,target,settings):
    """Public configuration contains references; credentials stay in env only."""
    import os
    from prm.storage.policy import DurableCapabilityRegistry
    allowed={'owner_ref','owner_chat_id','budget_refs','job_budget','model','model_upper_bound','history_retention_seconds','model_resource_ref','archive_resource_ref',
             'public_web','public_upper_bound','public_search_ref','public_fetch_ref','tariff_version','graph','github','artifact_root','media_root','local_services','speech','vision','delivery','media_download'}
    if not isinstance(config,dict) or set(config)-allowed or not {'owner_ref','owner_chat_id','budget_refs','job_budget'}<=set(config):
        raise StorageError('explicit complete runtime configuration required')
    registry=DurableCapabilityRegistry(target,budget_refs=tuple(config['budget_refs']),job_budget=config['job_budget'])
    endpoint=None
    if config.get('model'):
        value=dict(config['model']);key_ref=value.pop('token_env',None)
        if 'token' in value:raise StorageError('raw credential forbidden in runtime configuration')
        if key_ref is not None and (not isinstance(key_ref,str) or not key_ref.startswith('PAI_') or not key_ref.replace('_','').isalnum()):
            raise StorageError('explicit task-specific credential environment reference required')
        endpoint=ModelEndpoint(**value,token=os.environ.get(key_ref,'') if key_ref else '')
    options={key:value for key,value in config.items() if key not in {'budget_refs','job_budget','model','public_web','graph','github','artifact_root','media_root','local_services','speech','vision','delivery','media_download'}}
    if config.get('public_web'):
        from .web import BraveSearchProvider
        from prm.public_web import PublicWebBounds
        value=config['public_web'];key_ref=value['token_env']
        if not isinstance(key_ref,str) or not key_ref.startswith('PAI_'):raise StorageError('explicit search credential reference required')
        options['public_web_provider']=BraveSearchProvider(token=os.environ.get(key_ref,''))
        options['public_web_bounds']=PublicWebBounds(**value['bounds'])
    root=AssistantRuntime(target=target,settings=settings,registry=registry,model_endpoint=endpoint,**options)
    if config.get('github'):
        from .web import GitHubReadProvider
        root.github_context_provider=GitHubReadProvider(registry=registry,owner_ref=root.owner_ref,**config['github'])
    if config.get('graph'):
        from .connections import GraphOAuth,TokenVault
        from .graph import GraphTransport
        from prm.mail_connector import MailScopeSelection
        from prm.schedule_connectors import CalendarScopeSelection
        from datetime import datetime
        value=config['graph'];key_ref=value['vault_key_env']
        if not isinstance(key_ref,str) or not key_ref.startswith('PAI_'):raise StorageError('explicit vault key reference required')
        vault=TokenVault(directory=value['vault_directory'],encryption_key=os.environ[key_ref].encode())
        manager=GraphOAuth(target=target,vault=vault,**value['oauth'])
        root.connections=manager
        transport=GraphTransport(registry=registry,connections=manager,owner_ref=root.owner_ref,connection_ref=value['connection_ref'],
            account_ref=value['account_ref'],upper_bound=value.get('upper_bound'))
        mail=None;calendar=None
        if value.get('mail_selection'):
            selected=dict(value['mail_selection'])
            for name in ('folders','sender_domains'):
                if name in selected:selected[name]=tuple(selected[name])
            for name in ('since','until'):
                if selected.get(name):selected[name]=datetime.fromisoformat(selected[name])
            mail=MailScopeSelection(**selected)
        if value.get('calendar_selection'):
            selected=dict(value['calendar_selection']);selected['calendar_refs']=tuple(selected['calendar_refs'])
            for name in ('window_start','window_end'):selected[name]=datetime.fromisoformat(selected[name])
            calendar=CalendarScopeSelection(**selected)
        root.attach_graph(transport,mail_selection=mail,calendar_selection=calendar)
        if mail is not None:
            from .watch import wire_mail_watch
            wire_mail_watch(root,transport=transport,selection=mail)
        from .actions import ActionRuntime
        root.attach_local_services(action_runtime=ActionRuntime(root,graph_transport=transport,upper_bound=value.get('action_upper_bound')))
    if config.get('local_services'):
        from .memory import MemoryRuntime
        from .brief import BriefRuntime
        from .academic import AcademicRuntime
        if not hasattr(root,'brief_source_hooks'):
            from .brief import BriefSourceHook
            from .research import LocalArchiveReader
            root.brief_source_hooks=[BriefSourceHook(root.archive_resource_ref,AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=None,
                capability='archive.read',resource_ref=root.archive_resource_ref,operation='read',data_class='private_archive',provider_ref='provider_local',purpose='brief.archive'),
                LocalArchiveReader(settings.db_path).window_evidence,0)]
        root.attach_local_services(memory_runtime=MemoryRuntime(root),brief_runtime=BriefRuntime(root,source_hooks=root.brief_source_hooks),academic_runtime=AcademicRuntime(root))
    if config.get('artifact_root'):
        from .reader import PrivateReportRuntime
        root.reader=PrivateReportRuntime(root,artifact_root=config['artifact_root'])
    if config.get('media_root'):
        from .media import MediaRuntime
        root.media=MediaRuntime(root,temporary_root=config['media_root'])
        def edit_transcript(request,request_ref,guard):
            parts=request.query.split(' ',3)
            if len(parts)!=4:raise StorageError('exact transcript ref, version and corrected text required')
            guard();item=root.media.revise_transcript(parts[1],text=parts[3],expected_version=int(parts[2]))
            return {'status':'corrected','text':'Расшифровка исправлена. Старое подтверждение больше не действует.','transcript_ref':item.object_id,'version':item.version}
        root.services['media']=edit_transcript
        if config.get('speech'):
            from .speech import SpeechTranscriber
            speech=dict(config['speech']);value=dict(speech.pop('endpoint'));key_ref=value.pop('token_env')
            if not key_ref.startswith('PAI_'):raise StorageError('explicit speech credential reference required')
            root.media.transcriber=SpeechTranscriber(root,endpoint=ModelEndpoint(**value,token=os.environ[key_ref]),**speech)
        if config.get('vision'):
            from .vision import VisionAdapter
            vision=dict(config['vision']);value=dict(vision.pop('endpoint'));key_ref=value.pop('token_env')
            if not key_ref.startswith('PAI_'):raise StorageError('explicit vision credential reference required')
            root.media.vision=VisionAdapter(root,endpoint=ModelEndpoint(**value,token=os.environ[key_ref]),**vision)
    if config.get('delivery'):
        from .transports import BoundedTelegramSender
        from .delivery import DeliveryExecutor
        value=dict(config['delivery']);key_ref=value.pop('token_env');upper=value.pop('upper_bound')
        if not key_ref.startswith('PAI_'):raise StorageError('explicit bot credential reference required')
        root.delivery=DeliveryExecutor(target,registry=registry,sender=BoundedTelegramSender(token=os.environ[key_ref],owner_chat_id=root.owner_chat_id,**value))
        root.ingress.delivery_executor=root.delivery;root.ingress.delivery_upper_bound=upper;root.ingress.destination_ref=value['destination_ref']
    if config.get('media_download'):
        from .media_download import TelegramMediaDownloader
        value=dict(config['media_download']);key_ref=value.pop('token_env')
        if not key_ref.startswith('PAI_'):raise StorageError('explicit media credential reference required')
        root.media_downloader=TelegramMediaDownloader(root,token=os.environ[key_ref],**value)
    return root
