#!/usr/bin/env python3
"""Route PA design reviews to OpenCode Go; verify historical pinned receipts."""
import sys
from playbook import main as pinned_main


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if "--provider" in args:
        index = args.index("--provider")
        if index + 1 >= len(args) or args[index + 1] != "opencode-go":
            print("Unsupported explicit reviewer provider", file=sys.stderr)
            return 2
        del args[index:index + 2]
        from opencode_role_review import main as opencode_main
        return opencode_main(args)
    if not args or args[0] not in {'verify','--help','-h'} or 'run' in args:
        print('Current PA reviewer policy requires --provider opencode-go; no Codex fallback.', file=sys.stderr)
        return 2
    return pinned_main(['run_codex_role', *args])

if __name__ == '__main__':
    raise SystemExit(main())
