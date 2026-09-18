import json
import logging
import os
import re
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib import parse, request

from bot.telegram_delivery import BOT_API_BASE
from prm.capabilities import (
    AuthorizationDecision,
    CapabilityDenied,
    is_authorized_egress,
    is_authorized_operation,
    require_authorized_egress,
    require_authorized_operation,
)


LOGGER = logging.getLogger(__name__)
TELEGRAM_FILE_BASE = "https://api.telegram.org/file"
DEFAULT_TRANSCRIPTION_MODEL = "whisper-1"
DEFAULT_MAX_VOICE_BYTES = 24 * 1024 * 1024
VOICE_MEDIA_DIR_PREFIX = "telegram-research-agent-voice-"
VOICE_MEDIA_FILE_PREFIX = "voice-"
VOICE_ATTACHMENT_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,512}")
TELEGRAM_PROVIDER_REF = "provider_telegram"
OPENAI_PROVIDER_REF = "provider_openai"
VOICE_DOWNLOAD_CAPABILITY = "media.voice_download"
VOICE_TRANSCRIPTION_CAPABILITY = "media.transcribe"


class VoiceTranscriptionError(RuntimeError):
    pass


class VoiceTranscriptionUnavailable(VoiceTranscriptionError):
    pass


@dataclass(frozen=True, slots=True)
class _VerifiedTelegramVoiceAttachment:
    """A local file whose resource identity came from Telegram ``getFile`` flow."""

    local_path: str
    file_id: str
    audio_bytes: bytes


def transcribe_telegram_voice(
    *,
    token: str,
    file_id: str,
    media_dir: str | None = None,
    download_authorization: AuthorizationDecision | None = None,
    download_file_authorization: AuthorizationDecision | None = None,
    transcription_authorization: AuthorizationDecision | None = None,
    owner_ref: str | None = None,
    connection_ref: str | None = None,
) -> str:
    """Download a Telegram voice file, transcribe it, and remove local audio."""
    if not token:
        raise VoiceTranscriptionError("Telegram bot token is missing")
    _require_safe_telegram_attachment_id(file_id)
    # The resource is the received Telegram attachment.  Do not allow a caller
    # to substitute an unrelated label for the file that will cross Telegram
    # and OpenAI boundaries.
    voice_resource_ref = file_id
    if not _voice_transcription_authorized(
        transcription_authorization,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=voice_resource_ref,
    ):
        raise VoiceTranscriptionUnavailable("Voice transcription requires an active capability grant")
    if not _voice_download_authorized(
        download_authorization,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=voice_resource_ref,
    ) or not _voice_download_authorized(
        download_file_authorization,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=voice_resource_ref,
    ):
        raise VoiceTranscriptionUnavailable("Each Telegram voice request requires an active capability grant")
    _require_openai_transcription_key()

    local_path = _download_telegram_voice(
        token=token,
        file_id=file_id,
        media_dir=media_dir,
        get_file_authorization=download_authorization,
        download_file_authorization=download_file_authorization,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=voice_resource_ref,
    )
    try:
        return _transcribe_verified_telegram_audio(
            _verified_telegram_voice_attachment(local_path=local_path, file_id=file_id),
            transcription_authorization=transcription_authorization,
            owner_ref=owner_ref,
            connection_ref=connection_ref,
        )
    finally:
        _delete_local_file(local_path)


def transcribe_audio_file(
    local_path: str,
    *,
    transcription_authorization: AuthorizationDecision | None = None,
    owner_ref: str | None = None,
    connection_ref: str | None = None,
    resource_ref: str | None = None,
) -> str:
    """Reject unverified local paths; only the Telegram wrapper can upload audio.

    A caller-supplied path plus a caller-supplied resource label does not prove
    that the label identifies the bytes about to leave the process.  PA-15 can
    add other ingress-specific verified bindings; PA-02 deliberately has none.
    """
    del local_path, transcription_authorization, owner_ref, connection_ref, resource_ref
    raise VoiceTranscriptionUnavailable(
        "Direct local audio transcription requires a verified attachment binding"
    )


