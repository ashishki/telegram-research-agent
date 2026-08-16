"""Compatibility facade for Telegram command handlers.

The active PRM runtime imports `bot.prm_handlers` directly. Historical callers
continue to resolve old names lazily from `bot.legacy_handlers`.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from config.settings import Settings
from .prm_handlers import PRM_SAFE_COMMANDS, dispatch_prm_command, send_message
from .runtime import BOT_RUNTIME_LEGACY, BOT_RUNTIME_MODES, BOT_RUNTIME_PRM_ASSISTANT, normalize_bot_runtime_mode


def dispatch_command(chat_id: str, text: str, settings: Settings, *, runtime_mode: str = BOT_RUNTIME_LEGACY) -> None:
    mode = normalize_bot_runtime_mode(runtime_mode)
    if mode == BOT_RUNTIME_PRM_ASSISTANT:
        dispatch_prm_command(chat_id, text, settings)
        return
    _legacy().dispatch_command(chat_id=chat_id, text=text, settings=settings, runtime_mode=BOT_RUNTIME_LEGACY)


def __getattr__(name: str) -> Any:
    module = _legacy()
    try:
        return getattr(module, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_legacy())))


def _legacy():
    return import_module("bot.legacy_handlers")


__all__ = [
    "BOT_RUNTIME_LEGACY",
    "BOT_RUNTIME_MODES",
    "BOT_RUNTIME_PRM_ASSISTANT",
    "PRM_SAFE_COMMANDS",
    "dispatch_command",
    "dispatch_prm_command",
    "normalize_bot_runtime_mode",
    "send_message",
]
