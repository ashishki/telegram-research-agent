"""Shared exact Telegram routes and object bindings, independent of transport."""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import json
import re
from prm.storage.postgres import StorageError


@dataclass(frozen=True)
class TelegramDestination:
    chat_id: str
    bot_ref: str = 'bot_default'
    message_thread_id: int | None = None
    business_connection_id: str | None = None
    audience_kind: str = 'owner_private'

    def __post_init__(self):
        if (not isinstance(self.chat_id, str) or not re.fullmatch(r'[1-9][0-9]{0,18}', self.chat_id)
            or int(self.chat_id) > 9223372036854775807 or not isinstance(self.bot_ref, str)
            or not self.bot_ref.startswith('bot_') or len(self.bot_ref) > 128
            or self.audience_kind != 'owner_private' or self.business_connection_id is not None
            or (self.message_thread_id is not None and (type(self.message_thread_id) is not int or self.message_thread_id <= 0))):
            raise StorageError('exact supported private Telegram destination required')


@dataclass(frozen=True)
class TelegramMessageBinding:
    owner: str
    destination: TelegramDestination
    message_id: int
    job_ref: str
    response_ref: str | None = None
    response_version: int | None = None
    presentation_revision: int = 1
    scope_revision: int = 1
    delivery_ref: str | None = None
    origin_kind: str = 'source'
    source_revision_ref: str | None = None
    source_revision: int = 1

    def __post_init__(self):
        if (not isinstance(self.owner, str) or not 0 < len(self.owner) <= 128
            or type(self.destination) is not TelegramDestination
            or type(self.message_id) is not int or self.message_id <= 0
            or not isinstance(self.job_ref, str) or not re.fullmatch(r'job_[a-f0-9]{32}', self.job_ref)
            or (self.response_ref is None) != (self.response_version is None)
            or (self.response_ref is not None and (not isinstance(self.response_ref, str) or not 0 < len(self.response_ref) <= 128))
            or self.origin_kind not in {'source', 'bot'}
            or any(value is not None and (not isinstance(value, str) or not 0 < len(value) <= 128)
                   for value in (self.delivery_ref, self.source_revision_ref))
            or any(type(value) is not int or value <= 0 for value in
                   (self.presentation_revision, self.scope_revision, self.source_revision, self.response_version if self.response_version is not None else 1))):
            raise StorageError('typed versioned Telegram message binding required')


class TelegramEnvelopeError(StorageError):
    """Typed pure-validation failure; unlike a DB outage it can be quarantined."""


@dataclass(frozen=True)
class TelegramQuote:
    text: str
    position: int
    verified: bool = False


@dataclass(frozen=True)
class TelegramUpdateEnvelope:
    update_id: int
    kind: str
    input_digest: str
    trusted_owner: bool
    destination: TelegramDestination | None = None
    actor_id: str | None = None
    message_id: int | None = None
    reply_to_message_id: int | None = None
    quote: TelegramQuote | None = None
    forward_origin: dict | None = None
    source_trust: str = 'owner_instruction'
    callback_query_id: str | None = None
    schema_version: str = 'telegram.update.v2'


