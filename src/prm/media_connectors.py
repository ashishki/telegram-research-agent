"""PA-15 local, fail-closed media contracts (voice, image, document).

Media obeys the same provider/grant policy as text: transcription, vision,
document understanding and speech are separate purposes, and a reservation is
re-checked immediately before each call. Malicious, oversized or unsupported
content is rejected before any adapter runs; OCR is bounded and used only when
the extracted text layer is inadequate. Every asset carries a temporary-cleanup
plan and an expiry.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Literal, Mapping, Protocol

from prm.capabilities import (
    AuthorizationDecision,
    CapabilityDenied,
    require_authorized_egress,
)


MEDIA_SCHEMA_VERSION = "assistant.media_connector.v1"
DATA_CLASS = "private_connector_content"
MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 200
OCR_TEXT_THRESHOLD = 200

_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,511}$")
_MEDIA = re.compile(r"^media_[a-z0-9_-]{3,120}$")

# Explicit allowlist. Anything else is unsupported and never processed.
ALLOWED_MIME = {
    "voice": ("audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav"),
    "image": ("image/png", "image/jpeg", "image/webp"),
    "document": ("application/pdf", "text/plain", "text/markdown"),
}
# Defence in depth: these are never treated as documents, even if mislabelled.
BLOCKED_MIME = (
    "application/x-msdownload", "application/x-executable", "application/x-sh",
    "application/zip", "application/x-tar", "application/x-7z-compressed",
    "application/x-httpd-php", "text/x-python", "application/x-sharedlib",
)
MEDIA_KINDS = ("voice", "image", "document")
EXTRACTION_METHODS = ("text_layer", "ocr")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _text(value: object, *, field: str, maximum: int, required: bool = True) -> str:
    text = " ".join(str(value or "").split())
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > maximum:
        raise ValueError(f"{field} exceeds {maximum} characters")
    if any(ord(char) < 32 for char in text):
        raise ValueError(f"{field} contains control characters")
    return text


def _ref(value: object, *, field: str) -> str:
    text = str(value or "")
    if not _REF.fullmatch(text):
        raise ValueError(f"invalid {field}")
    return text


@dataclass(frozen=True, slots=True)
class MediaAsset:
    media_ref: str
    owner_ref: str
    kind: Literal["voice", "image", "document"]
    mime_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
    expires_at: datetime
    page_count: int = 0
    temp_path_ref: str = ""

    def __post_init__(self) -> None:
        if not _MEDIA.fullmatch(self.media_ref):
            raise ValueError("invalid media_ref")
        _ref(self.owner_ref, field="owner_ref")
        if self.kind not in MEDIA_KINDS:
            raise ValueError("invalid media kind")
        if self.mime_type in BLOCKED_MIME or self.mime_type not in ALLOWED_MIME[self.kind]:
            raise ValueError("unsupported media type")
        if not isinstance(self.size_bytes, int) or isinstance(self.size_bytes, bool) or not 1 <= self.size_bytes <= MAX_BYTES:
            raise ValueError("media size is out of range")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("invalid sha256")
        if _utc(self.expires_at) <= _utc(self.created_at):
            raise ValueError("asset must expire after creation")
        if not isinstance(self.page_count, int) or isinstance(self.page_count, bool) or not 0 <= self.page_count <= MAX_PAGES:
            raise ValueError("page_count is out of range")
        if self.temp_path_ref:
            _ref(self.temp_path_ref, field="temp_path_ref")

    def is_expired(self, now: datetime) -> bool:
        return _utc(now) >= _utc(self.expires_at)

    def to_payload(self) -> dict[str, object]:
        return {
            "media_ref": self.media_ref,
            "owner_ref": self.owner_ref,
            "kind": self.kind,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "created_at": _iso(self.created_at),
            "expires_at": _iso(self.expires_at),
            "page_count": self.page_count,
        }


def build_media_asset(
    *,
    owner_ref: str,
    kind: str,
    mime_type: str,
    content: bytes,
    now: datetime,
    ttl_seconds: int = 3600,
    page_count: int = 0,
    temp_path_ref: str = "",
) -> MediaAsset:
    """Reject malicious/oversized/unsupported content before anything else."""

    if not isinstance(content, (bytes, bytearray)) or not content:
        raise ValueError("media content must be non-empty bytes")
    if len(content) > MAX_BYTES:
        raise ValueError("media content exceeds the size limit")
    if not 60 <= ttl_seconds <= 86400:
        raise ValueError("ttl_seconds is out of range")
    moment = _utc(now)
    digest = hashlib.sha256(bytes(content)).hexdigest()
    return MediaAsset(
        media_ref="media_" + digest[:20],
        owner_ref=owner_ref,
        kind=kind,  # type: ignore[arg-type]
        mime_type=mime_type,
        size_bytes=len(content),
        sha256=digest,
        created_at=moment,
        expires_at=moment + timedelta(seconds=ttl_seconds),
        page_count=page_count,
        temp_path_ref=temp_path_ref,
    )


@dataclass(frozen=True, slots=True)
class Transcription:
    """Editable transcription; revisions never lose the original."""

    transcript_ref: str
    media_ref: str
    owner_ref: str
    text: str
    language: str
    provider_ref: str
    version: int
    created_at: datetime

    def __post_init__(self) -> None:
        _ref(self.transcript_ref, field="transcript_ref")
        _ref(self.media_ref, field="media_ref")
        _ref(self.owner_ref, field="owner_ref")
        _text(self.text, field="text", maximum=20000, required=False)
        _text(self.language, field="language", maximum=16, required=False)
        _ref(self.provider_ref, field="provider_ref")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("transcription version must be positive")


def revise_transcription(transcription: Transcription, *, text: str, now: datetime) -> Transcription:
    return replace(
        transcription,
        text=_text(text, field="text", maximum=20000, required=False),
        version=transcription.version + 1,
        created_at=_utc(now),
    )


@dataclass(frozen=True, slots=True)
class ExtractedText:
    media_ref: str
    method: Literal["text_layer", "ocr"]
    pages: tuple[tuple[int, str], ...]

    def __post_init__(self) -> None:
        _ref(self.media_ref, field="media_ref")
        if self.method not in EXTRACTION_METHODS:
            raise ValueError("invalid extraction method")
        if len(self.pages) > MAX_PAGES:
            raise ValueError("too many pages")
        seen: set[int] = set()
        for number, text in self.pages:
            if not isinstance(number, int) or isinstance(number, bool) or number < 1 or number in seen:
                raise ValueError("page numbers must be unique positive integers")
            seen.add(number)
            if len(str(text)) > 20000:
                raise ValueError("page text is too large")

    @property
    def text(self) -> str:
        return "\n".join(text for _number, text in self.pages)

    @property
    def char_count(self) -> int:
        return len(self.text)


def needs_ocr(asset: MediaAsset, extracted: ExtractedText | None) -> bool:
    """OCR only when a text layer is missing or too thin; images always need it."""

    if asset.kind == "image":
        return True
    if asset.kind != "document":
        return False
    if extracted is None or extracted.method == "ocr":
        return extracted is None
    return extracted.char_count < OCR_TEXT_THRESHOLD


@dataclass(frozen=True, slots=True)
class MediaQuestion:
    owner_ref: str
    media_ref: str
    question: str
    max_answer_chars: int = 2000

    def __post_init__(self) -> None:
        _ref(self.owner_ref, field="owner_ref")
        _ref(self.media_ref, field="media_ref")
        _text(self.question, field="question", maximum=1000)
        if not isinstance(self.max_answer_chars, int) or isinstance(self.max_answer_chars, bool) or not 100 <= self.max_answer_chars <= 8000:
            raise ValueError("max_answer_chars is out of range")


@dataclass(frozen=True, slots=True)
class MediaAnswer:
    media_ref: str
    answer: str
    page_refs: tuple[int, ...]
    source_refs: tuple[str, ...]
    extraction_method: Literal["text_layer", "ocr"]

    def __post_init__(self) -> None:
        _ref(self.media_ref, field="media_ref")
        _text(self.answer, field="answer", maximum=8000, required=False)
        if self.extraction_method not in EXTRACTION_METHODS:
            raise ValueError("invalid extraction method")
        if len(set(self.page_refs)) != len(self.page_refs) or any(page < 1 for page in self.page_refs):
            raise ValueError("page refs must be unique positive integers")
        for value in self.source_refs:
            _ref(value, field="source_ref")


@dataclass(frozen=True, slots=True)
class CleanupPlan:
    media_ref: str
    targets: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _ref(self.media_ref, field="media_ref")
        for target, _reason in self.targets:
            if target not in ("temp_file", "derived_text", "derived_thumbnail", "transcript"):
                raise ValueError("unknown cleanup target")


def plan_cleanup(asset: MediaAsset, *, had_transcript: bool = False) -> CleanupPlan:
    targets = [
        ("temp_file", "delete the uploaded temporary file"),
        ("derived_text", "drop extracted text for this asset"),
        ("derived_thumbnail", "drop any derived thumbnail/preview"),
    ]
    if had_transcript:
        targets.append(("transcript", "drop the editable transcription copy"))
    return CleanupPlan(media_ref=asset.media_ref, targets=tuple(targets))


def require_media_egress_access(
    authorization: AuthorizationDecision | None,
    *,
    purpose: str,
    owner_ref: str,
    connection_ref: str,
    resource_ref: str,
) -> None:
    """One shared, fail-closed egress check for every media surface."""

    if purpose not in ("voice.transcription", "media.vision", "media.document", "media.speech"):
        raise CapabilityDenied("unsupported media purpose")
    capability = {
        "voice.transcription": "media.transcribe",
        "media.vision": "media.vision",
        "media.document": "media.document",
        "media.speech": "media.speech",
    }[purpose]
    require_authorized_egress(
        authorization,
        capability=capability,
        provider_ref="provider_openai",
        data_class=DATA_CLASS,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=resource_ref,
        purpose=purpose,
    )


class MediaAdapter(Protocol):
    def extract_text(self, asset: MediaAsset) -> ExtractedText: ...

    def ocr(self, asset: MediaAsset) -> ExtractedText: ...

    def understand(self, question: MediaQuestion, text: ExtractedText) -> MediaAnswer: ...

    def transcribe(self, asset: MediaAsset) -> Transcription: ...

    def speak(self, text: str, *, voice_ref: str) -> bytes: ...
