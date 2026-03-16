import argparse
import logging

from config.settings import load_settings


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram Research Agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("bootstrap", "ingest", "digest"):
        subparser = subparsers.add_parser(command)
        subparser.set_defaults(handler=handle_placeholder)

    return parser


def handle_placeholder(_: argparse.Namespace) -> int:
    LOGGER.info("Not yet implemented")
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_settings()
    parser = build_parser()
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
