import argparse
import asyncio
import logging
import os
import signal
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.settings import PROJECT_ROOT, load_settings
from db.migrate import run_migrations
from output.signal_report import PROFILE_YAML_PATH as _PROFILE_YAML_PATH
from ingestion.bootstrap_ingest import run_bootstrap
from ingestion.incremental_ingest import run_incremental
from bot.bot import run_bot
from llm.client import set_usage_db_path
from output.generate_digest import run_digest
from output.generate_insight import OUTPUT_DIR as INSIGHT_OUTPUT_DIR
from output.generate_insight import generate_insight
from output.map_project_insights import run_project_mapping
from output.signal_report import format_signal_report
from output.generate_study_plan import OUTPUT_DIR as STUDY_PLAN_OUTPUT_DIR
from output.generate_study_plan import generate_study_plan, send_study_reminder
from processing.cleanup import run_cleanup
from processing.cluster import cluster_posts
from processing.detect_topics import run_topic_detection
from processing.normalize_posts import run_normalization
from processing.score_posts import score_posts


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
    ingest_parser.add_argument("--skip-reactions", action="store_true", help="Skip Telegram reaction feedback sync")
    ingest_parser.set_defaults(handler=handle_ingest)

    reaction_parser = subparsers.add_parser(
        "sync-reactions",
        help="Sync your Telegram post reactions into feedback and manual tags",
    )
    reaction_parser.add_argument("--days", type=int, default=14, help="Lookback window in days (default: 14)")
    reaction_parser.add_argument("--limit", type=int, default=300, help="Maximum posts to inspect (default: 300)")
    reaction_parser.set_defaults(handler=handle_sync_reactions)

    digest_parser = subparsers.add_parser("digest")
    digest_parser.add_argument("--force", action="store_true")
    digest_parser.set_defaults(handler=handle_digest)

    study_parser = subparsers.add_parser("study", help="Generate or send the weekly study plan")
    study_parser.add_argument("--remind", action="store_true")
    study_parser.add_argument("--force", action="store_true")
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

    score_parser = subparsers.add_parser("score", help="Score posts by personal relevance (signal_score + bucket)")
    score_parser.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    score_parser.set_defaults(handler=handle_score)

    score_stats_parser = subparsers.add_parser("score-stats", help="Print scoring bucket counts and topic stats")
    score_stats_parser.set_defaults(handler=handle_score_stats)

    cost_stats_parser = subparsers.add_parser("cost-stats", help="Print aggregate LLM cost statistics")
    cost_stats_parser.set_defaults(handler=handle_cost_stats)

    health_check_parser = subparsers.add_parser("health-check", help="Print DB and config health information")
    health_check_parser.set_defaults(handler=handle_health_check)

    report_preview_parser = subparsers.add_parser(
        "report-preview",
        help="Render the current signal-first report preview from scored posts",
    )
    report_preview_parser.set_defaults(handler=handle_report_preview)

    bot_parser = subparsers.add_parser("bot", help="Start Telegram bot interface (long-polling)")
    bot_parser.set_defaults(handler=handle_bot)

    tune_parser = subparsers.add_parser(
        "tune-suggestions",
        help="Show boost topic suggestions based on acted-on signal feedback",
    )
    tune_parser.set_defaults(handler=handle_tune_suggestions)

    triage_stats_parser = subparsers.add_parser(
        "insight-triage-stats",
        help="Show triage counts and recent rejection memory",
    )
    triage_stats_parser.set_defaults(handler=handle_insight_triage_stats)

    memory_parser = subparsers.add_parser(
        "memory",
        help="Inspect memory surfaces (evidence, decisions, snapshots)",
    )
    memory_sub = memory_parser.add_subparsers(dest="memory_command", required=True)

    ie_parser = memory_sub.add_parser("inspect-evidence")
    ie_parser.add_argument("--project", default=None)
    ie_parser.add_argument("--week", default=None)
    ie_parser.add_argument("--kind", default=None)
    ie_parser.add_argument("--limit", type=int, default=20)
    ie_parser.set_defaults(handler=handle_memory_inspect_evidence)

    id_parser = memory_sub.add_parser("inspect-decisions")
    id_parser.add_argument("--project", default=None)
    id_parser.add_argument("--scope", dest="decision_scope", default=None)
    id_parser.add_argument("--status", default=None)
    id_parser.add_argument("--limit", type=int, default=20)
    id_parser.set_defaults(handler=handle_memory_inspect_decisions)

    is_parser = memory_sub.add_parser("inspect-snapshots")
    is_parser.add_argument("--stale-only", action="store_true")
    is_parser.set_defaults(handler=handle_memory_inspect_snapshots)

    isupp_parser = memory_sub.add_parser("inspect-suppression")
    isupp_parser.add_argument("--title", required=True)
    isupp_parser.set_defaults(handler=handle_memory_inspect_suppression)

    memory_parser.set_defaults(handler=lambda args: memory_parser.print_help() or 0)

    return parser


