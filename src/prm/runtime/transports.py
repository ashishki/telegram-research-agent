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
from prm.telegram_contracts import TelegramDestination, TelegramOutcome


class BotAPITransport:
    """A bounded, no-redirect request layer with explicit unknown outcomes."""
    METHODS = frozenset({'sendMessage', 'answerCallbackQuery', 'getUpdates'})
    RICH_METHODS=frozenset({'sendRichMessage','editMessageText'})

    def __init__(self, *, token, origin='https://api.telegram.org', synthetic=False,rich_messages=False):
        if not isinstance(token, str) or not token or len(token) > 512 or '\n' in token or '\r' in token:
            raise StorageError('explicit bounded bot credential required')
        parsed = urlsplit(origin)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'', '/'}:
            raise StorageError('fixed Telegram API origin required')
        if synthetic:
            if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port:
                raise StorageError('literal synthetic Telegram origin required')
        elif origin != 'https://api.telegram.org': raise StorageError('selected Telegram origin required')
        self._token, self.origin = token, origin.rstrip('/')
        if type(rich_messages)is not bool:raise StorageError('explicit rich feature flag required')
        self.rich_messages=rich_messages

    def request(self, method, values, *, timeout_seconds=8):
        if method not in self.METHODS and not (self.rich_messages and method in self.RICH_METHODS) or not isinstance(values, dict) or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 35:
            raise StorageError('bounded supported Telegram request required')
        data = urlencode(values).encode()
        if len(data) > (1572864 if method in self.RICH_METHODS else 128000): raise StorageError('Telegram request exceeds bound')
        maximum = 1048576 if method == 'getUpdates' else 512000 if method in self.RICH_METHODS else 64000
        status = 200
        try:
            request = Request(self.origin + '/bot' + self._token + '/' + method, data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'telegram-research-agent/1.0'}, method='POST')
            try:
                with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout_seconds) as response:
                    status = response.status
                    if response.headers.get_content_type() != 'application/json': return TelegramOutcome('unknown')
                    raw = response.read(maximum + 1)
            except HTTPError as error:
                status = error.code
                try: raw = error.read(maximum + 1)
                finally: error.close()
            if len(raw) > maximum: return TelegramOutcome('unknown')
            value = json.loads(raw)
        except Exception:
            # No exception/provider body or token-bearing URL leaves this layer.
            return TelegramOutcome('unknown')
        if not isinstance(value, dict): return TelegramOutcome('unknown')
        if value.get('ok') is True and 200 <= status < 300 and 'result' in value:
            return TelegramOutcome('accepted', value['result'])
        code = value.get('error_code')
        if value.get('ok') is not False or type(code) is not int or not 400 <= code < 500:
            return TelegramOutcome('unknown')
        parameters = value.get('parameters', {})
        retry = parameters.get('retry_after') if isinstance(parameters, dict) else None
        if type(retry) is not int or not 1 <= retry <= 86400: retry = None
        description=value.get('description','')
        format_rejected=bool(method in self.RICH_METHODS and code==400 and isinstance(description,str) and description.casefold().startswith((
            "bad request: can't parse rich message","bad request: invalid rich message","bad request: rich message format is not supported",
            'bad request: method sendrichmessage is not supported')))
        return TelegramOutcome('known_rejected', error_code=code, retry_after=retry,format_rejected=format_rejected)


