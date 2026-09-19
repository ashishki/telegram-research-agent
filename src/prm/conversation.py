"""Ephemeral, object-bound conversation state for the PA dialogue surface.

The store intentionally has no database backing.  PA-03 has no approved raw
conversation retention policy, so a process restart clears its state.  A
confirmation is consequently never recovered from a summary, topic label, or
keyword; it is usable only when the caller supplies the exact currently visible
proposal version again.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
import hashlib
import re
from threading import RLock
from typing import Mapping


CONVERSATION_TTL = timedelta(minutes=20)
MAX_CONVERSATIONS = 200
MAX_OBJECT_REFS = 8
MAX_MESSAGE_REFS = 12
_YES = frozenset({"yes", "да"})
_CANCEL = frozenset({"/cancel", "cancel", "отмена"})
_NEW = frozenset({"/new", "new", "новая тема"})
_SHORTEN = frozenset({"сделай короче", "сократи", "shorten it", "make it shorter"})
_SECOND = frozenset({"а второе", "второе", "second item", "the second one"})
_OBJECT_REF = re.compile(r"^response_[a-f0-9]{24}$")
_PROPOSAL_REF = re.compile(r"^(?:proposal|prm)_[a-z0-9_-]{3,120}$")
_VERSION = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")


@dataclass(frozen=True, slots=True)
class ResponseObjectRef:
    """A bounded visible object, never an authority to execute an action."""

    response_ref: str
    version: str
    kind: str
    display_text: str
    item_refs: tuple[str, ...] = ()
    item_texts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _OBJECT_REF.fullmatch(self.response_ref):
            raise ValueError("invalid response reference")
        if not _VERSION.fullmatch(self.version):
            raise ValueError("invalid response version")
        if self.kind not in {"answer", "list", "item", "clarification"}:
            raise ValueError("invalid response object kind")
        if not self.display_text or len(self.display_text) > 2_400:
            raise ValueError("invalid response display text")
        if len(self.item_refs) > 8 or len(set(self.item_refs)) != len(self.item_refs):
            raise ValueError("invalid response item references")
        if any(not _OBJECT_REF.fullmatch(item) for item in self.item_refs):
            raise ValueError("invalid response item reference")
        if len(self.item_texts) != len(self.item_refs) or any(not item or len(item) > 800 for item in self.item_texts):
            raise ValueError("invalid response item text")


@dataclass(frozen=True, slots=True)
class ConfirmationRef:
    """The only state a plain-language confirmation is allowed to select.

    PA-03 resolves this reference but deliberately does not execute it.  PA-13
    owns provider-write execution and reconciliation.
    """

    proposal_ref: str
    proposal_version: str
    response_ref: str
    chat_id_hash: str
    actor_id_hash: str
    owner_id_hash: str
    expires_at: datetime
    visible: bool = True

    def __post_init__(self) -> None:
        if not _PROPOSAL_REF.fullmatch(self.proposal_ref):
            raise ValueError("invalid confirmation proposal reference")
        if not _VERSION.fullmatch(self.proposal_version):
            raise ValueError("invalid confirmation proposal version")
        if not _OBJECT_REF.fullmatch(self.response_ref):
            raise ValueError("invalid confirmation response reference")
        if any(not _identity_hash(value) for value in (self.chat_id_hash, self.actor_id_hash, self.owner_id_hash)):
            raise ValueError("invalid confirmation identity binding")
        if self.expires_at.tzinfo is None:
            raise ValueError("confirmation expiry must be timezone-aware")
        if not isinstance(self.visible, bool):
            raise ValueError("confirmation visibility must be boolean")


@dataclass(frozen=True, slots=True)
class ConversationState:
    """A non-durable per-conversation view with explicit object references."""

    conversation_id: str
    chat_id_hash: str
    topic: str
    object_refs: tuple[ResponseObjectRef, ...] = ()
    message_refs: tuple[str, ...] = ()
    current_confirmation_ref: ConfirmationRef | None = None
    visible_confirmation_refs: tuple[ConfirmationRef, ...] = ()
    pending_request_ids: tuple[str, ...] = ()
    cancelled_request_ids: tuple[str, ...] = ()
    summary_version: int = 0
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc) + CONVERSATION_TTL)

    def __post_init__(self) -> None:
        if not self.conversation_id.startswith("conversation_") or len(self.conversation_id) != 37:
            raise ValueError("invalid conversation reference")
        if not _identity_hash(self.chat_id_hash):
            raise ValueError("invalid conversation identity")
        if len(self.topic) > 240:
            raise ValueError("conversation topic is too long")
        if len(self.object_refs) > MAX_OBJECT_REFS or len(self.message_refs) > MAX_MESSAGE_REFS:
            raise ValueError("conversation state is too large")
        if self.summary_version < 0 or self.expires_at.tzinfo is None:
            raise ValueError("invalid conversation state")


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    kind: str
    response_ref: str | None = None
    item_ref: str | None = None


@dataclass(frozen=True, slots=True)
class ConfirmationResolution:
    status: str
    confirmation_ref: ConfirmationRef | None = None


@dataclass(frozen=True, slots=True)
class SafeDialogueContext:
    """The sole model context PA-03 can assemble without archive authority."""

    conversation_id: str
    direct_user_text: str
    omitted_state: tuple[str, ...]


def conversation_id_for(chat_id: str) -> str:
    return "conversation_" + hashlib.sha256(f"pa.conversation.v1:{chat_id}".encode("utf-8")).hexdigest()[:24]


def identity_hash(value: str | None) -> str:
    return hashlib.sha256(f"pa.conversation.identity.v1:{str(value or '')}".encode("utf-8")).hexdigest()


def classify_turn(text: str, state: ConversationState | None) -> ConversationTurn:
    """Classify only object-bound controls; every other turn is a new topic.

    Text alone is never enough to select an old response or proposal.  This is
    intentionally more conservative than the historic archive follow-up
    heuristic: the latter may compose a read-only query, but cannot create
    confirmation authority.
    """

    clean = _clean(text).casefold()
    if clean in _CANCEL:
        return ConversationTurn("cancel")
    if clean in _NEW:
        return ConversationTurn("reset_topic")
    if clean in _YES:
        return ConversationTurn("plain_yes")
    current = _current_response(state)
    if clean in _SHORTEN and current is not None:
        return ConversationTurn("shorten", response_ref=current.response_ref)
    if clean in _SECOND and current is not None and len(current.item_refs) >= 2:
        return ConversationTurn("select_item", response_ref=current.response_ref, item_ref=current.item_refs[1])
    return ConversationTurn("new_topic")


def assemble_safe_dialogue_context(state: ConversationState, direct_user_text: str) -> SafeDialogueContext:
    """Allow only the current direct input across the PA-02 model boundary.

    Earlier response text, topic summaries and object references can be private
    or model-generated.  They remain local until a later slice gives them an
    explicit, provenance-bound egress contract.
    """

    clean = _clean(direct_user_text)
    if not clean:
        raise ValueError("dialogue input is empty")
    return SafeDialogueContext(
        conversation_id=state.conversation_id,
        direct_user_text=clean[:2_400],
        omitted_state=("prior_messages", "response_objects", "topic_summary", "confirmations"),
    )


class ConversationStore:
    """Thread-safe ephemeral store; restart means state is intentionally gone."""

    def __init__(self) -> None:
        self._states: dict[str, ConversationState] = {}
        self._lock = RLock()

    def clear(self) -> None:
        with self._lock:
            self._states.clear()

    def load(self, chat_id: str, *, now: datetime | None = None) -> ConversationState | None:
        conversation_id = conversation_id_for(chat_id)
        moment = _utc(now)
        with self._lock:
            state = self._states.get(conversation_id)
            if state is None:
                return None
            if _utc(state.expires_at) <= moment:
                self._states.pop(conversation_id, None)
                return None
            return state

    def start(self, chat_id: str, *, topic: str = "", now: datetime | None = None) -> ConversationState:
        conversation_id = conversation_id_for(chat_id)
        moment = _utc(now)
        with self._lock:
            state = ConversationState(
                conversation_id=conversation_id,
                chat_id_hash=identity_hash(chat_id),
                topic=_clean(topic)[:240],
                expires_at=moment + CONVERSATION_TTL,
            )
            self._put(state)
            return state

    def active_or_start(self, chat_id: str, *, now: datetime | None = None) -> ConversationState:
        return self.load(chat_id, now=now) or self.start(chat_id, now=now)

    def begin_new_topic(self, chat_id: str, *, now: datetime | None = None) -> ConversationState:
        state = self.active_or_start(chat_id, now=now)
        return self._replace(
            state,
            topic="",
            object_refs=(),
            message_refs=(),
            current_confirmation_ref=None,
            visible_confirmation_refs=(),
            summary_version=state.summary_version + 1,
            expires_at=_utc(now) + CONVERSATION_TTL,
        )

    def record_response(
        self,
        chat_id: str,
        *,
        text: str,
        topic: str = "",
        item_texts: tuple[str, ...] = (),
        now: datetime | None = None,
    ) -> ConversationState:
        state = self.active_or_start(chat_id, now=now)
        moment = _utc(now)
        cleaned_text = _clean(text)[:2_400]
        if not cleaned_text:
            return state
        item_refs = tuple(
            _response_ref(f"{state.conversation_id}:{index}:{_clean(item)}")
            for index, item in enumerate(item_texts[:8], start=1)
            if _clean(item)
        )
        response = ResponseObjectRef(
            response_ref=_response_ref(f"{state.conversation_id}:{state.summary_version + 1}:{cleaned_text}"),
            version=_version(cleaned_text),
            kind="list" if item_refs else "answer",
            display_text=cleaned_text,
            item_refs=item_refs,
            item_texts=tuple(_clean(item)[:800] for item in item_texts[:8] if _clean(item)),
        )
        objects = (response, *state.object_refs)[:MAX_OBJECT_REFS]
        return self._replace(
            state,
            topic=_clean(topic)[:240] or state.topic,
            object_refs=objects,
            message_refs=(response.response_ref, *state.message_refs)[:MAX_MESSAGE_REFS],
            # A different visible result invalidates every older proposal.
            current_confirmation_ref=None,
            visible_confirmation_refs=(),
            summary_version=state.summary_version + 1,
            expires_at=moment + CONVERSATION_TTL,
        )

    def offer_confirmation(self, chat_id: str, confirmation: ConfirmationRef, *, now: datetime | None = None) -> ConversationState:
        state = self.load(chat_id, now=now)
        if state is None or confirmation.chat_id_hash != state.chat_id_hash:
            raise ValueError("confirmation does not belong to an active conversation")
        response = next((item for item in state.object_refs if item.response_ref == confirmation.response_ref), None)
        if response is None or not confirmation.visible or _utc(confirmation.expires_at) <= _utc(now):
            raise ValueError("confirmation is not visible on a current response")
        # A new preview replaces, rather than accumulates with, a prior preview.
        return self._replace(
            state,
            current_confirmation_ref=confirmation,
            visible_confirmation_refs=(confirmation,),
            expires_at=_utc(now) + CONVERSATION_TTL,
        )

    def resolve_plain_yes(
        self,
        chat_id: str,
        *,
        actor_id: str | None,
        owner_chat_id: str | None,
        proposal_versions: Mapping[str, str] | None = None,
        now: datetime | None = None,
    ) -> ConfirmationResolution:
        if not str(chat_id or "").strip() or not str(actor_id or "").strip() or not str(owner_chat_id or "").strip():
            return ConfirmationResolution("unavailable")
        state = self.load(chat_id, now=now)
        if state is None:
            return ConfirmationResolution("unavailable")
        moment = _utc(now)
        visible = tuple(
            ref
            for ref in state.visible_confirmation_refs
            if ref.visible
            and _utc(ref.expires_at) > moment
            and ref.response_ref in {item.response_ref for item in state.object_refs}
            and ref.chat_id_hash == identity_hash(chat_id)
            and ref.actor_id_hash == identity_hash(actor_id)
            and ref.owner_id_hash == identity_hash(owner_chat_id)
        )
        if not visible:
            return ConfirmationResolution("unavailable")
        if len(visible) != 1 or state.current_confirmation_ref != visible[0]:
            return ConfirmationResolution("ambiguous_or_unavailable")
        current_version = (proposal_versions or {}).get(visible[0].proposal_ref)
        if current_version != visible[0].proposal_version:
            return ConfirmationResolution("stale_or_unavailable")
        return ConfirmationResolution("resolved", visible[0])

    def start_request(self, chat_id: str, request_id: str, *, now: datetime | None = None) -> ConversationState:
        clean = _clean(request_id)
        if not clean or len(clean) > 120:
            raise ValueError("invalid request reference")
        state = self.active_or_start(chat_id, now=now)
        if clean in state.cancelled_request_ids:
            raise ValueError("request is already cancelled")
        return self._replace(
            state,
            pending_request_ids=tuple((*state.pending_request_ids, clean))[-8:],
            expires_at=_utc(now) + CONVERSATION_TTL,
        )

    def finish_request(self, chat_id: str, request_id: str, *, now: datetime | None = None) -> ConversationState | None:
        state = self.load(chat_id, now=now)
        if state is None:
            return None
        clean = _clean(request_id)
        return self._replace(state, pending_request_ids=tuple(item for item in state.pending_request_ids if item != clean))

    def cancel(self, chat_id: str, request_id: str | None = None, *, now: datetime | None = None) -> ConversationState | None:
        state = self.load(chat_id, now=now)
        if state is None:
            return None
        selected = _clean(request_id) if request_id is not None else (state.pending_request_ids[-1] if state.pending_request_ids else "")
        cancelled = state.cancelled_request_ids
        pending = state.pending_request_ids
        if selected:
            cancelled = tuple((*cancelled, selected))[-8:]
            pending = tuple(item for item in pending if item != selected)
        return self._replace(
            state,
            pending_request_ids=pending,
            cancelled_request_ids=cancelled,
            current_confirmation_ref=None,
            visible_confirmation_refs=(),
            summary_version=state.summary_version + 1,
            expires_at=_utc(now) + CONVERSATION_TTL,
        )

    def cancel_request(self, request_id: str, *, now: datetime | None = None) -> ConversationState | None:
        """Cancel one unambiguous in-flight request without a chat lookup API."""

        clean = _clean(request_id)
        if not clean:
            return None
        with self._lock:
            candidates = [
                state for state in self._states.values()
                if clean in state.pending_request_ids and _utc(state.expires_at) > _utc(now)
            ]
            if len(candidates) != 1:
                return None
            # The request ID is globally generated by the application.
            # Reusing a colliding reference across conversations fails closed.
            return self._cancel_state(candidates[0], clean, now=now)

    def _cancel_state(self, state: ConversationState, request_id: str, *, now: datetime | None = None) -> ConversationState:
        clean = _clean(request_id)
        return self._replace(
            state,
            pending_request_ids=tuple(item for item in state.pending_request_ids if item != clean),
            cancelled_request_ids=tuple((*state.cancelled_request_ids, clean))[-8:],
            current_confirmation_ref=None,
            visible_confirmation_refs=(),
            summary_version=state.summary_version + 1,
            expires_at=_utc(now) + CONVERSATION_TTL,
        )

    def is_cancelled(self, chat_id: str, request_id: str, *, now: datetime | None = None) -> bool:
        state = self.load(chat_id, now=now)
        return bool(state is not None and _clean(request_id) in state.cancelled_request_ids)

    def _replace(self, state: ConversationState, **changes: object) -> ConversationState:
        updated = replace(state, **changes)
        with self._lock:
            self._put(updated)
        return updated

    def _put(self, state: ConversationState) -> None:
        if len(self._states) >= MAX_CONVERSATIONS and state.conversation_id not in self._states:
            self._states.pop(next(iter(self._states)))
        self._states[state.conversation_id] = state


GLOBAL_CONVERSATIONS = ConversationStore()


def _current_response(state: ConversationState | None) -> ResponseObjectRef | None:
    return state.object_refs[0] if state is not None and state.object_refs else None


def _response_ref(value: str) -> str:
    return "response_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _version(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _identity_hash(value: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{64}", value))


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _utc(value: datetime | None) -> datetime:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc)