def _transcribe_verified_telegram_audio(
    attachment: _VerifiedTelegramVoiceAttachment,
    *,
    transcription_authorization: AuthorizationDecision | None = None,
    owner_ref: str | None = None,
    connection_ref: str | None = None,
) -> str:
    """Upload only the immutable resource/path pair created by the wrapper."""
    resource_ref = attachment.file_id
    if not _voice_transcription_authorized(
        transcription_authorization,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=resource_ref,
    ):
        raise VoiceTranscriptionUnavailable("Voice transcription requires an active capability grant")
    api_key = _require_openai_transcription_key()

    model = (
        os.environ.get("VOICE_TRANSCRIPTION_MODEL", "").strip()
        or os.environ.get("OPENAI_TRANSCRIPTION_MODEL", "").strip()
        or DEFAULT_TRANSCRIPTION_MODEL
    )
    language = os.environ.get("VOICE_TRANSCRIPTION_LANGUAGE", "").strip()
    endpoint = os.environ.get("OPENAI_AUDIO_TRANSCRIPTIONS_URL", "").strip() or (
        "https://api.openai.com/v1/audio/transcriptions"
    )

    fields = {"model": model}
    if language:
        fields["language"] = language
    _require_voice_transcription_authorization(
        transcription_authorization,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=resource_ref,
    )
    body, boundary = _build_multipart_body(
        fields=fields,
        file_field="file",
        file_name=Path(attachment.local_path).name,
        file_bytes=attachment.audio_bytes,
    )
    http_request = request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with request.urlopen(http_request, timeout=120) as response:
            payload = response.read().decode("utf-8")
    except Exception:
        LOGGER.warning("OpenAI voice transcription failed")
        raise VoiceTranscriptionError("OpenAI voice transcription failed") from None

    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        raise VoiceTranscriptionError("OpenAI transcription response was not JSON") from None

    text = str(decoded.get("text") or "").strip()
    if not text:
        raise VoiceTranscriptionError("OpenAI transcription response did not include text")
    return text


def _require_openai_transcription_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise VoiceTranscriptionUnavailable("OPENAI_API_KEY is not set")
    return api_key


def _require_voice_download_authorization(
    authorization: AuthorizationDecision | None,
    *,
    owner_ref: str | None,
    connection_ref: str | None,
    resource_ref: str | None,
) -> None:
    try:
        require_authorized_operation(
            authorization,
            capability=VOICE_DOWNLOAD_CAPABILITY,
            operation="read",
            provider_ref=TELEGRAM_PROVIDER_REF,
            data_class="user_provided",
            owner_ref=owner_ref or "",
            connection_ref=connection_ref,
            resource_ref=resource_ref or "",
        )
    except CapabilityDenied as exc:
        raise VoiceTranscriptionUnavailable("Voice download requires an active capability grant") from exc


def _voice_download_authorized(
    authorization: AuthorizationDecision | None,
    *,
    owner_ref: str | None,
    connection_ref: str | None,
    resource_ref: str | None,
) -> bool:
    return bool(
        owner_ref
        and resource_ref
        and is_authorized_operation(
            authorization,
            capability=VOICE_DOWNLOAD_CAPABILITY,
            operation="read",
            provider_ref=TELEGRAM_PROVIDER_REF,
            data_class="user_provided",
            owner_ref=owner_ref,
            connection_ref=connection_ref,
            resource_ref=resource_ref,
        )
    )


def _voice_transcription_authorized(
    authorization: AuthorizationDecision | None,
    *,
    owner_ref: str | None,
    connection_ref: str | None,
    resource_ref: str | None,
) -> bool:
    return bool(
        owner_ref
        and resource_ref
        and is_authorized_egress(
            authorization,
            capability=VOICE_TRANSCRIPTION_CAPABILITY,
            provider_ref=OPENAI_PROVIDER_REF,
            data_class="user_provided",
            owner_ref=owner_ref,
            connection_ref=connection_ref,
            resource_ref=resource_ref,
        )
    )


