import json
import logging
import uuid
from pathlib import Path
from urllib import parse, request


LOGGER = logging.getLogger(__name__)
BOT_API_BASE = "https://api.telegram.org"
MESSAGE_CHUNK_SIZE = 4000


def _chunk_text(text: str, chunk_size: int = MESSAGE_CHUNK_SIZE) -> list[str]:
    if not text:
        return [""]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= chunk_size:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, chunk_size)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, chunk_size)
        if split_at <= 0:
            split_at = chunk_size

        chunk = remaining[:split_at].rstrip()
        if not chunk:
            chunk = remaining[:chunk_size]
            split_at = len(chunk)
        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()

    return chunks


def _telegram_request(url: str, data: bytes, headers: dict[str, str]) -> dict:
    http_request = request.Request(url, data=data, headers=headers, method="POST")
    with request.urlopen(http_request, timeout=60) as response:
        payload = response.read().decode("utf-8")
    decoded = json.loads(payload)
    if not decoded.get("ok"):
        raise RuntimeError(f"Telegram API returned error: {decoded!r}")
    return decoded


def _send_text_internal(chat_id: str, text: str, token: str, parse_mode: str | None = "Markdown") -> None:
    if not token:
        LOGGER.warning("Telegram send skipped because TELEGRAM_BOT_TOKEN is not set")
        return

    url = f"{BOT_API_BASE}/bot{token}/sendMessage"
    for chunk in _chunk_text(text):
        payload_dict = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": "true",
        }
        if parse_mode:
            payload_dict["parse_mode"] = parse_mode
        payload = parse.urlencode(payload_dict).encode("utf-8")
        _telegram_request(
            url=url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )


def send_text(chat_id: str, text: str, token: str, parse_mode: str | None = "HTML") -> None:
    _send_text_internal(chat_id=chat_id, text=text, token=token, parse_mode=parse_mode)


def send_document(chat_id: str, file_path: str, caption: str, token: str) -> None:
    if not token:
        LOGGER.warning("Telegram file send skipped because TELEGRAM_BOT_TOKEN is not set")
        return

    path = Path(file_path)
    if not path.exists():
        LOGGER.warning("Telegram file send skipped because file does not exist path=%s", path)
        return

    boundary = f"----codex-{uuid.uuid4().hex}"
    body = bytearray()

    def add_field(name: str, value: str) -> None:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")

    add_field("chat_id", chat_id)
    if caption:
        add_field("caption", caption)

    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        (
            f'Content-Disposition: form-data; name="document"; filename="{path.name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
    )
    body.extend(path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    _telegram_request(
        url=f"{BOT_API_BASE}/bot{token}/sendDocument",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )


# T21: not used in delivery path
def send_digest_bundle(
    chat_id: str,
    week_label: str,
    executive_summary: list[str],
    pdf_path: str | None,
    markdown_path: str,
    token: str,
) -> None:
    pdf_file = Path(pdf_path) if pdf_path else None
    if pdf_file and pdf_file.exists():
        summary_lines = [f"Weekly Digest {week_label}"]
        if executive_summary:
            summary_lines.append("")
            summary_lines.extend(f"- {line}" for line in executive_summary if line.strip())
        _send_text_internal(chat_id=chat_id, text="\n".join(summary_lines), token=token, parse_mode=None)
        send_document(chat_id=chat_id, file_path=str(pdf_file), caption=f"Weekly Digest {week_label}", token=token)
        return

    markdown_file = Path(markdown_path)
    if not markdown_file.exists():
        LOGGER.warning("Digest markdown fallback is missing week=%s path=%s", week_label, markdown_file)
        _send_text_internal(
            chat_id=chat_id,
            text=f"Digest {week_label} is unavailable right now.",
            token=token,
            parse_mode=None,
        )
        return

    send_text(chat_id=chat_id, text=markdown_file.read_text(encoding="utf-8"), token=token)


def send_report_preview(
    chat_id: str,
    title: str,
    summary_lines: list[str],
    week_label: str,
    token: str,
) -> None:
    lines = [title, f"Week: {week_label}"]
    if summary_lines:
        lines.append("")
        lines.extend(f"- {line}" for line in summary_lines if line.strip())
    send_text(chat_id=chat_id, text="\n".join(lines), token=token)
