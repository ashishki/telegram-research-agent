"""Concrete bounded foreground/background Telegram transport; no implicit key."""
import hashlib
import json
from urllib.parse import urlsplit,urlencode,quote
from urllib.request import Request,ProxyHandler,build_opener
from urllib.error import HTTPError
from .model import NoRedirect
from .delivery import TransportReceipt,KnownDeliveryRejection
from prm.storage.postgres import StorageError
from prm.capabilities import CapabilityDenied


class BoundedTelegramSender:
    def __init__(self,*,token,owner_chat_id,destination_ref,origin='https://api.telegram.org',synthetic=False):
        if not isinstance(token,str) or not token or '\n' in token or '\r' in token:raise StorageError('explicit bounded bot credential required')
        parsed=urlsplit(origin)
        if synthetic:
            if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or not parsed.port:raise StorageError('literal synthetic Telegram origin required')
        elif origin!='https://api.telegram.org':raise StorageError('selected Telegram origin required')
        if not owner_chat_id.isdigit() or owner_chat_id.startswith('0'):raise StorageError('positive exact private chat required')
        self._token,self.owner_chat_id,self.destination_ref,self.origin=token,owner_chat_id,destination_ref,origin
    def __call__(self,destination,text,attempt_ref):
        if destination!=self.destination_ref:raise CapabilityDenied('Telegram destination substituted')
        if not isinstance(text,str) or len(text)>3800:raise StorageError('one bounded Telegram effect per attempt; long results require reader or explicit chunk jobs')
        body=urlencode({'chat_id':self.owner_chat_id,'text':text,'disable_web_page_preview':'true'}).encode()
        try:
            with build_opener(ProxyHandler({}),NoRedirect()).open(Request(self.origin+'/bot'+self._token+'/sendMessage',data=body,
                headers={'Content-Type':'application/x-www-form-urlencoded'}),timeout=8) as response:
                raw=response.read(64001)
                if len(raw)>64000:raise StorageError('Telegram response exceeds bound')
                value=json.loads(raw)
        except HTTPError as error:
            if 400<=error.code<500:raise KnownDeliveryRejection('provider rejected exact request') from None
            raise StorageError('Telegram outcome unknown') from None
        except Exception:raise StorageError('Telegram outcome unknown') from None
        if value.get('ok') is not True:raise KnownDeliveryRejection('provider negative response')
        result=value.get('result',{})
        if str(result.get('chat',{}).get('id'))!=self.owner_chat_id or type(result.get('message_id'))is not int:
            raise StorageError('Telegram receipt recipient/identity unavailable')
        return TransportReceipt('telegram:'+self.owner_chat_id+':'+str(result['message_id']))
