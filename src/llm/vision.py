import base64
import logging

from llm.client import _get_client, _get_model, _record_usage


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

    import time
    client = _get_client()
    model = _get_model(CATEGORY)
    start = time.time()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=150,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": base64.standard_b64encode(image_bytes).decode("utf-8"),
                            },
                        },
                        {"type": "text", "text": USER_PROMPT},
                    ],
                }
            ],
        )
    except Exception:
        LOGGER.warning("Vision API call failed", exc_info=True)
        return None

    duration_ms = int((time.time() - start) * 1000)
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", 0)
    output_tokens = getattr(usage, "output_tokens", 0)
    _record_usage(CATEGORY, model, input_tokens, output_tokens, duration_ms)

    blocks = getattr(response, "content", [])
    text = "".join(b.text for b in blocks if getattr(b, "type", None) == "text").strip()

    if not text or text.upper().startswith(SKIP_MARKER):
        return None
    return text
