"""One explicit composition root for Telegram, CLI and durable workers."""
from __future__ import annotations
from dataclasses import replace,asdict
from contextvars import ContextVar
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
        self.services={};self.task_context=ContextVar('pa_model_task',default=None)
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

    def endpoint_for(self,role):
        profiles=getattr(self,'model_profile_registry',None)
        if profiles is None:return self.model_endpoint
        try:return profiles.select(role=role,quality=self.quality_profile)
        except StorageError:return None

    def scoped_client(self,endpoint,*,groups,task_ref,attempt_ref,history=(),guard=None):
        task_ref=self.task_context.get() or task_ref
        def observe(receipt,usage,observed_groups):
            from .cost_cache import CostCacheRuntime
            with self.queue.store.transaction() as tx:
                if tx.conn.execute("SELECT to_regclass('pa_cache.usage') AS meta").fetchone()['meta'] is None:return
            cost=CostCacheRuntime(self).record(task_ref=task_ref,attempt_ref=attempt_ref,provider=endpoint.provider_ref,model=endpoint.model,
                usage=usage,latency_ms=receipt.duration_ms,outcome=receipt.delivery_outcome,tariff_version=self.tariff_version)
            if cost is not None:
                for index,group in enumerate(observed_groups):self.registry.settle(self.owner_ref,group[0].operation_ref,outcome='accepted',actual=cost if index==0 else 0)
        return ScopedModelClient(endpoint,self.registry,groups=groups,history=history,guard=guard,usage_observer=observe,task_ref=self.task_context.get() or task_ref)

    def worker(self):
        return AssistantJobWorker(self.ingress,settings=self.settings,runtime=self,
            voice_resolver=self.resolve_voice if hasattr(self,'media') and hasattr(self,'media_downloader') else None)
    def resolve_voice(self,file_ref,lease):
        with self.queue.store.transaction() as tx:self.queue._fenced(tx,lease)
        content=self.media_downloader.download(file_ref,kind='voice',request_ref=lease.payload['input_ref'])
        with self.queue.store.transaction() as tx:self.queue._fenced(tx,lease)
        asset=self.media.ingest(content=content,kind='voice',mime_type='audio/ogg')
        try:
            value=self.media.extract(asset,task_ref=lease.payload['input_ref'])
            if value['status']!='transcribed':raise StorageError('authorized transcription adapter unavailable')
            return value['pages'][0][1]
        finally:self.media.cleanup(asset)
    def answer_media(self,body,*,request_ref,lease):
        if not hasattr(self,'media') or not hasattr(self,'media_downloader'):raise StorageError('media adapter unavailable')
        with self.queue.store.transaction() as tx:self.queue._fenced(tx,lease)
        selection=body['media_input'];content=self.media_downloader.download(selection['file_ref'],kind=selection['kind'],request_ref=request_ref)
        with self.queue.store.transaction() as tx:self.queue._fenced(tx,lease)
        asset=self.media.ingest(content=content,kind=selection['kind'],mime_type=selection['mime_type'])
        def guard():
            with self.queue.store.transaction() as tx:self.queue._fenced(tx,lease)
        value=self.media.question(asset,selection['question'],request_ref=request_ref,guard=guard)
        from prm.contracts import AssistantResult
        return AssistantResult(request_ref,value['status'],'research',value['text'],payload={**value,'source_data_class':'user_provided'})

    def answer(self,request:OperatorRequest,*,request_ref,lease=None):
        marker=self.task_context.set(request_ref)
        try:return self._answer(request,request_ref=request_ref,lease=lease)
        finally:self.task_context.reset(marker)

    def _answer(self,request:OperatorRequest,*,request_ref,lease=None):
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
                with self.queue.store.transaction() as tx:
                    visible=tx.conn.execute("SELECT 1 FROM pa_jobs.jobs j JOIN pa_delivery.attempts a ON a.owner=j.owner AND a.id='answer_'||j.id WHERE j.owner=%s AND a.status='sent' AND j.result_ref IS NOT NULL AND EXISTS(SELECT 1 FROM pa_runtime.object_versions v WHERE v.owner=j.owner AND v.namespace='result' AND v.object_id=j.result_ref AND v.payload->'payload'->>'proposal_ref'=%s AND v.payload->'payload'->>'version'=%s) LIMIT 1",(self.owner_ref,resolution.confirmation_ref.proposal_ref,resolution.confirmation_ref.proposal_version)).fetchone()
                if visible is None:return AssistantResult(request_ref,'confirmation_unavailable','chat','Подтверждение будет доступно после доставки полного текущего предпросмотра.')
                receipt=self.actions.confirm_and_execute(resolution.confirmation_ref.proposal_ref,actor_ref=self.owner_ref)
                return AssistantResult(request_ref,receipt.status,'chat','Исход подтверждённого действия: '+receipt.status,
                    payload={'receipt_ref':receipt.idempotency_key,'source_data_class':'private_connector_content'})
            return AssistantResult(request_ref,'confirmation_unavailable','chat','Для подтверждения нужен один текущий видимый предпросмотр с точной версией.')
        if request.query.startswith('/deep '):
            import json
            from .research import DurableResearchWorker
            from prm.contracts import AssistantResult
            argument=request.query.partition(' ')[2].strip()
            plan=json.loads(argument) if argument.startswith('{') else {'schema_version':1,'question':argument,
                'steps':[{'source':'archive','query':argument}],'max_tool_calls':3,'deadline_seconds':180}
            job=DurableResearchWorker(self).enqueue(plan,idempotency_key='deep_'+request_ref)
            return AssistantResult(request_ref,'queued','research','Исследование сохранено. /status '+job+'; отмена: /cancel '+job,
                payload={'job_ref':job,'source_data_class':'user_provided','source_data_classes':['user_provided']})
        lowered=request.query.casefold()
        service=None
        for name,words in {'actions':('/actpreview','/actedit','/actconfirm','/actreconcile'),
                           'mail':('/mail','что в почте','что требует ответа в почте'),'calendar':('/calendar','покажи календарь','конфликты расписания'),
                           'contacts':('/contacts','найди адресата'),'academic':('/academic','покажи академическую сводку'),
                           'memory':('/memory','/remember','/forget'),'media':('/transcriptedit',),'brief':('/weekly',)}.items():
            if name in self.services and (request.mode!='chat' or request.query.startswith('/')) and any(lowered.startswith(word) for word in words):service=self.services[name];break
        if service is not None:
            from prm.contracts import AssistantResult
            value=service(request,request_ref,guard);guard()
            if isinstance(value,AssistantResult):return value
            if name in {'mail','calendar','contacts','academic'}:value.setdefault('source_data_class','private_connector_metadata')
            elif name=='memory':value.setdefault('source_data_class','user_provided')
            elif name=='actions':value['source_data_class']='private_connector_content'
            if value.get('status') not in {'preview'}:
                state=self.conversations.record_response(request.chat_id,text=value['text'],topic='',item_texts=tuple(value['text'].splitlines()[:8]))
                self.conversations.record_origin(state.object_refs[0].response_ref,value.get('source_data_classes',(value.get('source_data_class','user_provided'),)),source_scopes=value.get('source_scopes',()))
                value['conversation']={'response_refs':[state.object_refs[0].response_ref]}
                for ref in value.get('source_memory_refs',()):
                    self.memory.register_dependency(parent_namespace='memory',parent_ref=ref,child_namespace='result',child_ref=state.object_refs[0].response_ref)
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
                supplied=self.conversations.user_prompts_for_model(request.chat_id)
                if supplied:
                    user_history_request=replace(text_request,capability='model.context_egress',data_class='user_provided',
                        purpose='dialogue.history',operation_ref=operation+'_user_history')
                    user_context=self.registry.authorize_and_reserve(user_history_request,upper_bound=self.model_upper_bound)
                    if user_context.allowed:
                        import json
                        groups.append((user_context,))
                        history=[{'role':'user','content':'Earlier user turns, oldest first. Use the supplied facts for continuity; follow the current request and any explicit topic change. Do not claim access to files or facts that were not supplied: '+json.dumps(supplied,ensure_ascii=False)},*history[-3:]]
                access=RuntimeModelAccess(decision,self.owner_ref,endpoint.connection_ref,self.model_resource_ref)
                client=self.scoped_client(endpoint,groups=groups,history=history,guard=guard,task_ref=request_ref,attempt_ref=operation)
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
                self.conversations.record_origin(state.object_refs[0].response_ref,('model_generated',))
                self.conversations.attach_user_prompt(state.object_refs[0].response_ref,request.query)
                result=replace(result,payload={**result.payload,'source_data_class':'model_generated',
                    'conversation':{'conversation_id':state.conversation_id,'summary_version':state.summary_version,
                                    'response_refs':[item.response_ref for item in state.object_refs],'retention':'durable_expiring'}})
            if 'source_data_classes' not in result.payload:
                refs=result.payload.get('conversation',{}).get('response_refs',())
                referenced=result.payload.get('response_ref')
                if referenced:
                    # Item references inherit the visible parent response.
                    state=self.conversations.load(request.chat_id)
                    parent=next((item.response_ref for item in state.object_refs if referenced==item.response_ref or referenced in item.item_refs),referenced) if state else referenced
                    classes=self.conversations.response_origin(parent)
                    result=replace(result,payload={**result.payload,'source_scopes':list(self.conversations.response_source_scopes(parent))})
                    if refs and refs[0]!=parent:self.conversations.record_origin(refs[0],classes,source_scopes=result.payload['source_scopes'],parent_response_ref=parent)
                elif result.payload.get('source_data_class'):classes=(result.payload['source_data_class'],)
                elif result.mode=='brief':
                    from prm.conversation import conversation_id_for
                    binding=self.briefs.store.get(self.owner_ref,'conversation',self.briefs._binding_ref(conversation_id_for(request.chat_id)))
                    manifest=self.briefs.store.get(self.owner_ref,'result',self.briefs._document_ref(binding.payload['brief_id']),version=binding.payload['version']) if binding and not binding.payload.get('forgotten') else None
                    classes=tuple(manifest.payload.get('source_data_classes',('private_archive','private_connector_content'))) if manifest else ('private_archive','private_connector_content')
                    result=replace(result,payload={**result.payload,'source_scopes':manifest.payload.get('source_scopes',[]) if manifest else []})
                elif result.mode=='chat':classes=('user_provided',)
                elif request.public_web_query:classes=('public','private_archive')
                else:classes=('private_archive',)
                result=replace(result,payload={**result.payload,'source_data_classes':list(classes),'source_data_class':classes[0]})
                if refs and not referenced and not result.route.get('conversation_control'):self.conversations.record_origin(refs[0],classes,source_scopes=result.payload.get('source_scopes',()))
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
                if request.query.startswith('/mailread '):
                    argument=request.query.partition(' ')[2];message_ref,_,question=argument.partition(' ')
                    guard();item=adapter.read_message(mail_selection,message_ref);guard()
                    from .connector_summary import summarize_metadata
                    fallback=item['subject']+'\n'+item['content']+'\nИсточник: '+item['webLink']+('\nТело письма сокращено до выбранного лимита.' if item['truncated'] else '')
                    text,measurement=summarize_metadata(self,question=question or 'Какие действия явно запрошены в этом письме?',request_ref=request_ref,
                        resource_ref=message_ref,items=[item],fallback=fallback,guard=guard,data_class='private_connector_content')
                    return {'status':'partial' if item['truncated'] else 'read','text':text,'source_data_class':'private_connector_content',
                        'source_scopes':[item['source_scope']],'summary_measurement':measurement}
                guard();sync=adapter.sync(mail_selection);guard();summary=adapter.summary(mail_selection)
                from .connector_summary import summarize_metadata
                fallback='Проверено писем в выбранном покрытии: '+str(len(summary['items']))+'. Необходимость ответа и сроки не подтверждены метаданными.\n'+summary['text']
                text,measurement=summarize_metadata(self,question=request.query,request_ref=request_ref,resource_ref=mail_selection.resource_ref,
                    items=summary['items'],fallback=fallback,guard=guard)
                return {'status':sync['status'],'text':text,'items':summary['items'],'limitations':[summary['limitation']],
                        'summary_measurement':measurement,'source_data_class':'private_connector_metadata',
                        'source_scopes':[asdict(AuthorizationRequest(owner_ref=self.owner_ref,connection_ref=transport.connection_ref,capability='assistant.mail_read',resource_ref=mail_selection.resource_ref,operation='read',data_class='private_connector_metadata',provider_ref='provider_microsoft_graph',purpose='mail.read'))],
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
                        'source_scopes':[asdict(AuthorizationRequest(owner_ref=self.owner_ref,connection_ref=transport.connection_ref,capability='assistant.calendar_read',resource_ref=calendar_selection.account_ref,operation='read',data_class='private_connector_metadata',provider_ref='provider_microsoft_graph',purpose='calendar.read'))],
                        'event_refs':[event.event_ref for event in value['events']],'conflicts':[list(pair) for pair in value['conflicts']]}
            self.services['calendar']=calendar
            self.brief_source_hooks.append(BriefSourceHook(calendar_selection.account_ref,AuthorizationRequest(owner_ref=self.owner_ref,
                connection_ref=transport.connection_ref,capability='assistant.calendar_read',resource_ref=calendar_selection.account_ref,operation='read',
                data_class='private_connector_metadata',provider_ref='provider_microsoft_graph',purpose='calendar.read'),
                lambda window:schedule.brief_evidence(calendar_selection,window),transport.upper_bound))
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
                if command=='/memoryedit':
                    value=json.loads(argument)
                    current=memory_runtime.inspect(value['object_ref'],**actor)
                    if current is None:raise StorageError('memory object unavailable')
                    ref=memory_runtime.preview(object_ref=current.object_id,text=value['text'],source_refs=tuple(current.payload['source_refs']),
                        kind=current.payload['kind'],lifecycle=value.get('lifecycle',current.payload['lifecycle']),expected_version=value['version'],**actor)
                    return {'status':'preview','text':'Предпросмотр исправления: '+value['text']+'\n/memoryconfirm '+ref,'preview_ref':ref}
                if command=='/memorysearch':
                    items=memory_runtime.search(argument,**actor)
                    return {'status':'found' if items else 'not_found','text':'\n'.join(item.object_id+': '+json.dumps(item.payload,ensure_ascii=False) for item in items) or 'Записи не найдены.',
                        'source_data_class':'private_connector_content','source_data_classes':['user_provided','private_connector_content'],'source_memory_refs':[item.object_id for item in items]}
                if command=='/memoryexport':
                    return {'status':'export','text':json.dumps(memory_runtime.export(**actor),ensure_ascii=False),'source_data_class':'private_connector_content',
                        'source_data_classes':['user_provided','private_connector_content']}
                if command=='/forget':
                    value=memory_runtime.forget(argument,**actor);return {'status':value['deletion_state'],'text':('Память удалена. ' if value['deletion_state']=='complete' else 'Записи удалены, очистка файлов ещё ожидается. ')+value['backup_limitation'],'object_ref':argument}
                item=memory_runtime.inspect(argument,**actor)
                return {'status':'found' if item else 'not_found','text':item.payload.get('text',json.dumps(item.payload,ensure_ascii=False)) if item else 'Запись не найдена.','source_memory_refs':[item.object_id] if item else [],'source_data_class':'private_connector_content' if argument.startswith('academic_') else 'user_provided'}
            self.services['memory']=memory
        if action_runtime is not None:
            self.actions=action_runtime
            def actions(request,request_ref,guard):
                import json
                command,_,argument=request.query.partition(' ');guard()
                if command=='/actreconcile':
                    receipt=action_runtime.reconcile(argument)
                    return {'status':receipt.status,'text':'Результат сверки с провайдером: '+receipt.status,'receipt_ref':receipt.idempotency_key}
                if command=='/actconfirm':
                    if request.input_kind!='text':raise StorageError('editable voice transcription is not write confirmation; use the exact text/button preview')
                    parts=argument.split()
                    if len(parts)!=3:raise StorageError('exact preview reference, version and digest required')
                    receipt=action_runtime.confirm_and_execute(parts[0],actor_ref=self.owner_ref,expected_version=int(parts[1]),expected_digest=parts[2])
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
                return {'status':'preview','text':'Предпросмотр '+proposal.action_code+': '+json.dumps(proposal.content,ensure_ascii=False)+'\n/actconfirm '+proposal.proposal_ref+' '+str(proposal.version)+' '+proposal.digest,
                        'proposal_ref':proposal.proposal_ref,'version':proposal.version,'content_digest':proposal.digest}
            self.services['actions']=actions
        if brief_runtime is not None:
            self.brief_runtime=brief_runtime
            def weekly(request,request_ref,guard):
                guard()
                with self.queue.store.transaction() as tx:
                    item=tx.conn.execute("SELECT created_at FROM pa_runtime.object_versions WHERE owner=%s AND namespace='conversation' AND object_id=%s AND version=1",(self.owner_ref,request_ref)).fetchone()
                return brief_runtime.answer(topic=request.query.removeprefix('/weekly').strip() or 'Важное за неделю',timezone_name='Europe/Berlin',
                    end_at=item['created_at'] if item else None)
            self.services['brief']=weekly
        if academic_runtime is not None:self.academic=academic_runtime


