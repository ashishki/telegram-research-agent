"""One deterministic owner-input adapter. It never confers execution authority."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class IntentKind(str, Enum):
    CHAT = 'chat'
    SEARCH = 'search'
    WEEKLY = 'weekly'
    MEMORY_OPERATION = 'memory_operation'
    JOB_STATUS = 'job_status'
    JOB_RESULT = 'job_result'
    JOB_CANCEL = 'job_cancel'
    ACTION_PREVIEW = 'action_preview'
    SERVICE = 'service'
    UNSUPPORTED = 'unsupported'


@dataclass(frozen=True)
class RequestIntent:
    kind: IntentKind
    query: str
    mode: str = 'auto'
    service: str | None = None
    target_ref: str | None = None
    target_version: int | None = None
    project_ref: str | None = None
    source_filters: tuple[str, ...] = ()
    origin: str = 'text'
    needs_clarification: bool = False
    public_web_query: str = ''


SERVICE_COMMANDS = {
    'projects':('/projectpreview','/projectconfirm','/projects','/projectshow','/projectapply'),
    'budget':('/budget',), 'archive':('/archives',),
    'actions': ('/actpreview', '/actedit', '/actconfirm', '/actreconcile'),
    'mail': ('/mail', '/mailread'), 'calendar': ('/calendar',), 'contacts': ('/contacts',),
    'academic': ('/academic', '/academicdone', '/academicstage', '/academicwatch'),
    'memory': ('/memory', '/memoryedit', '/memorysearch', '/memoryexport', '/remember', '/memoryconfirm', '/forget'),
    'media': ('/transcriptedit',), 'brief': ('/weekly','/briefmaterials'),
}
SERVICE_PHRASES = {
    'mail': ('что в почте', 'что требует ответа в почте'),
    'calendar': ('покажи календарь', 'конфликты расписания'),
    'contacts': ('найди адресата',), 'academic': ('покажи академическую сводку',),
}
PHRASES = {
    'собери обзор недели': '/weekly', 'обзор недели': '/weekly',
    'что с задачей': '/status', 'что с обзором': '/status',
    'останови': '/cancel', 'стоп': '/cancel', 'останови обзор': '/cancel',
    'верни результат': '/result', 'покажи результат': '/result',
    'новая тема': '/new', 'начни новую тему': '/new',
}
JOB_COMMANDS = {'/status': IntentKind.JOB_STATUS, '/result': IntentKind.JOB_RESULT,
                '/cancel': IntentKind.JOB_CANCEL}


def parse_request_intent(text: str, *, requested_mode: str = 'auto') -> RequestIntent:
    """A bounded phrase vocabulary, followed by the existing Chat fallback."""
    clean = text.strip()
    origin = 'command' if clean.startswith('/') else 'text'
    phrase = PHRASES.get(clean.casefold().rstrip('?!.')) if requested_mode != 'chat' else None
    if phrase is not None:
        clean, origin = phrase, 'phrase'
    elif requested_mode != 'chat' and clean.casefold().startswith('собери обзор недели '):
        clean, origin = '/weekly ' + clean[len('собери обзор недели '):].strip(), 'phrase'
    elif requested_mode != 'chat' and clean.casefold().startswith('глубоко исследуй '):
        clean, origin = '/deep ' + clean[len('глубоко исследуй '):].strip(), 'phrase'
    command, _, argument = clean.partition(' ')
    if command in JOB_COMMANDS:
        return RequestIntent(JOB_COMMANDS[command], '', target_ref=argument.strip() or None, origin=origin)
    for service, commands in SERVICE_COMMANDS.items():
        if command in commands:
            kind = {'memory': IntentKind.MEMORY_OPERATION, 'brief': IntentKind.WEEKLY}.get(service, IntentKind.SERVICE)
            if command == '/actpreview': kind = IntentKind.ACTION_PREVIEW
            return RequestIntent(kind, clean, requested_mode, service=service, origin=origin)
    if command == '/new':
        return RequestIntent(IntentKind.CHAT, '/new', 'chat', origin=origin)
    if command in {'/deep','/deepcontinue'} and argument.strip():
        return RequestIntent(IntentKind.SEARCH, clean, requested_mode, service='deep', origin=origin)
    if command == '/web' and argument.strip():
        return RequestIntent(IntentKind.SEARCH, 'Проверь свежий факт: ' + argument.strip(), 'research',
                             origin=origin, public_web_query=argument.strip())
    if command in {'/auto', '/chat', '/research', '/brief'} and argument.strip():
        mode = command[1:]
        kind = IntentKind.CHAT if mode in {'auto', 'chat'} else IntentKind.SEARCH
        return RequestIntent(kind, argument.strip(), mode, origin=origin)
    if clean.startswith('/'):
        return RequestIntent(IntentKind.UNSUPPORTED, clean, origin=origin)
    if requested_mode != 'chat':
        lowered = clean.casefold()
        for service, phrases in SERVICE_PHRASES.items():
            if any(lowered == phrase or lowered.startswith(phrase + ' ') for phrase in phrases):
                return RequestIntent(IntentKind.SERVICE, clean, requested_mode, service=service)
    return RequestIntent(IntentKind.CHAT, clean, requested_mode, origin=origin)
