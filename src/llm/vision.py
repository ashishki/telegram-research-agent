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
    """Fail closed until PA-15 provides an ingress-verified image binding.

    The prior path wrote arbitrary image bytes to ``delete=False`` storage and
    passed a caller-selected path to the model adapter. PA-02 cannot prove that
    a vision grant names those exact bytes, so it makes neither local nor
    provider side effects. PA-15 owns verified attachment lifecycle work.
    """

    del image_bytes, mime_type
    return None
