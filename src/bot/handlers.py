"""Compatibility facade for Telegram command handlers.

The active PRM runtime imports `bot.prm_handlers` directly. Historical callers
continue to resolve old names lazily from `bot.legacy_handlers`.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from config.settings import Settings
from prm.contracts import ArchiveSynthesisAccess, ModelEgressAccess
from .prm_handlers import PRM_SAFE_COMMANDS, dispatch_prm_command, send_message
from .runtime import BOT_RUNTIME_LEGACY, BOT_RUNTIME_MODES, BOT_RUNTIME_PRM_ASSISTANT, normalize_bot_runtime_mode


def dispatch_command(
    chat_id: str, text: str, settings: Settings, *, runtime_mode: str = BOT_RUNTIME_PRM_ASSISTANT,
    actor_id: str | None = None, owner_chat_id: str | None = None,
    model_access: ModelEgressAccess | None = None,
    archive_synthesis_access: ArchiveSynthesisAccess | None = None,
) -> None:
    """Compatibility dispatcher; the default is the gated PRM assistant.

    Passing ``runtime_mode="legacy"`` is still honored explicitly, but omitting
    the mode can no longer reach the ungated legacy sender by default.
    """
    mode = normalize_bot_runtime_mode(runtime_mode)
    if mode == BOT_RUNTIME_PRM_ASSISTANT:
        kwargs: dict[str, object] = {"actor_id": actor_id, "owner_chat_id": owner_chat_id}
        if model_access is not None:
            kwargs["model_access"] = model_access
        if archive_synthesis_access is not None:
            kwargs["archive_synthesis_access"] = archive_synthesis_access
        dispatch_prm_command(chat_id, text, settings, **kwargs)
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
