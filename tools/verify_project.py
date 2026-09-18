#!/usr/bin/env python3
"""Canonical project-verifier name backed by the exact pinned Playbook.

The delivery contract intentionally retains tools/verify_project.py because
upstream validates that public interface. CLI calls use the guarded bridge;
imported helper APIs resolve to the same pinned implementation, never the old
compatibility snapshot. No model, account or application process is enabled.
"""
from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path

from playbook import ROOT, main as bridge_main, verified_upstream


@lru_cache(maxsize=1)
def _implementation():
    upstream = verified_upstream(ROOT)
    sys.path.insert(0, str(upstream / 'tools'))
    name = '_verified_upstream_project_verifier'
    spec = importlib.util.spec_from_file_location(name, upstream / 'tools/verify_project.py')
    if spec is None or spec.loader is None:
        raise RuntimeError('Pinned project verifier cannot be loaded')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def __getattr__(name: str):
    if name.startswith('__'):
        raise AttributeError(name)
    return getattr(_implementation(), name)


def main(argv: list[str] | None = None) -> int:
    return bridge_main(['verify_project', *(sys.argv[1:] if argv is None else argv)])


if __name__ == '__main__':
    raise SystemExit(main())