def handle_ingest(args: argparse.Namespace) -> int:
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

        if not getattr(args, "skip_reactions", False):
            try:
                from ingestion.reaction_sync import sync_reactions

                LOGGER.info("Starting step=sync_reactions")
                reaction_summary = asyncio.run(sync_reactions(settings, days=14, limit=300))
                LOGGER.info(
                    "Finished step=sync_reactions posts_checked=%d posts_with_reactions=%d "
                    "applied_tags=%d applied_feedback=%d skipped_existing=%d errors=%d",
                    reaction_summary["posts_checked"],
                    reaction_summary["posts_with_reactions"],
                    reaction_summary["applied_tags"],
                    reaction_summary["applied_feedback"],
                    reaction_summary["skipped_existing"],
                    reaction_summary["errors"],
                )
            except Exception:
                LOGGER.exception("Reaction sync failed; continuing ingest pipeline")

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

        LOGGER.info("Starting step=score_posts")
        scoring_summary = score_posts(settings, since_days=7)
        LOGGER.info(
            "Finished step=score_posts scored=%d strong=%d watch=%d cultural=%d noise=%d avg=%.4f",
            scoring_summary.get("scored", 0),
            scoring_summary.get("strong", 0),
            scoring_summary.get("watch", 0),
            scoring_summary.get("cultural", 0),
            scoring_summary.get("noise", 0),
            scoring_summary.get("avg_signal_score", 0.0),
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


def handle_sync_reactions(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        from ingestion.reaction_sync import sync_reactions

        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        LOGGER.info("Starting step=sync_reactions days=%d limit=%d", args.days, args.limit)
        summary = asyncio.run(sync_reactions(settings, days=args.days, limit=args.limit))
        LOGGER.info(
            "Finished step=sync_reactions posts_checked=%d posts_with_reactions=%d "
            "matched_reactions=%d applied_tags=%d applied_feedback=%d skipped_unknown=%d "
            "skipped_existing=%d errors=%d",
            summary["posts_checked"],
            summary["posts_with_reactions"],
            summary["matched_reactions"],
            summary["applied_tags"],
            summary["applied_feedback"],
            summary["skipped_unknown"],
            summary["skipped_existing"],
            summary["errors"],
        )
    except Exception:
        LOGGER.exception("Reaction sync failed")
        return 1
    return 0 if summary["errors"] == 0 else 1


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


def handle_digest(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        LOGGER.info("Starting step=generate_digest")
        summary = run_digest(settings, force_delivery=getattr(args, "force", False))
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


def handle_score(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        LOGGER.info("Starting step=score_posts days=%d", args.days)
        summary = score_posts(settings, since_days=args.days)
        LOGGER.info(
            "Finished step=score_posts scored=%d strong=%d watch=%d cultural=%d noise=%d avg=%.4f errors=%d",
            summary.get("scored", 0),
            summary.get("strong", 0),
            summary.get("watch", 0),
            summary.get("cultural", 0),
            summary.get("noise", 0),
            summary.get("avg_signal_score", 0.0),
            summary.get("errors", 0),
        )
    except Exception:
        LOGGER.exception("Scoring failed")
        return 1
    return 0


def handle_score_stats(_: argparse.Namespace) -> int:
    settings = load_settings()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat().replace("+00:00", "Z")

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            connection.execute("PRAGMA journal_mode = WAL;")

            bucket_rows = connection.execute(
                """
                SELECT bucket, COUNT(*) AS post_count, AVG(signal_score) AS avg_signal_score
                FROM posts
                WHERE posted_at >= ? AND bucket IS NOT NULL
                GROUP BY bucket
                """,
                (cutoff,),
            ).fetchall()
            bucket_stats = {
                row["bucket"]: {
                    "count": int(row["post_count"] or 0),
                    "avg": float(row["avg_signal_score"] or 0.0),
                }
                for row in bucket_rows
            }

            topic_rows = connection.execute(
                """
                SELECT t.label, COUNT(*) AS topic_count
                FROM post_topics pt
                INNER JOIN topics t ON t.id = pt.topic_id
                INNER JOIN posts p ON p.id = pt.post_id
                WHERE p.posted_at >= ? AND p.bucket IS NOT NULL
                GROUP BY t.id, t.label
                ORDER BY topic_count DESC, t.label ASC
                LIMIT 3
                """,
                (cutoff,),
            ).fetchall()

            # Trend vs previous week from quality_metrics
            qm_rows = connection.execute(
                """
                SELECT week_label, strong_count, watch_count, noise_count, total_posts
                FROM quality_metrics
                ORDER BY week_label DESC
                LIMIT 2
                """
            ).fetchall()
    except Exception:
        LOGGER.exception("Score stats failed")
        return 1

    lines = ["Score stats (last 7 days)"]
    for bucket in ("strong", "watch", "cultural", "noise"):
        stats = bucket_stats.get(bucket, {"count": 0, "avg": 0.0})
        lines.append(f"{bucket}: count={stats['count']} avg_signal_score={stats['avg']:.4f}")

    if topic_rows:
        lines.append("top_topics: " + ", ".join(f"{row['label']} ({int(row['topic_count'])})" for row in topic_rows))
    else:
        lines.append("top_topics: none")

    if len(qm_rows) >= 2:
        current_qm, prior_qm = qm_rows[0], qm_rows[1]
        lines.append(f"trend vs {prior_qm['week_label']}:")
        for col in ("strong_count", "watch_count", "noise_count"):
            cur = int(current_qm[col] or 0)
            prev = int(prior_qm[col] or 0)
            delta = cur - prev
            lines.append(f"  {col}: {cur} ({delta:+d})")
    elif len(qm_rows) == 1:
        lines.append(f"trend: only one run recorded ({qm_rows[0]['week_label']}), no comparison yet")

    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def handle_cost_stats(_: argparse.Namespace) -> int:
    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            connection.execute("PRAGMA journal_mode = WAL;")

            total_row = connection.execute(
                """
                SELECT
                    COUNT(*) AS call_count,
                    COALESCE(SUM(cost_usd), 0.0) AS total_cost_usd,
                    COALESCE(SUM(est_cost_usd), 0.0) AS total_est_cost_usd,
                    COUNT(DISTINCT substr(called_at, 1, 10)) AS distinct_days
                FROM llm_usage
                """
            ).fetchone()
            model_rows = connection.execute(
                """
                SELECT
                    model,
                    COUNT(*) AS call_count,
                    COALESCE(SUM(cost_usd), 0.0) AS total_cost_usd,
                    COALESCE(SUM(est_cost_usd), 0.0) AS total_est_cost_usd
                FROM llm_usage
                GROUP BY model
                ORDER BY total_cost_usd DESC, model ASC
                """
            ).fetchall()
            # Weekly cost trend: last 4 distinct weeks
            weekly_rows = connection.execute(
                """
                SELECT
                    strftime('%Y-W%W', called_at) AS week,
                    COALESCE(SUM(cost_usd), 0.0) AS week_cost,
                    COALESCE(SUM(est_cost_usd), 0.0) AS week_est_cost,
                    COUNT(*) AS call_count
                FROM llm_usage
                GROUP BY week
                ORDER BY week DESC
                LIMIT 4
                """
            ).fetchall()
            weekly_category_rows = connection.execute(
                """
                SELECT
                    strftime('%Y-W%W', called_at) AS week,
                    category,
                    COUNT(*) AS call_count,
                    COALESCE(SUM(cost_usd), 0.0) AS week_cost
                FROM llm_usage
                GROUP BY week, category
                ORDER BY week DESC, week_cost DESC, category ASC
                LIMIT 20
                """
            ).fetchall()
    except Exception:
        LOGGER.exception("Cost stats failed")
        return 1

    lines = [
        f"total_cost_usd={float(total_row['total_cost_usd'] or 0.0):.8f}",
        f"total_est_cost_usd={float(total_row['total_est_cost_usd'] or 0.0):.8f}",
        f"distinct_days={int(total_row['distinct_days'] or 0)}",
        "by_model:",
    ]
    if model_rows:
        for row in model_rows:
            lines.append(
                f"{row['model']} call_count={int(row['call_count'] or 0)} "
                f"total_cost_usd={float(row['total_cost_usd'] or 0.0):.8f} "
                f"total_est_cost_usd={float(row['total_est_cost_usd'] or 0.0):.8f}"
            )
    else:
        lines.append("none")

    if weekly_rows:
        lines.append("weekly_trend (last 4 weeks):")
        for row in weekly_rows:
            lines.append(
                f"  {row['week']}  calls={int(row['call_count'] or 0)}  "
                f"cost=${float(row['week_cost'] or 0.0):.6f}  "
                f"est=${float(row['week_est_cost'] or 0.0):.6f}"
            )
    if weekly_category_rows:
        lines.append("weekly_by_category (recent):")
        for row in weekly_category_rows:
            lines.append(
                f"  {row['week']}  {row['category']}  calls={int(row['call_count'] or 0)}  "
                f"cost=${float(row['week_cost'] or 0.0):.6f}"
            )

    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def _config_status_lines() -> list[str]:
    config_paths = (
        PROJECT_ROOT / "src" / "config" / "profile.yaml",
        PROJECT_ROOT / "src" / "config" / "projects.yaml",
        PROJECT_ROOT / "src" / "config" / "scoring.yaml",
    )
    return [f"{path.name}: {'present' if path.exists() else 'missing'}" for path in config_paths]


def handle_health_check(_: argparse.Namespace) -> int:
    db_path_raw = os.environ.get("AGENT_DB_PATH", "").strip()
    lines: list[str] = []

    if not db_path_raw:
        lines.append("DB_PATH not configured")
        lines.extend(_config_status_lines())
        sys.stdout.write("\n".join(lines) + "\n")
        return 0

    db_path = Path(db_path_raw)
    if not db_path.is_absolute():
        db_path = (PROJECT_ROOT / db_path).resolve()

    lines.append(f"db_path: {db_path}")
    if db_path.exists():
        try:
            with sqlite3.connect(db_path) as connection:
                connection.row_factory = sqlite3.Row
                posts_count = int(connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0])
                scored_posts_count = int(
                    connection.execute("SELECT COUNT(*) FROM posts WHERE scored_at IS NOT NULL").fetchone()[0]
                )
                llm_usage_count = int(connection.execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0])
                last_ingestion = (
                    connection.execute("SELECT MAX(ingested_at) FROM raw_posts").fetchone()[0] or "never"
                )
                last_scored = (
                    connection.execute("SELECT MAX(scored_at) FROM posts").fetchone()[0] or "never"
                )
                last_digest_row = connection.execute(
                    "SELECT week_label FROM digests ORDER BY week_label DESC LIMIT 1"
                ).fetchone()
                last_digest = last_digest_row[0] if last_digest_row else "none"
                unscored_count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM posts WHERE scored_at IS NULL"
                    ).fetchone()[0]
                )
        except Exception as exc:
            lines.append(f"db_error: {exc}")
        else:
            lines.append(f"posts: {posts_count}")
            lines.append(f"scored_posts: {scored_posts_count}")
            lines.append(f"llm_usage: {llm_usage_count}")
            lines.append(f"last_ingestion: {last_ingestion}")
            lines.append(f"last_scored: {last_scored}")
            lines.append(f"last_digest: {last_digest}")
            if unscored_count > 0:
                lines.append(f"WARNING: {unscored_count} posts pending scoring (stuck queue?)")
    else:
        lines.append("db_status: missing")

    lines.extend(_config_status_lines())
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def handle_report_preview(_: argparse.Namespace) -> int:
    settings = load_settings()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat().replace("+00:00", "Z")

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            connection.execute("PRAGMA journal_mode = WAL;")

            recent_rows = connection.execute(
                """
                SELECT id, content, signal_score, bucket, routed_model, score_breakdown, scored_at, posted_at
                FROM posts
                WHERE scored_at IS NOT NULL AND posted_at >= ?
                ORDER BY posted_at DESC
                """,
                (cutoff,),
            ).fetchall()

            if len(recent_rows) >= 10:
                rows = recent_rows
            else:
                rows = connection.execute(
                    """
                    SELECT id, content, signal_score, bucket, routed_model, score_breakdown, scored_at, posted_at
                    FROM posts
                    WHERE scored_at IS NOT NULL
                    ORDER BY posted_at DESC
                    """
                ).fetchall()
    except Exception:
        LOGGER.exception("Report preview failed")
        sys.stdout.write("No scored posts found. Run score-posts first.\n")
        return 0

    if not rows:
        sys.stdout.write("No scored posts found. Run score-posts first.\n")
        return 0

    report = format_signal_report([dict(row) for row in rows], settings)
    sys.stdout.write(report)
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
            LOGGER.info("Starting step=send_study_reminder")
            send_study_reminder(settings)
            LOGGER.info("Finished step=send_study_reminder")
            return 0

        LOGGER.info("Starting step=generate_study_plan")
        generate_study_plan(settings, force=getattr(args, "force", False))
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


