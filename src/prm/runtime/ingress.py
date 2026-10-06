"""Durable private ingress. Intake performs no research, transcription or effect."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import re

from prm.storage.jobs import JobQueue
from prm.storage.postgres import StorageError, StateConflict, _canonical


@dataclass(frozen=True)
class IntakeReply:
    text: str
    request_ref: str | None = None
    job_id: str | None = None


class TelegramJobIngress:
    """Explicit synthetic target and authenticated private owner, no env fallback."""

    def __init__(self, queue: JobQueue, *, owner_ref: str, owner_chat_id: str):
        if not owner_ref or len(owner_ref) > 128 or not re.fullmatch(r'[1-9][0-9]*', owner_chat_id):
            raise StorageError('explicit private owner required')
        self.queue = queue
        self.owner_ref = owner_ref
        self.owner_chat_id = owner_chat_id

    def receive(self, update: dict) -> IntakeReply | None:
        if not isinstance(update, dict) or type(update.get('update_id')) is not int or update['update_id'] < 0:
            raise StorageError('typed Telegram update ID required')
        callback = update.get('callback_query')
        message = callback.get('message', {}) if isinstance(callback, dict) else update.get('message', {})
        actor = (callback if isinstance(callback, dict) else message).get('from', {})
        chat = message.get('chat', {})
        if (str(actor.get('id', '')) != self.owner_chat_id or str(chat.get('id', '')) != self.owner_chat_id
                or chat.get('type') != 'private'):
            return None
        text = str(callback.get('data', '')) if isinstance(callback, dict) else str(message.get('text', '')).strip()
        if isinstance(callback, dict):
            parts = text.split(':')
            if len(parts) != 3 or parts[0] != 'pai' or parts[1] not in {'status', 'cancel', 'result'}:
                return IntakeReply('Это действие недоступно; подтверждение не использовано.')
            return self.control(parts[1], parts[2])
        parts = text.split(maxsplit=1)
        if parts and parts[0] in {'/status', '/cancel', '/result'}:
            if len(parts) != 2:
                return IntakeReply('Укажи ID задачи после команды.')
            return self.control(parts[0][1:], parts[1])
        voice = message.get('voice')
        transcript = message.get('voice_transcript') or (voice or {}).get('transcript')
        if transcript:
            body = {'query': str(transcript), 'input_kind': 'voice_transcript', 'mode': 'auto'}
        elif voice:
            file_ref = voice.get('file_id')
            if not isinstance(file_ref, str) or not 0 < len(file_ref) <= 512:
                raise StorageError('bounded voice reference required')
            body = {'voice_ref': file_ref, 'input_kind': 'voice', 'mode': 'auto'}
        elif text:
            mode = 'auto'
            if text.startswith('/'):
                command, _, query = text.partition(' ')
                if command not in {'/auto', '/chat', '/research', '/brief'} or not query.strip():
                    return IntakeReply('Отправь вопрос или /status, /result, /cancel с ID задачи.')
                mode, text = command[1:], query.strip()
            body = {'query': text, 'input_kind': 'text', 'mode': mode}
        else:
            return None
        if len(body.get('query', '').encode('utf-8')) > 16000:
            raise StorageError('request text exceeds its bound')
        body.update({'chat_id': self.owner_chat_id, 'actor_id': self.owner_chat_id,
                     'owner_chat_id': self.owner_chat_id, 'schema_version': 1})
        key = 'telegram_' + str(update['update_id'])
        request_ref = 'request_' + hashlib.sha256((self.owner_ref + ':' + key).encode()).hexdigest()[:32]
        with self.queue.store.transaction() as tx:
            # Inbox identity and queue admission share the same commit. A crash
            # before acknowledgement simply replays this exact immutable input.
            lock = int.from_bytes(hashlib.sha256((self.owner_ref + key).encode()).digest()[:8], 'big') % (2**63)
            tx.conn.execute('SELECT pg_advisory_xact_lock(%s)', (lock,))
            item = tx.get(self.owner_ref, 'conversation', request_ref, version=1)
            if item is not None and item.payload != body:
                raise StateConflict('update ID reused with different content')
            item = item or tx.put(self.owner_ref, 'conversation', request_ref, body, expected_version=0)
            payload = {'schema_version': 1, 'input_namespace': 'conversation', 'input_ref': request_ref,
                       'input_version': 1, 'input_digest': item.digest, 'connection_ref': None,
                       'resource_ref': 'resource_local_request', 'purpose': 'local.assistant', 'consent_revision': 1}
            now = tx.conn.execute('SELECT clock_timestamp() AS now').fetchone()['now']
            job = self.queue.enqueue_in(tx, owner=self.owner_ref, idempotency_key=key, payload=payload,
                                       deadline=now + timedelta(minutes=15), kind='compute.assistant')
        return IntakeReply(f'Запрос сохранён. Задача {job}. /status {job}', request_ref, job)

    def control(self, command: str, job_id: str) -> IntakeReply:
        if not re.fullmatch(r'job_[a-f0-9]{32}', job_id):
            return IntakeReply('Некорректный ID задачи.')
        state = self.queue.status(owner=self.owner_ref, job_id=job_id)
        if state is None:
            return IntakeReply('Задача не найдена.')
        if command == 'cancel':
            cancelled = self.queue.cancel(owner=self.owner_ref, job_id=job_id)
            return IntakeReply('Задача отменена.' if cancelled else f"Задача уже имеет статус {state['status']}.", job_id=job_id)
        if command == 'result' and state['status'] == 'completed':
            result = self.queue.store.get(self.owner_ref, 'result', state['result_ref'], version=1)
            if result is None:
                raise StorageError('completed result unavailable')
            return IntakeReply(str(result.payload.get('text', 'Результат не содержит текста.')), result.payload.get('request_ref'), job_id)
        return IntakeReply(f"{job_id}: {state['status']}; попытка {state['attempts']}.", job_id=job_id)


class RequestConversations:
    """Keep worker navigation tied to its request, including after restart."""
    def __init__(self, store, request_ref):
        self.store, self.request_ref = store, request_ref

    def __getattr__(self, name):
        method = getattr(self.store, name)
        if name in {'clear', 'cancel_request'}:
            return method
        def scoped(_chat_id, *args, **kwargs):
            return method(self.request_ref, *args, **kwargs)
        return scoped


class AssistantJobWorker:
    def __init__(self, ingress: TelegramJobIngress, *, settings, assistant_factory=None, voice_resolver=None):
        self.ingress, self.settings = ingress, settings
        self.assistant_factory, self.voice_resolver = assistant_factory, voice_resolver

    def run_once(self):
        from prm.application import PersonalResearchAssistant
        from prm.contracts import OperatorRequest
        from prm.storage.conversations import DurableConversationStore
        queue = self.ingress.queue
        lease = queue.claim(owner=self.ingress.owner_ref, lease_seconds=300, kinds=('compute.assistant',))
        if lease is None:
            return None
        if lease.kind != 'compute.assistant':
            queue.retry_compute(lease, error_code='compute_unavailable')
            return None
        item = queue.store.get(lease.owner, 'conversation', lease.payload['input_ref'], version=lease.payload['input_version'])
        body = dict(item.payload)
        queue.checkpoint(lease, {'stage': 'input_verified', 'request_ref': item.object_id})
        if body['input_kind'] == 'voice':
            # The resolver is responsible for fresh download/STT policy checks.
            # No configured credential or intake tuple authorizes either I/O.
            if self.voice_resolver is None:
                return queue.complete(lease, {'request_ref': item.object_id, 'text': 'Для расшифровки нужен разрешённый voice adapter.', 'status': 'voice_unavailable'})
            body['query'] = self.voice_resolver(body['voice_ref'], lease)
            if not isinstance(body['query'], str) or len(body['query'].encode()) > 16000:
                raise StorageError('invalid bounded transcription')
            body['input_kind'] = 'voice_transcript'
            queue.checkpoint(lease, {'stage': 'transcribed', 'request_ref': item.object_id})
        conversations = RequestConversations(DurableConversationStore(queue.store.target,
            owner_ref=lease.owner, history_retention_seconds=0), item.object_id)
        assistant = (self.assistant_factory or PersonalResearchAssistant)(settings=self.settings, conversations=conversations)
        request = OperatorRequest(query=body['query'], mode=body['mode'], input_kind=body['input_kind'],
                                  chat_id=body['chat_id'], actor_id=body['actor_id'], owner_chat_id=body['owner_chat_id'])
        queue.checkpoint(lease, {'stage': 'answering', 'request_ref': item.object_id})
        result = assistant.answer(request)
        # Fenced completion rejects cancellation/expiry during the slow call.
        # Delivery is a separately authorized read of this immutable result.
        record = {'request_ref': item.object_id, 'text': result.text, 'status': result.status,
                  'interaction_id': result.interaction_id, 'payload': dict(result.payload)}
        _canonical(record)
        return queue.complete(lease, record)
