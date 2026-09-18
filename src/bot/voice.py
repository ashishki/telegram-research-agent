import json
import logging
import os
import uuid
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
DEFAULT_VOICE_MEDIA_DIR = "/tmp/telegram-research-agent-voice"
DEFAULT_TRANSCRIPTION_MODEL = "whisper-1"
DEFAULT_MAX_VOICE_BYTES = 24 * 1024 * 1024
TELEGRAM_PROVIDER_REF = "provider_telegram"
OPENAI_PROVIDER_REF = "provider_openai"
VOICE_DOWNLOAD_CAPABILITY = "media.voice_download"
VOICE_TRANSCRIPTION_CAPABILITY = "media.transcribe"


class VoiceTranscriptionError(RuntimeError):
    pass


class VoiceTranscriptionUnavailable(VoiceTranscriptionError):
    pass


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
    if not file_id:
        raise VoiceTranscriptionError("Telegram voice file_id is missing")
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
        return transcribe_audio_file(
            local_path,
            transcription_authorization=transcription_authorization,
            owner_ref=owner_ref,
            connection_ref=connection_ref,
            resource_ref=voice_resource_ref,
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
    if not _voice_transcription_authorized(
        transcription_authorization,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=resource_ref,
    ):
        raise VoiceTranscriptionUnavailable("Voice transcription requires an active capability grant")
    api_key = _require_openai_transcription_key()

    path = Path(local_path)
    if not path.exists():
        raise VoiceTranscriptionError(f"Voice file does not exist: {path}")

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
    body, boundary = _build_multipart_body(fields=fields, file_field="file", path=path)
    http_request = request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    _require_voice_transcription_authorization(
        transcription_authorization,
        owner_ref=owner_ref,
        connection_ref=connection_ref,
        resource_ref=resource_ref,
    )
    try:
        with request.urlopen(http_request, timeout=120) as response:
            payload = response.read().decode("utf-8")
    except Exception as exc:
        LOGGER.warning("OpenAI voice transcription failed path=%s", path.name, exc_info=True)
        raise VoiceTranscriptionError("OpenAI voice transcription failed") from exc

    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise VoiceTranscriptionError("OpenAI transcription response was not JSON") from exc

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
    dest_dir = Path(media_dir or os.environ.get("TELEGRAM_VOICE_MEDIA_DIR", "") or DEFAULT_VOICE_MEDIA_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{file_id}_{uuid.uuid4().hex[:8]}.ogg"
    try:
        with request.urlopen(url, timeout=60) as response:
            data = response.read()
    except Exception as exc:
        raise VoiceTranscriptionError("Telegram voice download failed") from exc

    max_bytes = int(os.environ.get("TELEGRAM_VOICE_MAX_BYTES", DEFAULT_MAX_VOICE_BYTES))
    if len(data) > max_bytes:
        raise VoiceTranscriptionError(f"Telegram voice file is too large: {len(data)} bytes")
    dest_path.write_bytes(data)
    LOGGER.info("Downloaded Telegram voice file path=%s bytes=%d", dest_path.name, len(data))
    return str(dest_path)


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
    except Exception as exc:
        raise VoiceTranscriptionError("Telegram getFile failed") from exc
    decoded = json.loads(payload)
    if not decoded.get("ok"):
        raise VoiceTranscriptionError(f"Telegram getFile returned an error: {decoded!r}")
    result = decoded.get("result") if isinstance(decoded, dict) else None
    file_path = str((result or {}).get("file_path") or "").strip()
    if not file_path:
        raise VoiceTranscriptionError("Telegram getFile response did not include file_path")
    return file_path


def _build_multipart_body(*, fields: dict[str, str], file_field: str, path: Path) -> tuple[bytes, str]:
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
            f'Content-Disposition: form-data; name="{file_field}"; filename="{path.name}"\r\n'
            "Content-Type: audio/ogg\r\n\r\n"
        ).encode("utf-8")
    )
    body.extend(path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return bytes(body), boundary


def _delete_local_file(local_path: str) -> None:
    try:
        Path(local_path).unlink(missing_ok=True)
    except Exception:
        LOGGER.warning("Failed to delete local Telegram voice file path=%s", local_path, exc_info=True)
