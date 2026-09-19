import json
import logging
import os
import re
import hashlib
import uuid
from dataclasses import dataclass
from urllib import parse, request

from bot.telegram_delivery import BOT_API_BASE
from prm.capabilities import (
    AuthorizationDecision,
    CapabilityDenied,
    is_authorized_egress,
    is_authorized_operation,
    require_authorized_egress,
    require_authorized_operation,
    transport_purpose,
)


LOGGER = logging.getLogger(__name__)
TELEGRAM_FILE_BASE = "https://api.telegram.org/file"
DEFAULT_TRANSCRIPTION_MODEL = "whisper-1"
DEFAULT_MAX_VOICE_BYTES = 24 * 1024 * 1024
VOICE_ATTACHMENT_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,512}")
TELEGRAM_FILE_PATH_SEGMENT_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}")
MAX_TELEGRAM_FILE_PATH_CHARS = 1024
TELEGRAM_PROVIDER_REF = "provider_telegram"
OPENAI_PROVIDER_REF = "provider_openai"
VOICE_DOWNLOAD_CAPABILITY = "media.voice_download"
VOICE_TRANSCRIPTION_CAPABILITY = "media.transcribe"
OPENAI_TRANSCRIPTIONS_ENDPOINT = "https://api.openai.com/v1/audio/transcriptions"


class VoiceTranscriptionError(RuntimeError):
    pass


class VoiceTranscriptionUnavailable(VoiceTranscriptionError):
    pass


class _RejectRedirects(request.HTTPRedirectHandler):
    """Never follow a transcription redirect to a different recipient."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        del req, fp, code, msg, headers, newurl
        return None


@dataclass(frozen=True, slots=True)
class _VerifiedTelegramVoiceAttachment:
    """Immutable bytes bound to the Telegram attachment read that returned them."""

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
    """Download and transcribe a Telegram voice attachment without disk staging."""
    if not token:
        raise VoiceTranscriptionError("Telegram bot token is missing")
    del connection_ref
    telegram_connection_ref = _telegram_connection_ref(token)
    if telegram_connection_ref is None:
        raise VoiceTranscriptionUnavailable("Telegram voice download requires a configured connection")
    api_key = _require_openai_transcription_key()
    openai_connection_ref = _openai_connection_ref(api_key)
    _require_safe_telegram_attachment_id(file_id)
    # The resource is the received Telegram attachment.  Do not allow a caller
    # to substitute an unrelated label for the file that will cross Telegram
    # and OpenAI boundaries.
    voice_resource_ref = file_id
    if not _voice_transcription_authorized(
        transcription_authorization,
        owner_ref=owner_ref,
        connection_ref=openai_connection_ref,
        resource_ref=voice_resource_ref,
    ):
        raise VoiceTranscriptionUnavailable("Voice transcription requires an active capability grant")
    if not _voice_download_authorized(
        download_authorization,
        owner_ref=owner_ref,
        connection_ref=telegram_connection_ref,
        resource_ref=voice_resource_ref,
    ) or not _voice_download_authorized(
        download_file_authorization,
        owner_ref=owner_ref,
        connection_ref=telegram_connection_ref,
        resource_ref=voice_resource_ref,
    ):
        raise VoiceTranscriptionUnavailable("Each Telegram voice request requires an active capability grant")
    # ``media_dir`` remains an accepted compatibility argument, but PA-02 never
    # stages raw user audio on disk.  The bound bytes live only for this request.
    del media_dir
    attachment = _download_telegram_voice(
        token=token,
        file_id=file_id,
        media_dir=None,
        get_file_authorization=download_authorization,
        download_file_authorization=download_file_authorization,
        owner_ref=owner_ref,
        connection_ref=telegram_connection_ref,
        resource_ref=voice_resource_ref,
    )
    return _transcribe_verified_telegram_audio(
        attachment,
        transcription_authorization=transcription_authorization,
        owner_ref=owner_ref,
        connection_ref=openai_connection_ref,
    )


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
    del connection_ref
    resource_ref = attachment.file_id
    api_key = _require_openai_transcription_key()
    openai_connection_ref = _openai_connection_ref(api_key)
    if not _voice_transcription_authorized(
        transcription_authorization,
        owner_ref=owner_ref,
        connection_ref=openai_connection_ref,
        resource_ref=resource_ref,
    ):
        raise VoiceTranscriptionUnavailable("Voice transcription requires an active capability grant")

    model = (
        os.environ.get("VOICE_TRANSCRIPTION_MODEL", "").strip()
        or os.environ.get("OPENAI_TRANSCRIPTION_MODEL", "").strip()
        or DEFAULT_TRANSCRIPTION_MODEL
    )
    language = os.environ.get("VOICE_TRANSCRIPTION_LANGUAGE", "").strip()

    fields = {"model": model}
    if language:
        fields["language"] = language
    _require_voice_transcription_authorization(
        transcription_authorization,
        owner_ref=owner_ref,
        connection_ref=openai_connection_ref,
        resource_ref=resource_ref,
    )
    body, boundary = _build_multipart_body(
        fields=fields,
        file_field="file",
        file_name="voice.ogg",
        file_bytes=attachment.audio_bytes,
    )
    http_request = request.Request(
        OPENAI_TRANSCRIPTIONS_ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with _open_openai_transcription_request(http_request, timeout=120) as response:
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


def _open_openai_transcription_request(http_request: request.Request, *, timeout: int):
    """Allow one fixed OpenAI endpoint and reject all redirect destinations."""

    parsed = parse.urlsplit(http_request.full_url)
    expected = parse.urlsplit(OPENAI_TRANSCRIPTIONS_ENDPOINT)
    if (
        parsed.scheme != expected.scheme
        or parsed.netloc != expected.netloc
        or parsed.path != expected.path
        or parsed.query
        or parsed.fragment
    ):
        raise VoiceTranscriptionError("OpenAI transcription endpoint is not approved")
    return request.build_opener(_RejectRedirects()).open(http_request, timeout=timeout)


def _open_telegram_voice_download_request(http_request: request.Request, *, timeout: int):
    """Fetch voice bytes only from Telegram's fixed file origin, without redirects."""

    parsed = parse.urlsplit(http_request.full_url)
    expected = parse.urlsplit(TELEGRAM_FILE_BASE)
    file_prefix = f"{expected.path.rstrip('/')}/bot"
    if (
        parsed.scheme != expected.scheme
        or parsed.netloc != expected.netloc
        or not parsed.path.startswith(file_prefix)
        or len(parsed.path) <= len(file_prefix)
        or parsed.query
        or parsed.fragment
    ):
        raise VoiceTranscriptionError("Telegram voice download endpoint is not approved")
    return request.build_opener(_RejectRedirects()).open(http_request, timeout=timeout)


