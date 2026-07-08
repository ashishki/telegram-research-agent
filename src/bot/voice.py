import json
import logging
import os
import uuid
from pathlib import Path
from urllib import parse, request

from bot.telegram_delivery import BOT_API_BASE


LOGGER = logging.getLogger(__name__)
TELEGRAM_FILE_BASE = "https://api.telegram.org/file"
DEFAULT_VOICE_MEDIA_DIR = "/tmp/telegram-research-agent-voice"
DEFAULT_TRANSCRIPTION_MODEL = "whisper-1"
DEFAULT_MAX_VOICE_BYTES = 24 * 1024 * 1024


class VoiceTranscriptionError(RuntimeError):
    pass


class VoiceTranscriptionUnavailable(VoiceTranscriptionError):
    pass


def transcribe_telegram_voice(
    *,
    token: str,
    file_id: str,
    media_dir: str | None = None,
) -> str:
    """Download a Telegram voice file, transcribe it, and remove local audio."""
    _require_openai_transcription_key()
    if not token:
        raise VoiceTranscriptionError("Telegram bot token is missing")
    if not file_id:
        raise VoiceTranscriptionError("Telegram voice file_id is missing")

    local_path = _download_telegram_voice(token=token, file_id=file_id, media_dir=media_dir)
    try:
        return transcribe_audio_file(local_path)
    finally:
        _delete_local_file(local_path)


def transcribe_audio_file(local_path: str) -> str:
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


def _download_telegram_voice(*, token: str, file_id: str, media_dir: str | None) -> str:
    file_path = _get_telegram_file_path(token=token, file_id=file_id)
    dest_dir = Path(media_dir or os.environ.get("TELEGRAM_VOICE_MEDIA_DIR", "") or DEFAULT_VOICE_MEDIA_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{file_id}_{uuid.uuid4().hex[:8]}.ogg"

    url = f"{TELEGRAM_FILE_BASE}/bot{token}/{file_path}"
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


def _get_telegram_file_path(*, token: str, file_id: str) -> str:
    url = f"{BOT_API_BASE}/bot{token}/getFile?file_id={parse.quote(file_id, safe='')}"
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
