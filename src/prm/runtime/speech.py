"""Concrete one-call STT transport under a modality-specific current grant."""
import json
import uuid
import time
from urllib.request import Request,ProxyHandler,build_opener
from prm.capabilities import AuthorizationRequest,CapabilityDenied
from prm.storage.postgres import StorageError
from .model import NoRedirect,ModelEndpoint


class SpeechTranscriber:
    def __init__(self,root,*,endpoint:ModelEndpoint,upper_bound,resource_ref=None):
        self.root,self.endpoint,self.upper_bound,self.resource_ref=root,endpoint,upper_bound,resource_ref
        self.provider_ref=endpoint.provider_ref
    def __call__(self,asset,path,*,task_ref=None):
        endpoint=self.endpoint
        if asset.owner_ref!=self.root.owner_ref:raise CapabilityDenied('foreign voice input')
        decision=self.root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=self.root.owner_ref,connection_ref=endpoint.connection_ref,
            capability='media.transcribe',resource_ref=self.resource_ref or asset.media_ref,operation='model_egress',data_class='user_provided',
            provider_ref=endpoint.provider_ref,purpose='voice.transcription',operation_ref='stt_'+asset.media_ref),upper_bound=self.upper_bound)
        if not decision.allowed:raise CapabilityDenied(decision.reason)
        boundary='pai_'+uuid.uuid4().hex;content=path.read_bytes()
        if len(content)>16000000:raise StorageError('voice input exceeds bound')
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{endpoint.model}\r\n'
              f'--{boundary}\r\nContent-Disposition: form-data; name="response_format"\r\n\r\njson\r\n'
              f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="voice.ogg"\r\nContent-Type: audio/ogg\r\n\r\n').encode()+content+f'\r\n--{boundary}--\r\n'.encode()
        def transport():
            request=Request(endpoint.endpoint,data=body,headers={'Authorization':'Bearer '+endpoint.token,'Content-Type':'multipart/form-data; boundary='+boundary})
            try:
                with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=endpoint.timeout_seconds) as response:
                    raw=response.read(64001)
                    if len(raw)>64000 or response.headers.get_content_type()!='application/json':raise StorageError('speech response bound/type differs')
                    value=json.loads(raw)
            except Exception:raise StorageError('speech outcome unknown; automatic retry denied') from None
            text=value.get('text')
            if not isinstance(text,str) or len(text)>16000:raise StorageError('speech text unavailable')
            return text
        from .cost_cache import CostCacheRuntime
        started=time.monotonic();outcome='unknown'
        try:
            text=self.root.registry.execute_reserved((decision.reservation,),transport);outcome='accepted';return text
        finally:
            CostCacheRuntime(self.root).record(task_ref=task_ref or asset.media_ref,attempt_ref='stt_'+asset.media_ref,provider=endpoint.provider_ref,
                model=endpoint.model,usage={'input':None,'cached_input':None,'cache_write':None,'output':None,'reasoning':None,'semantics':'speech_usage_unavailable'},
                latency_ms=int((time.monotonic()-started)*1000),outcome=outcome,tariff_version=self.root.tariff_version)
