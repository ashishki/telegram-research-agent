import base64
import logging
import os
import tempfile

from llm.client import LLMClient


LOGGER = logging.getLogger(__name__)
CATEGORY = "photo_analysis"

SYSTEM_PROMPT = (
    "You are analyzing images from Russian-language Telegram tech channels. "
    "Be concise and focus only on technically relevant content."
)
USER_PROMPT = (
    "Look at this image from a Telegram tech channel post.\n"
    "If it contains technically useful information (code, architecture diagram, chart, "
    "benchmark results, UI screenshot, technical diagram), describe what it shows in 1-2 sentences in Russian.\n"
    "If it is decorative, a meme without technical content, a logo, or a generic photo, "
    "respond with exactly: SKIP"
)
SKIP_MARKER = "SKIP"
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB — Anthropic limit


def analyze_photo(image_bytes: bytes, mime_type: str = "image/jpeg") -> str | None:
    """Return a Russian description of the image, or None if not technically relevant."""
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        return None

    suffix = ".jpg"
    if mime_type == "image/png":
        suffix = ".png"
    elif mime_type == "image/webp":
        suffix = ".webp"

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            tmp_file.write(image_bytes)
            tmp_path = tmp_file.name
        text = LLMClient.complete_vision(
            prompt=f"{SYSTEM_PROMPT}\n\n{USER_PROMPT}",
            image_path=tmp_path,
        ).strip()
    except Exception:
        LOGGER.warning("Vision API call failed", exc_info=True)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not text or text.upper().startswith(SKIP_MARKER):
        return None
    return text