def handle_tune_suggestions(_: argparse.Namespace) -> int:
    import json
    import yaml

    settings = load_settings()

    try:
        run_migrations()
        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT p.score_breakdown
                FROM signal_feedback sf
                JOIN posts p ON p.id = sf.post_id
                WHERE sf.feedback = 'acted_on'
                """
            ).fetchall()
    except Exception:
        sys.stdout.write("Could not read feedback data. Run migrations and record some feedback first.\n")
        return 0

    if not rows:
        sys.stdout.write("No acted-on feedback found. Use /mark_useful <post_id> to record feedback.\n")
        return 0

    topic_counts: dict[str, int] = {}
    for row in rows:
        breakdown = {}
        try:
            breakdown = json.loads(row["score_breakdown"] or "{}") or {}
        except (TypeError, json.JSONDecodeError):
            pass
        topic = breakdown.get("topic") or ""
        if isinstance(topic, str) and topic.strip():
            topic_counts[topic.strip()] = topic_counts.get(topic.strip(), 0) + 1
        for label in (breakdown.get("topics") or []):
            if isinstance(label, str) and label.strip():
                topic_counts[label.strip()] = topic_counts.get(label.strip(), 0) + 1

    boost_topics: list[str] = []
    try:
        profile_data = yaml.safe_load(_PROFILE_YAML_PATH.read_text(encoding="utf-8")) or {}
        boost_topics = [str(t).lower() for t in (profile_data.get("boost_topics") or [])]
    except Exception:
        pass

    suggestions = [
        (topic, count)
        for topic, count in topic_counts.items()
        if count >= 2 and topic.lower() not in boost_topics
    ]
    suggestions.sort(key=lambda x: x[1], reverse=True)

    if not suggestions:
        sys.stdout.write("No suggestions — boost list may already cover your acted-on signals.\n")
        return 0

    sys.stdout.write("Suggested boost topics (appeared in acted-on signals but not in your profile):\n")
    for topic, count in suggestions:
        sys.stdout.write(f"  - {topic} (seen {count} times)\n")
    return 0


def handle_insight_triage_stats(_: argparse.Namespace) -> int:
    settings = load_settings()

    try:
        run_migrations()
        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            count_rows = connection.execute(
                """
                SELECT recommendation, COUNT(*) AS cnt
                FROM insight_triage_records
                GROUP BY recommendation
                ORDER BY recommendation ASC
                """
            ).fetchall()
            recent_rows = connection.execute(
                """
                SELECT week_label, recommendation, title, reason
                FROM insight_triage_records
                ORDER BY created_at DESC
                LIMIT 10
                """
            ).fetchall()
            memory_rows = connection.execute(
                """
                SELECT title, reason, rejected_at
                FROM insight_rejection_memory
                ORDER BY rejected_at DESC
                LIMIT 5
                """
            ).fetchall()
    except Exception:
        LOGGER.exception("Insight triage stats failed")
        return 1

    lines = ["Insight triage summary:"]
    if count_rows:
        for row in count_rows:
            lines.append(f"  {row['recommendation']}: {int(row['cnt'])}")
    else:
        lines.append("  no triage records found")

    if recent_rows:
        lines.append("Recent triage records (last 10):")
        for row in recent_rows:
            lines.append(f"  [{row['week_label']}] {row['recommendation']} — {row['title'][:60]}")
            lines.append(f"    reason: {row['reason']}")

    if memory_rows:
        lines.append("Rejection memory (last 5):")
        for row in memory_rows:
            lines.append(f"  {row['rejected_at'][:10]}  {row['title'][:60]}")
            lines.append(f"    reason: {row['reason']}")
    else:
        lines.append("Rejection memory: empty")

    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def handle_memory_inspect_evidence(args: argparse.Namespace) -> int:
    from db.retrieval import fetch_evidence_items

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")

            items = fetch_evidence_items(
                connection,
                project_name=args.project,
                week_label=args.week,
                evidence_kind=args.kind,
                limit=args.limit,
            )
    except Exception as exc:
        sys.stdout.write(f"Error inspecting evidence items: {exc}\n")
        return 1

    if not items:
        sys.stdout.write("No evidence items found for the given scope.\n")
        return 0

    lines: list[str] = []
    for item in items:
        posted_at = item.get("posted_at") or ""
        excerpt = (item.get("excerpt_text") or "")[:120]
        url = item.get("message_url") or "n/a"
        lines.append(
            f"[{item.get('week_label') or 'n/a'}] {item.get('evidence_kind') or 'n/a'} | "
            f"{item.get('source_channel') or 'n/a'} | {posted_at[:10]}"
        )
        lines.append(f"  excerpt: {excerpt}")
        lines.append(f"  url: {url}")
        lines.append(f"  reason: {item.get('selection_reason') or 'n/a'}")
        lines.append("")

    sys.stdout.write("\n".join(lines).rstrip() + "\n")
    return 0


def handle_memory_inspect_decisions(args: argparse.Namespace) -> int:
    from db.retrieval import fetch_decisions

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")

            decisions = fetch_decisions(
                connection,
                project_name=args.project,
                decision_scope=args.decision_scope,
                status=args.status,
                limit=args.limit,
            )
    except Exception as exc:
        sys.stdout.write(f"Error inspecting decision journal: {exc}\n")
        return 1

    if not decisions:
        sys.stdout.write("No decision journal entries found.\n")
        return 0

    lines: list[str] = []
    for row in decisions:
        recorded_at = row.get("recorded_at") or ""
        lines.append(
            f"[{recorded_at[:10]}] {row.get('decision_scope') or 'n/a'}/{row.get('status') or 'n/a'} | "
            f"ref={row.get('subject_ref_type') or 'n/a'}:{row.get('subject_ref_id') or 'n/a'}"
        )
        lines.append(f"  reason: {row.get('reason') or 'n/a'}")

    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def handle_memory_inspect_snapshots(args: argparse.Namespace) -> int:
    from db.retrieval import fetch_stale_snapshots

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")

            if args.stale_only:
                rows = fetch_stale_snapshots(connection)
            else:
                rows = [
                    dict(row)
                    for row in connection.execute(
                        """
                        SELECT project_id, project_name, snapshot_week_label, updated_at, linked_signal_count
                        FROM project_context_snapshots
                        ORDER BY project_name ASC
                        """
                    ).fetchall()
                ]
    except Exception as exc:
        sys.stdout.write(f"Error inspecting project snapshots: {exc}\n")
        return 1

    if not rows:
        sys.stdout.write("No project snapshots found.\n")
        return 0

    lines = [
        f"{row.get('project_name') or 'n/a'} | week={row.get('snapshot_week_label') or 'never'} | "
        f"signals={row.get('linked_signal_count') or 0} | updated={(row.get('updated_at') or '')[:10]}"
        for row in rows
    ]
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def handle_memory_inspect_suppression(args: argparse.Namespace) -> int:
    from db.retrieval import fetch_suppression_context
    from output.insight_triage import _normalize_fingerprint

    settings = load_settings()

    try:
        LOGGER.info("Starting step=run_migrations")
        run_migrations()
        LOGGER.info("Finished step=run_migrations")

        fingerprint = _normalize_fingerprint(args.title)

        with sqlite3.connect(settings.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON;")
            context = fetch_suppression_context(connection, fingerprint)
    except Exception as exc:
        sys.stdout.write(f"Error inspecting suppression context: {exc}\n")
        return 1

    rejection_memory = context.get("rejection_memory")
    recent_decisions = context.get("recent_decisions") or []

    lines = [
        f"Fingerprint: {fingerprint}",
        f"Rejection memory: {rejection_memory or 'not found'}",
        f"Recent decisions ({len(recent_decisions)}):",
    ]
    for row in recent_decisions:
        recorded_at = row.get("recorded_at") or ""
        lines.append(f"  [{recorded_at[:10]}] {row.get('status') or 'n/a'} — {row.get('reason') or 'n/a'}")

    if rejection_memory is None:
        lines.append("No rejection memory entry found for this title.")

    sys.stdout.write("\n".join(lines) + "\n")
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
