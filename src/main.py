import argparse
import asyncio
import logging

from config.settings import load_settings
from db.migrate import run_migrations
from ingestion.bootstrap_ingest import run_bootstrap
from processing.normalize_posts import run_normalization


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram Research Agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.set_defaults(handler=handle_bootstrap)

    for command in ("ingest", "digest"):
        subparser = subparsers.add_parser(command)
        subparser.set_defaults(handler=handle_placeholder)

    normalize_parser = subparsers.add_parser("normalize")
    normalize_parser.set_defaults(handler=handle_normalize)

    return parser


def handle_placeholder(_: argparse.Namespace) -> int:
    LOGGER.info("Not yet implemented")
    return 0


def handle_bootstrap(_: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        run_migrations()
        bootstrap_summary = asyncio.run(run_bootstrap(settings))
        normalization_summary = run_normalization(settings)
    except Exception:
        LOGGER.exception("Bootstrap failed")
        return 1
    LOGGER.info(
        "Bootstrap complete inserted=%d skipped=%d errors=%d",
        bootstrap_summary["inserted"],
        bootstrap_summary["skipped"],
        bootstrap_summary["errors"],
    )
    LOGGER.info(
        "Normalization complete processed=%d skipped=%d errors=%d",
        normalization_summary["processed"],
        normalization_summary["skipped"],
        normalization_summary["errors"],
    )
    return 0 if bootstrap_summary["errors"] == 0 and normalization_summary["errors"] == 0 else 1


def handle_normalize(_: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        run_migrations()
        summary = run_normalization(settings)
    except Exception:
        LOGGER.exception("Normalization failed")
        return 1
    LOGGER.info(
        "Normalization complete processed=%d skipped=%d errors=%d",
        summary["processed"],
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