class BoundedTelegramSender:
    def __init__(self,*,token,owner_chat_id,destination_ref,origin='https://api.telegram.org',synthetic=False,bot_ref='bot_default',message_thread_id=None,rich_messages=False):
        if not isinstance(token,str) or not token or '\n' in token or '\r' in token:raise StorageError('explicit bounded bot credential required')
        parsed=urlsplit(origin)
        if synthetic:
            if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or not parsed.port:raise StorageError('literal synthetic Telegram origin required')
        elif origin!='https://api.telegram.org':raise StorageError('selected Telegram origin required')
        if not owner_chat_id.isdigit() or owner_chat_id.startswith('0'):raise StorageError('positive exact private chat required')
        self._token,self.owner_chat_id,self.destination_ref,self.origin=token,owner_chat_id,destination_ref,origin
        self.destination = TelegramDestination(chat_id=owner_chat_id, bot_ref=bot_ref, message_thread_id=message_thread_id)
        self.api = BotAPITransport(token=token, origin=origin, synthetic=synthetic,rich_messages=rich_messages)
        self.rich_messages=rich_messages
    def __call__(self,destination,text,attempt_ref):
        return self.send_with_options(destination,text,attempt_ref)

    def send_with_options(self,destination,text,attempt_ref,*,navigation=None,parse_mode=None,reply_to_message_id=None):
        if destination!=self.destination_ref:raise CapabilityDenied('Telegram destination substituted')
        if not isinstance(text,str) or len(text)>3800:raise StorageError('one bounded Telegram effect per attempt; long results require reader or explicit chunk jobs')
        if parse_mode not in {None,'HTML'}:raise StorageError('unsupported trusted Telegram parse mode')
        values={'chat_id':self.owner_chat_id,'text':text,'disable_web_page_preview':'true'}
        if self.destination.message_thread_id is not None: values['message_thread_id'] = self.destination.message_thread_id
        if reply_to_message_id is not None:
            if type(reply_to_message_id) is not int or not 0 < reply_to_message_id < 2**63: raise StorageError('exact reply message required')
            values['reply_parameters'] = json.dumps({'message_id': reply_to_message_id, 'allow_sending_without_reply': False})
        if parse_mode:values['parse_mode']=parse_mode
        if navigation is not None:
            markup=navigation_markup(navigation)
            if markup is not None:values['reply_markup']=json.dumps(markup,ensure_ascii=False)
        outcome = self.api.request('sendMessage', values)
        if outcome.kind == 'known_rejected':
            error = KnownDeliveryRejection('provider rejected exact request')
            error.retry_after = outcome.retry_after; error.error_code = outcome.error_code
            raise error
        if outcome.kind != 'accepted': raise StorageError('Telegram outcome unknown')
        result = outcome.result
        if (not isinstance(result, dict) or not isinstance(result.get('chat'), dict)
            or str(result['chat'].get('id'))!=self.owner_chat_id or result['chat'].get('type', 'private') != 'private'
            or type(result.get('message_id'))is not int or not 0 < result['message_id'] < 2**63
            or result.get('message_thread_id') != self.destination.message_thread_id):
            raise StorageError('Telegram receipt recipient/identity unavailable')
        return TransportReceipt('telegram:'+self.owner_chat_id+':'+str(result['message_id']),
            destination=self.destination, message_id=result['message_id'], method='sendMessage')

    def send_rich_with_options(self,destination,rich_message,attempt_ref,*,source_urls=(),callback_tokens=(),message_id=None):
        if destination!=self.destination_ref:raise CapabilityDenied('Telegram destination substituted')
        if not self.rich_messages:raise StorageError('rich presentation not selected')
        from prm.telegram_rich import validate_rich_message
        validate_rich_message(rich_message,source_urls=source_urls,callback_tokens=callback_tokens)
        values={'chat_id':self.owner_chat_id,'rich_message':json.dumps(rich_message,ensure_ascii=False)}
        method='sendRichMessage'
        if message_id is not None:
            if type(message_id)is not int or not 0<message_id<2**63:raise StorageError('exact rich edit message required')
            values['message_id']=message_id;method='editMessageText'
        elif self.destination.message_thread_id is not None:values['message_thread_id']=self.destination.message_thread_id
        outcome=self.api.request(method,values)
        if outcome.kind=='known_rejected':
            error=KnownDeliveryRejection('provider rejected exact rich request')
            error.format_rejected=outcome.format_rejected;error.error_code=outcome.error_code;error.retry_after=outcome.retry_after
            raise error
        if outcome.kind!='accepted':raise StorageError('Telegram rich outcome unknown')
        result=outcome.result
        if (not isinstance(result,dict) or not isinstance(result.get('chat'),dict) or str(result['chat'].get('id'))!=self.owner_chat_id
            or result['chat'].get('type','private')!='private' or type(result.get('message_id'))is not int or not 0<result['message_id']<2**63
            or message_id is not None and result['message_id']!=message_id or result.get('message_thread_id')!=self.destination.message_thread_id):raise StorageError('rich receipt identity unavailable')
        return TransportReceipt('telegram:'+self.owner_chat_id+':'+str(result['message_id']),destination=self.destination,message_id=result['message_id'],method=method)


def navigation_markup(value):
    """Only bounded text keyboards; callbacks/URLs cannot be smuggled into metadata."""
    if not isinstance(value,dict):return None
    if value.get('kind') == 'inline_keyboard':
        import re
        if set(value) != {'kind', 'inline_keyboard'}: raise StorageError('unknown inline control metadata')
        rows = value['inline_keyboard']
        if not isinstance(rows, list) or not 1 <= len(rows) <= 8: raise StorageError('bounded inline controls required')
        for row in rows:
            if not isinstance(row, list) or len(row) != 1: raise StorageError('bounded inline control row required')
            button = row[0]
            if (not isinstance(button, dict) or set(button) != {'text', 'callback_data'}
                or not isinstance(button['text'], str) or not 1 <= len(button['text']) <= 90
                or not isinstance(button['callback_data'], str) or not re.fullmatch(r'paic:[a-f0-9]{32}', button['callback_data'])):
                raise StorageError('opaque job control required')
        return {'inline_keyboard': rows}
    if value.get('kind')!='reply_keyboard':return None
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
