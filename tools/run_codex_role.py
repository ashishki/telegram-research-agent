#!/usr/bin/env python3
"""Forward role execution to the verified pinned development kit."""
import sys
from playbook import main

if __name__ == '__main__':
    raise SystemExit(main(['run_codex_role', *sys.argv[1:]]))
