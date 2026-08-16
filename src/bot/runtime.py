"""Telegram runtime modes independent from command implementations."""

BOT_RUNTIME_LEGACY = "legacy"
BOT_RUNTIME_PRM_ASSISTANT = "prm_assistant"
BOT_RUNTIME_MODES = frozenset({BOT_RUNTIME_LEGACY, BOT_RUNTIME_PRM_ASSISTANT})


def normalize_bot_runtime_mode(value: str) -> str:
    clean = str(value or "").strip().casefold().replace("-", "_")
    aliases = {
        "prm": BOT_RUNTIME_PRM_ASSISTANT,
        "assistant": BOT_RUNTIME_PRM_ASSISTANT,
        "prm_assistant": BOT_RUNTIME_PRM_ASSISTANT,
        "legacy": BOT_RUNTIME_LEGACY,
    }
    result = aliases.get(clean, clean)
    if result not in BOT_RUNTIME_MODES:
        raise ValueError(f"unsupported bot runtime mode: {value}")
    return result
