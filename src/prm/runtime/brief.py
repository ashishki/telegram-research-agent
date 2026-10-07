"""Weekly selected sources -> immutable Brief -> application and delivery."""
from dataclasses import dataclass,replace
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from prm.briefs import BriefBuildRequest,BriefWindow,CoverageSource,build_brief_document,render_brief_document
from prm.contracts import OperatorRequest
from prm.storage.postgres import StorageError


@dataclass(frozen=True)
class BriefSourceHook:
    source_ref: str
    authorization_request: object
    collector: object
    upper_bound: int | None


class BriefRuntime:
    def __init__(self,root,*,source_hooks=(),editorial=None):
        if len(source_hooks)>16:raise StorageError('bounded selected Brief sources required')
        self.root,self.source_hooks=root,tuple(source_hooks)
        self.editorial=editorial or (RuntimeBriefEditorial(root) if root.model_endpoint is not None else None)

    def build(self,*,topic,timezone_name,end_at=None,previous_document=None,comparison_document=None):
        zone=ZoneInfo(timezone_name);end=(end_at or datetime.now(timezone.utc)).astimezone(zone)
        window=BriefWindow(timezone_name,end-timedelta(days=7),end,datetime.now(timezone.utc))
        evidence=[];coverage=[];limits=[]
        for hook in self.source_hooks:
            if hook.authorization_request.owner_ref!=self.root.owner_ref or hook.authorization_request.resource_ref!=hook.source_ref:
                raise StorageError('Brief hook source scope differs')
            import uuid
            decision=self.root.registry.authorize_and_reserve(replace(hook.authorization_request,operation_ref='briefsource_'+uuid.uuid4().hex),upper_bound=hook.upper_bound)
            if not decision.allowed:
                coverage.append(CoverageSource(hook.source_ref,'unavailable','scope denied'));continue
            try:
                batch=self.root.registry.execute_reserved((decision.reservation,),lambda:hook.collector(window))
                if not isinstance(batch,(list,tuple)) or len(batch)>48:raise StorageError('Brief source batch exceeds bound')
                if any(item.get('local_source_provenance') and item.get('source_owner_ref')!=self.root.owner_ref for item in batch):
                    raise StorageError('Brief personal source owner differs')
                evidence.extend(batch);coverage.append(CoverageSource(hook.source_ref,'checked'))
            except Exception:
                coverage.append(CoverageSource(hook.source_ref,'unavailable','collection unavailable'))
        if not self.source_hooks:limits.append('selected_sources_unavailable')
        request=BriefBuildRequest(topic,window,tuple(evidence[:48]),self.root.owner_ref,tuple(coverage),tuple(limits),
            previous_document=previous_document,comparison_document=comparison_document,period_basis='explicit_requested_range')
        document=build_brief_document(request)
        if self.editorial is not None:
            editorial=self.editorial(document)
            if editorial is not None:document=build_brief_document(replace(request,editorial=editorial))
        return document

    def answer(self,*,topic,timezone_name,end_at=None):
        from prm.application import PersonalResearchAssistant
        document=self.build(topic=topic,timezone_name=timezone_name,end_at=end_at)
        assistant=PersonalResearchAssistant(settings=self.root.settings,conversations=self.root.conversations,briefs=self.root.briefs)
        request=OperatorRequest(query=topic,mode='brief',chat_id=self.root.owner_chat_id,
            actor_id=self.root.owner_chat_id,owner_chat_id=self.root.owner_chat_id)
        from prm.briefs import rebuild_brief_request
        return assistant.render_brief_document(request,rebuild_brief_request(document))


class RuntimeBriefEditorial:
    def __init__(self,root):self.root=root
    def __call__(self,document):
        import hashlib,json,uuid
        from prm.capabilities import AuthorizationRequest
        from prm.brief_editorial import BriefEditorial
        from .model import ScopedModelClient
        if not document.evidence:return None
        root=self.root;endpoint=root.model_endpoint;operation='briefeditorial_'+uuid.uuid4().hex;groups=[]
        scopes=[('model.generate',root.model_resource_ref,'user_provided','answer.request'),
                ('model.context_egress',root.archive_resource_ref,'private_archive','brief.editorial_archive'),
                ('model.context_egress','resource_personal_brief','private_connector_metadata','brief.editorial_personal')]
        for index,(capability,resource,data_class,purpose) in enumerate(scopes):
            decision=root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=root.owner_ref,connection_ref=endpoint.connection_ref,
                capability=capability,resource_ref=resource,operation='model_egress',data_class=data_class,provider_ref=endpoint.provider_ref,
                purpose=purpose,operation_ref=operation+'_'+str(index)),upper_bound=root.model_upper_bound)
            if not decision.allowed:
                for group in groups:group[0].reservation.abandon_before_transport()
                return None
            groups.append((decision,))
        sources=[{'evidence_ref':item.evidence_ref,'title':item.title,'summary':item.summary,'source_ref':item.source_ref} for item in document.evidence]
        client=ScopedModelClient(endpoint,root.registry,groups=groups,history=({'role':'user','content':'Untrusted selected evidence: '+json.dumps(sources,ensure_ascii=False)},))
        try:
            receipt=client.complete_with_receipt(prompt=document.topic,
                system='Return JSON {stories:[{title,summary,explanation,plain_explanation,why_selected,next_step,caveat,anchors:[{evidence_ref,quote}]}],omitted_refs:[]}. Select at most five actual events. Each quote must be an exact selected source substring of at least 16 characters. Explain importance separately from facts. Preserve deadlines/conflicts/coverage. No tools or external claims.',
                max_tokens=3500,category='brief_editorial',authorization=groups[0][0],data_class='user_provided',owner_ref=root.owner_ref,
                connection_ref=endpoint.connection_ref,resource_ref=root.model_resource_ref)
            return BriefEditorial.from_dict(json.loads(receipt.text),document.evidence)
        except Exception:return None
        finally:
            for group in groups:group[0].reservation.abandon_before_transport()
