#!/usr/bin/env python3
"""Forward prompt rendering to the verified pinned development kit."""

import sys

from playbook import main


if __name__ == "__main__":
    raise SystemExit(main(["render_codex_exec_prompt", *sys.argv[1:]]))
