"""Lazy package facade.

Importing any ``assistant.*`` submodule executes this package initializer. It
deliberately does *not* eagerly import ``pi_facade``/``pi_tools`` (and the
report-era ``output.*`` modules they pull in). Names are resolved on first use
via :pep:`562` module ``__getattr__`` so the active PA path does not
import-load the report-era tree.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "PersonalIntelligenceFacade": "assistant.pi_facade",
    "PITool": "assistant.pi_tools",
    "build_pi_tool_catalog": "assistant.pi_tools",
    "call_pi_tool": "assistant.pi_tools",
    "list_pi_tools": "assistant.pi_tools",
}

__all__ = sorted(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(module_name), name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
