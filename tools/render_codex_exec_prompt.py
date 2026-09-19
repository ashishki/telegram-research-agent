#!/usr/bin/env python3
"""Proxy the exact pinned renderer for CLI use and in-process marker parsing."""

from importlib.util import module_from_spec, spec_from_file_location
import sys

from playbook import ROOT, main as run_pinned_tool, verified_upstream


def _load_pinned_renderer():
    upstream = verified_upstream(ROOT)
    renderer_path = upstream / "tools" / "render_codex_exec_prompt.py"
    if renderer_path.is_symlink() or not renderer_path.is_file():
        raise RuntimeError("Pinned prompt renderer is missing or a symlink")
    spec = spec_from_file_location("_pinned_render_codex_exec_prompt", renderer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Pinned prompt renderer cannot be loaded")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PINNED_RENDERER = _load_pinned_renderer()


def __getattr__(name):
    return getattr(_PINNED_RENDERER, name)


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    return run_pinned_tool(["render_codex_exec_prompt", *arguments])


if __name__ == "__main__":
    raise SystemExit(main())