def update_digest(update, *, maximum=65536):
    try: raw = json.dumps(update, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
    except (ValueError, TypeError, RecursionError): raise TelegramEnvelopeError('invalid Telegram envelope') from None
    if len(raw) > maximum: raise TelegramEnvelopeError('Telegram envelope exceeds bound')
    return hashlib.sha256(raw).hexdigest()


def _message_id(value, *, optional=True):
    if value is None and optional: return None
    if type(value) is not int or not 0 < value < 2**63: raise TelegramEnvelopeError('typed positive Telegram message reference required')
    return value


def normalize_update(update, *, owner_chat_id, bot_ref='bot_default'):
    """Preserve declared metadata, without inventing an actor or source identity."""
    if not isinstance(update, dict) or type(update.get('update_id')) is not int or not 0 <= update['update_id'] < 2**63:
        raise TelegramEnvelopeError('typed Telegram update ID required')
    digest = update_digest(update)
    fields = [key for key in update if key != 'update_id']
    if len(fields) != 1: raise TelegramEnvelopeError('one Telegram update payload required')
    kind = fields[0]
    if kind not in {'message', 'edited_message', 'callback_query'}:
        return TelegramUpdateEnvelope(update['update_id'], kind, digest, False)
    data = update[kind]
    if not isinstance(data, dict): raise TelegramEnvelopeError('typed Telegram update payload required')
    callback = kind == 'callback_query'
    message = data.get('message', {}) if callback else data
    if not isinstance(message, dict): raise TelegramEnvelopeError('typed Telegram message required')
    actor, chat = data.get('from', {}), message.get('chat', {})
    if not isinstance(actor, dict) or not isinstance(chat, dict): raise TelegramEnvelopeError('typed Telegram private tuple required')
    from assistant.prm_post_answer_actions import canonical_private_owner_id
    actor_id, chat_id = canonical_private_owner_id(str(actor.get('id', ''))), canonical_private_owner_id(str(chat.get('id', '')))
    if actor_id != owner_chat_id or chat_id != owner_chat_id or chat.get('type') != 'private' or message.get('business_connection_id') is not None:
        return TelegramUpdateEnvelope(update['update_id'], kind, digest, False)
    thread = message.get('message_thread_id')
    if thread is not None: _message_id(thread, optional=False)
    route = TelegramDestination(chat_id=chat_id, bot_ref=bot_ref, message_thread_id=thread)
    reply = message.get('reply_to_message')
    if reply is not None and not isinstance(reply, dict): raise TelegramEnvelopeError('typed Telegram reply required')
    quote = message.get('quote')
    if quote is not None:
        if (not isinstance(quote, dict) or not isinstance(quote.get('text'), str) or len(quote['text']) > 1024
            or type(quote.get('position')) is not int or quote['position'] < 0): raise TelegramEnvelopeError('bounded UTF-16 quote required')
        quote = TelegramQuote(quote['text'], quote['position'])
    forward = message.get('forward_origin')
    if forward is not None:
        if not isinstance(forward, dict) or forward.get('type') not in {'user', 'hidden_user', 'chat', 'channel'}:
            raise TelegramEnvelopeError('typed forward origin required')
        origin = {'type': forward['type'], 'source_identity': None}
        date = forward.get('date')
        if type(date) is int and date >= 0: origin['date'] = date
        # Hidden names are display metadata, never canonical person identity.
        if forward['type'] == 'hidden_user':
            name = forward.get('sender_user_name')
            if isinstance(name, str): origin['display_name'] = name[:128]
        elif forward['type'] == 'user':
            sender = forward.get('sender_user', {})
            if isinstance(sender, dict): origin['source_identity'] = canonical_private_owner_id(str(sender.get('id', '')))
        else:
            source = forward.get('chat' if forward['type'] == 'channel' else 'sender_chat', {})
            identifier = source.get('id') if isinstance(source, dict) else None
            if type(identifier) is int and -(2**63) < identifier < 2**63: origin['source_identity'] = str(identifier)
        forward = origin
    for key in ('text', 'caption', 'voice_transcript'):
        if key in message and (not isinstance(message[key], str) or len(message[key].encode()) > 16000):
            raise TelegramEnvelopeError('bounded Telegram input text required')
    for key in ('voice', 'document', 'photo'):
        if key not in message: continue
        selected = message[key]
        if key == 'photo':
            if not isinstance(selected, list) or not 1 <= len(selected) <= 20: raise TelegramEnvelopeError('bounded inbound media reference required')
            selected = selected[-1]
        if not isinstance(selected, dict): raise TelegramEnvelopeError('bounded inbound media reference required')
        # Existing synthetic transcripts omit a file ref deliberately.
        if key == 'voice' and isinstance(selected.get('transcript'), str): continue
        ref = selected.get('file_id')
        if not isinstance(ref, str) or not 0 < len(ref) <= 512: raise TelegramEnvelopeError('bounded inbound media reference required')
        if key == 'document' and selected.get('mime_type') not in {'application/pdf', 'image/png', 'image/jpeg'}:
            raise TelegramEnvelopeError('media MIME not allowlisted')
    callback_id = data.get('id') if callback else None
    if callback_id is not None and (not isinstance(callback_id, str) or not 0 < len(callback_id) <= 256):
        raise TelegramEnvelopeError('bounded callback identity required')
    return TelegramUpdateEnvelope(update['update_id'], kind, digest, True, route, actor_id,
        _message_id(message.get('message_id')), _message_id(reply.get('message_id')) if reply else None,
        quote, forward, 'untrusted_source' if forward is not None or message.get('external_reply') is not None else 'owner_instruction', callback_id)


def quote_matches(text, quote):
    if type(quote) is not TelegramQuote or not isinstance(text, str): return False
    encoded = text.encode('utf-16-le')
    start = quote.position * 2
    target = quote.text.encode('utf-16-le')
    return encoded[start:start + len(target)] == target


@dataclass(frozen=True)
class TelegramOutcome:
    kind: str
    result: object = field(default=None, repr=False)
    error_code: int | None = None
    retry_after: int | None = None