def _require_voice_transcription_authorization(
    authorization: AuthorizationDecision | None,
    *,
    owner_ref: str | None,
    connection_ref: str | None,
    resource_ref: str | None,
) -> None:
    try:
        require_authorized_egress(
            authorization,
            capability=VOICE_TRANSCRIPTION_CAPABILITY,
            provider_ref=OPENAI_PROVIDER_REF,
            data_class="user_provided",
            owner_ref=owner_ref or "",
            connection_ref=connection_ref,
            resource_ref=resource_ref or "",
        )
    except CapabilityDenied as exc:
        raise VoiceTranscriptionUnavailable("Voice transcription requires an active capability grant") from exc


def _download_telegram_voice(
    *,
    token: str,
    file_id: str,
    media_dir: str | None,
    get_file_authorization: AuthorizationDecision | None,
    download_file_authorization: AuthorizationDecision | None,
    owner_ref: str | None,
    connection_ref: str | None,
    resource_ref: str | None,
) -> str:
    _require_safe_telegram_attachment_id(file_id)
    file_path = _get_telegram_file_path(
        token=token,
        file_id=file_id,
        authorization=get_file_authorization,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=resource_ref,
    )
    url = f"{TELEGRAM_FILE_BASE}/bot{token}/{file_path}"
    _require_voice_download_authorization(
        download_file_authorization,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=resource_ref,
    )
    try:
        with request.urlopen(url, timeout=60) as response:
            data = response.read()
    except Exception:
        raise VoiceTranscriptionError("Telegram voice download failed") from None

    max_bytes = int(os.environ.get("TELEGRAM_VOICE_MAX_BYTES", DEFAULT_MAX_VOICE_BYTES))
    if len(data) > max_bytes:
        raise VoiceTranscriptionError(f"Telegram voice file is too large: {len(data)} bytes")
    dest_dir = _create_private_voice_directory(media_dir)
    try:
        dest_path = _write_private_voice_file(dest_dir, data)
    except OSError:
        _delete_private_voice_directory(dest_dir)
        raise VoiceTranscriptionError("Telegram voice file could not be stored") from None
    LOGGER.info("Downloaded Telegram voice bytes=%d", len(data))
    return str(dest_path)


def _require_safe_telegram_attachment_id(file_id: str) -> None:
    """Keep the provider attachment identity out of local path construction."""

    if not isinstance(file_id, str) or not VOICE_ATTACHMENT_ID_PATTERN.fullmatch(file_id):
        raise VoiceTranscriptionError("Telegram voice attachment identifier is invalid")


def _create_private_voice_directory(media_dir: str | None) -> Path:
    """Create a fresh, owner-private directory for one downloaded attachment."""

    configured_dir = (media_dir or os.environ.get("TELEGRAM_VOICE_MEDIA_DIR", "")).strip()
    if configured_dir:
        parent = Path(configured_dir)
        _ensure_private_voice_parent(parent)
        dest_dir = Path(tempfile.mkdtemp(prefix=VOICE_MEDIA_DIR_PREFIX, dir=str(parent)))
    else:
        # ``mkdtemp`` chooses a randomized directory below the platform's secure
        # temporary area instead of a predictable shared /tmp path.
        dest_dir = Path(tempfile.mkdtemp(prefix=VOICE_MEDIA_DIR_PREFIX))
    _ensure_private_voice_directory(dest_dir)
    return dest_dir


def _ensure_private_voice_parent(parent: Path) -> None:
    """Create or validate an explicitly configured parent without following links."""

    try:
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        metadata = parent.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise OSError("voice media parent is not a directory")
        os.chmod(parent, 0o700)
        _ensure_private_voice_directory(parent)
    except OSError:
        raise VoiceTranscriptionError("Telegram voice media directory is not private") from None


