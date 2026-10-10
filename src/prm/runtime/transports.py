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
        return self.send_with_options(destination,text,attempt_ref)

    def send_with_options(self,destination,text,attempt_ref,*,navigation=None,parse_mode=None):
        if destination!=self.destination_ref:raise CapabilityDenied('Telegram destination substituted')
        if not isinstance(text,str) or len(text)>3800:raise StorageError('one bounded Telegram effect per attempt; long results require reader or explicit chunk jobs')
        if parse_mode not in {None,'HTML'}:raise StorageError('unsupported trusted Telegram parse mode')
        values={'chat_id':self.owner_chat_id,'text':text,'disable_web_page_preview':'true'}
        if parse_mode:values['parse_mode']=parse_mode
        if navigation is not None:
            markup=navigation_markup(navigation)
            if markup is not None:values['reply_markup']=json.dumps(markup,ensure_ascii=False)
        body=urlencode(values).encode()
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


def navigation_markup(value):
    """Only bounded text keyboards; callbacks/URLs cannot be smuggled into metadata."""
    if not isinstance(value,dict) or value.get('kind')!='reply_keyboard':return None
    if value.get('button_text')=='Показать полный бриф' and value.get('current_visible_brief_only') is True:
        return {'keyboard':[[{'text':'Показать полный бриф'}]],'resize_keyboard':True,'one_time_keyboard':True}
    if set(value)!={'kind','keyboard','resize_keyboard','one_time_keyboard'}:raise StorageError('unknown Telegram control metadata')
    rows=value['keyboard']
    if not isinstance(rows,list) or not 1<=len(rows)<=6:raise StorageError('bounded Telegram text controls required')
    for row in rows:
        if not isinstance(row,list) or not 1<=len(row)<=3:raise StorageError('bounded Telegram control row required')
        for button in row:
            if (not isinstance(button,dict) or set(button)!={'text'} or not isinstance(button['text'],str)
                or not 1<=len(button['text'])<=90):raise StorageError('only bounded text buttons allowed')
    if value['resize_keyboard'] is not True or value['one_time_keyboard'] is not True:raise StorageError('explicit one-time controls required')
    return {key:value[key] for key in ('keyboard','resize_keyboard','one_time_keyboard')}