def runtime_from_config(config,*,target,settings):
    """Public configuration contains references; credentials stay in env only."""
    import os
    from prm.storage.policy import DurableCapabilityRegistry
    allowed={'owner_ref','owner_chat_id','budget_refs','job_budget','model','model_upper_bound','history_retention_seconds','model_resource_ref','archive_resource_ref',
             'public_web','public_upper_bound','public_search_ref','public_fetch_ref','tariff_version','graph','github','canvas','artifact_root','media_root','local_services','speech','vision','delivery','media_download','model_profiles','quality_profile'}
    if not isinstance(config,dict) or set(config)-allowed or not {'owner_ref','owner_chat_id','budget_refs','job_budget'}<=set(config):
        raise StorageError('explicit complete runtime configuration required')
    registry=DurableCapabilityRegistry(target,budget_refs=tuple(config['budget_refs']),job_budget=config['job_budget'])
    endpoint=None
    selected_model=config.get('model')
    if config.get('model_profiles'):
        quality=config.get('quality_profile','balanced')
        if quality not in {'economical','balanced','maximum'}:raise StorageError('unsupported requested quality profile')
        # A cheaper automatic profile needs measured paired evidence. The
        # explicit baseline is used until that evidence is reviewed/installed.
        selected_quality='balanced' if quality=='economical' else quality
        selected_model=config['model_profiles'].get(selected_quality,{}).get('chat')
        if selected_model is None:raise StorageError('selected quality profile lacks a configured chat model')
    if selected_model:
        value=dict(selected_model);key_ref=value.pop('token_env',None)
        if 'token' in value:raise StorageError('raw credential forbidden in runtime configuration')
        if key_ref is not None and (not isinstance(key_ref,str) or not key_ref.startswith('PAI_') or not key_ref.replace('_','').isalnum()):
            raise StorageError('explicit task-specific credential environment reference required')
        endpoint=ModelEndpoint(**value,token=os.environ.get(key_ref,'') if key_ref else '')
    options={key:value for key,value in config.items() if key not in {'budget_refs','job_budget','model','public_web','graph','github','canvas','artifact_root','media_root','local_services','speech','vision','delivery','media_download','model_profiles','quality_profile'}}
    if config.get('public_web'):
        from .web import BraveSearchProvider
        from prm.public_web import PublicWebBounds
        value=config['public_web'];key_ref=value['token_env']
        if not isinstance(key_ref,str) or not key_ref.startswith('PAI_'):raise StorageError('explicit search credential reference required')
        options['public_web_provider']=BraveSearchProvider(token=os.environ.get(key_ref,''))
        options['public_web_bounds']=PublicWebBounds(**value['bounds'])
    root=AssistantRuntime(target=target,settings=settings,registry=registry,model_endpoint=endpoint,**options)
    if config.get('model_profiles'):
        from .profiles import ModelProfiles
        configured={}
        for quality,roles in config['model_profiles'].items():
            configured[quality]={}
            for role,description in roles.items():
                value=dict(description);key_ref=value.pop('token_env',None)
                if 'token' in value or not isinstance(key_ref,str) or not key_ref.startswith('PAI_'):raise StorageError('explicit role credential reference required')
                configured[quality][role]=ModelEndpoint(**value,token=os.environ.get(key_ref,''))
        root.model_profile_registry=ModelProfiles(configured);root.quality_profile=config.get('quality_profile','balanced')
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
        root.academic_source_hooks=[]
        from prm.academic_inbox import AcademicCandidate,categorize
        if mail is not None and 'mail' in value.get('academic_sources',()):
            from .graph import GraphMailAdapter
            def academic_mail():
                snapshot=GraphMailAdapter(transport).summary(mail)
                return tuple(AcademicCandidate('academic_'+hashlib.sha256(('mail:'+item['id']).encode()).hexdigest()[:32],root.owner_ref,'mail',
                    (item.get('subject') or 'Письмо')[:240],'Выбранные метаданные письма; тело и сроки не подтверждены.',categorize('mail',item.get('subject','')),
                    'official_message',eligibility_uncertain=True,source_refs=(item['webLink'],),source_version=hashlib.sha256(str(item).encode()).hexdigest()) for item in snapshot['items'][:48] if item.get('webLink'))
            root.academic_source_hooks.append(('mail',AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=transport.connection_ref,capability='assistant.mail_read',
                resource_ref=mail.resource_ref,operation='read',data_class='private_connector_metadata',provider_ref='provider_microsoft_graph',purpose='academic.mail'),academic_mail,0))
        if calendar is not None and 'calendar' in value.get('academic_sources',()):
            def academic_calendar():
                with root.queue.store.transaction() as tx:
                    rows=tx.conn.execute("SELECT payload FROM pa_sources.items WHERE owner=%s AND connection_ref=%s AND kind='calendar' AND NOT deleted ORDER BY id LIMIT 48",(root.owner_ref,transport.connection_ref)).fetchall()
                return tuple(AcademicCandidate('academic_'+hashlib.sha256(('calendar:'+item['event_ref']).encode()).hexdigest()[:32],root.owner_ref,'calendar',
                    item['title'][:240],'Начало события: '+item['start_at']+'; это не подтверждение срока сдачи.','uncertain','official_message',eligibility_uncertain=True,
                    source_refs=(item['source_ref'],),source_version=item.get('version','')) for row in rows if (item:=row['payload']).get('calendar_ref') in calendar.calendar_refs and item.get('source_ref'))
            root.academic_source_hooks.append(('calendar',AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=transport.connection_ref,capability='assistant.calendar_read',
                resource_ref=calendar.account_ref,operation='read',data_class='private_connector_metadata',provider_ref='provider_microsoft_graph',purpose='academic.calendar'),academic_calendar,0))

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
    if config.get('local_services'):
        from .watch import wire_archive_watch
        wire_archive_watch(root)
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
    if config.get('canvas'):
        from .academic import CanvasReadAdapter,AcademicRuntime
        from prm.academic_inbox import CanvasScopeSelection
        from datetime import datetime
        value=config['canvas'];key_ref=value['token_env']
        if not key_ref.startswith('PAI_'):raise StorageError('explicit Canvas credential reference required')
        selected=dict(value['selection']);selected['course_refs']=tuple(selected['course_refs'])
        for name in ('window_start','window_end'):selected[name]=datetime.fromisoformat(selected[name])
        selection=CanvasScopeSelection(**selected)
        adapter=CanvasReadAdapter(registry=root.registry,origin=value['origin'],credential=os.environ[key_ref],institution_access_ref=value.get('institution_access_ref'))
        academic=AcademicRuntime(root,scheduler=getattr(root,'watch_scheduler',None));root.academic=academic
        def academic_answer(request,request_ref,guard):
            command,_,argument=request.query.partition(' ')
            if command=='/academicdone':
                result=academic.mark_done(argument,actor_ref=root.owner_ref)
                return {'status':'local_done','text':'Отмечено выполненным локально. Связанные напоминания остановлены; сдача в Canvas не выполнялась.',**result,'source_data_class':'private_connector_content'}
            if command=='/academicstage':
                preview=academic.preview_stage(argument,actor_ref=root.owner_ref)
                return {'status':'preview','text':'Предпросмотр учебного этапа: '+argument+'\n/memoryconfirm '+preview,'source_data_class':'user_provided'}
            if command=='/academicwatch':
                parts=argument.split()
                if len(parts)!=3:raise StorageError('exact academic item, schedule and subject refs required')
                academic.link_watch(parts[0],schedule_id=parts[1],subject_ref=parts[2],actor_ref=root.owner_ref)
                return {'status':'linked','text':'Академическая запись связана с подтверждённой подпиской.'}
            guard();result=adapter.collect(selection,owner_ref=root.owner_ref,connection_ref=value['connection_ref'],upper_bound=value.get('upper_bound'))
            context,context_coverage=academic.selected_context()
            candidates=academic.merge(result['candidates']+context,identity_bindings=value.get('identity_bindings',{}));guard()
            result['coverage']+=context_coverage
            if any(not entry.endswith(':checked') for entry in context_coverage):result['complete']=False
            return {'status':'ok' if result['complete'] else 'partial','text':academic.describe(candidates),'coverage':result['coverage'],
                    'source_data_class':'private_connector_content','source_connections':[value['connection_ref']]}
        root.services['academic']=academic_answer
        from .brief import BriefSourceHook
        hook=BriefSourceHook(selection.account_ref,AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=value['connection_ref'],
            capability='assistant.academic_read',resource_ref=selection.account_ref,operation='read',data_class='private_connector_content',
            provider_ref='provider_canvas',purpose='academic.read'),academic.brief_evidence,value.get('upper_bound'))
        root.brief_source_hooks=getattr(root,'brief_source_hooks',[])+[hook]
        if hasattr(root,'brief_runtime'):root.brief_runtime.source_hooks=tuple(root.brief_source_hooks)
    return root
