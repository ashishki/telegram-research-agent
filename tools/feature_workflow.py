#!/usr/bin/env python3
"""Forward the feature workflow to the verified pinned development kit."""
import sys
from playbook import main

if __name__ == '__main__':
    raise SystemExit(main(['feature_workflow', *sys.argv[1:]]))
