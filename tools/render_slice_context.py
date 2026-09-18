#!/usr/bin/env python3
"""Forward bounded slice context rendering to the verified pinned kit."""
import sys
from playbook import main

if __name__ == '__main__':
    raise SystemExit(main(['render_slice_context', *sys.argv[1:]]))
