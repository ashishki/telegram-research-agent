"""Bounded Telegram file metadata/download under one current source scope."""
import json
import time
import uuid
from urllib.parse import urlencode,quote
from urllib.request import Request,ProxyHandler,build_opener
from prm.capabilities import AuthorizationRequest,CapabilityDenied
from prm.storage.postgres import StorageError
from .model import NoRedirect


class TelegramMediaDownloader:
    def __init__(self,root,*,token,resource_ref,upper_bound,origin='https://api.telegram.org'):
        if origin!='https://api.telegram.org' or not token or '\n' in token or '\r' in token:raise StorageError('explicit Telegram media connection required')
        self.root,self._token,self.resource_ref,self.upper_bound,self.origin=root,token,resource_ref,upper_bound,origin
    def download(self,file_ref,*,kind):
        if not isinstance(file_ref,str) or not 0<len(file_ref)<=512:raise StorageError('bounded inbound file ref required')
        decision=self.root.registry.authorize_and_reserve(AuthorizationRequest(owner_ref=self.root.owner_ref,connection_ref=None,
            capability='media.voice_download' if kind=='voice' else 'media.file_download',resource_ref=self.resource_ref,operation='read',data_class='user_provided',
            provider_ref='provider_telegram',purpose='voice.transcription' if kind=='voice' else 'media.download',operation_ref='download_'+uuid.uuid4().hex),upper_bound=self.upper_bound)
        if not decision.allowed:raise CapabilityDenied(decision.reason)
        def transport():
            deadline=time.monotonic()+8;opener=build_opener(ProxyHandler({}),NoRedirect())
            try:
                with opener.open(Request(self.origin+'/bot'+self._token+'/getFile?'+urlencode({'file_id':file_ref})),timeout=max(.1,deadline-time.monotonic())) as response:
                    raw=response.read(64001)
                    if len(raw)>64000:raise StorageError('file metadata exceeds bound')
                    value=json.loads(raw)
                metadata=value.get('result',{})
                if value.get('ok') is not True or metadata.get('file_id')!=file_ref or metadata.get('file_size',16000001)>16000000:
                    raise StorageError('file identity or size differs')
                path=metadata.get('file_path')
                if not isinstance(path,str) or path.startswith('/') or '..' in path.split('/') or len(path)>512:raise StorageError('file path substituted')
                with opener.open(Request(self.origin+'/file/bot'+self._token+'/'+quote(path,safe='/')),timeout=max(.1,deadline-time.monotonic())) as response:
                    content=response.read(16000001)
                    if len(content)>16000000 or time.monotonic()>deadline:raise StorageError('download bound exceeded')
                return content
            except Exception:raise StorageError('bounded media download unavailable') from None
        return self.root.registry.execute_reserved((decision.reservation,),transport)
