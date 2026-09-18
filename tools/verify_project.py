#!/usr/bin/env python3
"""Canonical verifier interface backed by the pinned initializer's template.

The upstream initializer carries verify_project_script() as a literal template,
not tools/verify_project.py. Extract that exact literal without running the
initializer or overwriting any downstream file.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from playbook import ROOT, load_generated_verifier, main as bridge_main, verified_upstream


@lru_cache(maxsize=1)
def _implementation():
    return load_generated_verifier(verified_upstream(ROOT))


def __getattr__(name: str):
    if name.startswith('__'):
        raise AttributeError(name)
    return getattr(_implementation(), name)


def main(argv: list[str] | None = None) -> int:
    return bridge_main(['verify_project', *(sys.argv[1:] if argv is None else argv)])


if __name__ == '__main__':
    raise SystemExit(main())
