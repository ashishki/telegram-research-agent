import json
import logging
import mimetypes
import os
import sqlite3
import time
from typing import Any

from anthropic import APIConnectionError, APIStatusError, APITimeoutError, Anthropic, RateLimitError

from llm.router import estimate_cost_usd

LOGGER = logging.getLogger(__name__)
DEFAULT_MODEL_PROVIDER = "claude-haiku-4-5"
MAX_RETRIES = 3

# Model routing by task category.
# Override any entry via env var: LLM_MODEL_DIGEST, LLM_MODEL_BOT_ASK, etc.
CATEGORY_MODEL_MAP: dict[str, str] = {
    # Deep synthesis — quality over cost
    "digest":            "claude-sonnet-4-6",
    "recommendations":   "claude-sonnet-4-6",
    "study_plan":        "claude-sonnet-4-6",
    "insight":           "claude-sonnet-4-6",
    "bot_ask":           "claude-sonnet-4-6",
    "preference_judge":  "claude-sonnet-4-6",
    # Fast + cheap — called many times per run
    "project_insights":  "claude-haiku-4-5",
    "topic_detection":   "claude-haiku-4-5",
    "photo_analysis":    "claude-haiku-4-5",
    "unknown":           "claude-haiku-4-5",
    "test":              "claude-haiku-4-5",
}
_usage_db_path: str = ""


class LLMError(Exception):
    pass


class LLMSchemaError(LLMError):
    pass


def set_usage_db_path(path: str) -> None:
    global _usage_db_path
    _usage_db_path = path


def _resolve_usage_db_path() -> str:
    return _usage_db_path or os.environ.get("AGENT_DB_PATH", "").strip()


def _record_usage(task_type: str, model: str, input_tokens: int, output_tokens: int, duration_ms: int) -> None:
    db_path = _resolve_usage_db_path()
    if not db_path:
        return

    cost = estimate_cost_usd(model=model, input_tokens=input_tokens, output_tokens=output_tokens)
    try:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                (
                    "INSERT INTO llm_usage "
                    "("
                    "called_at, model, task_type, input_tokens, output_tokens, est_cost_usd, "
                    "category, cost_usd, duration_ms"
                    ") VALUES (?,?,?,?,?,?,?,?,?)"
                ),
                (
                    now,
                    model,
                    task_type,
                    input_tokens,
                    output_tokens,
                    round(cost, 8),
                    task_type,
                    round(cost, 8),
                    duration_ms,
                ),
            )
    except Exception:
        LOGGER.warning("Failed to record LLM usage", exc_info=True)


def _get_client() -> Anthropic:
    api_key = os.environ.get("LLM_API_KEY", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise LLMError("LLM_API_KEY or ANTHROPIC_API_KEY is not set")
    return Anthropic(api_key=api_key)


def _get_model(category: str = "unknown") -> str:
    # Per-category env override: LLM_MODEL_DIGEST, LLM_MODEL_TOPIC_DETECTION, etc.
    env_key = f"LLM_MODEL_{category.upper()}"
    if os.environ.get(env_key):
        return os.environ[env_key]
    # Category routing table
    if category in CATEGORY_MODEL_MAP:
        return CATEGORY_MODEL_MAP[category]
    # Global fallback
    return os.environ.get("MODEL_PROVIDER", DEFAULT_MODEL_PROVIDER)


def _should_retry(exc: Exception) -> bool:
    if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError)):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500


def _extract_text(response: Any) -> str:
    blocks = getattr(response, "content", [])
    text_parts = [block.text for block in blocks if getattr(block, "type", None) == "text"]
    return "".join(text_parts).strip()


def complete(
    prompt: str,
    system: str = "",
    max_tokens: int = 2048,
    category: str = "unknown",
    model: str | None = None,
) -> str:
    client = _get_client()
    selected_model = model or _get_model(category)
    attempt = 0

    while True:
        attempt += 1
        start_time = time.time()
        try:
            LOGGER.debug(
                "Anthropic completion request model=%s prompt_length=%s max_tokens=%s attempt=%s",
                selected_model,
                len(prompt),
                max_tokens,
                attempt,
            )
            response = client.messages.create(
                model=selected_model,
                system=system,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            text = _extract_text(response)
            duration_ms = int((time.time() - start_time) * 1000)
            input_tokens = getattr(getattr(response, "usage", None), "input_tokens", 0)
            output_tokens = getattr(getattr(response, "usage", None), "output_tokens", 0)
            est_cost_usd = estimate_cost_usd(
                model=selected_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            _record_usage(category, selected_model, input_tokens, output_tokens, duration_ms)
            LOGGER.debug(
                "model=%s input_tokens=%s output_tokens=%s est_cost_usd=%.8f",
                selected_model,
                input_tokens,
                output_tokens,
                est_cost_usd,
            )
            LOGGER.debug(
                "Anthropic completion response model=%s response_length=%s",
                selected_model,
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


def complete_vision(prompt: str, image_path: str, model: str | None = None) -> str:
    client = _get_client()
    selected_model = model or _get_model("photo_analysis")
    attempt = 0
    media_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"

    with open(image_path, "rb") as image_file:
        image_payload = image_file.read()

    while True:
        attempt += 1
        start_time = time.time()
        try:
            LOGGER.debug(
                "Anthropic vision request model=%s image_path=%s attempt=%s",
                selected_model,
                image_path,
                attempt,
            )
            response = client.messages.create(
                model=selected_model,
                max_tokens=150,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": __import__("base64").standard_b64encode(image_payload).decode("utf-8"),
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            text = _extract_text(response)
            duration_ms = int((time.time() - start_time) * 1000)
            input_tokens = getattr(getattr(response, "usage", None), "input_tokens", 0)
            output_tokens = getattr(getattr(response, "usage", None), "output_tokens", 0)
            est_cost_usd = estimate_cost_usd(
                model=selected_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            _record_usage("photo_analysis", selected_model, input_tokens, output_tokens, duration_ms)
            LOGGER.debug(
                "vision model=%s input_tokens=%s output_tokens=%s est_cost_usd=%.8f",
                selected_model,
                input_tokens,
                output_tokens,
                est_cost_usd,
            )
            return text
        except Exception as exc:
            if attempt >= MAX_RETRIES or not _should_retry(exc):
                LOGGER.exception("Anthropic vision completion failed after %s attempt(s)", attempt)
                raise LLMError("Anthropic vision completion failed") from exc

            delay = 2 ** (attempt - 1)
            remaining_attempts = MAX_RETRIES - attempt
            LOGGER.warning(
                "Anthropic vision completion retrying in %s second(s) after %s remaining_attempts=%s",
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


def complete_json(
    prompt: str,
    system: str = "",
    category: str = "unknown",
    model: str | None = None,
) -> dict[str, Any] | list[Any]:
    response_text = _strip_code_fence(
        complete(prompt=prompt, system=system, max_tokens=2048, category=category, model=model)
    )
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
    def complete(
        prompt: str,
        system: str = "",
        max_tokens: int = 2048,
        category: str = "unknown",
        model: str | None = None,
    ) -> str:
        return complete(prompt=prompt, system=system, max_tokens=max_tokens, category=category, model=model)

    @staticmethod
    def complete_json(
        prompt: str,
        system: str = "",
        category: str = "unknown",
        model: str | None = None,
    ) -> dict[str, Any] | list[Any]:
        return complete_json(prompt=prompt, system=system, category=category, model=model)

    @staticmethod
    def complete_vision(prompt: str, image_path: str, model: str | None = None) -> str:
        return complete_vision(prompt=prompt, image_path=image_path, model=model)