def _open_telegram_get_file_request(http_request: request.Request, *, timeout: int):
    """Call Telegram's fixed ``getFile`` endpoint without accepting redirects."""

    parsed = parse.urlsplit(http_request.full_url)
    expected = parse.urlsplit(BOT_API_BASE)
    bot_prefix = f"{expected.path.rstrip('/')}/bot"
    query = parse.parse_qsl(parsed.query, keep_blank_values=True)
    if (
        parsed.scheme != expected.scheme
        or parsed.netloc != expected.netloc
        or not parsed.path.startswith(bot_prefix)
        or not parsed.path.endswith("/getFile")
        or len(parsed.path) <= len(bot_prefix) + len("/getFile")
        or parsed.fragment
        or len(query) != 1
        or query[0][0] != "file_id"
        or not query[0][1]
    ):
        raise VoiceTranscriptionError("Telegram getFile endpoint is not approved")
    return request.build_opener(_RejectRedirects()).open(http_request, timeout=timeout)


def _telegram_connection_ref(token: str) -> str | None:
    return _credential_connection_ref("telegram", token)


def _openai_connection_ref(api_key: str) -> str | None:
    return _credential_connection_ref("openai", api_key)


def _credential_connection_ref(provider: str, credential: str) -> str | None:
    """Return an opaque in-memory ref for exactly one configured credential."""

    clean_credential = str(credential or "").strip()
    if not clean_credential:
        return None
    return f"connection_{provider}_{hashlib.sha256(clean_credential.encode('utf-8')).hexdigest()[:32]}"


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
            purpose=transport_purpose(
                provider_ref=TELEGRAM_PROVIDER_REF,
                capability=VOICE_DOWNLOAD_CAPABILITY,
                operation="read",
            ),
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
            purpose=transport_purpose(
                provider_ref=TELEGRAM_PROVIDER_REF,
                capability=VOICE_DOWNLOAD_CAPABILITY,
                operation="read",
            ),
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
            purpose=transport_purpose(
                provider_ref=OPENAI_PROVIDER_REF,
                capability=VOICE_TRANSCRIPTION_CAPABILITY,
                operation="model_egress",
            ),
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
            purpose=transport_purpose(
                provider_ref=OPENAI_PROVIDER_REF,
                capability=VOICE_TRANSCRIPTION_CAPABILITY,
                operation="model_egress",
            ),
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
) -> _VerifiedTelegramVoiceAttachment:
    # Kept in the private helper signature for compatibility; raw user audio is
    # deliberately never written there or to any other local path.
    del media_dir, connection_ref
    telegram_connection_ref = _telegram_connection_ref(token)
    if telegram_connection_ref is None:
        raise VoiceTranscriptionUnavailable("Telegram voice download requires a configured connection")
    _require_safe_telegram_attachment_id(file_id)
    file_path = _require_safe_telegram_file_path(_get_telegram_file_path(
        token=token,
        file_id=file_id,
        authorization=get_file_authorization,
        owner_ref=owner_ref,
        connection_ref=telegram_connection_ref,
        resource_ref=resource_ref,
    ))
    url = f"{TELEGRAM_FILE_BASE}/bot{token}/{file_path}"
    _require_voice_download_authorization(
        download_file_authorization,
        owner_ref=owner_ref,
        connection_ref=telegram_connection_ref,
        resource_ref=resource_ref,
    )
    try:
        with _open_telegram_voice_download_request(request.Request(url), timeout=60) as response:
            data = response.read()
    except Exception:
        raise VoiceTranscriptionError("Telegram voice download failed") from None

    max_bytes = int(os.environ.get("TELEGRAM_VOICE_MAX_BYTES", DEFAULT_MAX_VOICE_BYTES))
    if len(data) > max_bytes:
        raise VoiceTranscriptionError(f"Telegram voice file is too large: {len(data)} bytes")
    LOGGER.info("Downloaded Telegram voice bytes=%d", len(data))
    return _VerifiedTelegramVoiceAttachment(file_id=file_id, audio_bytes=data)


