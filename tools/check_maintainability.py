#!/usr/bin/env python3
"""Forward maintainability signals to the verified pinned development kit."""
import sys
from playbook import main

if __name__ == '__main__':
    raise SystemExit(main(['check_maintainability', *sys.argv[1:]]))
