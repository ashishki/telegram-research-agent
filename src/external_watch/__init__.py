"""Source-bounded UTD shadow watch package.

The package initializer stays lazy: importing a submodule such as
``external_watch.delivery`` must not import-load the full collector engine.
``ShadowCollector``/``ShadowRunResult`` resolve from ``.collector`` on first
use via :pep:`562` ``__getattr__``.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "ShadowCollector": "external_watch.collector",
    "ShadowRunResult": "external_watch.collector",
}

__all__ = sorted(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(module_name), name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