def _require_safe_telegram_attachment_id(file_id: str) -> None:
    """Keep the provider attachment identity out of local path construction."""

    if not isinstance(file_id, str) or not VOICE_ATTACHMENT_ID_PATTERN.fullmatch(file_id):
        raise VoiceTranscriptionError("Telegram voice attachment identifier is invalid")


def _require_safe_telegram_file_path(file_path: object) -> str:
    """Accept only a bounded, relative Telegram file path without URL syntax."""

    if not isinstance(file_path, str):
        raise VoiceTranscriptionError("Telegram getFile response included an invalid file_path")
    clean_path = file_path.strip()
    parsed = parse.urlsplit(clean_path)
    if (
        not clean_path
        or len(clean_path) > MAX_TELEGRAM_FILE_PATH_CHARS
        or clean_path.startswith("/")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or "\\" in clean_path
    ):
        raise VoiceTranscriptionError("Telegram getFile response included an invalid file_path")
    segments = clean_path.split("/")
    if any(
        segment in {"", ".", ".."}
        or not TELEGRAM_FILE_PATH_SEGMENT_PATTERN.fullmatch(segment)
        for segment in segments
    ):
        raise VoiceTranscriptionError("Telegram getFile response included an invalid file_path")
    return clean_path


def _get_telegram_file_path(
    *,
    token: str,
    file_id: str,
    authorization: AuthorizationDecision | None,
    owner_ref: str | None,
    connection_ref: str | None,
    resource_ref: str | None,
) -> str:
    del connection_ref
    telegram_connection_ref = _telegram_connection_ref(token)
    if telegram_connection_ref is None:
        raise VoiceTranscriptionUnavailable("Telegram voice download requires a configured connection")
    url = f"{BOT_API_BASE}/bot{token}/getFile?file_id={parse.quote(file_id, safe='')}"
    _require_voice_download_authorization(
        authorization,
        owner_ref=owner_ref,
        connection_ref=telegram_connection_ref,
        resource_ref=resource_ref,
    )
    try:
        with _open_telegram_get_file_request(request.Request(url), timeout=30) as response:
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
    file_path = (result or {}).get("file_path")
    return _require_safe_telegram_file_path(file_path)


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
