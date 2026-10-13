"""Shared exact Telegram routes and object bindings, independent of transport."""
from __future__ import annotations
from dataclasses import dataclass
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

    def __post_init__(self):
        if (not isinstance(self.owner, str) or not 0 < len(self.owner) <= 128
            or type(self.destination) is not TelegramDestination
            or type(self.message_id) is not int or self.message_id <= 0
            or not isinstance(self.job_ref, str) or not re.fullmatch(r'job_[a-f0-9]{32}', self.job_ref)
            or (self.response_ref is None) != (self.response_version is None)
            or (self.response_ref is not None and (not isinstance(self.response_ref, str) or not 0 < len(self.response_ref) <= 128))
            or any(type(value) is not int or value <= 0 for value in
                   (self.presentation_revision, self.scope_revision, self.response_version if self.response_version is not None else 1))):
            raise StorageError('typed versioned Telegram message binding required')
