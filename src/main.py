import argparse
import asyncio
import logging

from config.settings import load_settings
from db.migrate import run_migrations
from ingestion.bootstrap_ingest import run_bootstrap


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram Research Agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.set_defaults(handler=handle_bootstrap)

    for command in ("ingest", "digest"):
        subparser = subparsers.add_parser(command)
        subparser.set_defaults(handler=handle_placeholder)

    return parser


def handle_placeholder(_: argparse.Namespace) -> int:
    LOGGER.info("Not yet implemented")
    return 0


def handle_bootstrap(_: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        run_migrations()
        summary = asyncio.run(run_bootstrap(settings))
    except Exception:
        LOGGER.exception("Bootstrap failed")
        return 1
    LOGGER.info(
        "Bootstrap complete inserted=%d skipped=%d errors=%d",
        summary["inserted"],
        summary["skipped"],
        summary["errors"],
    )
    return 0 if summary["errors"] == 0 else 1


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = build_parser()
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
