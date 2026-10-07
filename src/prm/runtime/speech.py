"""Concrete one-call STT transport under a modality-specific current grant."""
import json
import uuid
import hashlib
from urllib.request import Request,ProxyHandler,build_opener
from urllib.error import HTTPError
from .model_errors import ModelProviderRejected,ModelResponseInvalid,DEFINITIVE_REJECTIONS
from prm.capabilities import AuthorizationRequest,CapabilityDenied
from prm.storage.postgres import StorageError
from .model import NoRedirect,ModelEndpoint
from .media_attempts import read_bounded_media,execute_fenced_media


class SpeechTranscriber:
    def __init__(self,root,*,endpoint:ModelEndpoint,upper_bound,resource_ref=None):
        self.root,self.endpoint,self.upper_bound,self.resource_ref=root,endpoint,upper_bound,resource_ref
        self.provider_ref=endpoint.provider_ref
    def __call__(self,asset,path,*,task_ref=None):
        endpoint=self.endpoint
        if asset.owner_ref!=self.root.owner_ref or asset.kind!='voice':raise CapabilityDenied('owned voice input required')
        decision=self.root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=self.root.owner_ref,connection_ref=endpoint.connection_ref,
            capability='media.transcribe',resource_ref=self.resource_ref or asset.media_ref,operation='model_egress',data_class='user_provided',
            provider_ref=endpoint.provider_ref,purpose='voice.transcription',operation_ref='stt_'+asset.media_ref),upper_bound=self.upper_bound)
        if not decision.allowed:raise CapabilityDenied(decision.reason)
        try:content=read_bounded_media(asset,path,maximum=16000000,signatures={'audio/ogg':b'OggS'})
        except Exception:
            decision.reservation.abandon_before_transport()
            raise
        boundary='pai_'+uuid.uuid4().hex
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{endpoint.model}\r\n'
              f'--{boundary}\r\nContent-Disposition: form-data; name="response_format"\r\n\r\njson\r\n'
              f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="voice.ogg"\r\nContent-Type: audio/ogg\r\n\r\n').encode()+content+f'\r\n--{boundary}--\r\n'.encode()
        http_attempted=False
        def transport():
            nonlocal http_attempted
            request=Request(endpoint.endpoint,data=body,headers={'Authorization':'Bearer '+endpoint.token,'Content-Type':'multipart/form-data; boundary='+boundary})
            try:
                http_attempted=True
                with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=endpoint.timeout_seconds) as response:
                    raw=response.read(64001)
                    if len(raw)>64000 or response.headers.get_content_type()!='application/json':raise ModelResponseInvalid()
                    value=json.loads(raw)
            except HTTPError as error:
                if error.code in DEFINITIVE_REJECTIONS:raise ModelProviderRejected(error.code) from None
                raise StorageError('speech transport outcome unknown; do not retry') from None
            except ModelResponseInvalid:raise
            except (json.JSONDecodeError,UnicodeDecodeError):raise ModelResponseInvalid() from None
            except Exception:raise StorageError('speech transport outcome unknown; do not retry') from None
            if not isinstance(value,dict):raise ModelResponseInvalid()
            text=value.get('text')
            if not isinstance(text,str) or len(text)>16000:raise ModelResponseInvalid()
            return text
        from .cost_cache import CostCacheRuntime
        from .model_attempts import prepare_model_attempt
        try:attempt_ref=prepare_model_attempt(self.root.queue.store,owner=self.root.owner_ref,task_ref=task_ref or asset.media_ref,purpose='voice.transcription',operation_refs=(decision.operation_ref,),input_digest=hashlib.sha256(body).hexdigest())
        except Exception:
            decision.reservation.abandon_before_transport()
            raise
        def record(outcome,duration_ms):
            CostCacheRuntime(self.root).record(task_ref=task_ref or asset.media_ref,attempt_ref='stt_'+asset.media_ref,provider=endpoint.provider_ref,
                model=endpoint.model,usage={'input':None,'cached_input':None,'cache_write':None,'output':None,'reasoning':None,'semantics':'speech_usage_unavailable'},
                latency_ms=duration_ms,outcome=outcome,tariff_version=self.root.tariff_version)
        return execute_fenced_media(self.root.registry,decision.reservation,transport,record,attempt_ref=attempt_ref,
            model=endpoint.model,http_attempted=lambda:http_attempted)
