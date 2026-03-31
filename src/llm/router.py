import logging

from config.settings import CHEAP_MODEL, MID_MODEL, STRONG_MODEL


LOGGER = logging.getLogger(__name__)
WATCH_THRESHOLD = 0.45
STRONG_THRESHOLD = 0.75
MODEL_RATES_USD_PER_MILLION: dict[str, dict[str, float]] = {
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
}
DEFAULT_MODEL_RATES = MODEL_RATES_USD_PER_MILLION["claude-haiku-4-5-20251001"]


def route(task_type: str, signal_score: float | None = None) -> str:
    normalized_task = (task_type or "").strip().lower()
    if normalized_task == "synthesis":
        return STRONG_MODEL

    if signal_score is None:
        LOGGER.warning("route() received signal_score=None for task_type=%s; using cheap model", normalized_task)
        return CHEAP_MODEL

    score = float(signal_score)
    if score >= STRONG_THRESHOLD:
        return STRONG_MODEL
    if score >= WATCH_THRESHOLD:
        return MID_MODEL
    return CHEAP_MODEL


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = MODEL_RATES_USD_PER_MILLION.get(model, DEFAULT_MODEL_RATES)
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