def _ensure_private_voice_directory(directory: Path) -> None:
    metadata = directory.stat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise OSError("voice media path is not a directory")
    if metadata.st_mode & 0o077:
        raise OSError("voice media directory permissions are not private")
    geteuid = getattr(os, "geteuid", None)
    if geteuid is not None and metadata.st_uid != geteuid():
        raise OSError("voice media directory is not owned by this process")


def _write_private_voice_file(dest_dir: Path, data: bytes) -> Path:
    """Write raw audio once to a randomized, identifier-free 0600 file."""

    descriptor, raw_path = tempfile.mkstemp(
        prefix=VOICE_MEDIA_FILE_PREFIX,
        suffix=".ogg",
        dir=str(dest_dir),
    )
    dest_path = Path(raw_path)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as voice_file:
            descriptor = -1
            written = voice_file.write(data)
            if written != len(data):
                raise OSError("incomplete voice file write")
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    return dest_path


def _verified_telegram_voice_attachment(
    *,
    local_path: str,
    file_id: str,
) -> _VerifiedTelegramVoiceAttachment:
    """Freeze the just-downloaded bytes with their Telegram attachment identity."""

    path = Path(local_path)
    try:
        audio_bytes = path.read_bytes()
    except OSError:
        raise VoiceTranscriptionError("Downloaded Telegram voice file is unavailable") from None
    return _VerifiedTelegramVoiceAttachment(
        local_path=str(path),
        file_id=file_id,
        audio_bytes=audio_bytes,
    )


def _get_telegram_file_path(
    *,
    token: str,
    file_id: str,
    authorization: AuthorizationDecision | None,
    owner_ref: str | None,
    connection_ref: str | None,
    resource_ref: str | None,
) -> str:
    url = f"{BOT_API_BASE}/bot{token}/getFile?file_id={parse.quote(file_id, safe='')}"
    _require_voice_download_authorization(
        authorization,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=resource_ref,
    )
    try:
        with request.urlopen(url, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except Exception:
        raise VoiceTranscriptionError("Telegram getFile failed") from None
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        raise VoiceTranscriptionError("Telegram getFile response was not JSON") from None
    if not isinstance(decoded, dict) or decoded.get("ok") is not True:
        raise VoiceTranscriptionError("Telegram getFile returned an error")
    result = decoded.get("result")
    file_path = str((result or {}).get("file_path") or "").strip()
    if not file_path:
        raise VoiceTranscriptionError("Telegram getFile response did not include file_path")
    return file_path


def _build_multipart_body(
    *,
    fields: dict[str, str],
    file_field: str,
    file_name: str,
    file_bytes: bytes,
) -> tuple[bytes, str]:
    boundary = f"----telegram-research-{uuid.uuid4().hex}"
    body = bytearray()

    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")

    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"\r\n'
            "Content-Type: audio/ogg\r\n\r\n"
        ).encode("utf-8")
    )
    body.extend(file_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return bytes(body), boundary


def _delete_local_file(local_path: str) -> None:
    path = Path(local_path)
    try:
        path.unlink(missing_ok=True)
    except Exception:
        LOGGER.warning("Failed to delete local Telegram voice file")
        return
    _delete_private_voice_directory(path.parent)


def _delete_private_voice_directory(directory: Path) -> None:
    """Remove only the randomized per-attachment directory we created."""

    if not directory.name.startswith(VOICE_MEDIA_DIR_PREFIX):
        return
    try:
        _ensure_private_voice_directory(directory)
        for child in directory.iterdir():
            child_metadata = child.lstat()
            if not (stat.S_ISREG(child_metadata.st_mode) or stat.S_ISLNK(child_metadata.st_mode)):
                raise OSError("private voice directory contains an unexpected entry")
            child.unlink()
        directory.rmdir()
    except FileNotFoundError:
        return
    except OSError:
        LOGGER.warning("Failed to delete local Telegram voice directory")
