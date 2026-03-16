import json
import logging
import os
import time
from typing import Any

from anthropic import APIConnectionError, APIStatusError, APITimeoutError, Anthropic, RateLimitError


LOGGER = logging.getLogger(__name__)
DEFAULT_MODEL_PROVIDER = "claude-haiku-4-5"
MAX_RETRIES = 3


class LLMError(Exception):
    pass


class LLMSchemaError(LLMError):
    pass


def _get_client() -> Anthropic:
    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        raise LLMError("LLM_API_KEY is not set")
    return Anthropic(api_key=api_key)


def _get_model() -> str:
    return os.environ.get("MODEL_PROVIDER", DEFAULT_MODEL_PROVIDER)


def _should_retry(exc: Exception) -> bool:
    if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError)):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500


def _extract_text(response: Any) -> str:
    blocks = getattr(response, "content", [])
    text_parts = [block.text for block in blocks if getattr(block, "type", None) == "text"]
    return "".join(text_parts).strip()


def complete(prompt: str, system: str = "", max_tokens: int = 2048) -> str:
    client = _get_client()
    model = _get_model()
    attempt = 0

    while True:
        attempt += 1
        try:
            LOGGER.debug(
                "Anthropic completion request model=%s prompt_length=%s max_tokens=%s attempt=%s",
                model,
                len(prompt),
                max_tokens,
                attempt,
            )
            response = client.messages.create(
                model=model,
                system=system,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            text = _extract_text(response)
            LOGGER.debug(
                "Anthropic completion response model=%s response_length=%s",
                model,
                len(text),
            )
            return text
        except Exception as exc:
            if attempt >= MAX_RETRIES or not _should_retry(exc):
                LOGGER.exception("Anthropic completion failed after %s attempt(s)", attempt)
                raise LLMError("Anthropic completion failed") from exc

            delay = 2 ** (attempt - 1)
            remaining_attempts = MAX_RETRIES - attempt
            LOGGER.warning(
                "Anthropic completion retrying in %s second(s) after %s remaining_attempts=%s",
                delay,
                exc.__class__.__name__,
                remaining_attempts,
            )
            time.sleep(delay)


def _strip_code_fence(text: str) -> str:
    """Strip markdown code fences that models sometimes add around JSON."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]  # remove ```json or ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def complete_json(prompt: str, system: str = "") -> dict[str, Any] | list[Any]:
    response_text = _strip_code_fence(complete(prompt=prompt, system=system, max_tokens=2048))
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as exc:
        LOGGER.exception("Anthropic JSON response parsing failed")
        raise LLMSchemaError("Anthropic response was not valid JSON") from exc

    if not isinstance(data, (dict, list)):
        raise LLMSchemaError("Anthropic response JSON must decode to an object or array")
    return data


class LLMClient:
    @staticmethod
    def complete(prompt: str, system: str = "", max_tokens: int = 2048) -> str:
        return complete(prompt=prompt, system=system, max_tokens=max_tokens)

    @staticmethod
    def complete_json(prompt: str, system: str = "") -> dict[str, Any] | list[Any]:
        return complete_json(prompt=prompt, system=system)
