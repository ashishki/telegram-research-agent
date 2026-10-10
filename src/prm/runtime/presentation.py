"""Trusted text controls and human status rendering; never new execution authority."""
from __future__ import annotations
from zoneinfo import ZoneInfo
from prm.storage.postgres import StorageError

CONFIRM_LABELS={'mail.send':'Отправить письмо','calendar.create':'Создать событие',
                'calendar.update':'Изменить событие','calendar.cancel':'Отменить событие'}
ACTION_CHECK='Проверить результат действия'


def keyboard(*labels):
    if not labels or len(labels)>6 or any(not isinstance(label,str) or not 1<=len(label)<=90 for label in labels):
        raise StorageError('bounded trusted text controls required')
    return {'kind':'reply_keyboard','keyboard':[[{'text':label}] for label in labels],
            'resize_keyboard':True,'one_time_keyboard':True}


def action_preview(proposal):
    value=proposal.content;code=proposal.action_code
    if code=='mail.send':
        lines=['Предпросмотр письма','Из выбранного подключённого аккаунта Microsoft.',
               'Кому: '+', '.join(value['to']),'Тема: '+value['subject'],'','Текст письма:',value['body']]
    else:
        title={'calendar.create':'Создать событие','calendar.update':'Изменить событие','calendar.cancel':'Отменить событие'}[code]
        lines=['Предпросмотр: '+title,'Из выбранного подключённого календаря Microsoft.']
        for key,label in [('title','Название'),('start_at','Начало'),('end_at','Окончание'),('timezone','Часовой пояс')]:
            if key in value:lines.append(label+': '+str(value[key]))
        if code=='calendar.cancel':lines.append('Событие: '+value['event_ref'])
    until=proposal.expires_at.astimezone(ZoneInfo('Europe/Berlin')).strftime('%d.%m %H:%M')
    lines.extend(['',f'Подтверждение действует до {until} (Europe/Berlin).',
                  'Проверь полный текст и параметры. Нажми «'+CONFIRM_LABELS[code]+'» или ответь «да».'])
    text='\n'.join(lines)
    if len(text)>32000:raise StorageError('exact action preview exceeds delivery bound')
    return text


def action_outcome(receipt,action_code,*,repeated=False,reconciled=False):
    prefix='Повторное подтверждение уже использовано; нового действия не было.\n' if repeated else ''
    if receipt.status=='unknown':
        if receipt.error_code=='provider_accepted_pending_verification':
            text='Провайдер принял запрос, но выполнение ещё не подтверждено.'
        else:text='Результат запроса неизвестен; он мог дойти до провайдера.'
        return prefix+text+' Автоматически повторять его не буду. Нажми «'+ACTION_CHECK+'» для отдельной сверки.'
    if receipt.status=='succeeded':
        if action_code=='mail.send':
            text='Письмо найдено в «Отправленных».' if reconciled else 'Провайдер подтвердил операцию с письмом.'
            text+=' Получение письма адресатом этим не подтверждается.'
        else:text='Провайдер подтвердил действие с календарём.'
        if receipt.provider_operation_ref:text+='\nИдентификатор объекта у провайдера: '+receipt.provider_operation_ref
        return prefix+text
    if receipt.status=='not_sent':return prefix+'Отправка не началась; подтверждённого внешнего действия нет.'
    return prefix+'Действие не выполнено. Для продолжения нужен новый точный предпросмотр.'


def split_html_messages(text,limit=3500):
    """Split trusted Telegram HTML while retaining complete tags/entities."""
    import re
    from html.parser import HTMLParser
    class Tracker(HTMLParser):
        def __init__(self):super().__init__(convert_charrefs=False);self.open=[]
        def handle_starttag(self,tag,attrs):
            if tag not in {'b','strong','i','em','u','s','code','pre','a','blockquote'}:raise StorageError('unsupported Telegram HTML tag')
            self.open.append((tag,self.get_starttag_text()))
        def handle_endtag(self,tag):
            if not self.open or self.open[-1][0]!=tag:raise StorageError('unbalanced Telegram HTML')
            self.open.pop()
    tracker=Tracker();pieces=[];current=''
    for token in re.findall(r'<[^>]*>|&(?:#[0-9]+|#x[0-9a-fA-F]+|[A-Za-z]+);|[^<&]+|[<&]',text):
        atoms=[token] if token.startswith(('<','&')) else [token[i:i+500] for i in range(0,len(token),500)]
        for atom in atoms:
            closing=''.join('</'+tag+'>' for tag,_ in reversed(tracker.open))
            if len(current)+len(atom)+len(closing)>limit:
                pieces.append(current+closing);current=''.join(raw for _,raw in tracker.open)
            if len(current)+len(atom)>limit:raise StorageError('single Telegram HTML token exceeds bound')
            current+=atom;tracker.feed(atom)
    tracker.close()
    if tracker.open:raise StorageError('unbalanced Telegram HTML')
    if current:pieces.append(current)
    return pieces
