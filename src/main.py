import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone

from config.settings import PROJECT_ROOT, load_settings
from db.migrate import run_migrations
from ingestion.bootstrap_ingest import run_bootstrap
from ingestion.incremental_ingest import run_incremental
from bot.bot import run_bot
from llm.client import set_usage_db_path
from output.generate_digest import run_digest
from output.generate_insight import OUTPUT_DIR as INSIGHT_OUTPUT_DIR
from output.generate_insight import generate_insight
from output.map_project_insights import run_project_mapping
from output.generate_recommendations import run_recommendations
from output.generate_study_plan import OUTPUT_DIR as STUDY_PLAN_OUTPUT_DIR
from output.generate_study_plan import generate_study_plan, send_study_reminder
from processing.cleanup import run_cleanup
from processing.cluster import cluster_posts
from processing.detect_topics import run_topic_detection
from processing.normalize_posts import run_normalization


LOGGER = logging.getLogger(__name__)


def _handle_sigterm(_: int, __) -> None:
    LOGGER.info("SIGTERM received, shutting down")
    sys.exit(0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram Research Agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.set_defaults(handler=handle_bootstrap)

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.set_defaults(handler=handle_ingest)

    digest_parser = subparsers.add_parser("digest")
    digest_parser.set_defaults(handler=handle_digest)

    study_parser = subparsers.add_parser("study", help="Generate or send the weekly study plan")
    study_parser.add_argument("--remind", action="store_true")
    study_parser.add_argument("--friday", action="store_true")
    study_parser.set_defaults(handler=handle_study)

    insight_parser = subparsers.add_parser(
        "insight",
        help="Generate retroactive project insights from Telegram history",
    )
    insight_parser.add_argument("--since-bootstrap", action="store_true")
    insight_parser.add_argument("--weeks", type=int, default=4)
    insight_parser.set_defaults(handler=handle_insight)

    normalize_parser = subparsers.add_parser("normalize")
    normalize_parser.set_defaults(handler=handle_normalize)

    cleanup_parser = subparsers.add_parser("cleanup", help="Strip raw_json and delete posts older than 100 days")
    cleanup_parser.set_defaults(handler=handle_cleanup)

    bot_parser = subparsers.add_parser("bot", help="Start Telegram bot interface (long-polling)")
    bot_parser.set_defaults(handler=handle_bot)

    return parser


def handle_ingest(_: argparse.Namespace) -> int:
    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        LOGGER.info("Starting step=incremental_ingest")
        incremental_summary = asyncio.run(run_incremental(settings))
        LOGGER.info(
            "Finished step=incremental_ingest inserted=%d skipped=%d errors=%d",
            incremental_summary["inserted"],
            incremental_summary["skipped"],
            incremental_summary["errors"],
        )

        LOGGER.info("Starting step=normalize_posts")
        normalization_summary = run_normalization(settings)
        LOGGER.info(
            "Finished step=normalize_posts processed=%d skipped=%d errors=%d",
            normalization_summary["processed"],
            normalization_summary["skipped"],
            normalization_summary["errors"],
        )

        LOGGER.info("Starting step=cluster")
        clusters = cluster_posts(settings)
        LOGGER.info("Finished step=cluster clusters=%d", len(clusters))

        LOGGER.info("Starting step=detect_topics")
        topic_summary = run_topic_detection(settings, clusters=clusters)
        LOGGER.info(
            "Finished step=detect_topics new_topics=%d merged=%d skipped=%d",
            topic_summary["new_topics"],
            topic_summary["merged"],
            topic_summary["skipped"],
        )
    except Exception:
        LOGGER.exception("Ingest pipeline failed")
        return 1

    if incremental_summary["errors"] or normalization_summary["errors"]:
        return 1
    return 0


def handle_bootstrap(_: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        LOGGER.info("Starting step=bootstrap_ingest")
        bootstrap_summary = asyncio.run(run_bootstrap(settings))
        LOGGER.info(
            "Finished step=bootstrap_ingest inserted=%d skipped=%d errors=%d",
            bootstrap_summary["inserted"],
            bootstrap_summary["skipped"],
            bootstrap_summary["errors"],
        )

        LOGGER.info("Starting step=normalize_posts")
        normalization_summary = run_normalization(settings)
        LOGGER.info(
            "Finished step=normalize_posts processed=%d skipped=%d errors=%d",
            normalization_summary["processed"],
            normalization_summary["skipped"],
            normalization_summary["errors"],
        )
    except Exception:
        LOGGER.exception("Bootstrap failed")
        return 1
    return 0 if bootstrap_summary["errors"] == 0 and normalization_summary["errors"] == 0 else 1


def handle_normalize(_: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        LOGGER.info("Starting step=normalize_posts")
        summary = run_normalization(settings)
        LOGGER.info(
            "Finished step=normalize_posts processed=%d skipped=%d errors=%d",
            summary["processed"],
            summary["skipped"],
            summary["errors"],
        )
    except Exception:
        LOGGER.exception("Normalization failed")
        return 1
    return 0 if summary["errors"] == 0 else 1


def handle_digest(_: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        LOGGER.info("Starting step=generate_digest")
        summary = run_digest(settings)
        LOGGER.info(
            "Finished step=generate_digest week=%s posts=%d output=%s json=%s",
            summary.week_label,
            summary.post_count,
            summary.output_path,
            summary.json_path or "",
        )
    except Exception:
        LOGGER.exception("Digest generation failed")
        return 1

    try:
        LOGGER.info("Starting step=generate_recommendations")
        recommendation_summary = run_recommendations(settings)
        if recommendation_summary["output_path"] is None:
            LOGGER.warning("Recommendations skipped week=%s", recommendation_summary["week_label"])
        else:
            LOGGER.info(
                "Finished step=generate_recommendations week=%s output=%s",
                recommendation_summary["week_label"],
                recommendation_summary["output_path"],
            )
    except Exception:
        LOGGER.exception("Recommendations generation failed but digest succeeded")

    try:
        LOGGER.info("Starting step=generate_study_plan")
        generate_study_plan(settings)
        LOGGER.info("Finished step=generate_study_plan output_dir=%s", STUDY_PLAN_OUTPUT_DIR)
    except Exception:
        LOGGER.exception("Study plan generation failed but digest succeeded")

    try:
        LOGGER.info("Starting step=map_project_insights")
        project_mapping_summary = run_project_mapping(settings)
        LOGGER.info(
            "Finished step=map_project_insights projects_processed=%d links_created=%d",
            project_mapping_summary["projects_processed"],
            project_mapping_summary["links_created"],
        )
    except Exception:
        LOGGER.exception("Project mapping failed but digest succeeded")

    try:
        LOGGER.info("Starting step=cleanup")
        cleanup_summary = run_cleanup(settings.db_path)
        LOGGER.info(
            "Finished step=cleanup raw_json_nulled=%d posts_deleted=%d vacuum=%s",
            cleanup_summary["raw_json_nulled"],
            cleanup_summary["posts_deleted"],
            cleanup_summary["vacuum"],
        )
    except Exception:
        LOGGER.exception("Cleanup failed but digest succeeded")

    return 0


def handle_cleanup(_: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        LOGGER.info("Starting step=cleanup")
        summary = run_cleanup(settings.db_path)
        LOGGER.info(
            "Finished step=cleanup raw_json_nulled=%d posts_deleted=%d vacuum=%s",
            summary["raw_json_nulled"],
            summary["posts_deleted"],
            summary["vacuum"],
        )
    except Exception:
        LOGGER.exception("Cleanup failed")
        return 1
    return 0


def handle_bot(_: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")
        LOGGER.info("Starting step=run_bot")
        run_bot(settings)
        LOGGER.info("Finished step=run_bot")
    except Exception:
        LOGGER.exception("Bot runtime failed")
        return 1
    return 0


def handle_study(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")
        if args.remind:
            LOGGER.info("Starting step=send_study_reminder is_friday=%s", getattr(args, "friday", False))
            send_study_reminder(settings, is_friday=getattr(args, "friday", False))
            LOGGER.info("Finished step=send_study_reminder")
            return 0

        LOGGER.info("Starting step=generate_study_plan")
        generate_study_plan(settings)
        output_path = STUDY_PLAN_OUTPUT_DIR / f"{_current_week_label()}.md"
        LOGGER.info("Finished step=generate_study_plan output=%s", output_path)
        sys.stdout.write(f"{output_path}\n")
    except Exception:
        LOGGER.exception("Study plan command failed")
        return 1
    return 0


def _current_week_label() -> str:
    year, week, _ = datetime.now(timezone.utc).isocalendar()
    return f"{year}-W{week:02d}"


def handle_insight(args: argparse.Namespace) -> int:
    settings = load_settings()
    lookback_days = 90 if args.since_bootstrap else max(1, args.weeks) * 7

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        LOGGER.info("Starting step=generate_insight lookback_days=%d", lookback_days)
        output_md = generate_insight(settings.db_path, lookback_days=lookback_days)
        output_path = INSIGHT_OUTPUT_DIR / f"{_current_week_label()}.md"
        if output_md:
            LOGGER.info("Finished step=generate_insight output=%s", output_path)
            sys.stdout.write(f"{output_path}\n")
        else:
            LOGGER.info("Insight generation produced no output")
    except Exception:
        LOGGER.exception("Insight generation failed")
        return 1

    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    signal.signal(signal.SIGTERM, _handle_sigterm)
    parser = build_parser()
    try:
        settings = load_settings()
        set_usage_db_path(settings.db_path)
        LOGGER.info(
            "Startup python_version=%s project_root=%s db_path=%s model_provider=%s",
            sys.version.split()[0],
            PROJECT_ROOT,
            settings.db_path,
            settings.model_provider,
        )
        args = parser.parse_args()
        return args.handler(args)
    except KeyboardInterrupt:
        LOGGER.info("Interrupted")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
